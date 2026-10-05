# Result storage

Generated runs live in ignored `runs/`; the machine snapshot is `machine.json`.
E0 bundles contain analytical checks and a synthetic ground map, not an aircraft
prediction. Preserve each run directory as immutable evidence.

Keep large CFD fields, renders and derived paper text out of Git. Commit concise
reviewed summaries with exact artifact paths/hashes and reproducible commands.
For a result used in a scientific claim, archive its full manifest, source inputs,
checkpoint/solver configuration, raw metrics and uncertainty evidence in durable
storage before relying on a local ignored directory.

The small [one-second Restás visualization](restas-still-air-alpha65-1s-preview.mp4)
is a shareable preview. Current CPU and GPU trial findings, local evidence paths,
and solver-selection research are summarized in
[`VOF_TRIALS_2026-09-27.md`](VOF_TRIALS_2026-09-27.md); full run bundles remain
local and ignored.


Latest inspected videos use cell-to-point interpolated alpha=0.5 geometry:

| Video | Saved physical horizon | Playback | Orientation |
| --- | --- | --- | --- |
| [Corrected horizontal four-slot case](restas-horizontal-alpha50-100ms-100x.mp4) | 0–0.1 s | 100× slower, 11 s including final hold | +x horizontal |
| [Longest available historical case](restas-legacy-downward-alpha50-1s-10x.mp4) | 0–1.0 s | 10× slower, 11 s including final hold | Legacy downward; predates outlet correction |

Each video has matching `.json` provenance and a `.png` final-frame preview.
Both begin with all air and hold the stored snapshots; no intermediate fluid
states are fabricated. They are exploratory water-only fields, without modeled
foam, ground deposition or a paper-validation claim. Rendering commands are
recorded in the adjacent JSON files; raw fields remain local and ignored.

[CL415 pilot diagnostics](cl415-pilot-2026-10-01.json) include actual structure
counts, sampled mass balance, the digitized paper count for context, and the
retained classification-recovery evidence. The assumed-geometry pilot has not
reproduced the published structure count.

The Dash-8 five-second attempt failed at 1.039547 s. Complete checkpoints
through 1.0 s were recovered and inspected. The [smoothed close-up video](dash8-smoothed-alpha50-1s-10x-closeup.mp4)
and [full-domain video](dash8-smoothed-alpha50-1s-10x.mp4) cover 0–1.0 s at
10× slowdown: 1080p, 30 fps, 11 s including the final hold. Each has matching
JSON provenance and a PNG final-frame preview. Surface smoothing changes only
the display; the saved cell fractions and mass diagnostics are unchanged.

The [paper comparison plot](dash8-paper-comparison-2026-10-04.png) and
[comparison data](dash8-paper-comparison-2026-10-04.json) show substantial
discrepancies under provisional geometry and unverified coordinate registration.
These partial, exploratory results do not establish paper reproduction.

The [paper-cloud-threshold video](dash8-cloud-alpha0001-1s-10x.mp4) uses
alpha=0.001 at the same 10× slowdown and full-domain camera. The
[flow audit](dash8-flow-audit-2026-10-04.json) checks saved air/water velocities
and documents the provisional area-times-velocity source calculation.

The newer [smoothed continuation](dash8-restart-alpha50-1p22s-10x.mp4) and
[whole-cloud continuation](dash8-restart-cloud001-1p22s-10x.mp4) reach the
actual saved time **1.219995 s**, at 10× slowdown (13.2 s playback). Root
inspected their first and last frames using the RTX 5090. These combine the
original trajectory and two restart branches; the final branch changes only
the k/epsilon linear solver. The last logged solver time is 1.300022 s, but
no 1.3 s full field was saved. Their JSON records hash the recovery manifest,
which lists the mixed numerical history. The sampled restart mass residual
remains under investigation; these videos do not establish a stability or
conservation pass.

The [completed from-zero run](dash8-fromzero-alpha50-1p5s-10x.mp4) covers
**0–1.5 s** at 10× slowdown (16 s including the final hold). It uses the
candidate k/epsilon linear settings throughout, rather than combining restart
branches. Root inspected the final frame. The alpha=0.5 surface is smoothed
for display; computed cell fractions and fragment counts remain unchanged.
Successful completion over this horizon does not establish paper agreement.

The [uneven-outflow video](dash8-uneven-alpha50-1s-10x.mp4) shows the completed
0–1 s trial at 10× slowdown. Its assumed exit-speed pattern varies across
the opening and continuously over time; the area mean retains the digitized
discharge history. The [uniform/uneven comparison](dash8-uniform-vs-uneven-native-t1.png)
shows the computed cloud and core at 1 s: native cloud counts change from
41 to 45, without a substantial breakup improvement. The [0.5 s mesh comparison](dash8-local-refinement-uniform-vs-reference-t0p5.png)
compares 670,480 and 1,857,796 cells; both retain an attached sheet. The finer
run was still active when sampled. [Preview provenance](dash8-uneven-preview.json)
records source paths, hashes, actual forcing and display assumptions.
