from __future__ import annotations

import pandas as pd

from analytics.data_quality import summarize_air_quality
from analytics.urban_stress import calculate_urban_stress


def _normalise_parameter(value: object) -> str:
    return (
        str(value).lower().replace(".", "").replace("_", "").replace(" ", "")
        .replace("₂", "2").replace("₅", "5")
    )


def _normalise_unit(value: object) -> str:
    return (
        str(value).lower().replace(" ", "").replace("μ", "µ")
        .replace("³", "3").replace("^", "")
    )


UNIT_TO_UG_M3 = {
    "µg/m3": 1.0,
    "ug/m3": 1.0,
    "mg/m3": 1000.0,
}


def pollutant_median(summary: pd.DataFrame, pollutant: str) -> float | None:
    """Return a µg/m³ median after unit conversion; reject incomparable units."""
    if summary.empty:
        return None
    tokens = summary["parameter"].map(_normalise_parameter)
    matched = summary.loc[
        tokens.isin({pollutant, pollutant + "mass"})
    ].copy()
    matched["unit_token"] = matched["unit"].map(_normalise_unit)
    matched = matched.loc[matched["unit_token"].isin(UNIT_TO_UG_M3)].copy()
    if matched.empty:
        return None
    matched["normalised_median"] = matched.apply(
        lambda row: float(row["median_value"]) * UNIT_TO_UG_M3[row["unit_token"]],
        axis=1,
    )
    return float(matched["normalised_median"].median())


def latest_pollutant_summary(
    air: pd.DataFrame,
    pollutant: str,
    now: pd.Timestamp | None = None,
    max_age_hours: int = 48,
) -> dict:
    """Return a pollutant median from one latest fresh report per fixed station."""
    empty = {"value": None, "station_count": 0, "latest_utc": None, "age_hours": None}
    required = {"parameter", "unit", "value", "datetime_utc"}
    if air.empty or not required.issubset(air.columns):
        return empty

    frame = air.copy()
    frame["parameter_token"] = frame["parameter"].map(_normalise_parameter)
    frame = frame.loc[frame["parameter_token"].isin({pollutant, pollutant + "mass"})].copy()
    frame["unit_token"] = frame["unit"].map(_normalise_unit)
    frame = frame.loc[frame["unit_token"].isin(UNIT_TO_UG_M3)].copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["value", "datetime_utc"])
    if frame.empty:
        return empty

    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    frame = frame.loc[
        (frame["datetime_utc"] >= now - pd.Timedelta(hours=max_age_hours))
        & (frame["datetime_utc"] <= now + pd.Timedelta(minutes=15))
    ].copy()
    if frame.empty:
        return empty

    frame["value_ug_m3"] = frame.apply(
        lambda row: float(row["value"]) * UNIT_TO_UG_M3[row["unit_token"]],
        axis=1,
    )
    station_key = "location_id" if "location_id" in frame.columns else "station"
    if station_key not in frame.columns:
        frame["_station"] = frame.index.astype(str)
        station_key = "_station"
    if "is_mobile" in frame.columns:
        frame = frame.loc[~frame["is_mobile"].fillna(False).astype(bool)].copy()
    if frame.empty:
        return empty

    frame = frame.sort_values("datetime_utc").drop_duplicates(subset=[station_key], keep="last")
    latest = frame["datetime_utc"].max()
    return {
        "value": float(frame["value_ug_m3"].median()),
        "station_count": int(frame[station_key].nunique()),
        "latest_utc": latest,
        "age_hours": max(0.0, (now - latest).total_seconds() / 3600.0),
    }


def build_city_comparison_record(
    city_name: str,
    current_weather: dict,
    air: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> dict:
    """Build a comparable row using fresh pollutant data and explicit coverage."""
    summary = summarize_air_quality(air, now=now)
    pm25 = latest_pollutant_summary(air, "pm25", now=now)
    pm10 = latest_pollutant_summary(air, "pm10", now=now)
    stress = calculate_urban_stress(current_weather, air, now=now) if current_weather else {"index": None}
    if not air.empty and "location_id" in air.columns:
        stations = int(air["location_id"].nunique())
    elif not air.empty and "station" in air.columns:
        stations = int(air["station"].nunique())
    else:
        stations = 0

    return {
        "City": city_name,
        "Weather observation time": current_weather.get("time"),
        "Temperature (°C)": current_weather.get("temperature_2m"),
        "Feels like (°C)": current_weather.get("apparent_temperature"),
        "Humidity (%)": current_weather.get("relative_humidity_2m"),
        "Rainfall (mm)": current_weather.get("precipitation"),
        "PM2.5 (µg/m³)": pm25["value"],
        "PM2.5 stations": pm25["station_count"],
        "PM2.5 latest UTC": pm25["latest_utc"],
        "PM10 (µg/m³)": pm10["value"],
        "PM10 stations": pm10["station_count"],
        "PM10 latest UTC": pm10["latest_utc"],
        "Latest air observation (UTC)": summary["latest_utc"].max() if not summary.empty else None,
        "Air reading age (h)": float(summary["age_hours"].min()) if not summary.empty else None,
        "CityPulse Index": stress.get("index"),
        "Monitoring stations": stations,
    }
