from __future__ import annotations

import json
import math
import time

import requests

API = "https://api.worldpop.org/v3"
YEAR = 2025
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "CityPulse-WorldPop-SmokeCheck/1.0 (+https://github.com/SnehalTripathy/CityPulse)",
}
CITIES = {
    "Bengaluru": (12.9716, 77.5946),
    "London": (51.5074, -0.1278),
    "Nairobi": (-1.2864, 36.8219),
}
GROUPS = ["under_5", "age_65_plus", "age_15_64"]


def circle_geojson(latitude: float, longitude: float, radius_km: float = 10.0) -> dict:
    lat_radius = radius_km / 111.32
    lon_radius = radius_km / (111.32 * abs(math.cos(math.radians(latitude))))
    ring = []
    for index in range(48):
        angle = 2 * math.pi * index / 48
        ring.append([
            longitude + lon_radius * math.cos(angle),
            latitude + lat_radius * math.sin(angle),
        ])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def post_json(path: str, payload: dict) -> dict:
    response = requests.post(
        f"{API}{path}",
        json=payload,
        headers=HEADERS,
        timeout=(10, 90),
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or "error" in result:
        raise RuntimeError(f"{path} returned an invalid API payload: {result!r}")
    return result


def require_number(value: object, label: str, *, minimum: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AssertionError(f"{label} is missing or not numeric: {value!r}") from None
    if not math.isfinite(number) or number < minimum:
        raise AssertionError(f"{label} is outside the expected range: {number!r}")
    return number


def check_city(name: str, latitude: float, longitude: float) -> dict:
    catchment = post_json(
        "/catchment",
        {
            "points": [{"id": name, "lon": longitude, "lat": latitude}],
            "radii_km": [1, 3, 5, 10],
            "year": YEAR,
        },
    )
    time.sleep(1.1)  # Keep counting calls sequential and below the public rate limit.
    groups = post_json(
        "/groups",
        {
            "geojson": circle_geojson(latitude, longitude),
            "year": YEAR,
            "groups": GROUPS,
        },
    )

    points = catchment.get("points")
    if not isinstance(points, list) or not points or not isinstance(points[0], dict):
        raise AssertionError(f"{name}: catchment returned no point result")
    rings = points[0].get("rings")
    if not isinstance(rings, list) or len(rings) != 4:
        raise AssertionError(f"{name}: expected four catchment rings, received {rings!r}")
    for ring in rings:
        require_number(ring.get("population"), f"{name} ring population")
        require_number(ring.get("cumulative"), f"{name} cumulative population")

    area = require_number(groups.get("area_km2"), f"{name} catchment area", minimum=0.000001)
    total = require_number(groups.get("total_population"), f"{name} total population")
    returned_groups = {
        item.get("name"): item
        for item in groups.get("groups", [])
        if isinstance(item, dict)
    }
    absent = sorted(set(GROUPS) - set(returned_groups))
    if absent:
        raise AssertionError(f"{name}: demographic groups missing: {absent}")
    for group_name in GROUPS:
        group = returned_groups[group_name]
        require_number(group.get("population"), f"{name} {group_name} population")
        share = require_number(group.get("share"), f"{name} {group_name} share")
        if share > 1:
            raise AssertionError(f"{name}: {group_name} share exceeds 1: {share}")

    return {
        "city": name,
        "data_year": groups.get("data_year"),
        "area_km2": round(area, 3),
        "total_population_10km": round(total, 1),
        "ring_count": len(rings),
        "demographic_groups": GROUPS,
        "data_source": groups.get("data_source"),
    }


def check_raster(latitude: float, longitude: float) -> dict:
    response = requests.post(
        f"{API}/raster",
        json={
            "geojson": circle_geojson(latitude, longitude, radius_km=3),
            "year": YEAR,
            "resolution": "1km",
        },
        headers={**HEADERS, "Accept": "image/tiff"},
        timeout=(10, 90),
    )
    response.raise_for_status()
    body = response.content
    tiff_signatures = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
    if not any(body.startswith(signature) for signature in tiff_signatures):
        raise AssertionError(
            f"/raster did not return a TIFF payload (content-type={response.headers.get('content-type')!r})"
        )
    return {"raster_bytes": len(body), "content_type": response.headers.get("content-type")}


def check_exposure(latitude: float, longitude: float) -> dict:
    result = post_json(
        "/exposure",
        {
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "radius_km": 2,
            "p": 1,
            "year": YEAR,
        },
    )
    total = result.get("total")
    if not isinstance(total, dict):
        raise AssertionError("/exposure returned no total result")
    exposed = require_number(total.get("exposed_population"), "weighted exposed population")
    within = require_number(total.get("population_within"), "population within radius")
    if exposed > within + 1e-6:
        raise AssertionError("weighted exposed population exceeds population within the radius")
    return {"exposed_population": round(exposed, 1), "population_within": round(within, 1)}


def main() -> None:
    results = []
    for name, (latitude, longitude) in CITIES.items():
        results.append(check_city(name, latitude, longitude))
        time.sleep(1.1)
    raster = check_raster(*CITIES["Bengaluru"])
    time.sleep(1.1)
    exposure = check_exposure(*CITIES["Bengaluru"])
    print(json.dumps({"status": "ok", "cities": results, "raster": raster, "exposure": exposure}, indent=2))


if __name__ == "__main__":
    main()
