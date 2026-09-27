# Candidate5 producer observability interface

**Status:** Primary-frozen implementation interface revision 1.2, pending
independent code and numerical review. This document permits candidate5
instrumentation work only. It approves no tolerance, timestep margin, solver
case, GPU source run, or scientific result. Candidate4 and its evidence remain
immutable.

The source-readiness audit found that candidate4 does not serialize stage-indexed
alpha/rho/mu ghost evidence or a complete requested/applied boundary-vector
audit, and its fixed-step route does not evaluate the full AB2 timestep bound.
Candidate5 adds compact summaries from full runtime scans; it does not dump all
successful ghost or boundary arrays. Every scanned value is checked, and each
failed summary retains the first offending location and expected/observed
values. Independent review must decide whether this representation is
sufficient before source execution.

## Versioned producer files

The producer schema identifier is
`candidate5-observability-v1.2`; the run manifest's `manifest_schema` is
`candidate5-run-manifest-v2`. The manifest pins the producer, candidate,
image, case, input, analyzer, and shared-schema identities. It also records
planned and completed interval counts, the controlled stop reason and indices,
exact output row counts and hashes, scan/reduction order, timestep inputs,
runtime samples, and the pressure-solver disposition. JSON is strict UTF-8
without BOM, has unique keys, sorted keys, compact separators, no non-finite
JSON values, LF line endings, and one trailing LF. Counts and indices are JSON
integers; physical values are canonical decimal strings. Each CSV has strict
UTF-8 without BOM, one exact header, LF line endings, canonical decimal fields,
no duplicate keys, canonical row order, and one trailing LF. No CSV field is
quoted unless RFC 4180 requires it; this schema's fields never require quoting.
Normal completion and the three declared guard/audit-stop prefixes are
analyzable. Any unrecognized solver stop fails closed. First-failure value
fields use the explicit exception defined below.

`phase-property-stage-audit.csv` has these columns, in order:

```text
state_index,transport_interval_index,stage_id,face,source_class,property,scanned_cells,mismatch_count,nonfinite_count,max_abs_error,first_bad_i,first_bad_j,first_bad_k,expected,observed
```

The on-disk header is a single line. `property` is `alpha`, `rho`, or `mu`.
`face` is one of `xlow`, `xhigh`, `ylow`, `yhigh`, `zlow`, `zhigh`.
`source_class` is one of `active_slot`, `inactive_slot`, `top_offmask`,
`bottom_return`, `other_inflow`, `other_outflow`, or `periodic`. For this
paired-return fixture, the permitted face/class set is `(xlow,periodic)`,
`(xhigh,periodic)`, `(ylow,periodic)`, `(yhigh,periodic)`,
`(zhigh,active_slot)`, `(zhigh,inactive_slot)`, `(zhigh,top_offmask)`, and
`(zlow,bottom_return)`. Other source classes are reserved; adding them requires
a prospective schema revision. Stage properties are exact: `pre_vof_x`,
`pre_vof_y`, and `pre_vof_z` each scan only the actual `alpha` array used by
that directional VOF sweep (`vof`, `dvof1`, and `dvof2`, respectively).
`pre_momentum` scans the actual post-advection `vof`, `rho`, and `mu` arrays
after `update_property`, generic `boundp`, and the source-aware refresh. Never
synthesize or report an observed `rho` or `mu` array at a VOF stage where the
solver does not have that stage-local property field.

The paired-return inputs are frozen at `nx=160`, `ny=84`, `nz=40`,
`nh_d=nh_u=1`; phase arrays include indices `0:nx+1`, `0:ny+1`, `0:nz+1`.
Derive the slot-cell set from the hashed `source-boundary.in` input, validating
that masks are in bounds, non-overlapping, and have the declared slot count.
One-slot has 240 mask cells; four-slot has 960; dry has zero. For phase rows,
scan exactly these sets:

| Face/class, in declared order | Cell indices | Expected cells |
|---|---|---:|
| `(xlow,periodic)` | `i=0`, `j=0..ny+1`, `k=0..nz+1` | `(ny+2)(nz+2)=3612` |
| `(xhigh,periodic)` | `i=nx+1`, `j=0..ny+1`, `k=0..nz+1` | 3612 |
| `(ylow,periodic)` | `j=0`, `i=1..nx`, `k=0..nz+1` | `nx(nz+2)=6720` |
| `(yhigh,periodic)` | `j=ny+1`, `i=1..nx`, `k=0..nz+1` | 6720 |
| `(zlow,bottom_return)` | `k=0`, `i=1..nx`, `j=1..ny` | `nx*ny=13440` |
| `(zhigh,active_slot)` | `k=nz+1`, configured slot cells only when `schedule[k]` is active | 240/960 when active, otherwise 0 |
| `(zhigh,inactive_slot)` | `k=nz+1`, configured slot cells only when `schedule[k]` is inactive | 240/960 when inactive, otherwise 0 |
| `(zhigh,top_offmask)` | `k=nz+1`, interior `i,j` outside every configured slot | 13200/12480/13440 for one/four/dry |

Here `schedule[k]` is the source active on half-open interval `[step_on,
step_off)`. An empty class still has its declared zero-count row. The producer
and analyzer independently derive these sets and counts from the pinned input;
counts equal visited cells, not a producer-selected sample. The x-face scan
owns x/y periodic corners; y-face scans exclude x halos; z-face scans exclude
x/y halos. For a periodic expected value, wrap every periodic coordinate in
the scanned location (`0→n`, `n+1→1`) and retain the z coordinate. This defines
edge/corner ownership without duplicate scans. Compare the scanned value to
the wrapped value of the same actual stage array.

For z faces, use the actual normal `w` at the corresponding face to choose the
boundary rule. At `zhigh`, `w<0` means inflow: alpha is one only for a scheduled
active slot and zero for all other top inflow; for `w>=0`, generic zero-gradient
extrapolation retains the adjacent interior value. At `zlow`, `w>0` means
reverse inflow and sets alpha to zero; for `w<=0`, generic extrapolation
retains the adjacent interior value. For `rho` and `mu` at `pre_momentum`, the
same inflow branches use the actual phase-specific water/air property values;
outflow/zero-flow branches use the corresponding interior property value.
Every expected value and scanned value must be finite, except that a
non-finite value is preserved under the failure rule below. Record rows after
each actual boundary fill and source-aware refresh that feeds x, y, and z VOF
fluxes, and after the post-advection property refresh immediately before the
momentum update.

`boundary-velocity-stage-audit.csv` has these columns, in order:

```text
state_index,transport_interval_index,stage_id,face,source_class,component,scanned_cells,mismatch_count,nonfinite_count,max_abs_error,first_bad_i,first_bad_j,first_bad_k,requested,applied
```

`component` is `u`, `v`, or `w`. For this paired-return fixture, the permitted
face/class set is `(zhigh,active_slot)`, `(zhigh,inactive_slot)`,
`(zhigh,top_offmask)`, and `(zlow,bottom_return)` for each component. Emit all
12 keys at every applicable stage, including declared empty classes as
zero-scanned rows. For both z faces and all components, scan the exact padded
rectangle `i=1-nh_u..nx+nh_u`, `j=1-nh_u..ny+nh_u` (therefore `0..nx+1` and
`0..ny+1`), with `nh_u=1`. The total rectangle has 13932 values. Classify top
cells after periodic wrapping: active/inactive slot membership uses the
schedule at the velocity field's `state_index`; all other padded positions
are `top_offmask`. `bottom_return` owns the entire padded lower rectangle.
For U/V, the upper ghost is at `k=nz+1` and the lower ghost at `k=0`; expected
ghost values are the Dirichlet reflection `2*requested_tangent-interior`
using interior `k=nz` at the top and `k=1` at the bottom. For W, the top
normal face is `k=nz` and has the requested source-normal speed on scheduled
slot cells, zero elsewhere. The bottom normal at `k=0`, including
periodic-padded indices, is the source return velocity. Reproduce its exact
candidate operation order: `face_area=dl(1)*dl(2)`; initialize `Q=0`; visit
configured slots in input order, then `j` ascending, then `i` ascending; for
each active cell accumulate `Q=Q+max(0._rp,-expected_w)*face_area`; and set
`return_velocity=-Q/(real(nx*ny,rp)*face_area)` when `Q>0`, otherwise zero.
Do not replace this reduction with `mask_cell_count*rate`, reorder the sum, or
reassociate the denominator. The `requested` column is the expected value at
the scanned storage location after the staggered mapping; `applied` is the
actual stored value there.
Use stage IDs `initial_u0`, `projection_override`, `corrected_endpoint`, and
`pre_vof`. In this table, `state_index` identifies the velocity field:
`initial_u0` is `(state_index=0, transport_interval_index=-1)`; `pre_vof` for
interval k is `(k,k)`; projection override and corrected endpoint for
interval k are `(k+1,k)`. Phase class membership uses `schedule[transport_interval_index]`;
velocity class membership uses `schedule[state_index]`, so endpoint `(2,1)`
uses the newly active state-2 profile. This also defines initial U0 and pulse
edges. A full scan checks every declared location. Successful raw vectors need
not be written per cell under this interface; the exact comparison predicate
is frozen below and remains separate from any scientific acceptance limit.

