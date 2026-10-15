"""Independent finite-volume and interface-observer audit checks."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.audit_interface_wave_flux import (
    AuditError,
    MeshAddressing,
    Patch,
    alpha_half_crossing_mode,
    finite_volume_divergence,
    phi_ascii_quantization_bound,
    read_volume_vector_internal,
    structured_periodic_gauss_divergence,
    volume_interface_mode,
)
from scripts.run_cpu_interface_growth import V2_LENGTHS, alpha_seed_v2


def test_owner_oriented_face_balance_counts_cyclic_faces_once() -> None:
    # One internal face 0 -> 1 and two cyclic boundary faces; all three
    # oriented fluxes close the periodic two-cell ring.
    owner = np.array([0, 0, 1])
    neighbour = np.array([1])
    phi = np.array([5.0, -5.0, 5.0])
    divergence = finite_volume_divergence(owner, neighbour, phi, np.ones(2))
    np.testing.assert_allclose(divergence, 0.0, atol=0.0)


def test_open_boundary_flux_matches_integrated_fv_divergence() -> None:
    owner = np.array([0, 1])
    divergence = finite_volume_divergence(
        owner, np.array([], dtype=int), np.array([2.0, -3.0]), np.array([2.0, 1.0])
    )
    assert np.dot(np.array([2.0, 1.0]), divergence) == pytest.approx(-1.0)


def test_periodic_linear_face_interpolation_keeps_flat_shear_divergence_free() -> None:
    nx, ny, nz = 8, 4, 12
    z = (np.arange(nz) + 0.5) / nz
    grid = np.zeros((nz, ny, nx, 3))
    grid[..., 0] = (0.3 + np.tanh((z - 0.25) * 9.0))[:, None, None]
    divergence = structured_periodic_gauss_divergence(
        grid.reshape((-1, 3)), (nx, ny, nz), (0.12 / nx, 0.06 / ny, 0.12 / nz)
    )
    np.testing.assert_allclose(divergence, 0.0, atol=0.0)


def test_phi_ascii_rounding_bound_accounts_for_owner_and_neighbour() -> None:
    mesh = MeshAddressing(
        owner=np.array([0, 0, 1]),
        neighbour=np.array([1]),
        patches=(
            Patch("xMin", "cyclic", 1, 1, "xMax"),
            Patch("xMax", "cyclic", 2, 1, "xMin"),
        ),
        n_cells=2,
    )
    bound = phi_ascii_quantization_bound(mesh, np.array([4.4e-5, -4.4e-5, 4.4e-5]), np.ones(2), 12)
    assert bound[0] > 0.0
    assert bound[1] > 0.0
    assert bound[0] == pytest.approx(bound[1])


def test_vector_field_reader_accepts_ascii_nonuniform_values(tmp_path: Path) -> None:
    path = tmp_path / "U"
    path.write_text(
        """FoamFile
{
    class volVectorField;
    object U;
}
dimensions [0 1 -1 0 0 0 0];
internalField nonuniform List<vector> 2
(
(1 2 3)
(-4.5e-2 0 8)
);
boundaryField {}
"""
    )
    result = read_volume_vector_internal(path, 2)
    np.testing.assert_allclose(result, [[1.0, 2.0, 3.0], [-0.045, 0.0, 8.0]])


@pytest.mark.parametrize("mesh", [(128, 64, 128), (192, 96, 192)])
@pytest.mark.parametrize("amplitude_m", [1.5e-4, 5e-5, 2.5e-5])
def test_two_alpha_observers_recover_small_seed_on_both_meshes(
    mesh: tuple[int, int, int], amplitude_m: float
) -> None:
    nx, ny, nz = mesh
    alpha = alpha_seed_v2(nx, ny, nz, amplitude_m=amplitude_m)
    cell_size = tuple(length / count for length, count in zip(V2_LENGTHS, mesh, strict=True))
    volume = volume_interface_mode(alpha.reshape(-1), mesh, cell_size)
    contour = alpha_half_crossing_mode(alpha.reshape(-1), mesh, cell_size)
    assert volume["symmetric_amplitude_m"] == pytest.approx(amplitude_m, rel=6e-4)
    assert contour["symmetric_amplitude_m"] == pytest.approx(amplitude_m, rel=1e-3)
    assert contour["transverse_coverage_fraction"] == {"lower": 1.0, "upper": 1.0}
    assert contour["crossings_per_x_column"]["lower"]["minimum"] == ny
    assert contour["crossings_per_x_column"]["upper"]["maximum"] == ny


def test_alpha_half_contour_requires_the_expected_crossing_direction() -> None:
    mesh = (16, 4, 32)
    nx, ny, nz = mesh
    original = alpha_seed_v2(nx, ny, nz, amplitude_m=5e-5)
    inverted = 1.0 - original
    cell_size = tuple(length / count for length, count in zip(V2_LENGTHS, mesh, strict=True))
    with pytest.raises(AuditError, match="directed alpha=0.5"):
        alpha_half_crossing_mode(inverted, mesh, cell_size)
