#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/../../.." && pwd)"
base_image="track2/flutas-nvhpc:26.9"
expected_base_id="sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8"
actual_base_id="$(docker image inspect --format '{{.Id}}' "$base_image")"
if [[ "$actual_base_id" != "$expected_base_id" ]]; then
  printf 'Expected base %s to resolve to %s, found %s\n' \
    "$base_image" "$expected_base_id" "$actual_base_id" >&2
  exit 2
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
evidence_dir="$script_dir/evidence/runs/$run_id"
mkdir -p "$evidence_dir"
candidate_image="track2/flutas-source-boundary:5982106-candidate5-$run_id"
metadata_file="$evidence_dir/metadata.txt"
status_file="$evidence_dir/workspace-status.txt"
input_status_file="$evidence_dir/build-input-status.txt"
command_file="$evidence_dir/build-command.txt"

{
  printf 'started_utc=%s\nrun_id=%s\ncandidate=candidate5\ncandidate_image=%s\nbase_image=%s\nbase_image_id=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$run_id" "$candidate_image" "$base_image" "$actual_base_id"
  printf 'source_commit=598210616bebd51f7d51f61455f196e6f3479916\n'
  printf 'producer_schema=candidate5-observability-v1.2\n'
  printf 'producer_schema_sha256=%s\n' "$(sha256sum "$repo_dir/experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md" | awk '{print $1}')"
  printf 'candidate_source_patch_sha256=%s\n' "$(sha256sum "$script_dir/source-boundary.patch" | awk '{print $1}')"
  printf 'candidate_evidence_excluded_from_build_hashes=true\n'
  printf 'docker_build_cpu_quota=200000/100000 (2 CPUs)\ndocker_build_memory_limit=6 GiB\n'
  printf 'docker_build_gpu_devices=none\ngpu_runtime=not requested\nsolver_case=not run\n'
  printf 'source_run_approval=not granted\nindependent_review=pending\n'
  printf 'host_online_cpus=%s\n' "$(getconf _NPROCESSORS_ONLN)"
  printf 'host_allowed_cpus=%s\n' "$(awk '/Cpus_allowed_list/ {print $2}' /proc/self/status)"
  printf 'host_mem_available_kib=%s\n' "$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
} > "$metadata_file"

(
  cd "$repo_dir"
  git rev-parse HEAD > "$evidence_dir/revision.txt"
  git status --short --untracked-files=all > "$status_file"
  grep -vF 'containers/flutas/candidate3/evidence/' "$status_file" \
    | grep -vF 'containers/flutas/candidate4/evidence/' \
    | grep -vF 'containers/flutas/candidate5/evidence/' > "$input_status_file"
  sha256sum "$input_status_file" > "$evidence_dir/build-input-status.sha256"
)
{
  printf '\n[build input hashes]\n'
  (cd "$script_dir" && sha256sum .dockerignore Dockerfile build.sh source-boundary.patch source-pin.txt SOURCE_BOUNDARY.md INDEPENDENT_REVIEW.md cases/source_boundary/SHA256SUMS)
  (cd "$script_dir" && find tests -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum)
  (cd "$script_dir" && find tools -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum)
} >> "$metadata_file"
(
  cd "$script_dir/cases/source_boundary"
  sha256sum --check SHA256SUMS
) > "$evidence_dir/input-manifest-check.txt"
printf 'input_manifest=PASS\n' >> "$metadata_file"
printf 'docker build --pull=false --network=none --memory=6g --cpu-period=100000 --cpu-quota=200000 --file %s --build-arg BASE_IMAGE=%s --build-arg FLUTAS_COMMIT=%s --tag %s %s\n' \
  "$script_dir/Dockerfile" "$base_image" \
  '598210616bebd51f7d51f61455f196e6f3479916' \
  "$candidate_image" "$script_dir" > "$command_file"

finish() {
  status=$?
  printf 'exit_status=%s\nfinished_utc=%s\n' \
    "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$metadata_file"
  if [[ "$status" -eq 0 ]]; then
    candidate_id="$(docker image inspect --format '{{.Id}}' "$candidate_image")"
    printf 'candidate_image_id=%s\n' "$candidate_id" | tee -a "$metadata_file"
    printf 'candidate_repo_digests=%s\n' \
      "$(docker image inspect --format '{{json .RepoDigests}}' "$candidate_image")" \
      | tee -a "$metadata_file"
    printf 'oci_manifest_digest_available=%s\n' \
      "$(docker image inspect --format '{{if .RepoDigests}}yes{{else}}no{{end}}' "$candidate_image")" \
      | tee -a "$metadata_file"
    candidate_container="$(docker create --entrypoint /bin/true "$candidate_image")"
    docker cp "$candidate_container:/opt/FluTAS/src/flutas.two_phase_inc_isot" \
      "$evidence_dir/flutas.two_phase_inc_isot"
    docker rm "$candidate_container" >/dev/null
    printf 'candidate_executable_sha256=%s\n' \
      "$(sha256sum "$evidence_dir/flutas.two_phase_inc_isot" | awk '{print $1}')" \
      | tee -a "$metadata_file"
    printf 'solver_run_manifest=not generated\nsolver_run=not launched\ngpu=not used\n' \
      >> "$metadata_file"
  fi
}
trap finish EXIT

docker build \
  --pull=false \
  --network=none \
  --memory=6g \
  --cpu-period=100000 \
  --cpu-quota=200000 \
  --file "$script_dir/Dockerfile" \
  --build-arg "BASE_IMAGE=$base_image" \
  --build-arg "FLUTAS_COMMIT=598210616bebd51f7d51f61455f196e6f3479916" \
  --tag "$candidate_image" \
  "$script_dir" 2>&1 | tee "$evidence_dir/docker-build.log"
