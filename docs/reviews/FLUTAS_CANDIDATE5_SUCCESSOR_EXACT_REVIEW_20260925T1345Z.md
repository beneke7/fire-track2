# Candidate5 successor exact implementation and smoke review

Independent reviewer: **gpt-6-astra, max**, under
`.codex/agents/general_reviewer.toml`. Review date: 2026-09-25 UTC; closing
identity snapshot 13:49:56 UTC. Only this memo was written. No build, container
start, solver, image export, GPU process, or compiled helper was launched.
The primary remains the compute scheduler and launch decision owner.

| Scope | Disposition |
| --- | --- |
| One source-disabled GPU regression of the exact local image and patch below through the unchanged locked runner | **ELIGIBLE** after the primary's current resource/queue check; exact command and limits below. |
| Prior producer H1/H2/H3 repairs | **Verified at source and archived host-helper scope.** This is not production arithmetic or source-run approval. |
| Prior producer M3 | Reciprocal checks and realistic positive fixture are implemented; **production-flag compatibility remains unproved**. |
| Aggregate source-level producer acceptance | **REVISE / CLOSED**: source-contract H4's spacing-index defect is present in this exact successor. |
| Schema-v1.2 immutable build/run provenance | **Not established by this build bundle**; no receipt or OCI identity substitution is permitted by this review. |
| B1-pre, B1-runtime, B2 production, source-enabled execution, source CFD, pilot, E1–E6 or scientific gate | **CLOSED / NOT APPROVED**. |

## Exact snapshot and build evidence

The reviewed successor evidence directory is
`containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/`.
All **15** entries of its `SHA256SUMS`, all **16** build-input hashes in
`metadata.txt`, all **15** case-input hashes, and the build-status-file hash
match actual bytes at both opening and closing. The evidence directory has no
unlisted file except `SHA256SUMS` itself. Opening and closing hashes in the
table at the end are identical.

