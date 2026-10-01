# Orchestrator-led execution

The primary agent owns the scientific decisions and integration. It decomposes
work into bounded assignments, uses Luna Max for high-volume research and
implementation, and uses Astra Max for blocker planning, general review and
project-level warden checks. The current session supports three workers
alongside the primary. Agent concurrency is independent of
simulation-process concurrency.

## Configuration

`.codex/config.toml` sets `agents.enabled`, a limit of three concurrent subagent
threads, and `gpt-6-luna` / `max` defaults. It leaves the primary model and permission
policy unchanged. Project role files define research, implementation and scientific
review workers. These settings follow the [official subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference),
checked against local Codex CLI 0.156.1 during initialization.

Project configuration must be loaded by the client; restart/reopen a session after
adding it. Client trust and runtime limits still apply. `AGENTS.md` remains the
workflow contract even when a client does not expose named roles. With the current
collaboration tools, the primary explicitly requests:

```text
model: gpt-6-luna
reasoning_effort: max
fork_turns: none
```

The worker prompt supplies the plan location, relevant context, files and expected
output. A full-history fork can inherit the parent's model and is unsuitable when
it prevents honoring the requested worker model. Never pretend a model override
worked if the runtime rejects it. Escalate hard reasoning and final review to the
primary rather than silently substituting worker models.

Project custom roles live under `.codex/agents/`: `implementation_worker`,
`research_worker`, and `scientific_reviewer` use Luna Max; `blocker_planner`,
`general_reviewer`, and `project_warden` pin Astra Max with max reasoning. The
warden is read-only and is used occasionally for major solver/architecture
decisions, repeated cross-project blockers, or difficult choices that could
redirect the critical path. It is not invoked for routine launches, handoffs,
or elapsed checkpoint counts. It audits the project-level critical path, resource
queue, stale status and user-only dependencies, and returns concrete assignments
with owners, dependencies and acceptance evidence for hard blockers. It does not
edit the shared plan or approve scientific gates. The primary remains
the single orchestrator and records only the resulting action in the compact
status. Create a separate memo only when it contains substantial review evidence.

Formal checkpoints still require their prescribed evidence and a primary
handoff decision. Astra Warden, blocker-planner and general-reviewer roles are
optional, consequential checks—not recurring paperwork. Invoke them only for a
hard decision, keep findings disjoint from implementation, and record the
resulting action in the compact status rather than duplicating memos.

## One work cycle

1. Read the compact status, experiment plan and relevant case files. Inspect the
   worktree and current CPU/GPU use before scheduling work.
2. For an exploratory run, record its objective, assumptions, solver, mesh,
   horizon and resource budget. For a formal benchmark, also freeze observables,
   tolerances, uncertainty and acceptance evidence.
3. Give parallel workers disjoint file paths and initial CPU/RAM/GPU estimates.
   Use available capacity and serialize GPU use. Do not negotiate routine
   allocation adjustments; workers talk directly only when an active long run
   materially delays assigned work or observed pressure affects responsiveness.
4. Inspect source assumptions and outputs after the run. Use independent scientific
   review for consequential physics, conservation or metric decisions, not for
   routine debug or profiling runs.
5. Update the compact status when ownership, compute state or a material decision
   changes. Keep exploratory results separate from E0–E6 validation claims.

## Keep useful work parallel without overbooking hardware

Use all available worker slots for independent work when the queue supports it:
for example, one paper/source task, one implementation task, and one separate
review or tooling task. A worker blocked on a dependent interface should return
that dependency to the primary instead of holding a slot. Use the shared machine
capacity reported by `make doctor`; task allocations are starting estimates,
not hard limits. Do not renegotiate allocations routinely.

At worker handoff, assign the next useful task without reopening other runs'
resource allocations. Use all effective CPU capacity when unrelated workloads
are idle; do not impose an arbitrary 18-core ceiling or fixed host reserve.
Treat per-task CPU/RAM/disk allocations as starting estimates. Workers talk
directly about resources only when an active long run materially delays assigned
work or observed pressure affects responsiveness. Start exploratory GPU trials
without advance exact review, serialize them through the shared lock, and keep
independent CPU work moving.
Capture completed workers' handoffs and promptly reassign or release their
slots whenever independent ready work remains.

Update `docs/STATUS.md` when ownership, compute state, or a decision changes.
Distinguish live agents from actual processes and measured utilization, but do
not maintain a timestamped ledger for routine handoffs.

The machine has one RTX 5090, so serialize local GPU work by the shared
launcher lock and keep independent CPU cases moving. Exploratory solver,
profiling and GPU-debug runs may start without advance exact review; preserve
new immutable run directories and label the result exploratory. The exact
candidate6 `dry_four` attempt remains failed and consumed under its old
amendment. Do not mutate that bundle or rerun the same protocol; a distinct
input/case is permitted under the user's standing authorization. The frozen
`dry_crossflow` and `crossflow_four` fixtures still intentionally fail their
candidate-specific timestep guard, so do not rerun them expecting success.
Formal source qualification and E0–E6 acceptance still use their declared
review and validation steps. Stop a trial for an observed failure or resource
limit and preserve its evidence; one GPU at a time avoids device contention.

Each GPU checkpoint writes a new immutable evidence directory with source
revision, dirty state, image ID, code/input hashes, device/driver, command,
exit status, logs, resource use and gate decision. Build scripts must not
overwrite prior attempt logs. Runtime launchers must verify application-level
completion markers and expected final physical time, reject solver error/abort
markers even if the container exits zero, and fail on missing or header-only
required artifacts. Sample actual device and process/container memory during
the run; a pre-run `nvidia-smi` snapshot is not a peak measurement. The primary
keeps the GPU queue and CPU worker queue visible in `docs/STATUS.md`; if a
scientific gate is waiting on review or inputs, schedule independent source
preparation or benchmark work instead of running ahead of the gate.

## Task packet

```text
Objective / scientific gate:
Inputs and exact source locations:
Owned files (all other writes require coordination with the primary):
Interface and dependencies:
CPU / threads / RAM / GPU / wall-time budget:
Checks with independent expected results:
Required outputs and evidence paths:
Known assumptions and forbidden inferences:
```

Handoffs include exact commands and results, changed files, uncertainty, and any
open findings. Update the task packet when scope changes rather than allowing
two workers to edit the same file. Never have workers manipulate the shared Git
index concurrently. No commit or publication is required for local initialization.

## Long runs and continuation

Before expensive CFD, create an experiment record from `experiments/TEMPLATE.md`.
The first pilot measures feasibility; subsequent runs use measured allocations
and a projected physical-time cost. Store checkpoints and compact metrics often
enough to resume within the declared budget. Give each run an immutable directory
and a manifest. Record failures and stopped jobs, not only successful outputs.

At handoff or context reset, `docs/STATUS.md` must identify the active gate, exact
running process/job and output directory if any, outstanding review findings,
next commands and missing data. Do not restart a long job just because its agent
context changed. Existing user authorization carries forward.
