# Live project status

Updated: 2026-10-27 01:49 UTC. Workstation priority: **I4F internal tank-to-nozzle discharge**.
Aerial/Rouaix/HPC execution belongs to the separate server agent; see
[HPC_STATUS.md](HPC_STATUS.md). Do not resume historical aerial queues here.

No complete trustworthy current discharge, accepted geometry-performance
comparison, hardware validation or new scientific gate pass exists yet.
The target remains a credible complete provisional trajectory and a supported
engineering comparison of the 1.0 m and 0.8 m outlet trains.

## Actual execution

- Luna is running the matched same-time water-fraction/actual-water-flux
  relaxation diagnostic: weights 1 and .5, ten MPI ranks per arm, same source,
  mesh and immutable .460047515286 s seed. The physical replay reaches the
  .493844 s trigger; diagnostic sweeps then hold physical time fixed.
  Weight 1 Docker `14025bd519fc126d99e321ce514a6b1a09b3f156cc20f07b3792a33c7847be09`
  started 01:32:43 UTC; its quota was raised 6→10 CPU equivalents after the
  physical trial finished, with protected input hashes unchanged.
  Weight .5 Docker `7a8264ea3a636513fe96e231f34eaf1e36c3e5090e8dafe1a297e32e2b6ef022`
  started 01:46:44 UTC with nine CPU equivalents. Both have independent durable
  exact-ID guards. The previous sequential dispatcher was stopped before the
  parallel release, preventing a duplicate launch.
  Runtime bundle: `results/runs/i4f-alpha-flux-relax-map-20261027T010936Z/`.
- A third Luna prepares one baseline-geometry interface-corridor mesh sensitivity
  from the localized front/disturbance. Actual meshing waits until the weight-1
  container is terminal and capacity is measured again. No third physical CFD
  calculation is authorized by that assignment; no geometry or thresholds change.
- The 5 kPa physical sensitivity is **terminal**, saved at .537437801153 s.
  Docker `71d34a2df7df1ade47e18ed17d431464a1b59c27f0364c46fcf5c7715ef4f793`
  ran 01:15:56–01:43:59 UTC, exit 0/normal End after a requested checkpoint,
  not successful completion of its .65 s target. Exact audit:
  `results/runs/i4f-pressure-floor5k-20261027T005941Z/analysis/terminal-capture.json`.
  The owner is extracting existing 8/16-outer bulk-observable comparisons;
  there is no automatic repeat of the censored case.

Twenty effective CPUs are shared with unrelated work; inspect actual processes,
not agent activity, before allocating more. Current work is CPU-only. Disk has
about 21–22 GiB free; the hard 20 GiB floor remains. Guards, Docker state and
native checkpoints are runtime authorities, not stale launcher labels.

## Findings that determine the next action

1. **Water transport restores the large feedback.** At fixed .493844 s, holding
   water transport while updating mechanics reduces max pressure updates
   16.47→1.92→about .42–.48 Pa. Restoring water transport gives 827→1064 Pa
   over eight sweeps with shared temperature, transported turbulence and old-time
   history held. This identifies a sufficient feedback path at one state,
   not its exact cause, a global stability result or a physical continuation.
   [Raw tables, source deltas and limitations](../results/summaries/i4f_20261025/water-pressure-feedback/README.md).
   Each direct source delta was applied to a clean published parent; all 72
   declared source files per arm matched. Fresh binary rebuilds were not done.
2. **More outer iterations alone did not cure it.** Matched 8/16-outer physical
   trials reached the stock 10 kPa floor near .528 s, with final updates around
   1347/1351 Pa. The successful 16-outer retry's terminal authority is
   `results/runs/i4f-cold-nouter16-advisory-20261026T2320Z/attempts/attempt-006-executable-mode-retry/guardian-status.json`.
   Earlier top-level failed-launch records are preserved and are not its result.
3. **The floor does not cause the earlier coupling mismatch.** Lowering only
   pMin 10→5 kPa allowed passage beyond the previous .528 s censor, but the
   coupled updates remained large. First new raw contact was .537268 s,
   about 4999.99 Pa; 21 pressure-pass contacts occurred. Last fully completed
   step had pressure updates 1293.74/1293.75 Pa and velocity update 10.74 m/s.
   Water-supported saturation margin remained about 2.65 kPa in the declared
   temperature envelope; no cavitation or physical acceptance is established.
   The complete endpoint contains 15 fields plus uniform/time, while terminal
   partial-step records have explicitly reported sequence gaps. Affected-cell
   liquid support is not removed mass.
