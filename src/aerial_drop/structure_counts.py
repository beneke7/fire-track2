"""Reproducible connected-liquid structure counts and per-structure statistics.

Calbrix et al. say that MATLAB reconstructed 3-D liquid structures at each
instant to characterize their sizes and velocities. Figure 11 uses the
thresholds ``alpha_L >= 0.9`` and ``alpha_L >= 0.001`` (PDF p. 8, printed
journal p. 1522; Fig. 11 is on PDF p. 10, printed p. 1524). The article does
not specify the connectivity rule, minimum cell count, equivalent-diameter
formula, or weighting used for its velocity bars. This module therefore defines
a portable method; it does not claim exact equivalence to the unpublished
MATLAB detector.

The supplied ``owner``/``neighbour`` edges define connectivity. OpenFOAM
internal-face pairs give face connectivity by default. For a point-connectivity
sensitivity, callers can include additional cell pairs that share a mesh point
and rerun the same routine. The default minimum is one selected cell. Filtering
small components changes reported labels and statistics only; it never edits
the caller's VOF field or mass ledger.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

_EDGE_CHUNK_SIZE = 1 << 20
_INT32_MAX = np.iinfo(np.int32).max


def label_liquid_structures(
    alpha_l: ArrayLike,
    owner: ArrayLike,
    neighbour: ArrayLike,
    threshold: float,
    *,
    min_cells: int = 1,
) -> NDArray[np.int32]:
    """Label thresholded cells connected by the supplied cell-pair edges.

    ``alpha_l`` is in native-cell order and each edge joins the two native cell
    indices in ``owner`` and ``neighbour``. Passing only OpenFOAM internal-face
    pairs gives face adjacency. Passing point-sharing pairs as well gives the
    corresponding point-adjacency sensitivity. Boundary faces do not connect
    cells. A selected cell has ``alpha_l >= threshold``; air or filtered cells
    receive ``-1``. Surviving component IDs are contiguous ``int32`` values,
    ordered by the smallest native-cell index in each component.

    ``min_cells`` defaults to 1, retaining every detected component. This
    filter is a reporting choice: it does not modify ``alpha_l`` or remove mass
    from any independent conservation calculation.
    """
    alpha = np.asarray(alpha_l)
    left = np.asarray(owner)
    right = np.asarray(neighbour)

    if alpha.ndim != 1:
        raise ValueError("alpha_l must be a one-dimensional native-cell array")
    if (
        not np.issubdtype(alpha.dtype, np.number)
        or np.issubdtype(alpha.dtype, np.complexfloating)
        or not np.all(np.isfinite(alpha))
    ):
        raise ValueError("alpha_l must contain finite numeric values")
    if not np.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("threshold must be finite and in (0, 1]")
    if isinstance(min_cells, bool) or not isinstance(min_cells, (int, np.integer)):
        raise ValueError("min_cells must be a positive integer")
    if min_cells < 1:
        raise ValueError("min_cells must be a positive integer")
    if left.ndim != 1 or right.ndim != 1 or left.shape != right.shape:
        raise ValueError("owner and neighbour must be one-dimensional arrays of equal length")
    if not np.issubdtype(left.dtype, np.integer) or not np.issubdtype(right.dtype, np.integer):
        raise ValueError("owner and neighbour must contain integer cell indices")

    n_cells = len(alpha)
    if n_cells > _INT32_MAX:
        raise ValueError("int32 labels support at most 2^31-1 native cells")
    if left.size and (
        np.any(left < 0) or np.any(right < 0) or np.any(left >= n_cells) or np.any(right >= n_cells)
    ):
        raise ValueError("owner and neighbour indices must be valid native-cell indices")

    selected = alpha >= threshold
    selected_ids = np.flatnonzero(selected)
    labels = np.full(n_cells, -1, dtype=np.int32)
    if selected_ids.size == 0:
        return labels

    # A component's smallest native cell ID is its stable representative.
    # Hooking only larger roots to smaller roots is deterministic and acyclic.
    parent = np.arange(n_cells, dtype=np.int32)
    while True:
        merged = False
        for start in range(0, left.size, _EDGE_CHUNK_SIZE):
            stop = min(start + _EDGE_CHUNK_SIZE, left.size)
            edge_left = left[start:stop]
            edge_right = right[start:stop]
            active = selected[edge_left] & selected[edge_right]
            if not np.any(active):
                continue

            edge_left = edge_left[active].astype(np.intp, copy=False)
            edge_right = edge_right[active].astype(np.intp, copy=False)
            root_left = _find_roots(parent, edge_left)
            root_right = _find_roots(parent, edge_right)

            # Compress the current endpoints before adding this batch of links.
            # These assignments are safe before the simultaneous root hooks.
            parent[edge_left] = root_left
            parent[edge_right] = root_right

            different = root_left != root_right
            if np.any(different):
                high = np.maximum(root_left[different], root_right[different])
                low = np.minimum(root_left[different], root_right[different])
                np.minimum.at(parent, high, low)
                merged = True

        if not merged:
            break

        # Pointer jumping keeps root walks short even when edge IDs arrive in
        # reverse native-cell order. Parent pointers only move toward lower IDs.
        while True:
            grandparent = parent[parent]
            if np.array_equal(parent, grandparent):
                break
            parent = grandparent

    roots = _find_roots(parent, selected_ids)
    unique_roots, counts = np.unique(roots, return_counts=True)
    retained_roots = unique_roots[counts >= min_cells]
    if retained_roots.size == 0:
        return labels

    positions = np.searchsorted(retained_roots, roots)
    retained = positions < retained_roots.size
    valid_indices = np.flatnonzero(retained)
    retained[valid_indices] = retained_roots[positions[valid_indices]] == roots[valid_indices]
    labels[selected_ids[retained]] = positions[retained].astype(np.int32)
    return labels


def _find_roots(parent: NDArray[np.int32], nodes: NDArray[np.intp]) -> NDArray[np.int32]:
    """Resolve representative IDs by vectorized pointer jumping."""
    roots = parent[nodes]
    while roots.size:
        parent_of_root = parent[roots]
        if np.array_equal(roots, parent_of_root):
            return roots
        grandparent = parent[parent_of_root]
        parent[roots] = grandparent
        roots = grandparent
    return roots


def structure_statistics(
    alpha_l: ArrayLike,
    cell_volumes_m3: ArrayLike,
    labels: ArrayLike,
    velocity_m_s: ArrayLike | None = None,
    *,
    density_kg_m3: float | ArrayLike = 1000.0,
) -> list[dict[str, int | float | tuple[float, float, float]]]:
    """Compute liquid volume, mass, sphere-equivalent diameter and mean velocity.

    Liquid volume is ``sum(alpha_l * cell_volume)`` over cells with nonnegative
    labels. The equivalent diameter is that liquid volume converted to a
    sphere, ``(6 * liquid_volume / pi)**(1/3)``. Mass uses liquid volume times
    ``density_kg_m3`` (uniform water at 1000 kg/m³ by default; a per-cell density
    array is also accepted). Optional velocity is averaged with liquid mass as
    its weight. Cells labelled ``-1`` are omitted from structure statistics but
    remain in the caller's field and ledger.

    The returned rows are sorted by input label and contain ``label``,
    ``cell_count``, ``liquid_volume_m3``, ``mass_kg`` and
    ``equivalent_diameter_m``. If velocity is provided, rows also contain
    ``mass_weighted_velocity_m_s`` as an (x, y, z) tuple. The weighting is an
    explicit reproducible choice; Calbrix et al. do not publish the weighting
    behind Fig. 11b's velocity bars.
    """
    alpha = np.asarray(alpha_l, dtype=float)
    volumes = np.asarray(cell_volumes_m3, dtype=float)
    region_labels = np.asarray(labels)
    if alpha.ndim != 1 or volumes.shape != alpha.shape or region_labels.shape != alpha.shape:
        raise ValueError("alpha_l, cell_volumes_m3 and labels must have matching 1-D shapes")
    if not np.all(np.isfinite(alpha)):
        raise ValueError("alpha_l must contain finite values")
    if not np.all(np.isfinite(volumes)) or np.any(volumes <= 0):
        raise ValueError("cell_volumes_m3 must contain finite positive values")
    if not np.issubdtype(region_labels.dtype, np.integer):
        raise ValueError("labels must contain integer IDs")
    if np.any(region_labels < -1):
        raise ValueError("labels must use -1 for excluded cells or nonnegative IDs")

    velocity = None
    if velocity_m_s is not None:
        velocity = np.asarray(velocity_m_s, dtype=float)
        if velocity.shape != (len(alpha), 3):
            raise ValueError("velocity_m_s must have shape (number of cells, 3)")
        if not np.all(np.isfinite(velocity[region_labels >= 0])):
            raise ValueError("velocity_m_s must be finite for labelled cells")

    density = np.asarray(density_kg_m3, dtype=float)
    if density.ndim == 0:
        if not np.isfinite(density) or density <= 0:
            raise ValueError("density_kg_m3 must be finite and positive")
        selected_density: float | NDArray[np.float64] = float(density)
    else:
        if density.shape != alpha.shape:
            raise ValueError("density_kg_m3 must be scalar or match the cell arrays")
        if not np.all(np.isfinite(density)) or np.any(density <= 0):
            raise ValueError("density_kg_m3 must contain finite positive values")
        selected_density = density[region_labels >= 0]

    selected = region_labels >= 0
    if not np.any(selected):
        return []
    if np.any(alpha[selected] < 0):
        raise ValueError("labelled cells must have nonnegative liquid fraction")

    component_ids, inverse = np.unique(region_labels[selected], return_inverse=True)
    liquid_volumes = alpha[selected] * volumes[selected]
    masses = liquid_volumes * selected_density
    if np.any(liquid_volumes <= 0) or not np.all(np.isfinite(masses)):
        raise ValueError("labelled cells must have finite positive liquid mass")

    component_volumes = np.bincount(inverse, weights=liquid_volumes)
    component_masses = np.bincount(inverse, weights=masses)
    component_counts = np.bincount(inverse)
    diameters = np.cbrt(6.0 * component_volumes / np.pi)

    component_velocities = None
    if velocity is not None:
        selected_velocity = velocity[selected]
        component_velocities = np.column_stack(
            [
                np.bincount(
                    inverse,
                    weights=masses * selected_velocity[:, axis],
                    minlength=len(component_ids),
                )
                / component_masses
                for axis in range(3)
            ]
        )

    rows: list[dict[str, int | float | tuple[float, float, float]]] = []
    for index, component_id in enumerate(component_ids):
        row: dict[str, int | float | tuple[float, float, float]] = {
            "label": int(component_id),
            "cell_count": int(component_counts[index]),
            "liquid_volume_m3": float(component_volumes[index]),
            "mass_kg": float(component_masses[index]),
            "equivalent_diameter_m": float(diameters[index]),
        }
        if component_velocities is not None:
            row["mass_weighted_velocity_m_s"] = tuple(
                float(value) for value in component_velocities[index]
            )
        rows.append(row)
    return rows
