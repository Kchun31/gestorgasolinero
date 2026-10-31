import base64
import os
import re

import requests
import streamlit as st

from app_estado import CARPETA_DESTINO, guardar_folio
from pdf_engine import generar_pdf_recepcion


def procesar_y_subir(folio_input, img_tira):
    factura_clean = re.sub(r'[\\/*?:"<>| ]', "_", st.session_state.d_factura.strip() or "SD")
    folio_str = str(int(folio_input)).zfill(4)
    nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_clean}.pdf"
    ruta_pdf = os.path.join(CARPETA_DESTINO, nombre_archivo_pdf)

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
        "operador": st.session_state.d_operador.strip() or "Javier Arturo Garcia",
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
            res = requests.post(
                url_script.strip(),
                data={"archivoB64": pdf_b64, "nombreArchivo": nombre_archivo_pdf},
                timeout=45,
            )
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
        st.download_button(
            label="📥 Descargar Copia",
            data=pdf_file.read(),
            file_name=nombre_archivo_pdf,
            mime="application/pdf",
            use_container_width=True,
        )
