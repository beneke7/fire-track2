"""Exact-rational, implementation-only evaluator for proposed E2 M03 histories.

This module generates in-memory source-table fixtures and implements the
canonical identity layers specified by M03.  It does not approve the proposed
scenario family or create solver-ready cases.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

METHOD_REVISION = "M03"
RUN_START_S = Fraction(Decimal("-0.03"))
RUN_END_S = Fraction(Decimal("0.5"))
DIAGNOSTIC_TIME_S = Fraction(Decimal("0.5"))
DELTA_STRINGS = ("-0.03", "0", "0.03")
RESIDUAL_STRINGS = ("-1", "0", "1")
READ_IDS = ("primary", "second_read")

PRIMARY_COLUMNS = (
    "time_s",
    "u_l_m_s",
    "figure_read_bound_time_s",
    "figure_read_bound_u_l_m_s",
)
SECOND_READ_COLUMNS = PRIMARY_COLUMNS + (
    "source_pdf_sha256",
    "pdf_page",
    "journal_page",
    "figure",
    "series_id",
    "source_pixel_x",
    "source_pixel_y",
    "sample_kind",
    "read_method",
)
NUMERIC_SOURCE_COLUMNS = frozenset(
    {
        "time_s",
        "u_l_m_s",
        "figure_read_bound_time_s",
        "figure_read_bound_u_l_m_s",
        "pdf_page",
        "journal_page",
        "figure",
        "source_pixel_x",
        "source_pixel_y",
    }
)
EXPECTED_SOURCE_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"


class HistoryGenerationError(ValueError):
    """Raised when source data or an exact-to-binary64 projection is invalid."""


class FloatKnotCollision(HistoryGenerationError):
    """Distinct exact time knots project to the same binary64 value."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def history_content_id(table_bytes: bytes) -> str:
    return f"E2-HIST-H{sha256_bytes(table_bytes)}"


def _decimal_fraction(token: str, *, field: str) -> Fraction:
    if token != token.strip() or not token:
        raise HistoryGenerationError(f"invalid whitespace or empty numeric token in {field}")
    try:
        number = Decimal(token)
    except InvalidOperation as exc:
        raise HistoryGenerationError(f"invalid base-10 Decimal in {field}: {token!r}") from exc
    if not number.is_finite():
        raise HistoryGenerationError(f"non-finite Decimal in {field}: {token!r}")
    return Fraction(number)


@dataclass(frozen=True)
class SourceHistory:
    read_id: str
    times: tuple[Fraction, ...]
    velocities: tuple[Fraction, ...]
    velocity_bounds: tuple[Fraction, ...]
    source_sha256: str

    def value(self, source_time_s: Fraction) -> Fraction:
        return _interpolate(self.times, self.velocities, source_time_s)

    def tapered_bound(self, source_time_s: Fraction) -> Fraction:
        # The M03 residual is anchored to zero at the axes origin; the CSV
        # bound in its t=0 row is intentionally excluded.
        taper_times = (Fraction(0), *self.times[1:])
        taper_values = (Fraction(0), *self.velocity_bounds[1:])
        return _interpolate(taper_times, taper_values, source_time_s)


