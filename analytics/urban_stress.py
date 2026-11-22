from __future__ import annotations

import pandas as pd

PM_REFERENCES_UG_M3 = {"pm25": 60.0, "pm10": 100.0}
MAX_READING_AGE_HOURS = 48


def _normalise_parameter(value: object) -> str | None:
    token = str(value).lower().replace("_", "").replace(" ", "")
    token = token.replace("₂", "2").replace(".", "")
    if token in {"pm25", "pm2.5", "pm25mass"}:
        return "pm25"
    if token in {"pm10", "pm10mass"}:
        return "pm10"
    return None


def _is_micrograms_per_cubic_metre(unit: object) -> bool:
    token = str(unit).lower().replace(" ", "").replace("μ", "µ")
    return token in {"µg/m³", "ug/m3", "µg/m3", "ug/m³", "µg/m^3", "ug/m^3"}


def _latest_citywide_pm(air: pd.DataFrame, now: pd.Timestamp) -> dict[str, float]:
    if air.empty or not {"parameter", "value", "unit", "datetime_utc"}.issubset(air.columns):
        return {}

    frame = air.copy()
    frame["pollutant"] = frame["parameter"].map(_normalise_parameter)
    frame = frame[frame["pollutant"].notna()]
    frame = frame[frame["unit"].map(_is_micrograms_per_cubic_metre)]
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["value", "datetime_utc"])
    if frame.empty:
        return {}

    cutoff = now - pd.Timedelta(hours=MAX_READING_AGE_HOURS)
    frame = frame[frame["datetime_utc"] >= cutoff]
    if frame.empty:
        return {}

    # Use one latest value per station and pollutant, then median across stations.
    station_key = "location_id" if "location_id" in frame.columns else "station"
    frame = frame.sort_values("datetime_utc").drop_duplicates(
        subset=[station_key, "pollutant"], keep="last"
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

    heat_score = float(((apparent - 22.0) / 18.0 * 100.0).clip(0, 100))
    rain_score = float(((precipitation if pd.notna(precipitation) else 0.0) / 10.0 * 100.0).clip(0, 100))
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
