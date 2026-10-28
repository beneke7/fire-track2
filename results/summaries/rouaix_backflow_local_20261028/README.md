# Rouaix local backflow sensitivity — 28 October 2026

This is an exploratory CPU pressure/backflow sensitivity, not an E1 gate or a
validated boundary-condition correction. The candidate changes only the four
open `p_rgh` patches from `prghPressure` to gravity-aware `prghTotalPressure`
(`p0 uniform 0`, `rho rho`, `U U`, `phi phi`, `value uniform 0`). Their
`pressureInletOutletVelocity` conditions and tangential velocity remain as in
the matched baseline.

## All-air result

The fresh all-air `air-backflow-030` case completed 3,000 fixed steps at
`deltaT=0.0001 s`, reaching `t=0.3000 s` with `End`, exit code 0, and no trigger
of its 200 m/s operational guard. It used eight MPI ranks on the existing
299,520-cell mesh. The final recorded maximum speed was 75.7689 m/s; the run
peak was 85.0362 m/s at 0.0366 s. `alpha.water` and integrated water volume
remained exactly zero. The archived initial and terminal snapshots passed
inventory checks. The 29,755,705-byte archive matched its remote SHA-256
(`08f640429749e2816e67ec0563afe8e61582e5cc4fc883ecf9a16d2d7d1d1f8b`).

The historical original-scheme static-pressure baseline and this candidate
share raw records through `t=0.1752 s`. Before its old 1000 m/s guard event,
the baseline had maximum speed 144.526 m/s at 0.1700 s while the candidate had
76.209 m/s. The baseline guard recorded a trigger at 0.1751 s and 1091.294 m/s;
its terminal speed at 0.1752 s was 1364.743 m/s. The candidate stayed near
76 m/s at the same raw times. Pressure extrema also diverged strongly. The
full numeric receipts and guard metadata are in
[`matched-time-comparison.json`](matched-time-comparison.json); full candidate
diagnostics and provenance are in [`air-result-summary.json`](air-result-summary.json).

This demonstrates strong sensitivity to the pressure treatment in this
coarse setup. It does not show that the candidate is physically correct, paper
matched, or validated.

## Water-nozzle sibling

The conditional `air-backflow-water-030` branch was released only after the
all-air run crossed 0.20 s with finite diagnostics, maximum speed below
200 m/s, and valid baseline/source/input checks. It is a fresh bulk-air case
whose nozzle alpha patch is copied from the existing water source case
(`fixedValue uniform 1`); it is not a water-filled domain. It completed all
3,000 steps to `t=0.3000 s` with `End`, exit 0, and no 200 m/s stop. Its
container ran 1019 s by the guard's elapsed-time counter. The archive is
33,418,815 bytes, SHA-256
`4cf036931475fbed0452107173e4b8c44f0a07c8753512d67edc3e247437930a`; the
remote/local hashes and endpoint snapshot inventory passed.
Its pre-GO source snapshot, frozen case/input-file hashes, guard READY check,
and GO-sentinel hash were independently cross-checked and all matched.

Its global speed peak was 103.1456 m/s at 0.0957 s; terminal speed was
100.2184 m/s. Alpha stayed in [0,1]. The maximum bulk Courant number was
0.26165; maximum interface Courant number was 0.16761. Water volume at the
endpoint was 0.379166666663 m³. Fixed-step integration of the signed
`alphaPhi_` patch records gives 0.379166666667 m³ entering at the nozzle and
3.534e-12 m³ net outward through the other patches, for a -3.661e-13 m³
volume residual. At the declared water density 997.6 kg/m³ this is
-3.65e-10 kg. This flux calculation is an exploratory diagnostic, not a
predeclared conservation gate. The detailed raw values, pressure extrema,
continuity record and per-patch flux sums are in
[`water-total-pressure-diagnostics.json`](water-total-pressure-diagnostics.json).
The first-100-step profile is in
[`water-profile-first100.json`](../../runs/rouaix-backflow-local-20261028/water-profile-first100.json).

## Matched static-pressure water control

The fresh `air-backflow-water-static-030` branch used the same 299,520-cell
mesh and water-nozzle initial condition, with original static `prghPressure`
on the four open patches. Pre-GO checks confirmed that only `0/p_rgh` and
`case-inputs.json` differ from the total-pressure water input; `0/p_rgh`
content outside those four blocks is identical. It started at 2026-10-28
13:11:42.569 UTC after the total-pressure run completed, with 19.592 of 20 CPU
equivalents available. The first-100 profile took 23 s ClockTime, with a
0.2332 s/step warm ExecutionTime slope.

