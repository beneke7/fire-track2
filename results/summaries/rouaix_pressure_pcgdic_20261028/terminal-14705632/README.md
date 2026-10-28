# Native `.255` parent receipt

Read-only capture from Slurm job `14705632` and its after-any auditor
`14705633`. Both jobs report `COMPLETED|0:0`; the solver run-state records 550
steps from `.200` to `.255`, native `End`, exit code 0, no guard or pause, and
converged solves. The compact selected run-state and terminal fields are in
`parent-terminal-evidence.json`; scheduler accounting is in
`slurm-accounting.txt`.

The actual inventory history is
`/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-restart-20261028/rouaix-restart-pressure-total-pcgdic-14705632/attempt/case/postProcessing/waterVolume/0.200000000000/volFieldValue.dat`.
Its SHA-256 is recorded in `parent-native-inventory-excerpt.txt`. The native
file begins with three metadata comments before the named `Time` header. The
`.255` sample is `0.3197941351801 m^3`; the exact five-line sample used by the
regression test is preserved in `parent-native-inventory-fixture.dat`.

This is evidence for the contract parser and parent handoff, not a new solver
run or physical acceptance result.
