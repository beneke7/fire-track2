"""Offline candidate5 v1.2 analyzer fixtures; these bytes are never CFD output."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path

import pytest

from aerial_drop import flutas_source_analyzer as analyzer

SCHEMA_PATH = (
    Path(__file__).parents[1] / "experiments" / "FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md"
)
SCHEMA_SHA256 = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
CANDIDATE_SHA256 = hashlib.sha256(b"offline candidate fixture").hexdigest()
ANALYZER_SHA256 = hashlib.sha256(b"offline analyzer pin").hexdigest()
IMAGE_DIGEST = "sha256:" + hashlib.sha256(b"offline container fixture").hexdigest()
INPUT_HASHES = {
    "cases/offline/dns.in": hashlib.sha256(b"synthetic dns input").hexdigest(),
    "cases/offline/source-boundary.in": hashlib.sha256(b"synthetic input").hexdigest(),
    "cases/offline/vof.in": hashlib.sha256(b"synthetic vof input").hexdigest(),
}
NX, NY, NZ = 160, 84, 40
SLOT_MASKS = tuple(
    frozenset((i, j) for i in range(i0, i0 + 10) for j in range(j0, j0 + 24))
    for i0, j0 in ((20, 10), (70, 10), (20, 50), (70, 50))
)
SLOT_CELLS = frozenset().union(*SLOT_MASKS)
assert sum(map(len, SLOT_MASKS)) == len(SLOT_CELLS) == 960
ACTIVE_INTERVALS = frozenset(range(analyzer.INTERVAL_COUNT))


def _number(value: float) -> str:
    return format(value, ".17g")


def _csv_bytes(header: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _fixture_scan_plan() -> dict[tuple[str, ...], int]:
    """Derive synthetic four-slot counts from dimensions and schedule, not CSV counts."""
    padded_cells = (NX + 2) * (NY + 2)
    interior_cells = NX * NY
    padded_slot_cells = sum(
        1
        for i in range(NX + 2)
        for j in range(NY + 2)
        if (
            NX if i == 0 else 1 if i == NX + 1 else i,
            NY if j == 0 else 1 if j == NY + 1 else j,
        )
        in SLOT_CELLS
    )
    plan: dict[tuple[str, ...], int] = {}
    for table, keys in (
        ("phase", analyzer._expected_audit_keys("phase")),
        ("velocity", analyzer._expected_audit_keys("velocity")),
    ):
        for key in keys:
            _, state, interval, _stage, face, source_class, _detail = key
            if table == "phase":
                if (face, source_class) in {("xlow", "periodic"), ("xhigh", "periodic")}:
                    count = (NY + 2) * (NZ + 2)
                elif (face, source_class) in {("ylow", "periodic"), ("yhigh", "periodic")}:
                    count = NX * (NZ + 2)
                elif (face, source_class) == ("zlow", "bottom_return"):
                    count = interior_cells
                elif source_class in {"active_slot", "inactive_slot"}:
                    active = int(interval) in ACTIVE_INTERVALS
                    selected = source_class == "active_slot"
                    count = len(SLOT_CELLS) if active == selected else 0
                else:
                    count = interior_cells - len(SLOT_CELLS)
            elif source_class == "bottom_return":
                count = padded_cells
            elif source_class in {"active_slot", "inactive_slot"}:
                active = int(state) in ACTIVE_INTERVALS
                selected = source_class == "active_slot"
                count = padded_slot_cells if active == selected else 0
            else:
                count = padded_cells - padded_slot_cells
            plan[key] = count
    return plan


def _phase_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    plan = _fixture_scan_plan()
    for interval in range(analyzer.INTERVAL_COUNT):
        for stage in analyzer.PHASE_STAGES:
            properties = analyzer.PROPERTIES if stage == "pre_momentum" else ("alpha",)
            for face, source_class in analyzer.PHASE_FACE_CLASSES:
                for prop in properties:
                    key = ("phase", str(interval), str(interval), stage, face, source_class, prop)
                    rows.append(
                        {
                            "state_index": str(interval),
                            "transport_interval_index": str(interval),
                            "stage_id": stage,
                            "face": face,
                            "source_class": source_class,
                            "property": prop,
                            "scanned_cells": str(plan[key]),
                            "mismatch_count": "0",
                            "nonfinite_count": "0",
                            "max_abs_error": "0",
                            "first_bad_i": "not_applicable",
                            "first_bad_j": "not_applicable",
                            "first_bad_k": "not_applicable",
                            "expected": "not_applicable",
                            "observed": "not_applicable",
                        }
                    )
    return rows


def _velocity_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    plan = _fixture_scan_plan()

    def add(state: int, interval: int, stage: str) -> None:
        for face, source_class in analyzer.VELOCITY_FACE_CLASSES:
            for component in analyzer.COMPONENTS:
                key = (
                    "velocity",
                    str(state),
                    str(interval),
                    stage,
                    face,
                    source_class,
                    component,
                )
                rows.append(
                    {
                        "state_index": str(state),
                        "transport_interval_index": str(interval),
                        "stage_id": stage,
                        "face": face,
                        "source_class": source_class,
                        "component": component,
                        "scanned_cells": str(plan[key]),
                        "mismatch_count": "0",
                        "nonfinite_count": "0",
                        "max_abs_error": "0",
                        "first_bad_i": "not_applicable",
                        "first_bad_j": "not_applicable",
                        "first_bad_k": "not_applicable",
                        "requested": "not_applicable",
                        "applied": "not_applicable",
                    }
                )

    add(0, -1, "initial_u0")
    for interval in range(analyzer.INTERVAL_COUNT):
        add(interval, interval, "pre_vof")
        add(interval + 1, interval, "projection_override")
        add(interval + 1, interval, "corrected_endpoint")
    return rows


def _timestep_inputs(
    *, sigma: str = "0", factor: str = "0.2", fixed_step: str = "0.0001"
) -> dict[str, object]:
    spacing = 0.025
    vertical_face = [spacing] * 42
    vertical_center = [spacing] * 42
    eps = sys.float_info.epsilon
    small = eps * (10.0 ** (15 / 2.0))
    return {
        "time_scheme": "ab2",
        "time_start_s": "0",
        "real_kind": 8,
        "precision_digits": 15,
        "machine_epsilon": _number(eps),
        "small_s_inv": _number(small),
        "cfl_c": "1",
        "cfl_d": _number(1.0 / 6.0),
        "rho1_kg_m3": "1000",
        "rho2_kg_m3": "1.2",
        "mu1_pa_s": "0.001",
        "mu2_pa_s": "0.000018",
        "dx_m": _number(spacing),
        "dy_m": _number(spacing),
        "dz_m": _number(spacing),
        "dxi_m_inv": _number(1.0 / spacing),
        "dyi_m_inv": _number(1.0 / spacing),
        "dzi_m_inv": _number(1.0 / spacing),
        "dzc_m": [_number(value) for value in vertical_center],
        "dzf_m": [_number(value) for value in vertical_face],
        "dzci_m_inv": [_number(1.0 / value) for value in vertical_center],
        "dzfi_m_inv": [_number(1.0 / value) for value in vertical_face],
        "sigma_n_m": sigma,
        "gravity_m_s2": ["0", "0", "9.81"],
        "fixed_step_factor": factor,
        "fixed_step_s": fixed_step,
    }


def _independent_terms(inputs: dict[str, object], raw_rate: float) -> dict[str, float | bool]:
    """Test-side source-order transcription, separate from analyzer implementation."""
    rho1 = float(inputs["rho1_kg_m3"])
    rho2 = float(inputs["rho2_kg_m3"])
    mu1 = float(inputs["mu1_pa_s"])
    mu2 = float(inputs["mu2_pa_s"])
    dlmin = min(
        1.0 / float(inputs["dxi_m_inv"]),
        1.0 / float(inputs["dyi_m_inv"]),
        1.0 / float(inputs["dzi_m_inv"]),
    )
    dlmin = min(dlmin, min(1.0 / float(value) for value in inputs["dzfi_m_inv"]))
    dlmini = dlmin ** (-1)
    nu = max(mu1 / rho1, mu2 / rho2)
    dtiv = nu * dlmini**2 / float(inputs["cfl_d"])
    sigma = float(inputs["sigma_n_m"])
    capillary = sigma != 0.0
    dtik = (
        math.sqrt(sigma / min(rho1, rho2) * dlmini**3)
        if capillary
        else float(inputs["small_s_inv"])
    )
    gravity = [float(value) for value in inputs["gravity_m_s2"]]
    dtig = math.sqrt(max(abs(value) for value in gravity) * dlmini)
    fallback = raw_rate == 0.0
    used = 1.0 if fallback else raw_rate
    rate = used + dtiv
    dtmax = (
        float(inputs["cfl_c"])
        * 2.0
        * (rate + math.sqrt(rate**2 + 4.0 * (dtig**2 + dtik**2))) ** (-1)
    )
    dtmax = min(dtmax, 1.0 / dtik)
    return {
        "zero_advection_fallback": fallback,
        "dtic_used_s_inv": used,
        "nu_max_m2_s": nu,
        "h_min_m": dlmin,
        "dlmini_m_inv": dlmini,
        "dtiv_s_inv": dtiv,
        "dtik_s_inv": dtik,
        "dtig_s_inv": dtig,
        "capillary_active": capillary,
        "dtmax_s": dtmax,
    }


def _full_timestep_rows(inputs: dict[str, object], raw_rate: float = 192.0) -> list[dict[str, str]]:
    dt = float(inputs["fixed_step_s"])
    t0 = float(inputs["time_start_s"])
    factor = float(inputs["fixed_step_factor"])
    terms = _independent_terms(inputs, raw_rate)
    rows: list[dict[str, str]] = []
    for state in range(analyzer.STATE_COUNT):
        ratio = dt / float(terms["dtmax_s"])
        guard = dt <= factor * float(terms["dtmax_s"])
        rows.append(
            {
                "state_index": str(state),
                "time_s": _number(t0 + state * dt),
                "dt_s": _number(dt),
                "dtic_raw_s_inv": _number(raw_rate),
                "dtic_used_s_inv": _number(float(terms["dtic_used_s_inv"])),
                "zero_advection_fallback": str(bool(terms["zero_advection_fallback"])).lower(),
                "nu_max_m2_s": _number(float(terms["nu_max_m2_s"])),
                "h_min_m": _number(float(terms["h_min_m"])),
                "dlmini_m_inv": _number(float(terms["dlmini_m_inv"])),
                "dtiv_s_inv": _number(float(terms["dtiv_s_inv"])),
                "dtik_s_inv": _number(float(terms["dtik_s_inv"])),
                "dtig_s_inv": _number(float(terms["dtig_s_inv"])),
                "capillary_active": str(bool(terms["capillary_active"])).lower(),
                "dtmax_s": _number(float(terms["dtmax_s"])),
                "fixed_step_factor": _number(factor),
                "dt_over_dtmax": _number(ratio),
                "guard_pass": "not_applicable"
                if state == analyzer.INTERVAL_COUNT
                else str(guard).lower(),
            }
        )
    return rows


def _filter_prefix(
    phase_rows: list[dict[str, str]],
    velocity_rows: list[dict[str, str]],
    timestep_rows: list[dict[str, str]],
    reason: str,
    interval: int,
    stage: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Test-side stop-prefix construction, intentionally independent of analyzer helper."""
    if reason == "normal_completion":
        return phase_rows, velocity_rows, timestep_rows
    if reason == "velocity_audit" and stage == "initial_u0":
        return [], [r for r in velocity_rows if r["stage_id"] == "initial_u0"], []

    def phase_keep(row: dict[str, str]) -> bool:
        row_interval = int(row["transport_interval_index"])
        if row_interval < interval:
            return True
        if row_interval > interval:
            return False
        if reason == "phase_audit":
            return analyzer.PHASE_STAGES.index(row["stage_id"]) <= analyzer.PHASE_STAGES.index(
                stage
            )
        return reason == "velocity_audit" and stage in {
            "projection_override",
            "corrected_endpoint",
        }

    def velocity_keep(row: dict[str, str]) -> bool:
        if row["stage_id"] == "initial_u0":
            return True
        row_interval = int(row["transport_interval_index"])
        if row_interval < interval:
            return True
        if row_interval > interval or reason == "timestep_guard":
            return False
        if reason == "phase_audit":
            return row["stage_id"] == "pre_vof"
        stage_count = {"pre_vof": 1, "projection_override": 2, "corrected_endpoint": 3}[stage]
        order = ("pre_vof", "projection_override", "corrected_endpoint")
        return order.index(row["stage_id"]) < stage_count

    phase = [row for row in phase_rows if phase_keep(row)]
    velocity = [row for row in velocity_rows if velocity_keep(row)]
    timesteps = [row for row in timestep_rows if int(row["state_index"]) <= interval]
    if reason == "timestep_guard":
        timesteps[interval]["guard_pass"] = "false"
    return phase, velocity, timesteps


