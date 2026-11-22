from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import heapq
import math

import numpy as np
from scipy.spatial import cKDTree

import pandas as pd
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_HEADERS = {
    "User-Agent": "CityPulse/1.0 (+https://github.com/SnehalTripathy/CityPulse)",
    "Accept": "application/json",
}
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
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=OVERPASS_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
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


def _fetch_wms_image(endpoint: str, layer: str, latitude: float, longitude: float, date_value: str | None = None, width: int = 720, height: int = 560) -> bytes:
    delta_lat = 0.055
    delta_lon = 0.055 / max(0.25, abs(math.cos(math.radians(latitude))))
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
    }
    if date_value:
        params["time"] = date_value
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
        latitude, longitude,
    )


WALKABLE_HIGHWAYS = {
    "footway", "path", "pedestrian", "steps", "living_street", "residential",
    "service", "unclassified", "track", "tertiary", "secondary", "primary",
    "cycleway", "bridleway", "tertiary_link", "secondary_link", "primary_link",
}


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def calculate_walking_access_from_osm(
    city_latitude: float,
    city_longitude: float,
    green_spaces: pd.DataFrame,
    elements: list[dict],
    maximum_snap_distance_m: float = 500.0,
    walking_speed_kmh: float = 4.8,
) -> tuple[pd.DataFrame, dict]:
    """Estimate walking-network distance from city centre to mapped green features.

    The route ends at the nearest walk-network node to each mapped feature
    centre, not at a verified public entrance. It uses the OSM ways returned
    for the bounded search area and therefore cannot establish citywide
    accessibility or prove that disconnected places are unreachable.
    """
    output_columns = [
        "name", "category", "straight_line_km", "walking_network_km",
        "estimated_walk_minutes", "park_snap_distance_m", "access_status",
    ]
    summary = {
        "status": "no_walk_network",
        "network_nodes": 0,
        "walkable_ways": 0,
        "routed_green_spaces": 0,
        "maximum_snap_distance_m": float(maximum_snap_distance_m),
        "assumed_walking_speed_kmh": float(walking_speed_kmh),
    }
    if green_spaces.empty:
        summary["status"] = "no_mapped_green_spaces"
        return pd.DataFrame(columns=output_columns), summary

    nodes: dict[int, tuple[float, float]] = {}
    for element in elements:
        if element.get("type") == "node" and element.get("lat") is not None and element.get("lon") is not None:
            nodes[int(element["id"])] = (float(element["lat"]), float(element["lon"]))

    graph: dict[int, list[tuple[int, float]]] = defaultdict(list)
    walkable_way_count = 0
    for element in elements:
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        highway = str(tags.get("highway", ""))
        if highway not in WALKABLE_HIGHWAYS:
            continue
        if str(tags.get("foot", "")).lower() == "no":
            continue
        if str(tags.get("access", "")).lower() in {"no", "private"}:
            continue
        if str(tags.get("motorroad", "")).lower() == "yes":
            continue
        node_ids = [int(value) for value in element.get("nodes", []) if int(value) in nodes]
        if len(node_ids) < 2:
            continue
        walkable_way_count += 1
        for first, second in zip(node_ids, node_ids[1:]):
            a_lat, a_lon = nodes[first]
            b_lat, b_lon = nodes[second]
            length = _distance_km(a_lat, a_lon, b_lat, b_lon)
            graph[first].append((second, length))
            graph[second].append((first, length))

    if not graph:
        summary.update({"status": "no_walkable_ways", "network_nodes": len(nodes)})
        rows = green_spaces.copy()
        rows["straight_line_km"] = pd.to_numeric(rows.get("distance_km"), errors="coerce")
        rows["walking_network_km"] = None
        rows["estimated_walk_minutes"] = None
        rows["park_snap_distance_m"] = None
        rows["access_status"] = "No walkable network returned"
        return rows[output_columns], summary

    graph_node_ids = list(graph)
    centre_lat = float(city_latitude)
    centre_lon = float(city_longitude)
    longitude_scale = max(0.05, math.cos(math.radians(centre_lat)))
    coordinates = np.array([
        (
            nodes[node_id][1] * 111.32 * longitude_scale,
            nodes[node_id][0] * 111.32,
        )
        for node_id in graph_node_ids
    ])
    tree = cKDTree(coordinates)

    def nearest_node(latitude: float, longitude: float) -> tuple[int, float]:
        point = (longitude * 111.32 * longitude_scale, latitude * 111.32)
        distance_degrees_km, index = tree.query(point, k=1)
        return graph_node_ids[int(index)], float(distance_degrees_km * 1000.0)

    origin_node, origin_snap_m = nearest_node(centre_lat, centre_lon)
    summary.update({
        "status": "ready",
        "network_nodes": len(graph),
        "walkable_ways": walkable_way_count,
        "origin_snap_distance_m": round(origin_snap_m, 1),
    })
    if origin_snap_m > maximum_snap_distance_m:
        summary["status"] = "origin_not_snapped"
        return pd.DataFrame(columns=output_columns), summary

    # Dijkstra from one origin; all park access distances reuse this single run.
    shortest = {origin_node: 0.0}
    queue = [(0.0, origin_node)]
    while queue:
        current_distance, node_id = heapq.heappop(queue)
        if current_distance > shortest.get(node_id, float("inf")):
            continue
        for neighbour, edge_km in graph.get(node_id, []):
            candidate = current_distance + edge_km
            if candidate < shortest.get(neighbour, float("inf")):
                shortest[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))

    rows = []
    for feature in green_spaces.to_dict(orient="records"):
        name = str(feature.get("name") or "Unnamed mapped green space")
        category = str(feature.get("category") or "green space")
        straight_line = feature.get("distance_km")
        lat, lon = feature.get("latitude"), feature.get("longitude")
        if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
            rows.append({
                "name":name, "category":category, "straight_line_km":straight_line,
                "walking_network_km":None, "estimated_walk_minutes":None,
                "park_snap_distance_m":None, "access_status":"Missing mapped feature coordinates",
            })
            continue
        target_node, target_snap_m = nearest_node(float(lat), float(lon))
        route = shortest.get(target_node)
        if target_snap_m > maximum_snap_distance_m:
            walking_km, walk_minutes, status = None, None, "Feature too far from mapped walk network"
        elif route is None:
            walking_km, walk_minutes, status = None, None, "No connected route in returned network sample"
        else:
            walking_km = origin_snap_m / 1000.0 + route + target_snap_m / 1000.0
            walk_minutes = walking_km / max(0.1, walking_speed_kmh) * 60.0
            status = "Estimated walk-network route"
        rows.append({
            "name":name,
            "category":category,
            "straight_line_km":float(straight_line) if straight_line is not None and pd.notna(straight_line) else None,
            "walking_network_km":round(walking_km, 2) if walking_km is not None else None,
            "estimated_walk_minutes":round(walk_minutes, 1) if walk_minutes is not None else None,
            "park_snap_distance_m":round(target_snap_m, 1),
            "access_status":status,
        })

    result = pd.DataFrame(rows, columns=output_columns)
    summary["routed_green_spaces"] = int(result["walking_network_km"].notna().sum())
    return result.sort_values("walking_network_km", na_position="last").reset_index(drop=True), summary


def fetch_walking_park_access(
    latitude: float,
    longitude: float,
    green_spaces: pd.DataFrame,
    radius_m: int = 6000,
) -> tuple[pd.DataFrame, dict]:
    """Fetch an OSM walkable way sample and estimate network proximity to parks."""
    if green_spaces.empty:
        return calculate_walking_access_from_osm(latitude, longitude, green_spaces, [])
    query = f"""
[out:json][timeout:40];
way(around:{int(radius_m)},{latitude},{longitude})["highway"]["foot"!="no"]["access"!="private"];
out body;
>;
out skel qt;
"""
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=OVERPASS_HEADERS,
        timeout=(5, 45),
    )
    response.raise_for_status()
    payload = response.json()
    elements = payload.get("elements", [])
    return calculate_walking_access_from_osm(
        latitude, longitude, green_spaces, elements
    )
