#!/usr/bin/env python3
"""Summarize OpenFOAM CPU scaling logs and optional Slurm accounting."""

from __future__ import annotations

import argparse
import contextlib
import csv
import importlib
import io
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+-]?(?:nan|inf(?:inity)?)"
TIME_RE = re.compile(rf"^\s*Time\s*=\s*({NUMBER})\s*$", re.IGNORECASE)
DELTA_T_RE = re.compile(rf"\bdeltaT\s*=\s*({NUMBER})", re.IGNORECASE)
COURANT_RE = re.compile(
    rf"^\s*(Interface\s+)?Courant Number\s+mean:\s*({NUMBER})\s+max:\s*({NUMBER})",
    re.IGNORECASE,
)
SOLVE_RE = re.compile(
    rf"Solving for\s+([^,]+),\s*Initial residual\s*=\s*({NUMBER}),\s*"
    rf"Final residual\s*=\s*({NUMBER}),\s*No Iterations\s+(\d+)",
    re.IGNORECASE,
)
ALPHA_RE = re.compile(rf"Min/max\s+([^\s=]+)\s*=\s*({NUMBER})\s+({NUMBER})", re.IGNORECASE)
ALPHA_EXTREMA_RE = re.compile(
    rf"Min\((?P<field>[^)]+)\)\s*=\s*(?P<minimum>{NUMBER}).*?"
    rf"Max\(\s*(?P=field)\s*\)\s*=\s*(?P<maximum>{NUMBER})",
    re.IGNORECASE,
)
VOLUME_FRACTION_RE = re.compile(
    rf"(?:(?P<label>[\w.-]+)\s+)?volume[ _]fraction\s*[:=]\s*(?P<value>{NUMBER})",
    re.IGNORECASE,
)
EXECUTION_RE = re.compile(rf"\bExecutionTime\s*=\s*({NUMBER})\s*s", re.IGNORECASE)
CLOCK_RE = re.compile(rf"\bClockTime\s*=\s*({NUMBER})\s*s", re.IGNORECASE)
LAUNCHER_WALL_RE = re.compile(rf"^\s*solver_wall_s\s*=\s*({NUMBER})\s*$", re.IGNORECASE)
LAUNCHER_EXIT_RE = re.compile(r"^\s*solver_exit_code\s*=\s*(-?\d+)\s*$", re.IGNORECASE)
NONFINITE_RE = re.compile(r"\b(?:nan|[+-]?inf(?:inity)?)\b", re.IGNORECASE)
FATAL_RE = re.compile(
    r"FOAM FATAL|\bfloating point exception\b(?!\s+trapping enabled)|\bMPI_ABORT\b|"
    r"\bsegmentation fault\b|"
    r"\bAborted\b|terminate called after throwing",
    re.IGNORECASE,
)
# shortcut: detect explicit failure/non-finite markers only; add solver-specific residual limits when declared.
DIVERGENCE_RE = re.compile(r"diverg(?:ence|ed)|non[- ]finite", re.IGNORECASE)
TIME_MATCH_TOLERANCE_S = 1e-12
MAX_DIAGNOSTICS = 10


def _finite_number(raw: str, kind: str, line: str, diagnostics: list[str]) -> float | None:
    value = float(raw)
    if math.isfinite(value):
        return value
    diagnostics.append(f"non-finite {kind}: {line.strip()[:240]}")
    return None


def _series(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "last": None}
    return {"min": min(values), "max": max(values), "last": values[-1]}


def _paired_series(
    values: list[tuple[float, float]], labels: tuple[str, str] = ("min", "max")
) -> dict[str, dict[str, float | None]]:
    if not values:
        return {label: _series([]) for label in labels}
    lows, highs = zip(*values, strict=True)
    return {labels[0]: _series(list(lows)), labels[1]: _series(list(highs))}


