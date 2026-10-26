#!/usr/bin/env python3
"""Collect v2512 native source/runtime evidence inside its Slurm allocation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_iso_vof_ledger import KNOWN_SOLVER_SOURCE_HASHES, PINNED_IMAGE  # noqa: E402

SOURCE_FILES = {
    "isoAdvectionTemplates.C": "src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvectionTemplates.C",
    "interIsoFoam_alphaEqnSubCycle.H": "applications/solvers/multiphase/interIsoFoam/alphaEqnSubCycle.H",
    "interIsoFoam_alphaEqn.H": "applications/solvers/multiphase/interIsoFoam/alphaEqn.H",
    "isoAdvection.H": "src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvection.H",
}
NATIVE_IDENTITY_FIELDS = (
    "module_name",
    "version",
    "build",
    "wm_options",
    "architecture",
    "precision",
    "label_size_bits",
    "executable_path",
    "executable_sha256",
    "solver_banner_sha256",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError(f"refusing to overwrite provenance output: {path}")
    temporary.write_text(data, encoding="utf-8")
    os.replace(temporary, path)


def _read_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _collect(
    *,
    module_name: str,
    module_list_path: Path,
    env: Mapping[str, str],
    executable_path: Path | None = None,
    architecture: str | None = None,
) -> tuple[dict[str, object], bytes]:
    if not module_name.strip():
        raise ValueError("module name must be nonempty")
    module_list_path = module_list_path.resolve(strict=True)
    module_list = module_list_path.read_text(encoding="utf-8", errors="replace")
    module_tokens = {token.strip(",:") for token in module_list.split()}
    if module_name not in module_tokens:
        raise ValueError(f"loaded module name is absent from {module_list_path}: {module_name}")

    project_dir_value = env.get("WM_PROJECT_DIR", "")
    if not project_dir_value:
        raise ValueError("WM_PROJECT_DIR is required")
    project_dir = Path(project_dir_value).resolve(strict=True)
    if not project_dir.is_dir():
        raise ValueError("WM_PROJECT_DIR must name a directory")
    version = env.get("WM_PROJECT_VERSION", "")
    if version != "v2512":
        raise ValueError(f"WM_PROJECT_VERSION must be v2512, got {version!r}")
    wm_options = env.get("WM_OPTIONS", "")
    if "DPInt32" not in wm_options:
        raise ValueError(f"WM_OPTIONS must identify a DPInt32 build, got {wm_options!r}")

    if executable_path is None:
        located = shutil.which("interIsoFoam", path=env.get("PATH"))
        if located is None:
            raise ValueError("interIsoFoam is not present on PATH")
        executable_path = Path(located)
    executable = executable_path.resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"interIsoFoam is not an executable regular file: {executable}")
    executable_hash = _sha256_file(executable)

    banner_result = subprocess.run(
        [str(executable), "-help"],
        capture_output=True,
        check=False,
        env=dict(env),
        text=True,
        timeout=60,
    )
    banner_bytes = (banner_result.stdout + banner_result.stderr).encode("utf-8")
    banner = banner_bytes.decode("utf-8", errors="replace")
    if banner_result.returncode != 0:
        raise ValueError(f"interIsoFoam -help exited with {banner_result.returncode}")
    build_match = re.search(r"(?m)^\s*Build\s*:\s*(\S.*?)\s*$", banner)
    if build_match is None:
        raise ValueError("interIsoFoam -help banner does not report a Build line")
    banner_hash = _sha256_bytes(banner_bytes)

    source_records: dict[str, dict[str, str]] = {}
    project_root = project_dir.resolve()
    if set(SOURCE_FILES) != set(KNOWN_SOLVER_SOURCE_HASHES):
        raise ValueError("collector source-file map differs from the ledger's pinned source map")
    for name, relative in SOURCE_FILES.items():
        source_path = (project_root / relative).resolve(strict=True)
        if not source_path.is_relative_to(project_root):
            raise ValueError(f"installed source path escapes WM_PROJECT_DIR: {relative}")
        digest = _sha256_file(source_path)
        expected = KNOWN_SOLVER_SOURCE_HASHES[name]
        if digest != expected:
            raise ValueError(
                f"installed OpenFOAM source differs from the pinned source reference for {name}"
            )
        source_records[name] = {
            "path": str(source_path),
            "sha256": digest,
        }

    selected_architecture = architecture or platform.machine()
    if not selected_architecture:
        raise ValueError("native architecture is unavailable")
    native_solver: dict[str, object] = {
        "module_name": module_name,
        "version": version,
        "build": build_match.group(1).strip(),
        "wm_options": wm_options,
        "architecture": selected_architecture,
        "precision": "DP",
        "label_size_bits": 32,
        "executable_path": str(executable),
        "executable_sha256": executable_hash,
        "solver_banner_sha256": banner_hash,
        "module_list_path": str(module_list_path),
        "module_list_sha256": _sha256_file(module_list_path),
        "wm_project_dir": str(project_root),
    }
    evidence: dict[str, object] = {
        "schema_version": 1,
        "execution_backend": "slurm-native",
        "source_reference_image_digest": PINNED_IMAGE,
        "solver_source": source_records,
        "native_solver": native_solver,
        "runtime_record_limitation": (
            "Installed-source and runtime metadata were collected in the active Slurm environment. "
            "This record is not proof of reproducible or bit-for-bit binary construction."
        ),
    }
    return evidence, banner_bytes


def _merge_run_manifest(
    path: Path,
    evidence: dict[str, object],
    evidence_path: Path,
) -> None:
    if path.exists():
        manifest = _read_object(path)
    else:
        manifest = {}
    native_solver = evidence["native_solver"]
    assert isinstance(native_solver, dict)
    expected_values = {
        "execution_backend": "slurm-native",
        "solver_version": "v2512",
        "native_solver": native_solver,
    }
    for key, expected in expected_values.items():
        if key in manifest and manifest[key] != expected:
            raise ValueError(f"existing run manifest conflicts with collected {key}")
    manifest.update(expected_values)
    manifest["native_source_evidence_path"] = str(evidence_path.resolve())
    manifest["native_source_evidence_sha256"] = _sha256_file(evidence_path)
    serialized = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if path.exists():
        temporary = path.with_name(f".{path.name}.tmp")
        if temporary.exists():
            raise FileExistsError(f"temporary run-manifest output already exists: {temporary}")
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, path)
    else:
        _atomic_write(path, serialized)


def collect_native_provenance(
    *,
    module_name: str,
    module_list_path: Path,
    output_path: Path,
    run_manifest_path: Path,
    env: Mapping[str, str] | None = None,
    executable_path: Path | None = None,
    architecture: str | None = None,
) -> dict[str, object]:
    runtime_env = dict(os.environ if env is None else env)
    evidence_path = output_path.resolve()
    manifest_path = run_manifest_path.resolve()
    if evidence_path == manifest_path:
        raise ValueError("source evidence and run manifest must use different paths")
    evidence, banner_bytes = _collect(
        module_name=module_name,
        module_list_path=module_list_path,
        env=runtime_env,
        executable_path=executable_path,
        architecture=architecture,
    )
    native_solver = evidence["native_solver"]
    assert isinstance(native_solver, dict)
    banner_path = evidence_path.with_name(f"{evidence_path.stem}.solver-banner.log")
    if evidence_path.exists() or banner_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing native evidence output: {evidence_path}"
        )
    native_solver["solver_banner_path"] = str(banner_path.resolve())
    _atomic_write(banner_path, banner_bytes.decode("utf-8", errors="replace"))
    _atomic_write(evidence_path, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    _merge_run_manifest(manifest_path, evidence, evidence_path)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-name", required=True, help="exact native OpenFOAM module name")
    parser.add_argument("--module-list", type=Path, required=True, help="captured module list")
    parser.add_argument(
        "--output", type=Path, required=True, help="new native source-evidence JSON"
    )
    parser.add_argument(
        "--run-manifest", type=Path, required=True, help="run manifest to bind to this runtime"
    )
    args = parser.parse_args()
    try:
        collect_native_provenance(
            module_name=args.module_name,
            module_list_path=args.module_list,
            output_path=args.output,
            run_manifest_path=args.run_manifest,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"native OpenFOAM provenance collection failed: {error}", file=sys.stderr)
        return 2
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
