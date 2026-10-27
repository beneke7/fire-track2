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
#SBATCH --time=00:20:00
#SBATCH --signal=B:TERM@180
#SBATCH --no-requeue
#SBATCH --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-restart-controls-20261027
#SBATCH --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-restart-controls-20261027/slurm-%j.out

set -eo pipefail

SOURCE_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-restart-source-v2-20261027
RUN_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-restart-controls-20261027

module load cray-python/3.11.7 > "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
module load openfoam >> "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
module load OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH >> "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
set +e +u
source "$FOAM_BASH" >> "$RUN_ROOT/modules-$SLURM_JOB_ID.log" 2>&1
foam_source_status=$?
set -euo pipefail
[[ $foam_source_status == 0 ]]
[[ ${WM_PROJECT_VERSION:-} == v2512 ]]
[[ ${WM_LABEL_SIZE:-} == 32 ]]
[[ ${WM_PRECISION_OPTION:-} == DP ]]

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export FOAM_IORANKS='(0)'
export FOAM_FILEHANDLER=collated
export PYTHONDONTWRITEBYTECODE=1
export ROUAIX_PROJECT_ROOT="$RUN_ROOT"

module list > "$RUN_ROOT/module-list-$SLURM_JOB_ID.log" 2>&1
printf '%s\n' "$WM_PROJECT_VERSION" > "$RUN_ROOT/foam-version-$SLURM_JOB_ID.txt"
lscpu > "$RUN_ROOT/lscpu-$SLURM_JOB_ID.txt" 2>&1 || true

exec python3 "$SOURCE_ROOT/cases/e1_rouaix_hpc_restart/run_restart.py" \
  --run-root "$RUN_ROOT" --variant original-smoke
