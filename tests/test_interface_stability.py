"""Independent checks for the inviscid finite-thickness shear reference."""

from __future__ import annotations

import numpy as np
import pytest

from aerial_drop.interface_stability import (
    BaseState,
    NoUnstableModeError,
    interpolate_mode,
    parity_characteristic,
    periodic_characteristic,
    solve_periodic_mode,
)

K_FUNDAMENTAL = 2.0 * np.pi / 0.12


def test_periodized_base_state_matches_at_vertical_seam() -> None:
    base = BaseState()
    z = np.array([-0.5 * base.Lz, 0.5 * base.Lz])
    velocity, shear, _ = base.velocity(z)
    assert np.isclose(velocity[0], velocity[1], rtol=0.0, atol=1.0e-12)
    assert np.isclose(shear[0], shear[1], rtol=0.0, atol=1.0e-12)
    details = base.as_dict()["periodization_diagnostics"]
    assert details["max_abs_U_change_from_raw_tanh_m_s"] < 0.02
    assert np.allclose(details["periodized_seam_dUdz_m_s2"], 0.0, atol=1.0e-12)
    assert np.allclose(
        details["raw_truncated_tanh_seam_dUdz_m_s2"],
        [-4.469835106734784, 4.469835106734784],
        rtol=1.0e-10,
        atol=1.0e-10,
    )


def test_uniform_velocity_has_no_growing_mode() -> None:
    uniform = BaseState(U_air=25.0, U_water=25.0)
    with pytest.raises(NoUnstableModeError, match="neutral advection"):
        solve_periodic_mode(uniform, K_FUNDAMENTAL, steps_per_layer=32)


def test_equal_density_limit_is_independent_of_absolute_density() -> None:
    unit_density = BaseState(rho_air=1.0, rho_water=1.0)
    large_equal_density = BaseState(rho_air=1000.0, rho_water=1000.0)
    phase_speed = 6.0 + 5.0j
    for characteristic in (periodic_characteristic, parity_characteristic):
        if characteristic is parity_characteristic:
            first = characteristic(unit_density, K_FUNDAMENTAL, phase_speed, "even", 64)
            second = characteristic(large_equal_density, K_FUNDAMENTAL, phase_speed, "even", 64)
        else:
            first = characteristic(unit_density, K_FUNDAMENTAL, phase_speed, 64)
            second = characteristic(large_equal_density, K_FUNDAMENTAL, phase_speed, 64)
        assert np.isclose(first, second, rtol=1.0e-12, atol=1.0e-12)


def test_finite_thickness_mode_converges_and_obeys_both_interface_conditions() -> None:
    base = BaseState()
    coarse = solve_periodic_mode(
        base,
        K_FUNDAMENTAL,
        steps_per_layer=64,
        points_per_layer=64,
        initial_c=5.84 + 5.99j,
        parity="even",
    )
    fine = solve_periodic_mode(
        base,
        K_FUNDAMENTAL,
        steps_per_layer=128,
        points_per_layer=128,
        initial_c=5.84 + 5.99j,
        parity="even",
    )
    assert coarse.growth > 0.0
    assert fine.growth > 0.0
    assert abs(coarse.growth - fine.growth) / fine.growth < 1.0e-4
    assert abs(fine.metadata["full_period_characteristic_residual_abs"]) < 1.0e-5
    assert abs(fine.metadata["monodromy_determinant"]["real"] - 1.0) < 1.0e-6
    assert abs(fine.metadata["monodromy_determinant"]["imag"]) < 1.0e-6
    assert fine.residual < 1.0e-8
    assert (
        max(
            check[key]
            for check in fine.metadata["interface_matching_residuals"]
            for key in (
                "psi_continuity_relative_residual",
                "normal_velocity_continuity_relative_residual",
                "pressure_continuity_relative_residual",
                "kinematic_condition_relative_residual",
                "tangential_velocity_jump_relative_residual",
            )
        )
        < 1.0e-9
    )
    assert np.isclose(max(abs(fine.eta_lower), abs(fine.eta_upper)), 1.0)
    assert abs(fine.eta_upper / fine.eta_lower - 1.0) < 1.0e-5


def test_odd_interface_branch_is_unstable_and_opposite_phase() -> None:
    odd = solve_periodic_mode(
        BaseState(),
        K_FUNDAMENTAL,
        steps_per_layer=64,
        points_per_layer=64,
        initial_c=4.81 + 5.13j,
        parity="odd",
    )
    assert odd.growth > 0.0
    assert abs(odd.eta_upper / odd.eta_lower + 1.0) < 1.0e-5
    c_conjugate = odd.c.conjugate()
    value = periodic_characteristic(BaseState(), K_FUNDAMENTAL, odd.c, 64)
    conjugate_value = periodic_characteristic(BaseState(), K_FUNDAMENTAL, c_conjugate, 64)
    assert np.isclose(conjugate_value, value.conjugate(), rtol=1.0e-9, atol=1.0e-8)


def test_interpolation_keeps_tangential_velocity_jump_one_sided() -> None:
    mode = solve_periodic_mode(
        BaseState(),
        K_FUNDAMENTAL,
        steps_per_layer=32,
        points_per_layer=32,
        initial_c=5.84 + 5.99j,
        parity="even",
    )
    base = BaseState()
    lower_air_u = interpolate_mode(mode, base.z_lower, layer=0, field="u")
    lower_water_u = interpolate_mode(mode, base.z_lower, layer=1, field="u")
    lower_air_w = interpolate_mode(mode, base.z_lower, layer=0, field="w")
    lower_water_w = interpolate_mode(mode, base.z_lower, layer=1, field="w")
    assert abs(lower_air_u - lower_water_u) > 1.0
    assert np.isclose(lower_air_w, lower_water_w, rtol=1.0e-12, atol=1.0e-12)
    with pytest.raises(ValueError, match="outside sampled layer"):
        interpolate_mode(mode, base.z_upper, layer=0, field="u")
