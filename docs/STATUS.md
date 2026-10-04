# Live project status

Updated: 2026-10-04 16:44 UTC. The user clarified **Dash-8** as the
single-opening paper case; diagnosing the failure is the current priority.
Only analytical E0 has passed. No quantitative paper or ground validation has
passed; measured Restás geometry/source histories remain pending.

## Actual compute and recovered results

The five-second Dash-8 attempt failed numerically at **1.039547 s** after
9,169 steps and 8,287 s solver clock time (2 h 18 min). The first extreme
epsilon residual appears at 1.039211 s; subsequent time steps collapse and
pressure/continuity diverge before a floating-point exception. This was not
a memory-limit or timeout stop. The first instrumented restart reached 1.08 s
without reproducing the crash. Its 5 ms adjustable writes change time-step
alignment, so a second controlled restart is now active on 20 ranks through
1.12 s. It uses unadjusted runtime writes and restores the original checkpoint
deltaT=0.00017281653 s, verified on all 20 ranks and in the original log.
Physics and solver schemes are unchanged. Per-step extrema include velocity,
pressure, k, epsilon, nut and alpha with locations; momentum flux is not logged.
The persistent controller stops on instability and preserves checkpoints.
[Active diagnostic record](../results/runs/dash8-failure-diagnostic-20261004T164125Z-runtime-writes/run-record.json).
[Failed original manifest](../results/runs/dash8-economy-overnight-20261001T210320Z/manifest.json).

All 20 ranks retain complete 0.1–1.0 s checkpoints. A Luna worker verified
800 required rank/time/field files and reconstructed alpha, velocity, k and
epsilon in a copied recovery bundle using the pinned solver image. The
failed original remains untouched. Frozen native-field analysis completed.
[Recovered analysis](../results/runs/dash8-recovery-20261004T173700Z/analytics/report.json).

At 0.5 s the dilute alpha>=0.001 cloud reaches 1.974 m downward and 1.253 m
maximum cross-track width. At 1.0 s these are 8.362 m and 5.833 m. Sampled
mass residuals are 0.0430% and 0.0173% of injected mass respectively, including
signed boundary escape flux. At the 1.0 s checkpoint the solver log still
shows normal Courant, turbulence residual and continuity values. That makes
it useful as a pre-failure diagnostic, not a validated solution.

The paper's digitized Fig. 6 cloud reaches 2.444 m in its displayed 0.5 s
range; ours reaches 1.895 m over that same streamwise interval and has a
nearly flat front. Median absolute curve separation is 0.442 m under the
assumed registration. Our opening center is not a verified paper origin,
so these unshifted overlays do not establish a validated pointwise error.
[Paper comparison plot](../results/dash8-paper-comparison-2026-10-04.png).
[Comparison data and source bounds](../results/dash8-paper-comparison-2026-10-04.json).
Fig. 8 shows a roughly 2.8 m maximum width, but its caption says 1.0 s while
the body says 0.5 s. Normalized Fig. 9 comparisons are conditional on our
inferred opening area; the paper's actual area remains unresolved.

Two 1920×1080, 30 fps videos now show the recovered 0–1.0 s interval at
10× slowdown, followed by a one-second hold (11 s total). Root inspected the
all-air first frame and the 0.5/1.0 s images. Alpha=0.5 display surfaces use
20 iterations of Taubin smoothing and SSAA; original cell fractions,
inventory and analytical diagnostics are unchanged. Stored states are held;
there is no temporal interpolation. The closer fixed view makes the water
visible without the large air-domain wireframe. Both label the failed run.
[Smoothed close-up video](../results/dash8-smoothed-alpha50-1s-10x-closeup.mp4).
[Full-domain video](../results/dash8-smoothed-alpha50-1s-10x.mp4).
A third [cloud-threshold video](../results/dash8-cloud-alpha0001-1s-10x.mp4)
uses alpha=0.001, matching the paper cloud threshold. Root inspected the
computed blobs; substantial morphology differences persist. Source-profile
interpretation and source/downstream grid sensitivity are the next priorities.

