#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/../../.." && pwd)"
base_image="track2/flutas-nvhpc:26.9"
expected_base_id="sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8"
expected_source_commit="598210616bebd51f7d51f61455f196e6f3479916"
expected_patch_sha256="3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee"

actual_base_id="$(docker image inspect --format '{{.Id}}' "$base_image")"
if [[ "$actual_base_id" != "$expected_base_id" ]]; then
  printf 'Expected base %s to resolve to %s, found %s\n' \
    "$base_image" "$expected_base_id" "$actual_base_id" >&2
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
evidence_dir="$evidence_root/full-source-build-$run_id"
mkdir "$evidence_dir"
candidate_image="track2/flutas-candidate6-build:$run_id"
metadata_file="$evidence_dir/metadata.txt"

{
  printf 'started_utc=%s\nrun_id=%s\ncandidate=candidate6\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$run_id"
  printf 'candidate_image=%s\nbase_image=%s\nbase_image_id=%s\n' \
    "$candidate_image" "$base_image" "$actual_base_id"
  printf 'source_commit=%s\nsource_patch_sha256=%s\n' \
    "$expected_source_commit" "$actual_patch_sha256"
  printf 'outer_cpu_limit=2 via scripts/run_local.py\ndocker_cpu_limit=2\ndocker_memory_limit=6 GiB\ndocker_network=none\n'
  printf 'gpu_runtime=not requested\nsolver_case=not run\nsource_CFD=not run\n'
  printf 'purpose=CPU native build and sm_120 code-object inspection only\n'
  printf 'source_run_approval=not granted\nindependent_review=pending\n'
  printf 'workspace_revision=%s\n' "$(git -C "$repo_dir" rev-parse HEAD)"
} > "$metadata_file"

git -C "$repo_dir" status --short --untracked-files=all \
  > "$evidence_dir/workspace-status.txt"
printf 'workspace_status_sha256=%s\n' \
  "$(sha256sum "$evidence_dir/workspace-status.txt" | awk '{print $1}')" \
  >> "$metadata_file"

sha256sum \
  "$script_dir/Dockerfile.build" \
  "$script_dir/Dockerfile.build.dockerignore" \
  "$script_dir/build-candidate6.sh" \
  "$script_dir/source-boundary.patch" \
  "$script_dir/source-pin.txt" \
  > "$evidence_dir/build-inputs.sha256"

docker run --rm --network=none --entrypoint /bin/bash "$base_image" \
  -lc 'git -C /opt/FluTAS rev-parse HEAD; sha256sum /opt/FluTAS/src/targets/target.generic-gpu; nvfortran --version; cuobjdump --version' \
  > "$evidence_dir/base-toolchain.txt" 2>&1
grep -F "$expected_source_commit" "$evidence_dir/base-toolchain.txt" >/dev/null
grep -F 'd694b6db322a2f9391ef09bb697bade0cb32ec3ab3f11bd6dfe9dba814a43759' \
  "$evidence_dir/base-toolchain.txt" >/dev/null

printf 'docker build --pull=false --network=none --cpu-period=100000 --cpu-quota=200000 --memory=6g --memory-swap=6g --file %s --build-arg BASE_IMAGE=%s --build-arg FLUTAS_COMMIT=%s --tag %s %s\n' \
  "$script_dir/Dockerfile.build" "$base_image" "$expected_source_commit" \
  "$candidate_image" "$script_dir" > "$evidence_dir/build-command.txt"

finish() {
  status=$?
  if [[ "${build_complete:-false}" != true ]]; then
    printf 'exit_status=%s\nfinished_utc=%s\n' \
      "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$metadata_file"
  fi
}
trap finish EXIT

"$repo_dir/.venv/bin/python" "$repo_dir/scripts/run_local.py" \
  --threads 2 --timeout 1800 -- \
  docker build \
    --pull=false \
    --network=none \
    --cpu-period=100000 \
    --cpu-quota=200000 \
    --memory=6g \
    --memory-swap=6g \
    --file "$script_dir/Dockerfile.build" \
    --build-arg "BASE_IMAGE=$base_image" \
    --build-arg "FLUTAS_COMMIT=$expected_source_commit" \
    --tag "$candidate_image" \
    "$script_dir" \
  > "$evidence_dir/docker-build.log" 2>&1

candidate_image_id="$(docker image inspect --format '{{.Id}}' "$candidate_image")"
printf 'candidate_image_id=%s\n' "$candidate_image_id" | tee -a "$metadata_file"
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{json .Config.Entrypoint}}' \
  "$candidate_image" > "$evidence_dir/candidate-image-identity.txt"

docker run --rm --network=none --entrypoint /bin/bash "$candidate_image" \
  -lc 'cuobjdump --list-elf /opt/FluTAS/src/flutas.two_phase_inc_isot; sha256sum /opt/FluTAS/src/flutas.two_phase_inc_isot; nvfortran --version' \
  > "$evidence_dir/code-object-and-compiler.txt" 2>&1
grep -F 'sm_120.cubin' "$evidence_dir/code-object-and-compiler.txt" >/dev/null

container_id="$(docker create --entrypoint /bin/true "$candidate_image")"
docker cp "$container_id:/opt/FluTAS/src/flutas.two_phase_inc_isot" \
  "$evidence_dir/flutas.two_phase_inc_isot"
docker rm "$container_id" >/dev/null
executable_sha256="$(sha256sum "$evidence_dir/flutas.two_phase_inc_isot" | awk '{print $1}')"
printf 'executable_sha256=%s\nsolver_run_manifest=not generated\n' \
  "$executable_sha256" | tee -a "$metadata_file"

printf 'exit_status=0\nfinished_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$metadata_file"
build_complete=true
(
  cd "$evidence_dir"
  find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)
sha256sum "$evidence_dir/SHA256SUMS" > "$evidence_dir/SHA256SUMS.sha256"
printf 'Evidence: %s\n' "$evidence_dir"
