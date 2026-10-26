#!/usr/bin/env python3
"""Adopt the N1/N2 pilots and dispatch the finite, predeclared overnight sequence."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

PLACEMENTS = {64: 1, 120: 1, 240: 2, 300: 3}
MAX_CORE_SECONDS = 2700 * 3600
RUN_PREFIX = "rouaix-e1-hpc-pilot-"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUPPLEMENTARY_AUDITOR_SHA256 = "4df8cc2088a5115290a709c90a2ea746b06d29e10935608f1f0c4857e1dacc80"
STAGES = {"diagnostic", "short", "scaling", "half_second", "five_second"}
REQUIRED_BASE_SOURCES = {
    "cases/e1_rouaix_hpc/prepare_case.py",
    "cases/e1_rouaix_hpc/run_pilot.py",
    "cases/e1_rouaix_hpc/pilot.sbatch",
}
REQUIRED_SELECTOR_SOURCES = {
    "cases/e1_rouaix_hpc/overnight_queue.py",
    "cases/e1_rouaix_hpc/overnight_selector.sbatch",
}
CASE_EXPORT_KEYS = frozenset(
    {
        "HOME",
        "USER",
        "LOGNAME",
        "PATH",
        "ROUAIX_PROJECT_ROOT",
        "ROUAIX_INPUT_ARCHIVE",
        "ROUAIX_INPUT_SHA256",
        "ROUAIX_CASE_ID",
        "ROUAIX_RANKS",
        "ROUAIX_NODES",
        "ROUAIX_WALL_BUDGET_S",
        "ROUAIX_END_TIME_S",
        "ROUAIX_DELTA_T_S",
        "ROUAIX_NUMERICAL_VARIANT",
        "ROUAIX_WRITE_INTERVAL_S",
        "ROUAIX_RETENTION_MODE",
        "ROUAIX_MINIMUM_FREE_DISK_GIB",
        "ROUAIX_HARD_DEADLINE_UTC",
        "ROUAIX_QUEUE_ID",
    }
)
SELECTOR_EXPORT_KEYS = frozenset(
    {
        "HOME",
        "USER",
        "LOGNAME",
        "PATH",
        "ROUAIX_PROJECT_ROOT",
        "ROUAIX_QUEUE_PLAN",
        "ROUAIX_QUEUE_STATE",
        "ROUAIX_QUEUE_MODE",
        "ROUAIX_COMPLETED_CASE_ID",
        "ROUAIX_COMPLETED_JOB_ID",
    }
)
PLAN_KEYS = {
    "schema_version",
    "queue_id",
    "project_root",
    "pause_file",
    "input_archive",
    "base_capsule",
    "base_source_sha256",
    "controller_source_sha256",
    "pilot_sbatch",
    "selector_sbatch",
    "seed_cases",
    "cutoff_utc",
    "max_ranks",
    "max_allocated_core_seconds",
    "memory_gib_per_node",
    "selector_wall_budget_s",
    "wall_budget_s_by_stage",
    "minimum_free_disk_gib_by_stage",
}


class QueueError(RuntimeError):
    """A provenance, scheduler, accounting, budget, or selection failure."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise QueueError(f"{label} must be an ISO-8601 UTC timestamp") from error
    offset = parsed.utcoffset() if parsed.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        raise QueueError(f"{label} must include a zero-offset UTC timezone")
    return parsed.astimezone(UTC)


def _file(path_value: Any, label: str) -> Path:
    if not isinstance(path_value, str) or not Path(path_value).is_absolute() or "," in path_value:
        raise QueueError(f"{label} path must be absolute and contain no commas")
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise QueueError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _hash_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise QueueError(f"{label} must contain exactly path and sha256")
    path = _file(record["path"], label)
    if not isinstance(record["sha256"], str) or not SHA256.fullmatch(record["sha256"]):
        raise QueueError(f"{label} SHA-256 is malformed")
    if sha256_file(path) != record["sha256"]:
        raise QueueError(f"{label} hash mismatch: {path}")
    return path


