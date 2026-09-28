from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finalize_flutas_dry_four as finalizer  # noqa: E402


def _bundle(root: Path, *, solver_status: int = 0) -> Path:
    bundle = root / "dry-four-run"
    for relative in (
        "metadata",
        "analysis",
        "dry_four",
        "supervisor/evidence",
        "work/data",
    ):
        (bundle / relative).mkdir(parents=True, exist_ok=True)
    (bundle / "metadata/launch-result.json").write_text(
        json.dumps({"solver_exit_status": solver_status}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (bundle / "metadata/candidate-build.json").write_text("{}\n", encoding="utf-8")
    (bundle / "dry_four/dns.in").write_text("case input\n", encoding="ascii")
    (bundle / "supervisor/evidence/stdout.log").write_bytes(b"solver output\n")
    (bundle / "work/data/performance.out").write_text("performance\n", encoding="ascii")
    (bundle / "work/data/restas_timestep-inputs.json").write_text("{}\n", encoding="ascii")
    return bundle


def _write_fake_adapter_outputs(argv: list[str]) -> None:
    arguments = dict(zip(argv[::2], argv[1::2], strict=True))
    Path(arguments["--run-metadata-output"]).write_text('{"adapter":"ok"}\n', encoding="utf-8")
    Path(arguments["--output"]).write_text('{"manifest":"normal"}\n', encoding="utf-8")


def _assert_inventory(bundle: Path) -> None:
    sums_raw = (bundle / "SHA256SUMS").read_bytes()
    rows = sums_raw.decode("utf-8").splitlines()
    listed = [line.split("  ", 1)[1][2:] for line in rows]
    assert listed == sorted(listed)
    expected: list[str] = []
    for path in bundle.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(bundle).as_posix()
        info = path.lstat()
        if info.st_nlink != 1 or relative in {"SHA256SUMS", "metadata/SHA256SUMS.sha256"}:
            continue
        expected.append(relative)
    assert listed == sorted(expected)
    for row in rows:
        digest, relative = row.split("  ", 1)
        path = bundle / relative[2:]
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    sums_digest = hashlib.sha256(sums_raw).hexdigest()
    assert (bundle / "metadata/SHA256SUMS.sha256").read_text(encoding="ascii") == (
        f"{sums_digest}  SHA256SUMS\n"
    )


def _forbid_process(*_args, **_kwargs):
    raise AssertionError("finalization must not start an external process")


def test_pinned_manifest_adapter_entrypoint_loads_without_running_it() -> None:
    adapter = finalizer._load_adapter()

    assert callable(adapter.main)
    assert finalizer.SCHEMA_PATH.is_file()
    assert hashlib.sha256(finalizer.SCHEMA_PATH.read_bytes()).hexdigest() == (
        "4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492"
    )


def test_normal_finalization_checks_before_adapter_and_writes_sorted_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)
    events: list[str] = []
    report = {"status": "complete", "checker_evidence": {"sha256": "abc123"}}

    def check_bundle(actual_bundle: Path) -> dict[str, object]:
        assert actual_bundle == bundle
        events.append("checker")
        return report

    def invoke_adapter(argv: list[str], repository_root: Path = finalizer.REPO_ROOT) -> int:
        events.append("adapter")
        arguments = dict(zip(argv[::2], argv[1::2], strict=True))
        assert arguments["--schema"] == str(
            repository_root
            / "containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/reference/schema-v1.2.md"
        )
        assert arguments["--case-root"] == str(bundle / "dry_four")
        assert arguments["--run-dir"] == str(bundle)
        assert arguments["--candidate-build"] == str(bundle / "metadata/candidate-build.json")
        assert arguments["--analyzer"] == str(finalizer.ANALYZER_PATH)
        assert arguments["--supervisor-dir"] == str(bundle / "supervisor/evidence")
        assert arguments["--stdout"] == str(bundle / "supervisor/evidence/stdout.log")
        assert arguments["--performance-output"] == str(bundle / "work/data/performance.out")
        assert arguments["--timestep-inputs"] == str(
            bundle / "work/data/restas_timestep-inputs.json"
        )
        assert arguments["--run-metadata-output"] == str(
            bundle / "analysis/adapter-run-metadata.json"
        )
        assert arguments["--output"] == str(bundle / "manifest.json")
        annex = json.loads((bundle / "analysis/dry-output-annex.json").read_text())
        assert annex == report
        _write_fake_adapter_outputs(argv)
        return 0

    monkeypatch.setattr(finalizer.output_check, "check_bundle", check_bundle)
    monkeypatch.setattr(finalizer, "_invoke_adapter", invoke_adapter)
    monkeypatch.setattr(subprocess, "run", _forbid_process)
    monkeypatch.setattr(subprocess, "Popen", _forbid_process)

    result = finalizer.finalize_bundle(bundle)

    assert result["status"] == "complete"
    assert result["solver_exit_status"] == 0
    assert result["checker_status"] == "complete"
    assert result["adapter_status"] == 0
    assert result["manifest"] == "manifest.json"
    assert events == ["checker", "adapter"]
    assert json.loads((bundle / "analysis/dry-output-annex.json").read_text()) == report
    command = json.loads((bundle / "metadata/finalizer-command.json").read_text())
    assert command["command"] == ["in-process", "finalize_bundle", str(bundle)]
    assert command["adapter"]["call"] == "main(argv)"
    assert command["policy"]["external_solver_or_docker_started"] is False
    assert command["policy"]["gpu_accessed"] is False
    assert (bundle / "metadata/finalization-result.json").exists()
    _assert_inventory(bundle)


def test_solver_failure_is_recorded_without_checker_adapter_or_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path, solver_status=17)
    calls: list[str] = []
    monkeypatch.setattr(
        finalizer.output_check, "check_bundle", lambda _path: calls.append("checker")
    )
    monkeypatch.setattr(
        finalizer, "_invoke_adapter", lambda _argv, **_kwargs: calls.append("adapter")
    )

    result = finalizer.finalize_bundle(bundle)

    assert result["status"] == "failed"
    assert result["solver_exit_status"] == 17
    assert result["failure_stage"] == "launch_result"
    assert "solver exit status is 17" in result["error"]
    assert calls == []
    assert not (bundle / "manifest.json").exists()
    recorded = json.loads((bundle / "metadata/finalization-result.json").read_text())
    assert recorded == result
    _assert_inventory(bundle)


