#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image_name="${FLUTAS_GPU_IMAGE:-track2/flutas-nvhpc:26.9}"

docker build \
  --pull=false \
  --cpu-period=100000 \
  --cpu-quota=200000 \
  --file "$script_dir/Dockerfile" \
  --tag "$image_name" \
  "$script_dir"
