import hashlib
import io

import streamlit as st
from PIL import ImageOps
from streamlit_paste_button import paste_image_button

from app_estado import OPCIONES_TQ
from extractor import extraer_tira_ocr_local


def _aplicar_ocr(ocr):
    s = st.session_state
    s.d_litros_desc = float(ocr.get("litros_descargados", 0.0) or 0.0)
    s.d_fecha = ocr.get("fecha", "") or ""
    s.d_hora_ini = ocr.get("hora_inicio", "") or ""
    s.d_hora_fin = ocr.get("hora_termino", "") or ""
    if ocr.get("tanque_vr") in OPCIONES_TQ:
        s.d_tanque_vr = ocr["tanque_vr"]
    s.ocr_confianza = ocr.get("confianza", "") or "nula"
    s.ocr_alertas = list(ocr.get("alertas", []))
    st.session_state["chk_confirma_ticket"] = False


def _mostrar_estado():
    conf = st.session_state.ocr_confianza
    if conf == "alta":
        st.success("✅ Ticket leído localmente (confianza alta).")
    else:
        st.warning(
            f"⚠️ Ticket leído localmente con confianza {conf or 'nula'}. "
            "Verifica los datos contra el ticket impreso."
        )
    for alerta in st.session_state.ocr_alertas:
        st.info(f"ℹ️ {alerta}")


def render_ticket():
    st.markdown("**2. Tira Veeder-Root (Pegar de Portapapeles)**")
    paste_result = paste_image_button(
        label="📋 Pegar imagen (PC)",
        background_color="#FF4B4B",
        hover_background_color="#FF6666",
        key="paste_btn",
    )
    img_tira = None
    if paste_result.image_data is not None:
        img_tira = ImageOps.exif_transpose(paste_result.image_data)
        buf = io.BytesIO()
        img_tira.convert("RGB").save(buf, format="PNG")
        bytes_tira = buf.getvalue()
        huella = hashlib.md5(bytes_tira).hexdigest()
        if st.session_state.ultimo_hash_tira != huella:
            with st.spinner("Leyendo ticket con OCR local (Tesseract)..."):
                ocr = extraer_tira_ocr_local(bytes_tira, st.session_state.d_litros_fac)
            _aplicar_ocr(ocr)
            st.session_state.ultimo_hash_tira = huella
        _mostrar_estado()
    return img_tira
