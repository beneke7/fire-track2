#!/usr/bin/env python3
"""Produce count comparisons and computed-field videos after queued CPU trials."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(path: Path, record: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_run(
    run: Path, output: Path, *, wait: bool, render: bool, ledger_only: bool = False
) -> dict:
    """Read a terminal run; preserve failures and refuse existing output bundles."""
    if output.exists():
        raise FileExistsError(f"refusing to overwrite previous postprocessing: {output}")
    output.mkdir(parents=True)
    record = {
        "run_dir": str(run),
        "classification": "Exploratory paper comparison and computed-field display; no gate decision",
        "started_utc": datetime.now(UTC).isoformat(),
        "status": "waiting",
        "source_run_modified": False,
        "ledger_only": ledger_only,
        "postprocessor_sha256": sha256(Path(__file__)),
        "steps": [],
    }
    record_path = output / "postprocess.json"
    save(record_path, record)
    manifest_path = run / "manifest.json"
    while True:
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        if manifest.get("finished_utc"):
            break
        if not wait:
            record["status"] = "source_run_not_terminal"
            save(record_path, record)
            return record
        time.sleep(60)

    record["source_manifest_sha256"] = sha256(manifest_path)
    record["source_exit_code"] = manifest.get("exit_code")
    report = run / "analytics/report.json"
    if manifest.get("exit_code") != 0 or not report.exists():
        record["status"] = "failed_or_missing_native_analysis"
        record["note"] = "Source evidence is preserved; no automatic validation or restart."
        save(record_path, record)
        return record

    record["source_analysis_sha256"] = sha256(report)
    if json.loads(report.read_text()).get("aircraft") != "Dash-8":
        record["status"] = "wrong_aircraft_analysis"
        save(record_path, record)
        return record
    python = str(ROOT / ".venv/bin/python")
    commands = (
        []
        if ledger_only
        else [
            [
                python,
                str(ROOT / "scripts/compare_dash8_structure_counts.py"),
                "--report",
                str(report),
                "--output-dir",
                str(output / "counts"),
            ]
        ]
    )
    commands.append(
        [
            python,
            str(ROOT / "scripts/audit_iso_vof_ledger.py"),
            "--run-dir",
            str(run),
            "--output-dir",
            str(output / "ledger"),
        ]
    )
    if render and not ledger_only:
        inputs = json.loads((run / "case/case-inputs.json").read_text())
        bounds = [str(v) for axis in "xyz" for v in inputs["domain_bounds_m"][axis]]
        for alpha, label, smoothing in (
            (0.5, "water-alpha50", 20),
            (0.001, "cloud-alpha001", 0),
            (0.9, "core-alpha90", 0),
        ):
            commands.append(
                [
                    python,
                    str(ROOT / "scripts/run_local.py"),
                    "--threads",
                    "1",
                    "--gpu",
                    "--",
                    python,
                    str(ROOT / "scripts/render_vof_animation.py"),
                    "--run-dir",
                    str(run),
                    "--output-dir",
                    str(output / label),
                    "--label",
                    label,
                    "--slowdown",
                    "10",
                    "--orientation-label",
                    "Single belly strip | Exploratory computed fields",
                    "--width",
                    "1920",
                    "--height",
                    "1080",
                    "--isosurface-alpha",
                    str(alpha),
                    "--surface-smoothing-iterations",
                    str(smoothing),
                    "--camera-bounds",
                    *bounds,
                ]
            )

    record["status"] = "processing"
    save(record_path, record)
    for index, command in enumerate(commands):
        with (output / f"step-{index}.log").open("w") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        record["steps"].append({"command": command, "exit_code": result.returncode})
        if result.returncode:
            record["status"] = "postprocess_failed"
            save(record_path, record)
        save(record_path, record)
    record.update(
        status=(
            "postprocess_failed"
            if any(step["exit_code"] for step in record["steps"])
            else "artifacts_ready"
        ),
        finished_utc=datetime.now(UTC).isoformat(),
    )
    save(record_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument(
        "--ledger-only",
        action="store_true",
        help="Add independent step-average ledgers to runs whose other outputs are already scheduled.",
    )
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_dir}")
    args.output_dir.mkdir(parents=True)
    records = []
    for run in args.run_dir:
        run = run.resolve()
        records.append(
            process_run(
                run,
                args.output_dir / run.name,
                wait=args.wait,
                render=not args.skip_render,
                ledger_only=args.ledger_only,
            )
        )
        save(args.output_dir / "summary.json", {"runs": records})
    return int(any(row["status"] != "artifacts_ready" for row in records))


if __name__ == "__main__":
    raise SystemExit(main())
