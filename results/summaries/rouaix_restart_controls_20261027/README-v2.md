# Komondor restart controls, source v2

V2 is staged at the separate frozen source root and imports passed under Cray Python 3.11.7 with NumPy 1.24.4. The source capsule SHA-256 is `d4de27c68f50afca40920e8553a3b82992777516cc6c6958ad9b300bf495c5dd`.

Two jobs are submitted and remain held (`JobHeldUser`): smoke 14676288 targets ten fixed 0.1 ms continuation steps from 0.2 to 0.201 s; original control 14676290 targets 1000 steps through 0.3 s and depends on `afterok:14676288`. Both request 120 ranks across 3 nodes (40/node), 22 GiB/node, no GPU. The control passes the smoke ID through `ROUAIX_PARENT_SMOKE_JOB_ID` and verifies the smoke archive, terminal state, convergence receipt, layout, and incremental ledger before running.

The new 3-node layout reflects the accepted test-only placement estimate. No solver steps have run while the jobs are held. V1 jobs 14675897 and 14676006 were left untouched for the primary to reconcile after this held receipt.

Focused restart tests: 13 passed; Ruff and formatting checks passed. Raw Slurm readback is in `slurm-readback-v2.txt`; source member hashes are in `source-capsule-index-v2.json`.

## Root release, superseding the held snapshot above

At18:02:56 UTC the primary verified and released smoke14676288 and
control14676290. The control retains afterok:14676288 and kill-on-invalid-
dependency. Auditors14676361/14676362 are armed afterany for each parent.
Oldv1 parent14675897 and auditor14676006 were cancelled while pending,
with zero elapsed time and zero allocated CPUs. See
`v2-release-and-v1-cancel.txt` and `v2-auditor-submit.txt`.

The main README is the current summary. The earlier held-only receipt and
sourcev1 are historical records, not instructions to submit another job.
