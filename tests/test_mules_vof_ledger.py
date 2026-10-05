from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_mules_vof_ledger as mules

SOURCE_RELATIVES = (
    "applications/solvers/multiphase/VoF/createAlphaFluxes.H",
    "applications/solvers/multiphase/VoF/alphaEqn.H",
    "applications/solvers/multiphase/VoF/alphaEqnSubCycle.H",
    "src/finiteVolume/cfdTools/general/include/alphaControls.H",
)
SOURCE_TEXT = {
    SOURCE_RELATIVES[0]: 'IOobject::groupName("alphaPhi0", alpha1.group())\nIOobject::AUTO_WRITE\n',
    SOURCE_RELATIVES[1]: "MULES::explicitSolve\nrhoPhi = alphaPhi10\n",
    SOURCE_RELATIVES[
        2
    ]: "if (nAlphaSubCycles > 1)\nrhoPhiSum += (runTime.deltaT()/totalDeltaT)*rhoPhi\n",
    SOURCE_RELATIVES[3]: 'get<label>("nAlphaSubCycles")\n',
}


@pytest.fixture
def case_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def make_case(*, start_from: str = "startTime", solver: str = "interFoam") -> tuple[Path, Path]:
        case = tmp_path / "case"
        source = tmp_path / "source"
        for relative, text in SOURCE_TEXT.items():
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(
            mules,
            "SOURCE_FILES",
            {
                relative: hashlib.sha256(text.encode()).hexdigest()
                for relative, text in SOURCE_TEXT.items()
            },
        )

        for folder in ("system", "constant/polyMesh", "constant", "0"):
            (case / folder).mkdir(parents=True, exist_ok=True)
        (case / "case-inputs.json").write_text(
            json.dumps(
                {
                    "solver": solver,
                    "openfoam_image": mules.PINNED_IMAGE,
                    "horizon_s": 0.6,
                    "analytic_expected_mass_kg": 600.0,
                    "numerical_method_comparison": {
                        "method": "OpenCFD v2512 stock interFoam MULES with bounded interface compression",
                        "phase_volume_flux": {"field_name": "alphaPhi0.water"},
                        "source_evidence": {
                            "image": mules.PINNED_IMAGE,
                            "image_sha256": mules.PINNED_IMAGE_ID,
                        },
                        "alpha_controls": {"nAlphaSubCycles": 1},
                    },
                    "source_patches": ["dash8Opening"],
                    "open_patches": list(mules.OPEN_PATCHES),
                    "source_patch_areas_m2": {"dash8Opening": 1.0},
                    "boundary_conditions": {"source_flow_sign": "outward +z; prescribed -z"},
                    "source_histories": {"dash8": {"samples_used_m_s": [[0, 1], [0.6, 1]]}},
                    "fluid_properties": {"water": {"rho_kg_m3": 1000.0}},
                }
            ),
            encoding="utf-8",
        )
        fo_names = [
            "waterVolume",
            *(f"{patch}Flux" for patch in ("dash8Opening", *mules.OPEN_PATCHES)),
        ]
        objects = []
        for name in fo_names:
            volume = name == "waterVolume"
            fields = "alpha.water" if volume else "phi alphaPhi0.water"
            binding = "" if volume else f"regionType patch; name {name.removesuffix('Flux')};"
            operation = "volIntegrate" if volume else "sum"
            fo_type = "volFieldValue" if volume else "surfaceFieldValue"
            objects.append(
                f"""{name} {{
                    type {fo_type}; operation {operation}; {binding}
                    fields ({fields}); executeControl timeStep; executeInterval 1;
                    writeControl timeStep; writeInterval 1;
                }}"""
            )
        (case / "system/controlDict").write_text(
            "\n".join(
                [
                    "application interFoam;",
                    f"startFrom {start_from};",
                    "startTime 0;",
                    "endTime 0.6;",
                    "timeFormat fixed;",
                    "timePrecision 6;",
                    "functions {",
                    *objects,
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (case / "system/fvSchemes").write_text("ddtSchemes { default Euler; }\n", encoding="utf-8")
        (case / "system/fvSolution").write_text(
            '"alpha.water.*" { nAlphaSubCycles 1; } PIMPLE { nOuterCorrectors 1; }\n',
            encoding="utf-8",
        )
        mesh_patches = [*mules.OPEN_PATCHES, "dash8Opening"]
        (case / "constant/polyMesh/boundary").write_text(
            "\n".join(f"{name} {{ type patch; }}" for name in mesh_patches)
            + "\nplate { type wall; }\n",
            encoding="utf-8",
        )
        (case / "0/alpha.water").write_text("internalField uniform 0;\n", encoding="utf-8")
        (case / "0/U").write_text(
            "boundaryField {\n"
            + "\n".join(f"{name} {{ type slip; }}" for name in [*mesh_patches, "plate"])
            + "\n}\n",
            encoding="utf-8",
        )
        (case / "constant/transportProperties").write_text(
            "water { rho 1000; }\n", encoding="utf-8"
        )
        return case, source

    return make_case


def _write_run(
    case: Path,
    times: list[str],
    delta_ts: list[str],
    volumes: list[float],
    *,
    source_flux: list[float] | None = None,
    x_escape: list[float] | None = None,
    log_segments: list[tuple[str, list[str], list[str]]] | None = None,
) -> None:
    source_flux = source_flux or [-1.0] * len(times)
    x_escape = x_escape or [0.0] * len(times)
    patch_fluxes = {patch: [0.0] * len(times) for patch in mules.OPEN_PATCHES}
    patch_fluxes["xOutlet"] = x_escape
    series: dict[str, tuple[list[float], list[float] | None]] = {
        "waterVolume": (volumes, None),
        "dash8Opening": (source_flux, None),
        **{patch: (values, None) for patch, values in patch_fluxes.items()},
    }
    for name, (first, _) in series.items():
        object_name = "waterVolume" if name == "waterVolume" else f"{name}Flux"
        is_volume = name == "waterVolume"
        root = case / "postProcessing" / object_name / "0"
        root.mkdir(parents=True, exist_ok=True)
        header = (
            "# Time volIntegrate(alpha.water)\n"
            if is_volume
            else "# Time sum(phi) sum(alphaPhi0.water)\n"
        )
        rows = []
        for i, time in enumerate(times):
            values = [first[i]] if is_volume else [0.0, first[i]]
            rows.append(time + " " + " ".join(map(str, values)))
        filename = "volFieldValue.dat" if is_volume else "surfaceFieldValue.dat"
        (root / filename).write_text(header + "\n".join(rows) + "\n", encoding="utf-8")

    if log_segments is None:
        log_segments = [("0", times, delta_ts)]
    log_lines = []
    for initial, segment_times, segment_dt in log_segments:
        log_lines.append(f"Time = {initial}")
        log_lines.extend(
            f"deltaT = {dt}\nTime = {time}"
            for time, dt in zip(segment_times, segment_dt, strict=True)
        )
    (case / "log.interFoam").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def test_variable_delta_t_signed_ledger_separates_prescribed_and_transported(
    case_factory, tmp_path
):
    case, source = case_factory()
    _write_run(
        case,
        ["0.1", "0.3"],
        ["0.1", "0.2"],
        [0.15, 0.35],
        source_flux=[-2.0, -1.0],
        x_escape=[0.5, 0.0],
    )

    result = mules.audit_run(case, tmp_path / "ledger", source_dir=source)

    with Path(result["ledger_csv"]).open(encoding="utf-8", newline="") as stream:
        ledger = list(csv.DictReader(stream))
    assert [float(row["deltaT_s_from_solver_log"]) for row in ledger] == [0.1, 0.2]
    assert result["integration"]["transported_source_mass_from_alphaPhi0_kg"] == pytest.approx(
        400.0
    )
    assert result["integration"][
        "prescribed_history_mass_over_observed_intervals_kg"
    ] == pytest.approx(300.0)
    assert result["integration"]["signed_net_open_boundary_escape_kg"] == pytest.approx(50.0)
    assert result["integration"]["final_native_inventory_kg"] == pytest.approx(350.0)
    assert result["integration"]["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)


def test_print_precision_endpoint_slop_is_clipped_and_reported(case_factory, tmp_path):
    case, source = case_factory()
    _write_run(
        case,
        ["0.1", "0.3", "0.6"],
        ["0.1", "0.2", "0.3000002"],
        [0.1, 0.3, 0.6000002],
        source_flux=[-1.0, -1.0, -1.0],
    )

    result = mules.audit_run(case, tmp_path / "roundoff", source_dir=source)

    assert result["integration"]["transported_source_mass_from_alphaPhi0_kg"] == pytest.approx(
        600.0002
    )
    assert result["integration"][
        "prescribed_history_mass_over_observed_intervals_kg"
    ] == pytest.approx(600.0)
    assert result["integration"]["prescribed_history_endpoint_clipped_duration_s"] == pytest.approx(
        2e-7
    )
    with pytest.raises(mules.MulesAuditError, match="does not cover interval"):
        mules._integrate_history_with_print_tolerance(
            [(0.0, 1.0), (0.6, 1.0)], 0.5, 0.601, tolerance_s=5e-7
        )


def test_repeated_restart_series_rejected_unless_explicit_complete_segment(case_factory, tmp_path):
    case, source = case_factory()
    times = ["0.1", "0.2", "0.1", "0.2", "0.3"]
    _write_run(
        case,
        times,
        ["0.1"] * 5,
        [0.1, 0.2, 0.1, 0.2, 0.3],
        source_flux=[-1.0] * 5,
        log_segments=[("0", times[:2], ["0.1"] * 2), ("0.1", times[2:], ["0.1"] * 3)],
    )
    with pytest.raises(mules.MulesAuditError, match="restarted or repeated"):
        mules.audit_run(case, tmp_path / "full", source_dir=source)

    control = case / "system/controlDict"
    control.write_text(control.read_text().replace("startFrom startTime", "startFrom latestTime"))
    result = mules.audit_run(
        case,
        tmp_path / "selected",
        source_dir=source,
        segment_start_s=0.2,
        segment_end_s=0.3,
        segment_initial_water_volume_m3=0.2,
    )
    assert result["coverage"]["segment_explicitly_selected"] is True
    assert result["coverage"]["complete_selected_segment"] is True
    assert result["integration"]["closure_residual_kg"] == pytest.approx(0.0, abs=1e-10)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("solver", "only solver=interFoam"),
        ("subcycles", "nAlphaSubCycles 1"),
        ("flux", "must report fields"),
        ("outer", "nOuterCorrectors 1"),
        ("ddt", "default Euler"),
    ],
)
def test_configuration_rejects_wrong_solver_subcycles_and_phase_flux(
    case_factory, mutation, message
):
    case, source = case_factory()
    if mutation == "solver":
        path = case / "case-inputs.json"
        data = json.loads(path.read_text())
        data["solver"] = "interIsoFoam"
        path.write_text(json.dumps(data))
    elif mutation == "subcycles":
        path = case / "system/fvSolution"
        path.write_text(path.read_text().replace("nAlphaSubCycles 1", "nAlphaSubCycles 2"))
    elif mutation == "outer":
        path = case / "system/fvSolution"
        path.write_text(path.read_text().replace("nOuterCorrectors 1", "nOuterCorrectors 2"))
    elif mutation == "ddt":
        path = case / "system/fvSchemes"
        path.write_text(path.read_text().replace("Euler", "backward"))
    else:
        path = case / "system/controlDict"
        path.write_text(path.read_text().replace("alphaPhi0.water", "alphaPhi_"))

    with pytest.raises(mules.MulesAuditError, match=message):
        mules.verify_configuration(case, source)


def test_missing_diagnostic_table_is_reported_without_partial_output(case_factory, tmp_path):
    case, source = case_factory()
    _write_run(case, ["0.1"], ["0.1"], [0.1])
    (case / "postProcessing/yMinFlux/0/surfaceFieldValue.dat").unlink()

    with pytest.raises(mules.MulesAuditError, match="missing surfaceFieldValue.dat"):
        mules.audit_run(case, tmp_path / "missing", source_dir=source)
    assert not (tmp_path / "missing").exists()


def test_nonfinite_or_unmatched_native_diagnostics_are_rejected(case_factory, tmp_path):
    case, source = case_factory()
    _write_run(case, ["0.1"], ["0.1"], [0.1], source_flux=[float("nan")])
    with pytest.raises(mules.MulesAuditError, match="non-finite"):
        mules.audit_run(case, tmp_path / "nonfinite", source_dir=source)

    _write_run(case, ["0.1"], ["0.1"], [0.1])
    flux_path = case / "postProcessing/xOutletFlux/0/surfaceFieldValue.dat"
    flux_path.write_text("# Time sum(phi) sum(alphaPhi0.water)\n0.2 0 0\n", encoding="utf-8")
    with pytest.raises(mules.MulesAuditError, match="unmatched/missing time rows"):
        mules.audit_run(case, tmp_path / "unmatched", source_dir=source)
