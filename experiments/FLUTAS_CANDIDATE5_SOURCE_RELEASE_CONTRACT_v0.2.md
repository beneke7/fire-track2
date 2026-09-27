# Candidate5 staged-input, conservation and launch contract

**Primary successor contract v0.2 — design proposal; exact review and primary
disposition pending. It does not accept B1-pre/B2 or authorize a source run.**

This document amends and supersedes only the conflicting provisions in
[`v0.1`](FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT.md), SHA-256
`09419b40c4cfd4f6262f45a2ed184d303efb68adcfa86dfd451de52f0f397112`. All
other v0.1 input hashes, fixture identities, schedule/mask definitions,
quantity tables, and acceptance dependencies remain in force. Where text
conflicts, v0.2 controls. v0.1 remains the historical draft reviewed as
**REVISE**, not a second active contract.

The frozen parent interface remains
[`candidate5 observability schema v1.2`](FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md),
SHA-256 `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`.
No amendment here changes its three-table manifest. This proposal incorporates
the exact findings in
[`Astra's v0.1 review`](../docs/reviews/FLUTAS_SOURCE_RELEASE_CONTRACT_REVIEW_20260925T1331Z.md)
and Warden 11. Its controls must be independently reviewed against exact
producer, analyzer, provenance-tool and launcher hashes before any source run.

## H1 — Output existence, empty files, and exact stop prefixes

All six inherited files must be created before any controlled stop, with the
exact header defined by the producer interface, UTF-8/ASCII-compatible bytes,
LF record ends, and a final LF. A legal zero-row file consists of its header
only; a missing file, wrong header, truncated row, or incomplete required
prefix is structural failure. The normal dry run has zero `source-flux.csv`
rows because it has no slots. It still has all 14 interval rows in
`source-offmask.csv` and `rate-check.csv`. The initial U0 velocity-audit stop
legally has header-only inherited and v1.2 tables. Empty slot classes in v1.2
remain represented by their required zero-count rows; a nonexistent dry-run
slot is not an empty declared slot class.

For `S=slot_count`, `K=completed_interval_count`, and `N=14`, inherited
interval keys are `0..row_count-1` with slots in input order; state keys start
at 0. Counts below exclude headers:

| Event | `source-flux` | `offmask` | `rate-check` | `boundary` | `mass` | `velocity-audit` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Normal completion | `N*S` | `N` | `N` | `N+1` | `N+1` | `N+1` |
| Failed `initial_u0` audit | 0 | 0 | 0 | 0 | 0 | 0 |
| Finite timestep guard at `U_K` | `K*S` | `K` | `K` | `K+1` | `K+1` | `K+1` |
| Failed velocity `pre_vof` in K | `K*S` | `K` | `K` | `K+1` | `K+1` | `K+1` |
| Failed phase `pre_vof_x/y/z` in K | `K*S` | `K` | `K` | `K+1` | `K+1` | `K+1` |
| Failed phase `pre_momentum` in K | `(K+1)*S` | `K+1` | `K+1` | `K+1` | `K+1` | `K+1` |
| Failed velocity `projection_override` or `corrected_endpoint` in K | `(K+1)*S` | `K+1` | `K+1` | `K+2` | `K+2` | `K+1` |

The final row intentionally has boundary/mass state K+1 but no velocity-audit
row for that state. `completed_interval_count` does not alone determine all
prefixes. Directional raw flux may have been produced before a phase-stage
failure even when the interval summary row is absent; the raw manifest records
each stage as reached/not reached and hashes every artifact actually emitted.

A rate-pair abort after it writes rate row K is an **unclassified failed
attempt**, not one of the three v1.2 controlled-stop reasons. Its six inherited
counts are exactly `K*S, K, K+1, K+1, K+1, K+1`: rate row K is present, while
the interval-K offmask/source rows and state-K+1 inventory are absent. Preserve
the nonzero exit and evidence; do not relabel it. Add a controlled reason only
through a versioned schema amendment and independent review.

