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
    """Use the full detected CPU budget unless the caller sets a smaller one."""
    count = max(1, effective_cpu_count() if cpu_count is None else cpu_count)
    return count


def gpu_lock_path() -> Path:
    """Return a per-user lock path shared by this project's local invocations."""
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    return Path("/tmp") / f"fire-track2-gpu-{uid}.lock"


@contextmanager
def gpu_lock(lock_path: Path | None = None) -> Iterator[None]:
    if fcntl is None:
        raise RuntimeError("--gpu serialization requires Linux fcntl.flock support")
    path = lock_path if lock_path is not None else gpu_lock_path()
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
    parser.add_argument(
        "--source-supervisor",
        metavar="CONFIG.json",
        help="run one source Docker case under the H7 lifecycle supervisor (requires --gpu)",
    )
    parser.add_argument("--source-guardian", metavar="CONFIG.json", help=argparse.SUPPRESS)
    parser.add_argument("--source-lock-path", metavar="PATH", help=argparse.SUPPRESS)
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
    if args.source_supervisor is not None and not args.gpu:
        parser.error("--source-supervisor requires --gpu")
    if args.source_supervisor is not None and args.timeout is not None:
        parser.error("--source-supervisor owns its wall limit; omit --timeout")
    if args.source_guardian is not None and not args.gpu:
        parser.error("internal source guardian requires --gpu")
    if args.source_guardian is not None and args.timeout is not None:
        parser.error("internal source guardian owns its wall limit; omit --timeout")
    if args.source_guardian is not None and args.source_supervisor is not None:
        parser.error("--source-guardian and --source-supervisor are mutually exclusive")
    if args.source_lock_path is not None and args.source_guardian is None:
        parser.error("--source-lock-path is reserved for the internal source guardian")
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


def run(
    command: list[str],
    *,
    threads: int,
    gpu: bool,
    timeout: float | None,
    source_supervisor: str | None = None,
    source_guardian: str | None = None,
    source_lock_path: str | None = None,
) -> int:
    environment = _command_environment(threads)
    print(f"[run_local] thread limit: {threads}", file=sys.stderr, flush=True)
    if source_supervisor is not None and (not gpu or timeout is not None):
        print(
            "[run_local] source supervisor requires --gpu and owns its wall timeout",
            file=sys.stderr,
        )
        return 2
    if source_guardian is not None and (not gpu or timeout is not None):
        print(
            "[run_local] internal source guardian requires --gpu and owns its wall timeout",
            file=sys.stderr,
        )
        return 2

    if source_guardian is not None:
        queued_signals: list[int] = []

        def queue_guardian_signal(signum: int, frame: object) -> None:
            del frame
            queued_signals.append(signum)

        previous_handlers = {
            signum: signal.signal(signum, queue_guardian_signal)
            for signum in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            from flutas_source_supervisor import run_from_config

            environment["FLUTAS_SOURCE_LOCK_OWNER_PID"] = str(os.getpid())
            os.environ["FLUTAS_SOURCE_LOCK_OWNER_PID"] = str(os.getpid())
            lock_path = Path(source_lock_path) if source_lock_path is not None else gpu_lock_path()
            with gpu_lock(lock_path):
                return run_from_config(
                    Path(source_guardian), command, environment, initial_signals=queued_signals
                )
        except (OSError, ValueError) as error:
            print(f"[run_local] source guardian configuration failed: {error}", file=sys.stderr)
            return 2
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)

    lock_context = gpu_lock() if gpu else nullcontext()
    if source_supervisor is not None:
        guardian: subprocess.Popen[bytes] | None = None
        queued_signals: list[int] = []

        def forward_guardian_signal(signum: int, frame: object) -> None:
            del frame
            queued_signals.append(signum)
            if guardian is not None:
                try:
                    guardian.send_signal(signum)
                except ProcessLookupError:
                    pass

        previous_handlers = {
            signum: signal.signal(signum, forward_guardian_signal)
            for signum in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            guardian_environment = environment.copy()
            guardian_environment["FLUTAS_SOURCE_LAUNCHER_PID"] = str(os.getpid())
            argv = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--gpu",
                "--threads",
                str(threads),
                "--source-guardian",
                source_supervisor,
                "--source-lock-path",
                str(gpu_lock_path()),
                "--",
                *command,
            ]
            guardian = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=guardian_environment,
                close_fds=True,
                start_new_session=True,
            )
            pending_at_spawn = tuple(queued_signals)
            queued_signals.clear()
            for requested_signal in pending_at_spawn:
                try:
                    guardian.send_signal(requested_signal)
                except ProcessLookupError:
                    pass
            print(
                f"[run_local] source lock guardian pid={guardian.pid}; detached from launcher",
                file=sys.stderr,
                flush=True,
            )
            return_code = guardian.wait()
            return return_code if return_code >= 0 else 128 - return_code
        except OSError as error:
            print(f"[run_local] cannot start source lock guardian: {error}", file=sys.stderr)
            return 127
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)

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
    return run(
        command,
        threads=threads,
        gpu=args.gpu,
        timeout=args.timeout,
        source_supervisor=args.source_supervisor,
        source_guardian=args.source_guardian,
        source_lock_path=args.source_lock_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