The eligible immutable **local Docker image ID** is
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`.
Read-only `docker image inspect` returned that exact ID, `RepoDigests=[]`,
and `Entrypoint=["/bin/true"]`; its recorded tag independently resolved to the
same ID. This is a Docker image/configuration ID, not an OCI manifest digest.

The archived native executable hashes to
`99cf345a2d8465d3be2993567907837e1988041f6a8a16d44199b8cda9111865`.
The build log records successful patch checking/application, native compilation
with NVHPC 26.9, `-fast -cuda -acc -gpu=cc120,cuda13.3`, and an
`sm_120.cubin` code object. The recipe performs CPU compilation and code-object
inspection, then defaults to `/bin/true`; it does not invoke a solver.
The build envelope is 2 CPUs / 6 GiB / network disabled / no GPU. These are
build limits, not an invented runtime memory limit.

The pre-build log records 19 source/static tests, 16 observability tests and
four manifest tests passing without skips, with exit 0. The Dockerfile's
separate test pass skips the multi-state analyzer test and one schema-dependent
manifest test because their external roots are absent. The handoff correctly
distinguishes these runs. The failed packaging attempt
`20260925T132519Z-2120267` is preserved: its build-log hash
`259caa24cde18904afc387b9185e1e66a74157e2c184479f89afe71f8bdb36f2`
and metadata hash
`70348514ac765ac0c74406ec5c57c2a66f418f9b2a845fee4b1bb917f40397da`
both match.

I independently applied every successor patch hunk **in memory** to exact git
objects at commit `598210616bebd51f7d51f61455f196e6f3479916`, checking context
and hunk counts. This passed without changing a checkout. The resulting main,
source include and VOF hashes are respectively:

- `src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`:
  `206c99e2a0695fa3533bf76877a887fb25e3438b6a13a8eb939fd7e54ee54d6d`.
- `src/restas_source.inc`:
  `775695dc665e42851bb70e5de6945b775a612509a9fdf3095e7983afa2145732`.
- `src/vof.f90`:
  `657e4d7e4c7ec0739b506ae806c9bd5e80df7aaa238e248cb9fab4ee43fcea61`.

These are reconstructed source identities, not an inspection of files inside
a running container.

## Prior repair dispositions

**H1 — finite timestep serialization: repaired.**
`source-boundary.patch:1558–1568` writes every finite real column through
`trim(restas_source_real_text(...))`; the helper at lines 1113–1124
left-adjusts descriptor padding and normalizes either zero sign to `0`.
The revised token test uses `NUMBER.fullmatch`
(`test_candidate5_observability.py:807–816`), and the multi-state test passes
actual compiled timestep CSV bytes to the independent analyzer. Nonfinite
restriction output is still flushed and rejected; no finite sentinel was
introduced. The repair concerns the v1.2 timestep table; inherited six-ledger
numeric grammar is a separate source-release interface.

**H2 — complete phase row order: repaired.**
Patch lines 1232–1240 rank bottom return fifth, followed by top active,
inactive and off-mask classes, then serialize by pair and property at
1335–1344. This matches the frozen schema's face/class order and
`alpha,rho,mu` property order. Tests at 427–436 assert the entire ordered
group against a separately declared frozen tuple, including all three
pre-momentum properties; both sides of the pulse-start edge are exercised.
The archived host suite passes this check. The 15-state analyzer integration
test does not itself substitute compiled phase rows into its synthetic
bundle, so it must not be described as a three-table producer-to-analyzer run.

**H3 — diagnostic time: source repair follows the primary's retained-v1.2
decision.** Capture at patch 1178–1179 preserves the solver start time and
fixed input step before U0; line 1476 evaluates
`restas_time_start + real(state_index,rp)*restas_time_fixed_step`.
The solver's accumulated `time` remains unchanged and is still checked for
finiteness. The dynamically compiled test variant emits U0–U14 using an
independently accumulated AB2 clock as its argument, while the producer emits
index-based times. Tests at 852–906 check all 15 times, explicitly distinguish
state 2, accept the actual CSV, and reject substituted accumulated times with
`TIMESTEP_TIME`. This includes states 2 and 12, but the test does not evolve a
source plume or exercise its actual pulse dynamics. The noninitial guard
requires the captured runtime inputs. No time tolerance or schema change was
added.

**M3 — reciprocal capture: source repair and realistic positive host fixture
are present.** Patch 1170–1177 rejects nonpositive spacings/inverses and
compares scalar and every vertical inverse against `1._rp/spacing`.
Unlike the three inherited helpers discussed below, this capture uses explicit
`0:` lower bounds (1158), retaining the correct 42 entries. The test fixture
reproduces pinned `initgrid` face differences and halos (test 80–106 and
263–305), checks both upstream `initgrid` and RK hashes, and compares emitted
spacing and inverse values exactly (838–850). The older constant-spacing
capture check still exists, supplemented by this new fixture.

**M3's production numerical acceptance remains open.** Both the ordinary host
suite and `_compile_multistate_helper` use CPU flags without `-fast`,
`-cuda`, or `-acc` (host script 15 onward; test 208–216). Native compilation
proves buildability, not that the optimized initialization, reciprocals,
nonfinite handling and restriction arithmetic produce the same accepted
bytes. Negative compiled reciprocal fixtures are also absent; current
reciprocal-specific checks combine positive data with source-string
assertions. The next bounded producer check should exercise the relevant
production arithmetic flags, corrupted individual reciprocal operands, and
archive exact results. This is CPU prerequisite work, not source GPU
authorization.

## Findings that keep producer/source acceptance closed

**High — source-contract H4 is confirmed, unchanged in this successor.**
The following dummies still use `dzf(:)`, with default lower bound one:

- `restas_source_accumulate_boundary_flux`, patch 749–752;
- `restas_source_record_inventory`, 866–870;
- `restas_source_record_velocity_audit`, 912–916.

Exact upstream main allocates `dzf(1-nh_d:nz+nh_d)` with `nh_d=1`
(upstream lines 220–246). Main and `advvof` pass the whole array, not the
interior slice (patch 114–115, 158, 184, 1730, 1759 and 1790).
Inside these helpers, `dzf(k)` consequently means caller `dzf(k-1)`.
This changes x/y geometric face areas, inventory cell volumes, face-volume
rates, divergence metrics and the inherited Courant diagnostic.

The independent source-order binary64 probe reproduced 22 differing interior
positions for the nominally uniform fixture; the first is k=3:
intended `0.024999999999999994`, wrongly addressed
`0.025000000000000001`. This demonstrates indexing, not measured solver mass
error or production optimized arithmetic. The two-halo validator
(`source_boundary_validator.f90:19–23`) has another lower bound and constant
spacings, which hide the defect.

**Smallest next action:** bounded producer owner preserves the intended
lower bound or passes an explicit interior slice consistently at every call,
then supplies compiled one-halo and two-halo tests with nonconstant spacings
and independent face/volume integrals. Re-review the resulting patch. Do not
repair this by teaching the analyzer the wrong mesh. Keep the inherited
division-based Courant diagnostic distinct from v1.2's captured-inverse
multiplication until its contract is prospectively reconciled.

**Medium — the compiled integration evidence does not pin its external
analyzer/fixtures or retain its emitted data.** The pre-build command mounts
the live repository. Test 878–891 hashes whatever analyzer it imports into a
temporary synthetic manifest but does not print or archive that hash;
the 16 build-input hashes do not cover the external analyzer or fixture file.
Test cleanup removes the helper's raw CSV/JSON and generated bundle.
The preserved log proves the named integration test passed, and code review
shows that actual compiled timestep bytes were used. It cannot establish the
exact historic analyzer/fixture pair or reconstruct those emitted bytes from
the log alone. The analyzer/fixture hashes in this review are the observed
review snapshot, not a retroactive pin for the pre-build run.

**Smallest next action:** producer evidence owner archives the generated
helper source, compile/link commands, tool versions, exact analyzer and fixture
hashes, raw timestep-input/CSV files, synthetic supplemental tables and report
in a fresh CPU evidence bundle. Include the production-arithmetic check above.
No solver or GPU is needed for this repair.

**Medium — an upstream-main provenance label in the handoff is wrong.**
Handoff lines 33–34 call
`ef4e55d8d5d6de489bb6e6c986a5fcc15f44e16170e4cf4add7b9e2559175a03`
the upstream `src/main.f90` hash; the prior exact review repeats it.
At the pinned commit, `src/main.f90` is absent. The actual application
template `src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`
(git blob `e0e1b4c232da1e261026e73c95118a4cb36cdd6e`) hashes to
`1d6450b3379b9995b0d69c0d8e22d8b038c66446ebd33066cfdffdf799616e22`.
The claimed `ef4e55...` matches the locally modified file in
`/tmp/flutas-pristine-5982106`; its git diff contains earlier source-boundary
changes. A directory's name is not source provenance.

**Smallest next action:** primary records an append-only erratum, preserving
both archived handoff and review. Future receipts distinguish exact upstream
template, applied candidate source and build-generated `main.f90`.
The corrected upstream objects were used in this review; this labeling defect
does not invalidate the independently pinned local image/patch smoke identity.

The original exact-review receipt finding also remains unresolved **by the
reviewed build bundle**: `candidate-build.json` is absent and the metadata
records no OCI digest. The primary reported a later offline OCI proof; this
review does not adjudicate or substitute that separate artifact. The frozen
source-release contract, input/scan binding, inherited conservation/raw
evidence, analyzer review, limits, resources and supervisor/stop provenance
still require their own accepted exact release. No source or scientific
acceptance follows from any repair listed here.

## Exact source-disabled GPU eligibility

The unchanged source gate separates this regression from source execution
(`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md:313–320`); schema 506–513 also calls it
a separate software check. The successor diff relative to the previous
reviewed patch only changes source instrumentation and its module state.
Absent `source-boundary.in`, the reader returns at patch 210–211 while
`restas_source_loaded` remains false (1612). Main's source calls are guarded,
and the source-disabled `advvof` branch passes no optional source arguments
(138–147). The H4 helpers and the changed timestep capture/writer stay
inactive. A dry source input is not permitted by this eligibility.

The exact outer launcher still verifies the local image ID, freezes that ID
into the locked runner, and invokes
`scripts/run_local.py --threads 2 --gpu --timeout 600`.
The locked runner rejects a regular file **or symlink** named
`source-boundary.in` in both the image's upstream bubble template and staged
case, verifies the embedded patch and inherited runner hashes **before any
GPU stage**, then selects `/usr/local/bin/flutas-gpu-tests` explicitly.
The candidate's default `/bin/true` entrypoint is not used for the test.

After its current doctor/headroom check and queue entry, the primary may run
exactly the unchanged launcher command below. **The reviewer did not run it.**

```sh
containers/flutas/run-candidate-gpu-regression.sh \
  sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43 \
  sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43 \
  aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7
