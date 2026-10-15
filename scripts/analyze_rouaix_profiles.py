#!/usr/bin/env python3
"""Observe Rouaix Case 1 cloud/core profiles from native OpenFOAM fields.

This is an exploratory full-cell AABB observer. It does not implement or claim
equivalence to the paper's unspecified Figure 13 post-processor. Native mesh
coordinates are retained: x is streamwise, y is the native vertical coordinate,
and z is spanwise. Down-positive penetration is reported explicitly as
``source_plane_y0_m - min(native cell y_low)``. Cells are assigned to one
declared x station by their native center; their full native AABBs define the
reported y and z envelope.
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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aerial_drop.structure_counts import label_liquid_structures  # noqa: E402
from scripts.analyze_native_vof import load_export  # noqa: E402

PROFILE_FORMAT = "fire-track2-rouaix-native-profiles-v1"
ROUAIX_CASE1_DIAMETER_M = 0.4
ALPHA_CLOUD_THRESHOLD = 0.1
ALPHA_CORE_THRESHOLD = 0.9
ALPHA_ROUNDOFF_TOLERANCE = 1e-12
CELL_GEOMETRY_TOLERANCE_M = 1e-10
ROUAIX_REFERENCE = {
    "title": "Liquid jet breakup in gaseous crossflow injected through a large diameter nozzle",
    "doi": "https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419",
    "local_pdf": "Rouaix_28516.pdf",
    "case1_diameter_source": "PDF p. 5 / printed article p. 4, Table 3",
    "cloud_and_core_threshold_source": "PDF p. 6 / printed article p. 5, Section 3.1",
    "case_source_record": "experiments/E1_ROUAIX_CASE1_SOURCE.md",
}


def _finite_array(value: Any, *, shape_tail: tuple[int, ...], label: str) -> NDArray[Any]:
    array = np.asarray(value)
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(array.dtype, np.complexfloating):
        raise ValueError(f"{label} must contain real numeric values")
    if array.ndim != len(shape_tail) + 1 or array.shape[1:] != shape_tail:
        if shape_tail:
            expected = f"(n, {', '.join(map(str, shape_tail))})"
        else:
            expected = "a one-dimensional array"
        raise ValueError(f"{label} must have shape {expected}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} must contain only finite values")
    return np.asarray(array, dtype=np.float64)


def _integer_ids(value: Any, *, label: str) -> NDArray[np.int64]:
    array = np.asarray(value)
    if array.ndim != 1 or not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"{label} must be a one-dimensional integer array")
    if np.issubdtype(array.dtype, np.bool_):
        raise ValueError(f"{label} must contain integer IDs")
    if np.any(array < 0):
        raise ValueError(f"{label} must contain nonnegative IDs")
    return np.asarray(array, dtype=np.int64)


def _finite_scalar(value: Any, *, label: str) -> float:
    try:
        scalar = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(scalar):
        raise ValueError(f"{label} must be a finite number")
    return scalar


def _validate_and_map_snapshot(
    snapshot: dict[str, Any], station_tolerance_m: float
) -> tuple[
    NDArray[np.int64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.int64],
    NDArray[np.int64],
    NDArray[np.int64],
]:
    required = (
        "cell_global_ids",
        "alpha_water",
        "cell_centres_xyz_m",
        "cell_bounds_minmax_xyz_m",
        "edges_native_global_ids",
        "source_owner_global_ids",
        "time_name",
        "time_value_s",
        "source_patch",
    )
    absent = [key for key in required if key not in snapshot]
    if absent:
        raise ValueError(f"native snapshot is missing required fields: {', '.join(absent)}")

    cell_ids = _integer_ids(snapshot["cell_global_ids"], label="cell_global_ids")
    if len(np.unique(cell_ids)) != len(cell_ids) or np.any(np.diff(cell_ids) <= 0):
        raise ValueError("cell_global_ids must be unique and sorted in native order")
    n_cells = len(cell_ids)

    alpha = _finite_array(snapshot["alpha_water"], shape_tail=(), label="alpha_water")
    centres = _finite_array(
        snapshot["cell_centres_xyz_m"], shape_tail=(3,), label="cell_centres_xyz_m"
    )
    bounds = _finite_array(
        snapshot["cell_bounds_minmax_xyz_m"],
        shape_tail=(6,),
        label="cell_bounds_minmax_xyz_m",
    )
    if alpha.shape != (n_cells,) or centres.shape != (n_cells, 3) or bounds.shape != (n_cells, 6):
        raise ValueError("native cell IDs, alpha, centers, and bounds must have matching lengths")
    if np.any(alpha < -ALPHA_ROUNDOFF_TOLERANCE) or np.any(alpha > 1.0 + ALPHA_ROUNDOFF_TOLERANCE):
        raise ValueError("alpha_water must be in [0, 1] within native roundoff tolerance")
    if np.any(bounds[:, :3] > bounds[:, 3:]):
        raise ValueError("native cell bounds have inverted min/max coordinates")
    if np.any(centres < bounds[:, :3] - CELL_GEOMETRY_TOLERANCE_M) or np.any(
        centres > bounds[:, 3:] + CELL_GEOMETRY_TOLERANCE_M
    ):
        raise ValueError("native cell centers lie outside their AABBs")

    raw_edges = np.asarray(snapshot["edges_native_global_ids"])
    if (
        raw_edges.ndim != 2
        or raw_edges.shape[1:] != (2,)
        or not np.issubdtype(raw_edges.dtype, np.integer)
    ):
        raise ValueError("edges_native_global_ids must have shape (n, 2) with integer IDs")
    global_edges = np.asarray(raw_edges, dtype=np.int64)
    if global_edges.size and np.any(global_edges < 0):
        raise ValueError("native edge IDs must be nonnegative")

    source_ids = _integer_ids(snapshot["source_owner_global_ids"], label="source_owner_global_ids")
    if not len(source_ids):
        raise ValueError("source_owner_global_ids are required to observe the connected core")

    def map_global_ids(ids: NDArray[np.int64], *, label: str) -> NDArray[np.int64]:
        positions = np.searchsorted(cell_ids, ids)
        valid = positions < len(cell_ids)
        if np.any(valid):
            valid[valid] = cell_ids[positions[valid]] == ids[valid]
        if not np.all(valid):
            raise ValueError(f"{label} reference unknown native global cell IDs")
        return positions.astype(np.int64, copy=False)

    edge_indices = map_global_ids(global_edges.reshape(-1), label="native face edges").reshape(
        (-1, 2)
    )
    source_indices = map_global_ids(source_ids, label="source owners")
    if len(np.unique(source_indices)) != len(source_indices):
        source_indices = np.unique(source_indices)
    station_tolerance_m = _finite_scalar(station_tolerance_m, label="station_tolerance_m")
    if station_tolerance_m < 0:
        raise ValueError("station_tolerance_m must be finite and nonnegative")

    return cell_ids, alpha, centres, bounds, edge_indices, source_indices, global_edges


def _station_membership(
    x_centres_m: NDArray[np.float64],
    station_edges_m: ArrayLike,
    station_tolerance_m: float,
) -> tuple[NDArray[np.int64], NDArray[np.float64], NDArray[np.float64]]:
    edges = _finite_array(station_edges_m, shape_tail=(), label="x_station_edges_m")
    if len(edges) < 2 or np.any(np.diff(edges) <= 0):
        raise ValueError("x_station_edges_m must contain at least two strictly increasing edges")
    if np.any(np.diff(edges) <= 2.0 * station_tolerance_m):
        raise ValueError("station edges must be separated by more than twice the tolerance")

    # Snap centers that fall within the declared tolerance of a station boundary.
    # Exact internal-boundary centers then enter the higher-x bin; the final edge
    # belongs to the last bin. This assigns each native cell at most once.
    snapped = x_centres_m.copy()
    right = np.searchsorted(edges, snapped, side="left")
    upper_valid = right < len(edges)
    upper = np.clip(right, 0, len(edges) - 1)
    lower = np.clip(right - 1, 0, len(edges) - 1)
    upper_distance = np.abs(snapped - edges[upper])
    lower_distance = np.abs(snapped - edges[lower])
    choose_upper = upper_valid & (upper_distance <= lower_distance)
    nearest = np.where(choose_upper, upper, lower)
    near_edge = np.abs(snapped - edges[nearest]) <= station_tolerance_m
    snapped[near_edge] = edges[nearest[near_edge]]

    assigned = (snapped >= edges[0]) & (snapped <= edges[-1])
    station = np.full(len(snapped), -1, dtype=np.int64)
    if np.any(assigned):
        station[assigned] = np.searchsorted(edges, snapped[assigned], side="right") - 1
        station[station == len(edges) - 1] = len(edges) - 2
    return station, edges[:-1], edges[1:]


def _envelope(
    cell_indices: NDArray[np.int64], bounds: NDArray[np.float64], *, y0_m: float, diameter_m: float
) -> dict[str, Any] | None:
    if not len(cell_indices):
        return None
    cells = bounds[cell_indices]
    y_low = float(np.min(cells[:, 1]))
    z_low = float(np.min(cells[:, 2]))
    z_high = float(np.max(cells[:, 5]))
    depth_down = y0_m - y_low
    return {
        "selected_cell_count": int(len(cell_indices)),
        "minimum_native_y_low_m": y_low,
        "maximum_native_y_high_m": float(np.max(cells[:, 4])),
        "native_y_low_minus_source_plane_m": y_low - y0_m,
        "penetration_down_positive_m": depth_down,
        "penetration_down_positive_over_D": depth_down / diameter_m,
        "minimum_signed_z_low_m": z_low,
        "maximum_signed_z_high_m": z_high,
        "full_spanwise_width_m": z_high - z_low,
        "full_spanwise_width_over_D": (z_high - z_low) / diameter_m,
    }


def profile_rouaix_snapshot(
    snapshot: dict[str, Any],
    *,
    x_station_edges_m: ArrayLike,
    x_origin_m: float,
    source_plane_y0_m: float,
    station_tolerance_m: float = 1e-9,
    diameter_m: float = ROUAIX_CASE1_DIAMETER_M,
) -> dict[str, Any]:
    """Return native-center-binned Rouaix cloud and source-connected core profiles.

    Full-cloud cells use ``alpha.water >= 0.1`` and include disconnected lobes.
    Core cells use ``alpha.water >= 0.9`` and are connected over the full native
    face graph before they are binned; only components intersecting explicit
    source-patch owner cells are retained. No cell-ID convention or fallback
    source seed is assumed.
    """
    x_origin_m = _finite_scalar(x_origin_m, label="x_origin_m")
    source_plane_y0_m = _finite_scalar(source_plane_y0_m, label="source_plane_y0_m")
    diameter_m = _finite_scalar(diameter_m, label="diameter_m")
    station_tolerance_m = _finite_scalar(station_tolerance_m, label="station_tolerance_m")
    if diameter_m <= 0:
        raise ValueError("diameter_m must be positive and finite")
    if station_tolerance_m < 0:
        raise ValueError("station_tolerance_m must be finite and nonnegative")
    time_name = str(snapshot.get("time_name", ""))
    if not time_name:
        raise ValueError("time_name must be nonempty")
    time_value_s = _finite_scalar(time_name, label="time_name numeric value")
    export_metadata_time_value_s = _finite_scalar(
        snapshot.get("time_value_s"), label="export metadata time_value_s"
    )
    if not str(snapshot.get("source_patch", "")):
        raise ValueError("source_patch must be nonempty")
    (
        cell_ids,
        alpha,
        centres,
        bounds,
        edge_indices,
        source_indices,
        _,
    ) = _validate_and_map_snapshot(snapshot, station_tolerance_m)
    station, station_lows, station_highs = _station_membership(
        centres[:, 0], x_station_edges_m, station_tolerance_m
    )

    cloud_selected = alpha >= ALPHA_CLOUD_THRESHOLD
    core_selected = alpha >= ALPHA_CORE_THRESHOLD
    labels = label_liquid_structures(
        alpha, edge_indices[:, 0], edge_indices[:, 1], ALPHA_CORE_THRESHOLD
    )
    source_selected = source_indices[core_selected[source_indices]]
    seeded_labels = (
        np.unique(labels[source_selected]) if len(source_selected) else np.empty(0, np.int32)
    )
    seeded_labels = seeded_labels[seeded_labels >= 0]
    core_connected = (
        np.isin(labels, seeded_labels) if len(seeded_labels) else np.zeros(len(alpha), bool)
    )

    n_stations = len(station_lows)
    station_rows: list[dict[str, Any]] = []
    for station_index in range(n_stations):
        in_station = station == station_index
        cloud_indices = np.flatnonzero(in_station & cloud_selected)
        core_indices = np.flatnonzero(in_station & core_connected)
        x_low = float(station_lows[station_index])
        x_high = float(station_highs[station_index])
        x_center = 0.5 * (x_low + x_high)
        station_rows.append(
            {
                "station_index": station_index,
                "x_station_low_m": x_low,
                "x_station_high_m": x_high,
                "x_station_center_m": x_center,
                "x_station_low_relative_to_origin_m": x_low - x_origin_m,
                "x_station_high_relative_to_origin_m": x_high - x_origin_m,
                "x_station_center_relative_to_origin_m": x_center - x_origin_m,
                "x_station_low_over_D": (x_low - x_origin_m) / diameter_m,
                "x_station_high_over_D": (x_high - x_origin_m) / diameter_m,
                "x_station_center_over_D": (x_center - x_origin_m) / diameter_m,
                "full_cloud_alpha_ge_0p1": _envelope(
                    cloud_indices, bounds, y0_m=source_plane_y0_m, diameter_m=diameter_m
                ),
                "source_connected_core_alpha_ge_0p9": _envelope(
                    core_indices, bounds, y0_m=source_plane_y0_m, diameter_m=diameter_m
                ),
            }
        )

    all_core_labels = np.unique(labels[core_selected])
    all_core_labels = all_core_labels[all_core_labels >= 0]
    return {
        "schema": PROFILE_FORMAT,
        "observer": "native-cell-center x bins with full native cell AABB envelopes",
        "exploratory_only": True,
        "paper_detector_equivalence": False,
        "paper_acceptance_decision": None,
        "comparison_limit": (
            "Figure 13's detector and sampling time are unspecified; its z/d_j ordinate is not "
            "converted to a half-width or full-width. This observer reports full AABB span."
        ),
        "reference": ROUAIX_REFERENCE,
        "field": "alpha.water",
        "time_name": time_name,
        "time_value_s": time_value_s,
        "export_metadata_time_value_s": export_metadata_time_value_s,
        "time_value_source": "numeric parse of exact native field time_name; export metadata value retained separately",
        "source_patch": str(snapshot["source_patch"]),
        "source_owner_global_cell_count": int(len(source_indices)),
        "coordinate_frame": {
            "x_axis": "native mesh x, streamwise",
            "x_origin_m": float(x_origin_m),
            "x_origin_description": "declared nozzle-center/source-plane x coordinate",
            "y_axis": "native mesh y; signed coordinates are retained",
            "source_plane_y0_m": float(source_plane_y0_m),
            "down_positive_penetration_definition": "source_plane_y0_m - minimum_native_y_low_m",
            "z_axis": "native mesh z, spanwise; signed edges are retained",
        },
        "diameter_normalization_m": float(diameter_m),
        "alpha_thresholds": {
            "full_cloud": {"value": ALPHA_CLOUD_THRESHOLD, "comparison": ">="},
            "source_connected_core": {"value": ALPHA_CORE_THRESHOLD, "comparison": ">="},
            "raw_alpha_values_clipped": False,
            "native_roundoff_tolerance": ALPHA_ROUNDOFF_TOLERANCE,
        },
        "station_assignment": {
            "edges_m": [float(item) for item in np.asarray(x_station_edges_m, dtype=float)],
            "cell_membership": "native cell-center x coordinate",
            "boundary_tolerance_m": float(station_tolerance_m),
            "within_tolerance_of_edge": "snap to the nearest edge before assignment",
            "internal_edge_rule": "center on an internal edge enters the higher-x bin",
            "final_edge_rule": "center on the final edge enters the final bin",
            "aabb_contribution": "full native y/z AABB for each cell assigned once by its center",
        },
        "connectivity": {
            "threshold_rule": "global alpha.water >= 0.9 selection, then native face-edge labels",
            "edge_source": "native internal faces plus processor-face joins from the export",
            "source_seed_rule": "components must intersect listed source_owner_global_ids",
            "selected_source_owner_cell_count": int(len(source_selected)),
            "selected_source_owner_component_count": int(len(seeded_labels)),
            "all_core_component_count": int(len(all_core_labels)),
            "source_connected_core_component_count": int(len(seeded_labels)),
            "source_connected_core_cell_count": int(np.count_nonzero(core_connected)),
            "no_source_seed_fallback": True,
        },
        "station_count": n_stations,
        "full_cloud_selected_cells_outside_query_bins": int(
            np.count_nonzero(cloud_selected & (station < 0))
        ),
        "source_connected_core_cells_outside_query_bins": int(
            np.count_nonzero(core_connected & (station < 0))
        ),
        "stations": station_rows,
    }


def _station_edges_from_range(
    x_range_m: tuple[float, float], station_width_m: float
) -> NDArray[np.float64]:
    low, high = (float(x_range_m[0]), float(x_range_m[1]))
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        raise ValueError("--x-range-m must be finite and increasing")
    if not math.isfinite(station_width_m) or station_width_m <= 0:
        raise ValueError("--x-station-width-m must be positive and finite")
    count = int(math.ceil((high - low) / station_width_m))
    edges = low + station_width_m * np.arange(count + 1, dtype=np.float64)
    edges[-1] = high
    if count > 1 and np.any(np.diff(edges) <= 0):
        raise ValueError("x station width is too small for the declared range")
    return edges


def _profile_csv_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    common = {
        "export_dir": run["export_dir"],
        "time_name": run["profile"]["time_name"],
        "time_value_s": run["profile"]["time_value_s"],
        "source_patch": run["profile"]["source_patch"],
        "field": run["profile"]["field"],
    }
    for station in run["profile"]["stations"]:
        row = {**common, **station}
        for profile_key in ("full_cloud_alpha_ge_0p1", "source_connected_core_alpha_ge_0p9"):
            envelope = row.pop(profile_key)
            for field in (
                "selected_cell_count",
                "minimum_native_y_low_m",
                "maximum_native_y_high_m",
                "native_y_low_minus_source_plane_m",
                "penetration_down_positive_m",
                "penetration_down_positive_over_D",
                "minimum_signed_z_low_m",
                "maximum_signed_z_high_m",
                "full_spanwise_width_m",
                "full_spanwise_width_over_D",
            ):
                row[f"{profile_key}_{field}"] = None if envelope is None else envelope[field]
        rows.append(row)
    return rows


def _write_outputs(output_dir: Path, runs: list[dict[str, Any]], *, snapshot_summary: bool) -> None:
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": PROFILE_FORMAT,
        "observer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runs": runs,
        "snapshot_summary": None,
    }
    if snapshot_summary and len(runs) >= 2:
        report["snapshot_summary"] = {
            "interpretation": "descriptive metrics across supplied field exports; stationarity is not asserted",
            "snapshots": [
                {
                    "export_dir": run["export_dir"],
                    "time_name": run["profile"]["time_name"],
                    "time_value_s": run["profile"]["time_value_s"],
                    "source_patch": run["profile"]["source_patch"],
                    "source_connected_core_cell_count": run["profile"]["connectivity"][
                        "source_connected_core_cell_count"
                    ],
                    "cloud_station_count_nonempty": sum(
                        station["full_cloud_alpha_ge_0p1"] is not None
                        for station in run["profile"]["stations"]
                    ),
                    "core_station_count_nonempty": sum(
                        station["source_connected_core_alpha_ge_0p9"] is not None
                        for station in run["profile"]["stations"]
                    ),
                }
                for run in runs
            ],
        }
    (output_dir / "profiles.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    rows = [row for run in runs for row in _profile_csv_rows(run)]
    if rows:
        with (output_dir / "profiles.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        (output_dir / "profiles.csv").write_text("\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-dir",
        type=Path,
        action="append",
        required=True,
        help="native export directory; repeat for snapshots",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="new output directory")
    parser.add_argument(
        "--x-range-m",
        type=float,
        nargs=2,
        required=True,
        metavar=("XMIN", "XMAX"),
        help="declared absolute native-mesh x range for query stations",
    )
    parser.add_argument(
        "--x-station-width-m",
        type=float,
        required=True,
        help="declared query-station width; the last station may be shorter",
    )
    parser.add_argument(
        "--x-origin-m",
        type=float,
        required=True,
        help="declared native-mesh x coordinate of the nozzle center/source plane",
    )
    parser.add_argument(
        "--source-plane-y0-m",
        type=float,
        required=True,
        help="declared native-mesh y coordinate of the source plane",
    )
    parser.add_argument(
        "--diameter-m",
        type=float,
        default=ROUAIX_CASE1_DIAMETER_M,
        help="normalization diameter (default: Rouaix Case 1 table value, 0.4 m)",
    )
    parser.add_argument(
        "--station-tolerance-m",
        type=float,
        default=1e-9,
        help="snap cell centers within this distance of station edges (default: 1e-9 m)",
    )
    parser.add_argument(
        "--snapshot-summary",
        action="store_true",
        help="include descriptive metrics for two or more snapshots; does not assert stationarity",
    )
    args = parser.parse_args(argv)
    try:
        edges = _station_edges_from_range(tuple(args.x_range_m), args.x_station_width_m)
        runs: list[dict[str, Any]] = []
        for export_dir in args.export_dir:
            snapshot, input_hashes = load_export(export_dir)
            profile = profile_rouaix_snapshot(
                snapshot,
                x_station_edges_m=edges,
                x_origin_m=args.x_origin_m,
                source_plane_y0_m=args.source_plane_y0_m,
                station_tolerance_m=args.station_tolerance_m,
                diameter_m=args.diameter_m,
            )
            runs.append(
                {
                    "export_dir": str(export_dir),
                    "native_export_sha256": input_hashes,
                    "geometry_observer_inputs": {
                        "x_origin_m": args.x_origin_m,
                        "source_plane_y0_m": args.source_plane_y0_m,
                        "x_station_edges_m": [float(item) for item in edges],
                        "diameter_normalization_m": args.diameter_m,
                        "station_tolerance_m": args.station_tolerance_m,
                    },
                    "profile": profile,
                }
            )
        _write_outputs(args.output_dir, runs, snapshot_summary=args.snapshot_summary)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Rouaix native profile analysis failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "json": str(args.output_dir / "profiles.json"),
                "csv": str(args.output_dir / "profiles.csv"),
                "snapshots": len(runs),
                "summary_written": bool(args.snapshot_summary and len(runs) >= 2),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
