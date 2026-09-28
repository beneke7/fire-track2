from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import prepare_flutas_dry_four as launcher

ROOT = Path(__file__).resolve().parents[1]
REVIEW_MEMO_REL = Path("docs/reviews/FLUTAS_CANDIDATE6_BUILD_HOST_EXACT_REVIEW_20260928T1128Z.md")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _disposition(review_memo: Path) -> dict[str, str]:
    return {
        "decision": "ACCEPT_TO_LAUNCH",
        "review_status": "ACCEPT",
        "amendment_sha256": _sha256(ROOT / launcher.AMENDMENT_RELATIVE_PATH),
        "reviewer_memo_sha256": _sha256(review_memo),
        "reviewer": "gpt-6-astra/max",
        "scope": "dry_four_execution_telemetry_only",
    }


def _launch_documents() -> tuple[Path, Path, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix=".dry-four-launch-test-", dir=ROOT / "tests"))
    memo_path = temp_dir / "astra-review.md"
    memo_path.write_text("synthetic exact-hash reviewer memo for mocked launch\n", encoding="utf-8")
    disposition_path = temp_dir / "primary-disposition.json"
    disposition_path.write_text(
        json.dumps(_disposition(memo_path), sort_keys=True) + "\n", encoding="utf-8"
    )
    return temp_dir, disposition_path, memo_path


def _fake_subprocess_run(calls: list[list[str]]):
    def run(argv, **kwargs):
        command = [str(item) for item in argv]
        calls.append(command)
        if "--output" in command:
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "schema_version": "candidate6-dry-four-identity-verification-v1",
                        "solver_started": False,
                        "gpu_requested": False,
                        "local_docker_images": {
                            "candidate_image_id": launcher.PINNED_IMAGE_ID,
                            "builder_image_id": "sha256:" + "1" * 64,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout=b"identity fixture\n", stderr=b"")
        stdout = kwargs.get("stdout")
        stderr = kwargs.get("stderr")
        if stdout is not None:
            stdout.write(b"mock run_local stdout\n")
        if stderr is not None:
            stderr.write(b"mock run_local stderr\n")
        return SimpleNamespace(returncode=0)

    return run


