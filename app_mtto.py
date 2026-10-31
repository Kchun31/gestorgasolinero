import pandas as pd
import streamlit as st
from mtto_engine import extraer_actividades_excel, generar_zip_mantenimiento

def render_modulo_mantenimiento():
    st.subheader("🛠️ Generador Automático de Bitácoras de Mantenimiento y Limpieza")
    st.caption("NOM-005-ASEA-2016 | Realiza: Salvador Delgado P. | Autoriza: Jesús Antonio Carbajal Álvarez")

    archivo_xlsx = st.file_uploader(
        "1. Sube el Calendario / Plan de Mantenimiento en Excel (.xlsx):",
        type=["xlsx", "xls"],
        key="up_mtto_xlsx"
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        anio_sel = st.number_input("Año de Ejecución", min_value=2024, max_value=2035, value=2026, step=1)
    with c2:
        folio_mtto = st.number_input("Folio Inicial Mantenimiento", min_value=1, value=1001, step=1)
    with c3:
        folio_limp = st.number_input("Folio Inicial Limpieza Diaria", min_value=1, value=5001, step=1)

    incluir_diaria = st.checkbox(
        "✅ Incluir automáticamente las Bitácoras Diarias de Limpieza de Elementos Constructivos (todos los días del mes)",
        value=True
    )

    if archivo_xlsx is not None:
        try:
            acts, mes_num, mes_nombre, anio_det = extraer_actividades_excel(
                archivo_xlsx.getvalue(), archivo_xlsx.name, anio_sel
            )
            st.success(
                f"✅ Excel analizado: **{len(acts)} mantenimientos programados** detectados en **{mes_nombre} {anio_sel}**."
            )

            with st.expander("📋 Ver desglose de actividades programadas en el Excel", expanded=False):
                df_vista = pd.DataFrame(acts)[["fecha", "area", "elemento", "periodicidad"]]
                df_vista.columns = ["Fecha", "Área / Equipo", "Numeral NOM-005", "Periodicidad"]
                st.dataframe(df_vista, use_container_width=True, hide_index=True)

            if st.button("🚀 Generar Paquete Completo de Bitácoras (.ZIP)", type="primary", use_container_width=True):
                with st.spinner("Generando bitácoras oficiales en PDF con firmas y organizando carpetas..."):
                    zip_bytes, sig_mtto, sig_limp = generar_zip_mantenimiento(
                        acts,
                        mes_num,
                        mes_nombre,
                        anio_sel,
                        folio_mtto_ini=folio_mtto,
                        folio_limp_ini=folio_limp,
                        incluir_limpieza_diaria=incluir_diaria,
                    )
                nombre_zip = f"Bitacoras_NOM005_{mes_nombre}_{anio_sel}_CBA.zip"
                st.success(
                    f"🎉 ¡Paquete generado con éxito! Siguiente folio Mantenimiento: **{sig_mtto}** | Siguiente folio Limpieza: **{sig_limp}**"
                )
                st.download_button(
                    label=f"📥 Descargar {nombre_zip} (Organizado por Carpetas)",
                    data=zip_bytes,
                    file_name=nombre_zip,
                    mime="application/zip",
                    use_container_width=True,
                )
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo Excel: {e}")
