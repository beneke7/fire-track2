import json

import numpy as np
import pytest

from aerial_drop.i4f_outlet_metrics import outlet_secondary_metrics


def test_uniform_outflow_momentum_and_zero_angle() -> None:
    metrics = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([1.0, 2.0]),
        velocity_face_xyz_m_s=np.asarray([[3.0, 0.0, 0.0], [3.0, 0.0, 0.0]]),
        projected_area_m2=np.asarray([0.5, 1.5]),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        alpha_water_face_raw=np.asarray([1.0, 1.0]),
        water_density_kg_m3=1000.0,
    )

    assert metrics["water_volume_flux_net_m3_s"] == pytest.approx(3.0)
    assert metrics["water_volume_flux_outward_m3_s"] == pytest.approx(3.0)
    assert metrics["water_volume_flux_reverse_magnitude_m3_s"] == pytest.approx(0.0)
    assert metrics["water_momentum_flux_net_reconstructed_N_xyz"] == pytest.approx(
        [9000.0, 0.0, 0.0]
    )
    assert metrics["outward_direction_mean_angle_deg_q_weighted"] == pytest.approx(0.0)
    assert metrics["outward_direction_rms_angle_deg_q_weighted"] == pytest.approx(0.0)
    assert metrics["outward_direction_resultant_unit_xyz"] == pytest.approx([1.0, 0.0, 0.0])
    histogram = metrics["outward_direction_angle_histogram"]
    assert sum(histogram["q_m3_s_by_bin"]) == pytest.approx(3.0)
    assert json.loads(json.dumps(metrics, allow_nan=False))["face_count"] == 2
    assert metrics["water_momentum_flux_outward_resultant_norm_reconstructed_N"] == pytest.approx(
        9000.0
    )
    assert metrics["water_momentum_flux_outward_resultant_unit_xyz"] == pytest.approx(
        [1.0, 0.0, 0.0]
    )
    assert metrics["water_momentum_flux_outward_resultant_angle_deg"] == pytest.approx(0.0)


def test_oblique_direction_angle_and_momentum_are_analytic() -> None:
    metrics = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([2.0]),
        velocity_face_xyz_m_s=np.asarray([[1.0, np.sqrt(3.0), 0.0]]),
        projected_area_m2=np.asarray([4.0]),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        water_density_kg_m3=1000.0,
    )

    assert metrics["water_momentum_flux_outward_reconstructed_N_xyz"] == pytest.approx(
        [2000.0, 2000.0 * np.sqrt(3.0), 0.0]
    )
    assert metrics["outward_direction_mean_angle_deg_q_weighted"] == pytest.approx(60.0)
    assert metrics["outward_direction_rms_angle_deg_q_weighted"] == pytest.approx(60.0)
    assert metrics["outward_direction_resultant_angle_deg"] == pytest.approx(60.0)


def test_momentum_resultant_is_speed_weighted_and_differs_from_direction_statistics() -> None:
    metrics = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([1.0, 1.0]),
        velocity_face_xyz_m_s=np.asarray([[1.0, 0.0, 0.0], [1.0, 10.0, 0.0]]),
        projected_area_m2=np.ones(2),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        water_density_kg_m3=1.0,
    )

    assert metrics["outward_direction_mean_angle_deg_q_weighted"] == pytest.approx(
        0.5 * np.degrees(np.arctan(10.0))
    )
    assert metrics["outward_direction_resultant_angle_deg"] == pytest.approx(
        0.5 * np.degrees(np.arctan(10.0))
    )
    assert metrics["water_momentum_flux_outward_reconstructed_N_xyz"] == pytest.approx(
        [2.0, 10.0, 0.0]
    )
    assert metrics["water_momentum_flux_outward_resultant_norm_reconstructed_N"] == pytest.approx(
        np.sqrt(104.0)
    )
    assert metrics["water_momentum_flux_outward_resultant_angle_deg"] == pytest.approx(
        np.degrees(np.arctan2(10.0, 2.0))
    )
    assert metrics["water_momentum_flux_outward_resultant_angle_deg"] != pytest.approx(
        metrics["outward_direction_mean_angle_deg_q_weighted"]
    )


