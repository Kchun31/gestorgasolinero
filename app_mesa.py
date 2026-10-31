import re
from datetime import datetime

import streamlit as st

from app_estado import OPCIONES_PROD, OPCIONES_TQ

CLAVE_PROD = {"REGULAR (MAGNA)": "MAGNA", "DIÉSEL": "DIÉSEL", "PREMIUM": "PREMIUM"}


def _indice(opciones, valor):
    return opciones.index(valor) if valor in opciones else 0


def render_mesa():
    s = st.session_state
    folio_input = st.number_input(
        "📌 Número de Folio Consecutivo", min_value=1, value=s.folio_actual, step=1
    )
    st.markdown("### 🛠️ Mesa de Control y Validación (NOM-005-ASEA-2016)")
    c1, c2, c3 = st.columns(3)
    with c1:
        s.d_factura = st.text_input("Folio Factura", value=s.d_factura)
        s.d_litros_fac = st.number_input("Litros Facturados (L)", value=float(s.d_litros_fac), step=100.0, format="%.2f")
        s.d_fecha = st.text_input("Fecha Descarga (DD/MM/AAAA)", value=s.d_fecha)
    with c2:
        s.d_uuid = st.text_input("Folio Fiscal (UUID)", value=s.d_uuid)
        s.d_litros_desc = st.number_input("Aumento Bruto Veeder-Root (L)", value=float(s.d_litros_desc), step=100.0, format="%.2f")
        s.d_hora_ini = st.text_input("Hora Inicio (HH:MM)", value=s.d_hora_ini)
    with c3:
        s.d_producto = st.selectbox("Producto", OPCIONES_PROD, index=_indice(OPCIONES_PROD, s.d_producto))
        s.d_tanque_vr = st.selectbox("Tanque Veeder-Root", OPCIONES_TQ, index=_indice(OPCIONES_TQ, s.d_tanque_vr))
        s.d_hora_fin = st.text_input("Hora Término (HH:MM)", value=s.d_hora_fin)

    c4, c5, c6 = st.columns(3)
    with c4:
        s.d_embarque = st.text_input("Embarque", value=s.d_embarque)
    with c5:
        s.d_tanque_at = st.text_input("Tanque Autotanque", value=s.d_tanque_at)
    with c6:
        s.d_operador = st.text_input("Operador", value=s.d_operador)

    if CLAVE_PROD.get(s.d_producto, "") not in s.d_tanque_vr:
        st.warning(f"⚠️ El producto ({s.d_producto}) no coincide con el tanque ({s.d_tanque_vr}). Verifica.")

    dif_litros = abs(s.d_litros_fac - s.d_litros_desc)
    pct_merma = (dif_litros / s.d_litros_fac * 100.0) if s.d_litros_fac > 0 else 0.0
    if s.d_litros_fac > 0 and s.d_litros_desc > 0:
        if pct_merma <= 0.55:
            st.success(f"🟢 SEMÁFORO NORMATIVO EN RANGO | Desviación: {dif_litros:,.2f} L ({pct_merma:.2f}%)")
        else:
            st.warning(f"🔴 ALERTA DE VARIACIÓN VOLUMÉTRICA | Desviación: {dif_litros:,.2f} L ({pct_merma:.2f}%)")

    if s.ocr_confianza and s.ocr_confianza != "alta":
        st.checkbox(
            "He verificado Aumento Bruto, fecha y horas contra el ticket impreso",
            key="chk_confirma_ticket",
        )
    return folio_input


def _hora_valida(valor):
    v = (valor or "").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", v):
        return False
    try:
        datetime.strptime(v, "%H:%M")
        return True
    except ValueError:
        return False


def validar_captura():
    s = st.session_state
    errores = []
    if s.d_litros_desc <= 0:
        errores.append("Captura el 'Aumento Bruto Veeder-Root' (debe ser mayor a 0).")
    try:
        datetime.strptime((s.d_fecha or "").strip(), "%d/%m/%Y")
    except ValueError:
        errores.append("La 'Fecha Descarga' debe ser válida y con formato DD/MM/AAAA.")
    if not _hora_valida(s.d_hora_ini):
        errores.append("La 'Hora Inicio' debe tener formato HH:MM (24 h).")
    if not _hora_valida(s.d_hora_fin):
        errores.append("La 'Hora Término' debe tener formato HH:MM (24 h).")
    if s.ocr_confianza and s.ocr_confianza != "alta" and not s.get("chk_confirma_ticket", False):
        errores.append("Marca la casilla de verificación del ticket impreso antes de continuar.")
    return errores
