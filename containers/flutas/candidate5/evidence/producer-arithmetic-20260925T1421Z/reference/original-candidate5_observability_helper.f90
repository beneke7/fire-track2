program candidate5_observability_helper
  use mpi
  use, intrinsic :: ieee_arithmetic, only: ieee_value,ieee_quiet_nan,ieee_positive_inf
  use mod_types, only: rp
  use mod_param, only: cbcvof,bcvof,rho1,rho2,mu1,mu2,sigma,cfl_c,cfl_d,time_scheme
  use mod_common_mpi, only: comm_cart,left,right,front,back,top,bottom
  use mod_bound, only: boundp,bounduvw
  use mod_vof, only: restas_source_read,restas_source_get_background,restas_source_cell, &
                     restas_source_apply_velocity,restas_source_prepare_boundary, &
                     restas_source_record_phase_stage,restas_source_record_velocity_stage, &
                     restas_source_record_timestep_restriction,restas_source_write_header, &
                     restas_source_capture_timestep_inputs,restas_source_close_log,update_property
  implicit none
  integer, parameter :: nx=160,ny=84,nz=40,nh=1
  integer :: mpi_ierr,profile,state,interval,i,j,k
  integer :: n(3),halo(3),idx_i,idx_j,idx_k
  real(rp), parameter :: dt_fixed=1.e-4_rp
  real(rp) :: dl(3),dli(3),dzc(1-nh:nz+nh),dzf(1-nh:nz+nh)
  real(rp) :: dzci(1-nh:nz+nh),dzfi(1-nh:nz+nh)
  real(rp) :: bc_velocity(0:1,3,3),background(3),qtop,qbottom
  real(rp), allocatable :: u(:,:,:),v(:,:,:),w(:,:,:),alpha(:,:,:),rho(:,:,:),mu(:,:,:)
  character(len=128) :: mode,case_name,pair_name,field_name,fault_name,stage_name
  character(len=512) :: output_prefix
  character(len=1) :: cbc_velocity(0:1,3,3)
  logical :: is_outflow(0:1,3)

  call get_command_argument(1,mode)
  call get_command_argument(2,case_name)
  call get_command_argument(3,output_prefix)
  call get_command_argument(4,pair_name)
  call get_command_argument(5,field_name)
  call get_command_argument(6,fault_name)
  call get_command_argument(7,stage_name)
  if(len_trim(stage_name).eq.0) stage_name='pre_vof_x'
  if(len_trim(mode).eq.0.or.len_trim(case_name).eq.0.or.len_trim(output_prefix).eq.0) &
    error stop 'mode, case, and output prefix are required'

  call MPI_Init(mpi_ierr)
  comm_cart=MPI_COMM_WORLD
  left=MPI_PROC_NULL
  right=MPI_PROC_NULL
  front=MPI_PROC_NULL
  back=MPI_PROC_NULL
  top=MPI_PROC_NULL
  bottom=MPI_PROC_NULL
  n=(/nx,ny,nz/)
  halo=1
  dl=0.025_rp
  dli=1._rp/dl
  dzc=dl(3)
  dzf=dl(3)
  dzci=1._rp/dzc
  dzfi=1._rp/dzf

  rho1=1000._rp
  rho2=1._rp
  mu1=0.001_rp
  mu2=1.8e-5_rp
  cfl_c=1._rp
  cfl_d=1._rp/6._rp
  time_scheme='ab2'
  sigma=0._rp
  cbcvof='P'
  cbcvof(:,3)='N'
  bcvof=0._rp
  cbc_velocity='P'
  cbc_velocity(:,3,:)='D'
  bc_velocity=0._rp
  is_outflow=.false.

  allocate(u(1-nh:nx+nh,1-nh:ny+nh,1-nh:nz+nh))
  allocate(v(1-nh:nx+nh,1-nh:ny+nh,1-nh:nz+nh))
  allocate(w(1-nh:nx+nh,1-nh:ny+nh,1-nh:nz+nh))
  allocate(alpha(0:nx+1,0:ny+1,0:nz+1))
  allocate(rho(0:nx+1,0:ny+1,0:nz+1))
  allocate(mu(0:nx+1,0:ny+1,0:nz+1))
  call restas_source_read()
  call restas_source_get_background(background)
  bc_velocity(:,3,1)=background(1)
  bc_velocity(:,3,2)=background(2)

  select case(trim(mode))
  case('runtime-inputs')
    call restas_source_write_header(trim(output_prefix))
    call restas_source_capture_timestep_inputs(0._rp,dt_fixed,dl,dli,dzc,dzf,dzci,dzfi)
    call restas_source_close_log()
  case('phase-pass')
    call restas_source_write_header(trim(output_prefix))
    do profile=1,2
      call initialize_state(profile)
      call restas_source_record_phase_stage(n,nh,profile,profile,'pre_vof_x',alpha,w,rho,mu)
      call restas_source_record_phase_stage(n,nh,profile,profile,'pre_vof_y',alpha,w,rho,mu)
      call restas_source_record_phase_stage(n,nh,profile,profile,'pre_vof_z',alpha,w,rho,mu)
      call restas_source_record_phase_stage(n,nh,profile,profile,'pre_momentum',alpha,w,rho,mu)
    enddo
    call restas_source_close_log()
  case('phase-pass-dry')
    call restas_source_write_header(trim(output_prefix))
    do profile=1,2
      call initialize_state(profile)
      call restas_source_record_phase_stage(n,nh,profile,profile,'pre_vof_x',alpha,w,rho,mu)
      call restas_source_record_phase_stage(n,nh,profile,profile,'pre_momentum',alpha,w,rho,mu)
    enddo
    call restas_source_close_log()
  case('phase-invalid-stage')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(1)
    call restas_source_record_phase_stage(n,nh,1,1,'unsupported_stage',alpha,w,rho,mu)
  case('phase-overflow')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(1)
    alpha(nx,5,5)=-huge(1._rp)
    alpha(0,5,5)=huge(1._rp)
    call restas_source_record_phase_stage(n,nh,1,1,'pre_vof_x',alpha,w,rho,mu)
  case('phase-fault')
    call restas_source_write_header(trim(output_prefix))
    profile=selected_profile(trim(pair_name))
    call initialize_state(profile)
    call phase_fault_location(trim(pair_name),idx_i,idx_j,idx_k)
    if(trim(fault_name).eq.'both') then
      call inject_phase_fault(trim(field_name),'mismatch',idx_i,idx_j,idx_k)
      call inject_phase_fault(trim(field_name),'nan',idx_i,idx_j,idx_k+1)
    else
      call inject_phase_fault(trim(field_name),trim(fault_name),idx_i,idx_j,idx_k)
    endif
    call restas_source_record_phase_stage(n,nh,profile,profile,trim(stage_name),alpha,w,rho,mu)
    error stop 'Injected phase fault was not detected'
  case('velocity-pass')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    call restas_source_record_velocity_stage(n,nh,dl,0,-1,'initial_u0',u,v,w)
    do interval=0,2
      call initialize_state(interval)
      call restas_source_record_velocity_stage(n,nh,dl,interval,interval,'pre_vof',u,v,w)
      call initialize_state(interval+1)
      call restas_source_record_velocity_stage(n,nh,dl,interval+1,interval, &
        'projection_override',u,v,w)
      call restas_source_record_velocity_stage(n,nh,dl,interval+1,interval, &
        'corrected_endpoint',u,v,w)
    enddo
    call restas_source_close_log()
  case('velocity-fault')
    call restas_source_write_header(trim(output_prefix))
    profile=selected_profile(trim(pair_name))
    call initialize_state(profile)
    call velocity_fault_location(trim(pair_name),trim(field_name),idx_i,idx_j,idx_k)
    if(trim(fault_name).eq.'both') then
      call inject_velocity_fault(trim(field_name),'mismatch',idx_i,idx_j,idx_k)
      call inject_velocity_fault(trim(field_name),'nan',idx_i,idx_j+1,idx_k)
    else
      call inject_velocity_fault(trim(field_name),trim(fault_name),idx_i,idx_j,idx_k)
    endif
    call restas_source_record_velocity_stage(n,nh,dl,profile,profile,'pre_vof',u,v,w)
    error stop 'Injected velocity fault was not detected'
  case('velocity-invalid-stage')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    call restas_source_record_velocity_stage(n,nh,dl,0,-1,'unsupported_stage',u,v,w)
  case('dt-pass-zero','dt-pass-capillary','dt-fail-crossflow','dt-terminal-crossflow')
    if(trim(mode).eq.'dt-pass-capillary') sigma=0.072_rp
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    state=0
    if(trim(mode).eq.'dt-terminal-crossflow') then
      call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,state,.false., &
        dli,dzci,dzfi,u,v,w)
    else
      call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,state,.true., &
        dli,dzci,dzfi,u,v,w)
    endif
    call restas_source_close_log()
  case('dt-nonfinite-ratio')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    call restas_source_record_timestep_restriction(n,nh,nh, &
      ieee_value(0._rp,ieee_positive_inf),0._rp,0,.true.,dli,dzci,dzfi,u,v,w)
  case('dt-nonfinite-rate')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    u(1,1,1)=huge(1._rp)
    call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,0,.true., &
      dli,dzci,dzfi,u,v,w)
  case('dt-pass-halo-min')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    dzf(0)=0.0125_rp
    dzfi(0)=1._rp/dzf(0)
    call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,0,.true., &
      dli,dzci,dzfi,u,v,w)
    call restas_source_close_log()
  case('dt-probe')
    call restas_source_write_header(trim(output_prefix))
    call initialize_state(0)
    do k=0,nz+1
      do j=0,ny+1
        do i=0,nx+1
          u(i,j,k)=real(4*i-2*j+k,rp)/16._rp
          v(i,j,k)=real(-2*i+4*j+3*k,rp)/32._rp
          w(i,j,k)=real(i-j+2*k,rp)/16._rp
        enddo
      enddo
    enddo
    call restas_source_record_timestep_restriction(n,nh,nh,dt_fixed,0._rp,0,.false., &
      dli,dzci,dzfi,u,v,w)
    call restas_source_close_log()
  case default
    error stop 'Unknown candidate5 observability test mode'
  end select
  call MPI_Finalize(mpi_ierr)

