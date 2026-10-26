#!/usr/bin/env python3
"""Compare native internal-field values and solver audits for the private restart probe."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parents[1]
ARMS = ("arm-a-uninterrupted", "arm-b-fallback", "arm-c-saved-dgdt")
COMPONENTS = {"scalar": 1, "vector": 3, "sphericalTensor": 1, "symmTensor": 6, "tensor": 9}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def find_time_directory(case: Path, value: float) -> Path | None:
    candidates = []
    for path in case.iterdir():
        if not path.is_dir():
            continue
        try:
            time_value = float(path.name)
        except ValueError:
            continue
        if math.isclose(time_value, value, rel_tol=0.0, abs_tol=1e-14):
            candidates.append((abs(time_value - value), path))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def parse_internal_field(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    match = re.search(
        rb"internalField\s+nonuniform\s+List<(?P<type>[^>]+)>\s+(?P<count>\d+)\s*\(",
        raw,
    )
    if not match:
        raise ValueError(f"could not find binary nonuniform internalField in {path}")
    value_type = match.group("type").decode("ascii")
    if value_type not in COMPONENTS:
        raise ValueError(f"unsupported field type {value_type!r} in {path}")
    count = int(match.group("count"))
    components = COMPONENTS[value_type]
    start = match.end()
    nvalues = count * components
    stop = start + nvalues * 8
    tail = raw[stop:]
    if stop > len(raw) or not (tail.startswith(b")") or tail.startswith(b"\n)") or tail.startswith(b"\r\n)")):
        raise ValueError(f"binary internalField extent does not match declared count in {path}")
    values = np.frombuffer(raw, dtype="<f8", count=nvalues, offset=start).copy()
    if not np.isfinite(values).all():
        raise ValueError(f"nonfinite internalField value in {path}")
    return values.reshape((count, components))


def kv_record(line: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        try:
            values[key] = float(value)
        except ValueError:
            values[key] = value
    return values


def metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    if left.shape != right.shape:
        raise ValueError(f"field shape mismatch: {left.shape} vs {right.shape}")
    delta = left - right
    abs_delta = np.abs(delta)
    denominator = np.maximum(np.maximum(np.abs(left), np.abs(right)), 1e-300)
    rel_delta = abs_delta / denominator
    return {
        "shape": list(left.shape),
        "max_abs": float(abs_delta.max(initial=0.0)),
        "rms_abs": float(np.sqrt(np.mean(delta * delta))) if delta.size else 0.0,
        "max_relative": float(rel_delta.max(initial=0.0)),
        "left_min": float(left.min(initial=math.inf)),
        "left_max": float(left.max(initial=-math.inf)),
        "right_min": float(right.min(initial=math.inf)),
        "right_max": float(right.max(initial=-math.inf)),
    }


def parse_log(log_path: Path, split_time: float, endpoint_time: float) -> dict[str, Any]:
    initial: list[dict[str, Any]] = []
    phase_states: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for line in log_path.read_text(errors="replace").splitlines():
        if line.startswith("I4F_INITIAL_PHASE_MASS "):
            initial.append(kv_record(line))
        elif line.startswith("I4F_PHASE_MASS_STATE "):
            phase_states.append(kv_record(line))
        elif line.startswith("I4F_FULL_PREDICTOR_SOURCE_SUMMARY "):
            sources.append(kv_record(line))
    split_states = [
        row for row in phase_states
        if isinstance(row.get("time_s"), float)
        and math.isclose(float(row["time_s"]), split_time, rel_tol=0.0, abs_tol=1e-12)
        and row.get("stage") == "after_correctRho"
    ]
    endpoint_states = [
        row for row in phase_states
        if isinstance(row.get("time_s"), float)
        and math.isclose(float(row["time_s"]), endpoint_time, rel_tol=0.0, abs_tol=1e-12)
        and row.get("stage") == "after_correctRho"
    ]
    endpoint_sources = [
        row for row in sources
        if isinstance(row.get("time_s"), float)
        and math.isclose(float(row["time_s"]), endpoint_time, rel_tol=0.0, abs_tol=1e-12)
    ]
    if not endpoint_states:
        raise ValueError(f"no post-EOS phase-mass audit at endpoint in {log_path}")
    if not endpoint_sources:
        raise ValueError(f"no full-predictor source audit at endpoint in {log_path}")
    return {
        "initial_phase_mass": initial[-1] if initial else None,
        "split_phase_mass_last_after_correctRho": split_states[-1] if split_states else None,
        "endpoint_phase_mass_last_after_correctRho": endpoint_states[-1],
        "endpoint_source_summaries": endpoint_sources,
    }


def main() -> None:
    statuses = {}
    arrays = {}
    log_data = {}
    for arm in ARMS:
        case_root = BUNDLE / "cases" / arm
        status = json.loads((case_root / "run-status.json").read_text())
        if status["status"] != "normal_end_complete":
            raise RuntimeError(f"arm {arm} did not complete normally: {status['status']}")
        endpoint = case_root / "case" / status["terminal_native_time_directory"]
        statuses[arm] = status
        arrays[arm] = {
            field: parse_internal_field(endpoint / field)
            for field in status["endpoint_fields_present"]
            if (endpoint / field).is_file()
        }
        log_data[arm] = parse_log(
            case_root / "case/log.compressibleInterFoam",
            split_time=0.1,
            endpoint_time=float(status["target_time_s"]),
        )

    comparisons = {}
    csv_path = BUNDLE / "provenance/restart-internal-field-differences.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("left_arm", "right_arm", "field", "left_sha256", "right_sha256", "bitwise_equal", "element_count", "max_abs", "rms_abs", "max_relative"),
        )
        writer.writeheader()
        for left_arm, right_arm in ((ARMS[0], ARMS[1]), (ARMS[0], ARMS[2]), (ARMS[1], ARMS[2])):
            common = sorted(set(arrays[left_arm]) & set(arrays[right_arm]))
            pair = {}
            for field in common:
                left_path = BUNDLE / "cases" / left_arm / "case" / statuses[left_arm]["terminal_native_time_directory"] / field
                right_path = BUNDLE / "cases" / right_arm / "case" / statuses[right_arm]["terminal_native_time_directory"] / field
                left_sha, right_sha = sha(left_path), sha(right_path)
                metric = metrics(arrays[left_arm][field], arrays[right_arm][field])
                metric.update({"left_sha256": left_sha, "right_sha256": right_sha, "bitwise_equal": left_sha == right_sha})
                pair[field] = metric
                writer.writerow({
                    "left_arm": left_arm,
                    "right_arm": right_arm,
                    "field": field,
                    "left_sha256": left_sha,
                    "right_sha256": right_sha,
                    "bitwise_equal": left_sha == right_sha,
                    "element_count": int(np.prod(metric["shape"])),
                    "max_abs": metric["max_abs"],
                    "rms_abs": metric["rms_abs"],
                    "max_relative": metric["max_relative"],
                })
            comparisons[f"{left_arm}__vs__{right_arm}"] = pair

    initial_masses = {arm: log_data[arm]["initial_phase_mass"] for arm in ARMS}
    final_masses = {arm: log_data[arm]["endpoint_phase_mass_last_after_correctRho"] for arm in ARMS}
    increments = {}
    for arm in ARMS:
        if arm == "arm-a-uninterrupted":
            initial = log_data[arm]["split_phase_mass_last_after_correctRho"]
        else:
            initial = initial_masses[arm]
        final = final_masses[arm]
        increments[arm] = {
            "baseline_source": "A last t=0.1 after_correctRho audit" if arm == "arm-a-uninterrupted" else "restart startup I4F_INITIAL_PHASE_MASS",
            "water_start_kg": initial["water_inventory_kg"],
            "water_end_kg": final["water_inventory_kg"],
            "water_increment_kg": final["water_inventory_kg"] - initial["water_inventory_kg"],
            "gas_start_kg": initial["gas_inventory_kg"],
            "gas_end_kg": final["gas_inventory_kg"],
            "gas_increment_kg": final["gas_inventory_kg"] - initial["gas_inventory_kg"],
        }

    split_manifest = json.loads((BUNDLE / "provenance/split-checkpoint.json").read_text())
    split_name = split_manifest["split_native_time_directory"]
    split_dir = BUNDLE / "cases/arm-a-uninterrupted/case" / split_name
    previous_time_dir = find_time_directory(
        BUNDLE / "cases/arm-a-uninterrupted/case", 0.09975
    )
    previous_time_files = sorted(path.name for path in previous_time_dir.iterdir() if path.is_file()) if previous_time_dir else []
    split_common_t = parse_internal_field(split_dir / "T")
    split_phase_t_differences = {
        name: metrics(split_common_t, parse_internal_field(split_dir / name))
        for name in ("T.air", "T.water")
    }
    endpoint_comparisons = comparisons["arm-a-uninterrupted__vs__arm-c-saved-dgdt"]
    restart_pair = comparisons["arm-b-fallback__vs__arm-c-saved-dgdt"]
    mass_a = log_data["arm-a-uninterrupted"]["endpoint_phase_mass_last_after_correctRho"]
    mass_b = log_data["arm-b-fallback"]["endpoint_phase_mass_last_after_correctRho"]
    mass_c = log_data["arm-c-saved-dgdt"]["endpoint_phase_mass_last_after_correctRho"]
    water_flux_expected = -0.03166964185 * 0.00025
    gas_cont_l1 = {
        arm: log_data[arm]["endpoint_phase_mass_last_after_correctRho"]["gas_cont_L1_nativeV_kg_s"]
        for arm in ARMS
    }
    source_a_outer1 = log_data[ARMS[0]]["endpoint_source_summaries"][0]
    source_c_outer1 = log_data[ARMS[2]]["endpoint_source_summaries"][0]
    source_outer1_comparable_keys = sorted((set(source_a_outer1) & set(source_c_outer1)) - {"outer_iteration"})
    source_outer1_exact_match = all(
        source_a_outer1[key] == source_c_outer1[key]
        for key in source_outer1_comparable_keys
    )

    source_files = {
        "createFields.H": BUNDLE / "build/source/v7-frozen-sp-v2-full-predictor-prototype/applications/solvers/multiphase/compressibleInterFoam/createFields.H",
        "pEqn.H": BUNDLE / "build/source/v7-frozen-sp-v2-full-predictor-prototype/applications/solvers/multiphase/compressibleInterFoam/pEqn.H",
        "UEqn.H": BUNDLE / "build/source/v7-frozen-sp-v2-full-predictor-prototype/applications/solvers/multiphase/compressibleInterFoam/UEqn.H",
        "TEqn.H": BUNDLE / "build/source/v7-frozen-sp-v2-full-predictor-prototype/applications/solvers/multiphase/compressibleInterFoam/TEqn.H",
    }

    source_build = json.loads((BUNDLE / "provenance/build-result.json").read_text())
    result = {
        "schema": "i4f-dgdt-restart-comparison/v1",
        "created_utc": utc(),
        "method": {
            "field_comparison": "binary native internalField values parsed as little-endian IEEE-754 float64 from OpenFOAM v2512 headers; boundary values remain recoverable in hashed native files",
            "phase_inventory": "I4F_PHASE_MASS_STATE post-correctRho; A baseline is t=0.1 last after_correctRho, B/C baseline is restart startup I4F_INITIAL_PHASE_MASS",
            "source_diagnostics": "I4F_FULL_PREDICTOR_SOURCE_SUMMARY rows at common endpoint physical time, grouped by PIMPLE outer iteration",
            "comparison_time_s": 0.10025000000000008,
            "dt_s": 0.00025,
            "serialization": "binary, scalar precision 64, writePrecision 17",
        },
        "patch_sha256": source_build["patch_sha256"],
        "probe_binary_sha256": source_build["new_binary_sha256"],
        "arm_runtime": {
            arm: {
                "container_id": statuses[arm]["container_id"],
                "started_at": statuses[arm]["started_at"],
                "log_sha256": statuses[arm]["log_sha256"],
                "endpoint_time_directory": statuses[arm]["terminal_native_time_directory"],
                "endpoint_field_sha256": statuses[arm]["endpoint_field_sha256"],
            }
            for arm in ARMS
        },
        "initial_phase_mass_events": initial_masses,
        "final_phase_mass_events": final_masses,
        "single_step_mass_increments": increments,
        "endpoint_full_predictor_source_summaries": {
            arm: log_data[arm]["endpoint_source_summaries"] for arm in ARMS
        },
        "diagnostic_summary": {
            "A_vs_C_pressure_max_abs_Pa": endpoint_comparisons["p"]["max_abs"],
            "B_vs_C_pressure_max_abs_Pa": restart_pair["p"]["max_abs"],
            "A_vs_C_alpha_water_max_abs": endpoint_comparisons["alpha.water"]["max_abs"],
            "A_vs_C_U_max_abs_m_s": endpoint_comparisons["U"]["max_abs"],
            "A_vs_C_T_max_abs_K": endpoint_comparisons["T"]["max_abs"],
            "A_vs_C_endpoint_gas_inventory_difference_kg": mass_c["gas_inventory_kg"] - mass_a["gas_inventory_kg"],
            "B_vs_C_endpoint_gas_inventory_difference_kg": mass_c["gas_inventory_kg"] - mass_b["gas_inventory_kg"],
            "A_vs_C_endpoint_water_inventory_difference_kg": mass_c["water_inventory_kg"] - mass_a["water_inventory_kg"],
            "A_water_inventory_increment_minus_prescribed_outflow_kg": increments["arm-a-uninterrupted"]["water_increment_kg"] - water_flux_expected,
            "B_water_inventory_increment_minus_prescribed_outflow_kg": increments["arm-b-fallback"]["water_increment_kg"] - water_flux_expected,
            "C_water_inventory_increment_minus_prescribed_outflow_kg": increments["arm-c-saved-dgdt"]["water_increment_kg"] - water_flux_expected,
            "endpoint_gas_continuity_L1_nativeV_kg_s": gas_cont_l1,
            "restart_to_A_endpoint_gas_continuity_L1_ratio": {
                "B_over_A": gas_cont_l1["arm-b-fallback"] / gas_cont_l1["arm-a-uninterrupted"],
                "C_over_A": gas_cont_l1["arm-c-saved-dgdt"] / gas_cont_l1["arm-a-uninterrupted"],
            },
            "C_outer1_full_source_summary_matches_A_outer1": source_outer1_exact_match,
            "split_phase_temperature_minus_common_T": split_phase_t_differences,
            "interpretation": "Saving dgdt reproduces A's outer-1 full-source residual summary in C but does not reproduce A's endpoint state. The large restart-arm gas-continuity L1 suggests additional Euler history/thermodynamic state matters; this short test does not isolate which state term is responsible. At the split, T.air and T.water already match common T to roundoff, so the expected constructor rewrite is not by itself evidence explaining the endpoint mismatch.",
        },
        "candidate_missing_euler_history": {
            "evidence": "B/C contain only the current split state at t=0.10000000000000007. A has an alpha.air function-object output at t=0.099750000000000075, but not the full previous-time solver state. The configured time scheme is Euler. Source equations use ddt(alpha1,rho1), ddt(alpha2,rho2), ddt(p_rgh), ddt(rho,U), ddt(rho,T), and ddt(rho,K).",
            "previous_time_directory_in_A": previous_time_dir.name if previous_time_dir else None,
            "only_files_written_in_that_previous_time_directory": previous_time_files,
            "previous_time_directory_present_in_restart_B_or_C": {
                arm: (BUNDLE / "cases" / arm / "case" / (previous_time_dir.name if previous_time_dir else "missing")).is_dir()
                for arm in ("arm-b-fallback", "arm-c-saved-dgdt")
            },
            "current_restart_fields_are_not_the_full_euler_state": "The copied native checkpoint contains current-time fields only. `dgdt` is a separate lagged pressure-derived quantity; saving it repairs the outer-1 full-source audit signature, but does not supply prior-time values used by the Euler ddt terms.",
            "likely_minimal_next_state": [
                "one previous-time history for alpha1/alpha2 and phase rho1/rho2 (or enough prior p/T plus exact EOS state to reconstruct rho1/rho2)",
                "one previous-time history for p_rgh, rho, U, T, and K where the compiled UEqn/TEqn/pEqn ddt operators use them; K is algebraically derived from U but its prior-time value must be consistent",
                "saved dgdt at the current checkpoint for the frozen/full-source path",
            ],
            "observed_consequence": "Endpoint gas-phase continuity L1 rises from 4.7048e-8 kg/s in uninterrupted A to 3.5741e-4 and 3.7638e-4 kg/s in restart B/C (about 7.60e3 and 8.00e3 times A); C still differs from A by max |p|=127.824 Pa although its outer-1 full-source summary matches A exactly.",
            "interpretation_status": "source-supported hypothesis, not isolated by this probe; exact OpenFOAM oldTime initialization behavior should be confirmed before implementing a history-preserving restart patch",
            "cheap_followup": "On the same tiny fixture, add a probe-only read/restore of prior-time ddt history (first alpha_i/rho_i and p_rgh; then rho/U/T/K if needed) from a .09975 snapshot and compare the first .10025 step against A. Keep the same native .1 checkpoint, binary precision, code, and all governing equations.",
        },
        "source_state_locations": {
            "source_tree_sha256_manifest": sha(BUNDLE / "provenance/parent-source-tree-manifest.json"),
            "files": {
                name: {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha(path),
                    "key_source_roles": {
                        "createFields.H": "phase rho1/rho2 references, composite rho READ_IF_PRESENT, rhoPhi NO_READ, and dgdt restart IO",
                        "pEqn.H": "Euler ddt(alpha_i,rho_i) and ddt(p_rgh) phase continuity/pressure terms plus EOS correction",
                        "UEqn.H": "Euler ddt(rho,U); K reconstructed from U before pressure coupling",
                        "TEqn.H": "Euler ddt(rho,T) and ddt(rho,K)",
                    }[name],
                }
                for name, path in source_files.items()
            },
        },
        "internal_field_pairwise_differences": comparisons,
        "source_interpretation_limits": [
            "A/B/C are deterministic short diagnostic arms on one sealed 60-cell grid, not apparatus validation.",
            "Exact or near field agreement only assesses this one saved Euler step and startup path.",
            "The phase source audit is a local equation diagnostic and does not establish energy closure.",
            "The B and C runs share the same t=0.1 files except for intentionally omitting dgdt in B; constructors may reconstruct phase T after restart.",
        ],
        "csv_path": str(csv_path.relative_to(ROOT)),
        "csv_sha256": sha(csv_path),
    }
    out = BUNDLE / "provenance/restart-comparison.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "json": str(out.relative_to(ROOT)),
        "csv": str(csv_path.relative_to(ROOT)),
        "field_pairs": {key: {field: {"max_abs": value["max_abs"], "rms_abs": value["rms_abs"], "bitwise_equal": value["bitwise_equal"]} for field, value in pair.items()} for key, pair in comparisons.items()},
        "mass_increments": increments,
    }, indent=2))


if __name__ == "__main__":
    main()
