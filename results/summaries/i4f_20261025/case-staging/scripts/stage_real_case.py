from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aerial_drop.i4f_case_staging import (
    VerifiedFile,
    build_static_template,
    load_static_template,
    sha256_file,
    stage_canonical_checkpoint,
)

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = ROOT / "results/runs/i4f-cold-pressure-advisory-continuation-20261026T2227Z"
SOURCE_CASE = SOURCE_BUNDLE / "case"
CANONICAL_CHECKPOINT_BUNDLE = (
    ROOT / "results/runs/i4f-cold-momentum-predictor-off-continuation-20261026T2048Z"
)
CANONICAL_CHECKPOINT_CASE = CANONICAL_CHECKPOINT_BUNDLE / "case"
TIME_NAME = "0.390705595007"
PREFIX = "processors10"
REPORT = BUNDLE / "integration-report.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    freeze_path = SOURCE_BUNDLE / "input-freeze.json"
    seed_path = SOURCE_BUNDLE / "continuation-seed.json"
    checkpoint_manifest_path = SOURCE_BUNDLE / "provenance/restart-checkpoint-fields.sha256"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    assert freeze["schema"] == "i4f-pressure-advisory-input-freeze/v1"
    assert seed["checkpoint_time_folder"] == TIME_NAME
    assert freeze["checkpoint_time_s"] == seed["checkpoint_time_s"]
    assert freeze["checkpoint_fields_sha256"] == seed["checkpoint_field_aggregate_sha256"]

    frozen_rows = {row["path"]: row for row in freeze["case_files"]}
    manifest_records: dict[str, str] = {}
    for line in checkpoint_manifest_path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        manifest_records[relative] = digest

    control_rel = "case/system/controlDict"
    control_record = frozen_rows[control_rel]
    control_source = SOURCE_CASE / "system/controlDict"
    if sha256_file(control_source) != control_record["sha256"]:
        raise RuntimeError("working controlDict no longer matches its pre-GO frozen hash")
    protected_control = BUNDLE / "provenance/controlDict.pre-GO"
    protected_control.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(control_source, protected_control)
    if sha256_file(protected_control) != control_record["sha256"]:
        raise RuntimeError("protected pre-GO controlDict copy failed its frozen hash")

    static_prefixes = ("case/constant/", "case/system/", f"case/{PREFIX}/constant/")
    static_inputs: dict[str, VerifiedFile] = {}
    expected_static_paths: set[str] = set()
    for row in freeze["case_files"]:
        frozen_path = row["path"]
        if not frozen_path.startswith(static_prefixes):
            continue
        relative = frozen_path.removeprefix("case/")
        expected_static_paths.add(relative)
        if relative == "system/controlDict":
            continue
        static_inputs[relative] = VerifiedFile(SOURCE_CASE / relative, row["sha256"])

    checkpoint_names = tuple(seed["checkpoint_fields"])
    checkpoint_root = CANONICAL_CHECKPOINT_CASE / PREFIX / TIME_NAME
    fields: dict[str, VerifiedFile] = {}
    for name in checkpoint_names:
        frozen_path = f"case/{PREFIX}/{TIME_NAME}/{name}"
        manifest_path = f"{PREFIX}/{TIME_NAME}/{name}"
        record = frozen_rows[frozen_path]
        if manifest_records.get(manifest_path) != record["sha256"]:
            raise RuntimeError(f"checkpoint freeze and field manifest disagree for {name}")
        fields[name] = VerifiedFile(checkpoint_root / name, record["sha256"])

    time_path = f"{PREFIX}/{TIME_NAME}/uniform/time"
    time_frozen_path = f"case/{time_path}"
    time_record = frozen_rows[time_frozen_path]
    if manifest_records.get(time_path) != time_record["sha256"]:
        raise RuntimeError("checkpoint freeze and field manifest disagree for uniform/time")
    uniform_time = VerifiedFile(checkpoint_root / "uniform/time", time_record["sha256"])

    template_path = BUNDLE / "template"
    if template_path.exists():
        failed_attempt = json.loads(
            (BUNDLE / "attempts/attempt-001.json").read_text(encoding="utf-8")
        )
        template = load_static_template(
            template_path, failed_attempt["static_template_manifest_sha256"]
        )
    else:
        template = build_static_template(
            template_path,
            static_inputs,
            control_dict_source=protected_control,
            control_dict_sha256=control_record["sha256"],
        )
    staged = stage_canonical_checkpoint(
        template,
        BUNDLE / "case",
        time_name=TIME_NAME,
        fields=fields,
        uniform_time=uniform_time,
        checkpoint_prefix=PREFIX,
        required_fields=checkpoint_names,
    )

    template_manifest = json.loads((template.path / "static-template.json").read_text())
    stage_manifest_path = staged.path / "provenance/staging-manifest.json"
    stage_manifest = json.loads(stage_manifest_path.read_text())
    template_paths = {row["path"] for row in template_manifest["files"]}
    if template_paths != expected_static_paths:
        raise RuntimeError(
            "template file set differs from frozen static inventory: "
            f"missing={sorted(expected_static_paths - template_paths)}, "
            f"extra={sorted(template_paths - expected_static_paths)}"
        )

    source_hash_mismatches: list[str] = []
    for relative, source in static_inputs.items():
        if not source.path.is_file() or sha256_file(source.path) != source.sha256:
            source_hash_mismatches.append(relative)
    for name, source in fields.items():
        if not source.path.is_file() or sha256_file(source.path) != source.sha256:
            source_hash_mismatches.append(f"checkpoint/{name}")
    if not uniform_time.path.is_file() or sha256_file(uniform_time.path) != uniform_time.sha256:
        source_hash_mismatches.append("checkpoint/uniform/time")
    if sha256_file(control_source) != control_record["sha256"]:
        source_hash_mismatches.append("system/controlDict")
    if source_hash_mismatches:
        raise RuntimeError(f"source changed during staging: {source_hash_mismatches}")

    staged_fields = staged.path / PREFIX / TIME_NAME
    independent_writable_fields: dict[str, bool] = {}
    for name, source in fields.items():
        output = staged_fields / name
        independent_writable_fields[name] = (
            not os.path.samefile(source.path, output)
            and bool(output.stat().st_mode & 0o200)
            and sha256_file(output) == source.sha256
        )
    if not all(independent_writable_fields.values()):
        raise RuntimeError("one or more canonical checkpoint fields are not independent copies")

    numeric_times = sorted(
        child.name
        for child in (staged.path / PREFIX).iterdir()
        if child.is_dir() and child.name.replace(".", "", 1).isdigit()
    )
    if numeric_times != [TIME_NAME]:
        raise RuntimeError(f"staged collated tree has unexpected numeric times: {numeric_times}")
    if not (staged.path / "constant/polyMesh/points").is_file():
        raise RuntimeError("native mesh points are missing")
    if not (staged.path / PREFIX / "constant/polyMesh/cellProcAddressing").is_file():
        raise RuntimeError("collated cellProcAddressing is missing")
    if (staged.path / "dynamicCode").exists():
        raise RuntimeError("undeclared generated dynamicCode was copied")

    expected_checkpoint_paths = {f"{PREFIX}/{TIME_NAME}/{name}" for name in checkpoint_names} | {
        time_path
    }
    actual_checkpoint_paths = {row["path"] for row in stage_manifest["checkpoint_files"]}
    if actual_checkpoint_paths != expected_checkpoint_paths:
        raise RuntimeError(
            "staged checkpoint path set mismatch: "
            f"missing={sorted(expected_checkpoint_paths - actual_checkpoint_paths)}, "
            f"extra={sorted(actual_checkpoint_paths - expected_checkpoint_paths)}"
        )

    frozen_checkpoint_paths = {
        path.removeprefix("case/")
        for path in frozen_rows
        if path.startswith(f"case/{PREFIX}/{TIME_NAME}/")
    }
    staged_file_bytes = sum(
        path.stat().st_size for path in staged.path.rglob("*") if path.is_file()
    )
    template_file_bytes = sum(
        path.stat().st_size for path in template.path.rglob("*") if path.is_file()
    )
    data_bytes = sum(row["bytes"] for row in stage_manifest["static_files"])
    data_bytes += sum(row["bytes"] for row in stage_manifest["checkpoint_files"])
    mismatch_count = 0
    for row in stage_manifest["static_files"] + stage_manifest["checkpoint_files"]:
        path = staged.path / row["path"]
        if path.stat().st_size != row["bytes"] or sha256_file(path) != row["sha256"]:
            mismatch_count += 1
    if mismatch_count:
        raise RuntimeError(f"staged manifest verification found {mismatch_count} mismatches")

    ancillary_paths = sorted(
        path for path in frozen_checkpoint_paths if path not in expected_checkpoint_paths
    )
    report = {
        "schema": "i4f-real-case-staging-integration/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_bundle": str(SOURCE_BUNDLE.relative_to(ROOT)),
        "source_case": str(SOURCE_CASE.relative_to(ROOT)),
        "canonical_checkpoint_source_case": str(CANONICAL_CHECKPOINT_CASE.relative_to(ROOT)),
        "source_input_freeze": {
            "path": str(freeze_path.relative_to(ROOT)),
            "sha256": sha256_file(freeze_path),
            "frozen_utc": freeze["frozen_utc"],
        },
        "driver": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "source_checkpoint": {
            "time_name": TIME_NAME,
            "time_value_s": seed["checkpoint_time_s"],
            "prefix": PREFIX,
            "source_bundle": str(CANONICAL_CHECKPOINT_BUNDLE.relative_to(ROOT)),
            "fields": list(checkpoint_names),
            "field_aggregate_sha256": seed["checkpoint_field_aggregate_sha256"],
            "manifest_path": str(checkpoint_manifest_path.relative_to(ROOT)),
            "manifest_sha256": sha256_file(checkpoint_manifest_path),
            "source_field_count": len(fields),
            "source_field_bytes": sum(source.path.stat().st_size for source in fields.values()),
            "uniform_time_sha256": uniform_time.sha256,
            "omitted_nonfield_checkpoint_files": ancillary_paths,
        },
        "protected_control_dict": {
            "source": str(control_source.relative_to(ROOT)),
            "frozen_sha256": control_record["sha256"],
            "protected_copy": str(protected_control.relative_to(ROOT)),
            "protected_copy_sha256": sha256_file(protected_control),
        },
        "template": {
            "path": str(template.path.relative_to(ROOT)),
            "manifest_sha256": template.manifest_sha256,
            "static_file_count": len(template_manifest["files"]),
            "static_data_bytes": sum(row["bytes"] for row in template_manifest["files"]),
            "mesh_inventory": template_manifest["mesh"],
            "excluded_undeclared_dynamic_code": template_manifest[
                "excluded_undeclared_dynamic_code"
            ],
        },
        "staged_case": {
            "path": str(staged.path.relative_to(ROOT)),
            "manifest": str(stage_manifest_path.relative_to(ROOT)),
            "manifest_sha256": staged.manifest_sha256,
            "static_file_count": len(stage_manifest["static_files"]),
            "checkpoint_file_count": len(stage_manifest["checkpoint_files"]),
            "data_bytes_excluding_manifests": data_bytes,
            "total_bytes_including_provenance_manifest": staged_file_bytes,
            "staged_file_hash_mismatches": mismatch_count,
            "independent_writable_field_copies": independent_writable_fields,
            "collated_numeric_times": numeric_times,
            "native_mesh_file_count": len(stage_manifest["mesh"]["native"]),
            "collated_mesh_file_count": len(stage_manifest["mesh"]["collated"][PREFIX]),
        },
        "template_total_bytes_including_manifest": template_file_bytes,
        "frozen_static_file_count_expected": len(expected_static_paths),
        "frozen_static_file_count_staged": len(template_paths),
        "omitted_nonfield_checkpoint_files_are_outside_stager_fields_time_contract": True,
        "solver_launched": False,
        "mismatch_count": mismatch_count,
        "source_hash_mismatches": source_hash_mismatches,
    }
    REPORT.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