def test_default_cli_only_prepares_and_stages_exact_readonly_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runs_root = tmp_path / "runs"

    def forbidden_process(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("preparation must not invoke the identity verifier or run_local")

    monkeypatch.setattr(launcher.subprocess, "run", forbidden_process)
    result = launcher.main(["--runs-root", str(runs_root), "--run-id", "prep-only-test"])
    assert result == 0
    bundle = Path(json.loads(capsys.readouterr().out)["bundle_root"])
    manifest = json.loads((bundle / "metadata" / "run-manifest.json").read_text())
    assert manifest["state"] == "PREPARED_ONLY_PROSPECTIVE"
    assert manifest["approval_gate"]["status"] == "PROSPECTIVE; NOT APPROVED TO LAUNCH"
    assert manifest["amendment"]["expected_sha256_pin_configured"] is False
    assert manifest["input_sha256"] == launcher.INPUTS
    assert not (bundle / "metadata" / "candidate6-identity.json").exists()
    assert not (bundle / launcher.ATTEMPT_CLAIM_NAME).exists()
    for name, digest in launcher.INPUTS.items():
        staged = bundle / "dry_four" / name
        assert _sha256(staged) == digest
        assert staged.stat().st_mode & 0o222 == 0
    assert (bundle / "dry_four").stat().st_mode & 0o222 == 0
    assert (bundle / "dry_four").name == "dry_four"
    assert (bundle / "metadata" / "host-snapshot.json").read_bytes() == (
        ROOT / "results" / "machine.json"
    ).read_bytes()
    layout_reference = json.loads((bundle / "metadata" / "oci-layout-reference.json").read_text())
    assert layout_reference["manifest_digest"] == launcher.PINNED_OCI_MANIFEST
    assert layout_reference["image_id"] == launcher.PINNED_IMAGE_ID


def test_launch_rejects_missing_or_wrong_disposition_without_external_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        launcher,
        "EXPECTED_AMENDMENT_SHA256",
        _sha256(ROOT / launcher.AMENDMENT_RELATIVE_PATH),
    )
    runs_root = tmp_path / "runs"
    calls: list[list[str]] = []
    monkeypatch.setattr(launcher.subprocess, "run", _fake_subprocess_run(calls))
    with pytest.raises(launcher.PreparationError, match="primary disposition JSON"):
        launcher.prepare_bundle(
            runs_root=runs_root,
            run_id="missing-disposition",
            review_memo_path=ROOT / REVIEW_MEMO_REL,
            launch=True,
        )
    assert calls == []
    assert not runs_root.exists()

    temp_dir, disposition_path, memo_path = _launch_documents()
    try:
        disposition = json.loads(disposition_path.read_text())
        disposition["review_status"] = "PENDING"
        disposition_path.write_text(json.dumps(disposition), encoding="utf-8")
        with pytest.raises(launcher.PreparationError, match="review_status.*ACCEPT"):
            launcher.prepare_bundle(
                runs_root=runs_root,
                run_id="pending-review",
                disposition_path=disposition_path,
                review_memo_path=memo_path,
                launch=True,
            )

        disposition["review_status"] = "ACCEPT"
        disposition["reviewer_memo_sha256"] = "0" * 64
        disposition_path.write_text(json.dumps(disposition), encoding="utf-8")
        with pytest.raises(launcher.PreparationError, match="review memo SHA-256 differs"):
            launcher.prepare_bundle(
                runs_root=runs_root,
                run_id="wrong-review-hash",
                disposition_path=disposition_path,
                review_memo_path=memo_path,
                launch=True,
            )

        disposition["reviewer_memo_sha256"] = _sha256(memo_path)
        disposition["amendment_sha256"] = "0" * 64
        disposition_path.write_text(json.dumps(disposition), encoding="utf-8")
        with pytest.raises(launcher.PreparationError, match="does not bind the pinned amendment"):
            launcher.prepare_bundle(
                runs_root=runs_root,
                run_id="wrong-disposition",
                disposition_path=disposition_path,
                review_memo_path=memo_path,
                launch=True,
            )
        assert calls == []
        assert not runs_root.exists()
    finally:
        shutil.rmtree(temp_dir)


def test_launch_stays_disabled_until_primary_pins_final_amendment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "EXPECTED_AMENDMENT_SHA256", None)
    with pytest.raises(launcher.PreparationError, match="launch is disabled until"):
        launcher.prepare_bundle(runs_root=tmp_path / "runs", run_id="un-pinned", launch=True)
    assert not (tmp_path / "runs").exists()


