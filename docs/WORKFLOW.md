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
warden is read-only and is invoked at major gate transitions, after source or
solver architecture changes, after two completed checkpoints, when a blocker
repeats, or immediately for a high-severity cross-discipline decision that can
redirect the critical path. It audits the project-level critical path, resource
queue, stale status and user-only dependencies, and returns concrete assignments
with owners, dependencies and acceptance evidence for hard blockers. It does not
edit the shared plan or approve scientific gates. The primary remains
the single orchestrator and integrates each warden memo. Archive each memo in
`docs/reviews/PROJECT_WARDEN_<UTC timestamp>.md`, then update the status and
blocker plan with only the steering needed for the next work cycle.

A completed checkpoint is a bounded deliverable with its prescribed checks,
exact evidence references, and a recorded primary handoff disposition. Status
edits, repeated discussion, and unchanged reruns do not count. Record the last
Warden memo, completed checkpoints since it, and the next trigger in
`docs/STATUS.md`; coalesce simultaneous triggers over the same evidence snapshot.
Each recommendation names its blocker, owner, prerequisite, next action,
acceptance or stop evidence, and CPU/GPU eligibility. For repeated blockers,
the Warden identifies the attempted resolution and remaining evidence, then
proposes a bounded discriminating check, implementation change, or supported
fallback. The primary records each recommendation as accepted, deferred, or
rejected, including a reason and the next evidence trigger. Warden advice never
replaces exact independent review or the primary's launch decision.

For a repeated, cross-discipline, or critical-path blocker needing a deeper
resolution plan, assign the Astra Max `blocker_planner` role a separate,
timestamped memo. Require ranked fixes, owners, dependencies, precise
acceptance evidence, CPU/GPU eligibility, and whether user or external evidence
is actually required. Use the Astra Max `general_reviewer` role for a separate
repository-wide consistency audit. Keep those deliverables disjoint from the
Warden's read-only steering memo and implementation files; the primary
integrates accepted advice and owns shared plans and gate decisions.

These Astra roles are recurring assignments, not background processes. Invoke
them explicitly as `gpt-6-astra` with `max` reasoning, using a fresh or limited
context; reuse an idle role agent for follow-up work when possible. The Warden
is occasional and consumes one of the same three worker slots while active. Do
not keep a completed role occupying a slot or run duplicate reviews of the
same evidence snapshot. Keep the role, live assignment, model/effort and next
trigger visible in the STATUS queue; the Luna defaults in `.codex/config.toml`
do not implicitly configure Astra tasks.

## One work cycle

1. Read `docs/STATUS.md`, the experiment plan and affected contracts. Inspect the
   worktree before editing. Run the resource doctor before scheduling simulations.
2. State the next gate and its acceptance evidence. Assign separate tasks such as
   source extraction, implementation and independent benchmark preparation.
3. Give each worker file ownership, dependencies, interfaces, CPU/thread/memory/GPU
   allocation, expected artifacts and checks. The primary owns shared interfaces.
4. Keep research and light CPU work moving while a single GPU pilot runs. Reassign
   finished workers to review; don't launch more expensive jobs than fit the
   shared resource budget.
5. Review contributions and their source evidence. For physics or metric changes,
   have a worker who did not write the implementation derive independent expected
   results and challenge conservation, frames, sampling and missing physics.
6. Integrate fixes, run relevant checks, record the gate decision and update status.
   A passing unit test does not automatically pass a paper or field benchmark.

## Keep useful work parallel without overbooking hardware

Use all available worker slots for independent work when the queue supports it:
for example, one paper/source task, one implementation task, and one separate
review or tooling task. A worker blocked on a dependent interface should return
that dependency to the primary instead of holding a slot. Keep CPU allocations
within the shared machine budget reported by `make doctor`; reserve two cores
for the host and do not multiply each agent's advertised budget by the number
of workers.

At every worker handoff, rebalance the workers and compute queues. Fill every
available slot with independent, gate-ready work and budget CPU jobs against
measured headroom, up to the shared 18-core ceiling. The throughput target is
the measured safe compute budget: overlap eligible GPU trials with independent
CPU work and avoid idle ready work. Each GPU-relevant software checkpoint gets
its smallest meaningful GPU trial promptly after exact candidate review and
other prerequisites pass. Record `not applicable` for CPU-only checkpoints or
the exact gate blocking a GPU trial. Keep one ordered GPU queue. Do not start
duplicate or dependent GPU runs to raise utilization; use measured profiles to
size the next approved trial.
Capture completed workers' handoffs and promptly reassign or release their
slots whenever independent ready work remains.

At every handoff, material dependency change, and Warden checkpoint, refresh a
timestamped queue ledger in `docs/STATUS.md`. List each worker's current task,
each compute job's ready/running/blocked/finished state, owner, exact candidate
and review state, resource ceiling, and next evidence trigger. Distinguish
occupied agent slots, running processes, resource allocations, and measured
utilization; when a queue is empty, name the dependency that holds it.

The machine has one RTX 5090, so GPU work is serialized by the shared launcher
lock. Native compilation and code-object inspection use the CPU. After exact
candidate review and the other prerequisites for a checkpoint pass, run the
smallest relevant GPU runtime trial while independent CPU-only work continues
in parallel. One GPU trial at a time is the device limit; CPU work and worker
assignments should fill other measured safe capacity. A candidate GPU runtime regression is
eligible only after an independent review of the exact candidate; it must run
with source mode disabled, without a source-boundary input, and be recorded as
a solver regression check rather than a source gate. For the source-boundary
path, the currently frozen positive sequence is quiescent `dry_four` →
one-slot → four-slot. The frozen `dry_crossflow` and `crossflow_four` inputs
are expected-negative timestep-guard fixtures and are not executable cases.
Positive crossflow requires a prospective versioned protocol amendment and
exact independent review. Run approved dependent solver cases on the GPU
**sequentially** only after inputs, acceptance limits, telemetry, output
analyzer, resource ceiling and independent review are frozen. Stop at the
first failed case. Parallelizing dependent GPU cases would obscure failure
causality and compete for the only device.

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
