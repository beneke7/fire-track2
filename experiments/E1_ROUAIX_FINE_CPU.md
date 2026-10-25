# Rouaix fine CPU startup resource pilot

Declared 24 October 2026 before launch. Exploratory resource and startup test;
no E1 acceptance decision or mesh convergence result is requested by this pilot.

The source is `Rouaix_28516.pdf`, DOI 10.1016/j.ijmultiphaseflow.2023.104419,
SHA-256 `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`.
PDF p.5/Table 3 Case 1 supplies D=0.4 m, liquid velocity (0,-10,0) m/s,
air (70,0,0) m/s and realizable k–epsilon. PDF p.6/§3.1 supplies first-order
implicit time integration, second-order convection and HRIC; this OpenFOAM
isoAdvector implementation is a different numerical method. PDF p.8/§3.3
explicitly gives hybrid Gauss/LSQ gradients with a Venkatakrishnan limiter,
locally refined 70/50/30/16 mm mesh regions and five prism layers. These are
transcribed from the original local PDF with `pdftotext -f 6 -l 8 -layout`.

Reuse Goblin's previously generated, checked mesh at
`results/runs/rouaix-static-mesh-quality-full-20261020T1949Z/candidate/case`.
It has 35,190,080 hex cells, a flat no-slip roof, no prism layers and trapezoid
x=[-2.5,17.5], y=[-10,0], roof z=[-3.5,3.5], bottom z=[-8,8] m.
Near-source directional edges are 11.49/11.49/21.875 mm; corridor edges grow
to approximately 67/73/39 mm. This is an anisotropic fine pilot, not an exact
16 mm paper Mesh1. Actual prior `checkMesh -allTopology -allGeometry` passed:
max nonorthogonality 24.16°, skewness 1.1215, minimum determinant 0.00236,
minimum face weight 0.4778. The 492 nozzle faces preserve the previous
82-face union, area 0.1237068965517 m², outward normal +y. The discretized
nozzle is 1.56% smaller than the analytic circle; speed is not renormalized.

Fresh air-filled t=0 fields and hydrostatic p_rgh come from that immutable
mesh package. Its physics/BCs and schemes are retained: incompressible
water/air, gravity (0,-9.81,0), atmospheric-pressure external outlets,
realizable k–epsilon, limitedLinearV momentum convection, upwind turbulence
convection, unrestricted Gauss-linear gradients and PBiCGStab/DILU momentum.
The latter choices are numerical diagnostic assumptions, not the paper's
specified gradient limiter or second-order turbulence convection. Air
intensity/length scale and wall functions remain provisional. This is not a
controlled isolation of refinement from all historical numerical changes.

Run stock pinned OpenCFD v2512 `interIsoFoam`, image
`sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`,
20 MPI ranks, quota 20 CPUs, BLAS/OMP one thread, 88 GiB memory/no swap.
Pilot horizon 0.002 s, fixed dt=0.0001 s (20 steps). Binary snapshots every
0.001 s; per-step native water-volume, alphaPhi_, phi and extrema diagnostics
are inherited. This horizon tests memory and initial timestepping only;
column breakup needs much longer than this pilot.

Goblin doctor measured 20 effective CPUs, 103.9 GiB available RAM and
198.1 GiB disk. Three old containers are paused; vmstat measured 98–99% idle.
Preserve old jobs and all failures. Decomposition is bounded to 20 minutes;
solver stop/write is requested at 40 minutes with five minutes to checkpoint.
Stop on max|U| >1000 m/s, nonfinite speed, 600 s with no printed time
advancement, free disk <30 GiB, or run/global PAUSE. The velocity threshold is
an operational failure guard, not accuracy tolerance. The memory cap limits
this qualification attempt; OOM is a recorded failure, not grounds to change
physics or repeat blindly. Do not use GPU compute or rendering.

The launcher creates a unique run, records git revision/dirty state, hashes,
source validation, solver logs, compact water ledger and process state. It
runs through `scripts/run_local.py --threads 1` in a durable systemd user
service. No automatic longer continuation is armed until measured startup
memory/throughput and stop/ledger behavior have been inspected.

At 21:52 UTC the resource recheck found an unrelated eight-CPU I4F container
and additional SGLang CPU work that appeared after the idle doctor sample.
The serial decomposition completed successfully in 115.894 s, exit 0,
without launching CFD. Its observed memory sample reached 13.74 GiB; this is
not a captured peak. The 20-rank clean-start case is preserved (12 GiB bundle).
The preparation supervisor was stopped before it could launch a solver.

The replacement durable service
`fire-track2-rouaix-fine-capacity-20261024T2154Z.service` is an actual finite
capacity watcher: up to 20 minutes, sampling host busy CPU and running
unpaused Docker containers every ten seconds. It launches the declared
20-rank/20-CPU pilot only when unrelated containers have stopped and sampled
CPU use is below one CPU equivalent; otherwise records
`prepared_capacity_deferred`. It honors PAUSE while waiting. No competing
work is stopped or throttled; no 20-rank result on a reduced quota is taken.
`--resume-prepared` consumes only a successful completed decomposition and
requires all twenty processor mesh boundaries. Old state, launcher and logs
are preserved. The current watcher is independent of this tool session.

## Startup audit and correction, 25 October 2026

Goblin completed the 20-way decomposition but did not run CFD. The prepared
capacity watcher launched the solver container after a low-busy sample; it
exited 127 before `mpirun` because `foamVersion` was unavailable after sourcing
the pinned image's OpenFOAM 2512 shell setup. The failure bundle remains
preserved at `results/runs/rouaix-fine-35m-startup-20261024T2225Z`; it records
zero solver samples, no printed simulation time, no native water ledger and no
solver memory measurement. The container's 88 GiB memory limit was configured,
not measured usage.

A one-CPU, 1 GiB, `interIsoFoam -help` probe in the same image exited 0 at
2026-10-25 08:27:45 UTC and printed `Using: OpenFOAM-2512 (2512)`, build
`_87ed40d2-20251219`, and `Arch: LSB;label=32;scalar=64`. The launcher now
records this installed solver banner before `mpirun` with strict shell failure
handling, so a failed help command cannot proceed into CFD. The original failed
state and logs were not edited. A future retry needs a new run ID and a clean
prepared attempt; reusing the failed container name/state would overwrite
evidence or conflict with the preserved Docker container.
