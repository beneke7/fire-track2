#!/usr/bin/env python3
"""Analyze native OpenFOAM fields for the provisional I4F apparatus case.

Cell inventories and outlet patch profiles are reconstructed from PyVista's
OpenFOAMReader. Cross-section fluxes are interpolation-based diagnostics; the
global water ledger is enabled only from solver-written, signed phase-flux
logs on every open boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aerial_drop.i4f_reduced import R_AIR_J_KG_K, R_CO2_J_KG_K  # noqa: E402

OUTPUT_SCHEMA = "fire-track2-i4f-field-analysis-v7"
OPEN_PATCHES = ("ambientAnnulus", "externalSides", "outlet")
SECTION_STATION_NAMES = (
    "pipe_upstream",
    "post_valve",
    "pipe_end",
    "transition_mid",
    "nozzle_lip",
    "external_mid",
)
NUMBER_RE = re.compile(
    r"[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|inf(?:inity)?|nan)",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    good = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    total = float(np.sum(weights[good]))
    if total <= 0:
        return None
    return float(np.sum(values[good] * weights[good]) / total)


def _weighted_std(values: np.ndarray, weights: np.ndarray) -> float | None:
    mean = _weighted_mean(values, weights)
    if mean is None:
        return None
    good = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    total = float(np.sum(weights[good]))
    return float(np.sqrt(np.sum(weights[good] * (values[good] - mean) ** 2) / total))


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float | None:
    """Weighted quantile for nonnegative face or cell weights."""
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must lie in [0, 1]")
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    good = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(good):
        return None
    order = np.argsort(values[good], kind="stable")
    sorted_values = values[good][order]
    sorted_weights = weights[good][order]
    cumulative = np.cumsum(sorted_weights)
    target = quantile * cumulative[-1]
    index = min(int(np.searchsorted(cumulative, target, side="left")), len(sorted_values) - 1)
    return float(sorted_values[index])


def tank_cell_mask(centres_xyz_m: np.ndarray, tank: dict[str, Any]) -> np.ndarray:
    """Geometric tank-cylinder mask; returned cells are VTK reconstructed cells."""
    centres = np.asarray(centres_xyz_m, dtype=float)
    axis = np.asarray(tank.get("axis_vector", [1.0, 0.0, 0.0]), dtype=float)
    norm = float(np.linalg.norm(axis))
    if (
        centres.ndim != 2
        or centres.shape[1] != 3
        or axis.shape != (3,)
        or not np.all(np.isfinite(axis))
        or norm <= 0
        or not np.all(np.isfinite(centres))
    ):
        raise ValueError("tank cell centres or axis vector are invalid")
    axis = axis / norm
    length = float(tank["length_m"])
    if "center_xyz_m" in tank:
        origin = np.asarray(tank["center_xyz_m"], dtype=float)
        if origin.shape != (3,) or not np.all(np.isfinite(origin)):
            raise ValueError("tank center_xyz_m must contain three finite coordinates")
    elif np.allclose(axis, [1.0, 0.0, 0.0], rtol=0.0, atol=1e-12):
        start_x = float(tank.get("start_x_m", 0.0))
        origin = np.asarray([start_x + length / 2.0, 0.0, float(tank["center_z_m"])], dtype=float)
    elif np.allclose(axis, [0.0, 0.0, 1.0], rtol=0.0, atol=1e-12):
        origin = np.asarray([0.0, 0.0, float(tank["center_z_m"])], dtype=float)
    else:
        raise ValueError(
            "tank center_xyz_m is required for axes other than legacy x-horizontal or z-vertical"
        )
    relative = centres - origin
    axial = relative @ axis
    radial = relative - axial[:, None] * axis[None, :]
    radius = float(tank["diameter_m"]) / 2.0
    return (np.abs(axial) <= length / 2.0 + 1e-9) & (
        np.linalg.norm(radial, axis=1) <= radius + 1e-9
    )


def connection_mouth_xyz_m(config: dict[str, Any]) -> np.ndarray:
    """Return the pipe centerline mouth, honoring the explicit apparatus coordinate."""
    tank = config["tank"]
    connection = config.get("connection", {})
    explicit = connection.get("centerline_mouth_xyz_m")
    if explicit is not None:
        mouth = np.asarray(explicit, dtype=float)
        if mouth.shape != (3,) or not np.all(np.isfinite(mouth)):
            raise ValueError("connection.centerline_mouth_xyz_m must be three finite coordinates")
        return mouth
    return np.asarray(
        [
            float(tank.get("start_x_m", 0.0)) + float(tank["length_m"]),
            0.0,
            float(config.get("nozzle", {}).get("center_z_m", connection.get("center_z_m", 0.0))),
        ],
        dtype=float,
    )


def section_stations_for_config(config: dict[str, Any]) -> tuple[tuple[str, float], ...]:
    """Derive +x taps from the configured mouth, pipe, transition, and valve."""
    mouth_x = float(connection_mouth_xyz_m(config)[0])
    pipe = config["pipe"]
    pipe_end_x = mouth_x + float(pipe["length_m"])
    transition_end_x = pipe_end_x + float(pipe["transition_length_m"])
    analysis = config.get("analysis", {})
    valve_x = float(config.get("valve", {}).get("location_x_m", mouth_x + 0.4))
    tap_offset = float(analysis.get("pressure_tap_offset_m", 0.2))
    pipe_end_upstream_offset = float(analysis.get("pipe_end_upstream_offset_m", 0.1))
    lip_inset = float(analysis.get("nozzle_lip_inset_m", 0.01))
    external_offset = float(analysis.get("external_mid_offset_m", 1.0))
    if tap_offset <= 0 or pipe_end_upstream_offset < 0 or lip_inset <= 0 or external_offset <= 0:
        raise ValueError(
            "pressure-tap, lip, and external offsets must be positive; pipe-end upstream offset must be nonnegative"
        )
    lip_inset = min(lip_inset, float(pipe["transition_length_m"]) / 2.0)
    stations = {
        "pipe_upstream": valve_x - tap_offset,
        "post_valve": valve_x + tap_offset,
        "pipe_end": pipe_end_x - pipe_end_upstream_offset,
        "transition_mid": (pipe_end_x + transition_end_x) / 2.0,
        "nozzle_lip": transition_end_x - lip_inset,
        "external_mid": transition_end_x + external_offset,
    }
    overrides = analysis.get("section_station_overrides_x_m", {})
    unknown = set(overrides) - set(SECTION_STATION_NAMES)
    if unknown:
        raise ValueError(f"unknown section station override(s): {sorted(unknown)}")
    stations.update({name: float(value) for name, value in overrides.items()})
    if not all(math.isfinite(value) for value in stations.values()):
        raise ValueError("section station coordinates must be finite")
    tolerance = 1e-9
    if not mouth_x - tolerance <= stations["pipe_upstream"] <= pipe_end_x + tolerance:
        raise ValueError("pipe_upstream station must lie within the straight pipe")
    if not mouth_x - tolerance <= stations["post_valve"] <= pipe_end_x + tolerance:
        raise ValueError("post_valve station must lie within the straight pipe")
    if not mouth_x - tolerance <= stations["pipe_end"] <= pipe_end_x + tolerance:
        raise ValueError("pipe_end station must lie within the straight pipe")
    if not pipe_end_x <= stations["transition_mid"] <= transition_end_x:
        raise ValueError("transition_mid station must lie in the transition")
    if not pipe_end_x < stations["nozzle_lip"] < transition_end_x:
        raise ValueError("nozzle_lip station must lie just upstream of the outlet lip")
    if stations["external_mid"] <= transition_end_x:
        raise ValueError("external_mid station must lie downstream of the nozzle exit")
    return tuple((name, stations[name]) for name in SECTION_STATION_NAMES)


def line_cell_mask(centres_xyz_m: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    """Approximate the line region; vertical tanks include the curved port stub."""
    centres = np.asarray(centres_xyz_m, dtype=float)
    if centres.ndim != 2 or centres.shape[1] != 3 or not np.all(np.isfinite(centres)):
        raise ValueError("line cell centres must be a finite N-by-3 array")
    tank = config["tank"]
    pipe = config["pipe"]
    nozzle = config["nozzle"]
    mouth = connection_mouth_xyz_m(config)
    start_x = float(mouth[0])
    end_x = start_x + float(pipe["length_m"]) + float(pipe["transition_length_m"])
    half_y = max(float(pipe["diameter_m"]) / 2.0, float(nozzle["width_m"]) / 2.0) + 0.01
    half_z = max(float(pipe["diameter_m"]) / 2.0, float(nozzle["height_m"]) / 2.0) + 0.01
    axis = np.asarray(tank.get("axis_vector", [1.0, 0.0, 0.0]), dtype=float)
    axis_norm = float(np.linalg.norm(axis))
    if axis.shape != (3,) or not np.all(np.isfinite(axis)) or axis_norm <= 0.0:
        raise ValueError("tank axis vector must be a finite nonzero 3-vector")
    axis = axis / axis_norm
    if np.allclose(axis, [0.0, 0.0, 1.0], rtol=0.0, atol=1e-12) and "center_xyz_m" in tank:
        center = np.asarray(tank["center_xyz_m"], dtype=float)
        tank_mask = tank_cell_mask(centres, tank)
        radius = float(tank["diameter_m"]) / 2.0
        pipe_radius = float(pipe["diameter_m"]) / 2.0
        lateral_offset = abs(float(mouth[1]) - float(center[1])) + pipe_radius
        if lateral_offset > radius:
            raise ValueError("vertical tank pipe port does not intersect the cylinder side")
        stub_start_x = float(center[0]) + math.sqrt(radius**2 - lateral_offset**2)
        pipe_stub = (
            (centres[:, 0] >= stub_start_x - 1e-9)
            & (centres[:, 0] < start_x)
            & (
                (centres[:, 1] - mouth[1]) ** 2 + (centres[:, 2] - mouth[2]) ** 2
                <= pipe_radius**2 + 1e-9
            )
        )
        downstream = (
            (centres[:, 0] >= start_x)
            & (centres[:, 0] <= end_x)
            & (np.abs(centres[:, 1] - mouth[1]) <= half_y)
            & (np.abs(centres[:, 2] - mouth[2]) <= half_z)
        )
        return (pipe_stub | downstream) & ~tank_mask

    # Keep the original horizontal box envelope when no vertical curved stub applies.
    return (
        (centres[:, 0] >= start_x)
        & (centres[:, 0] <= end_x)
        & (np.abs(centres[:, 1] - mouth[1]) <= half_y)
        & (np.abs(centres[:, 2] - mouth[2]) <= half_z)
    )


def inventory_metrics(
    *,
    alpha_water: np.ndarray,
    cell_volumes_m3: np.ndarray,
    pressure_abs_Pa: np.ndarray,
    temperature_K: np.ndarray,
    centres_xyz_m: np.ndarray,
    tank_mask: np.ndarray,
    line_mask: np.ndarray | None = None,
    water_density_kg_m3: float,
    gas_constant_J_kg_K: float | None = None,
    gas_cv_J_kg_K: float | None = None,
) -> dict[str, float | None]:
    """Reconstructed cell-volume inventory and two headspace weighting choices."""
    alpha = np.asarray(alpha_water, dtype=float)
    volume = np.asarray(cell_volumes_m3, dtype=float)
    pressure = np.asarray(pressure_abs_Pa, dtype=float)
    temperature = np.asarray(temperature_K, dtype=float)
    tank = np.asarray(tank_mask, dtype=bool)
    line = np.zeros_like(tank) if line_mask is None else np.asarray(line_mask, dtype=bool)
    if not (alpha.shape == volume.shape == pressure.shape == temperature.shape == tank.shape):
        raise ValueError("cell inventory arrays must share one cell ordering")
    if line.shape != tank.shape:
        raise ValueError("line mask must share the inventory cell ordering")
    if np.any(volume <= 0) or not np.all(np.isfinite(volume)):
        raise ValueError("cell volumes must be finite and positive")
    alpha_raw = alpha
    alpha = np.clip(alpha_raw, 0.0, 1.0)
    air_fraction = 1.0 - alpha
    total_water_volume_raw = float(np.sum(alpha_raw * volume))
    total_water_volume_bounded = float(np.sum(alpha * volume))
    tank_water_volume_raw = float(np.sum(alpha_raw[tank] * volume[tank]))
    tank_water_volume_bounded = float(np.sum(alpha[tank] * volume[tank]))
    line_water_volume_raw = float(np.sum(alpha_raw[line] * volume[line]))
    line_water_volume_bounded = float(np.sum(alpha[line] * volume[line]))
    gas_volume_raw = float(np.sum((1.0 - alpha_raw[tank]) * volume[tank]))
    gas_volume_bounded = float(np.sum(air_fraction[tank] * volume[tank]))
    core = tank & (air_fraction >= 0.9)
    core_volume = float(np.sum(volume[core]))
    ideal_air_mass = None
    ideal_air_sensible_energy = None
    ideal_air_mass_weighted_pressure = None
    ideal_air_mass_weighted_temperature = None
    if gas_constant_J_kg_K is not None:
        if gas_constant_J_kg_K <= 0:
            raise ValueError("ideal-gas R must be positive")
        if gas_cv_J_kg_K is not None and gas_cv_J_kg_K <= 0:
            raise ValueError("ideal-gas Cv must be positive")
        valid_thermo = (pressure[tank] > 0.0) & (temperature[tank] > 0.0)
        gas_density = np.divide(
            pressure[tank],
            gas_constant_J_kg_K * temperature[tank],
            out=np.zeros_like(pressure[tank]),
            where=valid_thermo,
        )
        gas_mass_by_cell = air_fraction[tank] * volume[tank] * gas_density
        ideal_air_mass = float(np.sum(gas_mass_by_cell))
        if gas_cv_J_kg_K is not None:
            ideal_air_sensible_energy = float(
                np.sum(gas_mass_by_cell * gas_cv_J_kg_K * temperature[tank])
            )
        ideal_air_mass_weighted_pressure = _weighted_mean(pressure[tank], gas_mass_by_cell)
        ideal_air_mass_weighted_temperature = _weighted_mean(temperature[tank], gas_mass_by_cell)
    domain_gas_mass_raw = None
    domain_gas_mass_bounded = None
    domain_gas_energy_raw = None
    domain_gas_energy_bounded = None
    domain_gas_invalid_thermo_count = 0
    if gas_constant_J_kg_K is not None:
        if gas_constant_J_kg_K <= 0:
            raise ValueError("ideal-gas R must be positive")
        valid_domain_thermo = (
            np.isfinite(pressure)
            & np.isfinite(temperature)
            & (pressure > 0.0)
            & (temperature > 0.0)
        )
        domain_gas_invalid_thermo_count = int(np.count_nonzero(~valid_domain_thermo))
        gas_density_domain = np.divide(
            pressure,
            gas_constant_J_kg_K * temperature,
            out=np.zeros_like(pressure),
            where=valid_domain_thermo,
        )
        gas_fraction_raw = 1.0 - alpha_raw
        domain_gas_mass_raw_by_cell = gas_fraction_raw * volume * gas_density_domain
        domain_gas_mass_bounded_by_cell = air_fraction * volume * gas_density_domain
        domain_gas_mass_raw = float(np.sum(domain_gas_mass_raw_by_cell))
        domain_gas_mass_bounded = float(np.sum(domain_gas_mass_bounded_by_cell))
        if gas_cv_J_kg_K is not None:
            if gas_cv_J_kg_K <= 0:
                raise ValueError("ideal-gas Cv must be positive")
            safe_temperature = np.where(valid_domain_thermo, temperature, 0.0)
            domain_gas_energy_raw = float(
                np.sum(domain_gas_mass_raw_by_cell * gas_cv_J_kg_K * safe_temperature)
            )
            domain_gas_energy_bounded = float(
                np.sum(domain_gas_mass_bounded_by_cell * gas_cv_J_kg_K * safe_temperature)
            )
    return {
        "alpha_water_raw_min": float(np.min(alpha_raw)) if len(alpha_raw) else None,
        "alpha_water_raw_max": float(np.max(alpha_raw)) if len(alpha_raw) else None,
        "alpha_water_below_zero_cell_count": float(np.count_nonzero(alpha_raw < 0.0)),
        "alpha_water_above_one_cell_count": float(np.count_nonzero(alpha_raw > 1.0)),
        "total_water_volume_vtk_m3": total_water_volume_raw,
        "total_water_mass_vtk_kg": total_water_volume_raw * water_density_kg_m3,
        "total_water_volume_vtk_bounded_alpha_m3": total_water_volume_bounded,
        "total_water_inventory_bounding_delta_m3": (
            total_water_volume_bounded - total_water_volume_raw
        ),
        "tank_water_volume_vtk_m3": tank_water_volume_raw,
        "tank_water_mass_vtk_kg": tank_water_volume_raw * water_density_kg_m3,
        "tank_water_volume_vtk_bounded_alpha_m3": tank_water_volume_bounded,
        "tank_water_inventory_bounding_delta_m3": (
            tank_water_volume_bounded - tank_water_volume_raw
        ),
        "line_water_volume_vtk_raw_alpha_m3": line_water_volume_raw,
        "line_water_volume_vtk_bounded_alpha_m3": line_water_volume_bounded,
        "headspace_gas_volume_vtk_m3": gas_volume_raw,
        "headspace_gas_volume_vtk_bounded_alpha_m3": gas_volume_bounded,
        "headspace_air_fraction_mean_volume_weighted": _weighted_mean(
            air_fraction[tank], volume[tank]
        ),
        "headspace_pressure_gas_phase_weighted_bounded_alpha_Pa": _weighted_mean(
            pressure[tank], air_fraction[tank] * volume[tank]
        ),
        "headspace_temperature_gas_phase_weighted_bounded_alpha_K": _weighted_mean(
            temperature[tank], air_fraction[tank] * volume[tank]
        ),
        "headspace_air_mass_ideal_gas_bounded_alpha_kg": ideal_air_mass,
        "headspace_air_sensible_internal_energy_ideal_gas_bounded_alpha_J": ideal_air_sensible_energy,
        "headspace_air_pressure_ideal_mass_weighted_bounded_alpha_Pa": ideal_air_mass_weighted_pressure,
        "headspace_air_temperature_ideal_mass_weighted_bounded_alpha_K": ideal_air_mass_weighted_temperature,
        "domain_gas_volume_raw_alpha_m3": float(np.sum((1.0 - alpha_raw) * volume)),
        "domain_gas_volume_bounded_alpha_m3": float(np.sum(air_fraction * volume)),
        "domain_gas_mass_ideal_gas_raw_alpha_kg": domain_gas_mass_raw,
        "domain_gas_mass_ideal_gas_bounded_alpha_kg": domain_gas_mass_bounded,
        "domain_gas_mass_bounding_delta_kg": (
            domain_gas_mass_bounded - domain_gas_mass_raw
            if domain_gas_mass_bounded is not None and domain_gas_mass_raw is not None
            else None
        ),
        "domain_gas_sensible_internal_energy_ideal_gas_raw_alpha_J": domain_gas_energy_raw,
        "domain_gas_sensible_internal_energy_ideal_gas_bounded_alpha_J": domain_gas_energy_bounded,
        "domain_gas_ideal_eos_invalid_pressure_or_temperature_cell_count": float(
            domain_gas_invalid_thermo_count
        ),
        "headspace_pressure_gas_core_volume_weighted_Pa": _weighted_mean(
            pressure[core], volume[core]
        ),
        "headspace_temperature_gas_core_volume_weighted_K": _weighted_mean(
            temperature[core], volume[core]
        ),
        "headspace_gas_core_cell_volume_m3": core_volume,
    }


def outlet_face_metrics(
    *,
    centres_xyz_m: np.ndarray,
    face_areas_m2: np.ndarray,
    alpha_water: np.ndarray,
    velocity_xyz_m_s: np.ndarray,
    pressure_abs_Pa: np.ndarray,
    temperature_K: np.ndarray,
    normal_xyz: np.ndarray | None = None,
    water_density_kg_m3: float = 998.2,
    gas_constant_J_kg_K: float = R_AIR_J_KG_K,
    metric_prefix: str = "outlet",
) -> tuple[dict[str, float | None], dict[str, np.ndarray]]:
    """Profile estimates on a reconstructed plane/patch; not native fluxes."""
    centres = np.asarray(centres_xyz_m, dtype=float)
    area = np.asarray(face_areas_m2, dtype=float)
    alpha_raw = np.asarray(alpha_water, dtype=float)
    alpha = np.clip(alpha_raw, 0.0, 1.0)
    velocity = np.asarray(velocity_xyz_m_s, dtype=float)
    pressure = np.asarray(pressure_abs_Pa, dtype=float)
    temperature = np.asarray(temperature_K, dtype=float)
    normal = np.asarray([1.0, 0.0, 0.0] if normal_xyz is None else normal_xyz, dtype=float)
    normal_norm = float(np.linalg.norm(normal))
    if not math.isfinite(normal_norm) or normal_norm <= 0:
        raise ValueError("outlet normal must be a finite, nonzero 3-vector")
    normal = normal / normal_norm
    n_faces = len(area)
    if centres.shape != (n_faces, 3) or velocity.shape != (n_faces, 3):
        raise ValueError("outlet centers and velocity must be one vector per face")
    if not (alpha.shape == area.shape == pressure.shape == temperature.shape):
        raise ValueError("outlet scalar fields must be one value per face")
    if np.any(area <= 0) or not np.all(np.isfinite(area)):
        raise ValueError("outlet face areas must be finite and positive")

    air_fraction = 1.0 - alpha
    normal_velocity = velocity @ normal
    speed = np.linalg.norm(velocity, axis=1)
    flow_angle = np.degrees(
        np.arctan2(
            np.linalg.norm(velocity - normal_velocity[:, None] * normal, axis=1), normal_velocity
        )
    )
    water_density = np.full(n_faces, water_density_kg_m3)
    gas_density = np.divide(
        pressure,
        gas_constant_J_kg_K * temperature,
        out=np.zeros_like(pressure),
        where=temperature > 0,
    )
    forward = np.maximum(normal_velocity, 0.0)
    reverse = np.maximum(-normal_velocity, 0.0)
    water_face_flux_m3_s = alpha * normal_velocity * area
    water_face_flux_kg_s = water_density * water_face_flux_m3_s
    gas_face_flux_kg_s = gas_density * air_fraction * normal_velocity * area
    mixture_density = water_density * alpha + gas_density * air_fraction
    mixture_momentum_flux_xyz_N = np.sum(
        (mixture_density * normal_velocity * area)[:, None] * velocity, axis=0
    )
    water_momentum_flux_xyz_N = np.sum(
        (water_density * alpha * normal_velocity * area)[:, None] * velocity, axis=0
    )
    forward_water_momentum_flux_xyz_N = np.sum(
        (water_density * alpha * forward * area)[:, None] * velocity, axis=0
    )
    forward_water_normal_momentum_flux_N = float(np.dot(forward_water_momentum_flux_xyz_N, normal))
    forward_water_transverse_momentum_flux_N = float(
        np.linalg.norm(
            forward_water_momentum_flux_xyz_N - forward_water_normal_momentum_flux_N * normal
        )
    )
    net_forward_water_momentum_angle_deg = (
        float(
            np.degrees(
                np.arctan2(
                    forward_water_transverse_momentum_flux_N,
                    forward_water_normal_momentum_flux_N,
                )
            )
        )
        if float(np.sum(alpha * forward * area)) > 0.0
        and forward_water_normal_momentum_flux_N > 0.0
        and float(np.linalg.norm(forward_water_momentum_flux_xyz_N)) > 0.0
        else None
    )
    wet = alpha >= 0.5
    positive_water_weights = alpha * area * forward
    wet_velocity_weights = area * wet
    alpha_area_weights = alpha * area
    mean_wet_vn = _weighted_mean(normal_velocity, wet_velocity_weights)
    std_wet_vn = _weighted_std(normal_velocity, wet_velocity_weights)
    mean_alpha_vn = _weighted_mean(normal_velocity, alpha_area_weights)
    std_alpha_vn = _weighted_std(normal_velocity, alpha_area_weights)
    summary = {
        "outlet_face_count": float(n_faces),
        "outlet_area_m2": float(np.sum(area)),
        "outlet_area_weighted_water_fraction": _weighted_mean(alpha, area),
        "outlet_alpha_water_raw_min": float(np.min(alpha_raw)) if n_faces else None,
        "outlet_alpha_water_raw_max": float(np.max(alpha_raw)) if n_faces else None,
        "outlet_alpha_water_below_zero_face_count": float(np.count_nonzero(alpha_raw < 0.0)),
        "outlet_alpha_water_above_one_face_count": float(np.count_nonzero(alpha_raw > 1.0)),
        "outlet_area_fraction_alpha_ge_0p5": float(np.sum(area[wet]) / np.sum(area)),
        "outlet_water_wetted_area_m2_alpha_weighted": float(np.sum(alpha * area)),
        "outlet_forward_water_volume_flux_profile_approx_m3_s": float(
            np.sum(alpha * forward * area)
        ),
        "outlet_reverse_water_volume_flux_profile_approx_m3_s": float(
            np.sum(alpha * reverse * area)
        ),
        "outlet_forward_water_mass_flux_profile_approx_kg_s": float(
            np.sum(water_density * alpha * forward * area)
        ),
        "outlet_reverse_water_mass_flux_profile_approx_kg_s": float(
            np.sum(water_density * alpha * reverse * area)
        ),
        "outlet_reverse_face_area_fraction": float(
            np.sum(area[normal_velocity < 0]) / np.sum(area)
        ),
        "outlet_mean_normal_velocity_wet_area_m_s": mean_wet_vn,
        "outlet_cv_normal_velocity_wet_area": (
            None
            if mean_wet_vn in (None, 0.0) or std_wet_vn is None
            else std_wet_vn / abs(mean_wet_vn)
        ),
        "outlet_mean_normal_velocity_alpha_area_m_s": mean_alpha_vn,
        "outlet_cv_normal_velocity_alpha_area": (
            None
            if mean_alpha_vn in (None, 0.0) or std_alpha_vn is None
            else std_alpha_vn / abs(mean_alpha_vn)
        ),
        "outlet_normal_velocity_wet_area_p05_m_s": weighted_quantile(
            normal_velocity[wet], area[wet], 0.05
        ),
        "outlet_normal_velocity_wet_area_p50_m_s": weighted_quantile(
            normal_velocity[wet], area[wet], 0.50
        ),
        "outlet_normal_velocity_wet_area_p95_m_s": weighted_quantile(
            normal_velocity[wet], area[wet], 0.95
        ),
        "outlet_water_flux_weighted_angle_deg": _weighted_mean(flow_angle, positive_water_weights),
        "outlet_net_forward_water_momentum_angle_deg": net_forward_water_momentum_angle_deg,
        "outlet_signed_water_momentum_flux_normal_profile_approx_N": float(
            np.dot(water_momentum_flux_xyz_N, normal)
        ),
        "outlet_forward_water_momentum_flux_normal_profile_approx_N": forward_water_normal_momentum_flux_N,
        "outlet_forward_water_momentum_flux_transverse_profile_approx_N": forward_water_transverse_momentum_flux_N,
        "outlet_water_momentum_flux_x_profile_approx_N": float(water_momentum_flux_xyz_N[0]),
        "outlet_water_momentum_flux_y_profile_approx_N": float(water_momentum_flux_xyz_N[1]),
        "outlet_water_momentum_flux_z_profile_approx_N": float(water_momentum_flux_xyz_N[2]),
        "outlet_forward_water_momentum_flux_x_profile_approx_N": float(
            forward_water_momentum_flux_xyz_N[0]
        ),
        "outlet_forward_water_momentum_flux_y_profile_approx_N": float(
            forward_water_momentum_flux_xyz_N[1]
        ),
        "outlet_forward_water_momentum_flux_z_profile_approx_N": float(
            forward_water_momentum_flux_xyz_N[2]
        ),
        "outlet_mixture_momentum_flux_x_profile_approx_N": float(mixture_momentum_flux_xyz_N[0]),
        "outlet_mixture_momentum_flux_y_profile_approx_N": float(mixture_momentum_flux_xyz_N[1]),
        "outlet_mixture_momentum_flux_z_profile_approx_N": float(mixture_momentum_flux_xyz_N[2]),
        "outlet_area_weighted_gas_fraction": _weighted_mean(air_fraction, area),
        "outlet_forward_gas_mass_flux_profile_approx_kg_s": float(
            np.sum(gas_density * air_fraction * forward * area)
        ),
        "outlet_reverse_gas_mass_flux_profile_approx_kg_s": float(
            np.sum(gas_density * air_fraction * reverse * area)
        ),
    }
    profile = {
        "x_m": centres[:, 0],
        "y_m": centres[:, 1],
        "z_m": centres[:, 2],
        "face_area_m2": area,
        "alpha_water": alpha,
        "alpha_water_raw": alpha_raw,
        "alpha_water_bounded": alpha,
        "alpha_gas": air_fraction,
        "p_abs_Pa": pressure,
        "T_K": temperature,
        "rho_gas_ideal_air_kg_m3": gas_density,
        "Ux_m_s": velocity[:, 0],
        "Uy_m_s": velocity[:, 1],
        "Uz_m_s": velocity[:, 2],
        "normal_velocity_m_s": normal_velocity,
        "speed_m_s": speed,
        "flow_angle_deg": flow_angle,
        "water_volume_flux_profile_approx_m3_s_per_face": water_face_flux_m3_s,
        "water_mass_flux_profile_approx_kg_s_per_face": water_face_flux_kg_s,
        "gas_mass_flux_profile_approx_kg_s_per_face": gas_face_flux_kg_s,
        "forward_water_momentum_flux_x_approx_N_per_face": (
            water_density * alpha * forward * area * velocity[:, 0]
        ),
        "forward_water_momentum_flux_y_approx_N_per_face": (
            water_density * alpha * forward * area * velocity[:, 1]
        ),
        "forward_water_momentum_flux_z_approx_N_per_face": (
            water_density * alpha * forward * area * velocity[:, 2]
        ),
    }
    if metric_prefix != "outlet":
        summary = {metric_prefix + key[len("outlet") :]: value for key, value in summary.items()}
    return summary, profile


def section_profile_metrics(
    *,
    x_m: float,
    cell_areas_m2: np.ndarray,
    alpha_water: np.ndarray,
    pressure_abs_Pa: np.ndarray,
    temperature_K: np.ndarray,
    velocity_xyz_m_s: np.ndarray,
) -> dict[str, float | None]:
    """Area-weighted mesh-cut profile; flux is explicitly interpolation-based."""
    area = np.asarray(cell_areas_m2, dtype=float)
    alpha_raw = np.asarray(alpha_water, dtype=float)
    alpha = np.clip(alpha_raw, 0.0, 1.0)
    pressure = np.asarray(pressure_abs_Pa, dtype=float)
    temperature = np.asarray(temperature_K, dtype=float)
    velocity = np.asarray(velocity_xyz_m_s, dtype=float)
    if velocity.shape != (len(area), 3) or not (
        alpha.shape == pressure.shape == temperature.shape == area.shape
    ):
        raise ValueError("section arrays must have consistent cell ordering")
    water_flux = alpha * velocity[:, 0] * area
    wet = alpha >= 0.5
    return {
        "station_x_m": float(x_m),
        "cut_cell_count": float(len(area)),
        "cut_area_m2": float(np.sum(area)),
        "pressure_area_mean_Pa_approx": _weighted_mean(pressure, area),
        "pressure_area_p05_Pa_approx": weighted_quantile(pressure, area, 0.05),
        "pressure_area_p95_Pa_approx": weighted_quantile(pressure, area, 0.95),
        "temperature_area_mean_K_approx": _weighted_mean(temperature, area),
        "water_fraction_area_mean": _weighted_mean(alpha, area),
        "water_fraction_raw_area_mean": _weighted_mean(alpha_raw, area),
        "alpha_water_raw_min": float(np.min(alpha_raw)) if len(alpha_raw) else None,
        "alpha_water_raw_max": float(np.max(alpha_raw)) if len(alpha_raw) else None,
        "alpha_water_below_zero_cut_cell_count": float(np.count_nonzero(alpha_raw < 0.0)),
        "alpha_water_above_one_cut_cell_count": float(np.count_nonzero(alpha_raw > 1.0)),
        "wet_area_fraction_alpha_ge_0p5": float(np.sum(area[wet]) / np.sum(area))
        if len(area) and np.sum(area) > 0
        else None,
        "mean_Ux_area_mean_m_s_approx": _weighted_mean(velocity[:, 0], area),
        "water_volume_flux_approx_m3_s": float(np.sum(water_flux)),
        "reverse_water_volume_flux_approx_m3_s": float(np.sum(np.minimum(water_flux, 0.0))),
    }


def nominal_section_area_m2(x_m: float, config: dict[str, Any]) -> float | None:
    """Analytic pipe/linear-transition area for checking VTK mesh-cut coverage."""
    pipe = config["pipe"]
    nozzle = config["nozzle"]
    mouth_x = float(connection_mouth_xyz_m(config)[0])
    transition_start_x = mouth_x + float(pipe["length_m"])
    transition_end_x = transition_start_x + float(pipe["transition_length_m"])
    pipe_area = math.pi * float(pipe["diameter_m"]) ** 2 / 4.0
    nozzle_area = float(nozzle["width_m"]) * float(nozzle["height_m"])
    if x_m <= transition_start_x:
        return pipe_area
    if x_m <= transition_end_x:
        fraction = (x_m - transition_start_x) / (transition_end_x - transition_start_x)
        return pipe_area + fraction * (nozzle_area - pipe_area)
    return None


def parse_scalar_table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read OpenFOAM scalar rows, retaining nonfinite values for ledger rejection."""
    times: list[float] = []
    values: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "(")):
            continue
        numbers = NUMBER_RE.findall(stripped)
        if len(numbers) < 2:
            continue
        row = [float(item) for item in numbers]
        times.append(row[0])
        values.append(row[-1])
    if not times:
        return np.empty(0), np.empty(0)
    order = np.argsort(times, kind="stable")
    t = np.asarray(times, dtype=float)[order]
    v = np.asarray(values, dtype=float)[order]
    keep = np.ones(len(t), dtype=bool)
    for index in range(1, len(t)):
        if math.isfinite(t[index - 1]) and math.isfinite(t[index]):
            if t[index] - t[index - 1] <= 1e-12:
                if math.isfinite(v[index - 1]) and math.isfinite(v[index]):
                    keep[index] = False
    return t[keep], v[keep]


