from __future__ import annotations

import math

import pandas as pd


def validate_observations(
    observations: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> dict:
    """Audit raw environmental rows without silently repairing or imputing them."""
    required = {"parameter", "unit", "value", "datetime_utc"}
    if observations.empty:
        return {
            "status": "no_data",
            "rows_total": 0,
            "rows_valid": 0,
            "rows_invalid": 0,
            "rows_future": 0,
            "missing_required_columns": sorted(required),
            "issues": ["No observations are available to validate."],
            "by_parameter": pd.DataFrame(),
        }
    missing_columns = sorted(required - set(observations.columns))
    frame = observations.copy()
    issues = []
    if missing_columns:
        issues.append("Missing required columns: " + ", ".join(missing_columns))
    if "value" not in frame:
        frame["value"] = pd.NA
    if "datetime_utc" not in frame:
        frame["datetime_utc"] = pd.NaT
    frame["_value_numeric"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["_time"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame["_unit"] = frame["unit"].astype("string").str.lower().str.replace(" ", "", regex=False) if "unit" in frame else pd.NA
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    future = frame["_time"] > now + pd.Timedelta(minutes=15)
    missing_value = frame["_value_numeric"].isna()
    missing_time = frame["_time"].isna()
    non_finite = frame["_value_numeric"].map(lambda x: False if pd.isna(x) else not math.isfinite(float(x)))
    invalid = missing_value | missing_time | non_finite
    plausible = pd.Series(True, index=frame.index)
    if "parameter" in frame:
        token = frame["parameter"].astype(str).str.lower().str.replace("₂", "2").str.replace("₅", "5")
        for names, low, high in [
            ({"pm25", "pm2.5"}, 0, 2000),
            ({"pm10"}, 0, 3000),
            ({"temperature", "temperature_2m", "apparent_temperature"}, -90, 65),
            ({"relativehumidity", "relative_humidity_2m"}, 0, 100),
            ({"wind_speed", "wind_speed_10m"}, 0, 150),
            ({"precipitation"}, 0, 500),
        ]:
            selected = token.isin(names)
            plausible.loc[selected] = frame.loc[selected, "_value_numeric"].between(low, high)
    out_of_range = ~plausible & ~missing_value
    valid = ~(invalid | future | out_of_range)
    if invalid.any():
        issues.append(f"{int(invalid.sum())} rows have missing, non-numeric or non-finite values/timestamps.")
    if future.any():
        issues.append(f"{int(future.sum())} rows are more than 15 minutes in the future.")
    if out_of_range.any():
        issues.append(f"{int(out_of_range.sum())} rows are outside broad plausibility bounds for recognized parameters.")
    if "unit" in frame:
        frame["_unit_missing"] = frame["_unit"].isna() | frame["_unit"].isin({"", "<na>", "none"})
        if frame["_unit_missing"].any():
            issues.append(f"{int(frame['_unit_missing'].sum())} rows have no reported unit.")
    else:
        frame["_unit_missing"] = True
    if "station" in frame:
        frame["_station_missing"] = frame["station"].isna() | frame["station"].astype(str).str.strip().eq("")
    elif "location_id" in frame:
        frame["_station_missing"] = frame["location_id"].isna()
    else:
        frame["_station_missing"] = True
    if frame["_station_missing"].any():
        issues.append(f"{int(frame['_station_missing'].sum())} rows have no station identity.")
    frame["_valid"] = valid
    frame["_future"] = future
    frame["_out_of_range"] = out_of_range
    if "parameter" in frame:
        grouped = frame.groupby("parameter", dropna=False).agg(
            rows=("parameter", "size"),
            valid_rows=("_valid", "sum"),
            future_rows=("_future", "sum"),
            out_of_range_rows=("_out_of_range", "sum"),
        ).reset_index()
    else:
        grouped = pd.DataFrame()
    return {
        "status": "review" if issues else "valid",
        "rows_total": int(len(frame)),
        "rows_valid": int(valid.sum()),
        "rows_invalid": int(invalid.sum()),
        "rows_future": int(future.sum()),
        "rows_out_of_range": int(out_of_range.sum()),
        "rows_missing_unit": int(frame["_unit_missing"].sum()),
        "rows_missing_station": int(frame["_station_missing"].sum()),
        "missing_required_columns": missing_columns,
        "issues": issues or ["No validation issues detected in the inspected fields."],
        "by_parameter": grouped,
    }


def coverage_label(station_count: int, reading_age_hours: float | None) -> str:
    """Describe observable station coverage; do not imply statistical confidence."""
    count = int(station_count or 0)
    if count <= 0:
        return "No eligible station readings"
    if reading_age_hours is None or pd.isna(reading_age_hours):
        return f"{count} station(s); freshness unknown"
    age = float(reading_age_hours)
    freshness = "fresh" if age <= 6 else "recent" if age <= 24 else "stale"
    coverage = "limited coverage" if count <= 2 else "moderate coverage" if count <= 5 else "broader returned sample"
    return f"{coverage} · {count} station(s) · {freshness} ({age:.1f} h)"


def source_quality_summary(
    weather: dict,
    air: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> dict:
    current = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    weather_time = pd.to_datetime(weather.get("time"), errors="coerce", utc=True) if weather else pd.NaT
    weather_age = None if pd.isna(weather_time) else max(0.0, (current-weather_time).total_seconds()/3600)
    quality = validate_observations(air, current)
    return {
        "weather_age_hours": weather_age,
        "weather_status": "unavailable" if weather_age is None else "fresh" if weather_age <= 3 else "aging" if weather_age <= 12 else "stale",
        "air_quality": quality,
    }