def load_plan(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise QueueError("queue plan must be a regular file")
    raw = path.read_bytes()
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as error:
        raise QueueError(f"invalid queue plan JSON: {error}") from error
    if not isinstance(plan, dict) or set(plan) != PLAN_KEYS:
        raise QueueError("queue plan has unknown or missing fields")
    if (
        plan["schema_version"] != 1
        or not isinstance(plan["queue_id"], str)
        or not SAFE_ID.fullmatch(plan["queue_id"])
    ):
        raise QueueError("queue plan schema or ID is invalid")
    root = Path(plan["project_root"])
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise QueueError("project_root must be an existing absolute directory")
    root = root.resolve(strict=True)
    plan["project_root"] = str(root)
    if not path.resolve(strict=True).is_relative_to(root):
        raise QueueError("immutable queue plan must be below project_root")
    pause = plan["pause_file"]
    if not isinstance(pause, str) or not Path(pause).is_absolute() or "," in pause:
        raise QueueError("pause_file must be an absolute path without commas")

    for name in ("input_archive", "base_capsule"):
        path_on_disk = _hash_record(plan[name], name)
        if not path_on_disk.is_relative_to(root):
            raise QueueError(f"{name} must be below project_root")

    for source_key, required_paths in (
        ("base_source_sha256", REQUIRED_BASE_SOURCES),
        ("controller_source_sha256", REQUIRED_SELECTOR_SOURCES),
    ):
        records = plan[source_key]
        if not isinstance(records, dict) or not required_paths <= set(records):
            raise QueueError(f"{source_key} omits required source hashes")
        for relative, digest in records.items():
            rel = Path(relative)
            source_path = root / rel
            if (
                rel.is_absolute()
                or ".." in rel.parts
                or not source_path.is_file()
                or source_path.is_symlink()
            ):
                raise QueueError(f"unsafe or missing source path: {relative}")
            if (
                not isinstance(digest, str)
                or not SHA256.fullmatch(digest)
                or sha256_file(source_path) != digest
            ):
                raise QueueError(f"source hash mismatch: {relative}")

    expected_scripts = {
        "pilot_sbatch": root / "cases/e1_rouaix_hpc/pilot.sbatch",
        "selector_sbatch": root / "cases/e1_rouaix_hpc/overnight_selector.sbatch",
    }
    for key in ("pilot_sbatch", "selector_sbatch"):
        script = _hash_record(plan[key], key)
        if script != expected_scripts[key]:
            raise QueueError(f"{key} must use the source tree under project_root")

    if plan["max_ranks"] != 300 or plan["memory_gib_per_node"] != 64:
        raise QueueError("plan must preserve the reviewed 300-rank and 64-GiB/node bounds")
    core_cap = plan["max_allocated_core_seconds"]
    if (
        isinstance(core_cap, bool)
        or not isinstance(core_cap, int)
        or not 1 <= core_cap <= MAX_CORE_SECONDS
    ):
        raise QueueError("allocated-core cap must be positive and at most 2700 core-hours")
    selector_budget = plan["selector_wall_budget_s"]
    if (
        isinstance(selector_budget, bool)
        or not isinstance(selector_budget, int)
        or not 30 <= selector_budget <= 600
    ):
        raise QueueError("selector wall cap must be 30–600 seconds")
    if _utc(plan["cutoff_utc"], "cutoff_utc") <= datetime.now(UTC):
        raise QueueError("queue cutoff has passed")

    walls = plan["wall_budget_s_by_stage"]
    floors = plan["minimum_free_disk_gib_by_stage"]
    if (
        not isinstance(walls, dict)
        or set(walls) != STAGES
        or not isinstance(floors, dict)
        or set(floors) != STAGES
    ):
        raise QueueError("wall and disk budgets must name every fixed queue stage")
    for stage in STAGES:
        wall, floor = walls[stage], floors[stage]
        wall_max = 12 * 3600 if stage == "five_second" else 6 * 3600
        if isinstance(wall, bool) or not isinstance(wall, int) or not 400 <= wall <= wall_max:
            raise QueueError(f"invalid {stage} wall budget")
        if isinstance(floor, bool) or not isinstance(floor, int) or not 4 <= floor <= 64:
            raise QueueError(f"invalid {stage} free-space floor")
        minimum_floor = {
            "diagnostic": 12,
            "short": 6,
            "scaling": 6,
            "half_second": 6,
            "five_second": 4,
        }[stage]
        if floor < minimum_floor:
            raise QueueError(f"{stage} free-space floor must be at least {minimum_floor} GiB")

    _validate_seeds(plan)
    return plan, hashlib.sha256(raw).hexdigest()


def _validate_seeds(plan: dict[str, Any]) -> None:
    seeds = plan["seed_cases"]
    if not isinstance(seeds, list) or len(seeds) not in {2, 3}:
        raise QueueError("seed_cases must contain N1/N2 and only the optional approved N3 run")
    expected = [
        ("N1-UPWIND-64-1MS-001", 64, 1, 0.01, 0.001, "upwind"),
        ("N2-ORIGINAL-64-01MS-001", 64, 1, 0.01, 0.0001, "original"),
    ]
    if len(seeds) == 3:
        expected.append(("N3-ORIGINAL-64-05MS-001", 64, 1, 0.01, 0.0005, "original"))
    job_ids: set[str] = set()
    for seed, (case_id, ranks, nodes, horizon, dt, variant) in zip(seeds, expected, strict=True):
        required = {
            "case_id",
            "job_id",
            "run_dir",
            "ranks",
            "nodes",
            "horizon_s",
            "delta_t_s",
            "numerical_variant",
            "input_archive_sha256",
            "run_state_sha256",
            "result_archive_sha256",
            "supplementary_audit",
            "accounting_snapshot",
        }
        if not isinstance(seed, dict) or set(seed) != required:
            raise QueueError("each seed must have the exact approved fields")
        if (
            seed["case_id"],
            seed["ranks"],
            seed["nodes"],
            seed["horizon_s"],
            seed["delta_t_s"],
            seed["numerical_variant"],
        ) != (case_id, ranks, nodes, horizon, dt, variant):
            raise QueueError("seed profile differs from the approved N1/N2 diagnostic pair")
        if seed["input_archive_sha256"] != plan["input_archive"]["sha256"]:
            raise QueueError("seed mesh input hash differs from plan")
        if not isinstance(seed["job_id"], str) or not seed["job_id"].isdigit():
            raise QueueError("seed job IDs must be numeric strings")
        if seed["job_id"] in job_ids:
            raise QueueError("seed job IDs must be distinct")
        job_ids.add(seed["job_id"])
        run_dir = Path(seed["run_dir"])
        root = Path(plan["project_root"])
        try:
            relative_run = run_dir.relative_to(root)
        except ValueError as error:
            raise QueueError("seed run directory must be under project_root") from error
        if any(
            (root / Path(*relative_run.parts[:index])).is_symlink()
            for index in range(1, len(relative_run.parts) + 1)
        ):
            raise QueueError("seed run directory traverses a symbolic link")
        if (
            run_dir.name != f"{RUN_PREFIX}{seed['job_id']}"
            or len(relative_run.parts) not in {1, 2}
            or (len(relative_run.parts) == 2 and not SAFE_ID.fullmatch(relative_run.parts[0]))
            or run_dir.is_symlink()
        ):
            raise QueueError(
                "seed run directory is outside its approved direct/versioned-root path"
            )
        for key in ("run_state_sha256", "result_archive_sha256"):
            value = seed[key]
            if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                raise QueueError(f"seed {key} must be null or a lowercase SHA-256")
        audit = seed["supplementary_audit"]
        if audit is not None:
            audit_path = _hash_record(audit, "seed supplementary_audit")
            if not audit_path.is_relative_to(root):
                raise QueueError("seed supplementary audit must be under project_root")
        snapshot = seed["accounting_snapshot"]
        if snapshot is not None:
            snapshot_path = _hash_record(snapshot, "seed accounting_snapshot")
            if not snapshot_path.is_relative_to(root):
                raise QueueError("seed accounting snapshot must be under project_root")


def _profile(phase: str, ranks: int, horizon: float, dt: float, variant: str) -> dict[str, Any]:
    if (
        ranks not in PLACEMENTS
        or horizon not in {0.01, 0.05, 0.5, 5.0}
        or dt not in {0.001, 0.0005, 0.0001}
        or variant not in {"original", "upwind"}
    ):
        raise QueueError("selection produced an undeclared case profile")
    stage = (
        "diagnostic"
        if horizon == 0.01
        else "short"
        if horizon == 0.05 and phase == "validation64"
        else "scaling"
        if horizon == 0.05
        else "half_second"
        if horizon == 0.5
        else "five_second"
    )
    case_id = {
        "diagnostic_n3": "N3-ORIGINAL-64-05MS-001",
        "upwind_temporal": "N4-UPWIND-64-05MS-001",
    }.get(phase, f"{phase}-{variant}-{ranks}-{dt:g}")
    return {
        "case_id": case_id,
        "phase": phase,
        "ranks": ranks,
        "nodes": PLACEMENTS[ranks],
        "horizon_s": horizon,
        "delta_t_s": dt,
        "numerical_variant": variant,
        "retention_mode": "full" if horizon >= 0.5 else "diagnostic",
        "write_interval_s": 1.0 if horizon == 5.0 else horizon,
        "stage": stage,
    }


def _seed_profile(seed: dict[str, Any]) -> dict[str, Any]:
    phase = {
        "N1-UPWIND-64-1MS-001": "diagnostic_n1",
        "N2-ORIGINAL-64-01MS-001": "diagnostic_n2",
        "N3-ORIGINAL-64-05MS-001": "diagnostic_n3",
    }[seed["case_id"]]
    return {
        "case_id": seed["case_id"],
        "phase": phase,
        "ranks": seed["ranks"],
        "nodes": seed["nodes"],
        "horizon_s": seed["horizon_s"],
        "delta_t_s": seed["delta_t_s"],
        "numerical_variant": seed["numerical_variant"],
        "retention_mode": "full",
        "write_interval_s": seed["horizon_s"],
        "stage": "diagnostic",
    }


def _viable(run_state: dict[str, Any]) -> bool:
    speed = run_state.get("solver_max_u_m_s")
    return bool(
        run_state.get("status") == "solver_complete_exploratory"
        and run_state.get("solver_exit_code") == 0
        and run_state.get("stop_reason") is None
        and run_state.get("solver_end_marker") is True
        and isinstance(speed, (int, float))
        and math.isfinite(speed)
        and speed <= 1000
        and run_state.get("ledger_audit_status") == "raw_exploratory_ledger_written"
        and isinstance(run_state.get("solver_convergence"), dict)
        and run_state["solver_convergence"].get("all_converged") is True
        and run_state.get("attempt_archive_status") == "verified_crc_hash_and_member_list"
    )


def _supplementary_seed_audit(
    seed: dict[str, Any],
    run_state: dict[str, Any],
    run_state_sha256: str,
    accounting: dict[str, Any],
) -> dict[str, Any] | None:
    audit_record = seed["supplementary_audit"]
    if audit_record is None:
        return None
    receipt_path = _hash_record(audit_record, "seed supplementary_audit")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    run_id = run_state.get("run_id")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("supplementary_audit_status") != "completed_exploratory_only"
        or receipt.get("attempt_id") != run_id
        or receipt.get("formal_validation_decision") is not None
    ):
        raise QueueError("supplementary seed audit status or attempt identity is invalid")
    speed = run_state.get("solver_max_u_m_s")
    convergence = run_state.get("solver_convergence")
    if (
        run_state.get("status") != "solver_complete_ledger_failed"
        or run_state.get("solver_exit_code") != 0
        or run_state.get("stop_reason") is not None
        or run_state.get("solver_end_marker") is not True
        or not isinstance(speed, (int, float))
        or not math.isfinite(speed)
        or speed > 1000
        or not isinstance(convergence, dict)
        or convergence.get("all_converged") is not True
        or run_state.get("attempt_archive_status") != "verified_crc_hash_and_member_list"
    ):
        raise QueueError(
            "supplementary audit cannot override a solver, stability, or archive failure"
        )
    original = receipt.get("original_run_record", {})
    archive_info = receipt.get("original_result_archive", {})
    if (
        original.get("job_id") != seed["job_id"]
        or original.get("run_state_sha256") != run_state_sha256
        or (
            accounting.get("is_upper_bound") is not True
            and original.get("terminal_status") != accounting["state"]
        )
        or original.get("terminal_status") != "FAILED"
        or original.get("solver_step_status") != "COMPLETED"
        or archive_info.get("sha256") != run_state.get("result_archive_sha256")
        or archive_info.get("bytes") != (Path(run_state["result_archive"]).stat().st_size)
        or archive_info.get("member_count") != run_state.get("result_archive_members")
    ):
        raise QueueError(
            "supplementary seed audit does not bind the original Slurm attempt/archive"
        )

    raw = receipt.get("raw_input_bindings", {})
    input_archive_bindings = [
        raw[key]
        for key in (
            "input_archive_sha256_from_run_state",
            "input_archive_sha256_from_run_state_and_case_inputs",
        )
        if key in raw
    ]
    if (
        len(input_archive_bindings) != 1
        or raw.get("solver_log_sha256") != run_state.get("solver_log_sha256")
        or raw.get("prepared_input_verification") != "verified"
        or raw.get("prepared_input_verified_file_count") != 22
        or raw.get("solver_identity_verification") != "native-module-source-correspondence"
        or raw.get("case_profile") != seed["case_id"]
        or raw.get("numerical_variant") != seed["numerical_variant"]
        or raw.get("horizon_s_from_run_state_and_case_inputs") != seed["horizon_s"]
        or raw.get("delta_t_s_from_run_state_and_case_inputs") != seed["delta_t_s"]
        or input_archive_bindings[0] != run_state.get("input_archive_sha256")
        or ("ranks" in raw and raw["ranks"] != seed["ranks"])
        or ("nodes" in raw and raw["nodes"] != seed["nodes"])
        or ("solver_version" in raw and raw["solver_version"] != "v2512")
    ):
        raise QueueError("supplementary seed audit raw log/provenance binding is incomplete")

    root = receipt_path.parent
    outputs = receipt.get("supplementary_outputs", {})
    summary_path = root / "ledger-fixed-controlDict/summary.json"
    ledger_path = root / "ledger-fixed-controlDict/ledger.csv"
    if (
        summary_path.is_symlink()
        or not summary_path.is_file()
        or ledger_path.is_symlink()
        or not ledger_path.is_file()
        or sha256_file(summary_path) != outputs.get("summary_json_sha256")
        or sha256_file(ledger_path) != outputs.get("ledger_csv_sha256")
    ):
        raise QueueError("supplementary seed audit output hashes are missing or changed")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit = receipt.get("audit_result", {})
    coverage = summary.get("coverage", {})
    prepared = summary.get("prepared_input_hash_verification", {})
    input_identity = receipt.get("raw_input_bindings", {})
    rows = audit.get("matched_rows")
    if (
        audit.get("auditor_sha256") != SUPPLEMENTARY_AUDITOR_SHA256
        or summary.get("source_code_and_input_sha256", {}).get("audit_script_sha256")
        != SUPPLEMENTARY_AUDITOR_SHA256
        or audit.get("coverage_status") != "configured_horizon_reached_exploratory_only"
        or coverage.get("status") != "configured_horizon_reached_exploratory_only"
        or coverage.get("configured_horizon_reached") is not True
        or coverage.get("coverage_fraction_of_requested_horizon") != 1.0
        or audit.get("configured_horizon_s") != seed["horizon_s"]
        or coverage.get("configured_horizon_s") != seed["horizon_s"]
        or audit.get("first_matched_time_s") != seed["delta_t_s"]
        or audit.get("last_matched_time_s") != seed["horizon_s"]
        or audit.get("matched_rows") != run_state.get("solver_time_steps_recorded")
        or audit.get("formal_validation_decision") is not None
        or summary.get("formal_validation_decision") is not None
        or prepared.get("verification_status") != "verified"
        or prepared.get("verified_file_count") != 22
        or input_identity.get("solver_log_sha256") != run_state.get("solver_log_sha256")
        or receipt.get("timestep_provenance", {}).get("mode") != "fixed-controlDict"
        or receipt.get("timestep_provenance", {}).get("controlDict_deltaT_token")
        != f"{seed['delta_t_s']:g}"
        or not isinstance(rows, int)
        or rows < 1
    ):
        raise QueueError("supplementary seed ledger does not cover every configured solver step")
    row_coverage = summary.get("row_coverage", {})
    if not row_coverage or any(
        not isinstance(value, dict) or value.get("matched_common_prefix_rows") != rows
        for value in row_coverage.values()
    ):
        raise QueueError("supplementary seed report row coverage is incomplete")
    image_verification = summary.get("solver_image_verification", {})
    reported_native = image_verification.get("native_solver", {})
    source_native = image_verification.get("source_evidence", {}).get("native_solver", {})
    if (
        image_verification.get("execution_backend") != "slurm-native"
        or image_verification.get("verification_mode") != "native-module-source-correspondence"
        or reported_native.get("version") != "v2512"
        or reported_native.get("architecture") != "x86_64"
        or reported_native.get("precision") != "DP"
        or reported_native.get("label_size_bits") != 32
        or not SHA256.fullmatch(str(reported_native.get("executable_sha256", "")))
        or source_native.get("executable_sha256") != reported_native.get("executable_sha256")
    ):
        raise QueueError("supplementary seed audit solver provenance does not match run manifest")
    return {
        "status": receipt["supplementary_audit_status"],
        "receipt_sha256": audit_record["sha256"],
        "auditor_sha256": audit["auditor_sha256"],
        "matched_rows": rows,
        "closure_residual_kg": audit.get("closure_residual_kg"),
        "formal_validation_decision": None,
    }


