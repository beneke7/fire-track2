# Track 2 project instructions

## Purpose and source of truth

Current user direction (2026-10-23): this workstation now investigates the
I4F internal pressure-driven discharge apparatus; aerial work continues
separately on the server. Follow the internal-apparatus section added to the
plan; `experiments/i4f_baseline.json` describes the earlier single-outlet
reference, while later one-tank/two-outlet references and full two-tank/four-outlet
runs carry their own immutable apparatus inputs. The latest user-confirmed
hardware facts take precedence in `experiments/i4f_hardware_notes_20261024.json`;
never apply them retroactively to historical cases. Preserve prior aerial evidence and
do not resume old aerial queues automatically. Predict discharge from tank,
gas headspace, valve, pipe and transition rather than prescribing an outlet
history. The new objective permits suitable GPU use, including rendering,
after inspecting unrelated workloads; avoid a GPU solver port before the
first complete physical result. CPU OpenFOAM remains an acceptable route.
The supplied, dimensionally approximate CAD and photo are preserved as
`docs/bencz 3D model (1).step` and `docs/IMG_20180209_103212.jpg`; maker notes
are in `experiments/i4f_hardware_notes_20261024.json`. Do not treat CAD
dimensions or their provisional reconstruction as measurements. Always generate
and inspect pictures of parameterized CAD/geometry for debugging, including
connection/cross-section views; preserve the original models.

User correction (2026-10-25): passages downstream of the valves initially
contain air. New apparatus baselines use that initial state and separately
account for wetted tank-to-valve feeds. Earlier primed-line runs are conditional
sensitivities, not the confirmed startup. The current provisional outlet train
has no added post-rise straight and a 1 m transition/mouth assembly; preserve
historical geometries and fields rather than changing them in place.

26 October reconstruction correction: the scaled pipe overlap creates an
unintended exposed shoulder inside the transition. New corrected-junction
candidates use `--pipe-transition-join flush-at-inlet`; `legacy-overlap` remains
available for historical reproduction. The corrected native mesh is being
tested with the standard phase-source update. Its effect on numerical stability
or hardware performance is not established.

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
- User preference (2026-10-05): the primary mostly plans, inspects evidence and
  integrates; delegate implementation, case preparation, run launches, analysis,
  rendering and check execution to Luna Max workers. Primary read-only
  inspection remains appropriate.
