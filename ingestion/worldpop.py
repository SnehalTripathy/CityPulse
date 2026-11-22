from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import transform as transform_coordinates
import requests

WORLDPOP_API = "https://api.worldpop.org/v3"
WORLDPOP_HEADERS = {
    "User-Agent": "CityPulse/1.0 (+https://github.com/SnehalTripathy/CityPulse)",
    "Accept": "application/json",
}
REQUEST_TIMEOUT = (8, 60)
DEFAULT_YEAR = 2025
DEMOGRAPHIC_GROUPS = ["under_5", "age_65_plus", "age_15_64"]


class WorldPopUnavailable(RuntimeError):
    """Raised when WorldPop cannot provide a valid population result."""


def circle_geojson(
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    vertices: int = 48,
) -> dict:
    """Approximate a small city-centre catchment as a WGS84 GeoJSON polygon."""
    lat = float(latitude)
    lon = float(longitude)
    radius = float(radius_km)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude or longitude is outside WGS84 bounds.")
    if not (0 < radius <= 100):
        raise ValueError("Population catchment radius must be between 0 and 100 km.")
    if vertices < 12 or vertices > 180:
        raise ValueError("Circle vertices must be between 12 and 180.")
    lat_radius = radius / 111.32
    cosine = math.cos(math.radians(lat))
    if abs(cosine) < 0.01:
        raise ValueError("City-centre buffers are not supported this close to the poles.")
    lon_radius = radius / (111.32 * abs(cosine))
    ring = []
    for index in range(vertices):
        angle = 2 * math.pi * index / vertices
        ring.append([
            lon + lon_radius * math.cos(angle),
            lat + lat_radius * math.sin(angle),
        ])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _post_json(path: str, payload: dict) -> dict:
    try:
        response = requests.post(
            f"{WORLDPOP_API}{path}",
            json=payload,
            headers={**WORLDPOP_HEADERS, "Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WorldPopUnavailable(f"WorldPop population service is temporarily unavailable: {exc}") from exc
    if not isinstance(result, dict):
        raise WorldPopUnavailable("WorldPop returned an unexpected response format.")
    return result


def fetch_population_context(
    latitude: float,
    longitude: float,
    year: int = DEFAULT_YEAR,
    radii_km: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Return WorldPop catchment rings and demographic groups around a city centre.

    The 10 km boundary is a geometric approximation around the configured
    city-centre coordinate, not an administrative city boundary.
    """
    selected_year = int(year)
    if selected_year < 2015 or selected_year > 2030:
        raise ValueError("WorldPop data year must be between 2015 and 2030.")
    radii = tuple(int(value) for value in radii_km)
    if not radii or len(radii) > 10 or sorted(set(radii)) != list(radii):
        raise ValueError("Catchment radii must be unique, ascending integers.")
    if any(value < 1 or value > 100 for value in radii):
        raise ValueError("Catchment radii must be between 1 and 100 km.")
    if radii[-1] > 10:
        raise ValueError("CityPulse city-centre population context is capped at 10 km.")

    geometry = circle_geojson(latitude, longitude, radius_km=float(radii[-1]))
    catchment = _post_json(
        "/catchment",
        {
            "points": [{"id": "city-centre", "lon": float(longitude), "lat": float(latitude)}],
            "radii_km": list(radii),
            "year": selected_year,
        },
    )
    groups = _post_json(
        "/groups",
        {
            "geojson": geometry,
            "year": selected_year,
            "groups": DEMOGRAPHIC_GROUPS,
        },
    )

    points = catchment.get("points") or []
    if not points or not isinstance(points[0], dict):
        raise WorldPopUnavailable("WorldPop returned no city-centre catchment result.")
    rings = points[0].get("rings") or []
    if not isinstance(rings, list):
        raise WorldPopUnavailable("WorldPop returned an unexpected catchment-ring format.")

    group_values = {}
    for item in groups.get("groups", []) if isinstance(groups.get("groups"), list) else []:
        if isinstance(item, dict) and item.get("name"):
            group_values[str(item["name"])] = {
                "population": pd.to_numeric(item.get("population"), errors="coerce"),
                "share": pd.to_numeric(item.get("share"), errors="coerce"),
            }

    area_km2 = float(groups.get("area_km2")) if groups.get("area_km2") is not None else None
    total_population = float(groups.get("total_population")) if groups.get("total_population") is not None else None
    reported_density = pd.to_numeric(groups.get("population_density"), errors="coerce")
    if pd.isna(reported_density) and area_km2 and area_km2 > 0 and total_population is not None:
        reported_density = total_population / area_km2

    return {
        "city_centre": {"latitude": float(latitude), "longitude": float(longitude)},
        "data_year": int(groups.get("data_year", catchment.get("data_year", selected_year))),
        "data_source": (
            str(groups.get("data_source") or catchment.get("data_source"))
            if "R2025A" in str(groups.get("data_source") or catchment.get("data_source") or "")
            else "WorldPop Global2 R2025A, 100 m"
        ),
        "release": "WorldPop Global2 R2025A",
        "licence": "CC BY 4.0",
        "area_km2": area_km2,
        "total_population_10km": total_population,
        "population_density_km2": float(reported_density) if pd.notna(reported_density) else None,
        "rings": [
            {
                "from_km": float(item.get("from_km", 0)),
                "to_km": float(item["to_km"]),
                "population": float(item["population"]),
                "cumulative": float(item["cumulative"]),
            }
            for item in rings
            if isinstance(item, dict)
            and item.get("to_km") is not None
            and item.get("population") is not None
            and item.get("cumulative") is not None
        ],
        "demographic_groups": group_values,
        "geometry": geometry,
        "method": "WorldPop 100 m estimates aggregated for distance rings and an approximate 10 km city-centre polygon.",
    }


def fetch_population_raster(
    latitude: float,
    longitude: float,
    year: int = DEFAULT_YEAR,
    radius_km: float = 10.0,
) -> pd.DataFrame:
    """Fetch the WorldPop 1 km population raster and return non-zero cell centres."""
    geometry = circle_geojson(latitude, longitude, radius_km=radius_km)
    payload = {"geojson": geometry, "year": int(year), "resolution": "1km"}
    try:
        response = requests.post(
            f"{WORLDPOP_API}/raster",
            json=payload,
            headers={**WORLDPOP_HEADERS, "Content-Type": "application/json", "Accept": "image/tiff"},
            timeout=(8, 90),
        )
        response.raise_for_status()
        with MemoryFile(response.content) as memory_file:
            with memory_file.open() as dataset:
                data = dataset.read(1, masked=True)
                if dataset.crs is None:
                    raise WorldPopUnavailable("WorldPop population raster has no coordinate reference system.")
                valid = (~np.ma.getmaskarray(data)) & np.isfinite(np.asarray(data.filled(np.nan)))
                values = np.asarray(data.filled(np.nan), dtype=float)
                valid &= values > 0
                rows, cols = np.where(valid)
                if len(rows) == 0:
                    return pd.DataFrame(columns=["latitude", "longitude", "population_per_cell"])
                xs, ys = rasterio.transform.xy(dataset.transform, rows.tolist(), cols.tolist(), offset="center")
                if dataset.crs.to_epsg() != 4326:
                    xs, ys = transform_coordinates(dataset.crs, "EPSG:4326", xs, ys)
                result = pd.DataFrame({
                    "longitude": np.asarray(xs, dtype=float),
                    "latitude": np.asarray(ys, dtype=float),
                    "population_per_cell": values[rows, cols],
                })
    except WorldPopUnavailable:
        raise
    except (requests.RequestException, rasterio.errors.RasterioError, ValueError, OSError) as exc:
        raise WorldPopUnavailable(f"WorldPop 1 km population layer is temporarily unavailable: {exc}") from exc
    return result.sort_values("population_per_cell", ascending=False).reset_index(drop=True)


def fetch_worldpop_event_exposure(
    geometry: dict,
    radius_km: float,
    year: int = DEFAULT_YEAR,
    features: dict | None = None,
) -> dict[str, Any]:
    """Estimate distance-weighted population near one event geometry or event features.

    For multiple event features WorldPop counts each person against the nearest
    feature, avoiding double counting between overlapping event buffers.
    """
    if not (0 < float(radius_km) <= 100):
        raise ValueError("WorldPop exposure radius must be between 0 and 100 km.")
    if int(year) < 2015 or int(year) > 2030:
        raise ValueError("WorldPop data year must be between 2015 and 2030.")
    payload: dict[str, Any] = {
        "radius_km": float(radius_km),
        "p": 1,
        "decay": "worldpop",
        "polygons": "area",
        "year": int(year),
    }
    if features is not None:
        if features.get("type") != "FeatureCollection" or not features.get("features"):
            raise ValueError("Exposure features must be a non-empty GeoJSON FeatureCollection.")
        payload["features"] = features
    else:
        if not isinstance(geometry, dict) or geometry.get("type") not in {
            "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"
        }:
            raise ValueError("Unsupported WorldPop exposure geometry.")
        payload["geometry"] = geometry

    result = _post_json("/exposure", payload)
    total = result.get("total") or {}
    if not isinstance(total, dict) or total.get("exposed_population") is None:
        raise WorldPopUnavailable("WorldPop returned no weighted population-exposure estimate.")
    return {
        "data_year": int(result.get("data_year", year)),
        "radius_km": float(result.get("radius_km", radius_km)),
        "exposed_population": float(total["exposed_population"]),
        "population_within": float(total["population_within"]) if total.get("population_within") is not None else None,
        "rings": total.get("rings") if isinstance(total.get("rings"), list) else [],
        "features": result.get("features") if isinstance(result.get("features"), list) else [],
        "decay": str(result.get("decay", "worldpop")),
        "weighting_power": float(result.get("p", 1)),
        "method": "WorldPop distance-weighted proximity estimate; not a measured count of affected people.",
    }
