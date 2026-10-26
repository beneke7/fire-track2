# Live project status

Updated: 2026-10-26 23:14 UTC. Priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.
User reaffirms workstation scope: tank → valves → pipes → four nozzles.
Rouaix/aerial experiments remain owned by the HPC thread; local outputs are
tank pressure/inventory and per-nozzle discharge/velocity histories.

HPC/Rouaix status is maintained separately in [HPC_STATUS.md](HPC_STATUS.md).
At 21:43 UTC the corrected 120-rank trial and its automatic terminal audit
have completed successfully. Upwind and 5 s cases wait on Priority; no CFD
cores are allocated. Two dependent terminal inspectors remain armed.
No new scientific gate passed.

## Current execution

No complete credible tank-to-nozzle trajectory exists yet. The latest
completed discharge trials failed their numerical screens;
failed fields are not restart inputs. A separate pressure-reconstruction trial
and tighter pressure-only diagnostic have ended. The latter damps the tested
pressure disturbance with held physical fields; this does not establish global
operator stability. A separate diagnostic continuation is live from the healthy
.390706 s cold-derived checkpoint. The case-staging utility passed ten regression tests and the real-apparatus
staging smoke; exact immediate-parent source recovery is complete. The source
rebuild reproduced the exact baseline binary; a one-step equivalence test is
preparing after a preserved MPI-user launch error. The mechanical-feedback
probe is live under its exact-ID guard.

| Latest test | Saved time (s) | Actual outcome |
| --- | ---: | --- |
| Cold-derived predictor-off, full source, proper Euler history | .484006 | Persistent pressure updates, final 394.097 Pa / 2.493 m/s; no raw floor contact |
| Same healthy warm seed, predictor off, source weight 1 | .494129 | Persistent pressure updates, final 1254.224 Pa; no raw floor contact |
| Same warm seed, source relaxation weight .5 | .494130 | Same late failure window, final 1253.704 Pa; no raw floor contact |
| Same warm seed, predictor off, maximum timestep 25 microseconds | .461923 | Two raw contacts at .461873 s: -2.671 and -62.001 kPa; one water-bearing cell |

The cold-derived run `f960b72b8049` finished at 21:59:19.36122318 UTC, normal
End/native checkpoint .484006034892. Its 1.0 s target was not reached. The
preceding cold startup had saved at .090771 s because of the 20 GiB disk guard;
that operational split had all fifteen fields/time hash-checked and proper
history initialization. It is not proven bitwise-equivalent to uninterrupted
apparatus integration. The timestep trial `c3eedf2f3a2f` finished at
21:47:03.684869702 UTC, after 75 steps. The .01563 kg in its contact cell is
liquid support, not removed water mass. Its final recovered minimum of
63.39 kPa and tiny final pressure update do not undo the raw negative pressure.
The failed no-step launch before it is retained separately as a preparation
error: cleanup removed the static collated mesh. The corrected launch checked
all 53 mesh/addressing files before GO.

Runtime authorities and compact outcome data:

- `results/runs/i4f-cold-momentum-predictor-off-continuation-20261026T2048Z/guardian-status.json`
- `results/runs/i4f-gamma-outer-relaxation-20261026T2027Z/gamma-mpno-omega1-dt25us-retry01-on/guardian-status.json`
- [Warm comparisons and timestep outcome](../results/summaries/i4f_20261025/gamma-outer-relaxation/gamma-outer-relaxation-negative-outcomes.json)

Current independent tasks:

- **Pressure-only operator probe:** Luna implements a replay to the failure
  stencil, then freezes flow, phases, temperature, momentum/pressure
  coefficients, sources and physical boundary gradients. Only pressure and
  its explicit nonorthogonal correction iterate: eight sweeps plus centered
  1/10 Pa perturbation responses. The first probe was inconclusive: its
  eight baseline and 1 Pa solves took zero iterations at the normal 1e-10
  tolerance; 10 Pa took one iteration and failed amplitude agreement. A new
  replay tightens only diagnostic maps to 1e-14, leaving the physical replay
  unchanged. Docker `fa6d93ab0de6`, StartedAt 22:38:28.320884831 UTC, ended normally
  at 22:53:25.623349021 UTC. Tight baseline solves took 6/3/3/2/1 iterations
  before reaching the residual floor. Centered 1/10 Pa response gains are
  .03256/.03158, with 23.2% relative vector-shape discrepancy; this supports
  selected-direction damping but not a precise amplitude-independent derivative
  or global stability. All 38 held-field checks match. The next discrimination
  is mechanical pressure/density/momentum feedback with water transport held,
  with the worker source-order sequence reviewed and authorized. The next
  probe Docker `7d24b34e1a23`, StartedAt 23:09:04.824336741 UTC, is
  confirmed live with ten MPI/eight CPUs and 32 GiB. It starts after the complete
  original pEqn/EOS/U update (a later stage
  than the pressure-only capture), holds water/temperature/turbulence state,
  preserves source ordering and old-time history, and stops censored on a
  first raw pressure-floor contact. It writes no physical endpoint. This follows
  the focused Astra review;
  it is an algebraic test, not a discharge continuation. The measured source
  change largely cancels the changed alpha-times-flux divergence, making it
  a response to the pressure mode rather than an established driver. No more
  source-weight or timestep sweeps are queued.
  [Tight-map evidence](../results/summaries/i4f_20261025/tight-pressure-map/summary.json)
  includes scalar results and a portable source delta. Root applied it to a
  clean published base and verified all 69 declared source hashes, plus 13
  packet artifacts and 41 referenced local raw-vector artifacts.
