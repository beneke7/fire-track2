"""Artifact and parser checks for the exploratory Rouaix mesh-only runner."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_rouaix_mesh_probe as probe  # noqa: E402


def test_prepare_only_snapshots_inputs_and_leaves_original_case_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(probe, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(
        probe,
        "_resolve_image_id",
        lambda _run_dir: (_ for _ in ()).throw(AssertionError("prepare-only inspected Docker")),
    )
    original_hashes = {name: probe._sha256(path) for name, path in probe._source_paths().items()}

    assert probe.main(["--run-id", "prepare-snapshot", "--prepare-only"]) == 0

    run_dir = runs_root / "prepare-snapshot"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "prepared_only"
    assert manifest["source_inputs_sha256"] == original_hashes
    assert manifest["scope"]["geometry_classification"] == (
        "assumed analytic wall; not source-derived geometry"
    )
    for relative, expected_hash in original_hashes.items():
        assert probe._sha256(run_dir / "source-snapshot" / relative) == expected_hash
    for relative, expected_hash in original_hashes.items():
        if relative.startswith((f"{probe.PACKAGE_REL}/case/", f"{probe.PACKAGE_REL}/geometry/")):
            assert (
                probe._sha256(run_dir / relative.removeprefix(f"{probe.PACKAGE_REL}/"))
                == expected_hash
            )
        assert probe._sha256(probe.ROOT / relative) == expected_hash
    assert not (run_dir / "openfoam-console.log").exists()


def test_existing_run_id_is_never_overwritten(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(probe, "RUNS_ROOT", runs_root)
    assert probe.main(["--run-id", "immutable", "--prepare-only"]) == 0
    manifest_path = runs_root / "immutable" / "manifest.json"
    before = manifest_path.read_bytes()

    assert probe.main(["--run-id", "immutable", "--prepare-only"]) == 2
    assert manifest_path.read_bytes() == before


def test_image_setup_failure_and_timeout_are_preserved_in_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(probe, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(
        probe,
        "_resolve_image_id",
        lambda _run_dir: (_ for _ in ()).throw(RuntimeError("pinned image unavailable")),
    )
    assert probe.main(["--run-id", "setup-failure"]) == 2
    failed = json.loads((runs_root / "setup-failure" / "manifest.json").read_text())
    assert failed["status"] == "setup_failed"
    assert failed["setup_failure"] == "pinned image unavailable"
    assert failed["stages"]["blockMesh"]["exit_code"] is None

    monkeypatch.setattr(
        probe,
        "_resolve_image_id",
        lambda _run_dir: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(["docker", "image", "inspect"], 20)
        ),
    )
    assert probe.main(["--run-id", "setup-timeout"]) == 124
    timed_out = json.loads((runs_root / "setup-timeout" / "manifest.json").read_text())
    assert timed_out["status"] == "setup_timeout"
    assert timed_out["timeout"] is True
    assert "Docker image inspection timed out" in timed_out["setup_failure"]


def test_stage_count_and_patch_parsers_keep_mesh_diagnostics_separate(tmp_path: Path) -> None:
    log = """\
ROUAIX_OPENFOAM_SETUP_EXIT code=0
ROUAIX_STAGE_EXIT stage=blockMesh code=0
ROUAIX_STAGE_EXIT stage=topoSet code=0
ROUAIX_STAGE_EXIT stage=createPatch code=0
ROUAIX_STAGE_EXIT stage=snappyHexMesh code=0
points: 1200
faces: 3400
internal faces: 3000
cells: 900
Mesh OK.
ROUAIX_STAGE_EXIT stage=checkMesh code=0
"""
    stage_codes, setup_code = probe._parse_stage_results(log)
    assert setup_code == 0
    assert stage_codes == {
        "blockMesh": 0,
        "topoSet": 0,
        "createPatch": 0,
        "snappyHexMesh": 0,
        "checkMesh": 0,
    }
    assert probe._parse_mesh_counts(log) == {
        "points": 1200,
        "faces": 3400,
        "internal_faces": 3000,
        "cells": 900,
    }

    boundary = tmp_path / "boundary"
    boundary.write_text(
        """\
2
(
    nozzle
    {
        type patch;
        nFaces 24;
        startFace 100;
    }
    aircraftWall
    {
        type wall;
        nFaces 160;
        startFace 124;
    }
)
""",
        encoding="utf-8",
    )
    assert probe._parse_boundary_patches(boundary) == {
        "nozzle": {"n_faces": 24, "type": "patch"},
        "aircraftWall": {"n_faces": 160, "type": "wall"},
    }


def test_only_declared_mesh_utilities_are_in_the_runtime_sequence() -> None:
    assert [name for name, _command in probe.STAGES] == [
        "blockMesh",
        "topoSet",
        "createPatch",
        "snappyHexMesh",
        "checkMesh",
    ]
    assert probe.STAGES[2][1] == ("createPatch", "-overwrite")
    assert probe.STAGES[3][1] == ("snappyHexMesh", "-overwrite")
    assert probe.STAGES[4][1] == ("checkMesh", "-allTopology", "-allGeometry")
    assert "interIsoFoam" not in probe._shell_script()
    assert "decomposePar" not in probe._shell_script()


def test_openfoam_bashrc_is_sourced_before_strict_mode_and_failure_is_preserved(
    tmp_path: Path,
) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    unset_reference = tmp_path / "unset-reference.bashrc"
    unset_reference.write_text('printf "MOCK_UNSET=%s\\n" "$MOCK_UNSET_VALUE"\n', encoding="utf-8")
    setup = probe._openfoam_setup_script(str(unset_reference))
    success_then_strict_failure = subprocess.run(
        [bash, "-c", setup + '; printf "AFTER_SOURCE\\n"; printf "%s" "$STILL_UNSET"'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert success_then_strict_failure.returncode != 0
    assert "MOCK_UNSET=" in success_then_strict_failure.stdout
    assert "ROUAIX_OPENFOAM_SETUP_EXIT code=0" in success_then_strict_failure.stdout
    assert "AFTER_SOURCE" in success_then_strict_failure.stdout

    nonzero_source = tmp_path / "nonzero.bashrc"
    nonzero_source.write_text("return 19\n", encoding="utf-8")
    failure = subprocess.run(
        [
            bash,
            "-c",
            probe._openfoam_setup_script(str(nonzero_source)) + "; printf BAD_CONTINUATION",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert failure.returncode == 19
    assert "ROUAIX_OPENFOAM_SETUP_EXIT code=19" in failure.stdout
    assert "BAD_CONTINUATION" not in failure.stdout
