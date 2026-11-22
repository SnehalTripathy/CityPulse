import pandas as pd

from ingestion.openaq_api import fetch_latest_measurements


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_missing_key_returns_empty_frame():
    result = fetch_latest_measurements(12.9716, 77.5946, None)
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_fetches_latest_sensor_values(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/locations"):
            return FakeResponse({"results": [{
                "id": 101,
                "name": "Bengaluru Central",
                "locality": "Bengaluru",
                "coordinates": {"latitude": 12.97, "longitude": 77.59},
                "distance": 1200,
                "sensors": [{
                    "id": 501,
                    "parameter": {"name": "pm25", "units": "µg/m³"},
                }],
            }]})
        if url.endswith("/locations/101/latest"):
            return FakeResponse({"results": [{
                "sensorsId": 501,
                "locationsId": 101,
                "value": 28.5,
                "datetime": {
                    "utc": "2026-11-22T10:00:00Z",
                    "local": "2026-11-22T15:30:00+05:30",
                },
            }]})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("ingestion.openaq_api.requests.get", fake_get)
    result = fetch_latest_measurements(12.9716, 77.5946, "test-key")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["station"] == "Bengaluru Central"
    assert row["parameter"] == "pm25"
    assert row["value"] == 28.5
    assert row["sensor_id"] == 501
    assert row["datetime_local"] == "2026-11-22T15:30:00+05:30"
