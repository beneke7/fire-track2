# E2 Figure 4 source-uncertainty method — research draft

**Status: unapproved proposal.** This note selects no scientific tolerance and
does not approve an E2 source, geometry, solver, or run. E0 has passed; accepted
E1 remains a prerequisite before E2 comparison execution. The existing E2/E3
replay draft and the gate decisions remain authoritative until the primary
integrates a reviewed method into the case packet.

This file does not amend the [shared replay draft](E2_E3_PROVISIONAL_REPLAY_DRAFT.md)
or the [validation protocol](../docs/VALIDATION.md).

## Scope and source evidence

This proposal covers the scalar Dash-8 outlet-velocity trace for the
finite-window E2-DIG-0.5 comparison. It handles only uncertainty in reading
Figure 4. It does not recover the unpublished `Q_L(t)`, exit area, spatial inlet
profile, or resolve the paper's use of `U_L` as both mean and maximum velocity.
It does not resolve the prose value “approximately 4.8 m/s at 0.5 s” against the
figure reads. Keep that discrepancy visible and retain E2-PK as a separate
peak-characterization case.

The source is Calbrix et al. (2023), Fig. 4, PDF p. 5 / journal p. 1519. The
[E2 source record](E2_CALBRIX_SOURCE.md) documents 0.1 s Figure 4 samples, a
horizontal read allowance of `±0.03 s`, and ordinate allowances usually
`±0.10 m/s`, widened to `±0.15 m/s` on the initial rise and `±0.20 m/s` on the
sharp 3.8–4.2 s decline. These are conservative figure-read bounds, not
source-provided errors or statistical intervals. A time displacement changes
the ordinate through the local curve slope, so the coordinates must not be
perturbed as independent per-sample random errors.

The [primary CSV](../data/derived/calbrix_dash8_fig4_velocity.csv) and
[second-read CSV](../data/derived/calbrix_dash8_fig4_velocity_independent.csv)
each have 51 samples from 0 to 5 s. Both contain `time_s`, `u_l_m_s`,
`figure_read_bound_time_s`, and `figure_read_bound_u_l_m_s`. The second-read
file additionally records `source_pdf_sha256`, `pdf_page`, `journal_page`,
`figure`, `series_id`, `source_pixel_x`, `source_pixel_y`, `sample_kind`, and
`read_method`; its metadata identifies PDF p. 5, journal p. 1519, Fig. 4,
`dash8_blue`, and `blue_rgb_mask_column_median`.

These are **two trace extractions from the same plotted raster with the same
stated axis calibration**, not two independent calibrations. The second
extraction uses a separate raster trace-read procedure but reuses the source
record's axis calibration (`x≈9..1459 px`, `y≈1148..7 px`). Their agreement
checks trace-read repeatability only; it does not bound shared axis
calibration error, inlet accuracy, or physical source uncertainty. The shared
local source PDF SHA-256 is
`128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4`.

At this review snapshot, the primary and second-read velocity CSV hashes are
`b43f2ee1220182cca532c290a0d265a5d6f382eb6025b9b7689216fea8f6c332` and
`fd4791bf79e39e2dbd3261af59c96b13d731b2a0a6ce4fe5450092aa2c1d7f0b`.
The primary and second-read Fig. 6(b) target CSV hashes are
`308c23d755828027acb54e9e9181f74142f831ad6649a1fc91f0a482023a5969` and
`2634389063a3d75a2e1e2c8523b3d27ae204ae31557d9e354de7fe4c2aceab4b`.
These are input snapshots for a future manifest, not approved case hashes.

A direct same-time comparison gives mean absolute ordinate difference
`0.0036667 m/s` and maximum `0.032 m/s` at `0.1 s`. The first piecewise-linear
segment slopes are `22.90 m/s²` for the primary read and `23.22 m/s²` for the
second read. Multiplying by `0.03 s` gives `0.687` and `0.6966 m/s`, respectively.
This arithmetic shows why the timing allowance must act on the history itself;
it is not a new uncertainty bound or a tolerance.

## Proposed continuous scenario evaluator

For each read `r`, let `u_r(x)` be the piecewise-linear function through the
CSV's `u_l_m_s` values at `time_s=x`, over the supported source domain
`0 ≤ x ≤ 5 s`. Let `b_r(x)` be the corresponding piecewise-linear function
through `figure_read_bound_u_l_m_s`. Do not smooth or average the two reads.
Preserve the visible short spike near `2.3 s` and the low-velocity tail; neither
is a basis for an artificial terminal cutoff.

