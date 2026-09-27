# FluTAS finite-slot source boundary gate

**Status: candidate2 remains historically blocked; candidate3's exact patch
review and source-disabled GPU regression passed; candidate4 is frozen, built,
exact-reviewed and passed one bounded source-disabled GPU regression with the
reviewed wrapper; no source CFD has run.**
Candidate3 repairs the dry-validator, periodic return-halo and source-shutoff
state defects and retains the frozen short-x/long-y geometry. The independent
review and its GPU smoke disposition are recorded in
[`candidate3/INDEPENDENT_REVIEW.md`](../containers/flutas/candidate3/INDEPENDENT_REVIEW.md)
and the source-disabled run bundle in `results/runs/`. Candidate4 adds measured
telemetry and remaining host behavior checks; its exact review permits only a
source-disabled smoke. The reviewed wrapper passed the bounded GPU regression
at `3.001520526915884 s`; immutable run evidence is in
[`candidate4 regression bundle`](../results/runs/flutas-candidate-gpu-regression-20260925T095317Z-2015705/).
The exact disposition is archived in
[`candidate4/INDEPENDENT_REVIEW.md`](../containers/flutas/candidate4/INDEPENDENT_REVIEW.md).
The runner verifies candidate patch provenance, solver completion and fatal
markers, final time, expected data rows and parseable runtime resource samples.
Source execution remains gated on an accepted analyzer, limits and protocol.
The draft below is an acceptance contract, not an authorization to run. The pinned
upstream bubble test is not evidence for this gate.

**Evidence class:** implementation verification for a synthetic, grid-aligned
water source. Passing this gate does not validate a built Restás outlet,
aircraft flow, plume breakup, deposition, or design performance.

## Pre-run eligibility versus runtime qualification

Keep source-run eligibility separate from results. **B1-pre** means the exact
candidate, supported input restrictions, call order and transition behavior,
producer observables, analyzer, numerical/resource limits and execution
contract are reviewed well enough to authorize an attempt. **B1-runtime** is
the projection/source/flux evidence measured in the ordered dry and source
trials below. Do not require B1-runtime measurements before making those same
trials eligible; that would make the gate circular. A B1-pre acceptance is not
a B1-runtime pass.

Before protocol freeze, map every gate-required quantity to a serialized
runtime artifact or an independently accepted executable assertion. This
includes the requested/applied boundary-velocity audit and the alpha/rho/mu
states at relevant solver stages. Helper-level tests alone do not show that a
run produced those runtime histories. If the exact candidate cannot provide
required evidence, preserve it and review a narrowly scoped candidate revision
before scheduling any source run.

## Question and scope

Can the pinned FluTAS solver apply finite-duration liquid velocity and VOF
fraction on a rectangular mask of one physical domain face, at every solver
stage that can overwrite or consume those boundary values, while retaining
per-slot geometric phase-flux and momentum attribution?

Use the declared provisional layout: four 1.0 m × 0.15 m slots in a symmetric
2 × 2 array with 0.05 m edge gaps. These dimensions are a synthetic test
geometry borrowed from the CPU characterization case, not measurements of the
built apparatus. Construct the source face so every mask edge lies on a grid
face. Use water density 1,000 kg/m³ and a constant 4.8 m/s normal source speed
only where a nonzero liquid pulse is required. No ramp is used in this
implementation test; pulse transitions occur exactly on time-step boundaries.

The schedule is a unit-test fixture with integer time levels. Let `t_k` be the
time of the last completed velocity projection/correction. VOF transport
during interval `k` covers `[t_k, t_(k+1))` and uses the corrected velocity
state `U_k`; its source schedule is active when `n_on <= k < n_off`. This
defines exactly `N_active = n_off - n_on` source intervals. FluTAS may advance
its reported clock to `t_(k+1)` before calling `advvof`; the implementation
must therefore carry the explicit interval index `k` into alpha-boundary
refreshes rather than infer it from the current clock. Initialize velocity
with schedule state 0. The velocity boundary setters used for the next
projection and after that correction apply endpoint state `k+1`, establishing
the velocity for the next interval. Before each normal-direction geometric
VOF flux, refresh alpha and material-property ghosts with interval state `k`.
The run bundle must include a call-order table tied to pinned driver source
lines and unit cases proving pulse start and stop are not shifted by one step.
Reapply source-aware alpha/rho/mu halos after every generic `boundp` or
`update_property` call that can feed VOF flux or momentum, including the
post-advection property-fill path before the Runge–Kutta momentum update.
Record actual geometric phase flux at flux calculation time, not a value
inferred from requested velocity.

