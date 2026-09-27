#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image_name="${FLUTAS_GPU_IMAGE:-track2/flutas-nvhpc:26.9}"
mkdir -p "$repo_root/results/runs"
run_dir="$(mktemp -d "$repo_root/results/runs/flutas-gpu-gate-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"

printf 'GPU verification evidence: %s\n' "$run_dir"
python3 "$repo_root/scripts/run_local.py" \
  --threads 2 \
  --gpu \
  --timeout 600 \
  -- bash -o pipefail -c \
  'docker run --rm --gpus all --cpus=2 --volume "$1:/evidence" "$2" /evidence 2>&1 | tee "$1/docker-run.log"' \
  _ "$run_dir" "$image_name"
