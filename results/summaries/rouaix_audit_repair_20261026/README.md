# Native terminal-audit repair — 26 October 2026

**Native smoke 14656128 passed** on one CPU: Slurm `COMPLETED 0:0`, 36 s
elapsed, 34.733 CPU-seconds and 156136 KiB batch MaxRSS. It verified completed
baseline 14652546's archive and captured its 100 steps, 801 converged linear
solves and mass-ledger residual −2.13e-14 kg. The compact bundle SHA-256 was
verified again after rsync. This tests the inspection pipeline, not CFD validity.

The earlier smoke 14654156 failed in two seconds because `sacct` on the compute
node connected to the configured `localhost:6819` and received connection
refused. Login-node `sacct` worked. Its five dependent auditors correctly
cancelled without allocating CPUs; the CFD parents were unaffected.
`diagnosis/` and `deployment/v2-failure-*` retain that failure evidence.

The repaired [auditor](../../../scripts/hpc_finished_audit.py) first tries
`sacct`, then retained parent state from `scontrol`. A completed parent can
already have aged out of the controller. If both routes are unavailable, the
auditor still captures a SHA-verified archive, leaving scheduler state
`UNKNOWN`, classification `scheduler_state_unavailable` and CPU accounting
unavailable. It never substitutes zero CPU. No-archive attempts report the
artifact/accounting gap without inventing a physical solver result. An input
mismatch remains higher priority than an unavailable scheduler classification.
Later accounting recovery can produce a new immutable capture version.

The native smoke exercised the actual unavailable-accounting/purged-parent
path. Its retained `native-smoke/audit.json` and packed bundle contain raw
solver, convergence and ledger diagnostics and explicit gaps. Actual parent
CPU/RSS must still be retrieved through the login node; the original
[baseline evidence](../rouaix_p0_base_20261026/README.md) already contains that
separate accounting. Missing accounting does not prevent archive inspection.

## Armed follow-up inspections

The smoke's success prerequisite is satisfied. Three one-CPU auditors are
released and now wait only for their explicit parents to terminate:

- **14656217** → original 120-rank **14651174**, currently running.
- **14656218** → upwind 120-rank **14651178**.
- **14656219** → long-horizon **14650641**.

Each requests one node, one task/CPU, 1800 MiB, ten minutes and no requeue/GPU.
Held identities, request shapes and `afterok:<smoke>,afterany:<parent>`
prerequisites were checked before release. `--kill-on-invalid-dep=yes` prevents
orphaned queued auditors after a failed smoke. The newly completed
[96-rank](../rouaix_s1_96_20261026/README.md) and
[24-rank profiling](../rouaix_p0_profile_20261026/README.md) cases received
direct terminal audits, avoiding duplicate post-processing jobs.

Frozen source:
`/project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-source-v3-20261026`.
Source archive SHA-256:
`e343ed46f6920faf622801094f6934399fa7a3b4245e63821f465acfcd3602d3`.
Reports:
`/project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-reports-v3-20261026/<parent-id>/`.
`deployment/source.tar.gz` preserves the executed source; its manifest binds
the five payloads, base revision and dirty state. Prior frozen versions remain
preserved. No CFD source, mesh, numerics, requests or dependencies changed.

## Verification and limits

97 auditor/metrics/runner tests passed, plus Ruff check/format and batch shell
syntax. Regression tests cover the exact connection refusal, state-only
controller fallback, purged-parent archive/no-archive cases, input mismatch,
no fabricated CPU and later accounting recovery. `root-checks.json` records
the checks; `deployment/smoke-verification.json` records the real native result.
`files.sha256.json` hashes this curated packet's payloads.

Inspections are finite and subject to their ten-minute, 1800 MiB and selected
payload limits. Full 3D fields are not copied; raw native profiling is retained
for interpretation rather than automatically presented as all-rank timing.
There is no momentum-validation or E1 gate decision, full field-I/O measurement,
W&B upload, or claim that the unrelated full repository suite is green.
