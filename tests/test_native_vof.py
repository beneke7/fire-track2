import numpy as np
import pytest

from scripts.analyze_native_vof import analyze_snapshot, assemble_rank_payloads


def _rank_payload(
    rank,
    rank_count,
    ids,
    alpha,
    volumes,
    internal_edges=(),
    processor_edges=(),
    source_owners=(),
    *,
    source_centres=(),
    source_area_vectors=(),
    cell_centres=None,
    cell_bounds=None,
):
    ids = np.asarray(ids, dtype=np.int64)
    source_owners = np.asarray(source_owners, dtype=np.int64)
    internal_edges = np.asarray(internal_edges, dtype=np.int64).reshape((-1, 2))
    processor_edges = np.asarray(processor_edges, dtype=np.int64).reshape((-1, 2))
    source_centres = np.asarray(source_centres, dtype=np.float64).reshape((-1, 3))
    source_area_vectors = np.asarray(source_area_vectors, dtype=np.float64).reshape((-1, 3))
    return {
        "metadata": {
            "rank": rank,
            "rank_count": rank_count,
            "time_name": "1",
            "time_value_s": 1.0,
            "source_patch": "dash8Opening",
            "local_cell_count": len(ids),
            "internal_face_count": len(internal_edges),
            "processor_edge_occurrences": len(processor_edges),
            "source_face_count_local": len(source_owners),
        },
        "cell_global_ids": ids,
        "cell_volumes_m3": np.asarray(volumes, dtype=np.float64),
        "alpha_water": np.asarray(alpha, dtype=np.float64),
        "velocity_xyz_m_s": np.zeros((len(ids), 3), dtype=np.float64),
        "cell_centres_xyz_m": (
            np.zeros((len(ids), 3), dtype=np.float64)
            if cell_centres is None
            else np.asarray(cell_centres, dtype=np.float64)
        ),
        "cell_bounds_minmax_xyz_m": (
            np.zeros((len(ids), 6), dtype=np.float64)
            if cell_bounds is None
            else np.asarray(cell_bounds, dtype=np.float64)
        ),
        "internal_edges_global": internal_edges,
        "processor_edges_global": processor_edges,
        "source_owner_global": source_owners,
        "source_face_local_ids": np.arange(len(source_owners), dtype=np.int64),
        "source_face_centres_xyz_m": source_centres,
        "source_face_area_vectors_xyz_m2": source_area_vectors,
    }


def test_processor_boundary_join_and_rank_with_zero_source_faces():
    # The same processor face is exported once by each rank. Rank 1 has no
    # source faces; explicit global IDs still join the two native cells.
    payloads = [
        _rank_payload(
            0,
            2,
            [0],
            [1.0],
            [0.01],
            processor_edges=[[0, 1]],
            source_owners=[0],
            source_centres=[[0, 0, 0]],
            source_area_vectors=[[0, 0, -0.01]],
        ),
        _rank_payload(1, 2, [1], [1.0], [0.02], processor_edges=[[1, 0]]),
    ]
    snapshot = assemble_rank_payloads(payloads)
    report = analyze_snapshot(snapshot)
    dense = report["thresholds"]["0.9"]["min_cells_1"]

    assert snapshot["topology"]["rank_count"] == 2
    assert snapshot["topology"]["processor_face_edge_occurrences_both_sides"] == 2
    assert snapshot["topology"]["unique_face_edges"] == 1
    assert snapshot["topology"]["source_boundary_face_count"] == 1
    assert snapshot["topology"]["source_patch_area_m2"] == pytest.approx(0.01)
    assert dense["component_count"] == 1
    assert dense["attached_component_count"] == 1
    assert dense["detached_component_count"] == 0
    assert dense["attached_component_mass_kg"] == pytest.approx(30.0)


def test_disconnected_native_pattern_attachment_mass_and_min_two_filter():
    # Face edges produce {0}, {2,3}, {4}; the subthreshold cell 1 cannot bridge.
    payload = _rank_payload(
        0,
        1,
        [0, 1, 2, 3, 4],
        [1.0, 0.5, 0.95, 0.9, 0.99],
        [0.01, 0.02, 0.03, 0.04, 0.05],
        internal_edges=[[0, 1], [2, 3]],
        source_owners=[0],
        source_centres=[[0, 0, 0]],
        source_area_vectors=[[0, 0, -0.01]],
    )
    report = analyze_snapshot(assemble_rank_payloads([payload]))
    threshold = report["thresholds"]["0.9"]
    all_components = threshold["min_cells_1"]
    minimum_two = threshold["min_cells_2"]

    assert all_components["component_count"] == 3
    assert all_components["attached_component_count"] == 1
    assert all_components["attached_component_mass_kg"] == pytest.approx(10.0)
    assert all_components["detached_component_mass_kg"] == pytest.approx(114.0)
    assert minimum_two["component_count"] == 1
    assert minimum_two["attached_component_count"] == 0
    assert minimum_two["reported_component_mass_kg"] == pytest.approx(64.5)
    # The reporting filter never removes mass from the independent full field.
    assert report["total_domain_water_mass_kg"] == pytest.approx(134.0)


