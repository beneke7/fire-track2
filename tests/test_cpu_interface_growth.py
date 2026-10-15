"""Analytical checks for the isolated interface-growth case generator."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aerial_drop.interface_stability import BaseState
from scripts.run_cpu_interface_growth import (
    ADDED_NU,
    LENGTHS,
    SEED_AMPLITUDE,
    V2_LENGTHS,
    V2_SEED_AMPLITUDE,
    WATER_BOTTOM,
    WATER_TOP,
    _fit_complex_mode,
    alpha05_interface_modes,
    alpha_seed,
    alpha_seed_v2,
    case_definitions,
    docker_memory_usage_bytes,
    initial_velocity,
    interface_mode_amplitude,
    interface_mode_components,
    periodic_divergence_max,
    plane_averaged_shear_metrics,
    v2_decompose_par_dict,
    v2_fv_schemes,
    v2_initial_fields,
)


def test_seeded_slab_is_bounded_and_conserves_its_declared_volume() -> None:
    nx, ny, nz = 48, 24, 48
    alpha = alpha_seed(nx, ny, nz)
    assert alpha.shape == (nz, ny, nx)
    assert float(alpha.min()) >= 0.0
    assert float(alpha.max()) <= 1.0

    dx, dy, dz = LENGTHS[0] / nx, LENGTHS[1] / ny, LENGTHS[2] / nz
    expected = LENGTHS[0] * LENGTHS[1] * (WATER_TOP - WATER_BOTTOM)
    assert float(alpha.sum() * dx * dy * dz) == pytest.approx(expected, abs=1e-15)


def test_known_mode_is_recovered_from_subcell_alpha_seed() -> None:
    nx, ny, nz = 48, 24, 48
    alpha = alpha_seed(nx, ny, nz)
    measured, eta = interface_mode_amplitude(alpha.ravel(order="C"), nx, ny, nz)
    assert measured == pytest.approx(SEED_AMPLITUDE, rel=0.01)
    assert abs(float(np.mean(eta))) < 1e-15


def test_seeded_lower_and_upper_modes_start_in_phase() -> None:
    nx, ny, nz = 72, 36, 72
    components = interface_mode_components(alpha_seed(nx, ny, nz).ravel(order="C"), nx, ny, nz)
    amplitudes = components["amplitudes"]
    assert amplitudes["lower"] == pytest.approx(SEED_AMPLITUDE, rel=0.01)
    assert amplitudes["upper"] == pytest.approx(SEED_AMPLITUDE, rel=0.01)
    assert amplitudes["symmetric"] == pytest.approx(SEED_AMPLITUDE, rel=0.01)
    assert amplitudes["antisymmetric"] < SEED_AMPLITUDE * 1e-10
    assert components["relative_interface_phase_rad"] == pytest.approx(0.0, abs=1e-8)


def test_experiment_record_matches_the_implemented_seed() -> None:
    record_path = Path(__file__).resolve().parents[1] / "cases/cpu_interface_growth/experiment.json"
    record = json.loads(record_path.read_text())
    seed = record["seeded_mode"]
    assert seed["interface_displacement_amplitude_m"] == SEED_AMPLITUDE
    assert seed["wavelength_m"] == LENGTHS[0]


def test_container_memory_sample_parser_handles_docker_units() -> None:
    assert docker_memory_usage_bytes("143.7MiB / 8GiB") == int(143.7 * 1024**2)


def test_advection_and_shear_initial_fields_are_divergence_free() -> None:
    nx, ny, nz = 32, 16, 32
    for variant in ("advection_control", "molecular_shear", "added_viscosity_shear"):
        velocity = initial_velocity(nx, ny, nz, variant)
        maximum, rms = periodic_divergence_max(velocity.ravel(order="C"), nx, ny, nz)
        assert maximum == pytest.approx(0.0, abs=1e-12)
        assert rms == pytest.approx(0.0, abs=1e-12)


def test_plane_mean_recovers_declared_finite_tanh_shear_thickness() -> None:
    nx, ny, nz = 72, 36, 72
    velocity = initial_velocity(nx, ny, nz, "molecular_shear")
    profiles = plane_averaged_shear_metrics(velocity.ravel(order="C"), nx, ny, nz)
    for surface in ("lower", "upper"):
        delta = profiles[surface]["plane_averaged_tanh_parameter_delta_m"]
        assert delta == pytest.approx(0.0075, rel=0.03)

    control = initial_velocity(nx, ny, nz, "advection_control")
    control_profiles = plane_averaged_shear_metrics(control.ravel(order="C"), nx, ny, nz)
    assert all(
        profile["plane_averaged_tanh_parameter_delta_m"] is None
        for profile in control_profiles.values()
    )


def test_sweep_pairs_controls_and_viscosity_on_two_fixed_physical_meshes() -> None:
    cases = case_definitions(pilot=False)
    assert len(cases) == 6
    meshes = {case["mesh_name"]: case["mesh"] for case in cases}
    assert meshes == {"coarse": [48, 24, 48], "fine": [72, 36, 72]}
    assert {case["variant"] for case in cases} == {
        "advection_control",
        "molecular_shear",
        "added_viscosity_shear",
    }
    damped = [case for case in cases if case["variant"] == "added_viscosity_shear"]
    assert len(damped) == 2
    assert all(case["nu_add_m2_s"] == ADDED_NU for case in damped)
    assert all(case["horizon_s"] == 0.012 for case in cases)


def test_pilot_is_separate_and_smaller_than_mesh_comparison() -> None:
    pilot = case_definitions(pilot=True)
    assert len(pilot) == 1
    assert pilot[0]["mesh"] == [32, 16, 32]
    assert pilot[0]["horizon_s"] == 0.002


@pytest.mark.parametrize("mesh", [(128, 64, 128), (192, 96, 192)])
def test_v2_two_amplitude_observers_recover_the_same_seed(mesh: tuple[int, int, int]) -> None:
    nx, ny, nz = mesh
    alpha = alpha_seed_v2(nx, ny, nz, amplitude_m=V2_SEED_AMPLITUDE)
    volume_observer = interface_mode_components(alpha.ravel(), nx, ny, nz)
    contour_observer = alpha05_interface_modes(alpha, nx, ny, nz)
    assert float(alpha.min()) >= 0.0
    assert float(alpha.max()) <= 1.0
    assert volume_observer["amplitudes"]["symmetric"] == pytest.approx(V2_SEED_AMPLITUDE, rel=2e-4)
    assert contour_observer["amplitudes_m"]["symmetric"] == pytest.approx(
        V2_SEED_AMPLITUDE, rel=1e-3
    )
    assert contour_observer["coverage_fraction"] == {"lower": 1.0, "upper": 1.0}


def test_v2_cell_volume_preserves_phase_volume_on_both_meshes() -> None:
    expected = V2_LENGTHS[0] * V2_LENGTHS[1] * (WATER_TOP - WATER_BOTTOM)
    for nx, ny, nz in ((128, 64, 128), (192, 96, 192)):
        alpha = alpha_seed_v2(nx, ny, nz, amplitude_m=5.0e-5)
        cell_volume = np.prod(V2_LENGTHS) / (nx * ny * nz)
        assert float(alpha.sum() * cell_volume) == pytest.approx(expected, abs=2e-15)


def test_v2_native_divergence_writer_matches_pinned_openfoam_contract() -> None:
    assert "div(phi) Gauss linear;" in v2_fv_schemes()
    decompose = v2_decompose_par_dict(16)
    assert "numberOfSubdomains 16;" in decompose
    assert "n (4 2 2);" in decompose


def test_v2_experiment_record_adds_new_inputs_without_replacing_v1() -> None:
    record_path = Path(__file__).resolve().parents[1] / "cases/cpu_interface_growth/experiment.json"
    record = json.loads(record_path.read_text())
    assert record["seeded_mode"]["interface_displacement_amplitude_m"] == SEED_AMPLITUDE
    v2 = record["v2_experiment"]
    assert v2["seeded_mode"]["initial_amplitude_m"] == 5.0e-5
    assert v2["mesh_families"] == {"coarse": [128, 64, 128], "fine": [192, 96, 192]}


def test_v2_eigen_seed_shifts_coordinates_and_preserves_velocity_jump_sides() -> None:
    state = BaseState()
    z = np.linspace(-0.06, 0.06, 193)
    base_u = state.velocity(z)[0]
    lower, upper = state.z_lower, state.z_upper
    mode_u = np.where(z < lower, 1.0, np.where(z < upper, 2.0, 3.0)).astype(complex)
    eigenpair = {
        "z": z,
        "U": base_u,
        "rho": state.density(z),
        "u": mode_u,
        "w": np.full(z.shape, 0.5 + 0.0j),
        "p": np.zeros(z.shape, dtype=complex),
        "eta_lower": 1.0 + 0.0j,
        "eta_upper": -1.0 + 0.0j,
        "k": 2.0 * np.pi / V2_LENGTHS[0],
        "sigma": 314.0 + 0.0j,
        "growth": 314.0,
        "residual": 1e-12,
        "metadata": {"coordinate_frame": "centered z"},
    }
    mesh = (64, 8, 64)
    case = {
        "mesh": list(mesh),
        "variant": "molecular_shear",
        "seed_amplitude_m": 5.0e-5,
        "mode_number": 1,
    }
    alpha, velocity, _, eta_lower, eta_upper = v2_initial_fields(case, eigenpair)
    nx, ny, nz = mesh
    z_reference = (np.arange(nz) + 0.5) * V2_LENGTHS[2] / nz - 0.06
    x = (np.arange(nx) + 0.5) * V2_LENGTHS[0] / nx
    phase = np.exp(1j * eigenpair["k"] * x)
    side_u = np.where(z_reference < lower, 1.0, np.where(z_reference < upper, 2.0, 3.0))
    common_scale = -1j * 5.0e-5
    expected_u = state.velocity(z_reference)[0][:, None] + np.real(
        side_u[:, None] * common_scale * phase[None, :]
    )
    np.testing.assert_allclose(
        velocity[..., 0], np.broadcast_to(expected_u[:, None, :], (nz, ny, nx)), atol=1e-12
    )
    assert eta_lower == pytest.approx(-1j * 5.0e-5)
    assert eta_upper == pytest.approx(1j * 5.0e-5)
    tracked = alpha05_interface_modes(alpha, nx, ny, nz)
    assert tracked["amplitudes_m"]["lower"] == pytest.approx(5.0e-5, rel=2e-3)
    assert tracked["amplitudes_m"]["upper"] == pytest.approx(5.0e-5, rel=2e-3)
    assert abs(abs(tracked["relative_lower_upper_phase_rad"]) - np.pi) < 2e-3


def test_v2_complex_mode_fit_recovers_growth_and_phase_frequency() -> None:
    times = np.linspace(0.006, 0.008, 9)
    sigma = 313.732230 - 305.731657j
    initial = -1j * V2_SEED_AMPLITUDE
    modes = [initial * np.exp(sigma * time) for time in times]
    fit = _fit_complex_mode(times, modes, np.ones(times.size, dtype=bool))
    assert fit["growth_s_inv"] == pytest.approx(sigma.real, rel=1e-12)
    assert fit["phase_rate_rad_s"] == pytest.approx(sigma.imag, rel=1e-12)
    assert fit["sample_count"] == 9
