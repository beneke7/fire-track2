program grid_operand_probe
  use mod_types, only: rp
  use mod_initgrid, only: initgrid
  implicit none
  integer, parameter :: n=40,nh_d=1
  real(rp) :: dzc(1-nh_d:n+nh_d),dzf(1-nh_d:n+nh_d)
  real(rp) :: zc(1-nh_d:n+nh_d),zf(1-nh_d:n+nh_d),dzci(1-nh_d:n+nh_d),dzfi(1-nh_d:n+nh_d)
  integer :: k
  call initgrid('zer',n,0.0_rp,1.0_rp,nh_d,dzc,dzf,zc,zf)
  do k=1-nh_d,n+nh_d
    dzci(k)=1.0_rp/dzc(k)
    dzfi(k)=1.0_rp/dzf(k)
    write(*,'(I2,4(1X,ES24.16E3))') k,dzf(k),dzc(k),dzfi(k),dzci(k)
  enddo
end program grid_operand_probe
