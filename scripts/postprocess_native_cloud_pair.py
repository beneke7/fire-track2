#!/usr/bin/env python3
"""Add native cloud-envelope profiles to a completed matched local-mesh pair.

The upstream pair postprocessor must already have exported and hashed native
fields at t=1 s. This script consumes those sealed exports without re-exporting
fields or touching either solver case. Its outputs are exploratory AABB
envelopes, not an E2 validation result.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyze_native_cloud_profiles as cloud_profiles  # noqa: E402

POSTPROCESS_SCHEMA = "dash8-local-mesh-pair-postprocess-v1"
OUTPUT_SCHEMA = "dash8-native-cloud-pair-profiles-v1"
EXPECTED_TIME_S = 1.0
TIME_TOLERANCE_S = 5e-10
EXPECTED_CELLS = 1_857_796
EXPECTED_RANKS = 20
SOURCE_PATCH = "dash8Opening"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
VARIANTS = ("uniform", "three-component")
REQUIRED_FIELDS = ("alpha.water", "U", "p_rgh", "k", "epsilon", "nut", "phi")
UPSTREAM_SUCCESS = "native_ledger_and_topology_complete_render_pending"
UPSTREAM_FAILURES = {
    "postprocessing_failed_solver_results_preserved",
    "native_postprocess_incomplete_no_cfd_retry",
    "pair_schedule_failed_or_incomplete_no_cfd_retry",
    "pair_member_failed_or_missing_no_cfd_retry",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label} JSON at {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} JSON must be an object: {path}")
    return value


def _project_path(value: str | Path, root: Path, label: str, *, must_exist: bool = True) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=must_exist)
    runs_root = (root / "results/runs").resolve(strict=True)
    if not resolved.is_relative_to(runs_root):
        raise ValueError(f"{label} must remain under {runs_root}: {resolved}")
    return resolved


def _sha_manifest(path: Path, label: str) -> dict[str, str]:
    record = _load_json(path, label)
    if not record or any(
        not isinstance(relative, str) or not isinstance(digest, str) or len(digest) != 64
        for relative, digest in record.items()
    ):
        raise ValueError(f"{label} must map relative paths to SHA-256 hex strings")
    for relative in record:
        rel_path = Path(relative)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise ValueError(f"unsafe relative path in {label}: {relative}")
    return {str(key): str(value) for key, value in record.items()}


def _check_time(value: Any, expected: float, label: str) -> float:
    try:
        actual = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not numeric: {value!r}") from error
    if not math.isfinite(actual) or not math.isclose(
        actual, expected, rel_tol=0.0, abs_tol=TIME_TOLERANCE_S
    ):
        raise ValueError(f"{label} is {actual!r} s, expected {expected:g} s")
    return actual


def _check_terminal_log(case_dir: Path) -> dict[str, Any]:
    log_path = case_dir / "log.interIsoFoam"
    if not log_path.is_file():
        raise ValueError(f"missing terminal solver log: {log_path}")
    with log_path.open("rb") as stream:
        stream.seek(max(0, log_path.stat().st_size - 8 * 1024 * 1024))
        tail = stream.read().decode("utf-8", errors="replace")
    times = re.findall(r"(?m)^\s*Time\s*=\s*([+\-0-9.eE]+)\s*$", tail)
    if not times:
        raise ValueError(f"solver log has no printed time records: {log_path}")
    last_time = float(times[-1])
    if not math.isclose(last_time, EXPECTED_TIME_S, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"solver log ends at {last_time:g} s, expected 1 s")
    if not re.search(r"(?m)^\s*End\s*$", tail):
        raise ValueError("successful solver manifest is not corroborated by an OpenFOAM End marker")
    return {
        "path": str(log_path),
        "sha256": sha256_file(log_path),
        "last_printed_time_s": last_time,
    }


def _checkpoint_hashes(
    case_dir: Path, record: dict[str, Any], expected_ranks: int
) -> dict[str, str]:
    checkpoint = record.get("exact_checkpoint")
    if not isinstance(checkpoint, dict):
        raise ValueError("upstream comparison lacks exact_checkpoint metadata")
    _check_time(checkpoint.get("requested_time_s"), EXPECTED_TIME_S, "checkpoint requested time")
    selected_name = checkpoint.get("selected_time_directory")
    if not isinstance(selected_name, str):
        raise ValueError("checkpoint has no saved time-directory name")
    _check_time(selected_name, EXPECTED_TIME_S, "checkpoint saved directory")
    if int(checkpoint.get("rank_count", -1)) != expected_ranks:
        raise ValueError("checkpoint rank count does not match case inputs")
    if tuple(checkpoint.get("fields_required_per_rank", ())) != REQUIRED_FIELDS:
        raise ValueError("checkpoint required-field inventory differs from the pair contract")

    expected_hashes = checkpoint.get("field_sha256")
    after_hashes = record.get("native_field_sha256_after_observers")
    if not isinstance(expected_hashes, dict) or not isinstance(after_hashes, dict):
        raise ValueError("comparison lacks before/after saved-field SHA-256 inventories")
    if expected_hashes != after_hashes:
        raise ValueError("upstream native observers recorded changed saved fields")

    actual: dict[str, str] = {}
    for rank in range(expected_ranks):
        rank_dir = case_dir / f"processor{rank}" / selected_name
        for field in REQUIRED_FIELDS:
            path = rank_dir / field
            if not path.is_file() or not path.resolve().is_relative_to(case_dir.resolve()):
                raise ValueError(f"missing or escaping saved field: {path}")
            relative = path.relative_to(case_dir).as_posix()
            actual[relative] = sha256_file(path)
    if actual != expected_hashes:
        raise ValueError("current saved native fields do not match the upstream checkpoint hashes")
    return actual


def _validate_one_run(
    role: str,
    record: dict[str, Any],
    repo_root: Path,
    observer_record: dict[str, Any],
) -> dict[str, Any]:
    run_dir = _project_path(record.get("run_directory", ""), repo_root, f"{role} run")
    expected_case_dir = (run_dir / "case").resolve(strict=True)
    case_dir = _project_path(record.get("case_directory", ""), repo_root, f"{role} case")
    if case_dir != expected_case_dir:
        raise ValueError(f"{role} case path is not the run bundle's case directory")

    manifest_path = _project_path(record.get("manifest_path", ""), repo_root, f"{role} manifest")
    if manifest_path != run_dir / "manifest.json":
        raise ValueError(f"{role} manifest path does not match the run bundle")
    manifest = _load_json(manifest_path, f"{role} run manifest")
    manifest_hash = sha256_file(manifest_path)
    if record.get("manifest_sha256") != manifest_hash:
        raise ValueError(f"{role} run-manifest hash changed after upstream postprocessing")
    if (
        manifest.get("run_id") != run_dir.name
        or manifest.get("variant") != role
        or manifest.get("status") != "solver_completed"
        or manifest.get("solver_exit_code") != 0
    ):
        raise ValueError(f"{role} run manifest does not prove a successful matching run")

    case_inputs_path = case_dir / "case-inputs.json"
    case_inputs = _load_json(case_inputs_path, f"{role} case inputs")
    input_hash = sha256_file(case_inputs_path)
    if manifest.get("case_input_hashes", {}).get("case-inputs.json") != input_hash:
        raise ValueError(f"{role} case-input hash disagrees with its sealed run manifest")
    if manifest.get("prepared_case_sha256", {}).get("case-inputs.json") != input_hash:
        raise ValueError(f"{role} prepared-case hash disagrees with its run manifest")
    if int(case_inputs.get("ranks", -1)) != EXPECTED_RANKS:
        raise ValueError(f"{role} case is not the expected {EXPECTED_RANKS}-rank pair member")
    if int(case_inputs.get("mesh_cells_expected", -1)) != EXPECTED_CELLS:
        raise ValueError(f"{role} case does not match the prepared local-mesh cell count")
    _check_time(case_inputs.get("horizon_s"), EXPECTED_TIME_S, f"{role} case horizon")

    area = float(case_inputs.get("source_patch_areas_m2", {}).get(SOURCE_PATCH, math.nan))
    face_count = int(case_inputs.get("source_patch_face_counts", {}).get(SOURCE_PATCH, -1))
    sources = case_inputs.get("source_geometry", {}).get("sources", [])
    source_matches = [item for item in sources if item.get("name") == SOURCE_PATCH]
    if len(source_matches) != 1 or not math.isfinite(area) or area <= 0:
        raise ValueError(f"{role} inputs lack one positive declared {SOURCE_PATCH} source")
    if not math.isclose(
        float(source_matches[0].get("area_m2", math.nan)), area, rel_tol=1e-9, abs_tol=1e-12
    ):
        raise ValueError(f"{role} case source geometry area is inconsistent")
    if face_count <= 0:
        raise ValueError(f"{role} inputs lack a positive native source-face count")
    solver_log = _check_terminal_log(case_dir)
    checkpoint_hashes = _checkpoint_hashes(case_dir, record, EXPECTED_RANKS)

    export_meta_path = _project_path(
        record.get("native_export_metadata_path", ""), repo_root, f"{role} export metadata"
    )
    export_meta = _load_json(export_meta_path, f"{role} native export metadata")
    raw_dir = (export_meta_path.parent / "raw").resolve(strict=True)
    declared_raw = Path(export_meta.get("raw_directory", "")).resolve(strict=True)
    if declared_raw != raw_dir:
        raise ValueError(f"{role} export metadata raw directory is inconsistent")
    if (
        export_meta.get("status") != "complete"
        or export_meta.get("return_code") != 0
        or not export_meta.get("input_hashes_unchanged")
        or export_meta.get("image_id") != PINNED_IMAGE_ID
        or export_meta.get("source_patch") != SOURCE_PATCH
        or export_meta.get("mpi_ranks") != EXPECTED_RANKS
    ):
        raise ValueError(f"{role} native export record is not a successful pinned read-only export")
    if Path(export_meta.get("case_directory", "")).resolve(strict=True) != case_dir:
        raise ValueError(f"{role} export metadata identifies a different solver case")
    _check_time(export_meta.get("selected_time_requested"), EXPECTED_TIME_S, f"{role} export time")

    native_analysis_path = _project_path(
        record.get("native_analysis_path", ""), repo_root, f"{role} native analysis"
    )
    raw_manifest_path = _project_path(
        record.get("native_export_raw_hash_manifest", ""),
        repo_root,
        f"{role} raw-export hash manifest",
    )
    if raw_manifest_path.parent != native_analysis_path.parent:
        raise ValueError(f"{role} native analysis and raw hash manifest are not co-located")
    native_report = _load_json(native_analysis_path, f"{role} native topology report")
    native_report_hash = sha256_file(native_analysis_path)
    native_topology_record = record.get("native_topology", {})
    observer_topology_record = observer_record.get("native_topology", {})
    if (
        native_topology_record.get("analysis_sha256") != native_report_hash
        or observer_topology_record.get("analysis_sha256") != native_report_hash
    ):
        raise ValueError(f"{role} native topology report hash does not match upstream comparison")
    topology = native_report.get("topology", {})
    _check_time(native_report.get("time_value_s"), EXPECTED_TIME_S, f"{role} native report time")
    if native_report.get("source_patch") != SOURCE_PATCH:
        raise ValueError(f"{role} native report identifies a different source patch")
    if (
        int(topology.get("native_cells", -1)) != EXPECTED_CELLS
        or int(topology.get("rank_count", -1)) != EXPECTED_RANKS
        or int(topology.get("source_boundary_face_count", -1)) != face_count
    ):
        raise ValueError(f"{role} native topology cell/rank/source-face metadata mismatch")
    native_area = float(topology.get("source_patch_area_m2", math.nan))
    if not math.isclose(native_area, area, rel_tol=1e-8, abs_tol=1e-10):
        raise ValueError(f"{role} native source area disagrees with the case input")

    raw_hashes = _sha_manifest(raw_manifest_path, f"{role} raw export hash manifest")
    if not any(key.endswith("alpha_water.f64") for key in raw_hashes):
        raise ValueError(f"{role} raw export manifest has no alpha.water payload")
    if not any(key.endswith("velocity_xyz_m_s.f64") for key in raw_hashes):
        raise ValueError(f"{role} raw export manifest has no velocity payload")
    return {
        "role": role,
        "run_id": run_dir.name,
        "run_directory": run_dir,
        "case_directory": case_dir,
        "case_inputs_path": case_inputs_path,
        "case_inputs": case_inputs,
        "case_inputs_sha256": input_hash,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_hash,
        "manifest": manifest,
        "solver_log": solver_log,
        "checkpoint_field_sha256": checkpoint_hashes,
        "export_metadata_path": export_meta_path,
        "export_metadata_sha256": sha256_file(export_meta_path),
        "export_metadata": export_meta,
        "raw_export_directory": raw_dir,
        "native_analysis_path": native_analysis_path,
        "native_analysis_sha256": native_report_hash,
        "native_analysis": native_report,
        "raw_hash_manifest_path": raw_manifest_path,
        "raw_hash_manifest_sha256": sha256_file(raw_manifest_path),
        "raw_hashes": raw_hashes,
        "source_area_m2": area,
        "source_face_count": face_count,
    }


def validate_upstream_comparison(comparison_path: Path, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    comparison_path = comparison_path.resolve(strict=True)
    comparison = _load_json(comparison_path, "upstream pair comparison")
    if comparison.get("schema") != POSTPROCESS_SCHEMA:
        raise ValueError("upstream comparison has an unsupported schema")
    if comparison.get("status") != UPSTREAM_SUCCESS:
        raise ValueError(
            f"upstream native ledger/topology did not complete: {comparison.get('status')!r}"
        )
    _check_time(comparison.get("time_s"), EXPECTED_TIME_S, "upstream comparison time")
    runs = comparison.get("runs")
    observers = comparison.get("observer_results")
    if not isinstance(runs, dict) or set(runs) != set(VARIANTS):
        raise ValueError(f"upstream comparison must contain exactly variants {VARIANTS}")
    if not isinstance(observers, dict) or set(observers) != set(VARIANTS):
        raise ValueError("upstream comparison lacks complete observer records for both variants")
    changed_paths = comparison.get("paired_input_comparison", {}).get("changed_paths")
    if changed_paths != ["0/U", "0/epsilon", "0/k", "case-inputs.json"]:
        raise ValueError(
            "upstream pair frozen-input comparison differs from the declared matched pair"
        )

    records: dict[str, Any] = {}
    for role in VARIANTS:
        observer = observers[role]
        if observer.get("status") != "complete":
            raise ValueError(f"upstream {role} native observer did not complete")
        records[role] = _validate_one_run(role, runs[role], repo_root, observer)
    if records["uniform"]["run_id"] == records["three-component"]["run_id"]:
        raise ValueError("pair members must have distinct run IDs")

    first = records["uniform"]
    second = records["three-component"]
    for key in ("source_area_m2", "source_face_count"):
        if first[key] != second[key]:
            raise ValueError(f"matched pair members disagree on {key}")
    for key in (
        "domain_bounds_m",
        "coordinate_frame",
        "source_geometry",
        "source_patch_areas_m2",
        "source_patch_face_counts",
    ):
        if first["case_inputs"].get(key) != second["case_inputs"].get(key):
            raise ValueError(f"matched pair members disagree on case-input {key}")

    maps = {role: records[role]["raw_hashes"] for role in VARIANTS}
    if set(maps["uniform"]) != set(maps["three-component"]):
        raise ValueError("pair native exports have different raw file inventories")
    allowed_variant_arrays = ("alpha_water.f64", "velocity_xyz_m_s.f64")
    geometry_keys = {key for key in maps["uniform"] if not key.endswith(allowed_variant_arrays)}
    mismatched_geometry = sorted(
        key for key in geometry_keys if maps["uniform"][key] != maps["three-component"][key]
    )
    if mismatched_geometry:
        raise ValueError(
            "native mesh/source exports differ between pair members: "
            + ", ".join(mismatched_geometry[:8])
        )
    changed_arrays = sorted(
        key
        for key in maps["uniform"]
        if key.endswith(allowed_variant_arrays)
        and maps["uniform"][key] != maps["three-component"][key]
    )

    return {
        "comparison": comparison,
        "comparison_path": comparison_path,
        "comparison_sha256": sha256_file(comparison_path),
        "runs": records,
        "native_mesh_hashes_equal_except_alpha_U": True,
        "variant_specific_export_arrays": changed_arrays,
        "variant_export_arrays_identical": not bool(changed_arrays),
        "observed_export_difference": bool(changed_arrays),
    }


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _write_combined_csv(
    output_path: Path, rows_by_variant: dict[str, list[dict[str, str]]]
) -> None:
    rows = []
    for variant, rows_for_variant in rows_by_variant.items():
        rows.extend({"variant": variant, **row} for row in rows_for_variant)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return
    fieldnames = ["variant", *[key for key in rows[0] if key != "variant"]]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot_native_groups(
    axis: Any,
    rows: list[dict[str, str]],
    *,
    x_key: str,
    y_key: str,
    color: str,
    style: str,
    label: str,
) -> None:
    normalized_rows = [{**row, y_key: None if row.get(y_key) == "" else row[y_key]} for row in rows]
    groups = cloud_profiles._native_contiguous_groups(normalized_rows, x_key, y_key)
    for index, group in enumerate(groups):
        axis.plot(
            [float(row[x_key]) for row in group],
            [float(row[y_key]) for row in group],
            color=color,
            linestyle=style,
            linewidth=1.2,
            label=label if index == 0 else None,
        )


def _pair_overlay(
    output_path: Path,
    profile_dirs: dict[str, Path],
    station_spacing_m: float,
    source_area_m2: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    primary_rows, _ = cloud_profiles._read_csv(cloud_profiles.PAPER_PRIMARY_CSV)
    independent_rows, _ = cloud_profiles._read_csv(cloud_profiles.PAPER_INDEPENDENT_CSV)
    paper = cloud_profiles._paper_series(primary_rows, independent_rows)
    cloud_profiles._validate_paper_axes(paper)
    colors = {"uniform": "#d1495b", "three-component": "#00798c"}
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.5), constrained_layout=True)

    axis = axes[0]
    cloud_profiles._plot_digital_groups(
        axis,
        paper["fig6_primary"],
        source="Paper Fig. 6(b), primary read, t=0.5 s",
        color="#174a8b",
        x_key="independent_value",
        y_key="dependent_value",
        x_error_key="read_bound_independent",
        y_error_key="read_bound_dependent",
        group_keys=("segment_id", "branch_id"),
        point_key="point_index",
    )
    cloud_profiles._plot_digital_groups(
        axis,
        paper["fig6_independent"],
        source="Independent Fig. 6(b) read, t=0.5 s",
        color="#7fa6d1",
        x_key="x_value",
        y_key="y_value",
        x_error_key="read_bound_x",
        y_error_key="read_bound_y",
        group_keys=("segment",),
        point_key=None,
    )
    axis.text(
        0.02,
        0.02,
        "Pair snapshots are at t=1 s; no time-mismatched native curve shown.",
        transform=axis.transAxes,
        fontsize=7,
        va="bottom",
    )
    axis.set_title("Fig. 6(b) reference at t=0.5 s")
    axis.set_xlabel("Streamwise distance y (m)")
    axis.set_ylabel("Downward penetration Z (m)")
    axis.grid(True, linewidth=0.3, alpha=0.4)
    axis.legend(fontsize=6.5, loc="best")

    axis = axes[1]
    for variant in VARIANTS:
        rows = [
            row
            for row in _read_rows(profile_dirs[variant] / "penetration_profiles.csv")
            if float(row["station_spacing_m"]) == station_spacing_m
            and float(row["alpha_threshold"]) == 0.001
            and row["origin_choice"] == "source_center"
        ]
        _plot_native_groups(
            axis,
            rows,
            x_key="paper_streamwise_station_center_m",
            y_key="aabb_envelope_downward_front_m",
            color=colors[variant],
            style="-",
            label=f"Native {variant}, t=1 s, alpha>=0.001",
        )
    axis.set_title("Native penetration profiles at t=1 s")
    axis.set_xlabel("Streamwise distance from source center (m)")
    axis.set_ylabel("Full-cell AABB downward front (m)")
    axis.grid(True, linewidth=0.3, alpha=0.4)
    axis.legend(fontsize=6.5, loc="best")

    axis = axes[2]
    cloud_profiles._plot_digital_groups(
        axis,
        paper["fig9_primary"],
        source="Paper Fig. 9(a), primary blue read, t=1 s",
        color="#174a8b",
        x_key="independent_value",
        y_key="dependent_value",
        x_error_key="read_bound_independent",
        y_error_key="read_bound_dependent",
        group_keys=("segment_id", "branch_id"),
        point_key="point_index",
    )
    cloud_profiles._plot_fig9_independent(axis, paper["fig9_independent"])
    for variant in VARIANTS:
        rows = _read_rows(profile_dirs[variant] / "width_profiles.csv")
        for threshold, style in ((0.001, "-"), (0.9, "--")):
            selected = [
                row
                for row in rows
                if float(row["station_spacing_m"]) == station_spacing_m
                and float(row["alpha_threshold"]) == threshold
            ]
            _plot_native_groups(
                axis,
                selected,
                x_key="conditional_depth_over_Lc",
                y_key="conditional_width_over_Lc",
                color=colors[variant],
                style=style,
                label=f"Native {variant} alpha>={threshold:g}",
            )
    axis.set_title("Fig. 9(a) t=1 s, conditional Lc")
    axis.set_xlabel("Downward depth z/Lc")
    axis.set_ylabel("Cross-track width L/Lc")
    axis.grid(True, linewidth=0.3, alpha=0.4)
    axis.legend(fontsize=6.5, loc="best")

    figure.suptitle(
        "Matched local-mesh Dash-8 pair: native polyhedral AABB cloud profiles\n"
        f"Lc=sqrt(case-declared S={source_area_m2:g} m²), conditional; paper numeric S and origin unknown",
        fontsize=10,
    )
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def postprocess_pair(
    comparison_path: Path,
    output_dir: Path,
    *,
    repo_root: Path = ROOT,
    station_spacing_m: float = 0.075,
    analyzer: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    if not math.isfinite(station_spacing_m) or station_spacing_m <= 0:
        raise ValueError("station spacing must be finite and positive")
    output_dir = output_dir if output_dir.is_absolute() else repo_root / output_dir
    output_dir = output_dir.resolve(strict=False)
    runs_root = (repo_root / "results/runs").resolve(strict=True)
    if not output_dir.is_relative_to(runs_root):
        raise ValueError(f"output must be under {runs_root}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_dir}")

    upstream = validate_upstream_comparison(comparison_path, repo_root)
    analyzer = analyzer or cloud_profiles.analyze
    output_dir.mkdir(parents=True, exist_ok=False)
    summary_path = output_dir / "pair_summary.json"
    summary: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "status": "running",
        "created_utc": dt.datetime.now(dt.UTC).isoformat(),
        "classification": "exploratory native full-cell AABB envelope observer; not detector equivalence or E2 validation",
        "upstream_comparison_path": str(upstream["comparison_path"]),
        "upstream_comparison_sha256": upstream["comparison_sha256"],
        "upstream_comparison_status": upstream["comparison"].get("status"),
        "saved_time_s": EXPECTED_TIME_S,
        "station_spacing_m": station_spacing_m,
        "native_mesh_hashes_equal_except_alpha_U": upstream[
            "native_mesh_hashes_equal_except_alpha_U"
        ],
        "variant_specific_export_arrays": upstream["variant_specific_export_arrays"],
        "variant_export_arrays_identical": upstream["variant_export_arrays_identical"],
        "observed_export_difference": upstream["observed_export_difference"],
        "runs": {},
        "paper_overlay": None,
    }
    _write_json(summary_path, summary)
    try:
        outputs: dict[str, Path] = {}
        reports: dict[str, dict[str, Any]] = {}
        profile_rows: dict[str, dict[str, list[dict[str, str]]]] = {}
        for variant in VARIANTS:
            record = upstream["runs"][variant]
            role_output = output_dir / variant
            report = analyzer(
                record["raw_export_directory"],
                record["case_inputs_path"],
                role_output,
                station_spacing_m,
            )
            fresh_hashes = _sha_manifest(
                role_output / "native_export_hashes.json", f"{variant} analyzer hash manifest"
            )
            if fresh_hashes != record["raw_hashes"]:
                raise ValueError(
                    f"{variant} native export files differ from the upstream sealed hash manifest"
                )
            if sha256_file(upstream["comparison_path"]) != upstream["comparison_sha256"]:
                raise ValueError("upstream comparison changed during profile analysis")
            outputs[variant] = role_output
            reports[variant] = report
            profile_rows[variant] = {
                "penetration": _read_rows(role_output / "penetration_profiles.csv"),
                "width": _read_rows(role_output / "width_profiles.csv"),
            }
            summary["runs"][variant] = {
                "run_id": record["run_id"],
                "run_directory": str(record["run_directory"]),
                "case_directory": str(record["case_directory"]),
                "run_manifest_sha256": record["manifest_sha256"],
                "case_inputs_sha256": record["case_inputs_sha256"],
                "solver_log": record["solver_log"],
                "saved_checkpoint_field_count": len(record["checkpoint_field_sha256"]),
                "saved_checkpoint_field_hashes_sha256": hashlib.sha256(
                    json.dumps(record["checkpoint_field_sha256"], sort_keys=True).encode()
                ).hexdigest(),
                "source_patch": SOURCE_PATCH,
                "source_face_count": record["source_face_count"],
                "source_area_m2": record["source_area_m2"],
                "native_cells": report["snapshot"]["native_cell_count"],
                "native_topology": record["native_analysis"]["topology"],
                "native_export_hash_manifest_sha256": report["provenance"][
                    "export_hash_manifest_sha256"
                ],
                "upstream_native_topology_analysis_sha256": record["native_analysis_sha256"],
                "native_cloud_analysis_sha256": sha256_file(role_output / "analysis.json"),
                "native_cloud_analysis_path": str(role_output / "analysis.json"),
                "penetration_profile_path": str(role_output / "penetration_profiles.csv"),
                "width_profile_path": str(role_output / "width_profiles.csv"),
                "paper_overlay_path": str(role_output / "paper_cloud_comparison.png"),
                "paper_overlay_sha256": sha256_file(role_output / "paper_cloud_comparison.png"),
                "source_field_hashes_match_upstream": True,
            }

        areas = [reports[v]["normalization"]["source_area_m2"] for v in VARIANTS]
        if not math.isclose(areas[0], areas[1], rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("analyzed pair source areas differ; cannot share a paper overlay")
        _write_combined_csv(
            output_dir / "combined_penetration_profiles.csv",
            {variant: profile_rows[variant]["penetration"] for variant in VARIANTS},
        )
        _write_combined_csv(
            output_dir / "combined_width_profiles.csv",
            {variant: profile_rows[variant]["width"] for variant in VARIANTS},
        )
        overlay = output_dir / "matched_pair_profile_comparison.png"
        _pair_overlay(overlay, outputs, station_spacing_m, areas[0])
        summary["status"] = "complete"
        summary["combined_penetration_profiles_csv"] = str(
            output_dir / "combined_penetration_profiles.csv"
        )
        summary["combined_width_profiles_csv"] = str(output_dir / "combined_width_profiles.csv")
        summary["paper_overlay"] = {"path": str(overlay), "sha256": sha256_file(overlay)}
        summary["limits"] = [
            "Native cloud bounds use selected full-cell AABBs, not reconstructed alpha isosurfaces.",
            "Per-slab native water inventory is assigned by cell center; it is not partial-cell overlap integration.",
            "The paper outlet area and registration origin are unspecified; normalized Fig. 9 coordinates remain conditional on each case's declared area.",
            "The pair has t=1 s native profiles; Fig. 6(b) is shown at t=0.5 s without a time-mismatched native curve.",
            "Native component/connectivity and profile observers are not asserted equivalent to the paper's unpublished MATLAB detector.",
        ]
        summary["finished_utc"] = dt.datetime.now(dt.UTC).isoformat()
        _write_json(summary_path, summary)
        return summary
    except Exception as error:
        summary["status"] = "native_cloud_pair_postprocess_failed_solver_cases_preserved"
        summary["error"] = f"{type(error).__name__}: {error}"
        summary["finished_utc"] = dt.datetime.now(dt.UTC).isoformat()
        _write_json(summary_path, summary)
        raise


def _observer_failure(report_path: Path) -> str | None:
    if not report_path.is_file():
        return None
    try:
        record = _load_json(report_path, "upstream observer")
    except ValueError:
        return None
    status = record.get("status")
    if status in {
        "pair_schedule_failed_or_incomplete_no_cfd_retry",
        "pair_member_failed_or_missing_no_cfd_retry",
        "native_postprocess_failed_solver_results_preserved_no_cfd_retry",
        "native_postprocess_incomplete_no_cfd_retry",
        "wait_timeout_before_scheduler_terminal",
    }:
        return str(status)
    return None


def wait_and_process(
    comparison_path: Path,
    output_dir: Path,
    *,
    observer_report: Path,
    wait_state_path: Path,
    repo_root: Path = ROOT,
    wait_timeout_s: float = 72 * 3600,
    poll_seconds: float = 30.0,
    station_spacing_m: float = 0.075,
    analyzer: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if wait_timeout_s <= 0 or poll_seconds <= 0:
        raise ValueError("wait timeout and polling period must be positive")
    wait_state_path = wait_state_path.resolve(strict=False)
    if wait_state_path.exists():
        raise FileExistsError(f"refusing to overwrite wait-state report: {wait_state_path}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_dir}")
    wait_state = {
        "schema": "dash8-native-cloud-pair-wait-v1",
        "status": "waiting_for_upstream_native_comparison",
        "created_utc": dt.datetime.now(dt.UTC).isoformat(),
        "comparison_path": str(comparison_path.resolve(strict=False)),
        "observer_report_path": str(observer_report.resolve(strict=False)),
        "render_success_required": False,
    }
    _write_json(wait_state_path, wait_state)
    deadline = time.monotonic() + wait_timeout_s
    upstream_failure = None
    while time.monotonic() < deadline:
        if comparison_path.is_file():
            try:
                comparison = _load_json(comparison_path, "upstream pair comparison")
            except ValueError:
                comparison = {}
            status = comparison.get("status")
            if status == UPSTREAM_SUCCESS:
                wait_state["status"] = "upstream_native_success_proof_seen"
                wait_state["upstream_comparison_sha256"] = sha256_file(comparison_path)
                _write_json(wait_state_path, wait_state)
                result = postprocess_pair(
                    comparison_path,
                    output_dir,
                    repo_root=repo_root,
                    station_spacing_m=station_spacing_m,
                    analyzer=analyzer,
                )
                wait_state["status"] = "complete"
                wait_state["downstream_summary_path"] = str(output_dir / "pair_summary.json")
                wait_state["finished_utc"] = dt.datetime.now(dt.UTC).isoformat()
                _write_json(wait_state_path, wait_state)
                return result
            if status in UPSTREAM_FAILURES:
                upstream_failure = str(status)
                break
        upstream_failure = _observer_failure(observer_report)
        if upstream_failure:
            break
        time.sleep(poll_seconds)

    if upstream_failure is None:
        wait_state["status"] = "wait_timeout_before_native_success_proof"
        wait_state["wait_timeout_s"] = wait_timeout_s
    else:
        wait_state["status"] = "upstream_failure_no_cloud_profiles_created"
        wait_state["upstream_failure_status"] = upstream_failure
    wait_state["finished_utc"] = dt.datetime.now(dt.UTC).isoformat()
    _write_json(wait_state_path, wait_state)
    raise RuntimeError(wait_state["status"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--station-spacing-m", type=float, default=0.075)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--observer-report", type=Path)
    parser.add_argument("--wait-state-json", type=Path)
    parser.add_argument("--wait-timeout-s", type=float, default=72 * 3600)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        if args.wait:
            if args.observer_report is None or args.wait_state_json is None:
                parser.error("--wait requires --observer-report and --wait-state-json")
            report = wait_and_process(
                args.comparison,
                args.output_dir,
                observer_report=args.observer_report,
                wait_state_path=args.wait_state_json,
                wait_timeout_s=args.wait_timeout_s,
                poll_seconds=args.poll_seconds,
                station_spacing_m=args.station_spacing_m,
            )
        else:
            report = postprocess_pair(
                args.comparison, args.output_dir, station_spacing_m=args.station_spacing_m
            )
        print(
            json.dumps(
                {"status": report["status"], "summary": str(args.output_dir / "pair_summary.json")}
            )
        )
        return 0
    except (FileExistsError, OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        print(f"native cloud pair postprocess failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
