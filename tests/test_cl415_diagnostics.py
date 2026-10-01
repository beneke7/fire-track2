"""Independent synthetic geometry and conservation checks for the CL415 probe."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


analysis = module("analyze_cl415_case")
runner = module("run_cl415_case")


def test_cartesian_face_pairs_preserve_reader_order_and_point_contacts():
    centers = np.array([[1, 1, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    owner, neighbour = analysis.structured_face_pairs(centers, np.ones_like(centers))
    pairs = {frozenset((a, b)) for a, b in zip(owner, neighbour, strict=True)}
    assert pairs == {frozenset(p) for p in ((1, 2), (3, 0), (1, 3), (2, 0))}
    labels = analysis.label_liquid_structures([1, 1, 0, 0], owner, neighbour, 0.9)
    assert labels.tolist() == [0, 1, -1, -1]
    with pytest.raises(ValueError, match="complete Cartesian"):
        analysis.structured_face_pairs(centers[:-1], np.ones_like(centers[:-1]))
    with pytest.raises(ValueError, match="nonconforming"):
        analysis.structured_face_pairs(centers, np.full_like(centers, 0.5))


def test_cloud_union_span_and_front_keep_cell_edges_and_frame():
    centers = np.array([[1, -1, -2], [1, 1, -1], [2, 0, -3]], dtype=float)
    widths = np.array([[0.2, 0.4, 0.6]] * 3)
    result = analysis.cloud_profiles(
        np.array([0.5, 0.95, 0.0001]),
        centers,
        widths,
        source_origin_m=np.array([0.5, 0.0, 0.0]),
        threshold=0.001,
    )
    assert result["selected_cells"] == 2
    assert result["penetration"][0]["streamwise_m"] == 0.5
    assert result["penetration"][0]["downward_front_m"] == 2.3
    assert result["total_water_volume_m3"] == pytest.approx(1.4501 * 0.2 * 0.4 * 0.6)
    # The two z levels have one selected cell each; widths must not be halved.
    assert [r["total_cross_track_width_m"] for r in result["expansion"]] == pytest.approx(
        [0.4, 0.4]
    )


def test_full_width_includes_gap_between_outlets_and_core_is_separate():
    centers = np.array([[0.0, -2, -1], [1e-12, 2, -1 + 1e-12]], dtype=float)
    widths = np.ones((2, 3))
    cloud = analysis.cloud_profiles(
        np.array([0.2, 1]), centers, widths, source_origin_m=np.zeros(3), threshold=0.001
    )
    core = analysis.cloud_profiles(
        np.array([0.2, 1]), centers, widths, source_origin_m=np.zeros(3), threshold=0.9
    )
    assert cloud["expansion"][0]["total_cross_track_width_m"] == 5
    assert core["expansion"][0]["total_cross_track_width_m"] == 1


def test_restart_flux_and_signed_sample_integration(tmp_path):
    for branch, rows in [("0", "0 0 0\n1 0 -2\n2 0 -100\n"), ("1", "1 0 -2\n2 0 -4\n")]:
        folder = tmp_path / "postProcessing/sourceFlux" / branch
        folder.mkdir(parents=True)
        (folder / "surfaceFieldValue.dat").write_text("# t phi alphaPhi_\n" + rows)
    data = analysis.flux_histories(tmp_path, ["source"])["source"]
    assert data == [(0, 0), (1, -2), (2, -4)]
    assert analysis.flux_integral(data, 1.5) == pytest.approx(-2.25)
    with pytest.raises(ValueError, match="cover"):
        analysis.flux_integral(data, 3)


def test_mesh_exit_zero_does_not_hide_quality_failure_or_short_flow():
    log = "Failed 3 mesh checks.\nCL415_STAGE_EXIT stage=checkMesh code=0\nTime = 0.03\n"
    result = runner.solver_summary(log, 0.1)
    assert result["stage_exit_codes"]["checkMesh"] == 0
    assert not result["mesh_ok"]
    assert not result["reached_requested_horizon"]
    assert result["last_time_s"] == 0.03


def test_fatal_at_target_is_not_a_success():
    result = runner.solver_summary("Mesh OK.\nTime = 0.1\nFloating point exception", 0.1)
    assert result["reached_requested_horizon"]
    assert result["fatal_error_observed"]


def test_openfoam_startup_trapping_message_is_not_a_failure():
    log = (
        "trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\n"
        "Mesh OK.\nTime = 0.1\nCL415_STAGE_EXIT stage=interIsoFoam code=0\n"
    )
    result = runner.solver_summary(log, 0.1)
    assert result["reached_requested_horizon"]
    assert not result["fatal_error_observed"]


@pytest.mark.parametrize("residual", [None, float("nan"), 2.0])
def test_long_trial_cannot_follow_missing_or_broken_pilot_ledger(tmp_path, residual):
    folder = tmp_path / "analytics"
    folder.mkdir()
    (folder / "report.json").write_text(
        json.dumps(
            {
                "times": [
                    {
                        "sampled_mass_residual_kg": residual,
                        "sampled_injected_water_kg": 100,
                    }
                ]
            }
        )
    )
    with pytest.raises(RuntimeError, match="mass diagnostic"):
        runner.pilot_mass_error(tmp_path, {"status": "exploratory_completed"})
    with pytest.raises(RuntimeError, match="did not complete"):
        runner.pilot_mass_error(tmp_path, {"status": "failed_or_incomplete"})
