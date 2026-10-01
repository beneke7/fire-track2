#!/usr/bin/env python3
"""Extract cell-level, liquid-shape, and timing diagnostics from an AMR probe run."""

from __future__ import annotations

import argparse
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[2]
REFINE_BOX = ((-3.0, -1.5, 2.5), (0.5, 1.5, 4.0))
BASE_X = (-7.975, -3.0, -0.175, -0.025, 0.025, 0.175, 0.5, 7.975)
BASE_NX = (25, 57, 3, 1, 3, 7, 37)
BASE_Y = (-3.025, -2.5, -1.025, -0.025, 0.025, 1.025, 2.5, 3.025)
BASE_NY = (3, 30, 20, 1, 20, 30, 3)
BASE_Z = (0.0, 4.0)
BASE_NZ = (32,)


def numeric_time_dirs(case: Path) -> list[Path]:
    found: list[Path] = []
    for path in case.iterdir():
        if path.is_dir():
            try:
                value = float(path.name)
            except ValueError:
                continue
            if math.isfinite(value) and value >= 0:
                found.append(path)
    return sorted(found, key=lambda p: float(p.name))


def base_expected_volume(centers: np.ndarray) -> np.ndarray:
    x_id = np.clip(np.searchsorted(BASE_X, centers[:, 0], side="right") - 1, 0, len(BASE_NX) - 1)
    y_id = np.clip(np.searchsorted(BASE_Y, centers[:, 1], side="right") - 1, 0, len(BASE_NY) - 1)
    z_id = np.clip(np.searchsorted(BASE_Z, centers[:, 2], side="right") - 1, 0, len(BASE_NZ) - 1)
    dx = np.diff(BASE_X)[x_id] / np.asarray(BASE_NX)[x_id]
    dy = np.diff(BASE_Y)[y_id] / np.asarray(BASE_NY)[y_id]
    dz = np.diff(BASE_Z)[z_id] / np.asarray(BASE_NZ)[z_id]
    return dx * dy * dz