def parse_openfoam_log(path: Path) -> dict[str, Any]:
    """Extract timings and common interIsoFoam diagnostics without guessing missing data."""
    times: list[float] = []
    delta_ts: list[float] = []
    courant: dict[str, list[tuple[float, float]]] = {"bulk": [], "interface": []}
    residuals: dict[str, dict[str, Any]] = {}
    alpha: dict[str, list[tuple[float, float]]] = {}
    volume_fraction: dict[str, list[float]] = {}
    execution_times: list[float] = []
    clock_times: list[float] = []
    fatal_errors: list[str] = []
    divergence_markers: list[str] = []
    step_metrics: list[dict[str, Any]] = []
    current_step: dict[str, Any] | None = None
    saw_end = False

    with path.open(encoding="utf-8", errors="replace") as log:
        for line in log:
            stripped = line.strip()
            match = TIME_RE.match(line)
            if match:
                value = _finite_number(match.group(1), "simulation time", line, divergence_markers)
                if value is not None:
                    times.append(value)
                    current_step = {"step": len(step_metrics) + 1, "time_s": value}
                    step_metrics.append(current_step)

            match = DELTA_T_RE.search(line)
            if match:
                value = _finite_number(match.group(1), "deltaT", line, divergence_markers)
                if value is not None:
                    delta_ts.append(value)
                    if current_step is not None:
                        current_step["delta_t_s"] = value

            match = COURANT_RE.match(line)
            if match:
                values = (
                    _finite_number(match.group(2), "Courant number", line, divergence_markers),
                    _finite_number(match.group(3), "Courant maximum", line, divergence_markers),
                )
                if values[0] is not None and values[1] is not None:
                    kind = "interface" if match.group(1) else "bulk"
                    courant[kind].append((values[0], values[1]))
                    if current_step is not None:
                        prefix = "interface_courant" if kind == "interface" else "courant"
                        current_step[f"{prefix}_mean"] = values[0]
                        current_step[f"{prefix}_max"] = values[1]

            match = SOLVE_RE.search(line)
            if match:
                field = match.group(1).strip()
                initial = _finite_number(
                    match.group(2), "initial residual", line, divergence_markers
                )
                final = _finite_number(match.group(3), "final residual", line, divergence_markers)
                iterations = int(match.group(4))
                if initial is not None and final is not None:
                    record = residuals.setdefault(
                        field,
                        {
                            "solves": 0,
                            "initial_min": initial,
                            "initial_max": initial,
                            "final_min": final,
                            "final_max": final,
                            "last_initial": initial,
                            "last_final": final,
                            "iterations_total": 0,
                            "iterations_max": 0,
                        },
                    )
                    record["solves"] += 1
                    record["initial_min"] = min(record["initial_min"], initial)
                    record["initial_max"] = max(record["initial_max"], initial)
                    record["final_min"] = min(record["final_min"], final)
                    record["final_max"] = max(record["final_max"], final)
                    record["last_initial"] = initial
                    record["last_final"] = final
                    record["iterations_total"] += iterations
                    record["iterations_max"] = max(record["iterations_max"], iterations)
                    if current_step is not None and field in {"p", "p_rgh"}:
                        current_step["pressure_solve_iterations"] = (
                            current_step.get("pressure_solve_iterations", 0) + iterations
                        )
                        current_step["pressure_final_residual"] = final

            match = ALPHA_EXTREMA_RE.search(line)
            if match:
                field = match.group("field").strip()
                low = _finite_number(
                    match.group("minimum"), "alpha minimum", line, divergence_markers
                )
                high = _finite_number(
                    match.group("maximum"), "alpha maximum", line, divergence_markers
                )
            else:
                match = ALPHA_RE.search(line)
                field = match.group(1) if match else ""
                low = (
                    _finite_number(match.group(2), "alpha minimum", line, divergence_markers)
                    if match
                    else None
                )
                high = (
                    _finite_number(match.group(3), "alpha maximum", line, divergence_markers)
                    if match
                    else None
                )
            if match:
                if low is not None and high is not None:
                    alpha.setdefault(field, []).append((low, high))
                    if current_step is not None and field.startswith("alpha"):
                        current_step[f"{field}_min"] = low
                        current_step[f"{field}_max"] = high

            for match in VOLUME_FRACTION_RE.finditer(line):
                value = _finite_number(
                    match.group("value"), "volume fraction", line, divergence_markers
                )
                if value is not None:
                    volume_fraction.setdefault(match.group("label") or "overall", []).append(value)
                    if current_step is not None:
                        current_step["volume_fraction"] = value

            match = EXECUTION_RE.search(line)
            if match:
                value = _finite_number(match.group(1), "ExecutionTime", line, divergence_markers)
                if value is not None:
                    execution_times.append(value)
                    if current_step is not None:
                        current_step["execution_time_seconds"] = value
            match = CLOCK_RE.search(line)
            if match:
                value = _finite_number(match.group(1), "ClockTime", line, divergence_markers)
                if value is not None:
                    clock_times.append(value)
                    if current_step is not None:
                        current_step["clock_time_seconds"] = value

            if FATAL_RE.search(line):
                if stripped not in fatal_errors:
                    fatal_errors.append(stripped[:240])
            if DIVERGENCE_RE.search(line) or NONFINITE_RE.search(line):
                if stripped not in divergence_markers:
                    divergence_markers.append(stripped[:240])
            saw_end = saw_end or stripped == "End"

    fatal_errors = fatal_errors[:MAX_DIAGNOSTICS]
    divergence_markers = divergence_markers[:MAX_DIAGNOSTICS]
    step_count = len(times)
    start_time = times[0] if times else None
    reached_time = times[-1] if times else None
    physical_advance = reached_time - start_time if step_count > 1 else None
    for previous, current in zip(step_metrics, step_metrics[1:]):
        time_step = current["time_s"] - previous["time_s"]
        if time_step >= 0:
            current["physical_time_step_s"] = time_step
        for metric in ("execution_time_seconds", "clock_time_seconds"):
            if metric in previous and metric in current:
                difference = current[metric] - previous[metric]
                if difference >= 0:
                    current[metric.removesuffix("_seconds") + "_step_seconds"] = difference
        clock_step = current.get("clock_time_step_seconds")
        current["steps_per_clock_second_step"] = _divide(1, clock_step)
        current["physical_seconds_per_clock_second_step"] = _divide(
            current.get("physical_time_step_s"), clock_step
        )
    execution_seconds = execution_times[-1] if execution_times else None
    clock_seconds = clock_times[-1] if clock_times else None
    interval_execution = _paired_step_interval(step_metrics, "execution_time_seconds")
    interval_clock = _paired_step_interval(step_metrics, "clock_time_seconds")
    interval_steps = max(0, step_count - 1)
    timing = {
        "execution_time_seconds": execution_seconds,
        "clock_time_seconds": clock_seconds,
        "execution_time_interval_seconds": interval_execution,
        "clock_time_interval_seconds": interval_clock,
        "last_step_execution_seconds": step_metrics[-1].get("execution_time_step_seconds")
        if step_metrics
        else None,
        "last_step_clock_seconds": step_metrics[-1].get("clock_time_step_seconds")
        if step_metrics
        else None,
    }
    status = (
        "failed"
        if fatal_errors
        else "diverged"
        if divergence_markers
        else "completed"
        if saw_end
        else "incomplete"
    )
    pressure_fields = {
        name: item["iterations_total"] for name, item in residuals.items() if name in {"p", "p_rgh"}
    }
    pressure_iterations = sum(pressure_fields.values()) if pressure_fields else None
    return {
        "completion_status": status,
        "step_count": step_count,
        "physical_time_start_s": start_time,
        "physical_time_reached_s": reached_time,
        "physical_time_advanced_s": physical_advance,
        "delta_t_s": _series(delta_ts),
        "courant_number": _paired_series(courant["bulk"], ("mean", "max")),
        "interface_courant_number": _paired_series(courant["interface"], ("mean", "max")),
        "timing": timing,
        "throughput": {
            "steps_per_clock_second_interval": _divide(interval_steps, interval_clock),
            "physical_seconds_per_clock_second_interval": _divide(physical_advance, interval_clock),
        },
        "step_metrics": step_metrics,
        "residuals": residuals,
        "pressure_solve_iterations": {
            "fields": pressure_fields,
            "total": pressure_iterations,
        },
        "alpha_min_max": {name: _paired_series(values) for name, values in alpha.items()},
        "volume_fraction": {name: _series(values) for name, values in volume_fraction.items()},
        "fatal_errors": fatal_errors,
        "divergence_detected": bool(divergence_markers),
        "divergence_markers": divergence_markers,
    }


