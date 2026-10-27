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

def limpiar_flotante(valor, nombre_campo):
    if valor is None or str(valor).strip() == "":
        return 0.0
    texto = str(valor).strip().replace(",", "")
    coincidencias = re.findall(r"[-+]?\d*\.?\d+", texto)
    if not coincidencias:
        raise ValueError(f"El campo '{nombre_campo}' no contiene un número válido (Valor recibido: '{valor}').")
    numero = float(coincidencias[0])
    if 10.0 <= numero <= 99.999 and "." in coincidencias[0] and len(coincidencias[0].split(".")[1]) == 3:
        numero = numero * 1000.0
    return numero

if "folio_actual" not in st.session_state:
    st.session_state.folio_actual = obtener_folio()

st.title("⛽ ERP | Recepción y Descargas")
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
                    bytes_pdf_raw = factura_file.getvalue()
                    reader = PyPDF2.PdfReader(io.BytesIO(bytes_pdf_raw))
                    for page in reader.pages:
                        extraido = page.extract_text()
                        if extraido:
                            texto_pdf += extraido + "\n"
                except Exception as e_pdf:
                    st.warning(f"Aviso al leer texto del PDF: {e_pdf}")
            else:
                try:
                    bytes_factura = factura_file.getvalue()
                    img_factura = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_factura)))
                except Exception as e_img:
                    st.error(f"Error al abrir la imagen de la factura: {e_img}")
    else:
        foto_factura_cam = st.camera_input("Toma foto de la factura", key="camara_factura")
        if foto_factura_cam:
            try:
                bytes_factura = foto_factura_cam.getvalue()
                img_factura = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_factura)))
            except Exception as e_cam:
                st.error(f"Error al procesar foto de cámara de factura: {e_cam}")

with col2:
    st.markdown("**2. Tira Veeder-Root (Foto o Cámara)**")
    paste_result = paste_image_button(label="📋 Pegar imagen (PC)", background_color="#FF4B4B", hover_background_color="#FF6666", key="paste_btn")
    img_tira, bytes_tira = None, None

    if paste_result.image_data is not None:
        try:
            img_tira = ImageOps.exif_transpose(paste_result.image_data)
            buffer_paste = io.BytesIO()
            img_tira.save(buffer_paste, format="PNG")
            bytes_tira = buffer_paste.getvalue()
            st.success("✅ Imagen pegada correctamente.")
        except Exception as e_paste:
            st.error(f"Error al procesar la imagen pegada: {e_paste}")
    else:
        metodo_foto = st.radio("Método Tira:", ["Usar Cámara", "Subir Archivo"], horizontal=True, key="metodo_captura")
        if metodo_foto == "Usar Cámara":
            foto_camara = st.camera_input("Toma la foto del ticket", key="camara_veeder")
            if foto_camara:
                try:
                    bytes_tira = foto_camara.getvalue()
                    img_tira = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_tira)))
                except Exception as e_cam_v:
                    st.error(f"Error al procesar cámara de Tira: {e_cam_v}")
        else:
            tira_up = st.file_uploader("Sube la foto:", type=["jpg", "jpeg", "png"], key="galeria_veeder")
            if tira_up:
                try:
                    bytes_tira = tira_up.getvalue()
                    img_tira = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_tira)))
                except Exception as e_up_v:
                    st.error(f"Error al abrir archivo de Tira: {e_up_v}")

folio_input = st.number_input("📌 Número de Folio Consecutivo", min_value=1, value=st.session_state.folio_actual, step=1)
st.markdown("---")

@st.cache_data(show_spinner=False)
def procesar_con_ia_seguro(prompt_texto, texto_extraido, b_factura, b_tira, api_key, pdf_raw=None):
    genai.configure(api_key=api_key)
    modelo = genai.GenerativeModel("gemini-3.8-flash")
    contenido = [prompt_texto]
    if pdf_raw:
        contenido.append({"mime_type": "application/pdf", "data": pdf_raw})
    if texto_extraido and texto_extraido.strip():
        contenido.append(f"Texto de apoyo extraído del PDF:\n{texto_extraido}")
    if b_factura:
        contenido.append(Image.open(io.BytesIO(b_factura)))
    if b_tira:
        contenido.append(Image.open(io.BytesIO(b_tira)))
    for intento in range(3):
        try:
            respuesta = modelo.generate_content(contenido)
            if not respuesta or not respuesta.text:
                raise ValueError("El modelo 'gemini-3.8-flash' devolvió una respuesta vacía.")
            return respuesta.text
        except exceptions.ResourceExhausted:
            if intento < 2:
                time.sleep(20)
            else:
                raise

