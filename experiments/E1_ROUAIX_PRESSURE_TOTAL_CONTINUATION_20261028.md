# Rouaix total-pressure continuation: 0.3 to 0.5 s (superseded, unsubmitted)

This is a predeclared exploratory continuation of a qualifying fine-grid
pressure-total run. It is conditional on a hash-verified, clean 0.3 s parent
with all 1,000 requested steps, `End`, exit 0, the unchanged 1,000 m/s guard,
and complete checkpoint, ledger, and archive receipts. A guarded, partial,
failed, or missing parent stops dispatch.

## Frozen continuation

- OpenCFD v2512 `interIsoFoam`, CPU only, inherited mesh, decomposition,
  fields, materials, gravity, numerics, and four `p_rgh` `prghTotalPressure`
  outlet patches with gauge `p0=0` from the parent.
- Start at 0.300000000000 s from the verified parent endpoint and advance to
  0.5 s in 2,000 fixed steps of `deltaT=0.0001 s`. Writes are requested every
  0.05 s at 0.35, 0.40, 0.45, and 0.50 s.
- 120 MPI ranks on three nodes, 40 per node, 22 GiB per node; `cpu-short`,
  2-hour wall limit, one CPU per rank, no requeue, and no GPU.
- Retain the existing `max|U|=1000 m/s` operational stop. A guarded partial
  endpoint remains exploratory and is not reported as reaching 0.5 s.
- Begin the incremental mass ledger at the parent's measured 0.3 s water
  inventory and integrate only child-interval fluxes. Do not recount injection
  or cumulative parent flux. Preserve inherited pressure-patch settings.
- Admission requires no shared or run-root `PAUSE` marker and at least 16 GiB
  free at the shared and solver roots. The bounded dispatcher is one CPU, 4
  GiB, and 15 minutes, submitted `afterany` the parent. It verifies the exact
  parent contract, freezes source plus contract, submits the child held and an
  existing-method after-any audit held, verifies both readbacks, then releases
  the audit first and child last. Child depends `afterany` on the dispatcher;
  audit depends `afterany` on the child.

## Dispatch outcome

This continuation was superseded before submission. Parent job `14702499`
failed before reaching 0.25 s and cannot satisfy the declared .3 s contract.
The active dispatcher has been retargeted to the new .255 s PCG/DIC parent
profile; this historical .3-to-.5 candidate remains unsubmitted and has no
continuation result.
