"""Numerical and coordinate checks for the optional Mitsuba VOF renderer."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.render_vof_mitsuba import (
    StructuredCoordinates,
    _uniform_grid_volume,
    resample_to_uniform_box,
    sigma_t_from_alpha,
    voxel_center_world_coordinate,
)


def _mitsuba_cpu():
    dr = pytest.importorskip("drjit")
    mi = pytest.importorskip("mitsuba")
    dr.set_thread_count(1)
    mi.set_variant("llvm_ad_rgb")
    return mi


def _volume_value(mi, volume, point_xyz):
    interaction = mi.Interaction3f(mi.Float(0), mi.Float(0), mi.Color0f(), mi.Point3f(*point_xyz))
    return float(volume.eval_1(interaction)[0])


def test_dilute_spherical_droplet_extinction_has_si_units() -> None:
    alpha = np.array([0.0, 0.01, 0.1], dtype=np.float64)
    actual = sigma_t_from_alpha(alpha, d32_m=5e-4, q_ext=2.0)
    np.testing.assert_allclose(actual, [0.0, 60.0, 600.0], rtol=0, atol=1e-12)


def test_gridvolume_uses_zyx_values_voxel_centres_and_world_bbox() -> None:
    mi = _mitsuba_cpu()
    values_zyx = np.zeros((2, 3, 4), dtype=np.float32)
    values_zyx[1, 2, 3] = 1.0
    bounds_xyz = ((10.0, 14.0), (20.0, 23.0), (30.0, 32.0))
    volume = _uniform_grid_volume(mi, values_zyx, bounds_xyz)

    assert tuple(volume.bbox().min) == pytest.approx((10.0, 20.0, 30.0))
    assert tuple(volume.bbox().max) == pytest.approx((14.0, 23.0, 32.0))
    center = voxel_center_world_coordinate(bounds_xyz, (4, 3, 2), (3, 2, 1))
    assert center == pytest.approx((13.5, 22.5, 31.5))
    assert _volume_value(mi, volume, center) == pytest.approx(1.0)

    # At a neighbouring zyx sample center the impulse is zero. At the midpoint
    # in x between those centers trilinear filtering returns one half.
    neighbor = voxel_center_world_coordinate(bounds_xyz, (4, 3, 2), (2, 2, 1))
    assert _volume_value(mi, volume, neighbor) == pytest.approx(0.0, abs=1e-6)
    midpoint = ((neighbor[0] + center[0]) / 2, neighbor[1], neighbor[2])
    assert _volume_value(mi, volume, midpoint) == pytest.approx(0.5, abs=1e-6)


def test_resampling_reproduces_linear_field_on_asymmetric_zyx_grid() -> None:
    pytest.importorskip("scipy.interpolate")

    x = np.array([1.0, 2.0, 3.0])
    y = np.array([4.0, 6.0, 8.0])
    z_by_y = np.array([-2.0, -1.0, 0.0, 1.0])[None, :] + 0.1 * y[:, None]
    ny, nx, nz = len(y), len(x), z_by_y.shape[1]

    iy = np.repeat(np.arange(ny), nx * nz)
    ix = np.tile(np.repeat(np.arange(nx), nz), ny)
    iz = np.tile(np.arange(nz), ny * nx)
    coords = StructuredCoordinates(x, y, z_by_y, ix, iy, iz, (ny, nx, nz))
    values_yxz = 2.0 * x[None, :, None] - 3.0 * y[:, None, None] + 0.5 * z_by_y[:, None, :]

    bounds = ((1.25, 2.75), (4.5, 7.5), (-0.25, 0.5))
    dimensions_xyz = (3, 2, 3)
    actual_zyx = resample_to_uniform_box(values_yxz, coords, bounds, dimensions_xyz)

    nx_out, ny_out, nz_out = dimensions_xyz
    x_out = np.linspace(*bounds[0], nx_out, endpoint=False) + (bounds[0][1] - bounds[0][0]) / (
        2 * nx_out
    )
    y_out = np.linspace(*bounds[1], ny_out, endpoint=False) + (bounds[1][1] - bounds[1][0]) / (
        2 * ny_out
    )
    z_out = np.linspace(*bounds[2], nz_out, endpoint=False) + (bounds[2][1] - bounds[2][0]) / (
        2 * nz_out
    )
    zz, yy, xx = np.meshgrid(z_out, y_out, x_out, indexing="ij")
    expected_zyx = 2.0 * xx - 3.0 * yy + 0.5 * zz
    assert actual_zyx.shape == (nz_out, ny_out, nx_out)
    np.testing.assert_allclose(actual_zyx, expected_zyx, rtol=0, atol=2e-6)


def test_pure_absorbing_one_metre_slab_transmits_exp_minus_one() -> None:
    mi = _mitsuba_cpu()
    scene = mi.load_dict(
        {
            "type": "scene",
            "integrator": {"type": "volpath", "max_depth": -1, "rr_depth": 4},
            "sensor": {
                "type": "orthographic",
                "to_world": mi.ScalarTransform4f.look_at(
                    origin=[0.0, 0.0, 2.0], target=[0.0, 0.0, 0.0], up=[0.0, 1.0, 0.0]
                ),
                "sampler": {"type": "independent", "sample_count": 256, "seed": 19},
                "film": {"type": "hdrfilm", "width": 16, "height": 16},
            },
            "environment": {
                "type": "constant",
                "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
            },
            "slab": {
                "type": "cube",
                "to_world": mi.ScalarTransform4f().scale(0.5),
                "bsdf": {"type": "null"},
                "interior": {
                    "type": "homogeneous",
                    "sigma_t": 1.0,
                    "albedo": 0.0,
                },
            },
        }
    )
    image = np.asarray(mi.render(scene, spp=256), dtype=np.float64)
    # Restrict the estimate to interior rays; orthographic-film edge pixels
    # straddle the cube and include unattenuated background paths.
    transmission = float(np.mean(image[6:10, 6:10, :]))
    assert transmission == pytest.approx(np.exp(-1.0), abs=0.025)
