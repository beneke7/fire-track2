# Komondor restart work — current queue

At28 October09:04 UTC, replacement smoke **14688328** and control **14688329**
are released. Smoke has all120 CPUs and is verifying/extracting the donor;
control is pending its dependency. Smoke targets0.20→0.201 s in ten fixed0.1 ms steps,
20-minute cap. Control targets0.20→0.30 s in1000 steps,90-minute cap, with
`afterok:14688328`, invalid-dependency cancellation and independent runtime
checks of actual smoke/time/ledger/convergence/archive evidence.
Both use120 ranks on three nodes,40/node,22 GiB/node, collated fields,
cpu-short, one CPU/rank, no GPUs or automatic retries. Auditors14688330/14688331
are armed afterany; their successful capture is not a scientific pass.
`submission-v3.json`, `afterany-manifest-v3.json` and held readback preserve
identities, source path and release time. Native restart steps remain unproven.

V2 smoke14676288 obtained120 CPUs but FAILED1:0 in three seconds at27 October
18:15:24 UTC before Python/CFD. The launcher quoted the module's FOAM_BASH,
which contains a bashrc path plus six startup arguments, as one filename.
Inspection also found its source root omitted `/unpacked`. Control14676290
cancelled without allocation; both afterany audits completed. `failed-v2/`
preserves native stderr, login-node accounting and terminal audit receipts.
No numerical result was produced. Earlier v1 jobs were cancelled before
allocation. Their exact source/submission/release records remain historical.

V3 changes startup/path handling and adds a regression for the actual
argument-bearing module value and setup failure. Capsule SHA:
`89b74ab3ab19f4814b07f25ac36926d03d4a680781b6aae0b6a88e0c60bac82e`.
All16 remote files match the frozen index; actual Komondor module startup,
v2512/DP32, seven source arguments, and the frozen runner's --help passed.
Cray Python supplies NumPy1.24.4. The119 affected tests, Ruff, formatting and
shell syntax passed. Full repository checks were not rerun.

The p0=0 total-pressure sensitivity remains unsubmitted. All CFD is exploratory;
only analytical E0 has passed. No restart equivalence or stability is claimed.
