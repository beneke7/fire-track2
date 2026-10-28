from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AUDIT_PATH = ROOT / "cases/e1_rouaix_hpc_restart/audit_restart.py"
SPEC = importlib.util.spec_from_file_location("rouaix_restart_audit", AUDIT_PATH)
assert SPEC is not None and SPEC.loader is not None
restart_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restart_audit)
RUNNER_PATH = ROOT / "cases/e1_rouaix_hpc_restart/run_restart.py"
RUNNER_SPEC = importlib.util.spec_from_file_location("rouaix_restart_runner", RUNNER_PATH)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
restart_runner = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = restart_runner
RUNNER_SPEC.loader.exec_module(restart_runner)


def _write_series(path: Path, header: str, rows: list[tuple[float, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(" ".join(f"{value:.12g}" for value in row) + "\n" for row in rows)
    path.write_text(f"# Time {header}\n{body}", encoding="ascii")


def _case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    inventories: list[tuple[float, float]] | None = None,
    fluxes: dict[str, list[tuple[float, float]]] | None = None,
    missing_patch: str | None = None,
    terminal_overrides: dict[str, object] | None = None,
    target_time_s: float = 0.2002,
) -> tuple[Path, Path]:
    run_dir = tmp_path / "restart-case"
    run_dir.mkdir()
    parent = {
        "coverage": {
            "last_matched_printed_time_s": 0.2,
            "last_matched_reconstructed_time_s": 0.2,
            "requested_end_time_s": 0.2,
            "requested_end_reached": True,
            "configured_horizon_reached": True,
        },
        "integration": {
            "density_kg_m3": 997.6,
            "final_inventory_m3": 0.25,
            "injected_kg": 123.0,
            "signed_net_escape_kg": 4.5,
            "closure_residual_kg": 0.002,
            "known_closure_caveat": "Native alpha snap/bounding may contribute to residuals.",
        },
    }
    parent_path = tmp_path / "parent-ledger.json"
    parent_bytes = (json.dumps(parent, indent=2) + "\n").encode()
    parent_path.write_bytes(parent_bytes)
    monkeypatch.setattr(
        restart_audit, "PARENT_LEDGER_SHA256", hashlib.sha256(parent_bytes).hexdigest()
    )

    receipt = {
        "archive_sha256": restart_audit.PARENT_ARCHIVE_SHA256,
        "checkpoint_time_s": 0.2,
        "inventory_m3": 0.25,
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_endpoint_member": restart_audit.PARENT_ENDPOINT_MEMBER,
    }
    (run_dir / "parent-checkpoint-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    terminal = {
        "schema_version": 1,
        "state": "terminal",
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_s": 0.2002,
        "target_time_s": target_time_s,
        "requested_start_time_s": 0.2,
        "solver_time_steps_recorded": 2,
        "stop_reason": None,
        "pause_observed": False,
    }
    terminal.update(terminal_overrides or {})
    actual_steps = round((float(terminal["solver_time_s"]) - 0.2) / 0.0001)
    if "solver_time_steps_recorded" not in (terminal_overrides or {}):
        terminal["solver_time_steps_recorded"] = actual_steps
    if terminal["stop_reason"] is not None:
        if "state" not in (terminal_overrides or {}):
            terminal["state"] = "guarded_partial"
        terminal.setdefault("write_and_stop_requested", True)
        terminal.setdefault("write_and_stop_acknowledged", True)
    (run_dir / "terminal-status.json").write_text(json.dumps(terminal), encoding="utf-8")

    time_rows = [0.2 + 0.0001 * index for index in range(actual_steps + 1)]
    inventory_rows = inventories or [
        (instant, 0.25 + 0.0000008 * index) for index, instant in enumerate(time_rows)
    ]
    _write_series(
        run_dir / "postProcessing/waterInventory/0/volFieldValue.dat",
        "volIntegrate(alpha.water)",
        inventory_rows,
    )
    fluxes = fluxes or {}
    for patch in restart_audit.PATCHES:
        if patch == missing_patch:
            continue
        rows = fluxes.get(patch, [(instant, 0.0) for instant in time_rows])
        # Include phi before alphaPhi_ to verify that the named phase-flux column is selected.
        _write_series(
            run_dir / f"postProcessing/liquidFlux_{patch}/0/surfaceFieldValue.dat",
            "sum(phi) sum(alphaPhi_)",
            [(instant, 0.0, value) for instant, value in rows],
        )
    return run_dir, parent_path


def test_nonzero_checkpoint_and_constant_flux_close_incremental_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    times = [0.2, 0.2001, 0.2002]
    fluxes = {
        "nozzle": [(times[0], 0.0), (times[1], -0.01), (times[2], -0.01)],
        "downstreamOutlet": [(times[0], 0.0), (times[1], 0.002), (times[2], 0.002)],
    }
    inventories = [(times[0], 0.25), (times[1], 0.2500008), (times[2], 0.2500016)]
    run_dir, parent = _case(tmp_path, monkeypatch, inventories=inventories, fluxes=fluxes)

    report = restart_audit.audit_restart(run_dir, parent, 0.2, 0.2002, 0.0001)

    incremental = report["incremental_only"]
    assert incremental["final_inventory_m3"] == pytest.approx(0.2500016)
    assert incremental["source_inflow_volume_m3"] == pytest.approx(2e-6)
    assert incremental["external_patch_outflow_volume_m3"] == pytest.approx(4e-7)
    assert incremental["stored_inventory_change_m3"] == pytest.approx(1.6e-6)
    assert incremental["signed_balance_residual_kg"] == pytest.approx(0.0, abs=1e-10)
    assert report["parent_checkpoint"]["initial_inventory_m3"] == pytest.approx(0.25)
    assert report["parent_checkpoint"]["cumulative_offsets_recounted"] is False
    with (run_dir / "restart-ledger.csv").open(encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 2


def test_positive_outgoing_flux_reduces_inventory_with_outward_sign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    times = [0.2, 0.2001, 0.2002]
    fluxes = {"downstreamOutlet": [(times[0], 0.0), (times[1], 0.002), (times[2], 0.002)]}
    inventories = [(times[0], 0.25), (times[1], 0.2499998), (times[2], 0.2499996)]
    run_dir, parent = _case(tmp_path, monkeypatch, inventories=inventories, fluxes=fluxes)

    report = restart_audit.audit_restart(run_dir, parent, 0.2, 0.2002, 0.0001)

    assert report["incremental_only"]["external_patch_outflow_volume_m3"] == pytest.approx(4e-7)
    assert report["incremental_only"]["stored_inventory_change_m3"] == pytest.approx(-4e-7)
    assert report["incremental_only"]["signed_balance_residual_kg"] == pytest.approx(0.0, abs=1e-10)


def test_missing_patch_history_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, parent = _case(tmp_path, monkeypatch, missing_patch="spanwisePlus")

    with pytest.raises(ValueError, match="expected exactly one surfaceFieldValue.dat"):
        restart_audit.audit_restart(run_dir, parent, 0.2, 0.2002, 0.0001)


def test_misaligned_patch_times_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    times = [0.2, 0.2001, 0.2002]
    fluxes = {"spanwiseMinus": [(times[0], 0.0), (0.20011, 0.0), (times[2], 0.0)]}
    run_dir, parent = _case(tmp_path, monkeypatch, fluxes=fluxes)

    with pytest.raises(ValueError, match="time mismatch"):
        restart_audit.audit_restart(run_dir, parent, 0.2, 0.2002, 0.0001)


def test_runner_guarded_partial_receipt_is_preserved_without_claiming_target_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_receipt = restart_runner.build_terminal_status(
        return_code=0,
        end_marker=True,
        actual_time_s=0.2001,
        step_count=1,
        stop_detail="operational stop: max|U|=1031.1 exceeded 1000.0 m/s",
        pause_observed=False,
        stop_signals=["12"],
        endpoint_verified=True,
    )
    run_dir, parent = _case(
        tmp_path,
        monkeypatch,
        terminal_overrides=runner_receipt,
        target_time_s=0.201,
    )
    terminal_receipt_path = run_dir / "terminal-status.json"
    assert json.loads(terminal_receipt_path.read_text(encoding="utf-8")) == runner_receipt

    report = restart_audit.audit_restart(run_dir, parent, 0.2, 0.201, 0.0001)

    assert report["coverage"]["status"] == "u_guard_partial_exploratory_only"
    assert report["coverage"]["requested_target_reached"] is False
    assert report["interval"]["actual_terminal_time_s"] == pytest.approx(0.2001)
    assert report["interval"]["step_count"] == 1
    assert (run_dir / "restart-audit.json").exists()
    with (run_dir / "restart-ledger.csv").open(encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 1


@pytest.mark.parametrize("actual_steps", [4, 5])
def test_diagnostic_early_save_accepts_native_iteration_overshoot_and_binds_raw_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actual_steps: int
) -> None:
    actual_time_s = 0.2 + actual_steps * 0.0001
    log_lines = [
        "sigStopAtWriteNow : Enabling writing and stopping upon signal 12",
        *[f"Time = {0.2 + step * 0.0001:.12f}" for step in range(1, actual_steps + 1)],
        "sigStopAtWriteNow : setting up write and stop at end of the next iteration",
        "End",
    ]
    raw_log = ("\n".join(log_lines) + "\n").encode("utf-8")
    solver_log = tmp_path / "solver.log"
    solver_log.write_bytes(raw_log)
    receipt = restart_runner.build_terminal_status(
        return_code=0,
        end_marker=True,
        actual_time_s=actual_time_s,
        step_count=actual_steps,
        stop_detail=restart_runner.EARLY_SAVE_STOP_REASON,
        pause_observed=False,
        stop_signals=["12"],
        endpoint_verified=True,
        variant="original-early-save",
        target_time_s=0.202,
        solver_log_sha256=hashlib.sha256(raw_log).hexdigest(),
        stop_signal_request_utc="2026-10-28T12:00:00+00:00",
        stop_signal_acknowledged_utc="2026-10-28T12:00:01+00:00",
        stop_signal_job_id="14700000",
        stop_signal_job_step="14700000.0",
        stop_signal_task_count=120,
        stop_signal_request_solver_time_s=0.2003,
        early_save_trigger_after_steps=3,
    )
    run_dir, parent = _case(
        tmp_path,
        monkeypatch,
        terminal_overrides=receipt,
        target_time_s=0.202,
    )

    report = restart_audit.audit_restart(run_dir, parent, 0.2, 0.202, 0.0001)

    assert report["coverage"]["status"] == "diagnostic_early_save_partial_exploratory_only"
    assert report["coverage"]["requested_target_reached"] is False
    assert report["interval"]["diagnostic_early_save_stop"] is True
    assert report["interval"]["partial_u_guard_stop"] is False
    assert report["interval"]["step_count"] == actual_steps
    assert report["interval"]["actual_terminal_time_s"] == pytest.approx(actual_time_s)
    solver_log.write_text("Time = 0.2003\nEnd\n", encoding="utf-8")
    with pytest.raises(ValueError, match="solver-log hash"):
        restart_audit.audit_restart(run_dir, parent, 0.2, 0.202, 0.0001)


@pytest.mark.parametrize("include_start_sample", [True, False])
@pytest.mark.parametrize(
    ("parent_variant", "parent_case_id", "checkpoint_time_s", "parent_steps"),
    [
        (
            "pressure-total-p0-zero",
            "rouaix-restart-pressure-total-p0-zero-0300",
            0.3,
            1000,
        ),
        (
            "pressure-total-pcgdic",
            "rouaix-restart-pressure-total-pcgdic-0255",
            0.255,
            550,
        ),
    ],
)
def test_pressure_continuation_audits_only_post_checkpoint_rows_and_records_inventory_basis(
    tmp_path: Path,
    include_start_sample: bool,
    parent_variant: str,
    parent_case_id: str,
    checkpoint_time_s: float,
    parent_steps: int,
) -> None:
    run_dir = tmp_path / "pressure-continuation"
    run_dir.mkdir()
    parent = {
        "coverage": {
            "status": "requested_horizon_reached_exploratory_only",
            "requested_target_reached": True,
            "actual_end_time_s": checkpoint_time_s,
        },
        "integration": {
            "density_kg_m3": 997.6,
            "final_inventory_m3": 0.4,
            "injected_kg": 123.0,
            "signed_net_escape_kg": 4.5,
            "closure_residual_kg": 0.002,
        },
        "interval": {"step_count": parent_steps},
    }
    parent_path = tmp_path / "parent-ledger-030.json"
    parent_raw = (json.dumps(parent, sort_keys=True) + "\n").encode()
    parent_path.write_bytes(parent_raw)
    ledger_sha = hashlib.sha256(parent_raw).hexdigest()
    mesh = {
        name: {"sha256": hashlib.sha256(name.encode()).hexdigest()}
        for name in restart_audit.PARENT_PROCESSOR_MESH_FILES
    }
    contract = {
        "schema_version": 1,
        "parent_job_id": "14709991",
        "case_id": parent_case_id,
        "variant": parent_variant,
        "parent_start_time_s": 0.2,
        "parent_target_time_s": checkpoint_time_s,
        "checkpoint_time_s": checkpoint_time_s,
        "delta_t_s": 0.0001,
        "step_count": parent_steps,
        "inventory_m3": 0.4,
        "density_kg_m3": 997.6,
        "archive_sha256": "a" * 64,
        "ledger_sha256": ledger_sha,
        "manifest_sha256": "b" * 64,
        "terminal_sha256": "c" * 64,
        "inventory_history_member": (
            "attempt/case/postProcessing/waterVolume/0.200000000000/volFieldValue.dat"
            if parent_variant == "pressure-total-pcgdic"
            else "attempt/case/postProcessing/waterInventory/0/volFieldValue.dat"
        ),
        "inventory_history_sha256": "d" * 64,
        "inventory_history_time_s": checkpoint_time_s,
        "inventory_history_m3": 0.4,
        "checkpoint_fields": {"alpha.water": {"sha256": "e" * 64}},
        "processor_mesh": mesh,
    }
    if parent_variant == "pressure-total-pcgdic":
        contract["fv_solution_member"] = "attempt/case/system/fvSolution"
        contract["fv_solution_sha256"] = "f" * 64
    endpoint_member = f"attempt/case/processors120/{checkpoint_time_s:.12f}/alpha.water"
    receipt = {
        "archive_sha256": contract["archive_sha256"],
        "checkpoint_time_s": checkpoint_time_s,
        "inventory_m3": 0.4,
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_endpoint_member": endpoint_member,
        "ledger_sha256": ledger_sha,
        "parent_job_id": contract["parent_job_id"],
        "manifest_sha256": contract["manifest_sha256"],
        "terminal_sha256": contract["terminal_sha256"],
    }
    if parent_variant == "pressure-total-pcgdic":
        receipt["fv_solution_sha256"] = contract["fv_solution_sha256"]
    (run_dir / "parent-checkpoint-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    terminal = {
        "state": "terminal",
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_s": checkpoint_time_s + 0.0002,
        "target_time_s": checkpoint_time_s + 0.0002,
        "requested_start_time_s": checkpoint_time_s,
        "solver_time_steps_recorded": 2,
        "stop_reason": None,
        "pause_observed": False,
    }
    (run_dir / "terminal-status.json").write_text(json.dumps(terminal), encoding="utf-8")
    times = [checkpoint_time_s + 0.0001, checkpoint_time_s + 0.0002]
    inventory_rows = [(time_s, 0.4 + index * 1e-6) for index, time_s in enumerate(times, 1)]
    if include_start_sample:
        inventory_rows.insert(0, (checkpoint_time_s, 0.4))
    _write_series(
        run_dir / "postProcessing/waterInventory/0/volFieldValue.dat",
        "volIntegrate(alpha.water)",
        inventory_rows,
    )
    for patch in restart_audit.PATCHES:
        _write_series(
            run_dir / f"postProcessing/liquidFlux_{patch}/0/surfaceFieldValue.dat",
            "sum(phi) sum(alphaPhi_)",
            [(time_s, 0.0, 0.0) for time_s in times],
        )

    report = restart_audit.audit_restart(
        run_dir,
        parent_path,
        checkpoint_time_s,
        checkpoint_time_s + 0.0002,
        0.0001,
        parent_contract=contract,
    )

    assert report["coverage"]["requested_target_reached"] is True
    assert report["interval"]["step_count"] == 2
    assert report["integration"]["initial_inventory_m3"] == pytest.approx(0.4)
    assert report["integration"]["injected_kg"] == pytest.approx(0.0)
    assert report["parent_checkpoint"]["prior_injected_kg_context_only"] == pytest.approx(123.0)
    assert report["parent_checkpoint"]["cumulative_offsets_recounted"] is False
    evidence = report["parent_checkpoint"]["initial_inventory_evidence"]
    assert evidence["history_inventory_m3"] == pytest.approx(0.4)
    assert evidence["history_time_s"] == pytest.approx(checkpoint_time_s)
    assert evidence["child_start_inventory_sample_status"] == (
        "present_and_matches_parent_contract"
        if include_start_sample
        else "absent; M0 inferred from the exact parent native history and identical hash-bound checkpoint alpha.water and mesh"
    )
    receipt["parent_job_id"] = "14700000"
    (run_dir / "parent-checkpoint-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt parent_job_id"):
        restart_audit.audit_restart(
            run_dir,
            parent_path,
            checkpoint_time_s,
            checkpoint_time_s + 0.0002,
            0.0001,
            parent_contract=contract,
        )