def test_reverse_flux_is_separate_and_cancelling_net_q_is_preserved() -> None:
    metrics = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([2.0, -2.0]),
        velocity_face_xyz_m_s=np.asarray([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]),
        projected_area_m2=np.ones(2),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        water_density_kg_m3=1000.0,
    )

    assert metrics["water_volume_flux_net_m3_s"] == pytest.approx(0.0)
    assert metrics["water_volume_flux_outward_m3_s"] == pytest.approx(2.0)
    assert metrics["water_volume_flux_reverse_magnitude_m3_s"] == pytest.approx(2.0)
    assert metrics["water_momentum_flux_outward_reconstructed_N_xyz"] == pytest.approx(
        [2000.0, 0.0, 0.0]
    )
    assert metrics["water_momentum_flux_reverse_signed_reconstructed_N_xyz"] == pytest.approx(
        [2000.0, 0.0, 0.0]
    )
    assert metrics["outward_direction_defined_water_flux_m3_s"] == pytest.approx(2.0)
    assert metrics["outward_direction_undefined_water_flux_m3_s"] == pytest.approx(0.0)

    all_reverse = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([-1.0]),
        velocity_face_xyz_m_s=np.asarray([[-1.0, 0.0, 0.0]]),
        projected_area_m2=np.ones(1),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
    )
    assert all_reverse["outward_direction_mean_angle_deg_q_weighted"] is None
    assert all_reverse["outward_direction_resultant_unit_xyz"] is None


def test_directional_cancellation_and_undefined_zero_speed_flux_are_explicit() -> None:
    cancel = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([1.0, 1.0]),
        velocity_face_xyz_m_s=np.asarray([[1.0, 1.0, 0.0], [1.0, -1.0, 0.0]]),
        projected_area_m2=np.ones(2),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
    )
    assert cancel["outward_direction_mean_angle_deg_q_weighted"] == pytest.approx(45.0)
    assert cancel["outward_direction_resultant_angle_deg"] == pytest.approx(0.0)
    assert cancel["outward_direction_resultant_strength_fraction"] == pytest.approx(
        1.0 / np.sqrt(2.0)
    )

    momentum_cancel = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([1.0, 1.0]),
        velocity_face_xyz_m_s=np.asarray([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]),
        projected_area_m2=np.ones(2),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
    )
    assert momentum_cancel[
        "water_momentum_flux_outward_resultant_norm_reconstructed_N"
    ] == pytest.approx(0.0)
    assert momentum_cancel["water_momentum_flux_outward_resultant_unit_xyz"] is None
    assert momentum_cancel["water_momentum_flux_outward_resultant_angle_deg"] is None
    assert momentum_cancel["water_momentum_flux_outward_resultant_direction_defined"] is False

    zero_speed = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([0.75]),
        velocity_face_xyz_m_s=np.zeros((1, 3)),
        projected_area_m2=np.asarray([1.0]),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
    )
    assert zero_speed["outward_direction_mean_angle_deg_q_weighted"] is None
    assert zero_speed["outward_direction_rms_angle_deg_q_weighted"] is None
    assert zero_speed["outward_direction_resultant_unit_xyz"] is None
    assert zero_speed["outward_direction_defined_water_flux_m3_s"] == pytest.approx(0.0)
    assert zero_speed["outward_direction_undefined_water_flux_m3_s"] == pytest.approx(0.75)
    json.dumps(zero_speed, allow_nan=False)
    histogram = zero_speed["outward_direction_angle_histogram"]
    assert sum(histogram["q_m3_s_by_bin"]) + histogram[
        "undefined_direction_q_m3_s"
    ] == pytest.approx(zero_speed["water_volume_flux_outward_m3_s"])


def test_raw_alpha_area_weighting_keeps_excursions_and_thresholds_are_descriptive() -> None:
    metrics = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([0.0, 0.0]),
        velocity_face_xyz_m_s=np.zeros((2, 3)),
        projected_area_m2=np.asarray([1.0, 3.0]),
        outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        alpha_water_face_raw=np.asarray([-0.1, 1.2]),
    )

    assert metrics["raw_alpha_water_min"] == pytest.approx(-0.1)
    assert metrics["raw_alpha_water_max"] == pytest.approx(1.2)
    assert metrics["raw_alpha_water_below_zero_face_count"] == 1
    assert metrics["raw_alpha_water_above_one_face_count"] == 1
    assert metrics["area_weighted_raw_alpha_water_fraction"] == pytest.approx(0.875)
    assert metrics["area_weighted_raw_alpha_gas_fraction_proxy"] == pytest.approx(0.125)
    thresholds = metrics["liquid_area_fraction_thresholds"]
    assert thresholds["display_alpha_ge_0p01_area_fraction"] == pytest.approx(0.75)
    assert thresholds["diagnostic_alpha_ge_0p50_area_fraction"] == pytest.approx(0.75)
    assert thresholds["diagnostic_alpha_ge_0p99_area_fraction"] == pytest.approx(0.75)
    assert metrics["outward_direction_mean_angle_deg_q_weighted"] is None


