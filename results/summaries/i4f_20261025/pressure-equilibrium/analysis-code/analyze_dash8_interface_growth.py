#!/usr/bin/env python3
"""Describe early Dash-8 liquid-sheet shape and near-interface fields.

The saved 0.1 s Eulerian fields support spatial morphology diagnostics. They do
not resolve millisecond-scale amplification and cannot identify a Lagrangian
disturbance growth rate. This observer reads existing native exports and saved
OpenFOAM fields without changing a case, mesh, checkpoint, or source record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_native_turbulence import (  # noqa: E402
    FIELD_DIMENSIONS,
    _header_value,
    read_foam_scalar_internal,
    verify_native_export_input_inventory,
)
from scripts.analyze_native_vof import load_export  # noqa: E402

SCHEMA = "fire-track2-dash8-interface-growth-analysis-v1"
TIMES_S = (0.1, 0.2, 0.3, 0.4, 1.0)
CASE_SPECS = {
    "uniform_670k": {
        "label": "670,480-cell corrected reference",
        "case": "results/runs/dash8-freestream-backflow-20261004T200945Z/case",
        "export": (
            "results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/"
            "exports/corrected_reference_670k/raw"
        ),
    },
    "uniform_refined_1p857m": {
        "label": "1,857,796-cell refined uniform inlet",
        "case": "results/runs/dash8-local-mesh-uniform-exit1-retry-20261005t0648z/case",
        "export": (
            "results/runs/dash8-local-pair-t0p4-comparison-20261005T130240Z/"
            "exports/uniform-attempt-01/raw"
        ),
    },
    "three_component_refined_1p857m": {
        "label": "1,857,796-cell refined three-component inlet",
        "case": "results/runs/dash8-local-mesh-three-component-exit1-retry-20261005t0648z/case",
        "export": (
            "results/runs/dash8-local-pair-t0p4-comparison-20261005T130240Z/"
            "exports/three_component-attempt-01/raw"
        ),
    },
}

VECTOR_DIMENSIONS = {"U": "0 1 -1 0 0 0 0"}
SCALAR_DIMENSIONS = {"alpha.water": "0 0 0 0 0 0 0", **FIELD_DIMENSIONS}
SOURCE_EXTENT_M = {"x": [0.0, 4.44], "y": [-0.15, 0.15], "z": [0.0, 0.0]}
SECTION_Z_M = (-0.15, -0.30, -0.45, -0.75, -1.2)
SECTION_DZ_M = 0.075
SECTION_DX_M = 0.15
SECTION_Y_LIMITS_M = (-1.5, 1.5)
SPECTRUM_MIN_SAMPLES = 16
SPECTRUM_MIN_WAVELENGTH_CELLS = 4.0
SPECTRUM_MIN_CYCLES_IN_SEGMENT = 2.0
MESH_TRANSITION_X_DOMAIN_M = (-1.0, 12.0)
MESH_TRANSITION_MAX_EMPTY_BIN_GAP_M = 4.0 * SECTION_DX_M
_NUMBER = rb"[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?|[+-]?(?:nan|inf(?:inity)?)"


@dataclass(frozen=True)
class CaseSpec:
    key: str
    label: str
    case_dir: Path
    export_dir: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_foam_vector_internal(
    path: Path,
    *,
    expected_count: int,
    expected_object: str,
    expected_location: str,
    expected_dimensions: str,
) -> NDArray[np.float64]:
    """Read a uniform or nonuniform ASCII/binary OpenFOAM vector internalField."""
    data = path.read_bytes()
    foam_header = re.search(rb"FoamFile\s*\{(.*?)\}", data, flags=re.DOTALL)
    if foam_header is None:
        raise ValueError(f"missing FoamFile header in {path}")
    header = foam_header.group(1)
    if _header_value(header, "class") != "volVectorField":
        raise ValueError(f"{path} is not a volVectorField")
    if _header_value(header, "object") != expected_object:
        raise ValueError(f"{path} object name does not match {expected_object}")
    if not math.isclose(
        float(_header_value(header, "location")), float(expected_location), rel_tol=0, abs_tol=5e-10
    ):
        raise ValueError(f"{path} location does not match {expected_location!r}")
    dimensions_match = re.search(rb"\bdimensions\s*\[([^\]]+)\]", data[: foam_header.end() + 4096])
    if dimensions_match is None:
        raise ValueError(f"{path} has no dimensions entry before internalField")
    dimensions = " ".join(dimensions_match.group(1).decode("ascii").split())
    if dimensions != expected_dimensions:
        raise ValueError(f"{path} dimensions {dimensions!r} do not match {expected_dimensions!r}")
    field_format = _header_value(header, "format")
    if field_format not in {"ascii", "binary"}:
        raise ValueError(f"unsupported OpenFOAM field format {field_format!r} in {path}")

    uniform = re.search(
        rb"\binternalField\s+uniform\s+\(\s*("
        + _NUMBER
        + rb")\s+("
        + _NUMBER
        + rb")\s+("
        + _NUMBER
        + rb")\s*\)\s*;",
        data,
    )
    if uniform is not None:
        vector = np.asarray([float(value) for value in uniform.groups()], dtype=np.float64)
        return np.broadcast_to(vector, (expected_count, 3)).copy()

    nonuniform = re.search(rb"\binternalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\(", data)
    if nonuniform is None:
        raise ValueError(f"{path} has an unsupported internalField representation")
    count = int(nonuniform.group(1))
    if count != expected_count:
        raise ValueError(f"{path} internalField has {count} vectors; expected {expected_count}")
    payload_start = nonuniform.end()
    if field_format == "binary":
        arch = _header_value(header, "arch")
        scalar_bits = re.search(r"(?:^|;)scalar=(\d+)(?:;|$)", arch)
        if scalar_bits is None or int(scalar_bits.group(1)) != 64:
            raise ValueError(f"unsupported binary scalar precision in {path}: {arch!r}")
        byte_order = "<" if arch.startswith("LSB") else ">" if arch.startswith("MSB") else None
        if byte_order is None:
            raise ValueError(f"unsupported binary byte order in {path}: {arch!r}")
        payload_end = payload_start + count * 3 * 8
        if payload_end > len(data):
            raise ValueError(f"truncated binary internalField in {path}")
        trailer = data[payload_end:].lstrip(b" \t\r\n")
        if not trailer.startswith(b")") or not trailer[1:].lstrip(b" \t\r\n").startswith(b";"):
            raise ValueError(f"binary internalField terminator is missing in {path}")
        return (
            np.frombuffer(
                data, dtype=np.dtype(f"{byte_order}f8"), count=count * 3, offset=payload_start
            )
            .astype(np.float64, copy=True)
            .reshape((count, 3))
        )

    closing = re.search(rb"\n\s*\)\s*;", data[payload_start:])
    if closing is None:
        raise ValueError(f"ASCII internalField closing parenthesis is missing in {path}")
    payload_end = payload_start + closing.start()
    triples = re.findall(
        rb"\(\s*(" + _NUMBER + rb")\s+(" + _NUMBER + rb")\s+(" + _NUMBER + rb")\s*\)",
        data[payload_start:payload_end],
    )
    if len(triples) != count:
        raise ValueError(f"{path} internalField has {len(triples)} vectors; expected {count}")
    return np.asarray([[float(token) for token in row] for row in triples], dtype=np.float64)


def _case_time_name(case_dir: Path, rank: int, time_s: float) -> str:
    root = case_dir / f"processor{rank}"
    matches = []
    for path in root.iterdir():
        if path.is_dir():
            try:
                value = float(path.name)
            except ValueError:
                continue
            if math.isclose(value, time_s, rel_tol=0.0, abs_tol=5e-10):
                matches.append(path.name)
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one saved t={time_s:g} under {root}; found {matches}")
    return matches[0]


def read_rank_fields(
    spec: CaseSpec,
    raw_export: Path,
    global_ids: NDArray[np.int64],
    time_s: float,
) -> tuple[dict[str, NDArray[np.float64]], dict[str, str]]:
    """Read and align saved internal fields to the native exporter cell order."""
    rank_dirs = sorted(raw_export.glob("rank-[0-9][0-9][0-9][0-9]"))
    if not rank_dirs:
        raise FileNotFoundError(f"no native rank exports under {raw_export}")
    aligned = {
        "alpha.water": np.empty(len(global_ids), dtype=np.float64),
        "U": np.empty((len(global_ids), 3), dtype=np.float64),
        "k": np.empty(len(global_ids), dtype=np.float64),
        "epsilon": np.empty(len(global_ids), dtype=np.float64),
        "nut": np.empty(len(global_ids), dtype=np.float64),
    }
    field_hashes: dict[str, str] = {}
    for expected_rank, rank_dir in enumerate(rank_dirs):
        rank = int(rank_dir.name.split("-")[-1])
        if rank != expected_rank:
            raise ValueError(f"non-contiguous rank inventory under {raw_export}")
        local_ids = np.fromfile(rank_dir / "cell_global_ids.i64", dtype=np.dtype("<i8"))
        metadata = json.loads((rank_dir / "metadata.json").read_text(encoding="utf-8"))
        if len(local_ids) != int(metadata["local_cell_count"]):
            raise ValueError(f"cell ID count mismatch in {rank_dir}")
        destinations = np.searchsorted(global_ids, local_ids)
        if np.any(destinations >= len(global_ids)) or not np.array_equal(
            global_ids[destinations], local_ids
        ):
            raise ValueError(f"rank {rank} IDs do not map to the native sorted cell order")
        time_name = _case_time_name(spec.case_dir, rank, time_s)
        time_dir = spec.case_dir / f"processor{rank}" / time_name
        count = len(local_ids)
        field_paths = {name: time_dir / name for name in aligned}
        for name, path in field_paths.items():
            if not path.is_file():
                raise FileNotFoundError(f"saved {name} is missing: {path}")
            relative = str(path.relative_to(spec.case_dir))
            field_hashes[relative] = sha256_file(path)
            if name == "U":
                values = read_foam_vector_internal(
                    path,
                    expected_count=count,
                    expected_object="U",
                    expected_location=time_name,
                    expected_dimensions=VECTOR_DIMENSIONS["U"],
                )
            else:
                values = read_foam_scalar_internal(
                    path,
                    expected_count=count,
                    expected_object=name,
                    expected_location=time_name,
                    expected_dimensions=SCALAR_DIMENSIONS[name],
                )
            aligned[name][destinations] = values
    if any(not np.all(np.isfinite(values)) for values in aligned.values()):
        raise ValueError(f"non-finite internal values at t={time_s:g} in {spec.key}")
    return aligned, field_hashes


def verify_field_hashes(case_dir: Path, hashes: dict[str, str]) -> None:
    changed = [
        relative
        for relative, expected in hashes.items()
        if sha256_file(case_dir / relative) != expected
    ]
    if changed:
        raise RuntimeError(f"saved field inputs changed during analysis: {changed[:5]}")


def weighted_summary(values: NDArray[np.float64], weights: NDArray[np.float64]) -> dict[str, Any]:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0.0)
    if not np.any(valid):
        return {"status": "missing", "reason": "no finite values with positive weights"}
    data, weight = values[valid], weights[valid]
    order = np.argsort(data, kind="stable")
    data_sorted, weight_sorted = data[order], weight[order]
    cumulative = np.cumsum(weight_sorted, dtype=np.float64)
    total = float(cumulative[-1])
    quantiles = {}
    for level in (0.05, 0.5, 0.9, 0.95, 0.99):
        index = min(
            int(np.searchsorted(cumulative, level * total, side="left")), len(data_sorted) - 1
        )
        quantiles[f"p{round(level * 100):02d}"] = float(data_sorted[index])
    return {
        "status": "computed",
        "positive_weight_sum": total,
        "weighted_mean": float(np.sum(data * weight, dtype=np.float64) / total),
        "weighted_quantiles": quantiles,
        "minimum": float(np.min(data)),
        "maximum": float(np.max(data)),
        "sample_count": int(np.count_nonzero(valid)),
    }


def source_connected_core(
    alpha: NDArray[np.float64],
    edges: NDArray[np.int64],
    source_owners: NDArray[np.int64],
    *,
    threshold: float = 0.5,
) -> NDArray[np.bool_]:
    """Return the face-connected alpha-thresholded component(s) touching source owners."""
    wet_cells = np.flatnonzero(alpha >= threshold)
    result = np.zeros(len(alpha), dtype=bool)
    if not len(wet_cells):
        return result
    lookup = np.full(len(alpha), -1, dtype=np.int64)
    lookup[wet_cells] = np.arange(len(wet_cells), dtype=np.int64)
    seeds = np.unique(source_owners[(source_owners >= 0) & (source_owners < len(alpha))])
    seeds = seeds[alpha[seeds] >= threshold]
    if not len(seeds):
        return result
    wet_edge_mask = (alpha[edges[:, 0]] >= threshold) & (alpha[edges[:, 1]] >= threshold)
    local_edges = lookup[edges[wet_edge_mask]]
    parent = np.arange(len(wet_cells), dtype=np.int64)
    rank = np.zeros(len(wet_cells), dtype=np.uint8)

    def find(index: int) -> int:
        root = index
        while parent[root] != root:
            root = int(parent[root])
        while parent[index] != index:
            next_index = int(parent[index])
            parent[index] = root
            index = next_index
        return root

    for left, right in local_edges:
        root_left, root_right = find(int(left)), find(int(right))
        if root_left == root_right:
            continue
        if rank[root_left] < rank[root_right]:
            root_left, root_right = root_right, root_left
        parent[root_right] = root_left
        if rank[root_left] == rank[root_right]:
            rank[root_left] += 1
    seed_roots = {find(int(lookup[index])) for index in seeds}
    connected = np.fromiter(
        (find(int(index)) in seed_roots for index in range(len(wet_cells))), bool
    )
    result[wet_cells] = connected
    return result


def cell_neighbours(mask: NDArray[np.bool_], edges: NDArray[np.int64]) -> NDArray[np.bool_]:
    adjacent = np.zeros(len(mask), dtype=bool)
    touching = mask[edges[:, 0]] | mask[edges[:, 1]]
    selected = edges[touching]
    adjacent[selected[:, 0]] = True
    adjacent[selected[:, 1]] = True
    return adjacent & ~mask


def least_squares_shear(
    centres: NDArray[np.float64],
    velocity: NDArray[np.float64],
    edges: NDArray[np.int64],
    target_mask: NDArray[np.bool_],
) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    """Estimate local strain-rate magnitude on targets from native face neighbours."""
    target_indices = np.flatnonzero(target_mask)
    shear = np.full(len(centres), np.nan, dtype=np.float64)
    valid_full = np.zeros(len(centres), dtype=bool)
    if len(target_indices) == 0:
        return shear, valid_full
    local_index = np.full(len(centres), -1, dtype=np.int64)
    local_index[target_indices] = np.arange(len(target_indices), dtype=np.int64)
    normal = np.zeros((len(target_indices), 3, 3), dtype=np.float64)
    rhs = np.zeros((len(target_indices), 3, 3), dtype=np.float64)
    edge_chunk = 100_000
    target_edges = target_mask[edges[:, 0]] | target_mask[edges[:, 1]]
    selected_edges = edges[target_edges]
    for start in range(0, len(selected_edges), edge_chunk):
        block = selected_edges[start : start + edge_chunk]
        left, right = block[:, 0], block[:, 1]
        delta_x = centres[right] - centres[left]
        delta_u = velocity[right] - velocity[left]
        products_xx = np.einsum("ni,nj->nij", delta_x, delta_x)
        products_xu = np.einsum("ni,nj->nij", delta_x, delta_u)
        left_local = local_index[left]
        select_left = left_local >= 0
        if np.any(select_left):
            np.add.at(normal, left_local[select_left], products_xx[select_left])
            np.add.at(rhs, left_local[select_left], products_xu[select_left])
        right_local = local_index[right]
        select_right = right_local >= 0
        if np.any(select_right):
            np.add.at(normal, right_local[select_right], products_xx[select_right])
            np.add.at(rhs, right_local[select_right], products_xu[select_right])
    eigenvalues = np.linalg.eigvalsh(normal)
    well_conditioned = (eigenvalues[:, 0] > 0.0) & (
        eigenvalues[:, 0] / np.maximum(eigenvalues[:, 2], np.finfo(float).tiny) > 1e-9
    )
    gradients = np.full_like(rhs, np.nan)
    if np.any(well_conditioned):
        gradients[well_conditioned] = np.linalg.solve(
            normal[well_conditioned], rhs[well_conditioned]
        )
    strain = 0.5 * (gradients + np.swapaxes(gradients, 1, 2))
    magnitudes = np.sqrt(2.0 * np.sum(strain * strain, axis=(1, 2)))
    valid_local = well_conditioned & np.isfinite(magnitudes)
    shear[target_indices[valid_local]] = magnitudes[valid_local]
    valid_full[target_indices[valid_local]] = True
    return shear, valid_full


def turbulence_and_shear_summary(
    snapshot: dict[str, Any],
    fields: dict[str, NDArray[np.float64]],
    *,
    x_shift_to_leading_edge_m: float,
) -> tuple[dict[str, Any], NDArray[np.float64], NDArray[np.bool_]]:
    alpha = fields["alpha.water"]
    volumes = snapshot["cell_volumes_m3"]
    edges = snapshot["edges_native_global_ids"]
    connected = source_connected_core(alpha, edges, snapshot["source_owner_global_ids"])
    adjacent = cell_neighbours(connected, edges)
    mixed = (alpha > 0.001) & (alpha < 0.999)
    connected_interface = mixed & (connected | adjacent)
    shear, shear_valid = least_squares_shear(
        snapshot["cell_centres_xyz_m"], fields["U"], edges, connected_interface
    )
    core_stats: dict[str, Any] = {}
    interface_stats: dict[str, Any] = {}
    for name in ("k", "epsilon", "nut"):
        core_stats[name] = weighted_summary(fields[name][connected], volumes[connected])
        interface_stats[name] = weighted_summary(
            fields[name][connected_interface], volumes[connected_interface]
        )
    interface_stats["strain_rate_magnitude_s^-1"] = weighted_summary(
        shear[connected_interface & shear_valid], volumes[connected_interface & shear_valid]
    )
    max_index = None
    if np.any(connected_interface & shear_valid):
        candidates = np.flatnonzero(connected_interface & shear_valid)
        max_index = int(candidates[np.argmax(shear[candidates])])
    max_solver_xyz = (
        snapshot["cell_centres_xyz_m"][max_index].copy() if max_index is not None else None
    )
    max_leading_edge_xyz = max_solver_xyz.copy() if max_solver_xyz is not None else None
    if max_leading_edge_xyz is not None:
        max_leading_edge_xyz[0] += x_shift_to_leading_edge_m
    return (
        {
            "connectivity_definition": (
                "face-connected cells with raw alpha.water >= 0.5 that touch at least one "
                "source-patch owner cell; interface shell is 0.001 < alpha < 0.999 on the "
                "component or one native-face neighbour from it"
            ),
            "source_connected_core_cell_count": int(np.count_nonzero(connected)),
            "connected_interface_cell_count": int(np.count_nonzero(connected_interface)),
            "interface_gradient_valid_cell_count": int(
                np.count_nonzero(connected_interface & shear_valid)
            ),
            "connected_water_core": core_stats,
            "connected_interface_shell": interface_stats,
            "maximum_interface_shear_location": (
                {
                    "cell_index_in_native_sorted_order": max_index,
                    "xyz_solver_source_center_origin_m": max_solver_xyz.tolist(),
                    "xyz_opening_leading_edge_origin_m": max_leading_edge_xyz.tolist(),
                    "alpha_water": float(alpha[max_index]),
                    "strain_rate_magnitude_s^-1": float(shear[max_index]),
                    "cell_aabb_width_xyz_m": (
                        snapshot["cell_bounds_minmax_xyz_m"][max_index, 3:]
                        - snapshot["cell_bounds_minmax_xyz_m"][max_index, :3]
                    ).tolist(),
                }
                if max_index is not None
                else None
            ),
            "gradient_method": (
                "unweighted 3-D least-squares gradient from native face-neighbour cell-centre "
                "and saved internal U differences; report sqrt(2 S:S), S=sym(grad U); "
                "singular/ill-conditioned local stencils are missing, not regularized"
            ),
            "coordinate_x_shift_to_opening_leading_edge_m": x_shift_to_leading_edge_m,
        },
        shear,
        connected_interface,
    )


def _intersect_fraction(
    low: NDArray[np.float64], high: NDArray[np.float64], limits: tuple[float, float]
) -> NDArray[np.float64]:
    overlap = np.maximum(0.0, np.minimum(high, limits[1]) - np.maximum(low, limits[0]))
    return np.clip(overlap / np.maximum(high - low, np.finfo(float).tiny), 0.0, 1.0)


def spectrum_from_profile(
    x_m: NDArray[np.float64],
    displacement_m: NDArray[np.float64],
    valid: NDArray[np.bool_],
    *,
    sample_spacing_m: float,
    local_cell_dx_m: NDArray[np.float64],
) -> dict[str, Any]:
    """Return a spatial FFT for the longest observed contiguous, unfilled segment."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, present in enumerate(np.r_[valid, False]):
        if present and start is None:
            start = index
        elif not present and start is not None:
            runs.append((start, index))
            start = None
    if not runs:
        return {"status": "missing", "reason": "no valid cross-section displacement samples"}
    first, end = max(runs, key=lambda item: item[1] - item[0])
    count = end - first
    if count < SPECTRUM_MIN_SAMPLES:
        return {
            "status": "missing",
            "reason": "longest contiguous segment has fewer than 16 samples; no gaps are filled",
            "contiguous_sample_count": count,
        }
    values = displacement_m[first:end].astype(np.float64, copy=True)
    values -= float(np.mean(values))
    window = np.hanning(count)
    amplitude = 2.0 * np.abs(np.fft.rfft(values * window)) / max(float(np.sum(window)), 1.0)
    frequency = np.fft.rfftfreq(count, d=sample_spacing_m)
    use = frequency > 0.0
    wavelength = 1.0 / frequency[use]
    amplitude = amplitude[use]
    median_local_dx = float(np.median(local_cell_dx_m[first:end]))
    segment_length_m = float(x_m[end - 1] - x_m[first] + sample_spacing_m)
    resolution_floor = max(
        SPECTRUM_MIN_WAVELENGTH_CELLS * sample_spacing_m,
        SPECTRUM_MIN_WAVELENGTH_CELLS * median_local_dx,
    )
    resolved = (wavelength >= resolution_floor) & (
        wavelength <= segment_length_m / SPECTRUM_MIN_CYCLES_IN_SEGMENT
    )
    if not np.any(resolved):
        return {
            "status": "missing",
            "reason": (
                "no FFT wavelength satisfies both the minimum of four sample/local mesh widths "
                "and the maximum length allowed by the two-cycle rule"
            ),
            "contiguous_sample_count": count,
            "resolution_floor_wavelength_m": resolution_floor,
            "segment_length_m": segment_length_m,
            "minimum_cycles_in_segment": SPECTRUM_MIN_CYCLES_IN_SEGMENT,
        }
    eligible_indices = np.flatnonzero(resolved)
    peak_index = int(eligible_indices[np.argmax(amplitude[resolved])])
    records = [
        {"wavelength_m": float(wavelength[i]), "amplitude_m": float(amplitude[i])}
        for i in eligible_indices
    ]
    return {
        "status": "computed",
        "coordinate": "streamwise x in the fixed horizontal z section; displacement is y",
        "contiguous_sample_count": count,
        "contiguous_x_bounds_m": [float(x_m[first]), float(x_m[end - 1])],
        "segment_length_m": segment_length_m,
        "minimum_cycles_in_segment": SPECTRUM_MIN_CYCLES_IN_SEGMENT,
        "sample_spacing_m": float(sample_spacing_m),
        "median_local_cell_dx_m": median_local_dx,
        "resolution_floor_wavelength_m": resolution_floor,
        "window": "Hann, after subtracting the segment mean",
        "frequency_is_spatial_inverse_wavelength": True,
        "resolved_modes": records,
        "largest_resolved_amplitude_peak": records[
            int(np.flatnonzero(eligible_indices == peak_index)[0])
        ],
        "warning": (
            "Eulerian spatial spectrum only; 0.1 s saved-time cadence does not resolve "
            "millisecond waves or a Lagrangian temporal growth rate"
        ),
    }


