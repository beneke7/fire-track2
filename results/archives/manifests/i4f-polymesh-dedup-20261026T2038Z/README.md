# I4F static polyMesh deduplication recovery record

This packet publishes the recovery map for the 26 October 2026 deduplication of exact-hash static `constant/polyMesh` payloads. It does not archive or alter solver fields, dictionaries, or source inputs.

The run planned 2,251 duplicate files. The journal records 2,230 unlinks; one file was restored for the private restore smoke, leaving 2,229 persistent unlinks at that handoff. The portable public helper was then exercised on a second distinct planned path; that file is also restored. Thus the current state retains 2 smoke-restored copies and 2,228 persistently unlinked duplicates. Twenty-one candidates were retained because their containing directories denied unlink permission. `final-handoff.json` records the measured free-space delta at the original batch handoff; `public-helper-restore-smoke.json` records the later restore validation.

`dedup-plan.json` maps every selected duplicate path to a retained byte-identical canonical path and records SHA-256, size, allocated bytes, mode, owner, group, atime, mtime, device, and original inode/ctime provenance. `dedup-journal.jsonl` records each verified unlink. The global target set has no overlap with canonical paths. The cross-check scanned 127 existing archive JSON documents and found no exact path references to any planned target or canonical.

Run the current portable restore helper from the repository root:

```sh
python3 results/archives/manifests/i4f-polymesh-dedup-20261026T2038Z/restore_duplicate_polymesh.py <repository-relative-duplicate-path>
```

The helper rejects symlink path components, copies from the retained canonical file into an independent temporary file, verifies SHA-256/size and metadata, then installs with an atomic no-clobber operation. The temporary-file link is removed after installation; the restored file never shares an inode with its canonical source. Existing destinations and install-time races are refused. It restores uid/gid/mode/atime/mtime; `ctime` is recorded but necessarily changes when a file is recreated.

`restore_duplicate_polymesh-executed-v1.py` is the exact helper recorded at the original cleanup. `restore_duplicate_polymesh-pre-safetyfix.py` is the public helper version used for the real-path smoke before its overwrite/symlink review. The current `restore_duplicate_polymesh.py` adds those safety fixes. `restore-helper-safety-smoke.json` records synthetic tests for a normal restore, existing target, symlink target, and a target created at install time. `manifest.json` hashes each packet file except itself.
