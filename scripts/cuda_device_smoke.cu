#include <cuda_runtime.h>

#include <cstdio>
#include <vector>

__global__ void affine_transform(float *output, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    output[index] = 3.0f * static_cast<float>(index) + 1.0f;
  }
}

int main() {
  constexpr int count = 1024;
  float *device_output = nullptr;
  cudaError_t status = cudaMalloc(&device_output, count * sizeof(float));
  if (status != cudaSuccess) {
    std::fprintf(stderr, "cudaMalloc failed: %s\n", cudaGetErrorString(status));
    return 1;
  }

  affine_transform<<<4, 256>>>(device_output, count);
  status = cudaGetLastError();
  if (status == cudaSuccess) {
    status = cudaDeviceSynchronize();
  }
  if (status != cudaSuccess) {
    std::fprintf(stderr, "CUDA kernel failed: %s\n", cudaGetErrorString(status));
    cudaFree(device_output);
    return 1;
  }

  std::vector<float> host_output(count);
  status = cudaMemcpy(host_output.data(), device_output, count * sizeof(float),
                      cudaMemcpyDeviceToHost);
  cudaFree(device_output);
  if (status != cudaSuccess) {
    std::fprintf(stderr, "cudaMemcpy failed: %s\n", cudaGetErrorString(status));
    return 1;
  }

  for (int index = 0; index < count; ++index) {
    const float expected = 3.0f * static_cast<float>(index) + 1.0f;
    if (host_output[index] != expected) {
      std::fprintf(stderr, "Incorrect result at index %d\n", index);
      return 1;
    }
  }

  int device = 0;
  cudaDeviceProp properties{};
  status = cudaGetDevice(&device);
  if (status == cudaSuccess) {
    status = cudaGetDeviceProperties(&properties, device);
  }
  if (status != cudaSuccess) {
    std::fprintf(stderr, "CUDA device query failed: %s\n", cudaGetErrorString(status));
    return 1;
  }

  std::printf("CUDA kernel smoke passed: %s, compute capability %d.%d, %d values checked\n",
              properties.name, properties.major, properties.minor, count);
  return 0;
}