Apply liquid fraction only where the face is actually inflowing. On outward
flow, extrapolate interior liquid fraction, including on a nominal source face
and over inactive parts of that face; forcing alpha to zero on outflow would
delete water. Off-mask inflow must have alpha zero and no source attribution.
Report active-slot inward liquid flux separately from all outward liquid flux
and reverse flow.

## Boundary and numerical preflight

Before running FluTAS, the patch author must provide a six-face table naming
the exact pressure and normal-velocity boundary-condition pair, `is_outflow`
setting, imposed/background condition, source override, alpha inflow/outflow
rule, and return/outlet path for every face. Show that the pair is supported
by the pinned GPU pressure solver (`PP`, `DD`, or `NN` family only) and that
whole-face outflow treatment cannot overwrite the slot mask. The source face,
return path, and any periodic faces must be compatible. If that full mapping
cannot be demonstrated, stop without running source CFD. A compatible
diagnostic box qualifies only the source implementation; it is not an external
aircraft-flow model.

Freeze mesh, timestep, material constants, solver tolerances, all boundary
conditions, source-face orientation, mask indices/areas, and exact start/stop
steps in the run contract before launch. Enforce time-step alignment at each
pulse transition. Define net volume flux from the solver's signed face-volume
fluxes and divergence/continuity norm from the pinned solver diagnostic;
retain both at every step in the one-slot, four-slot, and crossflow stages.
Freeze the exact global and interface Courant formulas from the pinned
implementation. Proposed limits `Co <= 0.5` and `Co_interface <= 0.25` are
inherited from the CPU OpenFOAM characterization and need explicit
justification and review before being used for FluTAS. The candidate's
`constant_dt=T` path bypasses upstream `chkdt_tw`; a `cfl=0.2` input is not an
enforced timestep safety factor on this path. Before any source run, derive and
independently review the complete pinned advective/viscous/gravity/capillary
timestep restriction, include the zero-advection fallback, enforce exact
material/gravity inputs, and choose a prospective fixed-step safety margin or
amend the timestep and schedule. Do not infer stability from advective Co
telemetry alone. The pinned pressure path is direct FFT/tridiagonal rather than
an iterative pressure solve; freeze a source-supported `not applicable`
disposition for iterative residual/iteration budgets and use reviewed
projection/continuity checks instead. Keep the first solver checks to one GPU
rank and a small mesh; use the project GPU lock. Record source revision, image
ID, input hashes, GPU/driver, sampled VRAM/RAM, step timing, pressure algorithm
identity, and all failed attempts. No refinement or 1–3 million-cell pilot is
part of this gate.

## Known crossflow timestep guard outcome

For the frozen 50 m/s crossflow profile, `dt=1e-4 s`, and
`fixed_step_factor=0.2`, the pinned AB2 startup estimate gives
`dtmax=4.9990777606081648e-4 s` and `dt/dtmax=0.20003689638113265`; the guard
rejects U0 before consuming an interval. This applies to both `dry_crossflow`
and `crossflow_four`. The inputs are retained as expected-negative guard
fixtures, not executable crossflow runtime cases. See the primary arithmetic
record at
[`FLUTAS_CROSSFLOW_GUARD_ARITHMETIC_PRIMARY_20260925T121916Z.md`](../docs/reviews/FLUTAS_CROSSFLOW_GUARD_ARITHMETIC_PRIMARY_20260925T121916Z.md).

The positive source-free/runtime sequence therefore uses quiescent `dry_four`
followed by one-slot and four-slot checks, after all gates pass. Do not launch
either frozen crossflow case or claim crossflow qualification. A positive
crossflow case needs a prospective versioned protocol/case amendment and exact
independent review; it must preserve or explicitly redeclare pulse duration,
dose and observation horizon. Do not silently relax the guard or modify
inputs to pass.

## Staged checks

1. **Pure schedule/mask tests (no solver):** mask areas equal the exact
   grid-aligned geometry; masks are disjoint; no active cells exist outside
   declared slots; pulse endpoints use the half-open interval above; inactive
   slots and times have zero source-velocity contribution; inactive and
   off-mask inflow requests zero source alpha, while outflow alpha is always
   extrapolated from the interior. Exercise source-aware alpha/rho/mu handling
   after every generic boundary/property fill that feeds VOF or momentum,
   including the post-advection path before the momentum update. Include an
   inflow-to-outflow change over an inactive mask and confirm interior alpha
   and material properties are extrapolated on outflow.
2. **Dry boundary check:** run the quiescent `dry_four` baseline with zero
   liquid fraction and no active source. Require zero liquid geometric phase
   flux through every face at every step, no solver instability and no
   unhandled boundary state. Exercise the frozen `dry_crossflow` startup guard
   only in static/host-negative fixtures; it cannot be run with the current
   fixed-step inputs.
