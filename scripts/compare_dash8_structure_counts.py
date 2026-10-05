#!/usr/bin/env python3
"""Compare saved Dash-8 structure counts with bounded Fig. 11(c) raster reads.

This is an exploratory detector comparison. The paper's structure detector is
unpublished, so a connected-cell count is not assumed to be equivalent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COUNTS = ROOT / "data/derived/calbrix_dash8_fig11_counts.csv"
DEFAULT_NATIVE_TRACE = ROOT / "data/derived/calbrix_dash8_fig11_native_trace.csv"
DEFAULT_METADATA = ROOT / "data/derived/calbrix_dash8_fig11_metadata.json"
DEFAULT_EXPERIMENT = ROOT / "experiments/E2_DASH8_BREAKUP_EXPLORATORY.json"
SOURCE_WINDOW_S = (0.0, 5.0)
TARGET_BIN_STEP_S = 0.1
NATIVE_ANALYSIS_SCHEMA = "fire-track2-native-vof-analysis-v1"
CSV_FIELDS = [
    "run_id",
    "report_path",
    "case_id",
    "time_s",
    "within_target_window",
    "alpha_threshold",
    "alpha_label",
    "operator",
    "operator_role",
    "operator_available",
    "simulation_count",
    "paper_native_time_s_nearest",
    "paper_native_time_delta_s",
    "source_read_status_nearest",
    "source_read_bound_time_s",
    "source_read_bound_count",
    "source_time_window_min_s",
    "source_time_window_max_s",
    "source_visible_envelope_samples",
    "source_count_envelope_min",
    "source_count_envelope_max",
    "source_native_raw_count",
    "absolute_error_count",
    "relative_error_fraction",
    "distance_to_source_envelope_count",
    "within_source_envelope",
    "comparison_status",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return data


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader)


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"nonfinite numeric value: {value!r}")
    return result


def threshold_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if match is None:
        raise ValueError(f"cannot parse alpha threshold from {value!r}")
    return float(match.group(0))


def threshold_label(value: float) -> str:
    if math.isclose(value, 0.001, rel_tol=0, abs_tol=1e-12):
        return "cloud"
    if math.isclose(value, 0.9, rel_tol=0, abs_tol=1e-12):
        return "core"
    return f"alpha_{value:g}"


def source_inputs(
    counts_path: Path,
    trace_path: Path,
    metadata_path: Path,
) -> tuple[dict[float, list[dict[str, Any]]], dict[float, list[dict[str, Any]]], dict]:
    metadata = read_json(metadata_path)
    axes = metadata.get("fig11c_axes_page_pixels", {})
    if optional_float(axes.get("y_zero_px")) != 2651.0:
        raise ValueError("expected corrected Fig. 11(c) y-zero pixel calibration of 2651")

    binned: dict[float, list[dict[str, Any]]] = {}
    for row in read_csv(counts_path):
        if row.get("aircraft") != "Dash-8" or row.get("panel") != "c":
            continue
        threshold = threshold_value(row["alpha_threshold"])
        binned.setdefault(threshold, []).append(
            {
                **row,
                "time_s": optional_float(row.get("time_s")),
                "nominal_time_s": optional_float(row.get("nominal_time_s")),
                "count": optional_float(row.get("count")),
                "raw_count": optional_float(row.get("raw_count")),
                "count_target_min": optional_float(row.get("count_target_min")),
                "count_target_max": optional_float(row.get("count_target_max")),
                "read_bound_time_s": optional_float(row.get("read_bound_time_s")),
                "read_bound_count": optional_float(row.get("read_bound_count")),
                "alpha_threshold_value": threshold,
            }
        )

    native: dict[float, list[dict[str, Any]]] = {}
    for row in read_csv(trace_path):
        if row.get("aircraft") != "Dash-8" or row.get("panel") != "c":
            continue
        threshold = threshold_value(row["alpha_threshold"])
        native.setdefault(threshold, []).append(
            {
                **row,
                "time_s": optional_float(row.get("time_s")),
                "raw_count": optional_float(row.get("raw_count")),
                "count": optional_float(row.get("count")),
                "count_target_min": optional_float(row.get("count_target_min")),
                "count_target_max": optional_float(row.get("count_target_max")),
                "read_bound_time_s": optional_float(row.get("read_bound_time_s")),
                "read_bound_count": optional_float(row.get("read_bound_count")),
                "alpha_threshold_value": threshold,
            }
        )

    if not binned or not native:
        raise ValueError("source CSVs must contain Dash-8 Fig. 11(c) cloud and core data")
    if set(binned) != set(native):
        raise ValueError("binned targets and native trace have different alpha thresholds")
    for rows in native.values():
        rows.sort(key=lambda row: row["time_s"])
    for rows in binned.values():
        rows.sort(key=lambda row: row["nominal_time_s"])
    return binned, native, metadata


def native_envelope(rows: list[dict[str, Any]], time_s: float) -> dict[str, Any]:
    """Return only observed raster reads whose own time bounds contain time_s."""
    candidates = [
        row
        for row in rows
        if row["time_s"] is not None
        and row["read_bound_time_s"] is not None
        and abs(row["time_s"] - time_s) <= row["read_bound_time_s"] + 1e-12
    ]
    if not candidates:
        return {
            "status": "no_visible_native_trace_within_time_bound",
            "candidates": [],
            "nearest": None,
        }

    candidates.sort(key=lambda row: (abs(row["time_s"] - time_s), row["time_s"]))
    nearest = candidates[0]
    lower = [row["count_target_min"] for row in candidates if row["count_target_min"] is not None]
    upper = [row["count_target_max"] for row in candidates if row["count_target_max"] is not None]
    if not lower or not upper:
        raise ValueError("visible native trace sample is missing its count read allowance")
    return {
        "status": nearest["count_read_status"],
        "candidates": candidates,
        "nearest": nearest,
        "time_min_s": min(row["time_s"] for row in candidates),
        "time_max_s": max(row["time_s"] for row in candidates),
        "count_min": min(lower),
        "count_max": max(upper),
    }


def count_methods(threshold_data: dict[str, Any]) -> list[dict[str, Any]]:
    face = validated_integer_count(
        threshold_data["connected_cell_regions"], "connected_cell_regions"
    )
    single_value = threshold_data.get("single_cell_regions")
    single = (
        validated_integer_count(single_value, "single_cell_regions")
        if single_value is not None
        else None
    )
    if single is not None and single > face:
        raise ValueError("single_cell_regions cannot exceed connected_cell_regions")
    point = threshold_data.get("point_connected_cell_regions")
    point_count = (
        validated_integer_count(point, "point_connected_cell_regions")
        if point is not None
        else None
    )
    return [
        {
            "operator": "face_all_sizes",
            "role": "primary",
            "available": True,
            "count": face,
        },
        {
            "operator": "point_all_sizes",
            "role": "sensitivity",
            "available": point_count is not None,
            "count": point_count,
        },
        {
            "operator": "face_minimum_2_cells",
            "role": "sensitivity",
            "available": single is not None,
            "count": face - single if single is not None else None,
        },
    ]


def normalize_native_analysis(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    """Adapt one native-polyhedral snapshot to the existing comparison schema.

    The native analyzer reports face-connected component counts after explicit
    minimum-cell filters. It does not provide point-touch connectivity, so
    that existing sensitivity is left unavailable instead of inferred.
    """
    if report.get("schema") != NATIVE_ANALYSIS_SCHEMA:
        return report

    time_s = optional_float(report.get("time_value_s"))
    time_name = report.get("time_name")
    if time_s is None or time_s < 0 or not isinstance(time_name, str):
        raise ValueError("native analysis must provide finite time_value_s and time_name")
    try:
        named_time_s = float(time_name)
    except ValueError as error:
        raise ValueError("native analysis time_name must be numeric") from error
    if not math.isfinite(named_time_s) or not math.isclose(
        named_time_s, time_s, rel_tol=0.0, abs_tol=5e-9
    ):
        raise ValueError("native analysis time_name and time_value_s disagree")

    native_thresholds = report.get("thresholds")
    if not isinstance(native_thresholds, dict) or not native_thresholds:
        raise ValueError("native analysis is missing threshold records")
    thresholds: list[dict[str, Any]] = []
    seen: set[float] = set()
    for key, record in native_thresholds.items():
        threshold = threshold_value(key)
        if threshold in seen or not isinstance(record, dict):
            raise ValueError("native analysis has duplicate or malformed threshold records")
        seen.add(threshold)
        one = record.get("min_cells_1")
        two = record.get("min_cells_2")
        if not isinstance(one, dict) or not isinstance(two, dict):
            raise ValueError(f"native alpha={threshold:g} record lacks min_cells_1/min_cells_2")
        count_one = validated_integer_count(
            one.get("component_count"), "min_cells_1.component_count"
        )
        count_two = validated_integer_count(
            two.get("component_count"), "min_cells_2.component_count"
        )
        if count_two > count_one:
            raise ValueError(f"native min_cells_2 count exceeds min_cells_1 at alpha={threshold:g}")
        thresholds.append(
            {
                "alpha_threshold": threshold,
                "connected_cell_regions": count_one,
                "single_cell_regions": count_one - count_two,
                # Deliberately omitted: point-touch connectivity was not run.
            }
        )
    case_id = str(report.get("case_id") or report_path.parent.name)
    return {
        "schema": NATIVE_ANALYSIS_SCHEMA,
        "input_report_schema": NATIVE_ANALYSIS_SCHEMA,
        "case_id": case_id,
        "classification": (
            "single saved-time native-polyhedral face-connected component analysis; "
            "not a reconstructed 0-5 s history"
        ),
        "times": [{"time_s": time_s, "thresholds": thresholds}],
        "native_analysis_provenance": {
            "time_name": time_name,
            "time_value_s": time_s,
            "source_patch": report.get("source_patch"),
            "native_cells": report.get("topology", {}).get("native_cells"),
            "connectivity_method": report.get("input_provenance", {})
            .get("connectivity", {})
            .get("method"),
            "unpublished_paper_detector_equivalence": report.get(
                "unpublished_paper_detector_equivalence"
            ),
            "point_touch_sensitivity_available": False,
            "component_filter_mapping": (
                "min_cells_1 -> face_all_sizes; min_cells_2 -> face_minimum_2_cells"
            ),
        },
    }


def validated_integer_count(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite nonnegative integer")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValueError(f"{field} must be a finite nonnegative integer")
    return int(numeric)


def comparison_row(
    *,
    run_id: str,
    report_path: Path,
    case_id: str,
    time_s: float,
    alpha_threshold: float,
    method: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    nearest = source.get("nearest")
    sim = method["count"] if method["available"] else None
    positive_resolved = (
        nearest is not None
        and nearest["count_read_status"] == "resolved_positive_count_read"
        and nearest["raw_count"] is not None
        and nearest["raw_count"] > 0
    )
    source_center = nearest["raw_count"] if positive_resolved else None
    absolute_error = (
        abs(sim - source_center) if sim is not None and source_center is not None else None
    )
    lower, upper = source.get("count_min"), source.get("count_max")
    relative_error = (
        absolute_error / source_center
        if absolute_error is not None and lower is not None and lower > 0
        else None
    )
    distance = None
    inside = None
    if sim is not None and lower is not None and upper is not None:
        distance = max(lower - sim, sim - upper, 0.0)
        inside = distance == 0.0
    if nearest is None:
        status = source["status"]
    elif not method["available"]:
        status = "operator_unavailable"
    elif positive_resolved:
        status = (
            "positive_source_interval_above_zero"
            if lower is not None and lower > 0
            else "positive_source_interval_overlaps_zero"
        )
    else:
        status = "near_zero_source_interval_only"
    candidates = source.get("candidates", [])
    return {
        "run_id": run_id,
        "report_path": str(report_path),
        "case_id": case_id,
        "time_s": time_s,
        "within_target_window": SOURCE_WINDOW_S[0] <= time_s <= SOURCE_WINDOW_S[1],
        "alpha_threshold": alpha_threshold,
        "alpha_label": threshold_label(alpha_threshold),
        "operator": method["operator"],
        "operator_role": method["role"],
        "operator_available": method["available"],
        "simulation_count": sim,
        "paper_native_time_s_nearest": nearest["time_s"] if nearest else None,
        "paper_native_time_delta_s": nearest["time_s"] - time_s if nearest else None,
        "source_read_status_nearest": nearest["count_read_status"] if nearest else None,
        "source_read_bound_time_s": nearest["read_bound_time_s"] if nearest else None,
        "source_read_bound_count": nearest["read_bound_count"] if nearest else None,
        "source_time_window_min_s": source.get("time_min_s"),
        "source_time_window_max_s": source.get("time_max_s"),
        "source_visible_envelope_samples": len(candidates),
        "source_count_envelope_min": lower,
        "source_count_envelope_max": upper,
        "source_native_raw_count": source_center,
        "absolute_error_count": absolute_error,
        "relative_error_fraction": relative_error,
        "distance_to_source_envelope_count": distance,
        "within_source_envelope": inside,
        "comparison_status": status,
    }


def summarize_run(
    *,
    run_id: str,
    report: dict[str, Any],
    report_path: Path,
    native: dict[float, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    observed_times = [float(row["time_s"]) for row in report.get("times", [])]
    inside_times = [t for t in observed_times if SOURCE_WINDOW_S[0] <= t <= SOURCE_WINDOW_S[1]]
    inside_times.sort()
    outside_count = len(observed_times) - len(inside_times)
    expected_bin_count = (
        int(round((SOURCE_WINDOW_S[1] - SOURCE_WINDOW_S[0]) / TARGET_BIN_STEP_S)) + 1
    )
    covered_bins = set()
    for time_s in inside_times:
        bin_index = int(math.floor(time_s / TARGET_BIN_STEP_S + 0.5))
        bin_time_s = bin_index * TARGET_BIN_STEP_S
        if (
            bin_index < expected_bin_count
            and abs(time_s - bin_time_s) <= TARGET_BIN_STEP_S / 2 + 1e-12
        ):
            covered_bins.add(bin_index)
    missing_bins = sorted(set(range(expected_bin_count)) - covered_bins)
    saved_time_gaps = [
        {
            "from_time_s": left,
            "to_time_s": right,
            "gap_s": right - left,
        }
        for left, right in zip(inside_times, inside_times[1:], strict=False)
    ]
    case_id = str(report.get("case_id", "unknown"))
    for snapshot in report.get("times", []):
        time_s = float(snapshot["time_s"])
        if not math.isfinite(time_s):
            raise ValueError(f"nonfinite simulation time in {report_path}")
        for threshold_data in snapshot.get("thresholds", []):
            threshold = threshold_value(threshold_data["alpha_threshold"])
            if threshold not in native:
                raise ValueError(f"missing native source curve for threshold alpha={threshold:g}")
            if SOURCE_WINDOW_S[0] <= time_s <= SOURCE_WINDOW_S[1]:
                source = native_envelope(native[threshold], time_s)
            else:
                source = {
                    "status": "outside_target_window",
                    "candidates": [],
                    "nearest": None,
                }
            for method in count_methods(threshold_data):
                comparisons.append(
                    comparison_row(
                        run_id=run_id,
                        report_path=report_path,
                        case_id=case_id,
                        time_s=time_s,
                        alpha_threshold=threshold,
                        method=method,
                        source=source,
                    )
                )

    summaries: dict[str, Any] = {
        "run_id": run_id,
        "report_path": str(report_path),
        "case_id": case_id,
        "report_schema": report.get("input_report_schema", report.get("schema")),
        "report_classification": report.get("classification"),
        "native_analysis_provenance": report.get("native_analysis_provenance"),
        "saved_snapshot_count": len(observed_times),
        "saved_snapshot_count_in_0_5_s": len(inside_times),
        "saved_snapshot_count_outside_0_5_s": outside_count,
        "saved_time_min_in_0_5_s": min(inside_times) if inside_times else None,
        "saved_time_max_in_0_5_s": max(inside_times) if inside_times else None,
        "sampled_horizon_fraction_of_0_5_s_by_last_saved_time": (
            max(inside_times) / SOURCE_WINDOW_S[1] if inside_times else 0.0
        ),
        "expected_0_1_s_target_bin_count_in_0_5_s": expected_bin_count,
        "saved_0_1_s_target_bin_coverage_count": len(covered_bins),
        "saved_0_1_s_target_bin_coverage_fraction": len(covered_bins) / expected_bin_count,
        "missing_0_1_s_target_bins_s": [
            round(index * TARGET_BIN_STEP_S, 10) for index in missing_bins
        ],
        "saved_time_gaps_s": saved_time_gaps,
        "maximum_saved_time_gap_s": max((row["gap_s"] for row in saved_time_gaps), default=None),
        "by_threshold_and_operator": {},
    }
    for threshold in sorted(native):
        threshold_key = f"{threshold:g}"
        summaries["by_threshold_and_operator"][threshold_key] = {}
        for operator in ("face_all_sizes", "point_all_sizes", "face_minimum_2_cells"):
            rows = [
                row
                for row in comparisons
                if row["alpha_threshold"] == threshold
                and row["operator"] == operator
                and row["within_target_window"]
            ]
            available = [row for row in rows if row["operator_available"]]
            center_errors = [
                row["absolute_error_count"]
                for row in available
                if row["absolute_error_count"] is not None
            ]
            relative = [
                row["relative_error_fraction"]
                for row in available
                if row["relative_error_fraction"] is not None
            ]
            interval_evaluable = [
                row for row in available if row["distance_to_source_envelope_count"] is not None
            ]
            positive_resolved_rows = [
                row for row in available if row["absolute_error_count"] is not None
            ]
            relative_error_eligible_rows = [
                row for row in available if row["relative_error_fraction"] is not None
            ]
            inside_count = sum(row["within_source_envelope"] is True for row in interval_evaluable)
            summaries["by_threshold_and_operator"][threshold_key][operator] = {
                "available": bool(available and available[0]["operator_available"]),
                "saved_samples_in_target_window": len(rows),
                "visible_native_source_envelope_samples": sum(
                    row["source_visible_envelope_samples"] > 0 for row in available
                ),
                "positive_resolved_source_samples": len(positive_resolved_rows),
                "relative_error_eligible_samples": len(relative_error_eligible_rows),
                "missing_visible_native_source_samples": sum(
                    row["comparison_status"] == "no_visible_native_trace_within_time_bound"
                    for row in available
                ),
                "near_zero_interval_only_samples": sum(
                    row["comparison_status"] == "near_zero_source_interval_only"
                    for row in available
                ),
                "source_interval_evaluable_samples": len(interval_evaluable),
                "within_propagated_source_interval_count": inside_count,
                "within_propagated_source_interval_fraction": (
                    inside_count / len(interval_evaluable) if interval_evaluable else None
                ),
                "mean_absolute_error_count_positive_resolved_only": (
                    sum(center_errors) / len(center_errors) if center_errors else None
                ),
                "mean_relative_error_fraction_positive_resolved_only": (
                    sum(relative) / len(relative) if relative else None
                ),
            }
    return comparisons, summaries


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_comparisons(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if value is None else value) for key, value in row.items()})


def make_plot(
    output_path: Path,
    comparisons: list[dict[str, Any]],
    native: dict[float, list[dict[str, Any]]],
    binned: dict[float, list[dict[str, Any]]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, constrained_layout=True)
    styles = {
        "face_all_sizes": ("-", "o", "face, all sizes"),
        "point_all_sizes": ("--", "s", "point, all sizes"),
        "face_minimum_2_cells": (":", "^", "face, minimum 2 cells"),
    }
    run_ids = list(dict.fromkeys(row["run_id"] for row in comparisons))
    for axis, threshold in zip(axes, (0.001, 0.9), strict=True):
        source_rows = [row for row in native[threshold] if row["time_s"] <= SOURCE_WINDOW_S[1]]
        resolved = [
            row for row in source_rows if row["count_read_status"] == "resolved_positive_count_read"
        ]
        unresolved = [
            row for row in source_rows if row["count_read_status"] != "resolved_positive_count_read"
        ]
        axis.errorbar(
            [row["time_s"] for row in resolved],
            [row["raw_count"] for row in resolved],
            yerr=[
                [row["raw_count"] - row["count_target_min"] for row in resolved],
                [row["count_target_max"] - row["raw_count"] for row in resolved],
            ],
            fmt=".",
            color="0.55",
            ecolor="0.78",
            elinewidth=0.5,
            markersize=2.2,
            capsize=0,
            label="visible native raster reads ± count allowance",
        )
        if unresolved:
            axis.vlines(
                [row["time_s"] for row in unresolved],
                [row["count_target_min"] for row in unresolved],
                [row["count_target_max"] for row in unresolved],
                color="0.45",
                linewidth=0.6,
                alpha=0.5,
                label="unresolved near-zero read interval",
            )
        targets = [
            row
            for row in binned[threshold]
            if row["nominal_time_s"] is not None
            and SOURCE_WINDOW_S[0] <= row["nominal_time_s"] <= SOURCE_WINDOW_S[1]
        ]
        target_resolved = [
            row
            for row in targets
            if row["count_read_status"] == "resolved_positive_count_read"
            and row["raw_count"] is not None
        ]
        if target_resolved:
            axis.errorbar(
                [
                    row["time_s"] if row["time_s"] is not None else row["nominal_time_s"]
                    for row in target_resolved
                ],
                [row["raw_count"] for row in target_resolved],
                yerr=[
                    [row["raw_count"] - row["count_target_min"] for row in target_resolved],
                    [row["count_target_max"] - row["raw_count"] for row in target_resolved],
                ],
                fmt="o",
                color="#c46c00",
                ecolor="#e9a744",
                elinewidth=0.8,
                markersize=3.2,
                capsize=1.5,
                label="selected 0.1 s source targets",
            )
        for row in targets:
            if row["raw_count"] is None and row["count_target_min"] is not None:
                axis.vlines(
                    row["time_s"] if row["time_s"] is not None else row["nominal_time_s"],
                    row["count_target_min"],
                    row["count_target_max"],
                    color="#c46c00",
                    linewidth=1.1,
                    alpha=0.65,
                )

        for run_id in run_ids:
            display_name = re.sub(r"-\d{8}T\d{6}Z(?:-.*)?$", "", run_id).replace("-", " ")
            for operator, (line, marker, label) in styles.items():
                rows = [
                    row
                    for row in comparisons
                    if row["run_id"] == run_id
                    and row["alpha_threshold"] == threshold
                    and row["operator"] == operator
                    and row["operator_available"]
                    and row["within_target_window"]
                ]
                rows.sort(key=lambda row: row["time_s"])
                if not rows:
                    continue
                axis.plot(
                    [row["time_s"] for row in rows],
                    [row["simulation_count"] for row in rows],
                    linestyle=line,
                    marker=marker,
                    markersize=3.4,
                    linewidth=1.0,
                    label=f"{display_name}: {label}",
                )
        axis.set_xlim(*SOURCE_WINDOW_S)
        axis.set_ylabel("Liquid structure count")
        axis.set_title(f"{threshold_label(threshold).title()} (α ≥ {threshold:g})")
        axis.grid(True, alpha=0.2)
        axis.legend(fontsize=7, ncol=2, loc="upper left" if threshold == 0.001 else "upper right")

    axes[-1].set_xlabel("Actual saved / digitized time (s)")
    figure.suptitle(
        "Exploratory Dash-8 counts — paper detector is unpublished; equivalence is unknown",
        fontsize=12,
    )
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def git_state() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"revision": revision, "working_tree_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "working_tree_dirty": None}


def build_bundle(
    reports: list[Path],
    *,
    report_labels: list[str] | None = None,
    counts_path: Path = DEFAULT_COUNTS,
    trace_path: Path = DEFAULT_NATIVE_TRACE,
    metadata_path: Path = DEFAULT_METADATA,
    experiment_path: Path = DEFAULT_EXPERIMENT,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[float, list[dict[str, Any]]],
    dict[float, list[dict[str, Any]]],
]:
    if report_labels is not None:
        if len(report_labels) != len(reports):
            raise ValueError("--report-label must be supplied once for each --report")
        if any(not label.strip() for label in report_labels):
            raise ValueError("report labels must be nonempty")

    binned, native, metadata = source_inputs(counts_path, trace_path, metadata_path)
    experiment = read_json(experiment_path)
    all_rows: list[dict[str, Any]] = []
    run_summaries = []
    used_reports = []
    inferred_native_run_ids: set[str] = set()
    for index, report_path in enumerate(reports):
        input_report = read_json(report_path)
        is_native_analysis = input_report.get("schema") == NATIVE_ANALYSIS_SCHEMA
        report = normalize_native_analysis(input_report, report_path)
        default_run_id = (
            str(input_report.get("run_id") or report_path.parent.name)
            if is_native_analysis
            else report_path.parent.parent.name
        )
        run_id = report_labels[index] if report_labels is not None else default_run_id
        if (
            is_native_analysis
            and report_labels is None
            and not input_report.get("run_id")
            and run_id in inferred_native_run_ids
        ):
            raise ValueError(
                "native reports infer the same run_id from their paths; supply one "
                "--report-label per report, or put an explicit run_id in each report"
            )
        if is_native_analysis and report_labels is None and not input_report.get("run_id"):
            inferred_native_run_ids.add(run_id)
        comparisons, summary = summarize_run(
            run_id=run_id,
            report=report,
            report_path=report_path,
            native=native,
        )
        all_rows.extend(comparisons)
        run_summaries.append(summary)
        used_reports.append(
            {
                "path": str(report_path),
                "sha256": sha256_file(report_path),
                "run_id": run_id,
                "report_label": report_labels[index] if report_labels is not None else None,
                "case_id": report.get("case_id"),
                "input_schema": input_report.get("schema"),
                "time_value_s": input_report.get("time_value_s") if is_native_analysis else None,
                "normalization": report.get("native_analysis_provenance"),
            }
        )

    source_target_summary = {}
    for threshold, rows in sorted(binned.items()):
        in_window = [
            row
            for row in rows
            if row["nominal_time_s"] is not None
            and SOURCE_WINDOW_S[0] <= row["nominal_time_s"] <= SOURCE_WINDOW_S[1]
        ]
        status_counts = Counter(row["count_read_status"] for row in in_window)
        source_target_summary[str(threshold)] = {
            "alpha_label": threshold_label(threshold),
            "target_rows_in_nominal_0_5_s_window": len(in_window),
            "status_counts": dict(status_counts),
        }
    summary = {
        "classification": "Exploratory paper-raster count comparison; not E2 acceptance or field validation",
        "detector_equivalence": "Unknown: Calbrix et al. do not publish the MATLAB structure-identification algorithm; native connected-cell counts are not assumed equivalent.",
        "comparison_method": "At each exact saved CFD time, use only visible native raster columns whose individual +/- time read bounds contain that time. No source interpolation or extrapolation is performed.",
        "input_time_coverage": "Each report contributes only its actually saved times. A native analysis-v1 report contains one analyzed time and is never expanded into an assumed history.",
        "count_allowances": "Source intervals retain the per-column +/- count read allowances. The native time envelope takes the minimum lower bound and maximum upper bound across visible reads in the exact saved-time window.",
        "relative_error_eligibility": "Relative error is reported only for a positive resolved nearest source read whose propagated source-count interval has a strictly positive lower bound. Otherwise absolute and interval distance remain available where defined.",
        "target_window_s": list(SOURCE_WINDOW_S),
        "full_window_decision": "No success or gate decision is made. Report each sampled horizon as a fraction of the full 0-5 s window; partial coverage is not a success result.",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git": git_state(),
        "source": {
            "counts_csv": {"path": str(counts_path), "sha256": sha256_file(counts_path)},
            "native_trace_csv": {"path": str(trace_path), "sha256": sha256_file(trace_path)},
            "metadata_json": {"path": str(metadata_path), "sha256": sha256_file(metadata_path)},
            "source_pdf_sha256": metadata.get("source_pdf_sha256"),
            "source_locator": metadata.get("source_locator"),
            "axis_y_zero_px": metadata["fig11c_axes_page_pixels"]["y_zero_px"],
            "digitization_allowances": metadata.get("digitization_allowances"),
            "source_target_rows": source_target_summary,
        },
        "experiment_record": {
            "path": str(experiment_path),
            "sha256": sha256_file(experiment_path),
            "experiment_id": experiment.get("experiment_id"),
            "classification": experiment.get("classification"),
            "comparison_rules": experiment.get("comparison_rules"),
        },
        "reports": used_reports,
        "runs": run_summaries,
        "operator_definitions": {
            "face_all_sizes": "Primary face-connected native-cell regions, minimum one cell.",
            "point_all_sizes": "Shared-point connectivity sensitivity only where the input report supplies it; otherwise explicitly unavailable.",
            "face_minimum_2_cells": "Face-connected count after excluding singleton-cell regions; separate detector sensitivity.",
        },
    }
    return all_rows, json_safe(summary), native, binned


def write_bundle(
    output_dir: Path,
    reports: list[Path],
    *,
    report_labels: list[str] | None = None,
    counts_path: Path = DEFAULT_COUNTS,
    trace_path: Path = DEFAULT_NATIVE_TRACE,
    metadata_path: Path = DEFAULT_METADATA,
    experiment_path: Path = DEFAULT_EXPERIMENT,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    for path in [*reports, counts_path, trace_path, metadata_path, experiment_path]:
        if not path.is_file():
            raise FileNotFoundError(path)
    comparisons, summary, native, binned = build_bundle(
        reports,
        report_labels=report_labels,
        counts_path=counts_path,
        trace_path=trace_path,
        metadata_path=metadata_path,
        experiment_path=experiment_path,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    write_comparisons(output_dir / "comparisons.csv", comparisons)
    summary["script_sha256"] = sha256_file(Path(__file__))
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (output_dir / "run_metadata.json").write_text(
        json.dumps(json_safe(summary), indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    make_plot(output_dir / "counts.png", comparisons, native, binned)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        type=Path,
        help="analytics/report.json input; repeat for multiple runs",
    )
    parser.add_argument(
        "--report-label",
        action="append",
        default=None,
        help=(
            "display/run identity for the corresponding --report; repeat once per report "
            "when source paths do not uniquely identify variants"
        ),
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-counts", type=Path, default=DEFAULT_COUNTS)
    parser.add_argument("--source-native", type=Path, default=DEFAULT_NATIVE_TRACE)
    parser.add_argument("--metadata-json", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--experiment-json", type=Path, default=DEFAULT_EXPERIMENT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    reports = [path.resolve() for path in args.report]
    summary = write_bundle(
        args.output_dir.resolve(),
        reports,
        report_labels=args.report_label,
        counts_path=args.source_counts.resolve(),
        trace_path=args.source_native.resolve(),
        metadata_path=args.metadata_json.resolve(),
        experiment_path=args.experiment_json.resolve(),
    )
    print(
        json.dumps(
            {
                "classification": summary["classification"],
                "reports": len(summary["reports"]),
                "output_dir": str(args.output_dir.resolve()),
            }
        )
    )


if __name__ == "__main__":
    main()
