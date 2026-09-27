# Candidate5 analyzer F1 independent exact review

Recorded 2026-09-25 13:48 UTC. **Configured reviewer: `gpt-6-astra`, reasoning
effort `max`**, explicitly assigned by the primary for this bounded read-only
review. The only project file written by this reviewer is this memo. No
implementation, schema, shared status, input, build, solver, or GPU was changed
or run.

**F1 is CLOSED for the exact analyzer identity below.** The four original
contradictory summaries now fail structurally in both phase and velocity
tables. Valid finite and nonfinite failure evidence is preserved. No new
blocking defect was found in the assigned F1 scope.

This disposition approves only the F1 analyzer repair. **Staged-input binding,
six-ledger conservation, physical/numerical limits, source-launch supervision,
B1-pre, B2, and source execution remain CLOSED / NOT APPROVED.** This review
does not validate a producer, candidate build, CFD result, or scientific gate.

## Exact identities and scope

The reviewer read `AGENTS.md`, the full primary-frozen schema v1.2, the original
Astra exact repair review, the F1 handoff, the implementation note, and the
relevant analyzer and tests. Repository HEAD was
`5bee7e762775e2ada7b129cb83faf0a3f96feacd`; the analyzer, tests, schema, and
implementation note are untracked in the existing dirty workspace. Content
hashes, rather than HEAD alone, identify the reviewed implementation.

All opening hashes were independently computed before testing and matched
the primary's assignment and handoff. Closing hashes were recomputed after
the suite, literal probes, and lint at **2026-09-25 13:48:25 UTC**; all were
unchanged.

| Artifact | Opening SHA-256 | Closing SHA-256 |
| --- | --- | --- |
| `src/aerial_drop/flutas_source_analyzer.py` | `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37` | `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37` |
| `tests/test_flutas_source_analyzer.py` | `b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20` | `b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `e6a4d2776859e62f53c60fb0662c5264bf748ab5bf6b8a4169b66d26a6f64171` | `e6a4d2776859e62f53c60fb0662c5264bf748ab5bf6b8a4169b66d26a6f64171` |
| `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| `docs/reviews/FLUTAS_ANALYZER_F1_HANDOFF_20260925T1342Z.md` | `ac4898a9a4035da45fc41fedb0c698de6da41da02375c11aacc9e570e418fa40` | `ac4898a9a4035da45fc41fedb0c698de6da41da02375c11aacc9e570e418fa40` |
| `docs/reviews/FLUTAS_ANALYZER_REPAIR_EXACT_REVIEW_20260925T1331Z.md` | `b5606ebce5fea7e89f384a623f3e4a22ee6d236723fbca72eb9894e4eab6dd09` | `b5606ebce5fea7e89f384a623f3e4a22ee6d236723fbca72eb9894e4eab6dd09` |

## Independent semantic assessment

The normative source is schema lines 469–493: finite comparison occurs in the
candidate's binary64 precision; `max_abs_error` is the finite maximum over all
finite pairs; finite subtraction overflow is nonconforming; nonfinite pairs
are a disjoint category and retain independently encoded members.

Both table validators call the same `_scan_counts_and_evidence` implementation
at analyzer lines 1332 and 1370. The repaired check:

- Converts the reported maximum to binary64 at lines 1152–1154, after finite
  grammar/range and nonnegative checks.
- Parses the two first-failure tokens independently at lines 1223–1226.
  Finite members still pass `_decimal` and binary64 range validation even when
  the other member is nonfinite.
- Requires a counted finite first pair to differ **after** binary64 conversion
  at lines 1236–1242. Decimal spellings that round to the same value cannot
  supply a recorded finite mismatch.
- Performs the actual binary64 subtraction and rejects a nonfinite result at
  lines 1243–1249. No clamped replacement maximum is accepted for an overflowing
  recorded first pair.
- Requires exact binary64 equality of the maximum and first-pair absolute
  difference for `mismatch_count == 1`, and a lower bound for more mismatches,
  at lines 1255–1267. With one finite mismatch, every other finite pair is an
  exact match with zero error, so singleton equality also applies when other
  cells are nonfinite.
