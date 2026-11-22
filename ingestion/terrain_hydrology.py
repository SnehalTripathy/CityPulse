from __future__ import annotations

import math

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from scipy.ndimage import uniform_filter
import requests

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
DEM_COLLECTION = "cop-dem-glo-30"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
REQUEST_TIMEOUT = (5, 45)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def analyze_dem_grid(
    elevation_m: np.ndarray,
    bbox: tuple[float, float, float, float],
    city_latitude: float,
    city_longitude: float,
    minimum_cells: int = 100,
    maximum_points: int = 1200,
) -> tuple[pd.DataFrame, dict]:
    """Derive slope and local topographic-position indicators from a DEM grid.

    Low-lying/gentle cells are a relative terrain screening proxy only. This
    function does not estimate flood probability, flow accumulation or drainage
    capacity and must not be labelled as a flood forecast.
    """
    empty_columns = [
        "latitude", "longitude", "elevation_m", "slope_degrees",
        "topographic_position_m", "terrain_class",
    ]
    elevation = np.asarray(elevation_m, dtype=float)
    if elevation.ndim != 2 or min(elevation.shape, default=0) < 3:
        return pd.DataFrame(columns=empty_columns), {"status": "invalid_dem_grid"}
    valid = np.isfinite(elevation) & (elevation > -500) & (elevation < 9000)
    valid_count = int(valid.sum())
    if valid_count < minimum_cells:
        return pd.DataFrame(columns=empty_columns), {
            "status": "insufficient_dem_coverage", "valid_cells": valid_count,
        }

    left, bottom, right, top = bbox
    height, width = elevation.shape
    cell_x_m = max(1.0, (right - left) * 111320.0 * math.cos(math.radians(city_latitude)) / width)
    cell_y_m = max(1.0, (top - bottom) * 110574.0 / height)
    filled = np.where(valid, elevation, np.nanmedian(elevation[valid]))
    gradient_y, gradient_x = np.gradient(filled, cell_y_m, cell_x_m)
    slope = np.degrees(np.arctan(np.hypot(gradient_x, gradient_y)))

    # Topographic position = elevation minus the valid-cell mean in a ~1 km
    # moving neighbourhood. Negative values indicate locally lower terrain.
    window = max(3, int(round(1000.0 / max(cell_x_m, cell_y_m))))
    if window % 2 == 0:
        window += 1
    valid_float = valid.astype(float)
    local_count = uniform_filter(valid_float, size=window, mode="nearest")
    local_sum = uniform_filter(np.where(valid, elevation, 0.0), size=window, mode="nearest")
    local_mean = np.divide(
        local_sum, local_count, out=np.full_like(local_sum, np.nan), where=local_count > 1e-6
    )
    tpi = filled - local_mean
    slope[~valid] = np.nan
    tpi[~valid] = np.nan
    tpi_values = tpi[valid]
    low_threshold = float(np.nanquantile(tpi_values, 0.20))
    classes = np.full(elevation.shape, "Moderate terrain", dtype=object)
    gentle = valid & (slope <= 5.0)
    low_gentle = gentle & (tpi <= low_threshold)
    classes[gentle] = "Gentle slope"
    classes[valid & (slope >= 15.0)] = "Steeper terrain"
    classes[low_gentle] = "Relatively low-lying & gentle"
    classes[~valid] = "No DEM data"

    stride = max(1, int(math.ceil(math.sqrt((height * width) / max(1, maximum_points)))))
    rows, cols = np.mgrid[0:height:stride, 0:width:stride]
    sample_valid = valid[rows, cols]
    sample = pd.DataFrame({
        "latitude": top - (rows[sample_valid] + 0.5) * (top - bottom) / height,
        "longitude": left + (cols[sample_valid] + 0.5) * (right - left) / width,
        "elevation_m": elevation[rows[sample_valid], cols[sample_valid]],
        "slope_degrees": slope[rows[sample_valid], cols[sample_valid]],
        "topographic_position_m": tpi[rows[sample_valid], cols[sample_valid]],
        "terrain_class": classes[rows[sample_valid], cols[sample_valid]],
    })
    summary = {
        "status": "ready",
        "valid_cells": valid_count,
        "sample_points": int(len(sample)),
        "resolution_x_m": round(cell_x_m, 1),
        "resolution_y_m": round(cell_y_m, 1),
        "elevation_min_m": round(float(np.nanmin(elevation[valid])), 1),
        "elevation_median_m": round(float(np.nanmedian(elevation[valid])), 1),
        "elevation_max_m": round(float(np.nanmax(elevation[valid])), 1),
        "slope_median_degrees": round(float(np.nanmedian(slope[valid])), 2),
        "relative_low_terrain_threshold_m": round(low_threshold, 2),
        "relative_low_gentle_cells": int(low_gentle.sum()),
        "city_centre_reference": [float(city_latitude), float(city_longitude)],
        "method": "Copernicus DEM DSM; 1 km neighbourhood topographic position and slope",
    }
    return sample[empty_columns], summary


