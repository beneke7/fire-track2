# Horizontal four-slot near-field VOF trial

This is a short exploratory CPU case for the hypothetical Restás-style four-slot source. Its OpenFOAM 2512 `interIsoFoam` solver runs use the locally available `opencfd/openfoam-default:2512` image on CPU; the established off-screen renderer is separately serialized through the local GPU lock. It is not E1–E6 validation, a reproduction of a built I4F/Restás device, or evidence for fire suppression or ground performance.

The coordinate frame is explicit: `+x` is horizontal and points downstream from the outlets; `y` is the horizontal cross-track direction; `+z` is upward and gravity acts in `-z`. Four separate rectangular source patches lie in the vertical plane `x=0`. Each patch is 1.0 m along `y` by 0.15 m along `z`, and each prescribed water vector is `(20, 0, 0) m/s` into the domain along `+x`. Their centers are at `y=±0.525 m` and `z=0.9, 1.1 m`, leaving 0.05 m gaps. The computational inlet patch outward normals point `−x`; the positive `x` flow represents horizontally facing source outlets. The case imposes a weak background air velocity `(0, 2, 0) m/s`, perpendicular to the liquid jets.

The project plan supplies an approximate 1 m by 0.10–0.15 m slot scale and a close 2×2 arrangement, but no local Restás source record or paper provides an outlet velocity, discharge history, or built geometry. Therefore the 20 m/s water source, 2 m/s airflow, 5% RANS inlet turbulence intensity, and chosen length scales are assumptions made for this diagnostic. They do not describe measured Restás hardware. The four rectangular slots have 0.60 m² combined area, so the imposed source is 12 m³/s (12,000 kg/s) and injects 240 kg over the 0.02 s main horizon; this large rate is a consequence of the provisional geometry and speed, not a claimed device capacity.

The box is 2.4 m × 2.55 m × 2.05 m. The 25 mm main mesh has 803,000 hexahedral cells, six cells across a 0.15 m slot height, and forty across its 1 m width. This is a useful first near-field discretization but does not resolve all interface scales and has no mesh or time-step convergence study. The 20 ms horizon covers the initial plume only. Water and air are Newtonian, with room-temperature water/air properties, surface tension 0.072 N/m, and gravity. There is no aircraft, wake, foam, tank, ground, parcel handoff, evaporation, or fire model.

The main matched comparison uses laminar, realizable k–ε, and k–ω SST cases with the same source, air, mesh, time horizon, and other solver settings. RANS cases use provisional 5% inlet turbulence intensity and 0.15 m water-source and 0.05 m air length scales. These closures are sensitivity endpoints, not selected or validated turbulence physics.

For OpenFOAM 2512, the SST setup declares `wallDist { method meshWave; }` in `system/fvSchemes`, matching the installed OpenCFD VOF tutorials. The output write interval is `min(0.01 s, endTime)` so short preflights still reconstruct a final field.

Run a small preflight, then the three matched cases with a planning allocation of ten MPI ranks (the runtime may rebalance this with other live project work), 32 GiB of container RAM, 12 Docker CPU shares for the ten ranks plus launcher headroom, and a 900 s per-case wall stop:

```bash
.venv/bin/python scripts/run_local.py --threads 2 -- .venv/bin/python cases/restas_horizontal_nearfield/run_case.py --model laminar --spacing 0.05 --end-time 0.01 --ranks 2 --memory-gib 8
.venv/bin/python scripts/run_local.py --threads 10 -- .venv/bin/python cases/restas_horizontal_nearfield/run_case.py --model laminar --spacing 0.025 --end-time 0.02 --ranks 10 --memory-gib 32
.venv/bin/python scripts/run_local.py --threads 10 -- .venv/bin/python cases/restas_horizontal_nearfield/run_case.py --model realizable-ke --spacing 0.025 --end-time 0.02 --ranks 10 --memory-gib 32
.venv/bin/python scripts/run_local.py --threads 10 -- .venv/bin/python cases/restas_horizontal_nearfield/run_case.py --model k-omega-sst --spacing 0.025 --end-time 0.02 --ranks 10 --memory-gib 32
```

Each invocation creates a new ignored run bundle under `results/runs/`, including generated case files, source/input hashes, a manifest, solver log, resource samples, and final reconstructed fields. Runs use adaptive stepping with `maxCo=0.3`, `maxAlphaCo=0.15`, and `maxDeltaT=3.75e-5 s`; the launcher stops if either Courant limit is exceeded or the 900 s wall bound is reached. The 100k-cell realizable k–ε probe recorded max `Co=0.3597` with the original `2.5e-4 s` ceiling while interface `Co` remained 0.108. A subsequent 803k-cell laminar run reached max `Co=0.3012` at 12.7 ms with a `7.5e-5 s` ceiling and was stopped before the 20 ms horizon. This step ceiling is halved and applied equally to the matched runs, keeping the predeclared global `Co` limit unchanged.

Render the final computed water volume from each main case with the established matte-blue alpha-threshold renderer, using one fixed camera and threshold:

```bash
.venv/bin/python scripts/render_restas_volume.py --run-dir results/runs/<run-id> --time 0.02 --alpha-threshold 0.65 --camera-bounds -0.05 0.75 -1.15 1.15 0.70 1.30
```

The shared renderer's legacy second caption says “Still-air,” although this case has a uniform +y crossflow. For a correctly labelled handoff image, run `cases/restas_horizontal_nearfield/annotate_crossflow_caption.py <render.png>`; it writes a separate `-crossflow.png` and record, changes only the caption band, and preserves the original renderer output.

