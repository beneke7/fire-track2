module mod_sanity
  implicit none
contains
  subroutine flutas_error(error)
    character(len=*), intent(in), optional :: error
    if(present(error)) write(*,'(a)') trim(error)
    error stop 'unexpected FluTAS sanity error in boundary helper test'
  end subroutine flutas_error
end module mod_sanity
