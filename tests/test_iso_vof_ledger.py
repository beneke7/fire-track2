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

from scripts.audit_iso_vof_ledger import PINNED_IMAGE, AuditError, audit_run  # noqa: E402

SOURCE = "dash8Opening"
OPEN = ("airInlet", "xOutlet", "yMin", "yMax", "zMin")
ALL_PATCHES = (SOURCE, *OPEN)
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
    delta_ts: list[float] | None = None,
    source_fluxes: list[float] | None = None,
    open_fluxes: dict[str, list[float]] | None = None,
    configured_end_s: float | None = None,
    n_alpha_subcycles: int = 1,
    dynamic_mesh: str | None = None,
    missing_row: tuple[str, int] | None = None,
) -> Path:
    dt = delta_ts or [0.1, 0.2]
    source = source_fluxes or [-2.0, -3.0]
    opens = open_fluxes or {patch: [0.0] * len(dt) for patch in OPEN}
    assert len(dt) == len(source)
    assert all(len(values) == len(dt) for values in opens.values())
    end_s = configured_end_s or sum(dt)
    times: list[float] = []
    clock = 0.0
    volumes: list[float] = []
    volume = 0.0
    for index, step_dt in enumerate(dt):
        clock += step_dt
        times.append(clock)
        volume -= (source[index] + sum(opens[patch][index] for patch in OPEN)) * step_dt
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
        "source_patches": [SOURCE],
        "open_patches": list(OPEN),
    }
    (case / "case-inputs.json").write_text(json.dumps(case_inputs), encoding="utf-8")
    flux_function_objects = []
    for patch in ALL_PATCHES:
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
    boundary_entries = [f"{SOURCE} {{ type patch; }}"]
    boundary_entries.extend(f"{patch} {{ type patch; }}" for patch in OPEN)
    boundary_entries.append("plate { type wall; }")
    (mesh / "boundary").write_text(
        f"{len(boundary_entries)}\n(\n" + "\n".join(boundary_entries) + "\n)\n",
        encoding="utf-8",
    )
    if dynamic_mesh is not None:
        (constant / "dynamicMeshDict").write_text(
            f"dynamicFvMesh {dynamic_mesh};\n", encoding="utf-8"
        )
    (zero / "alpha.water").write_text("internalField uniform 0;\n", encoding="utf-8")
    velocity_conditions = [f"{SOURCE} {{ type uniformFixedValue; }}"]
    velocity_conditions.extend(f"{patch} {{ type pressureInletOutletVelocity; }}" for patch in OPEN)
    velocity_conditions.append("plate { type slip; }")
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

    for patch in ALL_PATCHES:
        q_values = source if patch == SOURCE else opens[patch]
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


def _refresh_prepared_hash(case: Path, relative: str) -> None:
    manifest_path = case.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prepared_case_sha256"][relative] = hashlib.sha256(
        (case / relative).read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


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
