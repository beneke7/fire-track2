# Komondor Rouaix status

Updated 2026-10-26 19:03 UTC (20:03 CET). Analytical E0 is the only passed
gate; these CFD runs and their inspections are exploratory.

## Completed short-horizon results

- **S1 original 64 ranks, 14651180:** 500 fixed 0.1 ms steps through 0.05 s;
  all 4,001 recorded linear solves converged; peak speed 103.5026 m/s,
  bulk/interface Co 1.1210/0.5402; ledger closure +1.05e-11 kg.
  Solver wall 3490.203 s; whole job 3681 s, 65.44 allocated core-hours,
  61.57 actual CPU-hours. It ran on a 64-CPU GPU-capable host without GPU
  allocation, so runtime is not a controlled comparison with CPU128 nodes.
  [Hash-verified terminal evidence](../results/summaries/rouaix_s1_64_20261026/README.md).
- **P0 original 24 ranks, 14652546:** 100 fixed 0.1 ms steps through 0.01 s;
  all 801 recorded linear solves converged; peak speed 91.2426 m/s,
  bulk/interface Co .95745/.42012; ledger closure -2.13e-14 kg.
  Solver wall 2191.417 s; whole job 2372 s (39m32), 15.813 allocated
  core-hours and 14.559 actual CPU-hours. Final wall time supersedes a stale
  periodic solver_elapsed value. Batch MaxRSS 9.21 GiB and solver MaxRSS
  2.15 GiB per task are separate, not aggregate memory. No cgroup-v2 trace or
  pressure/full-I/O profile exists for this baseline.
  [Compact raw evidence](../results/summaries/rouaix_p0_base_20261026/README.md).

Both archives and compact file hashes were independently checked; full 3D
archives remain on the HPC. Large turbulence/reduced-pressure values and
momentum balance remain unresolved. No Rouaix field-validation result follows
from linear convergence or mass closure alone.

## Live CFD queue

At 19:03 UTC all five have **zero allocation**:

- S1 original 96 ranks **14651185**, Priority; .05 s target.
- S1 original 120 ranks **14651174**, afterany 14651185; .05 s target.
- S1 upwind 120 ranks **14651178**, afterany 14651174; .05 s target.
- P0 profile 24 ranks **14652548**, Priority; .01 s target.
- L1 original 120 ranks **14650641**, Priority; 5 s target.

All use fixed .1 ms timesteps. Latest start estimates are N/A and may change.
P0 baseline/profile requests were verified as 24 CPUs/CPT1, one node, 46 GiB.
The prior 48 GiB request inflated to 48 CPUs and was cancelled unallocated;
2000 MiB/core is the partition limit. Frozen CFD source roots are unchanged.
[Submission/provenance proof](../results/summaries/rouaix_percore_p0_20261026/README.md).

## Active terminal inspections

The historical review covers **59 finished case attempts plus 19 finished
support jobs**, and records the five pending cases separately. It recovered
parser-only and preflight failures while preserving missing conservation data
and the exact-mesh native concavity exception. All 36 gap-evidence references
and hashes were checked; some raw bundles are retained outside Git.

Six one-CPU post-processing jobs are released: smoke **14654156**, then
**14654159–14654163**, each requiring the successful smoke AND its explicit
CFD parent's termination. Each requests 1800 MiB/10 minutes, no requeue/GPU;
all held shapes and dependencies were verified. At this capture the smoke is
pending; native execution is unverified. Failed smoke cancels dependents.
V1 smoke 14654148 was cancelled before allocation for a profiling-selection
fix; its source and zero-CPU record remain preserved.

[Inspection registry, exact audit-parent mapping and deployment evidence](../results/summaries/rouaix_finished_inspection_20261026/README.md).
Auditors preserve hashes, compact diagnostics, convergence/ledger/accounting
and explicit diagnostic gaps. They do not restart jobs, interpret raw native
profiles, publish dashboards, or modify unrelated shared-account work.
95 affected auditor/metrics/runner tests, Ruff and shell syntax passed.

Root owns integration/interpretation. Completed workers are not running CFD
processes. Earlier campaign snapshots and measured results remain in
[the 26 October bundle](../results/summaries/rouaix_hpc_20261026/README.md),
[the S1 submission bundle](../results/summaries/rouaix_s1_20261026/README.md)
and the inspection bundle's previous-hpc-status.md.