def section_profile(
    centres: NDArray[np.float64],
    bounds: NDArray[np.float64],
    volumes: NDArray[np.float64],
    alpha: NDArray[np.float64],
    *,
    z_m: float,
    x_edges_m: NDArray[np.float64],
    dz_m: float = SECTION_DZ_M,
    y_limits_m: tuple[float, float] = SECTION_Y_LIMITS_M,
) -> dict[str, Any]:
    """Estimate water-equivalent sheet thickness and transverse displacement."""
    lower, upper = bounds[:, :3], bounds[:, 3:]
    cell_widths = np.maximum(upper - lower, np.finfo(float).tiny)
    z_band = (z_m - dz_m / 2.0, z_m + dz_m / 2.0)
    frac_z = _intersect_fraction(lower[:, 2], upper[:, 2], z_band)
    frac_y = _intersect_fraction(lower[:, 1], upper[:, 1], y_limits_m)
    x_index = np.searchsorted(x_edges_m, centres[:, 0], side="right") - 1
    bin_count = len(x_edges_m) - 1
    in_x = (x_index >= 0) & (x_index < bin_count)
    selected = in_x & (frac_z > 0.0) & (frac_y > 0.0)
    water_weight = alpha * volumes * frac_z * frac_y
    dense = selected & (alpha >= 0.5) & (water_weight > 0.0)
    dilute = selected & (alpha >= 0.001) & (water_weight > 0.0)
    x_centres = 0.5 * (x_edges_m[:-1] + x_edges_m[1:])
    thickness = np.full(bin_count, np.nan)
    centre_y = np.full(bin_count, np.nan)
    envelope_low = np.full(bin_count, np.nan)
    envelope_high = np.full(bin_count, np.nan)
    count = np.zeros(bin_count, dtype=np.int64)
    dense_count = np.zeros(bin_count, dtype=np.int64)
    median_dx = np.full(bin_count, np.nan)
    for index in range(bin_count):
        cell_mask = selected & (x_index == index)
        if np.any(cell_mask):
            median_dx[index] = float(np.median(cell_widths[cell_mask, 0]))
        core_mask = dense & (x_index == index)
        if np.any(core_mask):
            weights = water_weight[core_mask]
            total = float(np.sum(weights, dtype=np.float64))
            thickness[index] = total / ((x_edges_m[index + 1] - x_edges_m[index]) * dz_m)
            centre_y[index] = float(np.sum(centres[core_mask, 1] * weights) / total)
            dense_count[index] = int(np.count_nonzero(core_mask))
        dilute_mask = dilute & (x_index == index)
        if np.any(dilute_mask):
            count[index] = int(np.count_nonzero(dilute_mask))
            envelope_low[index] = float(np.min(centres[dilute_mask, 1]))
            envelope_high[index] = float(np.max(centres[dilute_mask, 1]))
    valid = np.isfinite(centre_y)
    if np.any(valid):
        mean_y = float(np.mean(centre_y[valid]))
        roughness_rms = float(np.sqrt(np.mean((centre_y[valid] - mean_y) ** 2)))
    else:
        mean_y = None
        roughness_rms = None
    spectrum = spectrum_from_profile(
        x_centres,
        centre_y,
        valid,
        sample_spacing_m=float(np.median(np.diff(x_edges_m))),
        local_cell_dx_m=np.where(np.isfinite(median_dx), median_dx, np.median(np.diff(x_edges_m))),
    )
    records = []
    for index, x in enumerate(x_centres):
        records.append(
            {
                "x_center_m": float(x),
                "sheet_center_y_m": float(centre_y[index]) if valid[index] else None,
                "water_equivalent_thickness_m": (
                    float(thickness[index]) if np.isfinite(thickness[index]) else None
                ),
                "alpha001_envelope_y_min_m": (
                    float(envelope_low[index]) if np.isfinite(envelope_low[index]) else None
                ),
                "alpha001_envelope_y_max_m": (
                    float(envelope_high[index]) if np.isfinite(envelope_high[index]) else None
                ),
                "alpha001_cell_count": int(count[index]),
                "alpha05_cell_count": int(dense_count[index]),
                "median_cell_dx_m": float(median_dx[index])
                if np.isfinite(median_dx[index])
                else None,
            }
        )
    valid_thickness = thickness[np.isfinite(thickness)]
    envelope_widths = envelope_high - envelope_low
    valid_width = np.isfinite(envelope_widths)
    return {
        "z_center_m": float(z_m),
        "section_band_m": [z_band[0], z_band[1]],
        "x_domain_m": [float(x_edges_m[0]), float(x_edges_m[-1])],
        "x_bin_spacing_m": float(np.median(np.diff(x_edges_m))),
        "transverse_limits_m": list(y_limits_m),
        "profile_method": (
            "cells assigned by center x-bin; alpha*native_volume weighted after AABB overlap "
            "fractions in the fixed z band and y window; divide by bin_width*band_depth. "
            "This is an Eulerian water-equivalent thickness estimate, not an isosurface thickness."
        ),
        "disturbance_method": (
            "alpha>=0.5 water-volume centroid in transverse y for each x bin; RMS about the "
            "section mean with no temporal or Lagrangian fit"
        ),
        "occupied_alpha001_bin_count": int(np.count_nonzero(count)),
        "dense_alpha05_bin_count": int(np.count_nonzero(valid)),
        "total_x_bin_count": int(bin_count),
        "dense_bin_fraction": float(np.count_nonzero(valid) / bin_count),
        "mean_dense_sheet_center_y_m": mean_y,
        "transverse_centerline_spatial_roughness_rms_m": roughness_rms,
        "water_equivalent_thickness_m": (
            {
                "p50_across_dense_bins": float(np.quantile(valid_thickness, 0.50)),
                "p90_across_dense_bins": float(np.quantile(valid_thickness, 0.90)),
                "maximum_across_dense_bins": float(np.max(valid_thickness)),
            }
            if len(valid_thickness)
            else {"status": "missing", "reason": "no alpha>=0.5 cells in the section"}
        ),
        "alpha001_center_sample_envelope_width_m": (
            {
                "p50_across_occupied_bins": float(np.quantile(envelope_widths[valid_width], 0.50)),
                "p90_across_occupied_bins": float(np.quantile(envelope_widths[valid_width], 0.90)),
                "maximum_across_occupied_bins": float(np.max(envelope_widths[valid_width])),
            }
            if np.any(valid_width)
            else {"status": "missing", "reason": "no alpha>=0.001 cells in the section"}
        ),
        "spatial_displacement_spectrum": spectrum,
        "profile": records,
    }


