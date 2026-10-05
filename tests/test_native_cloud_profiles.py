from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_native_cloud_profiles import (  # noqa: E402
    CloudFrame,
    _analyzer_source_identity,
    _native_contiguous_groups,
    _paper_series,
    _plot_fig9_independent,
    _validate_native_domain,
    extract_profiles,
    frame_from_case_inputs,
    sha256_file,
)


def toy_snapshot() -> dict:
    # Volumes deliberately differ from AABB products to catch geometric-volume
    # substitution. Cell x and z bounds leave one completely empty slab.
    return {
        "time_name": "1.000000",
        "time_value_s": 1.0,
        "source_patch": "dash8Opening",
        "cell_volumes_m3": np.asarray([0.1, 0.2, 0.3]),
        "alpha_water": np.asarray([0.001, 0.9, 0.5]),
        "cell_centres_xyz_m": np.asarray(
            [[0.5, 0.0, -0.5], [1.5, 0.3, -2.5], [3.5, 1.25, -2.5]],
            dtype=float,
        ),
        "cell_bounds_minmax_xyz_m": np.asarray(
            [
                [0.0, -0.4, -1.0, 1.0, 0.4, 0.0],
                [1.0, 0.1, -3.0, 2.0, 0.5, -2.0],
                [3.0, 0.5, -3.0, 4.0, 2.0, -2.0],
            ],
            dtype=float,
        ),
        "topology": {"source_patch_area_m2": 0.25},
    }


def toy_frame() -> CloudFrame:
    return CloudFrame(
        source_origin_xyz_m=(1.0, 0.3, 0.0),
        source_plane_z_m=0.0,
        streamwise_source_bounds_m=(0.5, 1.5),
        source_area_m2=0.25,
        l_characteristic_m=0.5,
        domain_bounds_m={"x": (0.0, 4.0), "y": (-1.0, 2.0), "z": (-3.0, 0.0)},
        source_patch="dash8Opening",
        source_area_evidence="synthetic assumed test area",
        paper_transform={
            "paper_streamwise_y_m": "mesh_x_m - source_origin_m[0]",
            "paper_downward_z_m": "source_plane_z_m - mesh_z_m",
            "paper_cross_track_x_m": "mesh_y_m - source_origin_m[1]",
        },
    )


