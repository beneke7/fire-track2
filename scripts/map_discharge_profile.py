#!/usr/bin/env python3
"""Conservatively map one rectangular tank-outlet profile snapshot to Dash-8 faces.

The source profile uses VTK coordinates (x=transverse, y=streamwise, z=up).
The target Dash-8 patch uses (x=streamwise, y=transverse, z=up).  Geometry
and velocity vectors therefore use the explicit x/y permutation
``(x_t, y_t, z_t) = (y_s, x_s, z_s)`` plus an origin-to-origin translation.

The public function accepts axis-aligned planar rectangle bounds as
``[xmin, ymin, zmin, xmax, ymax, zmax]``.  The optional CLI reads one snapshot
from a JSON manifest and numeric arrays from an NPZ file; it never interpolates
or holds a profile across time.  CLI inputs provide independent face areas for
both grids, checked against the rectangular bounds to catch nonrectangular faces.
Input schema v2 can additionally carry native, face-integrated ``alphaPhi_``
rates, face IDs, and oriented normals.  Those rates stay separate from the
interpolated alpha/U proxy, and any remapped target rates are predictions rather
than target-solver measurements.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

SCHEMA = "dash8-discharge-profile-mapping-v1"
INPUT_SCHEMA = "dash8-discharge-profile-mapping-input-v1"
SCHEMA_NATIVE_FLUX = "dash8-discharge-profile-mapping-v2"
INPUT_SCHEMA_NATIVE_FLUX = "dash8-discharge-profile-mapping-input-v2"
SOURCE_TO_TARGET_MATRIX = np.asarray(
    [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    dtype=np.float64,
)
NPZ_REQUIRED_KEYS = {
    "source_face_bounds_xyz_m",
    "source_face_area_m2",
    "source_face_velocity_xyz_m_s",
    "source_face_alpha",
    "target_face_bounds_xyz_m",
    "target_face_area_m2",
}
NPZ_NATIVE_FLUX_REQUIRED_KEYS = {
    "source_face_alphaPhi_m3_s",
    "source_face_native_id",
    "source_face_normal_unit_xyz",
    "target_face_native_id",
    "target_face_normal_unit_xyz",
}
NPZ_NATIVE_TARGET_MEASUREMENT_KEY = "target_face_native_alphaPhi_m3_s"
NATIVE_RATE_CONVENTION = "completed_main_step_dVf_over_deltaT"
NATIVE_SIGN_CONVENTION = "signed_along_supplied_native_oriented_face_normal"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_array(value: Any, shape_tail: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 1 + len(shape_tail) or array.shape[1:] != shape_tail:
        expected = "N" + "".join(f"x{part}" for part in shape_tail)
        raise ValueError(f"{name} must have shape {expected}, got {array.shape}")
    if array.shape[0] == 0:
        raise ValueError(f"{name} must contain at least one face")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains non-finite values")
    return array


def _finite_vector(value: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite 3-vector")
    return array


def _native_ids(value: Any, count: int, name: str) -> np.ndarray:
    raw = np.asarray(value)
    valid_shape = raw.shape == (count,) or raw.shape == (count, 2)
    if not valid_shape or raw.dtype.kind not in "iu":
        raise ValueError(f"{name} must be integer face IDs or (rank, local-ID) pairs")
    if raw.dtype.kind == "u" and np.any(raw > np.iinfo(np.int64).max):
        raise ValueError(f"{name} contains an ID outside int64 range")
    ids = raw.astype(np.int64, copy=False)
    unique_count = np.unique(ids, axis=0).shape[0] if ids.ndim == 2 else np.unique(ids).size
    if unique_count != count:
        raise ValueError(f"{name} values must be unique within this surface")
    return ids


def _unit_face_normals(value: Any, count: int, name: str) -> np.ndarray:
    normals = _finite_array(value, (3,), name)
    if normals.shape[0] != count:
        raise ValueError(f"{name} count does not match its face count")
    lengths = np.linalg.norm(normals, axis=1)
    if not np.allclose(lengths, 1.0, rtol=0.0, atol=1e-8):
        raise ValueError(f"{name} rows must be unit vectors")
    return normals


def _native_flux_mapping(
    source_alpha_phi_m3_s: Any,
    source_face_ids: Any,
    source_normals_source_xyz: Any,
    target_face_ids: Any,
    target_normals_target_xyz: Any,
    source_areas: np.ndarray,
    target_areas: np.ndarray,
    overlap_target_ids: np.ndarray,
    overlap_source_ids: np.ndarray,
    overlap_areas: np.ndarray,
    *,
    flow_direction_target_xyz: np.ndarray,
    profile_time_s: float,
    source_delta_t_s: float,
    target_alpha_phi_m3_s: Any | None,
    target_time_s: float | None,
    target_delta_t_s: float | None,
) -> dict[str, Any]:
    """Remap native integrated alphaPhi rates by face-area overlap.

    Rates are signed along each supplied native oriented face normal.  The
    returned target rates are predictions expressed along target native
    normals; they are not measurements from a target solver run.
    """
    source_rates = np.asarray(source_alpha_phi_m3_s, dtype=np.float64)
    if source_rates.shape != source_areas.shape or not np.isfinite(source_rates).all():
        raise ValueError("source_face_alphaPhi_m3_s must be finite and match source faces")
    source_ids = _native_ids(source_face_ids, source_areas.size, "source_face_native_id")
    target_ids = _native_ids(target_face_ids, target_areas.size, "target_face_native_id")
    source_normals = _unit_face_normals(
        source_normals_source_xyz, source_areas.size, "source_face_normal_unit_xyz"
    )
    target_normals = _unit_face_normals(
        target_normals_target_xyz, target_areas.size, "target_face_normal_unit_xyz"
    )
    source_normals_target_xyz = source_normals @ SOURCE_TO_TARGET_MATRIX.T
    source_alignment = source_normals_target_xyz @ flow_direction_target_xyz
    target_alignment = target_normals @ flow_direction_target_xyz
    if not np.allclose(np.abs(source_alignment), 1.0, rtol=0.0, atol=1e-8):
        raise ValueError(
            "source native face normals must be parallel to the declared flow direction"
        )
    if not np.allclose(np.abs(target_alignment), 1.0, rtol=0.0, atol=1e-8):
        raise ValueError(
            "target native face normals must be parallel to the declared flow direction"
        )
    if not math.isfinite(source_delta_t_s) or source_delta_t_s <= 0.0:
        raise ValueError("native source delta_t_s must be finite and positive")

    # Convert the source's signed oriented-face values to a common physical
    # flow direction, area-average their rates, then express the prediction
    # using each target face's own native normal orientation.
    source_flow_rates = source_rates * source_alignment
    source_flow_rate_density = source_flow_rates / source_areas
    target_flow_rate_density = _overlap_average(
        source_flow_rate_density,
        overlap_target_ids,
        overlap_source_ids,
        overlap_areas,
        target_areas,
    )
    target_flow_rates = target_flow_rate_density * target_areas
    target_predicted_rates = target_flow_rates * target_alignment
    source_flow_rate = float(source_flow_rates.sum())
    mapped_flow_rate = float(target_flow_rates.sum())
    if not math.isclose(source_flow_rate, mapped_flow_rate, rel_tol=1e-10, abs_tol=1e-12):
        raise RuntimeError("native alphaPhi overlap mapping failed to conserve oriented flow rate")

    mapped: dict[str, Any] = {
        "source_face_native_id": source_ids,
        "source_face_normal_unit_target_xyz": source_normals_target_xyz,
        "source_face_alphaPhi_m3_s": source_rates,
        "target_face_native_id": target_ids,
        "target_face_normal_unit_xyz": target_normals,
        "target_face_mapped_alphaPhi_m3_s": target_predicted_rates,
        "summary": {
            "field_name": "alphaPhi_",
            "source_time_s": float(profile_time_s),
            "source_delta_t_s": float(source_delta_t_s),
            "source_rate_convention": NATIVE_RATE_CONVENTION,
            "source_sign_convention": NATIVE_SIGN_CONVENTION,
            "target_mapping_status": "conservative_geometry_remap_prediction_not_solver_measurement",
            "source_face_count": int(source_areas.size),
            "target_face_count": int(target_areas.size),
            "source_native_id_shape": list(source_ids.shape),
            "target_native_id_shape": list(target_ids.shape),
            "native_id_contract": "opaque unique integer face IDs or unique (processor rank, local face ID) pairs",
            "source_oriented_rate_sum_m3_s": float(source_rates.sum()),
            "source_rate_along_declared_flow_m3_s": source_flow_rate,
            "mapped_target_rate_along_declared_flow_m3_s": mapped_flow_rate,
            "mapped_target_native_oriented_rate_sum_m3_s": float(target_predicted_rates.sum()),
            "source_completed_step_volume_along_flow_m3": source_flow_rate * source_delta_t_s,
            "mapped_target_completed_step_volume_using_source_delta_t_m3": (
                mapped_flow_rate * source_delta_t_s
            ),
            "rate_closure_target_minus_source_m3_s": mapped_flow_rate - source_flow_rate,
            "completed_step_volume_closure_m3": (mapped_flow_rate - source_flow_rate)
            * source_delta_t_s,
            "normal_alignment_source_to_flow": {
                "minimum_absolute_dot": float(np.min(np.abs(source_alignment))),
                "maximum_absolute_dot": float(np.max(np.abs(source_alignment))),
            },
            "normal_alignment_target_to_flow": {
                "minimum_absolute_dot": float(np.min(np.abs(target_alignment))),
                "maximum_absolute_dot": float(np.max(np.abs(target_alignment))),
            },
        },
    }
    if target_alpha_phi_m3_s is not None:
        if target_time_s is None or target_delta_t_s is None:
            raise ValueError("target native alphaPhi requires its saved time and delta_t_s")
        target_rates = np.asarray(target_alpha_phi_m3_s, dtype=np.float64)
        if target_rates.shape != target_areas.shape or not np.isfinite(target_rates).all():
            raise ValueError(
                "target_face_native_alphaPhi_m3_s must be finite and match target faces"
            )
        if not math.isfinite(target_time_s) or not math.isclose(
            target_time_s, profile_time_s, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("target native alphaPhi time must match source profile time")
        if not math.isfinite(target_delta_t_s) or target_delta_t_s <= 0.0:
            raise ValueError("target native delta_t_s must be finite and positive")
        target_measured_flow_rates = target_rates * target_alignment
        target_measured_flow_rate = float(target_measured_flow_rates.sum())
        mapped["target_face_native_alphaPhi_m3_s"] = target_rates
        mapped["summary"]["target_native_measurement"] = {
            "time_s": float(target_time_s),
            "delta_t_s": float(target_delta_t_s),
            "rate_convention": NATIVE_RATE_CONVENTION,
            "sign_convention": NATIVE_SIGN_CONVENTION,
            "native_oriented_rate_sum_m3_s": float(target_rates.sum()),
            "rate_along_declared_flow_m3_s": target_measured_flow_rate,
            "step_volume_along_flow_m3": target_measured_flow_rate * target_delta_t_s,
            "mapped_prediction_minus_measurement_rate_m3_s": (
                mapped_flow_rate - target_measured_flow_rate
            ),
            "source_and_target_step_volumes_share_same_delta_t": math.isclose(
                source_delta_t_s, target_delta_t_s, rel_tol=0.0, abs_tol=1e-12
            ),
        }
    elif target_time_s is not None or target_delta_t_s is not None:
        raise ValueError("target time/delta_t metadata requires target native alphaPhi values")
    return mapped


def _rectangular_faces(
    bounds: Any,
    *,
    name: str,
    geometry_tolerance_m: float,
    supplied_areas_m2: Any | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    face_bounds = _finite_array(bounds, (6,), f"{name}_bounds_xyz_m")
    widths = face_bounds[:, 3:6] - face_bounds[:, 0:3]
    if np.any(widths[:, 0] <= geometry_tolerance_m) or np.any(widths[:, 1] <= geometry_tolerance_m):
        raise ValueError(f"{name} contains a zero-width or zero-height rectangle")
    if np.any(np.abs(widths[:, 2]) > geometry_tolerance_m):
        raise ValueError(f"{name} faces must be planar rectangles at constant z")
    z_centres = (face_bounds[:, 2] + face_bounds[:, 5]) * 0.5
    if float(np.ptp(z_centres)) > geometry_tolerance_m:
        raise ValueError(f"{name} faces do not lie in one common source plane")
    geometric_areas = widths[:, 0] * widths[:, 1]
    if supplied_areas_m2 is None:
        areas = geometric_areas
    else:
        areas = np.asarray(supplied_areas_m2, dtype=np.float64)
        if areas.shape != (face_bounds.shape[0],) or not np.isfinite(areas).all():
            raise ValueError(f"{name}_area_m2 must be a finite vector matching the face count")
        if np.any(areas <= 0.0):
            raise ValueError(f"{name}_area_m2 must be positive")
        area_atol = geometry_tolerance_m * np.maximum(widths[:, 0], widths[:, 1]) * 2.0
        if not np.all(np.abs(areas - geometric_areas) <= area_atol + 1e-10 * geometric_areas):
            raise ValueError(f"{name} area does not match its axis-aligned rectangular bounds")
    return face_bounds, areas, float(np.mean(z_centres))


def _check_rectangular_partition(
    bounds: np.ndarray,
    areas: np.ndarray,
    *,
    name: str,
    geometry_tolerance_m: float,
    relative_area_tolerance: float,
) -> dict[str, float]:
    """Reject positive-area gaps and overlaps in one rectangular face tiling."""
    x0, y0 = np.min(bounds[:, :2], axis=0)
    x1, y1 = np.max(bounds[:, 3:5], axis=0)
    envelope_area = float((x1 - x0) * (y1 - y0))
    total_area = float(areas.sum())
    area_atol = max(
        1e-14,
        geometry_tolerance_m * max(float(x1 - x0), float(y1 - y0)) * 2.0,
    )
    if not math.isclose(
        total_area, envelope_area, rel_tol=relative_area_tolerance, abs_tol=area_atol
    ):
        raise ValueError(
            f"{name} faces do not tile their bounding rectangle: "
            f"face area={total_area:.12g} m2, envelope={envelope_area:.12g} m2"
        )

    order = np.argsort(bounds[:, 0], kind="stable")
    active: list[int] = []
    for index in order:
        xmin = bounds[index, 0]
        active = [other for other in active if bounds[other, 3] > xmin + geometry_tolerance_m]
        for other in active:
            overlap_x = min(bounds[index, 3], bounds[other, 3]) - max(
                bounds[index, 0], bounds[other, 0]
            )
            overlap_y = min(bounds[index, 4], bounds[other, 4]) - max(
                bounds[index, 1], bounds[other, 1]
            )
            if overlap_x > geometry_tolerance_m and overlap_y > geometry_tolerance_m:
                raise ValueError(f"{name} faces overlap with positive area")
        active.append(int(index))
    return {
        "face_area_sum_m2": total_area,
        "bounding_rectangle_area_m2": envelope_area,
        "x_span_m": float(x1 - x0),
        "y_span_m": float(y1 - y0),
    }


def _map_bounds_to_target(
    bounds: np.ndarray,
    source_origin: np.ndarray,
    target_origin: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the documented horizontal coordinate swap and anchor translation."""
    mapped = np.empty_like(bounds)
    mapped[:, 0] = target_origin[0] + bounds[:, 1] - source_origin[1]
    mapped[:, 1] = target_origin[1] + bounds[:, 0] - source_origin[0]
    mapped[:, 2] = target_origin[2] + bounds[:, 2] - source_origin[2]
    mapped[:, 3] = target_origin[0] + bounds[:, 4] - source_origin[1]
    mapped[:, 4] = target_origin[1] + bounds[:, 3] - source_origin[0]
    mapped[:, 5] = target_origin[2] + bounds[:, 5] - source_origin[2]
    translation = np.asarray(
        [
            target_origin[0] - source_origin[1],
            target_origin[1] - source_origin[0],
            target_origin[2] - source_origin[2],
        ],
        dtype=np.float64,
    )
    return mapped, translation


