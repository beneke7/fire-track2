# Live project status

Updated: 2026-10-26. CPU-only work. Analytical E0 is the only passed gate.
No E1, aircraft, ground or field reproduction is validated.

## ParaView alpha display ready and queued one-node 5 s target

Short job 14649329 is terminal COMPLETED with the full 500-step convergence
and ledger checks passed; local archive verification passed. Its exact peak
speed is 103.29355 m/s, bulk/interface Co 1.12154/0.56017, and cumulative
mass residual 1.05e-11 kg. Terminal analysis:
`results/runs/rouaix-one-node-t1-20261026/analysis-terminal-20261026T102840Z/terminal-analysis.json`.

ParaView now displays the user-requested simple **cell alpha.water >= 0.01**
surface at **0.05 s**, with only two pipeline sources and no extra layers.
State: `results/runs/rouaix-one-node-paraview-20261026/paraview/rouaix-alpha001.pvsm`;
native CLI render/readback: `rouaix-alpha001-retry-gui.json` and PNG beside it.
The viewer retains 34,800 cells from the full 10,099,265-cell case. The
14 mm x/y cell scale gives about 29 cells across D in x; cell-threshold faces
are visibly stepped. The older 35.19M mesh is anisotropic 11.49/11.49/21.875 mm
near the source and never produced CFD samples, so it is not a ready finer
flow-field alternative. This display change does not modify any solver field.

Mac ParaView cannot directly read this collated final state; the successful
fallback byte-unpacks exact rank payloads locally into ordinary processor
files. It preserves all 120x9 payloads and validates 10,099,265 cells at both
0/.05 s. Its raw water-volume integral differs from the native ledger by
relative 3.74e-9. No HPC inode expansion or login-node reconstruction was used.
The existing VM was stopped after its connection failed. GUI accessibility
actions crashed ParaView in macOS AX/objc_release; user-preferred CLI startup
and native rendering succeeded. Failed UI/CLI attempts remain recorded.
Redundant native postprocess job **14650644** was cancelled while PENDING,
after exact user/name/workdir checks; it allocated no CPUs. Other jobs were
untouched. ParaView is a normal user-requested desktop view, with no GPU CFD
or HPC GPU batch-render job.

Luna hpc_long_horizon owns declared **L1-ORIG-120-01MS-5S** staging/submission:
fresh original case, fixed .1 ms, 50,000 steps toward 5 s, 120 ranks/one node,
64 GiB, 72 h cap, 1 s checkpoints/purgeWrite=2, full compact histories and
unchanged guards. The measured starting solver estimate is ~45 h; stability
and throughput past .05 s remain unknown. New /project storage has ample
quota; scratch does not have sufficient margin for another long workspace.
Job **14650641** was accepted held, verified and released. Root independently
confirmed PENDING/Priority, 120 tasks on one node, 64 GiB, 3-day wall cap,
Dependency=null and Requeue=0, with command/workdir on /project; no allocation
or start forecast. It is independent of the 300-rank short diagnostic so its
unknown wait does not artificially block the one-node target. Receipt:
`results/runs/rouaix-one-node-5s-20261026/root-submission-readback.json`.
Declaration: E1_ROUAIX_HPC_PROGRESSION.md. The declaration-only case record
was restored to its exact pre-submit hash after status enrichment; both
versions and a verified metadata-only diff are retained separately.
At the latest root check **12:03:46 UTC (13:03:46 CET)**, both 14650641 and
14648472 remained PENDING/Priority with no allocation or start estimate.

User requests a later Rouaix comparison. Source/profile definitions and 14
verified reference hashes are prepared in
`results/runs/rouaix-5s-comparison-prep-20261026/comparison-manifest.json`.
Compare admitted complete-run 4/5 s snapshots using paper cloud alpha=.1,
connected core alpha=.9, h=-y, D=.4 and both unresolved width interpretations;
the alpha=.01 viewer does not redefine the paper observable. Field-format
adapter extension, appropriate native exporter resources and overlay join
remain implementation work before those future fields are analyzed; no
automatic comparison dispatcher or E1 acceptance is claimed. Eight relevant
reference/profile tests passed.

User now requests what can be said about agreement from available fields.
Read-only CPU diagnostics at t=.05 s use whole-cell alpha>=.1 plus exact
x-plane cuts, explicitly separate from the later Figure 13 observer/gate.
At x/D=.25, h/D=1.264 versus digitized 1.500; full span/D=1.085 versus
reported z/D=1.071 (half-span=.543). At x/D=.5 the corresponding values
are 1.229 versus 2.275 and full span .775 versus reported 2.143. No cloud
cells intersect requested planes x/D>=.75. The global cloud reaches only
x/D=.6285 and h/D=1.4749. These are early geometry descriptions, not a
developed-plume match or underprediction result: stages, detector and width
convention differ. Primary/raster sources, precise values and native-field
bindings: `results/runs/rouaix-startup-comparison-20261026/startup-comparison.json`.
Independent interpretation review confirms that limit. A separate historical
audit found no locally auditable healthy later-time comparator; the old
3.0736 s coarse profile is numerically compromised and boundary-censored.

Luna single_node_trial completed verified relocation of G1 and T1 archives to
`/project/nk_meshapplied/bene/fire-track2-hpc/archive-store-20261026/`, keeping
byte-identical evidence and original scratch paths through symlinks. Scratch
usage fell about 3.17 GiB. Job 14648472 was briefly held for maintenance and
released at 10:58:49 UTC; it is again PENDING/Priority, no dependency. No job
was left held. Archive SHA/size, ACL and ordinary metadata were verified;
project files use the destination default Lustre stripe layout. Receipt:
`results/runs/rouaix-archive-migration-20261026/receipts/migration-receipt.json`.
Unrelated autoresearch jobs remain untouched. Agents doing preparation are
not running CFD processes. Root owns integration and source/experiment decisions.

## One-node T1 completed diagnostic and terminal evidence

User requests the one-node option while 300-rank job 14648472 waits. Luna
single_node_trial owns a fresh read-only preflight and submission preparation
for **T1-ORIG-120-01MS-005**: existing tested 120 ranks on one node, original
schemes, fixed 0.1 ms through 0.05 s, full endpoint fields, 64 GiB node RAM,
45-minute cap and unchanged stop/ledger guards. Root declared the case in
`experiments/E1_ROUAIX_HPC_PROGRESSION.md`. Serialize the two owned full-output
trials with an exact-ID afterany dependency; unrelated autoresearch jobs under
the shared login remain untouched. **Job 14649329** was accepted held, verified
and released. Root's independent **09:54:17 UTC (10:54:17 CET)** readback shows
PENDING/Priority, no dependency, no allocation, 120 ranks/one node/64 GiB/45 min,
Requeue=0. Its current 15:26 CET forecast is provisional. Existing 300-rank
job **14648472** was PENDING/Dependency with `afterany:14649329`. This queued
snapshot is superseded by the running readback below. No new job was left held.
Source/input hashes and the
hardlinked immutable mesh passed staging checks. Receipts and independent
readback: `results/runs/rouaix-one-node-t1-20261026/`. Local make doctor confirms
10 effective Mac CPUs, 168.5 GiB free disk and no host CPU solver; no local
meshing/CFD is assigned.

