from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from aerial_drop.i4f_case_staging import (
    COLLATED_ADDRESSING_FILES,
    CORE_RESTART_FIELDS,
    NATIVE_MESH_FILES,
    VerifiedFile,
    build_static_template,
    load_static_template,
    sha256_file,
    stage_canonical_checkpoint,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RESTART = ROOT / "results/summaries/i4f_20261025/restart-history"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _verified(path: Path) -> VerifiedFile:
    return VerifiedFile(path, sha256_file(path))


def _synthetic_inputs(
    root: Path,
    *,
    omit: str | None = None,
    control: bytes = b"application compressibleInterFoam;\nstopAt endTime;\nendTime 0.65;\n",
) -> tuple[dict[str, VerifiedFile], Path, str, dict[str, VerifiedFile], VerifiedFile]:
    sources = root / "sources"
    native = {
        f"constant/polyMesh/{name}": _write(sources / "native" / name, f"native-{name}".encode())
        for name in NATIVE_MESH_FILES
    }
    static_paths = {
        **native,
        "constant/g": _write(sources / "gravity", b"uniform (0 0 -9.81);\n"),
        "system/fvSchemes": _write(
            sources / "schemes", b"laplacianSchemes { default Gauss linear corrected; }\n"
        ),
    }
    processor_paths = {}
    for name in (*NATIVE_MESH_FILES, *COLLATED_ADDRESSING_FILES):
        processor_paths[f"processors10/constant/polyMesh/{name}"] = _write(
            sources / "processor-mesh" / name, f"processor-{name}".encode()
        )
    static_paths.update(processor_paths)
    dynamic = _write(sources / "dynamicCode" / "generated.C", b"generated cache\n")
    static_paths["dynamicCode/generated.C"] = dynamic
    if omit is not None:
        static_paths.pop(omit)
    protected_control = _write(sources / "protected-controlDict", control)
    control_hash = sha256_file(protected_control)

    checkpoint = sources / "canonical" / "0.400000000000"
    fields: dict[str, VerifiedFile] = {}
    for name in CORE_RESTART_FIELDS:
        content = f"canonical-{name}\n".encode()
        path = _write(checkpoint / name, content)
        fields[name] = _verified(path)
    (checkpoint / "T.air").write_bytes(b"canonical-T.air\n")
    (checkpoint / "T.water").write_bytes(b"canonical-T.water\n")
    for name in ("alphat", "k", "nut", "omega"):
        fields[name] = _verified(_write(checkpoint / name, f"canonical-{name}\n".encode()))
    time_bytes = b"FoamFile\n{\n    class dictionary;\n    object time;\n}\nvalue 0.400000000000;\n"
    time_file = _write(checkpoint / "uniform" / "time", time_bytes)
    return (
        {name: _verified(path) for name, path in static_paths.items()},
        protected_control,
        control_hash,
        fields,
        _verified(time_file),
    )


def _build_synthetic_template(tmp_path: Path, *, omit: str | None = None):
    static, control, control_hash, fields, time_file = _synthetic_inputs(tmp_path, omit=omit)
    template = build_static_template(
        tmp_path / "template",
        static,
        control_dict_source=control,
        control_dict_sha256=control_hash,
    )
    return template, static, control, control_hash, fields, time_file


def test_template_stages_only_canonical_time_and_preserves_static_case_inputs(
    tmp_path: Path,
) -> None:
    template, static, control, control_hash, fields, time_file = _build_synthetic_template(tmp_path)
    staged = stage_canonical_checkpoint(
        template,
        tmp_path / "case",
        time_name="0.400000000000",
        fields=fields,
        uniform_time=time_file,
        checkpoint_prefix="processors10",
    )
    case = staged.path

    assert (case / "constant/g").read_bytes() == static["constant/g"].path.read_bytes()
    assert (case / "constant/polyMesh/points").is_file()
    assert (case / "system/fvSchemes").is_file()
    assert (case / "system/controlDict").read_bytes() == control.read_bytes()
    assert sha256_file(case / "system/controlDict") == control_hash
    assert (case / "processors10/constant/polyMesh/cellProcAddressing").is_file()
    assert (case / "processors10/constant/polyMesh/faceProcAddressing").is_file()
    assert (case / "processors10/0.400000000000/uniform/time").read_bytes() == (
        time_file.path.read_bytes()
    )
    assert not (case / "processors10/0.200000000000").exists()
    assert not (case / "0.200000000000").exists()
    assert not (case / "dynamicCode").exists()
    assert (case / "provenance/staging-manifest.json").is_file()

    source = fields["T.air"].path
    staged_field = case / "processors10/0.400000000000/T.air"
    assert staged_field.read_bytes() == b"canonical-T.air\n"
    assert not os.path.samefile(source, staged_field)
    assert staged_field.stat().st_mode & 0o200


def test_runtime_mutated_phase_caches_and_control_dict_cannot_replace_canonical_inputs(
    tmp_path: Path,
) -> None:
    template, _, protected_control, control_hash, fields, time_file = _build_synthetic_template(
        tmp_path
    )
    runtime = tmp_path / "working-case"
    _write(runtime / "system/controlDict", b"stopAt writeNow;\n")
    _write(runtime / "processors10/0.400000000000/T.air", b"runtime-rewritten-air\n")
    _write(runtime / "processors10/0.400000000000/T.water", b"runtime-rewritten-water\n")

    staged = stage_canonical_checkpoint(
        template,
        tmp_path / "case",
        time_name="0.400000000000",
        fields=fields,
        uniform_time=time_file,
    )
    assert (staged.path / "system/controlDict").read_bytes() == protected_control.read_bytes()
    assert sha256_file(staged.path / "system/controlDict") == control_hash
    assert (staged.path / "processors10/0.400000000000/T.air").read_bytes() == (
        b"canonical-T.air\n"
    )
    assert (staged.path / "processors10/0.400000000000/T.water").read_bytes() == (
        b"canonical-T.water\n"
    )

    corrupted_fields = dict(fields)
    corrupted_fields["T.air"] = VerifiedFile(
        runtime / "processors10/0.400000000000/T.air", fields["T.air"].sha256
    )
    with pytest.raises(ValueError, match="T.air SHA256 mismatch"):
        stage_canonical_checkpoint(
            template,
            tmp_path / "bad-case",
            time_name="0.400000000000",
            fields=corrupted_fields,
            uniform_time=time_file,
        )
    assert not (tmp_path / "bad-case").exists()


def test_runtime_mutated_control_dict_is_rejected_when_used_as_protected_source(
    tmp_path: Path,
) -> None:
    static, protected, protected_hash, _, _ = _synthetic_inputs(tmp_path)
    mutated = _write(tmp_path / "mutated-controlDict", b"stopAt writeNow;\n")
    with pytest.raises(ValueError, match="protected controlDict SHA256 mismatch"):
        build_static_template(
            tmp_path / "bad-template",
            static,
            control_dict_source=mutated,
            control_dict_sha256=protected_hash,
        )
    assert not (tmp_path / "bad-template").exists()
    assert sha256_file(protected) == protected_hash


@pytest.mark.parametrize(
    ("missing_path", "error"),
    [
        ("constant/polyMesh/points", "native polyMesh"),
        (
            "processors10/constant/polyMesh/cellProcAddressing",
            "processors10 mesh/addressing",
        ),
    ],
)
def test_missing_native_mesh_or_collated_addressing_fails_before_template_creation(
    tmp_path: Path, missing_path: str, error: str
) -> None:
    static, control, control_hash, _, _ = _synthetic_inputs(tmp_path, omit=missing_path)
    with pytest.raises(ValueError, match=error):
        build_static_template(
            tmp_path / "incomplete-template",
            static,
            control_dict_source=control,
            control_dict_sha256=control_hash,
        )
    assert not (tmp_path / "incomplete-template").exists()


def test_missing_checkpoint_field_or_time_does_not_create_or_change_output(
    tmp_path: Path,
) -> None:
    template, _, _, _, fields, time_file = _build_synthetic_template(tmp_path)
    incomplete = dict(fields)
    incomplete.pop("p_rgh")
    with pytest.raises(ValueError, match="missing required fields"):
        stage_canonical_checkpoint(
            template,
            tmp_path / "missing-field-case",
            time_name="0.400000000000",
            fields=incomplete,
            uniform_time=time_file,
        )
    assert not (tmp_path / "missing-field-case").exists()

    missing_time = VerifiedFile(tmp_path / "missing-time", time_file.sha256)
    with pytest.raises(FileNotFoundError, match="uniform/time"):
        stage_canonical_checkpoint(
            template,
            tmp_path / "missing-time-case",
            time_name="0.400000000000",
            fields=fields,
            uniform_time=missing_time,
        )
    assert not (tmp_path / "missing-time-case").exists()

    existing = tmp_path / "existing-case"
    existing.mkdir()
    sentinel = _write(existing / "preserve.txt", b"leave existing state intact")
    with pytest.raises(FileExistsError, match="refusing to overwrite staged case"):
        stage_canonical_checkpoint(
            template,
            existing,
            time_name="0.400000000000",
            fields=incomplete,
            uniform_time=missing_time,
        )
    assert sentinel.read_bytes() == b"leave existing state intact"


def test_generated_dynamic_code_is_excluded_unless_explicitly_frozen(tmp_path: Path) -> None:
    static, control, control_hash, _, _ = _synthetic_inputs(tmp_path)
    template = build_static_template(
        tmp_path / "template",
        static,
        control_dict_source=control,
        control_dict_sha256=control_hash,
        freeze_dynamic_code=False,
    )
    manifest = json.loads((template.path / "static-template.json").read_text())
    assert manifest["excluded_undeclared_dynamic_code"] == ["dynamicCode/generated.C"]
    assert not (template.path / "dynamicCode").exists()


def test_template_and_staged_case_refuse_overwrite_and_keep_sources_unchanged(
    tmp_path: Path,
) -> None:
    template, static, _, control_hash, fields, time_file = _build_synthetic_template(tmp_path)
    source_hashes = {name: sha256_file(source.path) for name, source in static.items()}
    staged = stage_canonical_checkpoint(
        template,
        tmp_path / "case",
        time_name="0.400000000000",
        fields=fields,
        uniform_time=time_file,
    )
    manifest_path = staged.path / "provenance/staging-manifest.json"
    manifest_before = manifest_path.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite staged case"):
        stage_canonical_checkpoint(
            template,
            staged.path,
            time_name="0.400000000000",
            fields=fields,
            uniform_time=time_file,
        )
    assert manifest_path.read_bytes() == manifest_before
    assert {name: sha256_file(source.path) for name, source in static.items()} == source_hashes
    assert sha256_file(fields["T.water"].path) == fields["T.water"].sha256
    with pytest.raises(FileExistsError, match="refusing to overwrite static template"):
        build_static_template(
            template.path,
            static,
            control_dict_source=tmp_path / "sources/protected-controlDict",
            control_dict_sha256=control_hash,
        )


def test_template_manifest_and_files_are_rechecked_before_staging(tmp_path: Path) -> None:
    template, _, _, _, fields, time_file = _build_synthetic_template(tmp_path)
    with pytest.raises(ValueError, match="static template manifest SHA256 mismatch"):
        load_static_template(template.path, "0" * 64)

    (template.path / "constant/g").write_bytes(b"mutated-template-gravity")
    with pytest.raises(RuntimeError, match="staged input mismatch for constant/g"):
        stage_canonical_checkpoint(
            template,
            tmp_path / "case",
            time_name="0.400000000000",
            fields=fields,
            uniform_time=time_file,
        )
    assert not (tmp_path / "case").exists()


def test_public_restart_packet_stages_canonical_restart_without_neighboring_times(
    tmp_path: Path,
) -> None:
    case_bundle = PUBLIC_RESTART / "cases/D"
    case = case_bundle / "case"
    freeze = json.loads((case_bundle / "provenance/case-freeze.json").read_text())
    static_inputs = {
        row["path"]: VerifiedFile(case / row["path"], row["sha256"])
        for row in freeze["files"]
        if row["path"].startswith(("constant/", "system/")) and row["path"] != "system/controlDict"
    }
    frozen_control = next(row for row in freeze["files"] if row["path"] == "system/controlDict")
    template = build_static_template(
        tmp_path / "public-D-template",
        static_inputs,
        control_dict_source=case / "system/controlDict",
        control_dict_sha256=frozen_control["sha256"],
    )

    packet_manifest = json.loads((PUBLIC_RESTART / "manifest.json").read_text())
    checkpoint_name = "0.10000000000000007"
    checkpoint_root = case / checkpoint_name
    packet_prefix = f"cases/D/case/{checkpoint_name}/"
    packet_rows = {
        row["path"][len(packet_prefix) :]: row
        for row in packet_manifest["files"]
        if row["path"].startswith(packet_prefix)
    }
    field_names = (*CORE_RESTART_FIELDS, "alpha.air")
    fields = {
        name: VerifiedFile(checkpoint_root / name, packet_rows[name]["sha256"])
        for name in field_names
    }
    uniform_row = packet_rows["uniform/time"]
    uniform_time = VerifiedFile(checkpoint_root / "uniform/time", uniform_row["sha256"])

    staged = stage_canonical_checkpoint(
        template,
        tmp_path / "public-D-case",
        time_name=checkpoint_name,
        fields=fields,
        uniform_time=uniform_time,
        checkpoint_prefix="",
    )
    output = staged.path
    assert (output / "constant/polyMesh/points").is_file()
    assert (output / "constant/g").read_bytes() == (case / "constant/g").read_bytes()
    assert (output / "system/controlDict").read_bytes() == (
        case / "system/controlDict"
    ).read_bytes()
    assert (output / checkpoint_name / "T.air").read_bytes() == (
        checkpoint_root / "T.air"
    ).read_bytes()
    assert (output / checkpoint_name / "T.water").read_bytes() == (
        checkpoint_root / "T.water"
    ).read_bytes()
    assert not (output / "0").exists()
    assert not (output / "0.10025000000000008").exists()
    assert not (output / "processors10").exists()
    assert not (output / "dynamicCode").exists()
    provenance = json.loads((output / "provenance/staging-manifest.json").read_text())
    assert provenance["checkpoint_time_name"] == checkpoint_name
    assert provenance["mesh"]["collated"] == {}
    assert provenance["protected_control_dict_sha256"] == frozen_control["sha256"]
