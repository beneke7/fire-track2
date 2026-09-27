program source_boundary_behavior_test
  use mpi
  use mod_types, only: rp, MPI_REAL_RP
  use mod_param, only: cbcvof, bcvof
  use mod_common_mpi, only: comm_cart,left,right,front,back,top,bottom
  use mod_vof, only: restas_source_read, restas_source_enabled, &
                     restas_source_active_at, restas_source_get_background, &
                     restas_source_validate, restas_source_apply_velocity, &
                     restas_source_refresh_vof_state
  use mod_mom, only: momad_xyz_tw_cen
  implicit none
  integer, parameter :: nx=160,ny=84,nz=40,nh_d=2,nh_u=2
  integer :: ng(3),i,j,k,mpi_ierr,halo(3)
  real(rp), parameter :: dt_input=1.e-4_rp
  real(rp) :: dl(3),dli(3),dzc(1-nh_d:nz+nh_d),dzf(1-nh_d:nz+nh_d)
  real(rp) :: dzci_inv(1-nh_d:nz+nh_d),dzfi_inv(1-nh_d:nz+nh_d)
  real(rp) :: bcvel(0:1,3,3),bcpre(0:1,3)
  real(rp) :: gacc(3),bvel(3),dpdl(3),background(3),qtop,qbottom,expected_return
  real(rp) :: rhs_x,rhs_y,expected_delta
  real(rp), allocatable :: u(:,:,:),v(:,:,:),w(:,:,:),vof(:,:,:)
  real(rp), allocatable :: nor(:,:,:,:),cur(:,:,:,:),kappa(:,:,:),d_thinc(:,:,:)
  real(rp), allocatable :: rho(:,:,:),mu(:,:,:),dudt(:,:,:),dvdt(:,:,:),dwdt(:,:,:)
  character(len=1) :: cbcvel(0:1,3,3),cbcpre(0:1,3)
  character(len=32) :: expected_case
  logical :: is_outflow(0:1,3),is_forced(3),is_crossflow,is_active
  logical, parameter :: constant_dt=.true.,restart=.false.,late_init=.false.

  call get_command_argument(1,expected_case)
  if(len_trim(expected_case).eq.0) error stop 'Expected fixture mode argument'
  call MPI_Init(mpi_ierr)
  comm_cart=MPI_COMM_WORLD
  left=MPI_PROC_NULL
  right=MPI_PROC_NULL
  front=MPI_PROC_NULL
  back=MPI_PROC_NULL
  top=MPI_PROC_NULL
  bottom=MPI_PROC_NULL
  halo=MPI_REAL_RP

  ng=(/nx,ny,nz/)
  dl=0.025_rp
  dli=1._rp/dl
  dzc=dl(3)
  dzf=dl(3)
  dzci_inv=1._rp/dl(3)
  dzfi_inv=1._rp/dl(3)
  cbcvel='P'
  cbcvel(:,3,:)='D'
  cbcpre='P'
  cbcpre(:,3)='N'
  cbcvof='P'
  cbcvof(:,3)='N'
  bcvel=0._rp
  bcpre=0._rp
  bcvof=0._rp
  is_outflow=.false.
  is_forced=.false.
  bvel=0._rp
  dpdl=0._rp

  call restas_source_read()
  if(.not.restas_source_enabled()) error stop 'Validator fixture was not loaded'
  call restas_source_get_background(background)
  is_crossflow=index(trim(expected_case),'crossflow').gt.0
  is_active=index(trim(expected_case),'active').eq.1
  bcvel(:,3,1)=background(1)
  bcvel(:,3,2)=background(2)
  gacc=(/0._rp,0._rp,0._rp/)
  if(is_crossflow) gacc(3)=-9.81_rp

  select case(trim(expected_case))
  case('dry')
    if(restas_source_active_at(2).or.restas_source_active_at(11)) &
      error stop 'Dry fixture unexpectedly activates source intervals'
    if(any(background.ne.0._rp)) error stop 'Quiescent dry fixture has nonzero background'
  case('dry-crossflow')
    if(restas_source_active_at(2).or.restas_source_active_at(11)) &
      error stop 'Dry crossflow fixture unexpectedly activates source intervals'
    if(any(background.ne.(/-50._rp,0._rp,0._rp/))) &
      error stop 'Dry crossflow fixture background is incorrect'
  case('active-one','active-four')
    if(.not.restas_source_active_at(2).or..not.restas_source_active_at(11).or. &
       restas_source_active_at(12)) error stop 'Active fixture interval is not [2,12)'
    if(any(background.ne.0._rp)) error stop 'Quiescent active fixture has nonzero background'
  case('active-crossflow')
    if(.not.restas_source_active_at(2).or..not.restas_source_active_at(11).or. &
       restas_source_active_at(12)) error stop 'Active crossflow interval is not [2,12)'
    if(any(background.ne.(/-50._rp,0._rp,0._rp/))) &
      error stop 'Active crossflow fixture background is incorrect'
  case default
    error stop 'Unknown fixture mode'
  end select

  call restas_source_validate(ng,dl,dt_input,constant_dt,cbcvel,cbcpre,cbcvof, &
    bcvel,bcpre,bcvof,is_outflow,restart,late_init,is_forced,gacc,bvel,dpdl,'cfr')

  allocate(u(1-nh_u:nx+nh_u,1-nh_u:ny+nh_u,1-nh_u:nz+nh_u))
  allocate(v(1-nh_u:nx+nh_u,1-nh_u:ny+nh_u,1-nh_u:nz+nh_u))
  allocate(w(1-nh_u:nx+nh_u,1-nh_u:ny+nh_u,1-nh_u:nz+nh_u))
  u=0._rp
  v=0._rp
  w=0._rp
  if(expected_case.eq.'active-one') then
    call restas_source_apply_velocity(ng,nh_u,2,dl,u,v,w,qtop,qbottom)
    expected_return=-0.72_rp/8.4_rp
    if(abs(qtop-0.72_rp).gt.1.e-12_rp.or.abs(qbottom-0.72_rp).gt.1.e-12_rp) &
      error stop 'One-slot helper returned the wrong volume rate'
  else if(expected_case.eq.'active-four'.or.expected_case.eq.'active-crossflow') then
    call restas_source_apply_velocity(ng,nh_u,2,dl,u,v,w,qtop,qbottom)
    expected_return=-2.88_rp/8.4_rp
    if(abs(qtop-2.88_rp).gt.1.e-12_rp.or.abs(qbottom-2.88_rp).gt.1.e-12_rp) &
      error stop 'Four-slot helper returned the wrong volume rate'
    if(abs(w(74,2,nz)+4.8_rp).gt.1.e-12_rp.or. &
       abs(w(73,2,nz)).gt.1.e-12_rp) error stop 'Active source mask was not applied'
  else
    call restas_source_apply_velocity(ng,nh_u,0,dl,u,v,w,qtop,qbottom)
    expected_return=0._rp
    if(qtop.ne.0._rp.or.qbottom.ne.0._rp) error stop 'Dry source/return must be zero'
  endif
  do j=1-nh_u,ny+nh_u
    do i=1-nh_u,nx+nh_u
      if(abs(w(i,j,0)-expected_return).gt.1.e-12_rp) &
        error stop 'Bottom return is inconsistent across periodic x/y halos'
    enddo
  enddo

  if(expected_case.eq.'active-four') call test_phase_transition_and_momentum_halos()
  write(*,'(a)') 'PASS source-boundary behavior: '//trim(expected_case)
  call MPI_Finalize(mpi_ierr)

