import numpy as np

from ingestion.terrain_hydrology import analyze_dem_grid, parse_hydro_features


def test_dem_analysis_finds_relative_low_gentle_terrain_without_claiming_flood_probability():
    height = width = 121
    rows, cols = np.mgrid[0:height, 0:width]
    distance = np.sqrt((rows - 60) ** 2 + (cols - 60) ** 2)
    elevation = 120 + rows * 0.02 + cols * 0.01 - 0.07 * np.maximum(0, 35 - distance)
    frame, summary = analyze_dem_grid(
        elevation,
        (77.0, 12.0, 77.12, 12.12),
        12.06,
        77.06,
    )
    assert summary["status"] == "ready"
    assert summary["valid_cells"] == height * width
    assert summary["sample_points"] <= 1200
    assert "slope_degrees" in frame
    assert "topographic_position_m" in frame
    assert frame["terrain_class"].notna().all()
    assert summary["relative_low_gentle_cells"] > 0


def test_dem_analysis_withholds_tiny_or_empty_grids():
    frame, summary = analyze_dem_grid(
        np.full((10, 10), np.nan),
        (0, 0, 1, 1),
        0.5,
        0.5,
    )
    assert summary["status"] == "insufficient_dem_coverage"
    assert frame.empty


def test_osm_hydro_feature_parser_uses_centres_and_computes_distance():
    frame = parse_hydro_features({
        "elements": [
            {"type": "way", "id": 12, "center": {"lat": 12.1, "lon": 77.1},
             "tags": {"waterway": "stream", "name": "Test Stream"}},
            {"type": "node", "id": 13, "lat": 12.2, "lon": 77.2,
             "tags": {"natural": "water"}},
            {"type": "way", "id": 14, "tags": {"waterway": "river"}},
        ]
    }, 12.0, 77.0)
    assert len(frame) == 2
    assert frame.iloc[0]["name"] == "Test Stream"
    assert frame.iloc[0]["category"] == "stream"
    assert frame["distance_km"].gt(0).all()
