#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
base_image="track2/flutas-nvhpc:26.9"
expected_base_id="sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8"
candidate_image="track2/flutas-source-boundary:5982106-candidate2"
actual_base_id="$(docker image inspect --format '{{.Id}}' "$base_image")"

if [[ "$actual_base_id" != "$expected_base_id" ]]; then
  printf 'Expected base %s to resolve to %s, found %s\n' \
    "$base_image" "$expected_base_id" "$actual_base_id" >&2
  exit 2
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
evidence_dir="$script_dir/evidence/source-candidate-runs/$run_id"
mkdir -p "$evidence_dir"
metadata_file="$evidence_dir/metadata.txt"
printf 'started_utc=%s\nrun_id=%s\ncandidate_image=%s\nbase_image=%s\nbase_image_id=%s\nsource_commit=598210616bebd51f7d51f61455f196e6f3479916\ndocker_cpu_quota=200000/100000 (2 CPUs)\ngpu_runtime=not requested\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$run_id" "$candidate_image" "$base_image" "$actual_base_id" > "$metadata_file"
sha256sum "$script_dir/Dockerfile.source-candidate" "$script_dir/source-boundary.patch" \
  "$script_dir/cases/source_boundary/SHA256SUMS" >> "$metadata_file"
trap 'status=$?; printf "exit_status=%s\nfinished_utc=%s\n" "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$metadata_file"' EXIT

docker build \
  --pull=false \
  --cpu-period=100000 \
  --cpu-quota=200000 \
  --file "$script_dir/Dockerfile.source-candidate" \
  --build-arg "BASE_IMAGE=$base_image" \
  --tag "$candidate_image" \
  "$script_dir" 2>&1 | tee "$evidence_dir/docker-build.log"

candidate_id="$(docker image inspect --format '{{.Id}}' "$candidate_image")"
printf 'candidate_image_id=%s\n' "$candidate_id" | tee -a "$metadata_file"
