from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from analytics.alerts import DEFAULT_ALERT_THRESHOLDS, build_alert_assessment
from analytics.alert_store import (
    email_delivery_configured,
    mark_notification,
    record_alerts,
    send_alert_email,
)

logger = logging.getLogger(__name__)

THRESHOLD_ENV = {
    "heat_c": "CITYPULSE_ALERT_HEAT_C",
    "rainfall_mm": "CITYPULSE_ALERT_RAINFALL_MM",
    "pm25_ug_m3": "CITYPULSE_ALERT_PM25_UG_M3",
    "pm10_ug_m3": "CITYPULSE_ALERT_PM10_UG_M3",
}


def scheduled_thresholds() -> dict:
    """Read deployment-wide monitoring thresholds, falling back to product defaults."""
    thresholds = DEFAULT_ALERT_THRESHOLDS.copy()
    for key, env_name in THRESHOLD_ENV.items():
        raw = os.getenv(env_name)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{env_name} must be numeric.") from None
        if not pd.notna(value) or value < 0 or value == float("inf") or value == float("-inf"):
            raise ValueError(f"{env_name} must be a finite, non-negative number.")
        thresholds[key] = value
    return thresholds


def scheduled_email_enabled() -> bool:
    return os.getenv("CITYPULSE_SCHEDULED_EMAIL_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def evaluate_scheduled_city(
    city: str,
    weather: pd.DataFrame,
    air: pd.DataFrame,
    *,
    state_path: str | Path | None = None,
    thresholds: dict | None = None,
    email_enabled: bool | None = None,
    now: pd.Timestamp | None = None,
) -> dict:
    """Evaluate one city snapshot, persist new triggers and optionally notify by SMTP."""
    current = weather.attrs.get("current", {}) if weather is not None and not weather.empty else {}
    assessment = build_alert_assessment(
        current,
        weather if weather is not None else pd.DataFrame(),
        air if air is not None else pd.DataFrame(),
        thresholds or scheduled_thresholds(),
        now=now,
    )
    newly_recorded = record_alerts(city, assessment["alerts"], path=state_path)
    return {
        "city": city,
        "alerts_found": int(len(assessment["alerts"])),
        "new_alerts": int(len(newly_recorded)),
        "new_events": newly_recorded,
        "unavailable": assessment["unavailable"],
    }


def deliver_scheduled_alert_batch(
    events: list[dict],
    *,
    state_path: str | Path | None = None,
    email_enabled: bool | None = None,
) -> str:
    """Send one consolidated email per monitoring run, avoiding per-city email bursts."""
    should_email = scheduled_email_enabled() if email_enabled is None else bool(email_enabled)
    if not events or not should_email:
        return "not_enabled"
    if not email_delivery_configured():
        error = "Scheduled email is enabled, but SMTP settings are incomplete or invalid."
        sent = False
    else:
        sent, error = send_alert_email("scheduled city monitoring", events)
    for event in events:
        mark_notification(
            event["fingerprint"],
            "sent" if sent else "failed",
            error,
            path=state_path,
        )
    return "sent" if sent else "failed"
