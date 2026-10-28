# Rouaix early-save native smoke v3

Built from the immutable v2 early-save capsule; only `run_pilot.py`, its runner tests, and private v3 path strings in the early-save Sbatch changed. The v3 archive contains 20 members; all 20 remote SHA-256 checks passed.

The saved checkpoint time fixture passed `validate_checkpoint_time`; importing the capsule runner and `config_for_variant("original-early-save")` confirmed start 0.2 s, horizon 0.202 s, fixed 0.0001 s step, 0.002 s write interval, 120 ranks (3 × 40), 22 GiB/node, and 1200 s wall. Diagnostic terminal reason is `diagnostic_early_save_after_3_steps`.

Native job 14700599 was submitted held, read back with 3 nodes/120 tasks/40 per node/22G per node/20 minute limit and v3 source paths, then released. One-CPU auditor 14700602 is held until `afterany:14700599`, was read back, then released. Last status: see `current-state.txt`.

The helper implementation separately passed actual owned-step signal probe 14700561 (signal 12 accepted, SIGUSR2 receipt and acknowledgement before `srun` returned). V2 native job 14700456 and audit 14700457 remain preserved as the prior no-ack attempt.

Artifacts: `early-save-source-v3.tar.gz`, `source-capsule-index.json`, `source-sha256sum.txt`, `preflight.json`, held/released Slurm readbacks, and audit manifest/batch script.

The duplicated local unpacked source tree is retained in ignored local preparation storage; the verified 20-file capsule is the published recoverable source. Python bytecode caches are excluded from publication. The active remote source tree is unchanged.
