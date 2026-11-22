import pandas as pd

from analytics.quality import coverage_label, validate_observations


def test_quality_audit_flags_missing_units_future_and_implausible_values():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    data = pd.DataFrame([
        {"parameter":"pm25","unit":"µg/m³","value":35,"datetime_utc":"2026-11-22T17:00:00Z","station":"A"},
        {"parameter":"pm25","unit":None,"value":-4,"datetime_utc":"2026-11-22T17:00:00Z","station":"B"},
        {"parameter":"pm10","unit":"µg/m³","value":60,"datetime_utc":"2026-11-23T00:00:00Z","station":"C"},
        {"parameter":"temperature","unit":"°C","value":120,"datetime_utc":"2026-11-22T17:00:00Z","station":"D"},
        {"parameter":"pm10","unit":"µg/m³","value":"bad","datetime_utc":"not-a-time","station":None},
    ])
    result = validate_observations(data, now=now)
    assert result["rows_total"] == 5
    assert result["rows_future"] == 1
    assert result["rows_out_of_range"] == 2
    assert result["rows_invalid"] == 1
    assert result["rows_missing_unit"] == 1
    assert result["rows_missing_station"] == 1
    assert result["status"] == "review"


def test_quality_handles_empty_frame_without_inventing_data():
    result = validate_observations(pd.DataFrame())
    assert result["status"] == "no_data"
    assert result["rows_valid"] == 0


def test_coverage_labels_describe_observable_sample_only():
    assert coverage_label(0, None) == "No eligible station readings"
    assert "limited coverage" in coverage_label(2, 2)
    assert "stale" in coverage_label(1, 30)
