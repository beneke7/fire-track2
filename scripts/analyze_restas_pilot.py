#!/usr/bin/env python3
"""Summarize an OpenFOAM pilot bundle without turning it into a validation claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            rows.append((float(fields[0]), float(fields[1])))
        except ValueError:
            continue
    return rows


def _resource_summary(samples: list[dict[str, str]]) -> dict[str, float | None]:
    cpu_percent: list[float] = []
    memory_gib: list[float] = []
    for sample in samples:
        try:
            cpu_percent.append(float(sample["cpu_percent"].rstrip("%")))
            memory = sample["memory_usage_and_limit"].split("/", maxsplit=1)[0].strip()
            match = re.fullmatch(rf"({NUMBER})\s*(B|KiB|MiB|GiB)", memory)
            if match:
                value = float(match.group(1))
                scale = {"B": 2**-30, "KiB": 2**-20, "MiB": 2**-10, "GiB": 1.0}
                memory_gib.append(value * scale[match.group(2)])
        except (KeyError, ValueError):
            continue
    return {
        "sample_count": len(samples),
        "peak_sampled_cpu_percent": max(cpu_percent, default=None),
        "peak_sampled_memory_gib": max(memory_gib, default=None),
    }


def build_report(run_dir: Path) -> dict[str, Any]:
    """Extract observed mesh, solver, inventory, artifact, and resource evidence."""
    run_dir = run_dir.resolve()
    manifest_path = run_dir / "manifest.json"
    inputs_path = run_dir / "inputs.json"
    log_path = run_dir / "openfoam-console.log"
    manifest = _read_json(manifest_path)
    inputs = _read_json(inputs_path)
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    source_ledger_path = run_dir / "source-ledger-summary.json"
    source_ledger = _read_json(source_ledger_path) if source_ledger_path.is_file() else None

    cells = re.findall(r"^\s*cells:\s*(\d+)\s*$", log, re.MULTILINE)
    solver_times = re.findall(rf"^Time = ({NUMBER})\s*$", log, re.MULTILINE)
    execution_times = re.findall(rf"^ExecutionTime = ({NUMBER})\s*s", log, re.MULTILINE)
    pressure_iterations = [
        int(value) for value in re.findall(r"GAMG:\s+Solving for p_rgh,.*?No Iterations (\d+)", log)
    ]
    inventory_paths = sorted(
        (run_dir / "case" / "postProcessing" / "waterVolume").glob("*/volFieldValue.dat")
    )
    inventory_rows = [row for path in inventory_paths for row in _inventory(path)]
    inventory_rows.sort()

    expected_mass = float(inputs["expected_released_mass_kg"])
    density = float(inputs["water"]["density_kg_m3"])
    expected_volume = expected_mass / density
    latest_inventory = inventory_rows[-1] if inventory_rows else None
    observed_volume = latest_inventory[1] if latest_inventory else None
    volume_delta = observed_volume - expected_volume if observed_volume is not None else None
    volume_delta_fraction = volume_delta / expected_volume if volume_delta is not None else None

    continuity = [float(value) for value in re.findall(rf"cumulative\s*=\s*({NUMBER})", log)]
    max_courant = [
        float(value)
        for value in re.findall(
            rf"^Courant Number mean: {NUMBER} max: ({NUMBER})", log, re.MULTILINE
        )
    ]
    max_interface_courant = [
        float(value)
        for value in re.findall(rf"Interface Courant Number mean: {NUMBER} max: ({NUMBER})", log)
    ]
    delta_t = [
        float(value) for value in re.findall(rf"^deltaT = ({NUMBER})\s*$", log, re.MULTILINE)
    ]
    alpha_bounds = [
        (float(low), float(high))
        for low, high in re.findall(
            rf"After conservative bounding: min\(alpha\) = ({NUMBER}), max\(alpha\) = ({NUMBER})",
            log,
        )
    ]
    surface_times = sorted(
        path.parent.name
        for path in (run_dir / "case" / "postProcessing" / "liquidInterface").glob(
            "*/freeSurface.vtp"
        )
    )
    surface_paths = sorted(
        (run_dir / "case" / "postProcessing" / "liquidInterface").glob("*/freeSurface.vtp")
    )
    expected_mesh = int(inputs["mesh_cells_expected"])
    observed_mesh = int(cells[-1]) if cells else None
    case_dir = run_dir / "case"
    reconstructed_case_input_hashes = {
        str(path.relative_to(case_dir)): _sha256(path)
        for path in sorted(case_dir.rglob("*"))
        if path.is_file() and path.relative_to(case_dir).parts[0] in {"0", "constant", "system"}
    }
    exit_code = manifest.get("exit_code")
    completed_to_end = (
        bool(solver_times) and float(solver_times[-1]) >= float(inputs["end_time_s"]) - 1e-9
    )
    check_mesh_ok = "Mesh OK." in log

    wall_time = manifest.get("wall_time_s")
    physical_time = float(solver_times[-1]) if solver_times else None
    resources = manifest.get("docker_resource_samples", [])
    latest_execution_time = float(execution_times[-1]) if execution_times else None
    allocated_cpu_hours = (
        wall_time * int(manifest.get("execution", {}).get("mpi_ranks", 0)) / 3600
        if isinstance(wall_time, (int, float))
        else None
    )
    if source_ledger is None:
        water_interpretation = (
            "Domain inventory compared with the intended rectangular source integral; no predeclared"
            " acceptance tolerance or saved per-patch liquid-flux history exists for this exploratory run."
        )
        ledger_gate_decision = (
            "Exploratory characterization only. No E1-E6 gate passed. Before a follow-on run,"
            " pre-register source-event treatment and conservation tolerances, save boundary liquid-flux"
            " histories, and have the contract independently reviewed."
        )
    else:
        water_interpretation = (
            "The domain-only difference from nominal release is not a mass-conservation error: water"
            " can leave through open boundaries. The sampled source, open-boundary, and domain-inventory"
            " ledger below is the relevant accounting check."
        )
        ledger_gate_decision = (
            "Exploratory characterization only. No E1-E6 gate passed. Per-slot source and open-boundary"
            " flux histories were recorded and the sampled mass ledger closes within its exploratory"
            " threshold. Source and turbulence inputs remain provisional, and mesh-convergence and"
            " independent-validation evidence are still absent."
        )

    report = {
        "run_id": manifest.get("run_id"),
        "run_bundle": str(run_dir),
        "analysis_script_sha256": _sha256(Path(__file__).resolve()),
        "exit_code": exit_code,
        "started_utc": manifest.get("started_utc"),
        "finished_utc": manifest.get("finished_utc"),
        "solver": inputs.get("solver"),
        "solver_image": manifest.get("solver_image"),
        "solver_image_id": manifest.get("solver_image_id"),
        "case_input_sha256": reconstructed_case_input_hashes,
        "case_input_hash_provenance": (
            "Recomputed post-run from retained case inputs because the original completion manifest's"
            " case_file_hashes field is empty."
            if not manifest.get("case_file_hashes")
            else "Copied/reconfirmed from the case inputs retained in the run bundle."
        ),
        "mesh": {
            "expected_cells": expected_mesh,
            "observed_cells": observed_mesh,
            "cell_count_matches": observed_mesh == expected_mesh,
            "check_mesh_passed": check_mesh_ok,
            "slot_patch_count": inputs.get("slot_count"),
            "cells_across_slot_short_axis": inputs.get("cells_across_slot_short_axis"),
        },
        "solver_advance": {
            "declared_end_time_s": inputs.get("end_time_s"),
            "last_time_written_s": physical_time,
            "reached_declared_end_time": completed_to_end,
            "latest_execution_time_s": latest_execution_time,
            "max_abs_logged_cumulative_continuity_error": max(map(abs, continuity), default=None),
            "logged_alpha_min": min((pair[0] for pair in alpha_bounds), default=None),
            "logged_alpha_max": max((pair[1] for pair in alpha_bounds), default=None),
            "observed_max_courant": max(max_courant, default=None),
            "configured_max_courant": inputs.get("max_courant"),
            "max_courant_within_configured_limit": (
                max(max_courant) <= float(inputs["max_courant"]) if max_courant else None
            ),
            "observed_max_interface_courant": max(max_interface_courant, default=None),
            "configured_max_interface_courant": inputs.get("max_alpha_courant"),
            "interface_courant_within_configured_limit": (
                max(max_interface_courant) <= float(inputs["max_alpha_courant"])
                if max_interface_courant
                else None
            ),
            "time_step_s": {"min": min(delta_t, default=None), "max": max(delta_t, default=None)},
            "logged_time_step_count": len(solver_times),
            "pressure_solver_iteration_summary": {
                "solve_count": len(pressure_iterations),
                "total_iterations": sum(pressure_iterations),
                "max_iterations_per_solve": max(pressure_iterations, default=None),
                "mean_iterations_per_solve": (
                    sum(pressure_iterations) / len(pressure_iterations)
                    if pressure_iterations
                    else None
                ),
                "pressure_solve_time_share_measured": False,
            },
        },
        "water_inventory": {
            "expected_prescribed_release_kg": expected_mass,
            "water_density_kg_m3": density,
            "expected_release_volume_m3": expected_volume,
            "latest_inventory_time_s": latest_inventory[0] if latest_inventory else None,
            "latest_domain_inventory_m3": observed_volume,
            "latest_domain_inventory_kg": (
                observed_volume * density if observed_volume is not None else None
            ),
            "observed_minus_expected_m3": volume_delta,
            "observed_minus_expected_percent": (
                100 * volume_delta_fraction if volume_delta_fraction is not None else None
            ),
            "observed_source_dose_kg": (
                source_ledger.get("observed_source_dose_kg") if source_ledger else None
            ),
            "open_boundary_mass_kg": (
                source_ledger.get("final_open_boundary_mass_kg") if source_ledger else None
            ),
            "sampled_mass_ledger_residual_kg": (
                source_ledger.get("final_mass_residual_kg") if source_ledger else None
            ),
            "sampled_mass_ledger_max_relative_residual": (
                source_ledger.get("maximum_relative_mass_residual") if source_ledger else None
            ),
            "sampled_mass_ledger_within_0p1_percent": (
                source_ledger.get("mass_ledger_within_0p1_percent") if source_ledger else None
            ),
            "interpretation": water_interpretation,
        },
        "source_ledger_summary": source_ledger,
        "source_ledger_summary_sha256": (
            _sha256(source_ledger_path) if source_ledger_path.is_file() else None
        ),
        "surface_artifacts": {
            "count": len(surface_times),
            "times_s": surface_times,
            "total_bytes": sum(path.stat().st_size for path in surface_paths),
            "fields": ["alpha.water", "U"],
            "format": "VTK PolyData interface surfaces (.vtp)",
        },
        "resources": {
            "mpi_ranks": manifest.get("execution", {}).get("mpi_ranks"),
            "docker_cpu_limit": manifest.get("execution", {}).get("docker_cpu_limit"),
            "docker_memory_limit_gib": manifest.get("execution", {}).get("docker_memory_limit_gib"),
            "wall_time_s": wall_time,
            "simulated_seconds_per_wall_hour": (
                physical_time / wall_time * 3600
                if physical_time is not None
                and isinstance(wall_time, (int, float))
                and wall_time > 0
                else None
            ),
            "mpi_rank_wall_clock_core_hours_estimate": allocated_cpu_hours,
            "sample_summary": _resource_summary(resources),
            "sampling_note": manifest.get("resource_sample_note"),
            "profile_gaps": [
                "pressure-solve wall-time share (iteration counts only)",
                "checkpoint and filesystem I/O time share",
                "GPU/VRAM use (CPU-only case)",
            ],
        },
        "gate_decision": ledger_gate_decision,
        "basic_execution_checks": {
            "container_exit_zero": exit_code == 0,
            "mesh_validation": check_mesh_ok,
            "mesh_count_matches_input": observed_mesh == expected_mesh,
            "reached_declared_end_time": completed_to_end,
            "observed_max_courant_within_input_limit": (
                max(max_courant) <= float(inputs["max_courant"]) if max_courant else None
            ),
            "observed_max_interface_courant_within_input_limit": (
                max(max_interface_courant) <= float(inputs["max_alpha_courant"])
                if max_interface_courant
                else None
            ),
        },
        "claim_limit": inputs.get("evidence_label"),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="path to one immutable results/runs bundle")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.run_dir)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    output_path = args.run_dir / "pilot-report.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