Root's fresh **10:09:42 UTC (11:09:42 CET)** readback confirms **14649329
RUNNING**, started **10:01:24 UTC** via Slurm backfill, with 120 allocated
CPUs/tasks, one node **x1000c7s4b1n1** and 64 GiB. MPI step .0 started about
10:03:16 UTC. This actual start supersedes the earlier 15:26 CET forecast.
Receipt: `results/runs/rouaix-one-node-t1-20261026/status/20261026T100942Z.json`.
Latest root readback at **10:30:51 UTC** confirms **t=0.05 s / 500 steps**,
solver exit **0**, status **solver_complete_exploratory**, authoritative
`solver_max_u_m_s` **103.29355 m/s** and solver envelope **1,595.439 s
(26.59 min)**. The old periodic `max_u_seen` field is slightly lower and is
not the authoritative terminal peak. The solver crossed the earlier spike
times without an equivalent runaway. Slurm still reports RUNNING while the
runner packs the full archive; terminal convergence/ledger/archive review
remains pending. Receipt: `status/20261026T103051Z.json` under the one-node
receipts directory. Luna's earlier captured prefix through .0348 s
had 2,790 recorded solves/zero convergence failures; partial water-volume/
boundary-flux closure through .0350 s was about 1e-14 m3. Those prefix audits
must not be presented as audits of the complete .05 s state. Luna owns a bounded
terminal capture and archive/ledger verification after the .05 s run ends.
300-rank job 14648472 remains pending on the dependency; no unrelated job
was changed.

The user-requested **gpt-6.1-sol / high** OpenFOAM research is complete:
`results/runs/openfoam-crossflow-research-20261026/{research.json,handoff.md}`.
Ten candidates comprise three crossflow families and seven numerical controls,
not ten validated Rouaix analogues. Liu 2024's public jetCrossFlow is the
strongest physical/numerical lead, with explicit published-versus-default
scheme, inlet-profile and mesh discrepancies. Independent Luna review in
`independent-consistency-review.json` confirms Euler/upwind versus
limitedLinearV mass–momentum consistency is a source-backed hypothesis, not a
diagnosis: the paper also contains stable inconsistent-scheme counterexamples.
No source scheme or physics change has been adopted and no new CFD was launched
by research/review. Root owns subsequent integration and experiment selection.
Evaluate routine one-node placement by queue wait plus solver/preparation/
capture time, and allocated cost, before choosing it as the default. Current
queue forecasts alone do not establish the best end-to-end placement.

## Numerical diagnosis: turbulence, timestep and paper differences

Read-only Luna reviews and primary integration are saved under
`results/runs/rouaix-diagnosis-20261026/`: `fault-tree-review.json`,
`turbulence-audit.json`, `adaptive-audit.json` and `integrated-review.json`.
They cover 16 diagnostic branches, paper/current differences, previous attempts
and falsifying tests. The current inputs imply **1% intensity in both streams**
and a **28 mm conventional mixing length**; only the liquid intensity is
specified for the paper's baseline. RealizableKE computes variable Cmu; 0.09
is only the conventional initialization conversion. The paper's Fig. 7 / Section
3.4 reports little penetration/width sensitivity to liquid intensity 1% versus
20%, no RANS, or SST. This does not establish our numerical stability.
The integrated review also retains the historical clean-start limited-gradient
failure at 0.17425 s and kFinal tolerance sensitivity, from committed status
at HEAD; these are secondary records rather than newly audited raw fields.

G1 has simultaneous elevated U/k/nut extrema, but they are not all co-located
and no peak-time full field identifies phase or causal order. The failed final
k solve follows the velocity peak. Keep the queued original-gradient, fixed
0.1 ms T1 as the clean timestep contrast. At **08:52:38 UTC**, job **14648472**
remained **PENDING/Priority**, StartTime unknown, with no allocated resources;
receipt: `results/runs/rouaix-diagnosis-20261026/t1-status.json`.

Native adaptive stepping is a separate proposed diagnostic, not a queued or
implemented mode. Current fixed stepping does not enforce maxCo/maxAlphaCo.
Adaptivity can shrink the next step but cannot undo a computed spike. Before
launch it needs native-helper source hashes, actual-dt flux accounting, tested
endpoint semantics and a minimum-productive-step/no-advance stop. Keep one
alpha subcycle: full-step alphaPhi aggregation is not verified for more. The
v2512 two-layer flag is documented for standard kEpsilon and is not demonstrated
as a drop-in wall-treatment match for our realizableKE model. No physics,
turbulence coefficients, running capsule or queue settings changed in this audit.

## Morning inspection, 26 October

Fresh raw capture at **07:04:54 UTC (08:04:54 CET)** is saved locally under
`results/runs/rouaix-hpc-morning-20261026/root-capture-20261026/`.
All 53 captured members passed their SHA/size checks. The 24-event terminal
queue state passed root's independent hash-chain verification. The initial SSH
master expired; fresh eduID and then existing-browser SSO restored access.
Earlier fallback receipts remain explicitly labelled and do not substitute
for this raw capture. No job was cancelled during the morning inspection. The later user-authorized G1 limiter submission is recorded below.

All four original-scheme, fixed **0.5 ms** / **0.05 s** cases completed
100 steps, their declared solver residual criteria and compact ledger audits:
64 ranks **14647793**, 120 **14647876**, 240 **14648039**, 300 **14648312**.
The matched 0.010–0.049 s clock-window times were **672/310/130/99 s**;
full solver envelopes were **896.207/414.264/181.415/142.220 s**.
300 ranks is the fastest measured placement; the 6.79x window speedup versus
64 ranks is an observed startup result, not a controlled universal efficiency
or a long-horizon prediction. Node placement and evolving numerical work differ.

Queue wait dominated: **52/5152/12073/5164 s** for the four CFD jobs.
They consumed **83.43 allocated core-hours** and about **52.16 CPU-hours**
in total. The final 300-rank case ended at 05:06:46 UTC. Selector 14648313
stopped the queue at 05:06:57 UTC: the next 0.5 s case forecast 1,947 s but
only 1,023 s of bounded allocation remained before the 05:30 UTC cutoff.
**No 0.5 s or 5 s case was launched.** All recorded CFD and selector IDs are
terminal and an exact-ID squeue query is empty; this is not a host process scan.