The v1.2 files also always exist. Use its exact three-table prefix rules: an
`initial_u0` failure has header-only phase and timestep files; a finite U0
guard stop has initial U0 diagnostics and a `guard_pass=false` row but no
transport-stage rows; later guard/audit stops have only the rows/groups
prescribed for their event in schema v1.2. Derive each table's prefix from
`stop_reason`, stop indices, stage ID, and producer call order. Never apply a
blanket “header-only means failure” rule.

CPU acceptance tests must cover every row above, every controlled stop stage,
dry normal completion, each one-row truncation at each prefix boundary, the
rate-pair abort, malformed headers, and valid empty versus missing files. A
fake-run invocation counter must prove no dependent case starts after any
failure. A failed/unclassified attempt is retained and cannot advance the
sequence.

## H2 — Freeze the inherited quantities, clocks, and joins

The inherited `rate-check.csv` quantities retain their implemented meanings
until a reviewed producer amendment explicitly changes code and header:

* The stored top rate is inward **phase volume on configured masks only**,
  divided by `dt`. It omits off-mask inflow and top outward flow.
* The stored bottom rate is a compensated signed sum of **total-volume** face
  flow `-w*area`, including air. It is not a sum of positive bottom liquid
  outflow terms.
* Independently reconstructed total top inward liquid rate is
  `(sum(slot_inward_volume)+offmask_in_volume)/dt`; top outward is
  `(sum(slot_reverse_out_volume)+offmask_out_volume)/dt`. Net flow is a separate
  derived quantity. Do not equate these with the stored masked rate.
* Slot rows and the stored rate use different floating-point grouping. Compare
  them with a preregistered reduction/error budget; algebraic equivalence does
  not imply bitwise equality.

The following keys and meanings are binding. Any producer change requires a
new contract/version and fresh compiled evidence:

| Output | Index/time and quantity meaning |
| --- | --- |
| `source-flux`, `source-offmask`, `rate-check` | Transport interval `k`; source membership is the half-open schedule `[2,12)`. Geometric flux already includes `dt`; volume is flux × area and rate divides by `dt` once. |
| `boundary-ledger` | Initial state 0 and phase inventory states k+1 after advection. `completed_state_index` does not mean momentum/projection completed. In/out columns are per-interval nonnegative magnitudes, not cumulative signed flux. |
| `mass-ledger` | Same phase-inventory states. `time_s` is the native accumulated solver clock. Per-face mass and net boundary volume are per interval; only explicitly cumulative in/out mass columns accumulate. Residual is `M_in-M_out-(M_box-M_0)`. |
| `velocity-audit` | Initial U0 and successfully corrected endpoint U(k+1), after that endpoint stage audit. `source_profile_interval` is the installed profile's state index (k+1 at an endpoint), not the just-consumed k. Top/bottom values are positive parts of net velocity-face sums. |
| v1.2 `timestep-restriction` | Diagnostic clock `time_start_s + state_index*dt`; retain the primary-frozen index clock. It is distinct from native accumulated solver time. |

Joins use integer state/interval keys and exact producer call order, never a
post-run time tolerance. Final-time checks separately bind planned intervals,
completed intervals, completed states, diagnostic index time, and native
solver time. CPU fixtures must include both pulse edges, reverse flow,
off-mask-only flow, and a multi-state AB2 clock example.

## H3 — Exact source lexer and separate `dns.in`/`vof.in` parsing

