import io
import json
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from physics.heat_transfer import solve_steady_state, solve_transient, stable_time_step, calculate_heat_flux
from physics.reporting import build_heat_transfer_pdf
from physics.materials import MATERIALS

st.set_page_config(page_title="Physics AI Studio", page_icon="🌡️", layout="wide")
st.markdown("<style>.block-container{max-width:1200px;padding-top:2rem;}div[data-testid='stMetric']{background:rgba(128,128,128,.07);padding:12px;border-radius:10px;}</style>", unsafe_allow_html=True)
st.title("Physics AI Studio")
st.caption("MVP 0.8 · Studi independensi mesh dan analisis fluks panas")
st.write("Atur model, jalankan solver numerik, amati distribusi temperatur, lalu unduh laporan simulasi.")

DEFAULT_SETTINGS = {
    "mode": "Steady-state", "material_name": "Custom", "nx": 41, "ny": 41,
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
        }
        for key, (low, high) in ranges.items():
            if not low <= settings[key] <= high:
                raise ValueError(f"Nilai {key} di luar rentang.")
        if not isinstance(settings["nx"], int) or not isinstance(settings["ny"], int):
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

with st.sidebar:
    st.header("Pengaturan")
    h1, h2 = st.columns(2)
    h1.button("↶ Undo", use_container_width=True, disabled=not st.session_state["_settings_undo"], on_click=undo_settings)
    h2.button("↷ Redo", use_container_width=True, disabled=not st.session_state["_settings_redo"], on_click=redo_settings)
    st.button("⟲ Default Settings", use_container_width=True, on_click=reset_settings)
    st.caption("Undo/Redo menyimpan hingga 50 perubahan parameter.")
    st.divider()
    st.header("Preset konfigurasi")
    st.caption("Preset tersimpan sementara selama sesi aplikasi. Ekspor JSON agar dapat digunakan kembali di sesi lain.")
    st.text_input("Nama preset", key="preset_name_input", placeholder="Contoh: Aluminium 2D")
    st.button("💾 Simpan konfigurasi saat ini", use_container_width=True, on_click=save_preset)
    _presets = st.session_state.setdefault("_user_presets", {})
    if _presets:
        st.selectbox("Preset tersimpan", list(_presets.keys()), key="_preset_selected")
        st.button("Terapkan preset", use_container_width=True, on_click=load_preset)
        st.button("Hapus preset terpilih", use_container_width=True, on_click=delete_preset)
        _selected = st.session_state.get("_preset_selected")
        if _selected in _presets:
            st.download_button(
                "⬇ Ekspor preset JSON",
                json.dumps({"name": _selected, "settings": _presets[_selected]}, indent=2).encode("utf-8"),
                file_name=f"physics_ai_preset_{_selected.lower().replace(' ', '_')}.json",
                mime="application/json",
                use_container_width=True,
            )
    st.file_uploader("Impor preset JSON", type=["json"], key="preset_upload")
    st.button("Impor file preset", use_container_width=True, on_click=import_preset)
    if st.session_state.get("_preset_message"):
        st.caption(st.session_state["_preset_message"])
    st.divider()
    st.header("1 · Model fisika")
    mode = st.selectbox("Jenis simulasi", ["Steady-state", "Transient"], key="mode", on_change=record_settings_change)
    nx = st.slider("Jumlah grid arah X", 11, 101, step=2, key="nx", on_change=record_settings_change)
    ny = st.slider("Jumlah grid arah Y", 11, 101, step=2, key="ny", on_change=record_settings_change)
    st.header("2 · Geometri")
    lx = st.number_input("Panjang X (m)", 0.01, 2.0, step=0.01, format="%.3f", key="lx", on_change=record_settings_change)
    ly = st.number_input("Panjang Y (m)", 0.01, 2.0, step=0.01, format="%.3f", key="ly", on_change=record_settings_change)
    st.header("3 · Sifat material")
    material_name = st.selectbox(
        "Pilih material",
        list(MATERIALS.keys()),
        key="material_name",
        on_change=select_material,
    )
    material_info = MATERIALS[material_name]
    st.caption(material_info["description"])
    if material_name != "Custom":
        st.caption("Sumber data: " + material_info["reference"])
    k = st.number_input("Konduktivitas termal k (W/m·K)", 0.01, 2000.0, step=1.0, key="k", on_change=record_settings_change)
    rho = st.number_input("Massa jenis (kg/m³)", 1.0, 25000.0, step=100.0, key="rho", on_change=record_settings_change)
    cp = st.number_input("Kalor jenis cp (J/kg·K)", 1.0, 10000.0, step=10.0, key="cp", on_change=record_settings_change)
    st.header("4 · Kondisi batas")
    st.caption("Temperatur pada keempat sisi pelat dianggap tetap.")
    t_left = st.number_input("Sisi kiri (°C)", step=5.0, key="t_left", on_change=record_settings_change)
    t_right = st.number_input("Sisi kanan (°C)", step=5.0, key="t_right", on_change=record_settings_change)
    t_top = st.number_input("Sisi atas (°C)", step=5.0, key="t_top", on_change=record_settings_change)
    t_bottom = st.number_input("Sisi bawah (°C)", step=5.0, key="t_bottom", on_change=record_settings_change)
    t_initial = st.number_input("Temperatur awal (°C)", step=5.0, key="t_initial", on_change=record_settings_change)
    st.header("5 · Sumber panas")
    q_vol = st.number_input("Pembangkitan panas volumetrik (W/m³)", 0.0, 1.0e8, step=1000.0, key="q_vol", on_change=record_settings_change)
    total_time = st.number_input("Lama simulasi (detik)", 0.01, 10000.0, step=1.0, key="total_time", on_change=record_settings_change) if mode == "Transient" else None
    run = st.button("▶ Jalankan simulasi", type="primary", use_container_width=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Grid", f"{nx} × {ny}")
c2.metric("Ukuran pelat", f"{lx:.2f} × {ly:.2f} m")
c3.metric("Konduktivitas", f"{k:g} W/m·K")
c4.metric("Difusivitas termal", f"{k/(rho*cp):.3e} m²/s")

if run:
    boundary = {"left": float(t_left), "right": float(t_right), "top": float(t_top), "bottom": float(t_bottom)}
    try:
        with st.spinner("Menghitung solusi numerik..."):
            if mode == "Steady-state":
                result = solve_steady_state(nx, ny, lx, ly, k, q_vol, boundary, t_initial)
                info = f"Steady-state · {result['iterations']:,} iterasi · konvergen: {'Ya' if result['converged'] else 'Belum'}"
                extra = f"Perubahan maksimum iterasi terakhir: {result['last_delta']:.3e} °C"
            else:
                dt_limit = 0.9 * stable_time_step(k, rho, cp, lx/(nx-1), ly/(ny-1))
                steps_required = int(np.ceil(total_time / dt_limit))
                if steps_required > 20000:
                    st.error(f"Simulasi membutuhkan {steps_required:,} langkah (batas MVP 20.000). Kurangi waktu simulasi atau jumlah grid.")
                    st.stop()
                result = solve_transient(nx, ny, lx, ly, k, rho, cp, q_vol, boundary, t_initial, total_time, dt_limit)
                info = f"Transient · {result['steps']:,} langkah · waktu akhir: {result['simulated_time']:.6g} s"
                extra = f"dt aktual = {result['dt']:.3e} s · batas stabilitas = {stable_time_step(k, rho, cp, lx/(nx-1), ly/(ny-1)):.3e} s"
        st.session_state["last_result"] = {
            "T": result["temperature"], "x": np.linspace(0, lx, nx), "y": np.linspace(0, ly, ny),
            "snapshots": result.get("snapshots", []), "snapshot_times": result.get("snapshot_times", []),
            "mode": mode, "info": info, "extra": extra,
            "p": {"nx": nx, "ny": ny, "lx": lx, "ly": ly, "k": k, "rho": rho, "cp": cp, "q": q_vol,
                  "boundary": boundary, "initial": t_initial, "total_time": total_time,
                  "material_name": material_name}
        }
        st.success("Simulasi selesai. Hasil numerik berhasil dihitung.")
    except Exception as exc:
        st.error(f"Simulasi gagal: {exc}")

data = st.session_state.get("last_result")
if data is None:
    st.info("Atur parameter pada panel kiri, lalu tekan **Jalankan simulasi**.")
    st.markdown("**Asumsi MVP:** konduksi 2D, material homogen dan isotropik, tanpa konveksi/radiasi, serta temperatur sisi pelat tetap.")
else:
    T, x, y = data["T"], data["x"], data["y"]
    qx, qy, qmag = calculate_heat_flux(T, data["p"]["k"], data["p"]["lx"], data["p"]["ly"])
    st.divider()
    st.subheader("Hasil simulasi")
    st.caption(data["info"])
    st.caption(data["extra"])
    a, b, c = st.columns(3)
    a.metric("Temperatur minimum", f"{T.min():.2f} °C")
    b.metric("Temperatur maksimum", f"{T.max():.2f} °C")
    c.metric("Temperatur rata-rata", f"{T.mean():.2f} °C")
    col1, col2 = st.columns([1.35, 1])
    with col1:
        fig = go.Figure(go.Heatmap(z=T, x=x, y=y, colorscale="Inferno", colorbar={"title": "°C"},
            hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>T=%{z:.2f} °C<extra></extra>"))
        fig.update_layout(title="Distribusi temperatur 2D", xaxis_title="Posisi X (m)", yaxis_title="Posisi Y (m)", height=500)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        mid = len(y)//2
        line = go.Figure(go.Scatter(x=x, y=T[mid, :], mode="lines+markers", name="Profil temperatur"))
        line.update_layout(title=f"Profil suhu pada y = {y[mid]:.4f} m", xaxis_title="Posisi X (m)", yaxis_title="Temperatur (°C)", height=350)
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
        colorbar={"title": "W/m²"},
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
        height=520, annotations=arrow_annotations,
    )
    st.plotly_chart(heat_flux_fig, use_container_width=True)
    st.caption("Komponen fluks: qx = −k·∂T/∂x dan qy = −k·∂T/∂y. Estimasi gradien memakai beda hingga numerik.")

    if data["mode"] == "Transient" and data.get("snapshots"):
        st.subheader("Evolusi temperatur terhadap waktu")
        st.caption("Geser indeks waktu untuk melihat bagaimana panas menyebar dari kondisi awal hingga akhir.")
        frame_index = st.slider(
            "Waktu simulasi (snapshot)",
            min_value=0,
            max_value=len(data["snapshots"]) - 1,
            value=0,
            format="%d",
            key="transient_snapshot_index",
        )
        frame_T = data["snapshots"][frame_index]
        frame_time = data["snapshot_times"][frame_index]
        e1, e2, e3 = st.columns(3)
        e1.metric("Waktu snapshot", f"{frame_time:.4f} s")
        e2.metric("Temperatur minimum", f"{frame_T.min():.2f} °C")
        e3.metric("Temperatur maksimum", f"{frame_T.max():.2f} °C")
        evolution = go.Figure(go.Heatmap(
            z=frame_T, x=x, y=y, colorscale="Inferno",
            colorbar={"title": "°C"},
            zmin=float(data["T"].min()), zmax=float(data["T"].max()),
            hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>T=%{z:.2f} °C<extra></extra>",
        ))
        evolution.update_layout(
            title=f"Distribusi temperatur pada t = {frame_time:.4f} s",
            xaxis_title="Posisi X (m)", yaxis_title="Posisi Y (m)", height=480,
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

## 7. Analisis fluks panas
- Fluks maksimum: {qmag.max():.5g} W/m²
- Fluks rata-rata: {qmag.mean():.5g} W/m²
- Fluks minimum: {qmag.min():.5g} W/m²

## 8. Batasan model
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
st.caption("Physics AI Studio · MVP 0.8 | Solver edukatif. Periksa asumsi dan konvergensi sebelum memakai hasil untuk keputusan rekayasa.")
