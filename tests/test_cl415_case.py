from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREPARE_CASE_PATH = ROOT / "cases/calbrix_cl415/prepare_case.py"
PREPARE_CASE_SPEC = importlib.util.spec_from_file_location("cl415_prepare_case", PREPARE_CASE_PATH)
assert PREPARE_CASE_SPEC is not None and PREPARE_CASE_SPEC.loader is not None
prepare_case = importlib.util.module_from_spec(PREPARE_CASE_SPEC)
sys.modules[PREPARE_CASE_SPEC.name] = prepare_case
PREPARE_CASE_SPEC.loader.exec_module(prepare_case)


def source_block(field_text: str, patch: str) -> str:
    marker = f"    {patch}\n    {{\n"
    start = field_text.index(marker) + len(marker)
    end = field_text.index("\n    }", start)
    return field_text[start:end]


def mesh_vertices(mesh_text: str) -> list[tuple[float, float, float]]:
    body = mesh_text.split("vertices\n(\n", 1)[1].split("\n);", 1)[0]
    return [
        tuple(float(value) for value in row.split()) for row in re.findall(r"\(([^()]*)\)", body)
    ]


def patch_faces(mesh_text: str, patch: str) -> list[tuple[int, int, int, int]]:
    match = re.search(
        rf"(?ms)^\s*{re.escape(patch)}\s*\{{.*?^\s*faces\s*\((.*?)^\s*\);",
        mesh_text,
    )
    assert match is not None, f"patch {patch} is missing from blockMeshDict"
    return [
        tuple(int(value) for value in row.split())
        for row in re.findall(r"\((\d+\s+\d+\s+\d+\s+\d+)\)", match.group(1))
    ]


def face_normal(
    vertices: list[tuple[float, float, float]], face: tuple[int, ...]
) -> tuple[float, float, float]:
    p0 = vertices[face[0]]
    p1 = vertices[face[1]]
    p2 = vertices[face[2]]
    a = tuple(p1[index] - p0[index] for index in range(3))
    b = tuple(p2[index] - p0[index] for index in range(3))
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def quad_area(vertices: list[tuple[float, float, float]], face: tuple[int, ...]) -> float:
    p0, p1, p2, p3 = (vertices[index] for index in face)
    first = face_normal(vertices, face)
    # The blockMesh faces are planar axis-aligned quads, so this gives both triangles' area.
    return math.sqrt(sum(component**2 for component in first))


def test_default_case_records_geometry_histories_and_all_flux_patches(tmp_path: Path) -> None:
    case = tmp_path / "cl415"
    inputs = prepare_case.prepare_case(case)

    assert inputs["case_id"] == "E3_CALBRIX_CL415_EXPLORATORY_NEARFIELD"
    assert inputs["solver"] == "interIsoFoam"
    assert inputs["horizon_s"] == pytest.approx(0.1)
    assert inputs["ranks"] == 20
    assert inputs["domain_bounds_m"] == {
        "x": [-2.0, 6.0],
        "y": [-3.0, 3.0],
        "z": [-4.0, 0.0],
    }
    assert inputs["mesh_shape"] == {"x": 80, "y": 60, "z": 40}
    assert inputs["mesh_cells_expected"] == 192_000
    assert inputs["source_patches"] == ["source_01", "source_02", "source_03", "source_04"]
    assert inputs["open_patches"] == ["airInlet", "xOutlet", "yMin", "yMax", "zMin"]
    assert set(inputs["mesh_breaks_m"]) == {"x", "y", "z"}
    assert set(inputs["mesh_widths_by_segment_m"]) == {"x", "y", "z"}
    assert inputs["source_geometry"]["source_plane_z_m"] == 0.0
    for source in inputs["source_geometry"]["sources"]:
        assert source["area_m2"] == pytest.approx(0.24)
        assert source["direction_unit"] == [0.0, 0.0, -1.0]
        assert inputs["source_patch_areas_m2"][source["name"]] == pytest.approx(0.24)

    assert inputs["source_histories"]["analytic_expected_mass_kg"] == pytest.approx(86.472)
    assert inputs["source_histories"]["not_a_payload"].find("6000 L") >= 0
    assert inputs["source_histories"]["initial_water_volume_anchor_m3"] == 0.0
    assert inputs["source_histories"]["top"]["samples_used_m_s"] == [
        [0.0, 0.0],
        [0.05, 0.784],
        [0.1, 1.627],
    ]

    assert json.loads((case / "case-inputs.json").read_text(encoding="utf-8")) == inputs
    assert "source_01Flux" in (case / "system/controlDict").read_text(encoding="utf-8")
    for patch in inputs["source_patches"] + inputs["open_patches"]:
        assert f"{patch}Flux" in (case / "system/controlDict").read_text(encoding="utf-8")
    assert "plateFlux" not in (case / "system/controlDict").read_text(encoding="utf-8")
    assert (
        case / inputs["source_histories"]["source_artifacts_relative_paths"]["fig4_primary_csv"]
    ).is_file()


