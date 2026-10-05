from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_native_vof_case.py"
SPEC = importlib.util.spec_from_file_location("run_native_vof_case", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def prepared_case(path: Path, *, ranks: int = 2, horizon: float = 1.0) -> Path:
    case = path
    mesh = case / "constant/polyMesh"
    system = case / "system"
    initial = case / "0"
    for directory in (mesh, system, initial):
        directory.mkdir(parents=True, exist_ok=True)
    for name in runner.POLYMESH_FILES:
        (mesh / name).write_text(f"fixture {name}\n", encoding="utf-8")
    (mesh / "boundary").write_text(
        """FoamFile
{
    version 2.0;
    format ascii;
    class polyBoundaryMesh;
    object boundary;
}
1
(
dash8Opening
{
    type patch;
    nFaces 3;
    startFace 10;
}
)
""",
        encoding="utf-8",
    )
    (system / "controlDict").write_text(
        f"""application interIsoFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {horizon};
writeControl adjustableRunTime;
writeInterval 0.1;
""",
        encoding="utf-8",
    )
    (system / "decomposeParDict").write_text(
        f"numberOfSubdomains {ranks};\nmethod simple;\n", encoding="utf-8"
    )
    metadata = {
        "solver": "interIsoFoam",
        "ranks": ranks,
        "horizon_s": horizon,
        "mesh_type": "static polyhedral",
        "mesh_cells_expected": 2,
        "source_patches": ["dash8Opening"],
        "source_patch_face_counts": {"dash8Opening": 3},
        "time_controls": {"snapshot_interval_s": 0.1},
    }
    (case / "case-inputs.json").write_text(json.dumps(metadata), encoding="utf-8")
    for name in ("alpha.water", "U", "k", "epsilon", "nut"):
        (initial / name).write_text("internalField uniform 0;\n", encoding="utf-8")
    return case


def successful_checkmesh() -> dict[str, Any]:
    return {
        "return_code": 0,
        "timed_out": False,
        "elapsed_s": 0.1,
        "log": "cells: 2\nMesh OK.\n",
        "console_log": "checkmesh-container.log",
        "version": "OpenFOAM-v2512",
        "container_cleanup": {
            "status": "owned_container_removed_after_stop",
            "stopped_verified": True,
        },
        "container_cleanup_verified": True,
    }


def patch_runtime(
    monkeypatch: pytest.MonkeyPatch, *, checkmesh: dict[str, Any], solver_fn: Any
) -> None:
    monkeypatch.setattr(runner, "_doctor", lambda run_dir: {"resources": {}})
    monkeypatch.setattr(
        runner,
        "_validate_capacity",
        lambda doctor, *, ranks, memory_gib: {
            "effective_cpu_count": ranks,
            "active_solver_or_mesh_processes": [],
        },
    )
    monkeypatch.setattr(runner, "_inspect_pinned_image", lambda: runner.PINNED_IMAGE_ID)
    monkeypatch.setattr(
        runner,
        "run_checkmesh",
        lambda command, *, run_dir, case_dir, image_id, timeout_s: checkmesh,
    )
    monkeypatch.setattr(runner, "run_solver", solver_fn)


def make_checkmesh_exception(case: Path, evidence_dir: Path) -> Path:
    mesh_dir = case / "constant/polyMesh"
    proof = {
        "concave_cell_count": 1,
        "supporting_plane_result": {
            "cells_with_two_sided_vertices": 0,
            "faces_with_two_sided_vertices": 0,
            "max_outside_excursion_m": 0.0,
        },
        "native_graph_files": {
            name: {"sha256": runner.sha256_file(mesh_dir / name)} for name in runner.POLYMESH_FILES
        },
    }
    proof_path = evidence_dir / "native_geometry.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    flag = "***Concave cells (using face planes) found, number of cells: 1"
    evidence = {
        "schema": "dash8-static-polyhedral-planar-exception-v1",
        "expected_checkmesh_failure_lines": [flag],
        "native_geometry_proof": {
            "path": str(proof_path),
            "sha256": runner.sha256_file(proof_path),
        },
    }
    evidence_path = evidence_dir / "exception.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_path


def test_prepared_polyhedral_case_validates_native_source_and_sparse_time(tmp_path: Path) -> None:
    case = prepared_case(tmp_path / "case")
    contract = runner.validate_prepared_case(case, ranks=2)

    assert contract["expected_mesh_cells"] == 2
    assert contract["source_patch_inventory"]["dash8Opening"] == {
        "expected_faces": 3,
        "native_boundary_faces": 3,
    }
    assert contract["write_control"] == "adjustableRunTime"
    assert contract["write_interval_s"] == pytest.approx(0.1)
    assert not (case / "processor0").exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("ranks", "requested ranks"),
        ("horizon", "does not match metadata horizon"),
        ("source_count", "native boundary count"),
        ("decomposition", "numberOfSubdomains"),
    ],
)
def test_prepared_case_rejects_stale_horizon_rank_and_source_metadata(
    tmp_path: Path, mutation: str, message: str
) -> None:
    case = prepared_case(tmp_path / "case")
    if mutation == "ranks":
        with pytest.raises(ValueError, match=message):
            runner.validate_prepared_case(case, ranks=3)
    elif mutation == "horizon":
        control = case / "system/controlDict"
        control.write_text(control.read_text().replace("endTime 1.0;", "endTime 2.0;"))
        with pytest.raises(ValueError, match=message):
            runner.validate_prepared_case(case, ranks=2)
    elif mutation == "source_count":
        boundary = case / "constant/polyMesh/boundary"
        boundary.write_text(boundary.read_text().replace("nFaces 3;", "nFaces 4;"))
        with pytest.raises(ValueError, match=message):
            runner.validate_prepared_case(case, ranks=2)
    else:
        decompose = case / "system/decomposeParDict"
        decompose.write_text(
            decompose.read_text().replace("numberOfSubdomains 2;", "numberOfSubdomains 3;")
        )
        with pytest.raises(ValueError, match=message):
            runner.validate_prepared_case(case, ranks=2)


