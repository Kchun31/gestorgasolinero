import base64
import io
import json
import os
import re
import time
import google.generativeai as genai
from google.api_core import exceptions
from PIL import Image, ImageOps
import PyPDF2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import requests
import streamlit as st
from streamlit_paste_button import paste_image_button

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

def buscar_imagen(nombre_base):
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        if os.path.exists(f"{nombre_base}.{ext}"):
            return f"{nombre_base}.{ext}"
    return None

if "folio_actual" not in st.session_state:
    st.session_state.folio_actual = obtener_folio()

st.title("ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**1. Factura (PDF o Cámara)**")
    metodo_factura = st.radio("Método Factura:", ["Subir PDF/Imagen", "Usar Cámara"], horizontal=True, key="metodo_factura")
    img_factura, factura_file, texto_pdf, bytes_factura = None, None, "", None

    if metodo_factura == "Subir PDF/Imagen":
        factura_file = st.file_uploader("Sube archivo:", type=["pdf", "png", "jpg", "jpeg"], key="factura_up")
        if factura_file:
            if factura_file.type == "application/pdf":
                try:
                    reader = PyPDF2.PdfReader(factura_file)
                    for page in reader.pages:
                        texto_pdf += page.extract_text() + "\n"
                except Exception:
                    pass
            else:
                bytes_factura = factura_file.getvalue()
                img_factura = ImageOps.exif_transpose(Image.open(factura_file))
    else:
        foto_factura_cam = st.camera_input("Toma foto de la factura", key="camara_factura")
        if foto_factura_cam:
            bytes_factura = foto_factura_cam.getvalue()
            img_factura = ImageOps.exif_transpose(Image.open(foto_factura_cam))

with col2:
    st.markdown("**2. Tira Veeder-Root (Foto o Cámara)**")
    paste_result = paste_image_button(label="Pegar imagen (PC)", background_color="#FF4B4B", hover_background_color="#FF6666", key="paste_btn")
    img_tira, bytes_tira = None, None

    if paste_result.image_data is not None:
        img_tira = ImageOps.exif_transpose(paste_result.image_data)
        buffer_paste = io.BytesIO()
        img_tira.save(buffer_paste, format="PNG")
        bytes_tira = buffer_paste.getvalue()
        st.success("Imagen pegada correctamente.")
    else:
        metodo_foto = st.radio("Método Tira:", ["Usar Cámara", "Subir Archivo"], horizontal=True, key="metodo_captura")
        if metodo_foto == "Usar Cámara":
            foto_camara = st.camera_input("Toma la foto del ticket", key="camara_veeder")
            if foto_camara:
                bytes_tira = foto_camara.getvalue()
                img_tira = ImageOps.exif_transpose(Image.open(foto_camara))
        else:
            tira_up = st.file_uploader("Sube la foto:", type=["jpg", "jpeg", "png"], key="galeria_veeder")
            if tira_up:
                bytes_tira = tira_up.getvalue()
                img_tira = ImageOps.exif_transpose(Image.open(tira_up))

folio_input = st.number_input("Número de Folio Consecutivo", min_value=1, value=st.session_state.folio_actual, step=1)
st.markdown("---")

@st.cache_data(show_spinner=False)
def procesar_con_ia_seguro(prompt_texto, texto_extraido, b_factura, b_tira, api_key):
    genai.configure(api_key=api_key)
    modelo = genai.GenerativeModel("gemini-1.5-flash")
    contenido = [prompt_texto]
    if texto_extraido:
        contenido.append(f"Texto extraído del PDF: {texto_extraido}")
    if b_factura:
        contenido.append(Image.open(io.BytesIO(b_factura)))
    if b_tira:
        contenido.append(Image.open(io.BytesIO(b_tira)))
    for intento in range(3):
        try:
            return modelo.generate_content(contenido).text
        except exceptions.ResourceExhausted:
            if intento < 2:
                time.sleep(20)
            else:
                raise

