"""Numerical motion of one isolated, fixed-radius water drop.

This module implements the momentum and aerodynamic-drag relations in
Denner (2026), Eqs. (1)--(11), for a single drop in a constant wind. It omits
evaporation, breakup products, collisions, spray feedback, wakes and turbulence.
The integrator stops at the first predicted breakup or ground impact so that a
fixed-radius trajectory is never continued beyond those events.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
StopReason = Literal["duration", "breakup", "ground"]


def _scalar(name: str, value: float, *, positive: bool = False) -> float:
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


def _readonly(values: list[FloatArray]) -> FloatArray:
    result = np.array(values, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _readonly_times(values: list[float]) -> FloatArray:
    result = np.array(values, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class MotionProperties:
    """Constant properties for the non-evaporating momentum model.

    Defaults are clearly provisional ambient values near 20 C. For comparisons
    against a specific paper or experiment, pass the case's documented values.
    """

    water_density_kg_m3: float = 997.0
    air_density_kg_m3: float = 1.204
    air_dynamic_viscosity_pa_s: float = 1.81e-5
    surface_tension_n_m: float = 0.072
    gravity_m_s2: tuple[float, float, float] = (0.0, 0.0, -9.81)

    def __post_init__(self) -> None:
        for name in (
            "water_density_kg_m3",
            "air_density_kg_m3",
            "air_dynamic_viscosity_pa_s",
            "surface_tension_n_m",
        ):
            object.__setattr__(self, name, _scalar(name, getattr(self, name), positive=True))
        gravity = _vector3("gravity_m_s2", self.gravity_m_s2)
        if float(np.linalg.norm(gravity)) == 0.0:
            raise ValueError("gravity_m_s2 must have nonzero magnitude")
        object.__setattr__(self, "gravity_m_s2", tuple(float(v) for v in gravity))


@dataclass(frozen=True)
class DropAerodynamics:
    reynolds_number: float
    weber_number: float
    drag_coefficient: float
    critical_weber_number: float
    breakup_predicted: bool


@dataclass(frozen=True)
class DropTrajectory:
    """An immutable sampled path, truncated at duration, breakup, or impact."""

    time_s: FloatArray
    position_m: FloatArray
    velocity_m_s: FloatArray
    radius_m: float
    stop_reason: StopReason
    breakup_bracket_s: tuple[float, float] | None
    ground_z_m: float | None

    @property
    def flight_time_s(self) -> float:
        return float(self.time_s[-1])

    @property
    def impact_position_m(self) -> tuple[float, float, float] | None:
        if self.stop_reason != "ground":
            return None
        return tuple(float(value) for value in self.position_m[-1])

    @property
    def within_nominal_source_size_range(self) -> bool:
        """Whether radius falls in Denner's cited 20 um--2 mm source range."""
        return 20e-6 <= self.radius_m <= 2e-3


def evaluate_drop_aerodynamics(
    radius_m: float,
    air_velocity_m_s: ArrayLike,
    drop_velocity_m_s: ArrayLike,
    properties: MotionProperties = MotionProperties(),
) -> DropAerodynamics:
    """Evaluate Denner (2026) Eqs. (5)--(11) at one state."""
    radius = _scalar("radius_m", radius_m, positive=True)
    air = _vector3("air_velocity_m_s", air_velocity_m_s)
    drop = _vector3("drop_velocity_m_s", drop_velocity_m_s)
    relative = air - drop
    speed = float(np.linalg.norm(relative))
    rho_a = properties.air_density_kg_m3
    mu_a = properties.air_dynamic_viscosity_pa_s
    sigma = properties.surface_tension_n_m
    reynolds = 2.0 * radius * rho_a * speed / mu_a
    weber = 2.0 * radius * rho_a * speed**2 / sigma

    if reynolds == 0.0:
        # The Stokes drag coefficient diverges at Re -> 0, while the vector
        # drag force tends continuously to zero with relative speed.
        cd_sphere = math.inf
        cd = math.inf
    else:
        cd_sphere = (24.0 / reynolds) * (
            1.0 + 0.15 * reynolds**0.687 + 0.0175 * reynolds / (1.0 + 42500.0 * reynolds**-1.16)
        )
        max_radius = radius * (1.0 + 0.19 * math.sqrt(weber))
        cd = cd_sphere * (1.0 + 2.632 * (1.0 - (radius / max_radius) ** 2))

    max_radius = radius * (1.0 + 0.19 * math.sqrt(weber))
    gravity_magnitude = float(np.linalg.norm(properties.gravity_m_s2))
    bond = properties.water_density_kg_m3 * gravity_magnitude * (2.0 * radius) ** 2 / sigma
    critical_weber = (4.0 / (3.0 * cd)) * (
        4.0 * math.pi**2 * (radius / max_radius) ** 4 - bond * (radius / max_radius) ** 2
    )
    return DropAerodynamics(
        reynolds_number=reynolds,
        weber_number=weber,
        drag_coefficient=cd,
        critical_weber_number=critical_weber,
        breakup_predicted=weber > critical_weber,
    )


