from __future__ import annotations

from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest

from analytics.alert_store import load_city_preferences

from config.cities import COUNTRY_CITIES


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
WORKSPACE_PAGES = (
    "Command Center",
    "City Comparison",
    "Air Quality Intelligence",
    "Environmental Analytics",
    "Predictive Intelligence",
    "Anomaly Detection",
    "Zone Intelligence",
    "Environmental Health & Exposure",
    "Smart Alerts & Recommendations",
    "Data Quality & Confidence",
    "Scenario Simulator",
    "Methodology",
)


def _block_network_requests(self, method, url, *args, **kwargs):
    """Keep UI smoke tests deterministic and independent of provider uptime."""
    raise requests.ConnectionError(f"Network disabled during Streamlit UI smoke test: {url}")


def test_streamlit_workspace_pages_render_when_providers_are_unavailable(monkeypatch):
    """Exercise the real app entrypoint and every workspace route in offline mode."""
    monkeypatch.setattr(requests.sessions.Session, "request", _block_network_requests)

    app = AppTest.from_file(str(APP_PATH), default_timeout=45).run(timeout=90)
    assert not app.exception, [item.message for item in app.exception]

    # The first sidebar selectbox is Country and the second is City.
    assert len(app.selectbox) >= 2
    app.selectbox[0].set_value("United States").run(timeout=90)
    assert not app.exception, [item.message for item in app.exception]
    assert app.selectbox[1].value in COUNTRY_CITIES["United States"]

    for page in WORKSPACE_PAGES:
        # Reacquire the element after each script rerun; AppTest refreshes its tree.
        app.radio[0].set_value(page)
        app.run(timeout=90)
        assert not app.exception, (
            f"Workspace page {page!r} raised an uncaught exception: "
            f"{[item.message for item in app.exception]}"
        )
        assert app.radio[0].value == page


def test_smart_alert_thresholds_save_and_restore_per_city_offline(monkeypatch, tmp_path):
    """Exercise threshold controls and city-scoped preferences without provider access."""
    monkeypatch.setattr(requests.sessions.Session, "request", _block_network_requests)
    state_path = tmp_path / "citypulse_state.sqlite3"
    monkeypatch.setenv("CITYPULSE_STATE_DB", str(state_path))

    app = AppTest.from_file(str(APP_PATH), default_timeout=45).run(timeout=90)
    app.radio[0].set_value("Smart Alerts & Recommendations")
    app.run(timeout=90)
    assert not app.exception, [item.message for item in app.exception]
    assert len(app.slider) >= 4

    selected_values = (45.0, 25.0, 85.0, 150.0)
    for index, value in enumerate(selected_values):
        app.slider[index].set_value(value)
    save_button = next(button for button in app.button if button.label == "Save alert preferences")
    save_button.click()
    app.run(timeout=90)
    assert not app.exception, [item.message for item in app.exception]

    saved = load_city_preferences("Bengaluru", path=state_path)
    assert (
        saved["heat_c"],
        saved["rainfall_mm"],
        saved["pm25_ug_m3"],
        saved["pm10_ug_m3"],
    ) == selected_values

    # A different city starts from its own preferences, not Bengaluru's sliders.
    app.selectbox[1].set_value("Mumbai")
    app.run(timeout=90)
    assert not app.exception, [item.message for item in app.exception]
    assert app.slider[0].value == 40.0

    # Returning to Bengaluru restores its saved threshold.
    app.selectbox[1].set_value("Bengaluru")
    app.run(timeout=90)
    assert not app.exception, [item.message for item in app.exception]
    assert app.slider[0].value == 45.0
