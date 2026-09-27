# Candidate5 staged-input, conservation and launch contract

**Primary draft v0.1 — design only, not independently reviewed or accepted.**
This companion contract does not change the accepted candidate5 observability
schema v1.2, approve B1-pre/B2, or authorize a source-enabled run. It defines
the missing interfaces and evidence that must be frozen and reviewed before
source-run release. Source CFD remains closed.

The parent interface is
[`FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md`](FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md),
SHA-256
`4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`. Schema
v1.2 governs three new diagnostic tables and the run manifest. This contract
adds independent input interpretation, six inherited output ledgers,
quantitative-limit disposition, immutable local image identity, and launch
supervision. It must receive an exact Astra Max review after its referenced
producer/analyzer successors and all open limit decisions are addressed.

## Staged-input identity and source-boundary grammar

The manifest `input_sha256` object must contain the exact byte hashes of every
regular staged solver input under the canonical case root. The current
candidate5 interface admits exactly `dns.in`, `vof.in`, and
`source-boundary.in`; require canonical POSIX relative names, unique files,
no symlinks or hard links, no omitted or extra solver inputs, and a read-only
staged mount during execution. Hash inputs before launch and verify the staged
bytes again on completion. A run must carry the actual input files and manifest
in its immutable evidence directory.

For `source-boundary.in`, the reviewed grammar will use ASCII bytes, LF line
ends, one required final LF, no BOM, no blank/comment records, one record per
physical line, and no extra tokens or trailing records. Whitespace may separate
tokens within a record. Integer tokens use base-10 syntax; real tokens use
finite decimal syntax with an optional `e`/`E` exponent. Reject NaN, infinity,
overflow, underflow to zero for a required nonzero value, D exponents, and
unconsumed text. The independent parser must produce one typed record object;
the compiled solver reader must consume the same complete record count and
reject every extra value. Exact accepted fixture bytes remain hash-pinned
below; this grammar does not silently make arbitrary new inputs eligible.

The records are, in order:

| Record | Fields | Token count |
| --- | --- | ---: |
| 1 | `slot_count` | 1 integer |
| 2 | `nx ny nz` | 3 integers |
| 3 | `step_on step_off` | 2 integers |
| 4 | `dt_s` | 1 real |
| 5 | `source_u source_v source_w` | 3 reals |
| 6 | `background_u background_v background_w` | 3 reals |
| 7 | `gravity_x gravity_y gravity_z` | 3 reals |
| 8 | `slot_short_x slot_long_y gap_x gap_y` | 4 reals |
| 9 through `8+slot_count` | `i0 i1 j0 j1` for each slot in input order | 4 integers per slot |
| final | `fixed_step_factor` | 1 real |

There are exactly `9 + slot_count` records: 9 for dry, 10 for one slot, and
13 for four slots. Validate `slot_count` in `{0,1,4}`, the fixture grid
`160 84 40`, and noninverted, in-bounds, nonoverlapping masks. The one-slot
rectangle is `74 79 2 41`. Four-slot rectangles, in schedule/accumulation
order, are `74 79 2 41`, `82 87 2 41`, `74 79 44 83`, `82 87 44 83`.
The current diagnostic uses a zero-based half-open schedule: dry has
`[0,0)`; positive source fixtures have `[2,12)` over 14 planned intervals.
The parser derives the exact mask union and every state/interval source
membership from the staged records, never from an analyzer caller's expected
plan argument or a case name alone.

The accepted fixture map below binds case ID to exact inputs. `dns.in` and
`vof.in` hashes are independently parsed as well: duplicated grid, fixed-step,
14-step schedule, no-restart/start-time, boundary, fluid, gravity and empty-box
values must agree with the source record and v1.2 rules. A case ID selects a
fixture only after hashes and parsed semantics both match.

