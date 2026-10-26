"""Reduced, single-liquid model for the provisional I4F internal discharge line.

The model couples tank liquid inventory, a sealed polytropic gas headspace, a
hydrostatic head, a time-varying equivalent valve restriction, Darcy pipe
friction, a lumped pipe/transition inertance, and an outlet kinetic head.  It
does not resolve the butterfly disk, the transition flow, gas entrainment, or
the external sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, isfinite, log, pi, sqrt
from typing import Any, Mapping

import numpy as np

R_AIR_J_KG_K = 287.05
R_CO2_J_KG_K = 188.92
WATER_VAPOR_PRESSURE_SCREEN_20C_PA = 2339.2
WATER_VAPOR_PRESSURE_SCREEN_TEMPERATURE_K = 293.15
WATER_VAPOR_PRESSURE_SCREEN_SOURCE = "IAPWS SR1-86(1992), saturation-pressure correlation"


@dataclass(frozen=True)
class ModelParameters:
    tank_axis: str
    tank_diameter_m: float
    tank_length_m: float
    tank_center_z_m: float
    tank_fill_fraction: float
    pipe_diameter_m: float
    pipe_length_m: float
    transition_length_m: float
    roughness_m: float
    entrance_loss_K: float
    transition_loss_K: float
    nozzle_width_m: float
    nozzle_height_m: float
    outlet_center_z_m: float
    connection_upper_edge_z_m: float
    gas_mode: str
    gas_kind: str
    initial_gas_pressure_Pa: float
    ambient_pressure_Pa: float
    gas_temperature_K: float
    polytropic_n: float
    liquid_density_kg_m3: float
    liquid_viscosity_Pa_s: float
    gravity_m_s2: float
    valve_opening_time_s: float
    valve_Cd: float
    valve_opening_law: str
    valve_minimum_effective_opening: float

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        polytropic_n: float | None = None,
        valve_opening_time_s: float | None = None,
        minimum_effective_opening: float | None = None,
    ) -> ModelParameters:
        tank = config["tank"]
        connection = config["connection"]
        pipe = config["pipe"]
        nozzle = config["nozzle"]
        gas = config["gas"]
        liquid = config.get("liquid", {})
        valve = config["valve"]
        result = cls(
            tank_axis=str(tank["axis"]).lower(),
            tank_diameter_m=float(tank["diameter_m"]),
            tank_length_m=float(tank["length_m"]),
            tank_center_z_m=float(tank["center_z_m"]),
            tank_fill_fraction=float(tank["fill_fraction"]),
            pipe_diameter_m=float(pipe["diameter_m"]),
            pipe_length_m=float(pipe["length_m"]),
            transition_length_m=float(pipe["transition_length_m"]),
            roughness_m=float(pipe["roughness_m"]),
            entrance_loss_K=float(pipe.get("entrance_K", 0.0)),
            transition_loss_K=float(pipe["transition_K"]),
            nozzle_width_m=float(nozzle["width_m"]),
            nozzle_height_m=float(nozzle["height_m"]),
            outlet_center_z_m=float(nozzle.get("center_z_m", connection["center_z_m"])),
            connection_upper_edge_z_m=float(connection["upper_edge_z_m"]),
            gas_mode=str(gas["mode"]).lower(),
            gas_kind=str(gas["kind"]).lower(),
            initial_gas_pressure_Pa=float(gas["initial_absolute_pressure_Pa"]),
            ambient_pressure_Pa=float(gas["ambient_pressure_Pa"]),
            gas_temperature_K=float(gas["temperature_K"]),
            polytropic_n=float(gas["polytropic_n"] if polytropic_n is None else polytropic_n),
            liquid_density_kg_m3=float(liquid.get("density_kg_m3", 998.2)),
            liquid_viscosity_Pa_s=float(liquid.get("dynamic_viscosity_Pa_s", 0.001002)),
            gravity_m_s2=float(config.get("gravity_m_s2", 9.81)),
            valve_opening_time_s=float(
                valve["opening_time_s"] if valve_opening_time_s is None else valve_opening_time_s
            ),
            valve_Cd=float(valve["Cd"]),
            valve_opening_law=str(valve["opening_law"]).lower(),
            valve_minimum_effective_opening=float(
                valve.get("minimum_effective_opening", 0.0)
                if minimum_effective_opening is None
                else minimum_effective_opening
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        positive = {
            "tank_diameter_m": self.tank_diameter_m,
            "tank_length_m": self.tank_length_m,
            "pipe_diameter_m": self.pipe_diameter_m,
            "pipe_length_m": self.pipe_length_m,
            "transition_length_m": self.transition_length_m,
            "nozzle_width_m": self.nozzle_width_m,
            "nozzle_height_m": self.nozzle_height_m,
            "initial_gas_pressure_Pa": self.initial_gas_pressure_Pa,
            "ambient_pressure_Pa": self.ambient_pressure_Pa,
            "gas_temperature_K": self.gas_temperature_K,
            "polytropic_n": self.polytropic_n,
            "liquid_density_kg_m3": self.liquid_density_kg_m3,
            "liquid_viscosity_Pa_s": self.liquid_viscosity_Pa_s,
            "gravity_m_s2": self.gravity_m_s2,
            "valve_Cd": self.valve_Cd,
        }
        for name, value in positive.items():
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.tank_axis not in {"horizontal", "vertical"}:
            raise ValueError("tank.axis must be 'horizontal' or 'vertical'")
        if not 0 < self.tank_fill_fraction < 1:
            raise ValueError("tank.fill_fraction must be strictly between zero and one")
        if self.gas_mode not in {"sealed", "maintained_pressure"}:
            raise ValueError("gas.mode must be 'sealed' or 'maintained_pressure'")
        if self.valve_opening_law not in {"smoothstep", "linear"}:
            raise ValueError("valve.opening_law must be 'smoothstep' or 'linear'")
        if self.valve_opening_time_s < 0 or not isfinite(self.valve_opening_time_s):
            raise ValueError("valve.opening_time_s must be finite and nonnegative")
        if (
            not isfinite(self.valve_minimum_effective_opening)
            or not 0.0 <= self.valve_minimum_effective_opening <= 1.0
        ):
            raise ValueError("valve.minimum_effective_opening must lie in [0, 1]")
        if self.roughness_m < 0 or self.entrance_loss_K < 0 or self.transition_loss_K < 0:
            raise ValueError("roughness and local loss coefficients must be nonnegative")
        if self.gas_kind not in {"air", "co2"}:
            raise ValueError("gas.kind must be 'air' or 'co2'")

    @property
    def tank_volume_m3(self) -> float:
        return pi * (self.tank_diameter_m / 2.0) ** 2 * self.tank_length_m

    @property
    def pipe_area_m2(self) -> float:
        return pi * (self.pipe_diameter_m / 2.0) ** 2

    @property
    def nozzle_area_m2(self) -> float:
        return self.nozzle_width_m * self.nozzle_height_m

    @property
    def line_prefill_volume_m3(self) -> float:
        """Water initially in pipe and linear-area transition, excluding tank."""
        area_pipe = self.pipe_area_m2
        area_nozzle = self.nozzle_area_m2
        return (
            self.pipe_length_m * area_pipe
            + self.transition_length_m * (area_pipe + area_nozzle) / 2.0
        )

    @property
    def liquid_column_inertance_kg_m4(self) -> float:
        """rho times integral(dl/A) for pipe plus linear-area transition."""
        area_pipe = self.pipe_area_m2
        area_nozzle = self.nozzle_area_m2
        if abs(area_nozzle - area_pipe) <= 1e-12 * max(area_pipe, area_nozzle):
            transition_integral = self.transition_length_m / area_pipe
        else:
            transition_integral = (
                self.transition_length_m * log(area_nozzle / area_pipe) / (area_nozzle - area_pipe)
            )
        return self.liquid_density_kg_m3 * (self.pipe_length_m / area_pipe + transition_integral)

    @property
    def pipe_inertance_kg_m4(self) -> float:
        """Straight-pipe contribution to the liquid-column inertance."""
        return self.liquid_density_kg_m3 * self.pipe_length_m / self.pipe_area_m2

    @property
    def transition_inertance_kg_m4(self) -> float:
        """Transition contribution, partitioned from the solver's total inertance."""
        return self.liquid_column_inertance_kg_m4 - self.pipe_inertance_kg_m4

    @property
    def gas_specific_constant_J_kg_K(self) -> float:
        return R_AIR_J_KG_K if self.gas_kind == "air" else R_CO2_J_KG_K


