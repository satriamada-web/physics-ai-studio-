"""Cartesian room-air domain helpers for voxelized solid obstacles.

The obstacle mask must represent solid material, not the interior of a hollow
room shell. This utility pads the obstacle grid with an air-filled room and
creates inlet/outlet selections on opposite room faces.
"""
import numpy as np


def create_enclosing_air_domain(obstacle_mask_zyx, padding_cells=4,
                                flow_axis="x", flow_sign=1):
    """Create a padded box of air around solid voxels and select flow openings.

    Args:
        obstacle_mask_zyx: 3D boolean mask where True denotes solid obstacle.
        padding_cells: Number of air cells added on every side (1..40).
        flow_axis: Main flow direction, one of x, y, z.
        flow_sign: +1 enters from the low-index face; -1 from high-index face.

    Returns a room mask, obstacle mask, air mask, inlet/outlet masks and metadata.
    This is a rectangular computational room, not automatic hollow-shell detection.
    """
    obstacle = np.asarray(obstacle_mask_zyx, dtype=bool)
    if obstacle.ndim != 3 or min(obstacle.shape) < 2 or not obstacle.any():
        raise ValueError("Mask obstacle harus berupa volume 3D non-kosong.")
    if isinstance(padding_cells, bool) or int(padding_cells) < 1 or int(padding_cells) > 40:
        raise ValueError("Padding domain harus antara 1 dan 40 sel.")
    padding_cells = int(padding_cells)
    axis_map = {"x": 2, "y": 1, "z": 0}
    axis = str(flow_axis).lower()
    if axis not in axis_map:
        raise ValueError("Arah aliran harus x, y, atau z.")
    if flow_sign not in (-1, 1):
        raise ValueError("flow_sign harus +1 atau -1.")

    pad = ((padding_cells, padding_cells),) * 3
    obstacle_room = np.pad(obstacle, pad, mode="constant", constant_values=False)
    room = np.ones(obstacle_room.shape, dtype=bool)
    air = room & ~obstacle_room

    inlet = np.zeros_like(air)
    outlet = np.zeros_like(air)
    inlet_face = [slice(None)] * 3
    outlet_face = [slice(None)] * 3
    inlet_face[axis_map[axis]] = 0 if flow_sign > 0 else -1
    outlet_face[axis_map[axis]] = -1 if flow_sign > 0 else 0
    inlet[tuple(inlet_face)] = air[tuple(inlet_face)]
    outlet[tuple(outlet_face)] = air[tuple(outlet_face)]

    if not inlet.any() or not outlet.any():
        raise ValueError("Tidak ditemukan bukaan inlet/outlet pada batas domain.")
    return {
        "room_mask_zyx": room,
        "obstacle_mask_zyx": obstacle_room,
        "air_mask_zyx": air,
        "inlet_mask_zyx": inlet,
        "outlet_mask_zyx": outlet,
        "shape_zyx": tuple(int(v) for v in air.shape),
        "padding_cells": padding_cells,
        "flow_axis": axis,
        "flow_sign": int(flow_sign),
        "domain_note": "Domain udara kotak dengan obstacle voxel; geometri shell berongga belum dideteksi otomatis.",
    }