The earlier 0.1 s paired pilots passed. Reducing the distant-air spacing from
400 to 600 mm cut cells from 1,177,848 to 670,480 and solver clock from 484 to
326 s (1.48× speedup), preserving the source-region 80 mm cells and initial
sampled envelopes. Their 0.347% sampled mass residual and early speed do not
predict later stability or convergence. The serial queue's profile-CSV bug
was fixed without repeating CFD; its subsequent failure reflects the solver.

## Inputs, diagnostics and limitations

The new generator and aircraft-specific runner use one provisional
4.44 × 0.30 m downward belly opening, the primary digitized Dash-8 Fig. 4
velocity curve, 50 m/s relative airflow, water and standard k–epsilon.
Surface tension is omitted following the paper. Aircraft CAD is omitted as
requested. The 26 × 20 × 31 m domain follows published dimensions; placement,
flat slip roof, numeric air properties and inlet turbulence remain assumed.
[Source record](../experiments/E2_CALBRIX_SOURCE.md).

The Fig. 2 dimensions describe tank features, so their use as opening area is
an inference. The paper also inconsistently calls the plotted velocity a mean
and a maximum. Uniformly applying it over this candidate area gives about
15,921 kg over five seconds; this is an assumed source integral, not measured
payload. It exceeds the generic 10 m³ capacity by 59%, a source-interpretation
warning rather than a calibration target. Only four cells span the opening
width. Actual upstream air is about 49.99 m/s; side air is about 51–53 m/s,
so the airflow is present. The assumed inputs give q=7.291 at 0.5 s versus
the paper's 7.90. [Flow audit](../results/dash8-flow-audit-2026-10-04.json).
The extracted curve still has 0.074 m/s at 5 s. No shutdown or sixth
second is invented. Streamwise registration uses the assumed opening center;
the paper's exact origin is unverified.

Static Cartesian refinement covers x=[-2.5,4], y=[-1.5,1.5], z=[-3,0] m.
The distant plume is coarser; this economy trial cannot establish converged
breakup or paper reproduction. Native diagnostics report water inventory,
boundary flux, alpha>=0.001 cloud and alpha>=0.9 core envelopes, face-connected
structures, equivalent sizes and velocities. Shared-point counts give a
connectivity sensitivity. No parcels, ground deposition or foam is modeled.

## Retained work and next decisions

The CL415 0.1 s pilot completed on 594,000 cells with 0.225% sampled mass
residual. Its two structures versus the digitized CL415 cloud count remain a
discrepancy. Fig. 3 specifies four CL415 exits and one Dash-8 exit; root corrected
its earlier geometry interpretation. The 3,540,900-cell CL415 half-second run
was stopped at complete 50 ms checkpoints on all 20 ranks. The horizontal
Restás 300 ms case also retains complete 50 ms checkpoints; neither resumes
while Dash-8 has priority. Their stopped bundles and failed attempts remain.

The matched AMR/static pair used 1.208/4.570 million peak cells and
4.72/12.64 GiB sampled RAM, but AMR was about 7% slower (7.66/7.14 h on
10 ranks). Static refinement is the present baseline. The SST trial diverged
at 30.599 ms; its cause remains unresolved. GPU solver work is outside the
critical path. Cluster access, scheduler, node memory and MPI/container policy
remain unverified.

Next: diagnose the epsilon-solve breakdown in a copied short restart, then
improve source-area interpretation and downstream grid sensitivity before
claiming a longer or quantitatively matched paper reproduction.
Do not compare Dash-8 counts to the CL415-only Fig. 11. Formal paper acceptance
still needs declared uncertainty, tolerances, refinement and independent review.
Software checks on 4 October passed 354 tests with one optional Docker smoke
skipped; both new smoothed videos encoded and their actual frames were inspected.
No E1–E6 acceptance decision was made. Curated videos, previews, comparison
data and their provenance are included for publication; raw run bundles remain
local and ignored.