def test_initial_air_and_time_varying_velocity_and_turbulence_tables(tmp_path: Path) -> None:
    case = tmp_path / "cl415"
    prepare_case.prepare_case(case, horizon_s=0.1)

    alpha = (case / "0/alpha.water").read_text(encoding="utf-8")
    velocity = (case / "0/U").read_text(encoding="utf-8")
    k = (case / "0/k").read_text(encoding="utf-8")
    epsilon = (case / "0/epsilon").read_text(encoding="utf-8")
    assert "internalField uniform 0;" in alpha
    assert "internalField uniform (50 0 0);" in velocity
    assert "type fixedValue;\n        value uniform 1;" in source_block(alpha, "source_01")
    assert "type uniformFixedValue;" in source_block(velocity, "source_01")
    assert "(0 (0 0 0))" in source_block(velocity, "source_01")
    assert "(0.05 (0 0 -0.784))" in source_block(velocity, "source_01")
    assert "(0.1 (0 0 -1.627))" in source_block(velocity, "source_01")
    assert "type uniformFixedValue;" in source_block(k, "source_01")
    assert "(0 1e-12)" in source_block(k, "source_01")
    assert "(0.05 0.00230496)" in source_block(k, "source_01")
    assert "type uniformFixedValue;" in source_block(epsilon, "source_01")
    assert "(0 1e-12)" in source_block(epsilon, "source_01")
    assert "type zeroGradient;" in source_block(k, "plate")
    assert "type zeroGradient;" in source_block(epsilon, "plate")
    assert "type calculated;" in source_block((case / "0/nut").read_text(encoding="utf-8"), "plate")
    assert "RASModel kEpsilon;" in (case / "constant/turbulenceProperties").read_text(
        encoding="utf-8"
    )
    transport = (case / "constant/transportProperties").read_text(encoding="utf-8")
    assert "rho 1000;" in transport
    assert "rho 1.2;" in transport
    assert "sigma 0;" in transport


def test_source_rectangles_are_disjoint_and_mesh_faces_recover_area() -> None:
    geometry = prepare_case._validate_geometry(
        prepare_case._default_geometry(), prepare_case.PILOT_DOMAIN
    )
    mesh_text, mesh = prepare_case.block_mesh_dict(
        domain=prepare_case.PILOT_DOMAIN,
        sources=geometry["sources"],
        spacing_m=0.1,
        coarse_spacing_m=0.1,
    )

    assert set(mesh["source_patch_macro_face_counts"]) == {
        "source_01",
        "source_02",
        "source_03",
        "source_04",
    }
    assert all(count == 1 for count in mesh["source_patch_macro_face_counts"].values())
    assert all(area == pytest.approx(0.24) for area in mesh["source_patch_areas_m2"].values())
    assert sum(mesh["source_patch_areas_m2"].values()) == pytest.approx(0.96)

    vertices = mesh_vertices(mesh_text)
    for patch in mesh["source_patch_macro_face_counts"]:
        faces = patch_faces(mesh_text, patch)
        assert sum(quad_area(vertices, face) for face in faces) == pytest.approx(0.24)
        assert all(face_normal(vertices, face)[2] > 0 for face in faces)
    outward_components = {
        "airInlet": (0, -1),
        "xOutlet": (0, 1),
        "yMin": (1, -1),
        "yMax": (1, 1),
        "zMin": (2, -1),
    }
    for patch, (axis, sign) in outward_components.items():
        faces = patch_faces(mesh_text, patch)
        assert faces
        assert all(sign * face_normal(vertices, face)[axis] > 0 for face in faces)


def test_nonuniform_mesh_caps_actual_widths_and_preserves_source_areas(tmp_path: Path) -> None:
    case = tmp_path / "cl415"
    inputs = prepare_case.prepare_case(
        case, spacing_m=0.05, coarse_spacing_m=0.1, horizon_s=0.01, ranks=20
    )

    assert inputs["mesh_cells_expected"] > 192_000
    for axis in ("x", "y", "z"):
        assert max(inputs["mesh_widths_by_segment_m"][axis]) <= 0.1 + 1e-12
        assert min(inputs["mesh_widths_by_segment_m"][axis]) <= 0.05 + 1e-12
    assert all(area == pytest.approx(0.24) for area in inputs["source_patch_areas_m2"].values())
    assert inputs["source_histories"]["top"]["samples_used_m_s"][-1][0] == pytest.approx(0.01)


