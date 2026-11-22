from __future__ import annotations

import pandas as pd


UNIT_TO_UG_M3 = {"µg/m3": 1.0, "ug/m3": 1.0, "mg/m3": 1000.0}


def _parameter_token(value: object) -> str:
    return str(value).lower().replace(".", "").replace("_", "").replace(" ", "").replace("₂", "2").replace("₅", "5")


def _unit_token(value: object) -> str:
    return str(value).lower().replace(" ", "").replace("μ", "µ").replace("³", "3").replace("^", "")


def build_pollution_event_features(
    air: pd.DataFrame,
    pollutant: str,
    threshold_ug_m3: float,
    now: pd.Timestamp | None = None,
    max_age_hours: int = 24,
) -> dict:
    """Create GeoJSON point features for fresh fixed stations individually above a trigger.

    Each feature preserves the actual station location and threshold-crossing
    report. Mobile sensors, incompatible units, future timestamps and stale
    readings are excluded.
    """
    required = {"parameter", "unit", "value", "datetime_utc", "latitude", "longitude"}
    empty = {"type": "FeatureCollection", "features": []}
    if air.empty or not required.issubset(air.columns):
        return empty

    frame = air.copy()
    frame["parameter_token"] = frame["parameter"].map(_parameter_token)
    frame = frame.loc[frame["parameter_token"].isin({pollutant, pollutant + "mass"})].copy()
    frame["unit_token"] = frame["unit"].map(_unit_token)
    frame = frame.loc[frame["unit_token"].isin(UNIT_TO_UG_M3)].copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce") * frame["unit_token"].map(UNIT_TO_UG_M3)
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame = frame.dropna(subset=["value", "datetime_utc", "latitude", "longitude"])
    current = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")
    frame = frame.loc[
        (frame["datetime_utc"] >= current - pd.Timedelta(hours=max_age_hours))
        & (frame["datetime_utc"] <= current + pd.Timedelta(minutes=15))
        & (frame["value"] >= float(threshold_ug_m3))
    ].copy()
    if "is_mobile" in frame.columns:
        mobile = frame["is_mobile"].map(lambda value: str(value).strip().lower() in {"true", "1", "yes", "y"})
        frame = frame.loc[~mobile].copy()
    if frame.empty:
        return empty

    if "location_id" in frame.columns:
        fallback = frame["station"] if "station" in frame.columns else frame.index.astype(str)
        frame["_station_key"] = frame["location_id"].where(frame["location_id"].notna(), fallback)
    elif "station" in frame.columns:
        frame["_station_key"] = frame["station"]
    else:
        frame["_station_key"] = frame.index.astype(str)
    frame = frame.sort_values("datetime_utc").drop_duplicates("_station_key", keep="last")

    features = []
    for row in frame.to_dict(orient="records")[:1000]:
        station = str(row.get("station") or row.get("_station_key"))
        features.append({
            "type": "Feature",
            "id": str(row.get("location_id") or row.get("_station_key")),
            "properties": {
                "station": station,
                "pollutant": pollutant,
                "value_ug_m3": float(row["value"]),
                "datetime_utc": row["datetime_utc"].isoformat(),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["longitude"]), float(row["latitude"])],
            },
        })
    return {"type": "FeatureCollection", "features": features}
