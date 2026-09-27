# Candidate5 staged-input, conservation and launch contract

**Primary successor contract v0.3 — design proposal; exact review and primary
disposition pending. It does not accept B1-pre/B2 or authorize a source run.**

This document amends and supersedes the conflicting provisions in
[`v0.2`](FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT_v0.2.md), SHA-256
`8965b0c1d58ba53252659d53ff7fcc0bd9fb41a2f82aeec4a65ea39d49281b32`, which
remains preserved as the Warden-reviewed proposal snapshot. It also inherits
the nonconflicting provisions of
[`v0.1`](FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT.md), SHA-256
`09419b40c4cfd4f6262f45a2ed184d303efb68adcfa86dfd451de52f0f397112`; input
hashes, fixture identities, schedule/mask definitions, quantity tables and
acceptance dependencies remain versioned. Where text conflicts, this v0.3
proposal controls. V0.1 remains the historical draft reviewed **REVISE**.

The frozen parent interface remains
[`candidate5 observability schema v1.2`](FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md),
SHA-256 `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`.
No amendment here changes its three-table manifest. This proposal incorporates
the exact findings in
[`Astra's v0.1 review`](../docs/reviews/FLUTAS_SOURCE_RELEASE_CONTRACT_REVIEW_20260925T1331Z.md)
Warden 11,
[`Warden 12`](../docs/reviews/PROJECT_WARDEN_20260925T1403Z.md), and the
[`focused Astra deblock plan`](../docs/reviews/BLOCKER_RESOLUTION_PLAN_ASTRA_20260925T1615Z.md).
Its controls must be independently reviewed against exact producer, analyzer,
input/ledger schema, provenance-tool and launcher hashes before any source run.

## H1 — Output existence, empty files, and exact stop prefixes

All six inherited files must be created before any controlled stop, with the
exact header defined by the producer interface, UTF-8/ASCII-compatible bytes,
LF record ends, and a final LF. A legal zero-row file consists of its header
only; a missing file, wrong header, truncated row, or incomplete required
prefix is structural failure. All inherited and v1.2 headers must be explicitly
flushed before the first possible controlled or unclassified stop. The normal
dry run has zero `source-flux.csv` rows because it has no slots; it still has
all 14 interval rows in `source-offmask.csv` and `rate-check.csv`. On an
`initial_u0` velocity-audit failure, the six inherited tables have zero data
rows, the v1.2 phase and timestep files are header-only, and the v1.2 velocity
file retains the complete 12-row failing `initial_u0` group at
`state_index=0`, `transport_interval_index=-1`, `stage_id=initial_u0`. Empty
slot classes in v1.2 remain represented by their required zero-count rows; a
nonexistent dry-run slot is not an empty declared slot class.

For `S=slot_count`, `K=completed_interval_count`, and `N=14`, inherited
source-flux keys are lexicographic `(interval_index,slot)` pairs. With `S>0`,
zero-based row r has `interval_index=r//S` and `slot=1+r%S`; with `S=0`, the
table has no data rows. State keys start at 0. Counts below exclude headers:

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
| `source-flux`, `source-offmask`, `rate-check` | Transport interval `k`; the positive-source fixtures use the half-open active schedule `[2,12)`, while the dry fixture declares `[0,0)`. Geometric flux already includes `dt`; volume is flux × area and rate divides by `dt` once. |
| `boundary-ledger` | Initial state 0 and phase inventory states k+1 after advection. `completed_state_index` does not mean momentum/projection completed. In/out columns are per-interval nonnegative magnitudes, not cumulative signed flux. |
| `mass-ledger` | Same phase-inventory states. `time_s` is the native accumulated solver clock. Per-face mass and net boundary volume are per interval; only explicitly cumulative in/out mass columns accumulate. Residual is `M_in-M_out-(M_box-M_0)`. |
| `velocity-audit` | Initial U0 and successfully corrected endpoint U(k+1), after that endpoint stage audit. `time_s` is the native accumulated solver clock captured for the state. `source_profile_interval` is the installed profile's state index (k+1 at an endpoint), not the just-consumed k. Top/bottom values are positive parts of net velocity-face sums. |
| v1.2 `timestep-restriction` | Diagnostic clock `time_start_s + state_index*dt`; retain the primary-frozen index clock. It is distinct from native accumulated solver time. |