def _failing_row(row: dict[str, str], *, kind: str, nonfinite: bool = False) -> None:
    row["mismatch_count"] = "0" if nonfinite else "1"
    row["nonfinite_count"] = "1" if nonfinite else "0"
    row["max_abs_error"] = "0" if nonfinite else "1"
    face = row["face"]
    source_class = row["source_class"]
    if face == "xlow":
        location = (0, 0, 0)
    elif face == "xhigh":
        location = (NX + 1, 0, 0)
    elif face == "ylow":
        location = (1, 0, 0)
    elif face == "yhigh":
        location = (1, NY + 1, 0)
    elif face == "zlow":
        location = (0, 0, 0) if kind == "velocity" else (1, 1, 0)
    elif kind == "phase" and source_class in {"active_slot", "inactive_slot"}:
        location = (*min(SLOT_CELLS), NZ + 1)
    elif kind == "phase":
        location = (1, 1, NZ + 1)
    elif source_class in {"active_slot", "inactive_slot"}:
        k = NZ if row["component"] == "w" else NZ + 1
        location = (*min(SLOT_CELLS), k)
    else:
        k = NZ if row["component"] == "w" else NZ + 1
        location = (0, 0, k)
    row["first_bad_i"], row["first_bad_j"], row["first_bad_k"] = map(str, location)
    first, second = ("expected", "observed") if kind == "phase" else ("requested", "applied")
    row[first] = "NaN" if nonfinite else "1"
    row[second] = "+Inf" if nonfinite else "0"