def test_capacity_preflight_rejects_busy_solver_or_undersized_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doctor = {
        "resources": {
            "cpu": {"effective": 20},
            "memory": {"total_bytes": 128 * 1024**3, "effective_available_bytes": 100 * 1024**3},
        }
    }
    empty_activity = {
        "container_status_by_id": {},
        "running_container_usage": [],
        "paused_containers": [{"id": "b" * 64, "name": "paused-run", "status": "Up 3h (Paused)"}],
        "running_container_cpu_equivalents": 0.0,
    }
    monkeypatch.setattr(runner, "_docker_activity_snapshot", lambda: empty_activity)
    monkeypatch.setattr(runner, "_current_solver_processes", lambda statuses=None: [])
    record = runner._validate_capacity(doctor, ranks=20, memory_gib=96)
    assert record["effective_cpu_count"] == 20
    assert record["paused_containers_excluded_from_cpu_load"] == empty_activity["paused_containers"]
    assert record["estimated_shared_cpu_capacity_available"] == pytest.approx(20.0)

    with pytest.raises(runner.RunnerError, match="effective CPU capacity"):
        runner._validate_capacity(doctor, ranks=21, memory_gib=96)
    with pytest.raises(runner.RunnerError, match="physical memory"):
        runner._validate_capacity(doctor, ranks=20, memory_gib=129)

    busy_activity = {
        **empty_activity,
        "running_container_usage": [
            {"id": "c" * 64, "name": "active-run", "status": "Up 2m", "cpu_equivalents": 19.0}
        ],
        "running_container_cpu_equivalents": 19.0,
        "paused_containers": [],
    }
    monkeypatch.setattr(runner, "_docker_activity_snapshot", lambda: busy_activity)
    with pytest.raises(runner.RunnerError, match="measured shared capacity"):
        runner._validate_capacity(doctor, ranks=20, memory_gib=96)

    shared = runner._validate_capacity(doctor, ranks=1, memory_gib=96)
    assert shared["estimated_shared_cpu_capacity_available"] == pytest.approx(1.0)


