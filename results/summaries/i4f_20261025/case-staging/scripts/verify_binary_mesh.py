from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from aerial_drop.i4f_case_staging import sha256_file

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = ROOT / "results/runs/i4f-cold-pressure-advisory-continuation-20261026T2227Z"
SOURCE_CASE = SOURCE_BUNDLE / "case"
STAGED_CASE = BUNDLE / "case"


def main() -> None:
    freeze_path = SOURCE_BUNDLE / "input-freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    stage_manifest_path = STAGED_CASE / "provenance/staging-manifest.json"
    stage_manifest = json.loads(stage_manifest_path.read_text(encoding="utf-8"))
    staged_rows = {row["path"]: row for row in stage_manifest["static_files"]}
    frozen_mesh_rows = {
        row["path"]: row
        for row in freeze["case_files"]
        if row["path"].startswith(
            ("case/constant/polyMesh/", "case/processors10/constant/polyMesh/")
        )
    }

    mismatches: list[str] = []
    for frozen_path, frozen_row in frozen_mesh_rows.items():
        staged_path = frozen_path.removeprefix("case/")
        row = staged_rows.get(staged_path)
        target = STAGED_CASE / staged_path
        if (
            row is None
            or row["sha256"] != frozen_row["sha256"]
            or row["bytes"] != frozen_row["bytes"]
            or not target.is_file()
            or target.stat().st_size != frozen_row["bytes"]
            or sha256_file(target) != frozen_row["sha256"]
        ):
            mismatches.append(staged_path)

    binary_paths = [
        "processors10/constant/polyMesh/points",
        "processors10/constant/polyMesh/faces",
        "processors10/constant/polyMesh/owner",
        "processors10/constant/polyMesh/neighbour",
        "processors10/constant/polyMesh/boundary",
        "processors10/constant/polyMesh/cellProcAddressing",
        "processors10/constant/polyMesh/faceProcAddressing",
        "processors10/constant/polyMesh/pointProcAddressing",
        "processors10/constant/polyMesh/boundaryProcAddressing",
    ]
    binary_probe: list[dict[str, object]] = []
    for relative in binary_paths:
        path = STAGED_CASE / relative
        header = path.read_bytes()[:4096]
        is_binary = bool(re.search(rb"\bformat\s+binary\s*;", header))
        binary_probe.append(
            {
                "path": relative,
                "format_binary_in_header": is_binary,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    native_count = sum(path.startswith("case/constant/polyMesh/") for path in frozen_mesh_rows)
    collated_count = sum(
        path.startswith("case/processors10/constant/polyMesh/") for path in frozen_mesh_rows
    )
    report = {
        "schema": "i4f-staging-real-binary-mesh-verification/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": "systemd-run --user --scope --quiet -p CPUQuota=50% -- nice -n 19 .venv/bin/python scripts/run_local.py --threads 1 -- .venv/bin/python results/runs/i4f-staging-integration-20261026T2251Z/scripts/verify_binary_mesh.py",
        "source_freeze_path": str(freeze_path.relative_to(ROOT)),
        "source_freeze_sha256": sha256_file(freeze_path),
        "staging_manifest_path": str(stage_manifest_path.relative_to(ROOT)),
        "staging_manifest_sha256": sha256_file(stage_manifest_path),
        "frozen_native_mesh_files": native_count,
        "frozen_collated_mesh_and_addressing_files": collated_count,
        "verified_mesh_file_mismatches": mismatches,
        "binary_header_probes": binary_probe,
        "all_probed_files_are_binary": all(row["format_binary_in_header"] for row in binary_probe),
        "mismatch_count": len(mismatches)
        + sum(not row["format_binary_in_header"] for row in binary_probe),
        "solver_launched": False,
    }
    output = BUNDLE / "analysis/mesh-binary-verification.json"
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