Peak speed differs materially with decomposition: **555.11/261.55/904.74/
412.48 m/s** at 64/120/240/300 ranks, respectively. Convergence and mass closure
do not establish physical accuracy. Independent scientific review recommends a **dt-only 0.1 ms / 0.05 s /
300-rank** diagnostic against the existing 0.5 ms case before a longer run,
keeping coupling and physics fixed and retaining fields near the spike window.
User steering now prioritizes the one-factor velocity-gradient-limiter case
**G1-ULIM-300-05MS-005** before reducing timestep: same 300-rank/0.5 ms/0.05 s
configuration, only grad(U) becomes cellLimited Gauss linear 1, full endpoint
fields, 30-minute wall/64 GiB per node/6 GiB free-disk floor. Luna prep owns the
case/runner variant; Luna execution owns a fresh versioned native capsule and
submission. **G1 job 14648417 started** 07:54:42 UTC (08:54:42 CET),
with 300 tasks / three nodes / 100 tasks per node / 64 GiB per node /
30-minute wall, no dependency or requeue. Actual nodes are
x1000c0s1b1n1, x1000c7s2b1n1, x1000c7s3b1n0. At 07:56:35 UTC it was in native
setup/decomposePar; case metadata confirmed the limited grad(U) and unchanged
limitedLinearV 1 momentum scheme. No solver result was yet claimed at that
snapshot. The planned-node forecasts changed and are superseded by actual
allocation; no duplicate or smaller-rank job was submitted. Latest G1 snapshot at 07:59:57 UTC: **stopped_with_preserved_evidence**,
91/100 steps through 0.0455 s, after a 6975.25 m/s peak at 0.0445 s triggered
the existing >1000 m/s write-and-stop guard. Solver exit 0/End is an orderly
partial stop, not success. One kFinal solve also failed its declared residual
criterion. G1 is now terminal (Slurm FAILED from the runner's intentional guarded-stop
exit status). Its full 1,688,102,352-byte / 129-member archive was copied locally,
matched the expected archive SHA, passed gzip CRC/member-list and regular-file
size checks, and owned-workspace cleanup completed. Receipt:
`results/runs/rouaix-ulim-g1-20261026/archive-14648417/archive-verification.json`.
Do not classify the limiter as effective from residual or mass closure alone.
The next declared bounded diagnostic is **T1-ORIG-300-01MS-005**, the previously
reviewed dt-only original-gradient 300-rank case at fixed 0.1 ms through 0.05 s,
compared with baseline 14648312. G1 capture and fresh quota checks passed, and **T1 was accepted once as
Slurm job 14648472**. At 08:28:17 UTC it was still PENDING/Priority with unknown
start time and no run directory/allocation yet; requested 300 ranks on three
nodes, 100 per node, 64 GiB/node, 30-minute wall, no dependency/requeue.
The separate source root is
`/scratch/nk_meshapplied/bene/fire-track2-hpc/rouaix-dt01-source-v1-20261026`.
It uses the unchanged frozen G1 code capsule, variant=original; its new case
declaration is separately hashed. Local receipts are in
`results/runs/rouaix-dt01-t1-20261026/`. No parallel CFD or long-run chain is
armed by this dispatch.
The new root is
`/scratch/nk_meshapplied/bene/fire-track2-hpc/rouaix-ulim-source-v1-20261026`;
its 24-file capsule SHA is
`19281933b6de48c5eb3cbcd1a00e610a74472b1b0e5a98d261604356241ff8b3`.
Every staged source hash and the hardlinked immutable input were verified;
80 affected case/runner/queue tests plus Ruff checks passed. The fresh preflight
found PAUSE absent and sufficient quota headroom; no unrelated job was touched.
Local receipts: `results/runs/rouaix-ulim-g1-20261026/`. The dt-only diagnostic
is queued as T1 above; coupling changes belong in a separate case. The analysis report
is `results/runs/rouaix-hpc-morning-20261026/analysis/matched-rank-scaling.json`
(SHA `eff0524c61b753d244ee458c1fec5268ae97566399540dbc8a166709d23cf034`).
The overnight scaling canvas includes all four verified max-speed histories.
Peak full-log interface Co is about 4.37–9.13; r300's final advance gives
bulk/interface maxima 9.7645/4.5624, beyond the narrower .010–.049 window.
The r64 log records intermediate isoAdvection min(alpha) −0.4454 after
conservative bounding; post-step internal fieldMinMax alpha remains nearly
bounded. These are distinct diagnostics, not a stored field minimum of −0.4454.
No velocity clipping has been added. The G1 one-entry grad(U) change can affect
limitedLinearV face weights, viscous stress and realizable-k-epsilon strain/
production terms; do not attribute any response to one of those pathways alone.

The preserved 5090-workstation Rouaix comparator used CPU OpenFOAM, a 2.733M
coarse mesh and adaptive timesteps; it stalled near 3.09428 s with timestep
collapse. The 35.19M fine mesh stopped before CFD and is not a successful
flow comparator. No matched old/new mesh test holds schemes, timestep and
initialization fixed, so the new mesh is a possible contributor, not a proven
cause. Residual convergence is not mesh/time convergence or physical validation.
Do not treat the operational viability flag as an E1 decision.
The current scratch project-ID 30284 quota has 310,324 inodes used (hard
330,000), and 1,057,316,852 KiB used against a 1,073,741,824 KiB soft byte
limit; inode grace is active. Other team workloads remain untouched.

## Mac Rouaix mesh and native HPC qualification

The Mac fine cast-only mesh is complete: 10,099,265 cells (9,936,263 hex,
163,002 poly), nominal 14/56 mm versus the paper's illustrated 16/50 mm.
The 10-core M4 / 24 GiB host used an existing Foundation 13 ARM64 VM configured
with 10 vCPUs and 16 GiB RAM. Castellation took 39m10s; serial full geometry
QA took 7m13s and 13.23 GiB peak RSS. The VM is now stopped for CPU-only
ParaView extraction. Direct SSH worked; multipass exec did not.

Fine native Foundation QA passes all categories except 114,008
concave-or-planar flags. An independent binary-mesh audit reproduced all flags:
maximum outward vertex-plane excursion is 6.224e-15 m, consistent with
coplanar AMR subdivisions and roundoff, not folded geometry. Max aspect 2.022,
nonorthogonality 41.08 degrees, skewness 0.6444; min determinant 0.731.
The clean five-core-file export and nozzle audit are hash-bound: 924 nozzle
faces, area 0.1254655493482296 m2 (−0.157688% from the analytical circle),
area vector +y. Source velocity is unchanged. Evidence:
`results/runs/rouaix-matched-mesh-mac-20261025/final-cast-only-transfer-core/`
and `results/runs/rouaix-mesh-convexity-20261025/`.

