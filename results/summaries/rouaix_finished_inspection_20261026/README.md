# Finished-run inspection, 26 October 2026

The exact-ID inventory covers **64 case attempts**: 59 terminal and five
pending at capture, plus **19 terminal control/support jobs**. It separates
raw Slurm state, wrapper exit, solver/mesh result and remaining evidence gaps.
Unrelated shared-account jobs are excluded. This is an exploratory evidence
review; analytical E0 remains the only passed gate.

`inventory.json` binds each attempt to retained evidence and its SHA-256;
`audit-gaps.json` records 12 findings. All 36 referenced gap-evidence paths and
hashes were checked locally. Some references point to ignored raw run bundles
retained on this workstation/HPC, rather than being included in Git. The
published [S1 64-rank result](../rouaix_s1_64_20261026/README.md) and
[P0 24-rank baseline](../rouaix_p0_base_20261026/README.md) contain compact raw
solver, convergence and ledger evidence. Native full-field archives remain on
Komondor; no large field download was needed.

The review recovered tutorial 14641244 as 100 solver steps through its declared
0.1 s despite a subsequent old-layout parser failure. Its initial inventory
and phase flux were not retained, so no mass/momentum closure can be claimed.
Job 14641346's recovered stdout identifies a run-directory preflight refusal;
the interpolated failed operand remains unknown. Native mesh failures
14643854/14643873 concern the exact 10,099,265-cell final cast-only mesh, with
the existing concavity exception; they remain native checkMesh failures.

## Active inspection on Komondor

The predeclared [audit manifest](../../../experiments/hpc_finished_audit_20261026.json)
lists only six explicit CFD parents. The native
[auditor](../../../scripts/hpc_finished_audit.py) and
[batch wrapper](../../../scripts/hpc_finished_audit.sbatch) read parent
accounting and immutable archives, validate SHA-256 and tar members, extract
compact diagnostics only, and preserve a packed audit bundle plus status.
They reuse the existing solver-convergence and metrics parsers, report missing
diagnostics, and never modify or restart CFD jobs. Native collated profiling
containers are retained for subsequent interpretation; no pressure-time or
full-field I/O result is fabricated.

V2 smoke **14654156** inspects completed baseline 14652546. Five released
auditors require `afterok:14654156` AND `afterany:<parent>`:

- 14654159 → original 96-rank 14651185.
- 14654160 → original 120-rank 14651174.
- 14654161 → upwind 120-rank 14651178.
- 14654162 → long-horizon 120-rank 14650641.
- 14654163 → profiling 24-rank 14652548.

At 19:03 UTC all were pending, with zero allocation; native execution has not
yet passed. Failed smoke makes dependent auditors cancel via
`--kill-on-invalid-dep=yes`. Each audit requests one node, one CPU, 1800 MiB
and 10 minutes, no requeue and no GPU. All six held resource identities and
both dependency prerequisites were verified before release. Maximum aggregate
allocation is one core-hour if all six hit their cap; no idle core is held.
V1 smoke 14654148 was cancelled while unallocated before the native profiling
selection fix. Its source and zero-CPU cancellation record are preserved.

Remote source:
`/project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-source-v2-20261026`.
Source archive SHA-256:
`31f931535d845484e5f4dac630ee776602c7350570d1512cbf89233f307d81da`.
Reports:
`/project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-reports-v2-20261026/<parent-id>/`.
Exact launch/readback records are in `deployment/`; the preserved source
manifest binds the dirty source bytes and base revision. No W&B upload occurred.

## Checks and limits

95 auditor/metrics/runner tests passed, with no skipped integration test;
Ruff check/format and batch shell syntax passed. The real S1 fixture is
self-contained in tracked files and checks published raw-log/ledger hashes.
The separate `worker-checks.json` captures the worker's narrower 11-test check.
`files.sha256.json` hashes the curated inventory payloads. Existing full-suite
dependency/platform failures were not repaired or claimed green.

Capturing a report is not a physical validation decision. TKE extrema,
aggregate job memory, momentum closure and native profile interpretation still
require appropriate evidence/review. Audits remain subject to Slurm allocation
and their 10-minute/selected-payload limits; missing or oversized artifacts are
reported rather than silently passed. Timestep values are compared against the
attempt manifest; independent checks of every logged time increment remain
manual. This finite audit list does not discover
new unrelated or subsequently submitted jobs.
