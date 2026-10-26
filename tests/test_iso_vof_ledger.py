from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_iso_vof_ledger import (  # noqa: E402
    KNOWN_SOLVER_SOURCE_HASHES,
    PINNED_IMAGE,
    AuditError,
    audit_run,
)

SOURCE = "dash8Opening"
OPEN = ("airInlet", "xOutlet", "yMin", "yMax", "zMin")
VALID_NUT_LIMITER = """FoamFile
{
    version 2.0;
    format ascii;
    class dictionary;
    location "constant";
    object fvOptions;
}
interfaceNutCap
{
    type limitTurbulenceViscosity;
    active yes;
    log yes;
    limitTurbulenceViscosityCoeffs
    {
        selectionMode geometric;
        updateSelection false;
        selection
        {
            nearSourceBox
            {
                action use;
                source box;
                min (-2.5 -1.5 -3);
                max (4 1.5 0);
            }
        }
        nut nut;
        c 1000;
    }
}
"""


def _write_table(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _make_run(
    root: Path,
    *,
    source_patch: str = SOURCE,
    open_patches: tuple[str, ...] = OPEN,
    wall_patch: str = "plate",
    wall_u_type: str = "slip",
    delta_ts: list[float] | None = None,
    source_fluxes: list[float] | None = None,
    open_fluxes: dict[str, list[float]] | None = None,
    source_geometry: dict[str, object] | None = None,
    configured_end_s: float | None = None,
    n_alpha_subcycles: int = 1,
    dynamic_mesh: str | None = None,
    missing_row: tuple[str, int] | None = None,
) -> Path:
    dt = delta_ts or [0.1, 0.2]
    source = source_fluxes or [-2.0, -3.0]
    opens = open_fluxes or {patch: [0.0] * len(dt) for patch in open_patches}
    assert len(dt) == len(source)
    assert set(opens) == set(open_patches)
    assert all(len(values) == len(dt) for values in opens.values())
    end_s = configured_end_s or sum(dt)
    times: list[float] = []
    clock = 0.0
    volumes: list[float] = []
    volume = 0.0
    for index, step_dt in enumerate(dt):
        clock += step_dt
        times.append(clock)
        volume -= (source[index] + sum(opens[patch][index] for patch in open_patches)) * step_dt
        volumes.append(volume)

    case = root / "case"
    system = case / "system"
    constant = case / "constant"
    zero = case / "0"
    system.mkdir(parents=True)
    constant.mkdir(parents=True)
    zero.mkdir(parents=True)
    case_inputs = {
        "solver": "interIsoFoam",
        "openfoam_image": "opencfd/openfoam-default:2512",
        "openfoam_image_digest": PINNED_IMAGE,
        "horizon_s": end_s,
        "fluid_properties": {"water": {"rho_kg_m3": 1000.0}},
        "source_patches": [source_patch],
        "open_patches": list(open_patches),
    }
    if source_geometry is not None:
        case_inputs["source_geometry"] = source_geometry
    (case / "case-inputs.json").write_text(json.dumps(case_inputs), encoding="utf-8")
    flux_function_objects = []
    for patch in (source_patch, *open_patches):
        flux_function_objects.append(
            f"{patch}Flux {{ type surfaceFieldValue; regionType patch; name {patch}; "
            "operation sum; fields (phi alphaPhi_); executeControl timeStep; "
            "executeInterval 1; writeControl timeStep; writeInterval 1; }"
        )
    function_objects = (
        "functions { waterVolume { type volFieldValue; operation volIntegrate; "
        "fields (alpha.water); executeControl timeStep; executeInterval 1; "
        "writeControl timeStep; writeInterval 1; } " + " ".join(flux_function_objects) + " }"
    )
    (system / "controlDict").write_text(
        "application interIsoFoam;\n"
        "startFrom startTime;\nstartTime 0;\n"
        f"endTime {end_s:.12g};\n"
        "timeFormat fixed;\ntimePrecision 6;\n" + function_objects,
        encoding="utf-8",
    )
    (system / "fvSolution").write_text(
        "alphaControls {\n"
        f"    nAlphaSubCycles {n_alpha_subcycles};\n"
        "}\nPIMPLE {\n    nOuterCorrectors 1;\n}\n",
        encoding="utf-8",
    )
    (constant / "transportProperties").write_text(
        "phases (water air);\n"
        "water { transportModel Newtonian; nu 1e-6; rho 1000; }\n"
        "air { transportModel Newtonian; nu 1.5e-5; rho 1.2; }\n"
        "sigma 0;\n",
        encoding="utf-8",
    )
    mesh = constant / "polyMesh"
    mesh.mkdir()
    boundary_entries = [f"{source_patch} {{ type patch; }}"]
    boundary_entries.extend(f"{patch} {{ type patch; }}" for patch in open_patches)
    boundary_entries.append(f"{wall_patch} {{ type wall; }}")
    (mesh / "boundary").write_text(
        f"{len(boundary_entries)}\n(\n" + "\n".join(boundary_entries) + "\n)\n",
        encoding="utf-8",
    )
    if dynamic_mesh is not None:
        (constant / "dynamicMeshDict").write_text(
            f"dynamicFvMesh {dynamic_mesh};\n", encoding="utf-8"
        )
    (zero / "alpha.water").write_text("internalField uniform 0;\n", encoding="utf-8")
    velocity_conditions = [f"{source_patch} {{ type uniformFixedValue; }}"]
    velocity_conditions.extend(
        f"{patch} {{ type pressureInletOutletVelocity; }}" for patch in open_patches
    )
    velocity_conditions.append(f"{wall_patch} {{ type {wall_u_type}; }}")
    (zero / "U").write_text(
        "boundaryField {\n" + "\n".join(velocity_conditions) + "\n}\n",
        encoding="utf-8",
    )

    volume_rows = []
    for index, (time_s, volume_m3) in enumerate(zip(times, volumes)):
        if missing_row == ("waterVolume", index):
            continue
        volume_rows.append(f"{time_s:.6f}\t{volume_m3:.12g}")
    _write_table(
        case / "postProcessing/waterVolume/0.000000/volFieldValue.dat",
        "# Time\tvolIntegrate(alpha.water)",
        volume_rows,
    )

    for patch in (source_patch, *open_patches):
        q_values = source if patch == source_patch else opens[patch]
        rows = []
        for index, (time_s, q_value) in enumerate(zip(times, q_values)):
            if missing_row == (patch, index):
                continue
            rows.append(f"{time_s:.6f}\t0\t{q_value:.12g}")
        _write_table(
            case / f"postProcessing/{patch}Flux/0.000000/surfaceFieldValue.dat",
            "# Time\tsum(phi)\tsum(alphaPhi_)",
            rows,
        )

    log_lines = ["OpenFOAM 2512 solver log"]
    for time_s, step_dt in zip(times, dt):
        log_lines.extend((f"deltaT = {step_dt:.12f}", f"Time = {time_s:.6f}"))
    (case / "log.interIsoFoam").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    frozen_paths = (
        "0/U",
        "0/alpha.water",
        "case-inputs.json",
        "constant/transportProperties",
        "constant/polyMesh/boundary",
        "system/controlDict",
        "system/fvSolution",
    )
    frozen_hashes = {
        relative: hashlib.sha256((case / relative).read_bytes()).hexdigest()
        for relative in frozen_paths
    }
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "solver_image": "opencfd/openfoam-default:2512",
                "solver_image_id": PINNED_IMAGE,
                "prepared_case_sha256": frozen_hashes,
            }
        ),
        encoding="utf-8",
    )
    return case