def fetch_terrain_susceptibility(
    latitude: float,
    longitude: float,
    radius_km: float = 12.0,
    grid_size: int = 360,
) -> tuple[pd.DataFrame, dict]:
    """Fetch Copernicus DEM GLO-30 tiles and derive a local terrain screen."""
    radius_lat = float(radius_km) / 110.574
    radius_lon = float(radius_km) / (111.32 * max(0.15, abs(math.cos(math.radians(latitude)))))
    bbox = (
        longitude - radius_lon, latitude - radius_lat,
        longitude + radius_lon, latitude + radius_lat,
    )
    diagnostics = {
        "status": "no_dem_tiles",
        "source": "Copernicus DEM GLO-30",
        "nominal_source_resolution_m": 30,
        "radius_km": float(radius_km),
        "tiles_found": 0,
        "tiles_used": 0,
    }
    catalog = pystac_client.Client.open(STAC_URL)
    search = catalog.search(collections=[DEM_COLLECTION], bbox=list(bbox), max_items=24)
    items = list(search.items())
    diagnostics["tiles_found"] = len(items)
    if not items:
        return pd.DataFrame(), diagnostics

    width = height = int(grid_size)
    transform = from_bounds(*bbox, width, height)
    dem = np.full((height, width), np.nan, dtype=np.float32)
    used = 0
    for raw_item in items:
        try:
            item = planetary_computer.sign(raw_item)
            asset = item.assets.get("data")
            if asset is None:
                continue
            tile = np.full((height, width), np.nan, dtype=np.float32)
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MAX_RETRY="2",
            ):
                with rasterio.open(asset.href) as source:
                    reproject(
                        source=rasterio.band(source, 1),
                        destination=tile,
                        src_transform=source.transform,
                        src_crs=source.crs,
                        dst_transform=transform,
                        dst_crs="EPSG:4326",
                        src_nodata=source.nodata,
                        dst_nodata=np.nan,
                        resampling=Resampling.bilinear,
                    )
            mask = np.isfinite(tile) & (tile > -500) & (tile < 9000)
            if mask.any():
                dem[mask] = tile[mask]
                used += 1
        except Exception:
            continue
    diagnostics["tiles_used"] = used
    frame, summary = analyze_dem_grid(
        dem, bbox, latitude, longitude, minimum_cells=100, maximum_points=1200
    )
    diagnostics.update(summary)
    diagnostics["source"] = "Copernicus DEM GLO-30"
    diagnostics["nominal_source_resolution_m"] = 30
    if diagnostics.get("status") == "ready":
        diagnostics["note"] = (
            "Copernicus DEM is a digital surface model. Relative low terrain and slope "
            "are screening indicators, not flood probability or drainage modelling."
        )
    return frame, diagnostics


def parse_hydro_features(
    payload: dict,
    city_latitude: float,
    city_longitude: float,
) -> pd.DataFrame:
    """Convert mapped OSM waterways and water bodies into a compact point layer."""
    rows = []
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        centre = element.get("center") or {}
        lat = element.get("lat", centre.get("lat"))
        lon = element.get("lon", centre.get("lon"))
        if lat is None or lon is None:
            continue
        category = tags.get("waterway") or tags.get("water") or tags.get("natural") or "water feature"
        name = tags.get("name") or tags.get("name:en") or "Unnamed mapped water feature"
        rows.append({
            "name": str(name),
            "category": str(category),
            "latitude": float(lat),
            "longitude": float(lon),
            "distance_km": round(_haversine_km(
                city_latitude, city_longitude, float(lat), float(lon)
            ), 2),
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
        })
    return pd.DataFrame(rows, columns=[
        "name", "category", "latitude", "longitude", "distance_km", "osm_type", "osm_id",
    ])


def fetch_hydro_features(
    latitude: float,
    longitude: float,
    radius_m: int = 12000,
    limit: int = 250,
) -> pd.DataFrame:
    """Fetch mapped rivers, streams, canals, drains and surface-water features."""
    query = f"""
[out:json][timeout:35];
(
  way(around:{int(radius_m)},{latitude},{longitude})["waterway"~"^(river|stream|canal|drain|ditch)$"];
  relation(around:{int(radius_m)},{latitude},{longitude})["waterway"~"^(river|stream|canal|drain|ditch)$"];
  way(around:{int(radius_m)},{latitude},{longitude})["natural"="water"];
  relation(around:{int(radius_m)},{latitude},{longitude})["natural"="water"];
  way(around:{int(radius_m)},{latitude},{longitude})["water"~"^(lake|reservoir|pond)$"];
  relation(around:{int(radius_m)},{latitude},{longitude})["water"~"^(lake|reservoir|pond)$"];
);
out center tags {int(limit)};
"""
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "CityPulse/1.0 (+https://github.com/SnehalTripathy/CityPulse)"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return parse_hydro_features(response.json(), latitude, longitude)
