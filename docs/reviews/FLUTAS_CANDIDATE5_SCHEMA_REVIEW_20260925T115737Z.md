# Candidate5 observability schema review — 2026-09-25 11:57:37 UTC

**Disposition: ACCEPT as the implementation interface only.** This Astra Max
read-only review does not accept the producer or analyzer, approve B1-pre,
B1-runtime, B2, the provisional `0.2` margin, any physical/numerical claim, or
source CFD/GPU execution.

The exact artifact reviewed was
[`FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md`](../../experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md).
Opening and closing SHA-256 both matched:

`4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`

Astra independently checked array membership/ranges and expected counts,
bottom-return summation order, the pinned `chkdt_tw` arithmetic and actual
staggered operands, guard and overflow failure rules, early-stop joins and
retained prefixes, manifest hash subjects and JSON types, and zero-row/failure
sentinels. No blocking ambiguity remains in the reviewed interface.

Two editorial issues were recorded as nonblocking: a duplicated introductory
fragment near lines 158–161 and reuse of `k` for both spatial and schedule
notation near lines 73–77. The interpretation is unambiguous. The candidate
producer and analyzer still require exact code/evidence review and runtime
serialization proof. Source arithmetic was statically compared to immutable
FluTAS commit `598210616bebd51f7d51f61455f196e6f3479916`; cross-compiler
reproducibility and physical validity were not tested.

The independent reviewer did not edit files, build, run tests, invoke a solver,
or use the GPU. See the Astra Max handoff in the project agent log for its
source-file hashes and detailed line-by-line findings.
