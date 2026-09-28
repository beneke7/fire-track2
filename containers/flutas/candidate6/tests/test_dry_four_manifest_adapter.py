from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "containers/flutas/candidate6/tools"))
import write_dry_four_manifest as adapter  # noqa: E402


def receipt() -> dict[str, object]:
    return {
        "schema_version": "track2-candidate-build-v1",
        "candidate_id": "candidate6-20260928T093141Z-4092509",
        "source": {"commit_oid": adapter.SOURCE_COMMIT},
        "patches": [
            {
                "path": "containers/flutas/candidate6/source-boundary.patch",
                "sha256": adapter.SOURCE_PATCH_SHA256,
            }
        ],
        "build": {"executable_sha256": adapter.EXECUTABLE_SHA256},
        "image": {
            "platform": {"os": "linux", "architecture": "amd64"},
            "oci_manifest_digest": adapter.OCI_MANIFEST_DIGEST,
            "docker_image_id": "sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b",
            "config_digest": "sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b",
            "entrypoint_argv": ["/bin/true"],
            "cmd_argv": [],
            "layers": [],
        },
    }


class DryFourManifestAdapterTests(unittest.TestCase):
    def test_normal_supervisor_completion_yields_adapter_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            supervisor = root / "supervisor"
            supervisor.mkdir()
            (supervisor / "summary.json").write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "disposition": "termination_verified",
                        "stop_trigger": None,
                        "signal_sequence": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            events = [
                {
                    "kind": "sample",
                    "phase": "before_create",
                    "sample_monotonic_s": 1.0,
                    "process_rss_bytes": 1000,
                    "gpu_memory_used_bytes": 16 * 1024**2,
                    "gpu_device_index": "0",
                },
                {
                    "kind": "sample",
                    "phase": "running",
                    "container_running": True,
                    "sample_monotonic_s": 1.1,
                    "process_rss_bytes": 2000,
                    "gpu_memory_used_bytes": 128 * 1024**2,
                    "gpu_utilization_percent": 5,
                    "gpu_device_index": "0",
                },
                {"kind": "solver_exit", "exit_code": 0},
                {
                    "kind": "attached_logs",
                    "returncode": 0,
                    "log_driver": "none",
                    "combined_bytes": 100,
                },
                {
                    "kind": "termination_verification",
                    "phase": "normal_completion",
                    "verified": True,
                    "docker_state_running": False,
                    "surviving_docker_client_or_solver_children": False,
                },
                {
                    "kind": "termination_verification",
                    "phase": "post_cleanup_verification",
                    "verified": True,
                    "docker_state_running": False,
                    "surviving_docker_client_or_solver_children": False,
                },
                {"kind": "result", "exit_code": 0, "disposition": "normal_termination_verified"},
            ]
            (supervisor / "supervision.jsonl").write_text(
                "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
                encoding="utf-8",
            )
            stdout = root / "stdout.log"
            stdout.write_bytes(b"*** Fim ***\n")
            performance = root / "performance.out"
            performance.write_text(
                "".join(
                    "".join(f"{value:15.7E}" for value in (step, step / 10000, 0, 0, 0.0001)) + "\n"
                    for step in range(1, 15)
                ),
                encoding="ascii",
            )

            metadata = adapter.derive_run_metadata(
                supervisor_dir=supervisor,
                stdout_path=stdout,
                performance_path=performance,
            )

            self.assertEqual(metadata["solver_exit_code"], 0)
            self.assertEqual(metadata["completed_interval_count"], 14)
            self.assertEqual(len(metadata["resources"]["step_timing_samples"]), 14)

    def test_exact_nested_receipt_binds_original_bytes_and_oci_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate-build.json"
            raw = (json.dumps(receipt(), sort_keys=True, separators=(",", ":")) + "\n").encode()
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(
                adapter.candidate_identity(path, expected_sha256=digest),
                (digest, adapter.OCI_MANIFEST_DIGEST),
            )

            altered = receipt()
            image = altered["image"]
            assert isinstance(image, dict)
            image["oci_manifest_digest"] = "sha256:" + "f" * 64
            path.write_text(json.dumps(altered) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OCI manifest digest"):
                adapter.candidate_identity(path, expected_sha256=adapter.sha256(path))

            altered = receipt()
            altered["unexpected"] = True
            path.write_text(json.dumps(altered) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nested H6 schema"):
                adapter.candidate_identity(path, expected_sha256=adapter.sha256(path))

    def test_round_trip_final_clock_matches_binary64_order_for_every_prefix(self) -> None:
        start = adapter.frozen.decimal_string("0", "start")
        dt = adapter.frozen.decimal_string("1.0000000000000000E-004", "dt")
        for completed in range(15):
            actual = float(adapter.final_time_string(start, dt, completed))
            expected = float(start) + completed * float(dt)
            self.assertEqual(actual, expected, f"completed prefix K={completed}")

        for completed in (3, 6, 9, 12, 13):
            decimal_arithmetic = float(start + completed * dt)
            expected = float(start) + completed * float(dt)
            self.assertNotEqual(decimal_arithmetic, expected, f"K={completed} must expose drift")


if __name__ == "__main__":
    unittest.main(verbosity=2)
