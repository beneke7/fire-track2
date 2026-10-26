#!/usr/bin/env python3
"""Stage an untouched A, C, or D reproduction case without endpoint files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PACKET = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("A", "C", "D"))
    parser.add_argument("output", type=Path, help="new path; must not already exist")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite staged case: {args.output}")

    source = PACKET / "cases" / args.arm / "case"
    freeze = json.loads(
        (PACKET / "cases" / args.arm / "provenance" / "case-freeze.json").read_text()
    )
    args.output.mkdir(parents=True)
    try:
        for name in ("0", "constant", "system"):
            shutil.copytree(source / name, args.output / name)
        if args.arm in {"C", "D"}:
            shutil.copytree(
                source / "0.10000000000000007",
                args.output / "0.10000000000000007",
            )
        for row in freeze["files"]:
            path = args.output / row["path"]
            if (
                not path.is_file()
                or path.stat().st_size != row["bytes"]
                or sha256(path) != row["sha256"]
            ):
                raise RuntimeError(f"staged input mismatch: {row['path']}")
        print(
            json.dumps(
                {
                    "status": "staged_and_static_inputs_verified",
                    "arm": args.arm,
                    "output": str(args.output),
                    "initial_restart_time": (
                        "0.10000000000000007" if args.arm in {"C", "D"} else "0"
                    ),
                    "static_file_count": freeze["static_file_count"],
                    "static_tree_sha256": freeze["static_tree_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        shutil.rmtree(args.output)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
