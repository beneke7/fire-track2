from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DISPATCH_PATH = ROOT / "cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.py"
SPEC = importlib.util.spec_from_file_location("rouaix_pressure_dispatch", DISPATCH_PATH)
assert SPEC is not None and SPEC.loader is not None
dispatcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dispatcher
SPEC.loader.exec_module(dispatcher)


def test_failed_guarded_parent_is_rejected_before_archive_or_checkpoint_access(
    tmp_path: Path,
) -> None:
    from cases.e1_rouaix_hpc_restart import run_restart

    parent = tmp_path / "rouaix-restart-pressure-total-p0-zero-14702499"
    parent.mkdir()
    (parent / "run-state.json").write_text(
        json.dumps(
            {
                "status": "failed_preserved",
                "job_id": "14702499",
                "variant": "pressure-total-p0-zero",
                "solver_time_steps_recorded": 495,
                "solver_time_s": 0.2496,
                "solver_exit_code": 143,
                "solver_end_marker": False,
                "stop_reason": "max|U| guard",
                "pause_observed": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(run_restart.RestartError, match="status"):
        run_restart.verify_completed_parent(parent, "14702499")


def test_dispatcher_stops_on_parent_failure_before_any_slurm_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cases.e1_rouaix_hpc_restart import run_restart

    source = tmp_path / "source"
    source.mkdir()
    (source / "dispatch-source-index.json").write_text(
        json.dumps({"schema_version": 1, "files": []}), encoding="utf-8"
    )
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "run-state.json").write_text('{"status":"failed_preserved"}\n', encoding="utf-8")
    paths = [tmp_path / name for name in ("project", "shared", "solver")]
    for path in paths:
        path.mkdir()
    monkeypatch.setattr(dispatcher, "PROJECT_ROOT", paths[0])
    monkeypatch.setattr(dispatcher, "check_admission", lambda *_args: {"ok": True})
    monkeypatch.setattr(dispatcher, "verify_auditor", lambda _path: "a" * 64)
    monkeypatch.setattr(
        run_restart,
        "verify_completed_parent",
        lambda *_args: (_ for _ in ()).throw(
            run_restart.RestartError("completed parent status is failed_preserved")
        ),
    )
    submitted: list[list[str]] = []
    monkeypatch.setattr(dispatcher, "_run", lambda argv, **_kwargs: submitted.append(argv))
    monkeypatch.setenv("SLURM_JOB_ID", "90001")

    with pytest.raises(run_restart.RestartError, match="failed_preserved"):
        dispatcher.dispatch(
            dispatcher.DispatchConfig(
                parent_job_id="14705632",
                parent_run=parent,
                shared_root=paths[1],
                solver_root=paths[2],
                seed_source_root=source,
            )
        )
    assert submitted == []


def test_dispatcher_rejects_wrong_parent_profile_before_any_slurm_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cases.e1_rouaix_hpc_restart import run_restart

    source = tmp_path / "source"
    source.mkdir()
    (source / "dispatch-source-index.json").write_text(
        json.dumps({"schema_version": 1, "files": []}), encoding="utf-8"
    )
    paths = [tmp_path / name for name in ("project", "shared", "solver", "parent")]
    for path in paths:
        path.mkdir()
    monkeypatch.setattr(dispatcher, "PROJECT_ROOT", paths[0])
    monkeypatch.setattr(dispatcher, "check_admission", lambda *_args: {"ok": True})
    monkeypatch.setattr(dispatcher, "verify_auditor", lambda _path: "a" * 64)
    monkeypatch.setattr(
        run_restart,
        "verify_completed_parent",
        lambda *_args: {
            "variant": "pressure-total-p0-zero",
            "case_id": "rouaix-restart-pressure-total-p0-zero-0300",
            "parent_start_time_s": 0.2,
            "parent_target_time_s": 0.3,
            "checkpoint_time_dir": "processors120/0.300000000000",
            "step_count": 1000,
            "archive_path": "unused",
        },
    )
    monkeypatch.setattr(run_restart, "validate_parent_contract", lambda *_args, **_kwargs: None)
    submitted: list[list[str]] = []
    monkeypatch.setattr(dispatcher, "_run", lambda argv, **_kwargs: submitted.append(argv))
    monkeypatch.setenv("SLURM_JOB_ID", "90002")

    with pytest.raises(dispatcher.DispatchError, match="PCG/DIC .255 s endpoint"):
        dispatcher.dispatch(
            dispatcher.DispatchConfig(
                parent_job_id="14705632",
                parent_run=paths[3],
                shared_root=paths[1],
                solver_root=paths[2],
                seed_source_root=source,
            )
        )
    assert submitted == []


def test_scontrol_readback_binds_owner_resources_dependency_and_hold_state() -> None:
    text = (
        "JobId=991 JobName=ml-vof UserId=nk_memj(123) Account=nk_meshapplied "
        "Partition=cpu-short QOS=normal JobState=PENDING Reason=JobHeldUser "
        "NumNodes=3-3 NumCPUs=120 NumTasks=120 NtasksPerN:B:S:C=40:0:*:1 MinCPUsNode=40 "
        "CPUs/Task=1 MinMemoryNode=22G "
        "TimeLimit=02:00:00 Dependency=afterany:900(unfulfilled) "
        "Comment=rouaix-pcgdic-900-child WorkDir=/project/run "
        "Command=/project/source/restart.sbatch Requeue=0"
    )
    fields = dispatcher.validate_job_readback(
        text,
        job_id="991",
        owner="nk_memj",
        name="ml-vof",
        nodes=3,
        tasks=120,
        tasks_per_node=40,
        cpus=120,
        memory_bytes=22 * 1024**3,
        wall_time="02:00:00",
        dependency="afterany:900",
        work_dir=Path("/project/run"),
        command=Path("/project/source/restart.sbatch"),
        comment="rouaix-pcgdic-900-child",
        held=True,
    )
    assert fields["Reason"] == "JobHeldUser"
    released = text.replace("Reason=JobHeldUser", "Reason=Dependency").replace(
        "(unfulfilled)", "(fulfilled)"
    )
    dispatcher.validate_job_readback(
        released,
        job_id="991",
        owner="nk_memj",
        name="ml-vof",
        nodes=3,
        tasks=120,
        tasks_per_node=40,
        cpus=120,
        memory_bytes=22 * 1024**3,
        wall_time="02:00:00",
        dependency="afterany:900",
        work_dir=Path("/project/run"),
        command=Path("/project/source/restart.sbatch"),
        comment="rouaix-pcgdic-900-child",
        held=False,
    )

    with pytest.raises(dispatcher.DispatchError, match="readback mismatch"):
        dispatcher.validate_job_readback(
            text.replace("afterany:900", "afterany:901"),
            job_id="991",
            owner="nk_memj",
            name="ml-vof",
            nodes=3,
            tasks=120,
            tasks_per_node=40,
            cpus=120,
            memory_bytes=22 * 1024**3,
            wall_time="02:00:00",
            dependency="afterany:900",
            work_dir=Path("/project/run"),
            command=Path("/project/source/restart.sbatch"),
            comment="rouaix-pcgdic-900-child",
            held=True,
        )


def test_audit_manifest_names_exact_child_run_and_horizon(tmp_path: Path) -> None:
    manifest = dispatcher.audit_manifest("991", tmp_path / "solver-runs")
    job = manifest["jobs"][0]
    assert job["job_id"] == "991"
    assert job["run_dir"] == str(
        tmp_path / "solver-runs/rouaix-restart-pressure-pcgdic-continuation-991"
    )
    assert job["expected_ranks"] == 120
    assert job["case_id"] == "rouaix-restart-pressure-pcgdic-continuation-0300"
    assert job["horizon_s"] == 0.3
    assert job["delta_t_s"] == 0.0001


def test_dispatch_and_child_sbatch_resources_are_bounded_cpu_only() -> None:
    dispatch_script = (
        ROOT / "cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.sbatch"
    ).read_text()
    child_script = (
        ROOT / "cases/e1_rouaix_hpc_restart/restart_pressure_pcgdic_continue.sbatch"
    ).read_text()
    assert "#SBATCH --cpus-per-task=2" in dispatch_script
    assert "#SBATCH --mem=4G" in dispatch_script
    assert "#SBATCH --time=00:15:00" in dispatch_script
    assert "#SBATCH --no-requeue" in dispatch_script
    assert "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1" in dispatch_script
    assert "#SBATCH --ntasks=120" in child_script
    assert "#SBATCH --nodes=3" in child_script
    assert "#SBATCH --mem=22G" in child_script
    assert "#SBATCH --time=02:00:00" in child_script
    assert "--variant pressure-pcgdic-continuation" in child_script
    assert "--parent-contract" in child_script
    assert "SOURCE_ROOT=${ROUAIX_SOURCE_ROOT:?" in child_script
    assert "BASH_SOURCE" not in child_script


def test_seed_source_hashes_are_checked_before_capsule_creation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = source / "cases/helper.py"
    payload.parent.mkdir()
    payload.write_bytes(b"frozen helper\n")
    (source / "dispatch-source-index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "cases/helper.py",
                        "bytes": payload.stat().st_size,
                        "sha256": dispatcher.sha256_file(payload),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    dispatcher.verify_seed_source(source)
    payload.write_bytes(b"changed helper\n")
    with pytest.raises(dispatcher.DispatchError, match="hash differs"):
        dispatcher.verify_seed_source(source)


def test_freeze_seed_source_records_all_code_and_additions_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    index_path = repo / "inputs/source-index.json"
    index_path.parent.mkdir(parents=True)
    base = repo / "cases/base.py"
    base.parent.mkdir()
    base.write_bytes(b"base helper\n")
    parent_capsule = index_path.parent / "parent-source.tar.gz"
    with tarfile.open(parent_capsule, "w:gz") as tar:
        tar.add(base, arcname="cases/base.py", recursive=False)
    parent_sha = dispatcher.sha256_file(parent_capsule)
    parent_capsule.with_suffix(parent_capsule.suffix + ".sha256").write_text(
        f"{parent_sha}  {parent_capsule.name}\n", encoding="ascii"
    )
    index_path.write_text(
        json.dumps(
            {
                "archive_sha256": parent_sha,
                "files": [{"path": "cases/base.py", "sha256": dispatcher.sha256_file(base)}],
            }
        ),
        encoding="utf-8",
    )
    for relative in dispatcher.EXTRA_SOURCE_PATHS:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{relative}\n", encoding="utf-8")
    monkeypatch.setattr(dispatcher, "PARENT_SOURCE_INDEX", "inputs/source-index.json")
    monkeypatch.setattr(dispatcher, "PARENT_SOURCE_CAPSULE", "parent-source.tar.gz")
    monkeypatch.setattr(
        dispatcher.subprocess,
        "run",
        lambda argv, **_kwargs: SimpleNamespace(
            stdout="f" * 40 + "\n" if argv[1] == "rev-parse" else "",
        ),
    )

    prep = tmp_path / "prep"
    result = dispatcher.freeze_seed_source(repo, prep)
    index = dispatcher.verify_seed_source(prep / "unpacked")
    assert index["parent_source_capsule_sha256"] == parent_sha
    assert result["file_count"] == 2 + len(dispatcher.EXTRA_SOURCE_PATHS)
    assert (prep / f"{dispatcher.CONTINUATION_SOURCE_CAPSULE}.sha256").is_file()
    assert (repo / dispatcher.CONTINUATION_SOURCE_SUMMARY / "source-capsule-index.json").is_file()
    with pytest.raises(dispatcher.DispatchError, match="refusing to overwrite"):
        dispatcher.freeze_seed_source(repo, prep)


def test_disk_admission_requires_reserve_plus_declared_output_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, shared, solver = (tmp_path / name for name in ("project", "shared", "solver"))
    for path in (project, shared, solver):
        path.mkdir()
    monkeypatch.setattr(dispatcher, "PROJECT_ROOT", project)
    config = dispatcher.DispatchConfig(shared_root=shared, solver_root=solver)
    required = config.disk_reserve_bytes + 8 * 1024**3
    monkeypatch.setattr(
        dispatcher.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=required - 1),
    )
    with pytest.raises(dispatcher.DispatchError, match="reserve plus output allowance"):
        dispatcher.check_admission(config, 8 * 1024**3)

    monkeypatch.setattr(
        dispatcher.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=required),
    )
    admission = dispatcher.check_admission(config, 8 * 1024**3)
    assert admission["required_free_bytes"] == required


def test_auditor_must_match_frozen_source_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auditor = tmp_path / "hpc_finished_audit.py"
    auditor.write_text("frozen auditor\n", encoding="utf-8")
    monkeypatch.setattr(dispatcher, "AUDITOR_SHA256", dispatcher.sha256_file(auditor))
    assert dispatcher.verify_auditor(auditor) == dispatcher.sha256_file(auditor)
    auditor.write_text("changed auditor\n", encoding="utf-8")
    with pytest.raises(dispatcher.DispatchError, match="frozen after-any auditor"):
        dispatcher.verify_auditor(auditor)


def test_child_submission_exports_source_root_independent_of_slurm_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object):
        commands.append(argv)
        return SimpleNamespace(returncode=0, stdout="991\n", stderr="")

    monkeypatch.setattr(dispatcher, "_run", fake_run)
    job_id, _, _recovered = dispatcher._submit_held(
        Path("/project/source/restart.sbatch"),
        "afterany:900",
        comment="rouaix-pcgdic-900-child",
        source_root=Path("/project/source"),
    )
    assert job_id == "991"
    assert "--export=ALL,ROUAIX_SOURCE_ROOT=/project/source" in commands[0]


def test_ambiguous_sbatch_result_is_reconciled_once_by_unique_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comment = "rouaix-pcgdic-900-child"
    readback = f"JobId=991 JobState=PENDING Reason=JobHeldUser Comment={comment}"
    commands: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object):
        commands.append(argv)
        if argv[0] == "sbatch":
            raise dispatcher.DispatchError("submission response timed out")
        if argv[0] == "squeue":
            return SimpleNamespace(returncode=0, stdout="991\n", stderr="")
        if argv[:2] == ["scontrol", "show"]:
            return SimpleNamespace(returncode=0, stdout=readback, stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(dispatcher, "_run", fake_run)
    job_id, _argv, recovered = dispatcher._submit_held(
        Path("/project/source/restart.sbatch"),
        "afterany:900",
        comment=comment,
    )
    assert job_id == "991"
    assert recovered is True
    assert sum(command[0] == "sbatch" for command in commands) == 1
