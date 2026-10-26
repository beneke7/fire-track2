# S1 original 96-rank terminal audit — 26 October 2026

Job **14651185** completed `0:0` on `x1000c4s5b1n0` with 96 CPU ranks and 64 GiB requested. It reached all 500 fixed steps (`deltaT=0.0001 s`) through `0.05 s`. This is an exploratory startup, not an E1 acceptance or field-validation result.

A read-only Slurm node query reports `CPUTot=128`, `CPUEfctv=128` and `Partitions=cpu` for this host; that is the host profile, while this job used 96 allocated ranks. Capture: `results/runs/rouaix-s1-96-terminal-20261026/scontrol-node-x1000c4s5b1n0.raw.txt` (SHA-256 `d2927a2c39da4bdafdb10f52ae96163f190f6bd115aea50f6c9ba58f38569960`, captured 2026-10-26T20:43:04Z).

## Findings

- **Solver:** OpenCFD `interIsoFoam` v2512, original momentum scheme, 10,099,265 cells. All 4,001 recorded linear solves satisfy their configured residual criteria. No parsed fatal/divergence marker.
- **Flow diagnostics:** maximum speed 103.323474473 m/s at 0.0499 s (peak-time 3D field not retained); bulk Co 1.131209104 at 0.0499 s; interface Co 0.533645775 at 0.0490 s. The `alpha.water` fieldMinMax object reports [0,1] for all 500 samples; the log parser separately sees minima of order 1e-12 below zero.
- **Water ledger:** 500 matched rows to 0.05 s; injected 62.582216014881666 kg, final inventory 62.582216014892133 kg, closure +1.0466e-11 kg. This is a mass ledger, not momentum closure; its alpha-flux/clipping caveat is in `analysis.json` and the raw ledger summary.
- **Turbulence/reduced pressure:** per-step extrema are retained. `k` peaks at 1072.42 m²/s², `epsilon` at 320811 m²/s³, and `nut` at 0.976262 m²/s. `p_rgh` spans -20488.4 to 30443.8 Pa; it is reduced pressure, not absolute pressure. These extrema are not interpreted as physically valid here.
- **Resources:** whole job 00:38:59 (2339.0 s), allocated 62.373 core-h and accounted TotalCPU 56.630 core-h. Solver step wall 2140.708 s and TotalCPU 56.568 core-h. Parent MaxRSS is missing; `.batch` MaxRSS is 9446824K, while solver-step MaxRSS is 1469532K per task, not node aggregate.
- **Comparison:** peak speed is -0.179132 m/s versus S1-64 (103.502606784 m/s at 0.0495 s), and +0.029927 m/s versus prior T1-120 (103.293547802 m/s at 0.0497 s). The three short cases share 500 steps, 0.1 ms and the qualified mesh, but use 96 ranks on a CPU128 host, 64 ranks on a GPU-capable CPU64 host without GPU allocation, and 120 ranks on a CPU128 host. Runtime and peak-scalar agreement do not establish field convergence or a controlled scaling law.

The 1.712 GB remote archive SHA matched its sidecar and run-state; actual `tar -tzf` returned 0 and the normalized 130-entry listing matched the saved member inventory. Only 32 allowlisted compact files (3.1 MB uncompressed; 416 kB compact transfer) were extracted. No full archive, mesh binaries, or 3D fields were transferred. Lossless `solver.log.gz` identity is verified in `solver-log-identity.json`.

The archived `attempt/experiment.md` still opens with an older 1 ms/50-step pilot description. The frozen S1-96 record, manifest, `controlDict`, run-state and solver log agree on 0.1 ms/500 steps. See `analysis.json` for hashes, exact accounting scopes, mass/momentum limits, all per-step extrema, and evidence paths.
