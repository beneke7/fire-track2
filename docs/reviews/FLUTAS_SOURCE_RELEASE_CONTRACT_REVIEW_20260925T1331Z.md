# Candidate5 source-release contract exact review

Configured reviewer: **`gpt-6-astra`, `max`**, independently assigned under the
read-only `general_reviewer` role. Review date: 2026-09-25 UTC. The assignment
allows this memo as the only write; the contract, implementation, fixtures,
shared status and gate records were not edited. No build, container start,
solver, image export, or GPU job was launched.

**Disposition: REVISE the v0.1 contract before freezing its implementation
interface. Source execution and B1-pre/B2 production acceptance remain CLOSED.**
The direction is sound, and the input inventory is correct. The draft contains
executable contradictions about empty outputs and measured top flow, leaves
important prefix/raw-evidence rules unresolved, and makes the initial resource
ceiling depend on a pilot that those ceilings must first permit. A source-read
spacing-index defect also needs a bounded producer repair. This memo approves
no candidate, launcher, numeric threshold, source run, pilot, or scientific gate.

## Exact scope and identities

The contract was hashed before inspection and again after the substantive
review. Opening and closing SHA-256 are identical:

`09419b40c4cfd4f6262f45a2ed184d303efb68adcfa86dfd451de52f0f397112`

The reviewed path is
`experiments/FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT.md`. Its line references
below refer to these held bytes, not a subsequent amendment.

| Read artifact | SHA-256 |
| --- | --- |
| Parent observability schema v1.2 | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| Prior candidate exact review, `FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md` | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
| Current candidate5 `source-boundary.patch`, inspected for call order and inherited helpers | `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7` |
| Candidate5 case `SHA256SUMS` | `a04cbac29baf540bce1c969ad0df2c081b0dc2a3a7a31177606c34602d7978f1` |
| Candidate5 `Dockerfile` | `4c0d59fce78c6b08db5b3a170d7c8577501fd4e067c4cd9729f33466770ac246` |
| Candidate5 `build.sh` | `eb578d8e9641459e3c238231ac33f51a9ae1787ed180943a4f55cc637e04520d` |
| Candidate5 manifest writer | `79219cfb371f94b9949c19617ca454487d630870ff40d4484ee816261ffc6304` |
| Upstream `src/initgrid.f90`, extracted by `git show` at the pinned commit | `87010cb1b014355eb70b299264d5b6cd274ab3248c309906a39ac4a66ab8ca28` |
| Upstream `src/vof.f90`, extracted by `git show` at the pinned commit | `034fb87f481e1fb2da5c2075f36aa39baaf4e2639c9532bc36307ae245ab59dc` |

The source commit is `598210616bebd51f7d51f61455f196e6f3479916`.
The prior exact review covered patch `22c80953e3646dd6ba01ca9aa877a61b8e009c7ebd25d269c1b9aa8c2207d543`;
it does **not** cover the current successor above. This contract review does
not resolve or re-review all producer/analyzer findings from that earlier memo.
The current patch hash was rechecked during this review and remained unchanged.
Working directories called “pristine” were not trusted by name: upstream
operation-order evidence uses the exact commit objects.

Sources read also include `AGENTS.md`, `docs/WORKFLOW.md`, `docs/COMPUTE.md`,
the experiment plan, current status, the primary time-interface decision,
candidate input files, helper/test code and relevant manifest-writer code.
Preliminary observations supplied in the task were treated as leads; the
findings below were checked against these sources.

## H1 — Empty-output and stop-prefix rules conflict with valid cases

Contract lines 143–148 and 191–203 need a stage-specific artifact policy.
The blanket rejection of a “missing or header-only output” at line 192 would
reject both a normal dry baseline and explicitly conforming v1.2 stops.

