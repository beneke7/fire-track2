#!/usr/bin/env python3
"""Summarize the three captured one-step arms and test observer passivity."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

BUNDLE = Path(__file__).resolve().parents[1]
ARMS = ("baseline-12d8-predictor-no", "predictor-no", "predictor-yes")
CELL_SPEC = {
    0: {"local_cell": 5154, "native_C_m": [2.2531251578440923, -0.7860508002907803, 0.36086487255256816]},
    5: {"local_cell": 4440, "native_C_m": [2.2531251842343183, 0.7860320548022439, 0.3608467912323964]},
}
CORE_FIELDS = ("alpha.water", "p", "p_rgh", "T", "U", "k", "omega", "nut", "alphat", "rho", "phi", "alphaPhi0.water", "T.air", "T.water")
KV_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
MPI_RE = re.compile(r"^\s*\[\d+\]\s*")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def numeric(row: dict[str, str], key: str) -> float | None:
    token = row.get(key, "")
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def instrumentation_summary(arm: str) -> dict[str, Any]:
    case = BUNDLE / "cases" / arm / "case"
    result: dict[str, Any] = {"arm": arm, "ranks": {}}
    for rank, spec in CELL_SPEC.items():
        path = case / f"i4f_firststep_energy_rank{rank}.csv"
        rows = read_rows(path)
        selected: dict[str, dict[str, str]] = {}
        for stage in ("before_UEqn", "before_TEqn_after_UEqn", "after_TEqn"):
            candidates = [row for row in rows if row.get("stage") == stage]
            if candidates:
                selected[stage] = candidates[0]
        p_rows = [row for row in rows if row.get("stage") == "after_pEqn_pressure_corrector"]
        p_row = p_rows[0] if p_rows else None
        before_u = selected.get("before_UEqn")
        before_t = selected.get("before_TEqn_after_UEqn")
        after_t = selected.get("after_TEqn")
        if not rows:
            result["ranks"][str(rank)] = {"csv_path": str(path.relative_to(BUNDLE)), "exists": False}
            continue
        cell = {"expected_local_cell": spec["local_cell"], "expected_native_C_m": spec["native_C_m"],
                "csv_path": str(path.relative_to(BUNDLE)), "row_count": len(rows),
                "stage_counts": {stage: sum(1 for row in rows if row.get("stage") == stage)
                                 for stage in sorted({row.get("stage", "") for row in rows})},
                "first_sample_time_s": numeric(rows[0], "time_s"),
                "first_sample_deltaT_s": numeric(rows[0], "deltaT_s")}
        if before_u:
            cell["before_UEqn"] = {key: numeric(before_u, key) for key in (
                "x_m", "y_m", "z_m", "Ux_m_s", "Uy_m_s", "Uz_m_s", "K_m2_s2", "T_K", "p_Pa", "rho_kg_m3",
                "rho_water_kg_m3", "rho_air_kg_m3", "alpha_water", "alpha_air",
                "Cv_water_J_kgK", "Cv_air_J_kgK", "psi_air_kg_m3_Pa",
                "global_min_T_K", "global_min_p_field_Pa")}
        if before_t:
            cell["before_TEqn_after_UEqn"] = {key: numeric(before_t, key) for key in (
                "Ux_m_s", "Uy_m_s", "Uz_m_s", "K_m2_s2", "K_old_m2_s2", "T_K", "p_Pa",
                "rho_kg_m3", "rho_old_kg_m3", "divUp_W_m3", "ddt_rhoK_W_m3",
                "rho_water_kg_m3", "rho_air_kg_m3", "alpha_water", "alpha_air",
                "Cv_water_J_kgK", "Cv_air_J_kgK", "psi_air_kg_m3_Pa",
                "div_rhoPhiK_W_m3", "contErr_times_K_W_m3", "explicit_energy_sum_W_m3",
                "T_rate_divUp_K_s", "T_rate_ddt_rhoK_K_s", "T_rate_div_rhoPhiK_K_s",
                "T_rate_contErrK_K_s", "T_rate_explicit_source_only_K_s",
                "rhoK_storage_rate_estimate_W_m3", "global_min_T_K", "global_min_p_field_Pa")}
        if after_t:
            cell["after_TEqn"] = {key: numeric(after_t, key) for key in (
                "Ux_m_s", "Uy_m_s", "Uz_m_s", "K_m2_s2", "T_K", "p_Pa", "rho_kg_m3",
                "global_min_T_K", "global_min_p_field_Pa")}
        if before_u and before_t:
            cell["momentum_predictor_delta_K_m2_s2"] = numeric(before_t, "K_m2_s2") - numeric(before_u, "K_m2_s2")
            cv_air = numeric(before_t, "Cv_air_J_kgK")
            delta_k = cell["momentum_predictor_delta_K_m2_s2"]
            cell["air_kinetic_energy_temperature_equivalent_K"] = -delta_k / cv_air if cv_air else None
            cell["momentum_predictor_delta_U_m_s"] = {
                component: numeric(before_t, f"U{component}_m_s") - numeric(before_u, f"U{component}_m_s")
                for component in ("x", "y", "z")}
        if before_t and after_t:
            delta_t = numeric(before_t, "deltaT_s")
            actual = numeric(after_t, "T_K") - numeric(before_t, "T_K")
            source_rate = numeric(before_t, "T_rate_explicit_source_only_K_s")
            predicted = source_rate * delta_t if delta_t is not None and source_rate is not None else None
            cell["TEqn_temperature_change"] = {
                "T_before_TEqn_K": numeric(before_t, "T_K"),
                "T_after_TEqn_K": numeric(after_t, "T_K"),
                "actual_deltaT_K": actual,
                "preTEqn_explicit_source_only_predicted_deltaT_K": predicted,
                "actual_minus_source_only_K": actual - predicted if predicted is not None else None,
                "interpretation": "The explicit source-only estimate is not the full TEqn closure; the remainder includes implicit and thermodynamic effects.",
            }
        if p_row:
            cell["first_after_pEqn_field_state"] = {key: numeric(p_row, key) for key in (
                "pressure_corrector", "p_Pa", "T_K", "global_min_T_K", "global_min_p_field_Pa")}
        cell["pressure_field_scope"] = "global_min_p_field_Pa is the current p field at the observation stage; it can be pMin-clamped and is not the raw pre-clamp minimum."
        result["ranks"][str(rank)] = cell
    return result


def raw_pressure_records(arm: str) -> dict[str, Any]:
    case = BUNDLE / "cases" / arm / "case"
    path = case / "log.energy-audit"
    records = []
    if path.is_file():
        for original in path.read_text(errors="replace").splitlines():
            line = MPI_RE.sub("", original)
            if "CLAMP_TRACE_RAW" not in line:
                continue
            values = dict(KV_RE.findall(line))
            record: dict[str, Any] = {"raw_line": original[:1000]}
            for key in ("time_s", "pass", "raw_cell_p_min_Pa", "pMin_Pa", "cells_strictly_below_pMin", "clipped_water_mass_kg", "clipped_water_volume_m3"):
                if key in values:
                    try:
                        record[key] = float(values[key])
                    except ValueError:
                        record[key] = values[key]
            if "raw_cell_p_min_Pa" in record and "pMin_Pa" in record:
                record["strictly_below_pMin"] = record["raw_cell_p_min_Pa"] < record["pMin_Pa"]
            records.append(record)
    contact = [row for row in records if row.get("strictly_below_pMin") is True]
    return {"log_path": str(path.relative_to(BUNDLE)), "log_sha256": sha(path) if path.is_file() else None,
            "record_count": len(records), "raw_floor_contact_count": len(contact),
            "records": records, "contacts": contact,
            "scope": "These are raw corrector pre-clamp minima from CLAMP_TRACE_RAW; the instrumented CSV p field minimum is after the solver's clamp at the corresponding capture stage."}


def endpoint(arm: str) -> tuple[dict[str, Any], Path | None]:
    status_path = BUNDLE / "arms" / arm / "guardian-status.json"
    if not status_path.is_file():
        raise RuntimeError(f"missing guardian status for {arm}")
    status = json.loads(status_path.read_text())
    if status.get("status") != "normal_End_complete_native_one_step":
        raise RuntimeError(f"arm {arm} is not captured as a complete normal-End one-step run: {status.get('status')}")
    ep = status.get("endpoint") or {}
    path = BUNDLE / ep["path"]
    return {"status": status["status"], "container_id": status["container_id"],
            "docker_started_at": status["docker_started_at"], "completed_time_s": ep.get("time_s"),
            "normal_End": status.get("normal_End"), "docker_exit_code": status.get("docker_exit_code"),
            "log_path": status.get("expected_log"), "log_sha256": sha(Path(status["expected_log"])),
            "endpoint": ep}, path


def observer_passivity(baseline: Path, observed: Path) -> dict[str, Any]:
    fields = list(CORE_FIELDS) + ["dgdt"]
    baseline_case = baseline.parents[1]
    observed_case = observed.parents[1]
    baseline_arm = baseline.parents[2].name
    observed_arm = observed.parents[2].name
    baseline_freeze = json.loads((baseline_case.parent / "case-freeze.json").read_text())
    observed_freeze = json.loads((observed_case.parent / "case-freeze.json").read_text())
    baseline_manifest = BUNDLE / "arms" / baseline_arm / "case-inputs.sha256"
    observed_manifest = BUNDLE / "arms" / observed_arm / "case-inputs.sha256"
    rows = []
    for field in fields:
        a, b = baseline / field, observed / field
        if not a.is_file() or not b.is_file():
            rows.append({"field": field, "available_in_both": False,
                         "baseline_exists": a.is_file(), "instrumented_exists": b.is_file()})
            continue
        ah, bh = sha(a), sha(b)
        rows.append({"field": field, "available_in_both": True,
                     "baseline_bytes": a.stat().st_size, "instrumented_bytes": b.stat().st_size,
                     "baseline_sha256": ah, "instrumented_sha256": bh,
                     "byte_identical": ah == bh})
    return {"comparison":"baseline 12d8, predictor=no vs read-only energy-audit binary, predictor=no",
            "baseline_case_static_tree_sha256": baseline_freeze["static_tree_sha256"],
            "instrumented_case_static_tree_sha256": observed_freeze["static_tree_sha256"],
            "same_case_input_static_hash": baseline_freeze["static_tree_sha256"] == observed_freeze["static_tree_sha256"],
            "baseline_case_inputs_manifest_sha256": sha(baseline_manifest),
            "instrumented_case_inputs_manifest_sha256": sha(observed_manifest),
            "case_inputs_manifest_byte_identical": sha(baseline_manifest) == sha(observed_manifest),
            "fields": rows,
            "uniform_time_byte_identical": sha(baseline / "uniform/time") == sha(observed / "uniform/time"),
            "uniform_time_sha256_baseline": sha(baseline / "uniform/time"),
            "uniform_time_sha256_instrumented": sha(observed / "uniform/time"),
            "interpretation":"Native output bytes directly test observer passivity for this same cold one-step case; this is not evidence about all solver versions or timesteps."}


def main() -> int:
    experiment = json.loads((BUNDLE / "experiment.json").read_text())
    summary: dict[str, Any] = {
        "schema":"i4f-firststep-energy-audit-results/v1",
        "experiment_sha256":sha(BUNDLE / "experiment.json"),
        "instrumented_binary_sha256":sha(BUNDLE / "bin/compressibleInterFoamI4FFirstStepEnergyAudit"),
        "baseline_binary_sha256":sha(BUNDLE / "bin/compressibleInterFoamI4FColdRestartConsistent"),
        "instrumented_source_delta_sha256":sha(BUNDLE / "provenance/instrumented-source-delta.json"),
        "cases":{},
        "interpretation":"One true-cold 12 microsecond step per arm. Raw corrector pressure minima are reported separately from the post-clamp p-field minimum. Energy source components support a local budget; source-only temperature-rate terms are not full TEqn closure.",
    }
    endpoints = {}
    for arm in ARMS:
        ep, path = endpoint(arm)
        endpoints[arm] = path
        raw = raw_pressure_records(arm)
        row: dict[str, Any] = {
            "terminal": ep,
            "raw_pressure": raw,
            "physical_screen_interpretation": (
                "normal End and one-step fields captured, but do not classify as healthy: raw pressure fell below pMin"
                if raw["raw_floor_contact_count"]
                else "normal End and one-step fields captured with no raw-pressure pMin contact; exploratory diagnostic only"
            ),
        }
        if arm != "baseline-12d8-predictor-no":
            row["local_energy_terms"] = instrumentation_summary(arm)
        summary["cases"][arm] = row
    summary["observer_passivity_predictor_no"] = observer_passivity(
        endpoints["baseline-12d8-predictor-no"], endpoints["predictor-no"])
    out = BUNDLE / "analysis"
    out.mkdir(exist_ok=True)
    (out / "firststep-energy-audit-results.json").write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+"\n")
    with (out / "firststep-energy-audit-cell-summary.csv").open("w",newline="") as stream:
        columns=["arm","rank","local_cell","time_s","deltaT_s","T_before_TEqn_K","T_after_TEqn_K","actual_deltaT_K",
                 "source_only_predicted_deltaT_K","actual_minus_source_only_K","Cv_air_J_kgK","kinetic_deltaT_equivalent_K",
                 "K_before_UEqn_m2_s2","K_after_UEqn_m2_s2",
                 "momentum_predictor_delta_K_m2_s2","raw_floor_contact_count","raw_min_p_Pa","clamped_min_p_field_Pa"]
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for arm in ("predictor-no","predictor-yes"):
            energy=summary["cases"][arm]["local_energy_terms"]["ranks"]
            raw=summary["cases"][arm]["raw_pressure"]
            contacts=raw["contacts"]
            rawmin=min((r["raw_cell_p_min_Pa"] for r in raw["records"] if "raw_cell_p_min_Pa" in r),default=None)
            for rank,cell in energy.items():
                before=cell.get("before_TEqn_after_UEqn",{}); after=cell.get("after_TEqn",{}); before_u=cell.get("before_UEqn",{}); temp=cell.get("TEqn_temperature_change",{})
                writer.writerow({"arm":arm,"rank":rank,"local_cell":CELL_SPEC[int(rank)]["local_cell"],
                    "time_s":cell.get("first_sample_time_s"),"deltaT_s":cell.get("first_sample_deltaT_s"),
                    "T_before_TEqn_K":before.get("T_K"),"T_after_TEqn_K":after.get("T_K"),
                    "actual_deltaT_K":temp.get("actual_deltaT_K"),
                    "source_only_predicted_deltaT_K":temp.get("preTEqn_explicit_source_only_predicted_deltaT_K"),
                    "actual_minus_source_only_K":temp.get("actual_minus_source_only_K"),
                    "Cv_air_J_kgK":before.get("Cv_air_J_kgK"),
                    "kinetic_deltaT_equivalent_K":cell.get("air_kinetic_energy_temperature_equivalent_K"),
                    "K_before_UEqn_m2_s2":before_u.get("K_m2_s2"),"K_after_UEqn_m2_s2":before.get("K_m2_s2"),
                    "momentum_predictor_delta_K_m2_s2":cell.get("momentum_predictor_delta_K_m2_s2"),
                    "raw_floor_contact_count":len(contacts),"raw_min_p_Pa":rawmin,
                    "clamped_min_p_field_Pa":(cell.get("first_after_pEqn_field_state") or {}).get("global_min_p_field_Pa")})
    print(json.dumps({"summary":str((out/"firststep-energy-audit-results.json").relative_to(BUNDLE)),
                      "passivity":summary["observer_passivity_predictor_no"],
                      "arms":{arm:summary["cases"][arm]["terminal"]["completed_time_s"] for arm in ARMS}},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
