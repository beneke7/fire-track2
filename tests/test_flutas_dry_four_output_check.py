from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flutas_dry_four_output_check as output_check  # noqa: E402

from aerial_drop import flutas_source_analyzer as analyzer  # noqa: E402


def _f24(value: float) -> str:
    mantissa, exponent = f"{value:.16E}".split("E")
    sign = exponent[0]
    number = int(exponent[1:])
    formatted = f"{mantissa}E{sign}{number:03d}"
    return f" {formatted}" if len(formatted) < 24 else formatted


def _v03_table(file_id: str) -> bytes:
    header = output_check.V03_HEADERS[file_id]
    lines = [",".join(header)]
    if file_id == "source_flux":
        pass
    elif file_id == "source_offmask":
        lines.extend(f"{i},{_f24(0)},{_f24(0)}" for i in range(14))
    elif file_id == "rate_check":
        lines.extend(f"{i}," + ",".join([_f24(0)] * 6) for i in range(14))
    elif file_id == "boundary_ledger":
        lines.extend(f"{i}," + ",".join([_f24(0)] * 12) for i in range(15))
    elif file_id == "mass_ledger":
        native_times = [0.0]
        for interval in range(14):
            if interval == 0:
                f_t1 = 1.0 * 0.0001
                f_t2 = 0.0 * 0.0001
            else:
                f_t1 = (1.0 + 0.5 * (0.0001 / 0.0001)) * 0.0001
                f_t2 = (-0.5 * (0.0001 / 0.0001)) * 0.0001
            native_times.append(native_times[-1] + (f_t1 + f_t2))
        lines.extend(f"{i},{_f24(native_times[i])}," + ",".join([_f24(0)] * 18) for i in range(15))
    elif file_id == "velocity_audit":
        native_times = [0.0]
        for interval in range(14):
            if interval == 0:
                f_t1 = 1.0 * 0.0001
                f_t2 = 0.0 * 0.0001
            else:
                f_t1 = (1.0 + 0.5 * (0.0001 / 0.0001)) * 0.0001
                f_t2 = (-0.5 * (0.0001 / 0.0001)) * 0.0001
            native_times.append(native_times[-1] + (f_t1 + f_t2))
        for i in range(15):
            fields = [
                str(i),
                str(i),
                _f24(native_times[i]),
                _f24(0.0001),
                "537600",
                _f24(0),
                "0",
                "0",
                _f24(0),
                *([_f24(0)] * 13),
            ]
            lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode("ascii")


