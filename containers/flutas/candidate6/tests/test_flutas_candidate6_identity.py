from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import flutas_candidate6_identity as identity


def _put_blob(layout: Path, payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    path = layout / "blobs" / "sha256" / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"digest": f"sha256:{digest}", "size": len(payload)}


class Candidate6IdentityTests(unittest.TestCase):
    def test_archive_hash_and_size_are_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.tar"
            path.write_bytes(b"pinned archive")
            expected = hashlib.sha256(b"pinned archive").hexdigest()
            self.assertEqual(
                identity.verify_oci_archive(path, expected_sha256=expected, expected_size=14),
                {"archive_sha256": expected, "archive_bytes": 14},
            )
            with self.assertRaisesRegex(ValueError, "archive digest or byte count"):
                identity.verify_oci_archive(path, expected_sha256=expected, expected_size=15)

    def test_oci_layout_binds_index_manifest_config_and_layer_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            layout = Path(temporary) / "layout"
            layout.mkdir()
            (layout / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}\n', encoding="utf-8")
            layer = b"minimal uncompressed OCI layer"
            layer_descriptor = _put_blob(layout, layer)
            config = {
                "architecture": "amd64",
                "os": "linux",
                "config": {"Entrypoint": ["/bin/true"], "Cmd": None},
                "rootfs": {
                    "type": "layers",
                    "diff_ids": [layer_descriptor["digest"]],
                },
            }
            config_raw = json.dumps(config, separators=(",", ":")).encode()
            config_descriptor = _put_blob(layout, config_raw)
            manifest = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    **config_descriptor,
                },
                "layers": [
                    {
                        "mediaType": "application/vnd.oci.image.layer.v1.tar",
                        **layer_descriptor,
                    }
                ],
            }
            manifest_raw = json.dumps(manifest, separators=(",", ":")).encode()
            manifest_descriptor = _put_blob(layout, manifest_raw)
            manifest_descriptor["mediaType"] = "application/vnd.oci.image.manifest.v1+json"
            index = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.index.v1+json",
                "manifests": [manifest_descriptor],
            }
            index_raw = json.dumps(index, separators=(",", ":")).encode()
            (layout / "index.json").write_bytes(index_raw)
            receipt = {
                "image": {
                    "oci_manifest_digest": manifest_descriptor["digest"],
                    "config_digest": config_descriptor["digest"],
                    "entrypoint_argv": ["/bin/true"],
                    "cmd_argv": [],
                    "layers": [
                        {
                            "media_type": "application/vnd.oci.image.layer.v1.tar",
                            "digest": layer_descriptor["digest"],
                            "diff_id": layer_descriptor["digest"],
                            "size": layer_descriptor["size"],
                        }
                    ],
                }
            }

            evidence = identity.verify_oci_layout(
                layout,
                receipt,
                expected_index_sha256=hashlib.sha256(index_raw).hexdigest(),
            )

            self.assertEqual(evidence["layer_count"], 1)
            self.assertEqual(evidence["layer_bytes_verified"], len(layer))

            blob = layout / "blobs" / "sha256" / layer_descriptor["digest"].removeprefix("sha256:")
            blob.write_bytes(b"changed layer")
            with self.assertRaisesRegex(ValueError, "blob digest/size mismatch"):
                identity.verify_oci_layout(
                    layout,
                    receipt,
                    expected_index_sha256=hashlib.sha256(index_raw).hexdigest(),
                )

    def test_identity_json_rejects_duplicate_keys_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                identity.read_json(duplicate)

            target = root / "target.json"
            target.write_text('{"ok":true}', encoding="utf-8")
            alias = root / "alias.json"
            alias.symlink_to(target)
            with self.assertRaises(OSError):
                identity.read_json(alias)


if __name__ == "__main__":
    unittest.main(verbosity=2)
