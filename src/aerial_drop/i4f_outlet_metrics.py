"""Secondary outlet metrics using native water flux and reconstructed face data.

The supplied water volume flux is signed positive out of the selected cut.
Velocity and optional liquid fraction are reconstructed at those faces. These
metrics therefore preserve the native phase-flux integral, but do not reproduce
the solver's mixture momentum-convection operator or establish gas breakthrough.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

_ANGLE_EDGES_DEG = np.linspace(0.0, 180.0, 13)
_RESULTANT_RELATIVE_CANCELLATION_TOLERANCE = 1e-12
_LIQUID_AREA_THRESHOLDS = (
    (0.01, "display_alpha_ge_0p01_area_fraction"),
    (0.50, "diagnostic_alpha_ge_0p50_area_fraction"),
    (0.99, "diagnostic_alpha_ge_0p99_area_fraction"),
)


def outlet_secondary_metrics(
    *,
    water_volume_flux_m3_s: np.ndarray,
    velocity_face_xyz_m_s: np.ndarray,
    projected_area_m2: np.ndarray,
    outlet_normal_unit_xyz: np.ndarray,
    alpha_water_face_raw: np.ndarray | None = None,
    water_density_kg_m3: float = 998.2,
    water_flux_stage_label: str = "native saved water phase-volume flux",
    velocity_stage_label: str = "reconstructed face velocity from saved U",
) -> dict[str, Any]:
    """Summarize a cut using native signed liquid flux and reconstructed fields.

    ``water_volume_flux_m3_s`` is the outward-oriented native phase water flux
    (for example, MULES ``alphaPhi0.water``), not ``phi``. ``velocity_face_xyz``
    and ``alpha_water_face_raw`` are secondary face reconstructions. Alpha is
    never clipped: the reported gas area fraction is the raw proxy
    ``sum(A*(1-alpha_water))/sum(A)``. Thresholded area fractions are descriptive
    only, not acceptance gates.

    The momentum vectors are ``rho_water*sum(q_f*U_f)``. Since saved q and
    reconstructed U can represent different stages, they are estimates rather
    than the solver's exact ``fvm::div(rhoPhi,U)`` contribution. Outflow direction
    statistics use positive q weights; zero-speed outflow is accounted as
    undefined direction. Initial air at a mouth is not evidence of breakthrough.
    """
    q = np.asarray(water_volume_flux_m3_s, dtype=float)
    velocity = np.asarray(velocity_face_xyz_m_s, dtype=float)
    area = np.asarray(projected_area_m2, dtype=float)
    normal = np.asarray(outlet_normal_unit_xyz, dtype=float)

    if q.ndim != 1:
        raise ValueError("water volume flux must be one-dimensional")
    n_faces = q.size
    if velocity.shape != (n_faces, 3):
        raise ValueError("face velocity must have shape (n_faces, 3)")
    if area.shape != (n_faces,):
        raise ValueError("projected face areas must have shape (n_faces,)")
    if normal.shape != (3,) or not np.all(np.isfinite(normal)):
        raise ValueError("outlet normal must be a finite 3-vector")
    normal_norm = float(np.linalg.norm(normal))
    if not math.isclose(normal_norm, 1.0, rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("outlet normal must be unit length")
    if not np.all(np.isfinite(q)):
        raise ValueError("water volume flux must be finite")
    if not np.all(np.isfinite(velocity)):
        raise ValueError("face velocity must be finite")
    if not np.all(np.isfinite(area)) or np.any(area <= 0.0):
        raise ValueError("projected face areas must be finite and positive")
    if not math.isfinite(water_density_kg_m3) or water_density_kg_m3 <= 0.0:
        raise ValueError("water density must be finite and positive")
    if not water_flux_stage_label.strip() or not velocity_stage_label.strip():
        raise ValueError("field stage labels must be nonempty")

    alpha: np.ndarray | None
    if alpha_water_face_raw is None:
        alpha = None
    else:
        alpha = np.asarray(alpha_water_face_raw, dtype=float)
        if alpha.shape != (n_faces,):
            raise ValueError("raw face liquid fractions must have shape (n_faces,)")
        if not np.all(np.isfinite(alpha)):
            raise ValueError("raw face liquid fractions must be finite")

    q_out = np.maximum(q, 0.0)
    q_reverse = np.minimum(q, 0.0)
    q_out_total = float(np.sum(q_out))
    q_reverse_magnitude = float(-np.sum(q_reverse))
    normal_velocity = velocity @ normal
    speed = np.linalg.norm(velocity, axis=1)
    directional = (q_out > 0.0) & (speed > 0.0)
    undefined_direction = (q_out > 0.0) & (speed == 0.0)
    direction_q = float(np.sum(q_out[directional]))
    undefined_direction_q = float(np.sum(q_out[undefined_direction]))

    angle_deg = np.full(n_faces, np.nan, dtype=float)
    if np.any(directional):
        cosine = (velocity[directional] @ normal) / speed[directional]
        angle_deg[directional] = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))

    direction_mean_deg: float | None = None
    direction_rms_deg: float | None = None
    resultant_unit: list[float] | None = None
    resultant_angle_deg: float | None = None
    resultant_fraction: float | None = None
    histogram_q = np.zeros(len(_ANGLE_EDGES_DEG) - 1, dtype=float)
    if direction_q > 0.0:
        weights = q_out[directional]
        angles = angle_deg[directional]
        direction_mean_deg = float(np.dot(weights, angles) / direction_q)
        direction_rms_deg = float(math.sqrt(np.dot(weights, angles * angles) / direction_q))
        histogram_q, _ = np.histogram(angles, bins=_ANGLE_EDGES_DEG, weights=weights)
        unit_velocity = velocity[directional] / speed[directional, None]
        resultant = np.sum(weights[:, None] * unit_velocity, axis=0)
        resultant_norm = float(np.linalg.norm(resultant))
        resultant_fraction = resultant_norm / direction_q
        if resultant_norm > 1e-12 * direction_q:
            resultant_direction = resultant / resultant_norm
            resultant_unit = [float(value) for value in resultant_direction]
            resultant_angle_deg = float(
                np.degrees(np.arccos(np.clip(float(resultant_direction @ normal), -1.0, 1.0)))
            )

    momentum_net = water_density_kg_m3 * np.sum(q[:, None] * velocity, axis=0)
    momentum_out = water_density_kg_m3 * np.sum(q_out[:, None] * velocity, axis=0)
    momentum_reverse = water_density_kg_m3 * np.sum(q_reverse[:, None] * velocity, axis=0)
    momentum_out_norm = float(np.linalg.norm(momentum_out))
    momentum_out_scale = float(water_density_kg_m3 * np.sum(q_out * speed))
    momentum_out_strength = (
        momentum_out_norm / momentum_out_scale if momentum_out_scale > 0.0 else None
    )
    momentum_out_unit: list[float] | None = None
    momentum_out_angle_deg: float | None = None
    if (
        momentum_out_scale > 0.0
        and momentum_out_norm > _RESULTANT_RELATIVE_CANCELLATION_TOLERANCE * momentum_out_scale
    ):
        momentum_out_direction = momentum_out / momentum_out_norm
        momentum_out_unit = [float(value) for value in momentum_out_direction]
        momentum_out_angle_deg = float(
            np.degrees(np.arccos(np.clip(float(momentum_out_direction @ normal), -1.0, 1.0)))
        )

    normal_mismatch_out = (q > 0.0) & (normal_velocity < 0.0)
    normal_mismatch_reverse = (q < 0.0) & (normal_velocity > 0.0)
    normal_zero_q = (q != 0.0) & (normal_velocity == 0.0)

    result: dict[str, Any] = {
        "face_count": int(n_faces),
        "projected_area_m2": float(np.sum(area)) if n_faces else None,
        "field_stage_labels": {
            "water_volume_flux": water_flux_stage_label,
            "face_velocity": velocity_stage_label,
            "qualification": (
                "Fields may be sampled at different pressure/outer-iteration stages; "
                "inspect PIMPLE outer convergence before physical interpretation."
            ),
        },
        "water_volume_flux_net_m3_s": float(np.sum(q)),
        "water_volume_flux_outward_m3_s": q_out_total,
        "water_volume_flux_reverse_magnitude_m3_s": q_reverse_magnitude,
        "water_mass_flux_net_kg_s": float(water_density_kg_m3 * np.sum(q)),
        "water_mass_flux_outward_kg_s": float(water_density_kg_m3 * q_out_total),
        "water_mass_flux_reverse_magnitude_kg_s": float(water_density_kg_m3 * q_reverse_magnitude),
        "water_momentum_flux_net_reconstructed_N_xyz": [float(v) for v in momentum_net],
        "water_momentum_flux_outward_reconstructed_N_xyz": [float(v) for v in momentum_out],
        "water_momentum_flux_outward_resultant_norm_reconstructed_N": momentum_out_norm,
        "water_momentum_flux_outward_resultant_unit_xyz": momentum_out_unit,
        "water_momentum_flux_outward_resultant_angle_deg": momentum_out_angle_deg,
        "water_momentum_flux_outward_resultant_strength_fraction": momentum_out_strength,
        "water_momentum_flux_outward_resultant_direction_defined": momentum_out_unit is not None,
        "water_momentum_flux_outward_resultant_definition": (
            "rho_water*sum(q_positive*U_face); direction angle is relative to outlet normal; "
            "undefined when vector cancellation is within 1e-12 of sum(rho_water*q_positive*|U_face|)"
        ),
        "water_momentum_flux_reverse_signed_reconstructed_N_xyz": [
            float(v) for v in momentum_reverse
        ],
        "outward_direction_defined_water_flux_m3_s": direction_q,
        "outward_direction_undefined_water_flux_m3_s": undefined_direction_q,
        "outward_direction_mean_angle_deg_q_weighted": direction_mean_deg,
        "outward_direction_rms_angle_deg_q_weighted": direction_rms_deg,
        "outward_direction_resultant_unit_xyz": resultant_unit,
        "outward_direction_resultant_angle_deg": resultant_angle_deg,
        "outward_direction_resultant_strength_fraction": resultant_fraction,
        "outward_direction_resultant_definition": (
            "normalize(sum(q_positive * U_face/|U_face|)) over nonzero-speed outflow faces; "
            "strength is its magnitude divided by defined-direction outflow q"
        ),
        "outward_direction_angle_histogram": {
            "angle_bin_edges_deg": [float(v) for v in _ANGLE_EDGES_DEG],
            "q_m3_s_by_bin": [float(v) for v in histogram_q],
            "undefined_direction_q_m3_s": undefined_direction_q,
        },
        "q_velocity_normal_sign_diagnostics": {
            "outward_q_with_inward_U_face_count": int(np.count_nonzero(normal_mismatch_out)),
            "outward_q_with_inward_U_face_flux_magnitude_m3_s": float(
                np.sum(q[normal_mismatch_out])
            ),
            "reverse_q_with_outward_U_face_count": int(np.count_nonzero(normal_mismatch_reverse)),
            "reverse_q_with_outward_U_face_flux_magnitude_m3_s": float(
                -np.sum(q[normal_mismatch_reverse])
            ),
            "nonzero_q_with_zero_normal_U_face_count": int(np.count_nonzero(normal_zero_q)),
            "nonzero_q_with_zero_normal_U_face_flux_magnitude_m3_s": float(
                np.sum(np.abs(q[normal_zero_q]))
            ),
        },
        "raw_alpha_proxy_available": alpha is not None,
        "raw_alpha_water_min": float(np.min(alpha)) if alpha is not None and n_faces else None,
        "raw_alpha_water_max": float(np.max(alpha)) if alpha is not None and n_faces else None,
        "raw_alpha_water_below_zero_face_count": (
            int(np.count_nonzero(alpha < 0.0)) if alpha is not None else None
        ),
        "raw_alpha_water_above_one_face_count": (
            int(np.count_nonzero(alpha > 1.0)) if alpha is not None else None
        ),
        "area_weighted_raw_alpha_water_fraction": (
            float(np.dot(area, alpha) / np.sum(area)) if alpha is not None and n_faces else None
        ),
        "area_weighted_raw_alpha_gas_fraction_proxy": (
            float(np.dot(area, 1.0 - alpha) / np.sum(area))
            if alpha is not None and n_faces
            else None
        ),
        "liquid_area_fraction_thresholds": {
            key: float(np.sum(area[alpha >= threshold]) / np.sum(area))
            if alpha is not None and n_faces
            else None
            for threshold, key in _LIQUID_AREA_THRESHOLDS
        },
        "qualification": (
            "Native signed water flux is combined with reconstructed face U for secondary momentum/direction metrics; "
            "these are not the solver's exact mixture momentum-convection flux. Raw alpha is not clipped. "
            "The gas area fraction is a reconstructed proxy, not a gas flux or breakthrough determination."
        ),
    }
    return result
