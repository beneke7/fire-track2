# Independent deblock plan — 2026-09-25 12:29 UTC assignment

**Advisory disposition only.** This Astra Max blocker-planner/general-review
memo accepts no implementation, scientific gate, mesh, characterization, or
launch. Evidence was inspected from 12:30 through 12:47 UTC. The E1 follow-up,
candidate5 preliminary findings and queue changes received during closing
inspection are incorporated below.
Only this memo was written. No tests, builds, mesh utilities,
solver, or GPU workload were launched by this reviewer.

The governing inputs were `AGENTS.md`, the blocker-planner and general-reviewer
role contracts, `track2_aerial_drop_experiment_plan.md`, `docs/VALIDATION.md`,
current status/blocker records, and the exact artifacts cited below. Existing
provisional-input authorization is sufficient for the engineering and expressly
assumed reconstruction work recommended here. No new user answer is needed for
the current critical path.

## Ranked next actions

1. **Finish candidate5's exact handoff and review.** The managed-attribute
   compile failure is now a preserved, resolved build attempt: the bounded
   retry passed at 12:35:46 UTC. Freeze its patch, executable, image ID, tests,
   and runner identities for Astra review. After acceptance for the limited
   scope, the primary should schedule one smallest source-disabled GPU
   regression. Production source acceptance still needs correction of the
   strict timestep CSV/phase-order defects identified during exact review, a
   real build receipt and resolution of the OCI-manifest-digest gap. Keep the
   final smoke decision conditional on the reviewer's closing memo.
2. **Review the completed B2 v1.2 analyzer now; have the primary freeze its
   missing production input interface in parallel.** Its 29-test handoff is
   ready for exact implementation review. That review does not require future
   source CFD. Production acceptance does require independently deriving the
   expected masks, schedule, scan sets, and timestep inputs from the exact
   staged files, rather than trusting an externally supplied object whose
   relationship to those bytes is unproved.
3. **Complete the now-assigned E1 correction against the returned exact
   review.** The follow-up returned REVISE for the Figure-3 PDF digest and a
   wall-node validator that accepts positive infinity/out-of-range heights and
   reads package-global geometry in alternate-case fixtures. Correct those,
   isolate the nesting regression, update provenance wording, regenerate and
   re-review one new exact package. Resolve D-NUT-BC and wetting choices as
   prospective assumptions before characterization.
4. **Complete the broader B2 conservation/limits/launch contract.** The current
   analyzer handles three new observability files, not all six inherited
   conservation/velocity files. Freeze their schemas, independent arithmetic,
   numerical and resource limits, failure handling, and exact launcher before
   B1-pre/B2 can release a source attempt. Later trials are quiescent dry → one
   slot → four slots, with analysis and independent disposition between them.
5. **Keep the frozen crossflow cases as negative fixtures.** Positive crossflow
   needs a prospective reviewed amendment; it is not a prerequisite to the
   independent E1 CPU route or to quiescent source checks. Later measured-data
   limitations must remain visible, but do not hold the present engineering
   work open waiting for raw cups, built-device measurements, or cluster access.

## Current evidence and changes during this review