Use the following candidate scenario parameters:

- `δ ∈ {−0.03, 0, +0.03} s` is one shared displacement of the complete history.
  The simulation-time input is evaluated at source time `x=t+δ`. Thus positive
  `δ` advances the source: at simulation time `t`, the evaluator reads a later
  point on the plotted history. Negative `δ` delays it.
- `a ∈ {−1, 0, +1}` is one common-sign ordinate residual coefficient across the
  trace, not one sign per sample. The residual is a proposed bounded sensitivity
  mode, not a probability model or a source-derived correlation law.

To keep the residual from creating a nonzero value at the constructed axes
origin, define `b̃_r(x)` by piecewise-linear interpolation through
`(0 s, 0 m/s)` and the CSV bound values at every positive source knot
`0.1, …, 5.0 s`. The CSV's `t=0` ordinate bound is therefore not applied by this
anchored residual mode. This taper is an additional reconstruction assumption
requiring reviewer approval; the source record identifies the origin as the
axes intersection, not as a measured flow value.

The candidate boundary history at actual simulation time `t` is

```text
x = t + δ
U_(r,δ,a)(t) = 0                                  if x < 0
U_(r,δ,a)(t) = max(0, u_r(x) + a b̃_r(x))          if 0 ≤ x ≤ 5 s
U_(r,δ,a)(t) = undefined / reject the case         if x > 5 s
```

For method revision `M03`, use the **fixed absolute Figure 4 / Figure 6(b)
clock** and compare every scenario at absolute simulation time `t=0.5 s`. This
is a prospective timing convention, not a time interpretation recovered from
the paper. Since `x=t+δ`, source origin is `source_origin_time=−δ`, and source
age at the fixed diagnostic is `0.5+δ`: `0.47`, `0.50`, or `0.53 s` for
`δ=−0.03`, `0`, or `+0.03 s`. The required source support is contained in both
full CSVs.

Start **every run at the common absolute time `t=−0.03 s`**. Every scenario
uses the same provisional gas-only initial field and the same non-source
boundary conditions and initialization settings; there is no liquid in that
initial field. The exact gas-only state and boundary values are not published
by Calbrix and must be frozen and hashed in the later approved case packet;
this draft does not invent them. Apply the shifted liquid source as zero
whenever `x=t+δ<0`; when `x≥0`, apply the evaluator above. Because
`b̃(0)=u_r(0)=0`, all three sources are zero at their own onset. The
`δ=+0.03` case therefore includes supported source history from
`t=−0.03 s` before absolute `t=0`; the `δ=0` case starts liquid input at
`t=0`; and the `δ=−0.03` case remains gas-only until `t=+0.03 s`. All cases
end at absolute `t=0.5 s` after exactly `0.53 s` elapsed solver time. The
declared liquid history is the only intended per-case boundary variation.

This is a **combined source-timing/startup assumption**, not a source-only
uncertainty claim and not a recovered Calbrix initialization. The paper does
not publish the gas-only initial field, startup state, or time-origin
relationship for the target snapshots. The shared gas-only state, non-source
boundary conditions and initialization settings must be identical across all
cases. If they cannot be made identical, the matrix does not isolate source
history. The relationship between the paper's snapshot time and this fixed
absolute clock remains a provisional assumption; do not change to elapsed time
since release or to per-case starts without a separately reviewed method
revision.

This defines the value at `t=0` without moving samples to unshifted replay
knots:

| `δ` | Candidate `U(0)` | Interpretation |
| --- | --- | --- |
| `−0.03 s` | `0` | At absolute `t=0`, `t+δ<0`; common solver start is `−0.03 s`, and source onset is delayed to `+0.03 s`. |
| `0` | `0` | The anchored source origin. |
| `+0.03 s` | `u_r(0.03)+a b̃_r(0.03)` | The source is advanced; common solver start is its source origin `t=−0.03 s`, where `U=0`. |

At `δ=+0.03 s`, `b̃(0.03)=0.045 m/s`; the primary read gives
`U(0)=0.687 + 0.045a m/s`, and the second read gives
`U(0)=0.6966 + 0.045a m/s`. Thus the advanced case has already received
supported liquid input by absolute `t=0`; every run starts at `−0.03 s` with
the same gas-only state and zero source velocity. Neither the nonzero `U(0)` nor
the common gas-only startup is a measured paper initial condition.

