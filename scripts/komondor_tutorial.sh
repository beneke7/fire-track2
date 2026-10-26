#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc
PAUSE_FILE=$PROJECT_ROOT/PAUSE

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
is_flex_node_count() { [[ ${1:-} =~ ^[1-8]$ ]]; }
is_wide_flex_node_count() {
  local node_count=${1:-} low=$2 high=$3
  [[ $node_count =~ ^[1-9][0-9]*$ ]] && (( node_count >= low && node_count <= high ))
}

(( $# == 4 )) || fail 'usage: komondor_tutorial.sh RUN_DIR REFINE STEPS DT'
RUN_DIR=${1%/}
REFINE=$2
STEPS=$3
DT=$4

[[ ${SLURM_JOB_ID:-} =~ ^[0-9]+$ ]] || fail 'must run inside a Slurm job'
[[ ${SLURM_JOB_ACCOUNT:-} == nk_meshapplied ]] || fail 'wrong Slurm account'
[[ ${SLURM_JOB_PARTITION:-} == cpu ]] || fail 'must use the cpu partition'
[[ ${SLURM_JOB_QOS:-} == normal ]] || fail 'must use the normal QOS'
[[ ${SLURM_CPUS_PER_TASK:-} == 1 ]] || fail 'expected one CPU per MPI rank'
[[ -d $PROJECT_ROOT ]] || fail "project directory is missing: $PROJECT_ROOT"

case "$REFINE:$STEPS:$DT" in
  1:100:0.001) expected_cells=9072; expected_time=0.1 ;;
  16:50:0.00002) expected_cells=2322432; expected_time=0.001 ;;
  *) fail 'only the declared smoke (1, 100, 0.001) or scaling (16, 50, 0.00002) case is allowed' ;;
esac

case ${SLURM_NTASKS:-} in
  8|16|32|64) expected_nodes=1 ;;
  300)
    if [[ ${SLURM_JOB_NAME:-} == ml-io-300f ]]; then
      is_wide_flex_node_count "${SLURM_JOB_NUM_NODES:-}" 3 8 || fail 'flexible 300-rank job must use 3 to 8 nodes'
      expected_nodes=$SLURM_JOB_NUM_NODES
    else
      expected_nodes=3
    fi
    ;;
  100)
    if [[ ${SLURM_JOB_NAME:-} == ml-io-flex ]]; then
      is_flex_node_count "${SLURM_JOB_NUM_NODES:-}" || fail 'flexible 100-rank job must use 1 to 8 nodes'
      expected_nodes=$SLURM_JOB_NUM_NODES
    else
      expected_nodes=1
    fi
    ;;
  500)
    if [[ ${SLURM_JOB_NAME:-} == ml-io-500f ]]; then
      is_wide_flex_node_count "${SLURM_JOB_NUM_NODES:-}" 5 12 || fail 'flexible 500-rank job must use 5 to 12 nodes'
      expected_nodes=$SLURM_JOB_NUM_NODES
    else
      expected_nodes=5
    fi
    ;;
  1000|1200)
    case "$SLURM_NTASKS:${SLURM_JOB_NAME:-}" in
      1000:ml-io-1000f)
        is_wide_flex_node_count "${SLURM_JOB_NUM_NODES:-}" 10 24 || fail 'flexible 1000-rank job must use 10 to 24 nodes'
        expected_nodes=$SLURM_JOB_NUM_NODES
        ;;
      1200:ml-io-1200f)
        is_wide_flex_node_count "${SLURM_JOB_NUM_NODES:-}" 10 32 || fail 'flexible 1200-rank job must use 10 to 32 nodes'
        expected_nodes=$SLURM_JOB_NUM_NODES
        ;;
      *) expected_nodes=10 ;;
    esac
    ;;
  *) fail 'unsupported MPI rank count' ;;