Explicit wall layers remain unresolved. Fixed/relative snappy layers and
native wall-cell splitting variants introduced warped cells or bad face-tet
geometry; all are preserved and rejected. Root stopped wall debugging and
selected the qualified cast-only mesh for exploratory resource/timestep tests:
0 added wall layers versus the paper's 5. This is mesh qualification, not E1
or CFD validation. The refinement guide is inferred above the digitized lower
cloud envelope, not a measured centerline; paper 3D region coordinates and
first prism-layer height are unpublished. Figure comparison and ParaView state
are complete, with equal scales and this gap labelled. ParaView and native
counts agree exactly. The pipeline state opens the mesh, non-triangulated
central slice and edges without rendering; comparison evidence is in
`results/runs/rouaix-mesh-comparison-20261025/`.

HPC SSH works through a root-created control master after normal interactive
login. The 22:05 UTC inventory counted 274 scratch + 50 project + 3 tiny HOME
backup entries (327 total across those owned roots), before new queue staging.
The preferred <100 persistent-entry target is not currently met. Lustre project
ID 30284, rather than the global filesystem free count, limits scratch: about
15.7 GiB to its soft byte limit, inode grace active and 19,773 inodes to the
hard limit. No unrelated team files or processes were changed. Project inode quota blocks new files, so bounded native v2512 work uses
checked scratch capacity and packed inputs/results, preferring node-local
unpacked work. Preserve failed attempts in archives; target fewer than 100
persistent entries without a custom filesystem/HDF5 solver format. Native QA
14643825 failed its overly strict CPU guard; 14643832 failed because runtime
fvSchemes/fvSolution were omitted. Both failures are preserved. Corrected
9-member input archive job 14643854 is terminal: native v2512 reports exactly
the same cell count and 114,008 concave-or-planar flags; all other topology
and geometry checks pass. The wrapper correctly records failure of the raw
all-geometry criterion rather than inventing Mesh OK. It took 2m41s overall
(checkMesh 2m19s, 13,076,672 KiB peak RSS), 0.537 allocated core-hours:
requested one task/one CPU, 24 GB; Slurm allocated 12 CPUs due its memory floor.
Independent review confirmed the same native face-plane criterion and the
factor-eight determinant normalization difference. Membership diagnostic
14643873 retained the native set: all 114,008 unique zero-based IDs exactly
equal the independently audited Foundation set (zero symmetric difference).
Root independently decoded both sets and emitted a narrow, hash-bound
exploratory import exception under `qualified-mesh-input/`; the raw failed
check remains intact. No E1 pass follows. No duplicate HPC meshing job was submitted; the later CFD startup trials are recorded below. The initial packed QA snapshot occupied 18 persistent
entries (13 files, 5 directories), 670,352,204 apparent bytes; the membership
attempt adds one packed result, launcher and Slurm log. The older project
tree originally had 172 entries. Thirteen closed metadata folders (123 entries,
1.47 MB regular-file content) were packed and verified in HPC HOME and locally
before their loose copies were removed. Project copy-back still gets EDQUOT,
so the small HOME backup is retained: project 49 + scratch 21 + HOME backup 3
= 73 persistent entries immediately after cleanup, down from 193; subsequent trial and queue staging adds entries. All 49 direct project files and large
run archives are unchanged. Receipts/backups:
`results/runs/komondor-inode-pack-20261025/`. Node-local environment
candidates were Lustre, so QA used scratch fallback and removed its owned
worktree after archive verification; this does not establish whether `/tmp`
has usable local disk.
Shared AI jobs under the same username remain untouched. QA evidence:
`results/runs/rouaix-native-mesh-qa-20261025/`.

A native v2512 CFD preparer imports only a hash-qualified mesh, generates fresh
fields and the p_rgh transform of uniform gauge-static p=0, and declares 0.05 s fixed-step pilots at 1 or
0.5 ms. Actual installed-source/runtime provenance is required; a Docker source
reference is not asserted as the native runtime. The ledger supports explicit
Rouaix source/open patch names with unchanged integration. The native Slurm
launcher and operational guards are implemented and reviewed: one node,
64 ranks, 64 GiB, fixed 1 ms, 50 steps, 20-minute wall limit, CPU-only,
short job name `ml-vof`. Setup and solver children are reaped before packing,
including unexpected-error paths. Stop conditions include PAUSE, nonfinite
diagnostics, speed above 1000 m/s, no time advance for 600 s, 12 GiB remaining
disk and the deadline margin. Native collated output is synchronous, with one
writer. All 139 affected tests passed, plus Ruff/Bash checks. The actual
18-member input archive passed the runner's validation and per-member hashes:
336,471,054 bytes, SHA `8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787`.
The 20-file runtime capsule, source hashes and Git dirty-state receipt are in
`results/runs/rouaix-native-mesh-qa-20261025/native-pilot-capsule/`.
SSH was restored after the user's eduID sign-in. The immutable input and
20-file source capsule were staged and hash-verified on scratch; project-ID
30284 still has about 22 GiB to its scratch soft byte limit and 19,983 inodes
to its hard limit, with grace active. Native pilot **14647683** (`ml-vof`)
was accepted at 20:12:43 UTC: one node, 64 one-CPU tasks, 64 GiB, 20 minutes,
no requeue. It failed before CFD because the installed signal source uses
`.cxx`, while the guard expected `.C`. Its 57 s allocation cost 1.013333
CPU-hours (53.356 s actual CPU), with all evidence archived and workspace
removed. Corrected retry **14647686** reached the solver, then diverged at
the first 1 ms update: Ux residual worsened to 1.372 after 100 iterations,
max speed reached 9.267e7 m/s; the next update FPE occurred in GAMG. This is
not a valid scaling point. Its 789,892,367-byte/108-member result was verified
and workspace removed. Native `min/max(mag(U))` parsing and the auditor's
explicit solver-log path were also corrected in the next live source version;
the archived retry remains unchanged. Independent blocker review prioritizes
upwind momentum at fixed 1 ms versus original momentum at fixed 0.1 ms on
the same mesh, then original 0.5 ms if the smaller-step case is viable. The
runtime is from the frozen capsule; follow-up code edits do not modify it.
Submission and staging receipts are in the native QA run bundle.

User direction: accelerate the logical reproduction sequence using fixed
steps, measured actual-case scaling, and a reason/input/method/result/performance
record for every attempt. Three 64-rank startup diagnostics are now terminal:

- N1 **14647712**, upwind momentum, fixed 1 ms: 10/10 steps through 0.01 s,
  solver wall 113.085 s; allocated job 288 s (5.12 core-hours).
- N2 **14647714**, original momentum, fixed 0.1 ms: 100/100 steps through
  0.01 s, solver wall 708.682 s; allocated job 880 s (15.6444 core-hours).
- N3 **14647739**, original momentum, fixed 0.5 ms: 20/20 steps through
  0.01 s, solver wall 200.9417 s; allocated job 379 s (6.7378 core-hours).
  Slurm COMPLETED, solver exit 0/End, and the in-job ledger passed with
  closure residual −2.6935e-10 kg. The 1,597,487,335-byte result archive passed
  gzip CRC and every member hash locally.

N1/N2 solver children completed, but their raw batch states remain FAILED
because the older audit whitelist omitted the stock failureLocations function
object. Independent, hash-bound supplemental audits passed 10/10 and 100/100
rows, respectively (closure −1.8386e-8 and −2.1316e-14 kg); raw records were
not rewritten. The fixed-controlDict ledger mode checks immutable prescribed
steps against every native printed Time; v2512 omits native deltaT lines when
adjustTimeStep is no. Independent review accepted this narrow extension.
The original 1 ms scheme failure remains preserved and is not retried.
Bootstrap-only failures 14647709/14647710 are excluded from numerical seeds.

The user authorized unattended work until about 06:30 CET on 26 October
(05:30 UTC). The finite Slurm selector chain is **armed**: initial selector **14647791**
completed and submitted CFD **14647793** plus selector **14647794** with
`afterany:14647793`. Exact readbacks confirm 64 one-CPU tasks / one node /
64 GiB / 27 minutes for the CFD case (PENDING on Priority), and one CPU /
1 GiB / three minutes for its selector (PENDING on Dependency). No solver
allocation or completed timing is claimed for this queued case. Seven actual
queue events, including both accepted submissions, passed root's independent
hash-chain verification. The bootstrap selector allocation lasted 14 s on one CPU, with 7.742 s
TotalCPU; its Python controller separately recorded nine elapsed core-seconds.
No duplicate submission occurred. The durable arm receipt is
`queue-stage-v2/arm-receipt.json` in the local deployment bundle
(SHA `0ba2ec37a606c1d900221b28ff1fccdf3be88efc2d565496fe199f2e3579bca7`).
The immutable plan is
`/scratch/nk_meshapplied/bene/fire-track2-hpc/queue-deploy-v2-20261026/overnight-plan.json`
(SHA `939e12a5aa25189f4f29d802483524c8d0a049a42e73b48647806bbd436cf915`).
Local deployment receipts and frozen plan are under
`results/runs/rouaix-native-mesh-qa-20261025/launch/overnight-deploy-20261026/queue-stage-v2/`.
Create `/scratch/nk_meshapplied/bene/fire-track2-hpc/PAUSE` to stop the owned
runner and prevent follow-up dispatch; do not cancel the shared username's
unrelated AI jobs.
The full in-memory adoption of all three actual seeds and next-case budget check
passed before submission; v1 was preserved after its preflight-only historical
retention mismatch, with no sbatch or production state write.
It selects original momentum at fixed 0.5 ms from N3, then a fresh 0.05 s
64-rank case, matched 120/240/optional 300-rank windows, a 0.5 s candidate,
and a checkpointed ~5 s target or bounded partial run. One CFD case at a
time, a 300-rank ceiling, 2700 allocated core-hours, explicit disk limits,
PAUSE and UTC cutoff bound the sequence. No idle node reservation or automatic
adaptive timestep is involved. Compute-to-sbatch and explicit-environment
bootstrap canaries both passed. Source capsules and seed archives are frozen;
new local edits do not change the previous attempts. Diagnostic retention now
recognizes native collated processors64 trees, verified with the real archive
layout and a regression test. All 194 affected tests passed across the HPC,
ledger, native runner, metrics, tutorial and mesh suites, plus Ruff/Bash checks.

Native profiling can measure instrumented pressure-solver scopes, but its
write scope covers only uniform/time rather than full field I/O. Pressure
iterations are counts, and checkpoint-write seconds remain unmeasured. W&B
metrics remain offline until a destination is supplied. The hash-bound N1–N3
summary is `results/runs/rouaix-hpc-metrics-20261025/n1-n3-offline-summary.json`.
These are exploratory
startup results, not E1 validation or evidence of a developed plume.

## Long-horizon sizing and Rouaix direction

The short tutorial's 64-rank full-job winner is not a long-horizon optimum.
A read-only timing-window audit found approximately 2x higher post-startup
physical-time throughput at 300 ranks than 64, with coarse clock quantization
and early-flow/mode/placement caveats. No fine-mesh runtime forecast follows.
For the older 35.19M Rouaix case, use 300–600 ranks as an initial profiling bracket,
including 300/360 on three compact CPU nodes, subject to real memory/startup
qualification. The new 10.10M cast-only mesh starts with the declared 64-rank
resource pilot; the older mesh's bracket is not its measured optimum.
Production ranks remain unselected; the new fine-mesh overnight chain is described above.

Fastest credible progress is a clean-start fine-case resource/stability pilot,
then matched actual-mesh throughput windows, checkpointed extension through
the older ~3.094 s failure region, and source-uncertainty-aware comparison
near the paper's ~5 s development horizon. The older 35M mesh's 0.002 s preparation
is not plume evidence; isoAdvector/upwind turbulence, anisotropic hex cells,
no prism layers and 1.56% nozzle-area deviation remain material differences.
Only E0 passed. Independent read-only source/path review and sizing artifacts:
`results/runs/komondor-long-horizon-sizing-20261025/`. New paper Table 3
consistency notes are in the E1 source record; original PDFs remain unchanged.

User direction, 25 October: retain the available hex/OpenFOAM route and use
the existing reproduction diagnostics to qualify source-like local refinement
and a fixed 1 ms timestep candidate. The 0.1 ms startup setting is not a
selected production timestep. Compare fixed-step candidates on matched clean
states, measuring interface/global Courant numbers, actual equation solves,
extrema, flux closure and observable drift; no automatic timestep reduction
should conceal a failed fixed-step trial. Paper §3.3's 70/50/30/16 mm values
describe four separate mesh-study candidates, not four prescribed nested
bands. Match the fine candidate's illustrated refinement footprint and
directional resolution; unknown region coordinates and first prism-layer
height remain explicit assumptions. No mesh, solver dictionary, queued job or
formal acceptance criterion was changed by this read-only review.
Prior coarse continuation tooling includes fixed 1 ms inputs, but there is no
completed fine-mesh 1 ms result. Keep the first matched timestep comparison
at one alpha subcycle: the existing ledger rejects multiple subcycles because
the exposed `alphaPhi_` is the last-subcycle flux, not a full-step integral.
Multiple subcycles require verified full-step flux aggregation before using
the same conservation audit.

