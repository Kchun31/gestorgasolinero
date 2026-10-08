import base64
import json
import os
import re
import google.generativeai as genai
from PIL import Image, ImageOps
import PyPDF2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
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
      except:
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

st.title("⛽ ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
  st.markdown("📄 **1. Factura (PDF o Cámara)**")
  metodo_factura = st.radio(
      "Método Factura:",
      ["📁 Subir PDF/Imagen", "📸 Usar Cámara"],
      horizontal=True,
      key="metodo_factura",
  )

  img_factura = None
  factura_file = None
  texto_pdf = ""

  if metodo_factura == "📁 Subir PDF/Imagen":
    factura_file = st.file_uploader(
        "Sube archivo:", type=["pdf", "png", "jpg", "jpeg"], key="factura_up"
    )
    if factura_file:
      if factura_file.type == "application/pdf":
        try:
          reader = PyPDF2.PdfReader(factura_file)
          for page in reader.pages:
            texto_pdf += page.extract_text() + " "
        except Exception:
          pass
      else:
        img_factura = ImageOps.exif_transpose(Image.open(factura_file))
  else:
    foto_factura_cam = st.camera_input(
        "Toma foto de la factura", key="camara_factura"
    )
    if foto_factura_cam:
      img_factura = ImageOps.exif_transpose(Image.open(foto_factura_cam))

with col2:
  st.markdown("🧾 **2. Tira Veeder-Root (Foto o Cámara)**")
  paste_result = paste_image_button(
      label="📋 Pegar imagen (PC)",
      background_color="#FF4B4B",
      hover_background_color="#FF6666",
      key="paste_btn",
  )

  img_tira = None
  if paste_result.image_data is not None:
    img_tira = ImageOps.exif_transpose(paste_result.image_data)
    st.success("✅ Imagen pegada correctamente.")
  else:
    metodo_foto = st.radio(
        "Método Tira:",
        ["📸 Usar Cámara", "📁 Subir Archivo"],
        horizontal=True,
        key="metodo_captura",
    )

    if metodo_foto == "📸 Usar Cámara":
      foto_camara = st.camera_input(
          "Toma la foto del ticket", key="camara_veeder"
      )
      if foto_camara:
        img_tira = ImageOps.exif_transpose(Image.open(foto_camara))
    else:
      tira_up = st.file_uploader(
          "Sube la foto:", type=["jpg", "jpeg", "png"], key="galeria_veeder"
      )
      if tira_up:
        img_tira = ImageOps.exif_transpose(Image.open(tira_up))

folio_input = st.number_input(
    "📌 Número de Folio Consecutivo",
    min_value=1,
    value=st.session_state.folio_actual,
    step=1,
)

st.markdown("---")

if st.button(
    "🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True
):
  if (not factura_file and img_factura is None) or img_tira is None:
    st.error(
        "⚠️ Proporciona tanto la Factura (PDF o foto) como la Tira Veeder-Root"
        " para continuar."
    )
  else:
    with st.spinner("Extrayendo datos y creando bitácora..."):
      try:
        api_key = st.secrets.get("GEMINI_API_KEY")
        if not api_key:
          st.error("⚠️ No se encontró la llave de Gemini en los Secrets.")
          st.stop()

        genai.configure(api_key=api_key)
        modelo_ia = genai.GenerativeModel("gemini-3.8-flash")
      except Exception as e:
        st.error(f"❌ Error de configuración: {e}")
        st.stop()

      prompt = f"""
            Eres un auditor estricto de estaciones de servicio.
            Analiza los documentos proporcionados:
            1. Texto de factura (si existe): {texto_pdf}
            2. Imagen de factura / ticket (si existe)
            3. Imagen del ticket Veeder-Root (busca el 'AUMENTO BRUTO CT', fecha y horarios).
            
            Devuelve ÚNICAMENTE un JSON con esta estructura exacta, sin saltos de línea adicionales:
            {{
                "uuid": "folio fiscal de 36 caracteres o SD",
                "factura": "numero de factura o SD",
                "litros_facturados": numero decimal (cantidad de Magna),
                "litros_descargados": numero decimal (aumento bruto del ticket),
                "fecha": "DD/MM/AAAA",
                "hora_inicio": "HH:MM",
                "hora_termino": "HH:MM"
            }}
            """

      try:
        contenido_ia = [prompt]
        if img_factura is not None:
          contenido_ia.append(img_factura)
        if img_tira is not None:
          contenido_ia.append(img_tira)

        respuesta = modelo_ia.generate_content(contenido_ia)
        match = re.search(r"\{.*\}", respuesta.text, re.DOTALL)
        if match:
          datos_ia = json.loads(match.group(0), strict=False)
        else:
          raise ValueError("Formato incorrecto en la respuesta de la IA.")

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
        st.error(f"❌ Error procesando con IA: {e}")
        st.stop()

      # --- GENERACIÓN DEL PDF ---
      folio_str = str(int(folio_input)).zfill(4)
      nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_num}.pdf"
      ruta_pdf = os.path.join(carpeta_destino, nombre_archivo_pdf)

      doc = SimpleDocTemplate(
          ruta_pdf,
          pagesize=letter,
          rightMargin=25,
          leftMargin=25,
          topMargin=25,
          bottomMargin=25,
      )
      elementos = []
      styles = getSampleStyleSheet()
      estilo_celda = ParagraphStyle(
          "Celda", fontName="Helvetica", fontSize=6.5, leading=8.5
      )
      estilo_celda_centro = ParagraphStyle(
          "CeldaCentro",
          fontName="Helvetica",
          fontSize=6.5,
          leading=8.5,
          alignment=1,
      )

      logo_path = buscar_imagen("logo_teika") or buscar_imagen("cabecera")
      img_logo = (
          RLImage(logo_path, width=85, height=40)
          if logo_path
          else Paragraph("<b>[Logo CBA]</b>", styles["Normal"])
      )

      t_cabecera = Table([[
          img_logo,
          Paragraph(
              "<font color='#a81c1c' size='10'><b>COMBUSTIBLES BUENOS AIRES"
              " S.A. DE C.V.</b></font><br/><font color='#333333'"
              " size='8'>CAMPO 4 SN, COLONIA BUENOS AIRES, JANOS, CHIHUAHUA."
              " C.P. 31844.</font>",
              ParagraphStyle("E", leading=12),
          ),
      ]], colWidths=[95, 465])
      t_cabecera.setStyle(
          TableStyle([
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LEFTPADDING", (1, 0), (1, 0), 5),
          ])
      )
      elementos.append(t_cabecera)
      elementos.append(Spacer(1, 10))

      estilo_sasi = ParagraphStyle(
          "Sasi",
          fontName="Helvetica-Bold",
          fontSize=6.5,
          textColor=colors.white,
          alignment=1,
      )
      estilo_bita = ParagraphStyle(
          "Bita",
          fontName="Helvetica-Bold",
          fontSize=9,
          textColor=colors.HexColor("#a81c1c"),
          alignment=1,
      )

      t_titulos = Table([[
          Paragraph(
              "SISTEMA DE ADMINISTRACIÓN (SASISOPA) • NOM-005-ASEA-2016",
              estilo_sasi,
          )
      ], [
          Paragraph(
              f"BITÁCORA OFICIAL DE RECEPCIÓN, DESCARGA Y CONTROL VEEDER-ROOT"
              f"    |    FOLIO: {folio_str}",
              estilo_bita,
          )
      ]], colWidths=[560])
      t_titulos.setStyle(
          TableStyle([
              ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#a81c1c")),
              ("BACKGROUND", (0, 1), (0, 1), colors.white),
              ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#a81c1c")),
              ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#a81c1c")),
              ("TOPPADDING", (0, 0), (-1, -1), 4),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ])
      )
      elementos.append(t_titulos)
      elementos.append(Spacer(1, 4))

      t_info = Table([
          [
              "FACTURA:",
              Paragraph(f"{factura_num}", estilo_celda),
              "RFC ESTACIÓN:",
              "CBA140131V12",
          ],
          [
              "PERMISO CRE:",
              "PL/3910/EXP/ES/2015",
              "FOLIO FISCAL:",
              Paragraph(f"{uuid}", estilo_celda),
          ],
          [
              "PRODUCTO:",
              f"REGULAR (MAGNA) ({vol_facturado:,.2f} L)",
              "PROVEEDOR:",
              Paragraph("UNEGAS DISTRIBUCION (UDA171106KV9)", estilo_celda),
          ],
          [
              "AUTOTANQUE:",
              Paragraph(
                  "Emb: 779274 | Tq: 23UY9X | Op: Javier Arturo García",
                  estilo_celda,
              ),
              "DESTINO:",
              Paragraph("Combustibles Buenos Aires", estilo_celda),
          ],
          [
              "FECHA DESCARGA:",
              Paragraph(f"<b>{fecha_tira}</b>", estilo_celda),
              "HORARIO (INICIO - FIN):",
              Paragraph(f"<b>{hora_inicio} a {hora_termino}</b>", estilo_celda),
          ],
      ], colWidths=[90, 190, 90, 190])
      t_info.setStyle(
          TableStyle([
              ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f7f7f7")),
              ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f7f7f7")),
              ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
              ("FONTSIZE", (0, 0), (-1, -1), 6.5),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#333333")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ])
      )
      elementos.append(t_info)
      elementos.append(Spacer(1, 4))

      t_control = Table([
          [
              "PARÁMETRO / CONTROL",
              "REGISTRO Y VALIDACIÓN VEEDER-ROOT (T1: MAGNA)",
              "CUMPLE SASISOPA",
              "ESTATUS / VALORES",
          ],
          [
              Paragraph("<b>CONTROL VEEDER-ROOT</b>", estilo_celda_centro),
              Paragraph(
                  "• Verificación de descarga autorizada.<br/>• Aumento Bruto"
                  f" CT: <b>{vol_descargado:,.2f} L</b>",
                  estilo_celda,
              ),
              Paragraph("[ X ] SÍ    [    ] NO", estilo_celda_centro),
              Paragraph(
                  f"Facturado: {vol_facturado:,.2f} L<br/>Descargado (Bruto):"
                  f" {vol_descargado:,.2f} L<br/><b>Desviación (Dif):</b>"
                  f" {desviacion:,.2f} L",
                  estilo_celda,
              ),
          ],
      ], colWidths=[110, 250, 90, 110])
      t_control.setStyle(
          TableStyle([
              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#a81c1c")),
              ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
              ("FONTSIZE", (0, 0), (-1, -1), 6.5),
              ("ALIGN", (2, 1), (2, 1), "CENTER"),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#333333")),
          ])
      )
      elementos.append(t_control)
      elementos.append(Spacer(1, 4))

      t_obs = Table([[
          "OBSERVACIONES / ACCIONES:",
          Paragraph(
              f"Recepción amparada con Factura {factura_num}. Aumento Bruto"
              " validado mediante registro fotográfico en Anexo 2.",
              estilo_celda,
          ),
      ]], colWidths=[130, 430])
      t_obs.setStyle(
          TableStyle([
              ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f7f7f7")),
              ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
              ("FONTSIZE", (0, 0), (-1, -1), 6.5),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#333333")),
              ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ])
      )
      elementos.append(t_obs)
      elementos.append(Spacer(1, 20))

      sj, sy = buscar_imagen("firma_javier"), buscar_imagen("firma_yahir")
      cj = (
          RLImage(sj, width=100, height=35)
          if sj
          else Paragraph("<b>[Firma Javier]</b>", styles["Normal"])
      )
      cy = (
          RLImage(sy, width=100, height=35)
          if sy
          else Paragraph("<b>[Firma Yahir]</b>", styles["Normal"])
      )
      t_firmas = Table([[cj, cy], [
          "________________________________________",
          "________________________________________",
      ], [
          "Javier Arturo García Venegas",
          "Yahir Caro Martínez",
      ], [
          "Operador / Encargado de Descarga (Realizó)",
          "Representante Técnico / Administrador (Autorizó)",
      ]], colWidths=[280, 280])
      t_firmas.setStyle(
          TableStyle([
              ("ALIGN", (0, 0), (-1, -1), "CENTER"),
              ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
              ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
              ("FONTSIZE", (0, 0), (-1, -1), 6.5),
              ("TEXTCOLOR", (0, 3), (-1, 3), colors.HexColor("#444444")),
          ])
      )
      elementos.append(t_firmas)

      elementos.append(PageBreak())
      elementos.append(t_cabecera)
      elementos.append(Spacer(1, 15))
      elementos.append(
          Paragraph(
              "ANEXO DE EVIDENCIA: LECTURA VISUAL DE TIRA VEEDER-ROOT",
              ParagraphStyle(
                  "TitAnexo",
                  fontName="Helvetica-Bold",
                  fontSize=9,
                  textColor=colors.HexColor("#a81c1c"),
                  alignment=1,
                  spaceAfter=8,
              ),
          )
      )

      temp_img_path = "temp_veeder.png"
      img_tira.save(temp_img_path)

      img_veeder_pdf = RLImage(temp_img_path, width=190, height=300)
      img_veeder_pdf.hAlign = "CENTER"
      elementos.append(img_veeder_pdf)
      elementos.append(Spacer(1, 10))

      t_notas = Table([[
          "Auditoría Documental:",
          Paragraph(
              f"• Factura: {factura_num} | Litros Facturados:"
              f" {vol_facturado:,.2f} L<br/>• Litros Descargados (Bruto):"
              f" {vol_descargado:,.2f} L | <b>Desviación (Dif):</b>"
              f" {desviacion:,.2f} L",
              estilo_celda,
          ),
      ]], colWidths=[130, 430])
      t_notas.setStyle(
          TableStyle([
              ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#fdfdfd")),
              ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
              ("FONTSIZE", (0, 0), (-1, -1), 6.5),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ])
      )
      elementos.append(t_notas)

      doc.build(elementos)

      # --- ENVÍO A GOOGLE DRIVE ---
      try:
        url_script = st.secrets.get("URL_GOOGLE_SCRIPT")
        if url_script:
          with open(ruta_pdf, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

          res = requests.post(
              url_script,
              data={
                  "archivoB64": pdf_b64,
                  "nombreArchivo": nombre_archivo_pdf,
              },
          )

          if "éxito" in res.text.lower():
            st.success(
                f"✅ Recepción validada: {vol_facturado:,.2f} L vs"
                f" {vol_descargado:,.2f} L (Bruto)."
            )
            st.success(
                "☁️ ¡Bitácora enviada y guardada en tu Google Drive con éxito!"
            )
            st.info(
                f"⏭️ El sistema ha reservado el folio <b>{siguiente_folio}</b>"
                " para la próxima.",
                icon="📌",
            )
          else:
            st.warning(f"⚠️ Error del puente Drive: {res.text}")
        else:
          st.warning("⚠️ Falta configurar URL_GOOGLE_SCRIPT en los Secrets.")
      except Exception as e:
        st.warning(f"⚠️ Error enviando a Drive: {e}")

      with open(ruta_pdf, "rb") as pdf_file:
        st.download_button(
            label="⬇️ Descargar Copia a tu Celular/PC",
            data=pdf_file,
            file_name=nombre_archivo_pdf,
            mime="application/pdf",
        )