esac
[[ ${SLURM_JOB_NUM_NODES:-} == "$expected_nodes" ]] || fail "expected $expected_nodes nodes for $SLURM_NTASKS ranks"
case "$SLURM_NTASKS:$REFINE" in
  8:1|8:16|16:16|32:16|64:16|100:16|300:16|500:16|1000:16|1200:16) ;;
  *) fail 'rank count does not match the declared smoke or scaling case' ;;
esac

[[ $RUN_DIR == "$PROJECT_ROOT/"* ]] || fail "RUN_DIR must be directly beneath $PROJECT_ROOT"
[[ $(dirname -- "$RUN_DIR") == "$PROJECT_ROOT" ]] || fail 'RUN_DIR must be a direct child of the project directory'
run_name=${RUN_DIR#"$PROJECT_ROOT/"}
[[ $run_name =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || fail 'RUN_DIR name must use only letters, numbers, dot, underscore or dash'
[[ ! -e $RUN_DIR && ! -L $RUN_DIR ]] || fail "run directory already exists: $RUN_DIR"
archive=$PROJECT_ROOT/$run_name.tar.gz
archive_tmp=$archive.tmp.${SLURM_JOB_ID}
[[ ! -e $archive && ! -L $archive ]] || fail "archive already exists: $archive"
[[ ! -e $archive_tmp && ! -L $archive_tmp ]] || fail "temporary archive already exists: $archive_tmp"
[[ ! -e $PAUSE_FILE ]] || fail "pause sentinel exists: $PAUSE_FILE"

mkdir -m 700 -- "$RUN_DIR" || fail "could not create new run directory: $RUN_DIR"
printf '%s\n' "$SLURM_JOB_ID" > "$RUN_DIR/.created_by_komondor_tutorial"
CASE_DIR=$RUN_DIR/damBreak
RUN_LOG=$RUN_DIR/launcher.log
touch "$RUN_LOG"

record_exit() {
  rc=$?
  trap - EXIT
  status_log=$RUN_LOG
  [[ -d $RUN_DIR ]] || status_log=$PROJECT_ROOT/$run_name.archive.log
  printf 'exit_code=%s\nfinished_utc=%s\n' "$rc" "$(date -u +%FT%TZ)" >> "$status_log" 2>/dev/null || true
  exit "$rc"
}
record_signal() {
  sig=$1
  status_log=$RUN_LOG
  [[ -d $RUN_DIR ]] || status_log=$PROJECT_ROOT/$run_name.archive.log
  printf 'interrupted_signal=%s\n' "$sig" >> "$status_log" 2>/dev/null || true
  case "$sig" in INT) exit 130 ;; TERM) exit 143 ;; esac
}
record_error() {
  local rc=$1 line=$2 command=$3
  printf 'error_exit_code=%s error_line=%s failing_command=%q\n' "$rc" "$line" "$command" >> "$RUN_LOG" 2>/dev/null || true
}
trap record_exit EXIT
trap 'record_signal INT' INT
trap 'record_signal TERM' TERM
trap 'record_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

pause_check() {
  if [[ -e $PAUSE_FILE ]]; then
    printf 'pause_sentinel=%s\n' "$PAUSE_FILE" >> "$RUN_LOG"
    fail "pause sentinel exists: $PAUSE_FILE"
  fi
}
pause_check

git_revision=${TRACK2_GIT_REVISION:-}
if [[ -z $git_revision ]]; then
  git_revision=$(git -C "$PWD" rev-parse HEAD 2>/dev/null || true)
fi
git_revision=${git_revision:-unavailable}
git_dirty=${TRACK2_GIT_DIRTY:-}
if [[ -z $git_dirty ]]; then
  if git -C "$PWD" rev-parse --show-toplevel >/dev/null 2>&1; then
    git_dirty=$(git -C "$PWD" status --short 2>/dev/null | tr '\n' ' ')
    [[ -n $git_dirty ]] && git_dirty=dirty || git_dirty=clean
  else
    git_dirty=unavailable
  fi
fi

export PATH=/opt/software/packages/openfoam/bin:$PATH
module load openfoam
module load OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH
set +e +u
trap - ERR
source $FOAM_BASH > "$RUN_DIR/openfoam-source.log" 2>&1
foam_source_status=$?
set -Eeuo pipefail
trap 'record_error "$?" "$LINENO" "$BASH_COMMAND"' ERR
printf 'foam_source_exit=%s\n' "$foam_source_status" >> "$RUN_LOG"
(( foam_source_status == 0 )) || fail "OpenFOAM environment source returned $foam_source_status"
[[ -n ${WM_PROJECT_VERSION:-} ]] || fail 'OpenFOAM source did not set WM_PROJECT_VERSION'
command -v interIsoFoam >/dev/null || fail 'OpenFOAM source did not put interIsoFoam on PATH'
export FOAM_IORANKS='(0)'
export FOAM_FILEHANDLER=collated
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1

srun --kill-on-bad-exit=1 --nodes=1 --ntasks=1 --cpu-bind=cores --mem-bind=local \
  interIsoFoam -help > "$RUN_DIR/solver-banner.log" 2>&1

TUTORIAL=$FOAM_TUTORIALS/multiphase/interIsoFoam/damBreak
[[ -d $TUTORIAL ]] || fail "installed interIsoFoam tutorial is missing: $TUTORIAL"
mkdir -- "$CASE_DIR"
cp -a "$TUTORIAL"/. "$CASE_DIR"/

{
  printf 'job_id=%s\naccount=%s\npartition=%s\nqos=%s\n' \
    "$SLURM_JOB_ID" "$SLURM_JOB_ACCOUNT" "$SLURM_JOB_PARTITION" "$SLURM_JOB_QOS"
  printf 'nodes=%s\nranks=%s\ntasks_per_node=%s\ncpus_per_task=%s\njob_nodelist=%s\n' \
    "$SLURM_JOB_NUM_NODES" "$SLURM_NTASKS" "${SLURM_TASKS_PER_NODE:-unknown}" "$SLURM_CPUS_PER_TASK" "${SLURM_JOB_NODELIST:-unknown}"
  printf 'allocated_cpus_per_node=%s\ncpus_on_node=%s\n' "${SLURM_JOB_CPUS_PER_NODE:-unknown}" "${SLURM_CPUS_ON_NODE:-unknown}"
  printf 'memory_per_node=%s\nmemory_per_cpu=%s\n' "${SLURM_MEM_PER_NODE:-unknown}" "${SLURM_MEM_PER_CPU:-unknown}"
  printf 'serial_setup_cpus_per_task=8\n'
  printf 'refine_xy=%s\nsteps=%s\ndelta_t_s=%s\nend_time_s=%s\nexpected_cells=%s\n' \
    "$REFINE" "$STEPS" "$DT" "$expected_time" "$expected_cells"
  foam_build=$(awk -F: '/^Build[[:space:]]*:/ {sub(/^[[:space:]]*/, "", $2); print $2; exit}' "$RUN_DIR/solver-banner.log")
  printf 'foam_project_version=%s\nfoam_build=%s\n' "$WM_PROJECT_VERSION" "${foam_build:-unreported}"
  printf 'executable=%s\n' "$(command -v interIsoFoam)"
  printf 'executable_sha256=%s\n' "$(sha256sum "$(command -v interIsoFoam)" | awk '{print $1}')"
  printf 'script_sha256=%s\n' "$(sha256sum "$0" | awk '{print $1}')"
  printf 'git_revision=%s\ngit_dirty=%s\n' "$git_revision" "$git_dirty"
  printf 'started_utc=%s\n' "$(date -u +%FT%TZ)"
  printf 'FOAM_IORANKS=%s\nFOAM_FILEHANDLER=%s\n' "$FOAM_IORANKS" "$FOAM_FILEHANDLER"
} > "$RUN_DIR/manifest.txt"
module list > "$RUN_DIR/modules.log" 2>&1

find "$CASE_DIR" -type f -print0 | sort -z | xargs -0 sha256sum > "$RUN_DIR/tutorial-inputs.sha256"

python3 - "$CASE_DIR/system/blockMeshDict" "$REFINE" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
factor = int(sys.argv[2])
text = path.read_text(encoding="utf-8")
pattern = re.compile(r"(hex\s+\([^)]*\)\s*\()\s*(\d+)\s+(\d+)\s+(\d+)\s*(\))")
matches = list(pattern.finditer(text))
expected = [(46, 16, 1), (38, 16, 1), (46, 84, 1), (8, 84, 1), (38, 84, 1)]
actual = [(int(m.group(2)), int(m.group(3)), int(m.group(4))) for m in matches]
if actual != expected:
    raise SystemExit(f"unexpected stock damBreak blocks: {actual!r}")
if factor not in (1, 16):
    raise SystemExit(f"unsupported x/y refinement factor: {factor}")
updated = pattern.sub(
    lambda m: f"{m.group(1)}{int(m.group(2))*factor} {int(m.group(3))*factor} {m.group(4)}{m.group(5)}",
    text,
)
path.write_text(updated, encoding="utf-8")
PY

CONTROL=$CASE_DIR/system/controlDict
DECOMPOSE=$CASE_DIR/system/decomposeParDict

run_serial() {
  stage=$1
  shift
  printf 'stage_start=%s utc=%s\n' "$stage" "$(date -u +%FT%TZ)" >> "$RUN_LOG"
  srun --kill-on-bad-exit=1 --nodes=1 --ntasks=1 --cpus-per-task=8 --cpu-bind=cores --mem-bind=local --chdir="$CASE_DIR" \
    "$@" > "$RUN_DIR/$stage.log" 2>&1
  printf 'stage_end=%s exit=0 utc=%s\n' "$stage" "$(date -u +%FT%TZ)" >> "$RUN_LOG"
}

run_serial configure-dictionaries bash -c '
  set -euo pipefail
  control=$1 decompose=$2 end_time=$3 dt=$4 steps=$5 ranks=$6
  foamDictionary "$control" -entry stopAt -set endTime
  foamDictionary "$control" -entry endTime -set "$end_time"
  foamDictionary "$control" -entry deltaT -set "$dt"
  foamDictionary "$control" -entry adjustTimeStep -set no
  foamDictionary "$control" -entry writeControl -set timeStep
  foamDictionary "$control" -entry writeInterval -set "$steps"
  foamDictionary "$control" -entry writeFormat -set binary
  foamDictionary "$control" -entry writeCompression -set off
  foamDictionary "$control" -entry purgeWrite -set 0
  foamDictionary "$control" -entry functions -remove
  foamDictionary "$control" -entry functions -set "{
    alphaBounds
    {
      type fieldMinMax;
      libs (fieldFunctionObjects);
      fields (alpha.water);
      location false;
      log true;
      writePrecision 16;
      executeControl timeStep;
      executeInterval $steps;
      writeControl timeStep;
      writeInterval $steps;
    }
    waterVolume
    {
      type volFieldValue;
      libs (fieldFunctionObjects);
      fields (alpha.water);
      operation volIntegrate;
      regionType all;
      log true;
      writeFields false;
      writeControl timeStep;
      writeInterval $steps;
    }
  }"
  foamDictionary "$control" -entry OptimisationSwitches -set "{fileHandler collated; maxThreadFileBufferSize 0; writeNowSignal 10; stopAtWriteNowSignal 12;}"
  foamDictionary "$decompose" -entry numberOfSubdomains -set "$ranks"
  foamDictionary "$decompose" -entry method -set scotch
