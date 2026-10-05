from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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


def _legacy_backflow_velocity_bytes(path: Path) -> bytes:
    """Remove only the declared freestream-tangential BC addition for history comparisons."""
    content = path.read_bytes()
    correction = b"        tangentialVelocity uniform (50 0 0);\n"
    if content.count(correction) != 4:
        raise AssertionError("expected the four declared 50 m/s backflow BC additions")
    return content.replace(correction, b"")


def _generated_input_tree_sha256(case: Path, *, account_for_backflow_fix: bool = False) -> str:
    files = sorted(
        path
        for directory in ("0", "constant", "system")
        for path in (case / directory).rglob("*")
        if path.is_file()
    )
    records_list = []
    for path in files:
        relative = path.relative_to(case).as_posix()
        content = (
            _legacy_backflow_velocity_bytes(path)
            if account_for_backflow_fix and relative == "0/U"
            else path.read_bytes()
        )
        records_list.append(f"{relative} {hashlib.sha256(content).hexdigest()}\n")
    records = "".join(records_list)
    return hashlib.sha256(records.encode("utf-8")).hexdigest()


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
    assert metadata["air_speed_m_s"] == pytest.approx(50.0)
    assert metadata["boundary_conditions"]["open_boundary_backflow_tangential_velocity_m_s"] == [
        50.0,
        0.0,
        0.0,
    ]

    velocity = (case / "0/U").read_text(encoding="utf-8")
    assert re.search(r"airInlet\s*\{\s*type fixedValue;\s*value uniform \(50 0 0\);", velocity)
    for patch in ["xOutlet", "yMin", "yMax", "zMin"]:
        assert (
            "tangentialVelocity uniform (50 0 0);"
            in (velocity.split(patch, maxsplit=1)[1].split("}", maxsplit=1)[0])
        )
    assert re.search(r"plate\s*\{\s*type slip;", velocity)
    opening = velocity.split("dash8Opening", maxsplit=1)[1].split("plate", maxsplit=1)[0]
    assert "uniformValue table" in opening
    assert "(0.5 (0 0 -4.677))" in opening


def test_uniform_and_perturbed_velocity_only_add_the_declared_backflow_correction(
    tmp_path: Path,
) -> None:
    case = tmp_path / "dash8-legacy-uniform-velocity"
    dash8.prepare_case(case, horizon_s=0.5, ranks=2)

    assert hashlib.sha256(_legacy_backflow_velocity_bytes(case / "0/U")).hexdigest() == (
        "6b508db58a0511fc72af1aa5ec720ac23e2978d06ce223c5ca397de33fb2567e"
    )

    perturbed_case = tmp_path / "dash8-legacy-perturbed-velocity"
    dash8.prepare_case(perturbed_case, horizon_s=0.5, ranks=2, source_profile="perturbed")
    assert hashlib.sha256(_legacy_backflow_velocity_bytes(perturbed_case / "0/U")).hexdigest() == (
        "95457924cacb02d2cea67295f57dc76f5700407a574c318fed2e7ce3353355d9"
    )


def test_inlet_profile_metadata_matches_boundary_activation_without_changing_inputs(
    tmp_path: Path,
) -> None:
    uniform_case = tmp_path / "metadata-uniform"
    uniform_metadata = dash8.prepare_case(uniform_case, horizon_s=0.5, ranks=2)
    uniform_profile = uniform_metadata["inlet_profile"]
    uniform_boundary = (
        (uniform_case / "0/U")
        .read_text(encoding="utf-8")
        .split("dash8Opening", maxsplit=1)[1]
        .split("plate", maxsplit=1)[0]
    )

    assert "type uniformFixedValue;" in uniform_boundary
    assert "uniformValue table" in uniform_boundary
    assert "(0.5 (0 0 -4.677))" in uniform_boundary
    assert "codedFixedValue" not in uniform_boundary
    assert "DASH8_PROFILE" not in uniform_boundary
    assert uniform_profile["spatial_model"].startswith("normal velocity is spatially uniform")
    assert "piecewise linearly in time" in uniform_profile["temporal_model"]
    assert "cosine" not in uniform_profile["temporal_model"]
    assert uniform_profile["mode"] is None
    assert uniform_profile["seed"] is None
    assert uniform_profile["correlation_time_s"] is None
    assert uniform_profile["spatial_perturbation_active"] is False
    assert uniform_profile["temporal_perturbation_active"] is False
    assert uniform_profile["runtime_boundary_code_active"] is False
    assert uniform_profile["runtime_logging_active"] is False
    assert uniform_profile["runtime_log_prefix"] is None
    assert uniform_profile["runtime_log_fields"] == []
    assert "no runtime boundary log" in uniform_profile["momentum_change"]["diagnostic"]
    # Preserve the historical physics-input hash while explicitly factoring
    # out only the four corrected ambient-backflow tangential components.
    assert _generated_input_tree_sha256(uniform_case, account_for_backflow_fix=True) == (
        "27799c0e9b2301ebc5bc73b9fe9806291c10d2ac7e9fdf71b7badd053c542e92"
    )

    perturbed_case = tmp_path / "metadata-perturbed"
    perturbed_metadata = dash8.prepare_case(
        perturbed_case,
        horizon_s=0.5,
        ranks=2,
        source_profile="perturbed",
    )
    perturbed_profile = perturbed_metadata["inlet_profile"]
    perturbed_boundary = (
        (perturbed_case / "0/U")
        .read_text(encoding="utf-8")
        .split("dash8Opening", maxsplit=1)[1]
        .split("plate", maxsplit=1)[0]
    )
    assert "type codedFixedValue;" in perturbed_boundary
    assert "DASH8_PROFILE" in perturbed_boundary
    assert perturbed_profile["spatial_perturbation_active"] is True
    assert perturbed_profile["temporal_perturbation_active"] is True
    assert perturbed_profile["runtime_boundary_code_active"] is True
    assert perturbed_profile["runtime_logging_active"] is True
    assert perturbed_profile["runtime_log_prefix"] == "DASH8_PROFILE"
    assert "cosine modes" in perturbed_profile["temporal_model"]
    assert "seeded cosine modes" in perturbed_profile["spatial_model"]
    assert perturbed_profile["runtime_log_fields"]
    assert _generated_input_tree_sha256(perturbed_case, account_for_backflow_fix=True) == (
        "d9d2f11fdeb3552180779f6297d4ed6daf39d164234afc0269ab9d3300754558"
    )


