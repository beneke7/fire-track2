# dry_four blocker-resolution memo — 28 September 2026

**Astra Max blocker planner; advisory, not a launch or gate approval.** Keep the
single GPU attempt unspent until the CPU integration checks below and exact
review pass. No solver, Docker container, GPU job, lock reservation, or full
identity/archive scan was run for this memo. The only write is this document.

The applicable scope remains the exact candidate6 executable and the frozen
537,600-cell, zero-slot, zero-liquid, 14-interval case. Its 1.4 ms *physical*
duration is known; its GPU wall duration has not been measured. Short wall
duration is a timing scenario to test, not an observed result. No measured
Restás inputs or external scientific data are needed to repair these software
interfaces. Source qualification, conservation reconstruction, positive-source
cases, B1/B2 and E1–E6 remain outside this memo.

I read AGENTS.md, the experiment plan, VALIDATION.md, current STATUS.md and
BLOCKER_RESOLUTION_PLAN.md, Warden 20260928T1127Z, the candidate6 build review,
the dry amendment/map, launcher, preflight, identity verifier, supervisor,
run_local, output checker, manifest adapter and their tests. I also traced the
pinned upstream time/output writers at commit
`598210616bebd51f7d51f61455f196e6f3479916`. The working tree changed during this
audit. Findings below distinguish the audited baseline, observed repairs, and
acceptance still needed; this memo does not approve later bytes implicitly.

## Ranked work and release evidence

| Rank | Finding and present classification | Owner and prerequisite | Required acceptance or stop evidence | CPU/GPU eligibility |
| --- | --- | --- | --- | --- |
| 1 | Native time/dt checks were absent. The first live repair accumulated `dt` directly, which contradicts the source AB2 operation order. **Confirmed original defect; final reread confirms the corrected CSV join against retained independent evidence. Native text checks and full acceptance remain open.** | Luna output-check worker; primary owns the frozen native-clock predicate. Use pinned `rk.f90`, main, v0.3 H2, and existing time-order evidence. | Exact source-order U0–U14 oracle; reject index-clock substitution, direct-dt accumulation, mismatched ledger clocks and wrong dt. Check native text state/clock fields at their written precision. Astra checks the source oracle independently. | CPU-ready; no GPU until exact accepted checker. |
| 2 | The original staged directory `inputs/` cannot satisfy the unchanged adapter's mandatory `dry_four` leaf name. **Confirmed deterministic manifest failure; launcher/map repair observed.** | Primary launcher/interface owner; fixed staging must reach mounts, command, output checker, adapter and tests together. | One no-solver integration fixture uses the launcher-produced directory and actual adapter, producing the unchanged v2 manifest. An original-fixture shortcut is forbidden. | CPU-ready; GPU waits for accepted end-to-end interface. |
| 3 | Ancillary map paths did not match emitted paths; the original launcher/checker had no complete finalizer/inventory. **Confirmed bundle-completion gap; map/launcher repairs observed.** | Primary owns map/amendment; Luna finalizer worker owns a bounded finalizer and its tests. Depends on ranks 1–2 for normal success. | Successful and failed synthetic attempts retain exact actual paths, report, command/exit records, manifest only on success, sorted complete SHA-256 inventory and inventory hash. Validate the emitted tree against the final map, not a second hardcoded roster. | CPU-ready, including failure fixtures; GPU waits for frozen completion path. |
| 4 | One immediate post-dispatch sample plus a one-second cadence can miss the running/GPU interval, or lose procfs/cgroup files during a sample. **Confirmed timing vulnerability; real-case failure probability unmeasured.** | Luna supervisor worker; retain H7 termination/lock behavior. Primary freezes any supplemental startup sampling change prospectively. | Deterministic delayed-start/short-run/GPU-allocation/exit-race tests plus bounded CPU-only control/sampler timing evidence. Normal acceptance requires actual in-run selected-device evidence, valid sample durations/gaps, and termination proof. | CPU-ready. No extra GPU trial to test the monitor; the approved diagnostic remains the sole solver invocation. |
| 5 | The reported identity CLI mismatch is no longer present in the audited launcher. **Repair confirmed at parser-interface scope only.** | Primary launcher owner; no new candidate needed for this wrapper fix. | Actual launcher argv reaches the real verifier's receipt validation; complete exact candidate/OCI verification remains required before the solver path. Do not infer full identity acceptance from a parser probe. | CPU-ready; full verification is I/O-heavy and scheduled by primary. |
| 6 | Hashes, retained evidence, resource snapshot and primary disposition must describe the final repaired packet. **Expected final gate, not a reason to weaken checks.** | Primary, then independent Astra reviewer. Depends on all preceding accepted CPU artifacts. | Final hash inventory, passing affected checks, current doctor/GPU/disk snapshot, accepted exact memo, pinned amendment and one-run primary disposition. Any mismatch stops before launch. | CPU-ready after integration; GPU eligible only after primary disposition. |

