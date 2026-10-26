#!/usr/bin/env python3
"""Analyze the four small source-mode runs at exact saved times."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
OLD = ROOT / "results/runs/i4f-gas-expansion-interface-mesh-sensitivity-20261025T213324Z"
P0, T0 = 1.2e6, 293.15
VW0, VG0, V0 = 8.0e-5, 2.0e-5, 1.0e-4
Q0 = 3.172675e-5
R_AIR, CP_AIR, RHO_W = 287.0477481284761, 1005.0, 998.2
GAMMA = CP_AIR / (CP_AIR - R_AIR)
DT, END = 2.5e-4, 0.4


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def table(path: Path) -> list[list[float]]:
    rows = [
        [float(value) for value in line.split()]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not rows or any(not math.isfinite(v) for row in rows for v in row):
        raise RuntimeError(f"empty/nonfinite function-object table: {path}")
    return rows


def scalar_field(path: Path, n: int) -> list[float]:
    text = path.read_text(encoding="utf-8")
    uniform = re.search(r"internalField\s+uniform\s+([-+0-9.eE]+)\s*;", text)
    if uniform:
        return [float(uniform.group(1))] * n
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"cannot parse scalar field: {path}")
    count = int(match.group(1))
    values = [float(value) for value in match.group(2).split()]
    if count != n or len(values) != n:
        raise RuntimeError(f"{path}: expected {n} entries, got {count}/{len(values)}")
    return values


def pressure_floor_audit(log_path: Path) -> dict[str, object]:
    raw_records = []
    execution = None
    text = log_path.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"CLAMP_TRACE_RAW time_s=([^ ]+) outer=(\d+) pass=(\d+) pMin_Pa=([^ ]+) "
        r"raw_cell_p_min_Pa=([^ ]+) raw_cell_p_max_Pa=([^ ]+) "
        r"cells_strictly_below_pMin=(\d+) clipped_water_volume_m3=([^ ]+) "
        r"clipped_water_mass_kg=([^ ]+)"
    )
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            values = match.groups()
            raw_records.append(
                {
                    "time_s": float(values[0]),
                    "pMin_Pa": float(values[3]),
                    "raw_cell_p_min_Pa": float(values[4]),
                    "raw_cell_p_max_Pa": float(values[5]),
                    "cells_strictly_below_pMin": int(values[6]),
                    "clipped_water_volume_m3": float(values[7]),
                    "clipped_water_mass_kg": float(values[8]),
                }
            )
        if line.startswith("ExecutionTime ="):
            timing = re.search(
                r"ExecutionTime\s*=\s*([-+0-9.eE]+)\s*s\s+ClockTime\s*=\s*([-+0-9.eE]+)\s*s",
                line,
            )
            if timing:
                execution = {
                    "execution_time_s": float(timing.group(1)),
                    "clock_time_s": float(timing.group(2)),
                }
    if not raw_records:
        raise RuntimeError(f"no CLAMP_TRACE_RAW pressure records found in {log_path}")
    result: dict[str, object] = {
        "raw_pressure_records": len(raw_records),
        "pressure_floor_values_Pa": sorted({row["pMin_Pa"] for row in raw_records}),
        "minimum_raw_cell_pressure_Pa": min(row["raw_cell_p_min_Pa"] for row in raw_records),
        "maximum_raw_cell_pressure_Pa": max(row["raw_cell_p_max_Pa"] for row in raw_records),
        "sum_reported_cells_below_floor_across_pressure_passes": sum(
            row["cells_strictly_below_pMin"] for row in raw_records
        ),
        "sum_reported_clipped_water_volume_across_pressure_passes_m3": sum(
            row["clipped_water_volume_m3"] for row in raw_records
        ),
        "sum_reported_clipped_water_mass_across_pressure_passes_kg": sum(
            row["clipped_water_mass_kg"] for row in raw_records
        ),
        "qualification": "logged raw pressure/floor diagnostics; clipped fields are summed over pressure passes and are not a unique-cell removed-mass ledger",
    }
    if execution:
        result.update(execution)
    return result


def full_source_log_audit(log_path: Path) -> dict[str, object]:
    records: list[dict[str, float]] = []
    pattern = re.compile(r"^I4F_FULL_PREDICTOR_SOURCE_SUMMARY\s+(.*)$")
    numeric_fields = (
        "min_rDeltaT_minus_C_s-1",
        "full_R_max_s-1",
        "full_R_volume_L1_m3_s",
        "full_R_signed_volume_integral_m3_s",
        "predicted_Sp_only_lag_max_s-1",
        "predicted_Sp_only_lag_volume_L1_m3_s",
        "predicted_Sp_only_lag_signed_volume_integral_m3_s",
    )
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        values = dict(item.split("=", 1) for item in match.group(1).split() if "=" in item)
        if not all(name in values for name in numeric_fields):
            raise RuntimeError(f"incomplete full-source summary record in {log_path}")
        records.append({name: float(values[name]) for name in numeric_fields})
    if not records:
        raise RuntimeError(
            f"full-source run emitted no I4F_FULL_PREDICTOR_SOURCE_SUMMARY records: {log_path}"
        )

    def range_for(name: str) -> dict[str, float]:
        values = [row[name] for row in records]
        return {"minimum": min(values), "maximum": max(values)}

    if not all(math.isfinite(value) for row in records for value in row.values()):
        raise RuntimeError(f"nonfinite full-source diagnostic in {log_path}")
    return {
        "record_count": len(records),
        "min_rDeltaT_minus_C_s-1": min(row["min_rDeltaT_minus_C_s-1"] for row in records),
        "full_R_max_s-1_range": range_for("full_R_max_s-1"),
        "full_R_volume_L1_m3_s_range": range_for("full_R_volume_L1_m3_s"),
        "full_R_signed_volume_integral_m3_s_range": range_for("full_R_signed_volume_integral_m3_s"),
        "predicted_Sp_only_lag_max_s-1_range": range_for("predicted_Sp_only_lag_max_s-1"),
        "predicted_Sp_only_lag_volume_L1_m3_s_range": range_for(
            "predicted_Sp_only_lag_volume_L1_m3_s"
        ),
        "qualification": "discrete local alpha-equation residual and predicted lag term; neither is a global continuity or pressure residual; the separate follow-up diagnostic measures predictor-step alpha residual R_P, not a pressure-field residual",
    }


def native_state(case: Path, n: int, time_value: float) -> dict[str, object]:
    time_dir = case / f"{time_value:g}"
    needed = ["alpha.air", "alpha.water", "p", "T", "rho"]
    if not all((time_dir / field).is_file() for field in needed):
        missing = [field for field in needed if not (time_dir / field).is_file()]
        raise RuntimeError(f"{case}: native {time_value:g} missing {missing}")
    alpha_air = scalar_field(time_dir / "alpha.air", n)
    alpha_water = scalar_field(time_dir / "alpha.water", n)
    pressure = scalar_field(time_dir / "p", n)
    temperature = scalar_field(time_dir / "T", n)
    rho = scalar_field(time_dir / "rho", n)
    cell_volume = V0 / n
    gas_volume = sum(alpha_air) * cell_volume
    water_volume = sum(alpha_water) * cell_volume
    gas_cell_mass = [
        alpha_air[i] * pressure[i] / (R_AIR * temperature[i]) * cell_volume for i in range(n)
    ]
    gas_mass = sum(gas_cell_mass)
    gas_t_mass = sum(gas_cell_mass[i] * temperature[i] for i in range(n)) / gas_mass
    gas_u = sum(alpha_air[i] * pressure[i] * cell_volume for i in range(n)) / (GAMMA - 1.0)
    rho_expected = [
        alpha_water[i] * RHO_W + alpha_air[i] * pressure[i] / (R_AIR * temperature[i])
        for i in range(n)
    ]
    return {
        "time_s": time_value,
        "gas_volume_field_m3": gas_volume,
        "water_volume_field_m3": water_volume,
        "gas_mass_EOS_kg": gas_mass,
        "gas_temperature_mass_weighted_K": gas_t_mass,
        "gas_internal_energy_J": gas_u,
        "mixture_rho_EOS_max_abs_error_kg_m3": max(abs(rho[i] - rho_expected[i]) for i in range(n)),
        "field_sha256": {field: sha(time_dir / field) for field in needed},
    }


def analyze_arm(
    arm: dict[str, object], source_summary: dict[str, object]
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    name = str(arm["arm"])
    run_status_path = OUT / name / "run-status.json"
    run_status = json.loads(run_status_path.read_text(encoding="utf-8"))
    if run_status.get("status") != "normal_end_complete_0p4":
        raise RuntimeError(f"{name}: not a complete normal run: {run_status.get('status')}")
    if run_status.get("completed_time_lines") != 1600 or not run_status.get(
        "startup_mode_verified"
    ):
        raise RuntimeError(f"{name}: wrong number of steps or predictor mode not verified")
    case = ROOT / str(arm["case_path"])
    pp = case / "postProcessing"
    paths = {
        "water": pp / "waterVolume/0/volFieldValue.dat",
        "gas": pp / "gasVolume/0/volFieldValue.dat",
        "mixture": pp / "mixtureMass/0/volFieldValue.dat",
        "flux": pp / "withdrawWaterFlux/0/surfaceFieldValue.dat",
        "gas_state": pp / "gasMeanState/0/volFieldValue.dat",
    }
    data = {key: table(path) for key, path in paths.items()}
    times = [row[0] for row in data["water"]]
    if len(times) != 1600 or abs(times[-1] - END) > 1e-12:
        raise RuntimeError(f"{name}: expected 1600 rows to .4, got {len(times)} ending {times[-1]}")
    if max(abs((times[i] - times[i - 1]) - DT) for i in range(1, len(times))) > 1e-12:
        raise RuntimeError(f"{name}: nonuniform or mismatched fixed timestep")
    for key, rows in data.items():
        if (
            len(rows) != len(times)
            or max(abs(rows[i][0] - times[i]) for i in range(len(times))) > 1e-12
        ):
            raise RuntimeError(f"{name}: function-object time join mismatch in {key}")

    water = [VW0] + [row[1] for row in data["water"]]
    gas = [VG0] + [row[1] for row in data["gas"]]
    mixture = [RHO_W * VW0 + P0 * VG0 / (R_AIR * T0)] + [row[1] for row in data["mixture"]]
    flux = [Q0] + [row[1] for row in data["flux"]]
    gas_pressure = [P0] + [row[1] for row in data["gas_state"]]
    gas_temperature = [T0] + [row[2] for row in data["gas_state"]]
    time_values = [0.0] + times
    cumulative_water_out = [0.0]
    gas_work = [0.0]
    for i in range(1, len(time_values)):
        dt = time_values[i] - time_values[i - 1]
        cumulative_water_out.append(cumulative_water_out[-1] + 0.5 * (flux[i] + flux[i - 1]) * dt)
        gas_work.append(
            gas_work[-1] + 0.5 * (gas_pressure[i] + gas_pressure[i - 1]) * (gas[i] - gas[i - 1])
        )
    gas_mass_mixture = [mixture[i] - RHO_W * water[i] for i in range(len(time_values))]
    p_adiab = [P0 * (VG0 / volume) ** GAMMA for volume in gas]
    t_adiab = [T0 * (VG0 / volume) ** (GAMMA - 1.0) for volume in gas]
    history: list[dict[str, object]] = []
    for i, t in enumerate(time_values):
        history.append(
            {
                "arm": name,
                "grid_cells_x": arm["grid_cells_x"],
                "mode": arm["mode"],
                "time_s": t,
                "water_volume_m3": water[i],
                "gas_volume_m3": gas[i],
                "water_outflow_m3_s": flux[i],
                "integrated_water_outflow_m3": cumulative_water_out[i],
                "gas_mixture_mass_kg": gas_mass_mixture[i],
                "gas_p_volume_weighted_Pa": gas_pressure[i],
                "gas_T_volume_weighted_K": gas_temperature[i],
                "adiabatic_p_at_native_gas_volume_Pa": p_adiab[i],
                "adiabatic_T_at_native_gas_volume_K": t_adiab[i],
                "p_error_pct": 100.0 * (gas_pressure[i] / p_adiab[i] - 1.0),
                "T_volume_error_pct": 100.0 * (gas_temperature[i] / t_adiab[i] - 1.0),
                "water_balance_residual_m3": water[i] - VW0 + cumulative_water_out[i],
                "total_volume_m3": water[i] + gas[i],
                "gas_p_dV_work_J": gas_work[i],
            }
        )

    checkpoint_rows = []
    native_states = []
    for t in (0.05, 0.1, 0.2, 0.3, 0.4):
        state = native_state(case, int(arm["grid_cells_x"]), t)
        native_states.append(state)
        idx = round(t / DT)
        mixture_mass = gas_mass_mixture[idx]
        gas_energy_initial = P0 * VG0 / (GAMMA - 1.0)
        endpoint_or_checkpoint = {
            "arm": name,
            "grid_cells_x": arm["grid_cells_x"],
            "mode": arm["mode"],
            **state,
            "native_vs_function_gas_volume_m3": state["gas_volume_field_m3"] - gas[idx],
            "native_vs_function_water_volume_m3": state["water_volume_field_m3"] - water[idx],
            "gas_mass_from_mixture_kg": mixture_mass,
            "gas_mass_drift_pct": 100.0 * (mixture_mass / gas_mass_mixture[0] - 1.0),
            "gas_mass_EOS_minus_mixture_kg": state["gas_mass_EOS_kg"] - mixture_mass,
            "gas_p_volume_weighted_function_Pa": gas_pressure[idx],
            "adiabatic_p_at_native_volume_Pa": P0 * (VG0 / state["gas_volume_field_m3"]) ** GAMMA,
            "p_native_error_pct": 100.0
            * (gas_pressure[idx] / (P0 * (VG0 / state["gas_volume_field_m3"]) ** GAMMA) - 1.0),
            "gas_T_volume_weighted_function_K": gas_temperature[idx],
            "gas_T_mass_weighted_native_K": state["gas_temperature_mass_weighted_K"],
            "adiabatic_T_at_native_volume_K": T0
            * (VG0 / state["gas_volume_field_m3"]) ** (GAMMA - 1.0),
            "T_mass_error_pct": 100.0
            * (
                state["gas_temperature_mass_weighted_K"]
                / (T0 * (VG0 / state["gas_volume_field_m3"]) ** (GAMMA - 1.0))
                - 1.0
            ),
            "gas_internal_energy_plus_p_dV_residual_J": state["gas_internal_energy_J"]
            - gas_energy_initial
            + gas_work[idx],
            "gas_internal_energy_plus_p_dV_residual_pct_initial_Ug": 100.0
            * (state["gas_internal_energy_J"] - gas_energy_initial + gas_work[idx])
            / gas_energy_initial,
        }
        checkpoint_rows.append(endpoint_or_checkpoint)

    last = checkpoint_rows[-1]
    endpoint = {
        "arm": name,
        "grid_cells_x": arm["grid_cells_x"],
        "mode": arm["mode"],
        "container_id": run_status["container_id"],
        "started_at": run_status["started_at"],
        "completed_steps": run_status["completed_time_lines"],
        "endpoint_time_s": END,
        "status": run_status["status"],
        "initial_water_volume_m3": VW0,
        "initial_gas_volume_m3": VG0,
        "final_native_water_volume_m3": last["water_volume_field_m3"],
        "final_native_gas_volume_m3": last["gas_volume_field_m3"],
        "final_total_phase_volume_m3": last["water_volume_field_m3"] + last["gas_volume_field_m3"],
        "final_water_outflow_m3_s": flux[-1],
        "integrated_water_outflow_m3": cumulative_water_out[-1],
        "water_balance_residual_m3": last["water_volume_field_m3"] - VW0 + cumulative_water_out[-1],
        "final_gas_pressure_volume_weighted_Pa": gas_pressure[-1],
        "adiabatic_pressure_at_native_gas_volume_Pa": last["adiabatic_p_at_native_volume_Pa"],
        "final_pressure_error_pct": last["p_native_error_pct"],
        "final_gas_temperature_mass_weighted_K": last["gas_T_mass_weighted_native_K"],
        "adiabatic_temperature_at_native_gas_volume_K": last["adiabatic_T_at_native_volume_K"],
        "final_temperature_error_pct": last["T_mass_error_pct"],
        "final_gas_mass_from_mixture_kg": last["gas_mass_from_mixture_kg"],
        "gas_mass_drift_pct": last["gas_mass_drift_pct"],
        "native_gas_mass_EOS_kg": last["gas_mass_EOS_kg"],
        "native_gas_mass_EOS_minus_mixture_kg": last["gas_mass_EOS_minus_mixture_kg"],
        "final_energy_balance_residual_J": last["gas_internal_energy_plus_p_dV_residual_J"],
        "final_energy_balance_residual_pct_initial_Ug": last[
            "gas_internal_energy_plus_p_dV_residual_pct_initial_Ug"
        ],
        "native_mixture_rho_EOS_max_abs_error_kg_m3": last["mixture_rho_EOS_max_abs_error_kg_m3"],
        "source_mode_banner": run_status["startup_mode_banner"],
        "pressure_floor_audit": pressure_floor_audit(case / "log.compressibleInterFoam"),
        "full_predictor_source_audit": (
            full_source_log_audit(case / "log.compressibleInterFoam")
            if run_status["startup_mode_verified"]
            and str(run_status["startup_mode_banner"]).endswith("full_predictor_source=true")
            else None
        ),
        "run_status_path": str(run_status_path.relative_to(ROOT)),
        "log_sha256": sha(case / "log.compressibleInterFoam"),
        "endpoint_field_hashes": last["field_sha256"],
    }
    return endpoint, history, checkpoint_rows


def paired_history_deltas(
    histories: list[dict[str, object]], grid_cells_x: int
) -> tuple[list[dict[str, object]], dict[str, dict[str, float | int]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in histories:
        if int(row["grid_cells_x"]) == grid_cells_x:
            grouped.setdefault(str(row["arm"]), []).append(row)
    sp_name = f"n{grid_cells_x:04d}-sp-only"
    full_name = f"n{grid_cells_x:04d}-full-source"
    sp_rows = grouped[sp_name]
    full_rows = grouped[full_name]
    if [row["time_s"] for row in sp_rows] != [row["time_s"] for row in full_rows]:
        raise RuntimeError(f"{grid_cells_x}-cell history time grids do not match exactly")
    variables = (
        "water_volume_m3",
        "gas_volume_m3",
        "water_outflow_m3_s",
        "integrated_water_outflow_m3",
        "gas_mixture_mass_kg",
        "gas_p_volume_weighted_Pa",
        "gas_T_volume_weighted_K",
        "p_error_pct",
        "T_volume_error_pct",
    )
    deltas: list[dict[str, object]] = []
    maxima: dict[str, dict[str, float | int]] = {}
    for variable in variables:
        pairs = [
            (float(full[variable]) - float(sp[variable]), float(sp["time_s"]))
            for sp, full in zip(sp_rows, full_rows, strict=True)
        ]
        signed, time_at_max = max(pairs, key=lambda pair: abs(pair[0]))
        maxima[variable] = {
            "max_abs_full_minus_sp": abs(signed),
            "signed_at_max": signed,
            "time_of_max_s": time_at_max,
        }
        for sp, full in zip(sp_rows, full_rows, strict=True):
            deltas.append(
                {
                    "grid_cells_x": grid_cells_x,
                    "time_s": sp["time_s"],
                    "quantity": variable,
                    "sp_only": sp[variable],
                    "full_source": full[variable],
                    "full_minus_sp": float(full[variable]) - float(sp[variable]),
                }
            )
    return deltas, maxima


def paired_native_field_deltas(
    study: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, dict[str, dict[str, float | int]]]]:
    fields = ("alpha.air", "alpha.water", "p", "T", "rho")
    times = (0.05, 0.1, 0.2, 0.3, 0.4)
    output: list[dict[str, object]] = []
    maxima: dict[str, dict[str, dict[str, float | int]]] = {}
    arms = study["arms"]
    for grid in (60, 120):
        selected = [arm for arm in arms if int(arm["grid_cells_x"]) == grid]
        mode_arms = {str(arm["mode"]): arm for arm in selected}
        sp_arm = mode_arms["sp-only"]
        full_arm = mode_arms["full-source"]
        sp_manifest = {
            item["path"]: item["sha256"]
            for item in json.loads(Path(str(sp_arm["case_input_manifest"])).read_text())["files"]
        }
        full_manifest = {
            item["path"]: item["sha256"]
            for item in json.loads(Path(str(full_arm["case_input_manifest"])).read_text())["files"]
        }
        different_inputs = [
            path
            for path in sorted(set(sp_manifest) | set(full_manifest))
            if sp_manifest.get(path) != full_manifest.get(path)
        ]
        if different_inputs != ["system/controlDict"]:
            raise RuntimeError(
                f"unexpected matched-pair input differences at {grid} cells: {different_inputs}"
            )
        case_sp = ROOT / str(sp_arm["case_path"])
        case_full = ROOT / str(full_arm["case_path"])
        for time_value in times:
            record: dict[str, object] = {"grid_cells_x": grid, "time_s": time_value}
            for field in fields:
                left = scalar_field(case_sp / f"{time_value:g}" / field, grid)
                right = scalar_field(case_full / f"{time_value:g}" / field, grid)
                if len(left) != len(right):
                    raise RuntimeError(
                        f"paired {field} field lengths differ at {grid} cells, t={time_value:g}"
                    )
                differences = [b - a for a, b in zip(left, right, strict=True)]
                maximum = max(abs(value) for value in differences)
                rms = math.sqrt(sum(value * value for value in differences) / len(differences))
                reference_scale = max(abs(value) for value in left)
                record[f"{field}_max_abs_difference"] = maximum
                record[f"{field}_rms_difference"] = rms
                record[f"{field}_relative_to_sp_max"] = (
                    maximum / reference_scale if reference_scale else None
                )
                by_grid = maxima.setdefault(str(grid), {})
                previous = by_grid.get(field)
                if previous is None or maximum > float(previous["max_abs_difference"]):
                    by_grid[field] = {
                        "max_abs_difference": maximum,
                        "rms_difference_at_max": rms,
                        "relative_to_sp_max_at_max": maximum / reference_scale
                        if reference_scale
                        else None,
                        "time_of_max_s": time_value,
                    }
            record["only_static_input_difference"] = "system/controlDict"
            output.append(record)
    return output, maxima


def main() -> None:
    study = json.loads((OUT / "experiment.json").read_text(encoding="utf-8"))
    source_lock = json.loads((OUT / "source-lock.json").read_text(encoding="utf-8"))
    launches = json.loads((OUT / "launch-summary.json").read_text(encoding="utf-8"))
    if launches.get("status") != "all_four_normal_end":
        raise RuntimeError("analysis requires all four exact-ID runs to normal-End at .4 s")
    old_summary = json.loads((OLD / "analysis-summary.json").read_text(encoding="utf-8"))
    old_cases = {case["name"]: case for case in old_summary["cases"]}
    endpoints: list[dict[str, object]] = []
    histories: list[dict[str, object]] = []
    checkpoints: list[dict[str, object]] = []
    for arm in study["arms"]:
        endpoint, history, checkpoint_rows = analyze_arm(arm, old_summary)
        prior = old_cases[f"n{int(arm['grid_cells_x']):04d}"]["final"]
        endpoint["historical_solver_pressure_error_pct"] = prior["p_error_pct"]
        endpoint["historical_solver_T_massweighted_error_pct"] = prior["T_massweighted_error_pct"]
        endpoint["historical_solver_integrated_outflow_m3"] = prior["integrated_water_outflow_m3"]
        endpoints.append(endpoint)
        histories.extend(history)
        checkpoints.extend(checkpoint_rows)
    comparisons = []
    by_arm = {row["arm"]: row for row in endpoints}
    for n in (60, 120):
        sp = by_arm[f"n{n:04d}-sp-only"]
        full = by_arm[f"n{n:04d}-full-source"]
        comparisons.append(
            {
                "grid_cells_x": n,
                "comparison_time_s": END,
                "full_minus_sp_final_p_Pa": full["final_gas_pressure_volume_weighted_Pa"]
                - sp["final_gas_pressure_volume_weighted_Pa"],
                "full_minus_sp_pressure_error_percentage_points": full["final_pressure_error_pct"]
                - sp["final_pressure_error_pct"],
                "full_minus_sp_temperature_error_percentage_points": full[
                    "final_temperature_error_pct"
                ]
                - sp["final_temperature_error_pct"],
                "full_minus_sp_native_gas_volume_m3": full["final_native_gas_volume_m3"]
                - sp["final_native_gas_volume_m3"],
                "full_minus_sp_water_outflow_m3": full["integrated_water_outflow_m3"]
                - sp["integrated_water_outflow_m3"],
                "full_minus_sp_gas_mass_drift_percentage_points": full["gas_mass_drift_pct"]
                - sp["gas_mass_drift_pct"],
                "historical_sp_only_p_error_pct": sp["historical_solver_pressure_error_pct"],
                "new_sp_only_minus_historical_p_error_percentage_points": sp[
                    "final_pressure_error_pct"
                ]
                - sp["historical_solver_pressure_error_pct"],
            }
        )
    paired_history: list[dict[str, object]] = []
    history_maxima: dict[str, dict[str, dict[str, float | int]]] = {}
    for grid in (60, 120):
        deltas, maxima = paired_history_deltas(histories, grid)
        paired_history.extend(deltas)
        history_maxima[str(grid)] = maxima
    native_field_deltas, native_field_maxima = paired_native_field_deltas(study)
    report = {
        "schema": "i4f-full-source-gas-withdrawal-analysis/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "four exact-endpoint native results analyzed; exploratory diagnostic only",
        "study": str((OUT / "experiment.json").relative_to(ROOT)),
        "study_sha256": sha(OUT / "experiment.json"),
        "analysis_helper_sha256": sha(Path(__file__).resolve()),
        "historical_analysis": str((OLD / "analysis-summary.json").relative_to(ROOT)),
        "historical_analysis_sha256": sha(OLD / "analysis-summary.json"),
        "prototype_source_lock": str((OUT / "source-lock.json").relative_to(ROOT)),
        "prototype_source_lock_sha256": sha(OUT / "source-lock.json"),
        "full_source_alphaEqn_H_sha256": source_lock["prototype_source_file_hashes"][
            "VoF/alphaEqn.H"
        ],
        "thermodynamics": {
            "R_air_J_kg_K": R_AIR,
            "Cp_air_J_kg_K": CP_AIR,
            "gamma_air": GAMMA,
            "rho_water_kg_m3": RHO_W,
            "adiabatic_pressure_reference": "p0*(Vg0/Vg)^gamma at the native gas volume",
            "adiabatic_temperature_reference": "T0*(Vg0/Vg)^(gamma-1) at the native gas volume",
        },
        "qualifications": [
            "The comparison changes only i4fFrozenPredictorFullSource false versus true; Sp is true in both arms.",
            "Water is rhoConst and turbulence is laminar, matching the historical sealed-channel diagnostic; these are not apparatus material/turbulence inputs.",
            "The full-source branch is a private prototype, not a released solver change or formal validation result.",
            "Historical solver data are shown as context; the exact predictor comparison is the new matched-bin pair at each resolution.",
            "No interpretation attributes apparatus pressure-cycle behavior from this simplified sealed-channel test.",
        ],
        "arms": endpoints,
        "paired_comparisons": comparisons,
        "paired_history_max_abs_deltas": history_maxima,
        "paired_native_field_checkpoint_max_abs_deltas": native_field_maxima,
    }
    (OUT / "analysis-summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for name, rows in (
        ("time-history.csv", histories),
        ("native-checkpoints.csv", checkpoints),
        ("paired-comparison.csv", comparisons),
        ("paired-history-deltas.csv", paired_history),
        ("paired-native-field-deltas.csv", native_field_deltas),
    ):
        with (OUT / name).open("w", newline="", encoding="utf-8") as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    with (OUT / "endpoints.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(endpoints[0]))
        writer.writeheader()
        writer.writerows(endpoints)
    print(
        json.dumps(
            {
                "analysis_summary": str((OUT / "analysis-summary.json").relative_to(ROOT)),
                "paired_comparisons": comparisons,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
