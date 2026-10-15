from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

AUDITOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rouaix_checkpoint_audit.py"
SPEC = importlib.util.spec_from_file_location("rouaix_checkpoint_audit", AUDITOR_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDITOR)


def _write_history(path: Path, rows: list[tuple[float, float]], tail: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "# Time native-value\n" + "".join(
        f"{time_s:.12g} {value:.12g}\n" for time_s, value in rows
    )
    path.write_text(content + tail, encoding="ascii")


def _case(tmp_path: Path) -> tuple[Path, Path]:
    case = tmp_path / "case"
    declaration_path = tmp_path / "case-declaration.json"
    declaration = {
        "run_id": "rouaix-prefix-fixture",
        "checkpoint": {"time_s": 1.0, "native_water_volume_m3": 1.0},
        "parent_ledger_offsets": {
            "checkpoint_inventory_volume_m3": 1.0,
            "prior_release_volume_m3": 1.5,
            "prior_escape_volume_m3": 0.5,
            "checkpoint_residual_expected_minus_observed_kg": 0.0,
            "offset_applied_once": True,
        },
    }
    declaration_path.write_text(json.dumps(declaration), encoding="utf-8")
    inventory = case / "postProcessing/waterInventory/0/volFieldValue.dat"
    _write_history(
        inventory,
        [(1.05, 1.0), (1.1, 1.0)],
        tail="1.2 1.0\n1.2005",
    )
    with inventory.open("ab") as stream:
        stream.write(b"\xfftruncated future row")
    for patch in AUDITOR.PATCHES:
        flux = -0.2 if patch == "nozzle" else (0.2 if patch == "gasInlet" else 0.0)
        rows = [(1.05, flux), (1.1, flux)]
        path = case / f"postProcessing/liquidFlux_{patch}/0/surfaceFieldValue.dat"
        _write_history(path, rows)
    return case, declaration_path


def test_audit_uses_exact_closed_prefix_and_ignores_unequal_future_tails(tmp_path: Path) -> None:
    case, declaration = _case(tmp_path)

    report = AUDITOR.audit(
        case,
        declaration,
        through_time_s=1.1,
        output_dir=tmp_path / "audit",
    )

    assert report["actual_final_time_s"] == 1.1
    assert report["rows"] == 2
    assert report["continuation_guard_0p1_percent"] == {
        "incremental_pass": True,
        "cumulative_pass": True,
    }
    assert (
        report["incremental_ledger_from_checkpoint"]["residual_expected_minus_observed_kg"] == 0.0
    )


def test_audit_rejects_mismatched_times_inside_the_requested_prefix(tmp_path: Path) -> None:
    case, declaration = _case(tmp_path)
    nozzle = case / "postProcessing/liquidFlux_nozzle/0/surfaceFieldValue.dat"
    _write_history(nozzle, [(1.050001, -0.2), (1.1, -0.2)])

    with pytest.raises(ValueError, match="time mismatch"):
        AUDITOR.audit(
            case,
            declaration,
            through_time_s=1.1,
            output_dir=tmp_path / "audit-mismatch",
        )


def test_audit_rejects_a_history_missing_the_exact_cutoff(tmp_path: Path) -> None:
    case, declaration = _case(tmp_path)
    nozzle = case / "postProcessing/liquidFlux_nozzle/0/surfaceFieldValue.dat"
    _write_history(nozzle, [(1.05, -0.2), (1.2, -0.2)])

    with pytest.raises(ValueError, match="requested checkpoint time .* is missing"):
        AUDITOR.audit(
            case,
            declaration,
            through_time_s=1.1,
            output_dir=tmp_path / "audit-missing",
        )