def _clear_failure(row: dict[str, str], *, kind: str) -> None:
    row["mismatch_count"] = "0"
    row["nonfinite_count"] = "0"
    row["max_abs_error"] = "0"
    row["first_bad_i"] = analyzer.NOT_APPLICABLE
    row["first_bad_j"] = analyzer.NOT_APPLICABLE
    row["first_bad_k"] = analyzer.NOT_APPLICABLE
    first, second = ("expected", "observed") if kind == "phase" else ("requested", "applied")
    row[first] = analyzer.NOT_APPLICABLE
    row[second] = analyzer.NOT_APPLICABLE


def _set_finite_failure(row: dict[str, str], *, kind: str, location: tuple[int, int, int]) -> None:
    row["mismatch_count"] = "1"
    row["nonfinite_count"] = "0"
    row["max_abs_error"] = "1"
    row["first_bad_i"], row["first_bad_j"], row["first_bad_k"] = map(str, location)
    first, second = ("expected", "observed") if kind == "phase" else ("requested", "applied")
    row[first] = "1"
    row[second] = "0"


def _manifest_bytes(record: dict[str, object]) -> bytes:
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    )


def _build_bundle(
    *,
    reason: str = "normal_completion",
    interval: int = 0,
    stage: str = analyzer.NOT_APPLICABLE,
    phase_failure: bool = False,
    velocity_failure: bool = False,
    nonfinite_failure: bool = False,
    timestep_inputs: dict[str, object] | None = None,
    raw_rate: float = 192.0,
) -> tuple[bytes, dict[str, bytes], analyzer.ExpectedProvenance]:
    inputs = _timestep_inputs() if timestep_inputs is None else timestep_inputs
    phase_rows = _phase_rows()
    velocity_rows = _velocity_rows()
    timestep_rows = _full_timestep_rows(inputs, raw_rate=raw_rate)
    phase_rows, velocity_rows, timestep_rows = _filter_prefix(
        phase_rows, velocity_rows, timestep_rows, reason, interval, stage
    )
    if phase_failure:
        row = next(
            row
            for row in phase_rows
            if row["transport_interval_index"] == str(interval) and row["stage_id"] == stage
        )
        _failing_row(row, kind="phase", nonfinite=nonfinite_failure)
    if velocity_failure:
        row = next(
            row
            for row in velocity_rows
            if row["transport_interval_index"] == ("-1" if stage == "initial_u0" else str(interval))
            and row["stage_id"] == stage
        )
        _failing_row(row, kind="velocity", nonfinite=nonfinite_failure)

    csv_files = {
        analyzer.PHASE_FILE: _csv_bytes(analyzer.PHASE_HEADER, phase_rows),
        analyzer.VELOCITY_FILE: _csv_bytes(analyzer.VELOCITY_HEADER, velocity_rows),
        analyzer.TIMESTEP_FILE: _csv_bytes(analyzer.TIMESTEP_HEADER, timestep_rows),
    }
    completed = analyzer.INTERVAL_COUNT if reason == "normal_completion" else interval
    stop_state: int | str = analyzer.NOT_APPLICABLE
    stop_interval: int | str = analyzer.NOT_APPLICABLE
    stop_stage = analyzer.NOT_APPLICABLE
    if reason != "normal_completion":
        stop_interval = interval
        stop_state = (
            interval + 1 if stage in {"projection_override", "corrected_endpoint"} else interval
        )
        stop_stage = stage
    final_time = float(inputs["time_start_s"]) + completed * float(inputs["fixed_step_s"])
    record: dict[str, object] = {
        "manifest_schema": analyzer.MANIFEST_SCHEMA,
        "producer_schema": analyzer.PRODUCER_SCHEMA,
        "schema_sha256": SCHEMA_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "image_digest": IMAGE_DIGEST,
        "case_id": "synthetic_four",
        "input_sha256": INPUT_HASHES,
        "analyzer_sha256": ANALYZER_SHA256,
        "run_status": "completed" if reason == "normal_completion" else "failed",
        "solver_exit_code": 0 if reason == "normal_completion" else 19,
        "stop_reason": reason,
        "state_count": analyzer.STATE_COUNT,
        "interval_count": analyzer.INTERVAL_COUNT,
        "completed_interval_count": completed,
        "stop_state_index": stop_state,
        "stop_interval_index": stop_interval,
        "stop_stage_id": stop_stage,
        "final_time_s": _number(final_time),
        "files_sha256": {
            name: hashlib.sha256(data).hexdigest() for name, data in csv_files.items()
        },
        "row_counts": {
            name: len(rows)
            for name, rows in (
                (analyzer.PHASE_FILE, phase_rows),
                (analyzer.VELOCITY_FILE, velocity_rows),
                (analyzer.TIMESTEP_FILE, timestep_rows),
            )
        },
        "scan_order": {
            "phase_property": analyzer.PHASE_SCAN_ORDER,
            "boundary_velocity": analyzer.VELOCITY_SCAN_ORDER,
            "timestep": analyzer.TIMESTEP_SCAN_ORDER,
        },
        "reduction_order": {
            "cell_scan_order": "i,j,k ascending",
            "max_error_order": "first lexicographic location on a tie",
            "floating_point": "candidate real(rp) binary64",
        },
        "timestep_inputs": inputs,
        "resources": {
            "ram_samples": [{"elapsed_s": "1", "rss_bytes": "1024"}],
            "vram_samples": [{"elapsed_s": "1", "used_bytes": "0"}],
            "step_timing_samples": []
            if completed == 0
            else [{"step": 0, "elapsed_s": "1"}, {"step": 1, "elapsed_s": "2"}],
        },
        "pressure_solver": {
            "kind": "direct_fft_xy_tridiagonal_z",
            "iterative_pressure_iterations": "not_applicable",
            "iterative_pressure_residual": "not_applicable",
            "reason": "direct FFT/tridiagonal path and direct continuity/projection evidence",
        },
    }
    manifest = _manifest_bytes(record)
    pins = analyzer.ExpectedProvenance(
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        schema_sha256=SCHEMA_SHA256,
        candidate_sha256=CANDIDATE_SHA256,
        image_digest=IMAGE_DIGEST,
        case_id="synthetic_four",
        input_sha256=INPUT_HASHES,
        analyzer_sha256=ANALYZER_SHA256,
        expected_timestep_inputs=inputs,
        expected_scan_cells=_fixture_scan_plan(),
        slot_masks=SLOT_MASKS,
        active_schedule_indices=ACTIVE_INTERVALS,
    )
    return manifest, csv_files, pins


