# Candidate4 source/runtime readiness audit — draft

**Disposition:** read-only B1-pre evidence audit for independent review. This is
not an accepted execution contract, a gate approval, or authorization to run a
source case. Candidate4 is exact-reviewed and has passed the source-disabled B0
GPU smoke; candidate4 has no source-on solver run, so B1-runtime is unmeasured.

## Finding

Candidate4 contains useful source checks and six planned CSV ledgers, and its
host harness exercises selected boundary transitions. The archived evidence
does not contain a candidate4 source-run CSV or solver log. The host CSVs were
written under a temporary build directory and removed when the helper runner
exited. The B0 runtime evidence explicitly omits `source-boundary.in` and runs
the upstream rising-bubble case.

The important B1-pre gap is observable coverage. Candidate4 does not serialize
alpha/rho/mu ghost values or a stage-indexed audit of them. Its one runtime
velocity assertion checks selected normal W values before VOF, but there is no
per-cell requested/applied vector history, and the aggregate velocity CSV
cannot substitute for one. The complete pinned AB2 restriction also is not
evaluated on the fixed-step path. On the nominal active crossflow profile, the
case's `cfl=0.2` safety factor would call for a smaller step than the frozen
`1e-4 s`, though that arithmetic is a profile estimate, not evidence of
instability. These items need an exact candidate revision or an independently
accepted executable assertion and a reviewed protocol before source-on launch.

## Evidence and exact sources

Candidate source citations below refer to added-line numbers in the patch
unless marked as Python or Fortran test lines. The candidate patch SHA-256 is
`2eddbe5cc406ecbc60e7ca1fe9ba3a5ff61b130283e74772b1593f1d385959ff`; the
candidate4 build manifest records this same hash. The pin is FluTAS commit
`598210616bebd51f7d51f61455f196e6f3479916`.

| Evidence | Exact identity |
| --- | --- |
| Candidate patch | [`source-boundary.patch`](../../containers/flutas/candidate4/source-boundary.patch), SHA-256 `2eddbe5c…5959ff` |
| Static/analytic source tests | [`test_source_boundary.py`](../../containers/flutas/candidate4/tests/test_source_boundary.py), SHA-256 `ea137fd9d9119bc753c16fe256f798c5cb2818c35a64ec113ea4c46900fc9c58` |
| CPU helper harness | [`source_boundary_validator.f90`](../../containers/flutas/candidate4/tests/source_boundary_validator.f90), SHA-256 `c44d1ba0f1b15877c2eaa518e54c6bd338e0d7b6ebb0729d813cce9edb2fe467` |
| Temporary-output helper runner | [`run_source_validator_tests.sh`](../../containers/flutas/candidate4/tests/run_source_validator_tests.sh), SHA-256 `25cf79c3eff8e7dc65d2da0d18702105b1b806cde8422b616febcbebc3225cca` |
| Candidate build evidence | [`docker-build.log`](../../containers/flutas/candidate4/evidence/runs/20260925T091602Z-1994261/docker-build.log), SHA-256 `7b8beef3309ad34faa533e627c654f0ec48dcf980d3156e9218d859049d5b630` |
| B0 source-disabled runtime bundle | [`20260925T095317Z-2015705`](../../results/runs/flutas-candidate-gpu-regression-20260925T095317Z-2015705/), manifest SHA-256 `b3fd948d34be4f82c0bdc2711a5ff01fdb845641e602d2113f2b874d81b2c2b4` |
| Current source gate | [`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md`](../../experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md), SHA-256 `6b63d4abd556cc9407bb5747ec825f770f8344c3d8fd9b7b5c4514c07c392636` |
| Astra B1–B3 deblock memo | [`BLOCKER_DEBLOCK_PLAN_CANDIDATE4_B1_B3_20260925T100500Z.md`](BLOCKER_DEBLOCK_PLAN_CANDIDATE4_B1_B3_20260925T100500Z.md), SHA-256 `0bc0244974b218243d4b8f12ef68c7a59b9dc384aa110f6808e44dd359838b9a` |

The upstream sources were read from the pinned GitHub commit, with the
following downloaded-source hashes and line locations:

