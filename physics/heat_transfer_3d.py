"""Prototype solver konduksi panas 3D berbasis finite difference.

Model: material homogen isotropik, properti konstan, sumber panas volumetrik
seragam, dan temperatur Dirichlet pada keenam sisi balok.
Array temperatur memakai urutan (z, y, x).
"""
import numpy as np
from physics.worker import check_cancel


def _validate(nx, ny, nz, lx, ly, lz, conductivity, boundary):
    if min(nx, ny, nz) < 3:
        raise ValueError("Grid X, Y, dan Z minimal 3.")
    if not np.isfinite([lx, ly, lz, conductivity]).all():
        raise ValueError("Dimensi dan konduktivitas harus berupa angka finite.")
    if min(lx, ly, lz, conductivity) <= 0:
        raise ValueError("Dimensi domain dan konduktivitas harus positif.")
    required = {"x_min", "x_max", "y_min", "y_max", "z_min", "z_max"}
    if not required.issubset(boundary):
        raise ValueError("Boundary harus berisi enam sisi: x_min/x_max, y_min/y_max, z_min/z_max.")
    if any(not np.isfinite(float(boundary[key])) for key in required):
        raise ValueError("Temperatur boundary harus berupa angka finite.")


def _apply_boundaries(T, boundary):
    """Terapkan temperatur tetap; nilai edge/corner adalah rata-rata sisi terkait."""
    total = np.zeros_like(T)
    count = np.zeros_like(T)
    faces = (
        (T[:, :, 0], "x_min"), (T[:, :, -1], "x_max"),
        (T[:, 0, :], "y_min"), (T[:, -1, :], "y_max"),
        (T[0, :, :], "z_min"), (T[-1, :, :], "z_max"),
    )
    totals = (
        (total[:, :, 0], "x_min"), (total[:, :, -1], "x_max"),
        (total[:, 0, :], "y_min"), (total[:, -1, :], "y_max"),
        (total[0, :, :], "z_min"), (total[-1, :, :], "z_max"),
    )
    counts = (
        count[:, :, 0], count[:, :, -1], count[:, 0, :],
        count[:, -1, :], count[0, :, :], count[-1, :, :],
    )
    for (_, key), (target, _), counter in zip(faces, totals, counts):
        target += float(boundary[key])
        counter += 1.0
    mask = count > 0
    T[mask] = total[mask] / count[mask]
    return T


def _grid(nx, ny, nz, lx, ly, lz):
    return lx / (nx - 1), ly / (ny - 1), lz / (nz - 1)


