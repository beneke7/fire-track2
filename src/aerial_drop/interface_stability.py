"""Inviscid periodic Rayleigh reference for a sheared two-fluid film.

The model solves the piecewise-constant-density Rayleigh equation for a
periodic streamwise Fourier mode. Density is discontinuous at the two film
interfaces; velocity and its first derivative are continuous there. The base
velocity is a periodically imaged pair of tanh transitions, so the periodic
seam has matching derivatives as well as matching velocity.

This is a linear inviscid reference, not a viscous CFD model. In particular,
surface tension, gravity, compressibility, three-dimensional disturbances,
and viscosity are omitted. The mode convention is
``exp(i*k*x + sigma*t)`` with ``sigma = -i*k*c``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

ComplexArray = NDArray[np.complex128]
FloatArray = NDArray[np.float64]
LayerArray = NDArray[np.int8]


class NoUnstableModeError(ValueError):
    """Raised when the requested initial guess does not converge to growth."""


@dataclass(frozen=True)
class BaseState:
    """Periodic water-film base state with sharp density interfaces.

    Coordinates use ``z in [-Lz/2, Lz/2]``. The water phase occupies
    ``z_lower < z < z_upper``. ``delta`` is the tanh parameter in metres,
    not a measured 10--90% thickness. The paired tanh profile matches the
    supplied CPU diagnostic after centering its original [0, Lz] coordinates.
    A finite image sum gives a smooth periodic extension.
    """

    Lz: float = 0.12
    z_lower: float = -0.03
    z_upper: float = 0.03
    delta: float = 0.0075
    rho_water: float = 1000.0
    rho_air: float = 1.2
    U_air: float = 50.0
    U_water: float = 0.0
    image_count: int = 3

    def __post_init__(self) -> None:
        if self.Lz <= 0 or self.delta <= 0:
            raise ValueError("Lz and delta must be positive")
        if not (-0.5 * self.Lz < self.z_lower < self.z_upper < 0.5 * self.Lz):
            raise ValueError("interfaces must be ordered strictly inside one period")
        if self.rho_water <= 0 or self.rho_air <= 0:
            raise ValueError("densities must be positive")
        if self.image_count < 1:
            raise ValueError("image_count must be at least one")

    def velocity(self, z: FloatArray | float) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Return periodic ``U``, ``dU/dz`` and ``d²U/dz²`` in SI units."""
        z_array = np.asarray(z, dtype=np.float64)
        shape = z_array.shape
        flat_z = z_array.reshape(-1)
        profile = np.zeros_like(flat_z)
        first = np.zeros_like(flat_z)
        second = np.zeros_like(flat_z)
        for image in range(-self.image_count, self.image_count + 1):
            lower_arg = (flat_z - self.z_lower - image * self.Lz) / self.delta
            upper_arg = (flat_z - self.z_upper - image * self.Lz) / self.delta
            tanh_lower = np.tanh(lower_arg)
            tanh_upper = np.tanh(upper_arg)
            sech2_lower = 1.0 - tanh_lower**2
            sech2_upper = 1.0 - tanh_upper**2
            profile += tanh_lower - tanh_upper
            first += (sech2_lower - sech2_upper) / self.delta
            second += (
                -2.0 * sech2_lower * tanh_lower + 2.0 * sech2_upper * tanh_upper
            ) / self.delta**2

        delta_u = self.U_air - self.U_water
        U = self.U_air - 0.5 * delta_u * profile
        Uz = -0.5 * delta_u * first
        Uzz = -0.5 * delta_u * second
        return U.reshape(shape), Uz.reshape(shape), Uzz.reshape(shape)

    def density(self, z: FloatArray | float) -> FloatArray:
        """Return the piecewise-constant density, with interfaces assigned to water."""
        z_array = np.asarray(z, dtype=np.float64)
        # At the lower boundary use the water-side trace; at the upper
        # boundary use the air-side trace. This matches the one-sided
        # derivatives retained in the sampled eigenpair.
        in_water = (z_array >= self.z_lower) & (z_array < self.z_upper)
        return np.where(in_water, self.rho_water, self.rho_air).astype(np.float64)

    def as_dict(self) -> dict[str, Any]:
        seam = np.array([-0.5 * self.Lz, 0.5 * self.Lz], dtype=np.float64)
        periodic_u, periodic_uz, _ = self.velocity(seam)
        raw_lower = (seam - self.z_lower) / self.delta
        raw_upper = (seam - self.z_upper) / self.delta
        raw_tanh_lower = np.tanh(raw_lower)
        raw_tanh_upper = np.tanh(raw_upper)
        delta_u = self.U_air - self.U_water
        raw_u = self.U_air - 0.5 * delta_u * (raw_tanh_lower - raw_tanh_upper)
        raw_uz = (
            -0.5 * delta_u * ((1.0 - raw_tanh_lower**2) - (1.0 - raw_tanh_upper**2)) / self.delta
        )
        diagnostic_z = np.linspace(-0.5 * self.Lz, 0.5 * self.Lz, 1025)
        periodic_profile = self.velocity(diagnostic_z)[0]
        raw_lower_grid = (diagnostic_z - self.z_lower) / self.delta
        raw_upper_grid = (diagnostic_z - self.z_upper) / self.delta
        raw_profile = self.U_air - 0.5 * delta_u * (
            np.tanh(raw_lower_grid) - np.tanh(raw_upper_grid)
        )
        return {
            "Lz_m": self.Lz,
            "z_lower_m": self.z_lower,
            "z_upper_m": self.z_upper,
            "delta_tanh_m": self.delta,
            "rho_water_kg_m3": self.rho_water,
            "rho_air_kg_m3": self.rho_air,
            "U_air_m_s": self.U_air,
            "U_water_m_s": self.U_water,
            "periodic_image_count": self.image_count,
            "centered_coordinate_mapping": "z_centered = z_original - Lz/2",
            "periodization_diagnostics": {
                "raw_truncated_tanh_seam_dUdz_m_s2": raw_uz.tolist(),
                "raw_truncated_tanh_seam_U_m_s": raw_u.tolist(),
                "periodized_seam_U_m_s": periodic_u.tolist(),
                "periodized_seam_dUdz_m_s2": periodic_uz.tolist(),
                "max_abs_U_change_from_raw_tanh_m_s": float(
                    np.max(np.abs(periodic_profile - raw_profile))
                ),
            },
            "density_interfaces": "sharp jumps; normal velocity and pressure continuous",
            "gravity_m_s2": 0.0,
            "surface_tension_N_m": 0.0,
            "viscosity": "omitted; inviscid eigenreference",
        }


