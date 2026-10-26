from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from cases.e1_rouaix_hpc import overnight_queue as queue


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan_tree(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "project"
    case_dir = root / "cases/e1_rouaix_hpc"
    case_dir.mkdir(parents=True)
    archive = root / "mesh-input.tar.gz"
    archive.write_bytes(b"verified input fixture")
    pilot = case_dir / "pilot.sbatch"
    pilot.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    selector = case_dir / "overnight_selector.sbatch"
    selector.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return {
        "project_root": str(root),
        "queue_id": "queue-fixture",
        "cutoff_utc": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
        "input_archive": {"path": str(archive), "sha256": _sha(archive)},
        "pilot_sbatch": {"path": str(pilot), "sha256": _sha(pilot)},
        "selector_sbatch": {"path": str(selector), "sha256": _sha(selector)},
        "memory_gib_per_node": 64,
        "selector_wall_budget_s": 120,
        "wall_budget_s_by_stage": {
            "diagnostic": 1200,
            "short": 1200,
            "scaling": 1800,
            "half_second": 3600,
            "five_second": 3600,
        },
        "minimum_free_disk_gib_by_stage": {
            "diagnostic": 12,
            "short": 6,
            "scaling": 6,
            "half_second": 6,
            "five_second": 4,
        },
    }


def _export_map(command: list[str]) -> dict[str, str]:
    value = next(arg.removeprefix("--export=") for arg in command if arg.startswith("--export="))
    return dict(item.split("=", 1) for item in value.split(","))


def _seed(
    case_id: str,
    job_id: str,
    profile: tuple[int, int, float, float, str],
    root: Path,
    input_sha: str,
) -> dict[str, object]:
    ranks, nodes, horizon, dt, variant = profile
    return {
        "case_id": case_id,
        "job_id": job_id,
        "run_dir": str(root / f"{queue.RUN_PREFIX}{job_id}"),
        "ranks": ranks,
        "nodes": nodes,
        "horizon_s": horizon,
        "delta_t_s": dt,
        "numerical_variant": variant,
        "input_archive_sha256": input_sha,
        "run_state_sha256": None,
        "result_archive_sha256": None,
        "supplementary_audit": None,
        "accounting_snapshot": None,
    }


def _write_supplementary_bundle(
    root: Path,
    seed: dict[str, object],
    run_state: dict[str, object],
    run_state_sha: str,
    archive_path: Path,
) -> dict[str, str]:
    bundle = root / "supplementary-audits" / str(seed["job_id"])
    reports = bundle / "ledger-fixed-controlDict"
    reports.mkdir(parents=True)
    rows = int(run_state["solver_time_steps_recorded"])
    csv_path = reports / "ledger.csv"
    step_rows = "".join(
        f"{int(seed['delta_t_s'] * 1_000_000) * index / 1_000_000:.9f},1.0\n"
        for index in range(1, rows + 1)
    )
    csv_path.write_text(f"time_s,injected_kg\n{step_rows}", encoding="utf-8")
    coverage = {
        "status": "configured_horizon_reached_exploratory_only",
        "configured_horizon_reached": True,
        "configured_horizon_s": seed["horizon_s"],
        "coverage_fraction_of_requested_horizon": 1.0,
        "first_matched_time_s": seed["delta_t_s"],
    }
    native = {
        "version": "v2512",
        "architecture": "x86_64",
        "precision": "DP",
        "label_size_bits": 32,
        "executable_sha256": "d" * 64,
    }
    summary = {
        "formal_validation_decision": None,
        "coverage": coverage,
        "prepared_input_hash_verification": {
            "verification_status": "verified",
            "verified_file_count": 22,
        },
        "source_code_and_input_sha256": {
            "audit_script_sha256": queue.SUPPLEMENTARY_AUDITOR_SHA256,
        },
        "row_coverage": {
            "nozzle": {"matched_common_prefix_rows": rows},
            "gasInlet": {"matched_common_prefix_rows": rows},
        },
        "solver_image_verification": {
            "execution_backend": "slurm-native",
            "verification_mode": "native-module-source-correspondence",
            "native_solver": native,
            "source_evidence": {"native_solver": native},
        },
    }
    summary_path = reports / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "attempt_id": f"rouaix-e1-hpc-pilot-{seed['job_id']}",
        "supplementary_audit_status": "completed_exploratory_only",
        "formal_validation_decision": None,
        "original_run_record": {
            "job_id": seed["job_id"],
            "run_state_sha256": run_state_sha,
            "terminal_status": "FAILED",
            "solver_step_status": "COMPLETED",
        },
        "original_result_archive": {
            "sha256": queue.sha256_file(archive_path),
            "bytes": archive_path.stat().st_size,
            "member_count": run_state["result_archive_members"],
        },
        "raw_input_bindings": {
            "solver_log_sha256": run_state["solver_log_sha256"],
            "prepared_input_verification": "verified",
            "prepared_input_verified_file_count": 22,
            "solver_identity_verification": "native-module-source-correspondence",
            "case_profile": seed["case_id"],
            "numerical_variant": seed["numerical_variant"],
            "horizon_s_from_run_state_and_case_inputs": seed["horizon_s"],
            "delta_t_s_from_run_state_and_case_inputs": seed["delta_t_s"],
            "input_archive_sha256_from_run_state": run_state["input_archive_sha256"],
        },
        "timestep_provenance": {
            "mode": "fixed-controlDict",
            "controlDict_deltaT_token": f"{seed['delta_t_s']:g}",
        },
        "audit_result": {
            "auditor_sha256": queue.SUPPLEMENTARY_AUDITOR_SHA256,
            "coverage_status": "configured_horizon_reached_exploratory_only",
            "configured_horizon_s": seed["horizon_s"],
            "first_matched_time_s": seed["delta_t_s"],
            "last_matched_time_s": seed["horizon_s"],
            "matched_rows": rows,
            "closure_residual_kg": -1.8e-8,
            "formal_validation_decision": None,
        },
        "supplementary_outputs": {
            "summary_json_sha256": queue.sha256_file(summary_path),
            "ledger_csv_sha256": queue.sha256_file(csv_path),
        },
    }
    receipt_path = bundle / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return {"path": str(receipt_path), "sha256": queue.sha256_file(receipt_path)}


