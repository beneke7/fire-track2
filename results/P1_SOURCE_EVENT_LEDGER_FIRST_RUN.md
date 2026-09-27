# P1 revision 1 first-run audit

**Decision: not passed under the frozen revision-1 contract.** This is a
provisional source-event and liquid-ledger diagnostic, not an E1–E6 benchmark,
breakup validation, built-system prediction, or field result.

Run bundle: `results/runs/restas-source-ledger-20260925T003321.108356Z-1927f2fd`.
The bundle is retained unchanged. Independent auditors read the raw flux and
volume tables; the bundle's original `ledger-report.json` is not a reliable
summary because it searched under `postProcessing/.../0/`, while OpenFOAM wrote
the tables under `postProcessing/.../0.000000/`.

All seven patch-flux tables and the volume table contain 1,200 aligned rows at
0.1 ms intervals from 0.0001 through 0.12 s. The log reports a successful mesh
check, 2,081,200 cells and a final state at 0.12 s. The recorded Courant maxima
are 0.23043815 global and 0.14366862 interface, below the 0.5 and 0.25 limits.
The run used 16 MPI ranks, took 2,199.1 s under the 3,600 s cap, and sampled a
memory peak of approximately 5.6 GiB under the 48 GiB cap.

The `alphaPhi_` integral is **57.636 kg per slot and 230.544 kg total**. Revision
1's frozen right-endpoint target was 57.564 kg per slot and 230.256 kg total,
so the measured value is 0.125078% above that target and fails the predeclared
0.1% dose gate. The continuous analytic dose is 57.600 kg per slot and
230.400 kg total; the measured `alphaPhi_` value is 0.0625% above it. The
separate `phi` integral is 57.564 kg per slot and 230.256 kg total.

The four-slot source, open-patch escape, and in-box liquid inventory close to a
maximum residual of about `7.2e-12 kg`; net liquid escape is about
`6.4e-12 kg`. The mass-ledger limit passes. The source-dose limit does not, so
the P1 diagnostic as a whole did not pass.

The two independent audits found that the `alphaPhi_` row at time `t_n`
represents the completed interval `[t_(n-1), t_n]`: during shutoff it follows
the left-endpoint boundary value by one sample. The 230.544 kg dose is therefore
the left-step quadrature of the frozen source profile; 230.256 kg is its
right-endpoint quadrature and matches `phi`. See
[`protocol amendment 1`](../experiments/P1_SOURCE_EVENT_LEDGER_AMENDMENT_1.md).
That amendment is prospective only. The first run stays failed under revision
1, and only a new run after protocol and code approval can test revision 2.

The original manifest records `exit_code: 1` and does not preserve a raw
`interIsoFoam` exit status separately. The solver/reconstruction log reaches
`End`, but that is not a substitute for the missing stage exit code. The
revision-2 runner records the raw solver, reconstruction and overall case
command statuses separately; its execution remains blocked until independent
review approves the exact code hashes.

To re-read the raw tables with the current analyzer without modifying the run
bundle, use:

```sh
.venv/bin/python scripts/analyze_restas_ledger.py \
  results/runs/restas-source-ledger-20260925T003321.108356Z-1927f2fd \
  --output /tmp/p1-first-run-reanalysis.json
```

That report intentionally remains `not_passed`: the saved inputs are revision 1
and the manifest lacks revision-2 approval and raw stage statuses. It reports
the measured rows and marks numerical proximity to the prospective revision-2
target as ineligible for acceptance on this old bundle.
