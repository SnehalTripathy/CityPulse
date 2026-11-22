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



def test_index_normalises_mg_units_and_excludes_mobile_stale_and_future_rows():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([
        {"parameter":"pm25","unit":"mg/m³","value":0.020,"datetime_utc":"2026-11-22T17:00:00Z","location_id":1,"is_mobile":False},
        {"parameter":"PM₂.₅","unit":"µg/m³","value":30,"datetime_utc":"2026-11-22T16:00:00Z","location_id":2,"is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":900,"datetime_utc":"2026-11-20T00:00:00Z","location_id":3,"is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":1000,"datetime_utc":"2026-11-22T17:30:00Z","location_id":4,"is_mobile":True},
        {"parameter":"pm25","unit":"µg/m³","value":2000,"datetime_utc":"2026-11-23T05:00:00Z","location_id":5,"is_mobile":False},
    ])
    result = calculate_urban_stress(
        {"apparent_temperature":30,"precipitation":0},
        air,
        now=now,
    )
    # Fixed stations contribute 20 and 30 µg/m³; their median is 25.
    assert result["pm25_median"] == 25
    assert result["air_score"] == round(25 / 60 * 100, 1)


def test_index_does_not_use_mobile_station_values():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([{
        "parameter":"pm25","unit":"µg/m³","value":80,
        "datetime_utc":"2026-11-22T17:00:00Z","location_id":1,"is_mobile":"True",
    }])
    result = calculate_urban_stress(
        {"apparent_temperature":30,"precipitation":0}, air, now=now
    )
    assert result["index"] is None
    assert result["air_score"] is None



def test_index_withholds_composite_when_rainfall_is_missing():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([{
        "parameter":"pm25","unit":"µg/m³","value":20,
        "datetime_utc":"2026-11-22T17:00:00Z","location_id":1,"is_mobile":False,
    }])
    result = calculate_urban_stress(
        {"apparent_temperature":30,"precipitation":None},
        air,
        now=now,
    )
    assert result["index"] is None
    assert result["rain_score"] is None
    assert "Rainfall input is unavailable" in result["reason"]