```

Scope: **one GPU-owning job, shared GPU lock, two CPU threads/cores,
600-second launcher timeout**; keep the aggregate project CPU ceiling and
responsiveness reserve. The runner uses one CPU for the initial nongpu
preflight and `--cpus=2` for the GPU container. No new runtime RAM/VRAM cap
is implied by the build's 6-GiB limit. Runtime sampled resources are evidence
of this small smoke only.

The sequence is inherited OpenACC kernel, two-rank CUDA-buffer MPI smoke,
then one-rank upstream rising-bubble solver/checker. It includes that bubble
solver and no source case. PASS requires the expected toolchain/device/kernel,
rank and `sm_120.cubin` markers; normal bubble completion without fatal
markers; a finite final timestep time at least 3 seconds; upstream
`True True`; and finite sampled GPU/container resources as enforced by the
unchanged runner. Preserve any failure and its new evidence directory;
do not continue into source diagnostics or a larger pilot.

Any mismatch in image ID, embedded patch, runner hashes, source-input absence,
preflight or resources stops this eligibility. There is **no build-receipt
or OCI-manifest substitution**, no source mode, no `source-boundary.in`,
and no new gate approval.

## Reviewer checks and identity table

Read-only hash/inventory checks, exact-commit source reads, in-memory hunk
application and spacing arithmetic were performed. `bash -n` passed both
regression scripts, inherited GPU test script, candidate build script and host
test script. No compiled tests or project-wide suite were rerun by this
reviewer. An initial Docker inspection requested an absent optional
`Config.Cmd` field and was retried successfully using the actual required
fields; it started no container. The current analyzer identities below are
context pins, not a separate analyzer acceptance.

| Artifact | Opening SHA-256 = closing SHA-256 |
| --- | --- |
| Schema v1.2: `experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| Prior exact review: `docs/reviews/FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md` | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
| Primary time decision: `docs/reviews/FLUTAS_CANDIDATE5_TIME_INTERFACE_PRIMARY_DECISION_20260925T1302Z.md` | `1300189c58e5f84fc19acddc6d28178c9fa5bf5f09eeeade7cfd696d37a17470` |
| Source-contract exact review: `docs/reviews/FLUTAS_SOURCE_RELEASE_CONTRACT_REVIEW_20260925T1331Z.md` | `058a3d83de7c326f5f51ac8af58d54f8f0f4c28db20a595343fafb9f2df3d336` |
| Candidate patch: `containers/flutas/candidate5/source-boundary.patch` | `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7` |
| Producer tests: `containers/flutas/candidate5/tests/test_candidate5_observability.py` | `965385bcf409e315de8866780e1afc38d57e9b5a9a518bdcf334a610084d17a4` |
| Helper source: `containers/flutas/candidate5/tests/candidate5_observability_helper.f90` | `18751fc873acc08c52d7a5ca5e698661c443f5ffa9de4af6346546aa00078a27` |
| Host-test script: `containers/flutas/candidate5/tests/run_source_validator_tests.sh` | `2cc11f54aa035ae4724e9070cbd3eab227bee9f5277937d8a4d5e6b34bd95b7a` |
| Dockerfile: `containers/flutas/candidate5/Dockerfile` | `4c0d59fce78c6b08db5b3a170d7c8577501fd4e067c4cd9729f33466770ac246` |
| Build script: `containers/flutas/candidate5/build.sh` | `eb578d8e9641459e3c238231ac33f51a9ae1787ed180943a4f55cc637e04520d` |
| Manifest writer: `containers/flutas/candidate5/tools/write_run_manifest.py` | `79219cfb371f94b9949c19617ca454487d630870ff40d4484ee816261ffc6304` |
| Case SHA256SUMS: `containers/flutas/candidate5/cases/source_boundary/SHA256SUMS` | `a04cbac29baf540bce1c969ad0df2c081b0dc2a3a7a31177606c34602d7978f1` |
| Successor evidence SHA256SUMS: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/SHA256SUMS` | `ee104db1f5f328ab9e5822fefaeb075116cdefcc9439cd865a10e2894f207e1d` |
| Successor handoff: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/handoff.md` | `a000cf9f444afca0c02010080ba74b96bff5405c5a4e60d1d15574535e015cbc` |
| Successor metadata: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/metadata.txt` | `aedf64524ca8a3a16477d416b9ba15fb73c78e930dee807b38a176c227fc957d` |
| Successor build log: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/docker-build.log` | `0fbbfb3a27ddb797dec9f5948a611d3c48a80a1541d7a323f44a47968d773c47` |
| Pre-build host-test log: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/prebuild-tests.log` | `da101175276b24131831bb0e9510848a973aac885346cec413e40dfc8b1a0eaa` |
| Pre-build host-test command: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/prebuild-test-command.txt` | `ced90957c021045b37baf487f15acf13d196721c0225e57e1e26b6d90745c959` |
| Extracted native executable: `containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/flutas.two_phase_inc_isot` | `99cf345a2d8465d3be2993567907837e1988041f6a8a16d44199b8cda9111865` |
| Current analyzer (context only): `src/aerial_drop/flutas_source_analyzer.py` | `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37` |
| Current analyzer fixtures (context only): `tests/test_flutas_source_analyzer.py` | `b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20` |
| Outer GPU launcher: `containers/flutas/run-candidate-gpu-regression.sh` | `282bfce5c5f2f86682318e26e7f9a6473e3277090a362fe3eb28232698c83d36` |
| Locked GPU runner: `containers/flutas/run-candidate-gpu-regression-locked.sh` | `9c88514318ed24ce30b607f3fdd2f9b3b20bcf3e9227a5cc9aa24817a7b24492` |
| Inherited GPU test script: `containers/flutas/run-gpu-tests.sh` | `e90285710e1ce77724d85bcf331c2fe993fdd6367cf3ccec159f81c70c88757c` |
| Local resource/lock launcher: `scripts/run_local.py` | `13e3d2fd6fcebe58ad623af339de36ed4d29f842b7588c18c59e750ae16d73db` |
| Source boundary gate: `experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md` | `b77ef87ae4a086f3e4cbce61e6ac22fb6c45d9aefab0988b9acde0b1db48928d` |

Shared status, blocker plans and queue disposition remain the primary's files.
The next producer repair is CPU eligible; the one exact source-disabled smoke
is separately GPU eligible. Source execution and all scientific gates remain
closed.