def parse_source_csv_bytes(data: bytes, *, read_id: str) -> SourceHistory:
    """Decode one pinned source CSV strictly and parse decimal tokens exactly."""
    if read_id not in READ_IDS:
        raise HistoryGenerationError(f"unknown read ID: {read_id!r}")
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HistoryGenerationError("source CSV is not strict UTF-8") from exc

    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    expected_columns = PRIMARY_COLUMNS if read_id == "primary" else SECOND_READ_COLUMNS
    if tuple(reader.fieldnames or ()) != expected_columns:
        raise HistoryGenerationError(f"unexpected {read_id} source columns: {reader.fieldnames!r}")

    rows: list[dict[str, str]] = []
    for line_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise HistoryGenerationError(f"malformed CSV row {line_number}")
        if any(row[column] == "" for column in expected_columns):
            raise HistoryGenerationError(f"empty CSV token on row {line_number}")
        rows.append(row)
    if len(rows) != 51:
        raise HistoryGenerationError(f"expected 51 source rows, received {len(rows)}")

    numeric_rows: list[dict[str, Fraction]] = []
    for line_number, row in enumerate(rows, start=2):
        numeric_row: dict[str, Fraction] = {}
        for column in NUMERIC_SOURCE_COLUMNS.intersection(row):
            numeric_row[column] = _decimal_fraction(
                row[column], field=f"{column} at CSV row {line_number}"
            )
        numeric_rows.append(numeric_row)

    if read_id == "second_read":
        if any(row["source_pdf_sha256"] != EXPECTED_SOURCE_PDF_SHA256 for row in rows):
            raise HistoryGenerationError("second-read PDF hash metadata does not match M03")
        fixed_metadata = {
            "pdf_page": Fraction(5),
            "journal_page": Fraction(1519),
            "figure": Fraction(4),
        }
        if any(
            numeric_row[column] != expected
            for numeric_row in numeric_rows
            for column, expected in fixed_metadata.items()
        ):
            raise HistoryGenerationError("second-read page/figure metadata does not match M03")
        if any(row["series_id"] != "dash8_blue" for row in rows):
            raise HistoryGenerationError("unexpected second-read series metadata")

    times = tuple(row["time_s"] for row in numeric_rows)
    velocities = tuple(row["u_l_m_s"] for row in numeric_rows)
    time_bounds = tuple(row["figure_read_bound_time_s"] for row in numeric_rows)
    velocity_bounds = tuple(row["figure_read_bound_u_l_m_s"] for row in numeric_rows)
    expected_times = tuple(Fraction(i, 10) for i in range(51))
    if times != expected_times:
        raise HistoryGenerationError("source time knots must be the exact 0.0..5.0 s grid")
    if time_bounds != (Fraction(3, 100),) * 51:
        raise HistoryGenerationError("source time-read allowances must all be exactly 0.03 s")
    if velocities[0] != 0 or any(bound < 0 for bound in velocity_bounds):
        raise HistoryGenerationError("source origin or ordinate-bound values are invalid")

    return SourceHistory(
        read_id=read_id,
        times=times,
        velocities=velocities,
        velocity_bounds=velocity_bounds,
        source_sha256=sha256_bytes(data),
    )


def read_source_history(path: str | Path, *, read_id: str) -> SourceHistory:
    return parse_source_csv_bytes(Path(path).read_bytes(), read_id=read_id)


def _interpolate(xs: Sequence[Fraction], ys: Sequence[Fraction], x: Fraction) -> Fraction:
    if len(xs) != len(ys) or not xs:
        raise HistoryGenerationError("interpolation knot arrays are invalid")
    if x < xs[0] or x > xs[-1]:
        raise HistoryGenerationError(f"requested source time outside support: {x}")
    position = bisect.bisect_right(xs, x) - 1
    if position == len(xs) - 1 or x == xs[position]:
        return ys[position]
    left_x, right_x = xs[position], xs[position + 1]
    left_y, right_y = ys[position], ys[position + 1]
    return left_y + (x - left_x) * (right_y - left_y) / (right_x - left_x)


@dataclass(frozen=True)
class Scenario:
    read_id: str
    delta_text: str
    residual_text: str

    def __post_init__(self) -> None:
        if self.read_id not in READ_IDS:
            raise HistoryGenerationError(f"unknown scenario read ID: {self.read_id!r}")
        if self.delta_text not in DELTA_STRINGS:
            raise HistoryGenerationError(f"unsupported scenario delta: {self.delta_text!r}")
        if self.residual_text not in RESIDUAL_STRINGS:
            raise HistoryGenerationError(
                f"unsupported residual coefficient: {self.residual_text!r}"
            )

    @property
    def delta(self) -> Fraction:
        return _decimal_fraction(self.delta_text, field="scenario delta")

    @property
    def residual(self) -> Fraction:
        return _decimal_fraction(self.residual_text, field="scenario residual")

    @property
    def read_tag(self) -> str:
        return {"primary": "P", "second_read": "R2"}[self.read_id]

    @property
    def delta_tag(self) -> str:
        return {"-0.03": "M030", "0": "Z000", "0.03": "P030"}[self.delta_text]

    @property
    def residual_tag(self) -> str:
        return {"-1": "M1", "0": "Z0", "1": "P1"}[self.residual_text]

    def as_record(self) -> dict[str, str]:
        return {
            "read": self.read_id,
            "delta_s": self.delta_text,
            "residual_coefficient": self.residual_text,
        }


def proposed_scenarios() -> tuple[Scenario, ...]:
    return tuple(
        Scenario(read_id, delta, residual)
        for read_id in READ_IDS
        for delta in DELTA_STRINGS
        for residual in RESIDUAL_STRINGS
    )


def scenario_case_id(scenario: Scenario, upstream_sha256: str, table_sha256: str) -> str:
    _require_sha256(upstream_sha256, field="upstream digest")
    _require_sha256(table_sha256, field="history table digest")
    return (
        f"E2-DIG-0.5-M03-{scenario.read_tag}-D{scenario.delta_tag}"
        f"-A{scenario.residual_tag}-U{upstream_sha256}-H{table_sha256}"
    )


