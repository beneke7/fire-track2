#!/usr/bin/env python3
"""Summarize the diagnostic-only RP/RF-RP replay against its full-source parent."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = Path(__file__).resolve().parent
ARM = BUNDLE / "n0120-full-source-rp-audit"
RUN = ARM / "run-status.json"
ORIGINAL = ROOT / "results/runs/i4f-full-source-gas-withdrawal-20261026T183953Z/n0120-full-source"
DIAGNOSTIC_PATCH = (
    ROOT
    / "results/runs/i4f-full-predictor-source-20261026T180031Z/full-source-on/provenance/rp-audit-build/provenance/rp-audit-diagnostic.patch"
)
FIELDS = (
    "T",
    "T.air",
    "T.water",
    "U",
    "alpha.air",
    "alpha.water",
    "alphaPhi0.water",
    "p",
    "p_rgh",
    "phi",
    "rho",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def records(path: Path, prefix: str) -> list[dict[str, str]]:
    output = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(prefix + " "):
            output.append(dict(item.split("=", 1) for item in line.split()[1:] if "=" in item))
    return output


def numeric_range(rows: list[dict[str, str]], name: str) -> dict[str, float]:
    values = [float(row[name]) for row in rows]
    if not values or not all(math.isfinite(value) for value in values):
        raise RuntimeError(f"missing/nonfinite field {name}")
    return {"min": min(values), "max": max(values), "max_abs": max(map(abs, values))}


def main() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    if run.get("status") != "normal_end_complete_0p4" or run.get("exit_code") != 0:
        raise RuntimeError("RP replay is not an exit-0 normal-End .4 capture")
    if run.get("completed_time_lines") != 1600 or not run.get("required_native_fields_present"):
        raise RuntimeError("RP replay lacks the expected complete native capture")

    log = ARM / "case/log.compressibleInterFoam"
    rp = records(log, "I4F_FULL_PREDICTOR_RP_AUDIT")
    full = records(log, "I4F_FULL_PREDICTOR_SOURCE_SUMMARY")
    if len(rp) != 3200 or len(full) != 3200:
        raise RuntimeError(f"expected 3200 RP and full-source records; got {len(rp)}, {len(full)}")
    # This exact equality checks the additional observer did not perturb the
    # already enabled full-source diagnostic stream.
    original_log = ORIGINAL / "case/log.compressibleInterFoam"
    original_full = records(original_log, "I4F_FULL_PREDICTOR_SOURCE_SUMMARY")
    if full != original_full:
        raise RuntimeError("full-source diagnostic records differ from the matched original run")

    audit_keys = (
        "RP_max_s-1",
        "RP_volume_L1_m3_s",
        "RP_signed_volume_integral_m3_s",
        "RF_minus_RP_max_s-1",
        "RF_minus_RP_volume_L1_m3_s",
        "RF_minus_RP_signed_volume_integral_m3_s",
    )
    ranges = {key: numeric_range(rp, key) for key in audit_keys}
    base_summary_keys = (
        "full_R_max_s-1",
        "full_R_volume_L1_m3_s",
        "full_R_signed_volume_integral_m3_s",
    )
    full_ranges = {key: numeric_range(full, key) for key in base_summary_keys}

    time_dir = ARM / "case/0.4"
    original_time_dir = ORIGINAL / "case/0.4"
    hashes = {field: sha(time_dir / field) for field in FIELDS}
    original_hashes = {field: sha(original_time_dir / field) for field in FIELDS}
    if hashes != original_hashes:
        differing = [field for field in FIELDS if hashes[field] != original_hashes[field]]
        raise RuntimeError(f"diagnostic-only replay endpoint differs for {differing}")

    payload = {
        "schema": "i4f-full-source-rp-audit-summary/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "exit-0 normal End at 0.4 s; exact native endpoint matches its full-source parent",
        "run_status": str(RUN.relative_to(ROOT)),
        "run_status_sha256": sha(RUN),
        "container_id": run["container_id"],
        "started_at": run["started_at"],
        "completed_steps": run["completed_time_lines"],
        "source_mode_banner": run["startup_mode_banner"],
        "binary_sha256": sha(BUNDLE / "bin/compressibleInterFoamFrozenAlphaSourceV2NoPout"),
        "diagnostic_patch": str(DIAGNOSTIC_PATCH.relative_to(ROOT)),
        "diagnostic_patch_sha256": sha(DIAGNOSTIC_PATCH),
        "log_sha256": sha(log),
        "matched_parent_run": "results/runs/i4f-full-source-gas-withdrawal-20261026T183953Z/n0120-full-source",
        "matched_parent_log_sha256": sha(original_log),
        "record_count": {"RP_audit": len(rp), "full_source_summary": len(full)},
        "endpoint_field_hashes": hashes,
        "endpoint_hashes_match_parent": True,
        "RP_and_RF_minus_RP_ranges": ranges,
        "full_source_R_ranges": full_ranges,
        "interpretation": "RP is the logged discrete predictor-step alpha-equation residual; RF_minus_RP is the logged difference to the full predictor residual. These are local alpha-equation diagnostics, not pressure-field residuals, global continuity residuals, or independent validation. Exact endpoint hash identity and identical full-source summary records demonstrate passivity for this one n=120 replay only.",
        "limitations": [
            "One n=120 run, one solver build and one diagnostic window; passivity is not established for all inputs or grids.",
            "R_P here names the predictor-step alpha-equation residual; it is not a pressure-field residual.",
        ],
    }
    out = BUNDLE / "rp-audit-summary.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": str(out.relative_to(ROOT)),
                "record_count": payload["record_count"],
                "endpoint_hashes_match_parent": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
