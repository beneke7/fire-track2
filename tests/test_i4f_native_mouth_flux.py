from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from aerial_drop.i4f_native_face_reader import MOUTH_WINDOWS
from aerial_drop.i4f_native_mouth_flux import (
    _compare_with_existing_xplane_cut,
    _patch_boundary_topology,
    _polygon_edges,
    _polygon_measure,
    _processor_pair_outward_flux,
    _summarize_components,
    _validate_control_surface,
)


def _synthetic_rectangular_surface() -> tuple[
    list[dict[str, object]], dict[str, set[tuple[int, int]]]
]:
    faces: list[dict[str, object]] = []
    boundary_edges: set[tuple[int, int]] = set()
    face_id = 0
    point_id = 0
    flux_by_mouth = {
        "A_lower": (0.3, -0.1),
        "A_upper": (0.0, 0.2),
        "B_lower": (0.5, 0.25),
        "B_upper": (-0.4, 0.1),
    }
    for mouth, window in MOUTH_WINDOWS.items():
        y0, y1 = window["y_min"], window["y_max"]
        z0, z1 = window["z_min"], window["z_max"]
        vertices = np.asarray(
            [
                [4.8, y0, z0],
                [4.8, y1, z0],
                [4.8, y1, z1],
                [4.8, y0, z1],
            ],
            dtype=np.float64,
        )
        ids = tuple(range(point_id, point_id + 4))
        point_id += 4
        boundary_edges.update(_polygon_edges(np.asarray(ids, dtype=np.int64)))
        triangles = ((0, 1, 2), (0, 2, 3))
        for triangle, q in zip(triangles, flux_by_mouth[mouth], strict=True):
            triangle_xyz = vertices[list(triangle)]
            area_vector, centroid, area, fan_area = _polygon_measure(triangle_xyz)
            triangle_ids = np.asarray([ids[index] for index in triangle], dtype=np.int64)
            faces.append(
                {
                    "global_face_id": face_id,
                    "mouth": mouth,
                    "point_ids": triangle_ids,
                    "vertices_xyz_m": triangle_xyz,
                    "centroid_xyz_m": centroid,
                    "area_m2": area,
                    "first_vertex_fan_area_m2": fan_area,
                    "outward_area_vector_xyz_m2": area_vector,
                    "edges": _polygon_edges(triangle_ids),
                    "water_volume_flux_m3_s": q,
                }
            )
            face_id += 1
    return faces, {"ambientAnnulus": boundary_edges}


def test_nonuniform_native_flux_on_four_oriented_rectangular_mouths() -> None:
    faces, boundary_edges = _synthetic_rectangular_surface()
    validation = _validate_control_surface(
        faces, boundary_edges_by_patch=boundary_edges, wall_face_ids=set()
    )
    assert validation["unique_face_count"] == 8
    assert validation["selected_wall_face_intersections"] == 0
    assert validation["all_perimeter_edges_covered_by_true_physical_patch_boundary"] is True
    assert len(validation["components"][0]["perimeter_edge_segments_xyz_m"]) == 4

    references = {
        "mouths": {
            mouth: {"plane_x_m": 4.8, "projected_area_x_m2": 0.15} for mouth in MOUTH_WINDOWS
        },
        "ambient_annulus_boundary_plane": {"plane_x_m": 4.799},
    }
    summaries = _summarize_components(
        faces,
        boundary_edges_by_patch=boundary_edges,
        physical_geometry_reference=references,
    )
    by_mouth = {summary.mouth: summary for summary in summaries}
    assert set(by_mouth) == set(MOUTH_WINDOWS)
    assert by_mouth["A_lower"].net_water_volume_flux_m3_s == pytest.approx(0.2)
    assert by_mouth["A_lower"].forward_water_volume_flux_m3_s == pytest.approx(0.3)
    assert by_mouth["A_lower"].reverse_water_volume_flux_m3_s == pytest.approx(0.1)
    assert by_mouth["B_lower"].net_water_volume_flux_m3_s == pytest.approx(0.75)
    assert by_mouth["B_upper"].net_water_volume_flux_m3_s == pytest.approx(-0.3)
    for summary in summaries:
        assert summary.fv_control_surface_mag_sf_m2 == pytest.approx(0.15)
        assert summary.nominal_window_plane_area_m2 == pytest.approx(0.15)
        assert summary.projected_sf_x_to_nominal_window_area_ratio == pytest.approx(1.0)
        assert summary.sum_oriented_sf_xyz_m2 == pytest.approx((0.15, 0.0, 0.0))
        assert summary.stl_branch_cap_projected_area_m2 == pytest.approx(0.15)
        assert summary.x_min_m == pytest.approx(4.8)
        assert summary.x_max_m == pytest.approx(4.8)
        assert summary.uncovered_perimeter_edge_count == 0


