#!/usr/bin/env python3
"""Build native-polyhedral full-cell cloud envelopes for Calbrix comparisons.

The observer classifies cells at alpha.water >= 0.001 and 0.9, then uses each
selected native cell's vertex-derived AABB whenever it overlaps a fixed
streamwise or vertical slab. These are conservative bounding envelopes, not an
interpolated alpha isosurface or the paper's unpublished postprocessor. Water
volume always uses OpenFOAM cell volumes, never AABB products.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_native_vof import load_export  # noqa: E402

PAPER_PRIMARY_CSV = REPO_ROOT / "data/derived/calbrix_dash8_cloud_curves.csv"
PAPER_INDEPENDENT_CSV = REPO_ROOT / "data/derived/calbrix_dash8_cloud_curves_independent.csv"
PAPER_SOURCE_RECORD = REPO_ROOT / "experiments/E2_CALBRIX_SOURCE.md"
ALPHA_THRESHOLDS = (0.001, 0.9)
WATER_DENSITY_KG_M3 = 1000.0
DOMAIN_TOUCH_TOLERANCE_M = 1e-9
CENTROID_BOUND_TOLERANCE_M = 1e-10
DOMAIN_EXTENT_TOLERANCE_M = 1e-7
FIG9_TIME_SERIES = (
    {
        "time_s": 0.5,
        "time_label": "0.5",
        "primary_series_id": "dash8_t0.5s",
        "independent_series_id": "fig9_dash8_alpha0p001_t0p5s",
        "color_name": "red",
        "primary_color": "#a92f42",
        "independent_color": "#d6818e",
    },
    {
        "time_s": 1.0,
        "time_label": "1.0",
        "primary_series_id": "dash8_t1.0s",
        "independent_series_id": "fig9_dash8_alpha0p001_t1p0s",
        "color_name": "blue",
        "primary_color": "#174a8b",
        "independent_color": "#7fa6d1",
    },
    {
        "time_s": 1.5,
        "time_label": "1.5",
        "primary_series_id": "dash8_t1.5s",
        "independent_series_id": "fig9_dash8_alpha0p001_t1p5s",
        "color_name": "green",
        "primary_color": "#287a51",
        "independent_color": "#78b48f",
    },
)
SUPPORTED_PAPER_TRANSFORM = {
    "paper_streamwise_y_m": "mesh_x_m - source_origin_m[0]",
    "paper_downward_z_m": "source_plane_z_m - mesh_z_m",
    "paper_cross_track_x_m": "mesh_y_m - source_origin_m[1]",
}


@dataclass(frozen=True)
class CloudFrame:
    """Declared mesh-to-paper axes and provisional source registration."""

    source_origin_xyz_m: tuple[float, float, float]
    source_plane_z_m: float
    streamwise_source_bounds_m: tuple[float, float]
    source_area_m2: float
    l_characteristic_m: float
    domain_bounds_m: dict[str, tuple[float, float]]
    source_patch: str
    source_area_evidence: str
    paper_transform: dict[str, str]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


ANALYZER_SOURCE_PATH = Path(__file__).resolve()
ANALYZER_LOADED_SOURCE_SHA256 = sha256_file(ANALYZER_SOURCE_PATH)


def _analyzer_source_identity(source_path: Path, loaded_source_sha256: str) -> dict[str, Any]:
    """Distinguish imported code provenance from the source currently on disk."""
    on_disk_sha256 = sha256_file(source_path)
    return {
        "analyzer_loaded_source_sha256": loaded_source_sha256,
        "analyzer_on_disk_source_sha256": on_disk_sha256,
        "analyzer_source_unchanged_since_import": loaded_source_sha256 == on_disk_sha256,
    }


def _finite_vector(value: Any, count: int, label: str) -> tuple[float, ...]:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (count,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{label} must contain {count} finite values")
    return tuple(float(item) for item in array)


def frame_from_case_inputs(case_inputs: dict[str, Any], snapshot: dict[str, Any]) -> CloudFrame:
    """Read only declared source/frame data and check it against native export."""
    coordinate_frame = case_inputs.get("coordinate_frame")
    if not isinstance(coordinate_frame, dict):
        raise ValueError("case inputs need coordinate_frame metadata")
    paper_transform = coordinate_frame.get("paper_plot_transform")
    if not isinstance(paper_transform, dict):
        raise ValueError("case inputs do not declare the paper-coordinate transforms")
    declared_transform = {key: str(paper_transform.get(key)) for key in SUPPORTED_PAPER_TRANSFORM}
    if declared_transform != SUPPORTED_PAPER_TRANSFORM:
        raise ValueError(
            "declared paper-coordinate transforms do not match the supported mesh x/y/-z mapping"
        )

    origin_value = coordinate_frame.get("source_origin_m", case_inputs.get("source_origin_m"))
    origin = _finite_vector(origin_value, 3, "declared source-center origin")
    if "source_origin_m" in case_inputs:
        top_origin = _finite_vector(case_inputs["source_origin_m"], 3, "top-level source origin")
        if not np.array_equal(np.asarray(origin), np.asarray(top_origin)):
            raise ValueError("nested and top-level source origins disagree")
    plane_z = coordinate_frame.get("source_plane_z_m", case_inputs.get("source_plane_z_m"))
    if plane_z is None or not math.isfinite(float(plane_z)):
        raise ValueError("case inputs need a finite source plane z coordinate")
    if not math.isclose(float(plane_z), origin[2], rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("declared source plane z must equal the declared source-origin z")

    source_patch = str(snapshot["source_patch"])
    sources = case_inputs.get("source_geometry", {}).get("sources", [])
    matching = [source for source in sources if source.get("name") == source_patch]
    if len(matching) != 1:
        raise ValueError(
            "case inputs must contain exactly one source geometry for the exported patch"
        )
    source = matching[0]
    x_bounds = _finite_vector(source.get("bounds_m", {}).get("x"), 2, "source streamwise bounds")
    if x_bounds[1] <= x_bounds[0]:
        raise ValueError("streamwise source bounds must be increasing")
    y_bounds = _finite_vector(source.get("bounds_m", {}).get("y"), 2, "source cross-track bounds")
    if y_bounds[1] <= y_bounds[0]:
        raise ValueError("cross-track source bounds must be increasing")
    declared_center = np.asarray(
        [source.get("center_x_m"), source.get("center_y_m"), source.get("plane_z_m")],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(declared_center)) or not np.allclose(
        declared_center, np.asarray(origin), rtol=0.0, atol=1e-9
    ):
        raise ValueError("source_origin_m must match the configured source center and plane")

    area_map = case_inputs.get("source_patch_areas_m2", {})
    if source_patch not in area_map:
        raise ValueError("case inputs do not declare source patch area")
    area = float(area_map[source_patch])
    source_area = float(source.get("area_m2", area))
    native_area = float(snapshot["topology"]["source_patch_area_m2"])
    if (
        not math.isfinite(area)
        or area <= 0
        or not math.isclose(area, source_area, rel_tol=1e-9, abs_tol=1e-12)
        or not math.isclose(area, native_area, rel_tol=1e-8, abs_tol=1e-10)
    ):
        raise ValueError("declared, geometry-record and native source areas do not agree")

    raw_domain = case_inputs.get("domain_bounds_m")
    if not isinstance(raw_domain, dict):
        raise ValueError("case inputs need domain_bounds_m")
    domain = {
        axis: _finite_vector(raw_domain.get(axis), 2, f"domain {axis} bounds") for axis in "xyz"
    }
    if any(bounds[1] <= bounds[0] for bounds in domain.values()):
        raise ValueError("domain bounds must be increasing")
    source_area_evidence = str(
        case_inputs.get("source_geometry_assumption", {}).get(
            "evidence_class", "not classified in case inputs"
        )
    )
    return CloudFrame(
        source_origin_xyz_m=origin,
        source_plane_z_m=float(plane_z),
        streamwise_source_bounds_m=(float(x_bounds[0]), float(x_bounds[1])),
        source_area_m2=area,
        l_characteristic_m=math.sqrt(area),
        domain_bounds_m=domain,
        source_patch=source_patch,
        source_area_evidence=source_area_evidence,
        paper_transform=declared_transform,
    )


def _station_edges(low: float, high: float, spacing_m: float) -> NDArray[np.float64]:
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("station spacing must be positive and finite")
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        raise ValueError("station domain must have finite increasing bounds")
    first = math.floor(low / spacing_m)
    last = math.ceil(high / spacing_m)
    edges = np.arange(first, last + 1, dtype=np.float64) * spacing_m
    if len(edges) < 2:
        raise ValueError("station grid needs at least one slab")
    return edges


def _span_statistics(spans: NDArray[np.float64]) -> tuple[float | None, float | None, float | None]:
    if len(spans) == 0:
        return None, None, None
    return float(np.min(spans)), float(np.median(spans)), float(np.max(spans))


def _domain_contacts(
    bounds: NDArray[np.float64], indices: NDArray[np.int64], frame: CloudFrame
) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for axis_index, axis in enumerate("xyz"):
        domain_low, domain_high = frame.domain_bounds_m[axis]
        cell_low = bounds[indices, axis_index]
        cell_high = bounds[indices, axis_index + 3]
        flags[f"touch_mesh_{axis}_min"] = bool(
            len(indices) and np.any(cell_low <= domain_low + DOMAIN_TOUCH_TOLERANCE_M)
        )
        flags[f"touch_mesh_{axis}_max"] = bool(
            len(indices) and np.any(cell_high >= domain_high - DOMAIN_TOUCH_TOLERANCE_M)
        )
    return flags


def _center_bin_indices(
    relative_centres: NDArray[np.float64], edges: NDArray[np.float64]
) -> NDArray[np.int64]:
    bins = np.searchsorted(edges, relative_centres, side="right") - 1
    bins[relative_centres == edges[-1]] = len(edges) - 2
    if np.any((bins < 0) | (bins >= len(edges) - 1)):
        raise ValueError("a cell center lies outside the declared profile station grid")
    return bins.astype(np.int64, copy=False)


def _penetration_rows(
    snapshot: dict[str, Any],
    frame: CloudFrame,
    threshold: float,
    spacing_m: float,
    origin_choice: str,
    origin_x_m: float,
) -> list[dict[str, Any]]:
    alpha = np.asarray(snapshot["alpha_water"], dtype=np.float64)
    volumes = np.asarray(snapshot["cell_volumes_m3"], dtype=np.float64)
    centres = np.asarray(snapshot["cell_centres_xyz_m"], dtype=np.float64)
    bounds = np.asarray(snapshot["cell_bounds_minmax_xyz_m"], dtype=np.float64)
    selected = alpha >= threshold
    center_origin_x = frame.source_origin_xyz_m[0]
    center_relative_low = bounds[:, 0] - center_origin_x
    center_relative_high = bounds[:, 3] - center_origin_x
    center_relative_edges = _station_edges(
        min(center_relative_low), max(center_relative_high), spacing_m
    )
    physical_edges = center_relative_edges + center_origin_x
    paper_edges = physical_edges - origin_x_m
    center_bins = _center_bin_indices(centres[:, 0], physical_edges)
    rows = []
    for bin_index, (x_low, x_high, slab_low, slab_high) in enumerate(
        zip(physical_edges[:-1], physical_edges[1:], paper_edges[:-1], paper_edges[1:], strict=True)
    ):
        overlaps = selected & (bounds[:, 0] < x_high) & (bounds[:, 3] > x_low)
        hit_indices = np.flatnonzero(overlaps)
        center_indices = np.flatnonzero(selected & (center_bins == bin_index))
        if len(hit_indices):
            front = frame.source_plane_z_m - float(np.min(bounds[hit_indices, 2]))
            x_span = bounds[hit_indices, 3] - bounds[hit_indices, 0]
            z_span = bounds[hit_indices, 5] - bounds[hit_indices, 2]
            x_min, x_median, x_max = _span_statistics(x_span)
            z_min, z_median, z_max = _span_statistics(z_span)
        else:
            front = None
            x_min = x_median = x_max = None
            z_min = z_median = z_max = None
        water_volume = float(
            np.sum(alpha[center_indices] * volumes[center_indices], dtype=np.float64)
        )
        row: dict[str, Any] = {
            "time_s": float(snapshot["time_value_s"]),
            "alpha_threshold": threshold,
            "station_spacing_m": spacing_m,
            "origin_choice": origin_choice,
            "registration_origin_mesh_x_m": origin_x_m,
            "mesh_x_slab_low_m": float(x_low),
            "mesh_x_slab_high_m": float(x_high),
            "paper_streamwise_slab_low_m": float(slab_low),
            "paper_streamwise_slab_high_m": float(slab_high),
            "paper_streamwise_station_center_m": float((slab_low + slab_high) / 2),
            "aabb_overlap_cell_count": int(len(hit_indices)),
            "center_assigned_cell_count": int(len(center_indices)),
            "aabb_envelope_downward_front_m": front,
            "center_assigned_native_water_volume_m3": water_volume,
            "center_assigned_native_water_mass_kg": water_volume * WATER_DENSITY_KG_M3,
            "aabb_streamwise_span_min_m": x_min,
            "aabb_streamwise_span_median_m": x_median,
            "aabb_streamwise_span_max_m": x_max,
            "aabb_vertical_span_min_m": z_min,
            "aabb_vertical_span_median_m": z_median,
            "aabb_vertical_span_max_m": z_max,
            "envelope_observer": "selected full-cell AABBs with positive streamwise slab overlap; front uses source_plane_z - minimum native cell z bound",
            "volume_observer": "selected-cell alpha.water * native OpenFOAM volume, assigned by native cell center to exactly one slab; no AABB volume product or partial-cell reconstruction",
        }
        row.update(_domain_contacts(bounds, hit_indices, frame))
        rows.append(row)
    return rows


def _width_rows(
    snapshot: dict[str, Any], frame: CloudFrame, threshold: float, spacing_m: float
) -> list[dict[str, Any]]:
    alpha = np.asarray(snapshot["alpha_water"], dtype=np.float64)
    volumes = np.asarray(snapshot["cell_volumes_m3"], dtype=np.float64)
    centres = np.asarray(snapshot["cell_centres_xyz_m"], dtype=np.float64)
    bounds = np.asarray(snapshot["cell_bounds_minmax_xyz_m"], dtype=np.float64)
    selected = alpha >= threshold
    depth_low = frame.source_plane_z_m - bounds[:, 5]
    depth_high = frame.source_plane_z_m - bounds[:, 2]
    edges = _station_edges(min(depth_low), max(depth_high), spacing_m)
    center_depth = frame.source_plane_z_m - centres[:, 2]
    center_bins = _center_bin_indices(center_depth, edges)
    origin_y = frame.source_origin_xyz_m[1]
    rows = []
    for bin_index, (slab_low, slab_high) in enumerate(zip(edges[:-1], edges[1:], strict=True)):
        overlaps = selected & (depth_low < slab_high) & (depth_high > slab_low)
        hit_indices = np.flatnonzero(overlaps)
        center_indices = np.flatnonzero(selected & (center_bins == bin_index))
        if len(hit_indices):
            cross_low = float(np.min(bounds[hit_indices, 1] - origin_y))
            cross_high = float(np.max(bounds[hit_indices, 4] - origin_y))
            width = cross_high - cross_low
            z_span = bounds[hit_indices, 5] - bounds[hit_indices, 2]
            y_span = bounds[hit_indices, 4] - bounds[hit_indices, 1]
            z_min, z_median, z_max = _span_statistics(z_span)
            y_min, y_median, y_max = _span_statistics(y_span)
        else:
            cross_low = cross_high = width = None
            z_min = z_median = z_max = None
            y_min = y_median = y_max = None
        water_volume = float(
            np.sum(alpha[center_indices] * volumes[center_indices], dtype=np.float64)
        )
        row: dict[str, Any] = {
            "time_s": float(snapshot["time_value_s"]),
            "alpha_threshold": threshold,
            "station_spacing_m": spacing_m,
            "registration_choice": "source_center_cross_track_and_source_plane_vertical",
            "paper_downward_depth_slab_low_m": float(slab_low),
            "paper_downward_depth_slab_high_m": float(slab_high),
            "paper_downward_depth_station_center_m": float((slab_low + slab_high) / 2),
            "aabb_overlap_cell_count": int(len(hit_indices)),
            "center_assigned_cell_count": int(len(center_indices)),
            "paper_cross_track_lower_m": cross_low,
            "paper_cross_track_upper_m": cross_high,
            "aabb_envelope_width_m": width,
            "conditional_Lc_m": frame.l_characteristic_m,
            "conditional_depth_over_Lc": float(
                (slab_low + slab_high) / (2 * frame.l_characteristic_m)
            ),
            "conditional_width_over_Lc": width / frame.l_characteristic_m
            if width is not None
            else None,
            "center_assigned_native_water_volume_m3": water_volume,
            "center_assigned_native_water_mass_kg": water_volume * WATER_DENSITY_KG_M3,
            "aabb_vertical_span_min_m": z_min,
            "aabb_vertical_span_median_m": z_median,
            "aabb_vertical_span_max_m": z_max,
            "aabb_transverse_span_min_m": y_min,
            "aabb_transverse_span_median_m": y_median,
            "aabb_transverse_span_max_m": y_max,
            "envelope_observer": "selected full-cell AABBs with positive downward-depth slab overlap; width is maximum cross-track bound minus minimum cross-track bound",
            "volume_observer": "selected-cell alpha.water * native OpenFOAM volume, assigned by native cell center to exactly one slab; no AABB volume product or partial-cell reconstruction",
        }
        row.update(_domain_contacts(bounds, hit_indices, frame))
        rows.append(row)
    return rows


def extract_profiles(
    snapshot: dict[str, Any], frame: CloudFrame, station_spacing_m: float = 0.075
) -> dict[str, Any]:
    """Extract the requested grid plus fixed 0.15 m station sensitivity."""
    alpha = np.asarray(snapshot["alpha_water"], dtype=np.float64)
    volumes = np.asarray(snapshot["cell_volumes_m3"], dtype=np.float64)
    centres = np.asarray(snapshot["cell_centres_xyz_m"], dtype=np.float64)
    bounds = np.asarray(snapshot["cell_bounds_minmax_xyz_m"], dtype=np.float64)
    n_cells = len(alpha)
    if (
        alpha.shape != (n_cells,)
        or volumes.shape != (n_cells,)
        or centres.shape != (n_cells, 3)
        or bounds.shape != (n_cells, 6)
        or not np.all(np.isfinite(alpha))
        or not np.all(np.isfinite(volumes))
        or not np.all(np.isfinite(centres))
        or not np.all(np.isfinite(bounds))
        or np.any(volumes <= 0)
        or np.any(alpha < -1e-12)
        or np.any(alpha > 1 + 1e-12)
        or np.any(bounds[:, :3] >= bounds[:, 3:])
    ):
        raise ValueError(
            "native alpha, volume, center or cell-bound arrays failed integrity checks"
        )
    centroid_outside = np.maximum(bounds[:, :3] - centres, centres - bounds[:, 3:])
    centroid_outside = np.maximum(centroid_outside, 0.0)
    if np.any(centroid_outside > CENTROID_BOUND_TOLERANCE_M):
        count = int(np.any(centroid_outside > CENTROID_BOUND_TOLERANCE_M, axis=1).sum())
        maximum = float(np.max(centroid_outside))
        raise ValueError(
            f"native cell centroids lie outside their vertex AABBs: {count} cells, "
            f"maximum violation {maximum:g} m"
        )
    spacings = [float(station_spacing_m)]
    if not math.isclose(station_spacing_m, 0.15, rel_tol=0.0, abs_tol=1e-15):
        spacings.append(0.15)
    origin_variants = [
        ("source_center", frame.source_origin_xyz_m[0]),
        ("upstream_source_edge", frame.streamwise_source_bounds_m[0]),
        ("downstream_source_edge", frame.streamwise_source_bounds_m[1]),
    ]
    penetration_rows: list[dict[str, Any]] = []
    width_rows: list[dict[str, Any]] = []
    threshold_summary = {}
    for threshold in ALPHA_THRESHOLDS:
        selected = alpha >= threshold
        exact_water_volume = float(np.sum(alpha[selected] * volumes[selected], dtype=np.float64))
        threshold_summary[f"{threshold:g}"] = {
            "selected_cell_count": int(np.count_nonzero(selected)),
            "selected_native_water_volume_m3": exact_water_volume,
            "selected_native_water_mass_kg": exact_water_volume * WATER_DENSITY_KG_M3,
            "selected_full_cell_volume_m3": float(np.sum(volumes[selected], dtype=np.float64)),
        }
        for spacing in spacings:
            for origin_choice, origin_x in origin_variants:
                penetration_rows.extend(
                    _penetration_rows(snapshot, frame, threshold, spacing, origin_choice, origin_x)
                )
            width_rows.extend(_width_rows(snapshot, frame, threshold, spacing))
    selected_all = alpha >= ALPHA_THRESHOLDS[0]
    center_of_volume = float(np.sum(alpha[selected_all] * volumes[selected_all], dtype=np.float64))
    if not math.isclose(
        center_of_volume,
        threshold_summary["0.001"]["selected_native_water_volume_m3"],
        rel_tol=0,
        abs_tol=1e-14,
    ):
        raise AssertionError("native-volume summary changed during profile extraction")
    return {
        "penetration_rows": penetration_rows,
        "width_rows": width_rows,
        "threshold_summary": threshold_summary,
        "all_cell_water_volume_m3": float(np.sum(alpha * volumes, dtype=np.float64)),
        "alpha_min_raw": float(np.min(alpha)) if len(alpha) else None,
        "alpha_max_raw": float(np.max(alpha)) if len(alpha) else None,
        "alpha_values_clipped": False,
        "geometry_integrity": {
            "centroid_outside_aabb_cell_count": 0,
            "centroid_aabb_tolerance_m": CENTROID_BOUND_TOLERANCE_M,
        },
        "station_spacings_m": spacings,
        "origin_variants": [
            {
                "choice": key,
                "mesh_x_origin_m": value,
                "paper_y_transform": f"mesh x - {value:.12g} m",
            }
            for key, value in origin_variants
        ],
    }


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader), list(reader.fieldnames)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _paper_series(
    primary_rows: list[dict[str, str]],
    independent_rows: list[dict[str, str]],
    snapshot_time_s: float = 1.0,
) -> dict[str, list[dict[str, str]]]:
    fig9_spec = _fig9_series_spec(snapshot_time_s)
    return {
        "fig6_primary": [
            row
            for row in primary_rows
            if row.get("figure") == "6"
            and row.get("series_id") == "dash8_t0.5s"
            and row.get("time_s") == "0.5"
            and row.get("alpha_l_threshold") == "0.001"
        ],
        "fig6_independent": [
            row
            for row in independent_rows
            if row.get("figure") == "Fig. 6(b)" and row.get("series") == "dash8_alpha0p001"
        ],
        "fig9_primary": [
            row
            for row in primary_rows
            if fig9_spec is not None
            and row.get("figure") == "9"
            and row.get("series_id") == fig9_spec["primary_series_id"]
            and row.get("time_s") == fig9_spec["time_label"]
            and row.get("alpha_l_threshold") == "0.001"
        ],
        "fig9_independent": [
            row
            for row in independent_rows
            if row.get("figure") == "Fig. 9(a)"
            and fig9_spec is not None
            and row.get("series") == fig9_spec["independent_series_id"]
        ],
    }


def _fig9_series_spec(snapshot_time_s: float) -> dict[str, Any] | None:
    """Return the reported Fig. 9 time series matching a native snapshot."""
    if not math.isfinite(snapshot_time_s):
        return None
    for series in FIG9_TIME_SERIES:
        if math.isclose(snapshot_time_s, series["time_s"], rel_tol=0.0, abs_tol=1e-9):
            return series
    return None


def _validate_axis_declaration(
    rows: list[dict[str, str]],
    *,
    x_variable_field: str,
    expected_x_variable: str,
    y_variable_field: str,
    expected_y_variable: str,
    x_unit_field: str,
    expected_x_unit: str,
    y_unit_field: str,
    expected_y_unit: str,
    label: str,
) -> None:
    if not rows:
        raise ValueError(f"{label} digitization is empty")
    declarations = {
        x_variable_field: ({row[x_variable_field] for row in rows}, expected_x_variable),
        y_variable_field: ({row[y_variable_field] for row in rows}, expected_y_variable),
        x_unit_field: ({row[x_unit_field] for row in rows}, expected_x_unit),
        y_unit_field: ({row[y_unit_field] for row in rows}, expected_y_unit),
    }
    for field, (actual, expected) in declarations.items():
        if actual != {expected}:
            raise ValueError(
                f"{label} has incompatible {field} declaration: "
                f"expected only {expected!r}, found {sorted(actual)!r}"
            )


def _plot_digital_groups(
    axis: Any,
    rows: list[dict[str, str]],
    *,
    source: str,
    color: str,
    x_key: str,
    y_key: str,
    x_error_key: str,
    y_error_key: str,
    group_keys: tuple[str, ...],
    point_key: str | None,
) -> None:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[key] for key in group_keys), []).append(row)
    label_used = False
    for group in grouped.values():
        if point_key:
            group.sort(key=lambda row: int(row[point_key]))
        x = np.asarray([float(row[x_key]) for row in group])
        y = np.asarray([float(row[y_key]) for row in group])
        if len(x) > 1:
            axis.plot(
                x,
                y,
                color=color,
                linewidth=0.8,
                alpha=0.65,
                label=source if not label_used else None,
            )
        axis.errorbar(
            x,
            y,
            xerr=np.asarray([float(row[x_error_key]) for row in group]),
            yerr=np.asarray([float(row[y_error_key]) for row in group]),
            fmt=".",
            color=color,
            markersize=1.3,
            elinewidth=0.25,
            capsize=0,
            alpha=0.18,
            label=source if not label_used and len(x) == 1 else None,
        )
        label_used = True


def _plot_fig9_independent(
    axis: Any,
    rows: list[dict[str, str]],
    *,
    source: str = "Independent raster read, t=1 s",
    color: str = "#7fa6d1",
) -> None:
    """Plot independent Fig. 9 x=L/Lc, y=z/Lc reads on depth/width axes."""
    _validate_axis_declaration(
        rows,
        x_variable_field="x_variable",
        expected_x_variable="normalized_lateral_expansion_L_over_Lc",
        y_variable_field="y_variable",
        expected_y_variable="normalized_vertical_distance_z_over_Lc",
        x_unit_field="x_unit",
        expected_x_unit="1",
        y_unit_field="y_unit",
        expected_y_unit="1",
        label="Independent Fig. 9(a)",
    )
    # The CSV's x is width and y is depth, while the figure axes are depth then
    # width. Swap both data columns and their corresponding read bounds.
    _plot_digital_groups(
        axis,
        rows,
        source=source,
        color=color,
        x_key="y_value",
        y_key="x_value",
        x_error_key="read_bound_y",
        y_error_key="read_bound_x",
        group_keys=("segment",),
        point_key=None,
    )


def _validate_paper_axes(paper: dict[str, list[dict[str, str]]]) -> None:
    _validate_axis_declaration(
        paper["fig6_primary"],
        x_variable_field="independent_variable",
        expected_x_variable="y",
        y_variable_field="dependent_variable",
        expected_y_variable="Z",
        x_unit_field="independent_unit",
        expected_x_unit="m",
        y_unit_field="dependent_unit",
        expected_y_unit="m",
        label="Primary Fig. 6(b)",
    )
    _validate_axis_declaration(
        paper["fig6_independent"],
        x_variable_field="x_variable",
        expected_x_variable="streamwise_distance_y",
        y_variable_field="y_variable",
        expected_y_variable="vertical_penetration_Z",
        x_unit_field="x_unit",
        expected_x_unit="m",
        y_unit_field="y_unit",
        expected_y_unit="m",
        label="Independent Fig. 6(b)",
    )
    if bool(paper["fig9_primary"]) != bool(paper["fig9_independent"]):
        raise ValueError("primary and independent Fig. 9 digitizations must select the same time")
    if paper["fig9_primary"]:
        _validate_axis_declaration(
            paper["fig9_primary"],
            x_variable_field="independent_variable",
            expected_x_variable="z_over_Lc",
            y_variable_field="dependent_variable",
            expected_y_variable="L_over_Lc",
            x_unit_field="independent_unit",
            expected_x_unit="1",
            y_unit_field="dependent_unit",
            expected_y_unit="1",
            label="Primary Fig. 9(a)",
        )
        _validate_axis_declaration(
            paper["fig9_independent"],
            x_variable_field="x_variable",
            expected_x_variable="normalized_lateral_expansion_L_over_Lc",
            y_variable_field="y_variable",
            expected_y_variable="normalized_vertical_distance_z_over_Lc",
            x_unit_field="x_unit",
            expected_x_unit="1",
            y_unit_field="y_unit",
            expected_y_unit="1",
            label="Independent Fig. 9(a)",
        )


def _native_contiguous_groups(
    rows: list[dict[str, Any]], x_key: str, y_key: str
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda value: float(value[x_key])):
        if row[y_key] is None:
            if current:
                groups.append(current)
                current = []
        else:
            current.append(row)
    if current:
        groups.append(current)
    return groups


def make_comparison_plot(
    output_path: Path,
    snapshot: dict[str, Any],
    profiles: dict[str, Any],
    paper: dict[str, list[dict[str, str]]],
    frame: CloudFrame,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    time_s = float(snapshot["time_value_s"])
    fig9_spec = _fig9_series_spec(time_s)
    primary_spacing = profiles["station_spacings_m"][0]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.4), constrained_layout=True)
    ax = axes[0]
    _plot_digital_groups(
        ax,
        paper["fig6_primary"],
        source="Paper Fig. 6(b), primary raster, t=0.5 s",
        color="#174a8b",
        x_key="independent_value",
        y_key="dependent_value",
        x_error_key="read_bound_independent",
        y_error_key="read_bound_dependent",
        group_keys=("segment_id", "branch_id"),
        point_key="point_index",
    )
    _plot_digital_groups(
        ax,
        paper["fig6_independent"],
        source="Independent raster read, t=0.5 s",
        color="#7fa6d1",
        x_key="x_value",
        y_key="y_value",
        x_error_key="read_bound_x",
        y_error_key="read_bound_y",
        group_keys=("segment",),
        point_key=None,
    )
    if math.isclose(time_s, 0.5, rel_tol=0.0, abs_tol=1e-9):
        origin_styles = {
            "source_center": ("#d1495b", "-"),
            "upstream_source_edge": ("#edae49", "--"),
            "downstream_source_edge": ("#00798c", ":"),
        }
        for origin_name, (color, style) in origin_styles.items():
            selected = [
                row
                for row in profiles["penetration_rows"]
                if row["alpha_threshold"] == 0.001
                and row["station_spacing_m"] == primary_spacing
                and row["origin_choice"] == origin_name
            ]
            for group in _native_contiguous_groups(
                selected, "paper_streamwise_station_center_m", "aabb_envelope_downward_front_m"
            ):
                ax.plot(
                    [row["paper_streamwise_station_center_m"] for row in group],
                    [row["aabb_envelope_downward_front_m"] for row in group],
                    color=color,
                    linestyle=style,
                    linewidth=1.1,
                    label=f"Native full-cell envelope: {origin_name.replace('_', ' ')}",
                )
    else:
        ax.text(
            0.03,
            0.04,
            f"Native export is t={time_s:g} s; no time-mismatched native curve shown.",
            transform=ax.transAxes,
            fontsize=8,
            va="bottom",
        )
    ax.set_title("Fig. 6(b): vertical penetration at t=0.5 s")
    ax.set_xlabel("Paper streamwise y (m); native registration alternatives are explicit")
    ax.set_ylabel("Downward front Z (m)")
    ax.grid(True, linewidth=0.3, alpha=0.4)
    ax.legend(fontsize=7, loc="best")

    ax = axes[1]
    if fig9_spec is not None:
        _plot_digital_groups(
            ax,
            paper["fig9_primary"],
            source=(f"Paper Fig. 9(a), {fig9_spec['color_name']} primary raster, t={time_s:g} s"),
            color=fig9_spec["primary_color"],
            x_key="independent_value",
            y_key="dependent_value",
            x_error_key="read_bound_independent",
            y_error_key="read_bound_dependent",
            group_keys=("segment_id", "branch_id"),
            point_key="point_index",
        )
        _plot_fig9_independent(
            ax,
            paper["fig9_independent"],
            source=f"Independent raster read, t={time_s:g} s",
            color=fig9_spec["independent_color"],
        )
    if fig9_spec is not None and math.isclose(
        time_s, fig9_spec["time_s"], rel_tol=0.0, abs_tol=1e-9
    ):
        for threshold, color, style, label in (
            (0.001, "#d1495b", "-", "Native AABB envelope alpha >= 0.001"),
            (0.9, "#555555", "--", "Native AABB envelope alpha >= 0.9 (core observer)"),
        ):
            selected = [
                row
                for row in profiles["width_rows"]
                if row["alpha_threshold"] == threshold
                and row["station_spacing_m"] == primary_spacing
            ]
            for group in _native_contiguous_groups(
                selected, "conditional_depth_over_Lc", "conditional_width_over_Lc"
            ):
                ax.plot(
                    [row["conditional_depth_over_Lc"] for row in group],
                    [row["conditional_width_over_Lc"] for row in group],
                    color=color,
                    linestyle=style,
                    linewidth=1.2,
                    label=label,
                )
        if math.isclose(time_s, 0.5, rel_tol=0.0, abs_tol=1e-9):
            depth = np.linspace(0.0, 8.0, 201)
            ax.plot(
                depth,
                0.07 * depth**2,
                color="#111111",
                linestyle="-.",
                linewidth=1.0,
                label="Eq. (6), Table 3 correlation at 0.5 s: 0.07(z/Lc)^2",
            )
    else:
        ax.text(
            0.03,
            0.04,
            f"Native export is t={time_s:g} s; no time-mismatched native curve shown.",
            transform=ax.transAxes,
            fontsize=8,
            va="bottom",
        )
    ax.set_title(
        "Fig. 9(a): lateral width" + (f" at t={time_s:g} s" if fig9_spec else " (digitized series)")
    )
    ax.set_xlabel("Downward depth z/Lc")
    ax.set_ylabel("Cross-track width L/Lc")
    ax.grid(True, linewidth=0.3, alpha=0.4)
    ax.legend(fontsize=7, loc="best")

    fig.suptitle(
        f"Dash-8 cloud envelopes; native alpha AABB slabs at {time_s:g} s\n"
        f"Lc = sqrt(case-declared S={frame.source_area_m2:g} m²) = {frame.l_characteristic_m:.4g} m (conditional; paper S unknown)",
        fontsize=10,
    )
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _export_attempt_provenance(
    export_dir: Path, case_inputs_path: Path, snapshot: dict[str, Any]
) -> dict[str, Any]:
    attempt_path = export_dir.parent / "export_attempt.json"
    if not attempt_path.is_file():
        return {"status": "no adjacent export_attempt.json; sealing provenance not verified"}
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    if (
        attempt.get("status") != "complete"
        or attempt.get("return_code") != 0
        or not attempt.get("input_hashes_unchanged")
    ):
        raise ValueError(
            "adjacent native export attempt is not complete or does not certify unchanged inputs"
        )
    requested = float(attempt["selected_time_requested"])
    if not math.isclose(requested, float(snapshot["time_value_s"]), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("native export time does not match its export-attempt record")
    declared_case = Path(attempt["case_directory"]).resolve()
    if declared_case != case_inputs_path.resolve().parent:
        raise ValueError("case-inputs file is not from the native export attempt's source case")
    return {
        "status": "complete",
        "record_path": str(attempt_path),
        "record_sha256": sha256_file(attempt_path),
        "selected_time_requested": attempt["selected_time_requested"],
        "case_directory": str(declared_case),
        "image_id": attempt.get("image_id"),
        "input_hashes_unchanged": bool(attempt.get("input_hashes_unchanged")),
        "native_export_cpu_limit": attempt.get("cpu_limit"),
        "native_export_memory_limit": attempt.get("memory_limit"),
    }


def _validate_native_domain(
    snapshot: dict[str, Any], frame: CloudFrame
) -> dict[str, tuple[float, float]]:
    bounds = np.asarray(snapshot["cell_bounds_minmax_xyz_m"], dtype=np.float64)
    if bounds.ndim != 2 or bounds.shape[1] != 6 or len(bounds) == 0:
        raise ValueError("native export has invalid or empty cell AABB bounds")
    if not np.all(np.isfinite(bounds)) or np.any(bounds[:, :3] >= bounds[:, 3:]):
        raise ValueError("native export cell AABB bounds are non-finite or degenerate")
    actual_bounds = {
        axis: (float(np.min(bounds[:, index])), float(np.max(bounds[:, index + 3])))
        for index, axis in enumerate("xyz")
    }
    for axis in "xyz":
        if not np.allclose(
            actual_bounds[axis],
            frame.domain_bounds_m[axis],
            rtol=0.0,
            atol=DOMAIN_EXTENT_TOLERANCE_M,
        ):
            raise ValueError(f"native mesh {axis} bounds do not match declared case domain")
    return actual_bounds


def analyze(
    export_dir: Path,
    case_inputs_path: Path,
    output_dir: Path,
    station_spacing_m: float = 0.075,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    snapshot, export_hashes = load_export(export_dir)
    case_inputs_bytes = case_inputs_path.read_bytes()
    case_inputs = json.loads(case_inputs_bytes)
    frame = frame_from_case_inputs(case_inputs, snapshot)
    actual_bounds = _validate_native_domain(snapshot, frame)
    case_provenance = _export_attempt_provenance(export_dir, case_inputs_path, snapshot)
    exporter_source_path = export_dir.parent / "buildsrc/exportNativeVof.C"
    primary_rows, _ = _read_csv(PAPER_PRIMARY_CSV)
    independent_rows, _ = _read_csv(PAPER_INDEPENDENT_CSV)
    time_s = float(snapshot["time_value_s"])
    fig9_spec = _fig9_series_spec(time_s)
    paper = _paper_series(primary_rows, independent_rows, time_s)
    if not paper["fig6_primary"] or not paper["fig6_independent"]:
        raise ValueError("required Fig. 6(b) t=0.5 digitized series is missing")
    if fig9_spec is not None and (not paper["fig9_primary"] or not paper["fig9_independent"]):
        raise ValueError(f"required Fig. 9(a) t={time_s:g} digitized series is missing")
    _validate_paper_axes(paper)
    profiles = extract_profiles(snapshot, frame, station_spacing_m)
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(output_dir / "penetration_profiles.csv", profiles["penetration_rows"])
    _write_csv(output_dir / "width_profiles.csv", profiles["width_rows"])
    (output_dir / "native_export_hashes.json").write_text(
        json.dumps(export_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    figure_path = output_dir / "paper_cloud_comparison.png"
    make_comparison_plot(figure_path, snapshot, profiles, paper, frame)
    report = {
        "schema_version": 1,
        "classification": "Exploratory native polyhedral bounding-envelope comparison; not a paper-detector reproduction or E2 validation.",
        "observer": {
            "thresholds": list(ALPHA_THRESHOLDS),
            "geometry": "Each selected cell is its full vertex-derived axis-aligned AABB. A cell contributes to each slab with positive AABB overlap. The front/width are conservative full-cell bounds; nonconforming and polyhedral cells are not forced onto a Cartesian grid.",
            "water_volume": "sum(alpha.water * native OpenFOAM cell volume); no AABB products, subcell interpolation, clipping, or per-slab partial-cell reconstruction. Profile water volume is assigned by native cell center, so it partitions exact native selected-cell alpha*V but is not a partial-cell overlap integral.",
            "empty_slabs": "The grid spans the full declared domain for every origin variant; rows with no selected AABB overlap remain present with null envelope and zero center-assigned volume.",
            "resolution": "Rows report min/median/max AABB spans along measured axes; these are bounding-box resolution indicators, not isotropic cell sizes.",
            "domain_contact": f"A selected bounding cell is flagged at a declared mesh-domain face if its bound is within {DOMAIN_TOUCH_TOLERANCE_M:g} m of that face.",
            "alpha_integrity": "Raw alpha values are retained; values are never clipped or altered.",
        },
        "snapshot": {
            "time_name": snapshot["time_name"],
            "time_value_s": float(snapshot["time_value_s"]),
            "native_cell_count": int(len(snapshot["alpha_water"])),
            "rank_count": int(snapshot["topology"]["rank_count"]),
            "source_patch": frame.source_patch,
            "source_face_count": int(snapshot["topology"]["source_boundary_face_count"]),
            "source_patch_area_native_m2": float(snapshot["topology"]["source_patch_area_m2"]),
            "geometry_integrity": profiles["geometry_integrity"],
            "alpha_min_raw": profiles["alpha_min_raw"],
            "alpha_max_raw": profiles["alpha_max_raw"],
            "alpha_values_clipped": profiles["alpha_values_clipped"],
            "all_cell_water_volume_m3": profiles["all_cell_water_volume_m3"],
            "thresholds": profiles["threshold_summary"],
        },
        "coordinate_frame": {
            "simulation_axes": case_inputs.get("coordinate_frame", {}).get("mesh", {}),
            "declared_paper_transform": frame.paper_transform,
            "applied_transform": {
                "paper_streamwise_y_m": "simulation x - chosen streamwise registration origin",
                "paper_downward_z_m": "source_plane_z_m - simulation z",
                "paper_cross_track_x_m": "simulation y - declared source-center y",
            },
            "source_center_origin_xyz_m": list(frame.source_origin_xyz_m),
            "streamwise_origin_variants": profiles["origin_variants"],
            "source_streamwise_edges_mesh_x_m": list(frame.streamwise_source_bounds_m),
            "registration_policy": "Use the case-declared source center as primary; also report upstream and downstream physical source-edge origin alternatives. No fitted shift or best alignment is selected.",
            "domain_bounds_mesh_xyz_m": {
                axis: list(bounds) for axis, bounds in frame.domain_bounds_m.items()
            },
            "native_mesh_bounds_xyz_m": {
                axis: list(bounds) for axis, bounds in actual_bounds.items()
            },
            "global_aabb_domain_extent_match": True,
            "global_aabb_domain_extent_tolerance_m": DOMAIN_EXTENT_TOLERANCE_M,
        },
        "normalization": {
            "source_area_m2": frame.source_area_m2,
            "source_area_evidence_class": frame.source_area_evidence,
            "conditional_Lc_sqrt_S_m": frame.l_characteristic_m,
            "paper_numeric_exit_area_reported": False,
            "scope": "L/Lc and z/Lc are conditional on the case-declared provisional area; they do not recover or assert the paper's exit area.",
        },
        "station_spacing_m": profiles["station_spacings_m"],
        "paper_digitizations": {
            "source_record": str(PAPER_SOURCE_RECORD.relative_to(REPO_ROOT)),
            "source_record_sha256": sha256_file(PAPER_SOURCE_RECORD),
            "primary_csv": {
                "path": str(PAPER_PRIMARY_CSV.relative_to(REPO_ROOT)),
                "sha256": sha256_file(PAPER_PRIMARY_CSV),
            },
            "independent_csv": {
                "path": str(PAPER_INDEPENDENT_CSV.relative_to(REPO_ROOT)),
                "sha256": sha256_file(PAPER_INDEPENDENT_CSV),
            },
            "fig6_series": {
                "primary_count": len(paper["fig6_primary"]),
                "independent_count": len(paper["fig6_independent"]),
                "time_s": 0.5,
                "threshold": 0.001,
            },
            "fig9_series": {
                "primary_count": len(paper["fig9_primary"]),
                "independent_count": len(paper["fig9_independent"]),
                "time_s": fig9_spec["time_s"] if fig9_spec else None,
                "series_color": fig9_spec["color_name"] if fig9_spec else None,
                "threshold": 0.001,
            },
            "fig9_table3_correlation": (
                {
                    "time_s": 0.5,
                    "relation": "L/Lc = K_L (z/Lc)^beta",
                    "K_L": 0.07,
                    "beta": 2.0,
                    "source_location": "PDF p. 9 / journal p. 1523, Table 3; Eq. (6) PDF p. 8 / journal p. 1522",
                    "status": "reported correlation; plotted separately from digitized/simulated traces",
                }
                if math.isclose(time_s, 0.5, rel_tol=0.0, abs_tol=1e-9)
                else None
            ),
            "plot_axis_mapping": {
                "fig6": {
                    "horizontal": "streamwise distance y (m)",
                    "vertical": "downward penetration Z (m)",
                    "primary_and_independent_csv_order": "x=streamwise, y=penetration",
                },
                "fig9": {
                    "horizontal": "downward depth z/Lc",
                    "vertical": "lateral width L/Lc",
                    "primary_csv_fields": {
                        "horizontal": "independent_value (z_over_Lc)",
                        "vertical": "dependent_value (L_over_Lc)",
                    },
                    "independent_csv_fields": {
                        "raw_csv_x": "x_value (L_over_Lc)",
                        "raw_csv_y": "y_value (z_over_Lc)",
                        "plotted_horizontal": "y_value; uncertainty read_bound_y",
                        "plotted_vertical": "x_value; uncertainty read_bound_x",
                    },
                },
            },
            "segmentation": "Plots retain independent segment/branch groups and do not join digitized gaps or use the Fig. 8 time-conflicted series.",
        },
        "provenance": {
            "export_dir": str(export_dir.resolve()),
            "exported_native_files_count": len(export_hashes),
            "export_hash_manifest_sha256": sha256_file(output_dir / "native_export_hashes.json"),
            "case_inputs_path": str(case_inputs_path.resolve()),
            "case_inputs_sha256": sha256_bytes(case_inputs_bytes),
            "export_attempt": case_provenance,
            # Keep the legacy key, but define it as the source hash captured at import.
            # A long-running observer can continue using loaded code after an on-disk edit.
            "analyzer_sha256": ANALYZER_LOADED_SOURCE_SHA256,
            **_analyzer_source_identity(ANALYZER_SOURCE_PATH, ANALYZER_LOADED_SOURCE_SHA256),
            "native_loader": "scripts/analyze_native_vof.py::load_export",
            "native_loader_sha256": sha256_file(REPO_ROOT / "scripts/analyze_native_vof.py"),
            "native_exporter_source_path": str(exporter_source_path.resolve()),
            "native_exporter_source_sha256": (
                sha256_file(exporter_source_path) if exporter_source_path.is_file() else None
            ),
        },
        "outputs": {
            "penetration_profiles_csv": "penetration_profiles.csv",
            "width_profiles_csv": "width_profiles.csv",
            "native_export_hashes_json": "native_export_hashes.json",
            "comparison_png": {"path": figure_path.name, "sha256": sha256_file(figure_path)},
        },
        "limits": [
            "Full-cell AABBs bound each nonconforming polyhedral cell and may overstate true cloud extents, especially for skewed cells.",
            "The alpha threshold is applied to cell values; no within-cell alpha=.001 or alpha=.9 surface is reconstructed.",
            "Center-assigned per-slab alpha*V is a native-volume partition, not an AABB-overlap-weighted partial-cell integral.",
            "The paper-to-case origin is unspecified; center/upstream-edge/downstream-edge alternatives are fixed geometry anchors, not fitted registrations.",
            "Fig. 6(b) is digitized at 0.5 s. Fig. 9(a) has separate red 0.5 s, blue 1.0 s and green 1.5 s traces; only the trace matching the exact native snapshot time is selected. The script never interpolates simulation snapshots or connects digitized gaps.",
            "Figure digitizations are pixel reads with recorded correlated read bounds, not author data or statistical confidence intervals.",
            "The case area is inferred/provisional and the paper numeric exit area is unknown; Fig. 9 dimensionalization remains conditional.",
        ],
        "created_utc": datetime.now(UTC).isoformat(),
    }
    report_path = output_dir / "analysis.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", required=True, type=Path)
    parser.add_argument("--case-inputs", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--station-spacing-m", type=float, default=0.075)
    args = parser.parse_args(argv)
    report = analyze(
        args.export_dir.resolve(),
        args.case_inputs.resolve(),
        args.output_dir.resolve(),
        args.station_spacing_m,
    )
    print(
        json.dumps(
            {
                "time_s": report["snapshot"]["time_value_s"],
                "cells": report["snapshot"]["native_cell_count"],
                "output_dir": str(args.output_dir.resolve()),
                "selected_cloud_cells": report["snapshot"]["thresholds"]["0.001"][
                    "selected_cell_count"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
