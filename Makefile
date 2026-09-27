.DEFAULT_GOAL := help
UV ?= uv
PYTHON ?= .venv/bin/python

# Pinned linux/amd64 manifest for nvidia/cuda:12.8.0-devel-ubuntu24.04.
CUDA_IMAGE ?= nvidia/cuda@sha256:9a8fffc32a955361aa66d754e7a0cda2513052eaf5aaf8f3ba69b80578d1c6a9

.PHONY: help setup doctor check test lint format e0 papers digitize digitize-e2 digitize-e3 digitize-e4 gpu-smoke flutas-build flutas-gpu-gate restas-pilot prepare-restas-pilot prepare-source-ledger restas-source-ledger prepare-restas-still-air restas-still-air render-pilot render-animation

help:
	@echo 'make setup   Install the locked Python environment with uv'
	@echo 'make doctor  Inspect CPU/RAM/GPU/tool readiness'
	@echo 'make check   Run lint, format checks and analytical/tooling tests'
	@echo 'make e0      Write a fresh analytical verification run'
	@echo 'make restas-pilot Run the predeclared four-slot CPU VOF characterization pilot'
	@echo 'make prepare-restas-pilot Generate that case without starting the solver'
	@echo 'make prepare-source-ledger Generate the reviewed P1 source/ledger case without running it'
	@echo 'make restas-source-ledger Run P1 only after its execution contract is marked ready'
	@echo 'make restas-still-air Run the exploratory 1 s, 10 m still-air CPU VOF case (about 1.6 million cells)'
	@echo 'make prepare-restas-still-air Prepare its immutable case bundle without starting the solver'
	@echo 'make render-pilot RUN=results/runs/<run-id> [TIME=seconds] Render one computed VOF frame (latest by default)'
	@echo 'make render-animation RENDER_CASE=label=results/runs/<run-id> RENDER_OUTPUT=results/runs/<new-id> Render one diagnostic animation'
	@echo 'make papers  Index and extract the supplied PDFs locally'
	@echo 'make digitize-e2 Rebuild Dash-8 Fig. 4 second read and Figs. 6-9 cloud-envelope traces'
	@echo 'make digitize-e3 Rebuild CL-415 Fig. 4 velocity and Fig. 11 structure-count traces'
	@echo 'make digitize-e4  Rebuild the plotted M134 Fig. 9 marker trace from the local PDF'
	@echo 'make digitize  Run all scripted E2-E4 paper-trace rebuild targets'
	@echo 'make gpu-smoke  Compile and run a small native CUDA kernel in Docker (GPU preflight only)'
	@echo 'make flutas-build Build the pinned FluTAS cc120 image (2 CPU build cap)'
	@echo 'make flutas-gpu-gate Build the image, then run OpenACC, GPU MPI and bubble checks'
	@echo 'make format  Format Python source, scripts and tests'

setup:
	$(UV) sync --frozen

doctor:
	$(PYTHON) scripts/doctor.py --output results/machine.json

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src scripts tests
	$(PYTHON) -m ruff format --check src scripts tests

check: lint test

format:
	$(PYTHON) -m ruff check --fix src scripts tests
	$(PYTHON) -m ruff format src scripts tests

e0:
	$(PYTHON) scripts/run_local.py --threads 1 -- $(PYTHON) -m aerial_drop.e0

papers:
	$(PYTHON) scripts/index_papers.py

digitize: digitize-e2 digitize-e3 digitize-e4

digitize-e2:
	$(PYTHON) scripts/digitize_calbrix_dash8_fig4_velocity_independent.py
	$(PYTHON) scripts/digitize_calbrix_dash8_cloud_curves.py
	$(PYTHON) scripts/digitize_calbrix_dash8_cloud_curves_independent.py

digitize-e3:
	$(PYTHON) scripts/digitize_calbrix_e3_fig4.py
	$(PYTHON) scripts/digitize_calbrix_e3_fig4_independent.py
	$(PYTHON) scripts/digitize_calbrix_e3_fig11.py
	$(PYTHON) scripts/digitize_calbrix_e3_fig11_independent.py

digitize-e4:
	$(PYTHON) scripts/digitize_amorim_m134_fig9.py

gpu-smoke:
	docker pull "$(CUDA_IMAGE)"
	$(PYTHON) scripts/run_local.py --threads 1 --gpu -- docker run --rm --pull=never --gpus all \
		-v "$(CURDIR)/scripts/cuda_device_smoke.cu:/tmp/cuda_device_smoke.cu:ro" \
		"$(CUDA_IMAGE)" bash -lc 'nvcc -arch=sm_120 -o /tmp/cuda_device_smoke /tmp/cuda_device_smoke.cu && /tmp/cuda_device_smoke'

flutas-build:
	containers/flutas/build-image.sh

flutas-gpu-gate: flutas-build
	containers/flutas/run-gpu-gate.sh

restas-pilot:
	$(PYTHON) scripts/run_local.py --timeout 3600 -- $(PYTHON) scripts/run_restas_pilot.py

prepare-restas-pilot:
	$(PYTHON) scripts/run_restas_pilot.py --prepare-only

prepare-source-ledger:
	$(PYTHON) scripts/run_restas_pilot.py --source-event-ledger --prepare-only

restas-source-ledger:
	$(PYTHON) scripts/run_local.py --threads 16 --timeout 3660 -- $(PYTHON) scripts/run_restas_pilot.py --source-event-ledger

restas-still-air:
	$(PYTHON) scripts/run_local.py --threads 16 --timeout 36660 -- $(PYTHON) scripts/run_restas_still_air_vof.py --threads 16 --memory-gib 48

prepare-restas-still-air:
	$(PYTHON) scripts/run_restas_still_air_vof.py --threads 16 --memory-gib 48 --prepare-only

render-pilot:
	@test -n "$(RUN)" || (echo 'Set RUN=results/runs/<run-id>' >&2; exit 2)
	$(PYTHON) scripts/render_restas_pilot.py --run-dir "$(RUN)" $(if $(TIME),--time "$(TIME)",)

render-animation:
	@test -z "$(RENDER_MODE)" -o "$(RENDER_MODE)" = diagnostic || (echo 'make render-animation is diagnostic-only; invoke scripts/render_aerial_animation.py directly for validated mode' >&2; exit 2)
	@test -n "$(RENDER_CASE)" || (echo 'Set RENDER_CASE=label=results/runs/<run-id>' >&2; exit 2)
	@test -n "$(RENDER_OUTPUT)" || (echo 'Set RENDER_OUTPUT=results/runs/<new-id>' >&2; exit 2)
	$(PYTHON) scripts/render_aerial_animation.py --mode diagnostic --case "$(RENDER_CASE)" --output-dir "$(RENDER_OUTPUT)" --fps "$(if $(RENDER_FPS),$(RENDER_FPS),6)" --size $(if $(RENDER_SIZE),$(RENDER_SIZE),1600 900)