`restas_source_record_flux` loops over `1..slot_count`
(`source-boundary.patch:831–863`). With zero slots, `source-flux.csv` has zero
data rows for a normal dry run. This is different from v1.2's required rows
for empty scan classes: a nonexistent slot is not a declared slot class.
The initial velocity audit runs at patch lines 97–101, before initial
inventory/velocity ledgers at 112–115 and the U0 timestep evaluation at
124–126. An `initial_u0` audit stop therefore has only header rows in all six
inherited ledgers, and header-only phase/timestep tables. The v1.2 schema
explicitly requires these files to exist even when empty (lines 405–429 and
464–465). A finite U0 timestep-guard stop has initial inventory and velocity
rows, but no transported-interval rows or phase rows.

The following is the inherited producer's actual event-prefix matrix. Let
`S=slot_count`, `K=completed_interval_count`, and `N=14`. Numbers are data-row
counts. Every file must exist with its exact header even when the count is
zero. This matrix must be independently frozen or deliberately amended before
implementation; it is source analysis, not runtime evidence.

| Termination event | source-flux | offmask | rate | boundary | mass | velocity-audit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Normal completion | `N*S` | `N` | `N` | `N+1` | `N+1` | `N+1` |
| Failed `initial_u0` | 0 | 0 | 0 | 0 | 0 | 0 |
| Finite timestep guard at `U_K` | `K*S` | `K` | `K` | `K+1` | `K+1` | `K+1` |
| Failed velocity `pre_vof` in K | `K*S` | `K` | `K` | `K+1` | `K+1` | `K+1` |
| Failed phase `pre_vof_x/y/z` in K | `K*S` | `K` | `K` | `K+1` | `K+1` | `K+1` |
| Failed phase `pre_momentum` in K | `(K+1)*S` | `K+1` | `K+1` | `K+1` | `K+1` | `K+1` |
| Failed velocity `projection_override` or `corrected_endpoint` in K | `(K+1)*S` | `K+1` | `K+1` | `K+2` | `K+2` | `K+1` |

Interval rows use keys `0..count-1`, with slots `1..S` in input order.
Boundary/mass/velocity rows use state keys beginning at zero. In the last
matrix row, boundary and mass include state K+1 but the six-ledger velocity
audit does not. The inventory call precedes both endpoint failure sites
(patch lines 153–185). In a `pre_momentum` failure, geometric flux has already
been recorded but inventory has not. Thus `completed_interval_count` alone
cannot select all ledger prefixes, and “through the first failed state” is
not a sufficient rule. Partial directional raw flux can also exist before a
`pre_vof_y/z` failure despite no interval-K summary row.

The existing rate check can abort after flushing rate row K but before
offmask/source-flux K or inventory K+1 (patch lines 580–585 and 1785–1791).
This is **not** one of v1.2's three controlled-stop classes. Keep it an
unclassified failed attempt with preserved evidence unless a prospective
schema amendment admits a new stop reason. Never disguise it as a phase,
velocity, or timestep stop.

**Repair/owner/evidence:** Primary freezes the matrix, missing-versus-empty
policy, flush points and unclassified-failure disposition; producer explicitly
flushes initialized headers before any possible early stop; launcher/analyzer
owners test all listed prefixes, each one-row truncation, dry success and the
unclassified rate stop with CPU fake executables. No GPU is needed.

## H2 — The rate and time descriptions must match the inherited producer

Contract line 129 calls `rate-check.csv` a measurement of total top liquid
flow. The current producer instead sums **inward phase volume only over the
configured masks**, then divides by dt (`restas_source_check_volume_pair`,
patch lines 550–559). Off-mask inflow and all top outflow are excluded.
Bottom rate is a compensated sum of signed total-volume flow `-w*area`,
including air, not a bottom liquid flux (lines 569–579). It is not generally
the sum of positive bottom outflow terms.

Keep those meanings explicit, or prospectively change the producer and header.
An independent total top inward liquid rate is
`(sum(slot_inward_volume)+offmask_in_volume)/dt`; outward top flow is
`(sum(slot_reverse_out_volume)+offmask_out_volume)/dt`. Define net flow
separately. The stored slot-masked rate and summed slot rows use different
grouping of floating-point additions; the contract must freeze the intended
comparison/reduction budget rather than assuming bitwise equality after an
algebraic regrouping. Inactive configured slots remain slot rows; dry cases
do not invent zero-slot rows.

