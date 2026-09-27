# Pinned FluTAS source/return boundary candidate

This folder contains a review candidate for the pinned FluTAS source commit in
[`source-pin.txt`](source-pin.txt). It is a synthetic, grid-aligned boundary
diagnostic. The slot dimensions are provisional project inputs and do not
represent the built aircraft device. The applyable source delta is
[`source-boundary.patch`](source-boundary.patch); the case records are under
[`cases/source_boundary`](cases/source_boundary).

The candidate uses a prescribed source at the top and a volume-matched return
at the bottom. Both z-normal velocities are Dirichlet and both z-pressure
conditions are zero-gradient Neumann. The pinned projection leaves the top
normal velocity unchanged for this pressure pairing, and the bottom normal
face is not pressure-corrected. The same prescribed boundary profile is
reapplied after generic velocity fills and after projection. This candidate has
not been independently approved for a source run.

## Frozen diagnostic inputs

The source fixtures are `quiescent_one`, `quiescent_four`, and
`crossflow_four`; `dry_four` exercises the same grid with no active slots or
source interval. The source fixtures share the following synthetic mesh and
pulse:

| Input | Frozen value |
|---|---|
| Centered coordinate frame | x = [−2, 2] m, y = [−1.05, 1.05] m, z = [0, 1] m |
| Solver coordinate frame | x = [0, 4] m, y = [0, 2.1] m, z = [0, 1] m; report x−2 and y−1.05 |
| Uniform cell width | Δx = Δy = Δz = 0.025 m |
| Grid | 160 × 84 × 40 = 537,600 cells |
| Slot geometry | Four 1.0 m × 0.15 m slots; 0.05 m edge gaps in x and y; long axis x |
| Slot masks, one-based i/j | (40..79,36..41), (82..121,36..41), (40..79,44..49), (82..121,44..49) |
| One-slot fixture | First/lower-left mask only |
| Dry fixture | Four-slot mesh with zero source masks and disabled interval [0,0) |
| Initial water/air | ρwater=1000 kg/m³, ρair=1 kg/m³, μwater=0.001 Pa·s, μair=1.8×10⁻⁵ Pa·s; empty initial VOF |
| Source normal speed | z+ W = −4.8 m/s on active slot masks; 0 elsewhere |
| Source interval | Zero-based half-open intervals [2,12), dt=10⁻⁴ s |
| Solver window | 14 steps, 0.0014 s; source intervals 12 and 13 are post-pulse checks |
| Requested pulse amount | 0.72 kg (0.00072 m³) per slot; 2.88 kg (0.00288 m³) for four slots |
| Return area | Full z− face, 4×2.1 = 8.4 m²; W = −Q/Areturn |
| Quiescent vector | Initial velocity (0,0,0) m/s; source vector (0,0,−4.8) m/s; gravity (0,0,0) m/s² |
| Crossflow vector | Initial and z-face tangential velocity (−50,0) m/s; source vector (−50,0,−4.8) m/s; gravity (0,0,−9.81) m/s² |
| Forcing | `is_forced=F,F,F`; `bvel=0`; `dpdl=0`; `bulk_ftype=cfr`; fixed dt; no restart/late initialization |

The negative x crossflow is the frozen P0-compatible diagnostic direction. The
x-period wrap time is 4/50 = 0.08 s, much longer than the 0.0014 s fixture.
Each mask is 40 x-cells by 6 y-cells; the centered 2-by-2 arrangement makes the
slot areas exact. This does not establish hardware geometry, aircraft boundary
conditions, ambient open-boundary behavior, or a validated nearfield model.

## Boundary table

Faces are ordered x−, x+, y−, y+, z−, z+. `PP` is periodic, `DD` is prescribed
velocity, and `NN` is a zero-gradient pressure/VOF condition. All `is_outflow`
flags are false. All pressure values and gradients in `bcpre` are zero.

| Face | U | V | W | Pressure | `cbcvof` | `is_outflow` | Applied value |
|---|---|---|---|---|---|---|---|
| x−, x+ | PP | PP | PP | PP | PP | false | periodic wrap |
| y−, y+ | PP | PP | PP | PP | PP | false | periodic wrap |
| z− | DD | DD | DD | NN | NN | false | U/V = background; W = −Q/Areturn |
| z+ | DD | DD | DD | NN | NN | false | U/V = background; W = −4.8 m/s on active masks and zero elsewhere |

The base `bcvel` W values on all faces are zero; the source helper sets z-face
normal W values after each generic `bounduvw`. The crossflow source mask inherits
U=−50 m/s and V=0 m/s, so its prescribed vector is explicitly
(−50, 0, −4.8) m/s. Quiescent source cells use (0, 0, −4.8) m/s. The return
normal speed uses the exact declared mask area and 4.8 m/s. The total-volume
return is predeclared from that same schedule and is part of the projected
velocity state. Measured geometric liquid-phase source flux is separately
recorded and asserted against the declared rate.

The outward volume convention is `F = ∫u·n dA`: at z+, n=+z and W<0 gives
−Q; at z−, n=−z and W<0 gives +Q. Thus a uniform bottom velocity
`W=−Q/8.4` cancels the top source's net boundary volume. The bottom return is a
volume outflow carrying the local outgoing phase; its velocity condition does
not prescribe liquid fraction.