| Pinned upstream file | SHA-256 | Relevant lines |
| --- | --- | --- |
| [`src/chkdt.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/chkdt.f90) | `68e9f9592220b6f7a80366e60ccceb0595685d7324977c3710656aab15b0e661` | 63–112 |
| [`src/apps/two_phase_inc_isot/param.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/apps/two_phase_inc_isot/param.f90) | `153519b5efb1be6b454a57a7bb6a96d7803511effe5d376e4b993df8cd8e4507` | 270–281 |
| [`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90) | `1d6450b3379b9995b0d69c0d8e22d8b038c66446ebd33066cfdffdf799616e22` | 497–506, 653–696, 749–779 |
| [`src/initsolver.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/initsolver.f90) | `e08a60f7b250352d437a6adb84a7fd04131ce394ba65c85675c7dbb860209dbb` | 58–118 |
| [`src/solver_gpu.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/solver_gpu.f90) | `ea483ff9f8c2fcf7180c880517e94404167bfecf6557f8b15d098a8a2b1ee5c6` | 112–174, 475–532 |
| [`src/fft.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/fft.f90) | `87ba946118917fcb503017331c21173973e42b1bcb7026d0edd3f65d251b55e4` | 196–230 |

The case manifest is
[`cases/source_boundary/SHA256SUMS`](../../containers/flutas/candidate4/cases/source_boundary/SHA256SUMS),
SHA-256 `529a81b0429e1f56d86bf2c1a8c691bcf8ae9037ef682d758fe1cb459fa1dc92`.
For the timestep examples below, the quiescent input hashes are `dns.in`
`929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0`,
`vof.in` `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54`,
and `source-boundary.in`
`20a95ee6da4a0e91cd9e6b4ba2775f20bccda0152c7182c6886d4523389780e2`.
Crossflow uses `dns.in`
`574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7`,
`vof.in` `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54`,
and `source-boundary.in`
`1f3b889429bae2b591eaa453fe2962a0d91f38ac1dbea025c30e2ffa6c2dfa2e`.

## B0 evidence is source-disabled; B1-runtime has not begun

The candidate build log records exact patch application, eight CPU helper modes
passing, two expected input rejects, a flushed expected rate failure, fourteen
Python tests passing, and an `sm_120.cubin` code object. The source behavior
harness is explicitly CPU-only and does not start the solver driver. Its runner
creates a `mktemp` directory and removes it on exit (runner lines 7–13 and
29–55), including the generated ledger CSVs. The build log records the checks,
not the temporary CSV files themselves.

The B0 bundle records the immutable candidate4 image and patch identity. Its
`source-disabled-preflight.txt` says `source-boundary.in` is absent; its staged
check reports a passing upstream rising-bubble run with `*** Fim ***` at step
1680 and time `3.001520526915884 s`. The archived solver log and `time.out`
belong to that 32×32×64 rising-bubble test. No `restas_*` CSV appears in the
bundle. These are useful build and source-disabled GPU evidence, but they do
not show candidate4 applying a source, projecting a source-on state, or
producing a B1 ledger.

## Gate observables mapped to candidate4

The producer schema appears in patch lines 604–641. The schema/count/value
tests are in `test_source_boundary.py` lines 455–591. A `PASS` below means the
static or synthetic helper check ran during the candidate build; it does not
mean a candidate4 source solver run generated that result.

| Gate quantity | Candidate4 source/output evidence | Archived candidate4 runtime evidence | Audit status |
| --- | --- | --- | --- |
| Frozen schedule, masks, one-rank uniform grid, paired boundary types | Validator restrictions in patch lines 256–399; case hashes above | No source-on run | Preflight restrictions are explicit and fail closed for supported inputs; runtime not demonstrated |
| Per-slot requested and geometric liquid volume/mass; reverse flow | `source-flux.csv` writer and requested/applied integrated fields in patch lines 717–777; synthetic row/count checks in Python lines 525–550 | No source-flux CSV | Producer formula is inspectable and helper outputs are checked; source-on result absent |
| Requested/applied momentum by slot | Requested impulse and mass-weighted face-velocity integration in patch lines 751–775; synthetic values checked in Python lines 536–540 | No source-flux CSV | Integrated momentum is serialized by slot, but no per-cell velocity values are |
| Off-mask top flux and rate mismatch | `source-offmask.csv` and `rate-check.csv` writers in patch lines 615–623, 644–653, 732–743; synthetic checks in Python lines 541–554, 577–587 | No source-offmask or rate-check CSV | Intended histories and synthetic checks exist; no source-on records |
| All-face liquid flux, inventory and mass residual | Boundary/mass headers in patch lines 624–633, accumulation in 662–715, inventory in 779–823; synthetic expectations in Python lines 555–567 | No boundary-ledger or mass-ledger CSV | Producer covers the planned quantities; no source-on result |
| Per-state advective Co, empty-interface semantics, net boundary volume and divergence | `velocity-audit.csv` header/writer in patch lines 634–640 and 825–909; synthetic checks in Python lines 568–591 | No velocity-audit CSV | Aggregate diagnostics are specified; no source-on result. The closure column is bookkeeping, not a continuity norm |
| Alpha/rho/mu boundary state at the stages that consume it | Boundary helper in patch lines 541–602; host assertions in Fortran lines 185–239; static call-order checks in Python lines 194–243 and 268–288 | No ghost-state history | Selected helper states pass, but there is no stage-indexed runtime history or full-stage assertion |
| Requested/applied boundary velocity at each relevant stage | Slot-top and full bottom W comparison in patch lines 457–489, called before VOF at lines 108–115; aggregate CSV only | No per-cell velocity data | Selected normal W is asserted before VOF; full per-cell vector request/apply observability is missing |
| Pressure solve and run completion | Pinned direct solver path below; source case should still log normal completion and resources | B0 only has source-disabled solver completion/resource history | No B1 pressure/runtime evidence |

