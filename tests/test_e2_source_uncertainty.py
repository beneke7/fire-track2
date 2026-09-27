"""Independent CPU checks for the implementation-only E2 M03 history evaluator."""

from __future__ import annotations

import copy
import json
import math
import platform
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from aerial_drop import e2_source_uncertainty as e2

ROOT = Path(__file__).resolve().parents[1]
METHOD_PATH = ROOT / "experiments" / "E2_SOURCE_UNCERTAINTY_METHOD_DRAFT.md"
PRIMARY_SOURCE_PATH = ROOT / "data" / "derived" / "calbrix_dash8_fig4_velocity.csv"
SECOND_SOURCE_PATH = ROOT / "data" / "derived" / "calbrix_dash8_fig4_velocity_independent.csv"
PRIMARY_TARGET_PATH = ROOT / "data" / "derived" / "calbrix_dash8_cloud_curves.csv"
SECOND_TARGET_PATH = ROOT / "data" / "derived" / "calbrix_dash8_cloud_curves_independent.csv"
GENERATOR_PATH = ROOT / "src" / "aerial_drop" / "e2_source_uncertainty.py"

EXPECTED_METHOD_SHA256 = "bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b"
EXPECTED_HASHES = {
    PRIMARY_SOURCE_PATH: "b43f2ee1220182cca532c290a0d265a5d6f382eb6025b9b7689216fea8f6c332",
    SECOND_SOURCE_PATH: "fd4791bf79e39e2dbd3261af59c96b13d731b2a0a6ce4fe5450092aa2c1d7f0b",
    PRIMARY_TARGET_PATH: "308c23d755828027acb54e9e9181f74142f831ad6649a1fc91f0a482023a5969",
    SECOND_TARGET_PATH: "2634389063a3d75a2e1e2c8523b3d27ae204ae31557d9e354de7fe4c2aceab4b",
}


def load_sources() -> dict[str, e2.SourceHistory]:
    return {
        "primary": e2.read_source_history(PRIMARY_SOURCE_PATH, read_id="primary"),
        "second_read": e2.read_source_history(SECOND_SOURCE_PATH, read_id="second_read"),
    }


def _sha(character: str) -> str:
    return character * 64


def synthetic_dependencies() -> dict[str, object]:
    sources = load_sources()
    return {
        "method_revision": "M03",
        "method_document_sha256": e2.sha256_file(METHOD_PATH),
        "source_pdf_sha256": e2.EXPECTED_SOURCE_PDF_SHA256,
        "source_csv_sha256": {
            "primary": sources["primary"].source_sha256,
            "second_read": sources["second_read"].source_sha256,
        },
        "target_csv_sha256": {
            "primary": e2.sha256_file(PRIMARY_TARGET_PATH),
            "second_read": e2.sha256_file(SECOND_TARGET_PATH),
        },
        "source_record_sha256": e2.sha256_file(ROOT / "experiments" / "E2_CALBRIX_SOURCE.md"),
        "replay_sha256": e2.sha256_file(ROOT / "experiments" / "E2_E3_PROVISIONAL_REPLAY_DRAFT.md"),
        "validation_sha256": e2.sha256_file(ROOT / "docs" / "VALIDATION.md"),
        "plan_sha256": e2.sha256_file(ROOT / "track2_aerial_drop_experiment_plan.md"),
        "approved_contract_sha256": None,
        "generator_source_sha256": e2.sha256_file(GENERATOR_PATH),
        "python": {
            "implementation": platform.python_implementation(),
            "version": sys.version.split()[0],
        },
        "conventions": copy.deepcopy(e2.CONVENTIONS),
        "startup_input_sha256": {
            "gas_only_initial_state": _sha("a"),
            "non_source_boundary_inputs": _sha("b"),
        },
        "repository": {
            "revision": "c" * 40,
            "dirty_state": {"state": "synthetic-test-fixture", "evidence_sha256": _sha("d")},
        },
    }


def test_method_and_four_csv_inputs_match_the_pinned_m03_snapshot() -> None:
    assert e2.sha256_file(METHOD_PATH) == EXPECTED_METHOD_SHA256
    for path, expected_hash in EXPECTED_HASHES.items():
        assert e2.sha256_file(path) == expected_hash