def _phase_rows() -> list[dict[str, str]]:
    rows = []
    for interval in range(14):
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
                            "scanned_cells": str(
                                analyzer._expected_scan_cell_count(key, frozenset(), frozenset())
                            ),
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
    rows = []

    def add(state: int, interval: int, stage: str) -> None:
        for face, source_class in analyzer.VELOCITY_FACE_CLASSES:
            for component in analyzer.COMPONENTS:
                key = ("velocity", str(state), str(interval), stage, face, source_class, component)
                rows.append(
                    {
                        "state_index": str(state),
                        "transport_interval_index": str(interval),
                        "stage_id": stage,
                        "face": face,
                        "source_class": source_class,
                        "component": component,
                        "scanned_cells": str(
                            analyzer._expected_scan_cell_count(key, frozenset(), frozenset())
                        ),
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
    for interval in range(14):
        add(interval, interval, "pre_vof")
        add(interval + 1, interval, "projection_override")
        add(interval + 1, interval, "corrected_endpoint")
    return rows


def _csv_bytes(header: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    lines = [",".join(header)]
    lines.extend(",".join(row[key] for key in header) for row in rows)
    return ("\n".join(lines) + "\n").encode("ascii")


def _pad_v12_to_size(
    raw: bytes, header: tuple[str, ...], rows: list[dict[str, str]], target: int
) -> bytes:
    if len(raw) > target:
        raise AssertionError(f"fixture CSV baseline {len(raw)} exceeds frozen size {target}")
    extra = target - len(raw)
    if extra == 0:
        return raw
    for row in rows:
        if extra == 0:
            break
        index = header.index("max_abs_error")
        amount = min(extra, 200)
        token = "-0" if amount == 1 else "0." + "0" * (amount - 1)
        row[header[index]] = token
        extra -= amount
    if extra:
        raise AssertionError("fixture size needs more padding than its rows can accept")
    result = _csv_bytes(header, rows)
    if len(result) != target:
        raise AssertionError(f"fixture padding made {len(result)} bytes; expected {target}")
    return result


def _timestep_inputs() -> dict[str, object]:
    eps = math.ulp(1.0)
    dzc, dzf = output_check._expected_dry_four_vertical_grid()
    return {
        "time_scheme": "ab2",
        "time_start_s": "0",
        "real_kind": 8,
        "precision_digits": 15,
        "machine_epsilon": repr(eps),
        "small_s_inv": repr(eps * 10.0**7.5),
        "cfl_c": "1.0000000000000000E+000",
        "cfl_d": "1.6666666666666666E-001",
        "rho1_kg_m3": "1.0000000000000000E+003",
        "rho2_kg_m3": "1.0000000000000000E+000",
        "mu1_pa_s": "1.0000000000000000E-003",
        "mu2_pa_s": "1.8000000000000000E-005",
        "dx_m": "2.5000000000000000E-002",
        "dy_m": "2.5000000000000000E-002",
        "dz_m": "2.5000000000000000E-002",
        "dxi_m_inv": "4.0000000000000000E+001",
        "dyi_m_inv": "4.0000000000000000E+001",
        "dzi_m_inv": "4.0000000000000000E+001",
        "dzc_m": [repr(value) for value in dzc],
        "dzf_m": [repr(value) for value in dzf],
        "dzci_m_inv": [repr(1.0 / value) for value in dzc],
        "dzfi_m_inv": [repr(1.0 / value) for value in dzf],
        "sigma_n_m": "0",
        "gravity_m_s2": ["0", "0", "0"],
        "fixed_step_factor": "2.0000000000000001E-001",
        "fixed_step_s": "1.0000000000000000E-004",
    }


def _timestep_csv(inputs: dict[str, object]) -> bytes:
    rows = []
    for state in range(15):
        raw = analyzer.Decimal("0") if hasattr(analyzer, "Decimal") else 0
        terms = analyzer._checked_timestep_expectations(inputs, raw)
        dt = float(inputs["fixed_step_s"])
        dtmax = float(terms["dtmax_s"])
        rows.append(
            {
                "state_index": str(state),
                "time_s": repr(float(inputs["time_start_s"]) + state * dt),
                "dt_s": repr(dt),
                "dtic_raw_s_inv": "0",
                "dtic_used_s_inv": repr(float(terms["dtic_used_s_inv"])),
                "zero_advection_fallback": "true",
                "nu_max_m2_s": repr(float(terms["nu_max_m2_s"])),
                "h_min_m": repr(float(terms["h_min_m"])),
                "dlmini_m_inv": repr(float(terms["dlmini_m_inv"])),
                "dtiv_s_inv": repr(float(terms["dtiv_s_inv"])),
                "dtik_s_inv": repr(float(terms["dtik_s_inv"])),
                "dtig_s_inv": repr(float(terms["dtig_s_inv"])),
                "capillary_active": "false",
                "dtmax_s": repr(dtmax),
                "fixed_step_factor": repr(float(inputs["fixed_step_factor"])),
                "dt_over_dtmax": repr(dt / dtmax),
                "guard_pass": "not_applicable" if state == 14 else "true",
            }
        )
    return _csv_bytes(analyzer.TIMESTEP_HEADER, rows)


def _make_bundle(root: Path) -> Path:
    bundle = root / "dry-four-fixture"
    bundle.mkdir()
    for directory in ("metadata", "dry_four", "work/data"):
        (bundle / directory).mkdir(parents=True, exist_ok=True)
    map_raw = (ROOT / "experiments/dry-output-map.json").read_bytes()
    (bundle / "metadata/dry-output-map.json").write_bytes(map_raw)
    manifest = {
        "output_map": {"sha256": output_check.MAP_SHA256},
        "input_sha256": output_check.INPUT_SHA256,
    }
    (bundle / "metadata/run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "metadata/launch-result.json").write_text(
        '{"solver_exit_status":0}', encoding="utf-8"
    )
    receipt = ROOT / "results/runs/candidate6-oci-layout-20260928T1139Z/candidate-build.json"
    shutil.copyfile(receipt, bundle / "metadata/candidate-build.json")
    for name in output_check.INPUT_SHA256:
        shutil.copyfile(
            ROOT / "containers/flutas/candidate5/cases/source_boundary/dry_four" / name,
            bundle / "dry_four" / name,
        )
        (bundle / "dry_four" / name).chmod(0o444)
        # Docker may leave empty writable mountpoint files when nested mounts
        # are removed; the immutable dry_four copies are the authoritative bytes.
        (bundle / "work" / name).write_bytes(b"")

    map_value = json.loads(map_raw)
    for item in map_value["producer_files"]:
        path = bundle / "work" / item["native_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        file_id = item["id"]
        expected_size = item["size_bytes"]["normal_expected_bytes"]
        if file_id in output_check.V03_HEADERS:
            raw = _v03_table(file_id)
        elif file_id == "phase_property":
            rows = _phase_rows()
            raw = _csv_bytes(analyzer.PHASE_HEADER, rows)
            raw = _pad_v12_to_size(raw, analyzer.PHASE_HEADER, rows, expected_size)
        elif file_id == "boundary_velocity":
            rows = _velocity_rows()
            raw = _csv_bytes(analyzer.VELOCITY_HEADER, rows)
            raw = _pad_v12_to_size(raw, analyzer.VELOCITY_HEADER, rows, expected_size)
        elif file_id == "timestep_restriction":
            raw = _timestep_csv(_timestep_inputs())
        elif file_id == "timestep_inputs_json":
            raw = (
                json.dumps(_timestep_inputs(), sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        elif file_id == "time_out":
            times = output_check._native_clock_values(_timestep_inputs())
            raw = (
                "\n".join(
                    "".join(
                        output_check._fortran_e15_7(value)
                        for value in (float(state), 0.0001, times[state])
                    )
                    for state in range(1, 15)
                )
                + "\n"
            ).encode("ascii")
        elif file_id == "pos_vt":
            times = output_check._native_clock_values(_timestep_inputs())
            raw = (
                "\n".join(
                    output_check._fortran_e15_7(times[state]) + "NaN".rjust(15) * 6
                    for state in range(1, 15)
                )
                + "\n"
            ).encode("ascii")
        elif file_id == "vof_info":
            times = output_check._native_clock_values(_timestep_inputs())
            raw = (
                "\n".join(
                    "".join(
                        output_check._fortran_e15_7(value)
                        for value in (float(state), 0.0001, times[state], 0.0, 0.0, 0.0)
                    )
                    for state in range(15)
                )
                + "\n"
            ).encode("ascii")
        elif file_id == "scalar_out":
            times = output_check._native_clock_values(_timestep_inputs())
            raw = (
                output_check._fortran_e15_7(times[14])
                + output_check._fortran_e15_7(0.0001)
                + f"{14:08d}".rjust(9)
                + "\n"
            ).encode("ascii")
        elif file_id == "restart_checkpoints":
            times = output_check._native_clock_values(_timestep_inputs())
            raw = (
                "".join(output_check._fortran_e15_7(value) for value in (14.0, times[14], 1.0))
                + "\n"
            ).encode("ascii")
        elif file_id == "performance":
            lines = []
            for state in range(1, 15):
                fields = [float(state), 0.0, 0.0, 0.0, 0.0001]
                lines.append("".join(f"{value:15.7E}" for value in fields))
            raw = ("\n".join(lines) + "\n").encode("ascii")
        elif item.get("dtype") == "IEEE-754 binary64":
            with path.open("wb") as stream:
                stream.truncate(expected_size)
            continue
        else:
            raw = b"x" * expected_size
        path.write_bytes(raw)
        if expected_size is not None and path.stat().st_size != expected_size:
            raise AssertionError(f"fixture {file_id} size {path.stat().st_size} != {expected_size}")
    return bundle


def test_native_output_map_names_initial_vof_file():
    output_map = json.loads((ROOT / "experiments/dry-output-map.json").read_bytes())
    vof = next(item for item in output_map["producer_files"] if item["id"] == "initial_3d_vof_fld")
    assert vof["native_path"] == "data/vof_fld_000000000.bin"
    pos_vt = next(item for item in output_map["producer_files"] if item["id"] == "pos_vt")
    assert pos_vt["native_path"] == "data/pos_vt.out"


def test_empty_phase_position_velocity_requires_only_expected_nan_fields():
    times = output_check._native_clock_values(_timestep_inputs())
    raw = (
        "\n".join(
            output_check._fortran_e15_7(times[state]) + "NaN".rjust(15) * 6
            for state in range(1, 15)
        )
        + "\n"
    ).encode("ascii")
    output_check._check_empty_phase_position_velocity(raw, times)

    malformed = raw.replace(b"            NaN", b"  0.0000000E+00", 1)
    with pytest.raises(output_check.OutputCheckError, match="zero-volume centroid fields NaN"):
        output_check._check_empty_phase_position_velocity(malformed, times)


def test_success_bundle_checks_rows_and_copies_native_bytes(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    resources = {
        "ram_samples": [{"elapsed_s": "0", "rss_bytes": "1024"}],
        "vram_samples": [{"elapsed_s": "0", "used_bytes": "0"}],
        "step_timing_samples": [{"step": 1, "elapsed_s": "0.1"}, {"step": 14, "elapsed_s": "1.4"}],
    }
    monkeypatch.setattr(
        output_check, "_derive_normal_metadata", lambda _bundle: {"resources": resources}
    )
    report = output_check.check_bundle(bundle)
    assert report["status"] == "complete"
    assert report["native_file_count"] == 38
    assert report["v03_data_rows"] == output_check.V03_ROW_COUNTS
    assert report["v12_analysis"]["row_counts"] == {
        analyzer.PHASE_FILE: 672,
        analyzer.VELOCITY_FILE: 516,
        analyzer.TIMESTEP_FILE: 15,
    }
    for item in json.loads((bundle / "metadata/dry-output-map.json").read_bytes())[
        "producer_files"
    ]:
        native = bundle / "work" / item["native_path"]
        canonical = bundle / item["canonical_path"]
        assert (
            hashlib.sha256(native.read_bytes()).digest()
            == hashlib.sha256(canonical.read_bytes()).digest()
        )
    assert (bundle / "timestep-inputs.json").read_bytes() == (
        bundle / "work/data/restas_timestep-inputs.json"
    ).read_bytes()


def test_native_roster_rejects_unlisted_file(tmp_path):
    work_data = tmp_path / "work/data"
    work_data.mkdir(parents=True)
    (work_data / "rogue.out").write_bytes(b"extra")
    with pytest.raises(output_check.OutputCheckError, match="unlisted native solver output"):
        output_check._check_native_roster(tmp_path, [{"native_path": "data/grid.bin"}])


def test_bundle_root_symlink_is_rejected(tmp_path):
    real_bundle = tmp_path / "real-bundle"
    real_bundle.mkdir()
    linked_bundle = tmp_path / "linked-bundle"
    linked_bundle.symlink_to(real_bundle, target_is_directory=True)
    with pytest.raises(output_check.OutputCheckError, match="real directory"):
        output_check.check_bundle(linked_bundle)


def _replace_csv_field(
    path: Path, header: tuple[str, ...], state: int, field: str, replacement: str
) -> None:
    lines = path.read_bytes().splitlines()
    values = lines[state + 1].decode("ascii").split(",")
    index = header.index(field)
    assert len(values[index]) == len(replacement)
    values[index] = replacement
    lines[state + 1] = ",".join(values).encode("ascii")
    path.write_bytes(b"\n".join(lines) + b"\n")


def _replace_e15_field(path: Path, row_index: int, field_index: int, replacement: str) -> None:
    assert len(replacement) == 15
    lines = path.read_bytes().splitlines()
    start = field_index * 15
    assert len(lines[row_index][start : start + 15]) == 15
    lines[row_index] = (
        lines[row_index][:start] + replacement.encode("ascii") + lines[row_index][start + 15 :]
    )
    path.write_bytes(b"\n".join(lines) + b"\n")


def _patch_success_metadata(monkeypatch) -> None:
    resources = {
        "ram_samples": [{"elapsed_s": "0", "rss_bytes": "1024"}],
        "vram_samples": [{"elapsed_s": "0", "used_bytes": "0"}],
        "step_timing_samples": [
            {"step": 1, "elapsed_s": "0.1"},
            {"step": 14, "elapsed_s": "1.4"},
        ],
    }
    monkeypatch.setattr(
        output_check,
        "_derive_normal_metadata",
        lambda _bundle: {"resources": resources},
    )


def test_native_clock_substitution_rejected_even_when_both_ledgers_match(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    _patch_success_metadata(monkeypatch)
    mass = bundle / "work/data/restas_mass-ledger.csv"
    velocity = bundle / "work/data/restas_velocity-audit.csv"
    mass_rows = mass.read_text(encoding="ascii").splitlines()
    assert mass_rows[3].split(",")[1] == _f24(0.00020000000000000004)
    assert mass_rows[15].split(",")[1] == _f24(0.0014000000000000004)
    # Replace accumulated U7 with its index-derived value in both native tables.
    derived_u7 = output_check._fortran_es24_16e3(7 * 0.0001)
    _replace_csv_field(mass, output_check.V03_HEADERS["mass_ledger"], 7, "time_s", derived_u7)
    _replace_csv_field(
        velocity, output_check.V03_HEADERS["velocity_audit"], 7, "time_s", derived_u7
    )
    with pytest.raises(output_check.OutputCheckError, match="native accumulated.*differs"):
        output_check.check_bundle(bundle)


@pytest.mark.parametrize("table", ["velocity_audit", "timestep_restriction"])
def test_fixed_dt_substitution_rejected(tmp_path, monkeypatch, table):
    bundle = _make_bundle(tmp_path)
    _patch_success_metadata(monkeypatch)
    if table == "velocity_audit":
        path = bundle / "work/data/restas_velocity-audit.csv"
        header = output_check.V03_HEADERS[table]
        replacement = output_check._fortran_es24_16e3(0.0002)
    else:
        path = bundle / "work/data/restas_timestep-restriction.csv"
        header = analyzer.TIMESTEP_HEADER
        replacement = "0.0002"
    _replace_csv_field(path, header, 4, "dt_s", replacement)
    with pytest.raises(output_check.OutputCheckError, match="dt_s|TIMESTEP_INPUT_MISMATCH"):
        output_check.check_bundle(bundle)


@pytest.mark.parametrize("key", ["dzc_m", "dzf_m", "dzci_m_inv", "dzfi_m_inv"])
def test_source_derived_vertical_operands_accept_exact_values_and_reject_mutations(key):
    inputs = _timestep_inputs()
    assert output_check._validate_dry_timestep_inputs(inputs) is inputs

    mutated = dict(inputs)
    values = list(inputs[key])
    changed = float(values[17]) + math.ulp(float(values[17]))
    values[17] = repr(changed)
    mutated[key] = values
    inverse_key = {"dzc_m": "dzci_m_inv", "dzf_m": "dzfi_m_inv"}.get(key)
    if inverse_key is not None:
        inverse_values = list(inputs[inverse_key])
        inverse_values[17] = repr(1.0 / changed)
        mutated[inverse_key] = inverse_values
    with pytest.raises(output_check.OutputCheckError, match=key):
        output_check._validate_dry_timestep_inputs(mutated)


@pytest.mark.parametrize(
    ("filename", "row_index", "field_index", "replacement"),
    [
        ("time.out", 6, 2, 0.0008),
        ("vof_info.out", 0, 3, 0.001),
        ("restart_dir/restart_subdir_001/scalar.out", 0, 0, 0.0015),
        ("restart_dir/restart_checkpoints.out", 0, 1, 0.0015),
    ],
)
def test_native_text_state_mutation_rejected(
    tmp_path, monkeypatch, filename, row_index, field_index, replacement
):
    bundle = _make_bundle(tmp_path)
    _patch_success_metadata(monkeypatch)
    path = bundle / "work/data" / filename
    _replace_e15_field(path, row_index, field_index, output_check._fortran_e15_7(replacement))
    with pytest.raises(output_check.OutputCheckError, match="differs from"):
        output_check.check_bundle(bundle)


def test_work_area_rejects_unlisted_file_outside_data(tmp_path):
    work = tmp_path / "work"
    (work / "data").mkdir(parents=True)
    (work / "debug.log").write_bytes(b"unlisted solver output")
    with pytest.raises(output_check.OutputCheckError, match="outside work/data"):
        output_check._check_work_area(tmp_path)


def test_work_area_allows_missing_mountpoints_and_empty_placeholders(tmp_path):
    work = tmp_path / "work"
    (work / "data").mkdir(parents=True)
    output_check._check_work_area(tmp_path)
    (work / "dns.in").write_bytes(b"")
    output_check._check_work_area(tmp_path)


def test_staged_input_leaf_rejects_unlisted_file(tmp_path):
    staged = tmp_path / "dry_four"
    staged.mkdir()
    for name in output_check.INPUT_SHA256:
        path = staged / name
        path.write_bytes(
            (
                ROOT / "containers/flutas/candidate5/cases/source_boundary/dry_four" / name
            ).read_bytes()
        )
        path.chmod(0o444)
    (staged / "restart.bin").write_bytes(b"unlisted")
    with pytest.raises(output_check.OutputCheckError, match="exactly the frozen three files"):
        output_check._check_staged_inputs(tmp_path)


def test_h1_rate_check_rejects_nonzero_dry_rate():
    item = {"id": "rate_check"}
    header = ",".join(output_check.V03_HEADERS["rate_check"])
    rows = ["0,1,0,0,0,0,0"] + [f"{i},0,0,0,0,0,0" for i in range(1, 14)]
    raw = ("\n".join([header, *rows]) + "\n").encode("ascii")
    with pytest.raises(output_check.OutputCheckError, match="must all be zero"):
        output_check._check_v03(item, raw)
