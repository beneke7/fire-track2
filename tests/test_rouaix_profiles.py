from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from scripts.analyze_rouaix_profiles import _write_outputs, profile_rouaix_snapshot


def toy_snapshot() -> dict:
    # Nonzero global IDs ensure source seeding is based on the explicit native
    # owner list, not a guessed cell-ID convention. Edge (7, 42) represents a
    # merged face join across an MPI rank boundary.
    return {
        "cell_global_ids": np.asarray([7, 19, 42, 105], dtype=np.int64),
        "time_name": "0.250",
        "time_value_s": 0.25,
        "source_patch": "nozzleOutlet",
        "alpha_water": np.asarray([0.9, 0.1, 0.9, 0.95]),
        "cell_centres_xyz_m": np.asarray(
            [
                [0.5, -1.5, -0.1],
                [0.75, -2.5, 0.15],
                [1.0 + 5e-10, -4.5, 0.0],
                [1.5, -8.5, 0.0],
            ]
        ),
        "cell_bounds_minmax_xyz_m": np.asarray(
            [
                [0.4, -2.0, -0.2, 0.6, -1.0, 0.0],
                [0.7, -3.0, 0.05, 0.8, -2.0, 0.2],
                [0.9, -5.0, -0.1, 1.1, -4.0, 0.1],
                [1.4, -9.0, -0.25, 1.6, -8.0, 0.25],
            ]
        ),
        "edges_native_global_ids": np.asarray([[7, 42]], dtype=np.int64),
        "source_owner_global_ids": np.asarray([7], dtype=np.int64),
    }


def test_full_cloud_keeps_detached_lobe_and_reports_full_signed_span() -> None:
    result = profile_rouaix_snapshot(
        toy_snapshot(),
        x_station_edges_m=[0.0, 1.0, 2.0, 3.0],
        x_origin_m=0.5,
        source_plane_y0_m=0.5,
        station_tolerance_m=1e-9,
    )

    first = result["stations"][0]["full_cloud_alpha_ge_0p1"]
    assert first["selected_cell_count"] == 2  # alpha == 0.1 is included
    assert first["minimum_native_y_low_m"] == -3.0
    assert first["native_y_low_minus_source_plane_m"] == -3.5
    assert first["penetration_down_positive_m"] == 3.5
    assert first["full_spanwise_width_m"] == pytest.approx(0.4)
    assert first["minimum_signed_z_low_m"] == -0.2
    assert first["maximum_signed_z_high_m"] == 0.2
    assert first["full_spanwise_width_over_D"] == pytest.approx(1.0)
    assert result["coordinate_frame"]["y_axis"] == "native mesh y; signed coordinates are retained"
    assert result["time_value_s"] == 0.25
    assert result["source_patch"] == "nozzleOutlet"
    assert result["paper_detector_equivalence"] is False


def test_core_is_global_face_connected_to_explicit_source_owners_before_binning() -> None:
    result = profile_rouaix_snapshot(
        toy_snapshot(),
        x_station_edges_m=[0.0, 1.0, 2.0, 3.0],
        x_origin_m=0.5,
        source_plane_y0_m=0.5,
        station_tolerance_m=1e-9,
    )

    connectivity = result["connectivity"]
    assert connectivity["selected_source_owner_cell_count"] == 1
    assert connectivity["selected_source_owner_component_count"] == 1
    assert connectivity["all_core_component_count"] == 2
    assert connectivity["source_connected_core_cell_count"] == 2
    assert connectivity["no_source_seed_fallback"] is True

    # The center just above x=1 is snapped within tolerance to the internal
    # boundary, then assigned to the higher-x bin. The detached 0.95 island
    # remains in the full cloud envelope but is absent from the connected core.
    second = result["stations"][1]
    assert second["x_station_low_m"] == 1.0
    assert second["source_connected_core_alpha_ge_0p9"]["selected_cell_count"] == 1
    assert second["source_connected_core_alpha_ge_0p9"]["penetration_down_positive_m"] == 5.5
    assert second["full_cloud_alpha_ge_0p1"]["selected_cell_count"] == 2
    assert second["full_cloud_alpha_ge_0p1"]["penetration_down_positive_m"] == 9.5
    assert result["stations"][2]["full_cloud_alpha_ge_0p1"] is None
    assert result["stations"][2]["source_connected_core_alpha_ge_0p9"] is None


