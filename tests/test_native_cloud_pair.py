from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import postprocess_native_cloud_pair as pair_profiles  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def build_pair_fixture(
    root: Path, *, identical_variant_arrays: bool = False
) -> tuple[Path, dict[str, Path]]:
    runs = root / "results/runs"
    runs.mkdir(parents=True, exist_ok=True)
    comparison: dict[str, object] = {
        "schema": pair_profiles.POSTPROCESS_SCHEMA,
        "status": pair_profiles.UPSTREAM_SUCCESS,
        "time_s": 1.0,
        "paired_input_comparison": {
            "changed_paths": ["0/U", "0/epsilon", "0/k", "case-inputs.json"]
        },
        "runs": {},
        "observer_results": {},
    }
    raw_dirs: dict[str, Path] = {}

    for variant in pair_profiles.VARIANTS:
        run_id = f"fixture-{variant}-run"
        run_dir = runs / run_id
        case_dir = run_dir / "case"
        case_dir.mkdir(parents=True)
        case_inputs = {
            "ranks": pair_profiles.EXPECTED_RANKS,
            "horizon_s": 1.0,
            "mesh_cells_expected": pair_profiles.EXPECTED_CELLS,
            "source_patch_areas_m2": {pair_profiles.SOURCE_PATCH: 1.332},
            "source_patch_face_counts": {pair_profiles.SOURCE_PATCH: 960},
            "source_geometry": {
                "sources": [
                    {
                        "name": pair_profiles.SOURCE_PATCH,
                        "area_m2": 1.332,
                        "bounds_m": {"x": [-2.22, 2.22], "y": [-0.15, 0.15]},
                        "center_x_m": 0.0,
                        "center_y_m": 0.0,
                        "plane_z_m": 0.0,
                    }
                ]
            },
            "source_geometry_assumption": {"evidence_class": "provisional fixture"},
            "source_origin_m": [0.0, 0.0, 0.0],
            "domain_bounds_m": {"x": [-3.0, 23.0], "y": [-10.0, 10.0], "z": [-31.0, 0.0]},
            "coordinate_frame": {
                "source_origin_m": [0.0, 0.0, 0.0],
                "source_plane_z_m": 0.0,
                "paper_plot_transform": {
                    "paper_streamwise_y_m": "mesh_x_m - source_origin_m[0]",
                    "paper_downward_z_m": "source_plane_z_m - mesh_z_m",
                    "paper_cross_track_x_m": "mesh_y_m - source_origin_m[1]",
                },
            },
        }
        case_inputs_path = case_dir / "case-inputs.json"
        _write_json(case_inputs_path, case_inputs)

        field_hashes: dict[str, str] = {}
        for rank in range(pair_profiles.EXPECTED_RANKS):
            time_dir = case_dir / f"processor{rank}" / "1.000000"
            time_dir.mkdir(parents=True)
            for field in pair_profiles.REQUIRED_FIELDS:
                path = time_dir / field
                path.write_bytes(f"{variant}:{rank}:{field}".encode())
                field_hashes[str(path.relative_to(case_dir))] = _sha(path)
        (case_dir / "log.interIsoFoam").write_text(
            "Time = 0.9\nTime = 1.000000\nEnd\n", encoding="utf-8"
        )

        manifest = {
            "run_id": run_id,
            "variant": variant,
            "status": "solver_completed",
            "solver_exit_code": 0,
            "case_input_hashes": {"case-inputs.json": _sha(case_inputs_path)},
            "prepared_case_sha256": {"case-inputs.json": _sha(case_inputs_path)},
        }
        manifest_path = run_dir / "manifest.json"
        _write_json(manifest_path, manifest)

        export_dir = runs / f"fixture-export-{variant}"
        raw_dir = export_dir / "raw"
        rank_raw = raw_dir / "rank-0000"
        rank_raw.mkdir(parents=True)
        array_suffix = "shared" if identical_variant_arrays else variant
        (rank_raw / "alpha_water.f64").write_bytes(f"alpha:{array_suffix}".encode())
        (rank_raw / "velocity_xyz_m_s.f64").write_bytes(f"velocity:{array_suffix}".encode())
        (rank_raw / "cell_global_ids.i64").write_bytes(b"same mesh ids")
        metadata = {
            "rank": 0,
            "rank_count": pair_profiles.EXPECTED_RANKS,
            "time_name": "1.000000",
            "time_value_s": 1.0,
            "source_patch": pair_profiles.SOURCE_PATCH,
        }
        _write_json(rank_raw / "metadata.json", metadata)
        raw_hashes = _tree_hashes(raw_dir)
        raw_manifest_path = runs / f"fixture-native-{variant}" / "raw_export_sha256.json"
        _write_json(raw_manifest_path, raw_hashes)
        native_analysis_path = raw_manifest_path.parent / "analysis.json"
        native_analysis = {
            "time_name": "1.000000",
            "time_value_s": 1.0,
            "source_patch": pair_profiles.SOURCE_PATCH,
            "topology": {
                "native_cells": pair_profiles.EXPECTED_CELLS,
                "rank_count": pair_profiles.EXPECTED_RANKS,
                "source_boundary_face_count": 960,
                "source_patch_area_m2": 1.332,
                "unique_face_edges": 100,
            },
        }
        _write_json(native_analysis_path, native_analysis)
        native_analysis_hash = _sha(native_analysis_path)
        export_meta_path = export_dir / "export_attempt.json"
        _write_json(
            export_meta_path,
            {
                "status": "complete",
                "return_code": 0,
                "input_hashes_unchanged": True,
                "image_id": pair_profiles.PINNED_IMAGE_ID,
                "source_patch": pair_profiles.SOURCE_PATCH,
                "mpi_ranks": pair_profiles.EXPECTED_RANKS,
                "selected_time_requested": "1.0",
                "case_directory": str(case_dir.resolve()),
                "raw_directory": str(raw_dir.resolve()),
            },
        )

        run_record = {
            "run_directory": str(run_dir.resolve()),
            "case_directory": str(case_dir.resolve()),
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": _sha(manifest_path),
            "exact_checkpoint": {
                "requested_time_s": 1.0,
                "selected_time_directory": "1.000000",
                "rank_count": pair_profiles.EXPECTED_RANKS,
                "fields_required_per_rank": list(pair_profiles.REQUIRED_FIELDS),
                "field_sha256": field_hashes,
            },
            "native_field_sha256_after_observers": field_hashes,
            "native_export_metadata_path": str(export_meta_path.resolve()),
            "native_analysis_path": str(native_analysis_path.resolve()),
            "native_export_raw_hash_manifest": str(raw_manifest_path.resolve()),
            "native_topology": {"analysis_sha256": native_analysis_hash},
        }
        observer_record = {
            "status": "complete",
            "native_topology": {"analysis_sha256": native_analysis_hash},
        }
        comparison["runs"][variant] = run_record  # type: ignore[index]
        comparison["observer_results"][variant] = observer_record  # type: ignore[index]
        raw_dirs[variant] = raw_dir

    comparison_path = runs / "upstream-comparison.json"
    _write_json(comparison_path, comparison)
    return comparison_path, raw_dirs