@dataclass(frozen=True)
class SimulationResult:
    parameters: ModelParameters
    samples: dict[str, np.ndarray]
    stop_reason: str
    stop_time_s: float
    initial_tank_water_volume_m3: float
    stop_tank_water_volume_m3: float
    initial_gas_volume_m3: float
    initial_line_water_volume_m3: float
    max_mass_balance_error_m3: float


def _circle_segment_area_m2(radius_m: float, depth_m: float) -> float:
    """Area below a horizontal chord at depth from the circle's bottom."""
    depth = min(2.0 * radius_m, max(0.0, depth_m))
    if depth == 0:
        return 0.0
    if depth == 2.0 * radius_m:
        return pi * radius_m**2
    y = radius_m - depth
    return radius_m**2 * acos(y / radius_m) - y * sqrt(max(0.0, radius_m**2 - y**2))


def tank_total_volume_m3(parameters: ModelParameters) -> float:
    return parameters.tank_volume_m3


def tank_volume_at_level_m3(parameters: ModelParameters, level_z_m: float) -> float:
    """Liquid volume below an absolute z level in the configured tank orientation."""
    radius = parameters.tank_diameter_m / 2.0
    if parameters.tank_axis == "vertical":
        bottom_z = parameters.tank_center_z_m - parameters.tank_length_m / 2.0
        depth = min(parameters.tank_length_m, max(0.0, level_z_m - bottom_z))
        return pi * radius**2 * depth
    bottom_z = parameters.tank_center_z_m - radius
    depth = min(2.0 * radius, max(0.0, level_z_m - bottom_z))
    return parameters.tank_length_m * _circle_segment_area_m2(radius, depth)


