# Live project status

Updated: 2026-10-05 08:50 UTC. The objective remains an approximate Dash-8
water-drop nearfield reproduction. Analytical E0 is the only passed gate; no
nearfield, ground, field, suppression, or 80–90% reproduction claim is validated.
See [the experiment plan](../track2_aerial_drop_experiment_plan.md),
[validation gates](VALIDATION.md), and [source map](REFERENCES.md).

## Compute and effective queue

The localized c=1000 `nut`-cap CFD completed at 03:15:11 UTC with exit 0;
ambient-air intensity 1% completed at 04:17:08 UTC with exit 0. The
6.2-million-cell refinement started at 04:17:37 UTC, saved its all-rank
0.1 s checkpoint and is now paused at logged t=0.113840 s. Its exact container
ID and 20 solver ranks are pinned by the active pair scheduler. The first
1.858-million-cell local-mesh member started at 06:49:05 UTC on 20 ranks;
its exact 0.5 s checkpoint was exported and analyzed at 08:49 UTC while the
solver continued. The 07:48 live sample measured
19.1 core equivalents and 5.45 GiB RAM; this is not a settled runtime estimate.
The matched three-component inlet member is queued behind it. After both,
the scheduler resumes the same fine container; its original 24 h watchdog
deadline remains 2026-10-06 04:17:37 UTC. Native analysis and GPU rendering
have a separate terminal observer, with no physics retry on observer failure.
The reusable prebuilt-polyhedral runner is handed off; root reviewed its
ownership-aware interruption cleanup, paused-process accounting and explicitly
analysis-only checkpoint inventory, and reran all 15 focused tests plus Ruff
and formatting. Its wider 4,962,992-cell input contract matches the prepared
inventory; saved checkMesh evidence was evaluated without a new mesh/CFD run
([verification](../results/runs/dash8-native-vof-runner-verification-20261005T065733Z/verification.json)).
Real Docker interruption and solver execution through this new runner remain
untested. The Luna workers handed off the native paper-count comparator,
one-shot live GPU mesh view and native-cell bounding envelopes for penetration/width.
The downstream count observer v3 is active (PID 1129726) and waits for the
matched pair's verified terminal outputs. Root reran all 11 count tests after
the label collision guard. Root inspected the saved 0.1 s GPU comparison:
both meshes show a short attached source strip at this early time; it cannot
establish a breakup improvement. Field and mesh hashes remained unchanged
([LIVE_PARTIAL image](../results/runs/dash8-native-paper-count-pair-observer-20261005T071428Z/live-partial-t0p1-attempt-01/live-partial-native-mesh-t0p1-nearfield.png)).
The native width/penetration companion is now active (PID 1139776), waiting
on the pair's sealed native analysis rather than GPU-render success. Its null
outcome regression accepts identical alpha/U outputs; full `make check` reports
497 passed and one optional Docker smoke skipped
([preparation](../results/runs/dash8-native-cloud-pair-observer-20261005T080924Z/preparation.json)).
The wider 4.963-million-cell baseline is now queued after successful pair and
fine completion or its explicit wall-budget timeout, ahead of the older held
source queue. Its waiting service is independently verified active, PID 1144066.
Frozen inputs preserve physics, source history and mesh; allocation is 20 ranks,
96 GiB maximum, 1.5 s horizon and a fresh 24 h budget from actual invocation.
The old source80 control now waits on a new release sentinel, written only
after owned solver cleanup and allowed terminal evidence. The prior control is
preserved. Root caught and reviewed the systemd-collection fix and independent
actual-log horizon/End check; 10 focused queue tests pass
([handoff](../results/runs/dash8-wider-plume-queue-20261005T075838Z/service-handoff.json)).
No wider CFD has started and no release sentinel exists. The one-shot
LIVE_PARTIAL native/GPU comparison at exact 0.5 s is complete. Root inspected
the fixed-camera image: both meshes retain a very similar attached sheet.
Native dilute-cloud counts remain one attached component in both cases.
Dense-core counts change from 13 to 19, but detached dense-core mass decreases
from 14.166 to 12.211 kg; minimum-two-cell counts change from 8 to 9. This
early mesh contrast does not establish improved breakup. All saved fields and
mesh hashes remained unchanged
([comparison](../results/runs/dash8-local-uniform-live-t0p5-retry-20261005T084810Z/comparison.json)).
The first observer's attribute-error failure is preserved; only the read-only
observer was corrected and retried, with no CFD action. The saved native
k/epsilon/nut diagnostic is now complete with seven tests and four subtests;
root reviewed global-cell alignment, raw-value and signed-weight handling.
The sealed 1 s reference reproduces the prior water-weighted means
k=1.41519 m²/s², epsilon=28.1337 m²/s³ and nut=0.00872631 m²/s; its saved
turbulence fields are finite and nonnegative. These snapshot statistics do
not identify the turbulence mechanism
([evidence](../results/runs/dash8-native-turbulence-audit-20261005T085142Z/evidence.json)).
The user-requested publication includes completed diagnostics and selected
previews with raw runs excluded. A Luna worker is checking a minimal upstream
discharge pilot with a simplified curved belly, calculating Q/S independently
before comparing with Figure 4; no discharge case or additional CFD has launched.
These implementations do not alter the frozen running pair or add another
live CFD allocation. Native diagnostics,
GPU pair rendering, mesh preparation, partition comparison and continuation
preparation are handed off. The continuation suite now passes 18 offline tests,
including actual checkpoint-time roundoff; solver restart equivalence is still
untested. No continuation is launched or queued.
The mesh handoff, inlet compilation/evaluation and throughput investigation are
complete. These tasks do not change the active fine experiment or its queue.
Root inspected the completed AIR
whole-plume render; the attached sheet and coarse downstream structures persist.
Water length completed at 02:00:13 UTC
with exit 0; its native counts, ledger and three videos are ready. Root owns
scientific decisions while persistent queue services continue.
The one-read early profile measures 14.79 s/step on the fine mesh versus
1.00 s/step on the coarse reference through about 0.013 simulated seconds;
the last ten fine steps average 13.6 s. These startup samples do not establish
a settled full-horizon ETA or pressure wall-time share ([profile](../results/runs/dash8-fine-startup-profile-20261005T043130Z/fine_startup_profile.json)).
The later one-read profile reaches t=0.034970 s (2.33% of the horizon). Its
latest nine intervals average 15.56 s/step; constant-rate arithmetic gives
35.77 h total against the 24 h cap. This establishes conditional budget
exposure, not a settled ETA. A separate continuation is being prepared to
preserve sealed checkpoints and the full absolute-time native flux history
if needed ([evidence](../results/runs/dash8-fine-throughput-investigation-20261005T045638Z/throughput_investigation.json)).

