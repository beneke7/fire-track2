#!/usr/bin/env pvpython
"""Read-only, descriptive alpha=0.1 plane profiles for the stored 0.05 s case."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

from vtkmodules.vtkCommonCore import vtkSMPTools
from paraview.simple import OpenFOAMReader, Slice, Threshold


TARGET_TIME = 0.05
DIAMETER_M = 0.4
ALPHA_CLOUD = 0.1
X_STATIONS_M = (0.0, 0.1, 0.2, 0.3, 0.4, 0.8, 1.6, 3.2)
EXPECTED_CELLS = 10_099_265
THREADS = 8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def array_info(data_info) -> dict:
    arrays = data_info.GetCellDataInformation()
    output = {}
    for index in range(arrays.GetNumberOfArrays()):
        array = arrays.GetArrayInformation(index)
        output[array.GetName()] = {
            "components": array.GetNumberOfComponents(),
            "component_ranges": [
                [float(value) for value in array.GetComponentRange(component)]
                for component in range(array.GetNumberOfComponents())
            ],
        }
    return output


def load_digitization(path: Path) -> dict[str, dict[float, dict]]:
    result: dict[str, dict[float, dict]] = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            x = float(row["x_over_dj"])
            result.setdefault(row["observable"], {})[x] = row
    return result


def reference_at(reference: dict[str, dict[float, dict]], observable: str, x_over_d: float) -> dict | None:
    rows = reference.get(observable, {})
    matched_x = next((x for x in rows if math.isclose(x, x_over_d, rel_tol=0.0, abs_tol=1e-9)), None)
    if matched_x is None:
        return None
    row = rows[matched_x]
    if "value_over_dj" in row:
        return {
            "method": "primary vector-path digitization",
            "value_over_D": float(row["value_over_dj"]),
            "sigma_value_over_D": float(row["sigma_value_over_dj"]),
            "sigma_x_over_D": float(row["sigma_x_over_dj"]),
        }
    return {
        "method": "independent raster trace",
        "value_over_D": float(row["value_over_dj_raster"]),
        "sigma_value_over_D": float(row["sigma_raster_bound"]),
        "source_value_over_D": float(row["source_value_over_dj"]),
        "source_sigma_value_bound_over_D": float(row["source_sigma_value_bound"]),
        "source_sigma_x_bound_over_D": float(row["source_sigma_x_bound"]),
    }


def bounds_or_none(data_info) -> list[float] | None:
    if data_info.GetNumberOfCells() <= 0:
        return None
    bounds = [float(value) for value in data_info.GetBounds()]
    if not all(math.isfinite(value) for value in bounds):
        return None
    return bounds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--primary-csv", type=Path, required=True)
    parser.add_argument("--raster-csv", type=Path, required=True)
    parser.add_argument("--comparison-manifest", type=Path, required=True)
    parser.add_argument("--provenance-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = args.case.expanduser().resolve()
    primary_csv = args.primary_csv.expanduser().resolve()
    raster_csv = args.raster_csv.expanduser().resolve()
    comparison_manifest = args.comparison_manifest.expanduser().resolve()
    provenance_json = args.provenance_json.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    for path in (case, primary_csv, raster_csv, comparison_manifest, provenance_json):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output_path.exists():
        raise FileExistsError(output_path)

    vtkSMPTools.Initialize(THREADS)
    if vtkSMPTools.GetEstimatedNumberOfThreads() != THREADS:
        raise RuntimeError(f"VTK did not honor the selected {THREADS}-thread worker budget")

    primary_data = load_digitization(primary_csv)
    raster_data = load_digitization(raster_csv)
    source_manifest = json.loads(comparison_manifest.read_text())
    provenance = json.loads(provenance_json.read_text())
    expected_source_hashes = {
        item["path"]: item["sha256"] for item in source_manifest["paper_reference"]["local_files"]
    }
    for path in (primary_csv, raster_csv):
        expected_hash = expected_source_hashes.get(str(path.relative_to(Path.cwd().resolve())))
        if expected_hash is None or sha256(path) != expected_hash:
            raise RuntimeError(f"reference source hash does not match the comparison manifest: {path}")

    reader = OpenFOAMReader(registrationName="Rouaix stored 0.05 s fields", FileName=str(case))
    reader.CaseType = "Decomposed Case"
    reader.SkipZeroTime = 0
    reader.MeshRegions = ["internalMesh"]
    reader.CellArrays = ["alpha.water", "U"]
    reader.UpdatePipelineInformation()
    times = sorted(float(value) for value in reader.TimestepValues)
    if times != [0.0, TARGET_TIME]:
        raise RuntimeError(f"expected exactly stored times [0, {TARGET_TIME}], got {times}")
    reader.UpdatePipeline(time=TARGET_TIME)
    raw_info = reader.GetDataInformation()
    raw_names = set(array_info(raw_info))
    if raw_info.GetNumberOfCells() != EXPECTED_CELLS:
        raise RuntimeError(f"expected {EXPECTED_CELLS} cells, got {raw_info.GetNumberOfCells()}")
    if not {"alpha.water", "U"}.issubset(raw_names):
        raise RuntimeError(f"required fields are missing: {sorted(raw_names)}")

    cloud = Threshold(registrationName="whole cells with alpha.water >= 0.1", Input=reader)
    cloud.Scalars = ["CELLS", "alpha.water"]
    cloud.ThresholdMethod = "Between"
    cloud.LowerThreshold = ALPHA_CLOUD
    cloud.UpperThreshold = 1.0
    cloud.UpdatePipeline(time=TARGET_TIME)
    cloud_info = cloud.GetDataInformation()
    cloud_bounds = bounds_or_none(cloud_info)
    cloud_summary = {
        "threshold": "CELL alpha.water >= 0.1 and <= 1.0",
        "cell_count": cloud_info.GetNumberOfCells(),
        "bounds_m": cloud_bounds,
        "bounds_x_over_D": [cloud_bounds[0] / DIAMETER_M, cloud_bounds[1] / DIAMETER_M] if cloud_bounds else None,
        "penetration_h_m": -cloud_bounds[2] if cloud_bounds else None,
        "penetration_h_over_D": -cloud_bounds[2] / DIAMETER_M if cloud_bounds else None,
        "z_low_m": cloud_bounds[4] if cloud_bounds else None,
        "z_high_m": cloud_bounds[5] if cloud_bounds else None,
        "full_span_m": cloud_bounds[5] - cloud_bounds[4] if cloud_bounds else None,
        "half_span_m": (cloud_bounds[5] - cloud_bounds[4]) / 2 if cloud_bounds else None,
    }
    print(json.dumps({"cloud_threshold_global": cloud_summary}), flush=True)

    slices = []
    for x_m in X_STATIONS_M:
        section = Slice(registrationName=f"alpha10 plane x={x_m:g} m", Input=cloud)
        section.SliceType = "Plane"
        section.SliceType.Origin = [x_m, 0.0, 0.0]
        section.SliceType.Normal = [1.0, 0.0, 0.0]
        section.UpdatePipeline(time=TARGET_TIME)
        info = section.GetDataInformation()
        bounds = bounds_or_none(info)
        x_over_d = x_m / DIAMETER_M
        matching_penetration = reference_at(primary_data, "penetration_y", x_over_d)
        matching_width = reference_at(primary_data, "width_z", x_over_d)
        raster_penetration = reference_at(raster_data, "penetration_y", x_over_d)
        raster_width = reference_at(raster_data, "width_z", x_over_d)
        row = {
            "x_m": x_m,
            "x_over_D": x_over_d,
            "slice_cut_cell_count": info.GetNumberOfCells(),
            "status": "nonempty alpha>=0.1 slice" if bounds else "no retained alpha>=0.1 cells intersect this plane",
            "bounds_m": bounds,
            "penetration_h_m": -bounds[2] if bounds else None,
            "penetration_h_over_D": -bounds[2] / DIAMETER_M if bounds else None,
            "z_low_m": bounds[4] if bounds else None,
            "z_high_m": bounds[5] if bounds else None,
            "full_span_m": bounds[5] - bounds[4] if bounds else None,
            "half_span_m": (bounds[5] - bounds[4]) / 2 if bounds else None,
            "full_span_over_D": (bounds[5] - bounds[4]) / DIAMETER_M if bounds else None,
            "half_span_over_D": (bounds[5] - bounds[4]) / (2 * DIAMETER_M) if bounds else None,
            "figure13_primary_reference": {
                "penetration_h_over_D": matching_penetration,
                "reported_z_over_D": matching_width,
            },
            "figure13_independent_raster_reference": {
                "penetration_h_over_D": raster_penetration,
                "reported_z_over_D": raster_width,
            },
            "comparison_note": (
                "digitized x/D values only; no interpolation/extrapolation"
                if any((matching_penetration, matching_width, raster_penetration, raster_width))
                else "no digitized point at this x/D; not interpolated"
            ),
            "origin_note": (
                "the shared x/D=0 digitizer origin is a nozzle-axis convention, not a physical t=0 comparison"
                if math.isclose(x_over_d, 0.0)
                else None
            ),
        }
        slices.append(row)
        print(json.dumps({"plane": row}), flush=True)

    output = {
        "schema": "rouaix-startup-snapshot-description-v1",
        "analysis_kind": "read-only descriptive startup comparison; not an E1 gate or formal Figure 13 curve comparison",
        "created_unix_time": time.time(),
        "case": {
            "case_id": provenance["source"]["case"],
            "solver": provenance["source"]["solver"],
            "marker": str(case),
            "case_type": "Decomposed Case",
            "stored_times_s": times,
            "selected_time_s": TARGET_TIME,
            "source_archive_path": provenance["source"]["source_archive_local"],
            "source_archive_bytes": provenance["source"]["source_archive_bytes"],
            "expected_source_archive_sha256": provenance["source"]["source_archive_sha256"],
            "reader_cells": raw_info.GetNumberOfCells(),
            "reader_bounds_m": bounds_or_none(raw_info),
            "cell_array_ranges": array_info(raw_info),
            "demux_manifest_path": str(case.parent / "demux-manifest.json"),
            "demux_manifest_sha256": sha256(case.parent / "demux-manifest.json"),
        },
        "geometry_method": {
            "cloud": "whole-cell VTK Threshold of cell alpha.water >= 0.1, then independent normal-+x Slice plane intersections",
            "paper_equivalence": False,
            "paper_detector": "Rouaix Figure 13 uses the chi=0.1 cloud envelope; this whole-cell VTK proxy is not the exact paper surface detector",
            "coordinates": {
                "x": "streamwise positive crossflow, x=0 at nozzle center",
                "y": "upward positive; source plane y0=0 m; penetration h=-y_low",
                "z": "native signed spanwise coordinate",
                "D_m": DIAMETER_M,
            },
            "cell_scale_uncertainty_note": "Bounds are cell-threshold/plane-intersection envelopes on a mixed mesh nominally 14/56 mm; local extent uncertainty is of order the local cell pitch (~14 mm in the fine near-nozzle region) and varies with x/z. This is a resolution scale, not a statistical error bar.",
            "station_policy": "Each requested plane is processed independently; empty planes remain null and no interpolation is made between stations.",
            "width_interpretation": "Keep signed z_low/z_high, full span, and half of the full span; compare both span interpretations with the unchanged paper z/D because the paper does not define half-width versus full-width.",
        },
        "cloud_threshold_global": cloud_summary,
        "startup_age_scale_context": {
            "formula": "v_j * t + 0.5 * g * t^2",
            "v_j_m_s": 10.0,
            "gravity_m_s2": 9.81,
            "time_s": TARGET_TIME,
            "ballistic_travel_scale_m": 10.0 * TARGET_TIME + 0.5 * 9.81 * TARGET_TIME**2,
            "observed_alpha01_downward_extent_m": cloud_summary["penetration_h_m"],
            "note": "A startup age-scale check only; not a Figure 13 detector match, acceptance tolerance, or physical validation metric.",
        },
        "slices": slices,
        "paper_context": {
            "case": "Rouaix et al. (2023) single-nozzle Case 1, Table 3, q=17.3, D=0.4 m, v_j=10 m/s, u_g=70 m/s",
            "figure13": "PDF p. 13 / printed article p. 12, green plus series; PDF p. 6 / article p. 5 states chi=0.1 for the cloud envelope",
            "figure13_sample_time": "not stated; do not equate Figure 1's 4.5 s illustration or the paper's roughly 5 s run duration with the Figure 13 sampling time",
            "primary_digitization_csv": str(primary_csv),
            "primary_digitization_sha256": sha256(primary_csv),
            "raster_digitization_csv": str(raster_csv),
            "raster_digitization_sha256": sha256(raster_csv),
            "source_record": str(comparison_manifest),
            "source_record_sha256": sha256(comparison_manifest),
            "source_files_with_recorded_hashes": source_manifest["paper_reference"]["local_files"],
            "breakup_context": "The generic q=17.3 Figure 16 marker is about x_BU/D=8.91 and y_BU/D=10.04 (roughly x=3.56 m, h=4.02 m), with ~0.25D plot-read uncertainty; Cases 1, 8 and 9 share q, so it is not Case-1-specific.",
        },
        "interpretation_limits": [
            "The current fields are a 0.05 s startup snapshot, not the paper's developed roughly five-second calculation; the Figure 13 sampling time is unspecified.",
            "Only exact digitized x/D points are reported. No interpolation is made where a point is absent, including x/D=8 penetration and x/D=4,8 width.",
            "At x/D=0, the plotted zero is a shared nozzle-axis digitizer convention and is not a time-zero match.",
            "These measurements can show early geometry and order-of-magnitude source compatibility only; they cannot establish developed-cloud agreement, E1 acceptance, validation, or a solver success/failure decision.",
            "No momentum closure, source-connected core, breakup location, or physical validation was computed.",
        ],
        "execution": {
            "vtk_smp_threads": THREADS,
            "render_called": False,
            "cfd_rerun": False,
            "hpc_job": False,
            "working_directory": str(Path.cwd().resolve()),
            "analysis_script": str(Path("results/runs/rouaix-startup-comparison-20261026/analyze_startup_snapshot.py").resolve()),
            "analysis_script_sha256": sha256(Path("results/runs/rouaix-startup-comparison-20261026/analyze_startup_snapshot.py").resolve()),
            "exact_command": "python3 scripts/run_local.py --threads 8 --timeout 900 -- /Applications/ParaView-6.1.1.app/Contents/bin/pvpython results/runs/rouaix-startup-comparison-20261026/analyze_startup_snapshot.py --case results/runs/rouaix-one-node-paraview-20261026/unpacked-display-case/decomposed-case-verified/rouaix-display.foam --primary-csv data/derived/rouaix_e1_case1_fig13.csv --raster-csv data/derived/rouaix_e1_case1_fig13_raster.csv --comparison-manifest results/runs/rouaix-5s-comparison-prep-20261026/comparison-manifest.json --provenance-json results/runs/rouaix-one-node-paraview-20261026/paraview/handoff.json --output results/runs/rouaix-startup-comparison-20261026/startup-comparison.json",
        },
    }
    output_path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"output": str(output_path), "output_sha256": sha256(output_path)}, indent=2))


if __name__ == "__main__":
    main()
