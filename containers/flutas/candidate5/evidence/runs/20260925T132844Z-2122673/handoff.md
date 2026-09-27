# Candidate5 producer repair handoff

**Disposition:** provisional implementation/evidence handoff for a new exact
review. This records implementation and checks; it is not approval of the
candidate, a source run, or a scientific gate.

## Frozen interface and reviewed inputs

Kept `candidate5-observability-v1.2` unchanged. The exact schema file
`experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md` has SHA-256
`4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`.
The exact Astra memo
`docs/reviews/FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md` has SHA-256
`b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68`.
The primary time-interface decision
`docs/reviews/FLUTAS_CANDIDATE5_TIME_INTERFACE_PRIMARY_DECISION_20260925T1302Z.md`
has SHA-256
`1300189c58e5f84fc19acddc6d28178c9fa5bf5f09eeeade7cfd696d37a17470`.

Following that decision, `timestep-restriction.csv.time_s` is the v1.2
diagnostic coordinate, evaluated in its declared order as
`time_start_s + real(state_index,rp)*fixed_dt`; `time_start_s` is captured from
the solver start state. The accumulated AB2 solver clock remains in its
existing solver-native output/log where needed. It is not relabeled as
`time_s`, and the CSV/schema gains no field or tolerance.

Pinned source revision is `598210616bebd51f7d51f61455f196e6f3479916`. The
upstream source files used for the operation-order fixture are pinned in the
test: `src/initgrid.f90` SHA-256
`87010cb1b014355eb70b299264d5b6cd274ab3248c309906a39ac4a66ab8ca28` and
`src/rk.f90` SHA-256
`6f86e54d8c95423099526228d72fcb3ee2720c9ac96a0692c486c0fc119a2e42`. The
upstream `src/main.f90` SHA-256 is
`ef4e55d8d5d6de489bb6e6c986a5fcc15f44e16170e4cf4add7b9e2559175a03`.

## Producer changes

- **H1:** finite timestep CSV numbers now use the canonical source-real
  serializer (`restas_source_real_text`), including trim and zero
  normalization. The tests check complete finite CSV tokens against the
  analyzer's numeric grammar and check that the timestep writer does not use a
  raw padded `ES` format.
- **H2:** the full frozen phase scan order is now xlow, xhigh, ylow, yhigh,
  zlow `bottom_return`, then zhigh `active_slot`, `inactive_slot`, and
  `top_offmask`. IDs and serialized ordering follow that sequence.
- **H3:** the CSV time field uses the captured start time and fixed diagnostic
  step multiplied by the state index. The actual solver clock is left intact
  for existing solver-native output.
- **M3:** runtime capture fails closed unless scalar spacing and inverse pairs
  and every one of 42 `dzci`/`dzfi` spacing-inverse pairs are positive and
  exactly reciprocal under the pinned initialization operation. The test
  reconstructs all 42 binary64 entries (including halos) using pinned
  `initgrid.f90` operation order and exercises nonuniform last-bit values.
- A compiled helper emits 15 states using the candidate producer and an
  independently accumulated AB2 clock. Its output is checked by the
  independent analyzer: index-based rows pass with all 15 rows checked;
  replacing the CSV times with the accumulated AB2 values is rejected with
  `TIMESTEP_TIME` (including the state-2 distinction).

The owned implementation files are `containers/flutas/candidate5/source-boundary.patch`
(SHA-256 `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7`)
and `containers/flutas/candidate5/tests/test_candidate5_observability.py`
(SHA-256 `965385bcf409e315de8866780e1afc38d57e9b5a9a518bdcf334a610084d17a4`).
No analyzer, launcher, frozen schema, gate, or status file was changed.

## Checks and build

`make doctor` was the first resource check. Its preserved full output is
`resource-doctor.json`. It reported CPython 3.12.3, NumPy 2.5.3, pytest 9.1.1,
PyVista 0.49.0; 20 effective host CPUs; and 126,653,546,496 bytes available
memory at sample time. The RTX 5090 was visible, but `nvcc` was unavailable
and solver GPU support was not verified. The CPU checks below were each
limited to one CPU and 4 GiB, with Docker networking disabled. Base-container
tool versions are preserved in `tool-versions.txt`.

