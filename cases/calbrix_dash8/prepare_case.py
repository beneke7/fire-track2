#!/usr/bin/env python3
"""Prepare a provisional single-opening Dash-8 OpenFOAM nearfield case.

The generator reuses the CL-415 case's Cartesian mesh and OpenFOAM dictionary
helpers. The one 4.44 m by 0.30 m source is a figure-derived geometry
candidate, not a reported aperture measurement. The five-second digitized
history ends at a nonzero velocity, so each case ends at its requested horizon
without adding a shutoff or an extrapolated tail.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PRIMARY_HISTORY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity.csv"
INDEPENDENT_HISTORY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity_independent.csv"
SOURCE_RECORD = ROOT / "experiments/E2_CALBRIX_SOURCE.md"
CL415_HELPERS_PATH = ROOT / "cases/calbrix_cl415/prepare_case.py"

CASE_ID = "E2_CALBRIX_DASH8_EXPLORATORY_NEARFIELD_SINGLE_OPENING"
SOURCE_NAME = "dash8Opening"
HISTORY_NAME = "dash8"
MAX_HISTORY_HORIZON_S = 5.0
WATER_RHO_KG_M3 = 1000.0
AIR_SPEED_M_S = 50.0
PARABOLIC_MAX_PROFILE = "parabolic-max"
GRAVITY_M_S2 = (0.0, 0.0, -9.81)
DEFAULT_SOURCE_LENGTH_M = 4.44
DEFAULT_SOURCE_WIDTH_M = 0.30
DEFAULT_DOMAIN_BOUNDS_M = {
    "x": (-3.0, 23.0),
    "y": (-10.0, 10.0),
    "z": (-31.0, 0.0),
}
DEFAULT_REFINEMENT_REGION_M = {
    "x": (-2.5, 4.0),
    "y": (-1.5, 1.5),
    "z": (-3.0, 0.0),
}
OPEN_PATCHES = ["airInlet", "xOutlet", "yMin", "yMax", "zMin"]
SOURCE_PROFILE_MODES = {
    "long_wave": (
        "smooth variation mainly along the streamwise opening with wavelengths from one to "
        "four times its length; cross-track wavelengths are at least twice the opening width"
    ),
    "cross_stream": (
        "smooth cross-track variation with a weak streamwise component; cross-track "
        "wavelengths are about 1.3 to four times the opening width, so resolution depends "
        "on the actual face spacing"
    ),
    "multi_scale": (
        "seeded mixture of streamwise wavelengths from one-half to four times the opening "
        "length and cross-track wavelengths from one to four times its width; shortest "
        "scales are provisional and must be checked against face spacing"
    ),
}
PROFILE_MODE_COUNT = 24
DEFAULT_PROFILE_AMPLITUDE = 0.20
DEFAULT_PROFILE_SEED = 1
DEFAULT_PROFILE_CORRELATION_TIME_S = 0.25


def _load_cl415_helpers() -> Any:
    """Load CL-415 helpers under a unique name without importing its CLI module."""
    module_name = "track2_dash8_cl415_mesh_field_dictionary_helpers"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, CL415_HELPERS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load CL-415 helpers from {CL415_HELPERS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CL_HELPERS = _load_cl415_helpers()
DEFAULT_TURBULENCE_INTENSITY = CL_HELPERS.TURBULENCE_INTENSITY
DEFAULT_AIR_LENGTH_SCALE_M = CL_HELPERS.AIR_LENGTH_SCALE_M
DEFAULT_WATER_LENGTH_SCALE_M = CL_HELPERS.WATER_LENGTH_SCALE_M


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return number


def _normalize_bounds(
    value: dict[str, Any] | None,
    *,
    default: dict[str, tuple[float, float]],
    name: str,
) -> dict[str, tuple[float, float]]:
    if value is None:
        value = default
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError(f"{name} must provide exactly x, y, and z bounds")
    normalized: dict[str, tuple[float, float]] = {}
    for axis in ("x", "y", "z"):
        pair = value[axis]
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f"{name} {axis} bounds must contain two finite numbers")
        lower = _finite_number(pair[0], f"{name} {axis} lower bound")
        upper = _finite_number(pair[1], f"{name} {axis} upper bound")
        if lower >= upper:
            raise ValueError(f"{name} {axis} lower bound must be less than upper bound")
        normalized[axis] = (lower, upper)
    return normalized


def validate_history(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Validate a digitized scalar history in seconds and metres per second."""
    if not isinstance(samples, list) or not samples:
        raise ValueError("Dash-8 source history must be a non-empty list")
    normalized: list[tuple[float, float]] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, (tuple, list)) or len(sample) != 2:
            raise ValueError("each source-history sample must be a (time, speed) pair")
        time_s = _finite_number(sample[0], f"history sample {index} time")
        speed_m_s = _finite_number(sample[1], f"history sample {index} speed")
        if time_s < 0.0 or speed_m_s < 0.0:
            raise ValueError("source-history times and speeds must be nonnegative")
        normalized.append((time_s, speed_m_s))
    if not math.isclose(normalized[0][0], 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Dash-8 history must include its digitized t=0 sample")
    if not math.isclose(normalized[0][1], 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Dash-8 digitized t=0 source speed must be zero")
    if any(left[0] >= right[0] for left, right in zip(normalized, normalized[1:])):
        raise ValueError("source-history times must be strictly increasing")
    return normalized


def read_primary_history(path: Path = PRIMARY_HISTORY_CSV) -> list[tuple[float, float]]:
    """Read the first Dash-8 blue-curve digitization without fitting or filtering."""
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not {"time_s", "u_l_m_s"}.issubset(reader.fieldnames):
            raise ValueError("primary Dash-8 history CSV lacks time_s or u_l_m_s")
        samples = [(float(row["time_s"]), float(row["u_l_m_s"])) for row in reader]
    return validate_history(samples)


def _interpolate_history(samples: list[tuple[float, float]], time_s: float) -> float:
    if time_s < samples[0][0] or time_s > samples[-1][0] + 1e-12:
        raise ValueError("requested time lies outside digitized source-history support")
    for (t0, v0), (t1, v1) in zip(samples, samples[1:]):
        if time_s <= t1:
            fraction = (time_s - t0) / (t1 - t0)
            return v0 + (v1 - v0) * fraction
    return samples[-1][1]


def history_to_horizon(
    samples: list[tuple[float, float]], horizon_s: float
) -> list[tuple[float, float]]:
    """Clip a piecewise-linear history to a supported horizon; never invent a tail."""
    checked = validate_history(samples)
    horizon = _finite_number(horizon_s, "horizon_s", positive=True)
    if horizon > checked[-1][0] + 1e-12:
        raise ValueError(
            f"horizon_s ({horizon:g}) exceeds digitized history support ({checked[-1][0]:g} s); "
            "do not extrapolate a tail or invent a shutoff"
        )
    bounded = [(time_s, speed) for time_s, speed in checked if time_s < horizon]
    bounded.append((horizon, _interpolate_history(checked, horizon)))
    return bounded


def integrate_history(samples: list[tuple[float, float]], horizon_s: float) -> float:
    """Integrate speed exactly for the piecewise-linear curve (distance in metres)."""
    bounded = history_to_horizon(samples, horizon_s)
    return math.fsum(
        (t1 - t0) * (v0 + v1) / 2.0 for (t0, v0), (t1, v1) in zip(bounded, bounded[1:])
    )


def integrate_squared_history(samples: list[tuple[float, float]], horizon_s: float) -> float:
    """Integrate squared speed for the uniform-source momentum impulse diagnostic."""
    bounded = history_to_horizon(samples, horizon_s)
    return math.fsum(
        (t1 - t0) * (v0 * v0 + v0 * v1 + v1 * v1) / 3.0
        for (t0, v0), (t1, v1) in zip(bounded, bounded[1:])
    )


def _validate_profile_controls(
    *,
    source_profile: str,
    profile_amplitude: float,
    profile_seed: int,
    profile_correlation_time_s: float,
    profile_mode: str,
) -> tuple[float, float]:
    if source_profile not in {"uniform", "perturbed", PARABOLIC_MAX_PROFILE}:
        raise ValueError("source_profile must be 'uniform', 'perturbed', or 'parabolic-max'")
    amplitude = _finite_number(profile_amplitude, "profile_amplitude")
    if not 0.0 <= amplitude <= 1.0:
        raise ValueError("profile_amplitude must lie between 0 and 1")
    if isinstance(profile_seed, bool) or not isinstance(profile_seed, int):
        raise ValueError("profile_seed must be an integer")
    if abs(profile_seed) > (2**63 - 1):
        raise ValueError("profile_seed must fit in a signed 64-bit integer")
    correlation_time = _finite_number(
        profile_correlation_time_s, "profile_correlation_time_s", positive=True
    )
    if profile_mode not in SOURCE_PROFILE_MODES:
        raise ValueError("profile_mode must be one of " + ", ".join(sorted(SOURCE_PROFILE_MODES)))
    return amplitude, correlation_time


def _generate_profile_modes(
    *,
    seed: int,
    correlation_time_s: float,
    source_length_m: float,
    source_width_m: float,
    profile_mode: str,
) -> list[dict[str, float]]:
    """Make a fixed, seeded harmonic field; no random numbers are drawn at run time."""
    rng = random.Random(seed)
    inverse_tau_frequency_sd = math.sqrt(2.0) / correlation_time_s
    two_pi = 2.0 * math.pi
    terms: list[dict[str, float]] = []
    for _ in range(PROFILE_MODE_COUNT):
        if profile_mode == "long_wave":
            kx = two_pi / source_length_m * rng.uniform(0.25, 1.0)
            ky = two_pi / source_width_m * rng.uniform(0.0, 0.5) * rng.choice((-1.0, 1.0))
        elif profile_mode == "cross_stream":
            kx = two_pi / source_length_m * rng.uniform(0.0, 0.5)
            ky = two_pi / source_width_m * rng.uniform(0.25, 0.75) * rng.choice((-1.0, 1.0))
        else:
            kx = two_pi / source_length_m * math.exp(rng.uniform(math.log(0.25), math.log(2.0)))
            ky = (
                two_pi
                / source_width_m
                * math.exp(rng.uniform(math.log(0.25), math.log(1.0)))
                * rng.choice((-1.0, 1.0))
            )
        terms.append(
            {
                "kx_rad_m": kx,
                "ky_rad_m": ky,
                "omega_rad_s": rng.gauss(0.0, inverse_tau_frequency_sd),
                "phase_rad": rng.uniform(0.0, two_pi),
                "weight": rng.gauss(0.0, 1.0 / math.sqrt(PROFILE_MODE_COUNT)),
            }
        )
    return terms


def evaluate_perturbed_profile(
    face_centers_m: list[tuple[float, float]],
    face_areas_m2: list[float],
    *,
    mean_speed_m_s: float,
    time_s: float,
    amplitude: float,
    terms: list[dict[str, float]],
) -> list[float]:
    """Evaluate the normalized normal-speed profile at supplied mesh face centers.

    The returned face values are nonnegative and their area-weighted mean equals
    ``mean_speed_m_s``. This mirrors the generated OpenFOAM `codedFixedValue`
    calculation and makes the mesh-face flux correction independently testable.
    """
    if len(face_centers_m) != len(face_areas_m2) or not face_centers_m:
        raise ValueError("face centers and areas must have the same nonzero length")
    mean_speed = _finite_number(mean_speed_m_s, "mean_speed_m_s")
    time_value = _finite_number(time_s, "time_s")
    amplitude_value = _finite_number(amplitude, "amplitude")
    if mean_speed < 0.0 or amplitude_value < 0.0 or amplitude_value > 1.0:
        raise ValueError("mean speed must be nonnegative and amplitude must lie in [0, 1]")
    areas = [
        _finite_number(area, f"face area {index}", positive=True)
        for index, area in enumerate(face_areas_m2)
    ]
    checked_centers: list[tuple[float, float]] = []
    for index, center in enumerate(face_centers_m):
        if not isinstance(center, (tuple, list)) or len(center) != 2:
            raise ValueError(f"face center {index} must provide x and y coordinates")
        checked_centers.append(
            (
                _finite_number(center[0], f"face center {index} x"),
                _finite_number(center[1], f"face center {index} y"),
            )
        )
    raw = [
        math.fsum(
            term["weight"]
            * math.cos(
                term["kx_rad_m"] * x
                + term["ky_rad_m"] * y
                + term["omega_rad_s"] * time_value
                + term["phase_rad"]
            )
            for term in terms
        )
        for x, y in checked_centers
    ]
    area_total = math.fsum(areas)
    raw_mean = math.fsum(area * value for area, value in zip(areas, raw, strict=True)) / area_total
    centered = [value - raw_mean for value in raw]
    peak = max(abs(value) for value in centered)
    if peak == 0.0:
        return [mean_speed] * len(centered)
    return [mean_speed * max(0.0, 1.0 + amplitude_value * value / peak) for value in centered]


def _parabolic_max_shape_values(
    face_centers_m: list[tuple[float, float]],
    face_areas_m2: list[float],
    *,
    center_x_m: float,
    center_y_m: float,
    length_x_m: float,
    width_y_m: float,
) -> tuple[list[float], list[float]]:
    if len(face_centers_m) != len(face_areas_m2) or not face_centers_m:
        raise ValueError("face centers and areas must have the same nonzero length")
    center_x = _finite_number(center_x_m, "center_x_m")
    center_y = _finite_number(center_y_m, "center_y_m")
    length_x = _finite_number(length_x_m, "length_x_m", positive=True)
    width_y = _finite_number(width_y_m, "width_y_m", positive=True)
    checked_areas = [
        _finite_number(area, f"face area {index}", positive=True)
        for index, area in enumerate(face_areas_m2)
    ]
    shape_values: list[float] = []
    for index, center in enumerate(face_centers_m):
        if not isinstance(center, (tuple, list)) or len(center) != 2:
            raise ValueError(f"face center {index} must provide x and y coordinates")
        x_m = _finite_number(center[0], f"face center {index} x")
        y_m = _finite_number(center[1], f"face center {index} y")
        if (
            x_m < center_x - length_x / 2.0 - 1e-10
            or x_m > center_x + length_x / 2.0 + 1e-10
            or y_m < center_y - width_y / 2.0 - 1e-10
            or y_m > center_y + width_y / 2.0 + 1e-10
        ):
            raise ValueError(f"face center {index} lies outside the parabolic source rectangle")
        theta_x = max(0.0, 1.0 - (2.0 * (x_m - center_x) / length_x) ** 2)
        theta_y = max(0.0, 1.0 - (2.0 * (y_m - center_y) / width_y) ** 2)
        shape_values.append(theta_x * theta_y)
    if max(shape_values) <= 0.0:
        raise ValueError("source face centers do not sample positive parabolic profile speed")
    return checked_areas, shape_values


def evaluate_parabolic_max_profile(
    face_centers_m: list[tuple[float, float]],
    face_areas_m2: list[float],
    *,
    maximum_speed_m_s: float,
    center_x_m: float,
    center_y_m: float,
    length_x_m: float,
    width_y_m: float,
) -> list[float]:
    """Sample a stationary separable parabolic shape against the continuous max speed.

    The continuous shape peaks at the source center. Face-center sampling is not
    renormalized, so its sampled maximum and area moments depend on mesh spacing.
    """
    maximum_speed = _finite_number(maximum_speed_m_s, "maximum_speed_m_s")
    if maximum_speed < 0.0:
        raise ValueError("maximum_speed_m_s must be nonnegative")
    _, shape_values = _parabolic_max_shape_values(
        face_centers_m,
        face_areas_m2,
        center_x_m=center_x_m,
        center_y_m=center_y_m,
        length_x_m=length_x_m,
        width_y_m=width_y_m,
    )
    return [maximum_speed * shape for shape in shape_values]


def parabolic_max_profile_moment_factors(
    face_centers_m: list[tuple[float, float]],
    face_areas_m2: list[float],
    *,
    center_x_m: float,
    center_y_m: float,
    length_x_m: float,
    width_y_m: float,
) -> dict[str, float | int]:
    """Return actual face-center quadrature factors for volume and momentum flux."""
    areas, shape_values = _parabolic_max_shape_values(
        face_centers_m,
        face_areas_m2,
        center_x_m=center_x_m,
        center_y_m=center_y_m,
        length_x_m=length_x_m,
        width_y_m=width_y_m,
    )
    area_total = math.fsum(areas)
    return {
        "source_face_area_m2": area_total,
        "source_face_count": len(areas),
        "sampled_maximum_shape_factor": max(shape_values),
        "discrete_volume_factor_f1": math.fsum(
            area * shape for area, shape in zip(areas, shape_values, strict=True)
        )
        / area_total,
        "discrete_momentum_factor_f2": math.fsum(
            area * shape * shape for area, shape in zip(areas, shape_values, strict=True)
        )
        / area_total,
    }


def _source_face_centers_and_areas(
    source: dict[str, Any], mesh_details: dict[str, Any]
) -> tuple[list[tuple[float, float]], list[float]]:
    centers_by_axis: dict[str, list[tuple[float, float]]] = {}
    for axis in ("x", "y"):
        lower, upper = source["bounds_m"][axis]
        breaks = mesh_details["mesh_breaks_m"][axis]
        counts = mesh_details["mesh_cells_per_segment"][axis]
        centers_and_widths: list[tuple[float, float]] = []
        for start, end, count in zip(breaks[:-1], breaks[1:], counts, strict=True):
            overlaps_source = start < upper - 1e-10 and end > lower + 1e-10
            lies_in_source = start >= lower - 1e-10 and end <= upper + 1e-10
            if overlaps_source and not lies_in_source:
                raise ValueError(f"source boundary does not align with the generated {axis} mesh")
            if lies_in_source:
                cell_width = (end - start) / count
                centers_and_widths.extend(
                    (start + (index + 0.5) * cell_width, cell_width) for index in range(count)
                )
        if not centers_and_widths:
            raise ValueError(f"generated mesh has no source-face centers along {axis}")
        centers_by_axis[axis] = centers_and_widths

    face_centers = [
        (x_center, y_center)
        for x_center, _ in centers_by_axis["x"]
        for y_center, _ in centers_by_axis["y"]
    ]
    face_areas = [
        x_width * y_width
        for _, x_width in centers_by_axis["x"]
        for _, y_width in centers_by_axis["y"]
    ]
    if len(face_centers) != mesh_details["source_patch_face_counts"][source["name"]]:
        raise ValueError("source face quadrature does not match generated mesh face count")
    if not math.isclose(math.fsum(face_areas), source["area_m2"], rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("source face quadrature does not cover the declared source area")
    return face_centers, face_areas


def _cpp_scalar(value: float) -> str:
    return "0" if value == 0.0 else f"{value:.17g}"


def _coded_profile_boundary(
    *,
    history: list[tuple[float, float]],
    terms: list[dict[str, float]],
    amplitude: float,
    center_x_m: float,
    center_y_m: float,
) -> str:
    """Generate a time-continuous boundary using the actual OpenFOAM face centers."""
    arrays = {
        name: ", ".join(_cpp_scalar(term[key]) for term in terms)
        for name, key in (
            ("modeKx", "kx_rad_m"),
            ("modeKy", "ky_rad_m"),
            ("modeOmega", "omega_rad_s"),
            ("modePhase", "phase_rad"),
            ("modeWeight", "weight"),
        )
    }
    history_times = ", ".join(_cpp_scalar(time_s) for time_s, _ in history)
    history_speeds = ", ".join(_cpp_scalar(speed) for _, speed in history)
    return f"""        type codedFixedValue;
        name dash8SeededNormalProfile;
        value uniform (0 0 0);
        codeInclude
        #{{
            #include "fvCFD.H"
        #}};
        code
        #{{
            const scalar sourceTimes[] = {{{history_times}}};
            const scalar sourceSpeeds[] = {{{history_speeds}}};
            const scalar modeKx[] = {{{arrays["modeKx"]}}};
            const scalar modeKy[] = {{{arrays["modeKy"]}}};
            const scalar modeOmega[] = {{{arrays["modeOmega"]}}};
            const scalar modePhase[] = {{{arrays["modePhase"]}}};
            const scalar modeWeight[] = {{{arrays["modeWeight"]}}};
            const label nSourceSamples = sizeof(sourceTimes)/sizeof(sourceTimes[0]);
            const label nModes = sizeof(modeKx)/sizeof(modeKx[0]);
            const scalar currentTime = this->db().time().value();
            scalar sourceSpeed = sourceSpeeds[nSourceSamples - 1];
            for (label i = 1; i < nSourceSamples; ++i)
            {{
                if (currentTime <= sourceTimes[i])
                {{
                    const scalar fraction =
                        (currentTime - sourceTimes[i - 1])
                       /(sourceTimes[i] - sourceTimes[i - 1]);
                    sourceSpeed = sourceSpeeds[i - 1]
                        + fraction*(sourceSpeeds[i] - sourceSpeeds[i - 1]);
                    break;
                }}
            }}

            const vectorField& faceCenters = this->patch().Cf();
            const scalarField& faceAreas = this->patch().magSf();
            scalarField rawField(this->size(), 0.0);
            scalar localArea = 0.0;
            scalar localRawAreaSum = 0.0;
            forAll(rawField, facei)
            {{
                const scalar x = faceCenters[facei].x() - {_cpp_scalar(center_x_m)};
                const scalar y = faceCenters[facei].y() - {_cpp_scalar(center_y_m)};
                scalar rawValue = 0.0;
                for (label modei = 0; modei < nModes; ++modei)
                {{
                    rawValue += modeWeight[modei]*Foam::cos
                    (
                        modeKx[modei]*x + modeKy[modei]*y
                      + modeOmega[modei]*currentTime + modePhase[modei]
                    );
                }}
                rawField[facei] = rawValue;
                localArea += faceAreas[facei];
                localRawAreaSum += faceAreas[facei]*rawValue;
            }}
            const scalar globalArea = returnReduce(localArea, sumOp<scalar>());
            const scalar rawMean =
                returnReduce(localRawAreaSum, sumOp<scalar>())/globalArea;
            scalar localPeakDeviation = 0.0;
            forAll(rawField, facei)
            {{
                localPeakDeviation = max
                (
                    localPeakDeviation,
                    mag(rawField[facei] - rawMean)
                );
            }}
            const scalar peakDeviation =
                returnReduce(localPeakDeviation, maxOp<scalar>());
            const scalar safePeak = max(peakDeviation, VSMALL);
            vectorField profileValues(this->size(), vector::zero);
            scalar localVolumeFlux = 0.0;
            scalar localMomentumFlux = 0.0;
            forAll(profileValues, facei)
            {{
                const scalar centered = rawField[facei] - rawMean;
                const scalar modulation =
                    {_cpp_scalar(amplitude)}*centered/safePeak;
                const scalar normalSpeed = sourceSpeed*max(scalar(0), scalar(1) + modulation);
                profileValues[facei] = vector(0, 0, -normalSpeed);
                localVolumeFlux += faceAreas[facei]*normalSpeed;
                localMomentumFlux += faceAreas[facei]*normalSpeed*normalSpeed;
            }}
            const scalar volumeFlux = returnReduce(localVolumeFlux, sumOp<scalar>());
            const scalar momentumFlux = {_cpp_scalar(WATER_RHO_KG_M3)}
                *returnReduce(localMomentumFlux, sumOp<scalar>());
            const scalar meanNormalSpeed = volumeFlux/globalArea;
            const scalar uniformMomentumFlux =
                {_cpp_scalar(WATER_RHO_KG_M3)}*globalArea*sourceSpeed*sourceSpeed;
            const scalar momentumRatio =
                uniformMomentumFlux > VSMALL ? momentumFlux/uniformMomentumFlux : 1.0;
            static scalar lastLoggedTime = -GREAT;
            const label localFaceCount = this->patch().size();
            const label globalFaceCount = returnReduce(localFaceCount, sumOp<label>());
            if (Pstream::master())
            {{
                if (currentTime > lastLoggedTime + SMALL)
                {{
                    lastLoggedTime = currentTime;
                    Info<< "DASH8_PROFILE t_s=" << currentTime
                        << " history_speed_m_s=" << sourceSpeed
                        << " source_area_m2=" << globalArea
                        << " source_patch=" << this->patch().name()
                        << " source_faces=" << globalFaceCount
                        << " area_mean_normal_speed_m_s=" << meanNormalSpeed
                        << " water_mass_flow_kg_s="
                        << {_cpp_scalar(WATER_RHO_KG_M3)}*volumeFlux
                        << " normal_momentum_flux_N=" << momentumFlux
                        << " uniform_momentum_ratio=" << momentumRatio << nl;
                }}
            }}
            operator==(profileValues);
        #}};
"""


def _coded_parabolic_max_boundary(
    *,
    history: list[tuple[float, float]],
    center_x_m: float,
    center_y_m: float,
    length_x_m: float,
    width_y_m: float,
) -> str:
    """Generate a fixed shape whose continuous center maximum follows the history."""
    history_times = ", ".join(_cpp_scalar(time_s) for time_s, _ in history)
    history_maximum_speeds = ", ".join(_cpp_scalar(speed) for _, speed in history)
    return f"""        type codedFixedValue;
        name dash8ParabolicMaximumProfile;
        value uniform (0 0 0);
        codeInclude
        #{{
            #include "fvCFD.H"
        #}};
        code
        #{{
            const scalar sourceTimes[] = {{{history_times}}};
            const scalar sourceMaximumSpeeds[] = {{{history_maximum_speeds}}};
            const label nSourceSamples = sizeof(sourceTimes)/sizeof(sourceTimes[0]);
            const scalar currentTime = this->db().time().value();
            scalar historyMaximumSpeed = sourceMaximumSpeeds[nSourceSamples - 1];
            for (label i = 1; i < nSourceSamples; ++i)
            {{
                if (currentTime <= sourceTimes[i])
                {{
                    const scalar fraction =
                        (currentTime - sourceTimes[i - 1])
                       /(sourceTimes[i] - sourceTimes[i - 1]);
                    historyMaximumSpeed = sourceMaximumSpeeds[i - 1]
                        + fraction*(sourceMaximumSpeeds[i] - sourceMaximumSpeeds[i - 1]);
                    break;
                }}
            }}

            const vectorField& faceCenters = this->patch().Cf();
            const scalarField& faceAreas = this->patch().magSf();
            scalarField shapeValues(this->size(), 0.0);
            scalar localArea = 0.0;
            scalar localPeakShapeFactor = 0.0;
            scalar localAreaShapeSum = 0.0;
            scalar localAreaShapeSquaredSum = 0.0;
            forAll(shapeValues, facei)
            {{
                const scalar xCoordinate = faceCenters[facei].x();
                const scalar yCoordinate = faceCenters[facei].y();
                const scalar xNormalized =
                    2.0*(xCoordinate - {_cpp_scalar(center_x_m)})
                   /{_cpp_scalar(length_x_m)};
                const scalar yNormalized =
                    2.0*(yCoordinate - {_cpp_scalar(center_y_m)})
                   /{_cpp_scalar(width_y_m)};
                const scalar thetaX = max(scalar(0), scalar(1) - xNormalized*xNormalized);
                const scalar thetaY = max(scalar(0), scalar(1) - yNormalized*yNormalized);
                const scalar shape = thetaX*thetaY;
                shapeValues[facei] = shape;
                localArea += faceAreas[facei];
                localPeakShapeFactor = max(localPeakShapeFactor, shape);
                localAreaShapeSum += faceAreas[facei]*shape;
                localAreaShapeSquaredSum += faceAreas[facei]*shape*shape;
            }}

            // Every rank, including ranks with an empty source patch, participates.
            const scalar globalArea = returnReduce(localArea, sumOp<scalar>());
            const scalar globalPeakShapeFactor =
                returnReduce(localPeakShapeFactor, maxOp<scalar>());
            const scalar globalAreaShapeSum =
                returnReduce(localAreaShapeSum, sumOp<scalar>());
            const scalar globalAreaShapeSquaredSum =
                returnReduce(localAreaShapeSquaredSum, sumOp<scalar>());
            const scalar volumeFactorF1 = globalAreaShapeSum/globalArea;
            const scalar momentumFactorF2 = globalAreaShapeSquaredSum/globalArea;

            vectorField profileValues(this->size(), vector::zero);
            scalar localVolumeFlux = 0.0;
            scalar localMomentumFlux = 0.0;
            scalar localSampledMaximumSpeed = 0.0;
            forAll(profileValues, facei)
            {{
                const scalar normalSpeed = historyMaximumSpeed*shapeValues[facei];
                profileValues[facei] = vector(0, 0, -normalSpeed);
                localVolumeFlux += faceAreas[facei]*normalSpeed;
                localMomentumFlux += faceAreas[facei]*normalSpeed*normalSpeed;
                localSampledMaximumSpeed = max(localSampledMaximumSpeed, normalSpeed);
            }}
            const scalar volumeFlow = returnReduce(localVolumeFlux, sumOp<scalar>());
            const scalar momentumFlow = {_cpp_scalar(WATER_RHO_KG_M3)}
                *returnReduce(localMomentumFlux, sumOp<scalar>());
            const scalar sampledMaximumSpeed =
                returnReduce(localSampledMaximumSpeed, maxOp<scalar>());
            const label localFaceCount = this->patch().size();
            const label globalFaceCount = returnReduce(localFaceCount, sumOp<label>());
            static scalar lastLoggedTime = -GREAT;
            if (Pstream::master())
            {{
                if (currentTime > lastLoggedTime + SMALL)
                {{
                    lastLoggedTime = currentTime;
                    Info<< "DASH8_PROFILE t_s=" << currentTime
                        << " source_patch=" << this->patch().name()
                        << " source_faces=" << globalFaceCount
                        << " source_area_m2=" << globalArea
                        << " history_maximum_speed_m_s=" << historyMaximumSpeed
                        << " sampled_maximum_shape_factor=" << globalPeakShapeFactor
                        << " sampled_maximum_normal_speed_m_s=" << sampledMaximumSpeed
                        << " area_mean_normal_speed_m_s=" << volumeFactorF1*historyMaximumSpeed
                        << " area_mean_shape_factor_F1=" << volumeFactorF1
                        << " area_mean_squared_shape_factor_F2=" << momentumFactorF2
                        << " prescribed_volume_flow_m3_s=" << volumeFlow
                        << " prescribed_mass_flow_kg_s="
                        << {_cpp_scalar(WATER_RHO_KG_M3)}*volumeFlow
                        << " normal_momentum_flux_N=" << momentumFlow
                        << " momentum_flux_ratio_to_uniform_max_reference="
                        << momentumFactorF2 << nl;
                }}
            }}
            operator==(profileValues);
        #}};
"""


def _make_source(
    *, length_m: float, width_m: float, plane_z_m: float, domain: dict[str, tuple[float, float]]
) -> dict[str, Any]:
    x_bounds = (-length_m / 2.0, length_m / 2.0)
    y_bounds = (-width_m / 2.0, width_m / 2.0)
    if x_bounds[0] < domain["x"][0] or x_bounds[1] > domain["x"][1]:
        raise ValueError("the single Dash-8 outlet lies outside the x domain")
    if y_bounds[0] < domain["y"][0] or y_bounds[1] > domain["y"][1]:
        raise ValueError("the single Dash-8 outlet lies outside the y domain")
    if not math.isclose(plane_z_m, domain["z"][1], rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("the single opening must lie on the flat top source plane")
    return {
        "name": SOURCE_NAME,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "length_x_m": length_m,
        "width_y_m": width_m,
        "area_m2": length_m * width_m,
        "direction_unit": [0.0, 0.0, -1.0],
        "history": HISTORY_NAME,
        "plane_z_m": plane_z_m,
        "bounds_m": {"x": list(x_bounds), "y": list(y_bounds)},
    }


def _git_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()
        dirty_lines = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}
    return {"revision": revision, "dirty": bool(dirty_lines)}


def prepare_case(
    output: Path,
    *,
    horizon_s: float = 5.0,
    ranks: int = 20,
    snapshot_interval_s: float = 0.1,
    spacing_m: float = 0.1,
    coarse_spacing_m: float = 0.4,
    source_length_m: float = DEFAULT_SOURCE_LENGTH_M,
    source_width_m: float = DEFAULT_SOURCE_WIDTH_M,
    source_profile: str = "uniform",
    profile_amplitude: float = DEFAULT_PROFILE_AMPLITUDE,
    profile_seed: int = DEFAULT_PROFILE_SEED,
    profile_correlation_time_s: float = DEFAULT_PROFILE_CORRELATION_TIME_S,
    profile_mode: str = "long_wave",
    turbulence_linear_solver: str = "gauss-seidel",
    air_turbulence_intensity: float = DEFAULT_TURBULENCE_INTENSITY,
    water_turbulence_intensity: float = DEFAULT_TURBULENCE_INTENSITY,
    air_length_scale_m: float = DEFAULT_AIR_LENGTH_SCALE_M,
    water_length_scale_m: float = DEFAULT_WATER_LENGTH_SCALE_M,
    domain_bounds_m: dict[str, tuple[float, float]] | None = None,
    refinement_region: dict[str, tuple[float, float]] | None = None,
    inner_refinement_region: dict[str, tuple[float, float]] | None = None,
    inner_spacing_m: float | None = None,
) -> dict[str, Any]:
    """Create a new case after validating source, history, domain, mesh and ranks."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output directory already exists; preserving it: {output}")
    if turbulence_linear_solver not in {"gauss-seidel", "pbicgstab"}:
        raise ValueError("turbulence_linear_solver must be gauss-seidel or pbicgstab")

    air_intensity = _finite_number(
        air_turbulence_intensity, "air_turbulence_intensity", positive=True
    )
    water_intensity = _finite_number(
        water_turbulence_intensity, "water_turbulence_intensity", positive=True
    )
    air_length_scale = _finite_number(air_length_scale_m, "air_length_scale_m", positive=True)
    water_length_scale = _finite_number(water_length_scale_m, "water_length_scale_m", positive=True)
    if air_intensity > 1.0:
        raise ValueError("air_turbulence_intensity must be no greater than 1.0")
    if water_intensity > 1.0:
        raise ValueError("water_turbulence_intensity must be no greater than 1.0")

    horizon = _finite_number(horizon_s, "horizon_s", positive=True)
    if horizon > MAX_HISTORY_HORIZON_S + 1e-12:
        raise ValueError(
            f"horizon_s ({horizon:g}) exceeds primary and independent CSV support "
            f"({MAX_HISTORY_HORIZON_S:g} s); do not invent a tail"
        )
    if isinstance(ranks, bool) or not isinstance(ranks, int) or ranks < 1:
        raise ValueError("ranks must be a positive integer")
    spacing = _finite_number(spacing_m, "spacing_m", positive=True)
    coarse_spacing = _finite_number(coarse_spacing_m, "coarse_spacing_m", positive=True)
    if coarse_spacing < spacing:
        raise ValueError("coarse_spacing_m must be no smaller than spacing_m")
    snapshot = _finite_number(snapshot_interval_s, "snapshot_interval_s", positive=True)
    source_length = _finite_number(source_length_m, "source_length_m", positive=True)
    source_width = _finite_number(source_width_m, "source_width_m", positive=True)
    amplitude, correlation_time = _validate_profile_controls(
        source_profile=source_profile,
        profile_amplitude=profile_amplitude,
        profile_seed=profile_seed,
        profile_correlation_time_s=profile_correlation_time_s,
        profile_mode=profile_mode,
    )
    domain = _normalize_bounds(
        domain_bounds_m,
        default=DEFAULT_DOMAIN_BOUNDS_M,
        name="domain_bounds_m",
    )
    refinement = _normalize_bounds(
        refinement_region,
        default=DEFAULT_REFINEMENT_REGION_M,
        name="refinement_region",
    )
    if not domain["x"][0] <= 0.0 <= domain["x"][1]:
        raise ValueError("the source-centered coordinate origin must lie in the x domain")
    if not domain["y"][0] <= 0.0 <= domain["y"][1]:
        raise ValueError("the source-centered coordinate origin must lie in the y domain")

    history = read_primary_history()
    if not math.isclose(history[-1][0], MAX_HISTORY_HORIZON_S, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("primary Dash-8 history support changed from the declared 5.0 s")
    bounded_history = history_to_horizon(history, horizon)
    plane_z = domain["z"][1]
    source = _make_source(
        length_m=source_length,
        width_m=source_width,
        plane_z_m=plane_z,
        domain=domain,
    )
    profile_terms = (
        _generate_profile_modes(
            seed=profile_seed,
            correlation_time_s=correlation_time,
            source_length_m=source_length,
            source_width_m=source_width,
            profile_mode=profile_mode,
        )
        if source_profile == "perturbed"
        else []
    )
    sources = [source]

    # Generate and validate the complete mesh before creating any output path.
    mesh_text, mesh_details = CL_HELPERS.block_mesh_dict(
        domain=domain,
        sources=sources,
        spacing_m=spacing,
        coarse_spacing_m=coarse_spacing,
        refinement_region=refinement,
        inner_refinement_region=inner_refinement_region,
        inner_spacing_m=inner_spacing_m,
    )
    expected_area = source_length * source_width
    patch_area = mesh_details["source_patch_areas_m2"][SOURCE_NAME]
    if not math.isclose(patch_area, expected_area, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError(
            f"generated opening faces cover {patch_area:g} m^2, expected {expected_area:g} m^2"
        )
    if ranks > int(mesh_details["mesh_shape"]["x"]):
        raise ValueError(
            f"ranks ({ranks}) must not exceed x-direction cell count "
            f"({mesh_details['mesh_shape']['x']})"
        )
    parabolic_moments: dict[str, float | int] | None = None
    if source_profile == PARABOLIC_MAX_PROFILE:
        source_face_centers, source_face_areas = _source_face_centers_and_areas(
            source, mesh_details
        )
        parabolic_moments = parabolic_max_profile_moment_factors(
            source_face_centers,
            source_face_areas,
            center_x_m=source["center_x_m"],
            center_y_m=source["center_y_m"],
            length_x_m=source_length,
            width_y_m=source_width,
        )
        if not math.isclose(
            parabolic_moments["source_face_area_m2"], expected_area, rel_tol=0.0, abs_tol=1e-10
        ):
            raise ValueError("parabolic source-profile quadrature does not conserve source area")

    source_origin = [0.0, 0.0, plane_z]
    domain_json = {axis: list(domain[axis]) for axis in ("x", "y", "z")}
    refinement_json = {axis: list(refinement[axis]) for axis in ("x", "y", "z")}
    mesh_details.update(
        {
            "domain_bounds_m": domain_json,
            "local_spacing_m": spacing,
            "coarse_spacing_m": coarse_spacing,
            "refinement_region_m": refinement_json,
        }
    )
    if inner_refinement_region is not None:
        source_refinement = {
            "region_m": mesh_details["inner_refinement_region_m"],
            "target_spacing_m": mesh_details["inner_spacing_m"],
            "actual_segment_widths_by_axis_m": mesh_details["mesh_widths_by_segment_m"],
            "mesh_cells_expected": mesh_details["mesh_cells_expected"],
            "source_patch_face_count": mesh_details["source_patch_face_counts"][SOURCE_NAME],
            "source_patch_macro_face_count": mesh_details["source_patch_macro_face_counts"][
                SOURCE_NAME
            ],
            "source_patch_area_m2": mesh_details["source_patch_areas_m2"][SOURCE_NAME],
            "mesh_interpretation": mesh_details["mesh_refinement_interpretation"],
        }
        mesh_details["source_refinement"] = source_refinement

    # All value validation is complete; preserve partial writes as evidence if I/O fails.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    for directory in ("0", "constant", "system"):
        (output / directory).mkdir()
    (output / "system" / "blockMeshDict").write_text(mesh_text, encoding="utf-8")

    histories = {HISTORY_NAME: bounded_history}
    turbulence_values = CL_HELPERS._write_fields(
        output,
        sources,
        histories,
        air_turbulence_intensity=air_intensity,
        water_turbulence_intensity=water_intensity,
        air_length_scale_m=air_length_scale,
        water_length_scale_m=water_length_scale,
    )
    if source_profile in {"perturbed", PARABOLIC_MAX_PROFILE}:
        u_field_path = output / "0" / "U"
        u_field = u_field_path.read_text(encoding="utf-8")
        uniform_boundary = CL_HELPERS._history_boundary(source, bounded_history)
        if source_profile == "perturbed":
            profiled_boundary = _coded_profile_boundary(
                history=bounded_history,
                terms=profile_terms,
                amplitude=amplitude,
                center_x_m=source["center_x_m"],
                center_y_m=source["center_y_m"],
            )
        else:
            profiled_boundary = _coded_parabolic_max_boundary(
                history=bounded_history,
                center_x_m=source["center_x_m"],
                center_y_m=source["center_y_m"],
                length_x_m=source_length,
                width_y_m=source_width,
            )
        if u_field.count(uniform_boundary) != 1:
            raise ValueError("could not locate the generated uniform Dash-8 U boundary")
        u_field_path.write_text(
            u_field.replace(uniform_boundary, profiled_boundary), encoding="utf-8"
        )
    patch_names = [SOURCE_NAME, *OPEN_PATCHES]
    delta_t_s = CL_HELPERS._write_dictionaries(
        output,
        horizon_s=horizon,
        mesh_details=mesh_details,
        ranks=ranks,
        patches=patch_names,
        snapshot_interval_s=snapshot,
    )
    if turbulence_linear_solver == "pbicgstab":
        solution_path = output / "system/fvSolution"
        solution = solution_path.read_text()
        for key, relative_tolerance in (("(k|epsilon)", "0.1"), ("(k|epsilon)Final", "0")):
            old = (
                f'"{key}" {{ solver smoothSolver; smoother GaussSeidel; '
                f"tolerance 1e-8; relTol {relative_tolerance}; }}"
            )
            new = (
                f'"{key}" {{ solver PBiCGStab; preconditioner DILU; '
                "tolerance 1e-8; relTol 0; maxIter 100; }"
            )
            if solution.count(old) != 1:
                raise ValueError(f"expected exactly one generated {key} solver entry")
            solution = solution.replace(old, new)
        solution_path.write_text(solution)

    default_dimensions = (
        source_length == DEFAULT_SOURCE_LENGTH_M and source_width == DEFAULT_SOURCE_WIDTH_M
    )
    geometry_evidence = (
        "provisional figure-derived candidate inference: Fig. 2 labels 4.44 m for the "
        "narrow lower section and 0.30 m for a bottom projection; the article does not "
        "identify these labels as aperture dimensions or report exit area"
        if default_dimensions
        else "provisional alternative dimensions supplied for this experiment; "
        "these dimensions are not reported or measured in the paper"
    )
    geometry = {
        "schema_version": 1,
        "source_origin_m": source_origin,
        "source_plane_z_m": plane_z,
        "geometry_evidence": geometry_evidence,
        "unused_figure_dimension_note": (
            "Fig. 2 also shows a 0.10 m bottom feature; it is not interpreted as an aperture gap"
        ),
        "sources": [
            {
                key: value
                for key, value in source.items()
                if key not in {"direction_unit", "history"}
            }
            | {
                "discharge_direction_unit": source["direction_unit"],
                "history": source["history"],
            }
        ],
    }
    geometry_path = output / "source_geometry.json"
    geometry_path.write_text(
        json.dumps(geometry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    source_dir = output / "source"
    source_dir.mkdir()
    source_paths = {
        "fig4_primary_csv": PRIMARY_HISTORY_CSV,
        "fig4_independent_csv": INDEPENDENT_HISTORY_CSV,
        "e2_source_record": SOURCE_RECORD,
    }
    for source_path in source_paths.values():
        (source_dir / source_path.name).write_bytes(source_path.read_bytes())

    integrated_speed_m = integrate_history(history, horizon)
    integrated_speed_squared_m2_s = integrate_squared_history(history, horizon)
    profile_volume_factor = (
        parabolic_moments["discrete_volume_factor_f1"] if parabolic_moments is not None else 1.0
    )
    profile_momentum_factor = (
        parabolic_moments["discrete_momentum_factor_f2"] if parabolic_moments is not None else 1.0
    )
    analytic_volume_m3 = expected_area * profile_volume_factor * integrated_speed_m
    analytic_mass_kg = WATER_RHO_KG_M3 * analytic_volume_m3
    analytic_momentum_impulse_n_s = (
        WATER_RHO_KG_M3 * expected_area * profile_momentum_factor * integrated_speed_squared_m2_s
    )
    uniform_reference_momentum_impulse = [
        0.0,
        0.0,
        -WATER_RHO_KG_M3 * expected_area * integrated_speed_squared_m2_s,
    ]
    profiled_momentum_impulse = [0.0, 0.0, -analytic_momentum_impulse_n_s]
    analytic_momentum_impulse = (
        profiled_momentum_impulse if source_profile in {"uniform", PARABOLIC_MAX_PROFILE} else None
    )
    per_source_row = {
        "source_area_m2": expected_area,
        "integral_speed_m": integrated_speed_m,
        "integral_speed_squared_m2_s": integrated_speed_squared_m2_s,
        "analytic_expected_volume_m3": analytic_volume_m3,
        "analytic_expected_mass_kg": analytic_mass_kg,
        "analytic_expected_momentum_impulse_N_s": analytic_momentum_impulse,
        "uniform_reference_momentum_impulse_N_s": uniform_reference_momentum_impulse,
        "profile_momentum_impulse_status": (
            "exact for the uniform profile"
            if source_profile == "uniform"
            else "exact for the stationary face-center-sampled parabolic profile"
            if source_profile == PARABOLIC_MAX_PROFILE
            else "not analytically evaluated; integrate actual runtime boundary flux diagnostics"
        ),
    }
    if parabolic_moments is not None:
        per_source_row.update(
            {
                "face_center_sampled_volume_factor_F1": profile_volume_factor,
                "face_center_sampled_momentum_factor_F2": profile_momentum_factor,
            }
        )
    per_source = {SOURCE_NAME: per_source_row}
    input_hashes = {
        "fig4_primary_csv_sha256": CL_HELPERS.sha256(PRIMARY_HISTORY_CSV),
        "fig4_independent_csv_sha256": CL_HELPERS.sha256(INDEPENDENT_HISTORY_CSV),
        "e2_source_record_sha256": CL_HELPERS.sha256(SOURCE_RECORD),
        "cl415_helper_module_sha256": CL_HELPERS.sha256(CL415_HELPERS_PATH),
        "prepare_case_sha256": CL_HELPERS.sha256(Path(__file__)),
        "source_geometry_sha256": CL_HELPERS.sha256(geometry_path),
    }
    if inner_refinement_region is not None:
        mesh_hash = CL_HELPERS.sha256(output / "system" / "blockMeshDict")
        input_hashes["block_mesh_dict_sha256"] = mesh_hash
        mesh_details["source_refinement"]["block_mesh_dict_sha256"] = mesh_hash
    effective_snapshot_interval = min(snapshot, horizon)
    if source_profile == "perturbed":
        profile_boundary = (
            "OpenFOAM v2512 codedFixedValue, compiled at runtime inside the pinned image"
        )
        profile_momentum_note = (
            "The uniform-profile impulse retained as a reference is not the perturbed result. "
            "The coded boundary logs the actual area-integrated normal momentum flux and its "
            "ratio to the uniform reference at every boundary update. Integrate the logged "
            "values over solver time for the realized profile impulse."
        )
    elif source_profile == PARABOLIC_MAX_PROFILE:
        profile_boundary = (
            "OpenFOAM v2512 codedFixedValue, compiled at runtime; stationary continuous "
            "parabolic maximum profile sampled at source-face centers"
        )
        profile_momentum_note = (
            "This assumed stationary shape intentionally changes release mass and momentum "
            "relative to the uniform inlet. The continuous shape maximum follows Figure 4; "
            "finite face-center samples determine the discrete flux factors recorded below."
        )
    else:
        profile_boundary = "legacy uniformFixedValue table; no runtime code"
        profile_momentum_note = (
            "The source is uniform over its mesh faces, so the analytic momentum impulse is "
            "exact for this prescribed area and scalar history."
        )
    peak_source_speed = max(speed for _, speed in bounded_history)
    peak_source_time_s = max(bounded_history, key=lambda sample: sample[1])[0]
    peak_source_k, peak_source_epsilon = CL_HELPERS._turbulence_values(
        peak_source_speed, water_length_scale, water_intensity
    )
    turbulence_peak_metadata = (
        {
            "peak_digitized_source_maximum_speed_m_s": peak_source_speed,
            "source_k_at_peak_digitized_maximum_speed_m2_s2": peak_source_k,
            "source_epsilon_at_peak_digitized_maximum_speed_m2_s3": peak_source_epsilon,
        }
        if source_profile == PARABOLIC_MAX_PROFILE
        else {
            "peak_digitized_source_mean_speed_m_s": peak_source_speed,
            "source_k_at_peak_digitized_mean_speed_m2_s2": peak_source_k,
            "source_epsilon_at_peak_digitized_mean_speed_m2_s3": peak_source_epsilon,
        }
    )
    if parabolic_moments is not None:
        assert source_profile == PARABOLIC_MAX_PROFILE
        air_density_assumption = 1.2
        q_denominator = air_density_assumption * AIR_SPEED_M_S**2
        sampled_maximum_factor = parabolic_moments["sampled_maximum_shape_factor"]
        volume_factor_f1 = parabolic_moments["discrete_volume_factor_f1"]
        momentum_factor_f2 = parabolic_moments["discrete_momentum_factor_f2"]

        def q_factors_at_history_speed(history_speed_m_s: float) -> dict[str, float]:
            nominal_maximum_q = WATER_RHO_KG_M3 * history_speed_m_s**2 / q_denominator
            return {
                "history_maximum_speed_m_s": history_speed_m_s,
                "nominal_continuous_maximum_q": nominal_maximum_q,
                "sampled_maximum_speed_m_s": history_speed_m_s * sampled_maximum_factor,
                "sampled_maximum_q": nominal_maximum_q * sampled_maximum_factor**2,
                "area_mean_speed_m_s": history_speed_m_s * volume_factor_f1,
                "area_mean_speed_q": nominal_maximum_q * volume_factor_f1**2,
                "momentum_equivalent_q": nominal_maximum_q * momentum_factor_f2,
            }

        q_at_05_speed = _interpolate_history(history, 0.5)
        parabolic_profile_diagnostics = {
            "spatial_shape": (
                "theta(x,y)=max(0,1-(2*(x-x0)/L)^2)*max(0,1-(2*(y-y0)/W)^2); "
                "U_normal=U_L(t)*theta, where the continuous maximum theta=1 at (x0,y0)"
            ),
            "continuous_volume_factor_f1": 4.0 / 9.0,
            "continuous_momentum_factor_f2": (8.0 / 15.0) ** 2,
            "discrete_face_center_moments": parabolic_moments,
            "normal_speed_uses_continuous_shape_without_discrete_max_renormalization": True,
            "nominal_history_maximum_is_not_required_to_equal_sampled_face_maximum": True,
            "q_definition": (
                "rho_water*speed^2/(rho_air*U_G^2); air density 1.2 kg/m^3 is assumed. "
                "area_mean_speed_q is q evaluated at the area-mean speed, not the area mean "
                "of local q; momentum_equivalent_q is q_nominal multiplied by F2 and reports "
                "the momentum-flux ratio to a uniform inlet at the continuous maximum speed."
            ),
            "q_at_digitized_0p5_s": {
                "time_s": 0.5,
                "within_case_horizon": horizon >= 0.5,
                **q_factors_at_history_speed(q_at_05_speed),
            },
            "q_at_peak_of_simulated_history": {
                "time_s": peak_source_time_s,
                **q_factors_at_history_speed(peak_source_speed),
            },
            "uniform_source_q_acceptance_note": (
                "The nominal maximum q, finite-mesh sampled-maximum q, area-mean-speed q, and "
                "momentum-equivalent q are distinct for this profile; a uniform-source q value "
                "must not be assigned to this candidate without stating which definition is used."
            ),
        }
        inlet_profile = {
            "kind": PARABOLIC_MAX_PROFILE,
            "interpretation": (
                "assumed stationary spatial profile interpreting the digitized Figure 4 scalar "
                "as the continuous maximum normal speed"
            ),
            "source_history_interpretation": (
                "maximum-speed hypothesis; PDF p. 3 defines U_L=Q_L/S as mean, while PDF p. 5 "
                "Fig. 4 caption and adjacent Results text call U_L(t) maximum velocity"
            ),
            "boundary_condition": profile_boundary,
            **parabolic_profile_diagnostics,
            "instantaneous_continuous_maximum_speed_matches_history": True,
            "instantaneous_sampled_maximum_speed_ratio_to_history": sampled_maximum_factor,
            "instantaneous_area_mean_speed_matches_history": False,
            "instantaneous_area_mean_speed_factor_F1": volume_factor_f1,
            "instantaneous_area_mean_squared_speed_factor_F2": momentum_factor_f2,
            "prescribed_volume_flow": (
                "source area times discrete face-area-weighted F1 times the digitized scalar "
                "history; this differs from the uniform area-mean interpretation"
            ),
            "normal_speed_nonnegative": True,
            "transverse_velocity_perturbation_m_s": 0.0,
            "source_area_m2": expected_area,
            "source_width_m": source_width,
            "momentum_change": {
                "diagnostic": "rho_water * sum(face_area * normal_speed^2), logged at every boundary update",
                "uniform_reference_impulse_N_s": uniform_reference_momentum_impulse,
                "actual_profile_impulse_N_s": analytic_momentum_impulse,
                "actual_profile_impulse_status": (
                    "exact from the stationary face-center-sampled profile and the piecewise-linear "
                    "digitized maximum-speed history"
                ),
                "instantaneous_momentum_flux_ratio_to_uniform_max_reference_F2": momentum_factor_f2,
                "note": profile_momentum_note,
            },
            "turbulence_boundary_assumption": (
                "k and epsilon remain uniform in space and use the digitized scalar maximum-speed "
                "history; they are not locally rescaled to the parabolic face velocity"
            ),
            "actual_mesh_face_area_weighting": True,
            "runtime_log_prefix": "DASH8_PROFILE",
            "runtime_log_fields": [
                "source_patch",
                "source_faces",
                "source_area_m2",
                "history_maximum_speed_m_s",
                "sampled_maximum_shape_factor",
                "sampled_maximum_normal_speed_m_s",
                "area_mean_normal_speed_m_s",
                "area_mean_shape_factor_F1",
                "area_mean_squared_shape_factor_F2",
                "prescribed_volume_flow_m3_s",
                "prescribed_mass_flow_kg_s",
                "normal_momentum_flux_N",
                "momentum_flux_ratio_to_uniform_max_reference",
            ],
        }
    else:
        inlet_profile = {
            "kind": source_profile,
            "boundary_condition": profile_boundary,
            "mode": profile_mode,
            "mode_description": SOURCE_PROFILE_MODES[profile_mode],
            "amplitude_fraction_of_mean": amplitude,
            "amplitude_interpretation": (
                "maximum absolute facewise deviation from the instantaneous area-mean normal "
                "speed, after zero-area-mean normalization; values in [0, 1]"
            ),
            "seed": profile_seed,
            "correlation_time_s": correlation_time,
            "temporal_model": (
                "fixed seeded cosine modes with normally distributed angular frequencies "
                "having standard deviation sqrt(2)/correlation_time_s; their ensemble "
                "covariance envelope before area-centering and peak scaling is "
                "exp(-(delta_t/correlation_time_s)^2). The finite discrete realization is "
                "continuous in solver time and draws no random numbers per step; the supplied "
                "correlation time is nominal and the realized face-profile autocorrelation may differ."
            ),
            "spatial_model": (
                "finite seeded cosine modes evaluated from OpenFOAM patch().Cf() face centers; "
                "the profile is recentered with actual face areas and scaled to the requested "
                "maximum deviation at every boundary update"
            ),
            "mode_terms": profile_terms,
            "instantaneous_area_mean_speed_matches_history": True,
            "instantaneous_water_volume_flux_m3_s": (
                "prescribed velocity-derived flux: source area times the digitized "
                "piecewise-linear mean-speed history; transported water flux must be "
                "measured separately from alphaPhi_"
            ),
            "exact_instantaneous_flux_constraint": (
                "sum(face_area * normal_velocity_perturbation) = 0 at every runtime boundary update"
            ),
            "normal_speed_nonnegative": True,
            "transverse_velocity_perturbation_m_s": 0.0,
            "source_area_m2": expected_area,
            "source_width_m": source_width,
            "momentum_change": {
                "diagnostic": "rho_water * sum(face_area * normal_speed^2), logged at each boundary update",
                "comparison": "ratio to rho_water * source_area * scalar_history_speed^2",
                "uniform_reference_impulse_N_s": uniform_reference_momentum_impulse,
                "actual_profile_impulse_status": (
                    "not analytically evaluated before the mesh run; integrate the coded-boundary "
                    "normal_momentum_flux_N log series for perturbed cases"
                    if source_profile == "perturbed"
                    else "equal to the uniform reference impulse"
                ),
                "note": profile_momentum_note,
            },
            "turbulence_boundary_assumption": (
                "k and epsilon retain the existing uniform-in-space tables generated from the "
                "area-mean scalar history; they are not locally rescaled with the perturbed face speed"
                if source_profile == "perturbed"
                else "k and epsilon retain the existing uniform-in-space tables generated from the scalar history"
            ),
            "actual_mesh_face_area_weighting": True,
            "runtime_log_prefix": "DASH8_PROFILE",
            "runtime_mass_flow_interpretation": (
                "water_mass_flow_kg_s is density times the prescribed normal-velocity "
                "flux, not the solver's transported alphaPhi_ water flux"
            ),
            "runtime_log_fields": [
                "source_area_m2",
                "source_patch",
                "source_faces",
                "history_speed_m_s",
                "area_mean_normal_speed_m_s",
                "water_mass_flow_kg_s",
                "normal_momentum_flux_N",
                "uniform_momentum_ratio",
            ],
            "seeded_mode_count": len(profile_terms),
        }
    metadata: dict[str, Any] = {
        "case_id": CASE_ID,
        "aircraft": "Dash-8",
        "evidence_label": "exploratory source-limited approximation; not E2 validation",
        "solver": "interIsoFoam",
        "openfoam_image": CL_HELPERS.IMAGE,
        "horizon_s": horizon,
        "ranks": ranks,
        "source_origin_m": source_origin,
        "source_patches": [SOURCE_NAME],
        "open_patches": OPEN_PATCHES,
        "coordinate_frame": {
            "mesh": {
                "x": "aircraft-frame streamwise axis; relative air flows in +x",
                "y": "cross-track horizontal axis",
                "z": "vertical upward; outlet flow and gravity act in -z",
            },
            "source_origin_m": source_origin,
            "source_plane_z_m": plane_z,
            "streamwise_origin_note": (
                "The coordinate origin is placed at the center of the assumed opening by convention; "
                "the paper does not identify the source rectangle's streamwise leading edge or origin."
            ),
            "paper_plot_transform": {
                "paper_streamwise_y_m": "mesh_x_m - source_origin_m[0]",
                "paper_cross_track_x_m": "mesh_y_m - source_origin_m[1]",
                "paper_downward_z_m": "source_plane_z_m - mesh_z_m",
            },
            "paper_frame_note": (
                "The published component directions are figure-read; a formal right-handed basis "
                "and signed gravity vector are not stated in the paper."
            ),
        },
        **mesh_details,
        "domain_placement_assumption": (
            f"Selected computational bounds are {domain_json} m; the top source plane "
            f"is at z={plane_z:g} m. The reported nearfield dimensions are 26 x 20 x 31 m. "
            "The outlet-to-boundary distances and source placement are assumed."
        ),
        "source_geometry": geometry,
        "source_geometry_assumption": {
            "opening_count": 1,
            "shape": "single longitudinal rectangle",
            "length_x_m": source_length,
            "width_y_m": source_width,
            "area_m2": expected_area,
            "width_sensitivity_note": (
                "At fixed Figure 4 maximum-speed history and fixed dimensionless shape, "
                "changing the assumed opening width changes patch area and discrete profile "
                "quadrature; no direction of its effect on breakup is assumed."
                if source_profile == PARABOLIC_MAX_PROFILE
                else "At fixed Figure 4 mean-speed history, changing the assumed opening width changes "
                "patch area and total released mass in direct proportion; no direction of its "
                "effect on breakup is assumed."
            ),
            "evidence_class": (
                "provisional figure-derived candidate inference, not a reported aperture"
                if default_dimensions
                else "provisional alternative dimensions, not a reported aperture"
            ),
            "evidence_location": (
                "Calbrix et al. (2023), Fig. 2(b-c), PDF p. 4 / journal p. 1518"
                if default_dimensions
                else "experiment-supplied dimensions; no paper location reports this aperture"
            ),
            "mapping": (
                "4.44 m narrow lower-section label and 0.30 m bottom-projection width label "
                "are provisionally mapped to one opening; the source does not establish that mapping"
                if default_dimensions
                else "supplied alternative dimensions override the default drawing-derived "
                "candidate; their experiment record must state the selection rationale"
            ),
            "0_10_m_dimension": "pictured bottom feature; not used as aperture height or gap",
            "source_center_m": [0.0, 0.0, plane_z],
            "direction_unit": [0.0, 0.0, -1.0],
            "direction_evidence": "assumed vertical downward discharge from belly into domain",
            "source_profile": (
                "uniform over the rectangle; no spatially varying profile is published"
                if source_profile == "uniform"
                else "assumed stationary separable parabolic profile with the continuous maximum following Fig. 4; not measured or published"
                if source_profile == PARABOLIC_MAX_PROFILE
                else "provisional seeded space-time normal-speed variation; no spatial profile is published"
            ),
        },
        "source_histories": {
            HISTORY_NAME: {
                "series_id": "dash8_blue",
                "figure_legend": "blue Dash-8 curve",
                "curve_quantity": (
                    "digitized scalar U_L(t), here interpreted as the continuous spatial maximum; "
                    "PDF p. 3 defines U_L=Q_L/S as mean, while PDF p. 5 Fig. 4 caption and "
                    "adjacent Results text call it maximum velocity"
                    if source_profile == PARABOLIC_MAX_PROFILE
                    else "digitized scalar U_L(t); paper defines U_L=Q_L/S as mean but Fig. 4 "
                    "caption/results call the plotted quantity maximum velocity"
                ),
                "mapping": (
                    "one scalar history as a uniform normal speed"
                    if source_profile == "uniform"
                    else "digitized scalar history is treated as continuous maximum normal speed and multiplied by the stationary parabolic shape at each source-face center"
                    if source_profile == PARABOLIC_MAX_PROFILE
                    else "one scalar history as the exact instantaneous area-mean normal speed"
                ),
                "spatial_profile_assumption": (
                    "uniform profile; pointwise exit velocity profile is unavailable"
                    if source_profile == "uniform"
                    else "assumed stationary separable parabolic shape; not measured, published, or fitted; source face-center maximum may be below the continuous maximum"
                    if source_profile == PARABOLIC_MAX_PROFILE
                    else "seeded analytic modes are provisional numerical perturbations, not recovered or measured exit-profile data"
                ),
                "samples_used_m_s": [[time_s, speed] for time_s, speed in bounded_history],
                "interpolation": "piecewise linear between primary digitized samples",
                "zero_at_t0": "t=0, U_L=0 is explicitly present in the primary digitization",
                "integration_method": "exact trapezoidal integral of the piecewise-linear speed history",
                "history_support_s": [history[0][0], history[-1][0]],
                "digitized_endpoint_speed_m_s": history[-1][1],
                "source_endpoint_policy": (
                    "no forced shutoff at the horizon; the primary curve is still 0.074 m/s at 5.0 s"
                ),
                "horizon_s": horizon,
                "analytic_expected_by_source": per_source,
                "analytic_expected_volume_m3": analytic_volume_m3,
                "analytic_expected_mass_kg": analytic_mass_kg,
                "analytic_expected_momentum_impulse_N_s": analytic_momentum_impulse,
                "uniform_reference_momentum_impulse_N_s": uniform_reference_momentum_impulse,
                "source_patch_areas_m2": mesh_details["source_patch_areas_m2"],
                "figure_read_allowances": {
                    "time_s": "copied unchanged from the CSV; about 0.03 s",
                    "velocity_m_s": "copied unchanged from the CSV; varies from about 0.10 to 0.20 m/s",
                    "status": "heuristic raster-read allowances, not paper uncertainty",
                },
                "independent_read": {
                    "source_artifact": f"source/{INDEPENDENT_HISTORY_CSV.name}",
                    "status": "second raster implementation copied as provenance; not blended into primary history",
                },
                "source_artifact": f"source/{PRIMARY_HISTORY_CSV.name}",
            }
        },
        "analytic_expected_mass_kg": analytic_mass_kg,
        "analytic_expected_mass_by_source_kg": {
            SOURCE_NAME: analytic_mass_kg,
        },
        "analytic_expected_momentum_impulse_by_source_N_s": {
            SOURCE_NAME: analytic_momentum_impulse,
        },
        "analytic_uniform_reference_momentum_impulse_by_source_N_s": {
            SOURCE_NAME: uniform_reference_momentum_impulse,
        },
        "inlet_profile": inlet_profile,
        "fluid_properties": {
            "water": {
                "rho_kg_m3": WATER_RHO_KG_M3,
                "mu_Pa_s": 1.0e-3,
                "evidence": "reported, E2 source record PDF p. 4 / journal p. 1518",
            },
            "air": {
                "rho_kg_m3": 1.2,
                "mu_Pa_s": 1.8e-5,
                "evidence": "assumed; numeric E2 air properties are absent from the paper",
            },
            "surface_tension_N_m": 0.0,
            "surface_tension_evidence": (
                "set to zero to match the paper's omitted momentum term; applicability on this mesh is unverified"
            ),
        },
        "air_speed_m_s": AIR_SPEED_M_S,
        "gravity_m_s2": list(GRAVITY_M_S2),
        "boundary_conditions": {
            "airInlet": "x-min plane; fixed 50 m/s +x aircraft-relative air flow",
            "open_boundaries": OPEN_PATCHES,
            "top_belly": (
                "flat slip wall over the top plane except for the single source rectangle; "
                "no aircraft or tank CAD geometry"
            ),
            "source_flow_sign": "top patch outward normal is +z; prescribed velocity is -z and enters the domain",
        },
        "turbulence_model": "standard k-epsilon RANS",
        "turbulence_assumptions": {
            "air_turbulence_intensity": air_intensity,
            "water_turbulence_intensity": water_intensity,
            "air_length_scale_m": air_length_scale,
            "water_length_scale_m": water_length_scale,
            **turbulence_values,
            "source_turbulence_reference_speed_m_s": 6.0,
            "source_turbulence_reference_note": (
                "source_turbulence_k/epsilon are calculated at 6 m/s using the configured water "
                "intensity and length scale; source boundary tables use the same water inputs "
                + (
                    "with the digitized scalar maximum-speed hypothesis."
                    if source_profile == PARABOLIC_MAX_PROFILE
                    else "with the digitized scalar history."
                )
            ),
            **turbulence_peak_metadata,
            "spatial_scaling_assumption": inlet_profile["turbulence_boundary_assumption"],
            "status": "assumed; E2 inlet turbulence values are not fully reported",
        },
        "time_controls": {
            "turbulence_linear_solver": {
                "choice": turbulence_linear_solver,
                "solver": "PBiCGStab"
                if turbulence_linear_solver == "pbicgstab"
                else "smoothSolver",
                "preconditioner_or_smoother": "DILU"
                if turbulence_linear_solver == "pbicgstab"
                else "GaussSeidel",
                "tolerance": 1e-8,
                "relative_tolerance": 0 if turbulence_linear_solver == "pbicgstab" else 0.1,
                "final_relative_tolerance": 0,
                "max_iterations": 100 if turbulence_linear_solver == "pbicgstab" else None,
                "classification": "Numerical solver settings only; standard k-epsilon physics is unchanged. Exploratory stability choice, not validation.",
            },
            "end_s": horizon,
            "initial_delta_t_s": delta_t_s,
            "max_delta_t_s": min(
                CL_HELPERS.MAX_DELTA_T_S,
                0.25
                * min(min(widths) for widths in mesh_details["mesh_widths_by_segment_m"].values())
                / AIR_SPEED_M_S,
            ),
            "adaptive": True,
            "max_Co": CL_HELPERS.MAX_CO,
            "max_alpha_Co": CL_HELPERS.MAX_ALPHA_CO,
            "requested_snapshot_interval_s": snapshot,
            "snapshot_interval_s": effective_snapshot_interval,
        },
        "resources": {"mpi_ranks": ranks, "starting_allocation_only": True},
        "intended_diagnostic": (
            "exploratory E2 nearfield VOF run; compare alpha>=0.001 cloud and alpha>=0.9 core "
            "morphology at available paper times; no ground deposition"
            + (
                "; parabolic maximum profile is a provisional source-shape hypothesis, not a paper fit"
                if source_profile == PARABOLIC_MAX_PROFILE
                else ""
            )
        ),
        "scope_limitations": [
            f"single {source_length:g} m by {source_width:g} m rectangle is provisional; the default candidate uses Fig. 2 labels, but the paper gives no numerical exit area",
            "the pictured 0.10 m bottom feature is not treated as an aperture gap",
            "the digitized U_L(t) may be maximum velocity while the paper also defines U_L=Q_L/S as mean; this discrepancy is unresolved",
            (
                "one uniform scalar speed is assigned over the assumed patch because pointwise exit profiles are unavailable"
                if source_profile == "uniform"
                else "the stationary separable parabolic profile is an assumed maximum-speed hypothesis, not measured or published; its finite-mesh sampled maximum can be below the continuous Figure 4 maximum"
                if source_profile == PARABOLIC_MAX_PROFILE
                else "the seeded facewise profile is a numerical perturbation, not measured Dash-8 exit-profile data; only its area mean follows the digitized scalar history"
            ),
            "the t=5 s digitized endpoint remains nonzero; this case does not append a shutoff, an extrapolated tail, or a claimed completed discharge",
            "no tank or aircraft geometry, rotor wake, foam, parcels, evaporation, ground impact, fire, or deposition",
            "air properties, gravity, turbulence boundary values, surface-tension omission, wall slip, and open boundaries are assumptions where not numerically specified",
            "the case is exploratory and cannot establish E2 validation, field performance, suppression, or design gain",
        ],
        "input_hashes": input_hashes,
        "provenance": {
            **_git_provenance(),
            **input_hashes,
            "source_artifacts_relative_paths": {
                key: f"source/{path.name}" for key, path in source_paths.items()
            },
        },
    }
    (output / "case-inputs.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def _read_json_bounds(path: Path | None) -> dict[str, tuple[float, float]] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"bounds JSON must contain an object: {path}")
    return {
        axis: tuple(bounds) if isinstance(bounds, list) else bounds
        for axis, bounds in value.items()
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new, non-existing case directory"
    )
    parser.add_argument("--horizon-s", type=float, default=5.0)
    parser.add_argument("--ranks", type=int, default=20)
    parser.add_argument("--snapshot-interval-s", type=float, default=0.1)
    parser.add_argument("--spacing-m", type=float, default=0.1, help="finest local cell width")
    parser.add_argument("--coarse-spacing-m", type=float, default=0.4)
    parser.add_argument("--source-length-m", type=float, default=DEFAULT_SOURCE_LENGTH_M)
    parser.add_argument("--source-width-m", type=float, default=DEFAULT_SOURCE_WIDTH_M)
    parser.add_argument(
        "--source-profile",
        choices=("uniform", "perturbed", PARABOLIC_MAX_PROFILE),
        default="uniform",
        help=(
            "uniform legacy inlet, seeded space-time perturbation, or assumed stationary "
            "parabolic profile with the digitized scalar as continuous maximum"
        ),
    )
    parser.add_argument("--profile-amplitude", type=float, default=DEFAULT_PROFILE_AMPLITUDE)
    parser.add_argument("--profile-seed", type=int, default=DEFAULT_PROFILE_SEED)
    parser.add_argument(
        "--profile-correlation-time-s",
        type=float,
        default=DEFAULT_PROFILE_CORRELATION_TIME_S,
    )
    parser.add_argument(
        "--profile-mode",
        choices=tuple(sorted(SOURCE_PROFILE_MODES)),
        default="long_wave",
    )
    parser.add_argument("--domain-bounds-json", type=Path)
    parser.add_argument(
        "--turbulence-linear-solver",
        choices=("gauss-seidel", "pbicgstab"),
        default="gauss-seidel",
        help="legacy baseline or exploratory PBiCGStab/DILU k/epsilon matrix solvers",
    )
    parser.add_argument(
        "--air-turbulence-intensity",
        type=float,
        default=DEFAULT_TURBULENCE_INTENSITY,
        help="assumed air turbulence intensity as a fraction (0 < I <= 1)",
    )
    parser.add_argument(
        "--water-turbulence-intensity",
        type=float,
        default=DEFAULT_TURBULENCE_INTENSITY,
        help="assumed water-source turbulence intensity as a fraction (0 < I <= 1)",
    )
    parser.add_argument(
        "--air-length-scale-m",
        type=float,
        default=DEFAULT_AIR_LENGTH_SCALE_M,
        help="assumed air turbulence length scale in metres",
    )
    parser.add_argument(
        "--water-length-scale-m",
        type=float,
        default=DEFAULT_WATER_LENGTH_SCALE_M,
        help="assumed water-source turbulence length scale in metres",
    )
    parser.add_argument("--refinement-region-json", type=Path)
    parser.add_argument(
        "--source-refinement-region-json",
        type=Path,
        help="optional finer source-region axis-band bounds in metres",
    )
    parser.add_argument(
        "--source-spacing-m",
        type=float,
        help="cell-width target for the optional finer source-region axis bands",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metadata = prepare_case(
            args.output,
            horizon_s=args.horizon_s,
            ranks=args.ranks,
            snapshot_interval_s=args.snapshot_interval_s,
            spacing_m=args.spacing_m,
            coarse_spacing_m=args.coarse_spacing_m,
            source_length_m=args.source_length_m,
            source_width_m=args.source_width_m,
            source_profile=args.source_profile,
            profile_amplitude=args.profile_amplitude,
            profile_seed=args.profile_seed,
            profile_correlation_time_s=args.profile_correlation_time_s,
            profile_mode=args.profile_mode,
            turbulence_linear_solver=args.turbulence_linear_solver,
            air_turbulence_intensity=args.air_turbulence_intensity,
            water_turbulence_intensity=args.water_turbulence_intensity,
            air_length_scale_m=args.air_length_scale_m,
            water_length_scale_m=args.water_length_scale_m,
            domain_bounds_m=_read_json_bounds(args.domain_bounds_json),
            refinement_region=_read_json_bounds(args.refinement_region_json),
            inner_refinement_region=_read_json_bounds(args.source_refinement_region_json),
            inner_spacing_m=args.source_spacing_m,
        )
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"prepare_case: {error}") from error
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_id": metadata["case_id"],
                "mesh_cells_expected": metadata["mesh_cells_expected"],
                "mesh_shape": metadata["mesh_shape"],
                "analytic_expected_mass_kg": metadata["analytic_expected_mass_kg"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