Joins use integer state/interval keys and exact producer call order, never a
post-run time tolerance. Final-time checks separately bind planned intervals,
completed intervals, completed states, diagnostic index time, and native
solver time. Both `mass-ledger.time_s` and `velocity-audit.time_s` are the
native accumulated solver clock, captured at their recorded state; repeated
rows for the same state must match the same native clock value exactly. The
v1.2 timestep `time_s` and manifest `final_time_s` remain diagnostic index
times, `time_start_s + state_index*dt`, not aliases for that native clock.
Normal completion requires exactly N completed intervals and the complete
state-0-through-state-N inventory/velocity prefixes. A controlled stop uses
the exact event prefix in H1; its last native-time row is the last state the
producer actually records, not `completed_interval_count*dt` inferred after
the fact. Final-state predicates bind planned intervals, completed intervals,
complete inventory states, corrected velocity states and diagnostic/native
clocks separately. CPU fixtures must include both pulse edges, reverse flow,
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
grammar. The pinned reader consumes exactly 29 DNS records and 8 VOF records.
The exact five allowlisted input triplets retain inline `!` comments, Fortran
logical tokens (`T`/`F`), and character identifiers; only two DNS byte
variants exist, for the declared crossflow velocity/gravity values. Their
normative per-record field/type/token map, cross-file checks and exact five-pair
hashes are in the proposed
[`input schema v0.1`](FLUTAS_CANDIDATE5_INPUT_SCHEMA_v0.1.md), SHA-256
`20afc81766fd0068bbc24732339412c5e10ca8707e40557038d68eee6c1139db`. Its
record tables are hash-pinned to the
[`DNS/VOF typed-record audit`](../docs/reviews/DNS_VOF_TYPED_SCHEMA_AUDIT_20260925T1443Z.md),
SHA-256 `e7709cc54e5ecbb623062fcba6f30f420d6c2c17048866cf9db25f756e917c47`.
These are proposed exact-fixture rules; generalized Fortran grammar and
out-of-allowlist values are not accepted.

After verifying exact raw hashes against the allowlist, the independent parser
decodes ASCII, strips only inline `!` comments, preserves physical record
order, requires exactly the schema's record/token counts, and parses each field
with its declared type. Blank records, CRLF, BOM, continuation,
comma/slash/null/repeat syntax, extra tokens, and added records fail. Before
eligibility it checks the duplicated grid, fixed-step mode/value, 14-step
stopping mode, AB2 time scheme, no-restart/start-time, boundary types/values,
fluid and empty-VOF setup, forcing, gravity, and extra-input absence against
the independently parsed source record and v1.2 derived schedule. A changed
but value-equivalent file is not eligible unless a prospective reviewed
amendment adds its exact hash and semantics. The new annex and this contract
still require exact Astra Max review and primary disposition; the full v0.3
release interface remains incomplete pending the ledger/raw annex and other
H1-H7 acceptance work.

CPU differential tests cover each exact accepted triplet, every record and
cross-file relation, malformed lines/types/tokens, byte mutations, changed
but value-equivalent inputs, CRLF/BOM, nonfinite and out-of-range values,
integer overflow, overlapping/out-of-grid source masks, and every
duplicated-field mismatch. A parser test never authorizes a changed fixture
for solver use.

## H4 — Correct the production lower bound for vertical spacing