def test_open_backflow_velocity_tracks_configured_speed_without_changing_source_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = tmp_path / "default-air"
    reference_metadata = dash8.prepare_case(reference, horizon_s=0.5, ranks=2)
    monkeypatch.setattr(dash8, "AIR_SPEED_M_S", 37.0)
    changed = tmp_path / "changed-air"
    changed_metadata = dash8.prepare_case(changed, horizon_s=0.5, ranks=2)

    assert reference_metadata["air_speed_m_s"] == pytest.approx(50.0)
    assert changed_metadata["air_speed_m_s"] == pytest.approx(37.0)
    assert changed_metadata["boundary_conditions"][
        "open_boundary_backflow_tangential_velocity_m_s"
    ] == [
        37.0,
        0.0,
        0.0,
    ]
    for case, speed in ((reference, 50), (changed, 37)):
        velocity = (case / "0/U").read_text(encoding="utf-8")
        assert f"value uniform ({speed} 0 0);" in _foam_patch_block(velocity, "airInlet")
        for patch in ["xOutlet", "yMin", "yMax", "zMin"]:
            assert f"tangentialVelocity uniform ({speed} 0 0);" in _foam_patch_block(
                velocity, patch
            )

    assert _foam_patch_block((reference / "0/U").read_text(), "dash8Opening") == (
        _foam_patch_block((changed / "0/U").read_text(), "dash8Opening")
    )
    for field in ("k", "epsilon"):
        assert _foam_patch_block((reference / "0" / field).read_text(), "dash8Opening") == (
            _foam_patch_block((changed / "0" / field).read_text(), "dash8Opening")
        )
    assert (reference / "0/alpha.water").read_bytes() == (changed / "0/alpha.water").read_bytes()
    assert (reference / "constant/g").read_bytes() == (changed / "constant/g").read_bytes()


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


def test_default_turbulence_field_bytes_match_the_legacy_generation(tmp_path: Path) -> None:
    case = tmp_path / "dash8-default-turbulence"
    dash8.prepare_case(case, horizon_s=0.1, ranks=2)

    expected_hashes = {
        "k": "f8cbadcaf210d944294d3b5fbbee9fd6d27c2811fc0947ca2e81ebfdfb505eba",
        "epsilon": "3506412c2bd306c675b184975063aea0620d9e3d5c567da624c83ee5312d292d",
    }
    for field_name, expected_hash in expected_hashes.items():
        field_bytes = (case / "0" / field_name).read_bytes()
        assert hashlib.sha256(field_bytes).hexdigest() == expected_hash


def _foam_patch_block(text: str, patch: str) -> str:
    match = re.search(rf"(?ms)^    {re.escape(patch)}\s*\{{(.*?)^    \}}", text)
    assert match is not None, f"patch {patch} is missing"
    return match.group(1)