def test_accepted_mocked_launch_preserves_verifier_and_refuses_second_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        launcher,
        "EXPECTED_AMENDMENT_SHA256",
        _sha256(ROOT / launcher.AMENDMENT_RELATIVE_PATH),
    )
    runs_root = tmp_path / "runs"
    temp_dir, disposition_path, memo_path = _launch_documents()
    calls: list[list[str]] = []
    monkeypatch.setattr(launcher.subprocess, "run", _fake_subprocess_run(calls))
    try:
        result = launcher.prepare_bundle(
            runs_root=runs_root,
            run_id="single-launch-test",
            disposition_path=disposition_path,
            review_memo_path=memo_path,
            launch=True,
        )
        bundle = Path(result["bundle_root"])
        assert result["finalization"]["status"] == "failed"
        assert result["finalization"]["failure_stage"] == "checker"
        assert (bundle / "SHA256SUMS").is_file()
        assert not (bundle / "manifest.json").exists()
        config = json.loads((bundle / "metadata" / "source-supervisor.json").read_text())
        assert config["image"] == launcher.PINNED_IMAGE_ID
        assert config["gpu_index"] == "0"
        assert config["disk_roots"] == [str(bundle)]
        assert config["evidence_dir"] == str(bundle / "supervisor" / "evidence")
        assert "--entrypoint=mpirun" in config["container_options"]
        assert "--gpus=device=0" in config["container_options"]
        assert "--network=none" in config["container_options"]
        mounts = [
            option.removeprefix("--mount=")
            for option in config["container_options"]
            if option.startswith("--mount=")
        ]
        work_mount = f"type=bind,source={bundle / 'work'},target=/work"
        assert work_mount in mounts
        assert not work_mount.endswith(",readonly")
        assert (bundle / "work" / "data").is_dir()
        for name in launcher.INPUTS:
            expected_input_mount = (
                f"type=bind,source={bundle / 'dry_four' / name},target=/work/{name},readonly"
            )
            assert expected_input_mount in mounts
        assert not any(mount.endswith(",readonly") and "target=/work," in mount for mount in mounts)
        assert result["state"] == "SUPERVISED_LAUNCH_FINISHED"
        assert (bundle / "metadata" / "candidate6-identity.json").is_file()
        assert (bundle / "metadata" / "candidate-identity-command.json").is_file()
        assert (
            bundle / "logs" / "candidate-identity.stdout.log"
        ).read_bytes() == b"identity fixture\n"
        assert (bundle / "logs" / "run-local.stdout.log").read_bytes() == b"mock run_local stdout\n"
        assert (runs_root / launcher.ATTEMPT_CLAIM_NAME).is_file()
        assert calls[0][1].endswith("flutas_candidate6_identity.py")
        assert calls[0][calls[0].index("--archive") + 1] == str(
            ROOT / launcher.CANDIDATE_ROOT_RELATIVE_PATH / "docker-save.tar"
        )
        assert calls[1][1].endswith("run_local.py")
        assert calls[1][2:9] == [
            "--gpu",
            "--threads",
            "2",
            "--source-supervisor",
            str(bundle / "metadata" / "source-supervisor.json"),
            "--",
            "--oversubscribe",
        ]
        assert calls[1][-2:] == ["1", launcher.SOLVER_EXECUTABLE]

        with pytest.raises(
            launcher.PreparationError, match="one candidate6 attempt is already claimed"
        ):
            launcher.prepare_bundle(
                runs_root=runs_root,
                run_id="must-not-retry",
                disposition_path=disposition_path,
                review_memo_path=memo_path,
                launch=True,
            )
        assert len(calls) == 2
        assert not (runs_root / "flutas-dry-four-candidate6-must-not-retry").exists()
    finally:
        shutil.rmtree(temp_dir)


def test_identity_verifier_cli_accepts_the_required_archive_argument_without_docker(
    tmp_path: Path,
) -> None:
    argv = [
        sys.executable,
        str(ROOT / launcher.IDENTITY_VERIFIER_RELATIVE_PATH),
        "--candidate-root",
        str(tmp_path / "missing-candidate"),
        "--archive",
        str(tmp_path / "missing-candidate" / "docker-save.tar"),
        "--layout",
        str(tmp_path / "missing-candidate" / "layout"),
        "--repository-root",
        str(ROOT),
        "--executable",
        str(tmp_path / "missing-executable"),
        "--docker",
        "docker-must-not-be-called",
        "--output",
        str(tmp_path / "identity.json"),
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 2
    assert "candidate identity rejected:" in result.stderr
    assert "required: --archive" not in result.stderr


def test_existing_bundle_is_never_overwritten(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    first = launcher.prepare_bundle(runs_root=runs_root, run_id="refuse-existing")
    bundle = Path(first["bundle_root"])
    manifest_before = (bundle / "metadata" / "run-manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        launcher.prepare_bundle(runs_root=runs_root, run_id="refuse-existing")
    assert (bundle / "metadata" / "run-manifest.json").read_bytes() == manifest_before
