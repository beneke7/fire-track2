# Candidate6 build and host-check exact review

**Astra Max disposition: ACCEPT at retained-build, static-wiring, and host-regression scope only.** This is not a source-run or GPU-runtime approval.

The reviewer independently verified all 6 files in the latest host bundle and all 9 files in the retained build bundle, their inventory hashes, 21 test-input entries, 5 build inputs, and the 15 frozen case files. The image patch reconstructs the three modified upstream source files from commit 598210616bebd51f7d51f61455f196e6f3479916 plus the pinned candidate6 patch. The image and retained executable match SHA-256 0c3563ed2bbd8a29586d1cdd9f61b8e53087854950e440812492154839b2bb58; cuobjdump reports an sm_120 code object.

The host bundle records 19 source-boundary and 16 observability tests with no skips, eight helper modes, five input-rejection cases, the expected flux-abort check, seven dzf(0:) lower-bound calls, and the static source-hook-order check. The exact commands and outputs are in [the host evidence bundle](../../containers/flutas/candidate6/evidence/source-helper-check-20260928T094855Z-4099677/).

The final retained build reused the compiled layer from attempt full-source-build-20260928T093015Z-4091383; it was not a fresh compilation. Historical test-input bytes are not fully retained for every failed attempt. No GPU runtime, source case, or physical time step was executed.

The review does not close H6 candidate provenance, H5 raw evidence/auditing, source input binding, numerical limits, H7 termination/lock enforcement, or the combined launch review. The current image is an inspected local Docker image; an immutable OCI layout and candidate-build receipt are still required.
