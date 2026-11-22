import pandas as pd

from analytics.spatial_interpolation import interpolate_station_surface


def _station_grid():
    rows = []
    coords = [
        (12.000, 77.000), (12.000, 77.030), (12.030, 77.000),
        (12.030, 77.030), (12.015, 77.010), (12.015, 77.020),
        (12.025, 77.015),
    ]
    for index, (lat, lon) in enumerate(coords):
        rows.append({
            "location_id": index + 1,
            "parameter": "pm25",
            "unit": "µg/m³",
            "value": 10 + index * 5,
            "datetime_utc": "2026-11-22T17:00:00Z",
            "latitude": lat,
            "longitude": lon,
        })
    return pd.DataFrame(rows)


def test_surface_is_generated_only_with_recent_comparable_stations():
    status, surface, details = interpolate_station_surface(
        _station_grid(), "pm2.5", "µg/m³",
        now=pd.Timestamp("2026-11-22T18:00:00Z"),
        minimum_stations=6,
        grid_spacing_km=0.5,
    )
    assert status == "ready"
    assert len(surface) > 0
    assert surface["estimated_value"].between(10, 40).all()
    assert surface["nearest_station_km"].max() <= 3.0
    assert details["station_count"] == 7
    assert details["leave_one_out_mae"] is not None
    assert details["median_baseline_mae"] is not None
    assert details["idw_beats_baseline"] is True


def test_surface_is_withheld_when_station_coverage_is_sparse():
    status, surface, details = interpolate_station_surface(
        _station_grid().head(4), "pm25", "µg/m³",
        now=pd.Timestamp("2026-11-22T18:00:00Z"),
    )
    assert status == "insufficient_station_density"
    assert surface.empty
    assert details["station_count"] == 4


def test_surface_is_withheld_for_stale_or_incompatible_readings():
    air = _station_grid()
    air["datetime_utc"] = "2026-11-20T12:00:00Z"
    status, surface, _ = interpolate_station_surface(
        air, "pm25", "ppm", now=pd.Timestamp("2026-11-22T18:00:00Z")
    )
    assert status == "no_matching_readings"
    assert surface.empty



def test_mobile_stations_are_excluded_from_fixed_station_surface():
    air = _station_grid()
    air["is_mobile"] = False
    air.loc[air.index[-1], "is_mobile"] = True
    status, _, details = interpolate_station_surface(
        air, "pm25", "µg/m³", now=pd.Timestamp("2026-11-22T18:00:00Z")
    )
    assert status == "ready"
    assert details["station_count"] == 6



def test_surface_is_withheld_when_idw_does_not_beat_median_baseline():
    air = _station_grid()
    air["value"] = 25
    status, surface, details = interpolate_station_surface(
        air, "pm25", "µg/m³", now=pd.Timestamp("2026-11-22T18:00:00Z")
    )
    assert status == "failed_cross_validation"
    assert surface.empty
    assert details["idw_beats_baseline"] is False
