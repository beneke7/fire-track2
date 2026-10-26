# Live project status

Updated: 2026-10-26 21:10 UTC. Priority: **I4F internal pressure-driven discharge**.
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

Current work is bounded and parallel; no failed fields are restart inputs:

- **Cold startup saved by disk guard:** Docker `8b086b299aee`, StartedAt
  2026-10-26T20:24:41.025680559Z, ten MPI ranks/ten CPU equivalents,
  had an uninterrupted target of 1.0 s. It saved normally at .090771166664 s
  when free disk crossed the unchanged 20 GiB floor; FinishedAt
  20:35:24.426198078Z. This was a storage stop, not a numerical failure.
  Its 375 steps had zero raw floor contacts/clipping, final pressure minimum
  99.516 kPa, T minimum 290.217 K and final outer dp .003365 Pa.
  Water defect was +2.917e-5 kg on 3198 kg; gas defect -6.849e-7 kg.
  Finite-water EOS, SST, upwind momentum, full cached predictor source,
  alpha tolerance 1e-12 and corrected first-step history initialization were
  retained. The intended control change from the failed cold startup was
  `momentumPredictor no`; pressure correction still updates velocity and
  kinetic energy. It has not tested the previous .48–.49 s coupling window.
  A recorded continuation is now live: Docker `f960b72b8049`, StartedAt
  20:50:36.466720222 UTC, ten MPI/ten CPU equivalents, target 1.0 s.
  All fifteen checkpoint fields plus time were copied and hash-checked. Root
  verified Docker and advancing guard at .098271 s/29 new steps with no raw
  floor contact or parser error. The original campaign deadline is retained
  (about 04:24 UTC, 27 October); this operational split is not claimed
  bitwise-equivalent to uninterrupted apparatus integration. No n-1 time
  directory requirement is inferred for Euler. Continuation authority:
  `results/runs/i4f-cold-momentum-predictor-off-continuation-20261026T2048Z/guardian-status.json`.
  Authority: `results/runs/i4f-cold-momentum-predictor-off-20261026T2022Z/guardian-status.json`.
- **First-step energy audit (performance worker):** three one-step arms
  reached 12 microseconds. The read-only predictor-off observer reproduces
  the baseline's fifteen native fields and time byte-for-byte. With the
  predictor enabled, the two selected pure-air cells reach about 713 m/s
  before temperature is solved, with K about 254178 m2/s2 and preserved Kold=0.
  The measured kinetic-energy source alone corresponds to -354.03 K; the
  solved temperature falls by 281.11 K to about 12.04 K. The remaining
  +72.92 K requires the implicit equation budget; it is not closed yet.
  Predictor-off leaves those cells at 293.15 K at this stage. The enabled
  trial has a raw 9.712 kPa pressure-floor contact (282 cells, no liquid
  clipping); its later sampled pressure-field minimum is 21.834 kPa, a
  different stage. Thus the unprojected predictor state is now measured,
  not inferred from a pressure-corrected velocity. An enriched read-only
  budget replay is assigned, with compact publication of the existing data.
  Evidence: `results/runs/i4f-cold-firststep-energy-audit-20261026T2032Z/analysis/`.
- **Source relaxation did not cure the late cycle:** weight .5, applied
  once after both pressure correctors, stopped at .494129725325 s with
  final dp 1253.704 Pa and dU 5.512 m/s. Docker `d353e078c78c` finished
  21:01:34.746304627 UTC with normal End/complete native checkpoint after
  the unchanged persistent-update screen, zero raw floor contacts/clipping.
  At .493750 s the raw source fixed-point error stopped contracting and
  grew from 3.62 to 3.98 s-1 over the later outer iterations. Smaller applied
  updates therefore did not provide convergence. The default-weight four-step
  identity test reproduced all twelve common laminar fields byte-for-byte.
  Its cumulative water defect .134243 kg includes .133296 kg inherited
  from the warm seed; compare only the new increment against other trials.
  Native localization places the terminal maximum-update cell at global
  31926 (rank 7 local 1779), a mixed cell owning a divider wall face, about
  14.9 mm beyond its leading edge. This is a location, not proof of a mesh bug.
  The conditional sixteen-outer run was withheld because this parent failed.
  No failed .494 s fields are used for continuation.
