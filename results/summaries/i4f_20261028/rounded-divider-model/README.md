# Rounded divider geometry candidate

For the physically shortened rise candidate, see [the compact assembly](../compact-rounded-divider-model/README.md). This folder preserves the prior 1.20 m rise.

This is a provisional, inspectable CAD candidate for the current two-tank, four-outlet I4F apparatus. It is **not** a CFD result or a validated hardware reconstruction.

## Model files

- `full_assembly.step`: complete assembly with separate envelope and 16 divider solids; STEP lengths are declared in millimetres (the apparatus mouth is at x=4800 mm).
- `full_assembly.stl`: complete envelope and divider assembly; STL coordinates are unitless SI metres. The opaque envelope hides interior plates in many viewers.
- `all_16_dividers.stl`: all 16 closed divider solids by themselves.
- `single_outlet_4_dividers.stl` and `single_outlet_dividers.step`: four plates for one outlet, suitable for inspecting the channel arrangement.
- `divider_solids.step`: the 16 finite divider solids, separate from the fluid envelope.

## Geometry choices

The user confirmed four vertical dividers per outlet and reported 10–20 mm thickness. The model uses a 15 mm nominal thickness, with each body station constructed to a 15 mm local normal section. The rounded leading edge is represented by a tangent semicircle with radius 7.5 mm, selected as half the nominal thickness. Its exact radius and manufacture are not measured. The current provisional divider start is x=4.216667 m; the transition/mouth length is 1.0 m, and the mouth is 1.0 m wide by 0.15 m high. Four plates form five nominal equal clear passages; the exit gap is 188 mm and the plate footprint blocks 6% of the nominal gross mouth area.

The candidate keeps the historical flush-at-inlet pipe/transition join and no post-rise straight. Divider positions follow the existing aligned ruled transition model. These are closed solids, not mid-surfaces. The earlier CFD mesh remains unchanged and used zero-thickness baffle faces; it does not inherit this finite blockage or rounded nose.

## Checks and limits

STEP round-trip reports 26 valid solids in the full assembly (10 envelope solids and 16 divider solids), all 16 divider solids valid, and a declared millimetre unit with the full x-bound ending at 4800 mm. STL closedness checks found 16 watertight divider components and four watertight single-outlet components, with zero boundary and non-manifold edges. No fluid mesh was generated. A CFD mesh must be regenerated with solids excluded from fluid and locally refined around the 15 mm nose (about 2 mm cells are a reasonable initial geometry-resolution target, not a validated requirement).

See `candidate_result.json` and the experiment record for provenance and hashes.
