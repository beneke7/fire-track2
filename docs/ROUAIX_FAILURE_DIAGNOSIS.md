# Rouaix failure diagnosis and next tests

Updated 28 October 2026, 14:00 UTC. This is the ranked working diagnosis for
the numerical failures, with separate notes on reproduction fidelity. It is
not an E1 acceptance decision.

The strongest present evidence concerns open-boundary pressure treatment.
The coarse all-air original and upwind cases failed near the same corner.
Changing only four open pressure patches to `prghTotalPressure p0=0` let the
matched all-air case complete 0.30 s: maximum speed over the run was
85.04 m/s, versus a 1364.74 m/s terminal maximum in the original at 0.1752 s.
The pressure candidate also completed a fresh water-injection run through
0.30 s: peak speed103.15 m/s, reported alpha in[0,1], bulk/interface Courant
maxima0.262/0.168 and a-3.65e-10 kg phase-balance residual. Its matched
original-pressure water control reached the200 m/s operational guard around
0.17 s. These controlled results establish a practical stability improvement
on this coarse mesh, while fine-grid transfer and paper agreement remain open. A separate fixed0.3 ms
water trial also completed0.30 s:1,000 steps in274 solver seconds, peak105.32 m/s,
alpha[0,1] and bulk/interface Co maxima0.776/0.491. Its field-level time-accuracy
comparison is still open. The0.1 ms reference remains preserved.

## Physical and numerical causes

1. **Reverse-flow pressure treatment — leading supported suspect.** Current
   static-pressure outlets and prescribed reverse-flow tangential velocity can
   interact with the pressure/velocity solution. The controlled pressure change
   removed the coarse air runaway through 0.30 s. The matched water pair now supports the same boundary sensitivity. Next,
   run the fine-grid restart and inspect local boundary flux signs. This is
   evidence of boundary sensitivity, not proof that the candidate is the correct
   physical far-field condition.

2. **Three-boundary corner — supported location, mechanism unresolved.** The
   coarse peak is an internal cell touching aircraftWall, downstreamOutlet and
   spanwisePlus. A sharp change between wall and open conditions can concentrate
   gradients. Inspect face fluxes and local pressure/velocity gradients; compare
   a controlled boundary extension or corner treatment if required. Do not
   transfer the coarse cell geometry to the fine mesh without checking it.

3. **Mesh quality and abrupt grading — plausible, not an automatic explanation.**
   The coarse hotspot is a regular unrefined hex cell and its global mesh checks
   passed. The fine mesh has its separately documented concavity qualification.
   Map the fine hotspot, inspect cell-local skewness/nonorthogonality and refine
   or improve the offending transition. A global Mesh OK does not prove adequate
   accuracy, and hex cells are not inherently better than the paper's mesh.

4. **Insufficient pressure/velocity coupling — untested control.** The current
   reference uses one PIMPLE outer iteration and three pressure correctors.
   Test two outer iterations with the original pressure boundaries. In v2512,
   later outer iterations also change alpha-flux averaging, so this is not
   exclusively a pressure-solver change. SIMPLE and PIMPLE are not inherently
   incompatible, but their settings are not interchangeable stability guarantees.

5. **Timestep and local Courant number — plausible contributor.** Fixed 0.1 ms
   does not guarantee small local Courant numbers. Halve the timestep in a
   matched branch or test adaptive stepping with recorded bulk/interface limits.
   Keep the fixed-step reference. The paper's 1 ms step used a different mesh,
   coupling algorithm and interface scheme; its step cannot be transferred alone.

6. **Momentum interpolation, gradients and limiter choice — partly tested.**
   Upwind delayed but did not cure the coarse all-air failure. The previous
   bounded-gradient fine-water trial failed much earlier near the nozzle, so
   blanket gradient limiting is not an established cure. Test one scheme change
   at a time, preserving boundedness diagnostics and comparing the same time.

7. **RANS closure and turbulent transport — plausible interaction.** Large
   k/epsilon/nut values were recorded in the water donor; they need field-level
   interpretation. A matched laminar static-pressure air control is the cheapest
   missing discriminator. If it also fails, RANS is not necessary for that
   failure; if it is stable, test turbulence transport and wall treatment. Laminar
   stability alone does not reproduce the Case 1 RANS calculation.

8. **Turbulence inlet values and startup — uncertain inputs, no obvious typo.**
   The current nozzle/gas k values scale with velocity squared and epsilon with
   velocity cubed, consistent with the same nominal intensity and length scale.
   The paper supplies liquid intensity but omits air-side intensity and several
   startup details. Use declared intensity/length-scale sensitivities; do not tune
   these values merely to suppress an instability.

9. **Near-wall resolution and wall model — important fidelity difference.**
   The paper used five prism layers and two-layer wall treatment. Our current
   mesh/wall-function combination is not that construction. Measure y-plus and
   near-wall resolution, then use a compatible wall treatment and a controlled
   layer/refinement study. This may affect shear, turbulence and plume shape even
   if the open-boundary instability is removed.

10. **VOF advection and large density contrast — possible additional water issue.**
    The air controls prove an interface is not necessary for the coarse failure.
    Water can still introduce separate density/flux coupling problems. Monitor
    raw alpha extrema, interface Courant number and mass/momentum consistency;
    test phase advection/subcycling only in separately matched branches. Small
    global mass error does not establish stable or accurate momentum transport.

