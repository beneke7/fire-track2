program openacc_cc120_smoke
  implicit none
  integer, parameter :: n = 1024
  integer :: i
  integer :: values(n)

  !$acc parallel loop copyout(values)
  do i = 1, n
    values(i) = 3 * i + 7
  end do
  !$acc end parallel loop

  do i = 1, n
    if (values(i) /= 3 * i + 7) error stop "OpenACC output mismatch"
  end do

  print *, "OpenACC GPU kernel PASS; output_count=1024"
end program openacc_cc120_smoke
