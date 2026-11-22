import pandas as pd

from analytics.comparison import build_city_comparison_record, pollutant_median
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
