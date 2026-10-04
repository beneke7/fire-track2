from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "cases/calbrix_dash8/prepare_case.py"

spec = importlib.util.spec_from_file_location("test_dash8_prepare_case", GENERATOR_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load Dash-8 generator at {GENERATOR_PATH}")
dash8 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dash8
spec.loader.exec_module(dash8)


@pytest.fixture
def prepared_case(tmp_path: Path) -> tuple[Path, dict]:
    case = tmp_path / "dash8-short-history"
    metadata = dash8.prepare_case(case, horizon_s=0.5, ranks=4)
    return case, metadata


def test_one_opening_area_history_mass_and_boundary_sign(prepared_case: tuple[Path, dict]) -> None:
    case, metadata = prepared_case

    assert metadata["aircraft"] == "Dash-8"
    assert metadata["source_patches"] == ["dash8Opening"]
    assert metadata["source_patch_areas_m2"] == pytest.approx({"dash8Opening": 4.44 * 0.30})
    assert metadata["source_geometry_assumption"]["evidence_class"].startswith(
        "provisional figure-derived"
    )
    assert "not a reported aperture" in metadata["source_geometry_assumption"]["evidence_class"]

    primary = dash8.read_primary_history()
    path_integral = dash8.integrate_history(primary, 0.5)
    expected_mass = 4.44 * 0.30 * 1000.0 * path_integral
    assert metadata["analytic_expected_mass_kg"] == pytest.approx(expected_mass)
    assert metadata["analytic_expected_mass_by_source_kg"] == pytest.approx(
        {"dash8Opening": expected_mass}
    )
    samples = metadata["source_histories"]["dash8"]["samples_used_m_s"]
    assert samples[0] == [0.0, 0.0]
    assert samples[-1] == [0.5, pytest.approx(4.677)]

    velocity = (case / "0/U").read_text(encoding="utf-8")
    assert re.search(r"airInlet\s*\{\s*type fixedValue;\s*value uniform \(50 0 0\);", velocity)
    assert re.search(r"plate\s*\{\s*type slip;", velocity)
    opening = velocity.split("dash8Opening", maxsplit=1)[1].split("plate", maxsplit=1)[0]
    assert "uniformValue table" in opening
    assert "(0.5 (0 0 -4.677))" in opening


def test_default_mesh_is_a_single_aligned_patch_in_the_reported_size_domain(
    prepared_case: tuple[Path, dict],
) -> None:
    case, metadata = prepared_case
    assert metadata["domain_bounds_m"] == {
        "x": [-3.0, 23.0],
        "y": [-10.0, 10.0],
        "z": [-31.0, 0.0],
    }
    assert metadata["mesh_cells_expected"] == (
        metadata["mesh_shape"]["x"] * metadata["mesh_shape"]["y"] * metadata["mesh_shape"]["z"]
    )
    assert 500_000 <= metadata["mesh_cells_expected"] <= 1_000_000
    assert metadata["source_patch_macro_face_counts"] == {"dash8Opening": 1}
    block_mesh = (case / "system/blockMeshDict").read_text(encoding="utf-8")
    for patch in (
        "dash8Opening",
        "plate",
        "airInlet",
        "xOutlet",
        "yMin",
        "yMax",
        "zMin",
    ):
        assert re.search(rf"\b{patch}\s*\{{", block_mesh)
    assert "type wall;" in block_mesh.split("plate", maxsplit=1)[1].split("airInlet", maxsplit=1)[0]


def test_five_second_endpoint_is_retained_and_independent_read_is_copied(tmp_path: Path) -> None:
    case = tmp_path / "dash8-five-seconds"
    metadata = dash8.prepare_case(case, horizon_s=5.0, ranks=4)

    history = metadata["source_histories"]["dash8"]
    assert history["samples_used_m_s"][-1] == [5.0, pytest.approx(0.074)]
    assert metadata["analytic_expected_mass_kg"] == pytest.approx(15_921.396, abs=1e-3)
    assert history["source_endpoint_policy"].startswith("no forced shutoff")
    independent_name = Path(history["independent_read"]["source_artifact"]).name
    assert (
        case / "source" / independent_name
    ).read_bytes() == dash8.INDEPENDENT_HISTORY_CSV.read_bytes()
    assert metadata["input_hashes"]["cl415_helper_module_sha256"]
    assert json.loads((case / "case-inputs.json").read_text(encoding="utf-8")) == metadata
    control_dict = (case / "system/controlDict").read_text(encoding="utf-8")
    assert "endTime 5;" in control_dict
    assert "writeInterval 0.1;" in control_dict


def test_horizon_above_digitized_support_is_rejected_before_output_creation(tmp_path: Path) -> None:
    case = tmp_path / "invalid-six-second-case"
    with pytest.raises(ValueError, match="exceeds primary and independent CSV support"):
        dash8.prepare_case(case, horizon_s=6.0)
    assert not case.exists()


@pytest.mark.parametrize(
    ("samples", "message"),
    [
        ([(0.0, 0.0), (1.0, -0.1)], "nonnegative"),
        ([(0.0, 0.0), (0.5, 1.0), (0.4, 1.1)], "strictly increasing"),
        ([(0.1, 0.0), (1.0, 0.0)], "t=0 sample"),
    ],
)
def test_bad_histories_are_rejected(samples: list[tuple[float, float]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dash8.validate_history(samples)


def test_custom_source_geometry_is_area_checked_and_bad_refinement_fails_early(
    tmp_path: Path,
) -> None:
    case = tmp_path / "dash8-custom-source"
    metadata = dash8.prepare_case(
        case,
        horizon_s=0.1,
        ranks=2,
        source_length_m=2.0,
        source_width_m=0.2,
        domain_bounds_m={"x": (-3.0, 3.0), "y": (-2.0, 2.0), "z": (-4.0, 0.0)},
        refinement_region={"x": (-1.5, 1.5), "y": (-1.0, 1.0), "z": (-2.0, 0.0)},
    )
    assert metadata["source_patch_areas_m2"] == pytest.approx({"dash8Opening": 0.4})
    assert "'x': [-3.0, 3.0]" in metadata["domain_placement_assumption"]
    assert "single 2 m by 0.2 m rectangle" in metadata["scope_limitations"][0]

    invalid_case = tmp_path / "dash8-invalid-refinement"
    with pytest.raises(ValueError, match="must cover outlet dash8Opening"):
        dash8.prepare_case(
            invalid_case,
            horizon_s=0.1,
            refinement_region={
                "x": (-1.0, 1.0),
                "y": (-1.0, 1.0),
                "z": (-2.0, 0.0),
            },
        )
    assert not invalid_case.exists()
