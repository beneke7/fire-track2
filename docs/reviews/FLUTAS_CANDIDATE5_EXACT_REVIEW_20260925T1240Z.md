# Candidate5 exact candidate, producer/analyzer, and regression review

Reviewed by Astra Max under `.codex/agents/general_reviewer.toml`, 2026-09-25
12:40–12:52 UTC. This review is independent of the candidate and analyzer
implementation handoffs. The reviewer wrote only this memo, performed
read-only source/hash/image inspection and in-memory CPU checks, and launched
no build, container, solver, or GPU process.

| Scope | Disposition |
| --- | --- |
| One bounded, source-disabled local GPU regression of the exact image below | **ELIGIBLE**, using the unchanged reviewed outer launcher and lock. The primary retains the launch decision. |
| Schema-v1.2 candidate-build receipt / OCI identity compliance | **NOT COMPLIANT / INCOMPLETE**. No `candidate-build.json` or OCI manifest digest is provided. The Docker image ID is not an OCI manifest digest. |
| Exact producer/analyzer conformance, B1-pre, B2 production acceptance, source-enabled execution, source CFD | **REVISE / CLOSED** for the findings and missing contracts below. |
| B1-runtime, E1–E6, field validity, or a scientific gate | **NOT APPROVED**. No such result is established by this review. |

## Exact identities and unchanged opening/closing snapshot

The following hashes were checked at opening and again at closing; they are
unchanged. All **51** entries in the complete
`containers/flutas/candidate5/evidence/runs/20260925T123352Z-2100410/handoff-hashes.txt`
passed `sha256sum --check` both times. The inventory covers the candidate files,
all case inputs, the failed build, the successful build, its extracted
executable, and the postbuild test output. Its own hash is pinned below. A
preliminary progress message incorrectly called this 53 entries; the checked
inventory contains 51.

