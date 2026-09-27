#!/usr/bin/env python3
"""Independently reconstruct candidate5 binary64 inputs and timestep CSV bytes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
OUT = ANALYSIS / "bundle"
RAW = ROOT / "outputs" / "m3-multistate-pass"
INPUT = json.loads((RAW / "ledger_timestep-inputs.json").read_bytes())
ACTUAL_CSV = (RAW / "ledger_timestep-restriction.csv").read_bytes()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def token(value: float) -> str:
    if value == 0.0:
        return "0"
    mantissa, exponent = format(value, ".16E").split("E")
    return f"{mantissa}E{int(exponent):+04d}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def initgrid_binary64() -> tuple[list[float], list[float], list[float], list[float]]:
    n = 40
    zf = [0.0] * (n + 2)
    for k in range(1, n + 1):
        z0 = (k - 0.0) / (1.0 * n)
        zf[k] = z0 * 1.0
    zf[0] = 0.0
    dzf = [0.0] * (n + 2)
    for k in range(1, n + 1):
        dzf[k] = zf[k] - zf[k - 1]
    dzf[0] = dzf[1]
    dzf[n + 1] = dzf[n]
    dzc = [0.0] * (n + 2)
    for k in range(0, n + 1):
        dzc[k] = 0.5 * (dzf[k] + dzf[k + 1])
    dzc[n + 1] = dzc[n]
    for k in range(0, 1):
        dzf[k] = dzf[-k + 1]
        dzc[k] = dzc[-k]
    for k in range(n + 1, n + 2):
        dzf[k] = dzf[2 * n - k - 1]
        dzc[k] = dzc[2 * n - k]
    dzci = [1.0 / value for value in dzc]
    dzfi = [1.0 / value for value in dzf]
    return dzc, dzf, dzci, dzfi


def expected_inputs_bytes() -> bytes:
    dzc, dzf, dzci, dzfi = initgrid_binary64()
    spacing = [float("0.0375"), float("0.0231"), float("0.025")]
    inverse = [1.0 / value for value in spacing]
    epsilon = sys.float_info.epsilon
    small = epsilon * 10.0 ** (15.0 / 2.0)
    values = {
        "cfl_c": 1.0,
        "cfl_d": 1.0 / 6.0,
        "dx_m": spacing[0],
        "dxi_m_inv": inverse[0],
        "dy_m": spacing[1],
        "dyi_m_inv": inverse[1],
        "dz_m": spacing[2],
        "dzc_m": dzc,
        "dzci_m_inv": dzci,
        "dzf_m": dzf,
        "dzfi_m_inv": dzfi,
        "dzi_m_inv": inverse[2],
        "fixed_step_factor": 0.2,
        "fixed_step_s": 1.0e-4,
        "gravity_m_s2": [0.0, 0.0, 0.0],
        "machine_epsilon": epsilon,
        "mu1_pa_s": 0.001,
        "mu2_pa_s": 1.8e-5,
        "rho1_kg_m3": 1000.0,
        "rho2_kg_m3": 1.0,
        "sigma_n_m": 0.0,
        "small_s_inv": small,
        "time_start_s": 0.0,
    }
    output = "{\n"
    scalar_order = (
        "cfl_c", "cfl_d", "dx_m", "dxi_m_inv", "dy_m", "dyi_m_inv", "dz_m",
    )
    for name in scalar_order:
        output += f'"{name}":"{token(values[name])}",'
    for name in ("dzc_m", "dzci_m_inv", "dzf_m", "dzfi_m_inv"):
        items = ",".join(f'"{token(value)}"' for value in values[name])
        output += f'"{name}":[{items}],\n'
    output += f'"dzi_m_inv":"{token(values["dzi_m_inv"])}",'
    output += f'"fixed_step_factor":"{token(values["fixed_step_factor"])}",'
    output += f'"fixed_step_s":"{token(values["fixed_step_s"])}",'
    gravity = ",".join(f'"{token(value)}"' for value in values["gravity_m_s2"])
    output += f'"gravity_m_s2":[{gravity}],\n'
    output += f'"machine_epsilon":"{token(values["machine_epsilon"])}",'
    output += f'"mu1_pa_s":"{token(values["mu1_pa_s"])}",'
    output += f'"mu2_pa_s":"{token(values["mu2_pa_s"])}",'
    output += '"precision_digits":15,\n'
    output += '"real_kind":8,\n'
    output += f'"rho1_kg_m3":"{token(values["rho1_kg_m3"])}",'
    output += f'"rho2_kg_m3":"{token(values["rho2_kg_m3"])}",'
    output += f'"sigma_n_m":"{token(values["sigma_n_m"])}",'
    output += f'"small_s_inv":"{token(values["small_s_inv"])}",'
    output += '"time_scheme":"ab2",'
    output += f'"time_start_s":"{token(values["time_start_s"])}" ' + "}\n"
    return output.encode("utf-8")


def restriction_values() -> dict[str, float | str]:
    dzci = [float(value) for value in INPUT["dzci_m_inv"]]
    dzfi = [float(value) for value in INPUT["dzfi_m_inv"]]
    dli = [float(INPUT[name]) for name in ("dxi_m_inv", "dyi_m_inv", "dzi_m_inv")]
    dtic_raw = 0.0
    for k in range(1, 41):
        ux = abs(0.125)
        vx = 0.25 * abs(0.0 + 0.0 + 0.0 + 0.0)
        wx = 0.25 * abs(0.25 + 0.25 + 0.25 + 0.25)
        dtix = ux * dli[0] + vx * dli[1] + wx * dzfi[k]
        uy = 0.25 * abs(0.125 + 0.125 + 0.125 + 0.125)
        vy = abs(0.0)
        wy = 0.25 * abs(0.25 + 0.25 + 0.25 + 0.25)
        dtiy = uy * dli[0] + vy * dli[1] + wy * dzfi[k]
        uz = 0.25 * abs(0.125 + 0.125 + 0.125 + 0.125)
        vz = 0.25 * abs(0.0 + 0.0 + 0.0 + 0.0)
        wz = abs(0.25)
        dtiz = uz * dli[0] + vz * dli[1] + wz * dzci[k]
        dtic_raw = max(dtic_raw, dtix, dtiy, dtiz)
    zero_fallback = dtic_raw == 0.0
    dtic_used = 1.0 if zero_fallback else dtic_raw
    dlmin = min(1.0 / value for value in dli)
    dlmin = min(dlmin, min(1.0 / value for value in dzfi))
    dlmini = dlmin ** (-1)
    nu_max = max(
        float(INPUT["mu1_pa_s"]) / float(INPUT["rho1_kg_m3"]),
        float(INPUT["mu2_pa_s"]) / float(INPUT["rho2_kg_m3"]),
    )
    dtiv = nu_max * dlmini**2 / float(INPUT["cfl_d"])
    dtik = float(INPUT["small_s_inv"])
    dtig = math.sqrt(max(abs(float(value)) for value in INPUT["gravity_m_s2"]) * dlmini)
    adv_diff = dtic_used + dtiv
    dt_bound = float(INPUT["cfl_c"]) * 2.0 * (
        adv_diff + math.sqrt(adv_diff**2 + 4.0 * (dtig**2 + dtik**2))
    ) ** (-1)
    dtmax = min(dt_bound, 1.0 / dtik)
    dt = float(INPUT["fixed_step_s"])
    dt_over = dt / dtmax
    guard_limit = float(INPUT["fixed_step_factor"]) * dtmax
    return {
        "dtic_raw_s_inv": dtic_raw,
        "dtic_used_s_inv": dtic_used,
        "zero_advection_fallback": "true" if zero_fallback else "false",
        "nu_max_m2_s": nu_max,
        "h_min_m": dlmin,
        "dlmini_m_inv": dlmini,
        "dtiv_s_inv": dtiv,
        "dtik_s_inv": dtik,
        "dtig_s_inv": dtig,
        "capillary_active": "false",
        "dtmax_s": dtmax,
        "fixed_step_factor": float(INPUT["fixed_step_factor"]),
        "dt_over_dtmax": dt_over,
        "guard_pass": "true" if dt <= guard_limit else "false",
    }


def expected_timestep_csv_bytes() -> bytes:
    header = (
        "state_index,time_s,dt_s,dtic_raw_s_inv,dtic_used_s_inv,"
        "zero_advection_fallback,nu_max_m2_s,h_min_m,dlmini_m_inv,dtiv_s_inv,"
        "dtik_s_inv,dtig_s_inv,capillary_active,dtmax_s,fixed_step_factor,"
        "dt_over_dtmax,guard_pass"
    )
    expected = restriction_values()
    lines = [header]
    start = float(INPUT["time_start_s"])
    step = float(INPUT["fixed_step_s"])
    for state in range(15):
        values = [
            str(state),
            token(start + float(state) * step),
            token(step),
            token(float(expected["dtic_raw_s_inv"])),
            token(float(expected["dtic_used_s_inv"])),
            str(expected["zero_advection_fallback"]),
            token(float(expected["nu_max_m2_s"])),
            token(float(expected["h_min_m"])),
            token(float(expected["dlmini_m_inv"])),
            token(float(expected["dtiv_s_inv"])),
            token(float(expected["dtik_s_inv"])),
            token(float(expected["dtig_s_inv"])),
            str(expected["capillary_active"]),
            token(float(expected["dtmax_s"])),
            token(float(expected["fixed_step_factor"])),
            token(float(expected["dt_over_dtmax"])),
            "not_applicable" if state == 14 else str(expected["guard_pass"]),
        ]
        lines.append(",".join(values))
    return ("\n".join(lines) + "\n").encode("utf-8")


def main() -> None:
    reference = ROOT / "reference"
    pins = {
        "candidate_patch_sha256": "aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7",
        "candidate_vof_source_sha256": "657e4d7e4c7ec0739b506ae806c9bd5e80df7aaa238e248cb9fab4ee43fcea61",
        "analyzer_sha256": "9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37",
        "analyzer_fixture_sha256": "b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20",
        "schema_sha256": "4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492",
        "initgrid_sha256": "87010cb1b014355eb70b299264d5b6cd274ab3248c309906a39ac4a66ab8ca28",
    }
    actual = {
        "candidate_patch_sha256": sha(reference / "candidate-source-boundary.patch"),
        "candidate_vof_source_sha256": sha(reference / "pinned-source" / "vof.f90"),
        "analyzer_sha256": sha(reference / "flutas_source_analyzer.py"),
        "analyzer_fixture_sha256": sha(reference / "test_flutas_source_analyzer.py"),
        "schema_sha256": sha(reference / "schema-v1.2.md"),
        "initgrid_sha256": sha(reference / "pinned-source" / "initgrid.f90"),
    }
    require(actual == pins, f"frozen source hash mismatch: {actual!r}")

    dzc, dzf, dzci, dzfi = initgrid_binary64()
    for key, values in (
        ("dzc_m", dzc), ("dzf_m", dzf),
        ("dzci_m_inv", dzci), ("dzfi_m_inv", dzfi),
    ):
        observed = [float(value) for value in INPUT[key]]
        mismatches = [
            (idx, expected.hex(), got.hex())
            for idx, (expected, got) in enumerate(zip(values, observed, strict=True))
            if expected != got
        ]
        require(not mismatches, f"{key} differs from independent initgrid: {mismatches[:5]!r}")

    expected_input = expected_inputs_bytes()
    observed_input_path = RAW / "ledger_timestep-inputs.json"
    (OUT / "expected-timestep-inputs.json").write_bytes(expected_input)
    input_equal = expected_input == observed_input_path.read_bytes()

    expected_csv = expected_timestep_csv_bytes()
    (OUT / "expected-timestep-restriction.csv").write_bytes(expected_csv)
    csv_equal = expected_csv == ACTUAL_CSV

    with (OUT / "expected-reciprocals.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("kind", "index", "spacing_hex", "expected_inverse_hex", "observed_token", "match"))
        for kind, spacing_key, inverse_key in (
            ("center", "dzc_m", "dzci_m_inv"),
            ("face", "dzf_m", "dzfi_m_inv"),
        ):
            for idx, (spacing, inverse, observed) in enumerate(
                zip(dzc if kind == "center" else dzf,
                    dzci if kind == "center" else dzfi,
                    INPUT[inverse_key], strict=True)
            ):
                writer.writerow((kind, idx, spacing.hex(), inverse.hex(), observed, str(float(observed) == inverse).lower()))
        scalar_spacing = (float("0.0375"), float("0.0231"), float("0.025"))
        scalar_inverse_tokens = (INPUT["dxi_m_inv"], INPUT["dyi_m_inv"], INPUT["dzi_m_inv"])
        for axis, spacing, observed in zip("xyz", scalar_spacing, scalar_inverse_tokens, strict=True):
            expected = 1.0 / spacing
            writer.writerow((f"scalar-{axis}", 0, spacing.hex(), expected.hex(), observed,
                             str(float(observed) == expected).lower()))

    header, *rows = ACTUAL_CSV.decode("utf-8").splitlines()
    actual_rows = list(csv.DictReader([header, *rows]))
    start = float(INPUT["time_start_s"])
    step = float(INPUT["fixed_step_s"])
    ab2_clock = start
    time_order_rows = []
    for state in range(15):
        if state == 1:
            f_t1 = 1.0 * step
            f_t2 = 0.0 * step
        elif state > 1:
            f_t1 = (1.0 + 0.5 * (step / step)) * step
            f_t2 = (-0.5 * (step / step)) * step
        if state > 0:
            ab2_clock = ab2_clock + (f_t1 + f_t2)
        index_clock = start + float(state) * step
        emitted = actual_rows[state]["time_s"]
        time_order_rows.append((state, token(index_clock), token(ab2_clock), emitted,
                                str(ab2_clock == index_clock).lower()))
    with (OUT / "time-order.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("state_index", "expected_index_time", "independent_ab2_clock", "emitted_time", "same_clock"))
        writer.writerows(time_order_rows)

    result = {
        "producer_patch_sha256": actual["candidate_patch_sha256"],
        "producer_module_sha256": actual["candidate_vof_source_sha256"],
        "initgrid_sha256": actual["initgrid_sha256"],
        "analyzer_sha256": actual["analyzer_sha256"],
        "fixture_sha256": actual["analyzer_fixture_sha256"],
        "schema_sha256": actual["schema_sha256"],
        "initgrid_spacing_and_reciprocal_binary64_match_count": 42 * 4,
        "input_json_exact_bytes_match_independent_serializer": input_equal,
        "timestep_csv_exact_bytes_match_independent_binary64_calculation": csv_equal,
        "timestep_csv_sha256": hashlib.sha256(ACTUAL_CSV).hexdigest(),
        "timestep_inputs_sha256": hashlib.sha256(observed_input_path.read_bytes()).hexdigest(),
        "restriction_expected": {key: (value.hex() if isinstance(value, float) else value)
                                  for key, value in restriction_values().items()},
        "ab2_state_2_differs_from_index_time": time_order_rows[2][2] != time_order_rows[2][1],
    }
    (OUT / "independent-arithmetic-report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    require(input_equal, "producer timestep-inputs.json differs from independent exact bytes")
    require(csv_equal, "producer timestep-restriction.csv differs from independent exact bytes")
    require(time_order_rows[2][2] != time_order_rows[2][1], "AB2 state 2 did not separate clocks")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
