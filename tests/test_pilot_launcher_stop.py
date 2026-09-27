"""Exercise live P1 hard stops without starting Docker or OpenFOAM."""

from __future__ import annotations

import io
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_restas_pilot as pilot  # noqa: E402


def _run_with_fake_docker(
    monkeypatch,
    tmp_path: Path,
    *,
    output: io.StringIO,
    stop_result: int = 0,
    kill_result: int = 0,
    wall_timeout_s: float | None = None,
    blocking_output: bool = False,
    stopped_exit_code: int = 143,
    completion_delay_s: float = 0.0,
    monitor_interval_s: float = 0.005,
) -> tuple[int, list[dict[str, str]], str | None, bool | None, str | None, list[str]]:
    container_stopped = threading.Event()
    docker_commands: list[list[str]] = []

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = output
            self.returncode: int | None = None

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            if completion_delay_s > 0:
                time.sleep(completion_delay_s)
            self.returncode = stopped_exit_code if container_stopped.is_set() else 0
            return self.returncode

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            container_stopped.set()
            self.returncode = 143

    class BlockingOutput:
        def __iter__(self):
            container_stopped.wait(timeout=2)
            return iter(())

    process = FakeProcess()
    if blocking_output:
        process.stdout = BlockingOutput()

    monkeypatch.setattr(pilot.subprocess, "Popen", lambda *args, **kwargs: process)

    def fake_run(command: list[str], *args, **kwargs) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        docker_commands.append(command)
        if command[1] == "stop":
            if stop_result == 0:
                container_stopped.set()
            return subprocess.CompletedProcess(command, stop_result, "container\n", "mock stop")
        if command[1] == "kill":
            if kill_result == 0:
                container_stopped.set()
            return subprocess.CompletedProcess(command, kill_result, "container\n", "mock kill")
        if command[1] == "stats":
            return subprocess.CompletedProcess(command, 0, "10GiB | 50% | 20%\n", "")
        raise AssertionError(f"unexpected subprocess command: {command}")

    monkeypatch.setattr(pilot.subprocess, "run", fake_run)
    case_dir = tmp_path / "case"
    run_dir = tmp_path / "run"
    case_dir.mkdir()
    run_dir.mkdir()
    result = pilot._run_container(
        case_dir,
        run_dir,
        "fake-p1-run",
        2,
        4,
        courant_limits=(0.5, 0.25),
        wall_timeout_s=wall_timeout_s,
        monitor_interval_s=monitor_interval_s,
    )
    return result


def test_live_courant_breach_requests_and_confirms_container_stop(
    monkeypatch, tmp_path: Path
) -> None:
    result = _run_with_fake_docker(
        monkeypatch,
        tmp_path,
        output=io.StringIO("Courant Number mean: 0.1 max: 0.5001\n"),
    )

    code, _samples, reason, confirmed, stop_error, _monitor_errors = result
    assert code == 143
    assert reason == "global Co 0.5001 exceeded 0.5"
    assert confirmed is True
    assert stop_error is None


def test_container_kill_is_used_when_graceful_stop_fails(monkeypatch, tmp_path: Path) -> None:
    result = _run_with_fake_docker(
        monkeypatch,
        tmp_path,
        output=io.StringIO("Courant Number mean: 0.1 max: 0.7\n"),
        stop_result=1,
        kill_result=0,
    )

    code, _samples, reason, confirmed, stop_error, _monitor_errors = result
    assert code == 143
    assert reason == "global Co 0.7 exceeded 0.5"
    assert confirmed is True
    assert stop_error is None


def test_wall_deadline_stops_a_blocked_solver_stream(monkeypatch, tmp_path: Path) -> None:
    result = _run_with_fake_docker(
        monkeypatch,
        tmp_path,
        output=io.StringIO(),
        wall_timeout_s=0.01,
        blocking_output=True,
    )

    code, _samples, reason, confirmed, stop_error, _monitor_errors = result
    assert code == 143
    assert reason == "wall-time limit of 0.01 s reached"
    assert confirmed is True
    assert stop_error is None


def test_failed_stop_and_kill_are_reported_and_fail_the_launcher(
    monkeypatch, tmp_path: Path
) -> None:
    result = _run_with_fake_docker(
        monkeypatch,
        tmp_path,
        output=io.StringIO("Interface Courant Number mean: 0.1 max: 0.3\n"),
        stop_result=1,
        kill_result=1,
    )

    code, _samples, reason, confirmed, stop_error, _monitor_errors = result
    assert code != 0
    assert reason == "interface Co 0.3 exceeded 0.25"
    assert confirmed is False
    assert stop_error is not None
    assert "docker stop returned 1" in stop_error
    assert "docker kill returned 1" in stop_error


def test_confirmed_hard_stop_cannot_return_a_success_exit_code(monkeypatch, tmp_path: Path) -> None:
    result = _run_with_fake_docker(
        monkeypatch,
        tmp_path,
        output=io.StringIO("Courant Number mean: 0.1 max: 0.5001\n"),
        stopped_exit_code=0,
    )

    code, _samples, reason, confirmed, stop_error, _monitor_errors = result
    assert code == 1
    assert reason == "global Co 0.5001 exceeded 0.5"
    assert confirmed is True
    assert stop_error is None


def test_wall_overrun_is_recorded_when_solver_finishes_between_monitor_polls(
    monkeypatch, tmp_path: Path
) -> None:
    result = _run_with_fake_docker(
        monkeypatch,
        tmp_path,
        output=io.StringIO(),
        wall_timeout_s=0.01,
        completion_delay_s=0.02,
        monitor_interval_s=0.1,
    )

    code, _samples, reason, confirmed, stop_error, _monitor_errors = result
    assert code == 124
    assert reason == "wall-time limit of 0.01 s reached before solver completion was observed"
    assert confirmed is False
    assert stop_error is None
