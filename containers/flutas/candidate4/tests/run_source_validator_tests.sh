#!/usr/bin/env bash
set -euo pipefail

source_root="${1:-/opt/FluTAS}"
case_root="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../cases/source_boundary" && pwd)}"
test_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
cd "$source_root/src"

# Compile a narrow CPU-only helper test executable. OpenACC/CUDA flags are
# intentionally absent: it exercises validation, scalar-boundary refresh,
# reconstruction, and one momentum stencil call without starting a solver.
host_flags=(-cpp -D_USE_VOF -D_DECOMP_X -I"$build_dir" -module "$build_dir")
mpif90 "${host_flags[@]}" -c types.f90 -o "$build_dir/types.o"
mpif90 "${host_flags[@]}" -c common_mpi.f90 -o "$build_dir/common_mpi.o"
mpif90 "${host_flags[@]}" -c apps/two_phase_inc_isot/param.f90 -o "$build_dir/param.o"
mpif90 "${host_flags[@]}" -c "$test_root/source_boundary_sanity_stub.f90" \
  -o "$build_dir/sanity_stub.o"
mpif90 "${host_flags[@]}" -c bound.f90 -o "$build_dir/bound_host.o"
mpif90 "${host_flags[@]}" -c mom.f90 -o "$build_dir/mom_host.o"
mpif90 "${host_flags[@]}" -c vof.f90 -o "$build_dir/vof_host.o"
mpif90 "${host_flags[@]}" -I"$build_dir" -module "$build_dir" \
  -c "$test_root/source_boundary_validator.f90" -o "$build_dir/validator.o"
mpif90 "$build_dir/types.o" "$build_dir/common_mpi.o" "$build_dir/param.o" \
  "$build_dir/sanity_stub.o" "$build_dir/bound_host.o" "$build_dir/mom_host.o" \
  "$build_dir/vof_host.o" "$build_dir/validator.o" -o "$build_dir/validator"

mkdir -p "$build_dir/ledger"
for pair in \
  'dry dry_four' \
  'dry-crossflow dry_crossflow' \
  'active-one quiescent_one' \
  'active-four quiescent_four' \
  'active-crossflow crossflow_four' \
  'ledger-active quiescent_one active' \
  'ledger-four quiescent_four four' \
  'ledger-dry dry_four dry'; do
  read -r mode case_name ledger_name <<< "$pair"
  if (
    cd "$case_root/$case_name"
    if [[ -n "${ledger_name:-}" ]]; then
      "$build_dir/validator" "$mode" "$build_dir/ledger/$ledger_name"
    else
      "$build_dir/validator" "$mode"
    fi
  ); then
    :
  else
    if [[ -n "${ledger_name:-}" && -f "$build_dir/ledger/${ledger_name}_rate-check.csv" ]]; then
      printf 'rate-check rows preserved at failure:\n' >&2
      tail -n 5 "$build_dir/ledger/${ledger_name}_rate-check.csv" >&2
    fi
    exit 1
  fi
done

expect_rejection() {
  local case_name="$1" mode="$2" expected="$3" fixture_dir="$4" log_file="$5"
  local status=0
  mkdir -p "$fixture_dir"
  cp "$case_root/$case_name/dns.in" "$case_root/$case_name/vof.in" \
    "$case_root/$case_name/source-boundary.in" "$fixture_dir/"
  if [[ "$mode" == "unsupported-slot-count" ]]; then
    sed -i '1s/^1$/2/' "$fixture_dir/source-boundary.in"
  elif [[ "$mode" == "dry-active-interval" ]]; then
    sed -i '3s/^0 0$/2 12/' "$fixture_dir/source-boundary.in"
  else
    printf 'unknown rejection fixture %s\n' "$mode" >&2
    return 2
  fi
  if (cd "$fixture_dir" && "$build_dir/validator" active-one) >"$log_file" 2>&1; then
    printf 'Unsupported input was accepted: %s\n' "$mode" >&2
    return 1
  else
    status=$?
  fi
  if [[ "$status" -eq 0 ]] || ! grep -F "$expected" "$log_file" >/dev/null; then
    printf 'Unsupported input rejection did not report expected reason: %s\n' "$mode" >&2
    cat "$log_file" >&2
    return 1
  fi
  printf 'PASS unsupported input rejected: %s\n' "$mode"
}

expect_rejection quiescent_one unsupported-slot-count \
  'Source diagnostic supports zero, one, or four slots' \
  "$build_dir/reject-slot-count" "$build_dir/reject-slot-count.log"
expect_rejection dry_four dry-active-interval \
  'Dry diagnostic requires the disabled interval [0,0)' \
  "$build_dir/reject-dry-active" "$build_dir/reject-dry-active.log"

if (cd "$case_root/quiescent_one" && \
    "$build_dir/validator" rate-failure "$build_dir/ledger/fail") \
    >"$build_dir/rate-failure.log" 2>&1; then
  printf 'Mismatched source flux unexpectedly passed its rate check\n' >&2
  exit 1
fi
grep -F 'Geometric liquid source flux differs from frozen total-volume schedule' \
  "$build_dir/rate-failure.log" >/dev/null
printf 'PASS mismatched flux records are flushed before expected abort\n'

python3 "$test_root/test_source_boundary.py" "$source_root" "$build_dir/ledger"