The render is based on saved computed `alpha.water` cells. It does not turn underresolved interface fragments into validated droplets. Compare water inventory, thresholded volume, interface area and bounds, timestep/solver timing, and sampled Docker resource use. Do not use these short-box diagnostics to infer deposition, useful-strip length, suppression, or a design gain.

## Main matched results

All three completed cases use 802,944 cells, 25 mm spacing, 10 MPI ranks, a 12-CPU Docker limit, 32 GiB RAM limit, 20 ms horizon, 534 positive time records, and the same `maxDeltaT=3.75e-5 s`. The expected input over 20 ms is 0.24 m³ / 240 kg. Integrated final `alpha.water` inventory agrees to within 9 mg in these records. Docker resource values are sampled peaks; the run bundles retain every sample and exact manifests.

| Model | Run ID | Solver / total wall (s) | Peak RAM (GiB) | Max Co / interface Co | Water inventory (m³); mass error (mg) |
|---|---|---:|---:|---:|---:|
| Laminar | `restas-hnf-laminar-20260928T145501Z-4fe554` | 485.98 / 495.89 | 2.192 | 0.15607 / 0.09641 | 0.2399999972; −2.8 |
| Realizable k–ε | `restas-hnf-realizableke-20260928T151453Z-0c472f` | 403.88 / 411.20 | 2.319 | 0.13429 / 0.04271 | 0.2399999913; −8.7 |
| k–ω SST | `restas-hnf-komegasst-20260928T152510Z-2e0e11` | 403.01 / 410.34 | 2.346 | 0.12272 / 0.05723 | 0.2399999925; −7.5 |

| Model | Cells with `alpha.water ≥ 0.65`; geometric volume (m³) | Threshold-render triangles | `freeSurface.vtp` area (m²); polygons | Interface bounds x; y; z (m) |
|---|---:|---:|---:|---|
| Laminar | 14,766; 0.230718755 | 15,948 | 3.94501; 7,349 | [0, 0.40288]; [−1.03726, 1.03912]; [0.81010, 1.18610] |
| Realizable k–ε | 14,290; 0.223281249 | 15,780 | 3.88173; 7,354 | [0, 0.40518]; [−1.03513, 1.03739]; [0.81157, 1.18441] |
| k–ω SST | 14,300; 0.223437499 | 15,812 | 3.92119; 7,251 | [0, 0.40280]; [−1.03686, 1.03929]; [0.80957, 1.18629] |

The matched RANS thresholded volumes differ by 0.07%; both are about 3.2% below the laminar threshold volume. Their interface areas are about 0.6–1.6% below laminar. These are single-grid, single-step-setting numerical differences, not an uncertainty range or evidence that either closure is more physical. Each log records 1,602 `p_rgh` GAMG solves (mean 7.67, 7.57, and 7.52 iterations; maximum 25 for laminar, k–ε, and SST respectively). The k–ε run also records 534 `k` and 534 `epsilon` solves at four iterations each; SST records 534 `k` solves averaging 3.85 iterations and 534 `omega` solves at four iterations. Solver logs provide aggregate execution time and iteration counts, not separate pressure-solve or I/O elapsed-time shares. The runs used about 10 CPU cores at peak and wrote about 410–474 MiB per bundle.

The corrected-caption images are [laminar](../../results/runs/restas-hnf-laminar-20260928T145501Z-4fe554/figures/water-volume-alpha-0p65-t-0p020000s-crossflow.png), [realizable k–ε](../../results/runs/restas-hnf-realizableke-20260928T151453Z-0c472f/figures/water-volume-alpha-0p65-t-0p020000s-crossflow.png), and [k–ω SST](../../results/runs/restas-hnf-komegasst-20260928T152510Z-2e0e11/figures/water-volume-alpha-0p65-t-0p020000s-crossflow.png). Each run directory contains the renderer JSON, source field, interface VTP, full console log, and manifest.

## Preserved preflights and failed attempts

- `results/runs/restas-horizontal-nearfield-preflight-20260928` is a 100,368-cell, 50 mm laminar, 2 ms preflight: `interIsoFoam` reached 2 ms in 1.32 s reported execution time, max Co was 0.14638, max interface Co 0.10111, and integrated source volume was 0.024 m³. Its mesh check passed.
- `restas-hnf-realizableke-20260928T144348Z-1f1e78` is the 100,368-cell, 10 ms realizable k–ε probe. The solver and reconstruction reached the end, but max Co 0.3597 exceeded the predeclared 0.3 stop while interface Co was 0.108; it is preserved and reported as a stopped attempt.
- `restas-hnf-laminar-20260928T144913Z-54b865` is the first 803k-cell laminar attempt. With a 7.5e-5 s step ceiling, it was stopped at 12.782 ms after max Co reached 0.3012. The matched runs use a halved common ceiling, 3.75e-5 s.
- `restas-hnf-realizableke-20260928T150446Z-c9c444` is an incomplete 803k-cell k–ε attempt. Its saved log stops during the step entering 13.221 ms and the run manifest has no exit code or wall time. `interrupted-observation.json` records the evidence and leaves the cause unknown; a complete rerun is the tabled comparison.
- `restas-hnf-komegasst-20260928T152214Z-3dce01` records an SST startup error: OpenFOAM 2512 required the missing `wallDist` method. `restas-hnf-komegasst-20260928T152427Z-f87627` records a 100k-cell SST preflight whose solver reached 2 ms but reconstruction found no saved final time because the old write interval was 10 ms. The case generator now uses `wallDist { method meshWave; }` and writes at `min(10 ms, endTime)`; the tabled 20 ms SST run completed.

The preflights are diagnostic only. None of these runs establishes a scientific validation gate or a built-system reproduction.