- **Matched warm predictor-off trial is live:** same healthy .460048 s
  seed, full-source method, eight outer/two pressure corrections and source
  weight 1; momentum predictor disabled. Docker `4b8ad3431709`, StartedAt
  21:06:10.557383444 UTC, ten MPI/eight CPU equivalents, target .505 s.
  Root verified exact Docker state and advancing guard at .464785 s/41
  completed steps, zero floor contacts. It tests whether predictor ordering
  matters in the late failure window, separately from cold startup.
  Authority: `results/runs/i4f-gamma-outer-relaxation-20261026T2027Z/gamma-mpno-omega1-on/guardian-status.json`.
- **Restart finding:** saving the expansion source alone did not reproduce
  uninterrupted evolution. Correctly initializing Euler field history before
  derived-field mutation did: a source-active channel split/restart matches
  the uninterrupted next step to 7.92e-9 Pa and 5.55e-13 m/s. This is a
  controlled one-step proof, not a general restart or apparatus validation.
  The corresponding warm apparatus replay still stopped at .494129 s,
  dp 1257.83 Pa and dU 5.506 m/s, without floor contact. Correct restart
  history therefore did not cure the later pressure cycle. Its guard's wrong
  log path was repaired on the same running container, preserving the original
  deadline and checkpoint; no solver relaunch occurred.
  The [public restart packet](../results/summaries/i4f_20261025/restart-history/README.md)
  contains both solver sources, inputs, split/end fields and comparison data.
  Root verified 335 artifacts and independently checked A/C/D staging; the
  new public rebuild recipe has not yet been exercised.
- **Other newly terminal trials:** tightened alpha solve stopped at
  .494128 s; the earlier uninterrupted Sp-only cold run stopped at .484302 s.
  Its conditional continuation correctly refused the failed parent and
  launched no child. Neither is live or awaiting automatic continuation.
- **Small verification:** the 6,400-cell periodic equilibrium case reached
  .1 s with terminal p/U/T errors 7.20e-9 Pa / 4.27e-12 m/s / 2.01e-11 K.
  Eight source-active gas-withdrawal cases reached .4 s on 60–480 cells.
  Full-source pressure error decreases to .878% on the finest grid;
  normalized water balance is at most 5.32e-11, but gas drift and thermal
  bias remain. These narrow checks do not validate the apparatus.
  Public evidence is under `results/summaries/i4f_20261025/`.
- **Rendering:** a new CPU cutaway of the failed .494 s endpoint was inspected.
  Water remains inside the branches at the dense-liquid threshold; it is not
  a complete discharge movie. Marked cells belong to an earlier pressure-cycle
  replay, not the current maximum-update cell. Context and exact source-closure
  evidence are in `full-source-apparatus/context-20261026T193827Z/` and
  `full-source-apparatus/source-closure-20261026T2010Z/` under the summary root.

Twenty effective CPUs are shared with unrelated workloads. At 21:10 UTC the
eight-CPU warm predictor-off trial and ten-CPU cold-derived continuation
are live. Their total declared quota is eighteen of twenty,
with about 1.13 CPU equivalents of unrelated work measured at admission.
Small diagnostics share admitted remaining capacity. No GPU or HPC
job is launched here. The runtime save floor remains 20 GiB. Verified
lossless archives preserve the old terminal logs, and duplicate-only cleanup
preserved every executed run's unique fields and source. A further three
closed logs were archived with about 1.32 GiB net allocated space recovered.
A further exact static-mesh duplicate cleanup removed 2,228 redundant paths
while retaining 401 canonical files; root checked every canonical SHA/size
and the global canonical/deletion-set separation. Measured free-space gain
was 9.36 GB during concurrent filesystem activity, with about 32 GB free
afterward. Two files were restored for smoke checks; 21 candidates with
permission failures remained untouched. Unique fields and source were not
removed. The [public recovery map and helper](../results/archives/manifests/i4f-polymesh-dedup-20261026T2038Z/README.md)
include atomic overwrite refusal and symlink checks, exercised with synthetic
restore/race tests. Root verified all thirteen public artifact hashes.
See the [archive and restore index](../results/archives/index.json).

After merging the shared HPC audit update 6d12db6, thirteen focused
terminal-audit tests passed (3.06 s), with Ruff passing for its module/tests. This is software verification,
not CFD acceptance. The earlier seven-step audit-output timing comparison
(51/42 seconds) does not establish a universal performance gain.

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