def _paired_step_interval(steps: list[dict[str, Any]], key: str) -> float | None:
    if len(steps) < 2 or key not in steps[0] or key not in steps[-1]:
        return None
    return steps[-1][key] - steps[0][key]


def _divide(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def _optional_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _slurm_seconds(raw: str | None) -> float | None:
    if not raw or raw in {"Unknown", "N/A", "UNLIMITED"}:
        return None
    try:
        day_count = 0
        time_part = raw
        if "-" in raw:
            days, time_part = raw.split("-", 1)
            day_count = int(days)
        fields = [float(field) for field in time_part.split(":")]
    except ValueError:
        return None
    if len(fields) == 3:
        hours, minutes, seconds = fields
    elif len(fields) == 2:
        hours, minutes, seconds = 0.0, fields[0], fields[1]
    elif len(fields) == 1:
        hours, minutes, seconds = 0.0, 0.0, fields[0]
    else:
        return None
    value = day_count * 86400 + hours * 3600 + minutes * 60 + seconds
    return value if math.isfinite(value) else None


def _rss_bytes(raw: str | None) -> int | None:
    if not raw:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGTPE]?)(?:i?B)?\s*", raw, re.IGNORECASE)
    if not match or not match.group(2):
        return None
    power = "kmgtpe".find(match.group(2).casefold()) + 1
    value = float(match.group(1)) * (1024**power)
    return int(value) if math.isfinite(value) else None


