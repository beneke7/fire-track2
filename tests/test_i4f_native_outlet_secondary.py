from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from aerial_drop.i4f_native_face_reader import (
    TARGET_X_M,
    _interpolate_owner_weighted,
    _local_face_cells_in_global_cut_order,
    _openfoam_linear_weight,
    _orient_local_internal_flux,
    _parse_internal,
    _read_water_density_model,
    _select_native_mouth_cut,
    _water_density_from_pressure,
    read_native_mouth_snapshot,
)

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/analyze_i4f_native_outlet_secondary.py"
SPEC = importlib.util.spec_from_file_location("i4f_native_outlet_secondary", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


def _face(q: float, velocity: list[float], area: float, alpha: float) -> dict[str, object]:
    return {
        "native_water_flux_m3_s": q,
        "velocity_face_xyz_m_s": velocity,
        "outward_projected_area_m2": area,
        "alpha_water_face_raw": alpha,
    }


def test_adapter_preserves_signed_native_flux_and_reconstructed_momentum() -> None:
    result = ADAPTER.summarize_face_inputs(
        {
            "A_lower": [
                _face(1.2, [3.0, 0.0, 4.0], 0.15, 0.9),
                _face(-0.2, [-1.0, 0.0, 0.0], 0.15, 0.2),
            ]
        },
        time_s=0.5,
        case_label="synthetic-adapter-check",
    )[0]

    assert result["native_alphaPhi0_water_Q_net_m3_s"] == 1.0
    assert result["native_alphaPhi0_water_Q_absolute_m3_s"] == 1.4
    assert result["native_area_projected_x_m2"] == 0.3
    helper = result["secondary_metrics_helper_raw"]
    assert helper["outward_direction_mean_angle_deg_q_weighted"] == 53.13010235415599
    assert helper["water_momentum_flux_net_reconstructed_N_xyz"] == pytest.approx(
        [998.2 * 3.8, 0.0, 998.2 * 4.8]
    )


def test_adapter_suppresses_interpretation_of_dry_numerical_trace() -> None:
    result = ADAPTER.summarize_face_inputs(
        {"B_upper": [_face(1e-205, [2.0, 0.0, 0.0], 0.15, 0.0)]},
        time_s=0.05,
        case_label="synthetic-dry-trace-check",
    )[0]

    assert result["flux_state"] == "dry_or_near_zero_native_liquid_trace"
    assert result["native_alphaPhi0_water_Q_net_m3_s"] == 1e-205
    assert (
        result["reported_secondary_metrics"]["outward_direction_mean_angle_deg_q_weighted"] is None
    )
    assert (
        result["secondary_metrics_helper_raw"]["outward_direction_mean_angle_deg_q_weighted"] == 0.0
    )


def test_adapter_passes_per_face_water_density_to_metrics() -> None:
    result = ADAPTER.summarize_face_inputs(
        {
            "A_lower": [
                _face(2.0, [1.0, 0.0, 0.0], 0.1, 1.0) | {"water_density_kg_m3": 1000.0},
                _face(-1.0, [-2.0, 0.0, 0.0], 0.1, 1.0) | {"water_density_kg_m3": 500.0},
            ]
        },
        time_s=0.5,
        case_label="synthetic-per-face-density",
    )[0]

    helper = result["secondary_metrics_helper_raw"]
    assert helper["water_density_model"] == "per_face"
    assert helper["water_mass_flux_net_kg_s"] == pytest.approx(1500.0)
    assert helper["water_momentum_flux_net_reconstructed_N_xyz"] == pytest.approx(
        [3000.0, 0.0, 0.0]
    )


def test_native_reader_binary_scalar_and_cut_orientation_helpers() -> None:
    values = np.asarray([0.25, 1.0], dtype="<f8")
    chunk = (
        b"FoamFile { format      binary; }\n"
        b"internalField nonuniform List<scalar> 2 (" + values.tobytes() + b"\n);\n"
    )
    np.testing.assert_array_equal(_parse_internal(chunk, "scalar"), values)

    center = np.asarray([0.0, 0.0, 0.0])
    owner = np.asarray([-0.25, 0.0, 0.0])
    neighbour = np.asarray([0.75, 0.0, 0.0])
    weight = _openfoam_linear_weight(np.asarray([2.0, 0.0, 0.0]), center, owner, neighbour)
    reversed_weight = _openfoam_linear_weight(
        np.asarray([-2.0, 0.0, 0.0]), center, owner, neighbour
    )
    assert weight == pytest.approx(0.75)
    assert reversed_weight == pytest.approx(weight)

    # OpenFOAM's returned weight is the owner contribution. The real
    # reconstruction path must preserve an asymmetric linear field exactly.
    # f(x)=x at face x=0 between owner x=-0.25 and neighbour x=0.75 is 0.
    reconstructed = _interpolate_owner_weighted(-0.25, 0.75, weight)
    assert reconstructed == pytest.approx(0.0, abs=1e-15)

    # A negative faceProcAddressing sign reverses the local face orientation
    # before the global owner/inside relation is applied.
    assert _orient_local_internal_flux(2.0, 1, True) == pytest.approx(2.0)
    assert _orient_local_internal_flux(2.0, -1, True) == pytest.approx(-2.0)
    assert _orient_local_internal_flux(2.0, 1, False) == pytest.approx(-2.0)
    assert _orient_local_internal_flux(2.0, -1, False) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="invalid signed faceProcAddressing"):
        _orient_local_internal_flux(2.0, 0, True)
    assert _local_face_cells_in_global_cut_order(20, 10, -1, True) == (10, 20)
    assert _local_face_cells_in_global_cut_order(20, 10, -1, False) == (20, 10)
    assert _local_face_cells_in_global_cut_order(10, 20, 1, True) == (10, 20)

    with pytest.raises(ValueError, match="scoped to 10-rank"):
        read_native_mouth_snapshot(Path("/not/a/case"), "0.5", nprocs=20)


