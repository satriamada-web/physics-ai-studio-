"""Structured Cartesian 3D grid utilities for Physics AI Studio.

This is a node-centred finite-difference grid, not a tetrahedral FEM mesh.
Array fields use the solver convention (nz, ny, nx) = (z, y, x).
"""
import math
import numpy as np
from physics.worker import check_cancel


def create_structured_mesh(nx, ny, nz, lx, ly, lz, max_nodes=200_000, progress_callback=None, cancel_event=None):
    """Create a node-centred Cartesian grid spanning [0,L] on each axis.

    Parameters
    ----------
    nx, ny, nz : int
        Number of grid nodes along X, Y, and Z (minimum 2).
    lx, ly, lz : float
        Domain lengths in metres; each must be finite and positive.
    max_nodes : int
        Safety limit for the total number of nodes.

    Returns
    -------
    dict
        Coordinate vectors, spacing, counts, bounds, and array shape.
        Coordinates are 1D vectors; no dense 3D coordinate arrays are allocated.
    """
    counts = {"nx": nx, "ny": ny, "nz": nz}
    for name, value in counts.items():
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} harus berupa bilangan bulat.")
        if int(value) < 2:
            raise ValueError(f"{name} minimal 2 node.")
    lengths = {"lx": lx, "ly": ly, "lz": lz}
    clean_lengths = {}
    for name, value in lengths.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} harus berupa angka positif.")
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{name} harus berupa angka positif dan finite.")
        clean_lengths[name] = number

    nx, ny, nz = int(nx), int(ny), int(nz)
    node_count = nx * ny * nz
    if node_count > int(max_nodes):
        raise ValueError(
            f"Grid berisi {node_count:,} node, melebihi batas aman "
            f"{int(max_nodes):,}. Kurangi resolusi."
        )

    lx, ly, lz = clean_lengths["lx"], clean_lengths["ly"], clean_lengths["lz"]
    check_cancel(cancel_event)
    x = np.linspace(0.0, lx, nx)
    if progress_callback: progress_callback(1, 3, None)
    check_cancel(cancel_event)
    y = np.linspace(0.0, ly, ny)
    if progress_callback: progress_callback(2, 3, None)
    check_cancel(cancel_event)
    z = np.linspace(0.0, lz, nz)
    if progress_callback: progress_callback(3, 3, None)
    return {
        "x": x,
        "y": y,
        "z": z,
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "lx": lx,
        "ly": ly,
        "lz": lz,
        "dx": lx / (nx - 1),
        "dy": ly / (ny - 1),
        "dz": lz / (nz - 1),
        "node_count": node_count,
        "cell_count": (nx - 1) * (ny - 1) * (nz - 1),
        "shape_zyx": (nz, ny, nx),
        "bounds_m": {"x": (0.0, lx), "y": (0.0, ly), "z": (0.0, lz)},
        "grid_type": "node-centred Cartesian structured grid",
        "method_note": "Finite-difference grid; not a tetrahedral/hexahedral FEM volume mesh.",
    }
