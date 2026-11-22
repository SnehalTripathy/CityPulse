from __future__ import annotations

import math

import pandas as pd

from analytics.comparison import latest_pollutant_summary


DEFAULT_ALERT_THRESHOLDS = {
    "heat_c": 40.0,
    "rainfall_mm": 20.0,
    "pm25_ug_m3": 60.0,
    "pm10_ug_m3": 100.0,
}

ALERT_COLUMNS = [
    "Signal", "Trigger basis", "Value", "Configured threshold", "Time",
    "Source and data type", "Stations", "Status",
]

RECOMMENDATIONS = {
    "Heat": (
        "Check the latest alert from the relevant national or local weather authority. "
        "Consider shifting strenuous outdoor work away from the hottest hours and make drinking water and shaded rest available."
    ),
    "Rainfall": (
        "Check local meteorological and municipal advisories before travelling. Avoid waterlogged underpasses and low-lying routes; "
        "this rainfall trigger does not establish that flooding is occurring."
    ),
    "PM2.5": (
        "Check the official air-quality bulletin for the area and consider reducing prolonged outdoor activity near traffic or visible sources. "
        "This station sample may not represent the whole city."
    ),
    "PM10": (
        "Check the official air-quality bulletin and consider limiting prolonged exposure near dust-generating activity. "
        "This station sample may not represent the whole city."
    ),
}


def _number(value: object) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed) or not math.isfinite(float(parsed)):
        return None
    return float(parsed)


def _time_label(value: object) -> str:
    if value is None or pd.isna(value):
        return "Timestamp unavailable"
    return str(value)


def _forecast_window(forecast: pd.DataFrame, current_weather: dict) -> pd.DataFrame:
    if forecast.empty or "time" not in forecast.columns:
        return pd.DataFrame()
    frame = forecast.copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame = frame.dropna(subset=["time"])
    if frame.empty:
        return frame
    start = pd.to_datetime(current_weather.get("time"), errors="coerce")
    if pd.isna(start):
        start = frame["time"].min()
    # Open-Meteo returns its selected city's local ISO timestamps. The app
    # passes the current and hourly values in that same local time basis.
    if getattr(frame["time"].dt, "tz", None) is None and getattr(start, "tzinfo", None) is not None:
        start = start.tz_localize(None)
    elif getattr(frame["time"].dt, "tz", None) is not None and getattr(start, "tzinfo", None) is None:
        start = start.tz_localize(frame["time"].dt.tz)
    end = start + pd.Timedelta(hours=24)
    return frame.loc[(frame["time"] > start) & (frame["time"] <= end)].copy()


