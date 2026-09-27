# E2 M03 history evaluator — implementation-only record

**Status: implementation fixtures only.** This record documents a CPU-only
implementation of the proposed M03 evaluator and identity rules. It does not
approve the 18 proposed scenarios, uncertainty coverage, target treatment,
score, tolerance, startup state, E2 case, or solver execution. No generated
table or manifest was written as a case artifact. The 18 history byte streams
below were regenerated in memory for checks only. Any `U`, case, matrix, or
execution identifiers used by tests were built from synthetic test dependency
descriptors.

The accepted-for-freezing method specification was verified at SHA-256
`bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b`.
The generator implements its strict UTF-8 source parsing, base-10
`Decimal`-to-`Fraction` conversion, anchored residual interpolation, exact
history shift and floor roots, common run-window knot union, collision-checked
binary64 projection, 16-ulp roundoff checks, `.17g` history bytes, and
canonical JSON identity layers. The tests include the complete proposed matrix
in M03 order, analytical nominal interpolation, synthetic strict-interior
floor roots, shifted support, absolute-clock values, segment integrals, and
mutations of source, target, method, generator, startup, contract, matrix,
approval, attempt, and execution-setting inputs.

The source and target CSV snapshots match the M03 hashes:

| Input | SHA-256 |
| --- | --- |
| `data/derived/calbrix_dash8_fig4_velocity.csv` | `b43f2ee1220182cca532c290a0d265a5d6f382eb6025b9b7689216fea8f6c332` |
| `data/derived/calbrix_dash8_fig4_velocity_independent.csv` | `fd4791bf79e39e2dbd3261af59c96b13d731b2a0a6ce4fe5450092aa2c1d7f0b` |
| `data/derived/calbrix_dash8_cloud_curves.csv` | `308c23d755828027acb54e9e9181f74142f831ad6649a1fc91f0a482023a5969` |
| `data/derived/calbrix_dash8_cloud_curves_independent.csv` | `2634389063a3d75a2e1e2c8523b3d27ae204ae31557d9e354de7fe4c2aceab4b` |

Each source CSV was decoded as strict UTF-8 and parsed without binary-float
intermediate values. Both sources have 51 exact decimal knots on `[0,5] s`.
The two target CSVs were read and hashed as complete raw inputs; this evaluator
does not choose a target-coordinate model, score, or compare against them.

## Reproducible CPU checks

Environment: Python 3.12.3, Ruff 0.16.9. The checkout was at revision
`5bee7e762775e2ada7b129cb83faf0a3f96feacd` and already had unrelated dirty and
untracked project files. The run used one Python process and no GPU, network,
mesh, build, solver, or CFD work.

Commands and results:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_e2_source_uncertainty.py
11 passed in 0.12s

.venv/bin/ruff check src/aerial_drop/e2_source_uncertainty.py tests/test_e2_source_uncertainty.py
All checks passed!

.venv/bin/ruff format --check src/aerial_drop/e2_source_uncertainty.py tests/test_e2_source_uncertainty.py
2 files already formatted
```

The test suite independently checks all 18 table generations and canonical
bytes. The largest table/evaluator difference was
`7.996492357165153e-16 m/s`; the largest query-time projection effect was
`2.1502799540940033e-16 m/s`, recorded separately. Exact rational trapezoid
and Simpson checks agreed with zero difference for both `∫U dt` and `∫U² dt`
on every interval. The primary `(δ=+0.03 s, a=0)` velocity-history integral on
the full `[-0.03,0.5] s` run window was `1.881265 m`, matching the M03 inline
arithmetic. These values are implementation roundoff and source-history
integral checks, not solver flux or physical validation.

The in-memory canonical table SHA-256 values were:

| Read | `δ` (s) | `a` | Knots | Canonical table SHA-256 |
| --- | ---: | ---: | ---: | --- |
| primary | -0.03 | -1 | 8 | `652e9c03c1346d5e8d0fbfc9493e96098b07788666c814850937d9ad254cef64` |
| primary | -0.03 | 0 | 8 | `f00a3272d04df7318161062eea997d8b0ba09b3477f3794d2a0c624eb70c3a43` |
| primary | -0.03 | 1 | 8 | `11980d05f5395a99bc5dc9a20dc9758a01b3e1dcdc5daa28a061635063e1ed98` |
| primary | 0 | -1 | 7 | `b6393686fa90e4947a7eb1f6e3bafb0d4fa6fd4b02fe104457d2fbdc9ca3a5a8` |
| primary | 0 | 0 | 7 | `eee14db59c0f542624bb501d667896e912a12580d1735c288f0ed19705723158` |
| primary | 0 | 1 | 7 | `2ed88f3a165bfc2d4ac2bd65910369e7bdf657c1a1b596a923f4221f0403439b` |
| primary | +0.03 | -1 | 8 | `1b4f23f8de60736aa3d09c854e2d90c3e76c99c8e2e8dce1ee7d6a7985669dfa` |
| primary | +0.03 | 0 | 8 | `f7fef15008965e051a8b54adb575d12746155b56a739e09da0c58d13a8e457c6` |
| primary | +0.03 | 1 | 8 | `9793dcc823361a22d12f3e23e4b2fb0602eef39479398c17f0f2a9450972214d` |
| second_read | -0.03 | -1 | 8 | `d96622fc6c60472e76218c08cddac4d04aee5bf2439e1b81f77f08d0dd0b08f7` |
| second_read | -0.03 | 0 | 8 | `a035d91b6040e2b3fce475fdb3199569777efd0dd8c20e9901bfe85be62df948` |
| second_read | -0.03 | 1 | 8 | `093f2e7a65aaa14f1cb9676c0c10f7e5a56aa219d59b1cfadde8f39a32318ea8` |
| second_read | 0 | -1 | 7 | `3654c4aca3c37d374cd11c73bd39c34485073186110f673ab48ffb3445617f68` |
| second_read | 0 | 0 | 7 | `2c109589f3b5f46da42ba43c2277a130b81bdc1bcd9c546cc86b9fd3f114c716` |
| second_read | 0 | 1 | 7 | `02ec4837b6caac7b36556e537a20643f6b89a6ae4b8a3ccbba25687a8faf883f` |
| second_read | +0.03 | -1 | 8 | `349fbcdef15b4eda690b201b6d8cbf953c6fa74fb12c7ff85d84494456395134` |
| second_read | +0.03 | 0 | 8 | `5c9dc413350e250768c76eba9c58bd3d36f10c3c745fe235ec2914d90f06134e` |
| second_read | +0.03 | 1 | 8 | `7009de091a2392b950c9ab6d98c30d282462db40c1837446c609ab928f4f1b62` |

Implementation artifact hashes:

| File | SHA-256 |
| --- | --- |
| `src/aerial_drop/e2_source_uncertainty.py` | `23aa2ead5647c11ae97e6a86980b59b29e85f9caaefea2052562c02263be8de5` |
| `tests/test_e2_source_uncertainty.py` | `6ca763f72b31d64333c5f99e4eb98ee969338c5b25ee7443c911e7b0728ccd65` |

## Primary integration checks

The primary tightened manifest validation to recompute `U` from the recorded
upstream fields, reject unknown top-level/nested fields, reject unreferenced or
duplicate history paths, and validate scenario values before identity
generation. Regression cases cover stale `U`, orphan histories, extra fields,
and unsupported scenarios. The generated 18 table bytes and their hashes are
unchanged.

On the integrated revision, the primary independently reran:

```text
.venv/bin/pytest -q tests/test_e2_source_uncertainty.py
11 passed in 0.10s

