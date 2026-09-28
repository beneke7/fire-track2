from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flutas_source_supervisor as supervisor  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.overshoot_next_sleep = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds + self.overshoot_next_sleep
        self.overshoot_next_sleep = 0.0


def _result(*argv: str, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return supervisor.CommandResult(tuple(argv), returncode, stdout, stderr)


class FakeEngine:
    def __init__(self, *, stop_mode: str = "graceful", exit_code: int = 0) -> None:
        self.stop_mode = stop_mode
        self.exit_code = exit_code
        self.created = False
        self.removed = False
        self.running = False
        self.child_alive = False
        self.docker_cli_alive = False
        self.started = threading.Event()
        self.state_stopped = threading.Event()
        self.container_exit = threading.Event()
        self.child_exit = threading.Event()
        self.inspect_errors = 0
        self.inspect_count = 0
        self.stop_requests = 0
        self.kill_requests = 0
        self.forced_children = 0
        self.last_limits: supervisor.Limits | None = None
        self.log_driver = "none"
        self._stop_finished = False
        self._kill_finished = False

    def create(self, config, command, limits):
        del command
        self.created = True
        self.removed = False
        self.last_limits = limits
        return "fake-container-id"

    def request_start(self, container_id, stdout_path, stderr_path):
        assert container_id == "fake-container-id"
        del stdout_path, stderr_path
        self.running = True
        self.state_stopped.clear()
        self.started.set()
        self._attached_finished = False
        return self._pending("start")

    def poll_start(self, pending):
        del pending
        if self.running or self._attached_finished:
            return None
        self._attached_finished = True
        return _result("docker", "start", "--attach", "fake-container-id")

    def inspect(self, container_id: str) -> Mapping[str, Any]:
        self.inspect_count += 1
        if self.inspect_errors:
            self.inspect_errors -= 1
            raise RuntimeError("fake inspect transport error")
        if not self.created or self.removed:
            raise supervisor.ContainerNotFound("fake container absent")
        if self.container_exit.is_set():
            self.running = False
        if not self.running:
            self.state_stopped.set()
        return {
            "Id": container_id,
            "State": {
                "Running": self.running,
                "Pid": 4242 if self.running else 0,
                "ExitCode": self.exit_code,
            },
            "HostConfig": {
                "NanoCpus": 2_000_000_000,
                "Memory": supervisor.H7_LIMITS.memory_bytes,
                "MemorySwap": supervisor.H7_LIMITS.memory_bytes,
                "LogConfig": {"Type": self.log_driver},
            },
        }

    def _pending(self, operation: str) -> supervisor.PendingDockerCommand:
        return supervisor.PendingDockerCommand(
            process=None,  # The fake engine owns completion in its poll method.
            argv=("docker", operation, "fake-container-id"),
            process_group=None,
        )

    def request_stop(self, container_id: str, grace_seconds: float):
        assert container_id == "fake-container-id"
        assert grace_seconds == supervisor.H7_LIMITS.graceful_seconds
        self.stop_requests += 1
        self.docker_cli_alive = True
        self._stop_finished = False
        if self.stop_mode == "graceful":
            self.running = False
        return self._pending("stop")

    def poll_stop(self, pending):
        del pending
        if self.stop_mode == "stuck" and self.docker_cli_alive:
            return None
        if not self._stop_finished:
            self._stop_finished = True
            self.docker_cli_alive = False
            return _result("docker", "stop", "fake-container-id")
        return None

    def request_kill(self, container_id: str):
        assert container_id == "fake-container-id"
        self.kill_requests += 1
        self.docker_cli_alive = True
        self._kill_finished = False
        self.running = False
        return self._pending("kill")

    def poll_kill(self, pending):
        del pending
        if not self._kill_finished:
            self._kill_finished = True
            self.docker_cli_alive = False
            return _result("docker", "kill", "fake-container-id")
        return None

    def remove(self, container_id: str):
        del container_id
        self.removed = True
        return _result("docker", "rm", "fake-container-id")

    def has_surviving_children(self) -> bool:
        if self.child_exit.is_set():
            self.child_alive = False
        return self.child_alive or self.docker_cli_alive

    def force_kill_children(self) -> None:
        self.forced_children += 1
        self.child_alive = False
        self.docker_cli_alive = False


class FakeSampler:
    def __init__(
        self,
        engine: FakeEngine,
        clock,
        *,
        failure: str | None = None,
        complete_after_running_sample: bool = False,
        gpu_used: int = 0,
        disk_used: int = 0,
        log_bytes: int = 0,
        event_bytes: int = 0,
    ) -> None:
        self.engine = engine
        self.clock = clock
        self.failure = failure
        self.complete_after_running_sample = complete_after_running_sample
        self.gpu_used = gpu_used
        self.disk_used = disk_used
        self.log_bytes = log_bytes
        self.event_bytes = event_bytes
        self.running_samples = 0

    def sample(self, container_id, inspection, stage) -> dict[str, Any]:
        del container_id
        if self.failure and stage == "solver_running":
            if self.failure == "exception":
                raise RuntimeError("fake sampler unavailable")
            sample = self._valid(inspection, stage)
            if self.failure == "missing":
                sample.pop("gpu_utilization_percent")
            elif self.failure == "nan":
                sample["gpu_memory_used_bytes"] = float("nan")
            elif self.failure == "gap":
                # The fake scheduler injects a gap before this sample starts.
                pass
            return sample
        sample = self._valid(inspection, stage)
        if stage == "solver_running":
            self.running_samples += 1
            if self.engine.container_exit.is_set():
                self.engine.running = False
            elif self.complete_after_running_sample:
                self.engine.running = False
        return sample

    def _valid(self, inspection, stage) -> dict[str, Any]:
        state = inspection.get("State", {}) if inspection else {}
        running_phase = stage == "solver_running"
        return {
            "process_cpu_seconds": 0.0,
            "process_rss_bytes": 0,
            "cgroup_cpu_percent": 0.0,
            "cgroup_cpu_usage_usec": 0,
            "cgroup_cpu_sample_interval_seconds": 0.0,
            "cgroup_memory_bytes": 0,
            "cgroup_memory_limit_bytes": supervisor.H7_LIMITS.memory_bytes,
            "gpu_device_index": "0",
            "gpu_memory_used_bytes": self.gpu_used if running_phase else 0,
            "gpu_utilization_percent": 0.0,
            "disk_used_bytes": self.disk_used if running_phase else 0,
            "stdout_bytes": self.log_bytes if running_phase else 0,
            "stderr_bytes": 0,
            "combined_stdout_stderr_bytes": self.log_bytes if running_phase else 0,
            "supervisor_event_bytes": self.event_bytes if running_phase else 0,
            "solver_stage": stage,
            "container_running": bool(state.get("Running", False)),
            "container_state": dict(state),
            "sample_duration_seconds": 0.0,
        }


def _config(tmp_path: Path, *, name: str = "fake-flutas-test") -> supervisor.RunConfig:
    disk = tmp_path / "disk"
    disk.mkdir(exist_ok=True)
    stage = tmp_path / "stage.txt"
    return supervisor.RunConfig(
        image="flutas-fake:locked",
        name=name,
        container_options=("--gpus", "all"),
        evidence_dir=tmp_path / "evidence",
        disk_roots=(disk,),
        stage_file=stage,
        stage_file_container="/run/h7-stage.txt",
    )


def _run_fake(
    tmp_path: Path,
    *,
    engine: FakeEngine | None = None,
    sampler: FakeSampler | None = None,
    clock: FakeClock | None = None,
    limits: supervisor.Limits = supervisor.H7_LIMITS,
) -> tuple[int, FakeEngine, FakeClock]:
    fake_clock = clock or FakeClock()
    fake_engine = engine or FakeEngine()
    fake_sampler = sampler or FakeSampler(fake_engine, fake_clock)
    instance = supervisor.SourceSupervisor(
        _config(tmp_path),
        ["fake-solver", "--case", "dry_four"],
        limits=limits,
        engine=fake_engine,
        sampler=fake_sampler,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )
    return instance.run(), fake_engine, fake_clock


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (path / "supervision.jsonl").read_text().splitlines()]


