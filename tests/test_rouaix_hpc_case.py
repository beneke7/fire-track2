from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from cases.e1_rouaix_hpc import collect_native_provenance as native_provenance
from cases.e1_rouaix_hpc import prepare_case as hpc_case

REAL_QUALIFIED_MESH_BUNDLE = (
    Path(__file__).resolve().parents[1]
    / "results/runs/rouaix-native-mesh-qa-20261025/qualified-mesh-input"
)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    mesh = tmp_path / "mesh" / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    for name in hpc_case.POLYMESH_FILES:
        (mesh / name).write_text("mesh fixture\n", encoding="utf-8")
    (mesh / "boundary").write_text(
        """7
(
nozzle
{
    type patch;
    nFaces 4;
    startFace 100;
}
gasInlet
{
    type patch;
    nFaces 8;
    startFace 104;
}
downstreamOutlet
{
    type patch;
    nFaces 8;
    startFace 112;
}
bottomOutlet
{
    type patch;
    nFaces 8;
    startFace 120;
}
aircraftWall
{
    type wall;
    nFaces 8;
    startFace 128;
}
spanwiseMinus
{
    type patch;
    nFaces 8;
    startFace 136;
}
spanwisePlus
{
    type patch;
    nFaces 8;
    startFace 144;
}
)
""",
        encoding="utf-8",
    )
    hashes = {name: hpc_case.sha256(mesh / name) for name in hpc_case.POLYMESH_FILES}
    log = tmp_path / "native-check.log"
    log.write_text("Mesh stats\n    cells: 17\nMesh OK.\n", encoding="utf-8")
    manifest = tmp_path / "mesh-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cell_count": 17,
                "mesh_files_sha256": hashes,
                "native_qa": {
                    "version": "v2512",
                    "status": "qualified",
                    "log_path": log.name,
                    "log_sha256": hpc_case.sha256(log),
                },
            }
        ),
        encoding="utf-8",
    )
    area = 0.12546554934822965
    audit = tmp_path / "nozzle-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "patch": "nozzle",
                "face_count": 4,
                "area_m2": area,
                "area_vector_m2": [0.0, area, 0.0],
                "mesh_files_sha256": hashes,
            }
        ),
        encoding="utf-8",
    )
    return mesh, manifest, audit


def _set_expr_fixture(tmp_path: Path) -> Path:
    utility = tmp_path / "setExprFields-fixture"
    utility.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import re

field = Path('0/p_rgh')
text = field.read_text()
field.write_text(re.sub(r'internalField\\s+uniform\\s+0\\s*;',
                        'internalField nonuniform List<scalar> 17 (\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n0\\n);', text))