' _ "$CONTROL" "$DECOMPOSE" "$expected_time" "$DT" "$STEPS" "$SLURM_NTASKS"
sha256sum "$CASE_DIR/system/blockMeshDict" "$CONTROL" "$DECOMPOSE" > "$RUN_DIR/configured-inputs.sha256"

write_file_count() { find "$RUN_DIR" -xdev | wc -l | tr -d ' '; }
printf 'inode_entries_before=%s\n' "$(write_file_count)" >> "$RUN_LOG"

[[ -d $CASE_DIR/0.orig && ! -e $CASE_DIR/0 ]] || fail 'expected pristine tutorial 0.orig and no 0 directory'
cp -a -- "$CASE_DIR/0.orig" "$CASE_DIR/0"
run_serial blockMesh blockMesh
run_serial setFields setFields
run_serial checkMesh checkMesh -allTopology -allGeometry
grep -q 'Mesh OK\.' "$RUN_DIR/checkMesh.log" || fail 'checkMesh did not report Mesh OK.'
mesh_cells=$(sed -nE 's/.*cells:[[:space:]]*([0-9,]+).*/\1/p' "$RUN_DIR/checkMesh.log" | head -n 1 | tr -d ',')
[[ $mesh_cells == "$expected_cells" ]] || fail "mesh has ${mesh_cells:-no reported} cells; expected $expected_cells"
find "$CASE_DIR/constant/polyMesh" -type f -print0 | sort -z | xargs -0 sha256sum > "$RUN_DIR/mesh.sha256"
run_serial decomposePar decomposePar -force -fileHandler collated