def _rewrite_csv(data: bytes, header: tuple[str, ...], mutate: callable) -> bytes:
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    mutate(rows)
    return _csv_bytes(header, rows)


def _refresh_bundle(
    manifest_bytes: bytes,
    files: dict[str, bytes],
    pins: analyzer.ExpectedProvenance,
    *,
    recalculate_row_counts: bool = True,
) -> tuple[bytes, dict[str, bytes], analyzer.ExpectedProvenance]:
    manifest = json.loads(manifest_bytes)
    manifest["files_sha256"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    }
    if recalculate_row_counts:
        manifest["row_counts"] = {
            name: len(list(csv.reader(io.StringIO(data.decode("utf-8"))))) - 1
            for name, data in files.items()
        }
    refreshed = _manifest_bytes(manifest)
    refreshed_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(refreshed).hexdigest()}
    )
    return refreshed, files, refreshed_pins


def _analyze(manifest: bytes, files: dict[str, bytes], pins: analyzer.ExpectedProvenance):
    return analyzer.analyze_bundle(manifest, files, pins)


def _audit_failure_bundle(kind: str, *, nonfinite: bool = False):
    if kind == "phase":
        manifest, files, pins = _build_bundle(
            reason="phase_audit",
            interval=0,
            stage="pre_vof_x",
            phase_failure=True,
            nonfinite_failure=nonfinite,
        )
        return (
            manifest,
            files,
            pins,
            analyzer.PHASE_FILE,
            analyzer.PHASE_HEADER,
            "expected",
            "observed",
        )
    manifest, files, pins = _build_bundle(
        reason="velocity_audit",
        interval=0,
        stage="initial_u0",
        velocity_failure=True,
        nonfinite_failure=nonfinite,
    )
    return (
        manifest,
        files,
        pins,
        analyzer.VELOCITY_FILE,
        analyzer.VELOCITY_HEADER,
        "requested",
        "applied",
    )