def find_function_table(case_dir: Path, object_names: Iterable[str], file_name: str) -> Path | None:
    matches: list[Path] = []
    wanted = set(object_names)
    for candidate in case_dir.glob(f"postProcessing/*/*/{file_name}"):
        object_name = candidate.parents[1].name
        if object_name in wanted:
            matches.append(candidate)
    if not matches:
        return None
    return sorted(matches, key=lambda path: path.as_posix())[-1]


def solver_time_output_format(case_dir: Path) -> tuple[str | None, int | None]:
    """Read explicit OpenFOAM Time formatting controls for roundoff accounting."""
    control_dict = case_dir / "system/controlDict"
    if not control_dict.is_file():
        return None, None
    clean = _strip_openfoam_comments(control_dict.read_text(encoding="utf-8"))
    formats = set(re.findall(r"\btimeFormat\s+(\w+)\s*;", clean))
    precisions = set(re.findall(r"\btimePrecision\s+(\d+)\s*;", clean))
    time_format = next(iter(formats)).lower() if len(formats) == 1 else None
    time_precision = int(next(iter(precisions))) if len(precisions) == 1 else None
    return time_format, time_precision


def _time_serialization_quantum_s(
    time_s: float, time_format: str | None, time_precision: int | None
) -> float:
    """Return one output quantum for a formatted time, or zero if unknown."""
    if time_format not in {"general", "fixed", "scientific"} or time_precision is None:
        return 0.0
    if time_precision < 1 or not math.isfinite(time_s) or time_s == 0.0:
        return 0.0
    if time_format == "fixed":
        exponent = -time_precision
    else:
        exponent = math.floor(math.log10(abs(time_s))) - time_precision
        if time_format == "general":
            exponent += 1
    return 10.0**exponent