pause_check
solver_start_ns=$(date +%s%N)
set +e
srun --kill-on-bad-exit=1 --nodes="$SLURM_JOB_NUM_NODES" --ntasks="$SLURM_NTASKS" \
  --cpus-per-task=1 --cpu-bind=cores --mem-bind=local \
  --chdir="$CASE_DIR" \
  interIsoFoam -parallel > "$RUN_DIR/interIsoFoam.log" 2>&1
solver_status=$?
set -e
solver_end_ns=$(date +%s%N)
solver_wall_s=$(python3 - "$solver_start_ns" "$solver_end_ns" <<'PY'
import sys
print(f"{(int(sys.argv[2]) - int(sys.argv[1])) / 1e9:.6f}")
PY
)
if (( solver_status != 0 )); then
  printf 'solver_exit_code=%s\nsolver_wall_s=%s\n' "$solver_status" "$solver_wall_s" >> "$RUN_LOG"
  exit "$solver_status"
fi

python3 - "$RUN_DIR/interIsoFoam.log" "$STEPS" "$expected_time" <<'PY'
import math
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
steps = int(sys.argv[2])
expected_time = float(sys.argv[3])
times = re.findall(r"^Time = ([^\s]+)", text, re.MULTILINE)
if len(times) != steps or not math.isclose(float(times[-1]), expected_time, rel_tol=0, abs_tol=1e-12):
    raise SystemExit(f"expected {steps} steps ending at {expected_time}; found {len(times)} ending at {times[-1] if times else 'none'}")
