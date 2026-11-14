"""Diagnostik kestabilan untuk solver transient eksplisit 2D."""


def calculate_transient_diagnostics(conductivity, density, specific_heat, lx, ly, nx, ny, dt):
    """Hitung difusivitas termal, bilangan Fourier, dan rasio stabilitas."""
    values = (conductivity, density, specific_heat, lx, ly, dt)
    if any(value <= 0 for value in values):
        raise ValueError("Sifat material, ukuran domain, dan dt harus positif.")
    if nx < 3 or ny < 3:
        raise ValueError("Grid minimal 3 × 3.")

    dx = lx / (nx - 1)
    dy = ly / (ny - 1)
    alpha = conductivity / (density * specific_heat)
    dt_limit = 0.5 / (alpha * (1.0 / dx**2 + 1.0 / dy**2))
    fourier_x = alpha * dt / dx**2
    fourier_y = alpha * dt / dy**2
    ratio = dt / dt_limit

    return {
        "thermal_diffusivity": alpha,
        "dx": dx,
        "dy": dy,
        "dt_actual": dt,
        "dt_stability_limit": dt_limit,
        "fourier_x": fourier_x,
        "fourier_y": fourier_y,
        "fourier_sum": fourier_x + fourier_y,
        "stability_ratio": ratio,
        "stable": ratio <= 1.0 + 1e-10,
    }