def solve_steady_state_3d(
    nx, ny, nz, lx, ly, lz, conductivity, heat_generation, boundary,
    initial_temperature=25.0, tolerance=1e-6, max_iterations=30000, progress_callback=None, cancel_event=None,
):
    """Selesaikan ∇²T + q_vol/k = 0 dengan iterasi Jacobi 3D."""
    _validate(nx, ny, nz, lx, ly, lz, conductivity, boundary)
    if not np.isfinite([heat_generation, initial_temperature, tolerance]).all() or tolerance <= 0 or max_iterations < 1:
        raise ValueError("Toleransi, iterasi, dan konduktivitas harus positif.")
    dx, dy, dz = _grid(nx, ny, nz, lx, ly, lz)
    ix, iy, iz = 1 / dx**2, 1 / dy**2, 1 / dz**2
    denominator = 2 * (ix + iy + iz)
    source = heat_generation / conductivity
    T = np.full((nz, ny, nx), float(initial_temperature), dtype=float)
    _apply_boundaries(T, boundary)
    converged = False
    delta = float("inf")
    for iteration in range(1, int(max_iterations) + 1):
        check_cancel(cancel_event)
        old = T.copy()
        T[1:-1, 1:-1, 1:-1] = (
            (old[1:-1, 1:-1, 2:] + old[1:-1, 1:-1, :-2]) * ix
            + (old[1:-1, 2:, 1:-1] + old[1:-1, :-2, 1:-1]) * iy
            + (old[2:, 1:-1, 1:-1] + old[:-2, 1:-1, 1:-1]) * iz
            + source
        ) / denominator
        _apply_boundaries(T, boundary)
        delta = float(np.max(np.abs(T[1:-1, 1:-1, 1:-1] - old[1:-1, 1:-1, 1:-1])))
        if progress_callback and (iteration == 1 or iteration % max(1, max_iterations // 100) == 0 or delta < tolerance or iteration == max_iterations):
            progress_callback(iteration, max_iterations, delta)
        if delta < tolerance:
            converged = True
            break
    return {
        "temperature": T, "iterations": iteration, "converged": converged,
        "last_delta": delta, "dx": dx, "dy": dy, "dz": dz,
        "shape_zyx": T.shape,
    }


def stable_time_step_3d(conductivity, density, specific_heat, dx, dy, dz):
    """Batas konservatif untuk skema eksplisit 3D: Fo_x + Fo_y + Fo_z <= 1/2."""
    if min(conductivity, density, specific_heat, dx, dy, dz) <= 0:
        raise ValueError("Properti material dan ukuran grid harus positif.")
    alpha = conductivity / (density * specific_heat)
    return 1.0 / (2.0 * alpha * (1.0 / dx**2 + 1.0 / dy**2 + 1.0 / dz**2))


def solve_transient_3d(
    nx, ny, nz, lx, ly, lz, conductivity, density, specific_heat,
    heat_generation, boundary, initial_temperature, total_time, max_dt,
    snapshot_count=9, progress_callback=None, cancel_event=None,
):
    """Selesaikan konduksi panas transient eksplisit dan simpan snapshot terbatas."""
    _validate(nx, ny, nz, lx, ly, lz, conductivity, boundary)
    if not np.isfinite([density, specific_heat, total_time, max_dt, heat_generation, initial_temperature]).all():
        raise ValueError("Parameter transient harus berupa angka finite.")
    if min(density, specific_heat, total_time, max_dt) <= 0:
        raise ValueError("rho, cp, total_time, dan max_dt harus positif.")
    dx, dy, dz = _grid(nx, ny, nz, lx, ly, lz)
    alpha = conductivity / (density * specific_heat)
    dt_limit = stable_time_step_3d(conductivity, density, specific_heat, dx, dy, dz)
    steps = max(1, int(np.ceil(total_time / min(max_dt, dt_limit))))
    if steps > 200000:
        raise ValueError("Jumlah langkah melebihi 200000; kurangi durasi atau perbesar grid spacing.")
    dt = total_time / steps
    fx, fy, fz = alpha * dt / dx**2, alpha * dt / dy**2, alpha * dt / dz**2
    if fx + fy + fz > 0.5 + 1e-12:
        raise ValueError("Langkah waktu melampaui batas stabilitas eksplisit 3D.")
    T = np.full((nz, ny, nx), float(initial_temperature), dtype=float)
    _apply_boundaries(T, boundary)
    count = max(2, min(int(snapshot_count), 25))
    target_steps = set(np.linspace(0, steps, count, dtype=int).tolist())
    snapshots, snapshot_times = [], []
    if 0 in target_steps:
        snapshots.append(T.copy())
        snapshot_times.append(0.0)
    for step in range(1, steps + 1):
        check_cancel(cancel_event)
        old = T.copy()
        T[1:-1, 1:-1, 1:-1] = old[1:-1, 1:-1, 1:-1] + dt * (
            alpha * (
                (old[1:-1, 1:-1, 2:] - 2 * old[1:-1, 1:-1, 1:-1] + old[1:-1, 1:-1, :-2]) / dx**2
                + (old[1:-1, 2:, 1:-1] - 2 * old[1:-1, 1:-1, 1:-1] + old[1:-1, :-2, 1:-1]) / dy**2
                + (old[2:, 1:-1, 1:-1] - 2 * old[1:-1, 1:-1, 1:-1] + old[:-2, 1:-1, 1:-1]) / dz**2
            ) + heat_generation / (density * specific_heat)
        )
        _apply_boundaries(T, boundary)
        if step in target_steps:
            snapshots.append(T.copy())
            snapshot_times.append(step * dt)
        if progress_callback and (step == 1 or step % max(1, steps // 100) == 0 or step == steps):
            progress_callback(step, steps, None)
    return {
        "temperature": T, "simulated_time": steps * dt, "dt_actual": dt,
        "dt_stability_limit": dt_limit, "steps": steps, "alpha": alpha,
        "fourier_sum": fx + fy + fz, "snapshots": snapshots,
        "snapshot_times": snapshot_times, "dx": dx, "dy": dy, "dz": dz,
        "converged": True,
    }


def calculate_heat_flux_3d(temperature, conductivity, dx, dy, dz):
    """Hitung q=-k∇T; output qx, qy, qz, dan magnitudo dalam W/m²."""
    T = np.asarray(temperature, dtype=float)
    if T.ndim != 3 or min(T.shape) < 3:
        raise ValueError("Field temperatur harus berupa array 3D minimal 3×3×3.")
    if min(conductivity, dx, dy, dz) <= 0:
        raise ValueError("Konduktivitas dan spacing harus positif.")
    dT_dz, dT_dy, dT_dx = np.gradient(T, dz, dy, dx, edge_order=2)
    qx, qy, qz = -conductivity * dT_dx, -conductivity * dT_dy, -conductivity * dT_dz
    magnitude = np.sqrt(qx**2 + qy**2 + qz**2)
    return qx, qy, qz, magnitude
