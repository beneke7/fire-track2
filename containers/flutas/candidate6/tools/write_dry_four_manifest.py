#!/usr/bin/env python3
"""Write the unchanged v2 observability manifest for the pinned dry_four run.

This is a narrow adapter for the nested H6 candidate receipt. It preserves the
historical candidate5 writer and manifest schema, but binds the exact H6 receipt
bytes and OCI manifest digest. It does not independently accept solver physics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "containers/flutas/candidate5"))
from tools import write_run_manifest as frozen  # noqa: E402

CASE_ID = "dry_four"
RECEIPT_SHA256 = "629e792cf9ebd02d203442b2b943de4aa1176a121f8be303fd86770543c643e0"
OCI_MANIFEST_DIGEST = "sha256:0cbfcc17c72484c004663ee009e320cbb551bf80f534cfdb1a9d3db1297b8972"
ANALYZER_SHA256 = "9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37"
EXECUTABLE_SHA256 = "0c3563ed2bbd8a29586d1cdd9f61b8e53087854950e440812492154839b2bb58"
SOURCE_COMMIT = "598210616bebd51f7d51f61455f196e6f3479916"
SOURCE_PATCH_SHA256 = "3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee"
INPUT_SHA256 = {
    "dns.in": "929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0",
    "source-boundary.in": "f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0",
    "vof.in": "2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54",
}
H6_TOP_LEVEL = {"schema_version", "candidate_id", "source", "patches", "build", "image"}
H6_IMAGE_KEYS = {
    "platform",
    "oci_manifest_digest",
    "docker_image_id",
    "config_digest",
    "entrypoint_argv",
    "cmd_argv",
    "layers",
}
H6_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_identity(path: Path, *, expected_sha256: str = RECEIPT_SHA256) -> tuple[str, str]:
    actual = sha256(path)
    if actual != expected_sha256:
        raise ValueError(f"candidate receipt SHA-256 mismatch: {actual}")
    receipt = frozen.read_json(path)
    if set(receipt) != H6_TOP_LEVEL or receipt.get("schema_version") != "track2-candidate-build-v1":
        raise ValueError("candidate receipt does not match the exact nested H6 schema")
    if receipt.get("candidate_id") != "candidate6-20260928T093141Z-4092509":
        raise ValueError("candidate receipt ID differs from the reviewed candidate6 build")
    source = receipt.get("source")
    if not isinstance(source, dict) or source.get("commit_oid") != SOURCE_COMMIT:
        raise ValueError("candidate receipt source commit differs from the reviewed candidate")
    patches = receipt.get("patches")
    if not isinstance(patches, list) or len(patches) != 1:
        raise ValueError("candidate receipt patch roster differs from candidate6")
    if patches[0] != {
        "path": "containers/flutas/candidate6/source-boundary.patch",
        "sha256": SOURCE_PATCH_SHA256,
    }:
        raise ValueError("candidate receipt patch identity differs from candidate6")
    build = receipt.get("build")
    if not isinstance(build, dict) or build.get("executable_sha256") != EXECUTABLE_SHA256:
        raise ValueError("candidate receipt executable identity differs from candidate6")
    image = receipt.get("image")
    if not isinstance(image, dict) or set(image) != H6_IMAGE_KEYS:
        raise ValueError("candidate receipt image fields differ from the H6 schema")
    if image.get("platform") != {"os": "linux", "architecture": "amd64"}:
        raise ValueError("candidate receipt platform differs from the reviewed candidate")
    if (
        image.get("docker_image_id")
        != "sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b"
    ):
        raise ValueError("candidate receipt Docker/config identity differs from candidate6")
    if image.get("oci_manifest_digest") != OCI_MANIFEST_DIGEST:
        raise ValueError("candidate receipt OCI manifest digest differs from candidate6")
    return actual, OCI_MANIFEST_DIGEST


def final_time_string(start: Decimal, dt: Decimal, completed_intervals: int) -> str:
    """Use the binary64 operation order required by the frozen analyzer."""
    result = float(start) + completed_intervals * float(dt)
    if not math.isfinite(result):
        raise ValueError("final time is not finite in binary64")
    return repr(result)


def _jsonl_events(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("supervision JSONL must be UTF-8, BOM-free and end in LF")
    events: list[dict[str, Any]] = []
    for index, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        try:
            value = json.loads(
                line,
                parse_constant=lambda token: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON number {token}")
                ),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid supervision JSONL record {index}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
            raise ValueError(f"supervision JSONL record {index} is not a named event")
        events.append(value)
    return events


def _step_samples(path: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    elapsed = 0.0
    for line_number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        if len(line) != 75:
            raise ValueError(f"performance.out row {line_number} is not five E15.7 fields")
        values = [float(line[index * 15 : (index + 1) * 15]) for index in range(5)]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"performance.out row {line_number} has a nonfinite value")
        step = int(values[0])
        if values[0] != step or step != line_number or values[4] < 0:
            raise ValueError(f"performance.out row {line_number} has an invalid step or duration")
        elapsed += values[4]
        if not math.isfinite(elapsed):
            raise ValueError("cumulative solver step timing is not finite")
        rows.append({"step": step, "elapsed_s": format(elapsed, ".17g")})
    if len(rows) != 14:
        raise ValueError(
            f"normal dry_four completion requires 14 performance rows, got {len(rows)}"
        )
    return rows


def _supervisor_resource_samples(events: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    samples = [event for event in events if event.get("kind") == "sample"]
    if not samples:
        raise ValueError("supervisor has no resource samples")
    times = [event.get("sample_monotonic_s") for event in samples]
    if any(type(value) not in (int, float) or not math.isfinite(float(value)) for value in times):
        raise ValueError("supervisor resource samples have invalid monotonic times")
    origin = float(times[0])
    previous = origin
    ram: list[dict[str, str]] = []
    vram: list[dict[str, str]] = []
    running_memory_increase = False
    baseline_vram: int | None = None
    running_container_samples = 0
    for event, sample_time in zip(samples, times, strict=True):
        current = float(sample_time)
        if current < previous:
            raise ValueError("supervisor sample time moved backwards")
        previous = current
        elapsed = format(current - origin, ".17g")
        rss = event.get("process_rss_bytes")
        used = event.get("gpu_memory_used_bytes")
        device = event.get("gpu_device_index")
        if type(rss) is not int or rss < 0 or type(used) is not int or used < 0:
            raise ValueError("supervisor resource samples have invalid RAM/VRAM values")
        if device != "0":
            raise ValueError("supervisor did not sample the frozen GPU device index 0")
        ram.append({"elapsed_s": elapsed, "rss_bytes": str(rss)})
        vram.append({"elapsed_s": elapsed, "used_bytes": str(used)})
        if event.get("phase") == "before_create":
            baseline_vram = used
        if event.get("phase") == "running" and event.get("container_running") is True:
            running_container_samples += 1
        if (
            event.get("phase") == "running"
            and event.get("container_running") is True
            and baseline_vram is not None
        ):
            utilization = event.get("gpu_utilization_percent")
            if type(utilization) not in (int, float) or not math.isfinite(float(utilization)):
                raise ValueError("running supervisor sample lacks valid GPU utilization")
            running_memory_increase |= used > baseline_vram or utilization > 0
    if running_container_samples == 0:
        raise ValueError("supervisor did not sample the solver while its container was running")
    if not running_memory_increase:
        raise ValueError("no GPU memory increase or utilization was observed while running")
    return {"ram_samples": ram, "vram_samples": vram}


def derive_run_metadata(
    *, supervisor_dir: Path, stdout_path: Path, performance_path: Path
) -> dict[str, Any]:
    summary = frozen.read_json(supervisor_dir / "summary.json")
    if summary.get("exit_code") != 0 or summary.get("disposition") != "termination_verified":
        raise ValueError("supervisor did not record successful, verified termination")
    if summary.get("stop_trigger") is not None or summary.get("signal_sequence") != []:
        raise ValueError("supervisor recorded a controlled stop or signal")
    events = _jsonl_events(supervisor_dir / "supervision.jsonl")
    if any(
        event["kind"] in {"sample_failure", "supervisor_event_budget_exhausted"} for event in events
    ):
        raise ValueError("supervision evidence contains a sampling or event-budget failure")
    solver_exit = [event for event in events if event["kind"] == "solver_exit"]
    result = [event for event in events if event["kind"] == "result"]
    attached = [event for event in events if event["kind"] == "attached_logs"]
    verified = [
        event
        for event in events
        if event["kind"] == "termination_verification"
        and event.get("phase") in {"normal_completion", "post_cleanup_verification"}
        and event.get("verified") is True
        and event.get("docker_state_running") is False
        and event.get("surviving_docker_client_or_solver_children") is False
    ]
    verified_phases = {event["phase"] for event in verified}
    if (
        len(solver_exit) != 1
        or solver_exit[0].get("exit_code") != 0
        or not result
        or result[-1].get("exit_code") != 0
        or result[-1].get("disposition") != "normal_termination_verified"
        or len(attached) != 1
        or attached[-1].get("returncode") != 0
        or attached[-1].get("log_driver") != "none"
        or attached[-1].get("combined_bytes", 64 * 1024**2 + 1) > 64 * 1024**2
        or verified_phases != {"normal_completion", "post_cleanup_verification"}
    ):
        raise ValueError("supervisor events do not prove normal solver and cleanup completion")
    if b"*** Fim ***" not in stdout_path.read_bytes():
        raise ValueError("solver stdout lacks the source program's normal-completion marker")
    resources = _supervisor_resource_samples(events)
    resources["step_timing_samples"] = _step_samples(performance_path)
    return {
        "solver_exit_code": 0,
        "stop_reason": "normal_completion",
        "completed_interval_count": 14,
        "stop_state_index": "not_applicable",
        "stop_interval_index": "not_applicable",
        "stop_stage_id": "not_applicable",
        "resources": resources,
    }


def make_manifest(args: argparse.Namespace) -> dict[str, Any]:
    if args.case_root.name != CASE_ID:
        raise ValueError("the immutable input directory leaf must be dry_four")
    if frozen.sha256(args.schema) != frozen.SCHEMA_SHA256:
        raise ValueError("shared schema bytes differ from the accepted frozen v1.2 schema")
    input_hashes = frozen._case_inputs(args.case_root)
    if input_hashes != INPUT_SHA256:
        raise ValueError("dry_four staged inputs differ from the frozen allowlist")
    intervals = frozen._planned_intervals(args.case_root)
    if intervals != 14:
        raise ValueError("dry_four manifest requires exactly 14 intervals")
    runtime_inputs = frozen._runtime_inputs(args.timestep_inputs)
    candidate_hash, image_digest = candidate_identity(args.candidate_build)
    if frozen.sha256(args.analyzer) != ANALYZER_SHA256:
        raise ValueError("analyzer bytes differ from the exact reviewed implementation")
    metadata = frozen.read_json(args.run_metadata)
    stop, _status = frozen._stop_fields(metadata, intervals)
    if stop["run_status"] != "completed" or stop["completed_interval_count"] != intervals:
        raise ValueError(
            "this one-run dry amendment only creates a manifest after normal completion"
        )
    files_hashes: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    for name, header in frozen.FILES.items():
        path = args.run_dir / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"required canonical CSV is missing or not regular: {path}")
        files_hashes[name] = sha256(path)
        row_counts[name] = frozen._count_rows(path, header)

    start = frozen.decimal_string(runtime_inputs["time_start_s"], "time_start_s")
    dt = frozen.decimal_string(runtime_inputs["fixed_step_s"], "fixed_step_s")
    final_time = final_time_string(start, dt, intervals)
    return {
        "manifest_schema": frozen.MANIFEST_SCHEMA,
        "producer_schema": frozen.PRODUCER_SCHEMA,
        "schema_sha256": frozen.SCHEMA_SHA256,
        "candidate_sha256": candidate_hash,
        "image_digest": image_digest,
        "case_id": CASE_ID,
        "input_sha256": input_hashes,
        "analyzer_sha256": ANALYZER_SHA256,
        "run_status": stop["run_status"],
        "solver_exit_code": stop["solver_exit_code"],
        "stop_reason": stop["stop_reason"],
        "state_count": intervals + 1,
        "interval_count": intervals,
        "completed_interval_count": stop["completed_interval_count"],
        "stop_state_index": stop["stop_state_index"],
        "stop_interval_index": stop["stop_interval_index"],
        "stop_stage_id": stop["stop_stage_id"],
        "final_time_s": final_time,
        "files_sha256": files_hashes,
        "row_counts": row_counts,
        "scan_order": frozen.SCAN_ORDER,
        "reduction_order": frozen.REDUCTION_ORDER,
        "timestep_inputs": runtime_inputs,
        "resources": stop["resources"],
        "pressure_solver": frozen.PRESSURE_SOLVER,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--analyzer", type=Path, required=True)
    parser.add_argument("--supervisor-dir", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--performance-output", type=Path, required=True)
    parser.add_argument("--run-metadata-output", type=Path, required=True)
    parser.add_argument("--timestep-inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_metadata = derive_run_metadata(
            supervisor_dir=args.supervisor_dir,
            stdout_path=args.stdout,
            performance_path=args.performance_output,
        )
        metadata_raw = (
            json.dumps(run_metadata, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with args.run_metadata_output.open("xb") as stream:
            stream.write(metadata_raw)
        args.run_metadata = args.run_metadata_output
        manifest = make_manifest(args)
        raw = (
            json.dumps(
                manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")
        with args.output.open("xb") as stream:
            stream.write(raw)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"candidate6 dry_four manifest adapter rejected the bundle: {exc}")
        return 2
    print(f"wrote {args.output} sha256={hashlib.sha256(raw).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
