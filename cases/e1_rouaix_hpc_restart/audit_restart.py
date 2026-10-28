#!/usr/bin/env python3
"""Audit one native Rouaix continuation interval from its measured checkpoint."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.continue_rouaix_case import (
    RHO_WATER_KG_M3,
    _right_endpoint_step_integral,
)

PARENT_LEDGER_SHA256 = "0baa380005d188edf6c94a0c175b790a5a8af5fa79773ff37ace5da5dda2f300"
PARENT_ARCHIVE_SHA256 = "31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9"
PARENT_ENDPOINT_MEMBER = "attempt/case/processors120/0.200000000000/alpha.water"
PATCHES = (
    "gasInlet",
    "downstreamOutlet",
    "bottomOutlet",
    "aircraftWall",
    "spanwiseMinus",
    "spanwisePlus",
    "nozzle",
)
PARENT_PROCESSOR_MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
TIME_TOL_S = 1e-10
DT_TOL_S = 1e-9
INVENTORY_TOL_M3 = 1e-10
EARLY_SAVE_REASON = "diagnostic_early_save_after_3_steps"
PARENT_CONTRACT_PROFILES = {
    "pressure-total-p0-zero": {
        "case_id": "rouaix-restart-pressure-total-p0-zero-0300",
        "start_time_s": 0.2,
        "target_time_s": 0.3,
        "step_count": 1000,
    },
    "pressure-total-pcgdic": {
        "case_id": "rouaix-restart-pressure-total-pcgdic-0255",
        "start_time_s": 0.2,
        "target_time_s": 0.255,
        "step_count": 550,
    },
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value, raw


def _parent_summary(
    source: Path | str | dict[str, Any], expected_sha256: str = PARENT_LEDGER_SHA256
) -> tuple[dict[str, Any], str, str]:
    if isinstance(source, (Path, str)):
        path = Path(source)
        summary, raw = _read_json(path)
        declared_sha256 = _sha256(raw)
    elif isinstance(source, dict):
        try:
            path = Path(source["source_path"])
            declared_sha256 = str(source["source_sha256"])
        except (KeyError, TypeError) as exc:
            raise ValueError("parent ledger dict requires source_path and source_sha256") from exc
        summary, raw = _read_json(path)
        if "summary" in source and source["summary"] != summary:
            raise ValueError("provided parent summary differs from its hash-bound source file")
        if _sha256(raw) != declared_sha256:
            raise ValueError("parent ledger dict source_sha256 does not match its source file")
    else:
        raise TypeError("parent_ledger must be a Path or a hash-bound source dict")
    if declared_sha256 != expected_sha256:
        raise ValueError("parent ledger summary SHA-256 does not match its checkpoint contract")
    return summary, declared_sha256, str(path)


def _series_file(run_dir: Path, object_names: tuple[str, ...], filename: str) -> tuple[Path, str]:
    found: list[tuple[Path, str]] = []
    for object_name in object_names:
        files = sorted((run_dir / "postProcessing" / object_name).glob(f"**/{filename}"))
        found.extend((path, object_name) for path in files)
    if len(found) != 1:
        raise ValueError(f"expected exactly one {filename} for {object_names}, found {len(found)}")
    return found[0]


def _read_native_series(
    path: Path, *, required_field: str
) -> tuple[list[tuple[float, float]], str, str]:
    """Read a native function-object table and select its named output column."""
    raw = path.read_bytes()
    header: list[str] | None = None
    data: list[tuple[float, float]] = []
    field_index: int | None = None
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        try:
            line = raw_line.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise ValueError(f"non-ASCII row {line_number} in {path}") from exc
        if not line:
            continue
        if line.startswith("#"):
            candidate = line[1:].strip().split()
            if candidate and candidate[0].casefold() in {"time", "t"}:
                if header is not None:
                    raise ValueError(f"duplicate time header in {path}")
                header = candidate
                matches = [i for i, name in enumerate(header) if required_field in name]
                if len(matches) != 1:
                    raise ValueError(
                        f"expected one `{required_field}` column in {path}, found {len(matches)}"
                    )
                field_index = matches[0]
            continue
        if header is None or field_index is None:
            raise ValueError(f"missing named native time header in {path}")
        fields = line.split()
        if len(fields) != len(header):
            raise ValueError(f"incomplete native row {line_number} in {path}")
        try:
            values = [float(value) for value in fields]
        except ValueError as exc:
            raise ValueError(f"non-numeric native row {line_number} in {path}") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"non-finite native row {line_number} in {path}")
        instant = values[0]
        if data and instant <= data[-1][0]:
            raise ValueError(f"native times are not strictly increasing in {path}")
        data.append((instant, values[field_index]))
    if not data:
        raise ValueError(f"no complete native samples in {path}")
    return data, _sha256(raw), " ".join(header or [])


def _validate_parent(
    run_dir: Path,
    parent: dict[str, Any],
    parent_sha256: str,
    parent_path: str,
    start_time_s: float,
    parent_contract: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    integration = parent.get("integration", {})
    coverage = parent.get("coverage", {})
    expected_checkpoint_time_s = (
        float(parent_contract["checkpoint_time_s"]) if parent_contract is not None else 0.2
    )
    expected_archive_sha256 = (
        str(parent_contract["archive_sha256"])
        if parent_contract is not None
        else PARENT_ARCHIVE_SHA256
    )
    expected_endpoint_member = (
        f"attempt/case/processors120/{expected_checkpoint_time_s:.12f}/alpha.water"
    )
    parent_end = float(
        coverage.get(
            "actual_end_time_s" if parent_contract is not None else "last_matched_printed_time_s",
            math.nan,
        )
    )
    parent_inventory = float(integration.get("final_inventory_m3", math.nan))
    density = float(integration.get("density_kg_m3", math.nan))
    if parent_contract is not None:
        profile = PARENT_CONTRACT_PROFILES.get(str(parent_contract.get("variant", "")))
        checkpoint_fields = parent_contract.get("checkpoint_fields", {})
        processor_mesh = parent_contract.get("processor_mesh", {})
        fv_solution_sha256 = str(parent_contract.get("fv_solution_sha256", ""))
        if (
            profile is None
            or parent_contract.get("case_id") != profile["case_id"]
            or not math.isclose(
                expected_checkpoint_time_s,
                profile["target_time_s"],
                rel_tol=0.0,
                abs_tol=TIME_TOL_S,
            )
            or parent_contract.get("step_count") != profile["step_count"]
            or (
                "parent_start_time_s" in parent_contract
                and not math.isclose(
                    float(parent_contract["parent_start_time_s"]),
                    profile["start_time_s"],
                    rel_tol=0.0,
                    abs_tol=TIME_TOL_S,
                )
            )
            or (
                "parent_target_time_s" in parent_contract
                and not math.isclose(
                    float(parent_contract["parent_target_time_s"]),
                    profile["target_time_s"],
                    rel_tol=0.0,
                    abs_tol=TIME_TOL_S,
                )
            )
            or not str(parent_contract.get("parent_job_id", "")).isdigit()
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(parent_contract.get("inventory_history_sha256", ""))
            )
            or not str(parent_contract.get("inventory_history_member", "")).startswith(
                "attempt/case/postProcessing/waterInventory/"
            )
            or not math.isclose(
                float(parent_contract.get("inventory_history_time_s", math.nan)),
                expected_checkpoint_time_s,
                rel_tol=0.0,
                abs_tol=TIME_TOL_S,
            )
            or not math.isclose(
                float(parent_contract.get("inventory_history_m3", math.nan)),
                float(parent_contract.get("inventory_m3", math.nan)),
                rel_tol=0.0,
                abs_tol=INVENTORY_TOL_M3,
            )
            or not isinstance(checkpoint_fields.get("alpha.water"), dict)
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(checkpoint_fields.get("alpha.water", {}).get("sha256", ""))
            )
            or not isinstance(processor_mesh, dict)
            or any(
                not isinstance(processor_mesh.get(name), dict)
                or not re.fullmatch(
                    r"[0-9a-f]{64}", str(processor_mesh.get(name, {}).get("sha256", ""))
                )
                for name in PARENT_PROCESSOR_MESH_FILES
            )
            or (
                parent_contract.get("variant") == "pressure-total-pcgdic"
                and (
                    parent_contract.get("fv_solution_member") != "attempt/case/system/fvSolution"
                    or not re.fullmatch(r"[0-9a-f]{64}", fv_solution_sha256)
                )
            )
        ):
            raise ValueError(
                "new parent contract lacks its exact profile inventory and checkpoint bindings"
            )
    if parent_contract is None:
        if (
            coverage.get("configured_horizon_reached") is not True
            or coverage.get("requested_end_reached") is not True
        ):
            raise ValueError(
                "parent ledger does not certify complete coverage through its endpoint"
            )
    elif (
        coverage.get("status") != "requested_horizon_reached_exploratory_only"
        or coverage.get("requested_target_reached") is not True
        or parent_contract is None
        or parent.get("interval", {}).get("step_count")
        != PARENT_CONTRACT_PROFILES[parent_contract["variant"]]["step_count"]
    ):
        raise ValueError("parent ledger does not certify requested-target completion")
    if not math.isclose(parent_end, expected_checkpoint_time_s, rel_tol=0.0, abs_tol=TIME_TOL_S):
        raise ValueError("hash-bound parent ledger does not end at its checkpoint time")
    if not math.isclose(start_time_s, parent_end, rel_tol=0.0, abs_tol=TIME_TOL_S):
        raise ValueError("restart start time differs from the audited parent checkpoint")
    if not math.isfinite(parent_inventory) or parent_inventory < 0:
        raise ValueError("parent ledger has no finite non-negative final inventory")
    if density != RHO_WATER_KG_M3:
        raise ValueError("parent ledger water density differs from 997.6 kg/m3")

    receipt_path = run_dir / "parent-checkpoint-receipt.json"
    receipt, raw = _read_json(receipt_path)
    expected = {
        "archive_sha256": expected_archive_sha256,
        "checkpoint_time_s": expected_checkpoint_time_s,
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_endpoint_member": expected_endpoint_member,
    }
    if parent_contract is not None:
        expected["ledger_sha256"] = parent_contract["ledger_sha256"]
        expected["parent_job_id"] = parent_contract["parent_job_id"]
        expected["manifest_sha256"] = parent_contract["manifest_sha256"]
        expected["terminal_sha256"] = parent_contract["terminal_sha256"]
        if parent_contract["variant"] == "pressure-total-pcgdic":
            expected["fv_solution_sha256"] = fv_solution_sha256
    for key, value in expected.items():
        actual = receipt.get(key)
        if key == "checkpoint_time_s":
            if not math.isclose(float(actual), value, rel_tol=0.0, abs_tol=TIME_TOL_S):
                raise ValueError("parent checkpoint receipt time differs from its contract")
        elif actual != value:
            raise ValueError(f"parent checkpoint receipt {key} does not match verified evidence")
    receipt_inventory = float(receipt.get("inventory_m3", math.nan))
    if not math.isclose(receipt_inventory, parent_inventory, rel_tol=0.0, abs_tol=INVENTORY_TOL_M3):
        raise ValueError("parent receipt inventory differs from hash-bound parent ledger")
    if parent_contract is not None and not math.isclose(
        receipt_inventory,
        float(parent_contract["inventory_m3"]),
        rel_tol=0.0,
        abs_tol=INVENTORY_TOL_M3,
    ):
        raise ValueError("parent receipt inventory differs from the hash-bound dispatcher contract")
    receipt_binding = {
        "path": str(receipt_path),
        "sha256": _sha256(raw),
        "archive_sha256": receipt["archive_sha256"],
        "checkpoint_time_s": float(receipt["checkpoint_time_s"]),
        "inventory_m3": receipt_inventory,
        "archive_status": receipt["archive_status"],
        "selected_endpoint_member": receipt["selected_endpoint_member"],
        "ledger_sha256": receipt.get("ledger_sha256"),
        "parent_job_id": receipt.get("parent_job_id"),
    }
    parent_binding = {
        "summary_path": parent_path,
        "summary_sha256": parent_sha256,
        "checkpoint_time_s": parent_end,
        "parent_job_id": receipt.get("parent_job_id"),
        "initial_inventory_m3": parent_inventory,
        "initial_inventory_kg": parent_inventory * density,
        "density_kg_m3": density,
        "prior_injected_kg_context_only": integration.get("injected_kg"),
        "prior_escape_kg_context_only": integration.get("signed_net_escape_kg"),
        "prior_residual_kg_context_only": integration.get("closure_residual_kg"),
        "cumulative_offsets_recounted": False,
    }
    if parent_contract is not None:
        parent_binding["initial_inventory_evidence"] = {
            "source": (
                f"parent exact {expected_checkpoint_time_s:g} native "
                "volIntegrate(alpha.water) sample cross-checked with its ledger"
            ),
            "history_member": parent_contract["inventory_history_member"],
            "history_sha256": parent_contract["inventory_history_sha256"],
            "history_time_s": float(parent_contract["inventory_history_time_s"]),
            "history_inventory_m3": float(parent_contract["inventory_history_m3"]),
            "restart_checkpoint_alpha_water_sha256": checkpoint_fields["alpha.water"]["sha256"],
            "restart_checkpoint_processor_mesh_sha256": {
                name: processor_mesh[name]["sha256"] for name in PARENT_PROCESSOR_MESH_FILES
            },
        }
    return {"parent": parent_binding, "receipt": receipt_binding}, _sha256(raw)


def _validate_terminal(
    run_dir: Path, start_time_s: float, target_time_s: float, delta_t_s: float
) -> dict[str, Any]:
    path = run_dir / "terminal-status.json"
    terminal, raw = _read_json(path)
    exact = {
        "solver_end_marker": True,
        "solver_exit_code": 0,
        "pause_observed": False,
    }
    for key, expected in exact.items():
        if terminal.get(key) != expected:
            raise ValueError(f"terminal-status.json {key} is not {expected!r}")
    for key, expected in (
        ("target_time_s", target_time_s),
        ("requested_start_time_s", start_time_s),
    ):
        if key not in terminal or not math.isclose(
            float(terminal[key]), expected, rel_tol=0.0, abs_tol=TIME_TOL_S
        ):
            raise ValueError(f"terminal-status.json {key} does not match the requested interval")
    actual_time_s = float(terminal.get("solver_time_s", math.nan))
    if (
        not math.isfinite(actual_time_s)
        or actual_time_s <= start_time_s
        or actual_time_s > target_time_s + TIME_TOL_S
    ):
        raise ValueError(
            "terminal-status.json actual solver time is outside the requested interval"
        )
    steps_float = (actual_time_s - start_time_s) / delta_t_s
    actual_steps = round(steps_float)
    if actual_steps < 1 or not math.isclose(
        steps_float, actual_steps, rel_tol=0.0, abs_tol=DT_TOL_S
    ):
        raise ValueError("terminal solver time is not an exact fixed-deltaT endpoint")
    if terminal.get("solver_time_steps_recorded") != actual_steps:
        raise ValueError(
            "terminal-status.json solver_time_steps_recorded differs from actual endpoint"
        )
    target_reached = abs(actual_time_s - target_time_s) <= TIME_TOL_S
    stop_reason = terminal.get("stop_reason")
    if target_reached:
        if terminal.get("state") != "terminal" or stop_reason is not None:
            raise ValueError("target terminal endpoint has a non-natural stop reason")
    elif stop_reason == EARLY_SAVE_REASON:
        if (
            terminal.get("state") != "diagnostic_early_saved"
            or terminal.get("write_and_stop_requested") is not True
            or terminal.get("write_and_stop_acknowledged") is not True
            or not isinstance(terminal.get("stop_signals"), list)
            or "12" not in terminal.get("stop_signals", [])
            or terminal.get("early_save_trigger_after_steps") != 3
            or actual_steps not in {3, 4, 5}
            or terminal.get("stop_signal_task_count") != 120
            or not str(terminal.get("stop_signal_job_id", "")).isdigit()
            or terminal.get("stop_signal_job_step") != f"{terminal.get('stop_signal_job_id')}.0"
            or not re.fullmatch(r"\d+\.0", str(terminal.get("stop_signal_job_step", "")))
        ):
            raise ValueError("diagnostic early save lacks its acknowledged 3-step receipt")
        try:
            requested_utc = datetime.fromisoformat(
                str(terminal["stop_signal_request_utc"]).replace("Z", "+00:00")
            )
            acknowledged_utc = datetime.fromisoformat(
                str(terminal["stop_signal_acknowledged_utc"]).replace("Z", "+00:00")
            )
            request_time_s = float(terminal["stop_signal_request_solver_time_s"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "diagnostic early-save signal receipt has invalid timestamps"
            ) from error
        if (
            requested_utc.utcoffset() is None
            or acknowledged_utc.utcoffset() is None
            or requested_utc.utcoffset().total_seconds() != 0
            or acknowledged_utc.utcoffset().total_seconds() != 0
            or acknowledged_utc < requested_utc
            or not math.isclose(
                request_time_s,
                start_time_s + 3 * delta_t_s,
                rel_tol=0.0,
                abs_tol=TIME_TOL_S,
            )
        ):
            raise ValueError("diagnostic early-save request is not recorded after 3 steps")
        log_path = run_dir.parent / "solver.log"
        if log_path.is_symlink() or not log_path.is_file():
            raise ValueError("diagnostic early save lacks a regular solver log")
        raw_log = log_path.read_bytes()
        if hashlib.sha256(raw_log).hexdigest() != terminal.get("solver_log_sha256"):
            raise ValueError("diagnostic early-save solver-log hash does not match its receipt")
        log_text = raw_log.decode("utf-8", errors="replace")
        logged_times = [
            float(value)
            for value in re.findall(r"(?m)^\s*(?:\[\d+\]\s*)?Time\s*=\s*([^\s]+)\s*$", log_text)
        ]
        post_checkpoint_times = [
            value for value in logged_times if value > start_time_s + TIME_TOL_S
        ]
        expected_times = [start_time_s + index * delta_t_s for index in range(1, actual_steps + 1)]
        if (
            not re.search(r"(?m)^\s*(?:\[\d+\]\s*)?End\s*$", log_text)
            or not re.search(
                r"sigStopAtWriteNow\s*:\s*setting up write and stop at end of the next iteration",
                log_text,
            )
            or len(post_checkpoint_times) != actual_steps
            or not math.isclose(
                post_checkpoint_times[-1], actual_time_s, rel_tol=0.0, abs_tol=TIME_TOL_S
            )
            or any(
                not math.isfinite(actual)
                or not math.isclose(actual, expected, rel_tol=0.0, abs_tol=TIME_TOL_S)
                for actual, expected in zip(post_checkpoint_times, expected_times, strict=True)
            )
            or not any(
                math.isclose(value, request_time_s, rel_tol=0.0, abs_tol=TIME_TOL_S)
                for value in post_checkpoint_times
            )
        ):
            raise ValueError(
                "diagnostic early-save log does not match its actual fixed-step endpoint"
            )
    elif (
        terminal.get("state") != "guarded_partial"
        or stop_reason != "max_abs_U_exceeded_1000.0_m_s"
        or terminal.get("write_and_stop_requested") is not True
        or terminal.get("write_and_stop_acknowledged") is not True
    ):
        raise ValueError(
            "partial target requires an acknowledged U-guard or diagnostic-save receipt"
        )
    terminal["requested_target_reached"] = target_reached
    terminal["actual_step_count"] = actual_steps
    return {"path": str(path), "sha256": _sha256(raw), **terminal}


def audit_restart(
    run_dir: Path,
    parent_ledger: Path | str | dict[str, Any],
    start_time_s: float,
    end_time_s: float,
    delta_t_s: float,
    parent_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit only the continuation interval, seeded by the parent's measured inventory."""
    run_dir = Path(run_dir)
    values = (start_time_s, end_time_s, delta_t_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("restart interval values must be finite")
    start_time_s, end_time_s, delta_t_s = map(float, values)
    if start_time_s < 0 or end_time_s <= start_time_s or delta_t_s <= 0:
        raise ValueError("restart interval must have start < end and positive deltaT")
    target_steps_float = (end_time_s - start_time_s) / delta_t_s
    target_steps = round(target_steps_float)
    if target_steps < 1 or not math.isclose(
        target_steps_float, target_steps, rel_tol=0.0, abs_tol=DT_TOL_S
    ):
        raise ValueError("requested restart interval is not an integer number of fixed steps")
    if parent_contract is not None and (
        parent_contract.get("schema_version") != 1
        or not math.isclose(
            float(parent_contract.get("checkpoint_time_s", math.nan)),
            start_time_s,
            rel_tol=0.0,
            abs_tol=TIME_TOL_S,
        )
        or not re.fullmatch(r"[0-9a-f]{64}", str(parent_contract.get("ledger_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(parent_contract.get("archive_sha256", "")))
    ):
        raise ValueError(
            "new parent checkpoint contract is incomplete or does not match restart start"
        )

    expected_parent_ledger_sha = (
        str(parent_contract["ledger_sha256"])
        if parent_contract is not None
        else PARENT_LEDGER_SHA256
    )
    parent, parent_sha, parent_path = _parent_summary(parent_ledger, expected_parent_ledger_sha)
    parent_binding, _ = _validate_parent(
        run_dir, parent, parent_sha, parent_path, start_time_s, parent_contract
    )
    terminal = _validate_terminal(run_dir, start_time_s, end_time_s, delta_t_s)
    actual_end_time_s = float(terminal["solver_time_s"])
    actual_steps = int(terminal["actual_step_count"])

    inventory_path, inventory_name = _series_file(
        run_dir, ("waterInventory", "waterVolume"), "volFieldValue.dat"
    )
    inventory_rows, inventory_sha, inventory_header = _read_native_series(
        inventory_path, required_field="alpha.water"
    )
    histories: dict[str, list[tuple[float, float]]] = {"inventory": inventory_rows}
    input_hashes = {
        "water_inventory": {
            "path": str(inventory_path),
            "sha256": inventory_sha,
            "header": inventory_header,
        }
    }
    flux_headers: dict[str, str] = {}
    for patch in PATCHES:
        path, object_name = _series_file(
            run_dir,
            (f"liquidFlux_{patch}", f"{patch}Flux"),
            "surfaceFieldValue.dat",
        )
        rows, digest, header = _read_native_series(path, required_field="alphaPhi_")
        histories[patch] = rows
        flux_headers[patch] = header
        input_hashes[patch] = {
            "path": str(path),
            "sha256": digest,
            "object_name": object_name,
            "header": header,
        }

    parent_inventory_m3 = float(parent["integration"]["final_inventory_m3"])
    all_times: dict[str, list[float]] = {}
    selected: dict[str, dict[float, float]] = {}
    checkpoint_inventory_sample: float | None = None
    for name, rows in histories.items():
        if any(time_s > actual_end_time_s + TIME_TOL_S for time_s, _ in rows):
            raise ValueError(f"{name} history contains samples after the terminal endpoint")
        at_checkpoint = [
            value for instant, value in rows if abs(instant - start_time_s) <= TIME_TOL_S
        ]
        if (
            name == "inventory"
            and at_checkpoint
            and not math.isclose(
                at_checkpoint[0], parent_inventory_m3, rel_tol=0.0, abs_tol=INVENTORY_TOL_M3
            )
        ):
            raise ValueError(
                "restart inventory at checkpoint disagrees with parent measured inventory"
            )
        if name == "inventory" and at_checkpoint:
            checkpoint_inventory_sample = at_checkpoint[0]
        later = [(instant, value) for instant, value in rows if instant > start_time_s + TIME_TOL_S]
        if len(later) != actual_steps:
            raise ValueError(
                f"{name} has {len(later)} post-checkpoint rows; expected {actual_steps}"
            )
        if abs(later[-1][0] - actual_end_time_s) > TIME_TOL_S:
            raise ValueError(f"{name} lacks the exact actual terminal endpoint")
        all_times[name] = [instant for instant, _ in later]
        selected[name] = dict(later)

    canonical_times = all_times["inventory"]
    for name, times in all_times.items():
        if len(times) != len(canonical_times) or any(
            abs(a - b) > TIME_TOL_S for a, b in zip(times, canonical_times, strict=True)
        ):
            raise ValueError(f"time mismatch between inventory and {name} samples")
        values_after_start = [
            value for instant, value in histories[name] if instant > start_time_s + TIME_TOL_S
        ]
        selected[name] = dict(zip(canonical_times, values_after_start, strict=True))
    if parent_contract is not None:
        evidence = parent_binding["parent"]["initial_inventory_evidence"]
        evidence["child_start_inventory_sample_m3"] = checkpoint_inventory_sample
        evidence["child_start_inventory_sample_status"] = (
            "present_and_matches_parent_contract"
            if checkpoint_inventory_sample is not None
            else "absent; M0 inferred from the exact parent native history and identical hash-bound checkpoint alpha.water and mesh"
        )
    intervals = [canonical_times[0] - start_time_s]
    intervals.extend(b - a for a, b in zip(canonical_times[:-1], canonical_times[1:], strict=True))
    if any(abs(interval - delta_t_s) > DT_TOL_S for interval in intervals):
        raise ValueError("post-checkpoint native samples do not align with fixed deltaT")

    # Use the same right-endpoint convention as existing continuation audits.
    import numpy as np

    per_patch_integrals = {
        patch: _right_endpoint_step_integral(
            start_time_s,
            np.asarray(canonical_times, dtype=np.float64),
            np.asarray([selected[patch][instant] for instant in canonical_times], dtype=np.float64),
            delta_t_s,
        )
        for patch in PATCHES
    }
    total_flux = [sum(selected[patch][instant] for patch in PATCHES) for instant in canonical_times]
    total_boundary_integral = _right_endpoint_step_integral(
        start_time_s,
        np.asarray(canonical_times, dtype=np.float64),
        np.asarray(total_flux, dtype=np.float64),
        delta_t_s,
    )
    density = RHO_WATER_KG_M3
    prior_inventory_m3 = parent_inventory_m3
    ledger_rows: list[dict[str, Any]] = []
    residuals_kg: list[float] = []
    cumulative_residual_kg = 0.0
    for index, instant in enumerate(canonical_times, start=1):
        inventory_m3 = selected["inventory"][instant]
        delta_inventory_m3 = inventory_m3 - prior_inventory_m3
        fluxes = {patch: selected[patch][instant] for patch in PATCHES}
        boundary_step_m3 = sum(fluxes.values()) * delta_t_s
        residual_m3 = delta_inventory_m3 + boundary_step_m3
        residual_kg = residual_m3 * density
        cumulative_residual_kg += residual_kg
        row: dict[str, Any] = {
            "step_index": index,
            "interval_start_s": f"{instant - delta_t_s:.12g}",
            "time_s": f"{instant:.12g}",
            "delta_t_s": f"{delta_t_s:.12g}",
            "water_inventory_m3": f"{inventory_m3:.12g}",
            "water_inventory_kg": f"{inventory_m3 * density:.12g}",
            "delta_inventory_m3": f"{delta_inventory_m3:.12g}",
            "delta_inventory_kg": f"{delta_inventory_m3 * density:.12g}",
        }
        row.update({f"alphaPhi_{patch}_outward_m3_s": f"{fluxes[patch]:.12g}" for patch in PATCHES})
        row.update(
            {
                f"alphaPhi_{patch}_integral_m3": f"{fluxes[patch] * delta_t_s:.12g}"
                for patch in PATCHES
            }
        )
        row.update(
            {
                "alphaPhi_all_boundaries_outward_m3_s": f"{sum(fluxes.values()):.12g}",
                "alphaPhi_all_boundaries_integral_m3": f"{boundary_step_m3:.12g}",
                "nozzle_inflow_volume_m3": f"{-fluxes['nozzle'] * delta_t_s:.12g}",
                "external_patch_outflow_volume_m3": f"{sum(fluxes[p] for p in PATCHES if p != 'nozzle') * delta_t_s:.12g}",
                "balance_residual_m3": f"{residual_m3:.12g}",
                "balance_residual_kg": f"{residual_kg:.12g}",
                "balance_residual_cumulative_kg": f"{cumulative_residual_kg:.12g}",
            }
        )
        ledger_rows.append(row)
        residuals_kg.append(residual_kg)
        prior_inventory_m3 = inventory_m3

    final_inventory_m3 = selected["inventory"][canonical_times[-1]]
    incremental_source_m3 = -per_patch_integrals["nozzle"]
    incremental_external_outflow_m3 = sum(
        per_patch_integrals[patch] for patch in PATCHES if patch != "nozzle"
    )
    incremental_residual_kg = (
        final_inventory_m3 - parent_inventory_m3 + total_boundary_integral
    ) * density
    injected_kg = incremental_source_m3 * density
    signed_net_escape_kg = incremental_external_outflow_m3 * density
    coverage_status = (
        "requested_horizon_reached_exploratory_only"
        if terminal["requested_target_reached"]
        else (
            "diagnostic_early_save_partial_exploratory_only"
            if terminal["state"] == "diagnostic_early_saved"
            else "u_guard_partial_exploratory_only"
        )
    )
    audit = {
        "schema_version": 1,
        "scope": "Exploratory incremental restart interval balance only; not a validation or conservation gate.",
        "formal_validation_gate": None,
        "run_dir": str(run_dir),
        "interval": {
            "start_time_s": start_time_s,
            "requested_target_time_s": end_time_s,
            "actual_terminal_time_s": actual_end_time_s,
            "delta_t_s": delta_t_s,
            "step_count": actual_steps,
            "actual_terminal_endpoint_present": True,
            "solver_end_exit_and_no_pause_verified": True,
            "requested_target_reached": bool(terminal["requested_target_reached"]),
            "partial_u_guard_stop": terminal["state"] == "guarded_partial",
            "diagnostic_early_save_stop": terminal["state"] == "diagnostic_early_saved",
        },
        "parent_checkpoint": parent_binding["parent"],
        "parent_checkpoint_receipt": parent_binding["receipt"],
        "terminal_status_receipt": terminal,
        "coverage": {
            "status": coverage_status,
            "requested_target_reached": bool(terminal["requested_target_reached"]),
            "requested_end_time_s": end_time_s,
            "actual_end_time_s": actual_end_time_s,
            "coverage_fraction_of_requested_interval": (actual_end_time_s - start_time_s)
            / (end_time_s - start_time_s),
            "interpretation": "A U-guard or diagnostic early-save stop is retained as its actual partial interval and is not labeled target completion.",
        },
        "integration": {
            "scope": f"New restart interval only: start from the hash-bound measured parent {start_time_s:g} s inventory; no parent cumulative source or escape is re-added.",
            "method": "Right endpoint: each completed-step alphaPhi_ sample multiplied by the preceding fixed deltaT.",
            "density_kg_m3": density,
            "initial_inventory_kg": parent_binding["parent"]["initial_inventory_kg"],
            "initial_inventory_m3": parent_inventory_m3,
            "injected_kg": injected_kg,
            "final_inventory_m3": final_inventory_m3,
            "signed_net_escape_kg": signed_net_escape_kg,
            "max_abs_per_step_closure_residual_kg": max(map(abs, residuals_kg)),
            "max_abs_cumulative_closure_residual_kg": max(
                abs(float(row["balance_residual_cumulative_kg"])) for row in ledger_rows
            ),
            "closure_residual_kg": incremental_residual_kg,
            "known_closure_caveat": parent["integration"].get(
                "known_closure_caveat",
                "Native alpha snap/bounding may contribute to the water-inventory residual after conservative alphaPhi_ fluxes are recorded.",
            ),
        },
        "formal_validation_decision": None,
        "density_kg_m3": density,
        "flux_orientation": "Native alphaPhi_ on all seven patches is outward-positive; inward nozzle flow is negative.",
        "integration_method": "Right endpoint: each completed-step alphaPhi_ sample multiplied by the preceding fixed deltaT.",
        "incremental_only": {
            "source_inflow_volume_m3": incremental_source_m3,
            "external_patch_outflow_volume_m3": incremental_external_outflow_m3,
            "all_boundary_outward_integral_m3": total_boundary_integral,
            "stored_inventory_change_m3": final_inventory_m3 - parent_inventory_m3,
            "stored_inventory_change_kg": (final_inventory_m3 - parent_inventory_m3) * density,
            "final_inventory_m3": final_inventory_m3,
            "final_inventory_kg": final_inventory_m3 * density,
            "signed_balance_residual_m3": incremental_residual_kg / density,
            "signed_balance_residual_kg": incremental_residual_kg,
            "max_abs_per_step_residual_kg": max(map(abs, residuals_kg)),
            "sum_of_per_step_residuals_kg": sum(residuals_kg),
            "per_patch_outward_integrals_m3": per_patch_integrals,
            "parent cumulative source/escape were not added to this interval balance": True,
        },
        "input_sources": {
            "parent_ledger": {
                "path": parent_binding["parent"]["summary_path"],
                "sha256": parent_binding["parent"]["summary_sha256"],
            },
            "parent_checkpoint_receipt": {
                "path": parent_binding["receipt"]["path"],
                "sha256": parent_binding["receipt"]["sha256"],
            },
            "terminal_status_receipt": {"path": terminal["path"], "sha256": terminal["sha256"]},
            "native_histories": input_hashes,
            "audit_helper_sha256": _sha256(Path(__file__).read_bytes()),
        },
        "native_snap_and_bounding_caveat": parent["integration"].get(
            "known_closure_caveat",
            "alphaPhi_ is the conservative flux-limited sweep; later native alpha snapping or clipping can appear in the inventory residual.",
        ),
        "interpretation_limit": "Raw numerical residuals are reported without a pass threshold; this audit does not validate physical fidelity or establish a conservation gate.",
        "output_files": ["restart-ledger.csv", "restart-audit.json"],
    }

    csv_path = run_dir / "restart-ledger.csv"
    json_path = run_dir / "restart-audit.json"
    csv_tmp = csv_path.with_name(f".{csv_path.name}.tmp")
    json_tmp = json_path.with_name(f".{json_path.name}.tmp")
    with csv_tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ledger_rows[0]))
        writer.writeheader()
        writer.writerows(ledger_rows)
    json_tmp.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_tmp.replace(csv_path)
    json_tmp.replace(json_path)
    return audit
