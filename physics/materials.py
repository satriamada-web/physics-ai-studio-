"""Database material representatif untuk simulasi konduksi panas.

Nilai bersifat pendekatan pada temperatur sekitar ruang (umumnya ~20-25 °C).
Gunakan datasheet material aktual untuk analisis desain atau keselamatan.
"""

MATERIALS = {
    "Custom": {
        "description": "Masukkan sifat material secara manual.",
        "k": 45.0, "rho": 7800.0, "cp": 500.0,
        "reference": "Nilai manual pengguna.",
    },
    "Baja karbon AISI 1018": {
        "description": "Baja karbon rendah; nilai tipikal.",
        "k": 51.9, "rho": 7870.0, "cp": 486.0,
        "reference": "EngiRef — AISI 1018 Carbon Steel.",
    },
    "Aluminium 6061-T6": {
        "description": "Paduan aluminium 6061-T6; nilai tipikal.",
        "k": 167.0, "rho": 2700.0, "cp": 896.0,
        "reference": "MatWeb — Aluminum 6061-T6.",
    },
    "Tembaga OFE C10100": {
        "description": "Tembaga oxygen-free high-conductivity; kondisi annealed.",
        "k": 394.0, "rho": 8930.0, "cp": 390.0,
        "reference": "KME — Cu-OFE C10100, typical values at 20 °C.",
    },
    "Stainless steel 304": {
        "description": "Stainless steel austenitik 304; nilai tipikal.",
        "k": 16.2, "rho": 8000.0, "cp": 500.0,
        "reference": "ASSDA — Typical physical properties, grade 304.",
    },
}
