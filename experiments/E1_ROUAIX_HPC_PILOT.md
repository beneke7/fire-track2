# Rouaix Case 1 fixed-step HPC startup pilot

**Status:** startup attempt **14647683** stopped before CFD at an installed
source-extension check. Corrected retry **14647686** diverged in the first
fixed 1 ms update and failed with an FPE on the next update. Both are preserved.
Subsequent isolated 1 ms upwind, 0.1 ms original and 0.5 ms original diagnostics
completed their solver horizons; see
[`E1_ROUAIX_HPC_PROGRESSION.md`](E1_ROUAIX_HPC_PROGRESSION.md) for those immutable
attempts and the overnight sequence. The cast-only mesh has a narrow,
hash-bound exploratory import exception; it does not create a Mesh OK result
or an E1 acceptance decision. E0 remains the only passed gate.

## Purpose and source

Run one clean-start resource and timestep pilot on the current global mesh at
fixed `deltaT=0.001 s` (50 steps), from `t=0` to `0.05 s`. Measure startup
memory and step cost, whether the current turbulence equations actually solve,
fixed-step stability, and the native water-volume/flux balance. The 50 ms
horizon is only a startup pilot; it is much shorter than the paper's roughly
5 s development run and cannot be compared as a stabilized plume profile.

The benchmark is Rouaix et al. (2023), DOI
[10.1016/j.ijmultiphaseflow.2023.104419](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419).
Source parameters and extraction locations are in
[`E1_ROUAIX_CASE1_SOURCE.md`](E1_ROUAIX_CASE1_SOURCE.md): PDF p. 5/Table 2–3
for properties and Case 1, p. 6/§3.1 for solver/numerics, p. 7/§3.2 for
geometry and boundaries, and p. 8/§3.3 for the mesh study and duration.
Original PDF hash: `624efe9e...cf28446` (full hash in the source record).

| Input | Declared pilot value | Evidence/status |
| --- | --- | --- |
| Nozzle | One circular nozzle, `D=0.4 m` | Reported Case 1; Table 3 |
| Liquid velocity | `(0, -10, 0) m/s` | Reported Case 1; y is upward |
| Air velocity | `(70, 0, 0) m/s` | Reported Case 1; x is crossflow-positive |
| Gravity | `(0, -9.81, 0) m/s²` | Reported; SI coordinate frame |
| Water | `rho=997.6 kg/m³`, `mu=8.89e-4 Pa·s` | Reported Table 2 |
| Air | `rho=1.18 kg/m³`, `mu=1.86e-5 Pa·s` | Reported Table 2 |
| Surface tension | `sigma=0.072 N/m` | Reported Table 2 |
| Turbulence | Realizable `k-epsilon`, inlet intensity 1% | Reported Case 1; initial k/epsilon fields and wall treatment follow the existing case dictionaries |
| Initial water | Internal `alpha.water=0`; source boundary remains prescribed | Fresh air-filled state, no restart mapping |
| Initial pressure | Gauge-static `p=0 Pa`; `p_rgh` from native v2512 `setExprFields`, `hRef=0 m` | `p_rgh=p-rho*g·(x-xRef)`; with all-air initial density, the expression is `1.18*9.81*y` |

The measured nozzle area and oriented area vector must come from an audit tied
to the same five polyMesh hashes used by the mesh manifest. The adapter checks
that the area is within the existing provisional 0.5% geometry rule and the
outward vector points along `+y`. The latest separate cast-only measurement
was `0.12546554935 m²` (about `-0.1577%` from `pi*(0.2 m)^2`); it is not
assumed to be the final mesh's measurement. Use the measured area directly to
report volume flow, mass flow, and downward momentum influx. Do not renormalize
the `10 m/s` velocity to compensate for area error.

## Mesh and solver inputs

The source-like Mac work aimed for nominal 14 mm fine and 56 mm surrounding
spacing with five 1.1-growth wall layers. The current transferable cast-only
mesh has 10,099,265 cells and **zero added wall layers**, while Rouaix reports
five. Fine-guide placement, dimensions, actual local resolution, domain extent,
and first layer height remain inferred or provisional; the source does not
publish exact 3D refinement boundaries or layer height.

Native v2512 `checkMesh -allTopology -allGeometry` reports raw `Failed 1 mesh
checks.` for 114,008 `concaveCells` and does not print `Mesh OK.`. The root-issued
qualification exception binds the five mesh hashes and raw checkMesh log,
checks exact equality of the zero-based native and Foundation 13 flagged-cell
sets, and binds the independent plane-screen report and its source files. It
permits this cast-only exploratory import only; the raw failure is preserved
and no wall-layer claim or E1 pass is made. The preparer rejects any other
failure/count/hash/set difference. The immutable mesh and receipt are in
`results/runs/rouaix-native-mesh-qa-20261025/qualified-mesh-input/`.

Use pinned OpenCFD v2512 `interIsoFoam` with isoAdvector, static mesh,
variable-density water/air and realizable `k-epsilon`. The exact current fine
case dictionaries were read-only copied from Goblin and hash-checked in
[`cases/e1_rouaix_hpc/source-provenance.json`](../cases/e1_rouaix_hpc/source-provenance.json):