@dataclass(frozen=True)
class ExactKnot:
    time_s: Fraction
    velocity_m_s: Fraction


@dataclass(frozen=True)
class ProjectionDiagnostics:
    max_time_roundtrip_error_s: float
    max_velocity_roundtrip_error_m_s: float
    interior_query_count: int
    max_table_evaluator_error_m_s: float
    max_query_projection_error_m_s: float


@dataclass(frozen=True)
class IntegralDiagnostics:
    integral_velocity_m: Fraction
    integral_velocity_squared_m2_per_s: Fraction
    max_velocity_simpson_difference: Fraction
    max_velocity_squared_simpson_difference: Fraction


@dataclass(frozen=True)
class GeneratedHistory:
    scenario: Scenario
    exact_knots: tuple[ExactKnot, ...]
    float_knots: tuple[tuple[float, float], ...]
    table_bytes: bytes
    table_sha256: str
    history_content_id: str
    projection: ProjectionDiagnostics
    integrals: IntegralDiagnostics


def _q(source: SourceHistory, residual: Fraction, source_time_s: Fraction) -> Fraction:
    return source.value(source_time_s) + residual * source.tapered_bound(source_time_s)


def exact_source_value(
    source: SourceHistory, scenario: Scenario, simulation_time_s: Fraction
) -> Fraction:
    """Evaluate M03's shifted, tapered, exact, nonnegative history."""
    source_time_s = simulation_time_s + scenario.delta
    if source_time_s < 0:
        return Fraction(0)
    if source_time_s > source.times[-1]:
        raise HistoryGenerationError("requested source evaluation exceeds the 5 s CSV support")
    return max(Fraction(0), _q(source, scenario.residual, source_time_s))


def _strict_interior_roots(source: SourceHistory, residual: Fraction) -> tuple[Fraction, ...]:
    roots: list[Fraction] = []
    for left_time, right_time in zip(source.times, source.times[1:]):
        left_q = _q(source, residual, left_time)
        right_q = _q(source, residual, right_time)
        if left_q * right_q < 0:
            root = left_time - left_q * (right_time - left_time) / (right_q - left_q)
            if not left_time < root < right_time:
                raise HistoryGenerationError("strict sign-change root was not interior")
            roots.append(root)
    return tuple(roots)


def _exact_history_knots(source: SourceHistory, scenario: Scenario) -> tuple[ExactKnot, ...]:
    delta = scenario.delta
    source_breaks = (*source.times, *_strict_interior_roots(source, scenario.residual))
    times = {RUN_START_S, RUN_END_S, Fraction(0)}
    times.update(
        source_time - delta
        for source_time in source_breaks
        if RUN_START_S <= source_time - delta <= RUN_END_S
    )
    source_origin = -delta
    if RUN_START_S <= source_origin <= RUN_END_S:
        times.add(source_origin)
    ordered_times = sorted(times)
    if len(ordered_times) < 2:
        raise HistoryGenerationError("run-window knot union is incomplete")
    return tuple(
        ExactKnot(time_s, exact_source_value(source, scenario, time_s)) for time_s in ordered_times
    )


def _float_projection(knots: Sequence[ExactKnot]) -> tuple[tuple[float, float], ...]:
    projected: list[tuple[float, float]] = []
    seen_times: dict[float, Fraction] = {}
    for knot in knots:
        time_float = float(knot.time_s)
        velocity_float = float(knot.velocity_m_s)
        if not math.isfinite(time_float) or not math.isfinite(velocity_float):
            raise HistoryGenerationError("non-finite binary64 projection")
        prior_time = seen_times.get(time_float)
        if prior_time is not None and prior_time != knot.time_s:
            raise FloatKnotCollision("FLOAT_KNOT_COLLISION")
        seen_times[time_float] = knot.time_s
        if velocity_float < 0.0:
            raise HistoryGenerationError("projected speed is negative")
        projected.append((time_float, velocity_float))
    if any(right[0] <= left[0] for left, right in zip(projected, projected[1:])):
        raise FloatKnotCollision("FLOAT_KNOT_COLLISION")
    return tuple(projected)


def _format_binary64(value: float) -> str:
    if not math.isfinite(value):
        raise HistoryGenerationError("cannot serialize non-finite binary64 value")
    if value == 0.0:
        return "0"
    return format(value, ".17g")


