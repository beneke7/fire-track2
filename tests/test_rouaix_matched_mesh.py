from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cases/e1_rouaix_matched_mesh"))

import build_case  # noqa: E402
import build_wall_layer_fixture  # noqa: E402
import mesh_audit  # noqa: E402


def test_domain_is_a_single_flat_roof_trapezoid_with_source_bounds() -> None:
    text = build_case.block_mesh_dict()
    assert "hex (0 1 2 3 4 5 6 7) (179 89 90)" in text
    assert "(-2.5 -10 -8)" in text and "(17.5 0 3.5)" in text
    assert "aircraftWall { type wall; faces ((3 7 6 2)); }" in text
    assert build_case.COUNTS[0] * build_case.COUNTS[1] * build_case.COUNTS[2] == 1_433_790


def test_inferred_roi_uses_lower_envelope_and_upward_buffer() -> None:
    lower = build_case.lower_envelope()
    guide = build_case.fine_guide(lower)
    assert lower[0] == guide[0] == (0.0, 0.0)
    assert lower[-1] == (6.5, -6.0)
    assert guide[-1] == (6.5, -5.2)
    assert all(0 <= y - edge <= 0.8 for (_, edge), (_, y) in zip(lower, guide))


def test_pilot_and_final_mesh_levels_encode_dyadic_targets_without_snappy_layers() -> None:
    pilot = build_case.snappy_dict("pilot")
    final = build_case.snappy_dict("final")
    assert "maxGlobalCells 6000000;" in pilot
    assert "levels ((1e15 2))" in pilot
    assert "levels ((1e15 3))" in final
    assert "levels ((1e15 4))" not in final
    assert "nozzleArea { mode inside; levels ((1e15 3)); }" in final
    assert "addLayers false" in final
    assert "addLayersControls" not in final
    assert "minDeterminant 0.001; minFaceWeight 0.05" in final
    assert "point2 (0 -0.16 0)" in final
    assert "writeFlags (scalarLevels)" in final
    assert "addLayers false" in final
    assert len(build_case.LAYER_EDGE_FRACTIONS) == 4


def test_runner_splits_five_wall_layers_without_snappy_shrinking() -> None:
    runner = (ROOT / "cases/e1_rouaix_matched_mesh/run_mesh.sh").read_text()
    for fraction in build_case.LAYER_EDGE_FRACTIONS:
        assert f"{fraction:.16g}" in runner
    assert "refineWallLayer '(aircraftWall)'" in runner
    assert "refineWallLayer -inSet wallOwnerCells '(aircraftWall)'" in runner
    assert "topoSet -dict system/wallOwnerSetDict -constant" in runner
    assert "shapeToCell; shape hex;" in build_case.wall_owner_set_dict()
    assert "source cellToFace" in build_case.wall_owner_set_dict()
    assert "set wallOwnerCells; option all;" in build_case.wall_owner_set_dict()
    assert "HEX_WALL_COVERAGE" in runner
    assert "layer-selection/pass-$index-hexWallFaces" in runner
    assert "aperture-fixture" in runner
    assert "WALL_SPLIT_CELL_COUNT" in runner
    assert "points.beforeWallSplit" in runner
    assert "snappyHexMesh -dict system/layersOnlyDict" not in runner


def test_aperture_fixture_has_owner_only_set_and_multiple_cells_across_surface(
    tmp_path: Path,
) -> None:
    fixture = build_wall_layer_fixture.block_mesh_dict()
    assert "(8 2 8)" in fixture
    assert "(-4 -2 -4)" in fixture and "(4 0 4)" in fixture
    assert build_wall_layer_fixture.NOZZLE_RADIUS == 1.6
    case = tmp_path / "fixture"
    build_wall_layer_fixture.write_case(case)
    assert "radius 1.6" in (case / "system/topoSetDict").read_text()
    owner_set = (case / "system/wallOwnerSetDict").read_text()
    assert "source faceToCell;" in owner_set
    assert "set wallFaces; option owner;" in owner_set
    assert "action subset; source shapeToCell; shape hex;" in owner_set
    assert "name hexWallFaces" in owner_set
    assert "action subset; source patchToFace; patch aircraftWall;" in owner_set