@dataclass(frozen=True)
class Eigenpair:
    """Sampled periodic eigenmode; fields use ``exp(i*k*x + sigma*t)``."""

    z: FloatArray
    U: FloatArray
    rho: FloatArray
    psi: ComplexArray
    layer: LayerArray
    u: ComplexArray
    w: ComplexArray
    p: ComplexArray
    eta_lower: complex
    eta_upper: complex
    k: float
    sigma: complex
    growth: float
    residual: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def c(self) -> complex:
        """Complex phase speed, with ``sigma = -i*k*c``."""
        return 1j * self.sigma / self.k


def _system_matrix(base: BaseState, k: float, c: complex, z: float) -> ComplexArray:
    U, _, Uzz = base.velocity(z)
    coefficient = k * k + Uzz.item() / (U.item() - c)
    return np.array([[0.0, 1.0], [coefficient, 0.0]], dtype=np.complex128)


def _rk4_step(
    base: BaseState, k: float, c: complex, z: float, h: float, state: ComplexArray
) -> ComplexArray:
    """Propagate the fundamental solution of psi''=(k²+U''/(U-c))psi."""
    first = _system_matrix(base, k, c, z) @ state
    second = _system_matrix(base, k, c, z + 0.5 * h) @ (state + 0.5 * h * first)
    third = _system_matrix(base, k, c, z + 0.5 * h) @ (state + 0.5 * h * second)
    fourth = _system_matrix(base, k, c, z + h) @ (state + h * third)
    return state + h * (first + 2.0 * second + 2.0 * third + fourth) / 6.0


def _jump_matrix(
    base: BaseState, c: complex, z_interface: float, rho_minus: float, rho_plus: float
) -> ComplexArray:
    """Apply psi continuity and pressure continuity at a sharp-density jump.

    For ``psi`` with ``u=psi'`` and ``w=-i*k*psi``, pressure is
    ``p=rho*((c-U)*psi' + U'*psi)``. Equality of pressure gives the
    derivative jump used below. Gravity and surface tension are zero.
    """
    U, Uz, _ = base.velocity(z_interface)
    derivative_jump = (rho_plus - rho_minus) / rho_plus * Uz.item() / (U.item() - c)
    return np.array(
        [[1.0, 0.0], [derivative_jump, rho_minus / rho_plus]],
        dtype=np.complex128,
    )