def _make_fixed_dt_run(
    root: Path,
    *,
    include_rouaix_wall_flux: bool = False,
    native_delta_t_tokens: tuple[str, ...] | None = None,
    metadata_delta_t: float | None = None,
) -> Path:
    source_patch = "nozzle" if include_rouaix_wall_flux else SOURCE
    open_patches = (
        ("gasInlet", "downstreamOutlet", "bottomOutlet", "spanwiseMinus", "spanwisePlus")
        if include_rouaix_wall_flux
        else OPEN
    )
    case = _make_run(
        root,
        source_patch=source_patch,
        open_patches=open_patches,
        wall_patch="aircraftWall" if include_rouaix_wall_flux else "plate",
        wall_u_type="noSlip" if include_rouaix_wall_flux else "slip",
        delta_ts=[0.001, 0.001],
        configured_end_s=0.05,
    )
    control_path = case / "system/controlDict"
    control = control_path.read_text(encoding="utf-8").replace(
        "timeFormat fixed;\ntimePrecision 6;",
        "timeFormat fixed;\ntimePrecision 12;\n"
        "deltaT 0.001;\nadjustTimeStep no;\nrunTimeModifiable false;\n"
        "stopAt endTime;\n"
        "writeControl runTime;\nwriteInterval 0.05;",
    )
    if include_rouaix_wall_flux:
        before, closing = control.rsplit(" }", 1)
        wall_object = (
            " aircraftWallFlux { type surfaceFieldValue; libs (fieldFunctionObjects); "
            "regionType patch; name aircraftWall; operation sum; fields (phi alphaPhi_); "
            "writeFields false; executeControl timeStep; executeInterval 1; "
            "writeControl timeStep; writeInterval 1; }"
        )
        extrema_objects = (
            " alphaExtrema { type fieldMinMax; libs (fieldFunctionObjects); "
            "fields (alpha.water); location false; log true; writePrecision 12; "
            "executeControl timeStep; executeInterval 1; writeControl timeStep; "
            "writeInterval 1; }"
            " speedExtrema { type fieldMinMax; libs (fieldFunctionObjects); "
            "mode magnitude; fields (U); location false; log true; writePrecision 12; "
            "executeControl timeStep; executeInterval 1; writeControl timeStep; "
            "writeInterval 1; }"
        )
        control = before + wall_object + extrema_objects + " }" + closing
    control_path.write_text(control, encoding="utf-8")

    inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    case_inputs["time_controls"] = {
        "adjust_time_step": False,
        "delta_t_s": 0.001 if metadata_delta_t is None else metadata_delta_t,
        "fixed_delta_t": True,
    }
    inputs_path.write_text(json.dumps(case_inputs), encoding="utf-8")
    _refresh_prepared_hash(case, "system/controlDict")
    _refresh_prepared_hash(case, "case-inputs.json")
    for path in case.glob("postProcessing/*/0.000000/*.dat"):
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("0.001000\t", "0.001000000000\t").replace(
                "0.002000\t", "0.002000000000\t"
            ),
            encoding="utf-8",
        )

    log_lines = ["OpenCFD OpenFOAM v2512", "Time = 0.000000000000"]
    if native_delta_t_tokens is None:
        log_lines.append("Time = 0.001000000000")
    else:
        log_lines.extend((f"deltaT = {native_delta_t_tokens[0]}", "Time = 0.001000000000"))
    log_lines.extend(
        (
            "ExecutionTime = 48.3 s  ClockTime = 52 s",
            "fieldMinMax speedExtrema write:",
            "    min/max(mag(U)) = 0.000000000000e+00 9.267239048760e+07",
            "Courant Number mean: 1.1986208009 max: 5964502.69592",
        )
    )
    if native_delta_t_tokens is None:
        log_lines.append("Time = 0.002000000000")
    else:
        log_lines.extend((f"deltaT = {native_delta_t_tokens[1]}", "Time = 0.002000000000"))
    (case / "log.interIsoFoam").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return case