global_matches = re.findall(r"^Courant Number mean:\s*([-+0-9.eE]+)\s+max:\s*([-+0-9.eE]+)", text, re.MULTILINE)
interface_matches = re.findall(r"^Interface Courant Number mean:\s*([-+0-9.eE]+)\s+max:\s*([-+0-9.eE]+)", text, re.MULTILINE)
if len(global_matches) < steps:
    raise SystemExit(f"expected at least {steps} global Courant diagnostics; found {len(global_matches)}")
for mean_s, max_s in global_matches + interface_matches:
    mean, maximum = float(mean_s), float(max_s)
    if not math.isfinite(mean) or not math.isfinite(maximum) or maximum > 0.5:
        raise SystemExit(f"non-finite or excessive Courant number: mean={mean_s}, max={max_s}")
if re.search(r"\b(?:nan|[-+]?inf(?:inity)?)\b", text, re.IGNORECASE):
    raise SystemExit("solver log contains NaN or infinity")
PY

run_serial reconstructPar reconstructPar -latestTime -fileHandler collated
touch "$CASE_DIR/damBreak.foam"
final_field=$CASE_DIR/$expected_time/alpha.water
[[ -s $final_field || -s $final_field.gz ]] || fail "reconstructed final alpha.water is missing: $final_field"
find "$CASE_DIR/$expected_time" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum > "$RUN_DIR/final-fields.sha256"