def solver_time_interval_rounding_bound_s(
    previous_time_s: float,
    current_time_s: float,
    time_format: str | None,
    time_precision: int | None,
) -> float:
    """Bound an interval error from rounding its two serialized endpoints."""
    previous_quantum = _time_serialization_quantum_s(previous_time_s, time_format, time_precision)
    current_quantum = _time_serialization_quantum_s(current_time_s, time_format, time_precision)
    return 0.5 * (previous_quantum + current_quantum)


def solver_delta_t_matches_serialized_interval(
    actual_interval_s: float,
    delta_t_s: float,
    previous_time_s: float,
    current_time_s: float,
    time_format: str | None,
    time_precision: int | None,
) -> tuple[bool, float]:
    """Check deltaT against solver output, allowing only justified print rounding."""
    existing_tolerance_s = max(2e-9, 5e-4 * max(abs(actual_interval_s), abs(delta_t_s)))
    rounding_bound_s = solver_time_interval_rounding_bound_s(
        previous_time_s, current_time_s, time_format, time_precision
    )
    difference_s = abs(actual_interval_s - delta_t_s)
    return (
        difference_s <= existing_tolerance_s or difference_s <= rounding_bound_s,
        rounding_bound_s,
    )


def solver_step_table(case_dir: Path) -> dict[str, Any]:
    """Read time and deltaT pairs from the newest compressibleInterFoam log."""
    candidates = [path for path in case_dir.glob("log.compressibleInterFoam*") if path.is_file()]
    if not candidates:
        return {"available": False, "reason": "no compressibleInterFoam solver log found"}
    path = max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)
    rows: list[tuple[float, float]] = []
    delta_t: float | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        dt_match = re.match(r"^\s*deltaT\s*=\s*(\S+)", line)
        if dt_match:
            try:
                delta_t = float(dt_match.group(1))
            except ValueError:
                delta_t = None
            continue
        time_match = re.match(r"^\s*Time\s*=\s*(\S+)", line)
        if time_match and delta_t is not None:
            try:
                time_s = float(time_match.group(1))
            except ValueError:
                continue
            if math.isfinite(time_s) and math.isfinite(delta_t) and delta_t > 0.0:
                rows.append((time_s, delta_t))
    if not rows:
        return {
            "available": False,
            "reason": f"solver log contains no parsed deltaT/Time pairs: {path.name}",
            "solver_log": str(path.relative_to(case_dir)),
        }
    time_format, time_precision = solver_time_output_format(case_dir)
    by_time: dict[float, float] = {}
    for time_s, delta_t in rows:
        by_time[time_s] = delta_t
    times = np.asarray(sorted(by_time), dtype=float)
    delta_ts = np.asarray([by_time[time_s] for time_s in times], dtype=float)
    return {
        "available": True,
        "solver_log": str(path.relative_to(case_dir)),
        "time_s": times,
        "deltaT_s": delta_ts,
        "parsed_row_count": int(len(times)),
        "time_format": time_format,
        "time_precision": time_precision,
    }


def native_flux_ledger(
    *,
    volume_times_s: np.ndarray,
    stored_water_volume_m3: np.ndarray,
    flux_tables: dict[str, tuple[np.ndarray, np.ndarray]],
    n_alpha_sub_cycles: int | None = 1,
    ddt_scheme: str | None = "Euler",
    solver_step_times_s: np.ndarray | None = None,
    solver_delta_t_s: np.ndarray | None = None,
    solver_time_format: str | None = None,
    solver_time_precision: int | None = None,
    end_time_limit_s: float | None = None,
) -> dict[str, Any]:
    """Build a water ledger only when every solver endpoint has a native flux.

    OpenFOAM v2512 exposes the last alpha subcycle as alphaPhi0.water when
    nAlphaSubCycles > 1, so those samples are diagnostic and cannot be integrated
    as full time-step boundary fluxes. For Euler, each right-endpoint flux is
    weighted by the solver's actual deltaT. The first exact inventory/flux time
    is the reference; no earlier interval is inferred.
    """
    if n_alpha_sub_cycles is None:
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "nAlphaSubCycles could not be determined from system/fvSolution",
        }
    if n_alpha_sub_cycles != 1:
        return {
            "available": False,
            "diagnostic_available": True,
            "conservative_ledger_available": False,
            "n_alpha_sub_cycles": n_alpha_sub_cycles,
            "reason": (
                "alphaPhi0.water is the last alpha subcycle rather than the full-step "
                "time-averaged flux when nAlphaSubCycles > 1; logged values are diagnostic only"
            ),
            "diagnostic_flux_semantics": "last alpha subcycle sample; not integrated for closure",
        }
    if ddt_scheme != "Euler":
        return {
            "available": False,
            "diagnostic_available": True,
            "conservative_ledger_available": False,
            "n_alpha_sub_cycles": n_alpha_sub_cycles,
            "ddt_scheme": ddt_scheme,
            "reason": "right-endpoint phase-flux integration is only enabled for Euler time stepping",
        }
    if solver_step_times_s is None or solver_delta_t_s is None:
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "solver time/deltaT endpoints are required to verify complete flux coverage",
        }
    volume_times = np.asarray(volume_times_s, dtype=float)
    stored = np.asarray(stored_water_volume_m3, dtype=float)
    step_times = np.asarray(solver_step_times_s, dtype=float)
    step_dt = np.asarray(solver_delta_t_s, dtype=float)
    if volume_times.shape != stored.shape or len(volume_times) < 2:
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "solver total-water inventory requires at least two aligned rows",
        }
    if (
        not np.all(np.isfinite(volume_times))
        or not np.all(np.isfinite(stored))
        or np.any(np.diff(volume_times) <= 0.0)
    ):
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "solver total-water inventory times and values must be finite and increasing",
        }
    if step_times.shape != step_dt.shape or not len(step_times):
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "solver time-step log has no complete time/deltaT table",
        }
    if (
        not np.all(np.isfinite(step_times))
        or not np.all(np.isfinite(step_dt))
        or np.any(step_dt <= 0.0)
        or np.any(np.diff(step_times) <= 0.0)
    ):
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "solver step times and deltaT values must be finite and increasing",
        }
    for patch, pair in flux_tables.items():
        patch_times, patch_values = (np.asarray(item, dtype=float) for item in pair)
        if patch_times.shape != patch_values.shape or len(patch_times) < 2:
            return {
                "available": False,
                "conservative_ledger_available": False,
                "reason": f"native flux table has fewer than two aligned rows on {patch}",
            }
        if (
            not np.all(np.isfinite(patch_times))
            or not np.all(np.isfinite(patch_values))
            or np.any(np.diff(patch_times) <= 0.0)
        ):
            return {
                "available": False,
                "conservative_ledger_available": False,
                "reason": f"native flux times and values must be finite and increasing on {patch}",
            }
    if end_time_limit_s is not None:
        if not math.isfinite(end_time_limit_s):
            return {
                "available": False,
                "conservative_ledger_available": False,
                "reason": "analysis end-time limit is not finite",
            }
        volume_mask = volume_times <= end_time_limit_s + 1e-12
        volume_times = volume_times[volume_mask]
        stored = stored[volume_mask]
        step_mask = step_times <= end_time_limit_s + 1e-12
        step_times = step_times[step_mask]
        step_dt = step_dt[step_mask]
        flux_tables = {
            name: (
                np.asarray(pair[0], dtype=float)[
                    np.asarray(pair[0], dtype=float) <= end_time_limit_s + 1e-12
                ],
                np.asarray(pair[1], dtype=float)[
                    np.asarray(pair[0], dtype=float) <= end_time_limit_s + 1e-12
                ],
            )
            for name, pair in flux_tables.items()
        }
    missing = [patch for patch in OPEN_PATCHES if patch not in flux_tables]
    if missing:
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": f"solver-native water phase flux missing for open patches: {missing}",
            "missing_open_patches": missing,
        }
    nonempty = {name: pair for name, pair in flux_tables.items() if len(pair[0]) >= 2}
    if len(nonempty) != len(OPEN_PATCHES):
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "one or more native flux tables have fewer than two rows",
        }
    flux_times = nonempty[OPEN_PATCHES[0]][0]
    for patch in OPEN_PATCHES[1:]:
        patch_times = nonempty[patch][0]
        if patch_times.shape != flux_times.shape or not np.allclose(
            patch_times, flux_times, rtol=1e-9, atol=1e-12
        ):
            return {
                "available": False,
                "conservative_ledger_available": False,
                "diagnostic_available": True,
                "reason": f"native phase-flux sample times are not aligned for {patch}",
            }

    def exact_index(value: float, candidates: np.ndarray) -> int | None:
        index = int(np.searchsorted(candidates, value))
        for candidate_index in (index - 1, index):
            if 0 <= candidate_index < len(candidates):
                candidate = float(candidates[candidate_index])
                tolerance = max(1e-12, 1e-9 * max(abs(value), abs(candidate), 1.0))
                if abs(candidate - value) <= tolerance:
                    return candidate_index
        return None

    reference: tuple[int, int] | None = None
    for volume_index, volume_time in enumerate(volume_times):
        flux_index = exact_index(float(volume_time), flux_times)
        if flux_index is not None:
            reference = (volume_index, flux_index)
            break
    if reference is None:
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "no exact saved-inventory/native-flux time is available as a ledger reference",
        }
    reference_volume_index = reference[0]
    reference_time = float(volume_times[reference_volume_index])
    selected_times = volume_times[reference_volume_index:]
    selected_stored = stored[reference_volume_index:]
    final_time = float(selected_times[-1])

    flux_step_mask = (flux_times > reference_time + 1e-12) & (flux_times <= final_time + 1e-12)
    selected_flux_step_times = flux_times[flux_step_mask]
    solver_step_mask = (step_times > reference_time + 1e-12) & (step_times <= final_time + 1e-12)
    selected_solver_times = step_times[solver_step_mask]
    selected_solver_dt = step_dt[solver_step_mask]
    if (
        len(selected_solver_times) == 0
        or selected_solver_times.shape != selected_flux_step_times.shape
        or not np.allclose(selected_solver_times, selected_flux_step_times, rtol=1e-9, atol=1e-12)
    ):
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "native water flux does not cover every solver right-endpoint from the selected reference time through the final inventory",
            "reference_time_s": reference_time,
            "final_inventory_time_s": final_time,
            "expected_solver_step_count": int(len(selected_solver_times)),
            "observed_native_flux_step_count": int(len(selected_flux_step_times)),
            "flux_interval_coverage_complete_from_reference_time": False,
        }

    checkpoint_flux_indices: list[int] = []
    for checkpoint_time in selected_times:
        flux_index = exact_index(float(checkpoint_time), flux_times)
        if flux_index is None:
            return {
                "available": False,
                "conservative_ledger_available": False,
                "diagnostic_available": True,
                "reason": "solver total-water inventory checkpoint has no exact native flux endpoint",
                "checkpoint_time_s": float(checkpoint_time),
                "reference_time_s": reference_time,
            }
        checkpoint_flux_indices.append(flux_index)

    for index, (time_s, delta_t) in enumerate(
        zip(selected_solver_times, selected_solver_dt, strict=True)
    ):
        previous_time = reference_time if index == 0 else float(selected_solver_times[index - 1])
        actual_interval = float(time_s) - previous_time
        interval_matches, rounding_bound_s = solver_delta_t_matches_serialized_interval(
            actual_interval,
            float(delta_t),
            previous_time,
            float(time_s),
            solver_time_format,
            solver_time_precision,
        )
        if not interval_matches:
            return {
                "available": False,
                "conservative_ledger_available": False,
                "reason": "solver log deltaT does not match adjacent right-endpoint times",
                "time_s": float(time_s),
                "logged_deltaT_s": float(delta_t),
                "adjacent_time_interval_s": actual_interval,
                "solver_time_format": solver_time_format,
                "solver_time_precision": solver_time_precision,
                "serialized_time_interval_rounding_bound_s": rounding_bound_s,
            }

    patch_step_flux: dict[str, np.ndarray] = {}
    patch_checkpoint_flux: dict[str, list[float]] = {}
    total_step_flux = np.zeros(len(selected_solver_times), dtype=float)
    total_checkpoint_flux = np.zeros(len(selected_times), dtype=float)
    for patch in OPEN_PATCHES:
        values = nonempty[patch][1]
        step_values = values[flux_step_mask]
        checkpoint_values = values[checkpoint_flux_indices]
        patch_step_flux[patch] = step_values
        patch_checkpoint_flux[patch] = checkpoint_values.tolist()
        total_step_flux += step_values
        total_checkpoint_flux += checkpoint_values

    increments = total_step_flux * selected_solver_dt
    cumulative_at_steps = np.cumsum(increments)
    cumulative_out = np.zeros(len(selected_times), dtype=float)
    for index, checkpoint_time in enumerate(selected_times[1:], start=1):
        completed = selected_solver_times <= checkpoint_time + 1e-12
        if np.any(completed):
            cumulative_out[index] = cumulative_at_steps[np.flatnonzero(completed)[-1]]
    residual = selected_stored - selected_stored[0] + cumulative_out
    return {
        "available": True,
        "conservative_ledger_available": True,
        "flux_quantity": "full-step signed water volume flux (m^3/s) from solver-written phase flux; outward positive",
        "time_integration": "Euler right-endpoint sum Q(t_i)*solver_deltaT_i; first exact inventory/flux time is the reference and no earlier interval is inferred",
        "n_alpha_sub_cycles": n_alpha_sub_cycles,
        "ddt_scheme": ddt_scheme,
        "analysis_end_time_limit_s": end_time_limit_s,
        "solver_time_format": solver_time_format,
        "solver_time_precision": solver_time_precision,
        "reference_time_s": reference_time,
        "first_saved_inventory_time_s": float(volume_times[0]),
        "unledgered_pre_reference_duration_s": float(reference_time - volume_times[0]),
        "unledgered_pre_reference_water_volume_change_m3": float(selected_stored[0] - stored[0]),
        "time_s": selected_times.tolist(),
        "per_patch_outward_water_volume_flux_m3_s": patch_checkpoint_flux,
        "total_outward_water_volume_flux_m3_s": total_checkpoint_flux.tolist(),
        "native_flux_step_time_s": selected_solver_times.tolist(),
        "native_flux_step_deltaT_s": selected_solver_dt.tolist(),
        "per_patch_native_flux_step_outward_water_volume_m3_s": {
            patch: values.tolist() for patch, values in patch_step_flux.items()
        },
        "total_native_flux_step_outward_water_volume_m3_s": total_step_flux.tolist(),
        "cumulative_outward_water_volume_m3": cumulative_out.tolist(),
        "stored_total_water_volume_m3": selected_stored.tolist(),
        "water_volume_balance_residual_m3": residual.tolist(),
        "max_absolute_water_volume_balance_residual_m3": float(np.max(np.abs(residual))),
        "initial_water_volume_m3": float(selected_stored[0]),
        "final_water_volume_m3": float(selected_stored[-1]),
        "cumulative_net_outward_water_volume_m3": float(cumulative_out[-1]),
        "expected_solver_step_count": int(len(selected_solver_times)),
        "integrated_solver_step_count": int(len(selected_solver_times)),
        "solver_step_endpoint_coverage_complete": True,
        "flux_interval_coverage_complete_from_reference_time": True,
        "sample_time_interpolation_used": False,
        "interval_before_reference_time_integrated": False,
        "startup_interval_before_first_logged_flux_integrated": False,
    }


