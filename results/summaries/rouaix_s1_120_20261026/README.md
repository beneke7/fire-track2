# S1 original 120-rank terminal audit — 26 October 2026

Job **14651174** (`S1-ORIG-120-01MS-005`) completed `COMPLETED 0:0` with 120 CPU ranks and 64 GiB requested on `x1000c1s2b0n1`. It reached all 500 fixed 0.1 ms steps through 0.05 s. This is an exploratory result; no E1 decision is made.

A read-only node query reports `CPUTot=128`, `CPUEfctv=128`, partition `cpu`. This is a current host-capacity observation; historical allocation is 120 CPUs per `sacct`.

## Numerical findings

- **Solver and mesh:** OpenCFD `interIsoFoam` v2512 on the 10,099,265-cell qualified native mesh. All 4,001 residual records satisfy configured criteria. The raw log ends with `End` and `Finalising parallel run`; the `trapFpe` enabled banner is normal and not a failure.
- **Speed and Courant:** per-step max speed is 103.293547802 m/s at 0.0497 s; bulk Co max 1.12154115569; interface Co max 0.560172813445. The peak-time 3D field is not in the compact evidence.
- **Water ledger:** 500 rows through 0.05 s; injected 62.582216014882 kg and final inventory 62.582216014892 kg; closure +1.047e-11 kg. This is a water-mass ledger only. `alphaPhi_` is captured before direct alpha snapping/clipping, so the residual has that caveat; no momentum balance is available.
- **Phase bounds:** parser minima are -6.437e-14 (`alpha`) and -1.650e-20 (`alpha.water`), consistent with tiny roundoff; maxima are 1.0. TKE extrema are not exposed by the current parser.

## Resources and comparison

Whole-job elapsed was **00:30:39** (1,839 s), with 61.3 allocated core-hours and 54.127 TotalCPU core-hours. Solver-step wall was **00:27:18** (1,638 s), with 54.6 allocated core-hours and 54.063 TotalCPU core-hours. Parent MaxRSS is blank; `.batch` MaxRSS is 9442664K; solver-step `.0` MaxRSS is 1413592K at task-maximum scope, not node aggregate. The raw `sacct` query also records automatic audit job 14656217 separately.

S1-96 peaked at 103.323474473 m/s at 0.0499 s (96 ranks, CPU128; 2,339 s whole-job, 62.373 allocated core-hours). S1-64 peaked at 103.502606784 m/s at 0.0495 s (64 ranks on CPU64 GPU-capable host, no GPU allocation; 3,681 s, 65.44 allocated core-hours). All three runs share 500 steps and the qualified 10M-cell mesh, but rank count and host size differ; timings are observational, not a controlled scaling law. These scalar peaks do not establish field convergence.

## Archive and evidence

The automatic auditor reports original result-archive SHA-256 `0e2225f58d762cd1785adaf437c67347420d89acdc529d3ac2d0819d67f0801a` and `verified_crc_hash_and_member_list` status. Locally, I verified the compact bundle against its sidecar (89876c31e0254e86a20d5a56f83c9fcacda5239c9ae2568232185cdce75c7666), its nested compact SHA (0f9bbc93a8e2120852af578dc51df873ec5b8ac2e35bd55cb22770a0906eba71), and all 13 selected member lengths/hashes. The full result archive was not downloaded or independently reread; no mesh binary or 3D field was transferred. The original bundle, report, sidecar, raw accounting, and node query are preserved under `evidence/`; see `analysis.json` for hashes and source member inventory.