def _row(case_id: str, phase: str, viable: bool) -> dict[str, object]:
    return {
        "case_id": case_id,
        "profile": {"phase": phase, "ranks": 64},
        "viable": viable,
    }


def test_case_submission_exports_input_and_every_declared_case_setting(tmp_path: Path) -> None:
    plan = _plan_tree(tmp_path)
    profile = queue._profile("diagnostic_n3", 64, 0.01, 0.0005, "original")

    command = queue.build_submit_argv(plan, profile, kind="case")
    exported = _export_map(command)

    assert set(exported) == queue.CASE_EXPORT_KEYS
    assert exported["ROUAIX_PROJECT_ROOT"] == plan["project_root"]
    assert exported["ROUAIX_INPUT_ARCHIVE"] == plan["input_archive"]["path"]
    assert exported["ROUAIX_INPUT_SHA256"] == plan["input_archive"]["sha256"]
    assert exported["ROUAIX_END_TIME_S"] == "0.01"
    assert exported["ROUAIX_DELTA_T_S"] == "0.0005"
    assert "ALL" not in exported
    assert "--no-requeue" in command
    assert "--kill-on-invalid-dep=yes" in command
    assert "--nodes=1" in command
    assert "--ntasks=64" in command
    assert f"--chdir={plan['project_root']}" in command
    assert f"--output={plan['project_root']}/rouaix-e1-hpc-%j.slurm.out" in command
    assert str(plan["project_root"]) in command[-1]


