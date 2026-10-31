import os
import pandas as pd
import streamlit as st
from mtto_engine import (
    ARCHIVO_PLAN_GUARDADO, cargar_folios_mtto, enviar_lote_drive,
    extraer_actividades_excel, fecha_hoy_chihuahua, generar_zip_mantenimiento,
)

def render_modulo_mantenimiento():
    st.subheader("🛠️ Generador Automático de Bitácoras de Mantenimiento y Limpieza")
    st.caption("NOM-005-ASEA-2016 | Realiza: Salvador Delgado P. | Autoriza: Jesús Antonio Carbajal Álvarez")

    hoy = fecha_hoy_chihuahua()
    folios = cargar_folios_mtto()

    archivo_xlsx = st.file_uploader(
        "1. Sube el Calendario / Plan de Mantenimiento (.xlsx) — Se queda guardado automáticamente:",
        type=["xlsx", "xls"],
        key="up_mtto_xlsx"
    )

    excel_bytes = None
    nombre_origen = ""
    if archivo_xlsx is not None:
        excel_bytes = archivo_xlsx.getvalue()
        nombre_origen = archivo_xlsx.name
        with open(ARCHIVO_PLAN_GUARDADO, "wb") as f:
            f.write(excel_bytes)
    elif os.path.exists(ARCHIVO_PLAN_GUARDADO):
        with open(ARCHIVO_PLAN_GUARDADO, "rb") as f:
            excel_bytes = f.read()
        nombre_origen = ARCHIVO_PLAN_GUARDADO
        st.info("📌 Usando el Plan de Mantenimiento guardado en el sistema. (Sube otro arriba si cambias de mes).")

    c1, c2, c3 = st.columns(3)
    with c1:
        anio_sel = st.number_input("Año de Ejecución", min_value=2024, max_value=2035, value=hoy.year, step=1)
    with c2:
        folio_mtto = st.number_input("Folio Inicial Mantenimiento", min_value=1, value=int(folios["folio_mtto"]), step=1)
    with c3:
        folio_limp = st.number_input("Folio Inicial Limpieza Diaria", min_value=1, value=int(folios["folio_limp"]), step=1)

    modo = st.radio(
        "📅 Alcance de generación de bitácoras:",
        [
            f"📆 Al Día de Hoy (Del día 1 al día {hoy.day:02d})",
            f"⚡ Solo lo de Hoy (Día {hoy.day:02d} — Limpieza diaria + Mantenimientos de hoy)",
            "🗂️ Mes Completo (Del día 1 al último día del mes)"
        ],
        index=0
    )

    incluir_diaria = st.checkbox(
        "✅ Incluir automáticamente las Bitácoras Diarias de Limpieza de Elementos Constructivos",
        value=True
    )
    subir_drive = st.checkbox(
        "☁️ Enviar también los PDFs generados a mi carpeta Bitacoras_CBA en Google Drive",
        value=False
    )

    if excel_bytes is not None:
        try:
            acts, mes_num, mes_nombre, _ = extraer_actividades_excel(excel_bytes, nombre_origen, anio_sel)

            if modo.startswith("📆"):
                d_ini, d_fin = 1, hoy.day
            elif modo.startswith("⚡"):
                d_ini, d_fin = hoy.day, hoy.day
            else:
                d_ini, d_fin = 1, 31

            acts_rango = [a for a in acts if d_ini <= a["dia"] <= d_fin]
            acts_hoy = [a for a in acts if a["dia"] == hoy.day]

            st.success(
                f"✅ Plan activo: **{mes_nombre} {anio_sel}** | "
                f"Mantenimientos en el rango seleccionado (días {d_ini} al {d_fin}): **{len(acts_rango)}** | "
                f"Programados exactamente para hoy (día {hoy.day:02d}): **{len(acts_hoy)}**"
            )

            with st.expander("📋 Ver actividades programadas en este rango", expanded=False):
                if acts_rango:
                    df_vista = pd.DataFrame(acts_rango)[["fecha", "area", "elemento", "periodicidad"]]
                    df_vista.columns = ["Fecha", "Área / Equipo", "Numeral NOM-005", "Periodicidad"]
                    st.dataframe(df_vista, use_container_width=True, hide_index=True)
                else:
                    st.write("No hay mantenimientos programados en este rango de días (solo se generará la Limpieza Diaria).")

            if st.button("🚀 Generar Bitácoras Oficiales (.ZIP)", type="primary", use_container_width=True):
                with st.spinner("Generando bitácoras oficiales firmadas..."):
                    zip_bytes, sig_mtto, sig_limp, creados = generar_zip_mantenimiento(
                        acts, mes_num, mes_nombre, anio_sel,
                        folio_mtto_ini=folio_mtto, folio_limp_ini=folio_limp,
                        incluir_limpieza_diaria=incluir_diaria,
                        dia_inicio=d_ini, dia_corte=d_fin
                    )
                    if subir_drive and creados:
                        url_script = st.secrets.get("URL_GOOGLE_SCRIPT")
                        _, msg_drive = enviar_lote_drive(creados, url_script)
                        st.info(f"☁️ {msg_drive}")

                nombre_zip = f"Bitacoras_NOM005_{mes_nombre}_{anio_sel}_Dias_{d_ini:02d}_a_{d_fin:02d}.zip"
                st.success(
                    f"🎉 ¡{len(creados)} bitácoras generadas! Siguiente folio Mtto: **{sig_mtto}** | Siguiente folio Limpieza: **{sig_limp}**"
                )
                st.download_button(
                    label=f"📥 Descargar {nombre_zip}",
                    data=zip_bytes,
                    file_name=nombre_zip,
                    mime="application/zip",
                    use_container_width=True,
                )
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo Excel: {e}")