def native_gas_mass_ledger(
    *,
    inventory_times_s: np.ndarray,
    stored_gas_mass_raw_kg: np.ndarray,
    stored_gas_mass_bounded_kg: np.ndarray,
    stored_headspace_gas_mass_bounded_kg: np.ndarray | None = None,
    total_mass_flux_tables: dict[str, tuple[np.ndarray, np.ndarray]],
    water_volume_flux_tables: dict[str, tuple[np.ndarray, np.ndarray]],
    solver_step_times_s: np.ndarray,
    solver_delta_t_s: np.ndarray,
    water_density_kg_m3: float,
    solver_time_format: str | None = None,
    solver_time_precision: int | None = None,
    n_alpha_sub_cycles: int | None = 1,
    ddt_scheme: str | None = "Euler",
    end_time_limit_s: float | None = None,
) -> dict[str, Any]:
    """Reconcile EOS gas storage with native total-minus-water boundary mass flux.

    The solver-native outward gas mass flux is
    ``rhoPhi_total - rho_water*alphaPhi0.water``.  alphaPhi0.water is a full-step
    phase volume flux only for one alpha subcycle.  The mass ledger uses Euler
    right-endpoint quadrature from complete solver-log step times and compares
    the integrated flux against saved-field EOS gas inventories.  Storage can
    therefore be sampled less often than the boundary flux.
    """

    def unavailable(reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "available": False,
            "conservative_ledger_available": False,
            "reason": reason,
            **extra,
        }

    if n_alpha_sub_cycles is None:
        return unavailable("nAlphaSubCycles could not be determined from system/fvSolution")
    if n_alpha_sub_cycles != 1:
        return unavailable(
            "alphaPhi0.water is the last subcycle when nAlphaSubCycles > 1",
            diagnostic_available=True,
            n_alpha_sub_cycles=n_alpha_sub_cycles,
        )
    if ddt_scheme != "Euler":
        return unavailable(
            "right-endpoint gas-flux integration is only enabled for Euler stepping",
            diagnostic_available=True,
            ddt_scheme=ddt_scheme,
            n_alpha_sub_cycles=n_alpha_sub_cycles,
        )
    if not math.isfinite(water_density_kg_m3) or water_density_kg_m3 <= 0.0:
        return unavailable("water density must be finite and positive")

    inventory_times = np.asarray(inventory_times_s, dtype=float)
    gas_raw = np.asarray(stored_gas_mass_raw_kg, dtype=float)
    gas_bounded = np.asarray(stored_gas_mass_bounded_kg, dtype=float)
    headspace_bounded = (
        None
        if stored_headspace_gas_mass_bounded_kg is None
        else np.asarray(stored_headspace_gas_mass_bounded_kg, dtype=float)
    )
    step_times = np.asarray(solver_step_times_s, dtype=float)
    step_dt = np.asarray(solver_delta_t_s, dtype=float)
    if not (inventory_times.shape == gas_raw.shape == gas_bounded.shape) or (
        headspace_bounded is not None and inventory_times.shape != headspace_bounded.shape
    ):
        return unavailable("saved gas inventory time/mass arrays do not share one shape")
    if len(inventory_times) < 2:
        return unavailable("at least two saved gas inventory times are required")
    if (
        not np.all(np.isfinite(inventory_times))
        or not np.all(np.isfinite(gas_raw))
        or not np.all(np.isfinite(gas_bounded))
        or (
            headspace_bounded is not None
            and (not np.all(np.isfinite(headspace_bounded)) or np.any(headspace_bounded < 0.0))
        )
        or np.any(np.diff(inventory_times) <= 0.0)
    ):
        return unavailable("saved gas inventory times and values must be finite and increasing")
    if step_times.shape != step_dt.shape or not len(step_times):
        return unavailable("solver time-step log has no complete time/deltaT table")
    if (
        not np.all(np.isfinite(step_times))
        or not np.all(np.isfinite(step_dt))
        or np.any(step_dt <= 0.0)
        or np.any(np.diff(step_times) <= 0.0)
    ):
        return unavailable("solver step times and deltaT values must be finite and increasing")
    if end_time_limit_s is not None:
        if not math.isfinite(end_time_limit_s):
            return unavailable("analysis end-time limit is not finite")
        keep = inventory_times <= end_time_limit_s + 1e-12
        inventory_times, gas_raw, gas_bounded = (
            inventory_times[keep],
            gas_raw[keep],
            gas_bounded[keep],
        )
        if headspace_bounded is not None:
            headspace_bounded = headspace_bounded[keep]
        if len(inventory_times) < 2:
            return unavailable("fewer than two saved gas inventories remain inside the time limit")

    missing_mass = [patch for patch in OPEN_PATCHES if patch not in total_mass_flux_tables]
    missing_water = [patch for patch in OPEN_PATCHES if patch not in water_volume_flux_tables]
    if missing_mass or missing_water:
        return unavailable(
            "native gas mass flux requires rhoPhi and alphaPhi0.water on every open patch",
            missing_total_mass_flux_patches=missing_mass,
            missing_water_phase_flux_patches=missing_water,
        )

    ref_times: np.ndarray | None = None
    mass_values: dict[str, np.ndarray] = {}
    water_values: dict[str, np.ndarray] = {}
    flux_table_matching: dict[str, dict[str, Any]] = {}
    for patch in OPEN_PATCHES:
        mass_times, mass_flux = total_mass_flux_tables[patch]
        water_times, water_flux = water_volume_flux_tables[patch]
        mass_times = np.asarray(mass_times, dtype=float)
        mass_flux = np.asarray(mass_flux, dtype=float)
        water_times = np.asarray(water_times, dtype=float)
        water_flux = np.asarray(water_flux, dtype=float)
        if mass_times.shape != mass_flux.shape or water_times.shape != water_flux.shape:
            return unavailable(f"native mass/water flux row shape mismatch on {patch}")
        if len(mass_times) < 2 or len(water_times) < 2:
            return unavailable(f"native mass/water flux table has fewer than two rows on {patch}")
        if (
            not np.all(np.isfinite(mass_times))
            or not np.all(np.isfinite(water_times))
            or np.any(np.diff(mass_times) <= 0.0)
            or np.any(np.diff(water_times) <= 0.0)
        ):
            return unavailable(f"native mass/water flux times are invalid on {patch}")
        if not np.all(np.isfinite(mass_flux)) or not np.all(np.isfinite(water_flux)):
            return unavailable(f"native mass/water flux contains nonfinite values on {patch}")

        # Function objects can be added after startup, so rhoPhi may be a
        # suffix of the longer alphaPhi0.water log. Pair only matching times;
        # no values are interpolated or inferred for unmatched rows.
        mass_indices: list[int] = []
        water_indices: list[int] = []
        mass_index = water_index = 0
        while mass_index < len(mass_times) and water_index < len(water_times):
            mass_time = float(mass_times[mass_index])
            water_time = float(water_times[water_index])
            time_tolerance = max(1e-12, 1e-9 * max(abs(mass_time), abs(water_time), 1.0))
            difference = mass_time - water_time
            if abs(difference) <= time_tolerance:
                mass_indices.append(mass_index)
                water_indices.append(water_index)
                mass_index += 1
                water_index += 1
            elif difference < 0.0:
                mass_index += 1
            else:
                water_index += 1
        if len(mass_indices) < 2:
            return unavailable(f"fewer than two exact-time rhoPhi/alphaPhi0.water pairs on {patch}")
        matched_mass_times = mass_times[mass_indices]
        matched_water_times = water_times[water_indices]
        if not np.allclose(matched_mass_times, matched_water_times, rtol=1e-9, atol=1e-12):
            return unavailable(f"paired rhoPhi and alphaPhi0.water times drift on {patch}")
        if ref_times is None:
            ref_times = matched_mass_times
        elif ref_times.shape != matched_mass_times.shape or not np.allclose(
            ref_times, matched_mass_times, rtol=1e-9, atol=1e-12
        ):
            return unavailable(f"native open-patch flux sample times are not aligned on {patch}")
        mass_values[patch] = mass_flux[mass_indices]
        water_values[patch] = water_flux[water_indices]
        flux_table_matching[patch] = {
            "rhoPhi_logged_row_count": int(len(mass_times)),
            "alphaPhi0_water_logged_row_count": int(len(water_times)),
            "matched_time_row_count": int(len(mass_indices)),
            "unmatched_rhoPhi_row_count": int(len(mass_times) - len(mass_indices)),
            "unmatched_alphaPhi0_water_row_count": int(len(water_times) - len(water_indices)),
            "first_matched_time_s": float(matched_mass_times[0]),
            "last_matched_time_s": float(matched_mass_times[-1]),
        }
    assert ref_times is not None
    if np.any(np.diff(ref_times) <= 0.0):
        return unavailable("native open-patch flux times must be strictly increasing")

    if end_time_limit_s is not None:
        flux_keep = ref_times <= end_time_limit_s + 1e-12
        ref_times = ref_times[flux_keep]
        mass_values = {patch: values[flux_keep] for patch, values in mass_values.items()}
        water_values = {patch: values[flux_keep] for patch, values in water_values.items()}
        step_keep = step_times <= end_time_limit_s + 1e-12
        step_times, step_dt = step_times[step_keep], step_dt[step_keep]

    tolerance = 1e-11
    selected_start: int | None = None
    expected_step_mask: np.ndarray | None = None
    flux_step_mask: np.ndarray | None = None
    for candidate in range(len(inventory_times) - 1):
        start_time = inventory_times[candidate]
        end_time = inventory_times[-1]
        expected = (step_times > start_time + tolerance) & (step_times <= end_time + tolerance)
        observed = (ref_times > start_time + tolerance) & (ref_times <= end_time + tolerance)
        expected_times = step_times[expected]
        observed_times = ref_times[observed]
        if (
            len(expected_times)
            and expected_times.shape == observed_times.shape
            and np.allclose(expected_times, observed_times, rtol=1e-9, atol=1e-12)
        ):
            selected_start = candidate
            expected_step_mask = expected
            flux_step_mask = observed
            break
    if selected_start is None or expected_step_mask is None or flux_step_mask is None:
        return unavailable(
            "no saved-field reference time has complete rhoPhi/alphaPhi0 flux coverage through the final inventory",
            first_saved_inventory_time_s=float(inventory_times[0]),
            last_saved_inventory_time_s=float(inventory_times[-1]),
            first_logged_flux_time_s=float(ref_times[0]) if len(ref_times) else None,
            flux_table_matching=flux_table_matching,
            expected_solver_step_count=int(np.count_nonzero(step_times <= inventory_times[-1])),
            available_native_flux_step_count=int(len(ref_times)),
        )

    start_time = float(inventory_times[selected_start])
    selected_inventory_times = inventory_times[selected_start:]
    selected_raw = gas_raw[selected_start:]
    selected_bounded = gas_bounded[selected_start:]
    selected_headspace_bounded = (
        None if headspace_bounded is None else headspace_bounded[selected_start:]
    )
    flux_times = ref_times[flux_step_mask]
    used_step_times = step_times[expected_step_mask]
    used_step_dt = step_dt[expected_step_mask]
    if not np.allclose(flux_times, used_step_times, rtol=1e-9, atol=1e-12):
        return unavailable("native flux rows do not match solver step times without interpolation")

    for time_s, delta_t in zip(used_step_times, used_step_dt, strict=True):
        previous_candidates = step_times[step_times < time_s - tolerance]
        previous_time = float(previous_candidates[-1]) if len(previous_candidates) else start_time
        actual_interval = float(time_s) - previous_time
        interval_matches, rounding_bound_s = solver_delta_t_matches_serialized_interval(
            actual_interval,
            float(delta_t),
            previous_time,
            float(time_s),
            solver_time_format,
            solver_time_precision,
        )
        if not interval_matches:
            return unavailable(
                "solver log deltaT does not match adjacent right-endpoint times",
                time_s=float(time_s),
                logged_deltaT_s=float(delta_t),
                adjacent_time_interval_s=actual_interval,
                solver_time_format=solver_time_format,
                solver_time_precision=solver_time_precision,
                serialized_time_interval_rounding_bound_s=rounding_bound_s,
            )

    per_patch_mass_flux: dict[str, np.ndarray] = {}
    per_patch_water_flux: dict[str, np.ndarray] = {}
    per_patch_gas_flux: dict[str, np.ndarray] = {}
    for patch in OPEN_PATCHES:
        mass_flux = mass_values[patch][flux_step_mask]
        water_flux = water_values[patch][flux_step_mask]
        gas_flux = mass_flux - water_density_kg_m3 * water_flux
        per_patch_mass_flux[patch] = mass_flux
        per_patch_water_flux[patch] = water_flux
        per_patch_gas_flux[patch] = gas_flux
    total_gas_flux = np.sum(np.stack([per_patch_gas_flux[p] for p in OPEN_PATCHES]), axis=0)

    cumulative_by_patch = {patch: [0.0] for patch in OPEN_PATCHES}
    cumulative_total = [0.0]
    for left, right in zip(
        selected_inventory_times[:-1], selected_inventory_times[1:], strict=True
    ):
        interval = (used_step_times > left + tolerance) & (used_step_times <= right + tolerance)
        for patch in OPEN_PATCHES:
            increment = float(np.sum(per_patch_gas_flux[patch][interval] * used_step_dt[interval]))
            cumulative_by_patch[patch].append(cumulative_by_patch[patch][-1] + increment)
        increment_total = float(np.sum(total_gas_flux[interval] * used_step_dt[interval]))
        cumulative_total.append(cumulative_total[-1] + increment_total)

    cumulative = np.asarray(cumulative_total, dtype=float)
    residual_raw = selected_raw - selected_raw[0] + cumulative
    residual_bounded = selected_bounded - selected_bounded[0] + cumulative
    initial_raw_mass = float(selected_raw[0])
    initial_bounded_mass = float(selected_bounded[0])
    residual_raw_percent: list[float | None] = (
        (100.0 * residual_raw / initial_raw_mass).tolist()
        if initial_raw_mass > 0.0
        else [None] * len(residual_raw)
    )
    residual_bounded_percent: list[float | None] = (
        (100.0 * residual_bounded / initial_bounded_mass).tolist()
        if initial_bounded_mass > 0.0
        else [None] * len(residual_bounded)
    )
    initial_domain_raw_mass = float(gas_raw[0])
    initial_domain_bounded_mass = float(gas_bounded[0])
    residual_raw_initial_domain_percent: list[float | None] = (
        (100.0 * residual_raw / initial_domain_raw_mass).tolist()
        if initial_domain_raw_mass > 0.0
        else [None] * len(residual_raw)
    )
    residual_bounded_initial_domain_percent: list[float | None] = (
        (100.0 * residual_bounded / initial_domain_bounded_mass).tolist()
        if initial_domain_bounded_mass > 0.0
        else [None] * len(residual_bounded)
    )
    initial_headspace_mass = float(headspace_bounded[0]) if headspace_bounded is not None else None
    reference_headspace_mass = (
        float(selected_headspace_bounded[0]) if selected_headspace_bounded is not None else None
    )
    residual_raw_headspace_percent: list[float | None] = (
        (100.0 * residual_raw / initial_headspace_mass).tolist()
        if initial_headspace_mass is not None and initial_headspace_mass > 0.0
        else [None] * len(residual_raw)
    )
    residual_bounded_headspace_percent: list[float | None] = (
        (100.0 * residual_bounded / initial_headspace_mass).tolist()
        if initial_headspace_mass is not None and initial_headspace_mass > 0.0
        else [None] * len(residual_bounded)
    )
    return {
        "available": True,
        "conservative_ledger_available": True,
        "storage_quantity": "whole-domain EOS gas mass from native OpenFOAM V times gas fraction times p/(R*T); raw and clipped-alpha variants both reported",
        "outward_gas_mass_flux_formula": "rhoPhi_total - rho_water*alphaPhi0.water on each open boundary; outward positive",
        "water_density_kg_m3": float(water_density_kg_m3),
        "water_density_source": "constant rhoConst from thermophysicalProperties.water/config",
        "solver_time_format": solver_time_format,
        "solver_time_precision": solver_time_precision,
        "n_alpha_sub_cycles": n_alpha_sub_cycles,
        "ddt_scheme": ddt_scheme,
        "time_integration": "Euler right-endpoint sum Fgas_out(t_i)*deltaT_i from solver log; no flux time interpolation",
        "mass_water_flux_pairing": "paired by timestamp within 1e-9 relative/1e-12 s absolute tolerance; unmatched rows are retained in source function-object files and not interpolated",
        "reference_time_s": start_time,
        "first_saved_field_time_s": float(inventory_times[0]),
        "unledgered_pre_reference_duration_s": float(start_time - inventory_times[0]),
        "unledgered_pre_reference_gas_mass_change_kg_raw_alpha": float(
            gas_raw[selected_start] - gas_raw[0]
        ),
        "unledgered_pre_reference_gas_mass_change_kg_bounded_alpha": float(
            gas_bounded[selected_start] - gas_bounded[0]
        ),
        "time_s": selected_inventory_times.tolist(),
        "stored_domain_gas_mass_raw_alpha_kg": selected_raw.tolist(),
        "stored_domain_gas_mass_bounded_alpha_kg": selected_bounded.tolist(),
        "initial_domain_gas_mass_raw_alpha_kg": initial_domain_raw_mass,
        "initial_domain_gas_mass_bounded_alpha_kg": initial_domain_bounded_mass,
        "stored_tank_headspace_gas_mass_bounded_alpha_kg": (
            selected_headspace_bounded.tolist() if selected_headspace_bounded is not None else None
        ),
        "native_flux_step_time_s": used_step_times.tolist(),
        "native_flux_step_deltaT_s": used_step_dt.tolist(),
        "flux_table_matching": flux_table_matching,
        "per_patch_total_mass_flux_rhoPhi_kg_s": {
            patch: per_patch_mass_flux[patch].tolist() for patch in OPEN_PATCHES
        },
        "per_patch_water_phase_volume_flux_alphaPhi0_m3_s": {
            patch: per_patch_water_flux[patch].tolist() for patch in OPEN_PATCHES
        },
        "per_patch_outward_gas_mass_flux_kg_s": {
            patch: per_patch_gas_flux[patch].tolist() for patch in OPEN_PATCHES
        },
        "total_outward_gas_mass_flux_kg_s": total_gas_flux.tolist(),
        "cumulative_outward_gas_mass_by_patch_kg": {
            patch: values for patch, values in cumulative_by_patch.items()
        },
        "cumulative_outward_gas_mass_kg": cumulative.tolist(),
        "gas_mass_balance_residual_raw_alpha_kg": residual_raw.tolist(),
        "gas_mass_balance_residual_bounded_alpha_kg": residual_bounded.tolist(),
        "gas_mass_balance_residual_raw_alpha_percent_reference_raw_domain_gas_mass": residual_raw_percent,
        "gas_mass_balance_residual_bounded_alpha_percent_reference_domain_gas_mass": residual_bounded_percent,
        "gas_mass_balance_residual_raw_alpha_percent_initial_raw_domain_gas_mass": residual_raw_initial_domain_percent,
        "gas_mass_balance_residual_bounded_alpha_percent_initial_domain_gas_mass": residual_bounded_initial_domain_percent,
        "gas_mass_balance_residual_raw_alpha_percent_initial_tank_headspace_gas_mass": residual_raw_headspace_percent,
        "gas_mass_balance_residual_bounded_alpha_percent_initial_tank_headspace_gas_mass": residual_bounded_headspace_percent,
        "max_absolute_gas_mass_balance_residual_raw_alpha_kg": float(np.max(np.abs(residual_raw))),
        "max_absolute_gas_mass_balance_residual_bounded_alpha_kg": float(
            np.max(np.abs(residual_bounded))
        ),
        "initial_tank_headspace_gas_mass_bounded_alpha_kg": initial_headspace_mass,
        "reference_tank_headspace_gas_mass_bounded_alpha_kg": reference_headspace_mass,
        "final_domain_gas_mass_raw_alpha_kg": float(selected_raw[-1]),
        "final_domain_gas_mass_bounded_alpha_kg": float(selected_bounded[-1]),
        "cumulative_net_outward_gas_mass_kg": float(cumulative[-1]),
        "sample_time_interpolation_used": False,
        "flux_interval_coverage_complete_from_reference_time": True,
        "initial_domain_includes_tank_headspace_pipe_and_external_air": True,
        "limitation": "Storage is EOS-derived from native cell volumes and p/T, not an independent solver gas-phase mass field. Pre-reference gas exchange is excluded and explicitly reported.",
    }


