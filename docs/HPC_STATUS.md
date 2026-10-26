# Komondor Rouaix status

Updated 2026-10-26 21:43 UTC (22:43 CET). Analytical E0 remains the only
passed gate; all CFD results below are exploratory.

## Current compute and queue

**No CFD cores are currently allocated.** Original 120-rank trial 14651174
completed at 20:58:16 UTC; its automatic inspector 14656217 completed at
20:59:43 UTC. Upwind 120-rank 14651178 is now eligible but pending on Priority,
with start estimate N/A; its earlier midnight CET forecast was withdrawn.
Independent 5 s target 14650641 is also pending on Priority; latest forecast
27 October 16:29:55 UTC (17:29:55 CET). Forecasts are not reservations.
Both remaining CFD jobs have released afterany inspectors waiting for them.

## New terminal results

- **120-rank original, 14651174:** all 500 fixed .1 ms steps through .05 s;
  all 4,001 recorded linear solves converged, peak speed 103.29355 m/s.
  Bulk/interface Co 1.12154/.56017; mass closure +1.0466e-11 kg.
  Solver wall 1638.392 s (27m18); whole job 1839 s (30m39), 61.300 allocated
  core-hours and 54.127 TotalCPU hours. This is faster and fewer allocated
  core-hours than the 96-/64-rank short trials, with host/NUMA/co-tenancy
  uncertainty preventing a controlled scaling claim. Native automatic audit
  verified the archive and diagnostics; login-node accounting supplements its
  state-only controller fallback.
  [Compact terminal audit](../results/summaries/rouaix_s1_120_20261026/README.md).
- **96-rank original, 14651185:** 500 fixed .1 ms steps through .05 s;
  all 4,001 recorded linear solves converged. Peak speed 103.3235 m/s,
  bulk/interface Co 1.1312/.53365. Mass-ledger closure +1.0466e-11 kg.
  Solver wall 2140.708 s (35m41); whole job 2339 s (38m59), 62.373 allocated
  core-hours and 56.630 TotalCPU hours. It used 96 ranks on a 128-CPU node,
  not a 96-CPU machine. Parent MaxRSS is absent; batch MaxRSS 9446824 KiB
  and solver-task MaxRSS 1469532 KiB are separate, not node aggregate.
  [Verified raw/compact audit](../results/summaries/rouaix_s1_96_20261026/README.md).
- **24-rank profiling, 14652548:** 100 fixed .1 ms steps through .01 s,
  all 801 linear solves converged. Ledger, peak-speed and convergence outputs
  match the unprofiled baseline's hashes. Peak speed 91.242559 m/s, mass
  closure -2.13e-14 kg. Solver wall 2221.959 s; whole job 2409 s (40m09),
  16.060 allocated core-hours and 14.766 TotalCPU hours. Solver wall is
  +1.394% versus baseline on another node, an uncontrolled timing difference.
  [Profile audit and raw object](../results/summaries/rouaix_p0_profile_20261026/README.md).

The profile contains one ordinary dictionary under a collated processor path,
with `caseprocessor0` scope; no all-rank max/average/min summary was retained.
Rank-zero pressure linear-solver scope is 850.222 s/300 calls. The .0387 s
`objectRegistry::writeObject` scope covers only `uniform/time`, not full field
I/O. No aggregate node memory/cgroup trace or full checkpoint timing exists.

Both full result archives were hash/member checked remotely and compact
payloads rsynced with matching hashes. Full 3D archives remain on Komondor.
Mass closure and linear convergence do not establish momentum closure or
physical fidelity; large turbulence extrema remain unresolved.

## Earlier terminal references

[S1 64-rank 14651180](../results/summaries/rouaix_s1_64_20261026/README.md)
reached .05 s/500 steps, all 4001 solves converged, peak speed 103.5026 m/s,
solver wall 3490.203 s, whole job 3681 s. It ran on a GPU-capable 64-CPU
host without GPU allocation. The new 96-rank case was faster and used fewer
allocated core-hours, but different hosts prevent a controlled scaling claim.
[P0 baseline 14652546](../results/summaries/rouaix_p0_base_20261026/README.md)
reached .01 s/100 steps, solver wall 2191.417 s and whole job 2372 s.
Native v2512 mesh use still carries the documented exact-mesh concavity
exception, not an unconditional native checkMesh pass.

## Active terminal inspection

V2 smoke 14654156 failed after two seconds: compute-node sacct could not
reach localhost:6819. Its five dependent auditors cancelled with zero CPUs.
The failed source/status/accounting evidence is preserved; CFD jobs were
unaffected. Login-node sacct remains usable.

**Repaired native smoke 14656128 passed** in 36 s, 34.733 CPU-seconds and
156136 KiB batch MaxRSS. It verified the baseline archive, 100 steps, all
801 solves and ledger. Missing sacct/purged controller state are explicit
UNKNOWN/null accounting gaps; no CPU or scheduler state is fabricated.
The real 120-rank completion also passed native inspection: 14656217 ran
39 s, 37.471 CPU-seconds and 160956 KiB batch MaxRSS; it recovered retained
COMPLETED state through scontrol and preserved verified archive diagnostics.
Actual CPU/RSS were separately captured through login sacct. The two remaining
inspectors are 14656218 -> upwind 14651178 and 14656219 -> 5 s 14650641;
smoke success is satisfied and each waits for its parent's termination.
Completed 96-rank/profile runs were audited directly.
Each inspector is bounded to one CPU, 1800 MiB, ten minutes, no requeue/GPU.
[Native proof, source hashes and repaired deployment](../results/summaries/rouaix_audit_repair_20261026/README.md).

97 affected auditor/metrics/runner tests, Ruff and shell syntax passed.
Root owns integration; workers completed inspection, not separate CFD jobs.
[Historical attempt registry](../results/summaries/rouaix_finished_inspection_20261026/README.md)
preserves the earlier 59 terminal cases/19 support jobs plus its five-pending
snapshot; the three new terminal audits above supplement that frozen inventory.
