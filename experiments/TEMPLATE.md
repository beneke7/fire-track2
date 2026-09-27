# Experiment record: <ID / descriptive name>

Copy this file into an experiment-specific directory before a scientific run.
Fill every applicable field; mark missing data as missing. A draft with missing
acceptance criteria cannot pass a gate.

## Question and evidence class

- Plan experiment / region:
- Hypothesis and comparison:
- Evidence class: analytical / numerical benchmark / field comparison / design prediction
- Prerequisite gate decisions and artifacts:
- Status: draft / ready / running / passed / failed / inconclusive
- Owner and independent reviewer:

## Inputs fixed before execution

| Quantity | Value and SI unit | Measured / digitized / assumed / fitted | Source page/figure/table or file/hash | Uncertainty |
| --- | --- | --- | --- | --- |
| Payload, outlet geometry/spacing and velocity/history | | | | |
| Fluid properties and modeled phases | | | | |
| Aircraft height, speed, attitude and reference frame | | | | |
| Wind/airflow and environmental state | | | | |
| Target width, threshold and section pass fraction | | | | |

- Solver revision, build flags and dependency/driver versions:
- Geometry, boundary/initial conditions and coordinate transforms:
- Mesh/domain, time-step controls, parcel weights/count and random seeds:
- Handoff definition, overlap/direct-VOF reference, coupling assumptions:
- Evaporation/breakup/dispersion models and deliberately omitted physics:
- Calibration data and untouched validation case:

## Predeclared acceptance and stopping criteria

| Observable | Reference and extraction method | Error definition | Tolerance and justification | Outcome |
| --- | --- | --- | --- | --- |
| Released/ground/airborne/escaped/evaporated mass | | | | |
| Handoff mass and momentum flux | | | | |
| Penetration, width, breakup or deposition data | | | | |
| Ground map, L95 and useful fraction | | | | |

- Grid, timestep, parcel sampling, domain and handoff refinements:
- Threshold, section tolerance and map-resolution sensitivities:
- Source-data/digitization uncertainty and planned propagation:
- Numerical failure/stop conditions:
- CPU ranks × threads, RAM, GPU/VRAM, disk and wall-time budget:
- Pilot measurements, scaling evidence and projected cost:
- Checkpoint cadence, sparse full-field output times and resume command:

## Run and decision record

- Exact command and immutable output directory:
- UTC times, revision, dirty patch/code/input hashes, machine manifest:
- Raw data, mass ledger, errors, uncertainty intervals and overlays:
- Failed/stopped attempts and their reason:
- Independent review findings and resolution:
- Gate decision and evidence, including limitations:
- Changes needed before the next gate:

If criteria change after seeing results, preserve the old record, explain why,
and treat the revised case as a new experiment. An undefined control-length ratio
must remain undefined; report the two absolute lengths.
