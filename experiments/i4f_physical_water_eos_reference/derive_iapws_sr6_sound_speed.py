#!/usr/bin/env python3
"""Reproduce IAPWS SR6-08(2011) w0 at 20 C from its published equations."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

R = 461.51805
TR = 10.0
P0 = 100_000.0
TA = 593.0
TB = 232.0

# Coefficients and exponents transcribed from IAPWS SR6-08(2011), Table 1.
# Eq. (1) c3 and a1..a3,b1..b4 are used for cp0 in Table 2.
CP_C3 = -8.983025854
CP_A = {1: -1.661470539e5, 2: 2.708781640e6, 3: -1.557191544e8}
CP_N = {1: 4, 2: 5, 3: 7}
CP_B = {1: -8.237426256e-1, 2: 1.908956353, 3: -2.017597384, 4: 8.546361348e-1}
CP_M = {1: 2, 2: 3, 3: 4, 4: 5}

# Eq. (2): v0 coefficients and exponents.
V_A = {
    5: 1.93763157e-2,
    6: 6.74458446e3,
    7: -2.22521604e5,
    8: 1.00231247e8,
    9: -1.63552118e9,
    10: 8.32299658e9,
}
V_N = {6: 4, 7: 5, 8: 7, 9: 8, 10: 9}
V_B = {
    5: 5.78545292e-3,
    6: -1.53195665e-2,
    7: 3.11337859e-2,
    8: -4.23546241e-2,
    9: 3.38713507e-2,
    10: -1.19946761e-2,
}
V_M = {5: 1, 6: 2, 7: 3, 8: 4, 9: 5, 10: 6}

# Eq. (3): vp0 coefficients and exponents.
VP_A = {
    11: -7.5245878e-6,
    12: -1.3767418e-2,
    13: 1.0627293e1,
    14: -2.0457795e2,
    15: 1.2037414e3,
}
VP_N = {11: 1, 12: 3, 13: 5, 14: 6, 15: 7}
VP_B = {
    11: -3.1091470e-6,
    12: 2.8964919e-5,
    13: -1.3112763e-4,
    14: 3.0410453e-4,
    15: -3.9034594e-4,
    16: 2.3403117e-4,
    17: -4.8510101e-5,
}
VP_M = {11: 1, 12: 3, 13: 4, 14: 5, 15: 6, 16: 7, 17: 9}


def properties(t_kelvin: float) -> dict[str, float]:
    tau = t_kelvin / TR
    alpha = TR / (TA - t_kelvin)
    beta = TR / (t_kelvin - TB)
    v0 = R * TR / P0 * (
        V_A[5]
        + sum(V_A[i] * alpha**V_N[i] for i in V_N)
        + sum(V_B[i] * beta**V_M[i] for i in V_M)
    )
    v_t0 = R / P0 * (
        sum(V_N[i] * V_A[i] * alpha ** (V_N[i] + 1) for i in V_N)
        - sum(V_M[i] * V_B[i] * beta ** (V_M[i] + 1) for i in V_M)
    )
    v_p0 = R * TR / P0**2 * (
        sum(VP_A[i] * alpha**VP_N[i] for i in VP_N)
        + sum(VP_B[i] * beta**VP_M[i] for i in VP_M)
    )
    cp0 = -R * (
        CP_C3
        + tau * sum(
            CP_N[i] * (CP_N[i] + 1) * CP_A[i] * alpha ** (CP_N[i] + 2)
            for i in CP_N
        )
        + tau * sum(
            CP_M[i] * (CP_M[i] + 1) * CP_B[i] * beta ** (CP_M[i] + 2)
            for i in CP_M
        )
    )
    w0 = math.sqrt(-v0**2 / (v_p0 + t_kelvin * v_t0**2 / cp0))
    return {
        "temperature_K": t_kelvin,
        "pressure_Pa": P0,
        "specific_volume_m3_kg": v0,
        "density_kg_m3": 1.0 / v0,
        "vT0_m3_kg_K": v_t0,
        "vp0_m3_kg_Pa": v_p0,
        "cp0_J_kg_K": cp0,
        "speed_of_sound_m_s": w0,
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_20 = properties(293.15)
    result_table8 = properties(298.15)
    reference_table8 = 1496.69922
    delta = result_table8["speed_of_sound_m_s"] - reference_table8
    if abs(delta) > 1e-5:
        raise SystemExit(f"Table 8 check failed: discrepancy={delta} m/s")
    record = {
        "schema": "i4f-iapws-sr6-sound-speed-derivation/v1",
        "status": "DERIVED_FROM_PUBLISHED_EQUATIONS_TABLES_NO_FIT_NO_INTERPOLATION",
        "source": {
            "title": "IAPWS SR6-08(2011), Revised Supplementary Release on Properties of Liquid Water at 0.1 MPa",
            "url": "https://iapws.org/technical-guidance/release/LiquidWater.download",
            "downloaded_pdf_sha256": sha256(args.source_pdf),
            "source_equations": "Eqs. (2)-(3), Table 1 coefficients; Table 2 cp0 and vT0 derivatives; Table 3 w0 relation",
            "source_pdf_pages": {
                "equations": 3,
                "table_1_coefficients": 4,
                "cp_and_vT_derivative": 5,
                "speed_of_sound_combination": 6,
                "Table_8_program_check": 11,
            },
        },
        "method": {
            "T_star": "tau=T/TR; alpha=TR/(Ta-T); beta=TR/(T-Tb)",
            "constants": {"R_J_kg_K": R, "TR_K": TR, "p0_Pa": P0, "Ta_K": TA, "Tb_K": TB},
            "sound_speed_equation": "w0=sqrt(-v0^2/(vp0 + T*vT0^2/cp0))",
            "coefficients": {
                "cp0_c3": CP_C3,
                "cp0_a": CP_A,
                "cp0_n": CP_N,
                "cp0_b": CP_B,
                "cp0_m": CP_M,
                "v0_a": V_A,
                "v0_n": V_N,
                "v0_b": V_B,
                "v0_m": V_M,
                "vp0_a": VP_A,
                "vp0_n": VP_N,
                "vp0_b": VP_B,
                "vp0_m": VP_M,
            },
        },
        "evaluated_state": result_20,
        "table8_verification": {
            "evaluated_at_298_15_K": result_table8,
            "published_table8_speed_of_sound_m_s": reference_table8,
            "difference_m_s": delta,
            "absolute_tolerance_m_s": 1e-5,
            "passed": True,
        },
        "uncertainty_and_scope": {
            "published_stable_region_relative_speed_uncertainty_k2": 5e-5,
            "interpretation": "IAPWS describes this as an uncertainty estimate with coverage factor k=2. This is the low-pressure liquid correlation, not a validation of the apparatus pressure range.",
            "correlation_pressure_MPa": 0.1,
            "apparatus_tank_pressure_exceeds_0p3_MPa": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(record["evaluated_state"], sort_keys=True))
    print(json.dumps(record["table8_verification"], sort_keys=True))


if __name__ == "__main__":
    main()