## Komondor wide-rank results, 25 October

- Completed matched tutorial trials: 300 ranks on eight nodes (`14642569`),
  500 on twelve (`14642572`), and 1000 on twenty-four (`14642611`). Fixed
  2,322,432 cells, 50 steps at 20 microseconds through 0.001 s; alpha 0–1,
  water integral 0.0006225782 m3. Source/input/mesh/executable hashes match;
  decomposition varies by rank. No formal numerical gate advanced.
- Default-mode 300/500 solver-step envelopes were 24.205820/32.953254 s,
  whole jobs 290/282 s, allocated cost 24.1667/39.1667 core-hours. The
  completed 1000-rank trial used software receive matching: envelope
  81.311145 s (OpenFOAM ClockTime 24 s), whole job 416 s, allocated cost
  115.5556 core-hours. Keep transport configurations separate in scaling.
  The earlier 64-rank tutorial remains fastest end-to-end at 165 s; this
  does not select production ranks for the 35M-cell Rouaix case.
- First default-mode 1000 (`14642573`) failed before any timestep at CXI/OFI
  endpoint allocation. Paired native MPI probe `14642602` reproduced default
  failure and passed software matching in the same 24-node allocation.
  This supports the scoped workaround, not a universal NIC/RAM diagnosis.
- 1200 ranks were actually allocated on 32 nodes. First software attempt
  `14642612` failed preflight before meshing. A single placement diagnostic
  `14642633` excluded only its primary error host x1000c0s4b1n1. Its exact-
  rank MPI preflight passed, but OpenFOAM then failed at MPI/PMI initialization
  after a 308.443356 s failed step, with zero CFD timesteps. Job elapsed
  509 s; all steps are terminal. No 1200 solver speedup/horizon is valid.
  Stop this retry sequence; preserve all failures and do not blacklist more
  nodes automatically. No simulation or MPI diagnostic remains active.
- Slurm resource interpretation was verified: exact total requested CPU/task
  counts and minimum eight CPUs/node, no fixed tasks/node, no GPU or exclusive
  request. An earlier pending chain and collector were cancelled with zero
  allocation when the per-node task setting became a 120-CPU/node minimum.
  Corrected requests used free fragments and started without the packed
  request's multi-day forecast. No unrelated workloads were modified.
- Collectors `14642578`, `14642614`, `14642641` all completed. Compact evidence
  checksums/CRC and completed source archives were verified. Compute-node
  SlurmDBD was unreachable; raw terminal accounting was recovered from login.
  Completed software manifests lacked Git state; separate provenance notes
  tie source/wrapper/probe hashes to submission records without editing raw
  manifests or asserting whole-working-tree identity.
- Root owns integration/status. Corrected cleanup `14642663` completed in
  190 s with one CPU/1000M, preserving all three failed trees as verified
  archives before source removal. The initial cleanup failed safely before
  touching data; full positive/negative tiny fixtures checked the correction.
  CRC/SHA/ownership and source-identity checks preceded every removal. All
  trial, diagnostic, collector and cleanup jobs are terminal; canonical staged
  launchers/probe/collectors remain. The seven allocated CFD/MPI trial parents
  used 439.89 allocated core-hours including failed starts, excluding tiny
  collectors/cleanup. This is not actual busy CPU time; see
  `allocated-resource-summary.json` in the wide run bundle. All 20 affected
  HPC tests, Ruff/Bash, staged resource/hash, compiled MPI and parser checks
  passed. The scaling view separates transport modes and completed points.
- Protocol: `experiments/HPC_P0_KOMONDOR_TUTORIAL.md`. Evidence:
  `results/runs/komondor-wide-20261025/`, including default collectors,
  `mpi-diagnostic/`, `software-collector/`, `software-ex1-collector/` and
  submission-side provenance supplements. W&B is offline; no publication.

## Komondor overnight results

- All five matched tutorial jobs completed: 8/16/32/64/100 ranks, IDs
  `14641430/14641431/14641432/14641434/14641435`. The fixed workload was
  2,322,432 cells, 50 steps at 0.00002 s to 0.001 s. Solver-step envelopes
  were 182.480876/144.379802/60.653313/29.057098/27.833033 s; whole-job times
  were 341/301/202/165/225 s. Eight through 64 ranks used one node; 100 ranks
  used eight nodes. These are single trials with differing background load
  and decomposition, not a production scaling law.
- At 64 ranks the solver was 6.28x faster than at eight ranks (78.5% relative
  parallel efficiency). The fragmented 100-rank run saved only 4.2% solver
  time versus 64 ranks, while whole-job time grew 36.4% and allocated cost
  grew from 2.933 to 6.25 core-hours. Use 64 as the provisional tutorial
  candidate; measure the actual fine Rouaix case before choosing its ranks.
- Offline collector `14641457` completed in 80 s at 00:19 Budapest on
  25 October (22:19 UTC on 24 October). A SlurmDBD connection refusal prevented
  its accounting/scaling report; solver logs survived. Morning accounting
  recovered terminal job states. Compact recovered evidence is under
  `results/runs/overnight-20261025/hpc/`; original discovery and failed
  attempts remain under `results/runs/komondor-discovery-20261024T203716Z/`.
- At 08:25 UTC the CPU partition reported 21,068 allocated, 1,972 idle
  (including 640 planned) and 512 other CPUs. Idle counts do not establish
  immediately grantable full nodes or measured CPU activity.
- Morning queue inspection found no running or pending jobs from this CFD
  exercise. No full-node or three-node standing allocation was established;
  the finite chain released its resources. The user's preference is to keep
  useful work queued toward three nodes. An ordinary backlog cannot guarantee
  uninterrupted ownership between allocations; a reserved pool requires site
  support. The earlier 500/1000/1200-rank chains were cancelled before useful
  CFD and must not be reported as completed tests.
- Successful scaling cases use synchronous native collated I/O, sparse binary
  fields and verified archives, approximately 442–444 MB each. This is not
  HDF5. The smoke used 102 live filesystem entries before archival, slightly
  above the preferred 100. Use project storage; scratch was already above its
  soft inode limit. Preserve failed cases and transfer compact evidence with
  rsync rather than per-rank trees.
