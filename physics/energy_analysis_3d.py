"""Approximate energy accounting for Cartesian 3D heat-conduction results."""
import numpy as np


def _node_weights(n):
    weights = np.ones(n, dtype=float)
    weights[0] = weights[-1] = 0.5
    return weights


def _initial_field(shape, initial_temperature, boundary):
    nz, ny, nx = shape
    field = np.full(shape, float(initial_temperature), dtype=float)
    total = np.zeros(shape, dtype=float)
    count = np.zeros(shape, dtype=float)
    faces = (
        (total[:, :, 0], count[:, :, 0], "x_min"),
        (total[:, :, -1], count[:, :, -1], "x_max"),
        (total[:, 0, :], count[:, 0, :], "y_min"),
        (total[:, -1, :], count[:, -1, :], "y_max"),
        (total[0, :, :], count[0, :, :], "z_min"),
        (total[-1, :, :], count[-1, :, :], "z_max"),
    )
    for values, counts, key in faces:
        values += float(boundary[key])
        counts += 1.0
    mask = count > 0
    field[mask] = total[mask] / count[mask]
    return field


def _outward_power(temperature, conductivity, dx, dy, dz):
    t = np.asarray(temperature, dtype=float)
    dtdz, dtdy, dtdx = np.gradient(t, dz, dy, dx, edge_order=2)
    qx, qy, qz = -conductivity * dtdx, -conductivity * dtdy, -conductivity * dtdz
    wx, wy, wz = _node_weights(t.shape[2]), _node_weights(t.shape[1]), _node_weights(t.shape[0])
    # Trapezoidal surface integration; edges have half weights on each face.
    px = (
        np.sum((-qx[:, :, 0]) * wz[:, None] * wy[None, :])
        + np.sum(qx[:, :, -1] * wz[:, None] * wy[None, :])
    ) * dy * dz
    py = (
        np.sum((-qy[:, 0, :]) * wz[:, None] * wx[None, :])
        + np.sum(qy[:, -1, :] * wz[:, None] * wx[None, :])
    ) * dx * dz
    pz = (
        np.sum((-qz[0, :, :]) * wy[:, None] * wx[None, :])
        + np.sum(qz[-1, :, :] * wy[:, None] * wx[None, :])
    ) * dx * dy
    return float(px + py + pz), {
        "x_faces_W": float(px), "y_faces_W": float(py), "z_faces_W": float(pz)
    }


def analyze_energy_balance_3d(
    temperature, conductivity, density, specific_heat, heat_generation,
    dx, dy, dz, initial_temperature, boundary,
    snapshots=None, snapshot_times=None,
):
    """Return approximate control-volume energy accounting for a rectangular grid."""
    final_t = np.asarray(temperature, dtype=float)
    if final_t.ndim != 3 or min(final_t.shape) < 3:
        raise ValueError("Field temperatur harus berupa array 3D minimal 3×3×3.")
    if min(conductivity, density, specific_heat, dx, dy, dz) <= 0:
        raise ValueError("Properti material dan spacing harus positif.")
    volume_weights = (
        _node_weights(final_t.shape[0])[:, None, None]
        * _node_weights(final_t.shape[1])[None, :, None]
        * _node_weights(final_t.shape[2])[None, None, :]
    )
    cell_volume = dx * dy * dz
    volume = (final_t.shape[2] - 1) * dx * (final_t.shape[1] - 1) * dy * (final_t.shape[0] - 1) * dz
    initial_t = _initial_field(final_t.shape, initial_temperature, boundary)
    delta_u = float(np.sum(density * specific_heat * (final_t - initial_t) * volume_weights) * cell_volume)
    source_power = float(heat_generation * volume)
    if snapshots and snapshot_times and len(snapshots) >= 2 and len(snapshots) == len(snapshot_times):
        powers = [_outward_power(frame, conductivity, dx, dy, dz)[0] for frame in snapshots]
        times = np.asarray(snapshot_times, dtype=float)
        outward_energy = float(np.sum(0.5 * (np.asarray(powers[:-1]) + np.asarray(powers[1:])) * np.diff(times)))
        final_power, face_power = _outward_power(final_t, conductivity, dx, dy, dz)
        generated_energy = source_power * float(times[-1] - times[0])
        residual = delta_u - (generated_energy - outward_energy)
        scale = max(abs(delta_u), abs(generated_energy), abs(outward_energy), 1e-15)
        return {
            "mode": "Transient", "volume_m3": float(volume),
            "delta_internal_energy_J": delta_u, "source_power_W": source_power,
            "generated_energy_J": generated_energy, "outward_energy_J": outward_energy,
            "final_outward_power_W": final_power, "face_power_W": face_power,
            "balance_residual_J": float(residual), "relative_balance_error_pct": float(abs(residual) / scale * 100),
        }
    outward_power, face_power = _outward_power(final_t, conductivity, dx, dy, dz)
    residual = source_power - outward_power
    scale = max(abs(source_power), abs(outward_power), 1e-15)
    return {
        "mode": "Steady-state", "volume_m3": float(volume),
        "source_power_W": source_power, "outward_power_W": outward_power,
        "face_power_W": face_power, "balance_residual_W": float(residual),
        "relative_balance_error_pct": float(abs(residual) / scale * 100),
    }
