# Rouaix local all-air pilot (2026-10-27)

This is the compact audit of the 100-step all-air negative control `ROUAIX-AIR-ORIGINAL-00100`. The raw run and its source snapshots are preserved under `results/runs/rouaix-fast-local-20261027/cases-and-runs/attempt-002/`; the native mesh audit is a prerequisite for this exploratory run, not an E1 grid qualification.

## Outcome

The solver completed all 100 fixed steps to 0.0100 s (exit 0, `End`, `horizon_end`). Maximum native `mag(U)` was 75.641679 m/s; the final value was 75.641438 m/s. `alpha.water` and integrated water volume stayed zero. Bulk Courant maximum was 0.174332; interface Courant was zero. `p_rgh` is the reduced hydrostatic pressure field in Pa and is not absolute pressure.

The solver log reports ExecutionTime 91.26 s and ClockTime 93 s. In the warm t=0.002..0.010 s interval, clock time was 0.9125 s/step; a linear 5,000-step extrapolation is about 75.1 min of solver wall, before full-horizon output differences. The case was not continued to 0.5 s because that exceeds the 30-minute branch. Manual container samples were near 394-398% CPU and 0.96-1.01 GiB cgroup memory of 3 GiB; they are samples, not peak RSS.

## Inputs and execution

- Mesh: 299,520 cells, x-band counts 4/20/18/10/13, y-band counts 5/7/20, and 144 z cells; `snappyHexMesh` refinement was disabled. All seven patches passed, minimum cell determinant 0.00130702, 52 nozzle faces with area error 0.577%.
- Solver: OpenCFD OpenFOAM v2512, build `_87ed40d2-20251219`, cached image sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b. Four MPI ranks, `--bind-to none`, 3 GiB memory limit, no GPU, no network. OpenMPI root opt-in was set only inside this disposable container.
- Exact launch: `.venv/bin/python scripts/run_local.py --threads 1 --timeout 2400 -- python3 results/runs/rouaix-fast-local-20261027/cases-and-runs/attempt-002/run_remote.py solver --case air-a-pilot`.
- Outcome archive SHA-256: `62893a7904cc9d2a91cec747e71dacfc451b50f7fdd6b79685ca0e95ece18d76` (76,330 bytes; 57 regular members), verified against the remote sidecar.
- Git revision `b2d86bab3f716805ec3f33a23b84292ac5c9228a`, dirty tree at run time; exact source, case and mesh hashes are in `analysis.json` and the pre-GO manifest.

## Files

`pilot-timeseries.csv` has 100 rows of field extrema, locations, Courant numbers and water volume. `patch-fluxes.csv` has 100 records for all seven patches and both `phi` and `alphaPhi_`; `fixed-probes.csv` retains both point histories. `solver.log.gz` is a lossless gzip of the raw solver log. `analysis.json` gives the scoped audit, hashes and performance projection. `archive-verification.json` records the extracted-member and SHA boundary.

The run archive did not retain the declared final 0.0100 s processor-field snapshot: the capture selector accepted only 0.25 and 0.5 s. This omission is explicitly recorded; no 3D output is inferred from the compact metrics. The all-air control cannot rule out interface-related instability, and this coarse exploratory mesh does not validate the Rouaix physics.

## Bounded follow-on queue

The active input is an all-air composition control, not a gas-turbulence-matched
case: the unchanged source boundaries retain nozzle `k=0.015 m²/s²`,
`epsilon=0.0107810420 m²/s³` and gas-inlet `k=0.735 m²/s²`,
`epsilon=3.6978974178 m²/s³`. `phi` is mixture-volume flux;
`alphaPhi_` is water-phase flux. The queue preserves both labels and requires
saved U, `alpha.water`, and `p_rgh` fields at every reached declared time plus
the terminal checkpoint. Its inventory lists declared future times separately
when a guard stops early.

At 12:04 UTC, launchd job `com.firetrack.rouaix-fast-q20261027` (PID 60998) was
waiting for capacity before the 8-rank 100-step reprofile. Its latest sample
was 18.336 busy CPU equivalents against the predeclared 11-equivalent launch
threshold; the local, Goblin, and Komondor pause checks were clear. No solver
was active. The finite queue has a six-hour wait budget and stops at a user
PAUSE after requesting an OpenFOAM write-and-stop signal. Its source capsule is
`queue-source-bundle.tar.gz`, SHA-256
`c71f7b089b792a3c5fb72f9af05df304015a7c2ae2b8b42d3936b9a628f9b5a6`.

The existing Mac OpenFOAM VM was started and stopped for a read-only capacity
check. Guest access returned “No route to host”, so guest solver version,
affinity, and free resources remain unknown; no solver ran. The hash-bound
receipt and raw readbacks are under
`results/runs/rouaix-fast-local-20261027/mac-vm-check/`. Current dispatcher,
source, checks, and machine readback hashes are listed in
`handoff-manifest.json`.
