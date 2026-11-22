import pandas as pd

from ingestion import snapshot
from ingestion.snapshot import append_snapshot, collect_snapshot


def test_collect_snapshot_keeps_weather_when_air_is_unavailable(monkeypatch):
    weather = pd.DataFrame({"time": ["2026-11-22T18:00"]})
    weather.attrs["current"] = {
        "time": "2026-11-22T18:00",
        "temperature_2m": 29.0,
        "apparent_temperature": 31.0,
        "relative_humidity_2m": 60,
        "precipitation": 0.0,
        "wind_speed_10m": 8.0,
    }
    monkeypatch.setattr(snapshot, "fetch_forecast", lambda *_: weather)

    def fail_air(*_):
        raise RuntimeError("temporary provider issue")

    monkeypatch.setattr(snapshot, "fetch_latest_measurements", fail_air)
    result = collect_snapshot("placeholder-key")
    assert len(result) == 5
    assert set(result["source"]) == {"open-meteo"}
    assert set(result["city"]) == {"Bengaluru"}


def test_append_snapshot_deduplicates_provider_records(tmp_path):
    path = tmp_path / "observations.csv"
    data = pd.DataFrame([
        {
            "source": "open-meteo",
            "city": "Bengaluru",
            "station": "Bengaluru model grid",
            "sensor_id": "open-meteo-current",
            "parameter": "temperature_2m",
            "value": 29.0,
            "unit": "°C",
            "datetime_utc": "2026-11-22T10:00:00+00:00",
            "observed_at_utc": "2026-11-22T10:02:00+00:00",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
    ])
    assert append_snapshot(data, path) == 1
    assert append_snapshot(data, path) == 1
    saved = pd.read_csv(path)
    assert len(saved) == 1
    assert saved.iloc[0]["value"] == 29.0
