# Rouaix P0 base terminal record — 26 October 2026

Job **14652546**, case **P0-BASE-24-46G-01MS-001**, completed with exit code 0 and an `End` marker. The fixed-mesh `interIsoFoam` v2512 run used 24 CPU ranks, one node, a 10,099,265-cell mesh, fixed `deltaT=0.0001 s`, and reached **0.01 s in 100 steps**. All 801 recorded linear-solve entries passed the configured criteria. This is an exploratory startup result, **not E1 acceptance or field validation**.

The logged speed peak was **91.242559 m/s at 0.01 s**. The alpha-bound and phase-fraction diagnostics each have 100 samples. The 100-row water ledger reports 12.516443 kg injected and stored, zero signed escape, and final closure residual **−2.13×10⁻¹⁴ kg**; the audit warns that subsequent alpha snap/clipping can contribute to residual. Logged maxima include `k=193.716 m²/s²` and `epsilon=32,454.421 m²/s³`. The `p_rgh` extrema span approximately **−20,488 to +30,444 Pa**. `p_rgh` is **reduced pressure in Pa, not absolute pressure**; these short-startup extrema have no physical validation here.

## Timing and resources

The solver-step Slurm record (`14652546.0`) reports **00:36:31 elapsed** (2,191 s). The run-state `solver_wall_s` is **2,191.4174056160264 s**. Its `solver_elapsed_s=2,168.697047112044 s` is stale; use `solver_wall_s` and the Slurm solver-step elapsed field for solver wall time. Whole-job elapsed was **00:39:32 (2,372 s)**.

Slurm `TotalCPU` was **14:33:33** at the whole-job scope (about **14.56 core-hours**) and **14:30:29** for the solver step (about **14.51 core-hours**), summed over the allocated CPU tasks. These are CPU-time totals, not wall times. The `.batch` and solver-step `.0` MaxRSS fields are preserved as Slurm reported them: **9,655,132K** and **2,254,608K**, respectively; `.0` AveRSS was **1,308,832K**. There is no aggregate node RSS or cgroup-v2 memory trace, so these values are not presented as a node-total peak. Baseline profiling was disabled; pressure-solver wall share and separate I/O fraction were not measured.

## Preserved evidence

- [baseline analysis](baseline-analysis.json) records timings, convergence, alpha stages, extrema, mass ledger, provenance, and limitations.
- [archive verification](archive-verification.json), [run-state](run-state.json), [Slurm accounting](terminal-sacct.txt), and [the selected-member list](select-members.txt), [remote hashes](selected-member-hashes.remote.txt), and [local hashes](selected-member-hashes.local.txt) preserve the terminal and transfer checks. The remote **1,577,750,282-byte** result archive was hash-verified, but not copied; no full fields are included.
- [solver log](solver.log.gz) is gzip-compressed losslessly. [Its identity record](solver-log-identity.json) compares the decompressed bytes and SHA-256 with the source log and run-state hash.
- [convergence audit](solver-convergence.json), [ledger CSV](ledger.csv), [ledger summary](ledger-summary.json), and [max-speed CSV](max-speed.csv) retain compact raw diagnostics.
- [files.sha256.json](files.sha256.json) records the byte length and SHA-256 of every payload in this directory except the manifest itself.

The archived `experiment.md` still has legacy 1 ms / 50-step text. The active progression declaration, immutable case inputs, manifest, `controlDict`, run-state, and solver log establish this run's 0.1 ms / 100-step / 0.01 s configuration. At the last recorded check (18:43:30 UTC), profile follow-up job 14652548 was still PD/Priority; no profile result is included. No historical input was changed. The source capsule SHA-256 is `b43ba9d9768bd853b53876af47f2366af431113c9c3284cafc736771b2d85692`; its recorded revision is `4c86f017ed1feb3a81620e82cc93766088acee01`, while the run manifest's revision is unknown.