def mesh_transition_profile(
    centres: NDArray[np.float64],
    bounds: NDArray[np.float64],
    *,
    z_m: float,
    x_edges_m: NDArray[np.float64],
    declared_refinement_region_x_analysis_m: tuple[float, float] | None,
    dz_m: float = SECTION_DZ_M,
) -> dict[str, Any]:
    lower, upper = bounds[:, :3], bounds[:, 3:]
    widths = np.maximum(upper - lower, np.finfo(float).tiny)
    frac_z = _intersect_fraction(lower[:, 2], upper[:, 2], (z_m - dz_m / 2.0, z_m + dz_m / 2.0))
    roi_y = _intersect_fraction(lower[:, 1], upper[:, 1], (-1.5, 1.5)) > 0.0
    x_index = np.searchsorted(x_edges_m, centres[:, 0], side="right") - 1
    records = []
    h_median = np.full(len(x_edges_m) - 1, np.nan)
    for index in range(len(h_median)):
        mask = (x_index == index) & (frac_z > 0.0) & roi_y & (centres[:, 2] <= 0.0)
        if np.any(mask):
            local = np.max(widths[mask], axis=1)
            h_median[index] = float(np.median(local))
            records.append(
                {
                    "x_center_m": float(0.5 * (x_edges_m[index] + x_edges_m[index + 1])),
                    "cell_count": int(np.count_nonzero(mask)),
                    "median_max_axis_width_m": float(np.median(local)),
                    "p90_max_axis_width_m": float(np.quantile(local, 0.90)),
                    "median_width_xyz_m": np.median(widths[mask], axis=0).tolist(),
                }
            )
        else:
            records.append(
                {
                    "x_center_m": float(0.5 * (x_edges_m[index] + x_edges_m[index + 1])),
                    "cell_count": 0,
                    "median_max_axis_width_m": None,
                    "p90_max_axis_width_m": None,
                    "median_width_xyz_m": None,
                }
            )
    occupied = [
        index
        for index, record in enumerate(records)
        if record["cell_count"] >= 3 and np.isfinite(h_median[index])
    ]
    transitions = []
    for left_index, right_index in zip(occupied, occupied[1:]):
        left, right = h_median[left_index], h_median[right_index]
        left_x = records[left_index]["x_center_m"]
        right_x = records[right_index]["x_center_m"]
        gap = right_x - left_x
        if (
            gap <= MESH_TRANSITION_MAX_EMPTY_BIN_GAP_M + 1e-12
            and max(left, right) / min(left, right) >= 1.75
        ):
            transitions.append(
                {
                    "method": (
                        "bracketed by nearest nonempty mesh-profile bins with at least three cells "
                        "each; bins may be separated by up to four 0.15 m profile steps"
                    ),
                    "x_bracket_m": [float(left_x), float(right_x)],
                    "x_midpoint_m": float(0.5 * (left_x + right_x)),
                    "bracket_width_m": float(gap),
                    "location_half_bracket_uncertainty_m": float(0.5 * gap),
                    "left_median_max_axis_width_m": float(left),
                    "right_median_max_axis_width_m": float(right),
                    "size_ratio": float(max(left, right) / min(left, right)),
                }
            )
    return {
        "method": (
            "median largest cell AABB width in each streamwise bin, for cells intersecting the "
            "same z band and y window; transition flags compare consecutive nonempty bins with "
            "at least three cells each, separated by no more than four profile steps, and flag "
            "a median-size ratio >=1.75; the midpoint is only a bracket summary"
        ),
        "profile_x_domain_m": [float(x_edges_m[0]), float(x_edges_m[-1])],
        "profile_x_bin_spacing_m": float(np.median(np.diff(x_edges_m))),
        "maximum_gap_between_compared_bins_m": MESH_TRANSITION_MAX_EMPTY_BIN_GAP_M,
        "declared_refinement_region_x_analysis_m": (
            list(declared_refinement_region_x_analysis_m)
            if declared_refinement_region_x_analysis_m is not None
            else None
        ),
        "transition_flags": transitions,
        "profile": records,
    }


