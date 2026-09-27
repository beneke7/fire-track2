import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "scripts" / "analyze_restas_ledger.py"
ANALYZER_SPEC = importlib.util.spec_from_file_location("restas_ledger", ANALYZER)
assert ANALYZER_SPEC is not None and ANALYZER_SPEC.loader is not None
ledger = importlib.util.module_from_spec(ANALYZER_SPEC)
sys.modules[ANALYZER_SPEC.name] = ledger
ANALYZER_SPEC.loader.exec_module(ledger)


def _source_rate(time_s: float) -> float:
    if time_s <= 0.0795:
        return -0.72
    if time_s < 0.0805:
        return -0.72 * (1 - (time_s - 0.0795) / 0.001)
    return 0.0


def _endpoint_sampled_source_volume_to(time_s: float) -> float:
    step_count = round(time_s / 0.0001)
    return -sum(_source_rate(step * 0.0001) for step in range(1, step_count + 1)) * 0.0001


def _left_endpoint_sampled_source_volume_to(time_s: float) -> float:
    step_count = round(time_s / 0.0001)
    return -sum(_source_rate(step * 0.0001) for step in range(step_count)) * 0.0001


def _write_table(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _make_run(
    root: Path,
    *,
    exit_code: int = 0,
    max_global_co: float = 0.2,
    max_interface_co: float = 0.1,
    mesh_ok: bool = True,
    mesh_cells: int = 2_081_200,
    startup_global_co: float = 0.1,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    case_dir = root / "case"
    inputs = {
        "solver": "interIsoFoam",
        "protocol_revision": 2,
        "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
        "alpha_phi_sampling_convention": "left_endpoint_of_completed_interval",
        "alpha_phi_left_sampled_expected_release_kg": 230.544,
        "alpha_phi_left_sampled_expected_release_per_slot_kg": 57.636,
        "phi_right_sampled_expected_release_kg": 230.256,
        "phi_right_sampled_expected_release_per_slot_kg": 57.564,
        "openfoam_image": "opencfd/openfoam-default:2512",
        "mesh_cells_expected": 2_081_200,
        "slot_count": 4,
        "expected_released_mass_kg": 230.4,
        "water": {"density_kg_m3": 1000.0},
        "fixed_delta_t_s": 0.0001,
        "adjust_time_step": False,
        "end_time_s": 0.12,
        "time_step_mode": "fixed",
        "expected_time_steps": 1200,
        "n_alpha_sub_cycles": 1,
        "max_courant": 0.5,
        "max_alpha_courant": 0.25,
        "source_profile_m_s": [[0.0, -4.8], [0.0795, -4.8], [0.0805, 0.0], [0.12, 0.0]],
        "source_velocity_m_s": [0.0, 0.0, -4.8],
        "source_constant_velocity_interval_s": [0.0, 0.0795],
        "source_window_s": [0.0, 0.0805],
        "source_shutoff_ramp_s": [0.0795, 0.0805],
        "source_shutoff_s": 0.0805,
        "expected_source_mass_flow_kg_s": 2880.0,
        "source_dose_tolerance_fraction": 0.001,
        "mass_ledger_tolerance_fraction": 0.001,
        "flux_field": "alphaPhi_",
        "flux_patch_names": [*ledger.SLOT_PATCHES, *ledger.OPEN_PATCHES],
        "flux_sample_interval_steps": 1,
        "volume_sample_interval_steps": 1,
        "hard_stop_on_courant_breach": True,
    }
    manifest = {
        "run_id": "synthetic-p1-ledger",
        "solver_image": "opencfd/openfoam-default:2512",
        "solver_image_id": "sha256:synthetic",
        "exit_code": exit_code,
        "case_command_exit_code": exit_code,
        "interisofoam_exit_code": exit_code,
        "reconstruction_exit_code": 0 if exit_code == 0 else None,
        "case_stage_exit_records": [
            {"stage": "blockMesh", "exit_code": 0},
            {"stage": "checkMesh", "exit_code": 0},
            {"stage": "decomposePar", "exit_code": 0},
            {"stage": "interIsoFoam", "exit_code": exit_code},
            *([{"stage": "reconstructPar", "exit_code": 0}] if exit_code == 0 else []),
        ],
        "openfoam_log": "openfoam-console.log",
        "execution": {"wall_time_limit_s": 3600.0},
        "wall_time_s": 120.0,
        "stop_reason": None,
        "stop_confirmed": None,
        "stop_error": None,
        "independent_review": {
            "execution_status": "ready",
            "protocol_revision": 2,
            "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
            "protocol_decision": "approved_with_revisions",
            "protocol_reviewer": "synthetic-protocol-reviewer",
            "amendment_1_review_decision": "approved_with_revisions",
            "amendment_1_reviewer": "synthetic-amendment-reviewer",
            "amendment_1_reviewed_utc": "2026-09-25T00:00:00Z",
            "execution_code_review": "approved",
            "execution_code_reviewer": "synthetic-code-reviewer",
            "execution_code_reviewed_utc": "2026-09-25T00:00:00Z",
        },
    }
    (root / "inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    flux_objects = []
    for patch_name in (*ledger.SLOT_PATCHES, *ledger.OPEN_PATCHES):
        flux_objects.append(
            f"    {patch_name}Flux\n    {{\n"
            "        type surfaceFieldValue;\n"
            "        libs (fieldFunctionObjects);\n"
            "        regionType patch;\n"
            f"        name {patch_name};\n"
            "        operation sum;\n"
            "        fields (phi alphaPhi_);\n"
            "        writeFields false;\n"
            "        executeControl timeStep;\n"
            "        executeInterval 1;\n"
            "        writeControl timeStep;\n"
            "        writeInterval 1;\n"
            "    }"
        )
    control_dict = (
        "application interIsoFoam;\n"
        "startFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        "deltaT 0.0001;\nendTime 0.12;\nadjustTimeStep no;\n"
        "maxCo 0.5;\nmaxAlphaCo 0.25;\n"
        "functions\n{\n"
        "    waterVolume\n    {\n"
        "        type volFieldValue;\n"
        "        libs (fieldFunctionObjects);\n"
        "        writeControl timeStep;\n"
        "        writeInterval 1;\n"
        "        operation volIntegrate;\n"
        "        writeFields false;\n"
        "        fields (alpha.water);\n"
        "    }\n" + "\n".join(flux_objects) + "\n}\n"
    )
    (system_dir / "controlDict").write_text(control_dict, encoding="utf-8")
    (system_dir / "fvSolution").write_text(
        'solvers\n{\n    "alpha.water.*"\n    {\n        nAlphaSubCycles 1;\n    }\n}\n',
        encoding="utf-8",
    )
    constant_dir = case_dir / "constant"
    constant_dir.mkdir(parents=True, exist_ok=True)
    (constant_dir / "transportProperties").write_text(
        "phases (water air);\n"
        "water { transportModel Newtonian; nu 1e-6; rho 1000; }\n"
        "air { transportModel Newtonian; nu 1.48e-5; rho 1.225; }\n",
        encoding="utf-8",
    )
    source_rows = []
    for time_s, z_velocity in inputs["source_profile_m_s"]:
        source_rows.append(f"({time_s:g} (0 0 {z_velocity:g}))")
    source_table = "(" + " ".join(source_rows) + ")"
    velocity_patches = []
    for slot_name in ledger.SLOT_PATCHES:
        velocity_patches.append(
            f"    {slot_name}\n    {{\n"
            "        type uniformFixedValue;\n"
            f"        uniformValue table {source_table};\n"
            "        value uniform (0 0 -4.8);\n"
            "    }"
        )
    (case_dir / "0").mkdir(parents=True, exist_ok=True)
    (case_dir / "0" / "U").write_text(
        "boundaryField\n{\n" + "\n".join(velocity_patches) + "\n}\n", encoding="utf-8"
    )
    final_state = case_dir / "0.120000"
    final_state.mkdir(parents=True, exist_ok=True)
    (final_state / "alpha.water").write_text("synthetic final alpha field\n", encoding="utf-8")

    times = [step * 0.0001 for step in range(1, 1201)]
    for slot_name in ledger.SLOT_PATCHES:
        rows = []
        for time_s in times:
            phi = _source_rate(time_s)
            alpha_phi = _source_rate(time_s - 0.0001)
            rows.append(f"{time_s:.7f}\t{phi:.12g}\t{alpha_phi:.12g}")
        _write_table(
            case_dir / "postProcessing" / f"{slot_name}Flux" / "0" / "surfaceFieldValue.dat",
            "# Time\tsum(phi)\tsum(alphaPhi_)",
            rows,
        )

    open_patch_rates = {"airInlet": -0.0001, "airOutlet": 0.0002, "lowerOutlet": 0.0003}
    for patch_name, flux in open_patch_rates.items():
        rows = [f"{time_s:.7f}\t{flux:.12g}\t{flux:.12g}" for time_s in times]
        _write_table(
            case_dir / "postProcessing" / f"{patch_name}Flux" / "0" / "surfaceFieldValue.dat",
            "# Time\tsum(phi)\tsum(alphaPhi_)",
            rows,
        )

    volume_rows = []
    for time_s in times:
        source_mass_kg = 4 * 1000.0 * _left_endpoint_sampled_source_volume_to(time_s)
        signed_open_mass_kg = 1000.0 * sum(open_patch_rates.values()) * time_s
        volume_m3 = (source_mass_kg - signed_open_mass_kg) / 1000.0
        volume_rows.append(f"{time_s:.7f}\t{volume_m3:.12g}")
    _write_table(
        case_dir / "postProcessing" / "waterVolume" / "0" / "volFieldValue.dat",
        "# Time\tvolIntegrate(alpha.water)",
        volume_rows,
    )

    log_rows = [
        f"    cells: {mesh_cells}",
        "Mesh OK." if mesh_ok else "Mesh check failed.",
        f"Courant Number mean: 0.01 max: {startup_global_co:.7g}",
        "Starting time loop",
    ]
    for time_s in times:
        log_rows.extend(
            (
                f"Courant Number mean: 0.01 max: {max_global_co:.7g}",
                f"Interface Courant Number mean: 0.01 max: {max_interface_co:.7g}",
                f"Time = {time_s:.7f}",
            )
        )
    log_rows.extend(("End", "Exec: reconstructPar -latestTime", "Time = 0.120000", "End"))
    (root / "openfoam-console.log").write_text("\n".join(log_rows) + "\n", encoding="utf-8")
    return root


def _read_table_rows(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_synthetic_source_event_ledger_matches_independent_expected_values(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "synthetic-run")

    report = ledger.build_ledger_report(run_dir)

    # alphaPhi_ at t_n represents the completed interval from the left endpoint.
    expected_slot_mass_kg = 1000.0 * _left_endpoint_sampled_source_volume_to(0.12)
    phi_right_sampled_slot_mass_kg = 1000.0 * _endpoint_sampled_source_volume_to(0.12)
    continuous_slot_mass_kg = 1000.0 * 0.15 * 4.8 * 0.08
    expected_source_mass_kg = 4 * expected_slot_mass_kg
    continuous_source_mass_kg = 4 * continuous_slot_mass_kg
    expected_open_mass_kg = 1000.0 * (-0.0001 + 0.0002 + 0.0003) * 0.12
    expected_box_volume_m3 = (expected_source_mass_kg - expected_open_mass_kg) / 1000.0

    assert report["gate_status"] == "pass_provisional_P1_ledger"
    assert report["gate_decision"]["p1_ledger_passed"]
    assert report["gate_decision"]["e1_e6_passed"] is False
    assert report["proposal_status"]["status"] == "protocol_approved_with_revisions"
    assert report["proposal_status"]["implementation_code_review"] == "approved"
    assert report["checks"]["execution_contract_ready_and_reviewed"]
    assert report["data_completeness"]["source_ramp_interval_count"] == 10
    assert len(report["ledger"]["samples"]) == 1200
    assert report["case_protocol"]["matches_protocol"]
    assert report["case_protocol"]["fvSolution"]["alpha_water_nAlphaSubCycles"] == "1"
    assert report["case_protocol"]["function_objects"]["matches_protocol"]
    assert report["case_protocol"]["transport_properties"]["matches_protocol"]
    assert report["case_protocol"]["transport_properties"]["phases"] == "(water air)"
    assert report["case_protocol"]["transport_properties"]["water_density_kg_m3"] == 1000.0
    assert report["expected_contract"]["max_wall_time_s"] == 3600.0
    assert report["manifest"]["execution_wall_time_limit_s"] == 3600.0
    assert report["manifest"]["wall_time_s"] == 120.0
    assert report["checks"]["manifest_wall_time_limit_is_frozen_3600_s"]
    assert report["checks"]["manifest_wall_time_is_within_limit"]
    assert report["checks"]["solver_exit_zero"]
    assert report["checks"]["case_workflow_exit_zero"]
    assert report["solver_checks"]["solver_loop_time_count"] == 1200
    assert report["solver_checks"]["solver_loop_global_courant_sample_count"] == 1200
    assert report["solver_checks"]["solver_step_diagnostic_group_count"] == 1200
    assert report["solver_checks"]["startup_global_courant_sample_count"] == 1
    assert report["solver_checks"]["global_courant_sample_count_including_startup"] == 1201
    assert report["solver_checks"]["trailing_reconstruction_time_count_ignored"] == 1
    assert report["solver_checks"]["last_solver_time_s"] == 0.12
    assert math.isclose(
        report["ledger"]["source_dose"]["observed_total_kg"],
        expected_source_mass_kg,
        abs_tol=1e-9,
    )
    assert math.isclose(expected_slot_mass_kg, 57.636, abs_tol=1e-10)
    assert math.isclose(expected_source_mass_kg, 230.544, abs_tol=1e-10)
    assert math.isclose(phi_right_sampled_slot_mass_kg, 57.564, abs_tol=1e-10)
    assert report["ledger"]["source_dose"]["alphaPhi_left_sampled_target_total_kg"] == 230.544
    assert report["ledger"]["source_dose"]["phi_right_sampled_target_total_kg"] == 230.256
    assert (
        report["ledger"]["source_dose"]["previous_alphaPhi_right_sampled_target_total_kg"]
        == 230.256
    )
    assert report["ledger"]["source_dose"]["continuous_analytic_target_total_kg"] == 230.4
    assert math.isclose(continuous_source_mass_kg, 230.4, abs_tol=1e-10)
    assert math.isclose(
        report["ledger"]["source_dose"]["relative_error_to_continuous_target"],
        abs(expected_source_mass_kg - continuous_source_mass_kg) / continuous_source_mass_kg,
        abs_tol=1e-12,
    )
    assert math.isclose(
        report["ledger"]["open_patch_outflow"]["signed_net_mass_kg"],
        expected_open_mass_kg,
        abs_tol=1e-9,
    )
    assert math.isclose(
        report["ledger"]["inventory"]["volume_m3"], expected_box_volume_m3, abs_tol=1e-9
    )
    assert abs(report["ledger"]["residual"]["final_signed_kg"]) < 1e-8
    assert report["ledger"]["residual"]["within_proposed_0p1_percent"]
    assert (
        report["ledger"]["residual"]["max_absolute_relative_to_cumulative_measured_source"] < 1e-12
    )
    assert not report["ledger"]["alpha_clipping_and_interface_snap"][
        "separate_correction_diagnostics_available"
    ]
    for slot in ledger.SLOT_PATCHES:
        observed = report["ledger"]["source_dose"]["per_slot"][slot]["observed_mass_kg"]
        assert math.isclose(observed, expected_slot_mass_kg, abs_tol=1e-9)
        assert math.isclose(
            report["ledger"]["source_dose"]["per_slot"][slot]["continuous_analytic_target_mass_kg"],
            continuous_slot_mass_kg,
            abs_tol=1e-10,
        )
        assert math.isclose(
            report["ledger"]["source_dose"]["per_slot"][slot]["phi_observed_mass_kg"],
            phi_right_sampled_slot_mass_kg,
            abs_tol=1e-9,
        )
        assert math.isclose(
            report["ledger"]["phi_vs_alphaPhi_inlet_cross_check"]["per_slot"][slot][
                "relative_difference_using_phi"
            ],
            (expected_slot_mass_kg - phi_right_sampled_slot_mass_kg)
            / phi_right_sampled_slot_mass_kg,
            abs_tol=1e-12,
        )
    assert all(report["checks"].values())
    assert "E1-E6" in report["claim_limit"]


def test_missing_flux_sample_fails_completeness(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "missing-sample")
    path = run_dir / "case" / "postProcessing" / "slot_02Flux" / "0" / "surfaceFieldValue.dat"
    rows = _read_table_rows(path)
    path.write_text("\n".join(row for row in rows if not row.startswith("0.0002000")) + "\n")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert not report["checks"]["source_data_complete"]
    assert report["data_completeness"]["series"]["slot_02"]["missing_step_count"] == 1


def test_missing_solver_time_fails_completeness(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "missing-solver-time")
    log_path = run_dir / "openfoam-console.log"
    log_path.write_text(
        "\n".join(
            line
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("Time = 0.0002000")
        )
        + "\n",
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert not report["checks"]["source_data_complete"]
    assert not report["data_completeness"]["solver_log_times_complete"]


def test_residual_uses_cumulative_measured_source_denominator(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "early-residual")
    volume_path = run_dir / "case" / "postProcessing" / "waterVolume" / "0" / "volFieldValue.dat"
    rows = _read_table_rows(volume_path)
    volume_path.write_text(
        "\n".join(
            row.replace("0.00028796", "0.00028896", 1) if row.startswith("0.0001000") else row
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    residual = report["ledger"]["residual"]
    assert not residual["within_proposed_0p1_percent"]
    assert residual["max_absolute_relative_to_cumulative_measured_source"] > 0.001
    assert residual["max_absolute_percent_of_continuous_target"] < 0.001


def test_malformed_flux_row_and_missing_open_patch_are_reported(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "malformed-data")
    malformed_path = (
        run_dir / "case" / "postProcessing" / "slot_01Flux" / "0" / "surfaceFieldValue.dat"
    )
    rows = _read_table_rows(malformed_path)
    malformed_path.write_text(
        "\n".join(
            row.replace("-0.72\t-0.72", "invalid\t-0.72", 1) if row.startswith("0.0002000") else row
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )
    missing_path = (
        run_dir / "case" / "postProcessing" / "airOutletFlux" / "0" / "surfaceFieldValue.dat"
    )
    missing_path.unlink()

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert not report["data_completeness"]["series"]["slot_01"]["complete"]
    assert any(
        "non-numeric" in issue
        for issue in report["data_completeness"]["series"]["slot_01"]["issues"]
    )
    assert any(
        "cannot read" in issue
        for issue in report["data_completeness"]["series"]["airOutlet"]["issues"]
    )


def test_exit_mesh_and_courant_failures_block_any_p1_pass(tmp_path: Path) -> None:
    run_dir = _make_run(
        tmp_path / "failed-gates",
        exit_code=1,
        max_global_co=0.5001,
        max_interface_co=0.2501,
        mesh_ok=False,
        mesh_cells=2_081_199,
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert not report["checks"]["solver_exit_zero"]
    assert not report["checks"]["mesh_check_and_cell_count"]
    assert not report["checks"]["global_courant_within_proposed_0p5"]
    assert not report["checks"]["interface_courant_within_proposed_0p25"]
    assert report["checks"]["end_time_and_final_state"]
    assert report["solver_checks"]["log_reached_0p12_s"]


def test_authoritative_control_dictionary_mismatch_fails_closed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "control-mismatch")
    control_path = run_dir / "case" / "system" / "controlDict"
    control_path.write_text(
        control_path.read_text(encoding="utf-8").replace("maxCo 0.5;", "maxCo 0.51;"),
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]
    assert not report["case_protocol"]["controlDict"]["checks"]["maxCo"]
    assert any("controlDict maxCo" in issue for issue in report["issues"])


def test_inputs_must_agree_with_authoritative_dictionaries(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "input-mismatch")
    inputs_path = run_dir / "inputs.json"
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    inputs["max_alpha_courant"] = 0.3
    inputs_path.write_text(json.dumps(inputs), encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert not report["case_protocol"]["inputs"]["matches_protocol"]
    assert not report["case_protocol"]["controlDict"]["inputs_agree"]["maxAlphaCo"]
    assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]


def test_slot_source_table_mismatch_fails_closed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "source-profile-mismatch")
    velocity_path = run_dir / "case" / "0" / "U"
    velocity = velocity_path.read_text(encoding="utf-8")
    target = "slot_03\n    {\n        type uniformFixedValue;\n        uniformValue table "
    start = velocity.index(target)
    end = velocity.index("\n    }", start)
    patch = velocity[start:end]
    velocity_path.write_text(
        velocity[:start]
        + patch.replace("(0.0795 (0 0 -4.8))", "(0.0795 (0 0 -4.7))")
        + velocity[end:],
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert not report["case_protocol"]["source_profiles"]["per_slot"]["slot_03"]["matches_protocol"]
    assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]


def test_alpha_subcycle_dictionary_mismatch_fails_closed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "subcycle-mismatch")
    solution_path = run_dir / "case" / "system" / "fvSolution"
    solution_path.write_text(
        solution_path.read_text(encoding="utf-8").replace(
            "nAlphaSubCycles 1;", "nAlphaSubCycles 2;"
        ),
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert not report["case_protocol"]["fvSolution"]["matches_protocol"]
    assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]


def test_function_object_interval_mismatch_fails_closed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "function-object-mismatch")
    control_path = run_dir / "case" / "system" / "controlDict"
    control = control_path.read_text(encoding="utf-8")
    object_start = control.index("    airOutletFlux")
    object_end = control.index("\n    }", object_start)
    object_text = control[object_start:object_end]
    control_path.write_text(
        control[:object_start]
        + object_text.replace("writeInterval 1;", "writeInterval 2;")
        + control[object_end:],
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert not report["case_protocol"]["function_objects"]["objects"]["airOutletFlux"][
        "matches_protocol"
    ]
    assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]


def test_missing_surface_flux_write_fields_setting_fails_closed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "missing-write-fields")
    control_path = run_dir / "case" / "system" / "controlDict"
    control = control_path.read_text(encoding="utf-8")
    object_start = control.index("    airOutletFlux")
    object_end = control.index("\n    }", object_start)
    object_text = control[object_start:object_end]
    control_path.write_text(
        control[:object_start]
        + object_text.replace("        writeFields false;\n", "")
        + control[object_end:],
        encoding="utf-8",
    )

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert (
        "writeFields must be false"
        in report["case_protocol"]["function_objects"]["objects"]["airOutletFlux"]["issues"]
    )
    assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]


def test_openfoam_formatted_start_time_directory_is_discovered(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "formatted-start-time")
    object_names = [f"{name}Flux" for name in (*ledger.SLOT_PATCHES, *ledger.OPEN_PATCHES)]
    object_names.append("waterVolume")
    for object_name in object_names:
        object_dir = run_dir / "case" / "postProcessing" / object_name
        (object_dir / "0").rename(object_dir / "0.000000")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "pass_provisional_P1_ledger"
    assert report["data_completeness"]["complete"]
    for object_name in object_names:
        assert (
            "0.000000"
            in report["data_completeness"]["series"][
                "waterVolume" if object_name == "waterVolume" else object_name.removesuffix("Flux")
            ]["path"]
        )


def test_multiple_function_output_directories_fail_closed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "ambiguous-function-output")
    table_path = run_dir / "case" / "postProcessing" / "slot_01Flux" / "0" / "surfaceFieldValue.dat"
    alternate_path = table_path.parent.parent / "0.000000" / table_path.name
    alternate_path.parent.mkdir(parents=True)
    alternate_path.write_text(table_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert any(
        "found 2 numeric time directories" in issue
        for issue in report["data_completeness"]["series"]["slot_01"]["issues"]
    )


def test_execution_review_status_is_reported_and_gated(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "unreviewed-execution")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["independent_review"]["execution_code_review"] = "pending"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["proposal_status"]["implementation_code_review"] == "pending"
    assert not report["checks"]["execution_contract_ready_and_reviewed"]
    assert report["gate_status"] == "not_passed_provisional_P1_ledger"


def test_solver_exit_code_is_separate_from_runner_gate_exit_code(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "separate-exit-codes")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["interisofoam_exit_code"] = 0
    manifest["exit_code"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["checks"]["solver_exit_zero"]
    assert report["manifest"]["solver_exit_code"] == 0
    assert report["manifest"]["case_command_exit_code"] == 0
    assert report["manifest"]["runner_exit_code"] == 1


def test_aggregate_or_legacy_exit_code_cannot_substitute_for_raw_solver_status(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(tmp_path / "missing-raw-stage-status")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("interisofoam_exit_code")
    manifest["solver_exit_code"] = 0
    manifest["exit_code"] = 0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert not report["checks"]["solver_exit_zero"]
    assert not report["checks"]["case_workflow_exit_zero"]
    assert report["manifest"]["solver_exit_code"] is None
    assert report["gate_status"] == "not_passed_provisional_P1_ledger"


def test_startup_global_courant_is_gated_but_not_counted_as_step(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "startup-courant", startup_global_co=0.5001)

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "not_passed_provisional_P1_ledger"
    assert report["checks"]["courant_rows_complete"]
    assert report["solver_checks"]["solver_loop_global_courant_sample_count"] == 1200
    assert report["solver_checks"]["startup_global_courant_sample_count"] == 1
    assert not report["checks"]["global_courant_within_proposed_0p5"]


def test_extra_per_step_flux_sample_fails_completeness(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "extra-flux-sample")
    path = run_dir / "case" / "postProcessing" / "slot_04Flux" / "0" / "surfaceFieldValue.dat"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("0.1201000\t0\t0\n")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert not report["data_completeness"]["series"]["slot_04"]["complete"]
    assert report["data_completeness"]["series"]["slot_04"]["unexpected_times_s"] == [0.1201]


def test_extra_solver_co_row_fails_step_diagnostic_completeness(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "extra-solver-co")
    log_path = run_dir / "openfoam-console.log"
    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    loop_start = log_lines.index("Starting time loop")
    log_lines.insert(loop_start + 1, "Courant Number mean: 0.01 max: 0.2")
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert not report["checks"]["courant_rows_complete"]
    assert report["solver_checks"]["solver_loop_global_courant_sample_count"] == 1201
    assert report["solver_checks"]["trailing_reconstruction_time_count_ignored"] == 1
    assert report["solver_checks"]["solver_loop_time_count"] == 1200


def test_stopped_or_missing_stop_metadata_cannot_pass_p1(tmp_path: Path) -> None:
    scenarios = (
        (
            {
                "stop_reason": "wall-time limit of 3600 s reached",
                "stop_confirmed": True,
                "stop_error": None,
            },
            (),
        ),
        (
            {
                "stop_reason": "global Co 0.5001 exceeded 0.5",
                "stop_confirmed": True,
                "stop_error": None,
            },
            (),
        ),
        (
            {
                "stop_reason": "interface Co 0.2501 exceeded 0.25",
                "stop_confirmed": False,
                "stop_error": "docker stop and kill failed",
            },
            (),
        ),
        ({"stop_reason": None, "stop_confirmed": False, "stop_error": None}, ()),
        ({"stop_reason": None, "stop_confirmed": "false", "stop_error": None}, ()),
        ({"stop_reason": None, "stop_error": None}, ("stop_confirmed",)),
        ({}, ("stop_reason", "stop_confirmed", "stop_error")),
    )

    for index, (stop_metadata, missing_fields) in enumerate(scenarios):
        run_dir = _make_run(tmp_path / f"stopped-run-{index}")
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(stop_metadata)
        for key in missing_fields:
            manifest.pop(key)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        report = ledger.build_report(run_dir)

        assert report["gate_status"] == "not_passed_provisional_P1_ledger"
        assert report["manifest"]["exit_code"] == 0
        assert not report["checks"]["no_hard_stop_or_stop_error"]
        assert not report["manifest"]["clean_solver_termination"]


def test_manifest_wall_time_over_limit_blocks_p1_even_with_zero_exit(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "wall-time-over-limit")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wall_time_s"] = 3600.001
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["manifest"]["exit_code"] == 0
    assert report["manifest"]["wall_time_s"] == 3600.001
    assert not report["checks"]["manifest_wall_time_is_within_limit"]
    assert report["checks"]["manifest_wall_time_limit_is_frozen_3600_s"]
    assert report["gate_status"] == "not_passed_provisional_P1_ledger"


def test_missing_or_malformed_manifest_wall_time_fails_closed(tmp_path: Path) -> None:
    scenarios = (
        "missing_limit",
        "malformed_execution",
        "string_limit",
        "missing_elapsed",
        "string_elapsed",
        "boolean_elapsed",
    )
    for scenario in scenarios:
        run_dir = _make_run(tmp_path / f"wall-time-{scenario}")
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if scenario == "missing_limit":
            manifest["execution"].pop("wall_time_limit_s")
            expected_failed_check = "manifest_wall_time_limit_is_frozen_3600_s"
        elif scenario == "malformed_execution":
            manifest["execution"] = []
            expected_failed_check = "manifest_wall_time_limit_is_frozen_3600_s"
        elif scenario == "string_limit":
            manifest["execution"]["wall_time_limit_s"] = "3600"
            expected_failed_check = "manifest_wall_time_limit_is_frozen_3600_s"
        elif scenario == "missing_elapsed":
            manifest.pop("wall_time_s")
            expected_failed_check = "manifest_wall_time_is_within_limit"
        elif scenario == "string_elapsed":
            manifest["wall_time_s"] = "120.0"
            expected_failed_check = "manifest_wall_time_is_within_limit"
        else:
            manifest["wall_time_s"] = True
            expected_failed_check = "manifest_wall_time_is_within_limit"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        report = ledger.build_report(run_dir)

        assert not report["checks"][expected_failed_check]
        assert report["gate_status"] == "not_passed_provisional_P1_ledger"


def test_transport_properties_water_density_must_match_protocol_and_inputs(
    tmp_path: Path,
) -> None:
    for mismatch in ("case", "inputs"):
        run_dir = _make_run(tmp_path / f"density-mismatch-{mismatch}")
        if mismatch == "case":
            path = run_dir / "case" / "constant" / "transportProperties"
            path.write_text(
                path.read_text(encoding="utf-8").replace("rho 1000;", "rho 999;"),
                encoding="utf-8",
            )
        else:
            path = run_dir / "inputs.json"
            inputs = json.loads(path.read_text(encoding="utf-8"))
            inputs["water"]["density_kg_m3"] = 999.0
            path.write_text(json.dumps(inputs), encoding="utf-8")

        report = ledger.build_report(run_dir)

        assert report["gate_status"] == "not_passed_provisional_P1_ledger"
        assert not report["checks"]["case_configuration_matches_frozen_P1_protocol"]
        assert not report["case_protocol"]["transport_properties"]["matches_protocol"]
        assert not report["case_protocol"]["transport_properties"]["inputs_agree_with_case"]


def test_missing_and_duplicate_courant_rows_cannot_cancel_out(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path / "mispaired-solver-co")
    log_path = run_dir / "openfoam-console.log"
    original = log_path.read_text(encoding="utf-8").splitlines()
    in_loop = False
    loop_courant_seen = 0
    output = []
    for line in original:
        if line == "Starting time loop":
            in_loop = True
        if in_loop and line == "Courant Number mean: 0.01 max: 0.2":
            loop_courant_seen += 1
            if loop_courant_seen == 100:
                continue
        if in_loop and line == "Time = 0.0002000":
            output.append("Courant Number mean: 0.01 max: 0.2")
        output.append(line)
    log_path.write_text("\n".join(output) + "\n", encoding="utf-8")

    report = ledger.build_report(run_dir)

    assert report["gate_status"] == "inconclusive_incomplete_data"
    assert report["solver_checks"]["solver_loop_global_courant_sample_count"] == 1200
    assert not report["data_completeness"]["solver_step_diagnostics_paired_with_times"]
    assert not report["checks"]["courant_rows_complete"]