def test_concave_planar_face_uses_area_normal_not_first_vertex_fan_magnitude() -> None:
    # A 3x3 square with a 1x2 notch removed. The start vertex is chosen so the
    # absolute first-vertex triangle fan overcounts the polygon area.
    yz = np.asarray(
        [
            [3.0, 0.5],
            [2.0, 0.5],
            [2.0, 2.5],
            [3.0, 2.5],
            [3.0, 3.0],
            [0.0, 3.0],
            [0.0, 0.0],
            [3.0, 0.0],
        ]
    )
    polygon = np.column_stack((yz, np.zeros(len(yz))))
    area_normal, centre, mag_sf, first_vertex_fan = _polygon_measure(polygon)

    assert area_normal == pytest.approx([0.0, 0.0, 7.0])
    assert centre == pytest.approx([1.462962962962963, 1.5, 0.0])
    assert centre != pytest.approx([1.2142857142857142, 1.5, 0.0])
    assert mag_sf == pytest.approx(7.0)
    assert first_vertex_fan == pytest.approx(11.0)


def test_warped_face_area_normal_matches_openfoam_central_decomposition() -> None:
    polygon = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 1.0, 1.0],
            [0.0, 1.0, 0.0],
        ]
    )
    average = polygon.mean(axis=0)
    expected = np.zeros(3)
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        expected += 0.5 * np.cross(next_point - point, average - point)
    expected_fan_abs = sum(
        0.5 * np.linalg.norm(np.cross(polygon[index] - polygon[0], polygon[index + 1] - polygon[0]))
        for index in range(1, len(polygon) - 1)
    )

    area_normal, centre, mag_sf, fan_abs = _polygon_measure(polygon)
    assert area_normal == pytest.approx(expected)
    assert centre == pytest.approx([1.0561870939151656, 0.5073955390829363, 0.2677445430202596])
    assert centre != pytest.approx([1.0634920634920635, 0.5079365079365079, 0.2698412698412698])
    assert mag_sf == pytest.approx(np.linalg.norm(expected))
    assert fan_abs == pytest.approx(expected_fan_abs)
    assert mag_sf != pytest.approx(fan_abs)


def test_processor_partition_mirrored_signs_count_one_outward_flux() -> None:
    q_out, error = _processor_pair_outward_flux(
        first_flux_owner_outward=0.075,
        first_face_map_sign=-1,
        first_owner_is_apparatus=True,
        second_flux_owner_outward=-0.075,
        second_face_map_sign=1,
        second_owner_is_apparatus=False,
    )
    assert q_out == pytest.approx(0.075)
    assert error["absolute_error_m3_s"] == pytest.approx(0.0)
    assert error["relative_error"] == pytest.approx(0.0)

    with pytest.raises(ValueError, match="disagree"):
        _processor_pair_outward_flux(
            first_flux_owner_outward=0.075,
            first_face_map_sign=-1,
            first_owner_is_apparatus=True,
            second_flux_owner_outward=-0.07,
            second_face_map_sign=1,
            second_owner_is_apparatus=False,
        )