def canonical_history_table_bytes(knots: Sequence[tuple[float, float]]) -> bytes:
    if len(knots) < 2:
        raise HistoryGenerationError("history table needs at least two knots")
    lines = ["time_s,u_l_m_s"]
    previous: float | None = None
    for time_s, velocity_m_s in knots:
        if not math.isfinite(time_s) or not math.isfinite(velocity_m_s):
            raise HistoryGenerationError("cannot serialize non-finite history knot")
        if previous is not None and time_s <= previous:
            raise FloatKnotCollision("binary64 table times must be unique and increasing")
        if velocity_m_s < 0:
            raise HistoryGenerationError("history table speed cannot be negative")
        lines.append(f"{_format_binary64(time_s)},{_format_binary64(velocity_m_s)}")
        previous = time_s
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_canonical_history_table_bytes(data: bytes) -> tuple[tuple[float, float], ...]:
    """Parse and revalidate the exact M03 history-table byte representation."""
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HistoryGenerationError("history table is not strict UTF-8") from exc
    if decoded.startswith("\ufeff") or "\r" in decoded or not decoded.endswith("\n"):
        raise HistoryGenerationError("history table must be UTF-8 without BOM, LF-only, final LF")
    if decoded.endswith("\n\n"):
        raise HistoryGenerationError("history table must end with exactly one LF")
    lines = decoded[:-1].split("\n")
    if not lines or lines[0] != "time_s,u_l_m_s" or len(lines) < 3:
        raise HistoryGenerationError("history table header or row count is invalid")
    knots: list[tuple[float, float]] = []
    for line_number, line in enumerate(lines[1:], start=2):
        fields = line.split(",")
        if len(fields) != 2 or not all(fields):
            raise HistoryGenerationError(f"malformed history table row {line_number}")
        try:
            time_s, velocity_m_s = float(fields[0]), float(fields[1])
        except ValueError as exc:
            raise HistoryGenerationError(
                f"invalid binary64 token on history row {line_number}"
            ) from exc
        if not math.isfinite(time_s) or not math.isfinite(velocity_m_s) or velocity_m_s < 0.0:
            raise HistoryGenerationError(f"invalid history values on row {line_number}")
        if knots and time_s <= knots[-1][0]:
            raise FloatKnotCollision("binary64 table times must be unique and increasing")
        knots.append((time_s, velocity_m_s))
    parsed = tuple(knots)
    if canonical_history_table_bytes(parsed) != data:
        raise HistoryGenerationError("history table bytes are not in canonical .17g form")
    return parsed


def _runtime_table_value(knots: Sequence[tuple[float, float]], query_s: float) -> float:
    times = [knot[0] for knot in knots]
    if not math.isfinite(query_s) or query_s < times[0] or query_s > times[-1]:
        raise HistoryGenerationError("runtime table query lies outside the common run window")
    position = bisect.bisect_right(times, query_s) - 1
    if query_s == times[position] or position == len(knots) - 1:
        return knots[position][1]
    left_time, left_value = knots[position]
    right_time, right_value = knots[position + 1]
    fraction = (query_s - left_time) / (right_time - left_time)
    return left_value + fraction * (right_value - left_value)


def _runtime_segment_endpoints(
    knots: Sequence[tuple[float, float]], query_s: float
) -> tuple[float, float]:
    position = max(0, bisect.bisect_right([knot[0] for knot in knots], query_s) - 1)
    right_position = min(len(knots) - 1, position + 1)
    return knots[position][1], knots[right_position][1]


def _roundoff_bound(scale: float) -> Fraction:
    return Fraction.from_float(16.0 * math.ulp(scale))


