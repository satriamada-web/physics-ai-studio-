"""Axis-aligned room air-domain generator with explicit inlet/outlet apertures."""
import numpy as np


def create_room_domain(length_x=6.0, length_y=4.0, height=3.0,
                       nx=24, ny=16, nz=12,
                       inlet_wall="x_min", outlet_wall="x_max",
                       opening_width_fraction=0.35,
                       opening_height_fraction=0.55,
                       max_cells=50000):
    """Create a cell-centred rectangular air domain and wall aperture masks.

    The room is represented as air cells; walls are impermeable except for
    rectangular inlet/outlet patches on opposite faces.
    """
    dims = np.asarray([length_x, length_y, height], dtype=float)
    counts = np.asarray([nx, ny, nz], dtype=int)
    if not np.isfinite(dims).all() or np.any(dims <= 0):
        raise ValueError("Panjang, lebar, dan tinggi ruangan harus positif.")
    if np.any(counts < 4) or np.any(counts > 50):
        raise ValueError("Jumlah sel setiap sumbu harus antara 4 dan 50.")
    total = int(np.prod(counts))
    if total > int(max_cells):
        raise ValueError(f"Jumlah sel {total:,} melebihi batas {max_cells:,}. Kurangi resolusi.")
    valid_pairs = {
        "x_min": "x_max", "x_max": "x_min",
        "y_min": "y_max", "y_max": "y_min",
        "z_min": "z_max", "z_max": "z_min",
    }
    if inlet_wall not in valid_pairs or valid_pairs[inlet_wall] != outlet_wall:
        raise ValueError("Inlet dan outlet harus berada pada dua sisi berlawanan.")
    for value in (opening_width_fraction, opening_height_fraction):
        if not np.isfinite(value) or value <= 0 or value > 1:
            raise ValueError("Ukuran bukaan harus antara 0 dan 1 dari dimensi dinding.")

    dx, dy, dz = dims / counts
    x = (np.arange(nx) + 0.5) * dx
    y = (np.arange(ny) + 0.5) * dy
    z = (np.arange(nz) + 0.5) * dz
    mask = np.ones((nz, ny, nx), dtype=bool)
    inlet = np.zeros_like(mask)
    outlet = np.zeros_like(mask)

    axis_name = inlet_wall[0]
    side = inlet_wall.endswith("min")
    if axis_name == "x":
        face_in = (slice(None), slice(None), 0 if side else -1)
        face_out = (slice(None), slice(None), -1 if side else 0)
        # Width along Y, height along Z.
        y0 = (1-opening_width_fraction)/2
        z0 = (1-opening_height_fraction)/2
        yi = (y >= y0*length_y) & (y <= (y0+opening_width_fraction)*length_y)
        zi = (z >= z0*height) & (z <= (z0+opening_height_fraction)*height)
        patch = zi[:,None] & yi[None,:]
        inlet[face_in] = patch
        outlet[face_out] = patch
        azimuth = 0.0 if side else 180.0
    elif axis_name == "y":
        face_in = (slice(None), 0 if side else -1, slice(None))
        face_out = (slice(None), -1 if side else 0, slice(None))
        x0 = (1-opening_width_fraction)/2
        z0 = (1-opening_height_fraction)/2
        xi = (x >= x0*length_x) & (x <= (x0+opening_width_fraction)*length_x)
        zi = (z >= z0*height) & (z <= (z0+opening_height_fraction)*height)
        patch = zi[:,None] & xi[None,:]
        inlet[face_in] = patch
        outlet[face_out] = patch
        azimuth = 90.0 if side else -90.0
    else:
        face_in = (0 if side else -1, slice(None), slice(None))
        face_out = (-1 if side else 0, slice(None), slice(None))
        x0 = (1-opening_width_fraction)/2
        y0 = (1-opening_width_fraction)/2
        xi = (x >= x0*length_x) & (x <= (x0+opening_width_fraction)*length_x)
        yi = (y >= y0*length_y) & (y <= (y0+opening_width_fraction)*length_y)
        patch = yi[:,None] & xi[None,:]
        inlet[face_in] = patch
        outlet[face_out] = patch
        azimuth = 0.0

    centers_grid = np.stack(np.meshgrid(x, y, z, indexing="xy"), axis=-1)
    # meshgrid above is (ny,nx,nz); construct canonical z,y,x coordinate arrays.
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    centers = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    velocity_direction = {
        "x_min": [1.0, 0.0, 0.0], "x_max": [-1.0, 0.0, 0.0],
        "y_min": [0.0, 1.0, 0.0], "y_max": [0.0, -1.0, 0.0],
        "z_min": [0.0, 0.0, 1.0], "z_max": [0.0, 0.0, -1.0],
    }[inlet_wall]
    return {
        "shape": "Rectangular room air domain",
        "inside_mask_zyx": mask,
        "inlet_mask_zyx": inlet,
        "outlet_mask_zyx": outlet,
        "cell_centers": centers,
        "x": x, "y": y, "z": z,
        "nx": int(nx), "ny": int(ny), "nz": int(nz),
        "dx": float(dx), "dy": float(dy), "dz": float(dz),
        "active_cell_count": total,
        "candidate_cell_count": total,
        "volume_estimate_m3": float(np.prod(dims)),
        "bounds_min_m": [0.0, 0.0, 0.0],
        "bounds_max_m": dims.tolist(),
        "inlet_wall": inlet_wall, "outlet_wall": outlet_wall,
        "inlet_cell_count": int(inlet.sum()),
        "outlet_cell_count": int(outlet.sum()),
        "velocity_direction": velocity_direction,
        "mesh_type": "rectangular room Cartesian air-domain",
        "boundary_note": "Inlet/outlet rectangular apertures; remaining room boundaries are impermeable in this MVP.",
    }