### Ghost states and local velocities

`restas_source_prepare_boundary` applies alpha, rho, and mu only on actual
inflow. Top active-slot inflow gets liquid properties; all other top inflow
gets air; bottom reverse inflow gets air. Generic extrapolation remains for
outflow (patch lines 541–579). The patch refreshes alpha before geometric
flux/reconstruction and reapplies the source-aware property boundary after
post-advection `update_property` and generic property fills before momentum
(patch lines 91–99, 107–126, and 1018–1059; the static order checks are Python
lines 194–243, 268–288). The host harness exercises selected active inflow,
off-mask inflow, reverse bottom inflow, shutoff and outflow values
(`source_boundary_validator.f90` lines 185–239).

Those checks do not record the values for each solver stage. They also do not
independently assert every alpha/rho/mu ghost cell after every actual driver
fill. None of the six CSV headers contains alpha, rho, mu, a stage name, or a
ghost-state mismatch count. Thus the proposed gate quantity is neither
serialized nor fully asserted over the runtime stage sequence. The host
harness is good transition evidence for its selected synthetic arrays, not a
substitute for source-run history.

There is one narrower runtime assertion: `restas_source_assert_velocity`
compares every slot cell's top-face W with the interval's expected W and every
bottom W entry, including horizontal stencil halos, with the expected return
(patch lines 457–489). The driver calls it on incoming `U_k` before interval-k
VOF (patch lines 108–115). It does not emit those values. It does not compare
each cell's U/V/W vector, assert off-mask top W, or record checks immediately
after every source override. The initial `U_0` is applied and summarized, but
this assertion is first invoked at the first VOF interval. `source-flux.csv`
does serialize requested and applied **integrated** momentum per slot from
actual geometric flux (patch lines 751–775); that is not a per-cell requested /
applied velocity history. The Python checks assert helper text and selected
states, including bottom halo consistency, rather than archiving per-cell
values (Python lines 245–267, 289–385; Fortran lines 120–144, 267–301).

### Complete pinned AB2 timestep restriction

In pinned `chkdt.f90`, the advective rate is the global maximum over cells of
three staggered directional sums. For example,

```text
dtix = |u(i,j,k)|/dx
     + |v(i,j,k)+v(i,j-1,k)+v(i+1,j,k)+v(i+1,j-1,k)|/(4 dy)
     + |w(i,j,k)+w(i,j,k-1)+w(i+1,j,k)+w(i+1,j,k-1)|/(4 dzf[k])
```

`dtiy` and `dtiz` use the analogous four-face averages; the vertical normal
term in `dtiz` is `|w(i,j,k)|/dzci[k]`. The source sets `dtic=dti`; if the
global rate is exactly zero, upstream sets `dti=1` before proceeding, rather
than treating the advective rate as zero or infinity. Define
`h=min(dx,dy,dz,min(dzf))` and `nu_max=max(mu1/rho1,mu2/rho2)`. The remaining
two-phase rates and complete non-heat bound are

