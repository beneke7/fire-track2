#!/usr/bin/env python3
"""Static integration checks for source hooks in the pinned FluTAS driver.

This is a CPU-only regression guard for wiring and ordering. It does not certify
the source producer, raw evidence, conservation, boundary compatibility, or a
source-run gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def normalized_fortran(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        # These assertions concern code statements; strip Fortran comments.
        lines.append(line.split("!", 1)[0])
    text = " ".join(lines).lower().replace("&", " ")
    text = re.sub(r"\s*([(),/])\s*", r"\1", text)
    return re.sub(r"\s+", " ", text)


def require_sequence(text: str, markers: list[str], label: str) -> None:
    cursor = 0
    missing = []
    for marker in markers:
        normalized_marker = re.sub(r"\s*([(),/])\s*", r"\1", marker.lower())
        found = text.find(normalized_marker, cursor)
        if found < 0:
            missing.append(marker)
            continue
        cursor = found + len(normalized_marker)
    if missing:
        raise AssertionError(f"{label}: missing or out-of-order markers: {missing}")


def require_count(text: str, marker: str, expected: int, label: str) -> None:
    actual = text.count(marker.lower())
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected} {marker!r} calls, got {actual}")


def main(source_root: Path) -> None:
    vof_path = source_root / "src/vof.f90"
    driver_path = source_root / "src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90"
    for path in (vof_path, driver_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    vof = normalized_fortran(vof_path)
    driver = normalized_fortran(driver_path)

    # The optional source interval must refresh the incoming VOF and record
    # each actual directional flux before the corresponding flux array is
    # reused or the transported state advances.
    require_count(vof, "call cmpt_vof_flux", 3, "VOF directional sweep count")
    require_sequence(
        vof,
        [
            "call restas_source_refresh_vof_state",
            "'pre_vof_x'",
            "call cmpt_vof_flux(n(1),n(2),n(3),dli(1),dt,nh_u,vof,nor,cur,d_thinc,1,ug,flux)",
            "call restas_source_accumulate_boundary_flux(n,dl,dzf,1,flux)",
            "call restas_source_prepare_boundary(n,nh_u,source_step,dvof1,wg,rho_state,mu_state)",
            "'pre_vof_y'",
            "call cmpt_vof_flux(n(1),n(2),n(3),dli(2),dt,nh_u,dvof1,nor,cur,d_thinc,2,vg,flux)",
            "call restas_source_accumulate_boundary_flux(n,dl,dzf,2,flux)",
            "call restas_source_prepare_boundary(n,nh_u,source_step,dvof2,wg,rho_state,mu_state)",
            "'pre_vof_z'",
            "call cmpt_vof_flux(n(1),n(2),n(3),dli(3),dt,nh_u,dvof2,nor,cur,d_thinc,3,wg,flux)",
            "call restas_source_check_volume_pair",
            "call restas_source_accumulate_boundary_flux(n,dl,dzf,3,flux)",
            "call restas_source_record_flux(n,nh_u,dl,dt,source_step,flux,ug,vg,wg)",
        ],
        "VOF directional source wiring",
    )

    # Every generic property fill used between VOF directions must be followed
    # by source-aware boundary preparation before the next reconstruction or
    # momentum update consumes the fields.
    require_count(vof, "call update_property(n,(/rho1,rho2/)", 2, "directional density rebuilds")
    require_count(vof, "call update_property(n,(/mu1,mu2/)", 2, "directional viscosity rebuilds")
    require_count(vof, "call restas_source_prepare_boundary(n,nh_u,source_step,dvof1,wg,rho_state,mu_state)", 2,
                  "dvof1 source-aware property refreshes")
    require_count(vof, "call restas_source_prepare_boundary(n,nh_u,source_step,dvof2,wg,rho_state,mu_state)", 2,
                  "dvof2 source-aware property refreshes")
    require_sequence(
        vof,
        [
            "call update_property(n,(/rho1,rho2/),dvof1,rho_state)",
            "call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,rho_state)",
            "call update_property(n,(/mu1,mu2/),dvof1,mu_state)",
            "call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,mu_state)",
            "call restas_source_prepare_boundary(n,nh_u,source_step,dvof1,wg,rho_state,mu_state)",
            "'pre_vof_y'",
            "call update_property(n,(/rho1,rho2/),dvof2,rho_state)",
            "call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,rho_state)",
            "call update_property(n,(/mu1,mu2/),dvof2,mu_state)",
            "call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,mu_state)",
            "call restas_source_prepare_boundary(n,nh_u,source_step,dvof2,wg,rho_state,mu_state)",
            "'pre_vof_z'",
        ],
        "directional material-property refresh",
    )
    require_sequence(
        vof,
        [
            "call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,vof)",
            "call restas_source_prepare_boundary(n,nh_u,source_step,vof,wg)",
            "call update_vof(n,dli,nh_d,dzc,dzf,+1,halo,vof,nor,cur,kappa,d_thinc)",
        ],
        "final VOF boundary refresh",
    )

    # Verify initialization, interval-index propagation, post-advection
    # property refresh, and velocity reapplication around projection/correction.
    require_sequence(
        driver,
        [
            "call bounduvw(cbcvel,n,bcvel,nh_d,nh_u,halo_u,is_outflow,dl,dzc,dzf,u,v,w)",
            "call restas_source_apply_velocity(n,nh_u,0,dl,u,v,w,source_qtop,source_qbottom)",
            "'initial_u0'",
            "call restas_source_prepare_boundary(n,nh_u,0,psi,w,rho,mu)",
            "call restas_source_record_inventory(n,dl,dzf,psi,0,time)",
            "call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt_input,0,0,time,psi,u,v,w)",
            "source_interval=istep-1",
            "'pre_vof'",
            "call restas_source_assert_velocity(n,nh_u,source_interval,dl,w)",
            "call restas_source_begin_step()",
            "call advvof",
            "call update_property(n,(/rho1,rho2/),psi,rho)",
            "call boundp(cbcvof,n,bcvof,nh_d,nh_v,halo_v,dl,dzc,dzf,rho)",
            "call update_property(n,(/mu1,mu2/),psi,mu)",
            "call boundp(cbcvof,n,bcvof,nh_d,nh_v,halo_v,dl,dzc,dzf,mu)",
            "call restas_source_prepare_boundary(n,nh_u,source_interval,psi,w,rho,mu)",
            "'pre_momentum'",
            "call restas_source_record_inventory(n,dl,dzf,psi,istep,time)",
            "call bounduvw(cbcvel,n,bcvel,nh_d,nh_u,halo_u,no_outflow,dl,dzc,dzf,u,v,w)",
            "call restas_source_apply_velocity(n,nh_u,istep,dl,u,v,w,source_qtop,source_qbottom)",
            "'projection_override'",
            "call correc(",
            "call bounduvw(cbcvel,n,bcvel,nh_d,nh_u,halo_u,is_outflow,dl,dzc,dzf,u,v,w)",
            "call restas_source_apply_velocity(n,nh_u,istep,dl,u,v,w,source_qtop,source_qbottom)",
            "'corrected_endpoint'",
            "call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,istep,istep,time,psi,u,v,w)",
            "call restas_source_record_timestep_restriction",
        ],
        "driver source and velocity stage order",
    )
    print("PASS candidate6 source hook call order in pinned VOF and driver sources")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} FLUTAS_SOURCE_ROOT")
    main(Path(sys.argv[1]))