def numeric_histogram(values: np.ndarray) -> dict[str, int]:
    labels, counts = np.unique(np.rint(values).astype(int), return_counts=True)
    return {str(int(label)): int(count) for label, count in zip(labels, counts, strict=True)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    case = run_dir / "case"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    inputs = json.loads((run_dir / "inputs.json").read_text())
    log = (run_dir / "openfoam-console.log").read_text(errors="replace")
    solver_log = log.rsplit("Exec   : interIsoFoam -parallel", 1)[-1]
    # The run console continues into reconstructPar, which also prints `Time =`
    # rows for written snapshots. Keep solver step counts and clocks scoped to
    # interIsoFoam itself.
    solver_log = solver_log.split("\nExec   : reconstructPar", 1)[0]
    exec_matches = re.findall(
        r"^ExecutionTime = ([0-9.eE+-]+) s\s+ClockTime = ([0-9.eE+-]+) s", solver_log, re.M
    )
    step_clock = [float(clock) for _, clock in exec_matches]
    refine_events = []
    active_time: float | None = None
    for line in solver_log.splitlines():
        mtime = re.match(r"Time = ([0-9.eE+-]+)", line)
        if mtime:
            active_time = float(mtime.group(1))
        mref = re.search(r"Refined from (\d+) to (\d+) cells\.", line)
        munref = re.search(r"Unrefined from (\d+) to (\d+) cells\.", line)
        match = mref or munref
        if match:
            refine_events.append(
                {
                    "time_s": active_time,
                    "operation": "refine" if mref else "unrefine",
                    "cells_before": int(match.group(1)),
                    "cells_after": int(match.group(2)),
                    "delta_cells": int(match.group(2)) - int(match.group(1)),
                }
            )

    timeseries: list[dict[str, Any]] = []
    time_dirs = numeric_time_dirs(case)
    with tempfile.TemporaryDirectory(prefix="restas-amr-analysis-") as temporary:
        reader_case = Path(temporary)
        for source in [case / "constant", case / "system", *time_dirs]:
            if source.exists():
                (reader_case / source.name).symlink_to(source, target_is_directory=True)
        marker = reader_case / "probe.foam"
        marker.touch()
        reader = pv.OpenFOAMReader(str(marker))
        reader.enable_cell_array("alpha.water")
        try:
            reader.enable_cell_array("cellLevel")
        except (ValueError, KeyError):
            pass
        available = [float(t) for t in reader.time_values]
        for saved in time_dirs:
            requested = float(saved.name)
            if not any(math.isclose(t, requested, abs_tol=1e-9) for t in available):
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
            water_volume = float(alpha @ volumes)
            if "cellLevel" in mesh.cell_data:
                level_values = np.asarray(mesh.cell_data["cellLevel"], dtype=float)
                level_method = "OpenFOAM dynamicRefineFvMesh cellLevel field"
                level_hist = numeric_histogram(level_values)
            elif inputs["variant"] == "static_localized":
                lo = np.asarray(REFINE_BOX[0])
                hi = np.asarray(REFINE_BOX[1])
                mask = np.all((centers >= lo) & (centers <= hi), axis=1)
                level_hist = {"0": int((~mask).sum()), "1": int(mask.sum())}
                level_method = (
                    "nominal fixed-box level; structured transition cell volumes also reported"
                )
            else:
                level_hist = {"0": int(mesh.n_cells)}
                level_method = "unrefined fixed mesh"
            base_volumes = base_expected_volume(centers)
            ratio = volumes / base_volumes
            ratio_classes: dict[str, int] = {}
            for nominal in (1.0, 0.5, 0.25, 0.125, 0.0625):
                label = f"{nominal:g}x base cell volume"
                ratio_classes[label] = int(
                    np.count_nonzero(np.isclose(ratio, nominal, rtol=0.08, atol=1e-5))
                )
            dilute = alpha >= 0.001
            core = alpha >= 0.9

            def bounds(mask: np.ndarray) -> dict[str, Any] | None:
                if not np.any(mask):
                    return None
                xyz = centers[mask]
                return {
                    "x_m": [float(xyz[:, 0].min()), float(xyz[:, 0].max())],
                    "y_m": [float(xyz[:, 1].min()), float(xyz[:, 1].max())],
                    "z_m": [float(xyz[:, 2].min()), float(xyz[:, 2].max())],
                    "penetration_down_from_slot_plane_m": float(4.0 - xyz[:, 2].min()),
                    "thresholded_cell_count": int(mask.sum()),
                }

            timeseries.append(
                {
                    "time_s": requested,
                    "cell_count": int(mesh.n_cells),
                    "cell_counts_by_level": level_hist,
                    "level_count_method": level_method,
                    "cell_volume_ratio_classes": ratio_classes,
                    "water_inventory_m3": water_volume,
                    "alpha_ge_0p001_envelope": bounds(dilute),
                    "alpha_ge_0p9_core": bounds(core),
                }
            )
    if not timeseries:
        raise RuntimeError("No reconstructed OpenFOAM times could be read for this probe")

    last_clock = step_clock[-1] if step_clock else None
    # Every fixed physical step emits one ExecutionTime/ClockTime row. Integer
    # ClockTime is too coarse to support a meaningful median per-step value.
    nsteps = len(step_clock)
    report_path = run_dir / "probe-report.json"
    report = json.loads(report_path.read_text())
    report["mesh"].update(
        {
            "initial_cells": timeseries[0]["cell_count"],
            "final_cells": timeseries[-1]["cell_count"],
            "cell_counts_by_level_by_written_time": [
                {
                    "time_s": row["time_s"],
                    "cell_count": row["cell_count"],
                    "levels": row["cell_counts_by_level"],
                    "method": row["level_count_method"],
                }
                for row in timeseries
            ],
            "cell_volume_ratio_classes_by_written_time": [
                {"time_s": row["time_s"], "classes": row["cell_volume_ratio_classes"]}
                for row in timeseries
            ],
            "check_mesh_passed": "Mesh OK." in log,
        }
    )
    report["time"].update(
        {
            "solver_steps": nsteps,
            "solver_time_rows": nsteps,
            "solver_wall_time_s_from_OpenFOAM_ClockTime": last_clock,
            "solver_wall_time_per_step_s": last_clock / nsteps if last_clock and nsteps else None,
            "mean_step_clock_s": last_clock / nsteps if last_clock and nsteps else None,
            "median_step_clock_s": None,
            "per_step_timing_note": "Mean is solver ClockTime divided by ExecutionTime row count; OpenFOAM ClockTime is logged to whole seconds, so a median step wall time is not resolved.",
        }
    )
    report["refinement_overhead"] = {
        "mesh_change_events": len(refine_events),
        "events": refine_events,
        "solver_wall_time_includes_mesh_update": True,
        "separate_mesh_update_seconds": None,
        "measurement_limit": "Stock interIsoFoam logs total time-step clock time but does not isolate dynamicRefineFvMesh.update(); event counts and total compared wall time are reported as observable overhead evidence.",
    }
    report["plume"] = {
        "shape_time_series": timeseries,
        "interpretation": "cell-centered alpha.water thresholds from reconstructed VOF fields; exploratory nearfield morphology only, not validated breakup or ground delivery",
    }
    report["resources"]["output_bytes_before_render"] = sum(
        p.stat().st_size for p in run_dir.rglob("*") if p.is_file()
    )
    report["manifest"] = {
        "image_id": manifest.get("solver_image_id"),
        "input_sha256": manifest.get("inputs_sha256"),
        "case_input_sha256": manifest.get("case_input_sha256"),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (run_dir / "amr-timeseries.json").write_text(
        json.dumps(timeseries, indent=2, sort_keys=True) + "\n"
    )
    (run_dir / "refinement-events.json").write_text(
        json.dumps(refine_events, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "run_id": run_dir.name,
                "times": len(timeseries),
                "cell_counts": [row["cell_count"] for row in timeseries],
                "level_histograms": [row["cell_counts_by_level"] for row in timeseries],
                "final_water_m3": timeseries[-1]["water_inventory_m3"],
                "solver_wall_s": last_clock,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
