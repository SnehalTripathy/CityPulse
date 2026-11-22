from __future__ import annotations

import pandas as pd

from analytics.data_quality import summarize_air_quality
from analytics.urban_stress import calculate_urban_stress


def _normalise_parameter(value: object) -> str:
    return (
        str(value).lower().replace(".", "").replace("_", "").replace(" ", "")
        .replace("₂", "2")
    )


def _normalise_unit(value: object) -> str:
    return (
        str(value).lower().replace(" ", "").replace("μ", "µ")
        .replace("³", "3").replace("^", "")
    )


def pollutant_median(summary: pd.DataFrame, pollutant: str) -> float | None:
    """Return a comparable median only when concentration units are mass/volume."""
    if summary.empty:
        return None
    tokens = summary["parameter"].map(_normalise_parameter)
    matched = summary.loc[
        tokens.isin({pollutant, pollutant + "mass"})
    ].copy()
    allowed_units = {"µg/m3", "ug/m3"}
    matched = matched.loc[matched["unit"].map(_normalise_unit).isin(allowed_units)]
    if matched.empty:
        return None
    return float(matched["median_value"].median())


def build_city_comparison_record(
    city_name: str,
    current_weather: dict,
    air: pd.DataFrame,
) -> dict:
    """Build one comparison row while retaining missing values and timestamps."""
    summary = summarize_air_quality(air)
    stress = calculate_urban_stress(current_weather, air) if current_weather else {"index": None}
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
        "PM2.5 (µg/m³)": pollutant_median(summary, "pm25"),
        "PM10 (µg/m³)": pollutant_median(summary, "pm10"),
        "Latest air observation (UTC)": summary["latest_utc"].max() if not summary.empty else None,
        "Air reading age (h)": float(summary["age_hours"].min()) if not summary.empty else None,
        "CityPulse Index": stress.get("index"),
        "Monitoring stations": stations,
    }