3. **One-slot square pulse:** start from a uniform, quiescent box with one slot
   active. Define inward normal flux as positive and integrate geometric
   liquid phase flux by slot. For vector momentum flux, multiply each signed
   geometric liquid volume flux by `rho_l` and all three velocity components
   interpolated to that geometric face from FluTAS's staggered fields.
   Document the pinned interpolation and sign convention and retain each
   component before reduction. In the uniform-velocity fixture, this must
   reduce to injected mass times the prescribed velocity vector. The analytic
   injected mass is `rho_l * A_slot * |v_n| * N_active * dt` for constant
   `dt`. Requested and applied face velocities, mask area, alpha/rho/mu
   boundary state, and flux histories must be retained.
4. **Four-slot symmetric pulse:** activate all four slots with identical
   schedule and velocity. Preserve separate per-slot fluxes and the total,
   using deterministic increasing slot-index then face-index accumulation in
   double precision. Record the reduction order in the run manifest.
   Verify each slot against its own analytic dose, symmetry between the four
   integrated slot doses, and equality of total dose to four times the
   one-slot dose at the same timestep and mesh.
5. **Crossflow/gravity source ledger check:** this positive check is blocked for
   the current frozen input because its U0 timestep guard rejects. After a
   separately reviewed prospective case amendment, add the declared 50 m/s
   background crossflow and gravity only after checks 1–4 pass. Record per-slot inlet mass
   and vector momentum flux, liquid outflow on every boundary, in-domain
   liquid inventory, net domain volume flux, divergence, and cumulative mass
   residual at every step. The chosen z+ source face has prescribed W (active
   or zero off-mask), so no reverse-flow/outward liquid flux is expected there;
   any outward source-face liquid flux fails the frozen-boundary check. Count
   the prescribed z− return as an all-boundary outflow using its actual phase
   fraction. Keep water already in the domain distinct from post-shutoff
   source flux; require zero new liquid influx after shutoff.

Stop at the first failed check. Do not tune mesh, timestep, schedule,
boundaries, solver tolerances, or thresholds after seeing a failed result; any
change requires a versioned protocol amendment and independent approval before
rerun.

## Acceptance criteria proposed for review

These are proposed verification budgets, not yet approved thresholds:

- Mask area and non-overlap are exact in cell-face counts; off-mask
  source-attributed liquid inflow and dry-case liquid flux are exactly zero
  in the recorded geometric phase-flux sums. Outward flow across inactive or
  source faces is retained as outflow, never zeroed or counted as input.
- At every solver stage, the source-velocity contribution on active and
  inactive mask cells matches the frozen schedule; background or tangential
  flow may remain outside the source mask. Prescribe alpha as 1 on active-slot
  inflow and 0 on all other inflow; on every outflow face extrapolate interior
  alpha and consistent material-property ghosts. No off-mask inflow is
  attributed to a source slot.
- For uniform one-slot and four-slot pulses, measured geometric phase mass and
  vector momentum flux agree with the analytic discrete schedule to floating
  point accumulation error using the documented fixed reduction order. Report
  absolute and normalized errors; do not silently broaden this criterion.
- The four symmetric slot doses agree with one another within 1e-10 relative
  error in the uniform test, and the four-slot total agrees with four times
  the one-slot dose within 1e-10. If the implementation or solver introduces
  a documented non-deterministic reduction that cannot satisfy this, stop and
  submit a revised bound with an error budget before rerunning.
- Let `M_in,cum(k)` and `M_out,cum(k)` be time-integrated inward and outward
  liquid mass, respectively, over **all six domain faces** through the end of
  interval `k`; let `M_source,cum(k)` separately record liquid entering the
  active source masks; and let `M_box(t)` be liquid inventory. The cumulative
  residual is `R(k) = M_in,cum(k) - M_out,cum(k) -
  [M_box(t_(k+1)) - M_box(t_0)]`. Report `R(k)` at every step in source-only
  and crossflow/gravity stages, normalized by `M_source,cum(k)` once it is
  nonzero, plus absolute and final-target-normalized residuals. Keep source
  attribution separate from control-volume closure; periodic-face in/out
  fluxes must balance as a pair. **The
  0.1% bound remains unapproved until independent protocol review.** No source
  liquid may enter after `n_off`.
- Require net volume-flux closure/divergence, source-mass, Courant, and
  pressure/velocity-solve limits in one-slot and four-slot as well as
  crossflow/gravity stages. Exact limits and formulas remain release-blocking
  fields for the final independently reviewed protocol; copied CPU Courant
  thresholds are not automatically valid for FluTAS. Any limit breach, solver
  failure, missing flux attribution, or missing resource record fails the
  gate.