def test_final_case_is_binary_mesh_only_and_never_overwrites(tmp_path: Path) -> None:
    case = tmp_path / "case"
    build_case.write_case(case, "final")
    control = (case / "system/controlDict").read_text()
    assert "writeFormat binary" in control
    assert "writePrecision 16" in control
    assert (case / "case.foam").is_file()
    assert not (case / "0").exists()
    metadata = json.loads((case / "mesh-input.json").read_text())
    assert metadata["levels"]["nozzle_audit"] == 3
    assert metadata["wall_layers"] == {
        "paper_reported_count": 5,
        "paper_reported_growth": 1.1,
        "reproduced_count": 0,
        "status": "not_reproduced",
        "note": "The generated and selected Mac mesh is cast-only. Experimental layer trials are archived separately and rejected; no layer method is part of this case's default pipeline.",
    }
    assert not (case / "system/wallOwnerSetDict").exists()


def test_experimental_wall_sets_are_opt_in(tmp_path: Path) -> None:
    case = tmp_path / "experimental"
    build_case.write_case(case, "final", experimental_wall_sets=True)
    assert (case / "system/wallOwnerSetDict").is_file()


def test_owner_wall_split_requires_explicit_experimental_case_input() -> None:
    runner = (ROOT / "cases/e1_rouaix_matched_mesh/run_mesh.sh").read_text()
    assert "EXPERIMENTAL_WALL_SET_DICT_MISSING; rebuild with --experimental-wall-sets" in runner


def test_mesh_runner_uses_current_foundation_reconstruction_and_serial_patch_steps() -> None:
    runner = (ROOT / "cases/e1_rouaix_matched_mesh/run_mesh.sh").read_text()
    assert "reconstructParMesh" not in runner
    assert "reconstructPar -constant -noFields -noSets" in runner
    assert "run nozzle-set topoSet -constant" in runner
    assert "run nozzle-patch createPatch -overwrite" in runner
    assert "GLOBAL_CELL_COUNT_MISMATCH" in runner
    assert 'assert_global_cells "$cast_cells" before-prelayer-check' in runner
    assert 'wall_split "$cast_cells"' in runner


def test_ascii_patch_audit_reports_polygon_area_and_outward_normal(tmp_path: Path) -> None:
    mesh = tmp_path / "constant/polyMesh"
    mesh.mkdir(parents=True)
    (mesh / "points").write_text("4\n(\n(0 0 0)\n(0 0 1)\n(1 0 1)\n(1 0 0)\n)\n")
    (mesh / "faces").write_text("1\n(\n4(0 1 2 3)\n)\n")
    (mesh / "boundary").write_text(
        "1\n(\nnozzle\n{\n type patch;\n nFaces 1;\n startFace 0;\n}\n)\n"
    )
    measured = mesh_audit.patch_area_normal(mesh, "nozzle")
    assert measured["area_m2"] == 1
    assert measured["normal"] == [0, 1, 0]
    assert measured["area_vector_m2"] == [0, 1, 0]
    assert measured["area_vector_magnitude_m2"] == pytest.approx(1)
    assert measured["faces"] == 1


def test_ascii_patch_audit_rejects_empty_and_zero_area_patches(tmp_path: Path) -> None:
    empty = tmp_path / "empty/constant/polyMesh"
    empty.mkdir(parents=True)
    (empty / "points").write_text("0\n(\n)\n")
    (empty / "faces").write_text("0\n(\n)\n")
    (empty / "boundary").write_text(
        "1\n(\nnozzle\n{\n type patch;\n nFaces 0;\n startFace 0;\n}\n)\n"
    )
    with pytest.raises(ValueError, match="patch has no faces"):
        mesh_audit.patch_area_normal(empty, "nozzle")

    degenerate = tmp_path / "degenerate/constant/polyMesh"
    degenerate.mkdir(parents=True)
    (degenerate / "points").write_text("4\n(\n(0 0 0)\n(1 0 0)\n(2 0 0)\n(3 0 0)\n)\n")
    (degenerate / "faces").write_text("1\n(\n4(0 1 2 3)\n)\n")
    (degenerate / "boundary").write_text(
        "1\n(\nnozzle\n{\n type patch;\n nFaces 1;\n startFace 0;\n}\n)\n"
    )
    with pytest.raises(ValueError, match="zero-area face"):
        mesh_audit.patch_area_normal(degenerate, "nozzle")


