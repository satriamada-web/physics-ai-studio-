import io
import json
import re
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from ui.theme import apply_theme
from physics.heat_transfer import solve_steady_state, solve_transient, stable_time_step, calculate_heat_flux, calculate_steady_residual
from physics.transient_diagnostics import calculate_transient_diagnostics
from physics.reporting import build_heat_transfer_pdf
from physics.materials import MATERIALS
from physics.verification import run_verification_suite
from physics.worker import submit_job, get_job, cancel_job


st.set_page_config(page_title="Physics AI Studio", page_icon="🌡️", layout="wide")

@st.fragment(run_every="500ms")
def render_job_monitor(job_key, result_key, title):
    job_id = st.session_state.get(job_key)
    if not job_id:
        return
    job = get_job(job_id)
    if job is None:
        st.error("Status pekerjaan tidak ditemukan. Silakan jalankan ulang simulasi.")
        return
    st.markdown("**" + title + "**")
    st.progress(job["progress"], text=job["message"])
    if job["metric"] is not None:
        st.caption(f"Iterasi/langkah {job['current']:,}/{job['total']:,} · metrik perubahan {job['metric']:.3e}")
    elif job["total"]:
        st.caption(f"Progres: {job['current']:,}/{job['total']:,}")
    if job["status"] in ("queued", "running"):
        if st.button("■ Cancel Solver", key=f"cancel_{job_id}", type="secondary"):
            cancel_job(job_id)
            st.warning("Permintaan pembatalan dikirim. Solver berhenti pada checkpoint berikutnya.")
    elif job["status"] == "completed":
        st.session_state[result_key] = job["result"]
        st.session_state.pop(job_key, None)
        st.success("Pekerjaan selesai. Hasil siap ditampilkan.")
        st.rerun()
    elif job["status"] == "cancelled":
        st.session_state.pop(job_key, None)
        st.warning(job["message"] or "Simulasi dibatalkan.")
    elif job["status"] == "failed":
        st.session_state.pop(job_key, None)
        st.error(job["error"] or "Simulasi gagal.")


def _run_2d_job(mode, nx, ny, lx, ly, k, rho, cp, q_vol, boundary,
                initial, total_time, tolerance, max_iterations, probe_x, probe_y, material_name,
                progress_callback=None, cancel_event=None):
    if mode == "Steady-state":
        result = solve_steady_state(
            nx, ny, lx, ly, k, q_vol, boundary, initial,
            tolerance=tolerance, max_iterations=max_iterations,
            progress_callback=progress_callback, cancel_event=cancel_event,
        )
        residual = calculate_steady_residual(result["temperature"], k, lx, ly, q_vol)
        return {"result": result, "residual": residual, "transient_diagnostics": None, "params": {"mode": mode, "nx": nx, "ny": ny, "lx": lx, "ly": ly, "k": k, "rho": rho, "cp": cp, "q": q_vol, "boundary": dict(boundary), "initial": initial, "total_time": total_time, "material_name": material_name, "solver_tolerance": tolerance, "solver_max_iterations": max_iterations}}
    dt_limit = 0.9 * stable_time_step(k, rho, cp, lx/(nx-1), ly/(ny-1))
    result = solve_transient(
        nx, ny, lx, ly, k, rho, cp, q_vol, boundary, initial,
        total_time, dt_limit, probe_x=probe_x, probe_y=probe_y,
        progress_callback=progress_callback, cancel_event=cancel_event,
    )
    diagnostics = calculate_transient_diagnostics(k, rho, cp, lx, ly, nx, ny, result["dt"])
    return {"result": result, "residual": None, "transient_diagnostics": diagnostics, "params": {"mode": mode, "nx": nx, "ny": ny, "lx": lx, "ly": ly, "k": k, "rho": rho, "cp": cp, "q": q_vol, "boundary": dict(boundary), "initial": initial, "total_time": total_time, "material_name": material_name, "solver_tolerance": tolerance, "solver_max_iterations": max_iterations}}


def _run_3d_job(solver_function, solver_args, solver_kwargs, mode,
                mesh_info, material_info, progress_callback=None, cancel_event=None):
    result = solver_function(
        *solver_args, progress_callback=progress_callback,
        cancel_event=cancel_event, **solver_kwargs
    )
    result["mode"] = mode
    return {"result": result, "mesh": mesh_info, "material": material_info}


def number_input_with_unit(label, *args, **kwargs):
    """Render a numeric input with a compact unit badge on its right."""
    match = re.search(r"\(([^()]*)\)\s*$", str(label))
    unit = match.group(1) if match else ("iterasi" if "iterasi" in str(label).lower() else "node" if "node" in str(label).lower() else "—")
    clean_label = str(label)[:match.start()].rstrip() if match else str(label)
    input_col, unit_col = st.columns([5.8, 1.05], vertical_alignment="bottom")
    with input_col:
        value = st.number_input(clean_label, *args, **kwargs)
    with unit_col:
        st.markdown(f'<div class="pas-unit-badge">{unit}</div>', unsafe_allow_html=True)
    return value


def _bump_slider_value(key, delta, step, minimum, maximum, callback=None):
    current = st.session_state.get(key, minimum)
    st.session_state[key] = max(minimum, min(maximum, current + delta * step))
    if callback:
        callback()


def slider_with_stepper(label, minimum, maximum, step=1, key=None, value=None, on_change=None, help=None):
    """Slider plus compact +/- controls sharing one session-state value."""
    if key not in st.session_state:
        st.session_state[key] = minimum if value is None else value
    slider_col, minus_col, plus_col = st.columns([7, 0.7, 0.7], vertical_alignment="bottom")
    with slider_col:
        value = st.slider(label, min_value=minimum, max_value=maximum,
                          step=step, key=key, on_change=on_change, help=help)
    with minus_col:
        st.button("−", key=f"{key}_step_down", disabled=value <= minimum,
                  on_click=_bump_slider_value,
                  args=(key, -1, step, minimum, maximum, on_change), use_container_width=True)
    with plus_col:
        st.button("+", key=f"{key}_step_up", disabled=value >= maximum,
                  on_click=_bump_slider_value,
                  args=(key, 1, step, minimum, maximum, on_change), use_container_width=True)
    return value


apply_theme()

def _set_playing(key, value):
    st.session_state[key] = value


def _reset_timeline(index_key, playing_key, slider_key):
    st.session_state[index_key] = 0
    st.session_state[slider_key] = 0
    st.session_state[playing_key] = False


@st.fragment(run_every="500ms")
def render_transient_pill(snapshot_count, times, prefix):
    """Floating transient timeline with fragment-driven playback."""
    index_key = f"{prefix}_frame"
    playing_key = f"{prefix}_playing"
    slider_key = f"{prefix}_timeline"
    if index_key not in st.session_state:
        st.session_state[index_key] = 0
    if playing_key not in st.session_state:
        st.session_state[playing_key] = False
    if st.session_state[playing_key]:
        next_index = st.session_state[index_key] + 1
        if next_index >= snapshot_count:
            st.session_state[index_key] = snapshot_count - 1
            st.session_state[playing_key] = False
        else:
            st.session_state[index_key] = next_index
        st.session_state[slider_key] = st.session_state[index_key]
    with st.container(key=f"transient_pill_{prefix}"):
        st.markdown('<div class="timeline-pill-label">TRANSIENT PLAYBACK</div>', unsafe_allow_html=True)
        play_col, pause_col, reset_col, timeline_col = st.columns([0.8, 0.8, 0.8, 5.4], vertical_alignment="center")
        with play_col:
            st.button("▶", key=f"{prefix}_play", help="Play", disabled=st.session_state[playing_key] or st.session_state[index_key] >= snapshot_count - 1,
                      on_click=_set_playing, args=(playing_key, True), use_container_width=True)
        with pause_col:
            st.button("Ⅱ", key=f"{prefix}_pause", help="Pause", disabled=not st.session_state[playing_key],
                      on_click=_set_playing, args=(playing_key, False), use_container_width=True)
        with reset_col:
            st.button("↺", key=f"{prefix}_reset", help="Reset ke awal", on_click=_reset_timeline,
                      args=(index_key, playing_key, slider_key), use_container_width=True)
        with timeline_col:
            current = st.slider("Timeline simulasi", 0, max(0, snapshot_count - 1),
                                key=slider_key, label_visibility="collapsed")
            st.session_state[index_key] = current
            st.caption(f"t = {times[current]:.5g} s / {times[-1]:.5g} s · frame {current + 1}/{snapshot_count}")
    return int(st.session_state[index_key])



