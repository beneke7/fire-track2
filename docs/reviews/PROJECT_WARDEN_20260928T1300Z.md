# Project Warden checkpoint — dry diagnostic packet review

**Astra Max Warden, read-only advisory snapshot at 2026-09-28 13:00 UTC.** No
files changed, tests executed, Docker/GPU calls made, or diagnostic gate
disposition issued.

The packet has progressed beyond Warden 14: candidate6's retained executable,
OCI receipt/layout, strict input staging, guarded launcher, detached lock
supervisor, manifest adapter, and dry-output checker exist. Integration gaps
remain before exact launch review.

`dry_four` contains no active water source: `slot_count=0`, schedule `[0,0)`,
empty initial VOF, zero gravity/background velocity, and 14 fixed intervals.
The source parameter `(0,0,-4.8)` is unused. A successful execution cannot
establish water injection, plume behavior, conservation from raw fields, or any
E1–E6 result.

| Finding | Recommended action | Acceptance evidence |
| --- | --- | --- |
| Identity verifier requires `--archive`; both launcher argv constructions omit it. The sole attempt is claimed before this exits 2. | Add `--archive <candidate_root>/docker-save.tar` to actual and recorded argv. | CPU-only test exercises the real argument contract and confirms no attempt is lost to missing arguments. |
| Map paths and evidence producers disagree; there is no complete post-run inventory/finalizer. | Align paths and explicitly retain host snapshot, annex, success-only manifest, failure evidence, and sorted inventory. | Success/failure fixtures prove required artifacts, staged-input binding, preserved native bytes, annex, manifest gating, and inventory/hash. |
| Native clocks are insufficiently checked. `_check_v03` accepts arbitrary finite mass/velocity `time_s` and velocity `dt_s`; adapter timing checks do not close these joins. | Add source-derived native clock/state joins and fixed-step checks. | Mutated native clocks and `dt_s` reject while native AB2 and index-derived clocks remain separate. |
| The amendment is proposed, the amendment hash pin is `None`, and no exact diagnostic disposition exists. | Obtain separate exact review after integration; primary records final pins and bounded disposition. | Exact reviewed hashes, affected checks, and one-attempt launch record. This Warden memo supplies no approval. |

The nonproducer map mismatch is extensive. The root `dry-output-map.json` is
actually retained at `metadata/dry-output-map.json`; `metadata/staged-inputs/`
is actually `inputs/`; preflight is `input-preflight.json` and is also embedded
in `metadata/run-manifest.json`; launcher configuration/streams differ from
`metadata/source-supervisor.json`, `metadata/command.json`, and
`logs/run-local.*`; and supervisor evidence is under `supervisor/evidence/`
with stage at `supervisor/stage.txt`. The map also requires artifacts that are
not produced: `metadata/oci-layout-reference.json`, an in-bundle host
snapshot, `analysis/dry-output-annex.json`, and root `SHA256SUMS`. Container
details are present in supervision events but the map must point there. The
checker prints its report and creates canonical copies; it does not retain the
report, call the manifest adapter, or generate the full inventory. Inventory
policy must state how its own hash is handled and include both success and
failure evidence.

The checker/adapter split is appropriate for the narrow claim: exact receipt
and input binding, unchanged v1.2 schema, strict output roster/counts,
empty-interface semantics, byte-identical canonical copies, and no raw
conservation claim. `_check_native_roster` currently examines only
`work/data`; the writable `/work` root needs a roster policy. Allow the three
Docker input mountpoint placeholders, while keeping `inputs/*` authoritative.

The nested mount correction is present: writable `/work`, precreated
`work/data`, and three individually read-only input file mounts. This removes
the prior Docker failure caused by creating an output mount below a read-only
parent. Configuration tests assert the corrected argv, but no real Docker
mount execution was reviewed.

Short-run telemetry remains a limitation. The immediate sample can precede
container startup/CUDA allocation, and the next one-second sample can follow
solver exit. A bounded CPU fake timeline should cover both missing the entire
running interval and missing only GPU activity. Optional opportunistic startup
samples can reduce misses while preserving fixed solver inputs, hard ceilings,
and fail-closed behavior; they cannot guarantee observation. Do not add solver
steps or treat post-exit utilization as proof.

The latest machine artifact is timestamped 12:46:57 UTC: 20 effective CPUs,
about 118.2 GiB available RAM, 196.7 GiB available disk, and one RTX 5090 with
16 MiB used. It does not contain a current utilization measurement. The 11:30
status's 243.6 GiB disk figure and live worker assignments are stale; OCI
receipt creation and supervisor/checker implementation are no longer pending.
Broad H5/H6 qualification and exact diagnostic review remain distinct open
work.

The CPU queue can proceed with launcher/finalizer corrections, clock mutation
tests, and independent review. GPU work remains gated on those corrections,
frozen evidence, and exact disposition. Once eligible, retain one job, 2 CPU
cores, 16 GiB hard RAM, 24 GiB sampled VRAM stop, 1,800 seconds, and the
detached lock guardian. No user input or measured geometry is needed for these
engineering fixes.

Exact reviewed SHA-256 anchors at this snapshot:

| Artifact | SHA-256 |
| --- | --- |
| Amendment revision 2 | `4560b335e345e403488c8a787b806e35e298704d696518b1e2e19f5ea575504d` |
| `experiments/dry-output-map.json` | `5cecfbc0a5b5609fb28842c99009184569380eb16244563e0e1d6fe3e0d04aa5` |
| `scripts/prepare_flutas_dry_four.py` | `ded680010c85406cf09d2d17591161ffc9253689d309bf5886d3330b210fa1c2` |
| `scripts/flutas_dry_four_output_check.py` | `fb85e73188093d918d56c55425bbae9d4bc7fd1859ac4cb205a42a72caf1f705` |
| Candidate6 manifest adapter | `373511b66b46531a99b5670e5ab680eef51811e67456fe98c056a5a1882ab29b` |
| Candidate6 receipt | `629e792cf9ebd02d203442b2b943de4aa1176a121f8be303fd86770543c643e0` |

The next Warden trigger is the corrected exact launch-gate transition, a
material architecture change, or two newly accepted bounded checkpoints.
