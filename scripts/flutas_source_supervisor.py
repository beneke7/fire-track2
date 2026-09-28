#!/usr/bin/env python3
"""Fail-closed lifecycle supervision for a single source-boundary Docker run.

The caller must hold run_local.gpu_lock for the entire call to run_from_config.
The supervisor creates a named, inspectable container (never --rm), applies the
H7 hard CPU/RAM limits, monitors the run, and returns only after Docker reports
State.Running=false and every tracked Docker client process group is gone.

The JSON configuration contains image, name, container_options, evidence_dir,
disk_roots, stage_file, stage_file_container, gpu_index, docker_executable and
nvidia_smi_executable. The command passed after run_local's -- is the command
inside that pinned image. container_options may contain mounts and --gpus, but
cannot override lifecycle identity or hard resource limits.
"""

from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol

GIB = 1024**3
MIB = 1024**2
DETERMINISTIC_DATA_FILE_COUNT = 37
DETERMINISTIC_DATA_BYTES = 57_447_891


@dataclass(frozen=True)
class Limits:
    cpu_cores: float = 2.0
    memory_bytes: int = 16 * GIB
    gpu_memory_stop_bytes: int = 24 * GIB
    disk_stop_bytes: int = 1 * GIB
    combined_stdout_stderr_stop_bytes: int = 64 * MIB
    supervisor_events_stop_bytes: int = 16 * MIB
    wall_seconds: float = 1800.0
    sample_seconds: float = 1.0
    startup_sample_seconds: float = 0.25
    startup_sample_window_seconds: float = 1.0
    max_sample_gap_seconds: float = 2.0
    sample_budget_seconds: float = 0.8
    graceful_seconds: float = 10.0
    force_dispatch_seconds: float = 1.0
    verification_seconds: float = 30.0

    def validate(self) -> None:
        finite_positive = (
            self.cpu_cores,
            self.wall_seconds,
            self.sample_seconds,
            self.startup_sample_seconds,
            self.startup_sample_window_seconds,
            self.max_sample_gap_seconds,
            self.sample_budget_seconds,
            self.graceful_seconds,
            self.force_dispatch_seconds,
            self.verification_seconds,
        )
        if any(not math.isfinite(value) or value <= 0 for value in finite_positive):
            raise ValueError("all H7 limits and intervals must be finite and positive")
        if any(
            value <= 0
            for value in (
                self.memory_bytes,
                self.gpu_memory_stop_bytes,
                self.disk_stop_bytes,
                self.combined_stdout_stderr_stop_bytes,
                self.supervisor_events_stop_bytes,
            )
        ):
            raise ValueError("H7 byte limits must be positive")
        if self.sample_seconds > self.max_sample_gap_seconds:
            raise ValueError("sample interval cannot exceed the maximum valid sample gap")
        if not math.isclose(self.sample_seconds, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("H7 steady-state resource sampling is fixed at one second")
        if self.startup_sample_seconds > 0.25 or self.startup_sample_window_seconds > 1.0:
            raise ValueError("H7 startup sampling exceeds its fixed burst bounds")
        if self.max_sample_gap_seconds > 2.0 or self.sample_budget_seconds > 0.8:
            raise ValueError("H7 sample gap or dispatch budget exceeds its fixed maximum")
        if self.force_dispatch_seconds > 1.0 or self.verification_seconds > 30.0:
            raise ValueError("force-dispatch and verification deadlines exceed H7 bounds")
        if self.graceful_seconds > 10.0:
            raise ValueError("graceful shutdown allowance exceeds the H7 bound")
        if (
            self.cpu_cores > 2.0
            or self.memory_bytes > 16 * GIB
            or self.gpu_memory_stop_bytes > 24 * GIB
            or self.disk_stop_bytes > 1 * GIB
            or self.combined_stdout_stderr_stop_bytes > 64 * MIB
            or self.supervisor_events_stop_bytes > 16 * MIB
            or self.wall_seconds > 1800.0
        ):
            raise ValueError("configured H7 resource ceilings cannot exceed the reviewed proposal")


H7_LIMITS = Limits()


@dataclass(frozen=True)
class RunConfig:
    image: str
    name: str
    container_options: tuple[str, ...]
    evidence_dir: Path
    disk_roots: tuple[Path, ...]
    stage_file: Path
    stage_file_container: str
    gpu_index: str = "0"
    docker_executable: str = "docker"
    nvidia_smi_executable: str = "nvidia-smi"

    @classmethod
    def from_json(cls, path: Path) -> RunConfig:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("source supervisor configuration must be a JSON object")
        required = {
            "image",
            "name",
            "container_options",
            "evidence_dir",
            "disk_roots",
            "stage_file",
            "stage_file_container",
        }
        missing = required.difference(value)
        if missing:
            raise ValueError(f"source supervisor configuration is missing {sorted(missing)}")
        options = value["container_options"]
        roots = value["disk_roots"]
        if not isinstance(options, list) or any(not isinstance(item, str) for item in options):
            raise ValueError("container_options must be an array of strings")
        if not isinstance(roots, list) or any(not isinstance(item, str) for item in roots):
            raise ValueError("disk_roots must be an array of paths")
        config = cls(
            image=_string(value, "image"),
            name=_string(value, "name"),
            container_options=tuple(options),
            evidence_dir=Path(_string(value, "evidence_dir")),
            disk_roots=tuple(Path(item) for item in roots),
            stage_file=Path(_string(value, "stage_file")),
            stage_file_container=_string(value, "stage_file_container"),
            gpu_index=str(value.get("gpu_index", "0")),
            docker_executable=str(value.get("docker_executable", "docker")),
            nvidia_smi_executable=str(value.get("nvidia_smi_executable", "nvidia-smi")),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.image.strip() or not self.name.strip():
            raise ValueError("image and container name must be nonempty")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", self.name) is None:
            raise ValueError("container name contains unsupported characters")
        if not self.container_options:
            raise ValueError("container_options must explicitly declare GPU access")
        reserved = {
            "--rm",
            "--name",
            "--cpus",
            "--cpu-quota",
            "--cpu-period",
            "--cpu-shares",
            "--cpuset-cpus",
            "--memory",
            "-m",
            "--memory-swap",
            "--memory-reservation",
            "--memory-swappiness",
            "--memory-oom-kill-disable",
            "--cidfile",
            "--stop-timeout",
            "--privileged",
            "--cgroupns",
            "--pid",
            "--log-driver",
            "--log-opt",
            "--attach",
            "-a",
        }
        for option in self.container_options:
            head = option.split("=", 1)[0]
            if head in reserved:
                raise ValueError(f"container_options cannot override supervisor option {head}")
        if not any(
            item == "--gpus" or item.startswith("--gpus=") for item in self.container_options
        ):
            raise ValueError("container_options must explicitly select Docker GPU access")
        if not self.disk_roots or any(not path.is_absolute() for path in self.disk_roots):
            raise ValueError("per-run disk roots must be absolute paths")
        if not self.evidence_dir.is_absolute():
            raise ValueError("evidence_dir must be an absolute path")
        if any(not path.is_dir() for path in self.disk_roots):
            raise ValueError("every per-run disk root must exist and be a directory")
        resolved_roots = sorted(path.resolve() for path in self.disk_roots)
        for index, first in enumerate(resolved_roots):
            if any(first in second.parents for second in resolved_roots[index + 1 :]):
                raise ValueError("disk_roots cannot overlap or double-count nested directories")
        if not self.stage_file.is_absolute() or not Path(self.stage_file_container).is_absolute():
            raise ValueError("stage file paths must be absolute")
        if not self.docker_executable or not self.nvidia_smi_executable:
            raise ValueError("Docker and nvidia-smi executable names must be nonempty")


def _string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be a nonempty string")
    return result


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    process_group: int | None = None


class ContainerNotFound(RuntimeError):
    """Docker conclusively reported that the requested container is absent."""


@dataclass
class PendingDockerCommand:
    process: subprocess.Popen[bytes]
    argv: tuple[str, ...]
    process_group: int | None
    stdout_file: Any = None
    stderr_file: Any = None


class Engine(Protocol):
    def create(self, config: RunConfig, command: list[str], limits: Limits) -> str: ...

    def request_start(
        self, container_id: str, stdout_path: Path, stderr_path: Path
    ) -> PendingDockerCommand: ...

    def poll_start(self, pending: PendingDockerCommand) -> CommandResult | None: ...

    def inspect(self, container_id: str) -> Mapping[str, Any]: ...

    def request_stop(self, container_id: str, grace_seconds: float) -> PendingDockerCommand: ...

    def poll_stop(self, pending: PendingDockerCommand) -> CommandResult | None: ...

    def request_kill(self, container_id: str) -> PendingDockerCommand: ...

    def poll_kill(self, pending: PendingDockerCommand) -> CommandResult | None: ...

    def remove(self, container_id: str) -> CommandResult: ...

    def has_surviving_children(self) -> bool: ...

    def force_kill_children(self) -> None: ...


class DockerCLI:
    """Small Docker CLI adapter that owns and checks every CLI process group."""

    def __init__(self, executable: str, environment: Mapping[str, str] | None = None):
        self.executable = executable
        self.environment = dict(environment) if environment is not None else None
        self.process_groups: set[int] = set()
        self.processes: list[subprocess.Popen[bytes]] = []

    def _call(self, arguments: list[str], *, timeout: float = 1.0) -> CommandResult:
        argv = (self.executable, *arguments)
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.environment,
            start_new_session=(os.name == "posix"),
        )
        group = process.pid if os.name == "posix" else None
        if group is not None:
            self.process_groups.add(group)
        self.processes.append(process)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return CommandResult(argv, process.returncode or 0, stdout, stderr, group)
        except subprocess.TimeoutExpired:
            self._signal_group(group, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=0.1)
            except subprocess.TimeoutExpired:
                self._signal_group(group, signal.SIGKILL)
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                except subprocess.TimeoutExpired:
                    # Keep ownership and the group identity; verification will
                    # keep the caller's GPU lock until this child is gone.
                    return CommandResult(
                        argv, 124, "", "Docker CLI remains alive after SIGKILL", group
                    )
            return CommandResult(argv, 124, stdout, stderr or "Docker CLI timed out", group)

    @staticmethod
    def _signal_group(group: int | None, sig: int) -> None:
        if group is None:
            return
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            pass
        except OSError:
            pass

    @staticmethod
    def _group_alive(group: int) -> bool:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def create(self, config: RunConfig, command: list[str], limits: Limits) -> str:
        args = [
            "create",
            "--name",
            config.name,
            "--label",
            "fire-track2.supervised=true",
            "--cpus",
            f"{limits.cpu_cores:g}",
            "--memory",
            str(limits.memory_bytes),
            "--memory-swap",
            str(limits.memory_bytes),
            "--stop-timeout",
            f"{limits.graceful_seconds:g}",
            "--log-driver=none",
            *config.container_options,
            "--env",
            "OMP_NUM_THREADS=1",
            "--env",
            "OMP_THREAD_LIMIT=1",
            "--env",
            "OPENBLAS_NUM_THREADS=1",
            "--env",
            "MKL_NUM_THREADS=1",
            "--env",
            f"H7_STAGE_FILE={config.stage_file_container}",
            "--mount",
            (f"type=bind,source={config.stage_file},target={config.stage_file_container}"),
            config.image,
            *command,
        ]
        result = self._call(args, timeout=limits.sample_budget_seconds)
        if result.returncode != 0:
            raise RuntimeError(
                f"docker create returned {result.returncode}: {result.stderr.strip()}"
            )
        container_id = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if not container_id:
            raise RuntimeError("docker create returned no container ID")
        return container_id

    def request_start(
        self, container_id: str, stdout_path: Path, stderr_path: Path
    ) -> PendingDockerCommand:
        argv = (self.executable, "start", "--attach", container_id)
        stdout_file = stdout_path.open("ab", buffering=0)
        stderr_file = stderr_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                argv,
                stdout=stdout_file,
                stderr=stderr_file,
                env=self.environment,
                start_new_session=(os.name == "posix"),
            )
        except BaseException:
            stdout_file.close()
            stderr_file.close()
            raise
        group = process.pid if os.name == "posix" else None
        if group is not None:
            self.process_groups.add(group)
        self.processes.append(process)
        return PendingDockerCommand(process, argv, group, stdout_file, stderr_file)

    @staticmethod
    def poll_start(pending: PendingDockerCommand) -> CommandResult | None:
        return DockerCLI._poll_attached(pending)

    @staticmethod
    def _poll_attached(pending: PendingDockerCommand) -> CommandResult | None:
        if pending.process.poll() is None:
            return None
        pending.process.wait()
        for stream in (pending.stdout_file, pending.stderr_file):
            if stream is not None and not stream.closed:
                stream.flush()
                stream.close()
        return CommandResult(
            pending.argv, pending.process.returncode or 0, "", "", pending.process_group
        )

    def request_stop(self, container_id: str, grace_seconds: float) -> PendingDockerCommand:
        argv = (self.executable, "stop", "--time", f"{grace_seconds:g}", container_id)
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.environment,
            start_new_session=(os.name == "posix"),
        )
        group = process.pid if os.name == "posix" else None
        if group is not None:
            self.process_groups.add(group)
        self.processes.append(process)
        return PendingDockerCommand(process, argv, group)

    @staticmethod
    def poll_stop(pending: PendingDockerCommand) -> CommandResult | None:
        if pending.process.poll() is None:
            return None
        stdout, stderr = pending.process.communicate()
        return CommandResult(
            pending.argv,
            pending.process.returncode or 0,
            stdout,
            stderr,
            pending.process_group,
        )

    @staticmethod
    def poll_kill(pending: PendingDockerCommand) -> CommandResult | None:
        return DockerCLI.poll_stop(pending)

    def inspect(self, container_id: str) -> Mapping[str, Any]:
        result = self._call(["inspect", container_id], timeout=0.25)
        if result.returncode != 0:
            lowered = result.stderr.lower()
            if "no such object" in lowered or "no such container" in lowered:
                raise ContainerNotFound(result.stderr.strip())
            raise RuntimeError(
                f"docker inspect returned {result.returncode}: {result.stderr.strip()}"
            )
        decoded = json.loads(result.stdout)
        if not isinstance(decoded, list) or not decoded or not isinstance(decoded[0], dict):
            raise ValueError("docker inspect did not return one container object")
        return decoded[0]

    def kill(self, container_id: str) -> CommandResult:
        return self._call(["kill", container_id], timeout=1.0)

    def request_kill(self, container_id: str) -> PendingDockerCommand:
        argv = (self.executable, "kill", container_id)
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.environment,
            start_new_session=(os.name == "posix"),
        )
        group = process.pid if os.name == "posix" else None
        if group is not None:
            self.process_groups.add(group)
        self.processes.append(process)
        return PendingDockerCommand(process, argv, group)

    def remove(self, container_id: str) -> CommandResult:
        return self._call(["rm", container_id], timeout=1.0)

    def has_surviving_children(self) -> bool:
        for process in tuple(self.processes):
            process.poll()  # Reap completed direct children.
        self.processes = [process for process in self.processes if process.poll() is None]
        alive = [group for group in self.process_groups if self._group_alive(group)]
        self.process_groups.intersection_update(alive)
        return bool(alive)

    def force_kill_children(self) -> None:
        for group in tuple(self.process_groups):
            self._signal_group(group, signal.SIGKILL)


