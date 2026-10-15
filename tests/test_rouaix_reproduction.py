from __future__ import annotations

import json
import subprocess

import pytest

from scripts import run_rouaix_reproduction as reproduction


def _source_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reproduction,
        "read_json",
        lambda _path: {"launch": {"command": ["docker", "run", "--name", "rouaix-source"]}},
    )


def test_source_container_inspection_failure_blocks_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_manifest(monkeypatch)
    monkeypatch.setattr(
        reproduction,
        "run_command",
        lambda command, check=False: subprocess.CompletedProcess(
            command, 1, "", "Docker daemon unavailable"
        ),
    )

    with pytest.raises(reproduction.RunError, match="cannot verify source CFD container state"):
        reproduction.source_container_state()


def test_source_container_must_report_a_boolean_stopped_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_manifest(monkeypatch)
    monkeypatch.setattr(
        reproduction,
        "run_command",
        lambda command, check=False: subprocess.CompletedProcess(
            command, 0, json.dumps({"Status": "exited"}), ""
        ),
    )

    with pytest.raises(reproduction.RunError, match="did not report a boolean running state"):
        reproduction.source_container_state()


def test_source_container_stopped_state_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_manifest(monkeypatch)
    monkeypatch.setattr(
        reproduction,
        "run_command",
        lambda command, check=False: subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"Running": False, "Status": "exited", "ExitCode": 0}),
            "",
        ),
    )

    state = reproduction.source_container_state()

    assert state["name"] == "rouaix-source"
    assert state["inspect_available"] is True
    assert state["running"] is False
    assert state["exit_code"] == 0
