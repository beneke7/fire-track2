#!/usr/bin/env python3
"""Cache local PDF text and a content-addressed inventory without changing originals."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def extract(pdf: Path, root: Path, output: Path) -> dict:
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    text_path = output / f"{digest}.txt"
    if not text_path.exists():
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True,
            check=True,
            timeout=120,
        )
        text_path.write_bytes(completed.stdout)
    return {
        "path": str(pdf.relative_to(root)),
        "sha256": digest,
        "bytes": pdf.stat().st_size,
        "text_path": str(text_path),
        "extraction": "pdftotext -layout; form-feed separates PDF pages",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/derived/papers"))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if shutil.which("pdftotext") is None:
        parser.error("pdftotext is required (Poppler utilities)")
    root = Path(__file__).resolve().parents[1]
    papers = sorted(root.glob("*.pdf"))
    if not papers:
        parser.error("no PDFs found in the repository root")
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=min(args.workers, len(papers))) as pool:
        records = list(pool.map(lambda pdf: extract(pdf, root, args.output), papers))
    manifest = args.output / "index.json"
    manifest.write_text(json.dumps({"papers": records}, indent=2) + "\n")
    print(f"Indexed {len(records)} papers: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