def test_binary_patch_audit_reads_compact_face_lists_and_returns_area_vector(
    tmp_path: Path,
) -> None:
    mesh = tmp_path / "constant/polyMesh"
    mesh.mkdir(parents=True)
    header = (
        "FoamFile\n{\n    format binary;\n    class vectorField;\n}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n\n"
    ).encode("ascii")
    points = [(0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)]
    (mesh / "points").write_bytes(
        header
        + b"4\n("
        + struct.pack("<12d", *(value for point in points for value in point))
        + b")\n"
    )
    face_header = header.replace(b"vectorField", b"faceCompactList")
    (mesh / "faces").write_bytes(
        face_header
        + b"2\n("
        + struct.pack("<2i", 0, 4)
        + b")\n4\n("
        + struct.pack("<4i", 0, 1, 2, 3)
        + b")\n"
    )
    (mesh / "boundary").write_text(
        "1\n(\nnozzle\n{\n type patch;\n nFaces 1;\n startFace 0;\n}\n)\n"
    )
    measured = mesh_audit.binary_patch_area_normal(mesh, "nozzle")
    assert measured["faces"] == 1
    assert measured["area_m2"] == pytest.approx(1)
    assert measured["area_vector_m2"] == pytest.approx([0, 1, 0])
    assert measured["normal"] == pytest.approx([0, 1, 0])
    assert measured["binary_abi"] == {"endian": "little", "label_bits": 32, "scalar_bits": 64}


def test_ascii_face_reader_handles_multiline_polygons(tmp_path: Path) -> None:
    mesh = tmp_path / "constant/polyMesh"
    mesh.mkdir(parents=True)
    (mesh / "points").write_text("5\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n(1 2 0)\n(0 2 0)\n)\n")
    (mesh / "faces").write_text("2\n(\n3\n(0 1\n2)\n3 (1 3 4)\n)\n")
    (mesh / "boundary").write_text(
        "1\n(\naircraftWall\n{\n type wall;\n nFaces 2;\n startFace 0;\n}\n)\n"
    )
    assert list(mesh_audit.iter_ascii_faces(mesh / "faces")) == [[0, 1, 2], [1, 3, 4]]
    measured = mesh_audit.patch_area_normal(mesh, "aircraftWall")
    assert measured["faces"] == 2
    assert measured["area_m2"] == pytest.approx(1.5)


def test_refinement_counts_uses_last_mesh_histogram() -> None:
    log = """Cells per refinement level:
    0 100
    1 20
Cells per refinement level:
    0 70
    1 40
    2 10
"""
    assert mesh_audit.refinement_counts(log) == {0: 70, 1: 40, 2: 10}


def test_checkmesh_parser_keeps_native_flags_separate_from_exit_status() -> None:
    summary = mesh_audit.check_mesh_summary(
        """    cells: 2858817
 ***Error in face tets: 160 faces with low quality or negative volume decomposition tets.
 ***Concave cells (using face planes) found, number of cells: 31282
    Cell determinant (wellposedness) : minimum: 0.0765578 average: 9.1395
    Face interpolation weight : minimum: 0.0579498 average: 0.4944
    Face volume ratio : minimum: 0.0101558 average: 0.9720
 Failed 2 mesh checks.
"""
    )
    assert summary == {
        "cells": 2_858_817,
        "mesh_ok_banner": False,
        "failed_checkmesh_categories": 2,
        "low_quality_tet_faces": 160,
        "concave_or_planar_cells": 31_282,
        "minimum_cell_determinant": pytest.approx(0.0765578),
        "minimum_face_interpolation_weight": pytest.approx(0.0579498),
        "minimum_face_volume_ratio": pytest.approx(0.0101558),
    }


def test_vtk_problem_set_bounds_read_ascii_points_only(tmp_path: Path) -> None:
    path = tmp_path / "badCells.vtk"
    path.write_text(
        "# vtk DataFile Version 2.0\nsample\nASCII\nDATASET POLYDATA\n"
        "POINTS 4 float\n0 1 2 3 4 5 6 7 8 9 10 11\n"
        "POLYGONS 1 5\n4 0 1 2 3\n"
    )
    result = mesh_audit.vtk_point_bounds(path)
    assert result["points"] == 4
    assert result["bounds_m"] == {"x": [0.0, 9.0], "y": [1.0, 10.0], "z": [2.0, 11.0]}