contains

  subroutine initialize_state(source_profile)
    integer, intent(in) :: source_profile
    real(rp) :: source_rate,return_rate
    u=background(1)
    v=background(2)
    w=background(3)
    call bounduvw(cbc_velocity,n,bc_velocity,nh,nh,halo,is_outflow,dl,dzc,dzf,u,v,w)
    call restas_source_apply_velocity(n,nh,source_profile,dl,u,v,w,source_rate,return_rate)

    alpha=0.25_rp
    call boundp(cbcvof,n,bcvof,nh,nh,halo,dl,dzc,dzf,alpha)
    call restas_source_prepare_boundary(n,nh,source_profile,alpha,w)
    call update_property(n,(/rho1,rho2/),alpha,rho)
    call boundp(cbcvof,n,bcvof,nh,nh,halo,dl,dzc,dzf,rho)
    call update_property(n,(/mu1,mu2/),alpha,mu)
    call boundp(cbcvof,n,bcvof,nh,nh,halo,dl,dzc,dzf,mu)
    call restas_source_prepare_boundary(n,nh,source_profile,alpha,w,rho,mu)
  end subroutine initialize_state

  integer function selected_profile(source_pair)
    character(len=*), intent(in) :: source_pair
    selected_profile=2
    if(index(source_pair,'inactive_slot').gt.0) selected_profile=1
  end function selected_profile

  subroutine phase_fault_location(source_pair,ii,jj,kk)
    character(len=*), intent(in) :: source_pair
    integer, intent(out) :: ii,jj,kk
    select case(source_pair)
    case('xlow_periodic')
      ii=0; jj=0; kk=0
    case('xhigh_periodic')
      ii=nx+1; jj=0; kk=0
    case('ylow_periodic')
      ii=1; jj=0; kk=0
    case('yhigh_periodic')
      ii=1; jj=ny+1; kk=0
    case('zhigh_active_slot','zhigh_inactive_slot')
      ii=74; jj=2; kk=nz+1
    case('zhigh_top_offmask')
      ii=1; jj=1; kk=nz+1
    case('zlow_bottom_return')
      ii=1; jj=1; kk=0
    case default
      error stop 'Unknown phase scan pair'
    end select
  end subroutine phase_fault_location

  subroutine velocity_fault_location(source_pair,component,ii,jj,kk)
    character(len=*), intent(in) :: source_pair,component
    integer, intent(out) :: ii,jj,kk
    select case(source_pair)
    case('zhigh_active_slot','zhigh_inactive_slot')
      ii=74; jj=2
      kk=nz+1
      if(component.eq.'w') kk=nz
    case('zhigh_top_offmask')
      ii=0; jj=0
      kk=nz+1
      if(component.eq.'w') kk=nz
    case('zlow_bottom_return')
      ii=0; jj=0; kk=0
    case default
      error stop 'Unknown velocity scan pair'
    end select
  end subroutine velocity_fault_location

  subroutine inject_phase_fault(field,fault,ii,jj,kk)
    character(len=*), intent(in) :: field,fault
    integer, intent(in) :: ii,jj,kk
    real(rp) :: bad_value
    bad_value=alpha(ii,jj,kk)+0.5_rp
    if(fault.eq.'nan') bad_value=ieee_value(0._rp,ieee_quiet_nan)
    select case(field)
    case('alpha')
      alpha(ii,jj,kk)=bad_value
    case('rho')
      bad_value=rho(ii,jj,kk)+0.5_rp
      if(fault.eq.'nan') bad_value=ieee_value(0._rp,ieee_quiet_nan)
      rho(ii,jj,kk)=bad_value
    case('mu')
      bad_value=mu(ii,jj,kk)+0.5_rp
      if(fault.eq.'nan') bad_value=ieee_value(0._rp,ieee_quiet_nan)
      mu(ii,jj,kk)=bad_value
    case default
      error stop 'Unknown phase property'
    end select
  end subroutine inject_phase_fault

  subroutine inject_velocity_fault(component,fault,ii,jj,kk)
    character(len=*), intent(in) :: component,fault
    integer, intent(in) :: ii,jj,kk
    real(rp) :: bad_value
    select case(component)
    case('u')
      bad_value=u(ii,jj,kk)+0.5_rp
      if(fault.eq.'nan') bad_value=ieee_value(0._rp,ieee_quiet_nan)
      u(ii,jj,kk)=bad_value
    case('v')
      bad_value=v(ii,jj,kk)+0.5_rp
      if(fault.eq.'nan') bad_value=ieee_value(0._rp,ieee_quiet_nan)
      v(ii,jj,kk)=bad_value
    case('w')
      bad_value=w(ii,jj,kk)+0.5_rp
      if(fault.eq.'nan') bad_value=ieee_value(0._rp,ieee_quiet_nan)
      w(ii,jj,kk)=bad_value
    case default
      error stop 'Unknown velocity component'
    end select
  end subroutine inject_velocity_fault

end program candidate5_observability_helper
