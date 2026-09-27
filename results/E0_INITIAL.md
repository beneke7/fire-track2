# Initial analytical verification

Accepted on 2026-09-24 after author tests, independent scientific review and
orchestrator integration. These are synthetic analytical results, not aircraft
predictions, CFD benchmarks or field validation.

Commands: `make check` and `make e0`.

- Ruff lint and formatting: passed.
- Tests: 19 passed in 2.01 s in the final local integration run.
- E0 report checks: all seven passed.
- Input, output-artifact and recorded code hashes: independently checked and matched.

Local evidence bundle:
[`runs/e0-20260924T215802.780997Z-dfa62db3/`](runs/e0-20260924T215802.780997Z-dfa62db3/).
It contains `e0-report.json` and `ground-map.npz`. The bundle is ignored by Git;
recreate it with `make e0`, which always creates a new directory. Preserve the
original bundle externally if it becomes a cited research artifact.

| Check | Verified result |
| --- | --- |
| Constant inlet | 1200 kg for both velocity vectors with the same normal component |
| Ballistic trajectory | Flight time `sqrt(20)` s; absolute impact time `4 + sqrt(20)` s, with correct x/y translation |
| Deposition and ledger | 8 kg inside map + 3 kg landed outside = 11 kg deposited; zero escaped mass |
| Synthetic strip | L95 = 5 m; useful credit 28.5 kg / 250 kg released = 0.114; actual strip mass 35.625 kg |
| Ellipse/rectangle arithmetic | Full-width lengths 38.2993 m and 61.0865 m, ratio 1.59498; separate from the L95 tolerance definition |
| Zero control | Gain represented as undefined (`null` in JSON) |
| Handoff momentum | Vector sum closes algebraically; no physical conversion is implemented |

The source revision was `5bee7e762775e2ada7b129cb83faf0a3f96feacd` with uncommitted
initialization files. The manifest therefore also hashes the actual source, test,
E0 contract, project metadata and lockfile used. Python was 3.12.3 and NumPy 2.5.3.
The direct source arithmetic differs slightly from Restás's rounded table; see
[the source notes](../docs/REFERENCES.md).
