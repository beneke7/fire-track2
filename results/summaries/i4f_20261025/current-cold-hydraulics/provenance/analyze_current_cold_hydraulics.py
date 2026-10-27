#!/usr/bin/env python3
"""Freeze and compare compact native hydraulics rows from the cold Pno prefix."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / "results/runs/i4f-current-cold-hydraulics-20261026T2126Z"
PUBLIC = ROOT / "results/summaries/i4f_20261025/current-cold-hydraulics"
CURRENT_RUN = ROOT / "results/runs/i4f-cold-momentum-predictor-off-continuation-20261026T2048Z"
PRIOR_RUN = ROOT / "results/runs/i4f-flush-stock-cold-stage01-20261026T064444Z"
PUBLISHED_SUMMARY = ROOT / "results/summaries/i4f_20261025/flush-early-cfd-model-comparison.json"
MODEL_COMPARE = ROOT / "results/runs/i4f-flush-early-model-cfd-20261026T081148Z/inputs-snapshot/model/comparison.json"
MODEL_ROOT = ROOT / "results/runs/i4f-flush-filling-model-corrected299214"
INIT_READY = ROOT / "results/runs/i4f-physical-water-eos-cold-input-20261026T1104Z/analysis/physical-water-eos-cold-input-readiness.json"
TARGETS = (
    ("0.100021166664", 0.100021166664),
    ("0.150021166664", 0.150021166664),
    ("0.200021166664", 0.200021166664),
    ("0.250021166664", 0.250021166664),
    ("0.300021166664", 0.300021166664),
)
NATIVE_SOURCES = {
    "tankA": ("tankAWaterVolume", "volFieldValue.dat", 1),
    "tankB": ("tankBWaterVolume", "volFieldValue.dat", 1),
    "flux_A1": ("seatFluxA1", "surfaceFieldValue.dat", 2),
    "flux_A2": ("seatFluxA2", "surfaceFieldValue.dat", 2),
    "flux_B1": ("seatFluxB1", "surfaceFieldValue.dat", 2),
    "flux_B2": ("seatFluxB2", "surfaceFieldValue.dat", 2),
    "probe_p": ("i4fTankHeadspaceProbes", "p", None),
    "probe_T": ("i4fTankHeadspaceProbes", "T", None),
}
PRECISE_TIME_SERIES = ("tankA", "tankB", "flux_A1", "flux_A2", "flux_B1", "flux_B2")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_read(path: Path, attempts: int = 5) -> tuple[bytes, dict[str, Any]]:
    """Read an append-only function file only when its stat tuple is stable."""
    for attempt in range(1, attempts + 1):
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        before_sig = (before.st_size, before.st_mtime_ns, before.st_ino)
        after_sig = (after.st_size, after.st_mtime_ns, after.st_ino)
        if before_sig == after_sig and len(data) == after.st_size:
            return data, {
                "bytes": len(data),
                "mtime_ns": after.st_mtime_ns,
                "sha256": sha_bytes(data),
                "stable_read_attempt": attempt,
            }
    raise RuntimeError(f"source kept changing while snapshotted: {path}")


def snapshot_file(src: Path, dst: Path, registry: dict[str, Any], label: str) -> None:
    data, record = stable_read(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    copied_sha = sha_file(dst)
    if copied_sha != record["sha256"]:
        raise RuntimeError(f"snapshot hash mismatch: {src}")
    record.update({
        "source_path": str(src.relative_to(ROOT)),
        "snapshot_path": str(dst.relative_to(ROOT)),
        "label": label,
    })
    registry[label] = record


def find_one(root: Path, object_name: str, filename: str) -> Path:
    matches = sorted((root / object_name).glob(f"*/{filename}"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one {object_name}/{filename}; found {len(matches)}")
    return matches[0]


def capture() -> None:
    manifest_path = BUNDLE / "inputs/capture-manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite frozen capture: {manifest_path}")
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    registry: dict[str, Any] = {}

    for tag, run, time_folder in (
        ("current", CURRENT_RUN, "postProcessing"),
        ("prior", PRIOR_RUN, "postProcessing"),
    ):
        case_post = run / "case/postProcessing"
        for key, (object_name, filename, _column) in NATIVE_SOURCES.items():
            src = find_one(case_post, object_name, filename)
            dst = BUNDLE / f"inputs/{tag}-cfd/{key}.dat"
            snapshot_file(src, dst, registry, f"{tag}.{key}")

    metadata_files = {
        "current.launch_manifest": CURRENT_RUN / "launch-manifest.json",
        "current.experiment": CURRENT_RUN / "experiment.json",
        "current.guardian_status": CURRENT_RUN / "guardian-status.json",
        "current.input_freeze": CURRENT_RUN / "input-freeze.json",
        "current.continuation_seed": CURRENT_RUN / "continuation-seed.json",
        "current.source_tree_manifest": CURRENT_RUN / "provenance/source-tree-sha256.json",
        "current.continuation_lineage": CURRENT_RUN / "provenance/continuation-lineage.json",
        "current.parent_input_freeze": CURRENT_RUN / "provenance/parent-input-freeze.json",
        "current.reused_binary_build_reference": CURRENT_RUN / "provenance/reused-binary-build-reference.json",
        "current.control_dict": CURRENT_RUN / "case/system/controlDict",
        "current.ledger_objects": CURRENT_RUN / "case/system/twoTankLedgerObjects",
        "current.seat_flux_objects": CURRENT_RUN / "case/system/valveBandFluxObjects",
        "prior.launch_manifest": PRIOR_RUN / "launch-manifest.json",
        "prior.experiment": PRIOR_RUN / "experiment.json",
        "prior.guardian_status": PRIOR_RUN / "guardian-status.json",
        "prior.input_freeze": PRIOR_RUN / "input-freeze.json",
        "prior.source_lock": PRIOR_RUN / "provenance/run-source-lock.json",
        "prior.control_dict": PRIOR_RUN / "case/system/controlDict",
        "prior.ledger_objects": PRIOR_RUN / "case/system/twoTankLedgerObjects",
        "prior.seat_flux_objects": PRIOR_RUN / "case/system/valveBandFluxObjects",
        "model_comparison": MODEL_COMPARE,
        "published_summary": PUBLISHED_SUMMARY,
        "native_initial_readiness": INIT_READY,
    }
    for label, src in metadata_files.items():
        if not src.is_file():
            raise FileNotFoundError(src)
        dst = BUNDLE / "inputs/provenance" / f"{label.replace('.', '-')}{src.suffix or '.txt'}"
        snapshot_file(src, dst, registry, label)

    # The ODE histories are sizeable and already immutable run outputs. Hash them
    # in place and retain only exact interpolation brackets in the analysis JSON.
    model_comparison = json.loads(MODEL_COMPARE.read_text())
    model_history_paths: dict[str, Path] = {}
    model_history_records: dict[str, dict[str, Any]] = {}
    for arm, source_key in (("n_gamma", "gamma_dt50us"), ("n1_isothermal", "isothermal_dt50us")):
        item = model_comparison["generated_from_runs"][source_key]
        hist = ROOT / item["summary_files"]["history.csv"]["path"]
        expected_sha = item["summary_files"]["history.csv"]["sha256"]
        actual_sha = sha_file(hist)
        if actual_sha != expected_sha:
            raise RuntimeError(f"ODE history changed from published hash: {hist}")
        model_history_paths[arm] = hist
        model_history_records[arm] = {
            "path": str(hist.relative_to(ROOT)),
            "sha256": actual_sha,
            "bytes": hist.stat().st_size,
            "source_summary_run": item["path"],
            "polytropic_n": item["polytropic_n"],
            "time_step_s": item["time_step_s"],
        }

    launch = json.loads((CURRENT_RUN / "launch-manifest.json").read_text())
    container_id = launch["container_id"]
    inspected_raw = subprocess.run(
        ["docker", "inspect", container_id], check=True, capture_output=True, text=True
    ).stdout
    inspected = json.loads(inspected_raw)[0]
    if inspected["Id"] != container_id:
        raise RuntimeError("Docker inspect ID differs from launch manifest")
    started_at = inspected["State"]["StartedAt"]
    if started_at != launch["docker_started_at"]:
        raise RuntimeError("Docker StartedAt differs from launch manifest")
    docker_record = {
        "id": inspected["Id"],
        "name": inspected["Name"].lstrip("/"),
        "started_at": started_at,
        "running": inspected["State"]["Running"],
        "status": inspected["State"]["Status"],
        "nano_cpus": inspected["HostConfig"]["NanoCpus"],
        "memory_bytes": inspected["HostConfig"]["Memory"],
        "log_driver": inspected["HostConfig"].get("LogConfig", {}).get("Type"),
        "inspect_sha256": sha_bytes(inspected_raw.encode()),
    }
    # Capture the actual captured runtime record, not a generic terminal claim.
    current_guard = json.loads((CURRENT_RUN / "guardian-status.json").read_text())
    branch = current_guard["branches"]["fourmouth_coldstart"]
    if branch["container_id"] != container_id:
        raise RuntimeError("guardian container identity differs from launch manifest")

    current_full_precision_times: dict[str, float] = {}
    current_row_counts: dict[str, int] = {}
    for key in PRECISE_TIME_SERIES:
        rows = numeric_rows(BUNDLE / f"inputs/current-cfd/{key}.dat")
        if not rows:
            raise RuntimeError(f"no native rows for current {key}")
        current_full_precision_times[key] = rows[-1][0]
        current_row_counts[key] = len(rows)
    current_cutoff = min(current_full_precision_times.values())
    max_time_spread = max(current_full_precision_times.values()) - current_cutoff
    if max_time_spread > 1e-11:
        raise RuntimeError(f"native current scalar files are not at a common latest time: {max_time_spread}")
    for key in ("probe_p", "probe_T"):
        rows = numeric_rows(BUNDLE / f"inputs/current-cfd/{key}.dat")
        if len(rows) != min(current_row_counts.values()) or abs(rows[-1][0] - current_cutoff) > 5.1e-9:
            raise RuntimeError(f"probe series is not aligned to current full-precision prefix: {key}")

    finished = dt.datetime.now(dt.timezone.utc).isoformat()
    status = subprocess.run(["git", "status", "--porcelain=v1"], check=True, capture_output=True, text=True).stdout
    revision = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    doctor = ROOT / "results/machine.json"
    manifest = {
        "schema": "i4f-current-cold-hydraulics-prefix-capture/v1",
        "capture_started_utc": started,
        "capture_finished_utc": finished,
        "prefix_only": True,
        "current_solver_prefix_cutoff_s": current_cutoff,
        "current_solver_prefix_cutoff_definition": "Minimum last exact-time row across captured tank-A/tank-B VOF-volume and four valve-seat alphaPhi0.water native function files. Probe p/T files print time rounded to 8 decimals; row count and rounded final time were checked against the same full-precision step.",
        "current_solver_latest_full_precision_times_s": current_full_precision_times,
        "current_solver_max_latest_time_spread_s": max_time_spread,
        "current_solver_native_row_counts": current_row_counts,
        "current_guard_branch_status_at_capture": branch["status"],
        "current_guard_time_s_at_capture": branch.get("current_time_s"),
        "current_guard_updated_utc_at_capture": current_guard.get("updated_utc"),
        "current_container": docker_record,
        "previous_cfd_case": {
            "bundle": str(PRIOR_RUN.relative_to(ROOT)),
            "container_id": json.loads((PRIOR_RUN / "launch-manifest.json").read_text())["container_id"],
            "docker_started_at": json.loads((PRIOR_RUN / "launch-manifest.json").read_text())["docker_started_at"],
            "binary_sha256": json.loads((PRIOR_RUN / "launch-manifest.json").read_text())["binary_sha256"],
        },
        "model_history_sources": model_history_records,
        "repository": {
            "revision": revision,
            "dirty": bool(status.strip()),
            "porcelain_sha256": sha_bytes(status.encode()),
            "porcelain_status_at_capture": status.splitlines(),
        },
        "doctor": {
            "path": str(doctor.relative_to(ROOT)),
            "sha256": sha_file(doctor),
        },
        "files": registry,
        "capture_command": ".venv/bin/python scripts/run_local.py --threads 1 --timeout 300 -- nice -n 19 .venv/bin/python results/runs/i4f-current-cold-hydraulics-20261026T2126Z/scripts/analyze_current_cold_hydraulics.py --capture",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"capture_manifest": str(manifest_path.relative_to(ROOT)), "cutoff_s": current_cutoff, "captured_files": len(registry), "container": docker_record}, indent=2))


def capture_source_dictionaries() -> None:
    """Freeze the tiny dictionaries defining the PIMPLE mode and probes."""
    out = BUNDLE / "inputs/provenance/measurement-source-dictionaries.json"
    if out.exists():
        raise FileExistsError(out)
    records: dict[str, Any] = {}
    for tag, run in (("current", CURRENT_RUN), ("prior", PRIOR_RUN)):
        for label, rel in (
            (f"{tag}.fv_solution", "case/system/fvSolution"),
            (f"{tag}.numerical_health_objects", "case/system/i4fNumericalHealthObjects"),
        ):
            src = run / rel
            dst = BUNDLE / "inputs/provenance" / f"{tag}-{Path(rel).name}.txt"
            snapshot_file(src, dst, records, label)
    out.write_text(json.dumps({
        "schema": "i4f-hydraulics-measurement-source-dictionaries/v1",
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": records,
        "purpose": "Hash-frozen source for momentumPredictor setting and headspace-probe fields/locations.",
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"measurement_source_dictionaries": str(out.relative_to(ROOT)), "files": len(records)}, indent=2))


def numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            rows.append([float(value) for value in stripped.split()])
        except ValueError:
            continue
    return rows


def momentum_predictor_enabled(path: Path) -> bool | None:
    import re

    match = re.search(r"\bmomentumPredictor\s+(yes|no)\s*;", path.read_text())
    return None if match is None else match.group(1) == "yes"


def dict_rows(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as stream:
        return [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]


def interpolate(rows: list[list[float]], target: float, column: int, label: str) -> tuple[float, dict[str, Any]]:
    valid = sorted((row for row in rows if len(row) > column), key=lambda row: row[0])
    if not valid:
        raise ValueError(f"{label}: no bracketed data for target {target}")
    if target < valid[0][0] and valid[0][0] - target <= 5.1e-9:
        row = valid[0]
        return row[column], {
            "method": "nearest_probe_sample_within_8_digit_print_rounding",
            "lower_time_s": row[0],
            "upper_time_s": row[0],
            "printed_time_offset_s": row[0] - target,
        }
    if target > valid[-1][0] and target - valid[-1][0] <= 5.1e-9:
        row = valid[-1]
        return row[column], {
            "method": "nearest_probe_sample_within_8_digit_print_rounding",
            "lower_time_s": row[0],
            "upper_time_s": row[0],
            "printed_time_offset_s": row[0] - target,
        }
    if target < valid[0][0] - 1e-12 or target > valid[-1][0] + 1e-12:
        raise ValueError(f"{label}: no bracketed data for target {target}")
    exact = [row for row in valid if math.isclose(row[0], target, rel_tol=0, abs_tol=1e-12)]
    if exact:
        row = exact[0]
        return row[column], {"method": "exact_native_row", "lower_time_s": row[0], "upper_time_s": row[0]}
    low = max((row for row in valid if row[0] < target), key=lambda row: row[0])
    high = min((row for row in valid if row[0] > target), key=lambda row: row[0])
    f = (target - low[0]) / (high[0] - low[0])
    value = low[column] + f * (high[column] - low[column])
    return value, {
        "method": "linear_interpolation_bracketed_no_extrapolation",
        "lower_time_s": low[0],
        "upper_time_s": high[0],
        "largest_offset_s": max(target - low[0], high[0] - target),
    }


def interpolate_dict(rows: list[dict[str, float]], target: float) -> tuple[dict[str, float], dict[str, Any]]:
    valid = sorted(rows, key=lambda row: row["time_s"])
    if target < valid[0]["time_s"] - 1e-12 or target > valid[-1]["time_s"] + 1e-12:
        raise ValueError(f"model history does not bracket {target}")
    exact = [row for row in valid if math.isclose(row["time_s"], target, rel_tol=0, abs_tol=1e-12)]
    if exact:
        return exact[0], {"method": "exact_model_history_row", "lower_time_s": target, "upper_time_s": target}
    low = max((row for row in valid if row["time_s"] < target), key=lambda row: row["time_s"])
    high = min((row for row in valid if row["time_s"] > target), key=lambda row: row["time_s"])
    f = (target - low["time_s"]) / (high["time_s"] - low["time_s"])
    result: dict[str, float] = {"time_s": target}
    for key in low:
        if key == "time_s":
            continue
        a, b = low[key], high[key]
        result[key] = a + f * (b - a) if math.isfinite(a) and math.isfinite(b) else a
    return result, {
        "method": "linear_interpolation_bracketed_no_extrapolation",
        "lower_time_s": low["time_s"],
        "upper_time_s": high["time_s"],
        "largest_offset_s": max(target - low["time_s"], high["time_s"] - target),
    }


def read_series(tag: str) -> dict[str, list[list[float]]]:
    return {key: numeric_rows(BUNDLE / f"inputs/{tag}-cfd/{key}.dat") for key in NATIVE_SOURCES}


def sample_native(series: dict[str, list[list[float]]], target: float, label: str) -> dict[str, Any]:
    sampled: dict[str, Any] = {}
    for key in ("tankA", "tankB"):
        sampled[key], sampled[f"{key}_bracket"] = interpolate(series[key], target, 1, f"{label} {key}")
    for key in ("flux_A1", "flux_A2", "flux_B1", "flux_B2"):
        sampled[key], sampled[f"{key}_bracket"] = interpolate(series[key], target, 2, f"{label} {key}")
    for key in ("probe_p", "probe_T"):
        for probe, column in (("A", 1), ("B", 2)):
            sampled[f"{key}_{probe}"], sampled[f"{key}_{probe}_bracket"] = interpolate(series[key], target, column, f"{label} {key}_{probe}")
    sampled["QA_m3_s"] = sampled["flux_A1"] + sampled["flux_A2"]
    sampled["QB_m3_s"] = sampled["flux_B1"] + sampled["flux_B2"]
    sampled["mean_tank_Q_m3_s"] = 0.5 * (sampled["QA_m3_s"] + sampled["QB_m3_s"])
    sampled["mean_probe_p_abs_Pa"] = 0.5 * (sampled["probe_p_A"] + sampled["probe_p_B"])
    sampled["mean_probe_T_K"] = 0.5 * (sampled["probe_T_A"] + sampled["probe_T_B"])
    return sampled


def collect_target_rows(current: dict[str, list[list[float]]], prior: dict[str, list[list[float]]], manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_cutoff = manifest["current_solver_prefix_cutoff_s"]
    readiness = json.loads((BUNDLE / "inputs/provenance/native_initial_readiness.json").read_text())
    init = readiness["initial_state"]["zone_inventories"]
    initA = init["tankAZone"]["native_water_volume_m3"]
    initB = init["tankBZone"]["native_water_volume_m3"]
    modelmeta = json.loads((BUNDLE / "inputs/provenance/model_comparison.json").read_text())
    gamma_item = modelmeta["generated_from_runs"]["gamma_dt50us"]
    iso_item = modelmeta["generated_from_runs"]["isothermal_dt50us"]
    gamma_hist = dict_rows(ROOT / gamma_item["summary_files"]["history.csv"]["path"])
    iso_hist = dict_rows(ROOT / iso_item["summary_files"]["history.csv"]["path"])
    model_initial = gamma_hist[0]["tank_water_volume_m3"]
    rows: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for target_label, target in TARGETS:
        if target > current_cutoff + 1e-12:
            unavailable.append({"requested_time_s": target, "label": target_label, "reason": "beyond frozen current native-row prefix cutoff"})
            continue
        c = sample_native(current, target, "current")
        o = sample_native(prior, target, "prior standard-source CFD")
        g, g_bracket = interpolate_dict(gamma_hist, target)
        i, i_bracket = interpolate_dict(iso_hist, target)
        cwithdraw = 0.5 * ((initA - c["tankA"]) + (initB - c["tankB"])) * 1000.0
        owithdraw = 0.5 * ((initA - o["tankA"]) + (initB - o["tankB"])) * 1000.0
        gwithdraw = (model_initial - g["tank_water_volume_m3"]) * 1000.0
        iwithdraw = (model_initial - i["tank_water_volume_m3"]) * 1000.0
        row = {
            "time_s": target,
            "target_label": target_label,
            "current_tankA_alpha_volume_m3": c["tankA"],
            "current_tankB_alpha_volume_m3": c["tankB"],
            "current_mean_tank_withdrawal_from_native_initial_L": cwithdraw,
            "current_tankA_seat_flux_Q_m3_s": c["QA_m3_s"],
            "current_tankB_seat_flux_Q_m3_s": c["QB_m3_s"],
            "current_mean_tank_seat_flux_Q_m3_s": c["mean_tank_Q_m3_s"],
            "current_tankA_local_probe_p_abs_Pa": c["probe_p_A"],
            "current_tankB_local_probe_p_abs_Pa": c["probe_p_B"],
            "current_mean_local_probe_p_abs_Pa": c["mean_probe_p_abs_Pa"],
            "current_tankA_local_probe_T_K": c["probe_T_A"],
            "current_tankB_local_probe_T_K": c["probe_T_B"],
            "current_mean_local_probe_T_K": c["mean_probe_T_K"],
            "prior_tankA_alpha_volume_m3": o["tankA"],
            "prior_tankB_alpha_volume_m3": o["tankB"],
            "prior_mean_tank_withdrawal_from_native_initial_L": owithdraw,
            "prior_tankA_seat_flux_Q_m3_s": o["QA_m3_s"],
            "prior_tankB_seat_flux_Q_m3_s": o["QB_m3_s"],
            "prior_mean_tank_seat_flux_Q_m3_s": o["mean_tank_Q_m3_s"],
            "prior_tankA_local_probe_p_abs_Pa": o["probe_p_A"],
            "prior_tankB_local_probe_p_abs_Pa": o["probe_p_B"],
            "prior_mean_local_probe_p_abs_Pa": o["mean_probe_p_abs_Pa"],
            "prior_tankA_local_probe_T_K": o["probe_T_A"],
            "prior_tankB_local_probe_T_K": o["probe_T_B"],
            "prior_mean_local_probe_T_K": o["mean_probe_T_K"],
            "ode_ngamma_tank_water_volume_m3": g["tank_water_volume_m3"],
            "ode_ngamma_withdrawal_L": gwithdraw,
            "ode_ngamma_bulk_gas_pressure_abs_Pa": g["gas_pressure_abs_Pa"],
            "ode_ngamma_bulk_gas_T_K": g["gas_temperature_K"],
            "ode_ngamma_total_branch_Q_m3_s": g["total_branch_flow_m3_s"],
            "ode_n1_tank_water_volume_m3": i["tank_water_volume_m3"],
            "ode_n1_withdrawal_L": iwithdraw,
            "ode_n1_bulk_gas_pressure_abs_Pa": i["gas_pressure_abs_Pa"],
            "ode_n1_bulk_gas_T_K": i["gas_temperature_K"],
            "ode_n1_total_branch_Q_m3_s": i["total_branch_flow_m3_s"],
            "current_minus_prior_mean_withdrawal_L": cwithdraw - owithdraw,
            "current_minus_prior_mean_Q_m3_s": c["mean_tank_Q_m3_s"] - o["mean_tank_Q_m3_s"],
            "current_minus_ngamma_withdrawal_L": cwithdraw - gwithdraw,
            "current_minus_ngamma_Q_m3_s": c["mean_tank_Q_m3_s"] - g["total_branch_flow_m3_s"],
            "current_vs_ngamma_Q_percent": 100.0 * (c["mean_tank_Q_m3_s"] - g["total_branch_flow_m3_s"]) / g["total_branch_flow_m3_s"] if g["total_branch_flow_m3_s"] else math.nan,
            "current_minus_ngamma_probe_vs_bulk_pressure_Pa": c["mean_probe_p_abs_Pa"] - g["gas_pressure_abs_Pa"],
            "current_vs_ngamma_probe_vs_bulk_pressure_percent": 100.0 * (c["mean_probe_p_abs_Pa"] - g["gas_pressure_abs_Pa"]) / g["gas_pressure_abs_Pa"],
            "current_minus_ngamma_probe_vs_bulk_gas_T_K": c["mean_probe_T_K"] - g["gas_temperature_K"],
            "current_vs_prior_Q_percent": 100.0 * (c["mean_tank_Q_m3_s"] - o["mean_tank_Q_m3_s"]) / o["mean_tank_Q_m3_s"] if o["mean_tank_Q_m3_s"] else math.nan,
            "native_sampling": {"current": c, "prior": o, "ode_ngamma": g_bracket, "ode_n1": i_bracket},
            "ode_values": {"ngamma": g, "n1": i},
        }
        rows.append(row)
    return rows, unavailable


def derive_prefix_rows(series: dict[str, list[list[float]]], cutoff: float, initialA: float, initialB: float) -> list[dict[str, float]]:
    indexes: dict[str, list[list[float]]] = {}
    for key, data in series.items():
        printed_time_tolerance = 5.1e-9 if key in {"probe_p", "probe_T"} else 1e-12
        indexes[key] = [row for row in data if row[0] <= cutoff + printed_time_tolerance]
    times = [row[0] for row in indexes["tankA"]]
    output = []
    for idx, time_s in enumerate(times):
        if idx >= len(indexes["tankB"]) or abs(indexes["tankB"][idx][0] - time_s) > 1e-12:
            raise RuntimeError("tank water times are not row-aligned")
        fluxes = {}
        for key in ("flux_A1", "flux_A2", "flux_B1", "flux_B2"):
            if idx >= len(indexes[key]) or abs(indexes[key][idx][0] - time_s) > 1e-12:
                raise RuntimeError(f"seat flux not row-aligned with tank volumes: {key}")
            fluxes[key] = indexes[key][idx][2]
        probe_p_A, _ = interpolate(indexes["probe_p"], time_s, 1, "probe p A")
        probe_p_B, _ = interpolate(indexes["probe_p"], time_s, 2, "probe p B")
        output.append({
            "time_s": time_s,
            "mean_withdrawal_L": 0.5 * ((initialA - indexes["tankA"][idx][1]) + (initialB - indexes["tankB"][idx][1])) * 1000.0,
            "mean_probe_p_abs_Pa": 0.5 * (probe_p_A + probe_p_B),
            "mean_seat_Q_m3_s": 0.5 * ((fluxes["flux_A1"] + fluxes["flux_A2"]) + (fluxes["flux_B1"] + fluxes["flux_B2"])),
        })
    return output


def write_outputs() -> None:
    capture_path = BUNDLE / "inputs/capture-manifest.json"
    if not capture_path.is_file():
        raise FileNotFoundError("run capture step first")
    manifest = json.loads(capture_path.read_text())
    dictionary_capture_path = BUNDLE / "inputs/provenance/measurement-source-dictionaries.json"
    if not dictionary_capture_path.is_file():
        raise FileNotFoundError("capture measurement-source dictionaries before analysis")
    dictionary_capture = json.loads(dictionary_capture_path.read_text())
    current = read_series("current")
    prior = read_series("prior")
    rows, unavailable = collect_target_rows(current, prior, manifest)
    readiness = json.loads((BUNDLE / "inputs/provenance/native_initial_readiness.json").read_text())
    inventory = readiness["initial_state"]["zone_inventories"]
    initialA = inventory["tankAZone"]["native_water_volume_m3"]
    initialB = inventory["tankBZone"]["native_water_volume_m3"]
    cutoff = manifest["current_solver_prefix_cutoff_s"]
    current_curve = derive_prefix_rows(current, cutoff, initialA, initialB)
    prior_curve = derive_prefix_rows(prior, cutoff, initialA, initialB)
    modelmeta = json.loads((BUNDLE / "inputs/provenance/model_comparison.json").read_text())
    model_curves: dict[str, list[dict[str, float]]] = {}
    for arm, source_key in (("ngamma", "gamma_dt50us"), ("n1", "isothermal_dt50us")):
        history = dict_rows(ROOT / modelmeta["generated_from_runs"][source_key]["summary_files"]["history.csv"]["path"])
        model_curves[arm] = [row for row in history if row["time_s"] <= cutoff]

    output_csv = BUNDLE / "analysis/current-cold-hydraulics-common-times.csv"
    columns = [key for key in rows[0] if key not in {"native_sampling", "ode_values"}] if rows else []
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in columns})

    analysis_script = Path(__file__)
    metadata_file_hashes = {key: item["sha256"] for key, item in manifest["files"].items()}
    source_model_paths = {arm: item for arm, item in manifest["model_history_sources"].items()}
    summary = {
        "schema": "i4f-current-cold-hydraulics-prefix-comparison/v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "prefix_only": True,
        "capture_manifest_path": str(capture_path.relative_to(ROOT)),
        "capture_manifest_sha256": sha_file(capture_path),
        "current_solver_prefix_cutoff_s": cutoff,
        "current_solver_status_at_capture": manifest["current_guard_branch_status_at_capture"],
        "current_solver_guard_time_at_capture_s": manifest["current_guard_time_s_at_capture"],
        "complete_current_native_times_compared_s": [row["time_s"] for row in rows],
        "requested_times_not_available": unavailable,
        "current_solver": {
            "bundle": str(CURRENT_RUN.relative_to(ROOT)),
            "container_id": manifest["current_container"]["id"],
            "container_name": manifest["current_container"]["name"],
            "started_at_utc": manifest["current_container"]["started_at"],
            "container_running_at_capture": manifest["current_container"]["running"],
            "native_process_prefix_has_14_fields_plus_dgdt": True,
            "binary_sha256": json.loads((BUNDLE / "inputs/provenance/current-launch_manifest.json").read_text())["binary_sha256"],
            "static_input_tree_sha256": json.loads((BUNDLE / "inputs/provenance/current-launch_manifest.json").read_text())["static_input_tree_sha256"],
            "static_case_tree_sha256": json.loads((BUNDLE / "inputs/provenance/current-launch_manifest.json").read_text())["static_case_tree_sha256"],
            "momentum_predictor_enabled": momentum_predictor_enabled(BUNDLE / "inputs/provenance/current-fvSolution.txt"),
            "restart_qualification": "Cold-derived predictor-off history resumed operationally from the accepted 0.090771166664 s checkpoint after the prior bundle hit its disk guard. The continuation retained 14 native fields plus dgdt and uniform/time; full-apparatus bitwise continuity is not claimed.",
        },
        "prior_cfd": {
            "bundle": str(PRIOR_RUN.relative_to(ROOT)),
            "container_id": manifest["previous_cfd_case"]["container_id"],
            "started_at_utc": manifest["previous_cfd_case"]["docker_started_at"],
            "binary_sha256": manifest["previous_cfd_case"]["binary_sha256"],
            "momentum_predictor_enabled": momentum_predictor_enabled(BUNDLE / "inputs/provenance/prior-fvSolution.txt"),
            "source_family": "earlier standard-source DCEC cold case; not a matched momentum-predictor-only control for this full-source Pno continuation",
        },
        "reduced_model_sources": {
            "published_comparison_json": str(PUBLISHED_SUMMARY.relative_to(ROOT)),
            "published_comparison_sha256": sha_file(BUNDLE / "inputs/provenance/published_summary.json"),
            "model_definitions_json": str(MODEL_COMPARE.relative_to(ROOT)),
            "model_definitions_sha256": sha_file(BUNDLE / "inputs/provenance/model_comparison.json"),
            "histories": source_model_paths,
            "comparisons_are_non_fitted": True,
            "one_representative_tank_with_two_branches": True,
            "common_geometry_and_Cd_assumptions_across_n_arms": True,
            "n_gamma": modelmeta["generated_from_runs"]["gamma_dt50us"]["polytropic_n"],
            "n1_isothermal": modelmeta["generated_from_runs"]["isothermal_dt50us"]["polytropic_n"],
        },
        "measurement_definitions": {
            "tank_inventory": "Native volFieldValue volIntegrate(alpha.water) in each tank cellZone. Reported as VOF volume, not EOS water mass.",
            "withdrawal": "Initial native tank alpha.water volume minus sampled tank alpha.water volume; mean of tanks A and B, converted to litres. The reduced model uses its own t=0 tank-water volume.",
            "native_Q": "Sum the second numeric data column, sum(alphaPhi0.water), over seat A1+A2 and B1+B2; the first data column after time is face area and is excluded. Positive seat-zone flux is read from the frozen face-zone convention. Mean Q is the average of the two tank totals.",
            "pressure": "Mean of two local p point probes in tank headspaces. CFD point probes are not tank-volume means; reduced-model pressure is bulk gas pressure.",
            "probe_locations_m": [[1.25, -0.55, 1.60], [1.25, 0.55, 1.60]],
            "probe_fields": ["p", "T", "alpha.water", "U"],
            "probe_alignment": "Every p/T probe is interpolated to the exact full-precision tank/seat sample time; at a prefix endpoint only, the nearest probe row is accepted within its 8-digit printed-time rounding bound (5.1 ns). No extrapolation beyond that representation bound. Model histories are bracket-interpolated at the same time.",
        },
        "rows": rows,
        "prefix_curve_rows": len(current_curve),
        "caveats": [
            "The current run remains a prefix at the stated cutoff; absence of a later checkpoint is not run completion.",
            "The current full-source predictor-off continuation and earlier standard-source CFD differ in solver/source lineage; their differences are descriptive and not a one-factor causal estimate.",
            "The n=gamma and n=1 arms share the model's assumed compact geometry and Cd; agreement is an internal consistency check, not independent experimental validation.",
            "The reduced ODE has one representative tank and two branches; CFD reports both tanks separately and the table averages their native seat flows and withdrawals.",
            "CFD tank inventory and withdrawal use VOF alpha volume. They are not water-mass measurements for the finite-water EOS run.",
            "Headspace p/T values are local probes, not volume-weighted gas means. The pressure comparison therefore mixes local CFD samples with bulk-model pressure and is a screening comparison.",
            "No fit, valve coefficient adjustment, or thermal-exponent fit was performed. No validation gate is claimed.",
        ],
        "repository": manifest["repository"],
        "source_input_sha256": metadata_file_hashes,
        "measurement_source_dictionaries": {
            "path": str(dictionary_capture_path.relative_to(ROOT)),
            "sha256": sha_file(dictionary_capture_path),
            "record": dictionary_capture,
        },
        "analysis_command": ".venv/bin/python scripts/run_local.py --threads 1 --timeout 300 -- nice -n 19 .venv/bin/python results/runs/i4f-current-cold-hydraulics-20261026T2126Z/scripts/analyze_current_cold_hydraulics.py",
        "capture_command": manifest["capture_command"],
        "analysis_source": {
            "private_path": str(analysis_script.relative_to(ROOT)),
            "sha256": sha_file(analysis_script),
        },
        "private_csv_path": str(output_csv.relative_to(ROOT)),
        "private_csv_sha256": sha_file(output_csv),
    }
    out_json = BUNDLE / "analysis/current-cold-hydraulics-prefix.json"
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    make_plot(current_curve, prior_curve, model_curves, rows, cutoff, BUNDLE / "analysis/current-cold-hydraulics-prefix.png")
    print(json.dumps({"cutoff_s": cutoff, "times": summary["complete_current_native_times_compared_s"], "unavailable": unavailable, "csv": str(output_csv.relative_to(ROOT)), "json": str(out_json.relative_to(ROOT))}, indent=2))


def make_plot(current: list[dict[str, float]], prior: list[dict[str, float]], models: dict[str, list[dict[str, float]]], target_rows: list[dict[str, Any]], cutoff: float, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
    colors = {"current": "#b2182b", "prior": "#2166ac", "ngamma": "#1b7837", "n1": "#762a83"}
    current_t = [row["time_s"] for row in current]
    prior_t = [row["time_s"] for row in prior]
    model_t = {key: [row["time_s"] for row in data] for key, data in models.items()}
    axes[0].plot(current_t, [row["mean_withdrawal_L"] for row in current], color=colors["current"], lw=1.6, label="current Pno full-source, mean of tanks")
    axes[0].plot(prior_t, [row["mean_withdrawal_L"] for row in prior], color=colors["prior"], lw=1.3, label="prior standard-source CFD, mean of tanks")
    axes[0].plot(model_t["ngamma"], [(models["ngamma"][i]["tank_water_volume_m3"] - 1.35) * -1000.0 for i in range(len(models["ngamma"]))], color=colors["ngamma"], lw=1.3, label="ODE n=gamma")
    axes[0].plot(model_t["n1"], [(models["n1"][i]["tank_water_volume_m3"] - 1.35) * -1000.0 for i in range(len(models["n1"]))], color=colors["n1"], lw=1.2, label="ODE n=1")
    axes[0].set_ylabel("Tank withdrawal (L)\nfrom 1.35 m³ initial VOF volume")
    axes[0].legend(loc="upper left", fontsize=8)

    axes[1].plot(current_t, [row["mean_probe_p_abs_Pa"] / 1e6 for row in current], color=colors["current"], lw=1.6, label="current CFD: mean of two local probes")
    axes[1].plot(prior_t, [row["mean_probe_p_abs_Pa"] / 1e6 for row in prior], color=colors["prior"], lw=1.3, label="prior CFD: mean of two local probes")
    axes[1].plot(model_t["ngamma"], [row["gas_pressure_abs_Pa"] / 1e6 for row in models["ngamma"]], color=colors["ngamma"], lw=1.3, label="ODE n=gamma: bulk gas pressure")
    axes[1].plot(model_t["n1"], [row["gas_pressure_abs_Pa"] / 1e6 for row in models["n1"]], color=colors["n1"], lw=1.2, label="ODE n=1: bulk gas pressure")
    axes[1].set_ylabel("Absolute pressure (MPa)\nlocal CFD probes / bulk ODE")
    axes[1].legend(loc="upper right", fontsize=8)

    axes[2].plot(current_t, [row["mean_seat_Q_m3_s"] for row in current], color=colors["current"], lw=1.6, label="current CFD: native seat flux")
    axes[2].plot(prior_t, [row["mean_seat_Q_m3_s"] for row in prior], color=colors["prior"], lw=1.3, label="prior CFD: native seat flux")
    axes[2].plot(model_t["ngamma"], [row["total_branch_flow_m3_s"] for row in models["ngamma"]], color=colors["ngamma"], lw=1.3, label="ODE n=gamma: branch inflow")
    axes[2].plot(model_t["n1"], [row["total_branch_flow_m3_s"] for row in models["n1"]], color=colors["n1"], lw=1.2, label="ODE n=1: branch inflow")
    axes[2].set_ylabel("Tank-to-valve flow (m³/s)\nseat sums / branch inflow")
    axes[2].set_xlabel("Physical time (s)")
    axes[2].legend(loc="upper left", fontsize=8)
    for ax in axes:
        for row in target_rows:
            ax.axvline(row["time_s"], color="#666666", lw=0.6, ls=":", alpha=0.55)
        ax.set_xlim(min(current_t[0], 0.09), cutoff)
        ax.grid(True, alpha=0.25)
    fig.suptitle(f"Cold-derived Pno hydraulics prefix through t={cutoff:.9f} s\nComparisons are descriptive; CFD/ODE pressure support differs")
    fig.text(0.5, 0.012, "Prefix snapshot only; current CFD operationally resumed at 0.090771 s. CFD tank values are α-volume; headspace pressure is point-probed.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 0.96))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="freeze current/prior native rows and runtime identity")
    parser.add_argument("--capture-dictionaries", action="store_true", help="freeze the solver-mode and probe-source dictionaries")
    args = parser.parse_args()
    if args.capture:
        capture()
    elif args.capture_dictionaries:
        capture_source_dictionaries()
    else:
        write_outputs()


if __name__ == "__main__":
    main()
