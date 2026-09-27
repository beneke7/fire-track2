ARG BASE_IMAGE=track2/flutas-nvhpc:26.9
FROM ${BASE_IMAGE}

ARG FLUTAS_COMMIT=598210616bebd51f7d51f61455f196e6f3479916

COPY source-boundary.patch /tmp/source-boundary.patch
COPY tests /opt/flutas-source-protocol/tests
COPY cases/source_boundary /opt/flutas-source-protocol/cases/source_boundary

RUN set -eux; \
    test "$(git -C /opt/FluTAS rev-parse HEAD)" = "${FLUTAS_COMMIT}"; \
    git -C /opt/FluTAS apply --check /tmp/source-boundary.patch; \
    git -C /opt/FluTAS apply /tmp/source-boundary.patch; \
    /opt/flutas-source-protocol/tests/run_source_validator_tests.sh \
      /opt/FluTAS /opt/flutas-source-protocol/cases/source_boundary; \
    make -C /opt/FluTAS/src clean; \
    make -C /opt/FluTAS/src -j2 ARCH=generic-gpu APP=two_phase_inc_isot; \
    cuobjdump --list-elf /opt/FluTAS/src/flutas.two_phase_inc_isot | grep -F 'sm_120.cubin'; \
    test -x /opt/FluTAS/src/flutas.two_phase_inc_isot

# This candidate supports patch/build review only. It never starts the solver,
# executes the inherited GPU smoke suite, or attaches a GPU runtime.
ENTRYPOINT ["/bin/true"]
