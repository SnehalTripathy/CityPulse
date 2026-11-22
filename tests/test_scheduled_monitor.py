import pandas as pd

from analytics.scheduled_monitor import (
    deliver_scheduled_alert_batch,
    evaluate_scheduled_city,
    scheduled_email_enabled,
    scheduled_thresholds,
)


def _weather():
    frame = pd.DataFrame({
        "time": pd.to_datetime(["2026-11-22T13:00", "2026-11-22T14:00"]),
        "apparent_temperature": [41.0, 42.0],
        "precipitation": [0.0, 0.0],
    })
    frame.attrs["current"] = {
        "time": "2026-11-22T12:00",
        "apparent_temperature": 41.0,
        "precipitation": 0.0,
    }
    return frame


def test_scheduled_monitor_persists_new_city_alerts_and_deduplicates(tmp_path):
    db = tmp_path / "scheduled.sqlite3"
    first = evaluate_scheduled_city(
        "Bengaluru",
        _weather(),
        pd.DataFrame(),
        state_path=db,
        thresholds={"heat_c": 40, "rainfall_mm": 20, "pm25_ug_m3": 60, "pm10_ug_m3": 100},
        email_enabled=False,
        now=pd.Timestamp("2026-11-22T12:00:00Z"),
    )
    second = evaluate_scheduled_city(
        "Bengaluru",
        _weather(),
        pd.DataFrame(),
        state_path=db,
        thresholds={"heat_c": 40, "rainfall_mm": 20, "pm25_ug_m3": 60, "pm10_ug_m3": 100},
        email_enabled=False,
        now=pd.Timestamp("2026-11-22T12:00:00Z"),
    )

    assert first["alerts_found"] >= 1
    assert first["new_alerts"] >= 1
    assert first["new_events"][0]["city"] == "Bengaluru"
    assert second["new_alerts"] == 0
    assert second["new_events"] == []


def test_scheduled_email_is_off_by_default_and_one_batch_is_sent(monkeypatch, tmp_path):
    monkeypatch.delenv("CITYPULSE_SCHEDULED_EMAIL_ENABLED", raising=False)
    assert scheduled_email_enabled() is False
    assert deliver_scheduled_alert_batch([], state_path=tmp_path / "state.sqlite3") == "not_enabled"

    sent = {}
    monkeypatch.setattr("analytics.scheduled_monitor.email_delivery_configured", lambda: True)
    monkeypatch.setattr(
        "analytics.scheduled_monitor.send_alert_email",
        lambda city, events: sent.update(city=city, events=events) or (True, None),
    )
    marked = []
    monkeypatch.setattr(
        "analytics.scheduled_monitor.mark_notification",
        lambda fingerprint, status, error, path=None: marked.append((fingerprint, status)),
    )

    events = [{"fingerprint":"one","city":"Bengaluru"},{"fingerprint":"two","city":"Delhi"}]
    assert deliver_scheduled_alert_batch(
        events, state_path=tmp_path / "state.sqlite3", email_enabled=True
    ) == "sent"
    assert sent["city"] == "scheduled city monitoring"
    assert len(sent["events"]) == 2
    assert marked == [("one", "sent"), ("two", "sent")]


def test_scheduled_threshold_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("CITYPULSE_ALERT_HEAT_C", "43.5")
    monkeypatch.setenv("CITYPULSE_ALERT_PM25_UG_M3", "75")
    values = scheduled_thresholds()
    assert values["heat_c"] == 43.5
    assert values["pm25_ug_m3"] == 75
    assert values["rainfall_mm"] == 20


def test_scheduled_thresholds_reject_malformed_environment_values(monkeypatch):
    monkeypatch.setenv("CITYPULSE_ALERT_HEAT_C", "very hot")
    import pytest

    with pytest.raises(ValueError):
        scheduled_thresholds()
