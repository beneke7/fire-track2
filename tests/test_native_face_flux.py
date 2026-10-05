from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/configure_native_face_flux.py"
SPEC = importlib.util.spec_from_file_location("configure_native_face_flux", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load face-flux configurator at {SCRIPT}")
configurator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = configurator
SPEC.loader.exec_module(configurator)


def _source_case(root: Path) -> Path:
    case = root / "candidate"
    (case / "system").mkdir(parents=True)
    (case / "system/controlDict").write_text(
        """FoamFile
{
    version 2.0;
    object controlDict;
}
application interIsoFoam;
functions
{
    apertureFlux
    {
        type surfaceFieldValue;
        regionType faceZone;
        name outletPlane;
        operation sum;
        fields (phi alphaPhi_);
        writeFields false;
        writeControl timeStep;
        writeInterval 1;
    }
}
""",
        encoding="utf-8",
    )
    (case / "case-inputs.json").write_text(
        json.dumps(
            {
                "solver": "interIsoFoam",
                "openfoam_image_id": "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b",
                "physics": {"surface_tension_n_m": 0.0},
                "diagnostics": {"native_flux": "per-step aggregate"},
            }
        ),
        encoding="utf-8",
    )
    (case / "0").mkdir()
    (case / "0/alpha.water").write_text("unchanged field input\n", encoding="utf-8")
    return case


def test_configuration_adds_native_stream_without_changing_solver_inputs(tmp_path: Path) -> None:
    source = _source_case(tmp_path)
    source_hashes = configurator.tree_hashes(source)
    output = tmp_path / "instrumented/case"

    record = configurator.configure_case(source, output)

    assert record["status"] == "configured"
    assert record["changed_case_files"] == ["case-inputs.json", "system/controlDict"]
    assert record["added_case_files"] == []
    assert configurator.tree_hashes(source) == source_hashes
    assert (output / "0/alpha.water").read_bytes() == (source / "0/alpha.water").read_bytes()
    control = (output / "system/controlDict").read_text(encoding="utf-8")
    assert "nativeAlphaPhiOutlet" in control
    assert "writeControl timeStep;" in control
    assert "writeInterval 1;" in control
    assert 'lookupObject<surfaceScalarField>("alphaPhi_")' in control
    assert "faceRate = -faceRate" in control
    assert "<< runTime.deltaTValue()" in control
    assert "area_vector_x_m2" in control
    assert "min_x_m,min_y_m,min_z_m,max_x_m,max_y_m,max_z_m" in control
    assert "mesh.faces()[meshFacei]" in control
    metadata = json.loads((output / "case-inputs.json").read_text(encoding="utf-8"))
    assert metadata["physics"] == {"surface_tension_n_m": 0.0}
    assert metadata["diagnostics"]["native_face_alphaPhi"]["rate_convention"] == (
        "isoAdvection dVf_ divided by main Time::deltaT; row time is completed end-of-step time"
    )


def test_optional_target_patch_gets_outward_surface_flux_capture(tmp_path: Path) -> None:
    source = _source_case(tmp_path)
    output = tmp_path / "with-target"

    record = configurator.configure_case(source, output, target_patch="dash8Opening")

    control = (output / "system/controlDict").read_text(encoding="utf-8")
    assert record["target_patch"] == "dash8Opening"
    assert "nativeAlphaPhiTargetPatch" in control
    assert 'findPatchID("dash8Opening")' in control
    assert "flipSigns.append(0);" in control
    metadata = json.loads((output / "case-inputs.json").read_text(encoding="utf-8"))
    assert metadata["diagnostics"]["native_face_alphaPhi"]["optional_target_selection"] == {
        "type": "patch",
        "name": "dash8Opening",
    }


def test_duplicate_processor_side_is_filtered_like_surface_field_value(tmp_path: Path) -> None:
    source = _source_case(tmp_path)
    output = tmp_path / "instrumented"
    configurator.configure_case(source, output)
    control = (output / "system/controlDict").read_text(encoding="utf-8")

    assert "isA<coupledPolyPatch>(patch)" in control
    assert "refCast<const coupledPolyPatch>(patch).owner()" in control
    assert "!coupled->owner()" not in control
    assert "zone.flipMap()[zoneFacei]" in control
    assert "mesh.Sf()[meshFacei]" in control


def test_configuration_refuses_existing_output_and_nonidentifiers(tmp_path: Path) -> None:
    source = _source_case(tmp_path)
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        configurator.configure_case(source, existing)
    with pytest.raises(ValueError, match="OpenFOAM identifier"):
        configurator.configure_case(source, tmp_path / "bad-name", face_zone="bad name")


@pytest.mark.parametrize(
    ("control_text", "message"),
    [
        ("application interIsoFoam;", "exactly one functions dictionary"),
        (
            "functions { nativeAlphaPhiOutlet { type coded; } apertureFlux { type surfaceFieldValue; } }",
            "already contains a native alphaPhi sidecar",
        ),
        (
            "functions { other { type coded; } }",
            "lacks the per-step aggregate apertureFlux comparator",
        ),
    ],
)
def test_configuration_rejects_ambiguous_control_dict(
    tmp_path: Path, control_text: str, message: str
) -> None:
    source = _source_case(tmp_path)
    (source / "system/controlDict").write_text(control_text, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        configurator.configure_case(source, tmp_path / "instrumented")


def test_brace_matching_ignores_c_comments_and_quoted_braces() -> None:
    text = 'functions { a { code #{ if (x) { y(); } #}; } // } ignored\n b { s "}"; } }'
    opening = text.index("{")
    closing = configurator._matching_brace(text, opening)

    assert text[closing] == "}"
    assert not text[closing + 1 :].strip()
