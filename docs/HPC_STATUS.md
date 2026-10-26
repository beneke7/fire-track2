# Komondor Rouaix status

Updated from an independent readback at 2026-10-26 14:11:20 UTC.
Analytical E0 is the only passed gate; current CFD work is exploratory.

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
