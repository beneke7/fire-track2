from __future__ import annotations

import hashlib
import io
import json
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cases.e1_rouaix_hpc import run_pilot


def _input_archive(path: Path, *, unsafe_name: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_audit = b'{"source":"synthetic"}\n'
    receipt = (
        '{"raw_audit_path":"raw-nozzle-audit.json","raw_audit_sha256":"'
        + hashlib.sha256(raw_audit).hexdigest()
        + '"}\n'
    ).encode()
    with tarfile.open(path, "w:gz") as archive:
        files = {
            "mesh-input/mesh-manifest.json": b'{"native_qa":{}}\n',
            "mesh-input/nozzle-audit.json": receipt,
            "mesh-input/raw-nozzle-audit.json": raw_audit,
            "mesh-input/checkMesh.log": b"Mesh OK.\n",
            **{
                f"mesh-input/constant/polyMesh/{name}": b"mesh fixture\n"
                for name in run_pilot.POLYMESH_FILES
            },
        }
        if unsafe_name:
            files[unsafe_name] = b"unexpected\n"
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path


def _tar_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_input_archive_extracts_only_bound_mesh_receipts_and_five_mesh_files(
    tmp_path: Path,
) -> None:
    archive = _input_archive(tmp_path / "mesh-input.tar.gz")
    members = run_pilot.validate_input_archive(archive)
    destination = tmp_path / "extract"
    run_pilot.extract_input_archive(archive, destination)
    inventory = run_pilot.validate_extracted_input_inventory(destination / "mesh-input", members)

    assert len(members) == len(run_pilot.REQUIRED_INPUTS)
    assert inventory == run_pilot.REQUIRED_INPUTS
    assert (destination / "mesh-input/mesh-manifest.json").is_file()
    assert all(
        (destination / "mesh-input/constant/polyMesh" / name).is_file()
        for name in run_pilot.POLYMESH_FILES
    )


@pytest.mark.parametrize("unsafe_name", ["../escape", "/absolute"])
def test_input_archive_rejects_unsafe_members(tmp_path: Path, unsafe_name: str) -> None:
    archive = _input_archive(tmp_path / "unsafe.tar.gz", unsafe_name=unsafe_name)
    with pytest.raises(run_pilot.PilotError):
        run_pilot.validate_input_archive(archive)


def test_input_archive_rejects_unbound_extra_files(tmp_path: Path) -> None:
    archive = _input_archive(tmp_path / "extra.tar.gz", unsafe_name="mesh-input/extra.json")
    members = run_pilot.validate_input_archive(archive)
    destination = tmp_path / "extract"
    run_pilot.extract_input_archive(archive, destination)
    with pytest.raises(run_pilot.PilotError, match="extra"):
        run_pilot.validate_extracted_input_inventory(destination / "mesh-input", members)


def test_raw_nozzle_audit_must_match_preserved_adapter_hash(tmp_path: Path) -> None:
    mesh_input = tmp_path / "mesh-input"
    mesh_input.mkdir()
    raw = mesh_input / "raw-nozzle-audit.json"
    raw.write_text('{"area_m2":0.125}\n', encoding="utf-8")
    receipt = mesh_input / "nozzle-audit.json"
    receipt.write_text(
        '{"raw_audit_path":"raw-nozzle-audit.json","raw_audit_sha256":"'
        + run_pilot.sha256_file(raw)
        + '"}\n',
        encoding="utf-8",
    )

    assert (
        run_pilot.validate_raw_nozzle_binding(mesh_input)["raw_audit_path"]
        == "raw-nozzle-audit.json"
    )
    raw.write_text('{"area_m2":0.126}\n', encoding="utf-8")
    with pytest.raises(run_pilot.PilotError, match="does not match"):
        run_pilot.validate_raw_nozzle_binding(mesh_input)


def test_monitor_accepts_initial_extrema_before_time_and_requires_strict_time_advance() -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=5.0)
    assert monitor.feed("max(mag(U)) = 3.0\n", 7.0) is None
    assert monitor.feed("Time = 0\n", 20.0) is None
    assert monitor.last_progress_monotonic == 5.0
    assert monitor.feed("Time = 0.001\n", 25.0) is None
    assert monitor.last_progress_monotonic == 25.0
    assert monitor.feed("max(mag(U)) = 4.5\n", 26.0) is None
    assert monitor.feed("Time = 0.002\n", 27.0) is None
    assert monitor.rows[-1] == (0.001, 4.5)


def test_clock_window_uses_physical_start_and_end_samples() -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=0.0)
    for time_s, clock_s in ((0.01, 10.0), (0.049, 13.9)):
        assert monitor.feed(f"Time = {time_s}\n", clock_s) is None
        assert monitor.feed("max(mag(U)) = 1\n", clock_s) is None
        assert (
            monitor.feed(f"ExecutionTime = {clock_s} s  ClockTime = {clock_s} s\n", clock_s) is None
        )
    window = run_pilot.solver_clock_window(monitor.clock_samples, 0.01, 0.049)
    assert window["status"] == "measured"
    assert window["physical_seconds"] == pytest.approx(0.039)
    assert window["solver_clock_seconds"] == pytest.approx(3.9)
    assert window["physical_seconds_per_solver_clock_second"] == pytest.approx(0.01)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Solving for p_rgh, Initial residual = nan\n", "nonfinite solver diagnostic"),
        ("max(mag(U)) = inf\n", "nonfinite solver diagnostic"),
        ("max(mag(U)) = 1000.01\n", "exceeds 1000 m/s"),
    ],
)
def test_monitor_stops_on_nonfinite_diagnostics_and_excess_speed(line: str, expected: str) -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=0.0, current_time_s=0.001)
    fault = monitor.feed(line, 1.0)
    assert fault is not None and expected in fault


def test_monitor_flags_missing_per_step_u_extrema() -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=0.0)
    assert monitor.feed("Time = 0.001\n", 1.0) is None
    fault = monitor.feed("Time = 0.002\n", 2.0)
    assert fault is not None and "missing per-step" in fault


def test_monitor_parses_native_min_max_pair_and_applies_speed_guard() -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=0.0)
    assert monitor.feed("Time = 0.001\n", 1.0) is None

    fault = monitor.feed("fieldMinMax speedExtrema write: min/max(mag(U)) = 0 92672390.4876\n", 2.0)

    assert fault is not None and "exceeds 1000 m/s" in fault
    assert monitor.maximum_u_m_s == pytest.approx(92_672_390.4876)


def test_monitor_rejects_truncated_native_min_max_pair() -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=0.0, current_time_s=0.001)
    fault = monitor.feed("fieldMinMax speedExtrema write: min/max(mag(U)) = 0\n", 2.0)
    assert fault == "fieldMinMax U min/max diagnostic is malformed"


