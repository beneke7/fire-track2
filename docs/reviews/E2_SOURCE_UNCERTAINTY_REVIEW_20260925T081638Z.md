# Independent E2 source-uncertainty method review

Reviewer: Astra Max, `/root/general_reviewer_astra`. Evidence snapshot:
2026-09-25 08:16:38 UTC. This is an independent assessment of the existing
draft, with this review record as the only owned write. No source draft was
edited, no build or CFD/GPU job was launched, and no gate was approved.

**Decision: remains a research draft; do not adopt the current construction as
an approved source-uncertainty matrix or release E2.** The source evidence and
several safeguards are sound, but the proposed interpolation changes the stated
shifted curve, joint admissibility/coverage is unestablished, and the complete
comparison rule is not frozen. These are release blockers, not reports of a
failed E2 simulation: no E2 simulation was performed by this review.

## Exact reviewed inputs

SHA-256 values were independently read from the local files. Line references
below refer to these versions; the draft hash was checked again at the end.

| File | SHA-256 |
| --- | --- |
| `experiments/E2_SOURCE_UNCERTAINTY_METHOD_DRAFT.md` | `de3e876e3b776842c838047565e97429ab6e3063f21db3b1e3f222915b0412e0` |
| `experiments/E2_CALBRIX_SOURCE.md` | `0fdbf6709c3922bf2a023fd81972202743e4510d1398edbf694b22e8f229c9cd` |
| `experiments/E2_E3_PROVISIONAL_REPLAY_DRAFT.md` | `c7884a6d3b81d59cd872d99f9ddfd55edd9aa2ee86dc0ddd1186b0a9c972b3c2` |
| `docs/VALIDATION.md` | `0bc0748172f0c38fa0bb2a495f51dd8aa560b1e9419019f686c5c811e4f19f66` |
| `track2_aerial_drop_experiment_plan.md` | `569833febde7ddecd5f709dfb13b88d7d15a8abc77a95657ee4a29596e6f310d` |
| `data/derived/calbrix_dash8_fig4_velocity.csv` | `b43f2ee1220182cca532c290a0d265a5d6f382eb6025b9b7689216fea8f6c332` |
| `data/derived/calbrix_dash8_fig4_velocity_independent.csv` | `fd4791bf79e39e2dbd3261af59c96b13d731b2a0a6ce4fe5450092aa2c1d7f0b` |
| `scripts/digitize_calbrix_dash8_fig4_velocity_independent.py` | `bdd7ba6294f495cf3345791d2ef1d339db169537da2d557257a8ba044c1ea6c6` |
| `data/derived/calbrix_dash8_cloud_curves.csv` | `308c23d755828027acb54e9e9181f74142f831ad6649a1fc91f0a482023a5969` |
| `data/derived/calbrix_dash8_cloud_curves_independent.csv` | `2634389063a3d75a2e1e2c8523b3d27ae204ae31557d9e354de7fe4c2aceab4b` |
| `Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf` | `128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4` |

## Severity-ranked findings and smallest fixes

### B1 — Blocking: the generated function is not the claimed whole-history shift

Draft lines 66–89 and 113–115 describe a coherent horizontal shift. Lines
73–81 instead evaluate shifted ordinates at five **unshifted** knot times,
force a zero origin, and interpolate that new six-knot curve. This discards the
shifted slope changes and modifies the early source history. This is a definite
mathematical difference, independent of any CFD response.

For the primary read, `delta=+0.03 s, a=0`:

- The continuous shifted function gives `u(0.03)=0.687 m/s` at simulation
  time zero; the proposal forces zero.
- At `t=0.07 s`, the shifted function gives `u(0.10)=2.29000 m/s`, whereas
  the proposal gives `0.7*u(0.13)=1.89238 m/s`. The difference is
  `0.39762 m/s`, larger than the initial `0.15 m/s` ordinate allowance.
- Over `[0,0.5] s`, the integral of the continuous shifted function is
  `1.87096 m`; the proposal's integral is `1.81141 m`, a `3.18286%`
  decrease. This is a source-dose change per unit uniform area, before solver
  error. It is not evidence that either interpretation is physically correct.

For `delta=-0.03 s`, a true shifted evaluator needs negative source times
on `0 <= t < 0.03 s`, which the CSV does not supply. The six-knot proposal
avoids that lookup by inventing a different initial ramp; e.g. for the primary
`a=0` case it gives `U(0.03)=0.4809 m/s` where `u(0)=0`. Lines 101–104
correctly resolve upper support through `0.53 s`, but do not resolve this lower
support issue. The origin is a constructed axes intersection, not an extracted
flow measurement: source record lines 126–127 and generator lines 286–290.

