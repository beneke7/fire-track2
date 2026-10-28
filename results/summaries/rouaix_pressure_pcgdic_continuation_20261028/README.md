# Rouaix PCG/DIC continuation dispatch

## Parent verification

Parent `14705632` and its auditor `14705633` completed with exit code 0. The
parent reached .255 s in 550 steps with native `End`, all solves converged, no
guard or pause, and verified archive/ledger. Its native inventory at .255 s is
`0.3197941351801 m^3`; the actual object is
`postProcessing/waterVolume/0.200000000000/volFieldValue.dat`, which has three
metadata lines before the named `Time` header. The detailed terminal evidence
is in `results/summaries/rouaix_pressure_pcgdic_20261028/terminal-14705632/`.

## Failed v2 attempt

Root released dispatcher `14706859` after reviewing its held readback and v2
capsule. It failed closed after two seconds because the then-current verifier
did not accept the native metadata header. Its Slurm output and failure receipt
are preserved in `attempts/dispatch-output-failed-14706859.txt` and
`attempts/dispatch-receipt-failed-14706859.json`. It created no parent claim,
child, or child auditor. The released-job readback and submission record retain
the original scheduler receipt.

## V3 attempt and current V4 preparation

The frozen v3 capsule is
`results/summaries/rouaix_pressure_pcgdic_20261028/continuation-source-v3/rouaix-pressure-pcgdic-continuation-source-20261028-v3.tar.gz`.
Its SHA-256 is
`b854bd0a0fad6a81e3eb9bf3c905fa21b6e09cac85cbd72c97d9ca26c870373e`; the
outer index SHA-256 is
`1bab995f23eba97bd84d1189074634ab58cebf0207c2435e50a3f2a8d5762492`. V3
contains the corrected parser, verified history locations `waterInventory`
and `waterVolume`, and a dispatcher script that points to the v3 source root.
The earlier v1 and v2 capsules remain preserved.

Actual parent-contract verification job `14708344` ran with two CPUs, 4 GiB,
and a 15-minute limit. Slurm no longer accepted the completed parent/auditor
IDs as new dependency targets, so the utility ran without a dependency after
both were confirmed complete. It failed closed at the endpoint patch check:
processor0 has zero `downstreamOutlet` faces and writes empty nonuniform p0 and
value lists. The source `changeDictionaryDict` still declares the expected
four-patch pressure treatment. See
`attempts/verify-output-failed-14708344.txt`; no contract JSON was written.
The attempted `afterok:14705633` submission failed without creating a job;
its receipt is in `attempts/verify-submit-dependency-failed.txt`.

Dispatcher `14708349` was held after-any on verification job `14708344`, then
canceled when that verifier failed. The held readback is
`dispatch-readback-held-14708349.txt`; the cancellation receipt is
`attempts/cancel-v3-dispatcher-14708349.txt`. It requested one task, two CPU
slots, 4 GiB, 15 minutes, `cpu-short`, and no requeue. No held dispatcher,
child, or child auditor remains.

The replacement v4 capsule is frozen locally at
`results/summaries/rouaix_pressure_pcgdic_20261028/continuation-source-v4/`.
Its archive SHA-256 is
`dd06eb5a93b6a99ffc005c572e0a4ae6cdf4562e032f2043231290fa625662ce`; its
outer index SHA-256 is
`84080cb39ee707f1a603c03b9d8cdefdb6a3c70897b27fba02318ab5d6162c07`. The
internal dispatch index SHA-256 is
`05084f3808ce201a97ae1f3a6454b4660ab69bad307925646484afb6aa2d4a92`. It
includes the final runtime-checkpoint validator and points at the v4 remote
source root. Remote staging and the next bounded verifier job have not run:
the prior SSH control socket expired, and a fresh connection now requires
keyboard-interactive authentication after accepting the key.

The earlier one-CPU declaration and `--mem-per-cpu=4G` probe both allocated
two CPU slots; their canceled receipts remain under `attempts/`.

## Checks

The focused runner, audit, and dispatcher suite passed 58 tests. Ruff,
formatting, Bash syntax, Python compilation, and v3 capsule member-hash checks
passed. Remote v3 member hashes, Python 3.11.7, NumPy, and runner/verifier
imports passed. The actual parent-contract verification has not passed yet;
the v4 capsule has not been staged or executed.

The prepared one-shot utility will also call the continuation `prepare_case`
against the actual parent contract, without running the solver. It writes one
dry-preparation directory and records the inherited `fvSolution` SHA, .255 to
.300 s manifest bounds, checkpoint field hashes, and processor-mesh hashes.
That actual preparation has not yet run.
