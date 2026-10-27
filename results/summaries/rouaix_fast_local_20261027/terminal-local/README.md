# Terminal local all-air inspection

This compact addendum audits three terminal attempt-003 all-air runs. It does not change or replace the existing frozen summary. Exact measurements, per-file provenance and SHA-256 values are in `analysis.json`; original archives, logs, case inputs and snapshots remain under the ignored raw run paths recorded there.

## Results

- `air-a-pilot-8rank` completed its 0.0100 s / 100-step pilot (8 MPI ranks, 0.0001 s fixed step), with exit code 0 and an `End` marker. Its maximum recorded `mag(U)` is about 75.642 m/s at 0.0099 s, on processor 6 near (0.225, -0.1750, 0.02485) m. `alpha.water` minimum and maximum are both zero in all 100 extrema rows.
- `air-original-030` reached 0.1752 s of the requested 0.3 s, after its 1000 m/s guard tripped at 0.1751 s (1091.294 m/s). The orderly guard stop wrote the terminal snapshot and exited with code 0 and `End`. The recorded global `mag(U)` peak is 1364.7435 m/s at 0.1752 s, on processor 7 near (17.42308, -0.02503, 3.48688) m. All 1,752 `alpha.water` extrema rows are exactly 0/0.
- All three archives contain 86 regular files; each actual archive SHA agrees with its sidecar, run-result receipt, and archive-verification receipt. All three snapshot inventories pass and include terminal `U`, `alpha.water`, and `p_rgh`.
- Both cases use 8 ranks. Solver `ClockTime` was 36 s for the pilot, 630 s for `air-original-030`, and 695 s for `air-upwind-030`; start-to-archive-complete container wall was about 56.1 s, 647.1 s, and 718.0 s, respectively. All three used 8 ranks. There is no 4-rank comparator, and resource sample arrays are empty, so this is not a rank-scaling result or a measured CPU/RAM comparison.

The longer run's velocity-guard event occurs with no water present in any recorded cell. That supports only the bounded statement that this coarse all-air control can reach the configured guard. It does not establish the cause of a spike in a water-containing or differently resolved case, and it is not E1 validation.

The matched same-mesh `air-upwind-030` run later became terminal: it tripped the 1000 m/s guard at 0.1959 s (1031.096 m/s), wrote a terminal snapshot at 0.1960 s, and exited 0 with `End`. Its peak was 1221.6763 m/s near (17.42308, -0.02503, 3.48688) m on processor 7. All 1,960 recorded alpha.water extrema rows are 0/0. The upwind momentum scheme delayed this coarse all-air guard event relative to limitedLinearV by 208 fixed steps (0.0208 s), but did not prevent it. Same-mesh inputs and the comparison are hash-bound in `analysis.json`; this does not establish a fine-grid cause or physical validity.

These are not an 8-vs-4 comparison: all three were 8-rank launches. The pilot and the .30 s horizon cases have different endpoints, and the longer cases ended at guard triggers, so the wall numbers above are execution records rather than controlled performance estimates.
