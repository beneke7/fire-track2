#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu-short
#SBATCH --qos=normal
#SBATCH --job-name=ml-ctl
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --no-requeue
#SBATCH --signal=B:TERM@60
#SBATCH --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028
#SBATCH --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028/dispatch-%j.out

set -euo pipefail
SOURCE_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-source-v2-20261028/unpacked
module load cray-python/3.11.7 > "/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028/modules-dispatch-$SLURM_JOB_ID.log" 2>&1
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
exec python3 "$SOURCE_ROOT/cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.py" \
  --source-root "$SOURCE_ROOT" \
  --shared-root /project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028 \
  --solver-root /project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-continuation-20261028/solver-runs \
  --parent-job-id 14705632
