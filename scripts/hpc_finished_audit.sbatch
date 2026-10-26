#!/bin/bash -l
#SBATCH --job-name=ml-aud
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1800M
#SBATCH --time=00:10:00
#SBATCH --no-requeue
set -euo pipefail
export TZ=UTC PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
module load cray-python/3.11.7
source_root="$1"
parent_id="$2"
report_root="$3"
exec python3 "$source_root/scripts/hpc_finished_audit.py" \
    --manifest "$source_root/experiments/hpc_finished_audit_20261026.json" \
    --job-id "$parent_id" --output "$report_root/$parent_id"
