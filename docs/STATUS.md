# Live project status

Updated: 2026-10-27 11:01 UTC. Workstation scope: **I4F internal tank-to-nozzle discharge**.
Aerial/HPC work belongs to the separate server agent; see [HPC_STATUS.md](HPC_STATUS.md).
No complete trustworthy CFD discharge, accepted 1.0/0.8 m engineering comparison,
or hardware validation exists yet. The objective remains a publishable provisional
hydraulic calculation with supported engineering conclusions.

HPC/Rouaix status is maintained separately in [HPC_STATUS.md](HPC_STATUS.md).
At 2026-10-27 12:05 UTC, the 120-rank pre-instability checkpoint job 14669440
is running toward 0.20 s (0.0523 s at the last readback); auditor 14669459 waits
on completion. The old five-second
run failed its speed guard at 0.2628 s; the short upwind comparison completed
only 0.05 s. A four-CPU local all-air diagnostic completed 100 steps on a
299,520-cell mesh. A finite local queue is armed (PID 60998), waiting for shared
CPU capacity before an eight-rank reprofile and measured-cost-gated 0.30 s
matched air pair. I4F jobs are not changed. No new scientific gate passed.

## Running now

Both matched **cold t=0** mesh cases are advancing from clean saved checkpoints
under the repaired persistent V5 controller. Each has ten MPI ranks/nine CPU
equivalents and 32 GiB memory allowance. Exact container identities:

| Case | Container | Verified continuation progress |
| --- | --- | --- |
| 299,214-cell baseline | `cb6f5ac4df2cf773db51bf194a01daa25d09aa9a17e388455f6430ae6315b6f3` | Started 10:35:32 UTC from .259831959 s; 300 steps completed through .297457 s. |
| 323,682-cell corridor mesh | `c7bf540ac23b9dc1dde7fc52add31672b4cffcbbbce7cb579240bd94e8e9fc96` | Started 10:44:17 UTC from .239331959 s; 140 steps completed through .256957 s. |

Both first-step checks have zero raw pressure-floor contacts, clipped mass,
parser errors or diagnostic errors. This early health does not predict survival
through the earlier .51 s failure region. Physical settings remain joint
half-weight water/flux updates, full predictor source, momentum predictor off,
SST, finite-water EOS, ideal-gas air, Euler/MULES, sixteen outer iterations and
maxDeltaT=125 microseconds. Target is .70 s; each child has a six-hour save and
six-hour-fifteen-minute hard limit anchored to its own exact Docker start.

Controller and status:
`results/runs/i4f-coldmesh-continuation-v5-20261027T101135Z/analysis/continuation-status.json`.
Launch failures were infrastructure defects before solver steps: checkpoint
record completeness, inherited generated caches, GO identity/path handling.
Their exact runtime inputs and attempt evidence are preserved. The zero-step
V4 stages were re-used after independent restoration of 1,099 files/814 MB
with hashes and metadata verified; writable scientific fields remain independent.
The corridor's additional wrong-GO-path attempt is retained, and its corrected
attempt003 has actual parsed progress. Baseline was adopted without relaunch.
The guard's branch progress is authoritative; its cosmetic top-level readiness
label can remain stale after GO. The shared incremental output allowance is
2 GiB, with the 16 GiB reserve unchanged. Cleanup has supplied additional margin.

The same 1.0 m geometry is used on both meshes. Corridor adds 24,468 cells
(+8.1774%), retaining 48 source layers/branch and .15 m2 gross mouth area/outlet.
Nine configured quality criteria pass; an additional final allGeometry check is
not claimed. Prescribed cold fields, tank/feed inventories, mapped addressing
and roundtrip checks are recorded. Writable fields are independent; exact
immutable mesh files share verified retained copies. This is a cold-start mesh
sensitivity, not a matched comparison with earlier mid-trajectory restarts.
The separate 317,814-cell 0.8 m alternative now has a modern runtime stage at
`results/runs/i4f-short08-modern-runtime-stage-20261027T0605Z/`, with corrected
x=4.6 m mouth diagnostics and preserved cold inventories. It remains input only;
its nominal diagnostic windows are not conservative native-face flux measures,
and its different mesh is not a resolution-matched accuracy comparison.