The `max(0,·)` operation applies at every actual time, not only at CSV knots.
Because both terms are piecewise linear, the generator must find and insert
every zero crossing of `u_r+a b̃_r`; this preserves positivity without
reinterpolation artifacts. A zero segment created by this floor is a feature
of this bounded sensitivity history, not evidence of physical tank shutoff.
Do not use this method to infer the censored E2-HIST tail or terminal condition.

This evaluator is a candidate **finite sensitivity family**, not a justified
continuous uncertainty envelope. The CSV bounds do not establish that one
whole-history shift and one common-sign residual span all shared calibration,
trace-width, stretch, or sign-changing errors. They also do not establish that
all Cartesian combinations are jointly admissible or that the three selected
parameter values cover a nonlinear solver response. No probability, confidence
level, or conservativeness claim is assigned.

## Candidate finite matrix and target comparison

The proposed matrix crosses read ID, timing setting, and residual setting:

| Factor | Candidate values | Status |
| --- | --- | --- |
| Source read `r` | `primary`, `second_read` | Preserve separately; same raster and stated axis calibration. |
| Shift `δ` | `−0.03`, `0`, `+0.03 s` | Bounded settings from `figure_read_bound_time_s`. |
| Residual `a` | `−1`, `0`, `+1` | Bounded common-sign sensitivity mode from `figure_read_bound_u_l_m_s`, with the proposed origin taper. |

Enumerate deterministically in the order `primary`, then `second_read`; within
each read enumerate `δ` as `−0.03, 0, +0.03 s`, then `a` as `−1, 0, +1`. This
defines 18 proposed input cases, including the two nominal cases
`(δ=0,a=0)`. The fixed absolute observation clock and common gas-only startup
make this a combined source-timing/startup sensitivity design. The count 18
does not establish joint admissibility or uncertainty coverage. An independent
reviewer must approve this convention and case list or derive a different
paired set from raster/tick/trace evidence before it can serve as a gate input.
Never weight scenarios or choose them based on CFD fit.

Keep the [primary Fig. 6(b) target CSV](../data/derived/calbrix_dash8_cloud_curves.csv)
and [second-read target CSV](../data/derived/calbrix_dash8_cloud_curves_independent.csv)
separate. The primary target CSV
contains `independent_variable`, `dependent_value`, `read_bound_independent`,
and `read_bound_dependent`; its second data row has bounds about `(0.004711,
0.031111) m` for `(y,Z)`. The second target CSV contains `x_value`, `y_value`,
`read_bound_x`, and `read_bound_y`; its second data row has `(0.020,0.030) m`
bounds. Retain each target's own segment/branch metadata and all rows.

These target columns give coordinate-wise read allowances, not a joint
calibration covariance or an approved correlated target-curve family. Target
`y` uncertainty affects common support, interpolation and landmark locations;
target `Z` uncertainty affects profile values. The method for pairing these
coordinates, handling segment endpoints/gaps and propagating their bounds is
**open**. Until an independent reviewer freezes a target-coordinate model, the
two target centerlines may be shown as descriptive overlays, but scores against
their centers are not a complete uncertainty-aware E2 gate.

The shared replay draft's candidate Fig. 6(b) metric is normalized profile
RMSE with a prescribed `y=0` anchor, 0.02 m sampling, no extrapolation, and a
candidate 90% target-span coverage requirement; it also lists first crossings
at `Z=0.5, 1.0, 2.0 m` and a candidate 15% landmark-location tolerance. These
are **unapproved candidates**, as is the validation document's draft 10% curve
RMSE value. This note selects none of the formula details, support/weighting
rules, coordinate-bound treatment, landmark rules, or numerical tolerances.
The reviewer must freeze them, including source-space discrepancy scoring,
target-coordinate uncertainty, comparison normalization and required
conservation/refinement/resource limits, before any benchmark run.

The 18 proposed inputs crossed with the two target centerlines would produce 36
centerline comparisons, but that count does not propagate target-coordinate
uncertainty and is not sufficient by itself for pass/fail. If target scenarios
are later approved, the required analysis set must include the approved
source/target pairings without averaging the read identities. Any numerical
refinement comparisons required by the approved protocol remain additional
checks, not substitutes for source or target uncertainty.

## Decision and failure classification — proposed logic, limits open

