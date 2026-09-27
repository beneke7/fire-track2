# Candidate5 analyzer M1/M2 repair handoff

**Date:** 2026-09-25 13:16 UTC  
**Scope:** Astra exact review findings M1 and M2 in
[`FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md`](FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md).  
**Disposition:** Analyzer repairs implemented and focused offline checks pass.
Schema v1.2 is unchanged. This handoff does not open source execution or any
scientific gate.

The analyzer now parses both first-failure values independently. Each side must
be an allowed `NaN`, `+Inf`, or `-Inf` token, or a canonical decimal that is
representable as finite binary64 without underflow. It validates failure
locations against the face and class scan domain, the pinned slot masks and
schedule, and the velocity component plane. The expected scan-count plan must
also agree with those mask and schedule pins.

Timestep inputs are checked for binary64 representability before reciprocal
checks. Reciprocal divisors must be nonzero, and the reciprocal must remain
finite. Overflow and domain errors during timestep recomputation return the
structured `TIMESTEP_ARITHMETIC` code; a final arithmetic guard prevents raw
arithmetic/domain exceptions from escaping the analyzer report path. Finite
intermediate overflow is tested separately from literal non-finite tokens.

The frozen schema does not define a `source-boundary.in` grammar. This change
adds no parser or grammar: callers must provide the separately frozen slot-mask
and schedule pins, while the primary owns that companion interface. The
analyzer still cannot prove those pins derive from the staged input bytes, so
production bundle acceptance remains closed until that interface is frozen
and independently reviewed.

Focused checks used sequential single-process CPU work:

```text
.venv/bin/ruff check src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
.venv/bin/ruff format --check src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/test_flutas_source_analyzer.py
PYTHONPYCACHEPREFIX=/tmp/flutas-source-analyzer-pycache-20260925 .venv/bin/python -m py_compile src/aerial_drop/flutas_source_analyzer.py tests/test_flutas_source_analyzer.py
```

Results: Ruff passed; both files were already formatted; **39 tests passed in
11.50 s**; `py_compile` exited 0 with no output. No build, solver, staged
source input, or GPU work was run.

| Artifact | SHA-256 |
| --- | --- |
| `src/aerial_drop/flutas_source_analyzer.py` | `e326e3fd82bc476af5ed93fc3659f805f65f118a4cd051137cf788b76e1f1494` |
| `tests/test_flutas_source_analyzer.py` | `e87a478c823d3f09b3aa78a1e81def73b83fbfd0c35a3c88544020d3851f79fd` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `befab61a5905d22263542a6de5e56d1549478139f5579835c81906e209040d90` |
| `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