Candidate5 passed production `dzf(0:nz+1)` to assumed-shape `dzf(:)` dummies,
whose default lower bound shifted helper `dzf(k)` to caller `dzf(k-1)`. The
inherited Courant diagnostic uses the same spacing operands. Candidate6 changes
the boundary-flux, inventory and velocity-audit dummies to `dzf(0:)`. Astra's
exact review accepts that correction for the pinned one-halo production
caller and its exact patch application in the initial H4 review, which returned
**REVISE** for aggregate H4. The required regression has since been added and
independently reviewed. Astra Max accepts H4 at the bounded helper-test scope
in [`candidate6 two-halo exact review`](../docs/reviews/FLUTAS_CANDIDATE6_H4_TWO_HALO_EXACT_REVIEW_20260925T1445Z.md),
SHA-256 `176475954e7540739b7267f0a6d54cf6e298624dfb0141e7d5fa36616c3bf2d4`.
Nonuniform one-halo and explicit-slice two-halo cases pass; the whole-array
two-halo negative reproduces the index shift. Astra independently recomputed
all 600 CSV scalar values. The original probe measured 20,064 kg for the
wrong whole-array call versus 37,032 kg expected; passing `dzf(0:)` restored
the checked value.

The H4 successor must retain both (a) the production one-halo allocation and
(b) the host two-halo storage passed as the explicit physical-index section
`dzf(0:)`. Nonconstant spacing values must independently check x/y face areas,
cell volumes/inventory, velocity face flux/divergence, and the inherited
Courant terms. A separate negative control passes the two-halo storage whole
and must detect the one-index shift; it is a regression guard, never an
accepted call form. Preserve both positive cases and the negative control in
candidate6's tests. The historical candidate5 full validator still passes
whole arrays and is unsafe to reuse unchanged against the candidate6 helper;
the failed historical Python oracle snapshot was not retained. H4 acceptance
does not establish production build integration, source runtime, receipt,
GPU eligibility or any scientific gate. The v1.2 timestep bound separately uses captured
`dzfi/dzci` operands and frozen source-order multiplication; preserve that
operation order without asserting equality to the inherited division-based
diagnostic. Exact source-package/launch review is required before any source
run.
Source-disabled GPU smokes do not exercise this helper and must not be repeated
to close H4.

## H5 — Canonical ledger paths and raw-evidence manifest

The exact ledger and raw-artifact data model is normative only when the
companion ledger/raw schema annex is present and hash-pinned. Until then this
section is a requirements checklist, not a frozen producer/auditor interface.

The six native files are opened under prefix `data/restas`; their native paths
are `data/restas_source-flux.csv`, `data/restas_source-offmask.csv`,
`data/restas_rate-check.csv`, `data/restas_boundary-ledger.csv`,
`data/restas_mass-ledger.csv`, and `data/restas_velocity-audit.csv`. The
immutable run bundle copies each original byte stream to the six canonical
names without changing bytes, records both native and canonical paths, hashes
both, and verifies byte identity. The annex must pin the exact six headers and
column order to the reviewed producer patch/receipt hash, plus exact integer,
logical, and real token grammars. The inherited producer currently formats
real ledger values with `ES24.16E3` padding; the independent analyzer may trim
only surrounding ASCII space, then must enforce one numeric token per field
and reject internal whitespace, extra fields, nonfinite values and malformed
exponents. It may not infer a schema from a runtime header. This does not
relax v1.2's separate token grammar.

Add a separately versioned `source-evidence-manifest.json`; do not add keys to
the frozen v1.2 `files_sha256` or `row_counts`. The annex must freeze its
version string, exact top-level keys/types, canonical byte encoding (UTF-8,
sorted object keys, compact separators, no NaN/Infinity and one final LF), and
complete normal/stop-prefix examples. It binds exact bytes/hashes for v1.2,
this contract and all schema annexes, candidate receipt/image manifest,
staged inputs, six native and canonical ledgers, raw files, auditor/tool
dependencies, and source launcher. The expected raw roster is declared by the
annex from source call order; it is not self-declared by the producer.

Every raw entry declares one composite identity
`(artifact_role,state_index,transport_interval_index,stage_id,face,component,array_name,part_index)`;
unused dimensions have an explicit `not_applicable` value. This permits the
same role at different states and stages while rejecting duplicate identities.
Entries separately state `required_in_normal_run`, `expected_for_stop_prefix`,
and `capture_status` (`captured` or `not_reached`). The expected-prefix flag
is derived from the exact stop tuple and frozen roster. A captured entry must
have a canonical relative path, positive byte size and SHA-256; a not-reached
entry keeps its expected relative path and has null size/hash. A required
artifact expected for the current prefix may not be `not_reached`. The annex
must fix each file's encoding/storage order, endian, dtype, role-specific
shape and actual inclusive bounds/halo widths, units/sign and capture-source
hash. Reject symlinks, hardlinks, path escapes, unlisted files, missing
expected artifacts and hash/size/shape mismatches.

