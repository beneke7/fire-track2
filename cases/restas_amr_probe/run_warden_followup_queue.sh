#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

CURRENT_TAG="${CURRENT_TAG:-20260929T121040Z}"
REFERENCE_80="${REFERENCE_80:-results/runs/restas-hnf-realizableke-stage80ms-uniform-${CURRENT_TAG}}"
REFERENCE_100_RKE="${REFERENCE_100_RKE:-results/runs/restas-hnf-realizableke-pulse100ms-uniform-${CURRENT_TAG}}"
REFERENCE_100_STANDARD="${REFERENCE_100_STANDARD:-results/runs/restas-hnf-standardke-pulse100ms-uniform-${CURRENT_TAG}}"
STOP_AFTER="${STOP_AFTER:-all}"
case "$STOP_AFTER" in
    static-coverage|fine-amr|closure|all) ;;
    *) printf 'STOP_AFTER must be static-coverage, fine-amr, closure, or all\n' >&2; exit 2 ;;
esac
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="cases/restas_amr_probe/queue_logs/warden-followups-${TAG}"
STATUS_LOG="$LOG_DIR/status.log"
mkdir -p "$LOG_DIR"
exec 9>"cases/restas_amr_probe/queue_logs/.warden-followup-queue.lock"
if ! flock -n 9; then
    printf 'another Warden follow-up queue holds the lock; exiting\n'
    exit 0
fi

log_status() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$STATUS_LOG"
}

disk_guard() {
    local free_kib
    free_kib="$(df -Pk "$ROOT" | awk 'NR == 2 { print $4 }')"
    if (( free_kib < 41943040 )); then
        log_status "STOP: free disk ${free_kib} KiB is below the 40 GiB launch floor"
        return 1
    fi
}

verify_run() {
    local run_id="$1"
    local expected_time="$2"
    .venv/bin/python - "results/runs/${run_id}/manifest.json" "$expected_time" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
expected = float(sys.argv[2])
if not manifest_path.is_file():
    raise SystemExit(f"missing completion manifest: {manifest_path}")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
last_time = manifest.get("solver_log_summary", {}).get("last_time_s")
if manifest.get("exit_code") != 0 or not manifest.get("finished_utc"):
    raise SystemExit(f"run did not complete cleanly: exit={manifest.get('exit_code')}")
if last_time is None or last_time < expected - 1e-9:
    raise SystemExit(f"run stopped early: final={last_time}, expected={expected}")
PY
}

run_case() {
    local label="$1" run_id="$2" variant="$3" model="$4"
    local spacing="$5" levels="$6" ranks="$7" memory="$8" timeout_s="$9"
    shift 9
    local docker_cpus="$ranks"
    if (( ranks == 18 )); then docker_cpus=20; fi
    disk_guard || return 90
    log_status "starting ${label}: ${model}/${variant}, spacing=${spacing} m, ranks=${ranks}"
    .venv/bin/python scripts/run_local.py \
        --threads "$ranks" --timeout "$((timeout_s + 300))" -- \
        .venv/bin/python cases/restas_amr_probe/run_hnf_mesh_case.py \
        --stage pulse100ms --variant "$variant" --model "$model" \
        --finest-spacing "$spacing" --max-levels "$levels" --max-cells 2000000 \
        --reference-run-dir "$REFERENCE_80" --ranks "$ranks" \
        --docker-cpus "$docker_cpus" --memory-gib "$memory" \
        --timeout-s "$timeout_s" --run-id "$run_id" "$@"
    verify_run "$run_id" 0.1 || {
        log_status "FAILED completion verification for ${run_id}"
        return 1
    }
    log_status "verified completion: ${run_id}"
}

