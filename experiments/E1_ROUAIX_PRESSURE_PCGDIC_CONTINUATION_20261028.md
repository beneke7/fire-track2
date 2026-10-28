# Rouaix PCG/DIC continuation: 0.255 to 0.300 s

This exploratory child tests whether the `.2→.255 s` PCG/DIC parent can
continue beyond its verified endpoint under the same solver policy. Dispatch
requires the exact clean parent contract: 550 completed fixed steps, native
`End`, exit 0, no pause, speed guard, FPE, or convergence failure, and hash
verified checkpoint, inventory history, mesh, ledger, and archive.

## Frozen continuation

- OpenCFD v2512 `interIsoFoam`, CPU only, same donor mesh, decomposition,
  fields, material and physics. Inherit the four `p_rgh` `prghTotalPressure`
  patches at gauge `p0=0` and parent PCG/DIC `p_rgh` policy with `maxIter=1000`;
  child does not rewrite either.
- Start at 0.255000000000 s and target 0.300000000000 s in 450 fixed steps of
  `deltaT=0.0001 s`. Request writes every 0.005 s and retain the two newest
  collated checkpoints (`purgeWrite 2`).
- 120 MPI ranks on three nodes, 40 per node, 22 GiB per node; `cpu-short`,
  CPU only, one CPU per rank, 2-hour Slurm limit, no requeue, and no GPU.
- Preserve the existing 1000 m/s operational stop and all parent numerical
  guards. Any guarded or incomplete endpoint remains exploratory and cannot
  trigger the next continuation.
- Start the incremental mass ledger from the verified .255 s inventory and
  integrate only child-interval flux; do not recount the original .2 s
  injection or parent cumulative flux.
- Dispatch only afterany parent `14705632`, through a 4 GiB, 15-minute
  controller. Slurm reserves two CPU slots for this memory request; numerical
  and BLAS/OpenMP thread counts remain one. Require no shared/run-root `PAUSE`;
  require 16 GiB free reserve plus an incremental disk allowance of
  `max(8 GiB, 4 × parent archive uncompressed bytes)` for extraction, two
  retained checkpoints, and final archive. Freeze source and contract into a
  unique capsule, submit child and
  existing-method auditor held, verify IDs/owners/resources/dependencies,
  release audit first and child last. Child depends afterany on dispatcher;
  audit depends afterany on child.

## Interpretation

This is a conditional solver-continuation diagnostic. It does not validate the
total-pressure outlet treatment, hardware behavior, or an E1 acceptance case.
