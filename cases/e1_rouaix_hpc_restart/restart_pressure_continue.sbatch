#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu-short
#SBATCH --qos=normal
#SBATCH --job-name=ml-vof
#SBATCH --nodes=3
#SBATCH --ntasks=120
#SBATCH --ntasks-per-node=40
#SBATCH --cpus-per-task=1
#SBATCH --mem=22G
#SBATCH --time=02:00:00
#SBATCH --signal=B:TERM@180
#SBATCH --no-requeue
#SBATCH --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-total-continuation-20261028/solver-runs
#SBATCH --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-total-continuation-20261028/solver-runs/slurm-%j.out

set -e
SOURCE_ROOT=${ROUAIX_SOURCE_ROOT:?missing frozen source root from dispatcher}
RUN_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-total-continuation-20261028/solver-runs

module load cray-python/3.11.7 > "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
module load openfoam >> "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
module load OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH >> "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
read -r -a foam_bash_args <<< "$FOAM_BASH"
set +e +u +o pipefail
source "${foam_bash_args[@]}" >> "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
foam_source_status=$?
set -euo pipefail
if (( foam_source_status != 0 )); then
  printf 'ERROR: OpenFOAM environment setup failed (exit %s); see %s\n' \
    "$foam_source_status" "$RUN_ROOT/modules-$SLURM_JOB_ID.log" >&2
  exit "$foam_source_status"
fi
[[ ${WM_PROJECT_VERSION:-} == v2512 ]]
[[ ${WM_LABEL_SIZE:-} == 32 ]]
[[ ${WM_PRECISION_OPTION:-} == DP ]]

export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export FOAM_IORANKS='(0)' FOAM_FILEHANDLER=collated PYTHONDONTWRITEBYTECODE=1
export ROUAIX_PROJECT_ROOT="$RUN_ROOT"
module list > "$RUN_ROOT/module-list-$SLURM_JOB_ID.log" 2>&1
printf '%s\n' "$WM_PROJECT_VERSION" > "$RUN_ROOT/foam-version-$SLURM_JOB_ID.txt"
lscpu > "$RUN_ROOT/lscpu-$SLURM_JOB_ID.txt" 2>&1 || true

exec python3 "$SOURCE_ROOT/cases/e1_rouaix_hpc_restart/run_restart.py" \
  --run-root "$RUN_ROOT" --variant pressure-total-continuation \
  --parent-contract "$SOURCE_ROOT/parent-contract.json"
