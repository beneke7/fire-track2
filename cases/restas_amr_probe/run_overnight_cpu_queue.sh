#!/usr/bin/env bash
set -euo pipefail

# Persistent, gated CPU queue for the corrected horizontal near-field study.
# The gate and matched RKE 25 mm run are already launched separately by the
# coordinator; this script waits for their immutable run bundles before moving
# on. All generated CFD results remain unique under results/runs/.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GATE_RUN_DIR="results/runs/restas-hnf-standardke-stage1_25mm-uniform-20260928T194015Z-9390a0"
RKE25_BASELINE_DIR="results/runs/restas-hnf-realizableke-stage80ms-uniform-20260928T194033Z-288f65"
RKE25_REFERENCE_DIR="$RKE25_BASELINE_DIR"
RKE12P5_REFERENCE_DIR="results/runs/restas-hnf-realizableke-stage2_12p5mm-uniform-20260928T180054Z-c46dc4"
QUEUE_TAG="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="cases/restas_amr_probe/queue_logs/hnf-amr-${QUEUE_TAG}"
STATUS_LOG="$LOG_DIR/status.log"
mkdir -p "$LOG_DIR"
exec 9>"cases/restas_amr_probe/queue_logs/.overnight-queue.lock"
if ! flock -n 9; then
    printf '%s another overnight queue already holds the lock; exiting\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
fi

log_status() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$STATUS_LOG"
}

disk_free_kib() {
    df -Pk "$ROOT" | awk 'NR == 2 { print $4 }'
}

disk_guard() {
    local free_kib
    free_kib="$(disk_free_kib)"
    if (( free_kib < 83886080 )); then
        log_status "STOP: free disk ${free_kib} KiB is below the 80 GiB floor"
        return 1
    fi
}

manifest_finished() {
    .venv/bin/python - "$1/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

try:
    manifest = json.loads(Path(sys.argv[1]).read_text())
except (OSError, json.JSONDecodeError):
    print("no")
else:
    print("yes" if manifest.get("finished_utc") else "no")
PY
}

wait_for_run() {
    local label="$1"
    local run_dir="$2"
    if [[ ! -d "$run_dir" ]]; then
        log_status "STOP: expected $label bundle is missing: $run_dir"
        return 1
    fi
    while [[ "$(manifest_finished "$run_dir")" != "yes" ]]; do
        disk_guard || return 1
        log_status "waiting for $label to finish"
        sleep 30
    done
}

run_case() {
    local label="$1"
    local run_id="$2"
    local model="$3"
    local spacing="$4"
    local ranks="$5"
    local cpus="$6"
    local memory="$7"
    local timeout_s="$8"
    local reference="$9"
    shift 9
    local log_file="$LOG_DIR/${label}.log"
    local container_name="${run_id:0:63}"

    disk_guard || return 90
    log_status "start $label: model=$model spacing=${spacing}m ranks=$ranks cpus=$cpus memory=${memory}GiB timeout=${timeout_s}s"
    .venv/bin/python scripts/run_local.py \
        --threads "$ranks" \
        --timeout "$((timeout_s + 300))" \
        -- .venv/bin/python cases/restas_amr_probe/run_hnf_mesh_case.py \
        --stage stage80ms \
        --variant uniform \
        --model "$model" \
        --finest-spacing "$spacing" \
        --reference-run-dir "$reference" \
        --ranks "$ranks" \
        --docker-cpus "$cpus" \
        --memory-gib "$memory" \
        --timeout-s "$timeout_s" \
        --run-id "$run_id" \
        "$@" >"$log_file" 2>&1 &
    local job_pid=$!
    local exit_code=0
    local disk_stopped=0
    while kill -0 "$job_pid" 2>/dev/null; do
        if ! disk_guard; then
            log_status "disk guard stopping $label container $container_name"
            docker stop "$container_name" >/dev/null 2>&1 || true
            disk_stopped=1
            break
        fi
        sleep 30
    done
    local wait_code=0
    if wait "$job_pid"; then
        wait_code=0
    else
        wait_code=$?
    fi
    if (( disk_stopped )); then
        exit_code=90
    else
        exit_code="$wait_code"
    fi
    if (( exit_code == 0 )); then
        if ! .venv/bin/python cases/restas_amr_probe/analyze_hnf_mesh_comparison.py \
            --run-dirs "results/runs/$run_id" --common-spacing-m "$spacing" >>"$log_file" 2>&1; then
            exit_code=91
            log_status "analysis failed after solver completion: $label"
        fi
    fi
    log_status "finish $label exit_code=$exit_code run_id=$run_id"
    return "$exit_code"
}