def test_docker_activity_snapshot_excludes_paused_and_stopped_cpu_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1] == "ps":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    f"{'a' * 64}|running|Up 2 minutes\n"
                    f"{'b' * 64}|paused|Up 3 hours (Paused)\n"
                    f"{'c' * 64}|stopped|Exited (0) 1 hour ago\n"
                ),
                stderr="",
            )
        assert command[1] == "stats"
        assert command[-1] == "running"
        return subprocess.CompletedProcess(
            command, 0, stdout="running|1500.00%|12GiB / 96GiB\n", stderr=""
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    activity = runner._docker_activity_snapshot()
    assert len(calls) == 2
    assert [row["name"] for row in activity["running_containers"]] == ["running"]
    assert [row["name"] for row in activity["paused_containers"]] == ["paused"]
    assert activity["running_container_cpu_equivalents"] == pytest.approx(15.0)
    assert activity["container_status_by_id"]["c" * 64].startswith("Exited")


def test_process_capacity_counts_only_active_non_container_openfoam_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = """101 interIsoFoam Tl 99.0
102 checkMesh S 20.0
103 decomposePar R 85.0
104 interIsoFoam R 99.0
"""
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, output, ""),
    )
    paused_id = "b" * 64
    running_id = "a" * 64
    monkeypatch.setattr(
        runner,
        "_pid_docker_container_id",
        lambda pid: {101: paused_id, 104: running_id}.get(pid),
    )
    active = runner._current_solver_processes({paused_id: "Up 1h (Paused)", running_id: "Up 1m"})
    assert [row["pid"] for row in active] == [102, 103]
    assert sum(row["cpu_equivalents"] for row in active) == pytest.approx(1.05)


