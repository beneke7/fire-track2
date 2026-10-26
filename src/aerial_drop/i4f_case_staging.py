"""Hash-verified staging of immutable I4F templates and canonical restarts.

The caller supplies every file and expected SHA256. Staging never discovers
frozen bytes from a live working case, and it never prunes a copied case tree.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TypeAlias

CORE_RESTART_FIELDS = (
    "alpha.water",
    "p",
    "p_rgh",
    "T",
    "U",
    "T.air",
    "T.water",
    "rho",
    "phi",
    "alphaPhi0.water",
    "dgdt",
)
NATIVE_MESH_FILES = (
    "boundary",
    "faces",
    "neighbour",
    "owner",
    "points",
)
COLLATED_ADDRESSING_FILES = (
    "boundaryProcAddressing",
    "cellProcAddressing",
    "faceProcAddressing",
    "pointProcAddressing",
)
_TEMPLATE_SCHEMA = "i4f-static-template/v1"
_STAGE_SCHEMA = "i4f-canonical-checkpoint-stage/v1"
_TIME_VALUE_RE = re.compile(r"(?m)^\s*value\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*;")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_TIME_NAME_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


@dataclass(frozen=True)
class VerifiedFile:
    """A source file plus its caller-pinned SHA256."""

    path: Path
    sha256: str


@dataclass(frozen=True)
class StaticTemplate:
    """A materialized template whose file and manifest hashes are rechecked on use."""

    path: Path
    manifest_sha256: str


@dataclass(frozen=True)
class StagedCase:
    """The staged case path and hash of its provenance manifest."""

    path: Path
    manifest_sha256: str


CheckpointFiles: TypeAlias = Mapping[str, VerifiedFile]


def sha256_file(path: Path) -> str:
    """Hash a file using bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA256 hex digest")


def _relative_path(value: str, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} must be a non-empty POSIX relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != value
    ):
        raise ValueError(f"{label} must be canonical, relative, and contain no traversal")
    return relative


def _is_numeric_time(value: str) -> bool:
    return bool(_TIME_NAME_RE.fullmatch(value)) and math.isfinite(float(value))


def _validate_template_path(value: str, *, freeze_dynamic_code: bool) -> PurePosixPath:
    relative = _relative_path(value, label="template destination")
    parts = relative.parts
    if parts[0] in {"provenance", "static-template.json"}:
        raise ValueError(f"reserved template path: {value}")
    if _is_numeric_time(parts[0]):
        raise ValueError(f"numeric time directories are not static template inputs: {value}")
    if len(parts) > 1 and re.fullmatch(r"processors\d+", parts[0]) and _is_numeric_time(parts[1]):
        raise ValueError(f"processor time directories are not static template inputs: {value}")
    if parts[0] == "dynamicCode" and not freeze_dynamic_code:
        raise _UndeclaredDynamicCode(value)
    if value == "system/controlDict":
        raise ValueError("system/controlDict must come from the protected source argument")
    return relative


class _UndeclaredDynamicCode(ValueError):
    """Internal marker for a generated dynamicCode cache that must be omitted."""


def _verify_source(source: VerifiedFile, *, label: str) -> dict[str, object]:
    _validate_digest(source.sha256, f"{label} digest")
    if source.path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {source.path}")
    if not source.path.is_file():
        raise FileNotFoundError(f"{label} is missing or not a regular file: {source.path}")
    actual = sha256_file(source.path)
    if actual != source.sha256:
        raise ValueError(
            f"{label} SHA256 mismatch: expected {source.sha256}, got {actual} ({source.path})"
        )
    return {
        "source": str(source.path),
        "bytes": source.path.stat().st_size,
        "sha256": actual,
    }


def _control_bytes(source: Path | bytes, expected_sha256: str) -> tuple[bytes | None, Path | None]:
    _validate_digest(expected_sha256, "protected controlDict digest")
    if isinstance(source, bytes):
        actual = hashlib.sha256(source).hexdigest()
        if actual != expected_sha256:
            raise ValueError(
                f"protected controlDict SHA256 mismatch: expected {expected_sha256}, got {actual}"
            )
        return source, None
    path = Path(source)
    _verify_source(VerifiedFile(path, expected_sha256), label="protected controlDict")
    return None, path