`source-boundary.in` is ASCII, LF-only, exactly one final LF, no BOM, no blank
or comment lines, one physical record per declared record, and no bytes after
the final record. Only space and horizontal tab separate tokens. Integer
tokens match `-?(0|[1-9][0-9]*)`, then must fit signed 32-bit default Fortran
integer range. Real tokens match
`[+-]?(?:(?:0|[1-9][0-9]*)(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?(?:0|[1-9][0-9]*))?`.
No commas, slash termination, repetition/null values, comments, D exponent,
NaN/Inf spelling, or trailing tokens are admitted. Convert each real token
once to IEEE binary64; reject conversion overflow, nonfinite results, and any
mathematically nonzero decimal that converts to zero. Subnormal nonzero values
are lexically allowed, then field-domain checks decide whether that value is
permitted. Each physical line has the exact token count in v0.1 and the file
has exactly `9+slot_count` records. The independent parser and compiled reader
must return equal typed values, with no unconsumed text or record.

`dns.in` and `vof.in` use **separate fixture grammars**, not the source-file
grammar. Their current allowlisted bytes retain inline `!` comments, Fortran
logical tokens (`T`/`F`), character identifiers, and their declared typed
records. For this release only the exact five fixture hash triplets listed in
v0.1 are eligible. The independent parser strips only an inline `!` comment
after ASCII decoding, preserves physical record order, requires the exact
fixture line count and record token counts, and parses each record using its
field types. Blank records, CRLF, BOM, continuation, comma/slash/null/repeat
syntax, or added records are rejected. Before eligibility it checks the
duplicated grid, fixed-step mode/value, 14-step stopping mode, AB2 time scheme,
no-restart/start-time, boundary types/values, fluid and empty-VOF setup,
forcing, gravity, and extra-input absence against the independently parsed
source record and v1.2 derived schedule. A changed but syntactically valid file
is not an eligible fixture unless a prospective reviewed amendment adds its
exact hash and semantics.

CPU differential tests cover exact accepted files; short, long, extra and
missing records; extra/missing tokens; comma/slash/repetition/null; blank and
comment source lines; CRLF/BOM; D exponent; nonfinite, overflow, underflow;
integer overflow; overlapping/out-of-grid masks; and every duplicated-field
mismatch. A parser test never authorizes a changed fixture for solver use.

## H4 — Correct the production lower bound for vertical spacing

The inherited defect remains a **source-execution blocker** until a separately
reviewed producer patch closes it. Production passes `dzf(0:nz+1)` to
assumed-shape `dzf(:)` dummies in boundary-flux, inventory and velocity-audit
helpers. The dummy's default lower bound 1 maps helper `dzf(k)` to caller
`dzf(k-1)`. The inherited Courant diagnostic also indexes `dzf(k)` and is
affected. Fix every affected call/dummy consistently, preserving the intended
caller mapping for the production one-halo allocation and host harness. Do not
compensate by teaching the independent auditor the shifted mesh.

The fix requires compiled tests for one-halo production and harness layouts,
with nonconstant/nonuniform spacing values, independently calculated x/y face
areas, cell volumes/inventory, velocity face flux/divergence, and inherited
Courant terms. Include a deliberate shifted-index negative control. The v1.2
timestep bound separately uses captured `dzfi/dzci` operands and its frozen
source-order multiplication; document and test that operation order instead
of asserting equality with the inherited division-by-`dzf` diagnostic. Exact
patch/build review is required before any source run. Candidate5's current
source-disabled smoke does not close this defect.

## H5 — Canonical ledger paths and raw-evidence manifest

The six native files are opened under prefix `data/restas`; their native paths
are `data/restas_source-flux.csv`, `data/restas_source-offmask.csv`,
`data/restas_rate-check.csv`, `data/restas_boundary-ledger.csv`,
`data/restas_mass-ledger.csv`, and `data/restas_velocity-audit.csv`. The
immutable run bundle copies each original byte stream to the six canonical
names without changing bytes, records both native and canonical paths, hashes
both, and verifies byte identity. Headers and column order are exactly those
in the reviewed candidate patch/producer receipt. Inherited numeric fields
retain the explicit `ES24.16E3` padded representation; the separate analyzer
must trim only surrounding ASCII space, enforce one numeric token per field,
and reject internal whitespace, extra fields, nonfinite values, and malformed
exponents. This does not relax v1.2's token grammar.