def test_cleanup_never_targets_a_name_without_owned_full_cid_or_matching_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "dash8-runner-name-conflict"
    run_dir.mkdir()
    case_dir = run_dir / "case"
    case_dir.mkdir()

    def no_docker(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not call Docker without a full CID from this run")

    monkeypatch.setattr(runner.subprocess, "run", no_docker)
    no_cid = runner._ensure_owned_container_stopped(
        run_dir,
        stage="solver",
        case_dir=case_dir,
        image_id=runner.PINNED_IMAGE_ID,
    )
    assert no_cid["status"] == "no_cidfile_no_container_claimed"
    assert no_cid["cleanup_attempted"] is False

    (run_dir / "container.cid").write_text("d" * 64 + "\n", encoding="ascii")
    monkeypatch.setattr(
        runner,
        "_inspect_container",
        lambda cid: {
            "exists": True,
            "id": cid,
            "image_id": runner.PINNED_IMAGE_ID,
            "labels": {
                runner.CONTAINER_LABEL_RUN: "different-run",
                runner.CONTAINER_LABEL_STAGE: "solver",
            },
            "mounts": [{"Destination": "/case", "Source": str(case_dir)}],
            "state": {"Running": True, "Status": "running"},
        },
    )
    mismatched = runner._ensure_owned_container_stopped(
        run_dir,
        stage="solver",
        case_dir=case_dir,
        image_id=runner.PINNED_IMAGE_ID,
    )
    assert mismatched["status"] == "ownership_unverified_no_stop_attempted"
    assert mismatched["identity_checks"]["run_label_matches"] is False
    assert mismatched["cleanup_attempted"] is False


def test_lifecycle_commands_preserve_prebuilt_mesh_and_never_remesh(tmp_path: Path) -> None:
    case = prepared_case(tmp_path / "case")
    before = runner.tree_hashes(case)
    shell = runner.solver_shell_script(2)
    check_command = runner.mesh_check_command(tmp_path / "trial", case, runner.PINNED_IMAGE_ID, 4)

    assert "decomposePar" in shell and "interIsoFoam" in shell
    assert "blockMesh" not in shell and "snappyHexMesh" not in shell
    assert "blockMesh" not in " ".join(check_command)
    assert "snappyHexMesh" not in " ".join(check_command)
    assert "--cidfile" in check_command
    assert f"{runner.CONTAINER_LABEL_RUN}=trial" in check_command
    assert f"{runner.CONTAINER_LABEL_STAGE}=checkMesh" in check_command
    solver = runner.solver_command(
        tmp_path / "trial", case, runner.PINNED_IMAGE_ID, ranks=2, memory_gib=4
    )
    assert "--cidfile" in solver
    assert f"{runner.CONTAINER_LABEL_RUN}=trial" in solver
    assert f"{runner.CONTAINER_LABEL_STAGE}=solver" in solver
    assert runner.tree_hashes(case) == before


def test_checkmesh_exception_requires_exact_flag_hashes_and_zero_support_plane_violations(
    tmp_path: Path,
) -> None:
    case = prepared_case(tmp_path / "case")
    evidence = make_checkmesh_exception(case, tmp_path)
    log = (
        "cells: 2\n"
        "***Concave cells (using face planes) found, number of cells: 1\n"
        "Failed 1 mesh checks.\n"
    )

    accepted = runner.evaluate_checkmesh(
        return_code=1,
        log=log,
        case_dir=case,
        expected_cells=2,
        exception_evidence=evidence,
    )
    assert accepted["formal_quality_gate_pass"] is False
    assert accepted["status"] == "exploratory_planar_transition_exception_applied"
    run_bundle = tmp_path / "run-bundle"
    run_bundle.mkdir()
    preserved = runner.preserve_mesh_exception_evidence(evidence, run_bundle)
    bundled_evidence = run_bundle / preserved["bundle_evidence_path"]
    assert preserved["source_sha256"] == runner.sha256_file(evidence)
    assert preserved["geometry_proof_sha256"] == preserved["bundle_geometry_proof_sha256"]
    assert (
        runner.evaluate_checkmesh(
            return_code=1,
            log=log,
            case_dir=case,
            expected_cells=2,
            exception_evidence=bundled_evidence,
        )["status"]
        == "exploratory_planar_transition_exception_applied"
    )

    extra_flag = log.replace(
        "Failed 1 mesh checks.", "***Non-orthogonality check failed\nFailed 2 mesh checks."
    )
    with pytest.raises(ValueError, match="do not exactly match"):
        runner.evaluate_checkmesh(
            return_code=1,
            log=extra_flag,
            case_dir=case,
            expected_cells=2,
            exception_evidence=evidence,
        )
    with pytest.raises(ValueError, match="strictly"):
        runner.evaluate_checkmesh(
            return_code=1,
            log=log,
            case_dir=case,
            expected_cells=2,
            exception_evidence=None,
        )


def _create_rank_checkpoint(case: Path, time_name: str, ranks: int) -> None:
    for rank in range(ranks):
        directory = case / f"processor{rank}" / time_name
        directory.mkdir(parents=True, exist_ok=True)
        for field in ("alpha.water", "U", "k", "epsilon", "nut"):
            (directory / field).write_text(f"{field} {rank} {time_name}\n", encoding="utf-8")


def test_observer_failure_does_not_change_completed_solver_or_delete_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = prepared_case(tmp_path / "case")
    monkeypatch.setattr(runner, "ROOT", tmp_path)

    def fake_solver(
        command: list[str], *, run_dir: Path, case_dir: Path, image_id: str, timeout_s: float
    ) -> dict[str, Any]:
        del case_dir, image_id
        assert "decomposePar" in command[-1] and "interIsoFoam" in command[-1]
        assert "blockMesh" not in command[-1] and "snappyHexMesh" not in command[-1]
        _create_rank_checkpoint(run_dir / "case", "1.000000", 2)
        return {
            "return_code": 0,
            "timed_out": False,
            "elapsed_s": 2.0,
            "container_id": "fake-container",
            "console_log": str(run_dir / "openfoam-console.log"),
            "container_cleanup": {
                "status": "owned_container_removed_after_stop",
                "stopped_verified": True,
            },
            "container_cleanup_verified": True,
            "console": (
                "NATIVE_VOF_STAGE_EXIT stage=decomposePar code=0\n"
                "Time = 0\nTime = 1\n"
                "NATIVE_VOF_STAGE_EXIT stage=interIsoFoam code=0\n"
            ),
        }

    def failed_observer(
        run_dir: Path, *, ranks: int, horizon_s: float, source_patch: str
    ) -> dict[str, Any]:
        assert ranks == 2 and horizon_s == pytest.approx(1.0)
        analytics = run_dir / "analytics"
        analytics.mkdir()
        (analytics / "postprocess.json").write_text('{"status":"failed"}\n')
        return {"status": "failed_or_incomplete"}

    patch_runtime(monkeypatch, checkmesh=successful_checkmesh(), solver_fn=fake_solver)
    monkeypatch.setattr(runner, "run_postprocessors", failed_observer)
    code, run_dir = runner.run_case(
        case_dir=case,
        run_id="dash8-runner-observer-failure",
        ranks=2,
        memory_gib=4,
        timeout_s=30,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert code == 0
    assert manifest["solver_status"] == "completed_at_requested_horizon"
    assert manifest["postprocess_status"] == "failed_or_incomplete"
    assert manifest["prepared_source_input_unchanged"] is True
    assert (run_dir / "case/processor1/1.000000/alpha.water").is_file()
    assert (run_dir / "case-input-sha256.json").is_file()
    assert manifest["mesh_generators_invoked"] == {"blockMesh": False, "snappyHexMesh": False}


def test_timeout_preserves_last_common_checkpoint_and_attempt_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = prepared_case(tmp_path / "case")
    monkeypatch.setattr(runner, "ROOT", tmp_path)

    def timed_out_solver(
        command: list[str], *, run_dir: Path, case_dir: Path, image_id: str, timeout_s: float
    ) -> dict[str, Any]:
        del command, case_dir, image_id
        _create_rank_checkpoint(run_dir / "case", "0.500000", 2)
        return {
            "return_code": 124,
            "timed_out": True,
            "elapsed_s": timeout_s,
            "container_id": "fake-timeout-container",
            "console_log": str(run_dir / "openfoam-console.log"),
            "container_cleanup": {
                "status": "owned_container_removed_after_stop",
                "stopped_verified": True,
            },
            "container_cleanup_verified": True,
            "console": "NATIVE_VOF_STAGE_EXIT stage=decomposePar code=0\nTime = 0.5\n",
        }

    patch_runtime(monkeypatch, checkmesh=successful_checkmesh(), solver_fn=timed_out_solver)
    code, run_dir = runner.run_case(
        case_dir=case,
        run_id="dash8-runner-timeout-preserved",
        ranks=2,
        memory_gib=4,
        timeout_s=30,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert code == 1
    assert manifest["solver_status"] == "wall_timeout_checkpoint_preserved"
    assert manifest["latest_common_analysis_checkpoint"]["time_s"] == pytest.approx(0.5)
    assert manifest["latest_common_analysis_checkpoint"]["restart_ready"] is False
    assert manifest["latest_common_analysis_checkpoint"]["checkpoint_classification"] == (
        "analysis_only_not_restart_ready"
    )
    assert manifest["postprocess_status"] == "not_attempted_solver_incomplete"
    assert (run_dir / "case/processor0/0.500000/alpha.water").is_file()


def test_sigterm_stops_and_verifies_only_the_owned_solver_container(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "dash8-runner-sigterm-cleanup"
    case_dir = run_dir / "case"
    case_dir.mkdir(parents=True)
    docker_bin_dir = tmp_path / "fake-bin"
    docker_bin_dir.mkdir()
    state_path = tmp_path / "fake-docker-state.json"
    output_path = tmp_path / "solver-result.json"
    fake_docker = docker_bin_dir / "docker"
    fake_docker.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

state_path = Path(os.environ["FAKE_DOCKER_STATE"])
args = sys.argv[1:]

def read_state():
    return json.loads(state_path.read_text())

def write_state(value):
    state_path.write_text(json.dumps(value))

if args[0] == "run":
    cid = "a" * 64
    cid_path = Path(args[args.index("--cidfile") + 1])
    cid_path.write_text(cid + "\\n")
    labels = {}
    for index, item in enumerate(args[:-1]):
        if item == "--label":
            key, value = args[index + 1].split("=", 1)
            labels[key] = value
    mount = args[args.index("--mount") + 1]
    mount_source = mount.split("src=", 1)[1].split(",dst=", 1)[0]
    image_id = next(item for item in args if item.startswith("sha256:"))
    name = args[args.index("--name") + 1]
    write_state({
        "Id": cid,
        "Name": "/" + name,
        "Image": image_id,
        "Config": {"Image": image_id, "Labels": labels},
        "Mounts": [{"Source": mount_source, "Destination": "/case"}],
        "State": {"Running": True, "Status": "running"},
    })
    while read_state()["State"]["Running"]:
        time.sleep(0.02)
    print("mock solver stopped", flush=True)
elif args[0] == "inspect":
    print(json.dumps(read_state()))
elif args[0] in {"stop", "kill"}:
    state = read_state()
    if args[-1] != state["Id"]:
        raise SystemExit("cleanup target was not the full owned CID")
    state["State"] = {"Running": False, "Status": "exited"}
    write_state(state)
    print(state["Id"])
elif args[0] == "stats":
    Path(os.environ["FAKE_DOCKER_STATS_STARTED"]).write_text("started")
    time.sleep(0.5)
    print("{}")
else:
    raise SystemExit("unexpected fake docker command: " + " ".join(args))
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    command = runner.solver_command(
        run_dir, case_dir, runner.PINNED_IMAGE_ID, ranks=2, memory_gib=4
    )
    child = """
import importlib.util, json, os, subprocess, sys
from pathlib import Path
script, run_path, case_path, output_path = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("native_runner_child", script)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
command = json.loads(os.environ["FAKE_RUN_COMMAND"])
native_popen = runner.subprocess.Popen
class FirstRunWaitTimeout(native_popen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.force_first_timeout = self.args[0] == "docker" and "run" in self.args
    def wait(self, timeout=None):
        if self.force_first_timeout:
            self.force_first_timeout = False
            raise subprocess.TimeoutExpired(self.args, timeout)
        return super().wait(timeout=timeout)
runner.subprocess.Popen = FirstRunWaitTimeout
with runner.termination_handlers():
    result = runner.run_solver(
        command, run_dir=run_path, case_dir=case_path,
        image_id=runner.PINNED_IMAGE_ID, timeout_s=60.0,
    )
output_path.write_text(json.dumps(result))
"""
    environment = os.environ.copy()
    environment["PATH"] = f"{docker_bin_dir}{os.pathsep}{environment['PATH']}"
    environment["FAKE_DOCKER_STATE"] = str(state_path)
    stats_started_path = tmp_path / "fake-docker-stats-started"
    environment["FAKE_DOCKER_STATS_STARTED"] = str(stats_started_path)
    environment["FAKE_RUN_COMMAND"] = json.dumps(command)
    child_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child,
            str(SCRIPT),
            str(run_dir),
            str(case_dir),
            str(output_path),
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not stats_started_path.is_file():
        if child_process.poll() is not None:
            stdout, stderr = child_process.communicate()
            raise AssertionError(f"runner exited before starting mock container: {stdout} {stderr}")
        time.sleep(0.02)
    assert (run_dir / "container.cid").is_file()
    assert stats_started_path.is_file()
    os.kill(child_process.pid, signal.SIGTERM)
    stdout, stderr = child_process.communicate(timeout=15)

    assert child_process.returncode == 0, f"stdout={stdout} stderr={stderr}"
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["interrupted"] is True
    assert result["termination_signal"] == signal.SIGTERM
    assert result["return_code"] == 128 + signal.SIGTERM
    assert result["container_cleanup_verified"] is True
    assert result["container_cleanup"]["stopped_verified"] is True
    assert result["container_stop_attempt"]["attempts"][0]["target_full_id"] == "a" * 64
    assert json.loads(state_path.read_text(encoding="utf-8"))["State"]["Running"] is False


def test_checkmesh_failure_is_recorded_and_blocks_solver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = prepared_case(tmp_path / "case")
    stale_check_log = "old stale checkMesh output\n"
    (case / "log.checkMesh").write_text(stale_check_log, encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    failed_log = "cells: 2\n***Non-orthogonality check failed\nFailed 1 mesh checks.\n"

    def fake_check(
        command: list[str],
        *,
        run_dir: Path,
        case_dir: Path,
        image_id: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        del run_dir, image_id
        (case_dir / "log.checkMesh").write_text(failed_log, encoding="utf-8")
        return {
            "return_code": 1,
            "timed_out": False,
            "elapsed_s": 0.2,
            "log": failed_log,
            "console_log": "checkmesh-container.log",
            "version": "OpenFOAM-v2512",
            "container_cleanup": {
                "status": "owned_container_removed_after_stop",
                "stopped_verified": True,
            },
            "container_cleanup_verified": True,
        }

    def must_not_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("solver must not start after a failed strict mesh check")

    patch_runtime(monkeypatch, checkmesh=successful_checkmesh(), solver_fn=must_not_run)
    monkeypatch.setattr(runner, "run_checkmesh", fake_check)
    code, run_dir = runner.run_case(
        case_dir=case,
        run_id="dash8-runner-meshcheck-failure",
        ranks=2,
        memory_gib=4,
        timeout_s=30,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert code == 1
    assert manifest["solver_status"] == "preflight_or_stage_failed_attempt_preserved"
    assert manifest["mesh_check_attempt"]["return_code"] == 1
    assert manifest["mesh_check_attempt"]["failed_check_lines"] == [
        "***Non-orthogonality check failed"
    ]
    assert (run_dir / "case/log.checkMesh").read_text() == failed_log
    assert (run_dir / "preexisting-runtime-outputs/log.checkMesh").read_text() == stale_check_log
    assert (case / "log.checkMesh").read_text() == stale_check_log
    assert not (run_dir / "case/processor0").exists()
