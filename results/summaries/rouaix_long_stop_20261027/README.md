# Rouaix L1 original long-run postmortem — 27 October 2026

Job **14650641**, case **L1-ORIG-120-01MS-5S**, did not complete its requested 5 s horizon. The operational U guard observed **1,045.533 m/s at t=0.2625 s** and sent signal 12. The run-state preserves that stop reason. The solver then wrote its final diagnostics, reached `End` at **t=0.2628 s / step 2628**, and the solver step exited 0. Slurm records the **parent job as FAILED, exit 1:0**. The failed job is preserved as failed; the solver End marker does not turn it into a successful 5 s run. Coverage was 0.2628/5 = **5.256%**.

## What the time series shows

The maximum speed remains below **103.294 m/s through the first 0.05 s** (peak 103.294 m/s at 0.0497 s). Bulk Courant first exceeds 1 at **0.0136 s** (1.00417), well before the later speed surge. At **0.2341 s**, maximum U briefly jumps to **274.286 m/s** at `(1.138268, −1.959313, 0.894597) m`, processor 82, then drops to **108.079 m/s** on the next sample. Interface Courant first exceeds 1 at 0.2342 s (1.36922).

A distinct, monotone maximum-speed ramp begins near **0.2511 s**: it passes 150 m/s at 0.2542 s, 200 at 0.2568 s, 500 at 0.2610 s, and the guard threshold at 0.2625 s. The guard sample is at `(17.444134, −0.056180, 3.525281) m`, processor 10; the final logged maximum at 0.2628 s is **1,260.038 m/s** at `(17.444134, −0.056314, 3.486171) m`, processor 10. The final minimum `p_rgh` occurs in the same recorded cell.

The parent-confirmed qualified mesh bounds are `x=[−2.5,17.5]`, `y=[−10,0]`, `z=[−8,8] m` (checkMesh log line 96). The positive-span boundary is the sloping plane `z = 3.5 − 0.45y` (from parent inspection of `mesh-input.json` and `blockMeshDict`), rather than a rectangular `z=8 m` wall at all heights. Both late-ramp points lie about **55.9 mm upstream of x=17.5** and **56.2–56.3 mm below y=0**. The guard point lies on the positive-span plane to the printed coordinate precision; the final point lies **39.2 mm inside** it. This makes downstream/top/positive-span boundary adjacency a candidate for follow-up, not a proven cause. Local alpha at either recorded velocity maximum was not captured. The first transient spike is at a different point and its `p_rgh` minimum is elsewhere.

The per-step audit has **21,025 linear-solve records, all converged**, with zero failed records; `p_rgh` accounts for 7,884 solves and 46,246 total linear iterations. Logged peaks include `epsilon=498,332.2 m²/s³` at 0.0706 s, `k=1,631.98 m²/s²` at 0.1614 s, `nut=3.6764 m²/s` at 0.2608 s, and `p_rgh` from **−89,913 to +67,148 Pa** at 0.2628 s. `p_rgh` is reduced pressure in Pa, not absolute pressure. Converged linear solves do not remove the observed local high-speed instability.

The mass ledger covers all 2,628 steps through 0.2628 s. It records **328.932 kg injected**, **328.753 kg final inventory**, **0.17923 kg signed net escape**, and **1.20×10⁻⁵ kg closure residual**. At 0.05 s, 62.582 kg is injected and stored with effectively zero escape. The global phase-1 volume fraction at the stop is **1.4328×10⁻⁴**. This is substantial retained mass in the partial ledger, but it does not establish that the full domain was filling or that accumulation caused the local U spike. The ledger records the post-flux alpha snap/clipping caveat.

The solver's conservative-bounding diagnostic reports a transient `alpha` minimum of **−0.00134051 at 0.2281 s**; this recovers to round-off scale by 0.2341 s. For `alpha.water`, the auditor and solver phase line agree on **−1.55559×10⁻¹⁰ at 0.2067 s**. The `alphaExtrema` fieldMinMax file reports a minimum of 0 at every written time, including 0.2067 s. The small difference between the solver log/auditor and fieldMinMax outputs remains unresolved.

## Resources and next comparison

Slurm wall time was **9,380 s** for the whole job and **9,166 s** for solver step `.0`. TotalCPU was **12-15:20:39** (303.344 core-hours) at the job scope and **12-15:15:03** (303.251 core-hours) for the solver step. These hierarchical CPU totals are not added. Parent MaxRSS is blank; `.batch` MaxRSS is `9440696K` and solver-step `.0` MaxRSS is `1447244K`. `.0` AveRSS is retained raw as `308295714` without a unit suffix. There is no aggregate node RSS or cgroup time series; the saved `sstat` readback reports a persistent-connection failure.

The evidence supports the planned matched **upwind momentum-convection** trial through 0.5 s at fixed 0.1 ms and 120 ranks as a one-factor diagnostic. It can test whether the sustained surge is sensitive to the current `limitedLinearV 1` momentum scheme. At the observed average of **3.488 solver seconds per step**, a fresh 0.5 s run extrapolates to **4.844 solver wall-hours**; completing the remaining 2,372 steps from this run's stop extrapolates to **2.298 additional hours**. This is a linear estimate, and step cost may change in the later flow regime. Keep the downstream/top/positive-span boundary and local phase at the max-U point on the follow-up inspection list. A 0.5 s run would not establish longer-horizon stability or E1 validity.

Matplotlib was unavailable in both `.venv/bin/python` and system `python3`; no package was installed and no figure was produced.

## Preserved and verified evidence

- [postmortem analysis](postmortem-analysis.json) records the timing, locations, Courant and alpha onset, solve audit, ledger, Slurm scopes, and interpretation limits.
- [archive verification](archive-verification.json), [native auditor JSON](audit.json), [run-state](run-state.json), [selection](selection.json), [terminal sacct](sacct-14650641.txt), member lists, selected hashes, and [compressed-source identities](compressed-source-identities.json) preserve provenance and transfer checks.
- The native audit bundle SHA-256 was verified against its sidecar. Its nested compact archive SHA-256 matched `selection.json`; all 13 selected files (12,038,865 bytes) passed remote and local SHA-256 checks. Two additional small `failureLocations` and `alphaExtrema` files were extracted by exact member path from the original archive and matched their remote SHA-256 values. No full result archive or 3D field was transferred.
- The solver log, full 2,628-row mass ledger, max-speed trace, and per-step `failureLocations`/`alphaExtrema` tables are losslessly stored as `.xz`. [files.sha256.json](files.sha256.json) records byte length and SHA-256 for every payload in this directory except the manifest.

This is an exploratory partial run, not a successful 5 s completion, an E1 result, or a validation pass.