def test_strict_utf8_decimal_fraction_parser_and_exact_source_reads() -> None:
    sources = load_sources()
    assert len(sources["primary"].times) == len(sources["second_read"].times) == 51
    assert sources["primary"].times[1] == Fraction(1, 10)
    assert sources["primary"].velocities[1] == Fraction(229, 100)
    assert sources["primary"].velocity_bounds[0] == Fraction(15, 100)
    assert sources["primary"].tapered_bound(Fraction(0)) == 0
    assert sources["primary"].tapered_bound(Fraction(3, 100)) == Fraction(45, 1000)
    assert sources["second_read"].velocities[1] == Fraction(1161, 500)

    with pytest.raises(e2.HistoryGenerationError, match="strict UTF-8"):
        e2.parse_source_csv_bytes(b"\xff", read_id="primary")
    malformed = PRIMARY_SOURCE_PATH.read_bytes().replace(b"0.000,0.03", b"NaN,0.03", 1)
    with pytest.raises(e2.HistoryGenerationError, match="non-finite"):
        e2.parse_source_csv_bytes(malformed, read_id="primary")


def test_nominal_exact_evaluator_reproduces_both_piecewise_csv_histories() -> None:
    for read_id, source in load_sources().items():
        nominal = e2.Scenario(read_id, "0", "0")
        for index, source_time in enumerate(source.times):
            assert e2.exact_source_value(source, nominal, source_time) == source.velocities[index]
        for index, (left, right) in enumerate(zip(source.times, source.times[1:])):
            for numerator, denominator in ((1, 3), (1, 2), (2, 3)):
                query = left + (right - left) * Fraction(numerator, denominator)
                subinterval = (query - left) / (right - left)
                expected = source.velocities[index] + subinterval * (
                    source.velocities[index + 1] - source.velocities[index]
                )
                assert e2.exact_source_value(source, nominal, query) == expected


def test_all_18_scenarios_preserve_shifted_knots_floor_and_runtime_roundoff() -> None:
    sources = load_sources()
    scenarios = e2.proposed_scenarios()
    assert len(scenarios) == 18
    assert [(item.read_id, item.delta_text, item.residual_text) for item in scenarios[:9]] == [
        ("primary", delta, residual)
        for delta in e2.DELTA_STRINGS
        for residual in e2.RESIDUAL_STRINGS
    ]

    generated: list[e2.GeneratedHistory] = []
    for scenario in scenarios:
        source = sources[scenario.read_id]
        history = e2.generate_history(source, scenario)
        generated.append(history)
        assert history.exact_knots[0].time_s == e2.RUN_START_S
        assert history.exact_knots[-1].time_s == e2.RUN_END_S
        assert Fraction(0) in {knot.time_s for knot in history.exact_knots}
        assert all(
            math.isfinite(time) and math.isfinite(speed) and speed >= 0
            for time, speed in history.float_knots
        )
        assert history.table_bytes.startswith(b"time_s,u_l_m_s\n")
        assert history.table_bytes.endswith(b"\n") and not history.table_bytes.endswith(b"\n\n")
        assert b"\r" not in history.table_bytes and not history.table_bytes.startswith(
            b"\xef\xbb\xbf"
        )
        assert history.table_sha256 == e2.sha256_bytes(history.table_bytes)
        assert history.history_content_id == f"E2-HIST-H{history.table_sha256}"
        assert history.projection.interior_query_count == 3 * (len(history.exact_knots) - 1)
        assert history.projection.max_table_evaluator_error_m_s <= 16 * math.ulp(1.0)
        assert history.integrals.max_velocity_simpson_difference == 0
        assert history.integrals.max_velocity_squared_simpson_difference == 0

        exact_times = {knot.time_s for knot in history.exact_knots}
        for source_time in source.times:
            shifted_time = source_time - scenario.delta
            if e2.RUN_START_S <= shifted_time <= e2.RUN_END_S:
                assert shifted_time in exact_times
        source_origin = -scenario.delta
        if e2.RUN_START_S <= source_origin <= e2.RUN_END_S:
            assert source_origin in exact_times

        assert e2.exact_source_value(source, scenario, e2.RUN_START_S) == 0
        if scenario.delta == Fraction(-3, 100):
            assert e2.exact_source_value(source, scenario, Fraction(29, 1000)) == 0
            assert e2.exact_source_value(source, scenario, Fraction(3, 100)) == 0
            assert e2.exact_source_value(source, scenario, Fraction(301, 10000)) > 0
        if scenario.delta == Fraction(3, 100):
            assert e2.exact_source_value(source, scenario, Fraction(-29, 1000)) > 0
        if scenario.delta == 0:
            assert e2.exact_source_value(source, scenario, Fraction(0)) == 0
        if scenario.delta == Fraction(3, 100):
            expected_at_zero = max(
                Fraction(0),
                source.value(Fraction(3, 100))
                + scenario.residual * source.tapered_bound(Fraction(3, 100)),
            )
            assert e2.exact_source_value(source, scenario, Fraction(0)) == expected_at_zero
            expected_read_value = (
                Fraction(687, 1000) if scenario.read_id == "primary" else Fraction(3483, 5000)
            )
            assert expected_at_zero == max(
                Fraction(0), expected_read_value + scenario.residual * Fraction(45, 1000)
            )
        expected_at_diagnostic = source.value(e2.DIAGNOSTIC_TIME_S + scenario.delta)
        if scenario.residual == 0:
            assert (
                e2.exact_source_value(source, scenario, e2.DIAGNOSTIC_TIME_S)
                == expected_at_diagnostic
            )
        with pytest.raises(e2.HistoryGenerationError, match="exceeds the 5 s"):
            e2.exact_source_value(source, scenario, Fraction(501, 100) - scenario.delta)

    assert len({item.scenario for item in generated}) == 18
    assert any(
        knot.velocity_m_s == 0 and e2.RUN_START_S < knot.time_s < e2.RUN_END_S
        for item in generated
        for knot in item.exact_knots
        if item.scenario.residual == -1
    )


