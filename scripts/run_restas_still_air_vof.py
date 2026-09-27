#!/usr/bin/env python3
"""Run an exploratory one-second, still-air, four-slot OpenFOAM VOF case.

The established P0/P1 runner is deliberately left unchanged: its reviewed
short-run contracts remain exact. This runner reuses its container/resource
handling while giving the longer still-air case its own immutable bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import analyze_restas_ledger as ledger
import analyze_restas_pilot as pilot_report
import run_restas_pilot as pilot

ROOT = Path(__file__).resolve().parents[1]
END_TIME_S = 1.0
DELTA_T_S = 1e-4
STEP_COUNT = 10_000
SOURCE_TOLERANCE = 0.001
LEDGER_TOLERANCE = 0.001
WALL_LIMIT_S = 36_000.0
DOMAIN = {"x": (-7.975, 7.975), "y": (-3.025, 3.025), "z": (0.0, 10.0)}
NX = (50, 6, 1, 6, 50)
NY = (20, 40, 1, 40, 20)
NZ = 120
Z_END_TO_START_GRADING = 0.25
EXPECTED_CELLS = sum(NX) * sum(NY) * NZ
_Z_CELL_GROWTH = math.exp(math.log(Z_END_TO_START_GRADING) / (NZ - 1))
_Z_BOTTOM_CELL_M = DOMAIN["z"][1] * (1 - _Z_CELL_GROWTH) / (1 - _Z_CELL_GROWTH**NZ)
_Z_TOP_CELL_M = _Z_BOTTOM_CELL_M * Z_END_TO_START_GRADING
SLOT_K = 1.5 * (0.01 * 4.8) ** 2
TURBULENCE_LENGTH_M = 0.07 * 0.15
SLOT_EPSILON = 0.09**0.75 * SLOT_K**1.5 / TURBULENCE_LENGTH_M
AMBIENT_K = 1e-8
AMBIENT_EPSILON = 1e-8
SOURCE_NAMES = ("slot_01", "slot_02", "slot_03", "slot_04")
OPEN_NAMES = ("airInlet", "airOutlet", "lowerOutlet")


def _replace_patch(path: Path, patch: str, replacements: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?ms)^    {re.escape(patch)}\s*\{{.*?^    \}}")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected one {patch} patch in {path}, found {len(matches)}")
    block = matches[0].group(0)
    for old, new in replacements.items():
        if old not in block:
            raise ValueError(f"expected {old!r} in {patch} block of {path}")
        block = block.replace(old, new, 1)
    path.write_text(text[: matches[0].start()] + block + text[matches[0].end() :], encoding="utf-8")


def _scalar_field(
    name: str,
    dimensions: str,
    internal: float,
    slot_value: float | None,
    wall_condition: str,
    open_value: float,
) -> str:
    slot = (
        f"        type fixedValue;\n        value uniform {slot_value:.12g};"
        if slot_value is not None
        else "        type calculated;\n        value uniform 0;"
    )
    patches = {patch: slot for patch in SOURCE_NAMES}
    patches["airPlate"] = f"        type {wall_condition};\n        value uniform 0;"
    patches["airInlet"] = (
        "        type inletOutlet;\n"
        f"        inletValue uniform {open_value:.12g};\n"
        f"        value uniform {open_value:.12g};"
    )
    patches["airOutlet"] = patches["airInlet"]
    patches["lowerOutlet"] = patches["airInlet"]
    patches["sideMin"] = "        type symmetryPlane;"
    patches["sideMax"] = "        type symmetryPlane;"
    return pilot._boundary_field(
        name,
        "volScalarField",
        dimensions,
        f"{internal:.12g}",
        patches,
    )


def _prepare_case(case_dir: Path, ranks: int) -> dict[str, Any]:
    previous_mesh = (pilot.DOMAIN, pilot.NX, pilot.NY, pilot.NZ)
    try:
        pilot.DOMAIN = DOMAIN
        pilot.NX = NX
        pilot.NY = NY
        pilot.NZ = NZ
        details = pilot._write_case(case_dir, ranks, source_event_ledger=True)
    finally:
        pilot.DOMAIN, pilot.NX, pilot.NY, pilot.NZ = previous_mesh

    mesh_path = case_dir / "system" / "blockMeshDict"
    mesh_text = mesh_path.read_text(encoding="utf-8")
    mesh_text, replacements = re.subn(
        r"simpleGrading\s+\(1\s+1\s+1\)",
        f"simpleGrading (1 1 {Z_END_TO_START_GRADING:g})",
        mesh_text,
    )
    if replacements != (len(NX) * len(NY)):
        raise ValueError(f"expected {len(NX) * len(NY)} graded blocks, found {replacements}")
    mesh_path.write_text(mesh_text, encoding="utf-8")

    control_path = case_dir / "system" / "controlDict"
    control = control_path.read_text(encoding="utf-8")
    control, changed = re.subn(r"(?m)^endTime\s+0\.12;", f"endTime {END_TIME_S:g};", control)
    if changed != 1:
        raise ValueError("could not set the one-second end time")
    control_path.write_text(control, encoding="utf-8")

    u_path = case_dir / "0" / "U"
    u_text = u_path.read_text(encoding="utf-8")
    u_text = u_text.replace("internalField uniform (-50 0 0);", "internalField uniform (0 0 0);")
    u_text = u_text.replace("(0.12 (0 0 0))", "(1 (0 0 0))")
    u_path.write_text(u_text, encoding="utf-8")
    _replace_patch(
        u_path,
        "airInlet",
        {
            "type fixedValue;": "type pressureInletOutletVelocity;",
            "value uniform (-50 0 0);": "value uniform (0 0 0);",
        },
    )
    _replace_patch(
        u_path,
        "airOutlet",
        {"value uniform (-50 0 0);": "value uniform (0 0 0);"},
    )
    _replace_patch(
        u_path,
        "lowerOutlet",
        {"value uniform (0 0 -4.8);": "value uniform (0 0 0);"},
    )

    constant = case_dir / "constant"
    (constant / "turbulenceProperties").write_text(
        pilot._foam_header("turbulenceProperties", location="constant")
        + "density variable;\nsimulationType RAS;\n"
        + "RAS\n{\n    RASModel realizableKE;\n    turbulence on;\n    printCoeffs on;\n}\n",
        encoding="utf-8",
    )
    initial = case_dir / "0"
    (initial / "k").write_text(
        _scalar_field("k", "[0 2 -2 0 0 0 0]", AMBIENT_K, SLOT_K, "kqRWallFunction", AMBIENT_K),
        encoding="utf-8",
    )
    (initial / "epsilon").write_text(
        _scalar_field(
            "epsilon",
            "[0 2 -3 0 0 0 0]",
            AMBIENT_EPSILON,
            SLOT_EPSILON,
            "epsilonWallFunction",
            AMBIENT_EPSILON,
        ),
        encoding="utf-8",
    )
    (initial / "nut").write_text(
        _scalar_field("nut", "[0 2 -1 0 0 0 0]", 0.0, None, "nutkWallFunction", 0.0),
        encoding="utf-8",
    )

    schemes_path = case_dir / "system" / "fvSchemes"
    schemes = schemes_path.read_text(encoding="utf-8")
    schemes = schemes.replace(
        "gradSchemes { default Gauss linear; }",
        "gradSchemes { default Gauss linear; grad(k) Gauss linear; grad(epsilon) Gauss linear; }",
    )
    schemes = schemes.replace(
        "div(rhoPhi,U) Gauss limitedLinearV 1;",
        "div(rhoPhi,U) Gauss limitedLinearV 1;\n"
        "    div(rhoPhi,k) Gauss limitedLinear 1;\n"
        "    div(rhoPhi,epsilon) Gauss limitedLinear 1;",
    )
    schemes_path.write_text(schemes, encoding="utf-8")

    solution_path = case_dir / "system" / "fvSolution"
    solution = solution_path.read_text(encoding="utf-8")
    turbulence_solvers = (
        '    "(k|epsilon)" { solver smoothSolver; smoother GaussSeidel; '
        "tolerance 1e-8; relTol 0.1; nSweeps 2; maxIter 100; }\n"
        '    "(k|epsilon)Final" { solver smoothSolver; smoother GaussSeidel; '
        "tolerance 1e-8; relTol 0; nSweeps 2; maxIter 100; }\n"
    )
    if solution.count("PIMPLE\n") != 1:
        raise ValueError("fvSolution lacks a unique PIMPLE section")
    solution = solution.replace("\n}\nPIMPLE\n", "\n" + turbulence_solvers + "}\nPIMPLE\n", 1)
    solution_path.write_text(solution, encoding="utf-8")

    details.update(
        {
            "case_id": "restas_four_slot_still_air_long_horizon",
            "evidence_label": "exploratory near-field CPU VOF run; all device, source, and turbulence inputs provisional",
            "domain_bounds_m": DOMAIN,
            "mesh_cells_expected": EXPECTED_CELLS,
            "mesh_cell_width_m": {
                "slot_short_axis_x": 0.025,
                "slot_long_axis_y": 0.025,
                "vertical_top_cell_approx": _Z_TOP_CELL_M,
                "vertical_bottom_cell_approx": _Z_BOTTOM_CELL_M,
                "vertical_grading_end_to_start": Z_END_TO_START_GRADING,
            },
            "cells_across_slot_short_axis": 6,
            "cells_along_slot_long_axis": 40,
            "vertical_cells": NZ,
            "crossflow_m_s": [0.0, 0.0, 0.0],
            "crossflow_evidence": "user-selected still-air assumption; aircraft, rotor, and ambient wind omitted",
            "turbulence_model": "realizable k-epsilon RANS",
            "source_turbulence_intensity": 0.01,
            "source_turbulence_intensity_evidence": "Rouaix et al. (2023) Case 1 inlet value, borrowed provisionally for this different slot source",
            "source_turbulent_kinetic_energy_m2_s2": SLOT_K,
            "source_dissipation_rate_m2_s3": SLOT_EPSILON,
            "source_turbulence_length_scale_m": TURBULENCE_LENGTH_M,
            "ambient_air_turbulence": "quiescent initial air; low numerical k/epsilon floor; ambient turbulence is unmeasured",
            "source_profile_m_s": [
                [0.0, -4.8],
                [0.0795, -4.8],
                [0.0805, 0.0],
                [1.0, 0.0],
            ],
            "source_window_s": [0.0, 0.0805],
            "source_shutoff_s": 0.0805,
            "source_shutoff_ramp_s": [0.0795, 0.0805],
            "expected_released_mass_kg": 230.4,
            "expected_alpha_phi_left_sampled_release_kg": 230.544,
            "expected_alpha_phi_left_sampled_release_per_slot_kg": 57.636,
            "end_time_s": END_TIME_S,
            "fixed_delta_t_s": DELTA_T_S,
            "time_step_mode": "fixed",
            "adjust_time_step": False,
            "expected_time_steps": STEP_COUNT,
            "source_dose_tolerance_fraction": SOURCE_TOLERANCE,
            "mass_ledger_tolerance_fraction": LEDGER_TOLERANCE,
            "domain_exit_boundary_note": "A ballistic 4.8 m/s parcel under gravity travels about 9.7 m in 1 s; late-time liquid may approach the lower outlet.",
            "scope_limitations": [
                "no aircraft body, wake, rotor flow, or ambient wind",
                "no measured four-slot geometry, discharge trace, source turbulence, or air turbulence",
                "not a Legendre ground-pattern reproduction or Calbrix matched reproduction",
                "RANS turbulence is a provisional engineering closure; no mesh/time-step convergence claim",
                "no ground, parcel handoff, foam, evaporation, fire, or post-impact model",
                "not E1-E6 validation or a built-system prediction",
            ],
        }
    )
    for key in (
        "experiment_id",
        "protocol_revision",
        "protocol_amendment_id",
        "alpha_phi_left_sampled_expected_release_kg",
        "alpha_phi_left_sampled_expected_release_per_slot_kg",
        "phi_right_sampled_expected_release_kg",
    ):
        details.pop(key, None)
    return details


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ledger_summary(run_dir: Path) -> dict[str, Any]:
    case_dir = run_dir / "case"
    inputs = json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
    tables: dict[str, ledger.ParsedTable] = {}
    for name in (*SOURCE_NAMES, *OPEN_NAMES):
        path, path_issues = ledger._function_object_table_path(
            case_dir, f"{name}Flux", "surfaceFieldValue.dat"
        )
        table = ledger._parse_table(path, name, ("alphaPhi",))
        table.issues.extend(path_issues)
        tables[name] = table
    volume_path, volume_issues = ledger._function_object_table_path(
        case_dir, "waterVolume", "volFieldValue.dat"
    )
    volume = ledger._parse_table(volume_path, "waterVolume", ("volume",))
    volume.issues.extend(volume_issues)

    all_tables = [*tables.values(), volume]
    sample_counts = {table.name: len(table.samples) for table in all_tables}
    all_issues = {table.name: list(table.issues) for table in all_tables if table.issues}
    integrated = {name: ledger._integrate(table, "alphaPhi")[0] for name, table in tables.items()}
    common_times = ledger._common_times(all_tables)
    density = float(inputs["water"]["density_kg_m3"])
    samples = []
    for time_s in common_times:
        source_mass = sum(
            -density * (ledger._integral_at(integrated[name], time_s) or 0.0)
            for name in SOURCE_NAMES
        )
        exit_mass = density * sum(
            ledger._integral_at(integrated[name], time_s) or 0.0 for name in OPEN_NAMES
        )
        inventory_sample = ledger._sample_at(volume.samples, time_s)
        inventory_mass = (
            density * inventory_sample.values["volume"] if inventory_sample is not None else None
        )
        residual = source_mass - exit_mass - inventory_mass if inventory_mass is not None else None
        samples.append(
            {
                "time_s": time_s,
                "source_mass_kg": source_mass,
                "open_boundary_mass_kg": exit_mass,
                "inventory_mass_kg": inventory_mass,
                "residual_kg": residual,
            }
        )

    final = samples[-1] if samples else None
    per_slot = {
        name: -density * (ledger._integral_at(integrated[name], END_TIME_S) or 0.0)
        for name in SOURCE_NAMES
    }
    target_per_slot = float(inputs["expected_alpha_phi_left_sampled_release_per_slot_kg"])
    target_source = float(inputs["expected_alpha_phi_left_sampled_release_kg"])
    target_residual = target_source - float(final["source_mass_kg"]) if final else None
    max_relative_residual = max(
        (
            abs(float(sample["residual_kg"])) / max(float(sample["source_mass_kg"]), 1.0)
            for sample in samples
            if sample["residual_kg"] is not None
        ),
        default=None,
    )
    max_residual_sample = max(
        (sample for sample in samples if sample["residual_kg"] is not None),
        key=lambda sample: abs(float(sample["residual_kg"])),
        default=None,
    )
    log_path = run_dir / "openfoam-console.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    k_bounds = [
        (float(low), float(high))
        for low, high in re.findall(
            rf"bounding k, min: ({ledger.NUMBER}) max: ({ledger.NUMBER})", log_text
        )
    ]
    source_ok = (
        len(common_times) >= STEP_COUNT
        and final is not None
        and abs(target_residual or 0.0) <= SOURCE_TOLERANCE * target_source
        and all(
            abs(value - target_per_slot) <= SOURCE_TOLERANCE * target_per_slot
            for value in per_slot.values()
        )
    )
    ledger_ok = (
        len(common_times) >= STEP_COUNT
        and max_relative_residual is not None
        and max_relative_residual <= LEDGER_TOLERANCE
    )
    return {
        "classification": "exploratory numerical diagnostics; not a scientific validation gate",
        "expected_step_count": STEP_COUNT,
        "common_sample_count": len(common_times),
        "table_sample_counts": sample_counts,
        "table_issues": all_issues,
        "source_dose_target_kg_left_sampled": target_source,
        "source_dose_per_slot_target_kg_left_sampled": target_per_slot,
        "observed_source_dose_kg": final["source_mass_kg"] if final else None,
        "observed_source_per_slot_kg": per_slot,
        "source_dose_within_0p1_percent": source_ok,
        "final_open_boundary_mass_kg": final["open_boundary_mass_kg"] if final else None,
        "final_domain_inventory_kg": final["inventory_mass_kg"] if final else None,
        "final_mass_residual_kg": final["residual_kg"] if final else None,
        "maximum_relative_mass_residual": max_relative_residual,
        "maximum_residual_time_s": max_residual_sample["time_s"] if max_residual_sample else None,
        "mass_ledger_within_0p1_percent": ledger_ok,
        "turbulence_field_bounds": {
            "k_bounding_events": len(k_bounds),
            "minimum_prebounded_k_m2_s2": min((low for low, _ in k_bounds), default=None),
            "maximum_prebounded_k_m2_s2": max((high for _, high in k_bounds), default=None),
        },
    }


def _probe_solver() -> str:
    image_id = pilot._docker_image_id()
    probe = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            pilot.IMAGE,
            "-c",
            pilot.IMAGE_PROBE,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode:
        raise RuntimeError(f"OpenFOAM solver probe failed: {probe.stderr.strip()}")
    return image_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    available = pilot.effective_cpu_count()
    if not 1 <= args.threads <= max(1, available - 2):
        parser.error(f"--threads must be 1..{max(1, available - 2)} to keep two CPUs available")
    if args.memory_gib < 4 or args.memory_gib > 48:
        parser.error("--memory-gib must be between 4 and 48")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"restas-still-air-{stamp}-{uuid.uuid4().hex[:8]}"
    run_dir = ROOT / "results" / "runs" / run_id
    case_dir = run_dir / "case"
    case_dir.mkdir(parents=True, exist_ok=False)
    inputs = _prepare_case(case_dir, args.threads)
    inputs_path = run_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    source_paths = (
        Path(__file__),
        ROOT / "scripts" / "run_restas_pilot.py",
        ROOT / "scripts" / "analyze_restas_pilot.py",
        ROOT / "scripts" / "analyze_restas_ledger.py",
        ROOT / "scripts" / "doctor.py",
        ROOT / "scripts" / "run_local.py",
        ROOT / "cases" / "restas_four_slot" / "README.md",
        ROOT / "track2_aerial_drop_experiment_plan.md",
        ROOT
        / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf",
        ROOT / "cases" / "e1_rouaix_case1_static" / "case" / "constant" / "turbulenceProperties",
    )
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=False, capture_output=True, text=True
    ).stdout
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_utc": datetime.now(UTC).isoformat(),
        "git_revision": pilot._git_revision(),
        "git_worktree_dirty": bool(git_status.strip()),
        "source_sha256": {str(path.relative_to(ROOT)): _sha256(path) for path in source_paths},
        "inputs_sha256": _sha256(inputs_path),
        "prepared_case_file_hashes": {
            str(path.relative_to(case_dir)): _sha256(path)
            for path in sorted(case_dir.rglob("*"))
            if path.is_file() and path.relative_to(case_dir).parts[0] in {"0", "constant", "system"}
        },
        "solver_image": pilot.IMAGE,
        "solver_image_id": "not-probed" if args.prepare_only else _probe_solver(),
        "execution": {
            "mpi_ranks": args.threads,
            "docker_cpu_limit": args.threads + 2,
            "docker_memory_limit_gib": args.memory_gib,
            "wall_time_limit_s": WALL_LIMIT_S,
            "fixed_delta_t_s": DELTA_T_S,
            "expected_time_steps": STEP_COUNT,
            "hard_stop_courant_limits": {"global": 0.5, "interface": 0.25},
        },
        "scope": "exploratory still-air near-field CPU VOF; no validation claim",
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Run directory: {run_dir.relative_to(ROOT)}", flush=True)
    print(f"Expected mesh cells: {EXPECTED_CELLS:,}", flush=True)
    print(
        f"Grid: six cells across 0.15 m slots; forty cells along each 1 m slot; "
        f"{NZ} graded vertical cells",
        flush=True,
    )
    print(
        "Source target: 230.4 kg continuous; 230.544 kg in the fixed-step left-sampled ledger",
        flush=True,
    )
    if args.prepare_only:
        print("Prepared only; solver not started.", flush=True)
        return 0

    run_started = time.monotonic()
    return_code, samples, stop_reason, stop_confirmed, stop_error, monitor_errors = (
        pilot._run_container(
            case_dir,
            run_dir,
            run_id,
            args.threads,
            args.memory_gib,
            courant_limits=(0.5, 0.25),
            wall_timeout_s=WALL_LIMIT_S,
        )
    )
    finished = datetime.now(UTC).isoformat()
    stage_records = pilot._case_stage_exit_records(run_dir / "openfoam-console.log")
    manifest.update(
        {
            "finished_utc": finished,
            "wall_time_s": time.monotonic() - run_started,
            "exit_code": return_code,
            "case_command_exit_code": return_code,
            "case_stage_exit_records": stage_records,
            "interisofoam_exit_code": next(
                (row["exit_code"] for row in stage_records if row["stage"] == "interIsoFoam"), None
            ),
            "reconstruction_exit_code": next(
                (row["exit_code"] for row in stage_records if row["stage"] == "reconstructPar"),
                None,
            ),
            "stop_reason": stop_reason,
            "stop_confirmed": stop_confirmed,
            "stop_error": stop_error,
            "resource_monitor_errors": monitor_errors,
            "docker_resource_samples": samples,
            "resource_sample_note": "Docker stats snapshots at approximately two-second intervals; between-sample peaks may be higher.",
            "case_file_hashes": {
                str(path.relative_to(case_dir)): _sha256(path)
                for path in sorted(case_dir.rglob("*"))
                if path.is_file()
                and path.relative_to(case_dir).parts[0] in {"0", "constant", "system"}
            },
            "surface_artifact_hashes": {
                str(path.relative_to(run_dir)): _sha256(path)
                for path in sorted((case_dir / "postProcessing").rglob("*.vtp"))
                if path.is_file()
            },
        }
    )
    if stop_reason and stop_reason.startswith("wall-time"):
        return_code = 124
    manifest["exit_code"] = return_code
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_summary = _ledger_summary(run_dir)
    (run_dir / "source-ledger-summary.json").write_text(
        json.dumps(source_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = pilot_report.build_report(run_dir)
    (run_dir / "pilot-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if return_code == 0 and not (
        source_summary["source_dose_within_0p1_percent"]
        and source_summary["mass_ledger_within_0p1_percent"]
    ):
        return_code = 1
    manifest["exit_code"] = return_code
    manifest["finished_utc"] = finished
    manifest["diagnostic_artifact_hashes"] = {
        relative: _sha256(run_dir / relative)
        for relative in ("openfoam-console.log", "pilot-report.json", "source-ledger-summary.json")
        if (run_dir / relative).is_file()
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Exploratory source-dose check: {source_summary['source_dose_within_0p1_percent']}",
        flush=True,
    )
    print(
        f"Exploratory mass-ledger check: {source_summary['mass_ledger_within_0p1_percent']}",
        flush=True,
    )
    print(f"Run exit: {return_code}", flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
