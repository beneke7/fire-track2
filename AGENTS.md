# Track 2 project instructions

## Purpose and source of truth

Build the multiregion aerial-water-drop pipeline in
`track2_aerial_drop_experiment_plan.md`. Read that plan before changing physics,
metrics, validation order, or solver architecture. The root PDFs are reference
inputs; preserve their original names and contents. `docs/REFERENCES.md` maps
them to benchmarks. This project starts at analytical E0 verification, not at
a validated CFD solver.

User correction (2026-09-28): the four Restás outlets face horizontally and
discharge liquid at high speed. Use horizontal outlet vectors in new Restás
cases; the speed remains provisional until a source or measurement provides it.
Earlier downward-discharge CPU cases are exploratory and do not reproduce this
orientation.

## Orchestrator and subagents

- The primary agent directs the work, owns the plan and shared interfaces,
  reviews all contributions, integrates them, and reports evidence to the user.
- The user explicitly authorizes exploratory CPU/GPU runs and parallel agents
  without per-run permission requests. Start clearly labelled trials when
  local capacity is idle; do not let routine paperwork or exact reviews block
  a diagnostic, profiling run, baseline, or rendering check. Respect unrelated
  workloads: inspect process/GPU use first. Do not impose a fixed CPU reserve
  or small per-run limit when the machine is idle; use available capacity while
  keeping the desktop responsive.
- Use parallel workers when independent work shortens the critical path.
  Prefer Luna Max for bounded research, implementation, and compute tasks; use
  Astra Max sparingly for consequential scientific interpretation or a hard
  cross-project blocker. Do not fill slots just to keep them busy. The current
  project config allows three spawned workers alongside the orchestrator;
  respect any lower runtime limit and release workers promptly after handoff.
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
- Use independent scientific review when changing a published-case
  interpretation, conservation method, or E0–E6 acceptance decision. Ordinary
  exploratory runs and their implementation do not need advance Astra or
  Warden review. Label assumptions, inspect outputs, and decide later what
  merits formal review.
- Worker handoffs contain changed files, commands and results, source locations,
  assumptions, remaining defects, and evidence paths. A worker's completion
  message is not proof that a scientific gate passed.

### Independent oversight and status

- The Astra Max Warden is an occasional read-only project advisor. Use it for a
  major solver/architecture decision, a repeated cross-project blocker, or a
  difficult scientific choice that could redirect the work. Do not invoke it
  for routine launches, worker handoffs, or merely because time/checkpoints
  passed. Ask for concrete options, owners, dependencies and useful CPU/GPU
  experiments. The primary decides and records only the resulting action in
  `docs/STATUS.md`; write a separate memo only when it carries substantial
  review evidence.
- Use the Astra Max general reviewer or blocker planner only when a consequential
  scientific decision or hard blocker needs independent analysis. Routine
  exploratory simulations do not need advance review. Formal E0–E6 decisions
  retain their independent validation requirements.
- Update the compact `docs/STATUS.md` when work ownership, compute state, or a
  material decision changes. Distinguish live agents from actual processes and
  measured utilization. Do not maintain a separate timestamped ledger for each
  ordinary handoff or repeat the same information across documents.

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
- Before a formal benchmark or gate run, declare inputs, observables,
  tolerances, uncertainty, grid/time/parcel/domain refinements, compute budget
  and stop conditions in an experiment record. Select tolerances with
  physical/source justification; do not tune them after seeing results. For
  exploratory runs, a brief case record with provisional inputs, solver,
  resolution, horizon, resources and diagnostic is enough. Preserve each run
  without fit adjustments.
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

The user's standing authorization covers exploratory GPU smoke/debug runs,
CPU OpenFOAM baselines, short physical VOF cases, AMR and turbulence
comparisons, plus rendering and image inspection. It does not turn assumed
inputs into measured facts or make an exploratory result a validation pass.
Before a run, keep a brief case record (directory or run metadata) with
solver/version, grid, horizon, boundaries, turbulence model, resource limits,
and intended diagnostic. Preserve failures, render fields promptly, and avoid
separate review memos unless a hard decision needs one.

- Run `make doctor` before assigning compute. Detect CPU affinity/cgroup limits,
  current free RAM, GPU memory and disk; do not assume the workstation or a
  remote cluster is available from the plan's hardware description.
- Use `scripts/run_local.py` for local jobs. Allocate a **shared total** CPU
  budget across workers, processes and MPI ranks; keep BLAS/OpenMP threads at
  one inside process-parallel sweeps. Avoid nested oversubscription.
- The orchestrator and workers share the compute schedule. Use all effective
  CPU capacity when the machine is idle; there is no fixed 18-core ceiling or
  two-core reserve. Allocations are initial estimates, not standing caps.
  Avoid routine negotiation or allocation reports: workers coordinate directly
  only when an active long run materially delays assigned work or observed
  contention affects desktop responsiveness, memory, disk, or solver stability.
  Serialize GPU work with the launcher's lock.
- Profile small pilots to learn peak RAM/VRAM, step time, pressure-solve and I/O
  share, mass error, physical-time throughput, and checkpoint cost. The user
  also authorizes larger exploratory tests when measured memory, disk and
  solver support make them viable; size is not itself a review gate. GPU
  visibility is not proof that a solver supports this problem.
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
