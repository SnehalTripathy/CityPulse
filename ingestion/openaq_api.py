from __future__ import annotations

import pandas as pd
import requests

OPENAQ_URL = "https://api.openaq.org/v3/locations"

def fetch_latest_measurements(latitude: float, longitude: float, api_key: str | None) -> pd.DataFrame:
    if not api_key:
        return pd.DataFrame()
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    params = {"coordinates": f"{latitude},{longitude}", "radius": 25000, "limit": 100, "order_by": "lastUpdated", "sort_order": "desc"}
    response = requests.get(OPENAQ_URL, headers=headers, params=params, timeout=25)
    if response.status_code == 429:
        raise RuntimeError("OpenAQ rate limit reached. Please retry later.")
    if response.status_code == 401:
        raise RuntimeError("OpenAQ rejected the API key. Check Streamlit Secrets.")
    response.raise_for_status()
    results = response.json().get("results", [])
    rows = []
    for location in results:
        for sensor in location.get("sensors", []):
            parameter = sensor.get("parameter", {})
            rows.append({
                "station": location.get("name"),
                "location_id": location.get("id"),
                "parameter": parameter.get("name"),
                "unit": parameter.get("units"),
                "sensor_id": sensor.get("id"),
                "latitude": (location.get("coordinates") or {}).get("latitude"),
                "longitude": (location.get("coordinates") or {}).get("longitude"),
                "last_updated": location.get("datetimeLast"),
            })
    return pd.DataFrame(rows)
