#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu-short
#SBATCH --qos=normal
#SBATCH --job-name=ml-pvfy
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --no-requeue
#SBATCH --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028/dispatch
#SBATCH --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028/dispatch/verify-parent-contract-%j.out

set -euo pipefail
PROJECT=/project/nk_meshapplied/bene/fire-track2-hpc
SHARED_ROOT="$PROJECT/rouaix-pressure-pcgdic-continuation-20261028"
SOURCE_ROOT="$PROJECT/rouaix-pressure-pcgdic-continuation-source-v4-20261028/unpacked"
module load cray-python/3.11.7 > "$SHARED_ROOT/dispatch/modules-parent-verify-$SLURM_JOB_ID.log" 2>&1
export PYTHONPATH="$SOURCE_ROOT" PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
exec python3 "$SHARED_ROOT/dispatch/verify_parent_contract_once.py" \
  --source-root "$SOURCE_ROOT" \
  --parent-run "$PROJECT/rouaix-pressure-pcgdic-restart-20261028/rouaix-restart-pressure-total-pcgdic-14705632" \
  --parent-job-id 14705632 \
  --output "$SHARED_ROOT/dispatch/parent-contract-preflight-v4-14705632.json"
