# Track 2: aerial drop to useful ground strip

This repository implements the [experiment plan](track2_aerial_drop_experiment_plan.md)
for comparing conventional release with a prescribed four-slot Restás/i4f source.
The intended solver combines conservative nearfield VOF, checked descent transport,
and one shared ground-map scoring implementation.

The current implementation has the **E0 analytical foundation**, an
equation-checked isolated-drop momentum component, and a provisional four-slot
water-air VOF characterization case. The case is an early CPU pilot; it does
not validate breakup or establish a design improvement.

## Start here

Python 3.12, `uv`, and `make` are available on the initial workstation.
From the repository root:

```bash
make setup
make doctor
make check
make e0
make papers
make digitize
```

Dependencies are pinned by `uv.lock` in `.venv`. `make papers` needs Poppler's
`pdftotext`; `make digitize` needs Poppler's `pdftoppm` and `pdftocairo`. These
tools were available on the initial machine. `make papers` creates a local text
cache and SHA-256 inventory; the available digitization scripts deterministically
rebuild their documented E2-E4 figure-read CSVs from the supplied PDFs. These
CSV files remain figure-derived references, not raw experimental data. Original
PDFs remain unchanged. Generated runs go under `results/runs/` and are not
committed. Each E0 run is analytical verification; its synthetic footprint is
not a prediction for either aircraft.

The isolated-drop momentum relations from Denner (2026) are implemented in
`aerial_drop.parcel_motion`; run their equation and event checks with
`make test`. This is a fixed-radius single-drop component only. It omits
evaporation and dense-plume physics, and it does not supply the unknown size
distribution or conserve a future VOF-to-parcel transfer. Its source, scope,
and next validation gates are recorded in
[`experiments/REGION_C_DENNER_ISOLATED_DROP.md`](experiments/REGION_C_DENNER_ISOLATED_DROP.md).

For the optional GPU checks, `make gpu-smoke` verifies a native CUDA kernel in
a digest-pinned image. The repository also has an isolated, pinned FluTAS
Blackwell image: `make flutas-build` creates it under a two-CPU cap, and
`make flutas-gpu-gate` serializes the OpenACC kernel, CUDA-buffer MPI, and
upstream rising-bubble checks through the shared GPU lock. That build passed
its upstream checks on this RTX 5090, but has no Restas slot-source extension;
it is not yet cleared for the project GPU pilot. See
[`containers/flutas/`](containers/flutas/) and
[`docs/GPU_FLUTAS_FEASIBILITY.md`](docs/GPU_FLUTAS_FEASIBILITY.md) for the
evidence and next gate.

The local OpenFOAM image also enables `make restas-pilot`. It writes a fresh case
and evidence bundle under `results/runs/`. The pilot uses CPU OpenFOAM, does not
use the RTX 5090, and does not simulate the full aircraft-to-ground drop. Read
[`cases/restas_four_slot/`](cases/restas_four_slot/) and
[`experiments/P0_RESTAS_CPU_VOF.md`](experiments/P0_RESTAS_CPU_VOF.md) before
interpreting its provisional nearfield fields. To render actual solver output,
install `uv sync --frozen --extra visualization` and use
`make render-pilot RUN=results/runs/<run-id> TIME=0.08`; see
[`docs/RENDERING.md`](docs/RENDERING.md). The single-frame view is exploratory.
For actual timestamped surfaces, the same guide documents the provenance-checked
diagnostic and validated animation modes. The available six-frame P0 render is
only a 0.10 s nearfield diagnostic, not the planned full experiment.

The Rouaix Case 1 source record includes vector-path and independent raster
traces of Figure 13 in [`experiments/E1_ROUAIX_CASE1_SOURCE.md`](experiments/E1_ROUAIX_CASE1_SOURCE.md).
The two traces agree within their extraction bounds. The paper's Section 4.3
relations are separate cross-case empirical fits with unreported scatter, so
their residuals are a secondary consistency check rather than a demonstrated
source contradiction. E1's figure semantics and source-aware tolerances remain
open.
P1 revision 1 completed a full 0.12 s run but failed its frozen sampled-dose
gate; see the [first-run audit](results/P1_SOURCE_EVENT_LEDGER_FIRST_RUN.md).
Independent review approved the alpha-flux time-centering amendment with the
original 0.1% tolerance and approved the exact runner/analyzer hashes. A new
revision-2 confirmation with clearly labelled provisional inputs completed, and
the automated report plus independent raw-output audit pass all P1 checks. See
the [revision-2 result](results/P1_SOURCE_EVENT_LEDGER_REV2.md). The old run
remains failed under revision 1. `make prepare-source-ledger` prepares a case
without starting the solver. Astra Max prospectively reviewed and re-froze the
current Makefile and six-file launch path; focused non-solver checks confirm
the real contract, reject a stale hash, reproduce the accepted case inputs,
and match the recorded OpenFOAM image. `make restas-source-ledger` is ready for
an optional replay, but no new run is needed to retain the completed
revision-2 result. P1 only checks source timing and mass accounting; it does
not validate breakup or aircraft performance.

The Calbrix Dash-8 and CL-415 source records are in
[`experiments/E2_CALBRIX_SOURCE.md`](experiments/E2_CALBRIX_SOURCE.md) and
[`experiments/E3_CALBRIX_CL415_SOURCE.md`](experiments/E3_CALBRIX_CL415_SOURCE.md).
E3 now has paired independent reads of the plotted scalar outlet velocities;
E2 has independent Dash-8 cloud-envelope traces, and E3 has two reads of the
supplemental structure-count figure. These extractions check figure-reading
reproducibility only. Missing discharge inputs, outlet mappings, and
paper-method details remain; neither experiment is a runnable exact replay or
a benchmark pass.

## Agent workflow

Open this repository in Codex. [AGENTS.md](AGENTS.md) instructs the primary agent
to coordinate and review independent **GPT-6 Luna / Max** workers. The project
configuration sets three concurrent workers, leaving the primary model selected
by the user. Reopen the project/session to load newly added configuration;
explicit spawn settings are also documented for clients with different controls.

The initial setup itself uses three Luna Max workers. Future work follows
[the workflow](docs/WORKFLOW.md), including an independent scientific review before
integration. Workers receive disjoint files and a shared compute budget.

## Scientific and compute contracts

- [Validation](docs/VALIDATION.md): E0–E6, conservation, refinement, measured-data
  checks, and limits on scientific claims.
- [References](docs/REFERENCES.md): supplied papers, provenance and missing inputs.
- [Compute](docs/COMPUTE.md): actual machine inventory, resource limits and GPU pilots.
- [Experiment template](experiments/TEMPLATE.md): inputs, tolerances and stop criteria
  to declare before running a scientific case.
- [Current status](docs/STATUS.md): completed work and the next unresolved gates.

The primary outputs are the continuous qualifying length `L95`, the dose-capped
useful fraction, and a complete mass ledger. Compare matched conditions before
separate operational scenarios. Nearfield numerical agreement, collected ground
fraction, and useful-strip performance provide different evidence.
