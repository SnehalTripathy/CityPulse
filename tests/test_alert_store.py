import pandas as pd
import pytest

from analytics.alert_store import (
    clear_alert_history,
    email_delivery_configured,
    list_alert_history,
    load_city_preferences,
    mark_notification,
    record_alerts,
    save_city_preferences,
    send_alert_email,
)


def _alerts():
    return pd.DataFrame([{
        "Signal": "Heat",
        "Trigger basis": "Current apparent temperature",
        "Value": 42.0,
        "Configured threshold": 40.0,
        "Time": "2026-11-22T12:00:00",
        "Source and data type": "Open-Meteo modelled grid-cell condition",
        "Stations": "—",
        "Status": "Threshold crossed",
    }])


def _smtp_config():
    return {
        "CITYPULSE_SMTP_HOST": "smtp.example.test",
        "CITYPULSE_SMTP_PORT": "587",
        "CITYPULSE_SMTP_FROM": "alerts@example.test",
        "CITYPULSE_ALERT_EMAIL": "admin@example.test",
        "CITYPULSE_SMTP_USERNAME": "citypulse",
        "CITYPULSE_SMTP_PASSWORD": "secret",
    }


def test_preferences_round_trip_and_city_isolation(tmp_path):
    db = tmp_path / "state.sqlite3"
    saved = save_city_preferences("Bengaluru", {"heat_c": 41, "email_enabled": True}, db)
    assert saved["heat_c"] == 41
    assert load_city_preferences("Bengaluru", db)["email_enabled"] is True
    assert load_city_preferences("Chennai", db)["heat_c"] == 40


def test_preferences_reject_invalid_and_out_of_range_thresholds(tmp_path):
    db = tmp_path / "state.sqlite3"
    with pytest.raises(ValueError):
        save_city_preferences("Bengaluru", {"heat_c": float("nan")}, db)
    with pytest.raises(ValueError):
        save_city_preferences("Bengaluru", {"pm25_ug_m3": 999}, db)
    saved = save_city_preferences("Bengaluru", {"email_enabled": "false"}, db)
    assert saved["email_enabled"] is False


def test_alert_history_is_durable_and_deduplicated(tmp_path):
    db = tmp_path / "state.sqlite3"
    alerts = _alerts()
    inserted = record_alerts("Bengaluru", alerts, db)
    assert len(inserted) == 1
    assert len(record_alerts("Bengaluru", alerts, db)) == 0
    history = list_alert_history("Bengaluru", path=db)
    assert len(history) == 1
    assert history.iloc[0]["Signal"] == "Heat"
    mark_notification(inserted[0]["fingerprint"], "failed", "SMTP unavailable", db)
    history = list_alert_history("Bengaluru", path=db)
    assert history.iloc[0]["Notification status"] == "failed"
    assert history.iloc[0]["Notification error"] == "SMTP unavailable"
    assert clear_alert_history("Bengaluru", db) == 1
    assert list_alert_history("Bengaluru", path=db).empty


def test_smtp_configuration_accepts_secrets_and_rejects_invalid_port_or_partial_auth(monkeypatch):
    for name in _smtp_config():
        monkeypatch.delenv(name, raising=False)
    assert email_delivery_configured(_smtp_config()) is True

    bad_port = _smtp_config()
    bad_port["CITYPULSE_SMTP_PORT"] = "not-a-port"
    assert email_delivery_configured(bad_port) is False

    partial_auth = _smtp_config()
    partial_auth.pop("CITYPULSE_SMTP_PASSWORD")
    assert email_delivery_configured(partial_auth) is False


def test_send_alert_email_uses_supplied_streamlit_secret_values(monkeypatch):
    for name in _smtp_config():
        monkeypatch.delenv(name, raising=False)
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["connection"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def ehlo(self):
            sent["ehlo"] = sent.get("ehlo", 0) + 1

        def starttls(self):
            sent["starttls"] = True

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr("analytics.alert_store.smtplib.SMTP", FakeSMTP)
    success, error = send_alert_email("Bengaluru", _alerts().to_dict("records"), _smtp_config())

    assert success is True
    assert error is None
    assert sent["connection"] == ("smtp.example.test", 587, 15)
    assert sent["starttls"] is True
    assert sent["login"] == ("citypulse", "secret")
    assert sent["message"]["To"] == "admin@example.test"
    assert "Heat" in sent["message"].get_content()


def test_send_email_reports_unconfigured_delivery_without_connecting(monkeypatch):
    names = list(_smtp_config())
    for name in names:
        monkeypatch.delenv(name, raising=False)
    success, error = send_alert_email("Bengaluru", _alerts().to_dict("records"), {})
    assert success is False
    assert "not configured" in error
