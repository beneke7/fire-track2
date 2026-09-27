#!/usr/bin/env python3
"""Analyze the provisional P1 OpenFOAM source and liquid-inventory ledger."""

from __future__ import annotations

import argparse
import json
import math
import re
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WATER_DENSITY_KG_M3 = 1000.0
EXPECTED_MESH_CELLS = 2_081_200
CONTINUOUS_TARGET_SOURCE_MASS_KG = 230.4
CONTINUOUS_TARGET_SLOT_MASS_KG = CONTINUOUS_TARGET_SOURCE_MASS_KG / 4
ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG = 230.544
ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG = 57.636
PHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG = 230.256
PHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG = 57.564
PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG = 230.256
PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG = 57.564
PROPOSED_RELATIVE_TOLERANCE = 0.001
PROPOSED_MAX_COURANT = 0.5
PROPOSED_MAX_INTERFACE_COURANT = 0.25
EXPECTED_MAX_WALL_TIME_S = 3600.0
EXPECTED_DELTA_T_S = 1e-4
EXPECTED_END_TIME_S = 0.12
EXPECTED_STEP_COUNT = 1200
SOURCE_RAMP_START_S = 0.0795
SOURCE_RAMP_END_S = 0.0805
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TIME_TOLERANCE_S = 1e-9

SLOT_PATCHES = ("slot_01", "slot_02", "slot_03", "slot_04")
OPEN_PATCHES = ("airInlet", "airOutlet", "lowerOutlet")
FLUX_FIELDS = ("phi", "alphaPhi")
CASE_STAGE_ORDER = ("blockMesh", "checkMesh", "decomposePar", "interIsoFoam", "reconstructPar")
EXPECTED_SOURCE_PROFILE_M_S = (
    (0.0, 0.0, 0.0, -4.8),
    (0.0795, 0.0, 0.0, -4.8),
    (0.0805, 0.0, 0.0, 0.0),
    (0.12, 0.0, 0.0, 0.0),
)
EXPECTED_INPUT_SOURCE_PROFILE = ((0.0, -4.8), (0.0795, -4.8), (0.0805, 0.0), (0.12, 0.0))


@dataclass(frozen=True)
class Sample:
    time_s: float
    values: dict[str, float]
    line_number: int


@dataclass
class ParsedTable:
    name: str
    path: Path
    samples: list[Sample] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    indices: dict[str, int] = field(default_factory=dict)