The decision logic below is a proposal only. No score or tolerance has been
accepted. Before use, the scientific reviewer must freeze the score,
target-coordinate treatment, source-space allowance, output limits, gas-only
startup inputs and required scenario set.

Assign exactly one primary status using this precedence, with first applicable
condition winning; preserve any lower-priority observed defects as reason
codes:

1. `NOT_READY`: accepted E1, the source/method review, frozen scores/limits or
   another required preregistration is absent. No scientific pass/fail status
   is allowed.
2. `PROVENANCE_INVALID`: any required source, target, generator, method or
   contract hash does not match the frozen manifest.
3. `INCOMPLETE`: any required source/target scenario, run, observable,
   diagnostic or refinement is missing, stopped or unfinished. Keep reason
   codes for other observed defects, but do not treat available partial results
   as the complete set.
4. `SOURCE_BOUNDARY_INVALID`: the prescribed history is not the input actually
   applied, the gas-only/non-source startup does not match the frozen common
   state, or source boundary flux/provenance cannot be reconciled. This is an
   implementation failure, not source-read sensitivity.
5. `NUMERICAL_INVALID`: every required artifact exists, but a completed run
   fails a frozen numerical validity, conservation or refinement criterion.
   Attach a reason such as `NUMERICAL_SENSITIVITY`, `MASS_LEDGER` or
   `MOMENTUM_LEDGER`. Thus a completed run that fails a refinement gate is
   `NUMERICAL_INVALID` with reason `NUMERICAL_SENSITIVITY`; a missing required
   refinement is `INCOMPLETE`.
6. Only a complete source/target matrix with valid source-boundary and
   numerical checks may receive a scientific status. Never drop a failed,
   stopped or numerically invalid case and count it as scientific
   agreement/disagreement.

Within that final level, classify a decision change across approved `(r,δ,a)`
inputs with target treatment and numerical resolution fixed as
`INCONCLUSIVE_SOURCE_SENSITIVITY`. A change across approved target coordinate
scenarios with source and resolution fixed is
`INCONCLUSIVE_TARGET_SENSITIVITY`. If both contribute or interact, report
`INCONCLUSIVE_COMBINED_SENSITIVITY`. A figure uncertainty set wider than its
separately accepted budget is `INCONCLUSIVE_FIGURE_UNCERTAINTY`; report
`INCONCLUSIVE_NUMERICAL_SENSITIVITY` only as a reason code under
`NUMERICAL_INVALID`, never as a competing primary status.

A scientific **PASS** requires advance approval of this method and the finite
scenario family, accepted E1 and all other prerequisites, valid complete runs,
source and target uncertainty within their separately accepted budgets, and
every required score/landmark comparison passing frozen limits. A scientific
**FAIL** requires the complete valid set to fail those limits while source and
target uncertainty remain within their accepted budgets. If figure uncertainty
exceeds an accepted budget, use `INCONCLUSIVE_FIGURE_UNCERTAINTY`. Otherwise,
if valid figure scenarios straddle pass/fail, use the applicable source,
target, or combined sensitivity status and report its full deterministic score
range. The reason `NUMERICAL_SENSITIVITY` never competes with the primary
`NUMERICAL_INVALID` status for a completed failed-refinement set.

Source-input uncertainty (m/s), target-coordinate uncertainty (m), and
numerical discretization error are separate quantities. Do not compare their
raw magnitudes directly or combine them into a probability interval. If the
accepted source-space and output-score definitions are missing, if target
coordinate uncertainty is unpropagated, or if figure uncertainty spans the
acceptance boundary, report ranges and a descriptive result without a pass/fail
label. Never widen an accepted limit or prune a scenario after seeing outputs.

## Reproducible generator and canonical provenance — specification only

No generator or run manifest is created by this research draft. If the method
is accepted, implement a CPU-only pure evaluator and save a fresh immutable
source table for every approved case. Parse each source CSV as UTF-8 with a
strict decoder. Parse every numeric token as base-10 `Decimal`, then convert it
to an exact rational `Fraction(Decimal(token))`; do not first parse the CSV
through binary floating point. Parse scenario settings from the exact strings
`"-0.03"`, `"0"`, `"0.03"` and `"-1"`, `"0"`, `"1"`. Perform source
interpolation, origin-taper interpolation, addition, zero-root calculation,
and time shifting using exact rationals.

