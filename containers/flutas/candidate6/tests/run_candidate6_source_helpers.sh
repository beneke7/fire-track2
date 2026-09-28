#!/usr/bin/env bash
set -euo pipefail

source_root="${1:-/opt/FluTAS}"
case_root="${2:-/opt/flutas-source-protocol/cases/source_boundary}"
test_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
cd "$source_root/src"

# Host-only boundary checks. This compiles the pinned helper and its source
# validator without OpenACC/CUDA flags and never starts the FluTAS driver.
host_flags=(-cpp -D_USE_VOF -D_DECOMP_X -I"$build_dir" -module "$build_dir")
mpif90 "${host_flags[@]}" -c types.f90 -o "$build_dir/types.o"
mpif90 "${host_flags[@]}" -c common_mpi.f90 -o "$build_dir/common_mpi.o"
mpif90 "${host_flags[@]}" -c apps/two_phase_inc_isot/param.f90 -o "$build_dir/param.o"
mpif90 "${host_flags[@]}" -c funcs.f90 -o "$build_dir/funcs_host.o"
mpif90 "${host_flags[@]}" -c "$test_root/source_boundary_sanity_stub.f90" \
  -o "$build_dir/sanity_stub.o"
mpif90 "${host_flags[@]}" -c bound.f90 -o "$build_dir/bound_host.o"
mpif90 "${host_flags[@]}" -c mom.f90 -o "$build_dir/mom_host.o"
mpif90 "${host_flags[@]}" -c vof.f90 -o "$build_dir/vof_host.o"
mpif90 "${host_flags[@]}" -I"$build_dir" -module "$build_dir" \
  -c "$test_root/source_boundary_validator.f90" -o "$build_dir/validator.o"
mpif90 "$build_dir/types.o" "$build_dir/common_mpi.o" "$build_dir/param.o" \
  "$build_dir/funcs_host.o" "$build_dir/sanity_stub.o" "$build_dir/bound_host.o" \
  "$build_dir/mom_host.o" "$build_dir/vof_host.o" "$build_dir/validator.o" \
  -o "$build_dir/validator"

for pair in 'dry dry_four' 'active-four quiescent_four'; do
  read -r mode case_name <<< "$pair"
  (
    cd "$case_root/$case_name"
    "$build_dir/validator" "$mode"
  )
done
