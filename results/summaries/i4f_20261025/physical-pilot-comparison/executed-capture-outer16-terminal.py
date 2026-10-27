#!/usr/bin/env python3
"""Freeze the completed outer16 terminal evidence beside the earlier live snapshot."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "outer16-terminal-addendum-20261027T050412Z.json"
ARM = ROOT / "results/runs/i4f-physical-alpha-flux-relax-candidate-20261027T024711Z/arms/physical-omega-050-outer-pair/outer16"
ATTEMPT = ARM / "attempts/attempt-007-readiness-marker-retry"
MANIFEST_PATH = ATTEMPT / "launch-manifest.json"
GUARD_PATH = ATTEMPT / "guardian-status.json"
LOG = ARM / "case/log.cold-coupled"
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TOKEN = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
FIELD_ROW = re.compile(
    r"^\s*([-+\d.eE]+)\s+(\S+)\s+([-+\d.eE]+)\s+\(([^)]+)\)\s+\d+\s+([-+\d.eE]+)\s+\(([^)]+)\)\s+\d+"
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    before = path.stat().st_size
    digest = sha256(path)
    after = path.stat().st_size
    if before != after:
        raise RuntimeError(f"file changed during snapshot: {path}")
    return {"path": str(path.relative_to(ROOT)), "bytes": after, "sha256": digest}


def scan_log() -> dict[str, Any]:
    before = LOG.stat().st_size
    outer: dict[float, list[dict[str, Any]]] = defaultdict(list)
    thermo: dict[float, dict[str, Any]] = {}
    floor_passes: list[dict[str, Any]] = []
    phase: dict[float, dict[str, Any]] = {}
    latest_time: float | None = None
    latest_dt: float | None = None
    terminal_requests: list[dict[str, Any]] = []
    with LOG.open("rb") as stream:
        for raw in stream:
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("Time ="):
                try:
                    latest_time = float(line.split("=", 1)[1])
                except ValueError:
                    pass
            elif line.startswith("deltaT ="):
                try:
                    latest_dt = float(line.split("=", 1)[1])
                except ValueError:
                    pass
            if "I4F_TERMINAL_CHECKPOINT_REQUEST" in line:
                terminal_requests.append(dict(TOKEN.findall(line)))
            if "I4F_OUTER_STATE_DELTA" in line:
                kv = dict(TOKEN.findall(line))
                try:
                    t = float(kv["time_s"])
                except (KeyError, ValueError):
                    continue
                row: dict[str, Any] = {"time_s": t}
                for key in ("outer_iteration", "max_abs_dp_Pa", "max_abs_dU_m_s", "max_abs_dphi_m3_s", "max_abs_dalpha1"):
                    try:
                        row[key] = float(kv[key])
                    except (KeyError, ValueError):
                        row[key] = None
                outer[t].append(row)
            if "I4F_THERMO_ENVELOPE" in line:
                kv = dict(TOKEN.findall(line))
                try:
                    t = float(kv["time_s"])
                    pmin = float(kv["min_raw_p_water_Pa"])
                except (KeyError, ValueError):
                    continue
                row = thermo.setdefault(t, {"time_s": t, "passes": 0, "min_raw_water_pressure_Pa": float("inf")})
                row["passes"] += 1
                row["min_raw_water_pressure_Pa"] = min(row["min_raw_water_pressure_Pa"], pmin)
                for key, output in (("max_T_water_supported_K", "max_water_supported_T_K"), ("saturation_margin_Pa", "min_saturation_margin_Pa")):
                    try:
                        value = float(kv[key])
                    except (KeyError, ValueError):
                        continue
                    if output not in row:
                        row[output] = value
                    elif output == "max_water_supported_T_K":
                        row[output] = max(row[output], value)
                    else:
                        row[output] = min(row[output], value)
                if pmin < 10000.0:
                    floor_passes.append({
                        "time_s": t,
                        "outer_iteration": kv.get("outer"),
                        "pass": kv.get("pass"),
                        "min_raw_water_pressure_Pa": pmin,
                        "max_water_supported_T_K": row.get("max_water_supported_T_K"),
                        "saturation_margin_Pa": row.get("min_saturation_margin_Pa"),
                    })
            if "I4F_PHASE_MASS_STATE" in line:
                kv = dict(TOKEN.findall(line))
                if kv.get("stage") != "after_correctRho":
                    continue
                try:
                    t = float(kv["time_s"])
                except (KeyError, ValueError):
                    continue
                prior = phase.get(t)
                try:
                    pass_id = float(kv.get("pass", "-1"))
                except ValueError:
                    pass_id = -1.0
                if prior is None or pass_id >= prior["pass"]:
                    row = {"time_s": t, "pass": pass_id}
                    for key in ("water_inventory_kg", "gas_inventory_kg", "water_signed_boundary_flux_kg_s", "gas_signed_boundary_flux_kg_s"):
                        try:
                            row[key] = float(kv[key])
                        except (KeyError, ValueError):
                            row[key] = None
                    phase[t] = row
    after = LOG.stat().st_size
    if before != after:
        raise RuntimeError("terminal log changed during snapshot")
    last_times = sorted(thermo)
    last_time = last_times[-1] if last_times else None
    updates = []
    if outer:
        last_time_outer = max(outer)
        updates = sorted(outer[last_time_outer], key=lambda row: row["outer_iteration"] or -1)
    return {
        "path": str(LOG.relative_to(ROOT)),
        "bytes": after,
        "sha256": sha256(LOG),
        "last_Time_line_s": latest_time,
        "last_deltaT_line_s": latest_dt,
        "last_thermo_time_s": last_time,
        "last_thermo_state": thermo[last_time] if last_time is not None else None,
        "global_raw_pressure_minimum": min(thermo.values(), key=lambda row: row["min_raw_water_pressure_Pa"], default=None),
        "first_sub_10kPa_pass": floor_passes[0] if floor_passes else None,
        "sub_10kPa_pass_count": len(floor_passes),
        "final_time_outer_updates": updates,
        "final_time_phase_mass": phase.get(last_time),
        "terminal_checkpoint_requests": terminal_requests,
    }


def latest_numeric_row(path: Path) -> dict[str, Any] | None:
    header = None
    last = None
    with path.open(errors="replace") as stream:
        for line in stream:
            text = line.strip()
            if text.startswith("#"):
                if "Time" in text:
                    header = text[1:].strip()
                continue
            values = [float(value) for value in NUMBER.findall(text)]
            if values and all(abs(value) < float("inf") for value in values):
                last = {"values": values, "header": header}
    if last is None:
        return None
    return last


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    guard = json.loads(GUARD_PATH.read_text())
    branch = guard.get("branches", {}).get("fourmouth_coldstart", {})
    identity = manifest["container_id"]
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .}}", "--type", "container", identity],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    container_raw = json.loads(inspected.stdout)
    state = container_raw.get("State", {})
    container = {
        "id": container_raw.get("Id"),
        "name": container_raw.get("Name", "").lstrip("/"),
        "status": state.get("Status"),
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "oom_killed": state.get("OOMKilled"),
        "log_driver": container_raw.get("HostConfig", {}).get("LogConfig", {}).get("Type"),
    }
    proc_root = ARM / "case/processors10"
    native_times = sorted(
        ((float(path.name), path) for path in proc_root.iterdir() if path.is_dir() and path.name[:1].isdigit()),
        key=lambda pair: pair[0],
    )
    terminal_time, terminal_dir = native_times[-1]
    endpoint_files = [file_record(path) for path in sorted(terminal_dir.rglob("*")) if path.is_file()]
    post_root = ARM / "case/postProcessing"
    post_files = []
    latest_outputs = {}
    wanted = {"seatFluxA1", "seatFluxA2", "seatFluxB1", "seatFluxB2", "seatPressureA1", "seatPressureA2", "seatPressureB1", "seatPressureB2", "tankAWaterVolume", "tankBWaterVolume", "totalWaterVolume"}
    for path in sorted(post_root.rglob("*.dat")):
        record = file_record(path)
        post_files.append(record)
        rel = path.relative_to(post_root)
        object_name = rel.parts[0]
        if object_name in wanted:
            latest_outputs.setdefault(object_name, []).append({**latest_numeric_row(path), "path": str(rel)})
    latest_outputs = {
        name: max(rows, key=lambda row: row["values"][0])
        for name, rows in latest_outputs.items()
        if rows
    }
    field_extrema: dict[str, dict[str, Any]] = {}
    for path in sorted(post_root.rglob("fieldMinMax.dat")):
        with path.open(errors="replace") as stream:
            for line in stream:
                match = FIELD_ROW.match(line)
                if not match:
                    continue
                time_s = float(match.group(1))
                field = match.group(2)
                row = {
                    "time_s": time_s,
                    "field": field,
                    "min": float(match.group(3)),
                    "min_location": [float(value) for value in NUMBER.findall(match.group(4))],
                    "max": float(match.group(5)),
                    "max_location": [float(value) for value in NUMBER.findall(match.group(6))],
                    "source_file": str(path.relative_to(ROOT)),
                }
                if field not in field_extrema or time_s >= field_extrema[field]["time_s"]:
                    field_extrema[field] = row
    input_paths = [
        MANIFEST_PATH,
        GUARD_PATH,
        ARM / "case/system/controlDict",
        ARM / "case/system/fvSolution",
        ARM / "case/system/fvSchemes",
        ARM / "case/system/finalStepCheckpoint",
        ARM / "case/constant/thermophysicalProperties.air",
        ARM / "case/constant/thermophysicalProperties.water",
    ]
    step_health = ATTEMPT / "step_health.csv"
    if step_health.is_file():
        input_paths.append(step_health)
    data = {
        "schema": "i4f-physical-pilot-terminal-arm-addendum/v1",
        "captured_utc": utc(),
        "preserves_prior_snapshot": str((OUT.parent / "comparison.json").relative_to(ROOT)),
        "prior_snapshot_sha256": sha256(OUT.parent / "comparison.json"),
        "arm": str(ARM.relative_to(ROOT)),
        "attempt": str(ATTEMPT.relative_to(ROOT)),
        "container": container,
        "guard": {
            "status": guard.get("status"),
            "branch_status": branch.get("status"),
            "write_now_reason": branch.get("write_now_reason"),
            "current_time_s": branch.get("current_time_s"),
            "completed_steps": branch.get("completed_steps"),
            "diagnostic_error_count": len(branch.get("diagnostic_errors", [])),
            "parser_error_count": len(branch.get("parser_errors", [])),
            "thermo_envelope_error_count": len(branch.get("thermo_envelope_errors", [])),
            "last_step_health": branch.get("last_step_health"),
            "terminal_capture": branch.get("terminal_capture"),
        },
        "manifest_sha256": sha256(MANIFEST_PATH),
        "guard_manifest_sha256": sha256(GUARD_PATH),
        "binary_sha256": manifest.get("binary_sha256"),
        "image": manifest.get("image"),
        "native_checkpoint_times_s": [time for time, _ in native_times],
        "terminal_native_checkpoint": {
            "time_s": terminal_time,
            "path": str(terminal_dir.relative_to(ROOT)),
            "file_count": len(endpoint_files),
            "files": endpoint_files,
        },
        "raw_log": scan_log(),
        "latest_apparatus_outputs": latest_outputs,
        "latest_field_extrema": field_extrema,
        "postprocessing_files": post_files,
        "postprocessing_file_count": len(post_files),
        "control_and_runtime_hashes": [file_record(path) for path in input_paths],
    }
    payload = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with OUT.open("x") as stream:
        stream.write(payload)
    print(json.dumps({
        "status": data["guard"]["branch_status"],
        "container_status": container["status"],
        "terminal_time_s": terminal_time,
        "raw_log_sha256": data["raw_log"]["sha256"],
        "native_file_count": len(endpoint_files),
        "addendum": str(OUT.relative_to(ROOT)),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
