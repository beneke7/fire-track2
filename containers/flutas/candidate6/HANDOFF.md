# Candidate6 H4 two-halo follow-up handoff

Candidate6 remains an isolated successor to candidate5 for the `dzf` lower-bound
defect. The pinned FluTAS commit is `598210616bebd51f7d51f61455f196e6f3479916`.
Candidate5 files and its live exact review were left untouched. The source patch
was not changed in this follow-up; its SHA-256 remains
`3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee`, with a
1,388-line new-source hunk.

The exact-review REVISE identified a two-halo caller mapping case not covered by
the original one-halo driver. The permanent two-halo driver now declares
`dzf(-1:nz+2)` with nonconstant values and calls all three helpers
(boundary-flux accumulation, inventory, velocity audit) with `dzf(0:)`. This
section makes physical caller index zero become helper dummy index zero. Its
negative-control mode passes the whole array; then helper dummy `k` reads
caller index `k-1`. Independent Python calculations check separate inward and
outward geometric face areas, boundary flux volumes, both inventories,
divergence and legacy Courant. The existing one-halo test remains and still
checks the production caller's `dzf(0:nz+1)` mapping.

## Verification

The one-halo and two-halo tests both exited 0 in the pinned NVHPC 26.9 image,
with bounds checking, at 1 CPU / 4 GiB, no network and no GPU. The compile flags
were `nvfortran -O0 -g -Mbounds -Mextend`; generated helper modules, drivers,
executables and raw CSV outputs are retained. Exact command, compiler output,
input hashes and per-file evidence hashes are in
`evidence/dzf-two-halo-20260925T143734Z/`.

For the explicit physical slice, the independent comparisons produced x-low
area `42.6`, y-low area `28.4`, initial inventory `37032 kg`, updated inventory
`42144 kg`, y-low inward flux volume `4.814 m³`, maximum absolute divergence
`1.0019166666666666 s^-1`, global legacy Courant `0.12532708333333334`, and
divergence integral `79.5266 m³/s`. All face area, boundary volume, inventory,
velocity audit, divergence and Courant values matched their independent
expectations.

The deliberately shifted whole-array control also matched its independently
computed expectations, and differed from the explicit-slice result: x-low and
y-low areas were `22.8` and `15.2`; initial/updated inventory was `20064` /
`22800 kg`; y-low inward volume was `2.7520000000000002 m³`; maximum absolute
divergence was `2.751916666666667 s^-1`; and legacy Courant was
`0.3440770833333333`. This demonstrates that the nonconstant fixture detects
the one-index shift.

`evidence/dzf-two-halo-20260925T143646Z/` preserves the first attempt, which
exited 1 because the initial test oracle expected both inward and outward area
on each individual face. The oracle was corrected to use the helper's low-face
inward and high-face outward signs; the full one-halo and two-halo run then
passed in the separate evidence directory above. Both attempts have file
manifests. The passing two-halo `inputs.sha256` binds the patch, pin, both tests
and drivers.

The velocity audit retains its inherited `wx/dzf(k)` and `wz/dzf(k)` division
arithmetic. The separate candidate5 v1.2 timestep restriction retains its
captured `dzfi(k)` / `dzci(k)` multiplications and source order. The test checks
those expressions and independent expected values as distinct calculations;
it does not claim they are identical or execute the full timestep routine.

The earlier native-build record at
`evidence/native-build-20260925T141014Z/` remains available as historical CPU
evidence. No candidate6 executable or OCI image is retained, and this follow-up
did not rebuild one. No solver, source case or GPU run was performed.

## Handoff status and limits

Candidate6 now contains the permanent compiled one-halo and explicit two-halo
caller cases, including the shifted-index negative control requested by the
exact review. The source patch and production arithmetic were not changed. This
artifact is ready for the next exact independent review; it does not itself
close H4 or accept the broader source contract, B1/B2, or any scientific
validation gate. Primary scheduling remains required before source execution.
