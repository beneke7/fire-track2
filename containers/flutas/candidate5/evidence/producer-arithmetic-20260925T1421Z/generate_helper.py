#!/usr/bin/env python3
"""Generate the archived arithmetic helper from the exact candidate test helper."""
from pathlib import Path

root = Path(__file__).resolve().parent
source_path = root / "reference" / "original-candidate5_observability_helper.f90"
target_path = root / "build" / "candidate5_m3_arithmetic_helper.f90"
source = source_path.read_text(encoding="utf-8")

decl = "  real(rp) :: bc_velocity(0:1,3,3),background(3),qtop,qbottom\n"
decl_new = decl + "  real(rp) :: zf_grid(0:nz+1),zc_grid(0:nz+1),z0\n"
assert source.count(decl) == 1
source = source.replace(decl, decl_new, 1)

spacing = (
    "  dl=0.025_rp\n"
    "  dli=1._rp/dl\n"
    "  dzc=dl(3)\n"
    "  dzf=dl(3)\n"
    "  dzci=1._rp/dzc\n"
    "  dzfi=1._rp/dzf\n"
)
initgrid = (
    "  dl=(/0.0375_rp,0.0231_rp,0.025_rp/)\n"
    "  dli=1._rp/dl\n"
    "  ! Pinned initgrid.f90 operation order for gr=0, lz=1, nz=40.\n"
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
assert source.count(spacing) == 1
source = source.replace(spacing, initgrid, 1)

arithmetic_modes = """  case('m3-pass')
    call restas_source_write_header(trim(output_prefix))
    call restas_source_capture_timestep_inputs(0._rp,dt_fixed,dl,dli,dzc,dzf,dzci,dzfi)
    u=0.125_rp
    v=0._rp
    w=0.25_rp
    call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,0,.true., &
      dli,dzci,dzfi,u,v,w)
    call restas_source_close_log()
  case('m3-bad')
    call restas_source_write_header(trim(output_prefix))
    select case(trim(pair_name))
    case('scalar_x_mismatch')
      dli(1)=nearest(dli(1),1._rp)
    case('scalar_y_zero_inverse')
      dli(2)=0._rp
    case('scalar_z_negative_spacing')
      dl(3)=-dl(3)
    case('vertical_dzc_negative_spacing')
      dzc(17)=-dzc(17)
    case('vertical_dzfi_zero_inverse')
      dzfi(17)=0._rp
    case('vertical_dzci_nan_inverse')
      dzci(17)=ieee_value(0._rp,ieee_quiet_nan)
    case('vertical_dzfi_inf_inverse')
      dzfi(17)=ieee_value(0._rp,ieee_positive_inf)
    case('scalar_x_overflow_reciprocal')
      dl(1)=1.0e-309_rp
      dli(1)=huge(1._rp)
    case('vertical_dzf_overflow_reciprocal')
      dzf(17)=1.0e-309_rp
      dzfi(17)=huge(1._rp)
    case('vertical_dzci_mismatch')
      dzci(17)=nearest(dzci(17),1._rp)
    case default
      error stop 'Unknown reciprocal corruption case'
    end select
    call restas_source_capture_timestep_inputs(0._rp,dt_fixed,dl,dli,dzc,dzf,dzci,dzfi)
    call restas_source_close_log()
  case('m3-nonfinite-rate')
    call restas_source_write_header(trim(output_prefix))
    call restas_source_capture_timestep_inputs(0._rp,dt_fixed,dl,dli,dzc,dzf,dzci,dzfi)
    u=0._rp
    v=0._rp
    w=0._rp
    u(1,1,1)=huge(1._rp)
    call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,0,.true., &
      dli,dzci,dzfi,u,v,w)
  case('m3-nonfinite-dt')
    call restas_source_write_header(trim(output_prefix))
    call restas_source_capture_timestep_inputs(0._rp,dt_fixed,dl,dli,dzc,dzf,dzci,dzfi)
    u=0.125_rp
    v=0._rp
    w=0.25_rp
    call restas_source_record_timestep_restriction(n,nh,nh, &
      ieee_value(0._rp,ieee_positive_inf),0._rp,0,.true.,dli,dzci,dzfi,u,v,w)
"""
anchor = "  case('runtime-inputs')\n"
assert source.count(anchor) == 1
source = source.replace(anchor, arithmetic_modes + anchor, 1)
target_path.write_text(source, encoding="utf-8", newline="\n")
print(f"generated={target_path}")
print(f"source_sha256={__import__('hashlib').sha256(source.encode()).hexdigest()}")
