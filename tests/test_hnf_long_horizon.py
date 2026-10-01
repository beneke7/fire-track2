from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cases/restas_amr_probe"))
import run_hnf_mesh_case as hnf_case  # noqa: E402


def _pulse_case(tmp_path: Path, variant: str, *extra: str) -> tuple[Path, dict, str, dict]:
    args = hnf_case.parse_args(
        [
            "--stage",
            "pulse100ms",
            "--variant",
            variant,
            "--ranks",
            "4",
            "--docker-cpus",
            "4",
            *extra,
        ]
    )
    case = tmp_path / "case"
    inputs = hnf_case.prepare_case.prepare_case(
        case, args.model, args.ranks, 0.05 if variant != "uniform" else args.finest_spacing, 0.08
    )
    hnf_case.configure_pulse100ms_case(case, inputs, args)
    mesh_text, mesh_metadata = hnf_case.pulse100ms_mesh_dict(args)
    (case / "system/blockMeshDict").write_text(mesh_text, encoding="utf-8")
    inputs.update(mesh_metadata)
    return case, inputs, mesh_text, mesh_metadata


@pytest.mark.parametrize("variant", ["dynamic", "static", "uniform"])
def test_long_pulse_keeps_source_fixed_and_applies_mesh_time_inputs(
    tmp_path: Path, variant: str
) -> None:
    case, inputs, mesh_text, mesh_metadata = _pulse_case(
        tmp_path,
        variant,
        "--pulse-horizon-s",
        "0.3",
        "--domain-x-end-m",
        "8",
        "--domain-z-min-m",
        "-1.025",
        "--snapshot-interval-s",
        "0.025",
    )

    assert mesh_metadata["domain_bounds_m"] == {
        "x": [0.0, 8.0],
        "y": [-2.525, 2.525],
        "z": [-1.025, 2.025],
    }
    assert inputs["domain_bounds_m"] == mesh_metadata["domain_bounds_m"]
    assert inputs["time"]["end_s"] == 0.3
    assert inputs["time"]["snapshot_interval_s"] == 0.025
    assert inputs["source_pulse_duration_s"] == 0.08
    assert inputs["source_duration_s"] == 0.08
    assert inputs["analytic_source_mass_over_horizon_kg"] == pytest.approx(960.0)
    assert inputs["source"]["source_mass_expected_kg"] == pytest.approx(960.0)

    control = (case / "system/controlDict").read_text(encoding="utf-8")
    assert "endTime 0.3;" in control
    assert "writeInterval 0.025;" in control
    assert mesh_text.count("type patch;\n        faces") >= 7
    vertex_block = re.search(r"(?ms)^vertices\s*\((.*?)^\);", mesh_text)
    assert vertex_block is not None
    vertices = [
        tuple(map(float, match))
        for match in re.findall(
            r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)",
            vertex_block.group(1),
        )
    ]
    velocity = (case / "0/U").read_text(encoding="utf-8")
    for patch in ("slot_01", "slot_02", "slot_03", "slot_04"):
        patch_faces = re.search(
            rf"(?ms)^    {patch}\s*\{{.*?^        faces\s*\((.*?)^        \);",
            mesh_text,
        )
        assert patch_faces is not None
        face_ids = [
            tuple(map(int, face))
            for face in re.findall(r"\(\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\)", patch_faces.group(1))
        ]
        assert len(face_ids) == 1
        p0, p1, p2, p3 = (vertices[index] for index in face_ids[0])
        assert all(point[0] == pytest.approx(0.0) for point in (p0, p1, p2, p3))
        u = tuple(p1[index] - p0[index] for index in range(3))
        v = tuple(p2[index] - p1[index] for index in range(3))
        normal = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        assert normal[0] == pytest.approx(-0.15)
        assert normal[1:] == pytest.approx((0.0, 0.0))
        assert p3[0] == pytest.approx(0.0)

        patch_field = re.search(rf"(?ms)^    {patch}\s*\{{(.*?)^    \}}", velocity)
        assert patch_field is not None
        assert "uniformValue table" in patch_field.group(1)
        assert "(0 (20 0 0))" in patch_field.group(1)
        assert "(0.08 (20 0 0))" in patch_field.group(1)
        assert "(0.080001 (0 0 0))" in patch_field.group(1)
        assert "(0.3 (0 0 0))" in patch_field.group(1)


def test_pulse_stage_legacy_defaults_are_preserved(tmp_path: Path) -> None:
    case, inputs, _, mesh_metadata = _pulse_case(tmp_path, "dynamic")

    assert mesh_metadata["domain_bounds_m"]["x"] == [0.0, 4.0]
    assert mesh_metadata["domain_bounds_m"]["z"] == [-0.525, 2.025]
    assert inputs["time"]["end_s"] == 0.1
    assert inputs["time"]["snapshot_interval_s"] == 0.01
    assert inputs["source_pulse_duration_s"] == 0.08
    assert inputs["analytic_source_mass_over_horizon_kg"] == pytest.approx(960.0)
    control = (case / "system/controlDict").read_text(encoding="utf-8")
    assert "endTime 0.1;" in control
    assert "writeInterval 0.01;" in control


@pytest.mark.parametrize(
    "extra",
    [
        ("--pulse-horizon-s", "nan"),
        ("--pulse-horizon-s", "0.09"),
        ("--domain-x-end-m", "3.95"),
        ("--domain-z-min-m", "-0.5"),
        ("--snapshot-interval-s", "0"),
        ("--pulse-horizon-s", "0.3", "--snapshot-interval-s", "0.31"),
        ("--domain-x-end-m", "8.01"),
        ("--stage", "stage80ms", "--pulse-horizon-s", "0.3"),
    ],
)
def test_long_horizon_cli_rejects_invalid_or_wrong_stage_overrides(extra: tuple[str, ...]) -> None:
    base = ["--stage", "pulse100ms", "--variant", "dynamic"]
    if extra[:1] == ("--stage",):
        base = ["--variant", "dynamic"]
    with pytest.raises(SystemExit):
        hnf_case.parse_args([*base, *extra])
