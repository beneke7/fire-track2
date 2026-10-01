# Live project status

Updated: 2026-10-01 16:52 UTC. CL415 reproduction is the top priority.
Only analytical E0 has passed; no quantitative paper or ground validation
has passed. Measured Restás geometry/source histories remain pending.

## Actual compute and priority

The CL415 0.1 s pilot completed 437 steps on 20 ranks: 594,000 cells,
224 s solver clock time, all stages exited zero and mesh checks passed.
Its final sampled mass residual is 0.194 kg / 86.084 kg injected (0.225%).
A startup banner about exception trapping was wrongly classified as a failure;
the check is fixed and retained fields were processed without rerunning CFD.
Original classification and failed analysis attempts remain in the bundle.
[Published compact pilot evidence](../results/cl415-pilot-2026-10-01.json).

The 0.5 s CL415 case is actually running OpenFOAM on 20 ranks, with
3,540,900 cells, standard k–epsilon and static local refinement. At 16:51 UTC
it reached 1.619 ms without an observed fatal error. Local cells are 50 mm,
outer cells up to 200 mm; domain x=[-2,20], y=[-7,7], z=[-21,0] m.
Its 64 GiB allowance and 12 h timeout are launch limits, not runtime estimates.
The earlier waiting attempt was blocked by the false pilot classification and
is retained. The replacement freezes the runner, analyzer and structure-count
module, checks successful pilot diagnostics and uses the pinned Docker image.
[Active manifest](../results/runs/cl415-halfsecond-priority-20261001T165200Z/manifest.json).

The exploratory horizontal Restás 300 ms run was stopped to give CL415
priority. All 20 ranks have verified complete 50 ms checkpoints with hashes;
the last log time is 54.873 ms. No resume is scheduled while CL415 is active.
The original wrapper was absent when inspected; Docker was stopped explicitly,
and its exit code is unknown. This is a recoverable interruption, not a
completed 300 ms result.
[Checkpoint record](../results/runs/restas-hnf-rke-pulse300-dynamic25-20261001T093500Z/manifest.json).

## Reproduction method and next work

Fig. 4 red/top and green/bottom velocity histories are replayed on two assumed
openings each. Four coplanar 0.8 × 0.3 m rectangles, positions, downward uniform
profiles, flat slip belly, numeric air properties, 5% turbulence intensity and
0.05 m length scale remain provisional. Water properties, 50 m/s airflow,
standard k–epsilon and omitted surface tension follow Calbrix. Aircraft CAD
is omitted. Capacity does not establish payload; no source cutoff is invented.
[Source/extraction record](../experiments/E3_CALBRIX_CL415_SOURCE.md).

The structure counter is implemented and exercised on actual pilot fields:
threshold alpha >= 0.001 or 0.9, connect cells across faces, retain single-cell
pieces, report alpha-volume sphere-equivalent diameters and liquid-mass-weighted
velocities. Shared-point counts supply a connectivity sensitivity. Filtering
never removes water from the independent mass ledger. The current adapter is
restricted to a complete conforming Cartesian mesh; it rejects other meshes.
VTK point precision determines a recorded geometry-check tolerance.

At 0.1 s the pilot detects two structures at each threshold. The digitized
paper cloud count is 37 ±5 reading units at that time, so there is a substantial
initial discrepancy. It is not a reproduction success. The paper's unpublished
connectivity, filtering, diameter and velocity weighting cannot be recovered
exactly from its prose. The implementation is inexpensive; resolving geometry,
flow evolution and resolution is the more consequential work.

Next: finish the 0.5 s case, compare penetration/width and count history, inspect
fields, then vary resolution and source geometry without fitting to the count
curve. A new 339-point CL415 Fig. 6(b) penetration trace at 0.5 s is available.
CL415 width curves remain undigitized; Fig. 8 has conflicting 0.5/1 s timing,
and the exit-area convention for normalized curves is unresolved. Quantitative
acceptance needs a declared uncertainty/refinement study and independent review.

## Other findings and published visuals

The matched 12.5 mm AMR/static pair used 1.208/4.570 million peak cells,
4.72/12.64 GiB sampled RAM and 7.66/7.14 h solver time on 10 ranks.
AMR saved about 63% memory but was about 7% slower. Dilute-tail bounds remain
resolution-sensitive; CL415 therefore starts with static refinement.
The SST trial diverged at 30.599 ms after 6.54 h; its root cause is unresolved.
The Rouaix mesh-only probe failed three quality checks; no flow solve followed.

Two inspected smooth water-only videos are published with field/configuration
hashes, actual timestamps and fixed cameras in [results](../results/README.md):
corrected horizontal outlets through 0.1 s at 100× slowdown, and the historical
downward case through 1.0 s at 10× slowdown. Both play for 11 s including a final
hold. They retain the all-air t=0 frame; stored states are held, not temporally
interpolated. Alpha=0.5 surfaces improve display geometry, not CFD resolution.
An optional still-render trial adds inferred density; no foam physics or
calibrated multiple-scattering optics has been implemented.

Both Luna workers have handed off their changes; the actual CL415 process owns
compute. GPU solver work is outside the critical path. Cluster scheduler,
node memory, MPI/container policy and access are unverified. Software checks:
make check passed 345 tests, one optional Docker smoke skipped. The case generator
also passed its affected checks. No E1–E6 acceptance decision was made.
