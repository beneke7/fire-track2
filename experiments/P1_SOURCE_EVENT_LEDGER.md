# P1: resolved source event and conservative liquid ledger

**Status: revision 1 did not pass its frozen source-dose gate. Revision 2 passed
the frozen P1 gates under independently approved amendment 1, including an
independent raw-output audit.**

**Evidence class:** numerical solver/source-ledger diagnostic. This is not an
E1–E6 benchmark, breakup prediction, built-device representation, or field
validation.

## Question and purpose

Does a time-resolved, four-slot source on the unchanged P0 mesh deliver its
declared liquid volume, and does the solver's conservative phase flux close
against the in-domain liquid inventory and any liquid crossing open boundaries?
This isolates the source-cutoff discrepancy in P0 before any mesh refinement.

The P0 pilot intended 230.4 kg from a rectangular 0.08 s pulse but used a
0.1 microsecond shutoff ramp with adaptive steps as large as 0.378 ms. Its last
reported inventory was 0.269% above that intended value at 0.119177 s, and it
saved no per-slot phase-flux history. That comparison is diagnostic only; no
P0 conservation tolerance was registered.

## Prerequisites and fixed case

- Preserve the P0 2,081,200-cell mesh, box, boundary patches, fluid properties,
  gravity, 50 m/s idealized crossflow, laminar model, OpenFOAM 2512 image, and
  `interIsoFoam` solver configuration. Keep the same four 1.0 m by 0.15 m
  provisional slot patches and their 0.05 m edge gaps. The mesh has three cells
  across the short slot axis, so this case cannot qualify breakup or convergence.
- Use a piecewise-linear normal velocity table on every slot:
  `-4.8 m/s` at 0 and 0.0795 s; linearly to zero at 0.0805 s; remain zero
  through 0.12 s. The 1 ms stop ramp is centered on the provisional 0.08 s
  cutoff and is resolved by ten fixed steps. Its continuous integral equals
  the original rectangular dose: 57.6 kg per slot and 230.4 kg total at the
  assumed 1,000 kg/m³ density. These are explicitly provisional diagnostic
  inputs borrowed from the local Calbrix reference, not Restás measurements.
- Use `deltaT = 1e-4 s`, `adjustTimeStep no`, start at 0 and end at 0.12 s
  (1,200 steps). Both source-table knots align exactly with this step. Keep the
  P0 output cadence at 0.02 s and the 0.12 s final state; save compact flux and
  volume diagnostics every solver step. Keep `nAlphaSubCycles = 1`; with more
  alpha subcycles, this solver averages `rhoPhi` but leaves `alphaPhi_` holding
  only the last subcycle flux.
- Run up to 16 MPI ranks inside an 18-CPU Docker cap, reserve two host CPUs,
  cap memory at 48 GiB, and stop at one hour. P0 advanced about 0.443 simulated
  seconds per wall hour; 1,200 fixed steps project to roughly 40 minutes before
  added diagnostic output. Stop at the first logged global Co above 0.5 or
  interface Co above 0.25, or on solver divergence, missing diagnostic rows,
  resource limit, or timeout. These Co ceilings reuse P0's configured bounds;
  this run must enforce them as hard stop conditions rather than assume the
  time-step controller has held them.

## Flux and ledger method

OpenFOAM 2512's local `interIsoFoam` does not use the `alphaPhi0.water` field
name from the related `interFoam` code. Its `isoAdvection` object owns a
registered `surfaceScalarField` named `alphaPhi_`; `isoAdvection::advect()`
sets this field to `dVf_/deltaT`, the conservative phase-1 volume flux used by
the current VOF update. The installed source inspected inside the pinned image
is `$FOAM_SRC/transportModels/geometricVoF/advectionSchemes/isoAdvection/`
(`isoAdvection.C`, `isoAdvection.H`, `isoAdvectionTemplates.C`). The `IOobject`
uses `NO_READ`/`NO_WRITE` with OpenFOAM 2512's default `REGISTER` option, so a
`surfaceFieldValue` function object can sample `alphaPhi_` at every time step.
The independent reviewer confirmed the field registration, function-object
lookup, and its conservative phase-flux meaning from the pinned image source.
Function objects are dispatched by the time loop: a row at endpoint `t_n`
belongs to the completed interval `[t_(n-1), t_n]`; integrate each row using
`deltaT = t_n - t_(n-1)`, beginning with the known initial endpoint at t=0.
`alphaPhi_` records conservative transport before brute-force clipping and
interface snapping, which can alter alpha without revising the flux. Therefore
the residual also captures those corrections, as well as roundoff; it is not a
roundoff-only bound.

Create one signed patch-sum logger for each slot (`slot_01`–`slot_04`) and for
each open external patch (`airInlet`, `airOutlet`, `lowerOutlet`), with fields
`phi` and `alphaPhi_`, `operation sum`, and both execute/write controls at every
time step. `phi` is total volumetric flow; `alphaPhi_` is the phase-1 liquid
volume flow. Patch outward normals make slot delivery negative and outward
escape positive. Log `volIntegrate(alpha.water)` each step. The box walls and
symmetry planes have no liquid flux; still record all three open patches so
that any liquid escape is accounted for rather than assumed absent.

For each step, multiply the recorded step-averaged `alphaPhi_` by that actual
step duration. With water density `rho_w = 1,000 kg/m³`, compute

`M_source = -rho_w * integral(sum(alphaPhi_ over four slots) dt)`,

`M_escape = rho_w * integral(sum(alphaPhi_ over open patches) dt)`, and

