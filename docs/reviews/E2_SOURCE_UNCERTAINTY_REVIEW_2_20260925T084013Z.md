# E2 source-uncertainty method: independent second review

Reviewer: Astra Max, `/root/general_reviewer_astra`.
Evidence snapshot: 2026-09-25 08:40:13 UTC.
Scope: the revised method, its source/target CSVs, and the first archived review.
Only this review record was written. No generator was implemented, no case
table was exported, and no build, CFD or GPU job was run.

**Disposition: REVISE before freezing this as a gate method.** The original
continuous-history defect is resolved. The proposed evaluator is mathematically
coherent as a clearly assumed finite sensitivity construction. Remaining work
is a bounded set of timing, decision-precedence and implementation conventions;
the target model and scientific budgets remain explicitly open. This review
does not approve E2 execution, source-uncertainty coverage or a benchmark pass.
Accepted E1 remains required.

## Exact reviewed versions

| Input | Independently verified SHA-256 |
| --- | --- |
| `experiments/E2_SOURCE_UNCERTAINTY_METHOD_DRAFT.md` | `1cc5ccb66438250674282cbe872a9cde95a9d32235d99b161a91d97dc748133f` |
| `data/derived/calbrix_dash8_fig4_velocity.csv` | `b43f2ee1220182cca532c290a0d265a5d6f382eb6025b9b7689216fea8f6c332` |
| `data/derived/calbrix_dash8_fig4_velocity_independent.csv` | `fd4791bf79e39e2dbd3261af59c96b13d731b2a0a6ce4fe5450092aa2c1d7f0b` |
| `data/derived/calbrix_dash8_cloud_curves.csv` | `308c23d755828027acb54e9e9181f74142f831ad6649a1fc91f0a482023a5969` |
| `data/derived/calbrix_dash8_cloud_curves_independent.csv` | `2634389063a3d75a2e1e2c8523b3d27ae204ae31557d9e354de7fe4c2aceab4b` |
| `docs/reviews/E2_SOURCE_UNCERTAINTY_REVIEW_20260925T081638Z.md` | `cf8e5e6490721522f084783778911c6b437406dd13bdf73ea9f0952cdfdefb58` |

All draft line references below refer to the exact revised hash above. The
source PDF hash and extraction metadata agree with the prior reviewed record;
this bounded review did not re-extract the PDF or recalibrate the figure.

## Findings and smallest fixes

### H1 — High: freeze the observation clock and startup state before adopting the matrix

Lines 94–112 define a coherent candidate with `x=t+delta`, zero pre-release
extension, `t_start=min(0,-delta)`, and fixed absolute target time `t=0.5 s`.
They then leave fixed absolute time versus elapsed release time open. Those
are different experiments, not interchangeable clock labels. At the proposed
fixed target time the source ages are `0.47`, `0.50`, and `0.53 s`. If the
target instead means exactly `0.5 s` since each shifted source origin, its
simulation time is `0.5-delta`, and every history reaches source time `x=0.5`.
For an autonomous problem initialized with the same developed ambient state
at release, the timing factor then becomes a time translation rather than the
intended variation in source age at the observation.

The proposed starts also differ by up to `0.03 s`. Lines 103–108 specify an
empty liquid field, but not a common gas-flow state or gas initialization
clock. If the ambient/body flow has an initial transient, starting the full
solver at different times can mix ambient startup with source-read sensitivity.
This is an unresolved modeling choice, not a demonstrated error in the scalar
formula.

**Smallest fix:** choose one clock interpretation prospectively for this method
version, label it as an assumption if the source does not resolve it, and
record `source_origin_time`, `run_start`, `diagnostic_absolute_time`,
`source_age_at_diagnostic`, and `elapsed_solver_time`. Retain any alternative
as a separate method/case family. Specify either a common earlier gas-flow
initialization with zero liquid input before each source origin, or the same
reviewed developed ambient state at each start. An alternative explicit
startup assumption is permissible, but must not silently become a source-only
uncertainty claim. Freeze this before generating the final run matrix.

