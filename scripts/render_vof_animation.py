#!/usr/bin/env python3
"""Render saved OpenFOAM VOF snapshots as a timestamp-faithful MP4.

The video repeats each computed snapshot for the duration represented by its
simulation-time interval. It never interpolates or extrapolates flow fields.
The displayed alpha.water=0.50 surface is computed from cell-to-point
interpolation of the saved cell field and is a display geometry only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numeric_time_dirs(case_dir: Path) -> list[Path]:
    found: list[Path] = []
    for path in case_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if math.isfinite(value) and value >= 0.0:
            found.append(path)
    return sorted(found, key=lambda path: float(path.name))


def frame_hold_schedule(
    simulation_times_s: Sequence[float],
    *,
    slowdown: float,
    fps: int,
    endpoint_hold_s: float = 1.0,
) -> list[dict[str, Any]]:
    """Map each stored time to an integer video-frame hold without interpolation."""
    times = [float(value) for value in simulation_times_s]
    if not times or any(not math.isfinite(value) or value < 0.0 for value in times):
        raise ValueError(
            "simulation times must be a nonempty sequence of finite nonnegative values"
        )
    if not math.isclose(times[0], 0.0, abs_tol=1e-12):
        raise ValueError("the first saved simulation time must be zero")
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("saved simulation times must be strictly increasing")
    if not math.isfinite(slowdown) or slowdown <= 0.0:
        raise ValueError("slowdown must be finite and positive")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    if not math.isfinite(endpoint_hold_s) or endpoint_hold_s <= 0.0:
        raise ValueError("endpoint hold must be finite and positive")

    absolute_frames = [round(value * slowdown * fps) for value in times]
    schedule: list[dict[str, Any]] = []
    next_frame = 0
    for index, time_s in enumerate(times):
        is_endpoint = index == len(times) - 1
        if is_endpoint:
            frame_count = round(endpoint_hold_s * fps)
            interval_end_s = time_s
            represented_interval_s = 0.0
        else:
            frame_count = absolute_frames[index + 1] - absolute_frames[index]
            interval_end_s = times[index + 1]
            represented_interval_s = interval_end_s - time_s
        if frame_count < 1:
            raise ValueError(
                "slowdown and fps must allocate at least one video frame to every saved interval"
            )
        schedule.append(
            {
                "simulation_time_s": time_s,
                "simulation_interval_end_s": interval_end_s,
                "represented_simulation_interval_s": represented_interval_s,
                "playback_duration_s": frame_count / fps,
                "frame_start_inclusive": next_frame,
                "frame_count": frame_count,
                "endpoint_hold": is_endpoint,
                "sampling": "hold_saved_snapshot; no temporal interpolation or extrapolation",
            }
        )
        next_frame += frame_count
    return schedule


def _fixed_isometric_camera(
    plotter: Any,
    bounds: tuple[float, float, float, float, float, float],
    window_size: tuple[int, int],
) -> dict[str, Any]:
    """Set a repeatable parallel camera around fixed physical mesh bounds."""
    import numpy as np

    limits = np.asarray(bounds, dtype=np.float64).reshape(3, 2)
    if not np.isfinite(limits).all() or np.any(limits[:, 1] <= limits[:, 0]):
        raise ValueError("camera bounds must be six finite, increasing physical limits")
    center = limits.mean(axis=1)
    corners = np.asarray(
        [(x, y, z) for x in limits[0] for y in limits[1] for z in limits[2]],
        dtype=np.float64,
    )
    direction = np.asarray((-1.0, -1.0, -1.0), dtype=np.float64) / math.sqrt(3.0)
    view_up = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    right = np.cross(direction, view_up)
    right /= np.linalg.norm(right)
    screen_up = np.cross(right, direction)
    relative = corners - center
    half_height = float(np.max(np.abs(relative @ screen_up)))
    half_width = float(np.max(np.abs(relative @ right)))
    aspect = window_size[0] / window_size[1]
    parallel_scale = 1.06 * max(half_height, half_width / aspect)
    distance = 2.0 * float(np.max(limits[:, 1] - limits[:, 0]))

    camera = plotter.camera
    camera.focal_point = tuple(center)
    camera.position = tuple(center - direction * distance)
    camera.up = tuple(view_up)
    camera.parallel_projection = True
    camera.parallel_scale = parallel_scale
    plotter.reset_camera_clipping_range()
    return {
        "mode": "fixed-isometric-parallel",
        "physical_bounds_m": [float(value) for value in bounds],
        "focal_point_m": [float(value) for value in center],
        "view_direction": [float(value) for value in direction],
        "parallel_scale_m": parallel_scale,
    }


def _bounds_from_inputs(
    inputs: dict[str, Any],
) -> tuple[float, float, float, float, float, float] | None:
    raw = inputs.get("domain_bounds_m")
    if not isinstance(raw, dict):
        return None
    try:
        values = tuple(float(value) for axis in ("x", "y", "z") for value in raw[axis])
    except (KeyError, TypeError, ValueError):
        return None
    if len(values) != 6 or not all(math.isfinite(value) for value in values):
        return None
    if any(values[index + 1] <= values[index] for index in (0, 2, 4)):
        return None
    return values


def _git_record(repository: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(repository), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}
    return {"revision": revision, "dirty": dirty}


def _tool_version(command: str) -> str:
    result = subprocess.run([command, "-version"], check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).splitlines()[0].strip()


def _make_frame(
    *,
    pyvista_module: Any,
    surface: Any | None,
    camera_bounds: tuple[float, float, float, float, float, float],
    output_path: Path,
    window_size: tuple[int, int],
    title: str,
    orientation_label: str,
    simulation_time_s: float,
    slowdown: float,
    alpha_max: float,
    empty_field: bool,
    smoothing_iterations: int = 0,
    view_bounds: tuple[float, float, float, float, float, float] | None = None,
    isosurface_alpha: float = 0.5,
) -> dict[str, Any]:
    plotter = pyvista_module.Plotter(off_screen=True, window_size=window_size)
    try:
        plotter.set_background("#f7f9fc")
        plotter.enable_anti_aliasing("ssaa")
        if view_bounds is None:
            plotter.add_mesh(
                pyvista_module.Cube(bounds=camera_bounds),
                color="#cad3df",
                style="wireframe",
                line_width=0.7,
                opacity=0.75,
                reset_camera=False,
            )
        if surface is not None:
            plotter.add_mesh(
                surface,
                name="computed-water-alpha-isosurface",
                color="#2e91bd",
                smooth_shading=True,
                ambient=0.42,
                diffuse=0.76,
                specular=0.08,
                specular_power=28,
                show_edges=False,
                reset_camera=False,
            )
        plotter.add_axes(xlabel="x [m]", ylabel="y [m]", zlabel="z [m]")
        camera_record = _fixed_isometric_camera(
            plotter, view_bounds if view_bounds is not None else camera_bounds, window_size
        )
        plotter.add_text(
            f"{title}\n{orientation_label}",
            position="upper_left",
            font_size=13,
            color="#152238",
        )
        plotter.add_text(
            f"Actual simulation t = {simulation_time_s:.6f} s\nPlayback {slowdown:g}x slower",
            position="upper_right",
            font_size=13,
            color="#152238",
        )
        if surface is None:
            if empty_field:
                empty_label = "AIR ONLY - no water in saved alpha.water field"
            else:
                empty_label = (
                    f"No alpha.water = {isosurface_alpha:g} surface (field maximum {alpha_max:.3f})"
                )
            plotter.add_text(
                empty_label,
                position=(window_size[0] * 0.24, window_size[1] * 0.53),
                font_size=18,
                color="#52627a",
            )
        plotter.add_text(
            f"Computed water VOF | display surface: cell-to-point interpolated alpha.water = {isosurface_alpha:g}\n"
            + (
                f"Display-only surface smoothing: {smoothing_iterations} iterations | "
                if smoothing_iterations
                else ""
            )
            + "Water only; no temporal interpolation",
            position="lower_left",
            font_size=12,
            color="#26344a",
        )
        plotter.show(screenshot=str(output_path), auto_close=False, interactive=False)
        return camera_record
    finally:
        plotter.close()


def _probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames,duration",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def render(
    run_dir: Path,
    output_dir: Path,
    *,
    label: str,
    slowdown: float,
    orientation_label: str,
    fps: int = 30,
    width: int = 1600,
    height: int = 900,
    endpoint_hold_s: float = 1.0,
    surface_smoothing_iterations: int = 0,
    surface_smoothing_pass_band: float = 0.1,
    camera_bounds_override: tuple[float, float, float, float, float, float] | None = None,
    isosurface_alpha: float = 0.5,
) -> dict[str, Any]:
    """Render one water-only video and write a provenance record beside it."""
    try:
        import numpy as np
        import pyvista as pv
    except ImportError as error:
        raise RuntimeError(
            "Rendering dependencies are optional; use the environment with the visualization extra"
        ) from error

    if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise ValueError("label may contain only letters, numbers, underscores, and hyphens")
    if not math.isfinite(isosurface_alpha) or not 0 < isosurface_alpha < 1:
        raise ValueError("isosurface alpha must be finite and between 0 and 1")
    if (
        isinstance(surface_smoothing_iterations, bool)
        or not isinstance(surface_smoothing_iterations, int)
        or surface_smoothing_iterations < 0
    ):
        raise ValueError("surface smoothing iterations must be a nonnegative integer")
    if not math.isfinite(surface_smoothing_pass_band) or not 0 < surface_smoothing_pass_band < 2:
        raise ValueError("surface smoothing pass band must be finite and between 0 and 2")
    if camera_bounds_override is not None:
        if (
            len(camera_bounds_override) != 6
            or not all(math.isfinite(value) for value in camera_bounds_override)
            or any(camera_bounds_override[i] >= camera_bounds_override[i + 1] for i in (0, 2, 4))
        ):
            raise ValueError("camera bounds must contain six finite increasing axis limits")
    if not orientation_label.strip() or "\n" in orientation_label or "\r" in orientation_label:
        raise ValueError("orientation label must be one nonempty line")
    if isinstance(width, bool) or isinstance(height, bool) or width < 2 or height < 2:
        raise ValueError("video dimensions must be positive pixel sizes")
    if width % 2 or height % 2:
        raise ValueError("H.264 yuv420p output requires even width and height")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe are required to create and verify the MP4")

    run_dir = run_dir.resolve()
    output_dir = output_dir.resolve()
    case_dir = run_dir / "case"
    time_dirs = _numeric_time_dirs(case_dir)
    if not time_dirs:
        raise ValueError(f"No reconstructed OpenFOAM time directories found in {case_dir}")
    alpha_paths = [path / "alpha.water" for path in time_dirs]
    missing_fields = [str(path) for path in alpha_paths if not path.is_file()]
    if missing_fields:
        raise ValueError("Missing reconstructed alpha.water fields: " + ", ".join(missing_fields))

    points_path = case_dir / "constant" / "polyMesh" / "points"
    control_dict_path = case_dir / "system" / "controlDict"
    inputs_path = run_dir / "inputs.json"
    if not inputs_path.exists():
        inputs_path = run_dir / "case" / "case-inputs.json"
    manifest_path = run_dir / "manifest.json"
    for required in (points_path, control_dict_path, inputs_path, manifest_path):
        if not required.is_file():
            raise ValueError(f"Missing run provenance or case input: {required}")
    hashed_case_files = [
        points_path,
        case_dir / "constant" / "polyMesh" / "faces",
        case_dir / "constant" / "polyMesh" / "owner",
        case_dir / "constant" / "polyMesh" / "neighbour",
        case_dir / "constant" / "polyMesh" / "boundary",
        control_dict_path,
        case_dir / "constant" / "transportProperties",
        case_dir / "constant" / "turbulenceProperties",
    ]
    case_file_hashes = {
        str(path.relative_to(case_dir)): _sha256(path)
        for path in hashed_case_files
        if path.is_file()
    }
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(inputs, dict) or not isinstance(manifest, dict):
        raise ValueError("run inputs and manifest must contain JSON objects")

    simulation_times = [float(path.name) for path in time_dirs]
    schedule = frame_hold_schedule(
        simulation_times,
        slowdown=slowdown,
        fps=fps,
        endpoint_hold_s=endpoint_hold_s,
    )
    total_frame_count = sum(row["frame_count"] for row in schedule)
    if total_frame_count <= 0:
        raise ValueError("animation schedule contains no frames")

    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"{label}.mp4"
    record_path = output_dir / f"{label}.json"
    snapshots_dir = output_dir / "snapshots"
    if video_path.exists() or record_path.exists() or snapshots_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing animation output in {output_dir}")
    snapshots_dir.mkdir()

    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    try:
        import vtk

        vtk.vtkMultiThreader.SetGlobalMaximumNumberOfThreads(1)
    except (ImportError, AttributeError):
        pass

    snapshot_records: list[dict[str, Any]] = []
    camera_record: dict[str, Any] | None = None
    camera_bounds = _bounds_from_inputs(inputs)
    window_size = (width, height)

    # The reader and temporary .foam marker follow the established presentation
    # workflow; neither alters the source run bundle.
    with tempfile.TemporaryDirectory(prefix="vof-animation-reader-") as temporary:
        reader_case = Path(temporary)
        for source in [case_dir / "constant", case_dir / "system", *time_dirs]:
            os.symlink(source, reader_case / source.name, target_is_directory=True)
        marker = reader_case / "render.foam"
        marker.touch()
        reader = pv.OpenFOAMReader(str(marker))
        reader.enable_cell_array("alpha.water")

        for time_index, (time_dir, time_s, timing) in enumerate(
            zip(time_dirs, simulation_times, schedule, strict=True)
        ):
            if not any(math.isclose(value, time_s, abs_tol=1e-9) for value in reader.time_values):
                raise ValueError(f"VTK did not expose reconstructed time {time_s:g} s")
            reader.set_active_time_value(time_s)
            data = reader.read()
            try:
                volume_mesh = data["internalMesh"]
            except (KeyError, TypeError) as error:
                raise ValueError(
                    "OpenFOAM reader did not return the internal volume mesh"
                ) from error
            if "alpha.water" not in volume_mesh.cell_data:
                raise ValueError(f"Saved time {time_s:g} has no cell-centered alpha.water field")
            alpha = np.asarray(volume_mesh.cell_data["alpha.water"], dtype=np.float64)
            if alpha.shape != (volume_mesh.n_cells,) or not np.isfinite(alpha).all():
                raise ValueError(f"alpha.water at t={time_s:g} is not one finite value per cell")
            if float(alpha.min()) < -1e-5 or float(alpha.max()) > 1.0 + 1e-5:
                raise ValueError(f"alpha.water at t={time_s:g} lies outside [0, 1]")
            cell_volumes = np.asarray(
                volume_mesh.compute_cell_sizes(length=False, area=False, volume=True)["Volume"],
                dtype=np.float64,
            )
            water_inventory = float(alpha @ cell_volumes)
            current_mesh_bounds = tuple(float(value) for value in volume_mesh.bounds)
            if camera_bounds is None:
                camera_bounds = current_mesh_bounds
            if any(
                abs(current_mesh_bounds[index] - camera_bounds[index]) > 1e-6 for index in range(6)
            ):
                raise ValueError(
                    "mesh bounds changed across saved times; a fixed camera is invalid"
                )

            point_alpha_range: list[float] | None = None
            surface = None
            if float(alpha.max()) >= isosurface_alpha and float(alpha.min()) <= isosurface_alpha:
                # Match the refined presentation render: retain the original
                # cell field and interpolate it only for display.
                point_mesh = volume_mesh.cell_data_to_point_data(pass_cell_data=True)
                point_alpha = np.asarray(point_mesh.point_data["alpha.water"], dtype=np.float64)
                point_alpha_range = [float(point_alpha.min()), float(point_alpha.max())]
                surface = point_mesh.contour(
                    isosurfaces=[isosurface_alpha], scalars="alpha.water", method="contour"
                ).triangulate()
                if surface.n_points == 0 or surface.n_cells == 0:
                    surface = None
                elif surface_smoothing_iterations:
                    surface = surface.smooth_taubin(
                        n_iter=surface_smoothing_iterations,
                        pass_band=surface_smoothing_pass_band,
                        boundary_smoothing=False,
                        feature_smoothing=False,
                        normalize_coordinates=True,
                        inplace=False,
                    )
                    if not np.isfinite(np.asarray(surface.points)).all():
                        raise ValueError(
                            f"display smoothing produced nonfinite points at t={time_s:g}"
                        )

            snapshot_path = (
                snapshots_dir
                / f"snapshot-{time_index:03d}-t-{time_dir.name.replace('.', 'p')}s.png"
            )
            camera_record = _make_frame(
                pyvista_module=pv,
                surface=surface,
                camera_bounds=camera_bounds,
                output_path=snapshot_path,
                window_size=window_size,
                title=label.replace("_", " ").replace("-", " ").upper(),
                orientation_label=orientation_label,
                simulation_time_s=time_s,
                slowdown=slowdown,
                alpha_max=float(alpha.max()),
                empty_field=bool(np.max(np.abs(alpha)) <= 1e-12),
                smoothing_iterations=surface_smoothing_iterations,
                view_bounds=camera_bounds_override,
                isosurface_alpha=isosurface_alpha,
            )
            snapshot_records.append(
                {
                    "time_directory": time_dir.name,
                    "simulation_time_s": time_s,
                    "alpha_water_sha256": _sha256(time_dir / "alpha.water"),
                    "snapshot_png": str(snapshot_path.resolve()),
                    "snapshot_png_sha256": _sha256(snapshot_path),
                    "alpha_water_cell_value_range": [float(alpha.min()), float(alpha.max())],
                    "water_inventory_m3_from_cell_alpha_times_volume": water_inventory,
                    "volume_cell_count": int(volume_mesh.n_cells),
                    "display_surface_point_count": int(surface.n_points)
                    if surface is not None
                    else 0,
                    "display_surface_triangle_count": int(surface.n_cells)
                    if surface is not None
                    else 0,
                    "display_surface_bounds_m": (
                        [float(value) for value in surface.bounds] if surface is not None else None
                    ),
                    "display_point_alpha_range": point_alpha_range,
                    "empty_water_field": bool(np.max(np.abs(alpha)) <= 1e-12),
                    "timing": timing,
                }
            )
            print(
                f"Rendered {time_s:.6f} s snapshot "
                f"({snapshot_records[-1]['display_surface_triangle_count']:,} triangles)",
                flush=True,
            )

    if camera_bounds is None or camera_record is None:
        raise ValueError("could not determine fixed camera bounds from the reconstructed mesh")

    frame_dir = output_dir / "encode_frames"
    frame_dir.mkdir()
    frame_index = 0
    for snapshot, timing in zip(snapshot_records, schedule, strict=True):
        source = Path(snapshot["snapshot_png"])
        for _ in range(timing["frame_count"]):
            target = frame_dir / f"frame-{frame_index:06d}.png"
            try:
                target.hardlink_to(source)
            except OSError:
                shutil.copyfile(source, target)
            frame_index += 1

    ffmpeg_command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-framerate",
        str(fps),
        "-i",
        str(frame_dir / "frame-%06d.png"),
        "-frames:v",
        str(total_frame_count),
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_path),
    ]
    subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
    probe = _probe_video(video_path)
    stream = probe.get("streams", [{}])[0]
    if stream.get("codec_name") != "h264":
        raise RuntimeError(f"Expected H.264 video, ffprobe reported {stream.get('codec_name')!r}")
    if int(stream.get("width", 0)) != width or int(stream.get("height", 0)) != height:
        raise RuntimeError("ffprobe reported video dimensions different from the render settings")
    actual_frames = int(stream.get("nb_frames", -1))
    if actual_frames != total_frame_count:
        raise RuntimeError(
            f"ffprobe reports {actual_frames} frames; expected {total_frame_count} from saved times"
        )
    shutil.rmtree(frame_dir)

    start_index = 0
    middle_index = len(snapshot_records) // 2
    end_index = len(snapshot_records) - 1
    repo_root = Path(__file__).resolve().parents[1]
    video_record = {
        "schema": "vof-saved-snapshot-animation/v1",
        "rendered_utc": datetime.now(UTC).isoformat(),
        "label": label,
        "orientation_label": orientation_label,
        "run": {
            "run_id": manifest.get("run_id", run_dir.name),
            "run_directory": str(run_dir),
            "case_id": inputs.get("case_id"),
            "case_classification": manifest.get("case_classification")
            or inputs.get("case_classification")
            or inputs.get("evidence_label"),
            "run_started_utc": manifest.get("started_utc"),
            "run_finished_utc": manifest.get("finished_utc"),
            "run_git_revision": manifest.get("git_revision"),
            "run_git_worktree_dirty": manifest.get("git_worktree_dirty"),
            "run_exit_code": manifest.get("exit_code", manifest.get("case_command_exit_code")),
            "run_status": manifest.get("status"),
            "solver_image": manifest.get("solver_image") or inputs.get("openfoam_image"),
            "run_manifest_sha256": _sha256(manifest_path),
            "inputs_sha256": _sha256(inputs_path),
            "inputs": inputs,
        },
        "orientation": {
            "operator_label": orientation_label,
            "source_velocity_m_s_each": inputs.get("source_velocity_m_s_each"),
            "source_velocity_m_s": inputs.get("source_velocity_m_s"),
            "coordinate_frame": inputs.get("coordinate_frame"),
            "historical_orientation_warning": (
                "This saved historical case uses the legacy downward -z outlet vector. "
                "It predates the correction that the four Restas outlets discharge horizontally; "
                "it is presented separately and is not blended with the horizontal case."
                if inputs.get("source_velocity_m_s") == [0.0, 0.0, -4.8]
                else None
            ),
        },
        "physics_and_display": {
            "solver": inputs.get("solver"),
            "turbulence_model": inputs.get("turbulence_model") or inputs.get("model"),
            "mesh_spacing_m": inputs.get("mesh_spacing_m", inputs.get("local_spacing_m"))
            or inputs.get("finest_interface_cell_spacing_m")
            or inputs.get("mesh_cell_width_m"),
            "domain_bounds_from_inputs_m": inputs.get("domain_bounds_m"),
            "reconstructed_mesh_bounds_m": list(camera_bounds),
            "case_file_sha256": case_file_hashes,
            "surface_method": (
                "cell_data_to_point_data(pass_cell_data=True), then linear contour at "
                f"alpha.water={isosurface_alpha:g}, triangulate"
            ),
            "isosurface_alpha": isosurface_alpha,
            "surface_is_display_interpolation": True,
            "surface_smoothing": {
                "method": "Taubin windowed-sinc, display geometry only",
                "iterations": surface_smoothing_iterations,
                "pass_band": surface_smoothing_pass_band,
                "boundary_smoothing": False,
                "changes_cell_alpha_or_water_inventory": False,
            },
            "alpha_source_is_saved_cell_field": True,
            "computed_fields": [
                "saved cell-centered alpha.water",
                "water inventory from alpha.water times cell volume",
            ],
            "water_only": True,
            "foam_bubbles_mist_or_secondary_droplets_modeled": False,
            "temporal_interpolation_or_extrapolation": False,
            "empty_t0_frame_preserved": snapshot_records[0]["empty_water_field"],
        },
        "playback": {
            "slowdown_factor": float(slowdown),
            "fps": fps,
            "timestamp_rule": "each saved time snapshot is held through its following saved-time interval",
            "endpoint_hold_s": float(endpoint_hold_s),
            "duration_s": total_frame_count / fps,
            "total_frame_count": total_frame_count,
            "actual_saved_simulation_times_s": simulation_times,
            "maximum_actual_simulation_time_s": simulation_times[-1],
            "schedule": schedule,
        },
        "snapshots": snapshot_records,
        "inspection_frames": {
            "start_png": snapshot_records[start_index]["snapshot_png"],
            "middle_png": snapshot_records[middle_index]["snapshot_png"],
            "end_png": snapshot_records[end_index]["snapshot_png"],
            "middle_simulation_time_s": snapshot_records[middle_index]["simulation_time_s"],
        },
        "render": {
            "output_mp4": str(video_path),
            "output_mp4_sha256": _sha256(video_path),
            "output_size_bytes": video_path.stat().st_size,
            "pixel_size": [width, height],
            "camera": camera_record,
            "camera_bounds_override_m": camera_bounds_override,
            "domain_wireframe_shown": camera_bounds_override is None,
            "surface_color": "#2e91bd",
            "lighting": f"smooth shaded computed alpha={isosurface_alpha:g} isosurface",
            "anti_aliasing": "supersampling (SSAA)",
            "ffmpeg_command": ffmpeg_command,
            "ffmpeg_version": _tool_version("ffmpeg"),
            "ffprobe": probe,
            "pyvista_version": pv.__version__,
            "vtk_version": ".".join(str(value) for value in pv.vtk_version_info),
            "render_script_sha256": _sha256(Path(__file__).resolve()),
            "git": _git_record(repo_root),
        },
        "claim_limit": (
            f"Exploratory video of saved water-only VOF fields. The {isosurface_alpha:g} surface is interpolated "
            "display geometry; playback holds stored states and does not create intermediate physics. "
            "This does not validate breakup, descent, deposition, foam behavior, or field performance."
        ),
    }
    record_path.write_text(
        json.dumps(video_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Encoded {video_path} ({total_frame_count} frames, {total_frame_count / fps:.2f} s)")
    print(f"Render record {record_path}")
    return video_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--slowdown", required=True, type=float)
    parser.add_argument("--label", required=True, help="filename-safe video label")
    parser.add_argument(
        "--orientation-label",
        required=True,
        help="explicit source-orientation description shown on every frame",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--endpoint-hold", type=float, default=1.0, metavar="SECONDS")
    parser.add_argument("--surface-smoothing-iterations", type=int, default=0)
    parser.add_argument("--surface-smoothing-pass-band", type=float, default=0.1)
    parser.add_argument("--isosurface-alpha", type=float, default=0.5)
    parser.add_argument(
        "--camera-bounds",
        type=float,
        nargs=6,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"),
    )
    args = parser.parse_args()
    try:
        render(
            run_dir=args.run_dir,
            output_dir=args.output_dir,
            slowdown=args.slowdown,
            label=args.label,
            orientation_label=args.orientation_label,
            fps=args.fps,
            width=args.width,
            height=args.height,
            endpoint_hold_s=args.endpoint_hold,
            surface_smoothing_iterations=args.surface_smoothing_iterations,
            surface_smoothing_pass_band=args.surface_smoothing_pass_band,
            camera_bounds_override=tuple(args.camera_bounds) if args.camera_bounds else None,
            isosurface_alpha=args.isosurface_alpha,
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