def build_alert_assessment(
    current_weather: dict,
    forecast: pd.DataFrame,
    air: pd.DataFrame,
    thresholds: dict | None = None,
    now: pd.Timestamp | None = None,
) -> dict:
    """Build explainable prototype alerts from provider conditions, forecasts and station readings.

    Thresholds are user-configured product triggers, not regulatory standards,
    official warnings or medical thresholds. Open-Meteo weather values are
    modelled grid-cell data; particulate medians come from eligible fixed OpenAQ
    stations no more than 24 hours old.
    """
    configured = {**DEFAULT_ALERT_THRESHOLDS, **(thresholds or {})}
    rows: list[dict] = []
    recommendations: dict[str, str] = {}
    unavailable: list[str] = []

    def add(signal: str, basis: str, value: float, threshold: float, timestamp: object, source: str, stations: int | None = None) -> None:
        rows.append({
            "Signal": signal,
            "Trigger basis": basis,
            "Value": value,
            "Configured threshold": threshold,
            "Time": _time_label(timestamp),
            "Source and data type": source,
            "Stations": stations if stations is not None else "—",
            "Status": "Threshold crossed",
        })
        recommendations[signal] = RECOMMENDATIONS[signal]

    # Current modelled weather conditions (not a physical weather station reading).
    apparent = _number(current_weather.get("apparent_temperature")) if current_weather else None
    if apparent is not None:
        if apparent >= configured["heat_c"]:
            add(
                "Heat", "Current apparent temperature", apparent, configured["heat_c"],
                current_weather.get("time"),
                "Open-Meteo current modelled grid-cell condition",
            )
    else:
        unavailable.append("Current apparent temperature is unavailable.")

    recent_rain = _number(current_weather.get("precipitation")) if current_weather else None
    if recent_rain is not None:
        if recent_rain >= configured["rainfall_mm"]:
            add(
                "Rainfall", "Current preceding-hour precipitation", recent_rain,
                configured["rainfall_mm"], current_weather.get("time"),
                "Open-Meteo current modelled grid-cell condition; preceding-hour sum",
            )
    else:
        unavailable.append("Current preceding-hour precipitation is unavailable.")

    # Forecast is evaluated independently and limited to the next 24 hours.
    window = _forecast_window(forecast, current_weather or {})
    if not window.empty:
        if "apparent_temperature" in window.columns:
            heat_series = pd.to_numeric(window["apparent_temperature"], errors="coerce").dropna()
            if not heat_series.empty:
                peak_idx = heat_series.idxmax()
                peak = float(heat_series.loc[peak_idx])
                if peak >= configured["heat_c"]:
                    add(
                        "Heat", "Highest apparent temperature in next 24 hours", peak,
                        configured["heat_c"], window.loc[peak_idx, "time"],
                        "Open-Meteo hourly forecast; modelled grid-cell estimate",
                    )
            else:
                unavailable.append("Next-24-hour apparent-temperature forecast is unavailable.")
        else:
            unavailable.append("Next-24-hour apparent-temperature forecast is unavailable.")

        if "precipitation" in window.columns:
            rain_series = pd.to_numeric(window["precipitation"], errors="coerce").dropna()
            if not rain_series.empty:
                peak_idx = rain_series.idxmax()
                peak = float(rain_series.loc[peak_idx])
                if peak >= configured["rainfall_mm"]:
                    add(
                        "Rainfall", "Highest hourly precipitation in next 24 hours", peak,
                        configured["rainfall_mm"], window.loc[peak_idx, "time"],
                        "Open-Meteo hourly forecast; preceding-hour sum",
                    )
            else:
                unavailable.append("Next-24-hour hourly precipitation forecast is unavailable.")
        else:
            unavailable.append("Next-24-hour hourly precipitation forecast is unavailable.")
    else:
        unavailable.append("A usable next-24-hour forecast window is unavailable.")

    # PM alerts use a station median in compatible mass-concentration units.
    reference_time = now or pd.Timestamp.now(tz="UTC")
    for pollutant, key in (("pm25", "pm25_ug_m3"), ("pm10", "pm10_ug_m3")):
        summary = latest_pollutant_summary(
            air, pollutant, now=reference_time, max_age_hours=24
        )
        if summary["value"] is None or summary["station_count"] < 1:
            unavailable.append(
                f"{pollutant.upper()}: no eligible fixed-station reading no more than 24 hours old."
            )
            continue
        if summary["value"] >= configured[key]:
            add(
                pollutant.upper(), "Median of latest eligible fixed-station readings",
                float(summary["value"]), configured[key], summary["latest_utc"],
                "OpenAQ fixed monitoring stations; compatible units normalised to µg/m³",
                int(summary["station_count"]),
            )

    alerts = pd.DataFrame(rows, columns=ALERT_COLUMNS)
    if not alerts.empty:
        alerts = alerts.sort_values(["Signal", "Time"], kind="stable").reset_index(drop=True)
    return {
        "alerts": alerts,
        "recommendations": [
            {"signal": signal, "text": text}
            for signal, text in sorted(recommendations.items())
        ],
        "unavailable": unavailable,
        "thresholds": configured,
        "forecast_hours_checked": int(len(window)),
    }
