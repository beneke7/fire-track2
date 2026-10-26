# Live project status

Updated: 2026-10-26 19:17 UTC. Priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.
User reaffirms workstation scope: tank → valves → pipes → four nozzles.
Rouaix/aerial experiments remain owned by the HPC thread; local outputs are
tank pressure/inventory and per-nozzle discharge/velocity histories.

HPC/Rouaix status is maintained separately in [HPC_STATUS.md](HPC_STATUS.md).
At 19:03 UTC, the 64-rank S1 and 24-rank P0 baseline have completed their
declared short horizons; five CFD jobs remain pending. Historical finished
attempts were reviewed and five dependent terminal auditors submitted; their
one-CPU native smoke test is pending. No new scientific gate passed.

## Current execution

The completed apparatus runs below are terminal and preserved. Exit 0 means the guard
saved normally, not that the requested horizon or numerical screen passed.

| Test | Saved physical time (s) | Outcome |
| --- | ---: | --- |
| Finite-water EOS, original timestep, linearUpwind | .410223 | One raw pressure-floor contact; minimum -308.269 Pa |
| Finite-water EOS, smaller adaptive timestep | .383069 | One raw contact at .382719 s; minimum +677.757 Pa, below the 10 kPa floor |
| Constant-density cold control, avoiding the .413 s restart | .434532 | Eighteen raw pressure-floor contacts |
| Warm upwind, original .400020 s seed | .460048 | Completed this short target without floor contacts |
| Warm upwind continuation, eight outer iterations | .481894 | Persistent pressure updates, final 300.719 Pa; no floor contact |
| Same .460048 s seed, sixteen outer iterations | .481996 | Persistent pressure updates, final 319.638 Pa; no floor contact |
| Same .460048 s seed, nontransonic pressure linearization | .482098 | Persistent pressure-update stop; no floor contact |
| Matched linearUpwind warm restart at .400020 s | .410228 | Raw contact at .410003 s, minimum -14.5735 kPa |
| Tight temperature solve, same .460048 s seed | .481894 | Pressure cycle persists despite much tighter linear temperature residuals |
| 25 microsecond maximum timestep, warm restart | .460523 | Twenty raw floor contacts; first at .460473 s; minimum -81.114 kPa |
| Cached predictor Sp, same .460048 s seed | .494225 | Improved common-time mass residuals and pressure updates, then persistent-update stop; no floor contacts |
| Cached full predictor Sp+divU, same .460048 s seed | .494130 | Pressure-update stop at 1261.902 Pa / 5.520 m/s; no floor contacts; conservation improvement did not cure cycle |

The 100 Pa / three-step / final-to-penultimate ratio .9 screen is exploratory,
not a formal nonlinear-convergence or validation tolerance. Liquid support in
floor-contact cells is not removed water mass. The smaller-timestep event
contains .027324 kg support in two nearly pure-water cells at x=3.234 m,
z=.869 m; its saved field minimum recovered to 92.944 kPa. More iterations and
the alternative pressure linearization did not remove the later upwind
plateau. Their targets of .50 s were not reached.

The matched restart uses the same original fourteen checkpoint fields and
`uniform/time`, audit default/on and ambient-output policy as the upwind fork;
only momentum advection changes. It supports numerical transport sensitivity
more cleanly than comparison to the uninterrupted parent history. Restart also
reconstructs `dgdt` in `createFields.H`; matching saved fields is not proof of
bitwise continuation.

Runtime authorities for the latest tests:

- Sixteen-outer: `results/runs/i4f-upwind-warm-nouter16-diagnostic-20261026T161110Z/guardian-status.json`,
  Docker `946f81c95efb`, StartedAt 2026-10-26T16:16:39.15037673Z.
- Nontransonic: `results/runs/i4f-upwind-warm-nontransonic-diagnostic-20261026T162726Z/guardian-status.json`,
  Docker `7ff7ede117df`, StartedAt 2026-10-26T16:34:22.424288519Z.
- Matched restart: `results/runs/i4f-linearupwind-warm-control-20261026T162846Z/guardian-status.json`,
  Docker `7e3c90ce369a`, StartedAt 2026-10-26T16:32:34.134837295Z.
