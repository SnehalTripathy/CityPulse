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


def test_multi_horizon_weather_forecasts_report_holdout_and_baseline_metrics():
    from ml.forecasting import train_multi_horizon_weather_forecast

    result = train_multi_horizon_weather_forecast(synthetic_observations(300))
    assert result["status"] == "ready"
    assert set(result["horizons"]) == {"24", "48", "72"}
    for horizon in result["horizons"].values():
        assert "apparent_temperature" in horizon
        model = horizon["apparent_temperature"]
        assert model["status"] == "ready"
        assert model["training_samples"] >= 40
        assert model["holdout_samples"] >= 10
        assert model["mae"] >= 0
        assert model["persistence_mae"] >= 0
        assert model["validation"].startswith("chronological")


def test_pollutant_forecast_normalizes_units_and_excludes_mobile_stations():
    from ml.forecasting import train_pollutant_deterioration_forecast

    times = pd.date_range("2026-01-01", periods=320, freq="3h", tz="UTC")
    rows = []
    for index, stamp in enumerate(times):
        value = 22 + 8 * np.sin(index / 15) + 0.03 * index
        rows.append({
            "source": "openaq", "parameter": "pm25", "unit": "mg/m3",
            "value": value / 1000, "datetime_utc": stamp,
            "location_id": 1, "station": "Fixed", "is_mobile": False,
        })
        rows.append({
            "source": "openaq", "parameter": "pm25", "unit": "µg/m³",
            "value": value + 500, "datetime_utc": stamp,
            "location_id": 2, "station": "Mobile", "is_mobile": True,
        })
    result = train_pollutant_deterioration_forecast(pd.DataFrame(rows), "PM2.5")
    assert result["status"] == "ready"
    assert result["samples"] == 320
    assert set(result["horizons"]) == {"24", "48", "72"}
    assert result["horizons"]["24"]["status"] == "ready"


def test_pollutant_forecast_rejects_unsupported_or_empty_history():
    from ml.forecasting import train_pollutant_deterioration_forecast

    result = train_pollutant_deterioration_forecast(pd.DataFrame(), "PM10")
    assert result["status"] == "insufficient_data"
    assert result["horizons"] == {}
