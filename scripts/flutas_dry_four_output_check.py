#!/usr/bin/env python3
"""Check and byte-copy the frozen candidate6 dry_four normal output roster.

This is a read-only diagnostic output checker, not a flow or physics validator.
It does not create the candidate5 v2 run manifest; callers may do that only
after this function returns a complete report.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aerial_drop import flutas_source_analyzer as analyzer  # noqa: E402

MAP_SHA256 = "3f54d634afbd4338ef144f6fd97238de57dae52046b8c18da25b42d5d2876d33"
CASE_ID = "dry_four"
CANDIDATE_ID = "candidate6-20260928T093141Z-4092509"
CANDIDATE_RECEIPT_SHA256 = "629e792cf9ebd02d203442b2b943de4aa1176a121f8be303fd86770543c643e0"
IMAGE_DIGEST = "sha256:0cbfcc17c72484c004663ee009e320cbb551bf80f534cfdb1a9d3db1297b8972"
ANALYZER_SHA256 = "9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37"
MANIFEST_ADAPTER_SHA256 = "373511b66b46531a99b5670e5ab680eef51811e67456fe98c056a5a1882ab29b"
INPUT_SHA256 = {
    "dns.in": "929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0",
    "source-boundary.in": "f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0",
    "vof.in": "2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54",
}

V03_HEADERS: dict[str, tuple[str, ...]] = {
    "source_flux": (
        "interval_index",
        "slot",
        "requested_volume_m3",
        "geometric_inward_volume_m3",
        "requested_mass_kg",
        "applied_inward_mass_kg",
        "requested_mom_x_kgm_s",
        "requested_mom_y_kgm_s",
        "requested_mom_z_kgm_s",
        "applied_mom_x_kgm_s",
        "applied_mom_y_kgm_s",
        "applied_mom_z_kgm_s",
        "slot_reverse_out_m3",
    ),
    "source_offmask": ("interval_index", "offmask_in_m3", "offmask_out_m3"),
    "rate_check": (
        "interval_index",
        "measured_top_liquid_m3_s",
        "expected_top_liquid_m3_s",
        "top_residual_m3_s",
        "measured_bottom_volume_m3_s",
        "expected_bottom_volume_m3_s",
        "bottom_residual_m3_s",
    ),
    "boundary_ledger": (
        "completed_state_index",
        "xlow_in_m3",
        "xlow_out_m3",
        "xhigh_in_m3",
        "xhigh_out_m3",
        "ylow_in_m3",
        "ylow_out_m3",
        "yhigh_in_m3",
        "yhigh_out_m3",
        "zlow_in_m3",
        "zlow_out_m3",
        "zhigh_in_m3",
        "zhigh_out_m3",
    ),
    "mass_ledger": (
        "state_index",
        "time_s",
        "box_liquid_kg",
        "initial_liquid_kg",
        "cumulative_boundary_in_kg",
        "cumulative_boundary_out_kg",
        "residual_kg",
        "net_boundary_liquid_m3",
        "xlow_in_kg",
        "xlow_out_kg",
        "xhigh_in_kg",
        "xhigh_out_kg",
        "ylow_in_kg",
        "ylow_out_kg",
        "yhigh_in_kg",
        "yhigh_out_kg",
        "zlow_in_kg",
        "zlow_out_kg",
        "zhigh_in_kg",
        "zhigh_out_kg",
    ),
    "velocity_audit": (
        "state_index",
        "source_profile_interval",
        "time_s",
        "dt_s",
        "total_cell_count",
        "global_chkdt_advective_courant_max",
        "interface_cell_count",
        "interface_courant_defined",
        "interface_advective_courant_max",
        "top_in_m3_s",
        "bottom_out_m3_s",
        "net_boundary_m3_s",
        "integrated_divergence_m3_s",
        "closure_m3_s",
        "max_abs_divergence_s",
        "volume_integrated_abs_divergence_m3_s",
        "xlow_out_m3_s",
        "xhigh_out_m3_s",
        "ylow_out_m3_s",
        "yhigh_out_m3_s",
        "zlow_out_m3_s",
        "zhigh_out_m3_s",
    ),
}

V03_ROW_COUNTS = {
    "source_flux": 0,
    "source_offmask": 14,
    "rate_check": 14,
    "boundary_ledger": 15,
    "mass_ledger": 15,
    "velocity_audit": 15,
}
V12_SPECS = {
    "phase_property": (analyzer.PHASE_FILE, analyzer.PHASE_HEADER, 672),
    "boundary_velocity": (analyzer.VELOCITY_FILE, analyzer.VELOCITY_HEADER, 516),
    "timestep_restriction": (analyzer.TIMESTEP_FILE, analyzer.TIMESTEP_HEADER, 15),
}
NATIVE_TEXT_OUTPUTS = {"time_out", "vof_info", "pos_vt", "scalar_out", "restart_checkpoints"}


class OutputCheckError(ValueError):
    """The retained bundle is not an exact normal output bundle."""


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OutputCheckError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise OutputCheckError(f"non-finite JSON constant is forbidden: {token}")


def _strict_json(raw: bytes, label: str) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise OutputCheckError(f"{label} must not have a UTF-8 BOM")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_json_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OutputCheckError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lstat_regular(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise OutputCheckError(f"missing {label}: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise OutputCheckError(f"{label} must be a singly-linked regular file: {path}")
    return info


def _hash_regular(path: Path, label: str) -> tuple[str, int]:
    before = _lstat_regular(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise OutputCheckError(f"cannot safely open {label}: {path}: {exc}") from exc
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise OutputCheckError(f"{label} changed into a linked or non-regular file: {path}")
        digest = hashlib.sha256()
        size = 0
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
        after = os.fstat(stream.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, size):
        raise OutputCheckError(f"{label} changed while being read: {path}")
    return digest.hexdigest(), size


def _read_regular(path: Path, label: str) -> bytes:
    _lstat_regular(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise OutputCheckError(f"cannot safely open {label}: {path}: {exc}") from exc
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise OutputCheckError(f"{label} changed into a linked or non-regular file: {path}")
        return stream.read()


def _relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise OutputCheckError(f"{label} must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise OutputCheckError(f"{label} escapes its declared root: {value}")
    if path.as_posix() != value:
        raise OutputCheckError(f"{label} is not canonical POSIX path text: {value}")
    return path


def _load_map(bundle_root: Path, requested_map: Path | None) -> tuple[dict[str, Any], bytes]:
    copied_map = bundle_root / "metadata" / "dry-output-map.json"
    copied_raw = _read_regular(copied_map, "copied output map")
    if _sha256_bytes(copied_raw) != MAP_SHA256:
        raise OutputCheckError("bundle output-map copy differs from the frozen dry_four map pin")
    if requested_map is not None:
        requested_raw = _read_regular(requested_map, "requested output map")
        if requested_raw != copied_raw:
            raise OutputCheckError("requested output map differs from the bundle's frozen copy")
    run_manifest = _strict_json(
        _read_regular(bundle_root / "metadata" / "run-manifest.json", "launch run manifest"),
        "launch run manifest",
    )
    if run_manifest.get("output_map", {}).get("sha256") != MAP_SHA256:
        raise OutputCheckError("launch run manifest does not bind the frozen output map")
    value = _strict_json(copied_raw, "dry output map")
    scope = value.get("scope")
    files = value.get("producer_files")
    if (
        value.get("schema") != "flutas-dry-output-map-v0.1"
        or not isinstance(scope, dict)
        or scope.get("case_id") != CASE_ID
        or scope.get("candidate") != "candidate6"
        or not isinstance(files, list)
        or len(files) != 38
        or value.get("accounting", {}).get("expected_count") != 38
    ):
        raise OutputCheckError("output map is not the exact 38-entry candidate6 dry_four map")
    return value, copied_raw


def _check_native_roster(bundle_root: Path, files: list[dict[str, Any]]) -> dict[str, Path]:
    work = bundle_root / "work"
    data_root = work / "data"
    for directory, label in ((work, "work directory"), (data_root, "native data directory")):
        try:
            info = directory.lstat()
        except OSError as exc:
            raise OutputCheckError(f"missing {label}: {directory}") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise OutputCheckError(f"{label} must be a real directory: {directory}")

    expected: dict[str, Path] = {}
    expected_dirs: set[str] = set()
    for item in files:
        native = _relative_path(item.get("native_path"), "native_path").as_posix()
        if not native.startswith("data/"):
            raise OutputCheckError(f"native solver path is outside work/data: {native}")
        if native in expected:
            raise OutputCheckError(f"duplicate native solver path: {native}")
        expected[native] = work.joinpath(*PurePosixPath(native).parts)
        parents = PurePosixPath(native).parents
        expected_dirs.update(parent.as_posix() for parent in parents if parent.as_posix() != ".")

    seen_files: set[str] = set()
    seen_dirs: set[str] = {"data"}
    for current, dirnames, filenames in os.walk(data_root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(dirnames):
            path = current_path / name
            info = path.lstat()
            relative = path.relative_to(work).as_posix()
            if not stat.S_ISDIR(info.st_mode):
                raise OutputCheckError(f"symlink or non-directory under work/data: {relative}")
            if relative not in expected_dirs:
                raise OutputCheckError(f"unlisted directory under work/data: {relative}")
            seen_dirs.add(relative)
        for name in filenames:
            path = current_path / name
            relative = path.relative_to(work).as_posix()
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OutputCheckError(
                    f"native output must be singly-linked regular file: {relative}"
                )
            if relative not in expected:
                raise OutputCheckError(f"unlisted native solver output under work/data: {relative}")
            seen_files.add(relative)
    if seen_files != set(expected):
        missing = sorted(set(expected) - seen_files)
        raise OutputCheckError(f"native output roster has missing files: {missing}")
    if seen_dirs != expected_dirs:
        missing_dirs = sorted(expected_dirs - seen_dirs)
        raise OutputCheckError(f"native output roster has missing directories: {missing_dirs}")
    return expected


def _check_work_area(bundle_root: Path) -> None:
    """Reject work outputs outside data; tolerate Docker's staged-file mountpoints."""
    work = bundle_root / "work"
    permitted = {"data", *INPUT_SHA256}
    entries = {path.name for path in work.iterdir()}
    unexpected = entries - permitted
    if unexpected:
        raise OutputCheckError(
            f"unlisted solver-created output outside work/data: {sorted(unexpected)}"
        )
    for name in entries & set(INPUT_SHA256):
        path = work / name
        _lstat_regular(path, f"staged work input mountpoint {name}")


