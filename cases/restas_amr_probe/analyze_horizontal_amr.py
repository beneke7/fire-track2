#!/usr/bin/env python3
"""Analyze the horizontal four-slot AMR run and frozen laminar reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AMR_RUN = ROOT / "results/runs"
DEFAULT_REFERENCE = ROOT / "results/runs/restas-hnf-laminar-20260928T145501Z-4fe554"
OPEN_BOUNDARIES = ("xOutlet", "airInlet", "airOutlet")
SLOT_PATCHES = ("slot_01", "slot_02", "slot_03", "slot_04")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_times(case: Path) -> list[Path]:
    found: list[Path] = []
    for path in case.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if math.isfinite(value) and value >= 0:
            found.append(path)
    return sorted(found, key=lambda path: float(path.name))


def histogram(values: np.ndarray) -> dict[str, int]:
    labels, counts = np.unique(np.rint(values).astype(int), return_counts=True)
    return {str(int(label)): int(count) for label, count in zip(labels, counts, strict=True)}


def parse_flux_files(case: Path) -> dict[str, list[tuple[float, float]]]:
    result: dict[str, list[tuple[float, float]]] = {}
    for patch in (*SLOT_PATCHES, *OPEN_BOUNDARIES):
        rows: list[tuple[float, float]] = []
        for path in sorted(
            (case / "postProcessing" / f"{patch}Flux").glob("*/surfaceFieldValue.dat")
        ):
            for line in path.read_text(errors="replace").splitlines():
                parts = line.split()
                if len(parts) >= 3 and not line.lstrip().startswith("#"):
                    try:
                        rows.append((float(parts[0]), float(parts[2])))
                    except ValueError:
                        continue
        result[patch] = sorted(rows)
    return result


def integrate_flux(rows: list[tuple[float, float]], *, inward: bool) -> float:
    """Integrate a boundary alphaPhi_ sum in m3; OpenFOAM uses outward normals."""
    if len(rows) < 1:
        return 0.0
    sign = -1.0 if inward else 1.0
    rates = [(time_s, max(0.0, sign * rate_m3_s)) for time_s, rate_m3_s in rows]
    total = rates[0][0] * rates[0][1]
    for (ta, qa), (tb, qb) in zip(rates, rates[1:], strict=False):
        total += (tb - ta) * (qa + qb) / 2.0
    return total


def solver_diagnostics(log: str) -> dict[str, Any]:
    solver = log.rsplit("Exec   : interIsoFoam -parallel", 1)[-1]
    solver = re.split(r"\nExec\s+: (?:reconstructParMesh|reconstructPar)\b", solver, maxsplit=1)[0]
    clocks = [
        (float(cpu), float(wall))
        for cpu, wall in re.findall(
            r"^ExecutionTime =\s*([0-9.eE+-]+) s\s+ClockTime =\s*([0-9.eE+-]+) s",
            solver,
            re.M,
        )
    ]
    p_iterations = [
        int(value)
        for value in re.findall(r"GAMG:\s+Solving for p_rgh,.*?No Iterations (\d+)", solver)
    ]
    time_steps: list[float] = []
    refinement_events: list[dict[str, Any]] = []
    active_time: float | None = None
    for line in solver.splitlines():
        time_match = re.match(r"^Time =\s*([0-9.eE+-]+)", line)
        if time_match:
            active_time = float(time_match.group(1))
            time_steps.append(active_time)
        refine = re.search(r"Refined from (\d+) to (\d+) cells\.", line)
        unrefine = re.search(r"Unrefined from (\d+) to (\d+) cells\.", line)
        match = refine or unrefine
        if match:
            refinement_events.append(
                {
                    "time_s": active_time,
                    "operation": "refine" if refine else "unrefine",
                    "cells_before": int(match.group(1)),
                    "cells_after": int(match.group(2)),
                    "delta_cells": int(match.group(2)) - int(match.group(1)),
                }
            )
    dt = np.diff(np.asarray(time_steps, dtype=float))
    return {
        "last_time_s": time_steps[-1] if time_steps else None,
        "solver_steps": len(clocks),
        "solver_clock_time_s": clocks[-1][1] if clocks else None,
        "solver_cpu_time_s": clocks[-1][0] if clocks else None,
        "mean_clock_time_per_step_s": clocks[-1][1] / len(clocks) if clocks else None,
        "pressure_solve_count": len(p_iterations),
        "pressure_iteration_total": sum(p_iterations),
        "mean_pressure_iterations_per_solve": sum(p_iterations) / len(p_iterations)
        if p_iterations
        else None,
        "max_courant_number": max(
            (
                float(value)
                for value in re.findall(
                    r"^Courant Number mean:.*? max: ([0-9.eE+-]+)", solver, re.M
                )
            ),
            default=None,
        ),
        "max_interface_courant_number": max(
            (
                float(value)
                for value in re.findall(
                    r"^Interface Courant Number mean:.*? max: ([0-9.eE+-]+)", solver, re.M
                )
            ),
            default=None,
        ),
        "observed_delta_t_min_s": float(dt.min()) if dt.size else None,
        "observed_delta_t_max_s": float(dt.max()) if dt.size else None,
        "refinement_events": refinement_events,
    }


def sampled_ram_gib(manifest: dict[str, Any]) -> float | None:
    direct = manifest.get("peak_sampled_memory_gib")
    if direct is not None:
        return float(direct)
    unit_scale = {"B": 2**-30, "KiB": 2**-20, "MiB": 2**-10, "GiB": 1.0}
    values: list[float] = []
    for sample in manifest.get("docker_resource_samples", []):
        match = re.match(r"([0-9.]+)\s*(B|KiB|MiB|GiB)", sample.get("memory_usage_and_limit", ""))
        if match:
            values.append(float(match.group(1)) * unit_scale[match.group(2)])
    return max(values, default=None)


def sampled_cpu_percent(manifest: dict[str, Any]) -> float | None:
    direct = manifest.get("peak_sampled_cpu_percent")
    if direct is not None:
        return float(direct)
    return max(
        (
            float(sample["cpu_percent"].rstrip("%"))
            for sample in manifest.get("docker_resource_samples", [])
            if sample.get("cpu_percent")
        ),
        default=None,
    )


def field_diagnostics(run_dir: Path) -> list[dict[str, Any]]:
    case = run_dir / "case"
    times = numeric_times(case)
    if not times:
        raise RuntimeError(f"No reconstructed numeric time directories under {case}")
    with tempfile.TemporaryDirectory(prefix="restas-hnf-amr-analysis-") as temporary:
        view = Path(temporary)
        for source in (case / "constant", case / "system", *times):
            if source.exists():
                (view / source.name).symlink_to(source, target_is_directory=True)
        marker = view / "amr.foam"
        marker.touch()
        reader = pv.OpenFOAMReader(str(marker))
        reader.enable_cell_array("alpha.water")
        try:
            reader.enable_cell_array("cellLevel")
        except (KeyError, ValueError):
            pass
        available_times = [float(value) for value in reader.time_values]
        rows: list[dict[str, Any]] = []
        for folder in times:
            requested = float(folder.name)
            if not any(math.isclose(value, requested, abs_tol=1e-9) for value in available_times):
                continue
            reader.set_active_time_value(requested)
            block = reader.read()
            mesh = block["internalMesh"]
            alpha = np.asarray(mesh.cell_data["alpha.water"], dtype=float)
            centers = mesh.cell_centers().points
            volumes = np.asarray(
                mesh.compute_cell_sizes(length=False, area=False, volume=True).cell_data["Volume"],
                dtype=float,
            )
            if "cellLevel" in mesh.cell_data:
                levels = histogram(np.asarray(mesh.cell_data["cellLevel"], dtype=float))
                level_method = "reconstructed dynamicRefineFvMesh cellLevel field"
            else:
                levels = {"0": int(mesh.n_cells)}
                level_method = "uniform fine reference; no cellLevel field"

            def envelope(mask: np.ndarray) -> dict[str, Any] | None:
                if not np.any(mask):
                    return None
                points = centers[mask]
                return {
                    "x_m": [float(points[:, 0].min()), float(points[:, 0].max())],
                    "y_m": [float(points[:, 1].min()), float(points[:, 1].max())],
                    "z_m": [float(points[:, 2].min()), float(points[:, 2].max())],
                    "downstream_penetration_from_slot_plane_m": float(points[:, 0].max()),
                    "thresholded_cell_count": int(mask.sum()),
                }

            rows.append(
                {
                    "time_s": requested,
                    "cell_count": int(mesh.n_cells),
                    "cells_by_level": levels,
                    "cell_level_method": level_method,
                    "water_inventory_m3": float(alpha @ volumes),
                    "water_inventory_kg": float(alpha @ volumes) * 1000.0,
                    "alpha_ge_0p001_envelope": envelope(alpha >= 0.001),
                    "alpha_ge_0p9_core": envelope(alpha >= 0.9),
                }
            )
        return rows


def summarize_case(run_dir: Path, *, is_amr: bool) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
    log_path = run_dir / "openfoam-console.log"
    log = log_path.read_text(errors="replace") if log_path.is_file() else ""
    fields = field_diagnostics(run_dir)
    fluxes = parse_flux_files(run_dir / "case") if is_amr else {}
    result: dict[str, Any] = {
        "run_id": run_dir.name,
        "case_classification": manifest.get("case_classification", inputs.get("evidence_label")),
        "solver": inputs.get("solver", manifest.get("solver_image")),
        "model": inputs.get("model", inputs.get("turbulence_model")),
        "source_velocity_m_s": inputs.get("source_velocity_m_s_each"),
        "background_air_velocity_m_s": inputs.get("background_air_velocity_m_s"),
        "domain_bounds_m": inputs.get("domain_bounds_m"),
        "mesh_spacing_m": inputs.get(
            "mesh_spacing_m", inputs.get("finest_interface_cell_spacing_m")
        ),
        "expected_cells": inputs.get("mesh_cells_expected"),
        "horizon_s": inputs.get("time", {}).get("end_s", inputs.get("end_time_s")),
        "expected_source_mass_kg": inputs.get("analytic_source_mass_over_horizon_kg"),
        "fields": fields,
        "timing": solver_diagnostics(log) if log else manifest.get("solver_log_summary", {}),
        "resources": {
            "full_pipeline_wall_time_s": manifest.get("wall_time_s"),
            "solver_clock_time_s": (
                solver_diagnostics(log).get("solver_clock_time_s")
                if log
                else manifest.get("solver_log_summary", {}).get("final_reported_clock_time_s")
            ),
            "peak_sampled_cpu_percent": sampled_cpu_percent(manifest),
            "peak_sampled_memory_gib": sampled_ram_gib(manifest),
            "output_tree_bytes": sum(
                path.stat().st_size for path in run_dir.rglob("*") if path.is_file()
            ),
            "resource_sample_count": len(manifest.get("docker_resource_samples", [])),
        },
    }
    if is_amr:
        source_volume = sum(
            integrate_flux(fluxes.get(patch, []), inward=True) for patch in SLOT_PATCHES
        )
        outward_volume = sum(
            integrate_flux(fluxes.get(patch, []), inward=False) for patch in OPEN_BOUNDARIES
        )
        final = fields[-1]
        result["water_ledger"] = {
            "observed_source_inlet_volume_m3": source_volume,
            "observed_source_inlet_mass_kg": source_volume * 1000.0,
            "observed_open_boundary_outflow_volume_m3": outward_volume,
            "observed_open_boundary_outflow_mass_kg": outward_volume * 1000.0,
            "final_vof_inventory_volume_m3": final["water_inventory_m3"],
            "final_vof_inventory_mass_kg": final["water_inventory_kg"],
            "closure_residual_kg": (source_volume - outward_volume - final["water_inventory_m3"])
            * 1000.0,
            "flux_source": "time-integrated OpenFOAM surfaceFieldValue sum(alphaPhi_) at four inlet patches and xOutlet/airInlet/airOutlet; sign is interpreted using outward patch normals",
            "interpretation": "exploratory finite-volume ledger diagnostic; no acceptance tolerance; not a validation gate",
        }
        result["refinement"] = {
            "events": result["timing"].get("refinement_events", []),
            "event_count": len(result["timing"].get("refinement_events", [])),
            "mesh_update_seconds_isolated": None,
            "note": "Stock interIsoFoam step clock includes dynamic mesh updates; the update call is not separately timed.",
        }
    else:
        final = fields[-1]
        result["water_ledger"] = {
            "analytic_source_inlet_mass_kg": inputs.get("analytic_source_mass_over_horizon_kg"),
            "final_vof_inventory_mass_kg": final["water_inventory_kg"],
            "observed_open_boundary_outflow_mass_kg": None,
            "closure_residual_kg": None,
            "note": "Frozen baseline did not record patch phase fluxes; its case and bundle are read-only. Source is analytic and VOF inventory is integrated from saved fields.",
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amr-run-dir", type=Path, required=True)
    parser.add_argument("--reference-run-dir", type=Path, default=DEFAULT_REFERENCE)
    args = parser.parse_args()
    amr_dir = args.amr_run_dir.resolve()
    reference_dir = args.reference_run_dir.resolve()
    amr = summarize_case(amr_dir, is_amr=True)
    reference = summarize_case(reference_dir, is_amr=False)
    comparison = {
        "classification": "Exploratory horizontal four-slot AMR cost and morphology diagnostic; not validation.",
        "amr_run": amr,
        "reference_run": reference,
        "comparison": {
            "same_solver_model_domain_source_and_horizon": True,
            "source_case_hash_comparison": json.loads((amr_dir / "manifest.json").read_text())[
                "common_physics_and_field_file_hashes"
            ],
            "mesh_mismatch": "AMR starts at 0.05 m base spacing (100,368 cells) and permits one dynamic level to 0.025 m near alpha.water interfaces; reference is uniformly 0.025 m (802,944 cells).",
            "time_step_mismatch": "Both use the same adaptive controls, but local mesh-dependent Co can change the realized time-step sequence; compare observed steps/Co and timings rather than claiming identical dt history.",
            "measurement_mismatches": "AMR run adds patch flux function objects and reconstructs only selected fields; reference bundle is left untouched and contains its original outputs.",
            "mesh_update_wall_time": "Included in total solver ClockTime; dynamicRefineFvMesh update time is not separately exposed by these stock logs.",
            "validation_status": "Exploratory only. Neither this result nor the frozen baseline is an E1-E6 validation pass or device reproduction.",
        },
    }
    (amr_dir / "horizontal-amr-timeseries.json").write_text(
        json.dumps(
            {"amr": amr["fields"], "reference": reference["fields"]}, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    (amr_dir / "horizontal-amr-report.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if amr.get("refinement"):
        (amr_dir / "refinement-events.json").write_text(
            json.dumps(amr["refinement"]["events"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    manifest = json.loads((amr_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["analysis_artifacts"] = [
        "horizontal-amr-timeseries.json",
        "horizontal-amr-report.json",
        "refinement-events.json",
    ]
    manifest["analysis_source_sha256"] = sha256(Path(__file__).resolve())
    manifest["renderer_source_sha256"] = sha256(ROOT / "cases/restas_amr_probe/render_probe.py")
    manifest["run_sha256"] = {
        str(path.relative_to(amr_dir)): sha256(path)
        for path in sorted(amr_dir.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    manifest["output_tree_bytes"] = sum(
        path.stat().st_size for path in amr_dir.rglob("*") if path.is_file()
    )
    (amr_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "amr_run": amr_dir.name,
                "reference_run": reference_dir.name,
                "cells": [row["cell_count"] for row in amr["fields"]],
                "levels": [row["cells_by_level"] for row in amr["fields"]],
                "final_inventory_kg": amr["fields"][-1]["water_inventory_kg"],
                "closure_residual_kg": amr["water_ledger"]["closure_residual_kg"],
                "events": amr.get("refinement", {}).get("event_count"),
                "report": str((amr_dir / "horizontal-amr-report.json").relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
