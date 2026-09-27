#!/usr/bin/env python3
"""Render actual, time-stamped OpenFOAM interface surfaces as a fixed-view animation.

Diagnostic mode is intended for short characterization runs. The validated mode
requires a passed-gate record and a conservative ground-map artifact for every
case. Neither mode creates, interpolates, or extrapolates simulated physics.

Validated sidecars use these JSON schemas:

* ``aerial-drop-protocol/v1``: ``run_id``, an accepted E4/E5/E6 ground-map
  gate, independent review evidence, and its frozen mass-ledger tolerance.
* ``aerial-drop-validation/v1``: ``run_id``, a ground-map ``gate_id``,
  ``gate_status`` (exactly ``"pass"``), ``evidence``, the protocol SHA-256,
  accepted tolerance, and hashes binding the pass to the exact manifest and map.
* ``aerial-drop-ground-map/v1``: ``run_id``, ``artifact`` (the NPZ filename),
  ``artifact_sha256``, ``mass_ledger`` with ``released_kg``,
  ``in_map_deposited_kg``, ``outside_map_deposited_kg``, ``airborne_vof_kg``,
  ``airborne_parcel_kg``, ``escaped_kg``, ``evaporated_kg``, ``residual_kg``,
  and ``tolerance_kg``, plus ``scoring`` with ``target_rectangle_xy_m``
  [xmin, xmax, ymin, ymax], ``l95_interval_x_m`` [xstart, xstop] or null when
  no qualifying strip exists, ``l95_m``,
  and ``coverage_threshold_kg_m2``.

The NPZ must contain ``weighted_deposition_x_edges_m``,
``weighted_deposition_y_edges_m``, ``weighted_deposition_kg_m2``,
``impact_locations_xy_m`` and ``impact_masses_kg``. The renderer independently
rebins those impacts and checks both the map and the mutually exclusive mass
ledger before it displays the ground map.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Sequence

import numpy as np

from aerial_drop.e0 import GroundMap, score_ground_map


class RenderValidationError(ValueError):
    """Raised when an animation input is incomplete or fails its recorded contract."""


@dataclass(frozen=True)
class CaseSpec:
    """One immutable simulation bundle and its optional full-mode artifacts."""

    label: str
    run_dir: Path
    ground_map: Path | None = None
    ground_map_record: Path | None = None
    validation_record: Path | None = None
    protocol_record: Path | None = None


@dataclass(frozen=True)
class FrameSpec:
    time_s: float
    time_directory: str
    path: Path
    sha256: str


@dataclass
class PreparedCase:
    spec: CaseSpec
    run_id: str
    manifest: dict[str, Any]
    report: dict[str, Any]
    manifest_sha256: str
    input_hashes: dict[str, str]
    frames: tuple[FrameSpec, ...]
    bounds: tuple[float, float, float, float, float, float]
    speed_min_m_s: float
    speed_max_m_s: float
    frame_statistics: list[dict[str, Any]]
    ground_map_data: dict[str, Any] | None = None
    ground_map_record: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    protocol: dict[str, Any] | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolved_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise RenderValidationError(f"{label} escapes its declared root: {path}") from error
    return resolved


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing any existing path."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RuntimeError("atomic no-replace directory publication needs Linux renameat2")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise RenderValidationError(
                f"refusing to overwrite output path created during render: {destination}"
            )
        raise OSError(error_number, os.strerror(error_number), str(destination))


def _new_output_path(output_dir: Path) -> Path:
    requested = output_dir.expanduser()
    if requested.name in ("", ".", ".."):
        raise RenderValidationError("output directory must name a new leaf directory")
    output = requested.parent.resolve() / requested.name
    if os.path.lexists(output):
        raise RenderValidationError(f"refusing to overwrite existing output directory {output}")
    return output


def _read_json_hashed(path: Path) -> tuple[dict[str, Any], str]:
    before = _sha256(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RenderValidationError(f"Cannot read JSON record {path}: {error}") from error
    if not isinstance(value, dict):
        raise RenderValidationError(f"JSON record must contain an object: {path}")
    after = _sha256(path)
    if before != after:
        raise RenderValidationError(f"JSON input changed while it was being read: {path}")
    return value, before


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_hashed(path)[0]


def _finite_number(value: Any, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RenderValidationError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        qualifier = "finite and nonnegative" if nonnegative else "finite"
        raise RenderValidationError(f"{field} must be {qualifier}")
    return result


def _time_value(time_text: Any, index: int) -> tuple[float, str]:
    if isinstance(time_text, bool) or not isinstance(time_text, (str, int, float)):
        raise RenderValidationError(f"surface time #{index} must be numeric or a numeric string")
    directory = str(time_text)
    if not re.fullmatch(r"\d+(?:\.\d+)?", directory):
        raise RenderValidationError(f"invalid OpenFOAM time directory name: {directory!r}")
    time_s = float(directory)
    if not math.isfinite(time_s) or time_s < 0.0:
        raise RenderValidationError(f"invalid simulation time {directory!r}")
    return time_s, directory


def _surface_contract(
    run_dir: Path, manifest: dict[str, Any]
) -> tuple[dict[str, Any], str, dict[str, str], dict[str, Any]]:
    """Find the declared frame contract in the current or future manifest format."""
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise RenderValidationError(f"{run_dir}/manifest.json has no run_id")

    contract = None
    source_hashes: dict[str, str] = {}
    source_report: dict[str, Any] = {}
    render_contract = manifest.get("render_contract")
    if isinstance(render_contract, dict):
        candidate = render_contract.get("surface_artifacts")
        if isinstance(candidate, dict):
            contract = candidate

    if contract is None:
        for filename in ("pilot-report.json", "ledger-report.json"):
            candidate_path = run_dir / filename
            if not candidate_path.is_file():
                continue
            resolved_report = _resolved_within(candidate_path, run_dir, "run report")
            candidate_report, candidate_hash = _read_json_hashed(resolved_report)
            source_hashes[str(resolved_report)] = candidate_hash
            source_report = candidate_report
            if candidate_report.get("run_id") not in (None, run_id):
                raise RenderValidationError(
                    f"{candidate_path} run_id does not match manifest run_id {run_id!r}"
                )
            candidate_contract = candidate_report.get("surface_artifacts")
            if isinstance(candidate_contract, dict):
                contract = candidate_contract
                break
            nested_manifest = candidate_report.get("manifest")
            nested_render = (
                nested_manifest.get("render_contract")
                if isinstance(nested_manifest, dict)
                else None
            )
            if isinstance(nested_render, dict) and isinstance(
                nested_render.get("surface_artifacts"), dict
            ):
                contract = nested_render["surface_artifacts"]
                break

    if not isinstance(contract, dict):
        raise RenderValidationError(
            f"{run_dir} has no declared timestamped surface_artifacts contract"
        )
    declared_format = contract.get("format", "")
    if not isinstance(declared_format, str) or ".vtp" not in declared_format.lower():
        raise RenderValidationError(f"{run_dir} surface contract does not declare VTP files")
    fields = contract.get("fields")
    if not isinstance(fields, list) or not {"U", "alpha.water"}.issubset(fields):
        raise RenderValidationError(
            f"{run_dir} surface contract must declare cell fields U and alpha.water"
        )
    times = contract.get("times_s")
    count = contract.get("count")
    if not isinstance(times, list) or not times:
        raise RenderValidationError(f"{run_dir} declares no simulation surface frames")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(times):
        raise RenderValidationError(f"{run_dir} declared frame count does not match times_s")

    time_values = [_time_value(item, index) for index, item in enumerate(times)]
    numbers = [item[0] for item in time_values]
    if len(set(numbers)) != len(numbers) or numbers != sorted(numbers):
        raise RenderValidationError(f"{run_dir} surface times must be unique and increasing")
    if len(numbers) < 2:
        raise RenderValidationError(f"{run_dir} needs at least two actual frames for an animation")
    return contract, run_id, source_hashes, source_report


def _load_pyvista() -> Any:
    try:
        import pyvista as pv
    except ImportError as error:
        raise RuntimeError(
            "Rendering dependencies are optional; run `uv sync --frozen --extra visualization`"
        ) from error
    return pv


def _read_surface(
    pv: Any, path: Path, expected_time_s: float
) -> tuple[Any, np.ndarray, np.ndarray]:
    try:
        mesh = pv.read(path)
    except Exception as error:  # VTK raises several exception types for corrupt XML.
        raise RenderValidationError(f"Cannot read simulation surface {path}: {error}") from error
    if not isinstance(mesh, pv.PolyData) or mesh.n_points == 0 or mesh.n_cells == 0:
        raise RenderValidationError(f"{path} is not a non-empty VTK PolyData surface")
    if "U" not in mesh.cell_data or "alpha.water" not in mesh.cell_data:
        raise RenderValidationError(f"{path} must contain cell arrays U and alpha.water")
    velocity = np.asarray(mesh.cell_data["U"], dtype=np.float64)
    alpha = np.asarray(mesh.cell_data["alpha.water"], dtype=np.float64)
    if velocity.shape != (mesh.n_cells, 3):
        raise RenderValidationError(
            f"{path} U shape is {velocity.shape}; expected ({mesh.n_cells}, 3)"
        )
    if alpha.shape not in ((mesh.n_cells,), (mesh.n_cells, 1)):
        raise RenderValidationError(
            f"{path} alpha.water shape is {alpha.shape}; expected one value per cell"
        )
    alpha = alpha.reshape(-1)
    if not np.isfinite(velocity).all() or not np.isfinite(alpha).all():
        raise RenderValidationError(f"{path} contains non-finite required scalar/vector values")
    if np.any(alpha < -1e-6) or np.any(alpha > 1.0 + 1e-6):
        raise RenderValidationError(
            f"{path} alpha.water is outside [0, 1] within roundoff tolerance"
        )
    if "TimeValue" not in mesh.field_data:
        raise RenderValidationError(f"{path} has no VTK TimeValue field")
    time_values = np.asarray(mesh.field_data["TimeValue"], dtype=np.float64).reshape(-1)
    if time_values.size != 1 or not np.isfinite(time_values[0]):
        raise RenderValidationError(f"{path} has an invalid VTK TimeValue field")
    if not math.isclose(float(time_values[0]), expected_time_s, rel_tol=0.0, abs_tol=1e-8):
        raise RenderValidationError(
            f"{path} TimeValue={float(time_values[0]):g} disagrees with declared "
            f"time {expected_time_s:g} s"
        )
    speed = np.linalg.norm(velocity, axis=1)
    return mesh, speed, alpha


def _edge_array(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 1 or array.size < 2 or not np.isfinite(array).all():
        raise RenderValidationError(f"ground-map {name} must be a finite edge vector")
    if np.any(np.diff(array) <= 0.0):
        raise RenderValidationError(f"ground-map {name} must be strictly increasing")
    return array


def _rebin_impacts(
    x_edges: np.ndarray,
    y_edges: np.ndarray,
    locations: np.ndarray,
    masses: np.ndarray,
) -> tuple[np.ndarray, float]:
    binned = np.zeros((x_edges.size - 1, y_edges.size - 1), dtype=np.float64)
    outside = 0.0
    for (x_value, y_value), mass in zip(locations, masses, strict=True):
        x = float(x_value)
        y = float(y_value)
        if x < x_edges[0] or x > x_edges[-1] or y < y_edges[0] or y > y_edges[-1]:
            outside += float(mass)
            continue
        i = (
            x_edges.size - 2
            if x == x_edges[-1]
            else int(np.searchsorted(x_edges, x, side="right") - 1)
        )
        j = (
            y_edges.size - 2
            if y == y_edges[-1]
            else int(np.searchsorted(y_edges, y, side="right") - 1)
        )
        binned[i, j] += float(mass)
    areas = np.diff(x_edges)[:, None] * np.diff(y_edges)[None, :]
    return binned / areas, outside


def _validate_ground_map(
    spec: CaseSpec, run_id: str
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    if spec.ground_map is None or spec.ground_map_record is None:
        raise RenderValidationError(
            f"validated case {spec.label!r} needs both --ground-map and its provenance record"
        )
    run_dir = spec.run_dir.resolve()
    path = _resolved_within(spec.ground_map, run_dir, "ground-map artifact")
    record_path = _resolved_within(spec.ground_map_record, run_dir, "ground-map record")
    if not path.is_file() or not record_path.is_file():
        raise RenderValidationError(f"missing ground-map artifact or record for {spec.label!r}")
    record, record_hash = _read_json_hashed(record_path)
    if record.get("schema") != "aerial-drop-ground-map/v1":
        raise RenderValidationError(f"unsupported ground-map record schema: {record_path}")
    if record.get("run_id") != run_id:
        raise RenderValidationError(f"ground-map record run_id does not match run {run_id!r}")
    if record.get("artifact") != path.name:
        raise RenderValidationError("ground-map record artifact name does not match the NPZ file")
    actual_hash = _sha256(path)
    if record.get("artifact_sha256") != actual_hash:
        raise RenderValidationError("ground-map artifact hash does not match its provenance record")

    required = {
        "weighted_deposition_x_edges_m",
        "weighted_deposition_y_edges_m",
        "weighted_deposition_kg_m2",
        "impact_locations_xy_m",
        "impact_masses_kg",
    }
    try:
        with np.load(path, allow_pickle=False) as archive:
            if not required.issubset(archive.files):
                missing = sorted(required.difference(archive.files))
                raise RenderValidationError(f"ground-map NPZ is missing fields: {missing}")
            data = {name: np.asarray(archive[name], dtype=np.float64).copy() for name in required}
    except (OSError, ValueError) as error:
        if isinstance(error, RenderValidationError):
            raise
        raise RenderValidationError(f"Cannot load ground-map NPZ {path}: {error}") from error
    if _sha256(path) != actual_hash:
        raise RenderValidationError("ground-map NPZ changed while it was being read")

    x_edges = _edge_array(data["weighted_deposition_x_edges_m"], "x_edges_m")
    y_edges = _edge_array(data["weighted_deposition_y_edges_m"], "y_edges_m")
    concentration = data["weighted_deposition_kg_m2"]
    expected_shape = (x_edges.size - 1, y_edges.size - 1)
    if concentration.shape != expected_shape or not np.isfinite(concentration).all():
        raise RenderValidationError(
            f"ground-map concentration shape must be {expected_shape} with finite values"
        )
    if np.any(concentration < 0.0):
        raise RenderValidationError("ground-map concentration must be nonnegative")
    locations = data["impact_locations_xy_m"]
    masses = data["impact_masses_kg"]
    if locations.ndim != 2 or locations.shape[1] != 2 or not np.isfinite(locations).all():
        raise RenderValidationError("ground-map impact_locations_xy_m must have shape (n, 2)")
    if masses.ndim != 1 or masses.size != locations.shape[0] or not np.isfinite(masses).all():
        raise RenderValidationError(
            "ground-map impact_masses_kg must be finite and match locations"
        )
    if np.any(masses < 0.0):
        raise RenderValidationError("ground-map impact masses must be nonnegative")
    rebinned, outside_mass = _rebin_impacts(x_edges, y_edges, locations, masses)
    ledger = record.get("mass_ledger")
    if not isinstance(ledger, dict):
        raise RenderValidationError("ground-map record has no mass_ledger object")
    tolerance = _finite_number(
        ledger.get("tolerance_kg"), "mass_ledger.tolerance_kg", nonnegative=True
    )
    if tolerance <= 0.0:
        raise RenderValidationError("mass_ledger.tolerance_kg must be positive")
    areas = np.diff(x_edges)[:, None] * np.diff(y_edges)[None, :]
    in_map_mass = float(np.sum(concentration * areas))
    if not np.allclose(rebinned, concentration, rtol=1e-10, atol=1e-12):
        raise RenderValidationError(
            "stored ground map does not match conservative rebinning of impacts"
        )
    expected_ledger = {
        "released_kg": _finite_number(
            ledger.get("released_kg"), "mass_ledger.released_kg", nonnegative=True
        ),
        "in_map_deposited_kg": _finite_number(
            ledger.get("in_map_deposited_kg"), "mass_ledger.in_map_deposited_kg", nonnegative=True
        ),
        "outside_map_deposited_kg": _finite_number(
            ledger.get("outside_map_deposited_kg"),
            "mass_ledger.outside_map_deposited_kg",
            nonnegative=True,
        ),
        "airborne_vof_kg": _finite_number(
            ledger.get("airborne_vof_kg"), "mass_ledger.airborne_vof_kg", nonnegative=True
        ),
        "airborne_parcel_kg": _finite_number(
            ledger.get("airborne_parcel_kg"), "mass_ledger.airborne_parcel_kg", nonnegative=True
        ),
        "escaped_kg": _finite_number(
            ledger.get("escaped_kg"), "mass_ledger.escaped_kg", nonnegative=True
        ),
        "evaporated_kg": _finite_number(
            ledger.get("evaporated_kg"), "mass_ledger.evaporated_kg", nonnegative=True
        ),
        "residual_kg": _finite_number(ledger.get("residual_kg"), "mass_ledger.residual_kg"),
    }
    if abs(in_map_mass - expected_ledger["in_map_deposited_kg"]) > tolerance:
        raise RenderValidationError("ground-map in-map deposited mass disagrees with its ledger")
    if abs(outside_mass - expected_ledger["outside_map_deposited_kg"]) > tolerance:
        raise RenderValidationError("ground-map outside-map mass disagrees with its ledger")
    accounted = (
        in_map_mass
        + outside_mass
        + expected_ledger["airborne_vof_kg"]
        + expected_ledger["airborne_parcel_kg"]
        + expected_ledger["escaped_kg"]
        + expected_ledger["evaporated_kg"]
    )
    computed_residual = expected_ledger["released_kg"] - accounted
    if (
        abs(computed_residual) > tolerance
        or abs(computed_residual - expected_ledger["residual_kg"]) > tolerance
    ):
        raise RenderValidationError("ground-map full-drop mass ledger does not close")

    scoring = record.get("scoring")
    if not isinstance(scoring, dict):
        raise RenderValidationError("ground-map record has no scoring object")
    target = np.asarray(scoring.get("target_rectangle_xy_m"), dtype=np.float64)
    interval_raw = scoring.get("l95_interval_x_m")
    interval = None if interval_raw is None else np.asarray(interval_raw, dtype=np.float64)
    l95 = _finite_number(scoring.get("l95_m"), "scoring.l95_m", nonnegative=True)
    _finite_number(
        scoring.get("coverage_threshold_kg_m2"),
        "scoring.coverage_threshold_kg_m2",
        nonnegative=True,
    )
    if (
        target.shape != (4,)
        or not np.isfinite(target).all()
        or not target[0] < target[1]
        or not target[2] < target[3]
    ):
        raise RenderValidationError("scoring target_rectangle_xy_m must be [xmin,xmax,ymin,ymax]")
    if interval is not None and (
        interval.shape != (2,) or not np.isfinite(interval).all() or not interval[0] < interval[1]
    ):
        raise RenderValidationError("scoring l95_interval_x_m must be [start, stop]")
    target_width = float(target[3] - target[2])
    if not (
        math.isclose(float(target[2]), -0.5 * target_width, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(float(target[3]), 0.5 * target_width, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise RenderValidationError("scoring target y bounds must be centered on y=0")
    if (
        target[0] < x_edges[0]
        or target[1] > x_edges[-1]
        or target[2] < y_edges[0]
        or target[3] > y_edges[-1]
    ):
        raise RenderValidationError("scoring target rectangle is outside the deposited ground map")
    try:
        computed_score = score_ground_map(
            GroundMap(x_edges, y_edges, concentration),
            expected_ledger["released_kg"],
            target_width,
            _finite_number(
                scoring.get("coverage_threshold_kg_m2"),
                "scoring.coverage_threshold_kg_m2",
                nonnegative=True,
            ),
            outside_map_mass_kg=outside_mass,
        )
    except ValueError as error:
        raise RenderValidationError(f"cannot recompute recorded ground score: {error}") from error
    actual_interval = (
        None
        if computed_score.strip_x_start_m is None
        else [computed_score.strip_x_start_m, computed_score.strip_x_stop_m]
    )
    if actual_interval is None:
        if interval is not None:
            raise RenderValidationError(
                "scoring L95 interval must be null when no qualifying strip exists"
            )
    else:
        if interval is None or not all(
            math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12)
            for actual, expected in zip(interval, actual_interval, strict=True)
        ):
            raise RenderValidationError(
                "scoring L95 interval disagrees with recomputed ground score"
            )
    if not math.isclose(computed_score.l95_m, l95, rel_tol=1e-12, abs_tol=1e-12):
        raise RenderValidationError("scoring L95 disagrees with recomputed ground score")
    data["weighted_deposition_x_edges_m"] = x_edges
    data["weighted_deposition_y_edges_m"] = y_edges
    data["weighted_deposition_kg_m2"] = concentration
    return data, record, record_hash, actual_hash


_GROUND_MAP_GATES = {"E4-ground-map", "E5-ground-map", "E6-ground-map"}


def _validate_protocol(spec: CaseSpec, run_id: str) -> tuple[dict[str, Any], str]:
    if spec.protocol_record is None or not spec.protocol_record.is_file():
        raise RenderValidationError(
            f"validated case {spec.label!r} needs a reviewed frozen protocol record"
        )
    protocol_path = spec.protocol_record.resolve()
    protocol, protocol_hash_before = _read_json_hashed(protocol_path)
    if protocol.get("schema") != "aerial-drop-protocol/v1":
        raise RenderValidationError(f"unsupported experiment protocol schema: {protocol_path}")
    if protocol.get("run_id") != run_id:
        raise RenderValidationError("protocol record run_id does not match its simulation bundle")
    if protocol.get("gate_id") not in _GROUND_MAP_GATES:
        raise RenderValidationError("protocol record must name an E4/E5/E6 ground-map gate")
    if protocol.get("review_status") != "accepted":
        raise RenderValidationError("experiment protocol has not been accepted")
    if (
        not isinstance(protocol.get("review_evidence"), str)
        or not protocol["review_evidence"].strip()
    ):
        raise RenderValidationError("protocol record must identify its independent review evidence")
    tolerance = _finite_number(
        protocol.get("mass_ledger_tolerance_kg"),
        "protocol.mass_ledger_tolerance_kg",
        nonnegative=True,
    )
    if tolerance <= 0.0:
        raise RenderValidationError("protocol mass-ledger tolerance must be positive")
    return protocol, protocol_hash_before


def _validate_gate(
    spec: CaseSpec,
    run_id: str,
    *,
    manifest_sha256: str,
    ground_map_record_sha256: str,
    ground_map_artifact_sha256: str,
    protocol_sha256: str,
    mass_ledger_tolerance_kg: float,
    protocol: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    if spec.validation_record is None or not spec.validation_record.is_file():
        raise RenderValidationError(
            f"validated case {spec.label!r} needs a passed-gate validation record"
        )
    record, record_hash = _read_json_hashed(spec.validation_record.resolve())
    if record.get("schema") != "aerial-drop-validation/v1":
        raise RenderValidationError(
            f"unsupported validation record schema: {spec.validation_record}"
        )
    if record.get("run_id") != run_id:
        raise RenderValidationError("validation record run_id does not match its simulation bundle")
    if record.get("gate_id") not in _GROUND_MAP_GATES or record.get("gate_id") != protocol.get(
        "gate_id"
    ):
        raise RenderValidationError("validation record must pass the accepted ground-map protocol")
    if record.get("gate_type") != "ground_map":
        raise RenderValidationError("validation record must pass a ground_map gate")
    if record.get("gate_status") != "pass":
        raise RenderValidationError(
            f"case {spec.label!r} validation gate status is not pass: {record.get('gate_status')!r}"
        )
    if not isinstance(record.get("gate_id"), str) or not record["gate_id"].strip():
        raise RenderValidationError("validation record must name the passed gate")
    if not isinstance(record.get("evidence"), str) or not record["evidence"].strip():
        raise RenderValidationError("validation record must identify its evidence")
    required_bindings = {
        "manifest_sha256": manifest_sha256,
        "ground_map_record_sha256": ground_map_record_sha256,
        "ground_map_artifact_sha256": ground_map_artifact_sha256,
        "protocol_record_sha256": protocol_sha256,
    }
    for field, expected in required_bindings.items():
        if record.get(field) != expected:
            raise RenderValidationError(f"validation record {field} does not match rendered inputs")
    accepted_tolerance = _finite_number(
        record.get("accepted_mass_ledger_tolerance_kg"),
        "validation.accepted_mass_ledger_tolerance_kg",
        nonnegative=True,
    )
    if not math.isclose(
        accepted_tolerance, mass_ledger_tolerance_kg, rel_tol=0.0, abs_tol=0.0
    ) or not math.isclose(
        accepted_tolerance,
        float(protocol["mass_ledger_tolerance_kg"]),
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise RenderValidationError("validation record does not bind the accepted mass tolerance")
    return record, record_hash


def _prepare_case(
    spec: CaseSpec, pv: Any, mode: Literal["diagnostic", "validated"]
) -> PreparedCase:
    run_dir = spec.run_dir.resolve()
    # Resolve caller-supplied paths once so a later symlink retarget cannot
    # change which sidecar is validated, hashed, or recorded in the manifest.
    spec = replace(
        spec,
        run_dir=run_dir,
        ground_map=spec.ground_map.resolve() if spec.ground_map is not None else None,
        ground_map_record=(
            spec.ground_map_record.resolve() if spec.ground_map_record is not None else None
        ),
        validation_record=(
            spec.validation_record.resolve() if spec.validation_record is not None else None
        ),
        protocol_record=(
            spec.protocol_record.resolve() if spec.protocol_record is not None else None
        ),
    )
    manifest_path = _resolved_within(run_dir / "manifest.json", run_dir, "run manifest")
    if not run_dir.is_dir() or not manifest_path.is_file():
        raise RenderValidationError(f"run directory or manifest is missing: {run_dir}")
    manifest, manifest_hash = _read_json_hashed(manifest_path)
    input_hashes = {str(manifest_path.resolve()): manifest_hash}
    contract, run_id, report_hashes, report = _surface_contract(run_dir, manifest)
    input_hashes.update(report_hashes)

    hashes = manifest.get("surface_artifact_hashes")
    if not isinstance(hashes, dict):
        raise RenderValidationError(f"{manifest_path} has no surface_artifact_hashes")
    frame_specs: list[FrameSpec] = []
    all_bounds: list[np.ndarray] = []
    all_speeds: list[np.ndarray] = []
    statistics: list[dict[str, Any]] = []
    for index, (time_s, time_dir) in enumerate(
        (_time_value(item, i) for i, item in enumerate(contract["times_s"]))
    ):
        relative = f"case/postProcessing/liquidInterface/{time_dir}/freeSurface.vtp"
        path = run_dir / relative
        if not path.is_file():
            raise RenderValidationError(f"declared simulation frame {index} is missing: {path}")
        resolved_path = _resolved_within(path, run_dir, "simulation frame")
        expected_hash = hashes.get(relative)
        if not isinstance(expected_hash, str) or _sha256(resolved_path) != expected_hash:
            raise RenderValidationError(
                f"simulation frame hash is missing or incorrect: {relative}"
            )
        mesh, speed, alpha = _read_surface(pv, resolved_path, time_s)
        if _sha256(resolved_path) != expected_hash:
            raise RenderValidationError(f"simulation frame changed while it was read: {relative}")
        input_hashes[str(resolved_path)] = expected_hash
        bounds = np.asarray(mesh.bounds, dtype=np.float64)
        if not np.isfinite(bounds).all():
            raise RenderValidationError(f"{path} has non-finite geometry bounds")
        frame_specs.append(FrameSpec(time_s, time_dir, resolved_path, expected_hash))
        all_bounds.append(bounds)
        all_speeds.append(speed)
        statistics.append(
            {
                "time_s": time_s,
                "cell_count": int(mesh.n_cells),
                "point_count": int(mesh.n_points),
                "alpha_water_range": [float(np.min(alpha)), float(np.max(alpha))],
                "surface_speed_m_s": [float(np.min(speed)), float(np.max(speed))],
                "geometry_bounds_m": [float(value) for value in bounds],
            }
        )
    bounds_stack = np.stack(all_bounds)
    union_bounds = np.array(
        [
            bounds_stack[:, 0].min(),
            bounds_stack[:, 1].max(),
            bounds_stack[:, 2].min(),
            bounds_stack[:, 3].max(),
            bounds_stack[:, 4].min(),
            bounds_stack[:, 5].max(),
        ],
        dtype=np.float64,
    )
    all_speed_values = np.concatenate(all_speeds)
    prepared = PreparedCase(
        spec=spec,
        run_id=run_id,
        manifest=manifest,
        report=report,
        manifest_sha256=manifest_hash,
        input_hashes=input_hashes,
        frames=tuple(frame_specs),
        bounds=tuple(float(value) for value in union_bounds),
        speed_min_m_s=float(np.min(all_speed_values)),
        speed_max_m_s=float(np.max(all_speed_values)),
        frame_statistics=statistics,
    )
    if mode == "validated":
        (
            prepared.ground_map_data,
            prepared.ground_map_record,
            ground_record_hash,
            ground_artifact_hash,
        ) = _validate_ground_map(spec, run_id)
        assert spec.ground_map_record is not None and spec.ground_map is not None
        input_hashes[str(spec.ground_map_record.resolve())] = ground_record_hash
        input_hashes[str(spec.ground_map.resolve())] = ground_artifact_hash
        prepared.protocol, protocol_hash = _validate_protocol(spec, run_id)
        assert spec.protocol_record is not None
        input_hashes[str(spec.protocol_record.resolve())] = protocol_hash
        prepared.validation, validation_hash = _validate_gate(
            spec,
            run_id,
            manifest_sha256=manifest_hash,
            ground_map_record_sha256=ground_record_hash,
            ground_map_artifact_sha256=ground_artifact_hash,
            protocol_sha256=protocol_hash,
            mass_ledger_tolerance_kg=float(
                prepared.ground_map_record["mass_ledger"]["tolerance_kg"]
            ),
            protocol=prepared.protocol,
        )
        assert spec.validation_record is not None
        input_hashes[str(spec.validation_record.resolve())] = validation_hash
    elif (
        spec.ground_map is not None
        or spec.ground_map_record is not None
        or spec.validation_record is not None
        or spec.protocol_record is not None
    ):
        raise RenderValidationError(
            "ground maps and validation records are accepted only in validated mode"
        )
    return prepared


def _union_bounds(cases: Sequence[PreparedCase]) -> np.ndarray:
    bounds = np.asarray([case.bounds for case in cases], dtype=np.float64)
    return np.array(
        [
            bounds[:, 0].min(),
            bounds[:, 1].max(),
            bounds[:, 2].min(),
            bounds[:, 3].max(),
            bounds[:, 4].min(),
            bounds[:, 5].max(),
        ],
        dtype=np.float64,
    )


def _validated_range(
    value: tuple[float, float] | None,
    actual_min: float,
    actual_max: float,
    name: str,
    *,
    required: bool,
) -> tuple[float, float]:
    if value is None:
        if required:
            raise RenderValidationError(f"validated mode requires a predeclared {name}")
        lower = 0.0 if name == "speed_scale_m_s" else actual_min
        upper = actual_max
    else:
        if len(value) != 2:
            raise RenderValidationError(f"{name} must contain [minimum, maximum]")
        lower, upper = map(float, value)
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
        raise RenderValidationError(f"{name} must be finite with minimum less than maximum")
    if lower > actual_min or upper < actual_max:
        raise RenderValidationError(f"{name} must include every observed value across all cases")
    return lower, upper


def _validate_bounds(
    requested: tuple[float, float, float, float, float, float] | None,
    actual: np.ndarray,
    *,
    required: bool,
) -> np.ndarray:
    if requested is None:
        if required:
            raise RenderValidationError("validated mode requires predeclared camera_bounds_m")
        bounds = actual.copy()
    else:
        bounds = np.asarray(requested, dtype=np.float64)
    if bounds.shape != (6,) or not np.isfinite(bounds).all():
        raise RenderValidationError("camera_bounds_m must be six finite values")
    if not (bounds[0] < bounds[1] and bounds[2] < bounds[3] and bounds[4] < bounds[5]):
        raise RenderValidationError("camera_bounds_m must have positive extent on all axes")
    if (
        bounds[0] > actual[0]
        or bounds[1] < actual[1]
        or bounds[2] > actual[2]
        or bounds[3] < actual[3]
        or bounds[4] > actual[4]
        or bounds[5] < actual[5]
    ):
        raise RenderValidationError("camera_bounds_m must include every surface in every case")
    return bounds


def _install_camera(
    plotter: Any, pv: Any, bounds: np.ndarray, width: int, height: int, *, cols: int, rows: int
) -> None:
    center = np.array(
        [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
    )
    direction = np.array([1.0, -1.7, 1.2], dtype=np.float64)
    direction /= np.linalg.norm(direction)
    world_up = np.array([0.0, 0.0, 1.0])
    forward = -direction
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    view_up = np.cross(right, forward)
    corners = np.array(
        [[bounds[ix], bounds[iy], bounds[iz]] for ix in (0, 1) for iy in (2, 3) for iz in (4, 5)],
        dtype=np.float64,
    )
    relative = corners - center
    half_width_projected = float(np.max(np.abs(relative @ right)))
    half_height_projected = float(np.max(np.abs(relative @ view_up)))
    aspect = (width / cols) / (height / rows)
    parallel_scale = 1.10 * max(half_height_projected, half_width_projected / aspect)
    distance = max(float(np.linalg.norm(np.ptp(corners, axis=0))) * 3.0, 1.0)
    plotter.camera_position = [center + direction * distance, center, view_up]
    plotter.camera.parallel_projection = True
    plotter.camera.parallel_scale = parallel_scale


def _render_backend_info(window: Any) -> dict[str, str | None]:
    """Record the active VTK window and concise EGL/OpenGL identity strings."""
    capabilities = window.ReportCapabilities()
    labels = {
        "egl_vendor": "EGL vendor string",
        "egl_version": "EGL version string",
        "opengl_vendor": "OpenGL vendor string",
        "opengl_renderer": "OpenGL renderer string",
        "opengl_version": "OpenGL version string",
    }
    info: dict[str, str | None] = {"window_class": window.GetClassName()}
    info.update({name: None for name in labels})
    if isinstance(capabilities, str):
        for line in capabilities.splitlines():
            for name, label in labels.items():
                prefix = f"{label}:"
                if line.lstrip().startswith(prefix):
                    info[name] = line.split(":", maxsplit=1)[1].strip() or None
    return info


def _map_grid(pv: Any, case: PreparedCase) -> Any:
    assert case.ground_map_data is not None
    data = case.ground_map_data
    grid = pv.RectilinearGrid(
        data["weighted_deposition_x_edges_m"],
        data["weighted_deposition_y_edges_m"],
        np.array([0.0, 0.001]),
    )
    grid.cell_data["deposited_kg_m2"] = data["weighted_deposition_kg_m2"].ravel(order="F")
    return grid


def _outline(pv: Any, rectangle: Sequence[float], z: float) -> Any:
    x0, x1, y0, y1 = (float(value) for value in rectangle)
    points = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])
    return pv.PolyData(points, lines=np.array([5, 0, 1, 2, 3, 0]))


def _render_png(
    pv: Any,
    cases: Sequence[PreparedCase],
    frame_index: int,
    output_png: Path,
    *,
    mode: Literal["diagnostic", "validated"],
    width: int,
    height: int,
    camera_bounds: np.ndarray,
    speed_range: tuple[float, float],
    map_range: tuple[float, float] | None,
    map_camera_bounds_xy: tuple[float, float, float, float] | None,
) -> dict[str, str | None]:
    columns = len(cases)
    rows = 2 if mode == "validated" else 1
    plotter = pv.Plotter(
        off_screen=True,
        shape=(rows, columns),
        window_size=(width, height),
    )
    plotter.ren_win.SetMultiSamples(0)
    plotter.set_background("#f7f9fc")
    time_s = cases[0].frames[frame_index].time_s
    for column, case in enumerate(cases):
        frame = case.frames[frame_index]
        if _sha256(frame.path) != frame.sha256:
            raise RenderValidationError(f"simulation frame changed after preflight: {frame.path}")
        mesh, speed, _ = _read_surface(pv, frame.path, frame.time_s)
        if _sha256(frame.path) != frame.sha256:
            raise RenderValidationError(
                f"simulation frame changed while it was rendered: {frame.path}"
            )
        mesh.cell_data["speed_m_s"] = speed
        plotter.subplot(0, column)
        plotter.add_mesh(
            mesh,
            scalars="speed_m_s",
            cmap="viridis",
            clim=speed_range,
            smooth_shading=False,
            ambient=0.25,
            diffuse=0.8,
            specular=0.2,
            show_scalar_bar=column == 0,
            scalar_bar_args={
                "title": "Surface speed (m/s)",
                "title_font_size": 17,
                "label_font_size": 14,
                "n_labels": 5,
                "fmt": "%.1f",
                "color": "#182338",
                "vertical": True,
                "position_x": 0.84,
                "position_y": 0.2,
                "height": 0.62,
                "width": 0.11,
            },
        )
        plotter.add_text(
            f"{case.spec.label}  ·  simulation t = {time_s:.6f} s\n"
            "Computed water-air VOF surface; color is speed derived from cell U",
            position="upper_left",
            font_size=12,
            color="#182338",
        )
        if mode == "diagnostic":
            plotter.add_text(
                "SHORT P0 CHARACTERIZATION ONLY · provisional inputs · no validated descent, ground map, or design claim",
                position="lower_left",
                font_size=12,
                color="#8b1e1e",
            )
        else:
            validation = case.validation or {}
            plotter.add_text(
                f"Passed gate: {validation.get('gate_id')} · computed fields only",
                position="lower_left",
                font_size=10,
                color="#182338",
            )
        _install_camera(plotter, pv, camera_bounds, width, height, cols=columns, rows=rows)
        plotter.add_axes(xlabel="x", ylabel="y", zlabel="z", line_width=2)

        if mode == "validated":
            assert case.ground_map_data is not None and case.ground_map_record is not None
            plotter.subplot(1, column)
            grid = _map_grid(pv, case)
            plotter.add_mesh(
                grid,
                scalars="deposited_kg_m2",
                cmap="magma",
                clim=map_range,
                show_scalar_bar=column == 0,
                scalar_bar_args={
                    "title": "Deposited water-equivalent mass (kg/m²)",
                    "title_font_size": 15,
                    "label_font_size": 13,
                    "n_labels": 5,
                    "fmt": "%.2g",
                    "color": "#182338",
                },
            )
            scoring = case.ground_map_record["scoring"]
            target = scoring["target_rectangle_xy_m"]
            z = 0.004
            plotter.add_mesh(_outline(pv, target, z), color="#ffffff", line_width=3)
            interval = scoring["l95_interval_x_m"]
            if interval is not None:
                plotter.add_mesh(
                    _outline(pv, [interval[0], interval[1], target[2], target[3]], z + 0.001),
                    color="#31d4ff",
                    line_width=4,
                )
            interval_label = (
                "cyan: recomputed continuous L95 interval"
                if interval is not None
                else "no qualifying continuous strip"
            )
            plotter.add_text(
                f"Conservative accumulated ground map · L95 = {float(scoring['l95_m']):.3g} m\n"
                f"White: prescribed target · {interval_label}",
                position="upper_left",
                font_size=11,
                color="#182338",
            )
            assert map_camera_bounds_xy is not None
            map_bounds = np.asarray(map_camera_bounds_xy, dtype=np.float64)
            center = np.array(
                [(map_bounds[0] + map_bounds[1]) / 2, (map_bounds[2] + map_bounds[3]) / 2, 0.0]
            )
            plotter.camera_position = [center + np.array([0.0, 0.0, 10.0]), center, [0.0, 1.0, 0.0]]
            plotter.camera.parallel_projection = True
            map_aspect = (width / columns) / (height / rows)
            plotter.camera.parallel_scale = 1.08 * max(
                (map_bounds[3] - map_bounds[2]) / 2,
                (map_bounds[1] - map_bounds[0]) / (2 * map_aspect),
            )
    plotter.link_views() if columns > 1 and mode == "diagnostic" else None
    try:
        plotter.show(screenshot=str(output_png), auto_close=False)
        return _render_backend_info(plotter.ren_win)
    finally:
        plotter.close()


def render_animation(
    cases: Sequence[CaseSpec],
    output_dir: Path,
    *,
    mode: Literal["diagnostic", "validated"] = "diagnostic",
    fps: int = 6,
    window_size: tuple[int, int] = (1600, 900),
    camera_bounds_m: tuple[float, float, float, float, float, float] | None = None,
    speed_scale_m_s: tuple[float, float] | None = None,
    map_scale_kg_m2: tuple[float, float] | None = None,
    map_camera_bounds_xy_m: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Preflight all inputs, then render only their stored VTP times.

    In ``validated`` mode the caller must freeze camera and scalar ranges and
    supply matching ground-map and gate sidecars. Output is committed to a new
    directory and is refused if that directory already exists or is inside a
    source simulation bundle.
    """
    if mode not in ("diagnostic", "validated"):
        raise RenderValidationError(f"unsupported animation mode {mode!r}")
    if not cases or not all(isinstance(case, CaseSpec) for case in cases):
        raise RenderValidationError("provide at least one CaseSpec")
    labels = [case.label.strip() for case in cases]
    if any(not label for label in labels) or len(set(labels)) != len(labels):
        raise RenderValidationError("case labels must be non-empty and unique")
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 60:
        raise RenderValidationError("fps must be an integer from 1 through 60")
    width, height = window_size
    if width < 320 or height < 240 or width % 2 or height % 2:
        raise RenderValidationError("window size must be even and at least 320 × 240")
    pv = _load_pyvista()
    prepared = [_prepare_case(case, pv, mode) for case in cases]
    timelines = [[frame.time_s for frame in case.frames] for case in prepared]
    if any(timeline != timelines[0] for timeline in timelines[1:]):
        raise RenderValidationError(
            "all comparison cases must contain the same actual timestamps; frames are never interpolated"
        )

    if mode == "validated" and len(prepared) > 1:
        scoring_settings = []
        for case in prepared:
            assert case.ground_map_record is not None
            scoring = case.ground_map_record["scoring"]
            target = tuple(float(value) for value in scoring["target_rectangle_xy_m"])
            threshold = float(scoring["coverage_threshold_kg_m2"])
            scoring_settings.append((target, threshold))
        if any(settings != scoring_settings[0] for settings in scoring_settings[1:]):
            raise RenderValidationError(
                "validated comparison cases must use identical target rectangles and "
                "coverage thresholds"
            )

    actual_bounds = _union_bounds(prepared)
    camera_bounds = _validate_bounds(
        camera_bounds_m,
        actual_bounds,
        required=mode == "validated",
    )
    speed_min = min(case.speed_min_m_s for case in prepared)
    speed_max = max(case.speed_max_m_s for case in prepared)
    speed_range = _validated_range(
        speed_scale_m_s,
        speed_min,
        speed_max,
        "speed_scale_m_s",
        required=mode == "validated",
    )
    map_range: tuple[float, float] | None = None
    map_camera_bounds: tuple[float, float, float, float] | None = None
    if mode == "validated":
        maps = [
            case.ground_map_data["weighted_deposition_kg_m2"]
            for case in prepared
            if case.ground_map_data is not None
        ]
        map_min = min(float(np.min(values)) for values in maps)
        map_max = max(float(np.max(values)) for values in maps)
        map_range = _validated_range(
            map_scale_kg_m2,
            map_min,
            map_max,
            "map_scale_kg_m2",
            required=True,
        )
        map_edges_x = [
            case.ground_map_data["weighted_deposition_x_edges_m"]
            for case in prepared
            if case.ground_map_data is not None
        ]
        map_edges_y = [
            case.ground_map_data["weighted_deposition_y_edges_m"]
            for case in prepared
            if case.ground_map_data is not None
        ]
        actual_map_bounds = (
            min(float(np.min(edges)) for edges in map_edges_x),
            max(float(np.max(edges)) for edges in map_edges_x),
            min(float(np.min(edges)) for edges in map_edges_y),
            max(float(np.max(edges)) for edges in map_edges_y),
        )
        if map_camera_bounds_xy_m is None:
            raise RenderValidationError(
                "validated mode requires predeclared map_camera_bounds_xy_m"
            )
        map_camera_bounds = tuple(float(value) for value in map_camera_bounds_xy_m)
        if len(map_camera_bounds) != 4 or not all(
            math.isfinite(value) for value in map_camera_bounds
        ):
            raise RenderValidationError("map_camera_bounds_xy_m must contain four finite values")
        if not (
            map_camera_bounds[0] < map_camera_bounds[1]
            and map_camera_bounds[2] < map_camera_bounds[3]
        ):
            raise RenderValidationError("map_camera_bounds_xy_m must have positive x and y extents")
        if (
            map_camera_bounds[0] > actual_map_bounds[0]
            or map_camera_bounds[1] < actual_map_bounds[1]
            or map_camera_bounds[2] > actual_map_bounds[2]
            or map_camera_bounds[3] < actual_map_bounds[3]
        ):
            raise RenderValidationError("map_camera_bounds_xy_m must include every ground map")
    elif map_scale_kg_m2 is not None:
        raise RenderValidationError("map_scale_kg_m2 is only used in validated mode")
    elif map_camera_bounds_xy_m is not None:
        raise RenderValidationError("map_camera_bounds_xy_m is only used in validated mode")

    output = _new_output_path(output_dir)
    for case in prepared:
        run_dir = case.spec.run_dir.resolve()
        if output == run_dir or run_dir in output.parents:
            raise RenderValidationError(
                "animation output directory cannot be inside a source run bundle"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to encode the rendered animation")
    renderer_hash = _sha256(Path(__file__).resolve())
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        temporary_frames = temporary / "frames"
        temporary_frames.mkdir()
        render_backend: dict[str, str | None] | None = None
        for index, _time_s in enumerate(timelines[0]):
            frame_backend = _render_png(
                pv,
                prepared,
                index,
                temporary_frames / f"frame-{index:06d}.png",
                mode=mode,
                width=width,
                height=height,
                camera_bounds=camera_bounds,
                speed_range=speed_range,
                map_range=map_range,
                map_camera_bounds_xy=map_camera_bounds,
            )
            if render_backend is None:
                render_backend = frame_backend
            elif frame_backend != render_backend:
                raise RenderValidationError("render backend changed between animation frames")
        output_mp4 = temporary / "animation.mp4"
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(temporary_frames / "frame-%06d.png"),
                "-frames:v",
                str(len(timelines[0])),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "-1",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                "-y",
                str(output_mp4),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to encode animation: {completed.stderr.strip()}")
        shutil.rmtree(temporary_frames)
        ffmpeg_version = subprocess.run(
            [ffmpeg, "-version"], capture_output=True, text=True, check=False
        ).stdout.splitlines()[0]
        output_hash = _sha256(output_mp4)
        frame_records = [
            {
                "time_s": case.frames[index].time_s,
                "input_vtp": str(case.frames[index].path),
                "input_sha256": case.frames[index].sha256,
                "cell_count": case.frame_statistics[index]["cell_count"],
                "point_count": case.frame_statistics[index]["point_count"],
                "alpha_water_range": case.frame_statistics[index]["alpha_water_range"],
                "surface_speed_m_s": case.frame_statistics[index]["surface_speed_m_s"],
            }
            for index in range(len(timelines[0]))
            for case in prepared
        ]
        manifest: dict[str, Any] = {
            "schema": "aerial-drop-animation/v1",
            "mode": mode,
            "created_utc": datetime.now(UTC).isoformat(),
            "animation": {
                "file": "animation.mp4",
                "sha256": output_hash,
                "frame_count": len(timelines[0]),
                "frames_per_second": fps,
                "playback_duration_s": len(timelines[0]) / fps,
                "simulation_times_s": timelines[0],
                "simulation_time_span_s": timelines[0][-1] - timelines[0][0],
                "output_window_px": [width, height],
            },
            "render_settings": {
                "camera_bounds_m": [float(value) for value in camera_bounds],
                "camera_direction": [1.0, -1.7, 1.2],
                "multisampling_samples": 0,
                "surface_scalar": "speed magnitude derived from stored cell-centered U vectors",
                "surface_scalar_range_m_s": list(speed_range),
                "map_camera_bounds_xy_m": (
                    list(map_camera_bounds) if map_camera_bounds is not None else None
                ),
                "ground_map_scalar": (
                    "weighted deposited mass per area from conservative ground-map NPZ"
                    if mode == "validated"
                    else None
                ),
                "ground_map_scalar_range_kg_m2": list(map_range) if map_range else None,
                "playback_note": "Every encoded frame is one stored simulation time; no physics is interpolated.",
                "coordinate_frame": "x along-track, y cross-track, z upward; coordinates in metres",
            },
            "software": {
                "pyvista": pv.__version__,
                "vtk": str(pv.vtk_version_info),
                "ffmpeg": ffmpeg_version,
                "render_backend": render_backend,
            },
            "cases": [],
            "rendered_frames": frame_records,
            "claim_limit": (
                "Short provisional P0 characterization only; no validated descent, ground map, breakup, field validation, or design claim."
                if mode == "diagnostic"
                else "The named gate passed for each recorded bundle; animation remains a visualization of stored fields and does not establish claims beyond those gates."
            ),
            "provenance": {
                "renderer_script_sha256": renderer_hash,
                "renderer_writes_inside_source_run": False,
            },
        }
        for case in prepared:
            item: dict[str, Any] = {
                "label": case.spec.label,
                "run_id": case.run_id,
                "run_dir": str(case.spec.run_dir.resolve()),
                "git_revision": case.manifest.get("git_revision"),
                "git_worktree_dirty": case.manifest.get("git_worktree_dirty"),
                "manifest_sha256": case.manifest_sha256,
                "input_sha256": dict(sorted(case.input_hashes.items())),
                "surface_artifact_hashes": {
                    str(frame.path.relative_to(case.spec.run_dir.resolve())): frame.sha256
                    for frame in case.frames
                },
            }
            if case.validation is not None:
                item["validation_record"] = {
                    "path": str(case.spec.validation_record.resolve()),
                    "sha256": case.input_hashes[str(case.spec.validation_record.resolve())],
                    "gate_id": case.validation["gate_id"],
                    "gate_status": case.validation["gate_status"],
                    "evidence": case.validation["evidence"],
                }
                assert case.spec.protocol_record is not None and case.protocol is not None
                item["protocol_record"] = {
                    "path": str(case.spec.protocol_record.resolve()),
                    "sha256": case.input_hashes[str(case.spec.protocol_record.resolve())],
                    "gate_id": case.protocol["gate_id"],
                    "review_status": case.protocol["review_status"],
                    "review_evidence": case.protocol["review_evidence"],
                    "mass_ledger_tolerance_kg": case.protocol["mass_ledger_tolerance_kg"],
                }
                assert case.spec.ground_map is not None and case.spec.ground_map_record is not None
                item["ground_map"] = {
                    "path": str(case.spec.ground_map.resolve()),
                    "sha256": case.input_hashes[str(case.spec.ground_map.resolve())],
                    "record_path": str(case.spec.ground_map_record.resolve()),
                    "record_sha256": case.input_hashes[str(case.spec.ground_map_record.resolve())],
                    "mass_ledger": case.ground_map_record["mass_ledger"],
                    "scoring": case.ground_map_record["scoring"],
                }
            manifest["cases"].append(item)
        (temporary / "render-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for case in prepared:
            for path_text, expected_hash in case.input_hashes.items():
                if _sha256(Path(path_text)) != expected_hash:
                    raise RenderValidationError(
                        f"simulation input changed during rendering: {path_text}"
                    )
        if _sha256(Path(__file__).resolve()) != renderer_hash:
            raise RenderValidationError(
                "renderer source changed while the animation was being built"
            )
        _rename_noreplace(temporary, output)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _parse_named_path(value: str, flag: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"{flag} values must be LABEL=PATH")
    label, path = value.split("=", 1)
    if not label.strip() or not path.strip():
        raise argparse.ArgumentTypeError(f"{flag} values must be LABEL=PATH")
    return label.strip(), Path(path).expanduser()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("diagnostic", "validated"), default="diagnostic")
    parser.add_argument("--case", action="append", required=True, metavar="LABEL=RUN_DIR")
    parser.add_argument("--ground-map", action="append", default=[], metavar="LABEL=NPZ")
    parser.add_argument("--ground-map-record", action="append", default=[], metavar="LABEL=JSON")
    parser.add_argument("--protocol-record", action="append", default=[], metavar="LABEL=JSON")
    parser.add_argument("--validation-record", action="append", default=[], metavar="LABEL=JSON")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument(
        "--size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), default=(1600, 900)
    )
    parser.add_argument(
        "--camera-bounds",
        nargs=6,
        type=float,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"),
    )
    parser.add_argument("--speed-scale", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--map-scale", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument(
        "--map-camera-bounds",
        nargs=4,
        type=float,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
    )
    args = parser.parse_args(argv)
    try:
        case_paths = [_parse_named_path(value, "--case") for value in args.case]
        maps = dict(_parse_named_path(value, "--ground-map") for value in args.ground_map)
        map_records = dict(
            _parse_named_path(value, "--ground-map-record") for value in args.ground_map_record
        )
        protocols = dict(
            _parse_named_path(value, "--protocol-record") for value in args.protocol_record
        )
        validations = dict(
            _parse_named_path(value, "--validation-record") for value in args.validation_record
        )
        labels = [label for label, _path in case_paths]
        if any(
            key not in labels
            for mapping in (maps, map_records, protocols, validations)
            for key in mapping
        ):
            raise RenderValidationError("every artifact label must match a declared --case label")
        cases = [
            CaseSpec(
                label=label,
                run_dir=run_dir,
                ground_map=maps.get(label),
                ground_map_record=map_records.get(label),
                validation_record=validations.get(label),
                protocol_record=protocols.get(label),
            )
            for label, run_dir in case_paths
        ]
        manifest = render_animation(
            cases,
            args.output_dir,
            mode=args.mode,
            fps=args.fps,
            window_size=tuple(args.size),
            camera_bounds_m=tuple(args.camera_bounds) if args.camera_bounds else None,
            speed_scale_m_s=tuple(args.speed_scale) if args.speed_scale else None,
            map_scale_kg_m2=tuple(args.map_scale) if args.map_scale else None,
            map_camera_bounds_xy_m=(
                tuple(args.map_camera_bounds) if args.map_camera_bounds else None
            ),
        )
    except (OSError, RuntimeError, RenderValidationError, ValueError) as error:
        parser.error(str(error))
    output = args.output_dir.expanduser().resolve()
    print(
        f"Rendered {manifest['animation']['frame_count']} stored simulation frames to {output / 'animation.mp4'}"
    )
    print(f"Render manifest {output / 'render-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