- Native `OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH` supplies interIsoFoam build
  `_87ed40d256-20251219`. CPU nodes have 128 cores/256 GB; account
  `nk_meshapplied` has a shared 5,000-CPU cap, not dedicated capacity. Slurm
  PrivateData hides other jobs/users; allocated cores are not measured busy
  cores. The prior 95 s own-login cohort sample measured 30.716 busy CPU
  equivalents of 365 allocated (8.42%); it is historical, not current global
  utilization. Neither the empty authenticated Grafana catalogue nor hidden
  job rows establishes cluster idleness.
- W&B remains offline because the user deferred its destination. The metrics
  CLI separates solver timing, full-job time, actual CPU time and allocated
  cost. A reconstructed smoke ParaView state and checked fixed scales are
  linked in `docs/HPC_VISUALIZATION.md`. CPU-only state creation/readback
  works; the Mac runtime did not provide OSMesa, so automatic screenshots are
  disabled. A synthetic VTKHDF PolyData round trip passed with field-name
  changes; no CFD HDF5 conversion has been adopted.
- Affected tooling checks on 25 October: 20 HPC tests and 15 native-runner tests passed; Ruff lint/format,
  Bash syntax and the fine-pilot offline self-check passed. The earlier full
  suite had 652 passes, six skips and 14 failures outside the new tooling;
  locked default setup also lacks matplotlib for an existing test import.
  No dependency files changed. Protocol: `experiments/HPC_P0_KOMONDOR_TUTORIAL.md`.

## Goblin fine-mesh pilot

- The 35,190,080-cell anisotropic mesh passed prior full checkMesh and its
  clean-start 20-rank decomposition completed in 115.894 s. It is not an
  exact reproduction of Rouaix's 16 mm mesh: directional source edges are
  11.49/11.49/21.875 mm, with a flat roof and no prism layers. The paper and
  provisional numerics are recorded in `experiments/E1_ROUAIX_FINE_CPU.md`.
- The finite capacity watcher found a quiet interval, but the startup
  container exited 127 at `foamVersion` before mpirun. Run
  `rouaix-fine-35m-startup-20261024T2225Z` is `failed_solver`, ending
  22:12:09 UTC on 24 October. There are zero CFD samples and no measured
  solver memory or conservation result. The unsupported startup helper was
  replaced by a successful pinned-image `interIsoFoam -help` probe in both
  the fine and shared native launchers, with regression checks. PAUSE and
  expiry now take precedence over free-capacity launch checks. The failed
  attempt remains intact; any CFD retry needs a distinct attempt. Morning evidence is in
  `results/runs/overnight-20261025/goblin/`.
- At 08:25 UTC, unrelated Goblin work used about 19.8 of 20 CPUs; available
  RAM was about 118 GiB and disk 177 GiB. The pilot's old service/PIDs are
  gone. Do not infer capacity from yesterday's idle sample or interrupt other
  workloads. No GPU compute/rendering or new CFD retry was launched this morning.
- Root owns status/integration. Luna workers handed off HPC/Goblin audits,
  the scaling view and checked startup/queue-guard repairs. Agent activity
  is not simulation activity. Historical 16 October service/PID claims are
  superseded by the live inspection above; their failed-run evidence and
  published diagnostic videos remain preserved.

## Historical numerical findings

The clean-start air-only diagnostic also showed excessive turbulence quantities
and velocity-solver iteration limits. A matched air-only kFinal/minIter pair
remains an unresolved diagnostic; water-interface appearance and mass closure
do not explain away that anomaly. The 20 October coarse continuation to 1 s
and the fine startup preparation do not establish a remedy for the 3.094 s
failure below. Earlier rendering trials are presentation evidence, not physics
validation or permission for new GPU work.

The baseline stalled at 3.0942804546046 s with deltaT about 1.86e-17 s and
six hours without printed time advancement before manual pause. Its extreme
velocity/pressure growth invalidates the earlier completion estimate. Mass
closure and bounded alpha alone do not establish a credible flow solution.

| Diagnostic | Result | Interpretation |
| --- | --- | --- |
| maxCo 2 -> 1 | Manually checkpointed/stopped at 3.0851454757947256 s; mass guards passed | Did not reach the failure point; no fix established |
| k/epsilon convection -> upwind, maxCo=2 | Timed out at about 3.093817 s after 90 min; deltaT about 1.21e-6 s | Still shrinking timestep; no demonstrated remedy |
| Direct extrema in scalar trial | max velocity about 46,053 m/s, pressure extrema about +134/-262 MPa near x=10 m | Numerically compromised, despite finite fields and mass closure |
| Momentum convection -> upwind only | Guarded stop at 3.0753866640745677 s after velocity exceeded 10,000 m/s; checkpoint and native mass audit saved | Does not repair the already compromised restart seed |
| Active kFinal minIter 0 -> 1, matched one-step pair | 0 -> 2 iterations; relative L2 change in k 4.467%; k-floor cells 22 -> 0 | Actual solver settings materially affect k; convergence and a physical remedy remain unproven |

The scalar trial's k solver took zero iterations in all 1,622 recorded solves;
the sampled baseline at 2.75 s also had zero k iterations. Changing its
convection scheme therefore did not demonstrate evolving k transport. The
review identified linear-solver normalization/stiffness as a diagnostic target.
The sole PIMPLE iteration actually selects kFinal: the first k-only minIter
change was inactive and is preserved as a failed attempt. The corrected pair
in `recovery-rouaix-c4-kfinal-miniter-pair-20261015T2016Z` used the exact same
parent and terminal time 3.07365229458967493 s. Active minIter=1 changed all
2,733,120 k cells, with relative L2 difference 0.04467394; both native mass
audits passed the operational guards. This is sensitivity evidence, not a
convergence result; no model constants or viscosity caps are fitted.

The paper uses limited gradient reconstruction (PDF p. 8 / article p. 7,
section 3.3); our velocity linearUpwind reconstruction uses unrestricted
Gauss-linear gradients. The extreme velocities occur in the coarsened region,
where streamwise cells are 0.5 m long, rather than the nominal 70 mm corridor.
The current mesh is nonuniform: nozzle-plane spacing is about 34.48 mm in x
and 43.75 mm in z (roughly 12 by 9 cells across the nominal diameter), not
six cells across in each direction. Its measured nozzle area is
0.1237068965517 m2, 1.56% below the ideal 0.4 m circular opening. These
local sizes and actual source flux must accompany the nominal corridor size.
This motivates the single-change momentum diagnostic; causation is unproven.
Native sampling at the recovered 3.09328474300641 s checkpoint identifies
the logged peak cell (processor 9/local 85,297) as air: alpha=7.04e-28,
U=(64.5,-9149.96,20771.87) m/s, p_rgh=-1.113 MPa. Its center is
(11.75,-0.18967,-3.56294) m. Exact polygon distances place it 0.02043 m from
spanwiseMinus and about 0.19984 m from aircraftWall. The earlier centroid
distance did not identify the nearest boundary. The later 46 km/s peak has no matching saved field time;
sampling its location earlier does not establish its later local alpha.
This local velocity peak has nut about 3.36e-5 m2/s, so it must not be
conflated with the global maximum nut of about 19 m2/s elsewhere. Source-code
inspection found isoAdvector-derived rhoPhi feeding the momentum equation,
with no obvious phi-versus-rhoPhi substitution defect.

