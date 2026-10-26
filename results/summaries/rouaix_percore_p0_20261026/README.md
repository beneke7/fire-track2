# Small-allocation profiling campaign — 26 October 2026

The current jobs are **14652546** (baseline) and **14652548** (native profiling, afterany baseline). Both request 24 MPI ranks, 24 CPUs and one CPU per task, one node, 46 GiB, fixed 0.1 ms through 0.01 s/100 steps and a 60 min cap. They use the same 10,099,265-cell mesh and original numerical settings; the profile adds only the native monitoring block.

At the [independent 15:12 UTC capture](root-final-readback.json), both jobs and all five earlier CFD jobs were pending, with no start forecasts or allocated compute. There is no measured performance gain yet. The shared account had 25 allocated CPUs (1 cpu, 24 gpu); these belonged to other work, with zero CFD CPUs allocated.

The initial 48 GiB held request became 48 CPUs for 24 tasks/2 CPUs per task. It was cancelled before allocation. A 46 GiB request fits below the visible 2000 MiB/core threshold at 24 cores and read back as the intended 24 CPUs/one CPU per task. Test-only admission had missed the inflation; actual held-job verification caught it. Preserve the [cancelled-admission receipt](submission/baseline-cancelled-overallocation.txt), exact submitted commands, and immutable v2 case records.

Prior same-mesh sums of task RSS high-water marks were about 31.2–33.6 GiB; 46 GiB is an informed operating budget with about 37% margin, not a measured 24-rank peak. The [research proposal](proposal.json) retains the independent earlier memory recommendations; the active A2 declaration and actual held admission supersede its preliminary resource suggestions. See the [full declaration](../../../experiments/E1_ROUAIX_HPC_PROGRESSION.md).

The source captures CPU topology/rank-zero affinity and optional cgroup-v2 job memory peaks. Native profile scopes can expose linear-solver wall time and rank imbalance; they cannot time full field I/O. Numerical checks must pass before an overhead ratio is interpreted. Current 221 affected tests and Ruff pass; the full suite was not rerun.

S1's scheduler order was separately amended to 64 -> 96 -> original 120 -> upwind 120, preserving every numerical input and original record. P0 is independent so a 24-core opening can admit useful work while larger jobs wait. At most one P0 and one S1 short job can run alongside the independent 5 s target.

Source, case and scheduler hashes are retained here; large input/result archives remain outside Git. All 24 source member bytes matched this repository at verification. Batch cwd/Slurm stdout retain the historical /scratch defaults documented in the case records; submitted environment explicitly places source, run data and workspaces under the verified /project v2 root. No scientific gate or developed-flow performance qualification is claimed.