minmax_file=$(find "$CASE_DIR/postProcessing/alphaBounds" -type f -name fieldMinMax.dat -print -quit 2>/dev/null || true)
[[ -n $minmax_file ]] || fail 'fieldMinMax output is missing'
python3 - "$minmax_file" "$expected_time" <<'PY'
import math
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_time = float(sys.argv[2])
rows = []
header = []
for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
    stripped = line.strip()
    if not stripped:
        continue
    if stripped.startswith("#"):
        columns = stripped.lstrip("#").split()
        if columns and columns[0] == "Time":
            header = columns
        continue
    fields = line.split()
    try:
        time = float(fields[0])
        if "min(alpha.water)" in header and "max(alpha.water)" in header:
            minimum = float(fields[header.index("min(alpha.water)")])
            maximum = float(fields[header.index("max(alpha.water)")])
        elif len(fields) >= 4 and fields[1] == "alpha.water":
            minimum, maximum = float(fields[-2]), float(fields[-1])
        else:
            continue
    except ValueError:
        continue
    rows.append((time, minimum, maximum))
if len(rows) != 1 or not math.isclose(rows[0][0], expected_time, rel_tol=0, abs_tol=1e-12):
    raise SystemExit(f"expected one alpha.water extrema row at {expected_time}; found {rows!r}")
_, minimum, maximum = rows[0]
if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum < -1e-12 or maximum > 1 + 1e-12:
    raise SystemExit(f"alpha.water is non-finite or outside [0,1] at reported precision: min={minimum}, max={maximum}")
PY

volume_file=$(find "$CASE_DIR/postProcessing/waterVolume" -type f -name '*.dat' -print -quit 2>/dev/null || true)
[[ -n $volume_file ]] || fail 'volFieldValue output is missing'
volume_integral=$(python3 - "$volume_file" <<'PY'
import math
import sys
from pathlib import Path

values = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    try:
        value = float(line.split()[-1])
    except (IndexError, ValueError):
        continue
    if math.isfinite(value):
        values.append(value)
if not values:
    raise SystemExit("no finite volume integral in volFieldValue output")
print(f"{values[-1]:.16g}")
PY
)
printf 'solver_exit_code=0\nsolver_wall_s=%s\nsimulated_seconds_per_wall_hour=%s\n' \
  "$solver_wall_s" "$(python3 - "$expected_time" "$solver_wall_s" <<'PY'
import sys
print(f"{float(sys.argv[1]) / float(sys.argv[2]) * 3600:.6g}")
PY
)" >> "$RUN_LOG"
printf 'mesh_cells=%s\nfinal_alpha_minmax=%s\nfinal_water_volume_integral_m3=%s\nfinal_volume_integral_file=%s\n' \
  "$mesh_cells" "$minmax_file" "$volume_integral" "$volume_file" >> "$RUN_LOG"
printf 'inode_entries_after=%s\n' "$(write_file_count)" >> "$RUN_LOG"
printf 'job_completed=true\n' >> "$RUN_LOG"

printf 'verified_archive=%s\n' "$archive" >> "$RUN_LOG"
printf 'exit_code=0\nfinished_utc=%s\n' "$(date -u +%FT%TZ)" >> "$RUN_LOG"
tar -czf "$archive_tmp" -C "$PROJECT_ROOT" "$run_name"
gzip -t "$archive_tmp"
archive_contents=$(tar -tzf "$archive_tmp")
grep -Fxq "$run_name/.created_by_komondor_tutorial" <<< "$archive_contents"
mv -- "$archive_tmp" "$archive"
[[ $(cat "$RUN_DIR/.created_by_komondor_tutorial") == "$SLURM_JOB_ID" ]] || fail 'run ownership marker does not match this job'
[[ $(realpath -e -- "$RUN_DIR") == "$RUN_DIR" ]] || fail 'run path changed before cleanup'
rm -rf -- "$RUN_DIR"
trap - EXIT INT TERM
exit 0