contains

  subroutine test_phase_transition_and_momentum_halos()
    real(rp) :: normal_on,normal_off
    allocate(vof(0:nx+1,0:ny+1,0:nz+1))
    allocate(nor(0:nx+1,0:ny+1,0:nz+1,1:3))
    allocate(cur(0:nx+1,0:ny+1,0:nz+1,1:6))
    allocate(kappa(0:nx+1,0:ny+1,0:nz+1),d_thinc(0:nx+1,0:ny+1,0:nz+1))
    allocate(rho(0:nx+1,0:ny+1,0:nz+1),mu(0:nx+1,0:ny+1,0:nz+1))
    allocate(dudt(1:nx,1:ny,1:nz),dvdt(1:nx,1:ny,1:nz),dwdt(1:nx,1:ny,1:nz))
    vof=0.99_rp
    vof(1:nx,1:ny,1:nz)=0.25_rp
    nor=0._rp
    cur=0._rp
    kappa=0._rp
    d_thinc=0._rp
    rho=1000._rp
    mu=0._rp
    u=0._rp
    v=0._rp
    w=0._rp

    ! Interval 11 imposes liquid at active inflow despite a stale 0.99 ghost.
    call restas_source_apply_velocity(ng,nh_u,11,dl,u,v,w,qtop,qbottom)
    vof(:,:,nz+1)=0.99_rp
    call restas_source_refresh_vof_state(ng,dli,nh_d,nh_u,dzc,dzf,halo,11, &
      vof,w,nor,cur,kappa,d_thinc)
    if(abs(vof(74,2,nz+1)-1._rp).gt.1.e-12_rp) &
      error stop 'Active liquid inflow did not replace the stale ghost'
    if(abs(vof(74,2,nz)-0.25_rp).gt.1.e-12_rp) &
      error stop 'Fractional interior alpha changed during boundary refresh'
    normal_on=nor(74,2,nz,3)
    if(normal_on.lt.0.9_rp) error stop 'VOF reconstruction did not see active liquid inflow'

    ! At interval 12 the source is off. Generic NN fill must replace the old
    ! liquid ghost with the fractional interior value before reconstruction.
    call restas_source_apply_velocity(ng,nh_u,12,dl,u,v,w,qtop,qbottom)
    vof(:,:,nz+1)=0.99_rp
    call restas_source_refresh_vof_state(ng,dli,nh_d,nh_u,dzc,dzf,halo,12, &
      vof,w,nor,cur,kappa,d_thinc)
    if(abs(vof(74,2,nz+1)-0.25_rp).gt.1.e-12_rp) &
      error stop 'Shutoff did not remove stale liquid from the top ghost'
    normal_off=nor(74,2,nz,3)
    if(abs(normal_off).gt.1.e-12_rp.or.abs(normal_on-normal_off).lt.0.5_rp) &
      error stop 'Shutoff geometry was not rebuilt before the next flux sweep'

    ! Synthetic top reverse flow is outflow: generic NN extrapolation wins and
    ! source preparation leaves that extrapolated fractional alpha unchanged.
    w(74,2,nz)=0.25_rp
    vof(74,2,nz+1)=0.99_rp
    call restas_source_refresh_vof_state(ng,dli,nh_d,nh_u,dzc,dzf,halo,12, &
      vof,w,nor,cur,kappa,d_thinc)
    if(abs(vof(74,2,nz+1)-0.25_rp).gt.1.e-12_rp) &
      error stop 'Top outflow did not retain generic extrapolated alpha'

    ! Use the actual CPU momentum routine to verify its periodic edge stencils
    ! consume the bottom return halo. No time integration or advection is run.
    call restas_source_apply_velocity(ng,nh_u,11,dl,u,v,w,qtop,qbottom)
    u=1._rp
    v=1._rp
    rho=1._rp
    mu=0._rp
    call momad_xyz_tw_cen(nx,ny,nz,1._rp/dl(1),1._rp/dl(2),1._rp/dl(3), &
      nh_d,nh_u,dzci_inv,dzfi_inv,u,v,w,mu,rho,dudt,dvdt,dwdt)
    rhs_x=dudt(nx,1,1)
    rhs_y=dvdt(1,ny,1)
    expected_delta=20._rp*expected_return
    w(nx+1,1,0)=0._rp
    call momad_xyz_tw_cen(nx,ny,nz,1._rp/dl(1),1._rp/dl(2),1._rp/dl(3), &
      nh_d,nh_u,dzci_inv,dzfi_inv,u,v,w,mu,rho,dudt,dvdt,dwdt)
    if(abs((rhs_x-dudt(nx,1,1))-expected_delta).gt.1.e-10_rp) &
      error stop 'U momentum x-periodic edge stencil did not use the return halo'
    w(nx+1,1,0)=expected_return
    w(1,ny+1,0)=0._rp
    call momad_xyz_tw_cen(nx,ny,nz,1._rp/dl(1),1._rp/dl(2),1._rp/dl(3), &
      nh_d,nh_u,dzci_inv,dzfi_inv,u,v,w,mu,rho,dudt,dvdt,dwdt)
    if(abs((rhs_y-dvdt(1,ny,1))-expected_delta).gt.1.e-10_rp) &
      error stop 'V momentum y-periodic edge stencil did not use the return halo'
    w(1,ny+1,0)=expected_return
  end subroutine test_phase_transition_and_momentum_halos

end program source_boundary_behavior_test
