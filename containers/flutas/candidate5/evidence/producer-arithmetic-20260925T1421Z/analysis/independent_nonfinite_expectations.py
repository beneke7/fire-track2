#!/usr/bin/env python3
"""Independently compose exact CSV bytes for nonfinite M3 rejection probes."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import independent_expectations as base  # noqa: E402

OUT = ROOT / "analysis" / "bundle" / "nonfinite"
HEADER = (
    "state_index,time_s,dt_s,dtic_raw_s_inv,dtic_used_s_inv,"
    "zero_advection_fallback,nu_max_m2_s,h_min_m,dlmini_m_inv,dtiv_s_inv,"
    "dtik_s_inv,dtig_s_inv,capillary_active,dtmax_s,fixed_step_factor,"
    "dt_over_dtmax,guard_pass"
)


def token(value: float) -> str:
    if value == float("inf"):
        return "Inf"
    if value == float("-inf"):
        return "-Inf"
    if value != value:
        return "NaN"
    return base.token(value)


def row_from_expected(expected: dict[str, float | str], dt: float,
                      *, rate_overflow: bool) -> list[str]:
    values = dict(expected)
    if rate_overflow:
        values.update({
            "dtic_raw_s_inv": float("inf"),
            "dtic_used_s_inv": float("inf"),
            "dtmax_s": 0.0,
            "dt_over_dtmax": float("inf"),
            "guard_pass": "false",
        })
    else:
        values.update({
            "dt_over_dtmax": float("inf"),
            "guard_pass": "false",
        })
    return [
        "0", token(0.0), token(dt),
        token(float(values["dtic_raw_s_inv"])),
        token(float(values["dtic_used_s_inv"])),
        str(values["zero_advection_fallback"]),
        token(float(values["nu_max_m2_s"])),
        token(float(values["h_min_m"])),
        token(float(values["dlmini_m_inv"])),
        token(float(values["dtiv_s_inv"])),
        token(float(values["dtik_s_inv"])),
        token(float(values["dtig_s_inv"])),
        str(values["capillary_active"]),
        token(float(values["dtmax_s"])),
        token(float(values["fixed_step_factor"])),
        token(float(values["dt_over_dtmax"])),
        str(values["guard_pass"]),
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    expected = base.restriction_values()
    cases = {
        "rate": (ROOT / "outputs/m3-nonfinite-rate/ledger_timestep-restriction.csv",
                 row_from_expected(expected, float(base.INPUT["fixed_step_s"]), rate_overflow=True)),
        "dt": (ROOT / "outputs/m3-nonfinite-dt/ledger_timestep-restriction.csv",
               row_from_expected(expected, float("inf"), rate_overflow=False)),
    }
    report = {}
    for name, (actual_path, row) in cases.items():
        expected_bytes = (HEADER + "\n" + ",".join(row) + "\n").encode("utf-8")
        expected_path = OUT / f"expected-nonfinite-{name}.csv"
        expected_path.write_bytes(expected_bytes)
        actual_bytes = actual_path.read_bytes()
        report[name] = {
            "expected_sha256": hashlib.sha256(expected_bytes).hexdigest(),
            "actual_sha256": hashlib.sha256(actual_bytes).hexdigest(),
            "exact_bytes_match": expected_bytes == actual_bytes,
            "expected_row": row,
            "actual_path": str(actual_path.relative_to(ROOT)),
        }
        if expected_bytes != actual_bytes:
            raise AssertionError(f"{name} nonfinite row differs from independent bytes")
    report["method"] = (
        "Finite restriction quantities derive from independent binary64 initgrid and "
        "velocity arithmetic in independent_expectations.py; IEEE overflow and dt=+Inf "
        "are independently inserted into the corresponding formula outputs; the exact "
        "NVHPC ES24.16E3 nonfinite spelling is represented as Inf."
    )
    (OUT / "independent-nonfinite-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