def test_native_mouth_x_moves_cut_and_preserves_signed_fluxes() -> None:
    # Four independent three-cell rows straddle the same fixed mouth windows.
    # Their two internal face planes are at x=4.6 and x=4.8 m.
    mouth_yz = ((-0.55, 0.65), (-0.55, 0.90), (0.55, 0.65), (0.55, 0.90))
    centers = []
    owners = []
    neighbours = []
    points = []
    face_offsets = [0]
    face_labels = []
    for mouth_index, (y, z) in enumerate(mouth_yz):
        cell_start = 3 * mouth_index
        centers.extend(([4.5, y, z], [4.7, y, z], [4.9, y, z]))
        for offset, x in enumerate((4.6, 4.8)):
            owners.append(cell_start + offset)
            neighbours.append(cell_start + offset + 1)
            vertex_start = len(points)
            half_width = 0.04
            points.extend(
                (
                    [x, y - half_width, z - half_width],
                    [x, y + half_width, z - half_width],
                    [x, y + half_width, z + half_width],
                    [x, y - half_width, z + half_width],
                )
            )
            face_labels.extend(range(vertex_start, vertex_start + 4))
            face_offsets.append(len(face_labels))

    centers = np.asarray(centers, dtype=np.float64)
    owners = np.asarray(owners, dtype=np.int64)
    neighbours = np.asarray(neighbours, dtype=np.int64)
    points = np.asarray(points, dtype=np.float64)
    face_offsets = np.asarray(face_offsets, dtype=np.int64)
    face_labels = np.asarray(face_labels, dtype=np.int64)

    inside_46, faces_46 = _select_native_mouth_cut(
        centers, owners, neighbours, face_offsets, face_labels, points, 4.6
    )
    inside_48, faces_48 = _select_native_mouth_cut(
        centers, owners, neighbours, face_offsets, face_labels, points, 4.8
    )

    assert TARGET_X_M == pytest.approx(4.8)  # the public default is unchanged
    assert set(faces_46) == {0, 2, 4, 6}
    assert set(faces_48) == {1, 3, 5, 7}
    assert {face["mouth"] for face in faces_46.values()} == {
        "A_lower",
        "A_upper",
        "B_lower",
        "B_upper",
    }
    assert {face["mouth"] for face in faces_48.values()} == {
        "A_lower",
        "A_upper",
        "B_lower",
        "B_upper",
    }

    # Exercise the production signed-face orientation on the faces selected at
    # each cut. Opposite local map signs and reverse-flow values must remain
    # signed, and the cut must switch from the x=4.6 face to x=4.8 face.
    local_phi = {0: 1.0, 1: 5.0, 2: -2.0, 3: -6.0, 4: -3.0, 5: -7.0, 6: 4.0, 7: 8.0}
    face_map_sign = {0: 1, 1: 1, 2: -1, 3: -1, 4: 1, 5: 1, 6: -1, 7: -1}

    def mouth_q(inside: np.ndarray, selected: dict[int, dict[str, object]]) -> dict[str, float]:
        result = {}
        for face_id, geometry in selected.items():
            owner_inside = bool(inside[owners[face_id]])
            assert owner_inside
            mouth = str(geometry["mouth"])
            result[mouth] = _orient_local_internal_flux(
                local_phi[face_id], face_map_sign[face_id], owner_inside
            )
        return result

    assert mouth_q(inside_46, faces_46) == {
        "A_lower": 1.0,
        "A_upper": 2.0,
        "B_lower": -3.0,
        "B_upper": -4.0,
    }
    assert mouth_q(inside_48, faces_48) == {
        "A_lower": 5.0,
        "A_upper": 6.0,
        "B_lower": -7.0,
        "B_upper": -8.0,
    }

    with pytest.raises(ValueError, match="mouth_x_m must be a finite number"):
        _select_native_mouth_cut(
            centers, owners, neighbours, face_offsets, face_labels, points, np.nan
        )
    with pytest.raises(ValueError, match="no native internal faces straddle"):
        _select_native_mouth_cut(
            centers, owners, neighbours, face_offsets, face_labels, points, 10.0
        )


