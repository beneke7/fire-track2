#!/bin/bash -l
#SBATCH --account=nk_meshapplied
#SBATCH --partition=cpu
#SBATCH --qos=normal
#SBATCH --job-name=ml-vof
#SBATCH --nodes=1
#SBATCH --ntasks=64
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=00:20:00
#SBATCH --signal=B:TERM@180
#SBATCH --no-requeue
#SBATCH --chdir=/scratch/nk_meshapplied/bene/fire-track2-hpc
#SBATCH --output=/scratch/nk_meshapplied/bene/fire-track2-hpc/rouaix-e1-hpc-%j.slurm.out

set -Eeuo pipefail

PROJECT_ROOT=${ROUAIX_PROJECT_ROOT:-/scratch/nk_meshapplied/bene/fire-track2-hpc}
JOB_ID=${SLURM_JOB_ID:-unknown}
RUN_ID=rouaix-e1-hpc-pilot-$JOB_ID
RUN_DIR=$PROJECT_ROOT/$RUN_ID
PAUSE_FILE=/project/nk_meshapplied/bene/fire-track2-hpc/PAUSE
STAGE=bootstrap

record_bootstrap_failure() {
  local rc=$?
  trap - EXIT
  if [[ -d $RUN_DIR && ! -e $RUN_DIR/run-state.json ]]; then
    printf '{"schema_version":1,"job_id":"%s","run_id":"%s","status":"bootstrap_failed","stage":"%s","exit_code":%s}\n' \
      "$JOB_ID" "$RUN_ID" "$STAGE" "$rc" > "$RUN_DIR/run-state.json"
  fi
  exit "$rc"
}
trap record_bootstrap_failure EXIT

[[ $JOB_ID =~ ^[0-9]+$ ]]
[[ ${SLURM_JOB_NAME:-} == ml-vof ]]
[[ ${SLURM_JOB_ACCOUNT:-} == nk_meshapplied ]]
[[ ${SLURM_JOB_NUM_NODES:-} =~ ^[0-9]+$ ]]
(( SLURM_JOB_NUM_NODES >= 1 && SLURM_JOB_NUM_NODES <= 3 ))
[[ ${SLURM_NTASKS:-} =~ ^[0-9]+$ ]]
(( SLURM_NTASKS >= 64 ))
[[ ${SLURM_CPUS_PER_TASK:-} == 1 ]]
[[ ${SLURM_CPUS_ON_NODE:-} =~ ^[0-9]+$ ]]
(( SLURM_CPUS_ON_NODE >= 64 ))
[[ ${SLURM_MEM_PER_NODE:-} =~ ^[0-9]+$ ]]
(( SLURM_MEM_PER_NODE >= 65536 ))
RUNNER_RANKS=${ROUAIX_RANKS:-$SLURM_NTASKS}
RUNNER_NODES=${ROUAIX_NODES:-$SLURM_JOB_NUM_NODES}
RUNNER_WALL_BUDGET_S=${ROUAIX_WALL_BUDGET_S:-1200}
RUNNER_END_TIME_S=${ROUAIX_END_TIME_S:-0.05}
RUNNER_DELTA_T_S=${ROUAIX_DELTA_T_S:-0.001}
RUNNER_NUMERICAL_VARIANT=${ROUAIX_NUMERICAL_VARIANT:-original}
RUNNER_WRITE_INTERVAL_S=${ROUAIX_WRITE_INTERVAL_S:-$RUNNER_END_TIME_S}
RUNNER_CASE_ID=${ROUAIX_CASE_ID:-manual}
RUNNER_RETENTION_MODE=${ROUAIX_RETENTION_MODE:-full}
RUNNER_MINIMUM_FREE_DISK_GIB=${ROUAIX_MINIMUM_FREE_DISK_GIB:-12}
export ROUAIX_HARD_DEADLINE_UTC=${ROUAIX_HARD_DEADLINE_UTC:-}
: "${ROUAIX_INPUT_ARCHIVE:?Set ROUAIX_INPUT_ARCHIVE to the verified mesh-input archive}"
: "${ROUAIX_INPUT_SHA256:?Set ROUAIX_INPUT_SHA256 to its local SHA-256}"
[[ $ROUAIX_INPUT_SHA256 =~ ^[0-9a-f]{64}$ ]]
[[ ! -e $PAUSE_FILE ]]
[[ ! -e $PROJECT_ROOT/PAUSE ]]
mkdir -- "$RUN_DIR"
STAGE=module-load

