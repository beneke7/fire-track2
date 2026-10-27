# Live project status

Updated: 2026-10-27 04:45 UTC. Workstation priority: **I4F internal tank-to-nozzle discharge**.
Aerial/Rouaix/HPC execution belongs to the separate server agent; see
[HPC_STATUS.md](HPC_STATUS.md). Do not resume historical aerial queues here.

No complete trustworthy current discharge, accepted geometry-performance
comparison, hardware validation or new scientific gate pass exists yet.
The target remains a credible complete provisional trajectory and a supported
engineering comparison of the 1.0 m and 0.8 m outlet trains.

## Actual execution

Two matched physical-time half-weight water/flux pilots were launched on the
299,214-cell baseline, with ordinary temperature/turbulence evolution. The
eight-outer arm is now terminal; the sixteen-outer arm remains running. Each
uses ten MPI ranks/nine CPU equivalents, finite-water EOS, the same healthy
cold-derived .390705595007 s seed, pMin=10 kPa and target .65 s. Only outer
iteration count differs: eight versus sixteen. Existing .5/.6 s writes and
an independent .65 s terminal checkpoint are configured; two-hour budgets
and checkpoint grace are anchored to actual container starts.

- Eight-outer Docker `3b3d4b5c8159f8019d9860893b004b876d26714e544ed3ca8d1ced790f69e17e`,
  StartedAt 03:35:28 UTC; saved and ended normally at .518390228794 s.
  The diagnostic stop requested a save after water-supported intermediate raw
  pressure crossed 10 kPa (first contact 9,608 Pa at .518046 s). Last complete
  health record at .517875 s had final pressure update 5,082 Pa versus 4,860 Pa
  penultimate, final minimum 15,944 Pa and cumulative water defect -.014313 kg.
  This is renewed nonlinear nonconvergence, not a cavitation finding. Terminal
  partial diagnostic records have three explicitly recorded completeness gaps;
  native endpoint capture is complete. The smaller-step follow-up runs from the
  original healthy seed, never from this censored endpoint.
- Sixteen-outer Docker `de0cc3d2a13034485c2415a7bbf744355f37c583a381df5f5fddff90a18bc3f3`,
  StartedAt 03:37:59 UTC. At 04:45 UTC: t=.499687 s, no raw floor contacts.
  Last complete health record: pressure update 53.65 Pa, final minimum 29.61 kPa,
  cumulative water defect -.001902 kg. This earlier physical time cannot be
  compared directly with the eight-outer terminal state.
  Guard: `outer16/attempts/attempt-007-readiness-marker-retry/guardian-status.json`.
  Earlier no-GO attempts remain preserved. Its top-level readiness label can
  be stale; Docker state and advancing parsed physical time are authoritative.
- Pair root:
  `results/runs/i4f-physical-alpha-flux-relax-candidate-20261027T024711Z/arms/physical-omega-050-outer-pair/`.
  These are exploratory continuations, not uninterrupted cold starts, an
  adopted remedy, or a complete hardware discharge. Pressure warnings remain
  advisory; phase/bounds/nonfinite/raw-floor/material/resource guards remain.

The [physical candidate](../results/summaries/i4f_20261025/physical-alpha-flux-relaxation/README.md)
reproduced original/default-off/enabled-weight-one fields in one fixed 12 µs
step: 15 native fields plus uniform/time, 16 members total. Its actual enabled
half-weight branch also completed an eight-outer smoke with bounded alpha,
finite diagnostics and unchanged canonical inputs. Large local water residuals
remain relevant. All declared source files were reconstructed from the public
parent and hash-verified; no fresh executable rebuild from that packet is claimed.

The 1.0 m interface-corridor mesh is now cold-input ready at 323,682 cells,
with baseline 48-layer source resolution and corrected branch/mouth/exterior
zone definitions. No CFD has run on it. Runtime binding remains pending.
The separate 0.8 m candidate remains input-only as described below.