def test_case_submission_rejects_input_outside_versioned_project_root(tmp_path: Path) -> None:
    plan = _plan_tree(tmp_path)
    external = tmp_path / "external-mesh.tar.gz"
    external.write_bytes(b"outside root")
    plan["input_archive"] = {"path": str(external), "sha256": _sha(external)}

    with pytest.raises(queue.QueueError, match="project root"):
        queue.build_submit_argv(
            plan, queue._profile("diagnostic_n3", 64, 0.01, 0.0005, "original"), kind="case"
        )


def test_multinode_case_request_pins_compact_task_layout(tmp_path: Path) -> None:
    plan = _plan_tree(tmp_path)
    for ranks, nodes, tasks_per_node in ((240, 2, 120), (300, 3, 100)):
        command = queue.build_submit_argv(
            plan,
            queue._profile("scale240", ranks, 0.05, 0.0005, "original"),
            kind="case",
        )
        assert f"--nodes={nodes}" in command
        assert f"--ntasks={ranks}" in command
        assert f"--ntasks-per-node={tasks_per_node}" in command
        assert "--distribution=block:block" in command


def test_selector_submission_is_one_cpu_and_uses_explicit_queue_context(tmp_path: Path) -> None:
    plan = _plan_tree(tmp_path)
    root = Path(plan["project_root"])
    plan_file = root / "overnight-plan.json"
    plan_file.write_text("{}\n", encoding="utf-8")
    state_file = root / "overnight-state.json"

    command = queue.build_submit_argv(
        plan,
        kind="selector",
        plan_path=plan_file,
        state_path=state_file,
        previous_case_id="N2-ORIGINAL-64-01MS-001",
        previous_job_id="14647714",
    )

    assert set(_export_map(command)) == queue.SELECTOR_EXPORT_KEYS
    assert _export_map(command)["ROUAIX_PROJECT_ROOT"] == plan["project_root"]
    assert "--nodes=1" in command
    assert "--ntasks=1" in command
    assert "--cpus-per-task=1" in command
    assert "--dependency=afterany:14647714" in command
    assert f"--chdir={plan['project_root']}" in command
    assert f"--output={plan['project_root']}/rouaix-e1-hpc-selector-%j.log" in command
    assert "--no-requeue" in command
    assert "--kill-on-invalid-dep=yes" in command


def test_seed_order_and_profiles_are_the_final_n1_then_n2_pair(tmp_path: Path) -> None:
    tree = _plan_tree(tmp_path)
    root = Path(tree["project_root"])
    plan = {
        **tree,
        "seed_cases": [
            _seed(
                "N1-UPWIND-64-1MS-001",
                "14647712",
                (64, 1, 0.01, 0.001, "upwind"),
                root,
                tree["input_archive"]["sha256"],
            ),
            _seed(
                "N2-ORIGINAL-64-01MS-001",
                "14647714",
                (64, 1, 0.01, 0.0001, "original"),
                root,
                tree["input_archive"]["sha256"],
            ),
        ],
    }

    queue._validate_seeds(plan)
    versioned = {**plan, "seed_cases": [dict(item) for item in plan["seed_cases"]]}
    versioned["seed_cases"][0]["run_dir"] = str(
        root / "rouaix-n1-n2-source-v1" / f"{queue.RUN_PREFIX}14647712"
    )
    queue._validate_seeds(versioned)
    outside = {**versioned, "seed_cases": [dict(item) for item in versioned["seed_cases"]]}
    outside["seed_cases"][0]["run_dir"] = str(tmp_path / f"{queue.RUN_PREFIX}14647712")
    with pytest.raises(queue.QueueError, match="under project_root"):
        queue._validate_seeds(outside)
    with pytest.raises(queue.QueueError, match="approved N1/N2"):
        queue._validate_seeds({**plan, "seed_cases": list(reversed(plan["seed_cases"]))})
    n3 = _seed(
        "N3-ORIGINAL-64-05MS-001",
        "14647739",
        (64, 1, 0.01, 0.0005, "original"),
        root,
        tree["input_archive"]["sha256"],
    )
    queue._validate_seeds({**plan, "seed_cases": [*plan["seed_cases"], n3]})
    assert queue._seed_profile(n3)["phase"] == "diagnostic_n3"
    assert queue._seed_profile(n3)["retention_mode"] == "full"
    split_root_n3 = {
        **n3,
        "run_dir": str(
            root / "rouaix-n3-r4audit-source-v1-20261026" / f"{queue.RUN_PREFIX}14647739"
        ),
    }
    split_versions = {
        **plan,
        "seed_cases": [
            {
                **plan["seed_cases"][0],
                "run_dir": str(
                    root / "rouaix-n1-n2-source-v1-20261025" / f"{queue.RUN_PREFIX}14647712"
                ),
            },
            {
                **plan["seed_cases"][1],
                "run_dir": str(
                    root / "rouaix-n1-n2-source-v1-20261025" / f"{queue.RUN_PREFIX}14647714"
                ),
            },
            split_root_n3,
        ],
    }
    queue._validate_seeds(split_versions)
    n3["delta_t_s"] = 0.00025
    with pytest.raises(queue.QueueError, match="approved N1/N2"):
        queue._validate_seeds({**plan, "seed_cases": [*plan["seed_cases"], n3]})


