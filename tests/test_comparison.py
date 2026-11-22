import pandas as pd

from analytics.comparison import build_city_comparison_record, latest_pollutant_summary, pollutant_median
from analytics.data_quality import summarize_air_quality


def test_pollutant_median_normalises_parameter_but_requires_comparable_units():
    air = pd.DataFrame([
        {"parameter": "pm2.5", "unit": "µg/m³", "value": 10, "datetime_utc": "2026-11-22T17:00:00Z", "location_id": 1},
        {"parameter": "pm25", "unit": "µg/m³", "value": 20, "datetime_utc": "2026-11-22T17:00:00Z", "location_id": 2},
        {"parameter": "pm25", "unit": "ppm", "value": 999, "datetime_utc": "2026-11-22T17:00:00Z", "location_id": 3},
    ])
    summary = summarize_air_quality(air, now=pd.Timestamp("2026-11-22T18:00:00Z"))

    assert pollutant_median(summary, "pm25") == 15


def test_comparison_record_keeps_missing_air_quality_blank():
    weather = {
        "time": "2026-11-22T18:00",
        "temperature_2m": 25.0,
        "apparent_temperature": 26.0,
        "relative_humidity_2m": 60,
        "precipitation": 0.0,
    }
    result = build_city_comparison_record("Test City", weather, pd.DataFrame())

    assert result["City"] == "Test City"
    assert result["Temperature (°C)"] == 25.0
    assert result["PM2.5 (µg/m³)"] is None
    assert result["PM10 (µg/m³)"] is None
    assert result["CityPulse Index"] is None
    assert result["Monitoring stations"] == 0


def test_comparison_uses_fresh_fixed_stations_and_normalises_mg_units():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([
        {"parameter": "pm2.5", "unit": "mg/m³", "value": 0.020, "datetime_utc": "2026-11-22T17:00:00Z", "location_id": 1, "is_mobile": False},
        {"parameter": "pm25", "unit": "µg/m³", "value": 30, "datetime_utc": "2026-11-22T16:00:00Z", "location_id": 2, "is_mobile": False},
        {"parameter": "pm25", "unit": "µg/m³", "value": 800, "datetime_utc": "2026-11-20T00:00:00Z", "location_id": 3, "is_mobile": False},
        {"parameter": "pm25", "unit": "µg/m³", "value": 900, "datetime_utc": "2026-11-22T17:30:00Z", "location_id": 4, "is_mobile": True},
    ])
    result = latest_pollutant_summary(air, "pm25", now=now)
    assert result["station_count"] == 2
    assert result["value"] == 25
    assert result["age_hours"] == 1



def test_city_comparison_reports_timezone_and_fixed_mobile_coverage():
    weather = {
        "time":"2026-11-22T18:00",
        "timezone":"Asia/Kolkata",
        "temperature_2m":28,
        "apparent_temperature":30,
        "relative_humidity_2m":55,
        "precipitation":0.0,
    }
    air = pd.DataFrame([
        {"parameter":"pm25","unit":"µg/m³","value":10,"datetime_utc":"2026-11-22T17:00:00Z","location_id":1,"is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":20,"datetime_utc":"2026-11-22T17:00:00Z","location_id":2,"is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":100,"datetime_utc":"2026-11-22T17:00:00Z","location_id":3,"is_mobile":True},
    ])
    result = build_city_comparison_record("Bengaluru", weather, air, now=pd.Timestamp("2026-11-22T18:00:00Z"))
    assert result["Weather time zone"] == "Asia/Kolkata"
    assert result["Fixed monitoring stations"] == 2
    assert result["Mobile sensors"] == 1
    assert result["PM2.5 (µg/m³)"] == 15
    assert result["PM2.5 stations"] == 2



def test_comparison_suppresses_future_only_air_freshness_timestamp():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([{
        "parameter":"pm25","unit":"µg/m³","value":80,
        "datetime_utc":"2026-11-23T05:00:00Z","location_id":1,
        "is_mobile":False,
    }])
    result = build_city_comparison_record(
        "Future City", {"time":"2026-11-22T18:00","timezone":"UTC"}, air, now=now
    )
    assert result["PM2.5 (µg/m³)"] is None
    assert result["PM2.5 stations"] == 0
    assert result["Latest air observation (UTC)"] is None
    assert pd.isna(result["Air reading age (h)"])
