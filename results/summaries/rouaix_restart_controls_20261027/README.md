# Komondor restart work — current queue

**14676288** is a released restart smoke: load the verified0.20 s donor,
run ten fixed0.1 ms steps to0.201 s, and verify checkpoint/diagnostics/
incremental mass accounting. It has a20-minute cap.

**14676290** is the released unchanged original-scheme control through
0.30 s (1000 continuation steps), with a90-minute cap. It waits on
`afterok:14676288`, cancels if that dependency fails, and independently checks
the actual smoke endpoint, ten-step count, three-node layout, residuals,
incremental ledger and verified archive before its own solver launch.

Both use **120 MPI ranks across three nodes,40/node,22 GiB/node** (66 GiB
total), cpu-short, one CPU/rank, collated I/O, no GPU/requeue. This keeps the
120-way checkpoint decomposition and avoids replaying the first0.20 s.
The distribution favors fragmented short-partition capacity; forecast starts
are not reservations. No restart steps had been observed at release.

Native v3 afterany auditors14676361/14676362 are armed, each bounded to one
CPU,1800 MiB,ten minutes. `afterany-manifest-v2.json` binds their expected
source/run paths, IDs, ranks, horizons and timesteps. Native auditor capture
success alone is not a scientific or restart compatibility pass.

`README-v2.md`, `submission-v2.json` and `slurm-readback-v2.txt` preserve the
held submission; `v2-release-and-v1-cancel.txt` and `v2-auditor-submit.txt`
record subsequent root actions. V1 jobs14675897/14676006 were replaced
while pending, with zero allocated CPUs and no solver steps; exact old
sources/receipts remain here. Do not reuse the preliminary v1 launcher.

The frozen v2 capsule SHA is
`d4de27c68f50afca40920e8553a3b82992777516cc6c6958ad9b300bf495c5dd`.
Remote source hashes and Cray Python imports passed. NumPy1.24.4 is supplied
by the existing Cray Python environment; no dependency was installed.
Thirteen focused restart tests passed; the combined affected HPC/restart run
passed105 tests. Ruff, formatting and shell syntax passed.
The smoke has not yet demonstrated native restart success; the full repository
suite was not rerun. The13-test unit success does not replace the native smoke.

The declared p0=0 total-pressure sensitivity is **not submitted**. The unchanged
restart control must first establish behavior across the previous instability
window. That future pressure treatment is diagnostic, not a paper-matched BC
or a validated fix. All CFD remains exploratory; only analytical E0 has passed.
