# Rouaix healthy-seed 0.2 s case, declared 27 October 2026

Declaration timestamp: `2026-10-27 10:51:27 UTC`.

**Current state (27 October 11:41 UTC): submitted and running as 14669440;
afterany auditor 14669459 is armed.** The preparation snapshot below is the
pre-submission declaration preserved in the frozen source capsule. Submission,
release and timestamp corrections are recorded in
`results/summaries/rouaix_healthy_seed_20261027/`; the template below is historical. This fresh
original-scheme run is a short checkpoint seed for later matched restart
branches. It is a new diagnostic, not a rerun or continuation of the failed
5.0 s job.

## Objective and stop point

Prepare a clean `t=0` solution through `t=0.2 s` at fixed `deltaT=0.0001 s`
(2,000 steps). The endpoint is before the known `0.2281 s` alpha event,
`0.2341 s` internal velocity spike and `0.2511 s` corner growth. A verified
`0.2 s` checkpoint could seed later matched restart branches from one common
original-scheme history. Do not construct a restart/continuation framework in
this run.

The checkpoint is a candidate donor, not presumed healthy. The terminal audit
must verify the actual reached time, archive and input hashes, convergence,
conservation and diagnostic gaps before later branches reuse it. If the
2-hour stop occurs before `0.2 s`, preserve the captured partial checkpoint
and classify it as partial; do not label it an exact `0.2 s` seed.

## Frozen case

- Case ID: `HSEED-ORIG-120-01MS-020`.
- Fresh fields at `t=0`; no restart, mapped fields, clipping or fitting.
- Native OpenCFD v2512 `interIsoFoam`, Cray MPICH, one node, 120 MPI ranks,
  one CPU per rank, 64 GiB, `cpu` partition, `normal` QoS.
- Rouaix Case 1 declared model inputs remain unchanged: `D=0.4 m`, water
  inlet `(0,-10,0) m/s`, air crossflow `(70,0,0) m/s`, gravity
  `(0,-9.81,0) m/s²`, Euler integration, one alpha subcycle, realizable
  `k-epsilon`, existing boundaries/materials and PIMPLE settings
  (`nOuterCorrectors=1`, `nCorrectors=3`).
- Keep the original momentum convection `div(rhoPhi,U) Gauss limitedLinearV 1`
  and `grad(U) Gauss linear`; no profile instrumentation or gradient
  limiter.
- Fixed `deltaT=0.0001 s`, `endTime=0.2 s`, `writeInterval=0.2 s`.
  Preserve collated full fields only at `t=0` and `t=0.2 s`; keep the
  runner's compact per-step solver, extrema, Courant and ledger diagnostics.
- Use the existing 10,099,265-cell qualified mesh archive,
  SHA-256 `8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787`.
  It has one documented `concaveCells` qualification exception and lacks the
  paper's prism layers. Reuse does not establish Rouaix mesh fidelity or
  numerical/physical validation. Inputs remain declared model values, not
  measurements.

## Wall limit and guards

Request `02:00:00` (7,200 s), at most 240 allocated core-hours. The measured
120-rank original startup took about 1,638.5 solver seconds for 0.05 s;
linear scaling to 0.2 s gives about 6,554 solver seconds. Adding about 200 s
for setup/decomposition projects roughly 6,754 s (1 h 52 min 34 s), leaving
about 446 s before the wall cap. This is a throughput-based projection with
little margin, not a guaranteed completion time; queue wait is separate.

Keep the existing PAUSE, nonfinite, `max|U|>1000 m/s`, 600 s no-progress,
12 GiB free-space, checkpoint, signal-escalation and wall-deadline guards.
No automatic retry or requeue. Use the shared `/project` workspace with
`ROUAIX_REQUIRE_SHARED_WORKSPACE=1`; inspect quota and free-space headroom
before release. This run has no GPU allocation.

## Frozen source and mesh

The local prep directory is
`results/runs/rouaix-healthy-seed-20261027/`. The mesh input there is a
hardlink to the qualified archive; its source bytes and inode remain
unchanged. The final indexed source capsule contains the current runner,
preparer, templates, S1 source set, focused tests and this declaration.

Code SHA-256 at preparation:

- `cases/e1_rouaix_hpc/run_pilot.py`:
  `40451793b20fb7365dc7a691f16557ce349719735295f7aa2ffddb1ba7f4d21a`
- `cases/e1_rouaix_hpc/prepare_case.py`:
  `d117fa7d0a08ccbadb1dc38c515a0f55f1a9dde6812d689d8458a4c506c2e7dc`
- unchanged `cases/e1_rouaix_hpc/pilot.sbatch`:
  `dbccd06f8cfd4b8a5cd3da121e62c58ab13daad4be26af1abe61f21100cb570d`
- unchanged `cases/e1_rouaix_hpc/source-provenance.json`:
  `947a39931ceb724795f1305194ae6309aa3216730baf231b8bebc4df2896e751`

The full capsule digest and all member hashes are in its adjacent index; the
capsule hash is kept out of this member to avoid a self-reference.

## Held submission template

This command is prepared, not executed. Before any submission, stage and
hash-check the indexed capsule and mesh under the new project root, create its
`logs/` directory, check PAUSE, quota and allocation identity, and wait for the
root agent's decision. Submit held, read back the exact job/resources, then
release only when the root agent directs it.

```sh
ssh -S /tmp/fire-track2-komondor-%C -oBatchMode=yes nk_memj@komondor.hpc.kifu.hu \
  'sbatch --parsable --hold --account=nk_meshapplied --partition=cpu --qos=normal --job-name=ml-vof --nodes=1 --ntasks=120 --cpus-per-task=1 --mem=64G --time=02:00:00 --signal=B:TERM@180 --no-requeue --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027 --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027/logs/HSEED-%j.slurm.out --export=ALL,ROUAIX_PROJECT_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027,ROUAIX_REQUIRE_SHARED_WORKSPACE=1,ROUAIX_INPUT_ARCHIVE=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027/inputs/qualified-mesh-input.tar.gz,ROUAIX_INPUT_SHA256=8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787,ROUAIX_RANKS=120,ROUAIX_NODES=1,ROUAIX_MEMORY_GIB=64,ROUAIX_WALL_BUDGET_S=7200,ROUAIX_END_TIME_S=0.2,ROUAIX_DELTA_T_S=0.0001,ROUAIX_NUMERICAL_VARIANT=original,ROUAIX_WRITE_INTERVAL_S=0.2,ROUAIX_CASE_ID=HSEED-ORIG-120-01MS-020,ROUAIX_RETENTION_MODE=full,ROUAIX_MINIMUM_FREE_DISK_GIB=12,ROUAIX_PROFILING=0,ROUAIX_HARD_DEADLINE_UTC= /project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027/cases/e1_rouaix_hpc/pilot.sbatch'
```

## Terminal audit handoff

After the parent job ID is read back, create a separate external v3 auditor
manifest with that ID, source root
`/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027`,
120 ranks, horizon `0.2`, step `0.0001`, and this case ID. Submit one native
`afterany` auditor using the frozen script
`/project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-source-v3-20261026/scripts/hpc_finished_audit.py`
with `--manifest`, `--job-id` and `--output`, under a new per-parent report
directory. Use one CPU, 1800 MiB and a 10-minute cap. Keep the new manifest and
reports outside the frozen auditor source and CFD source capsule. Do not
invent CPU totals if compute-node accounting is unavailable.

This is an exploratory seed only. It is not an E1 acceptance decision, a
validated long-horizon solution or evidence of field performance.
