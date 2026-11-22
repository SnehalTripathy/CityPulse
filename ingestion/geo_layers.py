from __future__ import annotations

from datetime import date, timedelta
import math

import pandas as pd
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NASA_GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
WORLD_COVER_WMS = "https://mapproxy.terrascope.be/mapproxy/service"
REQUEST_TIMEOUT = (5, 30)


def fetch_green_spaces(
    latitude: float,
    longitude: float,
    radius_m: int = 5000,
    limit: int = 120,
) -> pd.DataFrame:
    """Fetch mapped parks and green/vegetated features from OpenStreetMap.

    Returned polygons are represented by their provider-supplied centre point;
    this is a discovery layer, not a complete green-cover inventory.
    """
    query = f"""
[out:json][timeout:25];
(
  node["leisure"~"^(park|garden|nature_reserve)$"](around:{int(radius_m)},{latitude},{longitude});
  way["leisure"~"^(park|garden|nature_reserve)$"](around:{int(radius_m)},{latitude},{longitude});
  relation["leisure"~"^(park|garden|nature_reserve)$"](around:{int(radius_m)},{latitude},{longitude});
  way["landuse"~"^(forest|grass|recreation_ground)$"](around:{int(radius_m)},{latitude},{longitude});
  relation["landuse"~"^(forest|grass|recreation_ground)$"](around:{int(radius_m)},{latitude},{longitude});
  way["natural"~"^(wood|grassland)$"](around:{int(radius_m)},{latitude},{longitude});
  relation["natural"~"^(wood|grassland)$"](around:{int(radius_m)},{latitude},{longitude});
);
out center tags {int(limit)};
"""
    response = requests.post(OVERPASS_URL, data={"data": query}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    rows = []
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        centre = element.get("center") or {}
        lat = element.get("lat", centre.get("lat"))
        lon = element.get("lon", centre.get("lon"))
        if lat is None or lon is None:
            continue
        name = tags.get("name") or tags.get("name:en") or "Unnamed mapped green space"
        category = tags.get("leisure") or tags.get("landuse") or tags.get("natural") or "green space"
        rows.append({
            "name": str(name),
            "category": str(category),
            "latitude": float(lat),
            "longitude": float(lon),
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "distance_km": 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(
                math.sin(math.radians(float(lat) - latitude) / 2) ** 2
                + math.cos(math.radians(latitude)) * math.cos(math.radians(float(lat)))
                * math.sin(math.radians(float(lon) - longitude) / 2) ** 2
            ))),
        })
    return pd.DataFrame(rows, columns=["name", "category", "latitude", "longitude", "distance_km", "osm_type", "osm_id"])


def _fetch_wms_image(endpoint: str, layer: str, latitude: float, longitude: float, date_value: str, width: int = 720, height: int = 560) -> bytes:
    delta_lat = 0.055
    delta_lon = 0.055 / max(0.25, abs(__import__("math").cos(__import__("math").radians(latitude))))
    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetMap",
        "layers": layer,
        "styles": "",
        "srs": "EPSG:4326",
        "bbox": f"{longitude-delta_lon},{latitude-delta_lat},{longitude+delta_lon},{latitude+delta_lat}",
        "width": width,
        "height": height,
        "format": "image/png",
        "transparent": "false",
        "time": date_value,
    }
    response = requests.get(endpoint, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.lower().startswith("image/"):
        raise RuntimeError(f"Map service did not return an image (content type: {content_type or 'unknown'}).")
    return response.content


def fetch_nasa_land_surface_temperature(
    latitude: float,
    longitude: float,
    observation_date: date | None = None,
) -> tuple[bytes, str]:
    """Return NASA GIBS MODIS Terra daytime LST imagery for a selected date.

    The PNG is a visualization, not a numeric LST raster. Cloud gaps and the
    satellite's daytime overpass mean it is not by itself a city UHI estimate.
    """
    selected_date = observation_date or (date.today() - timedelta(days=2))
    image = _fetch_wms_image(
        NASA_GIBS_WMS, "MODIS_Terra_Land_Surface_Temp_Day",
        latitude, longitude, selected_date.isoformat(),
    )
    return image, selected_date.isoformat()


def fetch_esa_worldcover(
    latitude: float,
    longitude: float,
) -> bytes:
    """Return the ESA WorldCover 2021 10 m land-cover classification image."""
    return _fetch_wms_image(
        WORLD_COVER_WMS, "esa-worldcover-map-10m-2021-v2_map",
        latitude, longitude, "2021-01-01",
    )
