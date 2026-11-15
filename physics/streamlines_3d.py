"""Streamline tracing for voxelized 3D velocity fields.

Uses midpoint (RK2) integration and trilinear interpolation. Coordinates are
physical x,y,z; arrays are stored z,y,x[,component].
"""
import numpy as np


def trace_streamlines_3d(
    velocity_field_m_s, inside_mask_zyx, origin_xyz, spacing_xyz,
    seed_mask_zyx=None, seed_count=12, max_steps=1200,
    step_fraction=0.35, min_speed=1e-8,
):
    velocity = np.asarray(velocity_field_m_s, dtype=float)
    mask = np.asarray(inside_mask_zyx, dtype=bool)
    origin = np.asarray(origin_xyz, dtype=float)
    spacing = np.asarray(spacing_xyz, dtype=float)
    if mask.ndim != 3 or velocity.shape != mask.shape + (3,):
        raise ValueError("Medan kecepatan harus berukuran (nz, ny, nx, 3).")
    if origin.shape != (3,) or spacing.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("Origin dan spacing harus berupa vektor XYZ.")
    if not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Spacing XYZ harus positif dan finite.")
    if not np.isfinite(velocity[mask]).all():
        raise ValueError("Medan kecepatan aktif mengandung nilai non-finite.")
    if seed_count < 1 or max_steps < 1 or step_fraction <= 0:
        raise ValueError("Parameter integrasi streamline tidak valid.")
    seeds_mask = mask if seed_mask_zyx is None else np.asarray(seed_mask_zyx, dtype=bool)
    if seeds_mask.shape != mask.shape or np.any(seeds_mask & ~mask):
        raise ValueError("Mask seed harus berada di dalam domain aktif.")
    candidates = np.argwhere(seeds_mask)
    if len(candidates) == 0:
        return []

    # Deterministic, approximately even seed selection.
    indices = np.linspace(0, len(candidates)-1, min(int(seed_count), len(candidates)), dtype=int)
    seeds_zyx = candidates[indices]
    nz, ny, nx = mask.shape
    h = float(np.min(spacing) * step_fraction)
    lower = origin
    upper = origin + np.array([nx-1, ny-1, nz-1]) * spacing
    paths = []

    def interpolate(point):
        q = (point - origin) / spacing
        ix, iy, iz = q
        if ix < 0 or iy < 0 or iz < 0 or ix > nx-1 or iy > ny-1 or iz > nz-1:
            return None
        x0, y0, z0 = int(np.floor(ix)), int(np.floor(iy)), int(np.floor(iz))
        x1, y1, z1 = min(x0+1,nx-1), min(y0+1,ny-1), min(z0+1,nz-1)
        fx, fy, fz = ix-x0, iy-y0, iz-z0
        corners = ((z0,y0,x0,(1-fx)*(1-fy)*(1-fz)),
                   (z0,y0,x1,fx*(1-fy)*(1-fz)),
                   (z0,y1,x0,(1-fx)*fy*(1-fz)),
                   (z0,y1,x1,fx*fy*(1-fz)),
                   (z1,y0,x0,(1-fx)*(1-fy)*fz),
                   (z1,y0,x1,fx*(1-fy)*fz),
                   (z1,y1,x0,(1-fx)*fy*fz),
                   (z1,y1,x1,fx*fy*fz))
        result = np.zeros(3, dtype=float)
        total = 0.0
        for z,y,x,w in corners:
            if w > 1e-12:
                if not mask[z,y,x]:
                    return None
                result += w * velocity[z,y,x]
                total += w
        return result / total if total > 0 else None

    for seed in seeds_zyx:
        z,y,x = seed
        point = origin + np.array([x,y,z], dtype=float) * spacing
        path = [point.copy()]
        for _ in range(int(max_steps)):
            v1 = interpolate(point)
            if v1 is None:
                break
            speed = float(np.linalg.norm(v1))
            if not np.isfinite(speed) or speed <= min_speed:
                break
            midpoint = point + 0.5*h*v1/speed
            vmid = interpolate(midpoint)
            if vmid is None:
                break
            mid_speed = float(np.linalg.norm(vmid))
            if not np.isfinite(mid_speed) or mid_speed <= min_speed:
                break
            next_point = point + h*vmid/mid_speed
            if np.any(next_point < lower) or np.any(next_point > upper):
                break
            if interpolate(next_point) is None:
                break
            path.append(next_point.copy())
            point = next_point
        if len(path) >= 2:
            paths.append(np.asarray(path))
    return paths