Add a separately versioned `source-evidence-manifest.json`; do not add keys to
the frozen v1.2 `files_sha256` or `row_counts`. Its canonical byte encoding is
UTF-8, sorted object keys, compact separators, no NaN/Infinity, and one final
LF. It binds exact bytes/hashes for the v1.2 manifest, this contract, candidate
receipt/image manifest, staged inputs, six native and canonical ledgers, raw
files, auditor, and source launcher. Each raw artifact entry declares:
relative path; byte size and SHA-256; role; state, transport interval and
solver stage; face/component; actual inclusive index bounds and halo widths;
shape, dtype, endian/byte order, units and sign; capture routine/source hash;
mesh-spacing/build identity; and whether the artifact is required, captured,
or not reached at the recorded stop prefix. Reject symlinks, hardlinks, path
escapes, duplicate roles/keys, unlisted bytes, missing expected files and
hash/size/shape mismatches.

Capture directional phase-flux arrays immediately after each x/y/z sweep,
before the shared flux array is reused; capture source-face velocity operands
at the exact momentum-flux operation; capture liquid-fraction inventory and
the U/V/W states used by divergence and Courant stencils. At minimum retain
the pre-clip and post-clip alpha states at each of the three VOF clipping
sites (`dvof1`, `dvof2`, final `vof`), keyed to the stage; if the implementation
does not retain these, narrow raw-boundedness and clipping claims explicitly
before launch. Define absent-phase cells, stages, thresholds, and zero rules
as separate pending scientific limits. Raw files for stages reached before a
stop are kept and hashed; manifest entries mark later-stage artifacts
`not_reached`, never silently absent.

An independent auditor reads raw bytes and staged input, not producer summary
helpers, to reproduce all six ledgers, phase bounds, face signs, geometric
areas, inventory, staggered interpolation, divergence, Courant and integer
joins. Synthetic tests must expose sign, halo, staggering, mask/offmask,
clipping, zero-denominator, reduction-order, corruption and truncation errors.
The complete raw output size is measured statically from declared shapes,
dtypes and stop-prefix counts before resource caps are frozen.

## H6 — OCI layout, receipt, and authoritative source provenance

Keep the offline local OCI layout selected by v0.1. Preserve the exact config,
manifest and layer bytes; never reserialize an existing JSON blob to identify
it. Validate `oci-layout` version and `index.json`; exactly select the reviewed
`linux/amd64` image manifest; verify every descriptor's media type, raw byte
size and digest; verify base-to-top descriptor order against config
`rootfs.diff_ids` by hashing each uncompressed layer tar stream; verify config
blob digest equals Docker's local image ID; and bind the actual executable,
patch, entrypoint/command, compiler and build inputs. `image_digest` is the OCI
image-manifest digest, not the image config ID, index digest, archive digest,
or tag. Any generated JSON bytes have a frozen UTF-8, sorted-key, compact,
no-variable-annotation, final-LF encoding; verification hashes archived bytes
as stored.

The immutable `candidate-build.json` receipt records source commit and
authoritative Git object IDs, patch/tool/build-script hashes, compiler/version/
flags/command, executable hash, OCI manifest digest, local image/config ID,
platform and ordered layer descriptors/DiffIDs. The receipt itself is hashed
as `candidate_sha256`. The launcher verifies receipt, layout, local image,
executable, patch and overridden command before invoking the solver. Retain
the exact verified layout and receipt in the run bundle. Test one-bit blob
corruption, wrong size/media type/platform, missing/reordered layers, rewritten
config, index-versus-manifest substitution, altered manifest whitespace,
patch/executable substitution and archive path traversal.