def test_missing_source_owners_and_invalid_raw_fields_are_rejected() -> None:
    snapshot = toy_snapshot()
    snapshot["source_owner_global_ids"] = np.asarray([], dtype=np.int64)
    with pytest.raises(ValueError, match="source_owner_global_ids are required"):
        profile_rouaix_snapshot(
            snapshot,
            x_station_edges_m=[0.0, 1.0],
            x_origin_m=0.0,
            source_plane_y0_m=0.0,
        )

    snapshot = toy_snapshot()
    snapshot["alpha_water"][0] = np.nan
    with pytest.raises(ValueError, match="alpha_water must contain only finite values"):
        profile_rouaix_snapshot(
            snapshot,
            x_station_edges_m=[0.0, 1.0],
            x_origin_m=0.0,
            source_plane_y0_m=0.0,
        )

    snapshot = toy_snapshot()
    snapshot["alpha_water"][0] = 1.00001
    with pytest.raises(ValueError, match="alpha_water must be in \\[0, 1\\]"):
        profile_rouaix_snapshot(
            snapshot,
            x_station_edges_m=[0.0, 1.0],
            x_origin_m=0.0,
            source_plane_y0_m=0.0,
        )


def test_query_edges_require_positive_width_after_declared_tolerance() -> None:
    with pytest.raises(ValueError, match="strictly increasing edges"):
        profile_rouaix_snapshot(
            toy_snapshot(),
            x_station_edges_m=[0.0, 1.0, 1.0],
            x_origin_m=0.0,
            source_plane_y0_m=0.0,
        )
    with pytest.raises(ValueError, match="more than twice the tolerance"):
        profile_rouaix_snapshot(
            toy_snapshot(),
            x_station_edges_m=[0.0, 1e-9, 1.0],
            x_origin_m=0.0,
            source_plane_y0_m=0.0,
            station_tolerance_m=1e-9,
        )


def test_exact_field_time_name_takes_priority_over_rounded_export_metadata() -> None:
    snapshot = toy_snapshot()
    snapshot["time_name"] = "3.0735945651412"
    snapshot["time_value_s"] = 3.07359456514
    result = profile_rouaix_snapshot(
        snapshot,
        x_station_edges_m=[0.0, 1.0],
        x_origin_m=0.5,
        source_plane_y0_m=0.5,
    )
    assert result["time_value_s"] == 3.0735945651412
    assert result["export_metadata_time_value_s"] == 3.07359456514
    assert result["time_name"] == "3.0735945651412"


def test_json_csv_and_multisnapshot_summary_preserve_times_without_stationarity_claim(
    tmp_path,
) -> None:
    first_snapshot = toy_snapshot()
    second_snapshot = toy_snapshot()
    second_snapshot["time_name"] = "0.500"
    second_snapshot["time_value_s"] = 0.5
    inputs = {
        "x_station_edges_m": [0.0, 1.0, 2.0, 3.0],
        "x_origin_m": 0.5,
        "source_plane_y0_m": 0.5,
        "station_tolerance_m": 1e-9,
    }
    runs = [
        {
            "export_dir": "snapshot-a",
            "geometry_observer_inputs": inputs,
            "profile": profile_rouaix_snapshot(first_snapshot, **inputs),
        },
        {
            "export_dir": "snapshot-b",
            "geometry_observer_inputs": inputs,
            "profile": profile_rouaix_snapshot(second_snapshot, **inputs),
        },
    ]
    output_dir = tmp_path / "profiles"
    _write_outputs(output_dir, runs, snapshot_summary=True)

    report = json.loads((output_dir / "profiles.json").read_text(encoding="utf-8"))
    assert [run["profile"]["time_value_s"] for run in report["runs"]] == [0.25, 0.5]
    assert "stationarity is not asserted" in report["snapshot_summary"]["interpretation"]
    with (output_dir / "profiles.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert {row["source_patch"] for row in rows} == {"nozzleOutlet"}
    assert {row["time_value_s"] for row in rows} == {"0.25", "0.5"}
