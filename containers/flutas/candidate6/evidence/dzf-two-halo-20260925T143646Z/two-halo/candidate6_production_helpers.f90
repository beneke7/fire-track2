module mod_param
  implicit none
  integer, parameter :: rp=selected_real_kind(15,300)
  real(rp), parameter :: rho1=1000._rp
end module mod_param

module candidate6_production_helpers
  use mod_param, only: rp
  implicit none
  logical :: restas_source_loaded=.false.,restas_source_log_open=.false.
  integer :: restas_boundary_unit=31,restas_mass_unit=32,restas_velocity_unit=33
  real(rp) :: restas_step_in_volume(6)=0._rp,restas_step_out_volume(6)=0._rp
  real(rp) :: restas_cumulative_in_mass=0._rp,restas_cumulative_out_mass=0._rp
  real(rp) :: restas_initial_mass=0._rp
contains
  subroutine restas_source_accumulate_boundary_flux(n,dl,dzf,dir,flux)
    implicit none
    integer, intent(in) :: n(3),dir
    real(rp), intent(in) :: dl(3),dzf(0:)
    real(rp), intent(in) :: flux(0:,0:,0:)
    integer :: i,j,k,low_face,high_face
    real(rp) :: area,outward_volume
    if(.not.restas_source_loaded) return
    select case(dir)
    case(1)
      low_face=1
      high_face=2
      do k=1,n(3)
        area=dl(2)*dzf(k)
        do j=1,n(2)
          call restas_source_add_boundary_volume(low_face,-flux(0,j,k)*area)
          call restas_source_add_boundary_volume(high_face,flux(n(1),j,k)*area)
        enddo
      enddo
    case(2)
      low_face=3
      high_face=4
      do k=1,n(3)
        area=dl(1)*dzf(k)
        do i=1,n(1)
          call restas_source_add_boundary_volume(low_face,-flux(i,0,k)*area)
          call restas_source_add_boundary_volume(high_face,flux(i,n(2),k)*area)
        enddo
      enddo
    case(3)
      low_face=5
      high_face=6
      area=dl(1)*dl(2)
      do j=1,n(2)
        do i=1,n(1)
          call restas_source_add_boundary_volume(low_face,-flux(i,j,0)*area)
          call restas_source_add_boundary_volume(high_face,flux(i,j,n(3))*area)
        enddo
      enddo
    case default
      error stop 'Unsupported geometric flux direction'
    end select
  end subroutine restas_source_accumulate_boundary_flux

  subroutine restas_source_add_boundary_volume(face,outward_volume)
    implicit none
    integer, intent(in) :: face
    real(rp), intent(in) :: outward_volume
    if(outward_volume.ge.0._rp) then
      restas_step_out_volume(face)=restas_step_out_volume(face)+outward_volume
    else
      restas_step_in_volume(face)=restas_step_in_volume(face)-outward_volume
    endif
  end subroutine restas_source_add_boundary_volume

  subroutine restas_source_record_inventory(n,dl,dzf,vof,step_index,time)
    use mod_param, only: rho1
    implicit none
    integer, intent(in) :: n(3),step_index
    real(rp), intent(in) :: dl(3),dzf(0:),time
    real(rp), intent(in) :: vof(0:,0:,0:)
    integer :: i,j,k,face
    real(rp) :: box_mass,residual,net_volume,face_in_mass(6),face_out_mass(6)
    if(.not.restas_source_loaded.or..not.restas_source_log_open) return
    box_mass=0._rp
    do k=1,n(3)
      do j=1,n(2)
        do i=1,n(1)
          box_mass=box_mass+rho1*vof(i,j,k)*dl(1)*dl(2)*dzf(k)
        enddo
      enddo
    enddo
    if(step_index.eq.0) then
      restas_initial_mass=box_mass
      restas_cumulative_in_mass=0._rp
      restas_cumulative_out_mass=0._rp
    else
      restas_cumulative_in_mass=restas_cumulative_in_mass+rho1*sum(restas_step_in_volume)
      restas_cumulative_out_mass=restas_cumulative_out_mass+rho1*sum(restas_step_out_volume)
    endif
    residual=restas_cumulative_in_mass-restas_cumulative_out_mass- &
             (box_mass-restas_initial_mass)
    face_in_mass=rho1*restas_step_in_volume
    face_out_mass=rho1*restas_step_out_volume
    net_volume=sum(restas_step_in_volume)-sum(restas_step_out_volume)
    write(restas_boundary_unit,'(I0,12(",",ES24.16E3))') step_index, &
      restas_step_in_volume(1),restas_step_out_volume(1), &
      restas_step_in_volume(2),restas_step_out_volume(2), &
      restas_step_in_volume(3),restas_step_out_volume(3), &
      restas_step_in_volume(4),restas_step_out_volume(4), &
      restas_step_in_volume(5),restas_step_out_volume(5), &
      restas_step_in_volume(6),restas_step_out_volume(6)
    write(restas_mass_unit,'(I0,19(",",ES24.16E3))') step_index,time,box_mass, &
      restas_initial_mass,restas_cumulative_in_mass,restas_cumulative_out_mass,residual, &
      net_volume,face_in_mass(1),face_out_mass(1),face_in_mass(2),face_out_mass(2), &
      face_in_mass(3),face_out_mass(3),face_in_mass(4),face_out_mass(4), &
      face_in_mass(5),face_out_mass(5),face_in_mass(6),face_out_mass(6)
    flush(restas_boundary_unit)
    flush(restas_mass_unit)
  end subroutine restas_source_record_inventory

  subroutine restas_source_record_velocity_audit(n,nh_u,dl,dzf,dt,state_index, &
                                                    source_profile_interval,time,vof,u,v,w)
    implicit none
    integer, intent(in) :: n(3),nh_u,state_index,source_profile_interval
    real(rp), intent(in) :: dl(3),dzf(0:),dt,time
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
          ! Preserve the inherited audit's division by dzf(k) in all directions.
          ! This is distinct from the v1.2 timestep restriction, which uses the
          ! captured dzfi(k)/dzci(k) operands and source-order multiplication.
          ! These are advective Courant diagnostics, not the complete stability limit.
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
    write(restas_velocity_unit,'(I0,",",I0,2(",",ES24.16E3),",",I0,",",ES24.16E3,",",I0,",",I0,14(",",ES24.16E3))') &
      state_index,source_profile_interval,time,dt,total_cell_count,global_courant, &
      interface_cell_count,interface_courant_defined,interface_courant,top_in,bottom_out, &
      net_boundary,div_integral,closure,div_max,div_l1,face_out
    flush(restas_velocity_unit)
  end subroutine restas_source_record_velocity_audit
end module candidate6_production_helpers