Capture directional phase-flux arrays immediately after each x/y/z sweep,
before the shared flux array is reused; capture source-face velocity operands
at the exact momentum-flux operation; capture liquid-fraction inventory and
the U/V/W states used by divergence and Courant stencils. At minimum retain
the pre-clip and post-clip alpha states at each of the three VOF clipping
sites (`dvof1`, `dvof2`, final `vof`), keyed to the stage; if the implementation
does not retain these, narrow raw-boundedness and clipping claims explicitly
before launch. The annex freezes absent-phase classification, denominator and
zero behavior, required primitive operands, units, sign and reduction order.
Those definitions are not post-run scientific limits: only numeric pass,
inconclusive and fail thresholds remain pending scientific review. Raw files
for stages reached before a stop are kept and hashed; later-stage roster
entries are explicitly `not_reached`, never silently absent.

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

The immutable `candidate-build.json` uses this exact top-level object and no
additional keys: `schema_version`, `candidate_id`, `source`, `patches`,
`build`, and `image`. `schema_version` is the string
`track2-candidate-build-v1`; `candidate_id` is a nonempty string. `source` has
exactly `repository_url` (a nonempty string), `commit_oid` (40 lowercase hexadecimal
characters), `object_format` (the literal `sha1` for the pinned repository),
and `files` (an array sorted by unique repository-relative `path`). Paths use
UTF-8 POSIX separators and may not be absolute or contain `.`/`..` components.
Each source file object has exactly `path`, `git_blob_oid` (40 lowercase hex),
and `content_sha256` (64 lowercase hex). `patches` is an array in application
order; each entry has exactly repository-relative `path` and ordinary
64-character lowercase-hex `sha256`.

`build` has exactly `build_script_path`, `build_script_sha256`,
`builder_image_digest`, `compiler`, `compiler_version`, `compiler_sha256`,
`compiler_flags`, `command_argv`, `environment`, `inputs`, `executable_path`,
and `executable_sha256`. Build-script path is repository-relative; ordinary
hash fields are 64 lowercase hex; `builder_image_digest` is
`sha256:<64 lowercase hex>`; compiler and version are nonempty strings; flags
and command are arrays of nonempty argument strings; inputs is sorted by
repository-relative path, with each entry exactly `{path, sha256}`; and
environment is an object of exact nonsecret string-to-string build variables.
All receipt paths use the source path syntax above, except `executable_path`,
which is an absolute, normalized image path. Include all environment
variables and input files that affect the executable; do not
put credentials or secrets in the receipt. `image` has exactly `platform`,
`oci_manifest_digest`, `docker_image_id`, `config_digest`, `entrypoint_argv`,
`cmd_argv`, and `layers`. The two command fields are arrays of strings and
exactly reproduce the selected manifest config's Entrypoint and Cmd; empty
arrays remain empty.
Platform has exactly `os` and `architecture`, whose values are `linux` and
`amd64`. The three image identities use `sha256:<64 lowercase hex>`; the Docker
image ID must equal the OCI config-blob digest. Each layer entry has exactly
`media_type` (a nonempty string), `digest` and `diff_id` (each
`sha256:<64 lowercase hex>`), and `size` (a nonnegative integer, not a
boolean); the array preserves the OCI manifest's base-to-top order and must
match config `rootfs.diff_ids` one-for-one.