def test_strict_interior_floor_roots_are_inserted_exactly() -> None:
    times = tuple(Fraction(i, 10) for i in range(51))
    velocities = [Fraction(0)] * 51
    velocities[1] = Fraction(1, 10)
    velocities[2] = Fraction(3, 10)
    velocity_bounds = [Fraction(15, 100)] * 51
    source = e2.SourceHistory(
        read_id="primary",
        times=times,
        velocities=tuple(velocities),
        velocity_bounds=tuple(velocity_bounds),
        source_sha256=_sha("a"),
    )
    scenario = e2.Scenario("primary", "0", "-1")
    roots = e2._strict_interior_roots(source, scenario.residual)
    assert roots[:2] == (Fraction(1, 8), Fraction(1, 4))
    history = e2.generate_history(source, scenario)
    knots_by_time = {knot.time_s: knot.velocity_m_s for knot in history.exact_knots}
    assert knots_by_time[Fraction(1, 8)] == 0
    assert knots_by_time[Fraction(1, 4)] == 0


def test_common_absolute_clock_and_advanced_nominal_integral_match_inline_arithmetic() -> None:
    source = load_sources()["primary"]
    advanced_nominal = e2.Scenario("primary", "0.03", "0")
    history = e2.generate_history(source, advanced_nominal)
    assert e2.exact_source_value(source, advanced_nominal, Fraction(0)) == Fraction(687, 1000)
    assert history.integrals.integral_velocity_m == Fraction(376253, 200000)
    # This is only an integral of the source velocity history, not solver flux.


def test_distinct_rational_knots_that_collapse_to_one_float_are_rejected() -> None:
    tiny = Fraction(1, 2**1075)
    with pytest.raises(e2.FloatKnotCollision, match="FLOAT_KNOT_COLLISION"):
        e2._float_projection(
            (e2.ExactKnot(Fraction(0), Fraction(0)), e2.ExactKnot(tiny, Fraction(0)))
        )


def test_fraction_to_binary64_projection_uses_ties_to_even() -> None:
    even_tie = Fraction(1) + Fraction(1, 2**53)
    odd_tie = Fraction(1) + Fraction(3, 2**53)
    assert float(even_tie) == 1.0
    assert float(odd_tie) == 1.0 + 2.0**-51
    with pytest.raises(e2.HistoryGenerationError, match="unsupported scenario delta"):
        e2.Scenario("primary", "0.01", "0")
    with pytest.raises(e2.HistoryGenerationError, match="unsupported residual coefficient"):
        e2.Scenario("primary", "0", "0.5")


