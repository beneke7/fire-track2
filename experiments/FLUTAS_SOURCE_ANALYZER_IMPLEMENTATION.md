# FluTAS candidate5 source analyzer implementation

**Status: implementation-only, offline synthetic fixtures.** The analyzer is
aligned to primary-frozen observability schema revision 1.2, SHA-256
`4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`, and
manifest identifier `candidate5-run-manifest-v2`. The schema remains pending
independent code and numerical review. No source solver, build, mesh, GPU,
production manifest, or CFD run was used.

The CPU-only parser requires the exact v1.2 JSON fields and canonical sorted,
compact UTF-8 JSON bytes. It enforces the three exact CSV headers and canonical
UTF-8/LF representation, finite-number grammar, nonfinite first-failure
tokens parsed independently for both sides of each first failure, enums, unique
keys, group completeness, and ordering. Every finite decimal must fit in
binary64 without underflow to zero. Phase VOF stages contain only `alpha`;
`pre_momentum` contains `alpha`, `rho`, and `mu`. The timestep table is joined
only by `state_index`. Normal row totals are checked as 672 phase, 516 velocity,
and 15 timestep records. For the declared early guard/audit stops, the analyzer
derives exact key sets and row totals from the manifest stop reason, indices,
and stage, including the `initial_u0` no-time-row exception and endpoint-audit
state `K+1` exceptions.

The analyzer pins the accepted schema digest and externally supplied candidate,
image, case, staged-input, analyzer, timestep-input, scan-count, slot-mask, and
schedule contracts. It verifies each pinned scan count against the declared
face/class/component domain and checks every first-failure location against
that domain, including slot membership after velocity periodic wrapping and
the W normal-face plane. It recomputes the pinned AB2 restriction from the v1.2
round-trip binary64 spacing/inverse arrays in source operation order, including
`dlmini`, the capillary branch, zero-advection fallback, timestep ratio, and
guard. Reciprocal inputs are range-checked and required to have a nonzero finite
reciprocal before division. Finite intermediate overflow or domain errors
return deterministic structural codes (`TIMESTEP_ARITHMETIC` or
`ANALYZER_ARITHMETIC`). Exact binary64 equality is used after decimal parsing;
there is no post-hoc numerical tolerance. `dtic_raw` is supplied by the producer
summary; successful runtime U/V/W arrays are not serialized, so this analyzer
does not claim to recompute that rate from runtime fields.

For phase and velocity audit summaries, finite first-failure values are compared
after binary64 conversion. A counted mismatch must differ in binary64, its
subtraction must remain finite, and `max_abs_error` must equal the first-pair
absolute error when `mismatch_count == 1` or be at least that large when the
count is greater. When the first pair contains an allowed nonfinite token, the
finite-pair bound is not applied; this preserves valid mixed finite/nonfinite
audit stops while still requiring the declared summary counts and error range.

The test bundle is synthetic. It defines four disjoint 10×24 masks on the
frozen 160×84×40 grid, 14 active intervals, and derives test scan counts for
interior and padded faces. Those masks and inputs are not read from a real
`source-boundary.in`, candidate receipt, case directory, or producer output.
At the analyzer API, expected scan-cell counts, slot masks, active schedule
indices, and timestep inputs arrive as separate pins. This implementation does
not parse staged solver files or prove that those pins came from the exact
bytes in `input_sha256`; the missing `source-boundary.in` grammar remains a
primary-owned companion interface. No grammar was added or inferred here.
Production bundle acceptance therefore remains closed until that interface is
frozen and reviewed. The `input_sha256` map is compared with its external pin,
but the analyzer does not walk a case directory to check symlinks or staged
files.

Physical limits remain unfrozen. A structurally complete bundle can establish
only that its serialized evidence is well-formed and internally consistent.
An audit/guard stop is preserved as evidence failure. The overall decision is
always `not_adjudicated`; the module cannot emit scientific or execution
`PASS`. It applies no mass, momentum, Courant, divergence, pressure, or resource
threshold.

Focused offline checks used one CPU process:

```text
ulimit -v 4194304
.venv/bin/ruff check src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
.venv/bin/ruff format --check src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_local.py --threads 1 --timeout 60 -- .venv/bin/pytest -q -p no:cacheprovider tests/test_flutas_source_analyzer.py
PYTHONPYCACHEPREFIX=/tmp/flutas-source-analyzer-pycache-20260925 .venv/bin/python -m py_compile src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
```

Latest output:

```text
All checks passed!
2 files already formatted
.........................................................                [100%]
57 passed in 17.97s
```

The final `py_compile` command exited 0 with no output. These commands ran
sequentially under a 4 GiB virtual-memory limit; the pytest launcher capped its
thread environment at one.

The fixtures cover a valid normal bundle; exact normal row totals; guard,
phase-stage, velocity-stage, endpoint, and initial-velocity controlled
prefixes; missing, duplicate, orphan, unknown-stage, and invalid-face rows;
independent first-failure token parsing; invalid face, slot-mask, and W-plane
failure locations; NaN/Inf handling; empty-class counts and sentinel semantics;
binary64-equivalent value rejection, subtraction overflow, underreported and
overreported singleton maxima, and valid single- and multiple-mismatch
summaries for both audit tables; mixed finite/nonfinite audit stops with both
finite-first and nonfinite-first pairs;
inconsistent manifest/scan counts; duplicated or noncanonical JSON; wrong
schema and input pins; missing/tampered output hashes; timestep
intermediate/inverse tampering; finite binary64 intermediate overflow,
out-of-range decimal rejection, and reciprocal overflow; zero-rate and
capillary branches; nonfinite timestep rejection; and resource record types.
These checks validate analyzer behavior on generated in-memory bytes only. They
do not validate FluTAS or authorize source execution.

## Handoff hashes

The parked v1.1 opening files are identified in the read-only Warden checkpoint
[`PROJECT_WARDEN_20260925T111712Z.md`](../docs/reviews/PROJECT_WARDEN_20260925T111712Z.md):

| File | Opening SHA-256 | Closing SHA-256 |
| --- | --- | --- |
| `src/aerial_drop/flutas_source_analyzer.py` | `42479b283fd738ac3a3de35c7fe977d4a9978d18ca9ea69b279bc3038046e443` | `77c94d49c78a0581bb7c2a5f4f63cf85d22eea187133c92f604ba1796e103868` |
| `tests/test_flutas_source_analyzer.py` | `7c6a1aaf75c8b6bb258279745d639a83e90e73b2dea1e229605551198921d4d4` | `a2ab5203f13a84fbc1868bf634dda21375be6981b4eaa3ebbef31c74b9f4b7d1` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `18dbaee2a3f9196fbb1dee7e9def7e454e10c7bd1e534493aadff87675904782` | The final note digest is reported in the implementation handoff. |

The M1/M2/F1 repair hashes and focused verification output are recorded in the
timestamped review handoff note for this repair.
