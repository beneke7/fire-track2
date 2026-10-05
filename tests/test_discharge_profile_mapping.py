from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/map_discharge_profile.py"
SPEC = importlib.util.spec_from_file_location("discharge_profile_mapping", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load profile mapper at {SCRIPT}")
mapper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mapper
SPEC.loader.exec_module(mapper)


def _bounds(xs: list[tuple[float, float]], ys: list[tuple[float, float]], z: float) -> np.ndarray:
    return np.asarray(
        [[x0, y0, z, x1, y1, z] for y0, y1 in ys for x0, x1 in xs],
        dtype=np.float64,
    )


def _mixed_grid_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # Source axes are x=transverse and y=streamwise.  After the requested swap,
    # each coarse target rectangle spans two source samples.
    source_bounds = _bounds([(0.0, 1.0), (1.0, 2.0)], [(0.0, 1.0), (1.0, 2.0)], 0.0)
    alpha = np.asarray([1.0, 0.2, 0.5, 0.8])
    velocity = np.asarray(
        [
            [2.0, 10.0, -3.0],
            [4.0, 12.0, -7.0],
            [5.0, 15.0, -4.0],
            [8.0, 18.0, -9.0],
        ]
    )
    target_bounds = np.asarray(
        [
            [10.0, -4.0, 5.0, 12.0, -3.0, 5.0],
            [10.0, -3.0, 5.0, 12.0, -2.0, 5.0],
        ]
    )
    target_areas = np.asarray([2.0, 2.0])
    return source_bounds, velocity, alpha, target_bounds, target_areas


def _map_mixed_grid() -> dict:
    source_bounds, velocity, alpha, target_bounds, target_areas = _mixed_grid_inputs()
    return mapper.map_discharge_profile(
        source_bounds,
        velocity,
        alpha,
        target_bounds,
        target_areas,
        source_origin_xyz_m=(0.0, 0.0, 0.0),
        target_origin_xyz_m=(10.0, -4.0, 5.0),
        profile_time_s=0.5,
    )


def test_unequal_grids_conserve_alpha_transport_and_mean_components() -> None:
    result = _map_mixed_grid()
    summary = result["summary"]
    source = summary["source_integrated_proxies"]
    target = summary["target_reconstructed_from_mapped_alpha_and_phase_velocity"]
    conservative = summary["target_conservative_overlap_moments"]

    assert result["profile_time_s"] == 0.5
    assert result["overlap_target_face_index"].tolist() == [0, 0, 1, 1]
    assert result["overlap_area_m2"].tolist() == [1.0, 1.0, 1.0, 1.0]
    assert result["target_face_alpha"].tolist() == pytest.approx([0.75, 0.5])
    assert target["water_volume_transport_proxy_m3_s"] == pytest.approx(
        source["water_volume_transport_proxy_m3_s"]
    )
    assert target["water_mass_transport_proxy_kg_s"] == pytest.approx(
        source["water_mass_transport_proxy_kg_s"]
    )
    assert conservative["area_mean_velocity_xyz_m_s"] == pytest.approx(
        source["area_mean_velocity_xyz_m_s"]
    )
    assert conservative["convective_momentum_transport_proxy_N_xyz"] == pytest.approx(
        source["convective_momentum_transport_proxy_N_xyz"]
    )
    assert conservative["convective_kinetic_energy_transport_proxy_W"] == pytest.approx(
        source["convective_kinetic_energy_transport_proxy_W"]
    )

    # Independent averaging of alpha and U would lose this covariance and fail
    # to preserve the integral alpha*U_n transport proxy.
    naive_flux = 1000.0 * np.sum(
        np.asarray([2.0, 2.0])
        * result["target_face_alpha"]
        * (result["target_face_area_mean_velocity_xyz_m_s"] @ np.asarray([0.0, 0.0, -1.0]))
    )
    assert naive_flux != pytest.approx(source["water_mass_transport_proxy_kg_s"])
    assert summary["smoothing_diagnostics"][
        "reconstructed_momentum_proxy_delta_target_minus_source_N_xyz"
    ] != pytest.approx([0.0, 0.0, 0.0])
    assert (
        summary["smoothing_diagnostics"][
            "kinetic_energy_proxy_smoothing_loss_source_minus_reconstructed_W"
        ]
        > 0.0
    )


def test_axis_swap_translation_and_vertical_sign_are_explicit() -> None:
    result = mapper.map_discharge_profile(
        [[1.0, 3.0, 0.0, 3.0, 5.0, 0.0]],
        [[3.0, 7.0, -5.0]],
        [1.0],
        [[9.0, -2.0, 5.0, 11.0, 0.0, 5.0]],
        [4.0],
        source_origin_xyz_m=(2.0, 4.0, 0.0),
        target_origin_xyz_m=(10.0, -1.0, 5.0),
        profile_time_s=0.0,
    )
    assert result["target_face_velocity_xyz_m_s"][0].tolist() == pytest.approx([7.0, 3.0, -5.0])
    assert result["transformed_source_face_bounds_xyz_m"][0].tolist() == pytest.approx(
        [9.0, -2.0, 5.0, 11.0, 0.0, 5.0]
    )
    coords = result["summary"]["coordinate_mapping"]
    assert coords["source_to_target_matrix"] == [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    assert coords["origin_translation_xyz_m"] == pytest.approx([6.0, -3.0, 5.0])
    assert result["summary"]["source_integrated_proxies"][
        "water_volume_transport_proxy_m3_s"
    ] == pytest.approx(20.0)


def test_zero_startup_profile_is_supported_without_division_by_zero() -> None:
    result = mapper.map_discharge_profile(
        [[0.0, 0.0, 0.0, 1.0, 1.0, 0.0]],
        [[0.0, 0.0, 0.0]],
        [0.0],
        [[0.0, 0.0, -2.0, 1.0, 1.0, -2.0]],
        [1.0],
        source_origin_xyz_m=(0.5, 0.5, 0.0),
        target_origin_xyz_m=(0.5, 0.5, -2.0),
        profile_time_s=0.0,
    )
    assert result["target_face_alpha"].tolist() == [0.0]
    assert result["target_face_velocity_xyz_m_s"].tolist() == [[0.0, 0.0, 0.0]]
    assert result["summary"]["source_integrated_proxies"]["water_mass_transport_proxy_kg_s"] == 0.0


def test_gap_or_uncovered_source_faces_are_rejected() -> None:
    source = [[0, 0, 0, 0.8, 1, 0], [1.2, 0, 0, 2, 1, 0]]
    target = [[0, 0, 0, 2, 1, 0]]
    with pytest.raises(ValueError, match="do not tile"):
        mapper.map_discharge_profile(
            source,
            [[0, 0, -1], [0, 0, -1]],
            [1, 1],
            target,
            [2],
            source_origin_xyz_m=(0, 0, 0),
            target_origin_xyz_m=(0, 0, 0),
            profile_time_s=0.2,
        )


def test_overlapping_faces_are_rejected_even_if_overlap_balances_a_gap() -> None:
    # The upper-left square is duplicated while the equal-area upper-right
    # square is missing, so the global area sum alone would appear valid.
    with pytest.raises(ValueError, match="overlap with positive area"):
        mapper.map_discharge_profile(
            [
                [0, 0, 0, 1, 1, 0],
                [1, 0, 0, 2, 1, 0],
                [0, 1, 0, 1, 2, 0],
                [0, 1, 0, 1, 2, 0],
            ],
            [[0, 0, -1]] * 4,
            [1] * 4,
            [[0, 0, -1, 2, 2, -1]],
            [4],
            source_origin_xyz_m=(0, 0, 0),
            target_origin_xyz_m=(0, 0, -1),
            profile_time_s=0.2,
        )


@pytest.mark.parametrize(
    ("source_bounds", "target_bounds", "target_areas", "message"),
    [
        ([[0, 0, 0, 1, 1, 0.01]], [[0, 0, -1, 1, 1, -1]], [1], "planar rectangles"),
        ([[0, 0, 0, 1, 1, 0]], [[0, 0, -1, 1, 1, -1]], [1.2], "area does not match"),
        ([[0, 0, 0, 1, 1, 0]], [[0.1, 0, -1, 1.1, 1, -1]], [1], "bounds do not match"),
    ],
)
def test_malformed_geometry_is_rejected(
    source_bounds: list[list[float]],
    target_bounds: list[list[float]],
    target_areas: list[float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        mapper.map_discharge_profile(
            source_bounds,
            [[0, 0, -1]],
            [1],
            target_bounds,
            target_areas,
            source_origin_xyz_m=(0, 0, 0),
            target_origin_xyz_m=(0, 0, -1),
            profile_time_s=0.1,
        )


def test_nonfinite_or_out_of_range_profile_samples_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        mapper.map_discharge_profile(
            [[0, 0, 0, 1, 1, 0]],
            [[0, 0, float("nan")]],
            [1],
            [[0, 0, -1, 1, 1, -1]],
            [1],
            source_origin_xyz_m=(0, 0, 0),
            target_origin_xyz_m=(0, 0, -1),
            profile_time_s=0.1,
        )
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        mapper.map_discharge_profile(
            [[0, 0, 0, 1, 1, 0]],
            [[0, 0, -1]],
            [1.01],
            [[0, 0, -1, 1, 1, -1]],
            [1],
            source_origin_xyz_m=(0, 0, 0),
            target_origin_xyz_m=(0, 0, -1),
            profile_time_s=0.1,
        )


def test_supplied_source_area_detects_nonrectangular_face_geometry() -> None:
    with pytest.raises(ValueError, match="area does not match"):
        mapper.map_discharge_profile(
            [[0, 0, 0, 1, 1, 0]],
            [[0, 0, -1]],
            [1],
            [[0, 0, -1, 1, 1, -1]],
            [1],
            source_origin_xyz_m=(0, 0, 0),
            target_origin_xyz_m=(0, 0, -1),
            profile_time_s=0.1,
            source_face_area_m2=[0.9],
        )


def _native_flux_kwargs() -> dict:
    source_bounds, _, _, target_bounds, target_areas = _mixed_grid_inputs()
    source_areas = (source_bounds[:, 3] - source_bounds[:, 0]) * (
        source_bounds[:, 4] - source_bounds[:, 1]
    )
    return {
        # A faceZone may flip individual mesh-face orientations. The signed
        # rates and normal signs pair to the same positive flow-direction rate.
        "source_face_alpha_phi_m3_s": [1.0, -2.0, 3.0, -4.0],
        "source_face_native_id": [100, 101, 102, 103],
        "source_face_normal_unit_xyz": [
            [0.0, 0.0, -1.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
            [0.0, 0.0, 1.0],
        ],
        "target_face_native_id": [[7, 40], [7, 41]],
        "target_face_normal_unit_xyz": [[0.0, 0.0, 1.0]] * 2,
        "native_alpha_phi_time_s": 0.5,
        "native_alpha_phi_delta_t_s": 0.01,
        "target_face_native_alpha_phi_m3_s": [-4.0, -5.0],
        "target_native_time_s": 0.5,
        "target_native_delta_t_s": 0.02,
        "source_face_area_m2": source_areas,
    }


def test_native_alpha_phi_is_a_distinct_oriented_conservative_channel() -> None:
    source_bounds, velocity, alpha, target_bounds, target_areas = _mixed_grid_inputs()
    result = mapper.map_discharge_profile(
        source_bounds,
        velocity,
        alpha,
        target_bounds,
        target_areas,
        source_origin_xyz_m=(0.0, 0.0, 0.0),
        target_origin_xyz_m=(10.0, -4.0, 5.0),
        profile_time_s=0.5,
        **_native_flux_kwargs(),
    )
    summary = result["summary"]["native_alphaPhi_mapping"]

    assert result["source_face_native_id"].tolist() == [100, 101, 102, 103]
    assert result["target_face_native_id"].tolist() == [[7, 40], [7, 41]]
    assert result["target_face_normal_unit_xyz"].tolist() == [[0.0, 0.0, 1.0]] * 2
    assert result["target_face_mapped_alphaPhi_m3_s"].tolist() == pytest.approx([-4.0, -6.0])
    assert summary["source_rate_along_declared_flow_m3_s"] == pytest.approx(10.0)
    assert summary["source_oriented_rate_sum_m3_s"] == pytest.approx(-2.0)
    assert summary["mapped_target_rate_along_declared_flow_m3_s"] == pytest.approx(10.0)
    assert summary["source_completed_step_volume_along_flow_m3"] == pytest.approx(0.1)
    assert summary["target_native_measurement"]["rate_along_declared_flow_m3_s"] == pytest.approx(
        9.0
    )
    assert (
        summary["target_native_measurement"]["source_and_target_step_volumes_share_same_delta_t"]
        is False
    )
    assert summary["target_native_measurement"][
        "mapped_prediction_minus_measurement_rate_m3_s"
    ] == pytest.approx(1.0)
    # Native alphaPhi data remain separate from and are not inferred from the
    # interpolated-volume-field alpha*U proxy.
    assert summary["source_rate_along_declared_flow_m3_s"] != pytest.approx(
        result["summary"]["source_integrated_proxies"]["water_volume_transport_proxy_m3_s"]
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_face_native_id": None}, "supplied together"),
        ({"source_face_native_id": [1, 1, 2, 3]}, "must be unique"),
        ({"source_face_normal_unit_xyz": [[0.0, 0.0, -2.0]] * 4}, "unit vectors"),
        ({"native_alpha_phi_time_s": 0.4}, "must match profile_time_s"),
        ({"native_alpha_phi_delta_t_s": 0.0}, "finite and positive"),
    ],
)
def test_native_alpha_phi_requires_valid_complete_provenance(overrides: dict, message: str) -> None:
    source_bounds, velocity, alpha, target_bounds, target_areas = _mixed_grid_inputs()
    native = _native_flux_kwargs()
    native.update(overrides)
    with pytest.raises(ValueError, match=message):
        mapper.map_discharge_profile(
            source_bounds,
            velocity,
            alpha,
            target_bounds,
            target_areas,
            source_origin_xyz_m=(0.0, 0.0, 0.0),
            target_origin_xyz_m=(10.0, -4.0, 5.0),
            profile_time_s=0.5,
            **native,
        )


def test_native_alpha_phi_cli_round_trip_is_v2_and_preserves_v1_proxy(tmp_path: Path) -> None:
    arrays_path = tmp_path / "native-faces.npz"
    source_bounds, velocity, alpha, target_bounds, target_areas = _mixed_grid_inputs()
    source_areas = (source_bounds[:, 3] - source_bounds[:, 0]) * (
        source_bounds[:, 4] - source_bounds[:, 1]
    )
    np.savez(
        arrays_path,
        source_face_bounds_xyz_m=source_bounds,
        source_face_area_m2=source_areas,
        source_face_velocity_xyz_m_s=velocity,
        source_face_alpha=alpha,
        target_face_bounds_xyz_m=target_bounds,
        target_face_area_m2=target_areas,
        source_face_alphaPhi_m3_s=np.asarray([1.0, -2.0, 3.0, -4.0]),
        source_face_native_id=np.asarray([100, 101, 102, 103], dtype=np.int64),
        source_face_normal_unit_xyz=np.asarray(
            [[0.0, 0.0, -1.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]
        ),
        target_face_native_id=np.asarray([[7, 40], [7, 41]], dtype=np.int64),
        target_face_normal_unit_xyz=np.asarray([[0.0, 0.0, 1.0]] * 2),
    )
    manifest = tmp_path / "native-input.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": mapper.INPUT_SCHEMA_NATIVE_FLUX,
                "profile_time_s": 0.5,
                "arrays_npz": arrays_path.name,
                "source_origin_xyz_m": [0.0, 0.0, 0.0],
                "target_origin_xyz_m": [10.0, -4.0, 5.0],
                "native_alphaPhi": {
                    "source_time_s": 0.5,
                    "source_delta_t_s": 0.01,
                    "source_rate_convention": mapper.NATIVE_RATE_CONVENTION,
                    "source_sign_convention": mapper.NATIVE_SIGN_CONVENTION,
                    "target_measurement": None,
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "native-mapped"

    report = mapper.run_cli(manifest, output)

    assert report["schema"] == mapper.SCHEMA_NATIVE_FLUX
    assert report["summary"]["native_alphaPhi_mapping"][
        "mapped_target_rate_along_declared_flow_m3_s"
    ] == pytest.approx(10.0)
    assert report["summary"]["source_integrated_proxies"][
        "water_volume_transport_proxy_m3_s"
    ] != pytest.approx(10.0)
    with np.load(output / "mapped_profile_arrays.npz", allow_pickle=False) as archive:
        assert archive["target_face_mapped_alphaPhi_m3_s"].tolist() == pytest.approx([-4.0, -6.0])
        assert archive["target_face_native_id"].tolist() == [[7, 40], [7, 41]]


def test_native_alpha_phi_rejects_time_mismatch_without_creating_output(tmp_path: Path) -> None:
    arrays_path = tmp_path / "native-faces.npz"
    source_bounds, velocity, alpha, target_bounds, target_areas = _mixed_grid_inputs()
    source_areas = (source_bounds[:, 3] - source_bounds[:, 0]) * (
        source_bounds[:, 4] - source_bounds[:, 1]
    )
    np.savez(
        arrays_path,
        source_face_bounds_xyz_m=source_bounds,
        source_face_area_m2=source_areas,
        source_face_velocity_xyz_m_s=velocity,
        source_face_alpha=alpha,
        target_face_bounds_xyz_m=target_bounds,
        target_face_area_m2=target_areas,
        source_face_alphaPhi_m3_s=np.ones(4),
        source_face_native_id=np.arange(4, dtype=np.int64),
        source_face_normal_unit_xyz=np.asarray([[0.0, 0.0, -1.0]] * 4),
        target_face_native_id=np.arange(2, dtype=np.int64),
        target_face_normal_unit_xyz=np.asarray([[0.0, 0.0, 1.0]] * 2),
    )
    manifest = tmp_path / "native-input.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": mapper.INPUT_SCHEMA_NATIVE_FLUX,
                "profile_time_s": 0.5,
                "arrays_npz": arrays_path.name,
                "source_origin_xyz_m": [0.0, 0.0, 0.0],
                "target_origin_xyz_m": [10.0, -4.0, 5.0],
                "native_alphaPhi": {
                    "source_time_s": 0.4,
                    "source_delta_t_s": 0.01,
                    "source_rate_convention": mapper.NATIVE_RATE_CONVENTION,
                    "source_sign_convention": mapper.NATIVE_SIGN_CONVENTION,
                    "target_measurement": None,
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "must-not-be-created"

    with pytest.raises(ValueError, match="native source time must match"):
        mapper.run_cli(manifest, output)
    assert not output.exists()


def test_single_snapshot_cli_records_time_and_refuses_overwrite(tmp_path: Path) -> None:
    arrays_path = tmp_path / "faces.npz"
    source_bounds, velocity, alpha, target_bounds, target_areas = _mixed_grid_inputs()
    np.savez(
        arrays_path,
        source_face_bounds_xyz_m=source_bounds,
        source_face_area_m2=(source_bounds[:, 3] - source_bounds[:, 0])
        * (source_bounds[:, 4] - source_bounds[:, 1]),
        source_face_velocity_xyz_m_s=velocity,
        source_face_alpha=alpha,
        target_face_bounds_xyz_m=target_bounds,
        target_face_area_m2=target_areas,
    )
    manifest = tmp_path / "mapping-input.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": mapper.INPUT_SCHEMA,
                "profile_time_s": 0.0,
                "arrays_npz": "faces.npz",
                "source_origin_xyz_m": [0, 0, 0],
                "target_origin_xyz_m": [10, -4, 5],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "mapped"
    report = mapper.run_cli(manifest, output)
    saved = json.loads((output / "mapping.json").read_text(encoding="utf-8"))
    assert report["profile_time_s"] == saved["profile_time_s"] == 0.0
    assert "no time interpolation" in saved["summary"]["source_profile_time_semantics"]
    with np.load(output / "mapped_profile_arrays.npz", allow_pickle=False) as archive:
        assert archive["target_face_alpha"].shape == (2,)
        assert archive["overlap_area_m2"].shape == (4,)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        mapper.run_cli(manifest, output)