| Order | Run / state | Resources and dependency |
| --- | --- | --- |
| 1 | Water-length 5 mm — complete | 670,480 cells, 1 s; 20 ranks, 96 GiB; exit 0, native counts/ledger/three videos ready |
| 2 | Localized `nut` cap, c=1000 — complete | 670,480 cells, 1 s; 20 ranks, 96 GiB; exit 0 at 03:15:11 UTC |
| 3 | Ambient-air intensity 1% — complete | 670,480 cells, 1 s; 20 ranks, 96 GiB; exit 0, terminal comparison recovered and rendered |
| 4 | Matched large-opening refinement — paused for pair | 6,205,440 cells, 1.5 s; saved 0.1 s; exact Docker container remains paused, not restarted |
| 5 | Local-mesh uniform inlet — running | 1,857,796 cells, 1 s; 20 ranks, 96 GiB maximum; prebuilt mesh and physical time loop verified |
| 6 | Local-mesh three-component inlet — queued | Same mesh/history/numerics, altered U/k/epsilon; starts after uniform success, then fine resumes |
| 7 | Wider refined static baseline — queued | 4,962,992 cells, 1.5 s; 20 ranks, 96 GiB; waits for pair/fine terminal and actual capacity |
| 8 | Source80 / far300 — held | Existing SIGSTOP and resume controller now wait for the wider run's verified release sentinel |
| 9 | Source40 / far300 — waiting | Existing launcher waits for source80 |
| 10 | Small-area composite — waiting | Existing queue is downstream of source40 |

