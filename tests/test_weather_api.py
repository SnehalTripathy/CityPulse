import pandas as pd

from ingestion.weather_api import fetch_forecast


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetch_forecast_passes_requested_timezone(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse({
            "timezone": "America/Los_Angeles",
            "generationtime_ms": 1.0,
            "current": {"time": "2026-11-22T10:00", "temperature_2m": 18},
            "hourly": {"time": ["2026-11-22T10:00"], "temperature_2m": [18]},
        })

    monkeypatch.setattr("ingestion.weather_api.requests.get", fake_get)
    result = fetch_forecast(34.0522, -118.2437, "America/Los_Angeles")

    assert captured["params"]["timezone"] == "America/Los_Angeles"
    assert result.attrs["timezone"] == "America/Los_Angeles"
    assert result.attrs["current"]["time"] == "2026-11-22T10:00"