def _write_fake_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _install_fake_sampler_sitecustomize(directory: Path, environment: dict[str, str]) -> None:
    source = r"""import pathlib
import flutas_source_supervisor as module

class FakeSystemSampler:
    def __init__(self, config, *args, **kwargs):
        self.config = config

    def sample(self, container_id, inspection, stage):
        del container_id
        state = inspection.get("State", {}) if inspection else {}
        evidence = self.config.evidence_dir
        stdout = evidence / "stdout.log"
        stderr = evidence / "stderr.log"
        events = evidence / "supervision.jsonl"
        stdout_bytes = stdout.stat().st_size if stdout.exists() else 0
        stderr_bytes = stderr.stat().st_size if stderr.exists() else 0
        return {
            "process_cpu_seconds": 0.0,
            "process_rss_bytes": 0,
            "cgroup_cpu_percent": 0.0,
            "cgroup_cpu_usage_usec": 0,
            "cgroup_cpu_sample_interval_seconds": 0.0,
            "cgroup_v2_path": None,
            "cgroup_memory_bytes": 0,
            "cgroup_memory_limit_bytes": module.H7_LIMITS.memory_bytes,
            "gpu_device_index": self.config.gpu_index,
            "gpu_memory_used_bytes": 0,
            "gpu_utilization_percent": 0.0,
            "disk_used_bytes": 0,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "combined_stdout_stderr_bytes": stdout_bytes + stderr_bytes,
            "supervisor_event_bytes": events.stat().st_size if events.exists() else 0,
            "solver_stage": stage,
            "container_running": bool(state.get("Running", False)),
            "container_state": dict(state),
            "sample_duration_seconds": 0.0,
        }

module.SystemSampler = FakeSystemSampler
"""
    sitecustomize = directory / "sitecustomize.py"
    sitecustomize.write_text(source, encoding="utf-8")
    current = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(directory), str(SCRIPTS), current) if item
    )


def _cgroup_v2_fixture(
    tmp_path: Path,
    *,
    pid: int = 4242,
    membership_path: str = "/docker/test-container",
    usage_usec: int = 1_000_000,
    memory_current: int = 4096,
    memory_max: int = 16 * supervisor.GIB,
) -> tuple[Path, Path, Path]:
    proc_root = tmp_path / "proc"
    cgroup_root = tmp_path / "cgroup"
    proc_dir = proc_root / str(pid)
    proc_dir.mkdir(parents=True)
    cgroup_root.mkdir()
    (cgroup_root / "cgroup.controllers").write_text("cpu memory\n", encoding="ascii")
    (proc_dir / "cgroup").write_text(f"0::{membership_path}\n", encoding="ascii")
    components = [] if membership_path == "/" else membership_path.lstrip("/").split("/")
    cgroup_dir = cgroup_root.joinpath(*components)
    cgroup_dir.mkdir(parents=True)
    (cgroup_dir / "cpu.stat").write_text(
        f"usage_usec {usage_usec}\nuser_usec {usage_usec}\nsystem_usec 0\n", encoding="ascii"
    )
    (cgroup_dir / "memory.current").write_text(f"{memory_current}\n", encoding="ascii")
    (cgroup_dir / "memory.max").write_text(f"{memory_max}\n", encoding="ascii")
    return proc_root, cgroup_root, cgroup_dir


