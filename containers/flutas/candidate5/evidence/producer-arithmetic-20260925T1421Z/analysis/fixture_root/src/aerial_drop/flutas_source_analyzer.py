"""Offline structural analyzer for the proposed FluTAS candidate5 B2 outputs.

This analyzer checks pinned files, deterministic structure, joins, reported
scan summaries, and the producer's timestep guard arithmetic. It has no
scientific pass result: numerical, conservation, pressure, Courant, divergence,
and resource limits remain outside this implementation contract.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

PRODUCER_SCHEMA = "candidate5-observability-v1.2"
MANIFEST_SCHEMA = "candidate5-run-manifest-v2"
SCHEMA_SHA256_PIN = "4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492"
INTERVAL_COUNT = 14
STATE_COUNT = INTERVAL_COUNT + 1
NX, NY, NZ = 160, 84, 40
NOT_APPLICABLE = "not_applicable"
DECISION_NOT_ADJUDICATED = "not_adjudicated"

PHASE_FILE = "phase-property-stage-audit.csv"
VELOCITY_FILE = "boundary-velocity-stage-audit.csv"
TIMESTEP_FILE = "timestep-restriction.csv"
OUTPUT_FILES = (PHASE_FILE, VELOCITY_FILE, TIMESTEP_FILE)

PHASE_HEADER = (
    "state_index",
    "transport_interval_index",
    "stage_id",
    "face",
    "source_class",
    "property",
    "scanned_cells",
    "mismatch_count",
    "nonfinite_count",
    "max_abs_error",
    "first_bad_i",
    "first_bad_j",
    "first_bad_k",
    "expected",
    "observed",
)
VELOCITY_HEADER = (
    "state_index",
    "transport_interval_index",
    "stage_id",
    "face",
    "source_class",
    "component",
    "scanned_cells",
    "mismatch_count",
    "nonfinite_count",
    "max_abs_error",
    "first_bad_i",
    "first_bad_j",
    "first_bad_k",
    "requested",
    "applied",
)
TIMESTEP_HEADER = (
    "state_index",
    "time_s",
    "dt_s",
    "dtic_raw_s_inv",
    "dtic_used_s_inv",
    "zero_advection_fallback",
    "nu_max_m2_s",
    "h_min_m",
    "dlmini_m_inv",
    "dtiv_s_inv",
    "dtik_s_inv",
    "dtig_s_inv",
    "capillary_active",
    "dtmax_s",
    "fixed_step_factor",
    "dt_over_dtmax",
    "guard_pass",
)

FACES = ("xlow", "xhigh", "ylow", "yhigh", "zlow", "zhigh")
SOURCE_CLASSES = (
    "active_slot",
    "inactive_slot",
    "top_offmask",
    "bottom_return",
    "other_inflow",
    "other_outflow",
    "periodic",
)
PROPERTIES = ("alpha", "rho", "mu")
COMPONENTS = ("u", "v", "w")
PHASE_STAGES = ("pre_vof_x", "pre_vof_y", "pre_vof_z", "pre_momentum")
VELOCITY_STAGES = (
    "initial_u0",
    "projection_override",
    "corrected_endpoint",
    "pre_vof",
)
PHASE_FACE_CLASSES = (
    ("xlow", "periodic"),
    ("xhigh", "periodic"),
    ("ylow", "periodic"),
    ("yhigh", "periodic"),
    ("zlow", "bottom_return"),
    ("zhigh", "active_slot"),
    ("zhigh", "inactive_slot"),
    ("zhigh", "top_offmask"),
)
VELOCITY_FACE_CLASSES = (
    ("zhigh", "active_slot"),
    ("zhigh", "inactive_slot"),
    ("zhigh", "top_offmask"),
    ("zlow", "bottom_return"),
)

PHASE_SCAN_ORDER = [
    "transport_interval_index",
    "state_index",
    "stage_id",
    "face",
    "source_class",
    "property",
]
VELOCITY_SCAN_ORDER = [
    "transport_interval_index",
    "state_index",
    "stage_id",
    "face",
    "source_class",
    "component",
]
TIMESTEP_SCAN_ORDER = ["state_index"]

MANIFEST_FIELDS = frozenset(
    {
        "manifest_schema",
        "producer_schema",
        "schema_sha256",
        "candidate_sha256",
        "image_digest",
        "case_id",
        "input_sha256",
        "analyzer_sha256",
        "run_status",
        "solver_exit_code",
        "stop_reason",
        "state_count",
        "interval_count",
        "completed_interval_count",
        "stop_state_index",
        "stop_interval_index",
        "stop_stage_id",
        "final_time_s",
        "files_sha256",
        "row_counts",
        "scan_order",
        "reduction_order",
        "timestep_inputs",
        "resources",
        "pressure_solver",
    }
)

TIMESTEP_INPUT_FIELDS = frozenset(
    {
        "time_scheme",
        "time_start_s",
        "real_kind",
        "precision_digits",
        "machine_epsilon",
        "small_s_inv",
        "cfl_c",
        "cfl_d",
        "rho1_kg_m3",
        "rho2_kg_m3",
        "mu1_pa_s",
        "mu2_pa_s",
        "dx_m",
        "dy_m",
        "dz_m",
        "dxi_m_inv",
        "dyi_m_inv",
        "dzi_m_inv",
        "dzc_m",
        "dzf_m",
        "dzci_m_inv",
        "dzfi_m_inv",
        "sigma_n_m",
        "gravity_m_s2",
        "fixed_step_factor",
        "fixed_step_s",
    }
)

DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
INTEGER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
CASE_ID_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class AnalyzerError(ValueError):
    """A structural or provenance violation in a candidate5 bundle."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ExpectedProvenance:
    """Independent pins supplied by the reviewed run contract or test fixture."""

    manifest_sha256: str
    schema_sha256: str
    candidate_sha256: str
    image_digest: str
    case_id: str
    input_sha256: Mapping[str, str]
    analyzer_sha256: str
    expected_timestep_inputs: Mapping[str, Any]
    expected_scan_cells: Mapping[tuple[str, ...], int]
    slot_masks: tuple[frozenset[tuple[int, int]], ...]
    active_schedule_indices: frozenset[int]


@dataclass(frozen=True)
class AnalysisReport:
    structural_disposition: str
    evidence_disposition: str
    decision: str
    issue_codes: tuple[str, ...]
    row_counts: Mapping[str, int]
    timestep_rows_checked: int


def _fail(code: str, message: str) -> None:
    raise AnalyzerError(code, message)


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def _as_binary64(value: Decimal, field: str) -> float:
    try:
        binary64 = float(value)
    except (OverflowError, ValueError) as exc:
        raise AnalyzerError("NUMERIC_RANGE", f"{field} is outside binary64 range") from exc
    _require(
        math.isfinite(binary64) and (value.is_zero() or binary64 != 0.0),
        "NUMERIC_RANGE",
        f"{field} is not representable as finite binary64 without underflow",
    )
    return binary64


def _binary64_reciprocal(value: Decimal, field: str) -> float:
    binary64 = _as_binary64(value, field)
    _require(binary64 != 0.0, "TIMESTEP_INPUTS", f"{field} must be a nonzero divisor")
    try:
        reciprocal = 1.0 / binary64
    except (ArithmeticError, ValueError) as exc:
        raise AnalyzerError("TIMESTEP_INPUTS", f"reciprocal of {field} is undefined") from exc
    _require(
        math.isfinite(reciprocal) and reciprocal != 0.0,
        "TIMESTEP_INPUTS",
        f"reciprocal of {field} is outside finite binary64 range",
    )
    return reciprocal


def _valid_sha(value: Any, field: str) -> str:
    _require(
        isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
        "INVALID_HASH",
        f"{field} must be lowercase SHA-256",
    )
    return value


def _relative_path(value: Any, field: str) -> str:
    _require(
        isinstance(value, str) and value != "",
        "INVALID_PATH",
        f"{field} must be a repository-relative path",
    )
    path = PurePosixPath(value)
    _require(
        not path.is_absolute()
        and str(path) == value
        and bool(path.parts)
        and ".." not in path.parts
        and "\\" not in value,
        "INVALID_PATH",
        f"{field} is not repository-relative POSIX syntax",
    )
    return value


def _decimal(token: Any, field: str) -> Decimal:
    _require(isinstance(token, str), "INVALID_NUMERIC", f"{field} must be a decimal string")
    _require(
        token == token.strip() and DECIMAL_RE.fullmatch(token) is not None,
        "INVALID_NUMERIC",
        f"{field} is not a canonical ASCII decimal token",
    )
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise AnalyzerError("INVALID_NUMERIC", f"invalid Decimal in {field}") from exc
    _require(value.is_finite(), "NONFINITE_NUMERIC", f"{field} is not finite")
    _require(
        not (value.is_zero() and token.startswith("-")),
        "INVALID_NUMERIC",
        f"{field} uses noncanonical signed zero",
    )
    _as_binary64(value, field)
    return value


