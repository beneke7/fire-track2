#!/usr/bin/env bash
set -euo pipefail
if [[ ${SLURM_PROCID:-} == 0 ]]; then
  printf '%s %s %s %s\n' "${SLURM_JOB_ID:-}" "${SLURM_STEP_ID:-}" "${SLURM_NTASKS:-}" "${SLURM_PROCID:-}" > "${ROUAIX_STEP_IDENTITY}.tmp"
  mv -- "${ROUAIX_STEP_IDENTITY}.tmp" "$ROUAIX_STEP_IDENTITY"
  { printf 'slurm_procid=%s\n' "$SLURM_PROCID"; sed -n '/^Cpus_allowed_list:/p; /^Mems_allowed_list:/p' /proc/self/status; } > "$ROUAIX_RANK0_AFFINITY"
fi
exec interIsoFoam -parallel
