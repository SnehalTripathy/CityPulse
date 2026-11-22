import pandas as pd

from analytics.urban_stress import calculate_urban_stress


def test_composite_uses_recent_pm_reading():
    now = pd.Timestamp.now(tz="UTC")
    air = pd.DataFrame([{
        "parameter": "pm25",
        "unit": "µg/m³",
        "value": 30.0,
        "datetime_utc": now,
        "location_id": 10,
        "station": "Central",
    }])
    result = calculate_urban_stress(
        {"apparent_temperature": 31.0, "precipitation": 2.0},
        air,
        now=now,
    )
    assert result["index"] is not None
    assert 0 <= result["index"] <= 100
    assert result["air_score"] == 50.0


def test_composite_is_not_claimed_when_air_is_missing():
    result = calculate_urban_stress(
        {"apparent_temperature": 31.0, "precipitation": 0.0},
        pd.DataFrame(),
    )
    assert result["index"] is None
    assert result["heat_score"] is not None
    assert "PM2.5 or PM10" in result["reason"]


def test_stale_sensor_reading_is_excluded():
    now = pd.Timestamp.now(tz="UTC")
    air = pd.DataFrame([{
        "parameter": "pm10",
        "unit": "µg/m³",
        "value": 90.0,
        "datetime_utc": now - pd.Timedelta(days=5),
        "location_id": 11,
        "station": "Old station",
    }])
    result = calculate_urban_stress(
        {"apparent_temperature": 28.0, "precipitation": 0.0},
        air,
        now=now,
    )
    assert result["index"] is None
