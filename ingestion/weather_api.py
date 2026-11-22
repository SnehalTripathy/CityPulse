from __future__ import annotations

import requests
import pandas as pd

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

def fetch_forecast(latitude: float, longitude: float) -> pd.DataFrame:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m",
        "forecast_days": 7,
        "timezone": "Asia/Kolkata",
    }
    response = requests.get(WEATHER_URL, params=params, timeout=25)
    response.raise_for_status()
    payload = response.json()
    hourly = payload.get("hourly", {})
    frame = pd.DataFrame(hourly)
    if not frame.empty and "time" in frame:
        frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    current = payload.get("current", {})
    if current and not frame.empty:
        # Attach current API values as metadata; hourly series remains the forecast timeline.
        frame.attrs["current"] = current
    frame.attrs["timezone"] = payload.get("timezone", "unknown")
    frame.attrs["model"] = payload.get("generationtime_ms")
    return frame
