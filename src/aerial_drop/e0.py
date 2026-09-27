"""Small, analytical E0 checks for aerial-drop mass and ground-map scoring.

Coordinates use SI units in a fixed, inertial ground frame: x is along-track,
y is cross-track, and z is upward. Arrays are indexed ``[x_cell, y_cell]``.
The trajectory helper assumes constant aircraft velocity, constant gravity,
no wind-relative drag, and outlet axes aligned with the ground axes.

The deposition helper is a conservative weighted histogram. Each impact
contributes its full mass to one finite-volume cell; a ground impact outside
the map is retained as outside-map ground mass. This is a diagnostic
accumulation, not a droplet or plume transport model.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import resource
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


def _finite_scalar(name: str, value: float, *, positive: bool = False) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _vector3(name: str, value: ArrayLike) -> FloatArray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite length-3 vector")
    return result


def _frozen_array(name: str, value: ArrayLike, ndim: int = 1) -> FloatArray:
    result = np.array(value, dtype=np.float64, copy=True)
    if result.ndim != ndim or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite {ndim}-D array")
    result.setflags(write=False)
    return result


def _edges(name: str, value: ArrayLike) -> FloatArray:
    result = _frozen_array(name, value)
    if result.size < 2 or np.any(np.diff(result) <= 0.0):
        raise ValueError(f"{name} must contain at least two strictly increasing edges")
    return result


def release_mass(
    density_kg_m3: float,
    outlet_area_m2: float,
    velocity_m_s: ArrayLike,
    unit_normal: ArrayLike,
    duration_s: float,
) -> float:
    """Return constant-inlet mass flux integrated over time.

    Only ``abs(velocity dot unit_normal)`` contributes to flow through the
    outlet. Tangential components do not alter the released mass.
    """
    density = _finite_scalar("density_kg_m3", density_kg_m3, positive=True)
    area = _finite_scalar("outlet_area_m2", outlet_area_m2, positive=True)
    duration = _finite_scalar("duration_s", duration_s, positive=True)
    velocity = _vector3("velocity_m_s", velocity_m_s)
    normal = _vector3("unit_normal", unit_normal)
    normal_length = float(np.linalg.norm(normal))
    if normal_length == 0.0:
        raise ValueError("unit_normal must have nonzero length")
    normal = normal / normal_length
    return density * area * abs(float(np.dot(velocity, normal))) * duration


def aircraft_to_ground_position(
    position_aircraft_m: ArrayLike,
    time_s: float,
    aircraft_position_at_zero_m: ArrayLike,
    aircraft_velocity_m_s: ArrayLike,
) -> tuple[float, float, float]:
    """Map an aircraft-relative point to inertial ground coordinates at time t."""
    time = _finite_scalar("time_s", time_s)
    position = _vector3("position_aircraft_m", position_aircraft_m)
    origin = _vector3("aircraft_position_at_zero_m", aircraft_position_at_zero_m)
    velocity = _vector3("aircraft_velocity_m_s", aircraft_velocity_m_s)
    mapped = origin + velocity * time + position
    return tuple(float(component) for component in mapped)


@dataclass(frozen=True)
class BallisticImpact:
    """Impact state; ``position_m`` is in the inertial ground frame."""

    flight_time_s: float
    impact_time_s: float
    position_m: tuple[float, float, float]


def ballistic_impact(
    release_position_aircraft_m: ArrayLike,
    release_velocity_aircraft_m_s: ArrayLike,
    release_time_s: float,
    aircraft_position_at_zero_m: ArrayLike,
    aircraft_velocity_m_s: ArrayLike,
    gravity_m_s2: ArrayLike = (0.0, 0.0, -9.81),
    ground_z_m: float = 0.0,
) -> BallisticImpact:
    """Compute the first descending ground-plane impact under constant gravity.

    The release location is mapped from aircraft to ground coordinates at the
    absolute release time. Particle velocity in the ground frame is aircraft
    velocity plus outlet-relative velocity. The returned impact time is also
    absolute, so moving-aircraft mapping is not reset at release.
    """
    release_time = _finite_scalar("release_time_s", release_time_s)
    ground_z = _finite_scalar("ground_z_m", ground_z_m)
    release_position = _vector3("release_position_aircraft_m", release_position_aircraft_m)
    relative_velocity = _vector3("release_velocity_aircraft_m_s", release_velocity_aircraft_m_s)
    aircraft_velocity = _vector3("aircraft_velocity_m_s", aircraft_velocity_m_s)
    gravity = _vector3("gravity_m_s2", gravity_m_s2)
    aircraft_origin = _vector3("aircraft_position_at_zero_m", aircraft_position_at_zero_m)
    initial = aircraft_origin + aircraft_velocity * release_time + release_position
    initial_height = float(initial[2] - ground_z)
    if initial_height < 0.0:
        raise ValueError("release point must be on or above the ground plane")

    vertical_velocity = float(aircraft_velocity[2] + relative_velocity[2])
    vertical_acceleration = float(gravity[2])
    if vertical_acceleration == 0.0:
        if vertical_velocity >= 0.0:
            raise ValueError("trajectory does not descend to the ground plane")
        flight_time = -initial_height / vertical_velocity
    else:
        discriminant = vertical_velocity**2 - 2.0 * vertical_acceleration * initial_height
        if discriminant < 0.0:
            raise ValueError("trajectory does not reach the ground plane")
        root = math.sqrt(discriminant)
        quadratic_a = 0.5 * vertical_acceleration
        q = -0.5 * (vertical_velocity + math.copysign(root, vertical_velocity))
        candidates = (0.0,) if q == 0.0 else (q / quadratic_a, initial_height / q)
        descending = [
            candidate
            for candidate in candidates
            if candidate >= 0.0
            and vertical_velocity + vertical_acceleration * candidate <= 0.0
            and math.isfinite(candidate)
        ]
        if not descending:
            raise ValueError("trajectory has no nonnegative ground impact time")
        flight_time = min(descending)

    absolute_velocity = aircraft_velocity + relative_velocity
    impact = initial + absolute_velocity * flight_time + 0.5 * gravity * flight_time**2
    impact[2] = ground_z
    return BallisticImpact(
        flight_time_s=float(flight_time),
        impact_time_s=float(release_time + flight_time),
        position_m=tuple(float(component) for component in impact),
    )


@dataclass(frozen=True)
class GroundMap:
    """Cell-average deposited mass per area on a rectangular, nonuniform grid.

    ``concentration_kg_m2[i, j]`` is cell ``i`` along x and cell ``j`` along y.
    Edges and concentration are copied and made read-only at construction.
    """

    x_edges_m: FloatArray
    y_edges_m: FloatArray
    concentration_kg_m2: FloatArray

    def __post_init__(self) -> None:
        x_edges = _edges("x_edges_m", self.x_edges_m)
        y_edges = _edges("y_edges_m", self.y_edges_m)
        concentration = _frozen_array("concentration_kg_m2", self.concentration_kg_m2, ndim=2)
        expected_shape = (x_edges.size - 1, y_edges.size - 1)
        if concentration.shape != expected_shape:
            raise ValueError(f"concentration_kg_m2 shape must be {expected_shape}")
        if np.any(concentration < 0.0):
            raise ValueError("concentration_kg_m2 must be nonnegative")
        object.__setattr__(self, "x_edges_m", x_edges)
        object.__setattr__(self, "y_edges_m", y_edges)
        object.__setattr__(self, "concentration_kg_m2", concentration)

    @property
    def cell_areas_m2(self) -> FloatArray:
        areas = np.diff(self.x_edges_m)[:, None] * np.diff(self.y_edges_m)[None, :]
        areas.setflags(write=False)
        return areas

    @property
    def mass_inside_map_kg(self) -> float:
        return float(np.sum(self.concentration_kg_m2 * self.cell_areas_m2))


@dataclass(frozen=True)
class DepositionResult:
    """Ground landings inside the map and beyond its outer edges."""

    ground_map: GroundMap
    outside_map_mass_kg: float
    impact_locations_xy_m: FloatArray
    impact_masses_kg: FloatArray

    @property
    def in_map_mass_kg(self) -> float:
        return self.ground_map.mass_inside_map_kg

    @property
    def deposited_mass_kg(self) -> float:
        """All ground impacts, including landings outside the map extent."""
        return self.in_map_mass_kg + self.outside_map_mass_kg


def _cell_index(coordinate: float, edges: FloatArray) -> int | None:
    """Return a half-open-bin index; include the final outer edge in the last bin."""
    if coordinate < edges[0] or coordinate > edges[-1]:
        return None
    if coordinate == edges[-1]:
        return edges.size - 2
    return int(np.searchsorted(edges, coordinate, side="right") - 1)


def deposit_impacts(
    x_edges_m: ArrayLike,
    y_edges_m: ArrayLike,
    impact_xy_m: ArrayLike,
    impact_mass_kg: ArrayLike,
) -> DepositionResult:
    """Accumulate weighted point impacts into a nonuniform finite-volume map.

    Bins are half-open on their upper edges, except the final x/y bins include
    the map's last outer edge. Each in-map impact contributes to exactly one
    cell; impacts beyond any edge count as landed ground mass outside the map,
    never as mass that escaped the domain. Thus in-map plus outside-map mass
    equals input impact mass to floating-point precision.
    """
    x_edges = _edges("x_edges_m", x_edges_m)
    y_edges = _edges("y_edges_m", y_edges_m)
    points = np.asarray(impact_xy_m, dtype=np.float64)
    masses = np.asarray(impact_mass_kg, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or not np.all(np.isfinite(points)):
        raise ValueError("impact_xy_m must be a finite array with shape (n, 2)")
    if masses.shape != (points.shape[0],) or not np.all(np.isfinite(masses)):
        raise ValueError("impact_mass_kg must be a finite length-n array")
    if np.any(masses < 0.0):
        raise ValueError("impact_mass_kg must be nonnegative")

    deposited_cells = np.zeros((x_edges.size - 1, y_edges.size - 1), dtype=np.float64)
    outside_map = 0.0
    for (x, y), mass in zip(points, masses, strict=True):
        i = _cell_index(float(x), x_edges)
        j = _cell_index(float(y), y_edges)
        if i is None or j is None:
            outside_map += float(mass)
            continue
        deposited_cells[i, j] += float(mass)

    areas = np.diff(x_edges)[:, None] * np.diff(y_edges)[None, :]
    ground_map = GroundMap(x_edges, y_edges, deposited_cells / areas)
    in_map_mass = ground_map.mass_inside_map_kg
    input_mass = float(np.sum(masses))
    if not math.isclose(in_map_mass + outside_map, input_mass, rel_tol=1e-12, abs_tol=1e-12):
        raise ArithmeticError("weighted deposition failed mass conservation")
    return DepositionResult(
        ground_map,
        outside_map,
        _frozen_array("impact_xy_m", points, ndim=2),
        _frozen_array("impact_mass_kg", masses),
    )


@dataclass(frozen=True)
class MassLedger:
    """Mutually exclusive released-mass compartments, all in kilograms."""

    released_kg: float
    deposited_kg: float
    airborne_vof_kg: float
    airborne_parcels_kg: float
    escaped_kg: float
    evaporated_kg: float

    def __post_init__(self) -> None:
        names = (
            "released_kg",
            "deposited_kg",
            "airborne_vof_kg",
            "airborne_parcels_kg",
            "escaped_kg",
            "evaporated_kg",
        )
        values = tuple(_finite_scalar(name, getattr(self, name)) for name in names)
        if any(value < 0.0 for value in values):
            raise ValueError("mass ledger compartments must be nonnegative")
        if not math.isclose(values[0], sum(values[1:]), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError(
                "released mass must equal deposited + airborne VOF + airborne parcels "
                "+ escaped + evaporated"
            )

    @property
    def airborne_kg(self) -> float:
        return self.airborne_vof_kg + self.airborne_parcels_kg

    @property
    def residual_kg(self) -> float:
        return self.released_kg - (
            self.deposited_kg
            + self.airborne_vof_kg
            + self.airborne_parcels_kg
            + self.escaped_kg
            + self.evaporated_kg
        )


@dataclass(frozen=True)
class MomentumCheck:
    """VOF-to-parcel momentum balance diagnostic in kg m/s."""

    residual_kg_m_s: tuple[float, float, float]
    residual_norm_kg_m_s: float
    tolerance_kg_m_s: float
    conserved: bool


def check_momentum_conservation(
    incoming_kg_m_s: ArrayLike,
    outgoing_vof_kg_m_s: ArrayLike,
    outgoing_parcels_kg_m_s: ArrayLike,
    *,
    absolute_tolerance_kg_m_s: float = 1e-12,
    relative_tolerance: float = 1e-10,
) -> MomentumCheck:
    """Compare incoming momentum with the sum of two represented handoff phases."""
    incoming = _vector3("incoming_kg_m_s", incoming_kg_m_s)
    vof = _vector3("outgoing_vof_kg_m_s", outgoing_vof_kg_m_s)
    parcels = _vector3("outgoing_parcels_kg_m_s", outgoing_parcels_kg_m_s)
    absolute_tolerance = _finite_scalar("absolute_tolerance_kg_m_s", absolute_tolerance_kg_m_s)
    relative_tolerance = _finite_scalar("relative_tolerance", relative_tolerance)
    if absolute_tolerance < 0.0 or relative_tolerance < 0.0:
        raise ValueError("momentum tolerances must be nonnegative")
    residual = incoming - vof - parcels
    residual_norm = float(np.linalg.norm(residual))
    tolerance = absolute_tolerance + relative_tolerance * float(np.linalg.norm(incoming))
    return MomentumCheck(
        residual_kg_m_s=tuple(float(value) for value in residual),
        residual_norm_kg_m_s=residual_norm,
        tolerance_kg_m_s=tolerance,
        conserved=residual_norm <= tolerance,
    )


@dataclass(frozen=True)
class ScoreResult:
    """Continuous-strip metrics for the centered target width."""

    l95_m: float
    strip_x_start_m: float | None
    strip_x_stop_m: float | None
    strip_start_index: int | None
    strip_stop_index: int | None
    useful_fraction: float
    useful_credit_mass_kg: float
    actual_mass_inside_strip_kg: float
    mass_elsewhere_on_ground_kg: float
    released_mass_kg: float
    target_width_m: float
    coverage_threshold_kg_m2: float
    coverage_fraction: float


@dataclass(frozen=True)
class EllipseRectangleCheck:
    """Area-preserving rectangle versus an ellipse's full-width chord length."""

    ellipse_area_m2: float
    target_width_m: float
    full_width_ellipse_length_m: float
    same_area_rectangle_length_m: float
    rectangle_to_ellipse_length_ratio: float | None


