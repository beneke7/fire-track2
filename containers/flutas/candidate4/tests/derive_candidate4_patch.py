#!/usr/bin/env python3
"""Derive candidate4 from the reviewed candidate3 patch and bounded edits."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


source_root = Path(sys.argv[1]).resolve()
candidate_root = Path(sys.argv[2]).resolve()
base_patch = candidate_root / "evidence/input/candidate3-source-boundary.patch"
subprocess.run(
    ["git", "-C", str(source_root), "apply", "--check", str(base_patch)], check=True
)
subprocess.run(["git", "-C", str(source_root), "apply", str(base_patch)], check=True)


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text()
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"expected one occurrence in {path}: found {count} for {old!r}")
    path.write_text(source.replace(old, new, 1))


helper_path = source_root / "src/restas_source.inc"
helper = helper_path.read_text()

# Separate global off-mask totals from the per-slot table and add explicit
# per-interval and pre-abort rate-check records.
replace_once(
    helper_path,
    "    open(newunit=restas_source_flux_unit,file=trim(path_prefix)//'_source-flux.csv',status='replace')\n"
    "    open(newunit=restas_boundary_unit,file=trim(path_prefix)//'_boundary-ledger.csv',status='replace')\n"
    "    open(newunit=restas_mass_unit,file=trim(path_prefix)//'_mass-ledger.csv',status='replace')\n"
    "    open(newunit=restas_velocity_unit,file=trim(path_prefix)//'_velocity-audit.csv',status='replace')",
    "    open(newunit=restas_source_flux_unit,file=trim(path_prefix)//'_source-flux.csv',status='replace')\n"
    "    open(newunit=restas_offmask_unit,file=trim(path_prefix)//'_source-offmask.csv',status='replace')\n"
    "    open(newunit=restas_rate_unit,file=trim(path_prefix)//'_rate-check.csv',status='replace')\n"
    "    open(newunit=restas_boundary_unit,file=trim(path_prefix)//'_boundary-ledger.csv',status='replace')\n"
    "    open(newunit=restas_mass_unit,file=trim(path_prefix)//'_mass-ledger.csv',status='replace')\n"
    "    open(newunit=restas_velocity_unit,file=trim(path_prefix)//'_velocity-audit.csv',status='replace')",
)
replace_once(
    helper_path,
    "      'applied_mom_z_kgm_s,slot_reverse_out_m3,offmask_in_m3,offmask_out_m3'",
    "      'applied_mom_z_kgm_s,slot_reverse_out_m3'",
)
replace_once(
    helper_path,
    "      'interval,slot,requested_volume_m3,geometric_inward_volume_m3,requested_mass_kg,'// &",
    "      'interval_index,slot,requested_volume_m3,geometric_inward_volume_m3,requested_mass_kg,'// &",
)
replace_once(
    helper_path,
    "    write(restas_boundary_unit,'(A)') &",
    "    write(restas_offmask_unit,'(A)') 'interval_index,offmask_in_m3,offmask_out_m3'\n"
    "    write(restas_rate_unit,'(A)') &\n"
    "      'interval_index,measured_top_liquid_m3_s,expected_top_liquid_m3_s,top_residual_m3_s,'// &\n"
    "      'measured_bottom_volume_m3_s,expected_bottom_volume_m3_s,bottom_residual_m3_s'\n"
    "    write(restas_boundary_unit,'(A)') &",
)
replace_once(
    helper_path,
    "      'state_index,source_interval_index,time_s,top_in_m3_s,bottom_out_m3_s,net_boundary_m3_s,'// &\n"
    "      'integrated_divergence_m3_s,closure_m3_s,max_abs_div_s,l1_divergence_m3_s,'// &\n"
    "      'xlow_out_m3_s,xhigh_out_m3_s,ylow_out_m3_s,yhigh_out_m3_s,'// &\n"
    "      'zlow_out_m3_s,zhigh_out_m3_s'",
    "      'state_index,source_profile_interval,time_s,dt_s,total_cell_count,'// &\n"
    "      'global_chkdt_advective_courant_max,interface_cell_count,interface_courant_defined,'// &\n"
    "      'interface_advective_courant_max,top_in_m3_s,bottom_out_m3_s,net_boundary_m3_s,'// &\n"
    "      'integrated_divergence_m3_s,closure_m3_s,max_abs_divergence_s,'// &\n"
    "      'volume_integrated_abs_divergence_m3_s,xlow_out_m3_s,xhigh_out_m3_s,'// &\n"
    "      'ylow_out_m3_s,yhigh_out_m3_s,zlow_out_m3_s,zhigh_out_m3_s'",
)

replace_once(
    helper_path,
    "    real(rp) :: area,top_volume,qexpected,tol",
    "    real(rp) :: area,top_volume,qexpected,tol,qbottom_comp,qbottom_term,qbottom_y,qbottom_tmp",
)
replace_once(
    helper_path,
    "    if(abs(qtop-qexpected).gt.tol) &\n"
    "      error stop 'Geometric liquid source flux differs from frozen total-volume schedule'\n"
    "    qbottom=0._rp\n"
    "    do j=1,n(2)\n"
    "      do i=1,n(1)\n"
    "        qbottom=qbottom-w(i,j,0)*area\n"
    "      enddo\n"
    "    enddo\n"
    "    if(abs(qbottom-qexpected).gt.tol) &\n"
    "      error stop 'Projected bottom return differs from frozen total-volume schedule'",
    "    qbottom=0._rp\n"
    "    qbottom_comp=0._rp\n"
    "    do j=1,n(2)\n"
    "      do i=1,n(1)\n"
    "        qbottom_term=-w(i,j,0)*area\n"
    "        qbottom_y=qbottom_term-qbottom_comp\n"
    "        qbottom_tmp=qbottom+qbottom_y\n"
    "        qbottom_comp=(qbottom_tmp-qbottom)-qbottom_y\n"
    "        qbottom=qbottom_tmp\n"
    "      enddo\n"
    "    enddo\n"
    "    ! Persist both measured rates and signed residuals before a rate abort.\n"
    "    call restas_source_record_rate_check(step_index,qtop,qexpected,qbottom,qexpected)\n"
    "    if(abs(qtop-qexpected).gt.tol) &\n"
    "      error stop 'Geometric liquid source flux differs from frozen total-volume schedule'\n"
    "    if(abs(qbottom-qexpected).gt.tol) &\n"
    "      error stop 'Projected bottom return differs from frozen total-volume schedule'",
)

rate_writer = """  subroutine restas_source_record_rate_check(step_index,measured_top,expected_top, &
                                               measured_bottom,expected_bottom)
    implicit none
    integer, intent(in) :: step_index
    real(rp), intent(in) :: measured_top,expected_top,measured_bottom,expected_bottom
    if(.not.restas_source_loaded.or..not.restas_source_log_open) return
    write(restas_rate_unit,'(I0,6(\",\",ES24.16E3))') step_index,measured_top,expected_top, &
      measured_top-expected_top,measured_bottom,expected_bottom,measured_bottom-expected_bottom
    flush(restas_rate_unit)
  end subroutine restas_source_record_rate_check
  !