def test_dash8_rouaix_dash8_patch_names_are_run_local(tmp_path: Path) -> None:
    first_dash8 = _make_run(tmp_path / "first-dash8")
    first_summary = audit_run(first_dash8, tmp_path / "first-dash8-ledger")

    rouaix_open = (
        "gasInlet",
        "downstreamOutlet",
        "bottomOutlet",
        "spanwiseMinus",
        "spanwisePlus",
    )
    source_geometry = {
        "patch": "nozzle",
        "measured_area_m2": 0.12546554934822965,
        "analytic_circle_area_m2": 3.141592653589793 * 0.2**2,
        "relative_area_deviation_fraction": -0.00157688,
        "velocity_renormalized": False,
    }
    rouaix = _make_run(
        tmp_path / "rouaix",
        source_patch="nozzle",
        open_patches=rouaix_open,
        wall_patch="aircraftWall",
        wall_u_type="noSlip",
        open_fluxes={patch: [0.01, 0.02] for patch in rouaix_open},
        source_geometry=source_geometry,
    )
    rouaix_summary = audit_run(rouaix, tmp_path / "rouaix-ledger")

    second_dash8 = _make_run(tmp_path / "second-dash8")
    second_summary = audit_run(second_dash8, tmp_path / "second-dash8-ledger")

    assert first_summary["integration"]["source_patch"] == SOURCE
    assert first_summary["integration"]["open_patches"] == list(OPEN)
    assert second_summary["integration"]["source_patch"] == SOURCE
    assert second_summary["integration"]["open_patches"] == list(OPEN)
    integration = rouaix_summary["integration"]
    assert integration["source_patch"] == "nozzle"
    assert integration["open_patches"] == list(rouaix_open)
    assert integration["injected_kg"] == pytest.approx(800.0)
    assert integration["signed_net_escape_kg"] == pytest.approx(25.0)
    assert integration["native_function_inventory_kg"] == pytest.approx(775.0)
    assert integration["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)
    assert integration["source_geometry"] == source_geometry
    ledger_rows = _read_csv(tmp_path / "rouaix-ledger" / "ledger.csv")
    assert ledger_rows[0]["source_alphaPhi_m3_s"] == "-2"
    assert ledger_rows[0]["nozzle_alphaPhi_m3_s"] == "-2"
    assert ledger_rows[0]["gasInlet_alphaPhi_m3_s"] == "0.01"
    assert "dash8Opening_alphaPhi_m3_s" not in ledger_rows[0]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_patches", None, "explicitly declare exactly one source"),
        ("open_patches", None, "explicitly declare a nonempty open_patches"),
        ("source_patches", ["xOutlet"], "source_patches and open_patches must be disjoint"),
        ("open_patches", ["xOutlet", "xOutlet"], "must not contain duplicate"),
        ("open_patches", ["bad/name"], "must be OpenFOAM word identifiers"),
        ("open_patches", ["waterVolume"], "collide with ledger series names"),
        ("open_patches", ["source"], "collide with ledger series names"),
    ],
)
def test_case_must_explicitly_declare_valid_nonoverlapping_ledger_patches(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    case = _make_run(tmp_path / field.replace("_", "-"))
    inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    if value is None:
        case_inputs.pop(field)
    else:
        case_inputs[field] = value
    inputs_path.write_text(json.dumps(case_inputs), encoding="utf-8")

    with pytest.raises(AuditError, match=message):
        audit_run(case, tmp_path / "ledger-out")


def _refresh_prepared_hash(case: Path, relative: str) -> None:
    manifest_path = case.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prepared_case_sha256"][relative] = hashlib.sha256(
        (case / relative).read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _native_solver_record() -> dict[str, object]:
    return {
        "module_name": "OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH",
        "version": "v2512",
        "build": "OpenFOAM-v2512",
        "wm_options": "linux64CrayDPInt32Opt",
        "architecture": "x86_64",
        "precision": "DP",
        "label_size_bits": 32,
        "executable_path": "/opt/openfoam/v2512/platforms/linux64CrayDPInt32Opt/bin/interIsoFoam",
        "executable_sha256": "a" * 64,
        "solver_banner_sha256": "b" * 64,
    }


def _write_native_source_evidence(path: Path) -> Path:
    source_paths = {
        "isoAdvectionTemplates.C": "src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvectionTemplates.C",
        "interIsoFoam_alphaEqnSubCycle.H": "applications/solvers/multiphase/interIsoFoam/alphaEqnSubCycle.H",
        "interIsoFoam_alphaEqn.H": "applications/solvers/multiphase/interIsoFoam/alphaEqn.H",
        "isoAdvection.H": "src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvection.H",
    }
    source_records = {
        name: {
            "path": f"/opt/openfoam/v2512/{relative}",
            "sha256": KNOWN_SOLVER_SOURCE_HASHES[name],
        }
        for name, relative in source_paths.items()
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "execution_backend": "slurm-native",
                "source_reference_image_digest": PINNED_IMAGE,
                "solver_source": source_records,
                "native_solver": _native_solver_record(),
            }
        ),
        encoding="utf-8",
    )
    return path


