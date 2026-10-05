#!/usr/bin/env python3
"""Audit the supported fixed-mesh Dash-8 interIsoFoam water ledger.

This is an exploratory diagnostic, not a conservation gate. ``alphaPhi_`` is
treated as the interval-mean volumetric flux for one completed alpha step, so
each recorded flux is integrated with its paired native solver ``deltaT``.
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
from typing import Any, Iterable

PINNED_IMAGE = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
KNOWN_SOLVER_SOURCE_HASHES = {
    "isoAdvectionTemplates.C": "1d704aec280cffa4302f75cc3e15654db25dc75c6d1cb9e230ab8a4be64f1e90",
    "interIsoFoam_alphaEqnSubCycle.H": "b5f9845d57cb3fc75577ef00ed338186f83d13a9261c67d4ef88e6f1ef419385",
    "interIsoFoam_alphaEqn.H": "cbb4348977388633b29f0aa1f612225249c3062e80755f548fddfb0760c7311f",
    "isoAdvection.H": "505239083111afb87204f76ec9c3d722eaa9c47f5ee5d44b6f2e0e0e762d0ce7",
}
SOURCE_COPY_KEY_ALIASES = {
    "interIsoFoam_alphaEqnSubCycle.H": "alphaEqnSubCycle.H",
    "interIsoFoam_alphaEqn.H": "alphaEqn.H",
}
SOURCE_PATCH = "dash8Opening"
OPEN_PATCHES = ("airInlet", "xOutlet", "yMin", "yMax", "zMin")
SERIES_FILES = {
    "waterVolume": ("waterVolume", "volFieldValue", 1, "volintegrate(alpha.water)"),
    SOURCE_PATCH: (f"{SOURCE_PATCH}Flux", "surfaceFieldValue", 2, "sum(alphaphi_)"),
    **{patch: (f"{patch}Flux", "surfaceFieldValue", 2, "sum(alphaphi_)") for patch in OPEN_PATCHES},
}
RHO_EPS = 1.0e-12


class AuditError(ValueError):
    """Raised when input data are incomplete, inconsistent, or unsupported."""


@dataclass(frozen=True)
class DataRow:
    token: str
    time_s: float
    values: tuple[float, ...]
    path: Path
    line_number: int


@dataclass(frozen=True)
class ParsedTable:
    rows: tuple[DataRow, ...]
    files: tuple[Path, ...]
    trailing_partial_rows: int
    complete_rows_total: int
    excluded_after_cutoff: int
    file_sha256: dict[Path, str]
    file_byte_lengths: dict[Path, int]


@dataclass(frozen=True)
class LogRow:
    token: str
    time_s: float
    delta_t_s: float
    delta_t_token: str
    line_number: int


@dataclass(frozen=True)
class ParsedLog:
    rows: tuple[LogRow, ...]
    trailing_unpaired_delta_t_s: float | None
    complete_rows_total: int
    file_sha256: str
    file_byte_length: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuditError(f"expected a JSON object in {path}")
    return data


def _find_case_root(run_dir: Path) -> Path:
    if (run_dir / "postProcessing").is_dir():
        return run_dir
    if (run_dir / "case" / "postProcessing").is_dir():
        return run_dir / "case"
    raise AuditError(f"no postProcessing directory in {run_dir} or {run_dir / 'case'}")


def _config_path(
    case_root: Path, relative_system_path: str, snapshot_name: str | None = None
) -> Path:
    normal = case_root / relative_system_path
    if normal.is_file():
        return normal
    if snapshot_name is not None:
        snapshot = case_root / snapshot_name
        if snapshot.is_file():
            return snapshot
    raise AuditError(f"required case configuration is missing: {normal}")


def _strip_foam_comments(text: str) -> str:
    """Mask comments and OpenFOAM embedded code before parsing dictionaries.

    C++ code blocks use ``#{ ... #}`` and may contain balanced braces of their
    own. Masking them before the dictionary parsers run keeps C++ scopes and
    comments from changing the apparent OpenFOAM dictionary structure.
    """

    chars = list(text)

    def mask(start: int, stop: int) -> None:
        for position in range(start, stop):
            if chars[position] != "\n":
                chars[position] = " "

    index = 0
    while index < len(text):
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            if end == -1:
                end = len(text)
            mask(index, end)
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                end = len(text)
            else:
                end += 2
            mask(index, end)
            index = end
            continue
        if text[index] in {"'", '"'}:
            quote = text[index]
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                elif text[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            continue
        if text.startswith("#{", index):
            code_start = index
            index += 2
            while index < len(text):
                if text.startswith("//", index):
                    end = text.find("\n", index + 2)
                    index = len(text) if end == -1 else end
                    continue
                if text.startswith("/*", index):
                    end = text.find("*/", index + 2)
                    index = len(text) if end == -1 else end + 2
                    continue
                if text[index] in {"'", '"'}:
                    quote = text[index]
                    index += 1
                    while index < len(text):
                        if text[index] == "\\":
                            index += 2
                        elif text[index] == quote:
                            index += 1
                            break
                        else:
                            index += 1
                    continue
                if text.startswith("#}", index):
                    index += 2
                    mask(code_start, index)
                    break
                index += 1
            else:
                raise AuditError(
                    "unterminated OpenFOAM code block starting with '#{' (missing '#}')"
                )
            continue
        index += 1
    return "".join(chars)


def _single_int(text: str, key: str, path: Path) -> int:
    matches = re.findall(rf"\b{re.escape(key)}\s+([+-]?\d+)\s*;", _strip_foam_comments(text))
    if len(matches) != 1:
        raise AuditError(f"expected exactly one {key} declaration in {path}; found {len(matches)}")
    return int(matches[0])


def _single_float(text: str, key: str, path: Path) -> float:
    matches = re.findall(
        rf"\b{re.escape(key)}\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*;",
        _strip_foam_comments(text),
    )
    if len(matches) != 1:
        raise AuditError(f"expected exactly one {key} declaration in {path}; found {len(matches)}")
    value = float(matches[0])
    if not math.isfinite(value):
        raise AuditError(f"non-finite {key} declaration in {path}")
    return value


def _water_density(transport_path: Path, case_inputs: dict[str, Any]) -> float:
    text = _strip_foam_comments(transport_path.read_text(encoding="utf-8", errors="replace"))
    matches = re.findall(r"\bwater\s*\{([^{}]*)\}", text, flags=re.DOTALL)
    if len(matches) != 1:
        raise AuditError(f"expected one water dictionary in {transport_path}")
    densities = re.findall(
        r"\brho\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*;",
        matches[0],
    )
    if len(densities) != 1:
        raise AuditError(f"expected one constant water rho in {transport_path}")
    rho = float(densities[0])
    if not math.isfinite(rho) or rho <= 0:
        raise AuditError(f"water density must be finite and positive in {transport_path}")

    props = case_inputs.get("fluid_properties", {}).get("water", {})
    if isinstance(props, dict) and "rho_kg_m3" in props:
        declared = float(props["rho_kg_m3"])
        if not math.isfinite(declared) or not math.isclose(
            rho, declared, rel_tol=0.0, abs_tol=RHO_EPS
        ):
            raise AuditError(
                f"case-inputs water density {declared} disagrees with transportProperties {rho}"
            )
    return rho


def _foam_named_blocks(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"\b([A-Za-z_][\w.]*)\s*\{([^{}]*)\}", _strip_foam_comments(text))
    }


def _function_object_bindings(control_text: str) -> dict[str, dict[str, Any]]:
    """Verify that each output directory is bound to the intended patch/field."""
    blocks = _foam_named_blocks(control_text)
    expected: dict[str, tuple[str, str | None, str, tuple[str, ...]]] = {
        "waterVolume": ("volFieldValue", None, "volIntegrate", ("alpha.water",)),
        **{
            f"{patch}Flux": ("surfaceFieldValue", patch, "sum", ("phi", "alphaPhi_"))
            for patch in (SOURCE_PATCH, *OPEN_PATCHES)
        },
    }
    result: dict[str, dict[str, Any]] = {}
    for object_name, (
        expected_type,
        expected_patch,
        expected_operation,
        expected_fields,
    ) in expected.items():
        body = blocks.get(object_name)
        if body is None:
            raise AuditError(f"controlDict function object {object_name} is missing")
        type_values = re.findall(r"\btype\s+(\w+)\s*;", body)
        operation_values = re.findall(r"\boperation\s+(\w+)\s*;", body)
        field_values = re.findall(r"\bfields\s*\(([^)]*)\)\s*;", body)
        if type_values != [expected_type] or operation_values != [expected_operation]:
            raise AuditError(
                f"controlDict function object {object_name} has unexpected type/operation: "
                f"{type_values}/{operation_values}"
            )
        if len(field_values) != 1 or tuple(field_values[0].split()) != expected_fields:
            raise AuditError(
                f"controlDict function object {object_name} must report fields {expected_fields}; "
                f"got {field_values}"
            )
        binding: dict[str, Any] = {
            "type": type_values[0],
            "operation": operation_values[0],
            "fields": list(expected_fields),
        }
        if expected_patch is not None:
            region_types = re.findall(r"\bregionType\s+(\w+)\s*;", body)
            patch_names = re.findall(r"\bname\s+(\w+)\s*;", body)
            if region_types != ["patch"] or patch_names != [expected_patch]:
                raise AuditError(
                    f"controlDict function object {object_name} must bind to patch "
                    f"{expected_patch}; got regionType/name {region_types}/{patch_names}"
                )
            binding["regionType"] = region_types[0]
            binding["patch"] = patch_names[0]
        for key, value in (
            ("executeControl", "timeStep"),
            ("executeInterval", "1"),
            ("writeControl", "timeStep"),
            ("writeInterval", "1"),
        ):
            values = re.findall(rf"\b{key}\s+([^;]+)\s*;", body)
            if values != [value]:
                raise AuditError(
                    f"controlDict function object {object_name} requires {key} {value}; got {values}"
                )
        result[object_name] = binding
    return result


def _verify_boundary_inventory(case_root: Path, case_inputs: dict[str, Any]) -> dict[str, Any]:
    boundary_path = case_root / "constant" / "polyMesh" / "boundary"
    velocity_path = case_root / "0" / "U"
    if not boundary_path.is_file() or not velocity_path.is_file():
        raise AuditError(
            "mesh boundary and initial U dictionaries are required to verify ledger patches"
        )
    boundary_blocks = _foam_named_blocks(
        boundary_path.read_text(encoding="utf-8", errors="replace")
    )
    boundary_types = {
        name: match.group(1)
        for name, body in boundary_blocks.items()
        if name != "FoamFile"
        if (match := re.search(r"\btype\s+(\w+)\s*;", body)) is not None
    }
    if not boundary_types:
        raise AuditError(f"no mesh patch types parsed from {boundary_path}")

    velocity_text = _strip_foam_comments(
        velocity_path.read_text(encoding="utf-8", errors="replace")
    )
    boundary_field = re.search(r"\bboundaryField\s*\{", velocity_text)
    if boundary_field is None:
        raise AuditError(f"boundaryField is missing from {velocity_path}")
    open_index = velocity_text.find("{", boundary_field.start())
    depth = 0
    close_index = None
    for index in range(open_index, len(velocity_text)):
        if velocity_text[index] == "{":
            depth += 1
        elif velocity_text[index] == "}":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index is None:
        raise AuditError(f"unterminated boundaryField in {velocity_path}")
    velocity_blocks = _foam_named_blocks(velocity_text[open_index + 1 : close_index])
    velocity_types = {
        name: match.group(1)
        for name, body in velocity_blocks.items()
        if (match := re.search(r"\btype\s+(\w+)\s*;", body)) is not None
    }

    declared_sources = case_inputs.get("source_patches")
    declared_open = case_inputs.get("open_patches")
    if declared_sources != [SOURCE_PATCH] or declared_open != list(OPEN_PATCHES):
        raise AuditError(
            "supported audit requires the declared Dash-8 source/open patch inventory "
            f"{[SOURCE_PATCH]} + {list(OPEN_PATCHES)}"
        )
    accounted = {SOURCE_PATCH, *OPEN_PATCHES}
    actual = set(boundary_types)
    missing = accounted - actual
    if missing:
        raise AuditError(
            f"ledger source/open patches are absent from mesh boundary: {sorted(missing)}"
        )
    wrong_flux_patch_type = {
        name: boundary_types[name] for name in accounted if boundary_types[name] != "patch"
    }
    if wrong_flux_patch_type:
        raise AuditError(
            f"source/open ledger patches must be mesh type patch: {wrong_flux_patch_type}"
        )
    omitted = actual - accounted
    nonwall = {name: boundary_types[name] for name in omitted if boundary_types[name] != "wall"}
    if nonwall:
        raise AuditError(f"unledgered non-wall mesh patches would invalidate closure: {nonwall}")
    missing_u = actual - set(velocity_types)
    if missing_u:
        raise AuditError(f"U boundary conditions are missing for mesh patches: {sorted(missing_u)}")
    permeable_u = {
        name: velocity_types[name]
        for name in omitted
        if velocity_types[name] not in {"slip", "noSlip"}
    }
    if permeable_u:
        raise AuditError(
            f"unledgered wall patch lacks verified impermeable U condition: {permeable_u}"
        )
    return {
        "mesh_boundary_types": boundary_types,
        "velocity_boundary_types": velocity_types,
        "ledger_source_patch": SOURCE_PATCH,
        "ledger_open_patches": list(OPEN_PATCHES),
        "omitted_boundaries_verified_impermeable_walls": sorted(omitted),
        "mesh_boundary_file": str(boundary_path),
        "velocity_boundary_file": str(velocity_path),
    }


def _initial_zero_water(case_root: Path) -> tuple[float, Path]:
    candidates = (case_root / "0" / "alpha.water", case_root / "initial" / "alpha.water")
    path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not path.is_file():
        raise AuditError(f"initial water field is missing: {path}")
    text = _strip_foam_comments(path.read_text(encoding="utf-8", errors="replace"))
    match = re.search(
        r"\binternalField\s+uniform\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*;",
        text,
    )
    if match is None:
        raise AuditError("supported audit requires internalField uniform 0 in initial alpha.water")
    alpha = float(match.group(1))
    if not math.isfinite(alpha) or not math.isclose(alpha, 0.0, rel_tol=0.0, abs_tol=RHO_EPS):
        raise AuditError("supported audit requires initially water-free internalField uniform 0")
    return 0.0, path


def _walk_true_flags(value: Any, keys: set[str], path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key.lower() in keys and child not in (
                False,
                None,
                0,
                "",
                "false",
                "False",
                "off",
                "no",
            ):
                found.append(child_path)
            found.extend(_walk_true_flags(child, keys, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_true_flags(child, keys, f"{path}[{index}]"))
    return found


UNSUPPORTED_FLAGS = {
    "phase_change",
    "phasechange",
    "phase_change_enabled",
    "moving_mesh",
    "dynamic_mesh",
    "porosity",
    "porous",
    "porosity_enabled",
    "internal_mass_source",
    "mass_source",
    "volume_source",
    "fvoptions",
    "fvmodels",
}
UNSUPPORTED_PATTERN = re.compile(
    r"\b(phaseChange|porosity|porousZone|fvOptions|fvModels|"
    r"semiImplicitSource|codedSource|massSource|volumeSource|massTransferModel)\b",
    flags=re.IGNORECASE,
)

_FOAM_OPTION_TOKEN = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{}();]|[^\s{}();]+""")


