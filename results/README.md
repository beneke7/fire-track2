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
