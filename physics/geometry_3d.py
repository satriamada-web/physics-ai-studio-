"""Primitive 3D geometry generation for Physics AI Studio.

Coordinates are centered at the origin and expressed in meters.
Meshes are triangular surface meshes intended for preview, not FEM volume meshes.
"""
import numpy as np
from physics.worker import check_cancel


def create_geometry(shape, dimensions, resolution=24, progress_callback=None, cancel_event=None):
    """Return vertices (N,3), triangular faces (M,3), and metadata."""
    check_cancel(cancel_event)
    if shape not in {"Kubus", "Balok", "Silinder"}:
        raise ValueError("Bentuk geometri tidak didukung.")
    if not isinstance(dimensions, dict):
        raise ValueError("Dimensi harus berupa dictionary.")
    resolution = int(resolution)
    if resolution < 8 or resolution > 128:
        raise ValueError("Resolusi preview harus antara 8 dan 128.")

    if shape in {"Kubus", "Balok"}:
        if shape == "Kubus":
            side = float(dimensions.get("sisi", 0))
            lx = ly = lz = side
        else:
            lx = float(dimensions.get("panjang", 0))
            ly = float(dimensions.get("lebar", 0))
            lz = float(dimensions.get("tinggi", 0))
        if min(lx, ly, lz) <= 0 or not np.all(np.isfinite([lx, ly, lz])):
            raise ValueError("Semua dimensi harus berupa angka positif.")
        x, y, z = lx/2, ly/2, lz/2
        vertices = np.array([
            [-x,-y,-z], [x,-y,-z], [x,y,-z], [-x,y,-z],
            [-x,-y,z], [x,-y,z], [x,y,z], [-x,y,z],
        ], dtype=float)
        faces = np.array([
            [0,2,1],[0,3,2], [4,5,6],[4,6,7],
            [0,1,5],[0,5,4], [1,2,6],[1,6,5],
            [2,3,7],[2,7,6], [3,0,4],[3,4,7],
        ], dtype=int)
    else:
        radius = float(dimensions.get("radius", 0))
        height = float(dimensions.get("tinggi", 0))
        if min(radius, height) <= 0 or not np.all(np.isfinite([radius, height])):
            raise ValueError("Radius dan tinggi harus berupa angka positif.")
        angles = np.linspace(0, 2*np.pi, resolution, endpoint=False)
        z0, z1 = -height/2, height/2
        lower = np.column_stack((radius*np.cos(angles), radius*np.sin(angles), np.full(resolution,z0)))
        upper = np.column_stack((radius*np.cos(angles), radius*np.sin(angles), np.full(resolution,z1)))
        vertices = np.vstack((lower, upper, [[0,0,z0],[0,0,z1]]))
        bottom_center, top_center = 2*resolution, 2*resolution+1
        triangles = []
        for i in range(resolution):
            j = (i+1) % resolution
            triangles.extend([
                [i,j,resolution+j], [i,resolution+j,resolution+i],
                [bottom_center,j,i], [top_center,resolution+i,resolution+j],
            ])
        faces = np.asarray(triangles, dtype=int)
        lx = ly = 2*radius
        lz = height

    check_cancel(cancel_event)
    if progress_callback:
        progress_callback(1, 1, None)
    return {
        "shape": shape, "vertices": vertices, "faces": faces,
        "dimensions_m": {"x": float(lx), "y": float(ly), "z": float(lz)},
        "vertex_count": int(len(vertices)), "face_count": int(len(faces)),
    }