| Item | Confirmed current evidence | Consequence |
|---|---|---|
| Candidate5 interface | Schema v1.2 SHA-256 `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`; exact interface acceptance in `FLUTAS_CANDIDATE5_SCHEMA_REVIEW_20260925T115737Z.md`. | Acceptance is for the interface only. It does not accept its producer, analyzer, limits, or a run. |
| Candidate5 failed build | `containers/flutas/candidate5/evidence/runs/20260925T123034Z-2097803/metadata.txt`: exit 2 at 12:32:25 UTC; patch `4adf80ed82ac2f0f272aefa1c6e07a9fd2e383d5b9ab77dbff91b81cdac3f4ad`. `docker-build.log:892–898` records NVHPC managed-attribute mismatches at `restas_source.inc:447,449` and `vof.f90:203,205,241,243`. | Preserve this failure. It is compilation evidence, not a source-runtime failure. |
| Candidate5 retry | `containers/flutas/candidate5/evidence/runs/20260925T123352Z-2100410/metadata.txt`: exit 0 at 12:35:46 UTC; patch `22c80953e3646dd6ba01ca9aa877a61b8e009c7ebd25d269c1b9aa8c2207d543`; image ID `sha256:7bad4d20c55fa718321de53f49083f98042be522b6848b73903c7c8b005202d4`; executable `fe5231fe9ef5421a28a9627dfd08c784644039fe8bb275a5315a992f3d635ff1`. Log confirms `sm_120.cubin`. | The compile blocker cleared during this review. Exact code/build/runner review remains open; compilation is not a GPU or source qualification. |
| Candidate5 test scope | Build evidence records 19 static/input checks and 13 compiled-host observability checks. The in-build manifest suite ran four tests with one skipped because the schema was not mounted. The retry's `postbuild-manifest-test.txt` then records all four passing with the exact schema supplied, exit 0. | The skip has been closed by explicit follow-up evidence; do not conflate the two invocations. These are helper/serialization checks, not a real solver bundle. |
| B2 handoff | `FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` reports 29 offline tests and identifies source `77c94d49…`, tests `a2ab5203…`; those full hashes were independently rechecked below. | Completed implementation awaiting exact review, not still waiting for initial v1.2 implementation. No production bundle is accepted. |
| E1 candidate | All 20 `CASE_SHA256SUMS` entries independently pass read-only verification. Generator and generated JSON nevertheless contain the same wrong Figure-3 PDF digest. Both local Rouaix PDFs hash to the canonical source digest. Exact follow-up `E1_STATIC_PACKAGE_FOLLOWUP_20260925T123638Z.md` returned REVISE with a second geometry-validator finding. | A self-consistent generated manifest does not prove source identity or validator coverage. The full findings are now available and one Luna correction is active. |
| Resources | Primary's 12:30 UTC doctor ledger: 20 effective CPUs, 118.1 GiB available RAM, 260.7 GiB free disk. The completed retry's `postbuild-resource-snapshot.txt` reports 20 CPUs, 118.1 GiB RAM and 260.6 GiB free disk. Reviewer read-only `nvidia-smi` observed 0% GPU and 16/32607 MiB during the CPU retry. | Capacity is available, but these are snapshots, not reservations or peak-use profiles. The next GPU workload is blocked by review, not device occupancy. |

`docs/STATUS.md` was updated by the primary from 12:23 through 12:42 UTC during
inspection. The latest ledger correctly records the completed analyzer handoff,
successful candidate5 retry, OCI/build-receipt gap, E1 follow-up REVISE and new
worker assignments. Its earlier build-running wording is historical. The
blocker plan still carried a 12:23 header and analyzer-integration wording at
closing inspection. Refresh that shared plan; none of this is a reason to repeat
completed work. The older STATUS hash below is retained as an explicit snapshot,
alongside the closing one.

## 1. Candidate5 producer, build, and exact review

**Severity: high; true engineering gate to candidate5 runtime.** The specific
compile failure is resolved at the retry hash above. Optional density and
viscosity dummy arrays now carry matching managed declarations; an exact
review must still check the call chain and that production GPU and host-test
paths preserve the intended state refresh. The accepted schema does not confer
acceptance on this changed Fortran.

**Smallest defensible next step and owner:** the candidate5 Luna owner closes
the handoff with the final source/build/fixture/writer/test identities and all
successful/failed evidence paths. A separate Astra reviewer inspects this exact
candidate, actual staggered timestep operands, halo=1 refresh, transition
sequence, complete scan coverage and failure prefixes, plus the existing
source-disabled wrapper at its current hashes. No additional build is needed
merely to repeat the already passed compile. Any subsequent source change
requires its own build evidence and renewed affected review.

**Acceptance evidence:** exact opening/closing review hashes; 19 static checks,
13 compiled-host checks and four unskipped schema-bound manifest checks tied to
the final candidate; the successful NVHPC build, `sm_120` object, extracted
executable hash and immutable local image ID; candidate input hashes; and an
explicit decision authorizing only the source-disabled regression, if warranted.
Missing evidence, changed bytes during review, or unclosed findings stop the
affected scope of that handoff. Preserve both build attempts.

Two **high-severity source-output conformance defects** were reported by the
active exact reviewer through the primary at 12:46 UTC. This deblocker also
confirmed their source/schema mismatch by inspection at the recorded patch:

- `source-boundary.patch:1544–1549` writes timestep reals directly using
  fixed-width `ES24.16E3`. Ordinary finite values therefore contain field
  padding, while schema v1.2 requires whitespace-free numeric tokens and
  `flutas_source_analyzer.py:286–293` rejects leading/trailing whitespace.
  The canonical `restas_source_real_text` helper at patch lines 1115–1124
  already exists, but that timestep writer bypasses it.
- The phase-stage arrays at patch lines 1223–1231 place the three top classes
  before `bottom_return`, and the emission loop at lines 1326–1334 follows
  that order. The accepted schema's phase table at lines 64–75 requires
  `bottom_return` before the top classes. Counts can still be correct while
  the exact ordered record stream is nonconforming.

