from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/analyze_dash8_detachment.py"
spec = importlib.util.spec_from_file_location("dash8_detachment_analyzer_test_module", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load Dash-8 detachment analyzer at {SCRIPT_PATH}")
detachment = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = detachment
spec.loader.exec_module(detachment)


@pytest.fixture
def toy_cartesian_case() -> tuple[np.ndarray, np.ndarray, dict, dict, dict]:
    centers = np.asarray(
        [(x, 0.5, z) for z in (0.5, 1.5) for x in (0.5, 1.5, 2.5, 3.5)],
        dtype=np.float64,
    )
    widths = np.ones_like(centers)
    source_geometry = {
        "source_plane_z_m": 2.0,
        "sources": [
            {
                "name": "outlet",
                "bounds_m": {"x": [0.0, 2.0], "y": [0.0, 1.0]},
                "area_m2": 2.0,
                "plane_z_m": 2.0,
            }
        ],
    }
    mesh_inputs = {
        "mesh_breaks_m": {"x": [0.0, 4.0], "y": [0.0, 1.0], "z": [0.0, 2.0]},
        "mesh_cells_per_segment": {"x": [4], "y": [1], "z": [2]},
    }
    return centers, widths, source_geometry, {"outlet": 2.0}, mesh_inputs


def test_source_face_inventory_owns_only_cells_inside_rectangle(
    toy_cartesian_case: tuple[np.ndarray, np.ndarray, dict, dict, dict],
) -> None:
    centers, widths, geometry, patch_areas, mesh_inputs = toy_cartesian_case
    source_cells, inventory = detachment.source_face_inventory(
        centers,
        widths,
        geometry,
        patch_areas,
        source_patch_face_counts={"outlet": 2},
        mesh_inputs=mesh_inputs,
        geometry_tolerance_m=1e-10,
    )

    assert np.flatnonzero(source_cells).tolist() == [4, 5]
    assert inventory["native_source_cell_count_union"] == 2
    assert inventory["sources"][0]["face_count_native"] == 2
    assert inventory["sources"][0]["face_area_native_m2"] == pytest.approx(2.0)
    # The next cell begins exactly at the opening's streamwise edge. It shares
    # the edge but no positive area, so it does not own a source face.
    assert centers[6, 0] - widths[6, 0] / 2 == pytest.approx(2.0)
    assert not source_cells[6]


def test_multiple_source_attached_components_and_largest_detached_are_classified(
    toy_cartesian_case: tuple[np.ndarray, np.ndarray, dict, dict, dict],
) -> None:
    centers, widths, geometry, patch_areas, mesh_inputs = toy_cartesian_case
    source_cells, _ = detachment.source_face_inventory(
        centers,
        widths,
        geometry,
        patch_areas,
        source_patch_face_counts={"outlet": 2},
        mesh_inputs=mesh_inputs,
        geometry_tolerance_m=1e-10,
    )
    alpha = np.zeros(len(centers))
    labels = np.full(len(centers), -1, dtype=np.int32)
    velocity = np.zeros((len(centers), 3))
    alpha[4], alpha[5] = 0.2, 0.8
    labels[4], labels[5] = 0, 1
    velocity[4, 0], velocity[5, 0] = 1.0, 3.0
    # Four cells form one larger component wholly outside the source rectangle.
    detached_ids = np.asarray([2, 3, 6, 7])
    alpha[detached_ids] = 0.5
    labels[detached_ids] = 2
    velocity[detached_ids, 0] = 10.0

    result = detachment.classify_source_attachment(
        alpha,
        np.prod(widths, axis=1),
        velocity,
        labels,
        source_cells,
        threshold=0.1,
    )
    assert result["attached_component_count"] == 2
    assert result["detached_component_count"] == 1
    assert result["no_selected_source_cell"] is False
    components = result["components"]
    assert [(row["label"], row["attachment"], row["cell_count"]) for row in components] == [
        (0, "source-attached", 1),
        (1, "source-attached", 1),
        (2, "detached", 4),
    ]
    attached = result["groups"]["source-attached"]
    assert attached["number_mean_component_speed_m_s"] == pytest.approx(2.0)
    assert attached["mass_mean_component_speed_m_s"] == pytest.approx(2.6)
    assert attached["number_mean_component_velocity_m_s"] == pytest.approx([2.0, 0.0, 0.0])
    assert attached["mass_mean_component_velocity_m_s"] == pytest.approx([2.6, 0.0, 0.0])
    assert attached["diameter_bins"]["0p1_to_1_m"]["component_count"] == 1
    assert attached["diameter_bins"]["1_to_10_m"]["component_count"] == 1
    detached = result["groups"]["detached"]
    assert detached["component_count"] == 1
    assert detached["total_liquid_mass_kg"] == pytest.approx(2000.0)
    assert detached["diameter_bins"]["1_to_10_m"]["total_liquid_mass_kg"] == pytest.approx(2000.0)


def test_no_selected_source_cell_and_zero_water_are_valid_detached_outcomes(
    toy_cartesian_case: tuple[np.ndarray, np.ndarray, dict, dict, dict],
) -> None:
    centers, widths, geometry, patch_areas, mesh_inputs = toy_cartesian_case
    source_cells, _ = detachment.source_face_inventory(
        centers,
        widths,
        geometry,
        patch_areas,
        source_patch_face_counts={"outlet": 2},
        mesh_inputs=mesh_inputs,
        geometry_tolerance_m=1e-10,
    )
    alpha = np.zeros(len(centers))
    labels = np.full(len(centers), -1, dtype=np.int32)
    velocity = np.zeros((len(centers), 3))
    alpha[[2, 3]] = 0.5
    labels[[2, 3]] = 0
    alpha[[4, 5]] = 0.0

    detached = detachment.classify_source_attachment(
        alpha, np.prod(widths, axis=1), velocity, labels, source_cells, 0.1
    )
    assert detached["no_selected_source_cell"] is True
    assert detached["attached_component_count"] == 0
    assert detached["detached_component_count"] == 1

    empty = detachment.classify_source_attachment(
        np.zeros(len(centers)),
        np.prod(widths, axis=1),
        velocity,
        np.full(len(centers), -1, dtype=np.int32),
        source_cells,
        0.9,
    )
    assert empty["selected_native_cell_count"] == 0
    assert empty["selected_liquid_mass_kg"] == 0.0
    assert empty["component_count"] == 0
    assert (
        empty["groups"]["source-attached"]["diameter_bins"]["below_0p04_m"]["component_count"] == 0
    )

    roundoff_alpha = np.zeros(len(centers))
    roundoff_alpha[0] = -1e-18
    roundoff = detachment.classify_source_attachment(
        roundoff_alpha,
        np.prod(widths, axis=1),
        velocity,
        np.full(len(centers), -1, dtype=np.int32),
        source_cells,
        0.9,
    )
    assert roundoff["alpha_field_bounds"]["native_minimum"] == -1e-18
    assert roundoff["alpha_field_bounds"]["native_values_modified"] is False


@pytest.mark.parametrize(
    ("diameter", "expected"),
    [
        (0.039, "below_0p04_m"),
        (0.04, "0p04_to_0p1_m"),
        (0.1, "0p1_to_1_m"),
        (1.0, "1_to_10_m"),
        (10.0, "1_to_10_m"),
        (10.001, "above_10_m"),
    ],
)
def test_spherical_equivalent_diameter_bins_have_explicit_edges(
    diameter: float, expected: str
) -> None:
    assert detachment.diameter_bin(diameter) == expected


def test_malformed_source_area_and_edge_cut_are_rejected(
    toy_cartesian_case: tuple[np.ndarray, np.ndarray, dict, dict, dict],
) -> None:
    centers, widths, geometry, patch_areas, mesh_inputs = toy_cartesian_case
    wrong_area = {"outlet": 1.5}
    with pytest.raises(ValueError, match="patch area disagrees"):
        detachment.source_face_inventory(
            centers,
            widths,
            geometry,
            wrong_area,
            source_patch_face_counts={"outlet": 2},
            mesh_inputs=mesh_inputs,
            geometry_tolerance_m=1e-10,
        )

    cut_geometry = {
        "source_plane_z_m": 2.0,
        "sources": [
            {
                "name": "outlet",
                "bounds_m": {"x": [0.0, 1.5], "y": [0.0, 1.0]},
                "area_m2": 1.5,
                "plane_z_m": 2.0,
            }
        ],
    }
    with pytest.raises(ValueError, match="cuts through a native Cartesian cell face"):
        detachment.source_face_inventory(
            centers,
            widths,
            cut_geometry,
            {"outlet": 1.5},
            source_patch_face_counts={"outlet": 2},
            geometry_tolerance_m=1e-10,
        )


def test_analysis_refuses_an_existing_output_directory(tmp_path: Path) -> None:
    existing = tmp_path / "preserve-me"
    existing.mkdir()
    (existing / "sentinel").write_text("unchanged")
    with pytest.raises(FileExistsError, match="preserving it"):
        detachment.analyze(tmp_path / "no-run-here", existing)
    assert (existing / "sentinel").read_text() == "unchanged"


def test_report_case_directory_resolves_hashed_native_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory = tmp_path / "runner-bundle"
    case_directory = run_directory / "case"
    processor_time = case_directory / "processor0" / "1.000000"
    processor_time.mkdir(parents=True)
    (processor_time / "alpha.water").write_bytes(b"native-alpha-bytes")
    (processor_time / "U").write_bytes(b"native-velocity-bytes")
    case_inputs = {
        "case_id": "test-runner-bundle-provenance",
        "mesh_cells_expected": 1,
        "ranks": 1,
        "mesh_breaks_m": {axis: [0.0, 1.0] for axis in "xyz"},
        "mesh_widths_by_segment_m": {axis: [1.0] for axis in "xyz"},
        "source_patch_areas_m2": {"opening": 1.0},
        "source_patch_face_counts": {"opening": 1},
        "source_geometry": {
            "source_plane_z_m": 1.0,
            "sources": [
                {
                    "name": "opening",
                    "bounds_m": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
                    "area_m2": 1.0,
                    "plane_z_m": 1.0,
                }
            ],
        },
    }
    (case_directory / "case-inputs.json").write_text(json.dumps(case_inputs))

    reader_case_directories: list[Path] = []

    def read_synthetic_snapshot(
        reader_case: Path, time_s: float, reader_view: Path
    ) -> tuple[dict, dict]:
        reader_case_directories.append(reader_case)
        return (
            {
                "time_s": time_s,
                "centers_m": np.asarray([[0.5, 0.5, 0.5]], dtype=np.float32),
                "alpha_water": np.asarray([0.5], dtype=np.float32),
                "velocity_m_s": np.asarray([[1.0, 0.0, 0.0]], dtype=np.float32),
            },
            {"output_array_precision": {"mesh_points": ["float"]}},
        )

    monkeypatch.setattr(detachment, "_read_native_snapshot", read_synthetic_snapshot)
    report = detachment.analyze(run_directory, tmp_path / "analysis")

    recorded_case = Path(report["case_directory"])
    assert report["run_directory"] == str(run_directory.resolve())
    assert recorded_case == case_directory.resolve()
    assert recorded_case != Path(report["run_directory"])
    assert reader_case_directories == [recorded_case]
    rows = report["input_hashes"]["native_field_files"]["fields"]
    assert {row["field"] for row in rows} == {"alpha.water", "U"}
    for row in rows:
        native_path = recorded_case / row["relative_path"]
        assert native_path.is_file()
        assert hashlib.sha256(native_path.read_bytes()).hexdigest() == row["sha256"]
