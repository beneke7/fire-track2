from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cases/calbrix_dash8_flux_replay/prepare_case.py"
SPEC = importlib.util.spec_from_file_location("dash8_flux_replay_preparation", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load flux replay preparation at {SCRIPT}")
replay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replay
SPEC.loader.exec_module(replay)


def _source_manifest(*, npz_sha256: str = "a" * 64) -> dict:
    return {
        **replay.REQUIRED_SOURCE_MANIFEST,
        "source_run_id": "test-native-tank-run",
        "classification": "native_solver_alphaPhi_step_average",
        "source_npz_sha256": npz_sha256,
        "producer_script_path": "audit_native_face_alpha_phi.py",
        "producer_script_sha256": "b" * 64,
        "native_case_path": "/source/case",
        "native_reconciliation": {
            "all_steps_match": True,
            "matched_step_count": 2,
            "face_count": 2,
            "max_abs_rate_error_m3_s": 1e-12,
            "tolerance_m3_s": 1e-9,
            "method": "sum native per-face alphaPhi against native patch aggregate",
            "aggregate_path": "postProcessing/apertureFlux/surfaceFieldValue.dat",
            "aggregate_sha256": "c" * 64,
        },
    }


def _source_arrays() -> dict[str, np.ndarray]:
    return {
        "time_end_s": np.asarray([0.2, 0.6]),
        "delta_t_s": np.asarray([0.2, 0.4]),
        "source_face_bounds_xy_m": np.asarray([[0.0, 0.5, 0.0, 1.0], [0.5, 1.0, 0.0, 1.0]]),
        "source_face_areas_m2": np.asarray([0.5, 0.5]),
        "source_water_volume_rate_m3_s": np.asarray([[0.2, -0.1], [0.4, 0.2]]),
        "source_face_ids": np.asarray([[0, 11], [1, 7]], dtype=np.int64),
    }


def test_source_schema_preserves_signed_native_step_averages() -> None:
    checked = replay.validate_source_arrays(_source_arrays())
    assert checked["time_start_s"].tolist() == pytest.approx([0.0, 0.2])
    assert checked["source_water_volume_rate_m3_s"][0].tolist() == pytest.approx([0.2, -0.1])
    replay.validate_source_manifest(_source_manifest())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda d: d.__setitem__("classification", "interpolated_alpha_U_proxy"),
            "native per-face",
        ),
        (lambda d: d.__setitem__("coordinate_frame", "tank axes, unswapped"), "coordinate_frame"),
        (lambda d: d.__setitem__("source_normal_xyz", [0.0, 0.0, 1.0]), "normals"),
    ],
)
def test_source_manifest_rejects_proxy_wrong_frame_or_wrong_normal(mutate, message: str) -> None:
    manifest = _source_manifest()
    mutate(manifest)
    with pytest.raises(ValueError, match=message):
        replay.validate_source_manifest(manifest)


def test_source_manifest_requires_native_reconciliation_and_hashes() -> None:
    manifest = _source_manifest()
    manifest["native_reconciliation"]["all_steps_match"] = False
    with pytest.raises(ValueError, match="every time step"):
        replay.validate_source_manifest(manifest)
    manifest = _source_manifest()
    manifest["producer_script_sha256"] = "not-a-sha"
    with pytest.raises(ValueError, match="producer_script_sha256"):
        replay.validate_source_manifest(manifest)


