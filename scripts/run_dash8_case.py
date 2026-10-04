#!/usr/bin/env python3
"""Run prepared single-opening Dash-8 cases with the shared nearfield runner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_cl415_case import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(expected_aircraft="Dash-8"))