export PATH=/opt/software/packages/openfoam/bin:$PATH
module load cray-python/3.11.7 > "$RUN_DIR/module-load.log" 2>&1
module load openfoam >> "$RUN_DIR/module-load.log" 2>&1
module load OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH >> "$RUN_DIR/module-load.log" 2>&1
set +e +u
source $FOAM_BASH >> "$RUN_DIR/module-load.log" 2>&1
foam_source_status=$?
set -Eeuo pipefail
[[ $foam_source_status == 0 ]]
[[ ${WM_PROJECT_VERSION:-} == v2512 ]]
[[ ${WM_LABEL_SIZE:-} == 32 ]]
[[ ${WM_PRECISION_OPTION:-} == DP ]]
python3 --version > "$RUN_DIR/python-version.txt" 2>&1
python3 -c 'import sys; assert sys.version_info >= (3, 11), sys.version'

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export FOAM_IORANKS='(0)'
export FOAM_FILEHANDLER=collated
export ROUAIX_PROJECT_ROOT=$PROJECT_ROOT
export ROUAIX_CASE_ID=$RUNNER_CASE_ID
module list > "$RUN_DIR/modules.log" 2>&1
{
  printf 'job_id=%s\n' "$JOB_ID"
  printf 'job_name=%s\n' "$SLURM_JOB_NAME"
  printf 'nodes=%s\n' "${SLURM_JOB_NODELIST:-unknown}"
  printf 'partition=%s\n' "${SLURM_JOB_PARTITION:-unknown}"
  printf 'account=%s\n' "$SLURM_JOB_ACCOUNT"
  printf 'allocated_mpi_tasks=%s\n' "$SLURM_NTASKS"
  printf 'tasks_per_node=%s\n' "${SLURM_TASKS_PER_NODE:-unknown}"
  printf 'cpus_per_task=%s\n' "$SLURM_CPUS_PER_TASK"
  printf 'cpus_on_node=%s\n' "$SLURM_CPUS_ON_NODE"
  printf 'memory_mb=%s\n' "$SLURM_MEM_PER_NODE"
  printf 'declared_runner_ranks=%s\n' "$RUNNER_RANKS"
  printf 'declared_runner_nodes=%s\n' "$RUNNER_NODES"
  printf 'declared_wall_budget_s=%s\n' "$RUNNER_WALL_BUDGET_S"
  printf 'declared_end_time_s=%s\n' "$RUNNER_END_TIME_S"
  printf 'declared_delta_t_s=%s\n' "$RUNNER_DELTA_T_S"
  printf 'declared_numerical_variant=%s\n' "$RUNNER_NUMERICAL_VARIANT"
  printf 'declared_write_interval_s=%s\n' "$RUNNER_WRITE_INTERVAL_S"
  printf 'declared_case_id=%s\n' "$RUNNER_CASE_ID"
  printf 'declared_retention_mode=%s\n' "$RUNNER_RETENTION_MODE"
  printf 'declared_minimum_free_disk_gib=%s\n' "$RUNNER_MINIMUM_FREE_DISK_GIB"
  printf 'hard_deadline_utc=%s\n' "$ROUAIX_HARD_DEADLINE_UTC"
  printf 'WM_PROJECT_VERSION=%s\n' "$WM_PROJECT_VERSION"
  printf 'WM_LABEL_SIZE=%s\n' "$WM_LABEL_SIZE"
  printf 'WM_PRECISION_OPTION=%s\n' "$WM_PRECISION_OPTION"
  printf 'WM_OPTIONS=%s\n' "${WM_OPTIONS:-unset}"
  printf '\n-- threads and file handler --\n'
  env | grep -E '^(OMP_NUM_THREADS|OPENBLAS_NUM_THREADS|MKL_NUM_THREADS|BLIS_NUM_THREADS|NUMEXPR_NUM_THREADS|VECLIB_MAXIMUM_THREADS|FOAM_IORANKS|FOAM_FILEHANDLER)=' | sort
} > "$RUN_DIR/allocation.txt"

STAGE=pilot
exec python3 "$PROJECT_ROOT/cases/e1_rouaix_hpc/run_pilot.py" \
  --run-dir "$RUN_DIR" \
  --input-archive "$ROUAIX_INPUT_ARCHIVE" \
  --input-sha256 "$ROUAIX_INPUT_SHA256" \
  --shared-pause "$PAUSE_FILE" \
  --ranks "$RUNNER_RANKS" \
  --nodes "$RUNNER_NODES" \
  --wall-budget-s "$RUNNER_WALL_BUDGET_S" \
  --end-time-s "$RUNNER_END_TIME_S" \
  --delta-t-s "$RUNNER_DELTA_T_S" \
  --numerical-variant "$RUNNER_NUMERICAL_VARIANT" \
  --write-interval-s "$RUNNER_WRITE_INTERVAL_S" \
  --retention-mode "$RUNNER_RETENTION_MODE" \
  --minimum-free-disk-gib "$RUNNER_MINIMUM_FREE_DISK_GIB"
