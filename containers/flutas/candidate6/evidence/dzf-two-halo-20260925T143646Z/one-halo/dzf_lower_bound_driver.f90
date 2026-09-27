program dzf_lower_bound_driver
  use mod_param, only: rp
  use candidate6_production_helpers
  implicit none
  integer, parameter :: nx=2,ny=2,nz=3,nh=1
  integer :: n(3),i,j,k
  real(rp), parameter :: dt=0.125_rp
  real(rp) :: dl(3),dzf(0:nz+1)
  real(rp) :: flux(0:nx,0:ny,0:nz)
  real(rp) :: vof(0:nx+1,0:ny+1,0:nz+1)
  real(rp) :: u(0:nx+1,0:ny+1,0:nz+1)
  real(rp) :: v(0:nx+1,0:ny+1,0:nz+1)
  real(rp) :: w(0:nx+1,0:ny+1,0:nz+1)
  character(len=512) :: prefix

  call get_command_argument(1,prefix)
  if(len_trim(prefix).eq.0) error stop 'output prefix is required'
  n=(/nx,ny,nz/)
  dl=(/2._rp,3._rp,4._rp/)
  ! Match the production caller's one-halo 0:nz+1 shape and make dzf(0)
  ! conspicuously different so an assumed-shape remap cannot pass unnoticed.
  dzf=(/0.4_rp,1.1_rp,2.3_rp,3.7_rp,5.2_rp/)
  do k=0,nz
    do j=0,ny
      do i=0,nx
        flux(i,j,k)=0.13_rp*i-0.17_rp*j+0.09_rp*k-0.24_rp
      enddo
    enddo
  enddo
  restas_source_loaded=.true.
  restas_source_log_open=.true.
  restas_step_in_volume=0._rp
  restas_step_out_volume=0._rp
  call restas_source_accumulate_boundary_flux(n,dl,dzf,1,flux)
  call restas_source_accumulate_boundary_flux(n,dl,dzf,2,flux)
  call restas_source_accumulate_boundary_flux(n,dl,dzf,3,flux)

  open(unit=31,file=trim(prefix)//'_boundary.csv',status='replace',action='write')
  open(unit=32,file=trim(prefix)//'_mass.csv',status='replace',action='write')
  open(unit=33,file=trim(prefix)//'_velocity.csv',status='replace',action='write')
  restas_boundary_unit=31
  restas_mass_unit=32
  restas_velocity_unit=33

  vof=0._rp
  do k=1,nz
    do j=1,ny
      do i=1,nx
        vof(i,j,k)=0.11_rp+0.025_rp*i+0.015_rp*j+0.02_rp*k
      enddo
    enddo
  enddo
  call restas_source_record_inventory(n,dl,dzf,vof,0,0._rp)
  do k=1,nz
    do j=1,ny
      do i=1,nx
        vof(i,j,k)=vof(i,j,k)+0.03_rp
      enddo
    enddo
  enddo
  call restas_source_record_inventory(n,dl,dzf,vof,1,dt)

  do k=0,nz+1
    do j=0,ny+1
      do i=0,nx+1
        u(i,j,k)=0.01_rp*(0.25_rp*i-0.10_rp*j+0.05_rp*k)
        v(i,j,k)=0.01_rp*(-0.15_rp*i+0.20_rp*j-0.04_rp*k)
        w(i,j,k)=1.1_rp*k
      enddo
    enddo
  enddo
  do k=1,nz
    do j=1,ny
      do i=1,nx
        if(mod(i+j+k,2).eq.0) then
          vof(i,j,k)=0.25_rp
        else
          vof(i,j,k)=0.75_rp
        endif
      enddo
    enddo
  enddo
  call restas_source_record_velocity_audit(n,nh,dl,dzf,dt,1,0,dt,vof,u,v,w)

  close(31)
  close(32)
  close(33)
end program dzf_lower_bound_driver