def test_rotated_frame_invariance_and_q_velocity_sign_disagreement() -> None:
    q = np.asarray([1.0, -0.5])
    velocity = np.asarray([[-1.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
    normal = np.asarray([1.0, 0.0, 0.0])
    base = outlet_secondary_metrics(
        water_volume_flux_m3_s=q,
        velocity_face_xyz_m_s=velocity,
        projected_area_m2=np.ones(2),
        outlet_normal_unit_xyz=normal,
    )

    rotation = np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    rotated = outlet_secondary_metrics(
        water_volume_flux_m3_s=q,
        velocity_face_xyz_m_s=velocity @ rotation.T,
        projected_area_m2=np.ones(2),
        outlet_normal_unit_xyz=rotation @ normal,
    )
    assert rotated["outward_direction_mean_angle_deg_q_weighted"] == pytest.approx(
        base["outward_direction_mean_angle_deg_q_weighted"]
    )
    np.testing.assert_allclose(
        rotated["water_momentum_flux_net_reconstructed_N_xyz"],
        rotation @ base["water_momentum_flux_net_reconstructed_N_xyz"],
    )
    assert rotated["outward_direction_angle_histogram"] == base["outward_direction_angle_histogram"]
    signs = base["q_velocity_normal_sign_diagnostics"]
    assert signs["outward_q_with_inward_U_face_count"] == 1
    assert signs["outward_q_with_inward_U_face_flux_magnitude_m3_s"] == pytest.approx(1.0)
    assert signs["reverse_q_with_outward_U_face_count"] == 1
    assert signs["reverse_q_with_outward_U_face_flux_magnitude_m3_s"] == pytest.approx(0.5)


def test_empty_and_invalid_inputs() -> None:
    empty = outlet_secondary_metrics(
        water_volume_flux_m3_s=np.asarray([]),
        velocity_face_xyz_m_s=np.empty((0, 3)),
        projected_area_m2=np.asarray([]),
        outlet_normal_unit_xyz=np.asarray([0.0, 0.0, 1.0]),
        alpha_water_face_raw=np.asarray([]),
    )
    assert empty["water_volume_flux_net_m3_s"] == pytest.approx(0.0)
    assert empty["projected_area_m2"] is None
    assert empty["area_weighted_raw_alpha_gas_fraction_proxy"] is None
    assert empty["outward_direction_mean_angle_deg_q_weighted"] is None
    assert empty["outward_direction_resultant_unit_xyz"] is None
    json.dumps(empty, allow_nan=False)

    with pytest.raises(ValueError, match="unit length"):
        outlet_secondary_metrics(
            water_volume_flux_m3_s=np.asarray([1.0]),
            velocity_face_xyz_m_s=np.zeros((1, 3)),
            projected_area_m2=np.ones(1),
            outlet_normal_unit_xyz=np.asarray([2.0, 0.0, 0.0]),
        )
    with pytest.raises(ValueError, match="finite and positive"):
        outlet_secondary_metrics(
            water_volume_flux_m3_s=np.asarray([1.0]),
            velocity_face_xyz_m_s=np.zeros((1, 3)),
            projected_area_m2=np.asarray([-1.0]),
            outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        )
    with pytest.raises(ValueError, match="water volume flux must be finite"):
        outlet_secondary_metrics(
            water_volume_flux_m3_s=np.asarray([np.nan]),
            velocity_face_xyz_m_s=np.zeros((1, 3)),
            projected_area_m2=np.ones(1),
            outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
        )
    with pytest.raises(ValueError, match="raw face liquid fractions must be finite"):
        outlet_secondary_metrics(
            water_volume_flux_m3_s=np.asarray([0.0]),
            velocity_face_xyz_m_s=np.zeros((1, 3)),
            projected_area_m2=np.ones(1),
            outlet_normal_unit_xyz=np.asarray([1.0, 0.0, 0.0]),
            alpha_water_face_raw=np.asarray([np.inf]),
        )