def _projection_diagnostics(
    source: SourceHistory,
    scenario: Scenario,
    exact_knots: Sequence[ExactKnot],
    float_knots: Sequence[tuple[float, float]],
) -> ProjectionDiagnostics:
    max_time_error = 0.0
    max_velocity_error = 0.0
    for exact_knot, (time_float, velocity_float) in zip(exact_knots, float_knots, strict=True):
        time_error = abs(Fraction.from_float(time_float) - exact_knot.time_s)
        velocity_error = abs(Fraction.from_float(velocity_float) - exact_knot.velocity_m_s)
        time_scale = max(1.0, abs(time_float), abs(float(exact_knot.time_s)))
        velocity_scale = max(1.0, abs(velocity_float), abs(float(exact_knot.velocity_m_s)))
        if time_error > _roundoff_bound(time_scale):
            raise HistoryGenerationError("binary64 knot-time round-trip exceeds 16 ulp")
        if velocity_error > _roundoff_bound(velocity_scale):
            raise HistoryGenerationError("binary64 knot-speed round-trip exceeds 16 ulp")
        max_time_error = max(max_time_error, float(time_error))
        max_velocity_error = max(max_velocity_error, float(velocity_error))

    query_count = 0
    max_table_error = Fraction(0)
    max_projection_error = Fraction(0)
    for left, right in zip(exact_knots, exact_knots[1:]):
        width = right.time_s - left.time_s
        for numerator, denominator in ((1, 2), (1, 3), (2, 3)):
            requested_time = left.time_s + width * Fraction(numerator, denominator)
            query_time = float(requested_time)  # Python float conversion is RN-even binary64.
            query_fraction = Fraction.from_float(query_time)
            reference = exact_source_value(source, scenario, query_fraction)
            candidate = _runtime_table_value(float_knots, query_time)
            candidate_fraction = Fraction.from_float(candidate)
            endpoint_0, endpoint_1 = _runtime_segment_endpoints(float_knots, query_time)
            scale = max(
                1.0,
                abs(float(reference)),
                abs(candidate),
                abs(endpoint_0),
                abs(endpoint_1),
            )
            evaluator_error = abs(candidate_fraction - reference)
            if evaluator_error > _roundoff_bound(scale):
                raise HistoryGenerationError("table/evaluator mismatch exceeds 16 ulp")
            original_position_value = exact_source_value(source, scenario, requested_time)
            max_projection_error = max(
                max_projection_error, abs(original_position_value - reference)
            )
            max_table_error = max(max_table_error, evaluator_error)
            query_count += 1
    return ProjectionDiagnostics(
        max_time_roundtrip_error_s=max_time_error,
        max_velocity_roundtrip_error_m_s=max_velocity_error,
        interior_query_count=query_count,
        max_table_evaluator_error_m_s=float(max_table_error),
        max_query_projection_error_m_s=float(max_projection_error),
    )


def _integral_diagnostics(
    source: SourceHistory, scenario: Scenario, knots: Sequence[ExactKnot]
) -> IntegralDiagnostics:
    velocity_integral = Fraction(0)
    velocity_squared_integral = Fraction(0)
    max_velocity_difference = Fraction(0)
    max_velocity_squared_difference = Fraction(0)
    for left, right in zip(knots, knots[1:]):
        width = right.time_s - left.time_s
        middle_time = (left.time_s + right.time_s) / 2
        middle_value = exact_source_value(source, scenario, middle_time)
        formula_velocity = width * (left.velocity_m_s + right.velocity_m_s) / 2
        simpson_velocity = width * (left.velocity_m_s + 4 * middle_value + right.velocity_m_s) / 6
        formula_squared = (
            width
            * (
                left.velocity_m_s**2
                + left.velocity_m_s * right.velocity_m_s
                + right.velocity_m_s**2
            )
            / 3
        )
        simpson_squared = (
            width * (left.velocity_m_s**2 + 4 * middle_value**2 + right.velocity_m_s**2) / 6
        )
        max_velocity_difference = max(
            max_velocity_difference, abs(formula_velocity - simpson_velocity)
        )
        max_velocity_squared_difference = max(
            max_velocity_squared_difference, abs(formula_squared - simpson_squared)
        )
        velocity_integral += formula_velocity
        velocity_squared_integral += formula_squared
    if max_velocity_difference or max_velocity_squared_difference:
        raise HistoryGenerationError("exact segment integrals disagree with Simpson oracle")
    return IntegralDiagnostics(
        integral_velocity_m=velocity_integral,
        integral_velocity_squared_m2_per_s=velocity_squared_integral,
        max_velocity_simpson_difference=max_velocity_difference,
        max_velocity_squared_simpson_difference=max_velocity_squared_difference,
    )


def generate_history(source: SourceHistory, scenario: Scenario) -> GeneratedHistory:
    if source.read_id != scenario.read_id:
        raise HistoryGenerationError("scenario read ID does not match the selected CSV")
    exact_knots = _exact_history_knots(source, scenario)
    float_knots = _float_projection(exact_knots)
    table_bytes = canonical_history_table_bytes(float_knots)
    serialized_knots = parse_canonical_history_table_bytes(table_bytes)
    if serialized_knots != float_knots:
        raise HistoryGenerationError(
            "canonical bytes did not round-trip to projected binary64 knots"
        )
    table_sha = sha256_bytes(table_bytes)
    return GeneratedHistory(
        scenario=scenario,
        exact_knots=exact_knots,
        float_knots=float_knots,
        table_bytes=table_bytes,
        table_sha256=table_sha,
        history_content_id=history_content_id(table_bytes),
        projection=_projection_diagnostics(source, scenario, exact_knots, serialized_knots),
        integrals=_integral_diagnostics(source, scenario, exact_knots),
    )