- Momentum convection is `limitedLinearV 1`; `k` and `epsilon` convection are
  `upwind`; gradients are Gauss-linear.
- Momentum uses PBiCGStab/DILU. `nAlphaSubCycles=1` and
  `nOuterCorrectors=1` remain unchanged.
- `kFinal minIter 1` is already present in the current `fvSolution` and will be
  preserved. A separate historical `minIter 0` attempt printed zero `kFinal`
  iterations; that diagnostic is not this case. Active `minIter 1` changes the
  solve and is recorded as an existing input choice, not a formal remedy for
  the unresolved turbulence anomaly.
- The paper used HRIC and second-order-upwind convection. This diagnostic uses
  OpenCFD's isoAdvector plus the inherited schemes above, so it is not a
  controlled reproduction of the paper numerics or an E1 pass.

The single nozzle boundary imposes `alpha.water=1` and `(0,-10,0) m/s`;
the gas inlet uses `(70,0,0) m/s`. Existing Case 1 open-boundary and wall
conditions are retained. The native ledger accounts for `nozzle` as the
source and `gasInlet`, `downstreamOutlet`, `bottomOutlet`, `spanwiseMinus`,
and `spanwisePlus` as open boundaries. `aircraftWall` is monitored as a
no-slip leakage diagnostic and excluded from escape only under the verified
impermeable-wall check.

## Time controls, observables, and resources

The case uses fixed physics, initial fields, decomposition, and boundary
conditions. Time stepping is fixed: no adaptive time step, no alpha
subcycling above one, and no silent retry or time-step reduction. Full binary
fields are written only at the requested end time; the supplied `0/` fields
are the initial state. Compact measurements run at each solver step:

- `volIntegrate(alpha.water)` plus signed `alphaPhi_`/`phi` sums on the nozzle,
  open boundaries, and wall diagnostic.
- `alpha.water` and velocity-magnitude extrema.
- Standard native log lines for global/interface Courant numbers, pressure and
  momentum equation iterations/residuals, `ExecutionTime`, and `ClockTime`.
- Native runner resource samples for CPU and memory. Samples are periodic and
  may miss the true peak; a sampled maximum is not a peak-RSS guarantee.

Initial resource budget: one node, 64 MPI ranks, 64 GiB memory, 20 minutes
wall time, and one BLAS/OpenMP thread per rank. These are provisional until the
startup measurements are reviewed. No GPU is requested. The runner records the
allocation and measured free disk in `run-state.json`; it stops if available
disk falls below the declared 12 GiB floor. The final `solver_wall_s` value is
measured from monotonic start through the reaped `srun` process.

Stop and preserve the attempt on `PAUSE`, nonfinite solver diagnostics,
`max|U| > 1000 m/s`, no strictly increasing printed physical time for 600 s,
free disk below 12 GiB, OOM, or the 20 minute deadline. These are operational
failure guards, not accuracy tolerances. The runner monitors per-step
`fieldMinMax` U magnitude and requests the configured write-and-stop signal 12
only on its verified Slurm step. It escalates to TERM/KILL only against that
same verified step. It packs each attempt and verifies CRC, hash, and member
list before removing an owned node-local workspace. Failed attempts are not
restarted or overwritten. A zero solver exit counts as complete only when the
log proves all 50 fixed 1 ms steps through `0.05 s` and contains OpenFOAM's
`End` marker; any shorter successful prefix remains a preserved partial run.

## Prepared-case interface

The primary publishes a compact `mesh-input/` archive containing the qualified
manifest, nozzle adapter, preserved raw audit, unchanged native checkMesh log,
five polyMesh files, and bound exception evidence. The runner verifies the
outer archive hash, CRC, exact file inventory, receipt hashes, and raw nozzle
audit hash before preparation. A manual case preparation command is:

```sh
.venv/bin/python cases/e1_rouaix_hpc/prepare_case.py \
  --mesh-dir "$MESH_DIR/constant/polyMesh" \
  --mesh-manifest "$MESH_MANIFEST" \
  --nozzle-audit "$NOZZLE_AUDIT" \
  --output-dir results/runs/rouaix-e1-hpc-dt1ms/case \
  --ranks 64 --memory-gib 64 --timeout-s 1200 --delta-t-s 0.001
```

The pilot launcher accepts only `--delta-t-s 0.001`. The preparer fails closed
on a mesh hash mismatch, non-qualified/non-v2512 QA, cell-count/log mismatch,
unbound or additional native check failures, concave-set ID mismatch, stale
nozzle audit, wrong patch inventory/orientation, or area deviation above
0.5%. It imports only the five hashed native polyMesh files, copies fresh
fields and the exact solver dictionaries, runs native `setExprFields -time 0`,
and freezes input hashes before decomposition and solver launch.