.venv/bin/ruff check src/aerial_drop/e2_source_uncertainty.py tests/test_e2_source_uncertainty.py
All checks passed!

.venv/bin/ruff format --check src/aerial_drop/e2_source_uncertainty.py tests/test_e2_source_uncertainty.py
2 files already formatted
```

At the time of the author/primary integration, independent Astra code review
was pending because the collaboration runtime rejected a new thread. The exact
review was later completed on the pre-fix hashes listed above and returned
**REVISE** for two manifest-validation defects; method-specification acceptance
did not substitute for code review.

## Unresolved inputs and limits

The common gas-only initial-state hash and non-source boundary-input hash are
not available in the project records. The integration contract and
target-coordinate treatment also remain unfrozen. Accordingly, tests use
synthetic startup hashes, repository evidence, and solver descriptors only to
exercise mutation behavior; those values do not represent project inputs.
The test-only source-matrix fixture preserves
`approved_contract_sha256: null` and is not saved as an immutable matrix. A
production `U`, case IDs, source-matrix manifest, approval record, or execution
ID must wait for real frozen dependencies and review. The 18 histories are
proposed scenarios only and establish neither joint admissibility nor
uncertainty coverage or scientific acceptance.

## Astra exact-hash review and primary response

Astra Max's read-only exact-hash review is archived at
[`E2_IMPLEMENTATION_REVIEW_20260925T103306Z.md`](../docs/reviews/E2_IMPLEMENTATION_REVIEW_20260925T103306Z.md).
It accepted the numerical evaluator on inspection but found that normalized
filesystem path aliases could evade duplicate detection and that the fixture
schema/status fields accepted unrelated values and types. It also recommended
two stronger independent arithmetic assertions.

The primary's focused response is now in the current source and test files:

- Require the exact implementation-fixture schema and status values.
- Require canonical repository-relative POSIX file paths; reject aliases,
  traversal, directory-only spellings, backslashes, and NUL characters, and
  compare canonical paths for uniqueness and case/history joins.
- Add malformed schema/status type/value cases, dot/repeated-separator aliases
  across different history hashes, duplicate canonical paths, directory-only
  paths, and NUL-path tests.
- Derive interior interpolation expectations directly from adjacent rational
  endpoints and compare the nominal integral to its exact rational value.

Post-fix focused verification: 11 tests passed; Ruff lint passed; Ruff format
check passed. Astra's focused exact-hash follow-up is archived at
[`E2_IMPLEMENTATION_FOLLOWUP_20260925T103849Z.md`](../docs/reviews/E2_IMPLEMENTATION_FOLLOWUP_20260925T103849Z.md)
and accepts the bounded implementation fixes at these exact source/test hashes:
`5579d1d1e3327d281223e7e0e24cf2443f0b4d3ceb18beecf91d5b745b23841a` and
`2d202996de4d8d0b70f5768308bce6459a86a6b9cdd99d371c81f09c37ddb68d`. This
closes the E2 implementation code-review findings only. All E2 input, target,
coverage, score, protocol and solver-release limitations above remain open.
