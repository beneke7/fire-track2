from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.prepare_i4f_dcec_source import (
    prepare_source_tree,
    safe_relative_path,
)


def test_preparer_reconstructs_exact_68_file_dcec_tree(tmp_path: Path) -> None:
    output = tmp_path / "dcec-source"

    result = prepare_source_tree(output)

    assert result["status"] == "source_tree_prepared_and_hash_verified"
    assert result["file_count"] == 68
    assert result["override_count"] == 2
    assert len([path for path in output.rglob("*") if path.is_file()]) == 68
    assert (
        hashlib.sha256(
            (
                output
                / "applications/solvers/multiphase/compressibleInterFoam/compressibleInterFoam.C"
            ).read_bytes()
        ).hexdigest()
        == "6be187ca00dbf8be0ce2974c203195bbc424483c54afc982d324209a01067165"
    )
    assert (
        hashlib.sha256(
            (output / "applications/solvers/multiphase/compressibleInterFoam/pEqn.H").read_bytes()
        ).hexdigest()
        == "49662f9f9033a4b87fca41a11e1ffcc9f06a0b355a0462d01bc45bf6d19af6b6"
    )


def test_preparer_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(FileExistsError):
        prepare_source_tree(output)

    assert sentinel.read_text(encoding="utf-8") == "do not overwrite"


@pytest.mark.parametrize("value", ["../escape", "/absolute", "a\\b", "a/../b"])
def test_preparer_rejects_unsafe_manifest_paths(value: str) -> None:
    with pytest.raises(ValueError):
        safe_relative_path(value)