def test_canonical_bytes_and_dependency_hashes_follow_the_m03_rules() -> None:
    first = e2.canonical_json_bytes({"z": ("-0.03", None), "a": "é"})
    second = e2.canonical_json_bytes({"a": "é", "z": ["-0.03", None]})
    assert first == second == '{"a":"é","z":["-0.03",null]}\n'.encode("utf-8")
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    with pytest.raises(e2.HistoryGenerationError, match="use strings"):
        e2.canonical_json_bytes({"decimal_parameter": 0.03})

    dependencies = synthetic_dependencies()
    base_digest = e2.upstream_dependency_digest(dependencies)
    unchanged = e2.upstream_dependency_digest(copy.deepcopy(dependencies))
    assert base_digest == unchanged
    canonical_roundtrip = json.loads(e2.canonical_json_bytes(dependencies))
    assert e2.upstream_dependency_digest(canonical_roundtrip) == base_digest
    same_table_hash = e2.sha256_bytes(b"same canonical table bytes")
    assert e2.history_content_id(b"same canonical table bytes") == ("E2-HIST-H" + same_table_hash)
    assert e2.history_content_id(b"changed canonical table bytes") != (
        "E2-HIST-H" + same_table_hash
    )
    scenario = e2.Scenario("primary", "0", "0")
    base_case_id = e2.scenario_case_id(scenario, base_digest, same_table_hash)
    assert base_case_id.endswith(f"-U{base_digest}-H{same_table_hash}")

    mutation_paths = (
        ("method_document_sha256",),
        ("source_pdf_sha256",),
        ("source_csv_sha256", "primary"),
        ("source_csv_sha256", "second_read"),
        ("target_csv_sha256", "primary"),
        ("target_csv_sha256", "second_read"),
        ("source_record_sha256",),
        ("replay_sha256",),
        ("validation_sha256",),
        ("plan_sha256",),
        ("generator_source_sha256",),
        ("python", "implementation"),
        ("python", "version"),
        ("startup_input_sha256", "gas_only_initial_state"),
        ("startup_input_sha256", "non_source_boundary_inputs"),
        ("repository", "revision"),
        ("repository", "dirty_state", "evidence_sha256"),
    )
    for index, path in enumerate(mutation_paths):
        changed = copy.deepcopy(dependencies)
        target: object = changed
        for key in path[:-1]:
            target = target[key]  # type: ignore[index]
        leaf = path[-1]
        if leaf == "version":
            target[leaf] = "synthetic-mutated-version"  # type: ignore[index]
        elif leaf == "implementation":
            target[leaf] = "SyntheticPython"  # type: ignore[index]
        elif leaf == "revision":
            target[leaf] = "e" * 40  # type: ignore[index]
        else:
            target[leaf] = _sha("e" if index % 2 == 0 else "f")  # type: ignore[index]
        changed_digest = e2.upstream_dependency_digest(changed)
        assert changed_digest != base_digest
        assert e2.scenario_case_id(scenario, changed_digest, same_table_hash) != base_case_id

    changed_contract = copy.deepcopy(dependencies)
    changed_contract["approved_contract_sha256"] = _sha("e")
    contract_digest = e2.upstream_dependency_digest(changed_contract)
    assert contract_digest != base_digest
    assert e2.scenario_case_id(scenario, contract_digest, same_table_hash) != base_case_id

    changed_table_hash = e2.sha256_bytes(b"changed canonical table bytes")
    assert changed_table_hash != same_table_hash
    assert e2.scenario_case_id(scenario, base_digest, changed_table_hash) != base_case_id

    # Approval is downstream: it is not accepted by the upstream schema and is
    # absent from source-case identity inputs.
    with pytest.raises(e2.HistoryGenerationError, match=r"extra=\['approval_record_sha256'\]"):
        e2.upstream_dependency_digest({**dependencies, "approval_record_sha256": _sha("f")})
    assert e2.scenario_case_id(scenario, base_digest, same_table_hash) == base_case_id


