"""Check that restart histories represent only the continued CFD trajectory."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("pyvista")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cases/restas_amr_probe"))
import analyze_hnf_mesh_comparison as analysis  # noqa: E402


def write_flux(case: Path, start: str, rows: list[tuple[float, float]]) -> None:
    path = case / "postProcessing/slot_01Flux" / start / "surfaceFieldValue.dat"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# Time sum(phi) sum(alphaPhi_)\n"
        + "".join(f"{timestamp} 0 {flux}\n" for timestamp, flux in rows),
        encoding="utf-8",
    )


def test_restart_discards_abandoned_future_and_retains_checkpoint_anchor(tmp_path: Path) -> None:
    # The old run continued past t=2 before stopping, but only t=2 was saved.
    # Its enormous later flux must not contaminate the resumed trajectory.
    write_flux(tmp_path, "0.000000", [(0, -1), (1, -1), (2, -1), (3, -1000), (4, -1000)])
    write_flux(tmp_path, "2.000000", [(2.5, -2), (3, -2), (4, -2), (5, -2)])

    rows = analysis.boundary_flux_history(tmp_path)["slot_01"]

    assert rows == [(0, -1), (1, -1), (2, -1), (2.5, -2), (3, -2), (4, -2), (5, -2)]
    assert analysis.integrate_boundary_volume(rows, inward=True) == pytest.approx(7.75)


def test_new_branch_wins_at_checkpoint_and_branch_order_is_numeric(tmp_path: Path) -> None:
    write_flux(tmp_path, "0", [(0, -1), (2, -999), (12, -999)])
    write_flux(tmp_path, "2", [(2, -2), (3, -2), (10, -999), (12, -999)])
    write_flux(tmp_path, "10", [(10, -3), (11, -3), (11, -4), (12, -4)])

    rows = analysis.boundary_flux_history(tmp_path)["slot_01"]

    assert rows == [(0, -1), (2, -2), (3, -2), (10, -3), (11, -4), (12, -4)]
    assert len(rows) == len({timestamp for timestamp, _ in rows})