def test_solver_gate_uses_active_final_criteria_and_accepts_799_iteration_pcorr(
    tmp_path: Path,
) -> None:
    fv_solution = Path("cases/e1_rouaix_hpc/template/system/fvSolution")
    log = tmp_path / "solver.log"
    log.write_text(
        "DICPCG: Solving for pcorr, Initial residual = 1, Final residual = 9.778e-11, No Iterations 799\n"
        "Time = 0.001000000000\nPIMPLE: iteration 1\n"
        "DILUPBiCGStab: Solving for Ux, Initial residual = 1, Final residual = 1.372, No Iterations 100\n"
        "DILUPBiCGStab: Solving for Uy, Initial residual = 1, Final residual = 0.0169, No Iterations 100\n"
        "DILUPBiCGStab: Solving for Uz, Initial residual = 1, Final residual = 0.0184, No Iterations 100\n"
        "GAMG: Solving for p_rgh, Initial residual = 0.904, Final residual = 0.00888, No Iterations 3\n"
        "GAMG: Solving for p_rgh, Initial residual = 0.864, Final residual = 0.00671, No Iterations 3\n"
        "GAMG: Solving for p_rgh, Initial residual = 0.879, Final residual = 6.049e-9, No Iterations 25\n"
        "smoothSolver: Solving for epsilon, Initial residual = 0.966, Final residual = 5.8e-9, No Iterations 48\n"
        "smoothSolver: Solving for k, Initial residual = 1, Final residual = 5.8e-9, No Iterations 38\n",
        encoding="utf-8",
    )

    result = run_pilot.inspect_solver_convergence(log, fv_solution)

    assert result["solver_record_count"] == 9
    assert result["all_converged"] is False
    assert result["by_field"]["pcorr"]["max_iterations"] == 799
    assert result["by_field"]["pcorr"]["failed_count"] == 0
    failed = result["failure_examples"]
    assert [item["field"] for item in failed] == ["Ux", "Uy", "Uz"]
    assert all(item["active_solver_entry"] == "UFinal" for item in failed)


def test_completion_monitor_supports_half_second_half_ms_case() -> None:
    monitor = run_pilot.OutputMonitor(last_progress_monotonic=0.0, horizon_s=0.5, delta_t_s=0.0005)
    for step in range(1, 1001):
        now = float(step)
        assert monitor.feed(f"Time = {step * 0.0005:.4f}\n", now) is None
        assert monitor.feed("max(mag(U)) = 10\n", now) is None
    assert monitor.feed("End\n", 1001.0) is None
    assert monitor.finish() is None
    assert len(monitor.rows) == 1000
    assert monitor.completion_fault() is None
    monitor.saw_end_marker = False
    assert "End completion marker" in monitor.completion_fault()


def test_cgroup_v2_memory_records_job_peak_and_postrun_current(tmp_path: Path) -> None:
    root = tmp_path / "cgroup"
    job = root / "slurm/uid_1000/job_45678"
    job.mkdir(parents=True)
    (job / "memory.peak").write_text("36000000000\n")
    (job / "memory.current").write_text("1000000\n")
    membership = tmp_path / "self.cgroup"
    membership.write_text("0::/slurm/uid_1000/job_45678/step_batch\n")

    record = run_pilot._cgroup_v2_memory("45678", membership_path=membership, cgroup_root=root)

    assert record == {
        "source": "cgroup-v2-job-scope",
        "path": str(job.resolve()),
        "memory_peak_bytes": 36_000_000_000,
        "memory_current_bytes_after_solver": 1_000_000,
    }


def test_default_pilot_configuration_preserves_frozen_first_capsule() -> None:
    assert run_pilot.PilotConfig() == run_pilot.PilotConfig(
        ranks=64,
        nodes=1,
        wall_budget_s=1200,
        horizon_s=0.05,
        delta_t_s=0.001,
        memory_gib=64,
        profiling=False,
    )
    assert (
        run_pilot.PilotConfig(numerical_variant="u_gradient_limited").validate().numerical_variant
        == "u_gradient_limited"
    )


@pytest.mark.parametrize("memory_gib", [True, 31, 65, 32.0])
def test_pilot_memory_declaration_requires_integer_32_through_64(memory_gib: object) -> None:
    with pytest.raises(run_pilot.PilotError, match="integer from 32 through 64"):
        run_pilot.PilotConfig(memory_gib=memory_gib).validate()  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "tamper",
    ["none", "gradient_metadata", "momentum_metadata", "unrelated_gradient"],
)
def test_prepared_gradient_variant_requires_exact_scheme_and_metadata_chain(
    tmp_path: Path, tamper: str
) -> None:
    template_path = (
        Path(__file__).resolve().parents[1] / "cases/e1_rouaix_hpc/template/system/fvSchemes"
    )
    parent_schemes = template_path.read_text(encoding="utf-8")
    source_line, diagnostic_line = run_pilot.FVSCHEMES_OVERRIDE_BY_VARIANT["u_gradient_limited"]
    assert parent_schemes.count(source_line) == 1
    schemes = parent_schemes.replace(source_line, diagnostic_line, 1)
    if tamper == "unrelated_gradient":
        schemes = schemes.replace("grad(k) Gauss linear;", "grad(k) cellLimited Gauss linear 1;", 1)

    case = tmp_path / "case"
    system = case / "system"
    system.mkdir(parents=True)
    (system / "fvSchemes").write_text(schemes, encoding="utf-8")
    (system / "controlDict").write_text(
        "stopAt endTime; endTime 0.01; deltaT 0.0005; adjustTimeStep no; "
        "runTimeModifiable false; fileHandler collated; maxThreadFileBufferSize 0; "
        "writeNowSignal 10; stopAtWriteNowSignal 12; writeInterval 0.01; purgeWrite 0; "
        "speedExtrema fieldMinMax mode magnitude;\n",
        encoding="utf-8",
    )
    parent_sha = hashlib.sha256(parent_schemes.encode()).hexdigest()
    post_sha = hashlib.sha256(schemes.encode()).hexdigest()
    gradient = "grad(U) cellLimited Gauss linear 1;"
    momentum = "limitedLinearV 1"
    if tamper == "gradient_metadata":
        gradient = "grad(U) Gauss linear;"
    elif tamper == "momentum_metadata":
        momentum = "upwind"
    metadata = {
        "execution_backend": "slurm-native",
        "solver_version": "v2512",
        "ranks": 64,
        "node_count": 1,
        "horizon_s": 0.01,
        "numerical_variant": "u_gradient_limited",
        "time_controls": {
            "delta_t_s": 0.0005,
            "fixed_delta_t": True,
            "adjust_time_step": False,
            "nAlphaSubCycles": 1,
            "snapshot_interval_s": 0.01,
            "purge_write": 0,
            "checkpoint_policy": {
                "scheduled_field_write_times_s": [0.0, 0.01],
                "retained_positive_checkpoint_limit": None,
                "preserve_initial_global_t0": True,
                "retain_all_per_step_metrics": True,
            },
            "full_field_write_times_s": [0.0, 0.01],
        },
        "source_dictionary_provenance": {"system/fvSchemes": {"sha256": parent_sha}},
        "resource_budget_provisional": {"memory_gib": 64},
        "profiling": False,
        "parent_fvSchemes_sha256": parent_sha,
        "post_override_fvSchemes_sha256": post_sha,
        "solver_dictionary_sha256": {"system/fvSchemes": post_sha},
        "actual_momentum_convection": momentum,
        "actual_velocity_gradient_scheme": gradient,
        "numerical_assumptions": {
            "numerical_variant": "u_gradient_limited",
            "momentum_convection": momentum,
            "velocity_gradient_scheme": gradient,
            "velocity_gradient_limiter_scope": (
                "cellLimited Gauss linear 1 on grad(U) only; grad(k) and grad(epsilon) unchanged"
            ),
            "velocity_gradient_diagnostic_note": (
                "OpenFOAM cellLimited Gauss linear 1 is a bounded diagnostic choice, not the "
                "Rouaix paper's Venkatakrishnan or hybrid least-squares scheme"
            ),
            "parent_fvSchemes_sha256": parent_sha,
            "post_override_fvSchemes_sha256": post_sha,
        },
    }
    (case / "case-inputs.json").write_text(json.dumps(metadata), encoding="utf-8")
    config = run_pilot.PilotConfig(
        horizon_s=0.01,
        delta_t_s=0.0005,
        numerical_variant="u_gradient_limited",
    )

    if tamper == "none":
        verified, hashes = run_pilot.validate_prepared_case(case, config)
        assert verified["actual_velocity_gradient_scheme"] == (
            "grad(U) cellLimited Gauss linear 1;"
        )
        assert hashes["system/fvSchemes"] == post_sha
    else:
        with pytest.raises(run_pilot.PilotError, match="does not match its declared variant"):
            run_pilot.validate_prepared_case(case, config)


