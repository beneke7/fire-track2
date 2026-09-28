#!/usr/bin/env python3
"""CPU-only tests of candidate5 full scans and the pinned timestep helper."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

SOURCE_ROOT = Path(sys.argv[1])
CASE_ROOT = Path(sys.argv[2])
HELPER = Path(sys.argv[3])
sys.argv = sys.argv[:1]

PHASE_HEADER = [
    "state_index", "transport_interval_index", "stage_id", "face", "source_class",
    "property", "scanned_cells", "mismatch_count", "nonfinite_count",
    "max_abs_error", "first_bad_i", "first_bad_j", "first_bad_k", "expected", "observed",
]
VELOCITY_HEADER = [
    "state_index", "transport_interval_index", "stage_id", "face", "source_class",
    "component", "scanned_cells", "mismatch_count", "nonfinite_count",
    "max_abs_error", "first_bad_i", "first_bad_j", "first_bad_k", "requested", "applied",
]
TIMESTEP_HEADER = [
    "state_index", "time_s", "dt_s", "dtic_raw_s_inv", "dtic_used_s_inv",
    "zero_advection_fallback", "nu_max_m2_s", "h_min_m", "dlmini_m_inv", "dtiv_s_inv",
    "dtik_s_inv", "dtig_s_inv", "capillary_active", "dtmax_s",
    "fixed_step_factor", "dt_over_dtmax", "guard_pass",
]
PHASE_PAIRS = [
    ("xlow", "periodic", "xlow_periodic", (0, 0, 0)),
    ("xhigh", "periodic", "xhigh_periodic", (161, 0, 0)),
    ("ylow", "periodic", "ylow_periodic", (1, 0, 0)),
    ("yhigh", "periodic", "yhigh_periodic", (1, 85, 0)),
    ("zlow", "bottom_return", "zlow_bottom_return", (1, 1, 0)),
    ("zhigh", "active_slot", "zhigh_active_slot", (74, 2, 41)),
    ("zhigh", "inactive_slot", "zhigh_inactive_slot", (74, 2, 41)),
    ("zhigh", "top_offmask", "zhigh_top_offmask", (1, 1, 41)),
]
FROZEN_PHASE_FACE_CLASSES = (
    ("xlow", "periodic"),
    ("xhigh", "periodic"),
    ("ylow", "periodic"),
    ("yhigh", "periodic"),
    ("zlow", "bottom_return"),
    ("zhigh", "active_slot"),
    ("zhigh", "inactive_slot"),
    ("zhigh", "top_offmask"),
)
VELOCITY_PAIRS = [
    ("zhigh", "active_slot", "zhigh_active_slot"),
    ("zhigh", "inactive_slot", "zhigh_inactive_slot"),
    ("zhigh", "top_offmask", "zhigh_top_offmask"),
    ("zlow", "bottom_return", "zlow_bottom_return"),
]
PHASE_STAGES = [
    ("pre_vof_x", ("alpha",)),
    ("pre_vof_y", ("alpha",)),
    ("pre_vof_z", ("alpha",)),
    ("pre_momentum", ("alpha", "rho", "mu")),
]
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
TEMP_DIRS: dict[str, tempfile.TemporaryDirectory] = {}
INITGRID_SHA256 = "87010cb1b014355eb70b299264d5b6cd274ab3248c309906a39ac4a66ab8ca28"
RK_SHA256 = "6f86e54d8c95423099526228d72fcb3ee2720c9ac96a0692c486c0fc119a2e42"


def _pinned_uniform_initgrid_operands() -> tuple[list[float], list[float]]:
    """Reproduce initgrid.f90 steps 1-5 for the frozen gr=0, lz=1, nz=40 case."""
    nz = 40
    zf = [0.0] * (nz + 2)
    for k in range(1, nz + 1):
        z0 = (k - 0.0) / (1.0 * nz)
        zf[k] = z0 * 1.0
    zf[0] = 0.0

    dzf = [0.0] * (nz + 2)
    for k in range(1, nz + 1):
        dzf[k] = zf[k] - zf[k - 1]
    dzf[0] = dzf[1]
    dzf[nz + 1] = dzf[nz]

    dzc = [0.0] * (nz + 2)
    for k in range(0, nz + 1):
        dzc[k] = 0.5 * (dzf[k] + dzf[k + 1])
    dzc[nz + 1] = dzc[nz]

    for k in range(1 - 1, 1):
        dzf[k] = dzf[-k + 1]
        dzc[k] = dzc[-k]
    for k in range(nz + 1, nz + 2):
        dzf[k] = dzf[2 * nz - k - 1]
        dzc[k] = dzc[2 * nz - k]
    return dzc, dzf


def _load_independent_analyzer_fixtures():
    root_value = os.environ.get("CANDIDATE5_ANALYZER_ROOT")
    if not root_value:
        return None
    root = Path(root_value)
    analyzer_source = root / "src" / "aerial_drop" / "flutas_source_analyzer.py"
    fixture_source = root / "tests" / "test_flutas_source_analyzer.py"
    if not analyzer_source.is_file() or not fixture_source.is_file():
        return None
    sys.path.insert(0, str(root / "src"))
    # The imported module supplies deterministic bundle fixtures; no pytest
    # behavior is used by this unittest, so make its decorators inert here.
    pytest_stub = types.ModuleType("pytest")
    pytest_stub.mark = types.SimpleNamespace(
        parametrize=lambda *args, **kwargs: (lambda function: function)
    )
    sys.modules.setdefault("pytest", pytest_stub)
    spec = importlib.util.spec_from_file_location(
        "candidate5_independent_analyzer_fixtures", fixture_source
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ANALYZER_FIXTURES = _load_independent_analyzer_fixtures()


def read_csv(path: Path, expected_header: list[str]) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError(f"CSV is missing final LF or has BOM: {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != expected_header:
            raise AssertionError(f"unexpected CSV header at {path}: {reader.fieldnames!r}")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise AssertionError(f"CSV row has missing or extra fields: {path}")
    return rows


def csv_bytes(header: list[str], rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def candidate_source_text() -> str:
    patch_path = Path(__file__).resolve().parent.parent / "source-boundary.patch"
    if patch_path.is_file():
        return patch_path.read_text(encoding="utf-8")
    include_path = SOURCE_ROOT / "src" / "restas_source.inc"
    if include_path.is_file():
        return include_path.read_text(encoding="utf-8")
    raise AssertionError("candidate5 patch and applied source include are unavailable")


def run_helper(
    mode: str,
    case_name: str,
    *args: str,
    succeeds: bool,
    helper_path: Path = HELPER,
) -> tuple[int, Path]:
    temp = tempfile.TemporaryDirectory(prefix="candidate5-observability-")
    root = Path(temp.name)
    prefix = root / "ledger"
    completed = subprocess.run(
        [str(helper_path), mode, case_name, str(prefix), *args],
        cwd=CASE_ROOT / case_name,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if (completed.returncode == 0) != succeeds:
        temp.cleanup()
        raise AssertionError(
            f"helper mode {mode} returned {completed.returncode}; expected success={succeeds}\n"
            f"{completed.stdout}"
        )
    TEMP_DIRS[str(prefix)] = temp
    return completed.returncode, prefix


def _compile_multistate_helper() -> tuple[tempfile.TemporaryDirectory, Path]:
    compiler = shutil.which("mpif90")
    if compiler is None:
        raise unittest.SkipTest("mpif90 is unavailable for the multi-state compiled check")
    temp = tempfile.TemporaryDirectory(prefix="candidate5-multistate-build-")
    build_dir = Path(temp.name)
    src_dir = SOURCE_ROOT / "src"
    test_dir = Path(__file__).resolve().parent
    flags = [
        compiler,
        "-cpp",
        "-D_USE_VOF",
        "-D_DECOMP_X",
        f"-I{build_dir}",
        "-module",
        str(build_dir),
    ]
    sources = (
        (src_dir / "types.f90", "types.o"),
        (src_dir / "common_mpi.f90", "common_mpi.o"),
        (src_dir / "apps/two_phase_inc_isot/param.f90", "param.o"),
        (src_dir / "funcs.f90", "funcs_host.o"),
        (test_dir / "source_boundary_sanity_stub.f90", "sanity_stub.o"),
        (src_dir / "bound.f90", "bound_host.o"),
        (src_dir / "vof.f90", "vof_host.o"),
    )
    objects: list[Path] = []
    for source, object_name in sources:
        obj = build_dir / object_name
        result = subprocess.run(
            [*flags, "-c", str(source), "-o", str(obj)],
            cwd=src_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode:
            temp.cleanup()
            raise AssertionError(f"failed compiling {source.name}:\n{result.stdout}")
        objects.append(obj)

    helper_source = (test_dir / "candidate5_observability_helper.f90").read_text(
        encoding="utf-8"
    )
    declaration = (
        "  real(rp) :: bc_velocity(0:1,3,3),background(3),qtop,qbottom\n"
    )
    declaration_replacement = (
        "  real(rp) :: bc_velocity(0:1,3,3),background(3),qtop,qbottom\n"
        "  real(rp) :: zf_grid(0:nz+1),zc_grid(0:nz+1),z0\n"
        "  real(rp) :: time_clock,f_t1,f_t2,f_t12\n"
    )
    if declaration not in helper_source:
        temp.cleanup()
        raise AssertionError("candidate helper declaration anchor changed")
    helper_source = helper_source.replace(declaration, declaration_replacement, 1)
    uniform_spacing = (
        "  dzc=dl(3)\n"
        "  dzf=dl(3)\n"
        "  dzci=1._rp/dzc\n"
        "  dzfi=1._rp/dzf\n"
    )
    initgrid_spacing = (
        "  ! Pinned initgrid.f90 step order for gr=0, lz=1, nz=40.\n"
        "  zf_grid=0._rp\n"
        "  do k=1,nz\n"
        "    z0=(k-0.0_rp)/(1.0_rp*nz)\n"
        "    zf_grid(k)=z0*1._rp\n"
        "  enddo\n"
        "  zf_grid(0)=0._rp\n"
        "  do k=1,nz\n"
        "    dzf(k)=zf_grid(k)-zf_grid(k-1)\n"
        "  enddo\n"
        "  dzf(0)=dzf(1)\n"
        "  dzf(nz+1)=dzf(nz)\n"
        "  do k=0,nz\n"
        "    dzc(k)=0.5_rp*(dzf(k)+dzf(k+1))\n"
        "  enddo\n"
        "  dzc(nz+1)=dzc(nz)\n"
        "  zc_grid(0)=-dzc(0)/2.0_rp\n"
        "  zf_grid(0)=0.0_rp\n"
        "  do k=1,nz+1\n"
        "    zc_grid(k)=zc_grid(k-1)+dzc(k-1)\n"
        "    zf_grid(k)=zf_grid(k-1)+dzf(k)\n"
        "  enddo\n"
        "  do k=0,0\n"
        "    dzf(k)=dzf(-k+1)\n"
        "    dzc(k)=dzc(-k)\n"
        "  enddo\n"
        "  do k=nz+1,nz+1\n"
        "    dzf(k)=dzf(2*nz-k-1)\n"
        "    dzc(k)=dzc(2*nz-k)\n"
        "  enddo\n"
        "  do k=0,0,-1\n"
        "    zf_grid(k)=zf_grid(k+1)-dzf(k)\n"
        "    zc_grid(k)=zf_grid(k+1)-dzc(k+1)\n"
        "  enddo\n"
        "  do k=nz+1,nz+1\n"
        "    zf_grid(k)=zf_grid(k-1)+dzf(k)\n"
        "    zc_grid(k)=zf_grid(k-1)+dzc(k-1)\n"
        "  enddo\n"
        "  do k=0,nz+1\n"
        "    dzci(k)=1._rp/dzc(k)\n"
        "    dzfi(k)=1._rp/dzf(k)\n"
        "  enddo\n"
    )
    if uniform_spacing not in helper_source:
        temp.cleanup()
        raise AssertionError("candidate helper spacing anchor changed")
    helper_source = helper_source.replace(uniform_spacing, initgrid_spacing, 1)
    multistate_case = (
        "  case('dt-multistate')\n"
        "    call restas_source_write_header(trim(output_prefix))\n"
        "    call restas_source_capture_timestep_inputs(0._rp,dt_fixed,dl,dli,dzc,dzf,dzci,dzfi)\n"
        "    do k=0,nz+1\n"
        "      do j=0,ny+1\n"
        "        do i=0,nx+1\n"
        "          u(i,j,k)=real(4*i-2*j+k,rp)/16000._rp\n"
        "          v(i,j,k)=real(-2*i+4*j+3*k,rp)/32000._rp\n"
        "          w(i,j,k)=real(i-j+2*k,rp)/16000._rp\n"
        "        enddo\n"
        "      enddo\n"
        "    enddo\n"
        "    time_clock=0._rp\n"
        "    call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,time_clock, &\n"
        "      0,.true.,dli,dzci,dzfi,u,v,w)\n"
        "    do interval=1,14\n"
        "      if(interval.eq.1) then\n"
        "        f_t1=1._rp*dt_fixed\n"
        "        f_t2=0._rp*dt_fixed\n"
        "      else\n"
        "        f_t1=(1._rp+0.5_rp*(dt_fixed/dt_fixed))*dt_fixed\n"
        "        f_t2=(-0.5_rp*(dt_fixed/dt_fixed))*dt_fixed\n"
        "      endif\n"
        "      f_t12=f_t1+f_t2\n"
        "      time_clock=time_clock+f_t12\n"
        "      call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,time_clock, &\n"
        "        interval,interval.lt.14,dli,dzci,dzfi,u,v,w)\n"
        "    enddo\n"
        "    call restas_source_close_log()\n"
    )
    default_case = "  case default\n    error stop 'Unknown candidate5 observability test mode'"
    if default_case not in helper_source:
        temp.cleanup()
        raise AssertionError("candidate helper dispatch anchor changed")
    helper_source = helper_source.replace(default_case, multistate_case + default_case, 1)
    variant_source = build_dir / "candidate5_observability_helper_multistate.f90"
    variant_source.write_text(helper_source, encoding="utf-8")
    helper_obj = build_dir / "candidate5_observability_helper_multistate.o"
    compile_result = subprocess.run(
        [*flags, "-I", str(build_dir), "-c", str(variant_source), "-o", str(helper_obj)],
        cwd=src_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if compile_result.returncode:
        temp.cleanup()
        raise AssertionError(f"failed compiling multi-state helper:\n{compile_result.stdout}")
    binary = build_dir / "candidate5_observability_helper_multistate"
    link_result = subprocess.run(
        [compiler, *(str(obj) for obj in objects), str(helper_obj), "-o", str(binary)],
        cwd=src_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if link_result.returncode:
        temp.cleanup()
        raise AssertionError(f"failed linking multi-state helper:\n{link_result.stdout}")
    return temp, binary


def cleanup(prefix: Path) -> None:
    TEMP_DIRS.pop(str(prefix)).cleanup()


def phase_count(face: str, source_class: str, active: bool, slots: int = 4) -> int:
    fixed = {
        ("xlow", "periodic"): 3612,
        ("xhigh", "periodic"): 3612,
        ("ylow", "periodic"): 6720,
        ("yhigh", "periodic"): 6720,
        ("zlow", "bottom_return"): 13440,
    }
    if source_class == "active_slot":
        return slots * 240 if active else 0
    if source_class == "inactive_slot":
        return 0 if active else slots * 240
    if source_class == "top_offmask":
        return 13440 - slots * 240
    return fixed[(face, source_class)]


def velocity_count(source_class: str, active: bool, slots: int = 4) -> int:
    if source_class == "active_slot":
        return slots * 240 if active else 0
    if source_class == "inactive_slot":
        return 0 if active else slots * 240
    if source_class == "top_offmask":
        return 13932 - slots * 240
    return 13932


class Candidate5ScanTests(unittest.TestCase):
    def test_full_phase_and_velocity_scans_emit_all_stage_keys_and_exact_counts(self):
        _status, prefix = run_helper("phase-pass", "quiescent_four", succeeds=True)
        try:
            rows = read_csv(Path(f"{prefix}_phase-property-stage-audit.csv"), PHASE_HEADER)
            self.assertEqual(len(rows), 96)
            expected_groups = [(state, stage) for state in ("1", "2")
                               for stage, _properties in PHASE_STAGES]
            actual_groups = []
            for row in rows:
                key = (row["state_index"], row["stage_id"])
                if not actual_groups or actual_groups[-1] != key:
                    actual_groups.append(key)
            self.assertEqual(actual_groups, expected_groups)
            for state, stage in expected_groups:
                active = state == "2"
                properties = dict(PHASE_STAGES)[stage]
                selected_group = [row for row in rows
                                  if (row["state_index"], row["stage_id"]) == (state, stage)]
                self.assertEqual(len(selected_group), 8 * len(properties))
                expected_order = [
                    (face, source_class, prop)
                    for face, source_class in FROZEN_PHASE_FACE_CLASSES
                    for prop in properties
                ]
                self.assertEqual(
                    [(row["face"], row["source_class"], row["property"])
                     for row in selected_group],
                    expected_order,
                    "phase rows must use the complete frozen v1.2 key order",
                )
                for face, source_class, _pair, _location in PHASE_PAIRS:
                    expected_count = phase_count(face, source_class, active)
                    for prop in properties:
                        row = next(row for row in selected_group
                                   if row["face"] == face
                                   and row["source_class"] == source_class
                                   and row["property"] == prop)
                        self.assertEqual(row["scanned_cells"], str(expected_count))
                        self.assertEqual((row["mismatch_count"], row["nonfinite_count"]), ("0", "0"))
                        self.assertEqual(float(row["max_abs_error"]), 0.0)
                        self.assertEqual(
                            [row["first_bad_i"], row["first_bad_j"], row["first_bad_k"],
                             row["expected"], row["observed"]],
                            ["not_applicable"] * 5,
                        )

            _status, dry_prefix = run_helper("phase-pass-dry", "dry_four", succeeds=True)
            try:
                dry_rows = read_csv(
                    Path(f"{dry_prefix}_phase-property-stage-audit.csv"), PHASE_HEADER
                )
                self.assertEqual(len(dry_rows), 64)
                for row in dry_rows:
                    if row["source_class"] in {"active_slot", "inactive_slot"}:
                        self.assertEqual(row["scanned_cells"], "0")
                    elif row["source_class"] == "top_offmask":
                        self.assertEqual(row["scanned_cells"], "13440")
                    self.assertEqual((row["mismatch_count"], row["nonfinite_count"]), ("0", "0"))
            finally:
                cleanup(dry_prefix)
        finally:
            cleanup(prefix)

        _status, prefix = run_helper("velocity-pass", "quiescent_four", succeeds=True)
        try:
            rows = read_csv(Path(f"{prefix}_boundary-velocity-stage-audit.csv"), VELOCITY_HEADER)
            self.assertEqual(len(rows), 120)
            groups = [("initial_u0", 0, -1)]
            for interval in range(3):
                groups.extend([
                    ("pre_vof", interval, interval),
                    ("projection_override", interval + 1, interval),
                    ("corrected_endpoint", interval + 1, interval),
                ])
            actual_groups = []
            for row in rows:
                key = (row["stage_id"], int(row["state_index"]),
                       int(row["transport_interval_index"]))
                if not actual_groups or actual_groups[-1] != key:
                    actual_groups.append(key)
            self.assertEqual(actual_groups, groups)
            for stage, state, interval in groups:
                active = 2 <= state < 12
                group_rows = [row for row in rows
                              if (row["stage_id"], int(row["state_index"]),
                                  int(row["transport_interval_index"])) == (stage, state, interval)]
                self.assertEqual(len(group_rows), 12)
                for face, source_class, _pair in VELOCITY_PAIRS:
                    for component in ("u", "v", "w"):
                        row = next(row for row in group_rows
                                   if row["face"] == face and row["source_class"] == source_class
                                   and row["component"] == component)
                        self.assertEqual(row["scanned_cells"],
                                         str(velocity_count(source_class, active)))
                        self.assertEqual((row["mismatch_count"], row["nonfinite_count"]), ("0", "0"))
                        self.assertEqual(float(row["max_abs_error"]), 0.0)
                        self.assertEqual(
                            [row["first_bad_i"], row["first_bad_j"], row["first_bad_k"],
                             row["requested"], row["applied"]],
                            ["not_applicable"] * 5,
                        )
        finally:
            cleanup(prefix)

    def test_every_phase_stage_class_and_available_property_records_first_failure(self):
        for stage, properties in PHASE_STAGES:
            for face, source_class, pair, location in PHASE_PAIRS:
                for prop in properties:
                    for fault in ("mismatch", "nan"):
                        with self.subTest(stage=stage, pair=pair, prop=prop, fault=fault):
                            _status, prefix = run_helper(
                                "phase-fault", "quiescent_four", pair, prop, fault, stage,
                                succeeds=False,
                            )
                            try:
                                rows = read_csv(
                                    Path(f"{prefix}_phase-property-stage-audit.csv"), PHASE_HEADER
                                )
                                row = next(row for row in rows
                                           if row["stage_id"] == stage and row["face"] == face
                                           and row["source_class"] == source_class
                                           and row["property"] == prop)
                                self.assertEqual(
                                    (row["first_bad_i"], row["first_bad_j"], row["first_bad_k"]),
                                    tuple(map(str, location)),
                                )
                                if fault == "mismatch":
                                    self.assertEqual((row["mismatch_count"], row["nonfinite_count"]),
                                                     ("1", "0"))
                                    self.assertAlmostEqual(float(row["max_abs_error"]), 0.5)
                                    self.assertTrue(math.isfinite(float(row["observed"])))
                                else:
                                    self.assertEqual((row["mismatch_count"], row["nonfinite_count"]),
                                                     ("0", "1"))
                                    self.assertEqual(row["observed"], "NaN")
                                    self.assertTrue(math.isfinite(float(row["expected"])))
                            finally:
                                cleanup(prefix)

    def test_finite_subtraction_overflow_is_preserved_and_fails_closed(self):
        _status, prefix = run_helper("phase-overflow", "quiescent_four", succeeds=False)
        try:
            path = Path(f"{prefix}_phase-property-stage-audit.csv")
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], ",".join(PHASE_HEADER))
            row = next(line.split(",") for line in lines[1:]
                       if line.split(",")[:6] == ["1", "1", "pre_vof_x", "xlow",
                                                   "periodic", "alpha"])
            self.assertEqual(row[7:9], ["1", "0"])
            self.assertEqual(row[9], "+Inf")
            self.assertEqual((row[10], row[11], row[12]), ("0", "5", "5"))
            self.assertRegex(row[13], NUMBER)
            self.assertRegex(row[14], NUMBER)
            self.assertTrue(math.isinf(float(row[13]) - float(row[14])))
        finally:
            cleanup(prefix)

    def test_every_velocity_face_class_and_component_records_first_failure(self):
        for face, source_class, pair in VELOCITY_PAIRS:
            for component in ("u", "v", "w"):
                for fault in ("mismatch", "nan"):
                    with self.subTest(pair=pair, component=component, fault=fault):
                        _status, prefix = run_helper(
                            "velocity-fault", "quiescent_four", pair, component, fault,
                            succeeds=False,
                        )
                        try:
                            rows = read_csv(
                                Path(f"{prefix}_boundary-velocity-stage-audit.csv"), VELOCITY_HEADER
                            )
                            row = next(row for row in rows
                                       if row["face"] == face and row["source_class"] == source_class
                                       and row["component"] == component)
                            if source_class in {"active_slot", "inactive_slot"}:
                                location = (74, 2, 41 if component in {"u", "v"} else 40)
                            elif source_class == "top_offmask":
                                location = (0, 0, 41 if component in {"u", "v"} else 40)
                            else:
                                location = (0, 0, 0)
                            self.assertEqual(
                                (row["first_bad_i"], row["first_bad_j"], row["first_bad_k"]),
                                tuple(map(str, location)),
                            )
                            if fault == "mismatch":
                                self.assertEqual((row["mismatch_count"], row["nonfinite_count"]),
                                                 ("1", "0"))
                                self.assertAlmostEqual(float(row["max_abs_error"]), 0.5)
                                self.assertTrue(math.isfinite(float(row["applied"])))
                            else:
                                self.assertEqual((row["mismatch_count"], row["nonfinite_count"]),
                                                 ("0", "1"))
                                self.assertEqual(row["applied"], "NaN")
                                self.assertTrue(math.isfinite(float(row["requested"])))
                        finally:
                            cleanup(prefix)

    def test_first_finite_mismatch_is_retained_when_a_later_cell_is_nonfinite(self):
        _status, prefix = run_helper(
            "phase-fault", "quiescent_four", "xlow_periodic", "alpha", "both",
            "pre_vof_x", succeeds=False,
        )
        try:
            rows = read_csv(Path(f"{prefix}_phase-property-stage-audit.csv"), PHASE_HEADER)
            row = next(row for row in rows if row["face"] == "xlow")
            self.assertEqual((row["first_bad_i"], row["first_bad_j"], row["first_bad_k"]),
                             ("0", "0", "0"))
            self.assertEqual((row["mismatch_count"], row["nonfinite_count"]), ("1", "1"))
            self.assertTrue(math.isfinite(float(row["expected"])))
            self.assertTrue(math.isfinite(float(row["observed"])))
        finally:
            cleanup(prefix)

    def test_unknown_stage_and_existing_output_paths_fail_closed(self):
        for mode, filename, header in (
            ("phase-invalid-stage", "_phase-property-stage-audit.csv", PHASE_HEADER),
            ("velocity-invalid-stage", "_boundary-velocity-stage-audit.csv", VELOCITY_HEADER),
        ):
            with self.subTest(mode=mode):
                _status, prefix = run_helper(mode, "quiescent_four", succeeds=False)
                try:
                    self.assertEqual(read_csv(Path(f"{prefix}{filename}"), header), [])
                finally:
                    cleanup(prefix)

        with tempfile.TemporaryDirectory(prefix="candidate5-output-collision-") as temp:
            prefix = Path(temp) / "ledger"
            protected = Path(f"{prefix}_source-flux.csv")
            protected.write_bytes(b"preserve exact existing artifact\n")
            completed = subprocess.run(
                [str(HELPER), "phase-pass", "quiescent_four", str(prefix)],
                cwd=CASE_ROOT / "quiescent_four",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(protected.read_bytes(), b"preserve exact existing artifact\n")

        _status, prefix = run_helper(
            "velocity-fault", "quiescent_four", "zhigh_top_offmask", "u", "both",
            succeeds=False,
        )
        try:
            rows = read_csv(Path(f"{prefix}_boundary-velocity-stage-audit.csv"), VELOCITY_HEADER)
            row = next(row for row in rows if row["face"] == "zhigh"
                       and row["source_class"] == "top_offmask" and row["component"] == "u")
            self.assertEqual((row["first_bad_i"], row["first_bad_j"], row["first_bad_k"]),
                             ("0", "0", "41"))
            self.assertEqual((row["mismatch_count"], row["nonfinite_count"]), ("1", "1"))
            self.assertTrue(math.isfinite(float(row["requested"])))
            self.assertTrue(math.isfinite(float(row["applied"])))
        finally:
            cleanup(prefix)


class Candidate5TimestepTests(unittest.TestCase):
    def timestep_row(self, mode: str, case_name: str, succeeds: bool = True) -> dict[str, str]:
        _status, prefix = run_helper(mode, case_name, succeeds=succeeds)
        try:
            rows = read_csv(Path(f"{prefix}_timestep-restriction.csv"), TIMESTEP_HEADER)
            self.assertEqual(len(rows), 1)
            return dict(rows[0])
        finally:
            cleanup(prefix)

    def test_zero_advection_fallback_capillary_branch_and_full_bound(self):
        zero = self.timestep_row("dt-pass-zero", "quiescent_four")
        self.assertEqual(zero["zero_advection_fallback"], "true")
        self.assertEqual(float(zero["dtic_raw_s_inv"]), 0.0)
        self.assertEqual(float(zero["dtic_used_s_inv"]), 1.0)
        self.assertEqual(zero["capillary_active"], "false")
        self.assertEqual(zero["guard_pass"], "true")
        capillary = self.timestep_row("dt-pass-capillary", "quiescent_four")
        self.assertEqual(capillary["zero_advection_fallback"], "true")
        self.assertEqual(capillary["capillary_active"], "true")
        self.assertAlmostEqual(float(capillary["dtik_s_inv"]),
                               math.sqrt(0.072 / 1.0 * (1.0 / 0.025) ** 3), places=10)
        self.assertEqual(capillary["guard_pass"], "true")
        halo = self.timestep_row("dt-pass-halo-min", "quiescent_four")
        self.assertEqual(float(halo["h_min_m"]), 0.0125)
        self.assertEqual(float(halo["dlmini_m_inv"]), 80.0)
        nu_max = max(0.001 / 1000.0, 1.8e-5)
        self.assertAlmostEqual(float(halo["dtiv_s_inv"]), nu_max * 80.0**2 / (1.0 / 6.0),
                               places=10)

    def test_runtime_timestep_input_capture_keeps_all_actual_vertical_operands(self):
        _status, prefix = run_helper("runtime-inputs", "quiescent_one", succeeds=True)
        try:
            path = Path(f"{prefix}_timestep-inputs.json")
            raw = path.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            value = json.loads(raw)
            self.assertEqual(set(value), {
                "time_scheme", "time_start_s", "real_kind", "precision_digits", "machine_epsilon",
                "small_s_inv", "cfl_c", "cfl_d", "rho1_kg_m3", "rho2_kg_m3", "mu1_pa_s",
                "mu2_pa_s", "dx_m", "dy_m", "dz_m", "dxi_m_inv", "dyi_m_inv", "dzi_m_inv",
                "dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv", "sigma_n_m", "gravity_m_s2",
                "fixed_step_factor", "fixed_step_s",
            })
            self.assertEqual((value["time_scheme"], value["real_kind"], value["precision_digits"]),
                             ("ab2", 8, 15))
            for key in ("dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv"):
                self.assertEqual(len(value[key]), 42)
                self.assertTrue(all(isinstance(item, str) and NUMBER.fullmatch(item)
                                    for item in value[key]))
            self.assertTrue(all(float(item) == 0.025 for item in value["dzf_m"]))
            self.assertTrue(all(float(item) == 40.0 for item in value["dzfi_m_inv"]))
            self.assertEqual(value["gravity_m_s2"], ["0", "0", "0"])
        finally:
            cleanup(prefix)

    def test_pinned_initgrid_fixture_has_nonuniform_binary64_spacing_and_exact_inverses(self):
        initgrid = SOURCE_ROOT / "src" / "initgrid.f90"
        self.assertEqual(hashlib.sha256(initgrid.read_bytes()).hexdigest(), INITGRID_SHA256)
        dzc, dzf = _pinned_uniform_initgrid_operands()
        dzci = [1.0 / value for value in dzc]
        dzfi = [1.0 / value for value in dzf]
        self.assertEqual((len(dzc), len(dzf), len(dzci), len(dzfi)), (42, 42, 42, 42))
        self.assertGreater(len(set(dzf)), 1)
        self.assertGreater(len(set(dzc)), 1)
        self.assertTrue(all(inverse == 1.0 / spacing
                            for inverse, spacing in zip(dzci, dzc, strict=True)))
        self.assertTrue(all(inverse == 1.0 / spacing
                            for inverse, spacing in zip(dzfi, dzf, strict=True)))

        patch_text = candidate_source_text()
        capture = patch_text.split(
            "subroutine restas_source_capture_timestep_inputs", 1
        )[1].split("end subroutine restas_source_capture_timestep_inputs", 1)[0]
        self.assertIn("any(inverse_spacing.ne.1._rp/spacing)", capture)
        self.assertIn("any(dzci.ne.1._rp/dzc)", capture)
        self.assertIn("any(dzfi.ne.1._rp/dzf)", capture)

    def test_timestep_serialization_uses_canonical_real_serializer_for_finite_values(self):
        patch_text = candidate_source_text()
        timestep = patch_text.split(
            "subroutine restas_source_record_timestep_restriction", 1
        )[1].split("end subroutine restas_source_record_timestep_restriction", 1)[0]
        self.assertNotIn("ES24.16E3", timestep)
        self.assertIn("trim(restas_source_real_text(diagnostic_time))", timestep)
        self.assertIn("trim(restas_source_real_text(dtic_raw))", timestep)
        self.assertIn("all_finite=ieee_is_finite(dt).and.ieee_is_finite(time)", timestep)

    def test_staggered_rates_use_each_actual_directional_velocity_term(self):
        row = self.timestep_row("dt-probe", "quiescent_four")
        dx_inv = dy_inv = dzf_inv = dzc_inv = 40.0
        expected = 0.0
        for k in range(1, 41):
            for j in range(1, 85):
                for i in range(1, 161):
                    u = lambda ii, jj, kk: (4 * ii - 2 * jj + kk) / 16.0
                    v = lambda ii, jj, kk: (-2 * ii + 4 * jj + 3 * kk) / 32.0
                    w = lambda ii, jj, kk: (ii - jj + 2 * kk) / 16.0
                    ux = abs(u(i, j, k))
                    vx = 0.25 * abs(v(i, j, k) + v(i, j - 1, k)
                                    + v(i + 1, j, k) + v(i + 1, j - 1, k))
                    wx = 0.25 * abs(w(i, j, k) + w(i, j, k - 1)
                                    + w(i + 1, j, k) + w(i + 1, j, k - 1))
                    dtix = ux * dx_inv + vx * dy_inv + wx * dzf_inv
                    uy = 0.25 * abs(u(i, j, k) + u(i, j + 1, k)
                                    + u(i - 1, j + 1, k) + u(i - 1, j, k))
                    vy = abs(v(i, j, k))
                    wy = 0.25 * abs(w(i, j, k) + w(i, j + 1, k)
                                    + w(i, j + 1, k - 1) + w(i, j, k - 1))
                    dtiy = uy * dx_inv + vy * dy_inv + wy * dzf_inv
                    uz = 0.25 * abs(u(i, j, k) + u(i - 1, j, k)
                                    + u(i - 1, j, k + 1) + u(i, j, k + 1))
                    vz = 0.25 * abs(v(i, j, k) + v(i, j - 1, k)
                                    + v(i, j - 1, k + 1) + v(i, j, k + 1))
                    wz = abs(w(i, j, k))
                    dtiz = uz * dx_inv + vz * dy_inv + wz * dzc_inv
                    expected = max(expected, dtix, dtiy, dtiz)
        self.assertEqual(float(row["dtic_raw_s_inv"]), expected)

    def test_crossflow_guard_failure_is_preserved_and_terminal_state_is_not_consumed(self):
        failed = self.timestep_row("dt-fail-crossflow", "crossflow_four", succeeds=False)
        self.assertEqual(failed["guard_pass"], "false")
        self.assertAlmostEqual(float(failed["dtic_raw_s_inv"]), 2000.0, places=12)
        self.assertEqual(failed["zero_advection_fallback"], "false")
        self.assertGreater(float(failed["dt_s"]),
                           float(failed["fixed_step_factor"]) * float(failed["dtmax_s"]))
        terminal = self.timestep_row("dt-terminal-crossflow", "crossflow_four")
        self.assertEqual(terminal["guard_pass"], "not_applicable")
        self.assertAlmostEqual(float(terminal["dtic_raw_s_inv"]), 2000.0, places=12)

    def test_nonfinite_timestep_ratio_is_preserved_before_fail_closed_abort(self):
        row = self.timestep_row("dt-nonfinite-ratio", "quiescent_four", succeeds=False)
        self.assertTrue(math.isinf(float(row["dt_s"])))
        self.assertTrue(math.isinf(float(row["dt_over_dtmax"])))
        self.assertNotEqual(float(row["dt_over_dtmax"]), float.fromhex("0x1.fffffffffffffp+1023"))

    def test_nonfinite_ab2_rate_is_preserved_without_a_finite_sentinel(self):
        row = self.timestep_row("dt-nonfinite-rate", "quiescent_four", succeeds=False)
        self.assertTrue(math.isinf(float(row["dtic_raw_s_inv"])))
        self.assertTrue(math.isinf(float(row["dtic_used_s_inv"])))
        self.assertNotEqual(float(row["dtic_raw_s_inv"]), float.fromhex("0x1.fffffffffffffp+1023"))

    def test_serialized_finite_values_are_canonical_decimal_tokens(self):
        _status, prefix = run_helper("dt-pass-zero", "quiescent_four", succeeds=True)
        try:
            rows = read_csv(Path(f"{prefix}_timestep-restriction.csv"), TIMESTEP_HEADER)
            self.assertEqual(len(rows), 1)
            for key, value in rows[0].items():
                if key not in {"zero_advection_fallback", "capillary_active", "guard_pass"}:
                    self.assertIsNotNone(NUMBER.fullmatch(value), (key, value))
        finally:
            cleanup(prefix)

    @unittest.skipIf(
        ANALYZER_FIXTURES is None,
        "set CANDIDATE5_ANALYZER_ROOT to run the independent multi-state analyzer check",
    )
    def test_multistate_compiled_candidate_output_matches_frozen_analyzer(self):
        initgrid = SOURCE_ROOT / "src" / "initgrid.f90"
        rk_source = SOURCE_ROOT / "src" / "rk.f90"
        self.assertEqual(hashlib.sha256(initgrid.read_bytes()).hexdigest(), INITGRID_SHA256)
        self.assertEqual(hashlib.sha256(rk_source.read_bytes()).hexdigest(), RK_SHA256)
        build_temp, helper = _compile_multistate_helper()
        try:
            _status, prefix = run_helper(
                "dt-multistate", "quiescent_four", succeeds=True, helper_path=helper
            )
            try:
                output_path = Path(f"{prefix}_timestep-restriction.csv")
                rows = read_csv(output_path, TIMESTEP_HEADER)
                self.assertEqual([row["state_index"] for row in rows],
                                 [str(state) for state in range(15)])
                inputs = json.loads(Path(f"{prefix}_timestep-inputs.json").read_bytes())
                dzc, dzf = _pinned_uniform_initgrid_operands()
                self.assertTrue(all(float(token) == expected
                                    for token, expected in zip(inputs["dzf_m"], dzf, strict=True)))
                self.assertTrue(all(float(token) == expected
                                    for token, expected in zip(inputs["dzc_m"], dzc, strict=True)))
                self.assertTrue(all(float(inverse) == 1.0 / float(spacing)
                                    for inverse, spacing in zip(
                                        inputs["dzfi_m_inv"], inputs["dzf_m"], strict=True
                                    )))
                self.assertTrue(all(float(inverse) == 1.0 / float(spacing)
                                    for inverse, spacing in zip(
                                        inputs["dzci_m_inv"], inputs["dzc_m"], strict=True
                                    )))

                fixed_step = float(inputs["fixed_step_s"])
                time_start = float(inputs["time_start_s"])
                for state, row in enumerate(rows):
                    expected_time = time_start + state * fixed_step
                    self.assertEqual(float(row["time_s"]), expected_time)
                    self.assertIsNotNone(NUMBER.fullmatch(row["time_s"]))
                ab2_times = []
                solver_clock = time_start
                for state in range(15):
                    if state == 1:
                        solver_clock = solver_clock + fixed_step
                    elif state > 1:
                        f_t1 = (1.0 + 0.5 * (fixed_step / fixed_step)) * fixed_step
                        f_t2 = (-0.5 * (fixed_step / fixed_step)) * fixed_step
                        f_t12 = f_t1 + f_t2
                        solver_clock = solver_clock + f_t12
                    ab2_times.append(solver_clock)
                self.assertNotEqual(ab2_times[2], float(rows[2]["time_s"]))

                fixtures = ANALYZER_FIXTURES
                analyzer = fixtures.analyzer
                manifest, files, pins = fixtures._build_bundle(
                    timestep_inputs=inputs,
                    raw_rate=float(rows[0]["dtic_raw_s_inv"]),
                )
                analyzer_root = Path(os.environ["CANDIDATE5_ANALYZER_ROOT"])
                analyzer_hash = hashlib.sha256(
                    (analyzer_root / "src" / "aerial_drop" / "flutas_source_analyzer.py")
                    .read_bytes()
                ).hexdigest()
                manifest_record = json.loads(manifest)
                manifest_record["analyzer_sha256"] = analyzer_hash
                manifest = fixtures._manifest_bytes(manifest_record)
                pins = analyzer.ExpectedProvenance(
                    **{
                        **pins.__dict__,
                        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                        "analyzer_sha256": analyzer_hash,
                    }
                )
                files[analyzer.TIMESTEP_FILE] = output_path.read_bytes()
                manifest, files, pins = fixtures._refresh_bundle(manifest, files, pins)
                report = analyzer.analyze_bundle(manifest, files, pins)
                self.assertEqual(report.structural_disposition, "complete")
                self.assertEqual(report.evidence_disposition, "complete")
                self.assertEqual(report.timestep_rows_checked, 15)

                accumulated_rows = [dict(row) for row in rows]
                for state, row in enumerate(accumulated_rows):
                    row["time_s"] = format(ab2_times[state], ".17g")
                files[analyzer.TIMESTEP_FILE] = csv_bytes(TIMESTEP_HEADER, accumulated_rows)
                manifest, files, pins = fixtures._refresh_bundle(manifest, files, pins)
                rejected = analyzer.analyze_bundle(manifest, files, pins)
                self.assertEqual(rejected.structural_disposition, "fail")
                self.assertIn("TIMESTEP_TIME", rejected.issue_codes)
            finally:
                cleanup(prefix)
        finally:
            build_temp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
