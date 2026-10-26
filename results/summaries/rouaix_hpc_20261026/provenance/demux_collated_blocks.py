#!/usr/bin/env python3
"""Byte-preserving unpacking of OpenFOAM decomposedBlockData containers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

FILES = (
    "constant/polyMesh/points",
    "constant/polyMesh/faces",
    "constant/polyMesh/owner",
    "constant/polyMesh/neighbour",
    "constant/polyMesh/boundary",
    "0.000000000000/alpha.water",
    "0.000000000000/U",
    "0.050000000000/alpha.water",
    "0.050000000000/U",
)
MARKER_PREFIX = b"// processor"
COPY_CHUNK = 1024 * 1024


class FormatError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def read_count_line(stream, filename: str, rank: int) -> int:
    line = stream.readline()
    if not line.endswith(b"\n") or not line[:-1].isdigit():
        raise FormatError(f"{filename}: processor{rank} has invalid byte-count line {line!r}")
    return int(line[:-1])


def find_first_marker(stream, filename: str) -> None:
    prefix = stream.read(65536)
    marker = MARKER_PREFIX + b"0\n"
    offset = prefix.find(marker)
    if offset < 0:
        raise FormatError(f"{filename}: processor0 marker not found in outer header")
    stream.seek(offset + len(marker))


def extract_foam_header(payload_path: Path, expected_size: int) -> bytes:
    with payload_path.open("rb") as source:
        prefix = source.read(min(expected_size, 65536))
    if not prefix.startswith(b"FoamFile"):
        raise FormatError(f"processor0 payload in {payload_path} does not start with FoamFile")
    opening = prefix.find(b"{")
    if opening < 0:
        raise FormatError(f"processor0 FoamFile header in {payload_path} has no opening brace")
    depth = 0
    quote = False
    escaped = False
    for index in range(opening, len(prefix)):
        byte = prefix[index]
        if quote:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                quote = False
            continue
        if byte == ord('"'):
            quote = True
        elif byte == ord("{"):
            depth += 1
        elif byte == ord("}"):
            depth -= 1
            if depth == 0:
                end = index + 1
                if end < len(prefix) and prefix[end:end + 2] == b"\r\n":
                    end += 2
                elif end < len(prefix) and prefix[end:end + 1] == b"\n":
                    end += 1
                return prefix[:end]
    raise FormatError(f"processor0 FoamFile header in {payload_path} did not close in 64 KiB")


def copy_exact(source, destination, size: int, digest) -> None:
    remaining = size
    while remaining:
        chunk = source.read(min(COPY_CHUNK, remaining))
        if not chunk:
            raise FormatError(f"truncated processor payload: wanted {size} bytes")
        destination.write(chunk)
        digest.update(chunk)
        remaining -= len(chunk)


def demux_file(source_path: Path, case_root: Path, relative: str, ranks: int, total_ranks: int) -> dict:
    if ranks < 1 or ranks > total_ranks:
        raise ValueError(f"ranks must be in 1..{total_ranks}")
    source_hash = sha256_file(source_path)
    records = []
    shared_header = None
    with source_path.open("rb") as source:
        find_first_marker(source, relative)
        for rank in range(ranks):
            count = read_count_line(source, relative, rank)
            opener = source.read(1)
            if opener != b"(":
                raise FormatError(f"{relative}: processor{rank} expected '(', found {opener!r}")

            output_path = case_root / f"processor{rank}" / relative
            output_path.parent.mkdir(parents=True, exist_ok=True)
            raw_digest = hashlib.sha256()
            with output_path.open("xb") as output:
                if rank:
                    if shared_header is None:
                        raise FormatError(f"{relative}: shared processor0 header was not extracted")
                    output.write(shared_header)
                copy_exact(source, output, count, raw_digest)
                output.flush()
                os.fsync(output.fileno())

            if rank == 0:
                shared_header = extract_foam_header(output_path, count)
            closing = source.read(1)
            if closing != b")":
                raise FormatError(f"{relative}: processor{rank} payload length does not end at ')': {closing!r}")

            records.append(
                {
                    "rank": rank,
                    "payload_bytes": count,
                    "payload_sha256": raw_digest.hexdigest(),
                    "output": str(output_path),
                    "output_bytes": output_path.stat().st_size,
                    "output_sha256": sha256_file(output_path),
                }
            )

            line = source.readline()
            if rank + 1 < ranks:
                if line != b"\n":
                    raise FormatError(f"{relative}: processor{rank} closing delimiter is malformed: {line!r}")
                separator = source.readline()
                marker = source.readline()
                expected_marker = MARKER_PREFIX + str(rank + 1).encode("ascii") + b"\n"
                if separator != b"\n" or marker != expected_marker:
                    raise FormatError(
                        f"{relative}: expected contiguous processor{rank + 1}, got {separator!r} {marker!r}"
                    )
            elif ranks < total_ranks:
                if line != b"\n":
                    raise FormatError(f"{relative}: processor{rank} closing delimiter is malformed: {line!r}")
                separator = source.readline()
                marker = source.readline()
                expected_marker = MARKER_PREFIX + str(rank + 1).encode("ascii") + b"\n"
                if separator != b"\n" or marker != expected_marker:
                    raise FormatError(
                        f"{relative}: proof block does not continue with processor{rank + 1}: {separator!r} {marker!r}"
                    )
            else:
                if line != b"\n" or source.read(1):
                    raise FormatError(f"{relative}: final processor close or EOF is malformed: {line!r}")

    return {
        "source": str(source_path),
        "source_bytes": source_path.stat().st_size,
        "source_sha256": source_hash,
        "shared_header_bytes": len(shared_header or b""),
        "processed_ranks": ranks,
        "total_ranks": total_ranks,
        "blocks": records,
    }


def wrap_fixture(payloads: list[bytes]) -> bytes:
    parts = [b"FoamFile\n{\nclass decomposedBlockData;\n}\n(\n"]
    for rank, payload in enumerate(payloads):
        parts.append(f"// processor{rank}\n{len(payload)}\n(".encode("ascii"))
        parts.append(payload)
        if rank + 1 < len(payloads):
            parts.append(b")\n\n")
        else:
            parts.append(b")\n")
    return b"".join(parts)


def fixture_parse(path: Path, output_root: Path, ranks: int) -> None:
    output_root.mkdir(parents=True, exist_ok=False)
    demux_file(path, output_root, "0.050000000000/alpha.water", ranks, ranks)


def run_fixture_checks(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    payloads = [b"FoamFile\n{\n    class volScalarField;\n}\nraw-rank0", b"raw-rank1"]
    valid = wrap_fixture(payloads)
    checks = {}
    with tempfile.TemporaryDirectory(dir=destination) as temp_name:
        temp = Path(temp_name)
        good = temp / "valid.collated"
        good.write_bytes(valid)
        out = temp / "valid-out"
        fixture_parse(good, out, 2)
        first = (out / "processor0/0.050000000000/alpha.water").read_bytes()
        second = (out / "processor1/0.050000000000/alpha.water").read_bytes()
        expected_second = b"FoamFile\n{\n    class volScalarField;\n}\nraw-rank1"
        checks["valid_exact_payloads_and_header"] = first == payloads[0] and second == expected_second

        truncated = temp / "truncated.collated"
        truncated.write_bytes(valid[:-3])
        try:
            fixture_parse(truncated, temp / "truncated-out", 2)
        except FormatError:
            checks["rejects_truncated_payload_or_footer"] = True
        else:
            checks["rejects_truncated_payload_or_footer"] = False

        corrupt = temp / "corrupt.collated"
        corrupt.write_bytes(valid.replace(b"// processor1\n", b"// processor2\n", 1))
        try:
            fixture_parse(corrupt, temp / "corrupt-out", 2)
        except FormatError:
            checks["rejects_noncontiguous_rank_marker"] = True
        else:
            checks["rejects_noncontiguous_rank_marker"] = False
    if not all(checks.values()):
        raise RuntimeError(f"byte-demux fixture checks failed: {checks}")
    return checks


def prepare_case(source_root: Path, case_root: Path, ranks: int, total_ranks: int) -> dict:
    if case_root.exists():
        raise FileExistsError(f"refusing to overwrite {case_root}")
    case_root.mkdir(parents=True)
    (case_root / "system").mkdir()
    control_dict = source_root / "system/controlDict"
    (case_root / "system/controlDict").write_bytes(control_dict.read_bytes())
    (case_root / "rouaix-display.foam").touch()
    files = []
    for relative in FILES:
        record = demux_file(source_root / "processors120" / relative, case_root, relative, ranks, total_ranks)
        files.append(record)
        print(
            f"unpacked {relative}: {record['processed_ranks']} ranks, "
            f"{sum(block['output_bytes'] for block in record['blocks'])} output bytes",
            flush=True,
        )
    if ranks == total_ranks:
        shutil.copytree(source_root / "constant", case_root / "constant")
    return {
        "source_case_root": str(source_root.resolve()),
        "case_root": str(case_root.resolve()),
        "marker": str((case_root / "rouaix-display.foam").resolve()),
        "case_type": "Decomposed Case",
        "root_mesh_source": str((source_root / "constant").resolve()) if ranks == total_ranks else None,
        "ranks_processed": ranks,
        "total_ranks": total_ranks,
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_case", type=Path)
    parser.add_argument("case_root", type=Path)
    parser.add_argument("--ranks", type=int, default=120)
    parser.add_argument("--total-ranks", type=int, default=120)
    parser.add_argument("--fixture-checks", action="store_true")
    args = parser.parse_args()
    if args.fixture_checks:
        fixture_dir = args.case_root.parent / (args.case_root.name + "-fixture-checks")
        checks = run_fixture_checks(fixture_dir)
    else:
        checks = None
    result = prepare_case(args.source_case.resolve(), args.case_root.resolve(), args.ranks, args.total_ranks)
    result["fixture_checks"] = checks
    manifest_path = args.case_root / "demux-manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "case_root": result["case_root"],
        "marker": result["marker"],
        "processed_ranks": result["ranks_processed"],
        "files": len(result["files"]),
        "fixture_checks": checks,
        "manifest": str(manifest_path.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
