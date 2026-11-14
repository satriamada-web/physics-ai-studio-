# Physics AI Studio — MVP 0.4

Aplikasi web simulasi konduksi panas 2D, dapat diakses melalui browser Android.
Tidak membutuhkan COMSOL, Claude Code, atau komputer pribadi. Kode berada di GitHub,
sedangkan perhitungan dijalankan pada server cloud Streamlit.

## Fitur
- Konduksi panas 2D pada pelat persegi panjang.
- Steady-state dengan iterasi Jacobi.
- Transient dengan skema beda hingga eksplisit.
- Pengaturan geometri, grid, material, temperatur awal, kondisi batas, dan sumber panas.
- Peta temperatur 2D dan grafik profil suhu.
- Kontrol waktu akhir transient agar simulasi berhenti tepat pada durasi target.
- Hingga 9 snapshot untuk melihat evolusi distribusi temperatur dari awal hingga akhir.
- Ekspor hasil temperatur ke CSV, laporan ke Markdown, dan laporan ilmiah PDF (A4) dengan ringkasan parameter, kondisi batas, grafik distribusi temperatur, profil suhu, hasil numerik, serta batasan model.

## Batasan ilmiah
Material diasumsikan homogen, isotropik, dan sifatnya konstan. Keempat sisi memakai
temperatur tetap (Dirichlet). Belum ada konveksi, radiasi, kontak termal, perubahan fase,
material berlapis, atau geometri kompleks. Validasi eksperimen belum dilakukan.

## Struktur repository
```text
physics-ai-studio/
├── app.py
├── physics/
│   ├── __init__.py
│   └── heat_transfer.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Deploy dari HP Android
1. Unduh ZIP ini dan ekstrak dengan aplikasi pengelola berkas.
2. Buka https://github.com melalui Chrome dan masuk.
3. Buat repository baru bernama `physics-ai-studio`.
4. Unggah `app.py`, `requirements.txt`, `README.md`, `.gitignore`, serta folder `physics`
   yang berisi `__init__.py` dan `heat_transfer.py`. Semua harus berada di root repository.
5. Buka https://share.streamlit.io dan masuk menggunakan GitHub.
6. Pilih **Create app**, repository `physics-ai-studio`, branch `main`, file utama `app.py`.
7. Tekan **Deploy** dan tunggu instalasi selesai.
8. Buka URL aplikasi yang diberikan Streamlit.

## Uji pertama
- Mode: Steady-state
- Grid: 41 × 41
- Panjang X dan Y: 0.10 m
- k: 45 W/(m·K), rho: 7800 kg/m³, cp: 500 J/(kg·K)
- Temperatur kiri: 100 °C; kanan, atas, bawah: 25 °C
- Pembangkitan panas: 0 W/m³

Tekan **Jalankan simulasi**. Periksa peta temperatur, lalu coba unduh CSV dan laporan.

## Catatan
Streamlit Community Cloud cocok untuk MVP dan grid kecil-menengah. Layanan gratis memiliki
batas sumber daya dan aplikasi dapat tidur saat tidak digunakan. Ini bukan infrastruktur
produksi untuk CFD/FEM besar atau simulasi 3D berat.
