#!/usr/bin/env python3
"""Replay or monitor Rouaix checkpoints with the schema-aware exact-row auditor."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
SOURCE_RUN = ROOT / "results/runs/rouaix-c4-continue-5s-20261007T153256Z-retry01"
CASE = SOURCE_RUN / "case"
DECLARATION = RUN / "case-declaration.json"
AUDITOR = RUN / "audit_checkpoint.py"
NAME = SOURCE_RUN.name
FIELDS = ("alpha.water", "U", "p_rgh", "k", "epsilon", "nut")
RANKS = sorted(CASE.glob("processor[0-9]*"), key=lambda p: int(p.name.removeprefix("processor")))
AUDIT_ROOT = RUN / "checkpoint-audits"
INDEX = AUDIT_ROOT / "index.jsonl"


def numerical_times(rank: Path) -> set[str]:
    return {
        path.name
        for path in rank.iterdir()
        if path.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", path.name)
    }


def signature(time_name: str) -> tuple[tuple[str, int, int], ...] | None:
    parts = []
    if len(RANKS) != 16:
        return None
    for rank in RANKS:
        folder = rank / time_name
        uniform_time = folder / "uniform/time"
        required = [folder / name for name in FIELDS]
        if not uniform_time.is_file() or any(
            not path.is_file() or path.stat().st_size == 0 for path in required
        ):
            return None
        for path in [uniform_time, *required]:
            info = path.stat()
            parts.append((str(path.relative_to(CASE)), info.st_size, info.st_mtime_ns))
    return tuple(parts)


def container_running() -> bool | None:
    cidfile = SOURCE_RUN / "flow.cid"
    if not cidfile.is_file():
        return None
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", NAME],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    return result.stdout.strip().lower() == "true"


def append_record(record: dict[str, object]) -> None:
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    with INDEX.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def audit_one_checkpoint(
    time_name: str, attempt: int
) -> tuple[dict[str, object] | None, str | None]:
    stamp = time_name.replace(".", "p")
    out = AUDIT_ROOT / f"{stamp}-attempt{attempt}"
    out.mkdir(parents=True, exist_ok=False)
    declaration_copy = out / "case-declaration.json"
    shutil.copy2(DECLARATION, declaration_copy)
    env = os.environ.copy()
    for name in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        env[name] = "1"
    command = [
        str(ROOT / ".venv/bin/python"),
        str(AUDITOR),
        "--case",
        str(CASE),
        "--declaration",
        str(declaration_copy),
        "--through-time",
        time_name,
        "--output-dir",
        str(out),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "native ledger audit exceeded 600 s"
    (out / "audit.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (out / "audit.stderr.txt").write_text(result.stderr, encoding="utf-8")
    report_path = out / "ledger-report.json"
    if result.returncode or not report_path.is_file():
        return None, f"audit exit {result.returncode}; see {out.relative_to(RUN)}"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cumulative = report["cumulative_ledger_from_t0"]
    incremental = report["incremental_ledger_from_checkpoint"]
    cumulative_fraction = abs(float(cumulative["residual_fraction_of_total_source"]))
    incremental_fraction = abs(float(incremental["residual_fraction_of_incremental_source"]))
    summary: dict[str, object] = {
        "checkpoint_directory_time_s": float(time_name),
        "ledger_last_time_s": float(report["actual_final_time_s"]),
        "ledger_rows": int(report["rows"]),
        "cumulative_residual_kg": float(cumulative["residual_expected_minus_observed_kg"]),
        "cumulative_residual_fraction": cumulative_fraction,
        "incremental_residual_kg": float(incremental["residual_expected_minus_observed_kg"]),
        "incremental_residual_fraction": incremental_fraction,
        "cumulative_guard_pass": cumulative_fraction <= 0.001,
        "incremental_guard_pass": incremental_fraction <= 0.001,
        "report": str(report_path.relative_to(RUN)),
    }
    return summary, None


def stop_container(reason: str) -> None:
    (RUN / "checkpoint-guard-failure.txt").write_text(reason + "\n", encoding="utf-8")
    subprocess.run(
        ["docker", "stop", "--time", "60", NAME], cwd=ROOT, check=False, capture_output=True
    )


def replay_one_checkpoint(time_name: str) -> int:
    if signature(time_name) is None:
        print(f"checkpoint fields are incomplete at t={time_name}", file=sys.stderr)
        return 2
    stamp = time_name.replace(".", "p")
    attempt = 1
    while (AUDIT_ROOT / f"{stamp}-attempt{attempt}").exists():
        attempt += 1
    summary, error = audit_one_checkpoint(time_name, attempt)
    if error:
        append_record(
            {
                "utc": datetime.now(UTC).isoformat(),
                "checkpoint_directory_time_s": float(time_name),
                "status": "replay_failure",
                "attempt": attempt,
                "error": error,
            }
        )
        print(error, file=sys.stderr)
        return 2
    assert summary is not None
    passed = bool(summary["cumulative_guard_pass"] and summary["incremental_guard_pass"])
    append_record(
        {
            "utc": datetime.now(UTC).isoformat(),
            "status": "replay_pass" if passed else "replay_guard_failure",
            "attempt": attempt,
            **summary,
        }
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if passed else 3


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--audit-checkpoint":
        return replay_one_checkpoint(sys.argv[2])
    if len(RANKS) != 16:
        print(f"expected 16 processor directories, got {len(RANKS)}", file=sys.stderr)
        return 2
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    last_audited = float(declaration["checkpoint"]["time_s"])
    stable: dict[str, tuple[tuple[tuple[str, int, int], ...], float]] = {}
    failed_audits: dict[str, int] = {}
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    while True:
        common = set.intersection(*(numerical_times(rank) for rank in RANKS))
        candidates = sorted(
            (name for name in common if float(name) > last_audited + 1e-10), key=float
        )
        ready = None
        now = time.monotonic()
        for candidate in candidates:
            current = signature(candidate)
            if current is None:
                continue
            old = stable.get(candidate)
            if old is None or old[0] != current:
                stable[candidate] = (current, now)
            elif now - old[1] >= 30.0:
                ready = candidate
                break
        if ready is not None:
            audit_attempt = failed_audits.get(ready, 0) + 1
            summary, error = audit_one_checkpoint(ready, audit_attempt)
            if error is not None:
                failed_audits[ready] = audit_attempt
                append_record(
                    {
                        "utc": datetime.now(UTC).isoformat(),
                        "checkpoint_directory_time_s": float(ready),
                        "status": "retry",
                        "attempt": audit_attempt,
                        "error": error,
                    }
                )
                if audit_attempt >= 3:
                    stop_container(
                        f"Could not complete the checkpoint ledger audit after three attempts at t={ready}: {error}"
                    )
                    return 2
                time.sleep(15)
                continue
            assert summary is not None
            passed = bool(summary["cumulative_guard_pass"] and summary["incremental_guard_pass"])
            append_record(
                {
                    "utc": datetime.now(UTC).isoformat(),
                    "status": "pass" if passed else "guard_failure",
                    "attempt": audit_attempt,
                    **summary,
                }
            )
            if not passed:
                stop_container(
                    f"0.1% phase ledger guard failed at t={summary['ledger_last_time_s']}: {summary}"
                )
                return 3
            last_audited = float(summary["ledger_last_time_s"])
            stable.clear()
            continue
        state = container_running()
        if state is False:
            if candidates:
                candidate = candidates[0]
                if signature(candidate) is not None:
                    summary, error = audit_one_checkpoint(candidate, 1)
                    if error is None and summary is not None:
                        passed = bool(
                            summary["cumulative_guard_pass"] and summary["incremental_guard_pass"]
                        )
                        append_record(
                            {
                                "utc": datetime.now(UTC).isoformat(),
                                "status": "final_pass" if passed else "final_guard_failure",
                                **summary,
                            }
                        )
            append_record({"utc": datetime.now(UTC).isoformat(), "status": "container_exited"})
            return 0
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
