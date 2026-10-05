#!/usr/bin/env python3
"""Exploratory fixed-mesh water ledger for the pinned stock interFoam/MULES case.

This is intentionally separate from the interIsoFoam/isoAdvection audit.
For this prepared MULES case, ``alphaPhi0.water`` is the registered corrected
phase flux and one alpha subcycle makes each recorded value a main-step flux.
The result is a diagnostic ledger, never a validation or conservation gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts.audit_iso_vof_ledger import (
    AuditError as SharedParseError,
)
from scripts.audit_iso_vof_ledger import (
    DataRow,
    _foam_named_blocks,
    _parse_table_file,
    _strip_foam_comments,
    _water_density,
    sha256_file,
)

PINNED_IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
SOURCE_PATCH = "dash8Opening"
OPEN_PATCHES = ("airInlet", "xOutlet", "yMin", "yMax", "zMin")
SOURCE_FILES = {
    "applications/solvers/multiphase/VoF/createAlphaFluxes.H": "77b142f1d144f09bbea41218c65c7e839e4745549853faf16fb4917351f09c5f",
    "applications/solvers/multiphase/VoF/alphaEqn.H": "b05056ce6ea249a8043ff0a50c630c95af8200eee9f85fa6422ca5d45442b146",
    "applications/solvers/multiphase/VoF/alphaEqnSubCycle.H": "18876f2adbfd288f2733653c64fbb38b3d971143d3d8a82b6a7524914f6982e4",
    "src/finiteVolume/cfdTools/general/include/alphaControls.H": "8e9308777208495a1c87b615ada3f0a147553a19da3fa93963ce44fcd4f2a8fc",
}


class MulesAuditError(ValueError):
    """Raised when this narrow interFoam/MULES audit contract is not met."""


@dataclass(frozen=True)
class LogRow:
    token: str
    time: Decimal
    delta_t_token: str
    delta_t: Decimal
    line_number: int


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MulesAuditError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise MulesAuditError(f"expected a JSON object in {path}")
    return value


def _single_foam_scalar(text: str, key: str, path: Path) -> str:
    matches = re.findall(rf"\b{re.escape(key)}\s+([^;]+)\s*;", _strip_foam_comments(text))
    if len(matches) != 1:
        raise MulesAuditError(
            f"expected exactly one {key} declaration in {path}; found {len(matches)}"
        )
    return matches[0].strip()


def _foam_blocks(text: str, path: Path) -> dict[str, str]:
    try:
        return _foam_named_blocks(text)
    except SharedParseError as error:
        raise MulesAuditError(f"cannot parse OpenFOAM dictionary {path}: {error}") from error


def _table_files(case_dir: Path, function_name: str, file_stem: str) -> tuple[Path, ...]:
    root = case_dir / "postProcessing" / function_name
    if not root.is_dir():
        raise MulesAuditError(f"missing function-object output directory: {root}")
    paths = tuple(sorted(path for path in root.rglob("*.dat") if path.name == f"{file_stem}.dat"))
    if not paths:
        raise MulesAuditError(f"missing {file_stem}.dat under {root}")
    if len(paths) != 1:
        raise MulesAuditError(
            f"ambiguous/restarted {function_name} output has {len(paths)} data files; "
            "combine it into one explicitly selected complete segment before auditing"
        )
    return paths


def _read_table(
    path: Path, *, value_count: int, header_marker: str
) -> tuple[list[DataRow], dict[str, Any]]:
    raw = path.read_bytes()
    try:
        rows, trailing_partial, digest, byte_length = _parse_table_file(
            path, expected_values=value_count, header_marker=header_marker, content=raw
        )
    except SharedParseError as error:
        raise MulesAuditError(str(error)) from error
    if trailing_partial:
        raise MulesAuditError(
            f"incomplete trailing row(s) in {path}; wait for a sealed step or preserve this attempt"
        )
    return rows, {"path": str(path.resolve()), "byte_length": byte_length, "sha256": digest}


def _parse_log_rows(path: Path) -> tuple[list[LogRow], dict[str, Any], int]:
    raw = path.read_bytes()
    pending: tuple[str, int] | None = None
    rows: list[LogRow] = []
    initial_time_records = 0
    for line_no, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        dt_match = re.search(r"\bdeltaT\s*=\s*([+\-0-9.eE]+)", line)
        time_match = re.search(r"\bTime\s*=\s*([+\-0-9.eE]+)", line)
        if dt_match:
            if pending is not None:
                raise MulesAuditError(f"unpaired deltaT before another deltaT in {path}:{line_no}")
            pending = (dt_match.group(1), line_no)
            try:
                if not Decimal(pending[0]).is_finite() or Decimal(pending[0]) <= 0:
                    raise MulesAuditError(f"deltaT must be finite and positive in {path}:{line_no}")
            except InvalidOperation as error:
                raise MulesAuditError(f"invalid deltaT in {path}:{line_no}") from error
        if time_match:
            token = time_match.group(1)
            try:
                time = Decimal(token)
            except InvalidOperation as error:
                raise MulesAuditError(f"invalid solver time in {path}:{line_no}") from error
            if not time.is_finite():
                raise MulesAuditError(f"non-finite solver time in {path}:{line_no}")
            if pending is None:
                # OpenFOAM prints a startup/restart ``Time =`` line before
                # stepping. Preserve it as a segment marker; duplicate solver
                # times are rejected later unless the caller selects one
                # explicit, complete interval.
                initial_time_records += 1
                continue
            dt_token, _ = pending
            rows.append(LogRow(token, time, dt_token, Decimal(dt_token), line_no))
            pending = None
    if not rows:
        raise MulesAuditError(f"no completed deltaT/Time pairs in solver log {path}")
    return (
        rows,
        {
            "path": str(path.resolve()),
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "trailing_unpaired_deltaT": pending[0] if pending else None,
        },
        initial_time_records,
    )


def _decimal(token: str, context: str) -> Decimal:
    try:
        value = Decimal(token)
    except InvalidOperation as error:
        raise MulesAuditError(f"invalid numeric token {token!r} for {context}") from error
    if not value.is_finite():
        raise MulesAuditError(f"non-finite numeric token {token!r} for {context}")
    return value


def _verify_source_evidence(
    case_inputs: dict[str, Any], source_dir: Path, expected_hashes: dict[str, str] | None = None
) -> dict[str, Any]:
    expected_hashes = expected_hashes or SOURCE_FILES
    method = case_inputs.get("numerical_method_comparison")
    if not isinstance(method, dict):
        raise MulesAuditError("case metadata lacks the interFoam/MULES method contract")
    if (
        method.get("method")
        != "OpenCFD v2512 stock interFoam MULES with bounded interface compression"
    ):
        raise MulesAuditError(
            "case metadata does not identify the supported stock interFoam/MULES method"
        )
    field_info = method.get("phase_volume_flux", {})
    if field_info.get("field_name") != "alphaPhi0.water":
        raise MulesAuditError("case metadata must identify runtime field alphaPhi0.water")
    evidence = method.get("source_evidence", {})
    if evidence.get("image") != PINNED_IMAGE or evidence.get("image_sha256") != PINNED_IMAGE_ID:
        raise MulesAuditError(
            "case source-evidence metadata does not pin the supported v2512 image"
        )
    observed: dict[str, dict[str, str]] = {}
    for relative, expected in expected_hashes.items():
        path = source_dir / relative
        if path.is_symlink() or not path.is_file():
            raise MulesAuditError(f"pinned v2512 source copy is missing or unsafe: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise MulesAuditError(f"pinned v2512 source hash mismatch for {relative}: {actual}")
        observed[relative] = {"path": str(path.resolve()), "sha256": actual}
    create = (source_dir / "applications/solvers/multiphase/VoF/createAlphaFluxes.H").read_text(
        encoding="utf-8"
    )
    alpha_eqn = (source_dir / "applications/solvers/multiphase/VoF/alphaEqn.H").read_text(
        encoding="utf-8"
    )
    subcycle = (source_dir / "applications/solvers/multiphase/VoF/alphaEqnSubCycle.H").read_text(
        encoding="utf-8"
    )
    controls = (source_dir / "src/finiteVolume/cfdTools/general/include/alphaControls.H").read_text(
        encoding="utf-8"
    )
    required = (
        ("createAlphaFluxes.H", create, 'IOobject::groupName("alphaPhi0", alpha1.group())'),
        ("createAlphaFluxes.H", create, "IOobject::AUTO_WRITE"),
        ("alphaEqn.H", alpha_eqn, "MULES::explicitSolve"),
        ("alphaEqn.H", alpha_eqn, "rhoPhi = alphaPhi10"),
        ("alphaEqnSubCycle.H", subcycle, "if (nAlphaSubCycles > 1)"),
        ("alphaEqnSubCycle.H", subcycle, "rhoPhiSum += (runTime.deltaT()/totalDeltaT)*rhoPhi"),
        ("alphaControls.H", controls, 'get<label>("nAlphaSubCycles")'),
    )
    absent = [f"{name}: {pattern}" for name, text, pattern in required if pattern not in text]
    if absent:
        raise MulesAuditError(
            f"pinned interFoam source no longer satisfies the audited flux contract: {absent}"
        )
    return {
        "classification": "pinned-source-copy-and-hash-verified",
        "image": PINNED_IMAGE,
        "image_id": PINNED_IMAGE_ID,
        "field_registry_name": "alphaPhi0.water",
        "basis": "createAlphaFluxes.H uses IOobject::groupName(alphaPhi0, alpha1.group()) and AUTO_WRITE; phase group water yields alphaPhi0.water",
        "mules_usage": "the MULES alpha equation updates alphaPhi10 and uses that flux to assemble rhoPhi",
        "subcycle_implication": "subcycling time-averages rhoPhi only; nAlphaSubCycles=1 is required for the measured flux to be a single main-step value",
        "control_lookup": "alphaControls.H obtains nAlphaSubCycles from the alpha solver dictionary",
        "source_files": observed,
    }


def verify_configuration(
    case_dir: Path, source_dir: Path | None = None, *, allow_restart: bool = False
) -> dict[str, Any]:
    case_dir = case_dir.resolve(strict=True)
    case_inputs_path = case_dir / "case-inputs.json"
    if not case_inputs_path.is_file():
        raise MulesAuditError(f"case-inputs.json is missing: {case_inputs_path}")
    case_inputs = _read_json(case_inputs_path)
    if case_inputs.get("solver") != "interFoam":
        raise MulesAuditError("this audit accepts only solver=interFoam")
    if case_inputs.get("openfoam_image") != PINNED_IMAGE:
        raise MulesAuditError(f"case must use the pinned solver image {PINNED_IMAGE}")
    numerical = case_inputs.get("numerical_method_comparison", {})
    alpha_meta = numerical.get("alpha_controls", {})
    if alpha_meta.get("nAlphaSubCycles") != 1:
        raise MulesAuditError("case metadata must state nAlphaSubCycles=1")

    control_path = case_dir / "system/controlDict"
    scheme_path = case_dir / "system/fvSchemes"
    solution_path = case_dir / "system/fvSolution"
    for path in (control_path, scheme_path, solution_path):
        if not path.is_file():
            raise MulesAuditError(f"required solver dictionary is missing: {path}")
    control_raw = control_path.read_text(encoding="utf-8", errors="replace")
    control = _strip_foam_comments(control_raw)
    app = re.findall(r"\bapplication\s+(\w+)\s*;", control)
    if app != ["interFoam"]:
        raise MulesAuditError(f"controlDict must set application interFoam; got {app}")
    start_from = re.findall(r"\bstartFrom\s+(\w+)\s*;", control)
    start_time = re.findall(r"\bstartTime\s+([^;]+)\s*;", control)
    end_time = re.findall(r"\bendTime\s+([^;]+)\s*;", control)
    if len(start_from) != 1 or len(start_time) != 1:
        raise MulesAuditError("controlDict requires exactly one startFrom and startTime")
    parsed_start_time = _decimal(start_time[0], "startTime")
    if parsed_start_time < 0:
        raise MulesAuditError("controlDict startTime must be nonnegative")
    if not allow_restart and (start_from != ["startTime"] or parsed_start_time != 0):
        raise MulesAuditError("full-run ledger requires startFrom startTime and startTime 0")
    if allow_restart and start_from[0] not in {"startTime", "latestTime"}:
        raise MulesAuditError("explicit segment supports only startFrom startTime or latestTime")
    if len(end_time) != 1:
        raise MulesAuditError("controlDict requires exactly one endTime")
    configured_end = _decimal(end_time[0], "endTime")
    metadata_end = case_inputs.get("horizon_s")
    if metadata_end is None or _decimal(str(metadata_end), "case-inputs horizon") != configured_end:
        raise MulesAuditError("controlDict endTime and case-inputs horizon_s disagree")
    time_format = re.findall(r"\btimeFormat\s+(\w+)\s*;", control)
    time_precision = re.findall(r"\btimePrecision\s+(\d+)\s*;", control)
    if time_format != ["fixed"] or len(time_precision) != 1:
        raise MulesAuditError("only fixed timeFormat with one explicit timePrecision is supported")
    precision = int(time_precision[0])
    if precision < 1 or precision > 15:
        raise MulesAuditError("unsupported controlDict timePrecision")

    scheme_text = _strip_foam_comments(scheme_path.read_text(encoding="utf-8", errors="replace"))
    scheme_blocks = _foam_blocks(scheme_text, scheme_path)
    ddt_block = scheme_blocks.get("ddtSchemes")
    if ddt_block is None:
        raise MulesAuditError("fvSchemes has no ddtSchemes dictionary")
    ddt_entries = re.findall(r"\b([^;{}]+?)\s+([^;]+)\s*;", ddt_block)
    if ddt_entries != [("default", "Euler")]:
        raise MulesAuditError(
            f"supported MULES time scheme is exactly `ddtSchemes {{ default Euler; }}`; got {ddt_entries}"
        )

    solution_raw = solution_path.read_text(encoding="utf-8", errors="replace")
    solution = _strip_foam_comments(solution_raw)
    alpha_blocks = re.findall(r'"alpha\.water\.\*"\s*\{([^{}]*)\}', solution)
    if len(alpha_blocks) != 1:
        raise MulesAuditError(
            f"fvSolution requires one alpha.water.* controls block; found {len(alpha_blocks)}"
        )
    subcycles = re.findall(r"\bnAlphaSubCycles\s+(\d+)\s*;", alpha_blocks[0])
    all_subcycles = re.findall(r"\bnAlphaSubCycles\s+(\d+)\s*;", solution)
    if subcycles != ["1"] or all_subcycles != ["1"]:
        raise MulesAuditError(
            "fvSolution must define exactly one nAlphaSubCycles 1 in alpha.water.*"
        )
    solution_blocks = _foam_blocks(solution, solution_path)
    pimple = solution_blocks.get("PIMPLE")
    outer = re.findall(r"\bnOuterCorrectors\s+(\d+)\s*;", pimple or "")
    all_outer = re.findall(r"\bnOuterCorrectors\s+(\d+)\s*;", solution)
    if outer != ["1"] or all_outer != ["1"]:
        raise MulesAuditError("fvSolution must define exactly one PIMPLE nOuterCorrectors 1")

    functions = _foam_blocks(control_raw, control_path)
    expected = {
        "waterVolume": ("volFieldValue", "volIntegrate", ("alpha.water",), None),
        **{
            f"{patch}Flux": ("surfaceFieldValue", "sum", ("phi", "alphaPhi0.water"), patch)
            for patch in (SOURCE_PATCH, *OPEN_PATCHES)
        },
    }
    actual_bindings: dict[str, Any] = {}
    for object_name, (expected_type, operation, fields, patch) in expected.items():
        body = functions.get(object_name)
        if body is None:
            raise MulesAuditError(f"controlDict is missing required function object {object_name}")
        types = re.findall(r"\btype\s+(\w+)\s*;", body)
        operations = re.findall(r"\boperation\s+(\w+)\s*;", body)
        field_lists = re.findall(r"\bfields\s*\(([^)]*)\)\s*;", body)
        if types != [expected_type] or operations != [operation]:
            raise MulesAuditError(f"unexpected {object_name} type/operation: {types}/{operations}")
        if field_lists != [" ".join(fields)]:
            normalized = [" ".join(values.split()) for values in field_lists]
            if normalized != [" ".join(fields)]:
                raise MulesAuditError(
                    f"{object_name} must report fields {fields}; got {field_lists}"
                )
        if patch is not None:
            regions = re.findall(r"\bregionType\s+(\w+)\s*;", body)
            names = re.findall(r"\bname\s+(\w+)\s*;", body)
            if regions != ["patch"] or names != [patch]:
                raise MulesAuditError(
                    f"{object_name} must bind to patch {patch}; got {regions}/{names}"
                )
        for key, required in (
            ("executeControl", "timeStep"),
            ("executeInterval", "1"),
            ("writeControl", "timeStep"),
            ("writeInterval", "1"),
        ):
            values = re.findall(rf"\b{key}\s+([^;]+)\s*;", body)
            if values != [required]:
                raise MulesAuditError(f"{object_name} requires {key} {required}; got {values}")
        actual_bindings[object_name] = {
            "type": expected_type,
            "operation": operation,
            "fields": fields,
            "patch": patch,
        }

    for forbidden in ("fvOptions", "fvModels", "dynamicMeshDict"):
        candidates = (case_dir / "constant" / forbidden, case_dir / "system" / forbidden)
        existing = [path for path in candidates if path.exists()]
        if existing:
            raise MulesAuditError(
                f"unsupported source/model or moving-mesh configuration: {existing}"
            )
    mesh_boundary = case_dir / "constant/polyMesh/boundary"
    alpha_field = case_dir / "0/alpha.water"
    velocity_field = case_dir / "0/U"
    transport = case_dir / "constant/transportProperties"
    for path in (mesh_boundary, alpha_field, velocity_field, transport):
        if not path.is_file():
            raise MulesAuditError(f"required mass-ledger input is missing: {path}")
    boundary_blocks = _foam_blocks(
        mesh_boundary.read_text(encoding="utf-8", errors="replace"), mesh_boundary
    )
    patch_types = {
        name: matches[0]
        for name, body in boundary_blocks.items()
        if name != "FoamFile"
        if (matches := re.findall(r"\btype\s+(\w+)\s*;", body))
    }
    declared_sources = case_inputs.get("source_patches")
    declared_open = case_inputs.get("open_patches")
    if declared_sources != [SOURCE_PATCH] or declared_open != list(OPEN_PATCHES):
        raise MulesAuditError(
            "source/open patch inventory differs from the declared one-source/five-open MULES case"
        )
    ledger_patches = {SOURCE_PATCH, *OPEN_PATCHES}
    if not ledger_patches <= set(patch_types):
        raise MulesAuditError(
            f"source/open patches absent from mesh boundary: {sorted(ledger_patches - set(patch_types))}"
        )
    wrong_patch_types = {
        name: patch_types[name] for name in ledger_patches if patch_types[name] != "patch"
    }
    if wrong_patch_types:
        raise MulesAuditError(
            f"source/open boundaries must be mesh type patch: {wrong_patch_types}"
        )
    omitted = set(patch_types) - ledger_patches
    if any(patch_types[name] != "wall" for name in omitted):
        raise MulesAuditError(
            f"unledgered non-wall boundary patches exist: { {name: patch_types[name] for name in omitted if patch_types[name] != 'wall'} }"
        )
    velocity_blocks = _foam_blocks(
        velocity_field.read_text(encoding="utf-8", errors="replace"), velocity_field
    )
    velocity_types = {
        name: values[0]
        for name, body in velocity_blocks.items()
        if (values := re.findall(r"\btype\s+(\w+)\s*;", body))
    }
    if set(patch_types) - set(velocity_types):
        raise MulesAuditError(
            f"initial U omits mesh patches: {sorted(set(patch_types) - set(velocity_types))}"
        )
    porous_wall = {
        name: velocity_types[name]
        for name in omitted
        if velocity_types[name] not in {"slip", "noSlip"}
    }
    if porous_wall:
        raise MulesAuditError(
            f"unledgered wall patches are not verified impermeable U conditions: {porous_wall}"
        )

    alpha_text = _strip_foam_comments(alpha_field.read_text(encoding="utf-8", errors="replace"))
    initial_alpha = re.findall(r"\binternalField\s+uniform\s+([^;]+)\s*;", alpha_text)
    if not allow_restart and initial_alpha != ["0"]:
        raise MulesAuditError(
            f"full-run ledger requires initial alpha.water internalField uniform 0; got {initial_alpha}"
        )
    initial_alpha_value: float | None = None
    if len(initial_alpha) == 1:
        try:
            candidate_alpha = float(initial_alpha[0])
        except ValueError:
            candidate_alpha = math.nan
        if math.isfinite(candidate_alpha):
            initial_alpha_value = candidate_alpha
    if not allow_restart and initial_alpha_value != 0.0:
        raise MulesAuditError(
            f"full-run ledger requires initial alpha.water internalField uniform 0; got {initial_alpha}"
        )
    rho = _water_density(transport, case_inputs)
    if not math.isclose(rho, 1000.0, rel_tol=0.0, abs_tol=1e-12):
        raise MulesAuditError(
            f"this prepared Dash-8 comparator expects constant water rho=1000 kg/m3, got {rho}"
        )
    source_area = case_inputs.get("source_patch_areas_m2", {}).get(SOURCE_PATCH)
    if (
        not isinstance(source_area, (int, float))
        or not math.isfinite(source_area)
        or source_area <= 0
    ):
        raise MulesAuditError("case metadata must declare a finite positive dash8Opening area")
    source_sign = case_inputs.get("boundary_conditions", {}).get("source_flow_sign", "")
    if "+z" not in source_sign or "-z" not in source_sign:
        raise MulesAuditError(
            "source patch orientation metadata must declare outward +z and prescribed flow -z"
        )
    source_history = case_inputs.get("source_histories", {}).get("dash8", {})
    samples_raw = source_history.get("samples_used_m_s")
    if not isinstance(samples_raw, list) or len(samples_raw) < 2:
        raise MulesAuditError("case metadata lacks the sampled prescribed Dash-8 source history")
    samples = [(float(item[0]), float(item[1])) for item in samples_raw]
    if any(not math.isfinite(t) or not math.isfinite(u) or u < 0 for t, u in samples):
        raise MulesAuditError("prescribed source history contains invalid times/speeds")
    if any(right[0] <= left[0] for left, right in zip(samples, samples[1:])):
        raise MulesAuditError("prescribed source history times are not strictly increasing")

    if source_dir is None:
        source_dir = case_dir.parent.parent / "source"
    source_dir = source_dir.resolve(strict=True)
    source_evidence = _verify_source_evidence(case_inputs, source_dir)
    return {
        "case_directory": str(case_dir),
        "case_inputs_path": str(case_inputs_path.resolve()),
        "case_inputs_sha256": sha256_file(case_inputs_path),
        "solver": "interFoam",
        "openfoam_image": PINNED_IMAGE,
        "openfoam_image_id": PINNED_IMAGE_ID,
        "time_scheme": "Euler (ddtSchemes default; no override)",
        "alpha_subcycles": 1,
        "pimple_outer_correctors": 1,
        "phase_flux_field": "alphaPhi0.water",
        "registered_source_evidence": source_evidence,
        "function_object_bindings": actual_bindings,
        "mesh_boundary_types": patch_types,
        "ledger_source_patch": SOURCE_PATCH,
        "ledger_open_patches": list(OPEN_PATCHES),
        "omitted_boundaries_verified_wall": sorted(omitted),
        "initial_internal_alpha_water": initial_alpha_value,
        "water_density_kg_m3": rho,
        "source_area_m2": float(source_area),
        "configured_end_s": float(configured_end),
        "configured_start_time_s": float(parsed_start_time),
        "configured_start_from": start_from[0],
        "prescribed_source_history_samples_m_s": [[t, u] for t, u in samples],
        "prescribed_expected_mass_kg_from_case_inputs": case_inputs.get(
            "analytic_expected_mass_kg"
        ),
        "configuration_sha256": {
            str(path.relative_to(case_dir)): sha256_file(path)
            for path in (
                control_path,
                scheme_path,
                solution_path,
                mesh_boundary,
                alpha_field,
                velocity_field,
                transport,
            )
        },
    }


def _integrate_piecewise_linear(
    samples: list[tuple[float, float]], start: float, end: float
) -> float:
    if end < start or start < samples[0][0] - 1e-12 or end > samples[-1][0] + 1e-12:
        raise MulesAuditError(f"prescribed source table does not cover interval [{start}, {end}] s")

    def value(time_s: float) -> float:
        for (left_t, left_u), (right_t, right_u) in zip(samples, samples[1:]):
            if left_t - 1e-12 <= time_s <= right_t + 1e-12:
                fraction = min(1.0, max(0.0, (time_s - left_t) / (right_t - left_t)))
                return left_u + fraction * (right_u - left_u)
        return samples[-1][1]

    breaks = [start, *(time for time, _ in samples if start < time < end), end]
    return sum((value(a) + value(b)) * 0.5 * (b - a) for a, b in zip(breaks, breaks[1:]))


def _integrate_history_with_print_tolerance(
    samples: list[tuple[float, float]], start: float, end: float, *, tolerance_s: float
) -> tuple[float, float]:
    """Integrate covered source history and explicitly clip printed-time slop."""
    if not math.isfinite(tolerance_s) or tolerance_s < 0:
        raise MulesAuditError("source-history time tolerance must be finite and nonnegative")
    if start < samples[0][0] - tolerance_s or end > samples[-1][0] + tolerance_s:
        raise MulesAuditError(
            f"prescribed source table does not cover interval [{start}, {end}] s "
            f"within print-precision allowance {tolerance_s} s"
        )
    clipped_start = max(start, samples[0][0])
    clipped_end = min(end, samples[-1][0])
    covered_duration = max(0.0, clipped_end - clipped_start)
    clipped_duration = max(0.0, end - start - covered_duration)
    if covered_duration == 0.0:
        return 0.0, clipped_duration
    return _integrate_piecewise_linear(samples, clipped_start, clipped_end), clipped_duration


def _select_rows(
    rows: list[DataRow], start: Decimal, end: Decimal, *, name: str, explicit_segment: bool
) -> list[DataRow]:
    selected = [row for row in rows if start < Decimal(row.token) <= end]
    if not selected:
        raise MulesAuditError(f"no {name} rows in selected interval ({start}, {end}]")
    for previous, current in zip(selected, selected[1:]):
        if Decimal(current.token) <= Decimal(previous.token):
            if explicit_segment:
                raise MulesAuditError(
                    f"selected segment is ambiguous: duplicate/out-of-order {name} times "
                    f"{previous.token}, {current.token}"
                )
            raise MulesAuditError(
                f"restarted or repeated {name} time series; select a complete explicit segment"
            )
    return selected


def audit_run(
    case_dir: Path,
    output_dir: Path,
    *,
    source_dir: Path | None = None,
    solver_log: Path | None = None,
    segment_start_s: float | None = None,
    segment_end_s: float | None = None,
    segment_initial_water_volume_m3: float | None = None,
) -> dict[str, Any]:
    case_dir = case_dir.resolve(strict=True)
    output_dir = output_dir.resolve(strict=False)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing audit output: {output_dir}")
    explicit = any(
        value is not None
        for value in (segment_start_s, segment_end_s, segment_initial_water_volume_m3)
    )
    if explicit and any(
        value is None for value in (segment_start_s, segment_end_s, segment_initial_water_volume_m3)
    ):
        raise MulesAuditError(
            "explicit restart segment requires start, end, and initial-water-volume together"
        )
    config = verify_configuration(case_dir, source_dir, allow_restart=explicit)
    if explicit:
        start = _decimal(str(segment_start_s), "segment start")
        end = _decimal(str(segment_end_s), "segment end")
        initial_volume = float(segment_initial_water_volume_m3)
        if start < 0 or end <= start or initial_volume < 0 or not math.isfinite(initial_volume):
            raise MulesAuditError("explicit segment bounds/initial water volume are invalid")
        if config["configured_start_from"] == "startTime" and start != Decimal(
            str(config["configured_start_time_s"])
        ):
            raise MulesAuditError(
                "explicit segment start must match controlDict startTime when startFrom is startTime"
            )
        initial_kind = "caller-supplied checkpoint inventory for explicit complete segment"
    else:
        start = Decimal(0)
        end = _decimal(str(config.get("configured_end_s", 0.6)), "configured end time")
        initial_volume = 0.0
        initial_kind = "verified zero internal alpha.water at startTime 0"

    half_unit = Decimal("0.5").scaleb(
        -int(
            _single_foam_scalar(
                (case_dir / "system/controlDict").read_text(encoding="utf-8", errors="replace"),
                "timePrecision",
                case_dir / "system/controlDict",
            )
        )
    )
    function_names = {
        "waterVolume": ("waterVolume", "volFieldValue", 1, "volintegrate(alpha.water)"),
        **{
            patch: (
                f"{patch}Flux",
                "surfaceFieldValue",
                2,
                "sum(phi) sum(alphaphi0.water)",
            )
            for patch in (SOURCE_PATCH, *OPEN_PATCHES)
        },
    }
    series: dict[str, list[DataRow]] = {}
    table_snapshots: dict[str, Any] = {}
    for name, (object_name, file_stem, value_count, header) in function_names.items():
        files = _table_files(case_dir, object_name, file_stem)
        rows, snapshot = _read_table(files[0], value_count=value_count, header_marker=header)
        series[name] = rows
        table_snapshots[name] = snapshot

    log_path = (
        solver_log.resolve(strict=True) if solver_log is not None else case_dir / "log.interFoam"
    )
    if not log_path.is_file():
        raise MulesAuditError(f"interFoam solver log is missing: {log_path}")
    log_rows, log_snapshot, initial_time_records = _parse_log_rows(log_path)
    selected_series = {
        name: _select_rows(rows, start, end, name=name, explicit_segment=explicit)
        for name, rows in series.items()
    }
    selected_log = [row for row in log_rows if start < row.time <= end]
    if not selected_log:
        raise MulesAuditError(
            f"no completed solver log steps in selected interval ({start}, {end}]"
        )
    for previous, current in zip(selected_log, selected_log[1:]):
        if current.time <= previous.time:
            raise MulesAuditError("restarted/duplicate solver log times in selected interval")
    time_keys = [Decimal(row.token) for row in selected_series["waterVolume"]]
    if len(set(time_keys)) != len(time_keys):
        raise MulesAuditError("selected water-inventory output has duplicate times")
    for name, rows in selected_series.items():
        if [Decimal(row.token) for row in rows] != time_keys:
            raise MulesAuditError(
                f"unmatched/missing time rows for {name}: expected {len(time_keys)}, got {len(rows)}"
            )
    if len(selected_log) != len(time_keys):
        raise MulesAuditError(
            f"solver log and diagnostics have unmatched step counts: {len(selected_log)} vs {len(time_keys)}"
        )
    for diagnostic_time, log_row in zip(time_keys, selected_log, strict=True):
        if abs(diagnostic_time - log_row.time) > half_unit:
            raise MulesAuditError(
                f"solver/log time mismatch at {diagnostic_time}: log={log_row.time} (tolerance {half_unit})"
            )

    # Check that native deltaT values support the selected interval, accounting
    # only for the known printed time/deltaT precision.
    reconstructed = start
    cumulative_delta_rounding = Decimal(0)
    reconstructed_times: list[Decimal] = []
    reconstruction_allowances: list[Decimal] = []
    for row in selected_log:
        reconstructed += row.delta_t
        cumulative_delta_rounding += Decimal("0.5").scaleb(row.delta_t.as_tuple().exponent)
        if abs(reconstructed - row.time) > half_unit + cumulative_delta_rounding:
            raise MulesAuditError(
                f"native cumulative deltaT does not reconstruct solver time {row.token}; "
                f"reconstructed={reconstructed}"
            )
        reconstructed_times.append(reconstructed)
        reconstruction_allowances.append(half_unit + cumulative_delta_rounding)
    if explicit:
        if abs(time_keys[-1] - end) > half_unit:
            raise MulesAuditError(
                f"explicit segment is incomplete: last diagnostic time {time_keys[-1]} does not reach {end}"
            )
    elif time_keys[-1] > end + half_unit:
        raise MulesAuditError("diagnostic data exceed configured horizon")

    rho = float(config["water_density_kg_m3"])
    area = float(config["source_area_m2"])
    samples = [(float(t), float(u)) for t, u in config["prescribed_source_history_samples_m_s"]]
    volume_rows = selected_series["waterVolume"]
    output_rows: list[dict[str, float | int | str]] = []
    cumulative_injected_kg = 0.0
    cumulative_escape_kg = 0.0
    cumulative_prescribed_kg = 0.0
    cumulative_history_clip_s = 0.0
    cumulative_source_q_m3 = 0.0
    cumulative_open_q_m3 = 0.0
    previous_volume = initial_volume
    for index, (time_key, log_row) in enumerate(zip(time_keys, selected_log, strict=True)):
        dt = float(log_row.delta_t)
        interval_end_native = float(reconstructed_times[index])
        interval_start = interval_end_native - dt
        interval_end = interval_end_native
        source_flux = selected_series[SOURCE_PATCH][index].values[1]
        open_flux = {patch: selected_series[patch][index].values[1] for patch in OPEN_PATCHES}
        volume = volume_rows[index].values[0]
        prescribed_history_volume_m3, clipped_history_s = _integrate_history_with_print_tolerance(
            samples,
            interval_start,
            interval_end,
            tolerance_s=float(reconstruction_allowances[index]),
        )
        prescribed_volume_step = area * prescribed_history_volume_m3
        cumulative_history_clip_s += clipped_history_s
        prescribed_rate = prescribed_volume_step / dt
        transported_in_volume_step = -source_flux * dt
        escape_volume_step = sum(open_flux.values()) * dt
        inventory_change_kg = rho * (volume - previous_volume)
        injected_step_kg = rho * transported_in_volume_step
        escape_step_kg = rho * escape_volume_step
        residual_step_kg = inventory_change_kg - injected_step_kg + escape_step_kg
        cumulative_injected_kg += injected_step_kg
        cumulative_escape_kg += escape_step_kg
        cumulative_prescribed_kg += rho * prescribed_volume_step
        cumulative_source_q_m3 += transported_in_volume_step
        cumulative_open_q_m3 += escape_volume_step
        cumulative_residual = (
            rho * (volume - initial_volume) - cumulative_injected_kg + cumulative_escape_kg
        )
        row: dict[str, float | int | str] = {
            "step_index": index + 1,
            "time_s": str(time_key),
            "interval_start_s_from_solver_deltaT": f"{interval_start:.15g}",
            "interval_end_s_from_solver_deltaT": f"{interval_end:.15g}",
            "deltaT_s_from_solver_log": f"{dt:.15g}",
            "prescribed_source_Q_m3_s": f"{prescribed_rate:.15g}",
            "prescribed_history_print_precision_clipped_s": f"{clipped_history_s:.15g}",
            "transported_source_alphaPhi0_signed_m3_s": f"{source_flux:.15g}",
            "transported_source_inflow_m3_s": f"{-source_flux:.15g}",
            "transported_minus_prescribed_Q_m3_s": f"{-source_flux - prescribed_rate:.15g}",
            "prescribed_source_mass_step_kg": f"{rho * prescribed_volume_step:.15g}",
            "transported_source_mass_step_kg": f"{injected_step_kg:.15g}",
            "transported_source_mass_cumulative_kg": f"{cumulative_injected_kg:.15g}",
            "transported_source_volume_cumulative_m3": f"{cumulative_source_q_m3:.15g}",
            "native_inventory_m3": f"{volume:.15g}",
            "native_inventory_kg": f"{rho * volume:.15g}",
            "inventory_change_kg": f"{inventory_change_kg:.15g}",
            "signed_net_open_boundary_escape_step_kg": f"{escape_step_kg:.15g}",
            "signed_net_open_boundary_escape_cumulative_kg": f"{cumulative_escape_kg:.15g}",
            "closure_residual_step_kg": f"{residual_step_kg:.15g}",
            "closure_residual_cumulative_kg": f"{cumulative_residual:.15g}",
        }
        for patch, flux in open_flux.items():
            row[f"{patch}_alphaPhi0_signed_m3_s"] = f"{flux:.15g}"
            row[f"{patch}_signed_mass_step_kg"] = f"{rho * flux * dt:.15g}"
        output_rows.append(row)
        previous_volume = volume

    final_volume = volume_rows[-1].values[0]
    final_residual = (
        rho * (final_volume - initial_volume) - cumulative_injected_kg + cumulative_escape_kg
    )
    max_step_residual = max(abs(float(row["closure_residual_step_kg"])) for row in output_rows)
    max_cumulative_residual = max(
        abs(float(row["closure_residual_cumulative_kg"])) for row in output_rows
    )
    prescribed_mass_metadata = config.get("prescribed_expected_mass_kg_from_case_inputs")
    last_time = float(time_keys[-1])
    configured_end = float(config["configured_end_s"])
    result: dict[str, Any] = {
        "schema": "dash8-interfoam-mules-water-ledger-v1",
        "classification": "exploratory diagnostic; not a conservation gate or validation",
        "case_directory": str(case_dir),
        "coverage": {
            "configured_horizon_s": configured_end,
            "segment_explicitly_selected": explicit,
            "segment_start_s": float(start),
            "requested_segment_end_s": float(end),
            "last_matched_time_s": last_time,
            "matched_main_steps": len(output_rows),
            "horizon_reached": abs(last_time - configured_end) <= float(half_unit),
            "complete_selected_segment": abs(last_time - float(end)) <= float(half_unit),
            "status": "exploratory_complete_segment"
            if explicit
            else (
                "exploratory_horizon_reached"
                if abs(last_time - configured_end) <= float(half_unit)
                else "exploratory_matched_prefix"
            ),
        },
        "supported_configuration": config,
        "integration": {
            "method": "right rectangle Q_k * actual solver-log deltaT_k for each completed MULES main step",
            "rho_water_kg_m3": rho,
            "initial_water_volume_m3": initial_volume,
            "initial_water_source": initial_kind,
            "final_native_inventory_m3": final_volume,
            "final_native_inventory_kg": rho * final_volume,
            "prescribed_history_mass_over_observed_intervals_kg": cumulative_prescribed_kg,
            "prescribed_history_endpoint_clipped_duration_s": cumulative_history_clip_s,
            "prescribed_full_history_mass_from_case_inputs_kg": prescribed_mass_metadata,
            "transported_source_mass_from_alphaPhi0_kg": cumulative_injected_kg,
            "transported_source_volume_from_alphaPhi0_m3": cumulative_source_q_m3,
            "transported_minus_prescribed_source_mass_kg": cumulative_injected_kg
            - cumulative_prescribed_kg,
            "signed_net_open_boundary_escape_kg": cumulative_escape_kg,
            "signed_open_boundary_volume_m3": cumulative_open_q_m3,
            "closure_residual_kg": final_residual,
            "max_abs_step_residual_kg": max_step_residual,
            "max_abs_cumulative_residual_kg": max_cumulative_residual,
            "closure_equation": "rho*(V_end-V_initial) - transported_source_in_mass + signed_net_open_boundary_escape_mass",
            "source_flux_sign": "surfaceFieldValue patch flux is outward-positive; source patch outward is +z, so negative alphaPhi0.water is inflow along prescribed -z",
            "open_flux_sign": "each named open-boundary patch is outward-positive; signed inward water remains negative and is not clipped",
            "post_bounding_residual_note": "MULES bounded phase transport and native inventory are reported as measured; residual is not hidden or used as an acceptance gate",
        },
        "row_snapshots": {**table_snapshots, "solverLog": log_snapshot},
        "solver_log_unpaired_initial_time_records": initial_time_records,
        "source_copy_directory": str((source_dir or (case_dir.parent.parent / "source")).resolve()),
        "audit_script_sha256": sha256_file(Path(__file__).resolve()),
        "input_sha256": {
            "case_inputs": sha256_file(case_dir / "case-inputs.json"),
            **config["configuration_sha256"],
        },
        "scientific_limitations": [
            "this support is specific to the pinned stock v2512 interFoam/MULES case and alphaPhi0.water",
            "the audit does not reuse the interIsoFoam alphaPhi_ semantics or its closure flags",
            "a low residual is a diagnostic for these saved flux/inventory rows, not a VOF validation or gate pass",
            "prescribed source-Q is the uniform table history times declared source area; transported water is measured separately from MULES alphaPhi0.water",
            "prescribed table integration clips only any interval outside its tabulated time range within the solver/log print-precision allowance; clipped duration is reported and no source-history extrapolation is performed",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = output_dir / "ledger.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    result["ledger_csv"] = str(csv_path.resolve())
    result["ledger_csv_sha256"] = sha256_file(csv_path)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result


def write_preflight(
    case_dir: Path, output_path: Path, source_dir: Path | None = None
) -> dict[str, Any]:
    result = verify_configuration(case_dir, source_dir)
    result["classification"] = (
        "prepared-case contract verified; no solver run or mass-ledger result"
    )
    result["preflight_script_sha256"] = sha256_file(Path(__file__).resolve())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preflight-json", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--solver-log", type=Path)
    parser.add_argument("--segment-start-s", type=float)
    parser.add_argument("--segment-end-s", type=float)
    parser.add_argument("--segment-initial-water-volume-m3", type=float)
    args = parser.parse_args(argv)
    try:
        if args.preflight_json is not None:
            if args.output_dir is not None:
                raise MulesAuditError("choose either --preflight-json or --output-dir")
            result = write_preflight(args.case_dir, args.preflight_json, args.source_dir)
            print(
                json.dumps(
                    {
                        "classification": result["classification"],
                        "phase_flux_field": result["phase_flux_field"],
                    },
                    indent=2,
                )
            )
            return 0
        if args.output_dir is None:
            raise MulesAuditError("--output-dir is required unless --preflight-json is provided")
        result = audit_run(
            args.case_dir,
            args.output_dir,
            source_dir=args.source_dir,
            solver_log=args.solver_log,
            segment_start_s=args.segment_start_s,
            segment_end_s=args.segment_end_s,
            segment_initial_water_volume_m3=args.segment_initial_water_volume_m3,
        )
    except (MulesAuditError, FileNotFoundError, FileExistsError, SharedParseError) as error:
        print(
            json.dumps(
                {
                    "status": "audit_unavailable_or_input_invalid",
                    "error": str(error),
                    "formal_gate": None,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": result["coverage"]["status"],
                "coverage": result["coverage"],
                "integration": result["integration"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