def tank_level_z_m(parameters: ModelParameters, water_volume_m3: float) -> float:
    """Invert the tank-volume relation, including horizontal-cylinder level fall."""
    volume = min(parameters.tank_volume_m3, max(0.0, water_volume_m3))
    radius = parameters.tank_diameter_m / 2.0
    if parameters.tank_axis == "vertical":
        bottom_z = parameters.tank_center_z_m - parameters.tank_length_m / 2.0
        return bottom_z + volume / (pi * radius**2)
    if volume <= 0:
        return parameters.tank_center_z_m - radius
    if volume >= parameters.tank_volume_m3:
        return parameters.tank_center_z_m + radius
    target_area = volume / parameters.tank_length_m
    lower = 0.0
    upper = 2.0 * radius
    for _ in range(56):
        middle = (lower + upper) / 2.0
        if _circle_segment_area_m2(radius, middle) < target_area:
            lower = middle
        else:
            upper = middle
    return parameters.tank_center_z_m - radius + (lower + upper) / 2.0


def tank_free_surface_area_m2(parameters: ModelParameters, level_z_m: float) -> float:
    """Horizontal plan area exposed to the gas at the current liquid level."""
    radius = parameters.tank_diameter_m / 2.0
    if parameters.tank_axis == "vertical":
        bottom_z = parameters.tank_center_z_m - parameters.tank_length_m / 2.0
        top_z = bottom_z + parameters.tank_length_m
        return pi * radius**2 if bottom_z < level_z_m < top_z else 0.0
    local_height = level_z_m - parameters.tank_center_z_m
    chord = 2.0 * sqrt(max(0.0, radius**2 - local_height**2))
    return parameters.tank_length_m * chord


def valve_command_fraction(parameters: ModelParameters, time_s: float) -> float:
    """Commanded valve stroke fraction; it is not a measured butterfly angle."""
    duration = parameters.valve_opening_time_s
    if duration == 0 or time_s >= duration:
        return 1.0
    x = min(1.0, max(0.0, time_s / duration))
    if parameters.valve_opening_law == "linear":
        return x
    return x * x * (3.0 - 2.0 * x)


def opening_fraction(parameters: ModelParameters, time_s: float) -> float:
    """Equivalent effective flow-area fraction, clamped by a minimum opening."""
    command = valve_command_fraction(parameters, time_s)
    floor = parameters.valve_minimum_effective_opening
    return max(floor, command)


def darcy_friction_factor(reynolds: float, relative_roughness: float) -> float:
    """Darcy friction factor: 64/Re laminar, Haaland turbulent, blended in transition."""
    if reynolds <= 0:
        return float("inf")
    laminar = 64.0 / reynolds
    if reynolds <= 2300.0:
        return laminar
    turbulent = (
        -1.8 * np.log10((max(0.0, relative_roughness) / 3.7) ** 1.11 + 6.9 / reynolds)
    ) ** -2
    if reynolds >= 4000.0:
        return float(turbulent)
    weight = (reynolds - 2300.0) / (4000.0 - 2300.0)
    return float((1.0 - weight) * laminar + weight * turbulent)


def pipe_friction_pressure_drop_Pa(parameters: ModelParameters, flow_rate_m3_s: float) -> float:
    """Signed Darcy-Weisbach pipe loss; zero-flow laminar limit is exactly zero."""
    flow = abs(flow_rate_m3_s)
    if flow == 0:
        return 0.0
    area = parameters.pipe_area_m2
    velocity = flow / area
    reynolds = (
        parameters.liquid_density_kg_m3
        * velocity
        * parameters.pipe_diameter_m
        / parameters.liquid_viscosity_Pa_s
    )
    friction = darcy_friction_factor(reynolds, parameters.roughness_m / parameters.pipe_diameter_m)
    drop = (
        0.5
        * parameters.liquid_density_kg_m3
        * friction
        * parameters.pipe_length_m
        / parameters.pipe_diameter_m
        * velocity**2
    )
    return float(np.copysign(drop, flow_rate_m3_s))


def line_static_pressure_diagnostics(
    parameters: ModelParameters,
    flow_rate_m3_s: float,
    flow_acceleration_m3_s2: float,
) -> dict[str, float]:
    """Return 1-D section-mean static pressures at the transition entry and after valve.

    Both locations lie on the horizontal, equal-elevation line. ``pE`` is the
    pipe-side transition entrance pressure, recovered backward from ambient
    through the transition. ``pV`` is the lumped station after the scalar valve
    and before the full pipe inertance/friction element. The latter is not a
    spatially resolved pressure tap when the valve lies within a modeled pipe.

    This is a single-liquid pressure screen. It does not model vapor formation,
    gas ingestion, cavitation nuclei, or pressure recovery within the transition.
    The pressure below the 20 C water vapor reference is therefore diagnostic,
    not a cavitation prediction or a validity gate for continuing integration.
    """
    flow = float(flow_rate_m3_s)
    acceleration = float(flow_acceleration_m3_s2)
    if not isfinite(flow) or flow < 0.0:
        raise ValueError("flow_rate_m3_s must be finite and nonnegative")
    if not isfinite(acceleration):
        raise ValueError("flow_acceleration_m3_s2 must be finite")

    rho = parameters.liquid_density_kg_m3
    area_pipe = parameters.pipe_area_m2
    area_nozzle = parameters.nozzle_area_m2
    dynamic_pipe = 0.5 * rho * (flow / area_pipe) ** 2
    dynamic_nozzle = 0.5 * rho * (flow / area_nozzle) ** 2
    transition_inertial = parameters.transition_inertance_kg_m4 * acceleration
    transition_kinetic_change = dynamic_nozzle - dynamic_pipe
    transition_loss = parameters.transition_loss_K * dynamic_pipe
    pressure_before_transition = (
        parameters.ambient_pressure_Pa
        + transition_inertial
        + transition_kinetic_change
        + transition_loss
    )
    pipe_inertial = parameters.pipe_inertance_kg_m4 * acceleration
    pipe_friction = pipe_friction_pressure_drop_Pa(parameters, flow)
    pressure_after_valve = pressure_before_transition + pipe_inertial + pipe_friction
    return {
        "pressure_transition_entry_abs_Pa": pressure_before_transition,
        "pressure_after_valve_abs_Pa": pressure_after_valve,
        "flow_acceleration_m3_s2": acceleration,
        "pressure_transition_inertance_Pa": transition_inertial,
        "pressure_transition_kinetic_change_Pa": transition_kinetic_change,
        "pressure_pipe_inertance_Pa": pipe_inertial,
        "pressure_vapor_reference_20C_abs_Pa": WATER_VAPOR_PRESSURE_SCREEN_20C_PA,
    }


