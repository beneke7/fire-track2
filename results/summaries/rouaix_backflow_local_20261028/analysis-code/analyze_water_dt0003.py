#!/usr/bin/env python3
"""Extract compact, reproducible metrics from the fixed-dt Rouaix water run."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUN_ID = "air-backflow-water-dt0003-030"
RUN = ROOT / "container-runs" / RUN_ID
SUMMARY = ROOT.parents[1] / "summaries" / "rouaix_backflow_local_20261028"
RHO_WATER = 997.6


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_log() -> dict[str, list[Any]]:
    records: dict[str, list[Any]] = {
        key: []
        for key in (
            "bulk_co",
            "interface_co",
            "water_volume",
            "alpha_min",
            "alpha_max",
            "speed_max",
            "p_rgh_min",
            "p_rgh_max",
            "continuity",
            "execution_clock",
            "alpha_flux",
        )
    }
    current_time = 0.0
    patterns = (
        ("bulk_co", re.compile(r"Courant Number mean: ([^ ]+) max: ([^ ]+)")),
        (
            "interface_co",
            re.compile(r"Interface Courant Number mean: ([^ ]+) max: ([^ ]+)"),
        ),
        (
            "water_volume",
            re.compile(r"volIntegrate\(region0\) of alpha.water = ([^ ]+)"),
        ),
        ("alpha_min", re.compile(r"min\(alpha.water\) = ([^ ]+)")),
        ("alpha_max", re.compile(r"max\(alpha.water\) = ([^ ]+)")),
        ("speed_max", re.compile(r"max\(mag\(U\)\) = ([^ ]+)")),
        ("p_rgh_min", re.compile(r"min\(p_rgh\) = ([^ ]+)")),
        ("p_rgh_max", re.compile(r"max\(p_rgh\) = ([^ ]+)")),
        (
            "continuity",
            re.compile(
                r"time step continuity errors : sum local = ([^,]+), "
                r"global = ([^,]+), cumulative = ([^ ]+)"
            ),
        ),
        (
            "execution_clock",
            re.compile(r"ExecutionTime = ([^ ]+) s  ClockTime = ([^ ]+) s"),
        ),
        ("alpha_flux", re.compile(r"sum\(([^)]+)\) of alphaPhi_ = ([^ ]+)")),
    )
    time_pattern = re.compile(r"Time = ([0-9.eE+-]+)")
    log_path = RUN / "evidence" / "interIsoFoam.log"
    for raw_line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        time_match = time_pattern.match(line)
        if time_match:
            current_time = float(time_match.group(1))
            continue
        for key, pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            values = match.groups()
            if key in ("bulk_co", "interface_co"):
                records[key].append((current_time, float(values[1])))
            elif key == "continuity":
                records[key].append((current_time, tuple(map(float, values))))
            elif key == "execution_clock":
                records[key].append(tuple(map(float, values)))
            elif key == "alpha_flux":
                records[key].append((current_time, values[0], float(values[1])))
            else:
                records[key].append((current_time, float(values[0])))
            break
    return records


def extrema(records: list[tuple[float, float]]) -> dict[str, float]:
    time_s, value = max(records, key=lambda item: item[1])
    return {"max": value, "time_s": time_s}


def verify_pre_go() -> dict[str, bool]:
    pre_go_path = RUN / "pre-go-manifest.json"
    pre_go = load(pre_go_path)
    go = load(RUN / "go-released.json")
    upload = ROOT / "uploads" / RUN_ID
    source_snapshot = ROOT / f"source-snapshot-before-{RUN_ID}"
    source_files_match = all(
        sha256(source_snapshot / relative_path) == expected_hash
        for relative_path, expected_hash in pre_go["source_files_sha256"].items()
    )
    ready_lines = (RUN / "remote-control.log").read_text(encoding="utf-8").splitlines()
    ready = json.loads(ready_lines[1])
    archive_verification = load(RUN / "archive-verification.json")
    run_result = load(RUN / "run-result.json")
    source_manifest = source_snapshot / "manifest.json"
    return {
        "go_references_pre_go_hash": go["pre_go_manifest_sha256"] == sha256(pre_go_path),
        "container_id_matches": pre_go["container_id"] == run_result["container_id"],
        "input_case_hash_matches": pre_go["input_case_sha256"]
        == sha256(upload / "case" / "case-inputs.json"),
        "input_manifest_hash_matches": pre_go["input_file_manifest_sha256"]
        == sha256(upload / "case-files.sha256"),
        "source_files_match_snapshot": source_files_match,
        "source_snapshot_manifest_matches": sha256(source_manifest)
        == pre_go["source_snapshot_sha256"],
        "guard_ready_and_hashes_verified": ready["ready"] and ready["hashes_verified"],
        "archive_remote_local_hash_matches": archive_verification["remote_local_sha_match"],
        "terminal_snapshot_inventory_passed": run_result["snapshot_inventory"]["passed"],
    }


def main() -> None:
    case = load(ROOT / RUN_ID / "case-inputs.json")
    run_result = load(RUN / "run-result.json")
    archive = load(RUN / "archive-verification.json")
    records = parse_log()
    steps = int(case["expected_steps"])
    dt = float(case["delta_t_s"])
    if len(records["water_volume"]) != steps:
        raise SystemExit(f"expected {steps} water-volume records")
    if len(records["alpha_flux"]) != steps * 7:
        raise SystemExit("phase-flux record count does not cover seven patches per step")

    integrated_flux: defaultdict[str, float] = defaultdict(float)
    for _time_s, patch, flux_m3_s in records["alpha_flux"]:
        integrated_flux[patch] += flux_m3_s * dt
    injected_volume = -integrated_flux["nozzle"]
    other_outward_volume = sum(
        value for patch, value in integrated_flux.items() if patch != "nozzle"
    )
    terminal_volume = records["water_volume"][-1][1]
    volume_residual = terminal_volume - injected_volume + other_outward_volume
    reference = load(SUMMARY / "water-total-pressure-diagnostics.json")
    reference_clock_s = float(
        re.search(
            r"ClockTime = ([0-9.]+) s",
            reference["solver"]["final_execution_clock_line"],
        ).group(1)
    )
    clock_s = records["execution_clock"][-1][1]
    reference_steps = int(reference["solver"]["steps"])
    reference_dt = float(reference["solver"]["delta_t_s"])
    result = {
        "schema_version": 1,
        "case": RUN_ID,
        "interpretation": (
            "Exploratory fixed-step cost and stability diagnostic. It completed the "
            "same coarse 0.3000 s water-nozzle horizon with three times the fixed "
            "timestep; this is not a time-resolution study or an E1 result."
        ),
        "solver": {
            "name": "OpenCFD v2512 interIsoFoam",
            "mesh_cells": 299520,
            "mpi_ranks": case["mpi_ranks"],
            "delta_t_s": dt,
            "steps_completed": steps,
            "target_time_s": float(case["end_time_s"]),
            "final_execution_clock_line": (
                f"ExecutionTime = {records['execution_clock'][-1][0]:g} s  "
                f"ClockTime = {clock_s:g} s"
            ),
            "clock_time_per_step_s": clock_s / steps,
        },
        "result": {
            "started_utc": run_result["container_started_at"],
            "completed_utc": run_result["completed_utc"],
            "solver_wall_elapsed_s": run_result["guard"]["hard_deadline_elapsed_s"],
            "solver_time_s": float(run_result["terminal"]["solver_time_s"]),
            "solver_exit_code": run_result["terminal"]["solver_exit_code"],
            "end_marker": run_result["terminal"]["end_marker"],
            "guard_limit_m_s": run_result["guard"]["threshold_m_s"],
            "guard_reason": run_result["guard"]["reason"],
        },
        "speed_extrema": {
            "global_peak_m_s": extrema(records["speed_max"])["max"],
            "global_peak_time_s": extrema(records["speed_max"])["time_s"],
            "terminal_m_s": run_result["terminal"]["max_U_m_s"],
            "record_count": len(records["speed_max"]),
        },
        "alpha_water_extrema": {
            "min": min(value for _time, value in records["alpha_min"]),
            "max": max(value for _time, value in records["alpha_max"]),
            "record_count": len(records["alpha_min"]),
        },
        "courant_numbers": {
            "bulk_max": {"kind": "bulk", **extrema(records["bulk_co"])},
            "bulk_record_count": len(records["bulk_co"]),
            "interface_max": {
                "kind": "interface",
                **extrema(records["interface_co"]),
            },
            "interface_record_count": len(records["interface_co"]),
        },
        "water_volume_m3": {
            "initial_internal_field": 0.0,
            "terminal": terminal_volume,
            "record_count": len(records["water_volume"]),
        },
        "phase_volume_flux_balance": {
            "quadrature": (
                "sum of signed alphaPhi_ patch records at each fixed timestep times "
                "0.0003 s; exploratory diagnostic"
            ),
            "water_density_kg_m3": RHO_WATER,
            "initial_water_volume_m3": 0.0,
            "nozzle_injected_volume_m3": injected_volume,
            "non_nozzle_net_outward_alphaPhi_volume_m3": other_outward_volume,
            "terminal_water_volume_m3": terminal_volume,
            "signed_volume_closure_residual_m3": volume_residual,
            "closure_relative_to_injected_volume": volume_residual / injected_volume,
            "terminal_water_mass_kg": terminal_volume * RHO_WATER,
            "signed_mass_closure_residual_kg": volume_residual * RHO_WATER,
            "patches_integrated_alphaPhi_m3": dict(sorted(integrated_flux.items())),
        },
        "p_rgh_extrema_pa": {
            "dimensions": "[1 -1 -2 0 0 0 0]",
            "run_min": {
                "time_s": min(records["p_rgh_min"], key=lambda item: item[1])[0],
                "value_pa": min(records["p_rgh_min"], key=lambda item: item[1])[1],
            },
            "run_max": extrema(records["p_rgh_max"]),
            "terminal_min_pa": records["p_rgh_min"][-1][1],
            "terminal_max_pa": records["p_rgh_max"][-1][1],
        },
        "terminal_mixture_continuity_record": records["continuity"][-1][1],
        "matched_reference_comparison": {
            "reference_case": "air-backflow-water-030",
            "same_mesh_fields_boundaries_schemes_ranks_and_horizon": True,
            "reference_delta_t_s": reference_dt,
            "reference_steps": reference_steps,
            "reference_clock_time_s": reference_clock_s,
            "clock_time_speedup_for_same_horizon": reference_clock_s / clock_s,
            "reference_clock_time_per_step_s": reference_clock_s / reference_steps,
            "candidate_clock_time_per_step_fraction_of_reference": (
                (clock_s / steps) / (reference_clock_s / reference_steps)
            ),
            "reference_bulk_courant_max": reference["courant_numbers"]["bulk_max"]["max"],
            "candidate_bulk_courant_max": extrema(records["bulk_co"])["max"],
            "candidate_to_reference_bulk_courant_ratio": (
                extrema(records["bulk_co"])["max"] / reference["courant_numbers"]["bulk_max"]["max"]
            ),
            "reference_interface_courant_max": reference["courant_numbers"]["interface_max"]["max"],
            "candidate_interface_courant_max": extrema(records["interface_co"])["max"],
            "candidate_to_reference_interface_courant_ratio": (
                extrema(records["interface_co"])["max"]
                / reference["courant_numbers"]["interface_max"]["max"]
            ),
            "reference_peak_speed_m_s": reference["speed_extrema"]["global_peak_m_s"],
            "peak_speed_difference_m_s": (
                extrema(records["speed_max"])["max"] - reference["speed_extrema"]["global_peak_m_s"]
            ),
        },
        "pre_go_integrity_checks": verify_pre_go(),
        "provenance": {
            "git_revision": load(RUN / "pre-go-manifest.json")["git_revision"],
            "git_dirty": load(RUN / "pre-go-manifest.json")["git_dirty"],
            "container_id": run_result["container_id"],
            "pre_go_manifest_sha256": sha256(RUN / "pre-go-manifest.json"),
            "input_case_sha256": load(RUN / "pre-go-manifest.json")["input_case_sha256"],
            "input_file_manifest_sha256": load(RUN / "pre-go-manifest.json")[
                "input_file_manifest_sha256"
            ],
            "source_snapshot_sha256": load(RUN / "pre-go-manifest.json")["source_snapshot_sha256"],
            "archive_bytes": archive["bytes"],
            "archive_members": archive["regular_members"],
            "archive_sha256": archive["sha256"],
            "archive_remote_local_match": archive["remote_local_sha_match"],
            "snapshot_inventory_passed": run_result["snapshot_inventory"]["passed"],
        },
    }
    if not all(result["pre_go_integrity_checks"].values()):
        raise SystemExit("one or more pre-GO integrity checks failed")
    SUMMARY.mkdir(parents=True, exist_ok=True)
    destination = SUMMARY / "water-dt0003-diagnostics.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