11. **Surface tension and curvature — lower priority for the repeated air event.**
    Spurious interface currents or a restrictive capillary timestep could affect
    water cases, but cannot be the necessary cause of an exactly all-air case.
    Use a static-interface benchmark and a labelled sigma sensitivity if the
    water-only failure persists. Do not remove surface tension from a claimed
    reproduction merely to obtain a clean run.

12. **Pressure reference, gravity conversion and boundary compatibility — checked
    basics, remaining interactions.** The current p_rgh dimensions and gravity
    sign are coherent with the declared frame. Negative p_rgh is not by itself
    negative absolute pressure or cavitation. Check reconstructed pressure,
    mixture density, local phi, U and backflow alpha together. Avoid fixing a
    full velocity vector on open faces: that would also constrain normal flow.

13. **Linear solver conditioning and stopping criteria — symptom and possible
    contributor.** The failed continuation ended in GAMG, with eleven failed
    U/k/epsilon solve records. Pressure records meeting their configured criteria
    did not make the whole calculation converged. Examine equation residuals,
    iterations and conditioning before testing an alternative solver/preconditioner.
    Disabling floating-point traps would hide the failure rather than repair it.

14. **Initial state and restart reconstruction — controlled but not bitwise
    equivalence.** A native restart smoke passed and the unchanged continuation
    crossed the same 1000 m/s threshold time and reported point as the old run.
    Retain same-scheme restart controls and immutable parent hashes. Compare
    early histories before blaming a scheme change; stored fields alone do not
    imply all solver-internal histories are identical.

15. **Properties, incompressibility and omitted physics — lower current priority.**
    Source water/air properties are recorded against the paper. Recheck units,
    mixture-property use and absolute pressure if a water-specific failure
    remains. The enormous numerical velocities are not evidence of a physical
    supersonic plume. A new compressible/cavitation model is not the first remedy
    for an instability already present in the simple air control.

16. **MPI decomposition, builds and roundoff — possible influence, weak primary
    explanation.** One-node and three-node native water cases both failed in
    the same window; coarse cases also fail on Goblin's different MPI build.
    Preserve executable identities and compare matched decompositions if needed.
    More cores can change cost and roundoff, but do not correct a boundary model.

## Workflow failures and reproduction limits

17. **Stop and checkpoint control — confirmed separate workflow defect.** The
    old receipt could list signal 12 without an acknowledged request and stored
    its timestamp after waiting. Those receipt defects are corrected in the new
    source. The native probe then found that its active-step lookup reports
    not-found while the owned step is alive; this can prevent the signal request.
    The corrected public helper passed a live owned-step probe, then the120-rank
    native smoke14700599 saved at0.2005 s with End/exit0 and verified fields/ledger.
    The complete native save path now passes this healthy diagnostic. This
    explains lost endpoint evidence, not the physical velocity growth.

18. **Launcher and metadata parsing — earlier confirmed, repaired failures.**
    The argument-bearing FOAM_BASH was quoted as a filename, a source path omitted
    unpacked, and a literal time check rejected floating-point roundoff. These
    were failures before CFD. Their fixes and failed attempts are retained; the
    completed native restart demonstrates that those startup blockers are past.

19. **Memory, disk, allocation and wall limits — not supported as causes of the
    recorded runaway.** The failed control received all 120 ranks and failed well
    before its time cap with an FPE. The current small trials use about 1 GiB each.
    Keep actual resource monitoring and sparse collated output; allocation or
    storage tuning addresses throughput and reliability, not an unstable PDE.

20. **Stable execution versus paper reproduction — separate requirements.**
    Rouaix used STAR-CCM+, SIMPLE, HRIC, second-order-upwind convection,
    first-order implicit time, polyhedral cells and five prism layers. Our
    OpenFOAM/PIMPLE/isoAdvection construction differs and some original BC/startup
    details are unpublished. A stable 0.30 s diagnostic is useful progress; a
    reproduction still needs the paper's resolution pattern, longer horizon and
    penetration/width/breakup comparisons. A smoother alpha rendering is not an
    acceptance test.

## Current sequence

Complete and audit the matched coarse water pressure pair. In parallel, repair
and verify native early-save delivery, then prepare the fine-grid pressure-only
restart from the same 0.20 s donor, with a 0.25 s diagnostic checkpoint and
0.30 s target. If the pressure change fails, use the matched laminar air control
and a separate two-outer-iteration control to distinguish turbulence and coupling.
No field clipping or changed physical acceptance tolerance is part of this plan.

## Evidence

- [Native restart terminal logs and audits](../results/summaries/rouaix_restart_controls_20261027/terminal-v4/README.md).
- [Historical matched air results](../results/summaries/rouaix_fast_local_20261027/terminal-local/README.md).
- [New boundary trial declaration](../experiments/E1_ROUAIX_BACKFLOW_LOCAL_20261028.md)
  and [matched-time comparison](../results/summaries/rouaix_backflow_local_20261028/matched-time-comparison.json).
- [Coarse corner geometry inspection](../results/summaries/rouaix_corner_inspection_20261028/README.md).
- [Pressure boundary source review](../results/summaries/rouaix_restart_controls_20261027/outlet-control-review.md).
- [Rouaix paper extraction, pages and assumptions](../experiments/E1_ROUAIX_CASE1_SOURCE.md).