def gas_state(
    parameters: ModelParameters,
    initial_gas_volume_m3: float,
    current_gas_volume_m3: float,
) -> tuple[float, float, float | None]:
    """Return absolute pressure, ideal-gas temperature, and sealed gas mass."""
    if current_gas_volume_m3 <= 0:
        raise ValueError("gas volume must remain positive")
    if parameters.gas_mode == "maintained_pressure":
        return parameters.initial_gas_pressure_Pa, parameters.gas_temperature_K, None
    ratio = initial_gas_volume_m3 / current_gas_volume_m3
    pressure = parameters.initial_gas_pressure_Pa * ratio**parameters.polytropic_n
    temperature = parameters.gas_temperature_K * ratio ** (parameters.polytropic_n - 1.0)
    gas_mass = (
        parameters.initial_gas_pressure_Pa
        * initial_gas_volume_m3
        / (parameters.gas_specific_constant_J_kg_K * parameters.gas_temperature_K)
    )
    return pressure, temperature, gas_mass


def _pipe_resistance_coefficients(
    parameters: ModelParameters, flow_rate_m3_s: float
) -> tuple[float, float, float, float]:
    """Return linear/quadratic pipe resistances (Pa per Q and Pa per Q^2)."""
    q = abs(flow_rate_m3_s)
    area = parameters.pipe_area_m2
    rho = parameters.liquid_density_kg_m3
    mu = parameters.liquid_viscosity_Pa_s
    diameter = parameters.pipe_diameter_m
    if q == 0:
        reynolds = 0.0
    else:
        reynolds = rho * (q / area) * diameter / mu
    relative_roughness = parameters.roughness_m / diameter
    if reynolds < 2300.0:
        # Hagen-Poiseuille, algebraically equivalent to Darcy f=64/Re.
        linear = 128.0 * mu * parameters.pipe_length_m / (pi * diameter**4)
        return linear, 0.0, reynolds, float("inf") if reynolds == 0 else 64.0 / reynolds
    friction = darcy_friction_factor(reynolds, relative_roughness)
    quadratic = 0.5 * rho * friction * parameters.pipe_length_m / diameter / area**2
    return 0.0, quadratic, reynolds, friction


def _loss_coefficients(
    parameters: ModelParameters, flow_rate_m3_s: float, open_fraction: float
) -> tuple[float, float, float, float, float, float, float, float]:
    """Pressure loss law coefficients and reported local K values."""
    rho = parameters.liquid_density_kg_m3
    area_pipe = parameters.pipe_area_m2
    area_nozzle = parameters.nozzle_area_m2
    linear_pipe, quadratic_pipe, reynolds, friction = _pipe_resistance_coefficients(
        parameters, flow_rate_m3_s
    )
    if open_fraction <= 0:
        valve_K = float("inf")
    else:
        valve_K = 1.0 / (parameters.valve_Cd * open_fraction) ** 2
    entrance_K = parameters.entrance_loss_K
    transition_K = parameters.transition_loss_K
    exit_K = (area_pipe / area_nozzle) ** 2
    quadratic_local = 0.5 * rho * (valve_K + entrance_K + transition_K + exit_K) / area_pipe**2
    return (
        linear_pipe,
        quadratic_pipe + quadratic_local,
        reynolds,
        friction,
        valve_K,
        entrance_K,
        transition_K,
        exit_K,
    )


def _positive_midpoint_root(
    old_flow: float,
    time_step_s: float,
    inertance_kg_m4: float,
    pressure_force_Pa: float,
    linear_resistance: float,
    quadratic_resistance: float,
) -> float:
    """Solve the implicit midpoint scalar equation for non-reversing discharge."""
    if not isfinite(quadratic_resistance):
        return 0.0
    factor = time_step_s / inertance_kg_m4
    a = factor * max(0.0, quadratic_resistance)
    b = 2.0 + factor * max(0.0, linear_resistance)
    c = 2.0 * old_flow + factor * pressure_force_Pa
    if c <= 0:
        return 0.0
    if a <= 1e-30:
        return c / b
    return 2.0 * c / (b + sqrt(b * b + 4.0 * a * c))


