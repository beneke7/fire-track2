#!/usr/bin/env python3
"""Classify source-attached and detached Dash-8 VOF structures in native cells.

This is an exploratory geometric classifier, not an implementation of the
unpublished MATLAB detector used by Calbrix et al. It labels face-connected
native Cartesian cells, then marks a component source-attached only when it
contains a threshold-selected cell whose top face belongs to the declared
source rectangle.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from aerial_drop.structure_counts import label_liquid_structures, structure_statistics

# Direct file execution also needs the repository's scripts namespace package.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_cl415_case import cell_widths  # noqa: E402
from scripts.analyze_cl415_case import (  # noqa: E402
    structured_face_pairs as _shared_structured_face_pairs,
)

_OTHER_BIN_NAMES = ("below_0p04_m", "above_10_m")
ALPHA_BOUND_TOLERANCE = 1e-12


def scale_aware_geometry_tolerance_m(
    centers_m: ArrayLike, *, coordinate_dtype: np.dtype[Any] | type | None = None
) -> float:
    """Use four coordinate ULPs at domain scale, with a 2 nm absolute floor."""
    centers = np.asarray(centers_m)
    if centers.ndim != 2 or centers.shape[1] != 3 or not np.all(np.isfinite(centers)):
        raise ValueError("centers_m must be a finite (n, 3) array")
    dtype = np.dtype(coordinate_dtype if coordinate_dtype is not None else centers.dtype)
    if not np.issubdtype(dtype, np.floating):
        raise ValueError("coordinate_dtype must be floating point")
    scale = max(1.0, float(np.max(np.abs(centers))) if centers.size else 1.0)
    return max(2e-9, 4.0 * float(np.finfo(dtype).eps) * scale)


def _expected_axis_cell_count(
    lower_m: float,
    upper_m: float,
    *,
    axis: str,
    inputs: dict[str, Any],
    tolerance_m: float,
) -> int:
    """Count mesh cells spanning an aligned source interval from frozen inputs."""
    breaks = np.asarray(inputs["mesh_breaks_m"][axis], dtype=float)
    counts_by_axis = inputs.get("mesh_cells_per_segment")
    if not isinstance(counts_by_axis, dict) or axis not in counts_by_axis:
        raise ValueError("case inputs lack per-segment Cartesian cell counts")
    counts = np.asarray(counts_by_axis[axis], dtype=np.int64)
    if len(breaks) != len(counts) + 1 or np.any(counts <= 0):
        raise ValueError(f"invalid segment cell counts for {axis}")
    selected_count = 0
    for start, end, count in zip(breaks[:-1], breaks[1:], counts, strict=True):
        overlaps = start < upper_m - tolerance_m and end > lower_m + tolerance_m
        inside = start >= lower_m - tolerance_m and end <= upper_m + tolerance_m
        if overlaps and not inside:
            raise ValueError(f"source {axis} bounds cut through a declared mesh segment")
        if inside:
            selected_count += int(count)
    if selected_count == 0:
        raise ValueError(f"source interval has no declared {axis} cells")
    return selected_count


def source_face_inventory(
    centers_m: ArrayLike,
    widths_m: ArrayLike,
    source_geometry: dict[str, Any],
    source_patch_areas_m2: dict[str, float],
    *,
    source_patch_face_counts: dict[str, int] | None = None,
    mesh_inputs: dict[str, Any] | None = None,
    geometry_tolerance_m: float | None = None,
) -> tuple[NDArray[np.bool_], dict[str, Any]]:
    """Return native cells with a top face in the verified source inventory.

    Source bounds must align with Cartesian cell edges. Face count is compared
    with ``source_patch_face_counts`` when available, or independently derived
    from the frozen segment cell counts for older prepared cases. Face areas
    must match both source-geometry and patch-area metadata.
    """
    centers_input = np.asarray(centers_m)
    centers = np.asarray(centers_input, dtype=float)
    widths = np.asarray(widths_m, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 3 or widths.shape != centers.shape:
        raise ValueError("centers_m and widths_m must have matching (n, 3) shapes")
    if not np.all(np.isfinite(centers)) or not np.all(np.isfinite(widths)) or np.any(widths <= 0):
        raise ValueError("cell centers and widths must be finite; widths must be positive")
    if not isinstance(source_geometry, dict) or not isinstance(
        source_geometry.get("sources"), list
    ):
        raise ValueError("source_geometry must contain a sources list")
    if not source_geometry["sources"]:
        raise ValueError("source_geometry contains no source rectangles")
    if not isinstance(source_patch_areas_m2, dict):
        raise ValueError("source_patch_areas_m2 must be a mapping")
    tolerance = (
        scale_aware_geometry_tolerance_m(centers_input)
        if geometry_tolerance_m is None
        else float(geometry_tolerance_m)
    )
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("geometry_tolerance_m must be finite and positive")

    source_mask = np.zeros(len(centers), dtype=bool)
    source_records: list[dict[str, Any]] = []
    common_plane = source_geometry.get("source_plane_z_m")
    for source in source_geometry["sources"]:
        if not isinstance(source, dict):
            raise ValueError("each source geometry entry must be an object")
        name = source.get("name")
        bounds = source.get("bounds_m")
        if not isinstance(name, str) or not name or not isinstance(bounds, dict):
            raise ValueError("each source requires a name and x/y bounds")
        if name not in source_patch_areas_m2:
            raise ValueError(f"source patch area metadata is missing for {name}")
        if "x" not in bounds or "y" not in bounds:
            raise ValueError(f"source {name} requires x and y rectangle bounds")
        try:
            x0, x1 = (float(value) for value in bounds["x"])
            y0, y1 = (float(value) for value in bounds["y"])
            patch_area = float(source_patch_areas_m2[name])
            geometry_area = float(source["area_m2"])
            source_plane = float(source.get("plane_z_m", common_plane))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"source {name} has malformed geometry/area metadata") from exc
        values = (x0, x1, y0, y1, patch_area, geometry_area, source_plane)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"source {name} geometry and area values must be finite")
        if x1 <= x0 or y1 <= y0 or patch_area <= 0 or geometry_area <= 0:
            raise ValueError(f"source {name} must have positive rectangular dimensions and area")
        expected_area = (x1 - x0) * (y1 - y0)
        area_atol = max(1e-12, expected_area * 1e-10)
        if not math.isclose(geometry_area, expected_area, rel_tol=0.0, abs_tol=area_atol):
            raise ValueError(f"source {name} geometry area disagrees with its rectangle")
        if not math.isclose(patch_area, expected_area, rel_tol=0.0, abs_tol=area_atol):
            raise ValueError(f"source {name} patch area disagrees with its rectangle")

        cell_lower = centers - widths / 2.0
        cell_upper = centers + widths / 2.0
        top_face = np.isclose(cell_upper[:, 2], source_plane, rtol=0.0, atol=tolerance)
        x_overlap = (cell_lower[:, 0] < x1 - tolerance) & (cell_upper[:, 0] > x0 + tolerance)
        y_overlap = (cell_lower[:, 1] < y1 - tolerance) & (cell_upper[:, 1] > y0 + tolerance)
        candidate = top_face & x_overlap & y_overlap
        x_inside = (cell_lower[:, 0] >= x0 - tolerance) & (cell_upper[:, 0] <= x1 + tolerance)
        y_inside = (cell_lower[:, 1] >= y0 - tolerance) & (cell_upper[:, 1] <= y1 + tolerance)
        if np.any(candidate & ~(x_inside & y_inside)):
            raise ValueError(f"source {name} edge cuts through a native Cartesian cell face")
        faces = candidate & x_inside & y_inside
        face_count = int(np.count_nonzero(faces))
        face_area = float(np.sum(widths[faces, 0] * widths[faces, 1], dtype=np.float64))
        if face_count == 0:
            raise ValueError(
                f"source {name} has no native top-face cells in its declared rectangle"
            )

        expected_count = None
        count_reference = "source_patch_face_counts"
        if source_patch_face_counts is not None and name in source_patch_face_counts:
            expected_count = int(source_patch_face_counts[name])
        elif mesh_inputs is not None:
            count_reference = "mesh_cells_per_segment"
            nx = _expected_axis_cell_count(
                x0, x1, axis="x", inputs=mesh_inputs, tolerance_m=tolerance
            )
            ny = _expected_axis_cell_count(
                y0, y1, axis="y", inputs=mesh_inputs, tolerance_m=tolerance
            )
            expected_count = nx * ny
        else:
            raise ValueError(f"source {name} lacks face-count or segment-count metadata")
        if expected_count <= 0 or face_count != expected_count:
            raise ValueError(
                f"source {name} face inventory count {face_count} disagrees with metadata "
                f"({expected_count})"
            )
        if not math.isclose(face_area, patch_area, rel_tol=0.0, abs_tol=area_atol):
            raise ValueError(
                f"source {name} native face area {face_area:g} disagrees with metadata "
                f"({patch_area:g} m^2)"
            )
        source_mask |= faces
        source_records.append(
            {
                "name": name,
                "source_plane_z_m": source_plane,
                "face_count_native": face_count,
                "face_count_metadata": expected_count,
                "face_count_reference": count_reference,
                "face_area_native_m2": face_area,
                "face_area_metadata_m2": patch_area,
                "geometry_verified": True,
            }
        )

    return source_mask, {
        "definition": (
            "source cells are native Cartesian cells with a top face coincident with a declared "
            "source rectangle at its source-plane z; positive-area face overlap is required"
        ),
        "geometry_tolerance_m": tolerance,
        "native_source_cell_count_union": int(source_mask.sum()),
        "sources": source_records,
    }


def diameter_bin(diameter_m: float) -> str:
    """Assign a sphere-equivalent diameter to fixed, nonoverlapping reporting bins."""
    diameter = float(diameter_m)
    if not math.isfinite(diameter) or diameter < 0:
        raise ValueError("diameter_m must be finite and nonnegative")
    if diameter < 0.04:
        return _OTHER_BIN_NAMES[0]
    if diameter < 0.1:
        return "0p04_to_0p1_m"
    if diameter < 1.0:
        return "0p1_to_1_m"
    if diameter <= 10.0:
        return "1_to_10_m"
    return _OTHER_BIN_NAMES[1]


def _component_velocity_summary(components: list[dict[str, Any]]) -> dict[str, Any]:
    if not components:
        return {
            "component_count": 0,
            "total_liquid_mass_kg": 0.0,
            "number_mean_component_velocity_m_s": None,
            "number_mean_component_speed_m_s": None,
            "mass_mean_component_velocity_m_s": None,
            "mass_mean_component_speed_m_s": None,
        }
    vectors = np.asarray([row["mass_weighted_velocity_m_s"] for row in components], dtype=float)
    speeds = np.linalg.norm(vectors, axis=1)
    masses = np.asarray([row["mass_kg"] for row in components], dtype=float)
    mass_total = float(masses.sum())
    return {
        "component_count": len(components),
        "total_liquid_mass_kg": mass_total,
        "number_mean_component_velocity_m_s": np.mean(vectors, axis=0).tolist(),
        "number_mean_component_speed_m_s": float(np.mean(speeds)),
        "mass_mean_component_velocity_m_s": np.average(vectors, axis=0, weights=masses).tolist(),
        "mass_mean_component_speed_m_s": float(np.average(speeds, weights=masses)),
    }


def classify_source_attachment(
    alpha_water: ArrayLike,
    cell_volumes_m3: ArrayLike,
    velocity_m_s: ArrayLike,
    labels: ArrayLike,
    source_cell_mask: ArrayLike,
    threshold: float,
    *,
    density_kg_m3: float = 1000.0,
) -> dict[str, Any]:
    """Classify each labeled component by actual native source-face ownership.

    A component is attached if at least one threshold-selected cell in that
    component owns a verified source top face. No geometric-size or largest-
    component heuristic is used. Group number means give each component equal
    weight; mass means weight each component by its thresholded liquid mass.
    """
    alpha = np.asarray(alpha_water, dtype=float)
    volumes = np.asarray(cell_volumes_m3, dtype=float)
    velocity = np.asarray(velocity_m_s, dtype=float)
    component_labels = np.asarray(labels)
    source_mask = np.asarray(source_cell_mask, dtype=bool)
    if alpha.ndim != 1:
        raise ValueError("alpha_water must be one-dimensional")
    if volumes.shape != alpha.shape or source_mask.shape != alpha.shape:
        raise ValueError("cell volumes and source mask must match alpha_water")
    if velocity.shape != (len(alpha), 3):
        raise ValueError("velocity_m_s must have shape (number of cells, 3)")
    if component_labels.shape != alpha.shape or not np.issubdtype(
        component_labels.dtype, np.integer
    ):
        raise ValueError("labels must be an integer array matching alpha_water")
    if (
        not np.all(np.isfinite(alpha))
        or np.any(alpha < -ALPHA_BOUND_TOLERANCE)
        or np.any(alpha > 1.0 + ALPHA_BOUND_TOLERANCE)
        or not np.all(np.isfinite(volumes))
        or np.any(volumes <= 0)
        or not np.all(np.isfinite(velocity))
    ):
        raise ValueError(
            "alpha, velocities, and positive cell volumes must be finite and valid; "
            f"alpha must lie within [0, 1] up to {ALPHA_BOUND_TOLERANCE:g} roundoff"
        )
    if np.any(component_labels < -1):
        raise ValueError("labels must use -1 for unselected cells and nonnegative component IDs")
    threshold_value = float(threshold)
    density = float(density_kg_m3)
    if not math.isfinite(threshold_value) or not 0 < threshold_value <= 1:
        raise ValueError("threshold must be finite and in (0, 1]")
    if not math.isfinite(density) or density <= 0:
        raise ValueError("density_kg_m3 must be finite and positive")
    selected = alpha >= threshold_value
    labeled = component_labels >= 0
    if np.any(selected & ~labeled) or np.any(labeled & ~selected):
        raise ValueError("labels must contain exactly all cells selected by the threshold")

    cell_mass = alpha * volumes * density
    component_rows = structure_statistics(
        alpha,
        volumes,
        component_labels,
        velocity,
        density_kg_m3=density,
    )
    attached_labels = set(
        int(value) for value in np.unique(component_labels[source_mask & selected])
    )
    for row in component_rows:
        component_id = int(row["label"])
        cell_ids = component_labels == component_id
        component_speeds = np.linalg.norm(velocity[cell_ids], axis=1)
        row["attachment"] = "source-attached" if component_id in attached_labels else "detached"
        row["source_face_cell_count"] = int(np.count_nonzero(source_mask & cell_ids))
        row["number_mean_cell_velocity_m_s"] = np.mean(velocity[cell_ids], axis=0).tolist()
        row["number_mean_cell_speed_m_s"] = float(np.mean(component_speeds))
        row["mass_mean_cell_speed_m_s"] = float(
            np.average(component_speeds, weights=cell_mass[cell_ids])
        )
        row["diameter_bin"] = diameter_bin(float(row["equivalent_diameter_m"]))

    groups: dict[str, Any] = {}
    for attachment in ("source-attached", "detached"):
        group = [row for row in component_rows if row["attachment"] == attachment]
        group_bins = {}
        for bin_name in (
            *_OTHER_BIN_NAMES[:1],
            "0p04_to_0p1_m",
            "0p1_to_1_m",
            "1_to_10_m",
            *_OTHER_BIN_NAMES[1:],
        ):
            group_bins[bin_name] = _component_velocity_summary(
                [row for row in group if row["diameter_bin"] == bin_name]
            )
        groups[attachment] = {
            **_component_velocity_summary(group),
            "diameter_bins": group_bins,
        }

    group_component_count = sum(groups[name]["component_count"] for name in groups)
    group_liquid_mass = sum(groups[name]["total_liquid_mass_kg"] for name in groups)
    total_component_mass = float(sum(row["mass_kg"] for row in component_rows))
    mass_atol = max(1e-12, abs(float(np.sum(cell_mass[selected], dtype=np.float64))) * 1e-12)
    return {
        "alpha_threshold": threshold_value,
        "selected_native_cell_count": int(np.count_nonzero(selected)),
        "selected_liquid_mass_kg": float(np.sum(cell_mass[selected], dtype=np.float64)),
        "selected_source_face_cell_count": int(np.count_nonzero(source_mask & selected)),
        "no_selected_source_cell": not bool(np.any(source_mask & selected)),
        "component_count": len(component_rows),
        "attached_component_count": len(attached_labels),
        "detached_component_count": len(component_rows) - len(attached_labels),
        "component_cell_counts_reconcile": sum(row["cell_count"] for row in component_rows)
        == int(np.count_nonzero(selected)),
        "component_group_counts_and_masses_reconcile": (
            group_component_count == len(component_rows)
            and math.isclose(
                group_liquid_mass, total_component_mass, rel_tol=0.0, abs_tol=mass_atol
            )
            and math.isclose(
                total_component_mass,
                float(np.sum(cell_mass[selected], dtype=np.float64)),
                rel_tol=0.0,
                abs_tol=mass_atol,
            )
        ),
        "alpha_field_bounds": {
            "native_minimum": float(alpha.min()) if len(alpha) else None,
            "native_maximum": float(alpha.max()) if len(alpha) else None,
            "roundoff_tolerance": ALPHA_BOUND_TOLERANCE,
            "native_values_modified": False,
        },
        "velocity_averaging_definition": (
            "Within each component, mass_mean velocity weights native-cell U by alpha*cell_volume; "
            "number_mean_cell velocity is an arithmetic native-cell mean. Across components and "
            "diameter bins, number_mean gives each component equal weight and mass_mean weights "
            "components by liquid mass. These are descriptive VOF statistics, not droplet tracking."
        ),
        "diameter_definition": "sphere-equivalent diameter from thresholded alpha.water volume",
        "diameter_bins_m": {
            "0p04_to_0p1_m": {"lower_inclusive": 0.04, "upper_exclusive": 0.1},
            "0p1_to_1_m": {"lower_inclusive": 0.1, "upper_exclusive": 1.0},
            "1_to_10_m": {"lower_inclusive": 1.0, "upper_inclusive": 10.0},
            "below_0p04_m": {"upper_exclusive": 0.04},
            "above_10_m": {"lower_exclusive": 10.0},
        },
        "groups": groups,
        "components": component_rows,
    }


def _read_native_snapshot(
    case_directory: Path, time_s: float, reader_view: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read decomposed OpenFOAM cell fields through vtkPOpenFOAMReader."""
    import vtk
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkCommonDataModel import vtkDataSet
    from vtkmodules.vtkFiltersCore import vtkCellCenters
    from vtkmodules.vtkIOParallel import vtkPOpenFOAMReader

    case = Path(case_directory)
    inputs = json.loads((case / "case-inputs.json").read_text(encoding="utf-8"))
    if reader_view.exists():
        raise FileExistsError(f"refusing to replace existing reader view: {reader_view}")
    reader_view.mkdir()
    marker = reader_view / "case.foam"
    marker.touch()
    for child in case.iterdir():
        if child.name in {"constant", "system"} or child.name.startswith("processor"):
            if child.is_dir():
                (reader_view / child.name).symlink_to(child.resolve(), target_is_directory=True)

    reader = vtkPOpenFOAMReader()
    reader.SetFileName(str(marker))
    reader.SetCaseType(0)
    reader.SetUse64BitFloats(True)
    reader.DisableAllCellArrays()
    for field in ("alpha.water", "U"):
        reader.SetCellArrayStatus(field, 1)
    reader.UpdateInformation()
    time_values = reader.GetTimeValues()
    available_times = [
        float(time_values.GetValue(index)) for index in range(time_values.GetNumberOfTuples())
    ]
    selected_time = min(available_times, key=lambda value: abs(value - time_s))
    if not math.isclose(selected_time, time_s, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"requested time {time_s:g} s absent; available times: {available_times}")
    reader.SetTimeValue(selected_time)
    reader.Update()
    output = reader.GetOutput()

    centers_chunks = []
    alpha_chunks = []
    velocity_chunks = []
    array_precision: dict[str, set[str]] = {
        "mesh_points": set(),
        "cell_centers": set(),
        "alpha.water": set(),
        "U": set(),
    }
    iterator = output.NewIterator()
    iterator.SkipEmptyNodesOn()
    iterator.InitTraversal()
    while not iterator.IsDoneWithTraversal():
        block = vtkDataSet.SafeDownCast(iterator.GetCurrentDataObject())
        if block is not None and block.GetNumberOfCells() > 0:
            cell_data = block.GetCellData()
            alpha_array = cell_data.GetArray("alpha.water")
            velocity_array = cell_data.GetArray("U")
            if alpha_array is None or velocity_array is None:
                raise ValueError("native internalMesh lacks alpha.water or U cell arrays")
            centers_filter = vtkCellCenters()
            centers_filter.SetInputData(block)
            centers_filter.Update()
            center_points = centers_filter.GetOutput().GetPoints().GetData()
            center_chunk = vtk_to_numpy(center_points)
            alpha_chunk = vtk_to_numpy(alpha_array)
            velocity_chunk = vtk_to_numpy(velocity_array)
            if alpha_chunk.ndim != 1 or velocity_chunk.shape != (len(alpha_chunk), 3):
                raise ValueError("OpenFOAM reader returned malformed cell arrays")
            if len(center_chunk) != len(alpha_chunk):
                raise ValueError("native cell centers and fields have different lengths")
            centers_chunks.append(center_chunk)
            alpha_chunks.append(alpha_chunk)
            velocity_chunks.append(velocity_chunk)
            array_precision["mesh_points"].add(block.GetPoints().GetData().GetDataTypeAsString())
            array_precision["cell_centers"].add(center_points.GetDataTypeAsString())
            array_precision["alpha.water"].add(alpha_array.GetDataTypeAsString())
            array_precision["U"].add(velocity_array.GetDataTypeAsString())
        iterator.GoToNextItem()
    if not centers_chunks:
        raise ValueError("OpenFOAM reader returned no native volume cells")

    centers = np.concatenate(centers_chunks, axis=0)
    alpha = np.concatenate(alpha_chunks, axis=0)
    velocity = np.concatenate(velocity_chunks, axis=0)
    if len(alpha) != int(inputs["mesh_cells_expected"]):
        raise ValueError(
            f"reader returned {len(alpha)} native cells; metadata expects "
            f"{inputs['mesh_cells_expected']}"
        )
    snapshot = {
        "time_s": selected_time,
        "centers_m": centers,
        "alpha_water": alpha,
        "velocity_m_s": velocity,
        "array_precision": {key: sorted(value) for key, value in array_precision.items()},
    }
    reader_metadata = {
        "vtk_version": vtk.vtkVersion.GetVTKVersion(),
        "reader": "vtkPOpenFOAMReader",
        "case_type": "decomposed (SetCaseType(0))",
        "use_64_bit_floats_for_binary_input": True,
        "output_array_precision": snapshot["array_precision"],
        "actual_native_cell_count": int(len(alpha)),
        "snapshot_time_s": selected_time,
        "symlink_case_view": str(reader_view.resolve()),
        "source_case_fields_modified": False,
    }
    return snapshot, reader_metadata