- Current compute direction (2026-10-05): run the resumed instability and
  Dash-8 experiments on CPU. Do not launch GPU compute or rendering jobs
  unless the user changes this direction. Earlier GPU authorizations below
  remain historical context and do not override this CPU-only instruction.
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
  Capture UTC timestamps from the clock automatically; a bundle-name time is
  not an execution timestamp. Snapshot uncommitted source before a run, so a
  recorded hash still identifies recoverable code after later edits.
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
- Long workstation Docker runs, endpoint monitors and dispatchers must survive
  agent-session exit. Use bounded user-systemd services with `run_local.py`,
  and inspect Docker state plus solver End/checkpoints as the runtime authority.
  A missing launcher PID does not mean its Docker solver stopped: reattach
  supervision without relaunching it. Anchor deadlines to the original
  container start, honor PAUSE, and expose the active controller through the
  documented status/event paths while preserving prior attempts.
  For a new Docker launch, hold the solver behind a GO sentinel until its
  exact container ID/StartedAt and manifest exist and the guard is verified.
  Source the OpenFOAM bashrc before enabling shell nounset/pipefail, then set
  the case working directory explicitly. Check current CPU-tick deltas rather
  than lifetime `ps` percentages when paused historical MPI ranks are visible.
  Guard readiness is monotonic: a verified guard progressing to `running`
  must not fail a check waiting for its earlier readiness status. Test parsers
  against actual startup logs; `trapFpe`/`FOAM_SIGFPE` banners are not failures.
  Normalize MPI `[rank]` prefixes before matching Pout records, and search the
  raw log before claiming a diagnostic is absent. A stage monitor must adopt
  an existing manifest/GO rather than call its one-shot launcher a second time.
  Lint private/generated Python stage builders for undefined names as well as
  compiling syntax; exercise preparation against the actual saved parent before
  calling a continuation ready. This does not hold the initial diagnostic pilot.
  Check the launcher's required freeze keys and actual helper dependencies in
  that preparation; do not require copied helpers that nothing imports or uses.
  Before GO, repair the same working preparation when possible: preserve each
  failed script/configuration and error in numbered small attempt records,
  then regenerate and recheck its unreleased manifests. Repeated preparation
  errors do not require another full copy of unchanged mesh/checkpoint files.
  Released runs remain immutable; preserve their executed inputs and failures.
  In the current v2512 internal solver, the mixture-thermo constructor rewrites
  `T.air` and `T.water` from common `T` after GO. These are derived startup
  outputs, as documented in the corrected finite-water capsule. Verify the
  original checkpoint and all manifests before GO; use the immutable parent
  checkpoint for sibling trials. Do not repeatedly flag the expected live
  phase-temperature rewrite as corruption or restore fields in a running case.
  A changed common `T` or failed pre-GO hash remains a genuine discrepancy.
  Matching the fourteen stored fields does not prove a bitwise continuation:
  `createFields.H` reconstructs `dgdt` on restart. Use a matched same-scheme
  restart control before attributing a warm-fork improvement to a scheme change.
  OpenFOAM `oldTime()` may allocate and update history lazily. Calling it in
  supposedly passive diagnostics before its natural equation use can alter
  evolution; inspect allocation order and verify passivity. A first-order Euler
  restart mismatch is not by itself evidence that a previous-time directory is
  mathematically required.
  Terminal checks must use the branch's configured log path, not a fixed log
  basename. A missing expected filename is not evidence that the solver failed.
  Compare numerical dictionary values numerically, not by printed notation
  (`1e-05` and `1e-5` are equal). Formatting or cosmetic labels must not block
  an otherwise verified launch. If Docker exits before the guard records its
  final checkpoint, a dispatcher must wait for capture until its bounded
  deadline; pending metadata is not a failed solver or permission to relaunch.
  Keep internal and external wall deadlines consistent, checkpoint before the
  earliest limit, and guarantee an endpoint write independently of sparse output.
  An agent-initiated resource pause must have a durable resume-or-save action
  before that deadline; a read-only pause watcher is insufficient. A graceful
  save requires the solver to run, so unfreeze operationally paused containers
  before requesting the save. Never automatically resume a user-requested pause.
  Evaluate coupled-field diagnostics and `fvMatrix::residual()` on all MPI
  ranks in identical order; restrict only local extraction/printing to selected
  ranks. High CPU use without advancing `Time` can be an MPI communication
  stall. Preserve and stop a confirmed stalled observer rather than waiting
  for a writeNow checkpoint that its blocked solver cannot produce.
- The orchestrator and workers share the compute schedule. Use all effective
  CPU capacity when the machine is idle; there is no fixed 18-core ceiling or
  two-core reserve. Allocations are initial estimates, not standing caps.
  User direction (2026-10-14): Goblin is free; resume using all available CPUs
  (currently 20 effective CPU equivalents). This supersedes the earlier
  half-capacity limit. Respect unrelated active workloads and account for
  concurrent jobs together; a raised quota alone does not increase the number
  of active single-threaded MPI ranks.
  Avoid routine negotiation or allocation reports: workers coordinate directly
  only when an active long run materially delays assigned work or observed
  contention affects desktop responsiveness, memory, disk, or solver stability.
  Serialize GPU work with the launcher's lock.
- User direction (2026-10-15): keep useful CPU experiments ready while a run
  is active. Arm an actual bounded dispatcher for declared follow-up jobs;
  a written queue plan is not a running queue. Advance when the prior job and
  required checkpoint capture finish, sharing the available CPU budget and
  respecting unrelated workloads. A user pause must also suspend queued jobs.
  Do not wait for another status prompt to launch an already authorized next
  experiment, or repeat failed cases without a new diagnostic purpose.
- Profile small pilots to learn peak RAM/VRAM, step time, pressure-solve and I/O
  share, mass error, physical-time throughput, and checkpoint cost. The user
  also authorizes larger exploratory tests when measured memory, disk and
  solver support make them viable; size is not itself a review gate. GPU
  visibility is not proof that a solver supports this problem.
- Keep full 3D snapshots sparse; routinely save compact flux, impact, ledger,
  and scoring data. Checkpoint expensive jobs; measure CPU/MPI scaling before
  requesting cluster resources. Stop failed or unaffordable runs with evidence.
  Docker helpers that stream binary archives must use `--log-driver=none`,
  verified before export; the default JSON logger can exhaust disk by recording
  the binary stream. Verify lossless archives before removing their sources.

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
