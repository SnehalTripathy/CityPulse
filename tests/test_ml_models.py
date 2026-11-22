import numpy as np
import pandas as pd

from ml.anomaly import detect_recent_weather_anomaly
from ml.forecasting import train_next_observation_model


def synthetic_observations(rows=115):
    times = pd.date_range("2026-01-01", periods=rows, freq="3h", tz="UTC")
    records = []
    for index, stamp in enumerate(times):
        temperature = 28 + 4 * np.sin(index / 18) + 0.1 * np.sin(index)
        values = {
            "temperature_2m": temperature - 1,
            "apparent_temperature": temperature,
            "relative_humidity_2m": 55 + 8 * np.sin(index / 12),
            "precipitation": 0.2 + 0.1 * np.cos(index / 8),
            "wind_speed_10m": 10 + 2 * np.sin(index / 9),
        }
        for parameter, value in values.items():
            records.append({
                "source": "open-meteo",
                "parameter": parameter,
                "value": value,
                "datetime_utc": stamp,
            })
    return pd.DataFrame(records)


def test_forecast_waits_for_enough_data():
    result = train_next_observation_model(synthetic_observations(20))
    assert result["status"] == "insufficient_data"


def test_forecast_returns_time_holdout_metrics():
    result = train_next_observation_model(synthetic_observations())
    assert result["status"] == "ready"
    assert result["samples"] >= 80
    assert result["mae"] >= 0
    assert result["prediction"] > 0


def test_anomaly_detection_uses_history():
    result = detect_recent_weather_anomaly(synthetic_observations(45))
    assert result["status"] == "ready"
    assert result["samples"] >= 30
