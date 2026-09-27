"""Static-only E1 checks; no mesh, CFD, or source scoring is performed."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cases"))

from e1_rouaix_case1_static import prepare_case as case_generator  # noqa: E402
from e1_rouaix_case1_static.static_preparation import (  # noqa: E402
    PACKAGE_DIR,
    SOURCE_PDF_SHA256,
    absent_phase_leakage,
    alpha_correction_volumes,
    alpha_stage_summary,
    check_case_dictionaries,
    check_case_fields,
    check_static_material_and_geometry,
    contour_observable,
    edge_level_crossings,
    figure13_reference_stations,
    nozzle_geometry,
    pressure_reconstruct,
    prgh_from_static,
    score_reference_curve,
    static_input_checks,
    wall_y_serialization_allowance,
    zero_safe_ratio,
)


def test_static_case_field_material_mesh_and_provenance_checks() -> None:
    checks = static_input_checks()
    assert checks
    assert all(check.passed for check in checks), [check for check in checks if not check.passed]
    assert all(check.passed for check in check_case_fields())
    assert all(check.passed for check in check_case_dictionaries())
    assert next(
        check
        for check in checks
        if check.name == "sampler_each_plane_interpolates_and_matches_station"
    ).detail.startswith("30/30")
    assert next(
        check for check in checks if check.name == "nozzle_selection_boundary_then_cylinder_subset"
    ).passed


def test_case1_inlet_flux_and_momentum_are_derived_from_reported_bc() -> None:
    result = nozzle_geometry()
    assert result["classification"] == "derived_from_reported_case1_inputs"
    assert math.isclose(result["area_m2"], math.pi * 0.2**2, rel_tol=1e-14)
    assert math.isclose(result["volume_flow_m3_s"], 1.2566370614359172, rel_tol=1e-14)
    assert math.isclose(result["water_mass_flow_kg_s"], 1253.6211324884712, rel_tol=1e-13)
    assert math.isclose(result["momentum_influx_N"][1], -12536.211324884713, rel_tol=1e-14)
    assert result["momentum_influx_N"][0] == result["momentum_influx_N"][2] == 0.0


def test_p_rgh_pressure_reconstruction_handles_upward_axis_and_both_phases() -> None:
    y = -10.0
    air_p_rgh = prgh_from_static(0.0, 1.18, (0.0, y, 0.0))
    water_p_rgh = prgh_from_static(0.0, 997.6, (0.0, y, 0.0))
    assert math.isclose(air_p_rgh, -115.758, abs_tol=1e-12)
    assert math.isclose(water_p_rgh, -97864.56, abs_tol=1e-9)
    assert math.isclose(pressure_reconstruct(air_p_rgh, 1.18, (0.0, y, 0.0)), 0.0, abs_tol=1e-12)
    assert math.isclose(pressure_reconstruct(water_p_rgh, 997.6, (0.0, y, 0.0)), 0.0, abs_tol=1e-9)
    assert pressure_reconstruct(0.0, 1.18, (0.0, y, 0.0)) > 0.0


def test_zero_reference_ratios_never_divide_and_absent_phase_is_explicit() -> None:
    zero = zero_safe_ratio(0.0, 0.0)
    assert zero["status"] == "not_applicable_zero_reference"
    assert zero["ratio"] is None
    assert zero_safe_ratio(2.0, 0.0)["ratio"] is None

    valid_absent = absent_phase_leakage((3.0, 4.0, 0.0), (0.0, 0.0, 10.0))
    assert valid_absent["status"] == "absent_reference"
    assert valid_absent["ratio"] == 0.5
    assert valid_absent["expected_vector_N"] == [0.0, 0.0, 0.0]
    invalid_absent = absent_phase_leakage((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert invalid_absent["status"] == "invalid_present_reference"
    assert invalid_absent["ratio"] is None


def test_preclip_invalidity_survives_valid_postclip_and_corrections_are_separate() -> None:
    volumes = (2.0, 1.0)
    pre = (-2.0e-6, 0.5)
    post = (0.0, 0.5)
    final = (0.0, 0.5)
    assert alpha_stage_summary(pre, volumes)["valid_at_this_stage"] is False
    assert alpha_stage_summary(pre, volumes)["out_of_range_volume_m3"] == 2.0
    assert alpha_stage_summary(post, volumes)["valid_at_this_stage"] is True
    correction = alpha_correction_volumes(pre, post, final, volumes)
    assert math.isclose(correction["DeltaV_clip_m3"], 4.0e-6, abs_tol=1e-18)
    assert correction["DeltaV_later_m3"] == 0.0


def test_contour_crossings_keep_downward_sign_and_disconnected_outer_span() -> None:
    points = ((0.0, 0.0), (-4.0, 0.0), (-4.0, 2.0))
    crossings = edge_level_crossings(points, (0.0, 1.0, 0.0), threshold=0.5)
    assert crossings == [(-2.0, 0.0), (-4.0, 1.0)]
    triangular = contour_observable(crossings, station_x_over_dj=1.0)
    assert triangular["status"] == "sampled"
    assert triangular["Y"] == 10.0
    assert triangular["Z"] == 2.5

    disconnected = contour_observable(
        ((-4.0, -1.0), (-2.0, 2.0), (-3.0, 0.0)), station_x_over_dj=1.0
    )
    assert disconnected["Y"] == 10.0
    assert disconnected["Z"] == 7.5
    assert contour_observable((), station_x_over_dj=1.0)["status"] == "missing_station"


def test_figure13_station_and_score_semantics_are_static_only() -> None:
    stations = figure13_reference_stations()
    assert set(stations) == {"penetration_y", "width_z"}
    assert len(stations["penetration_y"]) == 20
    assert len(stations["width_z"]) == 10
    assert all(0.0 not in values for values in stations.values())

    reference: dict[str, dict[float, float]] = {name: {} for name in stations}
    source_csv = ROOT / "data" / "derived" / "rouaix_e1_case1_fig13.csv"
    with source_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            x = float(row["x_over_dj"])
            if x:
                reference[row["observable"]][x] = float(row["value_over_dj"])

    exact = score_reference_curve("penetration_y", reference["penetration_y"])
    assert exact["status"] == "scored_static_fixture"
    assert exact["station_count"] == 20
    assert exact["normalization_range"] == 5.225
    assert exact["NRMSE_lower"] == 0.0
    assert exact["NRMSE_upper"] > 0.0

    missing = dict(reference["width_z"])
    missing.pop(stations["width_z"][0])
    unavailable = score_reference_curve("width_z", missing)
    assert unavailable["status"] == "missing_station"
    assert unavailable["missing_x_over_dj"] == [stations["width_z"][0]]


def test_alpha_capture_map_is_present_and_contains_review4_names() -> None:
    text = (PACKAGE_DIR / "ALPHA_CAPTURE_MAP.md").read_text(encoding="utf-8")
    assert all(name in text for name in ("alpha_preclip", "alpha_postclip", "alpha_solver_final"))
    assert "Preserve its validity" in text


def _temporary_case(tmp_path: Path) -> Path:
    package_dir = tmp_path / "package"
    case_dir = package_dir / "case"
    shutil.copytree(PACKAGE_DIR / "case", case_dir)
    shutil.copytree(PACKAGE_DIR / "geometry", package_dir / "geometry")
    return case_dir


def _replace_wall_node_value(case_dir: Path, column: str, value: str) -> None:
    path = case_dir.parent / "geometry" / "top_wall_nodes.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert fieldnames is not None and rows
    rows[0][column] = value
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ("section", "key"),
    (("source", "pdf_sha256"), ("curved_aircraft_wall", "figure3_source_pdf_sha256")),
)
def test_geometry_checker_rejects_each_isolated_source_hash_mismatch(
    tmp_path: Path, section: str, key: str
) -> None:
    case_dir = _temporary_case(tmp_path)
    domain_path = case_dir.parent / "geometry" / "domain.json"
    domain = json.loads(domain_path.read_text(encoding="utf-8"))
    domain[section][key] = "0" * 64
    domain_path.write_text(json.dumps(domain, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checks = {check.name: check for check in check_static_material_and_geometry(case_dir)}
    assert not checks["geometry_source_pdf_identity"].passed
    assert checks["top_wall_nodes_finite"].passed
    assert checks["top_wall_nodes_within_top_footprint"].passed


@pytest.mark.parametrize(
    ("column", "value", "finite_expected"),
    (
        ("x_m", "nan", False),
        ("z_m", "inf", False),
        ("y_m", "-inf", False),
        ("x_m", "17.5001", True),
        ("z_m", "3.5001", True),
        ("y_m", "-0.0000001", True),
        ("y_m", "0.0800001", True),
    ),
)
def test_geometry_checker_rejects_nonfinite_and_out_of_range_wall_nodes(
    tmp_path: Path, column: str, value: str, finite_expected: bool
) -> None:
    case_dir = _temporary_case(tmp_path)
    _replace_wall_node_value(case_dir, column, value)

    checks = {check.name: check for check in check_static_material_and_geometry(case_dir)}
    assert checks["top_wall_nodes_finite"].passed is finite_expected
    assert not checks["top_wall_nodes_within_top_footprint"].passed


def test_geometry_checker_allows_only_justified_wall_csv_rounding(tmp_path: Path) -> None:
    case_dir = _temporary_case(tmp_path)
    domain = json.loads((case_dir.parent / "geometry" / "domain.json").read_text(encoding="utf-8"))
    amplitude = domain["curved_aircraft_wall"]["amplitude_m"]
    allowance = wall_y_serialization_allowance(amplitude)
    assert math.isclose(allowance, 5.0e-11, rel_tol=0.0, abs_tol=1.0e-25)

    _replace_wall_node_value(case_dir, "y_m", format(amplitude + allowance, ".12g"))
    checks = {check.name: check for check in check_static_material_and_geometry(case_dir)}
    assert checks["top_wall_nodes_within_top_footprint"].passed

    _replace_wall_node_value(case_dir, "y_m", format(amplitude + allowance + 1.0e-12, ".12g"))
    checks = {check.name: check for check in check_static_material_and_geometry(case_dir)}
    assert not checks["top_wall_nodes_within_top_footprint"].passed


def test_density_scheme_and_alpha_solver_malformed_dictionaries_fail(tmp_path: Path) -> None:
    case_dir = _temporary_case(tmp_path)
    turbulence_path = case_dir / "constant" / "turbulenceProperties"
    original_turbulence = turbulence_path.read_text(encoding="utf-8")
    turbulence_path.write_text(
        original_turbulence.replace("density variable;", ""), encoding="utf-8"
    )
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check for check in checks if check.name == "provisional_variable_density_top_level"
    ).passed
    turbulence_path.write_text(original_turbulence, encoding="utf-8")

    schemes_path = case_dir / "system" / "fvSchemes"
    original_schemes = schemes_path.read_text(encoding="utf-8")
    bad_schemes = original_schemes.replace("div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;", "")
    schemes_path.write_text(bad_schemes, encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check for check in checks if check.name.startswith("fvSchemes:div(((rho*nuEff)")
    ).passed
    bad_schemes = original_schemes.replace("div(rhoPhi,U) Gauss linearUpwind grad(U);", "")
    schemes_path.write_text(bad_schemes, encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(check for check in checks if check.name == "fvSchemes:div(rhoPhi,U)").passed
    schemes_path.write_text(original_schemes, encoding="utf-8")

    solution_path = case_dir / "system" / "fvSolution"
    original_solution = solution_path.read_text(encoding="utf-8")
    wrong_method = original_solution.replace(
        "reconstructionScheme isoAlpha;", "reconstructionScheme plicRDF;"
    )
    solution_path.write_text(wrong_method, encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check for check in checks if check.name == "fvSolution_alpha_controls_nested_isoAlpha"
    ).passed

    alpha_block_start = original_solution.index('    "alpha.*"')
    alpha_block_end = original_solution.index("\n    }", alpha_block_start) + len("\n    }")
    alpha_block = original_solution[alpha_block_start:alpha_block_end]
    moved_out = original_solution[:alpha_block_start] + original_solution[alpha_block_end:]
    pimple_index = moved_out.index("PIMPLE")
    moved_out = moved_out[:pimple_index] + alpha_block + "\n" + moved_out[pimple_index:]
    solution_path.write_text(moved_out, encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check for check in checks if check.name == "fvSolution_alpha_controls_nested_isoAlpha"
    ).passed


def test_sampler_interpolation_and_nozzle_boundary_order_malformed_fixtures_fail(
    tmp_path: Path,
) -> None:
    case_dir = _temporary_case(tmp_path)
    control_path = case_dir / "system" / "controlDict"
    control = control_path.read_text(encoding="utf-8")
    assert control.count("interpolate     true;") == 30
    control_path.write_text(control.replace("interpolate     true;", "", 1), encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check
        for check in checks
        if check.name == "sampler_each_plane_interpolates_and_matches_station"
    ).passed

    topo_path = case_dir / "system" / "topoSetDict"
    topo = topo_path.read_text(encoding="utf-8")
    topo_path.write_text(topo.replace("patch aircraftWall;", "patch gasInlet;"), encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check for check in checks if check.name == "nozzle_selection_boundary_then_cylinder_subset"
    ).passed

    topo_path.write_text(topo.replace("action new;", "action subset;", 1), encoding="utf-8")
    checks = check_case_dictionaries(case_dir)
    assert not next(
        check for check in checks if check.name == "nozzle_selection_boundary_then_cylinder_subset"
    ).passed


def test_gamg_smoother_and_contact_angle_require_provisional_contract(tmp_path: Path) -> None:
    case_dir = _temporary_case(tmp_path)
    solution_path = case_dir / "system" / "fvSolution"
    solution = solution_path.read_text(encoding="utf-8")
    solution_path.write_text(
        solution.replace("smoother DICGaussSeidel;", "smoother GaussSeidel;"), encoding="utf-8"
    )
    checks = check_case_dictionaries(case_dir)
    assert not next(check for check in checks if check.name == "fvSolution_GAMG_smoother").passed

    alpha_path = case_dir / "0" / "alpha.water"
    alpha = alpha_path.read_text(encoding="utf-8")
    alpha_path.write_text(alpha.replace("limit           gradient;", ""), encoding="utf-8")
    checks = check_case_fields(case_dir)
    assert not next(
        check for check in checks if check.name == "provisional_contact_angle_dictionary"
    ).passed


def test_generator_has_exact_file_set_is_deterministic_and_refuses_unknown_files(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "generated"
    case_dir = output_dir / "case"
    geometry_dir = output_dir / "geometry"
    case_generator.make_case_files(package_dir=output_dir)
    generated_domain = json.loads((geometry_dir / "domain.json").read_text(encoding="utf-8"))
    assert generated_domain["source"]["pdf_sha256"] == SOURCE_PDF_SHA256
    assert (
        generated_domain["curved_aircraft_wall"]["figure3_source_pdf_sha256"] == SOURCE_PDF_SHA256
    )
    assert (
        generated_domain["source"]["pdf_sha256"]
        == generated_domain["curved_aircraft_wall"]["figure3_source_pdf_sha256"]
    )
    assert generated_domain["curved_aircraft_wall"]["classification"] == (
        "assumed analytic wall; not source-derived geometry"
    )
    assert all(check.passed for check in check_case_fields(case_dir))
    assert all(check.passed for check in check_case_dictionaries(case_dir))
    first = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for root in (case_dir, geometry_dir)
        for path in root.rglob("*")
        if path.is_file()
    }
    assert set(first) == set(case_generator.EXPECTED_GENERATED_FILES)
    manifest_first = (output_dir / "CASE_SHA256SUMS").read_bytes()
    manifest_records = manifest_first.decode("utf-8").splitlines()
    assert [record.split("  ", maxsplit=1)[1] for record in manifest_records] == list(
        case_generator.EXPECTED_GENERATED_FILES
    )
    assert all(
        record.split("  ", maxsplit=1)[0] == hashlib.sha256(first[relative]).hexdigest()
        for record, relative in zip(manifest_records, case_generator.EXPECTED_GENERATED_FILES)
    )
    case_generator.make_case_files(package_dir=output_dir)
    second = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for root in (case_dir, geometry_dir)
        for path in root.rglob("*")
        if path.is_file()
    }
    assert second == first
    assert (output_dir / "CASE_SHA256SUMS").read_bytes() == manifest_first

    unknown_output = tmp_path / "unknown-output"
    unknown = unknown_output / "case" / "keep-me.txt"
    unknown.parent.mkdir(parents=True)
    unknown.write_text("preserve me", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown file"):
        case_generator.make_case_files(
            package_dir=unknown_output,
        )
    assert unknown.read_text(encoding="utf-8") == "preserve me"
    assert not (unknown_output / "case" / "0" / "U").exists()

    symlink_output = tmp_path / "symlink-output"
    symlink_output.mkdir()
    external_manifest = tmp_path / "external-manifest.txt"
    external_manifest.write_text("preserve manifest target", encoding="utf-8")
    (symlink_output / "CASE_SHA256SUMS").symlink_to(external_manifest)
    with pytest.raises(ValueError, match="symlink manifest"):
        case_generator.make_case_files(package_dir=symlink_output)
    assert external_manifest.read_text(encoding="utf-8") == "preserve manifest target"

    hardlink_output = tmp_path / "hardlink-output"
    hardlinked_output = hardlink_output / "case" / "0" / "U"
    hardlinked_output.parent.mkdir(parents=True)
    external_field = tmp_path / "external-field.txt"
    external_field.write_text("preserve field target", encoding="utf-8")
    hardlinked_output.hardlink_to(external_field)
    with pytest.raises(ValueError, match="multiply-linked output"):
        case_generator.make_case_files(package_dir=hardlink_output)
    assert external_field.read_text(encoding="utf-8") == "preserve field target"


def test_numeric_helpers_reject_nonfinite_values_and_nonpositive_volumes() -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        alpha_stage_summary((0.5,), (0.0,))
    with pytest.raises(ValueError, match="positive"):
        alpha_correction_volumes((0.0,), (0.0,), (0.0,), (-1.0,))
    with pytest.raises(ValueError, match="finite"):
        alpha_correction_volumes((math.nan,), (0.0,), (0.0,), (1.0,))
    with pytest.raises(ValueError, match="finite"):
        edge_level_crossings(((0.0, 0.0), (1.0, math.inf)), (0.0, 1.0))
    with pytest.raises(ValueError, match="finite"):
        contour_observable(((math.nan, 0.0),), station_x_over_dj=1.0)
    with pytest.raises(ValueError, match="positive"):
        contour_observable(((0.0, 0.0),), station_x_over_dj=1.0, nozzle_diameter_m=0.0)
    with pytest.raises(ValueError, match="finite"):
        pressure_reconstruct(math.inf, 1.0, (0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="positive"):
        prgh_from_static(0.0, 0.0, (0.0, 0.0, 0.0))
    stations = figure13_reference_stations()["penetration_y"]
    nonfinite_curve = {station: 0.0 for station in stations}
    nonfinite_curve[stations[0]] = math.nan
    with pytest.raises(ValueError, match="finite"):
        score_reference_curve("penetration_y", nonfinite_curve)
