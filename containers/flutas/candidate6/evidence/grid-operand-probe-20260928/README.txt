CPU-only source probe; no candidate executable or GPU was used.

The driver calls the pinned candidate5 initgrid.f90 with the dry_four vertical
inputs (nz=40, gr=0, lz=1 m, one halo). Compile with NVHPC builder image
sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8,
mounting this directory read-only at /probe and
containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/
reference/pinned-source read-only at /source:

nvfortran -O0 /probe/mod_types.f90 /probe/mod_param.f90 /source/initgrid.f90 /probe/driver.f90 -o /tmp/grid-operand-probe
/tmp/grid-operand-probe

The output contains indices 0..41 followed by dzf, dzc, reciprocal dzf, and
reciprocal dzc in ES24.16E3 format. The checker reproduces these binary64
values exactly.