`timestep-restriction.csv` has these columns, in order:

```text
state_index,time_s,dt_s,dtic_raw_s_inv,dtic_used_s_inv,zero_advection_fallback,
nu_max_m2_s,h_min_m,dlmini_m_inv,dtiv_s_inv,dtik_s_inv,dtig_s_inv,capillary_active,
dtmax_s,fixed_step_factor,dt_over_dtmax,guard_pass
```

Each normal run plans `N` intervals from frozen input and writes one row for
each state `U_0..U_N`; the fixture has `N=14`. `state_count=N+1` and
`interval_count=N` in the manifest mean **planned** counts, not counts inferred
from output rows. The table has only `state_index` as a join key. Row k is
state `U_k` at `time_s=t_0+k*dt`. The bound below reproduces the pinned
upstream AB2, two-phase, non-heat path; it is an implementation guard, not an
approved accuracy criterion.

From the actual staggered velocity state, for every interior cell
`i=1..nx`, `j=1..ny`, `k=1..nz`, compute the three directional inverse-time
The producer computes `dtic_raw` from the actual staggered velocity state. For
every interior cell and direction, it uses the upstream `chkdt_tw` rates:

```text
ux = abs(u(i,j,k))
vx = 0.25*abs(v(i,j,k)+v(i,j-1,k)+v(i+1,j,k)+v(i+1,j-1,k))
wx = 0.25*abs(w(i,j,k)+w(i,j,k-1)+w(i+1,j,k)+w(i+1,j,k-1))
dtix = ux*dxi + vx*dyi + wx*dzfi(k)

uy = 0.25*abs(u(i,j,k)+u(i,j+1,k)+u(i-1,j+1,k)+u(i-1,j,k))
vy = abs(v(i,j,k))
wy = 0.25*abs(w(i,j,k)+w(i,j+1,k)+w(i,j+1,k-1)+w(i,j,k-1))
dtiy = uy*dxi + vy*dyi + wy*dzfi(k)

uz = 0.25*abs(u(i,j,k)+u(i-1,j,k)+u(i-1,j,k+1)+u(i,j,k+1))
vz = 0.25*abs(v(i,j,k)+v(i,j-1,k)+v(i,j-1,k+1)+v(i,j,k+1))
wz = abs(w(i,j,k))
dtiz = uz*dxi + vz*dyi + wz*dzci(k)

dtic_raw = max over every interior cell and direction of (dtix,dtiy,dtiz)
```

`dxi`, `dyi`, `dzi`, `dzfi(k)`, and `dzci(k)` above are the actual `real(rp)`
operands passed by the selected application to `chkdt_tw`; they are not
reconstructed from a simplified spacing after the run. `timestep_inputs` stores
the three scalar inverse spacings and full dummy-array `dzfi`/`dzci` operands
as round-trippable decimal strings, as well as the corresponding source
spacings. The vertical inverse arrays retain indices `0..41` for this fixture.
The candidate validates each stored inverse against the pinned application's
`1._rp/spacing` initialization. `src/initgrid.f90` builds `dzf` from successive
rounded face-coordinate differences, builds `dzc` from adjacent `dzf` values,
and extends both arrays over the dummy halos. Thus the fixture's vertical
values may differ by representable roundoff even for a nominally uniform grid;
neither producer nor analyzer may replace the actual 42 entries with a uniform
constant. The timestep audit and independent analyzer use the stored inverse
operands themselves. Preserve the source expression order shown above. Source
mode validates a single rank over the full grid, so the upstream MPI maximum
reduction has exactly one contributor.