def _propagate_segment(
    base: BaseState,
    k: float,
    c: complex,
    start: float,
    end: float,
    steps: int,
    state: ComplexArray,
) -> ComplexArray:
    h = (end - start) / steps
    for index in range(steps):
        state = _rk4_step(base, k, c, start + index * h, h, state)
    return state


def _monodromy(base: BaseState, k: float, c: complex, steps_per_layer: int) -> ComplexArray:
    """Return one-period transfer matrix, splitting exactly at both interfaces."""
    left = -0.5 * base.Lz
    right = 0.5 * base.Lz
    state = np.eye(2, dtype=np.complex128)
    state = _propagate_segment(base, k, c, left, base.z_lower, steps_per_layer, state)
    state = _jump_matrix(base, c, base.z_lower, base.rho_air, base.rho_water) @ state
    state = _propagate_segment(base, k, c, base.z_lower, base.z_upper, steps_per_layer, state)
    state = _jump_matrix(base, c, base.z_upper, base.rho_water, base.rho_air) @ state
    return _propagate_segment(base, k, c, base.z_upper, right, steps_per_layer, state)


def periodic_characteristic(
    base: BaseState, k: float, c: complex, steps_per_layer: int = 256
) -> complex:
    """Return ``trace(monodromy)-2``; its zeros are periodic eigenmodes.

    The two density-jump determinants cancel over one period, so the
    monodromy determinant is one and ``trace(M)=2`` is equivalent to a
    periodic solution. This characteristic is intended for checks and
    root-refinement diagnostics.
    """
    _validate_solve_inputs(k, steps_per_layer)
    return complex(np.trace(_monodromy(base, k, c, steps_per_layer)) - 2.0)


