from __future__ import annotations

import math

import pandas as pd


def _station_key(frame: pd.DataFrame) -> str:
    return "location_id" if "location_id" in frame.columns else "station"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def build_zone_coverage(
    air: pd.DataFrame,
    city_latitude: float,
    city_longitude: float,
    now: pd.Timestamp | None = None,
    grid_km: float = 5.0,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Summarize returned station footprint; never infer unobserved city coverage."""
    summary_defaults = {
        "station_count": 0, "geocoded_station_count": 0, "nearest_station_km": None,
        "median_station_distance_km": None, "farthest_station_km": None,
        "occupied_grid_cells": 0, "fresh_stations": 0, "recent_stations": 0,
        "stale_stations": 0, "fixed_stations": 0, "mobile_stations": 0,
        "query_radius_km": 25.0,
    }
    station_columns = [
        "station", "latitude", "longitude", "distance_km", "latest_utc",
        "age_hours", "freshness", "pollutant_count", "reading_count",
    ]
    if air.empty or "datetime_utc" not in air.columns:
        return summary_defaults, pd.DataFrame(columns=station_columns), pd.DataFrame()

    frame = air.copy()
    key = _station_key(frame)
    if key not in frame.columns:
        return summary_defaults, pd.DataFrame(columns=station_columns), pd.DataFrame()
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame["latitude"] = pd.to_numeric(frame.get("latitude"), errors="coerce")
    frame["longitude"] = pd.to_numeric(frame.get("longitude"), errors="coerce")
    frame["distance_m"] = pd.to_numeric(frame.get("distance_m"), errors="coerce")
    frame = frame.dropna(subset=[key, "datetime_utc"])
    if frame.empty:
        return summary_defaults, pd.DataFrame(columns=station_columns), pd.DataFrame()

    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")

    rows = []
    for station_id, group in frame.groupby(key, dropna=False):
        latest = group["datetime_utc"].max()
        age = max(0.0, (now - latest).total_seconds() / 3600.0)
        freshness = "Fresh" if age <= 6 else ("Recent" if age <= 48 else "Stale")
        coord_rows = group.dropna(subset=["latitude", "longitude"])
        lat = float(coord_rows["latitude"].median()) if not coord_rows.empty else None
        lon = float(coord_rows["longitude"].median()) if not coord_rows.empty else None
        if lat is not None and lon is not None:
            distance_km = _haversine_km(city_latitude, city_longitude, lat, lon)
        else:
            distance_km = None
        distance_values = group["distance_m"].dropna()
        if distance_km is None and not distance_values.empty:
            distance_km = float(distance_values.min()) / 1000.0
        rows.append({
            "station": str(group["station"].dropna().iloc[0]) if "station" in group and group["station"].notna().any() else str(station_id),
            "station_id": station_id,
            "latitude": lat,
            "longitude": lon,
            "distance_km": distance_km,
            "latest_utc": latest,
            "age_hours": round(age, 1),
            "freshness": freshness,
            "pollutant_count": int(group["parameter"].nunique()) if "parameter" in group else 0,
            "reading_count": int(len(group)),
            "is_mobile": bool(group["is_mobile"].fillna(False).astype(bool).any()) if "is_mobile" in group else False,
        })
    inventory = pd.DataFrame(rows)
    mapped = inventory.dropna(subset=["latitude", "longitude"]).copy()
    distances = mapped["distance_km"].dropna()
    if not mapped.empty:
        # A 5 km local grid reports only cells containing returned stations.
        # Empty cells are not labelled as citywide monitoring gaps.
        lat_scale = 111.32
        lon_scale = max(1.0, 111.32 * math.cos(math.radians(city_latitude)))
        mapped["grid_x"] = ((mapped["longitude"] - city_longitude) * lon_scale / grid_km).apply(math.floor)
        mapped["grid_y"] = ((mapped["latitude"] - city_latitude) * lat_scale / grid_km).apply(math.floor)
        occupied = mapped.groupby(["grid_x", "grid_y"]).agg(
            station_count=("station_id", "nunique"),
            station_names=("station", lambda x: ", ".join(sorted(set(map(str, x))))),
        ).reset_index()
        grid_frame = occupied
    else:
        grid_frame = pd.DataFrame(columns=["grid_x", "grid_y", "station_count", "station_names"])

    summary = {
        "station_count": int(inventory["station_id"].nunique()),
        "geocoded_station_count": int(len(mapped)),
        "nearest_station_km": round(float(distances.min()), 2) if not distances.empty else None,
        "median_station_distance_km": round(float(distances.median()), 2) if not distances.empty else None,
        "farthest_station_km": round(float(distances.max()), 2) if not distances.empty else None,
        "occupied_grid_cells": int(len(grid_frame)),
        "fresh_stations": int((inventory["freshness"] == "Fresh").sum()),
        "recent_stations": int((inventory["freshness"] == "Recent").sum()),
        "stale_stations": int((inventory["freshness"] == "Stale").sum()),
        "mobile_stations": int(inventory["is_mobile"].sum()) if "is_mobile" in inventory else 0,
        "fixed_stations": int((~inventory["is_mobile"]).sum()) if "is_mobile" in inventory else int(len(inventory)),
        "query_radius_km": 25.0,
    }
    inventory = inventory.sort_values(["distance_km", "station"], na_position="last").reset_index(drop=True)
    return summary, inventory, grid_frame


def detect_observed_hotspot_clusters(
    air: pd.DataFrame,
    parameter: str,
    unit: str,
    now: pd.Timestamp | None = None,
    freshness_hours: int = 6,
    minimum_stations: int = 6,
    neighbour_radius_km: float = 5.0,
) -> tuple[str, pd.DataFrame, int]:
    """Find clusters of relatively high, recent station observations.

    This is a within-city relative signal, not a regulatory threshold, risk
    classification or interpolated neighbourhood surface. At least six
    distinct recent stations with coordinates and a common unit are required.
    """
    result_columns = ["station", "latitude", "longitude", "value", "unit", "datetime_utc", "cluster"]
    if air.empty or not {"parameter", "unit", "value", "datetime_utc", "latitude", "longitude"}.issubset(air.columns):
        return "insufficient_data", pd.DataFrame(columns=result_columns), 0
    frame = air.loc[
        (air["parameter"].astype(str).str.lower() == str(parameter).lower())
        & (air["unit"].astype(str) == str(unit))
    ].copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["value", "latitude", "longitude", "datetime_utc"])
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    frame = frame.loc[
        (frame["datetime_utc"] >= now - pd.Timedelta(hours=freshness_hours))
        & (frame["datetime_utc"] <= now + pd.Timedelta(minutes=15))
    ].copy()
    if "is_mobile" in frame.columns:
        frame = frame.loc[~frame["is_mobile"].fillna(False).astype(bool)].copy()
    if frame.empty:
        return "no_fresh_observations", pd.DataFrame(columns=result_columns), 0

    key = _station_key(frame)
    frame = frame.sort_values("datetime_utc").drop_duplicates(subset=[key], keep="last")
    sample_count = int(frame[key].nunique())
    if sample_count < minimum_stations:
        return "insufficient_station_density", pd.DataFrame(columns=result_columns), sample_count

    threshold = float(frame["value"].quantile(0.75))
    high = frame.loc[frame["value"] > threshold].copy().reset_index(drop=True)
    if len(high) < 2:
        return "no_cluster", pd.DataFrame(columns=result_columns), sample_count

    adjacency = {i: set() for i in range(len(high))}
    for i in range(len(high)):
        for j in range(i + 1, len(high)):
            distance = _haversine_km(
                float(high.loc[i, "latitude"]), float(high.loc[i, "longitude"]),
                float(high.loc[j, "latitude"]), float(high.loc[j, "longitude"]),
            )
            if distance <= neighbour_radius_km:
                adjacency[i].add(j)
                adjacency[j].add(i)

    clusters = []
    visited = set()
    cluster_id = 0
    for node in adjacency:
        if node in visited:
            continue
        stack, component = [node], []
        visited.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in adjacency[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(neighbour)
        if len(component) >= 2:
            cluster_id += 1
            for index in component:
                row = high.loc[index].to_dict()
                row["station"] = str(row.get("station", row.get(key, "Station")))
                row["cluster"] = cluster_id
                clusters.append(row)
    if not clusters:
        return "no_cluster", pd.DataFrame(columns=result_columns), sample_count
    output = pd.DataFrame(clusters)
    return "cluster_found", output[result_columns], sample_count
