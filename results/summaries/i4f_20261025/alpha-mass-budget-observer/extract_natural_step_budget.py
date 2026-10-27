#!/usr/bin/env python3
"""Extract selected v3 natural-step mass-budget rows from its Pout log."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

EOS_TAG = "I4F_ALPHA_MASS_BUDGET_EOS_V3 "
ALPHA_TAG = "I4F_ALPHA_MASS_BUDGET_ALPHA_V3 "
KEY_VALUE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)=([^ ]+)")


def parse_records(path: Path, tag: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        position = line.find(tag)
        if position < 0:
            continue
        row: dict[str, Any] = {}
        for key, value in KEY_VALUE.findall(line[position + len(tag) :]):
            try:
                row[key] = float(value)
            except ValueError:
                row[key] = value
        records.append(row)
    return records


def selected_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(records) != 32:
        raise ValueError(f"Expected 32 EOS pass records, found {len(records)}")
    max_outer = max(int(row["source_outer_iteration"]) for row in records)
    max_pass = max(int(row["pressure_pass"]) for row in records)
    selected: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: int(item["pressure_pass"])):
        pressure_pass = int(record["pressure_pass"])
        outer = int(record["source_outer_iteration"])
        groups = []
        if outer == 1:
            groups.append("first_outer")
        if outer == max_outer:
            groups.append("last_outer")
        if pressure_pass >= max_pass - 3:
            groups.append("last_four_pressure_passes")
        if not groups:
            continue
        components = (
            "rho_Ralpha_signed_kg_s",
            "rho_source_signed_kg_s",
            "alphaOld_drho_signed_kg_s",
            "face_density_noncommutation_signed_kg_s",
        )
        signed_sum = sum(float(record[name]) for name in components)
        rmass = float(record["Rmass_signed_kg_s"])
        selected.append(
            {
                "selection_groups": ";".join(groups),
                "time_s": record["time_s"],
                "source_outer_iteration": outer,
                "pressure_pass": pressure_pass,
                "source_call_index": int(record["source_call_index"]),
                "Rmass_signed_kg_s": record["Rmass_signed_kg_s"],
                "Rmass_L1_kg_s": record["Rmass_L1_kg_s"],
                "rho_Ralpha_signed_kg_s": record["rho_Ralpha_signed_kg_s"],
                "rho_Ralpha_L1_kg_s": record["rho_Ralpha_L1_kg_s"],
                "rho_actual_source_signed_kg_s": record["rho_source_signed_kg_s"],
                "rho_actual_source_L1_kg_s": record["rho_source_L1_kg_s"],
                "alpha_old_drho_signed_kg_s": record["alphaOld_drho_signed_kg_s"],
                "alpha_old_drho_L1_kg_s": record["alphaOld_drho_L1_kg_s"],
                "face_density_noncommutation_signed_kg_s": record[
                    "face_density_noncommutation_signed_kg_s"
                ],
                "face_density_noncommutation_L1_kg_s": record[
                    "face_density_noncommutation_L1_kg_s"
                ],
                "cutoff_at_assembly_signed_kg_s": record[
                    "source_cutoff_at_assembly_delta_signed_kg_s"
                ],
                "cutoff_at_assembly_L1_kg_s": record["source_cutoff_at_assembly_delta_L1_kg_s"],
                "source_state_change_signed_kg_s": record["source_state_delta_signed_kg_s"],
                "source_state_change_L1_kg_s": record["source_state_delta_L1_kg_s"],
                "signed_component_sum_kg_s": signed_sum,
                "Rmass_minus_signed_component_sum_kg_s": rmass - signed_sum,
                "cutoff_signed_magnitude_over_abs_Rmass": abs(
                    float(record["source_cutoff_at_assembly_delta_signed_kg_s"]) / rmass
                )
                if rmass
                else None,
                "source_split_identity_error_max_kg_m3_s": record[
                    "source_split_identity_error_max_kg_m3_s"
                ],
                "mass_identity_error_signed_kg_s": record["identity_error_signed_kg_s"],
                "mass_identity_error_L1_kg_s": record["identity_error_L1_kg_s"],
                "mass_identity_error_max_kg_m3_s": record["identity_error_max_kg_m3_s"],
                "denominator_floor_active_cells": int(record["source_denominator_floor_cells"]),
            }
        )
    if [int(row["pressure_pass"]) for row in selected] != [1, 2, 29, 30, 31, 32]:
        raise ValueError(
            f"Unexpected selected passes: {[row['pressure_pass'] for row in selected]}"
        )
    for row in selected:
        if abs(float(row["Rmass_minus_signed_component_sum_kg_s"])) > 2e-11:
            raise ValueError(f"Signed mass-budget terms do not close: {row}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True, help="v3 native solver Pout log")
    parser.add_argument(
        "--output",
        type=Path,
        help="optional CSV path; the file must not already exist (default: stdout)",
    )
    args = parser.parse_args()
    if not args.log.is_file():
        parser.error(f"log does not exist: {args.log}")
    if args.output and args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    eos = parse_records(args.log, EOS_TAG)
    alpha = parse_records(args.log, ALPHA_TAG)
    if len(alpha) != 16:
        parser.error(f"expected 16 alpha source records, found {len(alpha)}")
    rows = selected_rows(eos)
    fields = list(rows[0])
    stream = args.output.open("x", newline="") if args.output else sys.stdout
    try:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.output:
            stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