CONVENTIONS: dict[str, Any] = {
    "source_time_mapping": "x=t+delta_s",
    "shift_sign": "positive delta advances the source history",
    "run_window_s": ["-0.03", "0.5"],
    "diagnostic_time_s": "0.5",
    "source_domain_s": ["0", "5"],
    "negative_source_time": "zero extension for x<0 only",
    "beyond_source_domain": "reject",
    "origin_taper": "(0,0) plus source ordinate bounds at positive CSV knots",
    "floor": "max(0,u+a*b_tilde)",
    "binary64_projection": "IEEE-754 binary64 round-to-nearest, ties-to-even",
    "scenario_order": "read, then delta_s, then residual_coefficient",
    "scenarios": [scenario.as_record() for scenario in proposed_scenarios()],
}

UPSTREAM_FIELDS = frozenset(
    {
        "method_revision",
        "method_document_sha256",
        "source_pdf_sha256",
        "source_csv_sha256",
        "target_csv_sha256",
        "source_record_sha256",
        "replay_sha256",
        "validation_sha256",
        "plan_sha256",
        "approved_contract_sha256",
        "generator_source_sha256",
        "python",
        "conventions",
        "startup_input_sha256",
        "repository",
    }
)


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise HistoryGenerationError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """M03 canonical JSON: UTF-8, sorted keys, compact separators, one final LF."""

    def validate(node: Any, path: str = "$") -> None:
        if node is None or isinstance(node, (str, bool, int)):
            return
        if isinstance(node, float) or isinstance(node, Decimal):
            raise HistoryGenerationError(f"noncanonical numeric JSON value at {path}; use strings")
        if isinstance(node, list) or isinstance(node, tuple):
            for index, item in enumerate(node):
                validate(item, f"{path}[{index}]")
            return
        if isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise HistoryGenerationError(f"non-string JSON object key at {path}")
                validate(item, f"{path}.{key}")
            return
        raise HistoryGenerationError(
            f"unsupported canonical JSON value at {path}: {type(node).__name__}"
        )

    if not isinstance(value, Mapping):
        raise HistoryGenerationError("canonical JSON root must be an object")
    normalized = dict(value)
    validate(normalized)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise HistoryGenerationError("value cannot be serialized as canonical JSON") from exc
    return (encoded + "\n").encode("utf-8")