- Smaller timestep: `results/runs/i4f-finite-water-eos-halfdt-conditional-20261026T122804Z/stock-campaign-status.json`.

Next work is bounded and parallel; no failed fields are restart inputs:

- **Full predictor-source consistency (fresh launch worker):** the pressure observer
  passed a byte-identical ten-step compatibility check and then recorded an
  actual alternating pressure cycle. At one recurrent cell, the measured
  post-EOS liquid residual agrees within 0.31% with the extra term arising
  from changed predictor/corrector source coefficients. This is a selected
  local observation, not a global conservation proof. Caching Sp alone
  improved the matched warm trajectory but did not cure it. A new default-off
  prototype also passed the ten-step bytewise comparison; root reviewed its
  full coefficient C=Sp+divU implementation. The .460048→.50 s exploratory
  replay is terminal: Docker `d85f657cf1ae`, StartedAt 18:39:59.00363731 UTC,
  ten MPI ranks/eight CPU equivalents, two-hour hard/100-minute save limit.
  Docker FinishedAt 19:05:33.123553991 UTC, normal End/native checkpoint
  .494130458572 s/316 steps. Root verified terminal identity and guard capture:
  zero raw floor contacts, final outer dp 1261.902 Pa, dU 5.520 m/s and five
  persistent-update steps. It failed in the same window as Sp-only .494225 s;
  this source correction is not the pressure-cycle remedy. First-step
  full alpha-equation volume-L1 residual was about 3.24e-6 m3/s, versus a
  3.4e-4–5.0e-4 m3/s counterfactual omitted-divU term; the former also includes
  predictor solve error and is not a physical phase-mass closure. It requires
  static Euler, one alpha correction/subcycle, no previous correction reuse,
  a globally positive correction denominator, and logs the discrete alpha
  equation residual using the actual corrected flux. Evidence lives under
  `results/runs/i4f-full-predictor-source-20261026T180031Z/`.
  A matched near-.477208 s sample has water-continuity L1 .01288 versus
  .38335 kg/s for Sp-only (times .226 microseconds apart); this is one point.
  A .460048→.70 s candidate is now running with only alpha-predictor
  tolerance tightened to 1e-12, using a passive RP/RF-RP diagnostic binary.
  Its declared common comparison window is .46–.50 s; longer horizon avoids
  another intermediate restart if healthy. Docker `c5ccf7a1e92a`, StartedAt
  19:12:34.729904344 UTC; ten MPI/eight CPU equivalents, four-hour hard and
  3 h 40 min save bound. Exact guard unit:
  `i4f-full-predictor-source-alpha-tol-1e-12-20261026t1903z-guard.service`.
  It uses the original healthy .460048 s seed, not failed .494 fields. At
  .464021 s, corrected-minus-predictor alpha residual max is 2.25e-12 s^-1
  while predictor residual max is .00119 s^-1; this directly separates the
  remaining predictor-solve residual from correction inconsistency at this
  instant. Stability through the old failure window remains untested.
  [Terminal full-vs-Sp comparison](../results/summaries/i4f_20261025/full-source-apparatus/terminal-comparison.json).
- **Continuous cold trajectory (performance worker):** running a true t=0
  finite-water-EOS/upwind/cached-Sp trial to .50 s, ten MPI ranks and ten CPU
  equivalents. Docker `0f8517608ad4`, StartedAt 18:26:13.097379609 UTC,
  verified running by root at 18:26:49 UTC; exact identity and GO are recorded
  in `results/runs/i4f-cold-finite-water-eos-upwind-frozenSp-target050-20261026T181955Z/`.
  Target .50 s; graceful save after 3 h 40, hard limit 4 h from container start.
  At .199521 s/809 steps (19:04 UTC), no raw contacts were recorded; this
  early startup does not exercise the previous failure interval. It preserves
  the nine prescribed initial fields; the solver
  creates the derived fields. This avoids interpreting warm-start sensitivity
  as timestep convergence. The 25 microsecond warm trial failed almost
  immediately and must not be resumed.
  An actual conditional dispatcher is active under unit
  `i4f-cold-upwind-frozen-sp-campaign-20261026t1837z.service`; root verified its
  live PID and code. Its intent/status/events are inside the cold bundle.
  It permits a .50→.75 s warm follow-up only after healthy terminal capture,
  with fresh resources, PAUSE checks and the original 22:06/22:26 UTC
  save/hard deadlines. No child has been launched; restart reconstructs dgdt.