def analyze_time(
    spec: CaseSpec,
    raw_export: Path,
    snapshot: dict[str, Any],
    time_s: float,
    x_edges_m: NDArray[np.float64],
    mesh_x_edges_m: NDArray[np.float64],
    x_shift_to_leading_edge_m: float,
    declared_refinement_region_x_analysis_m: tuple[float, float] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, NDArray[np.float64]]]:
    fields, hashes = read_rank_fields(spec, raw_export, snapshot["cell_global_ids"], time_s)
    alpha = fields["alpha.water"]
    volumes = snapshot["cell_volumes_m3"]
    centres = snapshot["cell_centres_xyz_m"]
    bounds = snapshot["cell_bounds_minmax_xyz_m"]
    turbulence, shear, interface_mask = turbulence_and_shear_summary(
        snapshot, fields, x_shift_to_leading_edge_m=x_shift_to_leading_edge_m
    )
    analysis_centres, analysis_bounds = shift_x_to_opening_leading_edge(
        centres, bounds, x_shift_to_leading_edge_m
    )
    mass_result = {
        "alpha_water_volume_m3": float(np.sum(alpha * volumes, dtype=np.float64)),
        "raw_alpha_minimum": float(np.min(alpha)),
        "raw_alpha_maximum": float(np.max(alpha)),
        "alpha_outside_unit_interval_count": int(np.count_nonzero((alpha < 0.0) | (alpha > 1.0))),
        "alpha_values_clipped": False,
    }
    sections = []
    all_profiles = []
    for z_m in SECTION_Z_M:
        section = section_profile(
            analysis_centres, analysis_bounds, volumes, alpha, z_m=z_m, x_edges_m=x_edges_m
        )
        mesh_profile = mesh_transition_profile(
            analysis_centres,
            analysis_bounds,
            z_m=z_m,
            x_edges_m=mesh_x_edges_m,
            declared_refinement_region_x_analysis_m=declared_refinement_region_x_analysis_m,
        )
        section["mesh_profile"] = mesh_profile
        transitions = [float(record["x_midpoint_m"]) for record in mesh_profile["transition_flags"]]
        displacement_by_bin = {
            row["x_center_m"]: row["sheet_center_y_m"] for row in section["profile"]
        }
        near_transition = []
        for x_boundary in transitions:
            within_aperture = float(x_edges_m[0]) <= x_boundary <= float(x_edges_m[-1])
            if within_aperture:
                nearest_x = min(displacement_by_bin, key=lambda value: abs(value - x_boundary))
                near_transition.append(
                    {
                        "transition_x_m": x_boundary,
                        "within_aperture": True,
                        "nearest_profile_x_m": nearest_x,
                        "nearest_profile_distance_m": abs(nearest_x - x_boundary),
                        "sheet_center_y_m": displacement_by_bin[nearest_x],
                    }
                )
            else:
                near_transition.append(
                    {
                        "transition_x_m": x_boundary,
                        "within_aperture": False,
                        "nearest_profile_x_m": None,
                        "nearest_profile_distance_m": None,
                        "sheet_center_y_m": None,
                    }
                )
        section["displacement_at_mesh_transition_flags"] = near_transition
        sections.append(section)
        for row in section["profile"]:
            all_profiles.append(
                {
                    "case": spec.key,
                    "time_s": time_s,
                    "z_center_m": z_m,
                    **row,
                }
            )
    result = {
        "time_s": time_s,
        "coordinate_origin_transform": {
            "solver_source_center_origin_x_shifted_to_aperture_leading_edge_m": x_shift_to_leading_edge_m,
            "section_profile_x_origin": "provisional aperture leading edge at x=0; derived from frozen source_geometry.json bounds",
        },
        "fields_read": ["alpha.water", "U", "k", "epsilon", "nut"],
        "field_input_sha256": hashes,
        "raw_water_volume_and_alpha_range": mass_result,
        "source_connected_turbulence_and_shear": turbulence,
        "fixed_eulerian_sections": sections,
    }
    return result, all_profiles, fields


