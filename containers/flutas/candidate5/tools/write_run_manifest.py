#!/usr/bin/env python3
"""Assemble the frozen run manifest from candidate5 runtime artifacts.

This producer binds hashes and supervisor stop/resource metadata. It does not
decide whether CSV rows are scientifically valid; the independent analyzer
performs that check before B1 pre-run eligibility.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_SHA256 = "4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492"
PRODUCER_SCHEMA = "candidate5-observability-v1.2"
MANIFEST_SCHEMA = "candidate5-run-manifest-v2"
FILES = {
    "phase-property-stage-audit.csv": [
        "state_index", "transport_interval_index", "stage_id", "face", "source_class",
        "property", "scanned_cells", "mismatch_count", "nonfinite_count", "max_abs_error",
        "first_bad_i", "first_bad_j", "first_bad_k", "expected", "observed",
    ],
    "boundary-velocity-stage-audit.csv": [
        "state_index", "transport_interval_index", "stage_id", "face", "source_class",
        "component", "scanned_cells", "mismatch_count", "nonfinite_count", "max_abs_error",
        "first_bad_i", "first_bad_j", "first_bad_k", "requested", "applied",
    ],
    "timestep-restriction.csv": [
        "state_index", "time_s", "dt_s", "dtic_raw_s_inv", "dtic_used_s_inv",
        "zero_advection_fallback", "nu_max_m2_s", "h_min_m", "dlmini_m_inv",
        "dtiv_s_inv", "dtik_s_inv", "dtig_s_inv", "capillary_active", "dtmax_s",
        "fixed_step_factor", "dt_over_dtmax", "guard_pass",
    ],
}
INPUT_FILES = {"dns.in", "source-boundary.in", "vof.in"}
TIMESTEP_INPUT_KEYS = {
    "time_scheme", "time_start_s", "real_kind", "precision_digits", "machine_epsilon",
    "small_s_inv", "cfl_c", "cfl_d", "rho1_kg_m3", "rho2_kg_m3", "mu1_pa_s",
    "mu2_pa_s", "dx_m", "dy_m", "dz_m", "dxi_m_inv", "dyi_m_inv", "dzi_m_inv",
    "dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv", "sigma_n_m", "gravity_m_s2",
    "fixed_step_factor", "fixed_step_s",
}
SCAN_ORDER = {
    "phase_property": [
        "transport_interval_index", "state_index", "stage_id", "face", "source_class", "property",
    ],
    "boundary_velocity": [
        "transport_interval_index", "state_index", "stage_id", "face", "source_class", "component",
    ],
    "timestep": ["state_index"],
}
REDUCTION_ORDER = {
    "cell_scan_order": "i,j,k ascending",
    "floating_point": "candidate real(rp) binary64",
    "max_error_order": "first lexicographic location on a tie",
}
PRESSURE_SOLVER = {
    "iterative_pressure_iterations": "not_applicable",
    "iterative_pressure_residual": "not_applicable",
    "kind": "direct_fft_xy_tridiagonal_z",
    "reason": "The pinned pressure path uses direct FFT solves in x/y and a tridiagonal z solve; continuity and projection are recorded directly.",
}
DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise ValueError(f"JSON must be UTF-8 without BOM and end in LF: {path}")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"invalid JSON number {token}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid strict JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_string(value: Any, label: str) -> Decimal:
    if not isinstance(value, str) or DECIMAL.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} is not a decimal") from exc


def _case_inputs(case_root: Path) -> dict[str, str]:
    if not case_root.is_dir() or case_root.is_symlink():
        raise ValueError("case root must be a real directory")
    found: set[str] = set()
    for path in case_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"case inputs cannot be symlinks: {path}")
        if path.is_file():
            relative = path.relative_to(case_root).as_posix()
            if relative in found:
                raise ValueError(f"duplicate case input path: {relative}")
            found.add(relative)
        elif not path.is_dir():
            raise ValueError(f"case tree contains a non-regular entry: {path}")
    if found != INPUT_FILES:
        raise ValueError(f"case input set differs from frozen fixture: {sorted(found)}")
    return {name: sha256(case_root / name) for name in sorted(found)}


def _planned_intervals(case_root: Path) -> int:
    records = []
    for line in (case_root / "dns.in").read_text(encoding="utf-8").splitlines():
        text = line.split("!", 1)[0].split("#", 1)[0].strip()
        if text:
            records.append(text.split())
    if len(records) <= 10 or not records[10]:
        raise ValueError("dns.in is missing the frozen nstep record")
    try:
        count = int(records[10][0], 10)
    except ValueError as exc:
        raise ValueError("dns.in nstep is not an integer") from exc
    if count != 14:
        raise ValueError("candidate5 source fixture requires the frozen 14-interval schedule")
    return count


def _runtime_inputs(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if set(value) != TIMESTEP_INPUT_KEYS:
        raise ValueError("runtime timestep-input keys differ from schema v1.2")
    if value["time_scheme"] != "ab2" or value["real_kind"] != 8 or value["precision_digits"] != 15:
        raise ValueError("runtime timestep inputs do not match the pinned AB2 binary64 build")
    numeric_keys = TIMESTEP_INPUT_KEYS - {"time_scheme", "real_kind", "precision_digits", "dzc_m",
                                         "dzf_m", "dzci_m_inv", "dzfi_m_inv", "gravity_m_s2"}
    for key in numeric_keys:
        decimal_string(value[key], f"timestep_inputs.{key}")
    for key in ("dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv"):
        values = value[key]
        if not isinstance(values, list) or len(values) != 42:
            raise ValueError(f"timestep_inputs.{key} must contain 42 actual runtime entries")
        for index, item in enumerate(values):
            decimal_string(item, f"timestep_inputs.{key}[{index}]")
    gravity = value["gravity_m_s2"]
    if not isinstance(gravity, list) or len(gravity) != 3:
        raise ValueError("timestep_inputs.gravity_m_s2 must contain x/y/z components")
    for index, item in enumerate(gravity):
        decimal_string(item, f"timestep_inputs.gravity_m_s2[{index}]")
    return value


def _candidate_receipt(path: Path) -> tuple[str, str]:
    value = read_json(path)
    required = {
        "source_commit", "source_sha256", "source_patch_sha256", "build_script_sha256",
        "image_digest", "compiler", "compiler_version", "compiler_flags", "build_command",
        "executable_sha256",
    }
    if not required.issubset(value):
        raise ValueError(f"candidate-build.json is missing pinned receipt fields: {sorted(required - set(value))}")
    for key in ("source_patch_sha256", "build_script_sha256", "executable_sha256"):
        if not isinstance(value[key], str) or SHA256.fullmatch(value[key]) is None:
            raise ValueError(f"candidate-build.json {key} must be lowercase SHA-256")
    if not isinstance(value["source_sha256"], dict) or not value["source_sha256"]:
        raise ValueError("candidate-build.json source_sha256 must pin upstream source files")
    if any(not isinstance(item, str) or SHA256.fullmatch(item) is None
           for item in value["source_sha256"].values()):
        raise ValueError("candidate-build.json has an invalid upstream source hash")
    if not isinstance(value["compiler_flags"], list) or not all(isinstance(item, str) for item in value["compiler_flags"]):
        raise ValueError("candidate-build.json compiler_flags must be a string array")
    if not all(isinstance(value[key], str) and value[key] for key in
               ("source_commit", "compiler", "compiler_version", "build_command")):
        raise ValueError("candidate-build.json contains an empty build identity")
    image_digest = value["image_digest"]
    if not isinstance(image_digest, str) or IMAGE_DIGEST.fullmatch(image_digest) is None:
        raise ValueError("candidate-build.json must pin an immutable OCI image digest")
    return sha256(path), image_digest


def _resources(value: Any, completed: int) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"ram_samples", "vram_samples", "step_timing_samples"}:
        raise ValueError("resources keys differ from the frozen schema")
    for category, byte_key in (("ram_samples", "rss_bytes"), ("vram_samples", "used_bytes")):
        samples = value[category]
        if not isinstance(samples, list) or not samples:
            raise ValueError(f"resources.{category} requires at least one sample")
        last = Decimal("-1")
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict) or set(sample) != {"elapsed_s", byte_key}:
                raise ValueError(f"resources.{category}[{index}] has the wrong fields")
            elapsed = decimal_string(sample["elapsed_s"], f"resources.{category}[{index}].elapsed_s")
            amount = decimal_string(sample[byte_key], f"resources.{category}[{index}].{byte_key}")
            if elapsed < last or elapsed < 0 or amount < 0:
                raise ValueError(f"resources.{category}[{index}] is negative or non-monotone")
            last = elapsed
    steps = value["step_timing_samples"]
    if not isinstance(steps, list) or (completed > 0 and not steps):
        raise ValueError("step timing samples are required after a completed interval")
    last_step = -1
    last_elapsed = Decimal("-1")
    for index, sample in enumerate(steps):
        if not isinstance(sample, dict) or set(sample) != {"step", "elapsed_s"}:
            raise ValueError(f"resources.step_timing_samples[{index}] has the wrong fields")
        step = sample["step"]
        elapsed = decimal_string(sample["elapsed_s"], f"resources.step_timing_samples[{index}].elapsed_s")
        if type(step) is not int or step < 0 or step <= last_step or elapsed < 0 or elapsed < last_elapsed:
            raise ValueError(f"resources.step_timing_samples[{index}] is negative or non-monotone")
        last_step, last_elapsed = step, elapsed
    return value


def _stop_fields(metadata: dict[str, Any], intervals: int) -> tuple[dict[str, Any], str]:
    required = {
        "solver_exit_code", "stop_reason", "completed_interval_count", "stop_state_index",
        "stop_interval_index", "stop_stage_id", "resources",
    }
    if set(metadata) != required:
        raise ValueError(f"run metadata fields differ from the producer interface: {sorted(set(metadata) ^ required)}")
    code = metadata["solver_exit_code"]
    completed = metadata["completed_interval_count"]
    reason = metadata["stop_reason"]
    if type(code) is not int or type(completed) is not int or not 0 <= completed <= intervals:
        raise ValueError("solver exit code and completed interval count must be bounded integers")
    if reason not in {"normal_completion", "timestep_guard", "phase_audit", "velocity_audit"}:
        raise ValueError("unrecognized solver stop reason")
    status = "completed" if reason == "normal_completion" else "failed"
    if (reason == "normal_completion") != (code == 0):
        raise ValueError("normal completion requires exit code 0; controlled failures require nonzero")
    state = metadata["stop_state_index"]
    interval = metadata["stop_interval_index"]
    stage = metadata["stop_stage_id"]
    if reason == "normal_completion":
        if completed != intervals or (state, interval, stage) != ("not_applicable", "not_applicable", "not_applicable"):
            raise ValueError("normal completion must use the exact N-state stop sentinels")
    else:
        if type(interval) is not int or interval != completed or not 0 <= interval < intervals:
            raise ValueError("controlled stop must identify the first uncompleted interval")
        expected_state = interval
        if reason == "timestep_guard":
            if stage != "not_applicable":
                raise ValueError("timestep guard stop_stage_id must be not_applicable")
        elif reason == "phase_audit":
            if stage not in {"pre_vof_x", "pre_vof_y", "pre_vof_z", "pre_momentum"}:
                raise ValueError("phase audit stop has an unknown stage")
        else:
            if stage not in {"initial_u0", "pre_vof", "projection_override", "corrected_endpoint"}:
                raise ValueError("velocity audit stop has an unknown stage")
            if stage in {"projection_override", "corrected_endpoint"}:
                expected_state += 1
            if stage == "initial_u0" and interval != 0:
                raise ValueError("initial_u0 failure must be interval zero")
        if type(state) is not int or state != expected_state:
            raise ValueError("controlled stop state is inconsistent with the stop stage")
    resources = _resources(metadata["resources"], completed)
    return {
        "solver_exit_code": code,
        "run_status": status,
        "stop_reason": reason,
        "completed_interval_count": completed,
        "stop_state_index": state,
        "stop_interval_index": interval,
        "stop_stage_id": stage,
        "resources": resources,
    }, status


def _count_rows(path: Path, expected_header: list[str]) -> int:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise ValueError(f"CSV must be UTF-8 without BOM and end in LF: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV is empty: {path}") from exc
        if header != expected_header:
            raise ValueError(f"CSV header differs from schema v1.2: {path}")
        count = 0
        for row in reader:
            if len(row) != len(expected_header):
                raise ValueError(f"CSV row field count differs from schema: {path}")
            count += 1
    return count


def make_manifest(args: argparse.Namespace) -> dict[str, Any]:
    schema_hash = sha256(args.schema)
    if schema_hash != SCHEMA_SHA256:
        raise ValueError(f"shared schema hash is not the accepted frozen bytes: {schema_hash}")
    input_hashes = _case_inputs(args.case_root)
    intervals = _planned_intervals(args.case_root)
    runtime_inputs = _runtime_inputs(args.timestep_inputs)
    receipt_hash, image_digest = _candidate_receipt(args.candidate_build)
    analyzer_hash = sha256(args.analyzer)
    if SHA256.fullmatch(analyzer_hash) is None:
        raise ValueError("analyzer source does not have a SHA-256 identity")
    metadata = read_json(args.run_metadata)
    stop, _status = _stop_fields(metadata, intervals)
    files_hashes: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    for name, header in FILES.items():
        path = args.run_dir / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"required output file is missing or not regular: {path}")
        files_hashes[name] = sha256(path)
        row_counts[name] = _count_rows(path, header)
    start = decimal_string(runtime_inputs["time_start_s"], "timestep_inputs.time_start_s")
    dt = decimal_string(runtime_inputs["fixed_step_s"], "timestep_inputs.fixed_step_s")
    final_time = start + Decimal(stop["completed_interval_count"]) * dt
    manifest: dict[str, Any] = {
        "manifest_schema": MANIFEST_SCHEMA,
        "producer_schema": PRODUCER_SCHEMA,
        "schema_sha256": schema_hash,
        "candidate_sha256": receipt_hash,
        "image_digest": image_digest,
        "case_id": args.case_root.name,
        "input_sha256": input_hashes,
        "analyzer_sha256": analyzer_hash,
        "run_status": stop["run_status"],
        "solver_exit_code": stop["solver_exit_code"],
        "stop_reason": stop["stop_reason"],
        "state_count": intervals + 1,
        "interval_count": intervals,
        "completed_interval_count": stop["completed_interval_count"],
        "stop_state_index": stop["stop_state_index"],
        "stop_interval_index": stop["stop_interval_index"],
        "stop_stage_id": stop["stop_stage_id"],
        "final_time_s": format(final_time, "f"),
        "files_sha256": files_hashes,
        "row_counts": row_counts,
        "scan_order": SCAN_ORDER,
        "reduction_order": REDUCTION_ORDER,
        "timestep_inputs": runtime_inputs,
        "resources": stop["resources"],
        "pressure_solver": PRESSURE_SOLVER,
    }
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--analyzer", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--timestep-inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = make_manifest(args)
        raw = (json.dumps(manifest, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with args.output.open("xb") as stream:
            stream.write(raw)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"candidate5 manifest producer rejected the run bundle: {exc}")
        return 2
    print(f"wrote {args.output} sha256={hashlib.sha256(raw).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
