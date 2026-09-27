# Track 2 project instructions

## Purpose and source of truth

Build the multiregion aerial-water-drop pipeline in
`track2_aerial_drop_experiment_plan.md`. Read that plan before changing physics,
metrics, validation order, or solver architecture. The root PDFs are reference
inputs; preserve their original names and contents. `docs/REFERENCES.md` maps
them to benchmarks. This project starts at analytical E0 verification, not at
a validated CFD solver.

## Orchestrator and subagents

- The primary agent directs the work, owns the plan and shared interfaces,
  reviews all contributions, integrates them, and reports evidence to the user.
- Keep the available worker pool productively occupied with independent paper
  extraction, implementation, testing, and review tasks. The current project
  config allows three spawned workers alongside the orchestrator; respect any
  lower runtime limit. Give each a disjoint file scope and a bounded handoff.
- Use **`gpt-6-luna` with `max` reasoning** for bounded research and
  implementation workers. Use **`gpt-6-astra` with `max` reasoning** for the
  blocker planner, general repository reviewer, and project warden. Spawn with
  explicit model and effort when supported; a full-history fork may inherit the
  parent's model, so use a fresh or limited context and supply the task's
  necessary context.
- Keep the main agent's selected model. Default to at most three simultaneous
  workers plus the orchestrator, respecting the actual runtime limit. Reuse
  workers for follow-ups. Do not silently substitute another worker model if
  Luna Max is unavailable; report it and continue useful work in the primary.
- Parallelize paper extraction, independent modules, case preparation, analysis,
  and review. Keep dependent stages sequential. Workers must not recursively
  delegate unless the orchestrator explicitly assigns a bounded plan.
- Each assignment names the objective, input sources, owned files, public
  interface, resource allocation, tests, and expected handoff. Give workers
  disjoint write ownership. Shared-file changes go through the orchestrator.
  All agents share a filesystem; never revert another agent's changes.
- Use a separate reviewer for substantial physics, conservation, or scoring
  changes. That reviewer checks analytic expectations and source evidence, not
  just implementation consistency. The orchestrator resolves findings and
  reruns affected checks before accepting the result.
- Worker handoffs contain changed files, commands and results, source locations,
  assumptions, remaining defects, and evidence paths. A worker's completion
  message is not proof that a scientific gate passed.

### Warden and checkpoint cadence

- Use the project-scoped `project_warden` role in `.codex/agents/` as an
  independent Astra Max steering check at each major gate transition, after a
  source/solver architecture change, after two completed checkpoints, when
  a blocker repeats, or immediately for a high-severity cross-discipline
  decision that could redirect the critical path. The warden checks critical
  path, parallel work, compute queue, stale claims and user-only dependencies,
  then recommends concrete next assignments with owners, dependencies and
  acceptance evidence, especially for hard blockers. It is read-only and
  advisory: only the primary changes the
  shared plan, and only the assigned scientific reviewer approves a gate. The
  primary archives each memo in `docs/reviews/PROJECT_WARDEN_<UTC timestamp>.md`,
  integrates confirmed steering into `docs/STATUS.md` and
  `docs/BLOCKER_RESOLUTION_PLAN.md`, and preserves the full review record.
- Count a completed checkpoint only when a bounded deliverable, its prescribed
  checks, exact evidence references, and the primary's handoff disposition are
  recorded. Status edits, repeated discussion, and unchanged reruns are not
  checkpoints. Record the last Warden memo, completed checkpoints since it, and
  the next trigger in `docs/STATUS.md`. Coalesce simultaneous triggers into one
  memo for the same evidence snapshot.
- Each Warden recommendation names the blocker, responsible owner, prerequisite,
  next action, acceptance or stop evidence, and CPU/GPU eligibility. For a
  repeated blocker, identify the attempted resolution and remaining evidence,
  then recommend a bounded discriminating check, implementation change, or
  supported fallback. The primary records each recommendation as accepted,
  deferred, or rejected, with a reason and next evidence trigger, in the status
  or blocker records. Warden advice never substitutes for exact independent
  review or the primary's launch decision.