4. **There are distinct locations.** The late largest-update cell is in mixed
   water/air beside an apparatus wall, outside the valve source; adjacent cells
   have about 9× its volume. This is roughly 2× linear size, not proof of a bad
   mesh. The saved minimum-pressure cell instead touches a divider and wall.
   The [localization](../results/summaries/i4f_20261025/water-pressure-feedback/localization/localization.json)
   distinguishes these from earlier failure cells. Selected final-outer records
   across physical steps do not establish an alternating within-step cycle.
5. **Linear residuals require careful interpretation.** The periodic contact
   preserves p/U/T near roundoff despite unattained normalized GAMG tolerances.
   Direct assembled pressure defects are tiny; the raw residual observer has a
   coupled-boundary accounting artefact in that test. This does not invalidate
   the apparatus's real between-iteration field changes.
   [Audit and independent source review](../results/summaries/i4f_20261025/pressure-normalization-audit/residual-source-and-review.json).

## Prepared comparison and physical limits

The 0.8 m candidate has 317,814 cells, generic/configured mesh checks passing,
max skewness 3.9133, and a separate all-geometry concavity qualification.
Cold fields and ten-way decomposition were checked; no candidate flow solver
has run. Legacy runtime controls must be bound to the selected source before GO.
Native initial inventory differences from the baseline are negligible, not an
operational blocker; mesh and exterior-domain accuracy remain unmatched.
[Input packet and inspected CAD/mesh views](../results/summaries/i4f_20261025/short08-cold-start-input/README.md).
CAD views show provisional 4 mm divider solids; CFD currently uses zero-thickness
paired baffles, a declared geometric difference.

Current hardware interpretation: two .9 m diameter tanks, 1.35 m³ water per tank,
20–25% additional headspace, two .3 m valve branches per tank and four horizontal
outlets. Downstream passages initially contain air; upstream feeds are wetted.
Use 12 bar absolute provisionally, 13 bar as a separate convention sensitivity.
The reported five seconds is discharge duration, not measured valve-opening time.
Gas composition, valve motion and several geometry details remain unmeasured.
The air-headspace/water model does not validate CO₂ loading, dissolved gas or foam.
A distributed valve loss and 2% minimum-opening regularization do not resolve
butterfly-disk geometry, actual leakage or its wake. Frozen per-run inputs govern;
never silently substitute current assumptions into historical experiments.

The [sealed gas pressure-volume reference](../results/summaries/i4f_20261025/sealed-gas-pressure-budget/pressure-budget.json)
explains the cost of filling dry lines but is not an emptying-time prediction.
The [early hydraulic comparison](../results/summaries/i4f_20261025/current-cold-hydraulics/matched-time-comparison.csv)
is internal consistency with shared assumptions, not experimental validation.
Restart-history, local startup energy closure and exact-parent rebuild evidence
remain linked in the [results index](../results/summaries/i4f_20261025/README.md).

## Next decision and publication requirements

- Evaluate the paired maps using unrelaxed candidate changes, signed pressure
  alignment and the actual phase/source/flux residuals. Smaller blended updates
  alone prove neither convergence nor conservation. Both alpha and its actual
  transport flux must be treated consistently.
- If supported, test that remedy in a bounded physical window with phase ledgers;
  retain the original equations/physical inputs and preserve failed attempts.
- Establish the complete startup/outlet trajectory, then extend the horizon as
  required by the discharge claim. Check selected timestep, mesh and exterior
  domain sensitivities and the effect of iteration error on engineering observables.
- Compare matched 1.0/0.8 m inputs using per-tank pressure/inventory and four nozzle
  mass-flow/velocity histories. Do not claim outlet uniformity from a scalar
  valve model, or a geometry benefit from preparation/appearance alone.

Completed evidence is pushed through `322387e`; later local changes, if any,
remain visible in Git. [Archive index](../results/archives/index.json) records
reversible mesh deduplication, probe-vector compression and lossless compression
of 1,100 old aerial intermediate fields. Initial, .5 s restart and 1 s endpoints
were preserved. Restore helpers and packet hashes were checked; archive payloads
remain local. Software checks and recovery success are not CFD acceptance.