def test_water_density_eos_and_density_is_interpolated_after_cellwise_evaluation(
    tmp_path: Path,
) -> None:
    water = tmp_path / "thermophysicalProperties.water"
    water.write_text(
        """
        thermoType
        {
            type heRhoThermo;
            equationOfState adiabaticPerfectFluid;
        }
        mixture
        {
            equationOfState
            {
                p0 100000;
                rho0 998.2;
                gamma 7.15;
                B 306667767.13022316;
            }
        }
        """
    )
    model = _read_water_density_model(water)
    assert model["model"] == "adiabaticPerfectFluid"
    assert model["source_sha256"]

    cell_pressure = np.asarray([100_000.0, 1_300_000.0])
    cell_density = _water_density_from_pressure(cell_pressure, model)
    owner_weight = 0.75
    face_density = _interpolate_owner_weighted(cell_density[0], cell_density[1], owner_weight)
    interpolated_pressure = (
        owner_weight * cell_pressure[0] + (1.0 - owner_weight) * cell_pressure[1]
    )
    eos_of_face_pressure = _water_density_from_pressure(np.asarray([interpolated_pressure]), model)[
        0
    ]

    assert cell_density[0] == pytest.approx(998.2)
    assert face_density == pytest.approx(
        owner_weight * cell_density[0] + (1.0 - owner_weight) * cell_density[1]
    )
    assert abs(face_density - eos_of_face_pressure) > 1e-4


def test_water_density_reader_supports_rho_const_and_rejects_unknown_eos(tmp_path: Path) -> None:
    water = tmp_path / "thermophysicalProperties.water"
    water.write_text(
        "thermoType { equationOfState rhoConst; }\nmixture { equationOfState { rho 998.2; } }\n"
    )
    model = _read_water_density_model(water)
    density = _water_density_from_pressure(np.asarray([100_000.0, 1_300_000.0]), model)
    np.testing.assert_allclose(density, [998.2, 998.2])

    water.write_text(
        "thermoType { equationOfState unsupportedEOS; }\n"
        "mixture { equationOfState { rho 998.2; } }\n"
    )
    with pytest.raises(ValueError, match="unsupported water equationOfState"):
        _read_water_density_model(water)