## Source state and call order

Initialization sets projected state U₀ to source interval 0. At solver step
`istep`, the driver asserts that incoming corrected state Uₖ carries interval
k=`istep−1`, then advects VOF without changing its velocity. After the
preprojection generic velocity fill, it applies interval `istep` to next state
Uₖ₊₁. It reapplies that same profile after `correc`, so the pressure projection
sees the boundary conditions for Uₖ₊₁. The source and return are computed from
the exact mask area and remain unchanged during VOF advection. Inside `advvof`,
source-aware alpha and property halos are refreshed before flux sweeps. After
generic VOF fills, the source-aware inflow halos are reapplied before the next
sweep. For z, the geometric sweep measures slot liquid-phase volume as
`sum(max(0,−flux×dx×dy))`; dividing by dt gives actual geometric liquid Q. That
measurement and the bottom kinematic total-volume rate are checked against the
predeclared schedule; the check does not modify W or recompute the z sweep.
`flux` is converted using physical face area, not inverse grid spacing.

At z+ an actual inflow receives alpha=1 only on an active slot; other top inflow
receives alpha=0. Outflow alpha, density, and viscosity ghosts retain their
generic extrapolated values. At z−, reverse inflow receives alpha=0 and air
properties; ordinary bottom return is outflow and uses interior extrapolation.
After `advvof`, the main routine updates rho and mu and calls generic `boundp`
for each; source-aware halos are immediately reapplied so those generic fills
cannot replace phase-consistent inflow properties before momentum.

The three generic velocity fills are each followed by source overrides:

1. Initial `bounduvw`, then source override and boundary phase preparation.
2. Pre-projection `bounduvw(...,no_outflow,...)`, then source override.
3. `correc`, post-projection `bounduvw(...,is_outflow,...)`, then source override
   and the velocity/divergence audit.

The half-open source is active on VOF intervals 2 through 11, from state time
0.0002 s through 0.0012 s. With 14 solver steps, interval 12 advances the first
post-pulse state and interval 13 advances the second. Projected state U₁₂
already has the inactive interval-12 source and return, and U₁₃ has interval
13. The endpoint checks are static code-order assertions and analytic schedule
calculations only; they do not execute Fortran or prove solver flux, local
divergence, or pressure-projection behavior.

## Ledgers and proposed review gates

The candidate records requested and geometric phase volume and mass per slot,
requested and applied vector momentum, source-slot reverse outflux, off-mask
inflow/outflow, all six outward boundary phase-volume fluxes, and a liquid-mass
inventory. The inventory includes `Mbox(0)` and cumulative inward/outward liquid
flux over all faces, including source-face reverse flow. The signed residual is
`R = M_in − M_out − (M_box − M_box(0))`; per-step `net_boundary_liquid_m3` is
inward minus outward. Periodic faces are recorded on both sides and should
cancel as a pair. Momentum integration uses
the actual z-face flux in a fixed slot → j → i loop order; staggered U/V values
are averaged between the interior and ghost z planes, while W is sampled on the
z face. These exact operations are checked by the unit suite.

The following are proposed measurements for independent review, not accepted
numerical gates and not passed results:

* one-slot and four-slot requested-versus-geometric source mass by slot and in
  total, including the expected factor-four total scaling;
* source/return and all-face net volume closure, plus local maximum and L1
  discrete divergence and their integrated finite-volume closure;
* liquid inventory residual using initial inventory and every inward/outward
  phase flux;
* exactly zero requested source and return in intervals 12 and 13;
* requested/applied momentum-vector agreement in quiescent and crossflow
  fixtures.

An independent reviewer must freeze tolerances and approve the complete
protocol before a source case is launched. All Python checks are static source
order assertions and analytic calculations. No Fortran helper or boundary
runtime test has run. This package has not run the source solver, a source-slot
diagnostic, a GPU kernel, or any CFD.

The source's timestep indicator is statically inspected against upstream
`chkdt.f90`:
`Co_local = dt*max(dtix,dtiy,dtiz)`, where each directional term sums face or
four-point-averaged speed magnitudes divided by the corresponding grid spacing.
The theoretical normal-only Co is 0.0192 at the source speed; the crossflow-only
contribution is 0.2 at 50 m/s. A source-adjacent crossflow cell can combine the
components to about 0.2192 under the inspected directional formula. With
`constant_dt=T`, the driver skips `chkdt_tw` and emits no per-step Co or
interface telemetry. Formula checks and theoretical values are not runtime
measurements or an accepted timestep gate.

## Rebuild and static checks

The patch applies to the source commit in `source-pin.txt`; the candidate build
starts from the separately verified base image and checks its immutable local
image ID. It has a two-CPU cap, runs the static/analytic suite, compiles the
patched executable, and checks for an `sm_120` code object. It does not execute
the executable or inherit the base image's GPU-test entrypoint.

```sh
python3 containers/flutas/tests/test_source_boundary.py /tmp/flutas-pristine-5982106
containers/flutas/build-source-candidate.sh
```