def test_configured_air_and_water_turbulence_inputs_scale_fields_and_history(
    tmp_path: Path,
) -> None:
    air_intensity = 0.10
    water_intensity = 0.02
    air_length = 0.20
    water_length = 0.08
    case = tmp_path / "dash8-turbulence-sensitivity"
    metadata = dash8.prepare_case(
        case,
        horizon_s=0.5,
        ranks=2,
        air_turbulence_intensity=air_intensity,
        water_turbulence_intensity=water_intensity,
        air_length_scale_m=air_length,
        water_length_scale_m=water_length,
    )

    def expected(speed: float, intensity: float, length_scale: float) -> tuple[float, float]:
        k_value = 1.5 * (intensity * speed) ** 2
        epsilon_value = 0.09**0.75 * k_value**1.5 / length_scale
        return k_value, epsilon_value

    air_k, air_epsilon = expected(50.0, air_intensity, air_length)
    default_air_k, default_air_epsilon = expected(50.0, 0.05, 0.05)
    assert air_k / default_air_k == pytest.approx((air_intensity / 0.05) ** 2)
    assert air_epsilon / default_air_epsilon == pytest.approx(
        (air_intensity / 0.05) ** 3 * (0.05 / air_length)
    )
    for field_name, field_value in (("k", air_k), ("epsilon", air_epsilon)):
        field = (case / "0" / field_name).read_text(encoding="utf-8")
        internal = re.search(r"internalField uniform ([^;]+);", field)
        assert internal is not None
        assert float(internal.group(1)) == pytest.approx(field_value)
        for patch in ("airInlet", "xOutlet", "yMin", "yMax", "zMin"):
            block = _foam_patch_block(field, patch)
            boundary_value = re.search(r"(?:inletValue|value) uniform ([^;]+);", block)
            assert boundary_value is not None
            assert float(boundary_value.group(1)) == pytest.approx(field_value)

    water_history = metadata["source_histories"]["dash8"]["samples_used_m_s"]
    sample_time, sample_speed = water_history[1]
    sample_k, sample_epsilon = expected(sample_speed, water_intensity, water_length)
    default_sample_k, default_sample_epsilon = expected(sample_speed, 0.05, 0.05)
    assert sample_k / default_sample_k == pytest.approx((water_intensity / 0.05) ** 2)
    assert sample_epsilon / default_sample_epsilon == pytest.approx(
        (water_intensity / 0.05) ** 3 * (0.05 / water_length)
    )
    for field_name, expected_value in (("k", sample_k), ("epsilon", sample_epsilon)):
        field = (case / "0" / field_name).read_text(encoding="utf-8")
        source_block = _foam_patch_block(field, "dash8Opening")
        table_rows = re.findall(r"\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)", source_block)
        matching_values = [
            float(value) for time_s, value in table_rows if float(time_s) == sample_time
        ]
        assert matching_values == pytest.approx([expected_value])

    assumptions = metadata["turbulence_assumptions"]
    assert assumptions["air_turbulence_intensity"] == air_intensity
    assert assumptions["water_turbulence_intensity"] == water_intensity
    assert assumptions["air_length_scale_m"] == air_length
    assert assumptions["water_length_scale_m"] == water_length
    assert "intensity" not in assumptions
    reference_k, reference_epsilon = expected(6.0, water_intensity, water_length)
    assert assumptions["source_turbulence_k_m2_s2"] == pytest.approx(reference_k)
    assert assumptions["source_turbulence_epsilon_m2_s3"] == pytest.approx(reference_epsilon)
    peak_k, peak_epsilon = expected(
        assumptions["peak_digitized_source_mean_speed_m_s"], water_intensity, water_length
    )
    assert assumptions["source_k_at_peak_digitized_mean_speed_m2_s2"] == pytest.approx(peak_k)
    assert assumptions["source_epsilon_at_peak_digitized_mean_speed_m2_s3"] == pytest.approx(
        peak_epsilon
    )


