#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 IMAGE_REF EXPECTED_IMAGE_ID EXPECTED_CANDIDATE_PATCH_SHA256" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image_ref="$1"
expected_image_id="$2"
expected_candidate_patch_sha256="$3"
if [[ ! "$expected_image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "EXPECTED_IMAGE_ID must be sha256:<64 lowercase hex digits>" >&2
  exit 2
fi
if [[ ! "$expected_candidate_patch_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "EXPECTED_CANDIDATE_PATCH_SHA256 must be 64 lowercase hex digits" >&2
  exit 2
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
evidence_dir="$repo_root/results/runs/flutas-candidate-gpu-regression-$run_id"
mkdir -p "$repo_root/results/runs"
mkdir "$evidence_dir" || {
  echo "refusing to overwrite evidence directory: $evidence_dir" >&2
  exit 2
}
write_manifest() {
  manifest_tmp="$(mktemp)"
  (cd "$evidence_dir" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 -r sha256sum) \
    > "$manifest_tmp"
  mv "$manifest_tmp" "$evidence_dir/SHA256SUMS"
}
trap write_manifest EXIT

image_id="$(docker image inspect --format '{{.Id}}' "$image_ref")"
if [[ "$image_id" != "$expected_image_id" ]]; then
  printf 'expected image %s but %s resolves to %s\n' \
    "$expected_image_id" "$image_ref" "$image_id" | tee "$evidence_dir/image-check.txt" >&2
  exit 1
fi
expected_runner_sha256="e90285710e1ce77724d85bcf331c2fe993fdd6367cf3ccec159f81c70c88757c"

{
  printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'run_id=%s\n' "$run_id"
  printf 'purpose=source-disabled candidate GPU regression; not a source-boundary gate\n'
  printf 'image_ref=%s\n' "$image_ref"
  printf 'image_id=%s\n' "$image_id"
  printf 'image_entrypoint=%s\n' "$(docker image inspect --format '{{json .Config.Entrypoint}}' "$image_ref")"
  printf 'explicit_entrypoint=/usr/local/bin/flutas-gpu-tests (GPU test container)\n'
  printf 'upstream_runner_expected_sha256=%s\n' "$expected_runner_sha256"
  printf 'git_revision=%s\n' "$(git -C "$repo_root" rev-parse HEAD)"
  printf 'git_status=\n'
  git -C "$repo_root" status --short
  printf 'expected_embedded_candidate_patch_sha256=%s\n' "$expected_candidate_patch_sha256"
  printf 'launcher_sha256='
  sha256sum "$0"
  printf 'locked_runner_sha256='
  sha256sum "$repo_root/containers/flutas/run-candidate-gpu-regression-locked.sh"
  printf 'docker_cpu_limit=2\n'
  printf 'gpu_lock= scripts/run_local.py --gpu\n'
  printf 'source_input=absent; upstream rising-bubble case only\n'
} > "$evidence_dir/metadata.txt"
cp "$repo_root/results/machine.json" "$evidence_dir/machine.json"
cp "$0" "$evidence_dir/launcher-source.sh"
cp "$repo_root/containers/flutas/run-candidate-gpu-regression-locked.sh" \
  "$evidence_dir/locked-runner-source.sh"
printf '%q ' "$0" "$image_ref" "$expected_image_id" \
  "$expected_candidate_patch_sha256" > "$evidence_dir/command.txt"
printf '\n' >> "$evidence_dir/command.txt"

set +e
"$repo_root/.venv/bin/python" "$repo_root/scripts/run_local.py" \
  --threads 2 --gpu --timeout 600 -- \
  "$repo_root/containers/flutas/run-candidate-gpu-regression-locked.sh" \
  "$evidence_dir" "$image_id" "$expected_runner_sha256" \
  "$expected_candidate_patch_sha256" \
  > "$evidence_dir/launcher.log" 2>&1
run_status=$?
set -e
printf 'run_exit_status=%s\n' "$run_status" > "$evidence_dir/exit-status.txt"
if [[ $run_status -ne 0 ]]; then
  printf 'finished_utc=%s\nresult=FAIL\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$evidence_dir/exit-status.txt"
  echo "GPU regression failed; evidence: $evidence_dir" >&2
  exit "$run_status"
fi

required=(source-disabled-preflight.txt embedded-source-boundary.patch \
          embedded-patch-check.txt compiler.txt nvidia-smi.txt nvaccelinfo.txt flutas-cubins.txt \
          openacc-smoke.txt mpi-gpu-buffer-smoke.txt rising_bubble_3d/solver.log \
          rising_bubble_3d/verification.txt gpu-resource-samples.csv \
          container-resource-samples.tsv resource-sampler-errors.log \
          resource-validation.txt resource-use.txt stage-checks.txt)
for relative_path in "${required[@]}"; do
  if [[ ! -s "$evidence_dir/$relative_path" ]]; then
    printf 'missing or empty required output: %s\n' "$relative_path" \
      | tee -a "$evidence_dir/exit-status.txt" >&2
    printf 'finished_utc=%s\nresult=FAIL\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$evidence_dir/exit-status.txt"
    exit 1
  fi
done
embedded_patch_sha256="$(sha256sum "$evidence_dir/embedded-source-boundary.patch" | awk '{print $1}')"
if [[ "$embedded_patch_sha256" != "$expected_candidate_patch_sha256" ]]; then
  printf 'copied embedded candidate patch hash mismatch: expected %s, got %s\n' \
    "$expected_candidate_patch_sha256" "$embedded_patch_sha256" \
    | tee -a "$evidence_dir/exit-status.txt" >&2
  printf 'finished_utc=%s\nresult=FAIL\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$evidence_dir/exit-status.txt"
  exit 1
fi
printf 'verified_embedded_candidate_patch_sha256=%s\n' "$embedded_patch_sha256" \
  >> "$evidence_dir/metadata.txt"
if [[ -e "$evidence_dir/rising_bubble_3d/source-boundary.in" || \
      -L "$evidence_dir/rising_bubble_3d/source-boundary.in" ]]; then
  echo 'source-boundary.in unexpectedly present in GPU test case' \
    | tee -a "$evidence_dir/exit-status.txt" >&2
  printf 'finished_utc=%s\nresult=FAIL\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$evidence_dir/exit-status.txt"
  exit 1
fi
printf 'finished_utc=%s\nresult=PASS\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$evidence_dir/exit-status.txt"
echo "Source-disabled GPU regression passed; evidence: $evidence_dir"
