# Live project status

Updated: 2026-10-26 13:24 UTC. Priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.
User reaffirms workstation scope: tank → valves → pipes → four nozzles.
Rouaix/aerial experiments remain owned by the HPC thread; local outputs are
tank pressure/inventory and per-nozzle discharge/velocity histories.

## Current execution

- **Finite-compressibility water, first timestep setting: stopped numerically.**
  On the corrected 299,214-cell / ten-rank mesh, one intermediate pressure pass
  at .409998075890 s reached -308.269 Pa in two cells. The pressure floor was
  applied; .019267 kg is liquid support in those cells, not removed water.
  Docker `41ebc8ea6318` ended normally at .410222565383 s with all fourteen
  checkpoint fields. Its final pressure update was .159811 Pa and field minimum
  85.499 kPa after recovery; neither erases the prior floor event. Water ledger
  defect is +.120529 kg and gas -.000421 kg. This test has not supplied a remedy.
  Authority: `results/runs/i4f-cold-finite-water-eos-n2-20261026T1108Z/stock-campaign-status.json`
  is terminal, with no automatic restart. The [cell/iteration review](../results/summaries/i4f_20261025/finite-water-floor-review.json)
  reconciles all ten rank summaries: the event occurred on the last pressure
  pass, with a 32.54 kPa outer update and 5.014 m/s velocity update. Subsequent
  steps recovered. The affected nearly pure-water cells lie in the rising bend
  near x=3.437 m, z=.965 m; this does not establish a cause.
- **Finite-water smaller-timestep cold test: running.** Pilot `13324c8bdc84`
  completed normally at .050010583332 s. Its next preparation failed before GO
  because a child-local output-policy record was missing; the failed attempt is
  preserved. The repaired helper writes that record before freeze. The original
  controller resumed the healthy pilot without repeating it; stage01 Docker
  `4b8fa349b80d`, StartedAt 2026-10-26T13:18:45.043691461Z, ten MPI / 8.8 CPU
  equivalents, has advanced beyond .050636 s with zero contacts/errors.
  Initial deltaT=5e-6 s, maxDeltaT=.000125 s, maxCo=.25 and maxAlphaCo=.125;
  the same EOS, mesh, partition, binary, source and turbulence are retained.
  This is adaptive time refinement, not a claim of exactly half every step.
  Targets are .46 and 1.3 s if healthy; pressure/mass/capture stop rules remain.
  Authority: `results/runs/i4f-finite-water-eos-halfdt-conditional-20261026T122804Z/stock-campaign-status.json`;
  controller `i4f-finite-water-eos-halfdt-conditional-20261026t122804z-campaign.service`.
  Original finish deadline **2026-10-27 06:23:53 UTC** (+300 s capture margin).
- **Fresh constant-density cold control:** the .050021166664 s pilot completed
  normally with all fourteen checkpoint fields. After a preserved launcher
  packaging failure before GO, stage02 resumed that healthy pilot; Docker
  `efd36809073d`, StartedAt 2026-10-26T12:18:00.051165253Z, ten MPI ranks / 8.8
  CPU equivalents initially, increased to 10 after a fresh capacity sample;
  ten MPI ranks remain unchanged. Target .46 s and then 1.3 s if healthy.
  No pilot was repeated.
  Controller `i4f-rhoconst-cold-control-recovery-v2-20261026t1217z.service`.
  Authority: `results/runs/i4f-rhoconst-uninterrupted-cold-control-20261026T1110Z/stock-campaign-status.json`.
  Both current arms retain the same ten-rank partition, binary, eight outer
  iterations, two pressure correctors, SST and standard phase-source treatment;
  their time controls differ by the declared refinement above.
  Admission respects unrelated work; EOS reservation remains protected during
  healthy child-restart gaps and pending terminal capture. Future children may
  reclaim its reservation only after authoritative whole-campaign completion
  and inactive controller, with PAUSE/unknown states failing closed. Normal
  .05 s pilot continuations occur in both arms; the new control specifically
  avoids the earlier parser-induced .413 s restart.
