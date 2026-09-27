# Independent blocker-plan audit — requested checkpoint 2026-09-25 08:41 UTC

Reviewer: Astra Max, `/root/astra_max_blocker_deblocker`.
Initial evidence snapshot: 2026-09-25 08:47 UTC, with a shared-status recheck at
08:53 UTC, including the completed 08:38:56–08:39:21 source-disabled candidate3
regression. The filename retains the requested checkpoint time. This is an advisory deblocking memo, not a
scientific review approval, accepted protocol, or solver launch authorization.
Only this memo was written; no build, GPU job, solver, or shared-file edit was
performed.

The next source-path release depends on measured runtime diagnostics and a
complete executable contract. Repeating candidate2 repair work or the unchanged
candidate3 smoke is no longer the critical path. The independent CPU E1 branch
needs review of its corrected packet, then qualified case/mesh and resource
evidence. E2 method preparation can proceed in parallel, but its clock/startup
choice must be resolved before the scenario matrix is frozen. No source gate,
E1–E6 comparison, ground-delivery validation, or built-device claim is passed
by this memo.

## Evidence and exact scope

The audit read `AGENTS.md`, the full experiment plan, `docs/VALIDATION.md`,
`docs/COMPUTE.md`, the current status and blocker plan, the source gate, and
the independent reviews below. Line references are to this audit's snapshot.

| Record | Version or location |
| --- | --- |
| Candidate3 independent review | [Review](../../containers/flutas/candidate3/INDEPENDENT_REVIEW.md), SHA-256 `62f867a611ac14b9146414e4478707532d405187c9f98ed438b385002f34d954`; disposition lines 8–15; remaining findings lines 124–224; permitted regression lines 233–267. |
| Candidate3 exact build | [Metadata](../../containers/flutas/candidate3/evidence/runs/20260925T082315Z-1955187/metadata.txt); patch `055758a2690fe4bb9003bdc54665cbc63f67e490f8bd1e307d71ca6d013a4319`; image `sha256:90f1261308ab56e52ee29d129deefad86a19b352cef79b43feca08df6762e1c3`. |
| Completed candidate3 regression | [Bundle metadata](../../results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/metadata.txt), [resource limitation](../../results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/resource-use.txt), and [manifest](../../results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/SHA256SUMS). Manifest SHA-256 `0d6245b2d6df91d144c6959a024aa2e28ae5653953d41a5e6e3d73c3cb7fcf97`. |
| Latest Warden | [08:38 memo](PROJECT_WARDEN_20260925T0838Z.md), SHA-256 `8aa3a822839bc403f3737bdb8bc7984b5c004b572087937058140e6ee2ec1c7e`. Its regression assignment predates the completed run. |
| Prior E1 review and corrected packet | [Initial review](E1_GATE_REVIEW_20260925T0806Z.md) reviewed old draft `ac1c505b50ed987a3a36a88a408bdf1e8c4b52c4bfa9a1f9bafad7ab977a0c4c`. Current [E1 draft](../../experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md) is `3e5fb0644dde4c6f325bb1af0a65e759e424d99d91339f147314020842e0cd3d`; current [CPU audit](../../experiments/E1_CPU_SOLVER_CAPABILITY_AUDIT.md) is `083746f037544a162ac1f030f9480022059829574c171ccba343b7fbf61f4bfa`. The old review cannot approve the revised bytes. |
| Fresh E2 review | [Second review](E2_SOURCE_UNCERTAINTY_REVIEW_2_20260925T084013Z.md), SHA-256 `2090bb10024b7f8656841414e44bb50175cd1750386695dfc5cd3df0d6ecef92`, disposition **REVISE**. Reviewed [method](../../experiments/E2_SOURCE_UNCERTAINTY_METHOD_DRAFT.md) hash remains `1cc5ccb66438250674282cbe872a9cde95a9d32235d99b161a91d97dc748133f`. |

The regression is a **functional source-disabled hardware/upstream PASS with
incomplete runtime resource evidence**. It used the reviewed immutable image,
an explicit `/usr/local/bin/flutas-gpu-tests` entrypoint, a two-CPU container
cap, the shared GPU lock, and a 600-second outer timeout. Its archived runner
hash is `e90285710e1ce77724d85bcf331c2fe993fdd6367cf3ccec159f81c70c88757c`.
The preflight records absence of `source-boundary.in` in the actual upstream
bubble case. OpenACC reports 1,024 output values; both CUDA-buffer MPI ranks
report reduction result 3; bubble verification reports `True True`; final
recorded exit is zero. Independent read-only checking in this audit found:

- All 134 files in the run's SHA-256 manifest match, with no missing/mismatched
  entry; the copied bubble case still contains no source input.
- The bubble reference and computed tables each contain 168 rows. Maximum
  absolute differences in the checked z-centroid and z-velocity columns are
  both zero, checked directly rather than only trusting the upstream test's
  mean-difference comparison.
- `resource-use.txt` explicitly records **unknown runtime peak VRAM, host RAM,
  and container RAM**. The 16 MiB device reading is an initial snapshot, not a
  peak. Roughly 25 seconds of elapsed time is not a source-case performance
  profile. Later sampler changes do not retroactively fill this evidence gap.

This establishes execution of the source-disabled branch; it does not execute
`dry_four`, `dry_crossflow`, or any slot-source fixture. Preserve this bundle
and its limitation. Do not rerun unchanged smoke solely for utilization or
retroactively present a later runner as the one used here.

## Status corrections for the primary

These are synchronization tasks, not requests to weaken a gate. This worker
does not own the shared documents. Snapshot hashes are `4bf27a90dda9c940fa34b8a9991b974513fd164c2f3f5770565ae05fc1cb7180`
for STATUS, `35f28c039f51959afc89309ea58585cd695333ba4097ba7b77ad7c92f67fd947`
for the blocker plan, and `78fe587a6f2569a53f3288cbec98fc054c404eb65eca39111867965ceac8457f`
for the source gate.

| Stale location | Smallest accurate update |
| --- | --- |
| `docs/STATUS.md:3–18,279–292,303–317`; `docs/BLOCKER_RESOLUTION_PLAN.md:6–9,33,68` | Candidate3's exact review is complete; its three candidate2 repairs are accepted at code-review scope and its source-disabled GPU regression completed. Replace “awaits review/no candidate GPU run” and the pending unchanged regression assignment. Keep source CFD **not run**, source runtime gate **closed**, and unknown runtime peaks explicit. |
| `docs/STATUS.md:21–24,135–139` | The E1 author has supplied corrections, including phase-specific momentum. Say “corrected proposal awaiting independent disposition,” not that all original defects remain unaddressed. No reviewed acceptance or E1 execution follows from an author's correction. |
| `docs/STATUS.md:171–181`; blocker-plan B6 at line 73 | The second E2 review is complete and says **REVISE**. The continuous-history mathematical defect is closed at specification level; clock/startup, decision precedence, exact serialization, coverage/target/scoring and implementation remain open. |
| `docs/STATUS.md:279–299` | Replace historical worker states with actual handoffs/queues and link the 08:38 Warden. Preserve older memos. The 08:38 memo's instruction to perform the candidate3 regression has now been fulfilled functionally with the resource limitation above. |
| `docs/COMPUTE.md:138–146`; `experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md:3–9` and closing candidate2 discussion | Keep candidate2's defects as preserved history, identify the repaired/reviewed candidate3 and completed bounded regression, and name the telemetry/analyzer/protocol gate that now prevents source execution. |
| Candidate3 review M2, lines 216–231 | Correct scope labels in shared summaries or the next candidate's documents. Do not silently rewrite the hashed candidate3 build inputs to repair prose: host helper execution, source-string checks, native build, GPU regression and source CFD are distinct evidence. |

**Handoff synchronization:** while this memo was being drafted, the primary
updated the shared records. A re-read at 08:53 UTC confirms that STATUS, the
blocker plan's candidate/B1/B2/B6 entries, COMPUTE and the source-gate opening
now record completed candidate3 review/regression, the missing runtime peaks,
candidate4 preparation, corrected E1 pending review and E2's second-review
findings in their applicable locations. The stale-location table above is the
preserved initial finding, not an assertion that the updated copies still
contain those claims. The read-back hashes were STATUS
`348745c427529541fa0affe3ba108c9e2cf033f2ce9d575e77a05ab177ab64ed`, blocker plan
`1ad2ef2cd7f323a060b7fe79a4a697c0be7f5cf803313b82722e3b8c88108701`, source gate
`41f6c5fb7cc1d1687686d68a9ea606052a6f9fb91e590b6bfa2934d84406b969`, and COMPUTE
`f7fa3400027bc2210c3dd6897c4aaca4fa76675fd714f41278f2932f88e04930`. These edits
were the primary's, not this auditor's; no scientific gate changed.

