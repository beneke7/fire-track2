# Rouaix P0 native profiling record — 26 October 2026

Job **14652548**, case **P0-PROFILE-24-46G-01MS-001**, completed with exit code 0 and an `End` marker. The run used `interIsoFoam` v2512, 24 CPU ranks, one node, a 10,099,265-cell mesh, fixed `deltaT=0.0001 s`, and reached **0.01 s in 100 steps**. All 801 recorded linear-solve entries passed their configured criteria. This is an exploratory startup and profiling trial, **not E1 acceptance or field validation**.

The measured solver wall was **2,221.959 s** (`run-state.solver_wall_s`), versus **2,191.417 s** in unprofiled baseline job 14652546: an observed difference of **+30.542 s (+1.394%)**. Whole-job Slurm elapsed was **2,409 s**, versus **2,372 s** baseline. The two jobs ran on different nodes (`x1000c6s0b0n1` and `x1000c6s1b1n0`), so this difference is not an isolated causal estimate of profiler overhead. Scheduler End was 20:29:41 UTC; `run-state.updated_utc` is 20:29:45.926 UTC and is kept distinct.

The output arrays are identical to baseline for the 100-row water ledger, 100-row peak-speed CSV, and 801-record convergence audit (matching SHA-256). Peak speed was **91.242559 m/s** at 0.01 s. Bulk Courant max was **0.95745** and interface Courant max **0.42012**. The ledger reports 12.516443 kg injected and stored, zero signed escape, and final closure residual **−2.13×10⁻¹⁴ kg**; its alpha snap/clipping caveat remains. Logged extrema include `k=193.716 m²/s²`, `epsilon=32,454.421 m²/s³`, and `p_rgh` approximately **−20,488 to +30,444 Pa**. `p_rgh` is **reduced pressure in Pa, not absolute pressure**; the short-startup extrema are not physically validated.

## Native profiling scope

The full archive inventory contains one profiling member: `processors24/0.010000000000/uniform/profiling` (17,761 bytes). That object reports `time.run() caseprocessor0`; no `postProcessing/profiling` summary and no other profiling path are archived. The raw rank-0 `lduMatrix::solver.p_rgh` scope is **850.222 s across 300 calls**. No max/average/min across ranks is available, so this is not a 24-rank pressure timing result. Nested `totalTime` and `childTime` scopes overlap and should not be summed.

The native `objectRegistry::writeObject` scope is only **0.0387 s** for the small `uniform/time` dictionary write, not full field output. Full checkpoint duration and separate I/O share remain unmeasured. Slurm TotalCPU was **14.766 core-hours** for the whole job and **14.715 core-hours** for solver step `.0`; no aggregate node RSS or cgroup-v2 time series is available. Raw Slurm RSS scopes and values are retained without summing.

## Preserved evidence

- [profile analysis](profile-analysis.json) records convergence, alpha/Courant/extrema, ledger, node, wall/CPU/RSS scopes, and limitations.
- [archive verification](archive-verification.json), [run-state](run-state.json), [Slurm accounting](terminal-sacct.txt), selected-member allowlist and remote/local hashes preserve integrity checks. The remote archive was **1,577,764,722 bytes** and SHA-256 verified; only 17 compact files (540,120 bytes) were extracted/transferred. Full 3D fields and the full archive were not transferred.
- [lossless solver log](solver.log.gz), [identity record](solver-log-identity.json), [convergence audit](solver-convergence.json), [ledger CSV](ledger.csv), [ledger summary](ledger-summary.json), [max-speed CSV](max-speed.csv), [native profiling container](native-profiling-container.txt), and executed dictionaries retain compact raw evidence.
- The [`controlDict` diff](controlDict-profiler-only.diff) records the added native profiling block; the mesh, `fvSchemes`, `fvSolution`, and all other prepared-case file hashes match the unprofiled baseline. The `case-inputs.json` hash changes for the profile flag and run-specific path references; `setExprFields.log` contains run-specific paths.
- [files.sha256.json](files.sha256.json) records bytes and SHA-256 for every payload here except the manifest itself.

The case used the same 0.01 s/100-step startup conditions and mesh as baseline. The profile toggle added `active true; cpuInfo false; memInfo false; sysInfo false;` to `system/controlDict`. Revision/dirty state in the run manifest is `unknown`/`null`; the immutable source capsule SHA-256 is `b43ba9d9768bd853b53876af47f2366af431113c9c3284cafc736771b2d85692`, recorded source revision `4c86f017ed1feb3a81620e82cc93766088acee01`.
