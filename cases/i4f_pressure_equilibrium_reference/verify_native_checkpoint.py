#!/usr/bin/env python3
"""Report exact native p/U/T/alpha bounds at a captured checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_time(path: Path) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^\s*value\s+([-+0-9.eE]+)\s*;", text)
    if match is None:
        raise ValueError(f"no uniform time value in {path}")
    value = float(match.group(1))
    if not math.isfinite(value):
        raise ValueError("nonfinite checkpoint time")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--time-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = args.case.resolve(strict=True)
    time_dir = args.time_dir.resolve(strict=True)
    if time_dir.parent != case:
        raise ValueError(
            "selected checkpoint must be a direct child of the supplied case directory"
        )
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from scripts.analyze_dash8_interface_growth import read_foam_vector_internal
    from scripts.analyze_native_turbulence import read_foam_scalar_internal

    time_value = read_time(time_dir / "uniform/time")
    time_name = time_dir.name
    count = 6400
    location = time_name
    p = read_foam_scalar_internal(
        time_dir / "p",
        expected_count=count,
        expected_object="p",
        expected_location=location,
        expected_dimensions="1 -1 -2 0 0 0 0",
    )
    p_rgh = read_foam_scalar_internal(
        time_dir / "p_rgh",
        expected_count=count,
        expected_object="p_rgh",
        expected_location=location,
        expected_dimensions="1 -1 -2 0 0 0 0",
    )
    temperature = read_foam_scalar_internal(
        time_dir / "T",
        expected_count=count,
        expected_object="T",
        expected_location=location,
        expected_dimensions="0 0 0 1 0 0 0",
    )
    alpha = read_foam_scalar_internal(
        time_dir / "alpha.water",
        expected_count=count,
        expected_object="alpha.water",
        expected_location=location,
        expected_dimensions="0 0 0 0 0 0 0",
    )
    velocity = read_foam_vector_internal(
        time_dir / "U",
        expected_count=count,
        expected_object="U",
        expected_location=location,
        expected_dimensions="0 1 -1 0 0 0 0",
    )
    arrays = {"p": p, "p_rgh": p_rgh, "T": temperature, "alpha.water": alpha, "U": velocity}
    finite = {name: bool(np.isfinite(values).all()) for name, values in arrays.items()}
    alpha_min = float(np.min(alpha))
    alpha_max = float(np.max(alpha))
    cell_volume_m3 = 1e-6
    water_volume_m3 = float(np.sum(alpha, dtype=np.float64) * cell_volume_m3)
    p_min = float(np.min(p))
    p_max = float(np.max(p))
    p_rgh_gap_max = float(np.max(np.abs(p - p_rgh)))
    velocity_reference = np.asarray([10.0, 0.0, 0.0])
    field_errors = {
        "p_max_abs_error_Pa": float(np.max(np.abs(p - 100000.0))),
        "p_rgh_max_abs_error_Pa": float(np.max(np.abs(p_rgh - 100000.0))),
        "p_minus_p_rgh_max_abs_Pa": p_rgh_gap_max,
        "T_max_abs_error_K": float(np.max(np.abs(temperature - 293.15))),
        "U_max_abs_vector_error_m_s": float(
            np.max(np.linalg.norm(velocity - velocity_reference, axis=1))
        ),
    }
    status = (
        "native_fields_valid"
        if (
            all(finite.values())
            and p_min > 0.0
            and alpha_min >= -1e-12
            and alpha_max <= 1.0 + 1e-12
        )
        else "native_field_bound_failure"
    )
    payload: dict[str, Any] = {
        "schema": "i4f-pressure-equilibrium-native-terminal-check/v1",
        "status": status,
        "time_directory": time_name,
        "uniform_time_s": time_value,
        "cell_count": count,
        "field_sha256": {
            name: sha(time_dir / name) for name in ("alpha.water", "p", "p_rgh", "T", "U")
        },
        "finite_fields": finite,
        "pressure_bounds_Pa": {"min": p_min, "max": p_max, "positive": p_min > 0.0},
        "alpha_bounds": {
            "min": alpha_min,
            "max": alpha_max,
            "valid_with_1e-12_roundoff_allowance": alpha_min >= -1e-12 and alpha_max <= 1.0 + 1e-12,
        },
        "water_inventory": {
            "cell_volume_m3": cell_volume_m3,
            "volume_m3": water_volume_m3,
            "initial_volume_m3": 0.0032,
            "difference_m3": water_volume_m3 - 0.0032,
        },
        "field_errors_vs_exact_uniform_state": field_errors,
        "reference": {"p_Pa": 100000.0, "T_K": 293.15, "U_m_s": [10.0, 0.0, 0.0]},
        "qualification": "Native binary field bounds and exact-state errors for this periodic reference case only; not an apparatus or formal solver gate.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return 0 if status == "native_fields_valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
