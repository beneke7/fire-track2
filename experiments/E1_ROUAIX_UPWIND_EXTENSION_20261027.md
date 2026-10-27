# Rouaix upwind 0.5 s extension, prepared 27 October 2026

Preparation timestamp: `2026-10-27 10:24:51 UTC`.

**State: prepared only. No Slurm job has been submitted or released.** This
exploratory one-factor diagnostic is ready for the root agent's postmortem and
release decision. Its horizon is **0.5 s**, not 5.0 s.

## Question and interpretation

The independent original-scheme 5.0 s run, job `14650641`, stopped at solver
time `0.2628 s` after its existing operational guard observed
`max|U|=1045.53344847 m/s`, above the 1000 m/s limit. It had advanced 2628
fixed steps and preserved a verified archive. This was a guard stop before the
declared horizon, not a claim that the physical case failed or that 5.0 s was
completed. The matched 0.05 s upwind trial `14651178` completed with peak
speed `96.3851145471 m/s`; its original-scheme 0.05 s comparator `14651174`
peaked at `103.293547802 m/s`.

The postmortem located the final `1260 m/s` velocity and minimum `p_rgh`
together at `(17.444134,-0.056314,3.486171) m`. Relative to the qualified
mesh box (`x_max=17.5 m`, `y_max=0 m`), this is 55.9 mm from the downstream
outlet and 56.3 mm below the top, near the upper spanwise edge; phase at the
point was not measured. The first speed spike was 274 m/s at `0.2341 s`,
followed by a 108 m/s increase one step later; interface Courant exceeded 1
only at the next sample. Boundary interaction is therefore a candidate
alongside advection behavior. The upwind extension is a numerical sensitivity
trial, not a claimed fix or a separation of those mechanisms.

The proposed fresh-start upwind trial asks whether that single momentum
convection change remains bounded while crossing the original run's
`0.2628 s` guard-stop time. It extends the matched upwind horizon to **0.5 s
(5,000 steps at fixed `deltaT=0.0001 s`)**. It is not a restart, a 5.0 s
campaign, a formal E1 benchmark, or evidence of physical validity. No new
original-scheme rerun is proposed in this record.

## Frozen case definition

- Case ID: `EXT-UPWIND-120-01MS-050`.
- Fresh initialization at `t=0`; no mapped or restarted fields.
- Rouaix Case 1 declared conditions remain unchanged: 0.4 m round jet,
  water velocity `(0,-10,0) m/s`, air crossflow `(70,0,0) m/s`, gravity
  `(0,-9.81,0) m/s²`; native OpenCFD v2512 `interIsoFoam`, Cray MPI,
  Euler time integration, one alpha subcycle, original `grad(U) Gauss linear`,
  realizable `k-epsilon`, material properties and boundary conditions.
- Change only `div(rhoPhi,U)` from `Gauss limitedLinearV 1` to
  `Gauss upwind`. Do not add gradient limiting, time-step adaptation, clipping,
  or other scheme changes.
- Fixed `deltaT=0.0001 s`, `endTime=0.5 s`, 5,000 steps, write interval
  `0.5 s`; full initial/final field retention, no intermediate 3D fields,
  profiling disabled. Every-step compact solver and conservation diagnostics
  remain enabled by the existing runner.
- Reuse the 10,099,265-cell qualified mesh archive, SHA-256
  `8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787`.
  It is linked into the owned run directory without copying or changing the
  original inode or bytes.

The mesh is exploratory: its imported `checkMesh` record contains one
`concaveCells` exception and it has no prism layers, unlike the paper's mesh.
The accepted import qualification supports controlled reuse of this mesh; it
does not make the mesh faithful to the Rouaix setup or validate the solver.
Physical inputs are declared model values, not new measurements.

## Allocation and stop behavior

One CPU node, 120 MPI ranks, one CPU per rank, 64 GiB, `cpu` partition,
`normal` QoS, and an 8-hour Slurm cap (`28800 s`; at most 960 allocated
core-hours). The 8-hour cap allows roughly 4.7 hours at the observed short-run
rate plus uncertainty; that projection is not a runtime guarantee. The run
uses the shared `/project` workspace, one thread per rank, and the existing
runner's PAUSE, `max|U|>1000 m/s`, 600 s no-progress, 12 GiB free-space,
checkpoint, Slurm signal and wall-deadline stop guards. It has no automatic
retry or requeue. A guard stop must preserve and audit partial diagnostics;
it must not be reported as horizon completion.

## Inputs and local preparation

Local run directory: `results/runs/rouaix-upwind-extension-20261027/`.
The mesh archive is a hard link to the existing qualified input. A gzip source
capsule contains the 24 members of the 26 October S1 source capsule, refreshed
from the current unmodified checkout, plus this declaration. The authoritative
final snapshot is `source-capsule/upwind-extension-source-v3.tar.gz`, indexed
by `source-capsule/source-capsule-index-v3.json`; retained v1/v2 capsules are
earlier preflight snapshots. The index records member sizes and SHA-256 hashes;
the capsule hash is recorded there to avoid a self-referential declaration
hash.

