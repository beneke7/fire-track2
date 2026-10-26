# Rouaix HPC evidence — 26 October 2026

This compact bundle preserves selected measurements, source hashes, one preview, and the two exact scripts used to make the startup profile. All CFD and startup comparisons here are exploratory. The project's E0 analytical checks are the only passed gate; no E1 validation or acceptance is reported.

## Contents

- [selected-evidence.json](selected-evidence.json): matched-rank scaling, G1 and T1 outcomes, the 0.05 s startup profile, independent interpretation, and the 12:36 UTC scheduler capture.
- [matched-rank-scaling.csv](matched-rank-scaling.csv): four rows selected from the hash-bound matched-rank source JSON.
- [preview/rouaix-alpha001.png](preview/rouaix-alpha001.png): ParaView view of cell `alpha.water >= 0.01` at 0.05 s; this is a computed-field preview.
- [provenance/analyze_startup_snapshot.py](provenance/analyze_startup_snapshot.py) and [provenance/demux_collated_blocks.py](provenance/demux_collated_blocks.py): exact run scripts, copied byte-for-byte.
- [provenance/queue-status-20261026T123616Z.json](provenance/queue-status-20261026T123616Z.json): direct, time-stamped scheduler status; it does not establish later live status.
- [hpc-status-snapshot.md](hpc-status-snapshot.md): exact pre-merge project status snapshot captured by the primary agent.
- [source-hashes.json](source-hashes.json): repository-relative source paths, SHA-256 hashes, byte counts, and copied-artifact hashes.

## Checks

The [check report](checks/checks-summary.json) separates pre-merge and post-merge outcomes. On the integrated tree, all **201 affected tests** and Ruff checks passed. A fresh [E0 report](e0/e0-report.json) passed all seven analytical checks; its small synthetic ground map is included. `make check` remains **not green** because collection needs matplotlib. The pre-merge broader diagnostic (excluding that import) had 775 passes, 19 failures and 6 skips; its preserved log explains platform, dependency and missing-fixture limits. No claim of a passing full suite or CFD gate is made.

## Interpretation limits

G1 job 14648417 stopped after 91/100 steps at 0.0455 s when the speed guard observed a 6975.25 m/s peak. The parent Slurm job failed, despite the solver child writing `End`; this is partial evidence and not a completed 0.05 s result. T1 job 14649329 completed all 500 steps through 0.05 s with the recorded convergence and ledger checks, but does not establish 5 s stability or physical validation. The startup profile uses a cell-threshold and plane-intersection proxy at 0.05 s; the paper's Figure 13 sampling time is unspecified and its run developed for roughly 5 s. Do not call it a Figure 13 match or E1 pass.

The queue capture at 2026-10-26 12:36:16 UTC records jobs 14650641 (120 CPUs, one node) and 14648472 (300 CPUs, three nodes) as PENDING/Priority, with unknown start and end. It is a historical snapshot.

## Reproducibility and exclusions

The local single-node pilot runner can stage work on ephemeral node storage. Its current failure path records `workspace_retained` but does not copy that workspace to durable storage before allocation teardown. A final archive and verification failure could therefore lose the local workspace. All source-run archives represented in this bundle passed their recorded verification, so this limitation does not affect these reported archives; the launcher still needs a durable fallback for future failures.

The exact startup analyzer requires ParaView `pvpython`, the original decomposed fields, and the reference/manifests listed by the run record. The demux script requires the original collated fields. Raw mesh/field inputs and run archives are not included, so this evidence release cannot independently rerun the exact field bundle and neither script can recreate the run outputs from this bundle alone. The original comparison command and all source SHA-256 values are preserved in the upstream startup JSON and this source map. Reference PDFs and large field/archive data are omitted; no source capsule was needed. No credentials, authentication receipts, signed URLs, secrets, or local absolute-path state dumps are included.
