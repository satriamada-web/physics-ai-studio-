"""Solver konduksi panas 2D untuk MVP Physics AI Studio.

Asumsi: material homogen dan isotropik, sifat material konstan,
temperatur tetap pada keempat sisi, tanpa konveksi atau radiasi.
"""
import numpy as np


def _validate(nx, ny, lx, ly, k, boundary):
    if nx < 3 or ny < 3:
        raise ValueError("Grid X dan Y minimal 3.")
    if lx <= 0 or ly <= 0 or k <= 0:
        raise ValueError("Panjang domain dan konduktivitas harus positif.")
    if not {"left", "right", "top", "bottom"}.issubset(boundary):
        raise ValueError("Kondisi batas harus memiliki left, right, top, bottom.")


def _boundary(T, b):
    T[:, 0] = b["left"]
    T[:, -1] = b["right"]
    T[0, :] = b["bottom"]
    T[-1, :] = b["top"]
    T[0, 0] = 0.5 * (b["bottom"] + b["left"])
    T[0, -1] = 0.5 * (b["bottom"] + b["right"])
    T[-1, 0] = 0.5 * (b["top"] + b["left"])
    T[-1, -1] = 0.5 * (b["top"] + b["right"])
    return T


def solve_steady_state(nx, ny, lx, ly, conductivity, heat_generation, boundary,
                       initial_temperature=25.0, tolerance=1e-6, max_iterations=30000):
    """Persamaan steady-state: Laplacian(T) + q_vol/k = 0; iterasi Jacobi."""
    _validate(nx, ny, lx, ly, conductivity, boundary)
    dx, dy = lx / (nx - 1), ly / (ny - 1)
    T = np.full((ny, nx), float(initial_temperature))
    _boundary(T, boundary)
    dx2, dy2 = dx * dx, dy * dy
    den = 2.0 / dx2 + 2.0 / dy2
    source = heat_generation / conductivity
    last_delta = float("inf")
    converged = False
    for iteration in range(1, max_iterations + 1):
        old = T.copy()
        T[1:-1, 1:-1] = (
            (old[1:-1, 2:] + old[1:-1, :-2]) / dx2
            + (old[2:, 1:-1] + old[:-2, 1:-1]) / dy2
            + source
        ) / den
        _boundary(T, boundary)
        last_delta = float(np.max(np.abs(T[1:-1, 1:-1] - old[1:-1, 1:-1])))
        if last_delta < tolerance:
            converged = True
            break
    return {
        "temperature": T,
        "iterations": iteration,
        "converged": converged,
        "last_delta": last_delta,
        "dx": dx,
        "dy": dy,
    }


def stable_time_step(conductivity, density, specific_heat, dx, dy):
    """Batas stabilitas skema eksplisit 2D."""
    if min(conductivity, density, specific_heat, dx, dy) <= 0:
        raise ValueError("Sifat material dan ukuran grid harus positif.")
    alpha = conductivity / (density * specific_heat)
    return 0.5 / (alpha * (1.0 / dx**2 + 1.0 / dy**2))


def calculate_transient_diagnostics(conductivity, density, specific_heat, lx, ly, nx, ny, dt):
    """Hitung bilangan Fourier dan rasio batas stabilitas untuk skema eksplisit 2D."""
    if min(conductivity, density, specific_heat, lx, ly, dt) <= 0:
        raise ValueError("Sifat material, ukuran domain, dan dt harus positif.")
    if nx < 3 or ny < 3:
        raise ValueError("Grid minimal 3 × 3.")
    dx, dy = lx / (nx - 1), ly / (ny - 1)
    alpha = conductivity / (density * specific_heat)
    dt_limit = stable_time_step(conductivity, density, specific_heat, dx, dy)
    fourier_x = alpha * dt / dx**2
    fourier_y = alpha * dt / dy**2
    stability_ratio = dt / dt_limit
    return {
        "thermal_diffusivity": alpha, "dx": dx, "dy": dy,
        "dt_actual": dt, "dt_stability_limit": dt_limit,
        "fourier_x": fourier_x, "fourier_y": fourier_y,
        "fourier_sum": fourier_x + fourier_y,
        "stability_ratio": stability_ratio,
        "stable": stability_ratio <= 1.0 + 1e-10,
    }

