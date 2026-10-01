from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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


def _fake_run_local_supervisor(calls: list[list[str]]):
    def run_local(**kwargs):
        argv = [
            sys.executable,
            str(kwargs["repository_root"] / launcher.RUN_LOCAL_RELATIVE_PATH),
            "--gpu",
            "--threads",
            "2",
            "--source-supervisor",
            str(kwargs["config_path"]),
            "--",
            *kwargs["solver_argv"],
        ]
        calls.append(argv)
        kwargs["stdout_path"].write_bytes(b"mock run_local stdout\n")
        kwargs["stderr_path"].write_bytes(b"mock run_local stderr\n")
        return 0, argv

    return run_local


def test_signal_waits_for_detached_guardian_before_failed_bundle_inventory(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    (bundle / "metadata").mkdir(parents=True)
    (bundle / "logs").mkdir()
    lock_path = tmp_path / "guardian.lock"
    ready_path = tmp_path / "guardian-ready.json"
    release_path = tmp_path / "release-guardian"
    trace_path = tmp_path / "guardian-trace.txt"
    fake_run_local = tmp_path / "fake-run-local.py"
    fake_run_local.write_text(
        """\
import fcntl
import pathlib
import signal
import subprocess
import sys

lock, ready, release, trace = map(pathlib.Path, sys.argv[-4:])
guardian = r'''\
import fcntl
import pathlib
import signal
import sys
import time

lock, ready, release, trace = map(pathlib.Path, sys.argv[1:])
stream = lock.open('a+')
fcntl.flock(stream, fcntl.LOCK_EX)
ready.write_text('locked', encoding='ascii')
def record_signal(signum, frame):
    with trace.open('a', encoding='ascii') as output:
        output.write(f'signal:{signum}\\n')
signal.signal(signal.SIGTERM, record_signal)
signal.signal(signal.SIGINT, record_signal)
while not release.exists():
    with trace.open('a', encoding='ascii') as output:
        output.write('pulse\\n')
    time.sleep(0.02)
with trace.open('a', encoding='ascii') as output:
    output.write('guardian-finished\\n')
'''
child = subprocess.Popen(
    [sys.executable, '-c', guardian, *(str(path) for path in (lock, ready, release, trace))],
    start_new_session=True,
)
received = []
def forward(signum, frame):
    received.append(signum)
    child.send_signal(signum)
signal.signal(signal.SIGTERM, forward)
signal.signal(signal.SIGINT, forward)
child.wait()
raise SystemExit(128 + received[-1] if received else 0)
""",
        encoding="utf-8",
    )
    harness = tmp_path / "launch-harness.py"
    harness.write_text(
        """\
import json
import pathlib
import sys

root, fake, bundle, lock, ready, release, trace = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(root))
from scripts import prepare_flutas_dry_four as launcher
from scripts.finalize_flutas_dry_four import finalize_bundle

launcher.RUN_LOCAL_RELATIVE_PATH = fake
status, argv = launcher._run_local_supervisor(
    repository_root=root,
    config_path=root / 'unused-config.json',
    solver_argv=['--fake', str(lock), str(ready), str(release), str(trace)],
    stdout_path=bundle / 'logs/run-local.stdout.log',
    stderr_path=bundle / 'logs/run-local.stderr.log',
)
(bundle / 'metadata/launch-result.json').write_text(
    json.dumps({'state': 'SUPERVISED_LAUNCH_FINISHED', 'solver_exit_status': status}),
    encoding='utf-8',
)
result = finalize_bundle(bundle, repository_root=root)
print(json.dumps({'status': status, 'finalization': result}, sort_keys=True))
""",
        encoding="utf-8",
    )

    process = subprocess.Popen(
        [
            sys.executable,
            str(harness),
            str(ROOT),
            str(fake_run_local),
            str(bundle),
            str(lock_path),
            str(ready_path),
            str(release_path),
            str(trace_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not ready_path.exists():
            assert process.poll() is None, (
                "launch harness exited before its fake guardian held the lock"
            )
            time.sleep(0.02)
        assert ready_path.exists(), "fake detached guardian did not acquire its lock"
        os.kill(process.pid, signal.SIGTERM)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if trace_path.exists() and f"signal:{signal.SIGTERM}" in trace_path.read_text():
                break
            assert process.poll() is None, "launcher finalized before forwarded signal was observed"
            time.sleep(0.02)
        else:
            raise AssertionError("detached guardian did not receive the forwarded termination")

        before = trace_path.read_text(encoding="ascii").count("pulse\n")
        time.sleep(0.1)
        after = trace_path.read_text(encoding="ascii").count("pulse\n")
        assert after > before, "fake guardian must remain active after receiving termination"
        assert process.poll() is None, "launcher must wait for guardian-backed run_local completion"
        assert not (bundle / "SHA256SUMS").exists()
        assert not (bundle / "metadata/finalization-result.json").exists()
        with lock_path.open("a+") as lock_file:
            import fcntl

            with pytest.raises(BlockingIOError):
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

        release_path.touch()
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        result = json.loads(stdout.strip())
        assert result["status"] == 128 + signal.SIGTERM
        assert result["finalization"]["status"] == "failed"
        assert result["finalization"]["failure_stage"] == "launch_result"
        sums_path = bundle / "SHA256SUMS"
        sums_raw = sums_path.read_bytes()
        assert b"./metadata/finalization-result.json" in sums_raw
        entries = dict(
            line.decode("ascii").rstrip("\n").split("  ./", 1)[::-1]
            for line in sums_raw.splitlines()
        )
        for relative, digest in entries.items():
            assert hashlib.sha256((bundle / relative).read_bytes()).hexdigest() == digest
        stable_trace = hashlib.sha256(trace_path.read_bytes()).hexdigest()
        time.sleep(0.05)
        assert hashlib.sha256(trace_path.read_bytes()).hexdigest() == stable_trace
    finally:
        release_path.touch()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


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
    assert manifest["amendment"]["expected_sha256_pin_configured"] is True
    assert manifest["amendment"]["expected_sha256_pin"] == _sha256(
        ROOT / launcher.AMENDMENT_RELATIVE_PATH
    )
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
        "DISPOSITION_RELATIVE_PATH",
        Path("experiments/__missing_test_disposition__.json"),
    )
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
    monkeypatch.setattr(launcher, "_run_local_supervisor", _fake_run_local_supervisor(calls))
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