def inertial_flow_midpoint_step(
    flow_rate_m3_s: float,
    time_step_s: float,
    inertance_kg_m4: float,
    pressure_drive_Pa: float,
    linear_resistance_Pa_s_m3: float,
    quadratic_resistance_Pa_s2_m6: float,
) -> tuple[float, float]:
    """Advance ``I dQ/dt = drive - R1*Q - R2*Q|Q|`` by implicit midpoint.

    Returns midpoint and end-step nonnegative discharge rates.  This shared
    scalar update also provides an independent analytic limiting-test target.
    """
    if time_step_s <= 0 or inertance_kg_m4 <= 0:
        raise ValueError("time step and inertance must be positive")
    mid_flow = _positive_midpoint_root(
        flow_rate_m3_s,
        time_step_s,
        inertance_kg_m4,
        pressure_drive_Pa,
        linear_resistance_Pa_s_m3,
        quadratic_resistance_Pa_s2_m6,
    )
    new_flow = 2.0 * mid_flow - flow_rate_m3_s
    if new_flow < -1e-12:
        raise RuntimeError("reverse flow is outside this single-direction discharge model")
    return mid_flow, max(0.0, new_flow)


def _advance_step(
    parameters: ModelParameters,
    initial_gas_volume_m3: float,
    water_volume_m3: float,
    old_flow_m3_s: float,
    time_s: float,
    time_step_s: float,
) -> tuple[float, float, dict[str, float]]:
    """One implicit-midpoint step, iterating tank state and flow-dependent drag."""
    mid_time = time_s + time_step_s / 2.0
    mid_open = opening_fraction(parameters, mid_time)
    mid_flow = old_flow_m3_s
    diagnostics: dict[str, float] = {}
    for _ in range(12):
        mid_water = water_volume_m3 - mid_flow * time_step_s / 2.0
        mid_water = max(0.0, mid_water)
        level = tank_level_z_m(parameters, mid_water)
        gas_volume = parameters.tank_volume_m3 - mid_water
        gas_pressure, gas_temperature, _ = gas_state(parameters, initial_gas_volume_m3, gas_volume)
        surface_area = tank_free_surface_area_m2(parameters, level)
        tank_velocity_pressure = (
            0.0
            if surface_area <= 0
            else 0.5 * parameters.liquid_density_kg_m3 * (mid_flow / surface_area) ** 2
        )
        raw_drive = (
            gas_pressure
            - parameters.ambient_pressure_Pa
            + parameters.liquid_density_kg_m3
            * parameters.gravity_m_s2
            * (level - parameters.outlet_center_z_m)
        )
        drive = raw_drive + tank_velocity_pressure
        (
            linear,
            quadratic,
            reynolds,
            friction,
            valve_K,
            entrance_K,
            transition_K,
            exit_K,
        ) = _loss_coefficients(parameters, mid_flow, mid_open)
        candidate, _ = inertial_flow_midpoint_step(
            old_flow_m3_s,
            time_step_s,
            parameters.liquid_column_inertance_kg_m4,
            drive,
            linear,
            quadratic,
        )
        diagnostics = {
            "water_level_z_m": level,
            "gas_pressure_abs_Pa": gas_pressure,
            "gas_temperature_K": gas_temperature,
            "gas_volume_m3": gas_volume,
            "opening_fraction": mid_open,
            "valve_command_fraction": valve_command_fraction(parameters, mid_time),
            "pressure_drive_Pa": raw_drive,
            "tank_drawdown_kinetic_pressure_Pa": tank_velocity_pressure,
            "reynolds": reynolds,
            "darcy_friction_factor": friction,
            "valve_K_pipe_velocity_reference": valve_K,
            "entrance_K_pipe_velocity_reference": entrance_K,
            "transition_K_pipe_velocity_reference": transition_K,
            "exit_kinetic_K_pipe_velocity_reference": exit_K,
        }
        if abs(candidate - mid_flow) <= 1e-11 * max(1.0, candidate):
            mid_flow = candidate
            break
        mid_flow = 0.5 * mid_flow + 0.5 * candidate
    mid_flow, new_flow = inertial_flow_midpoint_step(
        old_flow_m3_s,
        time_step_s,
        parameters.liquid_column_inertance_kg_m4,
        diagnostics["pressure_drive_Pa"] + diagnostics["tank_drawdown_kinetic_pressure_Pa"],
        linear,
        quadratic,
    )
    diagnostics["flow_rate_m3_s"] = mid_flow
    diagnostics["new_flow_rate_m3_s"] = new_flow
    return mid_flow, new_flow, diagnostics