## 1. Preserve the actual AB2 native clock

In the baseline output checker, `_check_v03` checked that mass/velocity clock
fields were finite but did not bind them to state, dt or each other
(`scripts/flutas_dry_four_output_check.py`, baseline lines 355–410). A
read-only in-memory probe supplied `time_s=-1` for all 15 mass states and
`time_s=dt_s=-1` for all 15 velocity states. Both passed this validator. Their
byte lengths were **7,443 and 7,021**, exactly the frozen normal CSV sizes, so
the outer byte-length condition would not repair that omission. The probe did
not create a run bundle or exercise the complete checker.

The live `_check_native_clock_joins` addition is the right interface, but its
first implementation stated that fixed-step AB2 has `f_t12=fixed_step_s` and
advanced by `expected_native_time + fixed_step`. In binary64 that algebraic
substitution is wrong. Pinned upstream `src/rk.f90:119–132` computes:

```text
step 1: f_t1 = 1*dt;                    f_t2 = 0*dt
step >1: f_t1 = (1 + 0.5*(dt/dto))*dt; f_t2 = (-0.5*(dt/dto))*dt
f_t12 = f_t1 + f_t2
```

Pinned main lines 580–583 then perform `time = time + f_t12`; lines 749–761
maintain `dto=dt` and fixed dt. Preserve that operation order. With the frozen
binary64 dt, the independent recurrence yields:

| State | Native accumulated time | v1.2 diagnostic index time |
| --- | --- | --- |
| U0 | `0.0` | `0.0` |
| U1 | `0.0001` | `0.0001` |
| U2 | `0.00020000000000000004` | `0.0002` |
| U14 | `0.0014000000000000004` | `0.0014` |

This distinction was already identified in
`docs/reviews/FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md:140` and retained
in `containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/analysis/bundle/time-order.csv`.
The authoritative native join requirements are v0.3 H2, lines 110–133; the
dry amendment retains them at predicate 2. Do not change solver time, normalize
native CSVs, apply a post hoc tolerance, or use index time to make the check pass.

The smallest fix is a CPU oracle for the exact recurrence and writer format,
shared only as an expected-value function in the checker, with independently
constructed positive/negative fixtures. Verify all mass/velocity U0–U14 times,
exact same-state joins, and all stored dt values. Test state 2 specifically so
the first-step agreement cannot hide the wrong recurrence. Check compiled
serialization with the pinned compiler/flags if existing retained evidence
does not establish the formatting/rounding operation.

Native `time.out`, `vof_info.out`, checkpoint `scalar.out` and
`restart_checkpoints.out` also carry state/time/dt information. Baseline
`check_bundle` only size-checked these text files; the success test deliberately
filled most unparsed native text with `b'x' * expected_size`. Add narrow
structural, finite-number and state/clock checks using each writer's declared
format. For example, main lines 791–811 emit time/VOF rows, and
`src/load.f90:121–124` writes `time,dto,istep` with `(2E15.7,1I9.8)`. Compare
formatted expectations at E15.7 precision, not unrounded binary64 equality.
This is diagnostic integrity, not new raw-field conservation adjudication.

