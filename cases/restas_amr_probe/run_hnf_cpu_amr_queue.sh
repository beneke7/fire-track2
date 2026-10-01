#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TAG="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="cases/restas_amr_probe/queue_logs/amr-cpu-${TAG}"
mkdir -p "$LOG_DIR"
STATUS_LOG="$LOG_DIR/status.log"
REFERENCE_80="results/runs/restas-hnf-realizableke-stage80ms-uniform-20260928T194033Z-288f65"
PREVIOUS_AMR_TAG="20260929T114711Z"

log_status() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$STATUS_LOG"
}

disk_guard() {
    local free_kib
    free_kib="$(df -Pk "$ROOT" | awk 'NR == 2 { print $4 }')"
    if (( free_kib < 41943040 )); then
        log_status "STOP: free disk ${free_kib} KiB is below the 40 GiB safety threshold"
        return 1
    fi
}

run_case() {
    local stage="$1" variant="$2" model="$3" ranks="$4"
    local finest="$5" levels="$6" timeout_s="$7"
    local docker_cpus="$ranks"
    if (( ranks == 18 )); then docker_cpus=20; fi
    local model_slug="${model//-/}"
    local run_id="restas-hnf-${model_slug}-${stage}-${variant}-${TAG}"
    local outer_timeout=$((timeout_s + 300))
    local log_file="$LOG_DIR/${stage}-${model_slug}-${variant}.log"
    local manifest="results/runs/${run_id}/manifest.json"
    disk_guard || return 90
    log_status "starting ${stage}/${model}/${variant}: ${ranks} MPI ranks, finest=${finest} m"
    if .venv/bin/python scripts/run_local.py \
        --threads "$ranks" --timeout "$outer_timeout" -- \
        .venv/bin/python cases/restas_amr_probe/run_hnf_mesh_case.py \
        --stage "$stage" --variant "$variant" --model "$model" \
        --finest-spacing "$finest" --max-levels "$levels" --max-cells 2000000 \
        --reference-run-dir "$REFERENCE_80" \
        --ranks "$ranks" --docker-cpus "$docker_cpus" --memory-gib 24 \
        --timeout-s "$timeout_s" --run-id "$run_id" \
        >"$log_file" 2>&1; then
        :
    else
        local rc=$?
        log_status "FAILED ${stage}/${model}/${variant}: launcher returned ${rc}; see ${log_file}"
        return "$rc"
    fi
    if ! .venv/bin/python - "$manifest" "$stage" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
stage = sys.argv[2]
if not manifest_path.is_file():
    raise SystemExit(f"missing completion manifest: {manifest_path}")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
last_time = manifest.get("solver_log_summary", {}).get("last_time_s")
expected = 0.1 if stage == "pulse100ms" else 0.08
if manifest.get("exit_code") != 0 or manifest.get("finished_utc") is None:
    raise SystemExit(f"run did not complete cleanly: exit={manifest.get('exit_code')}")
if last_time is None or last_time < expected - 1e-9:
    raise SystemExit(f"run stopped early: final={last_time}, expected={expected}")
PY
    then
        log_status "FAILED completion verification for ${run_id}; see ${log_file}"
        return 1
    fi
    log_status "verified completion: ${run_id}"
}

run_pair() {
    local stage="$1" model="$2" finest="$3" levels="$4" timeout_s="$5"
    local rank_count=10
    local rc_a=0 rc_b=0
    run_case "$stage" dynamic "$model" "$rank_count" "$finest" "$levels" "$timeout_s" &
    local pid_a=$!
    run_case "$stage" static "$model" "$rank_count" "$finest" "$levels" "$timeout_s" &
    local pid_b=$!
    wait "$pid_a" || rc_a=$?
    wait "$pid_b" || rc_b=$?
    log_status "pair ${stage}/${model} complete: dynamic_exit=${rc_a}, static_exit=${rc_b}"
    return $((rc_a != 0 || rc_b != 0))
}

run_model_pair() {
    local stage="$1" variant="$2" finest="$3" levels="$4" timeout_s="$5"
    local rank_count=10
    local rc_a=0 rc_b=0
    run_case "$stage" "$variant" realizable-ke "$rank_count" "$finest" "$levels" "$timeout_s" &
    local pid_a=$!
    run_case "$stage" "$variant" standard-ke "$rank_count" "$finest" "$levels" "$timeout_s" &
    local pid_b=$!
    wait "$pid_a" || rc_a=$?
    wait "$pid_b" || rc_b=$?
    log_status "model pair ${stage}/${variant} complete: realizable-ke_exit=${rc_a}, standard-ke_exit=${rc_b}"
    return $((rc_a != 0 || rc_b != 0))
}

analyze_runs() {
    local report="$1" stage="$2"
    shift 2
    log_status "analyzing matched fields into ${report}"
    .venv/bin/python cases/restas_amr_probe/analyze_hnf_mesh_comparison.py \
        --common-spacing-m 0.025 --run-dirs "$@" \
        >"$LOG_DIR/${report}.json" 2>"$LOG_DIR/${report}.err" \
        || log_status "analysis failed for ${stage}; solver evidence remains preserved"
}

log_status "CPU queue started; provisional input values are explicitly exploratory"
log_status "correction: prior 100 ms entries were setup failures (missing metadata key), not completed solver runs"

log_status "run matched 10-rank uniform RANS references for the completed 80 ms AMR pair"
run_model_pair stage80ms uniform 0.025 1 10800 \
    || log_status "80 ms uniform model pair had a failed member; continuing to pulse cases"
analyze_runs stage80ms-matched-comparison stage80ms \
    "results/runs/restas-hnf-realizableke-stage80ms-uniform-${TAG}" \
    "results/runs/restas-hnf-rke-stage80ms-dynamic-${PREVIOUS_AMR_TAG}" \
    "results/runs/restas-hnf-rke-stage80ms-static-${PREVIOUS_AMR_TAG}"

log_status "run post-source 100 ms RANS dynamic/static mesh pair"
run_pair pulse100ms realizable-ke 0.025 1 43200 \
    || log_status "100 ms RKE AMR pair had a failed member; continuing to uniform cases"

log_status "run matched 10-rank uniform realizable-ke and standard-ke 100 ms references"
run_model_pair pulse100ms uniform 0.025 1 43200 \
    || log_status "100 ms uniform model pair had a failed member; analyze any complete cases"
analyze_runs pulse100ms-comparison pulse100ms \
    "results/runs/restas-hnf-realizableke-pulse100ms-uniform-${TAG}" \
    "results/runs/restas-hnf-realizableke-pulse100ms-dynamic-${TAG}" \
    "results/runs/restas-hnf-realizableke-pulse100ms-static-${TAG}" \
    "results/runs/restas-hnf-standardke-pulse100ms-uniform-${TAG}"

log_status "CPU AMR queue complete"