`dtic_used=1 s^-1` only when `dtic_raw` is exactly zero; otherwise it equals
`dtic_raw`. Reproduce the remaining restriction using the source expression
order at `src/chkdt.f90:96–107` (commit
`598210616bebd51f7d51f61455f196e6f3479916`, pinned source hashes below). `h_min_m`
stores source `dlmin`; `dlmini_m_inv` stores source `dlmini`. The full vertical
dummy-array operation is over the actual `dzfi` operands at indices `0..41`:

```text
dlmin = min(1._rp/dxi, 1._rp/dyi, 1._rp/dzi)
dlmin = min(dlmin, minval(1._rp/dzfi(:)))
dlmini = dlmin**(-1)
nu_max = max(mu1/rho1, mu2/rho2)
dtiv = nu_max * dlmini**2 / cfl_d
dtik = small                                      if sigma == 0
dtik = sqrt(sigma/min(rho1,rho2) * dlmini**3)   otherwise
dtig = sqrt(max(abs(gacc_x),abs(gacc_y),abs(gacc_z)) * dlmini)
dtmax = cfl_c*2._rp*(dtic_used+dtiv
         +sqrt((dtic_used+dtiv)**2
               +4._rp*(dtig**2+dtik**2)))**(-1)
dtmax = min(dtmax, 1._rp/dtik)
```

The analyzer reproduces these exact source operations from the stored inverse
operands and inputs. It compares each reported finite intermediate and result
after parsing its round-trip decimal representation as binary64; algebraic
rewrites such as division by `h_min**2`, putting `h_min**3` inside the capillary
denominator, or division by the unsquared rate denominator are not equivalent
for this contract and must not be substituted. The pinned binary64 build and
producer source must preserve the expression grouping above. If that arithmetic
cannot be reproduced on the analyzer, the mismatch is a review finding; no
post-hoc numerical tolerance is implied by this instrumentation schema.

For every `k<N`, the row records the outgoing fixed `dt_s`; evaluate the guard
at `U_k` before running any stage of interval k. Compute
`dt_over_dtmax=dt/dtmax` when `dtmax` is finite and positive. The guard passes
exactly when all required values and intermediates are finite,
`dt>0`, `dtmax>0`, `fixed_step_factor>0`, `dt_over_dtmax` and
`fixed_step_factor*dtmax` are finite, and
`dt <= fixed_step_factor*dtmax`; equality passes. Otherwise it fails. A
timestep-guard row is conforming only when every diagnostic and ratio is finite.
If evaluation produces a non-finite value or overflow, preserve the failed raw
evidence and nonzero solver exit without substituting a finite sentinel; the
analyzer reports it as nonconforming and cannot PASS it. This also applies to
non-finite derived timestep columns; they are not an accepted guard-stop
encoding. On a finite guard rejection, write and flush `guard_pass=false` at U_k and stop before consuming
interval k. Never rename this failed state as the normal final endpoint. On normal completion only,
include the diagnostic row for planned endpoint U_N with
`guard_pass=not_applicable`; report its finite bound, configured step, factor,
and ratio. `guard_pass` is exactly `true`, `false`, or `not_applicable`.
The analyzer independently recomputes `nu_max`, `h_min`, `dlmini`, `dtiv`,
`dtik`, `dtig`, `dtmax`, `dt_over_dtmax`, and each guard from the pinned inputs and
the reported `dtic_raw`; it validates the exact zero-rate fallback and
`dtic_used`. Successful U/V/W fields are not serialized, so the analyzer cannot
independently reconstruct the observed `dtic_raw` for a run. The exact pinned
producer source scan and independent host tests must therefore verify that
rate's implementation; the adequacy of this compact runtime summary remains an
independent-review decision. Do not describe the analyzer as independently
recomputing `dtic_raw` from runtime fields.