The smallest source repair is to use the canonical formatter for every
timestep real and serialize phase rows in the frozen order, without weakening
the strict analyzer. After the final review returns its complete findings and
closing hashes, assign one Luna owner to a versioned correction. Add a
compiled-host fixture that invokes the actual producer routines and feeds
their unmodified file bytes into the independent v1.2 parser; check numeric
grammar, signed-zero behavior, ordering, row keys and controlled-stop prefixes.
Do not substitute another synthetic reimplementation of the output writer.
Then rebuild the changed candidate, preserve old receipts and obtain exact
follow-up. These defects are not exercised by a source-disabled smoke. The
active reviewer considers that narrower smoke scope potentially approvable,
but its edge probes and final closing-hash memo were pending at this cutoff;
this memo provides no final smoke disposition.

There is a separate **production provenance gap**. The successful metadata says
`candidate_repo_digests=[]` and `oci_manifest_digest_available=no`.
`candidate5/build.sh:65–89` records the Docker image ID and executable, but does
not emit the `candidate-build.json` required by schema lines 358–364.
`tools/write_run_manifest.py:175–200` consumes such a receipt; a synthetic test
receipt is not the production receipt. Docker's `.Id` is not an OCI image
manifest digest. Do not satisfy the schema by putting the former into a field
whose declared hash subject is the latter.

The primary owns that identity decision. A bounded local OCI-layout/export
receipt can bind an actual manifest, its configuration, the built image and
executable without publishing anything. If the intended contract instead uses
an immutable local configuration/image ID, make that distinction in a
prospective reviewed interface amendment; do not silently change the already
accepted schema. The candidate owner can then emit a receipt with the exact
upstream/source/patch/build/compiler/flags/executable identities.

**GPU eligibility:** no trial before exact candidate/build/runner acceptance.
After that, one source-disabled regression through the existing locked wrapper
is the smallest useful check. That wrapper explicitly takes an immutable local
image ID, so this limited check need not wait for a future production OCI/run
manifest decision if its reviewer accepts the exact scope. Source-enabled
execution remains blocked by B1-pre/B2/limits/launch review. **User or external
data:** none. **Independent work:** B2 exact review/input contract and E1 review
can proceed throughout.

## 2. B2 v1.2 analyzer and missing staged-input binding

**Severity: high; true production-acceptance blocker, not a reason to postpone
the ready implementation review.** The current module and note explicitly
limit themselves to synthetic in-memory bundles. `ExpectedProvenance` at
`src/aerial_drop/flutas_source_analyzer.py:225–236` receives
`input_sha256`, `expected_timestep_inputs`, and `expected_scan_cells` from its
caller. The checks around lines 446–453 compare those pins; they do not derive
the physical expectations from the staged input bytes. The note, lines 28–39,
acknowledges this limit.

There is an executable Fortran reader, not an absent file format altogether:
`candidate5/source-boundary.patch:205–250` uses ordered list-directed records
for slot count, grid, pulse endpoints, dt, three velocity/gravity vectors,
geometry, masks and factor. What is missing is the **frozen independent
acceptance grammar and binding interface**. The producer's `_case_inputs`
hashes a three-file tree and rejects symlinks/extra files, but this does not
prove that the analyzer's expected geometry or numerical inputs came from
those files. The synthetic test uses four 10×24 masks; the real four-slot
fixture uses 6×40 masks. Each has 240 cells per slot, so agreement of count or
area alone cannot identify the actual geometry. This is a declared fixture
limitation, not a claim that the test is a production case.

**Smallest next step and owner:** the primary freezes a separate, narrowly
scoped case-input contract for the supported canonical fixtures, derived from
the pinned Fortran reader and DNS/VOF readers. Define exact file set, byte and
token grammar, record order/arity, allowed numeric forms, trailing/comment
rules, indices, units and signs, masks, schedule, material/gravity/BC/grid
cross-checks, and the hash subjects. It need not support arbitrary Fortran
list-directed syntax. Unsupported encodings must fail before launch. Keep the
accepted observability schema unchanged unless a deliberate versioned amendment
is actually required.

After that freeze, a Luna owner implements a disjoint input-binding module and
tests. Its public output is an immutable typed case description plus raw-input
hash map, independently derived complete scan plan and pinned timestep inputs
for `ExpectedProvenance`. It must use the verified staged bytes and reviewed
candidate/grid initialization; it must not copy expected values out of the
producer manifest or timestep CSV. The primary supplies build/compiler pins
that cannot be obtained from case files. Coordinate edits to the existing
analyzer only after its exact review returns.