def test_rank_payload_requires_dense_global_cell_addressing():
    payload = _rank_payload(0, 1, [1, 3], [1, 1], [1, 1])
    with pytest.raises(ValueError, match=r"dense \[0, N\)"):
        assemble_rank_payloads([payload])


def test_rank_metadata_must_cover_each_processor_once():
    payload = _rank_payload(1, 2, [0], [1], [1])
    with pytest.raises(ValueError, match="each rank exactly once"):
        assemble_rank_payloads([payload])


def test_processor_interface_requires_reciprocal_edge_on_both_ranks():
    payloads = [
        _rank_payload(0, 2, [0], [1], [0.01], processor_edges=[[0, 1]]),
        _rank_payload(1, 2, [1], [1], [0.01]),
    ]
    with pytest.raises(ValueError, match="not reciprocal"):
        assemble_rank_payloads(payloads)


def test_raw_alpha_roundoff_is_reported_and_not_clipped_from_mass():
    payload = _rank_payload(0, 1, [0], [1.0 + 5e-13], [1.0])
    snapshot = assemble_rank_payloads([payload])
    report = analyze_snapshot(snapshot)

    assert snapshot["alpha_water"][0] == 1.0 + 5e-13
    assert report["total_domain_water_mass_kg"] == pytest.approx(1000.0 * (1.0 + 5e-13))
    assert report["alpha_integrity"]["raw_values_clipped"] is False
    assert report["alpha_integrity"]["values_outside_unit_interval_within_roundoff_tolerance"] == 1


def test_native_component_bounds_and_centroid_outside_refinement_mass():
    payload = _rank_payload(
        0,
        1,
        [0, 1],
        [1.0, 1.0],
        [0.01, 0.02],
        source_owners=[0],
        source_centres=[[0, 0, -0.5]],
        source_area_vectors=[[0, 0, -0.01]],
        cell_centres=[[0, 0, 0], [2.5, 0.5, 0.5]],
        cell_bounds=[[-0.5, -0.5, -0.5, 0.5, 0.5, 0.5], [2, 0, 0, 3, 1, 1]],
    )
    report = analyze_snapshot(
        assemble_rank_payloads([payload]),
        refinement_box_m={"x": (-1, 1), "y": (-1, 1), "z": (-1, 1)},
    )
    cloud = report["thresholds"]["0.001"]["min_cells_1"]

    assert cloud["cells_outside_refinement_band"] == 1
    assert cloud["selected_water_mass_outside_refinement_band_kg"] == pytest.approx(20.0)
    assert cloud["components_extending_outside_refinement_band"] == 1
    assert cloud["component_native_bounds"] == [
        {"label": 0, "bounds_m": {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}},
        {"label": 1, "bounds_m": {"min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0]}},
    ]


def test_additive_geometric_volume_velocity_observers_preserve_primary_statistics():
    payload = _rank_payload(
        0,
        1,
        [0, 1],
        [0.25, 0.5625],
        [0.02, 0.08],
        internal_edges=[[0, 1]],
    )
    payload["velocity_xyz_m_s"] = np.asarray([[1.0, 0.0, -2.0], [5.0, 4.0, 2.0]])
    snapshot = assemble_rank_payloads([payload])
    report = analyze_snapshot(snapshot, thresholds=(0.1,))
    component = report["thresholds"]["0.1"]["min_cells_1"]["detached_components"][0]

    # The established alpha-volume mass, equivalent diameter, and mass-weighted
    # velocity remain intact. The new observer deliberately uses full V.
    assert component["cell_count"] == 2
    assert component["liquid_volume_m3"] == pytest.approx(0.05)
    assert component["mass_kg"] == pytest.approx(50.0)
    assert component["equivalent_diameter_m"] == pytest.approx(np.cbrt(6.0 * 0.05 / np.pi))
    assert component["mass_weighted_velocity_m_s"] == pytest.approx((4.6, 3.6, 1.6))

    assert component["selected_cell_geometric_volume_m3"] == pytest.approx(0.1)
    assert component["selected_cell_geometric_volume_equivalent_diameter_m"] == pytest.approx(
        np.cbrt(6.0 * 0.1 / np.pi)
    )
    assert component["selected_cell_geometric_volume_equivalent_diameter_m"] / component[
        "equivalent_diameter_m"
    ] == pytest.approx(2.0 ** (1.0 / 3.0))
    assert component["geometric_volume_weighted_velocity_m_s"] == pytest.approx((4.2, 3.2, 1.2))
    assert component["cell_number_mean_velocity_m_s"] == pytest.approx((3.0, 2.0, 0.0))
