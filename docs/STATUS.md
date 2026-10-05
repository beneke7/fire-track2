# Live project status

Updated: 2026-10-05 14:35 UTC. Objective: approximate Calbrix Dash-8 nearfield reproduction.
**Analytical E0 is the only passed gate.** No nearfield, ground, field,
suppression or 80–90% reproduction claim is validated.
See [plan](../track2_aerial_drop_experiment_plan.md),
[gates](VALIDATION.md) and [sources](REFERENCES.md).

**User discussion pause:** autonomous goal and all subagents are paused/stopped.
Only the existing three-component nearfield solver continues, logged
t=0.845779 s at 14:35 UTC, 20 MPI ranks. All three already-authorized head trials
completed 0.6 s/End/exit 0 with 26/26 retained inputs unchanged, owned containers
removed and exact C3 resumed; the final active trial completed at 14:34:47 UTC.
Twenty-six waiting project services (including analysis/render observers) were
stopped. Pair scheduler PID 1114445 and paused-fine supervisor PID 999922 are
SIGSTOP-held; the current nearfield solver/controller were not suspended.
No future simulation or analysis is authorized to launch until user continuation.
The fine container remains paused. Original watchdog budgets are not reset.
[Pause actions](../results/runs/user-discussion-pause-20261005T143009Z/pause-actions.json).
Later queue/ownership descriptions below record pre-pause preparation and history;
this hold overrides their launch state. Raw h125/h150 aggregate Q/S at 0.5 s is
3.10120/3.41706 m/s, versus h100 2.75074 and Fig.4 4.677. These two new per-face
traces and maxima await the stopped analysis workflow; no validation claim follows.

## Compute and queue

Local uniform completed at 10:42:19 UTC: exact 1 s checkpoint, solver End
and exit 0. Three-component variant launched at 10:42:31 UTC, advanced to
0.827767 s at 14:11 UTC after resuming from the instrumented tank trial. At
14:13:28 it was temporarily paused for the first authorized head trial, which
uses twenty MPI ranks; the fine baseline remains paused. Its epsilon solve
used two iterations but reported negative pre-bounding values and a high
maximum; this is recorded separately from finite saved fields, not a failure
declaration. Uniform terminal native analysis and GPU still renders are
complete; the computed-field slowed video is now complete and root inspected
its t=0 and t=1 frames. Initial internal alpha is zero and the first frame has
no liquid contour. The 09:10 resource sample
measured 19.8 core equivalents and 5.54 GiB; these are observations, not an ETA.
Actual machine capacity: 20 effective CPU cores; OpenFOAM v2512 pinned image;
RTX 5090 used for rendering. No GPU CFD implementation is qualified.

| Run | State and allocation |
| --- | --- |
| Water-length 5 mm | Complete: 670,480 cells, 1 s, 20 MPI ranks; native analysis/ledger/render ready |
| Fixed-region viscosity cap, c=1000 | Complete: same coarse mesh, 1 s; exploratory modified turbulence |
| Ambient-air intensity 1% | Complete: same coarse mesh, 1 s; assumed input sensitivity |
| Local uniform inlet | Complete: 1,857,796 cells, 1 s, 20 ranks; exact 0.5 and 1 s native analyses and matched still renders complete |
| Local three-component inlet | Running after final head cleanup, logged 0.845779 s; same mesh/history/numerics, altered U/k/epsilon; 1 s target, 20 ranks |
| Fine baseline | Paused at logged t=0.113840 s, exact 0.1 s saved; 6,205,440 cells, 1.5 s target |
| Wider refined plume | Queued after pair and fine terminal evidence: 4,962,992 cells, 1.5 s, 20 ranks |
| Source80 / Source40 / small-area composite | Held downstream of wider run's verified cleanup/release sentinel |
| Gravity-driven tank discharge | First attempt failed at 0.249255 s; upwind-only k/epsilon transport retry completed 0.6 s, exit 0; 452,800 cells, 20 ranks |
| Instrumented gravity tank | Solver complete at 0.6 s/End/exit 0; 452,800 cells, 20 ranks; exact baseline resumed; separate retained-input recovery and full native-flux archive complete |
| Gravity-head sensitivity | All three depths completed 0.6 s/End/exit 0, owned cleanup and exact C3 resume; 452,800 cells, 20 ranks; h125/h150 detailed analyses held |

