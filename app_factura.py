import streamlit as st

from extractor import (
    extraer_datos_factura_local,
    extraer_datos_xml_cfdi,
    texto_desde_pdf,
)


def _aplicar_factura(loc, nombre):
    s = st.session_state
    s.d_factura = loc.get("factura", "") or ""
    s.d_uuid = loc.get("uuid", "") or ""
    s.d_producto = loc.get("producto", "REGULAR (MAGNA)")
    s.d_tanque_vr = loc.get("tanque_vr", "T1: MAGNA")
    s.d_litros_fac = float(loc.get("litros_facturados", 0.0) or 0.0)
    s.d_embarque = loc.get("embarque", "S/D") or "S/D"
    s.d_tanque_at = loc.get("tanque_at", "S/D") or "S/D"
    s.ultimo_archivo_fac = nombre


def _campos_faltantes():
    s = st.session_state
    revisar = [
        ("Folio Factura", bool(s.d_factura)),
        ("UUID", bool(s.d_uuid)),
        ("Litros Facturados", s.d_litros_fac > 0),
        ("Embarque", s.d_embarque not in ("", "S/D")),
        ("Tanque Autotanque", s.d_tanque_at not in ("", "S/D")),
    ]
    return [nombre for nombre, ok in revisar if not ok]


def render_factura():
    st.markdown("**1. Factura (PDF o XML del SAT)**")
    archivo = st.file_uploader("Sube archivo PDF o XML:", type=["pdf", "xml"], key="factura_up")
    if not archivo:
        return
    nombre = archivo.name
    es_xml = nombre.lower().endswith(".xml")
    nuevo = st.session_state.ultimo_archivo_fac != nombre
    try:
        if nuevo:
            if es_xml:
                loc = extraer_datos_xml_cfdi(archivo.getvalue(), nombre)
            else:
                loc = extraer_datos_factura_local(texto_desde_pdf(archivo.getvalue()), nombre)
            _aplicar_factura(loc, nombre)
    except Exception as e_fac:
        st.warning(f"Aviso lectura de factura: {e_fac}")
        return
    if st.session_state.d_factura or st.session_state.d_uuid:
        origen = "XML leída al 100%" if es_xml else "PDF leída localmente"
        st.success(f"✅ Factura {origen} (0s).")
    else:
        st.warning("⚠️ No se pudo leer la factura (¿PDF escaneado?). Captura los datos en la Mesa de Control.")
    faltan = _campos_faltantes()
    if faltan:
        st.info("ℹ️ Revisa en la Mesa de Control: " + ", ".join(faltan) + ".")
