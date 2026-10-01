#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MAIN_DIR="results/runs/restas-hnf-rke12p5-stage80ms-main-20260928T195048Z"
SST_DIR="results/runs/restas-hnf-sst25-stage80-retry-20260929"
REFERENCE_DIR="results/runs/restas-hnf-realizableke-stage80ms-uniform-20260928T194033Z-288f65"
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="cases/restas_amr_probe/queue_logs/turbulence-factorial-${TAG}"
mkdir -p "$LOG_DIR"
STATUS_LOG="$LOG_DIR/status.log"

log_status() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$STATUS_LOG"
}

disk_guard() {
    local free_kib
    free_kib="$(df -Pk "$ROOT" | awk 'NR == 2 { print $4 }')"
    if (( free_kib < 83886080 )); then
        log_status "STOP: free disk ${free_kib} KiB is below the 80 GiB floor"
        return 1
    fi
}

log_status "waiting for the 12.5mm RKE continuation to reach 80ms"
while [[ ! -f "$MAIN_DIR/continuation-exit-code.txt" ]]; do
    disk_guard || exit 90
    sleep 30
done
if [[ "$(cat "$MAIN_DIR/continuation-exit-code.txt")" != 0 ]] || ! .venv/bin/python - "$MAIN_DIR/continuation-console.log" <<'PY'
import re
import sys
from pathlib import Path

times = [
    float(value)
    for value in re.findall(r"^Time =\s*([0-9.eE+-]+)", Path(sys.argv[1]).read_text(), re.M)
]
if not times or max(times) < 0.08:
    raise SystemExit(1)
PY
then
    log_status "STOP: main continuation did not complete through 80ms"
    exit 1
fi

log_status "main reached 80ms; starting isolated inlet-turbulence sensitivities"

run_case() {
    local label="$1"
    local run_id="$2"
    local ranks="$3"
    shift 3
    local log_file="$LOG_DIR/${label}.log"
    disk_guard || return 90
    .venv/bin/python scripts/run_local.py \
        --threads "$ranks" --timeout 11100 -- \
        .venv/bin/python cases/restas_amr_probe/run_hnf_mesh_case.py \
        --stage stage80ms --variant uniform --model realizable-ke \
        --finest-spacing 0.025 --reference-run-dir "$REFERENCE_DIR" \
        --ranks "$ranks" --docker-cpus "$ranks" --memory-gib 16 \
        --timeout-s 10800 --run-id "$run_id" "$@" >"$log_file" 2>&1 || return $?
    .venv/bin/python cases/restas_amr_probe/analyze_hnf_mesh_comparison.py \
        --run-dirs "results/runs/$run_id" --common-spacing-m 0.025 \
        >>"$log_file" 2>&1
}

run_pair() {
    local label_a="$1" id_a="$2" arg_a="$3" value_a="$4"
    local label_b="$5" id_b="$6" arg_b="$7" value_b="$8"
    local ranks=10
    if [[ ! -f "$SST_DIR/manifest.json" ]] || ! .venv/bin/python - "$SST_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path
try:
    manifest = json.loads(Path(sys.argv[1]).read_text())
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if manifest.get("finished_utc") else 1)
PY
    then
        ranks=9
    fi
    log_status "starting pair $label_a / $label_b at $ranks ranks each"
    run_case "$label_a" "restas-hnf-${id_a}-${TAG}" "$ranks" "$arg_a" "$value_a" >"$LOG_DIR/${label_a}.log" 2>&1 &
    local pid_a=$!
    run_case "$label_b" "restas-hnf-${id_b}-${TAG}" "$ranks" "$arg_b" "$value_b" >"$LOG_DIR/${label_b}.log" 2>&1 &
    local pid_b=$!
    local rc=0
    wait "$pid_a" || rc=$?
    wait "$pid_b" || rc=$?
    log_status "finished pair $label_a / $label_b exit=$rc"
}

# Isolate the input uncertainties that were combined in the earlier low/high
# corners: phase inlet intensity, liquid-source scale, and air scale.
run_pair "intensity-low" "rke-intensity025-stage80" \
    --turbulence-intensity 0.025 "intensity-high" "rke-intensity10-stage80" \
    --turbulence-intensity 0.10
run_pair "water-scale-half" "rke-waterL075-stage80" \
    --source-length-scale-m 0.075 "water-scale-double" "rke-waterL300-stage80" \
    --source-length-scale-m 0.30
run_pair "air-scale-half" "rke-airL025-stage80" \
    --air-length-scale-m 0.025 "air-scale-double" "rke-airL100-stage80" \
    --air-length-scale-m 0.10

log_status "turbulence factorial queue complete"