def test_retention_is_full_by_default_and_minimum_disk_can_be_explicitly_lowered() -> None:
    config = run_pilot.PilotConfig()
    assert config.retention_mode == "full"
    assert config.minimum_free_disk_gib == 12
    assert run_pilot.PilotConfig(minimum_free_disk_gib=4).validate().minimum_free_disk_gib == 4
    with pytest.raises(run_pilot.PilotError, match="4 through 64"):
        run_pilot.PilotConfig(minimum_free_disk_gib=3).validate()


def test_diagnostic_retention_records_and_removes_only_large_fields_and_mesh(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    case = attempt / "case"
    for relative, contents in (
        ("0/U", "initial field"),
        ("0/alpha.water", "initial phase"),
        ("0.01/U", "final field"),
        ("constant/polyMesh/points", "mesh points"),
        ("processor0/0/U", "decomposed field"),
        ("processors64/constant/polyMesh/points", "collated mesh"),
        ("processors64/0/U", "collated initial field"),
        ("processors64/0.05/U", "collated checkpoint field"),
        ("constant/transportProperties", "water properties"),
        ("system/fvSchemes", "declared schemes"),
    ):
        path = case / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    (attempt / "ledger").mkdir(parents=True)
    (attempt / "ledger/flux.csv").write_text("time,water_flux\n", encoding="utf-8")
    (attempt / "manifest.json").write_text('{"source":"pinned"}\n', encoding="utf-8")
    (attempt / "source-provenance.json").write_text('{"solver":"v2512"}\n', encoding="utf-8")

    record = run_pilot.apply_diagnostic_retention(attempt, audit_exit_code=0)

    assert record["status"] == "complete"
    assert record["omitted_file_count"] == 8
    assert record["omitted_bytes"] > 0
    assert record["offline_mesh_or_field_reaudit_supported"] is False
    omitted = {item["path"] for item in record["omitted_paths"]}
    assert omitted == {
        "case/0",
        "case/0.01",
        "case/constant/polyMesh",
        "case/processor0",
        "case/processors64",
    }
    assert not (case / "0").exists()
    assert not (case / "0.01").exists()
    assert not (case / "constant/polyMesh").exists()
    assert not (case / "processor0").exists()
    assert not (case / "processors64").exists()
    assert (case / "constant/transportProperties").is_file()
    assert (case / "system/fvSchemes").is_file()
    assert (attempt / "ledger/flux.csv").is_file()
    assert json.loads((attempt / "manifest.json").read_text()) == {"source": "pinned"}
    assert json.loads((attempt / "source-provenance.json").read_text()) == {"solver": "v2512"}
    stored = json.loads((attempt / "retention-manifest.json").read_text(encoding="utf-8"))
    assert stored == record


def test_diagnostic_retention_refuses_to_run_after_failed_ledger_audit(tmp_path: Path) -> None:
    case = tmp_path / "attempt/case/0"
    case.mkdir(parents=True)
    field = case / "U"
    field.write_text("preserve me", encoding="utf-8")
    with pytest.raises(run_pilot.PilotError, match="successful compact-ledger audit"):
        run_pilot.apply_diagnostic_retention(case.parents[1], audit_exit_code=1)
    assert field.is_file()


def test_absolute_hard_deadline_utc_takes_precedence_and_rejects_local_times() -> None:
    start = 100.0
    now = run_pilot.datetime(2026, 10, 26, 5, 0, tzinfo=run_pilot.UTC)
    deadline = run_pilot.effective_stop_deadline(
        start,
        3600,
        "2026-10-26T05:30:00Z",
        utc_now=now,
    )
    assert deadline == pytest.approx(100 + 30 * 60 - run_pilot.CHECKPOINT_GRACE_S)
    with pytest.raises(run_pilot.PilotError, match="zero-offset UTC"):
        run_pilot.effective_stop_deadline(
            start,
            3600,
            "2026-10-26T07:30:00+02:00",
            utc_now=now,
        )


@pytest.mark.parametrize(
    ("ranks", "horizon_s", "delta_t_s", "steps", "numerical_variant"),
    [(120, 0.5, 0.001, 500, "original"), (96, 0.05, 0.0001, 500, "upwind")],
)
def test_supervisor_runs_declared_one_node_fixed_step_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ranks: int,
    horizon_s: float,
    delta_t_s: float,
    steps: int,
    numerical_variant: str,
) -> None:
    config = run_pilot.PilotConfig(
        ranks=ranks,
        nodes=1,
        horizon_s=horizon_s,
        delta_t_s=delta_t_s,
        numerical_variant=numerical_variant,
    )
    case, attempt, run_dir = (tmp_path / name for name in ("case", "attempt", "run"))
    case.mkdir()
    attempt.mkdir()
    run_dir.mkdir()
    captured: list[list[str]] = []
    state_snapshots: list[dict[str, object]] = []
    clock = {"now": 0.0}

    def monotonic_clock() -> float:
        current = clock["now"]
        clock["now"] += 0.01
        return current

    monkeypatch.setattr(run_pilot.time, "monotonic", monotonic_clock)
    monkeypatch.setattr(run_pilot, "STATE_INTERVAL_S", 6.0)

    class CompleteSolver:
        returncode = 0

        def __init__(self, command, *, stdout, **_kwargs):
            captured.append(command)
            lines = ["Time = 0\n"]
            lines.extend(
                line
                for step in range(1, steps + 1)
                for line in (
                    f"Time = {step * config.delta_t_s:.12g}\n",
                    f"max(mag(U)) = {300 if step == steps else 20}\n",
                )
            )
            stdout.writelines([*lines, "End\n"])
            stdout.flush()

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(run_pilot.subprocess, "Popen", CompleteSolver)
    monkeypatch.setattr(run_pilot, "_record_disk_space", lambda _state, *_paths: 100 * 1024**3)

    def capture_state(snapshot: dict[str, object]) -> None:
        state_snapshots.append(dict(snapshot))

    state = {"solver_started_monotonic": run_pilot.time.monotonic()}
    return_code, monitor, stop_reason, paused = run_pilot.supervise_solver(
        case=case,
        attempt=attempt,
        run_dir=run_dir,
        shared_pause=tmp_path / "shared-PAUSE",
        project_root=tmp_path,
        job_id="45678",
        config=config,
        deadline=time.monotonic() + 1000,
        state=state,
        write_state=capture_state,
    )

    assert return_code == 0 and stop_reason is None and not paused
    assert monitor.completion_fault() is None and len(monitor.rows) == steps
    assert state_snapshots
    assert state_snapshots[-1]["max_u_seen_m_s"] == pytest.approx(20)
    assert monitor.rows[-1] == pytest.approx((horizon_s, 300))
    assert state["max_u_seen_m_s"] == pytest.approx(300)
    assert state["solver_max_u_m_s"] == pytest.approx(300)
    assert state["solver_wall_s"] >= 0
    assert (attempt / "solver.log").read_text(encoding="utf-8").rstrip().endswith("End")
    assert (
        (attempt / "max-speed.csv")
        .read_text(encoding="utf-8")
        .rstrip()
        .endswith(f"{horizon_s:g},300")
    )
    assert "--nodes=1" in captured[0]
    assert f"--ntasks={ranks}" in captured[0]
    assert f"--ntasks-per-node={ranks}" in captured[0]
    assert "Cpus_allowed_list" in (attempt / "solver-step.sh").read_text()
    assert any(
        item.startswith("--export=ALL,ROUAIX_STEP_IDENTITY=") and "ROUAIX_RANK0_AFFINITY=" in item
        for item in captured[0]
    )


