#!/usr/bin/env bash
set -euo pipefail

evidence_dir="${1:-/evidence}"
mkdir -p "$evidence_dir"

export OMP_NUM_THREADS=1
export OMP_THREAD_LIMIT=1
export OMPI_NUM_THREADS=1
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

nvfortran -V > "$evidence_dir/compiler.txt" 2>&1
mpif90 --showme:command >> "$evidence_dir/compiler.txt" 2>&1
nvidia-smi > "$evidence_dir/nvidia-smi.txt"
nvaccelinfo > "$evidence_dir/nvaccelinfo.txt"
cuobjdump --list-elf /opt/FluTAS/src/flutas.two_phase_inc_isot \
  > "$evidence_dir/flutas-cubins.txt"

/opt/flutas-gpu-smoke/openacc_cc120_smoke \
  > "$evidence_dir/openacc-smoke.txt" 2>&1
mpirun --oversubscribe -np 2 \
  /opt/flutas-gpu-smoke/mpi_cuda_buffer_smoke \
  > "$evidence_dir/mpi-gpu-buffer-smoke.txt" 2>&1

bubble_dir="$evidence_dir/rising_bubble_3d"
mkdir -p "$bubble_dir"
cp -a /opt/FluTAS/examples/two_phase_inc_isot/rising_bubble_3d/. "$bubble_dir/"
cd "$bubble_dir"
if ! mpirun --oversubscribe -np 1 \
  /opt/FluTAS/src/flutas.two_phase_inc_isot \
  > "$bubble_dir/solver.log" 2>&1; then
  cat "$bubble_dir/solver.log" >&2
  exit 1
fi
python3 -c 'import test_bub; test_bub.test_answer()' \
  > "$bubble_dir/verification.txt" 2>&1
cat "$bubble_dir/verification.txt"

printf 'GPU tests passed; evidence: %s\n' "$evidence_dir"