def _configure_native_run(case: Path, evidence: Path) -> Path:
    case_inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(case_inputs_path.read_text(encoding="utf-8"))
    case_inputs.update(
        execution_backend="slurm-native",
        solver_version="v2512",
        reference_image_digest=PINNED_IMAGE,
    )
    case_inputs.pop("openfoam_image", None)
    case_inputs.pop("openfoam_image_digest", None)
    case_inputs_path.write_text(json.dumps(case_inputs), encoding="utf-8")
    _refresh_prepared_hash(case, "case-inputs.json")

    manifest_path = case.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("solver_image", None)
    manifest.pop("solver_image_id", None)
    manifest.update(
        execution_backend="slurm-native",
        solver_version="v2512",
        native_solver=_native_solver_record(),
        native_source_evidence_path=str(evidence.resolve()),
        native_source_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _install_fv_options(case: Path, text: str) -> Path:
    path = case / "constant/fvOptions"
    path.write_text(text, encoding="utf-8")
    _refresh_prepared_hash(case, "constant/fvOptions")
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_native_dt_step_average_closes_where_trapezoid_does_not(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "synthetic-run")
    output = tmp_path / "ledger-out"

    summary = audit_run(case, output)

    assert summary["coverage"]["configured_horizon_reached"] is True
    assert summary["integration"]["injected_kg"] == pytest.approx(800.0)
    assert summary["integration"]["native_function_inventory_kg"] == pytest.approx(800.0)
    assert summary["integration"]["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)
    assert summary["formal_validation_decision"] is None
    assert summary["mutable_data_snapshot"]["captured_file_count"] == 8
    assert summary["mutable_data_snapshot"]["snapshot_files"]
    assert summary["prepared_input_hash_verification"]["verification_status"] == "verified"
    assert summary["supported_configuration"]["turbulent_viscosity_limiter"] == {
        "active": False,
        "status": "not configured",
    }

    # Treating the interval-average source fluxes as point samples gives only
    # 0.6 m^3 by trapezoid (including zero initial flux), versus 0.8 m^3 by
    # the required sum(Q_k * deltaT_k).
    trapezoid_source_m3 = 0.5 * (0.0 - 2.0) * 0.1 + 0.5 * (-2.0 - 3.0) * 0.2
    assert trapezoid_source_m3 == pytest.approx(-0.6)
    assert summary["integration"]["injected_kg"] + 1000.0 * trapezoid_source_m3 == pytest.approx(
        200.0
    )
    assert {p.name for p in output.iterdir()} == {"ledger.csv", "summary.json"}
    rows = _read_csv(output / "ledger.csv")
    assert len(rows) == 2
    assert float(rows[-1]["native_deltaT_s"]) == pytest.approx(0.2)
    assert summary["integration"]["deltaT_source_mode"] == "native-paired"


def test_fixed_control_dict_accepts_actual_n1_control_and_r2_log_format(
    tmp_path: Path,
) -> None:
    case = _make_fixed_dt_run(tmp_path / "fixed-r2-format", include_rouaix_wall_flux=True)
    # Exact frozen controlDict bytes from job 14647712's verified result archive
    # (SHA-256 605cc684...7861); its own file hash is asserted below.
    control_fixture = Path(__file__).parent / "fixtures/rouaix-n1-controlDict-14647712.txt"
    fixture_bytes = control_fixture.read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest() == (
        "70a17524ea3ac707d1f34d1b3e0efada04cc1d22ac1dc60874b2d4c10e10ab18"
    )
    (case / "system/controlDict").write_bytes(fixture_bytes)
    inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    case_inputs["horizon_s"] = 0.01
    case_inputs["time_controls"].update(
        max_delta_t_s=0.001,
        full_field_write_times_s=[0.0, 0.01],
        snapshot_interval_s=0.01,
        startup_steps=10,
    )
    inputs_path.write_text(json.dumps(case_inputs), encoding="utf-8")
    _refresh_prepared_hash(case, "system/controlDict")
    _refresh_prepared_hash(case, "case-inputs.json")
    log_path = case / "log.interIsoFoam"
    raw_log = log_path.read_bytes()
    assert b"deltaT =" not in raw_log
    assert b"min/max(mag(U)) = 0.000000000000e+00 9.267239048760e+07" in raw_log

    summary = audit_run(case, tmp_path / "fixed-r2-format-ledger")

    integration = summary["integration"]
    assert integration["deltaT_source_mode"] == "fixed-controlDict"
    assert integration["configured_deltaT_token"] == "0.001"
    assert integration["rounding_diagnostic"]["first_interval_deltaT_s"] == pytest.approx(0.001)
    assert integration["rounding_diagnostic"]["cumulative_deltaT_print_rounding_bound_s"] == 0
    assert integration["rounding_diagnostic"]["first_native_deltaT_s"] is None
    assert "no native log line is fabricated" in integration["rounding_diagnostic"]["warning"]
    log_row_counts = summary["row_coverage"]["solverLog"]
    assert log_row_counts["deltaT_source_mode"] == "fixed-controlDict"
    assert log_row_counts["complete_paired_rows_total"] is None
    assert log_row_counts["snapshot_sha256"] == hashlib.sha256(raw_log).hexdigest()
    rows = _read_csv(tmp_path / "fixed-r2-format-ledger" / "ledger.csv")
    assert len(rows) == 2
    assert rows[0]["interval_deltaT_s"] == "0.001"
    assert rows[0]["native_deltaT_s"] == ""
    assert rows[0]["deltaT_source_mode"] == "fixed-controlDict"
    assert integration["source_patch"] == "nozzle"


@pytest.mark.parametrize(
    ("old_time", "new_time"),
    [
        ("Time = 0.001000000000", "Time = 0.002000000000"),
        ("Time = 0.002000000000", "Time = 0.003000000000"),
    ],
)
def test_fixed_control_dict_rejects_missing_or_skipped_time_even_at_unmatched_tail(
    tmp_path: Path, old_time: str, new_time: str
) -> None:
    case = _make_fixed_dt_run(tmp_path / "fixed-time-gap")
    log_path = case / "log.interIsoFoam"
    log_path.write_text(
        log_path.read_text(encoding="utf-8").replace(old_time, new_time, 1),
        encoding="utf-8",
    )

    with pytest.raises(AuditError, match="fixed controlDict deltaT cumulative time differs"):
        audit_run(case, tmp_path / "fixed-time-gap-ledger")


@pytest.mark.parametrize(
    ("old_value", "new_value"),
    [
        ("runTimeModifiable false;", "runTimeModifiable true;"),
        ("startFrom startTime;", "startFrom latestTime;"),
        ("writeControl runTime;", "writeControl adjustableRunTime;"),
    ],
)
def test_fixed_control_dict_requires_immutable_clean_time_controls(
    tmp_path: Path, old_value: str, new_value: str
) -> None:
    case = _make_fixed_dt_run(tmp_path / "fixed-config-change")
    control_path = case / "system/controlDict"
    control_path.write_text(
        control_path.read_text(encoding="utf-8").replace(old_value, new_value),
        encoding="utf-8",
    )
    _refresh_prepared_hash(case, "system/controlDict")

    with pytest.raises(AuditError, match="does not meet fixed-controlDict fallback requirements"):
        audit_run(case, tmp_path / "fixed-config-change-ledger")


def test_fixed_control_dict_requires_case_metadata_and_frozen_hashes(tmp_path: Path) -> None:
    mismatch = _make_fixed_dt_run(tmp_path / "fixed-metadata-mismatch", metadata_delta_t=0.002)
    with pytest.raises(AuditError, match="case-inputs time_controls.delta_t_s differs"):
        audit_run(mismatch, tmp_path / "fixed-metadata-mismatch-ledger")

    missing_hash = _make_fixed_dt_run(tmp_path / "fixed-missing-hash")
    manifest_path = missing_hash.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prepared_case_sha256"].pop("system/controlDict")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AuditError, match="freezes both system/controlDict and case-inputs.json"):
        audit_run(missing_hash, tmp_path / "fixed-missing-hash-ledger")


def test_fixed_control_dict_rejects_conflicting_native_delta_t_line(tmp_path: Path) -> None:
    case = _make_fixed_dt_run(
        tmp_path / "fixed-native-conflict", native_delta_t_tokens=("0.002", "0.001")
    )

    with pytest.raises(AuditError, match="conflicts with frozen controlDict deltaT"):
        audit_run(case, tmp_path / "fixed-native-conflict-ledger")


def test_fixed_control_dict_rejects_modified_failure_locations_object(tmp_path: Path) -> None:
    case = _make_fixed_dt_run(
        tmp_path / "fixed-failure-locations-variation", include_rouaix_wall_flux=True
    )
    control_path = case / "system/controlDict"
    fixture = Path(__file__).parent / "fixtures/rouaix-n1-controlDict-14647712.txt"
    control = fixture.read_text(encoding="utf-8").replace(
        "fields (U p_rgh k epsilon nut);", "fields (U p_rgh k epsilon nut Ux);"
    )
    control_path.write_text(control, encoding="utf-8")
    _refresh_prepared_hash(case, "system/controlDict")

    with pytest.raises(AuditError, match="does not meet fixed-controlDict fallback requirements"):
        audit_run(case, tmp_path / "fixed-failure-locations-variation-ledger")


@pytest.mark.parametrize("programmable_input", ["coded-boundary", "include"])
def test_fixed_control_dict_rejects_programmable_time_or_boundary_inputs(
    tmp_path: Path, programmable_input: str
) -> None:
    case = _make_fixed_dt_run(tmp_path / f"fixed-{programmable_input}")
    if programmable_input == "coded-boundary":
        velocity_path = case / "0/U"
        velocity_path.write_text(
            velocity_path.read_text(encoding="utf-8").replace(
                f"{SOURCE} {{ type uniformFixedValue; }}",
                f"{SOURCE} {{ type codedFixedValue; code #{{ operator==(value); #}} }}",
            ),
            encoding="utf-8",
        )
        _refresh_prepared_hash(case, "0/U")
    else:
        control_path = case / "system/controlDict"
        control_path.write_text(
            '#include "runtime-control"\n' + control_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        _refresh_prepared_hash(case, "system/controlDict")

    with pytest.raises(AuditError, match="does not meet fixed-controlDict fallback requirements"):
        audit_run(case, tmp_path / f"fixed-{programmable_input}-ledger")


def test_nested_nut_limiter_passes_full_native_ledger_audit_and_is_hashed(
    tmp_path: Path,
) -> None:
    case = _make_run(tmp_path / "nut-limiter-run")
    option_path = _install_fv_options(case, VALID_NUT_LIMITER)

    summary = audit_run(case, tmp_path / "nut-limiter-out")

    limiter = summary["supported_configuration"]["turbulent_viscosity_limiter"]
    assert limiter["active"] is True
    assert limiter["type"] == "limitTurbulenceViscosity"
    assert limiter["corrected_field"] == "nut"
    assert limiter["coefficient_c"] == pytest.approx(1000.0)
    assert limiter["box_min_m"] == [-2.5, -1.5, -3.0]
    assert limiter["box_max_m"] == [4.0, 1.5, 0.0]
    assert limiter["dictionary_path"] == str(option_path)
    expected_hash = hashlib.sha256(option_path.read_bytes()).hexdigest()
    assert limiter["dictionary_sha256"] == expected_hash
    input_hashes = summary["source_code_and_input_sha256"]["inputs"]
    assert input_hashes["constant/fvOptions"] == expected_hash
    assert summary["prepared_input_hash_verification"]["verified_file_count"] == 8
    assert summary["integration"]["injected_kg"] == pytest.approx(800.0)
    assert summary["integration"]["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)


def test_nut_limiter_exposes_parameterized_valid_identifiers(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "renamed-nut-limiter-run")
    option_text = VALID_NUT_LIMITER.replace("interfaceNutCap", "diagnosticNutCap").replace(
        "nearSourceBox", "selectedAirRegion"
    )
    _install_fv_options(case, option_text)

    summary = audit_run(case, tmp_path / "renamed-nut-limiter-out")

    limiter = summary["supported_configuration"]["turbulent_viscosity_limiter"]
    assert limiter["option_name"] == "diagnosticNutCap"
    assert limiter["selection_name"] == "selectedAirRegion"
    assert summary["integration"]["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        (
            "alpha-source-option",
            VALID_NUT_LIMITER + "\nalphaMassSource { type semiImplicitSource; active yes; }\n",
            "exactly one active limitTurbulenceViscosity",
        ),
        (
            "extra-option",
            VALID_NUT_LIMITER + "\nextraCorrection { type somethingElse; active yes; }\n",
            "exactly one active limitTurbulenceViscosity",
        ),
        (
            "model-mixture-option",
            VALID_NUT_LIMITER
            + "\nmixtureCorrection { type multiphaseStabilizedTurbulence; active yes; }\n",
            "exactly one active limitTurbulenceViscosity",
        ),
        (
            "include-directive",
            VALID_NUT_LIMITER + '\n#include "extraOptions"\n',
            "directives, macros, and code are unsupported",
        ),
        (
            "missing-foamfile-header",
            VALID_NUT_LIMITER[VALID_NUT_LIMITER.index("interfaceNutCap") :],
            "requires a standard FoamFile header",
        ),
        (
            "unsupported-foamfile-version",
            VALID_NUT_LIMITER.replace("version 2.0;", "version 1.0;"),
            "FoamFile version must be 2.0",
        ),
        (
            "macro-substitution",
            VALID_NUT_LIMITER.replace("c 1000;", "c $cap;"),
            "directives, macros, and code are unsupported",
        ),
        (
            "embedded-code",
            VALID_NUT_LIMITER + "\n#{ option{}; #}\n",
            "directives, macros, and code are unsupported",
        ),
        (
            "wrong-corrected-field",
            VALID_NUT_LIMITER.replace("nut nut;", "nut k;"),
            "requires nut nut",
        ),
        (
            "dynamic-selection",
            VALID_NUT_LIMITER.replace("updateSelection false;", "updateSelection true;"),
            "requires updateSelection false",
        ),
        (
            "top-level-coefficients",
            VALID_NUT_LIMITER.replace(
                "    limitTurbulenceViscosityCoeffs\n    {\n",
                "    selectionMode geometric;\n    selection {}\n    nut nut;\n    c 1000;\n    limitTurbulenceViscosityCoeffs\n    {\n",
            ),
            "unsupported limitTurbulenceViscosity option schema",
        ),
        (
            "duplicate-coefficient",
            VALID_NUT_LIMITER.replace("        c 1000;", "        c 1000;\n        c 2000;"),
            "duplicate fvOptions dictionary token 'c'",
        ),
        (
            "missing-semicolon",
            VALID_NUT_LIMITER.replace("        c 1000;", "        c 1000"),
            "malformed value for 'c'",
        ),
        (
            "extra-coefficient-field",
            VALID_NUT_LIMITER.replace(
                "        c 1000;", "        c 1000;\n        alpha.water alpha.water;"
            ),
            "unsupported limitTurbulenceViscosityCoeffs schema",
        ),
    ],
)
def test_limit_turbulence_viscosity_allowlist_fails_closed(
    tmp_path: Path, name: str, text: str, message: str
) -> None:
    case = _make_run(tmp_path / name)
    _install_fv_options(case, text)
    output = tmp_path / f"{name}-out"

    with pytest.raises(AuditError, match=message):
        audit_run(case, output)
    assert not output.exists()


@pytest.mark.parametrize("coefficient", ["0", "-1", "NaN", "inf"])
def test_limit_turbulence_viscosity_requires_finite_positive_cap(
    tmp_path: Path, coefficient: str
) -> None:
    case = _make_run(tmp_path / f"nut-cap-{coefficient}")
    _install_fv_options(case, VALID_NUT_LIMITER.replace("c 1000;", f"c {coefficient};"))

    with pytest.raises(AuditError, match="coefficient c must be finite and positive"):
        audit_run(case, tmp_path / f"nut-cap-{coefficient}-out")


def test_fvmodels_remain_unsupported_with_allowlisted_nut_limiter(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "fvmodels-run")
    _install_fv_options(case, VALID_NUT_LIMITER)
    (case / "constant/fvModels").write_text(
        "alphaSource { type semiImplicitSource; active yes; }\n", encoding="utf-8"
    )
    output = tmp_path / "fvmodels-out"

    with pytest.raises(AuditError, match="fvModels are unsupported"):
        audit_run(case, output)
    assert not output.exists()


def test_fvoptions_outside_constant_path_is_rejected(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "wrong-fvoptions-path-run")
    _install_fv_options(case, VALID_NUT_LIMITER)
    (case / "system/fvOptions").write_text(VALID_NUT_LIMITER, encoding="utf-8")
    output = tmp_path / "wrong-fvoptions-path-out"

    with pytest.raises(AuditError, match="only supported at constant/fvOptions"):
        audit_run(case, output)
    assert not output.exists()


def test_fvoptions_symlink_is_rejected(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "symlink-fvoptions-run")
    target = case / "constant/fvOptions.real"
    target.write_text(VALID_NUT_LIMITER, encoding="utf-8")
    (case / "constant/fvOptions").symlink_to(target.name)

    with pytest.raises(AuditError, match="fvOptions must not be a symbolic link"):
        audit_run(case, tmp_path / "symlink-fvoptions-out")


def test_first_native_delta_t_is_not_replaced_by_rounded_time_difference(tmp_path: Path) -> None:
    first_dt = 0.00012004802
    case = _make_run(
        tmp_path / "rounding-run",
        delta_ts=[first_dt],
        source_fluxes=[-1.0],
        configured_end_s=0.01,
    )
    output = tmp_path / "rounding-out"

    summary = audit_run(case, output, end_time_s=0.000120)

    rounding = summary["integration"]["rounding_diagnostic"]
    assert rounding["first_native_deltaT_s"] == pytest.approx(first_dt)
    assert rounding["first_printed_interval_s"] == pytest.approx(0.000120)
    assert rounding["first_native_minus_printed_interval_s"] == pytest.approx(4.802e-8)
    assert summary["integration"]["injected_kg"] == pytest.approx(first_dt * 1000.0)
    row = _read_csv(output / "ledger.csv")[0]
    assert float(row["native_deltaT_s"]) == pytest.approx(first_dt)


def test_interior_missing_function_row_is_rejected(tmp_path: Path) -> None:
    case = _make_run(
        tmp_path / "gap-run",
        delta_ts=[0.1, 0.1, 0.1],
        source_fluxes=[-1.0, -2.0, -3.0],
        missing_row=("xOutlet", 1),
    )

    with pytest.raises(AuditError, match="interior time gap"):
        audit_run(case, tmp_path / "gap-out")
    assert not (tmp_path / "gap-out").exists()


def test_short_stream_does_not_hide_mismatch_in_continuing_streams(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "mismatched-tail-run")
    water_file = case / "postProcessing/waterVolume/0.000000/volFieldValue.dat"
    water_rows = water_file.read_text(encoding="utf-8").splitlines()
    water_file.write_text("\n".join(water_rows[:-1]) + "\n", encoding="utf-8")

    outlet_file = case / "postProcessing/xOutletFlux/0.000000/surfaceFieldValue.dat"
    outlet_text = outlet_file.read_text(encoding="utf-8").replace(
        "0.300000\t0\t0", "0.299000\t0\t0"
    )
    outlet_file.write_text(outlet_text, encoding="utf-8")

    with pytest.raises(AuditError, match="mismatched row in continuing"):
        audit_run(case, tmp_path / "mismatched-tail-out")


def test_run_manifest_image_digest_must_not_contradict_case_inputs(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "image-run")
    manifest = case.parent / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"solver_image": "opencfd/openfoam-default:2512", "solver_image_id": "sha256:wrong"}
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuditError, match="contradicts the pinned solver image"):
        audit_run(case, tmp_path / "image-out")


