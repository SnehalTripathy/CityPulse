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
    "source", "city", "station", "location_id", "sensor_id", "parameter", "value", "unit",
    "datetime_utc", "observed_at_utc", "latitude", "longitude",
    "is_mobile", "is_monitor", "timezone", "provider", "owner", "licenses",
]
DAILY_COLUMNS = [
    "source", "city", "station", "location_id", "parameter", "unit", "date", "median_value",
    "reading_count", "first_utc", "last_utc", "latitude", "longitude",
    "is_mobile", "is_monitor", "provider", "owner", "timezone", "licenses",
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
        try:
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
                    "location_id": None,
                    "sensor_id": "open-meteo-current",
                    "parameter": parameter,
                    "value": value,
                    "unit": unit,
                    "datetime_utc": weather_time,
                    "observed_at_utc": observed_at,
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "is_mobile": False,
                    "is_monitor": False,
                    "timezone": city["timezone"],
                    "provider": "Open-Meteo",
                    "owner": "Open-Meteo",
                    "licenses": "",
                })
        except Exception as exc:
            logger.warning("Open-Meteo snapshot failed for %s; continuing to remaining cities: %s", city_name, exc)

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
                    "location_id": measurement.get("location_id"),
                    "sensor_id": measurement.get("sensor_id"),
                    "parameter": measurement.get("parameter"),
                    "value": measurement.get("value"),
                    "unit": measurement.get("unit"),
                    "datetime_utc": timestamp_utc,
                    "observed_at_utc": observed_at,
                    "latitude": measurement.get("latitude"),
                    "longitude": measurement.get("longitude"),
                    "is_mobile": measurement.get("is_mobile", False),
                    "is_monitor": measurement.get("is_monitor", False),
                    "timezone": measurement.get("timezone"),
                    "provider": measurement.get("provider"),
                    "owner": measurement.get("owner"),
                    "licenses": measurement.get("licenses"),
                })

    return pd.DataFrame(rows, columns=COLUMNS)


def build_daily_observation_summary(observations: pd.DataFrame) -> pd.DataFrame:
    """Compact provider observations into station-level daily medians in UTC."""
    if observations.empty or not {"source", "city", "station", "parameter", "value", "unit", "datetime_utc"}.issubset(observations.columns):
        return pd.DataFrame(columns=DAILY_COLUMNS)
    frame = observations.copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["source", "city", "station", "parameter", "value", "datetime_utc"])
    if frame.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    frame["date"] = frame["datetime_utc"].dt.floor("D")
    aggregations = {
        "median_value": ("value", "median"),
        "reading_count": ("value", "size"),
        "first_utc": ("datetime_utc", "min"),
        "last_utc": ("datetime_utc", "max"),
    }
    for column in ["latitude", "longitude"]:
        if column in frame.columns:
            aggregations[column] = (column, "median")
    for column in ["is_mobile", "is_monitor"]:
        if column in frame.columns:
            aggregations[column] = (column, "max")
    for column in ["provider", "owner", "timezone", "licenses"]:
        if column in frame.columns:
            aggregations[column] = (column, "first")
    result = frame.groupby(
        ["source", "city", "station", "location_id", "parameter", "unit", "date"],
        dropna=False,
    ).agg(**aggregations).reset_index()
    for column in DAILY_COLUMNS:
        if column not in result:
            result[column] = None
    return result[DAILY_COLUMNS].sort_values(
        ["date", "city", "source", "station", "parameter"], kind="stable"
    ).reset_index(drop=True)


def update_daily_observation_archive(
    observations: pd.DataFrame,
    daily_path: str | Path = "data/processed/daily_city_observations.csv",
    retention_days: int = 365,
) -> int:
    """Upsert daily medians while retaining a year of compact city history."""
    destination = Path(daily_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    daily_new = build_daily_observation_summary(observations)
    existing = pd.DataFrame(columns=DAILY_COLUMNS)
    if destination.exists():
        try:
            existing = pd.read_csv(destination)
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            existing = pd.DataFrame(columns=DAILY_COLUMNS)
    if daily_new.empty and existing.empty:
        return 0
    if not observations.empty and "datetime_utc" in observations:
        stamps = pd.to_datetime(observations["datetime_utc"], errors="coerce", utc=True).dropna()
        window_start = stamps.min().floor("D") if not stamps.empty else None
        if window_start is not None and not existing.empty and "date" in existing:
            existing_dates = pd.to_datetime(existing["date"], errors="coerce", utc=True)
            existing = existing.loc[existing_dates < window_start].copy()
    combined = pd.concat([existing, daily_new], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce", utc=True)
    combined = combined.dropna(subset=["date"])
    dedupe = ["source", "city", "station", "parameter", "unit", "date"]
    combined = combined.drop_duplicates(subset=dedupe, keep="last")
    cutoff = pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=retention_days)
    combined = combined.loc[combined["date"] >= cutoff]
    combined = combined.sort_values(["date", "city", "source", "station", "parameter"])
    combined.to_csv(destination, index=False)
    return len(combined)


def append_snapshot(snapshot: pd.DataFrame, path: str | Path) -> int:
    """Append normalized rows, update daily archive, and cap high-frequency raw history."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = pd.read_csv(destination)
        combined = pd.concat([existing, snapshot], ignore_index=True)
    else:
        combined = snapshot.copy()

    if combined.empty:
        return 0

    update_daily_observation_archive(combined, destination.parent.parent / "processed" / "daily_city_observations.csv")
    combined = combined.drop_duplicates(
        subset=["source", "city", "location_id", "station", "sensor_id", "parameter", "datetime_utc"],
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
