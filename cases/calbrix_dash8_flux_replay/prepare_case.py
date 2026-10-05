#!/usr/bin/env python3
"""Prepare matched nearfield cases replaying a native tank water-flux history.

The source arrays are native, signed per-face ``alphaPhi_`` step averages from
the separate provisional gravity-discharge pilot.  They are conservatively
overlapped onto the Dash-8 opening and replayed by integrating source averages
over each actual nearfield step interval.  This module does not run OpenFOAM.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_CASE = ROOT / "results/runs/dash8-freestream-backflow-20261004T200945Z/case"
SOURCE_PATCH = "dash8Opening"
WATER_DENSITY_KG_M3 = 1000.0
SOURCE_ARRAY_KEYS = {
    "time_end_s",
    "delta_t_s",
    "source_face_bounds_xy_m",
    "source_face_areas_m2",
    "source_water_volume_rate_m3_s",
    "source_face_ids",
}
REQUIRED_SOURCE_MANIFEST = {
    "schema": "dash8-native-tank-alphaPhi-step-series-v1",
    "rate_field": "alphaPhi_",
    "rate_basis": "signed face-integrated volume rate averaged over [time_end-delta_t,time_end]",
    "coordinate_frame": "target nearfield frame: x streamwise, y transverse; tank x/y swap already applied",
    "positive_rate_direction": "downward, -z",
    "source_normal_xyz": [0.0, 0.0, -1.0],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_input_hashes(case_dir: Path) -> dict[str, str]:
    """Hash the exact trees copied into each candidate, excluding run outputs."""
    paths = [
        path
        for name in ("0", "constant", "system", "source")
        if (case_dir / name).is_dir()
        for path in (case_dir / name).rglob("*")
        if path.is_file()
    ]
    paths.extend(
        path
        for name in ("case-inputs.json", "source_geometry.json")
        if (path := case_dir / name).is_file()
    )
    return {path.relative_to(case_dir).as_posix(): sha256_file(path) for path in sorted(paths)}


def _git_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None, "dirty_paths": None}
    return {
        "revision": revision,
        "dirty": bool(status),
        "dirty_paths": [line[3:] for line in status],
    }


def _producer_provenance() -> dict[str, Any]:
    """Identify this generator and the shared base-case producer inputs."""
    base_helper = ROOT / "cases/calbrix_dash8/prepare_case.py"
    return {
        "generator_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
        "generator_sha256": sha256_file(Path(__file__).resolve()),
        "base_case_generator_path": base_helper.relative_to(ROOT).as_posix(),
        "base_case_generator_sha256": sha256_file(base_helper),
    }


def _finite_array(value: Any, shape_tail: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 1 + len(shape_tail) or array.shape[1:] != shape_tail:
        tail = "".join(f"x{n}" for n in shape_tail)
        raise ValueError(f"{name} must have shape Nx{tail}, got {array.shape}")
    if not array.shape[0] or not np.isfinite(array).all():
        raise ValueError(f"{name} must be nonempty and finite")
    return array


def validate_source_manifest(manifest: dict[str, Any]) -> None:
    """Require explicit semantics so interpolated alpha/U proxies cannot pass."""
    for key, expected in REQUIRED_SOURCE_MANIFEST.items():
        actual = manifest.get(key)
        if key == "source_normal_xyz":
            if (
                not isinstance(actual, (list, tuple))
                or len(actual) != 3
                or not np.allclose(
                    np.asarray(actual, dtype=np.float64), expected, rtol=0.0, atol=1e-12
                )
            ):
                raise ValueError("source normals must be native unit normals directed -z")
        elif actual != expected:
            raise ValueError(f"source manifest {key!r} must equal {expected!r}")
    source_run = manifest.get("source_run_id")
    if not isinstance(source_run, str) or not source_run.strip():
        raise ValueError("source manifest must identify source_run_id")
    if manifest.get("classification") != "native_solver_alphaPhi_step_average":
        raise ValueError("only a native per-face alphaPhi step-average series is accepted")
    for key in ("source_npz_sha256", "producer_script_sha256"):
        value = manifest.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"source manifest must provide a valid {key}")
    for key in ("producer_script_path", "native_case_path"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"source manifest must provide {key}")
    reconciliation = manifest.get("native_reconciliation")
    if not isinstance(reconciliation, dict):
        raise ValueError("source manifest must include native aggregate reconciliation evidence")
    if reconciliation.get("all_steps_match") is not True:
        raise ValueError("native per-face rates are not reconciled at every time step")
    for key in ("aggregate_sha256",):
        value = reconciliation.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"native reconciliation must provide a valid {key}")
    if not all(
        isinstance(reconciliation.get(key), str) and reconciliation[key].strip()
        for key in ("method", "aggregate_path")
    ):
        raise ValueError("native reconciliation must identify its method and aggregate file")
    try:
        max_error = float(reconciliation["max_abs_rate_error_m3_s"])
        tolerance = float(reconciliation["tolerance_m3_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "native reconciliation must report maximum rate error and tolerance"
        ) from error
    if not math.isfinite(max_error) or not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("native reconciliation error and tolerance must be finite and valid")
    if max_error < 0.0 or max_error > tolerance:
        raise ValueError("native per-face to aggregate flux difference exceeds producer tolerance")
    for key in ("matched_step_count", "face_count"):
        value = reconciliation.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"native reconciliation must provide positive integer {key}")


def validate_source_arrays(arrays: dict[str, Any]) -> dict[str, np.ndarray]:
    missing = SOURCE_ARRAY_KEYS - set(arrays)
    extras = set(arrays) - SOURCE_ARRAY_KEYS
    if missing or extras:
        raise ValueError(
            f"source arrays have missing keys {sorted(missing)} or extras {sorted(extras)}"
        )

    ends = _finite_array(arrays["time_end_s"], (), "time_end_s")
    delta = _finite_array(arrays["delta_t_s"], (), "delta_t_s")
    bounds = _finite_array(arrays["source_face_bounds_xy_m"], (4,), "source_face_bounds_xy_m")
    areas = _finite_array(arrays["source_face_areas_m2"], (), "source_face_areas_m2")
    rates = np.asarray(arrays["source_water_volume_rate_m3_s"], dtype=np.float64)
    raw_ids = np.asarray(arrays["source_face_ids"])
    if raw_ids.ndim != 2 or raw_ids.shape[1] != 2 or raw_ids.dtype.kind not in "iu":
        raise ValueError("source_face_ids must be an integer (faces, 2) rank/local-ID array")
    ids = raw_ids.astype(np.int64, copy=False)
    if len(np.unique(ids, axis=0)) != ids.shape[0]:
        raise ValueError("source_face_ids must be unique")
    if ends.ndim != 1 or delta.shape != ends.shape:
        raise ValueError("time_end_s and delta_t_s must be matching one-dimensional arrays")
    if np.any(delta <= 0.0) or np.any(ends <= 0.0) or np.any(np.diff(ends) <= 0.0):
        raise ValueError("source step durations and end times must be positive and increasing")
    starts = ends - delta
    if starts[0] < -1e-12 or not math.isclose(float(starts[0]), 0.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("native source support must start at t=0")
    if not np.allclose(starts[1:], ends[:-1], rtol=0.0, atol=1e-9):
        raise ValueError("native source intervals must be contiguous without gaps or overlap")
    if bounds.shape[0] != areas.size or ids.shape[0] != areas.size:
        raise ValueError("source geometry, areas, and IDs must contain the same faces")
    if rates.shape != (ends.size, areas.size) or not np.isfinite(rates).all():
        raise ValueError("source volume-rate matrix must have shape (steps, faces)")
    if np.any(areas <= 0.0):
        raise ValueError("source face areas must be positive")
    if np.any(bounds[:, 0] >= bounds[:, 1]) or np.any(bounds[:, 2] >= bounds[:, 3]):
        raise ValueError("source face rectangles must have positive x/y extents")
    geometric_areas = (bounds[:, 1] - bounds[:, 0]) * (bounds[:, 3] - bounds[:, 2])
    if not np.allclose(geometric_areas, areas, rtol=1e-8, atol=1e-12):
        raise ValueError("source face areas do not match their axis-aligned rectangles")
    return {
        "time_end_s": ends,
        "delta_t_s": delta,
        "time_start_s": starts,
        "source_face_bounds_xy_m": bounds,
        "source_face_areas_m2": areas,
        "source_water_volume_rate_m3_s": rates,
        "source_face_ids": ids,
    }


def _axis_cells(case_inputs: dict[str, Any], axis: str) -> list[tuple[float, float]]:
    breaks = case_inputs.get("mesh_breaks_m", {}).get(axis)
    counts = case_inputs.get("mesh_cells_per_segment", {}).get(axis)
    if (
        not isinstance(breaks, list)
        or not isinstance(counts, list)
        or len(breaks) != len(counts) + 1
        or not counts
    ):
        raise ValueError(f"case-inputs.json lacks valid {axis} mesh breaks/cell counts")
    cells: list[tuple[float, float]] = []
    for lo, hi, count in zip(breaks[:-1], breaks[1:], counts, strict=True):
        if not isinstance(count, int) or count <= 0 or float(lo) >= float(hi):
            raise ValueError(f"invalid {axis} mesh segment")
        step = (float(hi) - float(lo)) / count
        cells.extend((float(lo) + i * step, float(lo) + (i + 1) * step) for i in range(count))
    return cells


def target_rectangles_from_case_inputs(
    case_dir: Path, patch_name: str = SOURCE_PATCH
) -> dict[str, np.ndarray]:
    """Derive the structured opening-face rectangles from this target case's mesh metadata."""
    case_dir = Path(case_dir)
    inputs = json.loads((case_dir / "case-inputs.json").read_text(encoding="utf-8"))
    patch_counts = inputs.get("source_patch_face_counts", {})
    if patch_name not in patch_counts:
        raise ValueError(f"target case metadata does not declare patch {patch_name!r}")
    geometry_path = case_dir / "source_geometry.json"
    geometry = (
        json.loads(geometry_path.read_text(encoding="utf-8")) if geometry_path.is_file() else {}
    )
    sources = geometry.get("sources")
    if not isinstance(sources, list):
        sources = inputs.get("sources")
    if not sources:
        raise ValueError("target case metadata does not declare source opening bounds")
    source = next((row for row in sources if row.get("name") == patch_name), None)
    if source is None:
        raise ValueError(f"target metadata has no source geometry for {patch_name!r}")
    source_bounds = source.get("bounds_m")
    if not isinstance(source_bounds, dict):
        raise ValueError("target source geometry must include bounds_m")
    x0, x1 = map(float, source_bounds["x"])
    y0, y1 = map(float, source_bounds["y"])

    def within_opening(axis: str, lower: float, upper: float) -> list[tuple[float, float]]:
        cells = _axis_cells(inputs, axis)
        selected = []
        tolerance = 1e-9
        for lo, hi in cells:
            overlaps = lo < upper - tolerance and hi > lower + tolerance
            contained = lo >= lower - tolerance and hi <= upper + tolerance
            if overlaps and not contained:
                raise ValueError(f"opening boundary does not align with target {axis} cells")
            if contained:
                selected.append((lo, hi))
        if (
            not selected
            or not math.isclose(selected[0][0], lower, abs_tol=tolerance)
            or not math.isclose(selected[-1][1], upper, abs_tol=tolerance)
        ):
            raise ValueError(f"target {axis} cells do not tile the full opening")
        return selected

    x_cells = within_opening("x", x0, x1)
    y_cells = within_opening("y", y0, y1)
    # Stable geometric ordering. Runtime BC lookup uses the same x-major/y-minor order.
    bounds = np.asarray(
        [[xa, xb, ya, yb] for xa, xb in x_cells for ya, yb in y_cells], dtype=np.float64
    )
    areas = (bounds[:, 1] - bounds[:, 0]) * (bounds[:, 3] - bounds[:, 2])
    centers_x = np.asarray([(lo + hi) / 2.0 for lo, hi in x_cells], dtype=np.float64)
    centers_y = np.asarray([(lo + hi) / 2.0 for lo, hi in y_cells], dtype=np.float64)
    if bounds.shape[0] != int(patch_counts[patch_name]):
        raise ValueError(
            f"derived {bounds.shape[0]} faces for {patch_name}, metadata declares {patch_counts[patch_name]}"
        )
    declared_area = float(inputs.get("source_patch_areas_m2", {}).get(patch_name, -1.0))
    if not math.isclose(float(areas.sum()), declared_area, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("derived target rectangles do not match the declared opening area")
    return {
        "bounds_xy_m": bounds,
        "areas_m2": areas,
        "centers_x_m": centers_x,
        "centers_y_m": centers_y,
    }


def target_rectangles_from_native_geometry(
    case_dir: Path, geometry_json_path: Path, patch_name: str = SOURCE_PATCH
) -> dict[str, Any]:
    """Load native target-face rectangles after verifying the source mesh hashes.

    The runtime coded boundary uses a structured center lookup. Native face IDs
    are retained for provenance, while this loader checks that native cells
    form a complete x-major/y-minor center grid before producing its row order.
    """
    case_dir = Path(case_dir).resolve()
    geometry_path = Path(geometry_json_path).resolve()
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    if geometry.get("schema") != "dash8-native-target-face-rectangles-v1":
        raise ValueError("unsupported native target face geometry schema")
    if geometry.get("source_patch") != patch_name:
        raise ValueError(f"native target geometry is not for patch {patch_name!r}")
    if Path(geometry.get("case_path", "")).resolve() != case_dir:
        raise ValueError("native target geometry belongs to a different base case")

    inputs = json.loads((case_dir / "case-inputs.json").read_text(encoding="utf-8"))
    patch_count = int(inputs.get("source_patch_face_counts", {}).get(patch_name, -1))
    declared_area = float(inputs.get("source_patch_areas_m2", {}).get(patch_name, -1.0))
    if patch_count <= 0 or geometry.get("patch_face_count") != patch_count:
        raise ValueError("native target face count does not match the base case metadata")
    if geometry.get("mesh_cells_expected") != inputs.get("mesh_cells_expected"):
        raise ValueError("native target geometry cell count does not match the base case")

    provenance = geometry.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("native target geometry is missing mesh hash provenance")
    poly_mesh = case_dir / "constant/polyMesh"
    native_hash_names = {
        "boundary": "boundary_sha256",
        "faces": "faces_sha256",
        "owner": "owner_sha256",
        "points": "points_sha256",
    }
    native_hashes = {}
    for file_name, provenance_key in native_hash_names.items():
        path = poly_mesh / file_name
        expected = provenance.get(provenance_key)
        if not path.is_file() or not isinstance(expected, str):
            raise ValueError("native target geometry provenance lacks a polyMesh file hash")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"native target mesh {file_name} hash differs from geometry input")
        native_hashes[file_name] = actual

    bounds = _finite_array(geometry.get("bounds_xy_m"), (4,), "native target bounds_xy_m")
    areas = _finite_array(geometry.get("areas_m2"), (), "native target areas_m2")
    centers = _finite_array(geometry.get("centers_xyz_m"), (3,), "native target centers_xyz_m")
    area_vectors = _finite_array(
        geometry.get("area_vectors_m2"), (3,), "native target area_vectors_m2"
    )
    raw_ids = np.asarray(geometry.get("face_ids"))
    if raw_ids.ndim != 2 or raw_ids.shape != (patch_count, 3) or raw_ids.dtype.kind not in "iu":
        raise ValueError("native target face_ids must be integer patch/local/native/owner triples")
    ids = raw_ids.astype(np.int64, copy=False)
    if any(len(np.unique(ids[:, column])) != patch_count for column in range(3)):
        raise ValueError("native target patch-local/native/owner identifiers must be unique")
    if not (
        bounds.shape[0] == areas.size == centers.shape[0] == area_vectors.shape[0] == patch_count
    ):
        raise ValueError("native target geometry arrays have inconsistent face counts")
    if np.any(bounds[:, 0] >= bounds[:, 1]) or np.any(bounds[:, 2] >= bounds[:, 3]):
        raise ValueError("native target rectangles must have positive x/y extents")
    geometric_areas = (bounds[:, 1] - bounds[:, 0]) * (bounds[:, 3] - bounds[:, 2])
    if np.any(areas <= 0.0) or not np.allclose(geometric_areas, areas, rtol=1e-8, atol=1e-12):
        raise ValueError("native target face areas do not match rectangular bounds")
    if not np.allclose(
        centers[:, :2],
        np.column_stack(((bounds[:, 0] + bounds[:, 1]) / 2, (bounds[:, 2] + bounds[:, 3]) / 2)),
        rtol=0.0,
        atol=1e-10,
    ):
        raise ValueError("native target centers do not match rectangle midpoints")
    if not np.allclose(centers[:, 2], 0.0, rtol=0.0, atol=1e-10):
        raise ValueError("target source faces must lie on the declared z=0 plane")
    if not np.allclose(np.linalg.norm(area_vectors, axis=1), areas, rtol=1e-8, atol=1e-12):
        raise ValueError("native target Sf magnitudes do not match face areas")
    if not np.allclose(area_vectors[:, :2], 0.0, rtol=0.0, atol=1e-12) or not np.allclose(
        area_vectors[:, 2], areas, rtol=0.0, atol=1e-12
    ):
        raise ValueError("target top opening must have native outward Sf directed along +z")
    if not math.isclose(float(areas.sum()), declared_area, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("native target face areas do not match the declared source patch area")

    x_centers = np.unique(np.round(centers[:, 0], 10))
    y_centers = np.unique(np.round(centers[:, 1], 10))
    declared_grid = geometry.get("grid_shape_x_by_y")
    if x_centers.size * y_centers.size != patch_count or declared_grid != [
        int(x_centers.size),
        int(y_centers.size),
    ]:
        raise ValueError("native target face centers do not form the declared structured grid")
    lookup: dict[tuple[float, float], int] = {}
    for index, center in enumerate(np.round(centers[:, :2], 10)):
        key = (float(center[0]), float(center[1]))
        if key in lookup:
            raise ValueError("duplicate native target x/y face center")
        lookup[key] = index
    expected_keys = [(float(x), float(y)) for x in x_centers for y in y_centers]
    if set(lookup) != set(expected_keys):
        raise ValueError("native target centers do not cover every structured lookup position")
    order = np.asarray([lookup[key] for key in expected_keys], dtype=np.int64)
    declared_x = np.asarray(geometry.get("x_centers_m"), dtype=np.float64)
    declared_y = np.asarray(geometry.get("y_centers_m"), dtype=np.float64)
    if not np.allclose(declared_x, x_centers, rtol=0.0, atol=1e-10) or not np.allclose(
        declared_y, y_centers, rtol=0.0, atol=1e-10
    ):
        raise ValueError("native target center vectors differ from the geometry rows")
    face_ids = ids[order]
    if not np.array_equal(np.sort(face_ids[:, 0]), np.arange(patch_count)):
        raise ValueError("native target local face IDs are not a complete patch-local sequence")

    return {
        "bounds_xy_m": bounds[order],
        "areas_m2": areas[order],
        "centers_x_m": x_centers,
        "centers_y_m": y_centers,
        "face_ids": face_ids,
        "centers_xyz_m": centers[order],
        "area_vectors_m2": area_vectors[order],
        "geometry_provenance": {
            "geometry_json_path": str(geometry_path),
            "geometry_json_sha256": sha256_file(geometry_path),
            "geometry_schema": geometry["schema"],
            "native_mesh_hashes": native_hashes,
            "face_order": "runtime x-major/y-minor grid lookup; each row preserves patch-local index, native mesh-face index, and owner-cell ID",
            "target_outward_normal_xyz": [0.0, 0.0, 1.0],
            "target_patch_face_count": patch_count,
            "target_patch_area_m2": float(areas.sum()),
        },
    }


def overlap_matrix(
    source_bounds: np.ndarray,
    source_areas: np.ndarray,
    target_bounds: np.ndarray,
    target_areas: np.ndarray,
    *,
    area_tolerance_m2: float = 1e-11,
    relative_tolerance: float = 1e-8,
) -> np.ndarray:
    """Return source×target overlap areas, rejecting crop, gaps and inconsistent areas."""
    source_bounds = _finite_array(source_bounds, (4,), "source_bounds")
    target_bounds = _finite_array(target_bounds, (4,), "target_bounds")
    source_areas = _finite_array(source_areas, (), "source_areas")
    target_areas = _finite_array(target_areas, (), "target_areas")
    if source_areas.shape != (source_bounds.shape[0],) or target_areas.shape != (
        target_bounds.shape[0],
    ):
        raise ValueError("overlap face area vectors must match their bounds")
    source_geom = (source_bounds[:, 1] - source_bounds[:, 0]) * (
        source_bounds[:, 3] - source_bounds[:, 2]
    )
    target_geom = (target_bounds[:, 1] - target_bounds[:, 0]) * (
        target_bounds[:, 3] - target_bounds[:, 2]
    )
    if not np.allclose(source_geom, source_areas, rtol=relative_tolerance, atol=area_tolerance_m2):
        raise ValueError("source face areas do not match their rectangle geometry")
    if not np.allclose(target_geom, target_areas, rtol=relative_tolerance, atol=area_tolerance_m2):
        raise ValueError("target face areas do not match their rectangle geometry")
    x_width = np.maximum(
        0.0,
        np.minimum(source_bounds[:, None, 1], target_bounds[None, :, 1])
        - np.maximum(source_bounds[:, None, 0], target_bounds[None, :, 0]),
    )
    y_width = np.maximum(
        0.0,
        np.minimum(source_bounds[:, None, 3], target_bounds[None, :, 3])
        - np.maximum(source_bounds[:, None, 2], target_bounds[None, :, 2]),
    )
    overlaps = x_width * y_width
    source_covered = overlaps.sum(axis=1)
    target_covered = overlaps.sum(axis=0)
    if not np.allclose(
        source_covered, source_areas, rtol=relative_tolerance, atol=area_tolerance_m2
    ):
        raise ValueError(
            "target opening does not fully cover each source face; refusing crop/extrapolation"
        )
    if not np.allclose(
        target_covered, target_areas, rtol=relative_tolerance, atol=area_tolerance_m2
    ):
        raise ValueError(
            "source data do not fully cover each target face; refusing crop/extrapolation"
        )
    return overlaps


def map_rates_to_target(
    source_rates_m3_s: np.ndarray,
    source_bounds_xy_m: np.ndarray,
    source_areas_m2: np.ndarray,
    target_bounds_xy_m: np.ndarray,
    target_areas_m2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Conservatively map signed source face rates to the target grid.

    The within-source-face rate density is held constant over that native face;
    overlap integration preserves the total signed rate at every source step.
    """
    rates = np.asarray(source_rates_m3_s, dtype=np.float64)
    if rates.ndim != 2 or not rates.shape[0] or not np.isfinite(rates).all():
        raise ValueError("source rate matrix must be a finite two-dimensional array")
    source_areas = _finite_array(source_areas_m2, (), "source_areas_m2")
    target_areas = _finite_array(target_areas_m2, (), "target_areas_m2")
    if rates.shape[1] != source_areas.size:
        raise ValueError("source rate matrix does not match source face count")
    overlaps = overlap_matrix(source_bounds_xy_m, source_areas, target_bounds_xy_m, target_areas)
    mapped = rates @ (overlaps / source_areas[:, None])
    if not np.allclose(mapped.sum(axis=1), rates.sum(axis=1), rtol=1e-10, atol=1e-12):
        raise ValueError("mapped source rate does not conserve signed total flux")
    uniform = np.outer(rates.sum(axis=1) / target_areas.sum(), target_areas)
    return mapped, uniform


def rebin_step_averages(
    source_start_s: np.ndarray,
    source_end_s: np.ndarray,
    source_step_average: np.ndarray,
    target_start_s: np.ndarray,
    target_end_s: np.ndarray,
) -> np.ndarray:
    """Integrate source step-average data over target intervals (piecewise constant)."""
    starts = np.asarray(source_start_s, dtype=np.float64)
    ends = np.asarray(source_end_s, dtype=np.float64)
    values = np.asarray(source_step_average, dtype=np.float64)
    target_starts = np.asarray(target_start_s, dtype=np.float64)
    target_ends = np.asarray(target_end_s, dtype=np.float64)
    if (
        starts.ndim != 1
        or ends.shape != starts.shape
        or values.ndim < 1
        or values.shape[0] != ends.size
        or not np.isfinite(values).all()
    ):
        raise ValueError("source interval arrays and values have inconsistent lengths")
    if target_starts.ndim != 1 or target_ends.shape != target_starts.shape:
        raise ValueError("target interval starts and ends must match")
    if (
        not np.isfinite(starts).all()
        or not np.isfinite(ends).all()
        or not np.isfinite(target_starts).all()
        or not np.isfinite(target_ends).all()
    ):
        raise ValueError("all time intervals must be finite")
    if np.any(ends <= starts) or np.any(target_ends <= target_starts):
        raise ValueError("time intervals must have positive duration")
    if np.any(starts[1:] < ends[:-1] - 1e-9) or np.any(starts[1:] > ends[:-1] + 1e-9):
        raise ValueError("source intervals must be contiguous and ordered")
    output = np.zeros((target_starts.size, *values.shape[1:]), dtype=np.float64)
    for target_i, (start, end) in enumerate(zip(target_starts, target_ends, strict=True)):
        if start < starts[0] - 1e-9 or end > ends[-1] + 1e-9:
            raise ValueError(
                "target interval exceeds native source support; extrapolation is forbidden"
            )
        widths = np.maximum(0.0, np.minimum(end, ends) - np.maximum(start, starts))
        covered = float(widths.sum())
        if not math.isclose(covered, end - start, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("target interval is not completely covered by native source steps")
        output[target_i] = np.tensordot(widths, values, axes=(0, 0)) / (end - start)
    return output


def standard_kepsilon_from_speed(
    mean_speed_m_s: float,
    *,
    intensity: float = 0.05,
    length_scale_m: float = 0.05,
    Cmu: float = 0.09,
) -> tuple[float, float]:
    """Project-assumed water inlet k/epsilon values from the total-rate mean speed."""
    values = (mean_speed_m_s, intensity, length_scale_m, Cmu)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("k-epsilon source parameters must be finite")
    if intensity <= 0.0 or length_scale_m <= 0.0 or Cmu <= 0.0:
        raise ValueError("intensity, length scale, and Cmu must be positive")
    k = max(1e-12, 1.5 * (intensity * abs(mean_speed_m_s)) ** 2)
    epsilon = max(1e-12, Cmu**0.75 * k**1.5 / length_scale_m)
    return k, epsilon


def replay_diagnostics(
    rates_m3_s: np.ndarray, target_areas_m2: np.ndarray, delta_t_s: np.ndarray
) -> dict[str, Any]:
    rates = np.asarray(rates_m3_s, dtype=np.float64)
    if rates.ndim != 2 or not rates.shape[0] or not np.isfinite(rates).all():
        raise ValueError("rates_m3_s must be a finite step-by-face matrix")
    areas = _finite_array(target_areas_m2, (), "target_areas_m2")
    delta = _finite_array(delta_t_s, (), "delta_t_s")
    if rates.shape != (delta.size, areas.size) or np.any(areas <= 0.0) or np.any(delta <= 0.0):
        raise ValueError("replay diagnostic array shapes/areas/durations are invalid")
    speeds = rates / areas[None, :]
    per_step_momentum_abs = WATER_DENSITY_KG_M3 * np.sum(rates * rates / areas[None, :], axis=1)
    per_step_power_out = 0.5 * WATER_DENSITY_KG_M3 * np.sum(rates**3 / areas[None, :] ** 2, axis=1)
    uniform_rates = np.outer(rates.sum(axis=1) / areas.sum(), areas)
    uniform_momentum_abs = WATER_DENSITY_KG_M3 * np.sum(uniform_rates**2 / areas[None, :], axis=1)
    momentum_impulse = float(np.sum(per_step_momentum_abs * delta))
    uniform_momentum_impulse = float(np.sum(uniform_momentum_abs * delta))
    signed_energy = float(np.sum(per_step_power_out * delta))
    step_total_rate = rates.sum(axis=1)
    step_extra_momentum = per_step_momentum_abs - uniform_momentum_abs
    uniform_power = (
        0.5 * WATER_DENSITY_KG_M3 * np.sum(uniform_rates**3 / areas[None, :] ** 2, axis=1)
    )
    extra_power = per_step_power_out - uniform_power
    return {
        "signed_total_volume_m3": float(np.sum(rates.sum(axis=1) * delta)),
        "step_total_rate_min_m3_s": float(np.min(step_total_rate)),
        "step_total_rate_max_m3_s": float(np.max(step_total_rate)),
        "max_abs_step_total_difference_from_uniform_m3_s": float(
            np.max(np.abs(rates.sum(axis=1) - uniform_rates.sum(axis=1)))
        ),
        "normal_speed_min_m_s": float(np.min(speeds)),
        "normal_speed_max_m_s": float(np.max(speeds)),
        "normal_momentum_flux_magnitude_max_N": float(np.max(per_step_momentum_abs)),
        "uniform_normal_momentum_flux_magnitude_max_N": float(np.max(uniform_momentum_abs)),
        "extra_normal_momentum_flux_magnitude_max_N": float(np.max(step_extra_momentum)),
        "normal_momentum_impulse_magnitude_N_s": momentum_impulse,
        "uniform_normal_momentum_impulse_magnitude_N_s": uniform_momentum_impulse,
        "extra_normal_momentum_impulse_magnitude_N_s": momentum_impulse - uniform_momentum_impulse,
        "signed_outward_kinetic_energy_J": signed_energy,
        "uniform_signed_outward_kinetic_energy_J": float(np.sum(uniform_power * delta)),
        "extra_signed_outward_kinetic_energy_J": float(np.sum(extra_power * delta)),
        "signed_outward_kinetic_power_min_W": float(np.min(per_step_power_out)),
        "signed_outward_kinetic_power_max_W": float(np.max(per_step_power_out)),
        "momentum_sign_convention": "rho*sum(q_face^2/A_face); magnitude of normal advective momentum flux, vector points downward for the -z outlet orientation, including signed backflow",
        "kinetic_power_sign_convention": "0.5*rho*sum(q_face^3/A_face^2), signed outward through the downward-oriented plane",
    }


def write_step_diagnostics(
    path: Path,
    *,
    start_s: np.ndarray,
    end_s: np.ndarray,
    delta_t_s: np.ndarray,
    rates: np.ndarray,
    uniform_rates: np.ndarray,
    areas: np.ndarray,
) -> None:
    """Write per-step momentum/energy summaries separately from compact JSON."""
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        columns = [
            "step",
            "time_start_s",
            "time_end_s",
            "delta_t_s",
            "uniform_total_rate_m3_s",
            "mapped_total_rate_m3_s",
            "uniform_min_speed_m_s",
            "uniform_max_speed_m_s",
            "mapped_min_speed_m_s",
            "mapped_max_speed_m_s",
            "uniform_momentum_flux_N",
            "mapped_momentum_flux_N",
            "extra_momentum_flux_N",
            "uniform_signed_kinetic_power_W",
            "mapped_signed_kinetic_power_W",
            "extra_signed_kinetic_power_W",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for index in range(len(end_s)):
            q_uniform = uniform_rates[index]
            q_mapped = rates[index]
            uniform_momentum = WATER_DENSITY_KG_M3 * float(np.sum(q_uniform**2 / areas))
            mapped_momentum = WATER_DENSITY_KG_M3 * float(np.sum(q_mapped**2 / areas))
            uniform_power = 0.5 * WATER_DENSITY_KG_M3 * float(np.sum(q_uniform**3 / areas**2))
            mapped_power = 0.5 * WATER_DENSITY_KG_M3 * float(np.sum(q_mapped**3 / areas**2))
            writer.writerow(
                {
                    "step": index,
                    "time_start_s": format(float(start_s[index]), ".17g"),
                    "time_end_s": format(float(end_s[index]), ".17g"),
                    "delta_t_s": format(float(delta_t_s[index]), ".17g"),
                    "uniform_total_rate_m3_s": format(float(q_uniform.sum()), ".17g"),
                    "mapped_total_rate_m3_s": format(float(q_mapped.sum()), ".17g"),
                    "uniform_min_speed_m_s": format(float(np.min(q_uniform / areas)), ".17g"),
                    "uniform_max_speed_m_s": format(float(np.max(q_uniform / areas)), ".17g"),
                    "mapped_min_speed_m_s": format(float(np.min(q_mapped / areas)), ".17g"),
                    "mapped_max_speed_m_s": format(float(np.max(q_mapped / areas)), ".17g"),
                    "uniform_momentum_flux_N": format(uniform_momentum, ".17g"),
                    "mapped_momentum_flux_N": format(mapped_momentum, ".17g"),
                    "extra_momentum_flux_N": format(mapped_momentum - uniform_momentum, ".17g"),
                    "uniform_signed_kinetic_power_W": format(uniform_power, ".17g"),
                    "mapped_signed_kinetic_power_W": format(mapped_power, ".17g"),
                    "extra_signed_kinetic_power_W": format(mapped_power - uniform_power, ".17g"),
                }
            )


def _foam_scalar(value: float) -> str:
    return "0" if value == 0.0 else format(float(value), ".16g")


def _foam_list(values: np.ndarray) -> str:
    return "(" + " ".join(_foam_scalar(x) for x in np.asarray(values).reshape(-1)) + ")"


def write_replay_table(
    path: Path,
    centers_x: np.ndarray,
    centers_y: np.ndarray,
    areas: np.ndarray,
    start_s: np.ndarray,
    end_s: np.ndarray,
    rates: np.ndarray,
) -> None:
    """Write compact OpenFOAM dictionary data consumed once by codedFixedValue."""
    rows = ["(" + " ".join(_foam_scalar(q) for q in row) + ")" for row in rates]
    data = f"""/* Native alphaPhi step-average replay data. Positive q means downward water outflow. */
FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    location "system";
    object dash8FluxReplayData;
}}
timeStart_s {_foam_list(start_s)};
timeEnd_s {_foam_list(end_s)};
targetXCenters_m {_foam_list(centers_x)};
targetYCenters_m {_foam_list(centers_y)};
targetAreas_m2 {_foam_list(areas)};
rates_m3_s
(
{chr(10).join(rows)}
);
"""
    Path(path).write_text(data, encoding="utf-8")


def coded_replay_boundary(*, field: str = "U") -> str:
    """Generate interval-integrating v2512 codedFixedValue boundary code.

    The cached dictionary contains target-face source-step average rates. Every
    actual nearfield interval is integrated against those averages; no point
    interpolation, clipping of signed rates, or temporal hold is performed.
    """
    if field not in {"U", "k", "epsilon"}:
        raise ValueError("field must be U, k, or epsilon")
    # This helper deliberately reads the emitted OpenFOAM list dictionary once
    # per MPI process, not once per time step.
    value_entry = "uniform (0 0 0)" if field == "U" else "uniform 1e-12"
    result_decl = (
        "vectorField result(this->size(), vector::zero);"
        if field == "U"
        else "scalarField result(this->size(), 1e-12);"
    )
    field_code = f"""            const scalar intensity = 0.05;
            const scalar lengthScale = 0.05;
            const scalar Cmu = 0.09;
            const scalar areaTotal = sum(table.faceAreas);
            scalar totalVolume = 0.0;
            forAll(table.endTimes, stepj)
            {{
                const scalar overlap = max
                (
                    scalar(0),
                    min(tEnd, table.endTimes[stepj])
                  - max(tStart, table.startTimes[stepj])
                );
                totalVolume += overlap*table.totalRates[stepj];
            }}
            const scalar meanSpeed = mag(totalVolume/(deltaT*areaTotal));
            const scalar kMean = max(scalar(1e-12), scalar(1.5)*sqr(intensity*meanSpeed));
            const scalar epsilonMean = max
            (
                scalar(1e-12),
                pow(Cmu, scalar(0.75))*pow(kMean, scalar(1.5))/lengthScale
            );
            const scalar value = {"kMean" if field == "k" else "epsilonMean"};
            forAll(result, facei) result[facei] = value;
