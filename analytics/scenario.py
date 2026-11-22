from __future__ import annotations

import pandas as pd


def build_scenario_weather(
    current_weather: dict,
    apparent_temperature_delta: float,
    rainfall_multiplier: float,
) -> tuple[dict | None, str | None]:
    """Apply user-selected scenario deltas without inventing missing weather inputs."""
    if not current_weather:
        return None, "Current weather inputs are unavailable."

    apparent = pd.to_numeric(current_weather.get("apparent_temperature"), errors="coerce")
    rainfall = pd.to_numeric(current_weather.get("precipitation"), errors="coerce")
    if pd.isna(apparent):
        return None, "Current apparent temperature is missing."
    if pd.isna(rainfall):
        return None, "Current rainfall is missing."
    if float(rainfall) < 0:
        return None, "Current rainfall is outside the plausible non-negative range."

    result = dict(current_weather)
    result["apparent_temperature"] = float(apparent) + float(apparent_temperature_delta)
    result["precipitation"] = float(rainfall) * float(rainfall_multiplier)
    return result, None
