#include <cuda_runtime.h>
#include <mpi.h>

#include <cstdio>

int main(int argc, char **argv) {
  int init_status = MPI_Init(&argc, &argv);
  if (init_status != MPI_SUCCESS) {
    std::fprintf(stderr, "MPI_Init failed: %d\n", init_status);
    return 1;
  }

  int rank = 0;
  int size = 0;
  MPI_Comm_rank(MPI_COMM_WORLD, &rank);
  MPI_Comm_size(MPI_COMM_WORLD, &size);
  if (size != 2) {
    std::fprintf(stderr, "expected 2 MPI ranks, got %d\n", size);
    MPI_Abort(MPI_COMM_WORLD, 2);
  }

  cudaError_t cuda_status = cudaSetDevice(0);
  int *device_send = nullptr;
  int *device_recv = nullptr;
  if (cuda_status == cudaSuccess) {
    cuda_status = cudaMalloc(&device_send, sizeof(int));
  }
  if (cuda_status == cudaSuccess) {
    cuda_status = cudaMalloc(&device_recv, sizeof(int));
  }
  int host_send = rank + 1;
  if (cuda_status == cudaSuccess) {
    cuda_status = cudaMemcpy(device_send, &host_send, sizeof(int),
                             cudaMemcpyHostToDevice);
  }
  if (cuda_status != cudaSuccess) {
    std::fprintf(stderr, "rank %d CUDA setup failed: %s\n", rank,
                 cudaGetErrorString(cuda_status));
    MPI_Abort(MPI_COMM_WORLD, 3);
  }

  int mpi_status = MPI_Allreduce(device_send, device_recv, 1, MPI_INT, MPI_SUM,
                                 MPI_COMM_WORLD);
  int host_recv = 0;
  if (mpi_status == MPI_SUCCESS) {
    cuda_status = cudaMemcpy(&host_recv, device_recv, sizeof(int),
                             cudaMemcpyDeviceToHost);
  }
  if (mpi_status != MPI_SUCCESS || cuda_status != cudaSuccess || host_recv != 3) {
    std::fprintf(stderr,
                 "rank %d GPU-buffer allreduce failed: mpi=%d cuda=%s value=%d\n",
                 rank, mpi_status, cudaGetErrorString(cuda_status), host_recv);
    MPI_Abort(MPI_COMM_WORLD, 4);
  }

  std::printf("rank %d GPU-buffer MPI_Allreduce result=%d\n", rank, host_recv);
  cudaFree(device_recv);
  cudaFree(device_send);
  MPI_Finalize();
  return 0;
}