## Active blockers and smallest defensible releases

Severity is relative to the named gate: **blocking** means it prevents the
next execution or scientific claim; **high** means a necessary downstream
dependency; **medium** denotes a bounded evidence or workflow gap. “External”
distinguishes scientific evidence from routine authorization. Existing
provisional-input authorization is sufficient for the local preparation below.
All implementation/source authors are Luna Max; independent scientific/general
review is Astra Max; the primary integrates and schedules.

### B0 — state synchronization and incomplete regression resource provenance

- **Severity/evidence:** the initial high-priority shared-status corrections
  were integrated at handoff as recorded above; the remaining resource-record
  limitation is medium. Exact snapshot locations and immutable run evidence
  are listed above. Candidate3 is identifiable and reviewed;
  “implementation state not frozen” no longer accurately describes its saved
  patch/build. Runtime peaks nevertheless remain unavailable.
- **Smallest fix/owner:** primary synchronizes shared status and queues, retains
  the regression's explicit limitation, and verifies that the next relevant
  launcher records actual device/container samples and monitoring failures.
  Preserve the used launcher bytes and all historical candidates/attempts.
- **Dependency/check:** current review/run artifacts; check hashes, positive
  execution artifacts, exact source-disabled scope, and the resource sampler's
  behavior independently before relying on future measurements. A snapshot or
  configured memory cap must never stand in for measured peak use.
- **Gate unblocked:** accurate readiness reporting and future resource-evidence
  collection, not the source or pilot gate. **External required:** no.

### B1 — source runtime diagnostics and boundary behavior remain unqualified

- **Severity/evidence:** blocking for every source-path fixture, including dry.
  Candidate3 review B1/H1/M1, lines 126–182 and 197–214; source gate lines
  70–83,87–102,172–184. Fixed `dt` bypasses upstream `chkdt_tw`; its stability
  check is not an interface-Courant measurement. Theoretical initial Co values
  do not bound the evolved field. The existing host harness uses halo width
  two, omits actual optional rho/mu refresh and ledger behavior, and does not
  advance the solver.
- **Smallest fix/owner:** Luna source implementer prepares a new isolated
  candidate, preserving candidate3. With primary-owned diagnostic definitions,
  measure global and interface Courant values on the states actually consumed
  by transport; define empty-interface behavior and applicable advective,
  viscous, gravity and capillary restrictions. Preserve local maximum and L1
  divergence independently of net boundary-flux closure. Add production-width
  one tests, rho/mu refresh after generic fills, active/off-mask/reverse-flow
  behavior, nonzero audit-output oracles and unsupported-input rejection.
  Flush measured/expected flux and failing interval before assertion aborts.
- **Dependency/check:** independent exact-candidate review and executable
  behavior checks, then native build and the smallest separately eligible GPU
  regression. Review the `k` transport versus `k+1` projection/inventory states.
  Retain short-x/long-y geometry. Uniform pulse expectations remain 0.72 kg
  per slot and 2.88 kg total; quiescent per-slot impulse is
  `(0,0,-3.456) kg m/s`, crossflow `(-36,0,-3.456) kg m/s`.
- **Gate unblocked:** code/diagnostic prerequisites for B2/B3, not a source
  solver pass. **External required:** no; this is a synthetic implementation
  test with already authorized provisional dimensions.

### B2 — executable source schema, analyzer, and limits are not accepted

- **Severity/evidence:** blocking. Candidate3 review H1, lines 150–182;
  source gate lines 151–184; Warden lines 28–41. CSV existence and exit zero
  do not establish the mandatory checks. Numerical/resource limits remain
  unapproved, including copied CPU Co `0.5/0.25` and the 0.1% mass bound.
- **Smallest fix/owner:** primary freezes a versioned schema and contract;
  a separately scoped Luna analyzer author implements it. Source rows are
  interval `k`; inventory/boundary rows are completed state `k+1`; velocity
  rows describe the next endpoint profile. Handle repeated global off-mask
  columns without summing them per slot. Distinguish signed, step-integrated
  liquid volume from outward-positive instantaneous total-volume rate. Dry
  source files are header-only and require all other liquid-zero diagnostics.
  The reviewer accepts formulas, error budgets, empty/zero-source handling,
  all six faces, forcing/materials, resource ceilings and stops before launch.
