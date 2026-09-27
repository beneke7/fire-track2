# E2 source-uncertainty method: independent third review

Reviewer: Astra Max, `general_reviewer_astra` (read-only).
Review completed: 2026-09-25 09:24:16 UTC.
Disposition: **REVISE before freezing this method document.** This review does
not approve a generator, case matrix, CFD execution or scientific gate.

## Exact reviewed version and scope

The reviewed SHA-256 matched at initial inspection and again at completion:

`867403defd73046a8faf358b97e3828c38eb973bc7961d7d986d936df1265520`

The reviewer inspected the method, both previous reviews, source/target CSVs,
E2 source and replay records, E1 dependency, validation protocol, plan and
status. PDF extraction was not repeated. No files were edited and no generator,
test, build, CFD or GPU job was run. The author’s in-memory arithmetic checks
were not independently reproduced.

## Findings

### M1 — Medium: case identity does not follow required input identity

Locations: method lines 348–353, 380–382, and 406. Lines 348–353 define an ID
from method revision, read/scenario settings and the canonical history-table
digest. Lines 380–382 require a new ID after any required input hash changes.
A changed target CSV/read allowance changes the input and source-matrix
manifest, but not the history bytes, so the identity rule produces the old ID
where the mutation rule requires a new one. Changed unused source-history rows
can create the same contradiction.

**Minimum fix:** keep a reusable immutable history-content ID, and define each
case/execution identity using the source-matrix manifest or an acyclic canonical
upstream dependency digest. A changed dependency must create a new manifest and
execution identity while identical history bytes may keep their history ID.
Synchronize mutation tests and revision rules; keep the approval/manifest graph
acyclic.

### L1 — Low: runtime query-time rounding is implicit

Location: method line 322. Interior points are rational while the runtime
evaluator uses binary64 knots; the method does not say whether the comparison
uses an exact rational time or a rounded binary64 query.

**Minimum fix:** specify `t_query = RN-even-binary64(p)` and compare the runtime
value with the exact evaluator at `Fraction.from_float(t_query)`. If the exact
rational point is also compared, report time-projection error separately.

## Prior findings disposition

The following second-review items are closed at method-specification level:

- Fixed absolute diagnostic time `0.5 s`, common provisional gas start
  `−0.03 s`, and source ages `0.47/0.50/0.53 s`; explicitly described as a
  combined timing/startup assumption.
- A single primary-status precedence, distinguishing missing refinements from
  completed but failed numerical sensitivity checks.
- Exact arithmetic and binary64/root/knot rules, subject to the query-time
  clarification above; no implementation or generator is certified.
- Author-reported wording for unarchived preliminary checks.
- Separate integrals `1.87096 m` on `[0,0.5] s` and `1.881265 m` on
  `[−0.03,0.5] s`, including `0.010305 m` before zero.
- E1 remains mandatory, and the 18 proposed histories do not prove uncertainty
  coverage, joint admissibility or a confidence level.

Exact-hash review confirms the manifest/approval/execution graph is acyclic,
shared Figure 4 calibration is labelled correctly, no unsupported source or
uncertainty-coverage claim was found, and both input histories support source
ages through `0.53 s`. Target-coordinate uncertainty, gas startup fields,
budgets, scores and other scientific release decisions remain open. The later
source-flux ledger must begin at `t_start=−0.03 s` so the pre-zero source
contribution is not omitted.

After M1 and L1 are corrected, a focused exact-hash reconsideration can decide
the method-document freeze only. Generator acceptance, case-matrix
admissibility, E2 execution and scientific validation remain separate gates.
