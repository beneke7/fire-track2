# Region C foundation: isolated-drop momentum

**Status:** equation-checked numerical component; not a validated spray or
delivery simulation. Inputs below use explicitly provisional ambient values.

## Source and implemented equations

This case implements the single-drop momentum model in Fabian Denner,
*Water droplet dynamics and evaporation in airtanker firefighting*,
arXiv:2603.11855v1 (12 March 2026), PDF page 3 (printed page 2), Eqs. (1)--(11). The supplied
PDF SHA-256 is
`3680edea35f5ccd9f3bedbb9afd6d6f9a54a3436533ddc0df66883dff909f9a2`.
The equations were checked against the rendered source page, not OCR alone.

For a constant-radius drop of volume `V = 4*pi*r^3/3`, the acceleration is

`g*(rho_w-rho_a)/rho_w + 3*rho_a*Cd*|u_a-u_d|*(u_a-u_d)/(8*rho_w*r)`.

The implementation uses the paper's Clift--Gauvin spherical drag relation
(Eq. 6), deformation correction and `r_max` relation (Eqs. 5 and 7), and
Reynolds/Weber and critical-Weber breakup criterion (Eqs. 8--11). Classical
fixed-step RK4 advances position and velocity. A bisection localizes detected
ground and breakup events inside the final integration step. A fixed-radius
trajectory ends at the first such event; no post-breakup path is generated.

The default properties (`rho_w=997 kg/m^3`, `rho_a=1.204 kg/m^3`,
`mu_a=1.81e-5 Pa s`, `sigma=0.072 N/m`, `g=-9.81 m/s^2` vertically) are
provisional values near ambient 20 C, not measured Restas conditions and not
copied as a complete parameter set from Denner. Comparisons should provide
their documented properties. The result flags radii outside the paper's
cited nominal 20 um--2 mm primary-drop range without silently rejecting an
explicit sensitivity input.

## Scope and handoff limits

The module assumes one isolated spherical-equivalent drop, constant radius,
constant uniform wind, and constant properties. It omits the paper's coupled
heat and mass transfer, spatial weather, dense-plume interactions, coalescence,
secondary-breakup products, turbulence, aircraft wake, parcel weighting, and
all VOF-to-parcel transfer. It therefore cannot initialize or validate the
Restas spray, predict a ground map, or substitute for E1--E6.

Coordinates use a ground-fixed right-handed frame: x along-track, y
cross-track, z upward, with gravity defaulting to negative z. `ground_z_m` is a
constant horizontal impact plane in that frame.

The code checks the momentum equations and numerical event behavior. It has not
yet reproduced Denner's coupled evaporation cases or been compared with an
independent measured trajectory. Passing its unit tests is equation-level
verification, not empirical or full-model validation. Before Region C can be
used in a coupled result, independently reviewed comparisons must cover
terminal fall speed, crosswind drift, drop-size sensitivity, timestep
convergence, and the selected paper cases. A future parcel handoff must retain
mass weights and close mass and vector momentum against the VOF flux as defined
in [`docs/VALIDATION.md`](../docs/VALIDATION.md).

## Reproducible checks

Run the component tests with:

```bash
.venv/bin/python -m pytest -q tests/test_parcel_motion.py
```

The tests include hard-coded equation vectors, independently checked drag
acceleration and terminal speed, zero-relative-velocity/buoyancy behavior, the
closed-form ballistic limit at vanishing air density, timestep-refined breakup
detection, ground-contact edge cases, input rejection, immutability, and
source-range reporting. The 4 mm breakup event is an algorithm check outside
the paper's cited nominal primary-drop range. These are numerical checks, not a
CFD or paper-validation pass.