def test_dispatch_waits_for_both_seeds_and_prefers_original_candidate() -> None:
    n1 = _row("N1-UPWIND-64-1MS-001", "diagnostic_n1", True)
    n2_pass = _row("N2-ORIGINAL-64-01MS-001", "diagnostic_n2", True)
    n2_fail = _row("N2-ORIGINAL-64-01MS-001", "diagnostic_n2", False)

    profile, _, _ = queue._next([n1])
    assert profile is None
    profile, _, _ = queue._next([n1, n2_pass])
    assert profile is not None
    assert profile["case_id"] == "N3-ORIGINAL-64-05MS-001"
    profile, _, selected = queue._next([n1, n2_fail])
    assert profile is not None
    assert profile["phase"] == "upwind_temporal"
    assert selected == {
        "source_case_id": n1["case_id"],
        "numerical_variant": "upwind",
        "delta_t_s": 0.001,
    }
    profile, reason, _ = queue._next([_row(n1["case_id"], "diagnostic_n1", False), n2_fail])
    assert profile is None
    assert "no startup diagnostic" in reason


def test_queue_state_hash_chain_and_sbatch_routing_output(tmp_path: Path) -> None:
    plan = {"queue_id": "fixture"}
    state = queue._state_empty(plan, "a" * 64)
    queue._append(state, {"event_type": "decision", "value": "keep"})
    state_path = tmp_path / "state.json"
    queue._write_state(state_path, state)
    assert queue._read_state(state_path, plan, "a" * 64) == state
    changed = json.loads(state_path.read_text(encoding="utf-8"))
    changed["events"][0]["value"] = "altered"
    state_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(queue.QueueError, match="hash chain"):
        queue._read_state(state_path, plan, "a" * 64)

    job_id, raw = queue.parse_sbatch_output("sbatch: routing job to cpu-short\n14647712\n")
    assert job_id == "14647712"
    assert raw["stdout"].startswith("sbatch: routing")
    ambiguous, raw = queue.parse_sbatch_output("14647712\n14647713\n", "notice", 0)
    assert ambiguous is None
    assert raw["stderr"] == "notice"


