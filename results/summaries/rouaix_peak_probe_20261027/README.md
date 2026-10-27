# Rouaix 14650641 final peak-cell probe

This zero-simulation diagnostic reads the final retained checkpoint at **t = 0.2628 s**. The native auditor places the max-|U| cell on processor 10 at `(17.44413407821, -0.05631406956444, 3.486170872067) m`, with `|U| = 1260.037732681 m/s`, with `U = (50.707591, -470.220468, -1167.911186) m/s` in the case frame (x crossflow+, y upward+, z spanwise+). The same coordinate is the native `p_rgh` minimum.

The bounded U header identifies OpenFOAM v2512 `decomposedBlockData`, binary `LSB; label=32; scalar=64`. A read-only streaming extraction selected only processor 10 blocks for `U`, `alpha.water`, `p_rgh`, `k`, `epsilon`, and `nut` from the verified original result archive. The six arrays each contain 83,526 processor-local cells. The existing repository parser decoded those blocks; local `U` argmax and `p_rgh` minimum both occur at zero-based cell index 83,525. Their values reproduce the native `|U|` maximum and `p_rgh` minimum.

At that final peak cell, `alpha.water = 3.1934980037034703e-143` (effectively zero stored water fraction), `p_rgh = -89,913.416 Pa` (reduced pressure), `k = 0.7650391 m²/s²`, `epsilon = 4.761711 m²/s³`, and `nut = 3.521549e-5 m²/s`. This phase value is for the final checkpoint only; it does not identify the phase at the earlier guard trigger at 0.2625 s or explain the spike. The run stopped at 0.2628 s of a requested 5 s horizon; no validation gate is claimed.

## Evidence

- `analysis.json` records decoded values, validation checks, field-block hashes, and source hashes.
- Ignored raw evidence is at `results/runs/rouaix-fast-local-20261027/peak-probe/`: `processor10-fields.tar`, `U-file-header-2048.bin`, `extraction-manifest.json`, and `peak-diagnostic.json`. The tar contains only the six processor-10 field blocks and the extraction manifest.
- Archive source and native verification: `results/summaries/rouaix_long_stop_20261027/archive-verification.json` (original archive SHA-256 `bcd35bef1fa8ec47ff28aadf0cc3f19de41c144ce95d14ff9c90dc2a52a49cec`; the archive was not re-transferred).
- Decoder source: `src/aerial_drop/i4f_native_face_reader.py`, reusing `_COLLATED_FIELD_RE` and `_parse_internal`; no new binary decoder was added.
