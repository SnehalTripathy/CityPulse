from __future__ import annotations

import pandas as pd

WEATHER_FEATURES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
]


def weather_observations_to_wide(observations: pd.DataFrame) -> pd.DataFrame:
    required = {"source", "parameter", "value", "datetime_utc"}
    if observations.empty or not required.issubset(observations.columns):
        return pd.DataFrame()

    frame = observations[observations["source"] == "open-meteo"].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["datetime_utc", "value"])
    if frame.empty:
        return pd.DataFrame()

    wide = frame.pivot_table(
        index="datetime_utc",
        columns="parameter",
        values="value",
        aggfunc="mean",
    ).sort_index()
    for column in WEATHER_FEATURES:
        if column not in wide:
            wide[column] = float("nan")
    return wide[WEATHER_FEATURES].dropna(subset=["apparent_temperature"])
