# P0: four-slot CPU VOF characterization

**Type:** solver and boundary-condition characterization, not an E1–E6 result.
**Solver:** OpenFOAM v2512 `interIsoFoam`, from the locally available
`opencfd/openfoam-default:2512` image. The image ID and all generated inputs are
recorded in each run bundle. **GPU use:** none.

## Declared objective and decision

Confirm that the local OpenFOAM container can build a valid, fully three-
dimensional domain with four distinct time-dependent water inlet patches,
imposed aircraft-frame crossflow, gravity, and a conservative VOF interface.
Measure mesh size, wall time, CPU use, time-step progression, volume ledger,
and surface-output cost. This pilot does not select E1 conditions, validate
breakup, or predict ground deposition.

For this first characterization, `checkMesh -allTopology -allGeometry` must
report `Mesh OK` and the transient must complete without a fatal solver error.
This record was formalized after the solver launch began; therefore the draft
0.5% whole-domain budget in `docs/VALIDATION.md` is **not** a preregistered
acceptance tolerance for this run. The pilot sampled alpha-water volume but did
**not** save per-patch liquid boundary-flux histories. Treat the mass residual
as diagnostic evidence only. Freeze source-event handling, a case-specific
conservation budget, and exact flux diagnostics before the next CFD run. Do not
advance the mesh based on a rendered image.

## Provisional inputs

| Input | Declared value | Evidence class |
| --- | --- | --- |
| Slot count and arrangement | 4, arranged 2 × 2 | Plan assumption |
| Slot dimensions | 1.0 m × 0.15 m each | Upper end of plan's approximate 1.0 m × 0.10–0.15 m assumption |
| Slot edge gaps | 0.05 m along both array axes | Explicit pilot assumption; no paper supplies spacing |
| Slot orientation | Short axis along track; long axis cross-track | Pilot choice; not a measured I4F design |
| Outlet speed | 4.8 m/s normal downward | Constant value from the Calbrix Dash-8 peak, borrowed as a provisional source input |
| Release interval | 0 to 0.08 s; abrupt shutoff approximated by a 0.1 µs table ramp | Pilot window, not a payload-matched drop |
| Inlet area and flow | 0.60 m²; 2.88 m³/s; 2,880 kg/s | Calculated from declared slot geometry, water density and velocity |
| Expected injected mass | 230.4 kg before the 0.1 µs stop ramp | Calculated, not measured |
| Aircraft-frame crossflow | (-50, 0, 0) m/s | Calbrix reference airflow, reused as an idealized condition |
| Water | 1,000 kg/m³; (1.0\times10^{-6}) m²/s | Water-like assumed properties |
| Air | 1.225 kg/m³; (1.48\times10^{-5}) m²/s | Air-like assumed properties |
| Surface tension and gravity | 0.072 N/m; (0, 0, -9.81) m/s² | Water/terrestrial assumptions |
| Turbulence | Laminar solver model | Deliberate pilot limitation at high Reynolds number; not acceptable for final breakup prediction |
| Domain and grid | x = [-7.975, 7.975] m, y = [-3.025, 3.025] m, z = [0, 4] m; 2,081,200 cells | Generated structured mesh; 3 cells across each slot's short axis |
| Simulated time and output | 0.12 s total; 0.02 s surface snapshots; adaptive Δt, max Co 0.5 and alpha Co 0.25 | Pilot settings |

The 2023 Restás paper supports the illustrative 9 m strip and 2.4 kg/m²
coverage target, but does not specify this outlet hardware. The local Calbrix
paper supplies the borrowed 50 m/s crossflow and 4.8 m/s Dash-8 source-speed
reference. Their use here does not create a matched Calbrix or Restás benchmark.

## Resource and output budget

Run up to 16 MPI ranks inside an 18-CPU Docker cap, reserve two host CPUs, cap
the container at 48 GiB, and stop after one hour. Save only solver checkpoints
at the declared 0.02 s interval, an alpha-volume time series, and the computed
VOF interface surfaces. Each attempt gets a fresh ignored run directory and
records solver-image ID, code/input hashes, wall time, resource samples, logs,
and artifact hashes. No generated output may overwrite an earlier run.

## First-run observations

Run `restas-cpu-vof-20260924T222240.919816Z-49f65225` exited successfully at
0.12 s. The generated 2,081,200-cell all-hex mesh passed `checkMesh`; the source
had four distinct patches, with three cells across each 0.15 m short axis. The
case wrote six computed interface surfaces at 0.02–0.12 s. Maximum logged
cumulative continuity error was 2.17e-7. The logged alpha range was
[-2.35e-9, 1.0], consistent with a small lower-bound numerical excursion in the
solver log. The maximum logged global Courant number was 0.5417 against the
configured 0.5; maximum interface Courant was 0.2926 against 0.25. The solver
completed, but these observed exceedances were not captured by the original
report and need investigation before another case is accepted.

After the source cutoff, integrated alpha-water volume plateaued at
0.231019355 m³ at t=0.119177 s. The intended rectangular input integral was
0.2304 m³ (230.4 kg at the assumed 1,000 kg/m³), leaving +0.000619355 m³
(+0.269%) relative to that intention. The difference first appeared when the
adaptive step crossed the nominal 0.08 s cutoff. Since no acceptance tolerance
was pre-registered and the per-patch liquid flux was not saved, this is **not a
passed conservation gate**. The next case must explicitly resolve source timing,
record each slot's liquid flux, and repeat an independently reviewed ledger.

Measured resource evidence: 975.6 s wall time for 0.12 simulated seconds,
16 MPI ranks, 18-CPU Docker cap, 48 GiB memory cap, 5.55 GiB peak among roughly
two-second Docker samples, and 0.443 simulated seconds per wall hour. Sampling
can miss higher peaks. The solver wrote 0.02 s surface intervals with
`alpha.water` and `U`. A frame can be rendered with
[`docs/RENDERING.md`](../docs/RENDERING.md). The immutable run bundle's
`pilot-report.json` contains the machine-readable measurements and hashes; a
compact tracked result summary is in
[`results/P0_RESTAS_CPU_VOF.md`](../results/P0_RESTAS_CPU_VOF.md).
Pressure-solver iteration counts were parsed, but solver-time share and
filesystem I/O/checkpoint time share were not recorded; instrument those before
using this throughput to project a larger mesh. The report reconstructs the 16
initial/configuration-file hashes because the first completion manifest left
its `case_file_hashes` field empty; the runner has been corrected for later runs.

The characteristic slot-width Reynolds numbers are about 7.2e5 for the water
source and 5.1e5 for the 50 m/s airflow, using the declared kinematic
viscosities and the 0.15 m slot width. The laminar setup was a code-path
limitation; these values reinforce that the pilot cannot support a breakup
prediction.

## Interpretation limit

The short box has no aircraft body or wake, flight-height descent, parcels,
ground, foam, evaporation, fire, or post-impact physics. Three cells across a
slot and a laminar model cannot establish mesh convergence or physical breakup.
Even a clean P0 result only releases the next characterization step. The full
Rouaix manuscript is now available, but E1 still requires exact case extraction
and digitized comparison curves; E2–E3 still require paper-derived geometry and
time histories.
