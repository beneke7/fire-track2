# Komondor Rouaix status

Updated 2026-10-26 20:39 UTC (21:39 CET). Analytical E0 remains the only
passed gate; all CFD results below are exploratory.

## Current compute and queue

**120-rank original trial 14651174 is RUNNING**, started 20:27:37 UTC on
x1000c1s2b0n1. At 20:32 UTC it had reached .0043/.05 s with peak speed
84.16 m/s and no recorded stop. It uses fixed .1 ms timesteps.
Upwind 120-rank 14651178 remains afterany-dependent on that trial. Independent
5 s target 14650641 remains pending on Priority; the latest provisional start
forecast is 27 October 16:29:55 UTC (17:29:55 CET). Forecasts are not reservations.
Our CFD allocation is 120 CPUs; pending requests are not allocated CPUs.

## New terminal results

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
The three remaining parents have released dependent inspectors:
14656217 -> original 120-rank 14651174; 14656218 -> upwind 14651178;
14656219 -> 5 s 14650641. Smoke success is satisfied; each waits for its
own parent's termination. Completed 96-rank/profile runs were audited directly.
Each inspector is bounded to one CPU, 1800 MiB, ten minutes, no requeue/GPU.
[Native proof, source hashes and repaired deployment](../results/summaries/rouaix_audit_repair_20261026/README.md).

97 affected auditor/metrics/runner tests, Ruff and shell syntax passed.
Root owns integration; workers completed inspection, not separate CFD jobs.
[Historical attempt registry](../results/summaries/rouaix_finished_inspection_20261026/README.md)
preserves the earlier 59 terminal cases/19 support jobs plus its five-pending
snapshot; the two new terminal audits above supplement that frozen inventory.