def test_custom_source_geometry_is_configurable_and_horizon_cannot_exceed_curve(
    tmp_path: Path,
) -> None:
    base = prepare_case._default_geometry()
    base["sources"][0]["width_y_m"] = 0.4
    source_path = tmp_path / "geometry.json"
    source_path.write_text(json.dumps(base), encoding="utf-8")
    case = tmp_path / "custom-case"

    inputs = prepare_case.prepare_case(case, source_geometry=source_path)

    assert inputs["source_geometry"]["sources"][0]["area_m2"] == pytest.approx(0.32)
    assert inputs["source_patch_areas_m2"]["source_01"] == pytest.approx(0.32)
    assert (case / "source_geometry.json").read_text(encoding="utf-8") == source_path.read_text(
        encoding="utf-8"
    )

    rejected_output = tmp_path / "too-long"
    with pytest.raises(ValueError, match="exceeds the shorter digitized history support"):
        prepare_case.prepare_case(rejected_output, horizon_s=1.81)
    assert not rejected_output.exists()


def test_output_must_be_new_and_full_domain_is_placed_downstream(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="preserving it"):
        prepare_case.prepare_case(existing)

    case = tmp_path / "full"
    metadata = prepare_case.prepare_case(case, full_domain=True, ranks=20)
    assert metadata["domain_bounds_m"] == {
        "x": [-2.0, 20.0],
        "y": [-7.0, 7.0],
        "z": [-21.0, 0.0],
    }
    assert metadata["domain_placement_assumption"].find("2 m upstream x offset") >= 0


def test_full_domain_custom_refinement_has_expected_widths_and_cell_count(
    tmp_path: Path,
) -> None:
    region = {"x": (-1.0, 4.0), "y": (-1.5, 1.5), "z": (-4.0, 0.0)}
    case = tmp_path / "full-refined"
    metadata = prepare_case.prepare_case(
        case,
        horizon_s=0.5,
        spacing_m=0.05,
        coarse_spacing_m=0.2,
        full_domain=True,
        refinement_region=region,
    )

    assert metadata["horizon_s"] == pytest.approx(0.5)
    assert metadata["mesh_shape"] == {"x": 185, "y": 116, "z": 165}
    assert metadata["mesh_cells_expected"] == 3_540_900
    assert metadata["refinement_region_m"] == {
        axis: list(bounds) for axis, bounds in region.items()
    }
    assert metadata["refinement_covers_all_source_faces"] is True
    for axis in ("x", "y", "z"):
        bounds = metadata["mesh_breaks_m"][axis]
        widths = metadata["mesh_widths_by_segment_m"][axis]
        assert len(widths) == len(bounds) - 1
        for lower, upper, actual_width in zip(bounds[:-1], bounds[1:], widths, strict=True):
            middle = (lower + upper) / 2
            region_lower, region_upper = region[axis]
            requested_width = 0.05 if region_lower <= middle <= region_upper else 0.2
            assert actual_width <= requested_width + 1e-12


def test_invalid_or_source_excluding_refinement_fails_before_output_creation(
    tmp_path: Path,
) -> None:
    outside_domain = {"x": (-2.0, 6.1), "y": (-1.5, 1.5), "z": (-4.0, 0.0)}
    outside_output = tmp_path / "outside-domain"
    with pytest.raises(ValueError, match="inside the selected domain"):
        prepare_case.prepare_case(outside_output, refinement_region=outside_domain)
    assert not outside_output.exists()

    reversed_bounds = {"x": (4.0, -1.0), "y": (-1.5, 1.5), "z": (-4.0, 0.0)}
    malformed_output = tmp_path / "reversed-bounds"
    with pytest.raises(ValueError, match="lower bound must be less than upper bound"):
        prepare_case.prepare_case(malformed_output, refinement_region=reversed_bounds)
    assert not malformed_output.exists()

    missing_source = {"x": (-0.5, 4.0), "y": (-1.5, 1.5), "z": (-4.0, 0.0)}
    source_output = tmp_path / "source-excluded"
    with pytest.raises(ValueError, match="must cover outlet source_01"):
        prepare_case.prepare_case(source_output, refinement_region=missing_source)
    assert not source_output.exists()


def test_refinement_region_json_cli_argument(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    region_path = tmp_path / "refinement.json"
    region_path.write_text(
        json.dumps({"x": [-1.0, 2.0], "y": [-1.5, 1.5], "z": [-2.0, 0.0]}),
        encoding="utf-8",
    )
    case = tmp_path / "cli-case"
    result = prepare_case.main(
        ["--output", str(case), "--refinement-region-json", str(region_path)]
    )

    assert result == 0
    assert capsys.readouterr().out
    metadata = json.loads((case / "case-inputs.json").read_text(encoding="utf-8"))
    assert metadata["refinement_region_m"] == {
        "x": [-1.0, 2.0],
        "y": [-1.5, 1.5],
        "z": [-2.0, 0.0],
    }