**Acceptance evidence:** independent review of the current three analyzer
artifacts can proceed now; a later separate review must trace all real dry,
one-slot and four-slot pins to exact `dns.in`, `vof.in`, and
`source-boundary.in` bytes and candidate initialization. Offline integration
must feed producer-created bytes into the independent analyzer and reject
tampered case bytes/pins, wrong masks or endpoints, material/gravity/dt
disagreement, nonfinite/ambiguous/extra records, omitted files, path aliases or
symlinks, missing/duplicate/orphan rows, and invalid controlled-stop prefixes.
Production acceptance stops on any unbound externally supplied expectation.
Unapproved physical limits continue to produce `not_adjudicated`.

**GPU eligibility:** this checkpoint is CPU-only, not applicable. Missing
production binding blocks B2/source runs, not a separately reviewed
source-disabled smoke. **User/external data:** none; exact pinned code and
fixtures exist. **Independent work:** primary limits/launcher specification,
candidate review and E1 preparation decisions.

## 3. E1 static package provenance and review freeze

**Severity: medium; real static-package provenance and validation corrections
before exact handoff.** `prepare_case.py:735`, `geometry/domain.json:13`, and the preparation
note at line 101 give the Figure-3 PDF hash as
`624efe9ee2aec11b85624e9e2ac5364802b12c42657711d211e625052cf28446`.
The source note at line 19, generator at line 711, generated source record at
line 69, and both inspected local PDFs instead give
`624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`.
The rendered page hash itself matches the preparation record:
`12cd10ef2d1cb06b397dcc2fa81e83067a83bf8f7be5eca64a2d302fa2291726`.
This confirms a source-identity typo; it does not establish a recovered wall.

The preparation note at lines 28–33 also says the gate and audit were unedited
for the package while its later text and primary disposition record the wall
amendment. Review-4 gate hash `15a9b4a4…` is the accepted predecessor, not the
current amended `28e66d27…`. In addition, the unchanged capability audit retains
historical statements that no case/sampler exists (lines 3, 19, 26 and 192) and
the predecessor Figure-3-trace requirement. These must be identified as
historical or superseded in the current ledger/next version, without rewriting
an accepted historical record as though it had different bytes.

The exact follow-up arrived during closing inspection:
`docs/reviews/E1_STATIC_PACKAGE_FOLLOWUP_20260925T123638Z.md`, **REVISE**, with
opening/closing identities equal. It resolves the previous five findings at
static scope and adds M2: `static_preparation.py:1019` checks only `y>=0`, so
positive infinity and excessive positive heights pass; lines 975–1015 read
geometry through global `PACKAGE_DIR` even for another `case_dir`. This reviewer
also inspected those expressions. The current finite wall is not thereby
shown invalid; the defect is a validator that cannot establish its promised
bounds. The nesting test at line 198 also moves an already-invalid `plicRDF`
block, so it does not isolate nesting from reconstruction-method rejection.

**Smallest step and owner:** the E1 Luna owner is now assigned one bounded
revision incorporating M1/M2 and the two smaller follow-ups. Validate finite
coordinates and `0<=y<=A` with a justified serialization allowance, read the
fixture package's own geometry, and test isolated nonfinite/out-of-range,
wrong-provenance and nesting defects. Build the nesting fixture from otherwise
valid `isoAlpha`. Label the wall assumed analytic, not source-derived.
The primary owns any gate/audit amendment and the refreshed preparation-note
hash in its wall-disposition record. Preserve the historical exact review
records and source PDFs. No competing E1 correction owner is needed.

**Acceptance evidence:** canonical source digest checked against the preserved
PDF; clean deterministic regeneration/no-write checks; all 20 manifest entries;
focused static/synthetic tests and Ruff; negative provenance checks that would
detect disagreement with the canonical source identity; new generator,
manifest, note and affected gate/disposition hashes; separate Astra follow-up disposition.
The existing 20-entry manifest pass is insufficient because it faithfully
hashes the wrong string. Any mismatch or unresolved static finding keeps the
package unaccepted. The prior review freeze is released by its returned closing
inventory; freeze the next corrected candidate before follow-up review.

**GPU eligibility:** not applicable; E1 is the CPU OpenFOAM route. Mesh and
characterization are not authorized by this memo or by correcting a digest.
**User/external data:** none for the typo or the explicitly assumed wall.
Actual wall CAD could reduce later reconstruction uncertainty but is not a
reason to stop the authorized static package. **Independent work:** all FluTAS
producer/analyzer/contract work.

