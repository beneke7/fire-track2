# E1 wall assumption — primary disposition, 2026-09-25 12:07 UTC

**Disposition: adopt for static preparation only.** The primary amends the
prospective wall requirement in the E1 gate from a trace of Figure 3 to the
explicitly assumed analytic wall recorded in the gate and preparation note.
The user authorized clearly labelled provisional inputs on 2026-09-24; that
authorization supports this narrow preparation decision.

The adopted surface is
`y=A*(1-exp(-((x/Lx)^2+(z/Lz)^2)))`, with `A=0.080 m` and
`Lx=Lz=0.800 m`, represented by the declared bilinear node grid. The function
and all three parameters are project assumptions, not measurements, a Figure 3
trace, or recovered aircraft geometry. Flat-wall and declared geometry
sensitivities remain. Figure 3 lacks profile coordinates and a scale transform,
so it cannot support a defensible quantitative wall trace.

This disposition replaces only the wall baseline for static preparation. It
does not accept the E1 package, authorize meshing or characterization, resolve
D-NUT-BC/contact-angle choices, authorize E1 execution, or permit Figure 13
comparison. Those remain subject to exact independent review and separate
prospective decisions. The prior accepted gate review applies to its original
exact hash only; Astra must review the amended gate and corrected package.

Updated artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md` | `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` |
| `experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md` | `ac47a5fabb9431b26b285647fd26f7715f318a58959d3fe9c1551e622e6618f4` |

No mesh utility, solver, characterization, or GPU run was launched.
