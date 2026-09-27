"""Fast tests for P1 launch approval and hard-stop controls."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_restas_pilot import (  # noqa: E402
    _execution_stop_reason,
    _hash,
    _validate_p1_execution_contract,
)


def _ready_contract() -> dict[str, object]:
    return {
        "execution_status": "ready",
        "independent_review": {
            "decision": "approved_with_revisions",
            "amendment_1_review_decision": "approved_with_revisions",
            "amendment_1_reviewer": "test-reviewer",
            "amendment_1_reviewed_utc": "2026-09-25T00:00:00Z",
            "execution_code_review": "approved",
            "execution_code_reviewer": "test-code-reviewer",
            "execution_code_reviewed_utc": "2026-09-25T00:00:00Z",
        },
        "reviewed_code_sha256": {
            "Makefile": _hash(ROOT / "Makefile"),
            "scripts/analyze_restas_pilot.py": _hash(ROOT / "scripts" / "analyze_restas_pilot.py"),
            "scripts/run_restas_pilot.py": _hash(ROOT / "scripts" / "run_restas_pilot.py"),
            "scripts/analyze_restas_ledger.py": _hash(
                ROOT / "scripts" / "analyze_restas_ledger.py"
            ),
            "scripts/doctor.py": _hash(ROOT / "scripts" / "doctor.py"),
            "scripts/run_local.py": _hash(ROOT / "scripts" / "run_local.py"),
        },
        "experiment_id": "P1_SOURCE_EVENT_LEDGER",
        "protocol_revision": 2,
        "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
        "protocol_document_sha256": _hash(
            ROOT / "experiments" / "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1.md"
        ),
        "source_profile_m_s": [[0.0, -4.8], [0.0795, -4.8], [0.0805, 0.0], [0.12, 0.0]],
        "continuous_expected_release_kg": 230.4,
        "alpha_phi_sampling_convention": "left_endpoint_of_completed_interval",
        "alpha_phi_left_sampled_expected_release_kg": 230.544,
        "alpha_phi_left_sampled_expected_release_per_slot_kg": 57.636,
        "phi_right_sampled_expected_release_kg": 230.256,
        "phi_right_sampled_expected_release_per_slot_kg": 57.564,
        "source_dose_tolerance_fraction": 0.001,
        "mass_ledger_tolerance_fraction_of_cumulative_source": 0.001,
        "fixed_delta_t_s": 1e-4,
        "expected_time_steps": 1200,
        "n_alpha_sub_cycles": 1,
        "max_courant": 0.5,
        "max_alpha_courant": 0.25,
        "hard_stop_on_courant_breach": True,
        "mpi_ranks": 16,
        "max_memory_gib": 48,
        "max_wall_time_s": 3600,
    }


def test_ready_gate_returns_frozen_wall_limit_and_accepts_lower_resources() -> None:
    assert _validate_p1_execution_contract(_ready_contract(), ranks=8, memory_gib=24) == 3600


@pytest.mark.parametrize(
    ("mutate", "ranks", "memory_gib", "message"),
    [
        (lambda c: c.update(execution_status="draft"), 16, 48, "not ready"),
        (
            lambda c: c["independent_review"].update(decision="pending"),
            16,
            48,
            "scientific review",
        ),
        (
            lambda c: c["independent_review"].update(execution_code_review="pending"),
            16,
            48,
            "code review",
        ),
        (
            lambda c: c["independent_review"].update(amendment_1_review_decision="pending"),
            16,
            48,
            "sampling-convention amendment",
        ),
        (
            lambda c: c["reviewed_code_sha256"].update(
                {"scripts/analyze_restas_ledger.py": "0" * 64}
            ),
            16,
            48,
            "reviewed code hash no longer matches",
        ),
        (lambda c: c.update(mpi_ranks=32), 16, 48, "reviewed 16 ranks"),
        (lambda c: c.update(max_memory_gib=64), 16, 48, "reviewed 48 GiB"),
        (lambda c: c.update(max_wall_time_s=7200), 16, 48, "reviewed 3,600 s"),
        (lambda c: None, 17, 48, "at most 16 MPI ranks"),
        (lambda c: None, 16, 49, "at most 48 GiB"),
    ],
)
def test_p1_gate_rejects_unapproved_or_over_budget_runs(
    mutate, ranks: int, memory_gib: int, message: str
) -> None:
    contract = _ready_contract()
    mutate(contract)
    with pytest.raises(ValueError, match=message):
        _validate_p1_execution_contract(contract, ranks=ranks, memory_gib=memory_gib)


def test_ready_status_cannot_override_a_protocol_mismatch() -> None:
    contract = _ready_contract()
    contract["fixed_delta_t_s"] = 5e-5
    with pytest.raises(ValueError, match="fixed_delta_t_s"):
        _validate_p1_execution_contract(contract, ranks=16, memory_gib=48)


def test_ready_gate_requires_hashes_for_exact_reviewed_code_files() -> None:
    contract = _ready_contract()
    contract["reviewed_code_sha256"].pop("scripts/run_restas_pilot.py")
    with pytest.raises(ValueError, match="freeze every file in the local execution path"):
        _validate_p1_execution_contract(contract, ranks=16, memory_gib=48)


def test_ready_gate_requires_the_reviewed_amendment_document_hash() -> None:
    contract = _ready_contract()
    contract["protocol_document_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="amendment document hash"):
        _validate_p1_execution_contract(contract, ranks=16, memory_gib=48)


def test_courant_stop_parser_enforces_both_declared_ceilings() -> None:
    limits = (0.5, 0.25)
    assert (
        _execution_stop_reason(
            "Courant Number mean: 0.1 max: 0.5001",
            elapsed_s=2,
            courant_limits=limits,
            wall_timeout_s=3600,
        )
        == "global Co 0.5001 exceeded 0.5"
    )
    assert (
        _execution_stop_reason(
            "Interface Courant Number mean: 0.1 max: 0.26",
            elapsed_s=2,
            courant_limits=limits,
            wall_timeout_s=3600,
        )
        == "interface Co 0.26 exceeded 0.25"
    )
    assert (
        _execution_stop_reason(
            "Courant Number mean: 0.1 max: 0.5",
            elapsed_s=2,
            courant_limits=limits,
            wall_timeout_s=3600,
        )
        is None
    )


def test_wall_stop_fires_at_frozen_timeout() -> None:
    assert (
        _execution_stop_reason("", elapsed_s=3600, courant_limits=None, wall_timeout_s=3600)
        == "wall-time limit of 3600 s reached"
    )