The frozen runner inputs are `cases/e1_rouaix_hpc/run_pilot.py`,
`prepare_case.py`, `pilot.sbatch`, the unchanged case templates and the
source/declaration material in the indexed capsule. On preparation, the local
runner, preparer and batch-script SHA-256 values were respectively
`024483de8b2825f8c8842b5507602313ba310e1dbe2408d67270d17adfd3c96f`,
`5c0d1382e1f26a6ebd6101c50608fe83125c00e601180a29598200e8818de7f6`, and
`dbccd06f8cfd4b8a5cd3da121e62c58ab13daad4be26af1abe61f21100cb570d`.

`PilotConfig.validate()` accepted 120 ranks / 1 node, 64 GiB, 28,800 s,
0.5 s horizon, 0.0001 s fixed step, upwind, 0.5 s write interval, full
retention, 12 GiB free-space floor, and profiling off. The mesh archive
validator accepted all 18 members. The read-only scheduler admission probe
used `sbatch --test-only` twice and predicted 120 CPUs on `x1000c1s1b0n0`, first
beginning `2026-10-30T21:51:02` and later `2026-10-30T21:59:02`. Slurm printed
forecast job numbers `14668699` and `14668738`; neither is a submitted job ID.
These are forecasts only and created no job or reservation.

## Held submission command

The following is a prepared command template only. Before any submission, the
root agent must stage and hash-check the capsule and mesh under the new shared
project root, create its `logs/` directory, confirm PAUSE is absent, and make
the release decision. Submit held, read back the exact job identity and
allocation, then release only on explicit root direction.

```sh
ssh -S /tmp/fire-track2-komondor-%C -oBatchMode=yes nk_memj@komondor.hpc.kifu.hu \
  'sbatch --parsable --hold --account=nk_meshapplied --partition=cpu --qos=normal --job-name=ml-vof --nodes=1 --ntasks=120 --cpus-per-task=1 --mem=64G --time=08:00:00 --signal=B:TERM@180 --no-requeue --chdir=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-upwind-extension-source-v1-20261027 --output=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-upwind-extension-source-v1-20261027/logs/EXT-UPWIND-%j.slurm.out --export=ALL,ROUAIX_PROJECT_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-upwind-extension-source-v1-20261027,ROUAIX_INPUT_ARCHIVE=/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-upwind-extension-source-v1-20261027/inputs/qualified-mesh-input.tar.gz,ROUAIX_INPUT_SHA256=8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787,ROUAIX_RANKS=120,ROUAIX_NODES=1,ROUAIX_MEMORY_GIB=64,ROUAIX_WALL_BUDGET_S=28800,ROUAIX_END_TIME_S=0.5,ROUAIX_DELTA_T_S=0.0001,ROUAIX_NUMERICAL_VARIANT=upwind,ROUAIX_WRITE_INTERVAL_S=0.5,ROUAIX_CASE_ID=EXT-UPWIND-120-01MS-050,ROUAIX_RETENTION_MODE=full,ROUAIX_MINIMUM_FREE_DISK_GIB=12,ROUAIX_PROFILING=0,ROUAIX_HARD_DEADLINE_UTC= /project/nk_meshapplied/bene/fire-track2-hpc/rouaix-upwind-extension-source-v1-20261027/cases/e1_rouaix_hpc/pilot.sbatch'
```

After the parent is terminal, use the already frozen v3 finished-run auditor
directly in a small one-CPU Slurm `afterany` job. Its script is
`/project/nk_meshapplied/bene/fire-track2-hpc/hpc-finished-audit-source-v3-20261026/scripts/hpc_finished_audit.py`.
Create a separate manifest after the actual parent job ID is read back, with
that ID and this case's source root, 120 ranks, 0.5 s horizon, 0.0001 s step
and case ID. Write its report under a new per-parent directory. Invoke the
frozen script with `--manifest`, `--job-id` and `--output`, using
`cray-python/3.11.7`, one CPU, 1800 MiB and a 10-minute limit. Do not edit or
copy the v3 auditor, reuse its old manifest, or infer CPU accounting if the
compute-node accounting query is unavailable.

## Decision boundary

Interpret the result only as a controlled numerical stability comparison at
the declared mesh and startup inputs. Report actual terminal state, reached
solver time, guard reason, convergence, conservation and diagnostic gaps.
Completion at 0.5 s would not establish Rouaix benchmark agreement, a valid
momentum balance, correct breakup physics, or field performance. The one
concave-cell mesh exception and missing prism layers remain material limits.
