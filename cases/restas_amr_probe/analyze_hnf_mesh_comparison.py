#!/usr/bin/env python3
"""Common-grid plume and mass diagnostics for horizontal mesh comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[2]
SLOT_PATCHES = ("slot_01", "slot_02", "slot_03", "slot_04")
OPEN_PATCHES = ("xOutlet", "airInlet", "airOutlet")
DEFAULT_THRESHOLDS = (0.1, 0.5, 0.65, 0.9)


def normalize_mesh_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Fill mesh metadata for older uniform reference bundles."""
    if "mesh_method" not in inputs:
        inputs["mesh_method"] = "uniform"
        inputs["target_finest_spacing_m"] = float(inputs["mesh_spacing_m"])
    return inputs


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_field_dirs(case: Path) -> list[Path]:
    found = []
    for path in case.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if value >= 0 and (path / "alpha.water").is_file():
            found.append(path)
    return sorted(found, key=lambda p: float(p.name))


def rows_in_surface_file(path: Path) -> list[tuple[float, float]]:
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 3 and not line.lstrip().startswith("#"):
            try:
                rows.append((float(parts[0]), float(parts[2])))
            except ValueError:
                continue
    return rows


def boundary_flux_history(case: Path) -> dict[str, list[tuple[float, float]]]:
    """Read one trajectory, replacing abandoned output after each restart.

    OpenFOAM writes function objects into a directory named for the solver's
    start time. A copied case may retain records beyond its restart checkpoint;
    those belong to the abandoned trajectory. Retain the checkpoint-time row
    as an integration anchor, with a newer branch winning duplicate times.
    """
    histories: dict[str, list[tuple[float, float]]] = {}
    for patch in (*SLOT_PATCHES, *OPEN_PATCHES):
        branches = sorted(
            (float(path.parent.name), path)
            for path in (case / "postProcessing" / f"{patch}Flux").glob("*/surfaceFieldValue.dat")
        )
        starts = [start for start, _ in branches]
        if len(set(starts)) != len(starts):
            raise ValueError(f"ambiguous duplicate flux branch start time for {patch}")
        flux_by_time: dict[float, float] = {}
        for index, (start, path) in enumerate(branches):
            end = starts[index + 1] if index + 1 < len(starts) else math.inf
            for timestamp, flux in rows_in_surface_file(path):
                if start <= timestamp <= end:
                    flux_by_time[timestamp] = flux
        histories[patch] = sorted(flux_by_time.items())
    return histories


def integrate_boundary_volume(rows: list[tuple[float, float]], *, inward: bool) -> float:
    if not rows:
        return 0.0
    if inward:
        values = [(t, max(0.0, -q)) for t, q in rows]
    else:
        values = list(rows)
    total = values[0][0] * values[0][1]
    for (ta, qa), (tb, qb) in zip(values, values[1:], strict=False):
        total += (tb - ta) * (qa + qb) / 2.0
    return total


def width_per_center(
    centers: np.ndarray,
    *,
    breaks: list[float],
    widths: list[float],
) -> np.ndarray:
    if len(breaks) != len(widths) + 1:
        raise ValueError("mesh segment metadata is inconsistent")
    indices = np.clip(
        np.searchsorted(np.asarray(breaks), centers, side="right") - 1, 0, len(widths) - 1
    )
    return np.asarray(widths, dtype=np.float64)[indices]