def _diagnostic_row(
    parameters: ModelParameters,
    initial_gas_volume_m3: float,
    time_s: float,
    water_volume_m3: float,
    flow_rate_m3_s: float,
    cumulative_out_volume_m3: float,
) -> dict[str, float]:
    level = tank_level_z_m(parameters, water_volume_m3)
    gas_volume = parameters.tank_volume_m3 - water_volume_m3
    gas_pressure, gas_temperature, gas_mass = gas_state(
        parameters, initial_gas_volume_m3, gas_volume
    )
    open_fraction = opening_fraction(parameters, time_s)
    losses = _loss_coefficients(parameters, flow_rate_m3_s, open_fraction)
    linear, quadratic, reynolds, friction, valve_K, entrance_K, transition_K, exit_K = losses
    rho = parameters.liquid_density_kg_m3
    area_pipe = parameters.pipe_area_m2
    q = max(0.0, flow_rate_m3_s)
    raw_drive = (
        gas_pressure
        - parameters.ambient_pressure_Pa
        + rho * parameters.gravity_m_s2 * (level - parameters.outlet_center_z_m)
    )
    surface_area = tank_free_surface_area_m2(parameters, level)
    tank_kinetic = 0.0 if surface_area <= 0 else 0.5 * rho * (q / surface_area) ** 2
    velocity_pipe = q / area_pipe
    if q == 0 and open_fraction == 0:
        pipe_loss = entrance_loss = transition_loss = exit_loss = 0.0
        valve_loss = max(0.0, raw_drive)
    else:
        pipe_loss = pipe_friction_pressure_drop_Pa(parameters, q)
        velocity_pressure = 0.5 * rho * velocity_pipe**2
        entrance_loss = velocity_pressure * entrance_K
        transition_loss = velocity_pressure * transition_K
        exit_loss = velocity_pressure * exit_K
        valve_loss = velocity_pressure * valve_K
    nozzle_velocity = q / parameters.nozzle_area_m2
    if isfinite(quadratic):
        acceleration = (
            raw_drive + tank_kinetic - linear * q - quadratic * q * abs(q)
        ) / parameters.liquid_column_inertance_kg_m4
    else:
        # A zero effective opening holds the zero-flow startup state.
        acceleration = 0.0
    pressure_diagnostics = line_static_pressure_diagnostics(parameters, q, acceleration)
    return {
        "time_s": time_s,
        "tank_water_volume_m3": water_volume_m3,
        "gas_volume_m3": gas_volume,
        "total_internal_water_volume_m3": water_volume_m3 + parameters.line_prefill_volume_m3,
        "cumulative_external_discharge_volume_m3": cumulative_out_volume_m3,
        "cumulative_external_discharge_mass_kg": rho * cumulative_out_volume_m3,
        "water_level_z_m": level,
        "gas_pressure_abs_Pa": gas_pressure,
        "gas_temperature_K": gas_temperature,
        "sealed_gas_mass_kg": float("nan") if gas_mass is None else gas_mass,
        "opening_fraction": open_fraction,
        "valve_command_fraction": valve_command_fraction(parameters, time_s),
        "flow_rate_m3_s": q,
        **pressure_diagnostics,
        "flow_rate_kg_s": rho * q,
        "pipe_velocity_m_s": velocity_pipe,
        "nozzle_velocity_m_s": nozzle_velocity,
        "pressure_drive_Pa": raw_drive,
        "tank_drawdown_kinetic_pressure_Pa": tank_kinetic,
        "pressure_pipe_friction_Pa": pipe_loss,
        "pressure_pipe_entrance_Pa": entrance_loss,
        "pressure_valve_Pa": valve_loss,
        "pressure_transition_Pa": transition_loss,
        "pressure_exit_kinetic_Pa": exit_loss,
        "reynolds": reynolds,
        "darcy_friction_factor": friction,
        "valve_K_pipe_velocity_reference": valve_K,
        "entrance_K_pipe_velocity_reference": entrance_K,
        "transition_K_pipe_velocity_reference": transition_K,
        "exit_kinetic_K_pipe_velocity_reference": exit_K,
        "outlet_momentum_flux_N": rho * q * nozzle_velocity,
        "pipe_transition_liquid_momentum_kg_m_s": rho
        * q
        * (parameters.pipe_length_m + parameters.transition_length_m),
        "mass_balance_residual_m3": 0.0,
    }