@pytest.mark.parametrize(
    ("ranks", "nodes", "tasks_per_node", "cpus_on_node"),
    [
        (24, 1, "24", 24),
        (64, 1, "64", 64),
        (96, 1, "96", 96),
        (120, 1, "120", 120),
        (240, 2, "120(x2)", 120),
        (300, 3, "100(x3)", 100),
    ],
)
def test_allocation_matches_declared_placement_and_records_resources(
    ranks: int, nodes: int, tasks_per_node: str, cpus_on_node: int
) -> None:
    config = run_pilot.PilotConfig(ranks=ranks, nodes=nodes, wall_budget_s=1800, horizon_s=0.5)
    env = {
        "SLURM_JOB_NAME": run_pilot.JOB_NAME,
        "SLURM_JOB_ACCOUNT": "nk_meshapplied",
        "SLURM_JOB_NUM_NODES": str(nodes),
        "SLURM_NTASKS": str(ranks),
        "SLURM_TASKS_PER_NODE": tasks_per_node,
        "SLURM_CPUS_PER_TASK": "1",
        "SLURM_CPUS_ON_NODE": str(cpus_on_node),
        "SLURM_MEM_PER_NODE": "98304",
        "SLURM_JOB_NODELIST": "nid[001-003]",
    }
    allocation = run_pilot._validate_allocation(config, env)
    assert allocation["nodes"] == nodes
    assert allocation["ranks"] == ranks
    assert allocation["memory_mb_per_node"] == 98304
    assert allocation["memory_gib_per_node"] == 96
    assert allocation["memory_gib_total"] == 96 * nodes


def test_allocation_rejects_wrong_tasks_per_node_distribution() -> None:
    config = run_pilot.PilotConfig(ranks=240, nodes=2, wall_budget_s=1800)
    env = {
        "SLURM_JOB_NAME": run_pilot.JOB_NAME,
        "SLURM_JOB_ACCOUNT": "nk_meshapplied",
        "SLURM_JOB_NUM_NODES": "2",
        "SLURM_NTASKS": "240",
        "SLURM_TASKS_PER_NODE": "240",
        "SLURM_CPUS_PER_TASK": "1",
        "SLURM_CPUS_ON_NODE": "240",
        "SLURM_MEM_PER_NODE": "65536",
    }
    with pytest.raises(run_pilot.PilotError, match="tasks per node"):
        run_pilot._validate_allocation(config, env)


@pytest.mark.parametrize(
    ("declared_memory_gib", "allocated_memory_mb", "accepted"),
    [
        (32, 32768, True),
        (32, 32767, False),
        (48, 49152, True),
        (48, 49151, False),
        (64, 32768, False),
    ],
)
def test_allocation_enforces_declared_memory_floor_for_24_rank_placement(
    declared_memory_gib: int, allocated_memory_mb: int, accepted: bool
) -> None:
    config = run_pilot.PilotConfig(
        ranks=24, nodes=1, wall_budget_s=1800, memory_gib=declared_memory_gib
    )
    env = {
        "SLURM_JOB_NAME": run_pilot.JOB_NAME,
        "SLURM_JOB_ACCOUNT": "nk_meshapplied",
        "SLURM_JOB_NUM_NODES": "1",
        "SLURM_NTASKS": "24",
        "SLURM_TASKS_PER_NODE": "24",
        "SLURM_CPUS_PER_TASK": "1",
        "SLURM_CPUS_ON_NODE": "24",
        "SLURM_MEM_PER_NODE": str(allocated_memory_mb),
    }
    if accepted:
        allocation = run_pilot._validate_allocation(config, env)
        assert allocation["memory_gib_declared_per_node"] == declared_memory_gib
        assert allocation["memory_gib_per_node"] == (allocated_memory_mb + 1023) // 1024
    else:
        with pytest.raises(run_pilot.PilotError, match="declared .* GiB per-node floor"):
            run_pilot._validate_allocation(config, env)


def test_multinode_workspace_uses_quota_checked_shared_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared-project"
    shared.mkdir()
    monkeypatch.setattr(
        run_pilot,
        "select_node_local_workspace",
        lambda *_args, **_kwargs: pytest.fail("multi-node runs must not select node-local storage"),
    )
    monkeypatch.setattr(
        run_pilot.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=30 * 1024**3, used=10 * 1024**3, free=20 * 1024**3),
    )
    monkeypatch.setattr(run_pilot, "_filesystem_details", lambda _path: ("lustre", "project-fs"))

    workspace, record = run_pilot.create_workspace(
        {"ROUAIX_PROJECT_ROOT": str(shared)}, "45678", nodes=2
    )

    assert workspace.parent == shared
    assert record["storage_class"] == "shared-project-scratch-required-for-multinode"
    assert record["free_bytes_at_selection"] == 20 * 1024**3
    run_pilot.clean_owned_workspace(workspace, shared, "45678")