def test_control_surface_rejects_duplicate_wall_or_unclosed_faces() -> None:
    faces, boundary_edges = _synthetic_rectangular_surface()

    duplicate = faces + [dict(faces[0])]
    with pytest.raises(ValueError, match="duplicate global faces"):
        _validate_control_surface(
            duplicate, boundary_edges_by_patch=boundary_edges, wall_face_ids=set()
        )

    with pytest.raises(ValueError, match="wall faces"):
        _validate_control_surface(faces, boundary_edges_by_patch=boundary_edges, wall_face_ids={0})

    unclosed = _validate_control_surface(faces, boundary_edges_by_patch={}, wall_face_ids=set())
    assert unclosed["all_perimeter_edges_covered_by_true_physical_patch_boundary"] is False
    assert unclosed["components"][0]["perimeter_edges_not_on_any_true_physical_patch_boundary"] == 4


def test_annulus_boundary_loops_exclude_interior_seam_edges() -> None:
    # Four quads form a 10x10 square annulus around a 2x2 hole in y/z.
    yz = [(-5, -5), (5, -5), (5, 5), (-5, 5), (-1, -1), (1, -1), (1, 1), (-1, 1)]
    point_xyz = {
        point_id: np.asarray([0.0, y, z], dtype=np.float64) for point_id, (y, z) in enumerate(yz)
    }
    faces = []
    for index in range(4):
        following = (index + 1) % 4
        faces.append((index, following, 4 + following, 4 + index))

    topology = _patch_boundary_topology(faces, point_xyz)

    assert topology["unique_face_count"] == 4
    assert topology["boundary_edge_count"] == 8
    assert topology["interior_edge_count"] == 4
    assert sorted(loop["signed_projected_area_x_m2"] for loop in topology["loops"]) == [
        -4.0,
        100.0,
    ]
    assert sorted(loop["classification"] for loop in topology["loops"]) == [
        "outer_boundary",
        "outlet_hole",
    ]

    # A selected surface perimeter coincident with an interior annulus seam
    # must not pass the physical-patch boundary coverage check.
    seam = (0, 4)
    validation = _validate_control_surface(
        [
            {
                "global_face_id": 99,
                "edges": (seam,),
                "point_ids": seam,
                "vertices_xyz_m": np.asarray([point_xyz[0], point_xyz[4]]),
            }
        ],
        boundary_edges_by_patch={"ambientAnnulus": set(topology["boundary_edges"])},
        interior_edges_by_patch={"ambientAnnulus": set(topology["interior_edges"])},
        boundary_loops_by_patch={"ambientAnnulus": topology["loops"]},
        wall_face_ids=set(),
    )
    assert validation["all_perimeter_edges_covered_by_true_physical_patch_boundary"] is False
    assert validation["components"][0]["ambient_annulus_interior_patch_edge_count"] == 1
    assert (
        validation["components"][0]["perimeter_edges_not_on_any_true_physical_patch_boundary"] == 1
    )


def test_missing_legacy_global_geometry_skips_only_xplane_comparison(
    tmp_path: Path,
) -> None:
    case = tmp_path / "processor-only-case"
    (case / "processors10/constant/polyMesh").mkdir(parents=True)
    summaries = tuple(
        SimpleNamespace(mouth=mouth, net_water_volume_flux_m3_s=0.25) for mouth in MOUTH_WINDOWS
    )

    comparison = _compare_with_existing_xplane_cut(
        case,
        "0.1",
        10,
        summaries,  # type: ignore[arg-type]
    )

    assert comparison["status"] == "unavailable_missing_legacy_geometry"
    assert comparison["unavailable_required_inputs"] == [
        "constant/polyMesh/points",
        "constant/polyMesh/faces",
        "constant/polyMesh/owner",
        "constant/polyMesh/neighbour",
        "constant/C",
    ]
    assert len(comparison["by_mouth"]) == 4
    assert all(row["xplane_native_water_Q_m3_s"] is None for row in comparison["by_mouth"])
    assert all(
        row["fv_control_surface_water_Q_m3_s"] == pytest.approx(0.25)
        for row in comparison["by_mouth"]
    )
