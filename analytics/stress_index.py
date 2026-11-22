from __future__ import annotations

import pandas as pd

def add_weather_stress(frame: pd.DataFrame) -> pd.DataFrame:
    """Add a transparent weather-only heuristic (0-100); not a validated city index."""
    result = frame.copy()
    heat = ((result["apparent_temperature"].clip(lower=20, upper=45) - 20) / 25).clip(0, 1)
    humidity = (result["relative_humidity_2m"].clip(0, 100) / 100).clip(0, 1)
    rain = (result["precipitation"].clip(0, 20) / 20).clip(0, 1)
    result["weather_stress"] = (100 * (0.65 * heat + 0.20 * humidity + 0.15 * rain)).round(1)
    return result