def annotate_native_water_ledger_normalizations(
    ledger: dict[str, Any], tank_volume_table: tuple[np.ndarray, np.ndarray] | None
) -> None:
    """Add ledger residual fractions against initial water and tank drawdown."""
    if not ledger.get("available"):
        return
    times = np.asarray(ledger["time_s"], dtype=float)
    residual = np.asarray(ledger["water_volume_balance_residual_m3"], dtype=float)
    initial_total = float(ledger["initial_water_volume_m3"])
    residual_total_percent = (
        (100.0 * residual / initial_total).tolist()
        if initial_total > 0.0
        else [None] * len(residual)
    )
    ledger["balance_residual_fraction_initial_total_water_percent"] = residual_total_percent

    tank_values: list[float | None] = []
    for time_s in times:
        value, _ = exact_function_value(tank_volume_table, float(time_s))
        tank_values.append(value)
    reference_tank = tank_values[0] if tank_values else None
    tank_drawdown = [
        None if reference_tank is None or value is None else reference_tank - value
        for value in tank_values
    ]
    tank_residual_percent = [
        None if drawdown is None or drawdown <= 0.0 else 100.0 * float(error) / drawdown
        for error, drawdown in zip(residual, tank_drawdown, strict=True)
    ]
    ledger.update(
        {
            "normalization_reference": {
                "initial_total_water_volume_m3": initial_total,
                "tank_water_drawdown_reference": "native tankZone at the first ledger timestamp",
                "tank_table_match": "exact timestamp within 1e-10 s; no interpolation",
            },
            "native_tank_water_volume_m3": tank_values,
            "native_tank_drawdown_from_first_ledger_time_m3": tank_drawdown,
            "balance_residual_fraction_tank_drawdown_percent": tank_residual_percent,
            "max_abs_balance_residual_fraction_initial_total_water_percent": float(
                100.0 * np.max(np.abs(residual)) / initial_total
            )
            if initial_total > 0.0
            else None,
        }
    )


def annotate_gas_mass_normalization(rows: list[dict[str, Any]]) -> None:
    """Report tank ideal-air mass changes against the first saved field time."""
    masses = [
        float(row["headspace_air_mass_ideal_gas_bounded_alpha_kg"])
        for row in rows
        if row.get("headspace_air_mass_ideal_gas_bounded_alpha_kg") is not None
    ]
    reference = masses[0] if masses else None
    for row in rows:
        mass = row.get("headspace_air_mass_ideal_gas_bounded_alpha_kg")
        if reference is None or mass is None or reference == 0.0:
            row["headspace_air_mass_ideal_gas_delta_from_first_saved_kg"] = None
            row["headspace_air_mass_ideal_gas_change_percent_from_first_saved"] = None
        else:
            delta = float(mass) - reference
            row["headspace_air_mass_ideal_gas_delta_from_first_saved_kg"] = delta
            row["headspace_air_mass_ideal_gas_change_percent_from_first_saved"] = (
                100.0 * delta / reference
            )


def matched_checkpoint_normalizations(
    rows: list[dict[str, Any]], ledger: dict[str, Any]
) -> list[dict[str, float | None]]:
    """Collect only field times that exactly match solver-native ledger samples."""
    if not ledger.get("available"):
        return []
    residual_table = (
        np.asarray(ledger["time_s"], dtype=float),
        np.asarray(ledger["water_volume_balance_residual_m3"], dtype=float),
    )
    tank_values = ledger["native_tank_water_volume_m3"]
    tank_table = (
        (
            np.asarray(ledger["time_s"], dtype=float),
            np.asarray(tank_values, dtype=float),
        )
        if all(value is not None for value in tank_values)
        else None
    )
    initial_tank_values = [
        value for value in ledger["native_tank_water_volume_m3"] if value is not None
    ]
    initial_tank = float(initial_tank_values[0]) if initial_tank_values else None
    comparisons: list[dict[str, float | None]] = []
    for row in rows:
        time_s = float(row["time_s"])
        residual, _ = exact_function_value(residual_table, time_s)
        tank_value, _ = exact_function_value(tank_table, time_s)
        if residual is None or tank_value is None:
            continue
        drawdown = None if initial_tank is None else initial_tank - tank_value
        initial_total = float(ledger["initial_water_volume_m3"])
        gas_mass = row.get("headspace_air_mass_ideal_gas_bounded_alpha_kg")
        comparisons.append(
            {
                "time_s": time_s,
                "native_total_water_volume_m3": row.get("native_total_region_water_volume_m3"),
                "native_tank_water_volume_m3": float(tank_value),
                "tank_drawdown_from_first_ledger_time_m3": drawdown,
                "native_ledger_balance_residual_m3": float(residual),
                "residual_percent_of_initial_total_water": (
                    None if initial_total <= 0.0 else 100.0 * float(residual) / initial_total
                ),
                "residual_percent_of_tank_drawdown": (
                    None
                    if drawdown is None or drawdown <= 0.0
                    else 100.0 * float(residual) / drawdown
                ),
                "ideal_air_mass_kg": None if gas_mass is None else float(gas_mass),
                "ideal_air_mass_change_from_first_saved_percent": row.get(
                    "headspace_air_mass_ideal_gas_change_percent_from_first_saved"
                ),
            }
        )
    return comparisons


def _strip_openfoam_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def solver_time_controls(case_dir: Path) -> dict[str, Any]:
    """Read alpha subcycle count and ddt scheme, without assuming defaults."""
    result: dict[str, Any] = {
        "n_alpha_sub_cycles": None,
        "n_alpha_sub_cycles_source": None,
        "ddt_scheme": None,
        "ddt_scheme_source": None,
    }
    fv_solution = case_dir / "system/fvSolution"
    if fv_solution.is_file():
        clean = _strip_openfoam_comments(fv_solution.read_text(encoding="utf-8"))
        values = re.findall(r"\bnAlphaSubCycles\s+(\d+)\s*;", clean)
        unique_values = set(values)
        if len(unique_values) == 1:
            result["n_alpha_sub_cycles"] = int(values[0])
            result["n_alpha_sub_cycles_source"] = "system/fvSolution"
        elif not values:
            result["n_alpha_sub_cycles"] = 1
            result["n_alpha_sub_cycles_source"] = (
                "OpenFOAM default (no explicit nAlphaSubCycles entry)"
            )
    fv_schemes = case_dir / "system/fvSchemes"
    if fv_schemes.is_file():
        clean = _strip_openfoam_comments(fv_schemes.read_text(encoding="utf-8"))
        block_match = re.search(r"\bddtSchemes\s*\{([^}]*)\}", clean, flags=re.DOTALL)
        if block_match:
            block = block_match.group(1)
            explicit = re.search(r"\bddt\(alpha\.water\)\s+(\w+)\s*;", block)
            default = re.search(r"\bdefault\s+(\w+)\s*;", block)
            scheme_match = explicit or default
            if scheme_match:
                result["ddt_scheme"] = scheme_match.group(1)
                result["ddt_scheme_source"] = "system/fvSchemes"
    return result


def gas_thermo_properties(case_dir: Path, gas_kind: str) -> tuple[float, float | None, str | None]:
    """Return configured gas R and Cp-R from the OpenFOAM constant-Cp model."""
    gas_key = gas_kind.lower()
    gas_constant = R_AIR_J_KG_K if gas_key == "air" else R_CO2_J_KG_K
    path = case_dir / f"constant/thermophysicalProperties.{gas_key}"
    if not path.is_file():
        return gas_constant, None, None
    clean = _strip_openfoam_comments(path.read_text(encoding="utf-8"))
    match = re.search(
        r"\bthermodynamics\s*\{[^}]*?\bCp\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*;",
        clean,
        flags=re.DOTALL,
    )
    if match is None:
        return gas_constant, None, str(path)
    cp = float(match.group(1))
    cv = cp - gas_constant
    return gas_constant, cv if cv > 0 else None, str(path)


def mesh_topology_sha256(mesh: Any) -> str:
    """Hash VTK point coordinates and cell connectivity to validate V ordering."""
    digest = hashlib.sha256()
    digest.update(np.asarray([mesh.n_points, mesh.n_cells], dtype=np.int64).tobytes())
    for name in ("points", "cells", "celltypes"):
        if not hasattr(mesh, name):
            raise ValueError(f"cannot hash native cell-volume ordering: mesh lacks {name}")
        values = np.ascontiguousarray(np.asarray(getattr(mesh, name)))
        digest.update(name.encode("ascii"))
        digest.update(str(values.dtype).encode("ascii"))
        digest.update(values.tobytes())
    return digest.hexdigest()


def exact_function_value(
    table: tuple[np.ndarray, np.ndarray] | None, time_s: float, *, tolerance_s: float = 1e-10
) -> tuple[float | None, float | None]:
    """Return a function-object value only when its logged time matches exactly."""
    if table is None or len(table[0]) == 0:
        return None, None
    times, values = table
    index = int(np.argmin(np.abs(times - time_s)))
    offset = float(times[index] - time_s)
    if abs(offset) > tolerance_s:
        return None, offset
    return float(values[index]), offset


def annotate_native_volume_comparison(
    rows: list[dict[str, Any]],
    volume_tables: dict[str, tuple[np.ndarray, np.ndarray]],
) -> None:
    """Attach exact-time native region integrals and distinct VTK-mask deltas."""
    comparisons = (
        (
            "total",
            "total_water_volume_vtk_m3",
            "native_total_region_water_volume_m3",
            "total_cell_integral_minus_native_m3",
        ),
        (
            "tank",
            "tank_water_volume_vtk_m3",
            "native_tank_zone_water_volume_m3",
            "tank_geometric_cylinder_mask_minus_native_zone_m3",
        ),
        (
            "line",
            "line_water_volume_vtk_raw_alpha_m3",
            "native_line_zone_water_volume_m3",
            "line_geometric_mask_minus_native_zone_m3",
        ),
    )
    for row in rows:
        time_s = float(row["time_s"])
        for table_name, vtk_key, native_key, delta_key in comparisons:
            native_value, time_offset = exact_function_value(volume_tables.get(table_name), time_s)
            row[native_key] = native_value
            row[f"{native_key}_time_delta_s"] = time_offset
            row[delta_key] = (
                None
                if native_value is None or vtk_key not in row
                else float(row[vtk_key]) - native_value
            )