def _strip_foam_comments_preserving_tokens(text: str) -> str:
    """Mask comments while leaving directives and embedded code detectable."""
    chars = list(text)
    index = 0

    def mask(start: int, stop: int) -> None:
        for position in range(start, stop):
            if chars[position] != "\n":
                chars[position] = " "

    while index < len(text):
        if text[index] in {"'", '"'}:
            quote = text[index]
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                elif text[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
            mask(index, end)
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise AuditError("unterminated block comment in fvOptions")
            end += 2
            mask(index, end)
            index = end
            continue
        index += 1
    return "".join(chars)


class _FoamDictionaryParser:
    """Small strict parser for the scalar/nested-dictionary fvOptions subset."""

    def __init__(self, text: str, path: Path):
        commentless = _strip_foam_comments_preserving_tokens(text)
        if re.search(r"[#\$]", commentless):
            raise AuditError(f"preprocessor directives, macros, and code are unsupported in {path}")
        # Preserve the shared OpenFOAM comment/code lexer as the canonical input
        # cleanup after the special fvOptions safety check above.
        clean = _strip_foam_comments(text)
        self.tokens: list[str] = []
        index = 0
        while index < len(clean):
            if clean[index].isspace():
                index += 1
                continue
            match = _FOAM_OPTION_TOKEN.match(clean, index)
            if match is None:
                raise AuditError(f"invalid fvOptions token at byte {index} in {path}")
            self.tokens.append(match.group())
            index = match.end()
        self.path = path
        self.index = 0

    def _peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise AuditError(f"unexpected end of fvOptions dictionary in {self.path}")
        self.index += 1
        return token

    def _parse_block(self, *, closing_brace: bool) -> dict[str, Any]:
        entries: dict[str, Any] = {}
        while True:
            token = self._peek()
            if token is None:
                if closing_brace:
                    raise AuditError(f"unterminated dictionary block in {self.path}")
                return entries
            if token == "}":
                if not closing_brace:
                    raise AuditError(f"unexpected closing brace in {self.path}")
                self._take()
                return entries
            if token in {"{", "(", ")", ";"}:
                raise AuditError(
                    f"unexpected token {token!r} where a dictionary key was expected in {self.path}"
                )
            key = self._take()
            if key in entries:
                raise AuditError(f"duplicate fvOptions dictionary token {key!r} in {self.path}")
            if self._peek() == "{":
                self._take()
                value: Any = self._parse_block(closing_brace=True)
                if self._peek() == ";":
                    self._take()
                entries[key] = value
                continue

            values: list[str] = []
            parentheses = 0
            while True:
                value_token = self._peek()
                if value_token is None:
                    raise AuditError(f"missing semicolon after {key!r} in {self.path}")
                if value_token == ";" and parentheses == 0:
                    self._take()
                    break
                if value_token in {"{", "}"}:
                    raise AuditError(f"malformed value for {key!r} in {self.path}")
                value_token = self._take()
                if value_token == "(":
                    parentheses += 1
                elif value_token == ")":
                    parentheses -= 1
                    if parentheses < 0:
                        raise AuditError(f"unbalanced parentheses for {key!r} in {self.path}")
                values.append(value_token)
            if parentheses != 0 or not values:
                raise AuditError(f"malformed value for {key!r} in {self.path}")
            entries[key] = tuple(values)

    def parse(self) -> dict[str, Any]:
        result = self._parse_block(closing_brace=False)
        if self.index != len(self.tokens):
            raise AuditError(f"trailing tokens after fvOptions dictionary in {self.path}")
        return result


def _foam_scalar(value: Any, key: str, path: Path) -> str:
    if not isinstance(value, tuple) or len(value) != 1:
        raise AuditError(f"fvOptions {key} must be exactly one scalar token in {path}")
    token = value[0]
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
        return token[1:-1]
    return token


def _require_exact_keys(
    dictionary: dict[str, Any], expected: set[str], description: str, path: Path
) -> None:
    found = set(dictionary)
    if found != expected:
        missing, extra = sorted(expected - found), sorted(found - expected)
        raise AuditError(
            f"unsupported {description} schema in {path}; missing keys {missing}, extra keys {extra}"
        )


def _foam_vector(value: Any, key: str, path: Path) -> list[float]:
    if not isinstance(value, tuple) or len(value) != 5 or value[0] != "(" or value[-1] != ")":
        raise AuditError(f"fvOptions {key} must be a 3-component vector in {path}")
    try:
        vector = [float(token) for token in value[1:-1]]
    except ValueError as exc:
        raise AuditError(f"fvOptions {key} has nonnumeric coordinates in {path}") from exc
    if not all(math.isfinite(component) for component in vector):
        raise AuditError(f"fvOptions {key} coordinates must be finite in {path}")
    return vector


def _parse_turbulent_viscosity_limiter(path: Path) -> dict[str, Any] | None:
    """Accept only one active nut cap selected by one geometric box."""
    if path.is_symlink():
        raise AuditError(f"fvOptions must not be a symbolic link: {path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise AuditError(f"fvOptions must be a regular dictionary file: {path}")
    raw = path.read_text(encoding="utf-8", errors="replace")
    entries = _FoamDictionaryParser(raw, path).parse()
    foam_header = entries.pop("FoamFile", None)
    if not isinstance(foam_header, dict):
        raise AuditError(f"fvOptions requires a standard FoamFile header dictionary in {path}")
    header_keys = set(foam_header)
    required_header = {"version", "format", "class", "object"}
    if not required_header <= header_keys or header_keys - required_header - {"location"}:
        raise AuditError(f"unsupported FoamFile header schema in {path}")
    try:
        version = float(_foam_scalar(foam_header["version"], "FoamFile version", path))
    except ValueError as exc:
        raise AuditError(f"invalid FoamFile version in {path}") from exc
    if not math.isfinite(version) or version != 2.0:
        raise AuditError(f"fvOptions FoamFile version must be 2.0 in {path}")
    for key, expected in (
        ("format", "ascii"),
        ("class", "dictionary"),
        ("object", "fvOptions"),
    ):
        if _foam_scalar(foam_header[key], f"FoamFile {key}", path) != expected:
            raise AuditError(f"unexpected FoamFile {key} in {path}; expected {expected}")
    if (
        "location" in foam_header
        and _foam_scalar(foam_header["location"], "FoamFile location", path) != "constant"
    ):
        raise AuditError(f"unexpected FoamFile location in {path}")

    if len(entries) != 1:
        raise AuditError(
            f"fvOptions must contain exactly one active limitTurbulenceViscosity option in {path}; "
            f"found {len(entries)} option entries"
        )
    option_name, option = next(iter(entries.items()))
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", option_name) is None:
        raise AuditError(f"invalid fvOptions entry identifier {option_name!r} in {path}")
    if not isinstance(option, dict):
        raise AuditError(f"fvOptions entry {option_name} must be a dictionary in {path}")
    expected_option_keys = {"type", "active", "log", "limitTurbulenceViscosityCoeffs"}
    _require_exact_keys(option, expected_option_keys, "limitTurbulenceViscosity option", path)
    for key, expected in (
        ("type", "limitTurbulenceViscosity"),
        ("active", "yes"),
        ("log", "yes"),
    ):
        if _foam_scalar(option[key], key, path) != expected:
            raise AuditError(f"limitTurbulenceViscosity requires {key} {expected} in {path}")
    coeffs = option["limitTurbulenceViscosityCoeffs"]
    if not isinstance(coeffs, dict):
        raise AuditError(f"limitTurbulenceViscosityCoeffs must be a dictionary in {path}")
    _require_exact_keys(
        coeffs,
        {"selectionMode", "updateSelection", "selection", "nut", "c"},
        "limitTurbulenceViscosityCoeffs",
        path,
    )
    if _foam_scalar(coeffs["selectionMode"], "selectionMode", path) != "geometric":
        raise AuditError(f"limitTurbulenceViscosity requires selectionMode geometric in {path}")
    if _foam_scalar(coeffs["updateSelection"], "updateSelection", path) != "false":
        raise AuditError(f"limitTurbulenceViscosity requires updateSelection false in {path}")
    if _foam_scalar(coeffs["nut"], "nut", path) != "nut":
        raise AuditError(f"limitTurbulenceViscosity requires nut nut in {path}")
    try:
        coefficient = float(_foam_scalar(coeffs["c"], "c", path))
    except ValueError as exc:
        raise AuditError(
            f"limitTurbulenceViscosity coefficient c must be numeric in {path}"
        ) from exc
    if not math.isfinite(coefficient) or coefficient <= 0:
        raise AuditError(
            f"limitTurbulenceViscosity coefficient c must be finite and positive in {path}"
        )

    selection = coeffs["selection"]
    if not isinstance(selection, dict) or len(selection) != 1:
        raise AuditError(
            f"limitTurbulenceViscosity requires exactly one geometric box selection in {path}"
        )
    box_name, box = next(iter(selection.items()))
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", box_name) is None:
        raise AuditError(f"invalid geometric box selection identifier {box_name!r} in {path}")
    if not isinstance(box, dict):
        raise AuditError(
            f"limitTurbulenceViscosity selection {box_name} must be a dictionary in {path}"
        )
    _require_exact_keys(box, {"action", "source", "min", "max"}, "geometric box selection", path)
    for key, expected in (("action", "use"), ("source", "box")):
        if _foam_scalar(box[key], key, path) != expected:
            raise AuditError(f"geometric selection requires {key} {expected} in {path}")
    minimum = _foam_vector(box["min"], "selection min", path)
    maximum = _foam_vector(box["max"], "selection max", path)
    if any(upper <= lower for lower, upper in zip(minimum, maximum, strict=True)):
        raise AuditError(f"geometric selection box min must be below max on every axis in {path}")
    return {
        "active": True,
        "status": "verified_allowlisted_option",
        "option_name": option_name,
        "type": "limitTurbulenceViscosity",
        "coefficient_c": coefficient,
        "corrected_field": "nut",
        "selection_mode": "geometric",
        "selection_name": box_name,
        "selection_action": "use",
        "selection_source": "box",
        "box_min_m": minimum,
        "box_max_m": maximum,
        "update_selection": False,
        "logging_enabled": True,
        "source_effect_summary": (
            "Pinned v2512 source review finds the geometric option corrects selected internal nut only, "
            "with no direct alpha/mass source. The ledger still evaluates the resulting waterVolume "
            "and alphaPhi_ patch records; it does not assume the flow or fluxes are unchanged."
        ),
        "dictionary_path": str(path),
        "dictionary_sha256": sha256_file(path),
    }


def _check_supported_configuration(
    case_root: Path,
    case_inputs: dict[str, Any],
    control_path: Path,
    fvsolution_path: Path,
    transport_path: Path,
) -> dict[str, Any]:
    solver = str(case_inputs.get("solver", ""))
    if solver != "interIsoFoam":
        raise AuditError(f"only interIsoFoam is supported; case declares {solver!r}")

    control_text = _strip_foam_comments(control_path.read_text(encoding="utf-8", errors="replace"))
    application = re.findall(r"\bapplication\s+(\w+)\s*;", control_text)
    if application != ["interIsoFoam"]:
        raise AuditError(f"controlDict must declare application interIsoFoam: {application}")
    function_object_bindings = _function_object_bindings(control_text)
    fvsolution_text = fvsolution_path.read_text(encoding="utf-8", errors="replace")
    for path, text in (
        (control_path, control_text),
        (fvsolution_path, _strip_foam_comments(fvsolution_text)),
        (
            transport_path,
            _strip_foam_comments(transport_path.read_text(encoding="utf-8", errors="replace")),
        ),
    ):
        if UNSUPPORTED_PATTERN.search(text):
            raise AuditError(f"unsupported source/phase-change/porosity declaration in {path}")
    subcycles = _single_int(fvsolution_text, "nAlphaSubCycles", fvsolution_path)
    if subcycles != 1:
        raise AuditError(f"unsupported nAlphaSubCycles={subcycles}; only 1 is verified")
    outer = _single_int(fvsolution_text, "nOuterCorrectors", fvsolution_path)
    if outer != 1:
        raise AuditError(f"unsupported nOuterCorrectors={outer}; only 1 is verified")

    dynamic_path = case_root / "constant" / "dynamicMeshDict"
    if dynamic_path.exists():
        dynamic_text = _strip_foam_comments(
            dynamic_path.read_text(encoding="utf-8", errors="replace")
        )
        dynamic_types = re.findall(r"\bdynamicFvMesh\s+(\w+)\s*;", dynamic_text)
        if dynamic_types != ["staticFvMesh"]:
            raise AuditError(
                "moving or undeclared dynamic mesh is unsupported; "
                f"dynamicFvMesh declarations: {dynamic_types}"
            )
    flagged = _walk_true_flags(case_inputs, UNSUPPORTED_FLAGS)
    if flagged:
        raise AuditError(f"case-inputs declares unsupported physics/configuration: {flagged}")

    inspected: list[Path] = [control_path, fvsolution_path, transport_path]
    fvoptions_path = case_root / "constant" / "fvOptions"
    if fvoptions_path.is_symlink():
        raise AuditError(f"fvOptions must not be a symbolic link: {fvoptions_path}")
    if fvoptions_path.exists() and not fvoptions_path.is_file():
        raise AuditError(f"fvOptions must be a regular dictionary file: {fvoptions_path}")
    for folder in (case_root / "system", case_root / "constant"):
        if folder.is_dir():
            for path in folder.rglob("*"):
                if path.name == "fvModels":
                    raise AuditError(f"fvModels are unsupported in the native ledger: {path}")
                if path.name == "fvOptions":
                    if path != fvoptions_path:
                        raise AuditError(
                            f"fvOptions is only supported at constant/fvOptions: {path}"
                        )
                    if path.is_symlink() or not path.is_file():
                        raise AuditError(f"fvOptions must be a regular dictionary file: {path}")
                    if path.stat().st_size > 2_000_000:
                        raise AuditError(f"fvOptions dictionary exceeds the supported size: {path}")
                    inspected.append(path)
                    continue
                if not path.is_file() or path.name in {
                    "controlDict",
                    "fvSolution",
                    "transportProperties",
                }:
                    continue
                if path.stat().st_size > 2_000_000:
                    continue
                # Foam dictionaries and small text configuration files only.
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                inspected.append(path)
                if UNSUPPORTED_PATTERN.search(_strip_foam_comments(text)):
                    raise AuditError(
                        f"unsupported source/phase-change/porosity declaration in {path}"
                    )

    turbulent_viscosity_limiter = _parse_turbulent_viscosity_limiter(fvoptions_path)

    # The density parser checks the actual case dictionary and any duplicate case declaration.
    rho = _water_density(transport_path, case_inputs)
    boundary_inventory = _verify_boundary_inventory(case_root, case_inputs)
    if dynamic_path.is_file():
        mesh_mode = "explicit staticFvMesh"
    else:
        mesh_mode = "fixed mesh; no dynamicFvMeshDict present"
    return {
        "solver": solver,
        "nAlphaSubCycles": subcycles,
        "nOuterCorrectors": outer,
        "water_density_kg_m3": rho,
        "mesh_mode": mesh_mode,
        "diagnostic_function_object_bindings": function_object_bindings,
        "internal_sources_phase_change_porosity": "none detected in case inputs and scanned system/constant dictionaries",
        "turbulent_viscosity_limiter": (
            turbulent_viscosity_limiter
            if turbulent_viscosity_limiter is not None
            else {"active": False, "status": "not configured"}
        ),
        "boundary_inventory": boundary_inventory,
        "configuration_files_scanned": [str(path) for path in inspected],
    }


def _image_strings(value: Any, key: str = "", image_context: bool = False) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            child_context = image_context or key.lower() in {
                "docker_image_info",
                "container_image_info",
                "image_info",
            }
            found.extend(_image_strings(child, child_key, child_context))
    elif isinstance(value, list):
        for child in value:
            found.extend(_image_strings(child, key, image_context))
    elif isinstance(value, str) and (
        key.lower()
        in {
            "openfoam_image",
            "solver_image",
            "openfoam_image_digest",
            "solver_image_digest",
            "solver_image_id",
            "image_digest",
            "docker_image_info",
        }
        or image_context
        and key.lower() in {"id", "image_id", "digest", "repo_digests"}
    ):
        found.append((key, value))
    return found


def _verify_source_evidence(path: Path) -> dict[str, Any]:
    evidence = _read_json(path)
    if evidence.get("pinned_image") != PINNED_IMAGE:
        raise AuditError(
            f"source evidence must pin {PINNED_IMAGE}; got {evidence.get('pinned_image')!r}"
        )
    source_records = evidence.get("solver_source", {})
    copies = evidence.get("pinned_source_copies_sha256", {})
    if not isinstance(source_records, dict) or not isinstance(copies, dict):
        raise AuditError("source evidence lacks solver_source or pinned_source_copies_sha256 maps")
    verified: dict[str, str] = {}
    for name, expected in KNOWN_SOLVER_SOURCE_HASHES.items():
        source_record = source_records.get(name)
        source_hash = source_record.get("sha256") if isinstance(source_record, dict) else None
        copy_hash = copies.get(name, copies.get(SOURCE_COPY_KEY_ALIASES.get(name, "")))
        if source_hash != expected or copy_hash != expected:
            raise AuditError(f"source evidence hash mismatch for {name}")
        verified[name] = expected
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "pinned_image": PINNED_IMAGE,
        "verified_source_hashes": verified,
        "source_run": evidence.get("source_run"),
    }


def _run_manifest_paths(run_dir: Path, case_root: Path) -> tuple[Path, ...]:
    candidates = (run_dir / "manifest.json", case_root.parent / "manifest.json")
    return tuple(dict.fromkeys(path.resolve() for path in candidates if path.is_file()))


def _verify_prepared_case_hashes(case_root: Path, manifests: tuple[Path, ...]) -> dict[str, Any]:
    checked_files = 0
    checked_manifest_paths: list[str] = []
    for manifest_path in manifests:
        manifest = _read_json(manifest_path)
        declared = manifest.get("prepared_case_sha256")
        if declared is None:
            continue
        if not isinstance(declared, dict) or not declared:
            raise AuditError(f"invalid prepared_case_sha256 map in {manifest_path}")
        checked_manifest_paths.append(str(manifest_path))
        for relative, expected in declared.items():
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise AuditError(f"unsafe prepared-case path in {manifest_path}: {relative}")
            actual_path = case_root / relative_path
            if not actual_path.is_file():
                raise AuditError(f"frozen prepared-case file is missing: {actual_path}")
            actual = sha256_file(actual_path)
            if actual != expected:
                raise AuditError(
                    f"prepared-case input hash mismatch for {relative}: "
                    f"manifest={expected}, current={actual}"
                )
            checked_files += 1
    return {
        "verification_status": "verified" if checked_files else "not_available",
        "verified_file_count": checked_files,
        "run_manifests": checked_manifest_paths,
        "note": (
            "Every file listed in each available prepared_case_sha256 map matched."
            if checked_files
            else "No run manifest supplied prepared_case_sha256; current inputs are hashed but not compared to a frozen pre-run copy."
        ),
    }


def _verify_image(
    case_inputs: dict[str, Any],
    manifests: tuple[Path, ...],
    source_evidence: Path | None,
) -> dict[str, Any]:
    candidates = [("case-inputs", key, value) for key, value in _image_strings(case_inputs)]
    for manifest_path in manifests:
        manifest = _read_json(manifest_path)
        candidates.extend(
            (str(manifest_path), key, value) for key, value in _image_strings(manifest)
        )
    supplemental_evidence = (
        _verify_source_evidence(source_evidence) if source_evidence is not None else None
    )
    digest_records = [
        (origin, key, value) for origin, key, value in candidates if "sha256:" in value.lower()
    ]
    contradictory = [record for record in digest_records if PINNED_IMAGE not in record[2]]
    if contradictory:
        raise AuditError(f"run metadata contradicts the pinned solver image: {contradictory}")
    direct = [record for record in digest_records if PINNED_IMAGE in record[2]]
    if direct:
        result = {
            "verification_mode": "run-specific-image-digest",
            "image_fields": [list(record) for record in direct],
            "run_manifests": [str(path) for path in manifests],
        }
        if supplemental_evidence is not None:
            result["supplemental_verified_source_evidence"] = supplemental_evidence
        return result
    tag_match = any("opencfd/openfoam-default:2512" in value for _, _, value in candidates)
    if source_evidence is None:
        raise AuditError(
            "case-inputs does not record the pinned solver image digest; "
            "supply --verified-source-evidence for the pinned image/source record"
        )
    assert supplemental_evidence is not None
    verified = supplemental_evidence
    if not tag_match:
        raise AuditError("case image tag does not match opencfd/openfoam-default:2512")
    verified["verification_mode"] = "supplied-verified-source-evidence"
    verified["case_image_tag"] = "opencfd/openfoam-default:2512"
    verified["run_specific_image_digest_recorded"] = False
    verified["run_manifests"] = [str(path) for path in manifests]
    return verified


def _numeric_token(token: str, *, context: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise AuditError(f"non-numeric value {token!r} in {context}") from exc
    if not math.isfinite(value):
        raise AuditError(f"non-finite value {token!r} in {context}")
    return value


def _series_paths(case_root: Path, function_name: str, file_stem: str) -> tuple[Path, ...]:
    root = case_root / "postProcessing" / function_name
    if not root.is_dir():
        raise AuditError(f"missing function-object directory: {root}")
    paths = tuple(
        sorted(
            path
            for path in root.rglob("*.dat")
            if path.name == f"{file_stem}.dat" or path.name.startswith(f"{file_stem}_")
        )
    )
    if not paths:
        raise AuditError(f"no {file_stem}.dat output below {root}")
    return paths


def _parse_table_file(
    path: Path,
    *,
    expected_values: int,
    header_marker: str,
    content: bytes | None = None,
) -> tuple[list[DataRow], int, str, int]:
    raw = path.read_bytes() if content is None else content
    lines = raw.decode("utf-8", errors="replace").splitlines()
    has_header = False
    candidate_lines = [(index, line.strip()) for index, line in enumerate(lines, 1) if line.strip()]
    rows: list[DataRow] = []
    trailing_partial = 0
    for position, (line_number, line) in enumerate(candidate_lines):
        if line.startswith("#"):
            normalized = " ".join(line.lstrip("#").lower().split())
            if header_marker in normalized:
                has_header = True
            continue
        tokens = line.split()
        if len(tokens) != expected_values + 1:
            has_later_data = any(
                not later.startswith("#") for _, later in candidate_lines[position + 1 :]
            )
            if len(tokens) < expected_values + 1 and not has_later_data:
                trailing_partial += 1
                continue
            raise AuditError(
                f"malformed row in {path}:{line_number}: expected {expected_values + 1} values"
            )
        time_s = _numeric_token(tokens[0], context=f"{path}:{line_number} time")
        values = tuple(
            _numeric_token(token, context=f"{path}:{line_number} column {index}")
            for index, token in enumerate(tokens[1:], 1)
        )
        rows.append(DataRow(tokens[0], time_s, values, path, line_number))
    if not has_header:
        raise AuditError(f"required header marker {header_marker!r} missing from {path}")
    if not rows:
        raise AuditError(f"no complete numeric rows in {path}")
    return rows, trailing_partial, hashlib.sha256(raw).hexdigest(), len(raw)


def _parse_series(
    case_root: Path,
    name: str,
    cutoff_s: float,
    *,
    paths: tuple[Path, ...] | None = None,
    contents: dict[Path, bytes] | None = None,
) -> ParsedTable:
    function_name, file_stem, value_count, marker = SERIES_FILES[name]
    paths = paths or _series_paths(case_root, function_name, file_stem)
    all_rows: list[DataRow] = []
    trailing = 0
    total_rows = 0
    excluded_after_cutoff = 0
    file_hashes: dict[Path, str] = {}
    file_byte_lengths: dict[Path, int] = {}
    for path in paths:
        rows, partial, digest, byte_length = _parse_table_file(
            path,
            expected_values=value_count,
            header_marker=marker,
            content=None if contents is None else contents[path],
        )
        trailing += partial
        selected = [row for row in rows if row.time_s <= cutoff_s]
        total_rows += len(rows)
        excluded_after_cutoff += len(rows) - len(selected)
        file_hashes[path] = digest
        file_byte_lengths[path] = byte_length
        for previous, current in zip(selected, selected[1:]):
            if current.time_s <= previous.time_s:
                reason = "duplicate" if current.time_s == previous.time_s else "out-of-order"
                raise AuditError(
                    f"{reason} timestamps in {path}: {previous.token}, {current.token}"
                )
        all_rows.extend(selected)
    all_rows.sort(key=lambda row: (row.time_s, str(row.path), row.line_number))
    for previous, current in zip(all_rows, all_rows[1:]):
        if current.time_s <= previous.time_s:
            reason = "duplicate" if current.time_s == previous.time_s else "out-of-order"
            raise AuditError(
                f"{reason} timestamps across {name} output files: "
                f"{previous.token} ({previous.path}), {current.token} ({current.path})"
            )
    return ParsedTable(
        tuple(all_rows),
        paths,
        trailing,
        total_rows,
        excluded_after_cutoff,
        file_hashes,
        file_byte_lengths,
    )


DELTA_RE = re.compile(r"\bdeltaT\s*=\s*([+\-0-9.eE]+)")
TIME_RE = re.compile(r"\bTime\s*=\s*([+\-0-9.eE]+)")


def _parse_solver_log(path: Path, cutoff_s: float, *, content: bytes | None = None) -> ParsedLog:
    raw = path.read_bytes() if content is None else content
    rows: list[LogRow] = []
    pending: tuple[float, str, int] | None = None
    ignored_initial_times = 0
    for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        dt_match = DELTA_RE.search(line)
        time_match = TIME_RE.search(line)
        if dt_match:
            if pending is not None:
                raise AuditError(f"unpaired deltaT before another deltaT at {path}:{line_number}")
            delta_t = _numeric_token(dt_match.group(1), context=f"{path}:{line_number} deltaT")
            if delta_t <= 0:
                raise AuditError(f"deltaT must be positive at {path}:{line_number}")
            pending = (delta_t, dt_match.group(1), line_number)
        if time_match:
            token = time_match.group(1)
            time_s = _numeric_token(token, context=f"{path}:{line_number} Time")
            if pending is None:
                if not rows:
                    ignored_initial_times += 1
                    continue
                raise AuditError(f"Time without a preceding native deltaT at {path}:{line_number}")
            delta_t, delta_t_token, _ = pending
            rows.append(LogRow(token, time_s, delta_t, delta_t_token, line_number))
            pending = None
    selected = [row for row in rows if row.time_s <= cutoff_s]
    for previous, current in zip(selected, selected[1:]):
        if current.time_s <= previous.time_s:
            reason = "duplicate" if current.time_s == previous.time_s else "out-of-order"
            raise AuditError(
                f"{reason} solver-log Time records at {path}: {previous.token}, {current.token}"
            )
    if not selected:
        raise AuditError(
            f"no completed paired deltaT/Time rows at or before {cutoff_s:g} s in {path}"
        )
    return ParsedLog(
        tuple(selected),
        pending[0] if pending is not None else None,
        len(rows),
        hashlib.sha256(raw).hexdigest(),
        len(raw),
    )


def _time_precision(control_text: str, time_tokens: Iterable[str]) -> int:
    match = re.search(r"\btimePrecision\s+(\d+)\s*;", _strip_foam_comments(control_text))
    if match:
        return int(match.group(1))
    decimals = [len(token.partition(".")[2]) for token in time_tokens if "." in token]
    if not decimals:
        raise AuditError("cannot determine printed solver time precision")
    return min(decimals)


def _decimal_value(token: str, *, context: str) -> Decimal:
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise AuditError(f"invalid decimal value {token!r} in {context}") from exc
    if not value.is_finite():
        raise AuditError(f"non-finite decimal value {token!r} in {context}")
    return value


def _decimal_half_unit(token: str) -> Decimal:
    """Half of the last printed decimal place, including scientific notation."""
    value = _decimal_value(token, context="printed numeric token")
    exponent = value.as_tuple().exponent
    return Decimal("0.5").scaleb(exponent)


def _longest_common_prefix(streams: dict[str, tuple[Any, ...]]) -> int:
    common = 0
    while True:
        present = {name: rows[common] for name, rows in streams.items() if len(rows) > common}
        if not present:
            break
        tokens = {row.token for row in present.values()}
        times = {row.time_s for row in present.values()}
        if len(tokens) != 1 or len(times) != 1:
            details = {name: row.token for name, row in present.items()}
            raise AuditError(
                "interior time gap or mismatched row in continuing diagnostic/log streams "
                f"after {common} rows: {details}"
            )
        if len(present) != len(streams):
            break
        common += 1
    if common == 0:
        raise AuditError("the seven diagnostics and solver log have no common first row")
    return common


def _resolve_log_path(run_dir: Path, case_root: Path, override: Path | None) -> Path:
    if override is None:
        path = case_root / "log.interIsoFoam"
    elif override.is_absolute():
        path = override
    else:
        candidates = (run_dir / override, case_root / override)
        path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not path.is_file():
        raise AuditError(f"solver log not found: {path}")
    return path


def _relative_path(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _file_signature(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino)


def _capture_data_snapshot(
    case_root: Path,
    original_paths: dict[str, tuple[Path, ...]],
    log_path: Path,
) -> tuple[dict[Path, bytes], dict[Path, tuple[int, int, int, int]]]:
    """Read each mutable diagnostic once and retain the exact bytes parsed."""
    paths = {path for group in original_paths.values() for path in group}
    paths.add(log_path)
    contents: dict[Path, bytes] = {}
    signatures: dict[Path, tuple[int, int, int, int]] = {}
    for path in sorted(paths):
        try:
            before = _file_signature(path)
            raw = path.read_bytes()
            after = _file_signature(path)
        except OSError as exc:
            raise AuditError(f"diagnostic input could not be snapshotted: {path}") from exc
        if before != after or len(raw) != before[0]:
            raise AuditError(
                f"diagnostic input changed while being snapshotted; retry from a frozen copy: {path}"
            )
        signatures[path] = after
        contents[path] = raw
    for name, original in original_paths.items():
        function_name, file_stem, _, _ = SERIES_FILES[name]
        if _series_paths(case_root, function_name, file_stem) != original:
            raise AuditError(
                f"diagnostic file set changed while snapshotting {name}; retry from a frozen copy"
            )
    return contents, signatures


def audit_run(
    run_dir: Path,
    output_dir: Path,
    *,
    end_time_s: float | None = None,
    solver_log: Path | None = None,
    verified_source_evidence: Path | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    case_root = _find_case_root(run_dir)
    input_path = case_root / "case-inputs.json"
    if not input_path.is_file():
        raise AuditError(f"case-inputs.json is missing from {case_root}")
    case_inputs = _read_json(input_path)
    control_path = _config_path(case_root, "system/controlDict", "controlDict")
    fvsolution_path = _config_path(case_root, "system/fvSolution", "fvSolution")
    transport_path = case_root / "constant" / "transportProperties"
    if not transport_path.is_file():
        raise AuditError(f"constant water properties are missing: {transport_path}")
    config = _check_supported_configuration(
        case_root, case_inputs, control_path, fvsolution_path, transport_path
    )
    manifests = _run_manifest_paths(run_dir, case_root)
    image_check = _verify_image(case_inputs, manifests, verified_source_evidence)
    prepared_hash_check = _verify_prepared_case_hashes(case_root, manifests)
    initial_volume_m3, initial_field_path = _initial_zero_water(case_root)

    control_text = control_path.read_text(encoding="utf-8", errors="replace")
    clean_control = _strip_foam_comments(control_text)
    end_match = re.search(
        r"\bendTime\s+([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)\s*;",
        clean_control,
    )
    configured_end_value: Any = end_match.group(1) if end_match else None
    if configured_end_value is None:
        configured_end_value = case_inputs.get("horizon_s")
    if configured_end_value is None:
        configured_end_value = case_inputs.get("time_controls", {}).get("end_s")
    if configured_end_value is None:
        raise AuditError("cannot determine configured end time from controlDict or case-inputs")
    configured_end_decimal = _decimal_value(
        str(configured_end_value), context="configured end time"
    )
    configured_end_s = float(configured_end_decimal)
    if not math.isfinite(configured_end_s) or configured_end_decimal <= 0:
        raise AuditError("configured end time must be finite and positive")
    target_end_decimal = (
        configured_end_decimal
        if end_time_s is None
        else _decimal_value(str(end_time_s), context="requested end time")
    )
    target_end_s = float(target_end_decimal)
    if not math.isfinite(target_end_s) or target_end_decimal <= 0:
        raise AuditError("--end-time-s must be finite and positive")
    if target_end_decimal > configured_end_decimal:
        raise AuditError(
            f"requested end time {target_end_decimal:f} s exceeds configured horizon "
            f"{configured_end_decimal:f} s"
        )

    log_path = _resolve_log_path(run_dir, case_root, solver_log)
    selected_series_paths = {
        name: _series_paths(case_root, SERIES_FILES[name][0], SERIES_FILES[name][1])
        for name in SERIES_FILES
    }
    data_contents, data_signatures = _capture_data_snapshot(
        case_root, selected_series_paths, log_path
    )
    series: dict[str, ParsedTable] = {}
    for name in SERIES_FILES:
        series[name] = _parse_series(
            case_root,
            name,
            target_end_s,
            paths=selected_series_paths[name],
            contents=data_contents,
        )
    log_rows = _parse_solver_log(log_path, target_end_s, content=data_contents[log_path])
    streams: dict[str, tuple[Any, ...]] = {name: table.rows for name, table in series.items()}
    streams["solverLog"] = log_rows.rows
    common_count = _longest_common_prefix(streams)
    common_tokens = [streams["waterVolume"][index].token for index in range(common_count)]
    matched_time_s = [float(token) for token in common_tokens]

    start_match = re.search(
        r"\bstartTime\s+([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)\s*;",
        clean_control,
    )
    start_time_token = start_match.group(1) if start_match else "0"
    start_time_decimal = _decimal_value(start_time_token, context="controlDict startTime")
    start_time_s = float(start_time_decimal)
    if not math.isfinite(start_time_s) or start_time_decimal != 0:
        raise AuditError("supported ledger currently requires a run starting from time zero")
    if re.search(r"\bstartFrom\s+latestTime\s*;", clean_control):
        raise AuditError(
            "restart-only cumulative ledgers are unsupported; provide the complete start-from-zero log"
        )

    precision = _time_precision(control_text, common_tokens)
    format_match = re.search(r"\btimeFormat\s+(\w+)\s*;", clean_control)
    time_format = format_match.group(1) if format_match else "fixed"
    if time_format != "fixed":
        raise AuditError(
            "only fixed timeFormat is supported by the printed-time uncertainty check; "
            f"got {time_format!r}"
        )
    printed_time_half_unit = Decimal("0.5").scaleb(-precision)
    volume_rows = streams["waterVolume"][:common_count]
    log_prefix = streams["solverLog"][:common_count]
    flux_prefix = {
        patch: streams[patch][:common_count] for patch in (*[SOURCE_PATCH], *OPEN_PATCHES)
    }
    reconstructed_times: list[float] = []
    cumulative_delta_rounding_bounds: list[Decimal] = []
    max_reconstruction_error = 0.0
    max_dt_rounded_interval_error = 0.0
    max_allowed_time_difference = Decimal(0)
    first_printed_interval = Decimal(0)
    previous_printed_time = start_time_decimal
    cumulative_native_time = start_time_decimal
    cumulative_delta_rounding_bound = Decimal(0)
    for index, row in enumerate(log_prefix):
        delta_t_decimal = _decimal_value(row.delta_t_token, context="solver log deltaT")
        cumulative_native_time += delta_t_decimal
        cumulative_delta_rounding_bound += _decimal_half_unit(row.delta_t_token)
        allowed_time_difference = printed_time_half_unit + cumulative_delta_rounding_bound
        reconstructed_times.append(float(cumulative_native_time))
        cumulative_delta_rounding_bounds.append(cumulative_delta_rounding_bound)
        max_allowed_time_difference = max(max_allowed_time_difference, allowed_time_difference)
        printed_time = _decimal_value(row.token, context="solver log Time")
        error = abs(cumulative_native_time - printed_time)
        max_reconstruction_error = max(max_reconstruction_error, float(error))
        rounded_interval = printed_time - previous_printed_time
        if index == 0:
            first_printed_interval = rounded_interval
        max_dt_rounded_interval_error = max(
            max_dt_rounded_interval_error,
            float(abs(delta_t_decimal - rounded_interval)),
        )
        if error > allowed_time_difference:
            raise AuditError(
                f"native deltaT cumulative time differs from printed Time at {row.token}: "
                f"{cumulative_native_time} vs {printed_time} s "
                f"(allowed {allowed_time_difference} s; includes accumulated printed deltaT precision)"
            )
        previous_printed_time = printed_time

    rho = config["water_density_kg_m3"]
    initial_inventory_kg = rho * initial_volume_m3
    prior_volume_m3 = initial_volume_m3
    cumulative_injected_kg = 0.0
    cumulative_escape_kg = 0.0
    cumulative_boundary_kg = 0.0
    output_rows: list[dict[str, float | int | str]] = []
    for index in range(common_count):
        native = log_prefix[index]
        volume_m3 = volume_rows[index].values[0]
        dt = native.delta_t_s
        source_flux = flux_prefix[SOURCE_PATCH][index].values[1]
        source_signed_step_kg = rho * source_flux * dt
        injected_step_kg = -source_signed_step_kg
        open_flux_by_patch = {patch: flux_prefix[patch][index].values[1] for patch in OPEN_PATCHES}
        escape_step_kg = rho * sum(open_flux_by_patch.values()) * dt
        total_boundary_step_kg = source_signed_step_kg + escape_step_kg
        inventory_change_kg = rho * (volume_m3 - prior_volume_m3)
        step_residual_kg = inventory_change_kg + total_boundary_step_kg
        cumulative_injected_kg += injected_step_kg
        cumulative_escape_kg += escape_step_kg
        cumulative_boundary_kg += total_boundary_step_kg
        inventory_kg = rho * volume_m3
        cumulative_residual_kg = inventory_kg - initial_inventory_kg + cumulative_boundary_kg

        row: dict[str, float | int | str] = {
            "step_index": index + 1,
            "printed_time_s": native.token,
            "reconstructed_time_s": f"{reconstructed_times[index]:.12g}",
            "native_deltaT_s": f"{dt:.12g}",
            "interval_start_native_s": f"{reconstructed_times[index] - dt:.12g}",
            "interval_end_native_s": f"{reconstructed_times[index]:.12g}",
            "native_inventory_m3": f"{volume_m3:.12g}",
            "native_inventory_kg": f"{inventory_kg:.12g}",
            "inventory_change_kg": f"{inventory_change_kg:.12g}",
            "source_alphaPhi_m3_s": f"{source_flux:.12g}",
            "source_signed_boundary_step_kg": f"{source_signed_step_kg:.12g}",
            "injected_step_kg": f"{injected_step_kg:.12g}",
            "injected_cumulative_kg": f"{cumulative_injected_kg:.12g}",
            "signed_net_escape_step_kg": f"{escape_step_kg:.12g}",
            "signed_net_escape_cumulative_kg": f"{cumulative_escape_kg:.12g}",
            "total_boundary_signed_step_kg": f"{total_boundary_step_kg:.12g}",
            "closure_residual_step_kg": f"{step_residual_kg:.12g}",
            "closure_residual_cumulative_kg": f"{cumulative_residual_kg:.12g}",
        }
        for patch in OPEN_PATCHES:
            signed_mass_step = rho * open_flux_by_patch[patch] * dt
            row[f"{patch}_alphaPhi_m3_s"] = f"{open_flux_by_patch[patch]:.12g}"
            row[f"{patch}_signed_boundary_step_kg"] = f"{signed_mass_step:.12g}"
        output_rows.append(row)
        prior_volume_m3 = volume_m3

    max_abs_residual = max(abs(float(row["closure_residual_cumulative_kg"])) for row in output_rows)
    last_time_s = matched_time_s[-1]
    horizon_rounding_tolerance = printed_time_half_unit + cumulative_delta_rounding_bounds[-1]
    last_time_decimal = _decimal_value(common_tokens[-1], context="last matched printed Time")
    reached_target = last_time_decimal >= target_end_decimal - horizon_rounding_tolerance
    reached_configured = last_time_decimal >= configured_end_decimal - horizon_rounding_tolerance
    if reached_configured:
        coverage_status = "configured_horizon_reached_exploratory_only"
    elif end_time_s is not None and reached_target:
        coverage_status = "explicit_prefix_reached_exploratory_only"
    else:
        coverage_status = "partial_prefix_only"

    row_counts: dict[str, Any] = {}
    input_hashes: dict[str, str] = {}
    all_source_paths: set[Path] = {
        input_path,
        control_path,
        fvsolution_path,
        transport_path,
        case_root / "constant" / "polyMesh" / "boundary",
        case_root / "0" / "U",
        initial_field_path,
        log_path,
    }
    all_source_paths.update(Path(path) for path in config["configuration_files_scanned"])
    all_source_paths.update(manifests)
    data_input_hashes: dict[Path, str] = {log_path: log_rows.file_sha256}
    for name, parsed in series.items():
        matched = common_count
        selected = len(parsed.rows)
        row_counts[name] = {
            "source_files": [str(path) for path in parsed.files],
            "complete_rows_total": parsed.complete_rows_total,
            "complete_rows_at_or_before_requested_end": selected,
            "matched_common_prefix_rows": matched,
            "excluded_after_requested_end": parsed.excluded_after_cutoff,
            "excluded_unmatched_tail_rows": max(0, selected - matched),
            "trailing_partial_rows_ignored": parsed.trailing_partial_rows,
            "file_snapshots": {
                str(path): {
                    "byte_length": parsed.file_byte_lengths[path],
                    "sha256": parsed.file_sha256[path],
                }
                for path in parsed.files
            },
        }
        all_source_paths.update(parsed.files)
        data_input_hashes.update(parsed.file_sha256)
    row_counts["solverLog"] = {
        "source_file": str(log_path),
        "complete_paired_rows_total": log_rows.complete_rows_total,
        "paired_rows_at_or_before_requested_end": len(log_rows.rows),
        "snapshot_byte_length": log_rows.file_byte_length,
        "snapshot_sha256": log_rows.file_sha256,
        "matched_common_prefix_rows": common_count,
        "excluded_unmatched_tail_rows": max(0, len(log_rows.rows) - common_count),
        "excluded_after_requested_end": log_rows.complete_rows_total - len(log_rows.rows),
        "trailing_unpaired_deltaT_s": log_rows.trailing_unpaired_delta_t_s,
    }
    if verified_source_evidence is not None:
        all_source_paths.add(verified_source_evidence.resolve())
    for path in sorted(all_source_paths):
        digest = data_input_hashes.get(path)
        if digest is None:
            digest = sha256_file(path)
        input_hashes[_relative_path(path, run_dir)] = digest

    columns = list(output_rows[0])
    summary: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "Exploratory fixed-mesh interIsoFoam water ledger audit; not a validation or conservation gate.",
        "formal_validation_decision": None,
        "run_dir": str(run_dir),
        "case_root": str(case_root),
        "output_files": ["ledger.csv", "summary.json"],
        "coverage": {
            "configured_horizon_s": configured_end_s,
            "requested_end_time_s": target_end_s,
            "requested_end_was_explicit_cli_prefix": end_time_s is not None,
            "common_prefix_rows": common_count,
            "first_matched_time_s": matched_time_s[0],
            "last_matched_printed_time_s": last_time_s,
            "last_matched_reconstructed_time_s": reconstructed_times[-1],
            "coverage_fraction_of_requested_horizon": min(
                1.0, max(0.0, (last_time_s - start_time_s) / (target_end_s - start_time_s))
            ),
            "requested_end_reached": reached_target,
            "configured_horizon_reached": reached_configured,
            "status": coverage_status,
            "interpretation": "A partial prefix is reported as partial; it is never labeled a horizon success or gate pass.",
        },
        "row_coverage": row_counts,
        "mutable_data_snapshot": {
            "policy": "Each discovered diagnostics/log file was read once before parsing; hashes and byte lengths identify those exact in-memory byte snapshots. The live on-disk files may append after capture; later bytes are outside this audit.",
            "captured_file_count": len(data_signatures),
            "snapshot_files": {
                str(path): {
                    "byte_length": len(data_contents[path]),
                    "sha256": hashlib.sha256(data_contents[path]).hexdigest(),
                }
                for path in sorted(data_contents)
            },
        },
        "integration": {
            "method": "right rectangle on each completed physical interval: Q_k * native deltaT_k",
            "flux_interpretation": "sum(alphaPhi_) is the interval-mean water volumetric flux for the completed alpha-advection step; outward boundary sign is positive.",
            "source_patch": SOURCE_PATCH,
            "open_patches": list(OPEN_PATCHES),
            "density_kg_m3": rho,
            "initial_inventory_m3": initial_volume_m3,
            "initial_inventory_kg": initial_inventory_kg,
            "final_inventory_m3": volume_rows[-1].values[0],
            "native_function_inventory_kg": rho * volume_rows[-1].values[0],
            "injected_kg": cumulative_injected_kg,
            "signed_net_escape_kg": cumulative_escape_kg,
            "signed_total_boundary_mass_kg": cumulative_boundary_kg,
            "closure_residual_kg": cumulative_residual_kg,
            "max_abs_cumulative_closure_residual_kg": max_abs_residual,
            "max_abs_per_step_closure_residual_kg": max(
                abs(float(row["closure_residual_step_kg"])) for row in output_rows
            ),
            "rounding_diagnostic": {
                "time_precision_digits": precision,
                "time_format": time_format,
                "printed_time_half_unit_s": float(printed_time_half_unit),
                "cumulative_deltaT_print_rounding_bound_s": float(
                    cumulative_delta_rounding_bounds[-1]
                ),
                "max_allowed_native_vs_printed_time_difference_s": float(
                    max_allowed_time_difference
                ),
                "first_native_deltaT_s": log_prefix[0].delta_t_s,
                "first_native_deltaT_token": log_prefix[0].delta_t_token,
                "first_printed_interval_s": float(first_printed_interval),
                "first_native_minus_printed_interval_s": float(
                    _decimal_value(log_prefix[0].delta_t_token, context="first deltaT")
                    - first_printed_interval
                ),
                "max_abs_native_deltaT_vs_rounded_interval_s": max_dt_rounded_interval_error,
                "max_abs_reconstructed_native_time_vs_printed_time_s": max_reconstruction_error,
                "warning": "Native deltaT is used for integration. Rounded printed timestamp differences are diagnostic only.",
            },
            "known_closure_caveat": "Pinned isoAdvection applies conservative limitFluxes before direct alpha snap/clipping; alphaPhi_ reflects the conservative flux-limited sweep but later nonconservative alpha changes can appear in the residual.",
        },
        "supported_configuration": config,
        "prepared_input_hash_verification": prepared_hash_check,
        "solver_image_verification": image_check,
        "source_code_and_input_sha256": {
            "audit_script_sha256": sha256_file(Path(__file__).resolve()),
            "inputs": input_hashes,
        },
        "scientific_caveats": [
            "This narrow audit supports the pinned interIsoFoam/isoAdvection implementation with nAlphaSubCycles=1, nOuterCorrectors=1, fixed mesh, constant water density, zero initial water, and no internal source, phase-change, or porosity model.",
            "It does not establish semantic support for other solvers, multiphase models, restart-only cumulative intervals, subcycling, moving meshes, or source/sink models.",
            "A small residual is a diagnostic result for this sampled prefix, not a solver validation or E0-E6 gate decision.",
            "Fluxes are signed outward-positive at each patch; injected mass is the negative source-patch signed mass, while signed net escape sums the five open boundaries.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    csv_path = output_dir / "ledger.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(output_rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path, required=True, help="case directory or run bundle containing case/"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new directory for ledger.csv and summary.json",
    )
    parser.add_argument("--end-time-s", type=float, help="optional explicit audit-prefix end time")
    parser.add_argument(
        "--solver-log", type=Path, help="explicit solver log override, e.g. rawrestartsolver.log"
    )
    parser.add_argument(
        "--verified-source-evidence",
        type=Path,
        help="evidence.json pinning the expected solver image and source hashes",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = audit_run(
            args.run_dir,
            args.output_dir,
            end_time_s=args.end_time_s,
            solver_log=args.solver_log,
            verified_source_evidence=args.verified_source_evidence,
        )
    except (AuditError, FileExistsError, OSError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "output_files": summary["output_files"],
                "coverage_status": summary["coverage"]["status"],
                "matched_rows": summary["coverage"]["common_prefix_rows"],
                "closure_residual_kg": summary["integration"]["closure_residual_kg"],
                "formal_validation_decision": None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