Twenty effective CPUs are shared with unrelated work. The sixteen-outer arm
and the smaller-step follow-up each have nine CPU equivalents. Follow-up
attempt 002 passed GO after a preserved no-GO missing-log-directory failure.
Exact Docker `27cf3bd28cfe9366869a74e149bdd3974a7eab448c34915f08b5e12d8e2601c8`
is advancing (.397206 s at 04:45 UTC). Raw logs verify dt=.000125 s from the
first physical increment; the previously questioned guard time was its second
step. Its only case-input change from outer16 is maxDeltaT .00025→.000125 s.
A common-physical-time scalar comparison and exact source-budget observer are
being prepared in parallel; neither is a completed result. Current work is CPU-only. New bounded jobs use a 16 GiB disk
stop reserve plus declared incremental output allowance at admission, replacing
an agent-selected 20 GiB reserve that blocked small tests despite substantial
free storage. Historical guards/records are unchanged. Lossless log recovery
and exact-mesh dedup have restored several GiB; account for concurrent writers.

## Findings that determine the next action

1. **A specific alternating mode is measured and damped.** At fixed .493844 s,
   restoring water transport produces max pressure changes 827→1064 Pa;
   successive increments have cosine −.999997 and volume-norm ratio about one.
   Joint half-weight alpha/actual-water-flux updates reduce the pressure change
   453→46→9.88→1.39→about .42 Pa, ending .576 Pa. Unrelaxed candidates shrink,
   but a small late mode drifts and water continuity L1 remains near .078 kg/s.
   This is mode damping, not full convergence. The [figure, raw tables and source](../results/summaries/i4f_20261025/alpha-flux-relaxation/README.md)
   preserve the fixed physical time and residual normalization. All 73 declared
   diagnostic source files and 71 physical-candidate source files were reconstructed.
   Independent read-only review supported the bounded physical eight/sixteen
   comparison with water-budget analysis in parallel; no scientific gate passed.
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

The same-geometry 1.0 m corridor case adds 8.18% cells while retaining the
original two upstream ROI refinements (48 layers/5,376 source cells per branch).
Its configured nine quality rows pass; optional allGeometry still reports
7,304 concave cells. Fixed-coordinate neighbor volume ratios drop about 9.27→1.24.
Cold tank/feed inventories match closely, domain bounds match, and ten-way
mapping/reconstruction passed with pressure serialization differences at most
2.33e−10 Pa. The corrected case/phase pictures were inspected by its worker.
It is a mesh sensitivity, not the 0.8 m alternative or a flow result.
Readiness record:
`results/runs/i4f-uniform-interface-corridor-20261027T015002Z/pre-baffle-attempt-010-corridor-roundtrip-retry-20261027T0356Z/analysis/corridor-cold-input-readiness.json`.

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

- Analyze the matched physical pilots at common times, including adaptive-step
  differences, unrelaxed candidates, phase ledgers, signed/local residuals and
  four-nozzle observables. Smaller pressure changes alone are insufficient.
- The offline native source-cutoff estimate has the same sign and about 81%/76%
  of the signed residual magnitude in the separate one-step reference/half-weight
  endpoints. Endpoint-versus-cached-source timing and approximate density prevent
  treating this as an identity. Do not change its cutoff to manufacture acceptance.
- Establish the complete startup/outlet trajectory, then extend the horizon as
  required by the discharge claim. Check selected timestep, mesh and exterior
  domain sensitivities and the effect of iteration error on engineering observables.
- Compare matched 1.0/0.8 m inputs using per-tank pressure/inventory and four nozzle
  mass-flow/velocity histories. Do not claim outlet uniformity from a scalar
  valve model, or a geometry benefit from preparation/appearance alone.

Completed evidence is committed in the shared repository; later local changes, if any,
remain visible in Git. [Archive index](../results/archives/index.json) records
reversible mesh deduplication, probe-vector compression and lossless compression
of 1,100 old aerial intermediate fields plus recent closed internal logs. A further
1,008 exact duplicate mesh paths have tested retained-canonical recovery maps.
Initial, .5 s restart and 1 s endpoints
were preserved. Restore helpers and packet hashes were checked; archive payloads
remain local. Software checks and recovery success are not CFD acceptance.
