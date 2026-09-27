"""Fail-closed input checks for the computed-field animation pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import scripts.render_aerial_animation as animation
from scripts.render_aerial_animation import (
    CaseSpec,
    RenderValidationError,
    _new_output_path,
    _prepare_case,
    _rename_noreplace,
    _render_backend_info,
    _validate_ground_map,
)


class _FakeMesh:
    def __init__(self, time_s: float, *, include_alpha: bool = True) -> None:
        self.n_points = 4
        self.n_cells = 2
        self.bounds = (0.0, 1.0, -1.0, 1.0, 2.0, 4.0)
        self.cell_data = {"U": np.array([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]])}
        if include_alpha:
            self.cell_data["alpha.water"] = np.array([0.0, 1.0])
        self.field_data = {"TimeValue": np.array([time_s])}


class _FakePyVista:
    PolyData = _FakeMesh

    def __init__(self, include_alpha_for: str | None = None) -> None:
        self.include_alpha_for = include_alpha_for

    def read(self, path: Path) -> _FakeMesh:
        time_s = float(path.parent.name)
        return _FakeMesh(time_s, include_alpha=path.parent.name != self.include_alpha_for)


class _MutatingPyVista(_FakePyVista):
    def read(self, path: Path) -> _FakeMesh:
        mesh = super().read(path)
        path.write_text("changed during VTP read", encoding="utf-8")
        return mesh


class _RetargetingPyVista(_FakePyVista):
    def __init__(self, link: Path, replacement: Path) -> None:
        super().__init__()
        self.link = link
        self.replacement = replacement
        self.retargeted = False

    def read(self, path: Path) -> _FakeMesh:
        if not self.retargeted:
            self.link.unlink()
            self.link.symlink_to(self.replacement)
            self.retargeted = True
        return super().read(path)


class _FakeRenderWindow:
    def GetClassName(self) -> str:
        return "vtkEGLRenderWindow"

    def ReportCapabilities(self) -> str:
        return (
            "EGL version string: 1.5\n"
            "EGL vendor string: NVIDIA\n"
            "OpenGL vendor string: NVIDIA Corporation\n"
            "OpenGL renderer string: NVIDIA GeForce RTX 5090/PCIe/SSE2\n"
            "OpenGL version string: 3.2.0 NVIDIA 580.159.03\n"
        )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _fake_run(tmp_path: Path, *, times: list[str] | None = None) -> Path:
    run_dir = tmp_path / "run-a"
    run_dir.mkdir(parents=True)
    selected_times = times or ["0.020000", "0.040000"]
    surface_hashes = {}
    for time_text in selected_times:
        relative = f"case/postProcessing/liquidInterface/{time_text}/freeSurface.vtp"
        path = run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"test frame {time_text}", encoding="utf-8")
        surface_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_json(
        run_dir / "manifest.json",
        {"run_id": "run-a", "surface_artifact_hashes": surface_hashes},
    )
    _write_json(
        run_dir / "pilot-report.json",
        {
            "run_id": "run-a",
            "surface_artifacts": {
                "count": len(selected_times),
                "format": "VTK PolyData interface surfaces (.vtp)",
                "fields": ["alpha.water", "U"],
                "times_s": selected_times,
            },
        },
    )
    return run_dir


def test_frame_preflight_requires_every_declared_hashed_actual_surface(tmp_path: Path) -> None:
    run_dir = _fake_run(tmp_path)
    case = _prepare_case(CaseSpec("diagnostic", run_dir), _FakePyVista(), "diagnostic")
    assert [frame.time_s for frame in case.frames] == [0.02, 0.04]
    assert case.speed_max_m_s == pytest.approx(2.0)
    assert case.bounds == (0.0, 1.0, -1.0, 1.0, 2.0, 4.0)

    missing_frame_dir = tmp_path / "missing"
    missing_frame_dir.mkdir()
    missing_run = _fake_run(missing_frame_dir)
    (missing_run / "case/postProcessing/liquidInterface/0.040000/freeSurface.vtp").unlink()
    with pytest.raises(RenderValidationError, match="declared simulation frame .* is missing"):
        _prepare_case(CaseSpec("diagnostic", missing_run), _FakePyVista(), "diagnostic")


def test_frame_preflight_rejects_missing_required_scalar_and_hash_mismatch(tmp_path: Path) -> None:
    run_dir = _fake_run(tmp_path)
    with pytest.raises(RenderValidationError, match="cell arrays U and alpha.water"):
        _prepare_case(
            CaseSpec("diagnostic", run_dir),
            _FakePyVista(include_alpha_for="0.040000"),
            "diagnostic",
        )

    vtp = run_dir / "case/postProcessing/liquidInterface/0.020000/freeSurface.vtp"
    vtp.write_text("changed without a manifest update", encoding="utf-8")
    with pytest.raises(RenderValidationError, match="hash is missing or incorrect"):
        _prepare_case(CaseSpec("diagnostic", run_dir), _FakePyVista(), "diagnostic")


def test_frame_preflight_rejects_a_surface_mutated_during_read(tmp_path: Path) -> None:
    run_dir = _fake_run(tmp_path)
    with pytest.raises(RenderValidationError, match="changed while it was read"):
        _prepare_case(CaseSpec("diagnostic", run_dir), _MutatingPyVista(), "diagnostic")


def test_render_manifest_backend_records_active_egl_and_opengl_identity() -> None:
    assert _render_backend_info(_FakeRenderWindow()) == {
        "window_class": "vtkEGLRenderWindow",
        "egl_vendor": "NVIDIA",
        "egl_version": "1.5",
        "opengl_vendor": "NVIDIA Corporation",
        "opengl_renderer": "NVIDIA GeForce RTX 5090/PCIe/SSE2",
        "opengl_version": "3.2.0 NVIDIA 580.159.03",
    }


def test_validated_preflight_freezes_resolved_sidecar_paths(tmp_path: Path) -> None:
    case = _valid_ground_map(tmp_path / "case")
    assert case.protocol_record is not None
    protocol_link = tmp_path / "protocol-link.json"
    protocol_link.symlink_to(case.protocol_record)
    replacement = tmp_path / "replacement-protocol.json"
    _write_json(replacement, {"schema": "attacker-controlled replacement"})
    spec = CaseSpec(
        case.label,
        case.run_dir,
        case.ground_map,
        case.ground_map_record,
        case.validation_record,
        protocol_link,
    )

    prepared = _prepare_case(spec, _RetargetingPyVista(protocol_link, replacement), "validated")

    assert protocol_link.resolve() == replacement.resolve()
    assert prepared.protocol is not None
    assert prepared.protocol["gate_id"] == "E4-ground-map"


def _valid_ground_map(tmp_path: Path, *, corrupt_map: bool = False) -> CaseSpec:
    run_dir = _fake_run(tmp_path)
    map_path = run_dir / "ground-map.npz"
    concentration = np.array([[2.0], [3.0]])
    if corrupt_map:
        concentration[0, 0] = 4.0
    np.savez_compressed(
        map_path,
        weighted_deposition_x_edges_m=np.array([0.0, 1.0, 2.0]),
        weighted_deposition_y_edges_m=np.array([-0.5, 0.5]),
        weighted_deposition_kg_m2=concentration,
        impact_locations_xy_m=np.array([[0.5, 0.0], [1.5, 0.0], [3.0, 0.0]]),
        impact_masses_kg=np.array([2.0, 3.0, 4.0]),
    )
    record_path = run_dir / "ground-map.json"
    _write_json(
        record_path,
        {
            "schema": "aerial-drop-ground-map/v1",
            "run_id": "run-a",
            "artifact": map_path.name,
            "artifact_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
            "mass_ledger": {
                "released_kg": 12.0,
                "in_map_deposited_kg": 5.0,
                "outside_map_deposited_kg": 4.0,
                "airborne_vof_kg": 2.0,
                "airborne_parcel_kg": 0.0,
                "escaped_kg": 1.0,
                "evaporated_kg": 0.0,
                "residual_kg": 0.0,
                "tolerance_kg": 1e-9,
            },
            "scoring": {
                "target_rectangle_xy_m": [0.0, 2.0, -0.5, 0.5],
                "l95_interval_x_m": [1.0, 2.0],
                "l95_m": 1.0,
                "coverage_threshold_kg_m2": 2.4,
            },
        },
    )
    validation_path = run_dir / "validation.json"
    protocol_path = run_dir / "protocol.json"
    _write_json(
        protocol_path,
        {
            "schema": "aerial-drop-protocol/v1",
            "run_id": "run-a",
            "gate_id": "E4-ground-map",
            "review_status": "accepted",
            "review_evidence": "independent protocol review record",
            "mass_ledger_tolerance_kg": 1e-9,
        },
    )
    validation = {
        "schema": "aerial-drop-validation/v1",
        "run_id": "run-a",
        "gate_id": "E4-ground-map",
        "gate_type": "ground_map",
        "gate_status": "pass",
        "evidence": "reviewed conservative deposition audit",
        "manifest_sha256": hashlib.sha256((run_dir / "manifest.json").read_bytes()).hexdigest(),
        "ground_map_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "ground_map_artifact_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
        "protocol_record_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "accepted_mass_ledger_tolerance_kg": 1e-9,
    }
    _write_json(
        validation_path,
        validation,
    )
    return CaseSpec(
        "validated",
        run_dir,
        map_path,
        record_path,
        validation_path,
        protocol_path,
    )


def test_ground_map_validation_rebins_impacts_and_closes_mass_ledger(tmp_path: Path) -> None:
    case = _valid_ground_map(tmp_path)
    data, record, _, _ = _validate_ground_map(case, "run-a")
    assert data["weighted_deposition_kg_m2"].tolist() == [[2.0], [3.0]]
    assert record["mass_ledger"]["outside_map_deposited_kg"] == 4.0
    prepared = _prepare_case(case, _FakePyVista(), "validated")
    assert prepared.validation is not None
    assert prepared.validation["gate_status"] == "pass"


def test_ground_map_validation_fails_closed_on_corrupt_map_or_missing_artifact(
    tmp_path: Path,
) -> None:
    corrupt_case = _valid_ground_map(tmp_path, corrupt_map=True)
    with pytest.raises(RenderValidationError, match="does not match conservative rebinning"):
        _validate_ground_map(corrupt_case, "run-a")

    missing_case = CaseSpec("missing", tmp_path / "none")
    with pytest.raises(RenderValidationError, match="needs both --ground-map"):
        _validate_ground_map(missing_case, "run-a")


def test_ground_map_validation_recomputes_l95_and_requires_centered_target(tmp_path: Path) -> None:
    case = _valid_ground_map(tmp_path)
    record = json.loads(case.ground_map_record.read_text(encoding="utf-8"))
    record["scoring"]["l95_interval_x_m"] = [0.0, 2.0]
    record["scoring"]["l95_m"] = 2.0
    _write_json(case.ground_map_record, record)
    with pytest.raises(RenderValidationError, match="recomputed ground score"):
        _validate_ground_map(case, "run-a")

    centered_case = _valid_ground_map(tmp_path / "centered")
    centered_record = json.loads(centered_case.ground_map_record.read_text(encoding="utf-8"))
    centered_record["scoring"]["target_rectangle_xy_m"] = [0.0, 2.0, 0.0, 1.0]
    _write_json(centered_case.ground_map_record, centered_record)
    with pytest.raises(RenderValidationError, match="centered on y=0"):
        _validate_ground_map(centered_case, "run-a")


def test_validation_pass_is_bound_to_exact_manifest_and_ground_map_inputs(tmp_path: Path) -> None:
    changed_record_case = _valid_ground_map(tmp_path)
    record = json.loads(changed_record_case.ground_map_record.read_text(encoding="utf-8"))
    record["review_annotation"] = "changed after the validation pass"
    _write_json(changed_record_case.ground_map_record, record)
    with pytest.raises(RenderValidationError, match="ground_map_record_sha256"):
        _prepare_case(changed_record_case, _FakePyVista(), "validated")

    unrelated_gate_case = _valid_ground_map(tmp_path / "unrelated")
    validation = json.loads(unrelated_gate_case.validation_record.read_text(encoding="utf-8"))
    validation["gate_id"] = "E0-analytical"
    _write_json(unrelated_gate_case.validation_record, validation)
    with pytest.raises(RenderValidationError, match="accepted ground-map protocol"):
        _prepare_case(unrelated_gate_case, _FakePyVista(), "validated")

    changed_manifest_case = _valid_ground_map(tmp_path / "changed-manifest")
    manifest_path = changed_manifest_case.run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["post-validation-edit"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(RenderValidationError, match="manifest_sha256"):
        _prepare_case(changed_manifest_case, _FakePyVista(), "validated")


def test_full_bundle_requires_a_passed_matching_gate(tmp_path: Path) -> None:
    case = _valid_ground_map(tmp_path)
    assert case.validation_record is not None
    validation = json.loads(case.validation_record.read_text(encoding="utf-8"))
    validation["gate_status"] = "diagnostic"
    _write_json(case.validation_record, validation)
    with pytest.raises(RenderValidationError, match="gate status is not pass"):
        _prepare_case(case, _FakePyVista(), "validated")


@pytest.mark.parametrize(
    ("field", "value", "interval", "l95"),
    [
        ("target_rectangle_xy_m", [0.5, 2.0, -0.5, 0.5], [1.0, 2.0], 1.0),
        ("coverage_threshold_kg_m2", 1.0, [0.0, 2.0], 2.0),
    ],
)
def test_validated_comparisons_require_shared_scoring_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
    interval: list[float],
    l95: float,
) -> None:
    first = _valid_ground_map(tmp_path / "first")
    second = _valid_ground_map(tmp_path / "second")
    record = json.loads(second.ground_map_record.read_text(encoding="utf-8"))
    record["scoring"][field] = value
    record["scoring"]["l95_interval_x_m"] = interval
    record["scoring"]["l95_m"] = l95
    _write_json(second.ground_map_record, record)
    validation = json.loads(second.validation_record.read_text(encoding="utf-8"))
    validation["ground_map_record_sha256"] = hashlib.sha256(
        second.ground_map_record.read_bytes()
    ).hexdigest()
    _write_json(second.validation_record, validation)

    monkeypatch.setattr(animation, "_load_pyvista", _FakePyVista)
    with pytest.raises(
        RenderValidationError,
        match="identical target rectangles and coverage thresholds",
    ):
        animation.render_animation(
            [
                CaseSpec(
                    "baseline",
                    first.run_dir,
                    first.ground_map,
                    first.ground_map_record,
                    first.validation_record,
                    first.protocol_record,
                ),
                CaseSpec(
                    "comparison",
                    second.run_dir,
                    second.ground_map,
                    second.ground_map_record,
                    second.validation_record,
                    second.protocol_record,
                ),
            ],
            tmp_path / "render",
            mode="validated",
        )


def test_output_path_rejects_dangling_symlinks_and_atomic_publish_never_overwrites(
    tmp_path: Path,
) -> None:
    dangling = tmp_path / "dangling-output"
    dangling.symlink_to(tmp_path / "missing-target")
    with pytest.raises(RenderValidationError, match="refusing to overwrite"):
        _new_output_path(dangling)

    source = tmp_path / "staged-output"
    destination = tmp_path / "published-output"
    source.mkdir()
    destination.mkdir()
    (source / "payload").write_text("new", encoding="utf-8")
    (destination / "payload").write_text("existing", encoding="utf-8")
    with pytest.raises(RenderValidationError, match="refusing to overwrite"):
        _rename_noreplace(source, destination)
    assert (source / "payload").read_text(encoding="utf-8") == "new"
    assert (destination / "payload").read_text(encoding="utf-8") == "existing"