## Historical checkpoints and monitoring

- 3.0735945651412 s: durable 175,954,077-byte archive; exact 1,838-row native
  audit passed both 0.1% operational guards. Finite/bounded, but nearby fields
  already show about 1,229 m/s velocity; this is a recovery-comparison seed,
  not a physically verified initial state.
- 3.0851454757947256 s: maxCo=1 checkpoint archived (176,492,636 bytes), with
  1,070-row native audit passing both guards.
- 3.09328474300641 s: recovered manually from the scalar-upwind RAM case.
  Exact 1,304-row audit passed; incremental residual -6.007469e-6 kg,
  cumulative -0.012080196 kg. Its numerical velocity failure remains.

The scalar trial's automatic audit/capture watchers exited before Docker
created the container: they mistook a missing startup container for completed
work. Thus prior claims that these watchers remained active were incorrect.
The saved candidate was recovered to disk in
`results/runs/recovery-rouaix-c4-upwind-pilot-20261015T1948Z/`.
Startup ordering was corrected in the momentum trial; its direct velocity
guard requested a successful write/stop and checkpoint capture. The fresh
air run embeds its guards in the active dispatcher rather than assuming an
unverified watcher remains alive.
Native ledgers include all seven boundaries, exact closed time prefixes and
parent offsets applied once. Operational guards are not E1 acceptance tests.
Failed logs, snapshots and attempts remain preserved.

## Paper comparison and retained publication

The ten supplied PDFs were reviewed across two Luna reading tasks and primary
source inspection for the user's comparative report. Visually checked the
original Calbrix p.7 equation Lc=sqrt(S) and Shi p.5 Eq.16 transfer criteria
deq<=dthr and xi<=xi_c; extracted text loses these symbols. Calbrix does not
disclose its interface scheme, and Shi does not identify its solver package:
neither HRIC nor Fluent may be inferred from generic terminology. HRIC is
absent from the pinned local source tree; the isoAdvector authors' repository
contains uncompiled legacy HRIC/mHRIC/CICSAM implementations (reviewed tree
b2671915c5f777fc92e9910496f5ca3a1af90f23). Porting is feasible in principle,
but no HRIC implementation was installed or tested and no method was adopted.

Previously published code and compact evidence: `656850f` and `40ac757` on
main. This publication adds CPU recovery findings and selected attempt videos.
`results/summaries/rouaix_20261015/` contains the comparison figure, SI profiles,
nominal-D=0.4 m normalized profiles, hashes and explicitly scoped pilot evidence.
Raw CFD fields, large logs, archives and environments remain ignored.

- [Longer water attempt, 10x playback](../results/summaries/rouaix_20261016_videos/rouaix-long-attempt-10x.mp4):
  saved 2D center-layer and maximum-over-span projections, t=0.4-1.5 s;
  alpha=0.1/0.9 contours. Re-rendered with roof at top and gravity down.
- [Clean-start water diagnostic, 10x playback](../results/summaries/rouaix_20261016_videos/rouaix-startup-diagnostic-10x.mp4):
  seven saved fields from t=0 to 0.15 s, interpolated alpha=0.5 3D display
  surface with two display-only smoothing iterations and +y screen-up.
  This run later stopped at 0.17425 s on velocity runaway; no later motion
  is depicted. Both clips hold saved snapshots without temporal interpolation
  and are exploratory attempts, not validated reproductions. Root inspected
  both final poster images; raw fields and intermediate renders stay ignored.

At 3.0736 s, queried full alpha>=0.1 cloud depth reaches 9.5 m and width
4.86375 m; source-connected alpha>=0.9 core reaches 4.0556 m depth and
0.5523 m width. One selected cloud cell touches the domain bottom. The large
paper mismatch is not a validated physical conclusion: numerical corruption,
detached-cell selection, 70 mm versus 16 mm mesh, unspecified paper sampling
and full/half-width conventions all require resolution. The native whole-field
water-volume integral agrees with the saved inventory within 6.1e-14 m3.

Last full make check: 649 passed, one optional skip and four subtests; Ruff
passed. Three subsequently added source-container inspection regressions also
passed. No shared numerical acceptance criterion was changed.

## Next compute work

The fine-case startup correction is staged on Goblin. Preserve a new attempt
separately and prepare a compact immutable global-mesh/initial-field package
for Komondor. The inspected input is 7,984,888,141 bytes (~7.44 GiB)
in 29 extracted entries; no large transfer or new solver retry has occurred.
Measure native solver memory and throughput before long refined runs or a
300-rank three-node choice. Keep useful bounded follow-ups ready; do not
reserve nodes with idle placeholder work. More cores do not repair the
historical velocity runaway, and no formal numerical gate has advanced.

Plan: `track2_aerial_drop_experiment_plan.md`. Gates: `docs/VALIDATION.md`.
Sources: `docs/REFERENCES.md`. Detailed earlier status is retained in Git history
at `40ac757`; original run evidence has not been removed.


Local diagnostic-metadata correction, 26 October: the final solver-state write
now synchronizes legacy `max_u_seen_m_s` with authoritative
`solver_max_u_m_s`. Previously the first field could remain at the last 30 s
periodic sample (G1: 155.08 m/s) despite the correct final parser/log maximum
of 6975.25 m/s and a correctly triggered guard. The regression includes a late
peak after the last periodic snapshot; 50 runner tests and Ruff passed.
This is a future local wrapper fix only. The G1 and queued T1 remote capsules
remain immutable at runner SHA cf8205ea2e15a0eaf9072516fe06d91f3f3f8f8da0467ec5fb4b2698366b60ac.
No archived raw run-state/log was rewritten.


T1 placement review at 08:24–08:28 UTC: three nominally idle CPU nodes were
DRAIN and excluded. Two eligible MIXED+PLANNED nodes each had 64 idle CPUs;
no eligible node had a 100/120-CPU free block. Explicit 64/120/300 test-only
requests produced inconsistent, week-ahead forecasts that did not establish
an earlier finish than the real T1 job. The submitted 300-rank request remains
unchanged; no speculative duplicate, cancellation or resubmission occurred.
The exact-ID final readback still has Priority-pending / start Unknown.
Receipt: `results/runs/rouaix-dt01-t1-20261026/final-t1-handoff.json`.
