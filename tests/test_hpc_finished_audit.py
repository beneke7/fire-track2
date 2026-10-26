from __future__ import annotations

import gzip
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hpc_finished_audit.py"
SPEC = importlib.util.spec_from_file_location("hpc_finished_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDITOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDITOR
SPEC.loader.exec_module(AUDITOR)


def _job(source_root: str, job_id: str = "14651185", **extra: Any) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "source_root": source_root,
        "run_dir": f"rouaix-e1-hpc-pilot-{job_id}",
        "expected_ranks": 64,
        "horizon_s": 0.05,
        "delta_t_s": 0.001,
        "case_id": "S1-ORIG-64-01MS-005",
        **extra,
    }


def _manifest(source_root: str, job_id: str = "14651185", **extra: Any) -> dict[str, Any]:
    return {"jobs": [_job(source_root, job_id, **extra)]}


def _write_tar(
    path: Path, name: str, payload: bytes = b"x", member_type: bytes | None = None
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        if member_type is not None:
            member.type = member_type
            member.linkname = "../outside"
            archive.addfile(member)
        else:
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


def _accounting(job_id: str, state: str = "COMPLETED", cpu: str = "01:00:00") -> dict[str, Any]:
    return {
        "parent": {
            "job_id": job_id,
            "state": state,
            "exit_code": "0:0",
            "elapsed_raw": "00:01:00",
            "total_cpu": cpu,
            "allocated_cpus": "64",
            "max_rss": "1G",
        },
        "steps": [],
    }


def _sacct_persist_connection_refused(_job_id: str) -> dict[str, Any]:
    raise RuntimeError(
        "sacct exit 1: _open_persist_conn: failed to open persistent connection "
        "to host:localhost:6819: Connection refused"
    )


def _scontrol_parent_purged(_job_id: str) -> dict[str, Any]:
    raise RuntimeError("scontrol exit 1: Invalid job id specified")


def test_terminal_states_and_parent_step_accounting() -> None:
    for state in (
        "COMPLETED",
        "FAILED",
        "CANCELLED by 1234",
        "TIMEOUT",
        "OOM",
        "NODE_FAIL",
        "PREEMPTED",
        "BOOT_FAIL",
        "DEADLINE",
    ):
        assert AUDITOR.is_terminal_state(state)
    assert not AUDITOR.is_terminal_state("RUNNING")
    rows = AUDITOR.parse_sacct(
        "14651185|COMPLETED|0:0|00:02:00|01:59:00|64|1G|\n"
        "14651185.batch|COMPLETED|0:0|00:02:00|01:59:00|64|1G|\n"
        "14651185.0|COMPLETED|0:0|00:02:00|01:55:00|64|900M|\n",
        "14651185",
    )
    assert rows["parent"]["total_cpu"] == "01:59:00"
    assert [step["job_id"] for step in rows["steps"]] == ["14651185.batch", "14651185.0"]


def test_outcome_classification_keeps_solver_failure_and_exploratory_completion_distinct() -> None:
    assert AUDITOR.classify_result("FAILED", "failed", 1, False, False, True) == "slurm_failed"
    assert AUDITOR.classify_result("COMPLETED", "failed", 1, True, True, True) == (
        "solver_failed_or_missing_end_marker"
    )


def test_diagnostic_gaps_name_unavailable_evidence() -> None:
    missing = AUDITOR.diagnostic_gaps({}, {}, {"parent": {}, "steps": []})
    assert missing["ledger"]["status"] == "missing"
    assert missing["aggregate_memory"]["status"] == "not_aggregated"
    assert missing["tke_extrema"]["status"] == "not_exposed_by_current_parser"
    assert missing["native_profiling_interpretation"]["status"] == "not_captured"

    files = {"attempt/raw-profiling/container/time.json": Path("/unused")}
    present = AUDITOR.diagnostic_gaps(
        files,
        {"formal_validation_decision": None},
        {"parent": {"max_rss": "1G"}, "steps": [{"job_id": "7.0", "max_rss": "900M"}]},
    )
    assert present["native_profiling_interpretation"]["status"] == "raw_artifacts_uninterpreted"
    assert present["aggregate_memory"]["parent_max_rss"] == "1G"
    assert present["aggregate_memory"]["step_max_rss_rows"] == [
        {"job_id": "7.0", "max_rss": "900M"}
    ]
    assert AUDITOR.classify_result("COMPLETED", "completed", 0, True, True, True) == (
        "completed_horizon_converged_exploratory_only"
    )


def test_compact_validation_rejects_paths_links_limits_and_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("../outside", "/absolute", "attempt/../../outside"):
        original = tmp_path / "bad.tar.gz"
        _write_tar(original, name)
        with pytest.raises(ValueError, match="unsafe archive path"):
            AUDITOR.compact_archive(original, AUDITOR.sha256_file(original), None, tmp_path / "out")

    linked = tmp_path / "link.tar.gz"
    _write_tar(linked, "attempt/link", member_type=tarfile.SYMTYPE)
    with pytest.raises(ValueError, match="link or special"):
        AUDITOR.compact_archive(linked, AUDITOR.sha256_file(linked), None, tmp_path / "out")

    original = tmp_path / "selected.tar.gz"
    _write_tar(original, "attempt/solver.log", b"longer than limit")
    monkeypatch.setattr(AUDITOR, "MAX_FILE_BYTES", 4)
    with pytest.raises(ValueError, match="exceeds 512 MiB"):
        AUDITOR.compact_archive(original, AUDITOR.sha256_file(original), None, tmp_path / "out")
    with pytest.raises(ValueError, match="differs from run-state"):
        AUDITOR.compact_archive(original, "0" * 64, None, tmp_path / "out")


def test_compact_validation_rejects_selected_payload_hash_mismatch(tmp_path: Path) -> None:
    original = tmp_path / "source.tar.gz"
    _write_tar(original, "attempt/solver.log", b"solver output")
    archive_hash = AUDITOR.sha256_file(original)
    output = tmp_path / "capture"
    output.mkdir()
    selection = AUDITOR.compact_archive(original, archive_hash, None, output)
    selection["selected_files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="member hashes differ"):
        AUDITOR.verify_compact(output / "compact.tar.gz", selection, archive_hash)


def test_native_profiling_is_selected_only_at_known_summary_paths(tmp_path: Path) -> None:
    members = {
        "attempt/case/processors24/0.01/uniform/profiling": b"collated profile",
        "attempt/case/processors24/0.01/uniform/profiling.gz": b"compressed profile",
        "attempt/case/postProcessing/profiling/0.01/profiling": b"summary profile",
        "attempt/case/postProcessing/profiling/0.01/profiling.gz": b"compressed summary",
        "attempt/case/processors24/0.01/uniform/U": b"3D field payload",
        "attempt/case/processors24/0.01/uniform/profilingData": b"similar name",
        "attempt/case/postProcessing/profiling/0.01/U": b"postprocessing field",
    }
    archive_path = tmp_path / "profiling.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, payload in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))

    archive_hash = AUDITOR.sha256_file(archive_path)
    output = tmp_path / "capture"
    output.mkdir()
    selection = AUDITOR.compact_archive(archive_path, archive_hash, None, output)
    captured = {item["path"] for item in selection["selected_files"]}
    assert captured == {
        "attempt/case/processors24/0.01/uniform/profiling",
        "attempt/case/processors24/0.01/uniform/profiling.gz",
        "attempt/case/postProcessing/profiling/0.01/profiling",
        "attempt/case/postProcessing/profiling/0.01/profiling.gz",
    }
    AUDITOR.verify_compact(output / "compact.tar.gz", selection, archive_hash)


def test_manifest_rejects_traversal_and_unlisted_ids(tmp_path: Path) -> None:
    unsafe = _manifest(
        "/project/nk_meshapplied/bene/fire-track2-hpc/campaign", run_dir="../elsewhere"
    )
    with pytest.raises(ValueError, match="traverse"):
        AUDITOR.validate_manifest(unsafe)
    manifest = AUDITOR.validate_manifest(
        _manifest("/project/nk_meshapplied/bene/fire-track2-hpc/campaign")
    )
    assert manifest["jobs"][0]["job_id"] == "14651185"


def test_native_afterany_audits_real_s1_compact_data_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = ROOT / "results/summaries/rouaix_s1_64_20261026"
    fixture = ROOT / "tests/fixtures/rouaix_s1_audit"
    provenance = json.loads((fixture / "provenance.json").read_text(encoding="utf-8"))
    for item in provenance["files"]:
        assert AUDITOR.sha256_file(fixture / item["fixture_path"]) == item["sha256"]

    checksums = {
        item["path"]: item["sha256"]
        for item in json.loads((published / "files.sha256.json").read_text(encoding="utf-8"))
    }
    published_members = {
        "attempt/solver-convergence.json": "metrics/attempt/solver-convergence.json",
        "attempt/max-speed.csv": "metrics/attempt/max-speed.csv",
        "attempt/ledger/summary.json": "metrics/attempt/ledger/summary.json",
        "attempt/ledger/ledger.csv": "metrics/attempt/ledger/ledger.csv",
    }
    for relative in published_members.values():
        assert AUDITOR.sha256_file(published / relative) == checksums[relative]

    compressed_log = published / "solver.log.gz"
    assert AUDITOR.sha256_file(compressed_log) == checksums["solver.log.gz"]
    log_bytes = gzip.decompress(compressed_log.read_bytes())
    log_identity = json.loads((published / "solver-log-identity.json").read_text())
    assert len(log_bytes) == log_identity["uncompressed_bytes"]
    log_path = tmp_path / "solver.log"
    log_path.write_bytes(log_bytes)
    assert AUDITOR.sha256_file(log_path) == log_identity["uncompressed_sha256"]

    job_id = "14651180"
    campaign = tmp_path / "campaign"
    run_dir = campaign / f"rouaix-e1-hpc-pilot-{job_id}"
    run_dir.mkdir(parents=True)
    archive = run_dir / "result.tar.gz"
    with tarfile.open(archive, "w:gz", compresslevel=1) as stream:
        stream.add(log_path, arcname="attempt/solver.log", recursive=False)
        stream.add(fixture / "manifest.json", arcname="attempt/manifest.json", recursive=False)
        stream.add(
            fixture / "ledger-audit.log", arcname="attempt/ledger-audit.log", recursive=False
        )
        for archive_name, source_name in published_members.items():
            stream.add(published / source_name, arcname=archive_name, recursive=False)
        extra = tarfile.TarInfo("attempt/case/100/U")
        extra.size = 100
        stream.addfile(extra, io.BytesIO(b"x" * 100))
    archive_hash = AUDITOR.sha256_file(archive)
    (run_dir / "result.tar.gz.sha256").write_text(
        f"{archive_hash}  result.tar.gz\n", encoding="ascii"
    )
    state = json.loads((fixture / "run-state.json").read_text(encoding="utf-8"))
    state.update(
        {"job_id": job_id, "result_archive": str(archive), "result_archive_sha256": archive_hash}
    )
    (run_dir / "run-state.json").write_text(json.dumps(state), encoding="utf-8")

    attempt_manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    raw = _manifest(
        str(campaign),
        job_id,
        expected_ranks=64,
        horizon_s=0.05,
        delta_t_s=0.0001,
        case_id=attempt_manifest["case_id"],
    )
    manifest_path = tmp_path / "jobs.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(AUDITOR, "HOST_ROOTS", (str(tmp_path),))
    manifest = AUDITOR.validate_manifest(raw)
    monkeypatch.setattr(AUDITOR, "local_sacct", lambda _job: _accounting(job_id))
    output = tmp_path / "audit" / job_id

    assert AUDITOR.run_one(job_id, manifest, manifest_path, output) == 0
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    row = status["jobs"][job_id]
    assert row["phase"] == "captured"
    audit_path = Path(row["audit_path"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["metrics"]["classification"] == "completed_horizon_converged_exploratory_only"
    assert audit["metrics"]["expected_inputs_match"] is True
    assert audit["metrics"]["conservation"]["max_abs_cumulative_closure_residual_kg"] < 1e-9
    gaps = audit["metrics"]["diagnostic_gaps"]
    assert gaps["ledger"]["status"] == "raw_summary_captured"
    assert gaps["ledger"]["audit_log_present"] is True
    assert gaps["aggregate_memory"]["status"] == "not_aggregated"
    assert gaps["tke_extrema"]["status"] == "not_exposed_by_current_parser"
    assert gaps["native_profiling_interpretation"]["status"] == "not_captured"
    assert row["bundle_sha256"] == AUDITOR.sha256_file(Path(row["bundle_path"]))
    with tarfile.open(row["bundle_path"], "r:gz") as bundle:
        compact_data = bundle.extractfile("compact.tar.gz").read()
    with tarfile.open(fileobj=io.BytesIO(compact_data), mode="r:gz") as compact:
        names = {member.name for member in compact.getmembers()}
    assert "attempt/case/100/U" not in names
    assert "attempt/solver.log" in names
    assert "attempt/ledger-audit.log" in names
    first_versions = list((output / "jobs" / job_id).iterdir())
    assert AUDITOR.run_one(job_id, manifest, manifest_path, output) == 0
    assert list((output / "jobs" / job_id).iterdir()) == first_versions

    monkeypatch.setattr(AUDITOR, "local_sacct", _sacct_persist_connection_refused)
    monkeypatch.setattr(AUDITOR, "local_scontrol_parent", _scontrol_parent_purged)
    unknown_output = tmp_path / "audit-accounting-unavailable" / job_id
    assert AUDITOR.run_one(job_id, manifest, manifest_path, unknown_output) == 0
    unknown_row = json.loads((unknown_output / "status.json").read_text())["jobs"][job_id]
    assert unknown_row["phase"] == "captured"
    assert unknown_row["scheduler_accounting"]["status"] == "unavailable"
    assert (
        "localhost:6819: Connection refused" in unknown_row["scheduler_accounting"]["sacct_error"]
    )
    unknown_audit = json.loads(Path(unknown_row["audit_path"]).read_text())
    assert unknown_audit["metrics"]["classification"] == "scheduler_state_unavailable"
    assert unknown_audit["metrics"]["scheduler_state_available"] is False
    assert unknown_audit["metrics"]["slurm_state"] == "UNKNOWN"
    assert unknown_audit["metrics"]["cpu_accounting"]["parent"] is None
    assert unknown_audit["slurm"]["parent"] is None

    wrong_raw = _manifest(
        str(campaign),
        job_id,
        expected_ranks=63,
        horizon_s=0.05,
        delta_t_s=0.0001,
        case_id=attempt_manifest["case_id"],
    )
    wrong_manifest_path = tmp_path / "jobs-wrong-input.json"
    wrong_manifest_path.write_text(json.dumps(wrong_raw), encoding="utf-8")
    wrong_manifest = AUDITOR.validate_manifest(wrong_raw)
    wrong_output = tmp_path / "audit-wrong-input" / job_id
    assert AUDITOR.run_one(job_id, wrong_manifest, wrong_manifest_path, wrong_output) == 0
    wrong_row = json.loads((wrong_output / "status.json").read_text())["jobs"][job_id]
    wrong_audit = json.loads(Path(wrong_row["audit_path"]).read_text())
    assert wrong_audit["metrics"]["expected_inputs_match"] is False
    assert wrong_audit["metrics"]["classification"] == (
        "captured_attempt_inputs_differ_from_manifest"
    )

    def retained_scontrol_parent(_job_id: str) -> dict[str, Any]:
        accounting = _accounting(job_id)
        accounting["accounting_source"] = "scontrol"
        accounting["parent"]["total_cpu"] = "Unknown"
        accounting["parent"]["max_rss"] = "Unknown"
        return accounting

    monkeypatch.setattr(AUDITOR, "local_scontrol_parent", retained_scontrol_parent)
    scontrol_output = tmp_path / "audit-scontrol-fallback" / job_id
    assert AUDITOR.run_one(job_id, manifest, manifest_path, scontrol_output) == 0
    scontrol_row = json.loads((scontrol_output / "status.json").read_text())["jobs"][job_id]
    scontrol_audit = json.loads(Path(scontrol_row["audit_path"]).read_text())
    assert scontrol_row["scheduler_accounting"]["status"] == "partial"
    assert scontrol_audit["metrics"]["classification"] == (
        "completed_horizon_converged_exploratory_only"
    )
    assert scontrol_audit["slurm"]["parent"]["total_cpu"] == "Unknown"
    assert "CPU totals" in scontrol_audit["metrics"]["cpu_accounting"]["note"]

    monkeypatch.setattr(AUDITOR, "local_scontrol_parent", _scontrol_parent_purged)
    unknown_audit_path = Path(unknown_row["audit_path"])
    monkeypatch.setattr(AUDITOR, "local_sacct", lambda _job: _accounting(job_id))
    assert AUDITOR.run_one(job_id, manifest, manifest_path, unknown_output) == 0
    recovered_row = json.loads((unknown_output / "status.json").read_text())["jobs"][job_id]
    assert recovered_row["phase"] == "captured"
    assert recovered_row["audit_path"] != str(unknown_audit_path)
    recovered_audit = json.loads(Path(recovered_row["audit_path"]).read_text())
    assert recovered_audit["metrics"]["classification"] == (
        "completed_horizon_converged_exploratory_only"
    )
    assert recovered_audit["scheduler_accounting"]["status"] == "available"


def test_zero_cpu_cancel_and_missing_archive_are_not_solver_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    run_dir = campaign / "rouaix-e1-hpc-pilot-14651185"
    run_dir.mkdir(parents=True)
    output = tmp_path / "audits"
    raw = _manifest(str(campaign), slurm_output_path=str(tmp_path / "job-{job_id}.out"))
    Path(tmp_path / "job-14651185.out").write_text("bootstrap trace\n", encoding="utf-8")
    manifest_path = tmp_path / "jobs.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(AUDITOR, "HOST_ROOTS", (str(tmp_path),))
    manifest = AUDITOR.validate_manifest(raw)
    monkeypatch.setattr(
        AUDITOR,
        "local_sacct",
        lambda _job: _accounting("14651185", "CANCELLED by 1234", "00:00:00"),
    )
    assert AUDITOR.run_one("14651185", manifest, manifest_path, output) == 0
    record = json.loads((output / "status.json").read_text())["jobs"]["14651185"]
    assert record["classification"] == "cancelled_zero_cpu_no_archive"
    assert record["bootstrap_diagnostics"][0]["tail"] == ["bootstrap trace"]


def test_terminal_missing_artifact_is_reported_without_a_physical_failure_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    (campaign / "rouaix-e1-hpc-pilot-14651185").mkdir(parents=True)
    raw = _manifest(str(campaign))
    manifest_path = tmp_path / "jobs.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(AUDITOR, "HOST_ROOTS", (str(tmp_path),))
    manifest = AUDITOR.validate_manifest(raw)
    monkeypatch.setattr(AUDITOR, "local_sacct", lambda _job: _accounting("14651185"))
    assert AUDITOR.run_one("14651185", manifest, manifest_path, tmp_path / "audit") == 0
    record = json.loads((tmp_path / "audit/status.json").read_text())["jobs"]["14651185"]
    assert record["classification"] == "artifact_not_visible_afterany_start"
    assert "not a physical solver verdict" in record["reason"]


def test_unavailable_accounting_and_purged_parent_with_no_archive_is_not_zero_cpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    run_dir = campaign / "rouaix-e1-hpc-pilot-14651185"
    run_dir.mkdir(parents=True)
    raw = _manifest(str(campaign))
    manifest_path = tmp_path / "jobs.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(AUDITOR, "HOST_ROOTS", (str(tmp_path),))
    manifest = AUDITOR.validate_manifest(raw)
    monkeypatch.setattr(AUDITOR, "local_sacct", _sacct_persist_connection_refused)
    monkeypatch.setattr(AUDITOR, "local_scontrol_parent", _scontrol_parent_purged)

    output = tmp_path / "audit"
    assert AUDITOR.run_one("14651185", manifest, manifest_path, output) == 0
    record = json.loads((output / "status.json").read_text())["jobs"]["14651185"]
    assert record["phase"] == "inspected_no_archive"
    assert record["classification"] == "accounting_unavailable_no_archive"
    assert record["parent_cpu_seconds"] is None
    assert record["scheduler_state"] == "UNKNOWN"
    assert record["scheduler_accounting"]["status"] == "unavailable"
    assert record["sacct"]["parent"] is None
    assert "not a physical solver verdict" in record["reason"]

    def scontrol_completed_without_cpu(job_id: str) -> dict[str, Any]:
        accounting = _accounting(job_id)
        accounting["accounting_source"] = "scontrol"
        accounting["parent"]["total_cpu"] = "Unknown"
        accounting["parent"]["max_rss"] = "Unknown"
        return accounting

    monkeypatch.setattr(AUDITOR, "local_scontrol_parent", scontrol_completed_without_cpu)
    scontrol_output = tmp_path / "scontrol-audit"
    assert AUDITOR.run_one("14651185", manifest, manifest_path, scontrol_output) == 0
    scontrol_record = json.loads((scontrol_output / "status.json").read_text())["jobs"]["14651185"]
    assert scontrol_record["classification"] == "terminal_no_archive_cpu_unavailable"
    assert scontrol_record["parent_cpu_seconds"] is None
    assert scontrol_record["scheduler_accounting"]["source"] == "scontrol"


def test_sacct_queries_only_the_explicit_parent_job(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class Result:
        returncode = 0
        stdout = "14651185|COMPLETED|0:0|00:01:00|00:58:00|64|1G|\n"
        stderr = ""

    def fake_run(command: list[str], **kwargs: Any) -> Result:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return Result()

    monkeypatch.setattr(AUDITOR.subprocess, "run", fake_run)
    assert AUDITOR.local_sacct("14651185")["parent"]["state"] == "COMPLETED"
    assert "--jobs=14651185" in captured["command"]
    assert not any("--jobs=all" in argument for argument in captured["command"])
    assert captured["env"]["TZ"] == "UTC"


def test_scontrol_fallback_reads_state_without_fabricating_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Result:
        returncode = 0
        stdout = (
            "JobId=14651185 JobName=rouaix JobState=COMPLETED ExitCode=0:0 "
            "RunTime=00:39:32 NumCPUs=24 NodeList=x1000c0s4b1n1\n"
        )
        stderr = ""

    def fake_run(command: list[str], **kwargs: Any) -> Result:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return Result()

    monkeypatch.setattr(AUDITOR.subprocess, "run", fake_run)
    result = AUDITOR.local_scontrol_parent("14651185")
    assert result["parent"]["state"] == "COMPLETED"
    assert result["parent"]["total_cpu"] == "Unknown"
    assert result["parent"]["max_rss"] == "Unknown"
    assert result["accounting_source"] == "scontrol"
    assert captured["command"] == ["scontrol", "show", "job", "14651185", "--oneliner"]
    assert captured["env"]["TZ"] == "UTC"