class SampleProvider(Protocol):
    def sample(
        self, container_id: str | None, inspection: Mapping[str, Any] | None, stage: str
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CgroupV2Metrics:
    path: Path
    cpu_usage_usec: int
    memory_current_bytes: int
    memory_max_bytes: int


def _nonnegative_integer(path: Path, *, label: str) -> int:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"cgroup v2 {label} file is missing or unsafe: {path}")
    value = path.read_text(encoding="ascii").strip()
    if not value.isdecimal():
        raise ValueError(f"cgroup v2 {label} must be a nonnegative integer, got {value!r}")
    return int(value)


def _read_cpu_usage_usec(path: Path) -> int:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"cgroup v2 cpu.stat file is missing or unsafe: {path}")
    values: dict[str, int] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        pieces = line.split()
        if len(pieces) != 2 or pieces[0] in values or not pieces[1].isdecimal():
            raise ValueError(f"malformed cgroup v2 cpu.stat row: {line!r}")
        values[pieces[0]] = int(pieces[1])
    if "usage_usec" not in values:
        raise ValueError("cgroup v2 cpu.stat is missing usage_usec")
    return values["usage_usec"]


def _read_cgroup_v2_metrics(
    pid: int,
    *,
    proc_root: Path = Path("/proc"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> CgroupV2Metrics:
    """Read one host PID's unified cgroup counters without Docker stats."""
    if pid <= 0:
        raise ValueError("host PID must be a positive integer")
    proc_dir = proc_root / str(pid)
    membership = proc_dir / "cgroup"
    if proc_dir.is_symlink() or membership.is_symlink() or not membership.is_file():
        raise RuntimeError(f"host PID {pid} has no safe /proc cgroup membership file")
    lines = membership.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError(f"host PID {pid} has an empty /proc cgroup membership file")
    records: list[str] = []
    for line in lines:
        fields = line.split(":", 2)
        if len(fields) != 3 or not fields[0].isdecimal():
            raise ValueError(f"malformed /proc/{pid}/cgroup membership row: {line!r}")
        if fields[0] == "0" and fields[1] == "":
            records.append(fields[2])
    if len(records) != 1 or len(lines) != 1:
        raise RuntimeError(
            "cgroup v2 unified membership is unavailable for host PID "
            f"{pid}; refusing Docker stats fallback"
        )
    membership_path = records[0]
    pure_path = PurePosixPath(membership_path)
    if not pure_path.is_absolute() or "\x00" in membership_path:
        raise ValueError(f"invalid cgroup v2 membership path {membership_path!r}")
    components = [] if membership_path == "/" else membership_path[1:].split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ValueError(f"cgroup membership path escapes the v2 root: {membership_path!r}")
    if cgroup_root.is_symlink() or not cgroup_root.is_dir():
        raise RuntimeError(f"cgroup v2 mount root is missing or unsafe: {cgroup_root}")
    root = cgroup_root.resolve(strict=True)
    controllers = cgroup_root / "cgroup.controllers"
    if controllers.is_symlink() or not controllers.is_file():
        raise RuntimeError(
            f"cgroup v2 is required but {cgroup_root} has no cgroup.controllers file"
        )
    directory = cgroup_root.joinpath(*components)
    current = cgroup_root
    for component in components:
        current = current / component
        if current.is_symlink():
            raise RuntimeError(f"cgroup v2 path contains a symlink: {current}")
    if not directory.is_dir():
        raise RuntimeError(f"cgroup v2 directory for host PID {pid} is missing: {directory}")
    resolved = directory.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"cgroup v2 path escapes mount root: {resolved}") from error
    cpu_usage_usec = _read_cpu_usage_usec(resolved / "cpu.stat")
    memory_current_bytes = _nonnegative_integer(resolved / "memory.current", label="memory.current")
    memory_max_bytes = _nonnegative_integer(resolved / "memory.max", label="memory.max")
    if memory_max_bytes <= 0:
        raise ValueError("cgroup v2 memory.max must be positive and finite")
    return CgroupV2Metrics(
        path=resolved,
        cpu_usage_usec=cpu_usage_usec,
        memory_current_bytes=memory_current_bytes,
        memory_max_bytes=memory_max_bytes,
    )


def _process_metrics(pid: int | None) -> tuple[float, int]:
    if pid is None or pid <= 0:
        return 0.0, 0
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    fields = stat.rsplit(")", 1)[1].strip().split()
    ticks = int(fields[11]) + int(fields[12])
    cpu_seconds = ticks / os.sysconf("SC_CLK_TCK")
    status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
    rss = next(
        (int(line.split()[1]) * 1024 for line in status.splitlines() if line.startswith("VmRSS:")),
        None,
    )
    if rss is None or not math.isfinite(cpu_seconds):
        raise ValueError("solver process CPU or RSS sample is missing/nonfinite")
    return cpu_seconds, rss


def _measure_directory_bytes(path: Path, *, deadline: float, clock: Callable[[], float]) -> int:
    total = 0
    stack = [path]
    while stack:
        if clock() > deadline:
            raise TimeoutError(f"disk sample exceeded {path} deadline")
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if clock() > deadline:
                    raise TimeoutError(f"disk sample exceeded {path} deadline")
                if entry.is_symlink():
                    raise ValueError(f"symlink encountered while measuring disk root: {entry.path}")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
    return total


def _unique_disk_roots(config: RunConfig) -> tuple[Path, ...]:
    """Measure configured mutable roots plus evidence exactly once."""
    candidates = sorted(
        {path.resolve() for path in (*config.disk_roots, config.evidence_dir.resolve())},
        key=lambda item: (len(item.parts), str(item)),
    )
    roots: list[Path] = []
    for candidate in candidates:
        if not any(candidate == root or root in candidate.parents for root in roots):
            roots.append(candidate)
    return tuple(roots)


class SystemSampler:
    """Sample solver procfs, cgroup v2, selected GPU, disk roots and stage."""

    def __init__(
        self,
        config: RunConfig,
        engine: Engine,
        *,
        clock: Callable[[], float] = time.monotonic,
        nvidia_smi: str | None = None,
        budget_seconds: float = H7_LIMITS.sample_budget_seconds,
        memory_limit_bytes: int = H7_LIMITS.memory_bytes,
        proc_root: Path = Path("/proc"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        process_metrics: Callable[[int | None], tuple[float, int]] = _process_metrics,
    ):
        self.config = config
        self.engine = engine
        self.clock = clock
        self.nvidia_smi = nvidia_smi or config.nvidia_smi_executable
        self.budget_seconds = budget_seconds
        self.memory_limit_bytes = memory_limit_bytes
        self.proc_root = proc_root
        self.cgroup_root = cgroup_root
        self.process_metrics = process_metrics
        self._previous_cgroup_cpu: tuple[Path, int, float] | None = None

    def sample(
        self, container_id: str | None, inspection: Mapping[str, Any] | None, stage: str
    ) -> dict[str, Any]:
        started = self.clock()
        deadline = started + self.budget_seconds
        running = _running(inspection) if inspection is not None else False
        state = inspection.get("State", {}) if inspection is not None else {}
        pid = state.get("Pid") if running and isinstance(state, dict) else None
        if running and (
            not isinstance(pid, (int, float)) or not math.isfinite(float(pid)) or int(pid) <= 0
        ):
            raise ValueError("running container is missing a valid host solver PID")
        pid_int = int(pid) if isinstance(pid, (int, float)) and math.isfinite(float(pid)) else None
        process_cpu, process_rss = self.process_metrics(pid_int)
        cgroup_cpu_percent = 0.0
        cgroup_cpu_usage_usec = 0
        cgroup_cpu_sample_interval_seconds = 0.0
        cgroup_memory_bytes = 0
        cgroup_memory_limit_bytes = self.memory_limit_bytes
        cgroup_v2_path: str | None = None
        if running:
            if container_id is None:
                raise ValueError("running sample is missing a container ID")
            assert pid_int is not None
            cgroup_metrics = _read_cgroup_v2_metrics(
                pid_int,
                proc_root=self.proc_root,
                cgroup_root=self.cgroup_root,
            )
            cgroup_v2_path = str(cgroup_metrics.path)
            cgroup_cpu_usage_usec = cgroup_metrics.cpu_usage_usec
            cgroup_memory_bytes = cgroup_metrics.memory_current_bytes
            cgroup_memory_limit_bytes = cgroup_metrics.memory_max_bytes
            if cgroup_memory_limit_bytes != self.memory_limit_bytes:
                raise ValueError("observed Docker cgroup memory limit differs from H7 hard limit")
            cpu_snapshot_time = self.clock()
            if self._previous_cgroup_cpu is not None:
                previous_path, previous_usage_usec, previous_time = self._previous_cgroup_cpu
                if previous_path != cgroup_metrics.path:
                    raise RuntimeError("container cgroup v2 path changed during the supervised run")
                delta_usec = cgroup_cpu_usage_usec - previous_usage_usec
                cgroup_cpu_sample_interval_seconds = cpu_snapshot_time - previous_time
                if delta_usec < 0:
                    raise ValueError("cgroup v2 cpu.stat usage_usec counter decreased")
                if (
                    not math.isfinite(cgroup_cpu_sample_interval_seconds)
                    or cgroup_cpu_sample_interval_seconds <= 0
                ):
                    raise ValueError("cgroup v2 CPU sample interval must be finite and positive")
                cgroup_cpu_percent = (
                    delta_usec / 1_000_000 / cgroup_cpu_sample_interval_seconds * 100
                )
            self._previous_cgroup_cpu = (
                cgroup_metrics.path,
                cgroup_cpu_usage_usec,
                cpu_snapshot_time,
            )
        gpu = subprocess.run(
            [
                self.nvidia_smi,
                f"--id={self.config.gpu_index}",
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=max(0.01, min(0.25, deadline - self.clock())),
            check=False,
        )
        if gpu.returncode != 0:
            raise RuntimeError(f"nvidia-smi returned {gpu.returncode}: {gpu.stderr.strip()}")
        gpu_fields = [item.strip() for item in gpu.stdout.strip().split(",")]
        if len(gpu_fields) != 2:
            raise ValueError("GPU memory/utilization sample is malformed")
        gpu_memory_mib, gpu_utilization = map(float, gpu_fields)
        disk_bytes = 0
        for root in _unique_disk_roots(self.config):
            disk_bytes += _measure_directory_bytes(root, deadline=deadline, clock=self.clock)
        stdout_path = self.config.evidence_dir / "stdout.log"
        stderr_path = self.config.evidence_dir / "stderr.log"
        stdout_bytes = stdout_path.stat().st_size if stdout_path.exists() else 0
        stderr_bytes = stderr_path.stat().st_size if stderr_path.exists() else 0
        event_path = self.config.evidence_dir / "supervision.jsonl"
        event_bytes = event_path.stat().st_size if event_path.exists() else 0
        stage_value = self.config.stage_file.read_text(encoding="utf-8").strip()
        if not stage_value:
            raise ValueError("solver stage sample is empty")
        sample = {
            "process_cpu_seconds": process_cpu,
            "process_rss_bytes": process_rss,
            "cgroup_cpu_percent": cgroup_cpu_percent,
            "cgroup_cpu_usage_usec": cgroup_cpu_usage_usec,
            "cgroup_cpu_sample_interval_seconds": cgroup_cpu_sample_interval_seconds,
            "cgroup_memory_bytes": cgroup_memory_bytes,
            "cgroup_memory_limit_bytes": cgroup_memory_limit_bytes,
            "cgroup_v2_path": cgroup_v2_path,
            "gpu_device_index": self.config.gpu_index,
            "gpu_memory_used_bytes": int(gpu_memory_mib * 1024**2),
            "gpu_utilization_percent": gpu_utilization,
            "disk_used_bytes": disk_bytes,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "combined_stdout_stderr_bytes": stdout_bytes + stderr_bytes,
            "supervisor_event_bytes": event_bytes,
            "solver_stage": stage_value or stage,
            "container_running": running,
            "container_state": dict(state) if isinstance(state, dict) else {},
            "sample_duration_seconds": self.clock() - started,
        }
        return sample


def _running(inspection: Mapping[str, Any] | None) -> bool:
    if inspection is None:
        return False
    state = inspection.get("State")
    if not isinstance(state, Mapping) or not isinstance(state.get("Running"), bool):
        raise ValueError("Docker inspect is missing boolean State.Running")
    return state["Running"]


def _validate_sample(sample: Mapping[str, Any]) -> None:
    required_numeric = (
        "process_cpu_seconds",
        "process_rss_bytes",
        "cgroup_cpu_percent",
        "cgroup_cpu_usage_usec",
        "cgroup_cpu_sample_interval_seconds",
        "cgroup_memory_bytes",
        "cgroup_memory_limit_bytes",
        "gpu_memory_used_bytes",
        "gpu_utilization_percent",
        "disk_used_bytes",
        "stdout_bytes",
        "stderr_bytes",
        "combined_stdout_stderr_bytes",
        "supervisor_event_bytes",
        "sample_duration_seconds",
    )
    missing = [key for key in required_numeric if key not in sample]
    if missing:
        raise ValueError(f"sample is missing fields: {missing}")
    for key in required_numeric:
        value = sample[key]
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"sample field {key} is missing or nonfinite")
        if value < 0:
            raise ValueError(f"sample field {key} is negative")
    if sample["gpu_utilization_percent"] > 100:
        raise ValueError("GPU utilization sample exceeds 100 percent")
    if not isinstance(sample.get("solver_stage"), str) or not sample["solver_stage"].strip():
        raise ValueError("solver stage sample is missing")
    if not isinstance(sample.get("container_running"), bool):
        raise ValueError("container state sample is missing")


class SourceSupervisor:
    def __init__(
        self,
        config: RunConfig,
        command: list[str],
        *,
        limits: Limits = H7_LIMITS,
        engine: Engine | None = None,
        sampler: SampleProvider | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        limits.validate()
        config.validate()
        if not command:
            raise ValueError("a solver command is required after --")
        self.config = config
        self.command = list(command)
        self.limits = limits
        self.clock = clock
        self.sleep = sleep
        self.engine = engine or DockerCLI(config.docker_executable)
        self.sampler = sampler or SystemSampler(
            config,
            self.engine,
            clock=clock,
            budget_seconds=limits.sample_budget_seconds,
            memory_limit_bytes=limits.memory_bytes,
        )
        self.container_id: str | None = None
        self.stage = "pre_container"
        self.previous_sample_time: float | None = None
        self.previous_sample_start: float | None = None
        self.started_at: float | None = None
        self.signal_requests: list[int] = []
        self.signal_sequence: list[int] = []
        self.signal_events: list[dict[str, Any]] = []
        self.last_signal: int | None = None
        self.stop_trigger: str | None = None
        self.stop_trigger_monotonic_s: float | None = None
        self.exit_code = 1
        self.events_path = config.evidence_dir / "supervision.jsonl"
        self._events: Any = None
        self._event_bytes_written = 0
        self._event_budget_exhausted = False
        self.start_pending: PendingDockerCommand | None = None
        self.start_result: CommandResult | None = None
        self.saw_running_sample = False
        self.saw_gpu_execution_sample = False
        self.baseline_gpu_memory_used_bytes: int | None = None
        self.stdout_path = config.evidence_dir / "stdout.log"
        self.stderr_path = config.evidence_dir / "stderr.log"
        self._logs_captured = False
        self._last_sample: dict[str, Any] | None = None
        self.last_termination_verification: dict[str, Any] | None = None

    def request_signal(self, signum: int, frame: object = None) -> None:
        del frame
        self.signal_requests.append(signum)

    def _record(self, kind: str, **values: Any) -> None:
        event = {"kind": kind, "monotonic_s": self.clock(), **values}
        if self._events is not None:
            if self._event_budget_exhausted:
                return
            encoded = (json.dumps(event, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            cap = self.limits.supervisor_events_stop_bytes
            if self._event_bytes_written + len(encoded) > cap:
                self._event_budget_exhausted = True
                encoded = (
                    json.dumps(
                        {
                            "kind": "supervisor_event_budget_exhausted",
                            "monotonic_s": self.clock(),
                            "limit_bytes": cap,
                            "attempted_event": kind,
                        },
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf-8")
                remaining = cap - self._event_bytes_written
                if len(encoded) > remaining:
                    encoded = b""
                self._event_budget_exhausted = True
            if encoded:
                self._events.write(encoded.decode("utf-8"))
                self._event_bytes_written += len(encoded)
            self._events.flush()
            os.fsync(self._events.fileno())

    def _inspect(self, *, phase: str) -> Mapping[str, Any] | None:
        reference = self.container_id
        if reference is None:
            return None
        try:
            result = self.engine.inspect(reference)
            self._record("docker_inspect", phase=phase, response=result)
            return result
        except Exception as error:
            self._record(
                "docker_inspect_error", phase=phase, error=f"{type(error).__name__}: {error}"
            )
            return None

    def _sample(self, *, phase: str) -> tuple[dict[str, Any] | None, str | None]:
        started = self.clock()
        inspection: Mapping[str, Any] | None = None
        absent = self.container_id is None
        try:
            if self.container_id is not None:
                try:
                    inspection = self.engine.inspect(self.container_id)
                    self._record("docker_inspect", phase=phase, response=inspection)
                except ContainerNotFound as error:
                    absent = True
                    self._record("docker_container_absent", phase=phase, error=str(error))
                except Exception as error:
                    self._record(
                        "docker_inspect_error",
                        phase=phase,
                        error=f"{type(error).__name__}: {error}",
                    )
                    raise RuntimeError("Docker container state sample is unavailable") from error
            if self.container_id is not None and inspection is None and not absent:
                raise RuntimeError("Docker container state sample is missing")
            sample = self.sampler.sample(self.container_id, inspection, self.stage)
            _validate_sample(sample)
            completed = self.clock()
            gap = (
                None if self.previous_sample_start is None else started - self.previous_sample_start
            )
            record = {
                **sample,
                "phase": phase,
                "sample_started_monotonic_s": started,
                "sample_monotonic_s": completed,
                "sample_gap_s": gap,
            }
            self._record("sample", **record)
            self._last_sample = record
            if phase == "running" and sample["container_running"]:
                self.saw_running_sample = True
                if self.baseline_gpu_memory_used_bytes is not None and (
                    sample["gpu_memory_used_bytes"] > self.baseline_gpu_memory_used_bytes
                    or sample["gpu_utilization_percent"] > 0
                ):
                    self.saw_gpu_execution_sample = True
            if phase == "before_create":
                self.baseline_gpu_memory_used_bytes = sample["gpu_memory_used_bytes"]
            self.previous_sample_time = completed
            self.previous_sample_start = started
            if completed - started > self.limits.sample_budget_seconds:
                raise TimeoutError("resource sample exceeded its dispatch budget")
            if gap is not None and gap > self.limits.max_sample_gap_seconds:
                return (
                    record,
                    f"sample gap {gap:.6g}s exceeded {self.limits.max_sample_gap_seconds:g}s",
                )
            if sample["gpu_memory_used_bytes"] >= self.limits.gpu_memory_stop_bytes:
                return record, "GPU memory stop threshold reached"
            if sample["disk_used_bytes"] >= self.limits.disk_stop_bytes:
                return record, "per-run disk stop threshold reached"
            if (
                sample["combined_stdout_stderr_bytes"]
                >= self.limits.combined_stdout_stderr_stop_bytes
            ):
                return record, "combined stdout/stderr output budget reached"
            if (
                sample["supervisor_event_bytes"] >= self.limits.supervisor_events_stop_bytes
                or self._event_budget_exhausted
            ):
                return record, "supervisor event output budget reached"
            if sample["cgroup_memory_bytes"] > self.limits.memory_bytes:
                return record, "observed cgroup memory exceeds the hard limit"
            if sample["cgroup_memory_limit_bytes"] != self.limits.memory_bytes:
                return record, "observed cgroup memory limit differs from the hard limit"
            if sample["sample_duration_seconds"] > self.limits.sample_budget_seconds:
                return record, "resource sample exceeded its dispatch budget"
            return record, None
        except Exception as error:
            reason = f"sampler failure: {type(error).__name__}: {error}"
            self._record("sample_failure", phase=phase, error=reason)
            return None, reason

    def _trigger(self, reason: str) -> None:
        if self.stop_trigger is None:
            self.stop_trigger = reason
            self.stop_trigger_monotonic_s = self.clock()
            self._record("stop_trigger", reason=reason)

    def _verify_limits(self, inspection: Mapping[str, Any]) -> None:
        host = inspection.get("HostConfig")
        if not isinstance(host, Mapping):
            raise ValueError("Docker inspect is missing HostConfig")
        expected_nano = int(self.limits.cpu_cores * 1_000_000_000)
        expected_memory = self.limits.memory_bytes
        if host.get("NanoCpus") != expected_nano:
            raise ValueError("Docker CPU hard limit differs from H7 configuration")
        if host.get("Memory") != expected_memory or host.get("MemorySwap") != expected_memory:
            raise ValueError("Docker cgroup memory/swap hard limit differs from H7 configuration")
        log_config = host.get("LogConfig")
        if not isinstance(log_config, Mapping) or log_config.get("Type") != "none":
            raise ValueError(
                "Docker log driver is not disabled; external JSON-log storage is unbounded"
            )

    def _check_pending_signal(self) -> bool:
        if not self.signal_requests:
            return False
        signum = self.signal_requests.pop(0)
        self.signal_sequence.append(signum)
        self.last_signal = signum
        signal_event = {
            "signal": signum,
            "name": signal.Signals(signum).name,
            "monotonic_s": self.clock(),
        }
        self.signal_events.append(signal_event)
        self._record("signal", signal=signum, name=signal.Signals(signum).name)
        self._trigger(f"received {signal.Signals(signum).name}")
        return True

    def _wait_next_sample(self, next_sample: float) -> None:
        remaining = next_sample - self.clock()
        if remaining > 0:
            self.sleep(remaining)

    def _group_alive(self) -> bool:
        try:
            return self.engine.has_surviving_children()
        except Exception as error:
            self._record("child_check_error", error=f"{type(error).__name__}: {error}")
            return True

    def _verification(self, *, phase: str) -> tuple[bool, Mapping[str, Any] | None, bool]:
        inspection: Mapping[str, Any] | None = None
        absent = False
        try:
            if self.container_id is not None:
                inspection = self.engine.inspect(self.container_id)
                self._record("docker_inspect", phase=phase, response=inspection)
            else:
                absent = True
        except ContainerNotFound as error:
            absent = True
            self._record("docker_container_absent", phase=phase, error=str(error))
        except Exception as error:
            self._record(
                "docker_inspect_error", phase=phase, error=f"{type(error).__name__}: {error}"
            )
        if absent:
            running = False
        elif inspection is None:
            running = True
        else:
            try:
                running = _running(inspection)
            except Exception as error:
                self._record("state_parse_error", phase=phase, error=str(error))
                running = True
        child_alive = self._group_alive()
        self.last_termination_verification = {
            "phase": phase,
            "docker_container_absent": absent,
            "docker_state_running": running,
            "surviving_docker_client_or_solver_children": child_alive,
            "verified": not running and not child_alive,
            "monotonic_s": self.clock(),
        }
        self._record(
            "termination_verification",
            phase=phase,
            docker_state=(inspection.get("State") if inspection else None),
            docker_container_absent=absent,
            docker_state_running=running,
            surviving_docker_client_or_solver_children=child_alive,
            verified=(not running and not child_alive),
        )
        return (not running and not child_alive), inspection, child_alive

    def _poll_command(
        self, pending: PendingDockerCommand | None, *, command: str
    ) -> PendingDockerCommand | None:
        if pending is None:
            return None
        poller = self.engine.poll_stop if command == "stop" else self.engine.poll_kill
        try:
            result = poller(pending)
        except Exception as error:
            self._record(f"docker_{command}_poll_error", error=f"{type(error).__name__}: {error}")
            return pending
        if result is not None:
            self._record(
                f"docker_{command}",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                argv=result.argv,
            )
            return None
        return pending

    def _poll_start(self) -> CommandResult | None:
        if self.start_pending is None:
            return None
        try:
            result = self.engine.poll_start(self.start_pending)
        except Exception as error:
            self._record(
                "docker_attached_start_poll_error", error=f"{type(error).__name__}: {error}"
            )
            return None
        if result is not None:
            self.start_pending = None
            self.start_result = result
            self._record(
                "docker_attached_start_exit",
                returncode=result.returncode,
                argv=result.argv,
            )
        return result

    def _force_stop(self) -> PendingDockerCommand | None:
        dispatched_at = self.clock()
        try:
            self.engine.force_kill_children()
            self._record(
                "signal_dispatch",
                target="docker-client-and-solver-process-groups",
                signal="SIGKILL",
            )
        except Exception as error:
            self._record("force_child_kill_error", error=f"{type(error).__name__}: {error}")
        pending: PendingDockerCommand | None = None
        if self.container_id:
            try:
                pending = self.engine.request_kill(self.container_id)
                self._record("docker_kill_dispatch", argv=pending.argv)
            except Exception as error:
                self._record("docker_kill_error", error=f"{type(error).__name__}: {error}")
        elapsed = self.clock() - dispatched_at
        self._record(
            "force_dispatch",
            elapsed_s=elapsed,
            within_h7_limit=elapsed <= self.limits.force_dispatch_seconds,
        )
        return pending

    def _cleanup(self, reason: str) -> bool:
        self._trigger(reason)
        self.stage = "graceful_stop"
        stop_started = self.clock()
        pending_stop: PendingDockerCommand | None = None
        try:
            if self.container_id:
                pending_stop = self.engine.request_stop(
                    self.container_id, self.limits.graceful_seconds
                )
                self._record(
                    "signal_dispatch",
                    target="docker-container",
                    signal="SIGTERM",
                    argv=pending_stop.argv,
                    grace_seconds=self.limits.graceful_seconds,
                )
        except Exception as error:
            self._record("docker_stop_dispatch_error", error=f"{type(error).__name__}: {error}")
        dispatch_elapsed = self.clock() - stop_started
        self._record(
            "graceful_dispatch",
            elapsed_s=dispatch_elapsed,
            within_h7_limit=dispatch_elapsed <= self.limits.force_dispatch_seconds,
        )

        verified, _inspection, child_alive = self._verification(phase="graceful_stop_begin")
        graceful_deadline = stop_started + self.limits.graceful_seconds
        graceful_was_dispatched = pending_stop is not None
        next_sample = self.clock() + self.limits.sample_seconds
        while not verified and graceful_was_dispatched and self.clock() < graceful_deadline:
            self._poll_start()
            if pending_stop is not None:
                pending_stop = self._poll_command(pending_stop, command="stop")
            self._wait_next_sample(next_sample)
            _sample, sample_error = self._sample(phase="graceful_stop")
            if sample_error:
                self._record("cleanup_sample_failure", phase="graceful_stop", reason=sample_error)
            self._check_pending_signal()
            self._poll_start()
            verified, _inspection, child_alive = self._verification(phase="graceful_stop")
            next_sample += self.limits.sample_seconds

        if pending_stop is not None:
            pending_stop = self._poll_command(pending_stop, command="stop")
        if not verified:
            self.stage = "forced_stop"
            pending_kill = self._force_stop()
            force_started = self.clock()
            verification_deadline = force_started + self.limits.verification_seconds
            next_sample = self.clock() + self.limits.sample_seconds
            escalated = False
            while not verified:
                self._poll_start()
                pending_kill = self._poll_command(pending_kill, command="kill")
                self._wait_next_sample(next_sample)
                _sample, sample_error = self._sample(phase="termination_verification")
                if sample_error:
                    self._record(
                        "cleanup_sample_failure",
                        phase="termination_verification",
                        reason=sample_error,
                    )
                self._poll_start()
                verified, _inspection, child_alive = self._verification(
                    phase="termination_verification"
                )
                next_sample += self.limits.sample_seconds
                if not verified and self.clock() >= verification_deadline and not escalated:
                    self.stage = "quarantine_unverified"
                    self._record(
                        "escalation",
                        disposition="termination_not_verified_within_30_seconds_lock_must_remain_held",
                        docker_state_running=True,
                        surviving_children=child_alive,
                    )
                    print(
                        "[flutas_source_supervisor] CRITICAL: termination is unverified; "
                        "retaining the GPU lock and retrying proof",
                        file=sys.stderr,
                        flush=True,
                    )
                    escalated = True
                    # Keep retrying forever; returning would release run_local's lock.
                if (
                    not verified
                    and escalated
                    and int(self.clock() - verification_deadline) % 5 == 0
                ):
                    pending_kill = self._force_stop() or pending_kill

        # Logs and explicit removal are performed only after the container has
        # stopped. Their Docker clients are themselves included in the final
        # proof, so the lock cannot be released while one is still alive.
        self._capture_logs()
        self._remove()
        verified, _inspection, child_alive = self._verification(phase="post_cleanup_verification")
        if not verified:
            pending_kill = self._force_stop()
            verification_deadline = self.clock() + self.limits.verification_seconds
            next_sample = self.clock() + self.limits.sample_seconds
            escalated = False
            while not verified:
                self._poll_start()
                pending_kill = self._poll_command(pending_kill, command="kill")
                self._wait_next_sample(next_sample)
                _sample, sample_error = self._sample(phase="post_cleanup_verification")
                if sample_error:
                    self._record(
                        "cleanup_sample_failure",
                        phase="post_cleanup_verification",
                        reason=sample_error,
                    )
                self._poll_start()
                verified, _inspection, child_alive = self._verification(
                    phase="post_cleanup_verification"
                )
                next_sample += self.limits.sample_seconds
                if not verified and self.clock() >= verification_deadline and not escalated:
                    self.stage = "quarantine_unverified"
                    self._record(
                        "escalation",
                        disposition="post_cleanup_termination_not_verified_within_30_seconds_lock_must_remain_held",
                        surviving_children=child_alive,
                    )
                    escalated = True
                if (
                    not verified
                    and escalated
                    and int(self.clock() - verification_deadline) % 5 == 0
                ):
                    pending_kill = self._force_stop() or pending_kill
        self.stage = "terminated_verified"
        self._record("cleanup", disposition="termination_verified", trigger=self.stop_trigger)
        return True

    def _emergency_quarantine(self, original_error: BaseException) -> None:
        """Fail closed if normal cleanup itself fails while lock ownership is active."""
        self.stage = "quarantine_unverified"
        try:
            self._record(
                "emergency_quarantine",
                error=f"{type(original_error).__name__}: {original_error}",
                disposition="retain_gpu_lock_until_state_and_children_are_proven_stopped",
            )
        except BaseException:
            pass
        pending_kill: PendingDockerCommand | None = None
        next_sample = self.clock()
        while True:
            try:
                self.engine.force_kill_children()
                if self.container_id and pending_kill is None:
                    pending_kill = self.engine.request_kill(self.container_id)
                elif pending_kill is not None:
                    pending_kill = self._poll_command(pending_kill, command="kill")
                self._poll_start()
                _sample, sample_error = self._sample(phase="emergency_quarantine")
                if sample_error:
                    self._record(
                        "cleanup_sample_failure", phase="emergency_quarantine", reason=sample_error
                    )
                verified, _inspection, _children = self._verification(phase="emergency_quarantine")
                if verified:
                    self._record(
                        "emergency_quarantine_resolved",
                        disposition="termination_verified_after_cleanup_exception",
                    )
                    self.stage = "terminated_verified"
                    return
            except BaseException as error:
                try:
                    self._record(
                        "emergency_quarantine_error",
                        error=f"{type(error).__name__}: {error}",
                    )
                except BaseException:
                    pass
            next_sample += self.limits.sample_seconds
            self._wait_next_sample(next_sample)

    def _capture_logs(self) -> None:
        if self._logs_captured:
            return
        attached_result = self._poll_start()
        if attached_result is None:
            attached_result = self.start_result
        if self.start_pending is not None:
            self._record(
                "attached_logs_incomplete",
                reason="docker start --attach remains alive; retain lock until termination proof",
            )
            return
        stdout_bytes = self.stdout_path.stat().st_size if self.stdout_path.exists() else 0
        stderr_bytes = self.stderr_path.stat().st_size if self.stderr_path.exists() else 0
        try:
            self._record(
                "attached_logs",
                returncode=attached_result.returncode if attached_result is not None else None,
                stdout_path=str(self.stdout_path),
                stderr_path=str(self.stderr_path),
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                combined_bytes=stdout_bytes + stderr_bytes,
                log_driver="none",
                rotation="disabled; attached streams preserved as raw files",
            )
            self._logs_captured = True
        except Exception as error:
            self._record("attached_logs_record_error", error=f"{type(error).__name__}: {error}")

    def _remove(self) -> None:
        if not self.container_id:
            return
        try:
            result = self.engine.remove(self.container_id)
            self._record(
                "docker_remove",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                argv=result.argv,
            )
        except Exception as error:
            self._record("docker_remove_error", error=f"{type(error).__name__}: {error}")

    def run(self) -> int:
        self.config.evidence_dir.mkdir(parents=True, exist_ok=False)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.stdout_path.open("xb").close()
        self.stderr_path.open("xb").close()
        self.config.stage_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.stage_file.write_text("supervisor:precreate\n", encoding="utf-8")
        self._events = self.events_path.open("x", encoding="utf-8")
        self._record(
            "configured",
            image=self.config.image,
            container_name=self.config.name,
            container_options=list(self.config.container_options),
            disk_roots=[str(item) for item in self.config.disk_roots],
            measured_mutable_roots=[str(item) for item in _unique_disk_roots(self.config)],
            limits=asdict(self.limits),
            deterministic_data_file_count=DETERMINISTIC_DATA_FILE_COUNT,
            deterministic_data_bytes=DETERMINISTIC_DATA_BYTES,
            immutable_oci_budget=(
                "separate from mutable-run 1 GiB cap; image storage is external to this supervisor"
            ),
            command=self.command,
            evidence_dir=str(self.config.evidence_dir),
            lock_owner_pid=os.getpid(),
            launcher_pid=os.environ.get("FLUTAS_SOURCE_LAUNCHER_PID"),
            detached_lock_guardian=os.environ.get("FLUTAS_SOURCE_LOCK_OWNER_PID")
            == str(os.getpid()),
            monitoring_started_before_container_create=True,
        )
        try:
            _sample, reason = self._sample(phase="before_create")
            if reason:
                self._trigger(reason)
                return self._finish_failure(1)
            self._check_pending_signal()
            if self.stop_trigger:
                exit_code = 128 + self.last_signal if self.last_signal is not None else 1
                return self._finish_failure(exit_code)

            self.stage = "container_create"
            self.container_id = self.config.name
            try:
                created_id = self.engine.create(self.config, self.command, self.limits)
                if not created_id:
                    raise RuntimeError("Docker create returned an empty container ID")
                self.container_id = created_id
                self._record("docker_create", container_id=created_id)
                self.stage = "container_created"
                self.config.stage_file.write_text(
                    "supervisor:container_created\n", encoding="utf-8"
                )
                inspection = self._inspect(phase="created")
                if inspection is None:
                    raise RuntimeError("Docker state could not be inspected after create")
                self._verify_limits(inspection)
                if _running(inspection):
                    raise ValueError("new Docker container was unexpectedly already running")
            except BaseException as error:
                self._record("create_or_prestart_failure", error=f"{type(error).__name__}: {error}")
                self._trigger(f"container creation/setup failure: {type(error).__name__}")
                self._cleanup(self.stop_trigger or "container creation/setup failure")
                return self._finish_failure(1)

            if self._check_pending_signal():
                self._cleanup(self.stop_trigger or "termination signal")
                return self._finish_failure(128 + (self.last_signal or signal.SIGTERM))
            self.stage = "container_start"
            self.start_pending = self.engine.request_start(
                self.container_id, self.stdout_path, self.stderr_path
            )
            self._record(
                "docker_start_attached_dispatch",
                argv=self.start_pending.argv,
                stdout_path=str(self.stdout_path),
                stderr_path=str(self.stderr_path),
            )
            self.stage = "solver_running"
            self.started_at = self.clock()
            self.config.stage_file.write_text("supervisor:solver_running\n", encoding="utf-8")
            # Sample immediately, then use a bounded startup burst until a
            # running GPU sample is seen or one second elapses. Thereafter the
            # reviewed steady-state cadence remains one second.
            next_sample = self.started_at

            while True:
                if self._check_pending_signal():
                    self._cleanup(self.stop_trigger or "termination signal")
                    return self._finish_failure(128 + (self.last_signal or signal.SIGTERM))
                now = self.clock()
                if (
                    self.started_at is not None
                    and now - self.started_at >= self.limits.wall_seconds
                ):
                    self._trigger(f"solver wall limit of {self.limits.wall_seconds:g}s reached")
                    self._cleanup(self.stop_trigger or "wall timeout")
                    return self._finish_failure(124)
                self._wait_next_sample(next_sample)
                sample, reason = self._sample(phase="running")
                if (
                    self.started_at is not None
                    and self.clock() - self.started_at < self.limits.startup_sample_window_seconds
                    and not self.saw_gpu_execution_sample
                ):
                    next_sample = min(
                        self.started_at + self.limits.startup_sample_window_seconds,
                        self.clock() + self.limits.startup_sample_seconds,
                    )
                else:
                    next_sample = self.clock() + self.limits.sample_seconds
                if reason:
                    self._cleanup(reason)
                    return self._finish_failure(1)
                if self._check_pending_signal():
                    self._cleanup(self.stop_trigger or "termination signal")
                    return self._finish_failure(128 + (self.last_signal or signal.SIGTERM))
                start_result = self._poll_start()
                inspection = self._inspect(phase="completion_check")
                running = _running(inspection) if inspection is not None else True
                if start_result is not None and start_result.returncode != 0:
                    self._cleanup(f"docker start --attach returned {start_result.returncode}")
                    return self._finish_failure(1)
                if running and start_result is not None:
                    self._cleanup("docker start --attach exited while container remained running")
                    return self._finish_failure(1)
                if not running:
                    if self.start_pending is not None:
                        next_sample = max(next_sample, self.clock())
                        continue
                    if not self.saw_running_sample:
                        self._cleanup(
                            "no in-run sample observed the container running; result is inconclusive"
                        )
                        return self._finish_failure(1)
                    if self.start_pending is not None or self._group_alive():
                        self._cleanup(
                            "Docker container stopped but a solver/container child survived"
                        )
                        return self._finish_failure(1)
                    state = inspection.get("State", {}) if inspection else {}
                    exit_code = state.get("ExitCode", 1) if isinstance(state, Mapping) else 1
                    if not isinstance(exit_code, int) or exit_code < 0:
                        exit_code = 1
                    self.exit_code = exit_code
                    self.stage = "solver_exited"
                    self._record("solver_exit", exit_code=exit_code, sample=sample)
                    break

            verified, _inspection, child_alive = self._verification(phase="normal_completion")
            if not verified:
                self._cleanup(
                    "normal completion did not prove Docker stopped and all children exited"
                    if child_alive
                    else "normal completion did not prove Docker State.Running=false"
                )
                return self._finish_failure(1)
            self._capture_logs()
            self._remove()
            verified, _inspection, child_alive = self._verification(
                phase="post_cleanup_verification"
            )
            if not verified:
                self._cleanup(
                    "post-cleanup verification failed after logs/removal"
                    if child_alive
                    else "post-cleanup Docker state became unverifiable"
                )
                return self._finish_failure(1)
            self.stage = "terminated_verified"
            self._record(
                "result", exit_code=self.exit_code, disposition="normal_termination_verified"
            )
            return self.exit_code
        except BaseException as error:
            try:
                self._record("supervisor_exception", error=f"{type(error).__name__}: {error}")
            except BaseException:
                pass
            try:
                self._trigger(f"supervisor exception: {type(error).__name__}")
            except BaseException:
                self.stop_trigger = self.stop_trigger or "supervisor exception"
            try:
                self._cleanup(self.stop_trigger or "supervisor exception")
            except BaseException as cleanup_error:
                self._emergency_quarantine(cleanup_error)
            return self._finish_failure(1)
        finally:
            self._write_summary()
            self._events.close()
            self._events = None

    def _finish_failure(self, exit_code: int) -> int:
        self.exit_code = exit_code
        self._record(
            "result",
            exit_code=exit_code,
            disposition="failure_termination_verified_or_no_container",
        )
        return exit_code

    def _write_summary(self) -> None:
        path = self.config.evidence_dir / "summary.json"
        payload = {
            "container_id": self.container_id,
            "exit_code": self.exit_code,
            "stop_trigger": self.stop_trigger,
            "stop_trigger_monotonic_s": self.stop_trigger_monotonic_s,
            "signal_sequence": [signal.Signals(item).name for item in self.signal_sequence],
            "signals": self.signal_events,
            "disposition": "termination_verified"
            if self.stage == "terminated_verified"
            else self.stage,
            "last_termination_verification": self.last_termination_verification,
            "last_sample": self._last_sample,
            "supervision_event_bytes": self._event_bytes_written,
            "supervision_event_budget_exhausted": self._event_budget_exhausted,
            "stdout_bytes": self.stdout_path.stat().st_size if self.stdout_path.exists() else 0,
            "stderr_bytes": self.stderr_path.stat().st_size if self.stderr_path.exists() else 0,
            "limits": asdict(self.limits),
        }
        try:
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            print(f"[flutas_source_supervisor] cannot write summary {path}", file=sys.stderr)


def run_from_config(
    config_path: Path,
    command: list[str],
    environment: Mapping[str, str] | None = None,
    initial_signals: list[int] | None = None,
) -> int:
    queued_signals = initial_signals if initial_signals is not None else []

    def queue_signal(signum: int, frame: object) -> None:
        del frame
        queued_signals.append(signum)

    previous: dict[int, Any] = {
        signum: signal.signal(signum, queue_signal) for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        config = RunConfig.from_json(config_path)
        config.evidence_dir.parent.mkdir(parents=True, exist_ok=True)
        engine = DockerCLI(config.docker_executable, environment)
        supervisor = SourceSupervisor(config, command, engine=engine)
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, supervisor.request_signal)
        supervisor.signal_requests.extend(queued_signals)
        queued_signals.clear()
        return supervisor.run()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