The first tank diagnostic failed at 0.249255 s after about 173 s wall.
Changing only k/epsilon convection from limitedLinear to upwind completed
0.6 s in 378 s (10:29:34–10:35:52 UTC), with solver End and exit 0.
The owned pilot container was removed and the exact uniform container resumed;
the paused fine container and queue stayed intact. Both attempts are preserved
([successful retry and cleanup](../results/runs/dash8-gravity-discharge-upwind-retry-20261005T102609459314088Z/pilot-20261005T102934595442Z/launch.json)).
The queue is now three-component → larger-opening priority sensitivity
(temporary exact fine pause/resume) → fine continuation → wider plume → older
source queue. A native per-face-flux tank trial temporarily paused/resumed the
exact three-component run. That short trial completed
0.6 s with End/exit 0; the coded writer compiled and output covers 1,200 owning
faces. Root verified the pilot CID absent and the exact baseline CID running
unpaused. Its original manifest reports a postrun metadata error because a
whole-case hash traversal rejects legitimate runtime dynamicCode symlinks;
the worker recovered a retained-input-only audit separately, preserving
that original error. Recovery now verifies all 26 original input hashes; root
independently rehashed them and the trace, producer, trace builder, aggregate and
audit CSV. This is not another physical solver failure.
The full 1,374-step, 1,200-face native trace reconciles every step with the
aggregate within 4.9975e-9 m³/s (declared printed-rate tolerance 5.1e-9).
Integrated volume is 2.015733411766675 m³, differing from the printed aggregate
by -1.47e-11 m³. Native water-flux-equivalent normal-speed spatial CV at 0.5 s is 8.8009%, mean
2.73458 m/s and range 2.19155–3.15516 m/s. This is modest computed unevenness,
not measured turbulence or the prior 60% synthetic forcing.
[Frozen trace and sidecar](../results/runs/dash8-native-face-alphaPhi-preparation-20261005T112300Z/postprocess-attempt-01/native-tank-alphaPhi-step-series.json).
Successful transport stabilization does not establish a
physical breakup cause or numerical convergence.
Native geometry totals exactly 1.332 m² at z=0 with all oriented normals -z;
decomposed faceZone flipMap contains both signs and must be applied per face.

Fine's original 24 h watchdog deadline is **2026-10-06 04:17:37 UTC**, including
pauses. Its last throughput sample implied 35.77 h for 1.5 s at a constant
rate: budget exposure, not a settled ETA. Prepared continuation has 18 offline
tests; actual solver restart equivalence remains untested.

Exact operational handles and contracts:

- Completed uniform CID: `796b968903199f2e2bfe13dd35f50b8d087e471bbf93d43e90b08356c3c9d496`;
  [flow log](../results/runs/dash8-local-mesh-uniform-exit1-retry-20261005t0648z/case/log.interIsoFoam).
- Fine CID: `93e8ad234f6b2dc2e4715b45d31221f00f47c8290e5a9b00ebe569bb59f3051a`.
- [Pair scheduler and activation](../results/runs/dash8-local-mesh-pair-exit1-retry-20261005T064542Z/retry-activation.json);
  terminal native/GPU observer waits for successful sealed pair outputs.
- [Wider queue](../results/runs/dash8-wider-plume-queue-20261005T075838Z/service-handoff.json);
  actual flow-log horizon and owned cleanup are required for release.
- [Paper-count observer](../results/runs/dash8-native-paper-count-pair-observer-20261005T071428Z/);
  waits for native pair and render completion, with no CFD retry.
- [Width-profile replacement observer](../results/runs/dash8-native-cloud-pair-observer-loaded-source-20261005T094430Z/replacement-attempt-02.json);
  PID 1171527, waiting for native pair completion. Analyzer records import-time
  and on-disk source hashes separately. Old waiting-service evidence and failed
  replacement attempt are preserved; no CFD or upstream scheduler changed.