def native_cell_widths(
    centers: np.ndarray,
    level_values: np.ndarray | None,
    inputs: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    method = inputs["mesh_method"]
    if method == "dynamic":
        base = float(inputs["starting_mesh_spacing_m"])
        levels = (
            np.zeros(len(centers), dtype=np.int16)
            if level_values is None
            else np.rint(level_values).astype(np.int16)
        )
        widths = base / np.power(2.0, levels.astype(np.float64))
        return widths, widths, widths
    if method == "uniform":
        h = float(inputs["target_finest_spacing_m"])
        widths = np.full(len(centers), h, dtype=np.float64)
        return widths, widths, widths
    if method != "static":
        raise ValueError(f"unsupported mesh method in inputs: {method}")
    result = []
    for axis, axis_index in (("x", 0), ("y", 1), ("z", 2)):
        result.append(
            width_per_center(
                centers[:, axis_index],
                breaks=inputs[f"{axis}_breaks_m"],
                widths=inputs[f"{axis}_widths_by_segment_m"],
            )
        )
    return result[0], result[1], result[2]


def map_alpha_to_common_grid(
    alpha: np.ndarray,
    centers: np.ndarray,
    widths: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    bounds: dict[str, list[float]],
    common_h_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    axes = ("x", "y", "z")
    lower = np.asarray([bounds[axis][0] for axis in axes], dtype=np.float64)
    lengths = np.asarray([bounds[axis][1] - bounds[axis][0] for axis in axes], dtype=np.float64)
    shape_float = lengths / common_h_m
    shape = np.rint(shape_float).astype(int)
    if not np.allclose(shape_float, shape, rtol=0, atol=1e-7):
        raise ValueError("common-grid spacing does not divide every domain length")
    grid = np.zeros(tuple(shape), dtype=np.float32)
    coverage = np.zeros(tuple(shape), dtype=bool)
    wx, wy, wz = widths
    repeats = np.column_stack(
        tuple(np.rint(width / common_h_m).astype(np.int32) for width in widths)
    )
    if np.any(repeats < 1) or np.any(np.abs(repeats * common_h_m - np.column_stack(widths)) > 1e-7):
        raise ValueError("native cell widths are not integer multiples of common-grid spacing")
    low_indices = np.column_stack(
        tuple(
            np.rint((centers[:, i] - lower[i] - 0.5 * width) / common_h_m).astype(np.int64)
            for i, width in enumerate(widths)
        )
    )
    if np.any(low_indices < 0) or np.any(low_indices + repeats > shape):
        raise ValueError("a native cell lies outside the declared common-grid bounds")
    groups, inverse = np.unique(repeats, axis=0, return_inverse=True)
    for group_id, group in enumerate(groups):
        selected = np.flatnonzero(inverse == group_id)
        x0, y0, z0 = low_indices[selected].T
        vals = alpha[selected].astype(np.float32, copy=False)
        rx, ry, rz = map(int, group)
        for ox in range(rx):
            for oy in range(ry):
                for oz in range(rz):
                    grid[x0 + ox, y0 + oy, z0 + oz] = vals
                    coverage[x0 + ox, y0 + oy, z0 + oz] = True
    if not bool(np.all(coverage)):
        missing = int(coverage.size - np.count_nonzero(coverage))
        raise ValueError(f"common-grid mapping left {missing} voxels unfilled")
    width_triplets = Counter(map(tuple, repeats.tolist()))
    occupancy = {
        "common_grid_shape": shape.tolist(),
        "common_grid_voxels": int(grid.size),
        "native_cells_by_repeat_factor_xyz": {
            "x".join(map(str, key)): value for key, value in width_triplets.items()
        },
    }
    return grid, occupancy


def common_grid_metrics(
    alpha: np.ndarray,
    *,
    common_h_m: float,
    domain_bounds: dict[str, list[float]],
    thresholds: tuple[float, ...],
) -> dict[str, Any]:
    shape = alpha.shape
    cell_volume = common_h_m**3
    axes = (
        domain_bounds["x"][0] + (np.arange(shape[0], dtype=np.float64) + 0.5) * common_h_m,
        domain_bounds["y"][0] + (np.arange(shape[1], dtype=np.float64) + 0.5) * common_h_m,
        domain_bounds["z"][0] + (np.arange(shape[2], dtype=np.float64) + 0.5) * common_h_m,
    )
    all_water_volume = float(np.sum(alpha, dtype=np.float64) * cell_volume)
    threshold_data: dict[str, Any] = {}
    for threshold in (*thresholds, 0.001):
        mask_volume = 0.0
        occupied_count = 0
        centroid_moment = np.zeros(3, dtype=np.float64)
        x_lo = y_lo = z_lo = None
        x_hi = y_hi = z_hi = None
        max_area = 0.0
        max_area_x = None
        for ix in range(shape[0]):
            plane = alpha[ix]
            mask = plane >= threshold
            if not np.any(mask):
                continue
            yz = np.nonzero(mask)
            values = plane[mask].astype(np.float64, copy=False)
            weight_sum = float(values.sum()) * cell_volume
            mask_volume += weight_sum
            occupied_count += len(values)
            centroid_moment[0] += axes[0][ix] * weight_sum
            centroid_moment[1] += float(values @ axes[1][yz[0]]) * cell_volume
            centroid_moment[2] += float(values @ axes[2][yz[1]]) * cell_volume
            y0, y1 = int(yz[0].min()), int(yz[0].max())
            z0, z1 = int(yz[1].min()), int(yz[1].max())
            x_lo = ix if x_lo is None else x_lo
            x_hi = ix
            y_lo = y0 if y_lo is None else min(y_lo, y0)
            y_hi = y1 if y_hi is None else max(y_hi, y1)
            z_lo = z0 if z_lo is None else min(z_lo, z0)
            z_hi = z1 if z_hi is None else max(z_hi, z1)
            area = int(mask.sum()) * common_h_m**2
            if area > max_area:
                max_area = area
                max_area_x = float(axes[0][ix])
        centroid = (centroid_moment / mask_volume).tolist() if mask_volume else None
        bounds = None
        if x_lo is not None:
            bounds = {
                "x_m": [
                    float(axes[0][x_lo] - common_h_m / 2),
                    float(axes[0][x_hi] + common_h_m / 2),
                ],
                "y_m": [
                    float(axes[1][y_lo] - common_h_m / 2),
                    float(axes[1][y_hi] + common_h_m / 2),
                ],
                "z_m": [
                    float(axes[2][z_lo] - common_h_m / 2),
                    float(axes[2][z_hi] + common_h_m / 2),
                ],
            }
        key = "alpha_ge_0p001_tail" if threshold == 0.001 else f"alpha_ge_{threshold:g}"
        threshold_data[key] = {
            "threshold": threshold,
            "alpha_weighted_volume_m3": mask_volume,
            "occupied_cell_volume_m3": occupied_count * cell_volume,
            "occupied_common_grid_cells": occupied_count,
            "alpha_weighted_centroid_xyz_m": centroid,
            "max_yz_projected_area_m2": max_area,
            "max_area_x_m": max_area_x,
            "bounds_m": bounds,
        }
    return {
        "water_volume_m3": all_water_volume,
        "water_inventory_kg": 1000.0 * all_water_volume,
        "thresholds": threshold_data,
    }


def field_timeseries(
    run_dir: Path, common_h_m: float, thresholds: tuple[float, ...]
) -> list[dict[str, Any]]:
    case = run_dir / "case"
    inputs = normalize_mesh_inputs(
        json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
    )
    times = numeric_field_dirs(case)
    if not times:
        raise RuntimeError(f"no reconstructed alpha.water times in {case}")
    domain_bounds = inputs["domain_bounds_m"]
    bounds = {axis: domain_bounds[axis] for axis in ("x", "y", "z")}
    with tempfile.TemporaryDirectory(prefix="restas-hnf-common-grid-") as temporary:
        reader_case = Path(temporary)
        for source in (case / "constant", case / "system", *times):
            if source.exists():
                (reader_case / source.name).symlink_to(source, target_is_directory=True)
        marker = reader_case / "probe.foam"
        marker.touch()
        reader = pv.OpenFOAMReader(str(marker))
        reader.enable_cell_array("alpha.water")
        if inputs["mesh_method"] == "dynamic":
            reader.enable_cell_array("cellLevel")
        available = [float(value) for value in reader.time_values]
        results: list[dict[str, Any]] = []
        for folder in times:
            time_s = float(folder.name)
            if not any(math.isclose(value, time_s, abs_tol=1e-9) for value in available):
                continue
            reader.set_active_time_value(time_s)
            data = reader.read()["internalMesh"]
            alpha = np.asarray(data.cell_data["alpha.water"], dtype=np.float64)
            centers = data.cell_centers().points
            level = (
                np.asarray(data.cell_data["cellLevel"], dtype=np.float64)
                if "cellLevel" in data.cell_data
                else None
            )
            widths = native_cell_widths(centers, level, inputs)
            grid, occupancy = map_alpha_to_common_grid(
                alpha,
                centers,
                widths,
                bounds=bounds,
                common_h_m=common_h_m,
            )
            metrics = common_grid_metrics(
                grid,
                common_h_m=common_h_m,
                domain_bounds=bounds,
                thresholds=thresholds,
            )
            if level is not None:
                labels, counts = np.unique(np.rint(level).astype(int), return_counts=True)
                level_hist = {
                    str(int(key)): int(value) for key, value in zip(labels, counts, strict=True)
                }
            else:
                level_hist = None
            cell_sizes = np.column_stack(widths)
            native_volumes = np.prod(cell_sizes, axis=1)
            finest = float(inputs["target_finest_spacing_m"])
            target_finest = np.all(np.isclose(cell_sizes, finest, rtol=0, atol=1e-8), axis=1)
            results.append(
                {
                    "time_s": time_s,
                    "native_cell_count": int(data.n_cells),
                    "native_cells_by_dynamic_level": level_hist,
                    "native_cells_at_target_finest_spacing": int(np.count_nonzero(target_finest)),
                    "target_finest_cell_volume_fraction": float(
                        native_volumes[target_finest].sum() / native_volumes.sum()
                    ),
                    "common_grid_mapping": occupancy,
                    "common_grid_metrics": metrics,
                }
            )
        return results


def read_solver_metrics(manifest: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    summary = manifest.get("solver_log_summary", {})
    log = (run_dir / "openfoam-console.log").read_text(errors="replace")
    clock_rows = [
        (float(cpu), float(wall))
        for cpu, wall in re.findall(
            r"^ExecutionTime =\s*([0-9.eE+-]+) s\s+ClockTime =\s*([0-9.eE+-]+) s",
            log,
            re.M,
        )
    ]
    pressure = [
        int(value) for value in re.findall(r"GAMG:\s+Solving for p_rgh,.*?No Iterations (\d+)", log)
    ]
    events = summary.get("refinement_events", [])
    cpu_samples = []
    ram_samples_gib = []
    for row in manifest.get("docker_resource_samples", []):
        try:
            cpu_samples.append(float(str(row.get("cpu_percent", "0")).rstrip("%")))
            memory = str(row.get("memory_usage_and_limit", "")).split("/", maxsplit=1)[0]
            match = re.search(r"([0-9.]+)\s*(KiB|MiB|GiB)", memory)
            if match:
                amount, unit = match.groups()
                scale = {"KiB": 1024**2, "MiB": 1024, "GiB": 1}[unit]
                ram_samples_gib.append(float(amount) / scale)
        except (ValueError, TypeError):
            continue
    clock_time = summary.get(
        "solver_clock_time_s",
        summary.get("final_reported_clock_time_s", clock_rows[-1][1] if clock_rows else None),
    )
    pressure_iterations = summary.get(
        "pressure_iteration_total", sum(pressure) if pressure else None
    )
    pressure_count = summary.get("pressure_solve_count", len(pressure) if pressure else None)
    return {
        "solver_steps": summary.get(
            "solver_steps", summary.get("positive_time_records", len(clock_rows) or None)
        ),
        "solver_clock_time_s": clock_time,
        "mean_clock_time_per_step_s": summary.get(
            "mean_clock_time_per_step_s",
            clock_time / len(clock_rows) if clock_time is not None and clock_rows else None,
        ),
        "pressure_solve_count": pressure_count,
        "pressure_iteration_total": pressure_iterations,
        "mean_pressure_iterations_per_solve": summary.get(
            "mean_pressure_iterations_per_solve",
            pressure_iterations / pressure_count
            if pressure_iterations and pressure_count
            else None,
        ),
        "max_courant_number": summary.get("max_courant_number"),
        "max_interface_courant_number": summary.get("max_interface_courant_number"),
        "refinement_events": len(events),
        "refine_event_count": sum(event.get("operation") == "refine" for event in events),
        "unrefine_event_count": sum(event.get("operation") == "unrefine" for event in events),
        "peak_sampled_cpu_percent": manifest.get(
            "peak_sampled_cpu_percent", max(cpu_samples, default=None)
        ),
        "peak_sampled_memory_gib": manifest.get(
            "peak_sampled_memory_gib", max(ram_samples_gib, default=None)
        ),
    }


def summarize_run(
    run_dir: Path, common_h_m: float, thresholds: tuple[float, ...]
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    inputs = normalize_mesh_inputs(
        json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
    )
    timeseries = field_timeseries(run_dir, common_h_m, thresholds)
    fluxes = boundary_flux_history(run_dir / "case")
    inlet_volume = sum(
        integrate_boundary_volume(fluxes.get(patch, []), inward=True) for patch in SLOT_PATCHES
    )
    outlet_volume = sum(
        integrate_boundary_volume(fluxes.get(patch, []), inward=False) for patch in OPEN_PATCHES
    )
    final_inventory = timeseries[-1]["common_grid_metrics"]["water_volume_m3"]
    has_inlet_flux = any(fluxes.get(patch) for patch in SLOT_PATCHES)
    has_open_flux = any(fluxes.get(patch) for patch in OPEN_PATCHES)
    inlet_mass = inlet_volume * 1000.0 if has_inlet_flux else None
    outflow_mass = outlet_volume * 1000.0 if has_open_flux else None
    closure = (
        (inlet_volume - outlet_volume - final_inventory) * 1000.0
        if has_inlet_flux and has_open_flux
        else None
    )
    expected_mass = inputs.get("source", {}).get(
        "source_mass_expected_kg", inputs.get("analytic_source_mass_over_horizon_kg")
    )
    solver_metrics = read_solver_metrics(manifest, run_dir)
    return {
        "run_id": run_dir.name,
        "stage": manifest.get("stage"),
        "variant": manifest.get("variant"),
        "mesh_method": inputs.get("mesh_method"),
        "mesh_shape": inputs.get("mesh_shape"),
        "mesh_cells_expected": inputs.get("mesh_cells_expected"),
        "target_finest_spacing_m": inputs.get("target_finest_spacing_m"),
        "static_refinement_box_m": inputs.get("static_refinement_box_m"),
        "domain_bounds_m": inputs.get("domain_bounds_m"),
        "model": inputs.get("model"),
        "source": inputs.get("source", {}),
        "solver": solver_metrics,
        "resources": {
            "pipeline_wall_time_s": manifest.get("wall_time_s"),
            "solver_clock_time_s": solver_metrics["solver_clock_time_s"],
            "peak_sampled_cpu_percent": solver_metrics["peak_sampled_cpu_percent"],
            "peak_sampled_memory_gib": solver_metrics["peak_sampled_memory_gib"],
            "output_tree_bytes": manifest.get("output_tree_bytes"),
            "docker_cpu_limit": manifest.get("execution", {}).get("docker_cpu_limit"),
            "docker_memory_limit_gib": manifest.get("execution", {}).get("docker_memory_limit_gib"),
        },
        "water_ledger": {
            "analytic_expected_source_mass_kg": expected_mass,
            "observed_inlet_mass_kg": inlet_mass,
            "observed_open_boundary_outflow_mass_kg": outflow_mass,
            "final_common_grid_inventory_kg": final_inventory * 1000.0,
            "closure_residual_kg": closure,
            "observed_inlet_volume_m3": inlet_volume,
            "observed_outflow_volume_m3": outlet_volume,
            "interpretation": (
                "Flux-integrated finite-volume diagnostic, not a gate; source pulse is provisional."
                if has_inlet_flux and has_open_flux
                else "The historical reference has no saved per-step alphaPhi_ boundary ledger; source closure cannot be independently reconstructed."
            ),
        },
        "common_grid_spacing_m": common_h_m,
        "common_grid_timeseries": timeseries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dirs", nargs="+", required=True, type=Path)
    parser.add_argument("--common-spacing-m", type=float, required=True)
    parser.add_argument("--thresholds", nargs="+", type=float, default=DEFAULT_THRESHOLDS)
    args = parser.parse_args()
    threshold_tuple = tuple(args.thresholds)
    if any(not 0 < threshold <= 1 for threshold in threshold_tuple):
        parser.error("thresholds must lie in (0,1]")
    summaries = [
        summarize_run(path.resolve(), args.common_spacing_m, threshold_tuple)
        for path in args.run_dirs
    ]
    for summary, run_dir in zip(summaries, (path.resolve() for path in args.run_dirs), strict=True):
        # Never rewrite a historical reference bundle while producing a comparison.
        if "study_stage" not in json.loads((run_dir / "inputs.json").read_text(encoding="utf-8")):
            continue
        (run_dir / "common-grid-report.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["analysis_source_sha256"] = sha256(Path(__file__).resolve())
        manifest["run_sha256"] = {
            str(path.relative_to(run_dir)): sha256(path)
            for path in sorted(run_dir.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        }
        manifest["output_tree_bytes"] = sum(
            path.stat().st_size for path in run_dir.rglob("*") if path.is_file()
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            [
                {
                    "run_id": summary["run_id"],
                    "variant": summary["variant"],
                    "native_cells_final": summary["common_grid_timeseries"][-1][
                        "native_cell_count"
                    ],
                    "solver_clock_time_s": summary["solver"]["solver_clock_time_s"],
                    "wall_time_s": summary["resources"]["pipeline_wall_time_s"],
                    "peak_ram_gib": summary["resources"]["peak_sampled_memory_gib"],
                    "mass_residual_kg": summary["water_ledger"]["closure_residual_kg"],
                    "times": [row["time_s"] for row in summary["common_grid_timeseries"]],
                }
                for summary in summaries
            ],
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