def test_turbulence_cli_options_are_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = tmp_path / "dash8-cli-turbulence"
    assert (
        dash8.main(
            [
                "--output",
                str(case),
                "--horizon-s",
                "0.1",
                "--ranks",
                "2",
                "--air-turbulence-intensity",
                "0.08",
                "--water-turbulence-intensity",
                "0.03",
                "--air-length-scale-m",
                "0.12",
                "--water-length-scale-m",
                "0.07",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out
    metadata = json.loads((case / "case-inputs.json").read_text(encoding="utf-8"))
    assumptions = metadata["turbulence_assumptions"]
    assert assumptions["air_turbulence_intensity"] == pytest.approx(0.08)
    assert assumptions["water_turbulence_intensity"] == pytest.approx(0.03)
    assert assumptions["air_length_scale_m"] == pytest.approx(0.12)
    assert assumptions["water_length_scale_m"] == pytest.approx(0.07)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"air_turbulence_intensity": float("nan")}, "air_turbulence_intensity must be finite"),
        ({"water_turbulence_intensity": float("inf")}, "water_turbulence_intensity must be finite"),
        ({"air_turbulence_intensity": 0.0}, "air_turbulence_intensity must be finite and positive"),
        ({"water_turbulence_intensity": 1.01}, "water_turbulence_intensity must be no greater"),
        ({"air_length_scale_m": -0.1}, "air_length_scale_m must be finite and positive"),
        (
            {"water_length_scale_m": float("nan")},
            "water_length_scale_m must be finite and positive",
        ),
    ],
)
def test_invalid_turbulence_inputs_fail_before_output_creation(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    case = tmp_path / "invalid-turbulence-case"
    with pytest.raises(ValueError, match=message):
        dash8.prepare_case(case, horizon_s=0.1, **kwargs)
    assert not case.exists()


@pytest.mark.parametrize(
    ("option", "value"),
    [("--air-turbulence-intensity", "nan"), ("--water-turbulence-intensity", "1.01")],
)
def test_cli_rejects_invalid_turbulence_inputs_before_output_creation(
    tmp_path: Path, option: str, value: str
) -> None:
    case = tmp_path / "invalid-cli-turbulence-case"
    with pytest.raises(SystemExit, match="prepare_case:"):
        dash8.main(["--output", str(case), "--horizon-s", "0.1", option, value])
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
    assert "alternative" in metadata["source_geometry_assumption"]["evidence_class"]
    assert "not reported or measured" in metadata["source_geometry"]["geometry_evidence"]

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


def test_finer_source_region_resolves_small_opening_and_preserves_mass(tmp_path: Path) -> None:
    inner_region = {"x": (-1.11, 1.11), "y": (-0.075, 0.075), "z": (-0.5, 0.0)}
    baseline = dash8.prepare_case(
        tmp_path / "dash8-small-opening-base",
        horizon_s=1.0,
        ranks=20,
        spacing_m=0.08,
        coarse_spacing_m=0.6,
        source_length_m=2.22,
        source_width_m=0.15,
    )
    refined_case = tmp_path / "dash8-small-opening-refined"
    refined = dash8.prepare_case(
        refined_case,
        horizon_s=1.0,
        ranks=20,
        spacing_m=0.08,
        coarse_spacing_m=0.6,
        source_length_m=2.22,
        source_width_m=0.15,
        inner_refinement_region=inner_region,
        inner_spacing_m=0.04,
        turbulence_linear_solver="pbicgstab",
    )

    assert refined["source_patch_areas_m2"] == pytest.approx({"dash8Opening": 0.333})
    assert refined["analytic_expected_mass_kg"] == pytest.approx(
        baseline["analytic_expected_mass_kg"]
    )
    assert refined["mesh_cells_expected"] == math.prod(refined["mesh_shape"].values())
    assert refined["mesh_cells_expected"] > baseline["mesh_cells_expected"]
    assert refined["source_refinement"]["region_m"] == {
        axis: list(bounds) for axis, bounds in inner_region.items()
    }
    assert refined["source_refinement"]["target_spacing_m"] == pytest.approx(0.04)
    assert refined["source_refinement"]["mesh_cells_expected"] == refined["mesh_cells_expected"]
    assert (
        refined["source_refinement"]["source_patch_face_count"]
        == refined["source_patch_face_counts"]["dash8Opening"]
    )
    assert refined["source_refinement"]["source_patch_area_m2"] == pytest.approx(0.333)
    assert (
        refined["source_refinement"]["block_mesh_dict_sha256"]
        == refined["input_hashes"]["block_mesh_dict_sha256"]
    )
    assert len(refined["source_refinement"]["block_mesh_dict_sha256"]) == 64
    assert "axis bands" in refined["source_refinement"]["mesh_interpretation"]
    assert (
        "not true local three-dimensional AMR"
        in refined["source_refinement"]["mesh_interpretation"]
    )

    y_breaks = refined["mesh_breaks_m"]["y"]
    y_widths = refined["mesh_widths_by_segment_m"]["y"]
    y_counts = refined["mesh_cells_per_segment"]["y"]
    source_y_faces = [
        (count, width)
        for lower, upper, count, width in zip(
            y_breaks[:-1], y_breaks[1:], y_counts, y_widths, strict=True
        )
        if -0.075 - 1e-12 <= lower and upper <= 0.075 + 1e-12
    ]
    assert sum(count for count, _ in source_y_faces) == 4
    assert max(width for _, width in source_y_faces) <= 0.04 + 1e-12
    assert refined["source_patch_face_counts"]["dash8Opening"] == 56 * 4
    for name in (
        "0/U",
        "0/alpha.water",
        "0/p_rgh",
        "0/k",
        "0/epsilon",
        "0/nut",
        "constant/transportProperties",
        "constant/turbulenceProperties",
    ):
        assert (refined_case / name).read_bytes() == (
            tmp_path / "dash8-small-opening-base" / name
        ).read_bytes()
    assert "RASModel kEpsilon;" in (refined_case / "constant/turbulenceProperties").read_text(
        encoding="utf-8"
    )
    assert "sigma 0;" in (refined_case / "constant/transportProperties").read_text(encoding="utf-8")
    assert refined["time_controls"]["max_delta_t_s"] < baseline["time_controls"]["max_delta_t_s"]
    assert (
        refined["source_refinement"]["actual_segment_widths_by_axis_m"]
        == refined["mesh_widths_by_segment_m"]
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"inner_spacing_m": 0.04}, "must be provided together"),
        (
            {
                "inner_refinement_region": {
                    "x": (-1.11, 1.11),
                    "y": (-0.075, 0.075),
                    "z": (-0.5, 0.0),
                }
            },
            "must be provided together",
        ),
        (
            {
                "inner_refinement_region": {
                    "x": (-1.11, 1.11),
                    "y": (-0.075, 0.075),
                    "z": (-0.5, 0.0),
                },
                "inner_spacing_m": 0.09,
                "spacing_m": 0.08,
            },
            "no larger than spacing_m",
        ),
        (
            {
                "inner_refinement_region": {
                    "x": (-2.6, 2.6),
                    "y": (-0.2, 0.2),
                    "z": (-0.5, 0.0),
                },
                "inner_spacing_m": 0.04,
            },
            "inside the base refinement region",
        ),
        (
            {
                "inner_refinement_region": {
                    "x": (-1.2, 1.2),
                    "y": (0.01, 0.2),
                    "z": (-0.5, 0.0),
                },
                "inner_spacing_m": 0.04,
            },
            "must cover outlet dash8Opening",
        ),
        (
            {
                "inner_refinement_region": {
                    "x": (-1.11, 1.11),
                    "y": (-0.075, 0.075),
                    "z": (-0.5, 0.0),
                },
                "inner_spacing_m": math.inf,
            },
            "inner_spacing_m must be finite and positive",
        ),
    ],
)
def test_invalid_inner_refinement_fails_before_output_creation(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    output = tmp_path / "invalid-inner-refinement"
    with pytest.raises(ValueError, match=message):
        dash8.prepare_case(output, horizon_s=0.1, **kwargs)
    assert not output.exists()


def test_source_refinement_region_and_spacing_cli_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    region_path = tmp_path / "source-refinement.json"
    region_path.write_text(
        json.dumps({"x": [-1.11, 1.11], "y": [-0.075, 0.075], "z": [-0.5, 0.0]}),
        encoding="utf-8",
    )
    case = tmp_path / "cli-source-refined"
    result = dash8.main(
        [
            "--output",
            str(case),
            "--horizon-s",
            "0.1",
            "--ranks",
            "2",
            "--source-length-m",
            "2.22",
            "--source-width-m",
            "0.15",
            "--spacing-m",
            "0.08",
            "--coarse-spacing-m",
            "0.6",
            "--source-refinement-region-json",
            str(region_path),
            "--source-spacing-m",
            "0.04",
        ]
    )

    assert result == 0
    assert capsys.readouterr().out
    metadata = json.loads((case / "case-inputs.json").read_text(encoding="utf-8"))
    assert metadata["source_refinement"]["region_m"] == {
        "x": [-1.11, 1.11],
        "y": [-0.075, 0.075],
        "z": [-0.5, 0.0],
    }
    assert metadata["source_refinement"]["target_spacing_m"] == pytest.approx(0.04)


def test_seeded_normal_profile_preserves_face_weighted_flux_and_records_momentum_change(
    tmp_path: Path,
) -> None:
    centers = [(-2.035 + 0.37 * ix, -0.1125 + 0.075 * iy) for ix in range(12) for iy in range(4)]
    areas = [0.071 * (0.85 + 0.03 * (index % 7)) for index in range(len(centers))]
    terms = dash8._generate_profile_modes(
        seed=29,
        correlation_time_s=0.18,
        source_length_m=4.44,
        source_width_m=0.30,
        profile_mode="long_wave",
    )
    same_seed_terms = dash8._generate_profile_modes(
        seed=29,
        correlation_time_s=0.18,
        source_length_m=4.44,
        source_width_m=0.30,
        profile_mode="long_wave",
    )
    other_seed_terms = dash8._generate_profile_modes(
        seed=30,
        correlation_time_s=0.18,
        source_length_m=4.44,
        source_width_m=0.30,
        profile_mode="long_wave",
    )
    assert terms == same_seed_terms

    history = dash8.read_primary_history()
    for time_s in (0.17, 0.37, 0.50, 1.23, 2.97):
        mean_speed = dash8._interpolate_history(history, time_s)
        speeds = dash8.evaluate_perturbed_profile(
            centers,
            areas,
            mean_speed_m_s=mean_speed,
            time_s=time_s,
            amplitude=0.35,
            terms=terms,
        )
        area = math.fsum(areas)
        area_mean = math.fsum(a * u for a, u in zip(areas, speeds, strict=True)) / area
        momentum_ratio = math.fsum(a * u * u for a, u in zip(areas, speeds, strict=True)) / (
            area * mean_speed * mean_speed
        )
        assert min(speeds) >= 0.0
        assert area_mean == pytest.approx(mean_speed, abs=1e-12)
        assert momentum_ratio > 1.0

    first = dash8.evaluate_perturbed_profile(
        centers,
        areas,
        mean_speed_m_s=4.677,
        time_s=0.5,
        amplitude=0.35,
        terms=terms,
    )
    second = dash8.evaluate_perturbed_profile(
        centers,
        areas,
        mean_speed_m_s=4.677,
        time_s=0.5,
        amplitude=0.35,
        terms=other_seed_terms,
    )
    assert max(abs(a - b) for a, b in zip(first, second, strict=True)) > 1e-3

    case = tmp_path / "dash8-seeded-profile"
    metadata = dash8.prepare_case(
        case,
        horizon_s=0.5,
        ranks=4,
        source_profile="perturbed",
        profile_amplitude=0.35,
        profile_seed=29,
        profile_correlation_time_s=0.18,
        profile_mode="long_wave",
    )
    velocity = (case / "0/U").read_text(encoding="utf-8")
    source_boundary = velocity.split("dash8Opening", maxsplit=1)[1].split("plate", maxsplit=1)[0]
    assert "type codedFixedValue;" in source_boundary
    assert "this->patch().Cf()" in source_boundary
    assert "this->patch().magSf()" in source_boundary
    assert "returnReduce(localRawAreaSum, sumOp<scalar>())" in source_boundary
    assert "source_area_m2=" in source_boundary
    assert "DASH8_PROFILE" in source_boundary
    assert "source_area_m2" in metadata["inlet_profile"]["runtime_log_fields"]
    assert "random" not in source_boundary.lower()
    assert metadata["inlet_profile"]["instantaneous_area_mean_speed_matches_history"] is True
    assert metadata["inlet_profile"]["momentum_change"]["actual_profile_impulse_status"].startswith(
        "not analytically evaluated"
    )
    assert metadata["analytic_expected_momentum_impulse_by_source_N_s"]["dash8Opening"] is None
    assert metadata["analytic_uniform_reference_momentum_impulse_by_source_N_s"][
        "dash8Opening"
    ] == [*metadata["inlet_profile"]["momentum_change"]["uniform_reference_impulse_N_s"]]
    assert metadata["turbulence_assumptions"]["source_turbulence_reference_speed_m_s"] == 6.0
    assert (
        "not locally rescaled" in metadata["turbulence_assumptions"]["spatial_scaling_assumption"]
    )


def test_parabolic_max_profile_exact_anisotropic_face_moments() -> None:
    centers = [
        (-2.0 / 3.0, -2.0 / 3.0),
        (0.0, -2.0 / 3.0),
        (2.0 / 3.0, -2.0 / 3.0),
        (-2.0 / 3.0, 0.0),
        (0.0, 0.0),
        (2.0 / 3.0, 0.0),
        (-2.0 / 3.0, 2.0 / 3.0),
        (0.0, 2.0 / 3.0),
        (2.0 / 3.0, 2.0 / 3.0),
    ]
    areas = [1.0, 2.0, 1.0, 2.0, 4.0, 2.0, 1.0, 2.0, 1.0]
    moments = dash8.parabolic_max_profile_moment_factors(
        centers,
        areas,
        center_x_m=0.0,
        center_y_m=0.0,
        length_x_m=2.0,
        width_y_m=2.0,
    )

    # Independent exact weighted sums: corners have theta=25/81, edges=5/9,
    # and the center has theta=1. The nonuniform areas test face-area weighting.
    expected_f1 = 49.0 / 81.0
    expected_f2 = 2809.0 / 6561.0
    assert moments["source_face_count"] == 9
    assert moments["source_face_area_m2"] == 16.0
    assert moments["discrete_volume_factor_f1"] == pytest.approx(expected_f1)
    assert moments["discrete_momentum_factor_f2"] == pytest.approx(expected_f2)
    assert moments["sampled_maximum_shape_factor"] == 1.0

    speeds = dash8.evaluate_parabolic_max_profile(
        centers,
        areas,
        maximum_speed_m_s=6.0,
        center_x_m=0.0,
        center_y_m=0.0,
        length_x_m=2.0,
        width_y_m=2.0,
    )
    assert speeds == pytest.approx(
        [
            6.0 * 25.0 / 81.0,
            6.0 * 5.0 / 9.0,
            6.0 * 25.0 / 81.0,
            6.0 * 5.0 / 9.0,
            6.0,
            6.0 * 5.0 / 9.0,
            6.0 * 25.0 / 81.0,
            6.0 * 5.0 / 9.0,
            6.0 * 25.0 / 81.0,
        ]
    )
    assert (
        dash8.evaluate_parabolic_max_profile(
            centers,
            areas,
            maximum_speed_m_s=0.0,
            center_x_m=0.0,
            center_y_m=0.0,
            length_x_m=2.0,
            width_y_m=2.0,
        )
        == [0.0] * 9
    )

    two_by_two = [(-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5)]
    coarse = dash8.parabolic_max_profile_moment_factors(
        two_by_two,
        [1.0, 1.0, 1.0, 1.0],
        center_x_m=0.0,
        center_y_m=0.0,
        length_x_m=2.0,
        width_y_m=2.0,
    )
    assert coarse["sampled_maximum_shape_factor"] == pytest.approx(9.0 / 16.0)
    assert coarse["discrete_volume_factor_f1"] == pytest.approx(9.0 / 16.0)
    assert coarse["discrete_momentum_factor_f2"] == pytest.approx(81.0 / 256.0)


def test_parabolic_max_profile_reports_small_source_face_quadrature_and_fluxes(
    tmp_path: Path,
) -> None:
    inner_region = {
        "x": (-1.11, 1.11),
        "y": (-0.075, 0.075),
        "z": (-0.5, 0.0),
    }
    case = tmp_path / "dash8-parabolic-maximum"
    metadata = dash8.prepare_case(
        case,
        horizon_s=0.5,
        ranks=20,
        spacing_m=0.08,
        coarse_spacing_m=0.3,
        source_length_m=2.22,
        source_width_m=0.15,
        source_profile="parabolic-max",
        inner_refinement_region=inner_region,
        inner_spacing_m=0.04,
    )
    profile = metadata["inlet_profile"]
    moments = profile["discrete_face_center_moments"]

    # Independent face-center integration for the declared 56-by-4 opening mesh.
    assert moments["source_face_count"] == 224
    assert moments["source_face_area_m2"] == pytest.approx(0.333)
    assert moments["discrete_volume_factor_f1"] == pytest.approx(0.45840640943877553)
    assert moments["discrete_momentum_factor_f2"] == pytest.approx(0.28541669206090986)
    assert moments["sampled_maximum_shape_factor"] == pytest.approx(0.9372010522959183)
    assert profile["continuous_volume_factor_f1"] == pytest.approx(4.0 / 9.0)
    assert profile["continuous_momentum_factor_f2"] == pytest.approx((8.0 / 15.0) ** 2)
    assert profile["normal_speed_uses_continuous_shape_without_discrete_max_renormalization"]

    source_history = metadata["source_histories"]["dash8"]["samples_used_m_s"]
    expected_integrated_speed = math.fsum(
        (right[0] - left[0]) * (left[1] + right[1]) / 2.0
        for left, right in zip(source_history[:-1], source_history[1:], strict=True)
    )
    expected_integrated_speed_squared = math.fsum(
        (right[0] - left[0]) * (left[1] ** 2 + left[1] * right[1] + right[1] ** 2) / 3.0
        for left, right in zip(source_history[:-1], source_history[1:], strict=True)
    )
    area = 2.22 * 0.15
    expected_mass = 1000.0 * area * moments["discrete_volume_factor_f1"] * expected_integrated_speed
    expected_impulse = (
        -1000.0 * area * moments["discrete_momentum_factor_f2"] * expected_integrated_speed_squared
    )
    assert metadata["analytic_expected_mass_kg"] == pytest.approx(expected_mass)
    assert metadata["analytic_expected_momentum_impulse_by_source_N_s"][
        "dash8Opening"
    ] == pytest.approx([0.0, 0.0, expected_impulse])

    q05 = profile["q_at_digitized_0p5_s"]
    assert q05["within_case_horizon"] is True
    assert q05["nominal_continuous_maximum_q"] == pytest.approx(7.291443)
    assert q05["sampled_maximum_q"] == pytest.approx(6.404408425588, rel=1e-10)
    assert q05["area_mean_speed_q"] == pytest.approx(1.5321978468815292)
    assert q05["momentum_equivalent_q"] == pytest.approx(2.0810995414106768)
    assert "maximum-speed hypothesis" in profile["source_history_interpretation"]
    assert "not locally rescaled" in profile["turbulence_boundary_assumption"]
    assumptions = metadata["turbulence_assumptions"]
    assert "peak_digitized_source_maximum_speed_m_s" in assumptions
    assert "peak_digitized_source_mean_speed_m_s" not in assumptions
    assert "maximum-speed hypothesis" in assumptions["source_turbulence_reference_note"]

    velocity = (case / "0/U").read_text(encoding="utf-8")
    source_boundary = velocity.split("dash8Opening", maxsplit=1)[1].split("plate", maxsplit=1)[0]
    assert "type codedFixedValue;" in source_boundary
    assert "sourceMaximumSpeeds" in source_boundary
    assert "xNormalized*xNormalized" in source_boundary
    assert "yNormalized*yNormalized" in source_boundary
    assert "globalPeakShapeFactor" in source_boundary
    assert "historyMaximumSpeed*shapeValues[facei]" in source_boundary
    assert "DASH8_PROFILE" in source_boundary
    assert "sampled_maximum_normal_speed_m_s=" in source_boundary
    assert "area_mean_normal_speed_m_s=" in source_boundary
    assert "prescribed_volume_flow_m3_s=" in source_boundary
    assert "normal_momentum_flux_N=" in source_boundary
    assert "operator==(profileValues);" in source_boundary


def test_parabolic_max_profile_is_mesh_independent_and_cli_selectable(tmp_path: Path) -> None:
    domain = {"x": (-5.0, 6.0), "y": (-1.0, 1.0), "z": (-3.0, 0.0)}
    fine_region = {axis: bounds for axis, bounds in domain.items()}
    inner_region = {"x": (-2.22, 2.22), "y": (-0.15, 0.15), "z": (-0.5, 0.0)}
    coarse_case = tmp_path / "parabolic-coarse"
    fine_case = tmp_path / "parabolic-fine"
    coarse_metadata = dash8.prepare_case(
        coarse_case,
        horizon_s=0.5,
        ranks=2,
        spacing_m=0.4,
        coarse_spacing_m=0.8,
        source_profile="parabolic-max",
        domain_bounds_m=domain,
        refinement_region=fine_region,
        inner_refinement_region=inner_region,
        inner_spacing_m=0.2,
    )
    fine_metadata = dash8.prepare_case(
        fine_case,
        horizon_s=0.5,
        ranks=2,
        spacing_m=0.2,
        coarse_spacing_m=0.4,
        source_profile="parabolic-max",
        domain_bounds_m=domain,
        refinement_region=fine_region,
        inner_refinement_region=inner_region,
        inner_spacing_m=0.1,
    )

    coarse_u = (coarse_case / "0/U").read_text(encoding="utf-8")
    fine_u = (fine_case / "0/U").read_text(encoding="utf-8")
    coarse_boundary = coarse_u.split("dash8Opening", maxsplit=1)[1].split("plate", maxsplit=1)[0]
    fine_boundary = fine_u.split("dash8Opening", maxsplit=1)[1].split("plate", maxsplit=1)[0]
    assert coarse_boundary == fine_boundary
    coarse_moments = coarse_metadata["inlet_profile"]["discrete_face_center_moments"]
    fine_moments = fine_metadata["inlet_profile"]["discrete_face_center_moments"]
    assert coarse_moments["sampled_maximum_shape_factor"] != pytest.approx(
        fine_moments["sampled_maximum_shape_factor"]
    )
    assert coarse_moments["discrete_volume_factor_f1"] != pytest.approx(
        fine_moments["discrete_volume_factor_f1"]
    )
    assert (coarse_case / "0/k").read_bytes() == (fine_case / "0/k").read_bytes()
    assert (coarse_case / "0/epsilon").read_bytes() == (fine_case / "0/epsilon").read_bytes()
    parsed = dash8.parse_args(
        ["--output", str(tmp_path / "cli-case"), "--source-profile", "parabolic-max"]
    )
    assert parsed.source_profile == "parabolic-max"


def test_unknown_source_profile_fails_before_output_creation(tmp_path: Path) -> None:
    case = tmp_path / "invalid-source-profile"
    with pytest.raises(ValueError, match="source_profile must be"):
        dash8.prepare_case(case, horizon_s=0.1, source_profile="gaussian")
    assert not case.exists()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"profile_amplitude": 1.01}, "profile_amplitude must lie between"),
        ({"profile_seed": 1.5}, "profile_seed must be an integer"),
        ({"profile_correlation_time_s": 0.0}, "must be finite and positive"),
        ({"profile_mode": "checkerboard"}, "profile_mode must be one of"),
    ],
)
def test_invalid_seeded_profile_controls_fail_before_output_creation(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    case = tmp_path / "invalid-profile-case"
    with pytest.raises(ValueError, match=message):
        dash8.prepare_case(case, horizon_s=0.1, **kwargs)
    assert not case.exists()


def test_width_sensitivity_changes_area_and_release_mass_without_a_breakup_claim(
    tmp_path: Path,
) -> None:
    narrow = dash8.prepare_case(
        tmp_path / "dash8-width-030",
        horizon_s=0.2,
        ranks=4,
        source_width_m=0.30,
    )
    wide = dash8.prepare_case(
        tmp_path / "dash8-width-045",
        horizon_s=0.2,
        ranks=4,
        source_width_m=0.45,
    )

    assert wide["source_patch_areas_m2"]["dash8Opening"] / narrow["source_patch_areas_m2"][
        "dash8Opening"
    ] == pytest.approx(1.5)
    assert wide["analytic_expected_mass_kg"] / narrow["analytic_expected_mass_kg"] == pytest.approx(
        1.5
    )
    note = wide["source_geometry_assumption"]["width_sensitivity_note"]
    assert "no direction of its effect on breakup is assumed" in note


def test_turbulence_matrix_solver_choice_keeps_physical_inputs_and_mesh(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    reference = dash8.prepare_case(baseline, horizon_s=0.1, ranks=2)
    changed = dash8.prepare_case(
        candidate, horizon_s=0.1, ranks=2, turbulence_linear_solver="pbicgstab"
    )
    for name in ("0/U", "0/k", "0/epsilon", "constant/transportProperties", "system/blockMeshDict"):
        assert (baseline / name).read_bytes() == (candidate / name).read_bytes()
    assert reference["analytic_expected_mass_kg"] == changed["analytic_expected_mass_kg"]
    assert reference["mesh_cells_expected"] == changed["mesh_cells_expected"]
    solver = changed["time_controls"]["turbulence_linear_solver"]
    assert solver["choice"] == "pbicgstab"
    assert solver["relative_tolerance"] == solver["final_relative_tolerance"] == 0
    solution = (candidate / "system/fvSolution").read_text()
    assert solution.count("solver PBiCGStab; preconditioner DILU; tolerance 1e-8;") == 2
    assert '"(k|epsilon)Final"' in solution
    assert "maxIter 100;" in solution


def test_invalid_turbulence_solver_preserves_output_absence(tmp_path: Path) -> None:
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="turbulence_linear_solver"):
        dash8.prepare_case(output, turbulence_linear_solver="unknown")
    assert not output.exists()