For each piecewise-linear source segment, form the exact rational residual
`q(x)=u_r(x)+a b̃_r(x)`. Evaluate `q` at both segment endpoints. If endpoint
values have strictly opposite signs, insert the unique strict-interior root
`x_root=x_i−q_i (x_{i+1}−x_i)/(q_{i+1}−q_i)`. An endpoint with exact value zero
is already represented by that source knot and must not be inserted twice. A
segment whose two endpoint values are zero is identically zero; keep its
endpoints and add no interior roots. On intervals split by these roots,
`max(0,q)` is linear or identically zero. Transform each source knot or root
to actual solver time by `t=x−δ`; this is the same actual-time evaluator
`x=t+δ`, not resampling shifted values onto original knots.

The exact run window for every case is `[-0.03,0.5] s`. Form one sorted exact
rational union of the two run endpoints, `t=0`, every shifted source knot in
the window, each shifted source origin `−δ` in the window, and every shifted
strict-interior positivity root in the window. The exact-rational set union
merges coincident knots and roots before float conversion. Convert each unique
time and value exactly once to IEEE-754 binary64 using round-to-nearest,
ties-to-even. If two distinct exact times convert to the same binary64 value,
reject generation with `FLOAT_KNOT_COLLISION`; never silently deduplicate
them. Reject non-finite conversions and any requested source evaluation
outside `0≤x≤5 s`; the zero extension applies only to `x<0`, not beyond the
measured CSV domain. Do not enable fused multiply-add or fast-math. Record the
Python implementation and exact version used by the later generator.

The runtime table evaluator linearly interpolates the converted binary64
knots. Round-trip each exact knot coordinate and ordinate separately: compare
the binary64 time to its exact-rational time and the binary64 speed to its
exact-rational speed. For each, require absolute error no greater than
`16*ulp(S)`, where `S=max(1, |exact|, |converted|)` in that quantity's SI
units. For every rational test position (the midpoint and 1/3 and 2/3
positions in each interval), first convert the requested time to binary64 by
round-to-nearest, ties-to-even, and call that value `t_query`. Evaluate the
direct exact-rational reference at `Fraction.from_float(t_query)`, using the
exact rational representation of that binary64 query time. Compare it with the
runtime table speed at the same `t_query`; require absolute difference no
greater than `16*ulp(S)` in m/s, where
`S=max(1, |reference|, |candidate|, |segment endpoint 0|,
|segment endpoint 1|)`. Compute each bound with binary64 `math.ulp(S)`. If a
check also evaluates the original unprojected rational position, report the
resulting value difference as query-projection error separately; do not count
it as table/evaluator mismatch. These are roundoff-equivalence checks, not
physical tolerances. A violation is a generator defect; it cannot be absorbed
into a fitted or scientific tolerance.

Proposed canonical history-table bytes: UTF-8, no BOM, LF line endings, exact
header `time_s,u_l_m_s`, increasing unique binary64 times with no collisions.
Serialize finite values using Python's binary64 round-trip format `.17g`,
normalize signed zero to `0`, and end the file with exactly one LF. The knot
construction above must make the table piecewise-linear representation exact
up to the explicitly checked binary64 conversion and interpolation roundoff.
Keep complete original CSV hashes even though this run uses only source times
`0–0.53 s`.

Freeze the following noncircular identifiers and dependency order before
implementation. The method revision in this document is `M03`.

Separate history content identity from case identity:

- A history-content ID is `E2-HIST-H{sha256hex}`, where the suffix is the
  complete lowercase SHA-256 of canonical history-table bytes. This ID names
  immutable bytes only; identical table bytes may retain the same history ID
  across source/target dependency revisions.
- Before generating tables, form a canonical upstream-dependency descriptor
  for the complete proposed matrix. It contains the method revision and method
  document hash; source PDF and both source CSV hashes; both target CSV hashes;
  source-record, replay, validation and plan hashes; the score/target-treatment
  contract hash (null until frozen); generator source hash and Python
  implementation/version;
  the exact conventions and complete `(read, delta, a)` scenario list; hashes
  for the common gas-only initial state and non-source boundary inputs; and
  repository revision/dirty-state evidence. Encode it as canonical JSON using
  the manifest byte rules below. Exclude generated history hashes/paths, case
  IDs, the source-matrix manifest hash, approval/execution hashes, and run
  outputs. Its full lowercase SHA-256 is the upstream dependency digest `U`.
  Because `U` covers both source reads, both target reads and every other
  required input, changing a source or target dependency changes `U` even if
  it happens to produce identical history bytes.