def parse_sacct(path: Path) -> dict[str, Any]:
    """Read one sacct --parsable2 row, preferring the parent job over step rows."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"empty sacct file: {path}")

    def cells(line: str) -> list[str]:
        return next(csv.reader([line], delimiter="|"))

    first = cells(lines[0])

    def normalize(value: str) -> str:
        return re.sub(r"[^a-z]", "", value.casefold())

    if "jobid" in {normalize(item) for item in first} or "jobidraw" in {
        normalize(item) for item in first
    }:
        header = [normalize(item) for item in first]
        data_lines = lines[1:]
    else:
        # shortcut: headerless input assumes the documented seven-field command in --help.
        header = ["jobid", "elapsed", "totalcpu", "alloccpus", "maxrss", "state", "exitcode"]
        data_lines = lines

    rows: list[dict[str, str]] = []
    for line in data_lines:
        values = cells(line)
        if len(values) != len(header):
            raise ValueError(f"sacct column count does not match its header in {path}")
        rows.append(dict(zip(header, values, strict=True)))
    parent_rows = [
        row
        for row in rows
        if (job_id := row.get("jobid", row.get("jobidraw", ""))) and "." not in job_id
    ]
    if len(parent_rows) != 1:
        raise ValueError(f"expected one top-level job row in sacct file: {path}")
    row = parent_rows[0]

    def field(*names: str) -> str | None:
        for name in names:
            value = row.get(name)
            if value and value not in {"Unknown", "N/A"}:
                return value
        return None

    elapsed = _slurm_seconds(field("elapsed"))
    if elapsed is None:
        elapsed = _optional_float(field("elapsedraw"))
    total_cpu = _slurm_seconds(field("totalcpu"))
    allocated = field("alloccpus", "ncpus")
    try:
        allocated_cpus = int(allocated) if allocated is not None else None
    except ValueError:
        allocated_cpus = None
    return {
        "job_id": field("jobid", "jobidraw"),
        "elapsed_seconds": elapsed,
        "total_cpu_seconds": total_cpu,
        "allocated_cpus": allocated_cpus,
        "parent_max_rss_bytes": _rss_bytes(field("maxrss")),
        "state": field("state"),
        "exit_code": field("exitcode"),
    }


def parse_launcher_log(path: Path) -> dict[str, int | float | None]:
    """Read the runner's high-resolution srun timing without conflating it with ClockTime."""
    if path.suffix.casefold() == ".json":
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError(f"runner state must be a JSON object: {path}")
        wall = _optional_float(str(state["solver_wall_s"])) if "solver_wall_s" in state else None
        try:
            exit_code = int(state["solver_exit_code"])
        except (KeyError, TypeError, ValueError):
            exit_code = None
        return {
            "solver_wall_seconds": wall if wall is not None and wall >= 0 else None,
            "solver_exit_code": exit_code,
        }

    solver_wall_seconds = None
    solver_exit_code = None
    with path.open(encoding="utf-8", errors="replace") as log:
        for line in log:
            match = LAUNCHER_WALL_RE.match(line)
            if match:
                value = _optional_float(match.group(1))
                solver_wall_seconds = value if value is not None and value >= 0 else None
            match = LAUNCHER_EXIT_RE.match(line)
            if match:
                solver_exit_code = int(match.group(1))
    return {
        "solver_wall_seconds": solver_wall_seconds,
        "solver_exit_code": solver_exit_code,
    }


