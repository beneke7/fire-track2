"""Portable snapshot inventory used by the captured Rouaix fast runner.

The executed runner is preserved in the committed queue source capsule rather
than installed as an importable module. This helper promotes its inventory
logic from that captured source (SHA256
``b645afb746ce1259294fe7ebad83989bd434ef0bff73ab4855133f53f1a3af07``).
It checks required collated fields at declared write times reached by the
terminal solver time, plus the actual terminal time when present.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


def snapshot_inventory(output_dir: Path, case_dir: Path) -> dict[str, Any]:
    """Inventory required fields in an extracted collated solver snapshot."""
    evidence = output_dir / "evidence/case/times"
    metadata = json.loads((case_dir / "case-inputs.json").read_text(encoding="utf-8"))
    declared = {f"{float(value):.12g}" for value in metadata["field_write_times_s"]}
    terminal_path = output_dir / "terminal-status.json"
    terminal_time = None
    if terminal_path.is_file():
        terminal_time = json.loads(terminal_path.read_text(encoding="utf-8")).get("solver_time_s")
        if terminal_time and terminal_time != "unknown":
            terminal_time = f"{float(terminal_time):.12g}"
        else:
            terminal_time = None
    reached_declared = {
        time_value
        for time_value in declared
        if terminal_time is not None and float(time_value) <= float(terminal_time) + 1e-10
    }
    unreached_declared = declared - reached_declared
    expected = set(reached_declared)
    if terminal_time is not None:
        expected.add(terminal_time)
    checks: dict[str, Any] = {}
    for time_value in sorted(expected, key=float):
        checks[time_value] = {}
        for field in ("U", "alpha.water", "p_rgh"):
            matches = (
                [
                    path
                    for path in evidence.rglob(field)
                    if path.is_file()
                    and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", path.parent.name)
                    and math.isclose(
                        float(path.parent.name), float(time_value), rel_tol=0.0, abs_tol=1e-10
                    )
                ]
                if evidence.is_dir()
                else []
            )
            checks[time_value][field] = {
                "present": bool(matches),
                "paths": [str(path.relative_to(output_dir / "evidence")) for path in matches],
                "bytes": sum(path.stat().st_size for path in matches),
            }
    result = {
        "schema_version": 1,
        "field_handler": "collated",
        "required_fields": ["U", "alpha.water", "p_rgh"],
        "declared_times_s": sorted(declared, key=float),
        "reached_declared_times_s": sorted(reached_declared, key=float),
        "unreached_declared_times_s": sorted(unreached_declared, key=float),
        "terminal_time_s": terminal_time,
        "expected_captured_times_s": sorted(expected, key=float),
        "times": checks,
        "passed": terminal_time is not None
        and bool(checks)
        and all(item["present"] for per_time in checks.values() for item in per_time.values()),
    }
    (output_dir / "snapshot-inventory.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
