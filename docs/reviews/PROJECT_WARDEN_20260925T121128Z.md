# Project Warden checkpoint 9 — 2026-09-25 12:11:28 UTC

**Disposition: advisory steering only.** This read-only checkpoint accepts no
implementation, scientific gate or launch. E1 exact-package follow-up remains a
separate next review.

## Critical path and queue

The source track has moved from schema ambiguity to **candidate5 producer
completion → independent implementation review → the smallest
source-disabled GPU regression**. B2 v1.2 integration and E1 static preparation
proceed independently. The current three worker slots are distinct: Luna
candidate5 producer, Luna B2 analyzer, and Astra Warden/E1 reviewer. Agent
occupancy is not a running compute job.

| Owner | Dependency and next evidence | GPU eligibility |
|---|---|---|
| Luna candidate5 producer | Finish actual timestep operand capture and post-run manifest with build/case/input hashes, CSV row hashes/counts, stop prefixes, scan order, resource samples and direct-pressure disposition. Keep the 2 CPU / 6 GiB cap. Also close `dlmini_m_inv`, overflow and guard-product fail-closed behavior. | No GPU until exact candidate/build/runner review. |
| Luna B2 analyzer | Integrate accepted schema v1.2 in its disjoint source/tests/note; derive membership/arithmetic independently and keep unapproved limits `not_adjudicated`. Keep the 1 CPU / 2 GiB offline-fixture cap. | CPU-only checkpoint. |
| Astra E1 reviewer | Review the corrected static package and amended wall gate with opening/closing hashes after archiving this memo. | Static-preparation disposition only; no mesh, characterization, solver or GPU approval. |
| Primary | Freeze limits/launcher contract and producer/analyzer join; preserve additional conservation outputs required by B2. Keep source queue closed until B1-pre/B2/limits/launch review all pass. | After accepted candidate build and runner, one smallest source-disabled GPU regression promptly. Source stages remain ordered and stop at first failure. |

At the 12:00 UTC host snapshot, 20 CPUs were effective, 118.1 GiB RAM was
available, 260.8 GiB disk was free, and the RTX 5090 was idle at 0% / 16 MiB.
Keep two CPUs reserved and 18 as the shared ceiling. The current worker caps
total three CPUs. Profile build parallelism before raising caps; more cores
cannot substitute for missing artifacts or review. No solver/GPU job is
eligible now. Unchanged candidate3/4 smoke repeats and the unnecessary P1
replay remain deferred.

## Numerical issue found before any run

The frozen 50 m/s crossflow startup profile, fixed `dt=1e-4 s`, and provisional
`fixed_step_factor=0.2` are expected to fail the candidate5 guard at U0. This
affects both `dry_crossflow` and `crossflow_four`; no first interval should be
consumed. Before source eligibility, the primary must retain these as explicit
negative guard fixtures or prepare an independently reviewed prospective
amendment that preserves—or explicitly redeclares—the pulse duration, dose and
observation horizon. Do not discover this known failure through a GPU source
run or change the inputs retrospectively.

## Ledger corrections and next trigger

- The generated E1 static case and sampler exist and await exact review; no
  mesh, characterization or solver has run. The review-4 gate hash
  `15a9b4a4…` is a reviewed predecessor. Amended gate hash
  `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` awaits
  review.
- E5 source extraction is complete and separate from E5 simulation or
  validation. The CSV must remain visible to Git under the explicit allowlist.
- `STATUS.md` must explicitly distinguish the ready-but-unnecessary P1 replay
  from ineligible candidate5/E1 jobs and carry the latest live queue snapshot.
  Record completed primary-disposed deliverable checkpoints since this review.

**Recommended dispositions:** accept the role, ownership and resource
assignments; defer source CFD, E1 characterization, E2 scientific release and
large pilots; reject duplicate extraction, unchanged smoke repeats and
utilization-driven gate bypass. No new user input is needed for these tasks.

The next Warden trigger is two primary-disposed deliverable checkpoints, a
material eligibility/architecture transition, or a repeated hard blocker,
whichever occurs first. Coalesce simultaneous triggers.

Opening snapshot hashes supplied by the reviewer: STATUS
`cd2bfec0ee901be39d9e014023a7038a3baca52d8c84180dd3c315fc7b886abe`;
blocker plan
`680667468a9a8e2f34dc2a6a7f44761cfbe7730495e6f306fbe1af316143e8fe`;
COMPUTE `03ab96d739e77e43366bfc1910ccb4198e5cea85fd5ab1aeece5d6edbed850aa`.