Clipping also fails to commute with reinterpolation. For `delta=0,a=-1`,
`max(0,u(t)-b(t))` remains zero through `t=0.15/22.9=0.006550218 s`;
the proposal already reaches approximately `0.140175 m/s` there. The two
unperturbed nominal cases are exact copies on this window, but the other 16
functions are not exact translations plus the stated pointwise residual/floor.

**Smallest fix:** choose and name one prospective continuous transformation,
including time-zero and positivity conventions, then represent that function
exactly, including shifted breakpoints and any zero crossings. If a genuine
translation is chosen, declare supported prehistory and whether nonzero initial
inflow is admitted. If zero initial flow is essential, define an explicitly
anchored time warp/residual taper with its bounds and monotonicity constraints;
that is an additional reconstruction assumption. Alternatively retain the six
knots as an explicitly limited nodal sensitivity construction, remove the
whole-history-shift claim, and independently justify its extra ramp error.
Do not silently select an endpoint convention during implementation.

### H1 — High: 18 finite histories do not establish the claimed conservative uncertainty set

Draft lines 69–89 choose a common-sign residual and call the Cartesian list
conservative. Lines 134–140 and 171–182 correctly admit that neither the joint
error shape nor nonlinear response coverage is known. The four CSV columns
provide coordinate allowances, not evidence that one global translation and
one common-sign residual span the raster/calibration uncertainty. They do not
establish admissibility of every rectangle corner, exclude coherent stretch or
sign-changing calibration errors, or bound responses between the three sampled
values. Two nominal reads of the same figure do not resolve these questions.

**Smallest fix:** remove the unqualified conservative-set claim. Declare whether
the claim is limited to these finite sensitivity cases or is intended to bound
a justified continuous family. In the latter case, derive the permitted paired
transforms from raster/tick/trace evidence, document excluded error modes, and
justify the prospective scenario coverage or add scenarios before CFD. Do not
infer sufficiency from the count 18 or select perturbations using output fit.

### H2 — High: the 36 central-curve scores cannot yet support the proposed gate rule

Draft lines 126–132 and 150–167 use two Fig. 6(b) target reads but do not
propagate their coordinate bounds or provide an executable rule connecting
source-space uncertainty to accepted profile/landmark limits. This is expressly
left open at lines 144–148 and 183–184, so it is a remaining decision blocker,
not a hidden approved tolerance. Target CSV row 2 already shows nonzero bounds:
primary `(y,Z)` allowances are about `(0.00471,0.03111) m`, and independent
allowances are `(0.020,0.030) m`. Two central traces are not the whole target
read-uncertainty set. `docs/VALIDATION.md:72` requires treatment of horizontal
uncertainty and source intervals before applying RMSE.

The mixed-pass/fail rule attributes disagreement to source reads even when
only the target read changes. It also does not explicitly separate an invalid
solver result or missing required comparison from scientific disagreement.
The replay's frozen comparison must include its required support and landmark
checks as well as a profile score (`E2_E3_PROVISIONAL_REPLAY_DRAFT.md:98`).

**Smallest fix:** keep three separate quantities: input trace-read sensitivity,
target trace-read/calibration uncertainty, and unpublished inlet/geometry/model
uncertainty. Freeze the score, normalization, support, landmark logic, treatment
of target coordinate bounds, and a dimensionally consistent source-to-output
uncertainty decision. Define all required numerical-validity and completeness
checks first; missing/stopped/invalid runs cannot be dropped or counted as
scientific agreement/disagreement. Label mixed outcomes by input, target, or
combined sensitivity. A result wider than an approved budget stays inconclusive;
the budget cannot be widened after results. No additional CFD is needed to
specify or analytically test this decision logic.

### M1 — Medium: “independently calibrated” overstates Figure 4 provenance

Draft line 113 calls the two histories independently calibrated. The second
generator explicitly imports the same source-record axis convention: script
lines 40–48 use `x=9..1459`, `y=1148..7`, exactly the calibration in
`E2_CALBRIX_SOURCE.md:129–132`. The raster extraction is separately implemented,
but independent axis calibration is not demonstrated. This claim also appears
in the source record and validation text, so the primary should synchronize
the correction there rather than leaving conflicting provenance.

**Smallest fix:** call them separate trace reads sharing the stated calibration,
unless a new independently measured tick calibration is actually produced.
Preserve both inputs, but do not treat their small difference as a bound on
shared calibration error. Their agreement establishes extraction repeatability,
not inlet accuracy or two independent physical realizations.