- **Dependency/check:** stable B1 output contract, independent synthetic
  positive/negative fixtures and exact-hash review of analyzer, launcher and
  inputs. Expect 14 one-slot or 56 four-slot source rows for intervals 0–13,
  zero dry source rows, and 15 initial/completed rows 0–14 in other ledgers.
  Reject missing, duplicate, reordered, truncated, nonfinite and wrong-hash
  data, premature/failed solver exits, and missing resource records. Test
  local-divergence failures even when the telescoping integral closes; periodic
  pairing, source-off and off-mask failures; and all numerical limits. Mark
  FFT iteration count inapplicable where appropriate, retaining a meaningful
  solve-residual/continuity check instead of invented iteration telemetry.
- **Gate unblocked:** launch eligibility for the ordered B3 source diagnostics,
  only after independent acceptance of B1/B2. **External required:** no.

### B3 — ordered source diagnostics and GPU scaling evidence do not exist

- **Severity/evidence:** blocking for source qualification and larger GPU work.
  Source gate lines 85–138,186–192; `docs/VALIDATION.md:86–93`;
  `docs/COMPUTE.md:149–157`. A source-disabled rising bubble is not any of these
  source stages and cannot supply a 1–3 million-cell profile.
- **Smallest fix/owner:** after B1/B2 acceptance, primary alone schedules
  quiescent dry → dry crossflow/gravity → one slot → four slots → sourced
  crossflow/gravity, one GPU job at a time, stopping on the first failure.
  Independent reviewer audits each stage's actual per-step outputs. Only
  after source qualification prepare a separately reviewed pilot protocol.
- **Dependency/check:** immutable bundles with actual boundary/phase states,
  all-face and per-slot mass/momentum fluxes, inventory, local continuity,
  Courant/stability values, provenance, sampled resources and stop decisions.
  Later pilot must measure step time, pressure and I/O shares, physical-time
  throughput, checkpoint/restart cost and RAM/VRAM before projecting scale.
- **Gate unblocked:** source implementation qualification, then separately
  pilot/scaling readiness; no E1–E6 gate. **External required:** no for local
  bounded work; any future cluster allocation requires actual access, never
  the plan's nominal core count alone.

### B4 — E1 source semantics, momentum corrections and numerical decisions

- **Severity/evidence:** blocking for a controlled E1 comparison. Prior E1
  review findings 1–7 remain awaiting an exact revised-packet disposition.
  Current draft lines 140–159,163–251,437–503 provide concrete corrections
  and still explicitly say NOT READY. Figure 13's observation time and exact
  width operation are not recovered; Figure 16's marker is q-level context.
- **Smallest fix/owner:** Astra reviewer independently dispositions the stable
  corrected draft; Luna author resolves specific findings. Review the
  atmospheric static-pressure-to-`p_rgh` mapping and backflow choices, downward
  `Y` sign/full-span `Z`, exclusion of the calibration origin, fixed scored
  rows/ranges, whole-window source-read handling, assumed 4.5–5.0 s window and
  stationarity. Accept, replace or reject every proposed limit prospectively.
- **Momentum correction now present:** line 222 uses
  `-integral rho_q alpha_q U (U dot n_out) dA`, with water fraction
  `alpha.water`, air fraction `1-alpha.water`, each phase's density and each
  inlet's own reference. Water zero components are x/z; gas zero components
  are y/z. This corrects the Warden's identified water-only gas weight and
  shared zero-component set. It is a flux-rate check, not a proof of full
  control-volume momentum closure. Independent review must still check
  collocation/time sampling, signs/normals, rate versus impulse, nonzero
  references and the complete pass conjunction. The phrase “each inlet patch
  and phase” also needs an explicit rule for an absent phase whose reference
  norm is zero: either limit relative normalization to the intended nonzero
  phase and separately check contamination, or freeze an absolute zero-phase
  rule. Do not leave an implicit zero denominator in executable analysis.