def test_valid_v12_synthetic_bundle_has_exact_row_counts_and_no_scientific_pass() -> None:
    manifest, files, pins = _build_bundle()

    report = _analyze(manifest, files, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "complete"
    assert report.decision == "not_adjudicated"
    assert report.row_counts == {
        analyzer.PHASE_FILE: 672,
        analyzer.VELOCITY_FILE: 516,
        analyzer.TIMESTEP_FILE: 15,
    }
    assert report.timestep_rows_checked == 15
    timestep = list(csv.DictReader(io.StringIO(files[analyzer.TIMESTEP_FILE].decode())))
    assert "transport_interval_index" not in timestep[0]
    assert timestep[-1]["guard_pass"] == "not_applicable"


@pytest.mark.parametrize("nonfinite", [False, True])
def test_phase_audit_failure_is_preserved_as_a_valid_failed_prefix(nonfinite: bool) -> None:
    manifest, files, pins = _build_bundle(
        reason="phase_audit",
        interval=0,
        stage="pre_vof_x",
        phase_failure=True,
        nonfinite_failure=nonfinite,
    )

    report = _analyze(manifest, files, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "fail"
    assert report.decision == "not_adjudicated"
    assert "SOLVER_RUN_INCOMPLETE" in report.issue_codes
    assert ("PHASE_NONFINITE" if nonfinite else "PHASE_MISMATCH") in report.issue_codes
    assert report.row_counts == {
        analyzer.PHASE_FILE: 8,
        analyzer.VELOCITY_FILE: 24,
        analyzer.TIMESTEP_FILE: 1,
    }


@pytest.mark.parametrize(
    ("expected", "observed"),
    [("NaN", "garbage"), ("garbage", "+Inf")],
)
def test_first_failure_values_are_parsed_independently(expected: str, observed: str) -> None:
    manifest, files, pins = _build_bundle(
        reason="phase_audit",
        interval=0,
        stage="pre_vof_x",
        phase_failure=True,
        nonfinite_failure=True,
    )
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[analyzer.PHASE_FILE].decode())))
    failing = next(row for row in rows if row["nonfinite_count"] == "1")
    failing["expected"] = expected
    failing["observed"] = observed
    changed[analyzer.PHASE_FILE] = _csv_bytes(analyzer.PHASE_HEADER, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == ("INVALID_NUMERIC",)


@pytest.mark.parametrize("kind", ["phase", "velocity"])
@pytest.mark.parametrize(
    ("expected", "observed", "max_error", "mismatch_count", "accepted"),
    [
        ("1", "1.00000000000000001", "1", "1", False),
        ("1e308", "-1e308", "1", "1", False),
        ("1", "0", "0.5", "1", False),
        ("1", "0", "2", "1", False),
        ("1", "0", "1", "1", True),
        ("1", "0", "2", "2", True),
    ],
)
def test_finite_first_failure_pair_matches_binary64_summary(
    kind: str,
    expected: str,
    observed: str,
    max_error: str,
    mismatch_count: str,
    accepted: bool,
) -> None:
    manifest, files, pins, filename, header, first, second = _audit_failure_bundle(kind)
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[filename].decode())))
    rows[0].update(
        {
            first: expected,
            second: observed,
            "max_abs_error": max_error,
            "mismatch_count": mismatch_count,
            "nonfinite_count": "0",
        }
    )
    changed[filename] = _csv_bytes(header, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    if accepted:
        assert report.structural_disposition == "complete"
        assert report.evidence_disposition == "fail"
        assert f"{kind.upper()}_MISMATCH" in report.issue_codes
        assert report.decision == "not_adjudicated"
    else:
        assert report.structural_disposition == "fail"
        assert report.issue_codes == ("SCAN_ERROR",)


@pytest.mark.parametrize("kind", ["phase", "velocity"])
@pytest.mark.parametrize(("expected", "observed"), [("NaN", "1"), ("1", "-Inf")])
def test_mixed_nonfinite_first_failure_with_finite_mismatch_remains_valid(
    kind: str, expected: str, observed: str
) -> None:
    manifest, files, pins, filename, header, first, second = _audit_failure_bundle(
        kind, nonfinite=True
    )
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[filename].decode())))
    rows[0].update(
        {
            first: expected,
            second: observed,
            "max_abs_error": "1",
            "mismatch_count": "1",
            "nonfinite_count": "1",
        }
    )
    changed[filename] = _csv_bytes(header, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "fail"
    assert {f"{kind.upper()}_MISMATCH", f"{kind.upper()}_NONFINITE"}.issubset(report.issue_codes)
    assert "SOLVER_RUN_INCOMPLETE" in report.issue_codes


@pytest.mark.parametrize("kind", ["phase", "velocity"])
def test_finite_first_pair_with_later_nonfinite_cells_remains_valid(kind: str) -> None:
    manifest, files, pins, filename, header, _first, _second = _audit_failure_bundle(kind)
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[filename].decode())))
    rows[0]["nonfinite_count"] = "1"
    changed[filename] = _csv_bytes(header, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "fail"
    assert {f"{kind.upper()}_MISMATCH", f"{kind.upper()}_NONFINITE"}.issubset(report.issue_codes)


def test_phase_failure_location_must_belong_to_its_declared_face() -> None:
    manifest, files, pins = _build_bundle(
        reason="phase_audit",
        interval=0,
        stage="pre_vof_x",
        phase_failure=True,
    )
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[analyzer.PHASE_FILE].decode())))
    rows[0]["first_bad_i"] = "20"
    changed[analyzer.PHASE_FILE] = _csv_bytes(analyzer.PHASE_HEADER, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == ("INVALID_INDEX",)


def test_phase_slot_failure_location_must_belong_to_pinned_mask() -> None:
    manifest, files, pins = _build_bundle(
        reason="phase_audit",
        interval=0,
        stage="pre_vof_x",
        phase_failure=True,
    )
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[analyzer.PHASE_FILE].decode())))
    _clear_failure(rows[0], kind="phase")
    target = next(
        row for row in rows if row["face"] == "zhigh" and row["source_class"] == "active_slot"
    )
    _set_finite_failure(target, kind="phase", location=(1, 1, NZ + 1))
    changed[analyzer.PHASE_FILE] = _csv_bytes(analyzer.PHASE_HEADER, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == ("INVALID_INDEX",)


def test_velocity_w_failure_location_uses_the_normal_face_plane() -> None:
    manifest, files, pins = _build_bundle(
        reason="velocity_audit",
        interval=0,
        stage="projection_override",
        velocity_failure=True,
    )
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[analyzer.VELOCITY_FILE].decode())))
    original = next(
        row
        for row in rows
        if row["stage_id"] == "projection_override"
        and row["face"] == "zhigh"
        and row["source_class"] == "active_slot"
        and row["component"] == "u"
    )
    _clear_failure(original, kind="velocity")
    target = next(
        row
        for row in rows
        if row["stage_id"] == "projection_override"
        and row["face"] == "zhigh"
        and row["source_class"] == "active_slot"
        and row["component"] == "w"
    )
    _set_finite_failure(target, kind="velocity", location=(*min(SLOT_CELLS), NZ + 1))
    changed[analyzer.VELOCITY_FILE] = _csv_bytes(analyzer.VELOCITY_HEADER, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == ("INVALID_INDEX",)


def test_initial_velocity_failure_has_no_timestep_join_or_rows() -> None:
    manifest, files, pins = _build_bundle(
        reason="velocity_audit",
        stage="initial_u0",
        velocity_failure=True,
        nonfinite_failure=True,
    )

    report = _analyze(manifest, files, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "fail"
    assert "VELOCITY_NONFINITE" in report.issue_codes
    assert report.row_counts == {
        analyzer.PHASE_FILE: 0,
        analyzer.VELOCITY_FILE: 12,
        analyzer.TIMESTEP_FILE: 0,
    }


@pytest.mark.parametrize(
    ("reason", "stage", "phase_count", "velocity_count", "timestep_count"),
    [
        ("timestep_guard", analyzer.NOT_APPLICABLE, 0, 12, 1),
        ("phase_audit", "pre_vof_y", 64, 60, 2),
        ("velocity_audit", "pre_vof", 0, 24, 1),
        ("velocity_audit", "projection_override", 48, 36, 1),
        ("velocity_audit", "corrected_endpoint", 48, 48, 1),
    ],
)
def test_v12_controlled_stop_prefix_row_counts(
    reason: str,
    stage: str,
    phase_count: int,
    velocity_count: int,
    timestep_count: int,
) -> None:
    inputs = _timestep_inputs(factor="0.0001") if reason == "timestep_guard" else _timestep_inputs()
    manifest, files, pins = _build_bundle(
        reason=reason,
        interval=0 if reason != "phase_audit" else 1,
        stage=stage,
        phase_failure=reason == "phase_audit",
        velocity_failure=reason == "velocity_audit",
        timestep_inputs=inputs,
    )

    report = _analyze(manifest, files, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "fail"
    assert report.decision == "not_adjudicated"
    assert report.row_counts == {
        analyzer.PHASE_FILE: phase_count,
        analyzer.VELOCITY_FILE: velocity_count,
        analyzer.TIMESTEP_FILE: timestep_count,
    }


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "PHASE_KEYS"),
        ("duplicate", "DUPLICATE_KEY"),
        ("orphan", "ORPHAN_PHASE_JOIN"),
        ("unknown_stage", "UNKNOWN_STAGE"),
        ("unknown_face_class", "INVALID_FACE_CLASS"),
        ("nan", "INVALID_NUMERIC"),
        ("inf", "INVALID_NUMERIC"),
        ("wrong_scan_count", "SCAN_CELL_COUNT"),
        ("sentinel", "NOT_APPLICABLE"),
    ],
)
def test_phase_wire_and_key_violations_fail_closed(mutation: str, expected_code: str) -> None:
    manifest, files, pins = _build_bundle()
    changed = dict(files)
    rows = list(csv.DictReader(io.StringIO(changed[analyzer.PHASE_FILE].decode())))
    if mutation == "missing":
        rows.pop(0)
    elif mutation == "duplicate":
        rows.append(dict(rows[0]))
    elif mutation == "orphan":
        rows[0]["state_index"] = "1"
    elif mutation == "unknown_stage":
        rows[0]["stage_id"] = "pre_vof_q"
    elif mutation == "unknown_face_class":
        rows[0]["source_class"] = "other_inflow"
    elif mutation == "nan":
        rows[0]["max_abs_error"] = "NaN"
    elif mutation == "inf":
        rows[0]["max_abs_error"] = "+Inf"
    elif mutation == "wrong_scan_count":
        rows[0]["scanned_cells"] = str(int(rows[0]["scanned_cells"]) + 1)
    else:
        rows[0]["observed"] = "0"
    changed[analyzer.PHASE_FILE] = _csv_bytes(analyzer.PHASE_HEADER, rows)
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.evidence_disposition == "fail"
    assert report.decision == "not_adjudicated"
    assert expected_code in report.issue_codes