Source provenance must be derived from the pinned upstream Git commit, not a
mutable checkout or directory label. For upstream commit
`598210616bebd51f7d51f61455f196e6f3479916`, the authoritative driver path is
`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`; its exact Git-object
SHA-256 is
`1d6450b3379b9995b0d69c0d8e22d8b038c66446ebd33066cfdffdf799616e22`. The
handoff's `src/main.f90` / `ef4e55d8…` pair came from a dirty checkout and is
not an upstream identity. Preserve that handoff as history, append a corrected
provenance receipt, and re-derive every source-order/build claim from pinned
commit objects plus the exact applied patch. This defect blocks source/build
receipt acceptance; exact review determined it does not by itself alter the
separately scoped local-image source-disabled smoke decision.

## H7 — Prospective bootstrap envelope for the first source diagnostic

Do not require the later 1–3-million-cell pilot to release the first
537,600-cell, 14-interval source diagnostic. Before that first launch, propose
and independently review hard caps from the current machine snapshot, a
static raw/output bound, and a conservative wall allowance; then use observed
usage only to size later cases. The source-disabled smoke is not a source
resource profile.

Primary's 2026-09-25 15:54 UTC doctor snapshot reports 20 effective CPUs (18
shared, 2 reserved), 117.8 GiB available RAM, 236.8 GiB free disk, and one RTX
5090 with 31.8 GiB VRAM. Pending independent resource review, this contract
proposes the first diagnostic envelope: one MPI rank, one application thread,
at most 2 CPU cores total; 16 GiB cgroup memory; 24 GiB VRAM; 40 GiB per-run
disk; and 1,800 seconds wall time. These are prospective stop ceilings, not
scientific tolerances, measured demand, or permission to launch. The primary
must recompute available headroom and exact static output bound immediately
before launch; if either invalidates a cap, revise the proposal and review it
before use. Any resource cap may be lowered; raising one requires documented
headroom/output arithmetic and another exact review.

Sample process/cgroup CPU and memory, GPU memory/utilization, disk use, solver
stage and container state every 1 second. Maximum allowed sample gap is 5 s;
monitoring begins before container creation and ends after verified
termination. Stop on a missing/nonfinite sample, gap over 5 s, or predicted
hard-cap crossing. Resource sampling may overshoot a threshold by no more
than 2 s. On timeout or sampler/resource failure, request graceful stop for
10 s, then kill the container; allow up to 30 s for termination and verify
Docker `State.Running=false` plus no surviving solver/container child before
releasing the shared GPU lock. If termination cannot be verified, retain the
lock and escalate to the primary; never release it because only the client
process exited. Record configured and observed limits separately. Cgroup/RSS
definition, VRAM attribution, disk accounting, sampler failure and child
survival must pass CPU fake-executable/container tests.

## Numerical limits and release sequence

H2's formulas, signs, units, primitive operands, zero rules and row meanings
are frozen interfaces. Numerical acceptance thresholds for dose, momentum,
off-mask/return flow, mass closure, divergence, Courant, raw alpha/leakage,
fixed-step margin, reduction uncertainty and pass/inconclusive/fail precedence
remain explicit **pending** values. Primary and independent scientific review
must justify and freeze every value before source launch; do not adopt a value
after seeing a source result or copy it from P0/P1. The direct FFT plus
tridiagonal pressure route has no iterative residual; `not_applicable` requires
exact candidate confirmation and does not waive finite completion or
independent projection/continuity evidence.

The frozen 50 m/s crossflow inputs remain expected-negative host/parser
fixtures and are not GPU cases. The positive order remains `dry_four` →
`quiescent_one` → `quiescent_four`, one GPU case at a time, stopping at the
first failed check. Each prior case must be independently audited before the
next launches. The first source case remains blocked until exact contract,
producer, analyzer, raw auditor, candidate/OCI receipt, scientific limits,
launcher, resource caps and Astra Max launch review all pass. No source solver,
source GPU trial, B1-pre/B2 disposition, or scientific gate is approved by
this proposal.