- **Completed reconstruction trial:** one named pressure-Laplacian
  `Gauss linear limited 0.5` comparison with other diffusion/gravity schemes
  unchanged was tested as a numerical hypothesis;
  it is not an adopted method or cause proof. The possible pressure/gravity
  discretization mismatch is declared. Docker `09366119582b` ended at
  22:15:59 UTC, saving .474986 s after the unchanged pressure-update screen.
  It had no raw floor contacts, but its coupled defects were worse than
  the nearest-time baseline. Final dp had recovered to 42.8 Pa after the
  stop request; the .505 target was not reached. This is not a remedy.
- **Diagnostic continuation:** Docker `87c69f24d16d`, StartedAt
  22:34:41.550545949 UTC, ten MPI/ten CPUs, uses the unchanged corrected
  pressure operator and exact .390705595007 cold checkpoint. Only the
  >100 Pa update stop ACTION becomes advisory with identical thresholds
  and a flushed event CSV. Raw floor/clipping, mass/phase, NaN, disk and wall
  stops remain hard. Root reviewed that guard delta. At 23:02 UTC it had completed
  641 steps through .490599 s with zero raw floor contacts, but 68 consecutive
  pressure-update warnings and final updates about 1.34–1.60 kPa; no recovery
  from that criterion was established. Luna is auditing a frozen completed-step
  prefix for signed oscillations and engineering observables. Its CPU quota
  was raised from eight to ten after the pressure-only job ended, with exact
  identity/StartedAt, memory and deadlines unchanged; adjustment provenance
  remains in its private bundle. Target .65 s; save 00:49 UTC,
  hard 01:04 UTC on 27 October. Underconverged fields will not become a
  validation pass merely by finishing. Its launch had three preserved
  preparation attempts; the exact live ID/guard/seed hashes are recorded.
- **Mesh candidate:** the initialized 0.8 m base has 293,356 cells and
  matching 48 axial valve layers at 6.25 mm, 5,376 cells per branch. Its nine
  configured quality rows are zero, but four baffle-boundary faces fail
  generic skewness (max 4.816); optional allGeometry flags 6,087 concave
  cells. Three separately preserved mesh repairs did not clear the generic
  check. The last, uninitialized 311,318-cell repair has one boundary face
  at skewness 4.052 and 6,894 concave cells. The 1.0 m baseline has generic
  Mesh OK/max skew 3.230, with 6,345 concave cells as a separate qualification.
  No dimensions, dividers or thresholds changed, and no 0.8 m CFD has run.
  Its corrected source-zone classification is complete; the baseline was
  independently checked as fully classified and wetted: 21,504 source cells,
  .0841063 m3. The earlier omission was confined to the new candidate's prep.
- **Rendering completed:** Luna extracted the cold-terminal controller and created
  matched native-field .3907/.484 s views and a stencil zoom. Root inspected
  them; only the clear cutaways are selected for release. Underconverged
  endpoints remain labelled. No complete discharge movie exists.

New compact evidence is ready for inspection:

- [Startup energy audit](../results/summaries/i4f_20261025/firststep-energy/firststep-energy-evidence.json)
  and [exact local matrix budget](../results/summaries/i4f_20261025/firststep-energy/firststep-temperature-matrix-evidence.json):
  the predictor produces about 713 m/s in two pure-air cells before temperature
  is solved. Kinetic energy gives -354.03 K; implicit diffusion contributes
  +72.92 K, yielding the measured -281.11 K. Root recomputed both balances
  from raw CSVs. All fifteen fields/time match in the observer passivity tests.
  This closes two local first-outer equations, not global physical energy.
  A separate metadata correction preserves the original experiment while
  stating volume-integrated FV units (source/residual kg K/s, diagonal kg/s).