Effective order is water/cap/air (complete) → fine first checkpoint (saved,
paused) → local uniform (running) → local three-component → fine resume →
wider baseline → source80 → source40 → small-area composite. The source80 controller
waits for the wider baseline's release sentinel. Air counts, ledger and three videos are handled by its
existing postprocessor. The separate terminal AIR comparison recovered from an
existing-directory collision in fallback analysis; its successful retry uses
one-thread Sequential VTK on saved fields. This did not fail or restart CFD.
Water results are in its [postprocess record](../results/runs/dash8-water-ell005-20261004T221719Z-1s-postprocessed/dash8-water-ell005-20261004T221719Z-1s/postprocess.json);
live handles, input hashes, rollback attempt and prior status are in the
[air queue record](../results/runs/dash8-air-intensity-priority-20261005T014251Z/launch.json)
and its linked `status-before-compact.txt`.

The air trial changes only ambient-air turbulence intensity from the existing
5% assumption to an orchestrator-selected 1% assumption; it is not a measured
Calbrix input. The frozen candidate matches the 670,480-cell, 1.332 m² uniform
source, corrected 50 m/s backflow, water turbulence, numerics, and standard
k-epsilon reference. Only `0/k`, `0/epsilon`, and metadata differ; candidate
case inventory SHA256 is `80edf1bc7863fd799e38c58795b7a860d75796b29c67c1808a7ae9d507ead97e`.
Calbrix reports external-air speed but omits ambient-air turbulence values
(PDF p. 4 / journal p. 1518). The assumption conversions and exact hashes are
in the [frozen preparation](../results/runs/dash8-air-intensity-preparation-20261005T011459Z/case-record.json).

The fine terminal-comparison waiter for 1 and 1.5 s is active with corrected
fallback handling, PID 1045549 ([current service record](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/service-launch-fine-terminal-v2-20261005T042555Z.json)).
The cap and recovered AIR t=1 comparisons are complete; original failed attempts
and retired observation handles are preserved. Terminal observers wait for manifests
and sealed fields, reuse only live-monitor reports with verified hashes, and
fall back to analysis after completion when that monitor is absent. Each pair
uses native-field inventories/statistics and a serialized GPU render at shared
Ux limits 0–50 m/s; VTK is Sequential with one thread, nearfield camera half-
height is 4.5 m, and the overview uses the full-domain union framing. The
scale correction and readable labels were checked in the [nearfield render](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/nearfield-camera-scale-labels-20261005T030319Z/nearfield-alpha-iso-t1.png)
and its [camera record](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/nearfield-camera-scale-labels-20261005T030319Z/render.json).
The live-checkpoint path passed on Air at exact t=0.1 s while the solver remained
live: it checked the manifested image/container and all 20 ranks, held the 100
native alpha/U/k/epsilon/nut files stable across 2 s, verified exact VTK time,
and recorded an explicit 0–0.1 s native-flux prefix. The output is [LIVE_PARTIAL](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/integration-live-air-i001-t0p1-20261005T032445Z/t0p100000/comparison.json),
not a terminal success claim; its matched [nearfield](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/integration-live-air-i001-t0p1-20261005T032445Z/t0p100000/nearfield-alpha-iso-t0.1.png)
and [whole-domain](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/integration-live-air-i001-t0p1-20261005T032445Z/t0p100000/whole_plume-alpha-iso-t0.1.png)
views are checked. The corrected fine observer processes 0.5 then 1.0 s
sequentially, retries Docker timeouts only for the same container ID, uses a
one-thread VTK Sequential guard for newly computed attachment reports, and
leaves the solver untouched; the corrected v3 [service record](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/service-launch-fine-live-v3-20261005T034455Z.json)
is active with PIDs 1037897/1037898. The two earlier idle-observer attempts
are preserved in their [retirement records](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/service-retirement-fine-live-20261005T033653Z.json)
and [v2 record](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/service-retirement-fine-live-v2-20261005T034455Z.json).
Sixteen focused automation tests, Ruff, and Python compilation checks pass.