def _mesh_inventory(paths: set[str]) -> dict[str, object]:
    native = {f"constant/polyMesh/{name}" for name in NATIVE_MESH_FILES}
    missing_native = sorted(native - paths)
    if missing_native:
        raise ValueError(f"static template lacks native polyMesh files: {missing_native}")

    collated_groups = sorted(
        {
            PurePosixPath(path).parts[0]
            for path in paths
            if re.fullmatch(r"processors\d+", PurePosixPath(path).parts[0])
        }
    )
    collated: dict[str, list[str]] = {}
    for prefix in collated_groups:
        required = {
            f"{prefix}/constant/polyMesh/{name}"
            for name in (*NATIVE_MESH_FILES, *COLLATED_ADDRESSING_FILES)
        }
        missing = sorted(required - paths)
        if missing:
            raise ValueError(f"static template lacks {prefix} mesh/addressing files: {missing}")
        collated[prefix] = sorted(required)

    return {
        "native": sorted(native),
        "collated": collated,
    }


def _canonical_json(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _copy_to(root: Path, relative: str, source: Path) -> None:
    target = root.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _verify_tree_files(root: Path, records: list[dict[str, object]]) -> None:
    for record in records:
        relative = str(record["path"])
        relative_path = _relative_path(relative, label="manifest file path")
        expected_digest = str(record["sha256"])
        _validate_digest(expected_digest, f"manifest digest for {relative}")
        target = root.joinpath(*relative_path.parts)
        if target.is_symlink():
            raise RuntimeError(f"staged input must not be a symlink: {relative}")
        if not target.is_file():
            raise RuntimeError(f"staged input is missing: {relative}")
        size = target.stat().st_size
        digest = sha256_file(target)
        if size != record["bytes"] or digest != expected_digest:
            raise RuntimeError(
                f"staged input mismatch for {relative}: "
                f"{size} bytes / {digest}, expected {record['bytes']} / {record['sha256']}"
            )


def _remove_temp(path: Path) -> None:
    if path.exists():
        for directory, _, files in os.walk(path):
            for name in files:
                try:
                    (Path(directory) / name).chmod(0o600)
                except OSError:
                    pass
            try:
                Path(directory).chmod(0o700)
            except OSError:
                pass
        shutil.rmtree(path, ignore_errors=True)


def build_static_template(
    destination: Path,
    static_inputs: Mapping[str, VerifiedFile],
    *,
    control_dict_source: Path | bytes,
    control_dict_sha256: str,
    freeze_dynamic_code: bool = False,
) -> StaticTemplate:
    """Build a new template from hash-pinned files and protected controlDict bytes.

    Generated dynamicCode entries are recorded as excluded unless callers
    explicitly declare them frozen with freeze_dynamic_code=True.
    """

    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite static template: {destination}")

    control_bytes, control_path = _control_bytes(control_dict_source, control_dict_sha256)
    selected: list[tuple[str, VerifiedFile]] = []
    excluded_dynamic_code: list[str] = []
    for name, source in static_inputs.items():
        try:
            relative = _validate_template_path(name, freeze_dynamic_code=freeze_dynamic_code)
        except _UndeclaredDynamicCode:
            excluded_dynamic_code.append(name)
            continue
        _verify_source(source, label=f"static input {name}")
        selected.append((relative.as_posix(), source))

    if "system/controlDict" in {name for name, _ in selected}:
        raise ValueError("system/controlDict was supplied twice")
    selected.append(
        (
            "system/controlDict",
            VerifiedFile(control_path, control_dict_sha256)
            if control_path is not None
            else VerifiedFile(Path("<provided-bytes>"), control_dict_sha256),
        )
    )
    paths = {name for name, _ in selected}
    if "constant" not in paths and not any(name.startswith("constant/") for name in paths):
        raise ValueError("static template must include constant inputs")
    if not any(name.startswith("system/") for name in paths):
        raise ValueError("static template must include system inputs")
    mesh = _mesh_inventory(paths)

    source_records: list[dict[str, object]] = []
    for name, source in selected:
        if name == "system/controlDict" and control_bytes is not None:
            source_records.append(
                {
                    "path": name,
                    "bytes": len(control_bytes),
                    "sha256": control_dict_sha256,
                    "source": "explicit-protected-bytes",
                }
            )
        else:
            checked = _verify_source(source, label=f"static input {name}")
            source_records.append({"path": name, **checked})

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}.template-", dir=destination.parent))
    try:
        copied: list[dict[str, object]] = []
        for name, source in selected:
            record = next(item for item in source_records if item["path"] == name)
            target = temp.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if name == "system/controlDict" and control_bytes is not None:
                target.write_bytes(control_bytes)
            else:
                assert source.path != Path("<provided-bytes>")
                shutil.copyfile(source.path, target)
            actual = sha256_file(target)
            size = target.stat().st_size
            if actual != record["sha256"] or size != record["bytes"]:
                raise RuntimeError(f"template copy did not preserve verified input: {name}")
            copied.append(dict(record))

        manifest = {
            "schema": _TEMPLATE_SCHEMA,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "files": sorted(copied, key=lambda row: str(row["path"])),
            "excluded_undeclared_dynamic_code": sorted(excluded_dynamic_code),
            "protected_control_dict_sha256": control_dict_sha256,
            "mesh": mesh,
        }
        manifest_bytes = _canonical_json(manifest)
        (temp / "static-template.json").write_bytes(manifest_bytes)
        _verify_tree_files(temp, copied)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"refusing to overwrite static template: {destination}")
        os.rename(temp, destination)
        return StaticTemplate(destination, hashlib.sha256(manifest_bytes).hexdigest())
    except Exception:
        _remove_temp(temp)
        raise