### M1 — Medium: the numerical-failure classifications have conflicting precedence

Lines 208–216 classify failed accepted mesh/time/refinement checks as
`NUMERICAL_INVALID` or `INCOMPLETE`. Lines 227–229 classify the same numerical
sensitivity as `INCONCLUSIVE_NUMERICAL_SENSITIVITY`. The two descriptions can
be reconciled, but currently do not define one reproducible decision status.
The separation of input, target and combined sensitivity is otherwise a clear
improvement, and lines 230–246 properly prevent a scientific pass when required
evidence or uncertainty treatment is missing.

**Smallest fix:** define one primary-status precedence and allow secondary
reason codes. For example, a completed but failed refinement gate is
`NUMERICAL_INVALID` with reason `NUMERICAL_SENSITIVITY`; a missing required
refinement is `INCOMPLETE`. Reserve scientific source/target pass/fail or
straddle classifications for the full numerically valid required set. Test
combined missing-data, refinement-failure and source/target-straddle examples.

### M2 — Medium: the generator blueprint is substantially reproducible, but exact-byte details remain

Lines 250–291 now specify shifted breakpoints, positivity roots, run-window
endpoints, ordering, `.17g`, signed-zero normalization, newline rules, JSON
ordering and dependency hashes. That is a useful implementation specification,
and is sufficient to prepare a bounded CPU implementation once H1 is fixed.
It is not yet a complete independent byte-level oracle:

- Lines 261–267 do not specify how decimal source/parameter values become
  binary64, root-rounding/coincident-knot rules, or the comparison bound for
  direct versus exported interpolation. In real arithmetic the selected knots
  represent this piecewise-linear function exactly; independently evaluated
  binary64 expressions need not agree bit for bit. Do not use an undeclared
  physical tolerance to hide that arithmetic difference.
- Lines 157–159 give case IDs only as examples, while lines 288–290 require
  new IDs after hash changes. Freeze the ID grammar and a revision/content
  suffix rule before implementation acceptance.
- Define the dependency direction for approval records: an approval may
  reference the proposed source manifest, and a later execution manifest may
  reference both. Do not require one manifest to contain the hash of an
  approval document that in turn hashes that same final manifest, or a hash
  of its own content-addressed path.

**Smallest fix:** record explicit arithmetic/root/de-duplication and ID rules,
use a documented machine-roundoff test bound or exact-decimal/rational oracle
as appropriate, and define an acyclic manifest/approval schema. Preserve the
current `proposed_unapproved` status and null approval hash until approval is
actually recorded. The current statement that no generator or complete
manifest test exists is accurate; those artifacts remain future work.

### M3 — Medium evidence limitation: the reported inline test has no archived executable record

Lines 320–328 report 18 in-memory hashes, Gauss-quadrature residuals and a
mutation test, but the script, emitted hashes and execution record are not
linked. Lines 329–332 correctly limit the claim, so this is not evidence of an
unreported solver run. This reviewer independently confirms the scalar
arithmetic below, not the author's exact test execution or maximum residuals.

**Smallest fix:** label this paragraph as an author-reported preliminary check,
or link its preserved script/output. The eventual accepted generator must
provide its own exact-hash test evidence. Do not copy the quoted residuals into
an acceptance record as independently reproduced measurements.

## Findings closed or correctly bounded by this revision

- **Original B1 closed at the mathematical-specification level.** Lines 91–108
  define a continuous shifted function with explicit lower/upper support;
  lines 250–267 retain shifted breakpoints instead of resampling onto six
  nominal knots. `U=0` joins continuously at source time zero. Positive shifts
  now advance the source through the preceding interval rather than forcing
  away its nonzero value at absolute time zero.