The case bundle declares `execution_backend: slurm-native` and
`solver_version: v2512`; `reference_image_digest` identifies only the source
hash reference. It does not claim that Komondor runs in Docker. The primary
will use the site-native Slurm/OpenFOAM launch path and raw ledger CLI with
matching native source/runtime evidence. The case-owned
`collect_native_provenance.py` helper captures the loaded module, installed
solver source hashes, executable and banner inside the allocation, and binds
that identity into the run manifest. The verification is an installed-source
and runtime correspondence record, not a bit-reproducible binary proof. Do not
use Docker-managed `scripts/run_native_vof_case.py` on Komondor. The one-case
launcher is `cases/e1_rouaix_hpc/pilot.sbatch`; it requests one node, 64 tasks,
64 GiB, 20 minutes, no GPU, no exclusivity, and no requeue. It is prepared for
root review; the first staged/submitted instance is recorded below.

## HPC execution record: 14647683

**Why:** establish native startup correctness, actual memory and step cost on
the new 10.10M mesh before choosing ranks for a longer run. The earlier 2.32M
tutorial and older 35.19M Rouaix case do not supply this mesh's scaling law.

**How:** clean start; 64 MPI ranks on one node, one thread per rank, requested
64 GiB and 20 minutes, fixed 1 ms through 0.05 s. Physics and diagnostic
dictionaries are those declared above. There is no adaptive timestep,
automatic smaller-step retry, GPU, exclusive node request or requeue.
The scheduler also routes the short request to `cpu-short`. Initial requested
TRES are `cpu=64,mem=64G,node=1,billing=64`; allocation/placement are recorded
from actual readback, not inferred from that request.

**Frozen evidence:**
`results/runs/rouaix-native-mesh-qa-20261025/native-pilot-capsule/source-capsule-index.json`
records the 20-file source capsule, exact per-file hashes, Git revision and
dirty state. `qualified-mesh-input-archive.json` in the same parent run records
the 336,471,054-byte, 18-member input archive and its SHA-256. The qualification
receipt preserves the native failed criterion and exact set comparison.
Submission receipts and staged archives are under
`/scratch/nk_meshapplied/bene/fire-track2-hpc/rouaix-e1-hpc-stage-20261025/`.
The minimal runtime tree uses the sibling `cases/`, `scripts/` and
`experiments/` paths expected by the launcher; the capsule index names every
file. This tree is not changed while its job runs.

**Measured outcome:** bootstrap failure, zero CFD timesteps. The source guard
expected `sigStopAtWriteNow.C`; this installation supplies
`src/OSspecific/POSIX/signals/sigStopAtWriteNow.cxx`. The native source has the
required `stopAtWriteNowSignal` and `Time::saWriteNow` tokens. This is a
launcher portability defect, not an observed CFD instability or mesh failure.
The job ran for 57 s on node `x1000c7s2b1n1`, allocated 64 CPUs/64 GiB. Parent
Slurm TotalCPU is 53.356 s; allocated CPU time is 3,648 s = 1.013333 CPU-hours.
The batch-step MaxRSS is 6,582,488 KiB; no MPI solver-step RSS or throughput
exists. Serial setup occupied the allocation; its CPU utilization is not a
CFD scaling measurement. The 350,371,917-byte result archive (51 members) passed
CRC/member/hash verification before workspace removal. Result SHA-256:
`9853c80e2713c1eee66317080f6754abcd52a345d20a9c80e7cae51279a7be95`.

Local evidence: `outputs/failed-14647683/` and
`launch/pilot-20261025T2008Z-64r-1ms/job-14647683-terminal-accounting-readback.txt`
under `results/runs/rouaix-native-mesh-qa-20261025/`.

## HPC execution record: 14647686

**Why:** test the originally declared pilot after correcting the observed
bootstrap defect, with no numerical or resource change.

**How/difference from 14647683:** derive a new source capsule from the frozen
parent, changing only the source-file extension `.C` to `.cxx` in
`run_pilot.py`. The other 19 runtime files, mesh/input archive, 64-rank
placement request, 1 ms fixed step, 0.05 s horizon and 64 GiB/20-minute limits
are unchanged. The actual installed source was read and hashed before
resubmission: SHA-256
`5571278a48efd49507546d9ac4aa419519010d5a2de822992d53e287761a7a03`.
The corrected guard was exercised read-only against that installation. New
capsule hashes, exact diff and submission readback are preserved separately;
the failed parent and original capsule remain immutable. The scheduler first
reported Priority, one node/64 CPUs/64 tasks and 64G, with no requeue.

**Measurements/outcome:** pending. Preserve queue/submit/start/end timestamps,
actual node/rank/CPU/memory allocation, setup/decomposition and solver elapsed
times, per-step physical-time throughput, native Courant/extrema/iterations,
ledger residuals, end-write/packing bytes and elapsed time, terminal Slurm CPU
time/MaxRSS and allocated core-hours. Missing instrumentation is marked missing;
pressure iterations do not measure pressure-solve seconds. A 50 ms pilot cannot
establish developed-plume accuracy or long-horizon stability.

## Decision rule

This pilot selects only whether the fixed-step cases can start, advance,
preserve compact diagnostics, and fit the measured single-node budget. It has
no plume-accuracy tolerance, mesh-convergence tolerance, or validation pass.
Review solver stability, actual equation iterations, Courant histories, mass
closure, write time, and sampled memory before declaring any longer run.
