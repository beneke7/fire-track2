# Komondor Rouaix status

Updated from independent scheduler/accounting captures on 2026-10-26, latest 17:57 UTC.
Analytical E0 is the only passed gate; current CFD work is exploratory.

## Current queue and per-core profiling

Latest allocation update **17:57:33 UTC (18:57:33 CET)**: P0 baseline
**14652546 is RUNNING with 24 CPUs/one node**, started 17:49:48 UTC
(18:49:48 CET) on x1000c6s1b1n0. Profiling partner 14652548 remains
afterany-dependent. S1 64-rank 14651180 completed; the other five jobs
remain pending. L1's start forecast is currently N/A again. This confirms
allocation only; P0 solver progress has not yet been inspected.

**64-rank S1 completed:** job 14651180 ended 16:44:37 UTC (17:44:37 CET),
all 500 fixed 0.1 ms steps through 0.05 s. All 4,001 linear solve records met
their criteria. Peak speed 103.5026 m/s; bulk/interface Co 1.1210/0.5402;
500-row mass-ledger residual +1.05e-11 kg. Solver srun wall 3490.203 s,
whole job 3681 s/65.44 allocated core-hours; TotalCPU 61.57 core-hours.
Native archive verification succeeded and root's terminal analyst separately
matched remote SHA/member inventory and 16 compact files at both ends.
[Terminal result](../results/summaries/rouaix_s1_64_20261026/README.md).

It ran through Backfill/cpu-short on 64-CPU GPU-capable node x1001c2s3b0n0,
with no GPU TRES allocated. Hardware differs from the 120-rank 128-CPU case;
their peak-speed agreement (~0.2%) is a scalar check, not controlled scaling
or field convergence. High turbulence values and physical fidelity remain
unqualified. The full horizon is only 0.05 s; no E1 gate was assessed.

At **17:43:58 UTC (18:43:58 CET)** the other six jobs had zero allocations:
96-rank 14651185 and 24-rank 14652546 wait on Priority; 120-rank 14651174,
upwind 14651178 and profile 14652548 wait on Dependency. L1 job 14650641
waits on Priority, provisional forecast 28 October 02:48:48 UTC
(03:48:48 CET); the other starts are N/A. The 64-rank node has been released.

At **15:29:10 UTC (16:29:10 CET)** all seven owned CFD jobs remained
PENDING with zero allocated CPUs. The shared account had **1 CPU allocated**
on the cpu partition for unrelated work. Earlier snapshots were 82 CPUs at
14:51 and 25 at 15:12; allocation counts do not establish actual CPU activity.

Slurm now forecasts L1 job 14650641 for **28 October 06:46:56 UTC
(07:46:56 CET)**. The other six jobs still show N/A start estimates. This is
a provisional scheduler forecast, not a reservation or guaranteed start.

S1 now runs **64 -> 96 -> original 120 -> upwind 120**, jobs 14651180 ->
14651185 -> 14651174 -> 14651178. Root amended only pending dependencies,
verified the chain and released the brief control hold. Numerical inputs,
source snapshots, requests and original declarations remain preserved.
The independent 5 s target 14650641 is unchanged.

P0 v2 is submitted and released: **14652546 baseline -> 14652548 native
profile**. Both request 24 ranks/24 CPUs/CPT1, one node, 46 GiB, fixed 0.1 ms
through 0.01 s/100 steps and 60 min. Baseline waits on Priority and profile
on Dependency. Real held readbacks verified that shape. The earlier 48 GiB
request 14652491 became 48 CPUs/CPT2 and was cancelled before allocation.
The cpu limit is 2000 MiB/core: 48 GiB/24 exceeds it, whereas 46 GiB/24 fits.
Test-only admission did not reveal that inflation.

Prior summed task RSS peaks 31.2–33.6 GiB informed the 46 GiB budget; the
24-rank actual peak remains unmeasured. New source retains default 64 GiB,
adds 24-rank/memory/profile support, and captures topology, rank-zero affinity
and optional cgroup-v2 memory peaks. The profile adds only monitoring;
pressure/rank timing and overhead await execution, and full I/O timing is
not covered. No measured solver speedup or scientific gate is claimed.

All 221 affected tests and Ruff pass. Root verified the frozen 24-file v2
capsule against current bytes, submitted flags, actual CPU/memory shape and
source command. [Compact P0 proof](../results/summaries/rouaix_percore_p0_20261026/README.md);
full records: `results/runs/rouaix-percore-p0-20261026/`.

## Earlier S1 submission capture

S1 replacement is queued and released: **14651174** original 120 ranks,
**14651178** matched upwind 120, **14651180** original 64, **14651185**
original 96. The afterany chain runs in that order; each uses one node,
64 GiB, fixed 0.1 ms through 0.05 s/500 steps. Pending three-node job
14648472 was cancelled after identity checks; it already used 0.1 ms.
Historical completed 0.5 ms scaling evidence is retained. Independent 5 s
job 14650641 and unrelated account jobs are unchanged.

Root readback **14:11:20 UTC (15:11:20 CET)**: all five jobs PENDING, no
run-state/solver process started. 14651174 and 14650641 wait on Priority;
other S1 jobs wait on Dependency. All StartTime forecasts are Unknown/N/A.
The four held submissions were individually checked and released; no job
remains held. The 64-rank job is also eligible for site-added cpu-short.

New source adds 96-rank support, explicit shared-/project workspaces and an
active progression copy/hash in each attempt before preparation. 208 affected
tests and Ruff pass. The frozen 24-file capsule and hardlinked input were
hash-verified on Lustre; root verified all source bytes against the current
tree and scheduler resources/dependencies independently. Source capsule:
4d67729f3fee89aa888e9e8869952f1339ba0d02450b5e8528f1848b63d60420.
[Compact campaign evidence](../results/summaries/rouaix_s1_20261026/README.md);
full captures: `results/runs/rouaix-one-node-campaign-20261026/`.
Root owns integration and interpretation; no preparation agent is a CFD job.

Earlier measured results and startup comparison: [26 October bundle](../results/summaries/rouaix_hpc_20261026/README.md).