| Case | Disposition | `dns.in` SHA-256 | `source-boundary.in` SHA-256 | `vof.in` SHA-256 |
| --- | --- | --- | --- | --- |
| `dry_four` | Positive baseline, after all source gates | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` | `f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `quiescent_one` | Positive one-slot check | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` | `761dfef4cf386ae122344fc3b9b8e0fa3fb6e468ba79a7235224389c779b9b13` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `quiescent_four` | Positive four-slot check | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` | `f4d904ae10986f6fa6ff872f76435bb6e4cdb0b8a9c7707ff5307f911410f5b7` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `dry_crossflow` | Expected-negative U0 timestep-guard fixture; never run on the GPU with the frozen input | `574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7` | `7bbb8cdd01a06ae6bcbfe47fb448d9cf5a61f3bb2ae82b7a83c6b688be1024db` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `crossflow_four` | Expected-negative U0 timestep-guard fixture; never run on the GPU with the frozen input | `574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7` | `55f485ce507b8d19fa05c4324308028696ef50ddfe3faec2bab6b1a242e201ec` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |

The bytes above match the archived fixture hash inventory
`containers/flutas/candidate5/cases/source_boundary/SHA256SUMS`; the manifest
still records the actual per-run file hashes. The independent parser must
derive `state_count=15`, `interval_count=14`, `dt=1e-4 s`, `time_start_s=0` for
these no-restart fixtures, geometry and masks from input bytes. It must
recompute expected row keys/counts and stop-prefix expectations from the
derived schedule, masks and v1.2 stage order, including zero-scanned classes.
For v1.2, `timestep-restriction.csv.time_s` uses the primary-frozen diagnostic
clock `time_start_s + state_index*dt`; the accumulated AB2 solver clock is
preserved only in its native solver output and is never mislabeled as this
field. The 42-element runtime `dzc/dzf/dzci/dzfi` arrays remain actual captured
operands; bind each to the exact candidate build and independently check the
compiled initialization/recriprocal operation order.

## Candidate and image provenance

Before a source bundle can be accepted, `candidate-build.json` must be
immutable and included in each run archive. It must bind the upstream commit
and source hashes, patch hash, build-script/tool hashes, compiler/version/flags,
build command, executable SHA-256, and exact image identity. The v1.2
`candidate_sha256` hashes the receipt bytes; `image_digest` is a true lowercase
SHA-256 OCI image-manifest digest. A Docker image ID is a configuration digest,
not an OCI manifest digest, and must never be inserted in that field.

The primary selects an **offline local OCI layout** as the identity route; no
registry upload is required. The build task must export the built local image
to a deterministic OCI image layout, compute and record the exact OCI manifest
digest, and verify that the layout's config blob digest equals Docker's local
image ID and that every layer digest/config rootfs diff ID matches. The receipt
records both identities explicitly. At launch, the wrapper verifies the
receipt hash, OCI manifest/layout, local image ID, image entrypoint and mounted
candidate patch before starting. Any conversion or identity mismatch is a hard
pre-run failure. If a validated local OCI layout cannot be produced, stop and
submit a prospective schema amendment describing a local-image-only identity;
do not weaken v1.2 or relabel an image ID.

## Inherited conservation and velocity outputs

The six existing ledgers remain separate from the frozen three-table v1.2
subcontract. Their exact headers, numeric token format, index meaning, unit,
normal-completion row counts, controlled-stop prefixes, and inter-table joins
must be pinned by the implementation amendment. At minimum, the independent
auditor must verify these quantities:

