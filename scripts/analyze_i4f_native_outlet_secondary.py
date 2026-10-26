#!/usr/bin/env python3
"""Apply the shared secondary metrics to native four-mouth I4F data.

``alphaPhi0.water`` on native cell-centre cut faces is the primary liquid-flow
quantity. Face U and raw alpha are reconstructed from saved cell fields and
remain qualified secondary diagnostics. The in-repository reader supports the
current compact four-mouth geometry and ten-rank collated checkpoints.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
METRIC_SOURCE = ROOT / "src/aerial_drop/i4f_outlet_metrics.py"
READER_SOURCE = ROOT / "src/aerial_drop/i4f_native_face_reader.py"
NPROCS = 10
RHO_WATER = 998.2
NORMAL_X = np.asarray([1.0, 0.0, 0.0], dtype=np.float64)
DRY_ABS_NATIVE_FLUX_THRESHOLD_M3_S = 1e-12

sys.path.insert(0, str(ROOT / "src"))
from aerial_drop.i4f_native_face_reader import (  # noqa: E402
    MOUTH_WINDOWS,
    READER_EXTRACTION_PROVENANCE,
    read_native_mouth_snapshot,
)
from aerial_drop.i4f_outlet_metrics import outlet_secondary_metrics  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def summarize_face_inputs(
    rows_by_mouth: dict[str, list[dict[str, Any]]],
    *,
    time_s: float,
    case_label: str,
) -> list[dict[str, Any]]:
    """Call the canonical secondary metric helper for each mouth partition."""
    output = []
    for mouth in rows_by_mouth:
        rows = rows_by_mouth[mouth]
        if not rows:
            raise ValueError(f"no native faces assigned to mouth {mouth}")
        q = np.asarray([row["native_water_flux_m3_s"] for row in rows], dtype=np.float64)
        u = np.asarray([row["velocity_face_xyz_m_s"] for row in rows], dtype=np.float64)
        area = np.asarray([row["outward_projected_area_m2"] for row in rows], dtype=np.float64)
        alpha = np.asarray([row["alpha_water_face_raw"] for row in rows], dtype=np.float64)
        metrics = outlet_secondary_metrics(
            water_volume_flux_m3_s=q,
            velocity_face_xyz_m_s=u,
            projected_area_m2=area,
            outlet_normal_unit_xyz=NORMAL_X,
            alpha_water_face_raw=alpha,
            water_density_kg_m3=RHO_WATER,
            water_flux_stage_label="native saved alphaPhi0.water at selected checkpoint",
            velocity_stage_label="neighbor-cell U linearly reconstructed to native x<=4.8 m cut face",
        )
        total_abs_q = float(np.sum(np.abs(q)))
        dry = total_abs_q <= DRY_ABS_NATIVE_FLUX_THRESHOLD_M3_S
        # Preserve raw helper results but do not interpret directional or
        # momentum outputs when native liquid flux is only numerical trace.
        reported = {
            "outward_direction_mean_angle_deg_q_weighted": (
                None if dry else metrics["outward_direction_mean_angle_deg_q_weighted"]
            ),
            "outward_direction_rms_angle_deg_q_weighted": (
                None if dry else metrics["outward_direction_rms_angle_deg_q_weighted"]
            ),
            "water_momentum_flux_net_reconstructed_N_xyz": (
                None if dry else metrics["water_momentum_flux_net_reconstructed_N_xyz"]
            ),
            "water_momentum_flux_outward_reconstructed_N_xyz": (
                None if dry else metrics["water_momentum_flux_outward_reconstructed_N_xyz"]
            ),
            "water_momentum_flux_reverse_signed_reconstructed_N_xyz": (
                None if dry else metrics["water_momentum_flux_reverse_signed_reconstructed_N_xyz"]
            ),
        }
        output.append(
            {
                "case_label": case_label,
                "time_s": time_s,
                "mouth": mouth,
                "native_face_count": len(rows),
                "native_alphaPhi0_water_Q_net_m3_s": float(np.sum(q)),
                "native_alphaPhi0_water_Q_absolute_m3_s": total_abs_q,
                "native_area_projected_x_m2": float(np.sum(area)),
                "flux_state": "dry_or_near_zero_native_liquid_trace"
                if dry
                else "liquid_flux_present",
                "reported_secondary_metrics": reported,
                "secondary_metrics_helper_raw": metrics,
            }
        )
    return output


def _optional_reference_comparison(
    reference_path: Path | None,
    case_bundle: Path,
    time_s: float,
    mouth_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if reference_path is None:
        return {"status": "not requested"}
    reference = json.loads(reference_path.read_text())
    case_key = _display_path(case_bundle)
    match = next(
        (
            item
            for item in reference.get("cases", [])
            if item.get("case_bundle") == case_key
            and math.isclose(float(item.get("time_s", math.nan)), time_s, abs_tol=1e-12)
        ),
        None,
    )
    if match is None:
        return {
            "status": "no matching case/time in optional reference",
            "reference_path": _display_path(reference_path),
            "reference_sha256": sha256(reference_path),
        }
    expected = {
        item["mouth"]: float(item["native_alphaPhi0_water_Q_net_m3_s"])
        for item in match["per_mouth"]
    }
    comparisons = []
    for row in mouth_rows:
        actual = float(row["native_alphaPhi0_water_Q_net_m3_s"])
        prior = expected[row["mouth"]]
        difference = actual - prior
        if not math.isclose(actual, prior, rel_tol=1e-12, abs_tol=1e-300):
            raise ValueError(
                f"native Q differs from optional reference for {row['mouth']}: {actual} vs {prior}"
            )
        comparisons.append(
            {
                "mouth": row["mouth"],
                "adapter_native_Q_m3_s": actual,
                "reference_native_Q_m3_s": prior,
                "difference_m3_s": difference,
                "relative_difference": difference / prior if prior != 0 else 0.0,
            }
        )
    return {
        "status": "matched per-mouth native alphaPhi0 integrals",
        "reference_path": _display_path(reference_path),
        "reference_sha256": sha256(reference_path),
        "comparisons": comparisons,
    }


def run(
    case_bundle: Path,
    time_name: str,
    output_dir: Path,
    reference_v2_summary: Path | None = None,
) -> tuple[Path, Path]:
    case_bundle = case_bundle.resolve()
    case = case_bundle / "case"
    if not case.is_dir():
        raise FileNotFoundError(f"run bundle has no case/ directory: {case_bundle}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")

    snapshot = read_native_mouth_snapshot(case, time_name, nprocs=NPROCS)
    faces_by_mouth: dict[str, list[dict[str, Any]]] = {name: [] for name in MOUTH_WINDOWS}
    orientation_counts = {"outward_positive_projected_area": 0, "nonpositive_projected_area": 0}
    for mouth, faces in snapshot.mouth_faces.items():
        for face in faces:
            if face.outward_projected_area_m2 <= 0.0:
                orientation_counts["nonpositive_projected_area"] += 1
                raise ValueError(
                    f"native face {face.global_face_id} has nonpositive outward projected area"
                )
            orientation_counts["outward_positive_projected_area"] += 1
            faces_by_mouth[mouth].append(
                {
                    "native_face_id": face.global_face_id,
                    "native_water_flux_m3_s": face.native_alpha_phi_water_m3_s,
                    "native_phi_mixture_m3_s": face.native_phi_m3_s,
                    "outward_projected_area_m2": face.outward_projected_area_m2,
                    "native_polygon_area_m2": face.native_polygon_area_m2,
                    "velocity_face_xyz_m_s": face.reconstructed_velocity_xyz_m_s,
                    "alpha_water_face_raw": face.reconstructed_alpha_water_raw,
                    "interpolation_weight": face.interpolation_weight,
                    "face_center_xyz_m": face.centroid_xyz_m,
                    "face_map_sign": face.face_map_sign,
                    "record_kind": face.record_kind,
                }
            )
    mouth_rows = summarize_face_inputs(
        faces_by_mouth, time_s=snapshot.time_value_s, case_label=case_bundle.name
    )
    reference_check = _optional_reference_comparison(
        reference_v2_summary.resolve() if reference_v2_summary else None,
        case_bundle,
        snapshot.time_value_s,
        mouth_rows,
    )

    source_paths = [Path(__file__).resolve(), METRIC_SOURCE, READER_SOURCE]
    source_paths.extend(
        path
        for path in (
            case_bundle / "experiment.json",
            case_bundle / "input-freeze.json",
            case_bundle / "launch-manifest.json",
        )
        if path.is_file()
    )
    source_paths.extend(snapshot.input_paths)
    if reference_v2_summary is not None:
        source_paths.append(reference_v2_summary.resolve())
    hashed_sources = [
        {"path": _display_path(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in dict.fromkeys(source_paths)
    ]

    rows = []
    for row in mouth_rows:
        helper = row["secondary_metrics_helper_raw"]
        interpreted = row["reported_secondary_metrics"]
        rows.append(
            {
                "case_label": row["case_label"],
                "time_s": row["time_s"],
                "mouth": row["mouth"],
                "native_face_count": row["native_face_count"],
                "projected_area_m2": row["native_area_projected_x_m2"],
                "native_alphaPhi0_water_Q_net_m3_s": row["native_alphaPhi0_water_Q_net_m3_s"],
                "native_alphaPhi0_water_Q_absolute_m3_s": row[
                    "native_alphaPhi0_water_Q_absolute_m3_s"
                ],
                "flux_state": row["flux_state"],
                "helper_raw_outward_direction_mean_angle_deg": helper[
                    "outward_direction_mean_angle_deg_q_weighted"
                ],
                "reported_outward_direction_mean_angle_deg": interpreted[
                    "outward_direction_mean_angle_deg_q_weighted"
                ],
                "reported_water_momentum_net_N_xyz": json.dumps(
                    interpreted["water_momentum_flux_net_reconstructed_N_xyz"],
                    separators=(",", ":"),
                ),
                "reported_water_momentum_outward_N_xyz": json.dumps(
                    interpreted["water_momentum_flux_outward_reconstructed_N_xyz"],
                    separators=(",", ":"),
                ),
                "gas_area_fraction_proxy": helper["area_weighted_raw_alpha_gas_fraction_proxy"],
                "outward_q_m3_s": helper["water_volume_flux_outward_m3_s"],
                "reverse_q_magnitude_m3_s": helper["water_volume_flux_reverse_magnitude_m3_s"],
            }
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = output_dir / "outlet-secondary-by-mouth.csv"
    with csv_path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "schema": "i4f-native-outlet-secondary/v3",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "case_bundle": _display_path(case_bundle),
        "case_label": case_bundle.name,
        "case": _display_path(case),
        "processor_count": NPROCS,
        "selected_time_directory": time_name,
        "native_checkpoint_time_s": snapshot.time_value_s,
        "mouth_cut": {
            **snapshot.selection_metadata,
            "outlet_normal_unit_xyz": NORMAL_X.tolist(),
            "selected_native_face_count": snapshot.face_count,
            "assigned_face_count": sum(len(faces) for faces in snapshot.mouth_faces.values()),
            "orientation_counts": orientation_counts,
            "processor_pair_check": snapshot.processor_pair_summary,
        },
        "method": {
            "primary_native_quantity": "saved alphaPhi0.water on the native internal cut face, oriented from x<=4.8 cell to x>4.8 cell; alpha is never inferred as alphaPhi0/phi",
            "secondary_reconstruction": "saved cell U and alpha.water reconstructed to each native cut face with the checked OpenCFD basicFvGeometryScheme normal-distance linear weight",
            "helper_semantics": "aerial_drop.i4f_outlet_metrics.outlet_secondary_metrics; raw helper result retained per mouth",
            "dry_trace_rule": f"when sum(abs(native alphaPhi0.water)) <= {DRY_ABS_NATIVE_FLUX_THRESHOLD_M3_S:.1e} m3/s, direction and momentum are withheld from interpreted outputs; raw helper results remain available and are numerical-trace diagnostics only",
            "limitations": "reconstructed face U and alpha are secondary and may represent a different solver stage from native alphaPhi0.water; reconstructed water momentum is not the solver's exact mixture momentum-convection flux",
            "reconstruction_correction": "this version applies OpenFOAM's returned normal-distance factor as the owner weight, w*owner+(1-w)*neighbour, and applies signed faceProcAddressing to local-internal fluxes before the global cut orientation. Outputs in i4f-native-outlet-secondary-portable-20261026T053311Z used the reversed owner/neighbour interpolation coefficients; those secondary U/alpha metrics are superseded. Native alphaPhi0.water integrals were unchanged in the checked snapshots.",
        },
        "reader_extraction_provenance": list(READER_EXTRACTION_PROVENANCE),
        "optional_v2_native_Q_check": reference_check,
        "mouth_metrics": mouth_rows,
        "input_and_code_hashes": hashed_sources,
        "output_files": {
            csv_path.name: {"bytes": csv_path.stat().st_size, "sha256": sha256(csv_path)},
        },
    }
    json_path = output_dir / "outlet-secondary.json"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-bundle", type=Path, required=True, help="run bundle containing case/"
    )
    parser.add_argument("--time", required=True, help="exact processors10 time-directory name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new output directory; existing paths are never overwritten",
    )
    parser.add_argument(
        "--reference-v2-summary",
        type=Path,
        help="optional legacy summary used only to compare saved native mouth Q",
    )
    args = parser.parse_args()
    bundle = args.case_bundle if args.case_bundle.is_absolute() else ROOT / args.case_bundle
    out_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    reference = args.reference_v2_summary
    if reference is not None and not reference.is_absolute():
        reference = ROOT / reference
    try:
        json_path, csv_path = run(bundle, args.time, out_dir, reference)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