## 4. Crossflow negative fixtures

**Severity: high for a claimed positive crossflow run; deferred for the current
quiescent path.** The exact arithmetic record
`FLUTAS_CROSSFLOW_GUARD_ARITHMETIC_PRIMARY_20260925T121916Z.md` and source gate
lines 127–146 retain `dry_crossflow` and `crossflow_four` as negative fixtures.
At U0, `dtmax=0.00049990777606081648 s`, `dt/dtmax=0.20003689638113265`, and
the declared factor is 0.2. They must fail before the first transport interval.
This is a static/host expectation, not a solver observation.

**Smallest step and owner:** candidate owner and independent reviewer preserve
the two exact case hashes, negative guard arithmetic, atomic failure record,
and zero-consumed-interval expectations in offline/host checks. The primary
keeps them out of the positive runtime queue. This safe disposition already
exists; no additional GPU experiment is needed to rediscover the known result.

For later positive crossflow, the primary must name the scientific/numerical
reason for a revised fixed-step margin or dt/schedule and freeze a versioned
case/protocol before results. Derive pulse duration, dose, observation horizon,
all row counts, and transition indices again. A dt reduction with increased
step counts reaches beyond one numeric input: v1.2 and the current analyzer
hard-code 14 intervals/15 states, and the manifest writer checks 14. Any such
change needs matching prospective interface/code review. Raising the factor to
just exceed the known U0 ratio is not a reviewed stability justification and
does not show later states will satisfy the bound.

**Acceptance/stop evidence:** present negative fixtures reject at state zero
with the declared complete prefix, no transported interval and no hidden input
change. A future positive case needs exact amended hashes, independently
derived full-bound expectations, reviewed factor, preserved or explicitly
redeclared dose/duration/horizon, and all B1-pre/B2/launch prerequisites.
Unexpected negative-fixture acceptance or an unauthorized adjustment stops the
handoff. **GPU eligibility:** current fixtures ineligible by known U0 guard
rejection and explicit protocol disposition. **User/external data:** none.
**Independent work:** quiescent qualification preparation and the separate E1
CPU route; crossflow is not a reason to idle either.

## 5. D-NUT-BC, contact angle, and E1 characterization

**Severity: high before E1 characterization; agent-resolvable reconstruction
decisions, not missing user measurements.** The static package already
instantiates a candidate, rather than leaving the fields absent: calculated
`nut` with zero seeds at velocity inlets, `inletOutlet` with zero reverse-flow
value at openings, and `nutkWallFunction` at the wall. The wall alpha candidate
is `constantAlphaContactAngle`, `theta0=90`, `limit gradient`. These remain
unaccepted assumptions (`E1_ROUAIX_CASE1_STATIC_PREPARATION.md:140–152,221–225`;
`E1_CPU_SOLVER_CAPABILITY_AUDIT.md:21`).

**Smallest next step and owner:** after the static-review freeze is released,
the E1 preparation owner supplies a short decision packet tracing each patch
field to the pinned v2512 constructor/equation behavior, initial values,
turbulence correction and reverse-flow treatment. The primary prospectively
selects the candidate and named sensitivities; the independent E1 reviewer
accepts or replaces the exact choices. Do not claim the paper supplies them,
and do not select them using Figure-13 fit quality. External author/CAD/wetting
data would improve fidelity but are not necessary to decide a clearly labelled
approximation.

**Acceptance/stop evidence:** every patch/field type, dimensions, required seed
and reverse-flow value; accepted non-wall `nut` behavior; accepted contact-angle
limit and nominal/sensitivity angles; consistent variable-density/`rhoPhi`
schemes; exact dictionaries and static tests. Once the primary's separate mesh
decision is eligible, retain actual nozzle membership/area/normals, domain and
patch extents, layer/refinement evidence and complete `checkMesh`; a cylinder
face-centre selector does not establish a circular nozzle's actual area by
itself. Verify initial zero water and reconstructed static pressure from
`p_rgh`, density, gravity and reference.

