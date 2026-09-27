FROM nvidia/cuda:12.8.0-devel-ubuntu24.04@sha256:9a8fffc32a955361aa66d754e7a0cda2513052eaf5aaf8f3ba69b80578d1c6a9

ARG FLUTAS_COMMIT=598210616bebd51f7d51f61455f196e6f3479916
ARG NVHPC_ARCHIVE_URL=https://developer.download.nvidia.com/hpc-sdk/26.9/nvhpc_2026_269_Linux_x86_64_cuda_13.3.tar.gz
ARG NVHPC_ARCHIVE_SHA256=e1bbf2ccdb112a3773d2cc141f09fb1d087562e266ec7ec7adb30a0519d45877

ENV NVCOMPILERS=/opt/nvidia/hpc_sdk \
    NVARCH=Linux_x86_64 \
    NVHPCSDK_HOME=/opt/nvidia/hpc_sdk/Linux_x86_64/26.9 \
    PATH=/opt/nvidia/hpc_sdk/Linux_x86_64/26.9/comm_libs/mpi/bin:/opt/nvidia/hpc_sdk/Linux_x86_64/26.9/compilers/bin:/usr/local/cuda/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl=8.5.0-2ubuntu10.15 \
      gfortran=4:13.2.0-7ubuntu1 \
      git=1:2.43.0-1ubuntu7.3 \
      libfftw3-dev=3.3.10-1ubuntu3 \
      libnl-route-3-200=3.7.0-0.3build1.1 \
      python3-numpy=1:1.26.4+ds-6ubuntu1 \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    curl --fail --location --retry 2 --output /tmp/nvhpc.tar.gz "${NVHPC_ARCHIVE_URL}"; \
    echo "${NVHPC_ARCHIVE_SHA256}  /tmp/nvhpc.tar.gz" | sha256sum --check --status; \
    tar -xpzf /tmp/nvhpc.tar.gz -C /tmp; \
    NVHPC_SILENT=true \
      NVHPC_INSTALL_DIR=/opt/nvidia/hpc_sdk \
      NVHPC_INSTALL_TYPE=single \
      NVHPC_DEFAULT_CUDA=13.3 \
      /tmp/nvhpc_2026_269_Linux_x86_64_cuda_13.3/install; \
    rm -rf /tmp/nvhpc.tar.gz /tmp/nvhpc_2026_269_Linux_x86_64_cuda_13.3

COPY target.generic-gpu.patch /tmp/target.generic-gpu.patch
COPY openacc_cc120_smoke.f90 /opt/flutas-gpu-smoke/openacc_cc120_smoke.f90
COPY mpi_cuda_buffer_smoke.cpp /opt/flutas-gpu-smoke/mpi_cuda_buffer_smoke.cpp
COPY run-gpu-tests.sh /usr/local/bin/flutas-gpu-tests

RUN set -eux; \
    git clone --filter=blob:none https://github.com/Multiphysics-Flow-Solvers/FluTAS.git /opt/FluTAS; \
    git -C /opt/FluTAS checkout --detach "${FLUTAS_COMMIT}"; \
    test "$(git -C /opt/FluTAS rev-parse HEAD)" = "${FLUTAS_COMMIT}"; \
    git -C /opt/FluTAS apply --check /tmp/target.generic-gpu.patch; \
    git -C /opt/FluTAS apply /tmp/target.generic-gpu.patch; \
    make -C /opt/FluTAS/src -j2 ARCH=generic-gpu APP=two_phase_inc_isot

RUN set -eux; \
    nvfortran -acc=gpu -gpu=cc120,cuda13.3 -Minfo=accel \
      /opt/flutas-gpu-smoke/openacc_cc120_smoke.f90 \
      -o /opt/flutas-gpu-smoke/openacc_cc120_smoke; \
    mpic++ -cuda -gpu=cc120,cuda13.3 \
      -o /opt/flutas-gpu-smoke/mpi_cuda_buffer_smoke \
      /opt/flutas-gpu-smoke/mpi_cuda_buffer_smoke.cpp; \
    cuobjdump --list-elf /opt/FluTAS/src/flutas.two_phase_inc_isot \
      | grep -F 'sm_120.cubin'; \
    chmod +x /usr/local/bin/flutas-gpu-tests

ENTRYPOINT ["/usr/local/bin/flutas-gpu-tests"]
