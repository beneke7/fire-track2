# Candidate5 successor and analyzer F1 primary disposition

**Primary disposition, 2026-09-25 14:03 UTC.** This closes two narrow software
checkpoints and the one GPU trial they gated. It does not release source mode,
B1-pre, B2, CFD, or any scientific gate.

The primary **accepts F1 as closed for the exact hashes only** in
[`FLUTAS_ANALYZER_F1_HANDOFF_20260925T1342Z.md`](FLUTAS_ANALYZER_F1_HANDOFF_20260925T1342Z.md):
analyzer `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37`,
tests `b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20`,
implementation note `e6a4d2776859e62f53c60fb0662c5264bf748ab5bf6b8a4169b66d26a6f64171`,
and unchanged schema v1.2. Astra Max's
[`exact review`](FLUTAS_ANALYZER_F1_EXACT_REVIEW_20260925T1348Z.md), SHA-256
`058fed812980ab82d81c97bfd785713b2782c333575daea19d5dea296824d2b2`,
independently reran all 57 focused tests, Ruff and formatting, plus 42 literal
outcomes across phase and velocity tables. Staged-input binding, six-ledger
conservation, source launch, B1-pre/B2 and source runs remain closed.

The primary **accepts the Astra successor review only for one source-disabled
smoke** on the exact local image and patch. Reviewer memo:
[`FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md`](FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md),
SHA-256 `9615e07d93e9c3d4e0bcd1b4a2373650419a56ba7f220ca3a90f96b2074c108c`.
Exact image ID is
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`;
patch SHA-256 is
`aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7`.
Before launch, `make doctor` reported 20 effective CPUs, 117.8 GiB available
RAM, 236.8 GiB free disk, and one RTX 5090 with 31.8 GiB; Docker had no running
container and the GPU was idle. The unchanged launcher used two CPU cores, the
shared GPU lock, and a 600-second timeout.

The one smoke passed at
[`results/runs/flutas-candidate-gpu-regression-20260925T135456Z-2137699/`](../../results/runs/flutas-candidate-gpu-regression-20260925T135456Z-2137699/).
It completed the OpenACC check, CUDA-buffer MPI test, and upstream rising
bubble through 3 s; the verifier printed `True True`. No
`source-boundary.in` existed in the staged case. Exit status is 0; all files
listed in `SHA256SUMS` verify. SHA-256 of that list is
`4e1852edfb1f772665c23c45040c5ab83225184017b821a4f694feb34620d142`.
Thirteen GPU and eleven container samples parsed without malformed rows;
sampled maxima were 100% GPU utilization, 668 MiB GPU memory, 147.62 W,
330.4 MiB container memory and 193.96% container CPU. These samples are not
hardware peaks. The result closes one source-disabled software regression,
not source behavior, source resource use, or scaling.

The source-provenance locator in the producer handoff is corrected by the
append-only primary erratum
[`CANDIDATE5_SOURCE_PROVENANCE_PRIMARY_ERRATUM_20260925T1403Z.md`](CANDIDATE5_SOURCE_PROVENANCE_PRIMARY_ERRATUM_20260925T1403Z.md).
The exact upstream driver is under
`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`; its Git-object
identity and the patched image source hashes are pinned there. No OCI
`RepoDigest` or build receipt exists. The incorrect historical locator does
not change smoke results; full source provenance remains blocked.

The next producer candidate must repair the three assumed-shape `dzf(:)`
lower-bound sites and affected inherited Courant indexing with one-halo,
nonuniform-spacing compiled tests. Strict source parsing, raw evidence, the
six-ledger independent auditor, scientific limits, source supervisor and exact
release review also remain open under proposed contract v0.2. The candidate5
image and patch remain immutable; do not repeat this smoke or use it to bypass
the source gates.
