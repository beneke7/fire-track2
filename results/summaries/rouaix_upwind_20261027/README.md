# Rouaix S1 upwind 120-rank comparison — 27 October 2026

Job **14651178** (`S1-UPWIND-120-01MS-005`) completed `COMPLETED 0:0` with 120 CPU ranks and 64 GiB requested. It reached 500 fixed 0.1 ms steps through 0.05 s on the 10,099,265-cell qualified mesh with OpenCFD `interIsoFoam` v2512. This is exploratory; no physical-validation decision is made.

## Matched-control check

Original job **14651174** has the same input archive, mesh manifest and mesh-file hashes, solver executable, `controlDict`, `fvSolution`, rank count, timestep and horizon. The only numerical dictionary change is `div(rhoPhi,U) Gauss limitedLinearV 1` to `div(rhoPhi,U) Gauss upwind`. Case-input metadata records the scheme and run-local mesh paths; generated `setExprFields.log` also differs. Hash details are in `analysis.json`.

## Results

- **Peak speed:** upwind 96.3851145471 m/s at 0.0500 s; original 103.293547802 m/s at 0.0497 s. Lower peak speed does not by itself mean greater accuracy.
- **Courant and phase bounds:** bulk Co max 1.02016153774 vs 1.12154115569; interface Co max 0.471036191788 vs 0.560172813445. Upwind alpha minima -1.180e-16 / 0.0; original −6.437e−14 / −1.650e−20.
- **Solver and mass residuals:** all 4,001 linear solve records converge in both runs. Upwind maximum final `p_rgh` residual is 0.000566736, vs 0.000290662. Mass closure is -4.784e-10 kg vs +1.047e-11 kg; both inject 62.582216014882 kg. Upwind’s mass residual changes sign and grows in magnitude. The recorded `alphaPhi_` versus snap/clipping caveat applies; no momentum balance is available.
- **Runtime:** whole job 1,896 s (00:31:36; 63.2 allocated core-hours), vs 1,839 s. Solver wall 1692.689 s (sacct step elapsed 1,693 s), vs 1,638.392 s. Different CPU128 node IDs make the timing comparison observational.

## Evidence limits

The native auditor reports original result-archive SHA-256 `8a224b2a075be5b98e7454a5c3b3d96726e55cc9100793d2114208edb6477284` with `verified_crc_hash_and_member_list` status. Locally, the compact bundle sidecar (819753f3a6555a35cb22ba8f043cbe6698b1962c23e3e84812348dd0e98bbe38), nested compact archive SHA (97e6c6e83b74d70c1648d7676ccdc6cd107d052fd2a4ea5ea640a0347c7f4acf), and all 13 selected member lengths/hashes validate. The full result archive was not downloaded or reread; no 3D fields or mesh binaries were transferred. Raw report, bundle, sidecar, `sacct`, and node query are preserved under `evidence/`.
