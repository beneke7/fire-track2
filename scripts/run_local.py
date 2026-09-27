#!/usr/bin/env python3
"""Run a local command with a bounded thread count and optional GPU lock."""

from __future__ import annotations

import argparse
import math
import os
import signal
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - this project targets Linux compute hosts.
    fcntl = None  # type: ignore[assignment]

from doctor import effective_cpu_count

THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OMP_THREAD_LIMIT",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def default_threads(cpu_count: int | None = None) -> int:
    """Use the available budget while reserving two CPUs when possible."""
    count = max(1, effective_cpu_count() if cpu_count is None else cpu_count)
    return max(1, count - 2)


def gpu_lock_path() -> Path:
    """Return a per-user lock path shared by this project's local invocations."""
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    return Path("/tmp") / f"fire-track2-gpu-{uid}.lock"


@contextmanager
def gpu_lock() -> Iterator[None]:
    if fcntl is None:
        raise RuntimeError("--gpu serialization requires Linux fcntl.flock support")
    path = gpu_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "r+") as lock_file:
        print(f"[run_local] waiting for GPU lock: {path}", file=sys.stderr, flush=True)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number of seconds") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return seconds


def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=__doc__,
        usage="%(prog)s [--threads N] [--gpu] [--timeout SECONDS] -- COMMAND ARGS",
    )
    parser.add_argument("--threads", type=int, help="maximum threads for common BLAS/OMP runtimes")
    parser.add_argument(
        "--gpu", action="store_true", help="serialize this command with other local GPU jobs"
    )
    parser.add_argument(
        "--timeout", type=_positive_seconds, help="stop the command after this many seconds"
    )
    if "--" not in argv:
        parser.parse_args(argv)
        parser.error("include `--` before the command")
    separator = argv.index("--")
    args = parser.parse_args(argv[:separator])
    command = argv[separator + 1 :]
    if not command:
        parser.error("a command is required after `--`")
    if args.threads is not None and args.threads < 1:
        parser.error("--threads must be at least 1")
    return args, command


def _command_environment(threads: int) -> dict[str, str]:
    environment = os.environ.copy()
    for name in THREAD_ENV_VARS:
        environment[name] = str(threads)
    environment["OMP_DYNAMIC"] = "FALSE"
    return environment


def _stop_process_group(process: subprocess.Popen[bytes], first_signal: int) -> None:
    """Stop a command and any children it started, even if the parent exits first."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, first_signal)
        else:  # pragma: no cover - local compute tooling targets Linux.
            process.send_signal(first_signal)
    except ProcessLookupError:
        pass
    except OSError:
        pass

    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:  # pragma: no cover - local compute tooling targets Linux.
            process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        pass
    if process.poll() is None:
        process.wait()


class _TerminationRequested(Exception):
    def __init__(self, signum: int):
        self.signum = signum


def _handle_termination(signum: int, frame: object) -> None:
    del frame
    raise _TerminationRequested(signum)


def run(command: list[str], *, threads: int, gpu: bool, timeout: float | None) -> int:
    environment = _command_environment(threads)
    print(f"[run_local] thread limit: {threads}", file=sys.stderr, flush=True)
    lock_context = gpu_lock() if gpu else nullcontext()
    process: subprocess.Popen[bytes] | None = None
    previous_sigterm = signal.signal(signal.SIGTERM, _handle_termination)
    try:
        try:
            with lock_context:
                try:
                    process = subprocess.Popen(
                        command, env=environment, start_new_session=os.name == "posix"
                    )
                    return_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    assert process is not None
                    _stop_process_group(process, signal.SIGTERM)
                    print(
                        f"[run_local] command timed out after {timeout:g} seconds",
                        file=sys.stderr,
                    )
                    return 124
                except _TerminationRequested as requested:
                    if process is not None:
                        _stop_process_group(process, signal.SIGTERM)
                    return 128 + requested.signum
                except KeyboardInterrupt:
                    if process is not None:
                        _stop_process_group(process, signal.SIGINT)
                    return 130
        except _TerminationRequested as requested:
            return 128 + requested.signum
        except KeyboardInterrupt:
            return 130
        except FileNotFoundError:
            print(f"[run_local] command not found: {command[0]}", file=sys.stderr)
            return 127
        except PermissionError:
            print(f"[run_local] cannot execute command: {command[0]}", file=sys.stderr)
            return 126
        except RuntimeError as error:
            print(f"[run_local] {error}", file=sys.stderr)
            return 2
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)

    return return_code if return_code >= 0 else 128 - return_code


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args, command = _parse_args(arguments)
    available = max(1, effective_cpu_count())
    requested = args.threads if args.threads is not None else default_threads(available)
    threads = min(requested, available)
    if threads != requested:
        print(
            f"[run_local] limiting requested {requested} threads to the detected budget of {available}",
            file=sys.stderr,
        )
    return run(command, threads=threads, gpu=args.gpu, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