def test_multinode_workspace_rejects_shared_scratch_below_12_gib(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared-project"
    shared.mkdir()
    monkeypatch.setattr(
        run_pilot.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=30 * 1024**3, used=19 * 1024**3, free=11 * 1024**3),
    )
    with pytest.raises(run_pilot.PilotError, match="shared project scratch"):
        run_pilot.create_workspace({"ROUAIX_PROJECT_ROOT": str(shared)}, "45678", nodes=2)


def test_one_node_can_require_shared_workspace_and_records_storage_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared-project"
    shared.mkdir()
    sentinel = shared / "preserve-me"
    sentinel.write_text("existing evidence", encoding="utf-8")
    monkeypatch.setattr(
        run_pilot,
        "select_node_local_workspace",
        lambda *_args, **_kwargs: pytest.fail(
            "explicit shared mode must not use node-local storage"
        ),
    )
    monkeypatch.setattr(
        run_pilot.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=30 * 1024**3, used=10 * 1024**3, free=20 * 1024**3),
    )
    monkeypatch.setattr(run_pilot, "_filesystem_details", lambda _path: ("lustre", "project-fs"))

    workspace, record = run_pilot.create_workspace(
        {
            "ROUAIX_PROJECT_ROOT": str(shared),
            "ROUAIX_REQUIRE_SHARED_WORKSPACE": "1",
        },
        "45678",
        nodes=1,
    )

    assert workspace.parent == shared
    assert record["storage_class"] == "shared-project-scratch-required"
    assert sentinel.read_text(encoding="utf-8") == "existing evidence"
    run_pilot.clean_owned_workspace(workspace, shared, "45678")
    assert sentinel.read_text(encoding="utf-8") == "existing evidence"


