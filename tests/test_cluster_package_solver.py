from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.cluster.package_solver import stage_bundle


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    _write(source / "interIsoFoam/Make/files", b"app.C\n")
    _write(source / "interIsoFoam/Make/options", b"EXE_INC =\n")
    _write(source / "interIsoFoam/interIsoFoam.C", b"int main() {}\n")
    _write(source / "interIsoFoam/traceNormalHeadPressureFvPatchScalarField.C", b"// BC\n")
    _write(source / "interIsoFoam/traceNormalHeadPressureFvPatchScalarField.H", b"// BC header\n")
    _write(source / "interIsoFoam/helper.H", b"// helper\n")
    _write(source / "interFoam/helper.H", b"// dependency include\n")
    _write(source / "interIsoFoam/Make/linux64GccDPInt32Opt/app.o", b"excluded build output")

    binary = _write(source / "bin-replay/interIsoFoamTracePair", b"reference binary")
    binary.chmod(0o755)
    evidence = tmp_path / "evidence"
    launch = {
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "container": "local",
    }
    _write(evidence / "launch-record.json", json.dumps(launch).encode())
    _write(evidence / "solver-source.diff", b"custom overlay")
    output = tmp_path / "staged"
    return source, binary, evidence, output


def test_stages_custom_solver_overlay_and_provenance_without_build_products(tmp_path: Path) -> None:
    source, binary, evidence, output = _fixture(tmp_path)
    manifest = stage_bundle(
        source_root=source,
        binary=binary,
        evidence_root=evidence,
        output=output,
        local_image_id="sha256:mock-image-id",
    )

    assert (
        manifest["solver_kind"] == "custom interIsoFoam-derived diagnostic; not stock interIsoFoam"
    )
    assert manifest["reference_binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert manifest["local_build_environment"]["container_image_id"] == "sha256:mock-image-id"
    assert (
        output / "solver-overlay/interIsoFoam/traceNormalHeadPressureFvPatchScalarField.C"
    ).is_file()
    assert (output / "solver-overlay/interFoam/helper.H").is_file()
    assert not (output / "solver-overlay/interIsoFoam/Make/linux64GccDPInt32Opt/app.o").exists()
    assert (output / "reference-build/interIsoFoamTracePair").stat().st_mode & 0o111
    build_notes = (output / "BUILD-ON-CLUSTER.md").read_text(encoding="utf-8")
    assert "not stock" in build_notes
    assert "assumed compatible with the cluster ABI" in build_notes


def test_rejects_binary_mismatch_and_existing_output(tmp_path: Path) -> None:
    source, binary, evidence, output = _fixture(tmp_path)
    binary.write_bytes(b"changed binary")
    with pytest.raises(ValueError, match="does not match launch-record"):
        stage_bundle(source_root=source, binary=binary, evidence_root=evidence, output=output)

    output.mkdir()
    with pytest.raises(ValueError, match="refusing to overwrite"):
        stage_bundle(source_root=source, binary=binary, evidence_root=evidence, output=output)


def test_site_wrapper_rechecks_actual_binary_and_source_tree(tmp_path: Path) -> None:
    source, binary, evidence, output = _fixture(tmp_path)
    manifest = stage_bundle(
        source_root=source, binary=binary, evidence_root=evidence, output=output
    )
    mock_bin = tmp_path / "mock-bin"
    _write(mock_bin / "foamVersion", b"#!/bin/sh\nprintf 'OpenFOAM-v2512\\n'\n").chmod(0o755)
    marker = tmp_path / "srun-called"
    _write(
        mock_bin / "srun",
        b"""#!/bin/sh
printf '%s\\n' "$*" > "$SRUN_MARKER"
""",
    ).chmod(0o755)
    adapter = _write(tmp_path / "stop-adapter", b"#!/bin/sh\nexit 0\n")
    adapter.chmod(0o755)
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    wrapper = Path(__file__).resolve().parents[1] / "scripts/cluster/site_wrapper_example.sh"
    args = [
        str(wrapper),
        "--profile",
        "smoke",
        "--case",
        str(case_dir),
        "--ranks",
        "1",
        "--cpus-per-task",
        "1",
        "--job-id",
        "job-1",
        "--solver-name",
        "custom",
        "--openfoam-version",
        "OpenFOAM-v2512",
        "--expected-binary-sha256",
        manifest["reference_binary_sha256"],
        "--expected-source-manifest-sha256",
        manifest["source_manifest_sha256"],
        "--runtime-strategy",
        "site-wrapper",
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{mock_bin}:{environment['PATH']}",
            "FIRETRACK2_SOLVER_BIN": str(output / "reference-build/interIsoFoamTracePair"),
            "FIRETRACK2_STAGING_MANIFEST": str(output / "staging-manifest.json"),
            "FIRETRACK2_SLURM_MPI_TYPE": "mock-plugin",
            "FIRETRACK2_CHECKPOINT_STOP_ADAPTER": str(adapter),
            "SLURM_NTASKS": "1",
            "SLURM_CPUS_PER_TASK": "1",
            "SRUN_MARKER": str(marker),
        }
    )
    subprocess.run(args, env=environment, check=True, capture_output=True, text=True)
    assert marker.is_file()

    marker.unlink()
    (output / "solver-overlay/interIsoFoam/helper.H").write_text("changed", encoding="utf-8")
    result = subprocess.run(args, env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert "staged solver source changed" in result.stderr
    assert not marker.exists()
