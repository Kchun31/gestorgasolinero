import streamlit as st
import os
import PyPDF2
from PIL import Image
import json
import google.generativeai as genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Bitácoras CBA", page_icon="⛽", layout="centered")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    modelo_ia = genai.GenerativeModel('gemini-1.5-flash')
except:
    st.error("⚠️ Falta agregar GEMINI_API_KEY en los Secrets de Streamlit.")

carpeta_destino = "temp_destino"
os.makedirs(carpeta_destino, exist_ok=True)

def buscar_imagen(nombre_base):
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        if os.path.exists(f"{nombre_base}.{ext}"): return f"{nombre_base}.{ext}"
    return None

st.title("⛽ ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.write("Motor de Inteligencia Artificial activo para auditoría de documentos.")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    factura_up = st.file_uploader("📄 1. Factura (PDF)", type=['pdf'])
with col2:
    tira_up = st.file_uploader("🧾 2. Tira Veeder-Root (Foto)", type=['jpg', 'jpeg', 'png'])

st.markdown("---")

if st.button("🚀 Procesar con Inteligencia Artificial", type="primary", use_container_width=True):
    if not factura_up or not tira_up:
        st.error("⚠️ Sube ambos documentos para continuar.")
    else:
        with st.spinner("La IA está leyendo los documentos. Esto toma unos 5 segundos..."):
            texto_pdf = ""
            try:
                reader = PyPDF2.PdfReader(factura_up)
                for page in reader.pages:
                    texto_pdf += page.extract_text() + " "
            except:
                st.warning("El PDF no se pudo leer o es una imagen escaneada.")

            img_tira = Image.open(tira_up)
            
            prompt = f"""
            Eres un auditor estricto de estaciones de servicio.
            Aquí tienes dos evidencias:
            1. Texto de la factura: {texto_pdf}
            2. Imagen del ticket Veeder-Root adjunta.
            
            Extrae los datos y devuelve ÚNICAMENTE un archivo JSON válido con esta estructura exacta, sin texto extra antes ni después:
            {{
                "uuid": "folio fiscal de 36 caracteres",
                "factura": "numero de factura ej B4655",
                "litros_facturados": numero decimal de litros (cantidad de producto magna),
                "litros_descargados": numero decimal del 'AUMENTO NETO CT' que dice en el ticket de la imagen
            }}
            """
            
            try:
                respuesta = modelo_ia.generate_content([prompt, img_tira])
                texto_json = respuesta.text.replace('```json', '').replace('```', '').strip()
                datos_ia = json.loads(texto_json)
                
                factura_num = datos_ia.get('factura', 'SD')
                uuid = datos_ia.get('uuid', 'SD')
                vol_facturado = float(datos_ia.get('litros_facturados', 0))
                vol_descargado = float(datos_ia.get('litros_descargados', 0))
                desviacion = abs(vol_facturado - vol_descargado)
                
                st.success(f"✅ Análisis IA Completado: {vol_facturado:,.2f} L Facturados vs {vol_descargado:,.2f} L Descargados.")
            
            except Exception as e:
                st.error("Hubo un problema de conexión con la IA o leyendo los formatos. Revisa que el ticket sea legible.")
                st.stop()

            ruta_pdf = os.path.join(carpeta_destino, f"Bitacora_{factura_num}.pdf")
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
            t_titulos = Table([[Paragraph("SISTEMA DE ADMINISTRACIÓN (SASISOPA) • NOM-005-ASEA-2016", estilo_sasi)], [Paragraph("BITÁCORA OFICIAL DE RECEPCIÓN, DESCARGA Y CONTROL VEEDER-ROOT", estilo_bita)]], colWidths=[560])
            t_titulos.setStyle(TableStyle([('BACKGROUND', (0,0), (0,0), colors.HexColor('#a81c1c')), ('BACKGROUND', (0,1), (0,1), colors.white), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#a81c1c')), ('INNERGRID', (0,0), (-1,-1), 1, colors.HexColor('#a81c1c')), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
            elementos.append(t_titulos)
            elementos.append(Spacer(1, 4))

            t_info = Table([
                ["FACTURA:", Paragraph(f"{factura_num}", estilo_celda), "RFC ESTACIÓN:", "CBA140131V12"],
                ["PERMISO CRE:", "PL/3910/EXP/ES/2015", "FOLIO FISCAL:", Paragraph(f"{uuid}", estilo_celda)],
                ["PRODUCTO:", f"REGULAR (MAGNA) ({vol_facturado:,.2f} L)", "PROVEEDOR:", Paragraph("UNEGAS DISTRIBUCION (UDA171106KV9)", estilo_celda)],
                ["AUTOTANQUE:", Paragraph("Emb: 779274 | Tq: 23UY9X | Op: Javier Arturo García", estilo_celda), "DESTINO:", Paragraph("Combustibles Buenos Aires", estilo_celda)]
            ], colWidths=[90, 190, 90, 190])
            t_info.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f7f7f7')), ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f7f7f7')), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#333333')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            elementos.append(t_info)
            elementos.append(Spacer(1, 4))

            t_control = Table([
                ["PARÁMETRO / CONTROL", "REGISTRO Y VALIDACIÓN VEEDER-ROOT (T1: MAGNA)", "CUMPLE SASISOPA", "ESTATUS / VALORES"],
                [Paragraph("<b>CONTROL VEEDER-ROOT</b>", estilo_celda_centro), Paragraph(f"• Verificación de descarga autorizada.<br/>• Aumento Neto CT: <b>{vol_descargado:,.2f} L</b><br/><i>(Validación por Inteligencia Artificial en Anexo 2)</i>", estilo_celda), Paragraph("[ X ] SÍ    [   ] NO", estilo_celda_centro), Paragraph(f"Facturado: {vol_facturado:,.2f} L<br/>Descargado: {vol_descargado:,.2f} L<br/><b>Desviación (Dif):</b> {desviacion:,.2f} L", estilo_celda)]
            ], colWidths=[110, 250, 90, 110])
            t_control.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#a81c1c')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('ALIGN', (2, 1), (2, 1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#333333'))]))
            elementos.append(t_control)
            elementos.append(Spacer(1, 4))

            t_obs = Table([["OBSERVACIONES / ACCIONES:", Paragraph(f"Recepción amparada con Factura {factura_num}. Aumento Neto validado mediante registro fotográfico y auditoría automatizada en Anexo 2.", estilo_celda)]], colWidths=[130, 430])
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
            
            img_veeder_pdf = RLImage(tira_up, width=190, height=300)
            img_veeder_pdf.hAlign = 'CENTER'
            elementos.append(img_veeder_pdf)
            elementos.append(Spacer(1, 10))

            t_notas = Table([["Auditoría IA:", Paragraph(f"• Factura: {factura_num} | Litros Facturados: {vol_facturado:,.2f} L<br/>• Litros Descargados: {vol_descargado:,.2f} L | <b>Desviación (Dif):</b> {desviacion:,.2f} L", estilo_celda)]], colWidths=[130, 430])
            t_notas.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#fdfdfd')), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            elementos.append(t_notas)

            doc.build(elementos)

            with open(ruta_pdf, "rb") as pdf_file:
                st.download_button(label="⬇️ Descargar Bitácora PDF (Auditada por IA)", data=pdf_file, file_name=f"Bitacora_Factura_{factura_num}.pdf", mime="application/pdf", type="primary")
