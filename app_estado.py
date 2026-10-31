import os

import streamlit as st

CARPETA_DESTINO = "temp_destino"
ARCHIVO_FOLIO = "folio_historico.txt"
OPERADOR_DEFAULT = "Javier Arturo Garcia"
OPCIONES_PROD = ["REGULAR (MAGNA)", "DIÉSEL", "PREMIUM"]
OPCIONES_TQ = ["T1: MAGNA", "T2: DIÉSEL", "T3: PREMIUM"]


def obtener_folio():
    if os.path.exists(ARCHIVO_FOLIO):
        with open(ARCHIVO_FOLIO, "r") as f:
            try:
                val = int(f.read().strip())
                return val if val > 0 else 1
            except Exception:
                return 1
    return 1


def guardar_folio(nuevo_folio):
    with open(ARCHIVO_FOLIO, "w") as f:
        f.write(str(nuevo_folio))


def iniciar_estado():
    os.makedirs(CARPETA_DESTINO, exist_ok=True)
    defaults = {
        "folio_actual": obtener_folio(),
        "d_factura": "",
        "d_uuid": "",
        "d_producto": "REGULAR (MAGNA)",
        "d_tanque_vr": "T1: MAGNA",
        "d_litros_fac": 0.0,
        "d_litros_desc": 0.0,
        "d_fecha": "",
        "d_hora_ini": "",
        "d_hora_fin": "",
        "d_embarque": "S/D",
        "d_tanque_at": "S/D",
        "d_operador": OPERADOR_DEFAULT,
        "ultimo_archivo_fac": "",
        "ultimo_hash_tira": "",
        "ocr_confianza": "",
        "ocr_alertas": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