The earlier maximum-history source profile prescribed only 45.8% of uniform
release; its lower cloud count therefore does not show better breakup. See the
[profile comparison](../results/runs/dash8-maximum-profile-t1-comparison-20261004T231757Z/comparison.json).
Correcting air backflow reduced global turbulence maxima while water-weighted
`nut` changed little, without a demonstrated breakup improvement; see the
[matched boundary comparison](../results/runs/dash8-backflow-partial-comparison-20261004T220427Z-t1/summary.json).

## Current findings

At 1.0 s, corrected-uniform / uneven-outflow native counts are 41/45 for
alpha≥0.001 cloud and 123/104 for alpha≥0.9 core. Fig. 11’s digitized read is
about 267 cloud / 14 core regions (PDF p. 10 / journal p. 1524), but the paper
detector is unpublished. The change is mixed and remains exploratory; ledger,
velocity and count evidence is in the [terminal comparison](../results/runs/dash8-uneven-terminal-comparison-20261005T005540Z/summary.json).
The completed uneven case's frozen `0/U` contains 24 continuous space-time
cosine modes, modulating only downward-normal velocity with a maximum 60%
deviation (0.4–1.6 times the mean history). Actual mode periods span
0.0582–2.529 s; these are provisional forcing, not measured outlet dynamics.
Its area mean follows the digitized history, so it does not add whole-opening
discharge pulsations. The queued three-component inlet also varies continuously
in time and adds lateral velocities, but has a different assumed spectrum;
it is not an isolated same-spectrum direction test.
The paper-count comparator now accepts the native-polyhedral analyzer directly;
the old Cartesian input remains supported. Explicit report labels keep paired
native-analysis files with the same basename from being merged in plots.
Root reran all 11 comparator tests
and inspected the [reference overlay](../results/runs/dash8-native-paper-count-comparison-20261005T071000Z/counts.png).
At exact t=1 s, the native reference gives 41 cloud versus the raster read
266.6 (time-propagated bounds 256.9–275.1), and 123 core versus 14.0
(8.4–19.6). Minimum-two-cell counts are 35/38, not substitute primary results.
This one saved snapshot covers one of 51 target bins; detector equivalence and
the requested reproduction remain unproven. The count companion is installed
and waiting on the current pair's terminal analysis.
Native full-cell envelope profiles now support the nonconforming polyhedral
mesh, use actual OpenFOAM volumes, retain empty slabs and source-center/edge
registration alternatives, and report boundary contacts. Root corrected the
independent Fig. 9 width/depth column-order mismatch through worker review,
inspected the [reference width comparison](../results/runs/dash8-native-cloud-profile-audit-20261005T072224Z/analysis-attempt-07/paper_cloud_comparison.png),
and ran the combined native reader/runner/profile/count suites: 44 tests pass.
The old t=1 s reference's cloud bounding width peaks at 5.267 m, or 4.563
under the provisional Lc=1.154 m normalization, versus the primary figure-read
peak 6.165. This conditional geometry discrepancy accompanies the count gap;
it is not a formal score or proof of the paper's unknown aperture scale.
Profile extraction gives the same peak at 0.075/0.15 m station spacing and
preserves the native 5.171525 m³ inventory. Top-plane contacts include the
intended inlet and do not by themselves indicate plume truncation.
Root also inspected the completed uniform/cap/1%-air
[spreading overlay](../results/runs/dash8-turbulence-cloud-spreading-20261005T075113Z/comparison-complete/t1_cloud_spreading_comparison.png).
All three cloud-envelope maxima remain 5.267 m on their identical coarse mesh.
At 0.075 m slab spacing, the cap and lower-air-intensity cases increase median
common-depth width by 0.601/0.159 m, but the cap is 1.350 m narrower at 8 m depth.
Selected outer-cloud cells at 4–6 m depth span up to 0.567 m transversely.
These qualified full-cell bounds show redistribution rather than a consistent
spreading fix; wider refinement remains the next resolution diagnostic.
The sealed cap/air exports preserve their fields, and all source tables agree
through the common 1 s window despite the reference's 1.5 s horizon
([audit](../results/runs/dash8-turbulence-cloud-spreading-20261005T075113Z/comparison-complete/comparison.json)).