| Artifact | Opening SHA-256 = closing SHA-256 |
| --- | --- |
| `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| `containers/flutas/candidate5/source-boundary.patch` | `22c80953e3646dd6ba01ca9aa877a61b8e009c7ebd25d269c1b9aa8c2207d543` |
| Successful build `handoff-hashes.txt` | `0f6dde82531c6762cf56bdadb6b35feb6bf8f2f70f742691cd965e66ba031c84` |
| Successful build `metadata.txt` | `c183745c9911c741f4bea184f81c95b9c87ffcdf9de5a41f3a227a342294f23e` |
| Successful build `docker-build.log` | `0a51f9e160799c13724163639f01844a2ad2b8c7f5c2b4604c267cc620f986f4` |
| Successful build `postbuild-manifest-test.txt` | `99eebf718ef88a505be2a5449fe59613ba95780b0433b8a6bb102cb7f50e3031` |
| Successful build `flutas.two_phase_inc_isot` | `fe5231fe9ef5421a28a9627dfd08c784644039fe8bb275a5315a992f3d635ff1` |
| `containers/flutas/candidate5/Dockerfile` | `4c0d59fce78c6b08db5b3a170d7c8577501fd4e067c4cd9729f33466770ac246` |
| `containers/flutas/candidate5/build.sh` | `eb578d8e9641459e3c238231ac33f51a9ae1787ed180943a4f55cc637e04520d` |
| `containers/flutas/candidate5/tools/write_run_manifest.py` | `79219cfb371f94b9949c19617ca454487d630870ff40d4484ee816261ffc6304` |
| `src/aerial_drop/flutas_source_analyzer.py` | `77c94d49c78a0581bb7c2a5f4f63cf85d22eea187133c92f604ba1796e103868` |
| `tests/test_flutas_source_analyzer.py` | `a2ab5203f13a84fbc1868bf634dda21375be6981b4eaa3ebbef31c74b9f4b7d1` |
| `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` | `727c7133f8bb11f548342fc2c3e247f44d2fbe6fd3e34f3a74156a2c41cb7e5a` |
| `containers/flutas/run-candidate-gpu-regression.sh` | `282bfce5c5f2f86682318e26e7f9a6473e3277090a362fe3eb28232698c83d36` |
| `containers/flutas/run-candidate-gpu-regression-locked.sh` | `9c88514318ed24ce30b607f3fdd2f9b3b20bcf3e9227a5cc9aa24817a7b24492` |
| `containers/flutas/run-gpu-tests.sh` | `e90285710e1ce77724d85bcf331c2fe993fdd6367cf3ccec159f81c70c88757c` |
| `scripts/run_local.py` | `13e3d2fd6fcebe58ad623af339de36ed4d29f842b7588c18c59e750ae16d73db` |
| `experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md` | `b77ef87ae4a086f3e4cbce61e6ac22fb6c45d9aefab0988b9acde0b1db48928d` |

The eligible **local Docker image ID** is
`sha256:7bad4d20c55fa718321de53f49083f98042be522b6848b73903c7c8b005202d4`.
Its build tag is
`track2/flutas-source-boundary:5982106-candidate5-20260925T123352Z-2100410`.
Read-only `docker image inspect` independently returned that exact ID,
`RepoDigests=[]`, and `Entrypoint=["/bin/true"]`. No OCI manifest identity was
inferred from this result. The upstream commit is
`598210616bebd51f7d51f61455f196e6f3479916`; the base image ID in the receipt is
`sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8`.

The local working source `/tmp/candidate5-upstream` has this upstream commit;
`git diff HEAD --binary | sha256sum` equals the reviewed patch hash. It was
used only to read complete call context. The four upstream source hashes in
schema lines 269–274 were independently checked against
`/tmp/flutas-pristine-5982106` and match. Additional source identities used for
the time analysis are upstream `main__two_phase_inc_isot.f90`
`ef4e55d8d5d6de489bb6e6c986a5fcc15f44e16170e4cf4add7b9e2559175a03`
and `src/rk.f90`
`6f86e54d8c95423099526228d72fcb3ee2720c9ac96a0692c486c0fc119a2e42`.

## Why the local-image regression may proceed

The source gate explicitly separates a reviewed source-disabled regression
from B1-pre/source execution (`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md:313–320`);
schema lines 506–513 make the same distinction. The existing launcher contract
pins a **Docker image ID**, not a candidate5 source-run manifest. The missing
OCI receipt therefore blocks v1.2 source-bundle compliance but does not block
this separate, exact-local-image software check.

The unchanged outer launcher verifies the supplied image against the frozen
expected ID and passes that ID to the locked runner. It uses
`scripts/run_local.py --threads 2 --gpu --timeout 600`, retains each attempt in
a new directory, and hashes its evidence on exit. The locked runner checks
both the embedded source patch and upstream runner hash and rejects a regular
file or symlink named `source-boundary.in` in both template and staged bubble
case before starting any GPU stage (`run-candidate-gpu-regression-locked.sh:28–54`).
It explicitly selects `/usr/local/bin/flutas-gpu-tests`; it does not depend
on the candidate's default entrypoint. The source reader returns without
enabling source mode when that input is absent (`source-boundary.patch:205–211`),
and the source-free `advvof` branch supplies no optional source arguments
(`source-boundary.patch:138–147`). The source serialization findings below
are consequently outside the path this smoke exercises.

The allowed check is the inherited sequential OpenACC kernel, two-rank
CUDA-buffer MPI smoke, and one-rank upstream rising-bubble solver/checker.
That upstream bubble solve is an explicit part of this software regression.
It is neither a dry source case nor source-boundary evidence. PASS requires
the expected GPU/code-object markers, normal solver completion without fatal
markers, a finite final time at least 3 s, upstream `True True`, and finite
sampled GPU/container resources. The same two-CPU/600-second envelope and
shared GPU lock apply; no source case or larger pilot is included.

The primary may invoke the frozen outer launcher with the following exact
arguments after its routine resource/queue check. This command was **not run
by the reviewer**:

```sh
containers/flutas/run-candidate-gpu-regression.sh \
  sha256:7bad4d20c55fa718321de53f49083f98042be522b6848b73903c7c8b005202d4 \
  sha256:7bad4d20c55fa718321de53f49083f98042be522b6848b73903c7c8b005202d4 \
  22c80953e3646dd6ba01ca9aa877a61b8e009c7ebd25d269c1b9aa8c2207d543
