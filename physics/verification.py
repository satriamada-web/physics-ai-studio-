"""Pemeriksaan verifikasi dasar untuk solver Physics AI Studio."""
import numpy as np
from physics.heat_transfer import (
    solve_steady_state,
    solve_transient,
    stable_time_step,
    calculate_heat_flux,
    calculate_steady_residual,
)


def run_verification_suite():
    """Jalankan kasus uji dengan hasil analitik yang diketahui.

    Ini adalah verifikasi numerik dasar, bukan validasi terhadap eksperimen.
    """
    results = []

    # Kasus 1: seluruh batas dan kondisi awal sama -> solusi uniform.
    uniform_boundary = {
        "left": 50.0, "right": 50.0, "top": 50.0, "bottom": 50.0
    }
    steady = solve_steady_state(
        31, 31, 0.1, 0.1, 16.2, 0.0, uniform_boundary, 50.0
    )
    steady_error = float(np.max(np.abs(steady["temperature"] - 50.0)))
    steady_residual = calculate_steady_residual(steady["temperature"], 16.2, 0.1, 0.1, 0.0)
    residual_error = steady_residual["residual_max_abs"]
    results.append({
        "Uji": "Residual persamaan steady-state",
        "Error maksimum": residual_error,
        "Toleransi": 1e-8,
        "Status": "LULUS" if residual_error <= 1e-8 else "GAGAL",
        "Keterangan": "Medan temperatur seragam tanpa sumber memiliki residual nol",
    })
    results.append({
        "Uji": "Steady-state temperatur seragam",
        "Error maksimum": steady_error,
        "Toleransi": 1e-8,
        "Status": "LULUS" if steady["converged"] and steady_error <= 1e-8 else "GAGAL",
        "Keterangan": "Solusi analitik: 50 °C di seluruh domain",
    })

    # Kasus 2: keadaan setimbang seragam tidak boleh berubah saat transient.
    dx = 0.1 / 30
    dt_limit = stable_time_step(16.2, 8000.0, 500.0, dx, dx)
    transient = solve_transient(
        31, 31, 0.1, 0.1, 16.2, 8000.0, 500.0, 0.0,
        uniform_boundary, 50.0, 2.0, 0.9 * dt_limit
    )
    transient_error = float(np.max(np.abs(transient["temperature"] - 50.0)))
    results.append({
        "Uji": "Transient kondisi setimbang",
        "Error maksimum": transient_error,
        "Toleransi": 1e-8,
        "Status": "LULUS" if transient_error <= 1e-8 else "GAGAL",
        "Keterangan": "Temperatur seragam harus tetap 50 °C",
    })

    # Kasus 3: medan temperatur linear -> gradien dan fluks Fourier eksak.
    nx, ny = 31, 21
    lx, ly, conductivity = 0.3, 0.2, 10.0
    x = np.linspace(0.0, lx, nx)
    y = np.linspace(0.0, ly, ny)
    xx, yy = np.meshgrid(x, y)
    gradient_x, gradient_y = -200.0, 75.0
    temperature = 100.0 + gradient_x * xx + gradient_y * yy
    qx, qy, magnitude = calculate_heat_flux(
        temperature, conductivity, lx, ly
    )
    expected_qx = -conductivity * gradient_x
    expected_qy = -conductivity * gradient_y
    flux_error = max(
        float(np.max(np.abs(qx - expected_qx))),
        float(np.max(np.abs(qy - expected_qy))),
    )
    expected_magnitude = float(np.hypot(expected_qx, expected_qy))
    magnitude_error = float(np.max(np.abs(magnitude - expected_magnitude)))
    passed = flux_error <= 1e-8 and magnitude_error <= 1e-8
    results.append({
        "Uji": "Hukum Fourier pada medan linear",
        "Error maksimum": max(flux_error, magnitude_error),
        "Toleransi": 1e-8,
        "Status": "LULUS" if passed else "GAGAL",
        "Keterangan": (
            f"Nilai analitik: qx={expected_qx:.2f}, "
            f"qy={expected_qy:.2f}, |q|={expected_magnitude:.2f} W/m²"
        ),
    })

    return results