## Evidence that determines the next experiments

Native components use face connectivity and thresholds alpha>=0.001 (cloud)
and alpha>=0.9 (core); counts include source-attached regions and single cells.
The paper's MATLAB detector/filter/velocity weighting is unpublished.
Native counts and interpolated-isosurface counts are different observers.

| Completed coarse case, t=1 s | Cloud / core count | Detached cloud mass |
| --- | ---: | ---: |
| Corrected uniform reference | 41 / 123 | 400.05 kg |
| Normal-only uneven source | 45 / 104 | Mixed response; mean discharge retained |
| Water length 5 mm | 49 / 116 | 412.18 kg |
| Fixed-region viscosity cap | 74 / 103 | 391.51 kg |
| Ambient-air intensity 1% | 52 / 120 | 482.59 kg |

The paper's Fig. 11 raster read is about 267 cloud / 14 core regions at 1 s.
No completed sensitivity closes this gap or establishes improved physical
breakup. A larger count alone is insufficient: the cap increases cloud count
while reducing detached water mass. See [uneven](../results/runs/dash8-uneven-terminal-comparison-20261005T005540Z/summary.json),
[water length](../results/runs/dash8-water-length-terminal-comparison-20261005T020801Z/comparison.json),
[cap](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/comparisons/cap-t1/t1p000000/comparison.json)
and [air](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/comparisons/air-i001-t1-fixed-20261005T042700Z/t1p000000/comparison.json).

Terminal local-uniform t=1 native analysis is now available: cloud count
79 (73 with two-cell minimum), core count 321 (155 with two-cell minimum),
detached cloud mass 304.428 kg and total domain water 5197.193 kg. Reference
is 41/123 with 400.05 kg detached cloud water. Increased counts do not alone
establish improved breakup; core counts are strongly single-cell-sensitive.
[Exact local t=1 native analysis](../results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/analysis/local_uniform_1p86M/analysis.json).
Canonical turbulence analysis now accepts and verifies the complete original
export inventory (legacy or all three known system dictionaries); 12 tests
pass, and both actual snapshots analyze without editing export metadata.
The matched interpolated-surface observer gives cloud 27→64, core 3→10.
These are separate from native counts, with no fitted component filter.
Local max width falls 5.267→4.860 m and center-registered downward front
8.362→7.206 m. Refinement changes morphology but does not close the paper gap.
[Full comparison](../results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/comparison.json)
and [matched full-plume GPU render](../results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/render-full-plume-retry01/matched-full-plume-native-polyhedral-pair.png)
were inspected by root; all contour bounds fit the shared frame and source
fields remain unchanged. [New slowed refined-run video](../results/runs/dash8-refined-uniform-full-plume-animation-retry02-20261005T113418Z/refined-uniform-alpha001-vs-alpha05-full-plume-10x.mp4)
shows alpha=0.001 and 0.5 at exact saved times 0–1 s, 0.1 s apart, with the
same camera and Ux scale. Playback is 10x slowed using held snapshots, with
no temporal interpolation or surface smoothing. RTX 5090 rendering and all
440 source alpha/U field hashes are verified; the 330-frame video decodes.
Additive diameter/velocity observers preserve all
previous primary results (1,455 reference and 3,801 local metrics checked).
For detached clouds in the 0.1–1 m bin, using full selected-cell geometric
volume instead of liquid volume changes membership 34→37 reference and
62→72 local. Number-mean simulation-x velocity of the existing component
mass-weighted velocities changes 19.79→20.26 and 15.16→16.00 m/s respectively.
The paper's operators and axis convention remain unresolved; these are
measurement sensitivities, not a physical correction or equivalence claim.
[Observer comparison](../results/runs/dash8-equivalent-diameter-observer-20261005T111630Z/diameter_class_statistics.json).

At 0.5 s, local refinement leaves one attached dilute-cloud component, like
the coarse reference. Dense-core count rises 13→19, but detached dense-core
mass falls 14.166→12.211 kg. Both fixed-camera renders retain a similar sheet.
[Native comparison](../results/runs/dash8-local-uniform-live-t0p5-retry-20261005T084810Z/comparison.json).