def solve_transient(nx, ny, lx, ly, conductivity, density, specific_heat,
                    heat_generation, boundary, initial_temperature, total_time, dt,
                    snapshot_count=9, probe_x=None, probe_y=None):
    """Solver eksplisit 2D dengan langkah waktu yang disesuaikan agar t akhir tepat.

    dt yang diterima diperlakukan sebagai batas maksimum langkah waktu.
    Jumlah langkah dibulatkan ke atas, lalu dt aktual dihitung ulang sebagai
    total_time / steps. Dengan demikian waktu simulasi tidak melewati target.
    """
    _validate(nx, ny, lx, ly, conductivity, boundary)
    if min(density, specific_heat, total_time, dt) <= 0:
        raise ValueError("rho, cp, waktu, dan dt harus positif.")

    dx, dy = lx / (nx - 1), ly / (ny - 1)
    alpha = conductivity / (density * specific_heat)
    dt_max = stable_time_step(conductivity, density, specific_heat, dx, dy)
    if dt > dt_max * (1.0 + 1e-10):
        raise ValueError(f"dt tidak stabil. Gunakan dt <= {dt_max:.6g} detik.")

    steps = max(1, int(np.ceil(total_time / dt)))
    if steps > 20000:
        raise ValueError("Jumlah langkah melebihi batas 20.000.")
    dt_actual = total_time / steps
    if dt_actual > dt_max * (1.0 + 1e-10):
        raise ValueError("Langkah waktu aktual melampaui batas stabilitas.")

    probe_x = nx // 2 if probe_x is None else int(probe_x)
    probe_y = ny // 2 if probe_y is None else int(probe_y)
    if not (0 <= probe_x < nx and 0 <= probe_y < ny):
        raise ValueError("Indeks titik pemantauan berada di luar grid.")

    T = np.full((ny, nx), float(initial_temperature))
    _boundary(T, boundary)
    probe_times = [0.0]
    probe_temperatures = [float(T[probe_y, probe_x])]
    rx, ry = alpha * dt_actual / dx**2, alpha * dt_actual / dy**2
    source = heat_generation / (density * specific_heat)

    snapshot_steps = np.unique(np.linspace(
        0, steps, num=min(max(2, int(snapshot_count)), steps + 1), dtype=int
    ))
    snapshots = [T.copy()]
    snapshot_times = [0.0]
    snapshot_lookup = set(snapshot_steps[1:].tolist())

    for step in range(1, steps + 1):
        old = T.copy()
        T[1:-1, 1:-1] = (
            old[1:-1, 1:-1]
            + rx * (old[1:-1, 2:] - 2 * old[1:-1, 1:-1] + old[1:-1, :-2])
            + ry * (old[2:, 1:-1] - 2 * old[1:-1, 1:-1] + old[:-2, 1:-1])
            + dt_actual * source
        )
        _boundary(T, boundary)
        probe_times.append(step * dt_actual)
        probe_temperatures.append(float(T[probe_y, probe_x]))
        if step in snapshot_lookup:
            snapshots.append(T.copy())
            snapshot_times.append(step * dt_actual)

    return {
        "temperature": T,
        "probe_x": probe_x,
        "probe_y": probe_y,
        "probe_times": probe_times,
        "probe_temperatures": probe_temperatures,
        "snapshots": snapshots,
        "snapshot_times": snapshot_times,
        "steps": steps,
        "dt": dt_actual,
        "simulated_time": steps * dt_actual,
        "dx": dx,
        "dy": dy,
    }

def calculate_heat_flux(temperature, conductivity, lx, ly):
    """Hitung fluks panas konduktif q = -k grad(T) pada grid Cartesian.

    Parameter:
        temperature: array 2D dengan bentuk (ny, nx), dalam °C atau K
        conductivity: konduktivitas termal konstan, W/(m·K)
        lx, ly: panjang domain dalam meter

    Returns:
        qx, qy, magnitude dalam W/m². Komponen positif mengikuti arah +x dan +y.
    """
    T = np.asarray(temperature, dtype=float)
    if T.ndim != 2 or min(T.shape) < 3:
        raise ValueError("Field temperatur harus berupa array 2D minimal 3 × 3.")
    if conductivity <= 0 or lx <= 0 or ly <= 0:
        raise ValueError("Konduktivitas dan ukuran domain harus positif.")
    ny, nx = T.shape
    dx = lx / (nx - 1)
    dy = ly / (ny - 1)
    dT_dy, dT_dx = np.gradient(T, dy, dx, edge_order=2)
    qx = -float(conductivity) * dT_dx
    qy = -float(conductivity) * dT_dy
    magnitude = np.hypot(qx, qy)
    return qx, qy, magnitude

def calculate_steady_residual(temperature, conductivity, lx, ly, heat_generation=0.0):
    """Hitung residual diskret persamaan steady-state pada node interior.

    Residual R = d²T/dx² + d²T/dy² + q'''/k, satuan K/m².
    Nilai mendekati nol menunjukkan persamaan beda hingga dipenuhi.
    Batas domain tidak dimasukkan karena residual PDE dihitung pada node interior.
    """
    T = np.asarray(temperature, dtype=float)
    if T.ndim != 2 or min(T.shape) < 3:
        raise ValueError("Field temperatur harus berupa array 2D minimal 3 × 3.")
    if min(conductivity, lx, ly) <= 0:
        raise ValueError("Konduktivitas dan ukuran domain harus positif.")
    if not np.isfinite(T).all() or not np.isfinite(heat_generation):
        raise ValueError("Temperatur dan pembangkitan panas harus bernilai hingga.")
    ny, nx = T.shape
    dx = lx / (nx - 1)
    dy = ly / (ny - 1)
    laplacian = (
        (T[1:-1, 2:] - 2.0 * T[1:-1, 1:-1] + T[1:-1, :-2]) / dx**2
        + (T[2:, 1:-1] - 2.0 * T[1:-1, 1:-1] + T[:-2, 1:-1]) / dy**2
    )
    residual = laplacian + float(heat_generation) / float(conductivity)
    return {
        "residual_max_abs": float(np.max(np.abs(residual))),
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
        "residual_field": residual,
    }
