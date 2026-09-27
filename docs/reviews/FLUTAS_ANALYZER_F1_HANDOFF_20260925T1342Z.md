# Candidate5 analyzer F1 repair handoff

**Date:** 2026-09-25 13:42 UTC  
**Authority:** Astra Max exact review
[`FLUTAS_ANALYZER_REPAIR_EXACT_REVIEW_20260925T1331Z.md`](FLUTAS_ANALYZER_REPAIR_EXACT_REVIEW_20260925T1331Z.md),
SHA-256 `b5606ebce5fea7e89f384a623f3e4a22ee6d236723fbca72eb9894e4eab6dd09`.  
**Disposition:** F1 repaired in both analyzer tables; schema v1.2 is unchanged.

The shared phase/velocity scan-summary validator now converts both finite
first-failure values and `max_abs_error` to binary64. A counted finite first
pair must differ after conversion. The binary64 subtraction must be finite. If
`mismatch_count == 1`, the reported maximum must equal the first pair's
absolute difference; when the count is greater, the maximum must be at least
that difference. Violations return the existing structured `SCAN_ERROR`.
Allowed nonfinite first-failure tokens remain independently parsed. A
nonfinite first pair does not receive a finite-pair maximum check, preserving
mixed finite/nonfinite stops.

Literal negative cases cover, in both phase and velocity audit rows: values
that differ as decimals but convert to the same binary64 value; subtraction
overflow from finite operands; a maximum below the first pair's difference;
and an overstated maximum with exactly one finite mismatch. Positive cases in
both tables cover an exact single-mismatch maximum and a valid larger maximum
with multiple mismatches. Additional cases preserve mixed finite/nonfinite
stops when the first pair is finite or nonfinite. The previous M1/M2-focused
tests remain in the suite.

The exact checks ran sequentially under a 4 GiB virtual-memory limit. Pytest
used the project launcher with a one-thread cap:

```text
ulimit -v 4194304
.venv/bin/ruff check src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
.venv/bin/ruff format --check src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_local.py --threads 1 --timeout 60 -- .venv/bin/pytest -q -p no:cacheprovider tests/test_flutas_source_analyzer.py
PYTHONPYCACHEPREFIX=/tmp/flutas-source-analyzer-pycache-20260925 .venv/bin/python -m py_compile src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
```

Results: Ruff passed; both files were already formatted; **57 tests passed in
17.97 s**; `py_compile` exited 0 with no output. No build, solver, source
staging, or GPU work was run.

| Artifact | SHA-256 |
| --- | --- |
| `src/aerial_drop/flutas_source_analyzer.py` | `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37` |
| `tests/test_flutas_source_analyzer.py` | `b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `e6a4d2776859e62f53c60fb0662c5264bf748ab5bf6b8a4169b66d26a6f64171` |
| `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |

The analyzer still receives slot masks, schedule, and scan counts as external
pins; it does not derive them from staged `source-boundary.in` bytes. That
input-byte binding and production B2 acceptance remain open. This offline
synthetic test result does not approve source execution or a scientific gate.
