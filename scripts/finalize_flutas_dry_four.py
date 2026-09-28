#!/usr/bin/env python3
"""Finalize the frozen candidate6 dry_four output bundle.

Policy: this command runs only after the launcher and GPU lock have returned.
It requires a recorded zero solver status, runs the independent retained-output
checker, stores that checker's report, and only then calls the frozen manifest
adapter in-process. It never starts Docker, a solver, or a GPU task. Any failed
stage is recorded in metadata/finalization-result.json and must not yield a
normal manifest. The final sorted SHA256SUMS covers every singly-linked regular
file below the bundle except itself and metadata/SHA256SUMS.sha256; symlinks,
hardlinks, and special files are rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCHEMA_PATH = (
    REPO_ROOT
    / "containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/reference/schema-v1.2.md"
)
ADAPTER_PATH = REPO_ROOT / "containers/flutas/candidate6/tools/write_dry_four_manifest.py"
ANALYZER_PATH = REPO_ROOT / "src/aerial_drop/flutas_source_analyzer.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import flutas_dry_four_output_check as output_check  # noqa: E402


class FinalizationError(ValueError):
    """A completed bundle failed the finalization policy."""


def _load_adapter(repository_root: Path = REPO_ROOT) -> ModuleType:
    """Load the pinned adapter module so its public ``main(argv)`` can be called."""
    adapter_path = repository_root / "containers/flutas/candidate6/tools/write_dry_four_manifest.py"
    spec = importlib.util.spec_from_file_location(
        "_flutas_candidate6_dry_four_manifest_adapter", adapter_path
    )
    if spec is None or spec.loader is None:
        raise FinalizationError(f"cannot load manifest adapter: {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adapter_argv(bundle: Path, repository_root: Path = REPO_ROOT) -> list[str]:
    schema_path = (
        repository_root
        / "containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/reference/schema-v1.2.md"
    )
    analyzer_path = repository_root / "src/aerial_drop/flutas_source_analyzer.py"
    return [
        "--schema",
        str(schema_path),
        "--case-root",
        str(bundle / "dry_four"),
        "--run-dir",
        str(bundle),
        "--candidate-build",
        str(bundle / "metadata/candidate-build.json"),
        "--analyzer",
        str(analyzer_path),
        "--supervisor-dir",
        str(bundle / "supervisor/evidence"),
        "--stdout",
        str(bundle / "supervisor/evidence/stdout.log"),
        "--performance-output",
        str(bundle / "work/data/performance.out"),
        "--run-metadata-output",
        str(bundle / "analysis/adapter-run-metadata.json"),
        "--timestep-inputs",
        str(bundle / "work/data/restas_timestep-inputs.json"),
        "--output",
        str(bundle / "manifest.json"),
    ]


def _invoke_adapter(argv: list[str], repository_root: Path = REPO_ROOT) -> int:
    adapter = _load_adapter(repository_root)
    return adapter.main(argv)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_json_new(path: Path, value: Any) -> None:
    raw = _json_bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def _replace_owned_json(path: Path, value: Any) -> None:
    """Update a result file created by this finalizer without following links."""
    try:
        before = path.lstat()
    except FileNotFoundError as error:
        raise FinalizationError(f"finalization result disappeared before update: {path}") from error
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_nlink != 1:
        raise FinalizationError(f"finalization result is not a singly-linked regular file: {path}")
    flags = os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "wb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise FinalizationError(
                f"finalization result is not a singly-linked regular file: {path}"
            )
        os.ftruncate(stream.fileno(), 0)
        stream.write(_json_bytes(value))


def _ensure_real_directory(bundle: Path, relative: str) -> Path:
    path = bundle / relative
    try:
        info = path.lstat()
    except FileNotFoundError:
        path.mkdir()
        info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise FinalizationError(f"bundle directory is not a real directory: {path}")
    return path


def _read_launch_result(bundle: Path) -> int:
    path = bundle / "metadata/launch-result.json"
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise FinalizationError("metadata/launch-result.json is required") from error
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise FinalizationError("metadata/launch-result.json must be singly-linked regular data")
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalizationError(f"metadata/launch-result.json is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise FinalizationError("metadata/launch-result.json must contain a JSON object")
    status = value.get("solver_exit_status")
    if type(status) is not int:
        raise FinalizationError("launch result must contain an integer solver_exit_status")
    return status


def _walk_bundle(bundle: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """Return inventory files and any unsupported filesystem entries."""
    files: list[tuple[str, Path]] = []
    problems: list[str] = []
    root_info = bundle.lstat()
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise FinalizationError("bundle root must be a real directory")

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as scanner:
                entries = sorted(scanner, key=lambda entry: entry.name)
        except OSError as error:
            problems.append(f"cannot scan {directory.relative_to(bundle)}: {error}")
            return
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(bundle).as_posix()
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as error:
                problems.append(f"cannot inspect {relative}: {error}")
                continue
            if stat.S_ISLNK(info.st_mode):
                problems.append(f"symlink rejected: {relative}")
                continue
            if stat.S_ISDIR(info.st_mode):
                visit(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                problems.append(f"special file rejected: {relative}")
                continue
            if info.st_nlink != 1:
                problems.append(f"hardlink rejected: {relative} has link count {info.st_nlink}")
                continue
            if relative in {"SHA256SUMS", "metadata/SHA256SUMS.sha256"}:
                continue
            files.append((relative, path))

    visit(bundle)
    files.sort(key=lambda item: item[0])
    return files, problems


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksum_file(path: Path, raw: bytes) -> None:
    """Create or safely replace one of the two excluded checksum files."""
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
    if before is not None and stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode):
        raise FinalizationError(f"checksum output path is a directory: {path}")
    if before is not None and (
        stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
    ):
        # The inventory scan records this unsafe entry. Remove only the output
        # directory entry so a deterministic checksum artifact can still be made.
        path.unlink()
        before = None
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_EXCL if before is None else 0
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise FinalizationError(f"checksum output must be singly-linked regular data: {path}")
        os.ftruncate(stream.fileno(), 0)
        stream.write(raw)


def _write_inventory(bundle: Path) -> list[str]:
    files, problems = _walk_bundle(bundle)
    lines = [f"{_sha256(path)}  ./{relative}\n" for relative, path in files]
    raw = "".join(lines).encode("utf-8")
    sums_path = bundle / "SHA256SUMS"
    sidecar_path = bundle / "metadata/SHA256SUMS.sha256"
    _write_checksum_file(sums_path, raw)
    sidecar = f"{hashlib.sha256(raw).hexdigest()}  SHA256SUMS\n".encode("ascii")
    _write_checksum_file(sidecar_path, sidecar)
    return problems


def _command_record(
    bundle: Path, repository_root: Path, invocation: Sequence[str]
) -> dict[str, Any]:
    return {
        "command": list(invocation),
        "adapter": {
            "entrypoint": str(
                repository_root / "containers/flutas/candidate6/tools/write_dry_four_manifest.py"
            ),
            "call": "main(argv)",
            "argv": _adapter_argv(bundle, repository_root),
            "invocation_mode": "in_process",
        },
        "checker": {
            "call": "scripts.flutas_dry_four_output_check.check_bundle(bundle)",
            "bundle": str(bundle),
        },
        "policy": {
            "solver_exit_status_required": 0,
            "adapter_after_checker_pass_only": True,
            "external_solver_or_docker_started": False,
            "gpu_accessed": False,
            "inventory_exclusions": ["SHA256SUMS", "metadata/SHA256SUMS.sha256"],
            "filesystem_policy": "reject symlinks, hardlinks, and special files",
        },
        "schema": str(
            repository_root
            / "containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/reference/schema-v1.2.md"
        ),
    }


def _remove_failed_manifest(bundle: Path) -> str | None:
    path = bundle / "manifest.json"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        return "adapter left a directory at manifest.json; it was preserved"
    try:
        path.unlink()
    except OSError as error:
        return f"could not remove failed adapter manifest output: {error}"
    return None


def finalize_bundle(
    bundle_root: Path,
    repository_root: Path = REPO_ROOT,
    *,
    invocation: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Check and finalize a returned dry_four bundle, retaining failure evidence."""
    bundle = Path(bundle_root).absolute()
    repository = Path(repository_root).absolute()
    try:
        root_info = bundle.lstat()
    except OSError as error:
        raise FinalizationError(f"cannot access bundle root {bundle}: {error}") from error
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise FinalizationError("bundle root must be a real directory")

    metadata_dir = _ensure_real_directory(bundle, "metadata")
    _ensure_real_directory(bundle, "analysis")
    command_path = metadata_dir / "finalizer-command.json"
    if invocation is None:
        invocation = ["in-process", "finalize_bundle", str(bundle)]
    command = _command_record(bundle, repository, invocation)
    _write_json_new(command_path, command)

    result: dict[str, Any] = {
        "status": "failed",
        "bundle": str(bundle),
        "solver_exit_status": None,
        "checker_status": "not_run",
        "adapter_status": "not_run",
        "manifest": None,
        "failure_stage": None,
        "error": None,
    }
    _initial_files, initial_problems = _walk_bundle(bundle)
    adapter_was_invoked = False
    if initial_problems:
        result["failure_stage"] = "filesystem_preflight"
        result["error"] = "; ".join(initial_problems)
    else:
        stage = "launch_result"
        try:
            result["solver_exit_status"] = _read_launch_result(bundle)
            if result["solver_exit_status"] != 0:
                raise FinalizationError(
                    f"solver exit status is {result['solver_exit_status']}, expected 0"
                )
            manifest_path = bundle / "manifest.json"
            if manifest_path.exists() or manifest_path.is_symlink():
                raise FinalizationError("manifest.json already exists before finalization")

            stage = "checker"
            report = output_check.check_bundle(bundle)
            if not isinstance(report, dict) or report.get("status") != "complete":
                raise FinalizationError("output checker did not return a complete report")
            annex_path = bundle / "analysis/dry-output-annex.json"
            _write_json_new(annex_path, report)
            result["checker_status"] = "complete"

            stage = "adapter"
            argv = _adapter_argv(bundle, repository)
            adapter_was_invoked = True
            adapter_status = _invoke_adapter(argv, repository_root=repository)
            result["adapter_status"] = adapter_status
            if type(adapter_status) is not int or adapter_status != 0:
                raise FinalizationError(f"manifest adapter returned status {adapter_status!r}")
            for path in (bundle / "analysis/adapter-run-metadata.json", manifest_path):
                try:
                    info = path.lstat()
                except OSError as error:
                    raise FinalizationError(
                        f"manifest adapter output is missing: {path}"
                    ) from error
                if (
                    not stat.S_ISREG(info.st_mode)
                    or stat.S_ISLNK(info.st_mode)
                    or info.st_nlink != 1
                ):
                    raise FinalizationError(f"manifest adapter output is not regular: {path}")
            result["status"] = "complete"
            result["manifest"] = "manifest.json"
        except (Exception, SystemExit) as error:
            result["failure_stage"] = stage
            result["error"] = f"{type(error).__name__}: {error}"
            if adapter_was_invoked:
                cleanup_error = _remove_failed_manifest(bundle)
                if cleanup_error:
                    result["error"] += f"; {cleanup_error}"

    result_path = metadata_dir / "finalization-result.json"
    _write_json_new(result_path, result)

    inventory_problems = _write_inventory(bundle)
    if inventory_problems:
        result["status"] = "failed"
        result["manifest"] = None
        result["failure_stage"] = "filesystem_inventory"
        prior_error = result["error"]
        inventory_error = "; ".join(inventory_problems)
        result["error"] = f"{prior_error}; {inventory_error}" if prior_error else inventory_error
        if adapter_was_invoked:
            cleanup_error = _remove_failed_manifest(bundle)
            if cleanup_error:
                result["error"] += f"; {cleanup_error}"
        _replace_owned_json(result_path, result)
        # The result is covered by the root inventory, so rewrite it after recording the failure.
        second_problems = _write_inventory(bundle)
        unexpected_problems = [
            problem for problem in second_problems if problem not in inventory_problems
        ]
        if unexpected_problems:
            result["error"] += "; additional inventory error: " + "; ".join(unexpected_problems)
            _replace_owned_json(result_path, result)
            _write_inventory(bundle)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="returned dry_four run bundle")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    invoked_argv = list(argv) if argv is not None else sys.argv[1:]
    invocation = [sys.executable, str(Path(__file__).resolve()), *invoked_argv]
    try:
        result = finalize_bundle(args.bundle, invocation=invocation)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"dry_four finalization failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