Characterization requires its own prospective purpose/resource/stop protocol,
instrumentation and independent decision. The audit's 1–3M-cell, 300-step,
0.5-ms/0.15-s, 16-rank/18-CPU, 48-GiB, 30-GiB, four-hour figures remain
proposals, not approved allocations. Measure y+, actual Courant bounds,
preclip/postclip/final alpha and correction volumes, flux/ledger closure,
residuals, RAM, step/pressure/I/O cost; use that evidence to freeze comparison
mesh/dt. Do not require those future measured y+ or cost values before the
characterization that is intended to obtain them. Stop on unresolved boundary
choices, unsupported diagnostics, failed static mesh/field checks, or absent
reviewed stops. A short characterization is not the assumed 4.5–5.0-s Figure-13
comparison window.

**GPU eligibility:** not applicable to this CPU solver. The actual blockers are
exact static acceptance, boundary decisions, mesh evidence and the separate
characterization contract, not FluTAS completion. **Independent work:** B2 and
candidate5, plus preparation of E1 diagnostic/monitor contracts in disjoint
files. E2 execution still requires an accepted E1 advancement disposition.

## 6. Source CFD, numerical limits, and launch contract

**Severity: high; the remaining real release gate.** The current analyzer
accepts exactly `phase-property-stage-audit.csv`,
`boundary-velocity-stage-audit.csv`, and `timestep-restriction.csv`
(`flutas_source_analyzer.py:31–34,1624–1628`). The broader B2 requirement also
covers `source-flux.csv`, `source-offmask.csv`, `rate-check.csv`,
`boundary-ledger.csv`, `mass-ledger.csv`, and `velocity-audit.csv`; their
existing production purpose is recorded in the candidate4 readiness audit
table at lines 97–108 and in the source gate. A review of the three-file
module cannot silently stand for this broader conservation acceptance.

**Smallest next step and owner:** the primary completes a quantity-to-artifact
matrix and freezes a companion conservation/input/launch contract. A disjoint
Luna analyzer/launcher assignment follows that interface, with an independent
scientific review. Retain the accepted v1.2 three-file sub-contract; do not
expand its exact file set without an explicit version decision. The launcher
must stage/check the complete inputs, pin executable/image/patch/contract and
analyzer identities, enforce reviewed resource/time/failure rules, collect
parseable resource samples, retain failed bundles, and stop before later
stages when an attempt fails. Its fake-executable positive/negative tests are
CPU work that can precede solver release once the interface is stable.

**Acceptance evidence:** independently recomputed per-slot mass and vector
momentum, all-six-face signed transport and periodic cancellation, inventory
change, source attribution, net volume flux, maximum/L1 divergence, phase and
velocity stage joins, full source-order AB2 restriction, and correct
inactive/post-shutoff treatment. For the unchanged uniform quiescent fixtures,
ten active intervals give 0.72 kg per slot and 2.88 kg for four;
normal-completion source rows are 0/14/56 for dry/one/four, interval diagnostics
14, state ledgers 15; new phase/velocity/timestep totals are 672/516/15.
Review early-stop exceptions independently. Zero dry/off-mask attribution and
the pulse state transitions need their declared exact checks; do not substitute
requested flux for actual geometric phase flux.

Freeze source-supported numerical limits and a fixed-step margin, rather than
copying CPU `Co=0.5/0.25` or the unapproved 0.1% box budget. Review the direct
FFT/tridiagonal pressure solver's iterative-residual `not_applicable`
disposition and its actual projection/continuity criteria. Resource ceilings,
sampling, exit semantics and failure precedence must be explicit. Until these
are accepted, a structurally complete bundle remains `not_adjudicated`.

**GPU eligibility:** source CFD is closed until exact B1-pre, complete B2,
numerical/resource limits and launcher review all pass. Then the primary may
launch one locked GPU source task at a time, one solver rank, in order:
quiescent dry → one slot → four slots. Independently analyze/dispose each before
the next. B1-runtime is the resulting measurement, not a circular precondition
for attempting the same stages. A positive crossflow amendment is separate;
the 1–3M-cell performance pilot is later and separately reviewed. No 5–10M-cell
proposal follows from a tiny source check or a smoke test alone.

**User/external data:** none for this synthetic implementation qualification.
**Independent work:** all specified CPU review, input binding, serialization,
conservation fixtures, launch tests and E1 work. No later physical stage should
be run merely to use idle hardware.

## Worker ownership and compute queues

The opening live agent list showed the primary and three workers: this deblocker,
`astra_warden_checkpoint`, and `candidate4_source_readiness_audit`. The latter
two are reused agent names: the primary's 12:34 ledger identifies their current
assignments as E1 Astra exact review and candidate5 Luna production work.
The completed B2 Luna implementation is not a fourth active worker. There is
no confirmed overlapping write ownership in that arrangement. By closing
inspection, the primary's 12:42 ledger had rotated the Luna slot to the E1
correction (1 CPU/2 GiB) and the Astra slot to candidate5 exact review. This
deblocker remained the third worker. These are appropriate dependent handoffs,
not additional workers. Do not infer current work or model from an old agent
name.