def test_native_backend_rejects_pinned_image_digest_without_source_evidence(
    tmp_path: Path,
) -> None:
    case = _make_run(tmp_path / "native-with-fake-image-run")
    inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    case_inputs.update(
        execution_backend="slurm-native",
        solver_version="v2512",
        reference_image_digest=PINNED_IMAGE,
        openfoam_image_digest=PINNED_IMAGE,
    )
    inputs_path.write_text(json.dumps(case_inputs), encoding="utf-8")

    with pytest.raises(AuditError, match="requires --verified-source-evidence"):
        audit_run(case, tmp_path / "native-fake-image-out")


def test_native_backend_accepts_matching_installed_source_and_run_manifest(
    tmp_path: Path,
) -> None:
    case = _make_run(tmp_path / "native-matching-run")
    evidence = _write_native_source_evidence(tmp_path / "native-source-evidence.json")
    _configure_native_run(case, evidence)

    summary = audit_run(
        case,
        tmp_path / "native-matching-ledger",
        verified_source_evidence=evidence,
    )

    verification = summary["solver_image_verification"]
    assert verification["verification_mode"] == "native-module-source-correspondence"
    assert verification["native_solver"]["executable_sha256"] == "a" * 64
    assert (
        "not proof of reproducible or bit-for-bit binary construction"
        in verification["interpretation"]
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("executable_sha256", "c" * 64, "differs from installed-source evidence"),
        ("version", "v2506", "version must be v2512"),
        ("architecture", "aarch64", "differs from installed-source evidence"),
    ],
)
def test_native_backend_rejects_run_manifest_identity_mismatch(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    case = _make_run(tmp_path / field.replace("_", "-"))
    evidence = _write_native_source_evidence(tmp_path / "native-source-evidence.json")
    manifest_path = _configure_native_run(case, evidence)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_solver"][field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AuditError, match=message):
        audit_run(
            case,
            tmp_path / "native-mismatch-ledger",
            verified_source_evidence=evidence,
        )


def test_native_backend_requires_runtime_identity_in_run_manifest(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "native-no-runtime-run")
    evidence = _write_native_source_evidence(tmp_path / "native-source-evidence.json")
    manifest_path = _configure_native_run(case, evidence)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("native_solver")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AuditError, match="must contain a native_solver object"):
        audit_run(
            case,
            tmp_path / "native-no-runtime-ledger",
            verified_source_evidence=evidence,
        )


