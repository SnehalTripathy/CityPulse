import pandas as pd

from analytics.zone_grid import build_zone_coverage_grid


def test_coverage_grid_includes_empty_sample_cells_without_claiming_no_station_exists():
    occupied = pd.DataFrame([
        {"grid_x":0,"grid_y":0,"station_count":2,"station_names":"A, B"},
        {"grid_x":1,"grid_y":0,"station_count":1,"station_names":"C"},
    ])
    grid = build_zone_coverage_grid(occupied, 12.0, 77.0, radius_km=10, grid_km=5)
    assert not grid.empty
    returned = grid.loc[grid["coverage_status"] == "Returned fixed station"]
    empty = grid.loc[grid["coverage_status"] == "No fixed station returned in sample"]
    assert len(returned) == 2
    assert not empty.empty
    assert set(returned["station_count"]) == {1, 2}
    assert (empty["station_count"] == 0).all()
    assert grid["cell_centre_distance_km"].max() <= 10 + 5 * (2 ** 0.5) / 2