- Leaves the finite-pair bound undefined when the recorded first pair is
  nonfinite, while still requiring positive error exactly when finite
  mismatches are counted. A later finite mismatch can supply that maximum.
  Mixed or both-nonfinite failures retain the correct evidence issue codes.

This is the strongest maximum check implied by the recorded first pair and
counts. When more than one finite mismatch exists, or the first failure is
nonfinite, the summary does not reveal every finite error; it cannot prove
the exact unseen maximum. That existing summary limitation is not represented
as raw-array verification or producer approval.

## Literal outcomes, independently rerun

The reviewer reused only fixture construction and byte serialization from the
test file, supplied literal values below independently, and refreshed CSV and
manifest hashes. Phase used the complete interval-0 `pre_vof_x` audit-stop
prefix; velocity used the complete `initial_u0` audit-stop prefix. The valid
first-failure locations supplied by those fixtures were preserved.

Each of the following **21 cases ran in both tables: 42 checked outcomes**.
`m/n` denotes finite mismatch/nonfinite counts. `complete` below means only
structurally complete failed audit evidence. Every result had evidence `fail`
and decision `not_adjudicated`; no arithmetic exception escaped.

| First expected/requested | First observed/applied | Maximum | m/n | Outcome in both tables |
| --- | --- | --- | --- | --- |
| `1` | `1.00000000000000001` | `1` | 1/0 | `fail`, `SCAN_ERROR` |
| `1e308` | `-1e308` | `1` | 1/0 | `fail`, `SCAN_ERROR` |
| `1` | `0` | `0.5` | 1/0 | `fail`, `SCAN_ERROR` |
| `1` | `0` | `2` | 1/0 | `fail`, `SCAN_ERROR` |
| `1` | `0` | `1` | 1/0 | `complete`, mismatch evidence |
| `1` | `0` | `1` | 2/0 | `complete`, mismatch evidence |
| `1` | `0` | `2` | 2/0 | `complete`, mismatch evidence |
| `1` | `0` | `0.5` | 2/0 | `fail`, `SCAN_ERROR` |
| `1` | `0` | `1.00000000000000001` | 1/0 | `complete`, binary64-equal maximum |
| `0.1` | `0.3` | `0.19999999999999998` | 1/0 | `complete`, actual binary64 difference |
| `0.1` | `0.3` | `0.2` | 1/0 | `fail`, `SCAN_ERROR` |
| `0` | `4.9406564584124654e-324` | `4.9406564584124654e-324` | 1/0 | `complete`, minimum subnormal error |
| `1` | `0` | `1` | 1/1 | `complete`, mismatch and nonfinite evidence |
| `1` | `0` | `2` | 1/1 | `fail`, `SCAN_ERROR` |
| `NaN` | `1` | `1` | 1/1 | `complete`, mismatch and nonfinite evidence |
| `1` | `-Inf` | `1` | 1/1 | `complete`, mismatch and nonfinite evidence |
| `NaN` | `+Inf` | `0` | 0/1 | `complete`, nonfinite evidence |
| `NaN` | `garbage` | `0` | 0/1 | `fail`, `INVALID_NUMERIC` |
| `garbage` | `+Inf` | `0` | 0/1 | `fail`, `INVALID_NUMERIC` |
| `NaN` | `1` | `1` | 1/0 | `fail`, `NONFINITE_TOKEN` |
| `NaN` | `+Inf` | `1` | 0/1 | `fail`, `SCAN_ERROR` |

The first four rows are the original F1 counterexamples. The explicit
multiple-mismatch underreported-maximum probe covers the lower-bound branch
beyond the contributor's positive multiple-mismatch fixture. Decimal-versus-
binary64 difference and maximum probes also distinguish the numerical rule
from a Decimal comparison. The subnormal control confirms this repair does
not reject a representable nonzero binary64 error.

For every structurally complete phase result, the exact issues were
`SOLVER_RUN_INCOMPLETE` plus `PHASE_MISMATCH` and/or `PHASE_NONFINITE` according
to counts, with phase/velocity/timestep counts **8/24/1**. Velocity results
had the corresponding `VELOCITY_*` issues and counts **0/12/0**. All malformed
cases returned exactly the single structural code listed above.

