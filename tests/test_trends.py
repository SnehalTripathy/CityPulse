import pandas as pd

from analytics.trends import build_city_trend_frame


def test_city_trends_use_shared_utc_days_and_only_comparable_units():
    rows = [
        {"city": "A", "source": "openaq", "station": "A1", "parameter": "pm2.5", "value": 10, "unit": "µg/m³", "datetime_utc": "2026-11-21T08:00:00Z"},
        {"city": "A", "source": "openaq", "station": "A2", "parameter": "pm25", "value": 20, "unit": "µg/m³", "datetime_utc": "2026-11-21T09:00:00Z"},
        {"city": "B", "source": "openaq", "station": "B1", "parameter": "pm25", "value": 30, "unit": "ug/m3", "datetime_utc": "2026-11-21T08:00:00Z"},
        {"city": "B", "source": "openaq", "station": "B2", "parameter": "pm25", "value": 999, "unit": "ppm", "datetime_utc": "2026-11-21T09:00:00Z"},
        {"city": "A", "source": "openaq", "station": "A1", "parameter": "pm25", "value": 50, "unit": "µg/m³", "datetime_utc": "2026-11-22T08:00:00Z"},
    ]
    frame, coverage = build_city_trend_frame(
        pd.DataFrame(rows),
        ["A", "B"],
        "PM2.5 (µg/m³)",
        days=7,
        now=pd.Timestamp("2026-11-22T12:00:00Z"),
    )

    a_day_1 = frame.loc[(frame["city"] == "A") & (frame["date"] == pd.Timestamp("2026-11-21T00:00:00Z"))].iloc[0]
    b_day_1 = frame.loc[(frame["city"] == "B") & (frame["date"] == pd.Timestamp("2026-11-21T00:00:00Z"))].iloc[0]
    assert a_day_1["value"] == 15
    assert a_day_1["station_count"] == 2
    assert b_day_1["value"] == 30
    assert coverage.set_index("City").loc["A", "Days with data"] == 2


def test_city_trends_return_empty_for_missing_history():
    trend, coverage = build_city_trend_frame(
        pd.DataFrame(), ["A", "B"], "Temperature (°C)", now=pd.Timestamp("2026-11-22T12:00:00Z")
    )
    assert trend.empty
    assert coverage.empty
