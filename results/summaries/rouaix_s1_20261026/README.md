# S1 one-node startup campaign — 26 October 2026

Four real Slurm jobs replace cancelled pending three-node job 14648472. This bundle records submissions and source identity; no new CFD outcome is claimed.

- 14651174: original momentum scheme, 120 ranks.
- 14651178: matched upwind momentum trial, 120 ranks.
- 14651180: original scheme, 64 ranks.
- 14651185: original scheme, 96 ranks.

The afterany chain runs in that order, at most one short job at once. Each uses one node, 64 GiB, fixed 0.1 ms through 0.05 s (500 steps), the same qualified 10.1M-cell mesh and original Gauss-linear gradients. The upwind case changes only momentum convection. Independent 5 s job 14650641 is unchanged. See [schedule.json](schedule.json), the [active declaration](../../../experiments/E1_ROUAIX_HPC_PROGRESSION.md), immutable pre-submit records and the [fresh scheduler capture](root-current-readback.json).

At 14:11 UTC / 15:11 CET, all five jobs remained pending with unknown start forecasts. The first short job and long job waited on priority; the other short jobs waited on dependencies. No solver state existed. Forecasts are historical snapshots, not guarantees.

The new source supports 96 ranks and explicit shared workspaces; it captures the active progression declaration before case preparation. All 208 affected tests and Ruff passed; the full suite was not rerun. Original source-file hashes are in [the capsule index](source-capsule/source-capsule-index.json); all 24 files match this repository tree. Mesh and result archives remain outside Git. A hardlink reuses the verified input archive without duplicating its bytes.

These startup tests cannot establish developed-flow accuracy or an optimal long-run core count. Lower upwind velocity peaks would not alone prove momentum conservation or correct breakup.
