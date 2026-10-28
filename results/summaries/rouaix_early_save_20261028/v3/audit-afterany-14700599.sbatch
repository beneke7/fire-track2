#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu-short
#SBATCH --qos=normal
#SBATCH --job-name=ml-aud
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1800M
#SBATCH --time=00:10:00
#SBATCH --no-requeue
#SBATCH --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-early-save-v3-20261028/audit-slurm-%j.out
set -euo pipefail
export TZ=UTC PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
module load cray-python/3.11.7
exec python3 /project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-source-v3-20261026/scripts/hpc_finished_audit.py --manifest /project/nk_meshapplied/bene/fire-track2-hpc/rouaix-early-save-v3-20261028/audit-manifest-14700599.json --job-id 14700599 --output /project/nk_meshapplied/bene/fire-track2-hpc/rouaix-early-save-v3-20261028/audit-reports/14700599
