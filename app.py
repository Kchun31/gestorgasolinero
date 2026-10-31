import streamlit as st

st.set_page_config(page_title="Bitácoras CBA", page_icon="⛽", layout="centered")

from app_estado import iniciar_estado
from app_factura import render_factura
from app_ticket import render_ticket
from app_mesa import render_mesa, validar_captura
from app_envio import procesar_y_subir

iniciar_estado()

st.title("⛽ ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    render_factura()
with col2:
    img_tira = render_ticket()

folio_input = render_mesa()

st.markdown("---")

if st.button("🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True):
    if img_tira is None:
        st.error("❌ Primero pega la imagen de la Tira Veeder-Root con el botón rojo arriba.")
        st.stop()
    errores = validar_captura()
    if errores:
        for e in errores:
            st.error(f"❌ {e}")
        st.stop()
    procesar_y_subir(folio_input, img_tira)
# === FIN DE app.py ===