Inherited index/time meanings also need to be frozen before six-ledger code:

| Output | Actual producer meaning to preserve or explicitly amend |
| --- | --- |
| source-flux/offmask/rate | Transport interval k and source schedule `[2,12)`; geometric flux already includes the timestep, so volume is flux × area and rate divides by dt once. |
| boundary | Initial state 0 plus phase inventory state k+1 after advection. The existing `completed_state_index` header does not imply that momentum/projection has completed. Values are per-interval nonnegative in/out magnitudes, not cumulative signed flux. |
| mass | Same phase-inventory states; native solver `time` is passed through. Per-face mass and `net_boundary_liquid_m3` are per interval; only the explicitly cumulative in/out columns accumulate over intervals. Residual is `M_in-M_out-(M_box-M_0)`. |
| velocity-audit | Initial U0 and successfully corrected endpoint U(k+1), after that endpoint's stage audit. `source_profile_interval` is the installed profile's state index, k+1 at an endpoint, not the just-consumed interval k. Its top/bottom entries are positive parts of **net** velocity-face sums. |

The primary-frozen v1.2 timestep clock `t0 + real(k,rp)*dt` is correct for
that interface. It does not automatically change the two inherited `time_s`
writers, which still receive the accumulated AB2 solver clock (patch lines
903–907 and 991–994). Specify their clock and compare state joins explicitly.
Likewise, line 193's “wrong final physical time” must distinguish v1.2's
logical completed-interval time from native solver time and partial endpoint
state. Do not introduce a post-run time tolerance to reconcile them.

**Repair/owner/evidence:** Primary owns the six-ledger amendment; producer and
analyzer owners implement its chosen meanings. Require compiled-helper output
for an off-mask-only flux perturbation, reverse flow, both pulse edges and a
multi-state AB2 clock example. Audit sign, units and sums from raw operands.
CPU work only until the complete release gate is independently reviewed.

## H3 — The specified input grammar is not the current reader's grammar

The record table and fixture counts are correct. But current
`restas_source_read` uses one external list-directed read per requested record
and closes immediately after reading the factor (patch lines 205–240).
It does not enforce physical record token counts or EOF after the final
record. Fortran list-directed input can discard unused trailing values,
continue a short record onto the next record, and recognize syntax such as
commas, repetition factors, slash termination and D exponents that the draft
does not admit. `iostat==0` is not complete lexical consumption. The currently
compiled parser is therefore not evidence that lines 30–38 are enforced.

Pin the precise integer/real token regular expressions, allowed horizontal
whitespace, integer storage/range, binary64 conversion and underflow rule.
In particular “base-10 syntax,” “finite decimal syntax,” and “required
nonzero” need exact definitions. Lexically reject null/slash/repetition/comment
forms before converting individual validated tokens. Read/validate physical
lines, require the exact `9+slot_count` record count and final LF/EOF, and
compare the solver's typed record against an independent parsed object.
Exact approved hashes remain the run-eligibility boundary; parser robustness
tests with changed bytes do not authorize those bytes as cases.

The source grammar excludes comments, whereas the real `dns.in` and `vof.in`
fixtures contain comments and logical/character fields. Define their separate
record grammar, not an accidental application of the source grammar to all
three files. The “14-step schedule” comes from `dns.in`, not from the source
mask file alone. Validate stop mode, no restart, fixed step, time scheme,
fluid/VOF initialization, forcing, boundary types/values and the absence of
extra staged inputs. Record raw bytes alongside typed interpretations.

**Repair/owner/evidence:** Luna parser/producer owner plus an independent
analyzer owner, with disjoint files and a primary-owned typed interface.
Require differential compiled-reader/independent-parser tests: accepted exact
fixtures; short/long/extra records; comma, slash, repeated/null values;
comments, blanks, CRLF/BOM; D exponent; nonfinite/overflow/underflow; integer
overflow; overlapping masks; and inconsistent duplicate dns/source values.
These are CPU prerequisites, not solver trials.