The exact **0.1 s native comparison** now covers coarse, local uniform,
6.21M fine and local three-component checkpoints. All four have one source-
attached cloud and core, zero detached components at both thresholds, and
the same result with a two-cell minimum. Stored water is 151.987–152.256 kg;
local 3C core mass is 128.417 vs uniform 132.076 kg. This does not exclude
roughness/holes within a connected cloud or establish agreement with Fig. 5.
Coarse/fine metadata falsely describes seeded cosine forcing although frozen
0/U is uniformFixedValue; actual dictionaries are authoritative. Original
records remain frozen. Future-generator metadata now correctly labels inactive
perturbation settings and absence of coded uniform-boundary logs; 41 focused
tests pass, including pre-change physical-dictionary hash checks for uniform
and perturbed cases. Root reviewed the combined diff and downstream key use.
[Early native comparison](../results/runs/dash8-early-breakup-native-comparison-20261005T113841Z/comparison.json).

At exact **0.4 s**, local uniform and three-component cases still have one
attached component and zero detached components at both thresholds. Cloud
selected mass is 1695.0529 vs 1695.0554 kg; core selected mass is 1411.4745 vs
1386.7262 kg (1.75% lower). Native dilute-cloud bounds are identical: transverse
width 1.0125 m and downward front 1.39706 m. Root inspected the matched GPU
display: uneven forcing roughens the sheet, without demonstrated detached
breakup. This is an intermediate result, not the pending 1 s comparison.
[Native 0.4 s analysis](../results/runs/dash8-local-pair-t0p4-comparison-20261005T130240Z/analysis/three_component-attempt-01/analysis.json).

**Expansion remains too narrow**, conditional on provisional Lc=sqrt(1.332 m²).
At 0.5 s, refined L/Lc is 0.882, 1.248 and 0.929 at depths z/Lc=0.75, 1.25
and 1.5, versus digitized paper widths 1.742, 2.187 and 2.261: 43–59% narrower.
Coarse widths there are 0.816, 0.984 and 0.810. At 1 s, the completed coarse
run is about 39–41% narrower at z/Lc=1.5–3 and 12–20% narrower at 4–6.
Refined 0.5 s maximum penetration is about 1.99 m versus 2.44 m digitized.
Full-cell envelope slopes are grid-sensitive; dL/dz is not dL/dt.
[Expansion evidence](../results/runs/dash8-expansion-rate-audit-20261005T091303Z/comparison-attempt-02/comparison.json).

**Rendering thresholds explain part of the apparent transport difference.**
The sealed uniform t=1 snapshot reaches x=22.406 m at alpha>=0.001, but the
leading native cell contains only 0.0343 kg and is one 0.594 m coarse cell from
the outlet. At alpha>=0.5 the front is x=3.226 m and selected water is 81.4%
of domain water; at alpha>=0.9 the front is x=2.607 m. Most water remains near
the source. Fig. 10 uses alpha=0.001 but has no calibrated position scale, so
it cannot establish a numeric travel-distance error. Snapshot U is not a trajectory.
[Transport audit](../results/runs/dash8-advection-distance-audit-20261005T092100Z/native-t1-attempt-08/advection_distance_audit.json)
and [GPU threshold views](../results/runs/dash8-alpha-threshold-view-20261005T095433Z/render-output-attempt-04/alpha-thresholds-whole_plume-t1.png).
Contours use explicitly labelled cell-to-point interpolation for display;
numeric extents use native cell values and vertex bounds.

The native k/epsilon/nut diagnostic reproduces water-weighted reference means
1.41519 m²/s², 28.1337 m²/s³ and 0.00872631 m²/s. Saved fields are finite and
nonnegative, but these are shared-fluid snapshot statistics, not a closed
phase-specific turbulence budget or proof of a breakup cause.
[Diagnostic evidence](../results/runs/dash8-native-turbulence-audit-20261005T085142Z/evidence.json).
Water-length changes do not persistently lower water-weighted viscosity.
Stock multiphaseStabilizedTurbulence is incompatible with the current variable-
density path; the tested fixed-region cap does not follow the interface.
No further turbulence variant is selected without useful evidence.

