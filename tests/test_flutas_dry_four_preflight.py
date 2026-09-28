from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from scripts.flutas_dry_four_preflight import INPUTS, _read_exact_inputs, stage

FIXTURE = Path(__file__).parents[1] / "containers/flutas/candidate5/cases/source_boundary/dry_four"


def _copy_fixture(destination: Path) -> Path:
    case = destination / "case"
    shutil.copytree(FIXTURE, case)
    return case


def test_preflight_stages_exact_read_only_triplet_and_binds_semantics(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    staged = run / "inputs"

    report = stage(case, staged)

    assert report["cell_count"] == 537_600
    assert report["interval_count"] == 14
    assert report["state_count"] == 15
    assert report["source_slot_count"] == 0
    assert report["source_velocity_parameter_applies"] is False
    assert report["input_sha256"] == INPUTS
    assert sorted(path.name for path in staged.iterdir()) == sorted(INPUTS)
    assert all(path.stat().st_mode & 0o222 == 0 for path in staged.iterdir())
    assert staged.stat().st_mode & 0o222 == 0
    assert (run / "input-preflight.json").is_file()


def test_preflight_rejects_any_byte_change_before_staging(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    path = case / "dns.in"
    path.write_bytes(path.read_bytes().replace(b"160 84 40", b"161 84 40", 1))

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _read_exact_inputs(case)


def test_preflight_rejects_extra_case_file(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    (case / "restart.dat").write_bytes(b"not allowed\n")

    with pytest.raises(ValueError, match="exactly the three"):
        _read_exact_inputs(case)


def test_preflight_rejects_linked_or_nonregular_case_inputs(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    (case / "dns.in").unlink()
    os.symlink(FIXTURE / "dns.in", case / "dns.in")

    with pytest.raises(ValueError, match="regular, singly linked"):
        _read_exact_inputs(case)


def test_staging_refuses_existing_destination_without_overwriting(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    staged = run / "inputs"
    staged.mkdir()
    sentinel = staged / "keep"
    sentinel.write_text("evidence", encoding="utf-8")

    with pytest.raises(FileExistsError):
        stage(case, staged)

    assert sentinel.read_text(encoding="utf-8") == "evidence"
