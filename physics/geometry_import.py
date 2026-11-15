"""Import and validate triangulated 3D surface geometry (OBJ and STL).

Imported coordinates are converted to metres using the supplied scale factor.
This module deliberately creates a surface mesh only; it does not claim to
produce a tetrahedral/hexahedral volume mesh.
"""
import math
import struct
import numpy as np


MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FACES = 250_000


def _deduplicate_triangles(raw_vertices, scale):
    vertices = np.asarray(raw_vertices, dtype=float) * float(scale)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 3:
        raise ValueError("File tidak berisi koordinat vertex 3D yang cukup.")
    if not np.isfinite(vertices).all():
        raise ValueError("Geometri mengandung koordinat NaN atau infinity.")
    # Quantization removes duplicated STL vertices while retaining practical CAD precision.
    quantized = np.rint(vertices / 1e-9).astype(np.int64)
    lookup = {}
    unique = []
    faces = []
    for start in range(0, len(quantized), 3):
        tri = []
        for point in quantized[start:start + 3]:
            key = tuple(int(v) for v in point)
            if key not in lookup:
                lookup[key] = len(unique)
                unique.append(vertices[start + len(tri)])
            tri.append(lookup[key])
        if len(tri) == 3 and len(set(tri)) == 3:
            faces.append(tri)
    if not faces:
        raise ValueError("Tidak ditemukan segitiga permukaan yang valid.")
    return np.asarray(unique, dtype=float), np.asarray(faces, dtype=np.int64)


def _parse_obj(data, scale):
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("File OBJ harus berupa teks UTF-8.") from exc
    vertices = []
    faces = []
    for line_number, line in enumerate(source.splitlines(), 1):
        fields = line.strip().split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v":
            if len(fields) < 4:
                raise ValueError(f"Baris vertex OBJ {line_number} tidak lengkap.")
            vertices.append([float(fields[1]), float(fields[2]), float(fields[3])])
        elif fields[0] == "f":
            if len(fields) < 4:
                continue
            polygon = []
            for token in fields[1:]:
                raw_index = int(token.split("/")[0])
                index = raw_index - 1 if raw_index > 0 else len(vertices) + raw_index
                if index < 0 or index >= len(vertices):
                    raise ValueError(f"Indeks face OBJ tidak valid pada baris {line_number}.")
                polygon.append(index)
            for i in range(1, len(polygon) - 1):
                faces.append([polygon[0], polygon[i], polygon[i + 1]])
                if len(faces) > MAX_FACES:
                    raise ValueError("Jumlah face melebihi batas 250.000.")
    if not vertices or not faces:
        raise ValueError("OBJ harus memiliki data vertex (v) dan face (f).")
    points = np.asarray(vertices, dtype=float) * scale
    if not np.isfinite(points).all():
        raise ValueError("OBJ mengandung koordinat tidak finite.")
    return points, np.asarray(faces, dtype=np.int64)


def _parse_stl(data, scale):
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if count > 0 and 84 + count * 50 == len(data):
            if count > MAX_FACES:
                raise ValueError("Jumlah face STL melebihi batas 250.000.")
            raw = np.empty((count * 3, 3), dtype=float)
            offset = 84
            for i in range(count):
                values = struct.unpack_from("<12fH", data, offset)
                raw[i * 3:(i + 1) * 3] = np.asarray(values[3:12], dtype=float).reshape(3, 3)
                offset += 50
            return _deduplicate_triangles(raw, scale)
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Format STL tidak dikenali sebagai binary atau ASCII.") from exc
    raw = []
    for line in source.splitlines():
        fields = line.strip().split()
        if fields and fields[0].lower() == "vertex":
            if len(fields) != 4:
                raise ValueError("Baris vertex STL tidak valid.")
            raw.append([float(fields[1]), float(fields[2]), float(fields[3])])
            if len(raw) // 3 > MAX_FACES:
                raise ValueError("Jumlah face STL melebihi batas 250.000.")
    if len(raw) < 3 or len(raw) % 3:
        raise ValueError("STL ASCII harus memiliki tiga vertex untuk setiap facet.")
    return _deduplicate_triangles(raw, scale)


def inspect_surface(vertices, faces):
    """Return bounds and edge-incidence diagnostics for a triangle surface."""
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("Bentuk array geometri tidak valid.")
    if len(faces) == 0 or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Indeks segitiga berada di luar daftar vertex.")
    if not np.isfinite(vertices).all():
        raise ValueError("Vertex mengandung koordinat tidak finite.")

    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=0)
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    boundary_edges = int(np.count_nonzero(counts == 1))
    nonmanifold_edges = int(np.count_nonzero(counts > 2))
    watertight = boundary_edges == 0 and nonmanifold_edges == 0

    tri = vertices[faces]
    signed_volume = float(np.einsum(
        "ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])
    ).sum() / 6.0)
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    dimensions = maximum - minimum
    if np.any(dimensions <= 0):
        raise ValueError("Geometri memiliki dimensi nol; periksa file sumber.")
    return {
        "dimensions_m": {"x": float(dimensions[0]), "y": float(dimensions[1]), "z": float(dimensions[2])},
        "bounds_m": {"min": minimum.tolist(), "max": maximum.tolist()},
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": nonmanifold_edges,
        "is_watertight": bool(watertight),
        "surface_volume_m3": abs(signed_volume) if watertight else None,
    }


def import_surface_mesh(filename, file_bytes, scale_to_m=1.0, progress_callback=None, cancel_event=None):
    """Import OBJ/STL bytes and return the common geometry preview data structure.

    scale_to_m is the number of metres represented by one source coordinate unit.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Import geometri dibatalkan.")
    if progress_callback:
        progress_callback(0, 3, None)
    if not isinstance(file_bytes, (bytes, bytearray)):
        raise ValueError("Konten file harus berupa bytes.")
    data = bytes(file_bytes)
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Ukuran file harus lebih dari 0 dan maksimum 15 MB.")
    try:
        scale = float(scale_to_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("Skala harus berupa angka positif.") from exc
    if not math.isfinite(scale) or scale <= 0 or scale > 1000:
        raise ValueError("Skala harus berada di antara 0 dan 1000 meter per unit.")
    extension = str(filename).lower().rsplit(".", 1)[-1] if "." in str(filename) else ""
    if extension == "obj":
        vertices, faces = _parse_obj(data, scale)
    elif extension == "stl":
        vertices, faces = _parse_stl(data, scale)
    else:
        raise ValueError("Format belum didukung. Unggah file .OBJ atau .STL.")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Import geometri dibatalkan.")
    if progress_callback:
        progress_callback(2, 3, None)
    if len(faces) > MAX_FACES:
        raise ValueError("Jumlah face melebihi batas 250.000.")
    diagnostics = inspect_surface(vertices, faces)
    if progress_callback:
        progress_callback(3, 3, None)
    return {
        "shape": "Imported: " + str(filename),
        "source_filename": str(filename),
        "source_format": extension.upper(),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        **diagnostics,
    }
