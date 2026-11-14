"""Preset properti material representatif untuk Physics AI Studio.

Properti tipikal sekitar 20-25 °C. Nilai bergantung pada grade, temper,
temperatur, tekanan, dan kondisi proses; verifikasi datasheet untuk desain.
k: W/(m K), rho: kg/m3, cp: J/(kg K), E: Pa,
mu: Pa s (viskositas dinamis), nu: rasio Poisson, alpha: 1/K.
"""
MATERIALS = {
    "Custom": {
        "description": "Material khusus; masukkan properti sesuai datasheet.",
        "k": 45.0, "rho": 7800.0, "cp": 500.0,
        "E": 2.0e11, "mu": 0.0, "nu": 0.30, "alpha": 1.2e-5,
        "reference": "Input pengguna.",
    },
    "Baja karbon AISI 1018": {
        "description": "Baja karbon rendah, nilai tipikal.",
        "k": 51.9, "rho": 7870.0, "cp": 486.0,
        "E": 2.05e11, "mu": 0.0, "nu": 0.29, "alpha": 11.5e-6,
        "reference": "EngiRef / data tipikal AISI 1018.",
    },
    "Aluminium 6061-T6": {
        "description": "Paduan aluminium 6061-T6.",
        "k": 167.0, "rho": 2700.0, "cp": 896.0,
        "E": 6.89e10, "mu": 0.0, "nu": 0.33, "alpha": 23.6e-6,
        "reference": "MatWeb / datasheet 6061-T6.",
    },
    "Tembaga OFE C10100": {
        "description": "Tembaga oxygen-free high-conductivity.",
        "k": 394.0, "rho": 8930.0, "cp": 390.0,
        "E": 1.17e11, "mu": 0.0, "nu": 0.34, "alpha": 16.5e-6,
        "reference": "KME / data tipikal Cu-OFE pada 20 °C.",
    },
    "Stainless steel 304": {
        "description": "Baja tahan karat austenitik grade 304.",
        "k": 16.2, "rho": 8000.0, "cp": 500.0,
        "E": 1.93e11, "mu": 0.0, "nu": 0.29, "alpha": 17.2e-6,
        "reference": "ASSDA / properti tipikal grade 304.",
    },
    "Air (Water)": {
        "description": "Air cair sekitar 20 °C, tekanan atmosfer.",
        "k": 0.598, "rho": 998.2, "cp": 4182.0,
        "E": 2.2e9, "mu": 1.002e-3, "nu": 0.499, "alpha": 2.1e-4,
        "reference": "IAPWS / properti air sekitar 20 °C.",
    },
    "Udara (Air)": {
        "description": "Udara kering sekitar 20 °C, tekanan atmosfer.",
        "k": 0.0257, "rho": 1.204, "cp": 1005.0,
        "E": 1.42e5, "mu": 1.81e-5, "nu": 0.499, "alpha": 3.4e-3,
        "reference": "NIST / properti udara sekitar 20 °C.",
    },
    "Kaca soda-kapur": {
        "description": "Kaca soda-lime umum.",
        "k": 1.0, "rho": 2500.0, "cp": 840.0,
        "E": 7.0e10, "mu": 0.0, "nu": 0.22, "alpha": 9.0e-6,
        "reference": "Data tipikal kaca soda-kapur.",
    },
    "Beton normal": {
        "description": "Beton normal; properti sangat bergantung komposisi dan kadar air.",
        "k": 1.7, "rho": 2300.0, "cp": 880.0,
        "E": 2.5e10, "mu": 0.0, "nu": 0.20, "alpha": 10.0e-6,
        "reference": "Data tipikal beton normal.",
    },
}
