#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu
#SBATCH --qos=normal
#SBATCH --job-name=ml-vof-select
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:03:00
#SBATCH --no-requeue
#SBATCH --kill-on-invalid-dep=yes
#SBATCH --chdir=/scratch/nk_meshapplied/bene/fire-track2-hpc
#SBATCH --output=/scratch/nk_meshapplied/bene/fire-track2-hpc/rouaix-e1-hpc-selector-%j.log

set -Eeuo pipefail

PROJECT_ROOT=${ROUAIX_PROJECT_ROOT:-/scratch/nk_meshapplied/bene/fire-track2-hpc}
[[ ${SLURM_JOB_NAME:-} == ml-vof-select ]]
[[ ${SLURM_JOB_ACCOUNT:-} == nk_meshapplied ]]
[[ ${SLURM_NTASKS:-} == 1 ]]
[[ ${SLURM_CPUS_PER_TASK:-} == 1 ]]
: "${ROUAIX_QUEUE_PLAN:?Set ROUAIX_QUEUE_PLAN to the immutable queue plan}"
: "${ROUAIX_QUEUE_STATE:?Set ROUAIX_QUEUE_STATE to the shared queue-state file}"
: "${ROUAIX_QUEUE_MODE:?Set ROUAIX_QUEUE_MODE to adopt-seeds or after-case}"
[[ $ROUAIX_QUEUE_MODE == adopt-seeds || $ROUAIX_QUEUE_MODE == after-case ]]
export ROUAIX_PROJECT_ROOT=$PROJECT_ROOT

module load cray-python/3.11.7 > "$PROJECT_ROOT/selector-modules-$SLURM_JOB_ID.log" 2>&1
python3 --version > "$PROJECT_ROOT/selector-python-$SLURM_JOB_ID.log" 2>&1
python3 -c 'import sys; assert sys.version_info >= (3, 11), sys.version'

exec python3 "$PROJECT_ROOT/cases/e1_rouaix_hpc/overnight_queue.py"
