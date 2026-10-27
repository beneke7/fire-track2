#!/usr/bin/env python3
"""Focused safety checks for the public reversible mesh restore helper."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[3]
HELPER_PATH = PACKET / "restore_polymesh.py"
MANIFEST_PATH = PACKET / "restore-manifest.json"
JOURNAL_PATH = PACKET / "dedup-journal.jsonl"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("restore_polymesh_public", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load public restore helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_fixture(
    row: dict[str, Any], journal_event: dict[str, Any]
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, dict[str, Any]]:
    temp = tempfile.TemporaryDirectory(prefix="i4f-restore-safety-")
    root = Path(temp.name)
    canonical = root / row["canonical_path"]
    canonical.parent.mkdir(parents=True)
    real_canonical = REPO / row["canonical_path"]
    shutil.copyfile(real_canonical, canonical)
    os.chmod(canonical, row["canonical_mode"])
    source_stat = canonical.stat()
    os.utime(canonical, ns=(source_stat.st_atime_ns, row["canonical_mtime_ns"]))
    source_stat = canonical.stat()

    event_relative = Path(JOURNAL_PATH.relative_to(REPO))
    journal = root / event_relative
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps(journal_event, sort_keys=True) + "\n")

    row_fixture = dict(row)
    row_fixture.update(
        canonical_mode=stat.S_IMODE(source_stat.st_mode),
        canonical_uid=source_stat.st_uid,
        canonical_gid=source_stat.st_gid,
        canonical_mtime_ns=source_stat.st_mtime_ns,
        # Deliberately different from the current fixture filesystem device.
        device=source_stat.st_dev + 777,
        uid=os.getuid(),
        gid=os.getgid(),
        mode=stat.S_IMODE(row["mode"]),
        atime_ns=1_700_000_000_123_456_789,
        mtime_ns=1_700_000_100_987_654_321,
    )
    manifest = {
        "schema": "i4f-reversible-duplicate-polymesh-manifest/v1",
        "journal_path": str(event_relative),
        "records": [row_fixture],
    }
    fixture_manifest = root / Path(MANIFEST_PATH.relative_to(REPO))
    fixture_manifest.parent.mkdir(parents=True, exist_ok=True)
    fixture_manifest.write_text(json.dumps(manifest, sort_keys=True))
    return temp, root, canonical, row_fixture


def expect_raises(exception: type[BaseException], callback: Any, message: str) -> str:
    try:
        callback()
    except exception as exc:
        return f"{type(exc).__name__}: {exc}"
    raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        help="write the report to a new path (refuses to overwrite an existing path)",
    )
    args = parser.parse_args()

    helper = load_helper()
    manifest = json.loads(MANIFEST_PATH.read_text())
    rows = sorted(manifest["records"], key=lambda item: item["bytes"])
    row = rows[0]
    matching_event = next(
        json.loads(line)
        for line in JOURNAL_PATH.read_text().splitlines()
        if json.loads(line).get("duplicate_path") == row["duplicate_path"]
    )
    source = REPO / row["canonical_path"]
    original_stat_before = source.stat()
    source_digest = digest(source)
    if source_digest != row["sha256"] or source.stat().st_size != row["bytes"]:
        raise AssertionError("selected retained canonical does not match public manifest")

    results: dict[str, Any] = {}

    temp, root, canonical, row_fixture = make_fixture(row, matching_event)
    try:
        with canonical.open("r+b") as stream:
            byte = stream.read(1)
            stream.seek(0)
            stream.write(bytes([byte[0] ^ 0x01]))
            stream.flush()
            os.fsync(stream.fileno())
        # Restore only the fixture mtime so the rejection specifically checks
        # content SHA while preserving the changed fixture's exact pre-call state.
        st = canonical.stat()
        os.utime(canonical, ns=(st.st_atime_ns, row_fixture["canonical_mtime_ns"]))
        before_bytes = canonical.read_bytes()
        before_mtime = canonical.stat().st_mtime_ns
        refusal = expect_raises(
            RuntimeError,
            lambda: helper.restore(
                root / Path(MANIFEST_PATH.relative_to(REPO)), root, row_fixture["duplicate_path"]
            ),
            "changed canonical source was unexpectedly accepted",
        )
        after_bytes = canonical.read_bytes()
        after_mtime = canonical.stat().st_mtime_ns
        if after_bytes != before_bytes or after_mtime != before_mtime:
            raise AssertionError("rejected restore modified changed canonical bytes or mtime")
        results["changed_canonical_rejected_without_mutation"] = {
            "outcome": refusal,
            "bytes_unchanged": after_bytes == before_bytes,
            "mtime_unchanged": after_mtime == before_mtime,
        }
    finally:
        temp.cleanup()

    temp, root, canonical, row_fixture = make_fixture(row, matching_event)
    try:
        canonical.unlink()
        outside = root / "outside-source"
        outside.write_bytes(source.read_bytes())
        canonical.symlink_to(outside)
        refusal = expect_raises(
            ValueError,
            lambda: helper.restore(
                root / Path(MANIFEST_PATH.relative_to(REPO)), root, row_fixture["duplicate_path"]
            ),
            "canonical symlink was unexpectedly accepted",
        )
        target = root / row_fixture["duplicate_path"]
        if not canonical.is_symlink() or target.exists() or target.is_symlink():
            raise AssertionError("symlink refusal changed the fixture or created a target")
        results["canonical_symlink_refused"] = {
            "outcome": refusal,
            "symlink_preserved": canonical.is_symlink(),
            "target_absent": not target.exists() and not target.is_symlink(),
        }
    finally:
        temp.cleanup()

    temp, root, canonical, row_fixture = make_fixture(row, matching_event)
    try:
        target = root / row_fixture["duplicate_path"]
        restored = helper.restore(
            root / Path(MANIFEST_PATH.relative_to(REPO)), root, row_fixture["duplicate_path"]
        )
        final = target.stat()
        if digest(target) != row_fixture["sha256"]:
            raise AssertionError("restored target digest differs")
        if final.st_size != row_fixture["bytes"] or final.st_mtime_ns != row_fixture["mtime_ns"]:
            raise AssertionError("restored target size/mtime differs")
        refusal = expect_raises(
            FileExistsError,
            lambda: helper.restore(
                root / Path(MANIFEST_PATH.relative_to(REPO)), root, row_fixture["duplicate_path"]
            ),
            "existing restore target was unexpectedly overwritten",
        )
        if digest(target) != row_fixture["sha256"]:
            raise AssertionError("overwrite refusal changed the existing target")
        results["valid_restore_and_overwrite_refusal"] = {
            "restore": restored,
            "overwrite_refusal": refusal,
            "target_digest": digest(target),
            "target_size": final.st_size,
            "target_mtime_ns": final.st_mtime_ns,
            "historical_device_mismatch_accepted": True,
        }
    finally:
        temp.cleanup()

    temp, root, canonical, row_fixture = make_fixture(row, matching_event)
    try:
        duplicate = Path(row_fixture["duplicate_path"])
        parent = root / duplicate.parent
        parent.parent.mkdir(parents=True, exist_ok=True)
        outside_dir = root / "outside-dir"
        outside_dir.mkdir()
        parent.symlink_to(outside_dir, target_is_directory=True)
        refusal = expect_raises(
            ValueError,
            lambda: helper.restore(
                root / Path(MANIFEST_PATH.relative_to(REPO)), root, row_fixture["duplicate_path"]
            ),
            "target parent symlink was unexpectedly accepted",
        )
        if list(outside_dir.iterdir()):
            raise AssertionError("target parent symlink refusal created a file outside root")
        results["target_parent_symlink_refused"] = {
            "outcome": refusal,
            "outside_directory_empty": True,
        }
    finally:
        temp.cleanup()

    original_stat_after = source.stat()
    original_checks = {
        "sha256_unchanged": digest(source) == source_digest,
        "size_unchanged": original_stat_after.st_size == original_stat_before.st_size,
        "mode_unchanged": stat.S_IMODE(original_stat_after.st_mode)
        == stat.S_IMODE(original_stat_before.st_mode),
        "uid_gid_unchanged": (original_stat_after.st_uid, original_stat_after.st_gid)
        == (original_stat_before.st_uid, original_stat_before.st_gid),
        "mtime_unchanged": original_stat_after.st_mtime_ns == original_stat_before.st_mtime_ns,
        "atime_note": "read-only source hashing may update OS-managed atime; it is not restored",
    }
    if not all(value for key, value in original_checks.items() if key != "atime_note"):
        raise AssertionError(
            f"actual canonical source changed during fixture tests: {original_checks}"
        )

    report = {
        "schema": "i4f-polymesh-restore-safety-test-report/v1",
        "status": "passed",
        "command": ".venv/bin/python results/archives/manifests/i4f-polymesh-dedup-20261027T2330Z/test_restore_polymesh_safety.py",
        "fixture_source": {
            "canonical_path": row["canonical_path"],
            "duplicate_path": row["duplicate_path"],
            "sha256": source_digest,
            "bytes": row["bytes"],
            "all_restore_attempts_used_temporary_roots": True,
        },
        "cases": results,
        "actual_canonical_read_only_check": original_checks,
        "helper_sha256": digest(HELPER_PATH),
        "manifest_sha256": digest(MANIFEST_PATH),
        "journal_sha256": digest(JOURNAL_PATH),
    }
    report_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        report_path = args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write(report_text)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
