# Candidate5 analyzer M1/M2 exact repair review

Reviewed by Astra Max at max reasoning, 2026-09-25 13:23–13:27 UTC.
Scope is the analyzer repair only. No implementation, build, container,
solver, source input staging, or GPU execution was performed. The reviewer
wrote this memo; the required `make doctor` check also refreshed the ignored
`results/machine.json` resource report. Shared plans remain primary-owned.

| Item | Exact disposition |
| --- | --- |
| Original M1 malformed-token and invalid face/class/component location reproductions | **CLOSED** for the exact analyzer below. Both first-failure values are parsed, and the declared scan domain is enforced. |
| M1 failure-evidence conformance as a whole | **REVISE** for the additional finite-pair consistency finding F1 below. |
| M2 unhandled numerical arithmetic / reciprocal-range defect | **CLOSED** for the exact analyzer below. The reported overflow now returns a structured failure and range validation precedes reciprocal operations. |
| Production bundle acceptance, B1-pre, B2, source launch, or scientific result | **NOT APPROVED**. This bounded review does not adjudicate those gates. |

## Exact identities

These opening and closing hashes match. The repaired implementation, tests,
implementation note and unchanged v1.2 schema match the implementation
handoff. The companion source release contract was read as a draft dependency,
not reviewed or approved as part of this assignment.

| Artifact | SHA-256 |
| --- | --- |
| `src/aerial_drop/flutas_source_analyzer.py` | `e326e3fd82bc476af5ed93fc3659f805f65f118a4cd051137cf788b76e1f1494` |
| `tests/test_flutas_source_analyzer.py` | `e87a478c823d3f09b3aa78a1e81def73b83fbfd0c35a3c88544020d3851f79fd` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `befab61a5905d22263542a6de5e56d1549478139f5579835c81906e209040d90` |
| `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| `docs/reviews/FLUTAS_SOURCE_ANALYZER_REPAIR_20260925T1316Z.md` | `b3d4f17d027d0439682e7063509f38b96e4c4ca8cfb70289f1d218748b32ff3d` |
| `docs/reviews/FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md` | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
| `experiments/FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT.md` draft read | `09419b40c4cfd4f6262f45a2ed184d303efb68adcfa86dfd451de52f0f397112` |

## F1 — Medium: finite first-failure evidence can contradict its summary

`flutas_source_analyzer.py:1232–1241` compares parsed `Decimal` values and
requires only a positive `max_abs_error` when a finite mismatch is counted.
The frozen schema instead defines exact candidate binary64 equality and the
maximum binary64 absolute difference over all finite pairs
(`FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md:470–482`). A first finite failed
pair is already enough evidence to reject three contradictory summaries:

| Recorded first pair / error, with `mismatch_count=1` | Contradiction | Current result |
| --- | --- | --- |
| `expected=1`, `observed=1.00000000000000001`, `max_abs_error=1` | Both decimal tokens round to the same binary64 value, so this cannot be a finite first mismatch. | Structurally `complete` |
| `expected=1e308`, `observed=-1e308`, `max_abs_error=1` | Both operands are finite binary64; their binary64 subtraction overflows. The schema explicitly requires nonconforming rejection. | Structurally `complete` |
| `expected=1`, `observed=0`, `max_abs_error=0.5` | The reported maximum is smaller than the recorded first pair's absolute difference of 1. | Structurally `complete` |

All three remain evidence `fail`, decision `not_adjudicated`, with
`PHASE_MISMATCH` and `SOLVER_RUN_INCOMPLETE`. This is malformed-evidence
classification, not a false scientific PASS. The same shared code handles
velocity requested/applied values, so its correction must cover both tables.

**Smallest repair:** after independently parsing both tokens, convert a fully
finite pair to its binary64 values; require an actual unequal pair for a
finite first failure; compute its absolute difference with finite-result
validation; and require the binary64 `max_abs_error` to be at least that
difference. Retain valid mixed finite/non-finite audit failures and the
existing non-finite token treatment. Add literal negative fixtures for these
three cases and positive fixtures for a valid finite pair with equal or
larger recorded maximum. No physics limit or schema change is needed.

The following in-memory probe reproduced the table using a valid complete
phase audit-stop prefix, then rehashed the modified output and manifest. It
wrote no bundle or implementation file:

```python
import csv, io, runpy
f = runpy.run_path("tests/test_flutas_source_analyzer.py")
a = f["analyzer"]
base = f["_build_bundle"](
    reason="phase_audit", interval=0, stage="pre_vof_x", phase_failure=True
)
for expected, observed, error in (
    ("1", "1.00000000000000001", "1"),
    ("1e308", "-1e308", "1"),
    ("1", "0", "0.5"),
):
    manifest, original_files, pins = base
    files = dict(original_files)
    rows = list(csv.DictReader(io.StringIO(files[a.PHASE_FILE].decode())))
    rows[0].update(expected=expected, observed=observed, max_abs_error=error)
    files[a.PHASE_FILE] = f["_csv_bytes"](a.PHASE_HEADER, rows)
    manifest, files, pins = f["_refresh_bundle"](manifest, files, pins)
    print(a.analyze_bundle(manifest, files, pins))