def _normalized_column(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def _header_indices(tokens: list[str], required: tuple[str, ...]) -> dict[str, int] | None:
    normalized = [_normalized_column(token) for token in tokens]
    time_indices = [index for index, name in enumerate(normalized) if name in {"time", "times"}]
    if not time_indices:
        return None

    aliases = {
        "phi": {"phi", "sumphi"},
        "alphaPhi": {"alphaphi", "sumalphaphi"},
        "volume": {"volintegratealphawater"},
    }
    indices = {"time": time_indices[0]}
    for field_name in required:
        field_indices = [
            index for index, name in enumerate(normalized) if name in aliases[field_name]
        ]
        if len(field_indices) == 1:
            indices[field_name] = field_indices[0]
    return indices


def _parse_table(path: Path, name: str, required: tuple[str, ...]) -> ParsedTable:
    table = ParsedTable(name=name, path=path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        table.issues.append(f"cannot read {path}: {error}")
        return table

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        is_comment = line.startswith("#")
        content = line[1:].strip() if is_comment else line
        tokens = re.split(r"\s+", content)
        header_indices = _header_indices(tokens, required)
        if header_indices is not None:
            missing_columns = [
                field_name for field_name in required if field_name not in header_indices
            ]
            if missing_columns:
                table.issues.append(
                    f"line {line_number}: header is missing required column(s): "
                    + ", ".join(missing_columns)
                )
            elif table.indices and table.indices != header_indices:
                table.issues.append(f"line {line_number}: conflicting table header")
            else:
                table.indices = header_indices
                table.header = tokens
            continue
        if is_comment:
            continue

        if not table.indices:
            if not any("table header" in issue for issue in table.issues):
                table.issues.append("data rows appeared before a recognizable table header")
            continue

        last_index = max(table.indices[field_name] for field_name in ("time", *required))
        if len(tokens) <= last_index:
            table.issues.append(f"line {line_number}: row has too few columns")
            continue
        try:
            time_s = float(tokens[table.indices["time"]])
            values = {
                field_name: float(tokens[table.indices[field_name]]) for field_name in required
            }
        except ValueError:
            table.issues.append(f"line {line_number}: row contains a non-numeric value")
            continue
        if not math.isfinite(time_s) or any(not math.isfinite(value) for value in values.values()):
            table.issues.append(f"line {line_number}: row contains a non-finite value")
            continue
        if time_s < 0:
            table.issues.append(f"line {line_number}: negative sample time {time_s:g} s")
            continue
        if table.samples and time_s <= table.samples[-1].time_s + TIME_TOLERANCE_S:
            table.issues.append(
                f"line {line_number}: duplicate or non-increasing sample time {time_s:g} s"
            )
            continue
        table.samples.append(Sample(time_s, values, line_number))

    if not table.indices:
        table.issues.append("missing recognizable table header")
    return table


def _function_object_table_path(
    case_dir: Path, object_name: str, filename: str
) -> tuple[Path, list[str]]:
    """Resolve OpenFOAM's numeric start-time directory without guessing its format."""
    output_dir = case_dir / "postProcessing" / object_name
    candidates: list[Path] = []
    for path in sorted(output_dir.glob(f"*/{filename}")):
        if not path.is_file():
            continue
        try:
            time_value = float(path.parent.name)
        except ValueError:
            continue
        if math.isfinite(time_value) and time_value >= 0:
            candidates.append(path)
    if not candidates:
        return output_dir / "0" / filename, []
    if len(candidates) > 1:
        return candidates[0], [
            f"expected one {filename} table under {output_dir}, found {len(candidates)} numeric time directories"
        ]
    return candidates[0], []


def _load_json(path: Path, label: str, issues: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        issues.append(f"cannot read {label} {path}: {error}")
        return {}
    if not isinstance(value, dict):
        issues.append(f"{label} must contain a JSON object")
        return {}
    return value


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _as_json_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _strip_foam_comments(text: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//.*?$", "", without_block_comments, flags=re.MULTILINE)


def _matching_brace(text: str, opening_index: int, left: str = "{", right: str = "}") -> int | None:
    depth = 0
    in_quote: str | None = None
    escaped = False
    for index in range(opening_index, len(text)):
        char = text[index]
        if in_quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_quote:
                in_quote = None
            continue
        if char in {'"', "'"}:
            in_quote = char
        elif char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return index
    return None


def _named_blocks(text: str, name: str) -> list[str]:
    clean_text = _strip_foam_comments(text)
    pattern = re.compile(rf"(?m)^[ \t]*{re.escape(name)}\s*\{{")
    bodies = []
    for match in pattern.finditer(clean_text):
        opening_index = clean_text.find("{", match.start(), match.end())
        closing_index = _matching_brace(clean_text, opening_index)
        if closing_index is not None:
            bodies.append(clean_text[opening_index + 1 : closing_index])
    return bodies


def _single_named_block(text: str, name: str) -> str | None:
    blocks = _named_blocks(text, name)
    return blocks[0] if len(blocks) == 1 else None


def _dictionary_entries(text: str, key: str) -> list[str]:
    clean_text = _strip_foam_comments(text)
    return [
        match.group(1).strip()
        for match in re.finditer(rf"(?m)^[ \t]*{re.escape(key)}[ \t]+([^;\n]+);", clean_text)
    ]


def _single_dictionary_entry(text: str, key: str) -> str | None:
    entries = _dictionary_entries(text, key)
    return entries[0] if len(entries) == 1 else None


def _foam_number_matches(actual: Any, expected: float) -> bool:
    value = _as_float(actual)
    return value is not None and abs(value - expected) <= 1e-12


def _is_adjust_time_step_disabled(value: Any) -> bool:
    return (
        value is False
        or (isinstance(value, str) and value.lower() == "no")
        or (isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0)
    )


def _numeric_profile_matches(actual: Any, expected: tuple[tuple[float, ...], ...]) -> bool:
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(actual, expected, strict=True):
        if not isinstance(actual_row, list) or len(actual_row) != len(expected_row):
            return False
        if any(
            not _foam_number_matches(value, target)
            for value, target in zip(actual_row, expected_row, strict=True)
        ):
            return False
    return True


def _numeric_sequence_matches(actual: Any, expected: tuple[float, ...]) -> bool:
    return (
        isinstance(actual, list)
        and len(actual) == len(expected)
        and all(
            _foam_number_matches(value, target)
            for value, target in zip(actual, expected, strict=True)
        )
    )


def _profile_from_slot_patch(
    patch_body: str,
) -> tuple[list[tuple[float, float, float, float]], list[str]]:
    issues: list[str] = []
    if _single_dictionary_entry(patch_body, "type") != "uniformFixedValue":
        issues.append("slot boundary type is not uniformFixedValue")

    clean_body = _strip_foam_comments(patch_body)
    table_matches = list(re.finditer(r"\buniformValue\s+table\s*\(", clean_body))
    if len(table_matches) != 1:
        return [], [*issues, "slot source table is missing or malformed"]
    match = table_matches[0]
    opening_index = clean_body.find("(", match.start())
    closing_index = _matching_brace(clean_body, opening_index, "(", ")")
    if closing_index is None:
        return [], [*issues, "slot source table has unbalanced parentheses"]
    table_body = clean_body[opening_index + 1 : closing_index]
    row_pattern = re.compile(
        rf"\(\s*({NUMBER})\s+\(\s*({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*\)\s*\)"
    )
    matches = list(row_pattern.finditer(table_body))
    remainder = row_pattern.sub("", table_body)
    if re.sub(r"[\s()]", "", remainder):
        issues.append("slot source table contains malformed knot data")
    profile = [tuple(float(value) for value in row.groups()) for row in matches]
    if len(profile) != len(EXPECTED_SOURCE_PROFILE_M_S):
        issues.append("slot source table does not contain exactly four knots")

    expected_fallback = "uniform (0 0 -4.8)"
    if _single_dictionary_entry(patch_body, "value") != expected_fallback:
        issues.append("slot source fallback value is not uniform (0 0 -4.8)")
    return profile, issues


def _case_source_profile_report(case_dir: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    path = case_dir / "0" / "U"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return {
            "path": str(path),
            "per_slot": {},
            "matches_protocol": False,
            "inputs_profile_matches_protocol": _numeric_profile_matches(
                inputs.get("source_profile_m_s"), EXPECTED_INPUT_SOURCE_PROFILE
            ),
            "issues": [f"cannot read slot source boundary file {path}: {error}"],
        }

    boundary_field = _single_named_block(content, "boundaryField")
    issues: list[str] = []
    if boundary_field is None:
        issues.append("0/U must contain exactly one boundaryField dictionary")
        boundary_field = ""
    per_slot: dict[str, Any] = {}
    all_slots_match = boundary_field != ""
    for slot in SLOT_PATCHES:
        patch_blocks = _named_blocks(boundary_field, slot)
        patch_issues: list[str] = []
        if len(patch_blocks) != 1:
            patch_issues.append("slot boundary patch is missing or duplicated")
            profile: list[tuple[float, float, float, float]] = []
        else:
            profile, patch_issues = _profile_from_slot_patch(patch_blocks[0])
        profile_matches = len(profile) == len(EXPECTED_SOURCE_PROFILE_M_S) and all(
            all(
                _foam_number_matches(value, expected)
                for value, expected in zip(row, expected_row, strict=True)
            )
            for row, expected_row in zip(profile, EXPECTED_SOURCE_PROFILE_M_S, strict=True)
        )
        if not profile_matches:
            patch_issues.append("slot source knots differ from the frozen P1 profile")
        if patch_issues:
            all_slots_match = False
            issues.extend(f"{slot}: {issue}" for issue in patch_issues)
        per_slot[slot] = {
            "profile_m_s": profile,
            "matches_protocol": profile_matches and not patch_issues,
            "issues": patch_issues,
        }
    input_profile_matches = _numeric_profile_matches(
        inputs.get("source_profile_m_s"), EXPECTED_INPUT_SOURCE_PROFILE
    )
    if not input_profile_matches:
        issues.append("inputs.json source_profile_m_s differs from the frozen P1 profile")
    profiles_agree = all(
        per_slot[slot]["matches_protocol"]
        and all(
            _foam_number_matches(actual, expected)
            for actual, expected in zip(
                ((point[0], point[3]) for point in per_slot[slot]["profile_m_s"]),
                EXPECTED_INPUT_SOURCE_PROFILE,
                strict=True,
            )
            for actual, expected in zip(actual, expected, strict=True)
        )
        for slot in SLOT_PATCHES
    )
    return {
        "path": str(path),
        "per_slot": per_slot,
        "inputs_profile_matches_protocol": input_profile_matches,
        "case_profiles_agree_with_inputs": profiles_agree and input_profile_matches,
        "matches_protocol": all_slots_match and input_profile_matches and profiles_agree,
        "issues": issues,
    }


def _function_object_report(control_dict: str) -> dict[str, Any]:
    issues: list[str] = []
    functions_body = _single_named_block(control_dict, "functions")
    if functions_body is None:
        return {
            "matches_protocol": False,
            "objects": {},
            "issues": ["controlDict must contain exactly one functions dictionary"],
        }

    objects: dict[str, Any] = {}
    all_objects_match = True
    for patch in (*SLOT_PATCHES, *OPEN_PATCHES):
        object_name = f"{patch}Flux"
        blocks = _named_blocks(functions_body, object_name)
        object_issues: list[str] = []
        if len(blocks) != 1:
            object_issues.append("required flux function object is missing or duplicated")
            body = ""
        else:
            body = blocks[0]
        expected_values = {
            "type": "surfaceFieldValue",
            "libs": "(fieldFunctionObjects)",
            "regionType": "patch",
            "name": patch,
            "operation": "sum",
            "writeFields": "false",
            "executeControl": "timeStep",
            "executeInterval": "1",
            "writeControl": "timeStep",
            "writeInterval": "1",
        }
        observed_values = {key: _single_dictionary_entry(body, key) for key in expected_values}
        for key, expected_value in expected_values.items():
            if observed_values[key] != expected_value:
                object_issues.append(f"{key} must be {expected_value}")
        field_entries = re.findall(
            r"(?m)^[ \t]*fields[ \t]*\(([^)]*)\)[ \t]*;", _strip_foam_comments(body)
        )
        observed_fields = field_entries[0].split() if len(field_entries) == 1 else []
        if observed_fields != ["phi", "alphaPhi_"]:
            object_issues.append("fields must be exactly (phi alphaPhi_)")
        if object_issues:
            all_objects_match = False
            issues.extend(f"{object_name}: {issue}" for issue in object_issues)
        objects[object_name] = {
            "settings": observed_values,
            "fields": observed_fields,
            "matches_protocol": not object_issues,
            "issues": object_issues,
        }

    object_name = "waterVolume"
    blocks = _named_blocks(functions_body, object_name)
    object_issues = []
    if len(blocks) != 1:
        object_issues.append("required water-volume function object is missing or duplicated")
        body = ""
    else:
        body = blocks[0]
    expected_values = {
        "type": "volFieldValue",
        "libs": "(fieldFunctionObjects)",
        "writeControl": "timeStep",
        "writeInterval": "1",
        "operation": "volIntegrate",
        "writeFields": "false",
    }
    observed_values = {key: _single_dictionary_entry(body, key) for key in expected_values}
    for key, expected_value in expected_values.items():
        if observed_values[key] != expected_value:
            object_issues.append(f"{key} must be {expected_value}")
    field_entries = re.findall(
        r"(?m)^[ \t]*fields[ \t]*\(([^)]*)\)[ \t]*;", _strip_foam_comments(body)
    )
    observed_fields = field_entries[0].split() if len(field_entries) == 1 else []
    if observed_fields != ["alpha.water"]:
        object_issues.append("fields must be exactly (alpha.water)")
    execute_control = _single_dictionary_entry(body, "executeControl")
    execute_interval = _single_dictionary_entry(body, "executeInterval")
    if execute_control is not None or execute_interval is not None:
        if execute_control != "timeStep" or execute_interval != "1":
            object_issues.append("optional execute controls must be timeStep with interval 1")
    if object_issues:
        all_objects_match = False
        issues.extend(f"{object_name}: {issue}" for issue in object_issues)
    objects[object_name] = {
        "settings": observed_values,
        "fields": observed_fields,
        "matches_protocol": not object_issues,
        "issues": object_issues,
    }
    return {"matches_protocol": all_objects_match, "objects": objects, "issues": issues}


def _input_protocol_report(inputs: dict[str, Any]) -> dict[str, Any]:
    expected_values: dict[str, Any] = {
        "solver": "interIsoFoam",
        "protocol_revision": 2,
        "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
        "alpha_phi_sampling_convention": "left_endpoint_of_completed_interval",
        "alpha_phi_left_sampled_expected_release_kg": ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG,
        "alpha_phi_left_sampled_expected_release_per_slot_kg": ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG,
        "phi_right_sampled_expected_release_kg": PHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG,
        "phi_right_sampled_expected_release_per_slot_kg": PHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG,
        "mesh_cells_expected": EXPECTED_MESH_CELLS,
        "end_time_s": EXPECTED_END_TIME_S,
        "time_step_mode": "fixed",
        "fixed_delta_t_s": EXPECTED_DELTA_T_S,
        "adjust_time_step": False,
        "expected_time_steps": EXPECTED_STEP_COUNT,
        "n_alpha_sub_cycles": 1,
        "max_courant": PROPOSED_MAX_COURANT,
        "max_alpha_courant": PROPOSED_MAX_INTERFACE_COURANT,
        "source_dose_tolerance_fraction": PROPOSED_RELATIVE_TOLERANCE,
        "mass_ledger_tolerance_fraction": PROPOSED_RELATIVE_TOLERANCE,
        "source_velocity_m_s": [0.0, 0.0, -4.8],
        "source_constant_velocity_interval_s": [0.0, 0.0795],
        "source_window_s": [0.0, 0.0805],
        "source_shutoff_ramp_s": [0.0795, 0.0805],
        "source_shutoff_s": 0.0805,
        "expected_source_mass_flow_kg_s": 2880.0,
        "flux_field": "alphaPhi_",
        "flux_patch_names": [*SLOT_PATCHES, *OPEN_PATCHES],
        "flux_sample_interval_steps": 1,
        "volume_sample_interval_steps": 1,
        "hard_stop_on_courant_breach": True,
    }
    observed = {key: inputs.get(key) for key in expected_values}
    checks = {}
    issues: list[str] = []
    for key, expected in expected_values.items():
        if key == "source_velocity_m_s":
            matches = _numeric_sequence_matches(inputs.get(key), (0.0, 0.0, -4.8))
        elif key == "source_constant_velocity_interval_s":
            matches = _numeric_sequence_matches(inputs.get(key), (0.0, 0.0795))
        elif key == "source_window_s":
            matches = _numeric_sequence_matches(inputs.get(key), (0.0, 0.0805))
        elif key == "source_shutoff_ramp_s":
            matches = _numeric_sequence_matches(inputs.get(key), (0.0795, 0.0805))
        elif key == "flux_patch_names":
            matches = inputs.get(key) == expected
        elif key == "alpha_phi_sampling_convention":
            matches = inputs.get(key) == expected
        elif isinstance(expected, float):
            matches = _foam_number_matches(inputs.get(key), expected)
        elif isinstance(expected, bool):
            matches = type(inputs.get(key)) is bool and inputs.get(key) is expected
        elif key == "n_alpha_sub_cycles":
            matches = type(inputs.get(key)) is int and inputs.get(key) == expected
        else:
            matches = inputs.get(key) == expected
        checks[key] = matches
        if not matches:
            issues.append(f"inputs.json {key} differs from frozen P1 value {expected!r}")
    return {
        "matches_protocol": all(checks.values()),
        "observed": observed,
        "checks": checks,
        "issues": issues,
    }


def _transport_properties_report(case_dir: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    path = case_dir / "constant" / "transportProperties"
    issues: list[str] = []
    try:
        transport_properties = _strip_foam_comments(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except OSError as error:
        transport_properties = ""
        issues.append(f"cannot read authoritative case dictionary {path}: {error}")

    phases = _single_dictionary_entry(transport_properties, "phases")
    phases_match = phases is not None and re.fullmatch(r"\(\s*water\s+air\s*\)", phases) is not None
    if not phases_match:
        issues.append("case/constant/transportProperties phases must be exactly (water air)")

    water_blocks = _named_blocks(transport_properties, "water")
    water_body = water_blocks[0] if len(water_blocks) == 1 else ""
    if len(water_blocks) != 1:
        issues.append("case/constant/transportProperties must contain exactly one water block")
    density_entries = re.findall(r"(?<![\w])rho\s+([^;\n]+);", _strip_foam_comments(water_body))
    water_density_entry = density_entries[0].strip() if len(density_entries) == 1 else None
    water_density = _as_float(water_density_entry)
    water_density_matches = water_density is not None and _foam_number_matches(
        water_density, WATER_DENSITY_KG_M3
    )
    if not water_density_matches:
        issues.append("case/constant/transportProperties water rho must be 1000 kg/m3")

    water_inputs = inputs.get("water") if isinstance(inputs.get("water"), dict) else {}
    input_density = _as_float(water_inputs.get("density_kg_m3"))
    inputs_agree = (
        input_density is not None
        and water_density is not None
        and _foam_number_matches(input_density, water_density)
    )
    if not inputs_agree:
        issues.append(
            "inputs.json water density must agree with case/constant/transportProperties rho"
        )

    return {
        "path": str(path),
        "phases": phases,
        "phases_match_protocol": phases_match,
        "water_density_kg_m3": water_density,
        "water_density_matches_protocol": water_density_matches,
        "inputs_density_kg_m3": input_density,
        "inputs_agree_with_case": inputs_agree,
        "matches_protocol": phases_match and water_density_matches and inputs_agree,
        "issues": issues,
    }


def _case_protocol_report(case_dir: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    input_report = _input_protocol_report(inputs)
    issues.extend(input_report["issues"])
    transport_properties = _transport_properties_report(case_dir, inputs)
    issues.extend(transport_properties["issues"])

    control_path = case_dir / "system" / "controlDict"
    try:
        control_dict = _strip_foam_comments(
            control_path.read_text(encoding="utf-8", errors="replace")
        )
    except OSError as error:
        control_dict = ""
        issues.append(f"cannot read authoritative case dictionary {control_path}: {error}")
    control_expected: dict[str, Any] = {
        "application": "interIsoFoam",
        "startFrom": "startTime",
        "startTime": 0.0,
        "stopAt": "endTime",
        "deltaT": EXPECTED_DELTA_T_S,
        "endTime": EXPECTED_END_TIME_S,
        "adjustTimeStep": "no",
        "maxCo": PROPOSED_MAX_COURANT,
        "maxAlphaCo": PROPOSED_MAX_INTERFACE_COURANT,
    }
    control_values = {key: _single_dictionary_entry(control_dict, key) for key in control_expected}
    control_checks: dict[str, bool] = {}
    for key, expected in control_expected.items():
        actual = control_values[key]
        if isinstance(expected, float):
            matches = _foam_number_matches(actual, expected)
        else:
            matches = actual == expected
        control_checks[key] = matches
        if not matches:
            issues.append(
                f"case/system/controlDict {key} is missing, duplicated, or differs from {expected!r}"
            )

    input_control_pairs = {
        "deltaT": ("fixed_delta_t_s", "deltaT"),
        "endTime": ("end_time_s", "endTime"),
        "maxCo": ("max_courant", "maxCo"),
        "maxAlphaCo": ("max_alpha_courant", "maxAlphaCo"),
    }
    inputs_control_checks = {}
    for control_key, (input_key, _) in input_control_pairs.items():
        observed_control_value = _as_float(control_values[control_key])
        inputs_control_checks[control_key] = (
            observed_control_value is not None
            and _foam_number_matches(inputs.get(input_key), observed_control_value)
        )
    inputs_control_checks["adjustTimeStep"] = (
        "adjust_time_step" not in inputs
        or _is_adjust_time_step_disabled(inputs.get("adjust_time_step"))
    )
    for key, matches in inputs_control_checks.items():
        if not matches:
            issues.append(f"inputs.json disagrees with case/system/controlDict {key}")

    solution_path = case_dir / "system" / "fvSolution"
    try:
        fv_solution = _strip_foam_comments(
            solution_path.read_text(encoding="utf-8", errors="replace")
        )
    except OSError as error:
        fv_solution = ""
        issues.append(f"cannot read authoritative case dictionary {solution_path}: {error}")
    solvers_body = _single_named_block(fv_solution, "solvers")
    alpha_solver_body = (
        _single_named_block(solvers_body, '"alpha.water.*"') if solvers_body else None
    )
    subcycle_value = _single_dictionary_entry(alpha_solver_body or "", "nAlphaSubCycles")
    fv_solution_matches = subcycle_value == "1"
    if not fv_solution_matches:
        issues.append(
            "case/system/fvSolution alpha.water solver must set nAlphaSubCycles 1 exactly once"
        )
    input_subcycles_matches = (
        "n_alpha_sub_cycles" not in inputs or inputs.get("n_alpha_sub_cycles") == 1
    )
    if not input_subcycles_matches:
        issues.append("inputs.json disagrees with case/system/fvSolution nAlphaSubCycles")

    source_profile = _case_source_profile_report(case_dir, inputs)
    function_objects = _function_object_report(control_dict)
    issues.extend(source_profile["issues"])
    issues.extend(function_objects["issues"])
    matches_protocol = (
        input_report["matches_protocol"]
        and all(control_checks.values())
        and all(inputs_control_checks.values())
        and fv_solution_matches
        and input_subcycles_matches
        and source_profile["matches_protocol"]
        and function_objects["matches_protocol"]
        and transport_properties["matches_protocol"]
    )
    return {
        "matches_protocol": matches_protocol,
        "inputs": input_report,
        "controlDict": {
            "path": str(control_path),
            "observed": control_values,
            "checks": control_checks,
            "inputs_agree": inputs_control_checks,
            "matches_protocol": all(control_checks.values())
            and all(inputs_control_checks.values()),
        },
        "fvSolution": {
            "path": str(solution_path),
            "alpha_water_nAlphaSubCycles": subcycle_value,
            "matches_protocol": fv_solution_matches and input_subcycles_matches,
        },
        "source_profiles": source_profile,
        "function_objects": function_objects,
        "transport_properties": transport_properties,
        "issues": issues,
    }


def _time_matches(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= TIME_TOLERANCE_S


def _sample_at(samples: list[Sample], target_time_s: float) -> Sample | None:
    index = bisect_left(samples, target_time_s, key=lambda sample: sample.time_s)
    candidates = []
    if index < len(samples) and _time_matches(samples[index].time_s, target_time_s):
        candidates.append(samples[index])
    if index > 0 and _time_matches(samples[index - 1].time_s, target_time_s):
        candidates.append(samples[index - 1])
    return candidates[0] if len(candidates) == 1 else None


def _series_completeness(table: ParsedTable) -> dict[str, Any]:
    expected_by_index = {
        step: step * EXPECTED_DELTA_T_S for step in range(1, EXPECTED_STEP_COUNT + 1)
    }
    observed: set[int] = set()
    unexpected_times: list[float] = []
    for sample in table.samples:
        if _time_matches(sample.time_s, 0.0):
            continue
        step = round(sample.time_s / EXPECTED_DELTA_T_S)
        expected_time = expected_by_index.get(step)
        if expected_time is None or not _time_matches(sample.time_s, expected_time):
            unexpected_times.append(sample.time_s)
        else:
            observed.add(step)
    missing_steps = sorted(set(expected_by_index) - observed)
    complete = (
        not table.issues
        and not missing_steps
        and not unexpected_times
        and len(table.samples) in {EXPECTED_STEP_COUNT, EXPECTED_STEP_COUNT + 1}
    )
    return {
        "path": str(table.path),
        "header": table.header,
        "row_count": len(table.samples),
        "first_time_s": table.samples[0].time_s if table.samples else None,
        "last_time_s": table.samples[-1].time_s if table.samples else None,
        "expected_step_rows": EXPECTED_STEP_COUNT,
        "missing_step_count": len(missing_steps),
        "first_missing_step_indices": missing_steps[:20],
        "unexpected_times_s": unexpected_times[:20],
        "issues": list(table.issues),
        "complete": complete,
    }


def _integrate(table: ParsedTable, value_name: str) -> tuple[list[tuple[Sample, float]], list[str]]:
    cumulative = 0.0
    previous_time_s = 0.0
    integrated: list[tuple[Sample, float]] = []
    issues: list[str] = []
    for sample in table.samples:
        delta_time_s = sample.time_s - previous_time_s
        if delta_time_s < -TIME_TOLERANCE_S:
            issues.append(f"{table.name}: cannot integrate non-increasing time {sample.time_s:g} s")
            integrated.append((sample, cumulative))
            continue
        cumulative += sample.values[value_name] * max(0.0, delta_time_s)
        integrated.append((sample, cumulative))
        previous_time_s = sample.time_s
    return integrated, issues


def _integral_at(integrated: list[tuple[Sample, float]], target_time_s: float) -> float | None:
    index = bisect_left(integrated, target_time_s, key=lambda item: item[0].time_s)
    candidates = []
    if index < len(integrated) and _time_matches(integrated[index][0].time_s, target_time_s):
        candidates.append(integrated[index][1])
    if index > 0 and _time_matches(integrated[index - 1][0].time_s, target_time_s):
        candidates.append(integrated[index - 1][1])
    return candidates[0] if len(candidates) == 1 else None


def _numeric_log_values(log_text: str, pattern: str) -> list[float]:
    return [float(value) for value in re.findall(pattern, log_text, re.MULTILINE)]


def _find_log(run_dir: Path, manifest: dict[str, Any]) -> Path | None:
    declared = manifest.get("openfoam_log") or manifest.get("log_file")
    candidates: list[Path] = []
    if isinstance(declared, str):
        candidate = Path(declared)
        candidates.append(candidate if candidate.is_absolute() else run_dir / candidate)
    candidates.extend(
        (
            run_dir / "openfoam-console.log",
            run_dir / "case" / "openfoam-console.log",
            run_dir / "case" / "log.interIsoFoam",
        )
    )
    return next((path for path in candidates if path.is_file()), None)


def _solver_log_diagnostics(log_text: str) -> dict[str, Any]:
    lines = log_text.splitlines()
    start_indices = [
        index for index, line in enumerate(lines) if line.strip() == "Starting time loop"
    ]
    if len(start_indices) != 1:
        return {
            "loop_found": False,
            "loop_end_found": False,
            "solver_times": [],
            "solver_global_courant": [],
            "solver_interface_courant": [],
            "solver_step_diagnostic_groups": [],
            "unassigned_global_courant_rows": 0,
            "unassigned_interface_courant_rows": 0,
            "startup_global_courant": [],
            "trailing_times": [],
        }
    start_index = start_indices[0]
    end_index = next(
        (index for index in range(start_index + 1, len(lines)) if lines[index].strip() == "End"),
        None,
    )
    loop_end_index = end_index if end_index is not None else len(lines)
    loop_lines = lines[start_index + 1 : loop_end_index]
    startup_lines = lines[:start_index]
    trailing_lines = lines[loop_end_index + 1 :] if end_index is not None else []
    loop_text = "\n".join(loop_lines)
    startup_text = "\n".join(startup_lines)
    trailing_text = "\n".join(trailing_lines)
    step_diagnostic_groups: list[dict[str, Any]] = []
    pending_global = 0
    pending_interface = 0
    time_pattern = re.compile(rf"^\s*Time\s*=\s*({NUMBER})\s*$")
    global_pattern = re.compile(rf"^\s*Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})")
    interface_pattern = re.compile(
        rf"^\s*Interface Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})"
    )
    for line in loop_lines:
        time_match = time_pattern.match(line)
        if time_match:
            step_diagnostic_groups.append(
                {
                    "time_s": float(time_match.group(1)),
                    "global_courant_rows": pending_global,
                    "interface_courant_rows": pending_interface,
                }
            )
            pending_global = 0
            pending_interface = 0
        elif global_pattern.match(line):
            pending_global += 1
        elif interface_pattern.match(line):
            pending_interface += 1
    return {
        "loop_found": True,
        "loop_end_found": end_index is not None,
        "solver_times": _numeric_log_values(loop_text, rf"^\s*Time\s*=\s*({NUMBER})\s*$"),
        "solver_global_courant": _numeric_log_values(
            loop_text, rf"^\s*Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})"
        ),
        "solver_interface_courant": _numeric_log_values(
            loop_text,
            rf"^\s*Interface Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})",
        ),
        "solver_step_diagnostic_groups": step_diagnostic_groups,
        "unassigned_global_courant_rows": pending_global,
        "unassigned_interface_courant_rows": pending_interface,
        "startup_global_courant": _numeric_log_values(
            startup_text, rf"^\s*Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})"
        ),
        "trailing_times": _numeric_log_values(trailing_text, rf"^\s*Time\s*=\s*({NUMBER})\s*$"),
    }


def _final_state_written(case_dir: Path) -> tuple[bool, str | None]:
    try:
        entries = list(case_dir.iterdir())
    except OSError:
        return False, None
    for entry in entries:
        if not entry.is_dir():
            continue
        value = _as_float(entry.name)
        if value is not None and _time_matches(value, EXPECTED_END_TIME_S):
            try:
                alpha_field_written = any(
                    child.name == "alpha.water" and child.is_file() for child in entry.iterdir()
                )
                return alpha_field_written, str(entry)
            except OSError:
                return False, str(entry)
    return False, None


def _common_times(tables: list[ParsedTable]) -> list[float]:
    if not tables:
        return []
    common = []
    for candidate in tables[0].samples:
        if all(_sample_at(table.samples, candidate.time_s) is not None for table in tables[1:]):
            if not common or not _time_matches(common[-1], candidate.time_s):
                common.append(candidate.time_s)
    return common


def _ramp_interval_count(common_times: list[float]) -> int:
    return sum(
        1
        for start, end in zip(common_times, common_times[1:])
        if start >= SOURCE_RAMP_START_S - TIME_TOLERANCE_S
        and end <= SOURCE_RAMP_END_S + TIME_TOLERANCE_S
        and _time_matches(end - start, EXPECTED_DELTA_T_S)
    )


def _relative_error(observed: float | None, expected: float) -> float | None:
    return abs(observed - expected) / abs(expected) if observed is not None and expected else None


def build_report(run_dir: Path) -> dict[str, Any]:
    """Build an auditable P1 ledger report, retaining failures as report data."""
    run_dir = run_dir.resolve()
    issues: list[str] = []
    manifest = _load_json(run_dir / "manifest.json", "manifest", issues)
    inputs = _load_json(run_dir / "inputs.json", "inputs", issues)
    case_dir = run_dir / "case" if (run_dir / "case").is_dir() else run_dir

    if not manifest:
        issues.append("run manifest is unavailable")
    if not inputs:
        issues.append("run inputs are unavailable")
    independent_review = manifest.get("independent_review")
    independent_review = independent_review if isinstance(independent_review, dict) else {}
    protocol_review_decision = independent_review.get("protocol_decision")
    execution_code_review = independent_review.get("execution_code_review")
    execution_status = independent_review.get("execution_status")
    execution_review_approved = (
        independent_review.get("protocol_revision") == 2
        and independent_review.get("protocol_amendment_id") == "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1"
        and protocol_review_decision == "approved_with_revisions"
        and independent_review.get("amendment_1_review_decision") == "approved_with_revisions"
        and isinstance(independent_review.get("amendment_1_reviewer"), str)
        and bool(independent_review.get("amendment_1_reviewer", "").strip())
        and isinstance(independent_review.get("amendment_1_reviewed_utc"), str)
        and bool(independent_review.get("amendment_1_reviewed_utc", "").strip())
        and execution_code_review == "approved"
        and isinstance(independent_review.get("execution_code_reviewer"), str)
        and bool(independent_review.get("execution_code_reviewer", "").strip())
        and isinstance(independent_review.get("execution_code_reviewed_utc"), str)
        and bool(independent_review.get("execution_code_reviewed_utc", "").strip())
        and execution_status == "ready"
    )
    if not execution_review_approved:
        issues.append(
            "run manifest must record a ready execution contract with independent protocol and code approval"
        )

    tables: dict[str, ParsedTable] = {}
    for patch_name in (*SLOT_PATCHES, *OPEN_PATCHES):
        object_name = f"{patch_name}Flux"
        table_path, path_issues = _function_object_table_path(
            case_dir, object_name, "surfaceFieldValue.dat"
        )
        tables[patch_name] = _parse_table(table_path, patch_name, FLUX_FIELDS)
        tables[patch_name].issues.extend(path_issues)
    inventory_path, inventory_path_issues = _function_object_table_path(
        case_dir, "waterVolume", "volFieldValue.dat"
    )
    tables["waterVolume"] = _parse_table(inventory_path, "waterVolume", ("volume",))
    tables["waterVolume"].issues.extend(inventory_path_issues)
    series_checks = {name: _series_completeness(table) for name, table in tables.items()}
    for name, check in series_checks.items():
        for parse_issue in check["issues"]:
            issues.append(f"{name}: {parse_issue}")
        if check["missing_step_count"]:
            issues.append(
                f"{name}: {check['missing_step_count']} expected per-step row(s) are missing"
            )
        if check["unexpected_times_s"]:
            issues.append(f"{name}: unexpected time sample(s) were logged")

    case_protocol = _case_protocol_report(case_dir, inputs)
    issues.extend(case_protocol["issues"])
    control_values = case_protocol["controlDict"]["observed"]
    declared_delta_t_s = _as_float(control_values.get("deltaT"))
    declared_end_time_s = _as_float(control_values.get("endTime"))
    control_adjust_time_step = control_values.get("adjustTimeStep")
    input_adjust_time_step = inputs.get("adjust_time_step")
    adjust_time_step_disabled = control_adjust_time_step == "no"
    config_delta_t_ok = case_protocol["controlDict"]["checks"].get("deltaT", False)
    config_end_time_ok = case_protocol["controlDict"]["checks"].get("endTime", False)

    water_inputs = inputs.get("water") if isinstance(inputs.get("water"), dict) else {}
    declared_density = _as_float(water_inputs.get("density_kg_m3"))
    declared_mass = _as_float(inputs.get("expected_released_mass_kg"))
    declared_slot_count = inputs.get("slot_count")
    source_input_contract_ok = (
        declared_density is not None
        and _time_matches(declared_density, WATER_DENSITY_KG_M3)
        and declared_mass is not None
        and _time_matches(declared_mass, CONTINUOUS_TARGET_SOURCE_MASS_KG)
        and declared_slot_count == 4
    )
    if not source_input_contract_ok:
        issues.append(
            "inputs must declare four slots, 1,000 kg/m3 water, and the proposed 230.4 kg source target"
        )

    tables_list = list(tables.values())
    common_times = _common_times(tables_list)
    ramp_interval_count = _ramp_interval_count(common_times)
    expected_positive_times = [
        step * EXPECTED_DELTA_T_S for step in range(1, EXPECTED_STEP_COUNT + 1)
    ]
    common_expected_count = sum(
        1
        for expected_time in expected_positive_times
        if any(_time_matches(actual, expected_time) for actual in common_times)
    )
    data_complete = (
        all(check["complete"] for check in series_checks.values())
        and common_expected_count == EXPECTED_STEP_COUNT
        and ramp_interval_count == 10
    )
    if ramp_interval_count != 10:
        issues.append(f"source ramp has {ramp_interval_count} of 10 expected common time intervals")

    integrated: dict[str, list[tuple[Sample, float]]] = {}
    for name in (*SLOT_PATCHES, *OPEN_PATCHES):
        values, integration_issues = _integrate(tables[name], "alphaPhi")
        integrated[name] = values
        issues.extend(integration_issues)
    phi_integrated: dict[str, list[tuple[Sample, float]]] = {}
    for name in SLOT_PATCHES:
        values, integration_issues = _integrate(tables[name], "phi")
        phi_integrated[name] = values
        issues.extend(integration_issues)

    ledger_samples: list[dict[str, Any]] = []
    for index, time_s in enumerate(common_times):
        slot_source_kg: dict[str, float | None] = {}
        for slot in SLOT_PATCHES:
            liquid_volume_m3 = _integral_at(integrated[slot], time_s)
            slot_source_kg[slot] = (
                -WATER_DENSITY_KG_M3 * liquid_volume_m3 if liquid_volume_m3 is not None else None
            )
        open_patch_volume_m3 = {
            patch_name: _integral_at(integrated[patch_name], time_s) for patch_name in OPEN_PATCHES
        }
        if any(value is None for value in open_patch_volume_m3.values()):
            open_volume_total_m3 = None
            open_mass_total_kg = None
        else:
            open_volume_total_m3 = sum(
                float(value) for value in open_patch_volume_m3.values() if value is not None
            )
            open_mass_total_kg = WATER_DENSITY_KG_M3 * open_volume_total_m3
        inventory_sample = _sample_at(tables["waterVolume"].samples, time_s)
        inventory_volume_m3 = inventory_sample.values["volume"] if inventory_sample else None
        inventory_mass_kg = (
            WATER_DENSITY_KG_M3 * inventory_volume_m3 if inventory_volume_m3 is not None else None
        )
        total_source_kg = (
            sum(value for value in slot_source_kg.values() if value is not None)
            if all(value is not None and math.isfinite(value) for value in slot_source_kg.values())
            else None
        )
        residual_kg = (
            total_source_kg - open_mass_total_kg - inventory_mass_kg
            if total_source_kg is not None
            and open_mass_total_kg is not None
            and inventory_mass_kg is not None
            else None
        )
        if index == 0:
            delta_time_s = time_s
        else:
            delta_time_s = time_s - common_times[index - 1]
        ledger_samples.append(
            {
                "time_s": time_s,
                "interval_from_previous_common_sample_s": delta_time_s,
                "per_slot_source_mass_kg": slot_source_kg,
                "total_source_mass_kg": total_source_kg,
                "open_patch_signed_liquid_volume_m3": open_patch_volume_m3,
                "signed_net_open_patch_outflow_m3": open_volume_total_m3,
                "signed_net_open_patch_outflow_kg": open_mass_total_kg,
                "box_inventory_m3": inventory_volume_m3,
                "box_inventory_kg": inventory_mass_kg,
                "residual_kg": residual_kg,
                "residual_percent_of_continuous_target": (
                    100 * residual_kg / CONTINUOUS_TARGET_SOURCE_MASS_KG
                    if residual_kg is not None
                    else None
                ),
                "residual_relative_to_cumulative_source": (
                    abs(residual_kg) / total_source_kg
                    if residual_kg is not None
                    and total_source_kg is not None
                    and total_source_kg > 0
                    else None
                ),
                "residual_percent_of_cumulative_source": (
                    100 * residual_kg / total_source_kg
                    if residual_kg is not None
                    and total_source_kg is not None
                    and total_source_kg > 0
                    else None
                ),
            }
        )

    final_sample = next(
        (
            sample
            for sample in reversed(ledger_samples)
            if _time_matches(sample["time_s"], EXPECTED_END_TIME_S)
        ),
        None,
    )
    source_dose_protocol_eligible = case_protocol["matches_protocol"]
    slot_doses: dict[str, dict[str, Any]] = {}
    inlet_cross_check: dict[str, dict[str, Any]] = {}
    for slot in SLOT_PATCHES:
        observed = final_sample["per_slot_source_mass_kg"].get(slot) if final_sample else None
        phi_volume = _integral_at(phi_integrated[slot], EXPECTED_END_TIME_S)
        alpha_phi_volume = _integral_at(integrated[slot], EXPECTED_END_TIME_S)
        phi_inlet_volume = -phi_volume if phi_volume is not None else None
        alpha_phi_inlet_volume = -alpha_phi_volume if alpha_phi_volume is not None else None
        difference = (
            alpha_phi_inlet_volume - phi_inlet_volume
            if alpha_phi_inlet_volume is not None and phi_inlet_volume is not None
            else None
        )
        phi_observed_mass = -WATER_DENSITY_KG_M3 * phi_volume if phi_volume is not None else None
        left_target_error = (
            abs(observed - ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG)
            if observed is not None
            else None
        )
        continuous_target_error = (
            abs(observed - CONTINUOUS_TARGET_SLOT_MASS_KG) if observed is not None else None
        )
        numerical_left_target_within = (
            left_target_error
            <= PROPOSED_RELATIVE_TOLERANCE * ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG
            if left_target_error is not None
            else False
        )
        numerical_continuous_target_within = (
            continuous_target_error <= PROPOSED_RELATIVE_TOLERANCE * CONTINUOUS_TARGET_SLOT_MASS_KG
            if continuous_target_error is not None
            else False
        )
        left_target_within = source_dose_protocol_eligible and numerical_left_target_within
        continuous_target_within = (
            source_dose_protocol_eligible and numerical_continuous_target_within
        )
        slot_doses[slot] = {
            "alphaPhi_left_sampled_target_mass_kg": ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG,
            "previous_alphaPhi_right_sampled_target_mass_kg": PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG,
            "phi_right_sampled_target_mass_kg": PHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG,
            "continuous_analytic_target_mass_kg": CONTINUOUS_TARGET_SLOT_MASS_KG,
            "observed_mass_kg": observed,
            "absolute_error_to_alphaPhi_left_sampled_target_kg": left_target_error,
            "relative_error_to_alphaPhi_left_sampled_target": _relative_error(
                observed, ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG
            ),
            "relative_error_to_continuous_target": _relative_error(
                observed, CONTINUOUS_TARGET_SLOT_MASS_KG
            ),
            "relative_error_to_previous_alphaPhi_right_sampled_target": _relative_error(
                observed, PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG
            ),
            "numerically_within_alphaPhi_left_sampled_target_0p1_percent": numerical_left_target_within,
            "numerically_within_continuous_target_0p1_percent": numerical_continuous_target_within,
            "eligible_under_current_protocol_revision": source_dose_protocol_eligible,
            "within_alphaPhi_left_sampled_target_0p1_percent": left_target_within,
            "within_continuous_target_0p1_percent": continuous_target_within,
            "within_proposed_0p1_percent": left_target_within and continuous_target_within,
            "phi_observed_mass_kg": phi_observed_mass,
            "phi_relative_error_to_right_sampled_target": _relative_error(
                phi_observed_mass, PHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG
            ),
        }
        inlet_cross_check[slot] = {
            "inward_phi_volume_m3": phi_inlet_volume,
            "inward_alphaPhi_volume_m3": alpha_phi_inlet_volume,
            "alphaPhi_minus_phi_volume_m3": difference,
            "relative_difference_using_phi": (
                abs(difference) / abs(phi_inlet_volume)
                if difference is not None and phi_inlet_volume not in (None, 0.0)
                else None
            ),
            "acceptance_tolerance_registered": False,
        }

    final_source_mass_kg = final_sample["total_source_mass_kg"] if final_sample else None
    source_total_left_error = (
        abs(final_source_mass_kg - ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG)
        if final_source_mass_kg is not None
        else None
    )
    source_total_continuous_error = (
        abs(final_source_mass_kg - CONTINUOUS_TARGET_SOURCE_MASS_KG)
        if final_source_mass_kg is not None
        else None
    )
    numerical_source_dose_left_check = (
        source_total_left_error is not None
        and source_total_left_error
        <= PROPOSED_RELATIVE_TOLERANCE * ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG
    )
    numerical_source_dose_continuous_check = (
        source_total_continuous_error is not None
        and source_total_continuous_error
        <= PROPOSED_RELATIVE_TOLERANCE * CONTINUOUS_TARGET_SOURCE_MASS_KG
    )
    source_dose_left_check = source_dose_protocol_eligible and numerical_source_dose_left_check
    source_dose_continuous_check = (
        source_dose_protocol_eligible and numerical_source_dose_continuous_check
    )
    source_dose_check = (
        final_source_mass_kg is not None
        and source_dose_left_check
        and source_dose_continuous_check
        and all(slot["within_proposed_0p1_percent"] for slot in slot_doses.values())
    )
    max_abs_residual_kg = max(
        (
            abs(sample["residual_kg"])
            for sample in ledger_samples
            if sample["residual_kg"] is not None
        ),
        default=None,
    )
    final_residual_kg = final_sample["residual_kg"] if final_sample else None
    positive_source_samples = [
        sample
        for sample in ledger_samples
        if sample["total_source_mass_kg"] is not None and sample["total_source_mass_kg"] > 0
    ]
    residual_ratios = [
        sample["residual_relative_to_cumulative_source"]
        for sample in positive_source_samples
        if sample["residual_relative_to_cumulative_source"] is not None
    ]
    max_relative_residual = max(residual_ratios, default=None)
    max_relative_residual_sample = next(
        (
            sample
            for sample in positive_source_samples
            if sample["residual_relative_to_cumulative_source"] == max_relative_residual
        ),
        None,
    )
    box_residual_check = (
        bool(positive_source_samples)
        and len(residual_ratios) == len(positive_source_samples)
        and max_relative_residual is not None
        and max_relative_residual <= PROPOSED_RELATIVE_TOLERANCE
    )

    log_path = _find_log(run_dir, manifest)
    log_text = ""
    if log_path is None:
        issues.append("OpenFOAM console log is missing")
    else:
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            issues.append(f"cannot read OpenFOAM console log {log_path}: {error}")

    solver_log = _solver_log_diagnostics(log_text)
    solver_times = solver_log["solver_times"]
    startup_global_courant = solver_log["startup_global_courant"]
    solver_global_courant = solver_log["solver_global_courant"]
    solver_interface_courant = solver_log["solver_interface_courant"]
    step_diagnostic_groups = solver_log["solver_step_diagnostic_groups"]
    expected_log_time_rows = solver_times
    log_times_complete = (
        solver_log["loop_found"]
        and solver_log["loop_end_found"]
        and len(expected_log_time_rows) == EXPECTED_STEP_COUNT
        and all(
            _time_matches(actual, step * EXPECTED_DELTA_T_S)
            for step, actual in enumerate(expected_log_time_rows, start=1)
        )
    )
    solver_step_diagnostics_complete = (
        len(step_diagnostic_groups) == EXPECTED_STEP_COUNT
        and all(
            group["global_courant_rows"] == 1 and group["interface_courant_rows"] == 1
            for group in step_diagnostic_groups
        )
        and solver_log["unassigned_global_courant_rows"] == 0
        and solver_log["unassigned_interface_courant_rows"] == 0
    )
    courant_rows_complete = (
        solver_log["loop_found"]
        and solver_log["loop_end_found"]
        and len(solver_global_courant) == EXPECTED_STEP_COUNT
        and len(solver_interface_courant) == EXPECTED_STEP_COUNT
        and solver_step_diagnostics_complete
    )
    if not solver_log["loop_found"]:
        issues.append("solver log is missing a unique Starting time loop marker")
    elif not solver_log["loop_end_found"]:
        issues.append("solver log is missing the solver End marker")
    if len(solver_times) != EXPECTED_STEP_COUNT:
        issues.append(
            f"solver loop contains {len(solver_times)} Time rows; expected {EXPECTED_STEP_COUNT}"
        )
    if len(solver_global_courant) != EXPECTED_STEP_COUNT:
        issues.append(
            f"solver loop contains {len(solver_global_courant)} global Co rows; "
            f"expected {EXPECTED_STEP_COUNT}"
        )
    if len(solver_interface_courant) != EXPECTED_STEP_COUNT:
        issues.append(
            f"solver loop contains {len(solver_interface_courant)} interface Co rows; "
            f"expected {EXPECTED_STEP_COUNT}"
        )
    if not solver_step_diagnostics_complete:
        issues.append("solver loop Courant rows are not paired one-for-one with each Time row")
    run_data_complete = data_complete and log_times_complete and courant_rows_complete
    all_global_courant = [*startup_global_courant, *solver_global_courant]
    observed_max_global_courant = max(all_global_courant, default=None)
    observed_max_interface_courant = max(solver_interface_courant, default=None)
    global_courant_check = (
        courant_rows_complete
        and observed_max_global_courant is not None
        and observed_max_global_courant <= PROPOSED_MAX_COURANT
    )
    interface_courant_check = (
        courant_rows_complete
        and observed_max_interface_courant is not None
        and observed_max_interface_courant <= PROPOSED_MAX_INTERFACE_COURANT
    )
    log_end_time_reached = bool(solver_times) and _time_matches(
        solver_times[-1], EXPECTED_END_TIME_S
    )
    cells = [int(value) for value in re.findall(r"^\s*cells:\s*(\d+)\s*$", log_text, re.MULTILINE)]
    observed_mesh_cells = cells[-1] if cells else None
    expected_mesh_cells = inputs.get("mesh_cells_expected")
    try:
        expected_mesh_cells = int(expected_mesh_cells)
    except (TypeError, ValueError):
        expected_mesh_cells = None
    mesh_count_matches = (
        expected_mesh_cells is not None and observed_mesh_cells == expected_mesh_cells
    )
    mesh_check_passed = bool(re.search(r"\bMesh OK\.", log_text))
    final_state_written, final_state_path = _final_state_written(case_dir)
    inventory_end_reached = (
        _sample_at(tables["waterVolume"].samples, EXPECTED_END_TIME_S) is not None
    )
    logged_end_time_reached = log_end_time_reached and inventory_end_reached
    end_time_check = (
        logged_end_time_reached and final_state_written and config_end_time_ok and run_data_complete
    )

    runner_exit_code = manifest.get("exit_code")
    case_command_exit_code = manifest.get("case_command_exit_code")
    stage_records = manifest.get("case_stage_exit_records")
    stage_record_issues: list[str] = []
    if not isinstance(stage_records, list):
        stage_records = []
        stage_record_issues.append("case_stage_exit_records must be a list")
    normalized_stage_records: list[dict[str, Any]] = []
    for record in stage_records:
        if not isinstance(record, dict):
            stage_record_issues.append("case stage exit record must be an object")
            continue
        stage_name = record.get("stage")
        stage_exit_code = record.get("exit_code")
        if (
            not isinstance(stage_name, str)
            or not isinstance(stage_exit_code, int)
            or isinstance(stage_exit_code, bool)
        ):
            stage_record_issues.append("case stage exit record has an invalid stage or exit code")
            continue
        normalized_stage_records.append({"stage": stage_name, "exit_code": stage_exit_code})
    observed_stage_names = [record["stage"] for record in normalized_stage_records]
    valid_stage_prefix = observed_stage_names == list(CASE_STAGE_ORDER[: len(observed_stage_names)])
    if len(observed_stage_names) > len(CASE_STAGE_ORDER) or not valid_stage_prefix:
        stage_record_issues.append("case stage exit records are duplicated or out of order")
    case_stages_complete = observed_stage_names == list(CASE_STAGE_ORDER)
    stage_exit_codes = {record["stage"]: record["exit_code"] for record in normalized_stage_records}
    recorded_interisofoam_exit_code = manifest.get("interisofoam_exit_code")
    recorded_reconstruction_exit_code = manifest.get("reconstruction_exit_code")
    interisofoam_exit_code = (
        recorded_interisofoam_exit_code
        if isinstance(recorded_interisofoam_exit_code, int)
        and not isinstance(recorded_interisofoam_exit_code, bool)
        else None
    )
    reconstruction_exit_code = (
        recorded_reconstruction_exit_code
        if isinstance(recorded_reconstruction_exit_code, int)
        and not isinstance(recorded_reconstruction_exit_code, bool)
        else None
    )
    if interisofoam_exit_code != stage_exit_codes.get("interIsoFoam"):
        stage_record_issues.append(
            "interisofoam_exit_code is missing, invalid, or disagrees with its stage record"
        )
    if reconstruction_exit_code != stage_exit_codes.get("reconstructPar"):
        stage_record_issues.append(
            "reconstruction_exit_code is missing, invalid, or disagrees with its stage record"
        )
    solver_exit_zero = (
        interisofoam_exit_code == 0
        and stage_exit_codes.get("interIsoFoam") == 0
        and observed_stage_names[:4] == list(CASE_STAGE_ORDER[:4])
        and valid_stage_prefix
    )
    case_command_exit_zero = (
        isinstance(case_command_exit_code, int)
        and not isinstance(case_command_exit_code, bool)
        and case_command_exit_code == 0
    )
    case_workflow_exit_zero = (
        case_command_exit_zero
        and case_stages_complete
        and not stage_record_issues
        and all(record["exit_code"] == 0 for record in normalized_stage_records)
    )
    if not case_stages_complete or stage_record_issues:
        issues.extend(stage_record_issues or ["case stage exit records are incomplete"])
    if not case_command_exit_zero:
        issues.append("run manifest must record an explicit zero case_command_exit_code")
    termination_fields = ("stop_reason", "stop_confirmed", "stop_error")
    termination_metadata_present = all(key in manifest for key in termination_fields)
    stop_reason = manifest.get("stop_reason")
    stop_confirmed = manifest.get("stop_confirmed")
    stop_error = manifest.get("stop_error")
    clean_solver_termination = (
        termination_metadata_present
        and stop_reason is None
        and stop_confirmed is None
        and stop_error is None
    )
    if not clean_solver_termination:
        issues.append(
            "run manifest must confirm an uninterrupted solver attempt with no stop reason or stop error"
        )
    execution_manifest = manifest.get("execution")
    execution_manifest = execution_manifest if isinstance(execution_manifest, dict) else {}
    declared_wall_time_limit_s = _as_json_number(execution_manifest.get("wall_time_limit_s"))
    observed_wall_time_s = _as_json_number(manifest.get("wall_time_s"))
    wall_time_limit_matches = declared_wall_time_limit_s == EXPECTED_MAX_WALL_TIME_S
    wall_time_within_limit = (
        observed_wall_time_s is not None and 0.0 <= observed_wall_time_s <= EXPECTED_MAX_WALL_TIME_S
    )
    if not wall_time_limit_matches:
        issues.append("run manifest execution.wall_time_limit_s must equal the frozen 3600 s limit")
    if not wall_time_within_limit:
        issues.append(
            "run manifest wall_time_s must be a finite non-negative value within the frozen 3600 s limit"
        )
    fixed_step_check = config_delta_t_ok and config_end_time_ok and adjust_time_step_disabled
    overall_checks = {
        "source_data_complete": run_data_complete,
        "execution_contract_ready_and_reviewed": execution_review_approved,
        "fixed_step_configuration": fixed_step_check,
        "case_configuration_matches_frozen_P1_protocol": case_protocol["matches_protocol"],
        "source_input_contract": source_input_contract_ok,
        "logged_solver_times_complete": log_times_complete,
        "courant_rows_complete": courant_rows_complete,
        "alphaPhi_left_sampled_and_continuous_source_dose_within_proposed_0p1_percent": source_dose_check,
        "maximum_box_residual_within_proposed_0p1_percent": box_residual_check,
        "global_courant_within_proposed_0p5": global_courant_check,
        "interface_courant_within_proposed_0p25": interface_courant_check,
        "solver_exit_zero": solver_exit_zero,
        "case_workflow_exit_zero": case_workflow_exit_zero,
        "no_hard_stop_or_stop_error": clean_solver_termination,
        "manifest_wall_time_limit_is_frozen_3600_s": wall_time_limit_matches,
        "manifest_wall_time_is_within_limit": wall_time_within_limit,
        "mesh_check_and_cell_count": mesh_check_passed and mesh_count_matches,
        "end_time_and_final_state": end_time_check,
    }
    all_passed = all(overall_checks.values())
    if all_passed:
        gate_status = "pass_provisional_P1_ledger"
    elif not run_data_complete:
        gate_status = "inconclusive_incomplete_data"
    else:
        gate_status = "not_passed_provisional_P1_ledger"

    common_step_durations = [
        end - start for start, end in zip(common_times, common_times[1:]) if end > start
    ]
    return {
        "schema_version": 1,
        "run_id": manifest.get("run_id"),
        "run_bundle": str(run_dir),
        "proposal_status": {
            "status": (
                "protocol_approved_with_revisions"
                if execution_review_approved
                else "protocol_review_not_recorded_or_not_approved"
            ),
            "protocol_revision": inputs.get("protocol_revision"),
            "protocol_amendment_id": inputs.get("protocol_amendment_id"),
            "independent_protocol_review": protocol_review_decision or "not_recorded",
            "protocol_amendment_review": independent_review.get(
                "amendment_1_review_decision", "not_recorded"
            ),
            "protocol_amendment_reviewer": independent_review.get("amendment_1_reviewer"),
            "protocol_amendment_reviewed_utc": independent_review.get("amendment_1_reviewed_utc"),
            "implementation_code_review": execution_code_review or "not_recorded",
            "execution_status": execution_status or "not_recorded",
            "execution_code_reviewer": independent_review.get("execution_code_reviewer"),
            "execution_code_reviewed_utc": independent_review.get("execution_code_reviewed_utc"),
            "source_and_residual_limits_are_frozen_for_execution": True,
        },
        "claim_limit": (
            "A pass applies only to this provisional P1 source-event and box-ledger diagnostic. "
            "It does not pass or substitute for E1-E6, breakup validation, a built-device claim, "
            "or field validation."
        ),
        "expected_contract": {
            "density_kg_m3": WATER_DENSITY_KG_M3,
            "protocol_revision": 2,
            "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
            "alpha_phi_sampling_convention": "left_endpoint_of_completed_interval",
            "alpha_phi_left_sampled_target_source_mass_kg": ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG,
            "alpha_phi_left_sampled_target_mass_per_slot_kg": ALPHAPHI_LEFT_SAMPLED_TARGET_SLOT_MASS_KG,
            "phi_right_sampled_target_source_mass_kg": PHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG,
            "phi_right_sampled_target_mass_per_slot_kg": PHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG,
            "previous_alpha_phi_right_sampled_target_source_mass_kg": PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG,
            "previous_alpha_phi_right_sampled_target_mass_per_slot_kg": PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SLOT_MASS_KG,
            "continuous_analytic_target_source_mass_kg": CONTINUOUS_TARGET_SOURCE_MASS_KG,
            "continuous_analytic_target_mass_per_slot_kg": CONTINUOUS_TARGET_SLOT_MASS_KG,
            "source_dose_relative_tolerance": PROPOSED_RELATIVE_TOLERANCE,
            "residual_to_cumulative_source_relative_tolerance": PROPOSED_RELATIVE_TOLERANCE,
            "max_global_courant": PROPOSED_MAX_COURANT,
            "max_interface_courant": PROPOSED_MAX_INTERFACE_COURANT,
            "delta_t_s": EXPECTED_DELTA_T_S,
            "end_time_s": EXPECTED_END_TIME_S,
            "expected_step_count": EXPECTED_STEP_COUNT,
            "max_wall_time_s": EXPECTED_MAX_WALL_TIME_S,
            "source_ramp_start_s": SOURCE_RAMP_START_S,
            "source_ramp_end_s": SOURCE_RAMP_END_S,
            "expected_ramp_intervals": 10,
        },
        "inputs": {
            "solver": inputs.get("solver"),
            "solver_image": inputs.get("openfoam_image"),
            "declared_end_time_s": declared_end_time_s,
            "declared_delta_t_s": declared_delta_t_s,
            "declared_adjust_time_step": (
                input_adjust_time_step
                if input_adjust_time_step is not None
                else control_adjust_time_step
            ),
            "declared_expected_mass_kg": declared_mass,
            "declared_water_density_kg_m3": declared_density,
            "declared_slot_count": declared_slot_count,
            "expected_mesh_cells": expected_mesh_cells,
        },
        "case_protocol": case_protocol,
        "manifest": {
            "exit_code": runner_exit_code,
            "case_command_exit_code": case_command_exit_code,
            "solver_exit_code": interisofoam_exit_code,
            "interisofoam_exit_code": interisofoam_exit_code,
            "reconstruction_exit_code": reconstruction_exit_code,
            "case_stage_exit_records": normalized_stage_records,
            "runner_exit_code": runner_exit_code,
            "execution_wall_time_limit_s": declared_wall_time_limit_s,
            "wall_time_s": observed_wall_time_s,
            "wall_time_limit_matches_frozen": wall_time_limit_matches,
            "wall_time_within_limit": wall_time_within_limit,
            "solver_image": manifest.get("solver_image"),
            "solver_image_id": manifest.get("solver_image_id"),
            "stop_reason": stop_reason,
            "stop_confirmed": stop_confirmed,
            "stop_error": stop_error,
            "termination_metadata_present": termination_metadata_present,
            "clean_solver_termination": clean_solver_termination,
        },
        "data_completeness": {
            "complete": run_data_complete,
            "diagnostic_series_complete": data_complete,
            "solver_log_times_complete": log_times_complete,
            "courant_rows_complete": courant_rows_complete,
            "solver_loop_found": solver_log["loop_found"],
            "solver_loop_end_found": solver_log["loop_end_found"],
            "solver_step_diagnostics_paired_with_times": solver_step_diagnostics_complete,
            "series": series_checks,
            "common_sample_count": len(common_times),
            "common_expected_positive_step_count": common_expected_count,
            "first_common_time_s": common_times[0] if common_times else None,
            "last_common_time_s": common_times[-1] if common_times else None,
            "min_common_step_duration_s": min(common_step_durations, default=None),
            "max_common_step_duration_s": max(common_step_durations, default=None),
            "source_ramp_interval_count": ramp_interval_count,
            "source_ramp_intervals_complete": ramp_interval_count == 10,
        },
        "ledger": {
            "integration_method": (
                "Each recorded flux is multiplied by the actual interval duration ending at its "
                "logged time. alphaPhi_ represents phase transport for the completed interval "
                "[t_(n-1), t_n] and is checked against the frozen left-endpoint source sum; phi "
                "is reported against the right-endpoint source sum."
            ),
            "source_sign_convention": "slot inlet flux is inward-negative; delivered mass is -rho times integrated alphaPhi_",
            "open_patch_sign_convention": "outward-positive; signed net outflow includes airInlet, airOutlet, and lowerOutlet",
            "samples": ledger_samples,
            "final_sample": final_sample,
            "source_dose": {
                "protocol_revision": 2,
                "alphaPhi_left_sampled_target_total_kg": ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG,
                "phi_right_sampled_target_total_kg": PHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG,
                "previous_alphaPhi_right_sampled_target_total_kg": PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG,
                "continuous_analytic_target_total_kg": CONTINUOUS_TARGET_SOURCE_MASS_KG,
                "observed_total_kg": final_source_mass_kg,
                "absolute_error_to_alphaPhi_left_sampled_target_kg": source_total_left_error,
                "relative_error_to_alphaPhi_left_sampled_target": _relative_error(
                    final_source_mass_kg, ALPHAPHI_LEFT_SAMPLED_TARGET_SOURCE_MASS_KG
                ),
                "relative_error_to_previous_alphaPhi_right_sampled_target": _relative_error(
                    final_source_mass_kg,
                    PREVIOUS_ALPHAPHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG,
                ),
                "relative_error_to_phi_right_sampled_target": _relative_error(
                    final_source_mass_kg, PHI_RIGHT_SAMPLED_TARGET_SOURCE_MASS_KG
                ),
                "relative_error_to_continuous_target": _relative_error(
                    final_source_mass_kg, CONTINUOUS_TARGET_SOURCE_MASS_KG
                ),
                "numerically_within_alphaPhi_left_sampled_target_0p1_percent": numerical_source_dose_left_check,
                "numerically_within_continuous_target_0p1_percent": numerical_source_dose_continuous_check,
                "eligible_under_current_protocol_revision": source_dose_protocol_eligible,
                "per_slot": slot_doses,
                "within_alphaPhi_left_sampled_target_0p1_percent": source_dose_left_check,
                "within_continuous_target_0p1_percent": source_dose_continuous_check,
                "within_proposed_0p1_percent": source_dose_check,
            },
            "phi_vs_alphaPhi_inlet_cross_check": {
                "per_slot": inlet_cross_check,
                "interpretation": "informational signed-volume comparison; no separate tolerance is proposed",
            },
            "open_patch_outflow": {
                "patches": list(OPEN_PATCHES),
                "signed_net_liquid_volume_m3": (
                    final_sample["signed_net_open_patch_outflow_m3"] if final_sample else None
                ),
                "signed_net_mass_kg": (
                    final_sample["signed_net_open_patch_outflow_kg"] if final_sample else None
                ),
            },
            "inventory": {
                "volume_m3": final_sample["box_inventory_m3"] if final_sample else None,
                "mass_kg": final_sample["box_inventory_kg"] if final_sample else None,
                "density_kg_m3": WATER_DENSITY_KG_M3,
            },
            "residual": {
                "definition": "M_source - M_escape - M_box",
                "final_signed_kg": final_residual_kg,
                "max_absolute_kg": max_abs_residual_kg,
                "max_absolute_percent_of_continuous_target": (
                    100 * max_abs_residual_kg / CONTINUOUS_TARGET_SOURCE_MASS_KG
                    if max_abs_residual_kg is not None
                    else None
                ),
                "max_absolute_relative_to_cumulative_measured_source": max_relative_residual,
                "max_absolute_relative_sample_time_s": (
                    max_relative_residual_sample["time_s"]
                    if max_relative_residual_sample is not None
                    else None
                ),
                "cumulative_source_ratio_limit": PROPOSED_RELATIVE_TOLERANCE,
                "max_final_sample_limit_kg": (
                    PROPOSED_RELATIVE_TOLERANCE * final_source_mass_kg
                    if final_source_mass_kg is not None
                    else None
                ),
                "within_proposed_0p1_percent": box_residual_check,
                "interpretation": (
                    "At every positive cumulative measured-source sample, abs(residual) is "
                    "normalized by that sample's cumulative measured M_source. Alpha clipping "
                    "and interface-snapping corrections are not reported separately and remain "
                    "included in this residual."
                ),
            },
            "alpha_clipping_and_interface_snap": {
                "separate_correction_diagnostics_available": False,
                "interpretation": (
                    "No separate clipping/snap correction diagnostic was available in the "
                    "analyzed run files; their effects remain included in the ledger residual."
                ),
            },
        },
        "solver_checks": {
            "solver_loop_time_count": len(solver_times),
            "solver_step_diagnostic_group_count": len(step_diagnostic_groups),
            "logged_times_complete": log_times_complete,
            "last_solver_time_s": solver_times[-1] if solver_times else None,
            "log_reached_0p12_s": log_end_time_reached,
            "solver_loop_global_courant_sample_count": len(solver_global_courant),
            "unassigned_global_courant_rows": solver_log["unassigned_global_courant_rows"],
            "startup_global_courant_sample_count": len(startup_global_courant),
            "global_courant_sample_count_including_startup": len(all_global_courant),
            "observed_max_global_courant": observed_max_global_courant,
            "global_courant_limit": PROPOSED_MAX_COURANT,
            "global_courant_within_limit": global_courant_check,
            "interface_courant_sample_count": len(solver_interface_courant),
            "unassigned_interface_courant_rows": solver_log["unassigned_interface_courant_rows"],
            "observed_max_interface_courant": observed_max_interface_courant,
            "interface_courant_limit": PROPOSED_MAX_INTERFACE_COURANT,
            "interface_courant_within_limit": interface_courant_check,
            "trailing_reconstruction_time_count_ignored": len(solver_log.get("trailing_times", [])),
            "trailing_reconstruction_times_s_ignored": solver_log.get("trailing_times", []),
            "mesh_cells_observed": observed_mesh_cells,
            "mesh_cells_expected": expected_mesh_cells,
            "mesh_cell_count_matches": mesh_count_matches,
            "mesh_check_passed": mesh_check_passed,
            "final_state_written": final_state_written,
            "final_state_path": final_state_path,
            "solver_exit_code": interisofoam_exit_code,
            "solver_exit_zero": solver_exit_zero,
            "case_command_exit_code": case_command_exit_code,
            "case_command_exit_zero": case_command_exit_zero,
            "case_stage_exit_records_complete": case_stages_complete,
            "case_workflow_exit_zero": case_workflow_exit_zero,
        },
        "checks": overall_checks,
        "gate_status": gate_status,
        "gate_decision": {
            "p1_ledger_passed": gate_status == "pass_provisional_P1_ledger",
            "status": gate_status,
            "scope": "provisional P1 source-event and box-ledger diagnostic only",
            "e1_e6_passed": False,
        },
        "issues": issues,
    }


def build_ledger_report(run_dir: Path) -> dict[str, Any]:
    """Compatibility entry point used by the P1 pilot runner."""
    return build_report(run_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="one immutable P1 run bundle")
    parser.add_argument(
        "--output",
        type=Path,
        help="write the JSON ledger report here (default: RUN_DIR/source-event-ledger-report.json)",
    )
    args = parser.parse_args(argv)
    report = build_report(args.run_dir)
    output_path = args.output or args.run_dir / "source-event-ledger-report.json"
    try:
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as error:
        parser.error(f"cannot write ledger report to {output_path}: {error}")
    print(f"P1 ledger status: {report['gate_status']}")
    print(f"Report: {output_path}")
    return 0 if report["gate_status"] == "pass_provisional_P1_ledger" else 1


if __name__ == "__main__":
    raise SystemExit(main())
