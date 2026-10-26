# Live project status

Updated: 2026-10-26 13:00 UTC. Priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.

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
- **Finite-water smaller-timestep cold test: running.** The conditional pilot
  started only after that whole campaign exited, its controller became inactive
  and its exact terminal fields were captured. Docker `13324c8bdc84`, StartedAt
  2026-10-26T12:37:58.261453121Z, ten MPI / initial 8.7 CPU equivalents.
  Initial deltaT=5e-6 s, maxDeltaT=.000125 s, maxCo=.25 and maxAlphaCo=.125;
  the same EOS, mesh, partition, binary, source and turbulence are retained.
  This is adaptive time refinement, not a claim of exactly half every step.
  Targets are .05, .46 and 1.3 s if healthy; the existing pressure/mass/capture
  stop rules remain unchanged. Authority:
  `results/runs/i4f-finite-water-eos-halfdt-conditional-20261026T122804Z/stock-campaign-status.json`;
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
  shared CPU budget (18.7 allocated CPU equivalents, plus measured unrelated
  work ~1.18). No GPU solver/rendering job was launched. Closed historical
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
  `make check`: **750 passed, one optional Docker test skipped, four subtests
  passed**. Software checks do not validate the apparatus.

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