- For a repeated, cross-discipline, or critical-path blocker needing a deeper
  resolution plan, assign `.codex/agents/blocker_planner.toml` to an Astra Max
  worker at max reasoning. Give it a disjoint, timestamped memo path and ask
  for ranked fixes, owners, prerequisites, exact acceptance evidence, GPU/CPU
  eligibility, and whether user or external evidence is truly required. The
  separate `.codex/agents/general_reviewer.toml` role is also Astra Max at max
  reasoning and is used for independent repository-wide consistency review.
  Warden steers the whole project; deblocker and general reviewer return
  bounded artifacts. The primary integrates advice and remains responsible for
  shared plans, implementation choices, and gate decisions.
- At each handoff, dependency change, or Warden checkpoint, refresh the
  timestamped queue ledger in `docs/STATUS.md`: list each worker's live
  assignment, each compute job's ready/running/blocked/finished state, owner,
  candidate and review state, resource ceiling, and next evidence trigger.
  Identify the exact dependency when a queue is idle. Keep agent occupancy,
  running processes, resource allocations, and measured utilization distinct.
- Maintain separate CPU and GPU queues. Schedule one GPU-owning task at a time
  through `scripts/run_local.py`'s shared GPU lock, and keep independent
  CPU-only research, implementation, and review work moving during it. The
  project has one RTX 5090; parallel GPU trials would contend for the same
  device and are not an increase in useful throughput.
- Native builds and code-object inspection are CPU prerequisites. Every
  GPU-relevant implementation checkpoint gets its smallest meaningful GPU
  runtime check as soon as the exact candidate has independent review and all
  other prerequisites for that check pass; source diagnostics need their own
  gate approval. Overlap a GPU trial with independent CPU work when both queues
  have ready tasks. Record
  `not applicable` for CPU-only checkpoints, or name the exact gate blocking a
  GPU trial. Build or smoke evidence never substitutes for a source-boundary
  solver gate. Run dependent source CFD cases in order and stop on first
  failure; do not launch later stages in parallel.
- At every worker handoff, rebalance the worker pool and both compute queues.
  Keep every available worker slot on independent, gate-ready work when one
  exists, and schedule CPU jobs against measured headroom up to the shared
  18-core ceiling. The throughput target is the measured safe compute budget:
  overlap independent CPU and GPU work and avoid idle ready work. One RTX 5090
  means one ordered GPU trial at a time; never duplicate or parallelize jobs to
  inflate utilization. Record why a queue is empty or a trial is ineligible,
  size approved work from measured profiles, and never let utilization release
  a scientific gate. When a worker completes its bounded task, capture the
  handoff and promptly reassign or release that slot; do not keep completed
  workers occupying the pool while independent ready work is waiting.
- A scientific gate remains closed until its frozen inputs, observables,
  limits, diagnostics and independent review are complete. While it is closed,
  use CPU capacity for approved builds and the GPU for already-approved runtime
  smoke checks; continue independent tracks. Do not use utilization pressure to
  skip validation.

## Working commands and layout

`make setup` installs the locked local Python environment. `make check` runs
lint, formatting checks, and tests. `make doctor` inspects actual resources.
`make e0` writes a new analytical verification bundle to ignored `results/runs/`.
Use `make help` for commands. Python dependencies live in `pyproject.toml` and
`uv.lock`; use `.venv/bin/python` or `uv run --frozen`, not system `pip`.

- `src/aerial_drop/`: shared physics/diagnostics and verification code.
- `tests/`: independent analytical and regression checks.
- `scripts/`: environment and resource tooling.
- `experiments/`: predeclared cases, inputs, tolerances, and gate decisions.
- `docs/`: validation contract, sources, compute procedure, workflow and status.
- `results/`: small documented summaries; generated run bundles are ignored.

## Scientific requirements

- Use SI units internally and state coordinate frames, signs, cell orientation,
  source assumptions, and numerical resolution. Every paper parameter needs
  a DOI/local file plus page, equation, figure or table and extraction method.
  Mark measured, digitized, inferred, assumed, and fitted values separately.
- Implement regions A/B with conservative water-air VOF; a ballistic or parcel
  demonstrator cannot stand in for validated nearfield physics. Qualify any
  reduced model and preserve the intended multiregion architecture.
