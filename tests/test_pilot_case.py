"""Check generated OpenFOAM inputs for the P0 and reviewed P1 setups."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_restas_pilot import (  # noqa: E402
    CASE_COMMAND,
    CASE_STAGE_ORDER,
    _analyze_p1_run,
    _case_stage_exit_records,
    _write_case,
)


def test_p1_analyzer_reads_persisted_solver_and_wall_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    manifest = {"wall_time_s": 120.0, "execution": {"wall_time_limit_s": 3600.0}}
    stage_records = [{"stage": stage, "exit_code": 0} for stage in CASE_STAGE_ORDER]
    observed_manifest: dict[str, object] = {}

    def report_builder(path: Path) -> dict[str, object]:
        assert path == run_dir
        observed_manifest.update(json.loads(manifest_path.read_text(encoding="utf-8")))
        return {"gate_decision": {"p1_ledger_passed": True}, "manifest": {}}

    report, runner_exit_code = _analyze_p1_run(
        run_dir, manifest_path, manifest, 0, stage_records, report_builder
    )

    assert observed_manifest["case_command_exit_code"] == 0
    assert observed_manifest["interisofoam_exit_code"] == 0
    assert observed_manifest["reconstruction_exit_code"] == 0
    assert observed_manifest["wall_time_s"] == 120.0
    assert report["manifest"]["runner_exit_code"] == 0
    assert manifest["exit_code"] == 0
    assert runner_exit_code == 0


def test_p1_ledger_failure_preserves_solver_exit_code(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, object] = {}
    stage_records = [{"stage": stage, "exit_code": 0} for stage in CASE_STAGE_ORDER]

    def report_builder(path: Path) -> dict[str, object]:
        assert path == run_dir
        return {"gate_decision": {"p1_ledger_passed": False}, "manifest": {}}

    report, runner_exit_code = _analyze_p1_run(
        run_dir, manifest_path, manifest, 0, stage_records, report_builder
    )

    assert runner_exit_code == 1
    assert manifest["interisofoam_exit_code"] == 0
    assert manifest["case_command_exit_code"] == 0
    assert manifest["exit_code"] == 1
    assert report["manifest"]["runner_exit_code"] == 1


def test_source_event_case_resolves_knots_and_logs_every_step(tmp_path: Path) -> None:
    inputs = _write_case(tmp_path / "p1", 1, source_event_ledger=True)
    case = tmp_path / "p1"
    control = (case / "system" / "controlDict").read_text(encoding="utf-8")
    velocity = (case / "0" / "U").read_text(encoding="utf-8")
    solution = (case / "system" / "fvSolution").read_text(encoding="utf-8")

    assert "uniformValue table ((0 (0 0 -4.8)) (0.0795 (0 0 -4.8))" in velocity
    assert "(0.0805 (0 0 0)) (0.12 (0 0 0))" in velocity
    assert "deltaT 1e-4;" in control
    assert "adjustTimeStep no;" in control
    assert "writeInterval 1;\n        operation volIntegrate;" in control
    assert "nAlphaSubCycles 1;" in solution
    for patch in inputs["flux_patch_names"]:
        object_start = control.index(f"    {patch}Flux\n")
        object_end = control.index("\n    }", object_start)
        flux_object = control[object_start:object_end]
        assert f"        name {patch};" in flux_object
        assert "        type surfaceFieldValue;" in flux_object
        assert "        fields (phi alphaPhi_);" in flux_object
        assert "        writeFields false;" in flux_object
        assert "        executeControl timeStep;" in flux_object
        assert "        writeControl timeStep;" in flux_object
    assert inputs["experiment_id"] == "P1_SOURCE_EVENT_LEDGER"
    assert inputs["expected_time_steps"] == 1200
    assert inputs["expected_released_mass_kg"] == 230.4
    assert inputs["fixed_delta_t_s"] == 1e-4
    assert inputs["adjust_time_step"] is False
    assert inputs["n_alpha_sub_cycles"] == 1
    assert inputs["source_constant_velocity_interval_s"] == [0.0, 0.0795]
    assert inputs["source_window_s"] == [0.0, 0.0805]
    assert inputs["source_shutoff_s"] == 0.0805


def test_case_command_preserves_stage_exit_codes_and_parser_reads_them(tmp_path: Path) -> None:
    command = CASE_COMMAND.format(ranks=16)
    assert "run_stage interIsoFoam mpirun -np 16 interIsoFoam -parallel;" in command
    assert "run_stage reconstructPar reconstructPar -latestTime" in command
    syntax = subprocess.run(["bash", "-n", "-c", command], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    log_path = tmp_path / "openfoam-console.log"
    log_path.write_text(
        "P1_STAGE_EXIT stage=blockMesh code=0\n"
        "P1_STAGE_EXIT stage=checkMesh code=0\n"
        "P1_STAGE_EXIT stage=decomposePar code=0\n"
        "P1_STAGE_EXIT stage=interIsoFoam code=17\n",
        encoding="utf-8",
    )

    assert _case_stage_exit_records(log_path) == [
        {"stage": "blockMesh", "exit_code": 0},
        {"stage": "checkMesh", "exit_code": 0},
        {"stage": "decomposePar", "exit_code": 0},
        {"stage": "interIsoFoam", "exit_code": 17},
    ]


def test_existing_p0_case_keeps_its_original_event_and_controls(tmp_path: Path) -> None:
    _write_case(tmp_path / "p0", 1)
    case = tmp_path / "p0"
    control = (case / "system" / "controlDict").read_text(encoding="utf-8")
    velocity = (case / "0" / "U").read_text(encoding="utf-8")

    assert "uniformValue table ((0 (0 0 -4.8)) (0.08 (0 0 -4.8))" in velocity
    assert "(0.0800001 (0 0 0)) (0.12 (0 0 0))" in velocity
    assert "adjustTimeStep yes;" in control
    assert "writeInterval 10;\n        operation volIntegrate;" in control
    assert "alphaPhi_" not in control