The exact compatible boundary mapping, cell dimensions, timestep and its full
restriction/margin, number of active steps, source velocity vector,
projection/continuity limits, pressure algorithm and iterative-budget
applicability, and acceptable resource ceiling are intentionally
release-blocking fields. Code review must supply them from the final
implementation and frozen test input before launch. A blank field means no
solver run is authorized by this protocol.

## Claim limit and decision record

A pass permits a separately reviewed small GPU implementation/pilot decision.
It does not authorize calling a larger CFD run scientifically validated and
does not clear E1–E6. Record each stage as pass/fail/not-run, the exact gate
inputs and evidence bundle, deviations, and reviewer decision here and in
`docs/STATUS.md`. Keep failed bundles immutable.

## 2026-09-25 design review decision

The first proposed *open-outflow* top-face source override was stopped before
implementation or execution. In pinned FluTAS commit
`598210616bebd51f7d51f61455f196e6f3479916`,
`main__two_phase_inc_isot.f90:695–696` applies `bounduvw` after velocity
correction. With `is_outflow=true`, `sanity.f90:273–283` requires pressure D,
and `bound.f90:132–139` calls `outflow` for that face. At the upper z face,
`bound.f90:709–723` computes `w(i,j,nz)` from
tangential velocity divergence to make adjacent top-cell divergence zero.
Overwriting selected `w` values afterward changes that divergence by
`dzfi(nz) * (w_source - w_outflow)`. `chkdiv.f90:50–52` checks the same
top-cell divergence and `main__two_phase_inc_isot.f90:772–776` aborts if its
limit is exceeded. The source comments at `bound.f90:672–674` state the
outflow calculation assumes no volume source there.

An independent audit found a compatible paired source/return alternative in
the pinned code: on both z faces, use normal velocity `DD` with pressure `NN`
and set `is_outflow=false`; prescribe the localized source on z+ and a matched
return profile on z−, with periodic `PP` pairs on x and y. `sanity.f90:224–235`
lists the allowed pairings. With pressure Neumann on z, `bound.f90:320–425`
fills pressure ghosts with zero normal gradient, so `correc.f90:49–69` does
not change the prescribed z-normal boundary velocity. Because `is_outflow` is
false, `bound.f90:130–141` does not call the zero-divergence outflow override.
Choose the bottom return velocity each step so its integrated volume flux
exactly balances the active top-slot flux. This is a synthetic paired-return
box, not an aircraft external-flow boundary condition.

The verified sign convention uses Cartesian outward normals: z+ is top
(`k=nz`, `n=+z`) and z− is bottom (`k=0`, `n=−z`), per
`bound.f90:708–723,754–768`. Define signed outward volume flux
`F_f = integral_f(u dot n_f dA)`. An inward top source has `w_top < 0` and
`F_z+ = -Q`; the bottom outflow must also have coordinate `w_bottom < 0`, so
`F_z- = +Q`. For a uniform bottom return over area `A_return`, prescribe
`w_bottom = -Q/A_return`, using the actual active top source flux each step.
Verify `sum_f F_f = 0` from the solver's face-volume fluxes; do not rely only
on nominal patch areas. The implementation must check that its profile arrays
map these signs to the stated top/bottom indices.

This source-level audit corrects the earlier interpretation of
`sanity.f90:273–284`: executable validation requires pressure `D` when
`is_outflow=true`; it does not require the flag for every D-pressure face.
The paired-return mapping avoids D-pressure faces entirely. Candidate2's exact
patch remains blocked because its dry validator rejected `[0,0)`, its active
bottom return left periodic momentum-stencil halos at zero, and source-off
interval 12 could use stale liquid alpha/property ghosts and VOF reconstruction
during its first sweep. Candidate3 repairs those reviewed code defects; Astra
Max accepted its exact patch/build for a source-disabled GPU regression, which
passed. That run contains no source-boundary input and does not exercise the
source-on helper. Candidate3 still lacks measured per-step Courant and
interface-Courant telemetry, complete output semantics and a fail-closed
analyzer; numerical/resource limits and the full execution contract remain
unapproved. No source-slot CFD has run.

Keep source-enabled runs closed until a corrected candidate passes independent
review, behavioral tests cover dry/active schedules and periodic/state
transitions, runtime Courant and interface diagnostics and fail-closed
analysis are in place, and the complete pre-run contract and limits are
approved. A narrowly scoped source-disabled regression may be run only after
independent review of the exact candidate and must not be described as the dry
source gate. Then run source diagnostics sequentially, starting with dry and
stopping at the first failure. If the mapping or balanced return cannot be
maintained at every step, stop and revisit a projection-integrated source or
another conservative formulation.
