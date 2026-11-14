"""JSON project storage for Physics AI Studio.

Projects are stored on the Streamlit host in data/projects. Deployments must mount
persistent storage at this path to retain projects across server restarts/redeploys.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT / "data" / "projects"
SAMPLE_DIR = Path(__file__).resolve().parent / "sample_projects"

# Only simulation inputs are persisted; solver results, jobs, and UI internals are excluded.
KEYS = {
    "mode", "material_name", "nx", "ny", "solver_tolerance", "solver_max_iterations",
    "lx", "ly", "k", "rho", "cp", "t_left", "t_right", "t_top", "t_bottom",
    "t_initial", "q_vol", "total_time", "mesh_density_2d", "probe_x_2d", "probe_y_2d",
    "custom_E", "custom_mu", "custom_nu",
    "geometry_3d_shape", "geometry_cube_side", "geometry_block_x", "geometry_block_y",
    "geometry_block_z", "geometry_cylinder_radius", "geometry_cylinder_height",
    "geometry_3d_resolution", "mesh_density_3d", "mesh3d_nx", "mesh3d_ny",
    "mesh3d_nz", "mesh3d_lx", "mesh3d_ly", "mesh3d_lz",
    "heat3d_mode", "heat3d_material", "heat3d_k", "heat3d_rho", "heat3d_cp",
    "heat3d_q", "heat3d_bxmin", "heat3d_bxmax", "heat3d_bymin", "heat3d_bymax",
    "heat3d_bzmin", "heat3d_bzmax", "heat3d_initial", "heat3d_tolerance",
    "heat3d_iterations", "heat3d_total_time", "heat3d_max_dt",
    "heat2d_colormap", "heat3d_colormap", "heat3d_slice_axis", "heat3d_slice_x",\n    "heat3d_slice_y", "heat3d_slice_z",
}

def _safe_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9 _.-]", "", str(name)).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        raise ValueError("Nama proyek tidak boleh kosong.")
    return name[:80]

def _path(project_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", str(project_id)):
        raise ValueError("ID proyek tidak valid.")
    return PROJECT_DIR / (project_id + ".json")

def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()
                if isinstance(v, (str, int, float, bool, list, tuple, dict)) or v is None}
    raise TypeError("Nilai konfigurasi tidak dapat diserialisasi.")

def collect_settings(session_state) -> dict:
    return {key: _json_value(session_state[key]) for key in KEYS if key in session_state}

def save_project(name: str, settings: dict, project_id: str | None = None) -> dict:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    clean_name = _safe_name(name)
    pid = project_id or uuid.uuid4().hex
    path = _path(pid)
    now = datetime.now(timezone.utc).isoformat()
    created = now
    if path.exists():
        try:
            created = json.loads(path.read_text(encoding="utf-8")).get("created_at", now)
        except (OSError, ValueError):
            pass
    payload = {
        "schema_version": 1, "id": pid, "name": clean_name,
        "created_at": created, "updated_at": now,
        "settings": {k: _json_value(v) for k, v in settings.items() if k in KEYS},
    }
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return payload

def list_projects() -> list[dict]:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in PROJECT_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") == 1 and data.get("id") == path.stem:
                projects.append({k: data.get(k) for k in ("id", "name", "created_at", "updated_at")})
        except (OSError, ValueError, TypeError):
            continue
    return sorted(projects, key=lambda p: p.get("updated_at") or "", reverse=True)

def load_project(project_id: str) -> dict:
    data = json.loads(_path(project_id).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("settings"), dict):
        raise ValueError("Format proyek tidak didukung atau rusak.")
    return data

def rename_project(project_id: str, name: str) -> dict:
    data = load_project(project_id)
    data["name"] = _safe_name(name)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _path(project_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def duplicate_project(project_id: str) -> dict:
    source = load_project(project_id)
    return save_project(source["name"] + " Copy", source["settings"])

def delete_project(project_id: str) -> None:
    _path(project_id).unlink(missing_ok=True)

def list_samples() -> list[dict]:
    samples = []
    for path in sorted(SAMPLE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") == 1 and isinstance(data.get("settings"), dict):
                samples.append(data)
        except (OSError, ValueError, TypeError):
            continue
    return samples

def load_sample(sample_id: str) -> dict:
    for sample in list_samples():
        if sample.get("id") == sample_id:
            return sample
    raise ValueError("Template tidak ditemukan.")