def _overlap_weights(
    source_bounds_target: np.ndarray,
    target_bounds: np.ndarray,
    source_areas: np.ndarray,
    target_areas: np.ndarray,
    *,
    geometry_tolerance_m: float,
    relative_area_tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source_order = np.argsort(source_bounds_target[:, 0], kind="stable")
    ordered_xmin = source_bounds_target[source_order, 0]
    target_ids: list[int] = []
    source_ids: list[int] = []
    overlap_areas: list[float] = []
    for target_id, target in enumerate(target_bounds):
        stop = int(np.searchsorted(ordered_xmin, target[3] - geometry_tolerance_m, side="left"))
        candidates = source_order[:stop]
        if candidates.size == 0:
            continue
        candidates = candidates[
            source_bounds_target[candidates, 3] > target[0] + geometry_tolerance_m
        ]
        if candidates.size == 0:
            continue
        overlap_x = np.minimum(source_bounds_target[candidates, 3], target[3]) - np.maximum(
            source_bounds_target[candidates, 0], target[0]
        )
        overlap_y = np.minimum(source_bounds_target[candidates, 4], target[4]) - np.maximum(
            source_bounds_target[candidates, 1], target[1]
        )
        valid = (overlap_x > geometry_tolerance_m) & (overlap_y > geometry_tolerance_m)
        for source_id, area in zip(
            candidates[valid], overlap_x[valid] * overlap_y[valid], strict=True
        ):
            if area > 0.0:
                target_ids.append(target_id)
                source_ids.append(int(source_id))
                overlap_areas.append(float(area))

    ti = np.asarray(target_ids, dtype=np.int64)
    si = np.asarray(source_ids, dtype=np.int64)
    weights = np.asarray(overlap_areas, dtype=np.float64)
    if weights.size == 0:
        raise ValueError("source and target face rectangles do not overlap")
    covered_target = np.bincount(ti, weights=weights, minlength=target_areas.size)
    covered_source = np.bincount(si, weights=weights, minlength=source_areas.size)
    domain_scale = max(
        float(np.ptp(target_bounds[:, 0:1])),
        float(np.ptp(target_bounds[:, 1:2])),
        float(np.max(target_bounds[:, 3] - target_bounds[:, 0])),
        float(np.max(target_bounds[:, 4] - target_bounds[:, 1])),
    )
    area_atol = max(1e-14, geometry_tolerance_m * domain_scale * 2.0)
    if not np.allclose(covered_target, target_areas, rtol=relative_area_tolerance, atol=area_atol):
        bad = int(
            np.flatnonzero(
                ~np.isclose(
                    covered_target, target_areas, rtol=relative_area_tolerance, atol=area_atol
                )
            )[0]
        )
        raise ValueError(
            f"target face {bad} is not fully covered by source samples "
            f"({covered_target[bad]:.12g} of {target_areas[bad]:.12g} m2)"
        )
    if not np.allclose(covered_source, source_areas, rtol=relative_area_tolerance, atol=area_atol):
        bad = int(
            np.flatnonzero(
                ~np.isclose(
                    covered_source, source_areas, rtol=relative_area_tolerance, atol=area_atol
                )
            )[0]
        )
        raise ValueError(
            f"mapped source face {bad} is not fully covered by target faces "
            f"({covered_source[bad]:.12g} of {source_areas[bad]:.12g} m2)"
        )
    return ti, si, weights


def _overlap_average(
    values: np.ndarray,
    target_ids: np.ndarray,
    source_ids: np.ndarray,
    overlap_areas: np.ndarray,
    target_areas: np.ndarray,
) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    shape = (target_areas.size,) + values.shape[1:]
    integrated = np.zeros(shape, dtype=np.float64)
    np.add.at(
        integrated,
        target_ids,
        overlap_areas.reshape((-1,) + (1,) * (values.ndim - 1)) * values[source_ids],
    )
    return integrated / target_areas.reshape((-1,) + (1,) * (values.ndim - 1))


def _integrated_proxies(
    alpha: np.ndarray,
    velocity: np.ndarray,
    areas: np.ndarray,
    density: float,
    flow_direction: np.ndarray,
) -> dict[str, Any]:
    normal_speed = velocity @ flow_direction
    area = float(areas.sum())
    volume_flow = float(np.sum(areas * alpha * normal_speed))
    momentum = density * np.sum((areas * alpha * normal_speed)[:, None] * velocity, axis=0)
    kinetic_energy = float(
        0.5
        * density
        * np.sum(areas * alpha * normal_speed * np.einsum("ij,ij->i", velocity, velocity))
    )
    phase_volume = float(np.sum(areas * alpha))
    phase_velocity = (
        np.sum((areas * alpha)[:, None] * velocity, axis=0) / phase_volume
        if phase_volume > 0.0
        else np.zeros(3, dtype=np.float64)
    )
    return {
        "area_m2": area,
        "area_mean_alpha": float(np.sum(areas * alpha) / area),
        "area_mean_velocity_xyz_m_s": (np.sum(areas[:, None] * velocity, axis=0) / area).tolist(),
        "water_volume_transport_proxy_m3_s": volume_flow,
        "water_mass_transport_proxy_kg_s": density * volume_flow,
        "water_phase_mean_velocity_xyz_m_s": phase_velocity.tolist(),
        "convective_momentum_transport_proxy_N_xyz": momentum.tolist(),
        "convective_kinetic_energy_transport_proxy_W": kinetic_energy,
    }


def map_discharge_profile(
    source_face_bounds_xyz_m: Any,
    source_face_velocity_xyz_m_s: Any,
    source_face_alpha: Any,
    target_face_bounds_xyz_m: Any,
    target_face_area_m2: Any,
    *,
    source_origin_xyz_m: Sequence[float],
    target_origin_xyz_m: Sequence[float],
    profile_time_s: float,
    water_density_kg_m3: float = 1000.0,
    flow_direction_target_xyz: Sequence[float] = (0.0, 0.0, -1.0),
    source_face_area_m2: Any | None = None,
    geometry_tolerance_m: float = 1e-8,
    relative_area_tolerance: float = 1e-8,
    source_face_alpha_phi_m3_s: Any | None = None,
    source_face_native_id: Any | None = None,
    source_face_normal_unit_xyz: Any | None = None,
    target_face_native_id: Any | None = None,
    target_face_normal_unit_xyz: Any | None = None,
    native_alpha_phi_time_s: float | None = None,
    native_alpha_phi_delta_t_s: float | None = None,
    target_face_native_alpha_phi_m3_s: Any | None = None,
    target_native_time_s: float | None = None,
    target_native_delta_t_s: float | None = None,
) -> dict[str, Any]:
    """Map one planar source snapshot to target faces by exact rectangle overlap.

    The returned target phase velocity is the alpha-weighted mean, so alpha and
    alpha*U are both overlap-conservative.  A separate unweighted target
    velocity preserves area-mean U components.  Higher convective moments are
    reported as direct overlap averages and as reconstructed values from the
    mapped primitives; their difference measures covariance/energy smoothing.
    ``source_integrated_proxies`` and the alpha/U reconstruction remain
    geometric profile proxies.  An optional, separate native ``alphaPhi_``
    channel accepts actual signed per-face solver rates and conservatively
    remaps those rates by area overlap; its target values are predictions, not
    target-solver measurements unless an actual target field is separately
    supplied.
    """
    if not math.isfinite(profile_time_s) or profile_time_s < 0.0:
        raise ValueError("profile_time_s must be finite and nonnegative")
    if not math.isfinite(geometry_tolerance_m) or geometry_tolerance_m <= 0.0:
        raise ValueError("geometry_tolerance_m must be finite and positive")
    if (
        not math.isfinite(relative_area_tolerance)
        or relative_area_tolerance <= 0.0
        or relative_area_tolerance >= 1.0
    ):
        raise ValueError("relative_area_tolerance must be finite and in (0, 1)")
    if not math.isfinite(water_density_kg_m3) or water_density_kg_m3 <= 0.0:
        raise ValueError("water_density_kg_m3 must be finite and positive")

    source_bounds, source_areas, source_plane_z = _rectangular_faces(
        source_face_bounds_xyz_m,
        name="source",
        geometry_tolerance_m=geometry_tolerance_m,
        supplied_areas_m2=source_face_area_m2,
    )
    source_velocity = _finite_array(
        source_face_velocity_xyz_m_s, (3,), "source_face_velocity_xyz_m_s"
    )
    source_alpha = np.asarray(source_face_alpha, dtype=np.float64)
    if source_alpha.shape != (source_bounds.shape[0],) or not np.isfinite(source_alpha).all():
        raise ValueError("source_face_alpha must be a finite vector matching source face count")
    if np.any(source_alpha < 0.0) or np.any(source_alpha > 1.0):
        raise ValueError("source_face_alpha values must lie in [0, 1]")
    if source_velocity.shape[0] != source_bounds.shape[0]:
        raise ValueError("source velocity count does not match source face count")
    target_bounds, target_areas, target_plane_z = _rectangular_faces(
        target_face_bounds_xyz_m,
        name="target",
        geometry_tolerance_m=geometry_tolerance_m,
        supplied_areas_m2=target_face_area_m2,
    )
    source_origin = _finite_vector(source_origin_xyz_m, "source_origin_xyz_m")
    target_origin = _finite_vector(target_origin_xyz_m, "target_origin_xyz_m")
    flow_direction = _finite_vector(flow_direction_target_xyz, "flow_direction_target_xyz")
    norm = float(np.linalg.norm(flow_direction))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("flow_direction_target_xyz must be a unit vector")

    source_partition = _check_rectangular_partition(
        source_bounds,
        source_areas,
        name="source",
        geometry_tolerance_m=geometry_tolerance_m,
        relative_area_tolerance=relative_area_tolerance,
    )
    target_partition = _check_rectangular_partition(
        target_bounds,
        target_areas,
        name="target",
        geometry_tolerance_m=geometry_tolerance_m,
        relative_area_tolerance=relative_area_tolerance,
    )
    source_bounds_target, translation = _map_bounds_to_target(
        source_bounds, source_origin, target_origin
    )
    mapped_source_areas = (source_bounds_target[:, 3] - source_bounds_target[:, 0]) * (
        source_bounds_target[:, 4] - source_bounds_target[:, 1]
    )
    if not np.allclose(mapped_source_areas, source_areas, rtol=relative_area_tolerance, atol=1e-14):
        raise ValueError("coordinate map changed rectangular face areas")
    source_total = float(source_areas.sum())
    target_total = float(target_areas.sum())
    if not math.isclose(
        source_total,
        target_total,
        rel_tol=relative_area_tolerance,
        abs_tol=geometry_tolerance_m
        * max(source_partition["x_span_m"], source_partition["y_span_m"])
        * 2,
    ):
        raise ValueError(
            "source and target aperture areas differ; refusing implicit crop or extrapolation"
        )
    target_envelope = np.asarray(
        [
            target_bounds[:, 0].min(),
            target_bounds[:, 1].min(),
            target_bounds[:, 3].max(),
            target_bounds[:, 4].max(),
        ]
    )
    mapped_envelope = np.asarray(
        [
            source_bounds_target[:, 0].min(),
            source_bounds_target[:, 1].min(),
            source_bounds_target[:, 3].max(),
            source_bounds_target[:, 4].max(),
        ]
    )
    if not np.allclose(mapped_envelope, target_envelope, rtol=0.0, atol=geometry_tolerance_m):
        raise ValueError("translated source aperture bounds do not match target aperture bounds")
    if not math.isclose(
        float(target_origin[2] + source_plane_z - source_origin[2]),
        target_plane_z,
        rel_tol=0.0,
        abs_tol=geometry_tolerance_m,
    ):
        raise ValueError("source plane translation does not land on target source plane")

    target_ids, source_ids, overlap_areas = _overlap_weights(
        source_bounds_target,
        target_bounds,
        source_areas,
        target_areas,
        geometry_tolerance_m=geometry_tolerance_m,
        relative_area_tolerance=relative_area_tolerance,
    )
    native_values = (
        source_face_alpha_phi_m3_s,
        source_face_native_id,
        source_face_normal_unit_xyz,
        target_face_native_id,
        target_face_normal_unit_xyz,
        native_alpha_phi_time_s,
        native_alpha_phi_delta_t_s,
    )
    native_present = [value is not None for value in native_values]
    if any(native_present) and not all(native_present):
        raise ValueError("native alphaPhi mapping inputs must be supplied together")
    if target_face_native_alpha_phi_m3_s is not None and not all(native_present):
        raise ValueError(
            "target native alphaPhi requires the complete native source mapping inputs"
        )
    native_result: dict[str, Any] | None = None
    if all(native_present):
        if not math.isfinite(float(native_alpha_phi_time_s)) or not math.isclose(
            float(native_alpha_phi_time_s), profile_time_s, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("native source alphaPhi time must match profile_time_s")
        native_result = _native_flux_mapping(
            source_face_alpha_phi_m3_s,
            source_face_native_id,
            source_face_normal_unit_xyz,
            target_face_native_id,
            target_face_normal_unit_xyz,
            source_areas,
            target_areas,
            target_ids,
            source_ids,
            overlap_areas,
            flow_direction_target_xyz=flow_direction,
            profile_time_s=profile_time_s,
            source_delta_t_s=float(native_alpha_phi_delta_t_s),
            target_alpha_phi_m3_s=target_face_native_alpha_phi_m3_s,
            target_time_s=target_native_time_s,
            target_delta_t_s=target_native_delta_t_s,
        )
    source_velocity_target = source_velocity @ SOURCE_TO_TARGET_MATRIX.T
    mapped_alpha = _overlap_average(
        source_alpha, target_ids, source_ids, overlap_areas, target_areas
    )
    mapped_area_mean_velocity = _overlap_average(
        source_velocity_target, target_ids, source_ids, overlap_areas, target_areas
    )
    mapped_alpha_velocity = _overlap_average(
        source_alpha[:, None] * source_velocity_target,
        target_ids,
        source_ids,
        overlap_areas,
        target_areas,
    )
    mapped_phase_velocity = np.divide(
        mapped_alpha_velocity,
        mapped_alpha[:, None],
        out=np.zeros_like(mapped_alpha_velocity),
        where=mapped_alpha[:, None] > 0.0,
    )
    source_normal_speed = source_velocity_target @ flow_direction
    source_momentum_density = (
        water_density_kg_m3 * (source_alpha * source_normal_speed)[:, None] * source_velocity_target
    )
    source_energy_density = (
        0.5
        * water_density_kg_m3
        * source_alpha
        * source_normal_speed
        * np.einsum("ij,ij->i", source_velocity_target, source_velocity_target)
    )
    mapped_momentum_density = _overlap_average(
        source_momentum_density, target_ids, source_ids, overlap_areas, target_areas
    )
    mapped_energy_density = _overlap_average(
        source_energy_density, target_ids, source_ids, overlap_areas, target_areas
    )

    source_proxies = _integrated_proxies(
        source_alpha,
        source_velocity_target,
        source_areas,
        water_density_kg_m3,
        flow_direction,
    )
    target_reconstructed_proxies = _integrated_proxies(
        mapped_alpha,
        mapped_phase_velocity,
        target_areas,
        water_density_kg_m3,
        flow_direction,
    )
    target_area_mean_velocity = (
        np.sum(target_areas[:, None] * mapped_area_mean_velocity, axis=0) / target_total
    )
    source_area_mean_velocity = (
        np.sum(source_areas[:, None] * source_velocity_target, axis=0) / source_total
    )
    target_momentum_overlap = np.sum(target_areas[:, None] * mapped_momentum_density, axis=0)
    target_energy_overlap = float(np.sum(target_areas * mapped_energy_density))
    source_momentum = np.asarray(source_proxies["convective_momentum_transport_proxy_N_xyz"])
    target_momentum = np.asarray(
        target_reconstructed_proxies["convective_momentum_transport_proxy_N_xyz"]
    )
    mapped_mass_flux = water_density_kg_m3 * float(
        np.sum(target_areas * (mapped_alpha_velocity @ flow_direction))
    )
    if not math.isclose(
        mapped_mass_flux,
        source_proxies["water_mass_transport_proxy_kg_s"],
        rel_tol=1e-10,
        abs_tol=1e-10,
    ):
        raise RuntimeError("overlap mapping failed to conserve alpha*U transport proxy")
    if not np.allclose(
        target_area_mean_velocity, source_area_mean_velocity, rtol=1e-10, atol=1e-10
    ):
        raise RuntimeError("overlap mapping failed to conserve area-mean velocity components")

    result = {
        "profile_time_s": float(profile_time_s),
        "target_face_alpha": mapped_alpha,
        "target_face_velocity_xyz_m_s": mapped_phase_velocity,
        "target_face_area_mean_velocity_xyz_m_s": mapped_area_mean_velocity,
        "target_face_alpha_velocity_density_xyz_m_s": mapped_alpha_velocity,
        "target_face_momentum_flux_density_N_per_m2_xyz": mapped_momentum_density,
        "target_face_kinetic_energy_flux_density_W_m2": mapped_energy_density,
        "overlap_target_face_index": target_ids,
        "overlap_source_face_index": source_ids,
        "overlap_area_m2": overlap_areas,
        "transformed_source_face_bounds_xyz_m": source_bounds_target,
        "summary": {
            "source_profile_time_semantics": "single saved snapshot only; no time interpolation, forcing fit, or hold beyond the supplied time",
            "coordinate_mapping": {
                "source_axes": {"x": "transverse", "y": "streamwise", "z": "vertical upward"},
                "target_axes": {"x": "streamwise", "y": "transverse", "z": "vertical upward"},
                "source_to_target_matrix": SOURCE_TO_TARGET_MATRIX.tolist(),
                "origin_translation_xyz_m": translation.tolist(),
                "source_origin_xyz_m": source_origin.tolist(),
                "target_origin_xyz_m": target_origin.tolist(),
                "source_plane_z_m": source_plane_z,
                "target_plane_z_m": target_plane_z,
                "flow_direction_target_unit_xyz": flow_direction.tolist(),
            },
            "geometry": {
                "source_face_count": int(source_bounds.shape[0]),
                "target_face_count": int(target_bounds.shape[0]),
                "overlap_count": int(overlap_areas.size),
                "source_partition": source_partition,
                "target_partition": target_partition,
                "source_face_area_validation": (
                    "supplied polygon areas checked against rectangular bounds"
                    if source_face_area_m2 is not None
                    else "area derived from declared rectangular bounds"
                ),
                "source_total_area_m2": source_total,
                "target_total_area_m2": target_total,
                "fully_covered_both_directions": True,
                "geometry_tolerance_m": float(geometry_tolerance_m),
                "relative_area_tolerance": float(relative_area_tolerance),
            },
            "water_density_kg_m3": float(water_density_kg_m3),
            "source_integrated_proxies": source_proxies,
            "target_reconstructed_from_mapped_alpha_and_phase_velocity": target_reconstructed_proxies,
            "target_conservative_overlap_moments": {
                "area_mean_velocity_xyz_m_s": target_area_mean_velocity.tolist(),
                "water_mass_transport_proxy_kg_s": mapped_mass_flux,
                "convective_momentum_transport_proxy_N_xyz": target_momentum_overlap.tolist(),
                "convective_kinetic_energy_transport_proxy_W": target_energy_overlap,
            },
            "smoothing_diagnostics": {
                "area_mean_velocity_component_error_xyz_m_s": (
                    target_area_mean_velocity - source_area_mean_velocity
                ).tolist(),
                "reconstructed_momentum_proxy_delta_target_minus_source_N_xyz": (
                    target_momentum - source_momentum
                ).tolist(),
                "momentum_proxy_covariance_loss_source_minus_reconstructed_N_xyz": (
                    source_momentum - target_momentum
                ).tolist(),
                "kinetic_energy_proxy_delta_target_minus_source_W": (
                    target_reconstructed_proxies["convective_kinetic_energy_transport_proxy_W"]
                    - source_proxies["convective_kinetic_energy_transport_proxy_W"]
                ),
                "kinetic_energy_proxy_smoothing_loss_source_minus_reconstructed_W": (
                    source_proxies["convective_kinetic_energy_transport_proxy_W"]
                    - target_reconstructed_proxies["convective_kinetic_energy_transport_proxy_W"]
                ),
            },
            "interpretation_limit": (
                "These are geometric saved-profile transport and convective-moment proxies. "
                "They do not replace a native alphaPhi or solver flux measurement. "
                "The phase velocity recovers overlap-averaged alpha*U; higher moments "
                "need not survive reconstruction from one target alpha/U pair."
            ),
        },
    }
    if native_result is not None:
        result.update({key: value for key, value in native_result.items() if key != "summary"})
        result["summary"]["native_alphaPhi_mapping"] = native_result["summary"]
    return result


def _json_safe_summary(result: dict[str, Any]) -> dict[str, Any]:
    return result["summary"]


def run_cli(input_json: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    config = json.loads(input_json.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema") not in {
        INPUT_SCHEMA,
        INPUT_SCHEMA_NATIVE_FLUX,
    }:
        raise ValueError(
            f"input JSON must use schema {INPUT_SCHEMA!r} or {INPUT_SCHEMA_NATIVE_FLUX!r}"
        )
    native_schema = config["schema"] == INPUT_SCHEMA_NATIVE_FLUX
    allowed_config = {
        "schema",
        "profile_time_s",
        "arrays_npz",
        "source_origin_xyz_m",
        "target_origin_xyz_m",
        "water_density_kg_m3",
        "flow_direction_target_xyz",
        "geometry_tolerance_m",
        "relative_area_tolerance",
    }
    if native_schema:
        allowed_config.add("native_alphaPhi")
        if "native_alphaPhi" not in config:
            raise ValueError("native-flux input schema requires native_alphaPhi metadata")
    elif "native_alphaPhi" in config:
        raise ValueError("v1 input schema cannot declare native_alphaPhi metadata")
    unknown = set(config) - allowed_config
    if unknown:
        raise ValueError(f"unrecognized input manifest keys: {sorted(unknown)}")
    arrays_path = (input_json.parent / config["arrays_npz"]).resolve(strict=True)
    with np.load(arrays_path, allow_pickle=False) as archive:
        keys = set(archive.files)
        allowed_keys = NPZ_REQUIRED_KEYS.copy()
        if native_schema:
            missing_native = NPZ_NATIVE_FLUX_REQUIRED_KEYS - keys
            if missing_native:
                raise ValueError(f"native-flux NPZ is missing keys: {sorted(missing_native)}")
            allowed_keys |= NPZ_NATIVE_FLUX_REQUIRED_KEYS
            allowed_keys.add(NPZ_NATIVE_TARGET_MEASUREMENT_KEY)
        if keys != allowed_keys and not (
            native_schema and keys == allowed_keys - {NPZ_NATIVE_TARGET_MEASUREMENT_KEY}
        ):
            raise ValueError(f"NPZ keys must be exactly {sorted(allowed_keys)}, got {sorted(keys)}")
        arrays = {key: archive[key] for key in keys}
    native_metadata: dict[str, Any] | None = None
    if native_schema:
        native_metadata = config["native_alphaPhi"]
        if not isinstance(native_metadata, dict):
            raise ValueError("native_alphaPhi metadata must be an object")
        required_native_metadata = {
            "source_time_s",
            "source_delta_t_s",
            "source_rate_convention",
            "source_sign_convention",
            "target_measurement",
        }
        if set(native_metadata) != required_native_metadata:
            raise ValueError(
                f"native_alphaPhi metadata keys must be exactly {sorted(required_native_metadata)}"
            )
        if native_metadata["source_rate_convention"] != NATIVE_RATE_CONVENTION:
            raise ValueError("unsupported native source alphaPhi rate convention")
        if native_metadata["source_sign_convention"] != NATIVE_SIGN_CONVENTION:
            raise ValueError("unsupported native source alphaPhi sign convention")
        if not math.isclose(
            float(native_metadata["source_time_s"]),
            float(config["profile_time_s"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("native source time must match profile_time_s")
        target_measurement = native_metadata["target_measurement"]
        target_has_flux = NPZ_NATIVE_TARGET_MEASUREMENT_KEY in arrays
        if target_has_flux != (target_measurement is not None):
            raise ValueError("target native alphaPhi data and metadata must be supplied together")
        if target_measurement is not None:
            target_measurement_keys = {
                "time_s",
                "delta_t_s",
                "rate_convention",
                "sign_convention",
            }
            if (
                not isinstance(target_measurement, dict)
                or set(target_measurement) != target_measurement_keys
            ):
                raise ValueError(
                    "target_measurement metadata keys must be exactly "
                    f"{sorted(target_measurement_keys)}"
                )
            if target_measurement["rate_convention"] != NATIVE_RATE_CONVENTION:
                raise ValueError("unsupported target native alphaPhi rate convention")
            if target_measurement["sign_convention"] != NATIVE_SIGN_CONVENTION:
                raise ValueError("unsupported target native alphaPhi sign convention")
    result = map_discharge_profile(
        arrays["source_face_bounds_xyz_m"],
        arrays["source_face_velocity_xyz_m_s"],
        arrays["source_face_alpha"],
        arrays["target_face_bounds_xyz_m"],
        arrays["target_face_area_m2"],
        source_origin_xyz_m=config["source_origin_xyz_m"],
        target_origin_xyz_m=config["target_origin_xyz_m"],
        profile_time_s=float(config["profile_time_s"]),
        water_density_kg_m3=float(config.get("water_density_kg_m3", 1000.0)),
        flow_direction_target_xyz=config.get("flow_direction_target_xyz", (0.0, 0.0, -1.0)),
        source_face_area_m2=arrays.get("source_face_area_m2"),
        geometry_tolerance_m=float(config.get("geometry_tolerance_m", 1e-8)),
        relative_area_tolerance=float(config.get("relative_area_tolerance", 1e-8)),
        source_face_alpha_phi_m3_s=arrays.get("source_face_alphaPhi_m3_s"),
        source_face_native_id=arrays.get("source_face_native_id"),
        source_face_normal_unit_xyz=arrays.get("source_face_normal_unit_xyz"),
        target_face_native_id=arrays.get("target_face_native_id"),
        target_face_normal_unit_xyz=arrays.get("target_face_normal_unit_xyz"),
        native_alpha_phi_time_s=(
            float(native_metadata["source_time_s"]) if native_metadata is not None else None
        ),
        native_alpha_phi_delta_t_s=(
            float(native_metadata["source_delta_t_s"]) if native_metadata is not None else None
        ),
        target_face_native_alpha_phi_m3_s=arrays.get(NPZ_NATIVE_TARGET_MEASUREMENT_KEY),
        target_native_time_s=(
            float(native_metadata["target_measurement"]["time_s"])
            if native_metadata is not None and native_metadata["target_measurement"] is not None
            else None
        ),
        target_native_delta_t_s=(
            float(native_metadata["target_measurement"]["delta_t_s"])
            if native_metadata is not None and native_metadata["target_measurement"] is not None
            else None
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    arrays_output = output_dir / "mapped_profile_arrays.npz"
    np.savez_compressed(
        arrays_output,
        target_face_alpha=result["target_face_alpha"],
        target_face_velocity_xyz_m_s=result["target_face_velocity_xyz_m_s"],
        target_face_area_mean_velocity_xyz_m_s=result["target_face_area_mean_velocity_xyz_m_s"],
        target_face_alpha_velocity_density_xyz_m_s=result[
            "target_face_alpha_velocity_density_xyz_m_s"
        ],
        target_face_momentum_flux_density_N_per_m2_xyz=result[
            "target_face_momentum_flux_density_N_per_m2_xyz"
        ],
        target_face_kinetic_energy_flux_density_W_m2=result[
            "target_face_kinetic_energy_flux_density_W_m2"
        ],
        overlap_target_face_index=result["overlap_target_face_index"],
        overlap_source_face_index=result["overlap_source_face_index"],
        overlap_area_m2=result["overlap_area_m2"],
        transformed_source_face_bounds_xyz_m=result["transformed_source_face_bounds_xyz_m"],
        **(
            {
                "source_face_native_id": result["source_face_native_id"],
                "source_face_normal_unit_target_xyz": result["source_face_normal_unit_target_xyz"],
                "source_face_alphaPhi_m3_s": result["source_face_alphaPhi_m3_s"],
                "target_face_native_id": result["target_face_native_id"],
                "target_face_normal_unit_xyz": result["target_face_normal_unit_xyz"],
                "target_face_mapped_alphaPhi_m3_s": result["target_face_mapped_alphaPhi_m3_s"],
                **(
                    {"target_face_native_alphaPhi_m3_s": result["target_face_native_alphaPhi_m3_s"]}
                    if "target_face_native_alphaPhi_m3_s" in result
                    else {}
                ),
            }
            if "native_alphaPhi_mapping" in result["summary"]
            else {}
        ),
    )
    report = {
        "schema": SCHEMA_NATIVE_FLUX if "native_alphaPhi_mapping" in result["summary"] else SCHEMA,
        "status": "complete",
        "classification": (
            "conservative rectangular profile mapping with a separate native alphaPhi remap; "
            "not a CFD run or target solver flux audit"
            if "native_alphaPhi_mapping" in result["summary"]
            else "conservative rectangular profile mapping; not a CFD run or native flux audit"
        ),
        "input_json": str(input_json.resolve()),
        "input_json_sha256": sha256_file(input_json),
        "arrays_npz": str(arrays_path),
        "arrays_npz_sha256": sha256_file(arrays_path),
        "mapper_script": str(Path(__file__).resolve()),
        "mapper_script_sha256": sha256_file(Path(__file__).resolve()),
        "profile_time_s": result["profile_time_s"],
        "mapped_arrays_npz": str(arrays_output.resolve()),
        "mapped_arrays_npz_sha256": sha256_file(arrays_output),
        "summary": _json_safe_summary(result),
        "created_utc": dt.datetime.now(dt.UTC).isoformat(),
    }
    report_path = output_dir / "mapping.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_cli(args.input_json.resolve(strict=True), args.output_dir.resolve(strict=False))
    print(
        json.dumps(
            {
                "status": report["status"],
                "profile_time_s": report["profile_time_s"],
                "mapping_json": str((args.output_dir / "mapping.json").resolve()),
                "geometry": report["summary"]["geometry"],
                "source_integrated_proxies": report["summary"]["source_integrated_proxies"],
                "target_reconstructed_from_mapped_alpha_and_phase_velocity": report["summary"][
                    "target_reconstructed_from_mapped_alpha_and_phase_velocity"
                ],
                "smoothing_diagnostics": report["summary"]["smoothing_diagnostics"],
                "native_alphaPhi_mapping": report["summary"].get("native_alphaPhi_mapping"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
