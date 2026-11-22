import pandas as pd

from ingestion import snapshot
from ingestion.snapshot import append_snapshot, build_daily_observation_summary, collect_snapshot


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
    assert len(result) == 5 * len(snapshot.CITIES)
    assert set(result["source"]) == {"open-meteo"}
    assert set(result["city"]) == set(snapshot.CITIES)


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



def test_daily_summary_compacts_station_values_by_utc_day_and_provenance():
    raw = pd.DataFrame([
        {"source":"openaq","city":"Bengaluru","station":"Station A","parameter":"pm25","value":10,"unit":"µg/m³","datetime_utc":"2026-11-22T10:00:00Z","latitude":12.97,"longitude":77.59,"is_mobile":False,"provider":"Provider X"},
        {"source":"openaq","city":"Bengaluru","station":"Station A","parameter":"pm25","value":20,"unit":"µg/m³","datetime_utc":"2026-11-22T11:00:00Z","latitude":12.97,"longitude":77.59,"is_mobile":False,"provider":"Provider X"},
        {"source":"openaq","city":"Bengaluru","station":"Station B","parameter":"pm25","value":30,"unit":"µg/m³","datetime_utc":"2026-11-22T11:00:00Z","latitude":12.98,"longitude":77.60,"is_mobile":True,"provider":"Provider Y"},
    ])
    result = build_daily_observation_summary(raw)
    assert len(result) == 2
    station_a = result.loc[result["station"] == "Station A"].iloc[0]
    assert station_a["median_value"] == 15
    assert station_a["reading_count"] == 2
    assert station_a["provider"] == "Provider X"
    assert station_a["date"] == pd.Timestamp("2026-11-22T00:00:00Z")


def test_weather_collection_continues_when_one_city_fails(monkeypatch):
    cities = {
        "Good City": {"latitude": 1.0, "longitude": 1.0, "timezone": "UTC"},
        "Bad City": {"latitude": 2.0, "longitude": 2.0, "timezone": "UTC"},
    }
    monkeypatch.setattr(snapshot, "CITIES", cities)

    weather = pd.DataFrame({"time":["2026-11-22T18:00"]})
    weather.attrs["current"] = {
        "time":"2026-11-22T18:00",
        "temperature_2m":25,
        "apparent_temperature":25,
        "relative_humidity_2m":50,
        "precipitation":0,
        "wind_speed_10m":5,
    }
    def fake_weather(lat, *_):
        if lat == 2.0:
            raise RuntimeError("temporary weather failure")
        return weather
    monkeypatch.setattr(snapshot, "fetch_forecast", fake_weather)
    result = collect_snapshot()
    assert set(result["city"]) == {"Good City"}
    assert len(result) == 5


def test_append_snapshot_creates_compact_daily_archive(tmp_path):
    path = tmp_path / "data" / "raw" / "observations.csv"
    data = pd.DataFrame([{
        "source":"open-meteo","city":"Bengaluru","station":"Bengaluru model grid",
        "sensor_id":"open-meteo-current","parameter":"temperature_2m","value":29.0,
        "unit":"°C","datetime_utc":"2026-11-22T10:00:00Z",
        "observed_at_utc":"2026-11-22T10:02:00Z","latitude":12.9716,"longitude":77.5946,
    }])
    append_snapshot(data, path)
    daily_path = tmp_path / "data" / "processed" / "daily_city_observations.csv"
    saved = pd.read_csv(daily_path)
    assert len(saved) == 1
    assert saved.iloc[0]["median_value"] == 29.0
