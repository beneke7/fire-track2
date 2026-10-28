# Rouaix fine-grid p_rgh total-pressure restart sensitivity — 28 October 2026

Prepared exploratory CPU restart candidate; **not submitted**. This is not an
E1 acceptance run or a paper boundary-condition correction.

## Question and declared change

Test whether the four open p_rgh outlet conditions contribute to the
pressure-driven instability in the 120-rank continuation. Start from the
immutable water-injection checkpoint at 0.2 s, produced by the original static-pressure
case, and change only p_rgh on downstreamOutlet, bottomOutlet, spanwiseMinus,
and spanwisePlus to OpenCFD v2512 prghTotalPressure:

- type prghTotalPressure
- p0 uniform 0
- rho rho
- U U
- phi phi
- value uniform 0

Here p0=0 Pa is gauge pressure. This preserves the existing zero outflow gauge
while applying the reverse-flow dynamic-head term. It is a backflow-energy
sensitivity, not a match to a measured or ambient total pressure. The source
review and v2512 implementation receipts are recorded in
results/summaries/rouaix_restart_controls_20261027/outlet-control-review.md.

Apply the dictionary with native parallel I/O using srun on 3 nodes and 120
tasks, with changeDictionary -parallel -fileHandler collated -case
<private-case> -time 0.2 -dict system/changeDictionaryDict.

The candidate is a private extraction of parent archive SHA-256
31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9.
No collated binary is edited by byte replacement. Before solver start, the
runner records hashes for every other checkpoint field, parses the native
collated p_rgh internal arrays with the existing field reader, and verifies
that those arrays and all other checkpoint fields remain byte-identical. It
also checks the four new boundary dictionaries on every rank. A failed check
prevents solver launch and preserves the attempt.

## Matched controls and outputs

- OpenCFD v2512 interIsoFoam, original limitedLinearV 1 momentum scheme,
  parent 120-rank decomposition and mesh, materials, fields, gravity, and all
  non-pressure boundaries unchanged.
- Fixed deltaT=0.0001 s, start 0.2 s, target 0.3 s (1,000 continuation
  steps), 120 MPI ranks on 3 nodes × 40 ranks, 22 GiB/node.
- writeInterval=0.05 s, retaining collated checkpoints at 0.25 s and 0.30 s.
  The existing operational max|U|=1000 m/s guard is unchanged. No field
  clipping or threshold changes.
- 90-minute Slurm limit; CPU-only and collated I/O. The native utility runs
  before the solver in the same allocation. Its first srun consumes step 0;
  the solver step identity is recorded dynamically and may therefore be step 1.

The primary observables are maximum speed and location, pressure and patch-flux
traces, solver convergence, and whether the branch reaches 0.3 s. Any conclusion
is conditional on this checkpoint and boundary intervention.

## Release condition

Keep this sibling unsubmitted until both conditions pass:

1. The separate all-air prghTotalPressure local trial reaches at least 0.20 s
   with finite diagnostics and below its declared 200 m/s operational stop.
2. The native early-save restart smoke completes with a confirmed signal-12
   acknowledgement, native End, exact saved endpoint, and completed ledger.

The primary agent owns gate review and capsule staging. Passing these conditions
only makes this exploratory candidate eligible to queue; it does not validate
the boundary model.