print('Set all 17 values')
""",
        encoding="utf-8",
    )
    utility.chmod(0o755)
    return utility


def _concave_exception_inputs(tmp_path: Path, *, cell_count: int = 228_016):
    mesh, manifest_path, nozzle_audit = _inputs(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    count = hpc_case.CONCAVE_EXCEPTION_COUNT
    ids = list(range(0, count * 2, 2))
    assert ids[-1] < cell_count
    ids_bytes = ("".join(f"{identifier}\n" for identifier in ids)).encode("utf-8")

    def cell_set_bytes(labels: list[int], *, arch: str | None) -> bytes:
        arch_entry = f'    arch        "{arch}";\n' if arch else ""
        header = (
            "FoamFile\n{\n    format      binary;\n"
            f"{arch_entry}    class       cellSet;\n"
            '    location    "constant/polyMesh/sets";\n'
            "    object      concaveCells;\n}\n"
            "// OpenFOAM cellSet fixture\n"
            f"{len(labels)}\n(\n"
        )
        return (header + "".join(f"{identifier}\n" for identifier in labels) + ")\n").encode()

    native_set = tmp_path / "qualification/native-concaveCells"
    reference_set = tmp_path / "qualification/reference-concaveCells"
    native_set.parent.mkdir(parents=True)
    native_set.write_bytes(cell_set_bytes(ids, arch="LSB;label=32;scalar=64"))
    reference_set.write_bytes(cell_set_bytes(ids, arch=None))
    native_ids = native_set.parent / "native-concave-ids.txt"
    reference_ids = native_set.parent / "reference-concave-ids.txt"
    native_ids.write_bytes(ids_bytes)
    reference_ids.write_bytes(ids_bytes)
    log = tmp_path / "native-check.log"
    log.write_text(
        f"Mesh stats\n    cells: {cell_count}\n"
        f" ***Concave cells (using face planes) found, number of cells: {count}\n"
        "Failed 1 mesh checks.\nEnd\n",
        encoding="utf-8",
    )
    manifest["cell_count"] = cell_count
    manifest["native_qa"].update(log_sha256=hpc_case.sha256(log))

    mesh_hashes = {name: hpc_case.sha256(mesh / name) for name in hpc_case.POLYMESH_FILES}
    audit = {
        "provenance": {
            "input_sha256_verified": {
                **{name: mesh_hashes[name] for name in ("points", "faces", "owner", "neighbour")},
                "sets/concaveCells": hpc_case.sha256(reference_set),
            },
            "native_concave_set_count": count,
        },
        "independent_vertex_plane_screen": {
            "audited_cell_count": count,
            "native_flags_reproduced_by_recomputed_area_normal_face_centres": count,
            "native_flags_not_reproduced": 0,
            "cells_with_external_vertex_excursion_above_numeric_bound": 0,
            "cells_with_positive_cosine_witness_above_roundoff_band": 0,
            "max_positive_external_vertex_plane_excursion_m": 6.223858637768553e-15,
            "max_face_warp_m": 2.664535034107249e-15,
            "numeric_error_bound_m": 1e-11,
        },
    }
    audit_path = native_set.parent / "independent-audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    review = native_set.parent / "review.md"
    review.write_text("Exploratory exception evidence only.\n", encoding="utf-8")
    audit_tool = native_set.parent / "audit_binary_mesh.py"
    audit_tool.write_text("# verified tool fixture\n", encoding="utf-8")
    audit_tool_helper = native_set.parent / "audit_concavity.py"
    audit_tool_helper.write_text("# verified helper fixture\n", encoding="utf-8")
    receipt_path = native_set.parent / "native-qualification-exception.json"

    def artifact(path: Path, *, count_value: int | None = None) -> dict[str, object]:
        record: dict[str, object] = {
            "path": path.name,
            "sha256": hpc_case.sha256(path),
        }
        if count_value is not None:
            record["count"] = count_value
        return record

    receipt = {
        "schema_version": 1,
        "status": hpc_case.CONCAVE_EXCEPTION_STATUS,
        "mesh_files_sha256": mesh_hashes,
        "native_log_sha256": hpc_case.sha256(log),
        "native_failure": {"category": "concaveCells", "count": count, "failed_check_count": 1},
        "native_ids": artifact(native_ids, count_value=count),
        "reference_ids": artifact(reference_ids, count_value=count),
        "native_set": artifact(native_set),
        "reference_set": artifact(reference_set),
        "independent_audit": artifact(audit_path),
        "review": artifact(review),
        "audit_tool": artifact(audit_tool),
        "audit_tool_helper": artifact(audit_tool_helper),
        "decision_owner": "primary agent /root",
        "decision_date": "2026-10-25",
        "scope": "Exploratory cast-only resource/timestep pilot only. No E1.",
        "reason": "Raw Failed1 and no MeshOK are preserved.",
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest["native_qa"]["qualification_exception"] = {
        "path": "qualification/native-qualification-exception.json",
        "sha256": hpc_case.sha256(receipt_path),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return mesh, manifest_path, nozzle_audit, log, receipt_path, native_ids


@pytest.mark.parametrize(("delta_t_s", "step_count"), [(0.001, 50), (0.0005, 100)])
def test_preparation_preserves_case1_inputs_and_builds_fixed_step_case(
    tmp_path: Path, delta_t_s: float, step_count: int
) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    output = tmp_path / "prepared"
    utility = _set_expr_fixture(tmp_path)

    hpc_case.prepare_case(
        mesh,
        manifest,
        audit,
        output,
        ranks=64,
        delta_t_s=delta_t_s,
        set_expr_fields=str(utility),
    )

    inputs = json.loads((output / "case-inputs.json").read_text(encoding="utf-8"))
    assert inputs["execution_backend"] == "slurm-native"
    assert inputs["solver_version"] == "v2512"
    assert inputs["reference_image_digest"].startswith("sha256:")
    assert "openfoam_image_digest" not in inputs
    assert "openfoam_image" not in inputs
    assert inputs["mesh_cells_expected"] == 17
    assert inputs["ranks"] == 64 and inputs["node_count"] == 1
    assert inputs["horizon_s"] == 0.05
    assert inputs["source_patches"] == ["nozzle"]
    assert inputs["open_patches"] == [
        "gasInlet",
        "downstreamOutlet",
        "bottomOutlet",
        "spanwiseMinus",
        "spanwisePlus",
    ]
    assert inputs["source_patch_face_counts"] == {"nozzle": 4}
    assert inputs["source_patch_area_vector_m2"]["nozzle"] == [0.0, 0.12546554934822965, 0.0]
    assert inputs["source_geometry_deviation_fraction"] == pytest.approx(-0.00157688, abs=1e-7)
    assert inputs["source_velocity_m_s"] == [0.0, -10.0, 0.0]
    assert inputs["source_flow_from_measured_area_m3_s"] == pytest.approx(1.2546554934822965)
    assert inputs["source_momentum_influx_from_measured_area_N"][1] < 0
    assert inputs["time_controls"]["startup_steps"] == step_count
    assert inputs["time_controls"]["nAlphaSubCycles"] == 1

    alpha = (output / "0/alpha.water").read_text(encoding="utf-8")
    velocity = (output / "0/U").read_text(encoding="utf-8")
    pressure = (output / "0/p_rgh").read_text(encoding="utf-8")
    assert "internalField   uniform 0;" in alpha
    assert "value           uniform (0 -10 0);" in velocity
    assert "List<scalar> 17" in pressure
    assert "1.18*9.81*pos().y()" in (output / "system/setExprFieldsDict").read_text()

    schemes = (output / "system/fvSchemes").read_text()
    solution = (output / "system/fvSolution").read_text()
    control = (output / "system/controlDict").read_text()
    assert "div(rhoPhi,U) Gauss limitedLinearV 1;" in schemes
    assert "grad(U) Gauss linear;" in schemes
    assert "grad(k) Gauss linear;" in schemes
    assert "grad(epsilon) Gauss linear;" in schemes
    assert "div(rhoPhi,k) Gauss upwind;" in schemes
    assert "solver PBiCGStab;" in solution and "preconditioner DILU;" in solution
    assert "nAlphaSubCycles 1;" in solution and "minIter 1;" in solution
    assert "endTime 0.05;" in control and f"deltaT {delta_t_s};" in control
    assert "adjustTimeStep no;" in control and "writeInterval 0.05;" in control
    assert "timeFormat fixed;" in control
    assert "fileHandler collated;" in control and "maxThreadFileBufferSize 0;" in control
    assert "writeNowSignal 10;" in control and "stopAtWriteNowSignal 12;" in control
    assert "aircraftWallFlux" in control
    assert inputs["resource_budget_provisional"] == {
        "memory_gib": 64,
        "wall_time_s": 1200.0,
        "threads_per_rank": 1,
    }


def test_24_rank_32_gib_profile_is_only_a_control_dict_addition(tmp_path: Path) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    utility = _set_expr_fixture(tmp_path)
    control_baseline = tmp_path / "baseline"
    control_profile = tmp_path / "profile"
    for output, profiling in ((control_baseline, False), (control_profile, True)):
        hpc_case.prepare_case(
            mesh,
            manifest,
            audit,
            output,
            ranks=24,
            delta_t_s=0.001,
            memory_gib=48,
            profiling=profiling,
            set_expr_fields=str(utility),
        )

    baseline_inputs = json.loads((control_baseline / "case-inputs.json").read_text())
    profile_inputs = json.loads((control_profile / "case-inputs.json").read_text())
    baseline_control = (control_baseline / "system/controlDict").read_text()
    profile_control = (control_profile / "system/controlDict").read_text()
    block = (
        "\nprofiling\n{\n    active true;\n    cpuInfo false;\n"
        "    memInfo false;\n    sysInfo false;\n}\n"
    )
    assert baseline_inputs["ranks"] == profile_inputs["ranks"] == 24
    assert baseline_inputs["resource_budget_provisional"]["memory_gib"] == 48
    assert baseline_inputs["profiling"] is False
    assert profile_inputs["profiling"] is True
    assert "profiling\n{" not in baseline_control
    assert profile_control == baseline_control + block

    from scripts import audit_iso_vof_ledger

    profile_case = control_profile
    audit = audit_iso_vof_ledger._check_supported_configuration(
        profile_case,
        profile_inputs,
        profile_case / "system/controlDict",
        profile_case / "system/fvSolution",
        profile_case / "constant/transportProperties",
    )
    assert audit["nAlphaSubCycles"] == 1
    solution = profile_case / "system/fvSolution"
    solution.write_text(
        solution.read_text().replace("nAlphaSubCycles 1;", "nAlphaSubCycles 2;", 1),
        encoding="utf-8",
    )
    with pytest.raises(audit_iso_vof_ledger.AuditError, match="nAlphaSubCycles=2"):
        audit_iso_vof_ledger._check_supported_configuration(
            profile_case,
            profile_inputs,
            profile_case / "system/controlDict",
            solution,
            profile_case / "constant/transportProperties",
        )


@pytest.mark.parametrize(
    ("ranks", "nodes", "end_time_s", "delta_t_s", "steps"),
    [
        (64, 1, 0.05, 0.0001, 500),
        (96, 1, 0.05, 0.0001, 500),
        (120, 1, 0.05, 0.0001, 500),
        (120, 1, 0.5, 0.001, 500),
        (240, 2, 0.5, 0.0005, 1000),
        (300, 3, 0.5, 0.001, 500),
    ],
)
def test_case_preparation_records_supported_scaling_and_fixed_horizons(
    tmp_path: Path,
    ranks: int,
    nodes: int,
    end_time_s: float,
    delta_t_s: float,
    steps: int,
) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    output = tmp_path / "prepared"
    hpc_case.prepare_case(
        mesh,
        manifest,
        audit,
        output,
        ranks=ranks,
        nodes=nodes,
        end_time_s=end_time_s,
        delta_t_s=delta_t_s,
        set_expr_fields=str(_set_expr_fixture(tmp_path)),
    )
    metadata = json.loads((output / "case-inputs.json").read_text(encoding="utf-8"))
    control = (output / "system/controlDict").read_text(encoding="utf-8")
    decompose = (output / "system/decomposeParDict").read_text(encoding="utf-8")
    assert (metadata["ranks"], metadata["node_count"], metadata["horizon_s"]) == (
        ranks,
        nodes,
        end_time_s,
    )
    assert metadata["time_controls"]["delta_t_s"] == delta_t_s
    assert metadata["time_controls"]["startup_steps"] == steps
    assert f"numberOfSubdomains {ranks};" in decompose
    assert f"endTime {end_time_s:g};" in control
    assert f"deltaT {delta_t_s:g};" in control
    assert f"maxDeltaT {delta_t_s:g};" in control
    assert f"writeInterval {end_time_s:g};" in control
    assert "adjustTimeStep no;" in control
    assert "nAlphaSubCycles 1;" in (output / "system/fvSolution").read_text()


@pytest.mark.parametrize(
    (
        "variant",
        "ranks",
        "end_time_s",
        "delta_t_s",
        "steps",
        "expected_momentum",
        "expected_gradient",
        "original_scheme",
        "diagnostic_scheme",
    ),
    [
        (
            "upwind",
            96,
            0.05,
            0.0001,
            500,
            "upwind",
            "grad(U) Gauss linear;",
            "div(rhoPhi,U) Gauss limitedLinearV 1;",
            "div(rhoPhi,U) Gauss upwind;",
        ),
        (
            "original",
            64,
            0.01,
            0.0001,
            100,
            "limitedLinearV 1",
            "grad(U) Gauss linear;",
            None,
            None,
        ),
        (
            "u_gradient_limited",
            64,
            0.01,
            0.0005,
            20,
            "limitedLinearV 1",
            "grad(U) cellLimited Gauss linear 1;",
            "grad(U) Gauss linear;",
            "grad(U) cellLimited Gauss linear 1;",
        ),
    ],
)
def test_diagnostic_variants_bind_exact_scheme_changes_and_fixed_short_horizon(
    tmp_path: Path,
    variant: str,
    ranks: int,
    end_time_s: float,
    delta_t_s: float,
    steps: int,
    expected_momentum: str,
    expected_gradient: str,
    original_scheme: str | None,
    diagnostic_scheme: str | None,
) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    output = tmp_path / "prepared"
    hpc_case.prepare_case(
        mesh,
        manifest,
        audit,
        output,
        ranks=ranks,
        end_time_s=end_time_s,
        delta_t_s=delta_t_s,
        numerical_variant=variant,
        set_expr_fields=str(_set_expr_fixture(tmp_path)),
    )

    metadata = json.loads((output / "case-inputs.json").read_text(encoding="utf-8"))
    schemes = (output / "system/fvSchemes").read_text(encoding="utf-8")
    controls = (output / "system/controlDict").read_text(encoding="utf-8")
    provenance = json.loads(hpc_case.PROVENANCE.read_text(encoding="utf-8"))
    expected_parent_sha = provenance["dictionaries"]["system/fvSchemes"]["sha256"]
    actual_sha = hpc_case.sha256(output / "system/fvSchemes")

    assert metadata["numerical_variant"] == variant
    assert metadata["actual_momentum_convection"] == expected_momentum
    assert metadata["actual_velocity_gradient_scheme"] == expected_gradient
    assumptions = metadata["numerical_assumptions"]
    assert assumptions["momentum_convection"] == expected_momentum
    assert assumptions["velocity_gradient_scheme"] == expected_gradient
    assert assumptions["parent_fvSchemes_sha256"] == expected_parent_sha
    assert assumptions["post_override_fvSchemes_sha256"] == actual_sha
    assert metadata["parent_fvSchemes_sha256"] == expected_parent_sha
    assert metadata["post_override_fvSchemes_sha256"] == actual_sha
    assert metadata["solver_dictionary_sha256"]["system/fvSchemes"] == actual_sha
    assert schemes.count(f"div(rhoPhi,U) Gauss {expected_momentum};") == 1
    assert schemes.count(expected_gradient) == 1
    assert schemes.count("grad(k) Gauss linear;") == 1
    assert schemes.count("grad(epsilon) Gauss linear;") == 1
    assert metadata["time_controls"]["startup_steps"] == steps
    assert (metadata["ranks"], metadata["node_count"]) == (ranks, 1)
    assert metadata["time_controls"]["delta_t_s"] == delta_t_s
    assert metadata["time_controls"]["full_field_write_times_s"] == [0.0, end_time_s]
    assert f"endTime {end_time_s:g};" in controls and f"deltaT {delta_t_s:g};" in controls
    assert "adjustTimeStep no;" in controls
    assert "failureLocations" in controls
    assert "fields (U p_rgh k epsilon nut);" in controls
    assert "location true;" in controls

    if variant == "original":
        assert schemes == (
            Path(__file__).resolve().parents[1] / "cases/e1_rouaix_hpc/template/system/fvSchemes"
        ).read_text(encoding="utf-8")
        assert assumptions["velocity_gradient_limiter_scope"] == (
            "no velocity-gradient limiter override"
        )
        assert assumptions["velocity_gradient_diagnostic_note"] is None
    else:
        original = tmp_path / f"original-{variant}"
        hpc_case.prepare_case(
            mesh,
            manifest,
            audit,
            original,
            ranks=ranks,
            end_time_s=end_time_s,
            delta_t_s=delta_t_s,
            numerical_variant="original",
            set_expr_fields=str(_set_expr_fixture(tmp_path)),
        )
        original_schemes = (original / "system/fvSchemes").read_text(encoding="utf-8")
        assert original_scheme is not None and diagnostic_scheme is not None
        assert original_schemes.count(original_scheme) == 1
        assert original_schemes.replace(original_scheme, diagnostic_scheme, 1) == schemes
        for path in output.rglob("*"):
            relative = path.relative_to(output)
            if path.is_file() and relative.as_posix() not in {
                "case-inputs.json",
                "system/fvSchemes",
            }:
                assert (original / relative).read_bytes() == path.read_bytes()
        if variant == "u_gradient_limited":
            assert assumptions["velocity_gradient_limiter_scope"] == (
                "cellLimited Gauss linear 1 on grad(U) only; grad(k) and grad(epsilon) unchanged"
            )
            assert (
                "not the Rouaix paper's Venkatakrishnan"
                in assumptions["velocity_gradient_diagnostic_note"]
            )


def test_five_second_write_interval_declares_one_second_checkpoints(tmp_path: Path) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    output = tmp_path / "prepared"
    hpc_case.prepare_case(
        mesh,
        manifest,
        audit,
        output,
        ranks=64,
        end_time_s=5.0,
        write_interval_s=1.0,
        delta_t_s=0.001,
        set_expr_fields=str(_set_expr_fixture(tmp_path)),
    )

    metadata = json.loads((output / "case-inputs.json").read_text(encoding="utf-8"))
    control = (output / "system/controlDict").read_text(encoding="utf-8")
    assert metadata["time_controls"]["snapshot_interval_s"] == 1.0
    assert metadata["time_controls"]["full_field_write_times_s"] == [0, 1, 2, 3, 4, 5]
    assert "writeInterval 1;" in control
    assert "purgeWrite 2;" in control
    assert metadata["time_controls"]["purge_write"] == 2
    assert metadata["time_controls"]["checkpoint_policy"]["retained_positive_checkpoint_limit"] == 2
    assert metadata["time_controls"]["checkpoint_policy"]["preserve_initial_global_t0"] is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda m: m["native_qa"].update(status="unqualified"), "native_qa"),
        (lambda m: m["native_qa"].update(version="Foundation13"), "native_qa"),
        (lambda m: m.update(cell_count=18), "cell count"),
    ],
)
def test_mesh_evidence_must_be_qualified_and_match_log(
    tmp_path: Path, mutate, message: str
) -> None:
    mesh, manifest_path, audit = _inputs(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        hpc_case.verify_mesh_inputs(mesh, manifest_path, audit)


def test_concave_set_exception_accepts_only_hash_bound_exact_native_failure(
    tmp_path: Path,
) -> None:
    mesh, manifest, audit, _log, _receipt, _ids = _concave_exception_inputs(tmp_path)

    evidence = hpc_case.verify_mesh_inputs(mesh, manifest, audit)

    assert evidence["cell_count"] == 228_016
    assert evidence["native_qualification_exception"]["status"] == (
        "qualified_with_exact_concave_set_exception"
    )
    assert evidence["native_qualification_exception"]["native_failure"] == {
        "category": "concaveCells",
        "count": 114_008,
        "failed_check_count": 1,
    }


@pytest.mark.skipif(
    not (REAL_QUALIFIED_MESH_BUNDLE / "mesh-manifest.json").is_file(),
    reason="the native qualified mesh evidence bundle is local ignored run data",
)
def test_real_qualified_mesh_receipt_and_cell_sets_decode_without_mesh_rehash() -> None:
    bundle = REAL_QUALIFIED_MESH_BUNDLE
    manifest_path = bundle / "mesh-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    native = manifest["native_qa"]
    result = hpc_case._verify_concave_qualification_exception(
        mesh_dir=bundle / "constant/polyMesh",
        manifest_path=manifest_path,
        native_log_path=bundle / native["log_path"],
        native_log_sha=native["log_sha256"],
        cell_count=manifest["cell_count"],
        mesh_hashes=manifest["mesh_files_sha256"],
        exception_ref=native["qualification_exception"],
    )

    assert result["status"] == "qualified_with_exact_concave_set_exception"
    assert result["native_failure"] == {
        "category": "concaveCells",
        "count": 114_008,
        "failed_check_count": 1,
    }
    assert result["native_ids_sha256"] == result["reference_ids_sha256"]


def test_concave_set_exception_rejects_id_mismatch_and_additional_native_failure(
    tmp_path: Path,
) -> None:
    mesh, manifest_path, nozzle_audit, log, receipt_path, native_ids = _concave_exception_inputs(
        tmp_path / "ids"
    )
    manifest = json.loads(manifest_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    changed_ids = native_ids.read_text().replace("40\n", "41\n", 1)
    native_ids.write_text(changed_ids, encoding="utf-8")
    native_set = receipt_path.parent / receipt["native_set"]["path"]
    native_set.write_text(native_set.read_text().replace("\n40\n", "\n41\n", 1), encoding="ascii")
    receipt["native_ids"]["sha256"] = hpc_case.sha256(native_ids)
    receipt["native_set"]["sha256"] = hpc_case.sha256(native_set)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest["native_qa"]["qualification_exception"]["sha256"] = hpc_case.sha256(receipt_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="ID sets differ"):
        hpc_case.verify_mesh_inputs(mesh, manifest_path, nozzle_audit)

    mesh, manifest_path, nozzle_audit, log, receipt_path, _ids = _concave_exception_inputs(
        tmp_path / "extra-failure"
    )
    manifest = json.loads(manifest_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    log.write_text(log.read_text() + " ***Face pyramids failed\n", encoding="utf-8")
    log_sha = hpc_case.sha256(log)
    manifest["native_qa"]["log_sha256"] = log_sha
    receipt["native_log_sha256"] = log_sha
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest["native_qa"]["qualification_exception"]["sha256"] = hpc_case.sha256(receipt_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="extra, missing, or differently counted failure"):
        hpc_case.verify_mesh_inputs(mesh, manifest_path, nozzle_audit)


def test_mesh_hash_or_nozzle_geometry_mismatch_is_rejected(tmp_path: Path) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    (mesh / "points").write_text("changed after QA\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        hpc_case.verify_mesh_inputs(mesh, manifest, audit)

    mesh, manifest, audit = _inputs(tmp_path / "other")
    nozzle = json.loads(audit.read_text(encoding="utf-8"))
    nozzle["area_vector_m2"] = [0.0, -nozzle["area_m2"], 0.0]
    audit.write_text(json.dumps(nozzle), encoding="utf-8")
    with pytest.raises(ValueError, match=r"outward along \+y"):
        hpc_case.verify_mesh_inputs(mesh, manifest, audit)


def test_only_declared_fixed_steps_are_preparable(tmp_path: Path) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    with pytest.raises(ValueError, match="deltaT"):
        hpc_case.prepare_case(
            mesh,
            manifest,
            audit,
            tmp_path / "prepared",
            ranks=64,
            delta_t_s=0.00025,
            set_expr_fields=str(_set_expr_fixture(tmp_path)),
        )


def test_preparation_rejects_a_successful_setexprfields_without_cell_values(
    tmp_path: Path,
) -> None:
    mesh, manifest, audit = _inputs(tmp_path)
    utility = tmp_path / "setExprFields-noop"
    utility.write_text("#!/usr/bin/env python3\nprint('completed without changing p_rgh')\n")
    utility.chmod(0o755)
    output = tmp_path / "prepared"

    with pytest.raises(RuntimeError, match="declared transformed p_rgh value per mesh cell"):
        hpc_case.prepare_case(
            mesh,
            manifest,
            audit,
            output,
            ranks=64,
            delta_t_s=0.001,
            set_expr_fields=str(utility),
        )

    assert "internalField   uniform 0;" in (output / "0/p_rgh").read_text()
    assert (output / "setExprFields.log").is_file()


def test_native_provenance_collector_binds_sources_runtime_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "openfoam-src"
    source_hashes = {}
    for index, (name, relative) in enumerate(native_provenance.SOURCE_FILES.items()):
        source = source_root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"verified source fixture {index}\n", encoding="utf-8")
        source_hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(native_provenance, "KNOWN_SOLVER_SOURCE_HASHES", source_hashes)

    module_name = "OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH"
    modules_log = tmp_path / "modules.log"
    modules_log.write_text(f"Currently Loaded Modulefiles:\n{module_name}\n", encoding="utf-8")
    executable = tmp_path / "interIsoFoam"
    executable.write_text("#!/bin/sh\nprintf 'Build : OpenFOAM-v2512\\n'\n")
    executable.chmod(0o755)
    env = {
        **os.environ,
        "WM_PROJECT_DIR": str(source_root),
        "WM_PROJECT_VERSION": "v2512",
        "WM_OPTIONS": "linux64CrayDPInt32Opt",
    }
    output = tmp_path / "native-source-evidence.json"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"job_id": "fixture-job"}), encoding="utf-8")

    evidence = native_provenance.collect_native_provenance(
        module_name=module_name,
        module_list_path=modules_log,
        output_path=output,
        run_manifest_path=manifest_path,
        env=env,
        executable_path=executable,
        architecture="x86_64",
    )

    saved_evidence = json.loads(output.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    native_solver = saved_evidence["native_solver"]
    assert evidence["execution_backend"] == "slurm-native"
    assert native_solver["module_name"] == module_name
    assert native_solver["version"] == "v2512"
    assert native_solver["label_size_bits"] == 32
    assert native_solver["executable_sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert {
        name: record["sha256"] for name, record in saved_evidence["solver_source"].items()
    } == source_hashes
    assert manifest["job_id"] == "fixture-job"
    assert manifest["native_solver"] == native_solver
    assert (
        manifest["native_source_evidence_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert (tmp_path / "native-source-evidence.solver-banner.log").is_file()