def simulate(
    config: Mapping[str, Any],
    *,
    polytropic_n: float | None = None,
    valve_opening_time_s: float | None = None,
    minimum_effective_opening: float | None = None,
    time_step_s: float = 1.0e-4,
    max_time_s: float = 10.0,
) -> SimulationResult:
    """Integrate until gas first reaches the upper edge of the tank connection."""
    if time_step_s <= 0 or not isfinite(time_step_s):
        raise ValueError("time_step_s must be finite and positive")
    if max_time_s <= 0 or not isfinite(max_time_s):
        raise ValueError("max_time_s must be finite and positive")
    parameters = ModelParameters.from_config(
        config,
        polytropic_n=polytropic_n,
        valve_opening_time_s=valve_opening_time_s,
        minimum_effective_opening=minimum_effective_opening,
    )
    tank_volume = parameters.tank_volume_m3
    water_initial = parameters.tank_fill_fraction * tank_volume
    gas_initial = tank_volume - water_initial
    stop_water = tank_volume_at_level_m3(parameters, parameters.connection_upper_edge_z_m)
    initial_level = tank_level_z_m(parameters, water_initial)
    if initial_level <= parameters.connection_upper_edge_z_m:
        raise ValueError("initial gas-liquid interface is already at/below connection upper edge")
    if stop_water >= water_initial:
        raise ValueError("gas-breakthrough stop condition leaves no drainable tank inventory")

    time_s = 0.0
    water = water_initial
    flow = 0.0
    out_volume = 0.0
    data: dict[str, list[float]] = {
        key: [] for key in _diagnostic_row(parameters, gas_initial, 0.0, water, 0.0, 0.0)
    }

    def record(time_value: float, water_value: float, flow_value: float, out_value: float) -> None:
        row = _diagnostic_row(
            parameters, gas_initial, time_value, water_value, flow_value, out_value
        )
        for key, value in row.items():
            data[key].append(value)

    record(time_s, water, flow, out_volume)
    stopped = False
    while time_s < max_time_s:
        step = min(time_step_s, max_time_s - time_s)
        mid_flow, new_flow, _ = _advance_step(parameters, gas_initial, water, flow, time_s, step)
        predicted_water = water - mid_flow * step
        if predicted_water <= stop_water:
            final_step = step
            for _ in range(12):
                mid_flow, new_flow, _ = _advance_step(
                    parameters, gas_initial, water, flow, time_s, final_step
                )
                if mid_flow <= 0:
                    raise RuntimeError("flow stopped before the declared gas-breakthrough event")
                corrected = (water - stop_water) / mid_flow
                if abs(corrected - final_step) <= 1e-12 * max(1.0, final_step):
                    final_step = corrected
                    break
                final_step = min(step, corrected)
            water_next = stop_water
            out_next = water_initial - water_next
            time_next = time_s + final_step
            record(time_next, water_next, new_flow, out_next)
            time_s, water, flow, out_volume = time_next, water_next, new_flow, out_next
            stopped = True
            break
        water_next = max(stop_water, predicted_water)
        out_next = water_initial - water_next
        time_next = time_s + step
        record(time_next, water_next, new_flow, out_next)
        time_s, water, flow, out_volume = time_next, water_next, new_flow, out_next

    if not stopped:
        reason = "maximum model time reached before gas breakthrough"
    else:
        reason = "gas-liquid interface reached the upper edge of the tank connection"
    arrays = {key: np.asarray(values, dtype=float) for key, values in data.items()}
    mass_residual = (
        water_initial
        - arrays["tank_water_volume_m3"]
        - arrays["cumulative_external_discharge_volume_m3"]
    )
    arrays["mass_balance_residual_m3"] = mass_residual
    return SimulationResult(
        parameters=parameters,
        samples=arrays,
        stop_reason=reason,
        stop_time_s=time_s,
        initial_tank_water_volume_m3=water_initial,
        stop_tank_water_volume_m3=water,
        initial_gas_volume_m3=gas_initial,
        initial_line_water_volume_m3=parameters.line_prefill_volume_m3,
        max_mass_balance_error_m3=float(np.max(np.abs(mass_residual))),
    )


def _first_pressure_screen_event(
    samples: Mapping[str, np.ndarray], pressure_key: str, threshold_pa: float
) -> dict[str, float] | None:
    pressure = samples[pressure_key]
    crossings = np.flatnonzero(pressure <= threshold_pa)
    if not len(crossings):
        return None
    index = int(crossings[0])
    tank_water = float(samples["tank_water_volume_m3"][index])
    initial_water = float(samples["tank_water_volume_m3"][0])
    return {
        "time_s": float(samples["time_s"][index]),
        "pressure_abs_Pa": float(pressure[index]),
        "tank_water_volume_m3": tank_water,
        "tank_water_fraction_initial": tank_water / initial_water,
        "cumulative_external_discharge_volume_m3": float(
            samples["cumulative_external_discharge_volume_m3"][index]
        ),
        "flow_rate_m3_s": float(samples["flow_rate_m3_s"][index]),
    }


