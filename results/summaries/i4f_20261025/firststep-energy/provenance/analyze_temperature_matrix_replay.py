#!/usr/bin/env python3
"""Summarize the matched first-step FV temperature-matrix replay."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

BUNDLE = Path(__file__).resolve().parents[1]
ROOT = BUNDLE.parents[2]
PARENT = ROOT / "results/runs/i4f-cold-firststep-energy-audit-20261026T2032Z"
ARM = "predictor-yes-matrix"
RANKS = {0: 5154, 5: 4440}
FIELDS = (
    "alpha.water", "p", "p_rgh", "T", "U", "k", "omega", "nut", "alphat",
    "rho", "phi", "alphaPhi0.water", "T.air", "T.water", "dgdt",
)
STAGES = (
    "assembled_before_relax", "after_relax_before_options_constrain",
    "before_solve_after_options_constrain", "after_solve_before_options_correct",
    "after_options_correct_before_thermo", "after_thermo_correct",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def number(row: dict[str, str], key: str) -> float:
    return float(row[key])


def main() -> int:
    replay_status_path = BUNDLE / "arms" / ARM / "guardian-status.json"
    parent_status_path = PARENT / "arms/predictor-yes/guardian-status.json"
    replay_status = json.loads(replay_status_path.read_text())
    parent_status = json.loads(parent_status_path.read_text())
    launch_path = BUNDLE / "arms" / ARM / "launch-manifest.json"
    launch = json.loads(launch_path.read_text())
    go_path = BUNDLE / "arms" / ARM / "GO"
    if replay_status.get("status") != "normal_End_complete_native_one_step":
        raise RuntimeError(f"matrix replay is not fully captured: {replay_status.get('status')}")
    if parent_status.get("status") != "normal_End_complete_native_one_step":
        raise RuntimeError(f"parent predictor-on arm is not fully captured: {parent_status.get('status')}")
    replay_ep = replay_status["endpoint"]
    parent_ep = parent_status["endpoint"]
    replay_dir = BUNDLE / replay_ep["path"]
    parent_dir = PARENT / parent_ep["path"]
    replay_freeze = json.loads((BUNDLE / "cases/predictor-yes-matrix/case-freeze.json").read_text())
    parent_freeze = json.loads((PARENT / "cases/predictor-yes/case-freeze.json").read_text())
    same_frozen_inputs = replay_freeze["static_tree_sha256"] == parent_freeze["static_tree_sha256"]
    if not same_frozen_inputs:
        raise RuntimeError("matrix replay input tree does not match its parent predictor-on arm")
    fv_solution = (BUNDLE / "cases/predictor-yes-matrix/case/system/fvSolution").read_text()
    fv_solution_without_comments = "\n".join(line.split("//", 1)[0] for line in fv_solution.splitlines())
    passivity = []
    for field in FIELDS:
        left = replay_dir / field
        right = parent_dir / field
        if not left.is_file() or not right.is_file():
            passivity.append({"field": field, "present_in_both": False})
        else:
            lh, rh = sha(left), sha(right)
            passivity.append({"field": field, "present_in_both": True,
                              "bytes": left.stat().st_size, "replay_sha256": lh,
                              "parent_sha256": rh, "byte_identical": lh == rh})
    replay_time = replay_dir / "uniform/time"
    parent_time = parent_dir / "uniform/time"
    uniform_identical = replay_time.is_file() and parent_time.is_file() and sha(replay_time) == sha(parent_time)

    old_analysis = json.loads((PARENT / "analysis/firststep-energy-audit-results.json").read_text())
    results: dict[str, Any] = {
        "schema": "i4f-firststep-temperature-matrix-replay-analysis/v1",
        "bundle": str(BUNDLE.relative_to(ROOT)),
        "run": {"container_id": replay_status["container_id"],
                "container_name": replay_status["container_name"],
                "started_at_utc": replay_status["docker_started_at"],
                "finished_at_utc": replay_status["docker_final_state"]["FinishedAt"],
                "terminal_capture_utc": replay_status["terminal_utc"],
                "normal_End": replay_status["normal_End"],
                "docker_exit_code": replay_status["docker_exit_code"],
                "mpi_ranks": launch["ranks"],
                "docker_cpu_quota_equivalents": launch["quota_cpu_equivalents"],
                "docker_log_driver": "none (exact config checked before GO)",
                "hard_wall_seconds_from_StartedAt": launch["hard_wall_s_from_StartedAt"],
                "launch_manifest_sha256": sha(launch_path),
                "GO_marker_sha256": sha(go_path),
                "guardian_status_sha256": sha(replay_status_path),
                "time_records_s": replay_status["time_records"],
                "raw_pressure_record_count": replay_status["raw_pressure_record_count"],
                "raw_pressure_contact_count": replay_status["raw_pressure_contact_count"],
                "raw_pressure_contacts": replay_status["raw_pressure_contacts"],
                "log_path": replay_status["expected_log"],
                "log_sha256": sha(Path(replay_status["expected_log"])),
                "pre_GO_resource_sample": launch["resource_sample_final"]},
        "input_match": {"replay_case_static_tree_sha256": json.loads((BUNDLE / "cases/predictor-yes-matrix/case-freeze.json").read_text())["static_tree_sha256"],
                        "parent_case_static_tree_sha256": json.loads((PARENT / "cases/predictor-yes/case-freeze.json").read_text())["static_tree_sha256"],
                        "same_frozen_inputs": same_frozen_inputs},
        "observer_passivity_vs_prior_predictor_yes": {
            "parent_container_id": parent_status["container_id"],
            "fields": passivity,
            "all_fields_byte_identical": all(row.get("byte_identical") for row in passivity),
            "uniform_time_byte_identical": uniform_identical,
            "interpretation": "The extra FV matrix/residual observer is passive for this matched one-step input if all hashes are identical; this is a one-case result."},
        "operator_source": {
            "OpenFOAM": "v2512",
            "source_excerpt_path": "provenance/openfoam-matrix-api-source.txt",
            "source_excerpt_sha256": sha(BUNDLE / "provenance/openfoam-matrix-api-source.txt"),
            "residual_convention": "fvMatrix::residual is source minus A*psi; confirmed in pinned image source implementation.",
            "matrix_dimensions": {
                "D": "kg/s per local cell (finite-volume integrated coefficient; fvMatrix::D including average boundary diagonal)",
                "source": "kg*K/s per local cell (volume-integrated source)",
                "residual": "kg*K/s per local cell, including off-diagonal and coupled-interface terms"},
            "diffusion_operator": "The diagnostic matrix is the exact same-scheme -fvm::laplacian(turbulence.alphaEff(), T) term, assembled separately after full TEqn assembly and before solve. It remains referenced to the solved T field.",
            "explicit_fvSolution_relaxationFactors_dictionary_present": "relaxationFactors" in fv_solution_without_comments,
            "fvSolution_sha256": sha(BUNDLE / "cases/predictor-yes-matrix/case/system/fvSolution"),
            "equation_snapshot": "Original TEqn D/source/residual captured before relaxation, after relaxation, after fvOptions constrain/before solve, immediately after solve, after fvOptions.correct, and after thermo correction. All FV residual calls occur on every MPI rank in identical order; only selected local rows are written."},
        "selected_cells": {},
        "equation_diagnostics": {},
        "source_provenance": {
            "matrix_binary_sha256": sha(BUNDLE / "bin/compressibleInterFoamI4FFullTemperatureMatrixAudit"),
            "source_manifest_sha256": sha(BUNDLE / "provenance/source-manifest.json"),
            "source_delta_sha256": sha(BUNDLE / "provenance/instrumented-source-delta.json"),
            "matrix_TEqn_source_sha256": sha(BUNDLE / "build/source/v8-energy-matrix-audit/applications/solvers/multiphase/compressibleInterFoam/TEqn.H"),
            "experiment_file_sha256_at_GO": json.loads((BUNDLE / "arms" / ARM / "launch-manifest.json").read_text())["experiment_sha256"],
            "metadata_units_correction": "The frozen experiment.json used a per-volume label for matrix residual units. OpenFOAM FV matrices here are cell-volume integrated: D in kg/s, source and residual in kg*K/s. This post-run analysis corrects the interpretation without altering the frozen experiment or any solver input.",
            "governing_equations_changed": False,
            "parent_closure_manifest_path": "results/summaries/i4f_20261025/full-source-apparatus/source-closure-20261026T2010Z/closure-manifest.json"},
    }

    for rank, local_cell in RANKS.items():
        matrix_path = BUNDLE / "cases" / ARM / "case" / f"i4f_firststep_temperature_matrix_rank{rank}.csv"
        matrix_rows = rows(matrix_path)
        if len(matrix_rows) != 48:
            raise RuntimeError(f"rank {rank}: expected 6 matrix stages x 8 outer loops, got {len(matrix_rows)} rows")
        current_outer = {row["stage"]: row for row in matrix_rows if row["outer"] == "1"}
        if set(current_outer) != set(STAGES):
            raise RuntimeError(f"rank {rank}: incomplete first-outer stages: {sorted(current_outer)}")
        before = current_outer["before_solve_after_options_constrain"]
        solved = current_outer["after_solve_before_options_correct"]
        relaxed = current_outer["after_relax_before_options_constrain"]
        assembled = current_outer["assembled_before_relax"]
        constrained = current_outer["before_solve_after_options_constrain"]
        after_options = current_outer["after_options_correct_before_thermo"]
        after_thermo = current_outer["after_thermo_correct"]
        full_d = number(solved, "full_D_including_boundary_average")
        diffusion_d = number(solved, "diffusion_D_including_boundary_average")
        non_diff_diag = full_d - diffusion_d
        diffusion_residual = number(solved, "diffusion_residual_source_minus_Apsi")
        full_residual = number(solved, "full_residual_source_minus_Apsi")
        non_diff_residual = number(solved, "non_diffusive_residual_source_minus_Apsi")
        diffusion_equiv = diffusion_residual / non_diff_diag if non_diff_diag else None
        old_cell = old_analysis["cases"]["predictor-yes"]["local_energy_terms"]["ranks"][str(rank)]
        prior_remainder = old_cell["TEqn_temperature_change"]["actual_minus_source_only_K"]
        old_actual_dT = old_cell["TEqn_temperature_change"]["actual_deltaT_K"]
        source_only = old_cell["TEqn_temperature_change"]["preTEqn_explicit_source_only_predicted_deltaT_K"]
        relax_delta = {
            "D_after_relax_minus_assembled": number(relaxed, "full_D_including_boundary_average") - number(assembled, "full_D_including_boundary_average"),
            "source_after_relax_minus_assembled": number(relaxed, "full_source") - number(assembled, "full_source"),
            "D_after_options_constrain_minus_after_relax": number(constrained, "full_D_including_boundary_average") - number(relaxed, "full_D_including_boundary_average"),
            "source_after_options_constrain_minus_after_relax": number(constrained, "full_source") - number(relaxed, "full_source"),
            "T_after_options_correct_minus_after_solve_K": number(after_options, "T_K") - number(solved, "T_K"),
            "T_after_thermo_correct_minus_after_options_K": number(after_thermo, "T_K") - number(after_options, "T_K"),
        }
        results["selected_cells"][str(rank)] = {
            "local_cell": local_cell,
            "native_C_m": [number(solved, key) for key in ("x_m", "y_m", "z_m")],
            "matrix_csv_path": str(matrix_path.relative_to(BUNDLE)),
            "matrix_csv_sha256": sha(matrix_path),
            "matrix_rows": len(matrix_rows),
            "temperature_before_TEqn_K": number(before, "T_K"),
            "temperature_after_TEqn_K": number(solved, "T_K"),
            "actual_T_change_K": old_actual_dT,
            "prior_explicit_source_only_deltaT_K": source_only,
            "prior_positive_remainder_K": prior_remainder,
            "first_outer_matrix": {
                "full_D_kg_s": full_d,
                "diffusion_D_kg_s": diffusion_d,
                "non_diffusion_D_kg_s": non_diff_diag,
                "full_residual_source_minus_Apsi_kgK_s": full_residual,
                "diffusion_residual_source_minus_Apsi_kgK_s": diffusion_residual,
                "non_diffusion_residual_source_minus_Apsi_kgK_s": non_diff_residual,
                "residual_sum_check_kgK_s": full_residual - (diffusion_residual + non_diff_residual),
                "diffusion_temperature_equivalent_using_non_diffusion_diagonal_K": diffusion_equiv,
                "diffusion_equivalent_minus_prior_remainder_K": diffusion_equiv - prior_remainder if diffusion_equiv is not None else None,
                "matrix_D_source_and_residual_before_after_relax_options": relax_delta,
                "stage_values": {stage: {key: number(current_outer[stage], key) for key in (
                    "T_K", "full_D_including_boundary_average", "full_source", "full_residual_source_minus_Apsi",
                    "diffusion_D_including_boundary_average", "diffusion_source", "diffusion_residual_source_minus_Apsi",
                    "non_diffusive_residual_source_minus_Apsi")} for stage in STAGES},
            },
        }

    raw_log = Path(replay_status["expected_log"])
    log_sha = sha(raw_log)
    summary_path = BUNDLE / "analysis/temperature-matrix-replay-results.json"
    summary_path.parent.mkdir(exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n")
    csv_path = BUNDLE / "analysis/temperature-matrix-local-budget.csv"
    columns = (
        "rank", "local_cell", "x_m", "y_m", "z_m", "T_before_TEqn_K", "T_after_TEqn_K",
        "actual_deltaT_K", "prior_source_only_deltaT_K", "prior_remainder_K", "full_D_kg_s",
        "diffusion_D_kg_s", "non_diffusion_D_kg_s", "full_residual_kgK_s",
        "diffusion_residual_kgK_s", "non_diffusion_residual_kgK_s", "diffusion_equivalent_K",
        "equivalent_minus_prior_remainder_K", "full_residual_sum_check_kgK_s",
    )
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for rank, cell in results["selected_cells"].items():
            m = cell["first_outer_matrix"]
            writer.writerow({
                "rank": rank, "local_cell": cell["local_cell"],
                "x_m": cell["native_C_m"][0], "y_m": cell["native_C_m"][1], "z_m": cell["native_C_m"][2],
                "T_before_TEqn_K": cell["temperature_before_TEqn_K"], "T_after_TEqn_K": cell["temperature_after_TEqn_K"],
                "actual_deltaT_K": cell["actual_T_change_K"], "prior_source_only_deltaT_K": cell["prior_explicit_source_only_deltaT_K"],
                "prior_remainder_K": cell["prior_positive_remainder_K"],
                "full_D_kg_s": m["full_D_kg_s"], "diffusion_D_kg_s": m["diffusion_D_kg_s"],
                "non_diffusion_D_kg_s": m["non_diffusion_D_kg_s"],
                "full_residual_kgK_s": m["full_residual_source_minus_Apsi_kgK_s"],
                "diffusion_residual_kgK_s": m["diffusion_residual_source_minus_Apsi_kgK_s"],
                "non_diffusion_residual_kgK_s": m["non_diffusion_residual_source_minus_Apsi_kgK_s"],
                "diffusion_equivalent_K": m["diffusion_temperature_equivalent_using_non_diffusion_diagonal_K"],
                "equivalent_minus_prior_remainder_K": m["diffusion_equivalent_minus_prior_remainder_K"],
                "full_residual_sum_check_kgK_s": m["residual_sum_check_kgK_s"],
            })
    print(json.dumps({"summary":str(summary_path.relative_to(BUNDLE)),"summary_sha256":sha(summary_path),
                      "cell_csv":str(csv_path.relative_to(BUNDLE)),"cell_csv_sha256":sha(csv_path),
                      "all_native_fields_identical":results["observer_passivity_vs_prior_predictor_yes"]["all_fields_byte_identical"],
                      "uniform_time_identical":uniform_identical,
                      "diagnostic_log_sha256":log_sha,
                      "diffusion_equivalent_K":{r:c["first_outer_matrix"]["diffusion_temperature_equivalent_using_non_diffusion_diagonal_K"] for r,c in results["selected_cells"].items()}},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
