# Live project status

Updated: 2026-10-27 08:43 UTC. Workstation scope: **I4F internal tank-to-nozzle discharge**.
Aerial/HPC work belongs to the separate server agent; see [HPC_STATUS.md](HPC_STATUS.md).
No complete trustworthy CFD discharge, accepted 1.0/0.8 m engineering comparison,
or hardware validation exists yet. The objective remains a publishable provisional
hydraulic calculation with supported engineering conclusions.

## Running now

Both matched **cold t=0** mesh cases are advancing under their exact guards.
They use the same executed physical candidate, joint half-weight water/flux
updates, full predictor source, momentum predictor off, SST, finite-water EOS,
ideal-gas air, Euler/MULES, sixteen outer iterations and maxDeltaT=125 microseconds.
Each has ten MPI ranks/nine CPU equivalents and 32 GiB memory allowance.

| Case | Exact container | Latest independently checked state |
| --- | --- | --- |
| 299,214-cell baseline | `085ceade2df3e31537459037420080bdcc3f53144e7c7de795ac6d900c29a6be` | Running; t=0.192457 s, 1547 completed steps, last completed-step pressure correction 0.003749 Pa; 0 diagnostic and 0 parser errors, 0 raw floor contacts. |
| 323,682-cell corridor mesh | `cb6dc7256e876ede52ee2e78b27b520d160bc359f533efa57038b9c0b6479ef8` | Running; t=0.189832 s, 1526 completed steps, last completed-step pressure correction 0.0040836 Pa; 0 diagnostic and 0 parser errors, 0 raw floor contacts. |

Baseline StartedAt 05:56:04 UTC; corridor StartedAt 05:47:27 UTC. Each targets
.65 physical seconds with six hours to save and another fifteen minutes hard
limit, anchored separately to its own Docker start. These are targets, not ETA
promises. At the 07:25 UTC observed throughput, a linear projection gives about
.38 s after six hours and roughly ten hours to .65 s, before any later slowdown.
Thus the existing wall budget does not presently cover the intended endpoint;
continuation/resource planning must account for this. Current early health does
not predict survival through the failing region.

Run root: `results/runs/i4f-cold-mesh-pair-20261027T050932Z/`.
The bounded PAUSE-aware dispatcher `i4f-coldmesh-pair-dispatcher-r002.service`
adopts exact running identities and captures native endpoints. It uses allocated
CPU quotas plus measured unrelated CPU use rather than a misleading MPI-process
count; admission examples were tested. Both guards and the dispatcher survive
agent exit. A cold-start deadline-variable scoping bug stopped attempt 001
before GO; its scripts/hashes and terminal identity are preserved. Cold and warm
guard startup paths were mock-executed before attempt 002. No physics input changed.

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
but 872 concave cells. Boundary/mesh interpretation is being audited before
another discriminating trial. Both live VOF cases remain unchanged.

The bounded continuation service
`i4f-coldmesh-continuation-20261027t073946z.service` is armed and waiting for
both exact parents' clean normal-End checkpoint captures. It targets .70 s,
with new six-hour save/six-hour-fifteen-minute hard limits per child and an
absolute controller deadline of 23:01:30 UTC. Parent failures or PAUSE hold
queued stages; this is a restarted continuation with preserved lineage, not
bitwise trajectory equivalence. Its config and thirteen execution-source files
were independently hash-checked; no child has launched yet.
Status: `results/runs/i4f-coldmesh-continuation-20261027T073946Z/analysis/continuation-status.json`.

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
output allowance. Lossless closed-log/old-field archives and exact mesh sharing
preserve recoverable evidence. About 1.115 GiB of separately verified generated
reconstruction caches was removed after matching retained native processor
fields; rebuild commands are recorded. Native CFD outputs were not deleted by
that cache operation. See the [archive index](../results/archives/index.json).
Public packets contain compact evidence/source locks; local native meshes and
restart fields remain prerequisites where a packet says it is not standalone.
No new apparatus validation or aerial E0-E6 gate pass is claimed.
