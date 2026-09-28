# Prospective `dry_four` GPU diagnostic amendment — revision 3

**Status: proposed, not approved.** This revision supersedes the earlier
unreviewed draft and scopes exactly one
quiescent, zero-slot GPU diagnostic. It does not authorize a launch. Astra Max
must exact-review this file against the hashes below, the selected candidate,
the output analyzer, and the launch supervisor; the primary must then record a
narrow disposition before launch. An unsuccessful or interrupted invocation
consumes this amendment's one attempt. It is retained and cannot be retried
under this amendment.

This supplements the pending Candidate5 source-release contract v0.3 only for
the proposed diagnostic. The pinned v1.2 three-table manifest and headers do
not change. The experiment plan remains the physics source of truth. Passing
this diagnostic would be a runtime/software checkpoint, not a source-physics
or E0–E6 validation result.

## Exact case and scope

Run candidate6 once on GPU with case ID `dry_four` and only the candidate5
allowlisted input directory
`containers/flutas/candidate5/cases/source_boundary/dry_four/`. Its exact
solver-input triplet is:

| Staged file | SHA-256 |
| --- | --- |
| `dns.in` | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` |
| `source-boundary.in` | `f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0` |
| `vof.in` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |

These hashes are the `dry_four` row in input schema v0.1, SHA-256
`20afc81766fd0068bbc24732339412c5e10ca8707e40557038d68eee6c1139db`; the
candidate5 fixture inventory is
`containers/flutas/candidate5/cases/source_boundary/SHA256SUMS`, SHA-256
`a04cbac29baf540bce1c969ad0df2c081b0dc2a3a7a31177606c34602d7978f1`.
Stage those three files as regular files in a newly created, read-only
run-specific directory whose leaf is `dry_four`. This preserves the candidate
manifest adapter's exact case-root interface. Reject any changed bytes, symlink, hardlink, extra
file, restart/checkpoint, or unlisted input. Bind exactly those relative paths
and bytes in the run manifest. Do not stage other cases. In particular, the
top-level `containers/flutas/cases/source_boundary/dry_four/` copy is not
allowlisted here: its `source-boundary.in` hash is
`c9230cc43fc2a8c5a33b52429d8fbdde626fc4fc8b7acf3cd5d4de0c494b37b6`.

The fixture is 160×84×40 = 537,600 cells on a 4.0×2.1×1.0 m domain, with
uniform 0.025 m spacing and one halo. It declares 14 fixed intervals of
0.0001 s (planned diagnostic time 0.0014 s), no restart, `slot_count=0`, and
schedule `[0,0)`. Gravity, DNS background velocity, forcing, imposed wall
motion, and surface tension are zero; initial VOF is empty. The source-boundary
parameter `(0,0,-4.8) m/s` is declared in `source-boundary.in`, but with no
slots and schedule `[0,0)` no mask receives it; the DNS background velocity is
zero. The case name does not mean that four outlets exist. This run exercises
the source-enabled executable's zero-slot/empty-source setup and quiescent GPU
path; it does not exercise an active source.

## Frozen diagnostic predicates

The proposed pass criteria are structural/software checks for this one input:

1. The independent preflight parser reproduces every allowlisted byte-bound
   field and the fixture relations above, including the declared empty initial
   VOF, zero background velocity and no restart. The case has 15 planned
   velocity states and 14 planned intervals. Input parsing alone does not prove
   the observed interior field state.
2. Normal completion is accepted only with solver exit code 0, all 14
   intervals and states U0–U14 recorded, finite time/diagnostic values, and no
   unclassified stop. For each state, mass-ledger and velocity-audit native
   time strings must join exactly, and velocity-audit `dt_s` must equal the
   frozen fixed step. Derive native time with the pinned source's binary64
   AB2 operation order:
   `f_t12=(1+0.5*(dt/dto))*dt + (-0.5*(dt/dto))*dt`, then
   `time=time+f_t12`. Do not replace this with repeated addition of
   `fixed_step_s`: for this constant-step input, native U2 and U14 are
   `0.00020000000000000004` and `0.0014000000000000004`. Keep native
   accumulated clocks distinct from the v1.2 index-derived diagnostic clock
   `time_start_s+state_index*dt`.
   Also check `time.out` at U1–U14 and `vof_info.out` at U0–U14 as the
   producer's fixed-width E15.7 records; the latter has zero alpha minimum,
   maximum and water volume at every state. Validate the final `scalar.out`
   time/dto/step record and the single `restart_checkpoints.out` index/time
   record against native U14. These outputs use their declared formats and
   must match the same source-ordered clock, with finite fields and exact row
   counts.
3. All declared v1.2 stage scans complete. Each row has finite values,
   `mismatch_count=0`, `nonfinite_count=0`, and `max_abs_error=0`; on these
   successful rows, `first_bad_i/j/k`, `expected`, and `observed` are the
   schema's `not_applicable` failure-detail fields. Each declared empty slot
   class has its prescribed zero scanned-cell count. Air `rho` and `mu` remain
   finite even though the water phase is absent. Every consumed interval's
   timestep guard passes under the frozen v1.2 formula. At U14, only
   `guard_pass` is `not_applicable`; all numeric operands, bounds, and ratios
   remain finite and conform to the schema. The independent analyzer
   reproduces exact row keys, ordering, counts, prefixes, and byte hashes.
4. The inherited tables follow v0.3 H1 for N=14 and S=0: zero data rows in
   `source-flux.csv`; 14 rows each in `source-offmask.csv` and `rate-check.csv`;
   and 15 rows each in `boundary-ledger.csv`, `mass-ledger.csv`, and
   `velocity-audit.csv`. The v1.2 normal-completion roster has 672 phase rows,
   516 velocity rows, and 15 timestep rows. The host helper's 64 phase rows
   are `2*(8+24)`: two helper profiles, each with one eight-row `pre_vof_x`
   group and one 24-row `pre_momentum` group. Production emits three
   eight-row directional groups plus one 24-row `pre_momentum` group for
   each interval, so the exact normal count is
   `14*(8+8+8+24)=672`. Thus the helper exercises only part of the phase
   call roster; its 64 rows are not a competing production count. The
   production velocity count is `(1+3*14)*12=516` (initial U0 plus three
   12-row groups per interval), and timestep count is `14+1=15`. The
   amendment reviewer must verify this source-to-roster mapping for the exact
   candidate before launch. The helper loop is in
   [`candidate5_observability_helper.f90`](../containers/flutas/candidate6/tests/candidate5_observability_helper.f90),
   and production stage hooks are in the pinned
   [`candidate6 source patch`](../containers/flutas/candidate6/source-boundary.patch).
   Freeze absent-phase handling before launch: the dry velocity-audit row has
   `interface_cell_count=0`, `interface_courant_defined=0`, and stored
   `interface_advective_courant_max=0`, with that Courant value explicitly
   undefined because the interface set is empty. Air density and viscosity
   remain finite. The dry output annex may check the exact schema, byte
   preservation, row keys/counts, finite fields, and applicable frozen zero
   summaries read-only. It must not label those summary checks a raw ledger or
   conservation reconstruction.

   Preserve the v0.3 rate meanings: measured bottom rate is the signed
   total-volume sum `-w*area` over the bottom face, including air. It is not
   bottom liquid flux or `velocity-audit.bottom_out_m3_s`, which is the
   positive part of the net bottom velocity-face sum. On this stationary dry
   fixture both should be zero, but the semantics remain distinct. Any
   zero-denominator or absent-water field must follow an explicitly frozen
   dry-case encoding; do not divide by zero, invent a finite sentinel, omit a
   required row, or infer `not_applicable`. If a required representation is
   unresolved or unsupported, the output is inconclusive and this attempt
   cannot pass; do not loosen a predicate after seeing results.
5. The supervisor observes actual GPU use and the selected device, and the
   immutable output bundle passes independent post-run structure/hash checks.

The helper result is not a full 14-interval solver run; the counts above
reconcile its limited helper calls with the production call roster and do not
make helper evidence equivalent to runtime evidence.

Only a passing independent check supports the narrow claim that this exact
candidate completed the prescribed quiescent, zero-slot execution/telemetry
diagnostic for this exact fixture, within the recorded envelope, and that the
retained declared outputs passed the small dry annex's read-only byte and
semantic checks. This is not source-boundary or VOF physical qualification.
For this runtime-only diagnostic, defer generalized H5 raw directional flux,
momentum, pre/post-clipping, and full raw-ledger reconstruction. The retained
summary tables alone do **not** establish raw-field conservation or prove
that no transient/interior liquid or velocity anomaly occurred; report those
as unassessed. Do not claim source-dose or momentum accuracy, active-slot
source-mask behavior, multi-slot return-flow conservation, pulse-edge
behavior, clipping or boundedness between captured states, VOF-to-parcel
transfer, plume physics, ground impact/map metrics, `L95`, useful fraction,
suppression efficacy, grid or timestep convergence, or field validity. Do not
infer water or foam performance or a fourfold gain.

## Immutable outputs and failed-attempt handling

Create a new, unique `results/runs/` bundle before container creation; refuse
an existing destination and never overwrite evidence. Copy native output bytes
unchanged and hash both their native and canonical copies. Preserve the exact
candidate-build receipt and OCI layout reference, staged read-only input
snapshot, in-bundle host snapshot, preflight result, full command/argv and
environment, container configuration, stdout/stderr, solver exit status,
analyzer output, resource samples, stop/cleanup events, termination proof,
and a sorted SHA-256 inventory. Retain the primary launch result or failure
record. Once the locked runner has returned and released the GPU lock, the
launcher runs the CPU-only finalizer automatically. It saves the exact
output-check report at `analysis/dry-output-annex.json` and invokes the
unchanged candidate6 manifest adapter only after solver exit 0 and a complete
output check. Only that pass may produce
`analysis/adapter-run-metadata.json` and root `manifest.json`. For a failed or
incomplete attempt, do not create a normal manifest. In either case, write a
finalization result and sorted root `SHA256SUMS`. That inventory lists every
singly-linked regular file except itself and
`metadata/SHA256SUMS.sha256`; the sidecar records its digest. Preserve every
file produced before a stop, including partial CSVs, raw artifacts, logs and
all supervisor samples; do not rewrite a failed run as a normal run.

The frozen native/canonical output roster comprises all of the following:

| Native output or bundle artifact | Canonical bundle identity | Frozen quantity/count |
| --- | --- | --- |
| Six v0.3 tables under `data/restas_*.csv`: `source-flux`, `source-offmask`, `rate-check`, `boundary-ledger`, `mass-ledger`, `velocity-audit` | The exact same-named root-level canonical files `restas_source-flux.csv` through `restas_velocity-audit.csv` | H1 dry N=14/S=0 counts above; native and canonical bytes/hash match |
| `data/restas_phase-property-stage-audit.csv`, `data/restas_boundary-velocity-stage-audit.csv`, `data/restas_timestep-restriction.csv` | Same byte stream at root-level `phase-property-stage-audit.csv`, `boundary-velocity-stage-audit.csv`, `timestep-restriction.csv` | 672, 516, and 15 rows on normal completion, exact v1.2 order/prefix |
| `data/restas_timestep-inputs.json` | Same byte stream at root-level `timestep-inputs.json` | Preserve producer bytes exactly; verify the exact-byte SHA and parsed schema/operands read-only |
| CPU finalizer-generated `manifest.json` after full normal pass only | Root-level `manifest.json` | Exact frozen `candidate5-run-manifest-v2` schema; do not add keys |
| Finalizer report and command | `analysis/dry-output-annex.json`, `analysis/adapter-run-metadata.json`, `metadata/finalizer-command.json`, `metadata/finalization-result.json` | Retain the independent check, adapter inputs/status, and success/failure reason; no normal manifest after failed or incomplete output |
| Full bundle checksum inventory | Root `SHA256SUMS`; `metadata/SHA256SUMS.sha256` | Sorted full regular-file inventory excluding itself and its sidecar; sidecar records the inventory digest |
| Initialization snapshots: five 3D fields and four midplane fields | `canonical/initial/3d/field-01`…`field-05`; `canonical/initial/midplane/field-01`…`field-04` | Exactly one of each role; the map names exact fields, calls, shapes, types, layout, units and bytes |
| Final checkpoint: eight arrays | `canonical/final-checkpoint/array-01`…`array-08` | Exactly eight roles; the map names exact fields, calls, shapes, types, layout, units and bytes |
| All other solver text diagnostics and all run/control evidence | Exact native paths plus mapped paths under `logs/` and `metadata/` | Include full solver stdout/stderr, command/argv/environment, container configuration, exit status, analyzer output, resource samples, stop/cleanup events and termination proof, preflight and staged-input snapshot, candidate receipt/image identity, and sorted SHA-256 inventories |

Before launch, exact-review
[`dry-output-map.json`](dry-output-map.json), bound by the final primary
disposition. Its SHA-256 is
`47be3ec5072fdea9ea331a8f1b604e87eea3efc525d28559bca7404f7478d87c`. The map
binds every native path to its canonical identity above. For every file it
records role, writer/call-stage, variable or table, exact native and canonical
paths, format, shape/row-count bound, dtype, endianness, storage order, units,
and byte bound; array fields also record index bounds. The exact native producer
roster has 37 files and a conservative native byte bound of 57,447,891 bytes,
including the whole-record CSV envelope. The 64 MiB producer allocation leaves
9,660,973 bytes above that native bound. Native-plus-canonical copies are
114,895,782 bytes before runner evidence. `grid.out` is 3,192 bytes and
`geometry.out` is exactly 119 bytes for this pinned compiler, platform, and
input. The post-run inventory records the SHA-256 for every emitted byte
stream. Enumerate the source/config-selected filenames and output cadence from
the exact candidate and case. All output units and archival-field meanings are
source-mapped; the pressure and momentum-history arrays are retained as solver
outputs, and no acceptance predicate depends on their numeric values. An
unresolved name, shape, encoding, cadence, or byte bound blocks launch; no
glob-based acceptance or unlisted extra solver output is allowed. Copy
native streams unchanged and verify byte identity for each mapped pair.
Preserve every produced file on success or failure, including partial files.
The timestep-input JSON is not regenerated or normalized: retain and hash the
exact producer bytes, then independently parse its values against v1.2.
Preserve a separately versioned `source-evidence-manifest.json` only if the
reviewed dry-scope annex defines it; never add keys to the frozen v1.2
manifest.

The small dry output annex for this runtime-only attempt is read-only. It checks
the map and exact-byte hashes, input/source manifest binding, strict headers,
row/key order and frozen H1/v1.2 counts. Its exact dry predicates are: the
source-flux file has a header and no data rows; all 14 offmask rows and all
source/offmask rates and residuals are zero; all 15 boundary/mass rows have
zero water flux, inventory, and residual fields; all 15 velocity rows have
zero recorded boundary/divergence diagnostics and the empty-interface
encoding above; every v1.2 stage scan has the exact derived cell count, zero
mismatches/nonfinites/error, and `not_applicable` failure details; every
consumed guard passes; and all U14 operands are finite with only
`guard_pass=not_applicable`. Its signed bottom total-volume rate check uses
`-w*area`, including air, and remains distinct from the velocity audit's
positive-part `bottom_out_m3_s`. These are checks of retained declared
outputs, not independent reconstructions from raw fields. The annex does not
perform generalized raw directional-flux or momentum reconstruction,
pre/post-clipping checks, or full raw-ledger reconstruction. These are
explicitly deferred, as are positive-dose/source-vector cases and VOF/parcel
handoff arrays, because this fixture has no configured slot or liquid
transfer. Summary agreement must not be described as independent raw
conservation validation.

This amendment permits at most one solver invocation. Any nonzero exit,
controlled audit stop, guard failure, analyzer rejection, incomplete prefix,
timeout, sampling fault, or unverified termination is a failed attempt. Keep
its exact prefix and failure reason, stop the ordered GPU queue, and do not
run `quiescent_one` or `quiescent_four`. A retry or changed candidate/input
requires a new prospective amendment and fresh independent review.

## Candidate, resource envelope, and supervision

The latest retained candidate6 build evidence is
`containers/flutas/candidate6/evidence/full-source-build-20260928T093141Z-4092509/`:

| Identity | Recorded value |
| --- | --- |
| Pinned FluTAS commit | `598210616bebd51f7d51f61455f196e6f3479916` |
| Candidate6 patch SHA-256 | `3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee` |
| Builder base image ID | `sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8` |
| Built local image ID | `sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b` |
| Candidate OCI image-manifest digest | `sha256:0cbfcc17c72484c004663ee009e320cbb551bf80f534cfdb1a9d3db1297b8972` |
| Retained executable SHA-256 | `0c3563ed2bbd8a29586d1cdd9f61b8e53087854950e440812492154839b2bb58` |
| Compiler / code object | NVHPC 26.9; `sm_120.cubin` present |

This proves a recorded CPU build and code-object inspection, not a GPU runtime.
The latest candidate6 CPU regression evidence is
`containers/flutas/candidate6/evidence/source-helper-check-20260928T094855Z-4099677/`;
it reports exit 0 for the host source-boundary/observability regressions at
two CPU / 6 GiB, with no GPU runtime, solver driver, or advanced physical time.
The SHA-256 of its `SHA256SUMS` inventory is
`3110a29549f5052b2e9a7016ecb69a2e687726ac72a70e58dd59a34ccce7ce03`,
matching that bundle's `SHA256SUMS.sha256` record.

The archived Astra Max exact review returns **ACCEPT at retained-build,
static-wiring, and host-regression scope only**:
[`FLUTAS_CANDIDATE6_BUILD_HOST_EXACT_REVIEW_20260928T1128Z.md`](../docs/reviews/FLUTAS_CANDIDATE6_BUILD_HOST_EXACT_REVIEW_20260928T1128Z.md),
SHA-256 `9b4bd5ccb2d5dfec6080d1c3a0fa13b86f73579db9dc8b345e82086bf26a633b`.
It does not approve a GPU runtime or source run. The earlier H4 two-halo
successor separately accepts the bounded helper/regression scope (review
SHA-256 `176475954e7540739b7267f0a6d54cf6e298624dfb0141e7d5fa36616c3bf2d4`).
Before launch, bind the exact executable and candidate image to the retained
offline layout
[`candidate6 OCI layout`](../results/runs/candidate6-oci-layout-20260928T1139Z/layout/index.json).
Its index selects OCI image-manifest digest
`sha256:0cbfcc17c72484c004663ee009e320cbb551bf80f534cfdb1a9d3db1297b8972`,
distinct from local Docker/config ID
`sha256:c0b459afb9b80ce788ecae69c118fae0e3095b5ddb9839c9f2fb56e34ac3b11b`.
For this amendment only, define v0.3 H6 receipt field `builder_image_digest`
as the pinned builder base image's Docker/config ID
`sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8`,
not an OCI manifest digest; the base tag and evidence are in
[`build metadata`](../containers/flutas/candidate6/evidence/full-source-build-20260928T093141Z-4092509/metadata.txt),
[`base toolchain`](../containers/flutas/candidate6/evidence/full-source-build-20260928T093141Z-4092509/base-toolchain.txt), and
[`build log`](../containers/flutas/candidate6/evidence/full-source-build-20260928T093141Z-4092509/docker-build.log).
The immutable OCI archive is
`results/runs/candidate6-oci-layout-20260928T1139Z/docker-save.tar`,
25,230,410,240 bytes, SHA-256
`29272b7453a3ea5a33a97b97f4f21e8cabca53191e4f2e85896cb52a8cbfd49b`; the
layout index SHA-256 is
`3dba6c336c0e1b6113f8489357660e954d8c4220c421f5001c1be8354328deb4`.
The exact CPU-only identity verifier is
[`flutas_candidate6_identity.py`](../scripts/flutas_candidate6_identity.py),
SHA-256 `abfeaebcab4882c538e66f9aed782c8fccd2528a49e730730bfee09d47486231`;
its completed preflight evidence is
[`candidate6-identity-preflight-20260928T1200Z.json`](../results/runs/candidate6-identity-preflight-20260928T1200Z.json),
SHA-256 `5d112d1d0bfa904ac225038fd21c53f8183e5bad38e8820900f237b7fa304327`.
It verified the nested receipt, source/build inputs, retained executable,
archive bytes, all 21 OCI layers, local Docker candidate image, and builder
image. It reports `solver_started=false` and `gpu_requested=false`.
The amendment reviewer must independently verify this run's exact OCI
descriptors/blobs, config, platform, DiffIDs, executable, patch, build command,
and inputs; the launcher must rerun the identity check and reject any other
identity. The general H6
verifier mutation matrix may be deferred for this one diagnostic only and
remains open before broader reuse; broad H6 acceptance remains open. Produce
the already-retained exact H6 `candidate-build.json` receipt and obtain
amendment review of that receipt, both distinct image identities, executable,
source/patch/build inputs, and all amendment-specific predicates before launch.
Any hash change
selects a new candidate and requires review.

Before this run, refresh `make doctor`, free disk, and GPU state; record the
snapshot. The exact source roster, native byte bounds, and geometry output are
captured in the output map above. Budget the immutable OCI layout separately,
with its own measured size and disk accounting; do not conflate OCI storage
with the per-run disk stop threshold. If either bound or its disk budget is
unresolved, the launch gate remains closed.

Use the supervisor's implemented envelope: one MPI rank, one application
thread, 2-core CPU quota, 16 GiB hard cgroup memory limit, 24 GiB sampled VRAM
stop threshold, 1 GiB per-run sampled disk stop threshold, 64 MiB sampled
attached-log stop threshold, 16 MiB supervisor event-file limit, and
1,800 seconds solver wall-time stop. The unique absolute run-bundle root is
the only `disk_roots` entry; supervisor evidence is nested inside that root.
The immutable OCI archive/layout remains outside and is budgeted separately.
Disk and attached-log thresholds are sampled stop triggers, not filesystem
quotas: output can grow between samples and during shutdown. The 1 GiB
threshold has at least 196.7 GiB of host free-space headroom in the latest
snapshot, while declared normal native-plus-canonical output is under
110 MiB. Preserve the measured bundle size and any threshold overshoot. These
are engineering limits, not measured demand or scientific tolerances; do not
raise them from runtime results under this amendment.

The lock-owning supervisor samples process and cgroup-v2 CPU/memory, GPU
memory and utilization, disk use, solver stage, and container state before
container creation and throughout shutdown. After `docker start --attach`, it
samples immediately; while no running GPU-activity sample has been observed,
it opportunistically samples every 0.25 seconds for at most the first second.
Once running GPU activity is observed, or that one-second window expires, it
returns to the one-second cadence. Each sample retains the same 0.8-second
dispatch budget, and no valid sample gap may exceed 2 seconds. The bounded
startup burst reduces missed short GPU pulses but cannot guarantee a sample
over every very short execution. The diagnostic remains inconclusive if no
running sample demonstrates the required GPU evidence; do not infer activity
from a post-exit sample. Any missing or nonfinite sample, gap over 2 seconds,
reached threshold, or wall timeout requests graceful stop within 1 second;
allow 10 seconds, then force-kill the
container and solver process group within 1 second. Within 30 seconds attempt
to verify Docker `State.Running=false` and no surviving solver/container
child. Keep the shared GPU lock until both checks pass; on uncertainty, retain
the lock and escalate. The 10+1+30 second shutdown schedule is a target, not a
guaranteed upper bound. If termination cannot be proved within 30 seconds,
quarantine the job and keep the GPU lock held until proof arrives; this can be
indefinite. Preserve configured limits, all samples/gaps, trigger and signal
times, exit states, and termination proof.

The updated lock owner must pass CPU-only fake-process/container lifecycle
checks for CPU and memory limits, wall-time stop, sampler failures, timeout,
graceful/forced stop, surviving children, Docker-state verification, and
lock-retention/release ordering. A per-job thread cap or an exited client
process does not satisfy this condition. A harmless CPU-only container probe
showed that Docker's `stats --no-stream` exceeded both its 0.25-second and
0.75-second trial deadlines. The host cgroup-v2 files provided CPU/memory data
for a live test container in under 1 millisecond, and five host `nvidia-smi`
samples each completed in about 0.032 seconds. These probes requested no GPU
and ran no FluTAS. The integrated cgroup-v2 sampler still requires the exact
review below.


## Gate after this diagnostic

Before launch, the exact reviewer must accept this amendment, the dry-case
input parser and source-derived dry-output summary checks, expected native
record values, row keys/counts and zero-denominator rules, exact candidate6/OCI
receipt, static artifact bound, current resource snapshot, and lock-owner
stop/release behavior. The summary checks do not reconstruct raw fluxes or
fields. The primary then records **one-run dry diagnostic only** as its
disposition. If any item
fails or remains unspecified, do not launch.

After a run, an independent reviewer audits the immutable bundle and every
claim against the frozen inputs, output schemas, raw evidence that was
actually captured, and supervisor termination record. Only a complete pass
may open the next prospective gate: `quiescent_one`, under the full applicable
v0.3 source-release checks and a separate exact review. This dry diagnostic
does not approve that case, B1-pre/B1-runtime/B2, any mass/momentum tolerance,
or an E0–E6 scientific gate.
