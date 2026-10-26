"""Liquid-only quasi-1D discharge from one sealed tank into parallel branches.

For each branch j, the volume flow Q_j is integrated from the shared pressure
state using

    I_j dQ_j/dt = p_g(V_g) - p_amb + rho*g*(h - z_out,j) - sum(Delta p_j)
    I_j = rho * integral_branch(ds / A(s))
    dV_tank/dt = -sum_j Q_j,   V_g = V_tank,total - V_tank,water.

The sealed headspace follows p_g = p_g0*(V_g0/V_g)**n. Darcy-Weisbach friction
is integrated along user-specified sections. Entrance, scalar valve, and
transition K losses use the first circular-pipe velocity head; the outlet
kinetic head uses the terminal section area. Cross-sectional area and hydraulic
diameter vary linearly within a declared transition section. Its inertance is
therefore the exact integral for that *linear-area approximation*, not for the
actual ruled loft or a measured CAD flow path. The present revised preview
documents two separate bent feeds from each tank but labels their centerlines,
valves, and connectivity as assumptions; see
``results/runs/i4f-revised-dimensioned-cad-preview-v2-20261024T2030Z/preview-geometry.json``.
The broader provisional physical inputs are in ``experiments/i4f_baseline.json``.

The model assumes initially liquid-full branches and a well-mixed, uniform
headspace. It stops when the free surface reaches the highest intake crown or
when any branch would reverse. The latter stops the liquid-only integration
before outlet air ingestion; there is no mixed-phase or gas-purge closure.
Tank pressure at an intake elevation is a hydrostatic reservoir estimate, not
the local flowing pressure, and omits entrance acceleration. The drive also
omits the legacy single-line model's free-surface kinetic-head correction.
This network distributes inertance and Darcy friction across its sampled
sections; the legacy model lumps pipe/transition inertia and omits
transition-wall friction. Agreement of the scalar midpoint kernel therefore
does not imply trajectory identity for unlike geometries.
The pressure/state equations are a diagnostic reduced model, not an exact
reproduction of the unknown valve disk, bend profile, internal tank ports, or
loft geometry. SI units are used throughout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import copysign, isfinite, log, pi

import numpy as np

from aerial_drop.i4f_reduced import (
    R_AIR_J_KG_K,
    R_CO2_J_KG_K,
    darcy_friction_factor,
    gas_state,
    tank_level_z_m,
    tank_volume_at_level_m3,
)

_GAUSS_X, _GAUSS_W = np.polynomial.legendre.leggauss(8)
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class TankProperties:
    """One cylindrical tank; ``fill_fraction`` is tank liquid volume at t=0."""

    tank_axis: str
    tank_diameter_m: float
    tank_length_m: float
    tank_center_z_m: float
    fill_fraction: float

    def validate(self) -> None:
        if self.tank_axis not in {"horizontal", "vertical"}:
            raise ValueError("tank_axis must be 'horizontal' or 'vertical'")
        for name in ("tank_diameter_m", "tank_length_m"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(self.tank_center_z_m):
            raise ValueError("tank_center_z_m must be finite")
        if not isfinite(self.fill_fraction) or not 0 < self.fill_fraction < 1:
            raise ValueError("fill_fraction must lie strictly between zero and one")

    @property
    def tank_volume_m3(self) -> float:
        return pi * (self.tank_diameter_m / 2.0) ** 2 * self.tank_length_m


@dataclass(frozen=True)
class GasProperties:
    """Sealed, uniform polytropic gas headspace; pressure is absolute."""

    gas_kind: str
    initial_pressure_abs_Pa: float
    ambient_pressure_Pa: float
    initial_temperature_K: float
    polytropic_n: float

    def validate(self) -> None:
        if self.gas_kind not in {"air", "co2"}:
            raise ValueError("gas_kind must be 'air' or 'co2'")
        for name in (
            "initial_pressure_abs_Pa",
            "ambient_pressure_Pa",
            "initial_temperature_K",
            "polytropic_n",
        ):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

    # These aliases let this explicit headspace object use the existing public
    # gas_state helper, whose accepted object is otherwise ModelParameters.
    @property
    def gas_mode(self) -> str:
        return "sealed"

    @property
    def initial_gas_pressure_Pa(self) -> float:
        return self.initial_pressure_abs_Pa

    @property
    def gas_temperature_K(self) -> float:
        return self.initial_temperature_K

    @property
    def gas_specific_constant_J_kg_K(self) -> float:
        return R_AIR_J_KG_K if self.gas_kind == "air" else R_CO2_J_KG_K


@dataclass(frozen=True)
class LiquidProperties:
    density_kg_m3: float
    dynamic_viscosity_Pa_s: float
    gravity_m_s2: float = 9.81

    def validate(self) -> None:
        for name in ("density_kg_m3", "dynamic_viscosity_Pa_s", "gravity_m_s2"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class HydraulicSection:
    """Straight section or linear-area equivalent, dimensions in SI units.

    A and hydraulic diameter are interpolated linearly from start to end. For a
    constant circular pipe, use equal start/end areas and equal hydraulic
    diameters. The trapezoidal section volume is exact under this area model.
    """

    name: str
    length_m: float
    area_start_m2: float
    area_end_m2: float
    hydraulic_diameter_start_m: float
    hydraulic_diameter_end_m: float
    roughness_m: float = 0.0

    def validate(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError("section name must contain only letters, digits, and underscores")
        for name in (
            "length_m",
            "area_start_m2",
            "area_end_m2",
            "hydraulic_diameter_start_m",
            "hydraulic_diameter_end_m",
        ):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(self.roughness_m) or self.roughness_m < 0:
            raise ValueError("roughness_m must be finite and nonnegative")

    @property
    def volume_m3(self) -> float:
        return self.length_m * (self.area_start_m2 + self.area_end_m2) / 2.0

    @property
    def inertance_integral_m(self) -> float:
        """Return integral(ds/A), with units 1/m."""
        a0, a1 = self.area_start_m2, self.area_end_m2
        if abs(a1 - a0) <= 1e-12 * max(a0, a1):
            return self.length_m / a0
        return self.length_m * log(a1 / a0) / (a1 - a0)


@dataclass(frozen=True)
class BranchParameters:
    """One outlet branch from a common tank to ambient pressure.

    ``intake_upper_edge_z_m`` can specify a geometry-derived vertical upper
    edge for an oblique tank-wall opening. If omitted, the model uses the
    center elevation plus half the circular intake diameter.
    """

    name: str
    intake_center_z_m: float
    intake_diameter_m: float
    outlet_center_z_m: float
    sections: tuple[HydraulicSection, ...]
    valve_Cd: float
    valve_opening_time_s: float
    valve_opening_law: str = "smoothstep"
    valve_minimum_effective_opening: float = 0.0
    entrance_loss_K: float = 0.0
    transition_loss_K: float = 0.0
    intake_upper_edge_z_m: float | None = None

    def validate(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError("branch name must contain only letters, digits, and underscores")
        if not isfinite(self.intake_center_z_m) or not isfinite(self.outlet_center_z_m):
            raise ValueError("branch intake and outlet elevations must be finite")
        if self.intake_upper_edge_z_m is not None and (
            not isfinite(self.intake_upper_edge_z_m)
            or self.intake_upper_edge_z_m <= self.intake_center_z_m
        ):
            raise ValueError("intake_upper_edge_z_m must be finite and above the intake center")
        for name in ("intake_diameter_m", "valve_Cd"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(self.valve_opening_time_s) or self.valve_opening_time_s < 0:
            raise ValueError("valve_opening_time_s must be finite and nonnegative")
        if self.valve_opening_law not in {"linear", "smoothstep"}:
            raise ValueError("valve_opening_law must be 'linear' or 'smoothstep'")
        if not isfinite(self.valve_minimum_effective_opening) or not (
            0 <= self.valve_minimum_effective_opening <= 1
        ):
            raise ValueError("valve_minimum_effective_opening must lie in [0, 1]")
        for name in ("entrance_loss_K", "transition_loss_K"):
            value = getattr(self, name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not self.sections:
            raise ValueError("each branch must declare at least one hydraulic section")
        section_names = [section.name for section in self.sections]
        if len(section_names) != len(set(section_names)):
            raise ValueError(f"section names must be unique within branch {self.name}")
        for section in self.sections:
            section.validate()

    @property
    def inertance_integral_m(self) -> float:
        return sum(section.inertance_integral_m for section in self.sections)

    def inertance_kg_m4(self, liquid: LiquidProperties) -> float:
        return liquid.density_kg_m3 * self.inertance_integral_m

    @property
    def initial_line_water_volume_m3(self) -> float:
        return sum(section.volume_m3 for section in self.sections)

    @property
    def intake_crown_z_m(self) -> float:
        if self.intake_upper_edge_z_m is not None:
            return self.intake_upper_edge_z_m
        return self.intake_center_z_m + self.intake_diameter_m / 2.0

    @property
    def reference_area_m2(self) -> float:
        """Local-K and valve reference area: first pipe-section area."""
        return self.sections[0].area_start_m2

    @property
    def outlet_area_m2(self) -> float:
        return self.sections[-1].area_end_m2


@dataclass(frozen=True)
class NetworkParameters:
    tank: TankProperties
    gas: GasProperties
    liquid: LiquidProperties
    branches: tuple[BranchParameters, ...]

    def validate(self) -> None:
        self.tank.validate()
        self.gas.validate()
        self.liquid.validate()
        if not self.branches:
            raise ValueError("at least one outlet branch is required")
        names = [branch.name for branch in self.branches]
        if len(names) != len(set(names)):
            raise ValueError("branch names must be unique")
        for branch in self.branches:
            branch.validate()


@dataclass(frozen=True)
class NetworkSimulationResult:
    parameters: NetworkParameters
    samples: dict[str, np.ndarray]
    stop_reason: str
    stop_time_s: float
    initial_tank_water_volume_m3: float
    initial_gas_volume_m3: float
    initial_line_water_volume_m3: float
    stop_tank_water_volume_m3: float
    max_mass_balance_error_m3: float


def branch_inertial_midpoint_step(
    old_flow_m3_s: float,
    time_step_s: float,
    inertance_kg_m4: float,
    pressure_drive_Pa: float,
    linear_resistance_Pa_s_m3: float,
    quadratic_resistance_Pa_s2_m6: float,
) -> tuple[float, float]:
    """Advance signed ``I dQ/dt = drive - R1 Q - R2 Q|Q|`` implicitly.

    This generic midpoint kernel is useful for analytic limits and comparison
    with the legacy single-line kernel. Network branches use the same midpoint
    balance with a Darcy-based nonlinear pressure-loss callback.
    """
    values = (
        old_flow_m3_s,
        pressure_drive_Pa,
        linear_resistance_Pa_s_m3,
        quadratic_resistance_Pa_s2_m6,
    )
    if not all(isfinite(v) for v in values):
        raise ValueError("flow, drive, and resistance values must be finite")
    if time_step_s <= 0 or inertance_kg_m4 <= 0:
        raise ValueError("time step and inertance must be positive")
    if linear_resistance_Pa_s_m3 < 0 or quadratic_resistance_Pa_s2_m6 < 0:
        raise ValueError("resistances must be nonnegative")

    def residual(mid_flow: float) -> float:
        return (
            2.0 * inertance_kg_m4 / time_step_s * (mid_flow - old_flow_m3_s)
            + linear_resistance_Pa_s_m3 * mid_flow
            + quadratic_resistance_Pa_s2_m6 * mid_flow * abs(mid_flow)
            - pressure_drive_Pa
        )

    qscale = abs(old_flow_m3_s) + abs(pressure_drive_Pa) * time_step_s / inertance_kg_m4
    radius = max(qscale, 1e-12)
    low, high = old_flow_m3_s - radius, old_flow_m3_s + radius
    for _ in range(100):
        if residual(low) <= 0 and residual(high) >= 0:
            break
        radius *= 2.0
        low, high = old_flow_m3_s - radius, old_flow_m3_s + radius
    else:
        raise RuntimeError("could not bracket signed midpoint flow")
    for _ in range(64):
        mid = (low + high) / 2.0
        fmid = residual(mid)
        if fmid > 0:
            high = mid
        else:
            low = mid
    midpoint_flow = (low + high) / 2.0
    next_flow = 2.0 * midpoint_flow - old_flow_m3_s
    return midpoint_flow, next_flow


def _valve_opening(branch: BranchParameters, time_s: float) -> float:
    if branch.valve_opening_time_s == 0 or time_s >= branch.valve_opening_time_s:
        command = 1.0
    else:
        x = min(1.0, max(0.0, time_s / branch.valve_opening_time_s))
        command = x if branch.valve_opening_law == "linear" else x * x * (3.0 - 2.0 * x)
    return max(branch.valve_minimum_effective_opening, command)


def _section_friction_drop_Pa(
    section: HydraulicSection,
    flow_rate_m3_s: float,
    liquid: LiquidProperties,
) -> float:
    """Signed Darcy-Weisbach loss integrated through the section profile."""
    if flow_rate_m3_s == 0:
        return 0.0
    q_abs = abs(flow_rate_m3_s)
    if (
        section.area_start_m2 == section.area_end_m2
        and section.hydraulic_diameter_start_m == section.hydraulic_diameter_end_m
    ):
        area = section.area_start_m2
        diameter = section.hydraulic_diameter_start_m
        velocity = q_abs / area
        reynolds = liquid.density_kg_m3 * velocity * diameter / liquid.dynamic_viscosity_Pa_s
        darcy = darcy_friction_factor(reynolds, section.roughness_m / diameter)
        drop = section.length_m * darcy / diameter * 0.5 * liquid.density_kg_m3 * velocity**2
        return copysign(drop, flow_rate_m3_s)
    integral = 0.0
    for xi, wi in zip(_GAUSS_X, _GAUSS_W, strict=True):
        f = (float(xi) + 1.0) / 2.0
        area = section.area_start_m2 + f * (section.area_end_m2 - section.area_start_m2)
        diameter = section.hydraulic_diameter_start_m + f * (
            section.hydraulic_diameter_end_m - section.hydraulic_diameter_start_m
        )
        velocity = q_abs / area
        reynolds = liquid.density_kg_m3 * velocity * diameter / liquid.dynamic_viscosity_Pa_s
        f_darcy = darcy_friction_factor(reynolds, section.roughness_m / diameter)
        integrand = f_darcy / diameter * 0.5 * liquid.density_kg_m3 * velocity**2
        integral += float(wi) * integrand
    return copysign(section.length_m * integral / 2.0, flow_rate_m3_s)


def _branch_loss_components(
    branch: BranchParameters,
    liquid: LiquidProperties,
    flow_rate_m3_s: float,
    opening_fraction: float,
) -> dict[str, float]:
    sign = 0.0 if flow_rate_m3_s == 0 else copysign(1.0, flow_rate_m3_s)
    velocity_head_ref = (
        0.5 * liquid.density_kg_m3 * (flow_rate_m3_s / branch.reference_area_m2) ** 2
    )
    friction_by_section = {
        f"pressure_friction_{section.name}_Pa": _section_friction_drop_Pa(
            section, flow_rate_m3_s, liquid
        )
        for section in branch.sections
    }
    friction = sum(friction_by_section.values())
    valve_k = (
        float("inf") if opening_fraction <= 0 else 1.0 / (branch.valve_Cd * opening_fraction) ** 2
    )
    valve = sign * velocity_head_ref * valve_k if isfinite(valve_k) else 0.0
    entrance = sign * velocity_head_ref * branch.entrance_loss_K
    transition = sign * velocity_head_ref * branch.transition_loss_K
    outlet_kinetic = (
        sign * 0.5 * liquid.density_kg_m3 * (flow_rate_m3_s / branch.outlet_area_m2) ** 2
    )
    return {
        **friction_by_section,
        "pressure_friction_Pa": friction,
        "pressure_valve_Pa": valve,
        "pressure_entrance_Pa": entrance,
        "pressure_transition_Pa": transition,
        "pressure_outlet_kinetic_Pa": outlet_kinetic,
        "valve_K_pipe_velocity_reference": valve_k,
        "velocity_head_reference_Pa": velocity_head_ref,
    }


def _solve_branch_midpoint(
    branch: BranchParameters,
    liquid: LiquidProperties,
    old_flow_m3_s: float,
    time_step_s: float,
    inertance_kg_m4: float,
    pressure_drive_Pa: float,
    opening_fraction: float,
) -> tuple[float, float]:
    if opening_fraction <= 0:
        if abs(old_flow_m3_s) > 1e-13:
            raise ValueError(
                "instant valve closure under nonzero flow is outside this reduced model"
            )
        return 0.0, 0.0

    def residual(mid_flow: float) -> float:
        losses = _branch_loss_components(branch, liquid, mid_flow, opening_fraction)
        return (
            2.0 * inertance_kg_m4 / time_step_s * (mid_flow - old_flow_m3_s)
            + losses["pressure_friction_Pa"]
            + losses["pressure_valve_Pa"]
            + losses["pressure_entrance_Pa"]
            + losses["pressure_transition_Pa"]
            + losses["pressure_outlet_kinetic_Pa"]
            - pressure_drive_Pa
        )

    scale = abs(old_flow_m3_s) + abs(pressure_drive_Pa) * time_step_s / inertance_kg_m4
    radius = max(scale, 1e-12)
    low, high = old_flow_m3_s - radius, old_flow_m3_s + radius
    for _ in range(100):
        if residual(low) <= 0 and residual(high) >= 0:
            break
        radius *= 2.0
        low, high = old_flow_m3_s - radius, old_flow_m3_s + radius
    else:
        raise RuntimeError(f"could not bracket branch flow for {branch.name}")
    for _ in range(52):
        mid = (low + high) / 2.0
        if residual(mid) > 0:
            high = mid
        else:
            low = mid
    q_mid = (low + high) / 2.0
    return q_mid, 2.0 * q_mid - old_flow_m3_s


def _solve_network_step(
    parameters: NetworkParameters,
    initial_gas_volume_m3: float,
    tank_water_volume_m3: float,
    old_flows_m3_s: np.ndarray,
    time_s: float,
    time_step_s: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    branches = parameters.branches
    liquid = parameters.liquid
    rho = liquid.density_kg_m3
    mids = old_flows_m3_s.copy()
    step_diagnostics: dict[str, float] = {}
    for _ in range(80):
        water_mid = tank_water_volume_m3 - time_step_s * float(np.sum(mids)) / 2.0
        if water_mid <= 0 or water_mid >= parameters.tank.tank_volume_m3:
            raise RuntimeError("midpoint tank inventory left physical bounds")
        level_mid = tank_level_z_m(parameters.tank, water_mid)
        gas_volume_mid = parameters.tank.tank_volume_m3 - water_mid
        p_gas_mid, t_gas_mid, _ = gas_state(parameters.gas, initial_gas_volume_m3, gas_volume_mid)
        target_mids = np.empty_like(mids)
        step_diagnostics = {
            "midpoint_tank_water_volume_m3": water_mid,
            "midpoint_tank_level_z_m": level_mid,
            "midpoint_gas_volume_m3": gas_volume_mid,
            "midpoint_gas_pressure_abs_Pa": p_gas_mid,
            "midpoint_gas_temperature_K": t_gas_mid,
        }
        for index, branch in enumerate(branches):
            drive = (
                p_gas_mid
                - parameters.gas.ambient_pressure_Pa
                + rho * liquid.gravity_m_s2 * (level_mid - branch.outlet_center_z_m)
            )
            open_fraction = _valve_opening(branch, time_s + time_step_s / 2.0)
            qmid, _ = _solve_branch_midpoint(
                branch,
                liquid,
                float(old_flows_m3_s[index]),
                time_step_s,
                branch.inertance_kg_m4(liquid),
                drive,
                open_fraction,
            )
            target_mids[index] = qmid
            step_diagnostics[f"midpoint_pressure_drive_{branch.name}_Pa"] = drive
            step_diagnostics[f"midpoint_opening_{branch.name}"] = open_fraction
        difference = float(np.max(np.abs(target_mids - mids)))
        scale = max(1e-3, float(np.max(np.abs(target_mids))))
        if difference <= 2e-11 + 2e-9 * scale:
            mids = target_mids
            break
        mids = 0.5 * mids + 0.5 * target_mids
    else:
        raise RuntimeError("shared-tank/branch midpoint iteration did not converge")
    next_flows = 2.0 * mids - old_flows_m3_s
    return mids, next_flows, step_diagnostics


def _diagnostic_row(
    parameters: NetworkParameters,
    initial_gas_volume_m3: float,
    time_s: float,
    tank_water_volume_m3: float,
    flows_m3_s: np.ndarray,
    cumulative_branch_volumes_m3: np.ndarray,
    cumulative_total_volume_m3: float,
    midpoint: dict[str, float] | None,
    old_flows_m3_s: np.ndarray | None,
    step_s: float | None,
) -> dict[str, float]:
    rho = parameters.liquid.density_kg_m3
    level = tank_level_z_m(parameters.tank, tank_water_volume_m3)
    gas_volume = parameters.tank.tank_volume_m3 - tank_water_volume_m3
    p_gas, t_gas, gas_mass = gas_state(parameters.gas, initial_gas_volume_m3, gas_volume)
    line_water_volume = sum(branch.initial_line_water_volume_m3 for branch in parameters.branches)
    row: dict[str, float] = {
        "time_s": time_s,
        "tank_water_volume_m3": tank_water_volume_m3,
        "line_water_volume_m3": line_water_volume,
        "total_system_water_volume_including_discharge_m3": (
            tank_water_volume_m3 + line_water_volume + cumulative_total_volume_m3
        ),
        "total_system_water_balance_residual_m3": (
            parameters.tank.fill_fraction * parameters.tank.tank_volume_m3
            + line_water_volume
            - tank_water_volume_m3
            - line_water_volume
            - cumulative_total_volume_m3
        ),
        "tank_free_surface_level_z_m": level,
        "gas_volume_m3": gas_volume,
        "gas_pressure_abs_Pa": p_gas,
        "gas_temperature_K": t_gas,
        "sealed_gas_mass_kg": gas_mass,
        "total_flow_rate_m3_s": float(np.sum(flows_m3_s)),
        "total_flow_rate_kg_s": rho * float(np.sum(flows_m3_s)),
        "cumulative_discharge_volume_m3": cumulative_total_volume_m3,
        "cumulative_discharge_mass_kg": rho * cumulative_total_volume_m3,
        "cumulative_water_balance_residual_m3": (
            parameters.tank.fill_fraction * parameters.tank.tank_volume_m3
            - tank_water_volume_m3
            - cumulative_total_volume_m3
        ),
        "highest_intake_crown_z_m": max(branch.intake_crown_z_m for branch in parameters.branches),
    }
    for i, branch in enumerate(parameters.branches):
        q = float(flows_m3_s[i])
        opening = _valve_opening(branch, time_s)
        drive = (
            p_gas
            - parameters.gas.ambient_pressure_Pa
            + rho * parameters.liquid.gravity_m_s2 * (level - branch.outlet_center_z_m)
        )
        p_intake = p_gas + rho * parameters.liquid.gravity_m_s2 * (level - branch.intake_center_z_m)
        parts = _branch_loss_components(branch, parameters.liquid, q, opening)
        losses = (
            parts["pressure_friction_Pa"]
            + parts["pressure_valve_Pa"]
            + parts["pressure_entrance_Pa"]
            + parts["pressure_transition_Pa"]
            + parts["pressure_outlet_kinetic_Pa"]
        )
        row.update(
            {
                f"flow_rate_{branch.name}_m3_s": q,
                f"flow_rate_{branch.name}_kg_s": rho * q,
                f"cumulative_discharge_{branch.name}_volume_m3": float(
                    cumulative_branch_volumes_m3[i]
                ),
                f"intake_crown_{branch.name}_z_m": branch.intake_crown_z_m,
                f"tank_hydrostatic_pressure_at_intake_elevation_{branch.name}_abs_Pa": p_intake,
                f"outlet_pressure_{branch.name}_abs_Pa": parameters.gas.ambient_pressure_Pa,
                f"pressure_drive_{branch.name}_Pa": drive,
                f"pressure_drive_minus_loss_sum_{branch.name}_Pa": drive - losses,
                f"branch_inertance_{branch.name}_kg_m4": branch.inertance_kg_m4(parameters.liquid),
                f"opening_{branch.name}": opening,
                f"momentum_flux_{branch.name}_N": rho * q * q / branch.outlet_area_m2,
            }
        )
        for key, value in parts.items():
            row[f"{key}_{branch.name}"] = value
        if midpoint is None or old_flows_m3_s is None or step_s is None:
            row[f"last_step_midpoint_momentum_residual_{branch.name}_Pa"] = float("nan")
            continue
        q_mid = (float(old_flows_m3_s[i]) + q) / 2.0
        a_mid = (q - float(old_flows_m3_s[i])) / step_s
        p_drive_mid = midpoint[f"midpoint_pressure_drive_{branch.name}_Pa"]
        open_mid = midpoint[f"midpoint_opening_{branch.name}"]
        mid_parts = _branch_loss_components(branch, parameters.liquid, q_mid, open_mid)
        p_inertia_mid = branch.inertance_kg_m4(parameters.liquid) * a_mid
        balance_mid = (
            p_drive_mid
            - mid_parts["pressure_friction_Pa"]
            - mid_parts["pressure_valve_Pa"]
            - mid_parts["pressure_entrance_Pa"]
            - mid_parts["pressure_transition_Pa"]
            - mid_parts["pressure_outlet_kinetic_Pa"]
            - p_inertia_mid
        )
        row[f"last_step_midpoint_inertance_pressure_{branch.name}_Pa"] = p_inertia_mid
        row[f"last_step_midpoint_momentum_residual_{branch.name}_Pa"] = balance_mid
        for key, value in mid_parts.items():
            row[f"last_step_midpoint_{key}_{branch.name}"] = value
    return row


def simulate_parallel_branches(
    parameters: NetworkParameters,
    *,
    time_step_s: float = 1e-4,
    max_time_s: float = 10.0,
) -> NetworkSimulationResult:
    """Integrate shared-tank blowdown until intake-crown or flow-reversal event."""
    parameters.validate()
    if not isfinite(time_step_s) or time_step_s <= 0:
        raise ValueError("time_step_s must be finite and positive")
    if not isfinite(max_time_s) or max_time_s <= 0:
        raise ValueError("max_time_s must be finite and positive")

    tank = parameters.tank
    tank_volume = tank.tank_volume_m3
    water_initial = tank.fill_fraction * tank_volume
    gas_initial = tank_volume - water_initial
    stop_level = max(branch.intake_crown_z_m for branch in parameters.branches)
    stop_water = tank_volume_at_level_m3(tank, stop_level)
    initial_level = tank_level_z_m(tank, water_initial)
    if initial_level <= stop_level:
        raise ValueError("initial liquid surface is already at/below the highest intake crown")
    if not 0 <= stop_water < water_initial:
        raise ValueError("highest intake crown leaves no positive drainable tank inventory")

    time_s = 0.0
    water = water_initial
    flows = np.zeros(len(parameters.branches), dtype=float)
    cumulative_branch = np.zeros_like(flows)
    cumulative_total = 0.0
    line_volume = sum(branch.initial_line_water_volume_m3 for branch in parameters.branches)
    rows: list[dict[str, float]] = []
    rows.append(
        _diagnostic_row(
            parameters,
            gas_initial,
            time_s,
            water,
            flows,
            cumulative_branch,
            cumulative_total,
            None,
            None,
            None,
        )
    )
    stop_reason = "maximum model time reached before intake-crown event"

    while time_s < max_time_s:
        step = min(time_step_s, max_time_s - time_s)
        midpoint, next_flows, mid_diag = _solve_network_step(
            parameters, gas_initial, water, flows, time_s, step
        )
        reversed_indices = [i for i, q in enumerate(next_flows) if q < -1e-13]
        if reversed_indices:
            names = ", ".join(parameters.branches[i].name for i in reversed_indices)
            if any(flows[i] <= 1e-13 for i in reversed_indices):
                estimate = time_s
            else:
                estimates = [
                    time_s + step * flows[i] / (flows[i] - next_flows[i]) for i in reversed_indices
                ]
                estimate = min(estimates)
            stop_reason = (
                f"liquid-only integration stopped before predicted reverse flow in {names}; "
                f"approximate first reversal time {estimate:.9g} s"
            )
            break

        water_next = water - step * float(np.sum(midpoint))
        if water_next <= stop_water:
            low, high = 0.0, step
            final_mid = midpoint
            final_next = next_flows
            final_diag = mid_diag
            for _ in range(42):
                test_step = (low + high) / 2.0
                test_mid, test_next, test_diag = _solve_network_step(
                    parameters, gas_initial, water, flows, time_s, test_step
                )
                test_water = water - test_step * float(np.sum(test_mid))
                if test_water <= stop_water:
                    high = test_step
                    final_mid, final_next, final_diag = test_mid, test_next, test_diag
                else:
                    low = test_step
            final_step = high
            if final_step <= 1e-14:
                stop_reason = "highest intake crown already reached at the integration start"
                break
            final_total_delta = water - stop_water
            rates = final_mid.copy()
            branch_delta = final_step * rates
            # Assign the tiny root-finding remainder proportionally so the
            # event inventory closes exactly without altering branch flow.
            integrated_delta = float(np.sum(branch_delta))
            if integrated_delta > 0:
                branch_delta *= final_total_delta / integrated_delta
            cumulative_branch += branch_delta
            cumulative_total += final_total_delta
            water = stop_water
            time_s += final_step
            previous_flows = flows.copy()
            flows = final_next
            rows.append(
                _diagnostic_row(
                    parameters,
                    gas_initial,
                    time_s,
                    water,
                    flows,
                    cumulative_branch,
                    cumulative_total,
                    final_diag,
                    previous_flows,
                    final_step,
                )
            )
            stop_reason = "tank free surface reached the highest submerged-intake crown"
            break

        cumulative_branch += step * midpoint
        cumulative_total += step * float(np.sum(midpoint))
        previous_flows = flows.copy()
        water = water_next
        time_s += step
        flows = next_flows
        rows.append(
            _diagnostic_row(
                parameters,
                gas_initial,
                time_s,
                water,
                flows,
                cumulative_branch,
                cumulative_total,
                mid_diag,
                previous_flows,
                step,
            )
        )

    keys = dict.fromkeys(key for row in rows for key in row)
    samples = {
        key: np.asarray([row.get(key, float("nan")) for row in rows], dtype=float) for key in keys
    }
    balance = (
        water_initial
        + line_volume
        - samples["tank_water_volume_m3"]
        - line_volume
        - samples["cumulative_discharge_volume_m3"]
    )
    samples["total_water_balance_residual_m3"] = balance
    max_error = float(np.max(np.abs(balance)))
    return NetworkSimulationResult(
        parameters=parameters,
        samples=samples,
        stop_reason=stop_reason,
        stop_time_s=time_s,
        initial_tank_water_volume_m3=water_initial,
        initial_gas_volume_m3=gas_initial,
        initial_line_water_volume_m3=line_volume,
        stop_tank_water_volume_m3=water,
        max_mass_balance_error_m3=max_error,
    )


def summarize_network(result: NetworkSimulationResult) -> dict[str, object]:
    """Return compact assumptions, endpoint state, and ledger diagnostics."""
    sample = result.samples
    branch_summary = {}
    for branch in result.parameters.branches:
        name = branch.name
        qkey = f"flow_rate_{name}_m3_s"
        branch_summary[name] = {
            "intake_center_z_m": branch.intake_center_z_m,
            "intake_crown_z_m": branch.intake_crown_z_m,
            "outlet_center_z_m": branch.outlet_center_z_m,
            "initial_line_water_volume_m3": branch.initial_line_water_volume_m3,
            "inertance_kg_m4": branch.inertance_kg_m4(result.parameters.liquid),
            "flow_initial_m3_s": float(sample[qkey][0]),
            "flow_final_m3_s": float(sample[qkey][-1]),
            "max_flow_m3_s": float(np.max(sample[qkey])),
            "cumulative_discharge_volume_m3": float(
                sample[f"cumulative_discharge_{name}_volume_m3"][-1]
            ),
            "max_abs_last_step_midpoint_momentum_residual_Pa": float(
                np.nanmax(np.abs(sample[f"last_step_midpoint_momentum_residual_{name}_Pa"]))
            ),
            "endpoint_tank_hydrostatic_pressure_at_intake_elevation_abs_Pa": float(
                sample[f"tank_hydrostatic_pressure_at_intake_elevation_{name}_abs_Pa"][-1]
            ),
            "endpoint_pressure_drive_Pa": float(sample[f"pressure_drive_{name}_Pa"][-1]),
            "endpoint_pressure_drive_minus_loss_sum_Pa": float(
                sample[f"pressure_drive_minus_loss_sum_{name}_Pa"][-1]
            ),
            "endpoint_pressure_friction_Pa": float(sample[f"pressure_friction_Pa_{name}"][-1]),
            "endpoint_pressure_valve_Pa": float(sample[f"pressure_valve_Pa_{name}"][-1]),
            "endpoint_pressure_entrance_Pa": float(sample[f"pressure_entrance_Pa_{name}"][-1]),
            "endpoint_pressure_transition_Pa": float(sample[f"pressure_transition_Pa_{name}"][-1]),
            "endpoint_outlet_kinetic_pressure_Pa": float(
                sample[f"pressure_outlet_kinetic_Pa_{name}"][-1]
            ),
            "last_step_midpoint_inertance_pressure_Pa": float(
                sample[f"last_step_midpoint_inertance_pressure_{name}_Pa"][-1]
            ),
        }
    return {
        "stop_reason": result.stop_reason,
        "stop_time_s": result.stop_time_s,
        "sample_count": len(sample["time_s"]),
        "initial_tank_water_volume_m3": result.initial_tank_water_volume_m3,
        "initial_tank_fill_fraction": result.parameters.tank.fill_fraction,
        "stop_tank_water_volume_m3": result.stop_tank_water_volume_m3,
        "initial_gas_volume_m3": result.initial_gas_volume_m3,
        "initial_sealed_gas_mass_kg": float(sample["sealed_gas_mass_kg"][0]),
        "initial_line_water_volume_m3": result.initial_line_water_volume_m3,
        "initial_total_system_water_volume_m3": (
            result.initial_tank_water_volume_m3 + result.initial_line_water_volume_m3
        ),
        "total_cumulative_discharge_volume_m3": float(sample["cumulative_discharge_volume_m3"][-1]),
        "total_cumulative_discharge_mass_kg": float(sample["cumulative_discharge_mass_kg"][-1]),
        "initial_gas_pressure_abs_Pa": float(sample["gas_pressure_abs_Pa"][0]),
        "final_gas_pressure_abs_Pa": float(sample["gas_pressure_abs_Pa"][-1]),
        "maximum_abs_water_balance_residual_m3": result.max_mass_balance_error_m3,
        "branches": branch_summary,
        "limits": [
            "liquid-full branch assumption; branch line volume is reported as a constant inventory compartment",
            "single uniform sealed-gas pressure over the tank; no pre-existing dispersed gas",
            "stops at highest branch intake crown or before predicted reverse flow/air ingestion",
            "linear-area transition and sampled path inertance are approximations to the actual routed/ruled geometry",
            "tank hydrostatic intake pressure is an elevation-based reservoir estimate rather than a flowing tap pressure; the legacy free-surface kinetic-head term is omitted",
            "network section friction/inertance differ from the legacy lumped transition closure; equivalence is only checked in a simple constant-area limit",
            "scalar valve/entrance/transition coefficients do not resolve disk, bend, or separated-flow losses",
            "no cavitation, vapor, gas entrainment, mixed discharge, or nozzle-sheet model",
        ],
    }