Reducing water turbulence length from 0.05 m to 0.005 m gives a mixed response
at 1 s: dilute-cloud components rise 41→49 (minimum-two-cell sensitivity
35→40) and detached mass 400.05→412.18 kg, while dense-core components fall
123→116 (38→34 sensitivity) and detached mass 151.62→112.72 kg. Water-weighted
`nut` changes +1.18% at 1 s, so its earlier 13.12% decrease at 0.5 s does not
persist; weighted `k` and `epsilon` rise 2.67% and 3.18%. Both native ledgers
close to about −2.5×10⁻⁵ kg. This does not show that shortening the length
scale fixes breakup. See the [terminal comparison](../results/runs/dash8-water-length-terminal-comparison-20261005T020801Z/comparison.json)
and [0.5 s checkpoint](../results/runs/dash8-water-length-halfsecond-20261005T013128Z/comparison.json).
A separate diameter/velocity-operator sweep preserves the primary 41/123 counts
but shifts the 0.1–1 m cloud number-mean streamwise speed only from 19.79 to
21.37 m/s, still below the reported 41.57 m/s; the tested definitions do not
resolve that mismatch ([sweep](../results/runs/dash8-structure-operator-sensitivity-20261005T025226Z/evidence_retry3/operator_sensitivity.json)).
An interpolated surface-region observer gives 0.1–1 m mean Ux 32.07→41.63 m/s
for uniform→cap, but those regions use different topology, diameter and
weighting from native liquid components and are not equivalent to the paper's
41.57 m/s measure ([surface sensitivity](../results/runs/dash8-surface-velocity-sensitivity-20261005T034459Z/surface_velocity_comparison.json)).

For the fixed-box viscosity cap at exact 0.5 s, the alpha≥0.001 cloud stays one
attached region with no detached cloud. For alpha≥0.9, core components rise
13→18 but minimum-two-cell
components fall 8→6; detached mass falls 14.166→10.559 kg (minimum-two-cell
mass 11.863→4.821 kg) as singleton components rise 5→12. Water-weighted
`k`/`epsilon`/`nut` fall 73.35%/67.14%/73.89%; native alphaPhi ledgers cover
only the explicit 0–0.5 s prefix and close −1.42×10⁻⁶/−3.88×10⁻⁶ kg. All 100
saved alpha/U/k/epsilon/nut fields per case have unchanged pre/post hashes.
This fixed-box cap acts on shared `nut` in both phases and is not interface-
following. At t=1 s, corrected-uniform → cap native counts change 41→74 cloud
and 123→103 dense-core components (minimum-two-cell sensitivities 35→59 and
38→16). The cap still leaves 92.4% of threshold-selected dilute-cloud mass
source-attached; detached cloud mass changes 400.05→391.51 kg and detached
dense-core mass 151.62→123.99 kg. For 0.1–1 m clouds, number-mean streamwise
velocity changes 19.79→23.07 m/s and mass-mean 16.55→17.05 m/s, both below the
reported 41.57 m/s. Water-weighted k/epsilon/nut changed
1.415/28.134/0.008726 to 0.806/16.329/0.004663. The native alphaPhi ledger
records 5,196.76779 kg released,
5,156.67630 kg stored, 40.09146 kg net escape and −3.13×10⁻⁵ kg closure. The
separate interpolated-surface audit gives cloud/core counts 27/3→49/6, unlike
the native-cell counts; this is detector sensitivity, not equivalence to the
paper's unpublished method ([audit](../results/runs/dash8-cell-vs-isosurface-counts-20261005T031842Z/comparison.json)). See the
[terminal native report](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/comparisons/cap-t1/t1p000000/comparison.json).
The [0.5 s native comparison](../results/runs/dash8-nut-cap-halfsecond-evidence-20261005T023637Z/comparison.json)
and [figure](../results/runs/dash8-nut-cap-halfsecond-evidence-20261005T023637Z/side-by-side-native-alpha-isosurfaces-cap-vs-uniform-t0p5.png)
preserve the early-prefix evidence. The mixed count and attachment response
does not establish improved physical breakup.