def test_velocity_unknown_stage_and_schema_forbidden_class_fail_closed() -> None:
    manifest, files, pins = _build_bundle()
    changed = dict(files)
    changed[analyzer.VELOCITY_FILE] = _rewrite_csv(
        changed[analyzer.VELOCITY_FILE],
        analyzer.VELOCITY_HEADER,
        lambda rows: rows[0].__setitem__("source_class", "periodic"),
    )
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)
    report = _analyze(manifest, changed, pins)
    assert "INVALID_FACE_CLASS" in report.issue_codes


def test_manifest_duplicate_keys_noncanonical_bytes_and_wrong_schema_version_fail_closed() -> None:
    manifest, files, pins = _build_bundle()
    duplicate = manifest.rstrip()[:-1] + b',"producer_schema":"candidate5-observability-v1.2"}\n'
    duplicate_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(duplicate).hexdigest()}
    )
    assert _analyze(duplicate, files, duplicate_pins).issue_codes == ("DUPLICATE_JSON_KEY",)

    pretty = json.dumps(json.loads(manifest), indent=2).encode() + b"\n"
    pretty_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(pretty).hexdigest()}
    )
    assert _analyze(pretty, files, pretty_pins).issue_codes == ("MANIFEST_ENCODING",)

    changed, files, pins = _refresh_bundle(manifest, dict(files), pins)
    record = json.loads(changed)
    record["manifest_schema"] = "candidate5-run-manifest-v1"
    wrong_version = _manifest_bytes(record)
    wrong_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(wrong_version).hexdigest()}
    )
    assert _analyze(wrong_version, files, wrong_pins).issue_codes == ("MANIFEST_VERSION",)


