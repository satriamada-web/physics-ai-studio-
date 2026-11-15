"""Wind-driven heat transport on an imported voxel domain.

This MVP solves scalar advection-diffusion with a user-prescribed uniform wind
vector. It is NOT a Navier-Stokes CFD solver: velocity is imposed, pressure and
turbulence are not solved, and voxel walls are treated as adiabatic/no-flux.
"""
import numpy as np
from physics.worker import check_cancel


def _neighbor(array, axis, step):
    shifted = np.roll(array, step, axis=axis)
    edge = [slice(None)] * array.ndim
    edge[axis] = 0 if step == 1 else -1
    shifted[tuple(edge)] = np.nan
    return shifted


def solve_wind_heat_transport(
    inside_mask_zyx, dx, dy, dz, wind_speed, wind_azimuth_deg,
    wind_elevation_deg, inlet_temperature, initial_temperature,
    air_density=1.2, air_specific_heat=1005.0, air_conductivity=0.026,
    total_time=10.0, heat_source=0.0, snapshot_count=9,
    progress_callback=None, cancel_event=None, inlet_mask_zyx=None,
    outlet_mask_zyx=None,
):
    """Transient advection-diffusion of temperature in a voxelized air domain.

    Azimuth is measured from +X toward +Y; elevation is positive upward.
    Inlet temperature is imposed on active cells at upstream outer grid faces.
    """
    mask = np.asarray(inside_mask_zyx, dtype=bool)
    values = [dx, dy, dz, wind_speed, wind_azimuth_deg, wind_elevation_deg,
              inlet_temperature, initial_temperature, air_density,
              air_specific_heat, air_conductivity, total_time, heat_source]
    if mask.ndim != 3 or min(mask.shape) < 2 or not mask.any():
        raise ValueError("Mask domain udara harus berupa array 3D dan memiliki sel aktif.")
    if not np.isfinite(values).all():
        raise ValueError("Semua parameter aliran harus berupa angka finite.")
    if min(dx, dy, dz, air_density, air_specific_heat, air_conductivity, total_time) <= 0:
        raise ValueError("Ukuran sel, properti udara, dan durasi harus positif.")
    if wind_speed < 0:
        raise ValueError("Kecepatan angin tidak boleh negatif.")
    if wind_speed > 100:
        raise ValueError("Kecepatan angin MVP dibatasi 100 m/s.")
    az = np.deg2rad(wind_azimuth_deg)
    el = np.deg2rad(wind_elevation_deg)
    velocity = np.array([wind_speed*np.cos(el)*np.cos(az),
                         wind_speed*np.cos(el)*np.sin(az),
                         wind_speed*np.sin(el)], dtype=float)
    ux, uy, uz = velocity
    alpha = air_conductivity / (air_density * air_specific_heat)
    inv = (1.0/dx, 1.0/dy, 1.0/dz)
    adv_rate = abs(ux)/dx + abs(uy)/dy + abs(uz)/dz
    diff_rate = 2.0*alpha*(1.0/dx**2 + 1.0/dy**2 + 1.0/dz**2)
    dt_limit = min(0.45/(adv_rate + 1e-30), 0.45/(diff_rate + 1e-30))
    steps = max(1, int(np.ceil(total_time/dt_limit)))
    if steps > 100000:
        raise ValueError("Simulasi membutuhkan lebih dari 100.000 langkah. Kurangi durasi/kecepatan atau tingkatkan ukuran sel.")
    dt = total_time / steps
    nz, ny, nx = mask.shape
    if inlet_mask_zyx is None:
        inlet = np.zeros_like(mask)
        if ux > 0: inlet[:, :, 0] |= mask[:, :, 0]
        elif ux < 0: inlet[:, :, -1] |= mask[:, :, -1]
        if uy > 0: inlet[:, 0, :] |= mask[:, 0, :]
        elif uy < 0: inlet[:, -1, :] |= mask[:, -1, :]
        if uz > 0: inlet[0, :, :] |= mask[0, :, :]
        elif uz < 0: inlet[-1, :, :] |= mask[-1, :, :]
    else:
        inlet = np.asarray(inlet_mask_zyx, dtype=bool)
        if inlet.shape != mask.shape or np.any(inlet & ~mask):
            raise ValueError("Mask inlet harus sesuai bentuk domain dan berada di dalam domain aktif.")
    outlet = np.zeros_like(mask) if outlet_mask_zyx is None else np.asarray(outlet_mask_zyx, dtype=bool)
    if outlet.shape != mask.shape or np.any(outlet & ~mask):
        raise ValueError("Mask outlet harus sesuai bentuk domain dan berada di dalam domain aktif.")
    if np.any(inlet & outlet):
        raise ValueError("Area inlet dan outlet tidak boleh bertumpuk.")
    if wind_speed > 0 and not inlet.any():
        raise ValueError("Tidak ditemukan sel inlet pada sisi hulu domain. Periksa geometri atau arah angin.")
    T = np.full(mask.shape, float(initial_temperature), dtype=float)
    T[inlet] = float(inlet_temperature)

    def derivative(axis, component, spacing):
        if abs(component) < 1e-15:
            return np.zeros_like(T)
        if component > 0:
            prev = _neighbor(T, axis, 1)
            valid = np.roll(mask, 1, axis=axis)
            edge = [slice(None)] * 3; edge[axis] = 0
            valid[tuple(edge)] = False
            grad = np.zeros_like(T)
            use = mask & valid
            grad[use] = (T[use] - prev[use]) / spacing
            # At an upstream outer face, use the prescribed inlet state.
            face = [slice(None)] * 3; face[axis] = 0
            idx = tuple(face)
            # Only the explicitly selected inlet aperture receives inlet data.
            # Solid walls and obstacle faces use zero normal advective gradient.
            boundary_cells = inlet[idx] & mask[idx]
            grad[idx][boundary_cells] = (T[idx][boundary_cells] - inlet_temperature) / spacing
        else:
            nxt = _neighbor(T, axis, -1)
            valid = np.roll(mask, -1, axis=axis)
            edge = [slice(None)] * 3; edge[axis] = -1
            valid[tuple(edge)] = False
            grad = np.zeros_like(T)
            use = mask & valid
            grad[use] = (nxt[use] - T[use]) / spacing
            face = [slice(None)] * 3; face[axis] = -1
            idx = tuple(face)
            # Only the explicitly selected inlet aperture receives inlet data.
            # Other boundary cells remain zero-gradient (wall/outlet treatment).
            boundary_cells = inlet[idx] & mask[idx]
            grad[idx][boundary_cells] = (inlet_temperature - T[idx][boundary_cells]) / spacing
        return grad

    def laplacian_axis(axis, spacing):
        plus = _neighbor(T, axis, -1)
        minus = _neighbor(T, axis, 1)
        valid_plus = np.roll(mask, -1, axis=axis)
        valid_minus = np.roll(mask, 1, axis=axis)
        edge0 = [slice(None)]*3; edge0[axis] = 0
        edge1 = [slice(None)]*3; edge1[axis] = -1
        valid_minus[tuple(edge0)] = False
        valid_plus[tuple(edge1)] = False
        result = np.zeros_like(T)
        result[mask & valid_plus] += (plus[mask & valid_plus] - T[mask & valid_plus]) / spacing**2
        result[mask & valid_minus] += (minus[mask & valid_minus] - T[mask & valid_minus]) / spacing**2
        return result

    count = max(2, min(int(snapshot_count), 15))
    targets = set(np.linspace(0, steps, count, dtype=int).tolist())
    snapshots = [np.where(mask, T, np.nan)] if 0 in targets else []
    times = [0.0] if snapshots else []
    for step in range(1, steps+1):
        check_cancel(cancel_event)
        advection = -(ux*derivative(2, ux, dx) + uy*derivative(1, uy, dy) + uz*derivative(0, uz, dz))
        diffusion = alpha*(laplacian_axis(2, dx)+laplacian_axis(1, dy)+laplacian_axis(0, dz))
        T[mask] += dt*(advection[mask] + diffusion[mask] + heat_source/(air_density*air_specific_heat))
        if inlet.any():
            T[inlet] = float(inlet_temperature)
        if step in targets:
            snapshots.append(np.where(mask, T, np.nan))
            times.append(step*dt)
        if progress_callback and (step == 1 or step % max(1, steps//100) == 0 or step == steps):
            progress_callback(step, steps, None)
    return {
        "temperature": np.where(mask, T, np.nan),
        "snapshots": snapshots, "snapshot_times": times,
        "steps": steps, "dt_actual": dt, "dt_stability_limit": dt_limit,
        "velocity_m_s": velocity.tolist(), "wind_speed_m_s": float(wind_speed),
        "wind_azimuth_deg": float(wind_azimuth_deg),
        "wind_elevation_deg": float(wind_elevation_deg),
        "inlet_cell_count": int(inlet.sum()), "outlet_cell_count": int(outlet.sum()), "active_cell_count": int(mask.sum()),
        "alpha_m2_s": float(alpha), "converged": True,
        "model_note": "Prescribed-velocity advection-diffusion; no Navier-Stokes, pressure, turbulence, or-slip wall model.",
    }