log_status "queue started; gate=$GATE_RUN_DIR matched_rke25=$RKE25_BASELINE_DIR"
wait_for_run "standard-k-epsilon 25mm 20ms gate" "$GATE_RUN_DIR"
if ! .venv/bin/python cases/restas_amr_probe/analyze_hnf_mesh_comparison.py \
    --run-dirs "$GATE_RUN_DIR" --common-spacing-m 0.025 >"$LOG_DIR/gate-analysis.log" 2>&1; then
    log_status "STOP: standard-k-epsilon gate analysis failed"
    exit 1
fi
if ! .venv/bin/python - "$GATE_RUN_DIR" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
manifest = json.loads((run_dir / "manifest.json").read_text())
report = json.loads((run_dir / "common-grid-report.json").read_text())
assert manifest.get("exit_code") == 0, f"solver exit {manifest.get('exit_code')}"
assert manifest.get("solver_log_summary", {}).get("last_time_s", 0) >= 0.02, "did not reach 20ms"
assert all(record.get("exit_code") == 0 for record in manifest.get("stage_exit_records", []))
ledger = report["water_ledger"]
expected = ledger.get("analytic_expected_source_mass_kg") or 0
residual = ledger.get("closure_residual_kg")
assert expected > 0 and residual is not None, "source/outflow/inventory ledger is incomplete"
assert abs(residual) / expected <= 1e-3, f"mass residual {residual} kg exceeds 0.1%"
print(json.dumps({"last_time_s": manifest["solver_log_summary"]["last_time_s"], "mass_residual_kg": residual, "relative_mass_residual": abs(residual) / expected}))
PY
then
    log_status "STOP: standard-k-epsilon gate failed solver, horizon, or 0.1% mass closure check"
    exit 1
fi
log_status "standard-k-epsilon 25mm20ms gate passed; launching 12.5mm RKE80ms main"

MAIN_RC_FILE="$LOG_DIR/main.exit"
run_main() {
    local rc=0
    if run_case \
        "main-rke-12p5mm-80ms" \
        "restas-hnf-rke12p5-stage80ms-main-${QUEUE_TAG}" \
        "realizable-ke" 0.0125 18 20 96 28800 "$RKE12P5_REFERENCE_DIR"; then
        rc=0
    else
        rc=$?
    fi
    printf '%s\n' "$rc" >"$MAIN_RC_FILE"
    return "$rc"
}
run_main &
MAIN_PID=$!

# The already-running 2-rank matched RKE case has first claim on the two cores
# left by the 18-rank main. Start the remaining sensitivity series only after
# that exact baseline bundle completes.
wait_for_run "matched realizable-k-epsilon 25mm 80ms baseline" "$RKE25_BASELINE_DIR"

SENSITIVITY_CASES=(
    "standard-k-epsilon-25mm80|standardke25-stage80|standard-ke||"
    "k-omega-SST-25mm80|sst25-stage80|k-omega-sst||"
    "RKE-surface-tension-zero-25mm80|rke-sigma0-stage80|realizable-ke|sigma0|"
    "RKE-low-turbulence-corner-25mm80|rke-lowI-shortL-stage80|realizable-ke|low|"
    "RKE-high-turbulence-corner-25mm80|rke-highI-longL-stage80|realizable-ke|high|"
)
for item in "${SENSITIVITY_CASES[@]}"; do
    IFS='|' read -r label id model sensitivity _ <<<"$item"
    ranks=18
    cpus=20
    memory=96
    timeout_s=7200
    if [[ ! -f "$MAIN_RC_FILE" ]]; then
        ranks=2
        cpus=2
        memory=16
        timeout_s=10800
    fi
    run_id="restas-hnf-${id}-${QUEUE_TAG}"
    extras=()
    case "$sensitivity" in
        sigma0) extras+=(--surface-tension-n-m 0.0) ;;
        low)
            extras+=(--turbulence-intensity 0.025 --source-length-scale-m 0.075 --air-length-scale-m 0.025)
            ;;
        high)
            extras+=(--turbulence-intensity 0.10 --source-length-scale-m 0.30 --air-length-scale-m 0.10)
            ;;
    esac
    if run_case "$label" "$run_id" "$model" 0.025 "$ranks" "$cpus" "$memory" "$timeout_s" "$RKE25_REFERENCE_DIR" "${extras[@]}"; then
        :
    else
        log_status "case failed but queue continues: $label"
    fi
done

if wait "$MAIN_PID"; then
    main_exit=0
else
    main_exit=$?
fi
log_status "queue complete main_exit=$main_exit"
exit "$main_exit"