def ellipse_rectangle_check(
    semi_major_axis_m: float,
    semi_minor_axis_m: float,
    target_width_m: float,
) -> EllipseRectangleCheck:
    """Compare ellipse chord length and same-area rectangle length.

    This geometric illustration follows Restás (2023), *Examining the
    Effectiveness of Aerial Firefighting*, pp. 10–12 / Table 1: the paper uses
    approximately a=25 m, b=7 m, and W=9 m. Its full-width ellipse interval is
    about 38.3 m and its equal-area rectangle is about 61.1 m (roughly 1.6x).
    This is a 100%-width geometric comparison, not the map-based 95% L95 metric.
    """
    semi_major = _finite_scalar("semi_major_axis_m", semi_major_axis_m, positive=True)
    semi_minor = _finite_scalar("semi_minor_axis_m", semi_minor_axis_m, positive=True)
    width = _finite_scalar("target_width_m", target_width_m, positive=True)
    if width > 2.0 * semi_minor:
        raise ValueError("target_width_m cannot exceed the ellipse's minor-axis diameter")
    ellipse_area = math.pi * semi_major * semi_minor
    half_width_ratio = width / (2.0 * semi_minor)
    full_width_length = 2.0 * semi_major * math.sqrt(1.0 - half_width_ratio**2)
    rectangle_length = ellipse_area / width
    ratio = None if full_width_length == 0.0 else rectangle_length / full_width_length
    return EllipseRectangleCheck(
        ellipse_area_m2=ellipse_area,
        target_width_m=width,
        full_width_ellipse_length_m=full_width_length,
        same_area_rectangle_length_m=rectangle_length,
        rectangle_to_ellipse_length_ratio=ratio,
    )


