# Rouaix native early-save smoke — 28 October 2026

## Purpose and scope

Exercise the native OpenFOAM signal-12 write-and-stop path from the same
hash-bound 0.2 s checkpoint used by the 27 October restart controls. Request a
save after three completed continuation steps, while the recorded control was
still in its stable early interval. This is a stop/save observability smoke,
not a Rouaix E1 benchmark result or validation decision.

The terminal-v4 control receipt listed signal 12 but wrote
`stop_requested_utc` after the blocking wait, and the saved evidence could not
establish whether the signal preceded the later FPE. The refreshed runner records
the verified job step and request time before the call, then the successful
Slurm acknowledgement before waiting. The terminal-v4 diagnosis remains
historical evidence at
`results/summaries/rouaix_restart_controls_20261027/terminal-v4/README.md`.

The source is the existing parent archive
`rouaix-healthy-seed-source-v1-20261027/rouaix-e1-hpc-pilot-14669440/result.tar.gz`
(SHA-256 `31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9`).
Use its measured 0.2 s checkpoint and all stored fields as-is. Do not source
from, overwrite, or alter the historical v4 control evidence.

## Declared inputs and execution

- Native OpenFOAM v2512 `interIsoFoam`, CPU-only Slurm execution.
- 3 nodes × 40 MPI ranks (120 total), 1 CPU per task, 22 GiB/node, 20 minute
  allocation; 1,200 s runner wall budget.
- Continue from 0.2000 s with fixed `deltaT = 0.0001 s`; planned horizon
  0.2020 s. The nominal `writeInterval` is 0.002 s. Only restart-window and
  output-cadence entries in `controlDict` change; mesh, fields, solver schemes,
  solution controls, boundaries, turbulence model, and physical inputs remain
  those of the parent checkpoint.
- The supervisor requests signal 12 after three completed post-checkpoint
  steps, at logged solver time 0.2003 s. OpenFOAM's native handler schedules
  writing and stopping at the end of the next iteration, so the actual endpoint
  may include one or two additional complete steps. Record and audit the actual
  endpoint; do not label it as the requested 0.2020 s horizon.
- The 1,000 m/s operational guard remains unchanged. This diagnostic does not
  lower or reinterpret it.

The read-only v2512 source inspected on Komondor is
`/opt/software/packages/openfoam/v2512-20251230/OpenFOAM-v2512/src/OSspecific/POSIX/signals/sigStopAtWriteNow.cxx`
(SHA-256 `5571278a48efd49507546d9ac4aa419519010d5a2de822992d53e287761a7a03`).
Its handler calls `stopAt(Time::saWriteNow)` and prints that writing and
stopping are set up for the end of the next iteration; the loaded executable
and runtime banner remain checked by the runner.

## Required smoke evidence

Preserve request-initiation UTC and the verified `job.step` identity before the
signal request. Preserve successful `scancel` acknowledgement UTC and the
signal list before the blocking step-exit wait; an unsuccessful verification or
request must not be recorded as signal 12 sent. Require the native runtime
write-and-stop receipt, clean `End`, exit code 0, no pause, and all eight
collated endpoint fields plus `uniform/time`. The audit must match the terminal
step count to the raw log and fixed timestep, accept only an actual endpoint
after at least three completed steps (including the native one-to-two-step
overshoot), and integrate the complete actual interval from the parent ledger.

Raw mass residuals and solver convergence are diagnostics only. No physical
acceptance tolerance is declared or inferred, and this run does not establish
nearfield agreement, field performance, or a conservation gate.

## Launch artifacts

- Local runner: `cases/e1_rouaix_hpc_restart/run_restart.py`, variant
  `original-early-save`.
- Native batch script: `cases/e1_rouaix_hpc_restart/restart_early_save.sbatch`.
- Unique remote source/run roots are declared in that batch script under
  `rouaix-early-save-source-20261028` and `rouaix-early-save-20261028`.
- Local preparation/output directory:
  `results/runs/rouaix-early-save-20261028/`.

The early-save capsule, complete launch manifests, and queue are not released by
this record. The root agent must review and freeze the changed sources, stage
them under the declared unique root, and perform the remote preflight before
submission.
