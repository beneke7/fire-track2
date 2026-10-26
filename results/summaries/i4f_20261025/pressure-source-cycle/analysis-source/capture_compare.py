#!/usr/bin/env python3
"""Capture bounded I4F log prefixes and compare standard/frozen predictor-Sp runs."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = Path(__file__).resolve().parent
BASELINE = ROOT / "results/runs/i4f-upwind-momentum-warm-stage03-20261026T154240Z"
SP_TRUE = ROOT / "results/runs/i4f-frozen-predictor-sp-diagnostic-20261026T173557Z"
EVENT_CSV = ROOT / "results/runs/i4f-pressure-cycle-full-replay-20261026T170340Z/analysis/pressure-cycle-events.csv"
CHECKPOINT = "0.460047515286"
CHECKPOINT_TIME_S = 0.4600475152857613
REQUIRED_FIELDS = (
    "alpha.water", "alphaPhi0.water", "alphat", "k", "nut", "omega", "p",
    "p_rgh", "phi", "rho", "T", "T.air", "T.water", "U", "uniform/time",
)
TARGET_TIMES = (0.470, 0.478, 0.480, 0.482)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prefix_sha(path: Path, size: int) -> str:
    h = hashlib.sha256()
    remaining = size
    with path.open("rb") as stream:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise RuntimeError(f"source shrank while capturing prefix: {path}")
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def source_paths() -> dict[str, Path]:
    return {
        "baseline_log": BASELINE / "case/log.cold-coupled",
        "sp_true_log": SP_TRUE / "case/log.cold-coupled",
        "observer_event_csv": EVENT_CSV,
        "baseline_step_health": BASELINE / "step_health.csv",
        "sp_true_step_health": SP_TRUE / "step_health.csv",
        "baseline_guard": BASELINE / "guardian-status.json",
        "sp_true_guard": SP_TRUE / "guardian-status.json",
        "baseline_seed": BASELINE / "continuation-seed.json",
        "sp_true_seed": SP_TRUE / "continuation-seed.json",
        "baseline_freeze": BASELINE / "input-freeze.json",
        "sp_true_freeze": SP_TRUE / "input-freeze.json",
        "baseline_launch": BASELINE / "launch-manifest.json",
        "sp_true_launch": SP_TRUE / "launch-manifest.json",
        "baseline_controlDict": BASELINE / "case/system/controlDict",
        "sp_true_controlDict": SP_TRUE / "case/system/controlDict",
        "baseline_fvSolution": BASELINE / "case/system/fvSolution",
        "sp_true_fvSolution": SP_TRUE / "case/system/fvSolution",
        "baseline_fvSchemes": BASELINE / "case/system/fvSchemes",
        "sp_true_fvSchemes": SP_TRUE / "case/system/fvSchemes",
        "baseline_fvOptions": BASELINE / "case/constant/fvOptions",
        "sp_true_fvOptions": SP_TRUE / "case/constant/fvOptions",
        "baseline_water_thermo": BASELINE / "case/constant/thermophysicalProperties.water",
        "sp_true_water_thermo": SP_TRUE / "case/constant/thermophysicalProperties.water",
        "dcec_pEqn": ROOT / "solvers/i4f_frozen_sp/variants/dcec/overrides/applications/solvers/multiphase/compressibleInterFoam/pEqn.H",
        "dcec_solver_C": ROOT / "solvers/i4f_frozen_sp/variants/dcec/overrides/applications/solvers/multiphase/compressibleInterFoam/compressibleInterFoam.C",
        "common_defect_audit_H": ROOT / "solvers/i4f_frozen_sp/applications/solvers/multiphase/compressibleInterFoam/i4fDefectAudit.H",
        "vof_alphaEqn_H": ROOT / "solvers/i4f_frozen_sp/applications/solvers/multiphase/VoF/alphaEqn.H",
    }


def capture_prefix_manifest(snapshot_dir: Path) -> dict[str, Any]:
    paths = source_paths()
    prefix_names = {"baseline_log", "sp_true_log", "observer_event_csv"}
    rows: dict[str, Any] = {}
    for name, path in paths.items():
        if not path.is_file():
            rows[name] = {"path": str(path.relative_to(ROOT)), "exists": False}
            continue
        stat = path.stat()
        row: dict[str, Any] = {
            "path": str(path.relative_to(ROOT)),
            "exists": True,
            "bytes_at_capture": stat.st_size,
            "mtime_ns_at_capture": stat.st_mtime_ns,
        }
        if name in prefix_names:
            row["captured_prefix_bytes"] = stat.st_size
            row["captured_prefix_sha256"] = prefix_sha(path, stat.st_size)
            row["copied_into_bundle"] = False
        else:
            row["sha256"] = sha_file(path)
        rows[name] = row
    return {
        "schema": "i4f-sp-consistency-source-prefix-snapshot/v1",
        "captured_utc": utc(),
        "analysis_script_path": str(Path(__file__).relative_to(ROOT)),
        "analysis_script_sha256": sha_file(Path(__file__)),
        "prefixes_are_bounded_by_size_at_capture": True,
        "source_files": rows,
    }


def iter_complete_lines(path: Path, size: int) -> Iterator[str]:
    """Yield newline-terminated lines from precisely the captured prefix size."""
    remaining = size
    carry = b""
    with path.open("rb") as stream:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            pieces = (carry + chunk).split(b"\n")
            carry = pieces.pop()
            for raw in pieces:
                yield raw.rstrip(b"\r").decode("utf-8", errors="replace")
    # A partial final line is deliberately ignored.


def normalize_line(line: str) -> str:
    line = re.sub(r"^\s*(?:\[\d+\]\s*|\d+:\s*)", "", line)
    return line


KV_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")


def fields(line: str) -> dict[str, str]:
    return dict(KV_RE.findall(line))


def as_float(record: dict[str, str], key: str) -> float:
    value = float(record[key])
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {key}")
    return value


def parse_log_prefix(path: Path, size: int, seed: dict[str, Any]) -> dict[str, Any]:
    steps: dict[float, dict[str, Any]] = {}
    completed: set[float] = set()
    pending_dt: float | None = None
    current_time: float | None = None
    counts = {"phase_after_rows": 0, "outer_rows": 0, "time_rows": 0, "execution_time_rows": 0}
    for raw in iter_complete_lines(path, size):
        line = normalize_line(raw).strip()
        m = re.match(r"^deltaT\s*=\s*([^\s]+)", line)
        if m:
            try:
                pending_dt = float(m.group(1))
            except ValueError:
                pending_dt = None
            continue
        m = re.match(r"^Time\s*=\s*([^\s]+)", line)
        if m:
            try:
                if current_time is not None:
                    completed.add(current_time)
                current_time = float(m.group(1))
            except ValueError:
                current_time = None
                continue
            steps.setdefault(current_time, {"time_s": current_time, "deltaT_logged_s": pending_dt})
            if steps[current_time].get("deltaT_logged_s") is None:
                steps[current_time]["deltaT_logged_s"] = pending_dt
            pending_dt = None
            counts["time_rows"] += 1
            continue
        if line.startswith("ExecutionTime ="):
            counts["execution_time_rows"] += 1
            if current_time is not None:
                completed.add(current_time)
            continue
        if line == "End" and current_time is not None:
            completed.add(current_time)
            continue
        if line.startswith("I4F_PHASE_MASS_STATE ") and "stage=after_correctRho" in line:
            row = fields(line)
            try:
                t = as_float(row, "time_s")
                row_num = int(as_float(row, "pass"))
                parsed = {
                    "time_s": t,
                    "pass": row_num,
                    "water_inventory_kg": as_float(row, "water_inventory_kg"),
                    "gas_inventory_kg": as_float(row, "gas_inventory_kg"),
                    "water_boundary_flux_kg_s": as_float(row, "water_signed_boundary_flux_kg_s"),
                    "gas_boundary_flux_kg_s": as_float(row, "gas_signed_boundary_flux_kg_s"),
                    "water_cont_max_kg_m3_s": as_float(row, "water_cont_max_kg_m3_s"),
                    "water_cont_L1_nativeV_kg_s": as_float(row, "water_cont_L1_nativeV_kg_s"),
                    "water_cont_signed_nativeV_kg_s": as_float(row, "water_cont_signed_nativeV_kg_s"),
                    "gas_cont_max_kg_m3_s": as_float(row, "gas_cont_max_kg_m3_s"),
                    "gas_cont_L1_nativeV_kg_s": as_float(row, "gas_cont_L1_nativeV_kg_s"),
                    "gas_cont_signed_nativeV_kg_s": as_float(row, "gas_cont_signed_nativeV_kg_s"),
                    "continuity_definition": row.get("continuity_definition"),
                }
            except (KeyError, ValueError):
                continue
            cell = steps.setdefault(t, {"time_s": t, "deltaT_logged_s": None})
            if cell.get("phase_after_eos") is None or parsed["pass"] >= cell["phase_after_eos"]["pass"]:
                cell["phase_after_eos"] = parsed
            counts["phase_after_rows"] += 1
            continue
        if line.startswith("I4F_OUTER_STATE_DELTA "):
            row = fields(line)
            try:
                t = as_float(row, "time_s")
                outer = int(as_float(row, "outer_iteration"))
                parsed = {
                    "time_s": t,
                    "outer_iteration": outer,
                    "max_abs_dp_Pa": as_float(row, "max_abs_dp_Pa"),
                    "max_rel_dp": as_float(row, "max_rel_dp"),
                    "max_abs_dU_m_s": as_float(row, "max_abs_dU_m_s"),
                    "max_abs_dphi_m3_s": as_float(row, "max_abs_dphi_m3_s"),
                    "max_abs_dalpha1": as_float(row, "max_abs_dalpha1"),
                    "max_abs_dT_K": as_float(row, "max_abs_dT_K"),
                    "max_abs_drho1_kg_m3": as_float(row, "max_abs_drho1_kg_m3"),
                    "max_abs_drho2_kg_m3": as_float(row, "max_abs_drho2_kg_m3"),
                    "scope": row.get("scope"),
                }
            except (KeyError, ValueError):
                continue
            cell = steps.setdefault(t, {"time_s": t, "deltaT_logged_s": None})
            final = cell.get("final_outer")
            if outer % 8 == 0 and (final is None or outer >= final["outer_iteration"]):
                cell["final_outer"] = parsed
            cell["latest_outer"] = parsed
            counts["outer_rows"] += 1
    if current_time is not None and path.name.endswith("log.cold-coupled"):
        # End-complete runs have an explicit End; a growing prefix may leave the
        # current step incomplete and is not promoted by this fallback.
        pass

    seed_w = float(seed["checkpoint_water_kg"])
    seed_g = float(seed["checkpoint_gas_kg"])
    cum_w = 0.0
    cum_g = 0.0
    prev_w = seed_w
    prev_g = seed_g
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for t in sorted(completed):
        if t <= float(seed["checkpoint_time_s"]):
            continue
        step = steps.get(t, {})
        phase = step.get("phase_after_eos")
        outer = step.get("final_outer")
        dt = step.get("deltaT_logged_s")
        if phase is None or outer is None or dt is None:
            skipped.append({"time_s": t, "reason": "incomplete phase/outer/deltaT diagnostic set"})
            continue
        if phase["pass"] < 16 or phase["pass"] % 16 != 0:
            skipped.append({"time_s": t, "reason": f"not final 16-pressure-pass diagnostic: pass={phase['pass']}"})
            continue
        if abs(phase["time_s"] - t) > 1e-7 or abs(outer["time_s"] - t) > 1e-7:
            skipped.append({"time_s": t, "reason": "phase/outer diagnostic time mismatch"})
            continue
        w_step = phase["water_inventory_kg"] - prev_w + phase["water_boundary_flux_kg_s"] * dt
        g_step = phase["gas_inventory_kg"] - prev_g + phase["gas_boundary_flux_kg_s"] * dt
        cum_w += w_step
        cum_g += g_step
        row = {
            "time_s": t,
            "deltaT_logged_s": dt,
            "phase_mass_pass": phase["pass"],
            "water_inventory_kg": phase["water_inventory_kg"],
            "gas_inventory_kg": phase["gas_inventory_kg"],
            "water_boundary_flux_kg_s": phase["water_boundary_flux_kg_s"],
            "gas_boundary_flux_kg_s": phase["gas_boundary_flux_kg_s"],
            "water_cont_max_kg_m3_s": phase["water_cont_max_kg_m3_s"],
            "water_cont_L1_nativeV_kg_s": phase["water_cont_L1_nativeV_kg_s"],
            "water_cont_signed_nativeV_kg_s": phase["water_cont_signed_nativeV_kg_s"],
            "gas_cont_max_kg_m3_s": phase["gas_cont_max_kg_m3_s"],
            "gas_cont_L1_nativeV_kg_s": phase["gas_cont_L1_nativeV_kg_s"],
            "gas_cont_signed_nativeV_kg_s": phase["gas_cont_signed_nativeV_kg_s"],
            "final_outer_iteration": outer["outer_iteration"],
            "final_outer_max_abs_dp_Pa": outer["max_abs_dp_Pa"],
            "final_outer_max_abs_dU_m_s": outer["max_abs_dU_m_s"],
            "final_outer_max_abs_dphi_m3_s": outer["max_abs_dphi_m3_s"],
            "final_outer_max_abs_dalpha1": outer["max_abs_dalpha1"],
            "final_outer_max_abs_dT_K": outer["max_abs_dT_K"],
            "water_step_defect_from_guard_formula_kg": w_step,
            "gas_step_defect_from_guard_formula_kg": g_step,
            "water_mass_defect_increment_from_checkpoint_kg": cum_w,
            "gas_mass_defect_increment_from_checkpoint_kg": cum_g,
            "water_campaign_cumulative_defect_kg": float(seed["cumulative_water_defect_kg"]) + cum_w,
            "gas_campaign_cumulative_defect_kg": float(seed["cumulative_gas_defect_kg"]) + cum_g,
        }
        rows.append(row)
        prev_w = phase["water_inventory_kg"]
        prev_g = phase["gas_inventory_kg"]
    return {
        "rows": rows,
        "steps_seen": len(steps),
        "complete_time_entries": len(completed),
        "parsed_record_counts": counts,
        "skipped_complete_times": skipped,
        "last_complete_row": rows[-1] if rows else None,
        "captured_log_bytes": size,
    }


def read_input_file_rows(freeze_path: Path) -> dict[str, str]:
    obj = json.loads(freeze_path.read_text())
    return {row["path"]: row["sha256"] for row in obj.get("files", [])}


def dictionary_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s+([^;]+);", text)
    return match.group(1).strip() if match else None


def pair_input_audit() -> dict[str, Any]:
    base_freeze = json.loads((BASELINE / "input-freeze.json").read_text())
    true_freeze = json.loads((SP_TRUE / "input-freeze.json").read_text())
    base_seed = json.loads((BASELINE / "continuation-seed.json").read_text())
    true_seed = json.loads((SP_TRUE / "continuation-seed.json").read_text())
    base_files = read_input_file_rows(BASELINE / "input-freeze.json")
    true_files = read_input_file_rows(SP_TRUE / "input-freeze.json")
    common_paths = sorted(base_files.keys() & true_files.keys())
    same = [p for p in common_paths if base_files[p] == true_files[p]]
    different = [p for p in common_paths if base_files[p] != true_files[p]]
    only_in_sp_true = sorted(true_files.keys() - base_files.keys())
    only_in_baseline = sorted(base_files.keys() - true_files.keys())

    base_control_path = BASELINE / "case/system/controlDict"
    true_control_path = SP_TRUE / "case/system/controlDict"
    base_control = base_control_path.read_text()
    true_control = true_control_path.read_text()
    base_norm = re.sub(r"(?m)^(\s*i4fFrozenPredictorSp\s+)false(\s*;)", r"\1SWITCH\2", base_control)
    true_norm = re.sub(r"(?m)^(\s*i4fFrozenPredictorSp\s+)true(\s*;)", r"\1SWITCH\2", true_control)
    base_norm = re.sub(r"(?m)^(\s*endTime\s+)[^;]+;", r"\1TARGET;", base_norm)
    true_norm = re.sub(r"(?m)^(\s*endTime\s+)[^;]+;", r"\1TARGET;", true_norm)
    control_normalized_equal = base_norm == true_norm
    control_diff = list(difflib.unified_diff(
        base_control.splitlines(), true_control.splitlines(),
        fromfile="baseline/controlDict", tofile="sp_true/controlDict", lineterm="",
    ))

    def pimple(path: Path) -> dict[str, Any]:
        text = path.read_text()
        values = {}
        for key in ("nOuterCorrectors", "nCorrectors", "nNonOrthogonalCorrectors", "transonic"):
            match = re.search(rf"(?m)^\s*{key}\s+([^;]+);", text)
            values[key] = match.group(1).strip() if match else None
        return values

    base_control_scalars = {k: dictionary_scalar(base_control, k) for k in (
        "startFrom", "startTime", "endTime", "deltaT", "adjustTimeStep", "maxCo", "maxAlphaCo", "maxDeltaT",
        "i4fFrozenPredictorSp", "i4fFullPressureAudit",
    )}
    true_control_scalars = {k: dictionary_scalar(true_control, k) for k in base_control_scalars}
    material = {
        "same_checkpoint_path_and_time": base_seed.get("checkpoint_path_in_parent") == true_seed.get("checkpoint_path_in_parent") and base_seed.get("checkpoint_time_s") == true_seed.get("checkpoint_time_s") == CHECKPOINT_TIME_S,
        "same_15_restart_field_hashes": base_seed.get("checkpoint_field_sha256") == true_seed.get("checkpoint_field_sha256") and len(base_seed.get("checkpoint_field_sha256", {})) == 15,
        "input_freeze_parent_hashes_match_seed_both_runs": base_freeze.get("parent_checkpoint_field_sha256") == base_seed.get("checkpoint_field_sha256") and true_freeze.get("parent_checkpoint_field_sha256") == true_seed.get("checkpoint_field_sha256"),
        "same_binary_sha256": (json.loads((BASELINE / "launch-manifest.json").read_text()).get("binary_sha256") or json.loads((BASELINE / "launch-manifest.json").read_text()).get("source_binary_sha256")) == (json.loads((SP_TRUE / "launch-manifest.json").read_text()).get("binary_sha256") or json.loads((SP_TRUE / "launch-manifest.json").read_text()).get("source_binary_sha256")),
        "same_fvSchemes_sha256": sha_file(BASELINE / "case/system/fvSchemes") == sha_file(SP_TRUE / "case/system/fvSchemes"),
        "same_fvSolution_sha256": sha_file(BASELINE / "case/system/fvSolution") == sha_file(SP_TRUE / "case/system/fvSolution"),
        "same_fvOptions_sha256": sha_file(BASELINE / "case/constant/fvOptions") == sha_file(SP_TRUE / "case/constant/fvOptions"),
        "same_water_thermo_sha256": sha_file(BASELINE / "case/constant/thermophysicalProperties.water") == sha_file(SP_TRUE / "case/constant/thermophysicalProperties.water"),
        "controlDict_equal_after_normalizing_only_switch_and_endTime": control_normalized_equal,
        "same_pimple": pimple(BASELINE / "case/system/fvSolution") == pimple(SP_TRUE / "case/system/fvSolution"),
    }
    return {
        "baseline_input_freeze_sha256": sha_file(BASELINE / "input-freeze.json"),
        "sp_true_input_freeze_sha256": sha_file(SP_TRUE / "input-freeze.json"),
        "common_freeze_path_count": len(common_paths),
        "same_hash_path_count": len(same),
        "different_hash_paths": different,
        "only_in_baseline": only_in_baseline,
        "only_in_sp_true": only_in_sp_true,
        "material_checks": material,
        "baseline_control_values": base_control_scalars,
        "sp_true_control_values": true_control_scalars,
        "baseline_pimple": pimple(BASELINE / "case/system/fvSolution"),
        "sp_true_pimple": pimple(SP_TRUE / "case/system/fvSolution"),
        "controlDict_diff": control_diff,
        "controlDict_diff_only_switch_and_endTime": control_normalized_equal,
    }


def read_step_health(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def compare_targets(base_rows: list[dict[str, Any]], true_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out=[]
    for target in TARGET_TIMES:
        b=min(base_rows,key=lambda r:abs(r["time_s"]-target)) if base_rows else None
        a=min(true_rows,key=lambda r:abs(r["time_s"]-target)) if true_rows else None
        if b is None or a is None:
            out.append({"target_time_s":target,"status":"missing one run coverage","baseline_time_s":b and b["time_s"],"sp_true_time_s":a and a["time_s"]})
            continue
        pair={"target_time_s":target,"status":"nearest complete samples; actual times and offsets reported","baseline_time_s":b["time_s"],"sp_true_time_s":a["time_s"],"baseline_offset_s":b["time_s"]-target,"sp_true_offset_s":a["time_s"]-target,"paired_time_separation_s":a["time_s"]-b["time_s"]}
        for key in (
            "water_cont_L1_nativeV_kg_s", "gas_cont_L1_nativeV_kg_s",
            "water_cont_max_kg_m3_s", "gas_cont_max_kg_m3_s",
            "water_cont_signed_nativeV_kg_s", "gas_cont_signed_nativeV_kg_s",
            "water_inventory_kg", "gas_inventory_kg",
            "water_boundary_flux_kg_s", "gas_boundary_flux_kg_s",
            "water_mass_defect_increment_from_checkpoint_kg", "gas_mass_defect_increment_from_checkpoint_kg",
            "water_step_defect_from_guard_formula_kg", "gas_step_defect_from_guard_formula_kg",
            "final_outer_max_abs_dp_Pa", "final_outer_max_abs_dU_m_s", "final_outer_max_abs_dphi_m3_s",
            "final_outer_max_abs_dalpha1", "final_outer_max_abs_dT_K",
        ):
            bv=b[key]; av=a[key]
            pair[f"baseline_{key}"]=bv
            pair[f"sp_true_{key}"]=av
            pair[f"sp_true_over_baseline_{key}"]=av/bv if bv not in (0,None) else None
        pair["baseline_final_outer_iteration"]=b["final_outer_iteration"]
        pair["sp_true_final_outer_iteration"]=a["final_outer_iteration"]
        pair["baseline_phase_mass_pass"]=b["phase_mass_pass"]
        pair["sp_true_phase_mass_pass"]=a["phase_mass_pass"]
        out.append(pair)
    return out


def analyze_sp_event_rows() -> dict[str, Any]:
    rows=[]
    with EVENT_CSV.open(newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                delta_sp=float(row["corrector_Sp_recomputed_per_s"])-float(row["predictor_Sp_per_s"])
                delta_alpha=float(row["alpha_after_MULES_corrector"])-float(row["alpha_after_implicit_predictor"])
                d_s_inv=delta_sp*delta_alpha
                rho=float(row["rho_water_after_kg_m3"])
                source=rho*d_s_inv
                residual=float(row["water_postEOS_phase_continuity_kg_m3_s"])
                if not residual or not math.isfinite(source/residual):
                    continue
                rows.append({
                    "time_s":float(row["time_s"]),"time_index":int(row["time_index"]),
                    "outer_iteration":int(row["outer_iteration"]),"rank":int(row["rank"]),
                    "local_cell":int(row["local_cell"]),"stage":row["stage"],
                    "alpha_before_predictor":float(row["alpha_before_predictor"]),
                    "alpha_after_implicit_predictor":float(row["alpha_after_implicit_predictor"]),
                    "alpha_after_MULES_corrector":float(row["alpha_after_MULES_corrector"]),
                    "predictor_Sp_per_s":float(row["predictor_Sp_per_s"]),
                    "corrector_Sp_recomputed_per_s":float(row["corrector_Sp_recomputed_per_s"]),
                    "delta_Sp_per_s":delta_sp,"delta_alpha_F_minus_P":delta_alpha,
                    "D_per_s":d_s_inv,"rho_water_after_kg_m3":rho,
                    "rho_times_D_kg_m3_s":source,
                    "water_postEOS_phase_continuity_kg_m3_s":residual,
                    "signed_ratio_rhoD_over_residual":source/residual,
                })
            except (KeyError, ValueError, ZeroDivisionError):
                continue
    grouped: dict[tuple[int,int],list[dict[str,Any]]]=defaultdict(list)
    for row in rows:
        grouped[(row["rank"],row["local_cell"])].append(row)
    recurrent=[r for key, group in grouped.items() if len(group)>=2 for r in group]
    recurrent_cells=[]
    for (rank,cell),group in sorted(grouped.items(), key=lambda item:len(item[1]), reverse=True):
        if len(group)<2:
            continue
        ratios=[r["signed_ratio_rhoD_over_residual"] for r in group]
        recurrent_cells.append({
            "rank":rank,"local_cell":cell,"row_count":len(group),
            "time_min_s":min(r["time_s"] for r in group),"time_max_s":max(r["time_s"] for r in group),
            "median_signed_ratio":median(ratios),"median_absolute_ratio":median(abs(x) for x in ratios),
            "latest_row":max(group,key=lambda r:r["time_s"]),
        })
    ratios=[r["signed_ratio_rhoD_over_residual"] for r in recurrent]
    exact=[r for r in rows if abs(r["time_s"]-0.48199621213)<1e-12 and r["outer_iteration"]==1535 and r["rank"]==7 and r["local_cell"]==1164]
    return {
        "event_csv_path":str(EVENT_CSV.relative_to(ROOT)),
        "event_csv_bytes":EVENT_CSV.stat().st_size,
        "event_csv_sha256":sha_file(EVENT_CSV),
        "arithmetic_definition":"D=(corrector_Sp_recomputed_per_s-predictor_Sp_per_s)*(alpha_after_MULES_corrector-alpha_after_implicit_predictor); compare rho_water_after*D with the same row's water_postEOS_phase_continuity. This is a local term comparison, not a global closure or causal fit.",
        "valid_event_rows":len(rows),
        "recurrent_local_cells_count":len(recurrent_cells),
        "recurrent_event_rows_count":len(recurrent),
        "recurrent_row_ratio_summary":{
            "median_signed_ratio":median(ratios) if ratios else None,
            "median_absolute_ratio":median(abs(x) for x in ratios) if ratios else None,
            "p90_absolute_ratio":sorted(abs(x) for x in ratios)[int(0.9*(len(ratios)-1))] if ratios else None,
            "min_signed_ratio":min(ratios) if ratios else None,
            "max_signed_ratio":max(ratios) if ratios else None,
        },
        "most_recurrent_cells":recurrent_cells[:8],
        "quoted_cell_row_count":len(exact),
        "quoted_cell_rows":exact,
        "qualification":"Rows come from the saved full-replay observer event CSV, not a matched trajectory in either current comparison run. The source-term ratio is descriptive; no fit or general-causality claim is made.",
    }


def write_matched_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns=sorted({key for row in rows for key in row})
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def capture(snapshot_id: str) -> dict[str, Any]:
    snap=BUNDLE/"snapshots"/snapshot_id
    snap.mkdir(parents=True,exist_ok=False)
    # Hash and preserve source sizes first. The raw logs stay at their original
    # paths; only compact parsed rows are written to this bundle.
    prefix_manifest=capture_prefix_manifest(snap)
    save_json(snap/"source-prefix-manifest.json",prefix_manifest)

    baseline_seed=json.loads((BASELINE/"continuation-seed.json").read_text())
    true_seed=json.loads((SP_TRUE/"continuation-seed.json").read_text())
    base_source=prefix_manifest["source_files"]["baseline_log"]
    true_source=prefix_manifest["source_files"]["sp_true_log"]
    baseline=parse_log_prefix(BASELINE/"case/log.cold-coupled",int(base_source["captured_prefix_bytes"]),baseline_seed)
    sp_true=parse_log_prefix(SP_TRUE/"case/log.cold-coupled",int(true_source["captured_prefix_bytes"]),true_seed)
    input_audit=pair_input_audit()
    matched=compare_targets(baseline["rows"],sp_true["rows"])
    event_audit=analyze_sp_event_rows()

    baseline_guard=json.loads((BASELINE/"guardian-status.json").read_text())
    true_guard=json.loads((SP_TRUE/"guardian-status.json").read_text())
    base_branch=next(iter(baseline_guard["branches"].values()))
    true_branch=next(iter(true_guard["branches"].values()))
    baseline_health=read_step_health(BASELINE/"step_health.csv")
    true_health=read_step_health(SP_TRUE/"step_health.csv")
    true_run_terminal = true_guard.get("status") == "solver_terminal" or true_branch.get("status") == "normal_End_complete_native10_checkpoint"
    result={
        "schema":"i4f-sp-consistency-comparison/v1",
        "snapshot_id":snapshot_id,
        "analysis_created_utc":utc(),
        "status":"terminal_A_run_captured" if true_run_terminal else "bounded_prefix_analysis_A_run_may_continue",
        "comparison_contract":{
            "baseline":"standard DCEC predictor Sp, i4fFrozenPredictorSp=false, corrected native mesh, warm original .460047515286 checkpoint, nOuter=8, nCorrectors=2, transonic=yes, upwind momentum",
            "counterfactual":"same declared .460047515286 checkpoint with i4fFrozenPredictorSp=true; intended sole physical/numerical switch",
            "source_definition":"I4F_PHASE_MASS_STATE continuity L1 comes from global fvc::ddt(alpha*rho)+fvc::div(alphaPhi*rhoFace), after EOS density correction, integrated as sum(abs(residual)*native cell volume). It is not the pressure-matrix residual and is not itself the mass ledger.",
            "mass_defect_definition":"Per completed step, reproduce the active guard formula: inventory(t)-inventory(previous)+signed_outward_boundary_flux(t)*logged_deltaT. Sum from the exact .460047515286 checkpoint, and report the increment separately from campaign cumulative defect at the checkpoint.",
            "outer_update_definition":"Take the last I4F_OUTER_STATE_DELTA where cumulative outer_iteration mod 8 == 0 at that physical time; max_abs_dp is the final outer-state update, not a fully coupled residual.",
            "sample_policy":"For each requested target, use nearest complete sample in each run and report both actual timestamps/offsets. The baseline ends at .48189409979 s; no baseline value is invented beyond its terminal state.",
            "targets_s":list(TARGET_TIMES),
        },
        "source_prefix_manifest_path":str((snap/"source-prefix-manifest.json").relative_to(ROOT)),
        "source_prefix_manifest_sha256":sha_file(snap/"source-prefix-manifest.json"),
        "input_pair_audit":input_audit,
        "baseline_log_capture":{
            "path":str((BASELINE/"case/log.cold-coupled").relative_to(ROOT)),
            "prefix_bytes":int(base_source["captured_prefix_bytes"]),
            "prefix_sha256":base_source["captured_prefix_sha256"],
            "parsed_record_counts":baseline["parsed_record_counts"],
            "steps_seen":baseline["steps_seen"],"complete_time_entries":baseline["complete_time_entries"],
            "complete_diagnostic_rows":len(baseline["rows"]),"latest_complete_row":baseline["last_complete_row"],
        },
        "sp_true_log_capture":{
            "path":str((SP_TRUE/"case/log.cold-coupled").relative_to(ROOT)),
            "prefix_bytes":int(true_source["captured_prefix_bytes"]),
            "prefix_sha256":true_source["captured_prefix_sha256"],
            "parsed_record_counts":sp_true["parsed_record_counts"],
            "steps_seen":sp_true["steps_seen"],"complete_time_entries":sp_true["complete_time_entries"],
            "complete_diagnostic_rows":len(sp_true["rows"]),"latest_complete_row":sp_true["last_complete_row"],
        },
        "guard_status_snapshots":{
            "baseline":{"status":baseline_guard.get("status"),"updated_utc":baseline_guard.get("updated_utc"),"current_time_s":base_branch.get("current_time_s"),"completed_steps":base_branch.get("completed_steps"),"cumulative_water_defect_kg":base_branch.get("cumulative_water_defect_kg"),"cumulative_gas_defect_kg":base_branch.get("cumulative_gas_defect_kg"),"last_step_health":base_branch.get("last_step_health")},
            "sp_true":{"status":true_guard.get("status"),"updated_utc":true_guard.get("updated_utc"),"current_time_s":true_branch.get("current_time_s"),"completed_steps":true_branch.get("completed_steps"),"cumulative_water_defect_kg":true_branch.get("cumulative_water_defect_kg"),"cumulative_gas_defect_kg":true_branch.get("cumulative_gas_defect_kg"),"last_step_health":true_branch.get("last_step_health")},
        },
        "guard_csv_validation":{
            "baseline_step_health_rows":len(baseline_health),
            "sp_true_step_health_rows_visible_at_capture":len(true_health),
            "sp_true_step_health_note":"The controller keeps its CSV stream buffered until a 256-row flush; raw-log reconstruction is cross-checked against guardian last_step_health when available.",
            "baseline_last_csv_row":baseline_health[-1] if baseline_health else None,
            "sp_true_last_csv_row":true_health[-1] if true_health else None,
        },
        "matched_target_rows":matched,
        "full_replay_local_Sp_term_check":event_audit,
        "interpretation_limits":[
            "A and baseline are separate warm restart histories; only the exact .460047515286 checkpoint and declared inputs are shared.",
            "Global continuity L1 is a discrete diagnostic after EOS correction, not a formal conservation gate or pressure-matrix residual.",
            "Mass-defect increments use the controller's logged instantaneous net-outward flux times logged deltaT; they are ledger increments, not the campaign cumulative defect by itself.",
            "The local rho*D comparison uses a separate saved observer full-replay event CSV and cannot establish that the Sp=true trajectory is cured or conserved.",
            "This comparison makes no production-adoption, convergence, or hardware-performance claim.",
        ],
    }
    save_json(snap/"comparison.json",result)
    write_matched_csv(snap/"matched-times.csv",matched)
    save_json(snap/"local-source-term-ratio.json",event_audit)
    output_manifest={
        "schema":"i4f-sp-consistency-output-manifest/v1",
        "created_utc":utc(),
        "analysis_script_sha256":sha_file(Path(__file__)),
        "source_prefix_manifest_sha256":sha_file(snap/"source-prefix-manifest.json"),
        "outputs":{p.name:{"bytes":p.stat().st_size,"sha256":sha_file(p)} for p in (snap/"comparison.json",snap/"matched-times.csv",snap/"local-source-term-ratio.json")},
    }
    save_json(snap/"output-manifest.json",output_manifest)
    return result


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--snapshot-id",required=True)
    args=parser.parse_args()
    result=capture(args.snapshot_id)
    print(json.dumps({
        "snapshot_id":result["snapshot_id"],
        "baseline_complete_rows":result["baseline_log_capture"]["complete_diagnostic_rows"],
        "sp_true_complete_rows":result["sp_true_log_capture"]["complete_diagnostic_rows"],
        "targets":result["matched_target_rows"],
        "sp_local_event_rows":result["full_replay_local_Sp_term_check"]["valid_event_rows"],
        "recurrent_cells":result["full_replay_local_Sp_term_check"]["recurrent_local_cells_count"],
    },sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