- **Dependency/check:** E0 plus exact-hash independent review; arithmetic and
  synthetic sampler/score expectations tied to the accepted protocol. The
  proposed global/interface Co `5.7/1.0` caps are not approved by quoting
  STAR-CCM+ CFL; the reviewer must justify the pinned OpenFOAM definitions,
  operational stop behavior and resulting timestep pair. Curve agreement
  cannot rescue failed provenance, mass/momentum, coverage, stationarity or
  mesh/time checks. Preserve all 51 window samples and both source traces.
- **Gate unblocked:** a reviewed reconstructed E1 method, not E1 execution
  without B5, and not E2 advancement. **External required:** no to review an
  explicitly conditional reconstruction; author setup/postprocessing data
  are needed to remove the time/width/turbulence assumptions and claim exact
  recovery. Rejected semantics lead to descriptive/inconclusive status.

### B5 — the E1 case, sampler, mesh and resource contract are not prepared

- **Severity/evidence:** blocking for E1 execution. Current E1 draft lines
  35–41,93–108,145–159,339–435; CPU capability audit feature table. No Rouaix
  case, mesh, sampler or run exists. Available `interIsoFoam` is an approximate
  isoAdvector route, with a RANS/wall pairing different from the paper.
- **Smallest fix/owner:** Luna E1 preparer builds reviewable dictionaries,
  source-labelled curved-wall trace, circular-inlet/full-domain geometry,
  sampler and mesh evidence after the specified preparatory decision. Primary
  records the accepted deviations and assigns bounded compute. Keep mesh
  preparation, a separately preregistered characterization/profile, and full
  E1 execution as distinct releases; do not require measured runtime y+ or
  evolved-field Co before every possible characterization run, creating a
  circular dependency. The characterization must have its own reviewed limits.
- **Dependency/check:** B4's applicable input/geometry decisions, pinned image,
  actual patch area/normals, `checkMesh`, layer/refinement/y+ evidence appropriate
  to the stage, pressure reconstruction and sampler oracles. Then measure
  resource cost, source/box conservation, Co and numerical behavior on the
  actual E1 configuration before freezing an affordable full-domain run and
  refinement plan. P1 timing is not an E1 forecast. Final E1 execution needs
  accepted hashes, output retention, budgets, monitoring and stop conditions.
- **Gate unblocked:** controlled CPU E1 execution, followed by an independent
  result decision. **External required:** no for the reviewed provisional
  route; exact wall/setup equivalence would need stronger source data.

### B6a — E2 observation clock and ambient startup are unresolved

- **Severity/evidence:** blocking before freezing/generating the final matrix.
  Fresh E2 review H1, lines 34–62, and method lines 94–112. With `x=t+delta`
  and fixed absolute observation `t=0.5`, source ages are 0.47/0.50/0.53 s.
  Observing instead at exactly 0.5 s after each release means
  `t=0.5-delta`; these are different experiments. Variable starts can also
  mix ambient/body-flow startup with source-history sensitivity.
- **Smallest fix/owner:** Luna method author proposes one clock interpretation
  and gas-initialization convention, explicitly assumed if the paper cannot
  resolve it; primary integrates the proposal and Astra reviewer decides.
  Freeze `source_origin_time`, `run_start`, `diagnostic_absolute_time`,
  `source_age_at_diagnostic`, and `elapsed_solver_time`. Use a common earlier
  ambient initialization or the same reviewed developed ambient state, or
  explicitly bound another startup assumption. Keep alternatives in a separate
  method family rather than changing time semantics within a matrix.
- **Dependency/check:** review before matrix generation; independent full-run
  integral and endpoint checks. For the current fixed-absolute-time proposal,
  the primary `delta=+0.03,a=0` full integral is 1.881265 m; 1.87096 m is only
  `[0,0.5]`, excluding 0.010305 m before zero. Preserve both windows in tests
  and mass bookkeeping. These are history integrals, not measured payloads.
- **Gate unblocked:** coherent E2 scenario specification, not CFD.
  **External required:** no for an expressly assumed choice; exact figure-clock
  or physical timing uncertainty claims require source clarification/data.

### B6b — E2 generator, uncertainty/target scope and score remain incomplete

- **Severity/evidence:** blocking for E2 execution; medium for reproducibility
  conventions that can be closed now. Fresh E2 review M1–M3 and lines
  139–159. The continuous evaluator is mathematically repaired, but 18 cases
  are a finite assumed sensitivity family, not a proof of uncertainty coverage.