def test_native_backend_checks_reference_source_hashes_and_evidence_binding(
    tmp_path: Path,
) -> None:
    case = _make_run(tmp_path / "native-source-hash-run")
    evidence = _write_native_source_evidence(tmp_path / "native-source-evidence.json")
    manifest_path = _configure_native_run(case, evidence)

    damaged_evidence = json.loads(evidence.read_text(encoding="utf-8"))
    damaged_evidence["solver_source"]["isoAdvection.H"]["sha256"] = "0" * 64
    evidence.write_text(json.dumps(damaged_evidence), encoding="utf-8")
    with pytest.raises(AuditError, match="installed source hash mismatch for isoAdvection.H"):
        audit_run(
            case,
            tmp_path / "native-source-hash-ledger",
            verified_source_evidence=evidence,
        )

    evidence = _write_native_source_evidence(tmp_path / "native-source-evidence-2.json")
    manifest_path = _configure_native_run(case, evidence)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_source_evidence_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AuditError, match="must hash the supplied source evidence"):
        audit_run(
            case,
            tmp_path / "native-source-evidence-binding-ledger",
            verified_source_evidence=evidence,
        )


def test_flux_function_object_must_be_bound_to_its_named_patch(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "wrong-function-patch-run")
    control = case / "system/controlDict"
    control.write_text(
        control.read_text(encoding="utf-8").replace(
            "xOutletFlux { type surfaceFieldValue; regionType patch; name xOutlet;",
            "xOutletFlux { type surfaceFieldValue; regionType patch; name yMin;",
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuditError, match="xOutletFlux must bind to patch xOutlet"):
        audit_run(case, tmp_path / "wrong-function-patch-out")


def test_coded_fixed_value_braces_and_comments_do_not_hide_u_patch(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "coded-u-run")
    velocity_path = case / "0/U"
    velocity_text = velocity_path.read_text(encoding="utf-8").replace(
        f"{SOURCE} {{ type uniformFixedValue; }}",
        f"""{SOURCE}
    {{
        type codedFixedValue;
        name representativeProfile;
        value uniform (0 0 0);
        code
        #{{
            // The brace in this comment is not a dictionary boundary: {{
            /* This comment also has a closing brace: }} */
            if (true)
            {{
                const vector scoped{{0, 0, 0}};
                const char* brace = "}}";
            }}
        #}};
    }}""",
    )
    velocity_path.write_text(velocity_text, encoding="utf-8")
    _refresh_prepared_hash(case, "0/U")

    output = tmp_path / "coded-u-out"
    summary = audit_run(case, output)

    assert (
        summary["supported_configuration"]["boundary_inventory"]["velocity_boundary_types"][SOURCE]
        == "codedFixedValue"
    )
    # alphaPhi_ remains the sole source of injection accounting; velocity
    # boundary implementation does not alter the native ledger calculation.
    assert summary["integration"]["injected_kg"] == pytest.approx(800.0)
    assert summary["integration"]["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)


def test_missing_u_patch_dictionary_is_rejected(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "missing-u-patch-run")
    velocity_path = case / "0/U"
    velocity_text = velocity_path.read_text(encoding="utf-8").replace(
        f"{SOURCE} {{ type uniformFixedValue; }}\n", ""
    )
    velocity_path.write_text(velocity_text, encoding="utf-8")

    output = tmp_path / "missing-u-patch-out"
    with pytest.raises(AuditError, match=r"U boundary conditions are missing.*dash8Opening"):
        audit_run(case, output)
    assert not output.exists()


def test_unterminated_coded_fixed_value_block_is_rejected(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "unterminated-coded-u-run")
    velocity_path = case / "0/U"
    velocity_text = velocity_path.read_text(encoding="utf-8").replace(
        f"{SOURCE} {{ type uniformFixedValue; }}",
        f"{SOURCE} {{ type codedFixedValue; code #{{ if (true) {{ operator==(value); }} }}",
    )
    velocity_path.write_text(velocity_text, encoding="utf-8")

    output = tmp_path / "unterminated-coded-u-out"
    with pytest.raises(AuditError, match="unterminated OpenFOAM code block"):
        audit_run(case, output)
    assert not output.exists()


def test_native_time_delta_mismatch_is_rejected(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "mismatch-run")
    log = case / "log.interIsoFoam"
    text = log.read_text(encoding="utf-8").replace("deltaT = 0.2", "deltaT = 0.1")
    log.write_text(text, encoding="utf-8")

    with pytest.raises(AuditError, match="native deltaT cumulative time differs"):
        audit_run(case, tmp_path / "mismatch-out")


def test_requested_prefix_cannot_exceed_configured_end_by_fixed_epsilon(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "end-time-run")

    with pytest.raises(AuditError, match="requested end time 0.3000000001 s exceeds"):
        audit_run(case, tmp_path / "end-time-out", end_time_s=0.3000000001)


def test_accumulated_delta_t_print_precision_is_included_in_time_bound(tmp_path: Path) -> None:
    case = _make_run(
        tmp_path / "rounded-dt-run",
        delta_ts=[0.704871, 0.70487150049],
        source_fluxes=[0.0, 0.0],
        configured_end_s=2.0,
    )
    for path in case.glob("postProcessing/*/0.000000/*.dat"):
        lines = path.read_text(encoding="utf-8").splitlines()
        data_index = 0
        replaced = []
        for line in lines:
            if line.startswith("#") or not line.strip():
                replaced.append(line)
                continue
            tokens = line.split()
            tokens[0] = ("0.704871", "1.409742")[data_index]
            data_index += 1
            replaced.append("\t".join(tokens))
        path.write_text("\n".join(replaced) + "\n", encoding="utf-8")
    log_lines = [
        "deltaT = 0.704871",
        "Time = 0.704871",
        "deltaT = 0.70487150049",
        "Time = 1.409742",
    ]
    (case / "log.interIsoFoam").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    # The manifest freezes prepared inputs, not solver output files, so these
    # output timestamp changes do not alter prepared-case provenance.

    output = tmp_path / "rounded-dt-out"
    summary = audit_run(case, output)
    diagnostic = summary["integration"]["rounding_diagnostic"]
    assert diagnostic["cumulative_deltaT_print_rounding_bound_s"] == pytest.approx(5.00005e-7)
    assert diagnostic["max_abs_reconstructed_native_time_vs_printed_time_s"] == pytest.approx(
        5.0049e-7
    )
    assert diagnostic["max_allowed_native_vs_printed_time_difference_s"] == pytest.approx(
        1.000005e-6
    )
    assert summary["coverage"]["last_matched_printed_time_s"] == pytest.approx(1.409742)
    assert summary["coverage"]["last_matched_reconstructed_time_s"] == pytest.approx(1.40974250049)


def test_modified_prepared_solver_dictionary_is_rejected_by_manifest_hash(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "drift-run")
    inputs_path = case / "case-inputs.json"
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    inputs["annotation"] = "benign post-run edit"
    inputs_path.write_text(json.dumps(inputs), encoding="utf-8")

    with pytest.raises(AuditError, match="prepared-case input hash mismatch for case-inputs.json"):
        audit_run(case, tmp_path / "drift-out")


def test_unsupported_subcycles_and_moving_mesh_are_rejected(tmp_path: Path) -> None:
    subcycle_case = _make_run(tmp_path / "subcycle-run", n_alpha_subcycles=2)
    with pytest.raises(AuditError, match="nAlphaSubCycles=2"):
        audit_run(subcycle_case, tmp_path / "subcycle-out")

    moving_case = _make_run(tmp_path / "moving-run", dynamic_mesh="dynamicMotionSolverFvMesh")
    with pytest.raises(AuditError, match="moving or undeclared dynamic mesh"):
        audit_run(moving_case, tmp_path / "moving-out")

    permeable_case = _make_run(tmp_path / "permeable-run")
    velocity_path = permeable_case / "0/U"
    velocity_text = velocity_path.read_text(encoding="utf-8").replace(
        "plate { type slip; }", "plate { type pressureInletOutletVelocity; }"
    )
    velocity_path.write_text(velocity_text, encoding="utf-8")
    with pytest.raises(AuditError, match="lacks verified impermeable U condition"):
        audit_run(permeable_case, tmp_path / "permeable-out")


def test_existing_output_directory_and_contents_are_preserved(tmp_path: Path) -> None:
    case = _make_run(tmp_path / "preserve-run")
    output = tmp_path / "previous-ledger"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("existing report", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        audit_run(case, output)
    assert sentinel.read_text(encoding="utf-8") == "existing report"