if st.button("🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True):
    if (not factura_file and img_factura is None) or img_tira is None:
        st.error("Proporciona tanto la Factura como la Tira Veeder-Root para continuar.")
    else:
        with st.spinner("Analizando con precisión quirúrgica mediante IA..."):
            try:
                api_key = st.secrets.get("GEMINI_API_KEY")
                if not api_key:
                    st.error("❌ Llave GEMINI_API_KEY no encontrada en Secrets.")
                    st.stop()
            except Exception as e:
                st.error(f"❌ Error credenciales: {e}")
                st.stop()

            if factura_file and factura_file.type == "application/pdf" and not texto_pdf.strip() and not factura_file.getvalue():
                st.error("❌ El archivo PDF de la factura está vacío o dañado.")
                st.stop()

            prompt = """Eres un auditor fiscal y operativo experto en estaciones de servicio en México (NOM-005-ASEA-2016).
Analiza los documentos adjuntos (Factura y Tira Veeder-Root) y extrae con exactitud los siguientes datos:
1. FACTURA:
   - "factura": Folio o Serie+Folio de la factura (ejemplo: "B4705", "B4709").
   - "uuid": Folio Fiscal UUID completo (formato XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX).
   - "litros_facturados": Cantidad numérica de LITROS facturados en el concepto del combustible (busca el volumen/cantidad en litros, ej. 43628.00; ignora importes en pesos). Si hay varios productos, prioriza Regular/Magna; si solo hay un producto en la factura, extrae los litros de ese producto. NUNCA devuelvas 0 si aparece una cantidad en la factura.
   - "embarque": Número de embarque o remisión si aparece en la factura (ej. "779274"), o "S/D" si no aparece.
   - "tanque_at": Identificador del autotanque/tonel/placa si aparece en la factura (ej. "23UY9X"), o "S/D" si no aparece.
2. TIRA VEEDER-ROOT:
   - "litros_descargados": Busca la línea 'AUMENTO BRUTO' (a veces impresa como 'AUMENTO BRUTO = 43285' o 'AUMENTO BRIUTO') y extrae ese valor numérico exacto (ej. 43285.0 o 43342.0), sin importar si el ticket dice T1 o T2. NO uses el Aumento Neto. NUNCA devuelvas 0 si hay un número en AUMENTO BRUTO.
   - "fecha": Fecha del ticket en formato DD/MM/AAAA (convierte años de 2 dígitos como 13-10-26 a 13/10/2026).
   - "hora_inicio": Hora de INICIO AUMENTO en formato HH:MM (ej. "00:01" o "12:51").
   - "hora_termino": Hora de FIN AUMENTO en formato HH:MM (ej. "00:47" o "13:27").

Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta:
{"uuid": "...", "factura": "...", "litros_facturados": 0.0, "litros_descargados": 0.0, "fecha": "DD/MM/AAAA", "hora_inicio": "HH:MM", "hora_termino": "HH:MM", "embarque": "...", "tanque_at": "..."}"""

            respuesta_texto = ""
            try:
                pdf_bytes_envio = factura_file.getvalue() if (factura_file and factura_file.type == "application/pdf") else None
                respuesta_texto = procesar_con_ia_seguro(prompt, texto_pdf, bytes_factura, bytes_tira, api_key, pdf_bytes_envio)
                match = re.search(r"\{.*\}", respuesta_texto, re.DOTALL)
                if match:
                    datos_ia = json.loads(match.group(0), strict=False)
                else:
                    raise ValueError(f"La IA no devolvió un bloque JSON válido. Respuesta cruda: {respuesta_texto}")

                factura_raw = str(datos_ia.get("factura", "")).strip().replace("\n", "")
                if not factura_raw:
                    factura_raw = "SD"
                factura_num = re.sub(r'[\\/*?:"<>| ]', "_", factura_raw)

                uuid = str(datos_ia.get("uuid", "SD")).strip().replace("\n", "")
                vol_facturado = limpiar_flotante(datos_ia.get("litros_facturados"), "litros_facturados")
                vol_descargado = limpiar_flotante(datos_ia.get("litros_descargados"), "litros_descargados")
                fecha_tira = str(datos_ia.get("fecha", "SD")).strip().replace("\n", "")
                hora_inicio = str(datos_ia.get("hora_inicio", "SD")).strip().replace("\n", "")
                hora_termino = str(datos_ia.get("hora_termino", "SD")).strip().replace("\n", "")
                embarque = str(datos_ia.get("embarque", "S/D")).strip().replace("\n", "") or "S/D"
                tanque_at = str(datos_ia.get("tanque_at", "S/D")).strip().replace("\n", "") or "S/D"
                desviacion = abs(vol_facturado - vol_descargado)

                if vol_facturado <= 0 or vol_descargado <= 0:
                    st.warning(f"⚠️ Atención: Verifica la lectura de litros (Facturados: {vol_facturado:,.2f} L | Descargados: {vol_descargado:,.2f} L).")

            except Exception as e:
                st.error(f"❌ Error al extraer/validar datos de la IA: {e}")
                if respuesta_texto:
                    st.code(respuesta_texto, language="json")
                st.stop()

            try:
                folio_str = str(int(folio_input)).zfill(4)
                nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_num}.pdf"
                ruta_pdf = os.path.join(carpeta_destino, nombre_archivo_pdf)

                doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=25, bottomMargin=25)
                elementos, styles = [], getSampleStyleSheet()

                color_rojo = colors.HexColor("#a81c1c")
                color_rosa = colors.HexColor("#f9ebea")
                color_gris = colors.HexColor("#f2f2f2")
                color_gris_claro = colors.HexColor("#f9f9f9")

                estilo_enc_der = ParagraphStyle("EncDer", fontName="Helvetica", fontSize=7.5, leading=10, alignment=2, textColor=colors.HexColor("#222222"))
                estilo_sasisopa = ParagraphStyle("Sasisopa", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=colors.white)
                estilo_bita = ParagraphStyle("Bita", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=color_rojo)
                estilo_label = ParagraphStyle("Label", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8, textColor=colors.black)
                estilo_celda = ParagraphStyle("Celda", fontName="Helvetica", fontSize=6.8, leading=8.8, textColor=colors.black)
                estilo_celda_bold = ParagraphStyle("CeldaBold", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8, textColor=colors.black)
                estilo_celda_centro = ParagraphStyle("CeldaCentro", fontName="Helvetica-Bold", fontSize=7.0, leading=9.0, alignment=1, textColor=colors.black)
                estilo_th_control = ParagraphStyle("ThControl", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8, alignment=1, textColor=colors.white)
                estilo_firma_nombre = ParagraphStyle("FirmaNombre", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, alignment=1, textColor=colors.black)
                estilo_firma_cargo = ParagraphStyle("FirmaCargo", fontName="Helvetica", fontSize=6.5, leading=8.5, alignment=1, textColor=colors.HexColor("#444444"))

                logo_path = buscar_imagen("logo_teika") or buscar_imagen("cabecera")
                img_logo_p1 = RLImage(logo_path, width=95, height=42) if logo_path else Paragraph("<b>[Logo]</b>", styles["Normal"])
                img_logo_p2 = RLImage(logo_path, width=95, height=42) if logo_path else Paragraph("<b>[Logo]</b>", styles["Normal"])

                texto_cabecera_p1 = "<font size=10><b>COMBUSTIBLES BUENOS AIRES S.A. DE C.V.</b></font><br/>CAMPO 4 SN, COLONIA BUENOS AIRES, JANOS, CHIHUAHUA. C.P. 31844."
                t_cabecera_p1 = Table([[img_logo_p1, Paragraph(texto_cabecera_p1, estilo_enc_der)]], colWidths=[110, 442])
                t_cabecera_p1.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('LINEBELOW', (0, 0), (-1, -1), 1.5, color_rojo),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
                ]))
                elementos.extend([t_cabecera_p1, Spacer(1, 8)])

                t_titulos = Table([
                    [Paragraph("SISTEMA DE ADMINISTRACIÓN (SASISOPA) NOM-005-ASEA-2016", estilo_sasisopa)],
                    [Paragraph(f"BITÁCORA OFICIAL DE RECEPCIÓN, DESCARGA Y CONTROL VEEDER-ROOT | FOLIO: {folio_str}", estilo_bita)]
                ], colWidths=[552])
                t_titulos.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, 0), color_rojo),
                    ('BACKGROUND', (0, 1), (0, 1), color_rosa),
                    ('BOX', (0, 0), (-1, -1), 1, color_rojo),
                    ('LINEABOVE', (0, 1), (-1, 1), 0.8, color_rojo),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
                ]))
                elementos.extend([t_titulos, Spacer(1, 6)])

                texto_autotanque = f"Emb: {embarque} | Tq: {tanque_at} | Op: Javier Arturo Garcia"
                t_info = Table([
                    [Paragraph("FACTURA:", estilo_label), Paragraph(f"<b>{factura_raw}</b>", estilo_celda), Paragraph("RFC ESTACIÓN:", estilo_label), Paragraph("CBA140131V12", estilo_celda)],
                    [Paragraph("PERMISO CRE:", estilo_label), Paragraph("PL/3910/EXP/ES/2015", estilo_celda), Paragraph("FOLIO FISCAL:", estilo_label), Paragraph(f"{uuid}", estilo_celda)],
                    [Paragraph("PRODUCTO:", estilo_label), Paragraph(f"<b>REGULAR (MAGNA) ({vol_facturado:,.2f} L)</b>", estilo_celda), Paragraph("PROVEEDOR:", estilo_label), Paragraph("UNEGAS DISTRIBUCION (UDA171106KV9)", estilo_celda)],
                    [Paragraph("AUTOTANQUE:", estilo_label), Paragraph(texto_autotanque, estilo_celda), Paragraph("DESTINO:", estilo_label), Paragraph("Combustibles Buenos Aires", estilo_celda)],
                    [Paragraph("FECHA DESCARGA:", estilo_label), Paragraph(f"{fecha_tira}", estilo_celda), Paragraph("HORARIO (INICIO - FIN):", estilo_label), Paragraph(f"{hora_inicio} a {hora_termino}", estilo_celda)]
                ], colWidths=[95, 181, 105, 171])
                t_info.setStyle(TableStyle([
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('BACKGROUND', (0, 0), (0, -1), color_gris),
                    ('BACKGROUND', (2, 0), (2, -1), color_gris),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5)
                ]))
                elementos.extend([t_info, Spacer(1, 8)])

                registro_vr_html = f"• Verificación de descarga autorizada.<br/>• <b>Aumento Bruto CT: {vol_descargado:,.2f} L</b>"
                estatus_valores_html = f"Facturado: {vol_facturado:,.2f} L<br/>Descargado (Bruto): {vol_descargado:,.2f} L<br/><b>Desviación (Dif): {desviacion:,.2f} L</b>"

                t_control = Table([
                    [Paragraph("PARAMETRO/CONTROL", estilo_th_control), Paragraph("REGISTRO Y VALIDACIÓN VEEDER-ROOT (T1: MAGNA)", estilo_th_control), Paragraph("CUMPLE SASISOPA", estilo_th_control), Paragraph("ESTATUS/VALORES", estilo_th_control)],
                    [Paragraph("CONTROL VEEDER-ROOT", estilo_celda_bold), Paragraph(registro_vr_html, estilo_celda), Paragraph("[X] SÍ &nbsp;&nbsp; [ ] NO", estilo_celda_centro), Paragraph(estatus_valores_html, estilo_celda)]
                ], colWidths=[105, 212, 90, 145])
                t_control.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), color_rojo),
                    ('BACKGROUND', (0, 1), (0, 1), color_gris),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
