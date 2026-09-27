# Candidate5 offline OCI layout feasibility probe

**Primary-generated engineering evidence; not an independent review, candidate
acceptance, or source-run approval.** This probe was made to check the selected
offline image-identity route against the actual candidate5 successor image.

## Exact image and export

Docker client/server were both `29.1.3`. The local candidate image was
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`,
with no `RepoDigests`. The export command, run with one CPU through the local
launcher and a 600-second ceiling, was:

```sh
.venv/bin/python scripts/run_local.py --threads 1 --timeout 600 -- \
  docker save --output /tmp/fire-track2-candidate5-oci-proof-73b7.tar \
  sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43
```

The resulting 24 GiB temporary archive had SHA-256
`6d82a9e2b075cfa2ba86f01098f14977d3a0039ffd9f70ad9e59c48ece7576de`.
Its root contains `oci-layout`, `index.json` and `blobs/sha256/`. The layout
version is `1.0.0`; the index selects one OCI image manifest with raw digest
`sha256:5d3d0117271bf8e7e987d316a863d4f3397a77049eb9cd1f3122c44d03b7bda3`
and length 3,907 bytes. That digest is the selected OCI manifest identity; the
index and outer tar have different identities.

## Verification

The primary streamed every referenced object from the saved layout. The raw
manifest digest and size matched its index descriptor. The config blob digest
was exactly the Docker image ID above and its size matched the config
descriptor. The config's ordered `rootfs.diff_ids` matched the `RootFS.Layers`
reported by `docker image inspect`.

All 24 layer descriptors use the uncompressed media type
`application/vnd.oci.image.layer.v1.tar`. For every ordered layer, the raw
blob's SHA-256 and byte count matched its descriptor, and the same digest
matched the corresponding config `rootfs.diff_ids` entry. That equality holds
here because the layer bytes are uncompressed tar streams; it must not be
assumed for compressed layer media types. The complete per-layer descriptors
and checks are retained in
[`verification.json`](../../results/runs/candidate5-oci-layout-proof-20260925T1345Z/verification.json),
SHA-256 `25f146f4a47d2720e74531df97c10f5e4d736b951ff59e0038f0100e326eca92`.

The temporary image-layout archive was not retained after recording its digest
and descriptor report. This probe establishes that this Docker installation can
export the exact local candidate to a usable offline OCI layout archive and
that its config/layer identities reconcile. It does not establish deterministic
re-export, receipt completeness, build reproducibility, corruption handling,
launcher verification, or source-run eligibility. The released build workflow
must preserve the actual exported layout/manifest bytes in immutable evidence,
record the Docker config ID separately, and independently verify every
reference before launch. The successor still lacks `candidate-build.json`, and
the source-release contract remains under revision.

## Primary cleanup erratum — 2026-09-25 14:18 UTC

The preceding retention sentence described the intended cleanup but was stale:
the 24 GiB tar remained at `/tmp/fire-track2-candidate5-oci-proof-73b7.tar`
after this report was written. After Warden 12 confirmed that the archived
descriptor report was sufficient for the feasibility question and no reviewer
needed the temporary tar, the primary removed it at 14:18 UTC to recover local
disk. Its previously recorded SHA-256 remains
`6d82a9e2b075cfa2ba86f01098f14977d3a0039ffd9f70ad9e59c48ece7576de`; the
verified `results/runs/candidate5-oci-layout-proof-20260925T1345Z/` report is
retained. Three extracted `/tmp/candidate5-*` source files were removed with
it. No immutable build receipt or launch acceptance was created.