- **Internal warm upwind probe: armed, waiting.** From the complete healthy
  finite-EOS .400019820001 s checkpoint, change only momentum convection from
  `linearUpwind grad(U)` to `upwind`, keeping the full-step time controls and
  strict health rules. Targets .46 then .7 s if healthy. This tests a numerical
  mechanism near the bend; its mixed-scheme history is not a cold uniform-scheme
  verification or production adoption. It launches only after one current whole
  family is terminal/captured, preserving the other's ten-CPU reservation,
  actual capacity and PAUSE. No GO/solver exists yet. Authority:
  `results/runs/i4f-upwind-momentum-warm-20261026T130013Z/conditional-status.json`;
  service `i4f-upwind-momentum-warm-20261026t130013z-conditional.service`.
  Original deadline remains **2026-10-27 06:23:53 UTC** (+300 s capture margin).
- **Rendering:** a single serialized CPU/Mesa watcher follows the smaller-timestep
  EOS and constant-density families' separate native histories. It waits for a healthy complete state >=.65 s with resolved
  water, plus an optional normally completed 1.3 s endpoint. Cameras/scales match;
  10x playback holds actual saved states without temporal interpolation.
  No new discharge movie exists. Authority:
  `results/runs/i4f-cold-pair-render-20261026T1247Z-attempt3/watch-status.json`;
  service `i4f-cold-pair-render-20261026t1247z-attempt3.service`;
  fixed deadline **2026-10-27 06:53:53 UTC**.
- **Resources and retention:** make doctor confirms twenty effective CPUs and
  about 118 GiB available RAM. Both ten-rank solvers are now running with a
  shared CPU budget (18.8 allocated CPU equivalents, plus measured unrelated
  work ~1.16). No GPU solver/rendering job was launched. Closed historical
  gas-boundary VTK exports were losslessly archived, recovering 2.05 GiB net;
  fifty-eight closed solver logs were also archived in two bounded passes,
  recovering another 6.09 GiB. Each file is hash/type/metadata verified before its uncompressed duplicate is removed;
  current family histories, native checkpoints and scalar ledgers are excluded.
  Free space is about 28.5 GiB after these passes. The runtime save
  floor is **20 GiB**; 25 GiB is a bulk-staging planning target, not a general
  write ban. Future continuation stages retain scalar diagnostics,
  four-mouth data and native .05 s snapshots while disabling only the three
  redundant external-gas boundary VTK exports; existing stages are untouched.
  [Archive index and restore paths](../results/archives/index.json).

## Findings that determine the next experiment

[Four-trial numerical outcome data](../results/summaries/i4f_20261025/pressure-filling-diagnostic-outcomes.json)
retain exact checkpoints, stop reasons, ledger values and source hashes.

- **Geometry correction alone did not resolve the pressure instability.** The
  corrected-junction constant-density run saved .413688544708 s after an MPI-log
  parser error, then its recovered continuation encountered raw pressure down to
  -330.889 kPa and stopped at .434224203921 s. Nineteen contact passes and twenty
  cell traces reconcile. Maximum 0.006118 kg liquid support in contact cells is
  not removed water mass. Alternation of pressure and gas density across
  corrections within one timestep motivates testing physical liquid pressure
  storage; it is not a resolved pressure pulse or evidence of cavitation.
- **Fewer pressure correctors did not supply a converged discharge.** From the
  clean .413689 s checkpoint, one corrector stopped at .440685508369 s with
  persistent 7.78 kPa pressure and 8.10 m/s velocity updates, despite no floor
  contacts. The 456,954-cell tank-interface case stopped at .445300991960 s with
  3.00 kPa and 4.58 m/s updates. The older 881,431-cell bend/outlet case stopped
  at .396174757798 s on its persistent-update screen. These remain distinct
  meshes/source treatments and failed diagnostic trials, with no automatic
  restart. The 100 Pa / three-step update screen is exploratory, not a formal
  validation or nonlinear-convergence tolerance.