def test_fixture_source_matrix_has_18_cases_null_contract_and_no_identity_cycle() -> None:
    sources = load_sources()

    def make_fixture_manifest(dependencies: dict[str, object]) -> dict[str, object]:
        upstream_hash = e2.upstream_dependency_digest(dependencies)
        cases: list[dict[str, object]] = []
        histories_by_id: dict[str, dict[str, str]] = {}
        for scenario in e2.proposed_scenarios():
            history = e2.generate_history(sources[scenario.read_id], scenario)
            case_id = e2.scenario_case_id(scenario, upstream_hash, history.table_sha256)
            history_path = f"implementation-fixtures/{history.history_content_id}.csv"
            histories_by_id[history.history_content_id] = {
                "path": history_path,
                "history_content_id": history.history_content_id,
                "history_table_sha256": history.table_sha256,
            }
            cases.append(
                {
                    "scenario": scenario.as_record(),
                    "case_id": case_id,
                    "history_content_id": history.history_content_id,
                    "history_table_sha256": history.table_sha256,
                    "history_path": history_path,
                }
            )

        return {
            "schema": "e2-source-matrix-m03-implementation-fixture",
            "status": "implementation_fixture_not_approved_or_runnable",
            "method_revision": e2.METHOD_REVISION,
            "repository": dependencies["repository"],
            "source_pdf_sha256": dependencies["source_pdf_sha256"],
            "source_csv_sha256": dependencies["source_csv_sha256"],
            "target_csv_sha256": dependencies["target_csv_sha256"],
            "source_record_sha256": dependencies["source_record_sha256"],
            "replay_sha256": dependencies["replay_sha256"],
            "validation_sha256": dependencies["validation_sha256"],
            "plan_sha256": dependencies["plan_sha256"],
            "method_document_sha256": dependencies["method_document_sha256"],
            "generator_source_sha256": dependencies["generator_source_sha256"],
            "python": dependencies["python"],
            "conventions": dependencies["conventions"],
            "startup_input_sha256": dependencies["startup_input_sha256"],
            "upstream_dependency_sha256": upstream_hash,
            "histories": list(histories_by_id.values()),
            "cases": cases,
            "approved_contract_sha256": None,
        }

    dependencies = synthetic_dependencies()
    manifest = make_fixture_manifest(dependencies)
    manifest_bytes = e2.canonical_source_matrix_manifest_bytes(manifest)
    assert manifest["approved_contract_sha256"] is None
    assert b'"approved_contract_sha256":null' in manifest_bytes
    assert len(manifest["cases"]) == 18
    assert len(manifest["histories"]) <= 18
    assert e2.source_matrix_manifest_sha256(manifest) == e2.sha256_bytes(manifest_bytes)
    assert manifest_bytes.endswith(b"\n") and b"source_matrix_manifest_sha256" not in manifest_bytes
    upstream_hash = manifest["upstream_dependency_sha256"]
    assert all("-U" + upstream_hash + "-H" in case["case_id"] for case in manifest["cases"])

    for field, bad_value in (
        ("schema", "unrecognized-fixture-schema"),
        ("schema", 3),
        ("status", "PASS"),
        ("status", ["implementation_fixture_not_approved_or_runnable"]),
    ):
        bad_fixture_metadata = copy.deepcopy(manifest)
        bad_fixture_metadata[field] = bad_value
        with pytest.raises(e2.HistoryGenerationError, match=f"implementation fixture {field}"):
            e2.canonical_source_matrix_manifest_bytes(bad_fixture_metadata)

    for alias in ("./", "//"):
        aliased_path_manifest = copy.deepcopy(manifest)
        first_path = aliased_path_manifest["histories"][0]["path"]
        second_history = aliased_path_manifest["histories"][1]
        prefix, filename = first_path.rsplit("/", 1)
        second_history_id = second_history["history_content_id"]
        aliased_path = f"{prefix}/{alias}{filename}"
        second_history["path"] = aliased_path
        for case in aliased_path_manifest["cases"]:
            if case["history_content_id"] == second_history_id:
                case["history_path"] = aliased_path
        with pytest.raises(e2.HistoryGenerationError, match="canonical file path"):
            e2.canonical_source_matrix_manifest_bytes(aliased_path_manifest)

    for invalid_path in (
        "implementation-fixtures/",
        "implementation-fixtures/.",
        "bad\x00path.csv",
    ):
        invalid_path_manifest = copy.deepcopy(manifest)
        target_history = invalid_path_manifest["histories"][0]
        target_id = target_history["history_content_id"]
        target_history["path"] = invalid_path
        for case in invalid_path_manifest["cases"]:
            if case["history_content_id"] == target_id:
                case["history_path"] = invalid_path
        with pytest.raises(e2.HistoryGenerationError):
            e2.canonical_source_matrix_manifest_bytes(invalid_path_manifest)

    duplicate_history_path = copy.deepcopy(manifest)
    duplicate_path = duplicate_history_path["histories"][0]["path"]
    second_id = duplicate_history_path["histories"][1]["history_content_id"]
    duplicate_history_path["histories"][1]["path"] = duplicate_path
    for case in duplicate_history_path["cases"]:
        if case["history_content_id"] == second_id:
            case["history_path"] = duplicate_path
    with pytest.raises(e2.HistoryGenerationError, match="history table paths must be unique"):
        e2.canonical_source_matrix_manifest_bytes(duplicate_history_path)

    stale_upstream_hash = copy.deepcopy(manifest)
    stale_upstream_hash["upstream_dependency_sha256"] = _sha("f")
    with pytest.raises(e2.HistoryGenerationError, match="does not match its frozen dependency"):
        e2.canonical_source_matrix_manifest_bytes(stale_upstream_hash)

    orphan_history = copy.deepcopy(manifest)
    orphan_sha = _sha("e")
    orphan_history["histories"].append(
        {
            "path": f"implementation-fixtures/E2-HIST-H{orphan_sha}.csv",
            "history_content_id": f"E2-HIST-H{orphan_sha}",
            "history_table_sha256": orphan_sha,
        }
    )
    with pytest.raises(e2.HistoryGenerationError, match="unreferenced table"):
        e2.canonical_source_matrix_manifest_bytes(orphan_history)

    extra_manifest_field = copy.deepcopy(manifest)
    extra_manifest_field["unhashed_case_setting"] = "must be frozen upstream"
    with pytest.raises(e2.HistoryGenerationError, match="keys invalid"):
        e2.canonical_source_matrix_manifest_bytes(extra_manifest_field)

    changed_dependencies = copy.deepcopy(dependencies)
    changed_dependencies["target_csv_sha256"]["second_read"] = _sha("f")  # type: ignore[index]
    changed_manifest = make_fixture_manifest(changed_dependencies)
    changed_bytes = e2.canonical_source_matrix_manifest_bytes(changed_manifest)
    assert e2.source_matrix_manifest_sha256(changed_manifest) != e2.sha256_bytes(manifest_bytes)
    assert [item["history_content_id"] for item in changed_manifest["histories"]] == [
        item["history_content_id"] for item in manifest["histories"]
    ]
    assert all(
        original["case_id"] != changed["case_id"]
        for original, changed in zip(manifest["cases"], changed_manifest["cases"], strict=True)
    )
    assert changed_bytes != manifest_bytes

    bad = dict(manifest)
    bad["source_matrix_manifest_sha256"] = e2.sha256_bytes(manifest_bytes)
    with pytest.raises(e2.HistoryGenerationError, match="forbidden"):
        e2.canonical_source_matrix_manifest_bytes(bad)
    bad = dict(manifest)
    bad["approval_record_sha256"] = _sha("e")
    with pytest.raises(e2.HistoryGenerationError, match="forbidden"):
        e2.canonical_source_matrix_manifest_bytes(bad)