The candidate5 build is adiabatic; reject a heat-transfer build unless the
heat restriction is added by a reviewed schema revision. Require explicit
`fixed_step_factor` input. The fixture records provisional factor `0.2`, but
this schema does not approve it as a stability margin. The fixed `dt=1e-4 s`
crossflow fixtures are expected to violate the guard under the audited static
profile estimate; preserve that failure and do not alter their step or
schedule in this implementation task.

Pin this reconstruction to FluTAS commit
`598210616bebd51f7d51f61455f196e6f3479916` and these upstream source bodies:

| Path | SHA-256 | Use |
|---|---|---|
| `src/chkdt.f90` | `68e9f9592220b6f7a80366e60ccceb0595685d7324977c3710656aab15b0e661` | `_USE_VOF` `chkdt_tw` staggered rates and full restriction |
| `src/apps/two_phase_inc_isot/param.f90` | `153519b5efb1be6b454a57a7bb6a96d7803511effe5d376e4b993df8cd8e4507` | `small`, AB2 `cfl_c/cfl_d`, selected application |
| `src/types.f90` | `b356113a254a9d0e18c6ee4490004580ef8049a6b37469caf4fb820144aeb142` | `rp` kind selection |
| `src/initgrid.f90` | `87010cb1b014355eb70b299264d5b6cd274ab3248c309906a39ac4a66ab8ca28` | `dzf/dzc` coordinate differences and dummy-range halo extension |

For `time_scheme='ab2'`, upstream sets `cfl_c=1` and `cfl_d=1/6`.
In the selected application, `machine_epsilon=epsilon(pi)`,
`precision_digits=precision(pi)`, and
`small_s_inv=machine_epsilon*10**(precision_digits/2._rp)` from that same
compiled real kind. The candidate build must leave `_SINGLE_PRECISION` undefined,
so `rp=KIND(0.0D0)` and is binary64. For the pinned NVHPC 26.9 build,
`real_kind` is JSON integer `8` and `precision_digits` is JSON integer `15`;
the exact compiler flags and executable identity are pinned in build evidence.
The `timestep_inputs` object has exactly
these keys: `time_scheme`, `time_start_s`, `real_kind`, `precision_digits`,
`machine_epsilon`, `small_s_inv`,
`cfl_c`, `cfl_d`, `rho1_kg_m3`, `rho2_kg_m3`, `mu1_pa_s`, `mu2_pa_s`,
`dx_m`, `dy_m`, `dz_m`, `dxi_m_inv`, `dyi_m_inv`, `dzi_m_inv`,
`dzc_m`, `dzf_m`, `dzci_m_inv`, `dzfi_m_inv`, `sigma_n_m`, `gravity_m_s2`,
`fixed_step_factor`, and `fixed_step_s`. `dzc_m`, `dzf_m`, `dzci_m_inv`, and
`dzfi_m_inv` are arrays of 42 decimal strings for source indices `0..41`;
`gravity_m_s2` has three components in x/y/z order. The inverse arrays are the
actual runtime operands passed to `chkdt_tw` and are separately checked against
the spacing arrays and pinned candidate initialization. `time_start_s` is the
start time from the hashed case input and is zero for these no-restart fixtures.
The analyzer verifies these against the reviewed candidate/build and input
hashes; it must not infer them from a timestep CSV.

## Join, stop-prefix, and manifest rules

Phase and velocity rows carry `state_index` and `transport_interval_index`;
timestep rows carry only `state_index`. They are grouped many-to-one where a
timestep evaluation exists, never one-to-one between CSV tables; do not infer a
join from row order or assume every audit state has a timestep row. A timestep
row U_k is recorded before interval k is consumed. The initial velocity audit
`initial_u0=(0,-1)` normally shares U_0, but a controlled failure in
`initial_u0` occurs before timestep evaluation and therefore has no timestep
row. An endpoint audit failure in `projection_override` or
`corrected_endpoint` for interval K records velocity state K+1, while the last
timestep row is U_K; that audit state has no timestep row in this valid failure
prefix. These are the only permitted audit-state/timestep join exceptions.
In the phase table, `state_index` is the source schedule state k for the
interval, not the physical time of every property array. All stages for
interval k use `(state_index=k, transport_interval_index=k)`.
`pre_momentum` contains the post-advection endpoint `vof/rho/mu` arrays but
retains the interval-k schedule that applied throughout advection. Velocity
rows identify the actual velocity field: `pre_vof=(k,k)`, and both
projection/corrected endpoint groups for interval k use `(k+1,k)`.