def _acceleration(
    radius_m: float,
    air_velocity_m_s: FloatArray,
    drop_velocity_m_s: FloatArray,
    properties: MotionProperties,
) -> FloatArray:
    relative = air_velocity_m_s - drop_velocity_m_s
    speed = float(np.linalg.norm(relative))
    gravity = np.asarray(properties.gravity_m_s2)
    buoyancy_corrected_gravity = (
        1.0 - properties.air_density_kg_m3 / properties.water_density_kg_m3
    ) * gravity
    if speed == 0.0:
        return buoyancy_corrected_gravity
    aero = evaluate_drop_aerodynamics(radius_m, air_velocity_m_s, drop_velocity_m_s, properties)
    # The factor follows F_D/(rho_w V_d), using V_d=4*pi*r^3/3.
    drag_acceleration = (
        3.0
        * properties.air_density_kg_m3
        * aero.drag_coefficient
        * speed
        / (8.0 * properties.water_density_kg_m3 * radius_m)
        * relative
    )
    return buoyancy_corrected_gravity + drag_acceleration


def drop_acceleration_m_s2(
    radius_m: float,
    air_velocity_m_s: ArrayLike,
    drop_velocity_m_s: ArrayLike,
    properties: MotionProperties = MotionProperties(),
) -> FloatArray:
    """Return the Denner (2026) momentum-model acceleration at one state."""
    radius = _scalar("radius_m", radius_m, positive=True)
    air = _vector3("air_velocity_m_s", air_velocity_m_s)
    drop = _vector3("drop_velocity_m_s", drop_velocity_m_s)
    return _acceleration(radius, air, drop, properties)


def _breakup_margin(
    radius_m: float,
    air_velocity_m_s: FloatArray,
    drop_velocity_m_s: FloatArray,
    properties: MotionProperties,
) -> float:
    aero = evaluate_drop_aerodynamics(radius_m, air_velocity_m_s, drop_velocity_m_s, properties)
    return aero.weber_number - aero.critical_weber_number


def _rk4_step(
    position: FloatArray,
    velocity: FloatArray,
    step_s: float,
    radius_m: float,
    air_velocity_m_s: FloatArray,
    properties: MotionProperties,
) -> tuple[FloatArray, FloatArray]:
    def derivative(
        state_position: FloatArray, state_velocity: FloatArray
    ) -> tuple[FloatArray, FloatArray]:
        return state_velocity, _acceleration(radius_m, air_velocity_m_s, state_velocity, properties)

    k1x, k1v = derivative(position, velocity)
    k2x, k2v = derivative(position + 0.5 * step_s * k1x, velocity + 0.5 * step_s * k1v)
    k3x, k3v = derivative(position + 0.5 * step_s * k2x, velocity + 0.5 * step_s * k2v)
    k4x, k4v = derivative(position + step_s * k3x, velocity + step_s * k3v)
    next_position = position + (step_s / 6.0) * (k1x + 2 * k2x + 2 * k3x + k4x)
    next_velocity = velocity + (step_s / 6.0) * (k1v + 2 * k2v + 2 * k3v + k4v)
    return next_position, next_velocity


