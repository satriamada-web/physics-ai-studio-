"""Uji analitik awal untuk solver konduksi panas 3D."""
import numpy as np
from physics.heat_transfer_3d import (
    solve_steady_state_3d, solve_transient_3d, calculate_heat_flux_3d,
)

BOUNDARY_50 = {
    "x_min": 50.0, "x_max": 50.0, "y_min": 50.0,
    "y_max": 50.0, "z_min": 50.0, "z_max": 50.0,
}


def run_3d_verification_suite():
    """Verifikasi medan seragam dan Hukum Fourier pada medan linear 3D."""
    results = []
    steady = solve_steady_state_3d(
        9, 9, 9, 0.1, 0.1, 0.1, 16.2, 0.0, BOUNDARY_50,
        initial_temperature=50.0, tolerance=1e-10,
    )
    error = float(np.max(np.abs(steady["temperature"] - 50.0)))
    results.append({
        "Uji": "Steady-state 3D temperatur seragam",
        "Error maksimum": error, "Toleransi": 1e-8,
        "Status": "LULUS" if steady["converged"] and error <= 1e-8 else "GAGAL",
    })
    transient = solve_transient_3d(
        9, 9, 9, 0.1, 0.1, 0.1, 16.2, 8000.0, 500.0, 0.0,
        BOUNDARY_50, 50.0, 0.1, 0.5,
    )
    error = float(np.max(np.abs(transient["temperature"] - 50.0)))
    results.append({
        "Uji": "Transient 3D temperatur seragam",
        "Error maksimum": error, "Toleransi": 1e-8,
        "Status": "LULUS" if error <= 1e-8 else "GAGAL",
    })
    nz, ny, nx = 7, 8, 9
    dx, dy, dz = 0.02, 0.03, 0.04
    z, y, x = np.meshgrid(np.arange(nz)*dz, np.arange(ny)*dy, np.arange(nx)*dx, indexing="ij")
    field = 100.0 - 200.0*x + 75.0*y + 30.0*z
    qx, qy, qz, qmag = calculate_heat_flux_3d(field, 10.0, dx, dy, dz)
    error = max(
        float(np.max(np.abs(qx - 2000.0))),
        float(np.max(np.abs(qy + 750.0))),
        float(np.max(np.abs(qz + 300.0))),
        float(np.max(np.abs(qmag - np.sqrt(2000.0**2 + 750.0**2 + 300.0**2)))),
    )
    results.append({
        "Uji": "Hukum Fourier 3D pada medan linear",
        "Error maksimum": error, "Toleransi": 1e-8,
        "Status": "LULUS" if error <= 1e-8 else "GAGAL",
    })
    return results