The exact output order is:

1. Phase rows: ascending interval; within each interval
   `pre_vof_x`, `pre_vof_y`, `pre_vof_z`, `pre_momentum`; within each stage the
   face/class sequence in the phase table above; within a stage use applicable
   properties in `alpha`, `rho`, `mu` order.
2. Velocity rows: one `initial_u0` group first; then ascending interval, with
   `pre_vof`, `projection_override`, `corrected_endpoint`; within a stage use
   the velocity face/class sequence above and components `u`, `v`, `w`.
3. Timestep rows: ascending `state_index`.

For a normally completed 14-interval fixture, the phase table has
`14*(8+8+8+24)=672` data rows, the velocity table has
`12+14*(12+12+12)=516`, and the timestep table has 15. These totals are
independent of slot count because empty classes are still rows. For a controlled
stop, derive exact rows from the complete prefix rules below, never from a
producer-reported count.

Every stage group is atomic: scan and serialize the complete expected key set
for that stage, including empty classes, flush it, and only then stop if any
row fails. Never emit a partial stage group. The manifest has exactly these
top-level fields:

```text
manifest_schema,producer_schema,schema_sha256,candidate_sha256,image_digest,
case_id,input_sha256,analyzer_sha256,run_status,solver_exit_code,stop_reason,
state_count,interval_count,completed_interval_count,stop_state_index,
stop_interval_index,stop_stage_id,final_time_s,files_sha256,row_counts,
scan_order,reduction_order,timestep_inputs,resources,pressure_solver
```

The manifest is strict UTF-8 JSON without a BOM, has unique keys, sorted keys,
compact separators, no non-finite JSON numbers, LF endings, and one trailing
LF. Hashes are lowercase 64-character SHA-256 hex strings unless
`image_digest`, which is `sha256:<64 lowercase hex>`. `schema_sha256` hashes the
exact bytes of this schema file. `candidate_sha256` hashes the exact bytes of
the run's immutable `candidate-build.json` receipt; that receipt pins the
upstream commit/source hashes, patch and build-script hashes, image digest,
compiler/version/flags, build command, and executable SHA-256. `image_digest`
is the immutable OCI image digest used for this run, never a mutable tag.
`analyzer_sha256` hashes the exact reviewed analyzer source file bytes.
`input_sha256` is a JSON object whose sorted keys are every regular staged
solver-input path relative to the frozen case root, in canonical POSIX form,
and whose values hash exact file bytes. It includes the complete case input
set (including `dns.in`, `vof.in`, and `source-boundary.in`); symlinks,
duplicate paths, omitted files, or extra paths fail validation. `case_id` is the
exact case-directory identifier. `files_sha256` and `row_counts` are JSON
objects keyed by the exact three CSV basenames; hashes cover exact bytes and
counts are JSON integers excluding headers.

The version/case/hash/status fields and `image_digest` are JSON strings;
`solver_exit_code`, all planned/completed counts, and both controlled-stop
indices are JSON integers. `stop_stage_id` is always a JSON string. On normal completion, both stop-index fields and
`stop_stage_id` are the JSON string `not_applicable`. `final_time_s` and every physical value
are JSON decimal strings. `scan_order` is an object of ordered string arrays;
`reduction_order`, `timestep_inputs`, `resources`, `pressure_solver`,
`files_sha256`, `input_sha256`, and `row_counts` are JSON objects with the exact
keys and value types specified here. No numeric JSON values are accepted except
the declared integer fields.

