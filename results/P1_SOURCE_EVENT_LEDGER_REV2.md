# P1 revision 2: source-event and liquid-ledger result

**Decision: passed the frozen P1 revision-2 gates as a provisional source/ledger
diagnostic.** The analyzer and an independent raw-table audit agree. This is not
an E1–E6 benchmark, breakup validation, built-device representation, or field
validation. The historical revision-1 attempt remains failed under its original
contract.

## Run and inputs

Run bundle: `results/runs/restas-source-ledger-20260925T015720.514566Z-8e93eda1`.
It used the approved protocol amendment 1, OpenFOAM 2512 `interIsoFoam`, a
2,081,200-cell mesh, 16 MPI ranks in an 18-CPU Docker cap, a 48 GiB memory cap,
and a 3,600 s solver wall-time limit. The 0.12 s run took 2,200.881 s. Docker
resource sampling recorded a 5.598 GiB peak; peaks between samples may be higher.
All five case stages, the case command, solver, reconstruction, and runner
exited 0. No stop reason, stop error, or resource-monitor error was recorded.

The four 1.0 m by 0.15 m slots, 4.8 m/s source speed, 50 m/s crossflow, and
1,000 kg/m³ water density are clearly labelled provisional inputs. No measured
four-slot geometry or discharge/pressure traces for the built Restás system were
available. The source is held through 0.0795 s, then ramps linearly to zero at
0.0805 s. These assumptions do not become measurements by passing this case.

## Independent results

The auditor recomputed each endpoint flux over its completed interval using
`Δtₙ = tₙ − tₙ₋₁` and `ρ = 1,000 kg/m³`:

| Check | Raw-data result | Frozen limit |
| --- | ---: | ---: |
| Per-slot `alphaPhi_` dose | 57.636 kg | 57.636 kg left-step target, ±0.1% |
| Total `alphaPhi_` dose | 230.544 kg | 230.544 kg left-step target, ±0.1% |
| Difference from continuous analytic dose | +0.0625% | ±0.1% of 230.400 kg |
| Per-slot `phi` reference | 57.564 kg | 57.564 kg right-sampled reference |
| Total `phi` reference | 230.256 kg | 230.256 kg right-sampled reference |
| Net outward liquid across open boundaries | 6.4243×10⁻¹² kg | accounted in ledger |
| Final in-box liquid inventory | 230.544 kg (0.230544 m³) | ledger component |
| Maximum absolute ledger residual | 7.05×10⁻¹² kg | 0.1% of cumulative measured source |
| Maximum global/interface Courant number | 0.23043815 / 0.14366862 | 0.5 / 0.25 |

Each of the seven patch-flux tables and the water-inventory table contains
1,200 aligned rows at 0.1 ms intervals, from 0.0001 to 0.12 s. The ten shutoff
ramp intervals are present. The raw `slot_01Flux` table has the ramp samples on
lines 801–810; at 0.0796 s `phi` is −0.648 m³/s while `alphaPhi_` is −0.720
m³/s, and at 0.0805 s `phi` is approximately zero while `alphaPhi_` is −0.072
m³/s. This matches the approved convention that `alphaPhi_` at endpoint `tₙ`
represents phase transport over the completed interval ending at `tₙ`.

The analyzer reports a maximum residual of 7.1907×10⁻¹² kg; the independent
summation gives 7.05×10⁻¹² kg. The approximately 1.4×10⁻¹³ kg difference comes
from floating-point accumulation order and is negligible relative to the frozen
ledger tolerance. Both show a closed ledger. No separate clipping or interface
snap correction diagnostic was available; those effects remain included in the
residual.

`checkMesh` reports `Mesh OK` with 2,081,200 cells, and the reconstructed final
state is `case/0.120000`. Raw stage exit markers are in `openfoam-console.log`
at lines 203, 322, 537, 55863, and 55925 for `blockMesh`, `checkMesh`,
`decomposePar`, `interIsoFoam`, and `reconstructPar`. The manifest separately
records `case_command_exit_code`, `interisofoam_exit_code`,
`reconstruction_exit_code`, and runner `exit_code` as zero.

## Reproduction and scope

The generated run bundle contains `manifest.json`, `inputs.json`, the complete
solver log, raw patch/inventory tables, and `ledger-report.json`. Reanalyze the
bundle without replacing its saved report with:

```sh
.venv/bin/python scripts/analyze_restas_ledger.py \
  results/runs/restas-source-ledger-20260925T015720.514566Z-8e93eda1 \
  --output /tmp/p1-rev2-ledger-reanalysis.json
```

The frozen 0.1% dose and cumulative-ledger tolerances were unchanged after
revision 1. The independent protocol/code reviewer approved amendment 1 and the
exact launcher/analyzer hashes before this run. The raw-output auditor
independently recomputed the metrics above from all eight raw tables. This pass
qualifies only the source timing and mass accounting of this provisional,
coarse P0 box. It establishes no mesh/time-step convergence, breakup, E1–E6,
aircraft performance, foam, or built-system behavior.