def test_conservative_overlap_maps_unequal_faces_and_matches_uniform_total() -> None:
    source_bounds = np.asarray([[0.0, 0.5, 0.0, 1.0], [0.5, 1.0, 0.0, 1.0]], dtype=np.float64)
    source_areas = np.asarray([0.5, 0.5])
    target_bounds = np.asarray(
        [
            [0.0, 0.25, 0.0, 1.0],
            [0.25, 0.75, 0.0, 1.0],
            [0.75, 1.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    target_areas = np.asarray([0.25, 0.5, 0.25])
    source_rates = np.asarray([[0.2, -0.1], [0.4, 0.2]])
    mapped, uniform = replay.map_rates_to_target(
        source_rates, source_bounds, source_areas, target_bounds, target_areas
    )

    assert np.allclose(mapped, [[0.1, 0.05, -0.05], [0.2, 0.3, 0.1]])
    assert np.allclose(uniform, [[0.025, 0.05, 0.025], [0.15, 0.3, 0.15]])
    assert mapped.sum(axis=1).tolist() == pytest.approx(source_rates.sum(axis=1))
    assert np.any(mapped < 0.0)  # signed backflow is not clipped


def test_conservative_overlap_rejects_open_or_area_inconsistent_tiling() -> None:
    source_bounds = np.asarray([[0.0, 1.0, 0.0, 1.0]])
    source_areas = np.asarray([1.0])
    target_bounds = np.asarray([[0.0, 0.9, 0.0, 1.0]])
    with pytest.raises(ValueError, match="fully cover"):
        replay.overlap_matrix(source_bounds, source_areas, target_bounds, np.asarray([0.9]))
    with pytest.raises(ValueError, match="source face areas"):
        replay.overlap_matrix(source_bounds, np.asarray([0.9]), source_bounds, source_areas)


def test_piecewise_constant_rebinning_handles_unequal_steps_and_conserves_volume() -> None:
    source_start = np.asarray([0.0, 0.3, 0.5])
    source_end = np.asarray([0.3, 0.5, 0.9])
    source_values = np.asarray([[1.0, 10.0], [3.0, -1.0], [5.0, 6.0]])
    target_start = np.asarray([0.0, 0.2, 0.6])
    target_end = np.asarray([0.2, 0.6, 0.9])
    rebinned = replay.rebin_step_averages(
        source_start, source_end, source_values, target_start, target_end
    )

    assert np.allclose(rebinned, [[1.0, 10.0], [3.0, 3.5], [5.0, 6.0]])
    source_integral = np.sum(source_values * (source_end - source_start)[:, None], axis=0)
    target_integral = np.sum(rebinned * (target_end - target_start)[:, None], axis=0)
    assert target_integral == pytest.approx(source_integral)


@pytest.mark.parametrize(
    ("starts", "ends"),
    [([0.0], [0.7]), ([0.7], [0.9])],
)
def test_rebin_rejects_time_outside_native_support(starts, ends) -> None:
    with pytest.raises(ValueError, match="exceeds native source support"):
        replay.rebin_step_averages(
            np.asarray([0.0, 0.3]),
            np.asarray([0.3, 0.6]),
            np.ones((2, 1)),
            np.asarray(starts),
            np.asarray(ends),
        )


def test_rebin_rejects_gapped_native_time_intervals() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        replay.rebin_step_averages(
            np.asarray([0.0, 0.31]),
            np.asarray([0.3, 0.6]),
            np.ones((2, 1)),
            np.asarray([0.0]),
            np.asarray([0.2]),
        )


def test_total_rate_replay_has_same_history_but_uneven_profile_adds_momentum() -> None:
    source = _source_arrays()
    target_bounds = np.asarray(
        [[0.0, 0.25, 0.0, 1.0], [0.25, 0.75, 0.0, 1.0], [0.75, 1.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    target_areas = np.asarray([0.25, 0.5, 0.25])
    mapped, uniform = replay.map_rates_to_target(
        source["source_water_volume_rate_m3_s"],
        source["source_face_bounds_xy_m"],
        source["source_face_areas_m2"],
        target_bounds,
        target_areas,
    )
    uneven = replay.replay_diagnostics(mapped, target_areas, source["delta_t_s"])
    even = replay.replay_diagnostics(uniform, target_areas, source["delta_t_s"])
    assert uneven["signed_total_volume_m3"] == pytest.approx(even["signed_total_volume_m3"])
    assert uneven["max_abs_step_total_difference_from_uniform_m3_s"] == pytest.approx(0.0)
    assert uneven["extra_normal_momentum_flux_magnitude_max_N"] >= -1e-10
    assert uneven["extra_normal_momentum_impulse_magnitude_N_s"] > 0.0


def test_target_geometry_uses_its_own_mesh_and_maps_structured_opening(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    (case / "case-inputs.json").write_text(
        '{"source_patch_face_counts":{"dash8Opening":4},'
        '"source_patch_areas_m2":{"dash8Opening":2.0},'
        '"mesh_breaks_m":{"x":[-1.0,0.0,1.0],"y":[-0.5,0.5]},'
        '"mesh_cells_per_segment":{"x":[1,1],"y":[2]}}',
        encoding="utf-8",
    )
    (case / "source_geometry.json").write_text(
        '{"sources":[{"name":"dash8Opening","bounds_m":{"x":[-1.0,1.0],"y":[-0.5,0.5]}}]}',
        encoding="utf-8",
    )
    target = replay.target_rectangles_from_case_inputs(case)
    assert target["bounds_xy_m"].shape == (4, 4)
    assert target["areas_m2"].sum() == pytest.approx(2.0)
    assert target["centers_x_m"].tolist() == pytest.approx([-0.5, 0.5])
    assert target["centers_y_m"].tolist() == pytest.approx([-0.25, 0.25])


def _write_native_target_geometry_case(tmp_path: Path) -> tuple[Path, Path]:
    case = tmp_path / "native-case"
    poly_mesh = case / "constant/polyMesh"
    poly_mesh.mkdir(parents=True)
    for name in ("boundary", "faces", "owner", "points"):
        (poly_mesh / name).write_text(f"fixture {name}\n", encoding="utf-8")
    (case / "case-inputs.json").write_text(
        json.dumps(
            {
                "source_patch_face_counts": {"dash8Opening": 4},
                "source_patch_areas_m2": {"dash8Opening": 2.0},
                "mesh_cells_expected": 4,
            }
        ),
        encoding="utf-8",
    )
    # Deliberately shuffled. Runtime order is the x-major/y-minor center grid.
    rectangles = [
        [0.0, 1.0, 0.0, 0.5],
        [-1.0, 0.0, -0.5, 0.0],
        [0.0, 1.0, -0.5, 0.0],
        [-1.0, 0.0, 0.0, 0.5],
    ]
    areas = [0.5] * 4
    centers = [
        [0.5, 0.25, 0.0],
        [-0.5, -0.25, 0.0],
        [0.5, -0.25, 0.0],
        [-0.5, 0.25, 0.0],
    ]
    ids = [[2, 42, 3], [0, 40, 1], [1, 41, 2], [3, 43, 0]]
    geometry = {
        "schema": "dash8-native-target-face-rectangles-v1",
        "case_path": str(case.resolve()),
        "source_patch": "dash8Opening",
        "mesh_cells_expected": 4,
        "patch_face_count": 4,
        "grid_shape_x_by_y": [2, 2],
        "bounds_xy_m": rectangles,
        "areas_m2": areas,
        "centers_xyz_m": centers,
        "area_vectors_m2": [[0.0, 0.0, 0.5]] * 4,
        "face_ids": ids,
        "x_centers_m": [-0.5, 0.5],
        "y_centers_m": [-0.25, 0.25],
        "provenance": {
            f"{name}_sha256": replay.sha256_file(poly_mesh / name)
            for name in ("boundary", "faces", "owner", "points")
        },
    }
    geometry_path = tmp_path / "native-target-geometry.json"
    geometry_path.write_text(json.dumps(geometry), encoding="utf-8")
    return case, geometry_path


def test_native_target_geometry_reconciles_mesh_and_reorders_exact_rectangles(
    tmp_path: Path,
) -> None:
    case, geometry_path = _write_native_target_geometry_case(tmp_path)
    target = replay.target_rectangles_from_native_geometry(case, geometry_path)
    assert target["bounds_xy_m"].tolist() == [
        [-1.0, 0.0, -0.5, 0.0],
        [-1.0, 0.0, 0.0, 0.5],
        [0.0, 1.0, -0.5, 0.0],
        [0.0, 1.0, 0.0, 0.5],
    ]
    assert target["areas_m2"].sum() == pytest.approx(2.0)
    assert target["face_ids"][:, 0].tolist() == [0, 3, 1, 2]
    assert target["centers_x_m"].tolist() == pytest.approx([-0.5, 0.5])
    assert target["centers_y_m"].tolist() == pytest.approx([-0.25, 0.25])


def test_native_target_geometry_rejects_changed_mesh_or_incomplete_grid(tmp_path: Path) -> None:
    case, geometry_path = _write_native_target_geometry_case(tmp_path)
    (case / "constant/polyMesh/faces").write_text("changed faces\n", encoding="utf-8")
    with pytest.raises(ValueError, match="faces hash differs"):
        replay.target_rectangles_from_native_geometry(case, geometry_path)

    case, geometry_path = _write_native_target_geometry_case(tmp_path / "incomplete")
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    geometry["bounds_xy_m"][0] = geometry["bounds_xy_m"][2]
    geometry["centers_xyz_m"][0] = geometry["centers_xyz_m"][2]
    geometry_path.write_text(json.dumps(geometry), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate native target x/y face center"):
        replay.target_rectangles_from_native_geometry(case, geometry_path)


def test_interval_boundary_code_references_native_overlap_integration_and_kepsilon() -> None:
    vector_code = replay.coded_replay_boundary(field="U")
    k_code = replay.coded_replay_boundary(field="k")
    eps_code = replay.coded_replay_boundary(field="epsilon")
    assert "this->db().time().deltaTValue()" in vector_code
    assert "min(tEnd, table.endTimes[stepj])" in vector_code
    assert "volume/(deltaT*actualAreas[facei])" in vector_code
    assert "max(scalar(0)," not in vector_code
    assert "intensity = 0.05" in k_code and "lengthScale = 0.05" in k_code
    assert "kMean = max" in k_code
    assert "epsilonMean = max" in eps_code


def test_patch_replacement_keeps_generated_entries_inside_named_boundary_patch() -> None:
    original = """boundaryField
{
    dash8Opening
    {
        type fixedValue;
        value uniform (0 0 0);
    }
    farfield
    {
        type zeroGradient;
    }
}
"""
    replaced = replay._replace_patch_dictionary(
        original, "dash8Opening", replay.coded_replay_boundary(field="U")
    )
    assert "    dash8Opening\n    {\n        type codedFixedValue;" in replaced
    assert "    farfield\n    {\n        type zeroGradient;" in replaced
    assert replaced.count("dash8Opening") == 1


def test_prepare_pair_changes_only_replay_fields_and_records_matched_inputs(tmp_path: Path) -> None:
    base = tmp_path / "base"
    for relative in (
        "0",
        "constant/polyMesh",
        "system",
    ):
        (base / relative).mkdir(parents=True, exist_ok=True)
    inputs = {
        "source_patch_face_counts": {"dash8Opening": 4},
        "source_patch_areas_m2": {"dash8Opening": 2.0},
        "mesh_breaks_m": {"x": [-1.0, 0.0, 1.0], "y": [-0.5, 0.5]},
        "mesh_cells_per_segment": {"x": [1, 1], "y": [2]},
        "time_controls": {"end_s": 1.5},
        "mesh_cells_expected": 4,
        "analytic_expected_mass_kg": 12.0,
        "analytic_expected_mass_by_source_kg": {"dash8Opening": 12.0},
        "source_histories": {"dash8": {"origin": "Fig4 digitization"}},
    }
    (base / "case-inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    (base / "source_geometry.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "name": "dash8Opening",
                        "bounds_m": {"x": [-1.0, 1.0], "y": [-0.5, 0.5]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (base / "constant/polyMesh/boundary").write_text("patch dash8Opening\n", encoding="utf-8")
    (base / "system/controlDict").write_text(
        "endTime 1.5;\nmaxDeltaT 0.1;\nwriteInterval 0.1;\n", encoding="utf-8"
    )
    (base / "system/fvSchemes").write_text("fvSchemes {}\n", encoding="utf-8")
    (base / "system/fvSolution").write_text("fvSolution {}\n", encoding="utf-8")
    (base / "constant/transportProperties").write_text("transportProperties {}\n", encoding="utf-8")
    (base / "constant/turbulenceProperties").write_text(
        "turbulenceProperties {}\n", encoding="utf-8"
    )
    for field, content in {
        "U": "internalField uniform (0 0 0);\nboundaryField\n{\ndash8Opening\n{ type fixedValue; value uniform (0 0 0); }\n}\n",
        "alpha.water": "internalField uniform 0;\nboundaryField\n{\ndash8Opening\n{ type fixedValue; value uniform 1; }\n}\n",
        "k": "internalField uniform 1;\nboundaryField\n{\ndash8Opening\n{ type fixedValue; value uniform 1; }\n}\n",
        "epsilon": "internalField uniform 1;\nboundaryField\n{\ndash8Opening\n{ type fixedValue; value uniform 1; }\n}\n",
    }.items():
        (base / "0" / field).write_text(content, encoding="utf-8")

    source_npz = tmp_path / "source.npz"
    source_arrays = _source_arrays()
    source_arrays["source_face_bounds_xy_m"] = np.asarray(
        [[-1.0, 0.0, -0.5, 0.5], [0.0, 1.0, -0.5, 0.5]]
    )
    source_arrays["source_face_areas_m2"] = np.asarray([1.0, 1.0])
    np.savez(source_npz, **source_arrays)
    source_manifest = tmp_path / "source.json"
    source_manifest.write_text(
        json.dumps(_source_manifest(npz_sha256=replay.sha256_file(source_npz))), encoding="utf-8"
    )
    output = tmp_path / "prepared"
    record = replay.prepare_pair(
        base_case=base,
        source_npz=source_npz,
        source_manifest_path=source_manifest,
        output_dir=output,
        horizon_s=0.6,
        max_delta_t_s=0.00035,
    )

    uniform = Path(record["uniform_candidate"]["case_dir"])
    uneven = Path(record["uneven_candidate"]["case_dir"])
    assert record["target_faces"] == 4
    assert record["target_mesh_cells"] == 4
    assert record["uniform_vs_uneven_total_rate_max_abs_difference_m3_s"] == pytest.approx(0.0)
    assert (uniform / "system/controlDict").read_text().startswith("endTime 0.6;")
    assert "maxDeltaT 0.00035;" in (uniform / "system/controlDict").read_text()
    assert record["max_delta_t_s_override"] == pytest.approx(0.00035)
    assert (uniform / "0/alpha.water").read_bytes() == (base / "0/alpha.water").read_bytes()
    assert (uniform / "0/k").read_bytes() == (uneven / "0/k").read_bytes()
    assert (uniform / "0/epsilon").read_bytes() == (uneven / "0/epsilon").read_bytes()
    assert (uniform / "0/U").read_bytes() == (uneven / "0/U").read_bytes()
    assert (uniform / "system/fvSchemes").read_bytes() == (uneven / "system/fvSchemes").read_bytes()
    assert (uniform / "system/dash8FluxReplayData").read_bytes() != (
        uneven / "system/dash8FluxReplayData"
    ).read_bytes()
    for case in (uniform, uneven):
        assert "type codedFixedValue" in (case / "0/U").read_text()
        u_text = (case / "0/U").read_text()
        assert "dash8Opening\n{\n        type codedFixedValue;" in u_text
        assert "type codedFixedValue" in (case / "0/k").read_text()
        assert "type codedFixedValue" in (case / "0/epsilon").read_text()
        inputs_written = json.loads((case / "case-inputs.json").read_text())
        assert "source_histories" not in inputs_written
        assert "digitized_fig4_reference_not_replay" in inputs_written
        assert inputs_written["time_controls"]["end_s"] == pytest.approx(0.6)
        assert inputs_written["inlet_profile"]["turbulence_intensity_assumption"] == 0.05
        assert inputs_written["inlet_profile"]["turbulence_length_scale_assumption_m"] == 0.05
    assert record["source_npz_sha256"] == replay.sha256_file(output / "native-tank-flux-input.npz")
    assert record["repository"]["revision"]
    assert record["code_provenance"]["generator_sha256"] == replay.sha256_file(SCRIPT)
    assert set(record["uniform_candidate"]["case_input_hashes"]) == set(
        record["uneven_candidate"]["case_input_hashes"]
    )
    assert record["paired_case_hash_differences"] == [
        "case-inputs.json",
        "system/dash8FluxReplayData",
    ]