def score_ground_map(
    ground_map: GroundMap,
    released_mass_kg: float,
    target_width_m: float,
    coverage_threshold_kg_m2: float,
    *,
    coverage_fraction: float = 0.95,
    outside_map_mass_kg: float = 0.0,
) -> ScoreResult:
    """Compute L95 and threshold-capped useful fraction from a cell-average map.

    The target is centered on y=0. Partial y-cell overlap is integrated by
    overlap width. Each x cell is one constant section; adjacent valid cells
    form a continuous strip. Equal-length runs select the earliest x interval.
    A 1e-12 relative/scale tolerance handles roundoff at the coverage boundary.
    Useful credit is ``C*`` times qualifying area inside the selected strip;
    actual deposited mass is reported separately and includes excess dose.
    """
    released = _finite_scalar("released_mass_kg", released_mass_kg, positive=True)
    width = _finite_scalar("target_width_m", target_width_m, positive=True)
    threshold = _finite_scalar("coverage_threshold_kg_m2", coverage_threshold_kg_m2, positive=True)
    minimum_fraction = _finite_scalar("coverage_fraction", coverage_fraction, positive=True)
    outside_map = _finite_scalar("outside_map_mass_kg", outside_map_mass_kg)
    if outside_map < 0.0:
        raise ValueError("outside_map_mass_kg must be nonnegative")
    if minimum_fraction > 1.0:
        raise ValueError("coverage_fraction must be at most 1")
    known_ground_mass = ground_map.mass_inside_map_kg + outside_map
    mass_tolerance = 1e-12 * max(1.0, released)
    if known_ground_mass > released + mass_tolerance:
        raise ValueError("known ground mass cannot exceed released_mass_kg")

    y_lower, y_upper = -0.5 * width, 0.5 * width
    y_overlap = np.maximum(
        0.0,
        np.minimum(ground_map.y_edges_m[1:], y_upper)
        - np.maximum(ground_map.y_edges_m[:-1], y_lower),
    )
    if float(np.sum(y_overlap)) < width - 1e-12 * max(1.0, width):
        raise ValueError("ground-map y edges must cover the full centered target width")

    above_threshold = ground_map.concentration_kg_m2 >= threshold
    covered_width = above_threshold @ y_overlap
    minimum_width = minimum_fraction * width
    width_tolerance = 1e-12 * max(1.0, width)
    valid_sections = covered_width >= minimum_width - width_tolerance

    best_start: int | None = None
    best_stop: int | None = None
    best_length = 0.0
    cursor = 0
    x_edges = ground_map.x_edges_m
    while cursor < valid_sections.size:
        if not valid_sections[cursor]:
            cursor += 1
            continue
        start = cursor
        while cursor < valid_sections.size and valid_sections[cursor]:
            cursor += 1
        stop = cursor
        length = float(x_edges[stop] - x_edges[start])
        tie_tolerance = 1e-12 * max(1.0, abs(best_length), abs(length))
        if best_start is None or length > best_length + tie_tolerance:
            best_start, best_stop, best_length = start, stop, length

    if best_start is None or best_stop is None:
        strip_start_m = strip_stop_m = None
        useful_credit = actual_inside = 0.0
        elsewhere = known_ground_mass
        useful_fraction = 0.0
    else:
        strip_start_m = float(x_edges[best_start])
        strip_stop_m = float(x_edges[best_stop])
        x_widths = np.diff(x_edges)[best_start:best_stop]
        selected_concentration = ground_map.concentration_kg_m2[best_start:best_stop]
        selected_mask = above_threshold[best_start:best_stop]
        target_area_by_cell = x_widths[:, None] * y_overlap[None, :]
        qualifying_area = float(np.sum(target_area_by_cell * selected_mask))
        useful_credit = threshold * qualifying_area
        actual_inside = float(np.sum(target_area_by_cell * selected_concentration))
        elsewhere = max(0.0, known_ground_mass - actual_inside)
        useful_fraction = useful_credit / released

    return ScoreResult(
        l95_m=best_length,
        strip_x_start_m=strip_start_m,
        strip_x_stop_m=strip_stop_m,
        strip_start_index=best_start,
        strip_stop_index=best_stop,
        useful_fraction=useful_fraction,
        useful_credit_mass_kg=useful_credit,
        actual_mass_inside_strip_kg=actual_inside,
        mass_elsewhere_on_ground_kg=elsewhere,
        released_mass_kg=released,
        target_width_m=width,
        coverage_threshold_kg_m2=threshold,
        coverage_fraction=minimum_fraction,
    )