if st.button("Procesar y Subir a Google Drive", type="primary", use_container_width=True):
    if (not factura_file and img_factura is None) or img_tira is None:
        st.error("Proporciona tanto la Factura como la Tira Veeder-Root para continuar.")
    else:
        with st.spinner("Analizando con precisión quirúrgica mediante IA..."):
            try:
                api_key = st.secrets.get("GEMINI_API_KEY")
                if not api_key:
                    st.error("Llave Gemini no encontrada.")
                    st.stop()
            except Exception as e:
                st.error(f"Error credenciales: {e}")
                st.stop()

            prompt = """Eres un auditor fiscal y operativo experto en estaciones de servicio en México. 1. FACTURA: Busca Folio, UUID y EXTRAE EXCLUSIVAMENTE LITROS DE MAGNA/REGULAR (ignora Premium/Diésel/Pesos). 2. TIRA VEEDER-ROOT: Busca 'AUMENTO BRUTO CT' del tanque 1, fecha (DD/MM/AAAA) y horarios. Devuelve ÚNICAMENTE JSON válido: {"uuid": "...", "factura": "...", "litros_facturados": 0.0, "litros_descargados": 0.0, "fecha": "...", "hora_inicio": "...", "hora_termino": "..."}"""

            try:
                respuesta_texto = procesar_con_ia_seguro(prompt, texto_pdf, bytes_factura, bytes_tira, api_key)
                match = re.search(r"\{.*\}", respuesta_texto, re.DOTALL)
                if match:
                    datos_ia = json.loads(match.group(0), strict=False)
                else:
                    raise ValueError("Formato IA inválido")

                factura_num = str(datos_ia.get("factura", "SD")).replace("\n", "")
                uuid = str(datos_ia.get("uuid", "SD")).replace("\n", "")
                vol_facturado = float(datos_ia.get("litros_facturados", 0))
                vol_descargado = float(datos_ia.get("litros_descargados", 0))
                fecha_tira = str(datos_ia.get("fecha", "SD")).replace("\n", "")
                hora_inicio = str(datos_ia.get("hora_inicio", "SD")).replace("\n", "")
                hora_termino = str(datos_ia.get("hora_termino", "SD")).replace("\n", "")
                desviacion = abs(vol_facturado - vol_descargado)

                siguiente_folio = int(folio_input) + 1
                guardar_folio(siguiente_folio)
                st.session_state.folio_actual = siguiente_folio
            except Exception as e:
                st.error(f"Error IA: {e}")
                st.stop()

            try:
                folio_str = str(int(folio_input)).zfill(4)
                nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_num}.pdf"
                ruta_pdf = os.path.join(carpeta_destino, nombre_archivo_pdf)

                doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
                elementos, styles = [], getSampleStyleSheet()
                estilo_celda = ParagraphStyle("Celda", fontName="Helvetica", fontSize=6.5, leading=8.5)
                estilo_celda_centro = ParagraphStyle("CeldaCentro", fontName="Helvetica", fontSize=6.5, leading=8.5, alignment=1)

                logo_path = buscar_imagen("logo_teika") or buscar_imagen("cabecera")
                img_logo = RLImage(logo_path, width=85, height=40) if logo_path else Paragraph("[Logo]", styles["Normal"])

                t_cabecera = Table([[img_logo, Paragraph("<b>COMBUSTIBLES BUENOS AIRES S.A. DE C.V.<br/>JANOS, CHIHUAHUA.</b>", ParagraphStyle("E", leading=12))]], colWidths=[95, 465])
                elementos.extend([t_cabecera, Spacer(1, 10)])

                estilo_bita = ParagraphStyle("Bita", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#a81c1c"), alignment=1)
                t_titulos = Table([[Paragraph("SISTEMA SASISOPA", ParagraphStyle("S", alignment=1, textColor=colors.white))], [Paragraph(f"BITÁCORA OFICIAL FOLIO: {folio_str}", estilo_bita)]])
                t_titulos.setStyle(TableStyle([('BACKGROUND', (0,0), (0,0), colors.HexColor("#a81c1c")), ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#a81c1c"))]))
                elementos.extend([t_titulos, Spacer(1, 4)])

                t_info = Table([
                    ["FACTURA:", Paragraph(f"{factura_num}", estilo_celda), "RFC ESTACIÓN:", "CBA140131V12"],
                    ["PRODUCTO:", f"MAGNA ({vol_facturado:,.2f} L)", "PROVEEDOR:", "UNEGAS"],
                    ["FECHA DESCARGA:", Paragraph(f"{fecha_tira}", estilo_celda), "HORARIO:", Paragraph(f"{hora_inicio} a {hora_termino}", estilo_celda)]
                ], colWidths=[90, 190, 90, 190])
                t_info.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('FONTSIZE', (0,0), (-1,-1), 6.5)]))
                elementos.extend([t_info, Spacer(1, 4)])

                t_control = Table([
                    ["PARAMETRO", "REGISTRO", "CUMPLE", "VALORES"],
                    ["VEEDER-ROOT", Paragraph(f"Aumento Bruto: {vol_descargado:,.2f} L", estilo_celda), "[X] SÍ", Paragraph(f"Desviación: {desviacion:,.2f} L", estilo_celda)]
                ], colWidths=[110, 250, 90, 110])
                t_control.setStyle(TableStyle([('BACKGROUND', (0, 0), (1, 0), colors.HexColor("#a81c1c")), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('GRID', (0, 0), (-1,-1), 0.5, colors.black), ('FONTSIZE', (0,0), (-1,-1), 6.5)]))
                elementos.extend([t_control, Spacer(1, 20)])

                sj, sy = buscar_imagen("firma_javier"), buscar_imagen("firma_yahir")
                
                cj = RLImage(sj, width=100, height=35) if sj else Paragraph("[Firma Javier]", styles["Normal"])
                cy = RLImage(sy, width=100, height=35) if sy else Paragraph("[Firma Yahir]", styles["Normal"])

                t_firmas = Table([[cj, cy], ["Javier A. García", "Yahir Caro M."]], colWidths=[280, 280])
                t_firmas.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTSIZE', (0,0), (-1,-1), 6.5)]))
                elementos.extend([t_firmas, PageBreak(), t_cabecera, Spacer(1, 15)])

                temp_img_path = "temp_veeder.png"
                img_tira.save(temp_img_path)
                img_veeder_pdf = RLImage(temp_img_path, width=190, height=300)
                img_veeder_pdf.hAlign = "CENTER"
                elementos.extend([Paragraph("ANEXO DE EVIDENCIA", estilo_bita), img_veeder_pdf, Spacer(1, 10)])

                doc.build(elementos)
            except Exception as e:
                st.error(f"Error crítico al ensamblar el PDF: {e}")
                st.stop()

            try:
                url_script = st.secrets.get("URL_GOOGLE_SCRIPT")
                if url_script:
                    with open(ruta_pdf, "rb") as f:
                        pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
                    res = requests.post(url_script, data={"archivoB64": pdf_b64, "nombreArchivo": nombre_archivo_pdf})
                    if "éxito" in res.text.lower():
                        st.success("¡Bitácora enviada y guardada en tu Google Drive!")
                        st.info(f"Siguiente folio reservado: {siguiente_folio}")
                    else:
                        st.warning(f"Error Drive: {res.text}")
                else:
                    st.warning("Falta URL_GOOGLE_SCRIPT en Secrets.")
            except Exception as e:
                st.warning(f"Error red: {e}")

            try:
                with open(ruta_pdf, "rb") as pdf_file:
                    st.download_button(label="Descargar Copia", data=pdf_file, file_name=nombre_archivo_pdf, mime="application/pdf")
            except Exception as e:
                pass
