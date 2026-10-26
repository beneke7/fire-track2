"""Moving-front, vented-air 1-D filling model for provisional I4F branch routes.

This module extends the physical objects used by ``i4f_reduced_network`` but
leaves that frozen full-liquid model unchanged. Water starts in the tank and
in an explicitly specified upstream branch prefix ending at the valve seat;
the downstream route starts air-filled. Each branch carries a single rigid,
full-bore liquid front. The gas ahead of the front is assigned ambient static
pressure as a declared approximation, with dry-path Mach and friction-loss
screens reported at every output sample. That approximation does not model
stratification, pockets, water hammer, or detailed valve flow.

For a wetted path from the tank connection to a moving front, Euler's equation
integrates to

    p_g - p_front + rho*g*(z_tank_level-z_front)
      = rho*integral(ds/A)*dQ/dt + rho*u_front**2/2 + sum(losses).

The front kinetic term is the convective endpoint term after applying the
large-reservoir Bernoulli condition at the tank connection. Entrance and valve
losses remain separate pressure jumps and are not included in that term.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log, sqrt

import numpy as np

from aerial_drop.i4f_reduced import (
    R_AIR_J_KG_K,
    darcy_friction_factor,
    gas_state,
    tank_level_z_m,
    tank_volume_at_level_m3,
)
from aerial_drop.i4f_reduced_network import (
    BranchParameters,
    GasProperties,
    HydraulicSection,
    LiquidProperties,
    NetworkParameters,
    TankProperties,
    _section_friction_drop_Pa,
    _valve_opening,
)

_GAUSS4_X, _GAUSS4_W = np.polynomial.legendre.leggauss(4)


@dataclass(frozen=True)
class FillingBranch:
    """A full provisional branch path plus its elevations and initial wet prefix.

    ``elevation_samples_m`` has one value per section boundary, starting at
    the tank-side path origin and ending at the mouth. Section area and
    hydraulic diameter vary linearly as in ``HydraulicSection``; elevation is
    linearly interpolated over the same section. ``initial_front_s_m`` is the
    valve-seat location measured along the supplied path from that origin.
    It is an assumed effective seat coordinate when the real seat is unknown.
    """

    branch: BranchParameters
    elevation_samples_m: tuple[float, ...]
    initial_front_s_m: float
    transition_start_s_m: float | None = None
    transition_end_s_m: float | None = None
    air_minor_loss_K: float | None = None
    elevation_profile_s_m: tuple[float, ...] = ()
    elevation_profile_z_m: tuple[float, ...] = ()

    def validate(self) -> None:
        self.branch.validate()
        if len(self.elevation_samples_m) != len(self.branch.sections) + 1:
            raise ValueError("elevation_samples_m must contain one value per section boundary")
        if not all(isfinite(value) for value in self.elevation_samples_m):
            raise ValueError("elevation samples must be finite")
        if bool(self.elevation_profile_s_m) != bool(self.elevation_profile_z_m):
            raise ValueError("elevation profile stations and elevations must be supplied together")
        if self.elevation_profile_s_m:
            if len(self.elevation_profile_s_m) != len(self.elevation_profile_z_m):
                raise ValueError("elevation profile station and elevation arrays must align")
            if len(self.elevation_profile_s_m) < 2:
                raise ValueError("an elevation profile needs at least two stations")
            if not all(
                isfinite(value)
                for value in (*self.elevation_profile_s_m, *self.elevation_profile_z_m)
            ):
                raise ValueError("elevation profile values must be finite")
            if (
                abs(self.elevation_profile_s_m[0]) > 1e-10
                or abs(self.elevation_profile_s_m[-1] - self.length_m) > 1e-8
            ):
                raise ValueError("elevation profile must span the full branch path")
            if any(
                right <= left
                for left, right in zip(
                    self.elevation_profile_s_m[:-1], self.elevation_profile_s_m[1:], strict=True
                )
            ):
                raise ValueError("elevation profile stations must increase strictly")
        if not isfinite(self.initial_front_s_m) or not 0 <= self.initial_front_s_m <= self.length_m:
            raise ValueError("initial_front_s_m must lie on the branch path")
        if self.transition_start_s_m is not None and not (
            0 <= self.transition_start_s_m <= self.length_m
        ):
            raise ValueError("transition_start_s_m must lie on the branch")
        if self.transition_end_s_m is not None and not (
            0 <= self.transition_end_s_m <= self.length_m
        ):
            raise ValueError("transition_end_s_m must lie on the branch")
        if (
            self.transition_start_s_m is not None
            and self.transition_end_s_m is not None
            and self.transition_end_s_m < self.transition_start_s_m
        ):
            raise ValueError("transition_end_s_m cannot precede transition_start_s_m")
        if self.branch.transition_loss_K > 0 and (
            self.transition_start_s_m is None or self.transition_end_s_m is None
        ):
            raise ValueError("a nonzero transition loss requires its start and end locations")
        if self.air_minor_loss_K is not None and (
            not isfinite(self.air_minor_loss_K) or self.air_minor_loss_K < 0
        ):
            raise ValueError("air_minor_loss_K must be finite and nonnegative")

    @property
    def length_m(self) -> float:
        return sum(section.length_m for section in self.branch.sections)

    @property
    def initial_wet_volume_m3(self) -> float:
        return self.volume_to_s(self.initial_front_s_m)

    @property
    def full_wet_volume_m3(self) -> float:
        return sum(section.volume_m3 for section in self.branch.sections)

    @property
    def full_inertance_integral_m(self) -> float:
        return self.branch.inertance_integral_m

    def _section_starts(self) -> tuple[float, ...]:
        starts: list[float] = []
        cumulative = 0.0
        for section in self.branch.sections:
            starts.append(cumulative)
            cumulative += section.length_m
        return tuple(starts)

    def area_at_s(self, s_m: float) -> float:
        index, local = self._section_at(s_m)
        section = self.branch.sections[index]
        fraction = local / section.length_m
        return section.area_start_m2 + fraction * (section.area_end_m2 - section.area_start_m2)

    def diameter_at_s(self, s_m: float) -> float:
        index, local = self._section_at(s_m)
        section = self.branch.sections[index]
        fraction = local / section.length_m
        return section.hydraulic_diameter_start_m + fraction * (
            section.hydraulic_diameter_end_m - section.hydraulic_diameter_start_m
        )

    def elevation_at_s(self, s_m: float) -> float:
        if self.elevation_profile_s_m:
            return float(
                np.interp(
                    min(max(float(s_m), 0.0), self.length_m),
                    self.elevation_profile_s_m,
                    self.elevation_profile_z_m,
                )
            )
        index, local = self._section_at(s_m)
        section = self.branch.sections[index]
        fraction = local / section.length_m
        return self.elevation_samples_m[index] + fraction * (
            self.elevation_samples_m[index + 1] - self.elevation_samples_m[index]
        )

    def volume_to_s(self, s_m: float) -> float:
        """Return the centerline-area integral from route origin to ``s_m``."""
        s = min(max(float(s_m), 0.0), self.length_m)
        total = 0.0
        for start, section in zip(self._section_starts(), self.branch.sections, strict=True):
            local = min(max(s - start, 0.0), section.length_m)
            if local <= 0:
                continue
            slope = (section.area_end_m2 - section.area_start_m2) / section.length_m
            total += section.area_start_m2 * local + 0.5 * slope * local**2
            if local < section.length_m:
                break
        return total

    def inertance_integral_to_s(self, s_m: float) -> float:
        """Return ``integral(ds/A)`` from route origin to ``s_m`` in m^-1."""
        s = min(max(float(s_m), 0.0), self.length_m)
        total = 0.0
        for start, section in zip(self._section_starts(), self.branch.sections, strict=True):
            local = min(max(s - start, 0.0), section.length_m)
            if local <= 0:
                continue
            a0 = section.area_start_m2
            slope = (section.area_end_m2 - a0) / section.length_m
            a_local = a0 + slope * local
            if abs(slope) <= 1e-14 * max(a0, a_local):
                total += local / a0
            else:
                total += log(a_local / a0) / slope
            if local < section.length_m:
                break
        return total

    def s_from_volume(self, volume_m3: float) -> float:
        """Invert ``volume_to_s`` on a monotone positive-area route."""
        target = min(max(float(volume_m3), 0.0), self.full_wet_volume_m3)
        if target <= 0:
            return 0.0
        cumulative = 0.0
        for start, section in zip(self._section_starts(), self.branch.sections, strict=True):
            section_volume = section.volume_m3
            if target > cumulative + section_volume:
                cumulative += section_volume
                continue
            remaining = target - cumulative
            slope = (section.area_end_m2 - section.area_start_m2) / section.length_m
            if abs(slope) <= 1e-14 * section.area_start_m2:
                local = remaining / section.area_start_m2
            else:
                discriminant = section.area_start_m2**2 + 2.0 * slope * remaining
                local = 2.0 * remaining / (section.area_start_m2 + sqrt(discriminant))
            return start + min(max(local, 0.0), section.length_m)
        return self.length_m

    def wet_sections(self, front_s_m: float) -> tuple[HydraulicSection, ...]:
        """Return geometry sections clipped to the current wetted prefix."""
        front = min(max(float(front_s_m), 0.0), self.length_m)
        result: list[HydraulicSection] = []
        for start, section in zip(self._section_starts(), self.branch.sections, strict=True):
            length = min(max(front - start, 0.0), section.length_m)
            if length <= 0:
                break
            fraction = length / section.length_m
            area_end = section.area_start_m2 + fraction * (
                section.area_end_m2 - section.area_start_m2
            )
            diameter_end = section.hydraulic_diameter_start_m + fraction * (
                section.hydraulic_diameter_end_m - section.hydraulic_diameter_start_m
            )
            result.append(
                HydraulicSection(
                    name=f"{section.name}_wet",
                    length_m=length,
                    area_start_m2=section.area_start_m2,
                    area_end_m2=area_end,
                    hydraulic_diameter_start_m=section.hydraulic_diameter_start_m,
                    hydraulic_diameter_end_m=diameter_end,
                    roughness_m=section.roughness_m,
                )
            )
            if length < section.length_m:
                break
        return tuple(result)

    def _section_at(self, s_m: float) -> tuple[int, float]:
        s = min(max(float(s_m), 0.0), self.length_m)
        starts = self._section_starts()
        for index, (start, section) in enumerate(zip(starts, self.branch.sections, strict=True)):
            if s <= start + section.length_m or index == len(starts) - 1:
                return index, min(max(s - start, 0.0), section.length_m)
        raise RuntimeError("route section lookup failed")


@dataclass(frozen=True)
class FillingNetworkParameters:
    """Shared tank/headspace state and initially air-filled branches."""

    network: NetworkParameters
    branches: tuple[FillingBranch, ...]
    air_temperature_K: float = 293.15
    air_gamma: float = 1.4
    max_screened_air_mach: float = 0.1
    max_screened_air_loss_fraction: float = 0.05

    @property
    def tank(self) -> TankProperties:
        return self.network.tank

    @property
    def gas(self) -> GasProperties:
        return self.network.gas

    @property
    def liquid(self) -> LiquidProperties:
        return self.network.liquid

    def validate(self) -> None:
        self.network.validate()
        if len(self.branches) != len(self.network.branches):
            raise ValueError("each physical network branch needs a filling path")
        if tuple(item.branch.name for item in self.branches) != tuple(
            item.name for item in self.network.branches
        ):
            raise ValueError("filling branches must align with network branch names and order")
        for branch in self.branches:
            branch.validate()
        for name in ("air_temperature_K", "air_gamma", "max_screened_air_mach"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(self.max_screened_air_loss_fraction) or not (
            0 < self.max_screened_air_loss_fraction < 1
        ):
            raise ValueError(
                "max_screened_air_loss_fraction must lie strictly between zero and one"
            )


@dataclass(frozen=True)
class FillingSimulationResult:
    parameters: FillingNetworkParameters
    samples: dict[str, np.ndarray]
    stop_reason: str
    stop_time_s: float
    initial_tank_water_volume_m3: float
    initial_wet_line_water_volume_m3: float
    total_external_water_volume_m3: float
    max_volume_balance_error_m3: float


def _air_diagnostics(
    filling: FillingBranch,
    flow_rate_m3_s: float,
    dry_start_s_m: float,
    *,
    parameters: FillingNetworkParameters,
    liquid_drive_Pa: float,
) -> tuple[float, float, bool]:
    """Low-Mach, equal-volume-flow screen; not a compressible gas solution."""
    if dry_start_s_m >= filling.length_m or abs(flow_rate_m3_s) <= 1e-16:
        return 0.0, 0.0, True
    rho_air = parameters.gas.ambient_pressure_Pa / (R_AIR_J_KG_K * parameters.air_temperature_K)
    sound_speed = sqrt(parameters.air_gamma * R_AIR_J_KG_K * parameters.air_temperature_K)
    max_mach = 0.0
    pressure_drop = 0.0
    for section, section_start in zip(
        filling.branch.sections, filling._section_starts(), strict=True
    ):
        section_end = section_start + section.length_m
        begin = max(dry_start_s_m, section_start)
        end = section_end
        if end <= begin:
            continue
        local_start = begin - section_start
        local_end = end - section_start
        full_slope_a = (section.area_end_m2 - section.area_start_m2) / section.length_m
        full_slope_d = (
            section.hydraulic_diameter_end_m - section.hydraulic_diameter_start_m
        ) / section.length_m
        interval_mid = 0.5 * (local_start + local_end)
        interval_half = 0.5 * (local_end - local_start)
        friction_integral = 0.0
        # The Mach diagnostic is a maximum, not a quadrature. A linearly
        # expanding dry interval can attain its maximum at the front endpoint,
        # which Gauss nodes do not include. Keep pressure-loss quadrature below
        # unchanged and sample both exact interval endpoints for Mach.
        for local in (local_start, local_end):
            endpoint_area = section.area_start_m2 + full_slope_a * local
            endpoint_velocity = abs(flow_rate_m3_s) / endpoint_area
            max_mach = max(max_mach, endpoint_velocity / sound_speed)
        for xi, wi in zip(_GAUSS4_X, _GAUSS4_W, strict=True):
            local = interval_mid + interval_half * float(xi)
            area = section.area_start_m2 + full_slope_a * local
            diameter = section.hydraulic_diameter_start_m + full_slope_d * local
            velocity = abs(flow_rate_m3_s) / area
            max_mach = max(max_mach, velocity / sound_speed)
            reynolds = rho_air * velocity * diameter / 1.81e-5
            darcy = darcy_friction_factor(reynolds, section.roughness_m / diameter)
            friction_integral += float(wi) * darcy / diameter * 0.5 * rho_air * velocity**2
        pressure_drop += interval_half * friction_integral
    transition_mixed = (
        filling.transition_start_s_m is not None
        and filling.transition_end_s_m is not None
        and filling.transition_start_s_m < dry_start_s_m < filling.transition_end_s_m
    )
    if filling.air_minor_loss_K is not None:
        reference_velocity = abs(flow_rate_m3_s) / filling.branch.reference_area_m2
        pressure_drop += 0.5 * rho_air * reference_velocity**2 * filling.air_minor_loss_K
    available = abs(liquid_drive_Pa)
    valid = (
        max_mach <= parameters.max_screened_air_mach
        and available > 0
        and pressure_drop / available <= parameters.max_screened_air_loss_fraction
        and not transition_mixed
        and filling.air_minor_loss_K is not None
    )
    return max_mach, pressure_drop, valid


def _branch_losses_before_front(
    filling: FillingBranch,
    liquid: LiquidProperties,
    flow_rate_m3_s: float,
    front_s_m: float,
    opening_fraction: float,
) -> float:
    """Liquid losses up to the front; each local loss is applied once."""
    branch = filling.branch
    sign = 0.0 if flow_rate_m3_s == 0 else float(np.sign(flow_rate_m3_s))
    reference_velocity = flow_rate_m3_s / branch.reference_area_m2
    reference_head = 0.5 * liquid.density_kg_m3 * reference_velocity**2
    losses = sum(
        _section_friction_drop_Pa(section, flow_rate_m3_s, liquid)
        for section in filling.wet_sections(front_s_m)
    )
    if opening_fraction <= 0:
        return float("inf") if flow_rate_m3_s != 0 else 0.0
    valve_k = 1.0 / (branch.valve_Cd * opening_fraction) ** 2
    losses += sign * reference_head * (valve_k + branch.entrance_loss_K)
    if (
        filling.transition_start_s_m is not None
        and filling.transition_end_s_m is not None
        and front_s_m >= filling.transition_end_s_m
    ):
        losses += sign * reference_head * branch.transition_loss_K
    return float(losses)


def _state_derivative(
    parameters: FillingNetworkParameters,
    initial_gas_volume_m3: float,
    time_s: float,
    tank_water_volume_m3: float,
    flows_m3_s: np.ndarray,
    wet_volumes_m3: np.ndarray,
    external_volumes_m3: np.ndarray,
    full_modes: np.ndarray | None = None,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, dict[str, float]]:
    network = parameters.network
    liquid = parameters.liquid
    rho = liquid.density_kg_m3
    gas_volume = network.tank.tank_volume_m3 - tank_water_volume_m3
    gas_pressure, gas_temp, _ = gas_state(network.gas, initial_gas_volume_m3, gas_volume)
    tank_level = tank_level_z_m(network.tank, tank_water_volume_m3)
    qdot = np.zeros_like(flows_m3_s)
    wetdot = np.zeros_like(wet_volumes_m3)
    extdot = np.zeros_like(external_volumes_m3)
    diagnostics: dict[str, float] = {
        "tank_level_z_m": tank_level,
        "gas_volume_m3": gas_volume,
        "gas_pressure_abs_Pa": gas_pressure,
        "gas_temperature_K": gas_temp,
    }
    for index, filling in enumerate(parameters.branches):
        branch = filling.branch
        flow = float(flows_m3_s[index])
        wet_volume = min(max(float(wet_volumes_m3[index]), 0.0), filling.full_wet_volume_m3)
        front_s = filling.s_from_volume(wet_volume)
        full = (
            bool(full_modes[index])
            if full_modes is not None
            else wet_volume >= filling.full_wet_volume_m3 * (1.0 - 1e-13)
        )
        opening = _valve_opening(branch, time_s)
        if full:
            drive = (
                gas_pressure
                - network.gas.ambient_pressure_Pa
                + rho * liquid.gravity_m_s2 * (tank_level - branch.outlet_center_z_m)
            )
            losses = _branch_losses_before_front(filling, liquid, flow, filling.length_m, opening)
            # At a full route, use the original network's transition and outlet
            # terms exactly. The pre-front loss helper already has all but the
            # outlet kinetic head.
            velocity_out = flow / branch.outlet_area_m2
            losses += 0.5 * rho * velocity_out**2 * (0.0 if flow == 0 else np.sign(flow))
            inertance = rho * filling.full_inertance_integral_m
            qdot[index] = 0.0 if opening <= 0 else (drive - losses) / inertance
            extdot[index] = flow
            diagnostics[f"front_s_{branch.name}_m"] = filling.length_m
            diagnostics[f"front_z_{branch.name}_m"] = filling.elevation_samples_m[-1]
            diagnostics[f"front_froude_{branch.name}"] = float("nan")
            diagnostics[f"wet_volume_{branch.name}_m3"] = filling.full_wet_volume_m3
            diagnostics[f"inertance_{branch.name}_kg_m4"] = inertance
            diagnostics[f"air_mach_{branch.name}"] = 0.0
            diagnostics[f"air_pressure_drop_{branch.name}_Pa"] = 0.0
            diagnostics[f"ambient_front_screen_pass_{branch.name}"] = 1.0
            diagnostics[f"outlet_flow_{branch.name}_m3_s"] = flow
            diagnostics[f"liquid_drive_{branch.name}_Pa"] = drive
            continue

        area_front = filling.area_at_s(front_s)
        diameter_front = filling.diameter_at_s(front_s)
        z_front = filling.elevation_at_s(front_s)
        drive = (
            gas_pressure
            - network.gas.ambient_pressure_Pa
            + rho * liquid.gravity_m_s2 * (tank_level - z_front)
        )
        inertance = rho * filling.inertance_integral_to_s(front_s)
        if inertance <= 0:
            raise ValueError("initial wetted path must have nonzero inertance")
        losses = _branch_losses_before_front(filling, liquid, flow, front_s, opening)
        front_velocity = flow / area_front
        front_kinetic = 0.5 * rho * front_velocity**2
        qdot[index] = 0.0 if opening <= 0 else (drive - losses - front_kinetic) / inertance
        wetdot[index] = flow
        mach, air_drop, screen_pass = _air_diagnostics(
            filling,
            flow,
            front_s,
            parameters=parameters,
            liquid_drive_Pa=drive,
        )
        diagnostics[f"front_s_{branch.name}_m"] = front_s
        diagnostics[f"front_z_{branch.name}_m"] = z_front
        diagnostics[f"front_froude_{branch.name}"] = abs(front_velocity) / sqrt(
            liquid.gravity_m_s2 * diameter_front
        )
        diagnostics[f"wet_volume_{branch.name}_m3"] = wet_volume
        diagnostics[f"inertance_{branch.name}_kg_m4"] = inertance
        diagnostics[f"air_mach_{branch.name}"] = mach
        diagnostics[f"air_pressure_drop_{branch.name}_Pa"] = air_drop
        diagnostics[f"ambient_front_screen_pass_{branch.name}"] = float(screen_pass)
        diagnostics[f"outlet_flow_{branch.name}_m3_s"] = 0.0
        diagnostics[f"liquid_drive_{branch.name}_Pa"] = drive
    tank_dot = -float(np.sum(flows_m3_s))
    diagnostics["external_water_volume_m3"] = float(np.sum(external_volumes_m3))
    return tank_dot, qdot, wetdot, extdot, diagnostics


def simulate_filling(
    parameters: FillingNetworkParameters,
    *,
    time_step_s: float = 1.0e-4,
    max_time_s: float = 1.0,
) -> FillingSimulationResult:
    """Integrate tank/branch inventories and flow using explicit midpoint RK2."""
    parameters.validate()
    if not isfinite(time_step_s) or time_step_s <= 0:
        raise ValueError("time_step_s must be finite and positive")
    if not isfinite(max_time_s) or max_time_s <= 0:
        raise ValueError("max_time_s must be finite and positive")

    network = parameters.network
    tank_water_initial = network.tank.tank_volume_m3 * network.tank.fill_fraction
    gas_volume_initial = network.tank.tank_volume_m3 - tank_water_initial
    intake_crown_stop_z_m = max(branch.intake_crown_z_m for branch in network.branches)
    intake_crown_stop_water_m3 = tank_volume_at_level_m3(network.tank, intake_crown_stop_z_m)
    if tank_water_initial <= intake_crown_stop_water_m3:
        raise ValueError("initial tank level is at or below the highest branch intake crown")
    line_initial = np.array(
        [branch.initial_wet_volume_m3 for branch in parameters.branches], dtype=float
    )
    flows = np.zeros(len(parameters.branches), dtype=float)
    external = np.zeros_like(flows)
    cumulative_inflow = np.zeros_like(flows)
    tank_water = tank_water_initial
    line = line_initial.copy()
    time_s = 0.0
    samples: dict[str, list[float]] = {}
    stop_reason = "max_time"

    def record(
        now: float,
        state: tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    ) -> None:
        tank_v, q, wet, ext, branch_inflow = state
        derivative = _state_derivative(parameters, gas_volume_initial, now, tank_v, q, wet, ext)
        _, _, _, _, diag = derivative
        gas_v = network.tank.tank_volume_m3 - tank_v
        p_g, t_g, _ = gas_state(network.gas, gas_volume_initial, gas_v)
        row: dict[str, float] = {
            "time_s": now,
            "tank_water_volume_m3": tank_v,
            "gas_volume_m3": gas_v,
            "gas_pressure_abs_Pa": p_g,
            "gas_temperature_K": t_g,
            "total_branch_flow_m3_s": float(np.sum(q)),
            "total_external_water_volume_m3": float(np.sum(ext)),
            "total_wet_line_water_volume_m3": float(np.sum(wet)),
            "water_volume_balance_residual_m3": (
                tank_v
                + float(np.sum(wet))
                + float(np.sum(ext))
                - tank_water_initial
                - float(np.sum(line_initial))
            ),
        }
        for index, filling in enumerate(parameters.branches):
            name = filling.branch.name
            front_s = filling.s_from_volume(float(wet[index]))
            row[f"flow_{name}_m3_s"] = float(q[index])
            row[f"front_s_{name}_m"] = front_s
            row[f"wet_line_volume_{name}_m3"] = float(wet[index])
            row[f"external_water_volume_{name}_m3"] = float(ext[index])
            row[f"integrated_branch_inflow_{name}_m3"] = float(branch_inflow[index])
            row[f"branch_volume_balance_residual_{name}_m3"] = float(
                line_initial[index] + branch_inflow[index] - wet[index] - ext[index]
            )
            row[f"outlet_flow_{name}_m3_s"] = diag[f"outlet_flow_{name}_m3_s"]
            suffixes = {
                "front_z": "m",
                "front_froude": "",
                "inertance": "kg_m4",
                "air_mach": "",
                "air_pressure_drop": "Pa",
                "ambient_front_screen_pass": "",
                "liquid_drive": "Pa",
            }
            for key, suffix in suffixes.items():
                source_key = f"{key}_{name}{'_' + suffix if suffix else ''}"
                row[source_key] = diag[source_key]
        for key, value in row.items():
            samples.setdefault(key, []).append(float(value))

    state = (tank_water, flows.copy(), line.copy(), external.copy(), cumulative_inflow.copy())
    record(0.0, state)
    n_steps = int(np.ceil(max_time_s / time_step_s))
    for step in range(n_steps):
        dt = min(time_step_s, max_time_s - time_s)
        if dt <= 0:
            break
        full_modes = np.array(
            [
                line[index] >= filling.full_wet_volume_m3 * (1.0 - 1e-13)
                for index, filling in enumerate(parameters.branches)
            ],
            dtype=bool,
        )
        k1 = _state_derivative(
            parameters,
            gas_volume_initial,
            time_s,
            tank_water,
            flows,
            line,
            external,
            full_modes,
        )
        h1, q1, wet1, ext1, _ = k1
        mid_tank = tank_water + 0.5 * dt * h1
        mid_q = flows + 0.5 * dt * q1
        mid_wet = line + 0.5 * dt * wet1
        mid_ext = external + 0.5 * dt * ext1
        k2 = _state_derivative(
            parameters,
            gas_volume_initial,
            time_s + 0.5 * dt,
            mid_tank,
            mid_q,
            mid_wet,
            mid_ext,
            full_modes,
        )
        h2, q2, wet2, ext2, _ = k2
        next_tank = tank_water + dt * h2
        next_flows = flows + dt * q2
        next_line = line + dt * wet2
        next_external = external + dt * ext2
        next_cumulative_inflow = cumulative_inflow + dt * mid_q

        # Locate mouth contact to the current time-step bracket: a branch uses
        # its pre-arrival equation throughout the step, then line storage is
        # capped at its geometric full volume and excess water is assigned to
        # discharge. Its endpoint flow switches to the full-route equation on
        # the following step.
        crossed_indices: list[int] = []
        uncapped_next_line = next_line.copy()
        for index, filling in enumerate(parameters.branches):
            full_volume = filling.full_wet_volume_m3
            if not full_modes[index] and uncapped_next_line[index] >= full_volume:
                crossed_indices.append(index)
                next_line[index] = full_volume
        if crossed_indices:
            # Assign each event bracket's post-mouth water to the branch that
            # crossed. Redistributing the global excess by endpoint flow gives
            # false branch ledgers when unequal fronts cross in one RK2 step.
            for index in crossed_indices:
                overrun = max(
                    0.0,
                    uncapped_next_line[index] - parameters.branches[index].full_wet_volume_m3,
                )
                next_external[index] += overrun
        if next_tank <= intake_crown_stop_water_m3:
            tank_drop = tank_water - next_tank
            fraction = (
                1.0 if tank_drop <= 0 else (tank_water - intake_crown_stop_water_m3) / tank_drop
            )
            fraction = min(max(float(fraction), 0.0), 1.0)
            time_s += dt * fraction
            tank_water += fraction * (next_tank - tank_water)
            flows += fraction * (next_flows - flows)
            line += fraction * (next_line - line)
            external += fraction * (next_external - external)
            stop_reason = "tank_intake_crown_reached"
            cumulative_inflow += fraction * (next_cumulative_inflow - cumulative_inflow)
            record(
                time_s,
                (tank_water, flows.copy(), line.copy(), external.copy(), cumulative_inflow.copy()),
            )
            break
        time_s += dt
        tank_water, flows, line, external, cumulative_inflow = (
            next_tank,
            next_flows,
            next_line,
            next_external,
            next_cumulative_inflow,
        )
        if tank_water <= 0 or tank_water >= network.tank.tank_volume_m3:
            stop_reason = "tank_inventory_limit"
            record(
                time_s,
                (tank_water, flows.copy(), line.copy(), external.copy(), cumulative_inflow.copy()),
            )
            break
        if any(
            float(wet) < filling.initial_wet_volume_m3 - 1e-12
            for wet, filling in zip(line, parameters.branches, strict=True)
        ):
            stop_reason = "flow_reversal_beyond_initial_wet_prefix"
            record(
                time_s,
                (tank_water, flows.copy(), line.copy(), external.copy(), cumulative_inflow.copy()),
            )
            break
        record(
            time_s,
            (tank_water, flows.copy(), line.copy(), external.copy(), cumulative_inflow.copy()),
        )
        if time_s >= max_time_s:
            break

    arrays = {name: np.asarray(values, dtype=float) for name, values in samples.items()}
    residual = arrays["water_volume_balance_residual_m3"]
    return FillingSimulationResult(
        parameters=parameters,
        samples=arrays,
        stop_reason=stop_reason,
        stop_time_s=float(arrays["time_s"][-1]),
        initial_tank_water_volume_m3=tank_water_initial,
        initial_wet_line_water_volume_m3=float(np.sum(line_initial)),
        total_external_water_volume_m3=float(np.sum(external)),
        max_volume_balance_error_m3=float(np.max(np.abs(residual))),
    )


__all__ = [
    "FillingBranch",
    "FillingNetworkParameters",
    "FillingSimulationResult",
    "simulate_filling",
]