The exact reproducible pre-build command is
`prebuild-test-command.txt`; its full result is `prebuild-tests.log`, with
`prebuild-tests.status` recording exit status 0. Against a clean base image it
first passed `git apply --check`, then applied the patch and ran
`run_source_validator_tests.sh`. Results:

- Source-boundary behavior and unsupported-input checks: all passed.
- `test_source_boundary.py`: 19 passed.
- `test_candidate5_observability.py`: 16 passed, including the 15-state
  compiled-helper-to-analyzer check and AB2-time rejection.
- `test_run_manifest_writer.py`: 4 passed.

After those checks passed, the authorized frozen successor image build ran
with `timeout 900`, 2 CPUs, 6 GiB, `--network=none`, and no GPU devices. The
exact build command, complete log, build input hashes, image metadata, and
input manifest check are in this directory. Build input manifest check passed.
The pinned FluTAS commit check and patch applicability check passed; native
build succeeded with NVIDIA HPC SDK `nvfortran 26.9-0`,
`ARCH=generic-gpu`, `-fast -cuda -acc -gpu=cc120,cuda13.3`; `cuobjdump`
confirmed an `sm_120.cubin` code object. No GPU runtime, solver invocation, or
source case was executed.

The Dockerfile's own test phase did not mount the independent analyzer root or
the frozen schema. In that build-only run, the multi-state analyzer test and
one full-manifest test skipped for those declared missing inputs. The separate
bounded pre-build run above mounted both and passed all tests. The build image
is local-only: tag
`track2/flutas-source-boundary:5982106-candidate5-20260925T132844Z-2122673`,
image ID `sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`,
executable SHA-256
`99cf345a2d8465d3be2993567907837e1988041f6a8a16d44199b8cda9111865`.
`RepoDigests` is empty: there is **no OCI manifest digest and no
`candidate-build.json` receipt**. A schema-v1.2 run therefore cannot yet be
bound to this image under the frozen provenance contract.

An earlier build attempt is preserved at
`../20260925T132519Z-2120267/`. Its two new static tests assumed the patch was
copied beside the test file; the Dockerfile copies it to `/tmp` and tests the
applied source include instead. The errors were test-packaging path lookups,
before native compilation. The tests were adjusted to read the applied source
include when the patch file is not adjacent, and the complete bounded suite
and successor build then passed. Both failed-attempt log and metadata hashes
are listed below.

## Remaining blockers and boundary

1. **Exact implementation review pending.** This handoff requests that next
   review; no review acceptance is implied.
2. **Immutable image provenance blocked.** The successor is a local daemon
   image with no OCI digest and no `candidate-build.json`; preserve the image
   and create the required immutable receipt/identity through the authorized
   follow-up path before any bundle can claim the frozen image provenance.
3. **Runtime/source evidence absent by scope.** No solver or source case ran;
   no GPU runtime was used; no source launch was approved. The source-boundary
   scientific gate remains closed.

The current `SHA256SUMS` inventories every file in this evidence directory
except the checksum-list file itself.
The main build evidence hashes are: build log
`0fbbfb3a27ddb797dec9f5948a611d3c48a80a1541d7a323f44a47968d773c47`, metadata
`aedf64524ca8a3a16477d416b9ba15fb73c78e930dee807b38a176c227fc957d`, build
command `c89af296668660e04e2c30e40bf4db55d7e271aeb5a1caaa6c1d238e0e6f36d1`,
and build input hashes
`93c95b13750076c25ad1f90f57b5676c4cf89f1cb73027bbb8b5c763b05b30a7`. The
earlier failed-attempt log SHA-256 is
`259caa24cde18904afc387b9185e1e66a74157e2c184479f89afe71f8bdb36f2`; its
metadata SHA-256 is
`70348514ac765ac0c74406ec5c57c2a66f418f9b2a845fee4b1bb917f40397da`.