def integrate_isolated_drop(
    initial_position_m: ArrayLike,
    initial_velocity_m_s: ArrayLike,
    radius_m: float,
    air_velocity_m_s: ArrayLike = (0.0, 0.0, 0.0),
    *,
    duration_s: float,
    step_s: float,
    ground_z_m: float | None = None,
    properties: MotionProperties = MotionProperties(),
) -> DropTrajectory:
    """Integrate an isolated-drop path with fixed-step classical RK4.

    The result stops on the first sampled Denner breakup criterion or the
    first descending ground-plane crossing. Breakup time is reported as a
    bracket no wider than ``step_s``; the event's upper bracket endpoint is
    retained as the last sample so it can be reproduced from the input bundle.
    The fixed-radius model must not be interpreted after that event.
    """
    position = _vector3("initial_position_m", initial_position_m).copy()
    velocity = _vector3("initial_velocity_m_s", initial_velocity_m_s).copy()
    air = _vector3("air_velocity_m_s", air_velocity_m_s)
    radius = _scalar("radius_m", radius_m, positive=True)
    duration = _scalar("duration_s", duration_s, positive=True)
    step = _scalar("step_s", step_s, positive=True)
    ground = None if ground_z_m is None else _scalar("ground_z_m", ground_z_m)
    if ground is not None and position[2] < ground:
        raise ValueError("initial_position_m must be on or above the ground plane")

    times = [0.0]
    positions = [position.copy()]
    velocities = [velocity.copy()]
    initial_acceleration = _acceleration(radius, air, velocity, properties)
    if (
        ground is not None
        and position[2] == ground
        and (velocity[2] < 0.0 or (velocity[2] == 0.0 and initial_acceleration[2] < 0.0))
    ):
        return DropTrajectory(
            _readonly_times(times),
            _readonly(positions),
            _readonly(velocities),
            radius,
            "ground",
            None,
            ground,
        )
    if _breakup_margin(radius, air, velocity, properties) > 0.0:
        return DropTrajectory(
            _readonly_times(times),
            _readonly(positions),
            _readonly(velocities),
            radius,
            "breakup",
            (0.0, 0.0),
            ground,
        )

    elapsed = 0.0
    while elapsed < duration:
        h = min(step, duration - elapsed)
        next_position, next_velocity = _rk4_step(position, velocity, h, radius, air, properties)
        end_time = elapsed + h
        breakup_margin_end = _breakup_margin(radius, air, next_velocity, properties)
        breakup_event: tuple[float, float, FloatArray, FloatArray] | None = None
        if breakup_margin_end > 0.0:
            lo = 0.0
            hi = h
            event_position = next_position
            event_velocity = next_velocity
            for _ in range(48):
                mid = 0.5 * (lo + hi)
                mid_position, mid_velocity = _rk4_step(
                    position, velocity, mid, radius, air, properties
                )
                if _breakup_margin(radius, air, mid_velocity, properties) > 0.0:
                    hi = mid
                    event_position, event_velocity = mid_position, mid_velocity
                else:
                    lo = mid
            breakup_event = (hi, lo, event_position, event_velocity)

        ground_event: tuple[float, FloatArray, FloatArray] | None = None
        if ground is not None and position[2] > ground and next_position[2] <= ground:
            lo = 0.0
            hi = h
            impact_position = next_position
            impact_velocity = next_velocity
            for _ in range(48):
                mid = 0.5 * (lo + hi)
                mid_position, mid_velocity = _rk4_step(
                    position, velocity, mid, radius, air, properties
                )
                if mid_position[2] <= ground:
                    hi = mid
                    impact_position, impact_velocity = mid_position, mid_velocity
                else:
                    lo = mid
            ground_event = (hi, impact_position, impact_velocity)

        if breakup_event is not None and (
            ground_event is None or breakup_event[0] < ground_event[0]
        ):
            event_h, bracket_lower_h, event_position, event_velocity = breakup_event
            times.append(elapsed + event_h)
            positions.append(event_position.copy())
            velocities.append(event_velocity.copy())
            return DropTrajectory(
                _readonly_times(times),
                _readonly(positions),
                _readonly(velocities),
                radius,
                "breakup",
                (elapsed + bracket_lower_h, elapsed + event_h),
                ground,
            )

        if ground_event is not None:
            impact_h, impact_position, impact_velocity = ground_event
            impact_position[2] = ground
            times.append(elapsed + impact_h)
            positions.append(impact_position)
            velocities.append(impact_velocity)
            return DropTrajectory(
                _readonly_times(times),
                _readonly(positions),
                _readonly(velocities),
                radius,
                "ground",
                None,
                ground,
            )
        elapsed = end_time
        position, velocity = next_position, next_velocity
        times.append(elapsed)
        positions.append(position.copy())
        velocities.append(velocity.copy())

    return DropTrajectory(
        _readonly_times(times),
        _readonly(positions),
        _readonly(velocities),
        radius,
        "duration",
        None,
        ground,
    )
