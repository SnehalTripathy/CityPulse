from __future__ import annotations

import math

import pandas as pd


def build_zone_coverage_grid(
    occupied_cells: pd.DataFrame,
    city_latitude: float,
    city_longitude: float,
    radius_km: float = 25.0,
    grid_km: float = 5.0,
) -> pd.DataFrame:
    """Build a local returned-station coverage grid, including empty sample cells.

    Empty cells mean that the current limited OpenAQ nearby-location response
    returned no fixed station in that cell. They are not proof that a location
    has no monitoring infrastructure.
    """
    columns = [
        "grid_x", "grid_y", "latitude", "longitude", "station_count",
        "station_names", "coverage_status", "cell_centre_distance_km",
    ]
    station_lookup = {}
    if not occupied_cells.empty and {"grid_x", "grid_y", "station_count"}.issubset(occupied_cells.columns):
        for row in occupied_cells.to_dict(orient="records"):
            station_lookup[(int(row["grid_x"]), int(row["grid_y"]))] = row

    half_range = int(math.ceil(float(radius_km) / float(grid_km)))
    lon_scale = max(1.0, 111.32 * math.cos(math.radians(city_latitude)))
    rows = []
    for grid_x in range(-half_range - 1, half_range + 1):
        for grid_y in range(-half_range - 1, half_range + 1):
            offset_x = (grid_x + 0.5) * grid_km
            offset_y = (grid_y + 0.5) * grid_km
            distance = math.hypot(offset_x, offset_y)
            if distance > radius_km + grid_km * math.sqrt(2) / 2:
                continue
            cell = station_lookup.get((grid_x, grid_y), {})
            count = int(cell.get("station_count", 0))
            rows.append({
                "grid_x": grid_x,
                "grid_y": grid_y,
                "latitude": city_latitude + offset_y / 111.32,
                "longitude": city_longitude + offset_x / lon_scale,
                "station_count": count,
                "station_names": cell.get("station_names", ""),
                "coverage_status": "Returned fixed station" if count else "No fixed station returned in sample",
                "cell_centre_distance_km": round(distance, 2),
            })
    return pd.DataFrame(rows, columns=columns)