- **Smallest fix/owner:** after B6a, Luna author fixes primary decision-status
  precedence, binary64/decimal conversion, positivity-root rounding, coincident
  knot rules, comparison roundoff bound, case-ID/revision grammar and an
  acyclic proposed-manifest → review → execution-manifest dependency. Implement
  the deterministic evaluator/exporter and archive its executable tests and
  outputs. Label the unarchived inline checks author-reported until reproduced.
  Primary/reviewer then freeze scenario admissibility, target-coordinate and
  landmark/support treatment, score normalization/limits and the case's
  geometry, BC, turbulence and numerical assumptions.
- **Dependency/check:** independent evaluator/export agreement, exact segment
  integral oracles, serialization repeatability, full-domain/synthetic
  positivity-root cases (the 18 short histories do not exercise a crossing),
  hash-mutation rejection and combined missing/refinement/straddle decisions.
  Keep both source and target reads separate with shared-calibration provenance.
  Missing refinement is incomplete; completed failed refinement must have one
  deterministic primary status. Do not call 36 comparisons propagated target
  uncertainty. The inferred 1.332 m² area and uniform scalar velocity mapping
  remain assumptions; half/double areas remain non-gating sensitivities.
- **Gate unblocked:** executable, reviewed E2 method/case preparation. CFD still
  requires accepted E1 advancement, full E2 protocol and actual case profile.
  **External required:** no for deterministic finite-sensitivity preparation;
  exact Calbrix area, spatial velocity, full discharge and physical uncertainty
  coverage need stronger source evidence. A conditional family must retain
  its limited scientific scope.

### B7 — E3 four-port mapping and terminal source history are missing

- **Severity/evidence:** high downstream blocker; [E3 source record](../../experiments/E3_CALBRIX_CL415_SOURCE.md),
  especially lines 227–275, and blocker-plan B7. Two maximum-velocity curves
  do not define four patch histories, equal flow split or exact shutoff. Fig. 4
  labels conflict with prose; Fig. 11 uses an unpublished structure detector.
- **Smallest fix/owner:** Luna source preparer makes a source-labelled polygon,
  normal, area/group and supported-time-window packet; preserve both trace
  reads and explicit color convention. Reviewer accepts inferred mappings or
  limits the result to descriptive work. Keep Fig. 11 descriptive.
- **Dependency/check:** packet preparation now; E3 solver comparison only
  after accepted E2 and reviewed E3 input/target/limit/profile evidence. Check
  four distinct patches, source assignments and supported observation times;
  never extrapolate a tail into a claimed complete release.
- **Gate unblocked:** conditional E3 nearfield comparison readiness.
  **External required:** not for bounded paper/source preparation; actual
  outlet/CAD grouping and full flow/terminal history are needed for exact
  replay or a supported full-drop source if the paper cannot supply them.

### B8 — conservative A/B-to-C/D transport is not implemented/qualified

- **Severity/evidence:** high for ground predictions. Experiment-plan regions
  A–D and direct-VOF requirement; `docs/VALIDATION.md:32–50`; current
  `src/aerial_drop/` contains E0 and an isolated-drop component, not a qualified
  dense-plume transfer/descent pipeline. `docs/STATUS.md:266–272` names the gaps.
- **Smallest fix/owner:** primary freezes transfer/impact/ledger interfaces;
  Luna implementer builds synthetic conservative handoff and ground
  accumulation within those interfaces; independent reviewer derives the
  mass, momentum and absolute-time frame oracles. Prepare a direct-VOF descent
  attempt and loading assessment before selecting a handoff/coupling model.
- **Dependency/check:** interface/code preparation can overlap nearfield work;
  physical production use requires qualified A/B inputs, affordable direct-VOF
  evidence, overlap and handoff-location sensitivities in maps and `L95`.
  Preserve impact positions/times/weights and exclusive inventories; never
  add cumulative handoff flux to stored mass. Check high-loading two-way
  coupling rather than silently choosing one-way transport.
- **Gate unblocked:** conservative transport implementation, then ground-stage
  readiness with additional physics evidence. **External required:** no for
  analytical interfaces/tests; measured/calibrated unresolved-size or dense
  transport models may require independent evidence before physical claims.

### B9 — E4 M134 is limited to descriptive figure evidence