def test_accounting_falls_back_from_unavailable_dbd_to_scontrol_then_upper_bound() -> None:
    def controller_query(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[0] == "sacct":
            return SimpleNamespace(returncode=1, stdout="", stderr="database unavailable")
        return SimpleNamespace(
            returncode=0,
            stdout="JobId=12345 NumCPUs=64 RunTime=00:02:13 State=FAILED\n",
            stderr="",
        )

    core_seconds, accounting = queue._sacct("12345", controller_query)
    assert core_seconds == 64 * 133
    assert accounting["source"] == "scontrol"
    assert accounting["state"] == "FAILED"
    assert accounting["is_upper_bound"] is False

    def unavailable(command: list[str], **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="unavailable")

    core_seconds, accounting = queue._sacct(
        "12345",
        unavailable,
        profile={"nodes": 2, "wall_budget_s": 600},
        run_state={},
    )
    assert core_seconds == 2 * 128 * 600
    assert accounting["source"] == "conservative_allocation_upper_bound"
    assert accounting["is_upper_bound"] is True
    assert accounting["alloc_cpus"] == 256
    assert accounting["elapsed_s"] == 600


def test_wall_forecast_uses_same_dt_and_exact_or_nearest_rank_without_speedup() -> None:
    history = [
        {
            "case_id": "slow-64",
            "profile": {
                "ranks": 64,
                "horizon_s": 0.05,
                "delta_t_s": 0.0005,
                "numerical_variant": "original",
            },
            "viable": True,
            "solver_wall_s": 5_000.0,
            "solver_time_steps_recorded": 500,
            "accounting": {"elapsed_s": 5_300},
        },
        {
            "case_id": "fast-300",
            "profile": {
                "ranks": 300,
                "horizon_s": 0.05,
                "delta_t_s": 0.0005,
                "numerical_variant": "original",
            },
            "viable": True,
            "solver_wall_s": 1_000.0,
            "solver_time_steps_recorded": 500,
            "accounting": {"elapsed_s": 1_250},
        },
        {
            "case_id": "wrong-dt",
            "profile": {
                "ranks": 300,
                "horizon_s": 0.05,
                "delta_t_s": 0.001,
                "numerical_variant": "original",
            },
            "viable": True,
            "solver_wall_s": 1.0,
            "solver_time_steps_recorded": 50,
            "accounting": {"elapsed_s": 1},
        },
    ]

    exact = queue._wall_forecast(history, queue._profile("five_best", 300, 5.0, 0.0005, "original"))
    assert exact is not None
    solver_s, setup_pack_s, source = exact
    assert solver_s == 20_000
    assert setup_pack_s == 300
    assert source["case_id"] == "fast-300"
    assert source["timing_window"] == "full_run_includes_startup"
    assert source["placement_basis"] == "exact_rank_count"

    nearby = queue._wall_forecast(
        history, queue._profile("five_best", 240, 5.0, 0.0005, "original")
    )
    assert nearby is not None
    assert nearby[0] == 20_000
    assert nearby[2]["ranks"] == 300
    assert nearby[2]["placement_basis"] == "nearest_measured_rank_no_speedup_assumed"


def test_five_second_fit_uses_checkpoint_bytes_and_allows_bounded_cutoff_progress(
    tmp_path: Path,
) -> None:
    plan = _plan_tree(tmp_path)
    archive_path = Path(plan["input_archive"]["path"])
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"mesh fixture"
        info = tarfile.TarInfo("constant/polyMesh/points")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    plan["input_archive"] = {"path": str(archive_path), "sha256": _sha(archive_path)}
    plan["seed_cases"] = []
    plan["max_allocated_core_seconds"] = 2700 * 3600
    plan["wall_budget_s_by_stage"]["five_second"] = 12 * 3600
    plan["cutoff_utc"] = (datetime.now(UTC) + timedelta(seconds=1_200)).isoformat()
    half = {
        "case_id": "half-best-fixture",
        "profile": {
            "phase": "half_best",
            "ranks": 64,
            "nodes": 1,
            "horizon_s": 0.5,
            "delta_t_s": 0.0005,
            "numerical_variant": "original",
        },
        "viable": True,
        "solver_wall_s": 900.0,
        "solver_time_steps_recorded": 1_000,
        "accounting": {"elapsed_s": 900},
        "result_archive_bytes": 10_000,
        "result_archive_member_sizes": [
            {"path": "attempt/case/processors64/constant/polyMesh/points", "bytes": 1_000},
            {"path": "attempt/case/processors64/0.5/U", "bytes": 1_000},
            {"path": "attempt/case/postProcessing/waterVolume/0/volFieldValue.dat", "bytes": 100},
            {"path": "attempt/solver.log", "bytes": 300},
        ],
    }
    state = {
        "events": [
            {"event_type": "case_submission_accepted", "case_id": half["case_id"]},
            {"event_type": "case_completed", "case_record": half},
        ]
    }

    fits, reason, budget = queue._fit(
        plan,
        state,
        queue._profile("five_best", 64, 5.0, 0.0005, "original"),
        datetime.now(UTC),
        1,
    )

    assert fits, reason
    assert budget["wall_budget_s"] < budget["requested_full_case_wall_s"]
    assert budget["wall_budget_is_cutoff_limited"] is True
    assert budget["wall_budget_limiting_constraints"] == ["utc_cutoff"]
    estimate = budget["five_second_storage_estimate"]
    assert estimate["transient_three_checkpoint_write_peak_bytes"] == 8_012
    assert estimate["packing_headroom_bytes"] == 1024**3
    assert budget["required_free_disk_bytes"] == max(
        8_012 + 4 * 1024**3, estimate["packing_peak_bytes"] + 1024**3
    )


def test_adopt_seed_selector_records_three_versioned_runs_then_submits_validation(
    tmp_path: Path,
) -> None:
    plan = _plan_tree(tmp_path)
    root = Path(plan["project_root"])
    case_dir = root / "cases/e1_rouaix_hpc"
    (case_dir / "prepare_case.py").write_text("# fixture\n", encoding="utf-8")
    (case_dir / "run_pilot.py").write_text("# fixture\n", encoding="utf-8")
    (case_dir / "overnight_queue.py").write_text("# fixture\n", encoding="utf-8")
    capsule = root / "base-capsule.tar.gz"
    capsule.write_bytes(b"immutable capsule")
    plan["pause_file"] = str(root / "PAUSE")
    plan["schema_version"] = 1
    plan["base_capsule"] = {"path": str(capsule), "sha256": _sha(capsule)}
    plan["max_ranks"] = 300
    plan["max_allocated_core_seconds"] = 2700 * 3600
    plan["wall_budget_s_by_stage"]["five_second"] = 12 * 3600
    plan["wall_budget_s_by_stage"]["short"] = 3600
    plan["cutoff_utc"] = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
    plan["base_source_sha256"] = {
        relative: _sha(root / relative) for relative in sorted(queue.REQUIRED_BASE_SOURCES)
    }
    plan["controller_source_sha256"] = {
        relative: _sha(root / relative) for relative in sorted(queue.REQUIRED_SELECTOR_SOURCES)
    }
    root_input_sha = plan["input_archive"]["sha256"]
    seeds = [
        _seed(
            "N1-UPWIND-64-1MS-001", "14647712", (64, 1, 0.01, 0.001, "upwind"), root, root_input_sha
        ),
        _seed(
            "N2-ORIGINAL-64-01MS-001",
            "14647714",
            (64, 1, 0.01, 0.0001, "original"),
            root,
            root_input_sha,
        ),
    ]
    for seed in seeds:
        seed_root = root / "rouaix-n1-n2-source-v1-20261025"
        seed["run_dir"] = str(seed_root / f"{queue.RUN_PREFIX}{seed['job_id']}")
        run_dir = Path(seed["run_dir"])
        run_dir.mkdir(parents=True)
        archive = run_dir / "result.tar.gz"
        archive.write_bytes(f"archive for {seed['job_id']}".encode())
        is_n1 = seed["case_id"] == "N1-UPWIND-64-1MS-001"
        run_state = {
            "job_id": seed["job_id"],
            "run_id": f"rouaix-e1-hpc-pilot-{seed['job_id']}",
            "case_id": seed["case_id"],
            "input_archive_sha256": root_input_sha,
            "execution_backend": "slurm-native",
            "solver_version": "v2512",
            "status": "solver_complete_ledger_failed",
            "solver_exit_code": 0,
            "stop_reason": None,
            "solver_end_marker": True,
            "solver_max_u_m_s": 70.0,
            "solver_log_sha256": ("a" if is_n1 else "b") * 64,
            "solver_time_steps_recorded": round(seed["horizon_s"] / seed["delta_t_s"]),
            "ledger_audit_status": "failed_partial_or_unavailable",
            "solver_convergence": {"all_converged": True},
            "attempt_archive_status": "verified_crc_hash_and_member_list",
            "result_archive": str(archive),
            "result_archive_sha256": _sha(archive),
            "result_archive_members": 126,
            "solver_wall_s": 113.08542358409613 if is_n1 else 708.6818201621063,
            "ranks": seed["ranks"],
            "nodes": seed["nodes"],
            "horizon_s": seed["horizon_s"],
            "delta_t_s": seed["delta_t_s"],
            "numerical_variant": seed["numerical_variant"],
            "retention_mode": "full",
            "write_interval_s": seed["horizon_s"],
        }
        state_path = run_dir / "run-state.json"
        state_path.write_text(json.dumps(run_state, sort_keys=True), encoding="utf-8")
        seed["run_state_sha256"] = _sha(state_path)
        seed["result_archive_sha256"] = _sha(archive)
        accounting_path = root / "seed-accounting" / f"{seed['job_id']}.json"
        accounting_path.parent.mkdir(exist_ok=True)
        raw_accounting = accounting_path.with_suffix(".raw.txt")
        raw_accounting.write_text(
            f"{seed['job_id']}|64|{288 if is_n1 else 880}|{'FAILED' if is_n1 else 'COMPLETED'}\n",
            encoding="utf-8",
        )
        accounting_path.write_text(
            json.dumps(
                {
                    "schema": "rouaix-hpc-seed-accounting-v1",
                    "captured_utc": "2026-10-25T21:31:20Z",
                    "source_note": "verified terminal Slurm accounting source",
                    "jobs": [
                        {
                            "job_id": seed["job_id"],
                            "alloc_cpus": 64,
                            "elapsed_s": 288 if is_n1 else 880,
                            "state": "FAILED",
                            "source": {
                                "path": str(raw_accounting),
                                "sha256": _sha(raw_accounting),
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        seed["accounting_snapshot"] = {
            "path": str(accounting_path),
            "sha256": _sha(accounting_path),
        }
        seed["supplementary_audit"] = _write_supplementary_bundle(
            root,
            seed,
            run_state,
            str(seed["run_state_sha256"]),
            archive,
        )
    n3 = _seed(
        "N3-ORIGINAL-64-05MS-001",
        "14647739",
        (64, 1, 0.01, 0.0005, "original"),
        root,
        root_input_sha,
    )
    n3_root = root / "rouaix-n3-r4audit-source-v1-20261026"
    n3["run_dir"] = str(n3_root / f"{queue.RUN_PREFIX}{n3['job_id']}")
    n3_dir = Path(n3["run_dir"])
    n3_dir.mkdir(parents=True)
    n3_archive = n3_dir / "result.tar.gz"
    n3_archive.write_bytes(b"N3 archive fixture")
    n3_state = {
        "job_id": n3["job_id"],
        "run_id": f"rouaix-e1-hpc-pilot-{n3['job_id']}",
        "case_id": n3["case_id"],
        "input_archive_sha256": root_input_sha,
        "execution_backend": "slurm-native",
        "solver_version": "v2512",
        "status": "solver_complete_exploratory",
        "solver_exit_code": 0,
        "stop_reason": None,
        "solver_end_marker": True,
        "solver_max_u_m_s": 104.142506747,
        "solver_log_sha256": "c" * 64,
        "solver_time_steps_recorded": 20,
        "ledger_audit_status": "raw_exploratory_ledger_written",
        "solver_convergence": {"all_converged": True},
        "attempt_archive_status": "verified_crc_hash_and_member_list",
        "result_archive": str(n3_archive),
        "result_archive_sha256": _sha(n3_archive),
        "result_archive_members": 129,
        "solver_wall_s": 200.94173577893525,
        "ranks": n3["ranks"],
        "nodes": n3["nodes"],
        "horizon_s": n3["horizon_s"],
        "delta_t_s": n3["delta_t_s"],
        "numerical_variant": n3["numerical_variant"],
        "retention_mode": "full",
        "write_interval_s": n3["horizon_s"],
    }
    n3_state_path = n3_dir / "run-state.json"
    n3_state_path.write_text(json.dumps(n3_state, sort_keys=True), encoding="utf-8")
    n3["run_state_sha256"] = _sha(n3_state_path)
    n3["result_archive_sha256"] = _sha(n3_archive)
    seeds.append(n3)
    plan["seed_cases"] = seeds

    plan_path = root / "overnight-plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    state_path = root / "overnight-state.json"
    submitted: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[0] == "sacct":
            job_id = command[command.index("-j") + 1]
            state = "COMPLETED" if job_id == "14647739" else "FAILED"
            return SimpleNamespace(returncode=0, stdout=f"{job_id}|64|379|{state}\n", stderr="")
        submitted.append(command)
        job_id = "220001" if len(submitted) == 1 else "220002"
        return SimpleNamespace(
            returncode=0,
            stdout=f"sbatch: routing job to cpu-short\n{job_id}\n",
            stderr="",
        )

    result = queue.run_selector(
        plan_path=plan_path,
        state_path=state_path,
        mode="adopt-seeds",
        run=fake_run,
    )

    assert result["status"] == "submitted"
    assert result["case_id"] == "validation64-original-64-0.0005"
    assert len(submitted) == 2
    assert _export_map(submitted[0])["ROUAIX_INPUT_SHA256"] == root_input_sha
    assert _export_map(submitted[0])["ROUAIX_PROJECT_ROOT"] == str(root)
    assert _export_map(submitted[0])["ROUAIX_WALL_BUDGET_S"] != "1200"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    completed = [
        event["case_id"] for event in state["events"] if event["event_type"] == "case_completed"
    ]
    assert completed == [
        "N1-UPWIND-64-1MS-001",
        "N2-ORIGINAL-64-01MS-001",
        "N3-ORIGINAL-64-05MS-001",
    ]
    n1_record = next(
        event["case_record"]
        for event in state["events"]
        if event.get("event_type") == "case_completed" and event.get("case_id") == completed[0]
    )
    assert n1_record["status"] == "solver_complete_ledger_failed"
    assert n1_record["viable"] is True
    assert n1_record["eligibility_basis"] == "supplementary_seed_audit"
    assert n1_record["supplementary_audit"]["matched_rows"] == 10
    n3_record = next(
        event["case_record"]
        for event in state["events"]
        if event.get("event_type") == "case_completed"
        and event.get("case_id") == "N3-ORIGINAL-64-05MS-001"
    )
    assert n3_record["status"] == "solver_complete_exploratory"
    assert n3_record["eligibility_basis"] == "raw_runner_audit"
    assert any(event["event_type"] == "case_submission_accepted" for event in state["events"])

    repeated = queue.run_selector(
        plan_path=plan_path,
        state_path=state_path,
        mode="adopt-seeds",
        run=fake_run,
    )
    assert repeated["status"] == "already_dispatched"
    assert len(submitted) == 2
