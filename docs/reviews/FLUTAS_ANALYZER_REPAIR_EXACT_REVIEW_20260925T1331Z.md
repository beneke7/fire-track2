# Candidate5 analyzer M1/M2 independent exact re-review

Recorded 2026-09-25 13:33 UTC. **Configured role: `gpt-6-astra`, reasoning
effort `max`**, explicitly assigned by the primary as an independent, read-only
exact reviewer. The role configuration agrees with
`.codex/agents/general_reviewer.toml`. This assignment is limited to the
analyzer repair, its focused tests, and the associated frozen interface.

The earlier `FLUTAS_ANALYZER_REPAIR_EXACT_REVIEW_20260925T1326Z.md` is treated
as **unverified preliminary evidence**, because its full-history fork did not
guarantee the requested model override. Its claims were not adopted as an
authoritative review. The source inspection, hash checks, focused test run,
and in-memory results below were performed afresh. No implementation, build,
container, solver, source staging, or GPU execution was performed. This memo
is the reviewer's only project-document write; `make doctor` also refreshed
the ignored `results/machine.json` report. Shared status and gate decisions
remain primary-owned.

| Scope | Disposition |
| --- | --- |
| Original M1 independent token parsing and declared failure-location defects | **CLOSED for the exact analyzer hash below.** The original malformed-token and invalid xlow probes now reject structurally. |
| Finite first-failure/summary conformance | **REVISE.** F1 independently reproduces in both audit tables, with the additional singleton-maximum consequence described below. |
| M2 finite-intermediate overflow and reciprocal/range handling | **CLOSED for the exact analyzer hash below.** The original overflow returns a structured failure, and binary64 validation precedes reciprocal arithmetic. |
| Production analyzer/B2 acceptance, B1-pre, source launch, or scientific result | **NOT APPROVED.** This review neither supplies nor clears those contracts. |

## Exact evidence identities

The first seven hashes were taken before testing and rechecked after all
probes; every value remained unchanged. They match the 13:16 repair handoff
and, where listed there, the preliminary memo. Repository HEAD is
`5bee7e762775e2ada7b129cb83faf0a3f96feacd`; the reviewed source, tests, and
implementation note are untracked in the existing dirty workspace, so the
exact content hashes, rather than HEAD alone, identify this review.