def test_checker_failure_is_recorded_and_adapter_is_never_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)
    events: list[str] = []

    def check_bundle(_path: Path) -> dict[str, object]:
        events.append("checker")
        raise ValueError("frozen output predicate failed")

    monkeypatch.setattr(finalizer.output_check, "check_bundle", check_bundle)
    monkeypatch.setattr(
        finalizer, "_invoke_adapter", lambda _argv, **_kwargs: events.append("adapter")
    )

    result = finalizer.finalize_bundle(bundle)

    assert result["status"] == "failed"
    assert result["failure_stage"] == "checker"
    assert "frozen output predicate failed" in result["error"]
    assert events == ["checker"]
    assert not (bundle / "manifest.json").exists()
    assert json.loads((bundle / "metadata/finalization-result.json").read_text()) == result
    _assert_inventory(bundle)


@pytest.mark.parametrize("adapter_outcome", [2, "raise"])
def test_adapter_rejection_removes_partial_manifest_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, adapter_outcome: int | str
) -> None:
    bundle = _bundle(tmp_path)
    monkeypatch.setattr(
        finalizer.output_check, "check_bundle", lambda _path: {"status": "complete"}
    )

    def invoke_adapter(argv: list[str], **_kwargs) -> int:
        _write_fake_adapter_outputs(argv)
        if adapter_outcome == "raise":
            raise RuntimeError("adapter rejected the bundle")
        return adapter_outcome

    monkeypatch.setattr(finalizer, "_invoke_adapter", invoke_adapter)

    result = finalizer.finalize_bundle(bundle)

    assert result["status"] == "failed"
    assert result["failure_stage"] == "adapter"
    assert not (bundle / "manifest.json").exists()
    assert json.loads((bundle / "metadata/finalization-result.json").read_text()) == result
    _assert_inventory(bundle)


def test_symlink_is_rejected_but_failure_inventory_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside bundle\n", encoding="utf-8")
    (bundle / "untrusted-link").symlink_to(outside)
    calls: list[str] = []
    monkeypatch.setattr(
        finalizer.output_check, "check_bundle", lambda _path: calls.append("checker")
    )
    monkeypatch.setattr(
        finalizer, "_invoke_adapter", lambda _argv, **_kwargs: calls.append("adapter")
    )

    result = finalizer.finalize_bundle(bundle)

    assert result["status"] == "failed"
    assert result["failure_stage"] == "filesystem_inventory"
    assert "symlink rejected: untrusted-link" in result["error"]
    assert calls == []
    assert not (bundle / "manifest.json").exists()
    assert (bundle / "SHA256SUMS").is_file()
    assert (bundle / "metadata/SHA256SUMS.sha256").is_file()
    assert "untrusted-link" not in (bundle / "SHA256SUMS").read_text(encoding="utf-8")
    assert json.loads((bundle / "metadata/finalization-result.json").read_text()) == result
    _assert_inventory(bundle)


def test_hardlinked_file_is_rejected_without_starting_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)
    external = tmp_path / "external.txt"
    external.write_text("shared inode\n", encoding="utf-8")
    os.link(external, bundle / "hardlinked.txt")
    monkeypatch.setattr(finalizer.output_check, "check_bundle", lambda _path: pytest.fail())
    monkeypatch.setattr(finalizer, "_invoke_adapter", lambda _argv, **_kwargs: pytest.fail())

    result = finalizer.finalize_bundle(bundle)

    assert result["status"] == "failed"
    assert "hardlink rejected: hardlinked.txt" in result["error"]
    assert (bundle / "SHA256SUMS").is_file()
    assert (bundle / "metadata/SHA256SUMS.sha256").is_file()
    _assert_inventory(bundle)
