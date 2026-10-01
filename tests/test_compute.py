import importlib.util
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "doctor.py"
RUN_LOCAL = ROOT / "scripts" / "run_local.py"
DOCTOR_SPEC = importlib.util.spec_from_file_location("compute_doctor", DOCTOR)
assert DOCTOR_SPEC is not None and DOCTOR_SPEC.loader is not None
doctor = importlib.util.module_from_spec(DOCTOR_SPEC)
DOCTOR_SPEC.loader.exec_module(doctor)


def _run(script: Path, *arguments: str, timeout: float = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _read_line(stream, timeout: float = 4) -> str:
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        assert selector.select(timeout), "process did not produce expected output"
        return stream.readline()


def _process_state(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return stat.rsplit(")", 1)[1].strip().split()[0]


def _launcher_with_test_lock(lock_path: Path, *arguments: str) -> list[str]:
    bootstrap = (
        "import pathlib,sys; sys.path.insert(0,sys.argv[1]); import run_local; "
        "run_local.gpu_lock_path=lambda: pathlib.Path(sys.argv[2]); "
        "raise SystemExit(run_local.main(sys.argv[3:]))"
    )
    return [sys.executable, "-c", bootstrap, str(ROOT / "scripts"), str(lock_path), *arguments]


def test_doctor_json_reports_resources_and_readiness() -> None:
    completed = _run(DOCTOR, "--json")

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["schema_version"] == 1
    assert report["interpreter"]["executable"] == sys.executable
    assert report["resources"]["cpu"]["effective"] >= 1
    assert report["resources"]["memory"]["effective_available_bytes"] is None or (
        report["resources"]["memory"]["effective_available_bytes"] >= 0
    )
    assert report["resources"]["disk"]["free_bytes"] >= 0
    assert report["gpu"]["solver_support_verified"] is False
    assert report["readiness"]["gpu_solver_support_verified"] is False


def test_doctor_writes_json_report_with_human_summary(tmp_path: Path) -> None:
    output = tmp_path / "machine.json"
    completed = _run(DOCTOR, "--output", str(output))

    assert completed.returncode == 0, completed.stderr
    assert "Compute doctor" in completed.stdout
    assert "Python:" in completed.stdout
    assert "Packages:" in completed.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1


def test_doctor_honors_parent_cgroup_cpu_and_memory_limits(tmp_path: Path, monkeypatch) -> None:
    leaf = tmp_path / "leaf"
    parent = tmp_path / "parent"
    leaf.mkdir()
    parent.mkdir()
    (leaf / "cpu.max").write_text("max 100000", encoding="utf-8")
    (parent / "cpu.max").write_text("200000 100000", encoding="utf-8")
    (leaf / "cpuset.cpus.effective").write_text("0-19", encoding="utf-8")
    (leaf / "memory.max").write_text("max", encoding="utf-8")
    (leaf / "memory.current").write_text(str(900 * 1024 * 1024), encoding="utf-8")
    (parent / "memory.max").write_text(str(1024 * 1024 * 1024), encoding="utf-8")
    (parent / "memory.current").write_text(str(512 * 1024 * 1024), encoding="utf-8")

    files = {
        ("cpu.max", None): [leaf / "cpu.max", parent / "cpu.max"],
        ("cpu.cfs_quota_us", "cpu"): [],
        ("cpuset.cpus.effective", "cpuset"): [leaf / "cpuset.cpus.effective"],
        ("cpuset.cpus", "cpuset"): [],
        ("memory.max", None): [leaf / "memory.max", parent / "memory.max"],
        ("memory.current", None): [leaf / "memory.current", parent / "memory.current"],
        ("memory.limit_in_bytes", "memory"): [],
        ("memory.usage_in_bytes", "memory"): [],
    }
    monkeypatch.setattr(
        doctor,
        "_cgroup_candidates",
        lambda filename, controller=None: files.get((filename, controller), []),
    )

    cpu = doctor._cpu_limits()
    memory_limit, memory_current, _ = doctor._memory_cgroup()
    assert cpu["cgroup_quota_cores"] == 2
    assert cpu["effective"] <= 2
    assert cpu["default_threads"] == cpu["effective"]
    assert memory_limit == 1024 * 1024 * 1024
    assert memory_current == 512 * 1024 * 1024


def test_launcher_defaults_to_doctor_budget_and_passes_arguments_without_shell() -> None:
    doctor = _run(DOCTOR, "--json")
    assert doctor.returncode == 0, doctor.stderr
    default_threads = json.loads(doctor.stdout)["resources"]["cpu"]["default_threads"]
    probe = (
        "import json,os,sys; "
        "print(json.dumps({'threads':[os.environ[k] for k in "
        "('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')],"
        "'args':sys.argv[1:]}))"
    )
    argument = "literal ; argument with spaces"
    completed = _run(RUN_LOCAL, "--", sys.executable, "-c", probe, argument)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["threads"] == [str(default_threads)] * 3
    assert result["args"] == [argument]


def test_launcher_forwards_exit_code_and_times_out() -> None:
    failed = _run(RUN_LOCAL, "--threads", "1", "--", sys.executable, "-c", "raise SystemExit(7)")
    assert failed.returncode == 7

    timed_out = _run(
        RUN_LOCAL,
        "--timeout",
        "0.1",
        "--",
        sys.executable,
        "-c",
        "import time; time.sleep(5)",
        timeout=4,
    )
    assert timed_out.returncode == 124
    assert "timed out" in timed_out.stderr


def test_gpu_lock_serializes_jobs_even_with_explicit_thread_count(tmp_path: Path) -> None:
    first_environment = os.environ.copy()
    first_environment["TMPDIR"] = str(tmp_path / "first-temp")
    second_environment = os.environ.copy()
    second_environment["TMPDIR"] = str(tmp_path / "second-temp")
    release = tmp_path / "release-first"
    started_second = tmp_path / "second-started"
    first_code = (
        "import pathlib,sys,time\n"
        "print('started', flush=True)\n"
        "release=pathlib.Path(sys.argv[1])\n"
        "deadline=time.monotonic()+15\n"
        "while not release.exists():\n"
        "    if time.monotonic()>deadline: raise SystemExit(8)\n"
        "    time.sleep(0.01)\n"
    )
    first = subprocess.Popen(
        [
            *_launcher_with_test_lock(
                tmp_path / "gpu.lock",
                "--gpu",
                "--threads",
                "1",
                "--",
                sys.executable,
                "-c",
                first_code,
                str(release),
            ),
        ],
        cwd=ROOT,
        env=first_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    second = None
    try:
        assert first.stdout is not None
        assert _read_line(first.stdout).strip() == "started"
        second = subprocess.Popen(
            _launcher_with_test_lock(
                tmp_path / "gpu.lock",
                "--gpu",
                "--threads",
                "1",
                "--",
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('second', encoding='utf-8')",
                str(started_second),
            ),
            cwd=ROOT,
            env=second_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not started_second.exists() and second.poll() is None:
            time.sleep(0.01)
        assert second.poll() is None
        assert not started_second.exists()
        release.touch()
        _, first_error = first.communicate(timeout=4)
        second_output, second_error = second.communicate(timeout=4)
        assert first.returncode == 0, first_error
        assert second.returncode == 0, second_error
        assert started_second.read_text(encoding="utf-8") == "second"
    finally:
        release.touch()
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=2)
        if second is not None and second.poll() is None:
            second.kill()
            second.communicate(timeout=2)


def test_sigterm_stops_child_process_group_before_launcher_exits(tmp_path: Path) -> None:
    child_code = (
        "import os,signal,subprocess,sys,time\n"
        "grandchild_code='import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'\n"
        "grandchild=subprocess.Popen([sys.executable,'-c',grandchild_code])\n"
        "print(f'{os.getpgrp()} {grandchild.pid}', flush=True)\n"
        "time.sleep(30)\n"
    )
    launcher = subprocess.Popen(
        _launcher_with_test_lock(
            tmp_path / "gpu.lock",
            "--gpu",
            "--",
            sys.executable,
            "-c",
            child_code,
        ),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    process_group = None
    grandchild_pid = None
    try:
        assert launcher.stdout is not None
        process_group, grandchild_pid = map(int, _read_line(launcher.stdout).split())
        launcher.send_signal(signal.SIGTERM)
        _, error = launcher.communicate(timeout=5)
        assert launcher.returncode == 128 + signal.SIGTERM, error
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            states = [_process_state(pid) for pid in (process_group, grandchild_pid)]
            if all(state is None or state == "Z" for state in states):
                break
            time.sleep(0.02)
        assert all(
            state is None or state == "Z"
            for state in (_process_state(process_group), _process_state(grandchild_pid))
        )
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.communicate(timeout=2)
        if process_group is not None:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
