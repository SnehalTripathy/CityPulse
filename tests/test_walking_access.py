import pandas as pd

from ingestion.geo_layers import calculate_walking_access_from_osm


def test_walking_access_uses_osm_path_network_and_marks_disconnected_park():
    greens = pd.DataFrame([
        {"name":"Connected Park","category":"park","latitude":12.0,"longitude":77.002,"distance_km":0.22},
        {"name":"Isolated Park","category":"garden","latitude":12.006,"longitude":77.002,"distance_km":0.67},
    ])
    elements = [
        {"type":"node","id":1,"lat":12.0,"lon":77.0},
        {"type":"node","id":2,"lat":12.0,"lon":77.001},
        {"type":"node","id":3,"lat":12.0,"lon":77.002},
        {"type":"node","id":4,"lat":12.005,"lon":77.002},
        {"type":"node","id":5,"lat":12.006,"lon":77.002},
        {"type":"way","id":11,"nodes":[1,2,3],"tags":{"highway":"footway"}},
        {"type":"way","id":12,"nodes":[3,4],"tags":{"highway":"service","foot":"no"}},
        {"type":"way","id":13,"nodes":[4,5],"tags":{"highway":"footway"}},
        {"type":"way","id":14,"nodes":[3,4],"tags":{"highway":"residential","access":"private"}},
    ]
    access, summary = calculate_walking_access_from_osm(
        12.0,77.0,greens,elements,maximum_snap_distance_m=500
    )
    connected = access.loc[access["name"]=="Connected Park"].iloc[0]
    isolated = access.loc[access["name"]=="Isolated Park"].iloc[0]
    assert summary["status"] == "ready"
    assert summary["walkable_ways"] == 2
    assert connected["access_status"] == "Estimated walk-network route"
    assert connected["walking_network_km"] >= connected["straight_line_km"]
    assert connected["estimated_walk_minutes"] > 0
    assert isolated["walking_network_km"] is None
    assert isolated["access_status"] == "No connected route in returned network sample"


def test_walking_access_reports_missing_network_without_claiming_inaccessibility():
    greens = pd.DataFrame([
        {"name":"Park","category":"park","latitude":12.0,"longitude":77.002,"distance_km":0.22}
    ])
    access, summary = calculate_walking_access_from_osm(12.0,77.0,greens,[])
    assert summary["status"] == "no_walkable_ways"
    assert access.iloc[0]["walking_network_km"] is None
    assert access.iloc[0]["access_status"] == "No walkable network returned"
