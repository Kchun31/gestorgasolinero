import streamlit as st
import google.generativeai as genai
import requests
import base64
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from PIL import Image

# Configuración de página de la aplicación
st.set_page_config(page_title="Combustibles Buenos Aires S.A. de C.V.", layout="centered")

# Configurar API de Gemini con el modelo actualizado y estable
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Actualizado a gemini-2.5-flash para evitar errores de modelos obsoletos
    model = genai.GenerativeModel("gemini-2.5-flash")
except Exception as e:
    st.error(f"Error configurando la API de Gemini en los Secrets: {e}")

st.title("Combustibles Buenos Aires S.A. de C.V.")

# Interfaz principal
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Factura (Sube PDF o Toma Foto)")
    archivo_factura = st.file_uploader("Sube el archivo de la factura", type=["pdf", "png", "jpg", "jpeg"])

with col2:
    st.subheader("2. Tira Veeder-Root (Foto)")
    archivo_veeder = st.file_uploader("Sube la foto del Veeder-Root", type=["png", "jpg", "jpeg"], key="veeder")

folio = st.number_input("Número de Folio Consecutivo", min_value=1, value=20)

if st.button("Procesar y Subir a Google Drive", type="primary"):
    if not archivo_factura or not archivo_veeder:
        st.warning("Por favor sube ambos documentos (Factura y Veeder-Root) para continuar.")
    else:
        with st.status("Leyendo documentos con IA y creando bitácora...", expanded=True) as status:
            try:
                st.write("Analizando imágenes con Gemini...")
                
                # Procesar imagen del Veeder-Root y factura
                img_veeder = Image.open(archivo_veeder)
                
                prompt = (
                    "Analiza estos documentos de la estación de servicio y extrae los datos clave: "
                    "importe de factura, litros, número de estación y datos del medidor Veeder-Root."
                )
                
                # Generar contenido con el modelo actualizado
                response = model.generate_content([prompt, img_veeder])
                resultado_ia = response.text
                
                st.write("Generando documento PDF...")
                
                # Crear PDF con ReportLab
                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=letter)
                c.drawString(100, 750, "Combustibles Buenos Aires S.A. de C.V.")
                c.drawString(100, 730, f"Folio Consecutivo: {folio}")
                c.drawString(100, 700, "Resumen del análisis de IA:")
                
                y = 670
                for linea in resultado_ia.split('\n')[:15]:
                    c.drawString(100, y, linea[:90])
                    y -= 20
                    if y < 50:
                        break
                        
                c.save()
                buffer.seek(0)
                pdf_bytes = buffer.getvalue()
                
                nombre_pdf = f"Bitacora_Folio_{folio:04d}.pdf"
                
                st.write("Enviando respaldo automático a Google Drive...")
                
                # Enviar a Google Apps Script usando la URL configurada en los Secrets
                url_script = st.secrets["URL_GOOGLE_SCRIPT"]
                
                payload = {
                    "archivoB64": base64.b64encode(pdf_bytes).decode("utf-8"),
                    "nombreArchivo": nombre_pdf
                }
                
                response_script = requests.post(url_script, data=payload)
                
                if "Éxito" in response_script.text or response_script.status_code == 200:
                    status.update(label="¡Bitácora generada y guardada en Google Drive con éxito!", state="complete", expanded=False)
                    st.success("¡Proceso completado correctamente!")
                    st.download_button(
                        label="Descargar PDF Generado",
                        data=pdf_bytes,
                        file_name=nombre_pdf,
                        mime="application/pdf"
                    )
                else:
                    st.error(f"Error al guardar en Google Drive: {response_script.text}")
                    
            except Exception as e:
                status.update(label="Error procesando el documento.", state="error")
                st.error(f"Detalle del error: {e}")