- **Severity/evidence:** high for field-validation claims. [E4 source record](../../experiments/E4_AMORIM_M134_SOURCE.md):95–129;
  `docs/VALIDATION.md:80,84`. The adjusted plotted origin is not an absolute
  track, the CSV is not raw cup data, and `Vx` is a cross-track volume sum.
- **Smallest fix/owner:** Luna preparer independently extracts/reviews Fig. 4
  contours and figure uncertainty; primary freezes source reconstruction,
  units, wind/aircraft frames, registration and distinct profile/contour metrics
  before overlays. User/external data custodian can supply raw trial evidence
  when available; do not contact third parties without authorization.
- **Dependency/check:** prep now; controlled ground transport later requires
  preceding stages/B8, matching inputs and independently accepted uncertainty
  and limits. Do not integrate plotted `Vx dx` into collected mass. Retain
  source registration and all raw measurements if obtained.
- **Gate unblocked:** descriptive comparison now; a field-validation gate only
  with required measurement evidence. **External required:** yes for the
  current validation contract's field-validation pass: cup-level measurements,
  uncertainties and matching discharge/track/wind metadata. Their absence
  does not block the independent figure-preparation task.

### B10 — E5 six conditions and collection convention lack a dedicated packet

- **Severity/evidence:** high downstream blocker; `docs/REFERENCES.md:13`,
  `docs/VALIDATION.md:81,84`, blocker-plan B10 and lines 289–296. There is no
  `experiments/E5_GU_AG600_SOURCE.md` at this snapshot. Gu Tables 4/5 are on
  local PDF pages 8/9; source fractions are not local validation outputs.
- **Smallest fix/owner:** Luna preparer transcribes all six condition/result
  rows, release denominator, collection region/method and uncertainties with
  page/table locators; separate measured and reconstructed estimates. Astra
  independently checks the transcription and whether a comparison is
  defensible; primary freezes the usable scope.
- **Dependency/check:** paper packet now; controlled E5 after preceding gates
  and matched reconstruction. Independently verify all six groups and justify
  the paper's 10% relative-bias criterion for this specific use before adopting
  it. Scalar collected fractions must not be relabelled `f_useful`.
- **Gate unblocked:** source/collection-convention readiness, later E5 within
  its supported scope. **External required:** no for transcription; raw cups
  and release/collection/flight metadata are required for an independent map
  reconstruction or matching inputs not recoverable from the paper.

### B11 — E6, built-system evidence and final scientific animation

- **Severity/evidence:** high downstream claim blocker. Experiment-plan
  comparison and deliverables; `docs/VALIDATION.md:9–30,82,95–97`;
  `docs/STATUS.md:234–275`. No validated ground maps, matched gain or measured
  built-system source packet exists. The P0 animation is a short provisional
  diagnostic, not the full requested scientific experiment.
- **Smallest fix/owner:** primary freezes matched payload, flight/environment,
  target and numerical conditions; Luna integrates common physics/scoring and
  an unadjusted pair only after prerequisites. Reviewer audits ledger, maps,
  continuous-strip metrics and uncertainty. The final animation consumes
  computed time-stamped fields with fixed scales/cameras and explicit content
  labels, after its corresponding scientific evidence exists.
- **Dependency/check:** E0–E5 plus B8, source/physics and map/threshold/width
  sensitivities, raw impact preservation, partial-cell area weighting,
  deterministic ties and undefined gain when control `L95=0`. Keep collected
  mass, actual strip mass and capped useful dose distinct. Separate operational
  comparisons from matched counterfactuals.
- **Gate unblocked:** conditional E6 prediction and its scientific visual;
  built-system validation requires additional independent evidence.
  **External required:** no for authorized idealized preparation; yes for
  built-device claims: measured outlets/normals/spacing, synchronized
  discharge/pressure/valve/material/flight/wind records and independent
  deposition or calibrated plume evidence. Foam needs measured foam/aeration
  properties. The illustrative 9 m/2.4 kg/m² target does not prove suppression.

**Resolved and not to reopen:** B0-R/P1 replay hash drift is already resolved
by the recorded exact-path review and non-solver checks. P1 revision 2 remains
accepted only as its source/ledger diagnostic; revision 1 remains failed under
its original protocol. Neither P1 replay nor another unchanged candidate3
regression is needed to fill compute queues.

## Parallel author preparation and dependent review/run queue