The 12:23 blocker-plan wave table is therefore stale. Update it at the next
handoff, and keep roles, compute jobs and measured utilization separate. This
memo's inspection overlapped a two-CPU-capped build; it did not reserve a
second build or a GPU task.

| Queue / owner | State at evidence cutoff | Next action, prerequisite and ceiling |
|---|---|---|
| Candidate5 / CPU | Retry and handoff finished; Astra exact review active with preliminary timestep-format/phase-order findings. | Complete the current read-only review. Assign one subsequent Luna correction with actual producer-to-analyzer byte tests; changed builds retain the existing 2-CPU/6-GiB cap. No unchanged rebuild. |
| E1 Luna / CPU | Exact follow-up returned REVISE; one bounded static correction active. | Resolve M1/M2 and smaller findings, regenerate once, supply exact identities and isolated negative fixtures. 1 CPU/2 GiB; no mesh/solver/GPU. |
| Astra deblocker / CPU | This memo completes the assigned advisory deliverable. | The primary can reuse the Astra review slot for the ready B2 exact review; no new analyzer edits during that review. |
| Primary / CPU | Case grammar, image identity and conservation/limit/launch interfaces are unresolved. | Freeze these interfaces now; they do not require an additional worker or user input. Archive explicit accept/defer/reject dispositions for this memo's recommendations. |
| Next Luna implementation slot / CPU | Can start after a current worker frees and its specific interface is frozen. | Prefer the disjoint staged-input binder; E1 correction already has an owner. Do not assign two owners to the existing analyzer. Use Luna Max for implementation, Astra Max for independent review. |
| Candidate5 source-disabled GPU smoke / primary | Blocked by exact candidate/build/runner review. | Once accepted, existing wrapper uses `run_local.py --threads 2 --gpu --timeout 600` and one shared GPU lock; archive a new immutable result with source input absent. Overlap independent CPU work. |
| Source GPU trials / primary | Blocked by production identity/input binding, broader B2, approved limits and launcher. | No source job now. After release, one ordered attempt, then analysis/review, stopping on first failure. |
| E1 mesh/characterization / primary | Blocked by the exact static/decision/contract dependencies above. | CPU-only; allocate from measured headroom after its distinct release. Do not treat the draft 18-CPU ceiling as a reservation. |
| Repeated candidate3/4 smoke or P1 replay | No new evidence need. | Leave unqueued. Their readiness does not make unchanged reruns useful. |

Maintain two CPUs for responsiveness and at most **18 shared CPUs across all
actual processes/ranks/jobs**. For example, a two-CPU GPU wrapper plus a
two-CPU build and one-CPU offline test uses five, not eighteen per job. Set
BLAS/OpenMP to one inside process-parallel work. A future 18-CPU mesh or
characterization would need other compute allocations reduced or postponed;
worker reasoning occupancy is not an MPI/core allocation. Refresh `make doctor`
and actual process/device headroom before scheduling new compute. Increase
parallel build/mesh resources only from an approved task and measured scaling,
not to fill nominal capacity. One RTX 5090 means exactly one GPU-owning job,
with the shared launcher lock; never schedule parallel GPU trials.

Checkpoint 9 (`PROJECT_WARDEN_20260925T121128Z.md`) remains the last archived
Warden memo in the inspected ledger, with one primary-disposed checkpoint
since it. Completed build evidence or this memo is not automatically another
count until the bounded handoff and primary disposition are recorded. Coalesce
the upcoming completed handoffs/eligibility transition into the next Warden
snapshot. Do not create duplicate broad audits instead of exact code review,
input-contract completion, or the E1 correction. Warden advice does not approve
the scientific gate.

## What is deferred science or external data

The immediate blockers above are engineering, exact review, explicit
reconstruction decisions and unfilled pre-run contracts. They are not a need
for fresh permission to use provisional inputs. The FluTAS synthetic periodic
box does not supply E1's aircraft wall and external inlet/outlet model; the two
routes can progress independently.

