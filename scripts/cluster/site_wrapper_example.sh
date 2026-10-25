#!/usr/bin/env bash
# Example site wrapper contract. Verify the site's Slurm/MPI plugin before use.
set -euo pipefail

profile=""
case_dir=""
ranks=""
cpus_per_task=""
job_id=""
expected_binary_sha256=""
expected_source_manifest_sha256=""
expected_openfoam_version=""
while (($#)); do
    case "$1" in
        --profile) profile="$2"; shift 2 ;;
        --case) case_dir="$2"; shift 2 ;;
        --ranks) ranks="$2"; shift 2 ;;
        --cpus-per-task) cpus_per_task="$2"; shift 2 ;;
        --job-id) job_id="$2"; shift 2 ;;
        --solver-name) shift 2 ;;
        --openfoam-version) expected_openfoam_version="$2"; shift 2 ;;
        --expected-binary-sha256) expected_binary_sha256="$2"; shift 2 ;;
        --expected-source-manifest-sha256) expected_source_manifest_sha256="$2"; shift 2 ;;
        --runtime-strategy) shift 2 ;;
        *) echo "unknown wrapper argument: $1" >&2; exit 2 ;;
    esac
done

: "${profile:?missing --profile}"
: "${case_dir:?missing --case}"
: "${ranks:?missing --ranks}"
: "${job_id:?missing --job-id}"
: "${expected_openfoam_version:?missing --openfoam-version}"
: "${FIRETRACK2_SOLVER_BIN:?set absolute path to the site-built custom solver}"
: "${FIRETRACK2_STAGING_MANIFEST:?set path to staging-manifest.json}"
: "${FIRETRACK2_SLURM_MPI_TYPE:?set the site-verified srun --mpi plugin}"
: "${FIRETRACK2_CHECKPOINT_STOP_ADAPTER:?set tested site command for write-and-stop}"
[[ "$cpus_per_task" == 1 && "${SLURM_CPUS_PER_TASK:-}" == 1 ]] || {
    echo "this wrapper expects one CPU per MPI task" >&2
    exit 2
}
[[ "${SLURM_NTASKS:-}" == "$ranks" ]] || {
    echo "wrapper rank count does not match SLURM_NTASKS" >&2
    exit 2
}
[[ -d "$case_dir" && -x "$FIRETRACK2_SOLVER_BIN" && -f "$FIRETRACK2_STAGING_MANIFEST" ]] || {
    echo "case, solver binary, or staging manifest is missing" >&2
    exit 2
}
[[ -x "$FIRETRACK2_CHECKPOINT_STOP_ADAPTER" ]] || {
    echo "checkpoint-stop adapter is missing or not executable" >&2
    exit 2
}
actual_openfoam_version="$(foamVersion)"
[[ "$actual_openfoam_version" == "$expected_openfoam_version" ]] || {
    echo "foamVersion mismatch: expected '$expected_openfoam_version', got '$actual_openfoam_version'" >&2
    exit 2
}

python3 - "$FIRETRACK2_STAGING_MANIFEST" "$FIRETRACK2_SOLVER_BIN" \
    "$expected_binary_sha256" "$expected_source_manifest_sha256" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1]).resolve(strict=True)
binary_path = pathlib.Path(sys.argv[2]).resolve(strict=True)
expected_binary, expected_source = (item.lower() for item in sys.argv[3:5])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
overlay = manifest_path.parent / "solver-overlay"

binary_hash = hashlib.sha256(binary_path.read_bytes()).hexdigest()
if binary_hash != expected_binary:
    raise SystemExit(f"site solver binary hash mismatch: {binary_hash}")

digest = hashlib.sha256()
source_rows = manifest.get("source_files")
if not isinstance(source_rows, list) or not source_rows:
    raise SystemExit("staging manifest has no source file inventory")
for row in sorted(source_rows, key=lambda item: item["path"]):
    relative = pathlib.PurePosixPath(row["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(f"unsafe source path in staging manifest: {relative}")
    content = (overlay / pathlib.Path(*relative.parts)).read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()
    if file_hash != row["sha256"].lower():
        raise SystemExit(f"staged solver source changed: {relative}")
    encoded = relative.as_posix().encode("utf-8")
    digest.update(len(encoded).to_bytes(4, byteorder="big"))
    digest.update(encoded)
    digest.update(bytes.fromhex(file_hash))
source_hash = digest.hexdigest()
if source_hash != expected_source:
    raise SystemExit(f"site solver source manifest hash mismatch: {source_hash}")
PY

printf 'cluster_run job=%s profile=%s ranks=%s case=%s\n' "$job_id" "$profile" "$ranks" "$case_dir"
step_pid=""
pre_timeout_requested=0

on_pre_timeout() {
    if [[ -z "$step_pid" ]]; then
        pre_timeout_requested=1
        return
    fi
    trap - USR1
    if ! kill -0 "$step_pid" 2>/dev/null; then
        echo "Slurm pre-timeout warning arrived after the MPI step exited" >&2
        return
    fi
    echo "Slurm pre-timeout warning: requesting native checkpoint and orderly stop" >&2
    # The site adapter must checkpoint all ranks before stopping them. This
    # example does not assume OpenFOAM signal behavior or a particular PMI.
    "$FIRETRACK2_CHECKPOINT_STOP_ADAPTER" \
        --job-id "$job_id" --step-pid "$step_pid" --case "$case_dir" || {
        echo "checkpoint-stop adapter failed; step remains live until its own exit or Slurm limit" >&2
    }
}
trap on_pre_timeout USR1

# This launch form is an example only. The requested --mpi plugin must be
# confirmed for the site's OpenFOAM build before any scientific case is run.
srun --mpi="$FIRETRACK2_SLURM_MPI_TYPE" --ntasks="$ranks" \
    "$FIRETRACK2_SOLVER_BIN" -case "$case_dir" -parallel &
step_pid=$!
if ((pre_timeout_requested)); then
    on_pre_timeout
fi
while true; do
    set +e
    wait "$step_pid"
    step_status=$?
    set -e
    if ! kill -0 "$step_pid" 2>/dev/null; then
        exit "$step_status"
    fi
done