`M_box = rho_w * volIntegrate(alpha.water)`.

The exclusive liquid ledger residual is `M_source - M_escape - M_box`. Also
report each slot's delivered mass and the `phi` versus `alphaPhi_` inlet
cross-check. Do not substitute mixture `rhoPhi` or `alpha.water * phi` for the
isoAdvector phase flux.

## Revision 1 acceptance limits (historical for the completed attempt)

| Check | Proposed requirement | Case-specific basis |
| --- | --- | --- |
| Time/event resolution | Exactly 1,200 steps to 0.12 s; all ten ramp intervals present; final state exactly at 0.12 s | Fixed 0.1 ms step aligns to both table knots and resolves the 1 ms ramp with ten samples. |
| Per-slot and total delivered mass | Within 0.1% of the right-endpoint expectations, 57.564 kg per slot and 230.256 kg total; also report against the continuous analytic targets 57.6 kg and 230.4 kg | Revision 1 treated `alphaPhi_` at `t_n` as the right-endpoint sample `U(t_n)`. The retained run showed that convention matches `phi`, while `alphaPhi_` corresponds to the completed interval and is one source-table sample earlier through shutoff. This original expectation is preserved as the historical revision-1 gate. |
| Box ledger | At every logged step, `abs(M_source - M_escape - M_box) / M_source <= 0.1%` once cumulative `M_source > 0`; report absolute and final-target-normalized residuals too | Source flux and inventory refer to the same completed step. Scaling by cumulative measured release avoids allowing an error close to one full step early in the source. This criterion is independent of the source-table quadrature because it uses measured phase flux for `M_source`. Record clipping/snap corrections. |
| Courant limits | No logged global Co above 0.5 and no interface Co above 0.25 | Reuses the P0 case's stated numerical limits; unlike P0, enforce them by an immediate stop. No overshoot is accepted. |
| Completeness | Every expected per-step volume and patch-flux row is present; mesh check passes; solver exit is zero; a final state is written | Missing data or a stopped attempt is inconclusive/failed, never a pass. |

The independent reviewer approved revision 1's flux-object lifecycle and
source/ledger limits with the sampling, subcycle, and normalization
clarifications above. The 0.1% thresholds remain frozen; they are not widened
by the amendment. The reviewer assessed fixed 0.1 ms as a reasonable
diagnostic choice, while treating the P0-scaled Courant estimate as planning
evidence, not a guarantee.

## Current protocol amendment

[Amendment 1](P1_SOURCE_EVENT_LEDGER_AMENDMENT_1.md) corrects only the expected
`alphaPhi_` dose to use the left endpoint of each completed interval:
57.636 kg per slot and 230.544 kg total. It keeps the 0.1% tolerance and adds
an explicit 0.1% check against the continuous analytic dose, 57.6 kg per slot
and 230.4 kg total. `phi` remains compared with its right-endpoint diagnostic
target of 57.564 kg per slot and 230.256 kg total. The independent protocol
review approved amendment 1 with revisions. A new prospective Astra Max
execution-code review approved the exact current Makefile and six-file launch
path on 2026-09-25. The exact hashes and review history are recorded in the
execution JSON; its status is `ready` for replay.

**Current replay readiness:** the previous execution review pinned Makefile
SHA-256 `5bfb80e6…`; the current Makefile is
`f6dfe1e6…`. Astra Max reviewed the complete current P1 target and found no
hidden prerequisites or evaluation hooks; the target calls the previously
reviewed launcher path with the frozen limits. The six-file hash map was
re-frozen prospectively without claiming to recover the historical Makefile
diff. On the real execution JSON, the launcher validator now accepts the exact
contract and rejects a deliberately mismatched Makefile hash. Five focused
test modules passed (59 tests), the regenerated case inputs match the accepted
revision-2 manifest byte-for-byte, and the local OpenFOAM image ID matches the
accepted run. No solver was launched during this readiness recovery; the
historical revision-2 result and raw-output audit remain unchanged.

## Run record and limits

- **Independent reviewers:** `scientific_contract` approved revision 1 with
  the explicit qualifications above, amendment 1 with revisions, and the
  earlier exact-hash execution-code review. `general_reviewer_astra` approved
  the prospective current Makefile/launch-path re-freeze. `p1_output_audit`
  independently recomputed the revision-2 source doses and ledger from the raw
  tables and confirmed the gate pass.
- **Execution status:** revision 1 was launched and did not pass its source-dose
  gate. Revision 2 completed in bundle
  `restas-source-ledger-20260925T015720.514566Z-8e93eda1`; the automated report
  and independent raw-output audit pass all frozen P1 checks. The old run remains
  ineligible for retroactive acceptance.
- **Code, solver image and input hashes:** generated per immutable run bundle;
  include the generated function-object dictionary, this experiment record,
  solver/image identity, and every case input.
- **Gate decision:** revision 1 did not pass its source-dose check. Revision 2
  passed its frozen source-dose, ledger, completeness, mesh, Courant, and
  execution checks, confirmed independently from raw data. This pass only
  establishes source timing and liquid mass accounting for this provisional,
  coarse P0 box; it does not establish mesh/time-step convergence, E1, breakup,
  or built-system behavior. See the
  [revision-2 result record](../results/P1_SOURCE_EVENT_LEDGER_REV2.md).
- **Known unknowns:** actual outlet geometry, pressure/discharge traces, foam
  properties, aircraft wake, mesh/time-step convergence, and any water escaping
  through the box boundaries beyond the short diagnostic duration.