def test_original_point_audit_requires_unchanged_prefix(tmp_path: Path) -> None:
    before = tmp_path / "points-before"
    after = tmp_path / "points-after"
    before.write_text("3\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n)\n")
    after.write_text("4\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n(0 0 1)\n)\n")
    result = mesh_audit.point_prefix_preservation(before, after)
    assert result == {"original_points": 3, "final_points": 4, "unchanged_prefix": True}
    after.write_text("4\n(\n(0 0 0)\n(1 0 0)\n(0 1.01 0)\n(0 0 1)\n)\n")
    with pytest.raises(ValueError, match="original point coordinates changed"):
        mesh_audit.point_prefix_preservation(before, after)


def test_nozzle_owner_spacing_uses_cell_volume_over_boundary_area(tmp_path: Path) -> None:
    mesh = tmp_path / "constant/polyMesh"
    mesh.mkdir(parents=True)
    (mesh / "points").write_text(
        "8\n(\n(0 0 0)\n(1 0 0)\n(1 0 1)\n(0 0 1)\n(0 1 0)\n(1 1 0)\n(1 1 1)\n(0 1 1)\n)\n"
    )
    (mesh / "faces").write_text(
        "6\n(\n4(0 1 2 3)\n4(4 7 6 5)\n4(0 3 7 4)\n4(1 5 6 2)\n4(0 4 5 1)\n4(3 2 6 7)\n)\n"
    )
    (mesh / "owner").write_text("6\n(\n0\n0\n0\n0\n0\n0\n)\n")
    (mesh / "neighbour").write_text("0\n(\n)\n")
    names = ["bottom", "nozzle", "left", "right", "front", "back"]
    (mesh / "boundary").write_text(
        "6\n(\n"
        + "".join(
            f"{name}\n{{\n type patch;\n nFaces 1;\n startFace {index};\n}}\n"
            for index, name in enumerate(names)
        )
        + ")\n"
    )
    measured = mesh_audit.nozzle_owner_spacing(mesh)
    assert measured["patch_faces"] == 1
    assert measured["unique_owner_cells"] == 1
    assert measured["patch_area_m2"] == pytest.approx(1.0)
    assert measured["normal"] == pytest.approx([0.0, 1.0, 0.0])
    assert measured["owner_cell_volume_m3"]["median"] == pytest.approx(1.0)
    assert measured["volume_over_nozzle_area_m"]["median"] == pytest.approx(1.0)


def test_layer_coverage_is_area_weighted_and_requires_stable_patch_order(tmp_path: Path) -> None:
    base = tmp_path / "base"
    final = tmp_path / "final"
    selections = tmp_path / "selections"
    for mesh in (base, final):
        mesh.mkdir()
        (mesh / "points").write_text("5\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n(1 2 0)\n(0 2 0)\n)\n")
        (mesh / "faces").write_text("2\n(\n3(0 1 2)\n3(1 3 4)\n)\n")
        (mesh / "boundary").write_text(
            "1\n(\naircraftWall\n{\n type wall;\n nFaces 2;\n startFace 0;\n}\n)\n"
        )
    selections.mkdir()
    pass_labels = ([0], [0], [0], [1])
    for index, labels in enumerate(pass_labels, start=1):
        (selections / f"pass-{index}-hexWallFaces").write_text(
            f"{len(labels)}\n(\n" + "".join(f"{label}\n" for label in labels) + ")\n"
        )
        (selections / f"pass-{index}-startFace").write_text("0\n")

    measured = mesh_audit.wall_layer_coverage(base, final, selections)
    assert measured["total_wall_area_m2"] == pytest.approx(1.5)
    assert measured["area_fraction_by_achieved_bands"] == {
        "1": 0.0,
        "2": pytest.approx(2 / 3),
        "3": 0.0,
        "4": pytest.approx(1 / 3),
        "5": 0.0,
    }
    (final / "faces").write_text("2\n(\n3(1 3 4)\n3(0 1 2)\n)\n")
    with pytest.raises(ValueError, match="patch face count/order/geometry changed"):
        mesh_audit.wall_layer_coverage(base, final, selections)
