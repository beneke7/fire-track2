#!/usr/bin/env python3
"""Native-cell Calbrix cloud diagnostics; no smoothing or formal paper scoring."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from aerial_drop.structure_counts import label_liquid_structures, structure_statistics


def flux_histories(case: Path, patches: list[str]) -> dict[str, list[tuple[float, float]]]:
    """A restart branch replaces prior samples beyond its own start time."""
    histories = {}
    for patch in patches:
        branches = sorted(
            (float(path.parent.name), path)
            for path in (case / "postProcessing" / f"{patch}Flux").glob("*/surfaceFieldValue.dat")
        )
        if len({start for start, _ in branches}) != len(branches):
            raise ValueError("ambiguous restart branch")
        samples = {0.0: 0.0}  # This case's explicitly zero source velocity at t=0.
        for index, (start, path) in enumerate(branches):
            end = branches[index + 1][0] if index + 1 < len(branches) else float("inf")
            for line in path.read_text().splitlines():
                fields = line.split()
                if not fields or fields[0].startswith("#"):
                    continue
                t, phase_flux = float(fields[0]), float(fields[2])
                if start <= t <= end:
                    samples[t] = phase_flux
        histories[patch] = sorted(samples.items())
    return histories


def flux_integral(rows: list[tuple[float, float]], end_s: float) -> float:
    samples = np.asarray(rows, dtype=float)
    if len(samples) < 2 or end_s > samples[-1, 0] + 1e-6:
        raise ValueError("flux samples do not cover requested time")
    inside = samples[samples[:, 0] < end_s]
    final = [end_s, np.interp(end_s, samples[:, 0], samples[:, 1])]
    samples = np.vstack([inside, final])
    return float(np.trapezoid(samples[:, 1], samples[:, 0]))


def cell_widths(centers: np.ndarray, inputs: dict) -> np.ndarray:
    result = np.empty_like(centers, dtype=float)
    for axis_index, axis in enumerate("xyz"):
        breaks = np.asarray(inputs["mesh_breaks_m"][axis], dtype=float)
        widths = np.asarray(inputs["mesh_widths_by_segment_m"][axis], dtype=float)
        if len(breaks) != len(widths) + 1:
            raise ValueError(f"invalid mesh segments for {axis}")
        indices = np.searchsorted(breaks, centers[:, axis_index], side="right") - 1
        if np.any(indices < 0) or np.any(indices >= len(widths)):
            raise ValueError("cell center outside declared mesh")
        result[:, axis_index] = widths[indices]
    return result


def structured_face_pairs(
    centers: np.ndarray, widths: np.ndarray, *, geometry_atol_m: float = 2e-9
) -> tuple[np.ndarray, np.ndarray]:
    """Recover face adjacency for a complete conforming Cartesian box only.

    IDs remain in the reader's cell order. Nanometre coordinate grouping only
    removes blockMesh roundoff; incomplete, duplicate, or nonconforming grids
    are rejected rather than silently assigned Cartesian connectivity.
    """
    if centers.ndim != 2 or centers.shape[1] != 3 or widths.shape != centers.shape:
        raise ValueError("centers and widths must have matching (n, 3) shapes")
    if not np.all(np.isfinite(centers)) or not np.all(np.isfinite(widths)):
        raise ValueError("nonfinite Cartesian geometry")
    if not np.isfinite(geometry_atol_m) or geometry_atol_m <= 0:
        raise ValueError("positive finite geometry tolerance required")
    coordinates = []
    indices = []
    for axis in range(3):
        levels, inverse = np.unique(np.round(centers[:, axis], 9), return_inverse=True)
        coordinates.append(levels)
        indices.append(inverse)
    shape = tuple(len(levels) for levels in coordinates)
    if np.prod(shape) != len(centers):
        raise ValueError("requires a complete Cartesian box")
    flat = np.ravel_multi_index(tuple(indices), shape)
    if len(np.unique(flat)) != len(centers):
        raise ValueError("duplicate Cartesian cell center")
    ids = np.empty(shape, dtype=np.int32)
    ids.ravel()[flat] = np.arange(len(centers), dtype=np.int32)
    owners, neighbours = [], []
    for axis in range(3):
        lower = [slice(None)] * 3
        upper = [slice(None)] * 3
        lower[axis], upper[axis] = slice(None, -1), slice(1, None)
        left, right = ids[tuple(lower)].ravel(), ids[tuple(upper)].ravel()
        distance = centers[right, axis] - centers[left, axis]
        expected = 0.5 * (widths[right, axis] + widths[left, axis])
        if np.any(widths <= 0) or not np.allclose(distance, expected, rtol=0, atol=geometry_atol_m):
            raise ValueError("nonconforming Cartesian cell widths")
        owners.append(left)
        neighbours.append(right)
    return np.concatenate(owners), np.concatenate(neighbours)


def cloud_profiles(
    alpha: np.ndarray,
    centers: np.ndarray,
    widths: np.ndarray,
    *,
    source_origin_m: np.ndarray,
    threshold: float,
) -> dict:
    """Use full qualifying cells; bounds carry a cell-resolution uncertainty."""
    alpha = np.asarray(alpha, dtype=float)
    if centers.shape != (len(alpha), 3) or widths.shape != centers.shape:
        raise ValueError("alpha, centers and widths must describe the same cells")
    if not 0 < threshold <= 1 or np.any(widths <= 0):
        raise ValueError("positive widths and threshold in (0,1] required")
    if not all(np.all(np.isfinite(value)) for value in (alpha, centers, widths)):
        raise ValueError("nonfinite computed fields")
    selected = alpha >= threshold
    volumes = np.prod(widths, axis=1)
    c, w = centers[selected], widths[selected]
    origin = np.asarray(source_origin_m, dtype=float)
    penetration = []
    expansion = []
    # Structured native-cell slabs: no arbitrary resampling or render smoothing.
    # Identical blockMesh slabs can differ by floating-point roundoff across blocks.
    # Nanometre grouping removes that roundoff; it is far below the mesh resolution.
    x_slabs = np.round(c[:, 0], 9)
    z_slabs = np.round(c[:, 2], 9)
    for coordinate in np.unique(x_slabs):
        row = x_slabs == coordinate
        penetration.append(
            {
                "streamwise_m": float(coordinate - origin[0]),
                "streamwise_cell_width_m": float(w[row, 0].max()),
                "downward_front_m": float(origin[2] - np.min(c[row, 2] - w[row, 2] / 2)),
                "vertical_cell_width_m": float(w[row, 2].max()),
            }
        )
    for coordinate in np.unique(z_slabs):
        row = z_slabs == coordinate
        lo = np.min(c[row, 1] - w[row, 1] / 2)
        hi = np.max(c[row, 1] + w[row, 1] / 2)
        expansion.append(
            {
                "downward_m": float(origin[2] - coordinate),
                "vertical_cell_width_m": float(w[row, 2].max()),
                "total_cross_track_width_m": float(hi - lo),
                "cross_track_lower_m": float(lo - origin[1]),
                "cross_track_upper_m": float(hi - origin[1]),
                "transverse_cell_width_m": float(w[row, 1].max()),
            }
        )
    expansion.sort(key=lambda row: row["downward_m"])
    return {
        "alpha_threshold": threshold,
        "selected_cells": int(selected.sum()),
        "selected_water_volume_m3": float(np.sum(alpha[selected] * volumes[selected])),
        "total_water_volume_m3": float(np.sum(alpha * volumes)),
        "penetration": penetration,
        "expansion": expansion,
    }


def write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(run_dir: Path, output_dir: Path) -> dict:
    import pyvista as pv

    output_dir.mkdir(parents=True, exist_ok=False)
    case = run_dir / "case"
    inputs = json.loads((case / "case-inputs.json").read_text())
    marker = case / "nearfield.foam"
    marker.touch(exist_ok=True)
    reader = pv.OpenFOAMReader(str(marker))
    reader.disable_all_cell_arrays()
    reader.enable_cell_array("alpha.water")
    reader.enable_cell_array("U")
    report = {
        "classification": "Exploratory unsmoothed numerical diagnostics; not paper acceptance",
        "case_id": inputs.get("case_id"),
        "aircraft": inputs.get("aircraft", "CL415"),
        "coordinate_mapping": "paper y = simulation x - origin_x; downward z = origin_z - simulation z; transverse x = simulation y - origin_y",
        "source_origin_m": inputs["source_origin_m"],
        "paper_origin_registration": inputs.get("coordinate_frame", {}).get(
            "streamwise_origin_note", "assumed origin; paper-to-case registration is unverified"
        ),
        "operator": "Full-cell threshold envelopes on native structured slabs; dimensions uncertain at cell scale",
        "native_coordinate_grouping_m": 1e-9,
        "structure_operator": "Face-connected native Cartesian cells, minimum one cell; VTK shared-point count as sensitivity; unpublished paper Matlab equivalence unverified",
        "normalization": "Dimensional only: paper exit area aggregation for Lc is unresolved",
        "times": [],
    }
    histories = flux_histories(case, inputs["source_patches"] + inputs["open_patches"])
    for time_s in reader.time_values:
        reader.set_active_time_value(time_s)
        grid = reader.read()["internalMesh"]
        alpha = np.asarray(grid.cell_data["alpha.water"], dtype=float)
        centers = grid.cell_centers().points
        widths = cell_widths(centers, inputs)
        # VTK defaults to float32 mesh points. Bound the geometry check by
        # four ULPs at the domain scale while retaining native field order.
        geometry_atol_m = max(
            2e-9, 4 * np.finfo(grid.points.dtype).eps * max(1, np.abs(grid.points).max())
        )
        owner, neighbour = structured_face_pairs(centers, widths, geometry_atol_m=geometry_atol_m)
        row = {"time_s": float(time_s), "cells": grid.n_cells, "thresholds": []}
        row["face_geometry_tolerance_m"] = float(geometry_atol_m)
        mass_kg = float(np.sum(alpha * np.prod(widths, axis=1)) * 1000)
        row["airborne_water_mass_kg"] = mass_kg
        try:
            # Outward normals: source integrals negative, outlet net flux signed.
            net_escaped_kg = (
                sum(flux_integral(samples, time_s) for samples in histories.values()) * 1000
            )
            row["sampled_mass_residual_kg"] = mass_kg + net_escaped_kg
            row["sampled_injected_water_kg"] = (
                -sum(flux_integral(histories[name], time_s) for name in inputs["source_patches"])
                * 1000
            )
        except ValueError:
            row["sampled_mass_residual_kg"] = None
        row["ledger_note"] = (
            "Signed trapezoidal samples of alphaPhi_, initial all-air mass zero; diagnostic rather than exact solver-time quadrature"
        )
        for threshold in (0.001, 0.9):
            profiles = cloud_profiles(
                alpha,
                centers,
                widths,
                source_origin_m=np.asarray(inputs["source_origin_m"]),
                threshold=threshold,
            )
            labels = label_liquid_structures(alpha, owner, neighbour, threshold)
            statistics = structure_statistics(
                alpha, np.prod(widths, axis=1), labels, np.asarray(grid.cell_data["U"])
            )
            profiles["connected_cell_regions"] = len(statistics)
            profiles["single_cell_regions"] = sum(r["cell_count"] == 1 for r in statistics)
            rows = []
            for structure in statistics:
                velocity = structure.pop("mass_weighted_velocity_m_s")
                rows.append(
                    {
                        **structure,
                        **{
                            f"mass_weighted_U{axis}_m_s": v
                            for axis, v in zip("xyz", velocity, strict=True)
                        },
                    }
                )
            write_rows(output_dir / f"t{float(time_s):g}-alpha{threshold:g}-structures.csv", rows)
            threshold_grid = grid.threshold(
                [threshold, max(1.000001, float(alpha.max()))],
                scalars="alpha.water",
                preference="cell",
                all_scalars=True,
            )
            profiles["point_connected_cell_regions"] = 0
            if threshold_grid.n_cells:
                connected = threshold_grid.connectivity(extraction_mode="all", label_regions=True)
                profiles["point_connected_cell_regions"] = int(
                    len(np.unique(connected.cell_data["RegionId"]))
                )
            profiles["structure_statistics_note"] = (
                "Face adjacency, all sizes retained; alpha-volume sphere-equivalent diameter and liquid-mass-weighted velocity; shared-point count is a sensitivity. Paper detection/diameter/bar weighting equivalence unverified."
            )
            tag = f"t{float(time_s):g}-alpha{threshold:g}"
            write_rows(output_dir / f"{tag}-penetration.csv", profiles.pop("penetration"))
            write_rows(output_dir / f"{tag}-expansion.csv", profiles.pop("expansion"))
            row["thresholds"].append(profiles)
        report["times"].append(row)
    report["boundary_flux_history"] = histories
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = analyze(args.run_dir.resolve(), args.output_dir.resolve())
    print(json.dumps({"snapshots": len(report["times"]), "output": str(args.output_dir)}))


if __name__ == "__main__":
    main()
