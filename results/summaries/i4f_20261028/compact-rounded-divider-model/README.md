# Compact rounded-divider geometry candidate

This separate candidate shortens the **rise bend itself**. It does not crop away the old assembly's upstream pipe.

## Selected model

- `model/full_assembly.step`: complete provisional two-tank, four-outlet geometry with 16 finite rounded divider solids; STEP lengths are declared in millimetres.
- `model/full_assembly.stl`: binary STL of the same generated full assembly, unitless coordinates in metres, sized for GitHub viewing.
- `model/all_16_dividers.stl` and `model/one_outlet_four_dividers.stl`: divider-only inspection meshes.
- `model/before_after_full_assembly.png`: the published 1.20 m legacy Bezier rise and the compact 0.75 m circular-S candidate, rendered with the same camera and axis limits. It labels the removed 0.45 m rise length and unchanged 1.00 m transition.
- `model/compact_overview.png`, `model/compact_transition_sections.png`, and `model/rounded_nose_closeup.png`: compact geometry, join sections, and nose detail.

The compact candidate starts its rise at x=2.60 m and ends at x=3.35 m. The unchanged 1.00 m transition/mouth then ends at x=4.35 m. The two rise arcs use calculated centerline radii 0.975 m for the lower branch and 0.4515625 m for the upper branch; both exceed the 0.15 m pipe radius. The pipe keeps its 0.300 m circular bore and joins the transition flush, with no added straight.

Four vertical plates per outlet are retained at 15 mm nominal local gauge with 7.5 mm rounded noses. These values and the 0.75 m bend run are provisional. Only the count/orientation and 10–20 mm thickness range were user reported; the exact rise profile and dimensions are not measured.

## Limits

This is a CAD geometry candidate only. No CFD or mesh was generated. The existing 406,173-cell mesh belongs to the preserved 1.20 m bend layout and is not replaced by this model. The envelope represents the provisional fluid boundary, not a physical housing wall.

Machine-readable provenance and checks are in `candidate_result.json` and `experiments/i4f_compact_rounded_divider_candidate_20261028.json`. The exact generator used is preserved in the ignored run bundle and under `source/generate.py`.
