import base64, io, os, re, requests
from PIL import Image, ImageOps
import PyPDF2
import streamlit as st
from streamlit_paste_button import paste_image_button
from extractor import extraer_datos_factura_local, extraer_datos_xml_cfdi, extraer_tira_ocr_local
from pdf_engine import generar_pdf_recepcion

st.set_page_config(page_title="Bitácoras CBA", page_icon="⛽", layout="centered")
carpeta_destino = "temp_destino"
os.makedirs(carpeta_destino, exist_ok=True)
ARCHIVO_FOLIO = "folio_historico.txt"

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

defaults = {
    "folio_actual": obtener_folio(),
    "d_factura": "",
    "d_uuid": "",
    "d_producto": "REGULAR (MAGNA)",
    "d_tanque_vr": "T1: MAGNA",
    "d_litros_fac": 0.0,
    "d_litros_desc": 0.0,
    "d_fecha": "",
    "d_hora_ini": "00:01",
    "d_hora_fin": "00:47",
    "d_embarque": "S/D",
    "d_tanque_at": "S/D",
    "d_operador": "Javier Arturo Garcia",
    "ultimo_archivo_fac": "",
    "ultimo_hash_tira": 0
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.title("⛽ ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**1. Factura (PDF o XML del SAT)**")
    factura_file = st.file_uploader("Sube archivo PDF o XML:", type=["pdf", "xml"], key="factura_up")
    if factura_file:
        nombre_up = factura_file.name.lower()
        if nombre_up.endswith(".xml"):
            if st.session_state.ultimo_archivo_fac != factura_file.name:
                loc = extraer_datos_xml_cfdi(factura_file.getvalue(), factura_file.name)
                st.session_state.d_factura = loc["factura"]
                st.session_state.d_uuid = loc["uuid"]
                st.session_state.d_producto = loc["producto"]
                st.session_state.d_tanque_vr = loc["tanque_vr"]
                if loc["litros_facturados"] > 0:
                    st.session_state.d_litros_fac = loc["litros_facturados"]
                st.session_state.ultimo_archivo_fac = factura_file.name
            st.success("✅ Factura XML leída al 100% (0s).")
        elif nombre_up.endswith(".pdf"):
            try:
                texto_pdf = ""
                reader = PyPDF2.PdfReader(io.BytesIO(factura_file.getvalue()))
                for page in reader.pages:
                    texto_pdf += (page.extract_text() or "") + "\n"
                if st.session_state.ultimo_archivo_fac != factura_file.name:
                    loc = extraer_datos_factura_local(texto_pdf, factura_file.name)
                    st.session_state.d_factura = loc["factura"]
                    st.session_state.d_uuid = loc["uuid"]
                    st.session_state.d_producto = loc["producto"]
                    st.session_state.d_tanque_vr = loc["tanque_vr"]
                    if loc["litros_facturados"] > 0:
                        st.session_state.d_litros_fac = loc["litros_facturados"]
                    st.session_state.d_embarque = loc["embarque"]
                    st.session_state.d_tanque_at = loc["tanque_at"]
                    st.session_state.ultimo_archivo_fac = factura_file.name
                st.success("✅ Factura PDF leída localmente (0s).")
            except Exception as e_pdf:
                st.warning(f"Aviso lectura PDF: {e_pdf}")

with col2:
    st.markdown("**2. Tira Veeder-Root (Pegar de Portapapeles)**")
    paste_result = paste_image_button(
        label="📋 Pegar imagen (PC)",
        background_color="#FF4B4B",
        hover_background_color="#FF6666",
        key="paste_btn"
    )
    img_tira = None
    if paste_result.image_data is not None:
        img_tira = ImageOps.exif_transpose(paste_result.image_data)
        buf = io.BytesIO()
        img_tira.convert("RGB").save(buf, format="JPEG", quality=85)
        bytes_tira = buf.getvalue()
        h_tira = len(bytes_tira)
        if st.session_state.ultimo_hash_tira != h_tira:
            ocr = extraer_tira_ocr_local(bytes_tira)
            if ocr["litros_descargados"] > 0:
                st.session_state.d_litros_desc = ocr["litros_descargados"]
            if ocr["fecha"]:
                st.session_state.d_fecha = ocr["fecha"]
            if ocr["hora_inicio"]:
                st.session_state.d_hora_ini = ocr["hora_inicio"]
            if ocr["hora_termino"]:
                st.session_state.d_hora_fin = ocr["hora_termino"]
            if ocr["tanque_vr"]:
                st.session_state.d_tanque_vr = ocr["tanque_vr"]
            st.session_state.ultimo_hash_tira = h_tira
        st.success("✅ Imagen pegada y procesada localmente (Sin IA).")

folio_input = st.number_input("📌 Número de Folio Consecutivo", min_value=1, value=st.session_state.folio_actual, step=1)

st.markdown("### 🛠️ Mesa de Control y Validación (NOM-005-ASEA-2016)")
c1, c2, c3 = st.columns(3)
with c1:
