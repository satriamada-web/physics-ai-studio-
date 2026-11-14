# Physics AI Studio — MVP 1.2

Aplikasi web simulasi konduksi panas 2D, dapat diakses melalui browser Android.
Tidak membutuhkan COMSOL, Claude Code, atau komputer pribadi. Kode berada di GitHub,
sedangkan perhitungan dijalankan pada server cloud Streamlit.

## Fitur
- Diagnostik residual persamaan steady-state: residual maksimum absolut dan RMS dari persamaan beda hingga pada node interior.
- Pengaturan solver steady-state: toleransi konvergensi Jacobi dan batas iterasi maksimum dapat diubah, disimpan dalam preset, serta dicatat pada laporan PDF.
- Panel verifikasi numerik otomatis dengan empat kasus uji: residual steady-state, steady-state temperatur seragam, transient kondisi setimbang, dan Hukum Fourier pada medan temperatur linear.
- Konduksi panas 2D pada pelat persegi panjang.
- Steady-state dengan iterasi Jacobi.
- Transient dengan skema beda hingga eksplisit.
- Database material representatif: baja karbon AISI 1018, aluminium 6061-T6, tembaga OFE C10100, dan stainless steel 304; pilihan Custom tetap tersedia.
- Pemilihan material otomatis mengisi konduktivitas termal, massa jenis, dan kalor jenis; nilai tetap dapat disunting manual.
- Pengaturan geometri, grid, temperatur awal, kondisi batas, dan sumber panas.
- Peta temperatur 2D dan grafik profil suhu.
- Studi independensi mesh steady-state pada grid 21×21, 31×31, 41×41, dan 51×51; membandingkan temperatur pusat serta fluks maksimum terhadap grid referensi 51×51.
- Analisis fluks panas berdasarkan Hukum Fourier (q = −k∇T), dengan peta magnitudo dan panah arah aliran.
- Ringkasan fluks panas maksimum, rata-rata, dan minimum; ekspor data fluks sebagai CSV serta ringkasan pada laporan Markdown/PDF.
- Diagnostik stabilitas transient: difusivitas termal, bilangan Fourier arah X/Y, jumlah bilangan Fourier, batas dt kritis, dan rasio langkah waktu terhadap batas stabilitas; hasil ikut dicatat pada PDF.
- Kontrol waktu akhir transient agar simulasi berhenti tepat pada durasi target.
- Hingga 9 snapshot untuk melihat evolusi distribusi temperatur dari awal hingga akhir.
- Pengaturan Default Settings serta Undo/Redo parameter (maksimal 50 langkah).
- Simpan, terapkan, hapus, ekspor, dan impor preset konfigurasi JSON. Preset aktif disimpan selama sesi; ekspor JSON untuk penggunaan ulang.
- Ekspor hasil temperatur ke CSV, laporan ke Markdown, dan laporan ilmiah PDF (A4) dengan ringkasan parameter, kondisi batas, grafik distribusi temperatur, profil suhu, hasil numerik, serta batasan model.

## Analisis fluks panas MVP 0.7
Fluks panas lokal dihitung dari gradien temperatur numerik menggunakan `numpy.gradient`:
- qx = −k ∂T/∂x
- qy = −k ∂T/∂y
- |q| = √(qx² + qy²)

Satuan fluks panas adalah W/m². Besaran ini adalah densitas laju perpindahan panas lokal, bukan laju panas total (W). Estimasi gradien bergantung pada resolusi mesh dan kualitas solusi temperatur.

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


## Database material MVP 0.6
Nilai bawaan adalah nilai representatif, terutama di sekitar temperatur ruang, dan
bukan pengganti datasheet lot atau paduan yang sebenarnya. Sifat material dapat
berubah menurut komposisi, temper, proses manufaktur, dan temperatur. Untuk desain
rekayasa, gunakan data material spesifik dan lakukan verifikasi independen.

Referensi data:
- Baja karbon AISI 1018: EngiRef, https://engiref.app/materials/
- Aluminium 6061-T6: MatWeb, https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=MA6061T6
- Tembaga OFE C10100: KME, https://www.kme.com/fileadmin/DOWNLOADCENTER/COPPER%20DIVISON/4_Industrial_Rolled/3_Datasheets/07_2023_C10100_Cu-OFE_e.pdf
- Stainless steel 304: ASSDA, https://www.assda.asn.au/stainless-steel/properties-and-performance


## Studi independensi mesh MVP 0.8
Studi membandingkan empat resolusi grid pada domain dan parameter fisik yang sama.
Temperatur pusat dan fluks maksimum dibandingkan terhadap grid 51 × 51 sebagai
referensi numerik terhalus dalam studi. Grid referensi bukan solusi eksak.
Semua simulasi harus mencapai kriteria konvergensi solver; perbedaan antar-grid
tetap perlu dinilai sebelum menyatakan hasil independen terhadap mesh.


## Verifikasi numerik MVP 0.9
Panel verifikasi menjalankan tiga kasus dengan jawaban analitik yang diketahui:
1. Steady-state: temperatur 50 °C seragam pada seluruh domain harus tetap seragam.
2. Transient: kondisi awal dan seluruh batas 50 °C tanpa sumber panas harus tetap setimbang.
3. Hukum Fourier: medan temperatur linear harus menghasilkan komponen fluks konstan yang sesuai dengan q = −k∇T.

Toleransi pemeriksaan adalah 1×10⁻⁸ untuk kasus uji tersebut. Lulus pada kasus uji
ini hanya menunjukkan konsistensi pada kasus sederhana yang diuji; hal itu bukan
validasi eksperimen dan tidak membuktikan akurasi untuk semua geometri atau kondisi.


## Kontrol solver MVP 1.2

Pengguna dapat mengatur toleransi perubahan maksimum temperatur antar iterasi Jacobi
(default 1×10⁻⁶ °C; rentang 1×10⁻¹⁰ hingga 1×10⁻² °C) dan jumlah iterasi maksimum
(default 30.000; rentang 1.000 hingga 100.000). Jika batas iterasi tercapai sebelum
toleransi dipenuhi, hasil ditandai belum konvergen. Toleransi iterasi adalah kriteria
berhenti solver, sedangkan residual persamaan adalah diagnostik terpisah; keduanya
tidak boleh dianggap sebagai validasi eksperimen.

## Diagnostik residual MVP 1.0
Untuk mode steady-state, aplikasi menghitung residual diskret pada node interior:

R = d²T/dx² + d²T/dy² + q'''/k

Aplikasi menampilkan residual maksimum absolut dan residual RMS dalam K/m².
Residual menunjukkan konsistensi solusi terhadap persamaan beda hingga pada mesh
yang digunakan. Nilai residual bukan error eksperimen, bukan jaminan independensi
mesh, dan tidak boleh dibandingkan antar-mesh tanpa mempertimbangkan skala serta
ukuran grid. Diagnostik ini tidak ditampilkan untuk mode transient.