- Follow E0–E6 and the gates in `docs/VALIDATION.md`. E1–E3 are numerical
  benchmarks; E4–E5 supply measured ground evidence. Never infer field validity
  or a fourfold gain from nearfield appearance or one historical fraction.
- Before a scientific run, declare inputs, observables, tolerances, uncertainty,
  grid/time/parcel/domain refinements, compute budget and stop conditions in
  an experiment record. Select tolerances with physical/source justification;
  do not tune them after seeing results. Preserve a case without fit adjustments.
- Keep released mass in mutually exclusive compartments: deposited (inside and
  outside the map), airborne VOF, airborne parcels, escaped, and evaporated if
  modeled. Do not double-count cumulative handoff flux as stored mass. Check
  mass and momentum across VOF/parcel transfer, and coordinate transforms at
  each absolute impact time. Preserve impact locations and weights.
- Score both designs with the same code. `L95` is the longest **continuous**
  along-track interval whose every section meets `C >= C*` over at least 95%
  of the prescribed centered width. Weight partial cells by area. Useful
  fraction credits `C*` only in qualifying cells inside that interval, divided
  by total released mass. Keep collected fraction and actual strip mass distinct.
  Define deterministic ties. A zero control length makes the gain undefined.
- Freeze matched payload, flight/environment, target, physics, and resolution
  before optimization. Report operational comparisons separately. Publish
  sensitivity to map resolution, coverage threshold, and width tolerance.
- Test handoff-location stability against ground maps and `L95`; attempt direct
  VOF descent for the coherent Restás plume before selecting its handoff. Check
  two-way coupling requirements from loading; do not silently omit them.
- Record revision and dirty state, code/input hashes, solver/dependency versions,
  seeds, mesh, time steps, resource use, mass errors, raw observables and the gate
  decision. Never overwrite an existing run or omit failed attempts.
- Visuals use computed fields with consistent scales/cameras/times. Label
  computed, inferred subgrid, and footage content. Water-only inputs do not
  validate foam or the built pressurized device. No fire suppression or
  post-impact dynamics is established by this pipeline.

## Efficient execution

- Run `make doctor` before assigning compute. Detect CPU affinity/cgroup limits,
  current free RAM, GPU memory and disk; do not assume the workstation or a
  remote cluster is available from the plan's hardware description.
- Use `scripts/run_local.py` for local jobs. Allocate a **shared total** CPU
  budget across workers, processes and MPI ranks; keep BLAS/OpenMP threads at
  one inside process-parallel sweeps. Avoid nested oversubscription.
- The orchestrator is the single compute scheduler. Start with two CPU cores
  reserved for responsiveness. Independent light CPU work can overlap one GPU
  pilot; serialize GPU jobs with the launcher's lock. A per-job thread cap is
  not a reservation for the whole machine.
- Profile the 1–3 million-cell pilot before larger CFD: report peak RAM/VRAM,
  step time, pressure solve and I/O share, mass error, physical-time throughput,
  and projected checkpoint cost. Advance to 5–10 million cells only on measured
  evidence. GPU visibility is not proof that a solver supports this problem.
- Keep full 3D snapshots sparse; routinely save compact flux, impact, ledger,
  and scoring data. Checkpoint expensive jobs; measure CPU/MPI scaling before
  requesting cluster resources. Stop failed or unaffordable runs with evidence.

## Completion and autonomy

Continue authorized implementation, review, and checks without routine permission
questions. Ask concrete questions only when missing inputs change the scientific
meaning or prevent the next stage; continue independent work in the meantime.
Do not invent geometry, measured properties, source histories, validation data,
or cluster access. Keep provisional inputs explicit.

The user has authorized clearly labelled provisional inputs (2026-09-24). Use
the plan's approximate dimensions and declared sensitivity ranges to advance
idealized work; do not repeatedly ask whether provisional modeling is allowed.
This authorization does not turn assumed values into measurements.

Before ending, review the combined diff, run affected checks, update
`docs/STATUS.md`, and report what works and what remains scientifically unproven.
Keep changes local unless publication is requested. Preserve the user's work
and do not modify global Codex settings, GPU drivers, or system solvers as an
incidental setup step.