- A case ID is
  `E2-DIG-0.5-M03-{P|R2}-D{M030|Z000|P030}-A{M1|Z0|P1}-U{sha256hex}-H{sha256hex}`.
  `P` and `R2` identify primary and second-read traces; `D` is `M030` for
  `−0.03 s`, `Z000` for `0`, and `P030` for `+0.03 s`; `A` is `M1` for `−1`,
  `Z0` for `0`, and `P1` for `+1`; `U` is the upstream dependency digest; and
  `H` is the history-content ID digest. Thus identical table bytes may share
  `H`, while changed source/target dependencies produce different case IDs.
  Approval and execution are downstream and do not alter the already frozen
  source-case ID.

Any change to method behavior, algorithm, clock, scenario definition or
assumption increments the method revision; do not reuse M03 case IDs after
such a change. A changed source, target, generator, startup input or contract
hash changes `U` and therefore the case IDs even if the method revision and
history bytes stay the same. A changed table changes `H` and the case ID.

The later source-matrix manifest is canonical JSON: UTF-8 without BOM, sorted
object keys, compact separators, no timestamp, and exactly one final LF.
Represent decimal parameters as strings and file paths as repository-relative
paths. Include schema and method revision/status; repository revision and
dirty state; source PDF and both source CSV hashes; both target CSV hashes;
source-record, replay, validation, plan and accepted method-document hashes;
generator source hash and Python implementation/version; exact scenario
strings and conventions above; gas-only startup and non-source boundary input
hashes; history paths and hashes; and accepted score/target-treatment
contract hash. Until accepted, encode `approved_contract_sha256` as JSON
`null`. Hash raw input files before generation. Do not put the manifest's own
hash, an approval hash, or an execution hash inside this source-matrix
manifest.

Compute the source-matrix manifest SHA-256 over its canonical bytes and use
that digest outside its contents, for example in immutable manifest filename
`E2-SU-M03-sha256-{64 lowercase hex}.json`. The matrix manifest records `U`,
all case IDs, history-content IDs and table hashes. These relationships are
acyclic: frozen method/source/target/input hashes and generator produce `U`;
`U` plus exact case parameters and generated history-content hashes produce
case IDs; those inputs and outputs produce the source-matrix manifest; a
separate approval record references the source-matrix manifest's full hash
and reviewer decision.

An execution request is frozen only after that approval record exists. Define
its canonical descriptor from the source-matrix manifest hash, approval-record
hash, a unique immutable attempt token, solver/build/dependency versions,
solver settings, seeds and preregistered resource/run settings. Serialize it
with the same canonical JSON byte rules as the source-matrix manifest. Exclude
the execution ID, run outputs and execution-manifest hash from this descriptor.
Its ID is
`E2-EXEC-M03-S{source-matrix-sha256}-A{approval-record-sha256}-C{execution-descriptor-sha256}`;
all three suffixes are complete lowercase SHA-256 values. This ensures any
source/target dependency change changes the source-matrix hash and execution
ID, while a new approval or execution configuration also gets a new execution
ID. The execution manifest records this ID and references the source-matrix
and approval hashes; its own content hash is computed after completion and
remains external. Result artifacts reference that final execution-manifest
hash. Never backfill downstream approval or execution hashes into upstream
documents or manifests. A rerun with changed hashes under an existing case or
execution ID is rejected; a retry gets a new attempt token and execution ID.
Generated hashes do not replace source hashes or records of actual
solver-boundary phase mass and vector-momentum flux.

## Required independent CPU checks before accepting an implementation

An independent implementation/reviewer should check the generator against
analytical expectations, not only against itself:

- `δ=0,a=0` exactly reproduces each input CSV's piecewise-linear function at
  every source knot and arbitrary interior points before binary64 conversion.
- For every `δ`, source knot `t_i` appears at actual solver time `t_i−δ`;
  evaluate at actual times, verify the common run start `−0.03 s`, source
  origins and `U(0)` values, and reject lookup beyond source support. For
  `δ=−0.03`, verify zero extension through delayed onset `t=+0.03 s`; for
  `δ=+0.03`, verify the supported advanced source from `t=−0.03 s`.
- Verify all scenario outputs are finite and nonnegative, the floor's exact
  zero crossings appear in the exported knot set, and evaluator/table values
  agree at points strictly between all knots under the roundoff-only bound.
  Convert each rational query time by ties-to-even and evaluate the exact
  oracle at `Fraction.from_float(t_query)`; if also checking the original
  rational point, report its query-projection error separately.