run_pair() {
    local group="$1"
    shift
    local -a args_a=() args_b=()
    while (($#)) && [[ "$1" != "--" ]]; do
        args_a+=("$1")
        shift
    done
    if (($# == 0)); then
        log_status "FAILED pair ${group}: missing argument separator"
        return 1
    fi
    shift
    args_b=("$@")
    local rc_a=0 rc_b=0
    run_case "${group}-a" "${args_a[0]}" "${args_a[1]}" "${args_a[2]}" \
        "${args_a[3]}" "${args_a[4]}" 10 32 43200 "${args_a[@]:5}" \
        >"$LOG_DIR/${group}-a.log" 2>&1 &
    local pid_a=$!
    run_case "${group}-b" "${args_b[0]}" "${args_b[1]}" "${args_b[2]}" \
        "${args_b[3]}" "${args_b[4]}" 10 32 43200 "${args_b[@]:5}" \
        >"$LOG_DIR/${group}-b.log" 2>&1 &
    local pid_b=$!
    wait "$pid_a" || rc_a=$?
    wait "$pid_b" || rc_b=$?
    log_status "pair ${group} finished: exits=${rc_a},${rc_b}"
    (( rc_a == 0 && rc_b == 0 ))
}

analyze() {
    local label="$1" spacing="$2"
    shift 2
    log_status "analyzing ${label} at common spacing ${spacing} m"
    if .venv/bin/python scripts/run_local.py --threads 1 -- \
        .venv/bin/python cases/restas_amr_probe/analyze_hnf_mesh_comparison.py \
        --common-spacing-m "$spacing" --thresholds 0.001 0.1 0.5 0.65 0.9 --run-dirs "$@" \
        >"$LOG_DIR/${label}.json" 2>"$LOG_DIR/${label}.err"; then
        log_status "analysis completed: ${label}"
    else
        local analysis_exit=$?
        log_status "analysis ${label} failed with exit ${analysis_exit}; evidence saved, independent runs continue"
    fi
}

log_status "follow-up queue scheduled; waiting for the active 20260929T121040Z CPU queue"
while pgrep -f '^bash cases/restas_amr_probe/run_hnf_cpu_amr_queue.sh$' >/dev/null; do
    disk_guard || exit 90
    sleep 30
done
while pgrep -x interIsoFoam >/dev/null; do
    log_status "waiting for remaining interIsoFoam workers to exit"
    sleep 30
done

log_status "validating the matched 80/100 ms source queue before follow-ups"
.venv/bin/python - "$CURRENT_TAG" "$REFERENCE_100_RKE" "$REFERENCE_100_STANDARD" <<'PY'
import json
import sys
from pathlib import Path

tag = sys.argv[1]
checks = [
    (f"restas-hnf-realizableke-stage80ms-uniform-{tag}", 0.08),
    (f"restas-hnf-standardke-stage80ms-uniform-{tag}", 0.08),
    (f"restas-hnf-realizableke-pulse100ms-dynamic-{tag}", 0.1),
    (f"restas-hnf-realizableke-pulse100ms-static-{tag}", 0.1),
]
checks = [(Path("results/runs") / run_id, expected) for run_id, expected in checks]
checks.extend([(Path(sys.argv[2]), 0.1), (Path(sys.argv[3]), 0.1)])
for run_dir, expected in checks:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    last_time = manifest.get("solver_log_summary", {}).get("last_time_s")
    if manifest.get("exit_code") != 0 or not manifest.get("finished_utc"):
        raise SystemExit(f"base queue run incomplete: {run_dir.name}")
    if last_time is None or last_time < expected - 1e-9:
        raise SystemExit(f"base queue run stopped early: {run_dir.name}: {last_time}")
print("all six base cases reached their declared horizons")
PY

log_status "sweep static plume coverage to 2.0 and 2.4 m against completed 100 ms dynamic AMR"
run_pair static-coverage \
    "restas-hnf-rke-pulse100-static-x2000mm-${TAG}" static realizable-ke 0.025 1 --static-x-end-m 2.0 -- \
    "restas-hnf-rke-pulse100-static-x2400mm-${TAG}" static realizable-ke 0.025 1 --static-x-end-m 2.4
analyze static-coverage-comparison 0.025 \
    "results/runs/restas-hnf-realizableke-pulse100ms-dynamic-${CURRENT_TAG}" \
    "results/runs/restas-hnf-rke-pulse100-static-x2000mm-${TAG}" \
    "results/runs/restas-hnf-rke-pulse100-static-x2400mm-${TAG}"
if [[ "$STOP_AFTER" == "static-coverage" ]]; then
    log_status "selected static-coverage campaign complete"
    exit 0
fi

log_status "compare 12.5 mm dynamic AMR with a 12.5 mm static swept region"
run_pair fine-amr \
    "restas-hnf-rke-pulse100-dynamic-12p5mm-${TAG}" dynamic realizable-ke 0.0125 2 --static-x-end-m 2.0 -- \
    "restas-hnf-rke-pulse100-static-12p5mm-x2000mm-${TAG}" static realizable-ke 0.0125 2 --static-x-end-m 2.0
analyze fine-amr-comparison 0.0125 \
    "results/runs/restas-hnf-rke-pulse100-dynamic-12p5mm-${TAG}" \
    "results/runs/restas-hnf-rke-pulse100-static-12p5mm-x2000mm-${TAG}"
if [[ "$STOP_AFTER" == "fine-amr" ]]; then
    log_status "selected mesh campaign complete"
    exit 0
fi

log_status "extend turbulence-closure comparison through the post-pulse window with SST"
run_case sst-uniform \
    "restas-hnf-sst-pulse100-uniform-${TAG}" uniform k-omega-sst \
    0.025 1 20 48 43200 \
    >"$LOG_DIR/sst-uniform.log" 2>&1
analyze pulse100-closure-comparison 0.025 \
    "$REFERENCE_100_RKE" \
    "$REFERENCE_100_STANDARD" \
    "results/runs/restas-hnf-sst-pulse100-uniform-${TAG}"
if [[ "$STOP_AFTER" == "closure" ]]; then
    log_status "selected mesh and turbulence campaign complete"
    exit 0
fi

log_status "isolate provisional RANS inlet-turbulence intensity and length-scale effects at 100 ms"
run_pair intensity-sensitivity \
    "restas-hnf-rke-pulse100-intensity025-${TAG}" uniform realizable-ke 0.025 1 --turbulence-intensity 0.025 -- \
    "restas-hnf-rke-pulse100-intensity10-${TAG}" uniform realizable-ke 0.025 1 --turbulence-intensity 0.10
analyze intensity-sensitivity-comparison 0.025 \
    "$REFERENCE_100_RKE" \
    "results/runs/restas-hnf-rke-pulse100-intensity025-${TAG}" \
    "results/runs/restas-hnf-rke-pulse100-intensity10-${TAG}"

run_pair water-length-sensitivity \
    "restas-hnf-rke-pulse100-waterL075-${TAG}" uniform realizable-ke 0.025 1 --source-length-scale-m 0.075 -- \
    "restas-hnf-rke-pulse100-waterL300-${TAG}" uniform realizable-ke 0.025 1 --source-length-scale-m 0.30
analyze water-length-sensitivity-comparison 0.025 \
    "$REFERENCE_100_RKE" \
    "results/runs/restas-hnf-rke-pulse100-waterL075-${TAG}" \
    "results/runs/restas-hnf-rke-pulse100-waterL300-${TAG}"

run_pair air-length-sensitivity \
    "restas-hnf-rke-pulse100-airL025-${TAG}" uniform realizable-ke 0.025 1 --air-length-scale-m 0.025 -- \
    "restas-hnf-rke-pulse100-airL100-${TAG}" uniform realizable-ke 0.025 1 --air-length-scale-m 0.10
analyze air-length-sensitivity-comparison 0.025 \
    "$REFERENCE_100_RKE" \
    "results/runs/restas-hnf-rke-pulse100-airL025-${TAG}" \
    "results/runs/restas-hnf-rke-pulse100-airL100-${TAG}"

log_status "Warden-directed CPU follow-up queue complete"
