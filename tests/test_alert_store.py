import pandas as pd

from analytics.alert_store import (
    clear_alert_history, list_alert_history, load_city_preferences,
    record_alerts, save_city_preferences,
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


def test_preferences_round_trip_and_city_isolation(tmp_path):
    db = tmp_path / "state.sqlite3"
    saved = save_city_preferences("Bengaluru", {"heat_c": 41, "email_enabled": True}, db)
    assert saved["heat_c"] == 41
    assert load_city_preferences("Bengaluru", db)["email_enabled"] is True
    assert load_city_preferences("Chennai", db)["heat_c"] == 40


def test_alert_history_is_durable_and_deduplicated(tmp_path):
    db = tmp_path / "state.sqlite3"
    alerts = _alerts()
    assert len(record_alerts("Bengaluru", alerts, db)) == 1
    assert len(record_alerts("Bengaluru", alerts, db)) == 0
    history = list_alert_history("Bengaluru", path=db)
    assert len(history) == 1
    assert history.iloc[0]["Signal"] == "Heat"
    assert clear_alert_history("Bengaluru", db) == 1
    assert list_alert_history("Bengaluru", path=db).empty