- Integrate each linear segment independently: for duration `h` and endpoint
  speeds `v0,v1`, check `∫U dt = h(v0+v1)/2` and
  `∫U² dt = h(v0²+v0v1+v1²)/3`. Compare with a separate quadrature or
  independently coded oracle. These are velocity-history diagnostics, not
  payload or solver phase flux.
- Check the identity layers independently: identical canonical table bytes
  retain one history-content ID; changing table bytes changes that ID; and
  changing any required source, target, generator, method, startup or contract
  dependency changes `U` and the case ID even when history bytes stay the same.
  Verify approval-only changes do not rewrite source case IDs, while source
  matrix, approval, execution configuration or attempt-token changes produce
  a new execution ID. Mutate each dependency separately and assert the expected
  digest/ID changes; check canonical serialization and SHA-256 values.
- Check deterministic byte-for-byte history regeneration, expected case
  count, and separate approval/execution records with correct upstream hashes
  and no cyclic dependencies.
- Preserve actual solver-boundary phase mass and vector-momentum flux checks
  separately from source-table integrals.

**Author-reported, unarchived inline arithmetic checks:** an earlier
standard-library CPU reference check reconstructed nominal CSV samples,
exercised the 18 proposed cases with distinct in-memory history hashes,
checked shifted breakpoints and zero support, compared evaluator and table
interpolation at interior points, found a full-history lower-mode positivity
root, and compared linear/quadratic segment integrals with two-node Gauss
quadrature. Its reported maximum residuals were `1.11e-16 m` and
`8.88e-16 m²/s`. The reported primary `δ=+0.03 s, a=0` integral
`1.87096 m` applies to `[0,0.5] s` only. The
[independent second review](../docs/reviews/E2_SOURCE_UNCERTAINTY_REVIEW_2_20260925T084013Z.md)
also reports the full common-run-window integral from `−0.03` to `0.5 s` as
`1.881265 m` for that same primary advanced nominal history; the pre-`t=0`
part is `0.010305 m`. These are velocity-history integrals, not payload or
solver phase flux. The inline script/output was not archived, so these checks
are author-reported and have not been independently reproduced here. They do
not establish the M03 generator's Decimal/binary64, collision,
canonical-manifest, or approval-DAG behavior, nor scenario admissibility,
target uncertainty coverage, solver flux, or an E2 gate. There is no committed
generator, exported matrix, reproducible check script, full manifest-hash test,
or accepted test suite. The formula has not been tested in a solver.

**Author-reported, unarchived specification checks for this revision:** a
standard-library synthetic check changed a target dependency while holding
history bytes fixed and observed a new `U`/case ID with the same history ID;
changing matrix, approval or execution settings changed the execution ID. A
binary64 query-time example compared the table and exact evaluator at
`Fraction.from_float(t_query)` and reported the original-rational projection
delta separately. These checks used synthetic descriptors, created no case
matrix, and were not archived or independently reviewed; they do not verify a
production manifest or history generator.

## Remaining reviewer decisions and execution gate

An independent scientific reviewer must decide whether:

- the fixed absolute `t=0.5 s` comparison, common `t=−0.03 s` start, identical
  provisional gas-only initialization/non-source boundary conditions, and
  resulting source ages `0.47/0.50/0.53 s` are a coherent combined
  timing/startup convention; these are not recovered paper facts;
- the whole-history shift, shared-sign residual and origin taper are supported
  by the shared raster/axis calibration evidence, and whether the 18
  combinations are jointly admissible and adequate for the sensitivity claim;
- the zero pre-start extension, advanced source input before absolute `t=0`,
  and rejection beyond source-domain support are appropriate;
- a joint target-coordinate uncertainty model can be justified from the two
  Fig. 6(b) target extractions and their bound fields;
- target-coordinate pairing/interpolation, accepted profile and landmark
  score definitions, source/target uncertainty budgets, pass/fail/inconclusive
  limits, conservation checks, mesh/time/refinement requirements, resource
  budget and stop conditions are justified and frozen.

The shared source and validation records also need their provenance wording
synchronized by the primary; this draft alone does not edit those shared files.
Until these decisions, accepted E1, and every other E2 prerequisite are
recorded, this remains a research proposal only. It selects no fitting
tolerance and authorizes no solver, E2, or E3 execution.