- **Residual taper and positivity are coherent assumptions.** Lines 83–89
  explicitly exclude the origin's nonzero read allowance from this mode.
  On the first segment, the taper slope is `1.5 m/s^2`, so the primary
  lower-mode slope is `22.9-1.5=21.4 m/s^2`, still positive. Applying the
  floor continuously and inserting every sign-changing root preserves the
  stated function. The taper is not evidence that the actual origin error is
  zero; retaining that limitation is necessary.
- **Coverage overclaim removed.** Lines 136–142 and 154–162 correctly limit
  the 18 cases to a proposed finite sensitivity family. Their joint physical
  admissibility and sufficiency as an uncertainty envelope are still not
  established. The count 18 is not a coverage proof, and no such proof is now
  claimed. Limited conclusions about the chosen scenarios are possible once
  the method and other required case assumptions are approved.
- **Provenance corrected.** Lines 40–45 clearly identify two extractions with
  shared calibration. Both source and both target hashes match. The reported
  initial slopes, timing effects, and same-time discrepancies match the
  reviewed CSVs. All seven relative links resolve. Synchronization of shared
  wording remains the primary's task, expressly identified at 349–350.
- **Target and score gaps are now explicit.** Lines 173–199 do not treat two
  centerlines or 36 comparisons as a propagated target-uncertainty gate.
  Horizontal support/landmarks, ordinate uncertainty, target pairings and
  numerical budgets remain open. Lines 182–188 correctly label all quoted
  percentages and sampling values as candidates, rather than approved limits.
  These remain E2 release blockers; they do not make the source evaluator
  algebra invalid.
- **Upstream dependency retained.** Lines 4–7, 230–238 and 351–353 require
  accepted E1 and the remaining prerequisites. This review supplies no E2/E3
  execution authorization.

## Independent arithmetic evidence

A short read-only standard-library calculation used `Decimal` source values
and exact segment formulas. It produced no generator or matrix files. For the
proposed starts and fixed absolute target time, the full run integral is
`integral_0^(0.5+delta) max(0,u(x)+a*b_taper(x)) dx`; any delayed pre-release
portion contributes zero. The following values in metres are independent
checks for all 18 proposed cases:

| Read | delta (s) | Integral U, a=-1 | Integral U, a=0 | Integral U, a=+1 |
| --- | ---: | ---: | ---: | ---: |
| primary | -0.03 | 1.549068 | 1.601068 | 1.653068 |
| primary | 0 | 1.68645 | 1.74145 | 1.79645 |
| primary | +0.03 | 1.823265 | 1.881265 | 1.939265 |
| second_read | -0.03 | 1.554519 | 1.606519 | 1.658519 |
| second_read | 0 | 1.69185 | 1.74685 | 1.80185 |
| second_read | +0.03 | 1.8286005 | 1.8866005 | 1.9446005 |

The floor is inactive after the origin throughout the finite source-time
support of all 18 cases; all positive-time segment endpoints are positive.
Their distinct integrals establish that the 18 proposed histories are distinct,
without certifying uncertainty coverage. Full-domain lower-mode sign changes
occur near source times `4.6538461538 s` and `4.6466666667 s`, outside E2-DIG-0.5.
Future positivity tests therefore need a full-domain or synthetic crossing
case; merely testing the finite-window 18 cases cannot exercise a clipped root.

The primary advanced nominal history has `U(0)=0.687 m/s`; its pre-zero
integral on `[-0.03,0] s` is `0.010305 m`. Consequently the draft's correctly
labelled `[0,0.5] s` value `1.87096 m` at line 327 is **not** its full-run
integral: the latter is `1.881265 m`. For the second read, the corresponding
pre-zero integral is `0.010449 m`. Preserve both time windows explicitly in
future oracle/ledger checks. These are velocity-history integrals, not measured
payloads or actual solver phase fluxes.

The next bounded step is to resolve H1 and the deterministic conventions,
amend the method with a new hash, then implement and independently test the
CPU evaluator under a separately assigned task. No new user input is required
to state a clearly labelled provisional clock/startup assumption. Exact source
timing or physical uncertainty claims would require stronger source evidence.

Assessment complete; all reviewed inputs remain unchanged.