def summarize_run(
    label: str,
    log_path: Path,
    ranks: int | None = None,
    sacct_path: Path | None = None,
    launcher_path: Path | None = None,
) -> dict[str, Any]:
    parsed = parse_openfoam_log(log_path)
    sacct = parse_sacct(sacct_path) if sacct_path else None
    launcher = parse_launcher_log(launcher_path) if launcher_path else None
    if sacct and _sacct_failed(sacct):
        parsed["completion_status"] = "failed"
    if launcher and launcher["solver_exit_code"] not in {None, 0}:
        parsed["completion_status"] = "failed"
    timing = parsed["timing"]
    launcher_wall = launcher["solver_wall_seconds"] if launcher else None
    solver_wall = launcher_wall if launcher_wall is not None else timing["clock_time_seconds"]
    solver_wall_source = (
        "launcher.solver_wall_s (srun envelope)"
        if launcher_wall is not None
        else "OpenFOAM.ClockTime"
        if timing["clock_time_seconds"] is not None
        else None
    )
    sacct_elapsed = sacct["elapsed_seconds"] if sacct else None
    allocated_cpus = sacct["allocated_cpus"] if sacct else None
    total_cpu = sacct["total_cpu_seconds"] if sacct else None
    resources = {
        "solver_wall_time_seconds": solver_wall,
        "solver_wall_time_source": solver_wall_source,
        "launcher_solver_wall_seconds": launcher_wall,
        "solver_clock_time_seconds": timing["clock_time_seconds"],
        "sacct_elapsed_seconds": sacct_elapsed,
        "solver_core_hours_estimate": _divide(solver_wall * ranks, 3600)
        if solver_wall is not None and ranks
        else None,
        "sacct_allocated_core_hours": (
            _divide(sacct_elapsed * allocated_cpus, 3600)
            if sacct_elapsed is not None and allocated_cpus
            else None
        ),
        "sacct_cpu_core_hours": _divide(total_cpu, 3600),
        "sacct_cpu_utilization": (
            _divide(total_cpu, sacct_elapsed * allocated_cpus)
            if total_cpu is not None and sacct_elapsed is not None and allocated_cpus
            else None
        ),
        "sacct_parent_max_rss_bytes": sacct["parent_max_rss_bytes"] if sacct else None,
    }
    return {
        "label": label,
        "log_path": str(log_path),
        "ranks": ranks,
        **parsed,
        "sacct": sacct,
        "launcher": launcher,
        "resources": resources,
    }


def _sacct_failed(sacct: dict[str, Any]) -> bool:
    state = sacct["state"]
    if state and state.split()[0].rstrip("+").upper() != "COMPLETED":
        return True
    exit_code = sacct["exit_code"]
    if exit_code:
        try:
            return int(exit_code.split(":", 1)[0]) != 0
        except ValueError:
            return False
    return False