At exact 0.5 s, the live 1% ambient-air-intensity case keeps one source-attached
alpha≥0.001 cloud component, as does the 5% reference. Native alpha≥0.9 core
components change 13→9 (minimum-two-cell sensitivity 8→7), and detached core
mass changes 14.166→8.492 kg. For 0.1–1 m core components, number-/mass-mean
streamwise velocity changes 3.45/3.33→3.86/3.94 m/s. Water-weighted
k/epsilon/nut fall 24.6%/20.5%/22.1%; both 0–0.5 s ledgers close within
4.1×10⁻⁶ kg. The matched views still show an attached sheet with modest shape
change, so this live partial checkpoint does not show that lowering assumed
ambient intensity improves early breakup or predict the terminal response
([comparison](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/integration-live-air-i001-t0p5-20261005T034455Z/t0p500000/comparison.json),
[nearfield](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/integration-live-air-i001-t0p5-20261005T034455Z/t0p500000/nearfield-alpha-iso-t0.5.png),
[whole plume](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/integration-live-air-i001-t0p5-20261005T034455Z/t0p500000/whole_plume-alpha-iso-t0.5.png)).
At terminal t=1, lower air intensity changes cloud/core counts 41/123→52/120
(minimum-two-cell 35/38→43/32). Detached dilute-cloud mass rises
400.05→482.59 kg, whereas detached dense-core mass falls 151.62→129.55 kg;
medium-cloud liquid-weighted Ux remains 19.79→19.73 m/s. This mixed late response
does not close the paper gap; the earlier checkpoint did not predict it. Root
reviewed the recovered native report and paired render; both native ledgers
close within 2.5×10⁻⁵ kg ([terminal comparison](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/comparisons/air-i001-t1-fixed-20261005T042700Z/t1p000000/comparison.json)).

The offline diagnostic estimates 1.039 m/s normal RMS (23.3% of mean speed)
over 0.2–0.8 s; its deterministic normal-only forcing-energy proxy is 7.23×
modeled water inlet `k`, a diagnostic ratio rather than measured physical
turbulent energy, and the forcing is weakly resolved across four source rows,
not measured turbulence or a validated LES input ([diagnostic](../results/runs/dash8-source-forcing-diagnostic-20261005T020931Z/source_forcing_diagnostic.json)).

The t=1 refinement-region split finds 48.85/50.18% of all-alpha water outside
the [-2.5,4]×[-1.5,1.5]×[-3,0] m fine box for corrected-uniform/uneven cases;
32/41 and 42/45 cloud components touch coarse cells. This locates much plume
mass in coarser cells but does not isolate mesh causality; the matched fine
case is now running. See the [native region audit](../results/runs/dash8-coarse-region-split-audit-20261005T012848Z/summary.json).
On the old t=1 fields, rectangular cell-overlap integration places 99.52% of
uniform and 99.24% of cap water in the planned larger fine plume band; this is
coverage of existing fields, not a prediction of the fine run. The fixed
alpha-threshold sweep reproduces primary counts and remains far below the
paper cloud count across dilute thresholds. Raising alpha 0.001→0.003 changes
uniform/cap counts 41→39 / 74→66 while excluding only 0.046% / 0.069% additional
water; neither the threshold nor these results establish physical versus
numerical breakup ([bridge and coverage diagnostic](../results/runs/dash8-alpha-bridge-sensitivity-20261005T040203Z/bridge_sensitivity.json)).
Despite high mass coverage, 9/41 uniform and 18/74 cap cloud components are not
wholly contained in that band; low-mass fast fragments still need a resolution
check ([component coverage](../results/runs/dash8-alpha-bridge-sensitivity-20261005T040203Z/planned_band_primary_components.json)).