"""
    if field == "U":
        field_code = """            const vectorField& centers = this->patch().Cf();
            const scalarField& actualAreas = this->patch().magSf();
            forAll(result, facei)
            {
                label ix = -1;
                label iy = -1;
                scalar dxBest = GREAT;
                scalar dyBest = GREAT;
                forAll(table.xCenters, i)
                {
                    const scalar d = mag(centers[facei].x() - table.xCenters[i]);
                    if (d < dxBest) { dxBest = d; ix = i; }
                }
                forAll(table.yCenters, i)
                {
                    const scalar d = mag(centers[facei].y() - table.yCenters[i]);
                    if (d < dyBest) { dyBest = d; iy = i; }
                }
                if (ix < 0 || iy < 0 || dxBest > 1e-7 || dyBest > 1e-7)
                {
                    FatalErrorInFunction
                        << "source patch face center not found in replay mesh geometry"
                        << exit(FatalError);
                }
                const label row = ix*table.yCenters.size() + iy;
                if (mag(actualAreas[facei] - table.faceAreas[row]) > 1e-8)
                {
                    FatalErrorInFunction
                        << "source patch face area differs from replay table"
                        << exit(FatalError);
                }
                scalar volume = 0.0;
                forAll(table.endTimes, stepj)
                {
                    const scalar overlap = max
                    (
                        scalar(0),
                        min(tEnd, table.endTimes[stepj])
                      - max(tStart, table.startTimes[stepj])
                    );
                    volume += overlap*table.rates[stepj][row];
                }
                result[facei] = vector
                (
                    0,
                    0,
                    -volume/(deltaT*actualAreas[facei])
                );
            }
