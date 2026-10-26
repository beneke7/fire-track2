#!/usr/bin/env pvpython
"""Make a first-look ParaView state for a reconstructed OpenFOAM VOF case."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from paraview.simple import (
    AnnotateTimeFilter,
    Calculator,
    CellDatatoPointData,
    ColorBy,
    Contour,
    GetActiveViewOrCreate,
    GetAnimationScene,
    GetColorTransferFunction,
    GetScalarBar,
    OpenFOAMReader,
    Outline,
    SaveScreenshot,
    SaveState,
    Show,
    Slice,
    Text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="reconstructed OpenFOAM .foam marker or its directory")
    parser.add_argument("--state", required=True, help="new .pvsm output path")
    parser.add_argument("--screenshot", help="optional PNG; requires an OSMesa software backend")
    parser.add_argument("--slice-axis", choices=("x", "y", "z"), default="z")
    parser.add_argument(
        "--speed-range",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="fixed speed color range in m/s; default uses this case's data range",
    )
    return parser.parse_args()


def foam_marker(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.is_dir():
        markers = sorted(path.glob("*.foam"))
        if len(markers) == 1:
            return markers[0]
        if not markers:
            raise ValueError(f"{path} has no .foam marker; reconstruct the case and add one")
        raise ValueError(f"{path} has multiple .foam markers; pass the intended marker explicitly")
    if path.is_file() and path.suffix == ".foam":
        return path
    raise ValueError(f"expected an existing .foam marker or its directory, got {path}")


def data_array_names(array_info: object) -> set[str]:
    return {
        array_info.GetArrayInformation(index).GetName()
        for index in range(array_info.GetNumberOfArrays())
    }


def main() -> None:
    args = parse_args()
    case = foam_marker(args.case)
    state_path = Path(args.state).expanduser().resolve()
    screenshot_path = Path(args.screenshot).expanduser().resolve() if args.screenshot else None
    if screenshot_path == state_path:
        raise ValueError("--state and --screenshot must name different files")
    for output in (state_path, screenshot_path):
        if output is not None and output.exists():
            raise FileExistsError(f"refusing to overwrite {output}")
    if args.speed_range is not None and (
        not all(math.isfinite(value) for value in args.speed_range)
        or args.speed_range[0] >= args.speed_range[1]
    ):
        raise ValueError("--speed-range must be finite and increasing")

    reader = OpenFOAMReader(registrationName="OpenFOAM tutorial", FileName=str(case))
    reader.SkipZeroTime = 0
    reader.MeshRegions = ["internalMesh"]
    reader.CellArrays = ["alpha.water", "U"]
    reader.UpdatePipeline()

    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    scene.GoToLast()
    reader.UpdatePipeline()
    time = float(scene.AnimationTime)

    cell_names = data_array_names(reader.GetDataInformation().GetCellDataInformation())
    missing = {"alpha.water", "U"} - cell_names
    if missing:
        raise ValueError(f"{case} is missing required cell fields: {', '.join(sorted(missing))}")

    bounds = reader.GetDataInformation().GetBounds()
    center = [(bounds[i] + bounds[i + 1]) / 2.0 for i in (0, 2, 4)]
    axis = {"x": 0, "y": 1, "z": 2}[args.slice_axis]
    normal = [float(index == axis) for index in range(3)]

    point_fields = CellDatatoPointData(registrationName="Point fields", Input=reader)
    point_fields.UpdatePipeline()
    water_surface = Contour(registrationName="alpha.water = 0.5", Input=point_fields)
    water_surface.ContourBy = ["POINTS", "alpha.water"]
    water_surface.Isosurfaces = [0.5]
    speed = Calculator(registrationName="Speed magnitude", Input=water_surface)
    speed.AttributeType = "Point Data"
    speed.Function = "mag(U)"
    speed.ResultArrayName = "speed"

    center_slice = Slice(registrationName="Center volume-fraction slice", Input=point_fields)
    center_slice.SliceType = "Plane"
    center_slice.SliceType.Origin = center
    center_slice.SliceType.Normal = normal
    outline = Outline(registrationName="Domain outline", Input=reader)

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [1400, 900]
    view.OrientationAxesVisibility = 1
    speed_display = Show(speed, view)
    ColorBy(speed_display, ("POINTS", "speed"))
    speed_display.RescaleTransferFunctionToDataRange(True, False)
    speed_lut = GetColorTransferFunction("speed")
    if args.speed_range is not None:
        speed_lut.RescaleTransferFunction(*args.speed_range)
    speed_lut.AutomaticRescaleRangeMode = "Never"
    speed_bar = GetScalarBar(speed_lut, view)
    speed_bar.Title = "Speed"
    speed_bar.ComponentTitle = "m/s"
    speed_bar.WindowLocation = "Upper Right Corner"
    speed_display.SetScalarBarVisibility(view, True)

    slice_display = Show(center_slice, view)
    ColorBy(slice_display, ("POINTS", "alpha.water"))
    alpha_lut = GetColorTransferFunction("alpha.water")
    alpha_lut.RescaleTransferFunction(0.0, 1.0)
    alpha_lut.AutomaticRescaleRangeMode = "Never"
    alpha_bar = GetScalarBar(alpha_lut, view)
    alpha_bar.Title = "Water volume fraction"
    alpha_bar.ComponentTitle = "alpha.water"
    alpha_bar.WindowLocation = "Lower Right Corner"
    slice_display.SetScalarBarVisibility(view, True)

    outline_display = Show(outline, view)
    outline_display.DiffuseColor = [0.1, 0.1, 0.1]
    outline_display.LineWidth = 1.5
    label = Text(
        registrationName="Scope label",
        Text="interIsoFoam tutorial | exploratory computed fields | no inferred droplets",
    )
    label_display = Show(label, view)
    label_display.WindowLocation = "Upper Left Corner"
    label_display.FontSize = 14
    label_display.Color = [0.05, 0.05, 0.05]
    time_label = AnnotateTimeFilter(registrationName="Time annotation", Input=reader)
    time_label.Format = "Time: {time:g} s"
    time_display = Show(time_label, view)
    time_display.WindowLocation = "Lower Left Corner"
    time_display.FontSize = 14
    time_display.Color = [0.05, 0.05, 0.05]
    diagonal = math.sqrt(sum((bounds[i + 1] - bounds[i]) ** 2 for i in (0, 2, 4)))
    view.CameraFocalPoint = center
    view.CameraPosition = [center[0], center[1], center[2] + 2.0 * diagonal]
    view.CameraViewUp = [0.0, 1.0, 0.0]
    view.CameraParallelProjection = 1
    view.CameraParallelScale = 0.65 * diagonal

    state_path.parent.mkdir(parents=True, exist_ok=True)
    if screenshot_path is not None:
        render_window = view.GetRenderWindow()
        backend = render_window.GetClassName()
        if backend not in {"vtkOSOpenGLRenderWindow", "vtkOSMesaRenderWindow"}:
            raise RuntimeError(
                f"CPU screenshot needs an OSMesa render window; ParaView selected {backend}. "
                "Try a ParaView build with OSMesa and --opengl-window-backend OSMesa."
            )
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        SaveScreenshot(str(screenshot_path), view, ImageResolution=[1400, 900])
    SaveState(str(state_path))
    print(f"state: {state_path}")
    if screenshot_path is not None:
        print(f"screenshot: {screenshot_path}")
    print(f"latest time: {time:g} s; .foam input: {case}")


if __name__ == "__main__":
    main()
