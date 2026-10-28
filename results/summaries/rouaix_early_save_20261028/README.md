# Native checkpoint save diagnosis

The original native early-save attempt14700220 and v2 attempt14700456 both
continued to the normal0.202 s horizon without a signal acknowledgement; they
did not pass the intended partial-save test. Their exact source capsules and
terminal run-state receipts are retained. The first exposed the site's active
step-query visibility failure; the second exposed our UID display parser.
The latter expected leading digits while Slurm reported name(uid).

One-CPU probes14700234/14700244 reproduced the invisible active step and proved
exact-step signal delivery. Probe14700561 then exercised the actual corrected
public helper: live job/current UID/task count and own rank-zero identity
matched, scancel signal12 returned0, and the child received SIGUSR2. The helper
persists acknowledgement before waiting and fails closed for other query errors.

V3 native CFD early-save14700599 and afterany audit14700602 both COMPLETED0:0.
The solver stopped after5 continuation steps at0.2005 s, acknowledged signal12,
and verified End/exit0, all endpoint fields, incremental ledger and archive.
Whole solver-job wall was3m35s, its solver step25s; the audit took46s. They use120 tasks on3 nodes,40/node,22 GiB/node,
20 minutes. The source is recovered from the tested v2 capsule, with only the
Slurm helper, its tests and isolated v3 launcher paths replaced. All20 file
hashes and native saved-time/config preflight passed. It requests save after
three healthy fixed0.1 ms continuation steps from the original water donor.

[V3 source and queue evidence](v3/README.md). No new fine-pressure physical run
has been submitted. The intended healthy partial native End/endpoint/ledger is now observed;
this is an operational diagnostic, not a physical acceptance gate.
