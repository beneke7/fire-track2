# Immediate parent solver source for first-step energy baseline

This packet publishes the exact v8 solver-source overlay used for the uninstrumented first-step baseline executable. Its SHA256 is 12d8ed3e808deffa56a8d21e8e23227af65c27c76e57122a48986e732089da3a. The baseline container was i4f-firststep-energy-baseline-12d8-predictor-no-20261026t205819z, ID f462b86a1d657c26a6215fdd5f773e78aacccc8f91667ff4337b342615346fb7, started 2026-10-26T20:58:19.8784497Z, and exited 0 after a complete native checkpoint at 1.2e-05 s. This was a one-step energy diagnostic, not physical validation.

## Rebuild inputs

The exact source overlay is under build/source/v8-restart-cold. It has 90 manifest entries including lnInclude symlinks and the custom twoPhaseMixtureThermo and VoFphaseCompressibleTurbulenceModels source/Make directories. The verbatim original manifest is provenance/parent-source-tree-sha256.json, SHA256 31fbd531763fcfa6c8de5f01560598d643da6e960adc62dbf0c16e4ce43b3572. All entries were verified against the parent tree and input freeze.

The recorded builder is build_solver.sh, SHA256 35b7171d5d7d639bf1c0c17cd84a99baf5c31021ecfc52dbb7ca9af9d3a4829e. Its successful attempt log is provenance/parent-build-solver-attempt-02.log. The pinned environment is opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319, image ID sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b, linux/amd64.

To repeat the recorded command in a fresh work directory mounted at /pair, place this packet's build/source/v8-restart-cold at /pair/build/source/v8-restart-cold, put build_solver.sh at /pair/scripts/build_solver.sh, create /pair/bin, and run bash /pair/scripts/build_solver.sh inside the pinned image. The script sources OpenFOAM v2512 before strict shell flags, recreates the two custom lnInclude directories, cleans, and runs wmake.

The successful log links libtwoPhaseMixtureThermo and libVoFphaseCompressibleTurbulenceModels from the pinned image; their resolved shared-library hashes are in provenance/source-closure.json. The v8 overlay also carries their source and Make files, but the successful attempt-02 record does not show separate compilation of those libraries. No rebuild was performed for this handoff, so bitwise repeatability is unverified.

## Lineage and distinction

The previously published 07fca source is an ancestor, not the immediate source for the 12d8 executable. The exact v8 parent source is packaged here; lineage/07fca-ancestor-differences.json lists differing files and hashes.

The first-step experiment has a separate instrumented source tree with two declared observer modifications. The baseline-12d8 arm launched the uninstrumented 12d8 binary. Its source-copy verification and launch/guardian records are preserved in provenance to make this distinction explicit. The exact binary remains in the ignored run bundles; this public packet records its hash and execution identity.
