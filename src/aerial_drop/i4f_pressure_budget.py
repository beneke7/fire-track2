"""Sealed-gas quasistatic pressure budget for provisional I4F line inventories.

This is a pressure-supported reference, not a rigorous maximum-delivery bound
or a transient discharge model. It omits liquid inertia, gravity, valve/pipe
losses, gas venting, dissolution, and heat-transfer rates. The n=1 case is an
isothermal limit; no heat-transfer rate is modeled. A real flow can continue
after this quasistatic gas pressure reaches the back pressure if its momentum
and elevation head permit it.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class SealedGasBudgetCase:
    """One per-tank ideal-gas reference case, using absolute pressures and SI."""

    initial_pressure_abs_Pa: float
    back_pressure_abs_Pa: float
    tank_water_volume_m3: float
    headspace_ratio_to_tank_water: float
    wetted_feed_volume_m3: float
    initially_dry_downstream_volume_m3: float
    polytropic_exponent: float

    def validate(self) -> None:
        values = (
            self.initial_pressure_abs_Pa,
            self.back_pressure_abs_Pa,
            self.tank_water_volume_m3,
            self.headspace_ratio_to_tank_water,
            self.wetted_feed_volume_m3,
            self.initially_dry_downstream_volume_m3,
            self.polytropic_exponent,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("pressure-budget inputs must be finite")
        if self.initial_pressure_abs_Pa <= 0 or self.back_pressure_abs_Pa <= 0:
            raise ValueError("pressures must be positive absolute pressures")
        if self.tank_water_volume_m3 <= 0 or self.headspace_ratio_to_tank_water <= 0:
            raise ValueError("tank water and headspace ratio must be positive")
        if self.wetted_feed_volume_m3 < 0 or self.initially_dry_downstream_volume_m3 < 0:
            raise ValueError("line volumes cannot be negative")
        if self.polytropic_exponent <= 0:
            raise ValueError("polytropic exponent must be positive")

    @property
    def initial_headspace_volume_m3(self) -> float:
        return self.tank_water_volume_m3 * self.headspace_ratio_to_tank_water

    @property
    def initial_liquid_inventory_m3(self) -> float:
        """Tank plus separately wetted feed inventory, per tank."""
        return self.tank_water_volume_m3 + self.wetted_feed_volume_m3


def pressure_after_gas_displacement_abs_Pa(
    initial_pressure_abs_Pa: float,
    initial_headspace_volume_m3: float,
    gas_displacement_m3: float,
    polytropic_exponent: float,
) -> float:
    """Return ``P0*(Vg0/(Vg0+deltaVg))**n`` for a sealed gas inventory."""
    values = (
        initial_pressure_abs_Pa,
        initial_headspace_volume_m3,
        gas_displacement_m3,
        polytropic_exponent,
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("gas-state inputs must be finite")
    if initial_pressure_abs_Pa <= 0 or initial_headspace_volume_m3 <= 0:
        raise ValueError("initial pressure and gas volume must be positive")
    if initial_headspace_volume_m3 + gas_displacement_m3 <= 0:
        raise ValueError("expanded gas volume must be positive")
    if polytropic_exponent <= 0:
        raise ValueError("polytropic exponent must be positive")
    return (
        initial_pressure_abs_Pa
        * (initial_headspace_volume_m3 / (initial_headspace_volume_m3 + gas_displacement_m3))
        ** polytropic_exponent
    )


def tank_only_critical_headspace_ratio(
    initial_pressure_abs_Pa: float,
    back_pressure_abs_Pa: float,
    polytropic_exponent: float,
) -> float | None:
    """Headspace/water ratio that reaches back pressure after tank-water-only
    displacement; deliberately excludes feed and downstream line volumes.
    """
    if not all(
        isfinite(value)
        for value in (initial_pressure_abs_Pa, back_pressure_abs_Pa, polytropic_exponent)
    ):
        raise ValueError("pressure and exponent inputs must be finite")
    if initial_pressure_abs_Pa <= 0 or back_pressure_abs_Pa <= 0:
        raise ValueError("pressures must be positive absolute pressures")
    if polytropic_exponent <= 0:
        raise ValueError("polytropic exponent must be positive")
    blowdown_factor = (initial_pressure_abs_Pa / back_pressure_abs_Pa) ** (
        1.0 / polytropic_exponent
    ) - 1.0
    if blowdown_factor <= 0:
        return None
    return 1.0 / blowdown_factor


def pressure_budget(case: SealedGasBudgetCase) -> dict[str, float | bool | None]:
    """Compute quasistatic priming, pressure-equilibrium, and inventory states.

    The model treats the dry downstream volume as a displacement needed to
    establish full-bore liquid continuity before nozzle-delivered volume is
    counted. The initial tank-to-valve feed is already wetted: it contributes
    to available liquid inventory, but it is not added a second time to gas
    displacement during priming.
    """
    case.validate()
    vg0 = case.initial_headspace_volume_m3
    vdry = case.initially_dry_downstream_volume_m3
    available = case.initial_liquid_inventory_m3
    raw_delta_eq = vg0 * (
        (case.initial_pressure_abs_Pa / case.back_pressure_abs_Pa)
        ** (1.0 / case.polytropic_exponent)
        - 1.0
    )
    nozzle_eq_raw = max(0.0, raw_delta_eq - vdry)
    nozzle_eq_capped = min(available, nozzle_eq_raw)
    all_water_displacement = vdry + available
    return {
        "initial_headspace_volume_m3": vg0,
        "initial_liquid_inventory_m3": available,
        "line_priming_displacement_m3": vdry,
        "pressure_after_full_bore_priming_abs_Pa": pressure_after_gas_displacement_abs_Pa(
            case.initial_pressure_abs_Pa, vg0, vdry, case.polytropic_exponent
        ),
        "priming_pressure_margin_over_back_pressure_Pa": (
            pressure_after_gas_displacement_abs_Pa(
                case.initial_pressure_abs_Pa, vg0, vdry, case.polytropic_exponent
            )
            - case.back_pressure_abs_Pa
        ),
        "raw_pressure_equilibrium_gas_displacement_m3": raw_delta_eq,
        "raw_pressure_equilibrium_nozzle_volume_after_priming_m3": nozzle_eq_raw,
        "inventory_capped_pressure_equilibrium_nozzle_volume_m3": nozzle_eq_capped,
        "inventory_capped_total_gas_displacement_m3": min(
            all_water_displacement, max(0.0, raw_delta_eq)
        ),
        "pressure_after_hypothetical_expulsion_of_all_initial_water_abs_Pa": (
            pressure_after_gas_displacement_abs_Pa(
                case.initial_pressure_abs_Pa,
                vg0,
                all_water_displacement,
                case.polytropic_exponent,
            )
        ),
        "tank_only_critical_headspace_ratio": tank_only_critical_headspace_ratio(
            case.initial_pressure_abs_Pa,
            case.back_pressure_abs_Pa,
            case.polytropic_exponent,
        ),
        "equilibrium_nozzle_volume_was_inventory_capped": nozzle_eq_raw > available,
    }


def pressure_during_post_priming_delivery_abs_Pa(
    case: SealedGasBudgetCase, nozzle_delivered_volume_m3: float
) -> float:
    """Pressure reference at post-priming output volume; no outlet history."""
    case.validate()
    if not isfinite(nozzle_delivered_volume_m3) or nozzle_delivered_volume_m3 < 0:
        raise ValueError("post-priming nozzle volume must be finite and nonnegative")
    return pressure_after_gas_displacement_abs_Pa(
        case.initial_pressure_abs_Pa,
        case.initial_headspace_volume_m3,
        case.initially_dry_downstream_volume_m3 + nozzle_delivered_volume_m3,
        case.polytropic_exponent,
    )