def annotate_native_mixture_gas_storage(
    rows: list[dict[str, Any]],
    total_mixture_mass_table: tuple[np.ndarray, np.ndarray] | None,
    total_water_volume_table: tuple[np.ndarray, np.ndarray] | None,
    water_density_kg_m3: float,
) -> dict[str, Any]:
    """Cross-check EOS gas storage against native mixture mass minus water mass.

    The independent fields are OpenFOAM ``volIntegrate(rho)`` over region0 and
    the native total water-volume function object. Exact timestamps are
    required; this diagnostic is not used to enable the boundary-flux ledger.
    """
    if not math.isfinite(water_density_kg_m3) or water_density_kg_m3 <= 0.0:
        raise ValueError("water density must be finite and positive")
    matched = 0
    residuals: list[float] = []
    for row in rows:
        time_s = float(row["time_s"])
        mixture_mass, mixture_offset = exact_function_value(total_mixture_mass_table, time_s)
        water_volume, water_offset = exact_function_value(total_water_volume_table, time_s)
        row["native_total_mixture_mass_kg"] = mixture_mass
        row["native_total_mixture_mass_time_delta_s"] = mixture_offset
        row["native_total_water_volume_for_gas_crosscheck_m3"] = water_volume
        row["native_total_water_volume_for_gas_crosscheck_time_delta_s"] = water_offset
        if mixture_mass is None or water_volume is None:
            row["native_gas_mass_from_mixture_minus_water_kg"] = None
            row["eos_minus_native_mixture_gas_mass_kg"] = None
            continue
        native_gas_mass = mixture_mass - water_density_kg_m3 * water_volume
        row["native_gas_mass_from_mixture_minus_water_kg"] = native_gas_mass
        eos_gas_mass = row.get("domain_gas_mass_ideal_gas_bounded_alpha_kg")
        residual = (
            None
            if eos_gas_mass is None or not math.isfinite(float(eos_gas_mass))
            else float(eos_gas_mass) - native_gas_mass
        )
        row["eos_minus_native_mixture_gas_mass_kg"] = residual
        if residual is not None:
            matched += 1
            residuals.append(residual)
    return {
        "available": bool(matched),
        "matched_field_time_count": matched,
        "max_absolute_eos_minus_native_mixture_gas_mass_kg": (
            max((abs(value) for value in residuals), default=None)
        ),
        "method": "native totalMixtureMass volIntegrate(rho) minus configured constant water density times native totalWaterVolume",
        "time_matching": "exact timestamp only; no interpolation",
        "qualification": "independent solver function-object mass/volume cross-check against reconstructed EOS storage; not a boundary-flux conservation ledger",
    }


def _scalar_array(dataset: Any, name: str, length: int) -> np.ndarray:
    if name not in dataset.cell_data:
        raise ValueError(f"OpenFOAMReader dataset lacks cell field {name!r}")
    values = np.asarray(dataset.cell_data[name], dtype=float)
    if values.shape != (length,):
        raise ValueError(f"field {name!r} has shape {values.shape}, expected ({length},)")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"field {name!r} contains nonfinite values")
    return values


def _vector_array(dataset: Any, name: str, length: int) -> np.ndarray:
    if name not in dataset.cell_data:
        raise ValueError(f"OpenFOAMReader dataset lacks cell field {name!r}")
    values = np.asarray(dataset.cell_data[name], dtype=float)
    if values.shape != (length, 3) or not np.all(np.isfinite(values)):
        raise ValueError(f"field {name!r} has invalid vector values or shape {values.shape}")
    return values


def _find_named_multiblock(dataset: Any, name: str) -> Any | None:
    for index in range(dataset.n_blocks):
        if dataset.get_block_name(index) == name:
            return dataset[index]
    return None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_profile_csv(path: Path, time_s: float, profile: dict[str, np.ndarray]) -> None:
    names = list(profile)
    n = len(profile[names[0]]) if names else 0
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["time_s", *names])
        writer.writeheader()
        for index in range(n):
            writer.writerow({"time_s": time_s, **{key: profile[key][index] for key in names}})


def _plot_poly_slice(ax: Any, cut: Any, axes: tuple[int, int], title: str, output: Path) -> bool:
    from matplotlib.collections import PolyCollection

    if cut.n_cells == 0 or "alpha.water" not in cut.cell_data:
        return False
    points = np.asarray(cut.points)
    faces = np.asarray(cut.faces, dtype=np.int64)
    polygons: list[np.ndarray] = []
    cursor = 0
    while cursor < len(faces):
        count = int(faces[cursor])
        indices = faces[cursor + 1 : cursor + 1 + count]
        polygons.append(points[indices][:, axes])
        cursor += count + 1
    alpha = np.clip(np.asarray(cut.cell_data["alpha.water"], dtype=float), 0.0, 1.0)
    collection = PolyCollection(polygons, array=alpha, cmap="Blues", edgecolors="none")
    collection.set_clim(0.0, 1.0)
    ax.add_collection(collection)
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.set_xlabel("x or y (m)")
    ax.set_ylabel("z (m)")
    return True


def _render_images(
    output_dir: Path,
    mesh: Any,
    time_s: float,
    nozzle_profile: dict[str, np.ndarray] | None,
    domain_exit_profile: dict[str, np.ndarray] | None,
    nozzle_plane_xyz_m: tuple[float, float, float],
) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    images: list[str] = []
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    mid = mesh.slice(normal=(0.0, 1.0, 0.0), origin=(0.0, 0.0, 0.0))
    lip = mesh.slice(normal=(1.0, 0.0, 0.0), origin=nozzle_plane_xyz_m)
    made = _plot_poly_slice(
        axes[0], mid, (0, 2), f"Mid-plane y=0, t={time_s:g} s; color=alpha.water", output_dir
    )
    made |= _plot_poly_slice(
        axes[1],
        lip,
        (1, 2),
        f"Nozzle lip x={nozzle_plane_xyz_m[0]:g} m, t={time_s:g} s; color=alpha.water",
        output_dir,
    )
    if made:
        sm = plt.cm.ScalarMappable(cmap="Blues", norm=plt.Normalize(0, 1))
        fig.colorbar(sm, ax=axes, label="Water volume fraction")
        path = output_dir / "field_sections.png"
        fig.savefig(path, dpi=160)
        images.append(path.name)
    plt.close(fig)

    for name, profile, title in (
        ("nozzle_internal_plane", nozzle_profile, "Nozzle internal plane"),
        ("domain_exit_patch", domain_exit_profile, "Far-domain exit patch"),
    ):
        if profile is None:
            continue
        fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
        scatter = axes[0].scatter(
            profile["y_m"],
            profile["z_m"],
            c=profile["alpha_water"],
            s=np.clip(profile["face_area_m2"] * 250.0, 2.0, 24.0),
            cmap="Blues",
            vmin=0.0,
            vmax=1.0,
        )
        axes[0].set_aspect("equal", adjustable="box")
        axes[0].set_xlabel("y (m)")
        axes[0].set_ylabel("z (m)")
        axes[0].set_title(f"{title}: alpha.water (t={time_s:g} s)")
        fig.colorbar(scatter, ax=axes[0], label="bounded alpha.water", shrink=0.82)
        scatter = axes[1].scatter(
            profile["y_m"],
            profile["z_m"],
            c=profile["normal_velocity_m_s"],
            s=np.clip(profile["face_area_m2"] * 250.0, 2.0, 24.0),
            cmap="coolwarm",
        )
        axes[1].set_aspect("equal", adjustable="box")
        axes[1].set_xlabel("y (m)")
        axes[1].set_ylabel("z (m)")
        axes[1].set_title(f"{title}: normal velocity")
        fig.colorbar(scatter, ax=axes[1], label="m/s (+x)", shrink=0.82)
        path = output_dir / f"{name}_profiles.png"
        fig.savefig(path, dpi=160)
        images.append(path.name)
        plt.close(fig)
    return images


