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
    st.session_state.d_factura = st.text_input("Folio Factura", value=st.session_state.d_factura)
    st.session_state.d_litros_fac = st.number_input("Litros Facturados (L)", value=float(st.session_state.d_litros_fac), step=100.0, format="%.2f")
    st.session_state.d_fecha = st.text_input("Fecha Descarga (DD/MM/AAAA)", value=st.session_state.d_fecha)
with c2:
    st.session_state.d_uuid = st.text_input("Folio Fiscal (UUID)", value=st.session_state.d_uuid)
    st.session_state.d_litros_desc = st.number_input("Aumento Bruto Veeder-Root (L)", value=float(st.session_state.d_litros_desc), step=100.0, format="%.2f")
    st.session_state.d_hora_ini = st.text_input("Hora Inicio (HH:MM)", value=st.session_state.d_hora_ini)
with c3:
    opciones_prod = ["REGULAR (MAGNA)", "DIÉSEL", "PREMIUM"]
    idx_p = opciones_prod.index(st.session_state.d_producto) if st.session_state.d_producto in opciones_prod else 0
    st.session_state.d_producto = st.selectbox("Producto", opciones_prod, index=idx_p)
    opciones_tq = ["T1: MAGNA", "T2: DIÉSEL", "T3: PREMIUM"]
    idx_t = opciones_tq.index(st.session_state.d_tanque_vr) if st.session_state.d_tanque_vr in opciones_tq else 0
    st.session_state.d_tanque_vr = st.selectbox("Tanque Veeder-Root", opciones_tq, index=idx_t)
    st.session_state.d_hora_fin = st.text_input("Hora Término (HH:MM)", value=st.session_state.d_hora_fin)

c4, c5, c6 = st.columns(3)
with c4:
    st.session_state.d_embarque = st.text_input("Embarque", value=st.session_state.d_embarque)
with c5:
    st.session_state.d_tanque_at = st.text_input("Tanque Autotanque", value=st.session_state.d_tanque_at)
with c6:
    st.session_state.d_operador = st.text_input("Operador", value=st.session_state.d_operador)

dif_litros = abs(st.session_state.d_litros_fac - st.session_state.d_litros_desc)
pct_merma = (dif_litros / st.session_state.d_litros_fac * 100.0) if st.session_state.d_litros_fac > 0 else 0.0
if st.session_state.d_litros_fac > 0 and st.session_state.d_litros_desc > 0:
    if pct_merma <= 0.55:
        st.success(f"🟢 SEMÁFORO NORMATIVO EN RANGO | Desviación: {dif_litros:,.2f} L ({pct_merma:.2f}%)")
    else:
        st.warning(f"🔴 ALERTA DE VARIACIÓN VOLUMÉTRICA | Desviación: {dif_litros:,.2f} L ({pct_merma:.2f}%)")

st.markdown("---")

if st.button("🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True):
    if img_tira is None:
        st.error("❌ Primero pega la imagen de la Tira Veeder-Root con el botón rojo arriba.")
        st.stop()
    if st.session_state.d_litros_desc <= 0 or not st.session_state.d_fecha.strip():
        st.error("❌ Verifica que 'Aumento Bruto Veeder-Root' y 'Fecha Descarga' tengan datos en la Mesa de Control arriba.")
        st.stop()

    factura_clean = re.sub(r'[\\/*?:"<>| ]', "_", st.session_state.d_factura.strip() or "SD")
    folio_str = str(int(folio_input)).zfill(4)
    nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_clean}.pdf"
    ruta_pdf = os.path.join(carpeta_destino, nombre_archivo_pdf)

    datos_pdf = {
        "folio": int(folio_input),
        "factura": st.session_state.d_factura.strip() or "SD",
        "uuid": st.session_state.d_uuid.strip() or "SD",
        "producto": st.session_state.d_producto,
        "tanque_vr": st.session_state.d_tanque_vr,
        "litros_facturados": st.session_state.d_litros_fac,
        "litros_descargados": st.session_state.d_litros_desc,
        "fecha": st.session_state.d_fecha.strip() or "SD",
        "hora_inicio": st.session_state.d_hora_ini.strip() or "00:00",
        "hora_termino": st.session_state.d_hora_fin.strip() or "00:00",
        "embarque": st.session_state.d_embarque.strip() or "S/D",
        "tanque_at": st.session_state.d_tanque_at.strip() or "S/D",
        "operador": st.session_state.d_operador.strip() or "Javier Arturo Garcia"
    }

    try:
        generar_pdf_recepcion(datos_pdf, img_tira, ruta_pdf)
        siguiente_folio = int(folio_input) + 1
        guardar_folio(siguiente_folio)
        st.session_state.folio_actual = siguiente_folio
    except Exception as e_pdf:
        st.error(f"❌ Error al construir el PDF: {e_pdf}")
        st.stop()

    try:
        url_script = st.secrets.get("URL_GOOGLE_SCRIPT")
        if url_script:
            with open(ruta_pdf, "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
            res = requests.post(url_script.strip(), data={"archivoB64": pdf_b64, "nombreArchivo": nombre_archivo_pdf}, timeout=45)
            if any(w in res.text.lower() for w in ["éxito", "exito", "success"]):
                st.success("✅ ¡Bitácora enviada y guardada en tu Google Drive!")
                st.info(f"📌 Siguiente folio reservado: {siguiente_folio}")
            else:
                st.warning(f"⚠️ Respuesta Drive: {res.text}")
        else:
            st.warning("⚠️ Falta URL_GOOGLE_SCRIPT en Secrets.")
    except Exception as e_net:
        st.warning(f"⚠️ PDF creado, pero falló envío a Drive: {e_net}")

    with open(ruta_pdf, "rb") as pdf_file:
        st.download_button(label="📥 Descargar Copia", data=pdf_file.read(), file_name=nombre_archivo_pdf, mime="application/pdf", use_container_width=True)
# === FIN DE app.py ===