## Source and mesh limits

Dash-8 uses one downward belly opening; Restás uses four horizontal outlets.
The paper uses standard k-epsilon, 50 m/s relative air and omitted capillarity.
Current source is assumed 4.44×0.30 m, not recovered aperture geometry.
Fig. 4 is digitized and provisionally interpreted as mean speed Q/S; caption
and results call it maximum speed. The applied 0–5 s history would release
15.921 m³ at this assumed area; neither nominal 10 m³ capacity nor later
8.840 m³ retardant volume identifies the nearfield water payload. q is area-
independent; area changes total flow and momentum. Do not fit area to appearance.

Paper aircraft belly, tank-generated spatial profile, inlet turbulence,
initial external fields and source-clock registration are incompletely
specified. Current exterior is a flat slip roof. Fig. 5's 0.1 s cloud fringe
is visibly rougher than ours, though much water is still attached.
[Early comparison](../results/runs/dash8-early-breakup-investigation-20261005T091031Z/early_breakup_review.json).

Completed normal-only uneven forcing uses 24 continuous space-time cosine
modes, maximum 60% deviation, periods 0.0582–2.529 s; it preserves area mean
and adds no whole-opening pulses. Queued three-component forcing uses different
assumed wavelengths 0.265–0.373 m and a nominal half resolved/half modeled
energy split. It is not measured turbulence, LES, or a same-spectrum direction test.

The local and wider polyhedral meshes have preserved checkMesh failures on
planar transitions. Independent vertex supporting-plane checks found zero
nonconvex cells; exploratory exact-failure allowances do not pass a formal
mesh-quality gate. Wider refinement covers fast downstream fragments through
x=23 m; local refinement ends at x=8 m. Static refinement is not dynamic AMR.
[Local mesh](../results/runs/dash8-local-refinement-efficiency-20261005T045530Z/preparation.json)
and [wider mesh](../results/runs/dash8-wider-plume-mesh-preparation-20261005T061516Z/mesh_comparison.json).

## Active ownership and checks

Root integrates and makes scientific decisions. Exact saved 0.4 s comparison/GPU
views (root inspected) and finer inlet replay geometry/mapping analysis are
complete. The larger-opening waiting service now uses the reviewed immutable
wrapper, Type=exec, MainPID 1285124 and invocation
3a9c31ced8d84f5f9dd331b23f9c91db. It waits for the active pair and verified fine
resume; candidate physics is unchanged. Its 17 focused tests passed. Root
activated the numerical batch waiting service after 15 tests and an actual
verify-only run with zero launches. It is active with MainPID 1287563 and
invocation 52ba19697b9d4e1989ffb388f6775260, waiting for exact predecessors;
zero solver stages and no fine pause attempt are recorded.
Root review repaired own-process contention false positives, legitimate cleared
terminal systemd InvocationID handling and cleanup/resume recovery defects.
These are launcher defects, not physical solver failures. A second worker has
prepared three gravity-head cases (1.0/1.25/1.5 m in a common assumed 2.0 m tank),
all strict mesh checks passed at 452,800 cells. Root reviewed the corrected v4
launch helper, the v6 cleanup extraction and focused checks; all three serial
0.6 s/20-rank trials are authorized. The first started at 14:13:28 UTC, CID
b2b7f2523e4fcc582812a581454acec9cd7b80444cc9e437543d74fe08cca3d4,
and completed at 14:20:50 UTC with End/exit 0, 26/26 original inputs unchanged,
owned container removed and exact C3 resumed. The 1.25 m trial then started at
14:21:13 UTC, CID d9c634294ca83983559b2f07218f059d0900410cea658b07775d4fddb1db0d4f.
Each borrows CPU from only the exact live three-component container and
resumes that same container after owned-pilot inactivity is proven; fine is
untouched. Another Luna worker prepares native-flux/mean-versus-maximum comparisons, with disjoint output
ownership and no CFD launch authority.
The completed 1.0 m control native trace reconciles 1,612 steps/1,200 faces
with aggregate flux (maximum rate difference 4.9933e-9 m³/s). At 0.5 s its Q/S
is 2.750739 m/s versus old-tank 2.734581 and Fig.4 scalar 4.677; sampled U
maximum is 3.068 m/s. The tank extension/grid change does not materially close
the speed gap. Spatial flux-equivalent CV increases from 8.80% to 10.13%.
[Executed head comparison](../results/runs/dash8-gravity-head-comparison-20261005T140908Z/h100-comparison-v3/comparison.json).
Its frozen 670,480-cell candidate preserves the corrected reference
physics and extends only U/k/epsilon histories and horizon/output times. Root
reviewed that physical diff; waiting-service activation is authorized. Its 5 s
expected release is 15,921.396 kg under the provisional mean-speed reading.
The x=23 m and z=-31 m open boundaries remove older structures, so this is a
long-horizon nearfield-throughflow diagnostic, not a complete retained-drop or
late whole-cloud count reproduction. The curve remains nonzero at 5 s; no
unreported shutoff/tail is added.
[Frozen batch candidates](../results/runs/dash8-numerical-long-horizon-preparation-20261005T125937Z/preparation.json).
Existing queued controllers remain unchanged. Pinned stock
interFoam uses registered water flux alphaPhi0.water; with Euler and one alpha
subcycle this is the main-step phase-volume flux. The existing iso-only ledger
must not silently be reused. Early comparison and metadata correction are
handed off. Root found and the worker repaired a replay boundary dictionary-scope
bug before launch; replay checks now pass 16 tests, including patch preservation
and producer-checksum/reconciliation checks. The frozen coarse replay pair is
prepared and parsed. In a disposable actual-case copy, pinned v2512 postProcess
read and compiled U/k/epsilon coded boundaries, exit 0/End, three verified shared
libraries. No transient replay has run. Two preceding harness-only failures
(copied image-digest typo; bashrc under set-u/auto-removed container cleanup)
are preserved. Exact baseline quota was restored to 20 and it stayed unpaused.
Mapping from 1,200 native faces to 224 coarse inlet faces reduces the 0.5 s
flux-equivalent velocity CV from 8.8009% to 2.8322%; total Q is conserved but
~89% of the integrated extra normal impulse from spatial variance is lost.
This limits the coarse pair's test of natural source unevenness.
The verified local mesh supplies 960 native rectangular faces on a 120×8
grid. Its prepared 0.6 s replay pair conserves total Q to 2.1e-14 m³/s and
retains 61.75% of native time-integrated spatial variance (coarse: 11.07%).
At 0.5 s, mapped CV is 6.91% versus 8.80% native. Extra normal impulse is
23.236 N·s, only 0.431% above the uniform replay; no fitted amplification is
applied. Root reviewed the geometry adapter and matched physical inputs;
18 affected tests pass. Both resolutions remain unlaunched.
[Finer replay evidence](../results/runs/dash8-flux-replay-fine-mapping-20261005T125547Z/fine-pair-verification.json).
Root reran replay, source metadata and native face-writer checks: 63 tests pass.
Neither new comparator has launched CFD or changed the live queue. The pair will
use the same recorded total water history, liquid-only alpha=1 and zero
tangential inlet speed; it is not a coupled two-fluid/momentum handoff or a
Figure-4 reproduction. No replay CFD is launched or queued yet. Old proxy NPZs
are excluded; only the new actual per-step native trace is an allowed input.
GPU still rendering is complete. No routine Astra/Warden pass is pending.

The unlaunched MULES comparator's corrected case-02 matches the reference's
physical dictionaries and source history through 0.6 s; its first candidate
is preserved as superseded because it omitted the four freestream-backflow
entries. Shared future CL-415/Dash-8 generators now emit those entries using
the configured air speed and record them in metadata. Old cases are untouched.
Shared runner dispatch cross-checks the frozen solver against controlDict and
launches/parses the selected interIsoFoam or interFoam binary. A separate MULES
ledger verifies pinned source, Euler/one subcycle/one outer corrector, all
boundary phase fluxes and zero initial water. It reports prescribed flow and
transported flow separately; configuration-only preflight passes, with no
physical closure result yet.
[MULES candidate/source evidence](../results/runs/dash8-mules-preparation-20261005T122955Z/preparation.json).

