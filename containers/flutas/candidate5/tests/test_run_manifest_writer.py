#!/usr/bin/env python3
"""CPU-only producer tests for candidate5 manifest identity and path defects."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import write_run_manifest as writer

CASE_ROOT = Path(__file__).resolve().parents[1] / "cases" / "source_boundary" / "quiescent_one"
SCHEMA_PATH = Path(os.environ["CANDIDATE5_SCHEMA_PATH"]) if os.environ.get("CANDIDATE5_SCHEMA_PATH") else None


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def runtime_inputs() -> dict[str, object]:
    result: dict[str, object] = {
        "time_scheme": "ab2", "time_start_s": "0", "real_kind": 8, "precision_digits": 15,
        "machine_epsilon": "2.2204460492503131E-016", "small_s_inv": "1.0000000000000000E-008",
        "cfl_c": "1", "cfl_d": "0.16666666666666666", "rho1_kg_m3": "1000",
        "rho2_kg_m3": "1", "mu1_pa_s": "0.001", "mu2_pa_s": "0.000018",
        "dx_m": "0.025", "dy_m": "0.025", "dz_m": "0.025", "dxi_m_inv": "40",
        "dyi_m_inv": "40", "dzi_m_inv": "40", "dzc_m": ["0.025"] * 42,
        "dzf_m": ["0.025"] * 42, "dzci_m_inv": ["40"] * 42,
        "dzfi_m_inv": ["40"] * 42, "sigma_n_m": "0", "gravity_m_s2": ["0", "0", "0"],
        "fixed_step_factor": "0.2", "fixed_step_s": "0.0001",
    }
    return result


def build_receipt() -> dict[str, object]:
    digest = "a" * 64
    return {
        "source_commit": "598210616bebd51f7d51f61455f196e6f3479916",
        "source_sha256": {"src/chkdt.f90": digest},
        "source_patch_sha256": digest, "build_script_sha256": digest,
        "image_digest": "sha256:" + "b" * 64, "compiler": "nvfortran",
        "compiler_version": "26.9", "compiler_flags": ["-acc", "-gpu=cc120,cuda13.3"],
        "build_command": "make -j2 ARCH=generic-gpu APP=two_phase_inc_isot",
        "executable_sha256": digest,
    }


def resource_samples() -> dict[str, object]:
    return {
        "ram_samples": [{"elapsed_s": "0", "rss_bytes": "4096"}],
        "vram_samples": [{"elapsed_s": "0", "used_bytes": "0"}],
        "step_timing_samples": [{"step": 1, "elapsed_s": "0.01"}],
    }


class ManifestWriterTests(unittest.TestCase):
    def test_case_paths_reject_symlinks_and_extra_files(self):
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp) / "case"
            shutil.copytree(CASE_ROOT, case)
            (case / "extra.in").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "case input set"):
                writer._case_inputs(case)
            (case / "extra.in").unlink()
            (case / "dns-link.in").symlink_to(case / "dns.in")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                writer._case_inputs(case)

    def test_invalid_runtime_schema_and_mutable_image_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad_inputs = runtime_inputs()
            bad_inputs.pop("cfl_c", None)
            path = root / "inputs.json"
            write_json(path, bad_inputs)
            with self.assertRaisesRegex(ValueError, "runtime timestep-input keys"):
                writer._runtime_inputs(path)
            receipt = build_receipt()
            receipt["image_digest"] = "track2/flutas:latest"
            receipt_path = root / "candidate-build.json"
            write_json(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "immutable OCI image digest"):
                writer._candidate_receipt(receipt_path)

    def test_stop_tuple_and_resource_samples_are_checked(self):
        normal = {
            "solver_exit_code": 0, "stop_reason": "normal_completion", "completed_interval_count": 14,
            "stop_state_index": "not_applicable", "stop_interval_index": "not_applicable",
            "stop_stage_id": "not_applicable", "resources": resource_samples(),
        }
        stop, status = writer._stop_fields(normal, 14)
        self.assertEqual(status, "completed")
        self.assertEqual(stop["stop_state_index"], "not_applicable")
        invalid = dict(normal, stop_state_index=14)
        with self.assertRaisesRegex(ValueError, "normal completion"):
            writer._stop_fields(invalid, 14)
        invalid = dict(normal, solver_exit_code=1)
        with self.assertRaisesRegex(ValueError, "exit code"):
            writer._stop_fields(invalid, 14)

    @unittest.skipIf(SCHEMA_PATH is None, "full manifest fixture needs the mounted frozen schema")
    def test_full_manifest_is_canonical_and_binds_actual_files(self):
        assert SCHEMA_PATH is not None
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "run"
            run_dir.mkdir()
            for name, header in writer.FILES.items():
                (run_dir / name).write_text(",".join(header) + "\n", encoding="utf-8")
            inputs = root / "runtime-inputs.json"
            write_json(inputs, runtime_inputs())
            receipt = root / "candidate-build.json"
            write_json(receipt, build_receipt())
            analyzer = root / "analyzer.py"
            analyzer.write_text("# reviewed fixture analyzer\n", encoding="utf-8")
            metadata = root / "run-metadata.json"
            write_json(metadata, {
                "solver_exit_code": 0, "stop_reason": "normal_completion",
                "completed_interval_count": 14, "stop_state_index": "not_applicable",
                "stop_interval_index": "not_applicable", "stop_stage_id": "not_applicable",
                "resources": resource_samples(),
            })
            from argparse import Namespace
            args = Namespace(
                schema=SCHEMA_PATH,
                case_root=CASE_ROOT,
                run_dir=run_dir,
                timestep_inputs=inputs,
                candidate_build=receipt,
                analyzer=analyzer,
                run_metadata=metadata,
            )
            manifest = writer.make_manifest(args)
            self.assertEqual(manifest["producer_schema"], "candidate5-observability-v1.2")
            self.assertEqual(manifest["image_digest"], build_receipt()["image_digest"])
            self.assertEqual(manifest["final_time_s"], "0.0014")
            self.assertEqual(manifest["row_counts"], {name: 0 for name in writer.FILES})
            self.assertEqual(manifest["candidate_sha256"], writer.sha256(receipt))
            self.assertEqual(manifest["files_sha256"], {name: writer.sha256(run_dir / name)
                                                         for name in writer.FILES})
            canonical = json.dumps(manifest, ensure_ascii=False, allow_nan=False,
                                   sort_keys=True, separators=(",", ":")) + "\n"
            output = root / "manifest.json"
            output.write_text(canonical, encoding="utf-8")
            self.assertFalse(output.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertTrue(output.read_bytes().endswith(b"\n"))
            self.assertNotIn(b": ", output.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
