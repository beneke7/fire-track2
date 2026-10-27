#!/usr/bin/env python3
"""Extract compact paired alpha/flux diagnostic evidence from captured runs."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARMS = ROOT / "arms"
ORIGINAL_C = Path("results/runs/i4f-water-feedback-map-20261027T003208Z")
OUT = ROOT / "analysis"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return (list(rows[0]) if rows else [], rows)


def stats(rows: list[dict[str, str]], field: str) -> dict[str, float | int | None]:
    vals = [float(row[field]) for row in rows if row.get(field, "") not in (None, "")]
    if not vals:
        return {"count": 0, "first": None, "last": None, "mean_first4": None,
                "mean_last4": None, "mean_first8": None, "mean_last8": None,
                "last_over_first": None, "minimum": None, "maximum": None}
    first = vals[0]
    return {
        "count": len(vals),
        "first": first,
        "last": vals[-1],
        "mean_first4": sum(vals[:4]) / len(vals[:4]),
        "mean_last4": sum(vals[-4:]) / len(vals[-4:]),
        "mean_first8": sum(vals[:8]) / len(vals[:8]),
        "mean_last8": sum(vals[-8:]) / len(vals[-8:]),
        "mean_last4_over_first4": (sum(vals[-4:]) / len(vals[-4:])) / (sum(vals[:4]) / len(vals[:4]))
        if sum(vals[:4]) else None,
        "mean_last8_over_first8": (sum(vals[-8:]) / len(vals[-8:])) / (sum(vals[:8]) / len(vals[:8]))
        if sum(vals[:8]) else None,
        "last_over_first": vals[-1] / first if first else None,
        "minimum": min(vals),
        "maximum": max(vals),
    }


def log_phase_continuity(path: Path) -> dict[int, dict[str, float | int]]:
    pattern = re.compile(
        r"I4F_PHASE_MASS_STATE time_s=(\S+) pass=(\d+) "
        r"alpha_flux_relax_sweep=(\d+) stage=after_correctRho "
        r".*?water_cont_max_kg_m3_s=(\S+) "
        r"water_cont_L1_nativeV_kg_s=(\S+) "
        r"water_cont_signed_nativeV_kg_s=(\S+) "
        r"gas_cont_max_kg_m3_s=(\S+) "
        r"gas_cont_L1_nativeV_kg_s=(\S+) "
        r"gas_cont_signed_nativeV_kg_s=(\S+)"
    )
    # Each map sweep has two after-correctRho rows, one per pressure corrector.
    # Keep the larger pass number as the final correction for that sweep.
    final: dict[int, dict[str, float | int]] = {}
    with path.open(errors="replace") as stream:
        for line in stream:
            match = pattern.search(line)
            if not match:
                continue
            time_s, pass_i, sweep, wmax, wl1, wsigned, gmax, gl1, gsigned = match.groups()
            sweep_i = int(sweep)
            row: dict[str, float | int] = {
                "pass": int(pass_i),
                "time_s": float(time_s),
                "water_cont_max_kg_m3_s": float(wmax),
                "water_cont_L1_nativeV_kg_s": float(wl1),
                "water_cont_signed_nativeV_kg_s": float(wsigned),
                "gas_cont_max_kg_m3_s": float(gmax),
                "gas_cont_L1_nativeV_kg_s": float(gl1),
                "gas_cont_signed_nativeV_kg_s": float(gsigned),
            }
            if sweep_i not in final or row["pass"] > final[sweep_i]["pass"]:
                final[sweep_i] = row
    return final


def docker_state(container_id: str) -> dict[str, object] | None:
    try:
        obj = json.loads(subprocess.check_output(["docker", "inspect", container_id], text=True))[0]
    except (subprocess.CalledProcessError, IndexError):
        return None
    return {
        "status": obj["State"]["Status"],
        "exit_code": obj["State"].get("ExitCode"),
        "started_at": obj["State"].get("StartedAt"),
        "finished_at": obj["State"].get("FinishedAt"),
        "actual_nano_cpus": obj["HostConfig"].get("NanoCpus"),
        "log_driver": obj["HostConfig"].get("LogConfig", {}).get("Type"),
    }


def arm_metrics(tag: str) -> dict[str, object]:
    arm = ARMS / tag
    diag = arm / "case/i4f_alpha_flux_relax_map"
    _, summary = load_csv(diag / "summary.csv")
    _, residual = load_csv(diag / "source_residual.csv")
    log_path = arm / "logs/alpha-flux-relax-solver.log"
    continuity = log_phase_continuity(log_path)
    marker = json.loads((arm / "guardian-status.json").read_text())
    launch = json.loads((arm / "launch-manifest.json").read_text())
    cstate = docker_state(launch["container_id"])

    keep_fields = [
        "sweep", "time_s", "time_index", "deltaT_s", "max_abs_dp_Pa",
        "max_abs_dU_m_s", "max_abs_dalphaPhi1_m3_s", "max_abs_drhoPhi_kg_s",
        "same_time_delta_water_inventory_kg", "same_time_delta_gas_inventory_kg",
        "max_abs_dGamma_s-1", "max_abs_dalpha1", "max_abs_dalpha2",
        "dp_projection_previous", "dp_alignment_cosine_previous",
        "dp_volume_norm_ratio_previous", "dp_projection_defined",
    ]
    residual_fields = [
        "sweep", "omega", "alpha_hat_delta_L1", "alpha_hat_delta_rms",
        "alpha_applied_delta_L1", "alpha_applied_delta_rms",
        "F_hat_delta_max_m3_s", "F_hat_delta_sumAbs_m3_s",
        "F_applied_delta_max_m3_s", "F_applied_delta_sumAbs_m3_s",
        "L_candidate_L1_s-1", "L_applied_L1_s-1", "S_candidate_L1_s-1",
        "S_candidate_cached_L1_s-1", "S_applied_L1_s-1",
        "R_candidate_L1_s-1", "R_applied_L1_s-1",
        "R_candidate_rms_s-1", "R_applied_rms_s-1",
        "R_candidate_max_s-1", "R_applied_max_s-1",
        "R_candidate_cached_L1_s-1",
        "R_blend_defect_L1_s-1", "R_blend_defect_max_s-1",
        "S_blend_defect_L1_s-1", "S_blend_defect_max_s-1",
        "L_blend_identity_max_s-1",
        "identity_tolerance_s-1", "cached_source_lag_L1_s-1",
        "alpha_blend_identity_max", "flux_blend_identity_max_m3_s",
        "denominator_floor_cells_applied", "alpha_gt_one_cells_applied",
    ]
    rows = []
    for srow, rrow in zip(summary, residual, strict=True):
        row: dict[str, object] = {
            field: float(srow[field]) if field not in {"sweep", "time_index", "dp_projection_defined"}
            else int(float(srow[field]))
            for field in keep_fields
        }
        for field in residual_fields:
            if field == "sweep":
                continue
            row[field] = float(rrow[field]) if field not in {
                "denominator_floor_cells_applied", "alpha_gt_one_cells_applied"
            } else int(float(rrow[field]))
        sweep_i = int(float(srow["sweep"]))
        row.update({f"postEOS_{k}": v for k, v in continuity.get(sweep_i, {}).items()})
        rows.append(row)

    metric_fields = [
        "max_abs_dp_Pa", "max_abs_dU_m_s", "dp_alignment_cosine_previous",
        "dp_projection_previous", "dp_volume_norm_ratio_previous",
        "alpha_hat_delta_L1", "alpha_hat_delta_rms", "alpha_applied_delta_L1",
        "alpha_applied_delta_rms", "F_hat_delta_max_m3_s", "F_hat_delta_sumAbs_m3_s",
        "F_applied_delta_max_m3_s", "F_applied_delta_sumAbs_m3_s",
        "R_candidate_L1_s-1", "R_applied_L1_s-1",
        "R_candidate_rms_s-1", "R_applied_rms_s-1",
        "R_candidate_max_s-1", "R_applied_max_s-1",
        "R_candidate_cached_L1_s-1", "cached_source_lag_L1_s-1",
        "S_blend_defect_L1_s-1", "S_blend_defect_max_s-1",
        "R_blend_defect_L1_s-1", "R_blend_defect_max_s-1",
        "postEOS_water_cont_L1_nativeV_kg_s",
        "postEOS_water_cont_max_kg_m3_s", "postEOS_gas_cont_L1_nativeV_kg_s",
        "postEOS_gas_cont_max_kg_m3_s",
    ]
    metrics = {name: stats(rows, name) for name in metric_fields}

    def max_abs(field: str) -> float:
        return max(abs(float(row[field])) for row in residual)

    checks = {
        "max_alpha_blend_identity": max_abs("alpha_blend_identity_max"),
        "max_flux_blend_identity_m3_s": max_abs("flux_blend_identity_max_m3_s"),
        "max_flux_blend_tolerance_m3_s": max_abs("flux_blend_tolerance_m3_s"),
        "max_L_blend_identity_s-1": max_abs("L_blend_identity_max_s-1"),
        "max_L_blend_roundoff_tolerance_s-1": max_abs("L_blend_identity_tolerance_s-1"),
        "max_residual_source_identity_s-1": max_abs("residual_source_identity_max_s-1"),
        "max_residual_identity_tolerance_s-1": max_abs("identity_tolerance_s-1"),
        "max_R_blend_defect_s-1": max_abs("R_blend_defect_max_s-1"),
        "max_S_blend_defect_s-1": max_abs("S_blend_defect_max_s-1"),
    }
    checks["max_flux_blend_identity_over_tolerance"] = (
        checks["max_flux_blend_identity_m3_s"] / checks["max_flux_blend_tolerance_m3_s"]
    )
    checks["max_L_blend_identity_over_tolerance"] = (
        checks["max_L_blend_identity_s-1"] / checks["max_L_blend_roundoff_tolerance_s-1"]
    )
    checks["max_residual_source_identity_over_tolerance"] = (
        checks["max_residual_source_identity_s-1"] / checks["max_residual_identity_tolerance_s-1"]
    )

    return {
        "arm": tag,
        "omega": float(json.loads((arm / "experiment.json").read_text())[
            "alpha_flux_relaxation_map"]["omega"]),
        "container_id": launch["container_id"],
        "started_at": launch["docker_started_at"],
        "docker": cstate,
        "guard": {
            "status": marker["status"],
            "marker": marker.get("diagnostic_marker"),
            "fatal_line": marker.get("fatal_line"),
            "stop_action": marker.get("stop_action"),
        },
        "hashes": {
            "solver_log_sha256": sha256(log_path),
            "summary_csv_sha256": sha256(diag / "summary.csv"),
            "source_residual_csv_sha256": sha256(diag / "source_residual.csv"),
            "case_input_manifest_sha256": json.loads((arm / "provenance/case-freeze.json").read_text())[
                "case_input_manifest_sha256"
            ],
            "source_manifest_sha256": launch["source_manifest_sha256"],
            "binary_sha256": launch["binary_sha256"],
        },
        "sweep_count": len(rows),
        "postEOS_after_correctRho_rows_for_map_sweeps": sum(1 for n in continuity if 1 <= n <= len(rows)),
        "pre_map_after_correctRho_record_count": int(0 in continuity),
        "metrics_first_last_eight": metrics,
        "algebraic_identity_checks": checks,
        "sweeps": rows,
    }


def main() -> None:
    arms = {tag: arm_metrics(tag) for tag in ["omega-100", "omega-050"]}
    c_header, c_rows = load_csv(ORIGINAL_C / "case/i4f_water_feedback_map/summary.csv")
    new_header, new_rows = load_csv(ARMS / "omega-100/case/i4f_alpha_flux_relax_map/summary.csv")
    common = [field for field in c_header if field in new_header]
    comparisons = []
    for i in range(min(8, len(c_rows), len(new_rows))):
        unequal = [field for field in common if c_rows[i][field] != new_rows[i][field]]
        comparisons.append({"sweep": i + 1, "identical_common_fields": not unequal,
                            "unequal_fields": unequal})
    out = {
        "schema": "i4f-alpha-flux-relax-pair-analysis/v1",
        "observed_utc": subprocess.check_output(
            ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
        ).strip(),
        "scope": "Two completed same-trigger diagnostic maps, not physical continuation or validation.",
        "trigger": {"time_s": 0.4938444922371094, "time_index": 2736,
                    "deltaT_s": 9.514090971421265e-05, "sweeps": 16,
                    "pressure_correctors_per_sweep": 2},
        "original_C_default_identity": {
            "bundle": str(ORIGINAL_C),
            "summary_csv_sha256": sha256(ORIGINAL_C / "case/i4f_water_feedback_map/summary.csv"),
            "compared_columns": common,
            "first_eight_row_comparisons": comparisons,
            "all_first_eight_common_fields_identical": all(x["identical_common_fields"] for x in comparisons),
        },
        "interpretation_notes": [
            "alpha_hat_delta_* and F_hat_delta_* are unrelaxed stock-MULES candidate changes from each sweep entry; applied changes are recorded separately.",
            "postEOS continuity is the last after_correctRho record of each sweep, using ddt(alpha*rho)+div(alphaPhi*rhoFace), native-volume L1 in kg/s and local max in kg/m3/s; repeated sweeps do not advance physical time.",
            "dp projection, alignment cosine, and volume norm ratio compare consecutive same-time pressure increments; values near -1 and ratio near 1 indicate a persistent sign-alternating increment in that diagnostic map.",
            "The same-time map outputs are not physical checkpoints and do not prove long-horizon apparatus behavior.",
        ],
        "arms": arms,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "paired-map-analysis.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    columns = [
        "arm", "omega", "sweep", "max_abs_dp_Pa", "dp_projection_previous",
        "dp_alignment_cosine_previous", "dp_volume_norm_ratio_previous",
        "alpha_hat_delta_L1", "alpha_applied_delta_L1", "F_hat_delta_max_m3_s",
        "F_applied_delta_max_m3_s", "R_candidate_L1_s-1", "R_applied_L1_s-1",
        "postEOS_water_cont_L1_nativeV_kg_s", "postEOS_gas_cont_L1_nativeV_kg_s",
    ]
    with (OUT / "paired-map-sweeps.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for tag, arm in arms.items():
            for row in arm["sweeps"]:
                writer.writerow({"arm": tag, "omega": arm["omega"], **{k: row.get(k) for k in columns[2:]}})
    print(OUT / "paired-map-analysis.json")
    print(OUT / "paired-map-sweeps.csv")


if __name__ == "__main__":
    main()