```

## Findings requiring revision before source eligibility

**H1 — High, deterministic producer/parser mismatch: timestep CSV retains
descriptor padding.** `source-boundary.patch:1544–1549` writes physical fields
directly with `ES24.16E3`, unlike the audit writer's trimmed helper. A positive
zero field is ` 0.0000000000000000E+000`, which violates schema lines 498–503
and analyzer `_decimal` at `flutas_source_analyzer.py:286–303`. An in-memory
valid bundle with this exact token returns `INVALID_NUMERIC`. The canonical
producer test at `tests/test_candidate5_observability.py:486–493` uses
`assertRegex` with a pattern ending in `\Z` but lacking a start anchor; regex
search starts after the leading blank, so that test passes the defect.
**Smallest fix:** serialize every finite timestep number through the same
left-trimmed, zero-normalizing helper, use `fullmatch` for every numeric token,
and pass actual compiled-helper output through the independent parser. Preserve
non-finite raw evidence as rejection evidence; do not trim away its failure.

**H2 — High, deterministic row-order mismatch: phase bottom-return rows are
emitted last.** The producer declares pairs xlow, xhigh, ylow, yhigh, the three
top classes, then bottom (`source-boundary.patch:1222–1228`) and writes them in
that order at lines 1326–1332. The frozen phase table and schema lines 322–325
require bottom immediately after yhigh. The analyzer correctly uses that order
at `flutas_source_analyzer.py:109–117,954–965,1127–1130`. Reordering a valid
in-memory bundle to the producer's exact sequence returns `ROW_ORDER`.
The producer tests duplicate the producer ordering at
`test_candidate5_observability.py:36–44` and select rows by keys rather than
checking the frozen complete order. **Smallest fix:** align the producer's
phase pair ranks with v1.2 and assert the complete ordered sequence against an
independent schema fixture, including all three pre-momentum properties.

**H3 — High for exact time conformance: the producer records the accumulated
AB2 clock, while the schema/analyzer demand index-multiplied time.** The
endpoint call passes the solver's `time` (`source-boundary.patch:185–186`),
which is written unchanged at lines 1545–1549. Upstream main line 610 adds
`f_t12`; upstream `src/rk.f90:118–132` computes it as `f_t1+f_t2`, including
`1.5*dt` and `-0.5*dt` after the first AB2 step. The schema defines
`time_start+k*dt`, and `flutas_source_analyzer.py:1436–1440` compares exact
binary64 equality. A source-order binary64 transcription with `dt=1e-4`
first differs at state 2: accumulated `0.00020000000000000004`, required
`0.00020000000000000001`; feeding those times to the analyzer returns
`TIMESTEP_TIME`. This is an arithmetic/interface finding, not a claim that a
source solver was run. Production `-fast` compilation has not independently
established a different accepted clock or bitwise arithmetic behavior.
**Smallest fix:** freeze and implement one explicit time representation; if
v1.2 is retained, emit the declared index-based diagnostic time while preserving
the actual solver clock separately where required. Otherwise make a prospective
reviewed schema amendment for the exact upstream recurrence. Add a multi-state
compiled-helper-to-analyzer check, not a one-row check or a tolerance added
after a run.

**H4 — High for v1.2 provenance, not a smoke blocker: required candidate receipt
and OCI manifest identity are absent.** Schema lines 354–360 require
`candidate_sha256` to hash `candidate-build.json`, with an OCI image digest,
upstream source/patch/build hashes, compiler/flags, command and executable hash.
`build.sh:65–86` records textual metadata, Docker `.Id`, empty `.RepoDigests`
and the executable, but creates no candidate receipt. The actual build log
records `-fast -cuda -acc -gpu=cc120,cuda13.3` and no `_SINGLE_PRECISION` or
heat macro. Those logs are useful evidence, not the missing receipt.
The writer's `image_digest` regex at `write_run_manifest.py:175–200` cannot
distinguish a configuration/image ID from a manifest digest merely because both
are written `sha256:...`. **Smallest fix:** produce and independently review
an immutable receipt bound to a real OCI manifest, or prospectively review a
schema change that explicitly identifies a local-image-only source contract.
Never insert this local Docker ID into a field described as an OCI manifest
digest. No publication or registry upload is required by this review.

**M1 — Medium, malformed first-failure evidence can be called structurally
complete.** In `flutas_source_analyzer.py:1053–1070`, if either value is a
recognized non-finite token, the other value is not parsed. A complete phase
audit-stop fixture with `expected=NaN, observed=garbage` returns
`structural_disposition=complete`, although its evidence remains failed and
its overall decision remains `not_adjudicated`. Lines 1041–1052 also check only
global padded bounds; an xlow first failure `(20,10,41)` is accepted even
though xlow requires `i=0`. This invalid xlow location already occurs in the
test helper at `tests/test_flutas_source_analyzer.py:343–352`.
**Smallest fix:** parse each value independently as an allowed non-finite token
or finite binary64 decimal; validate failure locations against the declared
face/component scan domain and frozen mask/schedule. Keep legitimate audit
failures structurally valid but reject malformed evidence. Add independent
negative fixtures for each defect.

**M2 — Medium, arithmetic overflow escapes the analyzer's structured failure
path.** `_timestep_expectations` at `flutas_source_analyzer.py:1383` may raise
`OverflowError` for a finite binary64 `dtic_raw=1e200`; `analyze_bundle` at
lines 1613–1683 catches only `AnalyzerError`. The in-memory probe raises
`OverflowError: (34, 'Numerical result out of range')` instead of returning a
structural failure. Likewise inverse checks occur before the full binary64
range validation at lines 689–724. This does not create a PASS, but it breaks
the promised deterministic report on nonconforming numerical evidence.
**Smallest fix:** validate binary64 range/nonzero divisors before reciprocal
operations, convert arithmetic overflow/domain errors to explicit analyzer
failure codes, and exercise finite-intermediate overflow separately from
literal NaN/Inf tokens.

**M3 — Medium, candidate-side reciprocal validation and realistic operand
tests are incomplete.** The actual 42-entry arrays are correctly captured,
but `source-boundary.patch:1163–1169` checks size and finiteness only; it does
not validate each stored inverse against `1._rp/spacing` as schema lines
191–204 require. The analyzer does perform reciprocal checks. The helper
capture test at `test_candidate5_observability.py:405–427` uses every spacing
equal to `0.025` and every inverse equal to `40`, so it does not exercise the
rounded-coordinate variation that motivated v1.2. **Smallest fix:** add the
candidate-side reciprocal assertions and a nonuniform-in-the-last-bits,
42-entry fixture derived from the pinned `initgrid` operation sequence; verify
the bytes and exact analyzer recomputation without substituting a uniform
vertical operand. Test with the production arithmetic flags before claiming
exact producer/analyzer numerical compatibility.

## Confirmed implementation behavior and evidence limits

The capture call precedes initial U0 velocity audit and timestep evaluation
(`source-boundary.patch:83–100`). It passes actual `dzc`, `dzf`, `dzci`, `dzfi`
arrays, not reconstructed constants. The pinned application allocates indices
`0..41` with one halo and initializes the inverse arrays from its real spacing
arrays. The JSON helper serializes all 42 values as round-trip decimal strings.
This supports the intended pre-U0 evidence boundary, subject to M3 and the
absent source launcher/receipt.

The inspected phase scan visits every declared shell location: x owns periodic
corners, y excludes x halos, and z scans interior i/j. Per-class scans preserve
lexicographic first failures and atomic complete stage writes. VOF stages emit
only alpha from `vof`, `dvof1`, and `dvof2`; pre-momentum uses the post-advection
`vof/rho/mu`. Velocity scans cover both 162×86 padded rectangles, all three
components and declared empty classes. The frozen centered masks leave the
extra periodic-halo positions outside every slot; direct membership therefore
agrees with wrapped membership for these exact masks. The expected return uses
input slot order then j/i accumulation and the declared denominator. These are
source-read findings, not runtime proof.

The finite-pair subtraction overflow path retains an overflow flag and `+Inf`
at `source-boundary.patch:1015–1026,1101–1104`, then stops after flushing the
whole stage. It does not replace overflow with a finite sentinel. The
first-failure expected and observed tokens are handled independently in the
producer. The timestep scan preserves its first non-finite directional rate
instead of letting MPI maximum hide it, records failed raw diagnostics,
flushes, and exits nonzero (`source-boundary.patch:1482–1554`). The analyzer
rejects non-finite timestep tokens. These good source-level behaviors do not
resolve M1/M2 or certify arithmetic under all production optimization flags.

The build recipe contains no hidden solver launch. Its Dockerfile applies the
patch, compiles host-only helpers and the GPU executable, checks `sm_120.cubin`,
and sets `/bin/true`. `build.sh` only creates an unstarted `/bin/true` container
to copy the executable. The manifest writer contains no solver invocation.
The successful build receipt declares no GPU and no solver run, and preserves
the previous status-2 build attempt. Build evidence records 19 static/input
checks, 13 compiled-host observability checks, and three manifest checks with
one skipped in-container. The separately hashed postbuild output conclusively
records **all four manifest-writer tests passing without a skip**, exit 0,
with `CANDIDATE5_SCHEMA_PATH` set and the exact accepted schema hash recorded.

Those four tests establish the writer fixture behavior only. In particular,
`test_run_manifest_writer.py:105–151` uses synthetic receipt/runtime data and
header-only outputs while declaring normal completion; it does not send real
Fortran output through the independent analyzer or establish the missing
receipt. The writer deliberately binds supplied supervisor metadata and
output hashes rather than adjudicating the output; that division requires
the independent analyzer and execution contract before a source attempt.

The analyzer's existing 29 tests were independently rerun with
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider
tests/test_flutas_source_analyzer.py`: **29 passed in 0.28 s**. `bash -n`
accepted both GPU regression scripts, candidate build script and host test
script. No compiled tests were rerun by the reviewer. The baseline in-memory
bundle returns structural/evidence `complete`, `not_adjudicated`, and counts
672/516/15. Separate in-memory changes, with file/manifest hashes refreshed,
produced the exact outcomes cited in H1–H3 and M1–M2. No probe wrote a run
bundle or changed reviewed source files.

## Remaining release boundaries and smallest handoff

The primary can schedule the one eligible source-disabled smoke now and keep
its result separate from these required CPU revisions. Preserve this exact
candidate and its review evidence when making a successor patch. Route producer
serialization/order/time/reciprocal fixes and actual helper-to-analyzer checks
to a bounded implementation owner; route analyzer failure-value/domain and
overflow fixes to a separate owner with disjoint files. Re-review the exact
successor hashes and updated tests before any source eligibility decision.

Independent of these defects, the analyzer currently receives externally
supplied scan counts and timestep inputs; it does not derive and bind them to
the staged `source-boundary.in` grammar or independently stage/walk the case.
The three-file v1.2 interface excludes inherited mass, momentum, geometric
flux, offmask, rate and continuity ledgers. A separately accepted contract and
analyzer must cover them. Numerical limits, fixed-step margin, direct-pressure
residual applicability, resource ceilings, supervisor stop provenance and the
source execution contract remain open. Crossflow inputs retain their expected
U0 guard rejection and must not be silently altered into positive cases.

No B1-pre/B2 production acceptance, source-enabled GPU attempt, source CFD,
larger pilot, or E1–E6 scientific result is approved here. The local-image smoke
eligibility is a bounded software check and makes none of those claims.