class NativeCloudProfileTests(unittest.TestCase):
    def test_analyzer_provenance_keeps_loaded_hash_after_source_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "analyzer.py"
            source_path.write_bytes(b"loaded source version\n")
            loaded_hash = sha256_file(source_path)
            source_path.write_bytes(b"later on-disk version\n")

            identity = _analyzer_source_identity(source_path, loaded_hash)

        self.assertEqual(identity["analyzer_loaded_source_sha256"], loaded_hash)
        self.assertNotEqual(identity["analyzer_on_disk_source_sha256"], loaded_hash)
        self.assertFalse(identity["analyzer_source_unchanged_since_import"])

    def setUp(self) -> None:
        self.snapshot = toy_snapshot()
        self.frame = toy_frame()
        self.result = extract_profiles(self.snapshot, self.frame, 1.0)

    def _row(self, rows: list[dict], **criteria) -> dict:
        matches = [row for row in rows if all(row[key] == value for key, value in criteria.items())]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_native_water_volume_uses_fv_volume_not_aabb_product(self) -> None:
        cloud = self.result["threshold_summary"]["0.001"]
        self.assertAlmostEqual(cloud["selected_native_water_volume_m3"], 0.3301, places=14)
        self.assertAlmostEqual(cloud["selected_native_water_mass_kg"], 330.1, places=10)
        self.assertAlmostEqual(
            self.result["all_cell_water_volume_m3"],
            np.sum(self.snapshot["alpha_water"] * self.snapshot["cell_volumes_m3"]),
            places=14,
        )
        self.assertNotAlmostEqual(
            cloud["selected_native_water_volume_m3"],
            0.001 * 0.8 + 0.9 * 0.4 + 0.5 * 1.5,
        )

    def test_threshold_includes_equality_and_core_is_separate(self) -> None:
        self.assertEqual(self.result["threshold_summary"]["0.001"]["selected_cell_count"], 3)
        self.assertEqual(self.result["threshold_summary"]["0.9"]["selected_cell_count"], 1)
        self.assertAlmostEqual(
            self.result["threshold_summary"]["0.9"]["selected_native_water_volume_m3"], 0.18
        )

    def test_streamwise_empty_slabs_are_preserved_and_envelope_uses_bounds(self) -> None:
        gap = self._row(
            self.result["penetration_rows"],
            alpha_threshold=0.001,
            station_spacing_m=1.0,
            origin_choice="source_center",
            paper_streamwise_slab_low_m=1.0,
            paper_streamwise_slab_high_m=2.0,
        )
        self.assertEqual(gap["aabb_overlap_cell_count"], 0)
        self.assertEqual(gap["center_assigned_cell_count"], 0)
        self.assertIsNone(gap["aabb_envelope_downward_front_m"])
        self.assertEqual(gap["center_assigned_native_water_volume_m3"], 0.0)
        last = self._row(
            self.result["penetration_rows"],
            alpha_threshold=0.001,
            station_spacing_m=1.0,
            origin_choice="source_center",
            paper_streamwise_slab_low_m=2.0,
            paper_streamwise_slab_high_m=3.0,
        )
        self.assertEqual(last["aabb_overlap_cell_count"], 1)
        self.assertEqual(last["aabb_envelope_downward_front_m"], 3.0)
        self.assertEqual(last["touch_mesh_x_max"], True)
        self.assertEqual(last["touch_mesh_y_max"], True)
        self.assertEqual(last["touch_mesh_z_min"], True)

    def test_vertical_empty_slab_and_cross_track_width_use_paper_frame(self) -> None:
        gap = self._row(
            self.result["width_rows"],
            alpha_threshold=0.001,
            station_spacing_m=1.0,
            paper_downward_depth_slab_low_m=1.0,
            paper_downward_depth_slab_high_m=2.0,
        )
        self.assertEqual(gap["aabb_overlap_cell_count"], 0)
        self.assertIsNone(gap["aabb_envelope_width_m"])
        self.assertEqual(gap["conditional_width_over_Lc"], None)
        row = self._row(
            self.result["width_rows"],
            alpha_threshold=0.001,
            station_spacing_m=1.0,
            paper_downward_depth_slab_low_m=2.0,
            paper_downward_depth_slab_high_m=3.0,
        )
        self.assertAlmostEqual(row["paper_cross_track_lower_m"], -0.2)
        self.assertAlmostEqual(row["paper_cross_track_upper_m"], 1.7)
        self.assertAlmostEqual(row["aabb_envelope_width_m"], 1.9)
        self.assertAlmostEqual(row["conditional_width_over_Lc"], 3.8)
        self.assertAlmostEqual(row["center_assigned_native_water_volume_m3"], 0.33)

    def test_source_center_and_edge_registrations_are_fixed_physical_origins(self) -> None:
        variants = {row["choice"]: row["mesh_x_origin_m"] for row in self.result["origin_variants"]}
        self.assertEqual(
            variants,
            {"source_center": 1.0, "upstream_source_edge": 0.5, "downstream_source_edge": 1.5},
        )
        center = self._row(
            self.result["penetration_rows"],
            alpha_threshold=0.9,
            station_spacing_m=1.0,
            origin_choice="source_center",
            paper_streamwise_slab_low_m=0.0,
            paper_streamwise_slab_high_m=1.0,
        )
        upstream = self._row(
            self.result["penetration_rows"],
            alpha_threshold=0.9,
            station_spacing_m=1.0,
            origin_choice="upstream_source_edge",
            paper_streamwise_slab_low_m=0.5,
            paper_streamwise_slab_high_m=1.5,
        )
        self.assertEqual(
            center["aabb_envelope_downward_front_m"], upstream["aabb_envelope_downward_front_m"]
        )
        self.assertAlmostEqual(
            upstream["registration_origin_mesh_x_m"] - center["registration_origin_mesh_x_m"], -0.5
        )
        self.assertAlmostEqual(
            upstream["paper_streamwise_station_center_m"]
            - center["paper_streamwise_station_center_m"],
            0.5,
        )

    def test_requested_grid_retains_point_fifteen_meter_sensitivity(self) -> None:
        self.assertEqual(self.result["station_spacings_m"], [1.0, 0.15])

    def test_declared_case_origin_area_and_native_area_are_checked(self) -> None:
        case_inputs = {
            "coordinate_frame": {
                "source_origin_m": [1.0, 0.3, 0.0],
                "source_plane_z_m": 0.0,
                "paper_plot_transform": self.frame.paper_transform,
            },
            "source_origin_m": [1.0, 0.3, 0.0],
            "domain_bounds_m": {
                key: list(value) for key, value in self.frame.domain_bounds_m.items()
            },
            "source_patch_areas_m2": {"dash8Opening": 0.25},
            "source_geometry": {
                "sources": [
                    {
                        "name": "dash8Opening",
                        "area_m2": 0.25,
                        "center_x_m": 1.0,
                        "center_y_m": 0.3,
                        "plane_z_m": 0.0,
                        "bounds_m": {"x": [0.5, 1.5], "y": [-0.2, 0.8]},
                    }
                ]
            },
            "source_geometry_assumption": {"evidence_class": "synthetic assumed test area"},
        }
        frame = frame_from_case_inputs(case_inputs, self.snapshot)
        self.assertEqual(frame.source_origin_xyz_m, (1.0, 0.3, 0.0))
        self.assertEqual(frame.source_area_m2, 0.25)
        self.assertEqual(frame.l_characteristic_m, 0.5)
        case_inputs["source_patch_areas_m2"]["dash8Opening"] = 0.5
        with self.assertRaisesRegex(ValueError, "areas do not agree"):
            frame_from_case_inputs(case_inputs, self.snapshot)
        case_inputs["source_patch_areas_m2"]["dash8Opening"] = 0.25
        case_inputs["coordinate_frame"]["source_plane_z_m"] = 0.01
        with self.assertRaisesRegex(ValueError, "source plane z must equal"):
            frame_from_case_inputs(case_inputs, self.snapshot)
        case_inputs["coordinate_frame"]["source_plane_z_m"] = 0.0
        case_inputs["coordinate_frame"]["paper_plot_transform"]["paper_downward_z_m"] = (
            "mesh_z_m - source_plane_z_m"
        )
        with self.assertRaisesRegex(ValueError, "supported mesh x/y/-z mapping"):
            frame_from_case_inputs(case_inputs, self.snapshot)

    def test_native_centroids_must_lie_inside_vertex_aabbs(self) -> None:
        snapshot = toy_snapshot()
        snapshot["cell_centres_xyz_m"][0, 0] = -0.01
        with self.assertRaisesRegex(ValueError, "centroids lie outside their vertex AABBs"):
            extract_profiles(snapshot, self.frame, 1.0)

    def test_native_global_aabb_extents_must_match_declared_domain(self) -> None:
        frame = replace(
            self.frame,
            domain_bounds_m={"x": (0.0, 4.0), "y": (-0.4, 2.0), "z": (-3.0, 0.0)},
        )
        actual = _validate_native_domain(self.snapshot, frame)
        self.assertEqual(actual, {"x": (0.0, 4.0), "y": (-0.4, 2.0), "z": (-3.0, 0.0)})
        wrong_domain = replace(
            frame,
            domain_bounds_m={"x": (0.0, 4.01), "y": (-0.4, 2.0), "z": (-3.0, 0.0)},
        )
        with self.assertRaisesRegex(ValueError, "native mesh x bounds do not match"):
            _validate_native_domain(self.snapshot, wrong_domain)

    def test_native_gap_groups_do_not_bridge_empty_slabs(self) -> None:
        rows = [
            {"x": 0.0, "y": 1.0},
            {"x": 1.0, "y": None},
            {"x": 2.0, "y": 3.0},
        ]
        groups = _native_contiguous_groups(rows, "x", "y")
        self.assertEqual([[row["x"] for row in group] for group in groups], [[0.0], [2.0]])

    def test_independent_fig9_plot_swaps_axes_and_asymmetric_read_bounds(self) -> None:
        class CaptureAxis:
            def __init__(self) -> None:
                self.lines = []
                self.errors = []

            def plot(self, x, y, **kwargs) -> None:
                self.lines.append((list(x), list(y)))

            def errorbar(self, x, y, *, xerr, yerr, **kwargs) -> None:
                self.errors.append((list(x), list(y), list(xerr), list(yerr)))

        rows = [
            {
                "figure": "Fig. 9(a)",
                "series": "fig9_dash8_alpha0p001_t1p0s",
                "segment": "blue-1",
                "x_variable": "normalized_lateral_expansion_L_over_Lc",
                "x_unit": "1",
                "y_variable": "normalized_vertical_distance_z_over_Lc",
                "y_unit": "1",
                "x_value": "3.0",
                "y_value": "1.5",
                "read_bound_x": "0.4",
                "read_bound_y": "0.2",
            },
            {
                "figure": "Fig. 9(a)",
                "series": "fig9_dash8_alpha0p001_t1p0s",
                "segment": "blue-1",
                "x_variable": "normalized_lateral_expansion_L_over_Lc",
                "x_unit": "1",
                "y_variable": "normalized_vertical_distance_z_over_Lc",
                "y_unit": "1",
                "x_value": "4.0",
                "y_value": "2.5",
                "read_bound_x": "0.8",
                "read_bound_y": "0.3",
            },
        ]
        axis = CaptureAxis()
        _plot_fig9_independent(axis, rows)
        self.assertEqual(axis.lines, [([1.5, 2.5], [3.0, 4.0])])
        self.assertEqual(axis.errors, [([1.5, 2.5], [3.0, 4.0], [0.2, 0.3], [0.4, 0.8])])

    def test_fig9_series_selection_matches_native_snapshot_without_cross_time_rows(self) -> None:
        primary_specs = [
            ("dash8_t0.5s", "0.5"),
            ("dash8_t1.0s", "1.0"),
            ("dash8_t1.5s", "1.5"),
        ]
        independent_specs = [
            "fig9_dash8_alpha0p001_t0p5s",
            "fig9_dash8_alpha0p001_t1p0s",
            "fig9_dash8_alpha0p001_t1p5s",
        ]
        primary = [
            {
                "figure": "9",
                "series_id": series_id,
                "time_s": time_s,
                "alpha_l_threshold": "0.001",
            }
            for series_id, time_s in primary_specs
        ]
        primary.append({**primary[0], "alpha_l_threshold": "0.9"})
        independent = [
            {"figure": "Fig. 9(a)", "series": series_id} for series_id in independent_specs
        ]

        for time_s, primary_index, independent_index in (
            (0.5, 0, 0),
            (1.0, 1, 1),
            (1.5, 2, 2),
        ):
            selected = _paper_series(primary, independent, time_s)
            self.assertEqual(selected["fig9_primary"], [primary[primary_index]])
            self.assertEqual(selected["fig9_independent"], [independent[independent_index]])

        unsupported = _paper_series(primary, independent, 0.25)
        self.assertEqual(unsupported["fig9_primary"], [])
        self.assertEqual(unsupported["fig9_independent"], [])


if __name__ == "__main__":
    unittest.main()