def summarize(result: SimulationResult) -> dict[str, Any]:
    samples = result.samples
    q = samples["flow_rate_m3_s"]
    momentum_flux = samples["outlet_momentum_flux_N"]
    pressure = samples["gas_pressure_abs_Pa"]
    line_mass = result.parameters.liquid_density_kg_m3 * result.initial_line_water_volume_m3
    initial_internal = result.initial_tank_water_volume_m3 + result.initial_line_water_volume_m3
    final_internal = result.stop_tank_water_volume_m3 + result.initial_line_water_volume_m3
    cumulative = samples["cumulative_external_discharge_volume_m3"][-1]
    exponent = result.parameters.polytropic_n
    gas_invariant = (
        pressure * samples["gas_volume_m3"] ** exponent
        if result.parameters.gas_mode == "sealed"
        else np.asarray([], dtype=float)
    )
    pressure_locations = {
        "pipe_side_transition_entry": "pressure_transition_entry_abs_Pa",
        "lumped_station_after_valve": "pressure_after_valve_abs_Pa",
    }
    pressure_thresholds = {
        "10_kPa_absolute": 10_000.0,
        "5_kPa_absolute": 5_000.0,
        "water_vapor_reference_20C_absolute": WATER_VAPOR_PRESSURE_SCREEN_20C_PA,
        "zero_absolute": 0.0,
    }
    pressure_events = {
        location: {
            name: _first_pressure_screen_event(samples, pressure_key, threshold)
            for name, threshold in pressure_thresholds.items()
        }
        for location, pressure_key in pressure_locations.items()
    }
    pressure_values = {
        location: samples[pressure_key] for location, pressure_key in pressure_locations.items()
    }
    combined_pressure_events = [
        (event["time_s"], location, threshold_name, event)
        for location, thresholds in pressure_events.items()
        for threshold_name, event in thresholds.items()
        if event is not None
        and threshold_name in {"water_vapor_reference_20C_absolute", "zero_absolute"}
    ]
    first_phase_completeness_event = (
        None
        if not combined_pressure_events
        else {
            "location": min(combined_pressure_events, key=lambda item: item[0])[1],
            "threshold": min(combined_pressure_events, key=lambda item: item[0])[2],
            **min(combined_pressure_events, key=lambda item: item[0])[3],
        }
    )
    pressure_history_below_vapor = any(
        np.any(values <= WATER_VAPOR_PRESSURE_SCREEN_20C_PA) for values in pressure_values.values()
    )
    pressure_history_at_or_below_zero = any(
        np.any(values <= 0.0) for values in pressure_values.values()
    )
    minimum_pressures = {
        location: {
            "pressure_abs_Pa": float(np.min(values)),
            "time_s": float(samples["time_s"][int(np.argmin(values))]),
        }
        for location, values in pressure_values.items()
    }
    crown_stop_reached = "gas-liquid interface reached" in result.stop_reason
    return {
        "stop_reason": result.stop_reason,
        "discharge_duration_s": result.stop_time_s,
        "initial_tank_water_volume_m3": result.initial_tank_water_volume_m3,
        "stop_tank_water_volume_m3": result.stop_tank_water_volume_m3,
        "external_discharged_volume_m3": float(cumulative),
        "external_discharged_mass_kg": float(cumulative * result.parameters.liquid_density_kg_m3),
        "initial_pipe_transition_water_mass_kg": line_mass,
        "initial_total_internal_water_mass_kg": initial_internal
        * result.parameters.liquid_density_kg_m3,
        "final_internal_water_mass_kg": final_internal * result.parameters.liquid_density_kg_m3,
        "peak_flow_rate_m3_s": float(np.max(q)),
        "peak_mass_flow_rate_kg_s": float(np.max(samples["flow_rate_kg_s"])),
        "peak_nozzle_velocity_m_s": float(np.max(samples["nozzle_velocity_m_s"])),
        "peak_outlet_momentum_flux_N": float(np.max(momentum_flux)),
        "outlet_momentum_impulse_N_s": float(np.trapezoid(momentum_flux, samples["time_s"])),
        "initial_gas_pressure_abs_Pa": float(pressure[0]),
        "final_gas_pressure_abs_Pa": float(pressure[-1]),
        "final_gas_temperature_K": float(samples["gas_temperature_K"][-1]),
        "minimum_gas_pressure_abs_Pa": float(np.min(pressure)),
        "maximum_component_pressure_drops_Pa": {
            "pipe_friction": float(np.max(samples["pressure_pipe_friction_Pa"])),
            "pipe_entrance": float(np.max(samples["pressure_pipe_entrance_Pa"])),
            "valve": float(np.max(samples["pressure_valve_Pa"])),
            "transition": float(np.max(samples["pressure_transition_Pa"])),
            "outlet_kinetic": float(np.max(samples["pressure_exit_kinetic_Pa"])),
        },
        "gas_pressure_ratio_final_to_initial": float(pressure[-1] / pressure[0]),
        "maximum_reynolds": float(np.max(samples["reynolds"])),
        "maximum_mass_balance_error_m3": result.max_mass_balance_error_m3,
        "maximum_relative_polytropic_invariant_drift": (
            float(np.max(np.abs(gas_invariant / gas_invariant[0] - 1.0)))
            if len(gas_invariant)
            else None
        ),
        "stop_condition_reached": "gas-liquid interface reached" in result.stop_reason,
        "pressure_screen": {
            "status": "screen only; does not modify or truncate the single-liquid integration",
            "pressure_locations": pressure_locations,
            "pressure_location_qualifications": {
                "pipe_side_transition_entry": "One-dimensional section-mean static pressure at the pipe-side entrance to the transition; it is not a local minimum within the transition.",
                "lumped_station_after_valve": "One-dimensional lumped static pressure after the scalar valve and upstream of the full pipe inertance/friction element; it is not a spatially resolved axial tap.",
            },
            "thresholds_absolute_Pa": pressure_thresholds,
            "water_vapor_reference_temperature_K": WATER_VAPOR_PRESSURE_SCREEN_TEMPERATURE_K,
            "water_vapor_reference_source": WATER_VAPOR_PRESSURE_SCREEN_SOURCE,
            "water_vapor_reference_url": "https://www.iapws.org/relguide/Supp-sat.html",
            "first_at_or_below_threshold_events": pressure_events,
            "first_phase_completeness_warning_event": first_phase_completeness_event,
            "minimum_static_pressures": minimum_pressures,
            "history_at_or_below_water_vapor_reference": bool(pressure_history_below_vapor),
            "history_at_or_below_zero_absolute": bool(pressure_history_at_or_below_zero),
            "pressure_history_qualification": (
                "The saved single-liquid pressure history reaches or falls below the approximate pure-water saturation-pressure screen. "
                "The reduced model continues to its separately reported geometric crown stop and omits vapor, gas ingestion, and cavity dynamics; this screen is not evidence of cavitation or a gas-breakthrough prediction."
                if pressure_history_below_vapor
                else "The saved endpoint pressures remain above the approximate pure-water saturation-pressure screen; this does not validate the omitted multiphase physics."
            ),
            "crown_stop_time_s": result.stop_time_s if crown_stop_reached else None,
            "integration_stop_time_s": result.stop_time_s,
            "crown_stop_reached": crown_stop_reached,
            "crown_stop_reason": result.stop_reason,
        },
    }
