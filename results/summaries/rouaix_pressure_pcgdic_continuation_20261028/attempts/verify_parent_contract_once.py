#!/usr/bin/env python3
"""Verify the saved native .255 s parent once under a bounded Slurm job."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--parent-run", type=Path, required=True)
    parser.add_argument("--parent-job-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root))

    from cases.e1_rouaix_hpc_restart import run_restart

    contract = run_restart.verify_completed_parent(args.parent_run, args.parent_job_id)
    run_restart.validate_parent_contract(contract, expected_time_s=0.255)
    config = run_restart.config_for_variant("pressure-pcgdic-continuation")
    preflight_root = args.output.parent / "preflight-case-14705632"
    preflight_attempt = preflight_root / "attempt"
    preflight_attempt.mkdir(parents=True)
    case, manifest = run_restart.prepare_case(preflight_attempt, config, contract)
    seed_verification = json.loads(
        (preflight_attempt / "seed-verification.json").read_text(encoding="utf-8")
    )
    fv_solution_sha256 = run_restart.sha256_file(case / "system/fvSolution")
    if fv_solution_sha256 != contract["fv_solution_sha256"]:
        raise run_restart.RestartError("dry preparation changed inherited fvSolution")
    checkpoint_time = case / contract["checkpoint_time_dir"] / "uniform/time"
    run_restart.validate_checkpoint_time(
        checkpoint_time.read_text(encoding="ascii"),
        checkpoint_time_s=float(contract["checkpoint_time_s"]),
    )
    if manifest["start_time_s"] != 0.255 or manifest["horizon_s"] != 0.3:
        raise run_restart.RestartError(
            "dry preparation did not select the frozen .255-to-.300 interval"
        )
    payload = {
        "schema_version": 1,
        "verified_utc": datetime.now(UTC).isoformat(),
        "parent_job_id": args.parent_job_id,
        "preparation_only": True,
        "solver_started": False,
        "preflight_case": str(case),
        "preflight_manifest": str(preflight_attempt / "manifest.json"),
        "start_time_s": manifest["start_time_s"],
        "end_time_s": manifest["horizon_s"],
        "fv_solution_sha256": fv_solution_sha256,
        "checkpoint_fields": seed_verification["checkpoint_fields"],
        "processor_mesh": seed_verification["collated_decomposition_mesh"],
        "parent_contract_sha256": hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "parent_contract": contract,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, args.output)
    print(
        json.dumps(
            {
                "status": "verified",
                "parent_job_id": args.parent_job_id,
                "variant": contract["variant"],
                "checkpoint_time_s": contract["checkpoint_time_s"],
                "step_count": contract["step_count"],
                "inventory_history_member": contract["inventory_history_member"],
                "inventory_history_m3": contract["inventory_history_m3"],
                "contract_sha256": payload["parent_contract_sha256"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