### M2 — Medium: immutable-matrix and test specifications are incomplete

Draft lines 117–124 require hashes and saved knots but do not yet define case
IDs/order, file/schema version, numeric precision/serialization, transformation
implementation, its code hash, support/anchor/floor rules, target hashes, or an
actual generated 18-row manifest. “18 immutable input histories” currently
describes a proposal, not a generated and frozen artifact. The existing tests
check the CSVs and regeneration (`tests/test_calbrix_data.py:19–38` and
`tests/test_calbrix_dash8_fig4_velocity_independent.py:46–101`); they do not
verify this proposed matrix or its interpolation semantics.

**Smallest fix:** after resolving B1/H1, implement a bounded CPU-only generator
and a canonical manifest: source PDF/full-CSV hashes; explicit read IDs and
`delta_s/a` signs; all interpolation/support/anchor/floor settings; exact
generation nodes; schema and generator hash; each history's byte hash; and
the target/analysis/approved-contract hashes. Positive `delta` in `u(t+delta)`
advances the source in simulation time; state that sign. Include analytic
`integral(U dt)` and `integral(U^2 dt)` checks, without relabeling these as
measured payload or actual solver phase flux. Preserve actual source mass and
vector momentum diagnostics as required by replay lines 84 and 94.

Required non-solver tests: exact nominal reconstruction; both support edges;
origin/shifted breakpoints; positivity roots; evaluator-versus-exported-table
agreement between knots; exact linear/quadratic segment integrals; all IDs and
case count; deterministic byte regeneration; and rejection of changed source,
target, generator or contract hashes. Freeze a timestep/knot rule adequate for
the entire chosen family and retain separate mesh/time refinements; using the
same timestep in 18 cases does not establish numerical convergence.

## Confirmed checks and limits of this review

- Both history CSVs contain 51 rows at `0.1 s` spacing over `[0,5] s`, with
  the stated columns, nonnegative finite speeds and time bounds `0.03 s`.
  Independent metadata matches the PDF hash, page 5/journal 1519, Fig. 4 and
  blue Dash-8 extraction method. The source PDF's page-5 text confirms the
  maximum-velocity caption and approximate `4.8 m/s, 0.5 s` prose statement.
- The mean absolute same-time difference is `0.0036666667 m/s`; its maximum
  is `0.032 m/s` at `0.1 s`. The first-segment slopes are exactly `22.90`
  and `23.22 m/s^2`; multiplication by `0.03 s` gives `0.687` and
  `0.6966 m/s`. These support the draft's rounded arithmetic, not accuracy.
- A read-only Python enumeration produced all 18 distinct six-knot functions
  defined by the current proposal. Every function is finite and nonnegative;
  every positive-time input lookup lies in `[0.07,0.53] s`. The floor is
  inactive at those five positive-time knots. Analytic segment integration gives
  proposed `integral(U dt)` ranging from `1.5444` to `1.869275 m` over
  all 18; nominal primary/independent values are `1.74145/1.74685 m`.
  These checks establish arithmetic feasibility only. They do not certify
  joint admissibility, coverage or boundary implementation.
- All six relative-link occurrences in the draft resolve. The method keeps
  peak characterization separate, does not convert digitized velocity to
  published flow/payload, does not smooth the spike or infer a shutoff, and
  restricts the matrix to the supported finite window. Its unresolved spatial
  profile/mean-versus-maximum/geometry assumptions remain explicit.
- Lines 185–190 require **accepted E1 and all other E2 prerequisites** before
  comparison execution. This is a sound dependency, consistent with the plan's
  E1 then E2 numerical-benchmark sequence. No later-stage release is implied.

Checks used `sha256sum`, local file/line reads, `pdftotext -f 5 -l 5 <pdf> -`,
and short standard-library `.venv/bin/python` CSV/interpolation/integration and
link checks. No solver, build, GPU operation, or new general test-suite run was
performed. The analytical checks included shifted slope-change points and
positivity roots, rather than checking only nominal samples.

## Next bounded handoff

The method author can correct B1/H1 and the provenance now; a bounded CPU
implementation worker can then generate the matrix and analytic tests. The
primary owns corresponding shared-source/validation wording and the consolidated
case packet. An independent reviewer must reassess the new exact hashes,
representation, target treatment and decision rule before they are frozen.
E1 acceptance, source/geometry/solver qualification and the remaining E2 limits
still precede E2 launch. No new user information is required to revise and test
this provisional method. Recovering an exact published inlet history/profile or
physical source uncertainty would require external author/raw data, which this
method does not claim to supply.

Assessment complete. This record approves no scientific run and no gate.