def _native_field_hashes(case_directory: Path, time_name: str) -> dict[str, Any]:
    case = Path(case_directory)
    rows = []
    for processor_dir in sorted(case.glob("processor[0-9]*"), key=lambda path: int(path.name[9:])):
        for field in ("alpha.water", "U"):
            path = processor_dir / time_name / field
            if not path.is_file():
                raise FileNotFoundError(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append(
                {
                    "processor": processor_dir.name,
                    "field": field,
                    "relative_path": str(path.relative_to(case)),
                    "size_bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )
    if not rows or len(rows) % 2:
        raise ValueError("native alpha.water/U field inventory is incomplete")
    ranks = sorted({row["processor"] for row in rows})
    if len(ranks) != int(json.loads((case / "case-inputs.json").read_text())["ranks"]):
        raise ValueError("native field processor count disagrees with case metadata")
    return {"time_directory": time_name, "processor_count": len(ranks), "fields": rows}


def _resolve_case_directory(run_dir: Path) -> Path:
    """Resolve the existing runner-bundle layout's prepared case root."""
    case = (run_dir / "case").resolve()
    if not case.is_dir() or not (case / "case-inputs.json").is_file():
        raise ValueError(f"run directory lacks a prepared case: {run_dir}")
    return case


def _write_component_csv(path: Path, threshold_result: dict[str, Any], threshold: float) -> None:
    columns = (
        "alpha_threshold",
        "label",
        "attachment",
        "source_face_cell_count",
        "cell_count",
        "liquid_volume_m3",
        "mass_kg",
        "equivalent_diameter_m",
        "diameter_bin",
        "number_mean_cell_speed_m_s",
        "mass_mean_cell_speed_m_s",
        "mass_weighted_Ux_m_s",
        "mass_weighted_Uy_m_s",
        "mass_weighted_Uz_m_s",
        "number_mean_cell_Ux_m_s",
        "number_mean_cell_Uy_m_s",
        "number_mean_cell_Uz_m_s",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for component in threshold_result["components"]:
            mass_velocity = component["mass_weighted_velocity_m_s"]
            number_velocity = component["number_mean_cell_velocity_m_s"]
            writer.writerow(
                {
                    "alpha_threshold": threshold,
                    **{key: component[key] for key in columns if key in component},
                    "mass_weighted_Ux_m_s": mass_velocity[0],
                    "mass_weighted_Uy_m_s": mass_velocity[1],
                    "mass_weighted_Uz_m_s": mass_velocity[2],
                    "number_mean_cell_Ux_m_s": number_velocity[0],
                    "number_mean_cell_Uy_m_s": number_velocity[1],
                    "number_mean_cell_Uz_m_s": number_velocity[2],
                }
            )


def analyze(run_dir: Path, output_dir: Path, *, time_s: float = 1.0) -> dict[str, Any]:
    """Analyze one saved decomposed checkpoint without modifying the source case."""
    run_dir = Path(run_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists; preserving it: {output_dir}")
    case = _resolve_case_directory(run_dir)
    inputs = json.loads((case / "case-inputs.json").read_text(encoding="utf-8"))
    requested_time = float(time_s)
    if not math.isfinite(requested_time) or requested_time < 0:
        raise ValueError("time_s must be finite and nonnegative")
    time_name = f"{requested_time:.6f}"
    field_hashes = _native_field_hashes(case, time_name)
    output_dir.mkdir(parents=True, exist_ok=False)
    snapshot, reader_metadata = _read_native_snapshot(
        case, requested_time, output_dir / "reader-view"
    )
    centers = snapshot["centers_m"]
    alpha = np.asarray(snapshot["alpha_water"], dtype=float)
    velocity = np.asarray(snapshot["velocity_m_s"], dtype=float)
    widths = cell_widths(centers, inputs)
    mesh_point_type = reader_metadata["output_array_precision"]["mesh_points"]
    point_dtype = np.float32 if mesh_point_type == ["float"] else np.float64
    geometry_tolerance = scale_aware_geometry_tolerance_m(centers, coordinate_dtype=point_dtype)
    geometry = inputs.get("source_geometry")
    source_mask, source_inventory = source_face_inventory(
        centers,
        widths,
        geometry,
        inputs.get("source_patch_areas_m2", {}),
        source_patch_face_counts=inputs.get("source_patch_face_counts"),
        mesh_inputs=inputs,
        geometry_tolerance_m=geometry_tolerance,
    )
    owners, neighbours = _cartesian_face_pairs(centers, widths, geometry_tolerance)
    volumes = np.prod(widths, axis=1)
    total_airborne_mass = float(np.sum(alpha * volumes, dtype=np.float64) * 1000.0)
    threshold_reports = []
    for threshold in (0.001, 0.9):
        labels = label_liquid_structures(alpha, owners, neighbours, threshold)
        result = classify_source_attachment(
            alpha,
            volumes,
            velocity,
            labels,
            source_mask,
            threshold,
        )
        result["native_cell_count"] = int(len(alpha))
        result["airborne_water_mass_kg"] = total_airborne_mass
        result["global_component_mass_kg"] = float(
            sum(row["mass_kg"] for row in result["components"])
        )
        result["thresholded_mass_is_subset_of_airborne_inventory"] = (
            result["selected_liquid_mass_kg"] <= total_airborne_mass + 1e-7
        )
        tag = f"t{requested_time:g}-alpha{threshold:g}"
        _write_component_csv(output_dir / f"{tag}-components.csv", result, threshold)
        threshold_reports.append(result)
    report = {
        "classification": (
            "Exploratory native-cell VOF structure diagnostic; not equivalent to the unpublished "
            "Calbrix MATLAB detector and not a paper acceptance gate."
        ),
        "case_id": inputs.get("case_id"),
        "run_directory": str(run_dir),
        "case_directory": str(case),
        "snapshot_time_s": snapshot["time_s"],
        "source_geometry_assumption": geometry.get("geometry_evidence")
        if isinstance(geometry, dict)
        else None,
        "source_attachment_definition": (
            "A selected component is attached only if it contains a native cell whose top face "
            "lies on the verified source rectangle at source_plane_z. All other selected components "
            "are detached under this geometric threshold definition."
        ),
        "component_connectivity": (
            "six-face connectivity reconstructed from native Cartesian cell centers and declared "
            "axis widths, including inter-rank neighbors"
        ),
        "precision_note": (
            "vtkPOpenFOAMReader parsed decomposed binary data with SetUse64BitFloats(True); the "
            "returned coordinates and fields are recorded at their actual VTK array precision. "
            "Saved-snapshot structure values are estimates, not exact reconstructed solver state."
        ),
        "reader": reader_metadata,
        "geometry_tolerance_m": geometry_tolerance,
        "source_face_inventory": source_inventory,
        "cell_count_expected": int(inputs["mesh_cells_expected"]),
        "airborne_water_mass_kg_all_alpha": total_airborne_mass,
        "input_hashes": {
            "case_inputs_sha256": hashlib.sha256(
                (case / "case-inputs.json").read_bytes()
            ).hexdigest(),
            "native_field_files": field_hashes,
        },
        "thresholds": threshold_reports,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _cartesian_face_pairs(
    centers_m: ArrayLike, widths_m: ArrayLike, geometry_tolerance_m: float
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Apply the shared Cartesian adjacency helper with this analysis' tolerance."""
    centers = np.asarray(centers_m, dtype=float)
    widths = np.asarray(widths_m, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 3 or widths.shape != centers.shape:
        raise ValueError("centers_m and widths_m must have matching (n, 3) shapes")
    if not np.all(np.isfinite(centers)) or not np.all(np.isfinite(widths)) or np.any(widths <= 0):
        raise ValueError("Cartesian centers and widths must be finite and widths positive")
    if not math.isfinite(geometry_tolerance_m) or geometry_tolerance_m <= 0:
        raise ValueError("geometry_tolerance_m must be finite and positive")
    return _shared_structured_face_pairs(centers, widths, geometry_atol_m=geometry_tolerance_m)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--time-s", type=float, default=1.0)
    args = parser.parse_args()
    result = analyze(args.run_dir, args.output_dir, time_s=args.time_s)
    print(
        json.dumps(
            {
                "snapshot_time_s": result["snapshot_time_s"],
                "output_directory": str(args.output_dir.resolve()),
                "thresholds": [row["alpha_threshold"] for row in result["thresholds"]],
            }
        )
    )


if __name__ == "__main__":
    main()
