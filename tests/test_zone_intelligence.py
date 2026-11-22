import pandas as pd

from analytics.zone_intelligence import build_zone_coverage, detect_observed_hotspot_clusters


def _air_frame():
    rows = []
    for index, value in enumerate([10, 20, 30, 40, 50, 60]):
        rows.append({
            "location_id": index + 1,
            "station": f"Station {index + 1}",
            "latitude": 12.0 + (0.002 if index >= 4 else index * 0.03),
            "longitude": 77.0 + (0.002 if index >= 4 else index * 0.03),
            "distance_m": 1000 + index * 1000,
            "parameter": "pm25",
            "unit": "µg/m³",
            "value": value,
            "datetime_utc": "2026-11-22T17:00:00Z",
        })
    return pd.DataFrame(rows)


def test_zone_coverage_reports_returned_stations_and_freshness():
    summary, inventory, grid = build_zone_coverage(
        _air_frame(),
        12.0,
        77.0,
        now=pd.Timestamp("2026-11-22T18:00:00Z"),
    )
    assert summary["station_count"] == 6
    assert summary["geocoded_station_count"] == 6
    assert summary["fresh_stations"] == 6
    assert summary["occupied_grid_cells"] >= 2
    assert len(inventory) == 6
    assert not grid.empty


def test_hotspot_requires_sufficient_recent_stations_and_neighbour_cluster():
    status, clusters, sample_count = detect_observed_hotspot_clusters(
        _air_frame(),
        "pm25",
        "µg/m³",
        now=pd.Timestamp("2026-11-22T18:00:00Z"),
    )
    assert sample_count == 6
    assert status == "cluster_found"
    assert len(clusters) == 2
    assert clusters["cluster"].nunique() == 1

    status, clusters, sample_count = detect_observed_hotspot_clusters(
        _air_frame().head(4),
        "pm25",
        "µg/m³",
        now=pd.Timestamp("2026-11-22T18:00:00Z"),
    )
    assert status == "insufficient_station_density"
    assert clusters.empty


def test_uniform_station_values_do_not_create_a_relative_cluster():
    air = _air_frame()
    air["value"] = 25
    status, clusters, sample_count = detect_observed_hotspot_clusters(
        air, "pm25", "µg/m³", now=pd.Timestamp("2026-11-22T18:00:00Z")
    )
    assert sample_count == 6
    assert status == "no_cluster"
    assert clusters.empty



def test_mobile_sensors_do_not_inflate_fixed_station_coverage_grid():
    air = _air_frame()
    air["is_mobile"] = False
    air.loc[air.index[-1], "is_mobile"] = True
    summary, inventory, grid = build_zone_coverage(
        air, 12.0, 77.0, now=pd.Timestamp("2026-11-22T18:00:00Z")
    )
    assert summary["station_count"] == 6
    assert summary["fixed_stations"] == 5
    assert summary["mobile_stations"] == 1
    assert summary["geocoded_station_count"] == 5
    assert len(inventory) == 6
    assert len(grid) >= 1



def test_future_dated_station_is_not_counted_as_fresh():
    air = _air_frame().head(1).copy()
    air["datetime_utc"] = "2026-11-23T05:00:00Z"
    summary, inventory, grid = build_zone_coverage(
        air, 12.0, 77.0, now=pd.Timestamp("2026-11-22T18:00:00Z")
    )
    assert summary["fresh_stations"] == 0
    assert summary["future_timestamp_stations"] == 1
    assert inventory.iloc[0]["freshness"] == "Future timestamp"
    assert pd.isna(inventory.iloc[0]["age_hours"])
    assert grid.empty
