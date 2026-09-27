# E2 source-uncertainty method — focused Astra follow-up

**Disposition: ACCEPT for freezing this method document as a specification.**
Review 3's identity and query-time findings are closed. This disposition does
not approve a generator, case-matrix admissibility, CFD execution, or a
scientific gate.

Reviewed by Astra Max on 2026-09-25; the exact revision hash was independently
verified twice, unchanged through 09:32:55 UTC:

| File | SHA-256 |
| --- | --- |
| [`E2_SOURCE_UNCERTAINTY_METHOD_DRAFT.md`](../../experiments/E2_SOURCE_UNCERTAINTY_METHOD_DRAFT.md) | `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b` |

## Closed findings

- **M1 — identities and mutation rules.** History-content identity is separate
  from case identity. Identical canonical history bytes may retain history ID
  `H`; source and target hashes both enter upstream digest `U`, so a changed
  dependency changes the case ID even when `H` is unchanged. Execution identity
  depends on its case, source matrix, approval, descriptor and attempt token.
  The dependency graph is acyclic, and corresponding mutation checks are
  required.
- **L1 — query-time oracle.** Rational query times project to binary64 using
  round-to-nearest, ties-to-even. Both evaluators use the same `t_query`; the
  reference uses `Fraction.from_float(t_query)`. Error against the original
  rational position is reported separately as query-projection error.

**Low, nonblocking wording note:** the general sentence at draft lines 430–431
rejects reuse under “changed hashes” more broadly than the specific identity
rules. Scope case-ID reuse to changes in `U/H` and execution-ID reuse to changes
in execution-descriptor dependencies. This does not alter the explicit rules or
the acceptance above.

The author-reported synthetic mutation and query-projection checks remain
unarchived and are not independent implementation evidence. E1 acceptance,
target-coordinate treatment, scientific budgets, coverage, scoring, scenario
admissibility, and release decisions remain separate requirements. No
generator, cases, tests, build, CFD, or GPU work was performed for this review.