"""
    return f"""        type codedFixedValue;
        name dash8NativeTankFluxReplay{field.title()};
        value {value_entry};
        codeInclude
        #{{
            #include "fvCFD.H"
            #include "IOdictionary.H"
        #}};
        localCode
        #{{
            class Dash8FluxReplayTable
            {{
            public:
                List<scalar> startTimes;
                List<scalar> endTimes;
                List<scalar> xCenters;
                List<scalar> yCenters;
                List<scalar> faceAreas;
                List<scalar> totalRates;
                List<List<scalar>> rates;

                explicit Dash8FluxReplayTable(const Time& runTime)
                {{
                    IOdictionary data
                    (
                        IOobject
                        (
                            "dash8FluxReplayData",
                            runTime.system(),
                            runTime,
                            IOobject::MUST_READ,
                            IOobject::NO_WRITE,
                            false
                        )
                    );
                    data.lookup("timeStart_s") >> startTimes;
                    data.lookup("timeEnd_s") >> endTimes;
                    data.lookup("targetXCenters_m") >> xCenters;
                    data.lookup("targetYCenters_m") >> yCenters;
                    data.lookup("targetAreas_m2") >> faceAreas;
                    data.lookup("rates_m3_s") >> rates;
                    totalRates.setSize(rates.size(), 0.0);
                    if
                    (
                        startTimes.size() != endTimes.size()
                     || rates.size() != endTimes.size()
                     || faceAreas.size() != xCenters.size()*yCenters.size()
                    )
                    {{
                        FatalErrorInFunction
                            << "invalid Dash-8 replay table dimensions" << exit(FatalError);
                    }}
                    forAll(rates, stepi)
                    {{
                        if (rates[stepi].size() != faceAreas.size())
                        {{
                            FatalErrorInFunction
                                << "replay step has wrong face count" << exit(FatalError);
                        }}
                        totalRates[stepi] = sum(rates[stepi]);
                    }}
                }}
            }};
        #}};
        code
        #{{
            static const Dash8FluxReplayTable table(this->db().time());
            const scalar tEnd = this->db().time().value();
            const scalar deltaT = this->db().time().deltaTValue();
            {result_decl}
            if (tEnd > SMALL)
            {{
                const scalar tStart = tEnd - deltaT;
                const scalar supportStart = table.startTimes[0];
                const scalar supportEnd = table.endTimes.last();
                if (tStart < supportStart - 1e-9 || tEnd > supportEnd + 1e-9)
                {{
                    FatalErrorInFunction
                        << "nearfield replay interval [" << tStart << ", " << tEnd
                        << "] lies outside native tank support [" << supportStart << ", "
                        << supportEnd << "]" << exit(FatalError);
                }}
{field_code.rstrip()}
            }}
            operator==(result);
        #}};
