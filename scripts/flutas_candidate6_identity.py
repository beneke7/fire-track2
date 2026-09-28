#!/usr/bin/env python3
"""Fail-closed identity check for the exact candidate6 diagnostic image.

This performs CPU-only host/image inspection. It does not create the solver
container, request GPU access, or launch a CFD executable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

RECEIPT_SHA256 = "629e792cf9ebd02d203442b2b943de4aa1176a121f8be303fd86770543c643e0"
IMAGE_ID = "sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b"
OCI_MANIFEST = "sha256:0cbfcc17c72484c004663ee009e320cbb551bf80f534cfdb1a9d3db1297b8972"
BASE_IMAGE_ID = "sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8"
OCI_ARCHIVE_SHA256 = "29272b7453a3ea5a33a97b97f4f21e8cabca53191e4f2e85896cb52a8cbfd49b"
OCI_ARCHIVE_SIZE = 25_230_410_240
OCI_INDEX_SHA256 = "3dba6c336c0e1b6113f8489357660e954d8c4220c421f5001c1be8354328deb4"
EXECUTABLE_SHA256 = "0c3563ed2bbd8a29586d1cdd9f61b8e53087854950e440812492154839b2bb58"
EXECUTABLE_PATH = "/opt/FluTAS/src/flutas.two_phase_inc_isot"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HEX_DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")


def file_sha256(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(descriptor)
        raise ValueError(f"identity input must be a regular, singly linked file: {path}")
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(descriptor, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(descriptor)
        raise ValueError(f"identity JSON must be a regular, singly linked file: {path}")
    with os.fdopen(descriptor, "rb") as stream:
        raw = stream.read()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid identity JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"identity JSON must be an object: {path}")
    return value, raw


def _blob_path(layout: Path, digest: str) -> Path:
    match = HEX_DIGEST.fullmatch(digest)
    if match is None:
        raise ValueError(f"invalid OCI SHA-256 descriptor {digest!r}")
    return layout / "blobs" / "sha256" / match.group(1)


def _verify_blob(layout: Path, digest: str, expected_size: int) -> Path:
    path = _blob_path(layout, digest)
    actual_hash, actual_size = file_sha256(path)
    expected_hash = digest.removeprefix("sha256:")
    if actual_hash != expected_hash or actual_size != expected_size:
        raise ValueError(f"OCI blob digest/size mismatch: {digest}")
    return path


def verify_oci_layout(
    layout: Path,
    receipt: dict[str, Any],
    *,
    expected_index_sha256: str = OCI_INDEX_SHA256,
) -> dict[str, Any]:
    layout_info, _layout_raw = read_json(layout / "oci-layout")
    if layout_info != {"imageLayoutVersion": "1.0.0"}:
        raise ValueError("OCI layout version differs from the supported version")
    index, index_raw = read_json(layout / "index.json")
    if hashlib.sha256(index_raw).hexdigest() != expected_index_sha256:
        raise ValueError("OCI index bytes differ from the retained candidate layout")
    if (
        index.get("schemaVersion") != 2
        or index.get("mediaType") != "application/vnd.oci.image.index.v1+json"
    ):
        raise ValueError("OCI index schema or media type is invalid")
    descriptors = index.get("manifests")
    if not isinstance(descriptors, list) or len(descriptors) != 1:
        raise ValueError("OCI index must select exactly one image manifest")
    manifest_descriptor = descriptors[0]
    image = receipt["image"]
    if (
        manifest_descriptor.get("digest") != image["oci_manifest_digest"]
        or manifest_descriptor.get("mediaType") != "application/vnd.oci.image.manifest.v1+json"
    ):
        raise ValueError("OCI index selects a different candidate manifest")
    manifest_path = _verify_blob(layout, manifest_descriptor["digest"], manifest_descriptor["size"])
    manifest, _manifest_raw = read_json(manifest_path)
    if (
        manifest.get("schemaVersion") != 2
        or manifest.get("mediaType") != "application/vnd.oci.image.manifest.v1+json"
    ):
        raise ValueError("OCI image manifest schema or media type is invalid")
    config_descriptor = manifest.get("config")
    if not isinstance(config_descriptor, dict):
        raise ValueError("OCI image manifest has no config descriptor")
    if config_descriptor.get("digest") != image["config_digest"]:
        raise ValueError("OCI config digest differs from candidate receipt")
    config_path = _verify_blob(layout, config_descriptor["digest"], config_descriptor["size"])
    config, _config_raw = read_json(config_path)
    if config.get("os") != "linux" or config.get("architecture") != "amd64":
        raise ValueError("OCI config platform differs from the reviewed candidate")
    image_config = config.get("config")
    if not isinstance(image_config, dict):
        raise ValueError("OCI image config is missing")
    if image_config.get("Entrypoint") != image["entrypoint_argv"]:
        raise ValueError("OCI entrypoint differs from candidate receipt")
    if (image_config.get("Cmd") or []) != image["cmd_argv"]:
        raise ValueError("OCI command differs from candidate receipt")

    layer_descriptors = manifest.get("layers")
    receipt_layers = image.get("layers")
    if not isinstance(layer_descriptors, list) or not isinstance(receipt_layers, list):
        raise ValueError("OCI layers are missing")
    diff_ids = config.get("rootfs", {}).get("diff_ids")
    if config.get("rootfs", {}).get("type") != "layers" or not isinstance(diff_ids, list):
        raise ValueError("OCI rootfs diff IDs are invalid")
    if len(layer_descriptors) != len(receipt_layers) or len(diff_ids) != len(receipt_layers):
        raise ValueError("OCI layer descriptor, receipt and DiffID counts differ")
    total_layer_bytes = 0
    verified_layers = []
    for index_in_layers, (descriptor, recorded, diff_id) in enumerate(
        zip(layer_descriptors, receipt_layers, diff_ids, strict=True)
    ):
        expected = {
            "media_type": descriptor.get("mediaType"),
            "digest": descriptor.get("digest"),
            "diff_id": diff_id,
            "size": descriptor.get("size"),
        }
        if recorded != expected:
            raise ValueError(f"candidate receipt differs from OCI layer {index_in_layers}")
        if descriptor.get("mediaType") != "application/vnd.oci.image.layer.v1.tar":
            raise ValueError("candidate layers must use the pinned uncompressed OCI tar media type")
        if diff_id != descriptor.get("digest"):
            raise ValueError(f"uncompressed layer DiffID differs at index {index_in_layers}")
        _verify_blob(layout, descriptor["digest"], descriptor["size"])
        total_layer_bytes += descriptor["size"]
        verified_layers.append(descriptor["digest"])
    return {
        "index_sha256": hashlib.sha256(index_raw).hexdigest(),
        "manifest_digest": manifest_descriptor["digest"],
        "config_digest": config_descriptor["digest"],
        "layer_count": len(verified_layers),
        "layer_bytes_verified": total_layer_bytes,
        "ordered_layers": verified_layers,
    }


def verify_oci_archive(
    archive: Path,
    *,
    expected_sha256: str = OCI_ARCHIVE_SHA256,
    expected_size: int = OCI_ARCHIVE_SIZE,
) -> dict[str, Any]:
    actual_hash, actual_size = file_sha256(archive)
    if actual_hash != expected_sha256 or actual_size != expected_size:
        raise ValueError("offline candidate OCI archive digest or byte count differs")
    return {"archive_sha256": actual_hash, "archive_bytes": actual_size}


def verify_local_images(receipt: dict[str, Any], docker: str = "docker") -> dict[str, Any]:
    build = receipt["build"]
    image = receipt["image"]
    result = subprocess.run(
        [docker, "image", "inspect", IMAGE_ID],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Docker cannot inspect pinned candidate image: {result.stderr.strip()}")
    images = json.loads(result.stdout)
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise ValueError("Docker image inspection did not return exactly one candidate")
    local = images[0]
    if local.get("Id") != IMAGE_ID or local.get("Id") != image["docker_image_id"]:
        raise ValueError("Docker image ID differs from candidate receipt")
    if local.get("Os") != "linux" or local.get("Architecture") != "amd64":
        raise ValueError("local Docker image platform differs from candidate receipt")
    config = local.get("Config")
    if not isinstance(config, dict):
        raise ValueError("local Docker image has no config")
    if config.get("Entrypoint") != image["entrypoint_argv"]:
        raise ValueError("local Docker entrypoint differs from candidate receipt")
    if (config.get("Cmd") or []) != image["cmd_argv"]:
        raise ValueError("local Docker command differs from candidate receipt")
    local_diff_ids = local.get("RootFS", {}).get("Layers")
    expected_diff_ids = [layer["diff_id"] for layer in image["layers"]]
    if local_diff_ids != expected_diff_ids:
        raise ValueError("local Docker rootfs DiffIDs differ from candidate receipt")

    base = subprocess.run(
        [docker, "image", "inspect", BASE_IMAGE_ID],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if base.returncode != 0:
        raise RuntimeError(
            f"Docker cannot inspect pinned builder base image: {base.stderr.strip()}"
        )
    base_images = json.loads(base.stdout)
    if (
        not isinstance(base_images, list)
        or len(base_images) != 1
        or base_images[0].get("Id") != build["builder_image_digest"]
    ):
        raise ValueError("local builder base image differs from the pinned H6 receipt")
    return {"candidate_image_id": local["Id"], "builder_image_id": base_images[0]["Id"]}


def verify_receipt_and_build_inputs(
    receipt_path: Path,
    receipt_hash_file: Path,
    repository_root: Path,
    executable: Path,
    source_inventory: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    actual_receipt_hash, _size = file_sha256(receipt_path)
    if actual_receipt_hash != RECEIPT_SHA256:
        raise ValueError(f"candidate receipt SHA-256 mismatch: {actual_receipt_hash}")
    file_sha256(receipt_hash_file)
    if (
        receipt_hash_file.read_text(encoding="ascii").strip()
        != f"{RECEIPT_SHA256}  candidate-build.json"
    ):
        raise ValueError("external candidate receipt hash file differs")
    receipt, _raw = read_json(receipt_path)
    if set(receipt) != {"schema_version", "candidate_id", "source", "patches", "build", "image"}:
        raise ValueError("candidate receipt top-level object differs from H6")
    if receipt["schema_version"] != "track2-candidate-build-v1":
        raise ValueError("candidate receipt schema version differs from H6")
    if receipt["candidate_id"] != "candidate6-20260928T093141Z-4092509":
        raise ValueError("candidate ID differs from reviewed build")
    if receipt["source"].get("commit_oid") != "598210616bebd51f7d51f61455f196e6f3479916":
        raise ValueError("candidate source commit differs from reviewed build")
    if receipt["image"].get("oci_manifest_digest") != OCI_MANIFEST:
        raise ValueError("candidate OCI manifest digest differs from reviewed build")
    if (
        receipt["image"].get("docker_image_id") != IMAGE_ID
        or receipt["image"].get("config_digest") != IMAGE_ID
    ):
        raise ValueError("candidate Docker image ID/config digest differs from reviewed build")
    executable_hash, _size = file_sha256(executable)
    if (
        executable_hash != EXECUTABLE_SHA256
        or receipt["build"].get("executable_sha256") != executable_hash
    ):
        raise ValueError("retained executable bytes differ from candidate receipt")

    checked_inputs: dict[str, str] = {}
    build = receipt["build"]
    paths = {build["build_script_path"]: build["build_script_sha256"]}
    paths.update({item["path"]: item["sha256"] for item in build["inputs"]})
    for relative, expected in paths.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"build input path is not repository relative: {relative}")
        actual, _size = file_sha256(repository_root / relative)
        if actual != expected:
            raise ValueError(f"build input hash mismatch for {relative}")
        checked_inputs[relative] = actual
    if build.get("builder_image_digest") != BASE_IMAGE_ID:
        raise ValueError("pinned builder base image identity differs")

    source_files = receipt["source"].get("files")
    if not isinstance(source_files, list) or len(source_files) != 223:
        raise ValueError("candidate source receipt does not contain the exact 223-file inventory")
    expected_rows = [
        (item["path"], item["git_blob_oid"], item["content_sha256"]) for item in source_files
    ]
    source_inventory_hash, _source_inventory_size = file_sha256(source_inventory)
    actual_rows = [
        tuple(line.split("\t"))
        for line in source_inventory.read_text(encoding="utf-8").splitlines()
    ]
    if actual_rows != expected_rows:
        raise ValueError("upstream source blob inventory differs from candidate receipt")
    return receipt, {
        "candidate_receipt_sha256": actual_receipt_hash,
        "executable_sha256": executable_hash,
        "build_input_sha256": checked_inputs,
        "source_file_count": len(source_files),
        "source_inventory_sha256": source_inventory_hash,
    }


def verify_candidate(
    *,
    candidate_root: Path,
    archive: Path,
    layout: Path,
    repository_root: Path,
    executable: Path,
    docker: str,
) -> dict[str, Any]:
    receipt_path = candidate_root / "candidate-build.json"
    receipt_hash_path = candidate_root / "candidate-build.sha256"
    source_inventory = candidate_root / "source-tree-blobs.tsv"
    receipt, local_evidence = verify_receipt_and_build_inputs(
        receipt_path, receipt_hash_path, repository_root, executable, source_inventory
    )
    archive_evidence = verify_oci_archive(archive)
    oci_evidence = verify_oci_layout(layout, receipt)
    docker_evidence = verify_local_images(receipt, docker)
    if oci_evidence["manifest_digest"] != OCI_MANIFEST or oci_evidence["config_digest"] != IMAGE_ID:
        raise ValueError("verified OCI descriptors differ from the frozen image identities")
    return {
        "schema_version": "candidate6-dry-four-identity-verification-v1",
        "solver_started": False,
        "gpu_requested": False,
        "receipt": local_evidence,
        "oci_archive": archive_evidence,
        "oci_layout": oci_evidence,
        "local_docker_images": docker_evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_candidate(
            candidate_root=args.candidate_root,
            archive=args.archive,
            layout=args.layout,
            repository_root=args.repository_root,
            executable=args.executable,
            docker=args.docker,
        )
        raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(args.output, flags, 0o444)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print(f"candidate identity verified; evidence={args.output}")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"candidate identity rejected: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