def parity_characteristic(
    base: BaseState,
    k: float,
    c: complex,
    parity: str,
    steps_per_layer: int = 256,
) -> complex:
    """Return a half-period residual for even or odd modes of the symmetric base.

    The paired-tanh profile and density distribution are symmetric about
    ``z=0``. An even streamfunction obeys ``psi_z(Lz/2)=0``; an odd one obeys
    ``psi(Lz/2)=0``. These conditions isolate the two branches whose upper and
    lower interface displacements can be in phase or in opposition.
    """
    _validate_solve_inputs(k, steps_per_layer)
    if parity not in {"even", "odd"}:
        raise ValueError("parity must be 'even' or 'odd'")
    if abs(base.z_lower + base.z_upper) > 1.0e-12 * base.Lz:
        raise ValueError("parity reduction requires interfaces symmetric about z=0")
    state = (
        np.array([1.0, 0.0], dtype=np.complex128)
        if parity == "even"
        else np.array([0.0, 1.0], dtype=np.complex128)
    )
    # The half-domain water path is half the film thickness, so use half as
    # many steps as the full-period water segment for equal RK4 step length.
    state = _propagate_segment(base, k, c, 0.0, base.z_upper, max(1, steps_per_layer // 2), state)
    state = _jump_matrix(base, c, base.z_upper, base.rho_water, base.rho_air) @ state
    state = _propagate_segment(base, k, c, base.z_upper, 0.5 * base.Lz, steps_per_layer, state)
    return complex(state[1] if parity == "even" else state[0])


def _validate_solve_inputs(k: float, steps_per_layer: int) -> None:
    if not np.isfinite(k) or k <= 0:
        raise ValueError("k must be a positive finite streamwise wavenumber")
    if steps_per_layer < 8:
        raise ValueError("steps_per_layer must be at least eight")


def _refine_root(
    base: BaseState,
    k: float,
    initial_c: complex,
    steps_per_layer: int,
    max_iterations: int,
    parity: str | None,
) -> tuple[complex, float, int]:
    c = complex(initial_c)
    if c.imag <= 0.0:
        raise ValueError("initial_c must start in the growing half-plane (Im(c)>0)")

    def characteristic(root: complex) -> complex:
        if parity is None:
            return periodic_characteristic(base, k, root, steps_per_layer)
        return parity_characteristic(base, k, root, parity, steps_per_layer)

    for iteration in range(1, max_iterations + 1):
        value = characteristic(c)
        increment = 2.0e-5 * max(1.0, abs(c))
        derivative = (characteristic(c + increment) - characteristic(c - increment)) / (
            2.0 * increment
        )
        if abs(derivative) <= np.finfo(float).tiny:
            break
        correction = value / derivative
        if abs(correction) > 10.0:
            correction *= 10.0 / abs(correction)

        # Dampen Newton steps that leave the growing half-plane or increase
        # the characteristic residual; this avoids landing on the critical
        # layer of a real-c solution during early iterations.
        accepted = False
        scale = 1.0
        while scale >= 1.0 / 128.0:
            candidate = c - scale * correction
            if candidate.imag > 0.0:
                candidate_value = characteristic(candidate)
                if abs(candidate_value) <= abs(value) or abs(scale * correction) < 1.0e-11:
                    c = candidate
                    accepted = True
                    break
            scale *= 0.5
        if not accepted:
            break
        if abs(scale * correction) <= 2.0e-12 * max(1.0, abs(c)):
            break
    residual = abs(characteristic(c))
    return c, residual, iteration


def _profile_grid(base: BaseState, points_per_layer: int) -> FloatArray:
    # Interface coordinates are included exactly, and no sample duplicates
    # the periodic endpoints.
    intervals = (
        (-0.5 * base.Lz, base.z_lower),
        (base.z_lower, base.z_upper),
        (base.z_upper, 0.5 * base.Lz),
    )
    pieces = [
        np.linspace(left, right, points_per_layer + 1, endpoint=True)[:-1]
        for left, right in intervals
    ]
    return np.concatenate((*pieces, np.array([0.5 * base.Lz])))


def _sample_mode(
    base: BaseState,
    k: float,
    c: complex,
    monodromy: ComplexArray,
    points_per_layer: int,
) -> tuple[
    FloatArray,
    FloatArray,
    FloatArray,
    ComplexArray,
    LayerArray,
    ComplexArray,
    ComplexArray,
    ComplexArray,
    complex,
    complex,
    float,
    float,
]:
    left = -0.5 * base.Lz
    right = 0.5 * base.Lz
    _, _, vh = np.linalg.svd(monodromy - np.eye(2, dtype=np.complex128))
    start_state = vh[-1, :].conj()

    eta_values: list[complex] = []
    profile_states: list[tuple[float, ComplexArray, int]] = []
    current_z = left
    current_state = start_state

    def record_segment(end: float, count: int, layer: int) -> None:
        nonlocal current_z, current_state
        grid = np.linspace(current_z, end, count + 1, endpoint=True)
        grid_state = current_state.copy()
        previous_z = current_z
        profile_states.append((current_z, grid_state.copy(), layer))
        for next_z in grid[1:]:
            grid_state = _propagate_segment(base, k, c, previous_z, float(next_z), 1, grid_state)
            previous_z = float(next_z)
            profile_states.append((previous_z, grid_state.copy(), layer))
        current_z = end
        current_state = grid_state

    record_segment(base.z_lower, points_per_layer, 0)
    lower_psi = current_state[0]
    eta_values.append(lower_psi / (c - base.velocity(base.z_lower)[0].item()))
    current_state = (
        _jump_matrix(base, c, base.z_lower, base.rho_air, base.rho_water) @ current_state
    )
    record_segment(base.z_upper, points_per_layer, 1)
    upper_psi = current_state[0]
    eta_values.append(upper_psi / (c - base.velocity(base.z_upper)[0].item()))
    current_state = (
        _jump_matrix(base, c, base.z_upper, base.rho_water, base.rho_air) @ current_state
    )
    record_segment(right, points_per_layer, 2)

    raw_z = np.array([item[0] for item in profile_states], dtype=np.float64)
    raw_state = np.array([item[1] for item in profile_states], dtype=np.complex128)
    raw_layer = np.array([item[2] for item in profile_states], dtype=np.int8)
    # Duplicate z coordinates at sharp interfaces preserve both one-sided
    # tangential velocity traces. Consumers should interpolate separately by
    # ``layer``; interpolating across the duplicate would smear the jump.
    z = raw_z
    state = raw_state
    layer = raw_layer
    psi = state[:, 0]
    psi_z = state[:, 1]
    U, _, _ = base.velocity(z)
    rho = np.choose(layer, [base.rho_air, base.rho_water, base.rho_air]).astype(np.float64)

    normalization = max(abs(value) for value in eta_values)
    if normalization == 0.0:
        raise ArithmeticError("eigenvector has zero interface displacement")
    psi = psi / normalization
    psi_z = psi_z / normalization
    eta_lower, eta_upper = (value / normalization for value in eta_values)
    psi = psi.astype(np.complex128)
    u = psi_z.astype(np.complex128)
    w = (-1j * k * psi).astype(np.complex128)
    pressure = rho * ((c - U) * psi_z + base.velocity(z)[1] * psi)

    sampled_end_state = current_state
    periodic_error = np.linalg.norm(sampled_end_state - start_state) / max(
        np.linalg.norm(start_state), np.linalg.norm(sampled_end_state), 1.0
    )
    transfer_end_state = monodromy @ start_state
    transfer_error = np.linalg.norm(transfer_end_state - start_state) / max(
        np.linalg.norm(start_state), np.linalg.norm(transfer_end_state), 1.0
    )
    return (
        z,
        U,
        rho,
        psi,
        layer,
        u,
        w,
        pressure,
        eta_lower,
        eta_upper,
        float(periodic_error),
        float(transfer_error),
    )


def interpolate_mode(
    mode: Eigenpair,
    z: FloatArray | float,
    *,
    layer: int | NDArray[np.int8],
    field: str = "u",
) -> ComplexArray | FloatArray | complex | float:
    """Interpolate one modal field without crossing a sharp interface.

    ``layer`` is 0 for air below, 1 for water, and 2 for air above. Supplying
    the layer is mandatory because ``u=psi_z`` may jump at a density
    interface. The sampled arrays include duplicate interface coordinates,
    one for each one-sided trace; interpolation is performed independently in
    each layer.
    """
    if field not in {"U", "rho", "psi", "u", "w", "p"}:
        raise ValueError("field must be one of U, rho, psi, u, w, p")
    target_z = np.asarray(z, dtype=np.float64)
    layer_array = np.asarray(layer, dtype=np.int8)
    if layer_array.ndim == 0:
        layer_array = np.full(target_z.shape, int(layer_array), dtype=np.int8)
    if layer_array.shape != target_z.shape:
        raise ValueError("layer must be a scalar or have the same shape as z")
    if np.any((layer_array < 0) | (layer_array > 2)):
        raise ValueError("layer values must be 0 (lower air), 1 (water), or 2 (upper air)")
    source = getattr(mode, field)
    result_dtype = np.complex128 if np.iscomplexobj(source) else np.float64
    result = np.empty(target_z.shape, dtype=result_dtype)
    for layer_id in (0, 1, 2):
        selected = layer_array == layer_id
        if not np.any(selected):
            continue
        source_mask = mode.layer == layer_id
        source_z = mode.z[source_mask]
        if np.any(target_z[selected] < source_z[0] - 1.0e-12) or np.any(
            target_z[selected] > source_z[-1] + 1.0e-12
        ):
            raise ValueError(f"target z lies outside sampled layer {layer_id}")
        values = source[source_mask]
        if np.iscomplexobj(values):
            real = np.interp(target_z[selected], source_z, values.real)
            imag = np.interp(target_z[selected], source_z, values.imag)
            result[selected] = real + 1j * imag
        else:
            result[selected] = np.interp(target_z[selected], source_z, values)
    if target_z.ndim == 0:
        return result.item()
    return result


def _interface_checks(
    mode_arrays: tuple[
        FloatArray,
        FloatArray,
        FloatArray,
        ComplexArray,
        LayerArray,
        ComplexArray,
        ComplexArray,
        ComplexArray,
    ],
    base: BaseState,
    k: float,
    c: complex,
    eta_lower: complex,
    eta_upper: complex,
) -> list[dict[str, float]]:
    z, U, rho, psi, layer, u, w, pressure = mode_arrays
    checks: list[dict[str, Any]] = []
    for label, z_interface, lower_layer, upper_layer, eta in (
        ("lower", base.z_lower, 0, 1, eta_lower),
        ("upper", base.z_upper, 1, 2, eta_upper),
    ):
        lower_index = np.flatnonzero((layer == lower_layer) & np.isclose(z, z_interface))[-1]
        upper_index = np.flatnonzero((layer == upper_layer) & np.isclose(z, z_interface))[0]
        velocity, velocity_z, _ = base.velocity(z_interface)
        rho_minus = float(rho[lower_index])
        rho_plus = float(rho[upper_index])
        expected_u_plus = (
            rho_minus / rho_plus * u[lower_index]
            + (rho_plus - rho_minus)
            / rho_plus
            * velocity_z.item()
            / (velocity.item() - c)
            * psi[lower_index]
        )
        scales = {
            "psi": max(abs(psi[lower_index]), abs(psi[upper_index]), 1.0e-30),
            "w": max(abs(w[lower_index]), abs(w[upper_index]), 1.0e-30),
            "p": max(abs(pressure[lower_index]), abs(pressure[upper_index]), 1.0e-30),
            "u": max(abs(u[upper_index]), abs(expected_u_plus), 1.0e-30),
            "kinematic": max(abs(w[lower_index]), abs(k * (velocity.item() - c) * eta), 1.0e-30),
        }
        kinematic_velocity = 1j * k * (velocity.item() - c) * eta
        checks.append(
            {
                "interface": label,
                "psi_continuity_relative_residual": float(
                    abs(psi[upper_index] - psi[lower_index]) / scales["psi"]
                ),
                "normal_velocity_continuity_relative_residual": float(
                    abs(w[upper_index] - w[lower_index]) / scales["w"]
                ),
                "pressure_continuity_relative_residual": float(
                    abs(pressure[upper_index] - pressure[lower_index]) / scales["p"]
                ),
                "kinematic_condition_relative_residual": float(
                    abs(w[lower_index] - kinematic_velocity) / scales["kinematic"]
                ),
                "tangential_velocity_jump_relative_residual": float(
                    abs(u[upper_index] - expected_u_plus) / scales["u"]
                ),
                "u_minus_abs_m_s": float(abs(u[lower_index])),
                "u_plus_abs_m_s": float(abs(u[upper_index])),
                "w_abs_m_s_per_m_displacement": float(abs(w[lower_index])),
            }
        )
    return checks


def solve_periodic_mode(
    base_state: BaseState | None = None,
    k: float | None = None,
    *,
    steps_per_layer: int = 512,
    points_per_layer: int = 512,
    initial_c: complex | None = None,
    parity: str | None = "even",
    max_iterations: int = 40,
) -> Eigenpair:
    """Solve and sample one growing periodic eigenmode.

    ``steps_per_layer`` is used in each outer air segment and across the full
    central water film. The half-period parity solve uses half that number
    over the half-thickness water segment. ``parity`` selects the symmetric
    (``"even"``) or antisymmetric
    (``"odd"``) branch for a reflection-symmetric base; use ``None`` for the
    full-period characteristic. ``initial_c`` selects a root; when omitted,
    the deterministic seed targets a heavy-liquid/low-speed branch.

    The returned mode is normalized so the larger of the two interface
    displacement magnitudes is exactly 1 m. Scale all modal fields and both
    ``eta`` values together to prescribe a physical seed amplitude.
    """
    base = BaseState() if base_state is None else base_state
    streamwise_k = 2.0 * np.pi / 0.12 if k is None else float(k)
    _validate_solve_inputs(streamwise_k, steps_per_layer)
    if points_per_layer < 8:
        raise ValueError("points_per_layer must be at least eight")
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    if parity not in {None, "even", "odd"}:
        raise ValueError("parity must be 'even', 'odd', or None")
    if initial_c is None:
        delta_u = base.U_air - base.U_water
        initial_c = base.U_water + (0.12 + 0.12j) * delta_u

    # A uniform-velocity state has no growing shear mode. Treat the known
    # analytic limit explicitly instead of asking a critical-layer root solver
    # to resolve the degenerate c=U neutral continuum.
    _, base_shear, _ = base.velocity(np.linspace(-0.5 * base.Lz, 0.5 * base.Lz, 129))
    if np.max(np.abs(base_shear)) <= 1.0e-13:
        raise NoUnstableModeError("uniform velocity has only neutral advection modes")

    c, characteristic_residual, iterations = _refine_root(
        base, streamwise_k, initial_c, steps_per_layer, max_iterations, parity
    )
    if c.imag <= 0.0 or characteristic_residual > 1.0e-7:
        raise NoUnstableModeError(
            f"no converged growing root from initial_c={initial_c!r}; "
            f"Im(c)={c.imag:.6g}, characteristic residual={characteristic_residual:.3g}"
        )
    monodromy = _monodromy(base, streamwise_k, c, steps_per_layer)
    (
        z,
        U,
        rho,
        psi,
        layer,
        u,
        w,
        pressure,
        eta_lower,
        eta_upper,
        periodic_error,
        transfer_error,
    ) = _sample_mode(base, streamwise_k, c, monodromy, points_per_layer)
    sigma = -1j * streamwise_k * c
    growth = float(sigma.real)
    determinant = complex(np.linalg.det(monodromy))
    interface_residuals = _interface_checks(
        (z, U, rho, psi, layer, u, w, pressure),
        base,
        streamwise_k,
        c,
        eta_lower,
        eta_upper,
    )
    eta_ratio = eta_upper / eta_lower
    metadata: dict[str, Any] = {
        "convention": "exp(i*k*x + sigma*t); sigma=-i*k*c",
        "coordinate_frame": "x streamwise, z cross-shear; 2-D mode, invariant in y",
        "streamwise_wavenumber_rad_m": streamwise_k,
        "streamwise_wavelength_m": 2.0 * np.pi / streamwise_k,
        "normalization": "max(abs(eta_lower),abs(eta_upper)) = 1 m",
        "array_sampling": "duplicate z rows at sharp interfaces retain both one-sided traces; layer 0=air below, 1=water, 2=air above",
        "base_state": base.as_dict(),
        "method": "piecewise-density Rayleigh ODE; RK4 transfer matrix and pressure/kinematic jumps",
        "reflection_parity": parity,
        "rk4_steps_per_outer_air_segment": steps_per_layer,
        "rk4_steps_across_water_film": steps_per_layer,
        "profile_points_per_outer_air_segment": points_per_layer,
        "profile_points_across_water_film": points_per_layer,
        "newton_iterations": iterations,
        "characteristic_residual_abs": characteristic_residual,
        "full_period_characteristic_residual_abs": abs(np.trace(monodromy) - 2.0),
        "periodic_boundary_relative_residual": periodic_error,
        "transfer_boundary_relative_residual": transfer_error,
        "interface_matching_residuals": interface_residuals,
        "monodromy_determinant": {"real": determinant.real, "imag": determinant.imag},
        "omega_rad_s": {"real": (streamwise_k * c).real, "imag": (streamwise_k * c).imag},
        "phase_speed_m_s": {"real": c.real, "imag": c.imag},
        "growth_e_folding_time_s": 1.0 / growth,
        "eta_lower_m": {"real": eta_lower.real, "imag": eta_lower.imag},
        "eta_upper_m": {"real": eta_upper.real, "imag": eta_upper.imag},
        "eta_upper_over_lower": {"real": eta_ratio.real, "imag": eta_ratio.imag},
        "governing_reference": {
            "citation": "Alexakis, Young & Rosner, Physical Review E 65, 026313 (2002), DOI 10.1103/PhysRevE.65.026313",
            "local_or_author_pdf": "https://www.phys.ens.psl.eu/~alexakis/PAPERS/PhysRevE.WindWaves.pdf",
            "provenance": "page 2, equations 2.7-2.10: piecewise Rayleigh ODE, kinematic interface condition, and pressure continuity; this module extends the two-interface zero-gravity/zero-surface-tension problem periodically",
        },
        "input_provenance": "assumed exploratory values from cases/cpu_interface_growth/experiment.json; no parameter is a measured Dash-8 property",
        "limits": [
            "inviscid linear stability only; molecular viscosity omitted",
            "surface tension and gravity set to zero",
            "sharp density interfaces with continuous base U and U'",
            "no finite-amplitude breakup, turbulence, or Dash-8 validation claim",
        ],
    }
    # The root's normalized singular-vector mismatch is the public residual;
    # retain the characteristic residual in metadata as an independent check.
    return Eigenpair(
        z=z,
        U=U.astype(np.float64),
        rho=rho,
        psi=psi,
        layer=layer,
        u=u,
        w=w,
        p=pressure.astype(np.complex128),
        eta_lower=complex(eta_lower),
        eta_upper=complex(eta_upper),
        k=streamwise_k,
        sigma=complex(sigma),
        growth=growth,
        residual=max(periodic_error, transfer_error),
        metadata=metadata,
    )
