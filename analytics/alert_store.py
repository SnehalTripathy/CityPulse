from __future__ import annotations

import hashlib
import json
import os
import smtplib
import sqlite3
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_PREFERENCES = {
    "heat_c": 40.0,
    "rainfall_mm": 20.0,
    "pm25_ug_m3": 60.0,
    "pm10_ug_m3": 100.0,
    "email_enabled": False,
}


def _db_path(path: str | Path | None = None) -> Path:
    return Path(path or os.getenv("CITYPULSE_STATE_DB", "data/processed/citypulse_state.sqlite3"))


def _connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = _db_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS city_preferences (
            city TEXT PRIMARY KEY,
            preferences_json TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            signal TEXT NOT NULL,
            trigger_basis TEXT,
            value REAL,
            threshold REAL,
            event_time TEXT,
            source TEXT,
            stations TEXT,
            status TEXT,
            recorded_at_utc TEXT NOT NULL,
            notification_status TEXT NOT NULL DEFAULT 'not_requested',
            notification_error TEXT,
            UNIQUE(city, fingerprint)
        )
    """)
    connection.commit()
    return connection


def load_city_preferences(city: str, path: str | Path | None = None) -> dict:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT preferences_json FROM city_preferences WHERE city=?", (city,)
        ).fetchone()
    if not row:
        return DEFAULT_PREFERENCES.copy()
    try:
        saved = json.loads(row["preferences_json"])
    except (TypeError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULT_PREFERENCES, **saved}


def save_city_preferences(city: str, preferences: dict, path: str | Path | None = None) -> dict:
    allowed = set(DEFAULT_PREFERENCES)
    cleaned = {key: value for key, value in preferences.items() if key in allowed}
    merged = {**DEFAULT_PREFERENCES, **cleaned}
    for key in ("heat_c", "rainfall_mm", "pm25_ug_m3", "pm10_ug_m3"):
        value = float(merged[key])
        if not pd.notna(value) or value < 0:
            raise ValueError(f"Invalid alert threshold: {key}")
        merged[key] = value
    merged["email_enabled"] = bool(merged["email_enabled"])
    with _connect(path) as connection:
        connection.execute(
            """INSERT INTO city_preferences(city, preferences_json, updated_at_utc)
               VALUES(?,?,?) ON CONFLICT(city) DO UPDATE SET
               preferences_json=excluded.preferences_json, updated_at_utc=excluded.updated_at_utc""",
            (city, json.dumps(merged, sort_keys=True), pd.Timestamp.now(tz="UTC").isoformat()),
        )
    return merged


def _fingerprint(city: str, row: dict[str, Any]) -> str:
    payload = {
        "city": city,
        "signal": str(row.get("Signal", "")),
        "basis": str(row.get("Trigger basis", "")),
        "time": str(row.get("Time", "")),
        "value": float(row.get("Value", 0)),
        "threshold": float(row.get("Configured threshold", 0)),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def record_alerts(city: str, alerts: pd.DataFrame, path: str | Path | None = None) -> list[dict]:
    """Persist newly observed alert signatures; repeated refreshes do not duplicate them."""
    if alerts is None or alerts.empty:
        return []
    inserted = []
    now = pd.Timestamp.now(tz="UTC").isoformat()
    with _connect(path) as connection:
        for row in alerts.to_dict(orient="records"):
            fingerprint = _fingerprint(city, row)
            cursor = connection.execute(
                """INSERT OR IGNORE INTO alert_history
                (city,fingerprint,signal,trigger_basis,value,threshold,event_time,source,stations,status,recorded_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    city, fingerprint, str(row.get("Signal", "")),
                    str(row.get("Trigger basis", "")), float(row.get("Value", 0)),
                    float(row.get("Configured threshold", 0)), str(row.get("Time", "")),
                    str(row.get("Source and data type", "")), str(row.get("Stations", "")),
                    str(row.get("Status", "")), now,
                ),
            )
            if cursor.rowcount:
                inserted.append({"city": city, **row, "fingerprint": fingerprint})
    return inserted


def list_alert_history(city: str, limit: int = 250, path: str | Path | None = None) -> pd.DataFrame:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT signal AS Signal, trigger_basis AS 'Trigger basis', value AS Value,
            threshold AS 'Configured threshold', event_time AS Time, source AS 'Source and data type',
            stations AS Stations, status AS Status, recorded_at_utc AS 'Recorded at (UTC)',
            notification_status AS 'Notification status', notification_error AS 'Notification error'
            FROM alert_history WHERE city=? ORDER BY id DESC LIMIT ?""",
            (city, max(1, min(int(limit), 2000))),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def clear_alert_history(city: str, path: str | Path | None = None) -> int:
    with _connect(path) as connection:
        cursor = connection.execute("DELETE FROM alert_history WHERE city=?", (city,))
        return int(cursor.rowcount)


def mark_notification(fingerprint: str, status: str, error: str | None = None, path: str | Path | None = None) -> None:
    with _connect(path) as connection:
        connection.execute(
            "UPDATE alert_history SET notification_status=?, notification_error=? WHERE fingerprint=?",
            (status, error[:500] if error else None, fingerprint),
        )


def email_delivery_configured() -> bool:
    required = ("CITYPULSE_SMTP_HOST", "CITYPULSE_SMTP_PORT", "CITYPULSE_SMTP_FROM", "CITYPULSE_ALERT_EMAIL")
    return all(os.getenv(name) for name in required)


def send_alert_email(city: str, alerts: list[dict]) -> tuple[bool, str | None]:
    """Send new alerts to the deployment owner's configured address; never stores recipient data."""
    if not alerts:
        return True, None
    if not email_delivery_configured():
        return False, "Email delivery is not configured by the deployment administrator."
    message = EmailMessage()
    message["Subject"] = f"CityPulse alert update — {city} ({len(alerts)} trigger(s))"
    message["From"] = os.environ["CITYPULSE_SMTP_FROM"]
    message["To"] = os.environ["CITYPULSE_ALERT_EMAIL"]
    lines = [f"New CityPulse threshold trigger(s) for {city}:", ""]
    for alert in alerts:
        lines.extend([
            f"{alert.get('Signal')}: {alert.get('Value')} (threshold {alert.get('Configured threshold')})",
            f"Basis: {alert.get('Trigger basis')}",
            f"Time: {alert.get('Time')}",
            f"Source: {alert.get('Source and data type')}",
            "",
        ])
    lines.append("These are configurable prototype triggers, not official warnings or health advice.")
    message.set_content("\n".join(lines))
    host = os.environ["CITYPULSE_SMTP_HOST"]
    port = int(os.environ["CITYPULSE_SMTP_PORT"])
    username = os.getenv("CITYPULSE_SMTP_USERNAME")
    password = os.getenv("CITYPULSE_SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if username:
                server.login(username, password or "")
            server.send_message(message)
        return True, None
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