A deterministic three-component inlet forcing is prepared offline. Its assumed
0.265–0.373 m wavelengths pass the declared six-sample spatial criterion on
40 mm source faces but not 80 mm faces. Flux and mean-velocity checks pass;
adding its full resolved energy to unchanged RANS k would double nominal inlet
energy, so the candidate is not queued. It is not measured or divergence-free
turbulence, or LES ([preparation](../results/runs/dash8-three-component-forcing-preparation-20261005T040038Z/forcing_preparation.json)).
A separate runnable inlet case is prepared with a nominal 50/50
resolved/modeled energy split. Root checked native compilation and evaluation
at t=0.4 s on 888 source faces: serial and 20-rank results match at logged
precision, including 19 ranks with zero local source faces. Mean discharge
and positive inward flow are preserved. This evaluates the boundary only,
without advancing CFD equations ([verification](../results/runs/dash8-partitioned-inlet-case-preparation-20261005T043141Z/verification.json)).
The continuum split is knot-exact: between history knots,
linear interpolation of k differs from squaring the interpolated source speed.
The frozen modal amplitude and tables remain unchanged. The release-weighted
candidate/reference energy ratios are 0.998678 in the continuum and 0.998714
on the sampled faces; startup and finite-face differences remain explicit.
The active fine baseline and queue remain unchanged; this coupled inlet
sensitivity will be judged after baseline evidence.

The isolated local-refinement candidate has about 1.858 million cells and
960 source faces with unchanged 1.332 m² opening area. `checkMesh` reports
23,997 concave cells, while an independent native all-vertex supporting-plane
test finds zero nonconvex cells. The pinned checker also flags planar
face-centre pairs; the worker reproduced its flagged set on transition
polyhedra. The original failed check remains preserved. All cells intersecting
the declared plume band have spans ≤75 mm, and source-box cells have spans
≤37.5 mm; the farfield is coarsened from 300 to 600 mm. The 70.1% cell reduction
therefore includes both local topology and farfield coarsening, with no runtime
gain yet measured ([mesh handoff](../results/runs/dash8-local-refinement-efficiency-20261005T045530Z/preparation.json)).
Existing Cartesian-only readers cannot analyze this mesh correctly. The new
native owner/neighbour and source-face reader reproduces the finished
reference's 41 cloud / 123 core components in both serial and 20-rank reads.
Its local mesh-only read confirms one connected graph and 960 source faces;
the cold coded-boundary read leaves source hashes unchanged without compiling
boundary code. Seven focused tests, Ruff and formatting checks pass. Raw alpha
is preserved, including roundoff; processor joins are checked for reciprocity.
This is static-mesh analysis evidence, not a CFD validation pass
([verification](../results/runs/dash8-native-topology-analysis-20261005T053520Z/verification.json)).
Local uniform CFD is now running; the three-component member has not yet started.
The native polyhedral renderer produced both nearfield and whole-domain images
on the RTX 5090, with exact saved time and unchanged input hashes. Root viewed
both; this same-reference rendering check contains no new CFD outcome
([render record](../results/runs/dash8-local-mesh-pair-render-evidence-20261005T054500Z/same-reference-interface-check-v2/render.json)).
The local mesh's existing simple partition is cell-balanced to one cell.
Scotch reduces unique processor cuts from 276,180 to 107,101, but no solver
speedup is measured; retain simple for this frozen trial
([partition record](../results/runs/dash8-local-mesh-decomposition-20261005T060128Z/case-record.json)).
The matched 1.0 s pair is activated. The first attempt stopped before CFD
because its launcher rejected checkMesh exit 1 despite the sole reviewed
planar-transition flag; recovery resumed fine, and the failed attempt remains.
The fresh retry accepts exit 1 only for that same exact flag, unchanged mesh
hashes, byte-identical stdout/log and empty stderr. It records
`formal_quality_gate_pass=false`; other failures remain rejected. The scheduler
PID 1114445 and terminal observer PID 1116305 are independently verified live
([activation](../results/runs/dash8-local-mesh-pair-exit1-retry-20261005T064542Z/retry-activation.json)).
The observer's first stale-path failure is also preserved; its corrected v2
service is active. Five exit-policy regressions and 21 scheduling/pair tests
pass. Fine's unchanged 24 h budget includes this pause.