def _integer(token: Any, field: str) -> int:
    _require(
        isinstance(token, str) and INTEGER_RE.fullmatch(token) is not None,
        "INVALID_INTEGER",
        f"{field} is not a canonical integer token",
    )
    _require(token != "-0", "INVALID_INTEGER", f"{field} uses noncanonical negative zero")
    return int(token)


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AnalyzerError("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise AnalyzerError("NONFINITE_JSON", f"non-finite JSON constant is forbidden: {value}")


def parse_manifest_bytes(data: bytes) -> dict[str, Any]:
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AnalyzerError("INVALID_UTF8", "run manifest is not strict UTF-8") from exc
    _require(
        not decoded.startswith("\ufeff"), "INVALID_UTF8", "run manifest must not contain a BOM"
    )
    try:
        manifest = json.loads(
            decoded,
            object_pairs_hook=_json_no_duplicates,
            parse_constant=_reject_json_constant,
        )
    except AnalyzerError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise AnalyzerError("INVALID_MANIFEST_JSON", "run manifest is not valid JSON") from exc
    _require(isinstance(manifest, dict), "INVALID_MANIFEST", "run manifest root must be an object")
    try:
        canonical = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise AnalyzerError("INVALID_MANIFEST_JSON", "manifest is not canonical JSON data") from exc
    _require(data == canonical, "MANIFEST_ENCODING", "manifest JSON is not canonical")
    _require(
        set(manifest) == MANIFEST_FIELDS,
        "MANIFEST_FIELDS",
        "run manifest fields do not match the exact analyzer schema",
    )
    return manifest


def _validate_manifest(manifest: Mapping[str, Any], pins: ExpectedProvenance) -> None:
    _require(
        manifest["manifest_schema"] == MANIFEST_SCHEMA,
        "MANIFEST_VERSION",
        "unsupported run-manifest schema",
    )
    _require(
        manifest["producer_schema"] == PRODUCER_SCHEMA,
        "PRODUCER_VERSION",
        "unsupported producer schema",
    )
    candidate_hash = _valid_sha(manifest["candidate_sha256"], "candidate_sha256")
    _require(
        isinstance(manifest["image_digest"], str)
        and IMAGE_RE.fullmatch(manifest["image_digest"]) is not None,
        "INVALID_IMAGE",
        "image_digest must be sha256:<lowercase digest>",
    )
    _require(
        isinstance(manifest["case_id"], str)
        and CASE_ID_RE.fullmatch(manifest["case_id"]) is not None,
        "INVALID_CASE_ID",
        "case_id must be a lowercase ASCII identifier",
    )
    analyzer_hash = _valid_sha(manifest["analyzer_sha256"], "analyzer_sha256")
    input_hashes = manifest["input_sha256"]
    _require(
        isinstance(input_hashes, dict) and bool(input_hashes),
        "INPUT_PROVENANCE",
        "input_sha256 must be a nonempty path/hash object",
    )
    for path, digest in input_hashes.items():
        _relative_path(path, "input_sha256 path")
        _valid_sha(digest, f"input_sha256[{path}]")

    _valid_sha(pins.manifest_sha256, "external expected manifest hash")
    expected_schema_hash = _valid_sha(pins.schema_sha256, "external expected schema hash")
    _valid_sha(pins.candidate_sha256, "external expected candidate hash")
    _valid_sha(pins.analyzer_sha256, "external expected analyzer hash")
    _require(
        IMAGE_RE.fullmatch(pins.image_digest) is not None,
        "INVALID_IMAGE",
        "external expected image digest is malformed",
    )
    _require(
        isinstance(pins.case_id, str) and CASE_ID_RE.fullmatch(pins.case_id) is not None,
        "INVALID_CASE_ID",
        "external expected case_id must be a lowercase ASCII identifier",
    )
    _require(
        expected_schema_hash == SCHEMA_SHA256_PIN,
        "PROVENANCE_MISMATCH",
        "shared schema pin differs from the accepted v1.2 schema bytes",
    )
    _require(
        candidate_hash == pins.candidate_sha256,
        "PROVENANCE_MISMATCH",
        "candidate hash differs from external pin",
    )
    _require(
        manifest["schema_sha256"] == expected_schema_hash,
        "PROVENANCE_MISMATCH",
        "shared schema hash differs from external pin",
    )
    _require(
        manifest["image_digest"] == pins.image_digest,
        "PROVENANCE_MISMATCH",
        "image digest differs from external pin",
    )
    _require(
        manifest["case_id"] == pins.case_id,
        "PROVENANCE_MISMATCH",
        "case ID differs from external pin",
    )
    _require(
        analyzer_hash == pins.analyzer_sha256,
        "PROVENANCE_MISMATCH",
        "analyzer hash differs from external pin",
    )
    _require(
        dict(input_hashes) == dict(pins.input_sha256),
        "PROVENANCE_MISMATCH",
        "input path/hash map differs from external pin",
    )
    _require(
        manifest["timestep_inputs"] == dict(pins.expected_timestep_inputs),
        "TIMESTEP_INPUT_PIN",
        "timestep inputs differ from the externally frozen candidate/case values",
    )

    _require(
        type(manifest["state_count"]) is int and type(manifest["interval_count"]) is int,
        "INVALID_COUNT",
        "state and interval counts must be JSON integers",
    )
    _require(
        manifest["state_count"] == STATE_COUNT, "STATE_COUNT", "planned state_count must be 15"
    )
    _require(
        manifest["interval_count"] == INTERVAL_COUNT,
        "INTERVAL_COUNT",
        "planned interval_count must be 14",
    )
    _require(
        type(manifest["completed_interval_count"]) is int,
        "INVALID_COUNT",
        "completed_interval_count must be a JSON integer",
    )
    _require(
        isinstance(manifest["run_status"], str)
        and manifest["run_status"] in {"completed", "failed"},
        "RUN_STATUS",
        "run_status must be completed or failed",
    )
    _require(
        type(manifest["solver_exit_code"]) is int,
        "RUN_STATUS",
        "solver_exit_code must be a JSON integer",
    )
    _require(
        isinstance(manifest["stop_reason"], str)
        and manifest["stop_reason"]
        in {"normal_completion", "timestep_guard", "phase_audit", "velocity_audit"},
        "RUN_STATUS",
        "stop_reason is required",
    )
    _require(
        manifest["stop_reason"] == "normal_completion"
        and manifest["run_status"] == "completed"
        and manifest["solver_exit_code"] == 0
        and manifest["completed_interval_count"] == INTERVAL_COUNT
        and manifest["stop_state_index"] == NOT_APPLICABLE
        and manifest["stop_interval_index"] == NOT_APPLICABLE
        and manifest["stop_stage_id"] == NOT_APPLICABLE
        or manifest["stop_reason"] != "normal_completion"
        and manifest["run_status"] == "failed"
        and manifest["solver_exit_code"] != 0,
        "RUN_STATUS",
        "run status, exit code, completion count, and stop reason disagree",
    )
    if manifest["stop_reason"] != "normal_completion":
        _require(
            type(manifest["stop_state_index"]) is int
            and type(manifest["stop_interval_index"]) is int,
            "STOP_INDEX",
            "controlled stop indices must be JSON integers",
        )
        _require(
            manifest["stop_interval_index"] == manifest["completed_interval_count"]
            and 0 <= manifest["stop_interval_index"] < INTERVAL_COUNT,
            "STOP_INDEX",
            "controlled stop interval must equal completed count and be in range",
        )
        interval = manifest["stop_interval_index"]
        expected_state = interval
        stage = manifest["stop_stage_id"]
        if manifest["stop_reason"] == "timestep_guard":
            expected_stage = NOT_APPLICABLE
        elif manifest["stop_reason"] == "phase_audit":
            expected_stage = stage
            _require(stage in PHASE_STAGES, "STOP_STAGE", "phase stop stage is not declared")
        else:
            _require(stage in VELOCITY_STAGES, "STOP_STAGE", "velocity stop stage is not declared")
            expected_stage = stage
            if stage in {"projection_override", "corrected_endpoint"}:
                expected_state = interval + 1
            if stage == "initial_u0":
                _require(interval == 0, "STOP_INDEX", "initial_u0 stop must be at interval zero")
        _require(
            manifest["stop_stage_id"] == expected_stage,
            "STOP_STAGE",
            "stop_stage_id does not match the controlled stop reason",
        )
        _require(
            manifest["stop_state_index"] == expected_state,
            "STOP_INDEX",
            "stop_state_index does not match stop interval/stage semantics",
        )

    scan_order = manifest["scan_order"]
    expected_scan_order = {
        "phase_property": PHASE_SCAN_ORDER,
        "boundary_velocity": VELOCITY_SCAN_ORDER,
        "timestep": TIMESTEP_SCAN_ORDER,
    }
    _require(
        scan_order == expected_scan_order,
        "SCAN_ORDER",
        "manifest scan_order does not match the exact analyzer key order",
    )
    reduction_order = manifest["reduction_order"]
    _require(
        reduction_order
        == {
            "cell_scan_order": "i,j,k ascending",
            "max_error_order": "first lexicographic location on a tie",
            "floating_point": "candidate real(rp) binary64",
        },
        "REDUCTION_ORDER",
        "reduction_order must use the exact v1.2 descriptions",
    )

    files_sha = manifest["files_sha256"]
    row_counts = manifest["row_counts"]
    _require(
        isinstance(files_sha, dict) and set(files_sha) == set(OUTPUT_FILES),
        "OUTPUT_PROVENANCE",
        "manifest must hash exactly the three candidate5 CSV files",
    )
    _require(
        isinstance(row_counts, dict) and set(row_counts) == set(OUTPUT_FILES),
        "ROW_COUNTS",
        "manifest must count exactly the three candidate5 CSV files",
    )
    for filename in OUTPUT_FILES:
        _valid_sha(files_sha[filename], f"files_sha256[{filename}]")
        _require(
            type(row_counts[filename]) is int and row_counts[filename] >= 0,
            "ROW_COUNTS",
            f"row_counts[{filename}] must be a nonnegative JSON integer",
        )

    _validate_timestep_inputs(manifest["timestep_inputs"])
    _validate_resources(manifest["resources"], manifest["completed_interval_count"])
    _validate_pressure_record(manifest["pressure_solver"])
    _decimal(manifest["final_time_s"], "final_time_s")


def _validate_timestep_inputs(inputs: Any) -> dict[str, Any]:
    _require(
        isinstance(inputs, dict) and set(inputs) == TIMESTEP_INPUT_FIELDS,
        "TIMESTEP_INPUTS",
        "timestep_inputs must match the exact analyzer schema",
    )
    _require(inputs["time_scheme"] == "ab2", "TIMESTEP_INPUTS", "time_scheme must be ab2")
    _require(
        type(inputs["real_kind"]) is int and inputs["real_kind"] == 8,
        "TIMESTEP_INPUTS",
        "candidate real_kind must be binary64 kind 8",
    )
    _require(
        type(inputs["precision_digits"]) is int and inputs["precision_digits"] == 15,
        "TIMESTEP_INPUTS",
        "candidate precision_digits must be 15",
    )
    array_fields = {"dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv", "gravity_m_s2"}
    scalar_fields = (
        TIMESTEP_INPUT_FIELDS
        - array_fields
        - {
            "time_scheme",
            "real_kind",
            "precision_digits",
        }
    )
    parsed: dict[str, Any] = {
        field: _decimal(inputs[field], f"timestep_inputs.{field}") for field in scalar_fields
    }
    for field in (
        "rho1_kg_m3",
        "rho2_kg_m3",
        "mu1_pa_s",
        "mu2_pa_s",
        "dx_m",
        "dy_m",
        "dz_m",
        "cfl_c",
        "cfl_d",
        "small_s_inv",
        "fixed_step_factor",
        "fixed_step_s",
        "machine_epsilon",
    ):
        _require(parsed[field] > 0, "TIMESTEP_INPUTS", f"timestep_inputs.{field} must be positive")
    _require(
        parsed["time_start_s"] == 0,
        "TIMESTEP_INPUTS",
        "the frozen no-restart fixture requires time_start_s=0",
    )
    _require(parsed["sigma_n_m"] >= 0, "TIMESTEP_INPUTS", "surface tension cannot be negative")
    _require(
        float(parsed["machine_epsilon"]) == math.ulp(1.0),
        "TIMESTEP_INPUTS",
        "machine_epsilon differs from IEEE binary64 epsilon",
    )
    _require(
        float(parsed["small_s_inv"])
        == float(parsed["machine_epsilon"]) * (10.0 ** (inputs["precision_digits"] / 2.0)),
        "TIMESTEP_INPUTS",
        "small_s_inv differs from the pinned binary64 application formula",
    )
    _require(
        float(parsed["cfl_c"]) == 1.0 and float(parsed["cfl_d"]) == 1.0 / 6.0,
        "TIMESTEP_INPUTS",
        "AB2 cfl_c/cfl_d differs from the pinned upstream values",
    )
    parsed["real_kind"] = inputs["real_kind"]
    parsed["precision_digits"] = inputs["precision_digits"]
    parsed["time_scheme"] = inputs["time_scheme"]

    for field, expected_length in (
        ("dzc_m", 42),
        ("dzf_m", 42),
        ("dzci_m_inv", 42),
        ("dzfi_m_inv", 42),
        ("gravity_m_s2", 3),
    ):
        values = inputs[field]
        _require(
            isinstance(values, list) and len(values) == expected_length,
            "TIMESTEP_INPUTS",
            f"{field} must contain exactly {expected_length} decimal strings",
        )
        parsed[field] = [
            _decimal(value, f"timestep_inputs.{field}[{index}]")
            for index, value in enumerate(values)
        ]
    for field in ("dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv"):
        _require(
            all(value > 0 for value in parsed[field]),
            "TIMESTEP_INPUTS",
            f"all {field} entries must be positive",
        )
    for spacing, inverse in (
        ("dx_m", "dxi_m_inv"),
        ("dy_m", "dyi_m_inv"),
        ("dz_m", "dzi_m_inv"),
    ):
        _require(
            float(parsed[inverse]) == _binary64_reciprocal(parsed[spacing], f"{spacing}"),
            "TIMESTEP_INVERSE_MISMATCH",
            f"{inverse} is not the binary64 reciprocal of {spacing}",
        )
    for spacing_array, inverse_array in (("dzc_m", "dzci_m_inv"), ("dzf_m", "dzfi_m_inv")):
        _require(
            all(
                float(inverse_value)
                == _binary64_reciprocal(spacing_value, f"{spacing_array}[{index}]")
                for index, (spacing_value, inverse_value) in enumerate(
                    zip(parsed[spacing_array], parsed[inverse_array], strict=True)
                )
            ),
            "TIMESTEP_INVERSE_MISMATCH",
            f"{inverse_array} does not contain exact source binary64 reciprocals",
        )
    return parsed


def _validate_resources(resources: Any, completed_intervals: int) -> None:
    required = {"ram_samples", "vram_samples", "step_timing_samples"}
    _require(
        isinstance(resources, dict) and set(resources) == required,
        "RESOURCE_RECORDS",
        "manifest resource sample groups are incomplete",
    )
    for name, records in resources.items():
        _require(isinstance(records, list), "RESOURCE_RECORDS", f"{name} must be an array")
        if name in {"ram_samples", "vram_samples"}:
            _require(bool(records), "RESOURCE_RECORDS", f"{name} must contain at least one sample")
        elif completed_intervals > 0:
            _require(
                bool(records),
                "RESOURCE_RECORDS",
                "step_timing_samples may be empty only when no interval completed",
            )
        previous_time = Decimal("-1")
        previous_step = -1
        for index, record in enumerate(records):
            _require(
                isinstance(record, dict), "RESOURCE_RECORDS", f"{name}[{index}] must be an object"
            )
            if name == "ram_samples":
                _require(
                    set(record) == {"elapsed_s", "rss_bytes"},
                    "RESOURCE_RECORDS",
                    "RAM sample fields are invalid",
                )
                elapsed = _decimal(record["elapsed_s"], "RAM elapsed_s")
                amount = _integer(record["rss_bytes"], "RAM rss_bytes")
            elif name == "vram_samples":
                _require(
                    set(record) == {"elapsed_s", "used_bytes"},
                    "RESOURCE_RECORDS",
                    "VRAM sample fields are invalid",
                )
                elapsed = _decimal(record["elapsed_s"], "VRAM elapsed_s")
                amount = _integer(record["used_bytes"], "VRAM used_bytes")
            else:
                _require(
                    set(record) == {"step", "elapsed_s"},
                    "RESOURCE_RECORDS",
                    "step timing sample fields are invalid",
                )
                step = record["step"]
                _require(
                    type(step) is int and step >= 0,
                    "RESOURCE_RECORDS",
                    "step timing step must be a nonnegative JSON integer",
                )
                elapsed = _decimal(record["elapsed_s"], "step timing elapsed_s")
                amount = 0
                _require(
                    step > previous_step,
                    "RESOURCE_ORDER",
                    "step timing samples must have increasing step indexes",
                )
                previous_step = step
            _require(
                elapsed >= 0 and elapsed > previous_time,
                "RESOURCE_ORDER",
                f"{name} sample times must be nonnegative and increasing",
            )
            _require(amount >= 0, "RESOURCE_RECORDS", f"{name} samples cannot be negative")
            previous_time = elapsed


def _validate_pressure_record(record: Any) -> None:
    required = {"kind", "iterative_pressure_iterations", "iterative_pressure_residual", "reason"}
    _require(
        isinstance(record, dict) and set(record) == required,
        "PRESSURE_RECORD",
        "pressure-solver record is incomplete",
    )
    _require(
        record["kind"] == "direct_fft_xy_tridiagonal_z",
        "PRESSURE_RECORD",
        "candidate5 pressure solver identity is unexpected",
    )
    _require(
        record["iterative_pressure_iterations"] == NOT_APPLICABLE,
        "NOT_APPLICABLE",
        "direct pressure solver iteration count must use not_applicable",
    )
    _require(
        record["iterative_pressure_residual"] == NOT_APPLICABLE,
        "NOT_APPLICABLE",
        "direct pressure solver iterative residual must use not_applicable",
    )
    _require(
        isinstance(record["reason"], str)
        and all(
            word in record["reason"].lower()
            for word in ("direct", "fft", "tridiagonal", "continuity", "projection")
        ),
        "PRESSURE_RECORD",
        "pressure reason must name direct FFT/tridiagonal and continuity/projection evidence",
    )


def _parse_csv(data: bytes, expected_header: Sequence[str], filename: str) -> list[dict[str, str]]:
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AnalyzerError("INVALID_UTF8", f"{filename} is not strict UTF-8") from exc
    _require(not decoded.startswith("\ufeff"), "INVALID_UTF8", f"{filename} must not contain a BOM")
    _require(
        "\r" not in decoded and decoded.endswith("\n") and not decoded.endswith("\n\n"),
        "CSV_NEWLINES",
        f"{filename} must use LF and one trailing newline",
    )
    try:
        records = list(csv.reader(io.StringIO(decoded, newline=""), strict=True))
    except csv.Error as exc:
        raise AnalyzerError("CSV_SYNTAX", f"{filename} has malformed CSV syntax") from exc
    _require(
        bool(records) and tuple(records[0]) == tuple(expected_header),
        "CSV_HEADER",
        f"{filename} header does not exactly match candidate5 schema",
    )
    canonical = io.StringIO(newline="")
    writer = csv.writer(canonical, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerows(records)
    _require(
        canonical.getvalue().encode("utf-8") == data,
        "CSV_ENCODING",
        f"{filename} is not in canonical CSV encoding",
    )
    result: list[dict[str, str]] = []
    for line_number, fields in enumerate(records[1:], start=2):
        _require(
            len(fields) == len(expected_header),
            "CSV_WIDTH",
            f"{filename}:{line_number} has the wrong column count",
        )
        _require(
            all(field != "" for field in fields),
            "CSV_EMPTY_FIELD",
            f"{filename}:{line_number} has an empty field",
        )
        result.append(dict(zip(expected_header, fields, strict=True)))
    return result


def _face_class_valid(face: str, source_class: str) -> bool:
    if source_class in {"active_slot", "inactive_slot", "top_offmask"}:
        return face == "zhigh"
    if source_class == "bottom_return":
        return face == "zlow"
    if source_class == "periodic":
        return face in {"xlow", "xhigh", "ylow", "yhigh"}
    return source_class in {"other_inflow", "other_outflow"}


def _valid_scan_record(row: Mapping[str, str], *, table_kind: str) -> None:
    state = _integer(row["state_index"], "state_index")
    interval = _integer(row["transport_interval_index"], "transport_interval_index")
    stage = row["stage_id"]
    face = row["face"]
    source_class = row["source_class"]
    allowed_stages = PHASE_STAGES if table_kind == "phase" else VELOCITY_STAGES
    _require(0 <= state < STATE_COUNT, "ORPHAN_STATE", "audit row state_index is outside 0..14")
    _require(
        -1 <= interval < INTERVAL_COUNT,
        "ORPHAN_INTERVAL",
        "audit row interval index is outside -1..13",
    )
    _require(stage in allowed_stages, "UNKNOWN_STAGE", f"unknown {table_kind} stage_id: {stage}")
    _require(face in FACES, "UNKNOWN_FACE", f"unknown face: {face}")
    _require(
        source_class in SOURCE_CLASSES,
        "UNKNOWN_SOURCE_CLASS",
        f"unknown source_class: {source_class}",
    )
    _require(
        _face_class_valid(face, source_class),
        "INVALID_FACE_CLASS",
        "source_class is incompatible with the declared face",
    )
    if table_kind == "phase":
        _require(
            (face, source_class) in PHASE_FACE_CLASSES,
            "INVALID_FACE_CLASS",
            "phase row uses a face/class pair outside the frozen schema",
        )
        _require(
            interval >= 0 and state == interval,
            "ORPHAN_PHASE_JOIN",
            "phase rows use schedule state k for every stage in interval k",
        )
    elif stage == "initial_u0":
        _require(
            (face, source_class) in VELOCITY_FACE_CLASSES,
            "INVALID_FACE_CLASS",
            "velocity row uses a face/class pair outside the frozen schema",
        )
        _require(
            state == 0 and interval == -1,
            "ORPHAN_VELOCITY_JOIN",
            "initial_u0 must use state 0 and interval -1",
        )
    elif stage == "pre_vof":
        _require(
            (face, source_class) in VELOCITY_FACE_CLASSES,
            "INVALID_FACE_CLASS",
            "velocity row uses a face/class pair outside the frozen schema",
        )
        _require(
            interval >= 0 and state == interval,
            "ORPHAN_VELOCITY_JOIN",
            "pre_vof velocity row must describe incoming U_k",
        )
    else:
        _require(
            (face, source_class) in VELOCITY_FACE_CLASSES,
            "INVALID_FACE_CLASS",
            "velocity row uses a face/class pair outside the frozen schema",
        )
        _require(
            interval >= 0 and state == interval + 1,
            "ORPHAN_VELOCITY_JOIN",
            "projection/corrected velocity row must describe U_(k+1)",
        )


def _scan_sort_key(row: Mapping[str, str], *, table_kind: str) -> tuple[Any, ...]:
    state = int(row["state_index"])
    interval = int(row["transport_interval_index"])
    if table_kind == "phase":
        stage_rank = PHASE_STAGES.index(row["stage_id"])
        return (
            interval,
            state,
            stage_rank,
            PHASE_FACE_CLASSES.index((row["face"], row["source_class"])),
            PROPERTIES.index(row["property"]),
        )
    stage_order = ("initial_u0", "pre_vof", "projection_override", "corrected_endpoint")
    return (
        interval,
        state,
        stage_order.index(row["stage_id"]),
        VELOCITY_FACE_CLASSES.index((row["face"], row["source_class"])),
        COMPONENTS.index(row["component"]),
    )


def _nonfinite_failure_token(token: str) -> bool:
    return token in {"NaN", "+Inf", "-Inf"}


def _validated_slot_cells(
    slot_masks: tuple[frozenset[tuple[int, int]], ...],
) -> frozenset[tuple[int, int]]:
    _require(
        isinstance(slot_masks, tuple) and len(slot_masks) in {0, 1, 4},
        "SCAN_PLAN",
        "the frozen paired-return fixture must pin zero, one, or four slot masks",
    )
    occupied: set[tuple[int, int]] = set()
    for mask_index, mask in enumerate(slot_masks):
        _require(
            isinstance(mask, frozenset) and len(mask) == 240,
            "SCAN_PLAN",
            f"slot mask {mask_index} must contain exactly 240 unique cells",
        )
        for coordinate in mask:
            _require(
                isinstance(coordinate, tuple)
                and len(coordinate) == 2
                and type(coordinate[0]) is int
                and type(coordinate[1]) is int
                and 1 <= coordinate[0] <= NX
                and 1 <= coordinate[1] <= NY,
                "SCAN_PLAN",
                f"slot mask {mask_index} contains an out-of-bounds cell",
            )
        _require(
            occupied.isdisjoint(mask),
            "SCAN_PLAN",
            f"slot mask {mask_index} overlaps an earlier configured slot",
        )
        occupied.update(mask)
    return frozenset(occupied)


def _wrapped_cell(index: int, extent: int) -> int:
    if index == 0:
        return extent
    if index == extent + 1:
        return 1
    return index


def _expected_scan_cell_count(
    scan_key: tuple[str, ...],
    slot_cells: frozenset[tuple[int, int]],
    active_schedule_indices: frozenset[int],
) -> int:
    table_kind, state_token, interval_token, _stage, face, source_class, _detail = scan_key
    state = int(state_token)
    interval = int(interval_token)
    if table_kind == "phase":
        if face in {"xlow", "xhigh"}:
            return (NY + 2) * (NZ + 2)
        if face in {"ylow", "yhigh"}:
            return NX * (NZ + 2)
        if source_class == "bottom_return":
            return NX * NY
        if source_class == "top_offmask":
            return NX * NY - len(slot_cells)
        selected_index = interval
        slot_class_active = source_class == "active_slot"
        return (
            len(slot_cells)
            if (selected_index in active_schedule_indices) == slot_class_active
            else 0
        )

    if source_class == "bottom_return":
        return (NX + 2) * (NY + 2)
    padded_slot_cells = sum(
        (
            _wrapped_cell(i, NX),
            _wrapped_cell(j, NY),
        )
        in slot_cells
        for i in range(NX + 2)
        for j in range(NY + 2)
    )
    if source_class == "top_offmask":
        return (NX + 2) * (NY + 2) - padded_slot_cells
    slot_class_active = source_class == "active_slot"
    return padded_slot_cells if (state in active_schedule_indices) == slot_class_active else 0


def _location_in_declared_scan_domain(
    row: Mapping[str, str],
    *,
    table_kind: str,
    slot_cells: frozenset[tuple[int, int]],
    active_schedule_indices: frozenset[int],
    location: tuple[int, int, int],
) -> bool:
    i, j, k = location
    if not (0 <= i <= NX + 1 and 0 <= j <= NY + 1 and 0 <= k <= NZ + 1):
        return False
    face = row["face"]
    source_class = row["source_class"]
    if table_kind == "phase":
        if face == "xlow":
            return i == 0
        if face == "xhigh":
            return i == NX + 1
        if face == "ylow":
            return i in range(1, NX + 1) and j == 0
        if face == "yhigh":
            return i in range(1, NX + 1) and j == NY + 1
        if face == "zlow":
            return i in range(1, NX + 1) and j in range(1, NY + 1) and k == 0
        if face != "zhigh" or k != NZ + 1 or not (1 <= i <= NX and 1 <= j <= NY):
            return False
        slot_cell = (i, j) in slot_cells
        if source_class == "top_offmask":
            return not slot_cell
        selected_class_active = source_class == "active_slot"
        schedule_active = int(row["transport_interval_index"]) in active_schedule_indices
        return slot_cell and schedule_active == selected_class_active

    if face == "zlow":
        return source_class == "bottom_return" and k == 0
    if face != "zhigh":
        return False
    expected_k = NZ if row["component"] == "w" else NZ + 1
    if k != expected_k:
        return False
    wrapped_slot_cell = (
        _wrapped_cell(i, NX),
        _wrapped_cell(j, NY),
    ) in slot_cells
    if source_class == "top_offmask":
        return not wrapped_slot_cell
    selected_class_active = source_class == "active_slot"
    schedule_active = int(row["state_index"]) in active_schedule_indices
    return wrapped_slot_cell and schedule_active == selected_class_active


def _scan_counts_and_evidence(
    rows: Sequence[Mapping[str, str]],
    *,
    table_kind: str,
    expected_scan_cells: Mapping[tuple[str, ...], int],
    slot_cells: frozenset[tuple[int, int]],
    active_schedule_indices: frozenset[int],
) -> list[str]:
    evidence_issues: list[str] = []
    grouped_counts: dict[tuple[Any, ...], set[int]] = {}
    for row in rows:
        scanned = _integer(row["scanned_cells"], "scanned_cells")
        mismatch = _integer(row["mismatch_count"], "mismatch_count")
        nonfinite = _integer(row["nonfinite_count"], "nonfinite_count")
        _require(
            0 <= mismatch and 0 <= nonfinite and mismatch + nonfinite <= scanned,
            "SCAN_COUNT",
            "finite mismatch and nonfinite counts must be disjoint and no greater than scanned cells",
        )
        error = _decimal(row["max_abs_error"], "max_abs_error")
        _require(error >= 0, "NEGATIVE_ERROR", "max_abs_error cannot be negative")
        error_binary64 = _as_binary64(error, "max_abs_error")
        failure_indexes = (row["first_bad_i"], row["first_bad_j"], row["first_bad_k"])
        expected_name, observed_name = (
            ("expected", "observed") if table_kind == "phase" else ("requested", "applied")
        )
        scan_key = (
            table_kind,
            *(row[key] for key in (PHASE_HEADER if table_kind == "phase" else VELOCITY_HEADER)[:6]),
        )
        _require(
            scan_key in expected_scan_cells,
            "UNEXPECTED_SCAN_KEY",
            "audit row has no independently pinned scan-cell count",
        )
        expected_scanned = expected_scan_cells[scan_key]
        _require(
            type(expected_scanned) is int and expected_scanned >= 0,
            "SCAN_PLAN",
            "independent expected scan-cell count must be a nonnegative integer",
        )
        _require(
            scanned == expected_scanned,
            "SCAN_CELL_COUNT",
            "scanned_cells differs from the independent expected scan count",
        )
        _require(
            scanned > 0 or expected_scanned == 0,
            "SCAN_CELL_COUNT",
            "zero scanned cells are valid only for an independently declared empty class",
        )
        if mismatch == 0 and nonfinite == 0:
            _require(error == 0, "SCAN_ERROR", "zero-defect row must report zero max_abs_error")
            _require(
                all(value == NOT_APPLICABLE for value in failure_indexes),
                "NOT_APPLICABLE",
                "zero-defect row indexes must all be not_applicable",
            )
            _require(
                row[expected_name] == NOT_APPLICABLE and row[observed_name] == NOT_APPLICABLE,
                "NOT_APPLICABLE",
                "zero-defect row values must both be not_applicable",
            )
        else:
            for index_name, value in zip(
                ("first_bad_i", "first_bad_j", "first_bad_k"), failure_indexes, strict=True
            ):
                index = _integer(value, index_name)
                _require(index >= 0, "INVALID_INDEX", f"{index_name} must be nonnegative")
            _require(
                int(failure_indexes[0]) <= NX + 1
                and int(failure_indexes[1]) <= NY + 1
                and int(failure_indexes[2]) <= NZ + 1,
                "INVALID_INDEX",
                "first-failure location is outside the frozen padded grid bounds",
            )
            location = tuple(int(value) for value in failure_indexes)
            _require(
                _location_in_declared_scan_domain(
                    row,
                    table_kind=table_kind,
                    slot_cells=slot_cells,
                    active_schedule_indices=active_schedule_indices,
                    location=location,
                ),
                "INVALID_INDEX",
                "first-failure location is outside the declared face/class/component scan domain",
            )
            expected_token = row[expected_name]
            observed_token = row[observed_name]
            expected_nonfinite = _nonfinite_failure_token(expected_token)
            observed_nonfinite = _nonfinite_failure_token(observed_token)
            expected_value = None if expected_nonfinite else _decimal(expected_token, expected_name)
            observed_value = None if observed_nonfinite else _decimal(observed_token, observed_name)
            if expected_nonfinite or observed_nonfinite:
                _require(
                    nonfinite > 0,
                    "NONFINITE_TOKEN",
                    "a non-finite first-failure value requires a nonfinite_count",
                )
                first_pair_error: float | None = None
            else:
                assert expected_value is not None and observed_value is not None
                expected_binary64 = _as_binary64(expected_value, expected_name)
                observed_binary64 = _as_binary64(observed_value, observed_name)
                _require(
                    mismatch > 0 and observed_binary64 != expected_binary64,
                    "SCAN_ERROR",
                    "finite first-failure values must differ as binary64 for a counted mismatch",
                )
                difference = observed_binary64 - expected_binary64
                _require(
                    math.isfinite(difference),
                    "SCAN_ERROR",
                    "finite first-failure subtraction must remain finite in binary64",
                )
                first_pair_error = abs(difference)
            _require(
                (mismatch == 0 and error == 0) or (mismatch > 0 and error > 0),
                "SCAN_ERROR",
                "max_abs_error must be zero without finite mismatches and positive with them",
            )
            if first_pair_error is not None:
                if mismatch == 1:
                    _require(
                        error_binary64 == first_pair_error,
                        "SCAN_ERROR",
                        "a single finite mismatch must equal max_abs_error in binary64",
                    )
                else:
                    _require(
                        error_binary64 >= first_pair_error,
                        "SCAN_ERROR",
                        "max_abs_error cannot be smaller than the first finite-pair error",
                    )
            if mismatch > 0:
                evidence_issues.append(f"{table_kind.upper()}_MISMATCH")
            if nonfinite > 0:
                evidence_issues.append(f"{table_kind.upper()}_NONFINITE")
        if table_kind == "phase":
            group = tuple(
                row[key]
                for key in (
                    "state_index",
                    "transport_interval_index",
                    "stage_id",
                    "face",
                    "source_class",
                )
            )
        else:
            group = tuple(
                row[key]
                for key in (
                    "state_index",
                    "transport_interval_index",
                    "stage_id",
                    "face",
                    "source_class",
                )
            )
        grouped_counts.setdefault(group, set()).add(scanned)
    _require(
        all(len(counts) == 1 for counts in grouped_counts.values()),
        "SCAN_COUNT_JOIN",
        "counts differ across property/component summaries of one scan",
    )
    return evidence_issues


def _validate_phase_table(
    data: bytes,
    expected_scan_cells: Mapping[tuple[str, ...], int],
    required_keys: set[tuple[str, ...]],
    slot_cells: frozenset[tuple[int, int]],
    active_schedule_indices: frozenset[int],
) -> tuple[list[dict[str, str]], list[str]]:
    rows = _parse_csv(data, PHASE_HEADER, PHASE_FILE)
    seen: set[tuple[Any, ...]] = set()
    sort_keys: list[tuple[Any, ...]] = []
    for row in rows:
        _valid_scan_record(row, table_kind="phase")
        prop = row["property"]
        _require(prop in PROPERTIES, "UNKNOWN_PROPERTY", f"unknown property: {prop}")
        key = tuple(row[field] for field in PHASE_HEADER[:6])
        _require(key not in seen, "DUPLICATE_KEY", "duplicate phase/property row key")
        seen.add(key)
        sort_keys.append(_scan_sort_key(row, table_kind="phase"))
    _require(
        sort_keys == sorted(sort_keys),
        "ROW_ORDER",
        "phase/property rows are not in canonical deterministic order",
    )
    _require(
        seen == required_keys,
        "PHASE_KEYS",
        "phase/property rows differ from the exact v1.2 prefix key set",
    )
    _validate_group_completeness(rows, table_kind="phase")
    return rows, _scan_counts_and_evidence(
        rows,
        table_kind="phase",
        expected_scan_cells=expected_scan_cells,
        slot_cells=slot_cells,
        active_schedule_indices=active_schedule_indices,
    )


def _validate_boundary_table(
    data: bytes,
    expected_scan_cells: Mapping[tuple[str, ...], int],
    required_keys: set[tuple[str, ...]],
    slot_cells: frozenset[tuple[int, int]],
    active_schedule_indices: frozenset[int],
) -> tuple[list[dict[str, str]], list[str]]:
    rows = _parse_csv(data, VELOCITY_HEADER, VELOCITY_FILE)
    seen: set[tuple[str, ...]] = set()
    sort_keys: list[tuple[Any, ...]] = []
    for row in rows:
        _valid_scan_record(row, table_kind="velocity")
        component = row["component"]
        _require(component in COMPONENTS, "UNKNOWN_COMPONENT", f"unknown component: {component}")
        key = tuple(row[field] for field in VELOCITY_HEADER[:6])
        _require(key not in seen, "DUPLICATE_KEY", "duplicate boundary-velocity row key")
        seen.add(key)
        sort_keys.append(_scan_sort_key(row, table_kind="velocity"))
    _require(
        sort_keys == sorted(sort_keys),
        "ROW_ORDER",
        "boundary-velocity rows are not in canonical deterministic order",
    )
    _require(
        seen == required_keys,
        "VELOCITY_KEYS",
        "boundary-velocity rows differ from the exact v1.2 prefix key set",
    )
    _validate_group_completeness(rows, table_kind="velocity")
    return rows, _scan_counts_and_evidence(
        rows,
        table_kind="velocity",
        expected_scan_cells=expected_scan_cells,
        slot_cells=slot_cells,
        active_schedule_indices=active_schedule_indices,
    )


def _validate_group_completeness(rows: Sequence[Mapping[str, str]], *, table_kind: str) -> None:
    grouped: dict[tuple[str, ...], set[str]] = {}
    for row in rows:
        keys = ("state_index", "transport_interval_index", "stage_id", "face", "source_class")
        group = tuple(row[key] for key in keys)
        detail = row["property"] if table_kind == "phase" else row["component"]
        grouped.setdefault(group, set()).add(detail)
    for group, values in grouped.items():
        if table_kind == "phase":
            required = set(PROPERTIES) if group[2] == "pre_momentum" else {"alpha"}
        else:
            required = set(COMPONENTS)
        _require(
            values == required,
            "INCOMPLETE_SCAN_GROUP",
            f"incomplete fields in {table_kind} scan group {group}",
        )


def _expected_audit_keys(table_kind: str) -> set[tuple[str, ...]]:
    keys: set[tuple[str, ...]] = set()
    if table_kind == "phase":
        for interval in range(INTERVAL_COUNT):
            for stage in PHASE_STAGES:
                for face, source_class in PHASE_FACE_CLASSES:
                    properties = PROPERTIES if stage == "pre_momentum" else ("alpha",)
                    for prop in properties:
                        keys.add(
                            ("phase", str(interval), str(interval), stage, face, source_class, prop)
                        )
    else:
        for face, source_class in VELOCITY_FACE_CLASSES:
            for component in COMPONENTS:
                keys.add(("velocity", "0", "-1", "initial_u0", face, source_class, component))
        for interval in range(INTERVAL_COUNT):
            for face, source_class in VELOCITY_FACE_CLASSES:
                for component in COMPONENTS:
                    keys.add(
                        (
                            "velocity",
                            str(interval),
                            str(interval),
                            "pre_vof",
                            face,
                            source_class,
                            component,
                        )
                    )
                    keys.add(
                        (
                            "velocity",
                            str(interval + 1),
                            str(interval),
                            "projection_override",
                            face,
                            source_class,
                            component,
                        )
                    )
                    keys.add(
                        (
                            "velocity",
                            str(interval + 1),
                            str(interval),
                            "corrected_endpoint",
                            face,
                            source_class,
                            component,
                        )
                    )
    return keys


def _validate_expected_scan_plan(
    expected: Mapping[tuple[str, ...], int],
    slot_masks: tuple[frozenset[tuple[int, int]], ...],
    active_schedule_indices: frozenset[int],
) -> frozenset[tuple[int, int]]:
    slot_cells = _validated_slot_cells(slot_masks)
    _require(
        isinstance(active_schedule_indices, frozenset)
        and all(
            type(index) is int and 0 <= index < STATE_COUNT for index in active_schedule_indices
        ),
        "SCAN_PLAN",
        "active schedule indices must be frozen integer state indices in 0..14",
    )
    expected_keys = _expected_audit_keys("phase") | _expected_audit_keys("velocity")
    _require(
        set(expected) == expected_keys,
        "SCAN_PLAN",
        "independent scan plan does not exactly cover the frozen audit keys",
    )
    _require(
        all(type(count) is int and count >= 0 for count in expected.values()),
        "SCAN_PLAN",
        "independent scan-cell counts must be nonnegative JSON-style integers",
    )
    _require(
        all(
            count == _expected_scan_cell_count(key, slot_cells, active_schedule_indices)
            for key, count in expected.items()
        ),
        "SCAN_PLAN",
        "independent scan counts disagree with the separately pinned slot masks and schedule",
    )
    return slot_cells


def _prefix_keys(manifest: Mapping[str, Any], table_kind: str) -> set[tuple[str, ...]]:
    """Derive the exact v1.2 CSV key prefix from the controlled-stop manifest."""
    reason = manifest["stop_reason"]
    if reason == "normal_completion":
        stop_interval = INTERVAL_COUNT
        terminal_phase_stages = 0
        terminal_velocity_stages = 0
    else:
        stop_interval = manifest["stop_interval_index"]
        terminal_phase_stages = 0
        terminal_velocity_stages = 0
        if reason == "phase_audit":
            terminal_phase_stages = PHASE_STAGES.index(manifest["stop_stage_id"]) + 1
            terminal_velocity_stages = 1  # the K pre_vof velocity group is preserved
        elif reason == "velocity_audit":
            stage = manifest["stop_stage_id"]
            if stage == "pre_vof":
                terminal_velocity_stages = 1
            elif stage == "projection_override":
                terminal_velocity_stages = 2
                terminal_phase_stages = len(PHASE_STAGES)
            elif stage == "corrected_endpoint":
                terminal_velocity_stages = 3
                terminal_phase_stages = len(PHASE_STAGES)
            elif stage == "initial_u0":
                terminal_velocity_stages = -1  # only the initial group is present

    if table_kind == "phase":
        keys: set[tuple[str, ...]] = set()
        for interval in range(min(stop_interval, INTERVAL_COUNT)):
            for stage in PHASE_STAGES:
                properties = PROPERTIES if stage == "pre_momentum" else ("alpha",)
                for face, source_class in PHASE_FACE_CLASSES:
                    keys.update(
                        (str(interval), str(interval), stage, face, source_class, prop)
                        for prop in properties
                    )
        if terminal_phase_stages:
            interval = stop_interval
            for stage in PHASE_STAGES[:terminal_phase_stages]:
                properties = PROPERTIES if stage == "pre_momentum" else ("alpha",)
                for face, source_class in PHASE_FACE_CLASSES:
                    keys.update(
                        (str(interval), str(interval), stage, face, source_class, prop)
                        for prop in properties
                    )
        return keys

    keys = set()
    for face, source_class in VELOCITY_FACE_CLASSES:
        for component in COMPONENTS:
            keys.add(("0", "-1", "initial_u0", face, source_class, component))
    if reason == "velocity_audit" and manifest["stop_stage_id"] == "initial_u0":
        return keys
    for interval in range(min(stop_interval, INTERVAL_COUNT)):
        stages = ("pre_vof", "projection_override", "corrected_endpoint")
        for stage_index, stage in enumerate(stages):
            state = interval if stage_index == 0 else interval + 1
            for face, source_class in VELOCITY_FACE_CLASSES:
                for component in COMPONENTS:
                    keys.add((str(state), str(interval), stage, face, source_class, component))
    if terminal_velocity_stages > 0 and stop_interval < INTERVAL_COUNT:
        stages = ("pre_vof", "projection_override", "corrected_endpoint")
        for stage_index, stage in enumerate(stages[:terminal_velocity_stages]):
            state = stop_interval if stage_index == 0 else stop_interval + 1
            for face, source_class in VELOCITY_FACE_CLASSES:
                for component in COMPONENTS:
                    keys.add(
                        (
                            str(state),
                            str(stop_interval),
                            stage,
                            face,
                            source_class,
                            component,
                        )
                    )
    return keys


def _expected_timestep_states(manifest: Mapping[str, Any]) -> list[int]:
    if manifest["stop_reason"] == "normal_completion":
        return list(range(STATE_COUNT))
    if manifest["stop_reason"] == "velocity_audit" and manifest["stop_stage_id"] == "initial_u0":
        return []
    return list(range(manifest["stop_interval_index"] + 1))


def _binary64_equal(actual: Decimal, expected: float) -> bool:
    """Compare round-trip decimal output to the exact binary64 result."""
    actual_float = float(actual)
    return math.isfinite(actual_float) and math.isfinite(expected) and actual_float == expected


def _timestep_expectations(inputs: Mapping[str, Any], dtic_raw: Decimal) -> dict[str, float | bool]:
    rho1 = float(inputs["rho1_kg_m3"])
    rho2 = float(inputs["rho2_kg_m3"])
    mu1 = float(inputs["mu1_pa_s"])
    mu2 = float(inputs["mu2_pa_s"])
    dlmin = min(
        1.0 / float(inputs["dxi_m_inv"]),
        1.0 / float(inputs["dyi_m_inv"]),
        1.0 / float(inputs["dzi_m_inv"]),
    )
    dlmin = min(dlmin, min(1.0 / float(value) for value in inputs["dzfi_m_inv"]))
    dlmini = dlmin ** (-1)
    nu_max = max(mu1 / rho1, mu2 / rho2)
    cfl_d = float(inputs["cfl_d"])
    cfl_c = float(inputs["cfl_c"])
    dtiv = nu_max * dlmini**2 / cfl_d
    sigma = float(inputs["sigma_n_m"])
    capillary_active = sigma != 0.0
    if capillary_active:
        dtik = math.sqrt(sigma / min(rho1, rho2) * dlmini**3)
    else:
        dtik = float(inputs["small_s_inv"])
    gravity = [float(value) for value in inputs["gravity_m_s2"]]
    dtig = math.sqrt(max(abs(value) for value in gravity) * dlmini)
    zero_fallback = dtic_raw == 0
    dtic_used = 1.0 if zero_fallback else float(dtic_raw)
    sum_rate = dtic_used + dtiv
    dtmax = cfl_c * 2.0 * (sum_rate + math.sqrt(sum_rate**2 + 4.0 * (dtig**2 + dtik**2))) ** (-1)
    dtmax = min(dtmax, 1.0 / dtik)
    return {
        "dtic_used_s_inv": dtic_used,
        "zero_advection_fallback": zero_fallback,
        "nu_max_m2_s": nu_max,
        "h_min_m": dlmin,
        "dlmini_m_inv": dlmini,
        "dtiv_s_inv": dtiv,
        "dtik_s_inv": dtik,
        "dtig_s_inv": dtig,
        "capillary_active": capillary_active,
        "dtmax_s": dtmax,
    }


def _checked_timestep_expectations(
    inputs: Mapping[str, Any], dtic_raw: Decimal
) -> dict[str, float | bool]:
    try:
        expected = _timestep_expectations(inputs, dtic_raw)
    except AnalyzerError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise AnalyzerError(
            "TIMESTEP_ARITHMETIC",
            "binary64 timestep recomputation overflowed or left the real domain",
        ) from exc
    _require(
        all(type(value) is not float or math.isfinite(value) for value in expected.values()),
        "TIMESTEP_ARITHMETIC",
        "binary64 timestep recomputation produced a non-finite intermediate or result",
    )
    return expected


def _parse_bool(token: str, field: str) -> bool:
    _require(token in {"true", "false"}, "INVALID_BOOLEAN", f"{field} must be true or false")
    return token == "true"


def _validate_timestep_table(
    data: bytes, manifest: Mapping[str, Any]
) -> tuple[list[dict[str, str]], list[str]]:
    rows = _parse_csv(data, TIMESTEP_HEADER, TIMESTEP_FILE)
    expected_states = _expected_timestep_states(manifest)
    _require(len(rows) == len(expected_states), "TIMESTEP_ROW_COUNT", "wrong v1.2 prefix row count")
    inputs = _validate_timestep_inputs(manifest["timestep_inputs"])
    fixed_step = inputs["fixed_step_s"]
    fixed_factor = inputs["fixed_step_factor"]
    evidence_issues: list[str] = []
    for row, expected_state in zip(rows, expected_states, strict=True):
        state_index = _integer(row["state_index"], "state_index")
        _require(
            state_index == expected_state,
            "TIMESTEP_STATE_ORDER",
            "timestep rows must match the state-only v1.2 prefix in ascending order",
        )
        state = expected_state
        time = _decimal(row["time_s"], "time_s")
        dt = _decimal(row["dt_s"], "dt_s")
        raw_rate = _decimal(row["dtic_raw_s_inv"], "dtic_raw_s_inv")
        used_rate = _decimal(row["dtic_used_s_inv"], "dtic_used_s_inv")
        _require(
            raw_rate >= 0 and used_rate > 0 and dt > 0,
            "TIMESTEP_RANGE",
            "reported timestep rates and dt are invalid",
        )
        _require(
            _binary64_equal(dt, float(fixed_step)),
            "TIMESTEP_INPUT_MISMATCH",
            "dt_s differs from frozen fixed_step_s input",
        )
        expected_time = float(inputs["time_start_s"]) + state * float(fixed_step)
        _require(
            _binary64_equal(time, expected_time),
            "TIMESTEP_TIME",
            "state time differs from time_start + state_index*fixed_step",
        )
        zero_fallback = _parse_bool(row["zero_advection_fallback"], "zero_advection_fallback")
        nu_max = _decimal(row["nu_max_m2_s"], "nu_max_m2_s")
        h_min = _decimal(row["h_min_m"], "h_min_m")
        dlmini = _decimal(row["dlmini_m_inv"], "dlmini_m_inv")
        dtiv = _decimal(row["dtiv_s_inv"], "dtiv_s_inv")
        dtik = _decimal(row["dtik_s_inv"], "dtik_s_inv")
        dtig = _decimal(row["dtig_s_inv"], "dtig_s_inv")
        capillary = _parse_bool(row["capillary_active"], "capillary_active")
        dtmax = _decimal(row["dtmax_s"], "dtmax_s")
        row_factor = _decimal(row["fixed_step_factor"], "fixed_step_factor")
        dt_ratio = _decimal(row["dt_over_dtmax"], "dt_over_dtmax")
        guard_token = row["guard_pass"]
        is_terminal = manifest["stop_reason"] == "normal_completion" and state == INTERVAL_COUNT
        is_guard_stop = (
            manifest["stop_reason"] == "timestep_guard" and state == manifest["stop_interval_index"]
        )
        if is_terminal:
            _require(
                guard_token == NOT_APPLICABLE,
                "TERMINAL_GUARD",
                "terminal timestep row must use guard_pass=not_applicable",
            )
            guard_pass: bool | None = None
        else:
            guard_pass = _parse_bool(guard_token, "guard_pass")
        _require(
            dtiv > 0 and dtik > 0 and dtig >= 0 and dtmax > 0 and h_min > 0 and dlmini > 0,
            "TIMESTEP_RANGE",
            "reported timestep terms are outside their valid ranges",
        )

        expected = _checked_timestep_expectations(inputs, raw_rate)
        _require(
            zero_fallback == expected["zero_advection_fallback"],
            "TIMESTEP_FALLBACK",
            "zero-advection fallback flag is inconsistent",
        )
        _require(
            capillary == expected["capillary_active"],
            "TIMESTEP_CAPILLARY",
            "capillary_active flag is inconsistent with sigma",
        )
        for field, value in (
            ("dtic_used_s_inv", used_rate),
            ("nu_max_m2_s", nu_max),
            ("h_min_m", h_min),
            ("dlmini_m_inv", dlmini),
            ("dtiv_s_inv", dtiv),
            ("dtik_s_inv", dtik),
            ("dtig_s_inv", dtig),
            ("dtmax_s", dtmax),
        ):
            _require(
                _binary64_equal(value, float(expected[field])),
                "TIMESTEP_TERM_MISMATCH",
                f"{field} differs from independent recomputation",
            )
        _require(
            _binary64_equal(row_factor, float(fixed_factor)),
            "TIMESTEP_FACTOR",
            "row fixed_step_factor differs from input factor",
        )
        expected_ratio = float(dt) / float(expected["dtmax_s"])
        guard_limit = float(fixed_factor) * float(expected["dtmax_s"])
        _require(
            math.isfinite(expected_ratio) and math.isfinite(guard_limit),
            "TIMESTEP_NONFINITE",
            "guard ratio and fixed-step limit must be finite",
        )
        _require(
            _binary64_equal(dt_ratio, expected_ratio),
            "TIMESTEP_RATIO",
            "dt_over_dtmax is inconsistent",
        )
        if guard_pass is not None:
            derived_guard = float(dt) <= guard_limit
            _require(
                guard_pass == derived_guard,
                "TIMESTEP_GUARD",
                "guard_pass differs from the independently recomputed guard",
            )
            if not guard_pass:
                evidence_issues.append("FIXED_STEP_GUARD_FAIL")
        _require(
            (guard_pass is False) == is_guard_stop,
            "GUARD_PREFIX",
            "false guard row must be exactly the declared guard-stop state",
        )

    final_time = _decimal(manifest["final_time_s"], "final_time_s")
    expected_final_time = float(inputs["time_start_s"]) + manifest[
        "completed_interval_count"
    ] * float(fixed_step)
    _require(
        _binary64_equal(final_time, expected_final_time),
        "FINAL_TIME",
        "manifest final_time_s differs from time_start + completed_interval_count*dt",
    )
    return rows, evidence_issues


def _row_failed(row: Mapping[str, str]) -> bool:
    return int(row["mismatch_count"]) > 0 or int(row["nonfinite_count"]) > 0


def _validate_stop_evidence(
    manifest: Mapping[str, Any],
    phase_rows: Sequence[Mapping[str, str]],
    velocity_rows: Sequence[Mapping[str, str]],
    timestep_rows: Sequence[Mapping[str, str]],
) -> None:
    reason = manifest["stop_reason"]
    failed_phase = [row for row in phase_rows if _row_failed(row)]
    failed_velocity = [row for row in velocity_rows if _row_failed(row)]
    false_guards = [row for row in timestep_rows if row["guard_pass"] == "false"]
    if reason == "normal_completion":
        _require(
            not failed_phase and not failed_velocity and not false_guards,
            "RUN_STOP_PREFIX",
            "normal completion cannot contain audit failures or a rejected guard",
        )
        return
    if reason == "timestep_guard":
        _require(
            not failed_phase
            and not failed_velocity
            and len(false_guards) == 1
            and int(false_guards[0]["state_index"]) == manifest["stop_interval_index"],
            "RUN_STOP_PREFIX",
            "timestep-guard stop must preserve successful audits and one false guard at K",
        )
        return
    _require(not false_guards, "RUN_STOP_PREFIX", "audit stops require passing timestep guards")
    if reason == "phase_audit":
        interval = str(manifest["stop_interval_index"])
        stage = manifest["stop_stage_id"]
        stopping = [
            row
            for row in failed_phase
            if row["transport_interval_index"] == interval and row["stage_id"] == stage
        ]
        _require(
            bool(stopping) and len(stopping) == len(failed_phase) and not failed_velocity,
            "RUN_STOP_PREFIX",
            "phase stop must have failures only in its complete stopping stage",
        )
        return
    interval = str(manifest["stop_interval_index"])
    state = str(manifest["stop_state_index"])
    stage = manifest["stop_stage_id"]
    csv_interval = "-1" if stage == "initial_u0" else interval
    stopping = [
        row
        for row in failed_velocity
        if row["transport_interval_index"] == csv_interval
        and row["state_index"] == state
        and row["stage_id"] == stage
    ]
    _require(
        bool(stopping) and len(stopping) == len(failed_velocity) and not failed_phase,
        "RUN_STOP_PREFIX",
        "velocity stop must have failures only in its complete stopping stage",
    )


def analyze_bundle(
    manifest_bytes: bytes,
    files: Mapping[str, bytes],
    pins: ExpectedProvenance,
) -> AnalysisReport:
    """Analyze an offline bundle, never emitting a scientific PASS decision."""
    try:
        _require(
            sha256_bytes(manifest_bytes) == pins.manifest_sha256,
            "MANIFEST_HASH",
            "manifest bytes differ from external hash pin",
        )
        manifest = parse_manifest_bytes(manifest_bytes)
        _validate_manifest(manifest, pins)
        slot_cells = _validate_expected_scan_plan(
            pins.expected_scan_cells,
            pins.slot_masks,
            pins.active_schedule_indices,
        )
        required_phase_keys = _prefix_keys(manifest, "phase")
        required_velocity_keys = _prefix_keys(manifest, "velocity")
        _require(
            set(files) == set(OUTPUT_FILES),
            "OUTPUT_FILE_SET",
            "bundle must contain exactly the three candidate5 CSV files",
        )
        actual_counts: dict[str, int] = {}
        evidence_issues: list[str] = []
        parsed_rows: dict[str, list[dict[str, str]]] = {}
        for filename in OUTPUT_FILES:
            data = files[filename]
            _require(isinstance(data, bytes), "OUTPUT_TYPE", f"{filename} must be bytes")
            _require(
                sha256_bytes(data) == manifest["files_sha256"][filename],
                "OUTPUT_HASH",
                f"{filename} hash differs from run manifest",
            )
            if filename == PHASE_FILE:
                rows, issues = _validate_phase_table(
                    data,
                    pins.expected_scan_cells,
                    required_phase_keys,
                    slot_cells,
                    pins.active_schedule_indices,
                )
            elif filename == VELOCITY_FILE:
                rows, issues = _validate_boundary_table(
                    data,
                    pins.expected_scan_cells,
                    required_velocity_keys,
                    slot_cells,
                    pins.active_schedule_indices,
                )
            else:
                rows, issues = _validate_timestep_table(data, manifest)
            parsed_rows[filename] = rows
            actual_counts[filename] = len(rows)
            _require(
                len(rows) == manifest["row_counts"][filename],
                "ROW_COUNT_MISMATCH",
                f"{filename} row count differs from run manifest",
            )
            evidence_issues.extend(issues)
        _validate_stop_evidence(
            manifest,
            parsed_rows[PHASE_FILE],
            parsed_rows[VELOCITY_FILE],
            parsed_rows[TIMESTEP_FILE],
        )
        run_ok = manifest["run_status"] == "completed" and manifest["solver_exit_code"] == 0
        if not run_ok:
            evidence_issues.append("SOLVER_RUN_INCOMPLETE")
        return AnalysisReport(
            structural_disposition="complete",
            evidence_disposition="fail" if evidence_issues else "complete",
            decision=DECISION_NOT_ADJUDICATED,
            issue_codes=tuple(sorted(set(evidence_issues))),
            row_counts=actual_counts,
            timestep_rows_checked=actual_counts[TIMESTEP_FILE],
        )
    except AnalyzerError as exc:
        return AnalysisReport(
            structural_disposition="fail",
            evidence_disposition="fail",
            decision=DECISION_NOT_ADJUDICATED,
            issue_codes=(exc.code,),
            row_counts={},
            timestep_rows_checked=0,
        )
    except (ArithmeticError, ValueError):
        return AnalysisReport(
            structural_disposition="fail",
            evidence_disposition="fail",
            decision=DECISION_NOT_ADJUDICATED,
            issue_codes=("ANALYZER_ARITHMETIC",),
            row_counts={},
            timestep_rows_checked=0,
        )