def test_execution_id_mutates_with_matrix_approval_attempt_or_solver_settings() -> None:
    execution = {
        "source_matrix_manifest_sha256": _sha("a"),
        "approval_record_sha256": _sha("b"),
        "attempt_token": "attempt-001",
        "solver_build_dependencies": {"solver": "synthetic-only"},
        "solver_settings": {"time_step": "unselected"},
        "seeds": {"main": "0"},
        "preregistered_resource_run_settings": {"cpu_budget": "1"},
    }
    original_id = e2.execution_id(execution)
    assert original_id.startswith(
        f"E2-EXEC-M03-S{execution['source_matrix_manifest_sha256']}"
        f"-A{execution['approval_record_sha256']}-C"
    )
    mutations = (
        ("source_matrix_manifest_sha256", _sha("c")),
        ("approval_record_sha256", _sha("d")),
        ("attempt_token", "attempt-002"),
        ("solver_build_dependencies", {"solver": "other synthetic fixture"}),
        ("solver_settings", {"time_step": "another unselected value"}),
        ("seeds", {"main": "1"}),
        ("preregistered_resource_run_settings", {"cpu_budget": "2"}),
    )
    for field, value in mutations:
        changed = copy.deepcopy(execution)
        changed[field] = value
        assert e2.execution_id(changed) != original_id