- **Finite-water test is physically scaled and explicitly provisional.** The
  [material packet](../experiments/i4f_physical_water_eos_reference/i4f-physical-water-eos-reference.json)
  derives reference sound speed 1482.344344 m/s at 293.15 K and 0.1 MPa from
  IAPWS SR6 equations. `adiabaticPerfectFluid` uses assumed pressure exponent
  7.15 and B=306.668 MPa, with constant heat capacity; the exponent is not Cp/Cv.
  This is a barotropic compressibility sensitivity, not full IAPWS thermodynamics
  or a validated pressure-range material model. Initial water volumes match
  the control (3.202166 m3 including feeds); EOS density increases initial water
  mass by 1.606277 kg. Initial p_rgh is recomputed consistently, without fitting.
  The [runtime audit](../results/summaries/i4f_20261025/finite-water-runtime-audit.json)
  confirms EOS selection and reconstructs .05 s water inventory within
  2.1e-11 kg of the guard. Its later .410222 s pressure-floor stop means finite
  water storage alone did not eliminate the failure; the smaller-timestep test
  now examines sensitivity. The .343481 s audit observation was intermediate,
  not the final outcome or exact conservation.
  The focused independent blocker review recommended this cold comparison after
  the one-corrector diagnostic, followed by a complete trajectory and selected
  time/outer/mesh checks if healthy. No equation relaxation is being adopted.
- **Local mesh remains a sensitivity, not a proven sole cause.** Both latest
  contact cells have positive volume and three internal neighbours. Aspect ratios
  ~3.5 and nonorthogonality ~42 degrees pass configured limits, although their
  determinants and volume ratios lie in the poor-quality tail. No collapsed or
  disconnected cell was demonstrated. The earlier exposed ~18.5 mm shoulder
  was a real reconstruction artifact; its removal changes downstream air
  storage by -1.012 L while preserving tank/feed geometry. The corrected mesh
  passes all nine configured quality rows; optional checks report 6,345 concave
  cells. [Geometry evidence](../results/summaries/i4f_20261025/pipe-transition-join-summary.json).
- **Operational defects are separated from physical failures.** The
  [parser fix/replay](../results/summaries/i4f_20261025/parser-merge-replay.json)
  recovers an MPI-interleaved terminal record: all 1,644 completed steps parse,
  without changed equations or thresholds. One recovered step had a 3.45 kPa
  update, so parsing success does not establish convergence. The one-corrector
  guard now expects eight rather than sixteen phase records. First failed
  preparations, missing-mesh and resource-stop attempts remain preserved.
- **Early reduced-model agreement is useful but limited.** At .250021 s,
  mean withdrawal is 62.581 L CFD versus 62.210 L reduced model (+.597%);
  per-tank two-seat flow is .608803 versus .604200 m3/s (+.762%). Local gas-probe
  pressure is 946.934 kPa, versus bulk adiabatic/isothermal 920.654/989.501 kPa.
  [Comparison and sampling](../results/summaries/i4f_20261025/flush-early-cfd-model-comparison.json).
  The single full-bore front predicts mouth arrival .617–.625 s adiabatic or
  .585–.591 s isothermal, while CFD admits bottom filling with gas above. These
  are uncalibrated model predictions, not measured arrival or thermal bounds.
- **Gas energy and pressure observers retain qualifications.** Near .4 s,
  uniform-headspace delta(U*)+integral(pbar dV) is +137.319 kJ coarse / +92.225 kJ
  refined; it is not measured heat or a closed energy defect. A separate
  ~17.64 Pa native/fieldMinMax pressure discrepancy is associated with a
  ~6.15 mm runtime/stored cell-centre difference; its exact origin remains
  unresolved. Both minima were positive >87 kPa, so this does not explain the
  much larger subsequent raw failures.
- **Outlet diagnostics now handle both liquid EOS choices.** Native signed
  alphaPhi0.water remains the primary volume flux. Saved absolute cell pressure
  supplies phase-water density, interpolated to faces with the checked owner
  weight; reconstructed mass/momentum may combine different solver stages and
  are labelled secondary. Dry traces, backflow and undefined directions remain
  explicit. Independent read-only review found no material defect. Latest
  workstation `make check` after merging HPC commit `3c0ddaf`: **897 passed,
  two optional/evidence-dependent tests skipped, four subtests passed**; Ruff
  and case Python/shell checks passed. The earlier 750-test result preceded
  this merge. Software checks do not validate the apparatus.