| Artifact | SHA-256 |
| --- | --- |
| `src/aerial_drop/flutas_source_analyzer.py` | `e326e3fd82bc476af5ed93fc3659f805f65f118a4cd051137cf788b76e1f1494` |
| `tests/test_flutas_source_analyzer.py` | `e87a478c823d3f09b3aa78a1e81def73b83fbfd0c35a3c88544020d3851f79fd` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `befab61a5905d22263542a6de5e56d1549478139f5579835c81906e209040d90` |
| `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| `docs/reviews/FLUTAS_SOURCE_ANALYZER_REPAIR_20260925T1316Z.md` | `b3d4f17d027d0439682e7063509f38b96e4c4ca8cfb70289f1d218748b32ff3d` |
| `docs/reviews/FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md` | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
| Preliminary `docs/reviews/FLUTAS_ANALYZER_REPAIR_EXACT_REVIEW_20260925T1326Z.md` | `b832b161970075918bd216253819625b78a669acea19fed4bee9b8ef93d2a590` |
| Candidate5 build handoff `containers/flutas/candidate5/evidence/runs/20260925T123352Z-2100410/handoff-hashes.txt`, read as context | `0f6dde82531c6762cf56bdadb6b35feb6bf8f2f70f742691cd965e66ba031c84` |
| Same build's `metadata.txt`, read as context | `c183745c9911c741f4bea184f81c95b9c87ffcdf9de5a41f3a227a342294f23e` |

The build inventory was read and its own identity checked; this assignment
did not re-audit its 51 member artifacts or certify the producer/build.

## F1 — Medium: binary64 first-failure evidence can contradict the summary

At `flutas_source_analyzer.py:1232–1241`, a finite pair is compared as
`Decimal`, and the maximum error is only required to be positive when a finite
mismatch is counted. The frozen schema at lines 469–482 instead requires
candidate binary64 equality, the maximum binary64 absolute difference over
all finite pairs, and rejection when subtraction of finite values overflows.

Each row below used `mismatch_count=1`, `nonfinite_count=0`, a valid failure
location, a complete controlled audit-stop prefix, and refreshed output and
manifest hashes. The three requested probes and the fourth closely related
probe produced the same incorrect structural classification in **both** the
phase and velocity tables.

| First expected/requested value | First observed/applied value | `max_abs_error` | Required conclusion | Observed structure |
| --- | --- | --- | --- | --- |
| `1` | `1.00000000000000001` | `1` | Both tokens convert to binary64 `1.0`; the recorded first pair is not a mismatch. | `complete` |
| `1e308` | `-1e308` | `1` | Both operands are finite binary64, but their subtraction overflows; the summary is nonconforming. | `complete` |
| `1` | `0` | `0.5` | The maximum is smaller than the first pair's absolute difference, `1.0`. | `complete` |
| `1` | `0` | `2` | There is exactly one finite mismatch, so its difference must also be the maximum; `2` is inconsistent. | `complete` |

Every phase probe returned evidence `fail`, decision `not_adjudicated`, and
issues `PHASE_MISMATCH` and `SOLVER_RUN_INCOMPLETE`, with counts 8/24/1 for
phase/velocity/timestep. Every velocity probe returned evidence `fail`,
decision `not_adjudicated`, and issues `SOLVER_RUN_INCOMPLETE` and
`VELOCITY_MISMATCH`, with counts 0/12/0. This is a malformed-evidence
classification defect; it does not produce a false scientific PASS.

The last row also corrects the preliminary memo's suggested positive fixture:
a larger maximum is not a valid positive fixture when the recorded finite
pair is the only finite mismatch. If `mismatch_count>1`, a later, unrecorded
mismatch may legitimately supply a larger maximum. The independent controls
`(1,0,max=1,count=1)` and `(1,0,max=2,count=2)` both remained structurally
complete failed audit prefixes, as expected from the available summary.

## M1 and M2 closure evidence

Both values are now parsed independently at analyzer lines 1220–1225. Fresh
phase probes of `NaN/garbage` and `garbage/+Inf` each returned structural
`fail` with `INVALID_NUMERIC`. Valid mixed `NaN/1` and `1/-Inf` pairs, with
`nonfinite_count=1`, remained structurally complete audit failures with
`PHASE_NONFINITE` and `SOLVER_RUN_INCOMPLETE`. The existing focused suite also
preserves a both-nonfinite audit failure.

The original invalid xlow coordinate `(20,10,41)` now returns structural
`fail`, `INVALID_INDEX`. Source inspection of lines 1082–1130 matches the
declared domains: x faces own their padded corners; y faces exclude x halos;
phase z faces use interior i/j; velocity faces use padded i/j with periodic
slot wrapping; U/V use upper plane 41 and W upper plane 40. Phase membership
uses the interval, while velocity membership uses the state. Focused tests
also reject wrong slot membership and the wrong W plane. The mask/schedule
scan-count plan is checked before row analysis. This closes the cited M1
location/token defects without claiming complete production input binding.

For M2, `_decimal` performs binary64 representability validation at lines
316–334; `_binary64_reciprocal` at lines 273–285 checks the operand and
nonzero, finite reciprocal; scalar/array inverse checks invoke it at lines
720–740. `_checked_timestep_expectations` at lines 1600–1617 and the outer
report guard at lines 1908–1925 preserve structured rejection. Fresh probes
returned:

| Probe | Structural result / issue |
| --- | --- |
| Finite `dtic_raw_s_inv=1e200` | `fail` / `TIMESTEP_ARITHMETIC`; no escaped `OverflowError` |
| `dx_m=1e400`, pinned inverse `1` | `fail` / `NUMERIC_RANGE` |
| `dx_m=0`, pinned inverse `1` | `fail` / `TIMESTEP_INPUTS` |
| Finite `dx_m=5e-309`, finite inverse `1.7976931348623157e308` | `fail` / `TIMESTEP_INPUTS`, because the actual reciprocal overflows |

The newly required `ExpectedProvenance.slot_masks` and
`active_schedule_indices` pins remain caller-supplied. The note explicitly
acknowledges that the analyzer does not derive them from staged input bytes;
the synthetic four 10×24 masks are not real source-input evidence. No claim
of production B2 compliance follows from these repairs.

## Commands and reproducible probe

`make doctor` reported 20 effective CPUs, 117.5 GiB available RAM, and
260.3 GiB free disk. The only test workload was the focused analyzer suite;
the subsequent probes used the same sequential one-thread, 60-second
launcher envelope. There was no build or solver work. GPU: **not applicable**
for this CPU-only analyzer checkpoint.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_local.py \
  --threads 1 --timeout 60 -- .venv/bin/pytest -q -p no:cacheprovider \
  tests/test_flutas_source_analyzer.py
```

Result: **39 passed in 11.40 s**, exit 0. The in-memory probe command also
exited 0. Its F1 core is reproduced below; it reuses only fixture construction
and byte serialization, while the literal contradictory values and expected
binary64 conclusions come from the schema, not the analyzer implementation.
Run this body through the same launcher with `.venv/bin/python -`.

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
    for expected, observed, error, mismatch in (
        ("1", "1.00000000000000001", "1", "1"),
        ("1e308", "-1e308", "1", "1"),
        ("1", "0", "0.5", "1"),
        ("1", "0", "2", "1"),
        ("1", "0", "1", "1"),
        ("1", "0", "2", "2"),
    ):
        manifest, original_files, pins = base
        files = dict(original_files)
        rows = list(csv.DictReader(io.StringIO(files[filename].decode())))
        rows[0].update({first: expected, second: observed,
                        "max_abs_error": error, "mismatch_count": mismatch})
        files[filename] = f["_csv_bytes"](header, rows)
        report = a.analyze_bundle(*f["_refresh_bundle"](manifest, files, pins))
        print(kind, expected, observed, error, mismatch, report)
```

## Bounded next repair and acceptance evidence

The analyzer owner should change only the shared finite-pair summary check,
its focused tests, and its implementation/handoff note. Convert both finite
operands and `max_abs_error` to binary64 after the existing independent token
validation. Require an unequal first pair; reject a nonfinite absolute
difference; require the reported maximum to be at least that difference;
and, when `mismatch_count==1` and the first pair is finite, require exact
binary64 equality with that difference. Preserve the existing valid mixed
and both-nonfinite cases. No tolerance or schema amendment is needed.

Acceptance evidence is literal negative coverage for all four rows above in
both phase and velocity tables, the two positive controls, preservation of
the M1/M2 tests and nonfinite audit failures, focused lint/tests, and a new
exact-hash independent review. CPU-only, one process; GPU not applicable.
Stop on any escaped arithmetic exception or structurally complete
contradictory summary. Staged-input binding, producer compatibility,
candidate/OCI provenance, inherited conservation evidence, numerical limits,
and source supervision remain separately owned prerequisites. **B2 and every
source run remain unapproved by this memo.**