st.markdown("""
<style>
.pas-unit-badge {
  min-height:38px; display:flex; align-items:center; justify-content:center;
  margin:0 0 2px; padding:0 7px; border:1px solid rgba(130,160,190,.24);
  border-radius:9px; background:rgba(56,200,242,.10); color:#8EDFF5;
  font-size:.72rem; font-weight:750; white-space:nowrap; overflow:hidden;
}
div[data-testid="stTabs"] { margin-top:.35rem; }
div[data-testid="stTabs"] button { font-size:.78rem !important; font-weight:650 !important; }
div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:5px; flex-wrap:wrap; }
div[data-testid="stTabs"] button[role="tab"] { border-radius:9px 9px 0 0; padding:7px 11px; }
/* Viewport-first workstation layout */
[data-testid="stSidebar"] { display:none !important; }
[data-testid="stMainBlockContainer"] { max-width: 100% !important; padding-left: 1.2rem !important; padding-right: 1.2rem !important; padding-bottom: 20vh !important; }
div[class*="st-key-floating_run_button"] {
  position:fixed !important; top:86px !important; right:24px !important;
  z-index:998 !important; width:112px !important;
}
div[class*="st-key-floating_run_button"] button {
  width:100% !important; min-height:40px !important;
  border-radius:13px !important; background:#38C8F2 !important;
  color:#10212B !important; font-weight:800 !important;
  box-shadow:0 8px 24px rgba(0,0,0,.28) !important;
}
.floating-tools {
  display:flex; align-items:center; gap:8px; flex-wrap:wrap;
  width:fit-content; max-width:100%; margin: 4px 0 14px auto;
  padding:8px 10px; border:1px solid rgba(130,160,190,.25);
  border-radius:16px; background:rgba(37,51,66,.76);
  backdrop-filter: blur(16px); -webkit-backdrop-filter:blur(16px);
  box-shadow:0 8px 28px rgba(0,0,0,.22);
}
.tool-brand { color:#E7EDF5; font-size:.72rem; font-weight:800; letter-spacing:.12em; padding:0 8px; }
.tool-brand span { color:#91A4B8; font-weight:500; letter-spacing:.04em; }
.tool-chip { color:#CBD7E4; background:rgba(255,255,255,.045); border:1px solid rgba(150,175,200,.13); border-radius:10px; padding:7px 10px; font-size:.73rem; white-space:nowrap; }
.tool-run { color:#10212B; background:#38C8F2; border-color:#38C8F2; font-weight:750; }
.workspace-note { color:#91A4B8; font-size:.72rem; margin:0 0 8px 2px; letter-spacing:.025em; }
div[class*="st-key-bottom_sheet"] {
  position:fixed !important; z-index:1000 !important;
  left:50% !important; transform:translateX(-50%) !important;
  bottom:10px !important; width:min(1480px, calc(100vw - 20px)) !important;
  max-height:25vh !important; overflow-y:auto !important; resize:vertical !important;
  padding:7px 12px 10px !important;
  border:1px solid rgba(125,170,195,.35) !important;
  border-radius:18px !important;
  background:rgba(31,44,58,.91) !important;
  backdrop-filter:blur(18px) saturate(130%) !important;
  -webkit-backdrop-filter:blur(18px) saturate(130%) !important;
  box-shadow:0 12px 42px rgba(0,0,0,.38) !important;
}
.sheet-grip { width:38px; height:4px; border-radius:8px; background:#8295A8; opacity:.8; margin:1px auto 7px; }
.sheet-heading { color:#E7EDF5; font-size:.68rem; font-weight:800; letter-spacing:.12em; padding:0 3px 5px; }
.sheet-heading span { color:#8FA2B6; font-weight:500; letter-spacing:.04em; margin-left:6px; }
div[class*="st-key-bottom_sheet"] [data-testid="stExpander"] {
  background:rgba(42,57,73,.72) !important; border-color:rgba(125,170,195,.22) !important;
}
div[class*="st-key-bottom_sheet"] [data-testid="stExpander"] details[open] {
  max-height:calc(25vh - 62px); overflow-y:auto;
}
div[class*="st-key-bottom_sheet"] [data-testid="stExpander"] summary { padding-top:5px; padding-bottom:5px; }
div[class*="st-key-bottom_sheet"] h1,
div[class*="st-key-bottom_sheet"] h2,
div[class*="st-key-bottom_sheet"] h3 { margin-top:.35rem !important; margin-bottom:.35rem !important; }

div[data-testid="stProgress"] {
  padding:5px 8px; border:1px solid rgba(125,190,215,.18);
  border-radius:12px; background:rgba(20,32,45,.42);
}
div[data-testid="stProgress"] > div > div {
  height:9px !important; border-radius:99px !important;
  background:rgba(145,165,185,.16) !important;
}
div[data-testid="stProgress"] > div > div > div {
  border-radius:99px !important;
  background:linear-gradient(90deg,#2CA9D4,#55D8E8,#62D5A3) !important;
  box-shadow:0 0 12px rgba(56,200,242,.24);
}
div[class*="st-key-transient_pill"] {
  position:fixed !important; z-index:1200 !important; left:50% !important;
  transform:translateX(-50%) !important; bottom:22px !important;
  width:min(760px,calc(100vw - 24px)) !important; padding:9px 13px 7px !important;
  border:1px solid rgba(125,190,215,.30) !important; border-radius:22px !important;
  background:rgba(24,37,51,.88) !important; backdrop-filter:blur(20px) saturate(140%) !important;
  -webkit-backdrop-filter:blur(20px) saturate(140%) !important;
  box-shadow:0 12px 40px rgba(0,0,0,.38) !important;
}
.timeline-pill-label {font-size:.60rem; letter-spacing:.14em; color:#8DA4B9; font-weight:800; margin:0 0 3px 5px;}
div[class*="st-key-transient_pill_heat3d_playback"] { bottom:96px !important; }
@media(max-width:600px) {
 div[class*="st-key-transient_pill_heat3d_playback"] { bottom:88px !important; }
}
div[class*="st-key-transient_pill"] button {min-height:35px !important; border-radius:12px !important;}
div[class*="st-key-transient_pill"] [data-testid="stSlider"] {padding-top:0 !important;}
div[class*="st-key-transient_pill"] [data-testid="stSlider"] label {display:none !important;}
div[class*="st-key-transient_pill"] [data-testid="stCaptionContainer"] {text-align:right; font-size:.66rem;}
@media(max-width:600px) {
 div[class*="st-key-transient_pill"] {bottom:8px !important; padding:7px 8px 5px !important;}
 div[class*="st-key-transient_pill"] [data-testid="stHorizontalBlock"] {gap:.25rem !important;}
}
\ndiv[data-testid="stPlotlyChart"] { width:100% !important; }
@media (max-width: 700px) {
  [data-testid="stMainBlockContainer"] { padding-left:.55rem !important; padding-right:.55rem !important; padding-bottom:28vh !important; }
  .floating-tools { width:100%; justify-content:space-between; gap:5px; padding:6px; margin-bottom:9px; }
  .tool-chip { padding:6px 7px; font-size:.65rem; }
  .tool-brand { font-size:.65rem; padding:0 4px; }
  div[class*="st-key-bottom_sheet"] { width:calc(100vw - 12px) !important; bottom:6px !important; max-height:25vh !important; padding:6px 8px 8px !important; }
}
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="app-topbar"><div><div class="app-name">PHYSICS AI STUDIO</div><div class="app-subtitle">Multiphysics Simulation Environment · MVP 1.9</div></div><div class="app-status">● READY</div></div><div class="app-ribbon">FILE　 MODEL　 GEOMETRY　 MATERIALS　 PHYSICS　 MESH　 STUDY　 RESULTS</div>""", unsafe_allow_html=True)
with st.container(key="floating_run_button"):
    toolbar_run = st.button("▶ RUN 2D", key="toolbar_run_2d", type="primary")
st.markdown("""
<div class="floating-tools">
  <div class="tool-brand">PAS <span>WORKSPACE</span></div>
  <div class="tool-chip">◈ Geometry</div><div class="tool-chip">▦ Materials</div>
  <div class="tool-chip">⌗ Boundary</div><div class="tool-chip">▤ Mesh</div>
  <div class="tool-chip tool-run">▶ Study</div>
</div>
<div class="workspace-note">3D Heat Transfer · 2D Heat Transfer · Scientific Computing</div>
""", unsafe_allow_html=True)

st.divider()
st.header("Geometry Builder 3D · MVP 1.4")
st.caption("Buat dan putar geometri primitif 3D. Preview ini adalah surface mesh untuk visualisasi, belum merupakan mesh volume untuk solver FEM.")
with st.expander("Geometry Builder 3D", expanded=False):
    from physics.geometry_3d import create_geometry

    shape_col, size_col, resolution_col = st.columns([1, 1.4, 1])
    with shape_col:
        geometry_shape = st.selectbox(
            "Bentuk objek", ["Kubus", "Balok", "Silinder"], key="geometry_3d_shape"
        )
    dimensions = {}
    with size_col:
        if geometry_shape == "Kubus":
            dimensions["sisi"] = number_input_with_unit(
                "Panjang sisi (m)", min_value=0.001, max_value=10.0,
                value=0.10, step=0.01, format="%.3f", key="geometry_cube_side"
            )
        elif geometry_shape == "Balok":
            dimensions["panjang"] = number_input_with_unit(
                "Panjang X (m)", min_value=0.001, max_value=10.0,
                value=0.20, step=0.01, format="%.3f", key="geometry_block_x"
            )
            dimensions["lebar"] = number_input_with_unit(
                "Lebar Y (m)", min_value=0.001, max_value=10.0,
                value=0.12, step=0.01, format="%.3f", key="geometry_block_y"
            )
            dimensions["tinggi"] = number_input_with_unit(
                "Tinggi Z (m)", min_value=0.001, max_value=10.0,
                value=0.08, step=0.01, format="%.3f", key="geometry_block_z"
            )
        else:
            dimensions["radius"] = number_input_with_unit(
                "Radius (m)", min_value=0.001, max_value=5.0,
                value=0.05, step=0.005, format="%.3f", key="geometry_cylinder_radius"
            )
            dimensions["tinggi"] = number_input_with_unit(
                "Tinggi (m)", min_value=0.001, max_value=10.0,
                value=0.15, step=0.01, format="%.3f", key="geometry_cylinder_height"
            )
    with resolution_col:
        geometry_resolution = st.slider(
            "Resolusi silinder", min_value=8, max_value=64,
            value=24, step=4, key="geometry_3d_resolution"
        )
        st.caption("Makin tinggi resolusi, makin halus permukaan silinder.")
    if st.button("Buat / perbarui geometri 3D", key="build_geometry_3d", type="primary"):
        st.session_state["geometry3d_job_id"] = submit_job(
            "geometry-surface-mesh", create_geometry,
            geometry_shape, dimensions, geometry_resolution,
        )
        st.session_state.pop("geometry_3d_error", None)
    render_job_monitor("geometry3d_job_id", "geometry_3d_result", "Pembuatan geometri 3D")
    if st.session_state.get("geometry_3d_error"):
        st.error(st.session_state["geometry_3d_error"])
    geometry_result = st.session_state.get("geometry_3d_result")
    if geometry_result:
        vertices = geometry_result["vertices"]
        faces = geometry_result["faces"]
        mesh_fig = go.Figure(data=[go.Mesh3d(
            x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            color="#4C9BE8", opacity=0.88, flatshading=True,
            hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>z=%{z:.4f} m<extra></extra>",
        )])
        mesh_fig.update_layout(
            title=f"Preview geometri: {geometry_result['shape']}",
            scene={
                "xaxis_title": "X (m)", "yaxis_title": "Y (m)", "zaxis_title": "Z (m)",
                "aspectmode": "data",
                "camera": {"eye": {"x": 1.6, "y": 1.6, "z": 1.3}},
            },
            height=620, margin={"l": 0, "r": 0, "t": 35, "b": 0},
        )
        st.plotly_chart(mesh_fig, use_container_width=True, key="geometry_3d_preview")
        m1, m2, m3 = st.columns(3)
        m1.metric("Titik vertex", geometry_result["vertex_count"])
        m2.metric("Segitiga permukaan", geometry_result["face_count"])
        m3.metric("Dimensi X × Y × Z", " × ".join(f"{v:.3g}" for v in geometry_result["dimensions_m"].values()) + " m")
        st.download_button(
            "⬇ Unduh geometri (OBJ)",
            "\n".join(
                [*(f"v {v[0]:.10g} {v[1]:.10g} {v[2]:.10g}" for v in vertices),
                 *(f"f {f[0]+1} {f[1]+1} {f[2]+1}" for f in faces)]
            ).encode("utf-8"),
            file_name="physics_ai_studio_geometry.obj",
            mime="text/plain",
        )
        st.info("Geometri ini masih berupa permukaan segitiga (surface mesh). Solver 3D saat ini memakai grid Cartesian terstruktur dan belum menerima geometri arbitrer ini secara langsung.")

