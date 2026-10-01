import numpy as np
import pytest

from aerial_drop.structure_counts import label_liquid_structures, structure_statistics


def test_face_edges_leave_diagonal_corner_contact_disconnected():
    # Four cells in a 2x2 grid. Cells 0 and 3 meet only at one corner.
    alpha = np.array([1.0, 0.0, 0.0, 1.0])
    face_owner = np.array([0, 0, 1, 2])
    face_neighbour = np.array([1, 2, 3, 3])

    face_labels = label_liquid_structures(alpha, face_owner, face_neighbour, 0.9)
    point_labels = label_liquid_structures(
        alpha,
        np.append(face_owner, 0),
        np.append(face_neighbour, 3),
        0.9,
    )

    np.testing.assert_array_equal(face_labels, [0, -1, -1, 1])
    np.testing.assert_array_equal(point_labels, [0, -1, -1, 0])


def test_subthreshold_bridge_does_not_join_liquid_structures():
    alpha = np.array([0.95, 0.3, 0.95])
    owner = np.array([0, 1])
    neighbour = np.array([1, 2])

    connected_at_low_threshold = label_liquid_structures(alpha, owner, neighbour, 0.2)
    split_at_high_threshold = label_liquid_structures(alpha, owner, neighbour, 0.9)

    np.testing.assert_array_equal(connected_at_low_threshold, [0, 0, 0])
    np.testing.assert_array_equal(split_at_high_threshold, [0, -1, 1])


def test_minimum_cell_filter_only_excludes_reported_structure():
    alpha = np.array([1.0, 0.95, 0.8])
    original_alpha = alpha.copy()
    volumes = np.array([1.0, 1.0, 1.0])
    owner = np.array([0])
    neighbour = np.array([1])

    labels = label_liquid_structures(alpha, owner, neighbour, 0.9, min_cells=2)
    rows = structure_statistics(alpha, volumes, labels)

    np.testing.assert_array_equal(labels, [0, 0, -1])
    np.testing.assert_array_equal(alpha, original_alpha)
    assert sum(row["mass_kg"] for row in rows) == pytest.approx(1950.0)
    # The independent full-field water ledger still includes every alpha cell.
    assert np.sum(alpha * volumes * 1000.0) == pytest.approx(2750.0)


def test_equivalent_diameter_and_liquid_mass_weighted_velocity():
    alpha = np.array([0.5, 1.0])
    volumes = np.array([2.0, 1.0])
    velocity = np.array([[2.0, 0.0, 0.0], [8.0, 4.0, -4.0]])

    rows = structure_statistics(alpha, volumes, np.array([0, 0]), velocity)

    assert rows == [
        {
            "label": 0,
            "cell_count": 2,
            "liquid_volume_m3": pytest.approx(2.0),
            "mass_kg": pytest.approx(2000.0),
            "equivalent_diameter_m": pytest.approx((12.0 / np.pi) ** (1.0 / 3.0)),
            "mass_weighted_velocity_m_s": pytest.approx((5.0, 2.0, -2.0)),
        }
    ]


def test_per_cell_density_is_used_for_velocity_mass_weighting():
    rows = structure_statistics(
        np.array([1.0, 0.5]),
        np.array([1.0, 2.0]),
        np.array([0, 0]),
        np.array([[0.0, 0.0, 0.0], [6.0, 3.0, 0.0]]),
        density_kg_m3=np.array([1000.0, 2000.0]),
    )

    assert rows[0]["mass_kg"] == pytest.approx(3000.0)
    assert rows[0]["mass_weighted_velocity_m_s"] == pytest.approx((4.0, 2.0, 0.0))


def test_component_ids_are_ordered_by_smallest_native_cell_id():
    alpha = np.ones(6)
    # The two edges arrive in descending root order; labels still follow the
    # minimum native-cell IDs, including each isolated selected cell.
    labels = label_liquid_structures(
        alpha,
        np.array([5, 4]),
        np.array([1, 3]),
        0.001,
    )

    np.testing.assert_array_equal(labels, [0, 1, 2, 3, 3, 1])


def test_no_selected_cells_and_invalid_inputs():
    assert np.all(label_liquid_structures(np.zeros(2), np.array([0]), np.array([1]), 0.9) == -1)

    with pytest.raises(ValueError, match="threshold"):
        label_liquid_structures(np.ones(2), np.array([0]), np.array([1]), 0.0)
    with pytest.raises(ValueError, match="positive integer"):
        label_liquid_structures(np.ones(2), np.array([0]), np.array([1]), 0.9, min_cells=0)
    with pytest.raises(ValueError, match="valid native-cell"):
        label_liquid_structures(np.ones(2), np.array([-1]), np.array([1]), 0.9)
    with pytest.raises(ValueError, match="matching 1-D shapes"):
        structure_statistics(np.ones(2), np.ones(3), np.zeros(2, dtype=int))
