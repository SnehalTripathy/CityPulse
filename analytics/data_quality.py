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
    if station_column not in frame.columns:
        frame["station"] = "Unknown station"
        station_column = "station"

    rows: list[dict] = []
    for (parameter, unit), group in frame.groupby(["parameter", "unit"], dropna=False):
        latest = group["datetime_utc"].max()
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
            "median_value": float(group["value"].median()),
            "min_value": float(group["value"].min()),
            "max_value": float(group["value"].max()),
            "station_count": int(group[station_column].nunique(dropna=True)),
            "reading_count": int(len(group)),
            "latest_utc": latest,
            "age_hours": round(age_hours, 1),
            "freshness": freshness,
        })
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["parameter", "unit"], kind="stable"
    ).reset_index(drop=True)
