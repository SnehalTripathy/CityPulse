from __future__ import annotations

from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest

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

    workspace = app.radio[0]
    for page in WORKSPACE_PAGES:
        workspace.set_value(page)
        app.run(timeout=90)
        assert not app.exception, (
            f"Workspace page {page!r} raised an uncaught exception: "
            f"{[item.message for item in app.exception]}"
        )
        assert app.radio[0].value == page
