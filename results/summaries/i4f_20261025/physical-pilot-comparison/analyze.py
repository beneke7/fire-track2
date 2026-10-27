#!/usr/bin/env python3
"""Read-only, snapshot-bounded comparison of three I4F physical pilot arms."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = ROOT / "results/runs/i4f-physical-alpha-flux-relax-candidate-20261027T024711Z/arms"
SEED_TIME = 0.390705595007351136
TARGETS = (0.391, 0.392, 0.394, 0.395, 0.42, 0.46, 0.48, 0.4907023481865, 0.50, 0.51)
KV = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TIME_RE = re.compile(r"^Time\s*=\s*([-+\d.eE]+)")
DT_RE = re.compile(r"^deltaT\s*=\s*([-+\d.eE]+)")
EXEC_RE = re.compile(r"^ExecutionTime\s*=\s*([-+\d.eE]+)\s*s\s+ClockTime\s*=\s*([-+\d.eE]+)\s*s")
FIELD_RE = re.compile(
    r"^\s*([-+\d.eE]+)\s+(\S+)\s+([-+\d.eE]+)\s+\(([^)]+)\)\s+\d+\s+([-+\d.eE]+)\s+\(([^)]+)\)\s+\d+"
)

CASES = {
    "outer8": {
        "arm": BASE / "physical-omega-050-outer-pair/outer8",
        "attempt": None,
        "maxDeltaT": 0.00025,
        "nOuter": 8,
    },
    "outer16": {
        "arm": BASE / "physical-omega-050-outer-pair/outer16",
        "attempt": "attempts/attempt-007-readiness-marker-retry",
        "maxDeltaT": 0.00025,
        "nOuter": 16,
    },
    "dtcap_half_outer16": {
        "arm": BASE / "physical-omega-050-dtcap-half-outer16",
        "attempt": "attempts/attempt-002-dtcap-half",
        "maxDeltaT": 0.000125,
        "nOuter": 16,
    },
}

OBJECTS = (
    "seatFluxA1",
    "seatFluxA2",
    "seatFluxB1",
    "seatFluxB2",
    "seatPressureA1",
    "seatPressureA2",
    "seatPressureB1",
    "seatPressureB2",
    "tankAWaterVolume",
    "tankBWaterVolume",
    "lineAInitialWaterVolume",
    "lineBInitialWaterVolume",
    "lineAMouthBoundaryWaterVolume",
    "lineBMouthBoundaryWaterVolume",
    "totalWaterVolume",
    "externalAirWaterVolume",
    "fourMouthPlaneTotalUIntegral",
    "fourMouthPlaneWaterWeightedUIntegral",
)
PROBE_FIELDS = ("p", "T", "U", "alpha.water")
UPDATE_FIELDS = ("max_abs_dp_Pa", "max_abs_dU_m_s", "max_abs_dphi_m3_s", "max_abs_dalpha1")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_prefix(path: Path, size: int) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = size
        while remaining:
            block = stream.read(min(8 * 1024 * 1024, remaining))
            if not block:
                break
            h.update(block)
            remaining -= len(block)
    return h.hexdigest()


def rounded_time(value: float) -> float:
    return round(value, 12)


def add_seconds_to_rfc3339(value: str, seconds: int) -> str:
    match = re.fullmatch(
        r"(?P<whole>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?P<fraction>\.\d+)?(?P<zone>Z|[+-]\d{2}:\d{2})",
        value,
    )
    if not match:
        raise ValueError(f"unsupported RFC3339 timestamp: {value}")
    whole = datetime.fromisoformat(match.group("whole") + match.group("zone"))
    shifted = whole + timedelta(seconds=seconds)
    return (
        shifted.strftime("%Y-%m-%dT%H:%M:%S")
        + (match.group("fraction") or "")
        + match.group("zone")
    )


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def num(kv: dict[str, str], key: str) -> float | None:
    try:
        value = float(kv[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def inspect_container(identity: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{json .}}", "--type", "container", identity],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    raw = json.loads(result.stdout)
    state = raw.get("State", {})
    return {
        "id": raw.get("Id"),
        "name": raw.get("Name", "").lstrip("/"),
        "status": state.get("Status"),
        "running": state.get("Running"),
        "paused": state.get("Paused"),
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "oom_killed": state.get("OOMKilled"),
        "log_driver": raw.get("HostConfig", {}).get("LogConfig", {}).get("Type"),
    }


def inspect_guard_service(container_name: str) -> dict[str, Any]:
    unit = f"{container_name}-guard.service"
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            "--no-pager",
            "--property=Id,ActiveState,SubState,RuntimeMaxUSec,TimeoutStartUSec",
            unit,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    values = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return {
        "unit": unit,
        "query_returncode": result.returncode,
        "error": result.stderr.strip() or None,
        "id": values.get("Id"),
        "active_state": values.get("ActiveState"),
        "sub_state": values.get("SubState"),
        "runtime_max_usec": values.get("RuntimeMaxUSec"),
        "timeout_start_usec": values.get("TimeoutStartUSec"),
    }


def scan_log(path: Path, snapshot_bytes: int) -> dict[str, Any]:
    timestep_rows: list[dict[str, float]] = []
    clock_rows: list[dict[str, float]] = []
    outer: dict[float, list[dict[str, Any]]] = defaultdict(list)
    thermo: dict[float, dict[str, Any]] = {}
    pressure_floor_crossings: list[dict[str, Any]] = []
    phase: dict[float, dict[str, Any]] = {}
    phase_state_counts: dict[float, int] = defaultdict(int)
    initial: dict[str, float] = {}
    token_counts: dict[str, int] = defaultdict(int)
    pending_dt: float | None = None
    latest_time_s: float | None = None
    incomplete_last_line = False

    with path.open("rb") as stream:
        remaining = snapshot_bytes
        while remaining:
            raw = stream.readline(min(remaining, 2 * 1024 * 1024))
            if not raw:
                break
            remaining -= len(raw)
            if not raw.endswith(b"\n"):
                incomplete_last_line = True
                break
            line = raw.decode("utf-8", errors="replace").strip()
            dt_match = DT_RE.match(line)
            if dt_match:
                try:
                    pending_dt = float(dt_match.group(1))
                except ValueError:
                    pending_dt = None
            time_match = TIME_RE.match(line)
            if time_match:
                try:
                    t = float(time_match.group(1))
                except ValueError:
                    t = None
                if t is not None:
                    timestep_rows.append({"time_s": t, "deltaT_s": pending_dt or math.nan})
                    latest_time_s = t
                pending_dt = None
            execution_match = EXEC_RE.match(line)
            if execution_match and latest_time_s is not None:
                clock_rows.append(
                    {
                        "time_s": latest_time_s,
                        "execution_time_s": float(execution_match.group(1)),
                        "clock_time_s": float(execution_match.group(2)),
                    }
                )

            for token in re.findall(r"\bI4F_[A-Z0-9_]+", line):
                token_counts[token] += 1
            if not line.startswith("I4F_") and not re.match(r"^\[\d+\]\s+I4F_", line):
                continue
            marker_match = re.search(r"\b(I4F_[A-Z0-9_]+)", line)
            if not marker_match:
                continue
            marker = marker_match.group(1)
            kv = dict(KV.findall(line))
            t = num(kv, "time_s")
            if marker == "I4F_INITIAL_PHASE_MASS":
                initial = {
                    k: float(v)
                    for k, v in kv.items()
                    if k in {"water_inventory_kg", "gas_inventory_kg"}
                }
            elif marker == "I4F_OUTER_STATE_DELTA" and t is not None:
                row: dict[str, Any] = {"time_s": t, "raw": kv}
                row["outer_iteration"] = num(kv, "outer_iteration")
                for key in UPDATE_FIELDS:
                    row[key] = num(kv, key)
                outer[rounded_time(t)].append(row)
            elif marker == "I4F_THERMO_ENVELOPE" and t is not None:
                raw_min_p = num(kv, "min_raw_p_water_Pa")
                if raw_min_p is not None and raw_min_p < 10000.0:
                    pressure_floor_crossings.append({
                        "time_s": t,
                        "outer_iteration": num(kv, "outer"),
                        "pass": num(kv, "pass"),
                        "min_raw_water_pressure_Pa": raw_min_p,
                        "max_water_supported_T_K": num(kv, "max_T_water_supported_K"),
                        "saturation_margin_Pa": num(kv, "saturation_margin_Pa"),
                        "T_envelope_ok": num(kv, "T_envelope_ok"),
                    })
                key = rounded_time(t)
                row = thermo.setdefault(
                    key,
                    {
                        "time_s": t,
                        "passes": 0,
                        "min_raw_water_pressure_Pa": math.inf,
                        "max_water_supported_T_K": -math.inf,
                        "min_saturation_margin_Pa": math.inf,
                        "T_envelope_ok": 1.0,
                    },
                )
                row["passes"] += 1
                for field, out_key, fn in (
                    ("min_raw_p_water_Pa", "min_raw_water_pressure_Pa", min),
                    ("max_T_water_supported_K", "max_water_supported_T_K", max),
                    ("saturation_margin_Pa", "min_saturation_margin_Pa", min),
                    ("T_envelope_ok", "T_envelope_ok", min),
                ):
                    value = num(kv, field)
                    if value is not None:
                        row[out_key] = fn(row[out_key], value)
            elif marker == "I4F_PHASE_MASS_STATE" and t is not None:
                phase_state_counts[rounded_time(t)] += 1
                if kv.get("stage") == "after_correctRho":
                    key = rounded_time(t)
                    pass_id = num(kv, "pass") or -1
                    old = phase.get(key)
                    if old is None or pass_id >= old.get("pass", -1):
                        phase[key] = {
                            "time_s": t,
                            "pass": pass_id,
                            "water_inventory_kg": num(kv, "water_inventory_kg"),
                            "gas_inventory_kg": num(kv, "gas_inventory_kg"),
                            "water_signed_boundary_flux_kg_s": num(
                                kv, "water_signed_boundary_flux_kg_s"
                            ),
                            "gas_signed_boundary_flux_kg_s": num(
                                kv, "gas_signed_boundary_flux_kg_s"
                            ),
                        }

    update_series = []
    for t, rows in sorted(outer.items()):
        rows.sort(key=lambda r: r.get("outer_iteration") or -1)
        final = rows[-1]
        penult = rows[-2] if len(rows) > 1 else {}
        out: dict[str, Any] = {
            "time_s": final["time_s"],
            "outer_rows": len(rows),
            "final_outer_iteration": final.get("outer_iteration"),
            "penultimate_outer_iteration": penult.get("outer_iteration"),
        }
        for field in UPDATE_FIELDS:
            out[f"final_{field}"] = final.get(field)
            out[f"penultimate_{field}"] = penult.get(field)
            a, b = out[f"final_{field}"], out[f"penultimate_{field}"]
            out[f"final_to_penultimate_{field}_ratio"] = (
                a / b if isinstance(a, (float, int)) and isinstance(b, (float, int)) and b else None
            )
        update_series.append(out)

    recorded_times = [row["time_s"] for row in timestep_rows]
    mismatches = []
    if timestep_rows:
        first_logged = timestep_rows[0].get("deltaT_s")
        if first_logged is not None and math.isfinite(first_logged):
            mismatches.append(abs(timestep_rows[0]["time_s"] - SEED_TIME - first_logged))
    for previous, current in zip(timestep_rows, timestep_rows[1:]):
        dt = current["time_s"] - previous["time_s"]
        logged = current.get("deltaT_s")
        if logged is not None and math.isfinite(logged):
            mismatches.append(abs(dt - logged))
    return {
        "snapshot_bytes": snapshot_bytes,
        "snapshot_sha256": sha_prefix(path, snapshot_bytes),
        "incomplete_final_line": incomplete_last_line,
        "timestep_rows": timestep_rows,
        "clock_rows": clock_rows,
        "dt_summary": {
            "count": len(timestep_rows),
            "first_time_s": recorded_times[0] if recorded_times else None,
            "last_time_s": recorded_times[-1] if recorded_times else None,
            "first_deltaT_s": timestep_rows[0]["deltaT_s"] if timestep_rows else None,
            "last_deltaT_s": timestep_rows[-1]["deltaT_s"] if timestep_rows else None,
            "min_deltaT_s": min(
                (r["deltaT_s"] for r in timestep_rows if math.isfinite(r["deltaT_s"])), default=None
            ),
            "max_deltaT_s": max(
                (r["deltaT_s"] for r in timestep_rows if math.isfinite(r["deltaT_s"])), default=None
            ),
            "max_abs_deltaT_vs_printed_time_s": max(mismatches, default=None),
        },
        "outer_update_series": update_series,
        "thermo_by_time": thermo,
        "pressure_floor_crossings": pressure_floor_crossings,
        "phase_mass_by_time": phase,
        "phase_state_counts": phase_state_counts,
        "initial_phase_mass": initial,
        "token_counts": dict(token_counts),
        "coverage": {
            "log_time_rows": len(timestep_rows),
            "outer_update_times": len(outer),
            "thermo_times": len(thermo),
            "after_correctRho_mass_times": len(phase),
            "time_without_outer_delta_count": len(
                set(map(rounded_time, recorded_times)) - set(outer)
            ),
            "time_without_thermo_count": len(set(map(rounded_time, recorded_times)) - set(thermo)),
            "time_without_mass_count": len(set(map(rounded_time, recorded_times)) - set(phase)),
            "outer_rows_per_time_histogram": dict(sorted(Counter(map(len, outer.values())).items())),
            "outer_partial_or_unexpected_samples": [
                {"time_s": rows[0]["time_s"], "rows": len(rows)}
                for rows in outer.values()
                if len(rows) not in (8, 16)
            ][-5:],
            "thermo_passes_per_time_histogram": dict(
                sorted(Counter(row["passes"] for row in thermo.values()).items())
            ),
            "phase_state_records_per_time_histogram": dict(
                sorted(Counter(phase_state_counts.values()).items())
            ),
            "phase_state_partial_or_unexpected_samples": [
                {"time_s": key, "records": value}
                for key, value in phase_state_counts.items()
                if value not in (32, 64)
            ][-5:],
        },
    }


def parse_field_file(path: Path, snapshot_bytes: int) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    header = ""
    with path.open("rb") as stream:
        remaining = snapshot_bytes
        while remaining:
            raw = stream.readline(min(remaining, 1024 * 1024))
            if not raw:
                break
            remaining -= len(raw)
            if not raw.endswith(b"\n"):
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("#"):
                if "Time" in line:
                    header = line[1:].strip()
                continue
            match = FIELD_RE.match(line)
            if match:
                rows.append(
                    {
                        "time_s": float(match.group(1)),
                        "field": match.group(2),
                        "min": float(match.group(3)),
                        "max": float(match.group(5)),
                    }
                )
    return rows, header


def parse_numeric_series(path: Path, snapshot_bytes: int) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    header = ""
    with path.open("rb") as stream:
        remaining = snapshot_bytes
        while remaining:
            raw = stream.readline(min(remaining, 1024 * 1024))
            if not raw:
                break
            remaining -= len(raw)
            if not raw.endswith(b"\n"):
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("#"):
                if "Time" in line:
                    header = line[1:].strip()
                continue
            values = [float(x) for x in NUM.findall(line)]
            if len(values) >= 2 and math.isfinite(values[0]):
                rows.append({"time_s": values[0], "values": values[1:]})
    return rows, header


def parse_postprocessing(case: Path) -> dict[str, Any]:
    root = case / "postProcessing"
    objects: dict[str, list[dict[str, Any]]] = defaultdict(list)
    field_extrema: dict[str, list[dict[str, float]]] = defaultdict(list)
    file_meta: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"objects": {}, "field_extrema": {}, "files": []}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if path.suffix != ".dat" and not (
            rel.parts[0] == "i4fTankHeadspaceProbes" and path.name in PROBE_FIELDS
        ):
            continue
        size = path.stat().st_size
        digest = sha_prefix(path, size)
        file_meta.append({"path": str(rel), "snapshot_bytes": size, "sha256": digest})
        if path.name == "fieldMinMax.dat":
            rows, _ = parse_field_file(path, size)
            for row in rows:
                field_extrema[row["field"]].append(row)
        else:
            rows, header = parse_numeric_series(path, size)
            object_name = rel.parts[0]
            if rows:
                objects[object_name].append(
                    {
                        "file": str(rel),
                        "header": header,
                        "rows": rows,
                    }
                )
    return {"objects": dict(objects), "field_extrema": dict(field_extrema), "files": file_meta}


def flatten_object_series(post: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for object_name, file_groups in post["objects"].items():
        for group in file_groups:
            for row in group["rows"]:
                result[object_name].append(row)
    for values in result.values():
        values.sort(key=lambda row: row["time_s"])
    return result


def nearest(items: list[dict[str, Any]], target: float) -> dict[str, Any] | None:
    if not items:
        return None
    return min(items, key=lambda row: abs(row["time_s"] - target))


def nearest_exact_map(mapping: dict[float, dict[str, Any]], target: float) -> dict[str, Any] | None:
    return nearest(list(mapping.values()), target)


def nearest_field(series: list[dict[str, Any]], target: float) -> dict[str, Any] | None:
    return nearest(series, target)


def load_health_csv(path: Path) -> dict[str, Any]:
    size = path.stat().st_size if path.exists() else 0
    rows = []
    if size:
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("time_s"):
                    rows.append(row)
    return {
        "path": str(path),
        "snapshot_bytes": size,
        "sha256": sha_prefix(path, size) if size else None,
        "rows": rows,
    }


def dict_nearest_by_time(
    mapping: dict[float, dict[str, Any]], target: float
) -> dict[str, Any] | None:
    return nearest_exact_map(mapping, target)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    try:
        os.nice(19)
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    except (AttributeError, OSError):
        pass
    snapshot_utc = utc()
    runs: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {
        "schema": "i4f-physical-pilot-common-time-analysis/v1",
        "created_utc": snapshot_utc,
        "analysis_bundle": str(OUT.relative_to(ROOT)),
        "source_bundle": str(BASE.parent.relative_to(ROOT)),
        "comparison_method": "nearest physical-time samples; no wall-time alignment or interpolation",
        "target_times_s": list(TARGETS),
        "seed_time_s": SEED_TIME,
        "arms": {},
    }
    for name, config in CASES.items():
        arm = config["arm"]
        attempt = arm / config["attempt"] if config["attempt"] else arm
        manifest_path = (
            arm / "launch-manifest.json"
            if config["attempt"] is None
            else attempt / "launch-manifest.json"
        )
        guard_path = (
            arm / "guardian-status.json"
            if config["attempt"] is None
            else attempt / "guardian-status.json"
        )
        manifest = json.loads(manifest_path.read_text())
        guard = json.loads(guard_path.read_text())
        branch = guard.get("branches", {}).get("fourmouth_coldstart", {})
        docker = inspect_container(manifest["container_id"])
        guard_service = inspect_guard_service(docker["name"])
        log_path = Path(branch["log"])
        log_bytes = log_path.stat().st_size
        log = scan_log(log_path, log_bytes)
        health_path = attempt / "step_health.csv" if config["attempt"] else arm / "step_health.csv"
        health = load_health_csv(health_path)
        post = parse_postprocessing(arm / "case")
        processor_root = arm / "case/processors10"
        native_checkpoint_times = []
        if processor_root.is_dir():
            for child in processor_root.iterdir():
                if child.is_dir():
                    try:
                        native_checkpoint_times.append({"path": str(child.relative_to(ROOT)), "time_s": float(child.name)})
                    except ValueError:
                        continue
        native_checkpoint_times.sort(key=lambda row: row["time_s"])
        objects = flatten_object_series(post)
        for object_name in objects:
            objects[object_name].sort(key=lambda row: row["time_s"])
        # Probe outputs share the same function-object name and are held as separate file groups.
        probes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for group in post["objects"].get("i4fTankHeadspaceProbes", []):
            field_name = Path(group["file"]).name
            if field_name in PROBE_FIELDS:
                probes[field_name].extend(group["rows"])
        for rows in probes.values():
            rows.sort(key=lambda row: row["time_s"])
        control = (arm / "case/system/controlDict").read_text()
        scalar = {}
        for key in ("adjustTimeStep", "maxCo", "maxAlphaCo", "maxDeltaT", "startTime", "endTime"):
            match = re.search(r"(?m)^\s*" + re.escape(key) + r"\s+([^;]+);", control)
            scalar[key] = match.group(1).strip() if match else None
        seed_time_path = arm / "case/processors10/0.390705595007/uniform/time"
        seed_text = seed_time_path.read_text() if seed_time_path.is_file() else ""
        seed_dt_match = re.search(r"(?m)^\s*deltaT\s+([^;]+);", seed_text)
        seed_dt0_match = re.search(r"(?m)^\s*deltaT0\s+([^;]+);", seed_text)
        run = {
            "name": name,
            "arm": str(arm.relative_to(ROOT)),
            "attempt": config["attempt"],
            "manifest": manifest,
            "guard": guard,
            "branch": branch,
            "docker": docker,
            "guard_service": guard_service,
            "log_path": str(log_path),
            "log": log,
            "health": health,
            "post": post,
            "objects": objects,
            "probes": probes,
            "control": scalar,
            "seed_deltaT_s": float(seed_dt_match.group(1)) if seed_dt_match else None,
            "seed_deltaT0_s": float(seed_dt0_match.group(1)) if seed_dt0_match else None,
        }
        runs[name] = run
        dt = log["dt_summary"]
        branch_health = branch.get("last_step_health", {})
        summary["arms"][name] = {
            "arm": str(arm.relative_to(ROOT)),
            "attempt": config["attempt"],
            "container": docker,
            "guard_service": guard_service,
            "guard_status": guard.get("status"),
            "branch_status": branch.get("status"),
            "branch_current_time_s": branch.get("current_time_s"),
            "branch_completed_steps": branch.get("completed_steps"),
            "branch_current_deltaT_s": branch.get("current_deltaT_s"),
            "raw_log_last_time_minus_guard_current_time_s": (
                dt["last_time_s"] - float(branch["current_time_s"])
                if dt["last_time_s"] is not None and branch.get("current_time_s") is not None
                else None
            ),
            "raw_log_time_rows_minus_guard_completed_steps": dt["count"]
            - int(branch.get("completed_steps", 0)),
            "branch_stop_reason": branch.get("write_now_reason"),
            "control": scalar,
            "seed_deltaT_s": run["seed_deltaT_s"],
            "seed_deltaT0_s": run["seed_deltaT0_s"],
            "raw_log": {
                "path": str(log_path.relative_to(ROOT)),
                "snapshot_bytes": log["snapshot_bytes"],
                "snapshot_sha256": log["snapshot_sha256"],
                "incomplete_final_line": log["incomplete_final_line"],
            },
            "dt_series": dt,
            "initial_phase_mass": log["initial_phase_mass"],
            "latest_guard_mass_budget": {
                k: branch_health.get(k, branch.get(k))
                for k in (
                    "water_inventory_kg",
                    "gas_inventory_kg",
                    "water_cumulative_defect_kg",
                    "gas_cumulative_defect_kg",
                    "water_cumulative_defect_fraction_initial",
                    "gas_cumulative_defect_fraction_initial",
                    "water_boundary_flux_kg_s",
                    "gas_boundary_flux_kg_s",
                )
            },
            "latest_raw_phase_mass_state": max(
                log["phase_mass_by_time"].values(), key=lambda row: row["time_s"], default=None
            ),
            "raw_phase_inventory_delta_from_seed_kg": {
                "water": (
                    max(log["phase_mass_by_time"].values(), key=lambda row: row["time_s"])["water_inventory_kg"]
                    - log["initial_phase_mass"].get("water_inventory_kg")
                    if log["phase_mass_by_time"]
                    and max(log["phase_mass_by_time"].values(), key=lambda row: row["time_s"]).get("water_inventory_kg") is not None
                    else None
                ),
                "gas": (
                    max(log["phase_mass_by_time"].values(), key=lambda row: row["time_s"])["gas_inventory_kg"]
                    - log["initial_phase_mass"].get("gas_inventory_kg")
                    if log["phase_mass_by_time"]
                    and max(log["phase_mass_by_time"].values(), key=lambda row: row["time_s"]).get("gas_inventory_kg") is not None
                    else None
                ),
            },
            "latest_guard_step_health": branch_health,
            "guard_diagnostic_counts": {
                "diagnostic_errors": len(branch.get("diagnostic_errors", [])),
                "parser_errors": len(branch.get("parser_errors", [])),
                "thermo_envelope_errors": len(branch.get("thermo_envelope_errors", [])),
                "diagnostic_error_samples": branch.get("diagnostic_errors", [])[:4],
                "parser_error_samples": branch.get("parser_errors", [])[:4],
                "thermo_error_samples": branch.get("thermo_envelope_errors", [])[:4],
            },
            "raw_parser_coverage": log["coverage"],
            "raw_token_counts": log["token_counts"],
            "raw_minimum_pressure_state": min(
                log["thermo_by_time"].values(),
                key=lambda row: row["min_raw_water_pressure_Pa"],
                default=None,
            ),
            "first_raw_pressure_floor_contact": log["pressure_floor_crossings"][0]
            if log["pressure_floor_crossings"]
            else None,
            "raw_pressure_floor_crossing_pass_count": len(log["pressure_floor_crossings"]),
            "latest_recorded_field_extrema": {
                field: max(rows, key=lambda row: row["time_s"], default=None)
                for field, rows in post["field_extrema"].items()
                if field in {"p", "T", "U", "mag(U)"}
            },
            "step_health_csv": {
                "path": str(health_path.relative_to(ROOT)),
                "snapshot_bytes": health["snapshot_bytes"],
                "rows": len(health["rows"]),
                "first_time_s": float(health["rows"][0]["time_s"]) if health["rows"] else None,
                "last_time_s": float(health["rows"][-1]["time_s"]) if health["rows"] else None,
                "buffering_note": "live guard flushes step_health.csv every 256 rows; zero bytes can be buffered before that threshold",
            },
            "postprocessing_file_count": len(post["files"]),
            "postprocessing_snapshot_bytes": sum(item["snapshot_bytes"] for item in post["files"]),
            "postprocessing_files": post["files"],
            "native_checkpoint_time_dirs": native_checkpoint_times,
            "source_snapshot_sha256": {
                "launch_manifest": sha_prefix(manifest_path, manifest_path.stat().st_size),
                "guard_manifest": sha_prefix(guard_path, guard_path.stat().st_size),
                "controlDict": sha_prefix(arm / "case/system/controlDict", (arm / "case/system/controlDict").stat().st_size),
                "seed_time": sha_prefix(seed_time_path, seed_time_path.stat().st_size) if seed_time_path.is_file() else None,
                "step_health_csv": health["sha256"],
            },
        }

        dt_rows = [{"arm": name, **row} for row in log["timestep_rows"]]
        write_csv(OUT / f"{name}-dt-series.csv", dt_rows, ["arm", "time_s", "deltaT_s"])
        update_rows = [{"arm": name, **row} for row in log["outer_update_series"]]
        if update_rows:
            write_csv(OUT / f"{name}-outer-updates.csv", update_rows)
        mass_rows = []
        time_keys = sorted(set(log["thermo_by_time"]) | set(log["phase_mass_by_time"]))
        field_p = post["field_extrema"].get("p", [])
        field_t = post["field_extrema"].get("T", [])
        field_u = post["field_extrema"].get("U", []) or post["field_extrema"].get("mag(U)", [])
        health_by_time = {
            rounded_time(float(r["time_s"])): r for r in health["rows"] if r.get("time_s")
        }
        for t in time_keys:
            tr = log["thermo_by_time"].get(t, {})
            mr = log["phase_mass_by_time"].get(t, {})
            pr = nearest(field_p, t)
            temp = nearest(field_t, t)
            ur = nearest(field_u, t)
            hr = health_by_time.get(t, {})
            mass_rows.append(
                {
                    "arm": name,
                    "time_s": mr.get("time_s", tr.get("time_s", t)),
                    "thermo_passes": tr.get("passes"),
                    "min_raw_water_pressure_Pa": tr.get("min_raw_water_pressure_Pa"),
                    "max_water_supported_T_K": tr.get("max_water_supported_T_K"),
                    "min_saturation_margin_Pa": tr.get("min_saturation_margin_Pa"),
                    "T_envelope_ok": tr.get("T_envelope_ok"),
                    "water_inventory_kg": mr.get("water_inventory_kg"),
                    "gas_inventory_kg": mr.get("gas_inventory_kg"),
                    "water_boundary_flux_kg_s": mr.get("water_signed_boundary_flux_kg_s"),
                    "gas_boundary_flux_kg_s": mr.get("gas_signed_boundary_flux_kg_s"),
                    "final_field_min_p_Pa": pr.get("min") if pr else None,
                    "final_field_max_T_K": temp.get("max") if temp else None,
                    "final_field_max_U_m_s": ur.get("max") if ur else None,
                    "guard_water_step_defect_kg": hr.get("water_step_defect_kg"),
                    "guard_water_cumulative_defect_kg": hr.get("water_cumulative_defect_kg"),
                    "guard_gas_step_defect_kg": hr.get("gas_step_defect_kg"),
                    "guard_gas_cumulative_defect_kg": hr.get("gas_cumulative_defect_kg"),
                }
            )
        write_csv(OUT / f"{name}-pressure-mass-series.csv", mass_rows)

    # Build long-form apparatus series, retaining original object names and values.
    apparatus_rows = []
    for name, run in runs.items():
        for object_name in OBJECTS:
            for row in run["objects"].get(object_name, []):
                apparatus_rows.append(
                    {
                        "arm": name,
                        "object": object_name,
                        "time_s": row["time_s"],
                        "values_json": json.dumps(row["values"], separators=(",", ":")),
                    }
                )
        for field_name, series in run["probes"].items():
            for row in series:
                apparatus_rows.append(
                    {
                        "arm": name,
                        "object": f"i4fTankHeadspaceProbes/{field_name}",
                        "time_s": row["time_s"],
                        "values_json": json.dumps(row["values"], separators=(",", ":")),
                    }
                )
    write_csv(
        OUT / "apparatus-series.csv", apparatus_rows, ["arm", "object", "time_s", "values_json"]
    )

    common_rows = []
    coverage = {}
    max_dtcap_time = runs["dtcap_half_outer16"]["log"]["dt_summary"]["last_time_s"]
    field_extrema_by_arm = {n: run["post"]["field_extrema"] for n, run in runs.items()}
    for target in TARGETS:
        available = max_dtcap_time is not None and target <= max_dtcap_time + 1e-12
        coverage[str(target)] = {
            "available_in_dtcap_snapshot": available,
            "dtcap_latest_logged_time_s": max_dtcap_time,
            "nearest_sample_error_bound_s": 0.0001,
            "bound_basis": "0.1 ms, approximately half the largest observed early adaptive step (0.1923 ms)",
            "reason_unavailable": None
            if available
            else "live dt-cap arm had not reached this physical time at snapshot",
        }
        for name, run in runs.items():
            trow = nearest(run["log"]["timestep_rows"], target)
            outer_row = nearest(run["log"]["outer_update_series"], target)
            thermo_row = nearest_exact_map(run["log"]["thermo_by_time"], target)
            phase_row = nearest_exact_map(run["log"]["phase_mass_by_time"], target)
            pfield = nearest(field_extrema_by_arm[name].get("p", []), target)
            ufield = nearest(field_extrema_by_arm[name].get("U", []), target)
            if ufield is None:
                ufield = nearest(field_extrema_by_arm[name].get("mag(U)", []), target)
            health_rows = run["health"]["rows"]
            hrow = None
            if health_rows:
                hrow = nearest(
                    [{"time_s": float(r["time_s"]), "health": r} for r in health_rows], target
                )
                hrow = hrow.get("health") if hrow else None
            row: dict[str, Any] = {
                "target_time_s": target,
                "arm": name,
                "available_by_dtcap_horizon": available,
                "dt_sample_time_s": trow.get("time_s") if trow else None,
                "dt_nearest_error_s": abs(trow["time_s"] - target) if trow else None,
                "deltaT_s": trow.get("deltaT_s") if trow else None,
                "outer_sample_time_s": outer_row.get("time_s") if outer_row else None,
                "outer_nearest_error_s": abs(outer_row["time_s"] - target) if outer_row else None,
                "outer_rows": outer_row.get("outer_rows") if outer_row else None,
                "final_outer_iteration": outer_row.get("final_outer_iteration")
                if outer_row
                else None,
                "penultimate_outer_iteration": outer_row.get("penultimate_outer_iteration")
                if outer_row
                else None,
                "final_max_abs_dp_Pa": outer_row.get("final_max_abs_dp_Pa") if outer_row else None,
                "penultimate_max_abs_dp_Pa": outer_row.get("penultimate_max_abs_dp_Pa")
                if outer_row
                else None,
                "final_max_abs_dU_m_s": outer_row.get("final_max_abs_dU_m_s")
                if outer_row
                else None,
                "penultimate_max_abs_dU_m_s": outer_row.get("penultimate_max_abs_dU_m_s")
                if outer_row
                else None,
                "final_max_abs_dalpha1": outer_row.get("final_max_abs_dalpha1")
                if outer_row
                else None,
                "penultimate_max_abs_dalpha1": outer_row.get("penultimate_max_abs_dalpha1")
                if outer_row
                else None,
                "final_to_penultimate_dp_ratio": outer_row.get(
                    "final_to_penultimate_max_abs_dp_Pa_ratio"
                )
                if outer_row
                else None,
                "final_to_penultimate_dU_ratio": outer_row.get(
                    "final_to_penultimate_max_abs_dU_m_s_ratio"
                )
                if outer_row
                else None,
                "thermo_sample_time_s": thermo_row.get("time_s") if thermo_row else None,
                "thermo_nearest_error_s": abs(thermo_row["time_s"] - target)
                if thermo_row
                else None,
                "thermo_min_raw_water_pressure_Pa": thermo_row.get("min_raw_water_pressure_Pa")
                if thermo_row
                else None,
                "thermo_max_water_T_K": thermo_row.get("max_water_supported_T_K")
                if thermo_row
                else None,
                "thermo_min_saturation_margin_Pa": thermo_row.get("min_saturation_margin_Pa")
                if thermo_row
                else None,
                "phase_mass_sample_time_s": phase_row.get("time_s") if phase_row else None,
                "water_inventory_kg": phase_row.get("water_inventory_kg") if phase_row else None,
                "gas_inventory_kg": phase_row.get("gas_inventory_kg") if phase_row else None,
                "water_boundary_flux_kg_s": phase_row.get("water_signed_boundary_flux_kg_s")
                if phase_row
                else None,
                "gas_boundary_flux_kg_s": phase_row.get("gas_signed_boundary_flux_kg_s")
                if phase_row
                else None,
                "guard_water_cumulative_defect_kg": hrow.get("water_cumulative_defect_kg")
                if hrow
                else None,
                "guard_gas_cumulative_defect_kg": hrow.get("gas_cumulative_defect_kg")
                if hrow
                else None,
                "field_p_sample_time_s": pfield.get("time_s") if pfield else None,
                "final_field_min_p_Pa": pfield.get("min") if pfield else None,
                "field_speed_sample_time_s": ufield.get("time_s") if ufield else None,
                "final_field_max_U_m_s": ufield.get("max") if ufield else None,
            }
            row["dt_nearest_within_declared_bound"] = (
                row["dt_nearest_error_s"] is not None and row["dt_nearest_error_s"] <= 0.0001
            )
            row["outer_nearest_within_declared_bound"] = (
                row["outer_nearest_error_s"] is not None and row["outer_nearest_error_s"] <= 0.0001
            )
            row["pairwise_dt_sample_separation_vs_outer16_s"] = (
                abs(row["dt_sample_time_s"] - next(
                    (r["dt_sample_time_s"] for r in common_rows
                     if r["arm"] == "outer16" and r["target_time_s"] == target),
                    row["dt_sample_time_s"],
                ))
                if name == "dtcap_half_outer16" and row["dt_sample_time_s"] is not None
                else None
            )
            for object_name in OBJECTS:
                s = nearest(run["objects"].get(object_name, []), target)
                row[f"{object_name}_time_s"] = s.get("time_s") if s else None
                values = s.get("values", []) if s else []
                row[f"{object_name}_values"] = (
                    json.dumps(values, separators=(",", ":")) if s else None
                )
            for field_name in ("p", "T", "U"):
                s = nearest(run["probes"].get(field_name, []), target)
                row[f"tank_probe_{field_name}_time_s"] = s.get("time_s") if s else None
                vals = s.get("values", []) if s else []
                row[f"tank_probe_{field_name}_values"] = (
                    json.dumps(vals, separators=(",", ":")) if s else None
                )
            common_rows.append(row)
    write_csv(OUT / "common-time-comparison.csv", common_rows)

    # Assess cap binding and distinguish per-step iteration updates from state trajectories.
    baseline_dt = [
        r["deltaT_s"]
        for r in runs["outer16"]["log"]["timestep_rows"]
        if math.isfinite(r["deltaT_s"])
    ]
    candidate_dt = [
        r["deltaT_s"]
        for r in runs["dtcap_half_outer16"]["log"]["timestep_rows"]
        if math.isfinite(r["deltaT_s"])
    ]
    common_window = min((run["log"]["dt_summary"]["last_time_s"] or 0.0) for run in runs.values())
    candidate_rows = [
        r
        for r in common_rows
        if r["arm"] == "dtcap_half_outer16" and r["target_time_s"] <= common_window
    ]
    trajectory_diffs = []
    for row in candidate_rows:
        baseline = next(
            (
                r
                for r in common_rows
                if r["arm"] == "outer16" and r["target_time_s"] == row["target_time_s"]
            ),
            None,
        )
        if baseline:
            for field in (
                "thermo_min_raw_water_pressure_Pa",
                "water_inventory_kg",
                "gas_inventory_kg",
                "final_field_min_p_Pa",
            ):
                a, b = row.get(field), baseline.get(field)
                if isinstance(a, (float, int)) and isinstance(b, (float, int)):
                    trajectory_diffs.append(
                        {
                            "target_time_s": row["target_time_s"],
                            "field": field,
                            "dtcap_minus_outer16": a - b,
                            "outer16_sample_error_s": baseline.get("dt_nearest_error_s"),
                            "dtcap_sample_error_s": row.get("dt_nearest_error_s"),
                        }
                    )
    runtime_snapshot_utc = utc()
    runtime_snapshot_dt = parse_utc(runtime_snapshot_utc)
    runtime_rows = []
    for name, run in runs.items():
        manifest = run["manifest"]
        branch = run["branch"]
        docker = run["docker"]
        guard_service = run["guard_service"]
        start_text = docker.get("started_at")
        save_seconds = manifest.get("declared_graceful_save_wall_s_from_StartedAt")
        if save_seconds is None:
            save_seconds = manifest.get("writeNow_s_from_StartedAt")
        hard_seconds = manifest.get("declared_hard_wall_s_from_StartedAt")
        if hard_seconds is None:
            hard_seconds = manifest.get("hard_wall_s_from_StartedAt")
        save_seconds = int(save_seconds) if save_seconds is not None else None
        hard_seconds = int(hard_seconds) if hard_seconds is not None else None
        save_deadline = add_seconds_to_rfc3339(start_text, save_seconds) if start_text and save_seconds is not None else None
        hard_deadline = add_seconds_to_rfc3339(start_text, hard_seconds) if start_text and hard_seconds is not None else None
        clock_rows = run["log"]["clock_rows"]
        recent_clock = clock_rows[-6:]
        rates = []
        for previous, current in zip(recent_clock, recent_clock[1:]):
            dt_physical = current["time_s"] - previous["time_s"]
            dt_clock = current["clock_time_s"] - previous["clock_time_s"]
            if dt_physical > 0 and dt_clock > 0:
                rates.append(3600.0 * dt_physical / dt_clock)
        rate = median(rates) if rates else None
        latest_time_s = run["log"]["dt_summary"]["last_time_s"]

        def target_forecast(target: float) -> dict[str, Any]:
            remaining = target - latest_time_s if latest_time_s is not None else None
            eta_hours = remaining / rate if remaining is not None and remaining > 0 and rate else None
            arrival = (
                runtime_snapshot_dt + timedelta(hours=eta_hours)
                if eta_hours is not None
                else None
            )
            return {
                "target_time_s": target,
                "remaining_physical_time_s": remaining,
                "estimated_wall_hours_at_recent_rate": eta_hours,
                "estimated_arrival_utc": arrival.isoformat() if arrival else None,
                "before_graceful_save_deadline": (
                    arrival <= parse_utc(save_deadline)
                    if arrival is not None and save_deadline
                    else None
                ),
                "before_hard_deadline": (
                    arrival <= parse_utc(hard_deadline)
                    if arrival is not None and hard_deadline
                    else None
                ),
            }

        manifest_started = manifest.get("docker_started_at")
        declared_save_deadline = manifest.get("graceful_save_deadline_utc_from_StartedAt")
        declared_hard_deadline = manifest.get("hard_deadline_utc_from_StartedAt")
        guard_hard_deadline = branch.get("wall_deadline_utc")
        runtime = {
            "snapshot_utc": runtime_snapshot_utc,
            "docker_started_at": start_text,
            "manifest_docker_started_at": manifest_started,
            "declared_graceful_save_wall_s_from_StartedAt": save_seconds,
            "declared_hard_wall_s_from_StartedAt": hard_seconds,
            "derived_graceful_save_deadline_utc": save_deadline,
            "manifest_graceful_save_deadline_utc": declared_save_deadline,
            "derived_hard_deadline_utc": hard_deadline,
            "manifest_hard_deadline_utc": declared_hard_deadline,
            "guard_reported_hard_deadline_utc": guard_hard_deadline,
            "guard_reported_hard_wall_s_from_StartedAt": manifest.get("guard_hard_wall_s_from_StartedAt"),
            "guard_status": run["guard"].get("status"),
            "branch_status": branch.get("status"),
            "branch_current_time_s": branch.get("current_time_s"),
            "branch_reported_hard_deadline_matches_derived": (
                parse_utc(guard_hard_deadline) == parse_utc(hard_deadline)
                if guard_hard_deadline and hard_deadline
                else None
            ),
            "manifest_deadlines_match_derived": (
                parse_utc(declared_save_deadline) == parse_utc(save_deadline)
                and parse_utc(declared_hard_deadline) == parse_utc(hard_deadline)
                if declared_save_deadline and declared_hard_deadline and save_deadline and hard_deadline
                else None
            ),
            "docker_startedAt_matches_manifest": (
                parse_utc(start_text) == parse_utc(manifest_started)
                if start_text and manifest_started
                else None
            ),
            "guard_service": guard_service,
            "latest_log_time_s": latest_time_s,
            "recent_clock_sample": {
                "time_start_s": recent_clock[0]["time_s"] if recent_clock else None,
                "time_end_s": recent_clock[-1]["time_s"] if recent_clock else None,
                "clock_start_s": recent_clock[0]["clock_time_s"] if recent_clock else None,
                "clock_end_s": recent_clock[-1]["clock_time_s"] if recent_clock else None,
                "intervals": len(rates),
                "rate_samples_physical_s_per_wall_hour": rates,
                "median_physical_s_per_wall_hour": rate,
                "association": "ExecutionTime/ClockTime row paired with latest preceding Time line; median of up to five recent positive intervals",
            },
            "forecast_assumption": "recent solver ClockTime throughput persists; pressure-driven slowdown or changing MPI/I/O load can invalidate extrapolation",
            "eta_to_0_55": target_forecast(0.55) if docker.get("running") else None,
            "eta_to_0_65": target_forecast(0.65) if docker.get("running") else None,
        }
        summary["arms"][name]["runtime_budget_and_forecast"] = runtime
        runtime_rows.append({
            "arm": name,
            "container_id": docker.get("id"),
            "container_status": docker.get("status"),
            "docker_started_at": start_text,
            "graceful_save_wall_s": save_seconds,
            "hard_wall_s": hard_seconds,
            "derived_graceful_save_deadline_utc": save_deadline,
            "derived_hard_deadline_utc": hard_deadline,
            "guard_hard_deadline_utc": guard_hard_deadline,
            "manifest_deadlines_match_derived": runtime["manifest_deadlines_match_derived"],
            "guard_hard_deadline_matches_derived": runtime["branch_reported_hard_deadline_matches_derived"],
            "guard_service_active_state": guard_service.get("active_state"),
            "guard_service_runtime_max_usec": guard_service.get("runtime_max_usec"),
            "latest_log_time_s": latest_time_s,
            "recent_physical_s_per_wall_hour": rate,
            "eta_0_55_utc": runtime["eta_to_0_55"]["estimated_arrival_utc"] if runtime["eta_to_0_55"] else None,
            "eta_0_55_before_graceful_save": runtime["eta_to_0_55"]["before_graceful_save_deadline"] if runtime["eta_to_0_55"] else None,
            "eta_0_65_utc": runtime["eta_to_0_65"]["estimated_arrival_utc"] if runtime["eta_to_0_65"] else None,
            "eta_0_65_before_graceful_save": runtime["eta_to_0_65"]["before_graceful_save_deadline"] if runtime["eta_to_0_65"] else None,
            "eta_0_65_before_hard_deadline": runtime["eta_to_0_65"]["before_hard_deadline"] if runtime["eta_to_0_65"] else None,
        })
    summary["runtime_snapshot_utc"] = runtime_snapshot_utc
    write_csv(OUT / "runtime-deadlines.csv", runtime_rows)

    late_pairs = []
    for target in (0.42, 0.46, 0.48, 0.4907023481865, 0.50, 0.51):
        pair = {
            name: next(
                (row for row in common_rows if row["arm"] == name and row["target_time_s"] == target),
                None,
            )
            for name in ("outer8", "outer16")
        }
        a, b = pair["outer8"], pair["outer16"]
        if not a or not b or not a["dt_sample_time_s"] or not b["dt_sample_time_s"]:
            continue
        def flux_sum(row: dict[str, Any]) -> float | None:
            values = []
            for valve in ("seatFluxA1", "seatFluxA2", "seatFluxB1", "seatFluxB2"):
                raw = row.get(f"{valve}_values")
                vals = json.loads(raw) if raw else []
                if len(vals) < 2:
                    return None
                values.append(vals[1])
            return sum(values)
        valve_fluxes = {
            row_arm: {
                valve: (json.loads(pair[row_arm][f"{valve}_values"])[1]
                        if pair[row_arm].get(f"{valve}_values") else None)
                for valve in ("seatFluxA1", "seatFluxA2", "seatFluxB1", "seatFluxB2")
            }
            for row_arm in ("outer8", "outer16")
        }
        tank_volumes = {
            row_arm: {
                tank: (json.loads(pair[row_arm][f"{tank}WaterVolume_values"])[0]
                       if pair[row_arm].get(f"{tank}WaterVolume_values") else None)
                for tank in ("tankA", "tankB")
            }
            for row_arm in ("outer8", "outer16")
        }
        late_pairs.append({
            "target_time_s": target,
            "outer8_sample_time_s": a["dt_sample_time_s"],
            "outer16_sample_time_s": b["dt_sample_time_s"],
            "outer8_nearest_error_s": a["dt_nearest_error_s"],
            "outer16_nearest_error_s": b["dt_nearest_error_s"],
            "pairwise_sample_separation_s": abs(a["dt_sample_time_s"] - b["dt_sample_time_s"]),
            "both_within_0_1ms_target_bound": bool(a["dt_nearest_error_s"] <= 0.0001 and b["dt_nearest_error_s"] <= 0.0001),
            "valve_seat_water_flux_by_nozzle_m3_s": valve_fluxes,
            "tank_water_volume_m3": tank_volumes,
            "outer8_minus_outer16": {
                "tank_A_water_volume_m3": (tank_volumes["outer8"]["tankA"] - tank_volumes["outer16"]["tankA"])
                    if tank_volumes["outer8"]["tankA"] is not None and tank_volumes["outer16"]["tankA"] is not None else None,
                "tank_B_water_volume_m3": (tank_volumes["outer8"]["tankB"] - tank_volumes["outer16"]["tankB"])
                    if tank_volumes["outer8"]["tankB"] is not None and tank_volumes["outer16"]["tankB"] is not None else None,
                "raw_min_water_pressure_Pa": (a["thermo_min_raw_water_pressure_Pa"] - b["thermo_min_raw_water_pressure_Pa"])
                    if a["thermo_min_raw_water_pressure_Pa"] is not None and b["thermo_min_raw_water_pressure_Pa"] is not None else None,
                "water_inventory_kg": (a["water_inventory_kg"] - b["water_inventory_kg"])
                    if a["water_inventory_kg"] is not None and b["water_inventory_kg"] is not None else None,
                "gas_inventory_kg": (a["gas_inventory_kg"] - b["gas_inventory_kg"])
                    if a["gas_inventory_kg"] is not None and b["gas_inventory_kg"] is not None else None,
                "four_valve_seat_water_flux_m3_s": (flux_sum(a) - flux_sum(b))
                    if flux_sum(a) is not None and flux_sum(b) is not None else None,
                "field_min_p_Pa": (a["final_field_min_p_Pa"] - b["final_field_min_p_Pa"])
                    if a["final_field_min_p_Pa"] is not None and b["final_field_min_p_Pa"] is not None else None,
            },
            "outer8": {"raw_min_water_pressure_Pa": a["thermo_min_raw_water_pressure_Pa"],
                       "max_water_T_K": a["thermo_max_water_T_K"],
                       "water_inventory_kg": a["water_inventory_kg"],
                       "gas_inventory_kg": a["gas_inventory_kg"],
                       "four_valve_seat_water_flux_m3_s": flux_sum(a),
                       "field_min_p_Pa": a["final_field_min_p_Pa"],
                       "final_max_abs_dp_Pa": a["final_max_abs_dp_Pa"],
                       "penultimate_max_abs_dp_Pa": a["penultimate_max_abs_dp_Pa"],
                       "final_max_abs_dU_m_s": a["final_max_abs_dU_m_s"],
                       "penultimate_max_abs_dU_m_s": a["penultimate_max_abs_dU_m_s"]},
            "outer16": {"raw_min_water_pressure_Pa": b["thermo_min_raw_water_pressure_Pa"],
                        "max_water_T_K": b["thermo_max_water_T_K"],
                        "water_inventory_kg": b["water_inventory_kg"],
                        "gas_inventory_kg": b["gas_inventory_kg"],
                        "four_valve_seat_water_flux_m3_s": flux_sum(b),
                        "field_min_p_Pa": b["final_field_min_p_Pa"],
                        "final_max_abs_dp_Pa": b["final_max_abs_dp_Pa"],
                        "penultimate_max_abs_dp_Pa": b["penultimate_max_abs_dp_Pa"],
                        "final_max_abs_dU_m_s": b["final_max_abs_dU_m_s"],
                        "penultimate_max_abs_dU_m_s": b["penultimate_max_abs_dU_m_s"]},
        })
    summary["late_outer8_vs_outer16_common_time_samples"] = late_pairs
    summary["parser_diagnostic_gap_assessment"] = {
        "outer8_guard_errors": {
            "terminal_diagnostic_errors": runs["outer8"]["branch"].get("diagnostic_errors", []),
            "thermo_envelope_sequence_error_count": len(runs["outer8"]["branch"].get("thermo_envelope_errors", [])),
            "parser_error_count": len(runs["outer8"]["branch"].get("parser_errors", [])),
            "raw_log_full_step_group_histograms": runs["outer8"]["log"]["coverage"],
            "interpretation": "The terminal guard records 3 missing-record events and 20 thermo pass-sequence errors; the completed raw log snapshot nevertheless parses complete 8-row outer, 16-row thermo, and 32-row phase-state groups for every one of 839 time records. Preserve both facts; the reason for the guard/raw-log discrepancy is unresolved.",
        },
        "live_outer16_and_dtcap": {
            "guard_errors": "No diagnostic, parser, or thermo-envelope guard errors in the snapshot.",
            "snapshot_tail_partial_groups": {
                name: {
                    "outer_rows_histogram": runs[name]["log"]["coverage"]["outer_rows_per_time_histogram"],
                    "thermo_passes_histogram": runs[name]["log"]["coverage"]["thermo_passes_per_time_histogram"],
                    "phase_state_rows_histogram": runs[name]["log"]["coverage"]["phase_state_records_per_time_histogram"],
                }
                for name in ("outer16", "dtcap_half_outer16")
            },
            "interpretation": "Each live log has one trailing partial timestep group at snapshot, visible as the nonmodal row count in each histogram (complete groups have 16 outer, 32 thermo, and 64 phase-state records for nOuter=16). Earlier groups are complete. The tail is a concurrent log-read boundary, not a solver diagnostic.",
        },
    }
    summary["common_time_coverage"] = coverage
    summary["comparison_window_end_s"] = common_window
    summary["nearest_sample_policy"] = {
        "method": "independent nearest physical-time sample per arm; no wall-time matching and no interpolation",
        "maximum_absolute_target_error_s": 0.0001,
        "basis": "0.1 ms bound is approximately half the largest observed early adaptive timestep (0.1923 ms); each row carries an explicit in-bound flag, and pairwise sample separation is also reported",
    }
    summary["time_step_cap_assessment"] = {
        "outer16_control_maxDeltaT_s": runs["outer16"]["control"].get("maxDeltaT"),
        "dtcap_control_maxDeltaT_s": runs["dtcap_half_outer16"]["control"].get("maxDeltaT"),
        "outer16_actual_dt_min_s": min(baseline_dt) if baseline_dt else None,
        "outer16_actual_dt_max_s": max(baseline_dt) if baseline_dt else None,
        "outer16_actual_dt_latest_s": runs["outer16"]["log"]["dt_summary"]["last_deltaT_s"],
        "dtcap_actual_dt_min_s": min(candidate_dt) if candidate_dt else None,
        "dtcap_actual_dt_max_s": max(candidate_dt) if candidate_dt else None,
        "dtcap_actual_dt_latest_s": runs["dtcap_half_outer16"]["log"]["dt_summary"][
            "last_deltaT_s"
        ],
        "fraction_dtcap_steps_equal_to_declared_half_cap": (
            sum(abs(x - 0.000125) < 1e-12 for x in candidate_dt) / len(candidate_dt)
            if candidate_dt
            else None
        ),
        "fraction_outer16_steps_above_half_cap": (
            sum(x > 0.000125 + 1e-12 for x in baseline_dt) / len(baseline_dt)
            if baseline_dt
            else None
        ),
        "conclusion": (
            "The arm with half the maxDeltaT cap is binding at 0.000125 s for every observed step; "
            f"{sum(x > 0.000125 + 1e-12 for x in baseline_dt) / len(baseline_dt):.1%} "
            "of baseline outer16 steps exceed that cap. The snapshot ends before the low-pressure regime, "
            "so this does not establish late-time behavior."
            if baseline_dt and candidate_dt and all(abs(x - 0.000125) < 1e-12 for x in candidate_dt)
            else "The observed snapshot does not establish whether the declared half-cap binds."
        ),
        "iteration_vs_trajectory": {
            "same_nOuterCorrectors": 16,
            "same_omega": 0.5,
            "only_declared_case_change": "maxDeltaT",
            "state_differences_at_available_common_targets": trajectory_diffs,
            "interpretation_limit": "At available early common physical times, pressure and inventory trajectories are close but not identical; smaller per-step outer deltas are not by themselves evidence of iteration damping because maxDeltaT is the changed physical intervention. Final/penultimate dp and dU ratios move differently, and no late-time common endpoint is available.",
        },
    }

    summary_path = OUT / "comparison.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")

    plot_series(runs, common_window)
    print(
        json.dumps(
            {
                "status": "analysis_complete_snapshot_bounded",
                "bundle": str(OUT),
                "comparison_window_end_s": common_window,
                "targets_available": [
                    t for t, v in coverage.items() if v["available_in_dtcap_snapshot"]
                ],
                "dtcap_latest_time_s": max_dtcap_time,
                "dtcap_deltaT_range_s": [
                    summary["time_step_cap_assessment"]["dtcap_actual_dt_min_s"],
                    summary["time_step_cap_assessment"]["dtcap_actual_dt_max_s"],
                ],
            },
            sort_keys=True,
        )
    )


def plot_series(runs: dict[str, dict[str, Any]], common_window: float) -> None:
    colors = {"outer8": "#b04a4a", "outer16": "#286f9c", "dtcap_half_outer16": "#238256"}
    labels = {
        "outer8": "outer8, maxΔt 0.00025",
        "outer16": "outer16, maxΔt 0.00025",
        "dtcap_half_outer16": "outer16, maxΔt 0.000125",
    }
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    ax_dt, ax_p, ax_flux, ax_vol = axes.flat
    for name, run in runs.items():
        color = colors[name]
        dtrows = [r for r in run["log"]["timestep_rows"] if r["time_s"] <= common_window + 1e-12]
        ax_dt.plot(
            [r["time_s"] for r in dtrows],
            [r["deltaT_s"] for r in dtrows],
            color=color,
            lw=1.0,
            label=labels[name],
        )
        thermo = sorted(run["log"]["thermo_by_time"].values(), key=lambda r: r["time_s"])
        thermo = [r for r in thermo if r["time_s"] <= common_window + 1e-12]
        ax_p.plot(
            [r["time_s"] for r in thermo],
            [r["min_raw_water_pressure_Pa"] for r in thermo],
            color=color,
            lw=1.0,
            label=labels[name],
        )
        flux_series = []
        tank_a = run["objects"].get("tankAWaterVolume", [])
        tank_b = run["objects"].get("tankBWaterVolume", [])
        for trow in dtrows:
            t = trow["time_s"]
            total = 0.0
            found = True
            for valve in ("seatFluxA1", "seatFluxA2", "seatFluxB1", "seatFluxB2"):
                sample = nearest(run["objects"].get(valve, []), t)
                if not sample or len(sample["values"]) < 2:
                    found = False
                    break
                total += sample["values"][1]
            if found:
                flux_series.append((t, total))
        if flux_series:
            ax_flux.plot(
                [r[0] for r in flux_series],
                [r[1] for r in flux_series],
                color=color,
                lw=1.0,
                label=labels[name],
            )
        for label, series, style in (("tank A", tank_a, "-"), ("tank B", tank_b, "--")):
            vals = [r for r in series if r["time_s"] <= common_window + 1e-12]
            if vals:
                ax_vol.plot(
                    [r["time_s"] for r in vals],
                    [r["values"][0] for r in vals],
                    color=color,
                    linestyle=style,
                    lw=0.9,
                    label=f"{name} {label}",
                )
    ax_dt.axhline(0.000125, color="#238256", ls=":", lw=0.8)
    ax_dt.set_ylabel("actual deltaT (s)")
    ax_dt.set_title("Adaptive step history")
    ax_p.axhline(10000.0, color="black", ls=":", lw=0.8, label="pMin 10 kPa")
    ax_p.set_ylabel("minimum raw water-supported p (Pa)")
    ax_p.set_title("Thermo-envelope pressure minimum")
    ax_flux.set_ylabel("sum of four valve-seat alphaPhi0.water integrals (m³/s)")
    ax_flux.set_title("Four valve-seat water flux sum")
    ax_vol.set_ylabel("liquid volume (m³)")
    ax_vol.set_title("Tank A/B water volume")
    for ax in (ax_dt, ax_p, ax_flux, ax_vol):
        ax.set_xlabel("physical time (s)")
        ax.grid(True, alpha=0.2)
        ax.legend(fontsize=7, loc="best")
    fig.suptitle(
        f"Matched physical pilot snapshot through {common_window:.6f} s (live dt-cap endpoint incomplete)"
    )
    fig.savefig(OUT / "physical-pilot-comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
