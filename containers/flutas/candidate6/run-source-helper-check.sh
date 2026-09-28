#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/../../.." && pwd)"
candidate_image="track2/flutas-candidate6-build:20260928T093141Z-4092509"
expected_image_id="sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b"
expected_patch_sha256="3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee"
case_root="$repo_dir/containers/flutas/candidate5/cases/source_boundary"
check_mode="${1:-source-helpers}"
case "$check_mode" in
  source-helpers)
    check_script="run_candidate6_source_helpers.sh"
    outer_threads=1
    cpu_quota=100000
    memory_limit=4g
    scope="dry and four-slot source-boundary host helper modes"
    ;;
  full-host-regressions)
    check_script="run_candidate6_host_regressions.sh"
    outer_threads=2
    cpu_quota=200000
    memory_limit=6g
    scope="full source-boundary helper and observability host regressions"
    ;;
  *)
    printf 'Unknown check mode: %s\n' "$check_mode" >&2
    exit 2
    ;;
esac
extra_docker_args=()
analyzer_mode=not-used
if [[ "$check_mode" == full-host-regressions ]]; then
  analyzer_mode=enabled
  extra_docker_args+=(
    --volume "$repo_dir/src:/opt/track2/src:ro"
    --volume "$repo_dir/tests:/opt/track2/tests:ro"
    --volume "$repo_dir/experiments:/opt/track2/experiments:ro"
    --env CANDIDATE5_ANALYZER_ROOT=/opt/track2
  )
fi

actual_image_id="$(docker image inspect --format '{{.Id}}' "$candidate_image")"
if [[ "$actual_image_id" != "$expected_image_id" ]]; then
  printf 'Expected candidate image ID %s, found %s\n' \
    "$expected_image_id" "$actual_image_id" >&2
  exit 2
fi
actual_patch_sha256="$(sha256sum "$script_dir/source-boundary.patch" | awk '{print $1}')"
if [[ "$actual_patch_sha256" != "$expected_patch_sha256" ]]; then
  printf 'Expected candidate6 patch SHA-256 %s, found %s\n' \
    "$expected_patch_sha256" "$actual_patch_sha256" >&2
  exit 2
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
evidence_root="$script_dir/evidence"
mkdir -p "$evidence_root"
evidence_dir="$evidence_root/source-helper-check-$run_id"
mkdir "$evidence_dir"
metadata_file="$evidence_dir/metadata.txt"
build_complete=false

{
  printf 'started_utc=%s\nrun_id=%s\ncandidate=candidate6\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$run_id"
  printf 'candidate_image=%s\ncandidate_image_id=%s\n' \
    "$candidate_image" "$actual_image_id"
  printf 'source_commit=598210616bebd51f7d51f61455f196e6f3479916\n'
  printf 'source_patch_sha256=%s\n' "$actual_patch_sha256"
  printf 'check_mode=%s\nscope=%s\n' "$check_mode" "$scope"
  printf 'outer_cpu_limit=%s via scripts/run_local.py\ndocker_cpu_limit=%s\n' \
    "$outer_threads" "$outer_threads"
  printf 'docker_memory_limit=%s\ndocker_network=none\n' "$memory_limit"
  printf 'gpu_runtime=not requested\nsolver_driver=not started\nphysical_time_advanced=no\n'
  printf 'independent_analyzer=%s\n' "$analyzer_mode"
  printf 'fixture_source=read-only candidate5 allowlisted cases\n'
  printf 'source_run_approval=not granted\nindependent_review=pending\n'
  printf 'workspace_revision=%s\n' "$(git -C "$repo_dir" rev-parse HEAD)"
} > "$metadata_file"

git -C "$repo_dir" status --short --untracked-files=all \
  > "$evidence_dir/workspace-status.txt"
printf 'workspace_status_sha256=%s\n' \
  "$(sha256sum "$evidence_dir/workspace-status.txt" | awk '{print $1}')" \
  >> "$metadata_file"

(
  cd "$case_root"
  sha256sum --check SHA256SUMS
) > "$evidence_dir/case-input-manifest-check.txt"

sha256sum \
  "$script_dir/run-source-helper-check.sh" \
  "$script_dir/tests/$check_script" \
  "$script_dir/source-boundary.patch" \
  "$script_dir/tests/test_candidate6_source_call_order.py" \
  "$repo_dir/src/aerial_drop/flutas_source_analyzer.py" \
  "$repo_dir/tests/test_flutas_source_analyzer.py" \
  "$repo_dir/experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md" \
  "$case_root/SHA256SUMS" \
  > "$evidence_dir/test-inputs.sha256"
(
  cd "$script_dir"
  find tests -maxdepth 1 -type f ! -name '*.pyc' -print0 \
    | sort -z | xargs -0 sha256sum
) >> "$evidence_dir/test-inputs.sha256"

finish() {
  status=$?
  if [[ "${build_complete:-false}" != true ]]; then
    printf 'exit_status=%s\nfinished_utc=%s\n' \
      "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$metadata_file"
    (
      cd "$evidence_dir"
      find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name SHA256SUMS.sha256 \
        -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
    )
    sha256sum "$evidence_dir/SHA256SUMS" > "$evidence_dir/SHA256SUMS.sha256"
  fi
}
trap finish EXIT

"$repo_dir/.venv/bin/python" "$repo_dir/scripts/run_local.py" \
  --threads "$outer_threads" --timeout 900 -- \
  docker run --rm \
    --network=none \
    --cpu-period=100000 \
    --cpu-quota="$cpu_quota" \
    --memory="$memory_limit" \
    --memory-swap="$memory_limit" \
    --volume "$script_dir/tests:/opt/flutas-source-protocol/tests:ro" \
    --volume "$case_root:/opt/flutas-source-protocol/cases/source_boundary:ro" \
    "${extra_docker_args[@]}" \
    --entrypoint /bin/bash \
    "$candidate_image" \
    -lc "/opt/flutas-source-protocol/tests/$check_script /opt/FluTAS /opt/flutas-source-protocol/cases/source_boundary" \
  > "$evidence_dir/$check_mode.log" 2>&1

"$repo_dir/.venv/bin/python" \
  "$script_dir/tests/test_candidate6_validator_lower_bounds.py" \
  > "$evidence_dir/lower-bound-call-audit.txt"

printf 'exit_status=0\nfinished_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$metadata_file"
build_complete=true
(
  cd "$evidence_dir"
  find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name SHA256SUMS.sha256 \
    -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)
sha256sum "$evidence_dir/SHA256SUMS" > "$evidence_dir/SHA256SUMS.sha256"
printf 'Evidence: %s\n' "$evidence_dir"