```

## Confirmed repairs, tests and interface limits

M1's two sides are now parsed independently at analyzer lines 1220–1225.
Recognized `NaN`, `+Inf`, or `-Inf` on one side no longer suppresses parsing
of the other. The added tests reject `NaN`/`garbage` and
`garbage`/`+Inf`; legitimate fully finite and fully non-finite audit stops
remain structurally complete failures.

The location validator at lines 1082–1130 matches the v1.2 scan domains:
x owns padded periodic corners; y excludes x halos; phase z faces use
interior i/j; velocity uses the full padded rectangle with periodic slot
wrapping; U/V use the upper ghost plane and W the upper normal-face plane.
Phase classification uses the transport interval and velocity classification
uses the state index. The new tests distinguish a global-bounds check from a
correct face, mask membership and W-plane check. Scan-plan counts are also
checked against separately pinned masks and schedule before reading rows.

M2 is repaired by the shared `_as_binary64` check in `_decimal`, explicit
nonzero finite reciprocal validation, `_checked_timestep_expectations`, and
the outer structured arithmetic guard. The finite `dtic_raw=1e200` probe
is represented in the focused test and now yields `TIMESTEP_ARITHMETIC`.
Literal decimal overflow, zero spacing and finite-spacing reciprocal
overflow have separate tests. The report still cannot emit execution or
scientific PASS.

Independent command:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_local.py \
  --threads 1 --timeout 60 -- .venv/bin/pytest -q -p no:cacheprovider \
  tests/test_flutas_source_analyzer.py
```

Result: **39 passed in 11.69 s**, exit 0. The additional F1 probe used the
same one-thread, 60-second launcher envelope and exited 0. `make doctor`
reported 20 effective CPUs, 117.7 GiB available RAM and 260.5 GiB free disk.
GPU check: **not applicable**, because this is a CPU-only analyzer repair.
No broad suite, compiled producer test or candidate rebuild was performed by
this reviewer.

The repair adds required `slot_masks` and `active_schedule_indices` fields to
the Python `ExpectedProvenance` constructor. The in-repository fixture caller
has been migrated and all its focused tests pass; callers using the old
constructor must supply these new pins. The v1.2 on-disk interface is
unchanged. The implementation note correctly says that masks, schedule,
timestep inputs and counts still arrive as caller pins, rather than being
derived by this analyzer from staged input bytes. That is an acknowledged
production-acceptance dependency, not proof of input binding. Synthetic
10×24 masks exercise 240-cell slot membership, not the frozen physical
6×40 rectangles or their staged files.

An optional performance improvement is to compute the padded slot-cell
count once per validated mask union: `_expected_scan_cell_count` currently
rescans the entire 162×86 padded rectangle for many velocity keys. Preserve
the explicit count checks if this is optimized. It is not a release finding
and does not justify another unchanged validation run.

## Bounded next handoff

Assign the analyzer owner F1 only, with the same disjoint implementation and
test files, and re-review the resulting exact hashes plus literal evidence
fixtures. Keep the M2 closure tied to this hash and check that the small
follow-up preserves its tests. The primary still owns staged-input grammar
and binding, inherited conservation output contracts, justified limits,
candidate/OCI identity and source launch supervision. Their completion and
independent scientific review remain prerequisites for B1-pre/B2; this memo
does not release a source CFD case.