## H4 — The inherited helpers shift the vertical spacing index

This is a source defect relevant to contract lines 130–132 and 136–139, not
just missing documentation. Production main allocates `dzf(0:nz+1)` with
`nh_d=1` (pinned upstream main lines 220–246). Both main and `advvof` pass the
whole array to these helpers:

- `restas_source_accumulate_boundary_flux`: `dzf(:)`, patch lines 749–752;
- `restas_source_record_inventory`: `dzf(:)`, lines 866–870;
- `restas_source_record_velocity_audit`: `dzf(:)`, lines 912–916.

Their assumed-shape dummy begins at 1. Consequently helper `dzf(k)` denotes
caller `dzf(k-1)`, not caller cell k. This affects x/y geometric face areas,
inventory cell volumes, velocity face fluxes/divergence, and the inherited
Courant calculation. The calls are visible at patch lines 114–115, 158, 184,
1730 and 1759. It also shifts the two-halo host harness, whose spacing entries
are all the same and therefore cannot expose the problem.

The nominally uniform fixture is not bitwise uniform: `initgrid.f90:43–55`
forms face-coordinate differences. A source-order binary64 transcription
finds the first shifted difference at k=3: intended
`0.024999999999999994`, shifted `0.025000000000000001`, with 22 differing
interior positions. This is arithmetic/source evidence, not a measured solver
mass error. A nonuniform synthetic host fixture would make the error larger.

**Repair/owner/evidence:** Separate bounded producer follow-up: preserve the
actual lower bound explicitly or pass the intended interior slice, consistently
at every call. Test both production one-halo and harness interfaces using
nonconstant spacings and independently known face/volume integrals. Review
the exact resulting patch before source use. Do not “fix” the analyzer by
quietly reproducing a wrongly addressed mesh, and do not treat its small size
on this fixture as numerical acceptance evidence.

The inherited Courant formula also uses division by its `dzf(k)` for all
directions (patch lines 967–975), whereas v1.2's exact bound uses captured
`dzfi(k)`/`dzci(k)` and source-order multiplication. After the indexing repair,
freeze whether this remains a distinct diagnostic or is prospectively
changed. Do not require exact equality with `dt*dtic_raw` without reconciling
those operands and operations.

## H5 — The raw-evidence and six-ledger binding interface remains incomplete

Lines 134–141 correctly reject summary agreement as sufficient conservation
proof. “Per-step arrays” alone does not identify a reproducible capture point.
Freeze a raw-artifact schema with basename/path, interval/state/stage,
component/face, actual index bounds/halos, shape, dtype, endianness, byte order,
units/sign, mesh operand identity, byte size and exact content hash. Capture
directional phase-flux faces immediately after each corresponding sweep,
before the shared flux array is reused; capture the exact source-face velocity
operands used by the z-flux momentum calculation; retain inventory alpha and
the U-state arrays needed by the velocity/divergence stencil. Define which
partial-stage raw artifacts survive every H1 stop prefix.

The stability row at line 165 requires **raw** alpha bounds. Current VOF code
clips `dvof1`, `dvof2` and final `vof` before downstream audits/inventory
(patch lines 1736, 1765 and 1798; pinned upstream `clip_vof`, lines 273–298).
Post-clipping alpha cannot prove pre-clipping boundedness or quantify clip
mass. Add pre/post-clip evidence and a declared clipping-change budget, or
prospectively narrow that claim. Absent-phase leakage likewise needs specified
cells, stages and absolute/relative zero rules.

The canonical names in the draft are not the native paths: main uses prefix
`data/restas`, yielding `data/restas_source-flux.csv`, etc. Freeze the mapping
to canonical bundle names and retain/hash the originals. Pin exact six headers
(patch lines 680–705), token syntax and row order. The six current writers use
space-padded `ES24.16E3`; the new v1.2 tables' no-whitespace token rule cannot be
silently inherited. Choose the amended serialization or explicitly admit the
inherited padding in this separate schema.