## Commands and verification evidence

The primary allocated one CPU, 4 GiB virtual memory, and a 60-second timeout
per job. Workloads ran sequentially through the shared launcher with its
one-thread cap. The existing `results/machine.json` inspection receipt was
read (mtime 13:31:56 UTC; 20 effective CPUs); no new machine report was written.
GPU eligibility: **not applicable**, a CPU-only analyzer review.

```sh
ulimit -v 4194304
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_local.py \
  --threads 1 --timeout 60 -- .venv/bin/pytest -q -p no:cacheprovider \
  tests/test_flutas_source_analyzer.py
RAYON_NUM_THREADS=1 .venv/bin/python scripts/run_local.py \
  --threads 1 --timeout 60 -- .venv/bin/ruff check \
  src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
RAYON_NUM_THREADS=1 .venv/bin/python scripts/run_local.py \
  --threads 1 --timeout 60 -- .venv/bin/ruff format --check \
  src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
```

Results: **57 passed in 17.73 s**, Ruff `All checks passed!`, and
`2 files already formatted`; all exited 0. The suite retains the original
M1/M2 coverage. The 42 literal probes ran as a separate `.venv/bin/python -`
job under the same memory, thread, and timeout envelope, exiting 0 with
`42 independent literal probe outcomes verified; no escaped exception.`

To reproduce the probe matrix, place the table values into tuples
`(expected, observed, error, mismatch, nonfinite, expected_issue)`, where the
counts are strings and `expected_issue=None` for the complete cases, and use
this core with the same launcher:

```python
import csv, io, runpy

f = runpy.run_path("tests/test_flutas_source_analyzer.py")
a = f["analyzer"]
for kind, stage, filename, header, first, second in (
    ("phase", "pre_vof_x", a.PHASE_FILE, a.PHASE_HEADER, "expected", "observed"),
    ("velocity", "initial_u0", a.VELOCITY_FILE, a.VELOCITY_HEADER, "requested", "applied"),
):
    base = f["_build_bundle"](
        reason=kind + "_audit", interval=0, stage=stage,
        phase_failure=kind == "phase", velocity_failure=kind == "velocity",
    )
    for expected, observed, error, mismatch, nonfinite, expected_issue in cases:
        manifest, originals, pins = base
        files = dict(originals)
        rows = list(csv.DictReader(io.StringIO(files[filename].decode())))
        rows[0].update({first: expected, second: observed, "max_abs_error": error,
                        "mismatch_count": mismatch, "nonfinite_count": nonfinite})
        files[filename] = f["_csv_bytes"](header, rows)
        report = a.analyze_bundle(*f["_refresh_bundle"](manifest, files, pins))
        assert report.evidence_disposition == "fail"
        assert report.decision == "not_adjudicated"
        if expected_issue:
            assert report.structural_disposition == "fail"
            assert report.issue_codes == (expected_issue,)
        else:
            assert report.structural_disposition == "complete"
            issues = {"SOLVER_RUN_INCOMPLETE"}
            if int(mismatch):
                issues.add(kind.upper() + "_MISMATCH")
            if int(nonfinite):
                issues.add(kind.upper() + "_NONFINITE")
            assert set(report.issue_codes) == issues
            counts = (8, 24, 1) if kind == "phase" else (0, 12, 0)
            assert tuple(report.row_counts[x] for x in
                         (a.PHASE_FILE, a.VELOCITY_FILE, a.TIMESTEP_FILE)) == counts
```

## Handoff disposition

Accept the F1 repair only for the exact source, tests, implementation note,
and unchanged schema identified above. No further F1 implementation is
required by this review. The primary owns acceptance, checkpoint/status
integration, and subsequent assignments.

The analyzer still accepts externally supplied masks, schedule, scan counts,
and timestep inputs rather than deriving them from staged input bytes; the
synthetic fixtures do not close that binding. Six-ledger conservation and
limits are not supplied by this summary repair. **Staged-input binding,
six-ledger conservation, limits, source launch, B1-pre, B2, and every source
execution remain closed.** Source-free software evidence remains distinct
from source-boundary readiness and scientific validation.