"""
replace_once(
    helper_path,
    "  subroutine restas_source_begin_step()",
    rate_writer + "  subroutine restas_source_begin_step()",
)

# Off-mask totals are interval-wide and are written exactly once, including
# in dry cases where the source-slot table has no rows.
replace_once(
    helper_path,
    "    do islot=1,restas_slot_count\n      requested_volume=0._rp",
    "    write(restas_offmask_unit,'(I0,2(\",\",ES24.16E3))') step_index,offmask_in,offmask_out\n"
    "    flush(restas_offmask_unit)\n"
    "    do islot=1,restas_slot_count\n      requested_volume=0._rp",
)
replace_once(
    helper_path,
    "      write(restas_source_flux_unit,'(I0,\",\",I0,13(\",\",ES24.16E3))') &\n"
    "        step_index,islot,requested_volume,applied_volume,requested_mass,applied_mass, &\n"
    "        requested_momentum(1),requested_momentum(2),requested_momentum(3), &\n"
    "        applied_momentum(1),applied_momentum(2),applied_momentum(3), &\n"
    "        reverse_out,offmask_in,offmask_out",
    "      write(restas_source_flux_unit,'(I0,\",\",I0,11(\",\",ES24.16E3))') &\n"
    "        step_index,islot,requested_volume,applied_volume,requested_mass,applied_mass, &\n"
    "        requested_momentum(1),requested_momentum(2),requested_momentum(3), &\n"
    "        applied_momentum(1),applied_momentum(2),applied_momentum(3),reverse_out",
)
replace_once(
    helper_path,
    "    flush(restas_source_flux_unit)\n  end subroutine restas_source_record_flux",
    "    flush(restas_source_flux_unit)\n  end subroutine restas_source_record_flux",
)

# Rebuild the velocity audit with the exact advective terms used by upstream
# chkdt_tw, restricted to mixed-alpha cells for the interface maximum.
helper = helper_path.read_text()
start = helper.index("  subroutine restas_source_record_velocity_audit")
end = helper.index("  end subroutine restas_source_record_velocity_audit", start) + len(
    "  end subroutine restas_source_record_velocity_audit"
)
new_audit = """  subroutine restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,state_index, &
                                                    source_profile_interval,time,vof,u,v,w)
    implicit none
    integer, intent(in) :: n(3),nh_u,state_index,source_profile_interval
    real(rp), intent(in) :: dl(3),dzf(:),dt,time
    real(rp), intent(in) :: vof(0:,0:,0:)
    real(rp), intent(in) :: u(1-nh_u:,1-nh_u:,1-nh_u:)
    real(rp), intent(in) :: v(1-nh_u:,1-nh_u:,1-nh_u:)
    real(rp), intent(in) :: w(1-nh_u:,1-nh_u:,1-nh_u:)
    integer :: i,j,k,interface_cell_count,interface_courant_defined,total_cell_count
    real(rp) :: face_out(6),net_boundary,div,div_integral,div_l1,div_max,cell_volume
    real(rp) :: top_in,bottom_out,closure,ux,uy,uz,vx,vy,vz,wx,wy,wz
    real(rp) :: dtix,dtiy,dtiz,cell_courant,global_courant,interface_courant
    if(.not.restas_source_loaded.or..not.restas_source_log_open) return
    face_out=0._rp
    do k=1,n(3)
      do j=1,n(2)
        face_out(1)=face_out(1)-u(0,j,k)*dl(2)*dzf(k)
        face_out(2)=face_out(2)+u(n(1),j,k)*dl(2)*dzf(k)
      enddo
    enddo
    do k=1,n(3)
      do i=1,n(1)
        face_out(3)=face_out(3)-v(i,0,k)*dl(1)*dzf(k)
        face_out(4)=face_out(4)+v(i,n(2),k)*dl(1)*dzf(k)
      enddo
    enddo
    do j=1,n(2)
      do i=1,n(1)
        face_out(5)=face_out(5)-w(i,j,0)*dl(1)*dl(2)
        face_out(6)=face_out(6)+w(i,j,n(3))*dl(1)*dl(2)
      enddo
    enddo
    div_integral=0._rp
    div_l1=0._rp
    div_max=0._rp
    global_courant=0._rp
    interface_courant=0._rp
    interface_cell_count=0
    total_cell_count=product(n)
    do k=1,n(3)
      cell_volume=dl(1)*dl(2)*dzf(k)
      do j=1,n(2)
        do i=1,n(1)
          div=(u(i,j,k)-u(i-1,j,k))/dl(1)+ &
              (v(i,j,k)-v(i,j-1,k))/dl(2)+ &
              (w(i,j,k)-w(i,j,k-1))/dzf(k)
          div_integral=div_integral+div*cell_volume
          div_l1=div_l1+abs(div)*cell_volume
          div_max=max(div_max,abs(div))
          ! Match chkdt_tw's three directional face-speed estimates. These
          ! are advective Courant diagnostics, not its complete stability limit.
          ux=abs(u(i,j,k))
          vx=0.25_rp*abs(v(i,j,k)+v(i,j-1,k)+v(i+1,j,k)+v(i+1,j-1,k))
          wx=0.25_rp*abs(w(i,j,k)+w(i,j,k-1)+w(i+1,j,k)+w(i+1,j,k-1))
          dtix=ux/dl(1)+vx/dl(2)+wx/dzf(k)
          uy=0.25_rp*abs(u(i,j,k)+u(i,j+1,k)+u(i-1,j+1,k)+u(i-1,j,k))
          vy=abs(v(i,j,k))
          wy=0.25_rp*abs(w(i,j,k)+w(i,j+1,k)+w(i,j+1,k-1)+w(i,j,k-1))
          dtiy=uy/dl(1)+vy/dl(2)+wy/dzf(k)
          uz=0.25_rp*abs(u(i,j,k)+u(i-1,j,k)+u(i-1,j,k+1)+u(i,j,k+1))
          vz=0.25_rp*abs(v(i,j,k)+v(i,j-1,k)+v(i,j-1,k+1)+v(i,j,k+1))
          wz=abs(w(i,j,k))
          dtiz=uz/dl(1)+vz/dl(2)+wz/dzf(k)
          cell_courant=dt*max(dtix,dtiy,dtiz)
          global_courant=max(global_courant,cell_courant)
          if(vof(i,j,k).gt.0._rp.and.vof(i,j,k).lt.1._rp) then
            interface_cell_count=interface_cell_count+1
            interface_courant=max(interface_courant,cell_courant)
          endif
        enddo
      enddo
    enddo
    interface_courant_defined=0
    if(interface_cell_count.gt.0) interface_courant_defined=1
    net_boundary=sum(face_out)
    closure=div_integral-net_boundary
    top_in=max(0._rp,-face_out(6))
    bottom_out=max(0._rp,face_out(5))
    write(restas_velocity_unit,'(I0,\",\",I0,2(\",\",ES24.16E3),\",\",I0,\",\",ES24.16E3,\",\",I0,\",\",I0,14(\",\",ES24.16E3))') &
      state_index,source_profile_interval,time,dt,total_cell_count,global_courant, &
      interface_cell_count,interface_courant_defined,interface_courant,top_in,bottom_out, &
      net_boundary,div_integral,closure,div_max,div_l1,face_out
    flush(restas_velocity_unit)
  end subroutine restas_source_record_velocity_audit"""
helper_path.write_text(helper[:start] + new_audit + helper[end:])

# Add units for the two new time-series ledgers.
vof_path = source_root / "src/vof.f90"
replace_once(
    vof_path,
    "  integer :: restas_source_flux_unit, restas_boundary_unit\n",
    "  integer :: restas_source_flux_unit, restas_offmask_unit, restas_rate_unit\n"
    "  integer :: restas_boundary_unit\n",
)
replace_once(
    helper_path,
    "      close(restas_source_flux_unit)\n      close(restas_boundary_unit)",
    "      close(restas_source_flux_unit)\n      close(restas_offmask_unit)\n"
    "      close(restas_rate_unit)\n      close(restas_boundary_unit)",
)

# Update source calls: velocity rows describe completed state k+1 and carry
# the source profile installed for that state, while VOF flux rows describe k.
main_path = source_root / "src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90"
replace_once(
    main_path,
    "call restas_source_record_velocity_audit(n,nh_u,dl,dzf,0,0,time,u,v,w)",
    "call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt_input,0,0,time,psi,u,v,w)",
)
replace_once(
    main_path,
    "call restas_source_record_velocity_audit(n,nh_u,dl,dzf,istep,istep,time,u,v,w)",
    "call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,istep,istep,time,psi,u,v,w)",
)
replace_once(
    main_path,
    "      source_interval=istep-1\n",
    "      ! Interval k advects U_k into completed state k+1.\n"
    "      source_interval=istep-1\n",
)
replace_once(
    main_path,
    "        call restas_source_record_inventory(n,dl,dzf,psi,istep,time)",
    "        ! Boundary/mass rows are completed state k+1 after interval k.\n"
    "        call restas_source_record_inventory(n,dl,dzf,psi,istep,time)",
)
replace_once(
    main_path,
    "      call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,istep,istep,time,psi,u,v,w)",
    "      ! Corrected U_(k+1) carries source profile k+1 for the next interval.\n"
    "      call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,istep,istep,time,psi,u,v,w)",
)

subprocess.run(["git", "-C", str(source_root), "add", "-N", "src/restas_source.inc"], check=True)
diff = subprocess.run(
    [
        "git",
        "-C",
        str(source_root),
        "diff",
        "--binary",
        "--",
        "src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90",
        "src/vof.f90",
        "src/restas_source.inc",
    ],
    check=True,
    stdout=subprocess.PIPE,
).stdout
output = candidate_root / "source-boundary.patch"
output.write_bytes(diff)
print(f"wrote {output} ({len(diff)} bytes)")