| Artifact | Required meaning and independent checks |
| --- | --- |
| `source-flux.csv` | Per interval and slot: requested geometric volume and mass from exact mask area, schedule, `|w_source|`, `dt`, and `rho_l`; applied inward phase volume/mass from actual geometric flux; requested vector momentum from requested mass × requested velocity; applied vector momentum from phase mass flux × the declared staggered face interpolation; source-face reverse/outward volume. Check slot symmetry and sums independently. |
| `source-offmask.csv` | Per interval, z+ inward and outward geometric liquid volume outside the union of all source masks. Inward off-mask flow must meet its separately reviewed limit; outward flow remains recorded, not deleted. Recompute membership with periodic mapping from parsed masks. |
| `rate-check.csv` | Per interval, total measured top liquid flow, analytic scheduled top flow, residual, bottom-return volume flow, expected return and residual. Compare against sums reconstructed from slot rows and the frozen expected schedule. |
| `boundary-ledger.csv` | Per completed state/interval, inward and outward geometric liquid volume on all six faces, with outward-positive sign convention defined once. Recompute face areas and sums from the declared staggered/geometric flux representation; no face may be silently omitted. |
| `mass-ledger.csv` | At each state/time: liquid inventory `rho_l*sum(alpha*cell_volume)`, initial inventory, cumulative all-boundary liquid in/out mass, signed residual `M_in-M_out-(M_box-M_0)`, net boundary liquid volume, and per-face in/out mass. Cross-check every per-face mass against `boundary-ledger.csv*rho_l`; do not count cumulative handoff flux as stored mass. |
| `velocity-audit.csv` | At each audited state/time: total cell count, global and interface advective Courant maxima, interface count/defined flag, top/bottom rates, net boundary volume flux, integrated divergence, closure, max absolute divergence, volume-integrated absolute divergence, and per-face outward velocity flux. Independently reproduce face centering, cell divergence, cell volumes, summation order and joins to U-state/interval. These are diagnostics, not acceptance limits. |

Summary CSV agreement alone cannot establish source or conservation correctness.
The exact-run auditor needs sufficient raw evidence to independently recompute
each quantity: retain compact per-step face-phase flux arrays, liquid fraction
inventory fields, and velocity fields (or a prospectively reviewed lossless
diagnostic representation), keyed to the mesh, source state and completed
interval. Hash every raw artifact. If the retained raw state is too large,
reduce the fixture/field set only through an independently reviewed protocol
amendment before launch; do not accept producer summaries as their own proof.

For each output, the analyzer requires exact header/column order, finite
binary64 values on a pass, correct token count, unique and ordered keys,
valid state/interval joins, complete expected rows including empty classes,
and exact stop-prefix completeness. A failure run retains complete flushed
rows through the first failed state and a nonzero exit; malformed or truncated
evidence is a structural failure, not an audit stop. Recompute reported
residuals and ratios from primitive operands instead of trusting a residual
column.

## Limits and solver applicability that must be frozen

No source acceptance number is approved by this draft. The primary and
independent scientific reviewer must freeze formulas, units, sign conventions,
thresholds, uncertainty/tolerance arithmetic and pass/inconclusive/fail
precedence for every row below before source launch:

| Quantity | Required disposition before launch |
| --- | --- |
| Per-slot and total scheduled dose error | Preregister requested/applied volume/mass comparison, accumulation order and numeric uncertainty; the candidate `1e-10` symmetric arithmetic check and any `0.1%` budget are not automatically physical acceptance limits. |
| Top/bottom return and off-mask flow | Freeze relative/absolute tolerances, active/inactive behavior, reverse-flow policy and how a zero expected rate is tested. |
| All-face mass closure | Freeze the residual normalization, denominator/zero-mass rule, per-step and cumulative limit, and relation to independently reconstructed fields. |
| Continuity/divergence | Freeze `integrated_divergence`, net-boundary closure, `max_abs_divergence`, and volume-integrated absolute divergence limits with units and reduction error budget. |
| Stability and boundedness | Freeze global/interface Courant limits; raw alpha bounds and absent-phase leakage; timestep guard behavior and classification of expected-negative U0 cases. |
| Momentum | Freeze component-wise requested/applied momentum error and the exact staggered interpolation/reduction method. |
| Pressure/velocity solve | The pinned route is direct FFT plus tridiagonal pressure solve, not an iterative residual-controlled solver. Any iterative residual limit is `not_applicable` only if exact candidate review confirms the route; require finite solver completion and separately chosen divergence/closure limits. |
| Resource and completion | Freeze CPU/GPU/RAM/VRAM/disk/wall ceilings from a measured eligible pilot, sampling cadence, final physical time, checkpoint/restart rule and whether any controlled failure counts as a completed attempt. |