def _clock(record: dict[str, Any], key: str) -> float | None:
    value = record.get("solver_clock_windows", {}).get(key)
    seconds = value.get("solver_clock_seconds") if isinstance(value, dict) else None
    if value is None or value.get("status") != "measured" or not isinstance(seconds, (int, float)):
        return None
    return float(seconds) if math.isfinite(seconds) and seconds > 0 else None


def _fastest(
    records: list[dict[str, Any]], window: str, omit_ranks: set[int] | None = None
) -> dict[str, Any] | None:
    omit_ranks = omit_ranks or set()
    rows = [
        row
        for row in records
        if row.get("viable")
        and row["profile"]["ranks"] not in omit_ranks
        and _clock(row, window) is not None
    ]
    rows.sort(key=lambda row: (_clock(row, window), row["profile"]["ranks"]))
    return rows[0] if rows else None


def _candidate(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_id = {row["case_id"]: row for row in results}
    for case_id, variant, dt in (
        ("N3-ORIGINAL-64-05MS-001", "original", 0.0005),
        ("N2-ORIGINAL-64-01MS-001", "original", 0.0001),
        ("N1-UPWIND-64-1MS-001", "upwind", 0.001),
    ):
        row = by_id.get(case_id)
        if row and row["viable"]:
            return {"source_case_id": case_id, "numerical_variant": variant, "delta_t_s": dt}
    return None


def _candidate_next(
    selected: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
    if selected is None:
        return None, "no startup diagnostic passed completion, ledger, and residual gates", None
    if selected["numerical_variant"] == "upwind" and selected["delta_t_s"] == 0.001:
        return (
            _profile("upwind_temporal", 64, 0.01, 0.0005, "upwind"),
            "only upwind 1 ms passed; run a separate fixed 0.5 ms temporal check",
            selected,
        )
    return (
        _profile("validation64", 64, 0.05, selected["delta_t_s"], selected["numerical_variant"]),
        "selected startup profile merits a fresh 0.05 s validation",
        selected,
    )


def _half_next(
    history: list[dict[str, Any]], selected: dict[str, Any], reason: str
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    tested = [
        row
        for row in history
        if row["profile"]["phase"] in {"validation64", "scale120", "scale240", "scale300"}
    ]
    best = _fastest(tested, "0.010..0.049s")
    if best is None:
        return (
            None,
            "no viable measured scaling case has the declared startup-excluded clock window",
            selected,
        )
    selected = {
        **selected,
        "best_ranks": best["profile"]["ranks"],
        "best_source_case_id": best["case_id"],
    }
    return (
        _profile(
            "half_best",
            best["profile"]["ranks"],
            0.5,
            selected["delta_t_s"],
            selected["numerical_variant"],
        ),
        reason,
        selected,
    )


def _five_next(
    history: list[dict[str, Any]], selected: dict[str, Any], reason: str
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    half = [row for row in history if row["profile"]["phase"] == "half_best"]
    best = _fastest(half, "0.250..0.490s")
    if best is None:
        return None, "no 0.5 s run has a measured 0.250–0.490 s clock window", selected
    selected = {
        **selected,
        "best_ranks": best["profile"]["ranks"],
        "best_source_case_id": best["case_id"],
    }
    return (
        _profile(
            "five_best",
            best["profile"]["ranks"],
            5.0,
            selected["delta_t_s"],
            selected["numerical_variant"],
        ),
        reason,
        selected,
    )


def _state_empty(plan: dict[str, Any], plan_sha: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "queue_id": plan["queue_id"],
        "plan_sha256": plan_sha,
        "events": [],
    }


def _read_state(path: Path, plan: dict[str, Any], plan_sha: str) -> dict[str, Any]:
    if not path.exists():
        return _state_empty(plan, plan_sha)
    if path.is_symlink() or not path.is_file():
        raise QueueError("queue state is not a regular file")
    state = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(state, dict)
        or set(state) != {"schema_version", "queue_id", "plan_sha256", "events"}
        or state["schema_version"] != 1
        or state["queue_id"] != plan["queue_id"]
        or state["plan_sha256"] != plan_sha
        or not isinstance(state["events"], list)
    ):
        raise QueueError("queue state does not match immutable plan")
    previous = "0" * 64
    for index, event in enumerate(state["events"]):
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        if (
            event.get("sequence") != index
            or event.get("previous_event_sha256") != previous
            or hashlib.sha256(_json_bytes(body)).hexdigest() != event.get("event_sha256")
        ):
            raise QueueError("queue state hash chain is broken")
        previous = event["event_sha256"]
    return state


def _append(state: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    event = {
        **body,
        "sequence": len(state["events"]),
        "previous_event_sha256": state["events"][-1]["event_sha256"]
        if state["events"]
        else "0" * 64,
    }
    event["event_sha256"] = hashlib.sha256(_json_bytes(event)).hexdigest()
    state["events"].append(event)
    return event


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_json_bytes(state) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sacct(
    job_id: str,
    run: Callable[..., Any],
    *,
    seed: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    run_state: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    if seed is not None and seed.get("accounting_snapshot") is not None:
        path = _hash_record(seed["accounting_snapshot"], "seed accounting_snapshot")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        root = (project_root or Path(seed["run_dir"]).parent).resolve(strict=True)
        jobs = snapshot.get("jobs", []) if isinstance(snapshot, dict) else []
        rows = [item for item in jobs if isinstance(item, dict) and item.get("job_id") == job_id]
        row = rows[0] if len(rows) == 1 else {}
        source = row.get("source", {})
        if (
            not isinstance(snapshot, dict)
            or set(snapshot) != {"schema", "captured_utc", "jobs", "source_note"}
            or snapshot.get("schema") != "rouaix-hpc-seed-accounting-v1"
            or not isinstance(jobs, list)
            or len(rows) != 1
            or set(row) != {"job_id", "alloc_cpus", "elapsed_s", "state", "source"}
            or isinstance(row.get("alloc_cpus"), bool)
            or not isinstance(row.get("alloc_cpus"), int)
            or row["alloc_cpus"] <= 0
            or isinstance(row.get("elapsed_s"), bool)
            or not isinstance(row.get("elapsed_s"), int)
            or row["elapsed_s"] < 0
            or row.get("state") not in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"}
            or not isinstance(source, dict)
            or set(source) != {"path", "sha256"}
            or not isinstance(source.get("sha256"), str)
            or not SHA256.fullmatch(source["sha256"])
        ):
            raise QueueError(f"invalid staged Slurm accounting snapshot for {job_id}")
        source_path = _file(source.get("path"), "seed accounting raw source")
        if not source_path.is_relative_to(root) or sha256_file(source_path) != source["sha256"]:
            raise QueueError(f"seed accounting raw source hash/root mismatch for {job_id}")
        accounting = {
            "job_id": job_id,
            "alloc_cpus": row["alloc_cpus"],
            "elapsed_s": row["elapsed_s"],
            "state": row["state"],
            "source": "seed_accounting_snapshot",
            "is_upper_bound": False,
            "snapshot_sha256": seed["accounting_snapshot"]["sha256"],
            "raw_source_sha256": source["sha256"],
        }
        return accounting["alloc_cpus"] * accounting["elapsed_s"], accounting

    cmd = ["sacct", "-n", "-P", "-j", job_id, "--format=JobIDRaw,AllocCPUS,ElapsedRaw,State"]
    try:
        result = run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        result = None
    rows = (
        [line.split("|") for line in result.stdout.splitlines() if line.strip()]
        if result is not None and result.returncode == 0
        else []
    )
    rows = [row for row in rows if len(row) == 4 and row[0] == job_id]
    if len(rows) == 1:
        try:
            cpus, elapsed = int(rows[0][1]), int(rows[0][2])
        except ValueError:
            cpus, elapsed = 0, -1
        if cpus > 0 and elapsed >= 0:
            return cpus * elapsed, {
                "job_id": job_id,
                "alloc_cpus": cpus,
                "elapsed_s": elapsed,
                "state": rows[0][3].split()[0],
                "source": "sacct",
                "is_upper_bound": False,
            }

    try:
        result = run(
            ["scontrol", "show", "job", "-o", job_id],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0:
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) == 1:
            fields = dict(
                re.findall(r"(?:^|\s)(JobId|NumCPUs|RunTime|JobState|State)=([^\s]+)", lines[0])
            )
            runtime = fields.get("RunTime", "")
            cpus_text = fields.get("NumCPUs", "")
            state = fields.get("JobState", fields.get("State", ""))
            try:
                cpus = int(cpus_text)
                elapsed = _slurm_elapsed_seconds(runtime)
            except (ValueError, QueueError):
                cpus, elapsed = 0, -1
            if fields.get("JobId") == job_id and cpus > 0 and elapsed >= 0 and state:
                return cpus * elapsed, {
                    "job_id": job_id,
                    "alloc_cpus": cpus,
                    "elapsed_s": elapsed,
                    "state": state,
                    "source": "scontrol",
                    "is_upper_bound": False,
                }

    if profile is None or run_state is None:
        raise QueueError(f"Slurm accounting is unavailable for completed job {job_id}")
    cpus = int(profile["nodes"]) * 128
    elapsed = int(profile.get("wall_budget_s", run_state.get("wall_time_s", 0)))
    if cpus <= 0 or elapsed <= 0:
        raise QueueError(f"cannot form a conservative allocation bound for {job_id}")
    return cpus * elapsed, {
        "job_id": job_id,
        "alloc_cpus": cpus,
        "elapsed_s": elapsed,
        "state": "UNAVAILABLE",
        "source": "conservative_allocation_upper_bound",
        "is_upper_bound": True,
    }


def _slurm_elapsed_seconds(value: str) -> int:
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d{2}):(\d{2})", value)
    if match is None:
        raise QueueError("invalid Slurm RunTime value")
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise QueueError("invalid Slurm RunTime clock fields")
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _next(
    history: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
    if len(history) < 2:
        return None, "adopted N1 and N2 results are required before dispatch", None
    by_phase = {item["profile"]["phase"]: item for item in history}
    phase = history[-1]["profile"]["phase"]
    if not {"diagnostic_n1", "diagnostic_n2"} <= set(by_phase):
        return None, "both declared N1 and N2 outcomes must be adopted before dispatch", None
    if phase == "diagnostic_n2":
        if by_phase["diagnostic_n2"]["viable"]:
            return (
                _profile("diagnostic_n3", 64, 0.01, 0.0005, "original"),
                "N2 passed; run the predeclared original-scheme 0.5 ms diagnostic",
                None,
            )
        selected = _candidate(history)
        return _candidate_next(selected)
    if phase == "diagnostic_n3":
        return _candidate_next(_candidate(history))
    if phase == "upwind_temporal":
        if not history[-1]["viable"]:
            return None, "upwind 0.5 ms temporal check failed", None
        selected = {
            "source_case_id": history[-1]["case_id"],
            "numerical_variant": "upwind",
            "delta_t_s": 0.0005,
        }
        return (
            _profile("validation64", 64, 0.05, 0.0005, "upwind"),
            "upwind startup and temporal checks passed",
            selected,
        )

    selected = next(
        (item.get("chosen_profile") for item in reversed(history) if item.get("chosen_profile")),
        None,
    ) or _candidate(history)
    if selected is None:
        return None, "selected numerical profile is unavailable", None
    if phase == "validation64":
        if not history[-1]["viable"]:
            return None, "fresh 0.05 s validation failed", selected
        return (
            _profile("scale120", 120, 0.05, selected["delta_t_s"], selected["numerical_variant"]),
            "64-rank validation passed; test 120-rank placement",
            selected,
        )
    if phase == "scale120":
        if history[-1]["viable"]:
            return (
                _profile(
                    "scale240", 240, 0.05, selected["delta_t_s"], selected["numerical_variant"]
                ),
                "120-rank case passed; test two-node 240-rank placement",
                selected,
            )
        return _half_next(
            history, selected, "120-rank case failed; use only a viable measured placement"
        )
    if phase == "scale240":
        if history[-1]["viable"]:
            return (
                _profile(
                    "scale300", 300, 0.05, selected["delta_t_s"], selected["numerical_variant"]
                ),
                "240-rank case passed; try 300 ranks if budgets fit",
                selected,
            )
        return _half_next(
            history, selected, "240-rank case failed; use only viable 64/120-rank results"
        )
    if phase == "scale300":
        return _half_next(
            history, selected, "rank series complete; select by the 0.010–0.049 s clock window"
        )
    if phase == "half_best":
        if not history[-1]["viable"]:
            return None, "best measured placement failed at 0.5 s; do not attempt 5 s", selected
        return _five_next(
            history, selected, "0.5 s best passed; proceed to the declared 5 s clean start"
        )
    if phase == "five_best":
        return None, "declared overnight sequence complete", selected
    return None, f"no further case declared after {phase}", selected


def _seconds_since_start(started: float) -> int:
    return max(0, math.ceil(time.monotonic() - started))


def _record_completion(
    plan: dict[str, Any], state: dict[str, Any], case_id: str, job_id: str, run: Callable[..., Any]
) -> dict[str, Any]:
    key = f"complete:{job_id}"
    old = next((item for item in state["events"] if item.get("idempotency_key") == key), None)
    if old:
        return old["case_record"]
    seed = next(
        (
            item
            for item in plan["seed_cases"]
            if item["case_id"] == case_id and item["job_id"] == job_id
        ),
        None,
    )
    run_dir = (
        Path(seed["run_dir"])
        if seed is not None
        else Path(plan["project_root"]) / f"{RUN_PREFIX}{job_id}"
    )
    state_path = run_dir / "run-state.json"
    if (
        run_dir.is_symlink()
        or not run_dir.is_dir()
        or state_path.is_symlink()
        or not state_path.is_file()
    ):
        raise QueueError(f"run-state missing for {case_id}/{job_id}")
    raw = state_path.read_bytes()
    run_state = json.loads(raw)
    if (
        run_state.get("job_id") != job_id
        or run_state.get("case_id") != case_id
        or run_state.get("input_archive_sha256") != plan["input_archive"]["sha256"]
    ):
        raise QueueError(
            "completed case state does not match the approved job, case, or input hash"
        )
    accepted = next(
        (
            item
            for item in state["events"]
            if item.get("event_type") == "case_submission_accepted"
            and item.get("case_id") == case_id
            and item.get("job_id") == job_id
        ),
        None,
    )
    if accepted:
        profile, chosen = accepted["profile"], accepted.get("chosen_profile")
        if seed is not None:
            raise QueueError("a seed job cannot also be a queued case submission")
    elif seed:
        profile, chosen = _seed_profile(seed), None
        if seed["run_state_sha256"] and hashlib.sha256(raw).hexdigest() != seed["run_state_sha256"]:
            raise QueueError("seed run-state hash differs from plan")
        if (
            seed["result_archive_sha256"]
            and run_state.get("result_archive_sha256") != seed["result_archive_sha256"]
        ):
            raise QueueError("seed archive hash differs from plan")
    else:
        raise QueueError("completed case was not declared as a seed or queue submission")
    expected = {
        "ranks": profile["ranks"],
        "nodes": profile["nodes"],
        "horizon_s": profile["horizon_s"],
        "delta_t_s": profile["delta_t_s"],
        "numerical_variant": profile["numerical_variant"],
        "retention_mode": profile["retention_mode"],
        "write_interval_s": profile["write_interval_s"],
    }
    if any(run_state.get(key) != value for key, value in expected.items()):
        raise QueueError("run-state profile differs from its immutable declaration")
    if (run_state.get("execution_backend"), run_state.get("solver_version")) != (
        "slurm-native",
        "v2512",
    ):
        raise QueueError("completed case has wrong native backend or solver version")
    archive_sha = run_state.get("result_archive_sha256")
    archive: Path | None = None
    if run_state.get("attempt_archive_status") == "verified_crc_hash_and_member_list":
        archive = run_dir / "result.tar.gz"
        if (
            run_state.get("result_archive") != str(archive)
            or archive.is_symlink()
            or not archive.is_file()
            or sha256_file(archive) != archive_sha
        ):
            raise QueueError("verified result archive is missing or hash-mismatched")
    elif run_state.get("solver_started_utc"):
        raise QueueError("solver-started case has no verified archive; queue stops")
    core_seconds, accounting = _sacct(
        job_id,
        run,
        seed=seed,
        profile=profile,
        run_state=run_state,
        project_root=Path(plan["project_root"]),
    )
    supplementary = (
        _supplementary_seed_audit(seed, run_state, hashlib.sha256(raw).hexdigest(), accounting)
        if seed is not None
        else None
    )
    raw_viable = _viable(run_state)
    record = {
        "case_id": case_id,
        "job_id": job_id,
        "profile": profile,
        "chosen_profile": chosen,
        "run_state_sha256": hashlib.sha256(raw).hexdigest(),
        "result_archive_sha256": archive_sha,
        "allocated_core_seconds": core_seconds,
        "accounting": accounting,
        "status": run_state.get("status"),
        "solver_exit_code": run_state.get("solver_exit_code"),
        "stop_reason": run_state.get("stop_reason"),
        "solver_end_marker": run_state.get("solver_end_marker"),
        "solver_max_u_m_s": run_state.get("solver_max_u_m_s"),
        "ledger_audit_status": run_state.get("ledger_audit_status"),
        "solver_convergence": run_state.get("solver_convergence"),
        "solver_clock_windows": run_state.get("solver_clock_windows", {}),
        "solver_wall_s": run_state.get("solver_wall_s"),
        "solver_time_steps_recorded": run_state.get("solver_time_steps_recorded"),
        "result_archive_bytes": archive.stat().st_size if archive is not None else None,
        "result_archive_members": run_state.get("result_archive_members"),
        "result_archive_member_sizes": run_state.get("result_archive_member_sizes"),
        "attempt_archive_status": run_state.get("attempt_archive_status"),
        "viable": raw_viable or supplementary is not None,
        "eligibility_basis": (
            "raw_runner_audit"
            if raw_viable
            else "supplementary_seed_audit"
            if supplementary is not None
            else "ineligible"
        ),
        "supplementary_audit": supplementary,
    }
    _append(
        state,
        {
            "event_type": "case_completed",
            "idempotency_key": key,
            "case_id": case_id,
            "job_id": job_id,
            "case_record": record,
        },
    )
    return record


def _history(state: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        event["case_record"]
        for event in state["events"]
        if event.get("event_type") == "case_completed"
    ]
    ids = [seed["case_id"] for seed in plan["seed_cases"]] + [
        event["case_id"]
        for event in state["events"]
        if event.get("event_type") == "case_submission_accepted"
    ]
    by_id = {item["case_id"]: item for item in rows}
    return [by_id[key] for key in dict.fromkeys(ids) if key in by_id]


def _sacct_spent(state: dict[str, Any]) -> int:
    return sum(
        int(event["case_record"].get("allocated_core_seconds", 0))
        for event in state["events"]
        if event.get("event_type") == "case_completed"
    )


def _wall_forecast(
    history: list[dict[str, Any]], profile: dict[str, Any]
) -> tuple[int, int, dict[str, Any]] | None:
    rows: list[tuple[int, dict[str, Any]]] = []
    setup_pack_s = 0
    for index, record in enumerate(history):
        previous = record["profile"]
        wall = record.get("solver_wall_s")
        steps = record.get("solver_time_steps_recorded")
        if (
            not record.get("viable")
            or previous.get("numerical_variant") != profile["numerical_variant"]
            or previous.get("delta_t_s") != profile["delta_t_s"]
            or not isinstance(wall, (int, float))
            or not math.isfinite(wall)
            or wall <= 0
            or isinstance(steps, bool)
            or not isinstance(steps, int)
            or steps <= 0
        ):
            continue
        rows.append((index, record))
        accounting = record.get("accounting", {})
        elapsed = accounting.get("elapsed_s")
        if isinstance(elapsed, int) and elapsed >= wall:
            setup_pack_s = max(setup_pack_s, math.ceil(elapsed - wall))
    if not rows:
        return None

    target_ranks = profile["ranks"]
    exact = [(index, row) for index, row in rows if row["profile"].get("ranks") == target_ranks]
    if exact:
        placement_rows = exact
        placement_basis = "exact_rank_count"
    else:
        measured_ranks = {row["profile"]["ranks"] for _, row in rows}
        nearest = min(
            measured_ranks, key=lambda ranks: (abs(ranks - target_ranks), ranks > target_ranks)
        )
        placement_rows = [(index, row) for index, row in rows if row["profile"]["ranks"] == nearest]
        placement_basis = "nearest_measured_rank_no_speedup_assumed"

    preferred_windows = (
        ("0.250..0.490s", "0.010..0.049s")
        if profile["horizon_s"] >= 0.5
        else ("0.010..0.049s",)
        if profile["horizon_s"] >= 0.05
        else ()
    )
    windowed = [
        (index, row, window)
        for index, row in placement_rows
        for window in preferred_windows
        if _clock(row, window) is not None
    ]
    if windowed:
        source_index, source, timing_window = max(
            windowed,
            key=lambda item: (item[1]["profile"].get("horizon_s", 0), item[0]),
        )
        window = source["solver_clock_windows"][timing_window]
        physical_s = window.get("physical_seconds")
        elapsed_s = window.get("solver_clock_seconds")
        if (
            not isinstance(physical_s, (int, float))
            or not isinstance(elapsed_s, (int, float))
            or physical_s <= 0
            or elapsed_s <= 0
        ):
            return None
        solver_s = math.ceil((elapsed_s / physical_s) * profile["horizon_s"])
    else:
        source_index, source = max(
            placement_rows,
            key=lambda item: (item[1]["profile"].get("horizon_s", 0), item[0]),
        )
        solver_s = math.ceil(
            (source["solver_wall_s"] / source["solver_time_steps_recorded"])
            * round(profile["horizon_s"] / profile["delta_t_s"])
        )
        timing_window = "full_run_includes_startup"
    return (
        solver_s,
        setup_pack_s,
        {
            "case_id": source["case_id"],
            "ranks": source["profile"]["ranks"],
            "horizon_s": source["profile"]["horizon_s"],
            "timing_window": timing_window,
            "placement_basis": placement_basis,
        },
    )


def _five_second_storage_estimate(
    history: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, int]:
    half = next(
        (
            row
            for row in reversed(history)
            if row["profile"]["phase"] == "half_best" and row.get("viable")
        ),
        None,
    )
    if half is None:
        raise QueueError("5 s storage estimate requires the viable measured 0.5 s archive")
    sizes = half.get("result_archive_member_sizes")
    if not isinstance(sizes, list) or not sizes:
        raise QueueError("0.5 s archive lacks its TarInfo member-size inventory")
    seen: set[str] = set()
    positive: dict[str, int] = {}
    metric_bytes = 0
    base_bytes = 0
    for item in sizes:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "bytes"}
            or not isinstance(item["path"], str)
            or isinstance(item["bytes"], bool)
            or not isinstance(item["bytes"], int)
            or item["bytes"] < 0
            or item["path"] in seen
        ):
            raise QueueError("0.5 s archive TarInfo inventory is malformed")
        seen.add(item["path"])
        parts = item["path"].split("/")
        if (
            len(parts) >= 5
            and parts[:2] == ["attempt", "case"]
            and re.fullmatch(r"processors\d+", parts[2])
            and re.fullmatch(r"\d+(?:\.\d+)?", parts[3])
        ):
            if float(parts[3]) > 0:
                positive[parts[3]] = positive.get(parts[3], 0) + item["bytes"]
            else:
                base_bytes += item["bytes"]
        elif "postProcessing" in parts or parts[-1] in {"solver.log", "max-speed.csv"}:
            metric_bytes += item["bytes"]
        else:
            base_bytes += item["bytes"]
    if not positive or metric_bytes <= 0 or base_bytes <= 0:
        raise QueueError(
            "0.5 s archive does not expose positive fields, metrics, and static/decomp base"
        )
    checkpoint_bytes = max(positive.values())
    scale = 5.0 / float(half["profile"]["horizon_s"])
    five_second_metric_bytes = math.ceil(metric_bytes * scale)
    with tarfile.open(plan["input_archive"]["path"], "r:gz") as archive:
        input_extract_bytes = sum(member.size for member in archive.getmembers() if member.isfile())
    write_peak = input_extract_bytes + base_bytes + 3 * checkpoint_bytes + five_second_metric_bytes
    packed_attempt = base_bytes + 2 * checkpoint_bytes + five_second_metric_bytes
    packing_peak = input_extract_bytes + 2 * packed_attempt
    return {
        "input_extract_bytes": input_extract_bytes,
        "static_and_decomposed_base_bytes": base_bytes,
        "measured_positive_checkpoint_bytes": checkpoint_bytes,
        "transient_three_checkpoint_write_peak_bytes": write_peak,
        "projected_five_second_metrics_bytes": five_second_metric_bytes,
        "packing_peak_bytes": packing_peak,
        "packing_headroom_bytes": 1024**3,
        "source_case_archive_bytes": int(half.get("result_archive_bytes") or 0),
    }


def _fit(
    plan: dict[str, Any],
    state: dict[str, Any],
    profile: dict[str, Any],
    now: datetime,
    selector_s: int,
) -> tuple[bool, str, dict[str, Any]]:
    stage = profile["stage"]
    forecast = _wall_forecast(_history(state, plan), profile)
    if forecast is None:
        return False, "no viable matching-profile solver timing is available", {}
    solver_forecast_s, setup_pack_s, forecast_source = forecast
    full_forecast_s = math.ceil(solver_forecast_s * 1.25 + setup_pack_s + 180)
    stage_cap = plan["wall_budget_s_by_stage"][stage]
    floor = plan["minimum_free_disk_gib_by_stage"][stage]
    selector_cap = plan["selector_wall_budget_s"]
    cutoff_left = (_utc(plan["cutoff_utc"], "cutoff_utc") - now).total_seconds()
    spent_selectors = sum(
        int(e.get("selector_core_seconds", 0))
        for e in state["events"]
        if e.get("event_type") in {"selector_complete", "queue_stopped"}
    )
    used = _sacct_spent(state) + spent_selectors + selector_s
    core_wall_limit = max(
        0,
        (plan["max_allocated_core_seconds"] - used - selector_cap) // profile["ranks"],
    )
    cutoff_wall_limit = max(0, math.floor(cutoff_left - selector_cap - 180))
    wall_limits = {
        "stage": stage_cap,
        "measured_full_case_forecast": full_forecast_s,
        "remaining_core_budget": core_wall_limit,
        "utc_cutoff": cutoff_wall_limit,
    }
    wall = min(wall_limits.values())
    limiting_wall_constraints = sorted(name for name, limit in wall_limits.items() if limit == wall)
    free = shutil.disk_usage(plan["project_root"]).free
    storage: dict[str, int] | None = None
    storage_required = floor * 1024**3
    if stage == "five_second":
        try:
            storage = _five_second_storage_estimate(_history(state, plan), plan)
        except (OSError, tarfile.TarError, QueueError) as error:
            return False, f"cannot establish measured 5 s storage bound: {error}", {}
        storage_required = max(
            storage["transient_three_checkpoint_write_peak_bytes"] + storage_required,
            storage["packing_peak_bytes"] + storage["packing_headroom_bytes"],
        )
    details = {
        "spent_case_core_seconds": _sacct_spent(state),
        "spent_selector_core_seconds": spent_selectors,
        "current_selector_elapsed_s": selector_s,
        "next_case_and_selector_worst_case_core_seconds": profile["ranks"] * wall + selector_cap,
        "projected_core_seconds": used + profile["ranks"] * wall + selector_cap,
        "core_cap": plan["max_allocated_core_seconds"],
        "solver_wall_forecast_s": solver_forecast_s,
        "measured_setup_and_pack_wall_s": setup_pack_s,
        "requested_full_case_wall_s": full_forecast_s,
        "declared_stage_wall_cap_s": stage_cap,
        "wall_budget_s": wall,
        "wall_budget_limiting_constraints": limiting_wall_constraints,
        "timing_source_case_id": forecast_source["case_id"],
        "timing_source_rank_count": forecast_source["ranks"],
        "timing_source_horizon_s": forecast_source["horizon_s"],
        "timing_source_window": forecast_source["timing_window"],
        "timing_placement_basis": forecast_source["placement_basis"],
        "wall_budget_is_cutoff_limited": "utc_cutoff" in limiting_wall_constraints,
        "free_disk_bytes": free,
        "minimum_free_disk_gib": floor,
        "required_free_disk_bytes": storage_required,
        "five_second_storage_estimate": storage,
    }
    if wall < 400:
        return (
            False,
            "remaining wall/core budget is below the runner stop-and-checkpoint allowance",
            details,
        )
    if stage != "five_second" and wall < full_forecast_s:
        return (
            False,
            "measured full-case forecast exceeds stage, core, or UTC cutoff budget",
            details,
        )
    if stage == "five_second":
        seconds_per_physical = solver_forecast_s / profile["horizon_s"]
        estimated_physical_progress = max(0.0, (wall - setup_pack_s) / seconds_per_physical)
        details["estimated_physical_progress_s"] = min(
            profile["horizon_s"], estimated_physical_progress
        )
        if estimated_physical_progress < 0.1:
            return (
                False,
                "remaining bounded 5 s allocation forecasts less than 0.1 s useful progress",
                details,
            )
    if used + profile["ranks"] * wall + selector_cap > plan["max_allocated_core_seconds"]:
        return False, "worst-case next allocation exceeds remaining core-hour cap", details
    if free < storage_required:
        reason = (
            "project scratch free space is below measured 5 s write/packing bound plus floor"
            if stage == "five_second"
            else "project scratch free space is below the declared stage floor"
        )
        return False, reason, details
    return True, "measured throughput, bounded allocation, core, and disk budgets fit", details


def parse_sbatch_output(
    stdout: str, stderr: str = "", returncode: int = 0
) -> tuple[str | None, dict[str, str]]:
    raw = {"stdout": stdout, "stderr": stderr, "returncode": str(returncode)}
    if returncode != 0:
        return None, raw
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None, raw
    match = re.fullmatch(r"([0-9]+)(?:;[A-Za-z0-9._-]+)?", lines[-1])
    if match is None or any(
        re.fullmatch(r"(?:Submitted batch job\s+)?[0-9]+(?:;[A-Za-z0-9._-]+)?", line)
        for line in lines[:-1]
    ):
        return None, raw
    return match.group(1), raw


def _sbatch(command: list[str], run: Callable[..., Any]) -> tuple[str | None, dict[str, str]]:
    try:
        result = run(command, capture_output=True, text=True, check=False, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, {"error": f"{type(error).__name__}: {error}", "stdout": "", "stderr": ""}
    return parse_sbatch_output(result.stdout or "", result.stderr or "", result.returncode)


def _slurm_time(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _export(values: dict[str, str]) -> str:
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in values):
        raise QueueError("invalid Slurm environment variable name")
    if any("," in value or "\n" in value or "\r" in value for value in values.values()):
        raise QueueError("Slurm environment values must not contain commas or newlines")
    return ",".join(f"{key}={value}" for key, value in values.items())


def build_submit_argv(
    plan: dict[str, Any],
    profile: dict[str, Any] | None = None,
    *,
    kind: str,
    plan_path: Path | None = None,
    state_path: Path | None = None,
    previous_case_id: str | None = None,
    previous_job_id: str | None = None,
) -> list[str]:
    """Build one explicit, bounded sbatch request without inheriting user env."""
    root = Path(plan["project_root"]).resolve(strict=True)
    if kind == "case":
        if profile is None:
            raise QueueError("case submission requires a declared profile")
        ranks = profile.get("ranks")
        if ranks not in PLACEMENTS or profile.get("nodes") != PLACEMENTS[ranks]:
            raise QueueError("case submission has an invalid rank/node placement")
        archive = _hash_record(plan["input_archive"], "input_archive")
        pilot = _hash_record(plan["pilot_sbatch"], "pilot_sbatch")
        expected_pilot = root / "cases/e1_rouaix_hpc/pilot.sbatch"
        if not archive.is_relative_to(root) or pilot != expected_pilot:
            raise QueueError("input archive and pilot script must belong to the exact project root")
        stage = profile["stage"]
        env = {
            "HOME": "/home/nk_memj",
            "USER": "nk_memj",
            "LOGNAME": "nk_memj",
            "PATH": "/usr/bin:/bin",
            "ROUAIX_PROJECT_ROOT": str(root),
            "ROUAIX_INPUT_ARCHIVE": str(archive),
            "ROUAIX_INPUT_SHA256": plan["input_archive"]["sha256"],
            "ROUAIX_CASE_ID": profile["case_id"],
            "ROUAIX_RANKS": str(ranks),
            "ROUAIX_NODES": str(profile["nodes"]),
            "ROUAIX_WALL_BUDGET_S": str(
                profile.get("wall_budget_s", plan["wall_budget_s_by_stage"][stage])
            ),
            "ROUAIX_END_TIME_S": f"{profile['horizon_s']:g}",
            "ROUAIX_DELTA_T_S": f"{profile['delta_t_s']:g}",
            "ROUAIX_NUMERICAL_VARIANT": profile["numerical_variant"],
            "ROUAIX_WRITE_INTERVAL_S": f"{profile['write_interval_s']:g}",
            "ROUAIX_RETENTION_MODE": profile["retention_mode"],
            "ROUAIX_MINIMUM_FREE_DISK_GIB": str(plan["minimum_free_disk_gib_by_stage"][stage]),
            "ROUAIX_HARD_DEADLINE_UTC": plan["cutoff_utc"],
            "ROUAIX_QUEUE_ID": plan["queue_id"],
        }
        if env.keys() != CASE_EXPORT_KEYS:
            raise QueueError(
                "case sbatch export is missing or adds an undeclared configuration variable"
            )
        command = [
            "sbatch",
            "--parsable",
            "--no-requeue",
            "--kill-on-invalid-dep=yes",
            f"--chdir={root}",
            f"--output={root}/rouaix-e1-hpc-%j.slurm.out",
            f"--nodes={profile['nodes']}",
            f"--ntasks={ranks}",
            *(
                [
                    f"--ntasks-per-node={ranks // profile['nodes']}",
                    "--distribution=block:block",
                ]
                if profile["nodes"] > 1
                else []
            ),
            "--cpus-per-task=1",
            f"--mem={plan['memory_gib_per_node']}G",
            f"--time={_slurm_time(profile.get('wall_budget_s', plan['wall_budget_s_by_stage'][stage]))}",
            "--job-name=ml-vof",
            f"--export={_export(env)}",
            str(pilot),
        ]
    elif kind == "selector":
        if plan_path is None or state_path is None or not previous_case_id or not previous_job_id:
            raise QueueError(
                "selector submission requires plan/state paths and its completed-case identity"
            )
        if plan_path.is_symlink() or not plan_path.is_absolute():
            raise QueueError("queue plan must be a regular absolute file")
        plan_path = plan_path.resolve(strict=True)
        if not plan_path.is_relative_to(root):
            raise QueueError("queue plan must be under project_root")
        if (
            state_path.is_symlink()
            or not state_path.is_absolute()
            or not state_path.parent.resolve().is_relative_to(root)
        ):
            raise QueueError("queue state must be under project_root")
        selector = _hash_record(plan["selector_sbatch"], "selector_sbatch")
        expected_selector = root / "cases/e1_rouaix_hpc/overnight_selector.sbatch"
        if (
            selector != expected_selector
            or not SAFE_ID.fullmatch(previous_case_id)
            or not previous_job_id.isdigit()
        ):
            raise QueueError("selector script or completed-case identity is invalid")
        env = {
            "HOME": "/home/nk_memj",
            "USER": "nk_memj",
            "LOGNAME": "nk_memj",
            "PATH": "/usr/bin:/bin",
            "ROUAIX_PROJECT_ROOT": str(root),
            "ROUAIX_QUEUE_PLAN": str(plan_path),
            "ROUAIX_QUEUE_STATE": str(state_path),
            "ROUAIX_QUEUE_MODE": "after-case",
            "ROUAIX_COMPLETED_CASE_ID": previous_case_id,
            "ROUAIX_COMPLETED_JOB_ID": previous_job_id,
        }
        if env.keys() != SELECTOR_EXPORT_KEYS:
            raise QueueError("selector sbatch export is missing or adds an undeclared variable")
        command = [
            "sbatch",
            "--parsable",
            "--no-requeue",
            "--kill-on-invalid-dep=yes",
            f"--chdir={root}",
            f"--output={root}/rouaix-e1-hpc-selector-%j.log",
            "--nodes=1",
            "--ntasks=1",
            "--cpus-per-task=1",
            "--mem=1G",
            f"--time={_slurm_time(plan['selector_wall_budget_s'])}",
            "--job-name=ml-vof-select",
            f"--dependency=afterany:{previous_job_id}",
            f"--export={_export(env)}",
            str(selector),
        ]
    else:
        raise QueueError("submission kind must be case or selector")
    return command


def _dispatch(
    plan: dict[str, Any],
    plan_path: Path,
    state_path: Path,
    state: dict[str, Any],
    previous_case_id: str,
    previous_job_id: str,
    started: float,
    run: Callable[..., Any],
) -> dict[str, Any]:
    key = f"dispatch-after:{previous_job_id}"
    if any(event.get("idempotency_key") == key for event in state["events"]):
        return {"status": "already_dispatched", "decision_key": key}
    selector_s = math.ceil(time.monotonic() - started)
    results = _history(state, plan)
    profile, rationale, chosen = _next(results)
    if profile is None:
        _append(
            state,
            {
                "event_type": "queue_stopped",
                "idempotency_key": key,
                "reason": rationale,
                "selector_core_seconds": selector_s,
            },
        )
        _write_state(state_path, state)
        return {"status": "complete_or_stopped", "reason": rationale}
    if Path(plan["pause_file"]).exists() or (Path(plan["project_root"]) / "PAUSE").exists():
        _append(
            state,
            {
                "event_type": "queue_stopped",
                "idempotency_key": key,
                "reason": "PAUSE marker exists",
                "selector_core_seconds": selector_s,
            },
        )
        _write_state(state_path, state)
        return {"status": "stopped", "reason": "PAUSE marker exists"}
    now = datetime.now(UTC)
    fits, reason, budget = _fit(plan, state, profile, now, selector_s)
    if not fits and profile["phase"] == "scale300":
        profile, rationale, chosen = _half_next(
            results,
            chosen or {},
            "300-rank case exceeds remaining budget; choose fastest measured case",
        )
        if profile:
            fits, reason, budget = _fit(plan, state, profile, now, selector_s)
    if not fits or profile is None:
        _append(
            state,
            {
                "event_type": "queue_stopped",
                "idempotency_key": key,
                "reason": reason if not fits else rationale,
                "budget": budget,
                "selector_core_seconds": selector_s,
            },
        )
        _write_state(state_path, state)
        return {"status": "stopped", "reason": reason if not fits else rationale}

    profile = {**profile, "wall_budget_s": budget["wall_budget_s"]}

    _append(
        state,
        {
            "event_type": "dispatch_intent",
            "idempotency_key": key,
            "previous_case_id": previous_case_id,
            "previous_job_id": previous_job_id,
            "next_case_id": profile["case_id"],
            "profile": profile,
            "chosen_profile": chosen,
            "rationale": rationale,
            "budget": budget,
            "selector_core_seconds": selector_s,
        },
    )
    _write_state(state_path, state)
    case_command = build_submit_argv(plan, profile, kind="case")
    case_job, case_raw = _sbatch(case_command, run)
    if case_job is None:
        _append(
            state,
            {
                "event_type": "case_submission_ambiguous",
                "idempotency_key": f"case:{key}",
                "command": case_command,
                "raw_output": case_raw,
                "instruction": "Do not resubmit automatically; inspect Slurm output.",
            },
        )
        _write_state(state_path, state)
        return {"status": "submission_ambiguous", "raw_output": case_raw}

    # The next selector is dependency-only and costs no solver resources while waiting.
    selector_command = build_submit_argv(
        plan,
        kind="selector",
        plan_path=plan_path,
        state_path=state_path,
        previous_case_id=profile["case_id"],
        previous_job_id=case_job,
    )
    _append(
        state,
        {
            "event_type": "case_submission_accepted",
            "idempotency_key": f"case:{key}",
            "case_id": profile["case_id"],
            "job_id": case_job,
            "profile": profile,
            "chosen_profile": chosen,
            "command": case_command,
            "raw_output": case_raw,
            "input_archive_sha256": plan["input_archive"]["sha256"],
        },
    )
    _write_state(state_path, state)
    selector_job, selector_raw = _sbatch(selector_command, run)
    if selector_job is None:
        _append(
            state,
            {
                "event_type": "selector_submission_ambiguous",
                "idempotency_key": f"selector:{case_job}",
                "case_id": profile["case_id"],
                "case_job_id": case_job,
                "command": selector_command,
                "raw_output": selector_raw,
                "instruction": "Do not resubmit automatically; inspect Slurm output.",
            },
        )
        _write_state(state_path, state)
        return {
            "status": "selector_submission_ambiguous",
            "case_job_id": case_job,
            "raw_output": selector_raw,
        }
    _append(
        state,
        {
            "event_type": "selector_submission_accepted",
            "idempotency_key": f"selector:{case_job}",
            "selector_job_id": selector_job,
            "case_id": profile["case_id"],
            "case_job_id": case_job,
            "dependency": f"afterany:{case_job}",
            "command": selector_command,
            "raw_output": selector_raw,
        },
    )
    _append(
        state,
        {
            "event_type": "selector_complete",
            "selector_core_seconds": _seconds_since_start(started),
            "selector_job_id": os.environ.get("SLURM_JOB_ID"),
        },
    )
    _write_state(state_path, state)
    return {
        "status": "submitted",
        "case_id": profile["case_id"],
        "case_job_id": case_job,
        "selector_job_id": selector_job,
    }


def _adopt_seeds(plan: dict[str, Any], state: dict[str, Any], run: Callable[..., Any]) -> None:
    for seed in plan["seed_cases"]:
        state_path = Path(seed["run_dir"]) / "run-state.json"
        if seed["run_state_sha256"] and (
            not state_path.is_file() or sha256_file(state_path) != seed["run_state_sha256"]
        ):
            raise QueueError(f"approved seed run-state hash mismatch: {seed['case_id']}")
        _record_completion(plan, state, seed["case_id"], seed["job_id"], run)


def run_selector(
    *,
    plan_path: Path,
    state_path: Path,
    mode: str,
    completed_case_id: str | None = None,
    completed_job_id: str | None = None,
    run: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    started = time.monotonic()
    plan, plan_sha = load_plan(plan_path)
    if state_path.is_symlink():
        raise QueueError("queue state may not be a symlink")
    state_path = state_path.resolve()
    if not state_path.is_absolute() or not state_path.is_relative_to(Path(plan["project_root"])):
        raise QueueError("queue state must be below shared project_root")
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    if lock_path.is_symlink():
        raise QueueError("queue lock may not be a symlink")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read_state(state_path, plan, plan_sha)
        if mode == "adopt-seeds":
            _adopt_seeds(plan, state, run)
            _write_state(state_path, state)
            completed_case_id = plan["seed_cases"][-1]["case_id"]
            completed_job_id = plan["seed_cases"][-1]["job_id"]
        elif mode != "after-case":
            raise QueueError("mode must be adopt-seeds or after-case")
        if not completed_case_id or not completed_job_id:
            raise QueueError("completed case ID and Slurm job ID are required")
        key = f"dispatch-after:{completed_job_id}"
        if any(event.get("idempotency_key") == key for event in state["events"]):
            return {"status": "already_dispatched", "decision_key": key}
        _record_completion(plan, state, completed_case_id, completed_job_id, run)
        _write_state(state_path, state)
        return _dispatch(
            plan,
            plan_path.resolve(),
            state_path,
            state,
            completed_case_id,
            completed_job_id,
            started,
            run,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path(os.environ["ROUAIX_QUEUE_PLAN"])
        if os.environ.get("ROUAIX_QUEUE_PLAN")
        else None,
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(os.environ["ROUAIX_QUEUE_STATE"])
        if os.environ.get("ROUAIX_QUEUE_STATE")
        else None,
    )
    parser.add_argument(
        "--mode", choices=("adopt-seeds", "after-case"), default=os.environ.get("ROUAIX_QUEUE_MODE")
    )
    parser.add_argument("--completed-case-id", default=os.environ.get("ROUAIX_COMPLETED_CASE_ID"))
    parser.add_argument("--completed-job-id", default=os.environ.get("ROUAIX_COMPLETED_JOB_ID"))
    args = parser.parse_args()
    if args.plan is None or args.state is None or args.mode is None:
        parser.error("set ROUAIX_QUEUE_PLAN, ROUAIX_QUEUE_STATE, and ROUAIX_QUEUE_MODE")
    try:
        result = run_selector(
            plan_path=args.plan,
            state_path=args.state,
            mode=args.mode,
            completed_case_id=args.completed_case_id,
            completed_job_id=args.completed_job_id,
        )
        print(json.dumps(result, sort_keys=True))
        return (
            0
            if result["status"]
            in {
                "submitted",
                "already_dispatched",
                "complete_or_stopped",
                "stopped",
                "submission_ambiguous",
                "selector_submission_ambiguous",
            }
            else 1
        )
    except (OSError, json.JSONDecodeError, QueueError, subprocess.SubprocessError) as error:
        print(f"overnight selector stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