The baseline map's `vof_info` prose incorrectly says U1–U14/14 records although
its **1,365-byte bound is correct for 15 records**. Main lines 525–532 emit U0,
then lines 804–811 emit U1–U14. Correct the prose, cadence and initial-stage
source reference without changing the valid byte bound or native bytes.

Stop evidence: either deliberately wrong clock variant passes, correct
source-order output fails, a native text row is unresolved, or the final
checker/amendment disagree. None requires a GPU or new user data to resolve.

## 2–3. Make staging and archival completion one tested interface

The unchanged manifest adapter rejects `args.case_root.name != 'dry_four'`
before checking hashes (`containers/flutas/candidate6/tools/write_dry_four_manifest.py:251–258`).
The original launcher passed an actual staged directory named `inputs` to all
other components. During this audit the primary changed staging and the map
to `bundle/dry_four/`. That is a narrow repair which preserves the adapter and
candidate; accept it only after a test follows the actual launcher path through
the output checker and manifest adapter. Do not pass the original candidate5
fixture directory merely to satisfy the basename requirement.

The original map also prescribed root `dry-output-map.json`,
`metadata/staged-inputs/`, `logs/supervisor/*`, and
`metadata/solver-stage.txt`, while code produced
`metadata/dry-output-map.json`, `inputs/`, `supervisor/evidence/*`, and
`supervisor/stage.txt`. Several named preflight/host/container artifacts had
no standalone producer. The refreshed map uses the actual supervisor layout
and makes combined JSON/event records explicit; the refreshed launcher copies
`results/machine.json` and emits an OCI layout reference. These are observed
repairs, not yet an accepted complete bundle.

The finalizer must be concrete before launch. The original output checker only
printed a report and copied the 37 canonical streams; it did not retain the
annex, invoke the final manifest adapter, or write a full inventory. The
launcher returned after writing launch-result/failure evidence. Define one
bounded CPU finalization sequence:

1. Preserve launcher/supervisor exit status and all native bytes. Verify staged
   inputs again. Freeze the actual command, permitted environment, candidate
   identity, current host snapshot and external OCI reference under the map's
   exact paths.
2. On normal solver completion, run the complete dry checker, retain its report
   and stderr, then invoke the unchanged v2 adapter on the retained staged
   directory. A failed/incomplete attempt gets failure evidence and an
   inventory, never a synthesized normal manifest or missing native outputs.
3. After the final result record is closed, enumerate every regular file,
   reject unsafe paths/links, and write sorted `SHA256SUMS`. Exclude only that
   inventory and its declared checksum sidecar from its own listing; hash the
   inventory in the sidecar. Freeze the exclusion rule prospectively. Do not
   append evidence afterward without a new explicitly versioned inventory.
4. Independently recompute the inventory, verify all native/canonical pairs,
   and compare the complete emitted tree with the map's conditional
   success/failure roster. Distinguish external OCI bytes from mutable bundle
   bytes. Retain the measured final bundle size as well as runtime samples.

The refreshed map now declares `analysis/dry-output-annex.json`,
`analysis/adapter-run-metadata.json`, `manifest.json`, finalizer command/result
records, `SHA256SUMS`, and `metadata/SHA256SUMS.sha256`. These declarations need
an implemented, tested writer; text declarations alone do not close the gap.
The exact final normal v2 manifest must be the one whose bytes are archived
and checked, not solely an independently constructed transient in-memory
manifest that resembles it.

Acceptance fixtures must cover normal completion; nonzero solver exit; guard
or sampling failure; missing/extra native file; wrong native clock; output
checker rejection; adapter rejection; changed staged input; and partially
created canonical output. Each preserves all available evidence and refuses
overwrite. There is no requirement to rerun the solver to test these branches.

## 4. Resolve short-run sampling races without changing the case

The supervisor currently dispatches `docker start --attach` asynchronously,
then samples immediately, and increments `next_sample` by one second
(`scripts/flutas_source_supervisor.py:1464–1519`). Docker may still report
Created at the first sample. A run starting and finishing before the next
sample is then correctly classified inconclusive, despite solver exit 0.
The existing `test_fast_exit_without_running_sample_is_inconclusive` checks
failure handling, not successful observation of a short run.