def compare_runs(runs: list[dict[str, Any]], baseline_label: str) -> dict[str, Any]:
    by_label = {run["label"]: run for run in runs}
    baseline = by_label[baseline_label]
    common_reason: str | None = None
    if len(runs) < 2:
        common_reason = "strong scaling requires at least two runs"
    elif any(run["completion_status"] != "completed" for run in runs):
        common_reason = "all runs must complete without fatal or divergence markers"
    elif any(run["step_count"] <= 0 or run["ranks"] is None for run in runs):
        common_reason = "every run needs logged steps and an explicit positive rank count"
    elif any(run["ranks"] <= 0 for run in runs):
        common_reason = "rank counts must be positive"
    elif any(
        run["physical_time_start_s"] is None or run["physical_time_reached_s"] is None
        for run in runs
    ):
        common_reason = "every run needs a logged physical-time range"
    elif len({run["step_count"] for run in runs}) != 1:
        common_reason = "logged step counts differ across runs"
    elif any(
        not math.isclose(
            run["physical_time_start_s"],
            baseline["physical_time_start_s"],
            rel_tol=1e-9,
            abs_tol=TIME_MATCH_TOLERANCE_S,
        )
        or not math.isclose(
            run["physical_time_reached_s"],
            baseline["physical_time_reached_s"],
            rel_tol=1e-9,
            abs_tol=TIME_MATCH_TOLERANCE_S,
        )
        for run in runs
    ):
        common_reason = "physical-time start or horizon differs across runs"

    solver_reason = common_reason
    if solver_reason is None and any(
        run["resources"]["solver_wall_time_seconds"] is None for run in runs
    ):
        solver_reason = "every run needs launcher solver_wall_s or OpenFOAM ClockTime"
    elif (
        solver_reason is None
        and len({run["resources"]["solver_wall_time_source"] for run in runs}) != 1
    ):
        solver_reason = "solver wall-time sources differ across runs"
    elif solver_reason is None and any(
        run["resources"]["solver_wall_time_seconds"] <= 0 for run in runs
    ):
        solver_reason = "solver wall time must be positive"

    end_to_end_reason = common_reason
    if end_to_end_reason is None and any(
        run["resources"]["sacct_elapsed_seconds"] is None for run in runs
    ):
        end_to_end_reason = "all runs need sacct Elapsed for end-to-end scaling"
    elif end_to_end_reason is None and any(
        run["resources"]["sacct_elapsed_seconds"] <= 0 for run in runs
    ):
        end_to_end_reason = "sacct Elapsed must be positive"

    result: dict[str, Any] = {
        "baseline": baseline_label,
        "same_problem_assumed": True,
        "assumption": "inputs and numerical model match; parser checks completion, step count, and physical-time range only",
        "horizon_match_tolerance_s": TIME_MATCH_TOLERANCE_S,
        "eligible": solver_reason is None,
        "reason": solver_reason,
        "solver_time_source": (
            baseline["resources"]["solver_wall_time_source"]
            if len({run["resources"]["solver_wall_time_source"] for run in runs}) == 1
            else None
        ),
        "end_to_end_eligible": end_to_end_reason is None,
        "end_to_end_reason": end_to_end_reason,
        "end_to_end_time_source": "sacct.Elapsed" if end_to_end_reason is None else None,
        "runs": {},
    }
    for run in runs:
        solver_wall = run["resources"]["solver_wall_time_seconds"]
        job_elapsed = run["resources"]["sacct_elapsed_seconds"]
        rank_count = run["ranks"]
        comparison_row = {
            "ranks": rank_count,
            "solver_wall_time_seconds": solver_wall,
            "solver_core_hours_estimate": run["resources"]["solver_core_hours_estimate"],
            "solver_speedup": None,
            "solver_parallel_efficiency": None,
            "sacct_elapsed_seconds": job_elapsed,
            "sacct_allocated_core_hours": run["resources"]["sacct_allocated_core_hours"],
            "end_to_end_speedup": None,
            "end_to_end_parallel_efficiency": None,
        }
        if solver_reason is None and solver_wall is not None and rank_count is not None:
            base_solver_wall = baseline["resources"]["solver_wall_time_seconds"]
            solver_speedup = _divide(base_solver_wall, solver_wall)
            comparison_row["solver_speedup"] = solver_speedup
            comparison_row["solver_parallel_efficiency"] = (
                _divide(solver_speedup * baseline["ranks"], rank_count)
                if solver_speedup is not None
                else None
            )
        if end_to_end_reason is None and job_elapsed is not None and rank_count is not None:
            base_elapsed = baseline["resources"]["sacct_elapsed_seconds"]
            end_to_end_speedup = _divide(base_elapsed, job_elapsed)
            comparison_row["end_to_end_speedup"] = end_to_end_speedup
            comparison_row["end_to_end_parallel_efficiency"] = (
                _divide(end_to_end_speedup * baseline["ranks"], rank_count)
                if end_to_end_speedup is not None
                else None
            )
        result["runs"][run["label"]] = comparison_row
    return result