Schema v1.2 permits exactly three entries in `files_sha256` and `row_counts`
(lines 366–368, 431). Therefore the six ledgers and raw evidence need a
separately versioned, exact-hash manifest/receipt bound to the v1.2 manifest,
contract, candidate, actual staged inputs, raw files and the complete auditor
dependency set. Do not add six keys to the frozen v1.2 objects or merely trust
an analyzer path supplied by a caller. The writer at
`write_run_manifest.py:310–359` currently binds only the three table files.

**Repair/owner/evidence:** Primary freezes raw and conservation-manifest
interfaces, capture points and writer/reader file ownership. A producer owner
implements capture; a separate auditor owner recomputes quantities without
calling producer reduction helpers. Synthetic fields must discriminate signs,
halos, staggering, slot/offmask membership, clipping, zero denominators,
reduction order and corrupted/truncated/raw-hash cases. A byte/storage estimate
is a CPU prerequisite to resource sizing. Complete per-step evidence on this
small 537,600-cell diagnostic is a bounded task; sparse visualization outputs
cannot substitute for it.

## H6 — Offline OCI identity is feasible, but needs an exact conversion contract

The selected offline route is compatible with the provenance goal. It does
not require registry publication. Read-only inspection of the previously
reviewed local image returned ID
`sha256:7bad4d20c55fa718321de53f49083f98042be522b6848b73903c7c8b005202d4`,
`linux/amd64`, `RepoDigests=[]`, entrypoint `["/bin/true"]`, and 24 ordered
rootfs DiffIDs. Docker client/server are 29.1.3. This verifies the old image's
local identity only, not a successor build or an OCI export.

During closing, the primary reported a successful offline export of successor
image `sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`:
the archive already contains OCI layout 1.0.0, `index.json`, manifest
`sha256:5d3d0117271bf8e7e987d316a863d4f3397a77049eb9cd1f3122c44d03b7bda3`
(3,907 bytes), unchanged config identity and 24 uncompressed OCI tar layers.
The primary reports matching blob digests/sizes and ordered rootfs DiffIDs.
This is **primary-reported evidence pending its archived commands/report**;
this reviewer did not rerun the large export or independently inspect that
archive. It conditionally resolves practical local-export feasibility. Preserve
the existing manifest/config bytes rather than canonicalizing them. H6's
remaining work is the frozen verification/receipt contract and its exact
evidence, not finding a registry or inventing another image representation.

Amend lines 105–112 with an explicit algorithm and byte-level tests:

