import pandas as pd

from ingestion.snapshot import append_snapshot


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