## Completed results that guide the work

**Iteration count and the tested timestep cap did not cure the continuation.**
The half-weight eight-outer trial stopped at .518390 s; sixteen-outer at
.517939 s; sixteen-outer with half maxDeltaT at .512059 s. Each saved and ended
on the configured intermediate raw-pressure floor. Final pressure corrections
were still about 5.7-6.1 kPa. These are numerical failures to resolve, not
cavitation findings or complete discharge results. The maxDeltaT change did not
halve every adaptive timestep and does not exhaust temporal refinement.
[Common-time data and separate terminal addenda](../results/summaries/i4f_20261025/physical-pilot-comparison/).

**Bulk hydraulics agree better than the local iteration.** Near .4907 s,
eight/sixteen-outer valve-seat water flow differs .00698%, each tank water volume
about .446 L, despite local convergence problems. Valve-seat flow is internal
transfer, not nozzle delivery. The snapshots differ by 8.62 microseconds.
[Full observed-horizon plot](../results/summaries/i4f_20261025/physical-pilot-spatial-inspection/full-observed-horizon.png).

**The pressure minimum is beside a divider entrance.** Direct binary64 native
reads give 34.026/33.096 kPa in nearly pure water, 3.3-3.4 mm downstream of the
divider STL start; nearest transitional-alpha cell centres are 30-39 mm away.
A mesh-size transition is nearby, so one snapshot does not establish cause.
Native addressing/coordinates were verified; VTK float32 values were qualified.
Some function-object pressure minima differ by about 60 Pa from saved native p;
this observer-stage discrepancy remains unresolved and is recorded separately.
[Inspected cutaways and native verification](../results/summaries/i4f_20261025/physical-pilot-spatial-inspection/).

**One numerical mode is identified, but damping is not a complete remedy.**
At fixed .493844 s, pressure increments alternate with cosine -.999997 and
near-unit norm ratio. Joint half-weight alpha/actual-flux updates suppress that
mode by roughly three orders of magnitude, but water continuity does not thereby
converge. Source reconstructions and actual branch execution are preserved.
[Fixed-state evidence](../results/summaries/i4f_20261025/alpha-flux-relaxation/).

**Restart tests must preserve the timestep context.** A 12 microsecond restart
from the .490707 s snapshot produced raw undershoots in every solver arm.
Using the original next timestep (106.687 microseconds) produced no raw floor
contact and closely reproduced the continuous step's scalar pressure/velocity
updates. Observer-on versus original endpoint files were byte-identical.
Saved rho, phase temperatures and p/p_rgh hydrostatics independently match their
EOS relations closely; gross saved-state inconsistency is not supported.
[Saved-state audit](../results/summaries/i4f_20261025/restart-state-compatibility/).
The natural-step proof is private at
`results/runs/i4f-alpha-source-mass-observer-gap-20261027T044519Z/arms/native-natural-dt-attempt001-20261027T0542Z/`.
It is one-step passivity/scalar restart evidence, not full trajectory equivalence.

**Source-cutoff attribution needs the actual staged coefficients.** The old
endpoint estimate of roughly 76-81% of signed water residual used later dgdt and
approximate density. It is not an exact attribution. The default-off observer
now captures the actual full predictor source; a singular uncapped counterfactual
partition was rejected and replaced by a finite assembly/state-change identity.
[Healthy native execution, source reconstruction and synthetic checks](../results/summaries/i4f_20261025/alpha-mass-budget-observer/)
passed. In that one step the assembly-cutoff term is 94-97% of the final signed
water residual, with exact staged accounting; this is not a causal explanation
of the pressure instability or a retroactive validation of the old estimate.
The completed one-natural-step 1e-4/1e-5 cutoff comparison reduced the signed
water mass residual from -.022006 to -.004957 kg/s (4.44 times), while final
pressure/velocity updates were essentially unchanged. This separates a measured
conservation bias from an unproven pressure-instability mechanism; it supplies
no long-trajectory cure. See [cutoff sensitivity](../results/summaries/i4f_20261025/source-cutoff-sensitivity/).
Live cold-case cutoffs are unchanged. No conservation gate passes by this diagnostic.