def load_static_template(path: Path, expected_manifest_sha256: str) -> StaticTemplate:
    """Reopen a template only when its protected manifest hash is supplied."""

    _validate_digest(expected_manifest_sha256, "static template manifest digest")
    template = Path(path)
    manifest_path = template / "static-template.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"static template manifest is missing: {manifest_path}")
    actual = sha256_file(manifest_path)
    if actual != expected_manifest_sha256:
        raise ValueError(
            f"static template manifest SHA256 mismatch: expected {expected_manifest_sha256}, got {actual}"
        )
    return StaticTemplate(template, actual)


def _read_template(template: StaticTemplate) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest_path = template.path / "static-template.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"static template manifest is missing: {manifest_path}")
    actual = sha256_file(manifest_path)
    if actual != template.manifest_sha256:
        raise ValueError(
            f"static template manifest changed: expected {template.manifest_sha256}, got {actual}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != _TEMPLATE_SCHEMA:
        raise ValueError(f"unsupported static template schema: {manifest.get('schema')!r}")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise ValueError("static template manifest has no file list")
    _verify_tree_files(template.path, records)
    paths = {str(record["path"]) for record in records}
    mesh = _mesh_inventory(paths)
    if manifest.get("mesh") != mesh:
        raise ValueError("static template mesh inventory differs from its manifest")
    return manifest, records


def _checkpoint_relative(name: str) -> PurePosixPath:
    relative = _relative_path(name, label="checkpoint field")
    if len(relative.parts) != 1:
        raise ValueError(f"checkpoint field must be a basename: {name}")
    return relative


def _uniform_time_value(path: Path, expected_sha256: str) -> float:
    _verify_source(VerifiedFile(path, expected_sha256), label="canonical uniform/time")
    try:
        text = path.read_text(encoding="ascii")
    except UnicodeDecodeError as error:
        raise ValueError("canonical uniform/time is not ASCII") from error
    match = _TIME_VALUE_RE.search(text)
    if not match:
        raise ValueError("canonical uniform/time has no simple value <number>; entry")
    value = float(match.group(1))
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"canonical uniform/time value is invalid: {value}")
    return value


