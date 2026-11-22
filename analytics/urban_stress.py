from __future__ import annotations

import pandas as pd

PM_REFERENCES_UG_M3 = {"pm25": 60.0, "pm10": 100.0}
MAX_READING_AGE_HOURS = 48


def _normalise_parameter(value: object) -> str | None:
    token = str(value).lower().replace("_", "").replace(" ", "")
    token = token.replace("₂", "2").replace("₅", "5").replace(".", "")
    if token in {"pm25", "pm2.5", "pm25mass"}:
        return "pm25"
    if token in {"pm10", "pm10mass"}:
        return "pm10"
    return None


def _unit_to_ug_m3(unit: object) -> float | None:
    token = str(unit).lower().replace(" ", "").replace("μ", "µ")
    token = token.replace("³", "3").replace("^", "")
    return {"µg/m3": 1.0, "ug/m3": 1.0, "mg/m3": 1000.0}.get(token)


def _latest_citywide_pm(air: pd.DataFrame, now: pd.Timestamp) -> dict[str, float]:
    if air.empty or not {"parameter", "value", "unit", "datetime_utc"}.issubset(air.columns):
        return {}
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")

    frame = air.copy()
    frame["pollutant"] = frame["parameter"].map(_normalise_parameter)
    frame = frame[frame["pollutant"].notna()].copy()
    frame["unit_factor"] = frame["unit"].map(_unit_to_ug_m3)
    frame = frame[frame["unit_factor"].notna()].copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce") * frame["unit_factor"]
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["value", "datetime_utc"])
    if frame.empty:
        return {}

    cutoff = now - pd.Timedelta(hours=MAX_READING_AGE_HOURS)
    frame = frame.loc[
        (frame["datetime_utc"] >= cutoff)
        & (frame["datetime_utc"] <= now + pd.Timedelta(minutes=15))
    ].copy()
    if "is_mobile" in frame.columns:
        mobile = frame["is_mobile"].map(
            lambda value: str(value).strip().lower() in {"true", "1", "yes", "y"}
        )
        frame = frame.loc[~mobile].copy()
    if frame.empty:
        return {}

    # Use one latest value per fixed station and pollutant, then median across stations.
    if "location_id" in frame.columns:
        fallback = frame["station"] if "station" in frame.columns else frame.index.astype(str)
        frame["_station_key"] = frame["location_id"].where(frame["location_id"].notna(), fallback)
    elif "station" in frame.columns:
        frame["_station_key"] = frame["station"]
    else:
        frame["_station_key"] = frame.index.astype(str)
    frame = frame.sort_values("datetime_utc").drop_duplicates(
        subset=["_station_key", "pollutant"], keep="last"
    )
    return frame.groupby("pollutant")["value"].median().to_dict()


def calculate_urban_stress(
    current_weather: dict,
    air: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> dict:
    """Compute an experimental composite environmental stress signal.

    It is a project-specific heuristic, not India's official AQI or a health
    advisory. PM references are used only as transparent normalisation anchors.
    """
    if not current_weather:
        return {"index": None, "reason": "Current weather data is unavailable."}

    now = now or pd.Timestamp.now(tz="UTC")
    apparent = pd.to_numeric(current_weather.get("apparent_temperature"), errors="coerce")
    precipitation = pd.to_numeric(current_weather.get("precipitation"), errors="coerce")
    if pd.isna(apparent):
        return {"index": None, "reason": "Apparent-temperature data is unavailable."}

    heat_score = min(100.0, max(0.0, (float(apparent) - 22.0) / 18.0 * 100.0))
    if pd.isna(precipitation):
        return {
            "index": None,
            "heat_score": round(heat_score, 1),
            "air_score": None,
            "rain_score": None,
            "reason": "Rainfall input is unavailable; the composite is withheld rather than assuming zero rainfall.",
        }
    rainfall_value = float(precipitation)
    rain_score = min(100.0, max(0.0, rainfall_value / 10.0 * 100.0))
    pm = _latest_citywide_pm(air, now)
    pm_scores = [
        min(100.0, max(0.0, pm[name] / reference * 100.0))
        for name, reference in PM_REFERENCES_UG_M3.items()
        if name in pm
    ]
    air_score = max(pm_scores) if pm_scores else None

    if air_score is None:
        return {
            "index": None,
            "heat_score": round(heat_score, 1),
            "air_score": None,
            "rain_score": round(rain_score, 1),
            "pm25_median": pm.get("pm25"),
            "pm10_median": pm.get("pm10"),
            "reason": "A recent PM2.5 or PM10 observation is needed for the composite score.",
        }

    composite = 0.50 * heat_score + 0.35 * air_score + 0.15 * rain_score
    return {
        "index": round(float(composite), 1),
        "heat_score": round(heat_score, 1),
        "air_score": round(float(air_score), 1),
        "rain_score": round(rain_score, 1),
        "pm25_median": round(pm["pm25"], 2) if "pm25" in pm else None,
        "pm10_median": round(pm["pm10"], 2) if "pm10" in pm else None,
        "reason": None,
    }


def calculate_projected_urban_stress(
    weather_prediction: dict,
    pm25_ug_m3: float | None,
    pm10_ug_m3: float | None,
) -> dict:
    """Calculate a projected CityPulse Index from validated model outputs only.

    The component scores intentionally match the current experimental heuristic.
    Caller must pass only pollutant forecasts that cleared their persistence test.
    Missing weather or particulate forecasts withhold the composite.
    """
    apparent = pd.to_numeric(weather_prediction.get("apparent_temperature"), errors="coerce")
    precipitation = pd.to_numeric(weather_prediction.get("precipitation"), errors="coerce")
    if pd.isna(apparent) or pd.isna(precipitation):
        return {
            "index": None,
            "reason": "A validated apparent-temperature and hourly-rainfall forecast are both required.",
        }

    pm_values = {}
    for name, value in (("pm25", pm25_ug_m3), ("pm10", pm10_ug_m3)):
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric) and float(numeric) >= 0:
            pm_values[name] = float(numeric)
    if not pm_values:
        return {
            "index": None,
            "reason": "At least one validated fixed-station PM2.5 or PM10 forecast is required.",
        }

    heat_score = min(100.0, max(0.0, (float(apparent) - 22.0) / 18.0 * 100.0))
    rain_score = min(100.0, max(0.0, float(precipitation) / 10.0 * 100.0))
    pm_scores = [
        min(100.0, max(0.0, pm_values[name] / reference * 100.0))
        for name, reference in PM_REFERENCES_UG_M3.items()
        if name in pm_values
    ]
    air_score = max(pm_scores)
    index = 0.50 * heat_score + 0.35 * air_score + 0.15 * rain_score
    return {
        "index": round(float(index), 1),
        "heat_score": round(heat_score, 1),
        "air_score": round(air_score, 1),
        "rain_score": round(rain_score, 1),
        "pm25_forecast_ug_m3": round(pm_values["pm25"], 2) if "pm25" in pm_values else None,
        "pm10_forecast_ug_m3": round(pm_values["pm10"], 2) if "pm10" in pm_values else None,
        "reason": None,
        "method": "50% heat + 35% particulate + 15% hourly rainfall",
    }
