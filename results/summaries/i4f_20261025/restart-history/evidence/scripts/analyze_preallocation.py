#!/usr/bin/env python3
"""Compare the one-step oldTime preallocation restart with saved A/B/C arms."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BUNDLE = Path(__file__).resolve().parents[1]
SCRIPTS = BUNDLE / "scripts"
sys.path.insert(0, str(SCRIPTS))
import analyze_restart_probe as base  # noqa: E402

ARMS = (
    "arm-a-uninterrupted",
    "arm-b-fallback",
    "arm-c-saved-dgdt",
    "arm-d-preallocated-oldtime",
)
FIELD_SIZE = {
    "alpha1": (60, 1),
    "alpha2": (60, 1),
    "rho1": (60, 1),
    "rho2": (60, 1),
    "rho": (60, 1),
    "U": (60, 3),
    "T": (60, 1),
    "K": (60, 1),
    "p_rgh": (60, 1),
    "phi": (59, 1),
}
FLOAT = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_array(section: str, size: int, components: int) -> np.ndarray:
    uniform = re.search(r"\b(\d+)\{([^{}]+)\}", section)
    count = size * components
    if uniform:
        observed_size = int(uniform.group(1))
        values = [float(token) for token in FLOAT.findall(uniform.group(2))]
        if observed_size != size or len(values) != components:
            raise ValueError(f"uniform oldTime field size mismatch: {observed_size}, {values}")
        return np.tile(np.asarray(values, dtype=np.float64), size).reshape(size, components)

    start = section.find("\n(")
    if start < 0:
        raise ValueError(f"could not find OpenFOAM Field list in {section[:100]!r}")
    values = [float(token) for token in FLOAT.findall(section[start + 2 :])]
    if len(values) < count:
        raise ValueError(f"short oldTime Field list: expected {count}, got {len(values)}")
    return np.asarray(values[:count], dtype=np.float64).reshape(size, components)


def parse_oldtime_log(log_path: Path) -> dict[str, dict[str, Any]]:
    lines = log_path.read_text(errors="replace").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("I4F_RESTART_OLDTIME_STATE ")]
    result: dict[str, dict[str, Any]] = {}
    for pos, start in enumerate(starts):
        stop = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:stop])
        header = lines[start]
        phase_match = re.search(r"\bphase=(\S+)", header)
        field_match = re.search(r"\bfield=(\S+)", header)
        if not phase_match or not field_match:
            raise ValueError(f"malformed oldTime marker: {header}")
        phase, field = phase_match.group(1), field_match.group(1)
        if field not in FIELD_SIZE:
            raise ValueError(f"unexpected oldTime field {field!r}")
        current_section, old_section = block.split("current_primitive=", 1)[1].split(
            "old_primitive=", 1
        )
        size, components = FIELD_SIZE[field]
        current = parse_array(current_section, size, components)
        old = parse_array(old_section, size, components)
        values: dict[str, Any] = base.kv_record(header)
        values.update({"current": current, "old": old})
        result[f"{phase}/{field}"] = values
    expected = {f"before-first-alpha/{name}" for name in FIELD_SIZE} | {
        f"after-first-step/{name}" for name in FIELD_SIZE
    }
    if set(result) != expected:
        raise ValueError(f"oldTime state markers missing/extra: {sorted(set(result) ^ expected)}")
    return result


def main() -> None:
    statuses: dict[str, dict[str, Any]] = {}
    arrays: dict[str, dict[str, np.ndarray]] = {}
    logs: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        arm_dir = BUNDLE / "cases" / arm
        status = json.loads((arm_dir / "run-status.json").read_text())
        if status["status"] != "normal_end_complete":
            raise RuntimeError(f"arm {arm} is not a normal complete run")
        endpoint = arm_dir / "case" / status["terminal_native_time_directory"]
        statuses[arm] = status
        arrays[arm] = {
            name: base.parse_internal_field(endpoint / name)
            for name in status["endpoint_fields_present"]
            if (endpoint / name).is_file()
        }
        logs[arm] = base.parse_log(
            arm_dir / "case/log.compressibleInterFoam",
            split_time=0.1,
            endpoint_time=float(status["target_time_s"]),
        )

    field_rows: list[dict[str, Any]] = []
    comparisons: dict[str, dict[str, Any]] = {}
    for i, left_arm in enumerate(ARMS):
        for right_arm in ARMS[i + 1 :]:
            pair: dict[str, Any] = {}
            for field in sorted(set(arrays[left_arm]) & set(arrays[right_arm])):
                left_path = (
                    BUNDLE
                    / "cases"
                    / left_arm
                    / "case"
                    / statuses[left_arm]["terminal_native_time_directory"]
                    / field
                )
                right_path = (
                    BUNDLE
                    / "cases"
                    / right_arm
                    / "case"
                    / statuses[right_arm]["terminal_native_time_directory"]
                    / field
                )
                metric = base.metrics(arrays[left_arm][field], arrays[right_arm][field])
                left_hash, right_hash = sha(left_path), sha(right_path)
                metric.update(
                    {
                        "left_sha256": left_hash,
                        "right_sha256": right_hash,
                        "bitwise_equal": left_hash == right_hash,
                    }
                )
                pair[field] = metric
                field_rows.append(
                    {
                        "left_arm": left_arm,
                        "right_arm": right_arm,
                        "field": field,
                        "left_sha256": left_hash,
                        "right_sha256": right_hash,
                        "bitwise_equal": left_hash == right_hash,
                        "element_count": int(np.prod(metric["shape"])),
                        "max_abs": metric["max_abs"],
                        "rms_abs": metric["rms_abs"],
                        "max_relative": metric["max_relative"],
                    }
                )
            comparisons[f"{left_arm}__vs__{right_arm}"] = pair

    d_oldtime = parse_oldtime_log(
        BUNDLE / "cases/arm-d-preallocated-oldtime/case/log.compressibleInterFoam"
    )
    oldtime_comparison: dict[str, Any] = {}
    for field in FIELD_SIZE:
        before = d_oldtime[f"before-first-alpha/{field}"]
        after = d_oldtime[f"after-first-step/{field}"]
        oldtime_comparison[field] = {
            "before_current_vs_old": base.metrics(before["current"], before["old"]),
            "before_old_vs_after_old": base.metrics(before["old"], after["old"]),
            "before_current_time_index": before.get("current_time_index"),
            "before_old_time_index": before.get("old_time_index"),
            "before_old_time_levels": before.get("old_time_levels"),
            "after_current_time_index": after.get("current_time_index"),
            "after_old_time_index": after.get("old_time_index"),
            "after_old_time_levels": after.get("old_time_levels"),
        }

    split_manifest = json.loads((BUNDLE / "provenance/split-checkpoint.json").read_text())
    split_name = split_manifest["split_native_time_directory"]
    seed_dir = BUNDLE / "cases/arm-d-preallocated-oldtime/case" / split_name
    seed_rows = []
    for item in split_manifest["A_split_files"]:
        path = seed_dir / item["path"]
        seed_rows.append(
            {"path": item["path"], "bytes": path.stat().st_size, "sha256": sha(path)}
        )
    seed_after_run_differences = [
        {"path": observed["path"], "expected_A_sha256": expected["sha256"], "observed_after_run_sha256": observed["sha256"]}
        for expected, observed in zip(split_manifest["A_split_files"], seed_rows, strict=True)
        if expected != observed
    ]
    seed_field_map = {
        "alpha1": "alpha.water",
        "alpha2": "alpha.air",
        "rho": "rho",
        "U": "U",
        "T": "T",
        "p_rgh": "p_rgh",
        "phi": "phi",
    }
    seed_state_comparison = {}
    for state_name, native_name in seed_field_map.items():
        seed_native = base.parse_internal_field(
            BUNDLE / "cases/arm-a-uninterrupted/case" / split_name / native_name
        )
        seed_state_comparison[state_name] = base.metrics(
            seed_native, d_oldtime[f"before-first-alpha/{state_name}"]["current"]
        )
    initial_u = d_oldtime["before-first-alpha/U"]["current"]
    derived_k = 0.5 * np.sum(initial_u * initial_u, axis=1, keepdims=True)
    seed_state_comparison["K_vs_half_U_squared"] = base.metrics(
        derived_k, d_oldtime["before-first-alpha/K"]["current"]
    )

    masses = {}
    for arm in ARMS:
        initial = logs[arm]["initial_phase_mass"]
        final = logs[arm]["endpoint_phase_mass_last_after_correctRho"]
        if arm == "arm-a-uninterrupted":
            initial = logs[arm]["split_phase_mass_last_after_correctRho"]
        masses[arm] = {
            "start_basis": "A split post-EOS state" if arm == "arm-a-uninterrupted" else "run startup inventory",
            "water_start_kg": initial["water_inventory_kg"],
            "water_end_kg": final["water_inventory_kg"],
            "water_increment_kg": final["water_inventory_kg"] - initial["water_inventory_kg"],
            "gas_start_kg": initial["gas_inventory_kg"],
            "gas_end_kg": final["gas_inventory_kg"],
            "gas_increment_kg": final["gas_inventory_kg"] - initial["gas_inventory_kg"],
            "water_cont_L1_nativeV_kg_s": final["water_cont_L1_nativeV_kg_s"],
            "gas_cont_L1_nativeV_kg_s": final["gas_cont_L1_nativeV_kg_s"],
        }

    d_vs_a = comparisons["arm-a-uninterrupted__vs__arm-d-preallocated-oldtime"]
    d_status = statuses["arm-d-preallocated-oldtime"]
    launch_manifest = json.loads(
        (BUNDLE / "cases/arm-d-preallocated-oldtime/launch-manifest.json").read_text()
    )
    source_a = logs["arm-a-uninterrupted"]["endpoint_source_summaries"]
    source_d = logs["arm-d-preallocated-oldtime"]["endpoint_source_summaries"]
    source_differences = []
    for row_index, (left, right) in enumerate(zip(source_a, source_d, strict=True)):
        keys = (set(left) & set(right)) - {"outer_iteration"}
        numeric_differences = {
            key: abs(float(left[key]) - float(right[key]))
            for key in keys
            if isinstance(left[key], float) and isinstance(right[key], float)
        }
        source_differences.append(
            {
                "row_in_time_order": row_index,
                "comparable_keys": sorted(keys),
                "max_abs_numeric_difference": max(numeric_differences.values(), default=0.0),
                "numeric_differences": numeric_differences,
                "all_noncounter_fields_equal": all(left[key] == right[key] for key in keys),
            }
        )

    result = {
        "schema": "i4f-restart-oldtime-preallocation-comparison/v1",
        "created_utc": utc(),
        "method": {
            "comparison_time_s": 0.10025000000000008,
            "field_comparison": "native binary internalField IEEE-754 float64 arrays; endpoint field bytes independently hashed",
            "restart_seed": "exact 15-file original uninterrupted A split, including dgdt and uniform/time; verified against split-checkpoint manifest before GO",
            "diagnostic_patch_changes": "At first restart step only, explicitly calls oldTime twice for alpha1/alpha2/rho1/rho2/rho/U/T/K/p_rgh/phi immediately after ++runTime and before alpha/EOS/momentum/energy/pressure mutation; PDE terms unchanged.",
            "oldtime_log_precision": 17,
            "oldtime_state_capture": "exact primitive arrays and current/old time indices before first alpha and after first complete step",
        },
        "d_runtime": {
            "container_id": d_status["container_id"],
            "started_at": d_status["started_at"],
            "exit_code": d_status["exit_code"],
            "normal_End": d_status["normal_End"],
            "go_released": d_status["go_released"],
            "exact_target_Time_line": d_status["exact_target_Time_line"],
            "startup_mode_banner": d_status["startup_mode_banner"],
            "launch_manifest_sha256": sha(BUNDLE / "cases/arm-d-preallocated-oldtime/launch-manifest.json"),
            "docker_inspect_before_GO_sha256": launch_manifest["docker_inspect_before_GO_sha256"],
            "solver_binary_sha256": launch_manifest["binary_sha256"],
            "patch_sha256": launch_manifest["source_patch_sha256"],
            "case_freeze_sha256": launch_manifest["case_freeze_sha256"],
            "resource_admission_sha256": launch_manifest["resource_admission_sha256"],
            "runner_script_sha256": sha(BUNDLE / "scripts/run_arm.py"),
            "log_sha256": d_status["log_sha256"],
            "endpoint_native_time_directory": d_status["terminal_native_time_directory"],
            "endpoint_fields": d_status["endpoint_fields_present"],
        },
        "seed_checkpoint": {
            "expected_file_count": len(split_manifest["A_split_files"]),
            "observed_file_count": len(seed_rows),
            "seed_contains_per_field_oldtime_files": any(
                item["path"].endswith("_0") for item in split_manifest["A_split_files"]
            ),
            "pre_GO_exact_original_A_split_match": bool(d_status["go_released"] and d_status["normal_End"]),
            "pre_GO_verification_evidence": "The guarded runner's verify_case check ran before Docker create and again after create/before GO; its arm-D path compares the full split directory rows/bytes/SHA against split-checkpoint.json's immutable A_split_files. GO release and normal completion mean both checks returned without error. The pre-GO checkpoint was not copied to another archive.",
            "expected_original_A_split_rows": split_manifest["A_split_files"],
            "post_run_current_split_directory_differences": seed_after_run_differences,
            "post_run_split_note": "This directory is solver output after GO; phase-temperature constructor writes may change T.air/T.water. It is not used as a pre-GO input checksum.",
            "pre_alpha_current_state_vs_original_A_seed_fields": seed_state_comparison,
        },
        "oldtime_state": oldtime_comparison,
        "source_audit": {
            "pinned_image": "opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319",
            "openfoam_version": "OpenFOAM-2512",
            "actual_image_source_hashes": {
                "GeometricField.C": "b1de340737a0d928ce88cbfb12409ec4ee0889d1cc97aae042caa8d0bd71160d",
                "GeometricField.H": "f0b4587e49bef54073233bcb07775c29e1da8392dce1b2a109576024745826fa",
                "Time.C": "bf22382ddc0095dc7d9a8af2fa5decc8bb4bc71d80ad03b86a0bef387b028d7b",
                "EulerDdtScheme.C": "7c13af1cf0d954a802d742e32d97c74fb9a6b3fecb8cff49a474d856bacff2e9",
                "twoPhaseMixture.C": "4f2c8780a8afeaac4ff2b453dee14b13c06c5ffa147b9ac93c653662f5efb54c",
            },
            "source_loci": {
                "GeometricField_readOldTimeIfPresent": "GeometricField.C:132-170: absent <field>_0 returns false and leaves field0Ptr_ unallocated",
                "GeometricField_oldTime": "GeometricField.C:968-1002: first call copies current state; later call stores on parent Time index mismatch and advances parent timeIndex_",
                "GeometricField_nOldTimes": "GeometricField.C:920-923: const pointer-depth accessor; does not allocate",
                "GeometricField_read_constructor": "GeometricField.C:530-555: current field timeIndex_ initialized from Time::timeIndex() and old-time read is optional",
                "Time_increment": "Time.C:1060 onward: operator++ advances Time value/index; old GeometricFields synchronize lazily through oldTime/storeOldTimes",
                "Euler_phi_correction": "EulerDdtScheme.C:552-563: fvcDdtPhiCorr(U,phi) uses phi.oldTime() and U.oldTime()",
                "alpha2_constructor": "twoPhaseMixture.C:33-61: alpha2 is constructed as 1-alpha1, not read as an independent checkpoint field",
                "solver_call_order": "private copied compressibleInterFoam.C and alphaEqnSubCycle.H: ++runTime then alpha solve; mixture rho is assigned after alpha before contErr ddt(rho); UEqn then TEqn then pEqn phase ddt and pressure correctors",
            },
            "euler_state_fields_preallocated_in_D": list(FIELD_SIZE),
            "dgdt_role": "separately restored from the current A checkpoint and needed by the frozen full-source path; earlier C showed preserving dgdt alone did not recover A",
        },
        "endpoint_field_comparisons": comparisons,
        "d_vs_a_endpoint_summary": {
            field: {
                "bitwise_equal": metric["bitwise_equal"],
                "max_abs": metric["max_abs"],
                "rms_abs": metric["rms_abs"],
            }
            for field, metric in d_vs_a.items()
        },
        "phase_inventory_and_continuity": masses,
        "phase_continuity_ratios_to_A": {
            "D_water_L1_over_A": masses["arm-d-preallocated-oldtime"]["water_cont_L1_nativeV_kg_s"]
            / masses["arm-a-uninterrupted"]["water_cont_L1_nativeV_kg_s"],
            "D_gas_L1_over_A": masses["arm-d-preallocated-oldtime"]["gas_cont_L1_nativeV_kg_s"]
            / masses["arm-a-uninterrupted"]["gas_cont_L1_nativeV_kg_s"],
        },
        "full_source_summary_comparison": {
            "A_rows": source_a,
            "D_rows": source_d,
            "matched_row_comparison": source_differences,
            "comparison_note": "Outer counter labels differ after restart; compare rows by order and fields other than outer_iteration.",
        },
        "interpretation_limits": [
            "This one 60-cell, one-step sealed-channel restart test can test this grouped oldTime preallocation hypothesis only; it is not an apparatus validation or production restart policy.",
            "If D matches A, it supports the restart oldTime timing explanation for this test but does not isolate which field in the preallocated set was necessary.",
            "Continuity diagnostics are phase-ledger checks; they do not establish energy closure.",
        ],
        "artifacts": {
            "analysis_script_path": str(Path(__file__).resolve().relative_to(BUNDLE.parents[2])),
            "analysis_script_sha256": sha(Path(__file__)),
            "field_csv_path": "provenance/preallocation-endpoint-field-differences.csv",
            "run_log_path": "cases/arm-d-preallocated-oldtime/case/log.compressibleInterFoam",
        },
    }
    csv_path = BUNDLE / "provenance/preallocation-endpoint-field-differences.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("left_arm", "right_arm", "field", "left_sha256", "right_sha256", "bitwise_equal", "element_count", "max_abs", "rms_abs", "max_relative"),
        )
        writer.writeheader()
        writer.writerows(field_rows)
    result["artifacts"]["field_csv_sha256"] = sha(csv_path)
    output = BUNDLE / "provenance/preallocation-restart-comparison.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "json": str(output.relative_to(BUNDLE)),
        "csv": str(csv_path.relative_to(BUNDLE)),
        "seed_exact_pre_GO": result["seed_checkpoint"]["pre_GO_exact_original_A_split_match"],
        "d_vs_a": result["d_vs_a_endpoint_summary"],
        "d_phase_continuity_ratios_to_A": result["phase_continuity_ratios_to_A"],
        "oldtime": {name: {key: field[key] for key in ("before_current_time_index", "before_old_time_index", "before_old_time_levels")} for name, field in oldtime_comparison.items()},
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