E2 scientific release still follows accepted E1, despite its accepted
implementation. E3 exact four-port grouping and terminal histories remain
source-limited; bounded geometry/history preparation can proceed without
inventing a measured mapping. Conservative VOF/parcel/ground interfaces and
synthetic conservation/frame tests can be prepared, but production descent
needs qualified A/B physics, a direct-VOF attempt, loading/coupling decisions
and handoff-location/map/L95 evidence. E4/E5 matched validation needs source,
registration/uncertainty and measured-data support; E5's completed six-row
transcription should be reviewed, not independently re-extracted yet again.
Actual outlet/foam/discharge and deposition evidence are required for built
Restás claims, not for the presently authorized idealized preparation.

If reconstruction uncertainty prevents a defensible E1 comparison, record a
descriptive/inconclusive result and its consequence for E2; do not silently
rename a failed gate or change stage order. Only E0 is scientifically complete.
No present artifact establishes E1–E6 success, ground delivery, foam behavior,
built-device performance, fire suppression or a fourfold gain.

## Exact evidence inventory and inspection limits

| Artifact | SHA-256 inspected |
|---|---|
| Accepted observability schema | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| Candidate5 retry patch | `22c80953e3646dd6ba01ca9aa877a61b8e009c7ebd25d269c1b9aa8c2207d543` |
| Candidate5 failed metadata | `c9241e96357d2391a0bf1a3a3252292874a2ff83a4a59ddae35f13aebff22e6e` |
| Candidate5 successful metadata | `c183745c9911c741f4bea184f81c95b9c87ffcdf9de5a41f3a227a342294f23e` |
| Candidate5 build script | `eb578d8e9641459e3c238231ac33f51a9ae1787ed180943a4f55cc637e04520d` |
| Candidate5 manifest writer | `79219cfb371f94b9949c19617ca454487d630870ff40d4484ee816261ffc6304` |
| B2 analyzer source | `77c94d49c78a0581bb7c2a5f4f63cf85d22eea187133c92f604ba1796e103868` |
| B2 analyzer tests | `a2ab5203f13a84fbc1868bf634dda21375be6981b4eaa3ebbef31c74b9f4b7d1` |
| B2 implementation note | `727c7133f8bb11f548342fc2c3e247f44d2fbe6fd3e34f3a74156a2c41cb7e5a` |
| E1 generator | `2f31be31789c97a0ba4446aa6378640b024c870f5429eb010915bc4969cf523a` |
| E1 static checker | `cac2e57e6b199ef961f312a115657849b25ded9d0a9fd0653b4a3531c8625acb` |
| E1 generated domain JSON | `b15391274f9796266a2a15b4b2707d74d0febef4657d148fb07ad69bd6a0f7fa` |
| E1 20-file manifest | `291c9c48733c3500954a75ed3e172a3185e0be4fe4dbe20ed2ba27d790cedbcd` |
| E1 alpha capture map | `c0e8e1d3f51e3b0ac683039443a59a5fd07ad0f64656fcb488df469ce33abefd` |
| E1 focused tests | `342d68113dfdc439d77069a85e5e411fc588f8af6e9b5070d84eb9b2f0e0305e` |
| E1 preparation note | `ac47a5fabb9431b26b285647fd26f7715f318a58959d3fe9c1551e622e6618f4` |
| E1 amended gate | `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` |
| E1 historical capability audit | `a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32` |
| E1 exact static follow-up | `9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847` |
| STATUS snapshot read at 12:37 UTC | `70dce44ed95d39df6ea86bcdbb6b340b515e0179fa52e4d550212578ad93a919` |
| STATUS closing snapshot read at 12:43 UTC | `c0289bf114cc365486abf96be050fc4c9965f431b4d2915cf13796bab3a9e1a1` |
| STATUS preliminary-candidate-review update read at 12:46 UTC | `3210b6228ecf2fd1e96243cd36c228f9d0de5bf99d5ed6a52272803c94b28495` |
| Blocker-plan snapshot read at 12:37 UTC | `10a5ad1fb33140776a4b7d67e4f0ee2f2aa1d0f8ce737a395ef2c18ff91d54cc` |

Read-only commands included targeted `rg`/`sed`/`cat`, `git status --short`,
SHA-256 reads, `sha256sum -c CASE_SHA256SUMS` (20 OK), live-agent listing,
`docker ps`, and `nvidia-smi`. The local PDFs
`/tmp/Rouaix_28516.pdf` and `/tmp/rouaix_e1_independent.pdf` and Figure-3 PNG
were rehashed; no source file or rendered image was modified. Test/build
results reported here come from named existing logs or explicitly attributed
handoffs, not tests rerun by this reviewer. The workspace remains broadly dirty
and untracked; this is an artifact-specific advisory snapshot, not a claim of
a clean repository or an exact scientific gate review.
