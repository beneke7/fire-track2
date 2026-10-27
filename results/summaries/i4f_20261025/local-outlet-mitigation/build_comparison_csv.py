#!/usr/bin/env python3
"""Export a compact, verified iteration history for the B/D/E outlet study.

The B control retains all 197 logged iterations. D and E retain every tenth
row plus the first and final rows from their source histories. SIMPLE iteration
labels are solver iterations, not physical seconds.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RUNS = {
    "B_native_Cf_control": {
        "bundle": "results/runs/i4f-wet-branch-v2512-cf-control-20261027T0917Z",
        "analysis": "analysis.json",
        "stride": 1,
    },
    "D_outlet_extension": {
        "bundle": "results/runs/i4f-wet-branch-outlet-extension-20261027T085020Z",
        "analysis": "analysis/steady-endpoint-analysis.json",
        "stride": 10,
    },
    "E_D_continuation": {
        "bundle": "results/runs/i4f-wet-branch-outlet-extension-continue-9000-20261027T0920Z",
        "analysis": "analysis/steady-endpoint-analysis.json",
        "stride": 10,
    },
}
OUTPUT = OUT / "comparison.csv"
FIELDS = [
    "series",
    "steady_iteration",
    "history_selection",
    "p_abs_at_logged_min_p_cell_pa",
    "max_speed_m_s",
    "p_final_residual_max",
    "wet_inlet_Q_m3_s",
    "wet_outlet_Q_m3_s",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    output_rows: list[dict[str, str]] = []
    provenance = {}
    for series, spec in RUNS.items():
        bundle = ROOT / spec["bundle"]
        analysis = json.loads((bundle / spec["analysis"]).read_text())
        history_ref = analysis["iteration_history"]
        history_path = bundle / history_ref["csv"]
        history_hash = sha256(history_path)
        if history_hash != history_ref["csv_sha256"]:
            raise RuntimeError(f"source history hash mismatch: {history_path}")
        with history_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != history_ref["rows"]:
            raise RuntimeError(f"source row count mismatch: {history_path}")
        if not rows:
            raise RuntimeError(f"empty source history: {history_path}")
        stride = spec["stride"]
        selected = []
        for index, row in enumerate(rows):
            iteration = int(row["steady_iteration"])
            if stride == 1 or index == 0 or index == len(rows) - 1 or iteration % stride == 0:
                selected.append(
                    (
                        row,
                        "all_rows"
                        if stride == 1
                        else (
                            "first_or_last"
                            if index in (0, len(rows) - 1)
                            else f"every_{stride}th_iteration"
                        ),
                    )
                )
        for row, selection in selected:
            output_rows.append(
                {
                    "series": series,
                    "steady_iteration": row["steady_iteration"],
                    "history_selection": selection,
                    "p_abs_at_logged_min_p_cell_pa": row["p_abs_min_at_logged_pmin_pa"],
                    "max_speed_m_s": row["U_mag_max_value"],
                    "p_final_residual_max": row["p_final_residual_max"],
                    "wet_inlet_Q_m3_s": row["wetInlet_Q_m3_s"],
                    "wet_outlet_Q_m3_s": row["wetOutlet_Q_m3_s"],
                }
            )
        provenance[series] = {
            "source_history": str(history_path.relative_to(ROOT)),
            "source_history_sha256": history_hash,
            "source_rows": len(rows),
            "exported_rows": len(selected),
            "iteration_first": int(rows[0]["steady_iteration"]),
            "iteration_last": int(rows[-1]["steady_iteration"]),
            "stride": stride,
        }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    metadata = {
        "schema": "i4f-local-outlet-mitigation-csv-build/v1",
        "time_interpretation": "steady SIMPLE iteration labels, not physical seconds",
        "pressure_column_qualification": "per-iteration absolute pressure evaluated at the logged min(p) cell; it is not the global minimum absolute pressure",
        "decimation": "B control retains all source rows (197). D and E retain every tenth iteration, plus first and last rows. Full source histories remain in their ignored run bundles.",
        "source_histories": provenance,
        "output_rows": len(output_rows),
    }
    (OUT / "comparison-csv-provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
