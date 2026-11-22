import pandas as pd

from analytics.alerts import build_alert_assessment


def test_alerts_distinguish_current_modelled_conditions_from_forecast():
    current = {
        "time": "2026-11-22T10:00",
        "apparent_temperature": 41.0,
        "precipitation": 2.0,
    }
    forecast = pd.DataFrame({
        "time": pd.to_datetime(["2026-11-22T11:00", "2026-11-22T12:00", "2026-11-23T12:00"]),
        "apparent_temperature": [39.0, 42.0, 48.0],
        "precipitation": [1.0, 24.0, 80.0],
    })
    result = build_alert_assessment(
        current, forecast, pd.DataFrame(),
        {"heat_c": 40, "rainfall_mm": 20, "pm25_ug_m3": 60, "pm10_ug_m3": 100},
        now=pd.Timestamp("2026-11-22T10:00:00Z"),
    )
    alerts = result["alerts"]
    heat = alerts.loc[alerts["Signal"] == "Heat"]
    rain = alerts.loc[alerts["Signal"] == "Rainfall"]
    assert set(heat["Trigger basis"]) == {
        "Current apparent temperature",
        "Highest apparent temperature in next 24 hours",
    }
    assert set(rain["Trigger basis"]) == {"Highest hourly precipitation in next 24 hours"}
    assert result["forecast_hours_checked"] == 2
    assert all("Open-Meteo" in source for source in alerts["Source and data type"])


def test_alerts_use_fresh_fixed_station_medians_and_ignore_mobile_stale_and_future():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([
        {"parameter":"pm25","unit":"mg/m³","value":0.080,"datetime_utc":"2026-11-22T17:00:00Z","location_id":1,"station":"A","is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":50,"datetime_utc":"2026-11-22T16:00:00Z","location_id":2,"station":"B","is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":1000,"datetime_utc":"2026-11-22T17:00:00Z","location_id":3,"station":"Mobile","is_mobile":True},
        {"parameter":"pm10","unit":"µg/m³","value":500,"datetime_utc":"2026-11-20T00:00:00Z","location_id":4,"station":"Old","is_mobile":False},
        {"parameter":"pm10","unit":"µg/m³","value":900,"datetime_utc":"2026-11-23T00:00:00Z","location_id":5,"station":"Future","is_mobile":False},
    ])
    result = build_alert_assessment(
        {"time":"2026-11-22T18:00","apparent_temperature":20,"precipitation":0},
        pd.DataFrame(),
        air,
        {"heat_c":40,"rainfall_mm":20,"pm25_ug_m3":60,"pm10_ug_m3":100},
        now=now,
    )
    alerts = result["alerts"]
    pm25 = alerts.loc[alerts["Signal"] == "PM2.5"].iloc[0]
    assert pm25["Value"] == 65
    assert pm25["Stations"] == 2
    assert not (alerts["Signal"] == "PM10").any()


def test_alerts_do_not_fabricate_when_sources_are_missing():
    result = build_alert_assessment({}, pd.DataFrame(), pd.DataFrame(), now=pd.Timestamp("2026-11-22T18:00:00Z"))
    assert result["alerts"].empty
    assert result["recommendations"] == []
    assert result["unavailable"]


def test_subthreshold_values_do_not_trigger_alerts():
    result = build_alert_assessment(
        {"time":"2026-11-22T10:00","apparent_temperature":25,"precipitation":0},
        pd.DataFrame({
            "time":pd.to_datetime(["2026-11-22T11:00","2026-11-22T12:00"]),
            "apparent_temperature":[26,27],
            "precipitation":[0,1],
        }),
        pd.DataFrame(),
        now=pd.Timestamp("2026-11-22T10:00:00Z"),
    )
    assert result["alerts"].empty

 
def test_alert_assessment_rejects_invalid_thresholds():
    import pytest

    for invalid in (float("nan"), float("inf"), -1, "not-a-number"):
        with pytest.raises(ValueError):
            build_alert_assessment(
                {}, pd.DataFrame(), pd.DataFrame(),
                {"heat_c": invalid},
                now=pd.Timestamp("2026-11-22T18:00:00Z"),
            )