`state_count` and `interval_count` are the planned counts N+1 and N.
`completed_interval_count` is the count of wholly completed intervals before
termination. `run_status` is `completed` only for normal completion, which
requires `solver_exit_code=0`. The declared controlled guard/audit stops use
`failed` and the actual nonzero `solver_exit_code`. `stop_reason` is exactly
`normal_completion`,
`timestep_guard`, `phase_audit`, or `velocity_audit`. On normal completion,
both stop-index fields and `stop_stage_id` are the literal string
`not_applicable` and
`completed_interval_count=N`. On a controlled stop, `stop_interval_index=K`
and `completed_interval_count=K`; `stop_state_index=K` for timestep/phase
failures and `initial_u0`/`pre_vof` velocity failures, and `K+1` for velocity
`projection_override`/`corrected_endpoint` failures. `stop_stage_id` is
`not_applicable` for a timestep guard, the exact phase/velocity stage for an
audit failure, and `not_applicable` for normal completion. A timestep guard
stop at K<N includes the false U_K row and no row or audit group for interval
K. A velocity audit failure in `initial_u0` has the exact manifest tuple
`completed_interval_count=0`, `stop_state_index=0`, `stop_interval_index=0`,
`stop_stage_id="initial_u0"`, `run_status="failed"`, and
`stop_reason="velocity_audit"`, with a nonzero `solver_exit_code`; the CSV
velocity key retains its distinct `transport_interval_index=-1` sentinel.
Every controlled stop except a failure in `initial_u0` preserves the
successful `initial_u0` group and all complete phase/velocity groups for
intervals `<K`.

For a phase failure at `(K,stage)`, preserve `initial_u0`, all interval groups
`<K`, all phase groups through and including the complete failing stage at K, and the K
`pre_vof` velocity group; omit all later phase stages and endpoint velocity
groups in K. For a velocity failure at `initial_u0`, preserve only its complete
failing group and no timestep rows. For velocity `pre_vof`, preserve
`initial_u0`, all intervals `<K`, the complete failing `pre_vof` group at K, and timestep rows
through U_K; omit phase and later velocity groups at K. For
`projection_override` or `corrected_endpoint` failure, preserve all phase
groups in K and velocity groups through the complete failing group, plus
timestep rows through U_K; omit later groups. Audit failures are structurally
preserved and returned as failures, not malformed/truncated evidence.

The timestep table has rows U_0..U_N with only U_N `not_applicable` on normal
completion. Under a guard stop at K it has rows U_0..U_K and `guard_pass=false`
at K. Under an audit stop in interval K it has rows only through U_K; its guard
row K is true because the outgoing bound was checked before the audit. A
`projection_override` or `corrected_endpoint` failure at velocity state K+1
does not add a timestep row at K+1. For an initial U0 audit failure, the
timestep file contains only its header. The analyzer accepts exactly these
declared non-joined audit prefixes and rejects any other audit state missing
its required timestep row. The manifest `final_time_s=t_0+completed_interval_count*dt`.
The analyzer verifies the exact phase/velocity/timestep prefix implied by the
manifest reason, stop indices, and stage order; a missing future prefix is valid
only for these controlled stops. Any other missing, duplicate, unexpected,
reordered, or orphan row is a structural failure.

`files_sha256` and `row_counts` contain exactly the three named CSV files;
row counts exclude headers. `scan_order` has exactly the keys
`phase_property`, `boundary_velocity`, and `timestep`. Their values are, in
that order:

```text
[transport_interval_index,state_index,stage_id,face,source_class,property]
[transport_interval_index,state_index,stage_id,face,source_class,component]
[state_index]
```