The source commit and Git blob IDs are Git object identities; they are not
SHA-256 hashes of file contents. For this SHA-1 repository, `git_blob_oid` is
the 40-character object ID computed by Git over its blob object framing, while
`content_sha256` is SHA-256 over the exact unframed file bytes. The receipt
does not contain its own digest: external `candidate_sha256` is SHA-256 of the
exact archived receipt bytes. Generated receipt JSON is UTF-8, recursively
sorted object keys, compact separators, no duplicate keys or nonstandard
numeric constants, and exactly one final LF. Reject duplicate paths in the
source-file, patch, and build-input arrays. The launcher verifies receipt,
layout, local image, executable, patch, build identities and overridden
command before invoking the solver. Retain the exact verified layout and
receipt in the run bundle. Test one-bit blob corruption, wrong size/media
type/platform, missing/reordered layers, rewritten config, index-versus-
manifest substitution, altered manifest whitespace, patch/executable
substitution and archive path traversal.

Source provenance must be derived from the pinned upstream Git commit, not a
mutable checkout or directory label. For upstream commit
`598210616bebd51f7d51f61455f196e6f3479916`, the authoritative driver path is
`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`; its Git SHA-1 blob
object ID is `e0e1b4c232da1e261026e73c95118a4cb36cdd6e`, and SHA-256 over the
exact blob content is
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
and independently review resource limits from the current machine snapshot, a
static raw/output bound, and a conservative wall allowance; then use observed
usage only to size later cases. The source-disabled smoke is not a source
resource profile.

The primary's 2026-09-25 14:25 UTC doctor snapshot reports 20 effective CPUs
(18 shared, 2 reserved), 116.9 GiB available RAM, 260.3 GiB free disk, and one
RTX 5090 with 31.8 GiB VRAM. These are point-in-time values, not reserved
capacity. The proposed first-diagnostic envelope is one MPI rank, one
application thread, a 2-core CPU quota, a 16 GiB cgroup memory limit, a 24 GiB
VRAM sampled-stop threshold, 40 GiB per-run disk sampled-stop threshold, and
1,800 seconds solver wall time. These are engineering stop limits, not
scientific tolerances, measured demand, or permission to launch. CPU quota,
cgroup memory and wall time must be hard-enforced; VRAM and disk are sampled
stop thresholds, not hard caps. Keep adequate headroom below device/disk
capacity. Before launch, the primary must refresh available headroom and
compute the exact static raw/output bound; revise and independently review
the proposal if either invalidates it. Raising any limit requires documented
headroom/output arithmetic and another exact review.

The source supervisor samples process/cgroup CPU and memory, GPU memory and
utilization, disk use, solver stage and container state every 1 second; a
valid sample gap may not exceed 2 seconds. Monitoring starts before container
creation and ends only after verified termination. A missing or nonfinite
sample, a gap over 2 seconds, any configured stop threshold, or wall timeout
requests a graceful stop within 1 second. Allow 10 seconds for graceful
shutdown, then force-kill the container and solver process group within 1
second. Verify Docker `State.Running=false` and no surviving solver/container
child within 30 seconds. The maximum permitted threshold-to-verified-stop
latency under a valid monitor is therefore 44 seconds (2 s sample gap + 1 s
stop dispatch + 10 s grace + 1 s force-kill dispatch + 30 s verification).
This is a termination-latency bound, not a promise that sampled VRAM/disk use
cannot exceed its threshold during that interval. If termination cannot be
verified, retain the shared GPU lock and escalate; never release it because
only the client process exited. The 1,800-second solver limit excludes this
cleanup window, and the GPU lock remains held through cleanup verification.

The current `scripts/run_local.py` timeout path terminates its client process
group after a short grace period and then releases its lock without verifying
Docker/container termination. It does not meet this H7 contract. A
source-specific supervisor alone cannot satisfy H7 while the outer launcher
can release the lock first. Source mode remains blocked until the lock owner
implements and passes CPU fake-executable/container tests for hard limits,
sampler failure, timeout, graceful/forced termination, surviving children,
Docker-state verification, and lock retention/release ordering. Record
configured limits, sampled values and gaps, stop trigger/timestamps, signal
sequence, and termination proof separately.

## Numerical limits and release sequence

H2's formulas, signs, units, primitive operands and row meanings describe the
inherited quantities. The exact zero-denominator and absent-phase rules remain
pending the H5 schema annex and must be frozen before implementation. Numerical
acceptance thresholds for dose, momentum,
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
