# Komondor restart work — current queue

At28 October09:11 UTC, v4 smoke **14689395** and control **14689396** are
released and pending. Smoke targets0.20→0.201 s in ten fixed0.1 ms steps,
20-minute cap. Control targets0.20→0.30 s in1000 steps,90-minute cap, with
`afterok:14689395`, invalid-dependency cancellation and independent runtime
checks of actual smoke/time/ledger/convergence/archive evidence.
Both use120 ranks on three nodes,40/node,22 GiB/node, collated fields,
cpu-short, one CPU/rank, no GPUs or automatic retries. Auditors14689397/14689398
are armed afterany; capture success is not a scientific pass. V4 submission,
manifest and held readback preserve IDs, paths and release time. No native
restart steps have been proved yet.

V2 smoke14676288 obtained120 CPUs but FAILED1:0 in three seconds at27 October
18:15:24 UTC before Python/CFD. Its launcher quoted argument-bearing FOAM_BASH
as one filename; its source root also omitted `/unpacked`. Control14676290
cancelled without allocation. Both audits completed; `failed-v2/` preserves
module stderr, login-node accounting and audit receipts. V3 fixed startup/path,
which passed against Komondor's actual module with all six bashrc arguments.

V3 smoke14688328 then failed before CFD because a literal time check rejected
the saved0.199999999999994293 s value. Its field directory/name is0.200000000000,
index2000, deltaT/deltaT0=0.0001 s. The5.7e-15 s difference is accumulated
floating-point roundoff. It allocated120 CPUs for2m23s; control14688329 cancelled
without allocation. Both audits completed. `failed-v3/` retains native time,
run state, accounting, terminal audit and verified compact bundle (3 members).
No new CFD steps or numerical results were produced by these failed launches.

V4 parses the full raw time with a finite1e-12 s absolute metadata tolerance,
checks name/index/timestep and duplicates, and retains all archive/field hashes.
No solver or physical tolerances changed. Source capsule SHA:
`b4837ed3865548bdc98d2b863f4ba5d3900e88a4816121b99e057168861a2800`.
All16 remote files match the frozen index. The parser accepts the exact native
checkpoint-time file;126 affected tests, Ruff, formatting and shell syntax pass.
Full repository checks were not rerun. V1/v2/v3 source/submission records remain
historical evidence; do not reuse their superseded launchers.

The p0=0 pressure sensitivity remains unsubmitted. Native restart equivalence,
stability and physical reproduction are unproven; only analytical E0 has passed.