The gravity pilot assumes a rounded internal tank bottom, 1 m head from the
aperture plane, atmospheric openings and water initially at rest. It imposes
no Fig. 4 velocity. Repaired 452,800-cell mesh has strict checkMesh Mesh OK,
1,200 internal aperture faces, 1.332 m² area and 6.32045682 m³ initialized water.
Native internal-transfer and ambient/vent escape fluxes were logged separately.
The first attempt preserved profiles through 0.225 s. The numerical-scheme
retry now supplies the full 0.6 s profile history. Pressure PCG/GAMG reported the final floating-point exception;
k/epsilon solves had already hit 1,000 iterations and large nonphysical growth,
followed by a Courant jump above 4. This is evidence of numerical instability
in the new tank pilot, not a cause established for the stable old nearfield
sheet. Analysis distinguishes geometric Q/S, wet-area mean and maximum
velocity; VTP polygon winding is not used as the physical outlet normal.
No aircraft wake or 50 m/s external airflow is included in this source pilot.
The first attempt's native Q/S at 0.1 s was 2.269 m/s versus digitized 2.29 m/s;
at 0.225 s it was 2.873 versus about 3.857 m/s. The early agreement does not
establish discharge-history agreement. Mapping its 0.1 s saved alpha/U profile
preserves the 2.802 m³/s geometric flux proxy, but native alphaPhi is 3.023 m³/s:
a 7.31% mismatch that must remain explicit before boundary replay. Coarsening
also changes reconstructed momentum and kinetic-energy flux.
Completed upwind retry confirms native Q/S=2.735 m/s at 0.5 s and 2.644 at
0.6 s, versus digitized 4.677 and 4.567 m/s. Interpolated face maxima are
3.089 and 2.984 m/s. The provisional tank does not reproduce the later source
history under either mean or maximum interpretation. Its 0.6 s internal
transfer is 2015.738 kg, signed ambient/vent escape 989.496 kg and stored water
5330.96049 kg; internal transfer is excluded from global stored inventory.
[Successful tank analysis](../results/runs/dash8-gravity-discharge-upwind-analysis-20261005T104528Z/analysis-attempt-01/).
A doubled-opening 0.5 s diagnostic has a frozen corrected-airflow candidate:
4.44×0.60 m, 2.664 m², expected 670,480 cells/448 source faces, unchanged
Figure 4 mean-speed history and matched PBiCGStab/DILU scalar solvers.
Expected release 4639.223 kg at 0.5 s; mass/total momentum double and q stays
area-independent. Older uncorrected-air candidate is preserved and not used.
A replacement priority wrapper has completed root review and 17 focused tests.
Its Type=exec service is activated and waiting for both 1 s pair members and their
scheduler cleanup. It temporarily pauses/resumes the exact fine reference;
the candidate CFD has not launched and supplies no completed result.
[Waiting-controller state](../results/runs/dash8-width-controller-replacement-20261005T133025Z/controller/activation-state.json).
This changes payload and momentum.

Latest full `make check`: **587 tests and four subtests passed**, one optional
Docker smoke skipped; Ruff lint and formatting passed, 105 files checked
(13:02 UTC). Case-generator focused lint/format checks also pass. Runtime
native-writer reconciliation and replay-library compilation are recorded above;
transient replay and MULES solver results remain absent. Failures and retries
remain preserved; exploratory evidence is not a gate pass.

User-requested publication is pushed as `61b5e6e`, with selected previews
and raw runs ignored. New discharge/profile work remains local.

The [20-hour actual-run inventory](../results/runs/dash8-cfd-run-inventory-20261005T103100Z/solver_runs.json) records nine fresh completed coarse cases separately from
restart, mesh-only and analysis attempts. It preserves the 913 s overlap of
two 20-rank jobs on 20 effective cores and an aborted-run summary/log mismatch.
Neither resource caps nor overlapping elapsed time establish measured CPU-hours.