```text
dtiv = nu_max / (cfl_d h^2)
dtik = sqrt(sigma / (min(rho1,rho2) h^3))   if sigma != 0; otherwise small
dtig = sqrt(max(|gacc_x|, |gacc_y|, |gacc_z|) / h)
dtmax = min( 2 cfl_c /
             [dtic+dtiv + sqrt((dtic+dtiv)^2 + 4(dtig^2+dtik^2))],
             1/dtik )
```

The final `1/dtik` cap is present even with surface tension. With the candidate's
`sigma=0`, upstream substitutes `small`, so this cap is about `1.424e8 s` and
is inactive for the shown fixtures. If compiled with `_HEAT_TRANSFER`, there
is also a minimum with `dtth=cfl_d/(max(kappa/(rho cp)) h^-2)`; the candidate
two-phase build is adiabatic and does not take that branch. For AB2,
`param.f90` sets `cfl_c=1` and `cfl_d=1/6` (lines 273–280). The candidate's
`vof.in` has `sigma=0`, so these implementation fixtures intentionally omit
the capillary restriction for real water-air flow.

For its uniform 0.025 m mesh and stated material inputs,
`nu_max=max(0.001/1000, 1.8e-5/1)=1.8e-5 m^2/s`, hence
`dtiv=1.8e-5/(0.025^2)/(1/6)=0.1728 s^-1`. For crossflow gravity,
`dtig=sqrt(9.81/0.025)=19.8090888 s^-1`; it is zero in the quiescent cases.
The binary64 `small=epsilon(pi)*10^(precision(pi)/2)` is approximately
`7.02166694e-9 s^-1`. The following arithmetic uses constant-profile `dti`
values as a pre-run estimate, not a velocity history measured from FluTAS:

| Profile assumption | `dtic` (s⁻¹) | `dtmax` (s) | `1e-4/dtmax` | `0.2 dtmax` (s) |
| --- | ---: | ---: | ---: | ---: |
| Exactly zero velocity, including the upstream fallback `dtic=1` | 1 | 0.8526603 | 0.00011728 | 0.170532 |
| Quiescent active top W only, `4.8/0.025` | 192 | 0.00520365 | 0.01921728 | 0.00104073 |
| Dry crossflow only, `50/0.025`, `g=9.81` | 2,000 | 0.0004999078 | 0.200036896 | 0.00009998156 |
| Active crossflow and source W in one cell, `(50+4.8)/0.025`, `g=9.81` | 2,192 | 0.0004561312 | 0.219235179 | 0.00009122624 |

The active-crossflow row uses `dtic >= 2192 s^-1` for the declared uniform
background plus source-normal velocity at an active source cell. It is a
lower bound on the global advective rate, hence the listed `dtmax` is an upper
bound and the actual `dt/dtmax` can be larger. The dry-crossflow estimate is
for the stated uniform initial field; source-on evolved fields can also change
the maximum. Candidate unit tests verify `0.0192`, `0.2`, and `0.2192` as
static `dt U/h` arithmetic (Python lines 440–452), not as evolved-flow
stability evidence.

The driver normally sets `dt=cfl*dtmax` at initialization and at scheduled
stability checks (`main` lines 497–506 and 749–761). In candidate4,
`constant_dt=T` instead sets `dtmax=dt_input` and `dt=dt_input`; the same fixed
branch runs at every check. `restas_source_validate` requires that fixed path
and `1e-4 s` (patch lines 280–284). Thus the input `cfl=0.2` is ignored by the
source fixtures: it is not a safety factor on their fixed `1e-4 s` step. The
ordinary divergence check still runs (main lines 772–779), but it does not
evaluate the full timestep bound. Only the adaptive initial path and the
unconditional late-initialization path call `chkdt_tw`; candidate4 uses fixed
mode and explicitly rejects late initialization, so neither path supplies
this source fixture a full timestep check.

A prospective policy for independent review is to keep fixed integer-aligned
steps only if the recorded full bound satisfies
`dt_input <= gamma * dtmax(U_k)` for every accepted state, with a separately
reviewed `gamma`. Using `gamma=0.2` would preserve the apparent intent of the
existing input; it is a recommendation to review, not a proven stability
criterion. Under the nominal active-crossflow lower bound, `1e-4 s` exceeds
`0.2*dtmax` by about 9.6%; the static calculation does not prove the case
unstable. Either review a different prospective margin or version the input
step/schedule before launch. Advective Co alone is not the combined bound.

### Pressure solve and iterative residuals