def test_cgroup_v2_metrics_parse_current_and_limit(tmp_path: Path) -> None:
    proc_root, cgroup_root, cgroup_dir = _cgroup_v2_fixture(tmp_path)

    metrics = supervisor._read_cgroup_v2_metrics(4242, proc_root=proc_root, cgroup_root=cgroup_root)

    assert metrics.path == cgroup_dir.resolve()
    assert metrics.cpu_usage_usec == 1_000_000
    assert metrics.memory_current_bytes == 4096
    assert metrics.memory_max_bytes == 16 * supervisor.GIB


def test_deterministic_data_budget_matches_reviewed_dry_output_map() -> None:
    assert supervisor.DETERMINISTIC_DATA_FILE_COUNT == 37
    assert supervisor.DETERMINISTIC_DATA_BYTES == 57_447_891


def test_cgroup_v1_membership_fails_closed_with_explicit_reason(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    cgroup_root = tmp_path / "cgroup"
    proc_dir = proc_root / "4321"
    proc_dir.mkdir(parents=True)
    cgroup_root.mkdir()
    (proc_dir / "cgroup").write_text("12:cpu,memory:/docker/test\n", encoding="ascii")
    (cgroup_root / "cgroup.controllers").write_text("cpu memory\n", encoding="ascii")

    with pytest.raises(RuntimeError, match="cgroup v2 unified membership is unavailable"):
        supervisor._read_cgroup_v2_metrics(4321, proc_root=proc_root, cgroup_root=cgroup_root)


@pytest.mark.parametrize("membership_text", ["broken\n", "0::/docker/test\nbroken\n"])
def test_malformed_proc_cgroup_membership_fails_closed(
    tmp_path: Path, membership_text: str
) -> None:
    proc_root = tmp_path / "proc"
    cgroup_root = tmp_path / "cgroup"
    proc_dir = proc_root / "4242"
    proc_dir.mkdir(parents=True)
    cgroup_root.mkdir()
    (proc_dir / "cgroup").write_text(membership_text, encoding="ascii")
    (cgroup_root / "cgroup.controllers").write_text("cpu memory\n", encoding="ascii")

    with pytest.raises(ValueError, match="malformed /proc/4242/cgroup membership row"):
        supervisor._read_cgroup_v2_metrics(4242, proc_root=proc_root, cgroup_root=cgroup_root)


@pytest.mark.parametrize("missing", ["cpu.stat", "memory.current", "memory.max"])
def test_missing_cgroup_v2_file_fails_closed(tmp_path: Path, missing: str) -> None:
    proc_root, cgroup_root, cgroup_dir = _cgroup_v2_fixture(tmp_path)
    (cgroup_dir / missing).unlink()

    with pytest.raises(RuntimeError, match="missing or unsafe"):
        supervisor._read_cgroup_v2_metrics(4242, proc_root=proc_root, cgroup_root=cgroup_root)


def test_cgroup_v2_rejects_malformed_counters_and_path_escape(tmp_path: Path) -> None:
    proc_root, cgroup_root, cgroup_dir = _cgroup_v2_fixture(tmp_path)
    (cgroup_dir / "cpu.stat").write_text("usage_usec nan\n", encoding="ascii")
    with pytest.raises(ValueError, match="malformed cgroup v2 cpu.stat"):
        supervisor._read_cgroup_v2_metrics(4242, proc_root=proc_root, cgroup_root=cgroup_root)

    outside = tmp_path / "outside"
    outside.mkdir()
    escaped_root = tmp_path / "escaped-cgroup"
    escaped_root.mkdir()
    (escaped_root / "cgroup.controllers").write_text("cpu memory\n", encoding="ascii")
    (escaped_root / "escape").symlink_to(outside, target_is_directory=True)
    (proc_root / "4242" / "cgroup").write_text("0::/escape\n", encoding="ascii")
    with pytest.raises(RuntimeError, match="contains a symlink"):
        supervisor._read_cgroup_v2_metrics(4242, proc_root=proc_root, cgroup_root=escaped_root)


def test_system_sampler_derives_cpu_percent_from_consecutive_cgroup_snapshots(
    tmp_path: Path,
) -> None:
    proc_root, cgroup_root, cgroup_dir = _cgroup_v2_fixture(tmp_path, usage_usec=1_000_000)
    config = _config(tmp_path)
    config.evidence_dir.mkdir()
    config.stage_file.write_text("supervisor:solver_running\n", encoding="utf-8")
    fake_nvidia_smi = tmp_path / "fake-nvidia-smi"
    _write_fake_executable(fake_nvidia_smi, "#!/usr/bin/env python3\nprint('0, 0')\n")
    clock = FakeClock()
    sampler = supervisor.SystemSampler(
        config,
        FakeEngine(),
        clock=clock,
        nvidia_smi=str(fake_nvidia_smi),
        proc_root=proc_root,
        cgroup_root=cgroup_root,
        process_metrics=lambda _pid: (0.0, 0),
    )
    inspection = {"State": {"Running": True, "Pid": 4242}}

    first = sampler.sample("fake-container-id", inspection, "solver_running")
    (cgroup_dir / "cpu.stat").write_text("usage_usec 2500000\n", encoding="ascii")
    (cgroup_dir / "memory.current").write_text("8192\n", encoding="ascii")
    clock.now = 0.75
    second = sampler.sample("fake-container-id", inspection, "solver_running")

    assert first["cgroup_cpu_percent"] == 0.0
    assert first["cgroup_cpu_sample_interval_seconds"] == 0.0
    assert second["cgroup_cpu_percent"] == pytest.approx(200.0)
    assert second["cgroup_cpu_sample_interval_seconds"] == pytest.approx(0.75)
    assert second["cgroup_cpu_usage_usec"] == 2_500_000
    assert second["cgroup_memory_bytes"] == 8192


@pytest.mark.skipif(
    os.environ.get("FLUTAS_RUN_DOCKER_CGROUP_TEST") != "1",
    reason="set FLUTAS_RUN_DOCKER_CGROUP_TEST=1 for the harmless real Docker smoke",
)
def test_real_docker_cpu_only_cgroup_v2_smoke() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is unavailable")
    image = subprocess.run(
        [docker, "image", "inspect", "ubuntu:22.04"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if image.returncode != 0:
        pytest.skip("ubuntu:22.04 is not already present locally; test will not pull an image")
    name = f"flutas-cgroup-v2-smoke-{os.getpid()}-{time.monotonic_ns()}"
    created = False
    try:
        create = subprocess.run(
            [
                docker,
                "create",
                "--name",
                name,
                "--network",
                "none",
                "--cpus",
                "0.25",
                "--memory",
                "128m",
                "--memory-swap",
                "128m",
                "--log-driver=none",
                "ubuntu:22.04",
                "sh",
                "-c",
                "sleep 5",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert create.returncode == 0, create.stderr
        created = True
        start = subprocess.run(
            [docker, "start", name], capture_output=True, text=True, timeout=5, check=False
        )
        assert start.returncode == 0, start.stderr
        deadline = time.monotonic() + 3.0
        host_pid = 0
        while time.monotonic() < deadline:
            inspected = subprocess.run(
                [docker, "inspect", "--format", "{{.State.Running}} {{.State.Pid}}", name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            assert inspected.returncode == 0, inspected.stderr
            running, pid_text = inspected.stdout.strip().split()
            host_pid = int(pid_text)
            if running == "true" and host_pid > 0:
                break
            time.sleep(0.05)
        assert host_pid > 0, "CPU-only smoke container never exposed a running host PID"
        metrics = supervisor._read_cgroup_v2_metrics(host_pid)
        assert metrics.memory_max_bytes == 128 * 1024**2
        assert metrics.memory_current_bytes >= 0
        assert metrics.cpu_usage_usec >= 0
    finally:
        if created:
            subprocess.run(
                [docker, "rm", "-f", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )


@pytest.mark.parametrize("exit_code", [0, 7])
def test_normal_and_error_completion_are_recorded(tmp_path: Path, exit_code: int) -> None:
    engine = FakeEngine(exit_code=exit_code)
    clock = FakeClock()
    sampler = FakeSampler(engine, clock, complete_after_running_sample=True)

    result, engine, _ = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result == exit_code
    assert engine.removed
    assert engine.last_limits is not None
    assert engine.last_limits.cpu_cores == 2.0
    assert engine.last_limits.memory_bytes == 16 * supervisor.GIB
    events = _events(tmp_path / "evidence")
    first_running_sample = next(
        event
        for event in events
        if event.get("kind") == "sample" and event.get("phase") == "running"
    )
    assert first_running_sample["container_running"] is True
    assert first_running_sample["sample_started_monotonic_s"] == 0.0
    attached = next(event for event in events if event["kind"] == "attached_logs")
    if exit_code == 0:
        assert attached["returncode"] == 0
    assert any(
        event["kind"] == "termination_verification" and event["verified"] for event in events
    )
    assert events[-1]["disposition"] == "normal_termination_verified"


@pytest.mark.parametrize("failure", ["exception", "missing", "nan", "gap"])
def test_sampler_failure_or_gap_fails_closed_and_stops_container(
    tmp_path: Path, failure: str
) -> None:
    engine = FakeEngine()
    clock = FakeClock()
    if failure == "gap":
        clock.overshoot_next_sleep = 2.1
    sampler = FakeSampler(engine, clock, failure=failure)

    result, engine, _ = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert engine.stop_requests == 1
    assert engine.kill_requests == 0
    events = _events(tmp_path / "evidence")
    assert any(event["kind"] in {"sample_failure", "stop_trigger"} for event in events)
    assert any(
        event["kind"] == "termination_verification" and event["verified"] for event in events
    )


def test_wall_timeout_is_separate_from_verified_cleanup(tmp_path: Path) -> None:
    engine = FakeEngine()
    clock = FakeClock()
    limits = supervisor.Limits(wall_seconds=1.5)
    sampler = FakeSampler(engine, clock)

    result, engine, fake_clock = _run_fake(
        tmp_path, engine=engine, sampler=sampler, clock=clock, limits=limits
    )

    assert result == 124
    assert engine.stop_requests == 1
    assert engine.kill_requests == 0
    assert fake_clock() >= limits.wall_seconds
    assert _events(tmp_path / "evidence")[-1]["disposition"].startswith("failure_")


def test_signal_before_create_is_recorded_without_creating_container(tmp_path: Path) -> None:
    engine = FakeEngine()
    clock = FakeClock()
    instance = supervisor.SourceSupervisor(
        _config(tmp_path),
        ["fake-solver"],
        engine=engine,
        sampler=FakeSampler(engine, clock),
        clock=clock,
        sleep=clock.sleep,
    )
    instance.request_signal(signal.SIGTERM)

    result = instance.run()

    assert result == 128 + signal.SIGTERM
    assert not engine.created
    events = _events(tmp_path / "evidence")
    assert any(event["kind"] == "signal" and event["name"] == "SIGTERM" for event in events)
    summary = json.loads((tmp_path / "evidence" / "summary.json").read_text())
    assert summary["signal_sequence"] == ["SIGTERM"]


@pytest.mark.parametrize("threshold", ["gpu", "disk"])
def test_sampled_gpu_or_disk_threshold_requests_graceful_stop(
    tmp_path: Path, threshold: str
) -> None:
    engine = FakeEngine()
    clock = FakeClock()
    sampler = FakeSampler(
        engine,
        clock,
        gpu_used=supervisor.H7_LIMITS.gpu_memory_stop_bytes if threshold == "gpu" else 0,
        disk_used=supervisor.H7_LIMITS.disk_stop_bytes if threshold == "disk" else 0,
    )

    result, engine, _ = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert engine.stop_requests == 1
    assert engine.kill_requests == 0
    events = _events(tmp_path / "evidence")
    expected = (
        "GPU memory stop threshold reached"
        if threshold == "gpu"
        else "per-run disk stop threshold reached"
    )
    assert any(event["kind"] == "stop_trigger" and event["reason"] == expected for event in events)
    trigger_time = next(
        event["monotonic_s"]
        for event in events
        if event["kind"] == "stop_trigger" and event["reason"] == expected
    )
    dispatch_time = next(
        event["monotonic_s"]
        for event in events
        if event["kind"] == "signal_dispatch" and event.get("target") == "docker-container"
    )
    assert dispatch_time - trigger_time <= 1.0


@pytest.mark.parametrize(
    ("sample_field", "reason"),
    [
        ("log_bytes", "combined stdout/stderr output budget reached"),
        ("event_bytes", "supervisor event output budget reached"),
    ],
)
def test_sampled_log_and_event_budgets_request_graceful_stop(
    tmp_path: Path, sample_field: str, reason: str
) -> None:
    engine = FakeEngine()
    clock = FakeClock()
    value = (
        supervisor.H7_LIMITS.combined_stdout_stderr_stop_bytes
        if sample_field == "log_bytes"
        else supervisor.H7_LIMITS.supervisor_events_stop_bytes
    )
    sampler = FakeSampler(engine, clock, **{sample_field: value})

    result, engine, _ = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert engine.stop_requests == 1
    assert any(
        event["kind"] == "stop_trigger" and event["reason"] == reason
        for event in _events(tmp_path / "evidence")
    )


def test_supervision_jsonl_is_hard_bounded_by_event_allowance(tmp_path: Path) -> None:
    limits = supervisor.Limits(supervisor_events_stop_bytes=1024)

    result, engine, _ = _run_fake(tmp_path, limits=limits)

    assert result != 0
    assert not engine.created
    assert (tmp_path / "evidence" / "supervision.jsonl").stat().st_size <= 1024


@pytest.mark.parametrize(
    "override", ["--log-driver=json-file", "--log-opt=max-size=1m", "--attach=stdout", "-a"]
)
def test_config_rejects_output_storage_and_attach_overrides(tmp_path: Path, override: str) -> None:
    original = _config(tmp_path)
    invalid = supervisor.RunConfig(
        image=original.image,
        name=original.name,
        container_options=("--gpus", "all", override),
        evidence_dir=original.evidence_dir,
        disk_roots=original.disk_roots,
        stage_file=original.stage_file,
        stage_file_container=original.stage_file_container,
    )

    with pytest.raises(ValueError, match="cannot override supervisor option"):
        invalid.validate()


def test_external_docker_json_log_driver_fails_before_start(tmp_path: Path) -> None:
    engine = FakeEngine()
    engine.log_driver = "json-file"

    result, engine, _ = _run_fake(tmp_path, engine=engine)

    assert result != 0
    assert engine.created
    assert not engine.started.is_set()
    assert any(
        event["kind"] == "create_or_prestart_failure" for event in _events(tmp_path / "evidence")
    )


class _FastExitBeforeSampleEngine(FakeEngine):
    def request_start(self, container_id, stdout_path, stderr_path):
        del stdout_path, stderr_path
        assert container_id == "fake-container-id"
        self.started.set()
        self._attached_finished = False
        self.running = False
        return self._pending("start")


class _SubsecondGpuWindowEngine(FakeEngine):
    def __init__(self, clock: FakeClock) -> None:
        super().__init__()
        self.clock = clock
        self.started_at: float | None = None

    def request_start(self, container_id, stdout_path, stderr_path):
        assert container_id == "fake-container-id"
        del stdout_path, stderr_path
        self.started_at = self.clock()
        self.started.set()
        self._attached_finished = False
        return self._pending("start")

    def _elapsed(self) -> float:
        return 0.0 if self.started_at is None else self.clock() - self.started_at

    def inspect(self, container_id: str) -> Mapping[str, Any]:
        if self.started_at is not None:
            elapsed = self._elapsed()
            self.running = 0.2 <= elapsed < 0.75
            if elapsed >= 0.75:
                self.exit_code = 0
        return super().inspect(container_id)

    def poll_start(self, pending):
        del pending
        if self.started_at is not None and self._elapsed() >= 0.75:
            self.running = False
            self._attached_finished = True
            return _result("docker", "start", "--attach", "fake-container-id")
        return None


class _SubsecondGpuPulseSampler(FakeSampler):
    def sample(self, container_id, inspection, stage) -> dict[str, Any]:
        sample = super().sample(container_id, inspection, stage)
        state = inspection.get("State", {}) if inspection else {}
        if stage == "solver_running" and state.get("Running") and self.clock() >= 0.5:
            sample["gpu_memory_used_bytes"] = 64 * 1024**2
        return sample


def test_fast_exit_without_running_sample_is_inconclusive(tmp_path: Path) -> None:
    engine = _FastExitBeforeSampleEngine()

    result, engine, _ = _run_fake(tmp_path, engine=engine)

    assert result != 0
    assert engine.started.is_set()
    events = _events(tmp_path / "evidence")
    running_samples = [
        event
        for event in events
        if event.get("kind") == "sample" and event.get("phase") == "running"
    ]
    assert running_samples
    assert all(not event["container_running"] for event in running_samples)
    assert any(
        event["kind"] == "stop_trigger" and "no in-run sample observed" in event["reason"]
        for event in events
    )
    summary = json.loads((tmp_path / "evidence" / "summary.json").read_text())
    assert summary["last_termination_verification"]["verified"] is True


def test_startup_burst_observes_subsecond_container_and_gpu_pulse(tmp_path: Path) -> None:
    clock = FakeClock()
    engine = _SubsecondGpuWindowEngine(clock)
    sampler = _SubsecondGpuPulseSampler(engine, clock)

    result, _engine, _ = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result == 0
    samples = [event for event in _events(tmp_path / "evidence") if event.get("kind") == "sample"]
    running = [event for event in samples if event.get("phase") == "running"]
    assert any(not event["container_running"] for event in running)
    assert any(
        event["container_running"] and event["gpu_memory_used_bytes"] == 0 for event in running
    )
    assert any(
        event["container_running"] and event["gpu_memory_used_bytes"] == 64 * 1024**2
        for event in running
    )
    sample_times = [event["sample_monotonic_s"] for event in running]
    assert sample_times[:3] == pytest.approx([0.0, 0.25, 0.5])


def test_forced_stop_clears_a_surviving_child_after_grace(tmp_path: Path) -> None:
    engine = FakeEngine(stop_mode="stuck")
    engine.child_alive = True
    clock = FakeClock()
    sampler = FakeSampler(engine, clock, disk_used=supervisor.H7_LIMITS.disk_stop_bytes)

    result, engine, fake_clock = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert engine.stop_requests == 1
    assert engine.kill_requests == 1
    assert engine.forced_children >= 1
    assert fake_clock() >= supervisor.H7_LIMITS.graceful_seconds
    events = _events(tmp_path / "evidence")
    assert any(
        event["kind"] == "signal_dispatch" and event["signal"] == "SIGKILL" for event in events
    )
    assert any(
        event["kind"] == "termination_verification" and event["verified"] for event in events
    )


def test_exited_docker_client_does_not_release_lock_while_container_runs(tmp_path: Path) -> None:
    engine = FakeEngine(stop_mode="client_exits_early")
    clock = FakeClock()
    sampler = FakeSampler(engine, clock, failure="exception")

    result, engine, fake_clock = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert engine.kill_requests == 1
    assert fake_clock() >= supervisor.H7_LIMITS.graceful_seconds
    events = _events(tmp_path / "evidence")
    stopped_check = next(
        event
        for event in events
        if event["kind"] == "termination_verification" and event["phase"] == "graceful_stop"
    )
    assert stopped_check["docker_state_running"] is True
    assert stopped_check["surviving_docker_client_or_solver_children"] is False


def test_unverified_termination_after_30_seconds_stays_quarantined_until_proof(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    engine = _DelayedKillEngine(clock, delay_after_kill=35.0)
    sampler = FakeSampler(engine, clock, failure="exception")

    result, engine, fake_clock = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert fake_clock() >= 45.0
    events = _events(tmp_path / "evidence")
    escalation = next(event for event in events if event["kind"] == "escalation")
    verified = next(
        event
        for event in reversed(events)
        if event["kind"] == "termination_verification" and event["verified"]
    )
    assert escalation["monotonic_s"] >= 40.0
    assert verified["monotonic_s"] >= 45.0
    assert engine.kill_requests >= 2


def test_inspect_transport_error_is_not_treated_as_container_absent(tmp_path: Path) -> None:
    engine = FakeEngine(stop_mode="stuck")
    engine.inspect_errors = 2
    clock = FakeClock()
    sampler = FakeSampler(engine, clock, failure="exception")

    result, engine, _ = _run_fake(tmp_path, engine=engine, sampler=sampler, clock=clock)

    assert result != 0
    assert engine.kill_requests == 1
    events = _events(tmp_path / "evidence")
    assert any(event["kind"] == "docker_inspect_error" for event in events)
    assert not any(
        event["kind"] == "termination_verification"
        and event.get("phase") == "graceful_stop_begin"
        and event.get("docker_container_absent") is True
        and event.get("docker_state_running") is False
        for event in events
    )
    assert any(
        event["kind"] == "termination_verification" and event["verified"] for event in events
    )


def test_detached_guardian_holds_real_flock_after_launcher_is_killed(tmp_path: Path) -> None:
    lock_path = tmp_path / "gpu.lock"
    marker = tmp_path / "second-job-started"
    fake_docker = tmp_path / "fake-docker"
    fake_nvidia_smi = tmp_path / "fake-nvidia-smi"
    _write_fake_executable(fake_docker, _FAKE_DOCKER_SOURCE)
    _write_fake_executable(fake_nvidia_smi, "#!/usr/bin/env python3\nprint('0, 0')\n")
    config = supervisor.RunConfig(
        image="fake-image:locked",
        name="fake-flutas-guardian-test",
        container_options=("--gpus", "all"),
        evidence_dir=tmp_path / "guardian-evidence",
        disk_roots=(tmp_path,),
        stage_file=tmp_path / "guardian-stage.txt",
        stage_file_container="/run/h7-stage.txt",
        docker_executable=str(fake_docker),
        nvidia_smi_executable=str(fake_nvidia_smi),
    )
    config_path = tmp_path / "supervisor.json"
    config_path.write_text(
        json.dumps(
            {
                "image": config.image,
                "name": config.name,
                "container_options": list(config.container_options),
                "evidence_dir": str(config.evidence_dir),
                "disk_roots": [str(path) for path in config.disk_roots],
                "stage_file": str(config.stage_file),
                "stage_file_container": config.stage_file_container,
                "docker_executable": config.docker_executable,
                "nvidia_smi_executable": config.nvidia_smi_executable,
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    _install_fake_sampler_sitecustomize(tmp_path, environment)
    bootstrap = (
        "import pathlib,sys; sys.path.insert(0,sys.argv[1]); import run_local; "
        "run_local.gpu_lock_path=lambda: pathlib.Path(sys.argv[2]); "
        "raise SystemExit(run_local.main(sys.argv[3:]))"
    )
    launcher = subprocess.Popen(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(SCRIPTS),
            str(lock_path),
            "--gpu",
            "--threads",
            "1",
            "--source-supervisor",
            str(config_path),
            "--",
            "fake-solver",
            "--case",
            "dry_four",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    second_process: subprocess.Popen[str] | None = None
    release_child = tmp_path / "release-child"
    container_exit = tmp_path / "container-exit"
    fake_state = tmp_path / "fake-docker-state.json"
    guardian_pid: int | None = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if launcher.poll() is not None:
                stdout, stderr = launcher.communicate()
                raise AssertionError(f"launcher exited before start: {stdout}\n{stderr}")
            if fake_state.exists():
                state = json.loads(fake_state.read_text(encoding="utf-8"))
                if state.get("running") and state.get("pid"):
                    guardian_pid = int(state["lock_owner_pid"])
                    break
            time.sleep(0.05)
        assert guardian_pid is not None, "detached guardian did not start the fake container"
        assert os.getpgid(guardian_pid) != os.getpgid(launcher.pid)
        assert fake_state.exists()

        second_bootstrap = (
            "import pathlib,sys; sys.path.insert(0,sys.argv[1]); import run_local; "
            "run_local.gpu_lock_path=lambda: pathlib.Path(sys.argv[2]); "
            "raise SystemExit(run_local.main(sys.argv[3:]))"
        )
        second_process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                second_bootstrap,
                str(SCRIPTS),
                str(lock_path),
                "--gpu",
                "--threads",
                "1",
                "--",
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('started', encoding='utf-8')",
                str(marker),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.25)
        assert second_process.poll() is None and not marker.exists()

        launcher.kill()  # SIGKILL only the user-facing launcher PID.
        assert launcher.wait(timeout=3) == -signal.SIGKILL
        os.kill(guardian_pid, 0)
        assert second_process.poll() is None and not marker.exists()

        os.kill(guardian_pid, signal.SIGTERM)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state = json.loads(fake_state.read_text(encoding="utf-8"))
            if not state["running"]:
                break
            time.sleep(0.05)
        assert state["running"] is False
        time.sleep(0.2)
        assert second_process.poll() is None and not marker.exists()
        assert not release_child.exists()

        release_child.touch()
        stdout, stderr = second_process.communicate(timeout=10)
        assert second_process.returncode == 0, stderr
        assert not stdout
        assert marker.read_text(encoding="utf-8") == "started"
        events = _events(config.evidence_dir)
        configured = next(event for event in events if event["kind"] == "configured")
        assert configured["lock_owner_pid"] == guardian_pid
        assert configured["launcher_pid"] == str(launcher.pid)
        assert configured["detached_lock_guardian"] is True
        signals = [event for event in events if event["kind"] == "signal"]
        assert any(event["name"] == "SIGTERM" for event in signals)
        start_dispatch = next(
            event for event in events if event["kind"] == "docker_start_attached_dispatch"
        )
        assert "--attach" in start_dispatch["argv"]
        attached = next(event for event in events if event["kind"] == "attached_logs")
        assert attached["log_driver"] == "none"
        assert attached["stdout_bytes"] > 0
        assert attached["stderr_bytes"] > 0
        assert "fake supervised stdout" in (config.evidence_dir / "stdout.log").read_text()
        assert "fake supervised stderr" in (config.evidence_dir / "stderr.log").read_text()
        verifications = [
            event
            for event in events
            if event["kind"] == "termination_verification" and event["verified"]
        ]
        assert verifications[-1]["docker_state_running"] is False
        assert verifications[-1]["surviving_docker_client_or_solver_children"] is False
    finally:
        release_child.touch()
        container_exit.touch()
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=3)
        if second_process is not None and second_process.poll() is None:
            second_process.kill()
            second_process.communicate(timeout=2)


def test_launcher_sigterm_is_forwarded_and_guardian_waits_for_proof(tmp_path: Path) -> None:
    run_dir = tmp_path / "launcher-term"
    run_dir.mkdir()
    fake_docker = run_dir / "fake-docker"
    fake_nvidia_smi = run_dir / "fake-nvidia-smi"
    _write_fake_executable(fake_docker, _FAKE_DOCKER_SOURCE)
    _write_fake_executable(fake_nvidia_smi, "#!/usr/bin/env python3\nprint('0, 0')\n")
    config = supervisor.RunConfig(
        image="fake-image:locked",
        name="fake-flutas-launcher-term-test",
        container_options=("--gpus", "all"),
        evidence_dir=run_dir / "evidence",
        disk_roots=(run_dir,),
        stage_file=run_dir / "stage.txt",
        stage_file_container="/run/h7-stage.txt",
        docker_executable=str(fake_docker),
        nvidia_smi_executable=str(fake_nvidia_smi),
    )
    config_path = run_dir / "supervisor.json"
    config_path.write_text(
        json.dumps(
            {
                "image": config.image,
                "name": config.name,
                "container_options": list(config.container_options),
                "evidence_dir": str(config.evidence_dir),
                "disk_roots": [str(path) for path in config.disk_roots],
                "stage_file": str(config.stage_file),
                "stage_file_container": config.stage_file_container,
                "docker_executable": config.docker_executable,
                "nvidia_smi_executable": config.nvidia_smi_executable,
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    _install_fake_sampler_sitecustomize(run_dir, environment)
    lock_path = run_dir / "gpu.lock"
    bootstrap = (
        "import pathlib,sys; sys.path.insert(0,sys.argv[1]); import run_local; "
        "run_local.gpu_lock_path=lambda: pathlib.Path(sys.argv[2]); "
        "raise SystemExit(run_local.main(sys.argv[3:]))"
    )
    launcher = subprocess.Popen(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(SCRIPTS),
            str(lock_path),
            "--gpu",
            "--threads",
            "1",
            "--source-supervisor",
            str(config_path),
            "--",
            "fake-solver",
            "--case",
            "dry_four",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    release_child = run_dir / "release-child"
    state_path = run_dir / "fake-docker-state.json"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if launcher.poll() is not None:
                stdout, stderr = launcher.communicate()
                raise AssertionError(f"launcher exited before start: {stdout}\n{stderr}")
            if state_path.exists() and json.loads(state_path.read_text())["running"]:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("fake container did not start")

        launcher.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not json.loads(state_path.read_text())["running"]:
                break
            time.sleep(0.05)
        assert json.loads(state_path.read_text())["running"] is False
        assert launcher.poll() is None, "launcher must wait while child proof is outstanding"

        release_child.touch()
        _stdout, stderr = launcher.communicate(timeout=10)
        assert launcher.returncode == 128 + signal.SIGTERM, stderr
        events = _events(config.evidence_dir)
        assert any(event["kind"] == "signal" and event["name"] == "SIGTERM" for event in events)
        assert (
            next(
                event
                for event in reversed(events)
                if event["kind"] == "termination_verification" and event["verified"]
            )["surviving_docker_client_or_solver_children"]
            is False
        )
    finally:
        release_child.touch()
        (run_dir / "container-exit").touch()
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=3)


class _DelayedKillEngine(FakeEngine):
    def __init__(self, clock, *, delay_after_kill: float) -> None:
        super().__init__(stop_mode="stuck")
        self.clock = clock
        self.delay_after_kill = delay_after_kill
        self.kill_at: float | None = None

    def request_kill(self, container_id: str):
        assert container_id == "fake-container-id"
        self.kill_requests += 1
        self.docker_cli_alive = True
        self._kill_finished = False
        if self.kill_at is None:
            self.kill_at = self.clock() + self.delay_after_kill
        return self._pending("kill")

    def inspect(self, container_id: str) -> Mapping[str, Any]:
        if self.kill_at is not None and self.clock() >= self.kill_at:
            self.running = False
        return super().inspect(container_id)


_FAKE_DOCKER_SOURCE = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import time

base = pathlib.Path(__file__).resolve().parent
state_path = base / "fake-docker-state.json"
container_exit = base / "container-exit"
release_child = base / "release-child"
command = sys.argv[1]

def save(state):
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(state_path)

def load():
    return json.loads(state_path.read_text(encoding="utf-8"))

if command == "create":
    save({
        "id": "fake-container-id",
        "running": False,
        "removed": False,
        "log_driver_option": "--log-driver=none" in sys.argv,
        "lock_owner_pid": int(os.environ["FLUTAS_SOURCE_LOCK_OWNER_PID"]),
        "launcher_pid": os.environ["FLUTAS_SOURCE_LAUNCHER_PID"],
        "pid": None,
    })
    print("fake-container-id")
elif command == "start":
    worker_code = (
        "import pathlib,sys,time; release=pathlib.Path(sys.argv[1]); "
        "\nwhile not release.exists(): time.sleep(0.02)"
    )
    worker = subprocess.Popen(
        [sys.executable, "-c", worker_code, str(release_child)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    state = load()
    state["running"] = True
    state["pid"] = worker.pid
    save(state)
    print("fake supervised stdout", flush=True)
    print("fake supervised stderr", file=sys.stderr, flush=True)
    while not container_exit.exists():
        time.sleep(0.02)
elif command == "inspect":
    if not state_path.exists() or load().get("removed"):
        print("Error: no such container", file=sys.stderr)
        raise SystemExit(1)
    state = load()
    if container_exit.exists():
        state["running"] = False
        save(state)
    print(json.dumps([{
        "Id": state["id"],
        "State": {
            "Running": state["running"],
            "Pid": state["pid"] if state["running"] else 0,
            "ExitCode": 0,
        },
        "HostConfig": {
            "NanoCpus": 2000000000,
            "Memory": 17179869184,
            "MemorySwap": 17179869184,
            "LogConfig": {"Type": "none"},
        },
    }]))
elif command == "stats":
    print("0.0%,0B / 16GiB")
elif command == "stop":
    container_exit.touch(exist_ok=True)
    raise SystemExit(0)
elif command == "kill":
    release_child.touch(exist_ok=True)
    state = load()
    state["running"] = False
    save(state)
elif command == "logs":
    print("fake supervised output")
elif command == "rm":
    state = load()
    state["removed"] = True
    save(state)
else:
    print("unsupported fake Docker command: " + command, file=sys.stderr)
    raise SystemExit(2)
"""