def test_manifest_count_mismatch_and_schema_hash_pin_fail_closed() -> None:
    manifest, files, pins = _build_bundle()
    changed_record = json.loads(manifest)
    changed_record["row_counts"][analyzer.PHASE_FILE] += 1
    changed = _manifest_bytes(changed_record)
    changed_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(changed).hexdigest()}
    )
    assert _analyze(changed, files, changed_pins).issue_codes == ("ROW_COUNT_MISMATCH",)

    wrong_schema = dict(changed_record)
    wrong_schema["schema_sha256"] = hashlib.sha256(b"wrong schema").hexdigest()
    wrong_bytes = _manifest_bytes(wrong_schema)
    wrong_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(wrong_bytes).hexdigest()}
    )
    assert _analyze(wrong_bytes, files, wrong_pins).issue_codes == ("PROVENANCE_MISMATCH",)


def test_tampered_timestep_intermediate_or_inverse_is_rejected_exactly() -> None:
    manifest, files, pins = _build_bundle()
    changed = dict(files)
    changed[analyzer.TIMESTEP_FILE] = _rewrite_csv(
        changed[analyzer.TIMESTEP_FILE],
        analyzer.TIMESTEP_HEADER,
        lambda rows: rows[0].__setitem__(
            "dtiv_s_inv", _number(float(rows[0]["dtiv_s_inv"]) * 1.01)
        ),
    )
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)
    assert _analyze(manifest, changed, pins).issue_codes == ("TIMESTEP_TERM_MISMATCH",)

    changed_inputs = dict(pins.expected_timestep_inputs)
    changed_inputs["dxi_m_inv"] = "39"
    record = json.loads(manifest)
    record["timestep_inputs"] = changed_inputs
    wrong_input_bytes = _manifest_bytes(record)
    wrong_pins = analyzer.ExpectedProvenance(
        **{
            **pins.__dict__,
            "manifest_sha256": hashlib.sha256(wrong_input_bytes).hexdigest(),
            "expected_timestep_inputs": changed_inputs,
        }
    )
    assert _analyze(wrong_input_bytes, changed, wrong_pins).issue_codes == (
        "TIMESTEP_INVERSE_MISMATCH",
    )


def test_zero_rate_fallback_capillary_terms_and_terminal_sentinel() -> None:
    inputs = _timestep_inputs(sigma="0.072", fixed_step="0.000001")
    manifest, files, pins = _build_bundle(timestep_inputs=inputs, raw_rate=0.0)

    report = _analyze(manifest, files, pins)

    assert report.structural_disposition == "complete"
    assert report.evidence_disposition == "complete"
    parsed = list(csv.DictReader(io.StringIO(files[analyzer.TIMESTEP_FILE].decode())))
    assert parsed[0]["zero_advection_fallback"] == "true"
    assert parsed[0]["capillary_active"] == "true"
    assert parsed[-1]["guard_pass"] == "not_applicable"
    assert parsed[0]["dlmini_m_inv"] == _number(1.0 / float(parsed[0]["h_min_m"]))