def _mapping(raw: str, description: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"{description} must use LABEL=VALUE: {raw}")
    label, value = raw.split("=", 1)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", label) or not value:
        raise ValueError(f"invalid {description}: {raw}")
    return label, value


def _wandb_metrics(report: dict[str, Any]) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    comparison = report.get("comparison")
    comparison_runs = comparison["runs"] if comparison else {}
    for run in report["runs"]:
        prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", run["label"])
        values = {
            "ranks": run["ranks"],
            "steps": run["step_count"],
            "physical_time_reached_s": run["physical_time_reached_s"],
            "solver_wall_time_seconds": run["resources"]["solver_wall_time_seconds"],
            "launcher_solver_wall_seconds": run["resources"]["launcher_solver_wall_seconds"],
            "solver_clock_time_seconds": run["resources"]["solver_clock_time_seconds"],
            "sacct_elapsed_seconds": run["resources"]["sacct_elapsed_seconds"],
            "steps_per_clock_second_interval": run["throughput"]["steps_per_clock_second_interval"],
            "physical_seconds_per_clock_second_interval": run["throughput"][
                "physical_seconds_per_clock_second_interval"
            ],
            "solver_core_hours_estimate": run["resources"]["solver_core_hours_estimate"],
            "sacct_allocated_core_hours": run["resources"]["sacct_allocated_core_hours"],
            "sacct_cpu_utilization": run["resources"]["sacct_cpu_utilization"],
            "sacct_parent_max_rss_bytes": run["resources"]["sacct_parent_max_rss_bytes"],
        }
        if run["label"] in comparison_runs:
            values.update(
                {
                    "solver_speedup": comparison_runs[run["label"]]["solver_speedup"],
                    "solver_parallel_efficiency": comparison_runs[run["label"]][
                        "solver_parallel_efficiency"
                    ],
                    "end_to_end_speedup": comparison_runs[run["label"]]["end_to_end_speedup"],
                    "end_to_end_parallel_efficiency": comparison_runs[run["label"]][
                        "end_to_end_parallel_efficiency"
                    ],
                }
            )
        metrics.update(
            {
                f"{prefix}/{name}": value
                for name, value in values.items()
                if isinstance(value, (int, float)) and math.isfinite(value)
            }
        )
    return metrics


