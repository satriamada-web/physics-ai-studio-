import io
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from physics.heat_transfer import solve_steady_state, solve_transient, stable_time_step

st.set_page_config(page_title="Physics AI Studio", page_icon="🌡️", layout="wide")
st.markdown("<style>.block-container{max-width:1200px;padding-top:2rem;}div[data-testid='stMetric']{background:rgba(128,128,128,.07);padding:12px;border-radius:10px;}</style>", unsafe_allow_html=True)
st.title("Physics AI Studio")
st.caption("MVP 0.1 · Simulasi konduksi panas 2D")
st.write("Atur model, jalankan solver numerik, lalu amati distribusi temperatur dan profil suhu pada pelat.")

with st.sidebar:
    st.header("1 · Model fisika")
    mode = st.selectbox("Jenis simulasi", ["Steady-state", "Transient"])
    nx = st.slider("Jumlah grid arah X", 11, 101, 41, 2)
    ny = st.slider("Jumlah grid arah Y", 11, 101, 41, 2)
    st.header("2 · Geometri")
    lx = st.number_input("Panjang X (m)", 0.01, 2.0, 0.10, 0.01, format="%.3f")
    ly = st.number_input("Panjang Y (m)", 0.01, 2.0, 0.10, 0.01, format="%.3f")
    st.header("3 · Sifat material")
    k = st.number_input("Konduktivitas termal k (W/m·K)", 0.01, 2000.0, 45.0, 1.0)
    rho = st.number_input("Massa jenis ρ (kg/m³)", 1.0, 25000.0, 7800.0, 100.0)
    cp = st.number_input("Kalor jenis cp (J/kg·K)", 1.0, 10000.0, 500.0, 10.0)
    st.header("4 · Kondisi batas")
    st.caption("Temperatur pada keempat sisi pelat dianggap tetap.")
    t_left = st.number_input("Sisi kiri (°C)", value=100.0, step=5.0)
    t_right = st.number_input("Sisi kanan (°C)", value=25.0, step=5.0)
    t_top = st.number_input("Sisi atas (°C)", value=25.0, step=5.0)
    t_bottom = st.number_input("Sisi bawah (°C)", value=25.0, step=5.0)
    t_initial = st.number_input("Temperatur awal (°C)", value=25.0, step=5.0)
    st.header("5 · Sumber panas")
    q_vol = st.number_input("Pembangkitan panas volumetrik (W/m³)", 0.0, 1.0e8, 0.0, 1000.0)
    total_time = st.number_input("Lama simulasi (detik)", 0.01, 10000.0, 10.0, 1.0) if mode == "Transient" else None
    run = st.button("▶ Jalankan simulasi", type="primary", use_container_width=True)

c1,c2,c3,c4 = st.columns(4)
c1.metric("Grid", f"{nx} × {ny}")
c2.metric("Ukuran pelat", f"{lx:.2f} × {ly:.2f} m")
c3.metric("Konduktivitas", f"{k:g} W/m·K")
c4.metric("Difusivitas termal", f"{k/(rho*cp):.3e} m²/s")

if run:
    boundary = {"left":float(t_left),"right":float(t_right),"top":float(t_top),"bottom":float(t_bottom)}
    try:
        with st.spinner("Menghitung solusi numerik..."):
            if mode == "Steady-state":
                result = solve_steady_state(nx,ny,lx,ly,k,q_vol,boundary,t_initial)
                info = f"Steady-state · {result['iterations']:,} iterasi · konvergen: {'Ya' if result['converged'] else 'Belum'}"
                extra = f"Perubahan maksimum iterasi terakhir: {result['last_delta']:.3e} °C"
            else:
                dt = 0.9 * stable_time_step(k,rho,cp,lx/(nx-1),ly/(ny-1))
                steps = int(np.ceil(total_time/dt))
                if steps > 20000:
                    st.error(f"Simulasi membutuhkan {steps:,} langkah (batas MVP 20.000). Kurangi waktu simulasi atau jumlah grid.")
                    st.stop()
                result = solve_transient(nx,ny,lx,ly,k,rho,cp,q_vol,boundary,t_initial,total_time,dt)
                info = f"Transient · {result['steps']:,} langkah · waktu akhir: {result['simulated_time']:.4g} s"
                extra = f"Δt = {result['dt']:.3e} s (memenuhi batas stabilitas eksplisit)"
        st.session_state["last_result"] = {
            "T":result["temperature"],"x":np.linspace(0,lx,nx),"y":np.linspace(0,ly,ny),
            "mode":mode,"info":info,"extra":extra,
            "p":{"nx":nx,"ny":ny,"lx":lx,"ly":ly,"k":k,"rho":rho,"cp":cp,"q":q_vol,
                 "boundary":boundary,"initial":t_initial}
        }
        st.success("Simulasi selesai. Hasil numerik berhasil dihitung.")
    except Exception as exc:
        st.error(f"Simulasi gagal: {exc}")

