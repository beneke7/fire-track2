# Live project status

Updated: 2026-10-27 10:21 UTC. Workstation scope: **I4F internal tank-to-nozzle discharge**.
Aerial/HPC work belongs to the separate server agent; see [HPC_STATUS.md](HPC_STATUS.md).
No complete trustworthy CFD discharge, accepted 1.0/0.8 m engineering comparison,
or hardware validation exists yet. The objective remains a publishable provisional
hydraulic calculation with supported engineering conclusions.

## Running now

Both matched **cold t=0** mesh cases saved normal-End checkpoints without
raw pressure-floor contacts, clipping or parser/diagnostic errors. They are
currently stopped; restart infrastructure is being repaired, not a live solver.

| Case | Saved physical time | Reason for capture |
| --- | --- | --- |
| 299,214-cell baseline | 0.2598319592322597 s | Coordinated graceful save for storage/restart recovery; water defect +1.229 g, gas defect −0.0214 g. |
| 323,682-cell corridor mesh | 0.23933195923226194 s | Incremental output allowance reached; normal End. |

Parent run: `results/runs/i4f-cold-mesh-pair-20261027T050932Z/`.
The physical settings remain joint half-weight water/flux updates, full predictor
source, momentum predictor off, SST, finite-water EOS, ideal-gas air, Euler/MULES,
sixteen outer iterations and maxDeltaT=125 microseconds. Neither cold case has
yet reached the earlier failing .51 s region.

Continuation target is .70 s, ten MPI ranks/nine CPU equivalents and 32 GiB per
case, with six-hour save/six-hour-fifteen-minute hard limits per child.
Launch attempts exposed checkpoint-record, inherited cache and GO-identity
handshake defects before any continuation solver steps. Failed attempts remain
preserved. Recovery now reuses independently writable staged inputs only after
lossless archival and full restoration verification of the zero-step attempt;
no new field copy is charged unnecessarily. The recovering controller is under
`results/runs/i4f-coldmesh-continuation-v4-20261027T095800Z/` with its successor
being prepared. Do not infer running compute from a dispatcher or worker alone.
The shared incremental output allowance is 2 GiB, retaining the 16 GiB reserve;
this allowance may require another clean segment before .70 s.

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
This is a conditional crop with a fixed inlet and truncated exterior, and its
seed already differs after the first step; it does not establish a full-system
cure. A new crop seeded directly from the full endpoint is being prepared to
remove that initial-state confound before changing physical/numerical parameters.
Evidence: `results/runs/i4f-local-coupled-replay-to-0525-20261027T095254Z/attempts/attempt003-fpe-banner-filter/analysis/`.
The successful retry ran under UID 1000 and a tested fatal parser that exempts
the benign OpenFOAM trapFpe startup banner; the rejected attempts are retained.

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
output allowance. The mounted 4 TB NVMe has only about 19 GB free; a second
4 TB NVMe and a 12 TB HDD are unmounted and their ownership/use remains
unconfirmed. They have not been formatted or mounted. The two stopped cold-run
logs were losslessly compressed with verified roundtrips, recovering about
1.22 GB without removing restart fields. Lossless closed-log/old-field archives
and exact mesh sharing preserve recoverable evidence. About 1.115 GiB of separately verified generated
reconstruction caches was removed after matching retained native processor
fields; rebuild commands are recorded. Native CFD outputs were not deleted by
that cache operation. See the [archive index](../results/archives/index.json).
Public packets contain compact evidence/source locks; local native meshes and
restart fields remain prerequisites where a packet says it is not standalone.
No new apparatus validation or aerial E0-E6 gate pass is claimed.
