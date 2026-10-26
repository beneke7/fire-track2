#!/usr/bin/env python3
"""Stream OpenFOAM I4F logs into per-step timing and linear-solver profiles.

The log's cumulative ExecutionTime/ClockTime counters only provide global
process timing. This tool intentionally does not turn linear iteration counts
into estimated wall-time shares.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TIME_RE = re.compile(rf"^Time\s*=\s*({FLOAT})")
CREATE_MESH_TIME_RE = re.compile(rf"^Create mesh for time\s*=\s*({FLOAT})")
TIMER_RE = re.compile(rf"ExecutionTime\s*=\s*({FLOAT})\s*s\s+ClockTime\s*=\s*({FLOAT})\s*s")
PIMPLE_RE = re.compile(r"^PIMPLE:\s*iteration\s+(\d+)")
SOLVE_RE = re.compile(r"^([A-Za-z0-9_]+):\s+Solving for\s+([^,]+),.*?No Iterations\s*=?\s*(\d+)")
MPI_PREFIXES = (
    re.compile(r"^\s*\[(?:rank\s*)?\d+\]\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:rank\s*)?\d+\s*:\s*", re.IGNORECASE),
)
POUT_RE = re.compile(r"(?:^|\s)(?:Pout|I4F_[A-Za-z0-9_]*POUT)\b", re.IGNORECASE)
FATAL_RE = re.compile(r"\bFOAM FATAL(?: IO)? ERROR\b|\bFOAM ABORT\b", re.IGNORECASE)
DIAGNOSTIC_TAGS = (
    "I4F_PRESSURE_RESIDUAL",
    "I4F_PRESSURE_OPERATOR_DEFECT",
    "I4F_PHASE_MASS_STATE",
    "I4F_OUTER_STATE_DELTA",
    "I4F_TERMINAL_CHECKPOINT_REQUEST",
)


def normalize_mpi_prefix(line: str) -> str:
    """Remove common merged-stdout MPI rank prefixes before parsing records."""
    normalized = line
    for pattern in MPI_PREFIXES:
        normalized = pattern.sub("", normalized, count=1)
    return normalized.rstrip("\r\n")


@dataclass
class Step:
    segment: int
    index: int
    time_s: float | None
    delta_t_s: float | None
    outer_iterations: int = 0
    solves_by_field: Counter[str] = field(default_factory=Counter)
    iterations_by_field: Counter[str] = field(default_factory=Counter)
    solves_by_solver_field: Counter[str] = field(default_factory=Counter)
    iterations_by_solver_field: Counter[str] = field(default_factory=Counter)
    execution_time_cumulative_s: float | None = None
    clock_time_cumulative_s: float | None = None
    execution_interval_s: float | None = None
    clock_interval_s: float | None = None
    first_timer_in_segment: bool = False
    timer_reset: bool = False

    def as_record(self) -> dict[str, object]:
        return {
            "segment": self.segment,
            "step": self.index,
            "time_s": self.time_s,
            "delta_t_s": self.delta_t_s,
            "outer_iterations": self.outer_iterations,
            "solves_by_field": dict(sorted(self.solves_by_field.items())),
            "iterations_by_field": dict(sorted(self.iterations_by_field.items())),
            "solves_by_solver_field": dict(sorted(self.solves_by_solver_field.items())),
            "iterations_by_solver_field": dict(sorted(self.iterations_by_solver_field.items())),
            "execution_time_cumulative_s": self.execution_time_cumulative_s,
            "clock_time_cumulative_s": self.clock_time_cumulative_s,
            "execution_interval_s": self.execution_interval_s,
            "clock_interval_s": self.clock_interval_s,
            "first_timer_in_segment": self.first_timer_in_segment,
            "timer_reset": self.timer_reset,
        }


def _finish_step(step: Step | None, output: list[Step]) -> None:
    if step is not None:
        output.append(step)


def parse_lines(lines: Iterable[str]) -> tuple[list[Step], dict[str, object]]:
    """Parse a streamed solver log, retaining timer epochs and solver counts."""
    steps: list[Step] = []
    current: Step | None = None
    segment = 0
    step_index = 0
    segment_start_time: float | None = None
    previous_time: float | None = None
    previous_execution: float | None = None
    previous_clock: float | None = None
    counters: Counter[str] = Counter(
        {
            "pout_records": 0,
            "trapfpe_banner_lines": 0,
            "foam_fatal_lines": 0,
            "end_markers": 0,
            "time_markers": 0,
        }
    )
    diagnostic_bytes: Counter[str] = Counter()

    for raw_line in lines:
        line_bytes = len(raw_line.encode("utf-8", errors="replace"))
        line = normalize_mpi_prefix(raw_line).strip()
        if not line:
            continue

        if CREATE_MESH_TIME_RE.match(line):
            _finish_step(current, steps)
            current = None
            segment += 1
            segment_start_time = float(CREATE_MESH_TIME_RE.match(line).group(1))  # type: ignore[union-attr]
            previous_time = None
            previous_execution = None
            previous_clock = None
            counters["restart_or_create_mesh_boundaries"] += 1

        for tag in DIAGNOSTIC_TAGS:
            if tag in line:
                counters[f"tag:{tag}"] += 1
                diagnostic_bytes[tag] += line_bytes

        if POUT_RE.search(line):
            counters["pout_records"] += 1
        if "trapFpe:" in line or "FOAM_SIGFPE" in line:
            counters["trapfpe_banner_lines"] += 1
        if FATAL_RE.search(line):
            counters["foam_fatal_lines"] += 1
        if line == "End":
            counters["end_markers"] += 1

        time_match = TIME_RE.match(line)
        if time_match:
            time_s = float(time_match.group(1))
            if segment == 0:
                segment = 1
            if previous_time is not None and time_s <= previous_time:
                _finish_step(current, steps)
                current = None
                segment += 1
                previous_time = None
                previous_execution = None
                previous_clock = None
                counters["time_reset_boundaries"] += 1
            _finish_step(current, steps)
            step_index += 1
            delta_t = None
            prior_time = previous_time if previous_time is not None else segment_start_time
            if prior_time is not None:
                delta_t = time_s - prior_time
            current = Step(
                segment=segment,
                index=step_index,
                time_s=time_s,
                delta_t_s=delta_t,
            )
            previous_time = time_s
            segment_start_time = None
            counters["time_markers"] += 1
            continue

        if current is None:
            continue

        pimple_match = PIMPLE_RE.match(line)
        if pimple_match:
            current.outer_iterations += 1
            continue

        solve_match = SOLVE_RE.match(line)
        if solve_match:
            solver, field_name, iteration_text = solve_match.groups()
            field_name = field_name.strip()
            iterations = int(iteration_text)
            key = f"{solver}:{field_name}"
            current.solves_by_field[field_name] += 1
            current.iterations_by_field[field_name] += iterations
            current.solves_by_solver_field[key] += 1
            current.iterations_by_solver_field[key] += iterations
            counters["linear_solve_lines"] += 1
            continue

        timer_match = TIMER_RE.search(line)
        if timer_match:
            execution = float(timer_match.group(1))
            clock = float(timer_match.group(2))
            reset = (previous_execution is not None and execution < previous_execution) or (
                previous_clock is not None and clock < previous_clock
            )
            if reset:
                segment += 1
                current.segment = segment
                previous_execution = None
                previous_clock = None
                counters["timer_reset_boundaries"] += 1
            current.execution_time_cumulative_s = execution
            current.clock_time_cumulative_s = clock
            current.first_timer_in_segment = previous_execution is None
            current.timer_reset = reset
            if previous_execution is not None:
                current.execution_interval_s = execution - previous_execution
                current.clock_interval_s = clock - previous_clock  # type: ignore[operator]
            previous_execution = execution
            previous_clock = clock
            counters["timer_records"] += 1
            _finish_step(current, steps)
            current = None

    _finish_step(current, steps)
    counters["steps_with_timer"] = sum(
        step.execution_time_cumulative_s is not None for step in steps
    )
    counters["steps_with_clock_interval"] = sum(step.clock_interval_s is not None for step in steps)
    counters["steps_with_execution_interval"] = sum(
        step.execution_interval_s is not None for step in steps
    )
    metadata: dict[str, object] = {
        "counters": dict(sorted(counters.items())),
        "diagnostic_record_bytes": dict(sorted(diagnostic_bytes.items())),
    }
    return steps, metadata


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _statistics(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p90": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "min": min(values),
        "max": max(values),
    }


def _case_metadata(log_path: Path) -> dict[str, object]:
    case_dir = log_path.parent
    bundle_dir = case_dir.parent if case_dir.name == "case" else case_dir
    metadata: dict[str, object] = {
        "case_dir": str(case_dir),
        "bundle_dir": str(bundle_dir),
    }
    lock_path = bundle_dir / "provenance" / "run-source-lock.json"
    if lock_path.is_file():
        lock_bytes = lock_path.read_bytes()
        lock = json.loads(lock_bytes)
        metadata["source_lock"] = {
            "path": str(lock_path),
            "sha256": hashlib.sha256(lock_bytes).hexdigest(),
            "binary_sha256": lock.get("binary_sha256", lock.get("source_binary_sha256")),
            "binary_source_sha256": lock.get(
                "source_binary_sha256", lock.get("source_binary_expected_sha256")
            ),
            "image": lock.get("image", lock.get("openfoam_image")),
            "case_static_tree_sha256": lock.get("case_static_tree_sha256"),
            "schema": lock.get("schema"),
        }
    fv_solution = case_dir / "system" / "fvSolution"
    if fv_solution.is_file():
        text = fv_solution.read_text(encoding="utf-8", errors="replace")
        pimple = re.search(r"PIMPLE\s*\{([^}]*)\}", text, re.DOTALL)
        if pimple:
            block = pimple.group(1)
            metadata["pimple"] = {
                key: (int(value) if key != "transonic" else value.lower() == "yes")
                for key, value in re.findall(
                    r"\b(nOuterCorrectors|nCorrectors|nNonOrthogonalCorrectors|transonic)\s+([^;]+);",
                    block,
                )
            }
    control_dict = case_dir / "system" / "controlDict"
    if control_dict.is_file():
        text = control_dict.read_text(encoding="utf-8", errors="replace")
        settings = dict(
            re.findall(
                r"^\s*(writeInterval|deltaT|maxDeltaT|maxCo|maxAlphaCo|writeFormat|fileHandler)\s+([^;]+);",
                text,
                re.MULTILINE,
            )
        )
        if settings:
            metadata["control"] = settings
    return metadata


def _profile_log(path: Path) -> dict[str, object]:
    hasher = hashlib.sha256()
    byte_count = 0
    initial_stat = path.stat()
    snapshot_size = initial_stat.st_size
    snapshot_ends_with_newline = True

    def decoded_lines() -> Iterable[str]:
        nonlocal byte_count, snapshot_ends_with_newline
        remaining = snapshot_size
        with path.open("rb") as source:
            while remaining > 0:
                raw = source.readline(remaining)
                if not raw:
                    break
                hasher.update(raw)
                byte_count += len(raw)
                remaining -= len(raw)
                snapshot_ends_with_newline = (
                    raw.endswith(b"\n") if remaining == 0 else snapshot_ends_with_newline
                )
                yield raw.decode("utf-8", errors="replace")

    steps, parse_metadata = parse_lines(decoded_lines())
    final_stat = path.stat()
    aggregate_solves: Counter[str] = Counter()
    aggregate_iterations: Counter[str] = Counter()
    for step in steps:
        aggregate_solves.update(step.solves_by_solver_field)
        aggregate_iterations.update(step.iterations_by_solver_field)

    execution_intervals = [
        step.execution_interval_s for step in steps if step.execution_interval_s is not None
    ]
    clock_intervals = [step.clock_interval_s for step in steps if step.clock_interval_s is not None]
    physical_deltas = [step.delta_t_s for step in steps if step.delta_t_s is not None]
    outer_counts = [float(step.outer_iterations) for step in steps]
    p_iterations = [
        float(step.iterations_by_field["p_rgh"])
        for step in steps
        if "p_rgh" in step.iterations_by_field
    ]
    timed_physical = sum(
        step.delta_t_s or 0.0 for step in steps if step.clock_interval_s is not None
    )
    timed_clock = sum(clock_intervals)
    solve_counts_per_step: dict[str, list[float]] = defaultdict(list)
    iteration_counts_per_step: dict[str, list[float]] = defaultdict(list)
    for step in steps:
        for key, count in step.solves_by_solver_field.items():
            solve_counts_per_step[key].append(float(count))
        for key, count in step.iterations_by_solver_field.items():
            iteration_counts_per_step[key].append(float(count))
    first = next((step.time_s for step in steps if step.time_s is not None), None)
    last = next((step.time_s for step in reversed(steps) if step.time_s is not None), None)

    return {
        "input": {
            "path": str(path),
            "bytes": byte_count,
            "snapshot_size_bytes": snapshot_size,
            "snapshot_ends_with_newline": snapshot_ends_with_newline,
            "file_size_changed_during_profile": final_stat.st_size != snapshot_size,
            "sha256": hasher.hexdigest(),
            "mtime_utc_stat_only": datetime.fromtimestamp(initial_stat.st_mtime, UTC).isoformat(),
        },
        "case": _case_metadata(path),
        "parse": parse_metadata,
        "steps": [step.as_record() for step in steps],
        "summary": {
            "step_count": len(steps),
            "time_marker_count": parse_metadata["counters"].get("time_markers", 0),
            "physical_time_first_s": first,
            "physical_time_last_s": last,
            "physical_time_span_s": (last - first)
            if first is not None and last is not None
            else None,
            "physical_delta_t_s": _statistics(physical_deltas),
            "outer_iterations_per_step": _statistics(outer_counts),
            "p_rgh_linear_iterations_per_step": _statistics(p_iterations),
            "execution_time_cpu_intervals_s": _statistics(execution_intervals),
            "clock_time_intervals_s": _statistics(clock_intervals),
            "wall_clock_s_per_timed_physical_s": (
                timed_clock / timed_physical if timed_physical > 0 else None
            ),
            "linear_solve_calls_per_step_by_solver_field": {
                key: _statistics(values) for key, values in sorted(solve_counts_per_step.items())
            },
            "linear_iterations_per_step_by_solver_field": {
                key: _statistics(values)
                for key, values in sorted(iteration_counts_per_step.items())
            },
            "linear_solve_calls_by_solver_field": dict(sorted(aggregate_solves.items())),
            "linear_iterations_by_solver_field": dict(sorted(aggregate_iterations.items())),
            "timing_scope": (
                "OpenFOAM ExecutionTime CPU counter for the process that emits the "
                "merged Info stream, plus its cumulative ClockTime wall counter; "
                "ExecutionTime is not the sum across MPI ranks, and neither counter "
                "is a per-equation timer or a partition of wall-time among solvers. "
                "First timer in each process segment is excluded from intervals because "
                "it includes startup and has no prior marker."
            ),
        },
    }


def _write_steps_csv(path: Path, steps: list[dict[str, object]]) -> None:
    columns = (
        "segment",
        "step",
        "time_s",
        "delta_t_s",
        "outer_iterations",
        "execution_time_cumulative_s",
        "clock_time_cumulative_s",
        "execution_interval_s",
        "clock_interval_s",
        "first_timer_in_segment",
        "timer_reset",
        "solves_by_field_json",
        "iterations_by_field_json",
        "solves_by_solver_field_json",
        "iterations_by_solver_field_json",
    )
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for record in steps:
            row = {key: record.get(key) for key in columns}
            for key in (
                "solves_by_field",
                "iterations_by_field",
                "solves_by_solver_field",
                "iterations_by_solver_field",
            ):
                row[f"{key}_json"] = json.dumps(record.get(key, {}), sort_keys=True)
            writer.writerow(row)


def profile_logs(paths: list[Path], output_dir: Path) -> dict[str, object]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    profiles = []
    for path in paths:
        profile = _profile_log(path)
        path_token = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:8]
        csv_path = output_dir / f"{path_token}-steps.csv"
        _write_steps_csv(csv_path, profile["steps"])
        profile["steps_csv"] = str(csv_path)
        del profile["steps"]
        profiles.append(profile)
    report = {
        "schema": "i4f-runtime-profile/v1",
        "generated_utc": datetime.now(UTC).isoformat(),
        "tool": str(Path(__file__).resolve()),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timer_semantics": {
            "execution_time": (
                "In the pinned OpenCFD OpenFOAM v2512 image, Time::printExecutionTime "
                "prints elapsedCpuTime(); the POSIX cpuTime backend uses tms user+system "
                "ticks for the calling process. This is one process counter, not an MPI sum."
            ),
            "clock_time": "Time::printExecutionTime prints elapsedClockTime() for that process/run.",
            "source_paths": [
                "/usr/lib/openfoam/openfoam2512/src/OpenFOAM/db/Time/TimeIO.C",
                "/usr/lib/openfoam/openfoam2512/src/OSspecific/POSIX/cpuTime/cpuTimePosix.C",
            ],
            "clock_time_resolution_observed_s": 1.0,
        },
        "profiles": profiles,
        "interpretation_limits": [
            "Linear iteration counts describe work volume, not measured per-solver wall-time share.",
            "ExecutionTime/ClockTime report aggregate process timing only; output-function and checkpoint I/O are not separately timed by this parser.",
            "A trapFpe/FOAM_SIGFPE startup banner is recorded as a banner, not treated as a solver failure.",
        ],
    }
    (output_dir / "profile-summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path, help="new output directory")
    parser.add_argument("logs", nargs="+", type=Path, help="OpenFOAM merged stdout logs")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for path in args.logs:
        if not path.is_file():
            raise SystemExit(f"log not found: {path}")
    report = profile_logs(args.logs, args.out_dir)
    for profile in report["profiles"]:
        summary = profile["summary"]
        print(
            f"{profile['input']['path']}: steps={summary['step_count']} "
            f"timed_clock_intervals={summary['clock_time_intervals_s']['count']} "
            f"mean_clock_interval_s={summary['clock_time_intervals_s']['mean']} "
            f"p_rgh_iterations_per_step={summary['p_rgh_linear_iterations_per_step']['mean']}"
        )
    print(f"wrote {args.out_dir / 'profile-summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