def _check_staged_inputs(bundle_root: Path) -> None:
    staged_root = bundle_root / "dry_four"
    try:
        info = staged_root.lstat()
    except OSError as exc:
        raise OutputCheckError(f"missing immutable staged-input directory: {staged_root}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise OutputCheckError(f"staged-input root must be a real directory: {staged_root}")
    entries = {path.name for path in staged_root.iterdir()}
    expected = set(INPUT_SHA256)
    if entries != expected:
        raise OutputCheckError(
            f"staged-input leaf must contain exactly the frozen three files; "
            f"missing={sorted(expected - entries)}, extra={sorted(entries - expected)}"
        )
    for name, expected_digest in INPUT_SHA256.items():
        path = staged_root / name
        info = _lstat_regular(path, f"staged input {name}")
        if info.st_mode & 0o222:
            raise OutputCheckError(f"staged input must be read-only: {name}")
        actual, _ = _hash_regular(path, "staged input")
        if actual != expected_digest:
            raise OutputCheckError(f"staged input hash mismatch: {name}")


def _csv_rows(raw: bytes, header: tuple[str, ...], label: str, row_count: int) -> list[list[str]]:
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise OutputCheckError(f"{label} must be BOM-free LF text with a final LF")
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise OutputCheckError(f"{label} must be ASCII") from exc
    lines = text[:-1].split("\n")
    if not lines or any(not line or '"' in line for line in lines):
        raise OutputCheckError(f"{label} has a blank or quoted record")
    if tuple(lines[0].split(",")) != header:
        raise OutputCheckError(f"{label} header/order differs from the frozen schema")
    rows: list[list[str]] = []
    for line_number, line in enumerate(lines[1:], 2):
        values = line.split(",")
        if len(values) != len(header) or any(value == "" for value in values):
            raise OutputCheckError(f"{label} record {line_number} has malformed columns")
        rows.append(values)
    if len(rows) != row_count:
        raise OutputCheckError(f"{label} has {len(rows)} data rows; expected {row_count}")
    return rows


def _finite_number(token: str, label: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise OutputCheckError(f"{label} is not a numeric field: {token!r}") from exc
    if not math.isfinite(value):
        raise OutputCheckError(f"{label} is not finite")
    return value


def _check_v03(item: dict[str, Any], raw: bytes) -> list[list[str]]:
    file_id = item["id"]
    header = V03_HEADERS[file_id]
    rows = _csv_rows(raw, header, file_id, V03_ROW_COUNTS[file_id])
    for row_index, row in enumerate(rows):
        for field, token in zip(header, row, strict=True):
            value = _finite_number(token, f"{file_id}[{row_index}].{field}")
            if field in {
                "interval_index",
                "completed_state_index",
                "state_index",
                "slot",
                "source_profile_interval",
                "total_cell_count",
                "interface_cell_count",
                "interface_courant_defined",
            }:
                if not value.is_integer():
                    raise OutputCheckError(f"{file_id}[{row_index}].{field} must be an integer")

    if file_id == "source_flux":
        return rows
    if file_id in {"source_offmask", "rate_check"}:
        for index, row in enumerate(rows):
            if int(float(row[0])) != index:
                raise OutputCheckError(f"{file_id} interval rows are not 0..13")
            if any(_finite_number(token, file_id) != 0.0 for token in row[1:]):
                raise OutputCheckError(f"dry {file_id} values must all be zero")
        return rows
    if file_id in {"boundary_ledger", "mass_ledger"}:
        for state, row in enumerate(rows):
            if int(float(row[0])) != state:
                raise OutputCheckError(f"{file_id} states are not U0..U14")
            zero_start = 2 if file_id == "mass_ledger" else 1
            if any(_finite_number(token, file_id) != 0.0 for token in row[zero_start:]):
                raise OutputCheckError(f"dry {file_id} inventory and flux values must be zero")
        return rows

    # The interface Courant value is explicitly undefined only because the
    # interface set is empty. Keep this narrow check separate from raw fields.
    boundary_zero_indexes = (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)
    for state, row in enumerate(rows):
        if int(float(row[0])) != state or int(float(row[1])) != state:
            raise OutputCheckError("velocity-audit state/profile rows are not U0..U14")
        if int(float(row[4])) != 537600:
            raise OutputCheckError(
                "velocity-audit cell count differs from the frozen 160x84x40 grid"
            )
        if int(float(row[6])) != 0 or int(float(row[7])) != 0 or float(row[8]) != 0.0:
            raise OutputCheckError("dry interface must use count=0, defined=0, stored Courant=0")
        if any(
            _finite_number(row[index], "velocity-audit boundary/divergence") != 0.0
            for index in boundary_zero_indexes
        ):
            raise OutputCheckError("dry velocity boundary/divergence summaries must be zero")
    return rows


def _fortran_es24_16e3(value: float) -> str:
    """Reproduce the source's ES24.16E3 field for exact clock and dt tokens."""
    if not math.isfinite(value):
        raise OutputCheckError("cannot format a non-finite native time or timestep")
    mantissa, exponent = f"{value:.16E}".split("E")
    sign = exponent[0]
    exponent_value = int(exponent[1:])
    token = f"{mantissa}E{sign}{exponent_value:03d}"
    if len(token) > 24:
        raise OutputCheckError("native time/timestep does not fit ES24.16E3")
    return token.rjust(24)


def _fortran_e15_7(value: float) -> str:
    """Format the producer's E15.7 real fields, including its 0.x mantissa."""
    if not math.isfinite(value):
        raise OutputCheckError("cannot format a non-finite E15.7 field")
    if value == 0.0:
        return "0.0000000E+00".rjust(15)
    sign = "-" if value < 0.0 else ""
    mantissa, exponent = f"{abs(value):.7E}".split("E")
    leading_digit, fraction = mantissa.split(".")
    if len(leading_digit) != 1:
        raise OutputCheckError("native value has an unsupported E15.7 exponent")
    digits = leading_digit + fraction[:6]
    fortran_exponent = int(exponent) + 1
    token = f"{sign}0.{digits}E{fortran_exponent:+03d}"
    if len(token) > 15:
        raise OutputCheckError("native value does not fit the producer's E15.7 field")
    return token.rjust(15)


def _native_clock_values(inputs: Mapping[str, Any]) -> list[float]:
    """Reproduce native U0..U14 time using candidate5's binary64 update order."""
    # Producer source: upstream FLUTAS commit 5982106, src/rk.f90:119-132 and
    # src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90:526-534,610,792-804.
    # Frozen dns.in has constant_dt=T, dt_input=1e-4 and icheck=1 (line 14), so
    # dt/dto is exactly one after the Euler startup and every state adds f_t12.
    native_times = [float(inputs["time_start_s"])]
    fixed_step = float(inputs["fixed_step_s"])
    for state in range(14):
        if state == 0:
            # src/rk.f90:119-122: Euler for istep=1.
            f_t1 = 1.0 * fixed_step
            f_t2 = 0.0 * fixed_step
        else:
            # src/rk.f90:123-132: dt/dto=1 for this constant-dt case; preserve
            # the separate binary64 term evaluation and f_t12 summation.
            ratio_t1 = fixed_step / fixed_step
            f_t1 = (1.0 + 0.5 * ratio_t1) * fixed_step
            ratio_t2 = fixed_step / fixed_step
            f_t2 = (-0.5 * ratio_t2) * fixed_step
        native_times.append(native_times[-1] + (f_t1 + f_t2))
    return native_times


def _check_native_clock_joins(
    mass_rows: list[list[str]], velocity_rows: list[list[str]], inputs: Mapping[str, Any]
) -> None:
    """Check accumulated solver clocks separately from v1.2's index-derived clock."""
    if len(mass_rows) != 15 or len(velocity_rows) != 15:
        raise OutputCheckError("native mass and velocity clocks must each cover U0..U14")
    expected_native_times = _native_clock_values(inputs)
    fixed_step = float(inputs["fixed_step_s"])
    expected_dt = _fortran_es24_16e3(fixed_step)
    for state, (mass_row, velocity_row) in enumerate(zip(mass_rows, velocity_rows, strict=True)):
        if int(float(mass_row[0])) != state or int(float(velocity_row[0])) != state:
            raise OutputCheckError("native mass/velocity clock rows must join states U0..U14")
        expected_time = _fortran_es24_16e3(expected_native_times[state])
        mass_time = mass_row[1]
        velocity_time = velocity_row[2]
        if mass_time != velocity_time:
            raise OutputCheckError(f"native mass/velocity clocks do not join exactly at U{state}")
        if mass_time != expected_time:
            raise OutputCheckError(
                f"native accumulated mass/velocity clock at U{state} differs from source update"
            )
        if velocity_row[3] != expected_dt:
            raise OutputCheckError(
                f"native velocity-audit dt_s at U{state} differs from the frozen fixed step"
            )


def _check_native_out0d(
    raw: bytes,
    label: str,
    expected_rows: list[list[float]],
) -> None:
    """Check exact E15.7 columns emitted by output.out0d, row by row."""
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise OutputCheckError(f"{label} must be BOM-free LF text with a final LF")
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise OutputCheckError(f"{label} must be ASCII") from exc
    lines = text[:-1].split("\n")
    if len(lines) != len(expected_rows):
        raise OutputCheckError(f"{label} has {len(lines)} rows; expected {len(expected_rows)}")
    width = 15 * (len(expected_rows[0]) if expected_rows else 0)
    for row_index, (line, values) in enumerate(zip(lines, expected_rows, strict=True)):
        if len(line) != width:
            raise OutputCheckError(f"{label} row {row_index} is not fixed-width E15.7 text")
        expected = "".join(_fortran_e15_7(value) for value in values)
        fields = [line[offset : offset + 15] for offset in range(0, width, 15)]
        for field in fields:
            parsed = _finite_number(field.strip(), f"{label}[{row_index}]")
            if not math.isfinite(parsed):
                raise OutputCheckError(f"{label} row {row_index} contains a non-finite value")
        if line != expected:
            raise OutputCheckError(f"{label} row {row_index} differs from the frozen dry state")


def _check_checkpoint_scalar(raw: bytes, native_times: list[float], fixed_step: float) -> None:
    """Check load.f90's `(2E15.7,1I9.8)` final U14 scalar record."""
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise OutputCheckError("scalar.out must be one BOM-free LF record")
    try:
        text = raw[:-1].decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise OutputCheckError("scalar.out must be ASCII") from exc
    if len(text) != 39:
        raise OutputCheckError("scalar.out must match `(2E15.7,1I9.8)` width 39")
    time_field, dto_field, step_field = text[:15], text[15:30], text[30:39]
    for field, label in ((time_field, "scalar time"), (dto_field, "scalar dto")):
        _finite_number(field.strip(), label)
    try:
        step_value = int(step_field.strip())
    except ValueError as exc:
        raise OutputCheckError("scalar.out istep field is not an integer") from exc
    if step_value != 14:
        raise OutputCheckError("scalar.out istep must identify the final U14 checkpoint")
    expected = _fortran_e15_7(native_times[14]) + _fortran_e15_7(fixed_step) + f"{14:08d}".rjust(9)
    if text != expected:
        raise OutputCheckError("scalar.out differs from the frozen U14 time/dto/istep record")


def _check_restart_index(raw: bytes, native_times: list[float]) -> None:
    """Check the sole final checkpoint index record written through out0d."""
    _check_native_out0d(raw, "restart_checkpoints.out", [[14.0, native_times[14], 1.0]])


def _check_native_state_outputs(raw_by_id: Mapping[str, bytes], inputs: Mapping[str, Any]) -> None:
    native_times = _native_clock_values(inputs)
    fixed_step = float(inputs["fixed_step_s"])
    _check_native_out0d(
        raw_by_id["time_out"],
        "time.out",
        [[float(state), fixed_step, native_times[state]] for state in range(1, 15)],
    )
    _check_native_out0d(
        raw_by_id["vof_info"],
        "vof_info.out",
        [[float(state), fixed_step, native_times[state], 0.0, 0.0, 0.0] for state in range(15)],
    )
    _check_empty_phase_position_velocity(raw_by_id["pos_vt"], native_times)
    _check_checkpoint_scalar(raw_by_id["scalar_out"], native_times, fixed_step)
    _check_restart_index(raw_by_id["restart_checkpoints"], native_times)


def _check_empty_phase_position_velocity(raw: bytes, native_times: list[float]) -> None:
    """Validate the pinned writer's undefined centroid rows for this zero-VOF case."""
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise OutputCheckError("pos_vt.out must be BOM-free LF text with a final LF")
    try:
        lines = raw.decode("ascii", errors="strict")[:-1].split("\n")
    except UnicodeDecodeError as exc:
        raise OutputCheckError("pos_vt.out must be ASCII") from exc
    if len(lines) != 14 or len(native_times) != 15:
        raise OutputCheckError("pos_vt.out must contain the 14 U1..U14 rows")
    undefined = "NaN".rjust(15)
    for state, line in enumerate(lines, start=1):
        if len(line) != 7 * 15:
            raise OutputCheckError(f"pos_vt.out state U{state} is not seven E15.7 fields")
        fields = [line[index : index + 15] for index in range(0, len(line), 15)]
        if fields[0] != _fortran_e15_7(native_times[state]):
            raise OutputCheckError(f"pos_vt.out time differs from native state U{state}")
        if fields[1:] != [undefined] * 6:
            raise OutputCheckError(
                f"pos_vt.out U{state} must mark all six zero-volume centroid fields NaN"
            )


def _expected_dry_four_vertical_grid() -> tuple[list[float], list[float]]:
    """Reproduce pinned initgrid steps 1–5 for dry_four (n=40, gr=0, lz=1, nh_d=1)."""
    nz = 40
    zf = [0.0] * (nz + 2)  # Fortran indices 0..41.
    for k in range(1, nz + 1):
        z0 = (k - 0.0) / (1.0 * nz)
        # gridpoint_cluster_two_end(alpha=0, z0) returns z0 exactly.
        zf[k] = z0 * 1.0

    dzf = [0.0] * (nz + 2)
    for k in range(1, nz + 1):
        dzf[k] = zf[k] - zf[k - 1]
    dzf[0] = dzf[1]
    dzf[nz + 1] = dzf[nz]

    dzc = [0.0] * (nz + 2)
    for k in range(0, nz + 1):
        dzc[k] = 0.5 * (dzf[k] + dzf[k + 1])
    dzc[nz + 1] = dzc[nz]

    # Mirror the source's halo extension order, including its upper-face index.
    for k in range(1 - 1, 1):
        dzf[k] = dzf[-k + 1]
        dzc[k] = dzc[-k]
    for k in range(nz + 1, nz + 2):
        dzf[k] = dzf[2 * nz - k - 1]
        dzc[k] = dzc[2 * nz - k]
    return dzc, dzf


def _strict_float_array(inputs: Mapping[str, Any], key: str) -> list[float]:
    values = inputs.get(key)
    if not isinstance(values, list) or len(values) != 42:
        raise OutputCheckError(f"timestep input {key} must contain the 42 pinned vertical entries")
    if any(not isinstance(value, str) for value in values):
        raise OutputCheckError(f"timestep input {key} entries must be decimal strings")
    try:
        numbers = [float(value) for value in values]
    except ValueError as exc:
        raise OutputCheckError(f"timestep input {key} contains a nonnumeric entry") from exc
    if any(not math.isfinite(value) for value in numbers):
        raise OutputCheckError(f"timestep input {key} contains a non-finite entry")
    return numbers


def _validate_dry_timestep_inputs(inputs: Any) -> dict[str, Any]:
    if not isinstance(inputs, dict) or len(inputs) != 26:
        raise OutputCheckError("timestep-inputs.json must contain the frozen 26-key object")
    try:
        analyzer._validate_timestep_inputs(inputs)
    except analyzer.AnalyzerError as exc:
        raise OutputCheckError(
            f"timestep-inputs.json violates the pinned 26-key schema: {exc}"
        ) from exc
    exact_strings = {"time_scheme": "ab2"}
    exact_integers = {"real_kind": 8, "precision_digits": 15}
    exact_numbers = {
        "time_start_s": 0.0,
        "cfl_c": 1.0,
        "cfl_d": 1.0 / 6.0,
        "rho1_kg_m3": 1000.0,
        "rho2_kg_m3": 1.0,
        "mu1_pa_s": 0.001,
        "mu2_pa_s": 1.8e-5,
        "dx_m": 0.025,
        "dy_m": 0.025,
        "dz_m": 0.025,
        "dxi_m_inv": 40.0,
        "dyi_m_inv": 40.0,
        "dzi_m_inv": 40.0,
        "sigma_n_m": 0.0,
        "fixed_step_factor": 0.2,
        "fixed_step_s": 0.0001,
    }
    for key, expected in exact_strings.items():
        if inputs.get(key) != expected:
            raise OutputCheckError(f"timestep input {key} differs from the frozen dry_four case")
    for key, expected in exact_integers.items():
        if type(inputs.get(key)) is not int or inputs[key] != expected:
            raise OutputCheckError(f"timestep input {key} differs from the frozen dry_four case")
    try:
        for key, expected in exact_numbers.items():
            if not isinstance(inputs.get(key), str) or float(inputs[key]) != expected:
                raise OutputCheckError(
                    f"timestep input {key} differs from the frozen dry_four case"
                )
    except ValueError as exc:
        raise OutputCheckError("a frozen dry_four timestep scalar is not numeric") from exc
    if inputs.get("gravity_m_s2") != ["0", "0", "0"]:
        raise OutputCheckError("dry_four timestep gravity must be [0,0,0]")
    eps = inputs.get("machine_epsilon")
    small = inputs.get("small_s_inv")
    if not isinstance(eps, str) or not isinstance(small, str):
        raise OutputCheckError("timestep epsilon and small operands must be decimal strings")
    try:
        if float(eps) != math.ulp(1.0) or float(small) != float(eps) * (10.0**7.5):
            raise OutputCheckError("timestep epsilon operands differ from frozen binary64 inputs")
    except ValueError as exc:
        raise OutputCheckError("timestep epsilon operands are not numeric") from exc
    expected_dzc, expected_dzf = _expected_dry_four_vertical_grid()
    for key, expected in (("dzc_m", expected_dzc), ("dzf_m", expected_dzf)):
        if _strict_float_array(inputs, key) != expected:
            raise OutputCheckError(
                f"timestep input {key} differs from the pinned dry_four grid construction"
            )
    for key, expected in (
        ("dzci_m_inv", [1.0 / value for value in expected_dzc]),
        ("dzfi_m_inv", [1.0 / value for value in expected_dzf]),
    ):
        if _strict_float_array(inputs, key) != expected:
            raise OutputCheckError(
                f"timestep input {key} differs from the pinned dry_four vertical inverses"
            )
    return inputs


def _derive_normal_metadata(bundle_root: Path) -> dict[str, Any]:
    """Use the existing candidate6 adapter's strict supervisor/exit verifier."""
    adapter_path = REPO_ROOT / "containers/flutas/candidate6/tools/write_dry_four_manifest.py"
    if _hash_regular(adapter_path, "candidate6 manifest adapter")[0] != MANIFEST_ADAPTER_SHA256:
        raise OutputCheckError("candidate6 manifest adapter differs from its pinned implementation")
    spec = importlib.util.spec_from_file_location("_dry_four_manifest_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise OutputCheckError("cannot load the existing candidate6 manifest adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.derive_run_metadata(
        supervisor_dir=bundle_root / "supervisor/evidence",
        stdout_path=bundle_root / "supervisor/evidence/stdout.log",
        performance_path=bundle_root / "work/data/performance.out",
    )


def _analyze_v12(
    rows_by_file: Mapping[str, bytes],
    inputs: dict[str, Any],
    run_metadata: Mapping[str, Any],
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    analyzer_path = REPO_ROOT / "src/aerial_drop/flutas_source_analyzer.py"
    if _sha256_bytes(analyzer_path.read_bytes()) != ANALYZER_SHA256:
        raise OutputCheckError("local v1.2 analyzer differs from its pinned implementation")
    cells: dict[tuple[str, ...], int] = {}
    for kind in ("phase", "velocity"):
        for key in analyzer._expected_audit_keys(kind):
            cells[key] = analyzer._expected_scan_cell_count(key, frozenset(), frozenset())
    table_files = {
        analyzer.PHASE_FILE: rows_by_file["phase_property"],
        analyzer.VELOCITY_FILE: rows_by_file["boundary_velocity"],
        analyzer.TIMESTEP_FILE: rows_by_file["timestep_restriction"],
    }
    manifest = {
        "manifest_schema": analyzer.MANIFEST_SCHEMA,
        "producer_schema": analyzer.PRODUCER_SCHEMA,
        "schema_sha256": analyzer.SCHEMA_SHA256_PIN,
        "candidate_sha256": CANDIDATE_RECEIPT_SHA256,
        "image_digest": IMAGE_DIGEST,
        "case_id": CASE_ID,
        "input_sha256": dict(input_hashes),
        "analyzer_sha256": ANALYZER_SHA256,
        "run_status": "completed",
        "solver_exit_code": 0,
        "stop_reason": "normal_completion",
        "state_count": 15,
        "interval_count": 14,
        "completed_interval_count": 14,
        "stop_state_index": "not_applicable",
        "stop_interval_index": "not_applicable",
        "stop_stage_id": "not_applicable",
        "final_time_s": repr(float(inputs["time_start_s"]) + 14 * float(inputs["fixed_step_s"])),
        "files_sha256": {name: _sha256_bytes(data) for name, data in table_files.items()},
        "row_counts": {
            analyzer.PHASE_FILE: 672,
            analyzer.VELOCITY_FILE: 516,
            analyzer.TIMESTEP_FILE: 15,
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
        "resources": dict(run_metadata["resources"]),
        "pressure_solver": {
            "kind": "direct_fft_xy_tridiagonal_z",
            "iterative_pressure_iterations": "not_applicable",
            "iterative_pressure_residual": "not_applicable",
            "reason": "The pinned pressure path uses direct FFT solves in x/y and a tridiagonal z solve; continuity and projection are recorded directly.",
        },
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        + b"\n"
    )
    pins = analyzer.ExpectedProvenance(
        manifest_sha256=_sha256_bytes(manifest_bytes),
        schema_sha256=analyzer.SCHEMA_SHA256_PIN,
        candidate_sha256=CANDIDATE_RECEIPT_SHA256,
        image_digest=IMAGE_DIGEST,
        case_id=CASE_ID,
        input_sha256=input_hashes,
        analyzer_sha256=ANALYZER_SHA256,
        expected_timestep_inputs=inputs,
        expected_scan_cells=cells,
        slot_masks=(),
        active_schedule_indices=frozenset(),
    )
    report = analyzer.analyze_bundle(manifest_bytes, table_files, pins)
    if (
        report.structural_disposition != "complete"
        or report.evidence_disposition != "complete"
        or report.issue_codes
        or report.row_counts
        != {
            analyzer.PHASE_FILE: 672,
            analyzer.VELOCITY_FILE: 516,
            analyzer.TIMESTEP_FILE: 15,
        }
    ):
        raise OutputCheckError(f"pinned v1.2 analyzer rejected output tables: {report.issue_codes}")
    return {
        "structural_disposition": report.structural_disposition,
        "evidence_disposition": report.evidence_disposition,
        "decision": report.decision,
        "issue_codes": list(report.issue_codes),
        "row_counts": dict(report.row_counts),
        "timestep_rows_checked": report.timestep_rows_checked,
    }


def _preflight_destinations(bundle_root: Path, items: list[dict[str, Any]]) -> dict[str, Path]:
    destinations: dict[str, Path] = {}
    for item in items:
        relative = _relative_path(item.get("canonical_path"), "canonical_path")
        if relative.as_posix() in destinations:
            raise OutputCheckError(f"duplicate canonical destination: {relative}")
        destination = bundle_root.joinpath(*relative.parts)
        cursor = bundle_root
        for part in relative.parts[:-1]:
            cursor = cursor / part
            try:
                info = cursor.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(info.st_mode):
                raise OutputCheckError(f"canonical parent is not a real directory: {cursor}")
        if destination.exists() or destination.is_symlink():
            raise OutputCheckError(
                f"canonical target already exists; refusing overwrite: {destination}"
            )
        destinations[relative.as_posix()] = destination
    return destinations


def _copy_exact(source: Path, destination: Path, expected_digest: str, expected_size: int) -> str:
    current = destination.parent
    missing: list[Path] = []
    while not current.exists():
        missing.append(current)
        current = current.parent
    if current.is_symlink() or not current.is_dir():
        raise OutputCheckError(f"canonical parent chain is unsafe: {current}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        out_fd = os.open(destination, flags, 0o444)
    except OSError as exc:
        raise OutputCheckError(f"cannot create new canonical copy {destination}: {exc}") from exc
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    size = 0
    try:
        in_fd = os.open(source, source_flags)
        with os.fdopen(in_fd, "rb") as src, os.fdopen(out_fd, "wb") as dst:
            opened = os.fstat(src.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise OutputCheckError(f"native output changed before copy: {source}")
            for block in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(block)
                digest.update(block)
                size += len(block)
            dst.flush()
            os.fsync(dst.fileno())
    except Exception:
        # Preserve any partial copy as evidence; it is not a passing bundle.
        raise
    if size != expected_size or digest.hexdigest() != expected_digest:
        raise OutputCheckError(f"native bytes changed during canonical copy: {source}")
    copied_digest, copied_size = _hash_regular(destination, "canonical copy")
    if copied_size != expected_size or copied_digest != expected_digest:
        raise OutputCheckError(f"canonical byte identity check failed: {destination}")
    native_digest, native_size = _hash_regular(source, "native output after copy")
    if native_size != copied_size or native_digest != copied_digest:
        raise OutputCheckError(f"native/canonical SHA-256 mismatch: {source}")
    os.chmod(destination, 0o444)
    return copied_digest


def check_bundle(bundle_root: Path, map_path: Path | None = None) -> dict[str, Any]:
    """Validate outputs and create only new canonical byte-for-byte copies."""
    bundle_root = Path(bundle_root).absolute()
    try:
        root_info = bundle_root.lstat()
    except OSError as exc:
        raise OutputCheckError(f"bundle root is unavailable: {bundle_root}") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise OutputCheckError("bundle root must be a real directory")
    bundle_root = bundle_root.resolve(strict=True)
    map_value, _ = _load_map(bundle_root, map_path)
    items = map_value["producer_files"]
    expected_native = _check_native_roster(bundle_root, items)

    launch_manifest = _strict_json(
        _read_regular(bundle_root / "metadata/run-manifest.json", "launch run manifest"),
        "launch run manifest",
    )
    input_hashes = launch_manifest.get("input_sha256")
    if input_hashes != INPUT_SHA256:
        raise OutputCheckError(
            "launch manifest input hash map differs from the frozen dry_four triplet"
        )
    _check_staged_inputs(bundle_root)
    _check_work_area(bundle_root)

    receipt_path = bundle_root / "metadata/candidate-build.json"
    receipt_raw = _read_regular(receipt_path, "candidate receipt")
    receipt_hash = _sha256_bytes(receipt_raw)
    if receipt_hash != CANDIDATE_RECEIPT_SHA256:
        raise OutputCheckError("candidate receipt differs from the exact reviewed candidate6")
    receipt = _strict_json(receipt_raw, "candidate receipt")
    if receipt.get("candidate_id") != CANDIDATE_ID:
        raise OutputCheckError("candidate receipt ID differs from the frozen candidate6 build")

    normal_metadata = _derive_normal_metadata(bundle_root)
    launch_result = _strict_json(
        _read_regular(bundle_root / "metadata/launch-result.json", "launch result"),
        "launch result",
    )
    if launch_result.get("solver_exit_status") != 0:
        raise OutputCheckError("launch result does not record normal solver exit status 0")

    raw_by_id: dict[str, bytes] = {}
    digest_by_id: dict[str, str] = {}
    size_by_id: dict[str, int] = {}
    rows_by_id: dict[str, list[list[str]]] = {}
    for item in items:
        path = expected_native[item["native_path"]]
        digest, size = _hash_regular(path, f"native output {item['id']}")
        size_policy = item["size_bytes"]
        expected_size = size_policy.get("normal_expected_bytes")
        maximum = size_policy.get("frozen_max_bytes")
        if expected_size is not None and size != expected_size:
            raise OutputCheckError(
                f"{item['id']} size {size} differs from exact normal size {expected_size}"
            )
        if type(maximum) is not int or size > maximum:
            raise OutputCheckError(f"{item['id']} exceeds or lacks its frozen byte cap")
        if item["id"] == "timestep_restriction" and size > 5528:
            raise OutputCheckError(
                "timestep-restriction.csv exceeds the frozen 5,528-byte normal cap"
            )
        shape = item.get("shape")
        if isinstance(shape, list) and item.get("dtype") == "IEEE-754 binary64":
            if item.get("endianness") != "little" or any(
                type(d) is not int or d <= 0 for d in shape
            ):
                raise OutputCheckError(f"{item['id']} binary shape/endian declaration is invalid")
            expected_binary_size = math.prod(shape) * 8
            if size != expected_binary_size or expected_size != expected_binary_size:
                raise OutputCheckError(f"{item['id']} binary byte size does not match shape/endian")
        if item["id"] in V03_HEADERS:
            cap = item.get("per_record_policy_cap_bytes")
            if type(cap) is not int or any(
                len(record) > cap for record in path.read_bytes().splitlines()
            ):
                raise OutputCheckError(f"{item['id']} record exceeds its frozen byte cap")
            raw = path.read_bytes()
            rows_by_id[item["id"]] = _check_v03(item, raw)
            raw_by_id[item["id"]] = raw
        elif item["id"] in V12_SPECS:
            spec = V12_SPECS[item["id"]]
            raw = path.read_bytes()
            cap = item.get("per_record_policy_cap_bytes")
            if type(cap) is not int or any(len(record) > cap for record in raw.splitlines()):
                raise OutputCheckError(f"{item['id']} record exceeds its frozen byte cap")
            parsed = _csv_rows(raw, spec[1], item["id"], spec[2])
            raw_by_id[item["id"]] = raw
            rows_by_id[item["id"]] = parsed
            if len(parsed) != spec[2]:
                raise OutputCheckError(f"{item['id']} row count differs from its frozen count")
        elif item["id"] in NATIVE_TEXT_OUTPUTS:
            raw = _read_regular(path, f"native output {item['id']}")
            if len(raw) != size or _sha256_bytes(raw) != digest:
                raise OutputCheckError(f"{item['id']} changed while its text bytes were read")
            raw_by_id[item["id"]] = raw
        elif item["id"] == "timestep_inputs_json":
            raw = path.read_bytes()
            inputs = _validate_dry_timestep_inputs(_strict_json(raw, "timestep-inputs.json"))
            raw_by_id[item["id"]] = raw
            digest_by_id[item["id"]] = digest

        digest_by_id[item["id"]] = digest
        size_by_id[item["id"]] = size

    inputs = _validate_dry_timestep_inputs(
        _strict_json(raw_by_id["timestep_inputs_json"], "timestep-inputs.json")
    )
    _check_native_clock_joins(rows_by_id["mass_ledger"], rows_by_id["velocity_audit"], inputs)
    _check_native_state_outputs(raw_by_id, inputs)
    v12_raw = {
        "phase_property": raw_by_id["phase_property"],
        "boundary_velocity": raw_by_id["boundary_velocity"],
        "timestep_restriction": raw_by_id["timestep_restriction"],
    }
    analyzer_report = _analyze_v12(v12_raw, inputs, normal_metadata, input_hashes)
    destinations = _preflight_destinations(bundle_root, items)
    canonical_hashes: dict[str, str] = {}
    for item in items:
        native = expected_native[item["native_path"]]
        canonical = destinations[item["canonical_path"]]
        canonical_hashes[item["id"]] = _copy_exact(
            native,
            canonical,
            digest_by_id[item["id"]],
            size_by_id[item["id"]],
        )
    if canonical_hashes != digest_by_id:
        raise OutputCheckError("native and canonical digest inventories differ")
    return {
        "status": "complete",
        "case_id": CASE_ID,
        "candidate_id": CANDIDATE_ID,
        "output_map_sha256": MAP_SHA256,
        "native_file_count": len(items),
        "native_bytes": sum(expected_native[item["native_path"]].stat().st_size for item in items),
        "sha256_by_id": digest_by_id,
        "canonical_sha256_by_id": canonical_hashes,
        "v03_data_rows": V03_ROW_COUNTS,
        "v12_analysis": analyzer_report,
        "clock_semantics": {
            "native_mass_velocity": "U0 starts at captured time_start_s; each later row uses the source accumulated time += f_t12 sequence",
            "v1_2_timestep": "independent state-index clock time_start_s + state_index * fixed_step_s",
            "native_and_v1_2_clocks_collapsed": False,
        },
        "scope_limit": "retained bytes and frozen diagnostic predicates only; no flow/physics validation",
        "normal_manifest_action": "caller may invoke the existing candidate6 adapter only after this report passes",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="completed dry_four run bundle")
    parser.add_argument("--map", dest="map_path", type=Path, help="optional matching frozen map")
    args = parser.parse_args(argv)
    try:
        report = check_bundle(args.bundle, args.map_path)
    except (OSError, KeyError, TypeError, ValueError, OutputCheckError) as exc:
        parser.exit(2, f"dry_four output check failed: {exc}\n")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
