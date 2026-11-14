# Physics AI Studio — MVP 1.5

Aplikasi web simulasi konduksi panas 2D, dapat diakses melalui browser Android.
Tidak membutuhkan COMSOL, Claude Code, atau komputer pribadi. Kode berada di GitHub,
sedangkan perhitungan dijalankan pada server cloud Streamlit.

## Geometry Builder 3D — MVP 1.4

Antarmuka Streamlit menyediakan preview interaktif untuk tiga geometri primitif:
- Kubus dengan panjang sisi yang dapat diatur.
- Balok dengan panjang X, lebar Y, dan tinggi Z.
- Silinder dengan radius, tinggi, dan resolusi permukaan yang dapat diatur.

Geometri ditampilkan sebagai triangular surface mesh menggunakan Plotly 3D dan dapat
diputar/diperbesar melalui kontrol kamera. Pengguna juga dapat mengekspor permukaan
segitiga ke format OBJ. Modul pembangkit geometri berada pada `physics/geometry_3d.py`.

Batasan: surface mesh ini hanya untuk visualisasi dan ekspor. Ini belum menjadi mesh
volume tetrahedral/hexahedral dan belum terhubung langsung ke solver Heat Transfer 3D.
Solver 3D eksperimental saat ini memakai grid Cartesian terstruktur.

## Structured 3D Mesh Engine — MVP 1.5

Modul `physics/mesh_3d.py` membangkitkan grid Cartesian terstruktur dengan node
berjarak seragam pada arah X, Y, dan Z. Jumlah node dan panjang domain dapat diatur
secara independen pada setiap arah. Hasil mencakup vektor koordinat, dx/dy/dz,
jumlah node, jumlah cell antar-node, batas domain, dan bentuk array `(nz, ny, nx)`.

Antarmuka menampilkan preview 3D berbasis sampel node, sehingga tidak perlu
merender seluruh titik untuk grid yang besar. Batas aman bawaan adalah 200.000 node.
Grid ini cocok sebagai struktur spasial untuk metode beda hingga (FDM) dan mengikuti
konvensi array fondasi solver panas 3D.

Batasan penting: ini adalah node-centred Cartesian structured grid, bukan mesh
tetrahedral/hexahedral FEM dengan konektivitas elemen. Geometri primitif pada
Geometry Builder MVP 1.4 juga belum otomatis dipotong atau dipetakan ke grid ini.
Tahap selanjutnya adalah menghubungkan mesh dengan solver 3D dan visualisasi medan
temperatur hasil simulasi.

## Arah pengembangan multiphysics 3D

Fondasi eksperimental solver konduksi panas 3D tersedia pada `physics/heat_transfer_3d.py`.
Modul ini menggunakan finite difference pada grid Cartesian terstruktur, material homogen
isotropik dengan properti konstan, sumber panas volumetrik seragam, dan temperatur tetap
(Dirichlet) pada keenam sisi balok. Urutan array temperatur adalah (z, y, x).

Kemampuan awal:
- Steady-state 3D menggunakan iterasi Jacobi.
- Transient 3D menggunakan skema eksplisit dengan pemeriksaan batas stabilitas.
- Snapshot medan temperatur transient.
- Fluks panas 3D berdasarkan Hukum Fourier, q = -k∇T.
- Uji analitik awal pada `physics/verification_3d.py`.

Status: modul solver eksperimental dan belum dihubungkan ke antarmuka Streamlit utama.
Belum mendukung geometri CAD arbitrer, mesh tetrahedral, konveksi/radiasi, kontak termal,
atau kopling antar-fisika. Tahap berikutnya adalah verifikasi otomatis, visualisasi 3D,
kemudian pengembangan sistem geometri dan mesh.

## Fitur
- Diagnostik residual persamaan steady-state: residual maksimum absolut dan RMS dari persamaan beda hingga pada node interior.
- Pengaturan solver steady-state: toleransi konvergensi Jacobi dan batas iterasi maksimum dapat diubah, disimpan dalam preset, serta dicatat pada laporan PDF.
- Panel verifikasi numerik otomatis dengan lima kasus uji: residual steady-state, steady-state temperatur seragam, transient kondisi setimbang, dan Hukum Fourier pada medan temperatur linear.
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
- Pemantauan temperatur pada satu titik grid selama seluruh simulasi transient, dengan grafik riwayat waktu dan ekspor CSV.
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
│   ├── heat_transfer.py
│   └── transient_diagnostics.py
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


## Riwayat temperatur titik — MVP 1.3
Pada mode transient, pengguna dapat memilih indeks titik pemantauan pada arah X dan Y.
Aplikasi merekam temperatur titik tersebut pada setiap langkah waktu, lalu menampilkan
grafik temperatur terhadap waktu. Data dapat diunduh sebagai CSV dengan kolom
`time_s` dan `temperature_C`.

Pemantauan ini merekam nilai pada node grid, bukan interpolasi kontinu antar-node.
Indeks X = 0 berada di sisi kiri; indeks Y = 0 berada di sisi bawah domain.