Only the primary allocates compute and modifies shared plans/interfaces.
Three worker slots include this auditor and any Warden/reviewer; do not count
three implementers plus review roles as separate pools. As this memo hands
off, its slot can return to independent preparation.

| Work that can proceed in parallel | Exclusive ownership and bounded handoff |
| --- | --- |
| Luna source implementer: B1 successor candidate | New `containers/flutas/candidate4/` or another primary-assigned unused candidate directory; no edits to candidate3 or shared gate. Start with at most two allocated CPU cores for a build, no worker GPU/solver launch. Hand off diagnostic formulas/call sites, hashes, helper oracles, logs/exits, schema deviations and unresolved findings. |
| Luna analyzer author: B2 after primary freezes the schema | A primary-assigned new analyzer module and dedicated tests; no source patch or shared protocol edits. One CPU thread for synthetic fixtures. Hand off complete positive/negative reports, deterministic schema behavior, expected row/status rules and exact hashes. Until the schema is fixed, use this slot for B6 timing/convention revisions or E3/E4/E5 source preparation in disjoint files. |
| Astra independent reviewer: stable E1 packet, then revised E2/candidate/protocol as ready | Separate review records only, one light CPU thread, no author edits. First disposition the corrected E1 method/mesh proposal and its limits. Subsequent acceptance reviews depend on a complete stable author handoff, not an in-progress shared file. |
| Primary: integration, schemas, launchers, contract and status | Resolve shared interfaces before dependent code, update the stale state above, inspect combined diffs and run affected checks. No new user permission is needed for these authorized reversible tasks. |

The queues are sequential within each dependency chain:

1. **GPU/source chain:** completed candidate3 regression → successor telemetry
   and behavior implementation → native build/code-object evidence → exact
   bounded review and smallest eligible source-disabled runtime check → complete
   source analyzer/protocol approval → ordered source cases with stop-on-first-
   failure → separate pilot review/profile → only then a scale decision.
   Candidate3 is not eligible for a source run. While no changed, reviewed GPU
   checkpoint is eligible, record “B1/B2 telemetry/analyzer/protocol closed” as
   the idle reason and keep CPU preparation moving.
2. **CPU E1 chain:** stable corrected packet → independent source/metric/input
   decision → approved preparation and immutable case/mesh/sampler → reviewed
   bounded characterization/profile when needed → accepted full execution
   contract → E1/refinements → independent result disposition. A failed,
   inconclusive or descriptive-only E1 does not release E2 without a separately
   reviewed prospective scope amendment.
3. **E2 chain:** B6a clock/startup decision → deterministic method conventions
   → CPU generator/manifest and independent tests → reviewed scenario/target/
   score and full case protocol. These preparation stages can overlap E1;
   actual E2 CFD still waits for accepted E1 advancement and resource readiness.
4. **Later CPU preparation:** E3 source mapping, E4 uncertainty/registration,
   E5 six-case extraction and B8 interface/oracle work are useful independent
   tasks whenever a worker slot would otherwise wait. Their output does not
   authorize bypassing E1–E6 execution order.

Refresh `make doctor` and active-job/headroom inspection before allocating the
next substantial job. The historical 20-effective-CPU snapshot gives a shared
project ceiling of 18 after reserving two for responsiveness, not 18 per job.
A two-CPU build plus one-thread author plus one-thread reviewer uses four;
adding one eligible two-CPU locked GPU check would use six, subject to actual
RAM/disk/device headroom. Keep BLAS/OpenMP at one in process-parallel work.
One RTX 5090 means one GPU-owning task through `scripts/run_local.py --gpu`.
Runtime sampling must be recorded for future attempts and its limitations
retained. No supplied machine description establishes cluster access.

## Audit handoff and limits

Changed file: this memo only. Read-only checks used `rg`, `nl`/`cat`, SHA-256
calculation, and `.venv/bin/python` standard-library manifest/table comparison.
The run manifest check passed 134/134 entries; bubble table comparison found
168 matched rows with zero maximum z-centroid/z-velocity differences. These
were evidence inspections, not reruns. No source-code tests, build or solver
were run by this auditor because this task changes no executable behavior.

Immediate blockers are local implementation/protocol/review work, not a need
to reauthorize provisional inputs. The user/external evidence dependencies
above are specific claim limits. Only the primary updates STATUS and the
blocker plan; only the assigned scientific reviewer can approve a gate after
its required evidence is complete.