def unique_output_dir(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("i4f-analysis-%Y%m%dT%H%M%S.%fZ")
    path = output_root / stamp
    path.mkdir(exist_ok=False)
    return path


def analyze_case(
    case_dir: Path,
    config_path: Path,
    output_root: Path,
    max_field_time_s: float | None = None,
) -> Path:
    import pyvista as pv

    case_dir = case_dir.resolve(strict=True)
    config_path = config_path.resolve(strict=True)
    foam_marker = next(iter(sorted(case_dir.glob("*.foam"))), None)
    if foam_marker is None:
        raise FileNotFoundError(
            f"case directory has no .foam marker for PyVista OpenFOAMReader: {case_dir}"
        )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    mouth_xyz = connection_mouth_xyz_m(config)
    section_stations = section_stations_for_config(config)
    metadata_path = case_dir.parent / "case-inputs.json"
    case_metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    )
    output_dir = unique_output_dir(output_root.resolve())

    reader = pv.OpenFOAMReader(str(foam_marker))
    reader.enable_all_patch_arrays()
    available_times = np.asarray(reader.time_values, dtype=float)
    if len(available_times) == 0 or not np.all(np.isfinite(available_times)):
        raise ValueError("OpenFOAMReader found no finite saved field times")
    if max_field_time_s is not None:
        if not math.isfinite(max_field_time_s):
            raise ValueError("maximum field time must be finite")
        times = available_times[available_times <= max_field_time_s + 1e-12]
        if len(times) == 0:
            raise ValueError(
                f"OpenFOAMReader has no saved fields at or before {max_field_time_s:g} s"
            )
    else:
        times = available_times

    time_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    outlet_rows: list[dict[str, Any]] = []
    negative_signed_volume_cell_count = 0
    centres: np.ndarray | None = None
    tank_mask: np.ndarray | None = None
    line_mask: np.ndarray | None = None
    internal_mesh_for_render = None
    last_nozzle_profile: dict[str, np.ndarray] | None = None
    last_domain_exit_profile: dict[str, np.ndarray] | None = None
    missing_fields: set[str] = set()

    gas_kind = config["gas"]["kind"].lower()
    gas_constant, gas_cv, gas_thermo_path = gas_thermo_properties(case_dir, gas_kind)
    native_volume_reference: np.ndarray | None = None
    native_volume_reference_time_s: float | None = None
    native_volume_reference_topology_sha256: str | None = None
    for reference_index in range(len(times) - 1, -1, -1):
        reader.set_active_time_point(reference_index)
        reference_multi = reader.read()
        reference_mesh = _find_named_multiblock(reference_multi, "internalMesh")
        if reference_mesh is not None and "V" in reference_mesh.cell_data:
            native_volume_reference = _scalar_array(reference_mesh, "V", reference_mesh.n_cells)
            if np.any(native_volume_reference <= 0.0):
                raise ValueError("OpenFOAM native V cell volumes must all be positive")
            native_volume_reference_time_s = float(times[reference_index])
            native_volume_reference_topology_sha256 = mesh_topology_sha256(reference_mesh)
            break

    native_volume_used_any = False
    topology_mismatch_times: list[float] = []
    for index, time_s in enumerate(times):
        reader.set_active_time_point(index)
        multi = reader.read()
        internal = _find_named_multiblock(multi, "internalMesh")
        if internal is None or internal.n_cells == 0:
            raise ValueError(f"time {time_s:g}: OpenFOAMReader has no internalMesh cells")
        if centres is None:
            centres = np.asarray(internal.cell_centers().points, dtype=float)
            signed_volumes = np.asarray(
                internal.compute_cell_sizes(length=False, area=False, volume=True).cell_data[
                    "Volume"
                ],
                dtype=float,
            )
            negative_signed_volume_cell_count = int(np.count_nonzero(signed_volumes < 0.0))
            tank_mask = tank_cell_mask(centres, config["tank"])
            line_mask = line_cell_mask(centres, config)
            if not np.any(tank_mask):
                raise ValueError(
                    "configured tank volume does not overlap any reconstructed mesh cells"
                )
            vtk_absolute_volumes = np.abs(signed_volumes)
        current_topology_sha256 = mesh_topology_sha256(internal)
        native_volumes: np.ndarray | None = None
        volume_source = "VTK absolute cell-size approximation; native OpenFOAM V unavailable"
        if "V" in internal.cell_data:
            current_native_volumes = _scalar_array(internal, "V", internal.n_cells)
            if np.any(current_native_volumes <= 0.0):
                raise ValueError(
                    f"time {time_s:g}: OpenFOAM native V cell volumes must be positive"
                )
            native_volumes = current_native_volumes
            native_volume_used_any = True
            volume_source = "OpenFOAM native V field at this time"
        elif (
            native_volume_reference is not None
            and current_topology_sha256 == native_volume_reference_topology_sha256
        ):
            native_volumes = native_volume_reference
            native_volume_used_any = True
            volume_source = (
                "OpenFOAM native V field cached from "
                f"t={native_volume_reference_time_s:g} s after matching topology hash"
            )
        elif native_volume_reference is not None:
            topology_mismatch_times.append(float(time_s))
        volumes = native_volumes if native_volumes is not None else vtk_absolute_volumes
        internal_mesh_for_render = internal
        n_cells = internal.n_cells
        try:
            alpha = _scalar_array(internal, "alpha.water", n_cells)
            pressure = _scalar_array(internal, "p", n_cells)
            temperature = _scalar_array(internal, "T", n_cells)
            _vector_array(internal, "U", n_cells)
        except ValueError as error:
            missing_fields.add(str(error))
            raise
        metrics = inventory_metrics(
            alpha_water=alpha,
            cell_volumes_m3=volumes,
            pressure_abs_Pa=pressure,
            temperature_K=temperature,
            centres_xyz_m=centres,
            tank_mask=tank_mask,
            line_mask=line_mask,
            water_density_kg_m3=float(config["liquid"]["density_kg_m3"]),
            gas_constant_J_kg_K=gas_constant,
            gas_cv_J_kg_K=gas_cv,
        )
        time_rows.append(
            {
                "time_s": float(time_s),
                "cell_volume_source": volume_source,
                "native_volume_weighted_integrals_available": native_volumes is not None,
                "mesh_cell_order_topology_sha256": current_topology_sha256,
                **metrics,
            }
        )
        for name, x_m in section_stations:
            cut = internal.slice(
                normal=(1.0, 0.0, 0.0), origin=(x_m, float(mouth_xyz[1]), float(mouth_xyz[2]))
            )
            if cut.n_cells == 0:
                section_rows.append(
                    {
                        "time_s": float(time_s),
                        "section": name,
                        "station_x_m": x_m,
                        "cut_cell_count": 0,
                    }
                )
                continue
            cut = cut.compute_cell_sizes(length=False, area=True, volume=False)
            cut_area = np.asarray(cut.cell_data["Area"], dtype=float)
            section_rows.append(
                {
                    "time_s": float(time_s),
                    "section": name,
                    **section_profile_metrics(
                        x_m=x_m,
                        cell_areas_m2=cut_area,
                        alpha_water=np.asarray(cut.cell_data["alpha.water"], dtype=float),
                        pressure_abs_Pa=np.asarray(cut.cell_data["p"], dtype=float),
                        temperature_K=np.asarray(cut.cell_data["T"], dtype=float),
                        velocity_xyz_m_s=np.asarray(cut.cell_data["U"], dtype=float),
                    ),
                }
            )
            nominal_area = nominal_section_area_m2(x_m, config)
            if nominal_area is not None:
                section_rows[-1]["nominal_geometry_area_m2"] = nominal_area
                section_rows[-1]["relative_mesh_cut_area_error"] = (
                    float(cut_area.sum()) - nominal_area
                ) / nominal_area

        # The nozzle metric is an internal cut immediately upstream of the lip.
        # The OpenFOAM `outlet` patch is the far-domain boundary and is measured
        # separately below.
        nozzle_station_x_m = next(x for name, x in section_stations if name == "nozzle_lip")
        nozzle_cut = internal.slice(
            normal=(1.0, 0.0, 0.0),
            origin=(nozzle_station_x_m, float(mouth_xyz[1]), float(mouth_xyz[2])),
        )
        if nozzle_cut.n_cells:
            nozzle_cut = nozzle_cut.compute_cell_sizes(length=False, area=True, volume=False)
            nozzle_summary, last_nozzle_profile = outlet_face_metrics(
                centres_xyz_m=np.asarray(nozzle_cut.cell_centers().points, dtype=float),
                face_areas_m2=np.asarray(nozzle_cut.cell_data["Area"], dtype=float),
                alpha_water=np.asarray(nozzle_cut.cell_data["alpha.water"], dtype=float),
                velocity_xyz_m_s=np.asarray(nozzle_cut.cell_data["U"], dtype=float),
                pressure_abs_Pa=np.asarray(nozzle_cut.cell_data["p"], dtype=float),
                temperature_K=np.asarray(nozzle_cut.cell_data["T"], dtype=float),
                normal_xyz=np.asarray(config["nozzle"].get("direction", [1, 0, 0]), dtype=float),
                water_density_kg_m3=float(config["liquid"]["density_kg_m3"]),
                metric_prefix="nozzle_internal",
            )
            nozzle_summary["nozzle_internal_station_x_m"] = nozzle_station_x_m
            nozzle_summary["nozzle_internal_metric_kind"] = (
                "PyVista internalMesh cut interpolation and cut-cell areas; approximate"
            )
            time_rows[-1].update(nozzle_summary)
            profile_path = output_dir / f"nozzle_internal_t{float(time_s):.8g}.csv"
            _write_profile_csv(profile_path, float(time_s), last_nozzle_profile)
            outlet_rows.append(
                {
                    "time_s": float(time_s),
                    "profile_type": "nozzle_internal_plane",
                    "profile_file": profile_path.name,
                    **nozzle_summary,
                }
            )
        else:
            time_rows[-1]["nozzle_internal_plane_available"] = 0.0

        boundary = _find_named_multiblock(multi, "boundary")
        outlet = _find_named_multiblock(boundary, "outlet") if boundary is not None else None
        if outlet is None or outlet.n_cells == 0:
            time_rows[-1]["outlet_patch_available"] = 0.0
            continue
        if not all(name in outlet.cell_data for name in ("alpha.water", "p", "T", "U")):
            time_rows[-1]["outlet_patch_available"] = 0.0
            missing_fields.add("outlet patch lacks alpha.water/p/T/U face arrays")
            continue
        outlet_centres = np.asarray(outlet.cell_centers().points, dtype=float)
        outlet_area = np.asarray(
            outlet.compute_cell_sizes(length=False, area=True, volume=False).cell_data["Area"],
            dtype=float,
        )
        outlet_summary, last_domain_exit_profile = outlet_face_metrics(
            centres_xyz_m=outlet_centres,
            face_areas_m2=outlet_area,
            alpha_water=np.asarray(outlet.cell_data["alpha.water"], dtype=float),
            velocity_xyz_m_s=np.asarray(outlet.cell_data["U"], dtype=float),
            pressure_abs_Pa=np.asarray(outlet.cell_data["p"], dtype=float),
            temperature_K=np.asarray(outlet.cell_data["T"], dtype=float),
            normal_xyz=np.asarray(config["nozzle"].get("direction", [1, 0, 0]), dtype=float),
            water_density_kg_m3=float(config["liquid"]["density_kg_m3"]),
            gas_constant_J_kg_K=gas_constant,
            metric_prefix="domain_exit",
        )
        time_rows[-1].update(outlet_summary)
        time_rows[-1]["domain_exit_profile_metric_kind"] = (
            "PyVista outlet patch at the far external boundary; approximate"
        )
        profile_path = output_dir / f"domain_exit_faces_t{float(time_s):.8g}.csv"
        _write_profile_csv(profile_path, float(time_s), last_domain_exit_profile)
        outlet_rows.append(
            {
                "time_s": float(time_s),
                "profile_type": "far_domain_exit_patch",
                "profile_file": profile_path.name,
                **outlet_summary,
            }
        )

    # Solver function-object logs are the preferred conservative volume/flux records.
    volume_tables: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for label, object_names in (
        ("tank", ("tankWaterVolume",)),
        ("line", ("lineWaterVolume",)),
        ("total", ("totalWaterVolume",)),
    ):
        path = find_function_table(case_dir, object_names, "volFieldValue.dat")
        if path is not None:
            volume_tables[label] = parse_scalar_table(path)
    total_mixture_mass_path = find_function_table(
        case_dir, ("totalMixtureMass",), "volFieldValue.dat"
    )
    total_mixture_mass_table = (
        parse_scalar_table(total_mixture_mass_path) if total_mixture_mass_path is not None else None
    )
    annotate_native_volume_comparison(time_rows, volume_tables)
    annotate_gas_mass_normalization(time_rows)
    native_mixture_gas_storage_crosscheck = annotate_native_mixture_gas_storage(
        time_rows,
        total_mixture_mass_table,
        volume_tables.get("total"),
        float(config["liquid"]["density_kg_m3"]),
    )
    flux_names = {
        "ambientAnnulus": (
            "ambientAnnulusWaterPhaseVolumeFlux",
            "ambientAnnulusWaterFlux",
            "ambientAnnulusLiquidFlux",
        ),
        "externalSides": (
            "externalSidesWaterPhaseVolumeFlux",
            "externalSidesWaterFlux",
            "externalSidesLiquidFlux",
        ),
        "outlet": (
            "outletWaterPhaseVolumeFlux",
            "outletWaterFlux",
            "outletLiquidVolumeFlux",
        ),
    }
    flux_tables: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    flux_files: dict[str, str] = {}
    for patch, names in flux_names.items():
        path = find_function_table(case_dir, names, "surfaceFieldValue.dat")
        if path is not None:
            flux_tables[patch] = parse_scalar_table(path)
            flux_files[patch] = str(path.relative_to(case_dir))
    total_water_function = volume_tables.get("total", (np.empty(0), np.empty(0)))
    time_controls = solver_time_controls(case_dir)
    step_log = solver_step_table(case_dir)
    if len(total_water_function[0]) < 2:
        ledger = {
            "available": False,
            "reason": "solver-native total-water volume inventory is missing or has fewer than two rows; reconstructed VTK inventory is not used for conservation",
        }
    else:
        ledger = native_flux_ledger(
            volume_times_s=total_water_function[0],
            stored_water_volume_m3=total_water_function[1],
            flux_tables=flux_tables,
            n_alpha_sub_cycles=time_controls["n_alpha_sub_cycles"],
            ddt_scheme=time_controls["ddt_scheme"],
            solver_step_times_s=step_log.get("time_s"),
            solver_delta_t_s=step_log.get("deltaT_s"),
            solver_time_format=step_log.get("time_format"),
            solver_time_precision=step_log.get("time_precision"),
            end_time_limit_s=float(times[-1]),
        )
    if not flux_tables:
        ledger = {
            "available": False,
            "reason": "no solver-native all-open-boundary water phase flux logs were found; VTK flux is not used for conservation",
        }
    annotate_native_water_ledger_normalizations(ledger, volume_tables.get("tank"))
    if flux_tables and not ledger.get("available"):
        diagnostic_rows: list[dict[str, Any]] = []
        for patch in OPEN_PATCHES:
            if patch not in flux_tables:
                continue
            flux_times, flux_values = flux_tables[patch]
            diagnostic_rows.extend(
                {
                    "time_s": float(time_s),
                    "patch": patch,
                    "logged_alphaPhi0_water_m3_s": float(value),
                    "conservative_full_step_flux": False,
                }
                for time_s, value in zip(flux_times, flux_values, strict=True)
            )
        _write_csv(output_dir / "native_water_flux_samples_diagnostic.csv", diagnostic_rows)

    total_mass_flux_names = {
        "ambientAnnulus": ("ambientAnnulusTotalMassFlux", "ambientAnnulusMixtureMassFlux"),
        "externalSides": ("externalSidesTotalMassFlux", "externalSidesMixtureMassFlux"),
        "outlet": ("outletTotalMassFlux", "outletMixtureMassFlux"),
    }
    total_mass_flux_tables: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    total_mass_flux_files: dict[str, str] = {}
    for patch, names in total_mass_flux_names.items():
        path = find_function_table(case_dir, names, "surfaceFieldValue.dat")
        if path is not None:
            total_mass_flux_tables[patch] = parse_scalar_table(path)
            total_mass_flux_files[patch] = str(path.relative_to(case_dir))

    native_inventory_available = bool(time_rows) and all(
        row.get("native_volume_weighted_integrals_available") is True for row in time_rows
    )
    valid_gas_eos_inventory = bool(time_rows) and all(
        row.get("domain_gas_ideal_eos_invalid_pressure_or_temperature_cell_count") == 0.0
        for row in time_rows
    )
    if not native_inventory_available:
        gas_ledger: dict[str, Any] = {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "whole-domain EOS gas storage requires native OpenFOAM V at every analyzed field time",
        }
    elif not valid_gas_eos_inventory:
        gas_ledger = {
            "available": False,
            "conservative_ledger_available": False,
            "reason": "whole-domain EOS gas storage contains cells with invalid or nonpositive pressure/temperature",
        }
    elif not step_log.get("available"):
        gas_ledger = {
            "available": False,
            "conservative_ledger_available": False,
            "reason": step_log.get("reason", "solver timestep log is unavailable"),
        }
    else:
        gas_ledger = native_gas_mass_ledger(
            inventory_times_s=np.asarray([row["time_s"] for row in time_rows], dtype=float),
            stored_gas_mass_raw_kg=np.asarray(
                [row["domain_gas_mass_ideal_gas_raw_alpha_kg"] for row in time_rows],
                dtype=float,
            ),
            stored_gas_mass_bounded_kg=np.asarray(
                [row["domain_gas_mass_ideal_gas_bounded_alpha_kg"] for row in time_rows],
                dtype=float,
            ),
            stored_headspace_gas_mass_bounded_kg=np.asarray(
                [row["headspace_air_mass_ideal_gas_bounded_alpha_kg"] for row in time_rows],
                dtype=float,
            ),
            total_mass_flux_tables=total_mass_flux_tables,
            water_volume_flux_tables=flux_tables,
            solver_step_times_s=step_log["time_s"],
            solver_delta_t_s=step_log["deltaT_s"],
            water_density_kg_m3=float(config["liquid"]["density_kg_m3"]),
            solver_time_format=step_log.get("time_format"),
            solver_time_precision=step_log.get("time_precision"),
            n_alpha_sub_cycles=time_controls["n_alpha_sub_cycles"],
            ddt_scheme=time_controls["ddt_scheme"],
            end_time_limit_s=float(times[-1]),
        )
    gas_ledger["native_cell_volume_storage_available"] = native_inventory_available
    gas_ledger["valid_whole_domain_eos_storage_available"] = valid_gas_eos_inventory
    gas_ledger["solver_log"] = step_log.get("solver_log")
    gas_ledger["solver_step_count"] = step_log.get("parsed_row_count")
    if gas_ledger.get("available"):
        gas_ledger["thermodynamic_gas_constant_J_kg_K"] = gas_constant
        gas_ledger["thermodynamic_gas_cv_J_kg_K"] = gas_cv
        gas_ledger["thermophysical_properties_file"] = gas_thermo_path
    if (
        total_mass_flux_tables
        and flux_tables
        and time_controls["n_alpha_sub_cycles"] == 1
        and time_controls["ddt_scheme"] == "Euler"
    ):
        diagnostic_rows = []
        for patch in OPEN_PATCHES:
            if patch not in total_mass_flux_tables or patch not in flux_tables:
                continue
            mass_times, mass_values = total_mass_flux_tables[patch]
            water_times, water_values = flux_tables[patch]
            if mass_times.shape != water_times.shape or not np.allclose(
                mass_times, water_times, rtol=1e-9, atol=1e-12
            ):
                continue
            diagnostic_rows.extend(
                {
                    "time_s": float(time_s),
                    "patch": patch,
                    "rhoPhi_total_kg_s": float(mass_flux),
                    "alphaPhi0_water_m3_s": float(water_flux),
                    "derived_gas_mass_flux_kg_s": float(
                        mass_flux - float(config["liquid"]["density_kg_m3"]) * water_flux
                    ),
                    "integrated_for_closure": bool(gas_ledger.get("available")),
                }
                for time_s, mass_flux, water_flux in zip(
                    mass_times, mass_values, water_values, strict=True
                )
            )
        if diagnostic_rows and not gas_ledger.get("available"):
            _write_csv(output_dir / "native_gas_mass_flux_samples_diagnostic.csv", diagnostic_rows)

    _write_csv(output_dir / "inventory_pressure_history.csv", time_rows)
    _write_csv(output_dir / "section_profiles_approx.csv", section_rows)
    _write_csv(output_dir / "outlet_summary_approx.csv", outlet_rows)
    if ledger.get("available"):
        _write_csv(
            output_dir / "water_boundary_flux_ledger.csv",
            [
                {
                    "time_s": ledger["time_s"][index],
                    "flux_ambientAnnulus_m3_s": ledger["per_patch_outward_water_volume_flux_m3_s"][
                        "ambientAnnulus"
                    ][index],
                    "flux_externalSides_m3_s": ledger["per_patch_outward_water_volume_flux_m3_s"][
                        "externalSides"
                    ][index],
                    "flux_outlet_m3_s": ledger["per_patch_outward_water_volume_flux_m3_s"][
                        "outlet"
                    ][index],
                    "cumulative_out_m3": ledger["cumulative_outward_water_volume_m3"][index],
                    "stored_water_m3": ledger["stored_total_water_volume_m3"][index],
                    "balance_residual_m3": ledger["water_volume_balance_residual_m3"][index],
                    "balance_residual_percent_initial_total_water": ledger[
                        "balance_residual_fraction_initial_total_water_percent"
                    ][index],
                    "native_tank_water_volume_m3": ledger["native_tank_water_volume_m3"][index],
                    "tank_drawdown_from_first_ledger_time_m3": ledger[
                        "native_tank_drawdown_from_first_ledger_time_m3"
                    ][index],
                    "balance_residual_percent_tank_drawdown": ledger[
                        "balance_residual_fraction_tank_drawdown_percent"
                    ][index],
                }
                for index in range(len(ledger["time_s"]))
            ],
        )
    if gas_ledger.get("available"):
        gas_times = gas_ledger["time_s"]
        cumulative_by_patch = gas_ledger["cumulative_outward_gas_mass_by_patch_kg"]
        _write_csv(
            output_dir / "gas_mass_balance_ledger.csv",
            [
                {
                    "time_s": gas_times[index],
                    "stored_domain_gas_mass_raw_alpha_kg": gas_ledger[
                        "stored_domain_gas_mass_raw_alpha_kg"
                    ][index],
                    "stored_domain_gas_mass_bounded_alpha_kg": gas_ledger[
                        "stored_domain_gas_mass_bounded_alpha_kg"
                    ][index],
                    "stored_tank_headspace_gas_mass_bounded_alpha_kg": gas_ledger[
                        "stored_tank_headspace_gas_mass_bounded_alpha_kg"
                    ][index],
                    "cumulative_outward_gas_mass_ambientAnnulus_kg": cumulative_by_patch[
                        "ambientAnnulus"
                    ][index],
                    "cumulative_outward_gas_mass_externalSides_kg": cumulative_by_patch[
                        "externalSides"
                    ][index],
                    "cumulative_outward_gas_mass_outlet_kg": cumulative_by_patch["outlet"][index],
                    "cumulative_outward_gas_mass_kg": gas_ledger["cumulative_outward_gas_mass_kg"][
                        index
                    ],
                    "gas_mass_balance_residual_raw_alpha_kg": gas_ledger[
                        "gas_mass_balance_residual_raw_alpha_kg"
                    ][index],
                    "gas_mass_balance_residual_bounded_alpha_kg": gas_ledger[
                        "gas_mass_balance_residual_bounded_alpha_kg"
                    ][index],
                    "gas_mass_balance_residual_raw_alpha_percent_reference_mass": gas_ledger[
                        "gas_mass_balance_residual_raw_alpha_percent_reference_raw_domain_gas_mass"
                    ][index],
                    "gas_mass_balance_residual_bounded_alpha_percent_reference_mass": gas_ledger[
                        "gas_mass_balance_residual_bounded_alpha_percent_reference_domain_gas_mass"
                    ][index],
                    "gas_mass_balance_residual_raw_alpha_percent_initial_domain_mass": gas_ledger[
                        "gas_mass_balance_residual_raw_alpha_percent_initial_raw_domain_gas_mass"
                    ][index],
                    "gas_mass_balance_residual_bounded_alpha_percent_initial_domain_mass": gas_ledger[
                        "gas_mass_balance_residual_bounded_alpha_percent_initial_domain_gas_mass"
                    ][index],
                    "gas_mass_balance_residual_raw_alpha_percent_initial_headspace_mass": gas_ledger[
                        "gas_mass_balance_residual_raw_alpha_percent_initial_tank_headspace_gas_mass"
                    ][index],
                    "gas_mass_balance_residual_bounded_alpha_percent_initial_headspace_mass": gas_ledger[
                        "gas_mass_balance_residual_bounded_alpha_percent_initial_tank_headspace_gas_mass"
                    ][index],
                }
                for index in range(len(gas_times))
            ],
        )
        step_times = gas_ledger["native_flux_step_time_s"]
        step_dts = gas_ledger["native_flux_step_deltaT_s"]
        patch_gas_flux = gas_ledger["per_patch_outward_gas_mass_flux_kg_s"]
        patch_mass_flux = gas_ledger["per_patch_total_mass_flux_rhoPhi_kg_s"]
        patch_water_flux = gas_ledger["per_patch_water_phase_volume_flux_alphaPhi0_m3_s"]
        step_rows: list[dict[str, Any]] = []
        cumulative = 0.0
        for index, (time_s, delta_t) in enumerate(zip(step_times, step_dts, strict=True)):
            row: dict[str, Any] = {
                "time_s": time_s,
                "deltaT_s": delta_t,
                "integrated_net_outward_gas_mass_kg": sum(
                    patch_gas_flux[patch][index] for patch in OPEN_PATCHES
                )
                * delta_t,
            }
            for patch in OPEN_PATCHES:
                row[f"{patch}_rhoPhi_total_kg_s"] = patch_mass_flux[patch][index]
                row[f"{patch}_alphaPhi0_water_m3_s"] = patch_water_flux[patch][index]
                row[f"{patch}_derived_gas_mass_flux_kg_s"] = patch_gas_flux[patch][index]
            cumulative += float(row["integrated_net_outward_gas_mass_kg"])
            row["cumulative_outward_gas_mass_from_reference_kg"] = cumulative
            step_rows.append(row)
        _write_csv(output_dir / "native_gas_mass_flux_samples.csv", step_rows)

    images = _render_images(
        output_dir,
        internal_mesh_for_render,
        float(times[-1]),
        last_nozzle_profile,
        last_domain_exit_profile,
        (float(nozzle_station_x_m), float(mouth_xyz[1]), float(mouth_xyz[2])),
    )
    case_input_hash = sha256_file(metadata_path) if metadata_path.is_file() else None
    status = (
        "runtime fields analyzed"
        if len(times) > 1
        else "one saved field time; runtime discharge history pending"
    )
    if all(float(row["total_water_volume_vtk_m3"]) <= 1e-12 for row in time_rows):
        status = "no water present in saved fields; case initialization/run required"
    summary = {
        "schema": OUTPUT_SCHEMA,
        "status": status,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "case_dir": str(case_dir),
        "openfoam_marker": str(foam_marker),
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "case_inputs_path": str(metadata_path) if metadata_path.is_file() else None,
        "case_inputs_sha256": case_input_hash,
        "analyzer_sha256": sha256_file(Path(__file__).resolve()),
        "git_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()
        or None,
        "pyvista_version": pv.__version__,
        "vtk_reader": "PyVista OpenFOAMReader; native binary OpenFOAM fields reconstructed to VTK cell/patch fields",
        "field_times_s": times.tolist(),
        "field_time_limit_s": max_field_time_s,
        "saved_field_count": int(len(times)),
        "internal_mesh_cell_count": int(internal_mesh_for_render.n_cells),
        "vtk_negative_signed_cell_volume_count": negative_signed_volume_cell_count,
        "native_cell_volume_reference": {
            "field": "OpenFOAM V",
            "available": native_volume_reference is not None,
            "reference_time_s": native_volume_reference_time_s,
            "topology_sha256": native_volume_reference_topology_sha256,
            "cell_count": (
                int(len(native_volume_reference)) if native_volume_reference is not None else None
            ),
            "sum_m3": (
                float(np.sum(native_volume_reference))
                if native_volume_reference is not None
                else None
            ),
            "min_m3": (
                float(np.min(native_volume_reference))
                if native_volume_reference is not None
                else None
            ),
            "max_m3": (
                float(np.max(native_volume_reference))
                if native_volume_reference is not None
                else None
            ),
            "topology_mismatch_times_s": topology_mismatch_times,
            "native_volume_used_any": native_volume_used_any,
        },
        "open_boundary_patches_expected": list(OPEN_PATCHES),
        "outlet_normal_xyz": config["nozzle"].get("direction", [1, 0, 0]),
        "pressure_field": "p (absolute pressure expected for compressibleInterFoam; verify solver setup)",
        "inventory_kind": "cell volume times raw alpha.water; OpenFOAM V is the preferred quantitative cell-volume source, with explicitly flagged absolute-VTK-volume fallback only when V is absent",
        "native_volume_region_comparison": {
            "time_matching": "exact timestamp match only; no interpolation",
            "native_regions": "solver volFieldValue cell zones tankZone and lineZone, plus all-region totalWaterVolume",
            "vtk_regions": "tank cylinder center mask using explicit center_xyz_m when supplied; line center mask follows the +x pipe/transition envelope and includes the vertical tank curved port stub outside tank cells; neither is mislabeled as a solver cellZone",
            "line_mask_mouth_center_xyz_m": mouth_xyz.tolist(),
            "line_mask_excludes_tank_mask_for_vertical_stub": bool(
                np.allclose(
                    np.asarray(config["tank"].get("axis_vector", [1.0, 0.0, 0.0]), dtype=float)
                    / np.linalg.norm(
                        np.asarray(config["tank"].get("axis_vector", [1.0, 0.0, 0.0]), dtype=float)
                    ),
                    [0.0, 0.0, 1.0],
                    rtol=0.0,
                    atol=1e-12,
                )
                and "center_xyz_m" in config["tank"]
            ),
            "vertical_line_mask_rule": "for a +z tank and +x port, include the circular yz pipe stub from x=cx+sqrt(R^2-(|mouth_y-cy|+rp)^2) to the explicit mouth, excluding the tank-cylinder center mask; union the downstream mouth-to-exit line envelope",
        },
        "ideal_gas_phase_inventory": {
            "method": "sum(alpha-air bounded to [0,1]*V*p/(R*T)) over every cell in the geometric tank mask; no alpha threshold and no mixture rho field",
            "sensible_internal_energy": "sum(m_cell*Cv*T) over the same gas-weighted cells",
            "gas_R_J_kg_K": gas_constant,
            "gas_Cp_J_kg_K": (gas_constant + gas_cv) if gas_cv is not None else None,
            "gas_Cv_J_kg_K": gas_cv,
            "thermophysical_properties_file": gas_thermo_path,
            "qualification": "derived from reconstructed fields and V; not an independent solver mass or energy balance",
            "mass_normalization": "tank ideal-air mass change is also reported relative to the first saved field time",
        },
        "section_flux_kind": "interpolated cross-section integral alpha.water*U dot n dA; local diagnostic only, not conservative",
        "outlet_angle_and_momentum_definitions": {
            "outlet_water_flux_weighted_angle_deg": "Forward-water-flux-weighted mean of each sampled face's local departure angle from +normal; opposite lateral directions do not cancel, so this is not net jet deflection.",
            "outlet_net_forward_water_momentum_angle_deg": "Angle of the forward-only water momentum-flux vector, sum(rho_water*alpha_water*max(U_n,0)*A*U), relative to +normal; opposite lateral momenta cancel. Undefined when forward water flux is zero.",
            "outlet_water_momentum_flux_xyz_profile_approx_N": "Legacy integrated convective momentum transport is sum(rho*alpha*U_n*A*U) with signed normal velocity; reverse flow can add to the normal component. Forward-only momentum components are reported separately.",
        },
        "nozzle_internal_plane": {
            "station_x_m": nozzle_station_x_m,
            "plane_origin_xyz_m": [nozzle_station_x_m, float(mouth_xyz[1]), float(mouth_xyz[2])],
            "kind": "internalMesh slice interpolation; local nozzle velocity, wetting, angle and momentum estimates; not native flux",
        },
        "domain_exit_patch": {
            "patch_name": "outlet",
            "kind": "far-domain boundary patch face values; separate from the nozzle internal plane",
        },
        "outlet_profile_kind": "nozzle quality metrics use alpha.water*area weights; wet-area threshold metrics are separately labelled; all profiles are approximate and not native conservative fluxes",
        "section_stations": [{"name": name, "x_m": float(x)} for name, x in section_stations],
        "section_station_semantics": {
            "pipe_upstream_and_post_valve": "pressure taps at valve x minus/plus the configured pressure_tap_offset_m; default 0.2 m, required to remain inside straight pipe",
            "pipe_end": "legacy near-pipe-end pressure tap, not the pipe/transition boundary; configured pipe_end_upstream_offset_m default 0.1 m",
            "pipe_transition_boundary_x_m": float(mouth_xyz[0]) + float(config["pipe"]["length_m"]),
            "pipe_end_station_offset_upstream_m": float(mouth_xyz[0])
            + float(config["pipe"]["length_m"])
            - dict(section_stations)["pipe_end"],
            "transition_mid": "midpoint of the configured transition length",
            "nozzle_lip": "0.01 m (or configured inset) upstream of the transition exit",
            "external_mid": "configured default 1.0 m downstream of the nozzle exit",
        },
        "alpha_inventory_semantics": "raw VTK alpha.water is used for raw water inventories and overshoots are reported; bounded [0,1] phase-weighted diagnostics are separately named",
        "solver_function_object_volumes": {
            label: {
                "file": str(
                    find_function_table(case_dir, names, "volFieldValue.dat").relative_to(case_dir)
                ),
                "sample_count": int(len(volume_tables[label][0])),
                "time_s": volume_tables[label][0].tolist(),
                "value_m3": volume_tables[label][1].tolist(),
            }
            for label, names in (
                ("tank", ("tankWaterVolume",)),
                ("line", ("lineWaterVolume",)),
                ("total", ("totalWaterVolume",)),
            )
            if label in volume_tables
        },
        "solver_function_object_masses": (
            {
                "total_mixture_mass": {
                    "file": str(total_mixture_mass_path.relative_to(case_dir)),
                    "sample_count": int(len(total_mixture_mass_table[0])),
                    "time_s": total_mixture_mass_table[0].tolist(),
                    "value_kg": total_mixture_mass_table[1].tolist(),
                }
                if total_mixture_mass_path is not None and total_mixture_mass_table is not None
                else None
            }
        ),
        "native_mixture_gas_storage_crosscheck": native_mixture_gas_storage_crosscheck,
        "native_water_flux_files": flux_files,
        "native_total_mass_flux_files": total_mass_flux_files,
        "solver_step_log": {
            "available": bool(step_log.get("available")),
            "solver_log": step_log.get("solver_log"),
            "parsed_step_count": step_log.get("parsed_row_count"),
            "time_format": step_log.get("time_format"),
            "time_precision": step_log.get("time_precision"),
            "reason": step_log.get("reason"),
        },
        "solver_time_controls": time_controls,
        "native_water_flux_semantics": {
            "field": "alphaPhi0.water",
            "operation": "signed surfaceFieldValue sum",
            "units": "m^3/s",
            "sign": "boundary-outward positive",
            "source": "OpenCFD compressibleInterFoam v2512 alphaPhi0.water; full-step only for nAlphaSubCycles=1, otherwise the registered field is the last alpha subcycle",
            "integration": "Euler right-endpoint Q(t_i)*logged solver deltaT_i only when nAlphaSubCycles=1 and native phase-flux rows cover every solver endpoint after the first exact inventory/flux reference",
            "deltaT_time_consistency": "adjacent printed Time intervals must agree with logged deltaT under the existing relative/absolute tolerance or the half-quantum bound derived from explicit timeFormat/timePrecision",
        },
        "native_water_volume_ledger": ledger,
        "native_domain_gas_mass_flux_semantics": {
            "total_mass_field": "rhoPhi",
            "water_phase_volume_field": "alphaPhi0.water",
            "formula": "outward gas mass flux = rhoPhi - rho_water*alphaPhi0.water on each open boundary",
            "water_density_kg_m3": float(config["liquid"]["density_kg_m3"]),
            "water_density_assumption": "constant configured liquid density; requires phase mass flux represented by rhoPhi and full-step phase-volume flux",
            "sign": "boundary-outward positive",
            "integration": "Euler right-endpoint sum Fgas_out(t_i)*deltaT_i from paired solver Time/deltaT rows, only after a saved-field reference with complete per-step open-boundary logs",
            "validity_gate": "one alpha subcycle and Euler ddt; with multiple alpha subcycles alphaPhi0.water is only the last subcycle",
            "storage": "whole computational domain including tank gas, line gas, and external air; native OpenFOAM V times gas fraction times p/(R*T)",
            "storage_variants": "raw alpha.water and alpha.water clipped to [0,1] are both reported; EOS invalid p/T cells are separately counted",
            "residual_normalizations": "absolute kg plus percent of initial whole-domain gas mass and initial bounded tank/headspace gas mass are reported to expose external-air denominator dilution",
            "independent_conservation_status": "EOS-derived gas storage is compared with solver boundary flux; this is not an independent solver gas-mass field",
        },
        "native_domain_gas_mass_ledger": gas_ledger,
        "matched_checkpoint_normalizations": matched_checkpoint_normalizations(time_rows, ledger),
        "warnings": [
            "mesh-cut field profiles do not use native face flux and must not be used to close water conservation",
            "a global water ledger requires Euler stepping, one alpha subcycle, finite exact-time inventory/flux data on every open boundary, and native flux coverage at every solver endpoint after its explicit reference time",
            "tankZone and lineZone native volume logs are distinct from the analyzer's geometric center masks; exact-time deltas are reported separately",
            "ideal gas mass and Cv*T energy use all bounded alpha-air fractions, p/(R*T), and cell weights; these are diagnostics, not independent conservation proofs",
            "whole-domain gas storage uses native OpenFOAM V and reconstructed p/T with raw and clipped alpha; its boundary-flux residual is an EOS-versus-flux consistency check, not an independent solver gas-phase inventory",
            "the gas mass ledger is withheld if any analyzed cell has invalid or nonpositive p/T rather than silently omitting that gas inventory",
            "gas boundary mass flux is derived as rhoPhi minus configured constant water density times alphaPhi0.water; closure is disabled unless Euler stepping, one alpha subcycle, paired logs, and complete per-step coverage are available",
            "the gas ledger may start after startup when logging began late; pre-reference gas exchange is excluded and its duration and storage change are recorded",
            "OpenFOAM V cell volumes are required for quantitative volume-weighted field integrals; when absent, absolute-VTK-volume sums are approximate and marked",
            "VTK geometric signed cell volumes can be negative on concave cells; the negative count is reported and absolute VTK volumes are not treated as validated physical volumes",
            "all CFD inputs remain provisional and exploratory; no hardware validation is implied",
        ]
        + sorted(missing_fields),
        "images": images,
        "outputs": [
            "inventory_pressure_history.csv",
            "section_profiles_approx.csv",
            "outlet_summary_approx.csv",
            *(
                ["native_water_flux_samples_diagnostic.csv"]
                if flux_tables and not ledger.get("available")
                else []
            ),
            *(["water_boundary_flux_ledger.csv"] if ledger.get("available") else []),
            *(
                ["native_gas_mass_flux_samples_diagnostic.csv"]
                if total_mass_flux_tables and flux_tables and not gas_ledger.get("available")
                else []
            ),
            *(
                ["gas_mass_balance_ledger.csv", "native_gas_mass_flux_samples.csv"]
                if gas_ledger.get("available")
                else []
            ),
        ],
        "case_metadata": case_metadata,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    readme = [
        "I4F complete-apparatus field analysis",
        f"Status: {status}",
        f"Case: {case_dir}",
        f"Saved field times: {times[0]:g} to {times[-1]:g} s ({len(times)} fields)",
        f"Global water ledger: {'available' if ledger.get('available') else ledger.get('reason')}",
        f"Whole-domain gas ledger: {'available' if gas_ledger.get('available') else gas_ledger.get('reason')}",
        "Section and outlet profile flux/momentum values are reconstructed field estimates; use only native phase flux for conservation.",
        "",
        "Images: " + (", ".join(images) if images else "not generated"),
    ]
    (output_dir / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"Wrote I4F field analysis bundle: {output_dir}")
    print(f"Status: {status}")
    print(
        f"Saved field times: {len(times)}; water ledger: {ledger.get('available', False)}; "
        f"gas ledger: {gas_ledger.get('available', False)}"
    )
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir",
        type=Path,
        required=True,
        help="read-only OpenFOAM case directory containing a .foam marker",
    )
    parser.add_argument("--config", type=Path, default=ROOT / "experiments/i4f_baseline.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument(
        "--max-field-time",
        type=float,
        help="analyze the saved-field prefix up to this time (also limits the native ledger)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analyze_case(args.case_dir, args.config, args.output_root, max_field_time_s=args.max_field_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