def fake_analyzer_factory(calls: list[tuple[Path, Path, Path]]):
    def fake_analyze(
        export_dir: Path, case_inputs_path: Path, output_dir: Path, station_spacing_m: float
    ) -> dict:
        calls.append((export_dir, case_inputs_path, output_dir))
        output_dir.mkdir(parents=True)
        hashes = _tree_hashes(export_dir)
        _write_json(output_dir / "native_export_hashes.json", hashes)
        report = {
            "snapshot": {"native_cell_count": pair_profiles.EXPECTED_CELLS},
            "normalization": {"source_area_m2": 1.332},
            "provenance": {
                "export_hash_manifest_sha256": _sha(output_dir / "native_export_hashes.json")
            },
        }
        _write_json(output_dir / "analysis.json", report)
        (output_dir / "paper_cloud_comparison.png").write_bytes(b"fixture plot")
        penetration = [
            {
                "station_spacing_m": str(station_spacing_m),
                "alpha_threshold": "0.001",
                "origin_choice": "source_center",
                "paper_streamwise_station_center_m": "0.0",
                "aabb_envelope_downward_front_m": "0.5",
            },
            {
                "station_spacing_m": str(station_spacing_m),
                "alpha_threshold": "0.001",
                "origin_choice": "source_center",
                "paper_streamwise_station_center_m": "0.075",
                "aabb_envelope_downward_front_m": "",
            },
        ]
        width = [
            {
                "station_spacing_m": str(station_spacing_m),
                "alpha_threshold": "0.001",
                "conditional_depth_over_Lc": "0.1",
                "conditional_width_over_Lc": "0.2",
            },
            {
                "station_spacing_m": str(station_spacing_m),
                "alpha_threshold": "0.001",
                "conditional_depth_over_Lc": "0.2",
                "conditional_width_over_Lc": "",
            },
            {
                "station_spacing_m": str(station_spacing_m),
                "alpha_threshold": "0.9",
                "conditional_depth_over_Lc": "0.1",
                "conditional_width_over_Lc": "0.15",
            },
        ]
        for filename, rows in (
            ("penetration_profiles.csv", penetration),
            ("width_profiles.csv", width),
        ):
            with (output_dir / filename).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        return report

    return fake_analyze


class NativeCloudPairIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "results/runs").mkdir(parents=True)
        self.comparison_path, self.raw_dirs = build_pair_fixture(self.root)
        self.output_dir = self.root / "results/runs/pair-profiles"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _mutate_comparison(self, callback) -> None:
        comparison = json.loads(self.comparison_path.read_text())
        callback(comparison)
        _write_json(self.comparison_path, comparison)

    def test_success_routes_two_distinct_variants_and_preserves_inputs(self) -> None:
        case_hashes_before = {
            role: _tree_hashes(
                Path(json.loads(self.comparison_path.read_text())["runs"][role]["case_directory"])
            )
            for role in pair_profiles.VARIANTS
        }
        calls: list[tuple[Path, Path, Path]] = []
        report = pair_profiles.postprocess_pair(
            self.comparison_path,
            self.output_dir,
            repo_root=self.root,
            analyzer=fake_analyzer_factory(calls),
        )
        self.assertEqual(report["status"], "complete")
        self.assertEqual({call[0] for call in calls}, set(self.raw_dirs.values()))
        self.assertEqual(len({call[2] for call in calls}), 2)
        self.assertEqual(
            {record["run_id"] for record in report["runs"].values()},
            {
                "fixture-uniform-run",
                "fixture-three-component-run",
            },
        )
        self.assertTrue(report["native_mesh_hashes_equal_except_alpha_U"])
        self.assertTrue(report["runs"]["uniform"]["source_field_hashes_match_upstream"])
        self.assertTrue((self.output_dir / "matched_pair_profile_comparison.png").is_file())
        self.assertTrue((self.output_dir / "combined_penetration_profiles.csv").is_file())
        self.assertTrue((self.output_dir / "combined_width_profiles.csv").is_file())
        case_hashes_after = {
            role: _tree_hashes(
                Path(json.loads(self.comparison_path.read_text())["runs"][role]["case_directory"])
            )
            for role in pair_profiles.VARIANTS
        }
        self.assertEqual(case_hashes_before, case_hashes_after)

    def test_identical_alpha_velocity_arrays_are_valid_null_outcome(self) -> None:
        null_root = self.root / "identical-export-fixture"
        null_root.mkdir()
        comparison_path, raw_dirs = build_pair_fixture(null_root, identical_variant_arrays=True)
        report = pair_profiles.postprocess_pair(
            comparison_path,
            null_root / "results/runs/pair-profiles",
            repo_root=null_root,
            analyzer=fake_analyzer_factory([]),
        )
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["variant_specific_export_arrays"], [])
        self.assertTrue(report["variant_export_arrays_identical"])
        self.assertFalse(report["observed_export_difference"])
        self.assertTrue(
            (null_root / "results/runs/pair-profiles/matched_pair_profile_comparison.png").is_file()
        )
        self.assertEqual(
            _sha(raw_dirs["uniform"] / "rank-0000/alpha_water.f64"),
            _sha(raw_dirs["three-component"] / "rank-0000/alpha_water.f64"),
        )

    def test_duplicate_variant_run_id_is_rejected(self) -> None:
        self._mutate_comparison(
            lambda comparison: comparison["runs"]["three-component"].update(
                {"run_directory": comparison["runs"]["uniform"]["run_directory"]}
            )
        )
        with self.assertRaisesRegex(ValueError, "case path is not the run bundle"):
            pair_profiles.validate_upstream_comparison(self.comparison_path, self.root)
        self.assertFalse(self.output_dir.exists())

    def test_missing_or_wrong_saved_time_is_rejected_before_output(self) -> None:
        self._mutate_comparison(
            lambda comparison: comparison["runs"]["uniform"]["exact_checkpoint"].update(
                {"selected_time_directory": "0.500000"}
            )
        )
        with self.assertRaisesRegex(ValueError, "saved directory is 0.5 s"):
            pair_profiles.postprocess_pair(
                self.comparison_path, self.output_dir, repo_root=self.root
            )
        self.assertFalse(self.output_dir.exists())

    def test_missing_saved_native_field_is_rejected(self) -> None:
        record = json.loads(self.comparison_path.read_text())["runs"]["uniform"]
        case_dir = Path(record["case_directory"])
        (case_dir / "processor3/1.000000/phi").unlink()
        with self.assertRaisesRegex(ValueError, "missing or escaping saved field"):
            pair_profiles.validate_upstream_comparison(self.comparison_path, self.root)
        self.assertFalse(self.output_dir.exists())

    def test_failed_upstream_comparison_is_rejected_without_output(self) -> None:
        self._mutate_comparison(
            lambda comparison: comparison.update(
                {"status": "postprocessing_failed_solver_results_preserved"}
            )
        )
        with self.assertRaisesRegex(ValueError, "did not complete"):
            pair_profiles.postprocess_pair(
                self.comparison_path, self.output_dir, repo_root=self.root
            )
        self.assertFalse(self.output_dir.exists())

    def test_changed_native_export_hash_is_rejected_and_failure_preserved(self) -> None:
        calls: list[tuple[Path, Path, Path]] = []
        raw_alpha = self.raw_dirs["uniform"] / "rank-0000/alpha_water.f64"
        raw_alpha.write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "differ from the upstream sealed hash manifest"):
            pair_profiles.postprocess_pair(
                self.comparison_path,
                self.output_dir,
                repo_root=self.root,
                analyzer=fake_analyzer_factory(calls),
            )
        failed = json.loads((self.output_dir / "pair_summary.json").read_text())
        self.assertEqual(
            failed["status"], "native_cloud_pair_postprocess_failed_solver_cases_preserved"
        )

    def test_existing_output_directory_is_never_overwritten(self) -> None:
        self.output_dir.mkdir()
        sentinel = self.output_dir / "keep.txt"
        sentinel.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            pair_profiles.postprocess_pair(
                self.comparison_path, self.output_dir, repo_root=self.root
            )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "original")

    def test_wait_processes_native_success_without_render_success(self) -> None:
        observer = self.root / "results/runs/upstream-observer.json"
        _write_json(
            observer,
            {"status": "native_render_failed_solver_results_preserved_no_cfd_retry"},
        )
        wait_state = self.root / "results/runs/pair-wait.json"
        report = pair_profiles.wait_and_process(
            self.comparison_path,
            self.output_dir,
            observer_report=observer,
            wait_state_path=wait_state,
            repo_root=self.root,
            wait_timeout_s=1.0,
            poll_seconds=0.01,
            analyzer=fake_analyzer_factory([]),
        )
        self.assertEqual(report["status"], "complete")
        self.assertEqual(json.loads(wait_state.read_text())["status"], "complete")


if __name__ == "__main__":
    unittest.main()