def stage_canonical_checkpoint(
    template: StaticTemplate,
    destination: Path,
    *,
    time_name: str,
    fields: CheckpointFiles,
    uniform_time: VerifiedFile,
    checkpoint_prefix: str = "processors10",
    required_fields: tuple[str, ...] = CORE_RESTART_FIELDS,
) -> StagedCase:
    """Stage exactly one hash-pinned canonical time without pruning template content.

    checkpoint_prefix is empty for a serial case or a collated processorsN
    directory for a parallel restart. All supplied fields, including T.air
    and T.water, come from the caller's canonical sources and are hash-checked.
    """

    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite staged case: {destination}")

    if not _TIME_NAME_RE.fullmatch(time_name) or not _is_numeric_time(time_name):
        raise ValueError(f"checkpoint time name is not numeric: {time_name!r}")
    time_value = _uniform_time_value(uniform_time.path, uniform_time.sha256)
    if not math.isclose(time_value, float(time_name), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"uniform/time value {time_value:.17g} does not match directory {time_name}"
        )

    if checkpoint_prefix:
        prefix = _relative_path(checkpoint_prefix, label="checkpoint prefix")
        if len(prefix.parts) != 1 or not re.fullmatch(r"processors\d+", prefix.parts[0]):
            raise ValueError("checkpoint prefix must be empty or a single processorsN directory")
        checkpoint_prefix = prefix.as_posix()
    else:
        checkpoint_prefix = ""

    for name in required_fields:
        _checkpoint_relative(name)
    missing = sorted(set(required_fields) - set(fields))
    if missing:
        raise ValueError(f"canonical checkpoint is missing required fields: {missing}")
    for name in fields:
        _checkpoint_relative(name)

    template_manifest, static_records = _read_template(template)
    if checkpoint_prefix:
        collated = template_manifest["mesh"]["collated"]
        if checkpoint_prefix not in collated:
            raise ValueError(f"template has no verified collated mesh for {checkpoint_prefix}")

    source_rows: list[dict[str, object]] = []
    for name, source in sorted(fields.items()):
        verified = _verify_source(source, label=f"canonical checkpoint field {name}")
        target = PurePosixPath(checkpoint_prefix, time_name, name).as_posix()
        source_rows.append({"path": target, **verified, "field": name})
    time_target = PurePosixPath(checkpoint_prefix, time_name, "uniform/time").as_posix()
    time_record = _verify_source(uniform_time, label="canonical uniform/time")
    source_rows.append({"path": time_target, **time_record, "field": "uniform/time"})

    static_paths = {str(record["path"]) for record in static_records}
    staged_paths = {str(record["path"]) for record in source_rows}
    if static_paths & staged_paths:
        raise ValueError(
            f"checkpoint paths collide with static template: {sorted(static_paths & staged_paths)}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    try:
        copied_static: list[dict[str, object]] = []
        for record in static_records:
            relative = str(record["path"])
            source = template.path.joinpath(*PurePosixPath(relative).parts)
            target = temp.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            actual = sha256_file(target)
            if actual != record["sha256"] or target.stat().st_size != record["bytes"]:
                raise RuntimeError(f"static template copy changed: {relative}")
            copied_static.append(dict(record))

        copied_checkpoint: list[dict[str, object]] = []
        for name, source in sorted(fields.items()):
            target_relative = PurePosixPath(checkpoint_prefix, time_name, name).as_posix()
            _copy_to(temp, target_relative, source.path)
            target = temp.joinpath(*PurePosixPath(target_relative).parts)
            record = next(row for row in source_rows if row["path"] == target_relative)
            if sha256_file(target) != record["sha256"] or target.stat().st_size != record["bytes"]:
                raise RuntimeError(f"canonical checkpoint copy changed: {target_relative}")
            copied_checkpoint.append(dict(record))
        _copy_to(temp, time_target, uniform_time.path)
        time_output = temp.joinpath(*PurePosixPath(time_target).parts)
        if sha256_file(time_output) != time_record["sha256"]:
            raise RuntimeError("canonical uniform/time copy changed")
        copied_checkpoint.append(next(row for row in source_rows if row["path"] == time_target))

        _verify_tree_files(temp, copied_static + copied_checkpoint)
        stage_manifest = {
            "schema": _STAGE_SCHEMA,
            "staged_utc": datetime.now(timezone.utc).isoformat(),
            "template_manifest_sha256": template.manifest_sha256,
            "protected_control_dict_sha256": template_manifest["protected_control_dict_sha256"],
            "checkpoint_time_name": time_name,
            "checkpoint_time_value_s": time_value,
            "checkpoint_prefix": checkpoint_prefix,
            "required_fields": list(required_fields),
            "canonical_checkpoint_fields": sorted(fields),
            "static_files": sorted(copied_static, key=lambda row: str(row["path"])),
            "checkpoint_files": sorted(copied_checkpoint, key=lambda row: str(row["path"])),
            "mesh": template_manifest["mesh"],
            "copy_policy": {
                "no_numeric_time_pruning": True,
                "only_selected_checkpoint_copied": True,
                "copy_mode": "independent writable file copies",
            },
        }
        provenance = temp / "provenance"
        provenance.mkdir()
        manifest_bytes = _canonical_json(stage_manifest)
        (provenance / "staging-manifest.json").write_bytes(manifest_bytes)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"refusing to overwrite staged case: {destination}")
        os.rename(temp, destination)
        return StagedCase(destination, hashlib.sha256(manifest_bytes).hexdigest())
    except Exception:
        _remove_temp(temp)
        raise
