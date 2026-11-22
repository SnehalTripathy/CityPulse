import pandas as pd

from analytics.data_quality import summarize_air_quality


def test_air_quality_summary_reports_station_count_and_freshness():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([
        {"parameter": "pm25", "unit": "µg/m³", "value": 18, "datetime_utc": "2026-11-22T17:00:00Z", "location_id": 1},
        {"parameter": "pm25", "unit": "µg/m³", "value": 22, "datetime_utc": "2026-11-22T16:00:00Z", "location_id": 2},
        {"parameter": "no2", "unit": "µg/m³", "value": 12, "datetime_utc": "2026-11-20T00:00:00Z", "location_id": 3},
    ])

    result = summarize_air_quality(air, now=now)
    pm25 = result.loc[result["parameter"] == "pm25"].iloc[0]
    no2 = result.loc[result["parameter"] == "no2"].iloc[0]

    assert pm25["median_value"] == 20
    assert pm25["station_count"] == 2
    assert pm25["reading_count"] == 2
    assert pm25["freshness"] == "Fresh"
    assert no2["freshness"] == "Stale"


def test_air_quality_summary_returns_empty_schema_for_missing_data():
    result = summarize_air_quality(pd.DataFrame())
    assert result.empty
    assert "freshness" in result.columns