def _paper_curve_rows(path: Path, independent: bool, figure: str) -> dict[str, NDArray[np.float64]]:
    groups: dict[str, list[list[float]]] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if independent:
                if figure == "Fig. 6(b)":
                    keep = row["figure"] == figure and row["series"] == "dash8_alpha0p001"
                else:
                    keep = (
                        row["figure"] == figure and row["series"] == "dash8_simulation_alpha0p001"
                    )
                if not keep:
                    continue
                segment = row["segment"]
                pair = [float(row["x_value"]), float(row["y_value"])]
            else:
                expected_series = "dash8_t0.5s" if figure == "6" else "dash8_simulation_t0.5s"
                if row["figure"] != figure or row["series_id"] != expected_series:
                    continue
                segment = row["segment_id"]
                pair = [float(row["independent_value"]), float(row["dependent_value"])]
            groups.setdefault(segment, []).append(pair)
    return {key: np.asarray(values, dtype=np.float64) for key, values in groups.items()}


def _unique_x_profile(
    points: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    x_values = points[:, 0]
    unique_x = np.unique(x_values)
    y_mean = np.asarray([np.mean(points[x_values == x, 1]) for x in unique_x])
    return unique_x, y_mean


def _symmetric_nearest_rms(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    distances_squared: list[NDArray[np.float64]] = []
    for start in range(0, len(left), 128):
        block = left[start : start + 128]
        pair = np.sum((block[:, None, :] - right[None, :, :]) ** 2, axis=2)
        distances_squared.append(pair)
    distance_matrix = np.concatenate(distances_squared, axis=0)
    left_min = np.min(distance_matrix, axis=1)
    right_min = np.min(distance_matrix, axis=0)
    return float(np.sqrt(0.5 * (np.mean(left_min) + np.mean(right_min))))


def paper_scale_check() -> dict[str, Any]:
    """Compare the digitized dimensional Fig. 6 and normalized Fig. 7 main trace."""
    primary_path = ROOT / "data/derived/calbrix_dash8_cloud_curves.csv"
    independent_path = ROOT / "data/derived/calbrix_dash8_cloud_curves_independent.csv"
    candidates = {
        "sqrt_provisional_area_1p332_m2_m": math.sqrt(1.332),
        "1p155_m": 1.155,
        "0p566_from_alternative_area_0p32_m2_m": math.sqrt(0.32),
        "0p32_m_length_m": 0.32,
    }
    readers = []
    for label, path, independent in (
        ("primary_digitization", primary_path, False),
        ("independent_digitization", independent_path, True),
    ):
        fig6 = _paper_curve_rows(path, independent, "Fig. 6(b)" if independent else "6")
        fig7 = _paper_curve_rows(path, independent, "Fig. 7" if independent else "7")
        if "1" not in fig6 or "1" not in fig7:
            raise ValueError(f"expected the first plotted Fig. 6/7 trace segment in {path}")
        dimensional = fig6["1"]
        normalized_main = fig7["1"]
        x6, z6 = _unique_x_profile(dimensional)
        x7, z7 = _unique_x_profile(normalized_main)
        measures = {}
        all_fig7 = np.concatenate(list(fig7.values()), axis=0)
        for candidate_key, scale_m in candidates.items():
            normalized_x6 = x6 / scale_m
            normalized_z6 = z6 / scale_m
            common_low = max(float(np.min(normalized_x6)), float(np.min(x7)))
            common_high = min(float(np.max(normalized_x6)), float(np.max(x7)))
            if common_high <= common_low:
                vertical_rms_m = None
                sample_count = 0
            else:
                common_x = np.linspace(common_low, common_high, 300)
                residual = np.interp(common_x, normalized_x6, normalized_z6) - np.interp(
                    common_x, x7, z7
                )
                vertical_rms_m = float(np.sqrt(np.mean(residual**2)) * scale_m)
                sample_count = len(common_x)
            measures[candidate_key] = {
                "scale_m": scale_m,
                "main_segment_same_x_normalized_vertical_rms_m": vertical_rms_m,
                "same_x_interpolation_sample_count": sample_count,
                "all_segments_symmetric_nearest_point_2d_rms_m": _symmetric_nearest_rms(
                    dimensional, all_fig7 * scale_m
                ),
                "interpretation": (
                    "RMS of dimensional Z residual after mapping Fig. 6 y,Z to y/Lc,Z/Lc; "
                    "interpolate both main branches on their common y/Lc interval. The separate "
                    "2-D nearest-point diagnostic includes both disconnected Fig. 7 segments."
                ),
            }
        readers.append(
            {
                "reader": label,
                "source_csv": str(path.relative_to(ROOT)),
                "source_csv_sha256": sha256_file(path),
                "fig6_trace_point_count": int(len(dimensional)),
                "fig7_trace_point_count_by_segment": {
                    key: int(len(value)) for key, value in fig7.items()
                },
                "candidates": measures,
            }
        )
    pdf = (
        ROOT
        / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
    )
    memo = ROOT / "experiments/E2_CALBRIX_SOURCE.md"
    return {
        "classification": "digitization-based inference; not a measured area or source-reported numeric Lc",
        "source": {
            "title": "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers",
            "doi": "https://doi.org/10.1071/WF22147",
            "local_pdf": pdf.name,
            "local_pdf_sha256": sha256_file(pdf),
            "figure_6": "PDF p. 7 / journal p. 1521, panel (b): y=0..2 m, Z=0..3 m, Dash-8 t=0.5 s",
            "figure_7": "PDF p. 8 / journal p. 1522: y/Lc=0..2, Z/Lc=0..2, Dash-8 simulation t=0.5 s",
            "characteristic_length_definition": "PDF p. 7 / journal p. 1521: Lc = sqrt(S)",
            "equation_and_numeric_area_status": (
                "The body defines Lc=sqrt(S), and Eq. (5) defines We_G using Lc; the paper does "
                "not give a numeric tank-exit area S. Table 2 reports We_G and the Eq. (4) fit, "
                "not S."
            ),
            "source_extraction_record": str(memo.relative_to(ROOT)),
            "source_extraction_record_sha256": sha256_file(memo),
            "digitization_calibrations": {
                "primary_fig6_plot_corners_px": [[1359, 340], [2208, 1015]],
                "primary_fig7_plot_corners_px": [[313, 291], [1160, 935]],
                "record_location": "experiments/E2_CALBRIX_SOURCE.md table at lines 325-326",
            },
        },
        "assumed_reference_area_m2": 1.332,
        "sqrt_assumed_reference_area_m": math.sqrt(1.332),
        "alternative_area_m2": 0.32,
        "sqrt_alternative_area_m": math.sqrt(0.32),
        "earlier_0p32_m_length_candidate_note": (
            "0.32 m is separately evaluated as a length to retain the earlier unit ambiguity; "
            "it is not sqrt(0.32 m^2)."
        ),
        "readers": readers,
        "limits": [
            "The two traces are separately digitized raster data; their RMS is an axis-registration diagnostic, not author raw data or an uncertainty interval.",
            "The primary vertical RMS uses the common x/Lc interval of Fig. 7's main connected trace and does not compare through its visible gap or final detached segment.",
            "The symmetric 2-D nearest-point RMS includes all digitized Fig. 7 segments and is more sensitive to branch coverage and the visible endpoint fold.",
            "The computed fit is not a fitted physical input and must not be used as a formal gate pass. No numerical S is recovered.",
        ],
    }


def _case_input_summary(spec: CaseSpec, raw_export: Path) -> dict[str, Any]:
    manifest_path = spec.case_dir.parent / "manifest.json"
    inputs_path = spec.case_dir / "case-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    source_geometry_path = spec.case_dir / "source_geometry.json"
    source_geometry = json.loads(source_geometry_path.read_text(encoding="utf-8"))
    if len(source_geometry.get("sources", [])) != 1:
        raise ValueError(f"expected one declared opening in {source_geometry_path}")
    source_x_bounds = source_geometry["sources"][0]["bounds_m"]["x"]
    x_shift_to_leading_edge_m = -float(source_x_bounds[0])
    refinement_region = case_inputs.get("refinement_region_m")
    if refinement_region is None:
        refinement_region = case_inputs.get("native_mesh", {}).get("local_refinement_band_m")
    declared_refinement_x = (
        [
            float(refinement_region["x"][0]) + x_shift_to_leading_edge_m,
            float(refinement_region["x"][1]) + x_shift_to_leading_edge_m,
        ]
        if refinement_region is not None and "x" in refinement_region
        else None
    )
    export_attempt = json.loads(
        (raw_export.parent / "export_attempt.json").read_text(encoding="utf-8")
    )
    if Path(export_attempt["case_directory"]).resolve() != spec.case_dir.resolve():
        raise ValueError(f"native export case path does not match {spec.case_dir}")
    if export_attempt.get("input_hashes_unchanged") is not True:
        raise ValueError(f"native export did not preserve its source case: {raw_export}")
    rank_count = int(export_attempt["mpi_ranks"])
    exported_time = str(export_attempt["selected_time_requested"])
    verified_hashes, settings = verify_native_export_input_inventory(
        spec.case_dir,
        export_attempt["input_sha256_after"],
        rank_count=rank_count,
        time_name=exported_time,
    )
    return {
        "case_directory": str(spec.case_dir.relative_to(ROOT)),
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256_file(manifest_path),
        "case_inputs": str(inputs_path.relative_to(ROOT)),
        "case_inputs_sha256": sha256_file(inputs_path),
        "source_geometry_file": str(source_geometry_path.relative_to(ROOT)),
        "source_geometry_file_sha256": sha256_file(source_geometry_path),
        "source_geometry_bounds_m": source_geometry["sources"][0]["bounds_m"],
        "source_geometry_origin_transform": {
            "solver_source_center_x_origin_to_aperture_leading_edge_shift_m": x_shift_to_leading_edge_m,
            "method": "minus the frozen source_geometry.json lower x bound; preserves raw solver coordinate in location records",
            "classification": "analysis coordinate transform from declared provisional case geometry",
        },
        "case_revision": manifest.get("revision"),
        "dirty_state": manifest.get("dirty_state"),
        "solver": manifest.get("solver"),
        "container_image": manifest.get("container_image"),
        "completed_utc": manifest.get("finished_utc"),
        "case_input_cell_count": case_inputs.get("mesh_cells_expected"),
        "mesh_topology": case_inputs.get(
            "mesh_topology", case_inputs.get("native_mesh", {}).get("topology")
        ),
        "source_geometry_input": case_inputs.get("source_geometry"),
        "source_geometry_assumption": case_inputs.get("source_geometry_assumption"),
        "declared_refinement_region_solver_m": refinement_region,
        "declared_refinement_region_analysis_m": (
            {
                **{key: value for key, value in refinement_region.items() if key != "x"},
                "x": declared_refinement_x,
            }
            if refinement_region is not None
            else None
        ),
        "air_speed_m_s": case_inputs.get("air_speed_m_s"),
        "export": str(raw_export.relative_to(ROOT)),
        "export_time_s": float(exported_time),
        "export_attempt_sha256": sha256_file(raw_export.parent / "export_attempt.json"),
        "export_input_hashes_verified_count": len(verified_hashes),
        "export_verified_system_settings": list(settings),
        "saved_time_field_hashes_added_by_analysis": "listed per case and time in analysis.json",
    }


def _write_profiles_csv(path: Path, records: list[dict[str, Any]]) -> None:
    columns = (
        "case",
        "time_s",
        "z_center_m",
        "x_center_m",
        "sheet_center_y_m",
        "water_equivalent_thickness_m",
        "alpha001_envelope_y_min_m",
        "alpha001_envelope_y_max_m",
        "alpha001_cell_count",
        "alpha05_cell_count",
        "median_cell_dx_m",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row.get(column) for column in columns} for row in records)


def _render_slices(
    path: Path,
    slices: dict[str, tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        1, len(slices), figsize=(15, 4.2), sharex=True, sharey=True, layout="constrained"
    )
    if len(slices) == 1:
        axes = [axes]
    image = None
    for axis, (key, (x_edges, z_edges, alpha_image)) in zip(axes, slices.items(), strict=True):
        masked = np.ma.masked_invalid(alpha_image)
        image = axis.pcolormesh(
            x_edges, z_edges, masked, cmap="Blues", vmin=0.0, vmax=1.0, shading="flat"
        )
        axis.axvline(SOURCE_EXTENT_M["x"][0], color="black", linewidth=0.7, linestyle=":")
        axis.axvline(SOURCE_EXTENT_M["x"][1], color="black", linewidth=0.7, linestyle=":")
        axis.set_title(key.replace("_", " "))
        axis.set_xlabel("streamwise x (m)")
        axis.grid(alpha=0.15)
    axes[0].set_ylabel("z (m, upward positive)")
    figure.suptitle("Computed center plane y≈0, t=0.4 s; alpha.water (common 0–1 scale)")
    if image is not None:
        figure.colorbar(image, ax=axes, label="alpha.water", shrink=0.84)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _centerline_slice(
    centres: NDArray[np.float64],
    bounds: NDArray[np.float64],
    alpha: NDArray[np.float64],
    *,
    x_shift_to_leading_edge_m: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    centres, bounds = shift_x_to_opening_leading_edge(centres, bounds, x_shift_to_leading_edge_m)
    x_edges = np.arange(-0.3, 8.0001, 0.075)
    z_edges = np.arange(-2.4001, 0.1501, 0.075)
    lower, upper = bounds[:, :3], bounds[:, 3:]
    center_plane = (lower[:, 1] <= 0.0) & (upper[:, 1] >= 0.0)
    selected = (
        center_plane
        & (centres[:, 0] >= x_edges[0])
        & (centres[:, 0] < x_edges[-1])
        & (centres[:, 2] >= z_edges[0])
        & (centres[:, 2] < z_edges[-1])
    )
    x_index = np.searchsorted(x_edges, centres[selected, 0], side="right") - 1
    z_index = np.searchsorted(z_edges, centres[selected, 2], side="right") - 1
    values = alpha[selected]
    image = np.full((len(z_edges) - 1, len(x_edges) - 1), np.nan)
    counts = np.zeros_like(image)
    sums = np.zeros_like(image)
    np.add.at(sums, (z_index, x_index), values)
    np.add.at(counts, (z_index, x_index), 1.0)
    occupied = counts > 0
    image[occupied] = sums[occupied] / counts[occupied]
    return x_edges, z_edges, image


def shift_x_to_opening_leading_edge(
    centres: NDArray[np.float64],
    bounds: NDArray[np.float64],
    shift_m: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Translate native x centers/bounds into the provisional aperture-leading-edge origin."""
    shifted_centres = centres.copy()
    shifted_centres[:, 0] += shift_m
    shifted_bounds = bounds.copy()
    shifted_bounds[:, 0] += shift_m
    shifted_bounds[:, 3] += shift_m
    return shifted_centres, shifted_bounds


def run_analysis(output_dir: Path, *, times_s: tuple[float, ...] = TIMES_S) -> dict[str, Any]:
    started_utc = datetime.now(UTC)
    started_clock = time.perf_counter()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite analysis bundle {output_dir}")
    output_dir.mkdir(parents=True)
    x_edges = np.arange(0.0, SOURCE_EXTENT_M["x"][1] + SECTION_DX_M * 0.5, SECTION_DX_M)
    if not math.isclose(float(x_edges[-1]), SOURCE_EXTENT_M["x"][1], abs_tol=1e-12):
        x_edges = np.r_[x_edges[x_edges < SOURCE_EXTENT_M["x"][1]], SOURCE_EXTENT_M["x"][1]]
    mesh_x_edges = np.arange(
        MESH_TRANSITION_X_DOMAIN_M[0],
        MESH_TRANSITION_X_DOMAIN_M[1] + SECTION_DX_M * 0.5,
        SECTION_DX_M,
    )
    analyses: dict[str, Any] = {}
    all_profiles: list[dict[str, Any]] = []
    slice_images = {}
    source_hashes: dict[str, str] = {}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    for key, raw_spec in CASE_SPECS.items():
        spec = CaseSpec(
            key=key,
            label=raw_spec["label"],
            case_dir=(ROOT / raw_spec["case"]).resolve(),
            export_dir=(ROOT / raw_spec["export"]).resolve(),
        )
        raw_export = spec.export_dir
        input_summary = _case_input_summary(spec, raw_export)
        x_shift_to_leading_edge_m = float(
            input_summary["source_geometry_origin_transform"][
                "solver_source_center_x_origin_to_aperture_leading_edge_shift_m"
            ]
        )
        declared_refinement_region_x_analysis_m = input_summary[
            "declared_refinement_region_analysis_m"
        ]
        if declared_refinement_region_x_analysis_m is not None:
            declared_refinement_region_x_analysis_m = tuple(
                declared_refinement_region_x_analysis_m["x"]
            )
        snapshot, export_hashes = load_export(raw_export)
        if snapshot["topology"]["native_cells"] != input_summary["case_input_cell_count"]:
            raise ValueError(f"native export cell count disagrees with case metadata for {key}")
        case_times = []
        for time_s in times_s:
            result, profiles, fields = analyze_time(
                spec,
                raw_export,
                snapshot,
                time_s,
                x_edges,
                mesh_x_edges,
                x_shift_to_leading_edge_m,
                declared_refinement_region_x_analysis_m,
            )
            case_times.append(result)
            all_profiles.extend(profiles)
            source_hashes.update(
                {
                    f"{key}/{relative}": digest
                    for relative, digest in result["field_input_sha256"].items()
                }
            )
            if math.isclose(time_s, 0.4, rel_tol=0.0, abs_tol=1e-9):
                slice_images[key] = _centerline_slice(
                    snapshot["cell_centres_xyz_m"],
                    snapshot["cell_bounds_minmax_xyz_m"],
                    fields["alpha.water"],
                    x_shift_to_leading_edge_m=x_shift_to_leading_edge_m,
                )
            del fields
        verify_field_hashes(
            spec.case_dir,
            {k: v for entry in case_times for k, v in entry["field_input_sha256"].items()},
        )
        analyses[key] = {
            "label": spec.label,
            "input_provenance": input_summary,
            "native_cell_count": int(snapshot["topology"]["native_cells"]),
            "source_connected_component_method": "native OpenFOAM face connectivity from verified read-only export",
            "time_records": case_times,
            "native_export_input_hashes_sha256": export_hashes,
        }
        del snapshot
    profile_path = output_dir / "section_profiles.csv"
    _write_profiles_csv(profile_path, all_profiles)
    slice_path = output_dir / "centerplane_alpha_t0p4.png"
    _render_slices(slice_path, slice_images)
    pdf = (
        ROOT
        / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
    )
    memo = ROOT / "experiments/E2_CALBRIX_SOURCE.md"
    result = {
        "schema": SCHEMA,
        "created_utc": datetime.now(UTC).isoformat(),
        "execution": {
            "started_utc": started_utc.isoformat(),
            "elapsed_wall_s": time.perf_counter() - started_clock,
            "cpu_threads_requested": 1,
            "gpu_used": False,
            "command": "OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/analyze_dash8_interface_growth.py",
            "method": "read-only native field parsing, face-connectivity diagnostics, and CPU plotting; no OpenFOAM solver or GPU operation",
        },
        "analysis_classification": "numerical observer outputs from previously completed exploratory CFD runs",
        "decision_status": "evidence and proposed next diagnostic criteria only; no E0-E6 gate decision",
        "coordinate_frame": {
            "axes": "x streamwise, y transverse, z upward; SI metres; velocity components are signed x/y/z",
            "aperture_extent_m": SOURCE_EXTENT_M,
            "origin": "derived profiles use x=0 at the provisional aperture leading edge, x=4.44 m at its trailing edge, y=-0.15..0.15 m, z=0 at the outlet plane; the original OpenFOAM source is centered at solver x=0 and is preserved in input hashes",
            "solver_to_analysis_x_transform": "x_analysis = x_solver - x_source_lower_bound; for these frozen cases, x_source_lower_bound=-2.22 m, so x_analysis=x_solver+2.22 m",
        },
        "source_and_assumption_register": {
            "measured_inputs": [],
            "digitized_inputs": [],
            "assumed_case_inputs": [
                {
                    "value": "source geometry and inlet profile as frozen in each case case-inputs.json",
                    "classification": "assumed/provisional CFD setup, not field measurement",
                    "provenance": "case-specific path and SHA-256 in each input_provenance record",
                },
                {
                    "value": "source area 1.332 m^2 from the provisional 4.44 m x 0.30 m rectangular opening",
                    "classification": "assumed/provisional project geometry, not a published Dash-8 outlet area",
                    "provenance": "experiments/E2_CALBRIX_SOURCE.md, PDF p.4 Fig.2 and PDF p.5 Fig.3 interpretation; numeric exit area remains unstated by the paper",
                },
                {
                    "value": "water density 1000 kg/m^3 where relevant to the case mass convention",
                    "classification": "reported source value, not a new measurement",
                    "provenance": "Calbrix local PDF p.4 / journal p.1518, Domains and meshes; DOI 10.1071/WF22147",
                },
            ],
            "fitted_inputs": [],
            "missing_inputs": [
                "The paper does not report a numeric Dash-8 exit area S, exact patch outline, or complete wall and turbulence boundary settings; this observer does not infer them.",
                "0.1 s saved-time spacing cannot resolve millisecond-scale interface amplification or support a temporal growth-rate fit.",
                "The α-volume thickness and center-plane plots use cell-center and AABB overlap assumptions; they are estimates on the native polyhedral mesh, not reconstructed subcell interfaces.",
            ],
        },
        "paper_fig6_fig7_scale_check": paper_scale_check(),
        "sampling_and_spatial_resolution": {
            "saved_times_s": list(times_s),
            "saved_output_interval_s": 0.1,
            "section_x_bin_spacing_m": SECTION_DX_M,
            "section_band_thickness_m": SECTION_DZ_M,
            "spectrum_minimum_wavelength_rule": "at least four x samples and four local median x-cell widths; no interpolation across missing x bins",
            "spectrum_longest_wavelength_rule": "at least two cycles must fit inside the longest contiguous observed segment",
            "temporal_growth_rate_status": "not identifiable from these saved fields",
            "interpretation": "reported disturbance quantities are spatial variation at fixed Eulerian z sections, not Lagrangian gamma or amplification of a tagged wave",
        },
        "cases": analyses,
        "derived_profile_csv": {
            "path": profile_path.name,
            "sha256": sha256_file(profile_path),
            "classification": "derived numerical profiles; definitions are recorded per section in analysis.json",
        },
        "rendered_center_plane_slices": {
            "path": slice_path.name,
            "sha256": sha256_file(slice_path),
            "fields": "computed alpha.water at t=0.4 s; common 0..1 scale; native cell values binned at y=0 center plane",
            "classification": "computed fields, display-binned for inspection",
        },
        "input_field_sha256_count": len(source_hashes),
        "input_field_sha256_manifest": source_hashes,
        "source_pdf_sha256": sha256_file(pdf),
        "source_memo_sha256": sha256_file(memo),
        "proposed_follow_on_gate_criteria": [
            "Before estimating a temporal growth rate, save at least 10 samples over the shortest candidate e-folding time and demonstrate that the fitted rate is stable to halving both output interval and time step; report the fitted interval and uncertainty as a proposed diagnostic, not as a source measurement.",
            "For spatial disturbance convergence, compare matched perturbation spectra on three nested meshes with at least eight cells per shortest reported wavelength; evaluate only wavelengths resolved on every mesh and report the native cell-size profile and transition locations alongside each peak.",
            "For connected-sheet thickness, predeclare the alpha definition and cross-section, then require the profile and median thickness to change by less than the finer-grid cell width on the next refinement; keep dilute-envelope width separate from water-equivalent thickness.",
            "Require interface shear and k/epsilon/nut distributions to be finite, mapped to a declared source-connected interface mask, and stable under the same mesh refinement before treating them as physical near-interface evidence; this does not independently validate the turbulence model.",
        ],
        "gate_statement": "These proposed criteria are not predeclared acceptance tolerances, no formal gate is passed, and this observer does not establish field validity.",
    }
    output_path = output_dir / "analysis.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT
        / "results/runs"
        / f"dash8-interface-growth-analysis-{datetime.now(UTC):%Y%m%dt%H%M%SZ}",
        help="new ignored run bundle; existing directories are never overwritten",
    )
    parser.add_argument(
        "--times",
        nargs="+",
        type=float,
        default=list(TIMES_S),
        help="saved field times to read; defaults to early samples plus terminal t=1 s",
    )
    args = parser.parse_args(argv)
    try:
        result = run_analysis(args.output_dir.resolve(), times_s=tuple(args.times))
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Dash-8 interface-growth analysis failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "case_count": len(result["cases"]),
                "time_count_per_case": len(args.times),
                "field_hash_count": result["input_field_sha256_count"],
                "gate_status": result["decision_status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