The source gate's known frozen 50 m/s crossflow fixtures fail the U0 guard
(`dt/dtmax=0.20003689638113265` versus `0.2`). Treat them only as expected-
negative host/parser fixtures. The current positive sequence is quiescent
`dry_four` → `quiescent_one` → `quiescent_four`, one GPU case at a time after
all preregistered checks pass, stopping at the first failure. Positive
crossflow requires a prospective, independently reviewed amendment preserving
or redeclaring pulse, dose and horizon.

## Launch envelope and required fake-executable checks

The source launcher must stage a fresh immutable case copy, verify exact case
and binary identities, make staged inputs read-only, acquire the shared GPU
lock through `scripts/run_local.py`, record one MPI rank on one RTX 5090,
respect two reserved CPUs and the shared 18-CPU ceiling, and enforce reviewed
per-run RAM/VRAM/disk/wall limits. Initial source diagnostics use one GPU and a
resource ceiling frozen after exact candidate review; do not extrapolate from
the source-disabled smoke as a source-boundary performance or scaling result.

The wrapper records command, start/end, UTC time, source revision/dirty state,
candidate receipt/image IDs, input and analyzer hashes, device/driver,
environment, exit code, stop tuple, solver logs, raw diagnostics, resource
samples, output hashes and independent report. It fails closed on changed
inputs/patch/image, missing or header-only output, unknown/early termination,
fatal solver text with exit 0, wrong final physical time, inconsistent stop
tuple, sampling gaps, exceeded resource limits or manifest mismatch. It
preserves failed attempts and never reuses/overwrites a run directory.

Before exact launch review, a fake-executable suite must exercise at least:
normal completion; valid guard/audit stop with complete prefix and nonzero
exit; zero exit with fatal/abort marker; nonzero unclassified exit; wrong final
time; missing/header-only CSV; wrong input or image hash; source input missing
in source mode; source input present in source-disabled mode; timeout/OOM;
resource-sampler failure; and attempt to start the next dependent case after a
failure. Each negative must stop before any later GPU stage. The existing
candidate5 locked regression remains a different source-disabled check.

## Acceptance sequence and unresolved owners

1. **Luna producer successor:** strict input/parser semantics, v1.2 output
   fixes, actual timestep operands and compiled-output-to-independent-analyzer
   tests. Owner is the candidate5 producer task; no source run.
2. **Luna analyzer successor:** derive expected rows from actual staged bytes,
   close malformed-value/location/overflow findings, and independently audit
   all six inherited outputs. The current analyzer worker addresses M1/M2 only;
   broader source-input and conservation acceptance requires a separate bounded
   assignment after this contract is frozen.
3. **Primary provenance tooling:** implement local OCI layout export and
   `candidate-build.json` receipt, preserving both OCI manifest and Docker
   configuration identities; exact build/receipt review.
4. **Primary and scientific reviewer:** freeze every numeric limit, stop rule,
   and pressure-residual applicability with source/analytic rationale. Do not
   copy tolerances from P1/P0 or adopt values after seeing a run.
5. **Luna launcher task:** only after this contract is reviewed, implement the
   independent raw-field auditor, six-ledger analyzer, staged read-only
   binding, manifest integration and fake-executable suite in disjoint files.
6. **Astra Max exact review:** review exact input files, parser, candidate
   receipt/image, producer, analyzer, numeric limits and fake-run evidence as a
   single hash-pinned bundle. Only after approval may the primary queue the
   smallest GPU source sequence, one case at a time.

No user-provided measured inputs are needed for this implementation contract.
Measured built-Restás geometry and synchronized flow/pressure/valve traces are
still required for a built-system claim; E4/E5 raw cup data and matched release
metadata remain later field-validation dependencies.
