# Komondor restart work — current queue

At28 October11:18 UTC, both v4 CFD jobs and their auditors are terminal;
no Rouaix solver is running or pending.

- **Smoke14689395 COMPLETED0:0:** ten fixed0.1 ms steps from0.20 to0.201 s,
  peak111.97527 m/s; all81 configured linear solves converged. Verified terminal
  fields/archive and incremental ledger residual-6.33e-10 kg. Whole job4m03s,
  solver step39s. This demonstrates short native restart execution.
- **Control14689396 FAILED1:0:**35m47s whole job,120 ranks on three nodes,
  solver step32m36s. It logged658 complete continuation steps through0.2658 s
  and began0.2659 s, with unphysical speed growth and pressure GAMG FPE onrank12.
  No clean End or verified final fields exist. No new interval ledger is claimed.
  The speed guard requested signal12 but did not capture a clean endpoint.
- **Auditors14689397/14689398 COMPLETED0:0**, preserving both outcomes.

The0.30 s target was not reached. Native restart execution is established;
bitwise equivalence, stability and physical reproduction are not. Both old/new controls first cross1000 m/s at0.2625 s at the same reported
boundary point, with1045.53/1033.79 m/s respectively. They are not claimed
bitwise equivalent or proven to share a cause. The posthoc parser finds11
failed U/k/epsilon solve records in the new control. Exact signal-vs-FPE timing
is unresolved: stop_requested_utc is recorded after the blocking stop call. No identical retry or
pressure/backflow candidate is submitted. V4 uses120 ranks, three nodes ×40,
22 GiB/node, collated fields and fixed0.1 ms with bounded afterany capture.
The submission/manifest/held readback retain exact source and dependencies.
[Verified terminal evidence](terminal-v4/README.md) includes raw logs, speed traces,
accounting and hash/CRC-checked audit bundles.

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
