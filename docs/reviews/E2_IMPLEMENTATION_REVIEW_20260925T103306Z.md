# E2 M03 implementation exact-hash review — 2026-09-25 10:33 UTC

**Reviewer:** Astra Max, read-only.  
**Disposition:** **REVISE** the manifest validation before accepting the complete implementation package. The numerical evaluator matches M03 on inspection. This code review is separate from Warden checkpoint 6.

## Reviewed identities

| Artifact | SHA-256 |
| --- | --- |
| `src/aerial_drop/e2_source_uncertainty.py` | `23aa2ead5647c11ae97e6a86980b59b29e85f9caaefea2052562c02263be8de5` |
| `tests/test_e2_source_uncertainty.py` | `6ca763f72b31d64333c5f99e4eb98ee969338c5b25ee7443c911e7b0728ccd65` |
| `experiments/E2_SOURCE_UNCERTAINTY_IMPLEMENTATION.md` | `fb122e1d72c78529112b3ee7a8447d9f4e4d3dc81ed518167d1efc7defbd5816` |
| Accepted M03 specification | `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b` |

The source/target CSV hashes matched M03. All four reviewed hashes were unchanged on the closing check.

## Findings

### M1 — Path aliases bypass duplicate-path rejection

At `e2_source_uncertainty.py:785`, `PurePosixPath` rejects absolute and traversal syntax, but uniqueness at line 806 compared original strings. Different history hashes could therefore use `implementation-fixtures/h.csv` and `implementation-fixtures/./h.csv` while naming the same filesystem location. Repeated separators provide another alias. Reject noncanonical path spellings or compare normalized paths consistently; reject directory-only and NUL-containing paths. Add rejection fixtures for aliases assigned to distinct history hashes.

This counterexample follows from static control-flow inspection; the reviewer did not execute it.

### M2 — Fixture schema and status are unchecked

At `e2_source_uncertainty.py:759`, both fields were required but their values and types were not validated. An otherwise valid fixture with `status="PASS"` or an unrelated schema was serialized and hashed. Pin the implementation-only fixture schema and `implementation_fixture_not_approved_or_runnable` status, or define an explicit versioned allowed set. Test unknown schema, unsupported status, and wrong types.

This is malformed-metadata acceptance; it does not imply any solver was authorized.

### Low-priority test improvements

- The nominal interior-point check at `test_e2_source_uncertainty.py:104` used `source.value`, the same interpolation implementation under test. Compute the expected values directly from adjacent endpoint fractions.
- The rational integral assertion at line 226 used `math.isclose` with its default relative tolerance. Assert the known exact result `Fraction(376253, 200000)`.

## Reviewed areas that passed static inspection

- Strict UTF-8 decoding, Decimal-to-Fraction parsing, pinned grid/bounds, origin taper, and explicit scenario strings.
- Whole-history shift, common `[-0.03, 0.5]` window, zero extension, support rejection, exact roots, and knot union.
- Binary64 collision rejection, canonical `.17g` bytes, common projected query times, and separate query-projection error.
- Acyclic `U/H/case/matrix/execution` identities, dependency mutation coverage, recomputed upstream digest, and orphan/extra-entry rejection.
- Documentation limiting the work to implementation fixtures.

Independently deriving the primary advanced nominal integral from the CSV endpoints gives `1.74145 + 0.139815 = 1.881265 m`; its pre-zero contribution is `0.010305 m`. These are history integrals, not source mass or solver flux.

The reviewer performed file inspection and hash checks only: no tests, edits, matrix generation, build, or solver execution. The recorded 11 passing tests remain author/primary evidence. After the two manifest repairs, rerun affected checks and submit new source/test/note hashes for a focused independent follow-up.

This review approves no scenario coverage, target treatment, protocol, E2 execution, or scientific gate.