The pinned application calls the pressure equation an FFT-based direct solver
(`main__two_phase_inc_isot.f90` header lines 9–12). `initsolver.f90` constructs
x/y eigenvalues, combines them, forms the z tridiagonal coefficients, and
prepares the transforms (lines 58–118). With the candidate's one GPU and
periodic x/y plus Neumann z pressure pair, the GPU path applies x/y FFTs and
calls `gaussel_gpu` for nonperiodic z (`solver_gpu.f90` lines 112–174). That
routine performs forward elimination and backward substitution on the
tridiagonal system (lines 475–529); `fft.f90` wraps the forward and inverse
cuFFT calls (lines 196–230). This is a direct separable solve, not an iterative
Krylov or relaxation solver. It has no iteration count or iterative stopping
residual to report.

Proposed reviewed schema treatment: set
`pressure_solver_kind=direct_fft_xy_tridiagonal_z`,
`iterative_pressure_iterations=not_applicable`, and
`iterative_pressure_residual=not_applicable`, with a source citation and an
explicit reason. Do not write numeric zero for an unperformed iterative
residual. Keep mass `residual_kg` distinct from any pressure-equation residual.
Freeze pressure-solve elapsed time/algorithm identity if required for the run
record, and use reviewed post-projection continuity checks instead. Candidate4
already has upstream `chkdiv`'s local maximum abort and writes maximum and
volume-integrated L1 divergence plus signed finite-volume closure in its
synthetic velocity ledger. The proposed gate must set independent limits for
maximum and L1 divergence; the closure identity is only bookkeeping. An
independently calculated algebraic `A p - b` residual is a possible additional
check if reviewers require one, but it is not an iterative residual and is not
currently produced.

## Exact next engineering change and review questions

If the gate requires the stated alpha/rho/mu and velocity observables, preserve
candidate4 and make the narrowly scoped instrumentation in a new candidate5:

1. Add stage-indexed phase/property ghost audits after each generic alpha fill
   plus source refresh before every VOF flux sweep, and after the post-advection
   rho/mu fills before momentum. Scan every relevant inflow/outflow ghost by
   face and class (active slot, off-mask, inactive source mask, reverse bottom
   inflow, and outflow). Serialize expected/observed mismatch counts, maximum
   absolute error and nonfinite counts for alpha, rho and mu; fail closed on
   nonfinite or mismatched expected states. Include interval/state and exact
   stage identifiers so pulse-edge rows cannot be joined to the wrong state.
2. Audit requested versus applied boundary U/V/W at initial `U_0`, the
   pre-projection override, corrected `U_(k+1)`, and before interval-k VOF.
   Include source-mask top cells, off-mask top cells and the full bottom face
   and halos. Serialize per-stage/per-component mismatch counts, maximum
   errors and nonfinite counts, or have an accepted assertion inspect every
   cell and preserve its failing location/value. Unit fixtures should corrupt
   one cell in each class and prove that the gate rejects it.
3. Record `chkdt_tw`'s complete `dtmax` (or equivalent independently
   recomputed terms) for every fixed-step state and make the fixed-step margin
   an explicit reviewed input. Keep `dt_input` integer aligned with the source
   schedule; if the reviewed margin requires a smaller value, amend the step
   and schedule before running.
4. Freeze the CSV schema, analyzer, run manifest and no-iterative-pressure
   disposition with an independent exact-hash review. Continue to report a
   source-on trial as B1-runtime evidence only after the ordered run actually
   produces complete finite histories and passes reviewed limits.

Questions for the independent reviewer: are stage summaries from full ghost
scans sufficient, or are raw ghost values required? Is a per-cell fail-closed
vector assertion plus compact mismatch summary sufficient for requested /
applied velocity, or should every boundary vector be serialized? What fixed
step factor and separate maximum/L1 divergence limits are justified for this
synthetic gate? Is source-supported `not_applicable` for iterative residuals
acceptable with the direct solver identity and reviewed continuity checks?

## Audit commands and checks

This audit used read-only file searches/line inspection and SHA-256 checks,
retrieved the cited raw source files at the pinned commit into `/tmp` for exact
line/hash review, and evaluated the timestep arithmetic with a short Python
calculation (one process/thread). It did not run tests, build, solver, CFD or
GPU work. Existing evidence reviewed: candidate build checks above and the
B0 run bundle's source-disabled preflight, stage checks, metadata and solver
log. No external input, geometry or measured property was introduced.