## Inputs, limits and next result

The [hardware record](../experiments/i4f_hardware_notes_20261024.json) preserves
user-confirmed .900 m tank diameter, .300 m valve diameter, 1.350 m3 liquid per
tank, headspace .20–.25 times liquid volume, two tanks and two outlets each.
The reference uses 12 bar absolute, with 13 bar a declared sensitivity because
pressure convention is unknown. Roughly five seconds is discharge duration,
not measured valve-opening time. The compact provisional layout has no added
post-rise straight and a 1 m transition/mouth; four dividers start halfway.
Orientation, thickness, pipe ID and valve opening remain inferred/assumed.
Downstream passages initially contain air; tank-to-valve water is separate.
Air/water references do not model CO2 dissolution, foam or retardant rheology.

First obtain a healthy complete startup through mouth arrival and the declared
1.3 s endpoint. Then compare pressure, mass inventory, outlet flux and sheet
structure, with focused timestep/outer/mesh sensitivities before selecting an
engineering comparison. A mean-level intake-crown event is not emptying or
validated gas breakthrough. No-divider and valve-opening alternatives remain
conditional; the no-divider mesh is held on quality failures. No old aerial
queue or server case is resumed here.

[The scientific note](I4F_SCIENTIFIC_NOTE.md) and
[published results index](../results/summaries/i4f_20261025/README.md) retain
historical figures, failed trials and movies. Existing videos show earlier
partial runs and geometry, not the current corrected cold-pair discharge.

## HPC Rouaix work and GitHub evidence publication

HPC readback **2026-10-26 12:36:16 UTC (13:36:16 CET)**: job **14650641**
(one node, 120 ranks, fixed 0.1 ms toward 5 s, 72 h cap) and **14648472**
(300 ranks, three nodes, short 0.1 ms trial) were PENDING/Priority with no
allocation or start estimate. This timestamp is a snapshot, not live status.
No unrelated account jobs were changed. W&B remains offline pending a destination.

Short one-node T1 job **14649329** completed all 500 steps through 0.05 s;
all 4,001 linear-solver records met their configured criteria. Peak speed
103.29355 m/s, bulk/interface Co 1.12154/0.56017, mass residual 1.05e-11 kg.
G1 gradient-limiter trial **14648417** failed its speed guard after a
6,975.25 m/s peak and ended at 0.0455 s; it did not complete its target.
The 64/120/240/300-rank original-scheme timing samples do not establish
healthy long-time behavior or a universal optimum.

ParaView CLI displays the 10,099,265-cell result using the requested
cell alpha.water >= 0.01 threshold at 0.05 s. The early cloud comparison
uses alpha >= 0.1; its time, detector and unresolved paper-width convention
prevent a developed Rouaix agreement claim. Only analytical E0 has passed.

The [published compact evidence bundle](../results/summaries/rouaix_hpc_20261026/README.md)
contains selected measurements, hashes, preview, diagnostic source and check
results. The [preserved HPC status snapshot](../results/summaries/rouaix_hpc_20261026/hpc-status-snapshot.md)
retains the full prior history. Raw CFD archives/mesh remain in verified
local/HPC storage, outside Git; this is a summary release, not a standalone
raw-data reproduction package. Frozen queued-job source is unchanged by Git
integration or the later local max-U metadata and accounting-parser fixes.

Checks recorded by the HPC/Mac agent before this workstation merge: 201 affected tests and Ruff passed;
all seven fresh E0 analytical checks passed. Full make check is not green:
collection needs matplotlib; the pre-merge diagnostic excluding that module gave 775 passed,
19 failed and 6 skipped, involving platform support, missing dependencies,
missing ignored fixtures and a retained digitization mismatch. The compact
check report preserves those commands and outcomes. This workstation then
merged that history with the newer I4F work: its fresh Linux `make check` passed
897 tests with two skips and four subtests, plus case Python/shell checks.
These are different environment/source snapshots; neither software result is
a CFD acceptance pass.

