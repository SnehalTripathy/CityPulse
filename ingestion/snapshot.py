from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config.cities import CITIES
from ingestion.openaq_api import fetch_latest_measurements
from ingestion.weather_api import fetch_forecast

logger = logging.getLogger(__name__)

WEATHER_PARAMETERS = {
    "temperature_2m": "°C",
    "apparent_temperature": "°C",
    "relative_humidity_2m": "%",
    "precipitation": "mm",
    "wind_speed_10m": "km/h",
}
COLUMNS = [
    "source", "city", "station", "sensor_id", "parameter", "value", "unit",
    "datetime_utc", "observed_at_utc", "latitude", "longitude",
]


def _local_timestamp_to_utc(value: str | None, timezone_name: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(ZoneInfo(timezone_name))
    return stamp.tz_convert("UTC").isoformat()


def collect_snapshot(api_key: str | None = None) -> pd.DataFrame:
    """Collect one normalized snapshot of weather and nearby air sensor readings."""
    observed_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    for city_name, city in CITIES.items():
        weather = fetch_forecast(city["latitude"], city["longitude"], city["timezone"])
        current = weather.attrs.get("current", {}) or {}
        weather_time = _local_timestamp_to_utc(current.get("time"), city["timezone"])
        for parameter, unit in WEATHER_PARAMETERS.items():
            value = current.get(parameter)
            if value is None:
                continue
            rows.append({
                "source": "open-meteo",
                "city": city_name,
                "station": f"{city_name} model grid",
                "sensor_id": "open-meteo-current",
                "parameter": parameter,
                "value": value,
                "unit": unit,
                "datetime_utc": weather_time,
                "observed_at_utc": observed_at,
                "latitude": city["latitude"],
                "longitude": city["longitude"],
            })

        if api_key:
            try:
                air = fetch_latest_measurements(city["latitude"], city["longitude"], api_key)
            except Exception as exc:
                logger.warning("OpenAQ snapshot failed for %s; retaining weather rows: %s", city_name, exc)
                air = pd.DataFrame()
            for measurement in air.to_dict(orient="records"):
                stamp = measurement.get("datetime_utc")
                if stamp is not None and not pd.isna(stamp):
                    timestamp_utc = pd.Timestamp(stamp)
                    if timestamp_utc.tzinfo is None:
                        timestamp_utc = timestamp_utc.tz_localize("UTC")
                    timestamp_utc = timestamp_utc.tz_convert("UTC").isoformat()
                else:
                    timestamp_utc = ""
                rows.append({
                    "source": "openaq",
                    "city": city_name,
                    "station": measurement.get("station"),
                    "sensor_id": measurement.get("sensor_id"),
                    "parameter": measurement.get("parameter"),
                    "value": measurement.get("value"),
                    "unit": measurement.get("unit"),
                    "datetime_utc": timestamp_utc,
                    "observed_at_utc": observed_at,
                    "latitude": measurement.get("latitude"),
                    "longitude": measurement.get("longitude"),
                })

    return pd.DataFrame(rows, columns=COLUMNS)


def append_snapshot(snapshot: pd.DataFrame, path: str | Path) -> int:
    """Append normalized rows, de-duplicate provider timestamps, and cap file size."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = pd.read_csv(destination)
        combined = pd.concat([existing, snapshot], ignore_index=True)
    else:
        combined = snapshot.copy()

    if combined.empty:
        return 0

    combined = combined.drop_duplicates(
        subset=["source", "station", "sensor_id", "parameter", "datetime_utc"],
        keep="last",
    )
    combined = combined.sort_values(["datetime_utc", "source", "station"], na_position="last")
    combined = combined.tail(300_000)
    combined.to_csv(destination, index=False)
    return len(combined)


def main() -> None:
    import os

    api_key = os.getenv("OPENAQ_API_KEY")
    snapshot = collect_snapshot(api_key)
    destination = Path("data/raw/observations.csv")
    total = append_snapshot(snapshot, destination)
    print(f"Collected {len(snapshot)} rows; {total} unique observations stored at {destination}")


if __name__ == "__main__":
    main()