1. Export the exact local ID, preserving its config bytes. `docker image save`
   supplies a local archive, but the converter must validate the actual archive
   format and platform rather than treating its outer tar hash as an image
   manifest. No export was attempted by this reviewer.
   [Docker image-save reference](https://docs.docker.com/reference/cli/docker/image/save/)
2. Preserve stored layer blobs. For each descriptor, check media type, exact
   raw-byte size and digest; in stack order separately check the digest of the
   uncompressed tar stream against the corresponding `rootfs.diff_ids` entry.
   Blob digest and DiffID generally differ for compressed layers; they coincide
   for the same uncompressed tar bytes. Do not repack extracted files as proof
   of the original DiffID. Preserve the config bytes: their digest must equal
   Docker's ID, and their ordered DiffIDs must equal the inspected local image's
   rootfs list. A converter that rewrites config JSON fails this chosen route.
   [OCI configuration and DiffIDs](https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/config.md)
3. Freeze deterministic bytes for any newly generated manifest: for example,
   UTF-8, sorted object keys, compact separators, no varying annotations and an
   explicit final-LF rule. Hash and archive **those exact bytes**. Verification
   hashes the stored blob; it does not parse/reserialize an existing blob before
   hashing. OCI allows canonicalization but its digest identifies actual bytes.
   [OCI descriptors](https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/descriptor.md)
4. Require a self-contained layout with `oci-layout`, `index.json` and all
   referenced blobs. Select exactly the reviewed linux/amd64 image manifest;
   `image_digest` denotes that manifest, not `index.json`, the archive, or the
   config. Pin base-to-top layer ordering and descriptor types. The layout's
   index and the image manifest are different objects.
   [OCI layout](https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/image-layout.md),
   [OCI image manifest](https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/manifest.md)

This is a feasible design inference from the specifications and available local
image, not an export-success claim. Use original uncompressed layer archives
where available to avoid introducing compressor variability; if compression
is chosen, pin its tool, options and metadata. The deterministic identity of
an already built image is separate from reproducibility of a fresh rebuild.

**Repair/owner/evidence:** Primary provenance owner; CPU/disk only, separately
budgeted because the compiler image is not a tiny fixture. Produce a real
layout/receipt and an independent verification report; test one-bit blob
corruption, wrong byte size/media type/platform, reordered/missing layers,
rewritten config, index-versus-manifest substitution and altered manifest
whitespace. At launch use the mapped immutable Docker ID and verify the actual
executable/patch and overridden command, not merely a mutable tag or a mounted
copy of the patch. A config rewrite or unavailable raw layer history is a stop
under this contract, followed by prospective amendment if necessary.

## H7 — First-run resource limits must not depend on the blocked pilot

Contract line 168 requires limits “from a measured eligible pilot” before
source launch, but lines 172–186 and `docs/COMPUTE.md:136–174` put source
qualification before the larger GPU pilot. Read literally, the first source
diagnostic cannot be eligible until after the pilot it must enable.

Separate three decisions: (1) prospective hard ceilings for the first exact
537,600-cell, 14-interval diagnostic, based on a current doctor snapshot,
static memory/output bounds and a conservative time allocation; (2) measured
resources from the first eligible diagnostic, used to size later source
cases; (3) the separately gated 1–3-million-cell profiling pilot and later
scaling. The source-disabled smoke can inform software availability, but does
not establish source performance or source resource usage. Freeze initial
caps and sampling/stop rules before that first launch; do not select ceilings
after observing an overrun.

Define whether a RAM quantity is container/cgroup usage or process RSS, how
VRAM is attributed, maximum sample gaps, monitoring start/end coverage, disk
accounting and polling overshoot. A sampled VRAM high-water mark is not a
hardware allocation limit. Require verified container/process termination on
timeout, OOM or sampler failure before releasing the GPU lock; stopping the
Docker client alone is insufficient evidence of stopping its container.

**Repair/owner/evidence:** Primary scheduler plus scientific reviewer freeze
the initial envelope; launcher owner proves enforcement with CPU fake jobs.
The first GPU source trial remains blocked by all other release prerequisites.
No resource number is approved by this review.

## Limits that can remain pending during implementation

Absence of numerical acceptance values in this explicitly unapproved draft is
not by itself an additional contract contradiction. Dose, momentum, off-mask
and return-flow error, mass closure, divergence, Courant, raw alpha/leakage,
fixed-step margin, uncertainty arithmetic and pass/inconclusive/fail precedence
may remain explicit pending fields while CPU implementation proceeds. Their
formulas, units, denominators, zero rules and required evidence must be frozen
as interfaces first; their numeric limits need independent analytic/source
justification and exact review **before any source launch**. Existing helper
abort tolerances must be inventoried separately as implementation behavior;
they are neither hidden new scientific limits nor automatically sufficient
acceptance criteria.

The pinned GPU solver source has forward/backward FFT calls and a direct
tridiagonal solve. The draft correctly treats iterative pressure iterations
and residual as potentially `not_applicable`, conditional on the exact
candidate route. This does not waive finite completion, projection/divergence
evidence or pressure-route identity checks. No iterative tolerance should be
invented for this direct route.

No measured built-Restas geometry, field cup data, cluster account, or further
user approval is needed to complete these engineering contracts. Those inputs
remain later scientific dependencies; none can repair the implementation
contradictions listed here.

## Correct portions and bounded acceptance sequence

All 15 contract input hashes match actual bytes and the case inventory.
The source files have the declared ASCII/LF layout and 9, 10 or 13 records.
The masks contain 0, 240 or 960 cells without overlap. The positive fixtures
have exactly ten active intervals in `[2,12)` within N=14; dry is `[0,0)`.
The quiescent sequence `dry_four -> quiescent_one -> quiescent_four`, one GPU
case at a time, stopping at first failure, is consistent with project compute
instructions. Both 50 m/s crossflow cases remain negative host/parser
fixtures; do not run their known U0 guard failure on the GPU or silently
modify their hashes, dt, dose or horizon.

| Next bounded assignment | Owner / prerequisite | Acceptance or stop evidence | Compute eligibility |
| --- | --- | --- | --- |
| Amend v0.1 for H1–H3, H5–H7 | Primary; this memo and held source/schema | Exact grammar, prefix/clock/ledger/raw/binding/OCI/bootstrap interfaces; independently reviewed new contract hash | CPU only |
| Strict reader and spacing repair | Luna producer; primary-owned interfaces, disjoint patch ownership | Compiled reader versus independent parser; nonconstant-spacing integrals; exact patch/hash review | CPU build/helper checks; GPU blocked by source release |
| Raw capture and six-ledger auditor | Separate producer and analyzer owners; accepted raw schema | Compiled raw output to independent auditor, analytic perturbations and all prefix fixtures | CPU only until complete exact release |
| OCI layout and receipt | Primary provenance owner; frozen exporter rules and budget | Real archive/layout hashes, exact config/DiffID mapping, corruption tests and independent review | CPU/disk; GPU not applicable |
| Source supervision and fake-executable suite | Luna launcher owner; contract interfaces and prospective initial caps | Correct complete/prefix outcomes, no later-case invocation after any failure, resources stopped and lock retained through cleanup | CPU only |
| Numeric limit decision and exact launch review | Primary plus assigned independent scientific reviewer; complete operands and sources | Frozen justified limits, exact input/candidate/image/producer/analyzer/launcher hashes and test evidence | Review only; primary schedules one GPU case only after acceptance |

The fake suite at lines 197–203 is a good starting list. Add every controlled
stop stage in H1, valid header-only cases versus illegal missing files, rate
abort, unchanged-versus-mutated staged bytes at completion, malformed raw data,
receipt/layout tampering, monitoring gaps/NaN/dead sampler, disk/VRAM overrun,
and child/container survival after timeout. An invocation counter must show
that the next dependent case was never launched. Fake negative fixtures
exercise the supervisor on the CPU, not a forbidden real crossflow GPU run.

## Checks performed and evidence limits

- Read-only `sha256sum` checks pinned the contract, schema, inspected patch and
  supporting identities above. `sha256sum --check SHA256SUMS` in the fixture
  root reported **15 OK**.
- An independent in-memory `.venv/bin/python` byte/hash/token/mask check
  matched **15/15 contract table hashes**, all five record layouts, masks and
  source schedules. It derived normal six-ledger row totals of 0/14/56 source
  rows for dry/one/four slots, 14 offmask/rate rows and 15 state rows. Counts
  for crossflow are hypothetical normal-completion counts only; those cases
  are expected to stop at U0 and were not run.
- An in-memory binary64 transcription of upstream face-coordinate differences
  established the spacing-remap example in H4. It is not a compiled-production
  floating-point equivalence test.
- Read-only Docker inspection established the old image facts in H6. A tiny
  synthetic byte example confirmed that compressed-blob versus uncompressed
  hashes differ and that semantically identical JSON serializations can hash
  differently. It was not an OCI export or a valid candidate layout test.
- A first invocation of the Python inventory probe used the fixture directory
  with a repository-relative interpreter path and failed to find `.venv`.
  It was immediately rerun from the repository root successfully; no fixture
  bytes were changed. No compiled helper tests or project-wide tests were
  claimed or run for this read-only review.

The primary should record dispositions and queue dependencies in shared status
and blocker records. This memo leaves those files to their owner. **No-run /
no-gate disposition remains in force.**