st.divider()
st.header("Structured 3D Mesh Engine · MVP 1.5")
st.caption("Bangun grid Cartesian node-centred untuk domain balok. Grid ini memakai konvensi array (z, y, x) yang kompatibel dengan fondasi solver panas 3D.")
with st.expander("Buka 3D Mesh Engine", expanded=False):
    from physics.mesh_3d import create_structured_mesh

    mesh_density_3d = st.selectbox("Kepadatan mesh 3D", ["Coarse / Kasar", "Normal", "Fine / Halus"], index=1, key="mesh_density_3d")
    mesh3d_defaults = {"Coarse / Kasar": 7, "Normal": 11, "Fine / Halus": 17}
    if st.session_state.get("_mesh_density_3d_applied") != mesh_density_3d:
        st.session_state["mesh3d_nx"] = mesh3d_defaults[mesh_density_3d]
        st.session_state["mesh3d_ny"] = mesh3d_defaults[mesh_density_3d]
        st.session_state["mesh3d_nz"] = mesh3d_defaults[mesh_density_3d]
        st.session_state["_mesh_density_3d_applied"] = mesh_density_3d
    mesh_cols = st.columns(3)
    with mesh_cols[0]:
        mesh_nx = slider_with_stepper("Node arah X", 2, 58, step=1, key="mesh3d_nx", value=11)
        mesh_lx = number_input_with_unit("Panjang domain X (m)", min_value=0.001, max_value=10.0, value=0.10, step=0.01, format="%.3f", key="mesh3d_lx")
    with mesh_cols[1]:
        mesh_ny = slider_with_stepper("Node arah Y", 2, 58, step=1, key="mesh3d_ny", value=11)
        mesh_ly = number_input_with_unit("Panjang domain Y (m)", min_value=0.001, max_value=10.0, value=0.10, step=0.01, format="%.3f", key="mesh3d_ly")
    with mesh_cols[2]:
        mesh_nz = slider_with_stepper("Node arah Z", 2, 58, step=1, key="mesh3d_nz", value=11)
        mesh_lz = number_input_with_unit("Panjang domain Z (m)", min_value=0.001, max_value=10.0, value=0.10, step=0.01, format="%.3f", key="mesh3d_lz")
    st.caption("Batas aman saat ini: maksimum 200.000 node per grid. Preview hanya menampilkan sampel node agar browser tetap ringan.")
    if st.button("Buat / perbarui structured mesh", key="build_structured_mesh_3d", type="primary"):
        if min(mesh_nx, mesh_ny, mesh_nz) < 3:
            st.error("Solver FDM 3D membutuhkan minimal 3 node pada setiap arah.")
        else:
            st.session_state["mesh3d_job_id"] = submit_job(
                "structured-mesh", create_structured_mesh,
                int(mesh_nx), int(mesh_ny), int(mesh_nz),
                float(mesh_lx), float(mesh_ly), float(mesh_lz),
            )
            st.session_state.pop("structured_mesh_3d_error", None)
    render_job_monitor("mesh3d_job_id", "structured_mesh_3d_result", "Pembuatan mesh 3D")
    if st.session_state.get("structured_mesh_3d_error"):
        st.error(st.session_state["structured_mesh_3d_error"])
    structured_mesh = st.session_state.get("structured_mesh_3d_result")
    if structured_mesh:
        sx = structured_mesh["x"][::max(1, int(np.ceil(structured_mesh["nx"] / 11)))]
        sy = structured_mesh["y"][::max(1, int(np.ceil(structured_mesh["ny"] / 11)))]
        sz = structured_mesh["z"][::max(1, int(np.ceil(structured_mesh["nz"] / 11)))]
        if sx[-1] != structured_mesh["x"][-1]:
            sx = np.append(sx, structured_mesh["x"][-1])
        if sy[-1] != structured_mesh["y"][-1]:
            sy = np.append(sy, structured_mesh["y"][-1])
        if sz[-1] != structured_mesh["z"][-1]:
            sz = np.append(sz, structured_mesh["z"][-1])
        zz, yy, xx = np.meshgrid(sz, sy, sx, indexing="ij")
        grid_fig = go.Figure(go.Scatter3d(
            x=xx.ravel(), y=yy.ravel(), z=zz.ravel(),
            mode="markers",
            marker={"size": 2.5, "opacity": 0.7},
            hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>z=%{z:.4f} m<extra>Node grid</extra>",
        ))
        grid_fig.update_layout(
            title="Preview node grid Cartesian 3D (sampel)",
            scene={"xaxis_title": "X (m)", "yaxis_title": "Y (m)", "zaxis_title": "Z (m)", "aspectmode": "data"},
            height=560, margin={"l": 0, "r": 0, "t": 35, "b": 0},
        )
        st.plotly_chart(grid_fig, use_container_width=True, key="structured_mesh_3d_preview")
        mm1, mm2, mm3, mm4 = st.columns(4)
        mm1.metric("Total node", f"{structured_mesh['node_count']:,}")
        mm2.metric("Cell heksahedral", f"{structured_mesh['cell_count']:,}")
        mm3.metric("Bentuk array (z,y,x)", str(structured_mesh["shape_zyx"]))
        mm4.metric("Ukuran langkah dx/dy/dz", f"{structured_mesh['dx']:.4g} / {structured_mesh['dy']:.4g} / {structured_mesh['dz']:.4g} m")
        st.info("Grid ini merupakan node-centred Cartesian structured grid untuk metode beda hingga. Cell count menunjukkan jumlah blok antar-node; belum ada konektivitas elemen FEM atau mesh tetrahedral. Integrasi langsung ke antarmuka solver 3D menjadi tahap berikutnya.")

