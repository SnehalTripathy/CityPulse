from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.spatial import Delaunay, QhullError, cKDTree


def _parameter_token(value: object) -> str:
    return (
        str(value).strip().lower().replace(".", "").replace("_", "")
        .replace(" ", "").replace("₂", "2").replace("₅", "5")
    )


def _unit_token(value: object) -> str:
    return (
        str(value).strip().lower().replace(" ", "").replace("μ", "µ")
        .replace("³", "3").replace("^", "")
    )


def interpolate_station_surface(
    air: pd.DataFrame,
    parameter: str,
    unit: str,
    now: pd.Timestamp | None = None,
    freshness_hours: int = 12,
    minimum_stations: int = 6,
    grid_spacing_km: float = 1.0,
    maximum_nearest_station_km: float = 3.0,
    power: float = 2.0,
) -> tuple[str, pd.DataFrame, dict]:
    """Create an exploratory inverse-distance-weighted surface.

    Only the convex hull of recent, geocoded, distinct stations is interpolated.
    Grid cells farther than maximum_nearest_station_km from a station are
    excluded. The function also reports leave-one-station-out MAE so the UI
    can show how well this sparse station set supports the surface.

    This is not a regulatory map, a calibrated exposure estimate, or a
    substitute for measurements between stations.
    """
    columns = ["latitude", "longitude", "estimated_value", "nearest_station_km"]
    empty = pd.DataFrame(columns=columns)
    diagnostics = {
        "station_count": 0,
        "grid_cells": 0,
        "freshness_hours": int(freshness_hours),
        "grid_spacing_km": float(grid_spacing_km),
        "maximum_nearest_station_km": float(maximum_nearest_station_km),
        "leave_one_out_mae": None,
        "median_baseline_mae": None,
        "idw_beats_baseline": None,
        "leave_one_out_rmse": None,
        "value_min": None,
        "value_max": None,
    }
    required = {"parameter", "unit", "value", "datetime_utc", "latitude", "longitude"}
    if air.empty or not required.issubset(air.columns):
        return "insufficient_data", empty, diagnostics

    selected = air.loc[
        air["parameter"].map(_parameter_token) == _parameter_token(parameter)
    ].copy()
    selected = selected.loc[selected["unit"].map(_unit_token) == _unit_token(unit)].copy()
    if selected.empty:
        return "no_matching_readings", empty, diagnostics

    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    selected["latitude"] = pd.to_numeric(selected["latitude"], errors="coerce")
    selected["longitude"] = pd.to_numeric(selected["longitude"], errors="coerce")
    selected["datetime_utc"] = pd.to_datetime(selected["datetime_utc"], errors="coerce", utc=True)
    selected = selected.dropna(subset=["value", "latitude", "longitude", "datetime_utc"])
    selected = selected.loc[
        selected["latitude"].between(-90, 90)
        & selected["longitude"].between(-180, 180)
    ]
    if selected.empty:
        return "no_geocoded_readings", empty, diagnostics

    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    cutoff = now - pd.Timedelta(hours=freshness_hours)
    selected = selected.loc[
        (selected["datetime_utc"] >= cutoff) & (selected["datetime_utc"] <= now + pd.Timedelta(minutes=15))
    ].copy()
    if "is_mobile" in selected.columns:
        selected = selected.loc[~selected["is_mobile"].map(lambda value: str(value).strip().lower() in {"true", "1", "yes", "y"})].copy()
    if selected.empty:
        return "no_fresh_observations", empty, diagnostics

    station_key = "location_id" if "location_id" in selected.columns else "station"
    if station_key not in selected.columns:
        selected["_station"] = selected.index.astype(str)
        station_key = "_station"
    selected = selected.sort_values("datetime_utc").drop_duplicates(
        subset=[station_key], keep="last"
    )
    selected = selected.drop_duplicates(subset=["latitude", "longitude"], keep="last")
    station_count = int(len(selected))
    diagnostics["station_count"] = station_count
    if station_count < minimum_stations:
        return "insufficient_station_density", empty, diagnostics

    latitudes = selected["latitude"].to_numpy(dtype=float)
    longitudes = selected["longitude"].to_numpy(dtype=float)
    values = selected["value"].to_numpy(dtype=float)
    centre_lat = float(np.mean(latitudes))
    centre_lon = float(np.mean(longitudes))
    x = (longitudes - centre_lon) * 111.32 * max(0.05, math.cos(math.radians(centre_lat)))
    y = (latitudes - centre_lat) * 111.32
    points = np.column_stack([x, y])

    try:
        hull = Delaunay(points)
    except QhullError:
        return "collinear_station_geometry", empty, diagnostics

    spacing = max(0.25, float(grid_spacing_km))
    x_values = np.arange(float(x.min()), float(x.max()) + spacing * 0.5, spacing)
    y_values = np.arange(float(y.min()), float(y.max()) + spacing * 0.5, spacing)
    xx, yy = np.meshgrid(x_values, y_values)
    grid_points = np.column_stack([xx.ravel(), yy.ravel()])
    inside = hull.find_simplex(grid_points) >= 0

    tree = cKDTree(points)
    distances, _ = tree.query(grid_points, k=1)
    inside &= distances <= float(maximum_nearest_station_km)
    grid_points = grid_points[inside]
    distances = distances[inside]
    if not len(grid_points):
        return "no_supported_grid_cells", empty, diagnostics

    # Inverse-distance weighting, with exact station matches handled directly.
    all_distances = np.linalg.norm(
        grid_points[:, None, :] - points[None, :, :], axis=2
    )
    estimates = np.empty(len(grid_points), dtype=float)
    exact = all_distances.min(axis=1) < 1e-9
    if exact.any():
        closest = all_distances[exact].argmin(axis=1)
        estimates[exact] = values[closest]
    if (~exact).any():
        weights = 1.0 / np.maximum(all_distances[~exact], 1e-9) ** float(power)
        estimates[~exact] = (weights @ values) / weights.sum(axis=1)

    # Leave-one-station-out interpolation error is a diagnostic, not a
    # guarantee of map accuracy or spatial representativeness.
    loo_predictions = []
    median_predictions = []
    for index in range(station_count):
        other = np.delete(points, index, axis=0)
        other_values = np.delete(values, index)
        distances_to_others = np.linalg.norm(other - points[index], axis=1)
        if distances_to_others.min() < 1e-9:
            continue
        weights = 1.0 / distances_to_others ** float(power)
        loo_predictions.append(float(np.dot(weights, other_values) / weights.sum()))
        median_predictions.append(float(np.median(other_values)))
    loo_errors = values - np.asarray(loo_predictions)
    baseline_errors = values - np.asarray(median_predictions)
    if len(loo_errors):
        loo_mae = float(np.mean(np.abs(loo_errors)))
        baseline_mae = float(np.mean(np.abs(baseline_errors)))
        diagnostics["leave_one_out_mae"] = round(loo_mae, 3)
        diagnostics["median_baseline_mae"] = round(baseline_mae, 3)
        diagnostics["leave_one_out_rmse"] = round(float(np.sqrt(np.mean(loo_errors ** 2))), 3)
        diagnostics["idw_beats_baseline"] = bool(loo_mae < baseline_mae)
        if loo_mae >= baseline_mae:
            return "failed_cross_validation", empty, diagnostics

    result = pd.DataFrame({
        "latitude": centre_lat + grid_points[:, 1] / 111.32,
        "longitude": centre_lon + grid_points[:, 0] / (111.32 * max(0.05, math.cos(math.radians(centre_lat)))),
        "estimated_value": estimates,
        "nearest_station_km": distances,
    })
    diagnostics.update({
        "grid_cells": int(len(result)),
        "value_min": round(float(np.min(estimates)), 3),
        "value_max": round(float(np.max(estimates)), 3),
    })
    return "ready", result, diagnostics