**Outlet geometry and flux surfaces are now distinguished.** The independent
[native rim audit](../results/summaries/i4f_20261025/native-control-surface-geometry/geometry_audit.json)
finds four .15 m2 mesh holes matching their STL caps. The zone-boundary control
surfaces have larger projections and do not coincide with the physical mouths.
Their reader now runs directly on processor-only cold checkpoints; a missing
legacy global mesh disables only that optional comparison. Face centres match
the pinned v2512 source. Nonzero water-throughput validation remains outstanding.

The [fully wet branch trials](../results/summaries/i4f_20261025/wet-branch-hydraulic-reference/summary.json)
both diverged: linearUpwind exceeded 200 m/s at steady iteration 186, upwind
at 197. The latter saved and stopped on its declared runaway limit. These
are not physical seconds or accepted pressure/head-loss results. The first
runaway is near the truncated outlet (x=4.794 m), distinct from the full-case
divider-region minimum (x=4.22 m); a shared cause is unproven. The extracted
22,918-cell branch retains the divider entrances and has one connected region,
but 872 concave cells. The audited inlet/outlet signs and hydrostatic law have no gross error; a
SIMPLE-only control also diverged at the same terminal junction. A later
native-face-centre correction of about 6 Pa did not prevent the original
upwind runaway. The two-phase cold-case physical settings remain unchanged.

**Moving the local pressure boundary improves boundedness, not convergence.**
The numerical .30 m extension adds 4,608 cells and a flat outlet while preserving
the original 22,918 cell centres and divider faces. The water-only case and its
continuation reached steady iterations 3,000 and 9,000 without runaway, but
neither met the original SIMPLE convergence criteria. At 9,000, max speed is
about 11.78 m/s, relative flux imbalance 1.68e-7, pressure minimum 5.779 kPa
and apparent head loss 2.082 m. Pressure/head remain unsettled diagnostics.
The minimum is at the full-case divider hot spot. Moving the boundary also adds
walls and cells, so boundary distance alone is not isolated. The native-face
pressure-profile control still diverged at iteration 197.
[Hash-locked comparison and inspected geometry](../results/summaries/i4f_20261025/local-outlet-mitigation/).

**Small two-phase replay now supplies a faster discriminator.** The 22,918-cell
crop maps thirteen cell fields and 64,716 internal face fluxes exactly from the
near-failure parent. One natural step reproduces pressure at the critical cell
within .103 Pa of the full run, although crop-wide pressure differences reach
1.69 kPa near the cut inlet. Its continuation reached .525061585 s normally,
with a 17.435 kPa critical-cell probe minimum, no pressure-floor contacts and no
clipped-water volume. At the full run's .517939363 s terminal time, local probe
pressure is about 19.981 kPa versus 17.279 kPa in the full saved field.
This is a conditional crop with a fixed inlet and truncated exterior.
A second replay seeded directly from the full .490813 s endpoint verified all
thirteen mapped cell fields and both flux fields exactly and also reached
.525061393 s without a floor contact. Crucially, spatial auditing found that
the full-domain intermediate floor/update cells 71998 and 72683 lie OUTSIDE
this selected branch. Thus crop survival cannot reproduce or clear the actual
full-domain hotspots. At nearby .5179 s times, final-outer dp/dU are about
86.6 Pa/.816 m/s locally versus 6,120 Pa/1.631 m/s in the full case; these are
still materially different coupled problems. The full step's worst intermediate
raw minimum was 9.285 kPa/two cells below floor, while its final pass recovered
to 16.090 kPa/zero. Do not equate intermediate updates with saved-field minima.
Next local replay must include an actual offending branch before a remedy sweep.
Evidence: `results/runs/i4f-local-coupled-replay-to-0525-20261027T095254Z/attempts/attempt004-direct-full-seed/analysis/`.
Successful runs use UID 1000 and a tested fatal parser exempting the benign
OpenFOAM trapFpe startup banner; rejected attempts remain recorded.