def test_one_node_required_shared_workspace_rejects_invalid_setting_and_low_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared-project"
    shared.mkdir()
    sentinel = shared / "preserve-me"
    sentinel.write_text("existing evidence", encoding="utf-8")
    monkeypatch.setattr(
        run_pilot,
        "select_node_local_workspace",
        lambda *_args, **_kwargs: pytest.fail(
            "required shared mode must not fall back to node-local"
        ),
    )
    with pytest.raises(run_pilot.PilotError, match="must be 0 or 1"):
        run_pilot.create_workspace(
            {"ROUAIX_PROJECT_ROOT": str(shared), "ROUAIX_REQUIRE_SHARED_WORKSPACE": "true"},
            "45678",
            nodes=1,
        )

    monkeypatch.setattr(
        run_pilot.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=30 * 1024**3, used=19 * 1024**3, free=11 * 1024**3),
    )
    with pytest.raises(run_pilot.PilotError, match="required shared workspace"):
        run_pilot.create_workspace(
            {
                "ROUAIX_PROJECT_ROOT": str(shared),
                "ROUAIX_REQUIRE_SHARED_WORKSPACE": "1",
            },
            "45678",
            nodes=1,
        )
    assert list(shared.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "existing evidence"


def test_monitor_pause_no_progress_deadline_and_disk_guards() -> None:
    common = {
        "now": 100.0,
        "deadline": 1000.0,
        "last_progress": 100.0,
        "paused": False,
        "free_disk_bytes": run_pilot.MIN_FREE_DISK_BYTES,
    }
    assert run_pilot.monitor_stop_reason(**{**common, "paused": True}) == (
        "user PAUSE marker",
        True,
    )
    assert "600 s" in run_pilot.monitor_stop_reason(**{**common, "now": 701.0})[0]
    assert "deadline" in run_pilot.monitor_stop_reason(**{**common, "now": 1000.0})[0]
    assert (
        "disk"
        in run_pilot.monitor_stop_reason(
            **{**common, "free_disk_bytes": run_pilot.MIN_FREE_DISK_BYTES - 1}
        )[0]
    )
    assert run_pilot.monitor_stop_reason(**common) is None


def test_cancel_targets_only_verified_own_solver_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "step.txt"
    identity.write_text("12345 0 64 0\n", encoding="ascii")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "scontrol":
            return SimpleNamespace(
                returncode=0,
                stdout="StepId=12345.0 UserId=16018(ben) CPUs=64 Tasks=64 Name=interIsoFoam State=RUNNING\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_pilot.subprocess, "run", fake_run)
    assert run_pilot.signal_owned_step("12345", identity, "12")
    assert commands[-1] == ["scancel", "--signal=12", "12345.0"]


@pytest.mark.parametrize(("ranks", "tasks_per_node"), [(120, "120"), (240, "120(x2)")])
def test_cancel_targets_verified_dynamic_rank_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ranks: int,
    tasks_per_node: str,
) -> None:
    identity = tmp_path / "step.txt"
    identity.write_text(f"12345 0 {ranks} 0\n", encoding="ascii")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "scontrol":
            return SimpleNamespace(
                returncode=0,
                stdout=f"StepId=12345.0 UserId=16018(v) CPUs={ranks} Tasks={ranks} Name=interIsoFoam State=RUNNING\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_pilot.subprocess, "run", fake_run)
    assert run_pilot.signal_owned_step("12345", identity, "12", expected_ranks=ranks)
    assert commands[-1] == ["scancel", "--signal=12", "12345.0"]
    assert run_pilot._tasks_per_node(tasks_per_node) == ((120,) if ranks == 120 else (120, 120))


def test_cancel_refuses_step_identity_mismatch_before_scancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "step.txt"
    identity.write_text("12345 0 63 0\n", encoding="ascii")
    called = []
    monkeypatch.setattr(run_pilot.subprocess, "run", lambda *args, **kwargs: called.append(args))
    with pytest.raises(run_pilot.PilotError, match="rank count"):
        run_pilot.signal_owned_step("12345", identity, "12")
    assert called == []


@pytest.mark.parametrize(
    "record",
    [
        "StepId=12345.extern UserId=16018(v) CPUs=0 Tasks=1 Name=extern State=RUNNING\n",
        "StepId=12345.0 UserId=16018(v) CPUs=63 Tasks=63 Name=interIsoFoam State=RUNNING\n",
    ],
)
def test_cancel_rejects_non_solver_scontrol_record_before_scancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    identity = tmp_path / "step.txt"
    identity.write_text("12345 0 64 0\n", encoding="ascii")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=record, stderr="")

    monkeypatch.setattr(run_pilot.subprocess, "run", fake_run)
    with pytest.raises(run_pilot.PilotError, match="conflicts"):
        run_pilot.signal_owned_step("12345", identity, "12")
    assert len(commands) == 1 and commands[0][:3] == ["scontrol", "show", "step"]


def test_archive_crc_hash_and_member_list_are_verified_before_owned_cleanup(
    tmp_path: Path,
) -> None:
    base = tmp_path / "node-local"
    workspace = base / "rouaix-e1hpc-12345.fixture"
    attempt = workspace / "attempt"
    (attempt / "case/0").mkdir(parents=True)
    (attempt / "case/0/U").write_text("field\n", encoding="utf-8")
    (attempt / "manifest.json").write_text("{}\n", encoding="utf-8")
    run_dir = tmp_path / "shared" / "rouaix-e1-hpc-pilot-12345"
    run_dir.mkdir(parents=True)

    archive, digest, member_count, member_sizes = run_pilot.pack_attempt(attempt, run_dir)
    expected = [name for _path, name in run_pilot._attempt_inventory(attempt)]
    assert run_pilot.verify_result_archive(archive, expected) == digest == _tar_sha(archive)
    assert member_count == len(expected)
    with tarfile.open(archive, "r:gz") as packed:
        tarinfo_sizes = {
            member.name: member.size for member in packed.getmembers() if member.isfile()
        }
    assert {row["path"]: row["bytes"] for row in member_sizes} == tarinfo_sizes
    assert (run_dir / "result.tar.gz.sha256").read_text().startswith(digest)

    run_pilot.clean_owned_workspace(workspace, base, "12345")
    assert not workspace.exists()


def test_checkpoint_retention_preserves_global_t0_and_caps_positive_times(tmp_path: Path) -> None:
    case = tmp_path / "case"
    (case / "0").mkdir(parents=True)
    initial = case / "0/U"
    initial.write_text("immutable initial field\n", encoding="utf-8")
    hashes = {"0/U": run_pilot.sha256_file(initial)}
    processors = case / "processors64"
    for value in ("0", "1", "2"):
        (processors / value).mkdir(parents=True)

    result = run_pilot.verify_checkpoint_retention(case, hashes, horizon_s=5.0)
    assert result["initial_global_t0_preserved"] is True
    assert result["positive_checkpoint_times_s"] == [1.0, 2.0]

    (processors / "3").mkdir()
    with pytest.raises(run_pilot.PilotError, match="more than two"):
        run_pilot.verify_checkpoint_retention(case, hashes, horizon_s=5.0)
    initial.write_text("changed\n", encoding="utf-8")
    with pytest.raises(run_pilot.PilotError, match="immutable initial field"):
        run_pilot.verify_checkpoint_retention(case, hashes, horizon_s=0.5)


def test_owned_cleanup_rejects_workspace_outside_job_prefix(tmp_path: Path) -> None:
    base = tmp_path / "node-local"
    base.mkdir()
    workspace = tmp_path / "unrelated"
    workspace.mkdir()
    with pytest.raises(run_pilot.PilotError, match="refusing to remove"):
        run_pilot.clean_owned_workspace(workspace, base, "12345")
    assert workspace.is_dir()


def test_pilot_sbatch_is_valid_bash() -> None:
    script = Path(__file__).resolve().parents[1] / "cases/e1_rouaix_hpc/pilot.sbatch"
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    text = script.read_text(encoding="utf-8")
    assert 'exec python3 "$PROJECT_ROOT/cases/e1_rouaix_hpc/run_pilot.py"' in text
    assert "STAGE=complete" not in text


def test_stop_signal_source_resolves_and_hashes_installed_cxx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_pilot.STOP_SIGNAL_SOURCE_SHA256 == (
        "5571278a48efd49507546d9ac4aa419519010d5a2de822992d53e287761a7a03"
    )
    assert run_pilot.STOP_SIGNAL_SOURCE_RELATIVE.as_posix() == (
        "src/OSspecific/POSIX/signals/sigStopAtWriteNow.cxx"
    )
    project = tmp_path / "openfoam-v2512"
    source = project / run_pilot.STOP_SIGNAL_SOURCE_RELATIVE
    source.parent.mkdir(parents=True)
    source_bytes = b"const label stopAtWriteNowSignal = 12;\nTime::saWriteNow();\n"
    source.write_bytes(source_bytes)
    monkeypatch.setattr(
        run_pilot, "STOP_SIGNAL_SOURCE_SHA256", hashlib.sha256(source_bytes).hexdigest()
    )
    attempt = tmp_path / "attempt"
    evidence_dir = attempt / "input-evidence"
    evidence_dir.mkdir(parents=True)
    banner = evidence_dir / "checkMesh.log"
    banner.write_text(
        "sigStopAtWriteNow : Enabling writing and stopping upon signal 12\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "native-source-evidence.json"
    evidence.write_text(
        json.dumps({"native_solver": {"wm_project_dir": str(project)}}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"native_source_evidence_path": str(evidence)}), encoding="utf-8"
    )

    record = run_pilot.verify_stop_signal_source(attempt, manifest)

    assert record["requested_path"] == str(source)
    assert record["path"] == str(source)
    assert record["resolved_symlink"] is False
    assert record["sha256"] == hashlib.sha256(source_bytes).hexdigest()


@pytest.mark.parametrize(
    (
        "completed_steps",
        "end_marker",
        "expected_status",
        "expected_result",
        "inject_unexpected_solver_error",
        "max_speed_line",
        "retention_mode",
        "numerical_variant",
        "profiling",
    ),
    [
        (50, True, "solver_complete_exploratory", 0, False, None, "full", "original", False),
        (25, False, "stopped_with_preserved_evidence", 1, False, None, "full", "original", False),
        (0, False, "failed_preserved", 1, True, None, "full", "original", False),
        (
            1,
            False,
            "stopped_with_preserved_evidence",
            1,
            False,
            "fieldMinMax speedExtrema write: min/max(mag(U)) = 0 92672390.4876\n",
            "full",
            "original",
            False,
        ),
        (50, True, "solver_complete_exploratory", 0, False, None, "diagnostic", "original", False),
        (
            50,
            True,
            "solver_complete_exploratory",
            0,
            False,
            None,
            "full",
            "u_gradient_limited",
            False,
        ),
        (50, True, "solver_complete_exploratory", 0, False, None, "full", "original", True),
    ],
)
def test_synthetic_native_setup_and_srun_lifecycle_completion_and_frozen_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completed_steps: int,
    end_marker: bool,
    expected_status: str,
    expected_result: int,
    inject_unexpected_solver_error: bool,
    max_speed_line: str | None,
    retention_mode: str,
    numerical_variant: str,
    profiling: bool,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    job_id = "45678"
    run_dir = project_root / f"rouaix-e1-hpc-pilot-{job_id}"
    run_dir.mkdir()
    (run_dir / "modules.log").write_text("OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH\n", encoding="utf-8")
    archive = _input_archive(project_root / "mesh-input.tar.gz")
    local = tmp_path / "node-local"
    local.mkdir()

    monkeypatch.setenv("SLURM_JOB_ID", job_id)
    monkeypatch.setenv("SLURM_JOB_NAME", run_pilot.JOB_NAME)
    monkeypatch.setenv("SLURM_JOB_ACCOUNT", "nk_meshapplied")
    monkeypatch.setenv("SLURM_JOB_NUM_NODES", "1")
    monkeypatch.setenv("SLURM_NTASKS", "64")
    monkeypatch.setenv("SLURM_TASKS_PER_NODE", "64")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "1")
    monkeypatch.setenv("SLURM_CPUS_ON_NODE", "64")
    monkeypatch.setenv("SLURM_MEM_PER_NODE", "65536")
    monkeypatch.setenv("ROUAIX_PROJECT_ROOT", str(project_root))
    monkeypatch.setattr(
        run_pilot,
        "select_node_local_workspace",
        lambda _env, **_kwargs: (
            local,
            {
                "path": str(local),
                "filesystem_type": "xfs",
                "filesystem_source": "/dev/mock",
                "free_bytes_at_selection": 100 * 1024**3,
                "storage_class": "node-local-block",
            },
        ),
    )
    monkeypatch.setattr(
        run_pilot.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=200 * 1024**3, used=1, free=100 * 1024**3),
    )
    monkeypatch.setattr(run_pilot, "_git_record", lambda: {"revision": "fixture", "dirty": False})
    monkeypatch.setattr(run_pilot, "_cgroup_v2_memory", lambda _job_id: None)

    def fake_prepare_case(command, **_kwargs):
        assert "prepare_case.py" in command[1]
        assert command[command.index("--timeout-s") + 1] == "1200"
        assert command[command.index("--nodes") + 1] == "1"
        assert command[command.index("--end-time-s") + 1] == "0.05"
        assert command[command.index("--delta-t-s") + 1] == "0.001"
        assert command[command.index("--numerical-variant") + 1] == numerical_variant
        assert command[command.index("--write-interval-s") + 1] == "0.05"
        assert command[command.index("--memory-gib") + 1] == "64"
        assert ("--profiling" in command) is profiling
        case = Path(command[command.index("--output-dir") + 1])
        attempt = case.parent
        progression = attempt / "experiment-progression.md"
        expected_progression = (
            Path(run_pilot.ROOT) / "experiments/E1_ROUAIX_HPC_PROGRESSION.md"
        ).read_bytes()
        assert progression.read_bytes() == expected_progression
        assert b"S1-ORIG-96-01MS-005" in expected_progression
        staged_state = json.loads((run_dir / "run-state.json").read_text(encoding="utf-8"))
        assert staged_state["primary_experiment_declaration"] == {
            "path": "experiment-progression.md",
            "sha256": hashlib.sha256(expected_progression).hexdigest(),
        }
        (case / "system").mkdir(parents=True)
        template_path = Path(run_pilot.ROOT) / "cases/e1_rouaix_hpc/template/system/fvSchemes"
        parent_schemes = template_path.read_text(encoding="utf-8")
        schemes_text = parent_schemes
        override = run_pilot.FVSCHEMES_OVERRIDE_BY_VARIANT.get(numerical_variant)
        if override is not None:
            original_scheme, diagnostic_scheme = override
            schemes_text = parent_schemes.replace(original_scheme, diagnostic_scheme, 1)
        (case / "system/fvSchemes").write_text(schemes_text, encoding="utf-8")
        schemes_sha = hashlib.sha256(schemes_text.encode()).hexdigest()
        parent_sha = hashlib.sha256(parent_schemes.encode()).hexdigest()
        expected_momentum = run_pilot.MOMENTUM_CONVECTION_BY_VARIANT[numerical_variant]
        expected_gradient = run_pilot.VELOCITY_GRADIENT_BY_VARIANT[numerical_variant]
        limiter_scope = (
            "cellLimited Gauss linear 1 on grad(U) only; grad(k) and grad(epsilon) unchanged"
            if numerical_variant == "u_gradient_limited"
            else "no velocity-gradient limiter override"
        )
        limiter_note = (
            "OpenFOAM cellLimited Gauss linear 1 is a bounded diagnostic choice, not the "
            "Rouaix paper's Venkatakrishnan or hybrid least-squares scheme"
            if numerical_variant == "u_gradient_limited"
            else None
        )
        control_text = (
            "application interIsoFoam; stopAt endTime; endTime 0.05; deltaT 0.001; "
            "adjustTimeStep no; runTimeModifiable false; writeNowSignal 10; "
            "fileHandler collated; maxThreadFileBufferSize 0; stopAtWriteNowSignal 12; "
            "writeInterval 0.05; purgeWrite 0; speedExtrema fieldMinMax mode magnitude;\n"
        )
        if profiling:
            control_text += (
                "profiling\n{\n    active true;\n    cpuInfo false;\n"
                "    memInfo false;\n    sysInfo false;\n}\n"
            )
        (case / "system/controlDict").write_text(control_text, encoding="utf-8")
        (case / "system/fvSolution").write_text(
            "solvers\n{\n"
            "    U\n    {\n        solver PBiCGStab;\n        tolerance 1e-8;\n"
            "        relTol 0.1;\n        maxIter 100;\n    }\n}\n"
            "PIMPLE\n{\n    nOuterCorrectors 1;\n    nCorrectors 3;\n"
            "    nNonOrthogonalCorrectors 0;\n}\n",
            encoding="utf-8",
        )
        (case / "0").mkdir()
        (case / "0/U").write_text("U fixture\n", encoding="utf-8")
        (case / "case-inputs.json").write_text(
            json.dumps(
                {
                    "execution_backend": "slurm-native",
                    "solver_version": "v2512",
                    "reference_image_digest": "sha256:fixture",
                    "ranks": 64,
                    "node_count": 1,
                    "horizon_s": 0.05,
                    "numerical_variant": numerical_variant,
                    "profiling": profiling,
                    "resource_budget_provisional": {"memory_gib": 64},
                    "parent_fvSchemes_sha256": parent_sha,
                    "post_override_fvSchemes_sha256": schemes_sha,
                    "actual_momentum_convection": expected_momentum,
                    "actual_velocity_gradient_scheme": expected_gradient,
                    "solver_dictionary_sha256": {"system/fvSchemes": schemes_sha},
                    "source_dictionary_provenance": {"system/fvSchemes": {"sha256": parent_sha}},
                    "numerical_assumptions": {
                        "numerical_variant": numerical_variant,
                        "momentum_convection": expected_momentum,
                        "velocity_gradient_scheme": expected_gradient,
                        "velocity_gradient_limiter_scope": limiter_scope,
                        "velocity_gradient_diagnostic_note": limiter_note,
                        "parent_fvSchemes_sha256": parent_sha,
                        "post_override_fvSchemes_sha256": schemes_sha,
                    },
                    "time_controls": {
                        "delta_t_s": 0.001,
                        "fixed_delta_t": True,
                        "adjust_time_step": False,
                        "nAlphaSubCycles": 1,
                        "snapshot_interval_s": 0.05,
                        "purge_write": 0,
                        "checkpoint_policy": {
                            "scheduled_field_write_times_s": [0.0, 0.05],
                            "retained_positive_checkpoint_limit": None,
                            "preserve_initial_global_t0": True,
                            "retain_all_per_step_metrics": True,
                        },
                        "full_field_write_times_s": [0.0, 0.05],
                    },
                }
            ),
            encoding="utf-8",
        )

    fake_commands: list[list[str]] = []
    active_solver = []

    class FakeProcess:
        def __init__(self, command, *, stdout=None, env=None, **_kwargs):
            self.command = list(command)
            fake_commands.append(self.command)
            self.returncode = 0
            self.waited = False
            if self.command[0] == sys.executable and "prepare_case.py" in self.command[1]:
                fake_prepare_case(self.command)
            elif self.command[0] == "srun":
                assert "--ntasks=64" in self.command
                assert "--nodes=1" in self.command
                assert "--ntasks-per-node=64" in self.command
                assert "--cpus-per-task=1" in self.command
                assert "interIsoFoam" in Path(self.command[-1]).read_text(encoding="utf-8")
                if inject_unexpected_solver_error or max_speed_line:
                    self.returncode = None
                    identity = Path(env["ROUAIX_STEP_IDENTITY"])
                    identity.write_text("45678 0 64 0\n", encoding="ascii")
                    active_solver.append(self)
                if max_speed_line:
                    lines = ["Time = 0\n", "Time = 0.001\n", max_speed_line]
                else:
                    lines = ["max(mag(U)) = 0\n", "Time = 0\n"]
                    lines.extend(
                        line
                        for step in range(1, completed_steps + 1)
                        for line in (
                            f"Time = {step / 1000:.3f}\n",
                            "Solving for Ux, Initial residual = 1, Final residual = 1e-9, No Iterations 2\n",
                            "max(mag(U)) = 20\n",
                        )
                    )
                if end_marker:
                    lines.append("End\n")
                stdout.writelines(lines)
                stdout.flush()

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.waited = True
            return self.returncode

        def terminate(self):
            self.returncode = -signal.SIGTERM

        def kill(self):
            self.returncode = -signal.SIGKILL

    monkeypatch.setattr(run_pilot.subprocess, "Popen", FakeProcess)

    def fake_run(command, **_kwargs):
        if command[0] == "scontrol":
            return SimpleNamespace(
                returncode=0,
                stdout="StepId=45678.0 UserId=16018(v) CPUs=64 Tasks=64 Name=interIsoFoam State=RUNNING\n",
                stderr="",
            )
        if command[0] == "scancel":
            active_solver[0].returncode = 0
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[0] in {"sstat", "sacct"}:
            return SimpleNamespace(returncode=0, stdout="fixture accounting\n", stderr="")
        if command and command[0] == sys.executable and "audit_iso_vof_ledger.py" in command[1]:
            attempt_path = Path(command[command.index("--run-dir") + 1])
            solver_log = Path(command[command.index("--solver-log") + 1])
            assert solver_log == attempt_path / "solver.log"
            assert (attempt_path / "case/0/U").is_file()
            return SimpleNamespace(returncode=0, stdout="fixture audit\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_pilot.subprocess, "run", fake_run)

    original_pause_present = run_pilot.pause_present

    def raise_after_solver_starts(*args):
        if inject_unexpected_solver_error and active_solver:
            raise RuntimeError("injected monitor failure after srun launch")
        return original_pause_present(*args)

    monkeypatch.setattr(run_pilot, "pause_present", raise_after_solver_starts)

    original_pack_attempt = run_pilot.pack_attempt

    def pack_only_after_solver_reaped(attempt, destination):
        if inject_unexpected_solver_error:
            assert active_solver and active_solver[0].returncode is not None
            assert active_solver[0].waited
        return original_pack_attempt(attempt, destination)

    monkeypatch.setattr(run_pilot, "pack_attempt", pack_only_after_solver_reaped)

    def fake_collect(*, output_path, run_manifest_path, **_kwargs):
        evidence = output_path
        evidence.write_text("{}\n", encoding="utf-8")
        manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        manifest.update(
            native_source_evidence_path=str(evidence),
            native_source_evidence_sha256=run_pilot.sha256_file(evidence),
            execution_backend="slurm-native",
            solver_version="v2512",
        )
        run_pilot.write_json(run_manifest_path, manifest)

    from cases.e1_rouaix_hpc import collect_native_provenance as collector

    monkeypatch.setattr(collector, "collect_native_provenance", fake_collect)
    monkeypatch.setattr(run_pilot, "verify_stop_signal_source", lambda _attempt, _manifest: {})

    original_term = signal.signal(signal.SIGTERM, signal.getsignal(signal.SIGTERM))
    original_int = signal.signal(signal.SIGINT, signal.getsignal(signal.SIGINT))
    try:
        result = run_pilot.run_pilot(
            run_dir=run_dir,
            input_archive=archive,
            input_sha256=_tar_sha(archive),
            shared_pause=tmp_path / "shared-PAUSE",
            config=run_pilot.PilotConfig(
                retention_mode=retention_mode,
                numerical_variant=numerical_variant,
                profiling=profiling,
            ),
        )
    finally:
        signal.signal(signal.SIGTERM, original_term)
        signal.signal(signal.SIGINT, original_int)

    state = json.loads((run_dir / "run-state.json").read_text(encoding="utf-8"))
    assert result == expected_result
    assert state["status"] == expected_status
    assert state["attempt_archive_status"] == "verified_crc_hash_and_member_list"
    assert state["retention_mode"] == retention_mode
    assert state["memory_gib"] == 64
    assert state["profiling"] is profiling
    if expected_status != "failed_preserved":
        assert state["memory_measurement_source"] == "sacct MaxRSS fallback"
    if inject_unexpected_solver_error:
        assert active_solver[0].waited
        assert state["cleanup_stop_signals"] == ["12"]
        assert "injected monitor failure" in state["error"]
    elif max_speed_line:
        assert active_solver[0].waited
        assert state["stop_signals"] == ["12"]
        assert "exceeds 1000 m/s" in state["stop_reason"]
        assert state["solver_max_u_m_s"] == pytest.approx(92_672_390.4876)
    else:
        assert state["solver_time_steps_recorded"] == completed_steps
        assert state["solver_end_marker"] is end_marker
        assert state["solver_wall_s"] >= 0
        if not end_marker:
            assert "does not prove all 50 fixed" in state["stop_reason"]
    assert any(command[:2] == ["decomposePar", "-force"] for command in fake_commands)
    with tarfile.open(run_dir / "result.tar.gz", "r:gz") as result_archive:
        manifest = json.load(result_archive.extractfile("attempt/manifest.json"))
        control = result_archive.extractfile("attempt/case/system/controlDict").read()
        result_members = {member.name for member in result_archive.getmembers()}
        if retention_mode == "diagnostic" and expected_status == "solver_complete_exploratory":
            retention = json.load(result_archive.extractfile("attempt/retention-manifest.json"))
            assert retention["status"] == "complete"
            assert "attempt/case/0/U" not in result_members
        else:
            assert "attempt/case/0/U" in result_members
    assert (
        manifest["prepared_case_sha256"]["system/controlDict"]
        == hashlib.sha256(control).hexdigest()
    )
    assert manifest["prepared_case_sha256"]["case-inputs.json"]
    assert manifest["memory_gib"] == 64
    assert manifest["profiling"] is profiling
    assert (b"profiling\n{" in control) is profiling
    if numerical_variant == "u_gradient_limited":
        assert manifest["numerical_variant"] == "u_gradient_limited"
        assert manifest["momentum_convection"] == "limitedLinearV 1"
        assert manifest["velocity_gradient_scheme"] == ("grad(U) cellLimited Gauss linear 1;")
    assert "prepared_case_files_sha256_after_setExprFields" not in manifest
    assert not list(local.glob("rouaix-e1hpc-*"))