st.divider()
st.header("3D Heat Transfer Solver · MVP 1.6")
st.caption("Jalankan solver konduksi panas 3D pada structured mesh yang dibuat di atas. Model memakai material homogen-isotropik, properti konstan, sumber panas seragam, dan temperatur tetap pada enam sisi.")
with st.expander("Buka solver Heat Transfer 3D", expanded=False):
    from physics.heat_transfer_3d import (
        solve_steady_state_3d, solve_transient_3d,
        calculate_heat_flux_3d, stable_time_step_3d,
    )

    from physics.verification_3d import run_3d_verification_suite
    from physics.energy_analysis_3d import analyze_energy_balance_3d

    with st.expander("Verifikasi numerik solver 3D", expanded=False):
        st.write("Uji kasus analitik dasar untuk steady-state seragam, transient seragam, dan Hukum Fourier pada medan temperatur linear.")
        if st.button("Jalankan uji verifikasi 3D", key="run_verification_3d"):
            try:
                st.session_state["verification_3d_results"] = run_3d_verification_suite()
                st.session_state.pop("verification_3d_error", None)
            except Exception as exc:
                st.session_state["verification_3d_error"] = str(exc)
        if st.session_state.get("verification_3d_error"):
            st.error(st.session_state["verification_3d_error"])
        verification3 = st.session_state.get("verification_3d_results", [])
        if verification3:
            passed3 = sum(row["Status"] == "LULUS" for row in verification3)
            st.metric("Uji 3D lulus", f"{passed3}/{len(verification3)}")
            st.dataframe(verification3, use_container_width=True, hide_index=True)
            st.caption("Lulus pada kasus analitik dasar bukan validasi eksperimen dan tidak membuktikan akurasi untuk semua kondisi.")

    active_mesh = st.session_state.get("structured_mesh_3d_result")
    if not active_mesh:
        st.warning("Buat structured mesh terlebih dahulu pada bagian 3D Mesh Engine.")
    else:
        st.write(
            f"Mesh aktif: **{active_mesh['nx']} × {active_mesh['ny']} × {active_mesh['nz']}** "
            f"node · total **{active_mesh['node_count']:,}** node · "
            f"domain {active_mesh['lx']:.4g} × {active_mesh['ly']:.4g} × {active_mesh['lz']:.4g} m."
        )
        if active_mesh["node_count"] > 30000:
            st.warning("Untuk menjaga server cloud tetap responsif, solver MVP 1.6 dibatasi hingga 30.000 node. Kurangi resolusi mesh sebelum menjalankan simulasi.")
            solver_allowed = False
        else:
            solver_allowed = True

        solver_mode_3d = st.radio(
            "Mode simulasi 3D", ["Steady-state", "Transient"],
            horizontal=True, key="heat3d_mode",
        )
        material_tab3, boundary_tab3, solver_tab3 = st.tabs(
            ["Material & Source", "Boundary Conditions", "Solver Controls"]
        )
        with material_tab3:
            material3_name = st.selectbox("Preset material 3D", list(MATERIALS.keys()), index=list(MATERIALS.keys()).index("Stainless steel 304"), key="heat3d_material")
            material3 = MATERIALS[material3_name]
            if st.session_state.get("_heat3d_material_applied") != material3_name:
                st.session_state["heat3d_k"] = float(material3["k"])
                st.session_state["heat3d_rho"] = float(material3["rho"])
                st.session_state["heat3d_cp"] = float(material3["cp"])
                st.session_state["_heat3d_material_applied"] = material3_name
            st.caption(material3["description"] + " · " + material3["reference"])
            mat_cols = st.columns(2)
            with mat_cols[0]:
                k3 = number_input_with_unit("Konduktivitas k (W/m·K)", min_value=0.01, max_value=2000.0, step=1.0, key="heat3d_k")
                rho3 = number_input_with_unit("Massa jenis ρ (kg/m³)", min_value=1.0, max_value=25000.0, value=8000.0, step=100.0, key="heat3d_rho")
            with mat_cols[1]:
                cp3 = number_input_with_unit("Kalor jenis cp (J/kg·K)", min_value=1.0, max_value=10000.0, value=500.0, step=10.0, key="heat3d_cp")
                q3 = number_input_with_unit("Sumber panas (W/m³)", min_value=0.0, max_value=1.0e8, value=0.0, step=1000.0, key="heat3d_q")
        with boundary_tab3:
            st.caption("Enam sisi domain menggunakan temperatur tetap (Dirichlet).")
            bc_cols = st.columns(3)
            with bc_cols[0]:
                bxmin = number_input_with_unit("X minimum (°C)", value=100.0, step=5.0, key="heat3d_bxmin")
                bxmax = number_input_with_unit("X maksimum (°C)", value=25.0, step=5.0, key="heat3d_bxmax")
            with bc_cols[1]:
                bymin = number_input_with_unit("Y minimum (°C)", value=25.0, step=5.0, key="heat3d_bymin")
                bymax = number_input_with_unit("Y maksimum (°C)", value=25.0, step=5.0, key="heat3d_bymax")
            with bc_cols[2]:
                bzmin = number_input_with_unit("Z minimum (°C)", value=25.0, step=5.0, key="heat3d_bzmin")
                bzmax = number_input_with_unit("Z maksimum (°C)", value=25.0, step=5.0, key="heat3d_bzmax")
            initial3 = number_input_with_unit("Temperatur awal domain (°C)", value=25.0, step=5.0, key="heat3d_initial")
        with solver_tab3:
            if solver_mode_3d == "Steady-state":
                tol3 = st.select_slider("Toleransi perubahan maksimum (°C)",
                    options=[1e-4, 1e-5, 1e-6, 1e-7], value=1e-5,
                    format_func=lambda v: f"{v:.0e}", key="heat3d_tolerance")
                iter3 = number_input_with_unit("Iterasi maksimum", min_value=100, max_value=10000, value=3000, step=100, key="heat3d_iterations")
                total3 = None
                maxdt3 = None
            else:
                total3 = number_input_with_unit("Durasi simulasi (detik)", min_value=0.001, max_value=100.0, value=0.1, step=0.01, format="%.4f", key="heat3d_total_time")
                maxdt3 = number_input_with_unit("Batas langkah waktu maksimum (detik)", min_value=1e-8, max_value=1.0, value=0.001, format="%.6g", key="heat3d_max_dt")
                tol3 = None
                iter3 = None

        boundary3 = {
            "x_min": float(bxmin), "x_max": float(bxmax),
            "y_min": float(bymin), "y_max": float(bymax),
            "z_min": float(bzmin), "z_max": float(bzmax),
        }
        if solver_mode_3d == "Transient":
            stable_dt3 = stable_time_step_3d(
                float(k3), float(rho3), float(cp3),
                active_mesh["dx"], active_mesh["dy"], active_mesh["dz"],
            )
            st.caption(f"Batas stabilitas eksplisit untuk mesh dan material ini: dt ≤ {stable_dt3:.5g} s. Solver otomatis memilih langkah waktu aman berdasarkan batas tersebut dan input maksimum di atas.")
        if st.button("▶ Jalankan simulasi Heat Transfer 3D", key="run_heat3d", type="primary", disabled=not solver_allowed):
            try:
                if solver_mode_3d == "Steady-state":
                    solver_fn = solve_steady_state_3d
                    solver_args = (
                        active_mesh["nx"], active_mesh["ny"], active_mesh["nz"],
                        active_mesh["lx"], active_mesh["ly"], active_mesh["lz"],
                        float(k3), float(q3), boundary3,
                    )
                    solver_kwargs = {
                        "initial_temperature": float(initial3),
                        "tolerance": float(tol3), "max_iterations": int(iter3),
                    }
                else:
                    solver_fn = solve_transient_3d
                    solver_args = (
                        active_mesh["nx"], active_mesh["ny"], active_mesh["nz"],
                        active_mesh["lx"], active_mesh["ly"], active_mesh["lz"],
                        float(k3), float(rho3), float(cp3), float(q3), boundary3,
                        float(initial3), float(total3), float(maxdt3),
                    )
                    solver_kwargs = {"snapshot_count": 9}
                mesh_info = {key: active_mesh[key] for key in ("nx", "ny", "nz", "lx", "ly", "lz")}
                material_info = {
                    "k": float(k3), "rho": float(rho3), "cp": float(cp3),
                    "q": float(q3), "initial": float(initial3), "boundary": boundary3.copy(),
                }
                st.session_state["heat3d_job_id"] = submit_job(
                    "heat-transfer-3d", _run_3d_job, solver_fn, solver_args,
                    solver_kwargs, solver_mode_3d, mesh_info, material_info,
                )
                st.session_state.pop("heat3d_error", None)
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                st.session_state["heat3d_error"] = f"Input tidak valid: {exc}"
        render_job_monitor("heat3d_job_id", "heat3d_job_payload", "Solver Heat Transfer 3D")
        payload3 = st.session_state.pop("heat3d_job_payload", None)
        if payload3:
            st.session_state["heat3d_result"] = payload3["result"]
            st.session_state["heat3d_result_mesh"] = payload3["mesh"]
            for key, value in payload3["material"].items():
                st.session_state["heat3d_result_" + key] = value
        if st.session_state.get("heat3d_error"):
            st.error("Simulasi 3D gagal: " + st.session_state["heat3d_error"])

        result3 = st.session_state.get("heat3d_result")
        result_mesh3 = st.session_state.get("heat3d_result_mesh")
        if result3 and result_mesh3 == {
            "nx": active_mesh["nx"], "ny": active_mesh["ny"], "nz": active_mesh["nz"],
            "lx": active_mesh["lx"], "ly": active_mesh["ly"], "lz": active_mesh["lz"],
        }:
            T3 = result3["temperature"]
            if result3["mode"] == "Transient" and result3.get("snapshots"):
                snap3 = render_transient_pill(len(result3["snapshots"]), result3["snapshot_times"], "heat3d_playback")
                viewT3 = result3["snapshots"][snap3]
                viewtime3 = result3["snapshot_times"][snap3]
                st.caption(f"Snapshot pada t = {viewtime3:.5g} s dari total {result3['simulated_time']:.5g} s.")
            else:
                viewT3 = T3
            qx3, qy3, qz3, qmag3 = calculate_heat_flux_3d(
                viewT3, st.session_state.get("heat3d_result_k", float(k3)),
                active_mesh["dx"], active_mesh["dy"], active_mesh["dz"],
            )
            rcols = st.columns(4)
            rcols[0].metric("Temperatur minimum", f"{viewT3.min():.3f} °C")
            rcols[1].metric("Temperatur maksimum", f"{viewT3.max():.3f} °C")
            rcols[2].metric("Fluks panas maksimum", f"{qmag3.max():.4g} W/m²")
            if result3["mode"] == "Steady-state":
                rcols[3].metric("Iterasi", f"{result3['iterations']:,}")
                st.caption(f"Status konvergensi: {'Tercapai' if result3['converged'] else 'Belum tercapai'} · perubahan terakhir {result3['last_delta']:.3e} °C.")
            else:
                rcols[3].metric("Langkah waktu", f"{result3['steps']:,}")
                st.caption(f"dt aktual = {result3['dt_actual']:.4g} s · batas stabilitas = {result3['dt_stability_limit']:.4g} s · jumlah Fourier = {result3['fourier_sum']:.4f}.")
            st.subheader("Analisis irisan temperatur 3D")
            slice_axis3 = st.selectbox(
                "Bidang irisan", ["Z (XY)", "Y (XZ)", "X (YZ)"],
                key="heat3d_slice_axis",
            )
            if slice_axis3 == "Z (XY)":
                slice_index3 = st.slider("Indeks irisan Z", 0, viewT3.shape[0] - 1, viewT3.shape[0] // 2, key="heat3d_slice_z")
                slice_values3 = viewT3[slice_index3, :, :]
                slice_x3, slice_y3 = active_mesh["x"], active_mesh["y"]
                axis_labels3 = ("X (m)", "Y (m)")
                slice_title3 = f"Irisan bidang XY pada Z = {active_mesh['z'][slice_index3]:.5g} m"
                hover3 = "x=%{x:.4g} m<br>y=%{y:.4g} m<br>T=%{z:.3f} °C<extra></extra>"
            elif slice_axis3 == "Y (XZ)":
                slice_index3 = st.slider("Indeks irisan Y", 0, viewT3.shape[1] - 1, viewT3.shape[1] // 2, key="heat3d_slice_y")
                slice_values3 = viewT3[:, slice_index3, :]
                slice_x3, slice_y3 = active_mesh["x"], active_mesh["z"]
                axis_labels3 = ("X (m)", "Z (m)")
                slice_title3 = f"Irisan bidang XZ pada Y = {active_mesh['y'][slice_index3]:.5g} m"
                hover3 = "x=%{x:.4g} m<br>z=%{y:.4g} m<br>T=%{z:.3f} °C<extra></extra>"
            else:
                slice_index3 = st.slider("Indeks irisan X", 0, viewT3.shape[2] - 1, viewT3.shape[2] // 2, key="heat3d_slice_x")
                slice_values3 = viewT3[:, :, slice_index3]
                slice_x3, slice_y3 = active_mesh["y"], active_mesh["z"]
                axis_labels3 = ("Y (m)", "Z (m)")
                slice_title3 = f"Irisan bidang YZ pada X = {active_mesh['x'][slice_index3]:.5g} m"
                hover3 = "y=%{x:.4g} m<br>z=%{y:.4g} m<br>T=%{z:.3f} °C<extra></extra>"
            slice_fig3 = go.Figure(go.Heatmap(
                z=slice_values3, x=slice_x3, y=slice_y3,
                colorscale="Inferno", colorbar={"title": {"text": "TEMPERATUR<br>°C", "side": "right"}, "thickness": 11, "len": 0.78, "x": 1.02, "y": 0.5, "bgcolor": "rgba(20,32,45,0.28)", "outlinewidth": 0, "tickfont": {"size": 10}, "tickmode": "auto"},
                hovertemplate=hover3,
            ))
            slice_fig3.update_layout(
                title=slice_title3, xaxis_title=axis_labels3[0],
                yaxis_title=axis_labels3[1], height=470,
            )
            st.plotly_chart(slice_fig3, use_container_width=True, key="heat3d_selected_slice")

            st.subheader("3D Temperature Probe")
            probe_cols3 = st.columns(3)
            with probe_cols3[0]:
                probe_ix3 = st.slider("Indeks X", 0, viewT3.shape[2] - 1, viewT3.shape[2] // 2, key="heat3d_probe_x")
            with probe_cols3[1]:
                probe_iy3 = st.slider("Indeks Y", 0, viewT3.shape[1] - 1, viewT3.shape[1] // 2, key="heat3d_probe_y")
            with probe_cols3[2]:
                probe_iz3 = st.slider("Indeks Z", 0, viewT3.shape[0] - 1, viewT3.shape[0] // 2, key="heat3d_probe_z")
            probe_temp3 = float(viewT3[probe_iz3, probe_iy3, probe_ix3])
            st.metric("Temperatur pada titik probe", f"{probe_temp3:.4f} °C")
            st.caption(
                f"Node ({probe_ix3}, {probe_iy3}, {probe_iz3}) · "
                f"x={active_mesh['x'][probe_ix3]:.5g} m · "
                f"y={active_mesh['y'][probe_iy3]:.5g} m · "
                f"z={active_mesh['z'][probe_iz3]:.5g} m."
            )

            min_loc3 = np.unravel_index(int(np.argmin(viewT3)), viewT3.shape)
            max_loc3 = np.unravel_index(int(np.argmax(viewT3)), viewT3.shape)
            extrema_cols3 = st.columns(2)
            extrema_cols3[0].metric("Lokasi T minimum (i,j,k)", f"({min_loc3[2]}, {min_loc3[1]}, {min_loc3[0]})")
            extrema_cols3[1].metric("Lokasi T maksimum (i,j,k)", f"({max_loc3[2]}, {max_loc3[1]}, {max_loc3[0]})")
            st.caption(
                f"T minimum berada pada x={active_mesh['x'][min_loc3[2]]:.5g}, "
                f"y={active_mesh['y'][min_loc3[1]]:.5g}, z={active_mesh['z'][min_loc3[0]]:.5g} m; "
                f"T maksimum pada x={active_mesh['x'][max_loc3[2]]:.5g}, "
                f"y={active_mesh['y'][max_loc3[1]]:.5g}, z={active_mesh['z'][max_loc3[0]]:.5g} m."
            )
            zc, yc, xc = np.meshgrid(active_mesh["z"], active_mesh["y"], active_mesh["x"], indexing="ij")
            volume_fig3 = go.Figure(go.Volume(
                x=xc.ravel(), y=yc.ravel(), z=zc.ravel(), value=viewT3.ravel(),
                isomin=float(viewT3.min()) - 1e-9, isomax=float(viewT3.max()) + 1e-9,
                opacity=0.12, surface_count=12, colorscale="Inferno",
                colorbar={"title": {"text": "TEMPERATUR<br>°C", "side": "right"}, "thickness": 11, "len": 0.78, "x": 1.02, "y": 0.5, "bgcolor": "rgba(20,32,45,0.28)", "outlinewidth": 0, "tickfont": {"size": 10}},
            ))
            volume_fig3.update_layout(
                title="Visualisasi volume temperatur 3D",
                scene={"xaxis_title": "X (m)", "yaxis_title": "Y (m)", "zaxis_title": "Z (m)", "aspectmode": "data"},
                height=700, margin={"l": 0, "r": 82, "t": 50, "b": 0},
            )
            st.plotly_chart(volume_fig3, use_container_width=True, key="heat3d_volume")

            st.subheader("Vektor fluks panas 3D")
            st.caption(
                "Arah panah menunjukkan arah fluks panas menurut Hukum Fourier "
                "(q = −k∇T); warna menunjukkan besar fluks dalam W/m². "
                "Tampilan memakai sampel node agar visualisasi tidak terlalu berat."
            )
            stride_x3 = max(1, int(np.ceil(active_mesh["nx"] / 7)))
            stride_y3 = max(1, int(np.ceil(active_mesh["ny"] / 7)))
            stride_z3 = max(1, int(np.ceil(active_mesh["nz"] / 7)))
            xs3 = active_mesh["x"][::stride_x3]
            ys3 = active_mesh["y"][::stride_y3]
            zs3 = active_mesh["z"][::stride_z3]
            if xs3[-1] != active_mesh["x"][-1]:
                xs3 = np.append(xs3, active_mesh["x"][-1])
            if ys3[-1] != active_mesh["y"][-1]:
                ys3 = np.append(ys3, active_mesh["y"][-1])
            if zs3[-1] != active_mesh["z"][-1]:
                zs3 = np.append(zs3, active_mesh["z"][-1])
            qx_sample3 = qx3[::stride_z3, ::stride_y3, ::stride_x3]
            qy_sample3 = qy3[::stride_z3, ::stride_y3, ::stride_x3]
            qz_sample3 = qz3[::stride_z3, ::stride_y3, ::stride_x3]
            qm_sample3 = qmag3[::stride_z3, ::stride_y3, ::stride_x3]
            zgrid3, ygrid3, xgrid3 = np.meshgrid(zs3, ys3, xs3, indexing="ij")
            flux_threshold3 = max(float(qmag3.max()) * 1e-8, 1e-14)
            flux_mask3 = np.isfinite(qm_sample3) & (qm_sample3 > flux_threshold3)
            if np.any(flux_mask3):
                cone_fig3 = go.Figure(go.Cone(
                    x=xgrid3[flux_mask3], y=ygrid3[flux_mask3], z=zgrid3[flux_mask3],
                    u=qx_sample3[flux_mask3], v=qy_sample3[flux_mask3], w=qz_sample3[flux_mask3],
                    customdata=qm_sample3[flux_mask3],
                    colorscale="Viridis", cmin=0, cmax=float(qmag3.max()),
                    colorbar={"title": {"text": "FLUKS<br>W/m²", "side": "right"}, "thickness": 11, "len": 0.78, "x": 1.02, "y": 0.5, "bgcolor": "rgba(20,32,45,0.28)", "outlinewidth": 0, "tickfont": {"size": 10}}, showscale=True,
                    sizemode="scaled", sizeref=0.5, anchor="tail",
                    hovertemplate=(
                        "x=%{x:.4g} m<br>y=%{y:.4g} m<br>z=%{z:.4g} m"
                        "<br>|q|=%{customdata:.4g} W/m²<extra></extra>"
                    ),
                ))
                cone_fig3.update_layout(
                    title="Arah dan magnitudo fluks panas 3D",
                    scene={
                        "xaxis_title": "X (m)", "yaxis_title": "Y (m)",
                        "zaxis_title": "Z (m)", "aspectmode": "data",
                    },
                    height=560, margin={"l": 0, "r": 82, "t": 50, "b": 0},
                )
                st.plotly_chart(cone_fig3, use_container_width=True, key="heat3d_flux_vectors")
                st.caption(
                    f"Ditampilkan {int(np.count_nonzero(flux_mask3))} vektor dari "
                    f"{int(qm_sample3.size)} titik sampel. Nilai numerik lengkap tersedia pada CSV."
                )
            else:
                st.info("Fluks panas pada seluruh titik sampel mendekati nol; tidak ada vektor yang perlu ditampilkan.")

            st.subheader("Analisis energi & neraca energi 3D · MVP 1.9")
            st.caption(
                "Estimasi energi internal, daya sumber panas, dan panas yang keluar melalui "
                "enam permukaan. Integrasi memakai bobot control-volume/trapesium pada grid."
            )
            try:
                energy_args3 = (
                    T3 if result3["mode"] == "Transient" else viewT3,
                    st.session_state.get("heat3d_result_k", float(k3)),
                    st.session_state.get("heat3d_result_rho", float(rho3)),
                    st.session_state.get("heat3d_result_cp", float(cp3)),
                    st.session_state.get("heat3d_result_q", float(q3)),
                    active_mesh["dx"], active_mesh["dy"], active_mesh["dz"],
                    st.session_state.get("heat3d_result_initial", float(initial3)),
                    st.session_state.get("heat3d_result_boundary", boundary3),
                )
                if result3["mode"] == "Transient":
                    energy3 = analyze_energy_balance_3d(
                        *energy_args3, snapshots=result3.get("snapshots"),
                        snapshot_times=result3.get("snapshot_times"),
                    )
                else:
                    energy3 = analyze_energy_balance_3d(*energy_args3)
                if energy3["mode"] == "Transient":
                    ecols3 = st.columns(4)
                    ecols3[0].metric("Perubahan energi internal", f"{energy3['delta_internal_energy_J']:.5g} J")
                    ecols3[1].metric("Energi dari sumber", f"{energy3['generated_energy_J']:.5g} J")
                    ecols3[2].metric("Energi keluar batas", f"{energy3['outward_energy_J']:.5g} J")
                    ecols3[3].metric("Error neraca relatif", f"{energy3['relative_balance_error_pct']:.3g}%")
                    st.caption(
                        f"Residu ΔU − (E sumber − E keluar) = {energy3['balance_residual_J']:.5g} J · "
                        f"Daya keluar pada snapshot terpilih = {energy3['final_outward_power_W']:.5g} W."
                    )
                else:
                    ecols3 = st.columns(4)
                    ecols3[0].metric("Volume domain", f"{energy3['volume_m3']:.5g} m³")
                    ecols3[1].metric("Daya sumber panas", f"{energy3['source_power_W']:.5g} W")
                    ecols3[2].metric("Daya keluar batas", f"{energy3['outward_power_W']:.5g} W")
                    ecols3[3].metric("Error neraca relatif", f"{energy3['relative_balance_error_pct']:.3g}%")
                    st.caption(f"Residu daya (sumber − keluar) = {energy3['balance_residual_W']:.5g} W.")
                st.dataframe(
                    [{"Permukaan": face, "Daya keluar (W)": value}
                     for face, value in energy3["face_power_W"].items()],
                    use_container_width=True, hide_index=True,
                )
                st.info(
                    "Catatan numerik: ini adalah estimasi post-processing dari gradien batas "
                    "dan integrasi berbobot pada grid node-centred. Solver saat ini memakai "
                    "finite difference Jacobi/eksplisit, bukan formulasi finite-volume yang "
                    "menjamin konservasi lokal; residu neraca dipakai sebagai indikator, "
                    "bukan bukti validasi atau akurasi eksperimen."
                )
            except Exception as energy_exc3:
                st.warning("Analisis energi belum dapat dihitung: " + str(energy_exc3))

            flux_csv3 = io.StringIO()
            flux_csv3.write("x_m,y_m,z_m,temperature_C,qx_W_m2,qy_W_m2,qz_W_m2,q_magnitude_W_m2\n")
            for iz, zv in enumerate(active_mesh["z"]):
                for iy, yv in enumerate(active_mesh["y"]):
                    for ix, xv in enumerate(active_mesh["x"]):
                        flux_csv3.write(
                            f"{xv:.8g},{yv:.8g},{zv:.8g},{viewT3[iz,iy,ix]:.8g},"
                            f"{qx3[iz,iy,ix]:.8g},{qy3[iz,iy,ix]:.8g},"
                            f"{qz3[iz,iy,ix]:.8g},{qmag3[iz,iy,ix]:.8g}\n"
                        )
            st.download_button(
                "⬇ Unduh hasil temperatur dan fluks 3D (CSV)",
                flux_csv3.getvalue().encode("utf-8"),
                file_name="physics_ai_studio_heat_transfer_3d.csv",
                mime="text/csv",
            )
            st.info("Hasil ini berasal dari model konduksi 3D pada balok Cartesian. Kondisi batas tetap diterapkan pada enam bidang; geometri kubus/balok/silinder dari Geometry Builder belum dipakai sebagai domain pemotongan. Belum ada konveksi, radiasi, kontak termal, atau validasi eksperimen.")

DEFAULT_SETTINGS = {
    "mode": "Steady-state", "material_name": "Custom", "nx": 41, "ny": 41,
    "solver_tolerance": 1e-6, "solver_max_iterations": 30000,
    "lx": 0.10, "ly": 0.10, "k": 45.0, "rho": 7800.0, "cp": 500.0,
    "t_left": 100.0, "t_right": 25.0, "t_top": 25.0, "t_bottom": 25.0,
    "t_initial": 25.0, "q_vol": 0.0, "total_time": 10.0,
}
SETTING_KEYS = tuple(DEFAULT_SETTINGS.keys())

def read_settings():
    return {key: st.session_state[key] for key in SETTING_KEYS}

def record_settings_change():
    current = read_settings()
    previous = st.session_state.get("_settings_current", DEFAULT_SETTINGS.copy())
    if current != previous:
        history = st.session_state.setdefault("_settings_undo", [])
        history.append(previous.copy())
        if len(history) > 50:
            del history[0]
        st.session_state["_settings_redo"] = []
        st.session_state["_settings_current"] = current.copy()

def apply_settings(target):
    for key, value in target.items():
        st.session_state[key] = value
    st.session_state["_settings_current"] = target.copy()

def undo_settings():
    history = st.session_state.get("_settings_undo", [])
    if not history:
        return
    current = read_settings()
    target = history.pop()
    st.session_state.setdefault("_settings_redo", []).append(current.copy())
    apply_settings(target)

def redo_settings():
    history = st.session_state.get("_settings_redo", [])
    if not history:
        return
    current = read_settings()
    target = history.pop()
    st.session_state.setdefault("_settings_undo", []).append(current.copy())
    apply_settings(target)


def save_preset():
    name = st.session_state.get("preset_name_input", "").strip()
    if not name:
        st.session_state["_preset_message"] = "Masukkan nama preset terlebih dahulu."
        return
    st.session_state.setdefault("_user_presets", {})[name] = read_settings()
    st.session_state["_preset_selected"] = name
    st.session_state["_preset_message"] = f"Preset '{name}' berhasil disimpan pada sesi ini."

def load_preset():
    name = st.session_state.get("_preset_selected")
    preset = st.session_state.get("_user_presets", {}).get(name)
    if preset:
        current = read_settings()
        st.session_state.setdefault("_settings_undo", []).append(current.copy())
        st.session_state["_settings_redo"] = []
        apply_settings(preset.copy())
        st.session_state["_preset_message"] = f"Preset '{name}' diterapkan."

def delete_preset():
    name = st.session_state.get("_preset_selected")
    presets = st.session_state.setdefault("_user_presets", {})
    if name in presets:
        del presets[name]
        st.session_state["_preset_selected"] = next(iter(presets), "")
        st.session_state["_preset_message"] = f"Preset '{name}' dihapus."

def import_preset():
    uploaded = st.session_state.get("preset_upload")
    if uploaded is None:
        st.session_state["_preset_message"] = "Pilih file preset JSON terlebih dahulu."
        return
    try:
        payload = json.loads(uploaded.getvalue().decode("utf-8"))
        settings = payload.get("settings", payload)
        if set(settings) != set(SETTING_KEYS):
            raise ValueError("Struktur parameter tidak cocok.")
        if settings["mode"] not in ("Steady-state", "Transient"):
            raise ValueError("Mode simulasi tidak valid.")
        if settings["material_name"] not in MATERIALS:
            raise ValueError("Material preset tidak dikenal.")
        numeric = [key for key in SETTING_KEYS if key not in ("mode", "material_name")]
        if any(not isinstance(settings[key], (int, float)) or isinstance(settings[key], bool) for key in numeric):
            raise ValueError("Semua parameter numerik harus berupa angka.")
        ranges = {
            "nx": (11, 101), "ny": (11, 101), "lx": (0.01, 2.0), "ly": (0.01, 2.0),
            "k": (0.01, 2000), "rho": (1, 25000), "cp": (1, 10000),
            "q_vol": (0, 1.0e8), "total_time": (0.01, 10000),
            "solver_tolerance": (1e-10, 1e-2), "solver_max_iterations": (1000, 100000),
        }
        for key, (low, high) in ranges.items():
            if not low <= settings[key] <= high:
                raise ValueError(f"Nilai {key} di luar rentang.")
        if not isinstance(settings["nx"], int) or not isinstance(settings["ny"], int) or not isinstance(settings["solver_max_iterations"], int):
            raise ValueError("Jumlah grid harus berupa bilangan bulat.")
        if settings["nx"] % 2 == 0 or settings["ny"] % 2 == 0:
            raise ValueError("Jumlah grid harus ganjil.")
        name = payload.get("name", "Imported preset")
        st.session_state.setdefault("_user_presets", {})[name] = settings
        st.session_state["_preset_selected"] = name
        st.session_state["_preset_message"] = f"Preset '{name}' berhasil diimpor."
    except Exception as exc:
        st.session_state["_preset_message"] = f"Impor gagal: {exc}"

def select_material():
    name = st.session_state.get("material_name", "Custom")
    material = MATERIALS.get(name)
    if material and name != "Custom":
        for key in ("k", "rho", "cp"):
            st.session_state[key] = material[key]
    record_settings_change()


def reset_settings():
    current = read_settings()
    if current != DEFAULT_SETTINGS:
        st.session_state.setdefault("_settings_undo", []).append(current.copy())
        st.session_state["_settings_redo"] = []
    apply_settings(DEFAULT_SETTINGS.copy())

for _key, _value in DEFAULT_SETTINGS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _value
if "_settings_current" not in st.session_state:
    st.session_state["_settings_current"] = read_settings()
st.session_state.setdefault("_settings_undo", [])
st.session_state.setdefault("_settings_redo", [])

with st.container(key="bottom_sheet"):
    st.markdown('<div class="sheet-grip"></div><div class="sheet-heading">CONTROL DECK <span>PARAMETERS · STUDY · RUN</span></div>', unsafe_allow_html=True)
    with st.expander("⚙ Buka panel pengaturan simulasi", expanded=False):
        st.header("Control Deck · Parameter simulasi 2D")
        st.caption("Atur model, geometri, material, kondisi batas, dan solver melalui tab berikut.")
        preset_tab, model_tab, material_tab, boundary_tab, solver_tab = st.tabs(
            ["Preset & Riwayat", "Model & Mesh", "Material & Geometri", "Boundary Conditions", "Solver & Run"]
        )
        with preset_tab:
            h1, h2 = st.columns(2)
            h1.button("↶ Undo", use_container_width=True, disabled=not st.session_state["_settings_undo"], on_click=undo_settings)
            h2.button("↷ Redo", use_container_width=True, disabled=not st.session_state["_settings_redo"], on_click=redo_settings)
            st.button("⟲ Default Settings", use_container_width=True, on_click=reset_settings)
            st.caption("Undo/Redo menyimpan hingga 50 perubahan parameter.")
            st.divider()
            st.text_input("Nama preset", key="preset_name_input", placeholder="Contoh: Aluminium 2D")
            st.button("💾 Simpan konfigurasi saat ini", use_container_width=True, on_click=save_preset)
            _presets = st.session_state.setdefault("_user_presets", {})
            if _presets:
                st.selectbox("Preset tersimpan", list(_presets.keys()), key="_preset_selected")
                st.button("Terapkan preset", use_container_width=True, on_click=load_preset)
                st.button("Hapus preset terpilih", use_container_width=True, on_click=delete_preset)
                _selected = st.session_state.get("_preset_selected")
                if _selected in _presets:
                    st.download_button("⬇ Ekspor preset JSON",
                        json.dumps({"name": _selected, "settings": _presets[_selected]}, indent=2).encode("utf-8"),
                        file_name=f"physics_ai_preset_{_selected.lower().replace(' ', '_')}.json",
                        mime="application/json", use_container_width=True)
            st.file_uploader("Impor preset JSON", type=["json"], key="preset_upload")
            st.button("Impor file preset", use_container_width=True, on_click=import_preset)
            if st.session_state.get("_preset_message"):
                st.caption(st.session_state["_preset_message"])
        with model_tab:
            mode = st.selectbox("Jenis simulasi", ["Steady-state", "Transient"], key="mode", on_change=record_settings_change)
            st.markdown("**Kepadatan mesh 2D**")
            mesh_density = st.selectbox(
                "Preset mesh", ["Coarse / Kasar", "Normal", "Fine / Halus"],
                index=1, key="mesh_density_2d", help="Preset mengatur jumlah node awal; nilai X/Y tetap dapat disesuaikan manual."
            )
            mesh_defaults = {"Coarse / Kasar": 21, "Normal": 41, "Fine / Halus": 71}
            if st.session_state.get("_mesh_density_applied") != mesh_density:
                st.session_state["nx"] = mesh_defaults[mesh_density]
                st.session_state["ny"] = mesh_defaults[mesh_density]
                st.session_state["_mesh_density_applied"] = mesh_density
            nx = slider_with_stepper("Jumlah grid arah X", 11, 101, step=2, key="nx", on_change=record_settings_change)
            ny = slider_with_stepper("Jumlah grid arah Y", 11, 101, step=2, key="ny", on_change=record_settings_change)
            st.caption(f"Mesh {mesh_density}: {nx} × {ny} node · {(nx-1)*(ny-1):,} elemen persegi.")

        with material_tab:
            st.markdown("**Geometri domain**")
            geo_a, geo_b = st.columns(2)
            with geo_a:
                lx = number_input_with_unit("Panjang X (m)", 0.01, 2.0, step=0.01, format="%.3f", key="lx", on_change=record_settings_change)
            with geo_b:
                ly = number_input_with_unit("Panjang Y (m)", 0.01, 2.0, step=0.01, format="%.3f", key="ly", on_change=record_settings_change)
            st.divider()
            material_name = st.selectbox("Pilih material", list(MATERIALS.keys()), key="material_name", on_change=select_material)
            material_info = MATERIALS[material_name]
            st.caption(material_info["description"])
            if material_name != "Custom":
                st.caption("Sumber data: " + material_info["reference"])
            mat_a, mat_b, mat_c = st.columns(3)
            with mat_a:
                k = number_input_with_unit("Konduktivitas termal k (W/m·K)", 0.01, 2000.0, step=1.0, key="k", on_change=record_settings_change)
            with mat_b:
                rho = number_input_with_unit("Massa jenis (kg/m³)", 0.01, 25000.0, step=100.0, key="rho", on_change=record_settings_change)
            with mat_c:
                cp = number_input_with_unit("Kalor jenis cp (J/kg·K)", 1.0, 10000.0, step=10.0, key="cp", on_change=record_settings_change)
            if material_name == "Custom":
                st.markdown("**Properti material custom**")
                custom_a, custom_b, custom_c = st.columns(3)
                with custom_a:
                    st.number_input("Modulus elastisitas E (Pa)", min_value=0.0, value=float(st.session_state.get("custom_E", 2.0e11)), format="%.3e", key="custom_E")
                with custom_b:
                    st.number_input("Viskositas dinamis μ (Pa·s)", min_value=0.0, value=float(st.session_state.get("custom_mu", 0.0)), format="%.3e", key="custom_mu")
                with custom_c:
                    st.number_input("Rasio Poisson ν", min_value=0.0, max_value=0.499, value=float(st.session_state.get("custom_nu", 0.30)), format="%.3f", key="custom_nu")
            else:
                st.caption(f"{('E = ' + format(material_info['E'], '.3e') + ' Pa') if material_info.get('E') is not None else ('K bulk = ' + format(material_info.get('K_bulk', 0), '.3e') + ' Pa')} · μ = {material_info['mu']:.3e} Pa·s · {('ν = ' + format(material_info['nu'], '.3f')) if material_info.get('nu') is not None else 'ν = tidak berlaku'} · α = {material_info['alpha']:.3e} 1/K")
            st.caption("E, μ, ν, dan α disimpan sebagai properti referensi material. Solver panas saat ini menggunakan k, ρ, dan cp.");

        with boundary_tab:
            st.caption("Temperatur pada keempat sisi pelat dianggap tetap (Dirichlet).")
            bc_a, bc_b = st.columns(2)
            with bc_a:
                t_left = number_input_with_unit("Sisi kiri (°C)", step=5.0, key="t_left", on_change=record_settings_change)
                t_top = number_input_with_unit("Sisi atas (°C)", step=5.0, key="t_top", on_change=record_settings_change)
            with bc_b:
                t_right = number_input_with_unit("Sisi kanan (°C)", step=5.0, key="t_right", on_change=record_settings_change)
                t_bottom = number_input_with_unit("Sisi bawah (°C)", step=5.0, key="t_bottom", on_change=record_settings_change)
            t_initial = number_input_with_unit("Temperatur awal (°C)", step=5.0, key="t_initial", on_change=record_settings_change)
            q_vol = number_input_with_unit("Pembangkitan panas volumetrik (W/m³)", 0.0, 1.0e8, step=1000.0, key="q_vol", on_change=record_settings_change)
            if mode == "Transient":
                total_time = number_input_with_unit("Lama simulasi (detik)", 0.01, 10000.0, step=1.0, key="total_time", on_change=record_settings_change)
                st.markdown("**Titik pemantauan temperatur**")
                probe_a, probe_b = st.columns(2)
                with probe_a:
                    probe_x_index = st.slider("Indeks titik X", 0, nx - 1, nx // 2, key="probe_x_2d", help="0 = sisi kiri; indeks maksimum = sisi kanan.")
                with probe_b:
                    probe_y_index = st.slider("Indeks titik Y", 0, ny - 1, ny // 2, key="probe_y_2d", help="0 = sisi bawah; indeks maksimum = sisi atas.")
            else:
                total_time = None
                probe_x_index, probe_y_index = nx // 2, ny // 2
        with solver_tab:
            solver_a, solver_b = st.columns(2)
            with solver_a:
                solver_tolerance = number_input_with_unit("Toleransi konvergensi (°C)", min_value=1e-10, max_value=1e-2, step=1e-7, format="%.1e", key="solver_tolerance", on_change=record_settings_change, help="Batas perubahan maksimum temperatur antar iterasi Jacobi.")
            with solver_b:
                solver_max_iterations = number_input_with_unit("Iterasi maksimum", min_value=1000, max_value=100000, step=1000, key="solver_max_iterations", on_change=record_settings_change)
            st.caption("Steady-state memakai iterasi Jacobi; transient memakai skema eksplisit dengan batas stabilitas waktu.")
            run = st.button("▶ Jalankan simulasi", type="primary", use_container_width=True) or toolbar_run

with st.expander("✅ Verifikasi numerik otomatis", expanded=False):
    st.write("Jalankan lima kasus uji untuk memeriksa implementasi numerik dasar dan pencatatan probe transient. Pengujian ini memeriksa implementasi numerik dasar, bukan validasi eksperimen.")
    if st.button("Jalankan semua uji verifikasi", key="run_verification"):
        try:
            st.session_state["verification_results"] = run_verification_suite()
        except Exception as exc:
            st.session_state["verification_error"] = str(exc)
    if st.session_state.get("verification_error"):
        st.error("Verifikasi gagal dijalankan: " + st.session_state["verification_error"])
    verification_results = st.session_state.get("verification_results", [])
    if verification_results:
        passed_count = sum(item["Status"] == "LULUS" for item in verification_results)
        total_count = len(verification_results)
        v1, v2 = st.columns(2)
        v1.metric("Uji lulus", f"{passed_count}/{total_count}")
        v2.metric("Status keseluruhan", "LULUS" if passed_count == total_count else "PERLU PERIKSA")
        st.dataframe(verification_results, use_container_width=True, hide_index=True)
        st.caption("Error dibandingkan dengan hasil analitik. Toleransi numerik setiap kasus: 1×10⁻⁸.")
        
c1, c2, c3, c4 = st.columns(4)
c1.metric("Grid", f"{nx} × {ny}")
c2.metric("Ukuran pelat", f"{lx:.2f} × {ly:.2f} m")
c3.metric("Konduktivitas", f"{k:g} W/m·K")
c4.metric("Difusivitas termal", f"{k/(rho*cp):.3e} m²/s")

if run:
    st.session_state.pop("mesh_study_result", None)
    boundary = {"left": float(t_left), "right": float(t_right), "top": float(t_top), "bottom": float(t_bottom)}
    try:
        st.session_state.pop("last_result", None)
        st.session_state["heat2d_job_id"] = submit_job(
            "heat-transfer-2d", _run_2d_job,
            mode, int(nx), int(ny), float(lx), float(ly), float(k),
            float(rho), float(cp), float(q_vol), boundary, float(t_initial),
            None if total_time is None else float(total_time),
            float(solver_tolerance), int(solver_max_iterations),
            int(probe_x_index), int(probe_y_index), str(material_name),
        )
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        st.error(f"Input simulasi tidak valid: {exc}")

render_job_monitor("heat2d_job_id", "heat2d_job_payload", "Solver Heat Transfer 2D")
payload2 = st.session_state.pop("heat2d_job_payload", None)
if payload2:
    submitted2 = payload2["params"]
    mode = submitted2["mode"]
    nx, ny, lx, ly = submitted2["nx"], submitted2["ny"], submitted2["lx"], submitted2["ly"]
    k, rho, cp, q_vol = submitted2["k"], submitted2["rho"], submitted2["cp"], submitted2["q"]
    boundary, t_initial, total_time = submitted2["boundary"], submitted2["initial"], submitted2["total_time"]
    material_name = submitted2["material_name"]
    solver_tolerance, solver_max_iterations = submitted2["solver_tolerance"], submitted2["solver_max_iterations"]
    result = payload2["result"]
    residual = payload2["residual"]
    transient_diagnostics = payload2["transient_diagnostics"]
    if mode == "Steady-state":
        info = f"Steady-state · {result['iterations']:,} iterasi · konvergen: {'Ya' if result['converged'] else 'Belum'}"
        extra = f"Perubahan maksimum iterasi terakhir: {result['last_delta']:.3e} °C"
    else:
        info = f"Transient · {result['steps']:,} langkah · waktu akhir: {result['simulated_time']:.6g} s"
        extra = f"dt aktual = {result['dt']:.3e} s · batas stabilitas = {transient_diagnostics['dt_stability_limit']:.3e} s · rasio stabilitas = {transient_diagnostics['stability_ratio']:.3f}"
    st.session_state["last_result"] = {
        "T": result["temperature"], "x": np.linspace(0, lx, nx), "y": np.linspace(0, ly, ny),
        "snapshots": result.get("snapshots", []), "snapshot_times": result.get("snapshot_times", []),
        "probe_times": result.get("probe_times", []),
        "probe_temperatures": result.get("probe_temperatures", []),
        "probe_x": result.get("probe_x", probe_x_index),
        "probe_y": result.get("probe_y", probe_y_index),
        "mode": mode, "info": info, "extra": extra,
        "p": {"nx": nx, "ny": ny, "lx": lx, "ly": ly, "k": k, "rho": rho, "cp": cp, "q": q_vol,
              "boundary": boundary, "initial": t_initial, "total_time": total_time,
              "material_name": material_name, "solver_tolerance": solver_tolerance,
              "solver_max_iterations": solver_max_iterations},
        "residual": residual, "transient_diagnostics": transient_diagnostics,
    }
    st.success("Simulasi selesai. Hasil numerik berhasil dihitung.")

data = st.session_state.get("last_result")
if data is None:
    st.info("Atur parameter pada panel kiri, lalu tekan **Jalankan simulasi**.")
    st.markdown("**Asumsi MVP:** konduksi 2D, material homogen dan isotropik, tanpa konveksi/radiasi, serta temperatur sisi pelat tetap.")
else:
    T, x, y = data["T"], data["x"], data["y"]
    qx, qy, qmag = calculate_heat_flux(T, data["p"]["k"], data["p"]["lx"], data["p"]["ly"])
    st.divider()
    if data.get("transient_diagnostics") is not None:
        td = data["transient_diagnostics"]
        with st.expander("Diagnostik stabilitas transient", expanded=True):
            st.caption("Syarat stabilitas skema eksplisit 2D: Fo_x + Fo_y ≤ 0,5.")
            d1, d2, d3 = st.columns(3)
            d1.metric("Difusivitas termal", f"{td['thermal_diffusivity']:.3e} m²/s")
            d2.metric("Fo_x + Fo_y", f"{td['fourier_sum']:.4f}")
            d3.metric("Rasio dt / dt kritis", f"{td['stability_ratio']:.3f}")
            st.write(f"Fo_x = {td['fourier_x']:.5f} · Fo_y = {td['fourier_y']:.5f}")
            st.write(f"dt aktual = {td['dt_actual']:.3e} s · dt kritis = {td['dt_stability_limit']:.3e} s")
            if td["stable"]:
                st.success("Langkah waktu memenuhi batas stabilitas eksplisit.")
            else:
                st.error("Langkah waktu melampaui batas stabilitas eksplisit.")
    st.subheader("Hasil simulasi")
    st.caption(data["info"])
    st.caption(data["extra"])
    a, b, c = st.columns(3)
    a.metric("Temperatur minimum", f"{T.min():.2f} °C")
    b.metric("Temperatur maksimum", f"{T.max():.2f} °C")
    c.metric("Temperatur rata-rata", f"{T.mean():.2f} °C")
    if data.get("residual") is not None:
        st.subheader("Diagnostik residual steady-state")
        st.caption("Residual diskret mengukur seberapa dekat solusi memenuhi persamaan Laplace/Poisson pada node interior. Bandingkan pada mesh dan skala masalah yang sama.")
        r1, r2 = st.columns(2)
        r1.metric("Residual maksimum absolut", f"{data['residual']['residual_max_abs']:.3e} K/m²")
        r2.metric("Residual RMS", f"{data['residual']['residual_rms']:.3e} K/m²")
    fig = go.Figure(go.Heatmap(z=T, x=x, y=y, colorscale="Inferno", colorbar={"title": {"text": "TEMPERATUR<br>°C", "side": "right"}, "thickness": 11, "len": 0.78, "x": 1.02, "y": 0.5, "bgcolor": "rgba(20,32,45,0.28)", "outlinewidth": 0, "tickfont": {"size": 10}},
        hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>T=%{z:.2f} °C<extra></extra>"))
    # Overlay boundary-condition indicators: color-coded edges and temperature labels.
    _bc_colors = {"left": "#38C8F2", "right": "#FFB454", "top": "#A78BFA", "bottom": "#62D5A3"}
    _x0, _x1, _y0, _y1 = float(x[0]), float(x[-1]), float(y[0]), float(y[-1])
    _bc_values = {"left": boundary["left"], "right": boundary["right"], "top": boundary["top"], "bottom": boundary["bottom"]}
    for _side, _color in _bc_colors.items():
        if _side == "left":
            fig.add_shape(type="line", x0=_x0, x1=_x0, y0=_y0, y1=_y1, line={"color": _color, "width": 5})
            _ax, _ay, _text = _x0, (_y0+_y1)/2, f"L {_bc_values[_side]:g}°C"
        elif _side == "right":
            fig.add_shape(type="line", x0=_x1, x1=_x1, y0=_y0, y1=_y1, line={"color": _color, "width": 5})
            _ax, _ay, _text = _x1, (_y0+_y1)/2, f"R {_bc_values[_side]:g}°C"
        elif _side == "top":
            fig.add_shape(type="line", x0=_x0, x1=_x1, y0=_y1, y1=_y1, line={"color": _color, "width": 5})
            _ax, _ay, _text = (_x0+_x1)/2, _y1, f"T {_bc_values[_side]:g}°C"
        else:
            fig.add_shape(type="line", x0=_x0, x1=_x1, y0=_y0, y1=_y0, line={"color": _color, "width": 5})
            _ax, _ay, _text = (_x0+_x1)/2, _y0, f"B {_bc_values[_side]:g}°C"
        fig.add_annotation(x=_ax, y=_ay, text=_text, showarrow=False, bgcolor="rgba(20,32,45,.88)", bordercolor=_color, borderwidth=1, font={"color":_color,"size":10}, xshift=0 if _side in ("top","bottom") else (28 if _side=="left" else -28), yshift=(18 if _side=="top" else -18 if _side=="bottom" else 0))
    if abs(float(q_vol)) > 0:
        fig.add_annotation(x=(_x0+_x1)/2, y=(_y0+_y1)/2, text=f"☀ Heat source<br>{q_vol:.3g} W/m³", showarrow=False, bgcolor="rgba(255,180,84,.88)", font={"color":"#18212B","size":11})
    fig.update_layout(title="Distribusi temperatur 2D · Viewport + indikator boundary", xaxis_title="Posisi X (m)", yaxis_title="Posisi Y (m)", height=680, margin={"l": 12, "r": 82, "t": 52, "b": 12})
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Profil temperatur · Detail hasil", expanded=False):
        mid = len(y)//2
        line = go.Figure(go.Scatter(x=x, y=T[mid, :], mode="lines+markers", name="Profil temperatur"))
        line.update_layout(title=f"Profil suhu pada y = {y[mid]:.4f} m", xaxis_title="Posisi X (m)", yaxis_title="Temperatur (°C)", height=380)
        st.plotly_chart(line, use_container_width=True)
        st.caption("Profil temperatur sepanjang garis tengah pelat.")

    st.subheader("Analisis fluks panas")
    st.caption("Fluks panas dihitung dari Hukum Fourier, q = −k∇T. Panah menunjukkan arah aliran energi panas; warna menunjukkan besar fluks.")
    q1, q2, q3 = st.columns(3)
    q1.metric("Fluks maksimum", f"{float(qmag.max()):.3g} W/m²")
    q2.metric("Fluks rata-rata", f"{float(qmag.mean()):.3g} W/m²")
    q3.metric("Fluks minimum", f"{float(qmag.min()):.3g} W/m²")
    heat_flux_fig = go.Figure(go.Heatmap(
        z=qmag, x=x, y=y, colorscale="Viridis",
        colorbar={"title": {"text": "FLUKS<br>W/m²", "side": "right"}, "thickness": 11, "len": 0.78, "x": 1.02, "y": 0.5, "bgcolor": "rgba(20,32,45,0.28)", "outlinewidth": 0, "tickfont": {"size": 10}},
        hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>|q|=%{z:.3g} W/m²<extra></extra>",
    ))
    arrow_annotations = []
    arrow_stride = max(1, min(len(x), len(y)) // 12)
    arrow_length = 0.34 * min(data["p"]["lx"]/(len(x)-1), data["p"]["ly"]/(len(y)-1))
    for iy in range(1, len(y)-1, arrow_stride):
        for ix in range(1, len(x)-1, arrow_stride):
            magnitude = float(qmag[iy, ix])
            if magnitude <= 1e-14:
                continue
            ux = float(qx[iy, ix] / magnitude)
            uy = float(qy[iy, ix] / magnitude)
            arrow_annotations.append({
                "x": float(x[ix] + ux * arrow_length / 2),
                "y": float(y[iy] + uy * arrow_length / 2),
                "ax": float(x[ix] - ux * arrow_length / 2),
                "ay": float(y[iy] - uy * arrow_length / 2),
                "xref": "x", "yref": "y", "axref": "x", "ayref": "y",
                "showarrow": True, "arrowhead": 2, "arrowsize": 1,
                "arrowwidth": 1.2, "arrowcolor": "white",
            })
    heat_flux_fig.update_layout(
        title="Peta besar dan arah fluks panas",
        xaxis_title="Posisi X (m)", yaxis_title="Posisi Y (m)",
        height=680, margin={"l": 12, "r": 82, "t": 52, "b": 12}, annotations=arrow_annotations,
    )
    st.plotly_chart(heat_flux_fig, use_container_width=True)
    st.caption("Komponen fluks: qx = −k·∂T/∂x dan qy = −k·∂T/∂y. Estimasi gradien memakai beda hingga numerik.")

    if data["mode"] == "Transient" and data.get("probe_temperatures"):
        probe_x_value = float(x[data["probe_x"]])
        probe_y_value = float(y[data["probe_y"]])
        st.subheader("Riwayat temperatur titik pemantauan")
        st.caption(f"Titik grid ({data['probe_x']}, {data['probe_y']}) · posisi x = {probe_x_value:.4f} m, y = {probe_y_value:.4f} m.")
        probe_fig = go.Figure(go.Scatter(
            x=data["probe_times"], y=data["probe_temperatures"],
            mode="lines", name="Temperatur titik",
            hovertemplate="t = %{x:.5g} s<br>T = %{y:.4f} °C<extra></extra>",
        ))
        probe_fig.update_layout(
            title="Perubahan temperatur lokal selama simulasi",
            xaxis_title="Waktu (s)", yaxis_title="Temperatur (°C)", height=380,
        )
        st.plotly_chart(probe_fig, use_container_width=True)
        probe_csv = io.StringIO()
        probe_csv.write("time_s,temperature_C\n")
        for time_value, temp_value in zip(data["probe_times"], data["probe_temperatures"]):
            probe_csv.write(f"{time_value:.10g},{temp_value:.10g}\n")
        st.download_button(
            "⬇ Unduh riwayat temperatur titik (CSV)",
            probe_csv.getvalue().encode("utf-8"),
            file_name="physics_ai_temperature_probe.csv",
            mime="text/csv",
        )

    if data["mode"] == "Transient" and data.get("snapshots"):
        st.subheader("Evolusi temperatur terhadap waktu")
        st.caption("Geser indeks waktu untuk melihat bagaimana panas menyebar dari kondisi awal hingga akhir.")
        frame_index = render_transient_pill(len(data["snapshots"]), data["snapshot_times"], "heat2d_playback")
        frame_T = data["snapshots"][frame_index]
        frame_time = data["snapshot_times"][frame_index]
        e1, e2, e3 = st.columns(3)
        e1.metric("Waktu snapshot", f"{frame_time:.4f} s")
        e2.metric("Temperatur minimum", f"{frame_T.min():.2f} °C")
        e3.metric("Temperatur maksimum", f"{frame_T.max():.2f} °C")
        evolution = go.Figure(go.Heatmap(
            z=frame_T, x=x, y=y, colorscale="Inferno",
            colorbar={"title": {"text": "TEMPERATUR<br>°C", "side": "right"}, "thickness": 11, "len": 0.78, "x": 1.02, "y": 0.5, "bgcolor": "rgba(20,32,45,0.28)", "outlinewidth": 0, "tickfont": {"size": 10}},
            zmin=float(data["T"].min()), zmax=float(data["T"].max()),
            hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>T=%{z:.2f} °C<extra></extra>",
        ))
        evolution.update_layout(
            title=f"Distribusi temperatur pada t = {frame_time:.4f} s",
            xaxis_title="Posisi X (m)", yaxis_title="Posisi Y (m)", height=480, margin={"l": 12, "r": 82, "t": 52, "b": 12},
        )
        st.plotly_chart(evolution, use_container_width=True)

    csv = io.StringIO()
    csv.write("y_m," + ",".join([f"x={v:.6g}_m" for v in x]) + "\n")
    for yi, row in zip(y, T):
        csv.write(f"{yi:.8g}," + ",".join(f"{v:.8g}" for v in row) + "\n")

    p = data["p"]

    st.subheader("Studi independensi mesh")
    st.caption("Membandingkan solusi steady-state pada beberapa resolusi grid dengan geometri, material, sumber panas, dan kondisi batas yang sama. Studi ini memakai grid 21, 31, 41, dan 51 titik per arah.")
    if data["mode"] == "Steady-state":
        if st.button("🔬 Jalankan studi independensi mesh", use_container_width=True):
            mesh_rows = []
            with st.spinner("Menjalankan empat simulasi steady-state..."):
                for mesh_n in (21, 31, 41, 51):
                    mesh_result = solve_steady_state(
                        mesh_n, mesh_n, p["lx"], p["ly"], p["k"], p["q"],
                        p["boundary"], p["initial"]
                    )
                    mesh_T = mesh_result["temperature"]
                    _, _, mesh_qmag = calculate_heat_flux(mesh_T, p["k"], p["lx"], p["ly"])
                    mesh_rows.append({
                        "Grid": f"{mesh_n} × {mesh_n}",
                        "T pusat (°C)": float(mesh_T[mesh_n//2, mesh_n//2]),
                        "Fluks maksimum (W/m²)": float(mesh_qmag.max()),
                        "Iterasi": int(mesh_result["iterations"]),
                        "Konvergen": "Ya" if mesh_result["converged"] else "Tidak",
                    })
            reference_center = mesh_rows[-1]["T pusat (°C)"]
            reference_flux = mesh_rows[-1]["Fluks maksimum (W/m²)"]
            for row in mesh_rows:
                row["Error T pusat vs 51² (%)"] = (
                    100.0 * abs(row["T pusat (°C)"] - reference_center)
                    / max(abs(reference_center), 1e-12)
                )
                row["Error fluks vs 51² (%)"] = (
                    100.0 * abs(row["Fluks maksimum (W/m²)"] - reference_flux)
                    / max(abs(reference_flux), 1e-12)
                )
            st.session_state["mesh_study_result"] = mesh_rows
        mesh_rows = st.session_state.get("mesh_study_result")
        if mesh_rows:
            st.dataframe(mesh_rows, use_container_width=True, hide_index=True)
            st.caption("Grid 51 × 51 dipakai sebagai referensi pembanding, bukan solusi eksak. Error dihitung relatif terhadap hasil grid tersebut.")
            center_chart = go.Figure(go.Scatter(
                x=[21, 31, 41, 51],
                y=[row["T pusat (°C)"] for row in mesh_rows],
                mode="lines+markers",
                name="Temperatur pusat",
            ))
            center_chart.update_layout(
                title="Konvergensi temperatur pusat terhadap resolusi mesh",
                xaxis_title="Jumlah titik per arah",
                yaxis_title="Temperatur pusat (°C)",
                height=350,
            )
            st.plotly_chart(center_chart, use_container_width=True)
            if all(row["Konvergen"] == "Ya" for row in mesh_rows):
                st.info("Semua solusi pada studi mesh memenuhi kriteria konvergensi solver. Periksa juga perubahan nilai antar-grid sebelum menyimpulkan independensi mesh.")
            else:
                st.warning("Setidaknya satu grid belum konvergen. Hasil studi mesh belum layak dijadikan dasar kesimpulan.")
    else:
        st.info("Studi independensi mesh saat ini tersedia untuk mode Steady-state. Jalankan simulasi steady-state untuk mengaktifkannya.")

    if data.get("residual") is not None:
        residual_report = "- Residual maksimum absolut: " + format(data["residual"]["residual_max_abs"], ".5e") + " K/m²\n- Residual RMS: " + format(data["residual"]["residual_rms"], ".5e") + " K/m²"
    else:
        residual_report = "- Tidak berlaku untuk mode transient."

    report = f"""# Laporan Simulasi — Physics AI Studio

## 1. Ringkasan
- Mode: {data['mode']}
- Status numerik: {data['info']}
- Catatan: {data['extra']}

## 2. Geometri dan mesh
- Domain: {p['lx']} × {p['ly']} m
- Grid: {p['nx']} × {p['ny']}

## 3. Sifat material
- Material: {p['material_name']}
- Konduktivitas: {p['k']} W/(m·K)
- Massa jenis: {p['rho']} kg/m³
- Kalor jenis: {p['cp']} J/(kg·K)
- Difusivitas termal: {p['k']/(p['rho']*p['cp']):.5e} m²/s
- Pembangkitan panas: {p['q']} W/m³
- Temperatur awal: {p['initial']} °C

## 4. Kondisi batas
{p['boundary']}

## 5. Metode numerik
Konduksi panas 2D dengan metode beda hingga. Steady-state menggunakan iterasi Jacobi, sedangkan transient menggunakan skema eksplisit.

## 6. Hasil numerik
- Minimum: {T.min():.4f} °C
- Maksimum: {T.max():.4f} °C
- Rata-rata: {T.mean():.4f} °C

## 7. Diagnostik residual steady-state
{residual_report}

## 8. Analisis fluks panas
- Fluks maksimum: {qmag.max():.5g} W/m²
- Fluks rata-rata: {qmag.mean():.5g} W/m²
- Fluks minimum: {qmag.min():.5g} W/m²

## 9. Batasan model
Material homogen dan isotropik dengan sifat konstan; temperatur sisi tetap. Konveksi, radiasi, dan validasi eksperimen belum dimodelkan.
"""
    try:
        pdf_bytes = build_heat_transfer_pdf(data)
        st.download_button("⬇ Unduh laporan ilmiah (PDF)", pdf_bytes,
            "physics_ai_studio_heat_transfer_report.pdf", "application/pdf",
            use_container_width=True, type="primary")
    except Exception as exc:
        st.error(f"PDF belum dapat dibuat: {exc}")

    flux_csv = io.StringIO()
    flux_csv.write("x_m,y_m,qx_W_m2,qy_W_m2,q_magnitude_W_m2\n")
    for iy, yi in enumerate(y):
        for ix, xi in enumerate(x):
            flux_csv.write(
                f"{xi:.8g},{yi:.8g},{qx[iy,ix]:.8g},{qy[iy,ix]:.8g},{qmag[iy,ix]:.8g}\n"
            )

    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇ Data temperatur (CSV)", csv.getvalue().encode(),
        "physics_ai_studio_temperature.csv", "text/csv", use_container_width=True)
    d2.download_button("⬇ Data fluks panas (CSV)", flux_csv.getvalue().encode(),
        "physics_ai_studio_heat_flux.csv", "text/csv", use_container_width=True)
    d3.download_button("⬇ Laporan (Markdown)", report.encode(),
        "laporan_physics_ai_studio.md", "text/markdown", use_container_width=True)

st.divider()
st.caption("Physics AI Studio · MVP 1.9 | 3D Heat Transfer, post-processing, heat-flux vectors, dan energy balance. Solver edukatif; periksa asumsi dan konvergensi sebelum memakai hasil untuk keputusan rekayasa.")