- **Pressure-equilibrium verification completed:** the periodic 6,400-cell
  translating water/air slab reached .1 s/1000 steps, including an actual
  rerun using the public durable launcher. Maximum terminal p/U/T errors were
  7.20e-9 Pa / 4.27e-12 m/s / 2.01e-11 K, with no floor contacts. This checks
  uniform equilibrium preservation without the tank's active compression
  sources; it does not validate the tank. Public evidence:
  `results/summaries/i4f_20261025/pressure-equilibrium/public-reproduction-smoke.json`.
  The updated public launcher additionally snapshots nineteen launcher,
  reader, source-manifest and dependency files before GO. Root verified
  snapshot hashes and rejection of a tampered copy; Ruff/shell checks pass.
  This provenance addition postdates the executed public smoke and does not
  change its equations or retroactively change its recorded controller hash.
- **Source-active small verification completed:** all eight paired
  Sp-only/full-source gas-withdrawal cases (60/120/240/480 cells) reached
  .4 s/1600 steps without floor contact. With full source, three-finest-grid
  pressure-reference errors decrease 1.930→1.288→.878%, temperature errors
  1.914→1.272→.861%; normalized water-volume balance is at most 5.32e-11.
  Gas-mass drift is slightly worse with the full source, and thermal errors
  remain. These rhoConst/laminar/Pr1e9 cases do not validate the apparatus.
  A ninth n=120 diagnostic run reproduces native endpoint hashes exactly;
  corrected-minus-predictor alpha residual is below 9.21e-13 s^-1. Root
  inspected the figure, verified 34 artifact hashes and recalculated the
  eight-row SI/normalization table. Public data:
  `results/summaries/i4f_20261025/source-active-withdrawal/`.
- **Restart fidelity (performance worker):** source inspection identifies the
  pressure-derived dgdt as a candidate missing checkpoint state; rhoPhi and
  alpha flux are regenerated before first use under current controls. A
  separate minimal READ_IF_PRESENT/AUTO_WRITE probe is approved for build
  and a small uninterrupted/legacy-restart/saved-dgdt comparison. No result
  or sufficient-state claim exists yet. Current live cases remain unchanged.
- **Rendering:** the earlier paired watcher has no healthy >=.65 s apparatus
  trajectory to render. No new milestone discharge movie exists. Its status
  is `results/runs/i4f-cold-pair-render-20261026T1553Z-attempt5/watch-status.json`.

Twenty effective CPUs are available, shared with unrelated workloads. New
jobs use fresh measured admission; no GPU or HPC job is launched here. The
runtime save floor is 20 GiB. Two verified duplicate-only cleanups recovered
about 4.29 GiB of measured duplicate payload from never-launched preparations;
scripts, small inputs, errors and every executed run remain. Latest resource
check reported about 24 GiB free after lossless compression of twelve closed
Oct24–25 solver logs (3.296 GB raw to .478 GB allocated gzip; 2.625 GiB net
allocated space released). All streams passed decompression hash/size checks;
root verified compressed hashes and the recovery manifest is indexed. The cold
run uses ten CPU equivalents and the tighter-predictor trial eight. Twenty
effective CPUs are shared with unrelated
work. Current fields, inputs and active logs were not removed.
[Archive and restore index](../results/archives/index.json).

The earlier audit-output-only pair produced identical fourteen-field/time
endpoints and health rows, with solver ClockTime 51/42 s in one seven-step
sequential sample; this is not a universal speedup. Future helpers disable the
detailed audit stream while preserving health diagnostics. The new matched
warm advection control retains the original pilot's audit/on policy.

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