def upstream_dependency_descriptor(dependencies: Mapping[str, Any]) -> dict[str, Any]:
    """Construct the exact M03 upstream descriptor; downstream data are excluded."""
    missing = UPSTREAM_FIELDS - set(dependencies)
    extra = set(dependencies) - UPSTREAM_FIELDS
    if missing or extra:
        raise HistoryGenerationError(
            f"upstream descriptor keys invalid; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    descriptor = dict(dependencies)
    if descriptor["method_revision"] != METHOD_REVISION:
        raise HistoryGenerationError("M03 upstream descriptor has the wrong method revision")
    for field in (
        "method_document_sha256",
        "source_pdf_sha256",
        "source_record_sha256",
        "replay_sha256",
        "validation_sha256",
        "plan_sha256",
        "generator_source_sha256",
    ):
        _require_sha256(descriptor[field], field=field)
    if descriptor["approved_contract_sha256"] is not None:
        _require_sha256(descriptor["approved_contract_sha256"], field="approved contract hash")
    for group in ("source_csv_sha256", "target_csv_sha256"):
        values = descriptor[group]
        if not isinstance(values, Mapping) or set(values) != {"primary", "second_read"}:
            raise HistoryGenerationError(f"{group} must include primary and second_read hashes")
        for read_id, digest in values.items():
            _require_sha256(digest, field=f"{group}.{read_id}")
    startup = descriptor["startup_input_sha256"]
    if not isinstance(startup, Mapping) or set(startup) != {
        "gas_only_initial_state",
        "non_source_boundary_inputs",
    }:
        raise HistoryGenerationError(
            "startup hashes must name gas-only state and non-source inputs"
        )
    for name, digest in startup.items():
        _require_sha256(digest, field=f"startup_input_sha256.{name}")
    repository = descriptor["repository"]
    if not isinstance(repository, Mapping) or set(repository) != {"revision", "dirty_state"}:
        raise HistoryGenerationError("repository descriptor must include revision and dirty_state")
    if not isinstance(repository["revision"], str) or not repository["revision"]:
        raise HistoryGenerationError("repository revision must be recorded")
    if not isinstance(repository["dirty_state"], Mapping):
        raise HistoryGenerationError("repository dirty-state evidence must be an object")
    python = descriptor["python"]
    if not isinstance(python, Mapping) or set(python) != {"implementation", "version"}:
        raise HistoryGenerationError("Python implementation and exact version are required")
    if not all(isinstance(python[key], str) and python[key] for key in python):
        raise HistoryGenerationError("Python implementation/version must be nonempty strings")
    if descriptor["conventions"] != CONVENTIONS:
        raise HistoryGenerationError(
            "upstream descriptor must include the complete M03 conventions"
        )
    canonical_json_bytes(descriptor)
    return descriptor


def upstream_dependency_digest(dependencies: Mapping[str, Any]) -> str:
    descriptor = upstream_dependency_descriptor(dependencies)
    return sha256_bytes(canonical_json_bytes(descriptor))


SOURCE_MATRIX_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "status",
        "method_revision",
        "repository",
        "source_pdf_sha256",
        "source_csv_sha256",
        "target_csv_sha256",
        "source_record_sha256",
        "replay_sha256",
        "validation_sha256",
        "plan_sha256",
        "method_document_sha256",
        "generator_source_sha256",
        "python",
        "conventions",
        "startup_input_sha256",
        "upstream_dependency_sha256",
        "histories",
        "cases",
        "approved_contract_sha256",
    }
)
SOURCE_MATRIX_FORBIDDEN_FIELDS = frozenset(
    {
        "source_matrix_manifest_sha256",
        "approval_record_sha256",
        "execution_id",
        "execution_manifest_sha256",
        "run_outputs",
    }
)
SOURCE_MATRIX_FIXTURE_SCHEMA = "e2-source-matrix-m03-implementation-fixture"
SOURCE_MATRIX_FIXTURE_STATUS = "implementation_fixture_not_approved_or_runnable"


