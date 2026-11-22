from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

BASE_URL = "https://api.openaq.org/v3"
REQUEST_TIMEOUT = (5, 25)
MAX_NEARBY_LOCATIONS = 12


def _get_json(url: str, api_key: str, params: dict | None = None) -> dict:
    response = requests.get(
        url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 401:
        raise RuntimeError("OpenAQ rejected the API key. Check Streamlit Secrets.")
    if response.status_code == 403:
        raise RuntimeError("OpenAQ access was forbidden. Check the API key and account access.")
    if response.status_code == 429:
        raise RuntimeError("OpenAQ rate limit reached. Please retry after a short pause.")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAQ returned an unexpected response format.")
    return payload


def _fetch_location_latest(location: dict, api_key: str) -> list[dict]:
    location_id = location.get("id")
    if location_id is None:
        return []

    payload = _get_json(
        f"{BASE_URL}/locations/{location_id}/latest",
        api_key,
        params={"limit": 100, "page": 1},
    )
    sensor_lookup = {
        sensor.get("id"): sensor
        for sensor in location.get("sensors", [])
        if sensor.get("id") is not None
    }
    coords = location.get("coordinates") or {}
    rows = []

    for measurement in payload.get("results", []):
        sensor = sensor_lookup.get(measurement.get("sensorsId"), {})
        parameter = sensor.get("parameter") or {}
        timestamp = measurement.get("datetime") or {}
        rows.append({
            "station": location.get("name") or "Unnamed station",
            "locality": location.get("locality"),
            "location_id": location_id,
            "sensor_id": measurement.get("sensorsId"),
            "parameter": parameter.get("name", "Unknown"),
            "unit": parameter.get("units"),
            "value": measurement.get("value"),
            "datetime_local": timestamp.get("local") if isinstance(timestamp, dict) else timestamp,
            "datetime_utc": timestamp.get("utc") if isinstance(timestamp, dict) else None,
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "distance_m": location.get("distance"),
        })
    return rows


def fetch_latest_measurements(
    latitude: float,
    longitude: float,
    api_key: str | None,
) -> pd.DataFrame:
    """Fetch latest sensor readings from nearby OpenAQ locations.

    Returns an empty frame when no key is configured or no stations/readings
    are available. It never fabricates readings for missing stations.
    """
    if not api_key:
        return pd.DataFrame()

    locations_payload = _get_json(
        f"{BASE_URL}/locations",
        api_key,
        params={
            "coordinates": f"{latitude:.4f},{longitude:.4f}",
            "radius": 25000,
            "limit": MAX_NEARBY_LOCATIONS,
            "page": 1,
        },
    )
    locations = locations_payload.get("results", [])
    if not locations:
        return pd.DataFrame()

    rows: list[dict] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_location_latest, location, api_key): location
            for location in locations
        }
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except requests.RequestException as exc:
                errors.append(str(exc))
            except RuntimeError as exc:
                errors.append(str(exc))

    if not rows and errors:
        raise RuntimeError(f"Unable to retrieve nearby OpenAQ readings: {errors[0]}")
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    if "datetime_utc" in frame:
        frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    return frame.sort_values(["parameter", "station"], na_position="last").reset_index(drop=True)