- [Early hydraulic comparison](../results/summaries/i4f_20261025/current-cold-hydraulics/current-cold-hydraulics-prefix.png)
  freezes the scalar prefix through .294771 s and compares four exact times
  through .250021 s. At .2 s mean tank flow is .432743 m3/s, +.462% versus
  the adiabatic reduced model; local headspace pressure is +1.749% versus
  its bulk pressure. Common Cd/geometry inputs and different pressure
  measurement support make this internal consistency, not validation.
- [Restart packet](../results/summaries/i4f_20261025/restart-history/README.md):
  proper Euler history reduces the channel's one-step restart error to
  7.92e-9 Pa. Root verified 335 artifacts and A/C/D staging. Its new rebuild
  recipe has not been exercised. A separate .1 s periodic equilibrium test
  and eight source-active channel cases remain limited numerical evidence.

Twenty effective CPUs are shared with unrelated work. Allocations are measured
at launch; there is no fixed reserve or reason to retain old small prep quotas
when capacity becomes free. No GPU or HPC jobs are launched here. Disk guard
remains 20 GiB. Verified duplicate-only cleanup recovered about 9.36 GB during
concurrent filesystem activity; 2,228 removed paths have 401 retained canonical
files and a tested [public recovery map/helper](../results/archives/manifests/i4f-polymesh-dedup-20261026T2038Z/README.md).
An additional 60 closed text logs were losslessly compressed, with all archive
hashes independently verified: about 1.83 GB measured free-space recovery.
The restore smoke reproduced bytes and metadata and refused overwrite; the
[manifest/helper](../results/archives/manifests/i4f-closed-log-retention-20261026T2240Z.json)
and archive index preserve recovery. No unique fields/meshes were deleted.
The immutable-template/canonical-checkpoint staging API passed Ruff, formatting
and ten regression tests including the public channel packet. The real-apparatus
staging smoke succeeded after rejecting a runtime-mutated T.air source; root
independently verified all 174 staged files and independent checkpoint copies.
One time-local functionObjectProperties file is intentionally outside the API
contract; no physical restart was executed. It changes no live solver or guard.
The [exact immediate-parent source](../results/summaries/i4f_20261025/immediate-parent-source/README.md)
for the startup energy baseline is recovered, including original build recipe
and pinned image/library identities. Root verified 100 artifacts, also
from a clean Git archive. A fresh isolated rebuild reproduced the exact 12d8
baseline executable hash. The first one-step launch exited before stepping
because MPI ran as root; its retry matches the original non-root user.
The one-step native-field comparison remains pending. The ancestor packet alone was insufficient.
Unique fields and original source/CAD remain. Older outcomes and restorable
archives are retained in the scientific note, published results index and
[archive index](../results/archives/index.json). Thirteen focused tests passed
for the merged HPC audit module, plus Ruff; those checks do not certify CFD.

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
- **The uninterrupted cold constant-density path also contacted the pressure
  floor.** It saved a complete checkpoint at .434531925092 s after eighteen
  raw contacts. This is separate from the earlier operationally restarted
  .413689→.434224 s path; do not combine their pressure histories.
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
  water storage alone did not eliminate the failure; the smaller-timestep test also contacted the floor. Time refinement alone
  has not supplied a remedy. The .343481 s audit observation was intermediate,
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
- **A sealed-gas pressure budget narrows the provisional design question.** The
  [per-tank analysis](../results/summaries/i4f_20261025/sealed-gas-pressure-budget/pressure-budget.json)
  and [plot](../results/summaries/i4f_20261025/sealed-gas-pressure-budget/pressure-budget.png)
  use 12 bar absolute nominal pressure, with 13 bar sensitivity, 1.35 m3 tank
  water, 22.5% headspace and corrected 1.0/0.8 m downstream volumes. For the
  n=1.4 reference, full-bore priming leaves 3.478/3.771 bar; the sealed-gas
  formula reaches 1 bar after about 1.056/1.098 m3 nozzle delivery per tank.
  This is a pressure-equalization reference, not a delivery maximum: inertia and
  elevation can sustain flow, while valve/pipe losses and initial-air purge
  dynamics, heat-transfer rates, CO2 and foam are not modeled. The headspace
  sweep holds water fixed, so it also changes assumed total vessel capacity.
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
  explicit. Independent read-only review found no material defect. Full
  workstation `make check` at 15:35:25 UTC on commit `06a41f1` plus the then-dirty
  source tree reported **920 passed, two skipped, four subtests**; Ruff checked
  166 files and formatting was clean. After merging `43cb951`, the two changed
  HPC test modules reported **88 passed, one skipped** on `7caf306`; their
  changed Python files passed Ruff/format and the batch script passed shell
  syntax checking. No HPC job was launched here. Check records:
  `results/runs/i4f-runtime-check-20261026T153334Z/` and
  `results/runs/i4f-postmerge-hpc-check-20261026T154602Z/`.
  Software checks do not validate the apparatus.

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
