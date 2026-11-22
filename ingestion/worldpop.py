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


def _validate_year(year: int) -> int:
    try:
        numeric = float(year)
    except (TypeError, ValueError):
        raise ValueError("WorldPop data year must be an integer from 2015 to 2030.") from None
    if not math.isfinite(numeric) or not numeric.is_integer() or not 2015 <= numeric <= 2030:
        raise ValueError("WorldPop data year must be an integer from 2015 to 2030.")
    return int(numeric)


def _finite_number(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _coordinate_pairs(value: object):
    if not isinstance(value, (list, tuple)):
        return
    if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
        yield float(value[0]), float(value[1])
        return
    for child in value:
        yield from _coordinate_pairs(child)


def _validate_geometry(geometry: dict) -> None:
    supported = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}
    if not isinstance(geometry, dict) or geometry.get("type") not in supported:
        raise ValueError("Unsupported WorldPop exposure geometry.")
    pairs = list(_coordinate_pairs(geometry.get("coordinates")))
    if not pairs or any(
        not math.isfinite(lon) or not math.isfinite(lat)
        or not -180 <= lon <= 180 or not -90 <= lat <= 90
        for lon, lat in pairs
    ):
        raise ValueError("WorldPop exposure geometry must contain valid WGS84 coordinates.")


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
    try:
        vertex_count = int(vertices)
    except (TypeError, ValueError):
        raise ValueError("Circle vertices must be an integer between 12 and 180.") from None
    if vertex_count != vertices or not 12 <= vertex_count <= 180:
        raise ValueError("Circle vertices must be an integer between 12 and 180.")
    lat_radius = radius / 111.32
    cosine = math.cos(math.radians(lat))
    if abs(cosine) < 0.01:
        raise ValueError("City-centre buffers are not supported this close to the poles.")
    lon_radius = radius / (111.32 * abs(cosine))
    ring = []
    for index in range(vertex_count):
        angle = 2 * math.pi * index / vertex_count
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
    selected_year = _validate_year(year)
    try:
        raw_radii = tuple(radii_km)
        parsed_radii = []
        for value in raw_radii:
            numeric = float(value)
            if not math.isfinite(numeric) or not numeric.is_integer():
                raise ValueError
            parsed_radii.append(int(numeric))
        radii = tuple(parsed_radii)
    except (TypeError, ValueError):
        raise ValueError("Catchment radii must be integer kilometre values.") from None
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
    raw_rings = points[0].get("rings") or []
    if not isinstance(raw_rings, list):
        raise WorldPopUnavailable("WorldPop returned an unexpected catchment-ring format.")
    rings = []
    for item in raw_rings:
        if not isinstance(item, dict):
            continue
        from_km = _finite_number(item.get("from_km", 0))
        to_km = _finite_number(item.get("to_km"))
        population = _finite_number(item.get("population"))
        cumulative = _finite_number(item.get("cumulative"))
        if (
            from_km is None or to_km is None or population is None or cumulative is None
            or from_km < 0 or to_km <= from_km or population < 0 or cumulative < population
        ):
            continue
        rings.append({
            "from_km": from_km,
            "to_km": to_km,
            "population": population,
            "cumulative": cumulative,
        })
    if not rings:
        raise WorldPopUnavailable("WorldPop returned no valid catchment rings.")

    group_values = {}
    raw_groups = groups.get("groups", []) if isinstance(groups, dict) else []
    for item in raw_groups if isinstance(raw_groups, list) else []:
        if isinstance(item, dict) and item.get("name"):
            population = _finite_number(item.get("population"))
            share = _finite_number(item.get("share"))
            group_values[str(item["name"])] = {
                "population": population if population is not None and population >= 0 else pd.NA,
                "share": share if share is not None and 0 <= share <= 1 else pd.NA,
            }

    area_km2 = _finite_number(groups.get("area_km2")) if isinstance(groups, dict) else None
    total_population = _finite_number(groups.get("total_population")) if isinstance(groups, dict) else None
    if area_km2 is None or area_km2 <= 0 or total_population is None or total_population < 0:
        raise WorldPopUnavailable("WorldPop returned invalid area or total-population values.")
    reported_density = _finite_number(groups.get("population_density")) if isinstance(groups, dict) else None
    if reported_density is None and area_km2 > 0:
        reported_density = total_population / area_km2
    if reported_density is not None and reported_density < 0:
        reported_density = None

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
        "rings": rings,
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
    selected_year = _validate_year(year)
    geometry = circle_geojson(latitude, longitude, radius_km=radius_km)
    payload = {"geojson": geometry, "year": selected_year, "resolution": "1km"}
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
    selected_radius = _finite_number(radius_km)
    if selected_radius is None or not 0 < selected_radius <= 100:
        raise ValueError("WorldPop exposure radius must be between 0 and 100 km.")
    selected_year = _validate_year(year)
    payload: dict[str, Any] = {
        "radius_km": selected_radius,
        "p": 1,
        "decay": "worldpop",
        "polygons": "area",
        "year": selected_year,
    }
    if features is not None:
        if not isinstance(features, dict) or features.get("type") != "FeatureCollection":
            raise ValueError("Exposure features must be a GeoJSON FeatureCollection.")
        feature_list = features.get("features")
        if not isinstance(feature_list, list) or not 1 <= len(feature_list) <= 1000:
            raise ValueError("Exposure feature collection must contain between 1 and 1,000 features.")
        for feature in feature_list:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError("Each exposure feature must be a GeoJSON Feature.")
            _validate_geometry(feature.get("geometry"))
        payload["features"] = features
    else:
        _validate_geometry(geometry)
        payload["geometry"] = geometry

    result = _post_json("/exposure", payload)
    total = result.get("total") or {}
    if not isinstance(total, dict):
        raise WorldPopUnavailable("WorldPop returned no weighted population-exposure estimate.")
    exposed_population = _finite_number(total.get("exposed_population"))
    population_within = _finite_number(total.get("population_within"))
    if exposed_population is None or exposed_population < 0:
        raise WorldPopUnavailable("WorldPop returned an invalid weighted population-exposure estimate.")
    if population_within is not None and population_within < 0:
        raise WorldPopUnavailable("WorldPop returned an invalid population-within value.")
    returned_year = _finite_number(result.get("data_year", selected_year))
    if returned_year is None or not returned_year.is_integer() or not 2015 <= returned_year <= 2030:
        raise WorldPopUnavailable("WorldPop returned an invalid data year.")
    returned_radius = _finite_number(result.get("radius_km", selected_radius))
    if returned_radius is None or returned_radius <= 0 or returned_radius > 100:
        raise WorldPopUnavailable("WorldPop returned an invalid exposure radius.")
    return {
        "data_year": int(returned_year),
        "radius_km": returned_radius,
        "exposed_population": exposed_population,
        "population_within": population_within,
        "rings": total.get("rings") if isinstance(total.get("rings"), list) else [],
        "features": result.get("features") if isinstance(result.get("features"), list) else [],
        "decay": str(result.get("decay", "worldpop")),
        "weighting_power": _finite_number(result.get("p", 1)) or 1.0,
        "method": "WorldPop distance-weighted proximity estimate; not a measured count of affected people.",
    }