def test_nonfinite_timestep_values_are_rejected_not_encoded_as_guard_stop() -> None:
    manifest, files, pins = _build_bundle()
    changed = dict(files)
    changed[analyzer.TIMESTEP_FILE] = _rewrite_csv(
        changed[analyzer.TIMESTEP_FILE],
        analyzer.TIMESTEP_HEADER,
        lambda rows: rows[0].__setitem__("dtiv_s_inv", "NaN"),
    )
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)
    report = _analyze(manifest, changed, pins)
    assert "INVALID_NUMERIC" in report.issue_codes


def test_finite_binary64_intermediate_overflow_returns_structured_failure() -> None:
    manifest, files, pins = _build_bundle()
    changed = dict(files)
    changed[analyzer.TIMESTEP_FILE] = _rewrite_csv(
        changed[analyzer.TIMESTEP_FILE],
        analyzer.TIMESTEP_HEADER,
        lambda rows: rows[0].__setitem__("dtic_raw_s_inv", "1e200"),
    )
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == ("TIMESTEP_ARITHMETIC",)


def test_finite_decimal_outside_binary64_range_is_rejected() -> None:
    manifest, files, pins = _build_bundle()
    changed = dict(files)
    changed[analyzer.TIMESTEP_FILE] = _rewrite_csv(
        changed[analyzer.TIMESTEP_FILE],
        analyzer.TIMESTEP_HEADER,
        lambda rows: rows[0].__setitem__("dtic_raw_s_inv", "1e400"),
    )
    manifest, changed, pins = _refresh_bundle(manifest, changed, pins)

    report = _analyze(manifest, changed, pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == ("NUMERIC_RANGE",)


@pytest.mark.parametrize(
    ("spacing", "inverse", "expected_code"),
    [
        ("1e400", "1", "NUMERIC_RANGE"),
        ("0", "1", "TIMESTEP_INPUTS"),
        ("5e-309", "1.7976931348623157e308", "TIMESTEP_INPUTS"),
    ],
)
def test_invalid_spacing_or_reciprocal_fails_structurally(
    spacing: str, inverse: str, expected_code: str
) -> None:
    manifest, files, pins = _build_bundle()
    inputs = dict(pins.expected_timestep_inputs)
    inputs["dx_m"] = spacing
    inputs["dxi_m_inv"] = inverse
    record = json.loads(manifest)
    record["timestep_inputs"] = inputs
    changed_manifest = _manifest_bytes(record)
    changed_pins = analyzer.ExpectedProvenance(
        **{
            **pins.__dict__,
            "manifest_sha256": hashlib.sha256(changed_manifest).hexdigest(),
            "expected_timestep_inputs": inputs,
        }
    )

    report = _analyze(changed_manifest, files, changed_pins)

    assert report.structural_disposition == "fail"
    assert report.issue_codes == (expected_code,)


def test_manifest_timestep_input_pin_is_required() -> None:
    manifest, files, pins = _build_bundle()
    changed = json.loads(manifest)
    changed["timestep_inputs"]["fixed_step_s"] = "0.0002"
    bytes_changed = _manifest_bytes(changed)
    changed_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(bytes_changed).hexdigest()}
    )
    assert _analyze(bytes_changed, files, changed_pins).issue_codes == ("TIMESTEP_INPUT_PIN",)


def test_missing_output_tampered_output_hash_and_input_pin_fail_closed() -> None:
    manifest, files, pins = _build_bundle()
    omitted = dict(files)
    omitted.pop(analyzer.VELOCITY_FILE)
    assert _analyze(manifest, omitted, pins).issue_codes == ("OUTPUT_FILE_SET",)

    changed = dict(files)
    changed[analyzer.VELOCITY_FILE] += b"\n"
    assert _analyze(manifest, changed, pins).issue_codes == ("OUTPUT_HASH",)

    wrong_hashes = {"cases/offline/source-boundary.in": hashlib.sha256(b"other").hexdigest()}
    wrong_pins = analyzer.ExpectedProvenance(**{**pins.__dict__, "input_sha256": wrong_hashes})
    assert _analyze(manifest, files, wrong_pins).issue_codes == ("PROVENANCE_MISMATCH",)


def test_expected_scan_plan_must_cover_exact_full_v12_keys() -> None:
    manifest, files, pins = _build_bundle()
    reduced = dict(pins.expected_scan_cells)
    reduced.pop(next(iter(reduced)))
    changed_pins = analyzer.ExpectedProvenance(**{**pins.__dict__, "expected_scan_cells": reduced})
    assert _analyze(manifest, files, changed_pins).issue_codes == ("SCAN_PLAN",)


def test_resource_step_indices_are_json_integers_and_empty_only_at_zero_completion() -> None:
    manifest, files, pins = _build_bundle()
    record = json.loads(manifest)
    record["resources"]["step_timing_samples"][0]["step"] = "0"
    invalid = _manifest_bytes(record)
    invalid_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(invalid).hexdigest()}
    )
    assert _analyze(invalid, files, invalid_pins).issue_codes == ("RESOURCE_RECORDS",)


def test_source_analyzer_does_not_accept_scientific_or_execution_passes() -> None:
    manifest, files, pins = _build_bundle()
    record = json.loads(manifest)
    record["stop_reason"] = "user_stop"
    invalid = _manifest_bytes(record)
    invalid_pins = analyzer.ExpectedProvenance(
        **{**pins.__dict__, "manifest_sha256": hashlib.sha256(invalid).hexdigest()}
    )
    report = _analyze(invalid, files, invalid_pins)
    assert report.decision == "not_adjudicated"
    assert report.structural_disposition == "fail"