The static case triggered its 200 m/s guard at 0.1702 s (recorded trigger speed
200.697 m/s) and stopped at 0.1703 s with maximum speed 210.058 m/s, End, and
exit 0. Its 31,922,962-byte archive matched SHA-256
`92cce1b3745a54016ebf2f408e40d1ec10ab548853626900488f5c5122ca6269`; initial
and guard-time `U`, `alpha.water`, and `p_rgh` snapshots passed inventory. At
raw `Time=0.1700`, static/total-pressure max speed was 196.368/98.103 m/s; at
`Time=0.1701`, it was 200.697/98.135 m/s. Both cases had 0.215240277778 m³
water at 0.1703 s. The supervisor trigger timestamp is one step later than
the raw function-object time paired with its trigger speed, so both records
are preserved. See
[`water-pressure-matched-comparison.json`](water-pressure-matched-comparison.json)
and [`water-static-control-diagnostics.json`](water-static-control-diagnostics.json).

## Reproduction and provenance

- Pre-launch `make doctor` found 20 effective Goblin CPUs, 119 GiB available
  RAM, 95 GiB free on the results volume, and no active solver. Concurrent
  air and water runs each used about eight CPU-equivalents and 1.0–1.1 GiB.
- The target source snapshot records git revision
  `5a46626c2ff11d090099890d2fc311cc16732050`, dirty state, source-manifest
  SHA-256 `3d6ff02201edadf298fa038dcfe79fb055ce742e1ebbbe9e28a887f18bc1bb97`,
  and input-case SHA-256
  `a655ea13990787c5eeaea531f5a268e0a9bc0d350cabf14071702a4dbf4aa691`.
- The early signal-save smoke completed with `End`, exit 0, and captured
  `U`, `alpha.water`, and `p_rgh` at `t=0` and its 0.0003 s stop point.
- A first pre-GO smoke attempt failed the private guard parser self-test because
  its 100 m/s fixture was above the 70 m/s runtime threshold. That attempt is
  preserved under `../../runs/rouaix-backflow-local-20261028/attempts/`;
  the parser test was made threshold-independent and the same prepared pilot
  was then launched successfully.
- Targeted check: `.venv/bin/python -m pytest tests/test_rouaix_fast_diagnostics.py -q`
  — 3 passed. Ruff check and format checks passed for the generator, scoped
  test, and private preparation/runner/dispatcher scripts. Queue, guard-save,
  water-release gate, and water-static dispatcher self-tests passed.
- The complete inputs, source snapshots, launcher/guard, archives, and terminal
  receipts are in
  [`results/runs/rouaix-backflow-local-20261028`](../../runs/rouaix-backflow-local-20261028).

## Fixed `deltaT=0.0003 s` cost and stability diagnostic

The fresh `air-backflow-water-dt0003-030` case changed only `deltaT` in
`system/controlDict` and corresponding metadata relative to the completed
total-pressure water case. It used the same 299,520-cell mesh, initial fields,
boundaries, schemes, eight ranks, and 0.3000 s endpoint. It completed 1,000
fixed steps with `End`, exit 0, no 200 m/s guard trigger, and a 274 s solver
`ClockTime` (276 s supervisor elapsed under the 900 s cap). The archive is
31,797,802 bytes with SHA-256
`a7d0963990430d277a59bd2f32fe9ae63c50831f7ba82ea8826c4a09304d16b8`; remote
and local hashes matched, and initial/terminal snapshot inventory passed.

At the same physical horizon, it took 3.72 times less solver wall time than the
0.0001 s reference (274 versus 1,018 s). Its mean wall cost per step was
0.274 s versus 0.339 s in the reference. These are observed wall costs;
the reference overlapped another eight-rank case during part of its execution,
so the ratio is not a controlled attribution of all speedup to deltaT. The observed maximum bulk/interface
Courant numbers were 0.77629 at 0.0891 s and 0.49124 at 0.2271 s, about 2.97
and 2.93 times the reference maxima. Peak speed was 105.319 m/s at 0.0555 s
(2.173 m/s above the reference peak); terminal speed was 99.850 m/s. Alpha
remained in [0,1].

The terminal water volume was 0.379166476170 m³. Integrating fixed-step
`alphaPhi_` records gives 0.379166666667 m³ entering at the nozzle and
1.9049484e-7 m³ net outward through other patches, mostly at the bottom
outlet. The signed volume residual is -2.1571e-12 m³, or -2.1519e-9 kg at
997.6 kg/m³. This is an exploratory flux balance, not a formal conservation
gate. The higher Courant values and changed peak/flux records make this a cost
and stability sensitivity only; one coarse run does not establish timestep
convergence or E1 validity. Full diagnostics and provenance are in
[`water-dt0003-diagnostics.json`](water-dt0003-diagnostics.json); the parser is
[`analyze_water_dt0003.py`](../../runs/rouaix-backflow-local-20261028/analyze_water_dt0003.py).

The copied immutable input metadata retains the label `launch_state: prepared only`.
The matching GO sentinel, exact container identity and terminal receipts establish
actual release and completion; the released input was preserved unchanged.

The recoverable prelaunch source snapshots and bounded launch/guard/dispatcher
scripts are bundled in [source-and-launchers.tar.gz](source-and-launchers.tar.gz),
with every member hash in [the source index](source-and-launchers-index.json).
Full meshes and selected native field archives remain in the recorded local/Goblin
run stores; they are not included in this compact Git summary.
