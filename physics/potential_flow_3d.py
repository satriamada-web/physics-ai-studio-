"""Incompressible irrotational (potential-flow) approximation on a voxel grid.

This is a lightweight flow-field estimator, not a Navier-Stokes CFD solver.
It solves Laplace's equation for velocity potential with fixed inlet/outlet
potential and zero-normal-gradient treatment at solid/closed boundaries.
"""
import numpy as np
from physics.worker import check_cancel


def solve_potential_flow_3d(
    inside_mask_zyx, inlet_mask_zyx, outlet_mask_zyx,
    dx, dy, dz, reference_speed=1.0, max_iterations=2500,
    tolerance=1e-6, progress_callback=None, cancel_event=None,
):
    """Estimate a divergence-free potential-flow field around voxel obstacles.

    Inlet potential is 1, outlet potential is 0. The resulting -grad(phi)
    field is scaled so mean inlet-normal speed matches reference_speed.
    """
    mask = np.asarray(inside_mask_zyx, dtype=bool)
    inlet = np.asarray(inlet_mask_zyx, dtype=bool)
    outlet = np.asarray(outlet_mask_zyx, dtype=bool)
    spacing = np.asarray([dx, dy, dz], dtype=float)
    if mask.ndim != 3 or min(mask.shape) < 2 or not mask.any():
        raise ValueError("Domain aliran harus berupa mask 3D non-kosong.")
    if inlet.shape != mask.shape or outlet.shape != mask.shape:
        raise ValueError("Mask inlet/outlet harus sama dengan bentuk domain.")
    if np.any(inlet & ~mask) or np.any(outlet & ~mask) or np.any(inlet & outlet):
        raise ValueError("Inlet/outlet harus berada di domain aktif dan tidak bertumpuk.")
    if not inlet.any() or not outlet.any():
        raise ValueError("Domain harus memiliki inlet dan outlet.")
    if not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Ukuran sel harus positif dan finite.")
    if not np.isfinite(reference_speed) or reference_speed < 0 or reference_speed > 100:
        raise ValueError("Kecepatan referensi harus antara 0 dan 100 m/s.")
    if isinstance(max_iterations, bool) or int(max_iterations) < 1 or int(max_iterations) > 20000:
        raise ValueError("Iterasi harus antara 1 dan 20.000.")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Toleransi harus positif.")

    fixed = inlet | outlet
    phi = np.zeros(mask.shape, dtype=float)
    phi[inlet] = 1.0
    phi[outlet] = 0.0
    # Initial linear guess along the dominant inlet-to-outlet grid direction.
    coords = np.argwhere(inlet)
    out_coords = np.argwhere(outlet)
    delta = np.mean(out_coords, axis=0) - np.mean(coords, axis=0)
    axis = int(np.argmax(np.abs(delta)))
    line = np.linspace(1.0, 0.0, mask.shape[axis])
    reshape = [1, 1, 1]
    reshape[axis] = mask.shape[axis]
    phi[mask & ~fixed] = np.broadcast_to(line.reshape(reshape), mask.shape)[mask & ~fixed]

    inv_sq = (1.0 / spacing[2]**2, 1.0 / spacing[1]**2, 1.0 / spacing[0]**2)
    converged = False
    iterations = 0
    for iteration in range(1, int(max_iterations) + 1):
        check_cancel(cancel_event)
        weighted_sum = np.zeros_like(phi)
        weight_sum = np.zeros_like(phi)
        for ax, weight in ((2, inv_sq[0]), (1, inv_sq[1]), (0, inv_sq[2])):
            for shift in (-1, 1):
                neighbor = np.roll(phi, shift, axis=ax)
                valid = np.roll(mask, shift, axis=ax)
                edge = [slice(None)] * 3
                edge[ax] = 0 if shift == 1 else -1
                valid[tuple(edge)] = False
                weighted_sum[valid] += weight * neighbor[valid]
                weight_sum[valid] += weight
        update = mask & ~fixed & (weight_sum > 0)
        next_phi = phi.copy()
        next_phi[update] = weighted_sum[update] / weight_sum[update]
        next_phi[inlet] = 1.0
        next_phi[outlet] = 0.0
        change = float(np.max(np.abs(next_phi[update] - phi[update]))) if update.any() else 0.0
        phi = next_phi
        iterations = iteration
        if progress_callback and (iteration == 1 or iteration % 25 == 0 or change <= tolerance):
            progress_callback(iteration, int(max_iterations), change)
        if change <= tolerance:
            converged = True
            break

    def derivative(axis_index, spacing_value):
        plus = np.roll(phi, -1, axis=axis_index)
        minus = np.roll(phi, 1, axis=axis_index)
        valid_plus = np.roll(mask, -1, axis=axis_index)
        valid_minus = np.roll(mask, 1, axis=axis_index)
        edge0 = [slice(None)] * 3
        edge1 = [slice(None)] * 3
        edge0[axis_index] = 0
        edge1[axis_index] = -1
        valid_minus[tuple(edge0)] = False
        valid_plus[tuple(edge1)] = False
        both = mask & valid_plus & valid_minus
        only_plus = mask & valid_plus & ~valid_minus
        only_minus = mask & valid_minus & ~valid_plus
        grad = np.zeros_like(phi)
        grad[both] = (plus[both] - minus[both]) / (2.0 * spacing_value)
        grad[only_plus] = (plus[only_plus] - phi[only_plus]) / spacing_value
        grad[only_minus] = (phi[only_minus] - minus[only_minus]) / spacing_value
        return grad

    # Array axes are z,y,x while physical vector components are x,y,z.
    velocity = np.stack((
        -derivative(2, dx), -derivative(1, dy), -derivative(0, dz)
    ), axis=-1)
    velocity[~mask] = 0.0
    # Enforce zero normal velocity on faces adjacent to internal solid cells.
    for component, ax in ((0, 2), (1, 1), (2, 0)):
        for shift in (-1, 1):
            neighbor_mask = np.roll(mask, shift, axis=ax)
            edge = [slice(None)] * 3
            edge[ax] = 0 if shift == 1 else -1
            neighbor_mask[tuple(edge)] = True  # outer boundary is not a solid obstacle
            velocity[..., component][mask & ~neighbor_mask] = 0.0

    # Scale by mean speed on the selected inlet cells.
    inlet_values = velocity[inlet]
    measured = float(np.mean(np.linalg.norm(inlet_values, axis=1))) if len(inlet_values) else 0.0
    if reference_speed == 0:
        velocity[:] = 0.0
    elif measured > 1e-12:
        velocity *= float(reference_speed) / measured

    divergence = np.zeros(mask.shape, dtype=float)
    for component, ax, h in ((0, 2, dx), (1, 1, dy), (2, 0, dz)):
        field = velocity[..., component]
        plus = np.roll(field, -1, axis=ax)
        minus = np.roll(field, 1, axis=ax)
        vp = np.roll(mask, -1, axis=ax)
        vm = np.roll(mask, 1, axis=ax)
        e0 = [slice(None)] * 3
        e1 = [slice(None)] * 3
        e0[ax] = 0
        e1[ax] = -1
        vm[tuple(e0)] = False
        vp[tuple(e1)] = False
        both = mask & vp & vm
        onlyp = mask & vp & ~vm
        onlym = mask & vm & ~vp
        part = np.zeros(mask.shape)
        part[both] = (plus[both] - minus[both]) / (2*h)
        part[onlyp] = (plus[onlyp] - field[onlyp]) / h
        part[onlym] = (field[onlym] - minus[onlym]) / h
        divergence += part
    div_norm = float(np.sqrt(np.mean(divergence[mask]**2)))
    return {
        "velocity_field_m_s": velocity,
        "potential": np.where(mask, phi, np.nan),
        "iterations": iterations,
        "converged": bool(converged),
        "residual_max": float(change),
        "divergence_rms_s": div_norm,
        "active_cell_count": int(mask.sum()),
        "inlet_cell_count": int(inlet.sum()),
        "outlet_cell_count": int(outlet.sum()),
        "reference_speed_m_s": float(reference_speed),
        "model_note": "Potential-flow approximation (Laplace potential); not Navier-Stokes, pressure-coupled viscous CFD, or turbulence model.",
    }
