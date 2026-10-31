import streamlit as st
from app_estado import iniciar_estado
from app_factura import render_factura
from app_ticket import render_ticket
from app_mesa import render_mesa, validar_mesa
from app_envio import procesar_y_subir
from app_mtto import render_modulo_mantenimiento

st.set_page_config(page_title="ERP Bitácoras CBA", page_icon="⛽", layout="centered")
iniciar_estado()

st.sidebar.title("⛽ Gestor Gasolinero CBA")
modulo = st.sidebar.radio(
    "Selecciona el Módulo:",
    [
        "⛽ Recepción y Descargas (Veeder-Root)",
        "🛠️ Mantenimiento y Limpieza (NOM-005)"
    ]
)

st.title("⛽ ERP | Cumplimiento NOM-005-ASEA-2016")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

if modulo.startswith("⛽"):
    col1, col2 = st.columns(2)
    with col1:
        render_factura()
    with col2:
        img_tira = render_ticket()

    folio_input = st.number_input(
        "📌 Número de Folio Consecutivo",
        min_value=1,
        value=st.session_state.folio_actual,
        step=1,
    )
    confirmado = render_mesa()
    st.markdown("---")

    if st.button("🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True):
        errores = validar_mesa(img_tira, confirmado)
        if errores:
            for e in errores:
                st.error(f"❌ {e}")
            st.stop()
        procesar_y_subir(int(folio_input), img_tira)
else:
    render_modulo_mantenimiento()