A read-only companion restores the historical native x-plane reader for the
processor-only baseline: all 53 processor mesh/map files match the retained
global geometry; its .099957 s snapshot has independent field inodes. It reads
1,536 native faces with effectively zero outlet water flux. Provenance:
`results/runs/i4f-native-xcut-companion-20261027T0800Z/companion-provenance.json`.
No nonzero-throughput or exact mass-flux validation is claimed.

## Provisional engineering reference and limits

The [reduced filling-network check](../results/summaries/i4f_20261025/engineering-hydraulic-scale-check/)
uses the same provisional Cd=.7, 1 s opening and native headspace. At .4907 s,
its per-tank seat flow is 1.166 m3/s versus CFD mean 1.202 m3/s (3.06% difference);
water is still accumulating in initially dry lines. First modeled outlet water
arrives around .617/.625 s. The model stops when air can reach the intake crown
at 1.12655 s with .296 m3 remaining in the representative tank. It does not
predict subsequent gas ingestion, complete emptying or a five-second discharge.
Its line geometry differs from native CFD by about 2.9% in dry capacity;
shared assumptions and a closed volume ledger are not experimental validation.

Hardware interpretation remains two .9 m tanks, 1.35 m3 water each, two .3 m
valve branches/tank and four horizontal outlets. The current 1.0 m train has no
added post-rise straight; downstream passages start air-filled, feeds wetted.
Native total initial water is 3.202 m3 including about .502 m3 in feeds, not
2.7 m3 total. Gas headspace is about .2985 m3/tank. Use 12 bar absolute
provisionally, with the gauge convention unresolved. The reported five seconds
is discharge duration, not valve motion. The valve loss/opening and 2% minimum
opening are assumptions; zero-thickness CFD dividers differ from provisional
4 mm CAD display plates. CO2 dissolution, foaming and cavitation are not validated.

Next: compare the matched cold trajectories at common physical times, establish
first outlet delivery, then extend the healthy calculation toward gas ingestion
and full discharge. Check selected time/mesh/domain sensitivities before a
matched 1.0/0.8 m engineering comparison. Hardware measurements remain necessary
for claims about the built system; provisional numerical work can continue.

## Storage and reproducibility

New bounded jobs retain a 16 GiB free-disk reserve plus declared incremental
output allowance. User direction is to leave the unmounted drives alone.
Only the existing mounted filesystem is used.

The user explicitly authorized discarding unnecessary old simulations on
27 October. Cleanup removes oversampled intermediate native fields and
redundant generated copies while preserving inputs, source, compact metrics,
plots/movies, referenced source states and useful restart/failure checkpoints.
Discarded raw intermediates are intentionally not recoverable; the run identity
and retained evidence remain. This differs from earlier lossless compression.
No current 27 October solver/replay data is in the pruning scope.

The completed first pass raised free space from about 19.5 GB to 108 GB while
current solvers continued writing, a net improvement of roughly 89 GB. Removed
output includes oversampled old I4F histories and reconstructed clones, old
Restas intermediate fields, concluded Rouaix control-sweep raw fields and
unselected endpoint archives, old air-only debug histories, and five obsolete
Rouaix intermediate archive payloads. Selected independent seeds/endpoints,
inputs, compact outcomes and rendered evidence remain. Older generated VTP
exports were separately losslessly compressed with verified hashes/restore.
One clone deletion lacks exact inode-level reclaimed-byte accounting; the record
explicitly excludes it from the measured subtotal and retains the overall df
observations. Hardlinked air-history groups were skipped.

[Compact cleanup record](../results/archives/manifests/concluded-experiment-cleanup-20261027.json)
links detailed local manifests, retained states, byte counts and accounting
limits. [Archive index](../results/archives/index.json) now marks the five
discarded payloads unavailable; their previous restore instructions are historical
only. Other indexed lossless archives remain available. The project instructions
now authorize this retention policy for concluded exploratory output, rather
than requiring full histories of every failed variant forever.
No new apparatus validation or aerial E0-E6 gate pass is claimed.
