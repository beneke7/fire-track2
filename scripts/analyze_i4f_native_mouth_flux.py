#!/usr/bin/env python3
"""Extract saved native alphaPhi0.water on offset I4F FV control surfaces."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aerial_drop.i4f_native_mouth_flux import (  # noqa: E402
    read_native_apparatus_control_surface_flux,
    sha256,
    snapshot_to_dict,
)


def _write_csv(path: Path, data: dict[str, Any]) -> None:
    rows = data["control_surface_fluxes"]
    cut_by_mouth = {row["mouth"]: row for row in data["existing_xplane_cut_comparison"]["by_mouth"]}
    stl_by_mouth = data["physical_geometry_reference"].get("mouths", {})
    fields = (
        "case",
        "time_s",
        "mouth",
        "flux_units",
        "flux_sign",
        "phase_mass_conversion",
        "native_face_count",
        "fv_control_surface_mag_sf_m2",
        "absolute_first_vertex_fan_area_m2",
        "nominal_window_plane_area_m2",
        "stl_branch_cap_plane_x_m",
        "stl_branch_cap_projected_area_m2",
        "sum_oriented_sf_x_m2",
        "sum_absolute_face_sf_x_m2",
        "projected_sf_x_to_nominal_window_area_ratio",
        "projected_sf_x_to_stl_cap_area_ratio",
        "mag_sf_to_stl_cap_area_ratio",
        "net_water_volume_flux_m3_s",
        "forward_water_volume_flux_m3_s",
        "reverse_water_volume_flux_m3_s",
        "sum_absolute_water_volume_flux_m3_s",
        "centroid_xyz_m",
        "x_min_m",
        "x_max_m",
        "vertex_bounds_xyz_m",
        "sum_oriented_sf_xyz_m2",
        "area_weighted_mean_face_normal_xyz",
        "resultant_outward_unit_normal_xyz",
        "face_normal_component_bounds_xyz",
        "projected_x_offset_integral_to_branch_cap_m3",
        "projected_x_offset_integral_to_ambient_plane_m3",
        "buffer_volume_between_fv_surface_and_branch_cap_m3",
        "buffer_volume_status",
        "perimeter_edge_count",
        "perimeter_edge_patch_coverage",
        "uncovered_perimeter_edge_count",
        "xplane_cut_x_m",
        "xplane_projected_area_m2",
        "xplane_native_water_Q_m3_s",
        "control_minus_xplane_Q_m3_s",
        "relative_difference_when_resolved",
        "comparison_state",
    )
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            mouth_stl = stl_by_mouth.get(row["mouth"], {})
            xplane = cut_by_mouth[row["mouth"]]
            constants = {
                "flux_units": data["quantity"]["units"],
                "flux_sign": data["quantity"]["sign"],
                "phase_mass_conversion": data["quantity"]["phase_mass_conversion"],
                "stl_branch_cap_plane_x_m": mouth_stl.get("plane_x_m"),
                "xplane_cut_x_m": xplane["xplane_cut_x_m"],
                "xplane_projected_area_m2": xplane["xplane_projected_area_m2"],
                "xplane_native_water_Q_m3_s": xplane["xplane_native_water_Q_m3_s"],
                "control_minus_xplane_Q_m3_s": xplane["control_minus_xplane_Q_m3_s"],
                "relative_difference_when_resolved": xplane["relative_difference_when_resolved"],
                "comparison_state": xplane["comparison_state"],
            }
            writer.writerow(
                {
                    "case": data["case"],
                    "time_s": data["time_s"],
                    **{
                        key: json.dumps(row[key], separators=(",", ":"))
                        if isinstance(row[key], (dict, list, tuple))
                        else row[key]
                        for key in fields
                        if key
                        not in {
                            "case",
                            "time_s",
                            "flux_units",
                            "flux_sign",
                            "phase_mass_conversion",
                            "stl_branch_cap_plane_x_m",
                            "xplane_cut_x_m",
                            "xplane_projected_area_m2",
                            "xplane_native_water_Q_m3_s",
                            "control_minus_xplane_Q_m3_s",
                            "relative_difference_when_resolved",
                            "comparison_state",
                        }
                    },
                    **constants,
                }
            )


def run(case: Path, time_name: str, output_dir: Path, nprocs: int) -> tuple[Path, Path]:
    case = case.resolve()
    output_dir = output_dir.resolve()
    try:
        output_dir.relative_to(case)
    except ValueError:
        pass
    else:
        raise ValueError("output directory must not be inside the source case")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")

    snapshot = read_native_apparatus_control_surface_flux(case, time_name, nprocs=nprocs)
    data = snapshot_to_dict(snapshot)
    data["created_utc"] = datetime.now(timezone.utc).isoformat()
    data["analysis_code_sha256"] = {
        "module": sha256(ROOT / "src/aerial_drop/i4f_native_mouth_flux.py"),
        "script": sha256(Path(__file__).resolve()),
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    json_path = output_dir / "native-apparatus-control-surface-flux.json"
    csv_path = output_dir / "native-apparatus-control-surface-flux.csv"
    with json_path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
    _write_csv(csv_path, data)
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True, help="case directory (read-only)")
    parser.add_argument("--time", required=True, help="selected saved time directory name")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="new analysis output directory"
    )
    parser.add_argument("--nprocs", type=int, default=10)
    args = parser.parse_args()
    json_path, csv_path = run(args.case, args.time, args.output_dir, args.nprocs)
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
