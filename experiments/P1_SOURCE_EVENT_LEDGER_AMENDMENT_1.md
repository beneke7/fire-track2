# P1 protocol amendment 1: alphaPhi_ time-centering

Review decisions are recorded in the execution JSON and copied into each run
manifest. The runner requires independent protocol and code approval before
execution. The earlier P1 run remains a failure under protocol revision 1.

## Change

Revision 1 compared the conservative `alphaPhi_` integral with a right-endpoint
sum of the boundary velocity table. OpenFOAM v2512 advances `runTime` to `t_n`
before solving the time step, and the `interIsoFoam` alpha equation calls
`advector.advect()` before writing that time. The `isoAdvection` implementation
constructs the conservative alpha flux from the time-integrated face transport
for the completed step. In the retained tables, the `alphaPhi_` row at `t_n`
matches the input boundary value at `t_(n-1)` through the shutoff ramp, while
`phi` matches the current right-endpoint input value. The observed lag is one
fixed 0.1 ms step.

For the unchanged source profile, four provisional 0.15 m² slots, density of
1,000 kg/m³, `deltaT = 1e-4 s`, and 1,200 steps, direct quadrature gives:

| Quantity | Sampling convention | Expected dose |
| --- | --- | ---: |
| `alphaPhi_` completed-step flux | left endpoint `U(t_(n-1))`, for intervals `[t_(n-1), t_n]` | 57.636 kg/slot; 230.544 kg total |
| `phi` instantaneous cross-check | right endpoint `U(t_n)` | 57.564 kg/slot; 230.256 kg total |
| Continuous analytic input | exact piecewise-linear integral | 57.600 kg/slot; 230.400 kg total |

The `alphaPhi_` expected dose is therefore changed to the left-endpoint sum.
The 0.1% tolerance is unchanged, and the measured `alphaPhi_` dose must also
remain within 0.1% of the continuous analytic dose. `phi` remains an explicit
right-endpoint diagnostic; it is not substituted for the conservative liquid
flux in the mass ledger. The time-step, waveform, mesh, Courant limits, box
ledger limit, resource cap and all other P1 settings remain unchanged.

## Historical disposition and confirmation

Run `restas-source-ledger-20260925T003321.108356Z-1927f2fd` stays **not passed**
under revision 1: its 230.544 kg `alphaPhi_` result is 0.125078% above the
frozen 230.256 kg target. The amended target must not be applied retroactively
to relabel that run. Its original run bundle and report are retained unchanged.

Only a new run made after approval can test revision 2. It must use the same
waveform and numerical inputs, record all per-step `phi`, `alphaPhi_`, and
inventory rows, capture the raw `interIsoFoam` exit separately from the whole
case-command status, and satisfy both the left-endpoint `alphaPhi_` target and
continuous analytic dose at the unchanged 0.1% tolerance. The mass-ledger,
Courant, completeness, mesh, wall-time, and clean-workflow gates also remain in
force. A P1 pass would still be a provisional source/ledger diagnostic only.

## Review basis

- `scientific_contract` independently confirmed the left-step target and
  recommended preserving the historical revision-1 failure.
- `alpha_phi_time_review` independently integrated the profile and raw tables;
  its calculations were 57.636 kg/slot for left sampling, 57.564 kg/slot for
  right sampling, and 57.600 kg/slot continuously.
- The pinned OpenFOAM v2512 API source describes `interIsoFoam` advancing time
  before the alpha equation and calling `advector.advect()` for the step. The
  `isoAdvection` source forms the conservative phase flux from its integrated
  face transport. See the [v2512 interIsoFoam loop](https://api.openfoam.com/2512/interIsoFoam_8C_source.html),
  [alpha equation](https://api.openfoam.com/2512/interIsoFoam_2alphaEqn_8H_source.html),
  and [isoAdvection source](https://api.openfoam.com/2512/isoAdvection_8C_source.html).
  The one-step boundary-value mapping is also directly observable in the raw
  slot tables around 0.0795–0.0805 s.