Even if the first snapshot reports Running, it may precede accelerator
initialization. The adapter requires a running sample with GPU memory above
the before-create baseline or nonzero utilization
(`write_dry_four_manifest.py:148–194`). A later GPU burst followed by process
exit can be missed. A separate race exists between Docker inspection and
reading `/proc/<pid>/stat` or the cgroup path; if the process exits then,
`SystemSampler` raises a sample failure. These are confirmed control-flow
possibilities; this review has no measurement that the exact solver will hit
them.

Smallest prospective repair: keep the ordinary H7 one-second monitor and
deadlines, but add bounded startup/running observations tied to the transition
from Created to Running, rather than treating command dispatch as an observed
start. Freeze any supplemental cadence and its time budget in the amendment
before launch. Preserve the failure classification when valid in-run GPU
evidence is absent. Do not add solver steps, hold a finished container alive,
insert sleeps, or allocate unrelated GPU memory to manufacture evidence.
If polling cannot observe this candidate reliably, a supported, independently
reviewed runtime device/kernel evidence stream is a possible wrapper-level
fallback; mere GPU visibility or an sm_120 code object is not that evidence.

The primary should assign CPU fake-engine timelines for delayed start,
50–500 ms running periods, delayed GPU allocation, exit during procfs/cgroup
reads, slow inspect/sampler calls, and normal shutdown. Add a separate CPU-only
harmless-container probe of the integrated control/sampler path under the
declared limits; the former Docker-stats and isolated nvidia-smi timings do not
measure that complete path. Any probe using Docker remains scheduled by the
primary, with no FluTAS and no GPU request. Preserve measured whole-sample
latency, maximum gap, and relevant process-state times.

The independent post-run auditor should recompute finite-value checks,
whole-sample durations and start-to-start gaps from raw events. The adapter
currently verifies monotonic completion times and GPU/RAM values but does not
independently enforce every H7 sample bound. Confirm monitoring coverage
through the final termination proof: the normal path after `solver_exit`
performs verification, log capture, removal and another verification without
an additional scheduled resource sample. A slow normal cleanup must not leave
an unreported gap. Keep the detached guardian and GPU lock until container and
child termination are proved; no telemetry convenience may weaken that rule.

Stop evidence: no valid in-run selected-device observation, a sample fault or
gap, missing termination proof, or unresolved startup/shutdown coverage. These
remain failed/inconclusive attempts under the amendment if encountered in the
actual run. Their possible occurrence must not be converted into a pass.

## 5–6. Confirm repaired CLI and freeze the final packet

The actual and recorded launcher argv now include every required identity
argument: `--candidate-root`, `--archive`, `--layout`, `--repository-root`,
`--executable`, and `--output`, plus the Docker executable. I invoked the actual
`_run_identity_verifier` function with deliberately nonexistent receipt and
executable paths and `docker-must-not-be-called`. It returned status 2 with
`candidate identity rejected: ...candidate-build.json`, rather than an
argparse error; no output file was created and Docker was not reached. This
closes the reported CLI incompatibility at that limited scope.

Retain this test through the actual argv builder, not only a hand-written argv
list. The complete exact verifier must still check archive/layout/config,
layers, DiffIDs, executable, source/build inputs and both image identities.
The launcher reserves the sole attempt **before** invoking the identity
verifier; therefore preparation, parser checks and full CPU identity evidence
must all be accepted beforehand. Never delete a consumed claim or retry under
this amendment. Treat a verifier timeout/exception as retained failure evidence
and preserve its available streams.

At the original snapshot `EXPECTED_AMENDMENT_SHA256=None` deliberately kept
launch disabled. Leave it disabled until integration and exact review are
complete. The refreshed map changes its hash, and any checker/adapter/supervisor
change changes the review packet. Update all pins together only after the
primary has selected the final packet; do not bypass a pin to obtain a test
pass. Refresh doctor, available disk and GPU state immediately before the
single eligible launch. Separate immutable OCI storage from the 1 GiB mutable
bundle stop threshold.

