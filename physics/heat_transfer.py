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


def solve_transient(nx, ny, lx, ly, conductivity, density, specific_heat,
                    heat_generation, boundary, initial_temperature, total_time, dt):
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

    T = np.full((ny, nx), float(initial_temperature))
    _boundary(T, boundary)
    rx, ry = alpha * dt_actual / dx**2, alpha * dt_actual / dy**2
    source = heat_generation / (density * specific_heat)

    for _ in range(steps):
        old = T.copy()
        T[1:-1, 1:-1] = (
            old[1:-1, 1:-1]
            + rx * (old[1:-1, 2:] - 2 * old[1:-1, 1:-1] + old[1:-1, :-2])
            + ry * (old[2:, 1:-1] - 2 * old[1:-1, 1:-1] + old[:-2, 1:-1])
            + dt_actual * source
        )
        _boundary(T, boundary)

    return {
        "temperature": T,
        "steps": steps,
        "dt": dt_actual,
        "simulated_time": steps * dt_actual,
        "dx": dx,
        "dy": dy,
    }
