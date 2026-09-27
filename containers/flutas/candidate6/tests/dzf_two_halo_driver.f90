program dzf_two_halo_driver
  use mod_param, only: rp
  use candidate6_production_helpers
  implicit none
  integer, parameter :: nx=2,ny=2,nz=3,nh_u=2
  integer :: n(3),i,j,k
  real(rp), parameter :: dt=0.125_rp
  real(rp) :: dl(3),dzf(-1:nz+2)
  real(rp) :: flux(0:nx,0:ny,0:nz),area_flux(0:nx,0:ny,0:nz)
  real(rp) :: vof(0:nx+1,0:ny+1,0:nz+1)
  real(rp) :: u(-1:nx+2,-1:ny+2,-1:nz+2)
  real(rp) :: v(-1:nx+2,-1:ny+2,-1:nz+2)
  real(rp) :: w(-1:nx+2,-1:ny+2,-1:nz+2)
  character(len=64) :: mode
  character(len=512) :: prefix

  call get_command_argument(1,mode)
  call get_command_argument(2,prefix)
  if(len_trim(mode).eq.0.or.len_trim(prefix).eq.0) &
    error stop 'mode and output prefix are required'
  if(trim(mode).ne.'explicit-slice'.and.trim(mode).ne.'whole-array-negative') &
    error stop 'mode must be explicit-slice or whole-array-negative'
  n=(/nx,ny,nz/)
  dl=(/2._rp,3._rp,4._rp/)
  ! Host-validator two-halo storage. Index -1 is a conspicuous extra halo;
  ! physical cell spacings occupy indices 1:nz and differ by cell.
  dzf(-1)=9.9_rp
  dzf(0)=0.4_rp
  dzf(1)=1.1_rp
  dzf(2)=2.3_rp
  dzf(3)=3.7_rp
  dzf(4)=5.2_rp
  dzf(5)=8.8_rp
  do k=0,nz
    do j=0,ny
      do i=0,nx
        flux(i,j,k)=0.13_rp*i-0.17_rp*j+0.09_rp*k-0.24_rp
      enddo
    enddo
  enddo
  do k=-1,nz+2
    do j=-1,ny+2
      do i=-1,nx+2
        u(i,j,k)=0.01_rp*(0.25_rp*i-0.10_rp*j+0.05_rp*k)
        v(i,j,k)=0.01_rp*(-0.15_rp*i+0.20_rp*j-0.04_rp*k)
        w(i,j,k)=1.1_rp*k
      enddo
    enddo
  enddo
  restas_source_loaded=.true.
  restas_source_log_open=.true.
  restas_step_in_volume=0._rp
  restas_step_out_volume=0._rp
  area_flux=1._rp
  if(trim(mode).eq.'explicit-slice') then
    call restas_source_accumulate_boundary_flux(n,dl,dzf(0:),1,area_flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf(0:),2,area_flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf(0:),3,area_flux)
  else
    call restas_source_accumulate_boundary_flux(n,dl,dzf,1,area_flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf,2,area_flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf,3,area_flux)
  endif
  open(unit=34,file=trim(prefix)//'_area.csv',status='replace',action='write')
  do i=1,6
    write(34,'(I0,2(",",ES24.16E3))') &
      i,restas_step_in_volume(i),restas_step_out_volume(i)
  enddo
  close(34)
  restas_step_in_volume=0._rp
  restas_step_out_volume=0._rp

  if(trim(mode).eq.'explicit-slice') then
    ! Explicitly map physical index zero from the two-halo host storage.
    call restas_source_accumulate_boundary_flux(n,dl,dzf(0:),1,flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf(0:),2,flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf(0:),3,flux)
  else
    ! Negative control: whole array maps helper dummy zero to caller index -1.
    call restas_source_accumulate_boundary_flux(n,dl,dzf,1,flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf,2,flux)
    call restas_source_accumulate_boundary_flux(n,dl,dzf,3,flux)
  endif

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
  if(trim(mode).eq.'explicit-slice') then
    call restas_source_record_inventory(n,dl,dzf(0:),vof,0,0._rp)
  else
    call restas_source_record_inventory(n,dl,dzf,vof,0,0._rp)
  endif
  do k=1,nz
    do j=1,ny
      do i=1,nx
        vof(i,j,k)=vof(i,j,k)+0.03_rp
      enddo
    enddo
  enddo
  if(trim(mode).eq.'explicit-slice') then
    call restas_source_record_inventory(n,dl,dzf(0:),vof,1,dt)
  else
    call restas_source_record_inventory(n,dl,dzf,vof,1,dt)
  endif
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
  if(trim(mode).eq.'explicit-slice') then
    call restas_source_record_velocity_audit(n,nh_u,dl,dzf(0:),dt,1,0,dt,vof,u,v,w)
  else
    call restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,1,0,dt,vof,u,v,w)
  endif
  close(31)
  close(32)
  close(33)
end program dzf_two_halo_driver