Recommended pool use after this handoff: release this planning slot; keep
disjoint CPU owners on native-output validation, supervisor timing, and bundle
integration/finalization. The primary alone integrates map/amendment/pins and
schedules work within the shared 18-core ceiling. One CPU and roughly 2 GiB
per light test process is sufficient as an initial allocation; a full archive
rehash is a distinct measured I/O job. Run the affected pytest modules,
candidate6 adapter/identity tests, Ruff and formatting checks, retain their
exact commands/results, then give a separate Astra reviewer the final hashes,
source oracle and emitted synthetic bundles. That reviewer and the primary,
not this memo, decide whether the single diagnostic is eligible.

## Audited bytes and handoff limits

The baseline below identifies the files behind the confirmed findings and
in-memory probes. Concurrent changes are not covered by these hashes.

| Artifact | Baseline SHA-256 |
| --- | --- |
| `scripts/prepare_flutas_dry_four.py` | `c78304788b7661a919032b25fb6955ce035947c3fca4a7728a1021f4bce5973d` |
| `scripts/flutas_source_supervisor.py` | `309ccc0a5efe258debf75140ccb85f505428e47930fa5c6cae6d14a1932db5b5` |
| `scripts/flutas_candidate6_identity.py` | `abfeaebcab4882c538e66f9aed782c8fccd2528a49e730730bfee09d47486231` |
| `scripts/flutas_dry_four_output_check.py` | `fb85e73188093d918d56c55425bbae9d4bc7fd1859ac4cb205a42a72caf1f705` |
| `scripts/flutas_dry_four_preflight.py` | `0895e73dd22e310a13bceb3471db76e401da7fe780cfe4a7238345b86d3ac18f` |
| `containers/flutas/candidate6/tools/write_dry_four_manifest.py` | `373511b66b46531a99b5670e5ab680eef51811e67456fe98c056a5a1882ab29b` |
| `experiments/dry-output-map.json` | `5cecfbc0a5b5609fb28842c99009184569380eb16244563e0e1d6fe3e0d04aa5` |
| `experiments/FLUTAS_DRY_FOUR_DIAGNOSTIC_AMENDMENT_v0.1.md` | `4560b335e345e403488c8a787b806e35e298704d696518b1e2e19f5ea575504d` |

Observed interim repairs included launcher hash
`b87afb794f70b9af46b50d939e85a2eb43a5cfb6ebfdff7cadd6a7fdb4bc589e`,
checker hash `09ccf0f6001f42cbc90f3626b6f50b911a14093cb4cf76f9772c45d94c07e8b4`,
and map hash `46faea657ac53fb10c682329fdcd9d099019613912ef14f390bae096dafba923`.
These are review locators, not accepted successors. The initial native-clock
repair's direct-dt substitution was reported to the primary immediately.

At final reread, checker hash
`6fbd23ada6b95a344e981c2ef2f8c573893b0a3fe53d31eb3a22b21c167fefbd`
computes both AB2 terms explicitly. A further read-only call to its pure join
function accepted all U0–U14 native times from the retained independent
`time-order.csv`, rejected direct-dt accumulation at U2, rejected index time
at U2, and rejected negative dt at U0. This is a narrow positive result for
the corrected CSV time join, not an exact approval of the complete checker.
`scripts/finalize_flutas_dry_four.py` also appeared during integration, with
hash `1544b56dc6069cabe7cc2ff81fa85669b93346ccb30595a1c64655dfb959f2b9`;
its existence is recorded, but this planning audit does not review or accept
that new implementation.

Commands used were read-only `rg`, `sed`/`nl`, `git show`/`git status`,
`sha256sum`, and small `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python` programs.
They inspected the real identity parser failure path, called the pure row
validator, independently evaluated the AB2 recurrence, and checked the repaired
join against retained independent time-order evidence. No pytest suite,
compiler, solver or GPU operation was run by this planner. Existing pytest
results cannot prove the still-missing integration predicates. The primary
must record disposition and evidence for each recommendation in the shared
status/blocker plan and perform the required independent exact review.
