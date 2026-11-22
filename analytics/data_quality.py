from __future__ import annotations

import pandas as pd


def summarize_air_quality(
    air: pd.DataFrame,
    now: pd.Timestamp | None = None,
    recent_hours: int = 48,
) -> pd.DataFrame:
    """Summarize actual sensor observations by pollutant and unit.

    The output preserves source units and timestamps; it does not convert
    pollutant concentrations or calculate an official AQI.
    """
    columns = [
        "parameter", "unit", "median_value", "min_value", "max_value",
        "station_count", "reading_count", "latest_utc", "age_hours", "freshness",
        "future_timestamp_readings",
    ]
    if air.empty or not {"parameter", "value", "unit", "datetime_utc"}.issubset(air.columns):
        return pd.DataFrame(columns=columns)

    frame = air.copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["parameter", "value", "datetime_utc"])
    if frame.empty:
        return pd.DataFrame(columns=columns)

    now = now or pd.Timestamp.now(tz="UTC")
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")

    station_column = "location_id" if "location_id" in frame.columns else "station"
    if station_column == "location_id" and "station" in frame.columns:
        frame["_station_key"] = frame["location_id"].where(frame["location_id"].notna(), frame["station"])
        station_column = "_station_key"
    if station_column not in frame.columns:
        frame["station"] = "Unknown station"
        station_column = "station"

    rows: list[dict] = []
    future_limit = now + pd.Timedelta(minutes=15)
    for (parameter, unit), group in frame.groupby(["parameter", "unit"], dropna=False):
        future_rows = group.loc[group["datetime_utc"] > future_limit]
        valid_group = group.loc[group["datetime_utc"] <= future_limit].copy()
        if valid_group.empty:
            rows.append({
                "parameter": str(parameter),
                "unit": str(unit) if pd.notna(unit) else "Unspecified",
                "median_value": None,
                "min_value": None,
                "max_value": None,
                "station_count": 0,
                "reading_count": 0,
                "latest_utc": group["datetime_utc"].min(),
                "age_hours": None,
                "freshness": "Future timestamp",
                "future_timestamp_readings": int(len(future_rows)),
            })
            continue

        latest = valid_group["datetime_utc"].max()
        age_hours = max(0.0, (now - latest).total_seconds() / 3600.0)
        if age_hours <= 6:
            freshness = "Fresh"
        elif age_hours <= recent_hours:
            freshness = "Recent"
        else:
            freshness = "Stale"
        rows.append({
            "parameter": str(parameter),
            "unit": str(unit) if pd.notna(unit) else "Unspecified",
            "median_value": float(valid_group["value"].median()),
            "min_value": float(valid_group["value"].min()),
            "max_value": float(valid_group["value"].max()),
            "station_count": int(valid_group[station_column].nunique(dropna=True)),
            "reading_count": int(len(valid_group)),
            "latest_utc": latest,
            "age_hours": round(age_hours, 1),
            "freshness": freshness,
            "future_timestamp_readings": int(len(future_rows)),
        })
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["parameter", "unit"], kind="stable"
    ).reset_index(drop=True)
