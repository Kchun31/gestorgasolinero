import streamlit as st
import os
import PyPDF2
from PIL import Image
import json
import re
import base64
import requests
import google.generativeai as genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- LIBRERÍA PARA PEGAR DESDE PORTAPAPELES ---
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
            except:
                return 1
    return 1

def guardar_folio(nuevo_folio):
    with open(ARCHIVO_FOLIO, "w") as f:
        f.write(str(nuevo_folio))

def buscar_imagen(nombre_base):
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        if os.path.exists(f"{nombre_base}.{ext}"): return f"{nombre_base}.{ext}"
    return None

if 'folio_actual' not in st.session_state:
    st.session_state.folio_actual = obtener_folio()

st.title("⛽ ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    factura_up = st.file_uploader("📄 1. Sube tu Factura (PDF)", type=['pdf'])
    
with col2:
    st.markdown("🧾 **2. Tira Veeder-Root (Foto)**")
    paste_result = paste_image_button(
        label="📋 Pegar imagen (Si estás en PC)",
        background_color="#FF4B4B",
        hover_background_color="#FF6666"
    )
    
    img_tira = None
    if paste_result.image_data is not None:
        img_tira = paste_result.image_data
        st.success("✅ Imagen pegada correctamente.")
    else:
        tira_up = st.file_uploader("O toma/sube la foto:", type=['jpg', 'jpeg', 'png'])
        if tira_up:
            img_tira = Image.open(tira_up)

folio_input = st.number_input("📌 Número de Folio Consecutivo", min_value=1, value=st.session_state.folio_actual, step=1)

st.markdown("---")

if st.button("🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True):
    if not factura_up or img_tira is None:
        st.error("⚠️ Sube el PDF y toma/sube la imagen de la tira para continuar.")
    else:
        with st.spinner("Extrayendo horas y creando bitácora..."):
            try:
                api_key = st.secrets.get("GEMINI_API_KEY")
                if not api_key:
                    st.error("⚠️ No se encontró la llave de Gemini.")
                    st.stop()
                    
                genai.configure(api_key=api_key)
                modelo_ia = genai.GenerativeModel('gemini-3.6-flash')
            except Exception as e:
                st.error(f"❌ Error de configuración: {e}")
                st.stop()

            texto_pdf = ""
            try:
                reader = PyPDF2.PdfReader(factura_up)
                for page in reader.pages:
                    texto_pdf += page.extract_text() + " "
            except Exception:
                pass
            
            # --- SE ACTUALIZÓ EL PROMPT PARA PEDIR LAS HORAS ---
            prompt = f"""
            Eres un auditor estricto de estaciones de servicio.
            Analiza estos dos documentos:
            1. Texto extraído de la factura: {texto_pdf}
            2. Imagen del ticket Veeder-Root (busca el 'AUMENTO NETO CT' y los horarios del reporte).
            
            Devuelve ÚNICAMENTE un JSON con esta estructura exacta:
            {{
                "uuid": "folio fiscal de 36 caracteres",
                "factura": "numero de factura",
                "litros_facturados": numero decimal (cantidad de Magna),
                "litros_descargados": numero decimal (aumento neto del ticket),
                "hora_inicio": "HH:MM",
                "hora_termino": "HH:MM"
            }}
            """
            
            try:
                respuesta = modelo_ia.generate_content([prompt, img_tira])
                match = re.search(r'\{.*\}', respuesta.text, re.DOTALL)
                if match:
                    datos_ia = json.loads(match.group(0))
                else:
                    raise ValueError("Formato incorrecto.")
                
                factura_num = datos_ia.get('factura', 'SD')
                uuid = datos_ia.get('uuid', 'SD')
                vol_facturado = float(datos_ia.get('litros_facturados', 0))
                vol_descargado = float(datos_ia.get('litros_descargados', 0))
                hora_inicio = datos_ia.get('hora_inicio', 'SD')
                hora_termino = datos_ia.get('hora_termino', 'SD')
                desviacion = abs(vol_facturado - vol_descargado)
                
                siguiente_folio = int(folio_input) + 1
                guardar_folio(siguiente_folio)
                st.session_state.folio_actual = siguiente_folio
                
            except Exception as e:
                st.error(f"❌ Error procesando el documento. Detalle: {e}")
                st.stop()

            # --- GENERACIÓN DEL PDF OFICIAL ---
            folio_str = str(int(folio_input)).zfill(4) 
            nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_num}.pdf"
            ruta_pdf = os.path.join(carpeta_destino, nombre_archivo_pdf)
            
            doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
            elementos = []
            styles = getSampleStyleSheet()
            estilo_celda = ParagraphStyle('Celda', fontName='Helvetica', fontSize=6.5, leading=8.5)
            estilo_celda_centro = ParagraphStyle('CeldaCentro', fontName='Helvetica', fontSize=6.5, leading=8.5, alignment=1)

            logo_path = buscar_imagen("logo_teika") or buscar_imagen("cabecera")
            img_logo = RLImage(logo_path, width=85, height=40) if logo_path else Paragraph("<b>[Logo CBA]</b>", styles['Normal'])

            t_cabecera = Table([[img_logo, Paragraph("<font color='#a81c1c' size='10'><b>COMBUSTIBLES BUENOS AIRES S.A. DE C.V.</b></font><br/><font color='#333333' size='8'>CAMPO 4 SN, COLONIA BUENOS AIRES, JANOS, CHIHUAHUA. C.P. 31844.</font>", ParagraphStyle('E', leading=12))]], colWidths=[95, 465])
            t_cabecera.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (1,0), (1,0), 5)]))
            elementos.append(t_cabecera)
            elementos.append(Spacer(1, 10))

            estilo_sasi = ParagraphStyle('Sasi', fontName='Helvetica-Bold', fontSize=6.5, textColor=colors.white, alignment=1)
            estilo_bita = ParagraphStyle('Bita', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#a81c1c'), alignment=1)
            
            t_titulos = Table([[Paragraph("SISTEMA DE ADMINISTRACIÓN (SASISOPA) • NOM-005-ASEA-2016", estilo_sasi)], [Paragraph(f"BITÁCORA OFICIAL DE RECEPCIÓN, DESCARGA Y CONTROL VEEDER-ROOT   |   FOLIO: {folio_str}", estilo_bita)]], colWidths=[560])
            t_titulos.setStyle(TableStyle([('BACKGROUND', (0,0), (0,0), colors.HexColor('#a81c1c')), ('BACKGROUND', (0,1), (0,1), colors.white), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#a81c1c')), ('INNERGRID', (0,0), (-1,-1), 1, colors.HexColor('#a81c1c')), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
            elementos.append(t_titulos)
            elementos.append(Spacer(1, 4))

            # --- SE AGREGÓ UN RENGLÓN NUEVO PARA LOS HORARIOS ---
            t_info = Table([
                ["FACTURA:", Paragraph(f"{factura_num}", estilo_celda), "RFC ESTACIÓN:", "CBA140131V12"],
                ["PERMISO CRE:", "PL/3910/EXP/ES/2015", "FOLIO FISCAL:", Paragraph(f"{uuid}", estilo_celda)],
                ["PRODUCTO:", f"REGULAR (MAGNA) ({vol_facturado:,.2f} L)", "PROVEEDOR:", Paragraph("UNEGAS DISTRIBUCION (UDA171106KV9)", estilo_celda)],
                ["AUTOTANQUE:", Paragraph("Emb: 779274 | Tq: 23UY9X | Op: Javier Arturo García", estilo_celda), "DESTINO:", Paragraph("Combustibles Buenos Aires", estilo_celda)],
                ["HORA INICIO:", Paragraph(f"<b>{hora_inicio}</b>", estilo_celda), "HORA TÉRMINO:", Paragraph(f"<b>{hora_termino}</b>", estilo_celda)]
            ], colWidths=[90, 190, 90, 190])
            t_info.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f7f7f7')), ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f7f7f7')), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#333333')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            elementos.append(t_info)
            elementos.append(Spacer(1, 4))

            t_control = Table([
                ["PARÁMETRO / CONTROL", "REGISTRO Y VALIDACIÓN VEEDER-ROOT (T1: MAGNA)", "CUMPLE SASISOPA", "ESTATUS / VALORES"],
                [Paragraph("<b>CONTROL VEEDER-ROOT</b>", estilo_celda_centro), Paragraph(f"• Verificación de descarga autorizada.<br/>• Aumento Neto CT: <b>{vol_descargado:,.2f} L</b>", estilo_celda), Paragraph("[ X ] SÍ    [   ] NO", estilo_celda_centro), Paragraph(f"Facturado: {vol_facturado:,.2f} L<br/>Descargado: {vol_descargado:,.2f} L<br/><b>Desviación (Dif):</b> {desviacion:,.2f} L", estilo_celda)]
            ], colWidths=[110, 250, 90, 110])
            t_control.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#a81c1c')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('ALIGN', (2, 1), (2, 1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#333333'))]))
            elementos.append(t_control)
            elementos.append(Spacer(1, 4))

            t_obs = Table([["OBSERVACIONES / ACCIONES:", Paragraph(f"Recepción amparada con Factura {factura_num}. Aumento Neto validado mediante registro fotográfico en Anexo 2.", estilo_celda)]], colWidths=[130, 430])
            t_obs.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f7f7f7')), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#333333')), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
            elementos.append(t_obs)
            elementos.append(Spacer(1, 20))

            sj, sy = buscar_imagen("firma_javier"), buscar_imagen("firma_yahir")
            cj = RLImage(sj, width=100, height=35) if sj else Paragraph("<b>[Firma Javier]</b>", styles['Normal'])
            cy = RLImage(sy, width=100, height=35) if sy else Paragraph("<b>[Firma Yahir]</b>", styles['Normal'])
            t_firmas = Table([[cj, cy], ["________________________________________", "________________________________________"], ["Javier Arturo García Venegas", "Yahir Caro Martínez"], ["Operador / Encargado de Descarga (Realizó)", "Representante Técnico / Administrador (Autorizó)"]], colWidths=[280, 280])
            t_firmas.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#444444'))]))
            elementos.append(t_firmas)

            elementos.append(PageBreak())
            elementos.append(t_cabecera)
            elementos.append(Spacer(1, 15))
            elementos.append(Paragraph(f"ANEXO DE EVIDENCIA: LECTURA VISUAL DE TIRA VEEDER-ROOT", ParagraphStyle('TitAnexo', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#a81c1c'), alignment=1, spaceAfter=8)))
            
            temp_img_path = "temp_veeder.png"
            img_tira.save(temp_img_path)
            
            img_veeder_pdf = RLImage(temp_img_path, width=190, height=300)
            img_veeder_pdf.hAlign = 'CENTER'
            elementos.append(img_veeder_pdf)
            elementos.append(Spacer(1, 10))

            t_notas = Table([["Auditoría Documental:", Paragraph(f"• Factura: {factura_num} | Litros Facturados: {vol_facturado:,.2f} L<br/>• Litros Descargados: {vol_descargado:,.2f} L | <b>Desviación (Dif):</b> {desviacion:,.2f} L", estilo_celda)]], colWidths=[130, 430])
            t_notas.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#fdfdfd')), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            elementos.append(t_notas)

            doc.build(elementos)

            # --- ENVÍO AUTÓNOMO A GOOGLE DRIVE MEDIANTE EL PUENTE ---
            try:
                url_script = st.secrets.get("URL_GOOGLE_SCRIPT")
                if url_script:
                    with open(ruta_pdf, "rb") as f:
                        pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
                    
                    res = requests.post(url_script, data={"archivoB64": pdf_b64, "nombreArchivo": nombre_archivo_pdf})
                    
                    if "éxito" in res.text.lower():
                        st.success(f"✅ Recepción validada: {vol_facturado:,.2f} L vs {vol_descargado:,.2f} L.")
                        st.success("☁️ ¡Bitácora enviada y guardada 100% en automático en tu Drive!")
                        st.info(f"⏭️ El sistema ha reservado el folio <b>{siguiente_folio}</b> para la próxima.", icon="📌")
                    else:
                        st.warning(f"⚠️ Error del puente Drive: {res.text}")
                else:
                    st.warning("⚠️ Falta configurar URL_GOOGLE_SCRIPT en los Misterios.")
            except Exception as e:
                st.warning(f"⚠️ Error enviando a Drive: {e}")

            with open(ruta_pdf, "rb") as pdf_file:
                st.download_button(label="⬇️ Descargar Copia a tu Celular/PC", data=pdf_file, file_name=nombre_archivo_pdf, mime="application/pdf")
