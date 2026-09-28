"""Guard the source helper harness against candidate5's whole-array calls."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def check_validator(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    calls: list[str] = []
    start_pattern = re.compile(
        r"\bcall\s+restas_source_(?:accumulate_boundary_flux|record_inventory|"
        r"record_velocity_audit)\s*\(",
        re.IGNORECASE,
    )
    index = 0
    while index < len(lines):
        if not start_pattern.search(lines[index]):
            index += 1
            continue
        statement = lines[index]
        while statement.rstrip().endswith("&") and index + 1 < len(lines):
            index += 1
            statement += lines[index]
        calls.append(statement)
        index += 1
    if len(calls) != 7:
        raise AssertionError(f"expected 7 audited helper calls, found {len(calls)}")
    for index, arguments in enumerate(calls, start=1):
        normalized = re.sub(r"\s+|&", "", arguments).lower()
        if "dzf(0:)" not in normalized:
            raise AssertionError(f"helper call {index} does not pass the physical-index slice")
        if re.search(r"\bdzf,", arguments, re.IGNORECASE):
            raise AssertionError(f"helper call {index} passes the whole dzf array")
    return len(calls)


if __name__ == "__main__":
    validator = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name(
        "source_boundary_validator.f90"
    )
    print(f"PASS: {check_validator(validator)} helper calls pass dzf(0:)")
