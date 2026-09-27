#!/usr/bin/env python3
"""Apply the bounded candidate3 source edits and emit an applyable git diff."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text()
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"expected one occurrence in {path}: found {count} for {old!r}")
    path.write_text(source.replace(old, new, 1))


helper_path = root / "src/restas_source.inc"
replace_once(
    helper_path,
    "    if(q1.le.q0) error stop 'Invalid source schedule duration'",
    "    if(restas_slot_count.gt.0.and.q1.le.q0) error stop 'Invalid source schedule duration'",
)

helper = helper_path.read_text()
# Keep dimensions axis-neutral: the frozen geometry is long along x (i),
# short along y (j), matching the source masks used by this candidate.
helper = helper.replace("restas_short_x", "restas_short_dim")
helper = helper.replace("restas_long_y", "restas_long_dim")
helper_path.write_text(helper)
replace_once(
    helper_path,
    "    nxslot=nint(restas_short_dim/dl(1))\n    nyslot=nint(restas_long_dim/dl(2))",
    "    nxslot=nint(restas_long_dim/dl(1))\n    nyslot=nint(restas_short_dim/dl(2))",
)
replace_once(
    helper_path,
    "    expected_i0=(/74,82,74,82/)\n"
    "    expected_i1=(/79,87,79,87/)\n"
    "    expected_j0=(/2,2,44,44/)\n"
    "    expected_j1=(/41,41,83,83/)",
    "    expected_i0=(/40,82,40,82/)\n"
    "    expected_i1=(/79,121,79,121/)\n"
    "    expected_j0=(/36,36,44,44/)\n"
    "    expected_j1=(/41,41,49,49/)",
)

apply_start = helper.index("  subroutine restas_source_apply_velocity")
apply_end = helper.index("  end subroutine restas_source_apply_velocity", apply_start)
apply = helper[apply_start:apply_end]
replace_once(
    helper_path,
    "    do j=1,n(2)\n      do i=1,n(1)\n        w(i,j,0)=return_velocity\n      enddo\n    enddo",
    "    ! This uniform normal field must include periodic x/y stencil halos.\n"
    "    do j=1-nh_u,n(2)+nh_u\n"
    "      do i=1-nh_u,n(1)+nh_u\n"
    "        w(i,j,0)=return_velocity\n"
    "      enddo\n"
    "    enddo",
)

helper = helper_path.read_text()
assert_start = helper.index("  subroutine restas_source_assert_velocity")
assert_end = helper.index("  end subroutine restas_source_assert_velocity", assert_start)
assert_body = helper[assert_start:assert_end]
assert_body = assert_body.replace(
    "subroutine restas_source_assert_velocity(n,step_index,dl,w)",
    "subroutine restas_source_assert_velocity(n,nh_u,step_index,dl,w)",
    1,
)
assert_body = assert_body.replace(
    "integer, intent(in) :: n(3),step_index\n    real(rp), intent(in) :: dl(3),w(0:,0:,0:)",
    "integer, intent(in) :: n(3),nh_u,step_index\n"
    "    real(rp), intent(in) :: dl(3),w(1-nh_u:,1-nh_u:,1-nh_u:)",
    1,
)
assert_body = assert_body.replace(
    "    do j=1,n(2)\n      do i=1,n(1)\n        tol=restas_input_tol*max(1._rp,abs(return_velocity))",
    "    do j=1-nh_u,n(2)+nh_u\n"
    "      do i=1-nh_u,n(1)+nh_u\n"
    "        tol=restas_input_tol*max(1._rp,abs(return_velocity))",
    1,
)
if assert_body == helper[assert_start:assert_end]:
    raise SystemExit("source velocity assertion edits did not apply")
helper = helper[:assert_start] + assert_body + helper[assert_end:]

refresh = """  subroutine restas_source_refresh_vof_state(n,dli,nh_d,nh_u,dzc,dzf,halo, &
                                               step_index,vof,wg,nor,cur,kappa,d_thinc)
    use mod_param, only: cbcvof,bcvof
    use mod_bound, only: boundp
    implicit none
    integer, intent(in) :: n(3),nh_d,nh_u,halo(3),step_index
    real(rp), intent(in) :: dli(3),dzc(1-nh_d:),dzf(1-nh_d:)
    real(rp), intent(inout) :: vof(0:,0:,0:)
    real(rp), intent(in) :: wg(1-nh_u:,1-nh_u:,1-nh_u:)
    real(rp), intent(inout) :: nor(0:,0:,0:,1:),cur(0:,0:,0:,1:)
    real(rp), intent(inout) :: kappa(0:,0:,0:),d_thinc(0:,0:,0:)
    real(rp) :: dl(3)
    if(.not.restas_source_loaded) return
    dl=dli**(-1)
    ! Rebuild ordinary boundaries before applying interval-specific phase.
    call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,vof)
    call restas_source_prepare_boundary(n,nh_u,step_index,vof,wg)
    ! Reconstruction must match the refreshed alpha before the first flux sweep.
    call update_vof(n,dli,nh_d,dzc,dzf,+1,halo,vof,nor,cur,kappa,d_thinc)
  end subroutine restas_source_refresh_vof_state
  !
"""
marker = "  subroutine restas_source_write_header(path_prefix)"
if helper.count(marker) != 1:
    raise SystemExit("could not locate source helper insertion point")
helper = helper.replace(marker, refresh + marker, 1)
helper_path.write_text(helper)

vof_path = root / "src/vof.f90"
replace_once(
    vof_path,
    "  public :: restas_source_prepare_boundary,restas_source_check_volume_pair,restas_source_write_header\n",
    "  public :: restas_source_prepare_boundary,restas_source_check_volume_pair,restas_source_write_header\n"
    "  public :: restas_source_refresh_vof_state\n",
)
replace_once(
    vof_path,
    "    if(present(source_step)) then\n"
    "      call restas_source_prepare_boundary(n,nh_u,source_step,vof,wg)\n"
    "    endif",
    "    if(present(source_step)) call restas_source_refresh_vof_state( &\n"
    "      n,dli,nh_d,nh_u,dzc,dzf,halo,source_step,vof,wg,nor,cur,kappa,d_thinc)",
)
replace_once(
    vof_path,
    "    ! flux in x\n    !\n#if !defined(_TWOD)\n"
    "    if(present(source_step)) call restas_source_prepare_boundary(n,nh_u,source_step,vof,wg)\n",
    "    ! flux in x\n    !\n#if !defined(_TWOD)\n",
)

main_path = root / "src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90"
replace_once(
    main_path,
    "call restas_source_assert_velocity(n,source_interval,dl,w)",
    "call restas_source_assert_velocity(n,nh_u,source_interval,dl,w)",
)

subprocess.run(["git", "-C", str(root), "add", "-N", "src/restas_source.inc"], check=True)
diff = subprocess.run(
    ["git", "-C", str(root), "diff", "--binary", "--", "src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90", "src/vof.f90", "src/restas_source.inc"],
    check=True,
    stdout=subprocess.PIPE,
).stdout
output = Path(sys.argv[2]).resolve()
output.write_bytes(diff)
print(f"wrote {output} ({len(diff)} bytes)")