A wider static launch candidate has 4,962,992 cells covering x=[-2.5,23],
y=[-3.5,3.5], z=[-10,0] m with native spans ≤75 mm, source faces 37×37.5 mm,
and farfield ≤600 mm. The first wider attempt left downstream cells at 150 mm;
it is preserved. Correcting background subdivisions produced the requested
resolution, with 7.27 GB peak memory in the mesh build. The 44,965-cell planar
check failure remains explicit; independent geometry finds zero nonconvex
vertices. This candidate is prepared with corrected post-meshing metadata,
not decomposed or run ([comparison](../results/runs/dash8-wider-plume-mesh-preparation-20261005T061516Z/mesh_comparison.json)).

Four-snapshot k/epsilon VTK flux proxy indicates net air-to-water diffusion;
`k` transfer is 0.15–0.26 of same-band local production. It is spatially
incomplete and is neither a closed budget nor causal proof. Fig. 6/7 zero-origin
source digitizations jointly support provisional `Lc=1.130–1.184 m`; the
current `sqrt(1.332 m²)=1.154 m` is compatible, but the plotted endpoint is
clipped, so aperture and scale remain unresolved. See the
[flux proxy](../results/runs/dash8-interface-turbulence-flux-20261005T0113Z/diagnostics.json)
and [source cross-check](../results/runs/dash8-source-normalization-crosscheck-20261005T011452Z/source_normalization_crosscheck.json).
At 0.5 s, uniform and cap penetration profiles differ by 0.0148 m on average
and at most one local vertical cell; unknown source-origin registration prevents
a unique paper error score ([comparison](../results/runs/dash8-paper-cloud-comparison-20261005T031624Z/comparison_retry4/paper_cloud_comparison.json)).
The vertical velocity sign transform is supported conditionally on a shared
figure basis; the paper does not specify the initial fields or t=0
([source audit](../results/runs/dash8-paper-velocity-frame-audit-20261005T034559Z/review.json)).

Pinned v2512 review finds stock `multiphaseStabilizedTurbulence` incompatible
with the variable-density path; `buoyancyTurbSource` is a compatible k-only
signed density-gradient source, not direct interface damping, and was not run.
`limitTurbulenceViscosity` caps shared `nut` in a fixed region for both phases;
it does not follow the interface or reproduce STAR’s interface-damping method.
The completed c=1000 cap diagnostic used the fixed [-2.5,4]×[-1.5,1.5]×
[-3,0] m box. The matched refinement is a static band mesh with a changed time
step, not local AMR or an isolated spatial-convergence test. See the
[interface-treatment source review](../results/runs/dash8-interface-treatment-source-audit-20261005T013534Z/review.json).

The mixed Euler/BDF2 `rhoU` case remains unqueued: Euler-step `rhoPhi` and
pinned `interIsoFoam`’s lack of explicit `fvc::ddt(rho)`/Sp correction mean
changing `ddt(rho)` alone does not preserve uniform velocity as density varies.
A consistent BDF2 density flux needs history weighting; that algebraic
requirement is not an implementation recommendation or solver test
([audit](../results/runs/dash8-momentum-density-consistency-audit-20261005T023050Z/audit.json)).

## Unresolved inputs and limits

The paper’s source mean-velocity history is digitized from Fig. 4 (PDF p. 5 /
journal p. 1519), not a recovered outlet measurement; the 1.332 m² effective
opening remains assumed. Air/water turbulence intensity and length scales are
not fully reported. The custom uneven velocity field is provisional forcing,
not measured turbulence, and changes local peak speed and momentum. Native
fragmentation counts depend on an unpublished paper detector; mesh, interface
physics, and source assumptions remain coupled. Preserve raw fields and report
mass/momentum ledgers for every queued trial. No gate tolerances or source
parameters were fitted to these results.

The most recent full repository check reported 497 passed and 1 skipped. The
current queue transaction changed no tracked solver code; its launch scripts
passed Ruff and Python compilation.