Use the stage, face/class, property, and component ranks defined above rather
than lexical string order. `reduction_order` has exactly the keys
`cell_scan_order`, `max_error_order`, and `floating_point`, respectively
`i,j,k ascending`, `first lexicographic location on a tie`, and
`candidate real(rp) binary64`. `resources` has exactly `ram_samples`,
`vram_samples`, and `step_timing_samples`; RAM samples have exactly
`elapsed_s` and `rss_bytes`, VRAM samples exactly `elapsed_s` and `used_bytes`,
and step samples exactly `step` and `elapsed_s`. RAM/VRAM elapsed times and
byte values are nonnegative decimal strings; step indices are nonnegative JSON
integers and elapsed times are nonnegative decimal strings. RAM and
VRAM arrays each contain at least one monotone-time sample. Step samples have
monotonically increasing step indices and elapsed times; the array may be empty
if `completed_interval_count=0`. `pressure_solver` has exactly
`kind`, `iterative_pressure_iterations`, `iterative_pressure_residual`, and
`reason`; for the frozen direct solver the first is
`direct_fft_xy_tridiagonal_z`, the two iterative fields are
`not_applicable`, and the reason names the direct FFT/tridiagonal path and
direct continuity/projection evidence. All continuous manifest numbers are
decimal strings; `real_kind`, `precision_digits`, row counts, state/interval
counts, stop indices on a controlled stop, solver exit code, and resource step
indices are JSON integers. On normal completion, both stop-index fields and
`stop_stage_id` are the string `not_applicable`. Hashes cover exact file bytes.
All three CSVs are created even for an early controlled stop; a file with no
rows contains exactly its required header and trailing LF.

## Failure summary and scalar syntax

For each location, compute the expected value from the boundary mapping and
compare finite values by exact equality in the candidate's source `real(rp)`
precision. This is a strict instrumentation predicate for fields that should
be prescribed/copied by the boundary operation; it is not a scientific error
tolerance. A row's `mismatch_count` counts locations where both values are
finite and `observed /= expected`; `nonfinite_count` counts a location once if
either value is non-finite. The categories are disjoint and
`mismatch_count+nonfinite_count <= scanned_cells`. `max_abs_error` is the
maximum absolute difference over **all** locations where both values are
finite, including exact matches; it is zero when there are no such locations.
Every conforming row therefore has a finite `max_abs_error`. If subtracting a
finite expected/observed pair overflows, preserve the raw overflow and mark the
bundle failed/nonconforming; the analyzer rejects it and the producer must not
clamp it to a fabricated finite value.
Visit cells in ascending lexicographic `(i,j,k)` order (nested i, then j, then
k). Preserve the first offending cell of either category and never overwrite
it with a later mismatch. In a non-finite pair, encode `expected` and `observed`
independently: each non-finite member is exactly `NaN`, `+Inf`, or `-Inf`, and
each finite member uses the finite-number grammar below. This applies when both
members are non-finite; the location still contributes exactly one to
`nonfinite_count`. Every summary field other than the two value fields remains
finite. A zero-
failure row has zero counts/error and `not_applicable` for all failure indices
and both values. Zero scanned cells is legal only for a declared empty class;
its counts/error are still zero and failure fields are `not_applicable`.

Counts are nonnegative base-10 integers without whitespace, plus signs, or
leading zeroes (except `0`); indices are canonical integers, with `-1` only
for the initial velocity interval. Boolean CSV values are exactly `true` or
`false`. Finite CSV numbers match
`-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?`: no leading/trailing
whitespace, no leading plus, no leading zeroes, and uppercase or lowercase E
with an optional signed exponent. The Fortran writer left-trims descriptor
padding, writes enough digits to round-trip its `real(rp)` value, and emits
negative zero as `0`. First-failure values are the only permitted non-finite
tokens.

Candidate5 CPU helper tests inject a non-finite value and one mismatch in every
nonempty source class and component, verify first-failure retention (including
a finite mismatch preceding a later non-finite cell), test every declared
empty class, and test the complete timestep formula, zero-advection fallback,
capillary branch, guard pass/fail, controlled-prefix serialization, and input
rejection. These tests and the host build validate instrumentation behavior
only. A passing candidate5 source-disabled GPU regression is a separate
software regression, not B1-runtime evidence.

## Open review decisions

Before any source case, an independent reviewer must assess whether full-scan
mismatch summaries suffice without raw successful arrays; whether exact
comparison is appropriate for each producer-assigned field; the fixed-step
factor and any prospective dt/schedule amendment; maximum and L1 divergence
limits; the direct FFT/tridiagonal pressure-solver `not_applicable` treatment;
the strict analyzer and stage-count rules; and resource ceilings. Source CFD
remains closed until exact candidate/input/schema/limits/analyzer/launcher
review clears B1-pre and B2. Staged source cases remain serial and stop on the
first failure.
