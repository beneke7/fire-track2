#!/usr/bin/env python3
"""Summarize saved k, epsilon and nut on an exported native OpenFOAM mesh.

The saved volScalarField internal lists are paired with each rank's exported
cell_global_ids in native local-cell order, then reordered by global ID. This
is a descriptive field observer; it does not close turbulence equations or
attribute a field value to a particular production/diffusion mechanism.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_native_vof import load_export  # noqa: E402

OUTPUT_SCHEMA = "fire-track2-native-turbulence-analysis-v1"
TIME_TOLERANCE_S = 5e-10
FIELD_DIMENSIONS = {
    "k": "0 2 -2 0 0 0 0",
    "epsilon": "0 2 -3 0 0 0 0",
    "nut": "0 2 -1 0 0 0 0",
}
FIELD_UNITS_SI = {"k": "m^2 s^-2", "epsilon": "m^2 s^-3", "nut": "m^2 s^-1"}
QUANTILE_LEVELS = (0.05, 0.5, 0.95)
_NUMBER = rb"[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?|[+-]?(?:nan|inf(?:inity)?)"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _header_value(header: bytes, key: str) -> str:
    if key == "arch":
        quoted = re.search(rb'(?m)^\s*arch\s+"([^"]+)"\s*;', header)
        if not quoted:
            raise ValueError("OpenFOAM field header lacks arch")
        return quoted.group(1).decode("ascii").strip()
    match = re.search(rb"(?<!\S)" + key.encode("ascii") + rb"\s+([^;]+);", header)
    if not match:
        raise ValueError(f"OpenFOAM field header lacks {key}")
    return match.group(1).decode("ascii").strip().strip('"')


def read_foam_scalar_internal(
    path: Path,
    *,
    expected_count: int,
    expected_object: str,
    expected_location: str,
    expected_dimensions: str,
) -> NDArray[np.float64]:
    """Read a uniform or nonuniform scalar internalField from ASCII/binary FOAM."""
    data = path.read_bytes()
    foam_header = re.search(rb"FoamFile\s*\{(.*?)\}", data, flags=re.DOTALL)
    if foam_header is None:
        raise ValueError(f"missing FoamFile header in {path}")
    header = foam_header.group(1)
    if _header_value(header, "class") != "volScalarField":
        raise ValueError(f"{path} is not a volScalarField")
    if _header_value(header, "object") != expected_object:
        raise ValueError(f"{path} object name does not match {expected_object}")
    location = _header_value(header, "location")
    try:
        location_value = float(location)
        expected_location_value = float(expected_location)
    except ValueError as error:
        raise ValueError(f"invalid OpenFOAM field location in {path}: {location!r}") from error
    if not math.isclose(
        location_value, expected_location_value, rel_tol=0.0, abs_tol=TIME_TOLERANCE_S
    ):
        raise ValueError(
            f"{path} header location {location!r} does not match {expected_location!r}"
        )
    dimensions_match = re.search(rb"\bdimensions\s*\[([^\]]+)\]", data[: foam_header.end() + 4096])
    if dimensions_match is None:
        raise ValueError(f"{path} has no dimensions entry before internalField")
    dimensions = " ".join(dimensions_match.group(1).decode("ascii").split())
    if dimensions != expected_dimensions:
        raise ValueError(f"{path} dimensions {dimensions!r} do not match {expected_dimensions!r}")

    field_format = _header_value(header, "format")
    if field_format not in {"ascii", "binary"}:
        raise ValueError(f"unsupported OpenFOAM field format {field_format!r} in {path}")

    uniform = re.search(rb"\binternalField\s+uniform\s+(" + _NUMBER + rb")\s*;", data)
    if uniform is not None:
        values = np.full(expected_count, float(uniform.group(1)), dtype=np.float64)
        return values

    nonuniform = re.search(rb"\binternalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(", data)
    if nonuniform is None:
        raise ValueError(f"{path} has an unsupported internalField representation")
    count = int(nonuniform.group(1))
    if count != expected_count:
        raise ValueError(f"{path} internalField has {count} values; expected {expected_count}")
    payload_start = nonuniform.end()
    if field_format == "binary":
        arch = _header_value(header, "arch")
        scalar_bits = re.search(r"(?:^|;)scalar=(\d+)(?:;|$)", arch)
        if scalar_bits is None or int(scalar_bits.group(1)) != 64:
            raise ValueError(f"unsupported binary scalar precision in {path}: {arch!r}")
        byte_order = "<" if arch.startswith("LSB") else ">" if arch.startswith("MSB") else None
        if byte_order is None:
            raise ValueError(f"unsupported binary byte order in {path}: {arch!r}")
        payload_end = payload_start + count * 8
        if payload_end > len(data):
            raise ValueError(f"truncated binary internalField in {path}")
        trailer = data[payload_end:].lstrip(b" \t\r\n")
        if not trailer.startswith(b")"):
            raise ValueError(f"binary internalField closing parenthesis is missing in {path}")
        after_close = trailer[1:].lstrip(b" \t\r\n")
        if not after_close.startswith(b";"):
            raise ValueError(f"binary internalField terminator is missing in {path}")
        return np.frombuffer(
            data, dtype=np.dtype(f"{byte_order}f8"), count=count, offset=payload_start
        ).astype(np.float64, copy=True)

    payload_end = data.find(b")", payload_start)
    if payload_end < 0:
        raise ValueError(f"ASCII internalField closing parenthesis is missing in {path}")
    try:
        tokens = data[payload_start:payload_end].decode("ascii").split()
    except UnicodeDecodeError as error:
        raise ValueError(f"ASCII internalField contains non-ASCII bytes in {path}") from error
    if len(tokens) != count:
        raise ValueError(f"{path} internalField has {len(tokens)} ASCII values; expected {count}")
    after_close = data[payload_end + 1 :].lstrip(b" \t\r\n")
    if not after_close.startswith(b";"):
        raise ValueError(f"ASCII internalField terminator is missing in {path}")
    try:
        return np.asarray([float(token) for token in tokens], dtype=np.float64)
    except ValueError as error:
        raise ValueError(f"ASCII internalField contains a non-scalar token in {path}") from error


def _safe_hash_inventory(root: Path, inventory: dict[str, str]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative, expected in sorted(inventory.items()):
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"unsafe path in native export input hash inventory: {relative}")
        path = root / rel
        if not path.is_file():
            raise ValueError(f"exported input is missing: {path}")
        digest = sha256_file(path)
        if digest != expected:
            raise ValueError(f"case input changed since native export: {relative}")
        actual[relative] = digest
    return actual


def _validate_run_and_export(
    case_dir: Path, export_dir: Path, requested_time_s: float
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    case_dir = case_dir.resolve(strict=True)
    export_dir = export_dir.resolve(strict=True)
    manifest_path = case_dir.parent / "manifest.json"
    case_inputs_path = case_dir / "case-inputs.json"
    export_attempt_path = export_dir.parent / "export_attempt.json"
    for path, label in (
        (manifest_path, "run manifest"),
        (case_inputs_path, "case inputs"),
        (export_attempt_path, "native export attempt"),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"missing {label}: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_inputs = json.loads(case_inputs_path.read_text(encoding="utf-8"))
    export_attempt = json.loads(export_attempt_path.read_text(encoding="utf-8"))
    if manifest.get("status") not in {"exploratory_completed", "solver_completed"}:
        raise ValueError(f"run manifest is not a completed solver run: {manifest.get('status')!r}")
    if int(manifest.get("exit_code", manifest.get("solver_exit_code", -1))) != 0:
        raise ValueError("completed run manifest does not have exit code zero")
    if manifest.get("run_id") != case_dir.parent.name:
        raise ValueError("run manifest ID does not match the case directory")
    prepared_case_hashes = manifest.get("prepared_case_sha256")
    if not isinstance(prepared_case_hashes, dict) or not prepared_case_hashes:
        raise ValueError("run manifest lacks its frozen prepared-case SHA-256 inventory")
    _safe_hash_inventory(case_dir, prepared_case_hashes)
    if export_attempt.get("status") != "complete" or export_attempt.get("return_code") != 0:
        raise ValueError("native export attempt did not complete successfully")
    if not export_attempt.get("input_hashes_unchanged"):
        raise ValueError("native export reported changed case inputs")
    if Path(export_attempt.get("case_directory", "")).resolve(strict=True) != case_dir:
        raise ValueError("native export was produced from a different case directory")
    if not math.isclose(
        float(export_attempt.get("selected_time_requested", math.nan)),
        requested_time_s,
        rel_tol=0.0,
        abs_tol=TIME_TOLERANCE_S,
    ):
        raise ValueError("native export request time differs from --time-s")
    ranks = int(case_inputs.get("ranks", -1))
    if ranks <= 0 or int(export_attempt.get("mpi_ranks", -1)) != ranks:
        raise ValueError("case and native export rank counts disagree")
    if case_inputs.get("solver") != "interIsoFoam":
        raise ValueError("case is not the expected interIsoFoam VOF run")

    before = export_attempt.get("input_sha256_before")
    after = export_attempt.get("input_sha256_after")
    if not isinstance(before, dict) or not isinstance(after, dict) or before != after:
        raise ValueError("export attempt lacks matching before/after case-input hashes")
    _safe_hash_inventory(case_dir, after)
    source_patch = export_attempt.get("source_patch")
    areas = case_inputs.get("source_patch_areas_m2", {})
    if not source_patch or source_patch not in areas:
        raise ValueError("case inputs and native export do not identify the same source patch")
    if manifest.get("solver_image_id") and export_attempt.get("image_id") != manifest.get(
        "solver_image_id"
    ):
        raise ValueError("native export image differs from the solver run image")
    return manifest, case_inputs, export_attempt, export_attempt_path


def _validate_box(value: Any) -> dict[str, tuple[float, float]]:
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError("refinement box must declare exactly x, y and z bounds")
    result: dict[str, tuple[float, float]] = {}
    for axis in ("x", "y", "z"):
        bounds = value[axis]
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise ValueError(f"refinement box {axis} bounds must have two values")
        lower, upper = (float(bounds[0]), float(bounds[1]))
        if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
            raise ValueError(f"invalid refinement box {axis} bounds")
        result[axis] = (lower, upper)
    return result


def _validate_rank_metadata(
    metadata: dict[str, Any],
    *,
    expected_rank: int,
    expected_rank_count: int,
    expected_time_name: str,
    expected_time_s: float,
    expected_source_patch: str,
) -> int:
    rank = int(metadata.get("rank", -1))
    local_count = int(metadata.get("local_cell_count", -1))
    if rank != expected_rank or int(metadata.get("rank_count", -1)) != expected_rank_count:
        raise ValueError(f"noncontiguous rank or rank-count mismatch for rank {expected_rank}")
    if metadata.get("time_name") != expected_time_name or not math.isclose(
        float(metadata.get("time_value_s", math.nan)),
        expected_time_s,
        rel_tol=0.0,
        abs_tol=TIME_TOLERANCE_S,
    ):
        raise ValueError(f"rank {rank} export time mismatch")
    if metadata.get("source_patch") != expected_source_patch:
        raise ValueError(f"rank {rank} source-patch mismatch")
    if (
        metadata.get("parallel_global_id_source") != "constant/polyMesh/cellProcAddressing"
        or metadata.get("label_bytes_input") != 4
        or metadata.get("scalar_bytes_input") != 8
        or metadata.get("export_integer_bytes") != 8
        or metadata.get("export_float_bytes") != 8
        or metadata.get("export_byte_order") != "little-endian"
    ):
        raise ValueError(f"rank {rank} native export layout metadata is unsupported")
    if local_count < 0:
        raise ValueError(f"rank {rank} has a negative local cell count")
    return local_count


def align_rank_fields(
    rank_ids: list[NDArray[np.int64]],
    rank_values: dict[str, list[NDArray[np.float64]]],
    expected_global_ids: NDArray[np.int64],
) -> dict[str, NDArray[np.float64]]:
    if not rank_ids:
        raise ValueError("no rank cell IDs were supplied")
    if any(len(values) != len(rank_ids) for values in rank_values.values()):
        raise ValueError("per-rank field inventory does not match cell-ID rank inventory")
    for name, per_rank in rank_values.items():
        if any(len(values) != len(ids) for values, ids in zip(per_rank, rank_ids, strict=True)):
            raise ValueError(f"per-rank {name} values do not match local cell-ID counts")
    concatenated_ids = np.concatenate(rank_ids)
    if len(np.unique(concatenated_ids)) != len(concatenated_ids):
        raise ValueError("duplicate rank cell_global_ids while aligning turbulence values")
    order = np.argsort(concatenated_ids, kind="stable")
    if not np.array_equal(concatenated_ids[order], expected_global_ids):
        raise ValueError("rank cell_global_ids do not match the native loader's global cell order")
    return {name: np.concatenate(per_rank)[order] for name, per_rank in rank_values.items()}


def _weighted_quantile(
    values: NDArray[np.float64], weights: NDArray[np.float64], q: float
) -> float:
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order], dtype=np.float64)
    index = int(np.searchsorted(cumulative, q * cumulative[-1], side="left"))
    return float(sorted_values[min(index, len(sorted_values) - 1)])


def _extreme_record(
    index: int,
    values: NDArray[np.float64],
    weights: NDArray[np.float64],
    alpha: NDArray[np.float64],
    global_ids: NDArray[np.int64],
    centres: NDArray[np.float64],
) -> dict[str, Any]:
    return {
        "value": float(values[index]),
        "cell_global_id": int(global_ids[index]),
        "alpha_water_raw": float(alpha[index]),
        "phase_volume_weight_m3": float(weights[index]),
        "centroid_xyz_m": [float(item) for item in centres[index]],
    }


def _raw_extreme_record(
    index: int,
    values: NDArray[np.float64],
    alpha: NDArray[np.float64],
    global_ids: NDArray[np.int64],
    centres: NDArray[np.float64],
) -> dict[str, Any]:
    return {
        "value": float(values[index]),
        "cell_global_id": int(global_ids[index]),
        "alpha_water_raw": float(alpha[index]),
        "centroid_xyz_m": [float(item) for item in centres[index]],
    }


def _field_statistics(
    values: NDArray[np.float64],
    alpha: NDArray[np.float64],
    volumes: NDArray[np.float64],
    global_ids: NDArray[np.int64],
    centres: NDArray[np.float64],
    mask: NDArray[np.bool_],
) -> dict[str, Any]:
    selected = np.flatnonzero(mask)
    selected_values = values[selected]
    finite = np.isfinite(selected_values)
    finite_indices = selected[finite]
    finite_values = values[finite_indices]
    raw_minimum_index = (
        int(finite_indices[np.argmin(finite_values)]) if len(finite_values) else None
    )
    raw_maximum_index = (
        int(finite_indices[np.argmax(finite_values)]) if len(finite_values) else None
    )
    result: dict[str, Any] = {
        "selected_cell_count": int(len(selected)),
        "finite_value_count": int(np.count_nonzero(finite)),
        "nonfinite_value_count": int(len(selected) - np.count_nonzero(finite)),
        "negative_value_count": int(np.count_nonzero(selected_values[finite] < 0.0)),
        "raw_finite_min": float(np.min(finite_values)) if len(finite_values) else None,
        "raw_finite_max": float(np.max(finite_values)) if len(finite_values) else None,
        "raw_finite_min_location": (
            _raw_extreme_record(raw_minimum_index, values, alpha, global_ids, centres)
            if raw_minimum_index is not None
            else None
        ),
        "raw_finite_max_location": (
            _raw_extreme_record(raw_maximum_index, values, alpha, global_ids, centres)
            if raw_maximum_index is not None
            else None
        ),
        "raw_values_clipped": False,
        "phase_weights": {},
    }
    for phase, phase_weights in (
        ("water_volume_weighted", alpha * volumes),
        ("air_volume_weighted", (1.0 - alpha) * volumes),
    ):
        selected_weights = phase_weights[selected]
        positive = np.isfinite(selected_weights) & (selected_weights > 0.0)
        supported_finite = positive & finite
        support_indices = selected[supported_finite]
        support_values = values[support_indices]
        support_weights = phase_weights[support_indices]
        phase_report: dict[str, Any] = {
            "signed_phase_weight_sum_m3": float(np.sum(selected_weights, dtype=np.float64)),
            "positive_phase_weight_sum_m3": float(
                np.sum(selected_weights[positive], dtype=np.float64)
            ),
            "negative_phase_weight_sum_m3": float(
                np.sum(selected_weights[selected_weights < 0.0], dtype=np.float64)
            ),
            "positive_weight_cell_count": int(np.count_nonzero(positive)),
            "zero_weight_cell_count": int(np.count_nonzero(selected_weights == 0.0)),
            "negative_weight_cell_count": int(np.count_nonzero(selected_weights < 0.0)),
            "positive_weight_nonfinite_value_count": int(np.count_nonzero(positive & ~finite)),
            "distribution_method": (
                "weighted by positive raw alpha*V or (1-alpha)*V; nonpositive weights are "
                "reported and excluded from the nonnegative weighted distribution"
            ),
        }
        if len(support_values):
            minimum_local = int(np.argmin(support_values))
            maximum_local = int(np.argmax(support_values))
            phase_report.update(
                {
                    "status": "computed",
                    "finite_positive_weight_cell_count": int(len(support_values)),
                    "weighted_mean": float(
                        np.sum(support_values * support_weights, dtype=np.float64)
                        / np.sum(support_weights, dtype=np.float64)
                    ),
                    "weighted_quantiles": {
                        f"p{round(q * 100):02d}": _weighted_quantile(
                            support_values, support_weights, q
                        )
                        for q in QUANTILE_LEVELS
                    },
                    "minimum_on_positive_weight_support": _extreme_record(
                        int(support_indices[minimum_local]),
                        values,
                        phase_weights,
                        alpha,
                        global_ids,
                        centres,
                    ),
                    "maximum_on_positive_weight_support": _extreme_record(
                        int(support_indices[maximum_local]),
                        values,
                        phase_weights,
                        alpha,
                        global_ids,
                        centres,
                    ),
                }
            )
        else:
            phase_report.update(
                {
                    "status": "no_finite_positive_weight_support",
                    "finite_positive_weight_cell_count": 0,
                    "weighted_mean": None,
                    "weighted_quantiles": None,
                    "minimum_on_positive_weight_support": None,
                    "maximum_on_positive_weight_support": None,
                }
            )
        result["phase_weights"][phase] = phase_report
    return result


def summarize_turbulence(
    snapshot: dict[str, Any],
    fields: dict[str, NDArray[np.float64]],
    refinement_box_m: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    alpha = np.asarray(snapshot["alpha_water"], dtype=np.float64)
    volume = np.asarray(snapshot["cell_volumes_m3"], dtype=np.float64)
    gids = np.asarray(snapshot["cell_global_ids"], dtype=np.int64)
    centres = np.asarray(snapshot["cell_centres_xyz_m"], dtype=np.float64)
    if not (alpha.shape == volume.shape == gids.shape == (len(centres),)):
        raise ValueError("native alpha, volumes, IDs and centres do not align")
    n = len(alpha)
    if not np.all(np.isfinite(volume)) or np.any(volume <= 0.0):
        raise ValueError("native cell volumes must be finite and positive")
    if not np.all(np.isfinite(alpha)):
        raise ValueError("native alpha contains nonfinite values; raw alpha is not changed")
    alpha_outside = (alpha < 0.0) | (alpha > 1.0)
    in_box = np.ones(n, dtype=bool)
    for axis_index, axis in enumerate(("x", "y", "z")):
        low, high = refinement_box_m[axis]
        in_box &= (centres[:, axis_index] >= low) & (centres[:, axis_index] <= high)
    masks = {
        "all_cells": np.ones(n, dtype=bool),
        "pure_air_alpha_le_0p001": alpha <= 0.001,
        "interface_0p001_lt_alpha_lt_0p999": (alpha > 0.001) & (alpha < 0.999),
        "liquid_core_alpha_ge_0p999": alpha >= 0.999,
    }
    region_masks = {
        "whole_domain": np.ones(n, dtype=bool),
        "source_refinement_box_cell_centres": in_box,
    }
    region_reports: dict[str, Any] = {}
    for region_name, region_mask in region_masks.items():
        region_reports[region_name] = {
            "cell_count": int(np.count_nonzero(region_mask)),
            "alpha_outside_unit_interval_count": int(np.count_nonzero(alpha_outside & region_mask)),
            "phase_partition_masks": {},
        }
        for phase_class, class_mask in masks.items():
            selected_mask = region_mask & class_mask
            region_reports[region_name]["phase_partition_masks"][phase_class] = {
                "cell_count": int(np.count_nonzero(selected_mask)),
                "turbulence_fields": {
                    name: _field_statistics(values, alpha, volume, gids, centres, selected_mask)
                    for name, values in fields.items()
                },
            }
    return {
        "cell_count": int(n),
        "alpha_raw_min": float(np.min(alpha)),
        "alpha_raw_max": float(np.max(alpha)),
        "alpha_outside_unit_interval_count": int(np.count_nonzero(alpha_outside)),
        "alpha_raw_values_clipped": False,
        "phase_weight_basis": {
            "water": "raw alpha.water * native cell volume; no density factor",
            "air": "raw (1-alpha.water) * native cell volume; no density factor",
            "interpretation": "phase-volume weighting; constant phase density would not change within-phase normalized statistics",
        },
        "quantiles": {
            "levels": list(QUANTILE_LEVELS),
            "method": "left-continuous weighted empirical CDF over positive raw phase volume weights",
        },
        "refinement_box_m": {axis: list(bounds) for axis, bounds in refinement_box_m.items()},
        "refinement_box_membership": "inclusive cell-centroid membership; not a fractional overlap mask",
        "regions": region_reports,
    }


def analyze(
    case_dir: Path,
    export_dir: Path,
    requested_time_s: float,
    output_dir: Path,
    refinement_box_m: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    if not math.isfinite(requested_time_s) or requested_time_s < 0.0:
        raise ValueError("--time-s must be finite and nonnegative")
    output_dir = output_dir.resolve(strict=False)
    runs_dir = (ROOT / "results/runs").resolve(strict=True)
    if not output_dir.is_relative_to(runs_dir):
        raise ValueError(f"output directory must be under {runs_dir}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")

    manifest, case_inputs, export_attempt, export_attempt_path = _validate_run_and_export(
        case_dir, export_dir, requested_time_s
    )
    snapshot, export_hashes_before = load_export(export_dir)
    time_value = float(snapshot["time_value_s"])
    time_name = str(snapshot["time_name"])
    if not math.isclose(time_value, requested_time_s, rel_tol=0.0, abs_tol=TIME_TOLERANCE_S):
        raise ValueError(f"native export time is {time_value:g} s, expected {requested_time_s:g} s")
    native_rank_count = int(snapshot["topology"]["rank_count"])
    if native_rank_count != int(case_inputs["ranks"]):
        raise ValueError("native export and case-input rank counts disagree")
    if snapshot["source_patch"] != export_attempt["source_patch"]:
        raise ValueError("native export rank metadata and export attempt source patches disagree")
    n_native = len(snapshot["cell_global_ids"])
    if int(case_inputs.get("mesh_cells_expected", -1)) != n_native:
        raise ValueError("case declared cell count differs from assembled native export cell count")
    source_patch = str(snapshot["source_patch"])
    declared_area = float(case_inputs["source_patch_areas_m2"][source_patch])
    native_area = float(snapshot["topology"]["source_patch_area_m2"])
    declared_face_count = int(case_inputs["source_patch_face_counts"][source_patch])
    native_face_count = int(snapshot["topology"]["source_boundary_face_count"])
    if not math.isclose(native_area, declared_area, rel_tol=1e-8, abs_tol=1e-10):
        raise ValueError("native source-patch area differs from the case's declared area")
    if native_face_count != declared_face_count:
        raise ValueError("native source-face count differs from the case input")

    if refinement_box_m is None:
        refinement_box_m = _validate_box(case_inputs.get("refinement_region_m"))
    else:
        refinement_box_m = _validate_box(refinement_box_m)

    rank_dirs = sorted(export_dir.glob("rank-[0-9][0-9][0-9][0-9]"))
    rank_ids: list[NDArray[np.int64]] = []
    rank_field_values: dict[str, list[NDArray[np.float64]]] = {
        name: [] for name in FIELD_DIMENSIONS
    }
    field_hashes_before: dict[str, str] = {}
    rank_alignment: list[dict[str, Any]] = []
    for expected_rank, rank_dir in enumerate(rank_dirs):
        metadata = json.loads((rank_dir / "metadata.json").read_text(encoding="utf-8"))
        rank = expected_rank
        local_count = _validate_rank_metadata(
            metadata,
            expected_rank=expected_rank,
            expected_rank_count=native_rank_count,
            expected_time_name=time_name,
            expected_time_s=time_value,
            expected_source_patch=snapshot["source_patch"],
        )
        ids_path = rank_dir / "cell_global_ids.i64"
        local_ids = np.fromfile(ids_path, dtype=np.dtype("<i8"))
        if len(local_ids) != local_count:
            raise ValueError(f"exported global-ID count mismatch in {rank_dir}")
        rank_ids.append(local_ids)
        local_fields: dict[str, NDArray[np.float64]] = {}
        time_dir = case_dir / f"processor{rank}" / time_name
        for field_name, dimensions in FIELD_DIMENSIONS.items():
            path = time_dir / field_name
            if not path.is_file():
                raise FileNotFoundError(f"saved turbulence field is missing: {path}")
            digest = sha256_file(path)
            field_hashes_before[f"processor{rank}/{time_name}/{field_name}"] = digest
            values = read_foam_scalar_internal(
                path,
                expected_count=local_count,
                expected_object=field_name,
                expected_location=time_name,
                expected_dimensions=dimensions,
            )
            local_fields[field_name] = values
            rank_field_values[field_name].append(values)
        rank_alignment.append(
            {
                "rank": rank,
                "local_cell_count": local_count,
                "global_id_min": int(np.min(local_ids)) if len(local_ids) else None,
                "global_id_max": int(np.max(local_ids)) if len(local_ids) else None,
                "global_id_order_sha256": hashlib.sha256(
                    local_ids.astype("<i8", copy=False).tobytes()
                ).hexdigest(),
                "field_internal_list_counts": {
                    name: len(values) for name, values in local_fields.items()
                },
                "field_values_follow_native_local_cell_order": True,
            }
        )
    if len(rank_dirs) != native_rank_count:
        raise ValueError("native export does not contain exactly one payload directory per rank")

    aligned_fields = align_rank_fields(rank_ids, rank_field_values, snapshot["cell_global_ids"])

    stats = summarize_turbulence(snapshot, aligned_fields, refinement_box_m)
    raw_export_hashes_after = {
        str(path.relative_to(export_dir)): sha256_file(path)
        for path in sorted(export_dir.rglob("*"))
        if path.is_file()
    }
    if raw_export_hashes_after != export_hashes_before:
        raise ValueError("native export files changed during turbulence analysis")
    field_hashes_after = {key: sha256_file(case_dir / key) for key in sorted(field_hashes_before)}
    if field_hashes_after != field_hashes_before:
        raise ValueError("saved turbulence fields changed during analysis")
    export_attempt_input_hashes = export_attempt["input_sha256_after"]
    mesh_and_export_keys = {
        path: digest
        for path, digest in export_attempt_input_hashes.items()
        if "/constant/polyMesh/" in path
        or path.endswith(f"/{time_name}/alpha.water")
        or path.endswith(f"/{time_name}/U")
    }
    if len(mesh_and_export_keys) != len(export_attempt_input_hashes):
        raise ValueError("native export input hashes include unsupported non-mesh/non-flow files")
    expected_export_input_paths = {
        f"processor{rank}/constant/polyMesh/{name}"
        for rank in range(native_rank_count)
        for name in ("boundary", "cellProcAddressing", "faces", "neighbour", "owner", "points")
    }
    expected_export_input_paths.update(
        f"processor{rank}/{time_name}/{field}"
        for rank in range(native_rank_count)
        for field in ("alpha.water", "U")
    )
    if set(mesh_and_export_keys) != expected_export_input_paths:
        raise ValueError(
            "native export input hash inventory does not cover every rank's mesh and alpha/U fields"
        )
    checked_mesh_and_flow = _safe_hash_inventory(case_dir, mesh_and_export_keys)
    if checked_mesh_and_flow != mesh_and_export_keys:
        raise ValueError("mesh or exported flow fields differ from the sealed native export")

    log_path = case_dir / "log.interIsoFoam"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    printed_times = re.findall(r"(?m)^\s*Time\s*=\s*([+\-0-9.eE]+)\s*$", log_text)
    if not printed_times or float(printed_times[-1]) < requested_time_s - 1e-6:
        raise ValueError("solver log does not reach the requested saved time")
    if not re.search(r"(?m)^\s*End\s*$", log_text):
        raise ValueError("solver log does not prove successful terminal completion")

    input_paths = {
        "manifest.json": case_dir.parent / "manifest.json",
        "case-inputs.json": case_dir / "case-inputs.json",
        "constant/turbulenceProperties": case_dir / "constant/turbulenceProperties",
        "log.interIsoFoam": log_path,
        "export_attempt.json": export_attempt_path,
    }
    code_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    code_dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    report: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "status": "complete",
        "created_utc": dt.datetime.now(dt.UTC).isoformat(),
        "classification": "descriptive saved-field statistics; not an equation budget, causal attribution, or validation result",
        "case_id": manifest.get("run_id"),
        "case_directory": str(case_dir),
        "export_directory": str(export_dir),
        "requested_time_s": requested_time_s,
        "saved_time_name": time_name,
        "saved_time_value_s": time_value,
        "native_cell_count": n_native,
        "rank_count": native_rank_count,
        "source_patch": snapshot["source_patch"],
        "source_face_count": native_face_count,
        "source_area_m2_assumed": declared_area,
        "source_area_m2_native": native_area,
        "native_topology": snapshot["topology"],
        "turbulence_field_units_si": FIELD_UNITS_SI,
        "turbulence_field_dimensions": FIELD_DIMENSIONS,
        "turbulence_model": case_inputs.get("turbulence_model"),
        "turbulence_assumptions": case_inputs.get("turbulence_assumptions"),
        "source_geometry_assumption": case_inputs.get("source_geometry_assumption"),
        "input_provenance": {
            "git_revision_current": code_revision.stdout.strip()
            if code_revision.returncode == 0
            else None,
            "git_worktree_dirty_current": bool(code_dirty.stdout.strip())
            if code_dirty.returncode == 0
            else None,
            "case_git_revision": manifest.get("git_revision"),
            "case_git_dirty": manifest.get("git_dirty"),
            "solver_image": manifest.get("solver_image"),
            "solver_image_id": manifest.get("solver_image_id"),
            "native_export_image": export_attempt.get("image"),
            "native_export_image_id": export_attempt.get("image_id"),
            "native_export_source_patch": export_attempt.get("source_patch"),
            "native_global_id_source": "processorN/constant/polyMesh/cellProcAddressing, exported in native local cell order",
            "field_parser": "this script's strict OpenFOAM volScalarField internalField ASCII/binary reader",
            "analyzer_script_sha256": sha256_file(Path(__file__).resolve()),
            "input_sha256": {
                name: sha256_file(path) for name, path in input_paths.items() if path.is_file()
            },
            "native_export_files_sha256": export_hashes_before,
            "saved_turbulence_fields_sha256_by_rank": field_hashes_before,
            "saved_turbulence_fields_hashes_unchanged_after_analysis": True,
            "native_export_hashes_unchanged_after_analysis": True,
            "native_export_mesh_and_alpha_U_input_hashes_verified": True,
            "native_export_verified_input_file_count": len(mesh_and_export_keys),
            "native_export_verified_input_hash_inventory_sha256": hashlib.sha256(
                json.dumps(mesh_and_export_keys, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "rank_alignment": rank_alignment,
            "source_export_attempt": str(export_attempt_path),
        },
        "solver_log_last_printed_time_s": float(printed_times[-1]),
        "solver_log_has_End": True,
        "statistics": stats,
        "limitations": [
            "Water and air weights use alpha*V and (1-alpha)*V without density; means and quantiles are phase-volume weighted.",
            "Refinement-region membership uses exported cell centroids in the declared box; it is not partial-cell overlap.",
            "k, epsilon and nut are saved internal-cell values; patch boundary values and wall-function evaluations are not sampled.",
            "Turbulence quantities are summaries only; no production, dissipation, diffusion, transport or causal budget is calculated.",
            "Source geometry and turbulence boundary assumptions are copied from this exploratory case record; not reported calibrated inputs.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    _json_write(output_dir / "turbulence_fields.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--time-s", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--refinement-box-m",
        help='optional JSON object such as \'{"x":[-2.5,4],"y":[-1.5,1.5],"z":[-3,0]}\'; defaults to the case record',
    )
    args = parser.parse_args(argv)
    try:
        box = _validate_box(json.loads(args.refinement_box_m)) if args.refinement_box_m else None
        report = analyze(args.case_dir, args.export_dir, args.time_s, args.output_dir, box)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "time_s": report["saved_time_value_s"],
                    "cells": report["native_cell_count"],
                    "output": str(args.output_dir.resolve() / "turbulence_fields.json"),
                }
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"native turbulence analysis failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