data = st.session_state.get("last_result")
if data is None:
    st.info("Atur parameter pada panel kiri, lalu tekan **Jalankan simulasi**.")
    st.markdown("**Asumsi MVP:** konduksi 2D, material homogen dan isotropik, tanpa konveksi/radiasi, serta temperatur sisi pelat tetap.")
else:
    T,x,y = data["T"],data["x"],data["y"]
    st.divider()
    st.subheader("Hasil simulasi")
    st.caption(data["info"])
    st.caption(data["extra"])
    a,b,c = st.columns(3)
    a.metric("Temperatur minimum",f"{T.min():.2f} °C")
    b.metric("Temperatur maksimum",f"{T.max():.2f} °C")
    c.metric("Temperatur rata-rata",f"{T.mean():.2f} °C")
    col1,col2 = st.columns([1.35,1])
    with col1:
        fig = go.Figure(go.Heatmap(z=T,x=x,y=y,colorscale="Inferno",colorbar={"title":"°C"},
            hovertemplate="x=%{x:.4f} m<br>y=%{y:.4f} m<br>T=%{z:.2f} °C<extra></extra>"))
        fig.update_layout(title="Distribusi temperatur 2D",xaxis_title="Posisi X (m)",yaxis_title="Posisi Y (m)",height=500)
        st.plotly_chart(fig,use_container_width=True)
    with col2:
        mid = len(y)//2
        line = go.Figure(go.Scatter(x=x,y=T[mid,:],mode="lines+markers",name="Profil temperatur"))
        line.update_layout(title=f"Profil suhu pada y = {y[mid]:.4f} m",xaxis_title="Posisi X (m)",yaxis_title="Temperatur (°C)",height=350)
        st.plotly_chart(line,use_container_width=True)
        st.caption("Profil temperatur sepanjang garis tengah pelat.")

    csv = io.StringIO()
    csv.write("y_m," + ",".join([f"x={v:.6g}_m" for v in x]) + "\n")
    for yi,row in zip(y,T):
        csv.write(f"{yi:.8g}," + ",".join(f"{v:.8g}" for v in row) + "\n")
    p=data["p"]
    report=f"""# Laporan Simulasi — Physics AI Studio

## Ringkasan
- Mode: {data['mode']}
- Status numerik: {data['info']}
- Catatan: {data['extra']}

## Parameter
- Domain: {p['lx']} × {p['ly']} m
- Grid: {p['nx']} × {p['ny']}
- Konduktivitas: {p['k']} W/(m·K)
- Massa jenis: {p['rho']} kg/m³
- Kalor jenis: {p['cp']} J/(kg·K)
- Pembangkitan panas: {p['q']} W/m³
- Temperatur awal: {p['initial']} °C
- Kondisi batas: {p['boundary']}

## Hasil
- Minimum: {T.min():.4f} °C
- Maksimum: {T.max():.4f} °C
- Rata-rata: {T.mean():.4f} °C

## Metode dan batasan
Model konduksi panas dua dimensi pada material homogen dan isotropik.
Keempat sisi menggunakan kondisi batas temperatur tetap (Dirichlet).
Konveksi, radiasi, perubahan sifat material terhadap temperatur, dan deformasi
belum dimodelkan. Hasil adalah keluaran simulasi numerik, bukan pengukuran eksperimen.
Validasi terhadap solusi analitik atau eksperimen belum dilakukan.
"""
    d1,d2=st.columns(2)
    d1.download_button("⬇ Unduh data temperatur (CSV)",csv.getvalue().encode(), "physics_ai_studio_temperature.csv","text/csv",use_container_width=True)
    d2.download_button("⬇ Unduh laporan (Markdown)",report.encode(),"laporan_physics_ai_studio.md","text/markdown",use_container_width=True)

st.divider()
st.caption("Physics AI Studio · MVP 0.1 | Solver numerik edukatif. Periksa asumsi dan konvergensi sebelum memakai hasil untuk keputusan rekayasa.")