def improvement_gain(restas_l95_m: float, control_l95_m: float) -> float | None:
    """Return the L95 ratio, or ``None`` when the control has zero valid length."""
    restas = _finite_scalar("restas_l95_m", restas_l95_m)
    control = _finite_scalar("control_l95_m", control_l95_m)
    if restas < 0.0 or control < 0.0:
        raise ValueError("L95 values must be nonnegative")
    return None if control == 0.0 else restas / control


def _scoring_fixture() -> GroundMap:
    """A declared synthetic map for exercising partial edges, gaps, and ties."""
    x_edges = np.array([0.0, 2.0, 5.0, 7.0, 10.0, 12.0])
    y_edges = np.array([-2.0, -1.375, -1.125, -0.8, 0.8, 1.125, 1.375, 2.0])
    concentration = np.zeros((x_edges.size - 1, y_edges.size - 1))
    for i in (0, 1, 3, 4):
        concentration[i, 2:6] = 3.0
        concentration[i, (0, 6)] = 10.0  # deposited outside the target width
    return GroundMap(x_edges, y_edges, concentration)


def _git_metadata(repository_root: Path) -> tuple[str | None, bool | None]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return revision, bool(status.strip())


def _code_hashes(repository_root: Path) -> dict[str, str]:
    candidates = sorted((repository_root / "src" / "aerial_drop").glob("*.py"))
    candidates.extend(
        repository_root / relative
        for relative in (
            "tests/test_e0.py",
            "experiments/E0.md",
            "pyproject.toml",
            "uv.lock",
        )
        if (repository_root / relative).is_file()
    )
    hashes: dict[str, str] = {}
    for path in candidates:
        relative = path.relative_to(repository_root).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _run_checks() -> tuple[dict[str, object], GroundMap, DepositionResult]:
    density, area, duration = 1000.0, 0.12, 2.0
    normal_velocity = (5.0, 0.0, 0.0)
    tangential_velocity = (5.0, -12.0, 3.0)
    normal = (1.0, 0.0, 0.0)
    mass_a = release_mass(density, area, normal_velocity, normal, duration)
    mass_b = release_mass(density, area, tangential_velocity, normal, duration)

    ballistic = ballistic_impact(
        release_position_aircraft_m=(0.0, 0.0, 0.0),
        release_velocity_aircraft_m_s=(0.0, 0.0, 0.0),
        release_time_s=4.0,
        aircraft_position_at_zero_m=(0.0, 0.0, 100.0),
        aircraft_velocity_m_s=(10.0, 2.0, 0.0),
        gravity_m_s2=(0.0, 0.0, -10.0),
        ground_z_m=0.0,
    )
    expected_flight = math.sqrt(20.0)
    expected_impact_time = 4.0 + expected_flight
    expected_impact_position = (10.0 * expected_impact_time, 2.0 * expected_impact_time, 0.0)

    deposition = deposit_impacts(
        x_edges_m=(0.0, 1.0, 3.0),
        y_edges_m=(-1.0, 1.0, 3.0),
        impact_xy_m=((1.25, 1.0), (4.0, 1.0)),
        impact_mass_kg=(8.0, 3.0),
    )
    ledger = MassLedger(
        released_kg=11.0,
        deposited_kg=deposition.deposited_mass_kg,
        airborne_vof_kg=0.0,
        airborne_parcels_kg=0.0,
        escaped_kg=0.0,
        evaporated_kg=0.0,
    )

    scoring_map = _scoring_fixture()
    score = score_ground_map(scoring_map, 250.0, 2.5, 2.4)
    ellipse = ellipse_rectangle_check(25.0, 7.0, 9.0)
    handoff = check_momentum_conservation((1.0, 2.0, 3.0), (0.25, 0.5, 0.75), (0.75, 1.5, 2.25))

    checks = {
        "constant_inlet_mass": {
            "mass_for_normal_velocity_kg": mass_a,
            "mass_with_changed_tangential_velocity_kg": mass_b,
            "expected_mass_kg": density * area * 5.0 * duration,
            "passed": math.isclose(mass_a, mass_b, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(
                mass_a,
                density * area * 5.0 * duration,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ),
        },
        "ballistic_trajectory": {
            "flight_time_s": ballistic.flight_time_s,
            "impact_time_s": ballistic.impact_time_s,
            "impact_position_m": list(ballistic.position_m),
            "expected_flight_time_s": expected_flight,
            "expected_impact_time_s": expected_impact_time,
            "expected_impact_position_m": list(expected_impact_position),
            "passed": math.isclose(
                ballistic.flight_time_s, expected_flight, rel_tol=1e-12, abs_tol=1e-12
            )
            and math.isclose(
                ballistic.impact_time_s, expected_impact_time, rel_tol=1e-12, abs_tol=1e-12
            )
            and np.allclose(ballistic.position_m, expected_impact_position, rtol=1e-12, atol=1e-12),
        },
        "weighted_deposition_and_ledger": {
            "input_impact_mass_kg": 11.0,
            "in_map_mass_kg": deposition.in_map_mass_kg,
            "outside_map_mass_kg": deposition.outside_map_mass_kg,
            "deposited_mass_kg": deposition.deposited_mass_kg,
            "airborne_vof_mass_kg": ledger.airborne_vof_kg,
            "airborne_parcel_mass_kg": ledger.airborne_parcels_kg,
            "escaped_mass_kg": ledger.escaped_kg,
            "ledger_residual_kg": ledger.residual_kg,
            "impact_locations_xy_m": deposition.impact_locations_xy_m.tolist(),
            "impact_masses_kg": deposition.impact_masses_kg.tolist(),
            "passed": math.isclose(deposition.in_map_mass_kg, 8.0, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(deposition.outside_map_mass_kg, 3.0, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(deposition.deposited_mass_kg, 11.0, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(ledger.residual_kg, 0.0, rel_tol=0.0, abs_tol=1e-12),
        },
        "continuous_strip_scoring": {
            "synthetic_map": True,
            "l95_m": score.l95_m,
            "strip_x_m": [score.strip_x_start_m, score.strip_x_stop_m],
            "strip_cell_indices_start_stop": [score.strip_start_index, score.strip_stop_index],
            "useful_fraction": score.useful_fraction,
            "useful_credit_mass_kg": score.useful_credit_mass_kg,
            "actual_mass_inside_strip_kg": score.actual_mass_inside_strip_kg,
            "mass_elsewhere_on_ground_kg": score.mass_elsewhere_on_ground_kg,
            "expected_l95_m": 5.0,
            "expected_useful_credit_mass_kg": 28.5,
            "expected_actual_mass_inside_strip_kg": 35.625,
            "expected_mass_elsewhere_on_ground_kg": 164.375,
            "expected_useful_fraction": 0.114,
            "passed": math.isclose(score.l95_m, 5.0, rel_tol=1e-12, abs_tol=1e-12)
            and score.strip_start_index == 0
            and math.isclose(score.useful_credit_mass_kg, 28.5, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(
                score.actual_mass_inside_strip_kg, 35.625, rel_tol=1e-12, abs_tol=1e-12
            )
            and math.isclose(
                score.mass_elsewhere_on_ground_kg, 164.375, rel_tol=1e-12, abs_tol=1e-12
            )
            and math.isclose(score.useful_fraction, 0.114, rel_tol=1e-12, abs_tol=1e-12),
        },
        "ellipse_rectangle_illustration": {
            "semi_axes_m": [25.0, 7.0],
            "ellipse_area_m2": ellipse.ellipse_area_m2,
            "target_width_m": ellipse.target_width_m,
            "full_width_ellipse_length_m": ellipse.full_width_ellipse_length_m,
            "same_area_rectangle_length_m": ellipse.same_area_rectangle_length_m,
            "rectangle_to_ellipse_length_ratio": ellipse.rectangle_to_ellipse_length_ratio,
            "comparison": "full-width geometry; not the map-based 95% L95 metric",
            "passed": math.isclose(
                ellipse.full_width_ellipse_length_m,
                38.29930462415574,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            and math.isclose(
                ellipse.same_area_rectangle_length_m,
                61.08652381980154,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            and math.isclose(
                ellipse.rectangle_to_ellipse_length_ratio or 0.0,
                1.5949773610582394,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ),
        },
        "zero_control_gain": {
            "gain": improvement_gain(10.0, 0.0),
            "passed": improvement_gain(10.0, 0.0) is None,
        },
        "handoff_momentum_check": {
            "residual_kg_m_s": list(handoff.residual_kg_m_s),
            "residual_norm_kg_m_s": handoff.residual_norm_kg_m_s,
            "tolerance_kg_m_s": handoff.tolerance_kg_m_s,
            "passed": handoff.conserved,
            "scope": "algebraic check only; no VOF or parcel handoff is implemented",
        },
    }
    if not all(bool(check["passed"]) for check in checks.values()):
        raise ArithmeticError("one or more E0 analytical checks failed")
    return checks, scoring_map, deposition


def _default_output_path(repository_root: Path) -> Path:
    runs_dir = repository_root / "results" / "runs"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return runs_dir / f"e0-{timestamp}-{uuid.uuid4().hex[:8]}"


def write_e0_run(output_path: str | Path | None = None) -> Path:
    """Write a fresh, analytical-only E0 report and map bundle."""
    started = time.perf_counter()
    repository_root = Path(__file__).resolve().parents[2]
    checks, scoring_map, deposition = _run_checks()
    run_dir = (
        Path(output_path) if output_path is not None else _default_output_path(repository_root)
    )
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    # ``exist_ok=False`` is intentional: every run gets an immutable output directory.
    run_dir.mkdir(exist_ok=False)

    revision, dirty = _git_metadata(repository_root)
    try:
        distribution_version = importlib.metadata.version("fire-track2")
    except importlib.metadata.PackageNotFoundError:
        distribution_version = "source-tree"
    report: dict[str, object] = {
        "experiment": "E0 analytical verification",
        "scope": "analytical checks only; no CFD, VOF, breakup, drag, wind transport, or field validation",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "seed": 0,
        "seed_note": "No stochastic operation is used in E0; seed is recorded for run-schema consistency.",
        "input_config": {
            "release_density_kg_m3": 1000.0,
            "release_area_m2": 0.12,
            "release_normal_velocity_m_s": 5.0,
            "release_tangential_velocity_cases_m_s": [[0.0, 0.0], [-12.0, 3.0]],
            "release_duration_s": 2.0,
            "ballistic_aircraft_speed_m_s": [10.0, 2.0, 0.0],
            "ballistic_release_time_s": 4.0,
            "ballistic_initial_height_m": 100.0,
            "ballistic_gravity_m_s2": -10.0,
            "scoring_target_width_m": 2.5,
            "scoring_released_mass_kg": 250.0,
            "scoring_threshold_kg_m2": 2.4,
            "scoring_required_width_fraction": 0.95,
            "scoring_map": "synthetic nonuniform grid with a gap and equal-length valid runs",
            "ellipse_example": {
                "semi_major_axis_m": 25.0,
                "semi_minor_axis_m": 7.0,
                "target_width_m": 9.0,
                "source": "Restas (2023), Examining_the_Effectiveness_of_Aerial_Firefighting.pdf, pp. 10-12 / Table 1",
            },
            "weighted_deposition_impacts": {
                "locations_xy_m": deposition.impact_locations_xy_m.tolist(),
                "masses_kg": deposition.impact_masses_kg.tolist(),
                "interpretation": "outside-map points landed on ground outside map extent",
            },
        },
        "provenance": {
            "revision": revision,
            "dirty": dirty,
            "code_sha256": _code_hashes(repository_root),
            "package_versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "fire-track2": distribution_version,
            },
        },
        "checks": checks,
    }
    np.savez_compressed(
        run_dir / "ground-map.npz",
        x_edges_m=scoring_map.x_edges_m,
        y_edges_m=scoring_map.y_edges_m,
        concentration_kg_m2=scoring_map.concentration_kg_m2,
        weighted_deposition_x_edges_m=deposition.ground_map.x_edges_m,
        weighted_deposition_y_edges_m=deposition.ground_map.y_edges_m,
        weighted_deposition_kg_m2=deposition.ground_map.concentration_kg_m2,
        impact_locations_xy_m=deposition.impact_locations_xy_m,
        impact_masses_kg=deposition.impact_masses_kg,
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    report["input_config_sha256"] = hashlib.sha256(
        json.dumps(report["input_config"], sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    report["artifact_sha256"] = {
        "ground-map.npz": hashlib.sha256((run_dir / "ground-map.npz").read_bytes()).hexdigest()
    }
    rss_multiplier = 1 if sys.platform == "darwin" else 1024
    report["resource_use"] = {
        "wall_time_to_map_write_s": time.perf_counter() - started,
        "peak_rss_bytes": int(usage.ru_maxrss * rss_multiplier),
        "scope": "E0 analytical checks and NPZ serialization; excludes JSON manifest write",
    }
    with (run_dir / "e0-report.json").open("w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=2, sort_keys=True, allow_nan=False)
        report_file.write("\n")
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="new run directory (must not already exist); defaults to results/runs/e0-<UTC>-<id>",
    )
    args = parser.parse_args(argv)
    run_dir = write_e0_run(args.output)
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