"""


def _replace_patch_dictionary(text: str, patch: str, replacement: str) -> str:
    match = re.search(rf"(?m)^(\s*{re.escape(patch)}\s*)\n\s*\{{", text)
    if match is None:
        raise ValueError(f"could not find patch dictionary {patch!r}")
    open_brace = text.find("{", match.start())
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                close_brace = index + 1
                break
    else:
        raise ValueError(f"unterminated patch dictionary {patch!r}")
    header = match.group(1)
    patch_offset = header.find(patch)
    if patch_offset < 0:
        raise ValueError(f"could not preserve patch label {patch!r}")
    indent = header[:patch_offset]
    # ``replacement`` is the contents of a patch dictionary. Preserve the
    # actual OpenFOAM patch scope; codedFixedValue entries cannot be siblings
    # of patch dictionaries at boundaryField level.
    wrapped = f"{indent}{patch}\n{indent}{{\n{replacement.rstrip()}\n{indent}}}"
    result = text[: match.start()] + wrapped + text[close_brace:]
    if result == text:
        raise ValueError("patch replacement made no change")
    return result


def _case_input_directories(case_dir: Path) -> None:
    required = [
        case_dir / "0" / "U",
        case_dir / "0" / "alpha.water",
        case_dir / "system/controlDict",
        case_dir / "case-inputs.json",
        case_dir / "constant/polyMesh/boundary",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("base nearfield case is missing inputs: " + ", ".join(missing))


def _copy_base_case(base_case: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite case: {destination}")
    destination.mkdir(parents=True)
    for name in ("0", "constant", "system"):
        shutil.copytree(base_case / name, destination / name)
    for name in ("case-inputs.json", "source_geometry.json"):
        path = base_case / name
        if path.is_file():
            shutil.copy2(path, destination / name)
    source_dir = base_case / "source"
    if source_dir.is_dir():
        shutil.copytree(source_dir, destination / "source")


def prepare_pair(
    *,
    base_case: Path,
    source_npz: Path,
    source_manifest_path: Path,
    output_dir: Path,
    horizon_s: float = 0.6,
    target_face_geometry_json: Path | None = None,
    max_delta_t_s: float | None = None,
) -> dict[str, Any]:
    """Create matched uniform and mapped-flux case trees from a clean base case."""
    base_case = Path(base_case).resolve()
    source_npz = Path(source_npz).resolve()
    source_manifest_path = Path(source_manifest_path).resolve()
    output_dir = Path(output_dir).resolve()
    if target_face_geometry_json is not None:
        target_face_geometry_json = Path(target_face_geometry_json).resolve()
    if max_delta_t_s is not None and (
        not math.isfinite(float(max_delta_t_s)) or float(max_delta_t_s) <= 0.0
    ):
        raise ValueError("max_delta_t_s override must be finite and positive")
    _case_input_directories(base_case)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite preparation bundle: {output_dir}")
    if not source_npz.is_file() or not source_manifest_path.is_file():
        raise FileNotFoundError("native source NPZ and its provenance manifest are required")
    if target_face_geometry_json is not None and not target_face_geometry_json.is_file():
        raise FileNotFoundError(
            f"native target face geometry is missing: {target_face_geometry_json}"
        )
    manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    validate_source_manifest(manifest)
    source_npz_sha256 = sha256_file(source_npz)
    if manifest["source_npz_sha256"] != source_npz_sha256:
        raise ValueError("source NPZ SHA256 does not match the producer manifest")
    with np.load(source_npz, allow_pickle=False) as archive:
        arrays = validate_source_arrays({key: archive[key] for key in archive.files})
    reconciliation = manifest["native_reconciliation"]
    if reconciliation["matched_step_count"] != int(arrays["time_end_s"].size):
        raise ValueError("producer reconciliation step count does not match NPZ rows")
    if reconciliation["face_count"] != int(arrays["source_face_areas_m2"].size):
        raise ValueError("producer reconciliation face count does not match NPZ columns")
    if not math.isclose(float(arrays["time_end_s"][-1]), horizon_s, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("native source support must end exactly at the requested replay horizon")

    target = (
        target_rectangles_from_native_geometry(base_case, target_face_geometry_json)
        if target_face_geometry_json is not None
        else target_rectangles_from_case_inputs(base_case)
    )
    base_case_hashes = _case_input_hashes(base_case)
    source_manifest_sha256 = sha256_file(source_manifest_path)
    mapped_rates, uniform_rates = map_rates_to_target(
        arrays["source_water_volume_rate_m3_s"],
        arrays["source_face_bounds_xy_m"],
        arrays["source_face_areas_m2"],
        target["bounds_xy_m"],
        target["areas_m2"],
    )
    volume_by_source_step = (
        arrays["source_water_volume_rate_m3_s"].sum(axis=1) * arrays["delta_t_s"]
    )
    output_dir.mkdir(parents=True)
    source_archive = output_dir / "native-tank-flux-input.npz"
    source_sidecar = output_dir / "native-tank-flux-manifest.json"
    shutil.copy2(source_npz, source_archive)
    shutil.copy2(source_manifest_path, source_sidecar)
    if (
        sha256_file(source_archive) != manifest["source_npz_sha256"]
        or sha256_file(source_sidecar) != source_manifest_sha256
    ):
        raise ValueError("copied native source archive/manifest changed during preparation")
    copied_target_geometry: Path | None = None
    target_geometry_copy_provenance: dict[str, Any] | None = None
    if target_face_geometry_json is not None:
        copied_target_geometry = output_dir / "target-face-geometry.json"
        shutil.copy2(target_face_geometry_json, copied_target_geometry)
        if sha256_file(copied_target_geometry) != sha256_file(target_face_geometry_json):
            raise ValueError("copied native target face geometry changed during preparation")
        target_geometry_copy_provenance = {
            "source_path": str(target_face_geometry_json),
            "source_sha256": sha256_file(target_face_geometry_json),
            "bundle_copy": str(copied_target_geometry),
            "bundle_copy_sha256": sha256_file(copied_target_geometry),
            "schema": target.get("geometry_provenance", {}).get("geometry_schema"),
            "native_mesh_hashes": target.get("geometry_provenance", {}).get("native_mesh_hashes"),
        }
    step_diagnostics_path = output_dir / "replay-step-diagnostics.csv"
    write_step_diagnostics(
        step_diagnostics_path,
        start_s=arrays["time_start_s"],
        end_s=arrays["time_end_s"],
        delta_t_s=arrays["delta_t_s"],
        rates=mapped_rates,
        uniform_rates=uniform_rates,
        areas=target["areas_m2"],
    )
    candidates: dict[str, Any] = {}
    for name, rates in (("uniform", uniform_rates), ("uneven", mapped_rates)):
        case_dir = output_dir / name / "case"
        case_dir.parent.mkdir()
        _copy_base_case(base_case, case_dir)
        write_replay_table(
            case_dir / "system" / "dash8FluxReplayData",
            target["centers_x_m"],
            target["centers_y_m"],
            target["areas_m2"],
            arrays["time_start_s"],
            arrays["time_end_s"],
            rates,
        )
        u_path = case_dir / "0" / "U"
        u_text = u_path.read_text(encoding="utf-8")
        u_path.write_text(
            _replace_patch_dictionary(u_text, SOURCE_PATCH, coded_replay_boundary(field="U")),
            encoding="utf-8",
        )
        for scalar_field in ("k", "epsilon"):
            field_path = case_dir / "0" / scalar_field
            text = field_path.read_text(encoding="utf-8")
            field_path.write_text(
                _replace_patch_dictionary(
                    text, SOURCE_PATCH, coded_replay_boundary(field=scalar_field)
                ),
                encoding="utf-8",
            )
        inputs_path = case_dir / "case-inputs.json"
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        prior_reference = {
            key: inputs.pop(key)
            for key in (
                "analytic_expected_mass_kg",
                "analytic_expected_mass_by_source_kg",
                "analytic_expected_momentum_impulse_by_source_N_s",
                "analytic_uniform_reference_momentum_impulse_by_source_N_s",
                "source_histories",
                "inlet_profile",
            )
            if key in inputs
        }
        inputs["digitized_fig4_reference_not_replay"] = prior_reference
        inputs["horizon_s"] = horizon_s
        if isinstance(inputs.get("time_controls"), dict):
            inputs["time_controls"]["end_s"] = horizon_s
            if max_delta_t_s is not None:
                inputs["time_controls"]["max_delta_t_s"] = float(max_delta_t_s)
        inputs["evidence_label"] = (
            "exploratory one-way prescribed tank water-flux replay; "
            "not a Calbrix Figure 4 reproduction"
        )
        if isinstance(inputs.get("boundary_conditions"), dict):
            inputs["boundary_conditions"]["source_flow_sign"] = (
                "source face rates are signed along the downward -z normal; positive is water outflow"
            )
            inputs["boundary_conditions"]["source_profile"] = (
                "spatial profile replayed from native alphaPhi_ face-rate history of a separate "
                "provisional gravity-discharge tank pilot"
            )
        if isinstance(inputs.get("source_geometry_assumption"), dict):
            source_geometry_assumption = inputs["source_geometry_assumption"]
            source_geometry_assumption["source_profile"] = (
                "native gravity-tank discharge pattern replayed over the assumed opening; "
                "computed from a separate pilot, not published by Calbrix"
            )
            source_geometry_assumption["paper_profile_note"] = (
                "No spatial aperture profile is reported in the cited source; the replay is "
                "a numerical diagnostic using the project-assumed tank geometry/head."
            )
        inputs["inlet_profile"] = {
            "kind": f"native_tank_flux_replay_{name}",
            "native_source_run_id": manifest["source_run_id"],
            "native_source_rate_field": "alphaPhi_",
            "source_step_average_interpretation": REQUIRED_SOURCE_MANIFEST["rate_basis"],
            "coordinate_frame": REQUIRED_SOURCE_MANIFEST["coordinate_frame"],
            "positive_water_rate_direction": "downward -z; signed rates including backflow are preserved",
            "spatial_mapping": (
                "uniform total-rate control over the target opening"
                if name == "uniform"
                else "piecewise-constant native face rate density conservatively integrated over rectangular source-target overlaps"
            ),
            "target_interval_rule": "exact overlap-time integration of source step averages over each actual target [t-deltaT,t] interval",
            "target_face_count": int(target["areas_m2"].size),
            "target_face_area_m2": float(target["areas_m2"].sum()),
            "target_face_geometry": target.get("geometry_provenance"),
            "rate_array_sha256": sha256_file(source_archive),
            "source_npz_sha256": source_npz_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "volume_m3_from_native_step_averages": float(volume_by_source_step.sum()),
            "base_case_inlet_profile_not_replayed": prior_reference.get("inlet_profile"),
            "water_density_kg_m3": WATER_DENSITY_KG_M3,
            "phase_boundary": "alpha.water fixedValue 1 is inherited unchanged; solver alphaPhi_ must be measured after launch and is not assumed identical to prescribed velocity flux",
            "turbulence_boundary": "both cases use spatially uniform k and epsilon derived at each actual target step from the same native total-rate mean speed Q/S using assumed water I=0.05 and ell=0.05 m; the formula matches the existing standard k-epsilon boundary convention, but I and ell are project assumptions, not measured tank turbulence",
            "turbulence_intensity_assumption": 0.05,
            "turbulence_length_scale_assumption_m": 0.05,
            "turbulence_assumption_provenance": (
                "inherited project exploratory nearfield assumptions from the matched base-case "
                "record; not measured or paper-reported tank turbulence"
            ),
            "momentum_and_energy": replay_diagnostics(
                rates, target["areas_m2"], arrays["delta_t_s"]
            ),
        }
        inputs["tank_flux_replay"] = {
            "native_source_manifest_sha256": sha256_file(source_sidecar),
            "native_source_npz_sha256": sha256_file(source_archive),
            "source_areas_total_m2": float(arrays["source_face_areas_m2"].sum()),
            "source_face_count": int(arrays["source_face_areas_m2"].size),
            "source_step_count": int(arrays["time_end_s"].size),
            "total_prescribed_water_volume_m3": float(volume_by_source_step.sum()),
            "target_face_geometry": target.get("geometry_provenance"),
            "inherited_fig4_history_reference": prior_reference,
            "interpretation_limit": "The tank discharge shape is itself an exploratory gravity-pilot result under assumed tank geometry/head. Alpha=1 and downward velocity replay prescribe only a one-phase velocity flux; no pressure, tangential, turbulence, or two-fluid momentum handoff is reproduced.",
        }
        if max_delta_t_s is not None:
            inputs["tank_flux_replay"]["max_delta_t_s_override"] = float(max_delta_t_s)
        if target_geometry_copy_provenance is not None:
            inputs["tank_flux_replay"]["target_face_geometry_input"] = (
                target_geometry_copy_provenance
            )
        inputs_path.write_text(
            json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        control_path = case_dir / "system" / "controlDict"
        control_text = control_path.read_text(encoding="utf-8")
        control_text, count = re.subn(
            r"(?m)^endTime\s+[^;]+;", f"endTime {horizon_s:g};", control_text
        )
        if count != 1:
            raise ValueError("expected exactly one endTime entry in controlDict")
        if max_delta_t_s is not None:
            control_text, count = re.subn(
                r"(?m)^maxDeltaT\s+[^;]+;",
                f"maxDeltaT {float(max_delta_t_s):.16g};",
                control_text,
            )
            if count != 1:
                raise ValueError("expected exactly one maxDeltaT entry in controlDict")
        control_path.write_text(control_text, encoding="utf-8")
        candidates[name] = {
            "case_dir": str(case_dir),
            "case_input_hashes": _case_input_hashes(case_dir),
            "replay_table_sha256": sha256_file(case_dir / "system/dash8FluxReplayData"),
            "U_sha256": sha256_file(u_path),
            "alpha_sha256": sha256_file(case_dir / "0/alpha.water"),
            "k_sha256": sha256_file(case_dir / "0/k"),
            "epsilon_sha256": sha256_file(case_dir / "0/epsilon"),
            "control_dict_sha256": sha256_file(control_path),
            "case_inputs_sha256": sha256_file(inputs_path),
            "mapped_rate_sha256": hashlib.sha256(
                np.ascontiguousarray(rates).view(np.uint8)
            ).hexdigest(),
            "diagnostics": replay_diagnostics(rates, target["areas_m2"], arrays["delta_t_s"]),
        }
    # Cross-check that both candidate replay tables impose the same signed Q at
    # every native source interval and preserve the same k/epsilon assumptions.
    if not np.allclose(mapped_rates.sum(axis=1), uniform_rates.sum(axis=1), rtol=1e-10, atol=1e-12):
        raise AssertionError("uniform and uneven cases do not have identical total water rates")
    uniform_hashes = candidates["uniform"]["case_input_hashes"]
    uneven_hashes = candidates["uneven"]["case_input_hashes"]
    if uniform_hashes.keys() != uneven_hashes.keys():
        raise AssertionError("matched candidate input inventories differ")
    paired_case_hash_differences = sorted(
        path for path in uniform_hashes if uniform_hashes[path] != uneven_hashes[path]
    )
    record = {
        "schema": "dash8-native-tank-flux-replay-preparation-v1",
        "status": "prepared_no_solver_launch",
        "source_manifest": str(source_sidecar),
        "source_npz": str(source_archive),
        "source_manifest_sha256": sha256_file(source_sidecar),
        "source_npz_sha256": sha256_file(source_archive),
        "replay_step_diagnostics_csv": str(step_diagnostics_path),
        "replay_step_diagnostics_sha256": sha256_file(step_diagnostics_path),
        "source_producer_provenance": {
            key: manifest[key]
            for key in (
                "producer_script_path",
                "producer_script_sha256",
                "trace_builder_script_path",
                "trace_builder_script_sha256",
                "native_source_geometry",
                "time_series",
                "native_reconciliation",
                "native_case_path",
                "limitations",
            )
            if key in manifest
        },
        "repository": _git_provenance(),
        "code_provenance": _producer_provenance(),
        "base_case_input_hashes": base_case_hashes,
        "source_run_id": manifest["source_run_id"],
        "source_support_s": [0.0, float(arrays["time_end_s"][-1])],
        "source_steps": int(arrays["time_end_s"].size),
        "source_faces": int(arrays["source_face_areas_m2"].size),
        "target_base_case": str(base_case),
        "target_mesh_cells": int(
            json.loads((base_case / "case-inputs.json").read_text())["mesh_cells_expected"]
        ),
        "target_faces": int(target["areas_m2"].size),
        "target_area_m2": float(target["areas_m2"].sum()),
        "target_face_geometry_input": target_geometry_copy_provenance,
        "target_grid_shape_x_by_y": [
            int(target["centers_x_m"].size),
            int(target["centers_y_m"].size),
        ],
        "target_geometry_face_ids_sha256": (
            hashlib.sha256(np.ascontiguousarray(target["face_ids"]).view(np.uint8)).hexdigest()
            if "face_ids" in target
            else None
        ),
        "max_delta_t_s_override": max_delta_t_s,
        "uniform_vs_uneven_total_rate_max_abs_difference_m3_s": float(
            np.max(np.abs(mapped_rates.sum(axis=1) - uniform_rates.sum(axis=1)))
        ),
        "uniform_candidate": candidates["uniform"],
        "uneven_candidate": candidates["uneven"],
        "paired_case_hash_differences": paired_case_hash_differences,
        "matched_inputs_note": (
            f"Both cases copy the same {int(json.loads((base_case / 'case-inputs.json').read_text(encoding='utf-8'))['mesh_cells_expected'])}-cell nearfield base with {int(target['areas_m2'].size)} target opening faces. "
            "U rate tables differ only spatially while preserving signed total Q. k and epsilon are regenerated from the same total Q/S table using the fixed common 5%/0.05 m assumption. "
            "The alpha.water field and shared physical/numerical inputs are inherited; the declared horizon is 0.6 s."
            + (
                f" maxDeltaT is explicitly set to {float(max_delta_t_s):g} s to match the coarse replay pair."
                if max_delta_t_s is not None
                else ""
            )
        ),
        "limitations": [
            "The source tank geometry, fill/head, opening, gravity-pilot numerics, and resulting discharge are provisional assumptions/results; this is not a paper-prescribed inflow.",
            (
                f"The target source patch uses {int(target['areas_m2'].size)} rectangles. Conservative overlap preserves signed total rate but may reduce resolved face-to-face variance."
            ),
            "The velocity boundary has alpha.water=1 and zero tangential velocity; it does not reproduce two-fluid pressure, shear, entrainment, or full momentum handoff.",
            "The target solver's transported alphaPhi_ and water ledger are unmeasured until an actual nearfield run; prescribed velocity-rate conservation is not solver water-mass closure.",
        ],
    }
    record_path = output_dir / "preparation.json"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-case", type=Path, default=DEFAULT_BASE_CASE)
    parser.add_argument("--source-npz", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--horizon-s", type=float, default=0.6)
    parser.add_argument("--target-face-geometry-json", type=Path)
    parser.add_argument("--max-delta-t-s", type=float)
    args = parser.parse_args(argv)
    record = prepare_pair(
        base_case=args.base_case,
        source_npz=args.source_npz,
        source_manifest_path=args.source_manifest,
        output_dir=args.output_dir,
        horizon_s=args.horizon_s,
        target_face_geometry_json=args.target_face_geometry_json,
        max_delta_t_s=args.max_delta_t_s,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