def canonical_source_matrix_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    missing = SOURCE_MATRIX_REQUIRED_FIELDS - set(manifest)
    forbidden = SOURCE_MATRIX_FORBIDDEN_FIELDS.intersection(manifest)
    extra = set(manifest) - SOURCE_MATRIX_REQUIRED_FIELDS
    if missing or forbidden or extra:
        raise HistoryGenerationError(
            f"source-matrix manifest keys invalid; missing={sorted(missing)}, "
            f"forbidden={sorted(forbidden)}, extra={sorted(extra)}"
        )
    if manifest["schema"] != SOURCE_MATRIX_FIXTURE_SCHEMA:
        raise HistoryGenerationError("implementation fixture schema is unsupported")
    if manifest["status"] != SOURCE_MATRIX_FIXTURE_STATUS:
        raise HistoryGenerationError("implementation fixture status is unsupported")
    if manifest["method_revision"] != METHOD_REVISION:
        raise HistoryGenerationError("source-matrix manifest must use M03")
    if manifest["approved_contract_sha256"] is not None:
        raise HistoryGenerationError(
            "implementation-only M03 fixture must preserve contract hash null"
        )
    if not isinstance(manifest["histories"], list) or not isinstance(manifest["cases"], list):
        raise HistoryGenerationError("histories and cases must be JSON arrays")
    if len(manifest["cases"]) != 18:
        raise HistoryGenerationError("M03 proposed matrix fixture must retain all 18 cases")
    _require_sha256(manifest["upstream_dependency_sha256"], field="upstream dependency digest")
    upstream_descriptor = {field: manifest[field] for field in UPSTREAM_FIELDS}
    if upstream_dependency_digest(upstream_descriptor) != manifest["upstream_dependency_sha256"]:
        raise HistoryGenerationError(
            "source-matrix upstream digest does not match its frozen dependency fields"
        )

    def validate_relative_path(path: Any) -> str:
        if not isinstance(path, str) or not path:
            raise HistoryGenerationError("history path must be repository-relative")
        pure_path = PurePosixPath(path)
        if "\x00" in path or pure_path.is_absolute() or ".." in pure_path.parts or "\\" in path:
            raise HistoryGenerationError("history path must be repository-relative POSIX syntax")
        if not pure_path.name or pure_path.as_posix() != path:
            raise HistoryGenerationError("history path must be a canonical file path")
        return pure_path.as_posix()

    histories_by_id: dict[str, tuple[str, str]] = {}
    history_paths: set[str] = set()
    for history in manifest["histories"]:
        if not isinstance(history, Mapping):
            raise HistoryGenerationError("history manifest entries must be objects")
        if set(history) != {"path", "history_content_id", "history_table_sha256"}:
            raise HistoryGenerationError("history manifest entry has missing or extra fields")
        canonical_path = validate_relative_path(history.get("path"))
        history_id = history.get("history_content_id")
        table_sha = _require_sha256(history.get("history_table_sha256"), field="history table hash")
        if history_id != f"E2-HIST-H{table_sha}" or history_id in histories_by_id:
            raise HistoryGenerationError(
                "history-content ID is missing, inconsistent, or duplicated"
            )
        if canonical_path in history_paths:
            raise HistoryGenerationError("history table paths must be unique")
        history_paths.add(canonical_path)
        histories_by_id[history_id] = (table_sha, canonical_path)

    expected_scenarios = tuple(scenario.as_record() for scenario in proposed_scenarios())
    observed_scenarios: list[Mapping[str, Any]] = []
    referenced_histories: set[str] = set()
    for case in manifest["cases"]:
        if not isinstance(case, Mapping):
            raise HistoryGenerationError("case manifest entries must be objects")
        if set(case) != {
            "scenario",
            "case_id",
            "history_content_id",
            "history_table_sha256",
            "history_path",
        }:
            raise HistoryGenerationError("case manifest entry has missing or extra fields")
        scenario_record = case.get("scenario")
        if not isinstance(scenario_record, Mapping):
            raise HistoryGenerationError("case entry must include its exact scenario strings")
        if set(scenario_record) != {"read", "delta_s", "residual_coefficient"}:
            raise HistoryGenerationError("case scenario has missing or extra fields")
        observed_scenarios.append(scenario_record)
        scenario = Scenario(
            scenario_record.get("read"),
            scenario_record.get("delta_s"),
            scenario_record.get("residual_coefficient"),
        )
        history_id = case.get("history_content_id")
        table_sha = _require_sha256(
            case.get("history_table_sha256"), field="case history table hash"
        )
        if history_id != f"E2-HIST-H{table_sha}":
            raise HistoryGenerationError("case history-content ID does not match its table hash")
        if history_id not in histories_by_id or histories_by_id[history_id][0] != table_sha:
            raise HistoryGenerationError("case references a history absent from the history list")
        referenced_histories.add(history_id)
        canonical_case_path = validate_relative_path(case.get("history_path"))
        if canonical_case_path != histories_by_id[history_id][1]:
            raise HistoryGenerationError("case history path does not match the history record")
        expected_case_id = scenario_case_id(
            scenario, manifest["upstream_dependency_sha256"], table_sha
        )
        if case.get("case_id") != expected_case_id:
            raise HistoryGenerationError("case ID does not match its scenario, U and H hashes")
    if tuple(observed_scenarios) != expected_scenarios:
        raise HistoryGenerationError(
            "case list must contain all 18 M03 scenarios in canonical order"
        )
    if referenced_histories != set(histories_by_id):
        raise HistoryGenerationError("history list contains an unreferenced table")
    return canonical_json_bytes(manifest)


def source_matrix_manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_source_matrix_manifest_bytes(manifest))


EXECUTION_DESCRIPTOR_FIELDS = frozenset(
    {
        "source_matrix_manifest_sha256",
        "approval_record_sha256",
        "attempt_token",
        "solver_build_dependencies",
        "solver_settings",
        "seeds",
        "preregistered_resource_run_settings",
    }
)


def execution_descriptor_sha256(descriptor: Mapping[str, Any]) -> str:
    missing = EXECUTION_DESCRIPTOR_FIELDS - set(descriptor)
    extra = set(descriptor) - EXECUTION_DESCRIPTOR_FIELDS
    if missing or extra:
        raise HistoryGenerationError(
            f"execution descriptor keys invalid; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    _require_sha256(descriptor["source_matrix_manifest_sha256"], field="source matrix hash")
    _require_sha256(descriptor["approval_record_sha256"], field="approval record hash")
    if not isinstance(descriptor["attempt_token"], str) or not descriptor["attempt_token"]:
        raise HistoryGenerationError("execution attempt token must be unique and nonempty")
    return sha256_bytes(canonical_json_bytes(descriptor))


def execution_id(descriptor: Mapping[str, Any]) -> str:
    descriptor_hash = execution_descriptor_sha256(descriptor)
    return (
        f"E2-EXEC-M03-S{descriptor['source_matrix_manifest_sha256']}"
        f"-A{descriptor['approval_record_sha256']}-C{descriptor_hash}"
    )
