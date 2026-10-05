from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/compare_dash8_structure_counts.py"
SPEC = importlib.util.spec_from_file_location("dash8_count_comparison", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load comparison script at {SCRIPT}")
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def input_bundle(tmp_path: Path) -> dict[str, Path]:
    counts = tmp_path / "counts.csv"
    native = tmp_path / "native.csv"
    metadata = tmp_path / "metadata.json"
    experiment = tmp_path / "experiment.json"
    report = tmp_path / "baseline" / "analytics" / "report.json"
    report.parent.mkdir(parents=True)

    labels = {0.001: "0.001 <= alpha_L <= 1", 0.9: "0.9 <= alpha_L <= 1"}
    count_rows = [
        {
            "time_s": "0.305",
            "count": "14",
            "raw_count": "14.0",
            "count_target_min": "9.0",
            "count_target_max": "19.0",
            "count_read_status": "resolved_positive_count_read",
            "alpha_threshold": labels[0.001],
            "read_bound_time_s": "0.01",
            "read_bound_count": "5",
            "source_figure": "11c",
            "panel": "c",
            "aircraft": "Dash-8",
            "nominal_time_s": "0.3",
        },
        {
            "time_s": "",
            "count": "",
            "raw_count": "",
            "count_target_min": "",
            "count_target_max": "",
            "count_read_status": "no_visible_trace_read",
            "alpha_threshold": labels[0.001],
            "read_bound_time_s": "0.01",
            "read_bound_count": "5",
            "source_figure": "11c",
            "panel": "c",
            "aircraft": "Dash-8",
            "nominal_time_s": "0.1",
        },
        {
            "time_s": "0.105",
            "count": "",
            "raw_count": "-1.5",
            "count_target_min": "0.0",
            "count_target_max": "3.0",
            "count_read_status": "near_zero_unresolved_within_read_allowance",
            "alpha_threshold": labels[0.9],
            "read_bound_time_s": "0.01",
            "read_bound_count": "5",
            "source_figure": "11c",
            "panel": "c",
            "aircraft": "Dash-8",
            "nominal_time_s": "0.1",
        },
    ]
    _write_csv(counts, count_rows)
    native_rows = [
        {
            "time_s": "0.295",
            "count": "10",
            "raw_count": "10.0",
            "count_target_min": "5.0",
            "count_target_max": "15.0",
            "count_read_status": "resolved_positive_count_read",
            "alpha_threshold": labels[0.001],
            "read_bound_time_s": "0.01",
            "read_bound_count": "5",
            "panel": "c",
            "aircraft": "Dash-8",
        },
        {
            "time_s": "0.305",
            "count": "14",
            "raw_count": "14.0",
            "count_target_min": "9.0",
            "count_target_max": "19.0",
            "count_read_status": "resolved_positive_count_read",
            "alpha_threshold": labels[0.001],
            "read_bound_time_s": "0.01",
            "read_bound_count": "5",
            "panel": "c",
            "aircraft": "Dash-8",
        },
        {
            "time_s": "0.105",
            "count": "",
            "raw_count": "-1.5",
            "count_target_min": "0.0",
            "count_target_max": "3.0",
            "count_read_status": "near_zero_unresolved_within_read_allowance",
            "alpha_threshold": labels[0.9],
            "read_bound_time_s": "0.01",
            "read_bound_count": "5",
            "panel": "c",
            "aircraft": "Dash-8",
        },
    ]
    _write_csv(native, native_rows)
    metadata.write_text(
        json.dumps(
            {
                "fig11c_axes_page_pixels": {"y_zero_px": 2651.0},
                "source_pdf_sha256": "paper-hash",
                "source_locator": "PDF p. 10 / journal p. 1524, Fig. 11(c)",
                "digitization_allowances": {"count_plus_minus": 5, "time_plus_minus_s": 0.01},
            }
        ),
        encoding="utf-8",
    )
    experiment.write_text(
        json.dumps(
            {
                "experiment_id": "E2_DASH8_BREAKUP_EXPLORATORY",
                "classification": "exploratory",
                "comparison_rules": {"completion": "not a gate"},
            }
        ),
        encoding="utf-8",
    )

    snapshots = []
    for time_s, cloud, core in (
        (0.0, (0, 0, 0), (0, 0, 0)),
        (0.105, (3, 0, 3), (2, 2, 1)),
        (0.304, (18, 1, 9), (5, 0, 3)),
        (0.5, (21, 0, 21), (6, 0, 4)),
    ):
        snapshots.append(
            {
                "time_s": time_s,
                "thresholds": [
                    {
                        "alpha_threshold": 0.001,
                        "connected_cell_regions": cloud[0],
                        "single_cell_regions": cloud[1],
                        "point_connected_cell_regions": cloud[2],
                    },
                    {
                        "alpha_threshold": 0.9,
                        "connected_cell_regions": core[0],
                        "single_cell_regions": core[1],
                        "point_connected_cell_regions": core[2],
                    },
                ],
            }
        )
    report.write_text(
        json.dumps(
            {
                "classification": "exploratory test input",
                "case_id": "synthetic-test-case",
                "times": snapshots,
            }
        ),
        encoding="utf-8",
    )
    return {
        "counts": counts,
        "native": native,
        "metadata": metadata,
        "experiment": experiment,
        "report": report,
    }


def test_exact_saved_times_and_propagated_visible_read_envelope(
    input_bundle: dict[str, Path],
) -> None:
    bundle = input_bundle
    binned, native, _ = comparison.source_inputs(
        bundle["counts"], bundle["native"], bundle["metadata"]
    )
    report = json.loads(bundle["report"].read_text(encoding="utf-8"))
    rows, summary = comparison.summarize_run(
        run_id="baseline",
        report=report,
        report_path=bundle["report"],
        native=native,
    )
    assert next(
        row for row in binned[0.001] if row["count_read_status"] == "resolved_positive_count_read"
    )["nominal_time_s"] == pytest.approx(0.3)
    cloud = next(
        row
        for row in rows
        if row["time_s"] == pytest.approx(0.304)
        and row["alpha_threshold"] == 0.001
        and row["operator"] == "face_all_sizes"
    )
    assert cloud["time_s"] == 0.304
    assert cloud["paper_native_time_s_nearest"] == 0.305
    assert cloud["paper_native_time_delta_s"] == pytest.approx(0.001)
    assert cloud["source_read_bound_time_s"] == pytest.approx(0.01)
    assert cloud["source_read_bound_count"] == pytest.approx(5)
    assert cloud["source_visible_envelope_samples"] == 2
    assert cloud["source_count_envelope_min"] == pytest.approx(5)
    assert cloud["source_count_envelope_max"] == pytest.approx(19)
    assert cloud["absolute_error_count"] == pytest.approx(4)
    assert cloud["relative_error_fraction"] == pytest.approx(4 / 14)
    assert cloud["within_source_envelope"] is True

    nearzero = next(
        row
        for row in rows
        if row["time_s"] == pytest.approx(0.105)
        and row["alpha_threshold"] == 0.9
        and row["operator"] == "face_all_sizes"
    )
    assert nearzero["comparison_status"] == "near_zero_source_interval_only"
    assert nearzero["source_count_envelope_min"] == pytest.approx(0)
    assert nearzero["relative_error_fraction"] is None
    assert nearzero["absolute_error_count"] is None

    gap = next(
        row
        for row in rows
        if row["time_s"] == pytest.approx(0.5)
        and row["alpha_threshold"] == 0.001
        and row["operator"] == "face_all_sizes"
    )
    assert gap["comparison_status"] == "no_visible_native_trace_within_time_bound"
    assert gap["source_native_raw_count"] is None
    assert gap["source_count_envelope_min"] is None

    assert summary["sampled_horizon_fraction_of_0_5_s_by_last_saved_time"] == pytest.approx(0.1)
    assert summary["saved_snapshot_count_in_0_5_s"] == 4
    assert summary["expected_0_1_s_target_bin_count_in_0_5_s"] == 51
    assert summary["saved_0_1_s_target_bin_coverage_count"] == 4
    assert summary["saved_0_1_s_target_bin_coverage_fraction"] == pytest.approx(4 / 51)
    assert summary["maximum_saved_time_gap_s"] == pytest.approx(0.199)
    assert summary["missing_0_1_s_target_bins_s"][:4] == [0.2, 0.4, 0.6, 0.7]


def test_repeatable_report_cli_writes_bundle_and_refuses_overwrite(
    input_bundle: dict[str, Path], tmp_path: Path
) -> None:
    first_report = input_bundle["report"]
    second_report = tmp_path / "branch" / "analytics" / "report.json"
    second_report.parent.mkdir(parents=True)
    second_report.write_bytes(first_report.read_bytes())
    output = tmp_path / "new-bundle"
    common = [
        "--output-dir",
        str(output),
        "--source-counts",
        str(input_bundle["counts"]),
        "--source-native",
        str(input_bundle["native"]),
        "--metadata-json",
        str(input_bundle["metadata"]),
        "--experiment-json",
        str(input_bundle["experiment"]),
    ]
    comparison.main(["--report", str(first_report), "--report", str(second_report), *common])
    expected = {"comparisons.csv", "summary.json", "counts.png", "run_metadata.json"}
    assert {path.name for path in output.iterdir()} == expected
    metadata = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["reports"]) == 2
    assert metadata["source"]["axis_y_zero_px"] == 2651.0
    assert metadata["runs"][0][
        "sampled_horizon_fraction_of_0_5_s_by_last_saved_time"
    ] == pytest.approx(0.1)

    sentinel = output / "preserve.txt"
    sentinel.write_text("keep this evidence", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        comparison.main(["--report", str(first_report), *common])
    assert sentinel.read_text(encoding="utf-8") == "keep this evidence"
    assert (output / "summary.json").is_file()


def test_count_sensitivities_remain_separate() -> None:
    methods = comparison.count_methods(
        {
            "connected_cell_regions": 12,
            "single_cell_regions": 3,
            "point_connected_cell_regions": 7,
        }
    )
    assert [(row["operator"], row["count"]) for row in methods] == [
        ("face_all_sizes", 12),
        ("point_all_sizes", 7),
        ("face_minimum_2_cells", 9),
    ]
    assert [row["role"] for row in methods] == ["primary", "sensitivity", "sensitivity"]


def test_relative_error_is_omitted_when_count_bound_overlaps_zero() -> None:
    source = comparison.native_envelope(
        [
            {
                "time_s": 0.3,
                "read_bound_time_s": 0.01,
                "raw_count": 3.0,
                "count_target_min": 0.0,
                "count_target_max": 8.0,
                "read_bound_count": 5.0,
                "count_read_status": "resolved_positive_count_read",
            }
        ],
        0.3,
    )
    row = comparison.comparison_row(
        run_id="test",
        report_path=Path("report.json"),
        case_id="case",
        time_s=0.3,
        alpha_threshold=0.001,
        method={
            "operator": "face_all_sizes",
            "role": "primary",
            "available": True,
            "count": 5,
        },
        source=source,
    )
    assert row["source_native_raw_count"] == 3.0
    assert row["absolute_error_count"] == 2.0
    assert row["source_count_envelope_min"] == 0.0
    assert row["relative_error_fraction"] is None
    assert row["comparison_status"] == "positive_source_interval_overlaps_zero"


def test_native_analysis_schema_preserves_one_time_and_threshold_sensitivities(
    input_bundle: dict[str, Path], tmp_path: Path
) -> None:
    native_report = {
        "schema": comparison.NATIVE_ANALYSIS_SCHEMA,
        "time_name": "1.000000",
        "time_value_s": 1.0,
        "source_patch": "dash8Opening",
        "unpublished_paper_detector_equivalence": False,
        "input_provenance": {"connectivity": {"method": "native face edges; no point links"}},
        "topology": {"native_cells": 123456},
        "thresholds": {
            "0.001": {
                "min_cells_1": {"component_count": 41},
                "min_cells_2": {"component_count": 35},
            },
            "0.9": {
                "min_cells_1": {"component_count": 123},
                "min_cells_2": {"component_count": 38},
            },
        },
    }
    report_path = tmp_path / "native-reference" / "analysis.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(native_report), encoding="utf-8")

    binned, native_source, _ = comparison.source_inputs(
        input_bundle["counts"], input_bundle["native"], input_bundle["metadata"]
    )
    normalized = comparison.normalize_native_analysis(native_report, report_path)
    rows, summary = comparison.summarize_run(
        run_id="native-reference",
        report=normalized,
        report_path=report_path,
        native=native_source,
    )
    primary_cloud = next(
        row
        for row in rows
        if row["alpha_threshold"] == 0.001 and row["operator"] == "face_all_sizes"
    )
    minimum_two_cloud = next(
        row
        for row in rows
        if row["alpha_threshold"] == 0.001 and row["operator"] == "face_minimum_2_cells"
    )
    point_cloud = next(
        row
        for row in rows
        if row["alpha_threshold"] == 0.001 and row["operator"] == "point_all_sizes"
    )
    assert primary_cloud["time_s"] == 1.0
    assert primary_cloud["simulation_count"] == 41
    assert minimum_two_cloud["simulation_count"] == 35
    assert point_cloud["operator_available"] is False
    assert point_cloud["simulation_count"] is None
    assert summary["saved_snapshot_count"] == 1
    assert summary["saved_time_min_in_0_5_s"] == 1.0
    assert summary["saved_time_max_in_0_5_s"] == 1.0
    assert summary["saved_0_1_s_target_bin_coverage_count"] == 1
    assert summary["native_analysis_provenance"]["point_touch_sensitivity_available"] is False
    assert "not a reconstructed 0-5 s history" in summary["report_classification"]

    # Existing source-bin values still come from the shared Fig. 11 target data.
    assert binned[0.001][0]["nominal_time_s"] == 0.1


def test_native_analysis_rejects_inconsistent_time_and_filter_counts(tmp_path: Path) -> None:
    report_path = tmp_path / "analysis.json"
    valid = {
        "schema": comparison.NATIVE_ANALYSIS_SCHEMA,
        "time_name": "1.000000",
        "time_value_s": 1.0,
        "thresholds": {
            "0.001": {
                "min_cells_1": {"component_count": 4},
                "min_cells_2": {"component_count": 3},
            }
        },
    }
    with pytest.raises(ValueError, match="time_name and time_value_s disagree"):
        comparison.normalize_native_analysis({**valid, "time_name": "0.5"}, report_path)
    invalid_filter = json.loads(json.dumps(valid))
    invalid_filter["thresholds"]["0.001"]["min_cells_2"]["component_count"] = 5
    with pytest.raises(ValueError, match="exceeds min_cells_1"):
        comparison.normalize_native_analysis(invalid_filter, report_path)


def test_native_reports_with_same_parent_keep_separate_named_series(
    input_bundle: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports: list[Path] = []
    for variant, cloud_count, core_count in (
        ("uniform", 41, 103),
        ("three-component", 74, 89),
    ):
        report_path = tmp_path / variant / "observers" / "native-analysis" / "analysis.json"
        report_path.parent.mkdir(parents=True)
        thresholds = {
            "0.001": {
                "min_cells_1": {"component_count": cloud_count},
                "min_cells_2": {"component_count": cloud_count - 3},
            },
            "0.9": {
                "min_cells_1": {"component_count": core_count},
                "min_cells_2": {"component_count": core_count - 2},
            },
        }
        report_path.write_text(
            json.dumps(
                {
                    "schema": comparison.NATIVE_ANALYSIS_SCHEMA,
                    "time_name": "1.000000",
                    "time_value_s": 1.0,
                    "source_patch": "dash8Opening",
                    "topology": {"native_cells": 1000},
                    "thresholds": thresholds,
                }
            ),
            encoding="utf-8",
        )
        reports.append(report_path)

    with pytest.raises(ValueError, match="infer the same run_id"):
        comparison.build_bundle(
            reports,
            counts_path=input_bundle["counts"],
            trace_path=input_bundle["native"],
            metadata_path=input_bundle["metadata"],
            experiment_path=input_bundle["experiment"],
        )

    import matplotlib.axes

    plotted_labels: list[str] = []
    original_plot = matplotlib.axes.Axes.plot

    def capture_plot_labels(self: object, *args: object, **kwargs: object) -> object:
        label = kwargs.get("label")
        if isinstance(label, str):
            plotted_labels.append(label)
        return original_plot(self, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "plot", capture_plot_labels)
    output = tmp_path / "native-pair-comparison"
    comparison.write_bundle(
        output,
        reports,
        report_labels=["local-mesh uniform", "three-component inlet"],
        counts_path=input_bundle["counts"],
        trace_path=input_bundle["native"],
        metadata_path=input_bundle["metadata"],
        experiment_path=input_bundle["experiment"],
    )

    with (output / "comparisons.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    cloud_rows = [
        row
        for row in rows
        if row["alpha_threshold"] == "0.001" and row["operator"] == "face_all_sizes"
    ]
    assert [(row["run_id"], int(row["simulation_count"])) for row in cloud_rows] == [
        ("local-mesh uniform", 41),
        ("three-component inlet", 74),
    ]
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert [run["run_id"] for run in summary["runs"]] == [
        "local-mesh uniform",
        "three-component inlet",
    ]
    assert all(
        report["path"].endswith("native-analysis/analysis.json") for report in summary["reports"]
    )
    assert "local mesh uniform: face, all sizes" in plotted_labels
    assert "three component inlet: face, all sizes" in plotted_labels


def test_report_labels_must_map_one_to_one_but_may_name_one_shared_run(
    input_bundle: dict[str, Path],
) -> None:
    report = json.loads(input_bundle["report"].read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="once for each"):
        comparison.build_bundle([input_bundle["report"]], report_labels=[])
    _, summaries, _, _ = comparison.build_bundle(
        [input_bundle["report"], input_bundle["report"]], report_labels=["same", "same"]
    )
    assert [run["run_id"] for run in summaries["runs"]] == ["same", "same"]
    assert report["case_id"] == "synthetic-test-case"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"connected_cell_regions": -1, "single_cell_regions": 0}, "nonnegative integer"),
        ({"connected_cell_regions": 1.5, "single_cell_regions": 0}, "nonnegative integer"),
        ({"connected_cell_regions": 1, "single_cell_regions": 2}, "cannot exceed"),
    ],
)
def test_invalid_structure_counts_are_rejected(data: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        comparison.count_methods(data)