def upload_wandb(report: dict[str, Any], project: str, entity: str | None) -> None:
    """Upload scalar metrics only; import W&B and allow network access only on opt-in."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            wandb = importlib.import_module("wandb")
            run = wandb.init(
                project=project,
                entity=entity,
                config={
                    "baseline": report.get("comparison", {}).get("baseline"),
                    "run_labels": [item["label"] for item in report["runs"]],
                    "solver_wall_time_sources": {
                        item["label"]: item["resources"]["solver_wall_time_source"]
                        for item in report["runs"]
                    },
                },
            )
            if run is None:
                raise RuntimeError("W&B did not create a run")
            try:
                record_index = 0
                for item in report["runs"]:
                    prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", item["label"])
                    for step in item["step_metrics"]:
                        values = {
                            "record_index": record_index,
                            "time_s": step.get("time_s"),
                            "delta_t_s": step.get("delta_t_s"),
                            "clock_time_seconds": step.get("clock_time_seconds"),
                            "clock_time_step_seconds": step.get("clock_time_step_seconds"),
                            "execution_time_step_seconds": step.get("execution_time_step_seconds"),
                            "courant_max": step.get("courant_max"),
                            "interface_courant_max": step.get("interface_courant_max"),
                            "pressure_solve_iterations": step.get("pressure_solve_iterations"),
                        }
                        metrics = {
                            f"{prefix}/{name}": value
                            for name, value in values.items()
                            if isinstance(value, (int, float)) and math.isfinite(value)
                        }
                        if metrics:
                            run.log(metrics, step=record_index)
                        record_index += 1
                metrics = _wandb_metrics(report)
                if metrics:
                    run.log(metrics)
            finally:
                run.finish()
    except Exception as exc:
        if isinstance(exc, ImportError):
            raise RuntimeError(
                "W&B upload requested but the optional wandb package is not installed"
            ) from None
        raise RuntimeError(
            "W&B upload failed; details suppressed, JSON output is already available"
        ) from None


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize OpenFOAM solver logs, optional Slurm sacct data, and matched strong scaling.",
        epilog=(
            "Example: python scripts/hpc_metrics.py --run n100=logs/n100.log --ranks n100=100 "
            "--run n500=logs/n500.log --ranks n500=500 --baseline n100 --sacct n100=n100.sacct\n"
            "Create sacct input with: sacct --parsable2 -j JOBID "
            "--format=JobID,Elapsed,TotalCPU,AllocCPUS,MaxRSS,State,ExitCode > job.sacct"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=LOG",
        help="OpenFOAM log; repeat per run",
    )
    parser.add_argument(
        "--ranks",
        action="append",
        default=[],
        metavar="LABEL=N",
        help="explicit MPI rank count; repeat per run",
    )
    parser.add_argument(
        "--sacct",
        action="append",
        default=[],
        metavar="LABEL=FILE",
        help="optional parsable sacct file; repeat per run",
    )
    parser.add_argument(
        "--launcher",
        action="append",
        default=[],
        metavar="LABEL=FILE",
        help="optional wrapper log with high-resolution solver_wall_s; repeat per run",
    )
    parser.add_argument("--baseline", help="baseline run label; enables strong-scaling comparison")
    parser.add_argument(
        "--output", type=Path, help="create compact JSON at this new path (default: stdout)"
    )
    parser.add_argument("--wandb-project", help="opt in to W&B upload after JSON output")
    parser.add_argument("--wandb-entity", help="optional W&B entity")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _arguments()
    args = parser.parse_args(argv)
    if args.wandb_entity and not args.wandb_project:
        parser.error("--wandb-entity requires --wandb-project")
    try:
        run_paths = [_mapping(raw, "--run") for raw in args.run]
        labels = [label for label, _ in run_paths]
        if len(set(labels)) != len(labels):
            raise ValueError("run labels must be unique")
        ranks = {
            label: int(value)
            for label, value in map(lambda raw: _mapping(raw, "--ranks"), args.ranks)
        }
        if any(value <= 0 for value in ranks.values()):
            raise ValueError("rank counts must be positive")
        sacct_files = {
            label: Path(value)
            for label, value in map(lambda raw: _mapping(raw, "--sacct"), args.sacct)
        }
        launcher_files = {
            label: Path(value)
            for label, value in map(lambda raw: _mapping(raw, "--launcher"), args.launcher)
        }
        if (
            len(ranks) != len(args.ranks)
            or len(sacct_files) != len(args.sacct)
            or len(launcher_files) != len(args.launcher)
        ):
            raise ValueError("duplicate --ranks, --sacct, or --launcher label")
        unknown = (set(ranks) | set(sacct_files) | set(launcher_files)) - set(labels)
        if unknown:
            raise ValueError(
                f"--ranks/--sacct/--launcher labels have no matching --run: {', '.join(sorted(unknown))}"
            )
        if args.baseline and (args.baseline not in labels or len(labels) < 2):
            raise ValueError("--baseline must name one of at least two --run labels")

        runs = [
            summarize_run(
                label,
                Path(log_path),
                ranks.get(label),
                sacct_files.get(label),
                launcher_files.get(label),
            )
            for label, log_path in run_paths
        ]
        report: dict[str, Any] = {"schema_version": 1, "runs": runs}
        if args.baseline:
            report["comparison"] = compare_runs(runs, args.baseline)
        payload = json.dumps(report, separators=(",", ":"), sort_keys=True, allow_nan=False)
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(payload + "\n")
        else:
            print(payload)
        if args.wandb_project:
            upload_wandb(report, args.wandb_project, args.wandb_entity)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
