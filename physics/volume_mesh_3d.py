"""Voxel-based hexahedral volume approximation for closed triangle surfaces.

Each occupied voxel is an axis-aligned hexahedral cell whose centre lies inside
the imported watertight surface. This is a Cartesian approximation (stair-step
boundary), not a boundary-conforming FEM mesh.
"""
import math
import numpy as np
from physics.worker import check_cancel


def _ray_triangle_z_intersection(x, y, a, b, c, eps=1e-12):
    """Z coordinate where vertical ray through (x,y) intersects triangle, or None."""
    v0 = b[:2] - a[:2]
    v1 = c[:2] - a[:2]
    v2 = np.array([x, y], dtype=float) - a[:2]
    den = v0[0] * v1[1] - v1[0] * v0[1]
    if abs(den) <= eps:
        return None
    u = (v2[0] * v1[1] - v1[0] * v2[1]) / den
    v = (v0[0] * v2[1] - v2[0] * v2[1]) / den
    w = 1.0 - u - v
    if u < -eps or v < -eps or w < -eps:
        return None
    return float(w * a[2] + u * b[2] + v * c[2])


def create_voxel_volume_mesh(vertices, faces, resolution=20, max_cells=50000,
                             progress_callback=None, cancel_event=None):
    """Voxelize a closed triangle surface and return occupied hexahedral cells."""
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 4:
        raise ValueError("Vertex geometri tidak valid.")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) < 4:
        raise ValueError("Face geometri tidak valid.")
    if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Data geometri mengandung koordinat atau indeks tidak valid.")
    if isinstance(resolution, bool) or int(resolution) < 4 or int(resolution) > 40:
        raise ValueError("Resolusi voxel harus antara 4 dan 40.")
    resolution = int(resolution)

    edge_array = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edge_array.sort(axis=1)
    _, edge_counts = np.unique(edge_array, axis=0, return_counts=True)
    if np.any(edge_counts != 2):
        raise ValueError("Volume meshing memerlukan permukaan tertutup/manifold: setiap edge harus dipakai tepat dua segitiga.")

    lower = vertices.min(axis=0)
    upper = vertices.max(axis=0)
    lengths = upper - lower
    if np.any(lengths <= 0):
        raise ValueError("Geometri memiliki dimensi nol.")
    # Isotropic target spacing; cap each axis while retaining the model aspect ratio.
    longest = float(lengths.max())
    base_spacing = longest / resolution
    counts = np.maximum(2, np.ceil(lengths / base_spacing).astype(int))
    nx, ny, nz = (int(v) for v in counts)
    total = nx * ny * nz
    if total > int(max_cells):
        raise ValueError(f"Grid kandidat {total:,} sel melebihi batas {max_cells:,}. Turunkan resolusi.")
    dx, dy, dz = lengths / counts
    x = lower[0] + (np.arange(nx) + 0.5) * dx
    y = lower[1] + (np.arange(ny) + 0.5) * dy
    z = lower[2] + (np.arange(nz) + 0.5) * dz
    inside = np.zeros((nz, ny, nx), dtype=bool)
    triangles = vertices[faces]

    # Cast vertical rays at voxel-column centres. Tiny deterministic offsets avoid
    # rays coinciding with common axis-aligned triangulation edges.
    x_offset = dx * 1.234567e-7
    y_offset = dy * 2.345679e-7
    for iy, yc in enumerate(y):
        check_cancel(cancel_event)
        yy = float(yc + y_offset)
        for ix, xc in enumerate(x):
            xx = float(xc + x_offset)
            hits = []
            for tri in triangles:
                z_hit = _ray_triangle_z_intersection(xx, yy, tri[0], tri[1], tri[2])
                if z_hit is not None:
                    hits.append(z_hit)
            if hits:
                hits.sort()
                # Merge numerically duplicate hits where adjacent triangles share an edge.
                unique_hits = []
                tol = max(dx, dy, dz) * 1e-8
                for value in hits:
                    if not unique_hits or abs(value - unique_hits[-1]) > tol:
                        unique_hits.append(value)
                hit_values = np.asarray(unique_hits)
                inside[:, iy, ix] = (np.searchsorted(hit_values, z, side="right") % 2) == 1
        if progress_callback and (iy == ny - 1 or iy % max(1, ny // 20) == 0):
            progress_callback(iy + 1, ny, None)

    iz, iy, ix = np.where(inside)
    if len(ix) == 0:
        raise ValueError("Tidak ditemukan sel volume di dalam geometri. Coba tingkatkan resolusi atau periksa orientasi/topologi permukaan.")
    centers = np.column_stack((x[ix], y[iy], z[iz]))
    return {
        "x": x, "y": y, "z": z,
        "inside_mask_zyx": inside,
        "cell_centers": centers,
        "nx": nx, "ny": ny, "nz": nz,
        "candidate_cell_count": int(total),
        "active_cell_count": int(len(centers)),
        "volume_estimate_m3": float(len(centers) * dx * dy * dz),
        "dx": float(dx), "dy": float(dy), "dz": float(dz),
        "bounds_min_m": lower.tolist(), "bounds_max_m": upper.tolist(),
        "mesh_type": "voxelized Cartesian hexahedral volume approximation",
        "boundary_note": "Stair-step boundary; not a conforming tetrahedral/hexahedral FEM mesh.",
    }
