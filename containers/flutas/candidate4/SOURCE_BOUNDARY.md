# Pinned FluTAS source/return boundary candidate4

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
| Slot geometry | Four 0.15 m × 1.0 m slots; 0.05 m edge gaps in x and y; short axis x |
| Slot masks, one-based i/j | (74..79,2..41), (82..87,2..41), (74..79,44..83), (82..87,44..83) |
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
Each mask is 6 x-cells by 40 y-cells; the centered 2-by-2 arrangement makes the
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
13. The code names these as three distinct records: source-flux/off-mask/rate
rows describe interval k, from state k to completed state k+1; boundary and
mass rows are indexed by that completed state k+1; the velocity row for state
k+1 records the profile installed on Uₖ₊₁ for the next interval. Initial state
U₀ is paired with profile interval 0. These indices must not be joined as if
they described the same instant.

## Runtime telemetry and CSV schema

For each corrected velocity state, `global_chkdt_advective_courant_max` is
`dt * max_cell(max(dtix,dtiy,dtiz))`, using the same three directional
staggered-face speed estimates as upstream `chkdt_tw`. For example,
`dtix = |u(i,j,k)|/dx + |v(i,j,k)+v(i,j−1,k)+v(i+1,j,k)+v(i+1,j−1,k)|/(4dy)
+ |w(i,j,k)+w(i,j,k−1)+w(i+1,j,k)+w(i+1,j,k−1)|/(4dz)`; the y and z terms
follow the upstream stencil. The global count is `nx*ny*nz`. The interface
set is defined without a fitted alpha cutoff as interior cells with strictly
`0 < alpha < 1`. `interface_cell_count` gives the number of those cells;
`interface_courant_defined=1` means the maximum is measured over that set.
When the set is empty, the row records count 0, defined 0, and numeric maximum
0; the maximum is undefined in that case and must not be treated as a measured
zero.

The velocity audit keeps three divergence quantities separate:
`max_abs_divergence_s = max_i |div_i|`,
`volume_integrated_abs_divergence_m3_s = sum_i |div_i| V_i`, and the signed
`integrated_divergence_m3_s = sum_i div_i V_i`. `closure_m3_s` remains the
signed integral minus the outward-positive boundary rate. That finite-volume
telescoping identity is a bookkeeping check; it is not a continuity score.
No numerical acceptance limit is declared here. The fixed-step fixtures set
`constant_dt=T`, so they bypass upstream `chkdt_tw`'s complete combined
advective, viscous, capillary, and gravity timestep restriction. The logged
global and interface values are advective diagnostics only. The applicable
full restriction remains relevant to any future run; no candidate4 source
case has been launched or accepted on the basis of a Courant value.

The CSVs are time series with these expected counts for a completed 14-step
fixture: source flux has 14 rows for one slot, 56 for four slots, and no rows
for a dry fixture; interval indices are 0–13. Global off-mask totals live in
one `source-offmask.csv` row per interval (14 rows even when dry), never in
each slot row. `rate-check.csv` has one row per interval, with measured,
expected, and signed residual rates; it is flushed before either geometric
source or return-rate abort. Boundary, mass, and velocity ledgers each have 15
rows indexed by state 0–14. Dry source rows are absent by design, while its
boundary, mass, velocity, off-mask, and rate histories remain complete.

The helper test writes synthetic active-one, active-four, and dry ledgers and
checks fixed independent nonzero expectations for per-slot mass/momentum,
off-mask flux, all-face boundary values, mass inventory, Courant, and L1 versus
maximum divergence. It also intentionally mismatches a source flux and checks
that the rate record survives the expected abort. This is a CSV/helper test;
it is not a solver runtime or physics result.

## Ledgers and proposed review gates

The candidate records requested and geometric phase volume and mass per slot,
requested and applied vector momentum, source-slot reverse outflux, interval
off-mask inflow/outflow, all six outward boundary phase-volume fluxes, and a
liquid-mass inventory. The inventory includes `Mbox(0)` and cumulative
inward/outward liquid flux over all faces, including source-face reverse flow.
The signed residual is `R = M_in − M_out − (M_box − M_box(0))`; per-step
`net_boundary_liquid_m3` is inward minus outward. Periodic faces are recorded
on both sides and should cancel as a pair. Momentum integration uses the
actual z-face flux in a fixed slot → j → i loop order; staggered U/V values
are averaged between the interior and ghost z planes, while W is sampled on
the z face.

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

An independent reviewer must approve the complete protocol before a source
case is launched. The host-only Fortran harness runs the source reader and
validator, the prescribed return helper, actual `boundp`/`update_vof` refresh,
actual `update_property` followed by generic and phase-aware `rho`/`mu` halo
updates, ledger writers with synthetic fields, and the CPU momentum stencil at
periodic edges. It retains the halo-width-2 stress check and adds production
halo width one. It also checks rejection of an unsupported slot count and an
active interval in a dry fixture. These helper-level checks do not run the
FluTAS driver or establish a dry/crossflow solver pass, solver flux,
projection, stability, or source physics. No CSV analyzer, numerical gate
limits, or source CFD protocol is frozen. Candidate4 has no source-solver,
GPU-kernel, or CFD result.

The upstream timestep indicator in `chkdt.f90` combines advective, viscous,
capillary, and gravity restrictions with its safety factors. Candidate4 emits
the advective maximum from each velocity state, globally and on mixed-alpha
cells. Since `constant_dt=T` skips `chkdt_tw`, these telemetry values do not
show that the selected fixed step meets the complete stability restriction.

## Rebuild and static checks

The patch applies to the source commit in `source-pin.txt`; the candidate build
starts from the separately verified base image and checks its immutable local
image ID. It has a two-CPU cap, runs the static/analytic suite and host-only
Fortran harness, compiles the patched executable, and checks for an `sm_120`
code object. The unique build script hashes the source patch, test files,
Dockerfile, pin, input manifest, repository revision and dirty-state snapshot
into a unique evidence directory and records the expanded build command and
unique candidate tag. The proposal copy under `evidence/` is
excluded from the Docker build context and input hashes. The candidate does not
execute the executable or inherit the base image's GPU-test entrypoint.

Candidate3 review and patch provenance are copied under
[`evidence/input/`](evidence/input/). Candidate4 build evidence, if generated,
is unique under `evidence/runs/`; it does not inherit candidate3's image
identity or validation disposition.

```sh
containers/flutas/candidate4/build.sh
```
