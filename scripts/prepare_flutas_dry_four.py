#!/usr/bin/env python3
"""Prepare, and only with explicit approval launch, the frozen candidate6 dry_four case.

Preparation is CPU-only: it validates and stages the allowlisted candidate5
inputs, writes an immutable provenance bundle, and records the exact supervisor
configuration and argv.  ``--launch`` additionally requires an exact primary
disposition and a matching Astra memo hash before reserving the single attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

if __package__:
    from scripts.finalize_flutas_dry_four import finalize_bundle
    from scripts.flutas_dry_four_preflight import CASE_ID, INPUTS
    from scripts.flutas_dry_four_preflight import stage as stage_inputs
    from scripts.flutas_source_supervisor import RunConfig
else:  # Running as ``python scripts/prepare_flutas_dry_four.py``.
    from finalize_flutas_dry_four import finalize_bundle
    from flutas_dry_four_preflight import CASE_ID, INPUTS
    from flutas_dry_four_preflight import stage as stage_inputs
    from flutas_source_supervisor import RunConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
# The primary pins this to the final reviewed amendment hash before any launch.
EXPECTED_AMENDMENT_SHA256: str | None = (
    "abc329f3c5b7296cd69ae406dfd8f33b666b7fb441945443956ee93ef76a548a"
)
AMENDMENT_RELATIVE_PATH = Path("experiments/FLUTAS_DRY_FOUR_DIAGNOSTIC_AMENDMENT_v0.1.md")
OUTPUT_MAP_RELATIVE_PATH = Path("experiments/dry-output-map.json")
INPUT_RELATIVE_PATH = Path("containers/flutas/candidate5/cases/source_boundary/dry_four")
CANDIDATE_ROOT_RELATIVE_PATH = Path("results/runs/candidate6-oci-layout-20260928T1139Z")
EXECUTABLE_RELATIVE_PATH = Path(
    "containers/flutas/candidate6/evidence/full-source-build-20260928T093141Z-4092509/"
    "flutas.two_phase_inc_isot"
)
IDENTITY_VERIFIER_RELATIVE_PATH = Path("scripts/flutas_candidate6_identity.py")
RUN_LOCAL_RELATIVE_PATH = Path("scripts/run_local.py")
DISPOSITION_RELATIVE_PATH = Path("experiments/FLUTAS_DRY_FOUR_PRIMARY_DISPOSITION.json")

PINNED_IMAGE_ID = "sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b"
PINNED_OCI_MANIFEST = "sha256:0cbfcc17c72484c004663ee009e320cbb551bf80f534cfdb1a9d3db1297b8972"
PINNED_EXECUTABLE_SHA256 = "0c3563ed2bbd8a29586d1cdd9f61b8e53087854950e440812492154839b2bb58"
PINNED_RECEIPT_SHA256 = "629e792cf9ebd02d203442b2b943de4aa1176a121f8be303fd86770543c643e0"

DISPOSITION_FIELDS = {
    "decision",
    "review_status",
    "amendment_sha256",
    "reviewer_memo_sha256",
    "reviewer",
    "scope",
}
DISPOSITION_EXPECTED = {
    "decision": "ACCEPT_TO_LAUNCH",
    "review_status": "ACCEPT",
    "reviewer": "gpt-6-astra/max",
    "scope": "dry_four_execution_telemetry_only",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
ATTEMPT_CLAIM_NAME = ".flutas-dry-four-candidate6-attempt-claim.json"

HOST_CASE_PATH = "/work"
CONTAINER_STAGE_FILE = "/run/h7-stage.txt"
SOLVER_EXECUTABLE = "/opt/FluTAS/src/flutas.two_phase_inc_isot"


class PreparationError(RuntimeError):
    """The frozen case or its preparation evidence failed a fail-closed check."""


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PreparationError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PreparationError(f"{label} must be a JSON object")
    return value


def _read_regular(path: Path, *, singly_linked: bool = True) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or (singly_linked and info.st_nlink != 1):
            raise PreparationError(f"expected a regular, singly linked file: {path}")
        return stream.read()


def _file_sha256(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PreparationError(f"expected a regular, singly linked file: {path}")
        digest = hashlib.sha256()
        size = 0
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
        return digest.hexdigest(), size


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_exclusive(path: Path, data: bytes, mode: int = 0o444) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)


def _write_json_exclusive(path: Path, value: Any, mode: int = 0o444) -> bytes:
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    _write_exclusive(path, raw, mode)
    return raw


def _copy_regular_readonly(source: Path, destination: Path) -> tuple[str, int]:
    raw = _read_regular(source)
    _write_exclusive(destination, raw)
    copied = _read_regular(destination)
    if copied != raw:
        raise PreparationError(f"copy changed bytes: {source}")
    return _sha256(raw), len(raw)


def _copy_preparation_sources(
    *,
    repository_root: Path,
    bundle_root: Path,
    amendment_raw: bytes,
    output_map_raw: bytes,
    candidate_root: Path,
    candidate_info: dict[str, Any],
) -> dict[str, Any]:
    metadata = bundle_root / "metadata"
    copied: dict[str, Any] = {}
    for source, name, payload in (
        (repository_root / AMENDMENT_RELATIVE_PATH, "diagnostic-amendment.md", amendment_raw),
        (repository_root / OUTPUT_MAP_RELATIVE_PATH, "dry-output-map.json", output_map_raw),
    ):
        source_raw = _read_regular(source)
        if source_raw != payload:
            raise PreparationError(f"source changed while preparing evidence: {source}")
        _write_exclusive(metadata / name, source_raw)
        copied[name] = {"sha256": _sha256(source_raw), "size_bytes": len(source_raw)}

    for name in ("candidate-build.json", "candidate-build.sha256", "source-tree-blobs.tsv"):
        source = candidate_root / name
        digest, size = _copy_regular_readonly(source, metadata / name)
        copied[name] = {"sha256": digest, "size_bytes": size}

    host_snapshot = repository_root / "results" / "machine.json"
    digest, size = _copy_regular_readonly(host_snapshot, metadata / "host-snapshot.json")
    copied["host-snapshot.json"] = {"sha256": digest, "size_bytes": size}

    layout_reference = {
        "schema_version": "flutas-dry-four-oci-layout-reference-v1",
        "candidate_root": str(candidate_root),
        "archive_path": str(candidate_root / "docker-save.tar"),
        "layout_path": str(candidate_info["oci_layout_path"]),
        "index_path": str(candidate_info["oci_index_path"]),
        "index_sha256": candidate_info["oci_index_sha256"],
        "manifest_digest": candidate_info["oci_manifest_digest"],
        "image_id": candidate_info["image_id"],
        "storage_policy": "offline archive and OCI layout remain external immutable candidate evidence; launch identity verifier rechecks them",
    }
    layout_raw = (
        json.dumps(layout_reference, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    _write_exclusive(metadata / "oci-layout-reference.json", layout_raw)
    copied["oci-layout-reference.json"] = {
        "sha256": _sha256(layout_raw),
        "size_bytes": len(layout_raw),
    }
    return copied


def _resolve_under_root(path: Path, root: Path, label: str) -> Path:
    if path.is_symlink():
        raise PreparationError(f"{label} cannot be a symlink: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PreparationError(f"{label} does not exist: {path}") from exc
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise PreparationError(f"{label} must remain inside the repository: {path}")
    return resolved


def _validate_amendment(
    repository_root: Path, *, require_expected_pin: bool = False
) -> tuple[Path, bytes, str]:
    path = _resolve_under_root(
        repository_root / AMENDMENT_RELATIVE_PATH, repository_root, "diagnostic amendment"
    )
    raw = _read_regular(path)
    digest = _sha256(raw)
    if EXPECTED_AMENDMENT_SHA256 is None:
        if require_expected_pin:
            raise PreparationError(
                "launch is disabled until EXPECTED_AMENDMENT_SHA256 is set to the final reviewed hash"
            )
    elif digest != EXPECTED_AMENDMENT_SHA256:
        raise PreparationError(
            "diagnostic amendment SHA-256 differs from the launcher pin: "
            f"expected {EXPECTED_AMENDMENT_SHA256}, found {digest}"
        )
    return path, raw, digest


def _validate_output_map(repository_root: Path, input_hashes: dict[str, str]) -> tuple[bytes, str]:
    path = _resolve_under_root(
        repository_root / OUTPUT_MAP_RELATIVE_PATH, repository_root, "dry output map"
    )
    raw = _read_regular(path)
    value = _strict_json_bytes(raw, "dry output map")
    scope = value.get("scope")
    if not isinstance(scope, dict) or scope.get("case_id") != CASE_ID:
        raise PreparationError("dry output map does not select the frozen dry_four case")
    if scope.get("candidate") != "candidate6":
        raise PreparationError("dry output map does not select candidate6")
    rows = scope.get("staged_inputs")
    expected = [{"path": name, "sha256": digest} for name, digest in INPUTS.items()]
    if rows != expected or input_hashes != INPUTS:
        raise PreparationError("dry output map input rows differ from the frozen input hashes")
    return raw, _sha256(raw)


def _validate_candidate_artifacts(
    *, repository_root: Path, candidate_root: Path, executable: Path
) -> dict[str, Any]:
    candidate_root = _resolve_under_root(candidate_root, repository_root, "candidate receipt root")
    layout = _resolve_under_root(candidate_root / "layout", repository_root, "candidate OCI layout")
    if not layout.is_dir():
        raise PreparationError("candidate OCI layout must be a directory")
    receipt_hash, receipt_size = _file_sha256(candidate_root / "candidate-build.json")
    if receipt_hash != PINNED_RECEIPT_SHA256:
        raise PreparationError(f"candidate receipt SHA-256 differs from pin: {receipt_hash}")
    checksum = _read_regular(candidate_root / "candidate-build.sha256").decode("ascii").strip()
    if checksum != f"{PINNED_RECEIPT_SHA256}  candidate-build.json":
        raise PreparationError("candidate receipt checksum file differs from the frozen receipt")
    executable = _resolve_under_root(executable, repository_root, "candidate executable")
    executable_hash, executable_size = _file_sha256(executable)
    if executable_hash != PINNED_EXECUTABLE_SHA256:
        raise PreparationError(f"candidate executable SHA-256 differs from pin: {executable_hash}")
    index_path = layout / "index.json"
    index_hash, index_size = _file_sha256(index_path)
    index = _strict_json_bytes(_read_regular(index_path), "OCI index")
    manifests = index.get("manifests")
    if (
        not isinstance(manifests, list)
        or len(manifests) != 1
        or not isinstance(manifests[0], dict)
        or manifests[0].get("digest") != PINNED_OCI_MANIFEST
    ):
        raise PreparationError("candidate OCI index differs from the frozen manifest")
    return {
        "candidate_receipt_path": str(candidate_root / "candidate-build.json"),
        "candidate_receipt_sha256": receipt_hash,
        "candidate_receipt_size_bytes": receipt_size,
        "source_inventory_path": str(candidate_root / "source-tree-blobs.tsv"),
        "source_inventory_sha256": _file_sha256(candidate_root / "source-tree-blobs.tsv")[0],
        "oci_layout_path": str(layout),
        "oci_index_path": str(index_path),
        "oci_index_sha256": index_hash,
        "oci_index_size_bytes": index_size,
        "oci_manifest_digest": PINNED_OCI_MANIFEST,
        "oci_layout_storage_bytes_external_to_run_bundle": "not measured by preparation",
        "image_id": PINNED_IMAGE_ID,
        "executable_path": str(executable),
        "executable_sha256": executable_hash,
        "executable_size_bytes": executable_size,
    }


def _make_supervisor_config(bundle_root: Path) -> tuple[dict[str, Any], list[str]]:
    input_root = bundle_root / "dry_four"
    work_root = bundle_root / "work"
    work_root.mkdir(mode=0o700)
    output_root = work_root / "data"
    output_root.mkdir(mode=0o700)
    supervisor_root = bundle_root / "supervisor"
    supervisor_root.mkdir(mode=0o700)
    evidence_dir = supervisor_root / "evidence"
    stage_file = supervisor_root / "stage.txt"
    mounts = [f"--mount=type=bind,source={work_root},target={HOST_CASE_PATH}"]
    mounts.extend(
        f"--mount=type=bind,source={input_root / name},target={HOST_CASE_PATH}/{name},readonly"
        for name in INPUTS
    )
    run_suffix = bundle_root.name.rsplit("-", 1)[-1]
    config: dict[str, Any] = {
        "image": PINNED_IMAGE_ID,
        "name": f"flutas-dry-four-{run_suffix}",
        "container_options": [
            "--network=none",
            "--gpus=device=0",
            "--entrypoint=mpirun",
            f"--workdir={HOST_CASE_PATH}",
            *mounts,
            "--env=OMPI_ALLOW_RUN_AS_ROOT=1",
            "--env=OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1",
            "--env=OMPI_NUM_THREADS=1",
        ],
        "evidence_dir": str(evidence_dir),
        "disk_roots": [str(bundle_root)],
        "stage_file": str(stage_file),
        "stage_file_container": CONTAINER_STAGE_FILE,
        "gpu_index": "0",
        "docker_executable": "docker",
        "nvidia_smi_executable": "nvidia-smi",
    }
    solver_argv = ["--oversubscribe", "-np", "1", SOLVER_EXECUTABLE]
    return config, solver_argv


def _validate_disposition(
    *,
    repository_root: Path,
    amendment_sha256: str,
    disposition_path: Path,
    review_memo_path: Path | None,
) -> tuple[dict[str, Any], bytes, bytes, str]:
    if review_memo_path is None:
        raise PreparationError("--review-memo is required with --launch")
    disposition_path = _resolve_under_root(
        disposition_path, repository_root, "primary disposition JSON"
    )
    review_memo_path = _resolve_under_root(review_memo_path, repository_root, "Astra review memo")
    disposition_raw = _read_regular(disposition_path)
    disposition = _strict_json_bytes(disposition_raw, "primary disposition")
    if set(disposition) != DISPOSITION_FIELDS:
        raise PreparationError(
            "primary disposition keys differ from the strict schema: "
            f"expected {sorted(DISPOSITION_FIELDS)}"
        )
    for key, expected in DISPOSITION_EXPECTED.items():
        if disposition.get(key) != expected:
            raise PreparationError(f"primary disposition {key!r} must equal {expected!r}")
    if disposition.get("amendment_sha256") != amendment_sha256:
        raise PreparationError("primary disposition does not bind the pinned amendment SHA-256")
    memo_raw = _read_regular(review_memo_path)
    memo_sha256 = _sha256(memo_raw)
    declared_memo_hash = disposition.get("reviewer_memo_sha256")
    if not isinstance(declared_memo_hash, str) or SHA256_RE.fullmatch(declared_memo_hash) is None:
        raise PreparationError(
            "primary disposition reviewer_memo_sha256 is not a lowercase SHA-256"
        )
    if memo_sha256 != declared_memo_hash:
        raise PreparationError("Astra review memo SHA-256 differs from the primary disposition")
    return disposition, disposition_raw, memo_raw, memo_sha256


def _create_bundle(runs_root: Path, run_id: str | None) -> tuple[Path, str]:
    if runs_root.is_symlink():
        raise PreparationError(f"runs root cannot be a symlink: {runs_root}")
    if not runs_root.exists():
        runs_root.mkdir(mode=0o700, parents=True)
    if not runs_root.is_dir():
        raise PreparationError(f"runs root is not a directory: {runs_root}")
    if run_id is None:
        run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(6)}"
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise PreparationError(
            "run ID must contain only letters, digits, dot, underscore or hyphen"
        )
    bundle = runs_root / f"flutas-dry-four-candidate6-{run_id}"
    bundle.mkdir(mode=0o700, parents=False, exist_ok=False)
    info = bundle.lstat()
    if not stat.S_ISDIR(info.st_mode) or bundle.is_symlink():
        raise PreparationError("new run bundle is not a real directory")
    for name in ("metadata", "logs"):
        (bundle / name).mkdir(mode=0o700)
    return bundle.resolve(strict=True), run_id


def _claim_single_attempt(
    *, runs_root: Path, bundle_root: Path, amendment_sha256: str, reviewer_memo_sha256: str
) -> bytes:
    claim_path = runs_root / ATTEMPT_CLAIM_NAME
    if claim_path.exists() or claim_path.is_symlink():
        raise PreparationError(
            f"dry_four's one candidate6 attempt is already claimed: {claim_path}"
        )
    claim = {
        "schema_version": "flutas-dry-four-one-attempt-claim-v1",
        "case_id": CASE_ID,
        "candidate": "candidate6",
        "bundle_root": str(bundle_root),
        "amendment_sha256": amendment_sha256,
        "reviewer_memo_sha256": reviewer_memo_sha256,
        "claimed_utc": _now_utc(),
        "meaning": "reserved before candidate identity verification; never automatically retried",
    }
    raw = (json.dumps(claim, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_exclusive(claim_path, raw)
    _write_exclusive(bundle_root / "metadata" / "attempt-claim.json", raw)
    return raw


def _run_identity_verifier(
    *,
    repository_root: Path,
    candidate_root: Path,
    executable: Path,
    output_path: Path,
    docker: str,
) -> tuple[int, bytes, bytes, list[str]]:
    argv = [
        sys.executable,
        str(repository_root / IDENTITY_VERIFIER_RELATIVE_PATH),
        "--candidate-root",
        str(candidate_root),
        "--archive",
        str(candidate_root / "docker-save.tar"),
        "--layout",
        str(candidate_root / "layout"),
        "--repository-root",
        str(repository_root),
        "--executable",
        str(executable),
        "--docker",
        docker,
        "--output",
        str(output_path),
    ]
    result = subprocess.run(argv, capture_output=True, check=False, timeout=900)
    stdout = (
        result.stdout if isinstance(result.stdout, bytes) else str(result.stdout or "").encode()
    )
    stderr = (
        result.stderr if isinstance(result.stderr, bytes) else str(result.stderr or "").encode()
    )
    return result.returncode, stdout, stderr, argv


def _check_identity_output(path: Path) -> dict[str, Any]:
    value = _strict_json_bytes(_read_regular(path), "candidate identity verifier output")
    if value.get("schema_version") != "candidate6-dry-four-identity-verification-v1":
        raise PreparationError("candidate identity verifier output has an unexpected schema")
    if value.get("solver_started") is not False or value.get("gpu_requested") is not False:
        raise PreparationError("identity verifier unexpectedly reports solver/GPU activity")
    local = value.get("local_docker_images")
    if not isinstance(local, dict) or local.get("candidate_image_id") != PINNED_IMAGE_ID:
        raise PreparationError("identity verifier output does not confirm the pinned image")
    return value


def _run_local_supervisor(
    *,
    repository_root: Path,
    config_path: Path,
    solver_argv: list[str],
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, list[str]]:
    argv = [
        sys.executable,
        str(repository_root / RUN_LOCAL_RELATIVE_PATH),
        "--gpu",
        "--threads",
        "2",
        "--source-supervisor",
        str(config_path),
        "--",
        *solver_argv,
    ]
    process: subprocess.Popen[bytes] | None = None
    queued_signals: list[int] = []

    def forward_guardian_signal(signum: int, frame: object) -> None:
        del frame
        queued_signals.append(signum)
        if process is not None:
            try:
                process.send_signal(signum)
            except ProcessLookupError:
                pass

    previous_handlers = {
        signum: signal.signal(signum, forward_guardian_signal)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            pending_at_spawn = tuple(queued_signals)
            queued_signals.clear()
            for requested_signal in pending_at_spawn:
                try:
                    process.send_signal(requested_signal)
                except ProcessLookupError:
                    pass
            # Keep this client alive until run_local returns after its detached
            # lock guardian has stopped the solver and proved lock release.
            return_code = process.wait()
            return return_code, argv
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def prepare_bundle(
    *,
    repository_root: Path = REPOSITORY_ROOT,
    runs_root: Path | None = None,
    source: Path | None = None,
    run_id: str | None = None,
    candidate_root: Path | None = None,
    executable: Path | None = None,
    disposition_path: Path | None = None,
    review_memo_path: Path | None = None,
    launch: bool = False,
    docker: str = "docker",
    launcher_invocation: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Create one run bundle. The only external processes are under ``launch``."""
    repository_root = repository_root.resolve(strict=True)
    runs_root = runs_root or repository_root / "results" / "runs"
    if runs_root.is_symlink():
        raise PreparationError(f"runs root cannot be a symlink: {runs_root}")
    runs_root = runs_root.resolve()
    source = source or repository_root / INPUT_RELATIVE_PATH
    candidate_root = candidate_root or repository_root / CANDIDATE_ROOT_RELATIVE_PATH
    executable = executable or repository_root / EXECUTABLE_RELATIVE_PATH
    disposition_path = disposition_path or repository_root / DISPOSITION_RELATIVE_PATH

    _amendment_path, amendment_raw, amendment_sha256 = _validate_amendment(
        repository_root, require_expected_pin=launch
    )
    amendment_sha256_actual = _sha256(amendment_raw)
    if amendment_sha256_actual != amendment_sha256:
        raise PreparationError("diagnostic amendment changed while being read")

    disposition: dict[str, Any] | None = None
    disposition_raw = b""
    review_memo_raw = b""
    review_memo_sha256: str | None = None
    if launch:
        disposition, disposition_raw, review_memo_raw, review_memo_sha256 = _validate_disposition(
            repository_root=repository_root,
            amendment_sha256=amendment_sha256,
            disposition_path=disposition_path,
            review_memo_path=review_memo_path,
        )
        claim_path = runs_root / ATTEMPT_CLAIM_NAME
        if claim_path.exists() or claim_path.is_symlink():
            raise PreparationError(
                f"dry_four's one candidate6 attempt is already claimed: {claim_path}"
            )

    candidate_info = _validate_candidate_artifacts(
        repository_root=repository_root, candidate_root=candidate_root, executable=executable
    )
    source = _resolve_under_root(source, repository_root, "allowlisted candidate5 input directory")
    expected_source = (repository_root / INPUT_RELATIVE_PATH).resolve(strict=True)
    if source != expected_source:
        raise PreparationError(
            "the diagnostic accepts only the exact candidate5 dry_four input directory"
        )
    bundle_root, final_run_id = _create_bundle(runs_root, run_id)
    preflight = stage_inputs(source, bundle_root / "dry_four")
    if preflight.get("input_sha256") != INPUTS:
        raise PreparationError("independent input preflight produced unexpected hashes")
    output_map_raw, output_map_sha256 = _validate_output_map(
        repository_root, preflight["input_sha256"]
    )
    copied_sources = _copy_preparation_sources(
        repository_root=repository_root,
        bundle_root=bundle_root,
        amendment_raw=amendment_raw,
        output_map_raw=output_map_raw,
        candidate_root=candidate_root,
        candidate_info=candidate_info,
    )

    config, solver_argv = _make_supervisor_config(bundle_root)
    config_path = bundle_root / "metadata" / "source-supervisor.json"
    config_raw = _write_json_exclusive(config_path, config)
    parsed_config = RunConfig.from_json(config_path)
    if parsed_config.disk_roots != (bundle_root,) or parsed_config.evidence_dir != (
        bundle_root / "supervisor" / "evidence"
    ):
        raise PreparationError("supervisor config does not bind the full bundle disk root")

    identity_output_path = bundle_root / "metadata" / "candidate6-identity.json"
    identity_argv = [
        sys.executable,
        str(repository_root / IDENTITY_VERIFIER_RELATIVE_PATH),
        "--candidate-root",
        str(candidate_root),
        "--archive",
        str(candidate_root / "docker-save.tar"),
        "--layout",
        str(candidate_root / "layout"),
        "--repository-root",
        str(repository_root),
        "--executable",
        str(executable),
        "--docker",
        docker,
        "--output",
        str(identity_output_path),
    ]
    run_local_argv = [
        sys.executable,
        str(repository_root / RUN_LOCAL_RELATIVE_PATH),
        "--gpu",
        "--threads",
        "2",
        "--source-supervisor",
        str(config_path),
        "--",
        *solver_argv,
    ]
    command_record = {
        "schema_version": "flutas-dry-four-command-record-v1",
        "solver_image": PINNED_IMAGE_ID,
        "docker_entrypoint_override": "mpirun",
        "working_directory_in_container": HOST_CASE_PATH,
        "solver_argv_after_entrypoint": solver_argv,
        "effective_solver_argv": ["mpirun", *solver_argv],
        "run_local_argv": run_local_argv,
        "identity_verifier_argv": identity_argv,
        "container_environment": {
            "OMP_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMPI_NUM_THREADS": "1",
            "OMPI_ALLOW_RUN_AS_ROOT": "1",
            "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM": "1",
        },
        "host_environment_policy": "run_local.py inherits host environment and sets common thread controls to 2",
        "solver_rank_count": 1,
        "candidate_identity_verifier_runs_only_with_launch": True,
    }
    command_path = bundle_root / "metadata" / "command.json"
    command_raw = _write_json_exclusive(command_path, command_record)

    if launch:
        assert disposition is not None and review_memo_sha256 is not None
        _write_exclusive(bundle_root / "metadata" / "primary-disposition.json", disposition_raw)
        _write_exclusive(bundle_root / "metadata" / "astra-review-memo.md", review_memo_raw)
    run_local_returncode: int | None = None
    state = "LAUNCH_AUTHORIZED_PENDING_IDENTITY" if launch else "PREPARED_ONLY_PROSPECTIVE"

    manifest = {
        "schema_version": "flutas-dry-four-launch-bundle-v1",
        "case_id": CASE_ID,
        "candidate_id": "candidate6-20260928T093141Z-4092509",
        "bundle_id": bundle_root.name,
        "bundle_root": str(bundle_root),
        "created_utc": _now_utc(),
        "state": state,
        "scientific_gate": "PROSPECTIVE_ONLY; this diagnostic is not source-physics or E0-E6 validation",
        "amendment": {
            "path": str(AMENDMENT_RELATIVE_PATH),
            "sha256": amendment_sha256,
            "expected_sha256_pin": EXPECTED_AMENDMENT_SHA256,
            "expected_sha256_pin_configured": EXPECTED_AMENDMENT_SHA256 is not None,
            "status_in_amendment": "proposed; launch requires exact primary disposition",
        },
        "output_map": {"path": str(OUTPUT_MAP_RELATIVE_PATH), "sha256": output_map_sha256},
        "source_input_directory": str(source),
        "input_preflight": preflight,
        "input_staging_directory": str(bundle_root / "dry_four"),
        "input_sha256": preflight["input_sha256"],
        "candidate": candidate_info,
        "candidate_metadata_copies": copied_sources,
        "oci_layout_policy": "retained external immutable layout; identity verifier hashes its selected blobs at launch",
        "supervisor_config_path": str(config_path),
        "supervisor_config_sha256": _sha256(config_raw),
        "supervisor_config": config,
        "command_record_path": str(command_path),
        "command_record_sha256": _sha256(command_raw),
        "solver_exit_status": run_local_returncode,
        "approval_gate": (
            {
                "status": "ACCEPTED_TO_LAUNCH",
                "review_status": "ACCEPT",
                "reviewer": "gpt-6-astra/max",
                "scope": "dry_four_execution_telemetry_only",
                "amendment_sha256": amendment_sha256,
                "reviewer_memo_sha256": review_memo_sha256,
            }
            if launch
            else {
                "status": "PROSPECTIVE; NOT APPROVED TO LAUNCH",
                "required_disposition": str(DISPOSITION_RELATIVE_PATH),
                "required_review_status": "ACCEPT",
            }
        ),
    }
    manifest_path = bundle_root / "metadata" / "run-manifest.json"
    _write_json_exclusive(manifest_path, manifest)

    if launch:
        assert review_memo_sha256 is not None
        claim_raw = _claim_single_attempt(
            runs_root=runs_root,
            bundle_root=bundle_root,
            amendment_sha256=amendment_sha256,
            reviewer_memo_sha256=review_memo_sha256,
        )
        launch_error: BaseException | None = None
        try:
            identity_stdout_path = bundle_root / "logs" / "candidate-identity.stdout.log"
            identity_stderr_path = bundle_root / "logs" / "candidate-identity.stderr.log"
            identity_result = _run_identity_verifier(
                repository_root=repository_root,
                candidate_root=candidate_root,
                executable=executable,
                output_path=identity_output_path,
                docker=docker,
            )
            identity_returncode, identity_stdout, identity_stderr, actual_identity_argv = (
                identity_result
            )
            _write_exclusive(identity_stdout_path, identity_stdout)
            _write_exclusive(identity_stderr_path, identity_stderr)
            _write_json_exclusive(
                bundle_root / "metadata" / "candidate-identity-command.json",
                {
                    "argv": actual_identity_argv,
                    "returncode": identity_returncode,
                    "stdout_sha256": _sha256(identity_stdout),
                    "stderr_sha256": _sha256(identity_stderr),
                    "attempt_claim_sha256": _sha256(claim_raw),
                },
            )
            if identity_returncode != 0:
                raise PreparationError(
                    "candidate/image identity verifier failed with exit status "
                    f"{identity_returncode}; the one attempt is consumed and must not be retried"
                )
            _check_identity_output(identity_output_path)
            solver_stdout = bundle_root / "logs" / "run-local.stdout.log"
            solver_stderr = bundle_root / "logs" / "run-local.stderr.log"
            run_local_returncode, actual_run_local_argv = _run_local_supervisor(
                repository_root=repository_root,
                config_path=config_path,
                solver_argv=solver_argv,
                stdout_path=solver_stdout,
                stderr_path=solver_stderr,
            )
            _write_json_exclusive(
                bundle_root / "metadata" / "run-local-command.json",
                {
                    "argv": actual_run_local_argv,
                    "returncode": run_local_returncode,
                    "stdout_sha256": _file_sha256(solver_stdout)[0],
                    "stderr_sha256": _file_sha256(solver_stderr)[0],
                    "attempt_claim_sha256": _sha256(claim_raw),
                },
            )
            state = "SUPERVISED_LAUNCH_FINISHED"
            _write_json_exclusive(
                bundle_root / "metadata" / "launch-result.json",
                {
                    "state": state,
                    "solver_exit_status": run_local_returncode,
                    "attempt_claim_sha256": _sha256(claim_raw),
                    "finished_utc": _now_utc(),
                },
            )
        except BaseException as exc:
            failure_path = bundle_root / "metadata" / "launch-failure.json"
            if not failure_path.exists():
                _write_json_exclusive(
                    failure_path,
                    {
                        "state": "FAILED_OR_INCOMPLETE; ONE ATTEMPT RESERVED",
                        "failure_type": type(exc).__name__,
                        "failure": str(exc),
                        "attempt_claim_sha256": _sha256(claim_raw),
                        "failed_utc": _now_utc(),
                    },
                )
            launch_error = exc

        # Finalize only after run_local has returned and released the GPU lock.
        # If setup or execution failed, the same CPU-only path records a failed
        # result and inventories every artifact retained up to that point.
        finalization = finalize_bundle(
            bundle_root,
            repository_root=repository_root,
            invocation=(
                launcher_invocation
                if launcher_invocation is not None
                else [
                    "in-process",
                    "scripts.prepare_flutas_dry_four.prepare_bundle",
                    "--launch",
                    final_run_id,
                ]
            ),
        )
        if launch_error is not None:
            raise launch_error
    else:
        finalization = None
    return {
        "bundle_root": str(bundle_root),
        "bundle_id": final_run_id,
        "state": state,
        "manifest_sha256": _file_sha256(manifest_path)[0],
        "solver_exit_status": run_local_returncode,
        "finalization": finalization,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument(
        "--source", type=Path, help="allowlisted candidate5 dry_four input directory"
    )
    parser.add_argument("--run-id", help="optional unique suffix; an existing bundle is refused")
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--disposition", type=Path)
    parser.add_argument("--review-memo", type=Path)
    parser.add_argument("--docker", default="docker")
    parser.add_argument(
        "--launch",
        action="store_true",
        help="verify exact primary disposition, claim the sole attempt and invoke the supervisor",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(effective_argv)
    try:
        result = prepare_bundle(
            repository_root=args.repo_root,
            runs_root=args.runs_root,
            source=args.source,
            run_id=args.run_id,
            candidate_root=args.candidate_root,
            executable=args.executable,
            disposition_path=args.disposition,
            review_memo_path=args.review_memo,
            launch=args.launch,
            docker=args.docker,
            launcher_invocation=[
                sys.executable,
                str(Path(__file__).resolve()),
                *effective_argv,
            ],
        )
    except (
        FileExistsError,
        OSError,
        UnicodeDecodeError,
        ValueError,
        subprocess.SubprocessError,
        PreparationError,
    ) as exc:
        parser.exit(2, f"dry_four preparation failed: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    finalization = result.get("finalization")
    if isinstance(finalization, dict) and finalization.get("status") != "complete":
        return 2
    if result["solver_exit_status"] not in (None, 0):
        return int(result["solver_exit_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
