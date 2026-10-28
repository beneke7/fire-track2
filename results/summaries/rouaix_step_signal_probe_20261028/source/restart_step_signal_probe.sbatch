#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu-short
#SBATCH --qos=normal
#SBATCH --job-name=ml-sigprobe3
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:05:00
#SBATCH --no-requeue
#SBATCH --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-step-signal-helper-probe-20261028
#SBATCH --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-step-signal-helper-probe-20261028/slurm-%j.out

set -eo pipefail

RUN_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-step-signal-helper-probe-20261028
SOURCE_ROOT="$RUN_ROOT/source"
PROBE_DIR="$RUN_ROOT/probe-$SLURM_JOB_ID"
mkdir -p "$PROBE_DIR"

module load cray-python/3.11.7 > "$PROBE_DIR/modules-$SLURM_JOB_ID.log" 2>&1
module load openfoam >> "$PROBE_DIR/modules-$SLURM_JOB_ID.log" 2>&1
module load OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH >> "$PROBE_DIR/modules-$SLURM_JOB_ID.log" 2>&1
read -r -a foam_bash_args <<< "$FOAM_BASH"
set +e +u
source "${foam_bash_args[@]}" >> "$PROBE_DIR/modules-$SLURM_JOB_ID.log" 2>&1
foam_source_status=$?
set -euo pipefail
if (( foam_source_status != 0 )); then
  printf 'OpenFOAM environment setup failed rc=%s\n' "$foam_source_status" >&2
  exit "$foam_source_status"
fi
[[ ${WM_PROJECT_VERSION:-} == v2512 ]]
[[ ${WM_LABEL_SIZE:-} == 32 ]]
[[ ${WM_PRECISION_OPTION:-} == DP ]]
module list > "$PROBE_DIR/module-list-$SLURM_JOB_ID.log" 2>&1
python3 "$SOURCE_ROOT/step_signal_probe.py" "$PROBE_DIR"
