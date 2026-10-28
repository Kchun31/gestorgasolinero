import base64, io, json, os, re, time, requests
from PIL import Image, ImageOps
import PyPDF2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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

def limpiar_flotante(valor, campo):
    if valor is None or str(valor).strip() == "":
        raise ValueError(f"El dato '{campo}' llegó vacío desde la IA.")
    m = re.findall(r"[-+]?\d*\.?\d+", str(valor).replace(",", ""))
    if not m:
        raise ValueError(f"El dato '{campo}' no es numérico: '{valor}'")
    num = float(m[0])
    if 10.0 <= num <= 99.999 and "." in m[0] and len(m[0].split(".")[1]) == 3:
        num *= 1000.0
    return num

def optimizar_imagen_b64(img_bytes):
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("RGB")
    img.thumbnail((850, 850), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=72, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

if "folio_actual" not in st.session_state:
    st.session_state.folio_actual = obtener_folio()

st.title("⛽ ERP | Recepción y Descargas")
st.subheader("Combustibles Buenos Aires S.A. de C.V.")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**1. Factura (PDF o Cámara)**")
    metodo_factura = st.radio("Método Factura:", ["Subir PDF/Imagen", "Usar Cámara"], horizontal=True, key="metodo_factura")
    img_factura, factura_file, texto_pdf, bytes_factura, bytes_pdf_raw = None, None, "", None, None

    if metodo_factura == "Subir PDF/Imagen":
        factura_file = st.file_uploader("Sube archivo:", type=["pdf", "png", "jpg", "jpeg"], key="factura_up")
        if factura_file:
            if factura_file.type == "application/pdf":
                try:
                    bytes_pdf_raw = factura_file.getvalue()
                    reader = PyPDF2.PdfReader(io.BytesIO(bytes_pdf_raw))
                    for page in reader.pages:
                        texto_pdf += (page.extract_text() or "") + "\n"
                except Exception as e_pdf:
                    st.warning(f"Aviso lectura PDF: {e_pdf}")
            else:
                bytes_factura = factura_file.getvalue()
                img_factura = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_factura)))
    else:
        foto_factura_cam = st.camera_input("Toma foto de la factura", key="camara_factura")
        if foto_factura_cam:
            bytes_factura = foto_factura_cam.getvalue()
            img_factura = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_factura)))

with col2:
    st.markdown("**2. Tira Veeder-Root (Foto o Cámara)**")
    paste_result = paste_image_button(label="📋 Pegar imagen (PC)", background_color="#FF4B4B", hover_background_color="#FF6666", key="paste_btn")
    img_tira, bytes_tira = None, None

    if paste_result.image_data is not None:
        img_tira = ImageOps.exif_transpose(paste_result.image_data)
        buf = io.BytesIO()
        img_tira.convert("RGB").save(buf, format="JPEG", quality=85)
        bytes_tira = buf.getvalue()
        st.success("✅ Imagen pegada correctamente.")
    else:
        metodo_foto = st.radio("Método Tira:", ["Usar Cámara", "Subir Archivo"], horizontal=True, key="metodo_captura")
        if metodo_foto == "Usar Cámara":
            foto_camara = st.camera_input("Toma la foto del ticket", key="camara_veeder")
            if foto_camara:
                bytes_tira = foto_camara.getvalue()
                img_tira = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_tira)))
        else:
            tira_up = st.file_uploader("Sube la foto:", type=["jpg", "jpeg", "png"], key="galeria_veeder")
            if tira_up:
                bytes_tira = tira_up.getvalue()
                img_tira = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes_tira)))

folio_input = st.number_input("📌 Número de Folio Consecutivo", min_value=1, value=st.session_state.folio_actual, step=1)
st.markdown("---")

@st.cache_data(show_spinner=False)
def procesar_con_ia_seguro(prompt_texto, texto_extraido, b_factura, b_tira, api_key, pdf_raw=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key.strip()}"
    parts = [{"text": prompt_texto}]
    if texto_extraido and len(texto_extraido.strip()) > 30:
        parts.append({"text": f"Texto extraído de la factura PDF:\n{texto_extraido}"})
    elif pdf_raw:
        parts.append({"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf_raw).decode("utf-8")}})
    if b_factura:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": optimizar_imagen_b64(b_factura)}})
    if b_tira:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": optimizar_imagen_b64(b_tira)}})

    payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.1}}
    sesion = requests.Session()
    ultimo_err = ""
    for intento in range(3):
        try:
            r = sesion.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=(15, 120))
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif r.status_code in (429, 500, 502, 503, 504):
                ultimo_err = f"HTTP {r.status_code}: {r.text}"
                time.sleep(6 * (intento + 1))
            else:
                raise RuntimeError(f"Error API ({r.status_code}): {r.text}")
        except requests.exceptions.RequestException as e_req:
            ultimo_err = str(e_req)
            if intento < 2:
                time.sleep(5)
            else:
                raise RuntimeError(f"Fallo de red tras 3 intentos de 120s: {ultimo_err}")
    raise RuntimeError(ultimo_err)

if st.button("🚀 Procesar y Subir a Google Drive", type="primary", use_container_width=True):
    if (not factura_file and img_factura is None) or img_tira is None:
        st.error("Proporciona tanto la Factura como la Tira Veeder-Root para continuar.")
    else:
        with st.spinner("Analizando con precisión quirúrgica mediante IA..."):
            api_key = st.secrets.get("GEMINI_API_KEY")
            if not api_key:
                st.error("❌ Llave GEMINI_API_KEY no encontrada en Secrets.")
                st.stop()

            prompt = """Eres un auditor experto en estaciones de servicio en México (NOM-005-ASEA-2016).
Extrae de la FACTURA y de la TIRA VEEDER-ROOT los siguientes datos exactos:
1. FACTURA:
- "factura": Folio de la factura (ej. "B4705", "B4727").
- "uuid": Folio Fiscal UUID completo.
- "litros_facturados": Cantidad numérica de LITROS facturados del combustible (ej. 43628.00; ignora importes en pesos). Prohibido devolver 0.
- "embarque": Número de embarque (ej. "779274") o "S/D".
- "tanque_at": Clave de autotanque/tonel (ej. "23UY9X") o "S/D".
2. TIRA VEEDER-ROOT:
- "litros_descargados": Valor numérico de la línea 'AUMENTO BRUTO' (ej. 'AUMENTO BRUTO = 43285' o '43342', sin importar si dice T1 o T2). Prohibido devolver 0.
- "fecha": Fecha en formato DD/MM/AAAA (ej. 13-10-26 -> 13/10/2026).
- "hora_inicio": Hora de INICIO AUMENTO (HH:MM).
- "hora_termino": Hora de FIN AUMENTO (HH:MM).
Devuelve ÚNICAMENTE JSON válido:
{"uuid": "...", "factura": "...", "litros_facturados": 0.0, "litros_descargados": 0.0, "fecha": "...", "hora_inicio": "...", "hora_termino": "...", "embarque": "...", "tanque_at": "..."}"""

            respuesta_texto = ""
            try:
                respuesta_texto = procesar_con_ia_seguro(prompt, texto_pdf, bytes_factura, bytes_tira, api_key, bytes_pdf_raw)
                match = re.search(r"\{.*\}", respuesta_texto, re.DOTALL)
                if not match:
                    raise ValueError(f"Respuesta sin JSON válido: {respuesta_texto}")
                datos_ia = json.loads(match.group(0), strict=False)

                uuid_local = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", texto_pdf or "")
                factura_raw = str(datos_ia.get("factura", "SD")).strip().replace("\n", "") or "SD"
                factura_num = re.sub(r'[\\/*?:"<>| ]', "_", factura_raw)
                uuid = str(datos_ia.get("uuid") or (uuid_local.group(0).upper() if uuid_local else "SD")).strip().replace("\n", "")
                vol_facturado = limpiar_flotante(datos_ia.get("litros_facturados"), "litros_facturados")
                vol_descargado = limpiar_flotante(datos_ia.get("litros_descargados"), "litros_descargados")
                fecha_tira = str(datos_ia.get("fecha", "SD")).strip().replace("\n", "")
                hora_inicio = str(datos_ia.get("hora_inicio", "SD")).strip().replace("\n", "")
                hora_termino = str(datos_ia.get("hora_termino", "SD")).strip().replace("\n", "")
                embarque = str(datos_ia.get("embarque", "S/D")).strip().replace("\n", "") or "S/D"
                tanque_at = str(datos_ia.get("tanque_at", "S/D")).strip().replace("\n", "") or "S/D"
                desviacion = abs(vol_facturado - vol_descargado)
            except Exception as e:
                st.error(f"❌ Error IA / Validación de datos: {e}")
                if respuesta_texto:
                    st.code(respuesta_texto)
                st.stop()

            try:
                folio_str = str(int(folio_input)).zfill(4)
                nombre_archivo_pdf = f"Bitacora_Folio_{folio_str}_{factura_num}.pdf"
                ruta_pdf = os.path.join(carpeta_destino, nombre_archivo_pdf)

                doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=25, bottomMargin=25)
                elementos, styles = [], getSampleStyleSheet()
                c_rojo, c_rosa, c_gris = colors.HexColor("#a81c1c"), colors.HexColor("#f9ebea"), colors.HexColor("#f2f2f2")

                s_der = ParagraphStyle("Der", fontName="Helvetica", fontSize=7.5, leading=10, alignment=2)
                s_sas = ParagraphStyle("Sas", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=colors.white)
                s_bit = ParagraphStyle("Bit", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=c_rojo)
                s_lbl = ParagraphStyle("Lbl", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8)
                s_cel = ParagraphStyle("Cel", fontName="Helvetica", fontSize=6.8, leading=8.8)
                s_ctr = ParagraphStyle("Ctr", fontName="Helvetica-Bold", fontSize=7.0, leading=9.0, alignment=1)
                s_thc = ParagraphStyle("Thc", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8, alignment=1, textColor=colors.white)
                s_fnm = ParagraphStyle("Fnm", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, alignment=1)
                s_fcg = ParagraphStyle("Fcg", fontName="Helvetica", fontSize=6.5, leading=8.5, alignment=1, textColor=colors.HexColor("#444444"))

                def P(txt, st_p=s_cel):
                    return Paragraph(str(txt), st_p)

                logo_p = buscar_imagen("logo_teika") or buscar_imagen("cabecera")
                logo1 = RLImage(logo_p, width=95, height=42) if logo_p else P("<b>[Logo]</b>")
                logo2 = RLImage(logo_p, width=95, height=42) if logo_p else P("<b>[Logo]</b>")

                dir_txt = "<font size=10><b>COMBUSTIBLES BUENOS AIRES S.A. DE C.V.</b></font><br/>CAMPO 4 SN, COLONIA BUENOS AIRES, JANOS, CHIHUAHUA. C.P. 31844."
                estilo_cab = TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (1,0), (1,0), 'RIGHT'), ('LINEBELOW', (0,0), (-1,-1), 1.5, c_rojo), ('BOTTOMPADDING', (0,0), (-1,-1), 6)])

                t_cab1 = Table([[logo1, P(dir_txt, s_der)]], colWidths=[110, 442])
                t_cab1.setStyle(estilo_cab)
                elementos.extend([t_cab1, Spacer(1, 8)])

                t_tit = Table([[P("SISTEMA DE ADMINISTRACIÓN (SASISOPA) NOM-005-ASEA-2016", s_sas)], [P(f"BITÁCORA OFICIAL DE RECEPCIÓN, DESCARGA Y CONTROL VEEDER-ROOT | FOLIO: {folio_str}", s_bit)]], colWidths=[552])
                t_tit.setStyle(TableStyle([('BACKGROUND', (0,0), (0,0), c_rojo), ('BACKGROUND', (0,1), (0,1), c_rosa), ('BOX', (0,0), (-1,-1), 1, c_rojo), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
                elementos.extend([t_tit, Spacer(1, 6)])

                aut_txt = f"Emb: {embarque} | Tq: {tanque_at} | Op: Javier Arturo Garcia"
                t_info = Table([
                    [P("FACTURA:", s_lbl), P(f"<b>{factura_raw}</b>"), P("RFC ESTACIÓN:", s_lbl), P("CBA140131V12")],
                    [P("PERMISO CRE:", s_lbl), P("PL/3910/EXP/ES/2015"), P("FOLIO FISCAL:", s_lbl), P(uuid)],
                    [P("PRODUCTO:", s_lbl), P(f"<b>REGULAR (MAGNA) ({vol_facturado:,.2f} L)</b>"), P("PROVEEDOR:", s_lbl), P("UNEGAS DISTRIBUCION (UDA171106KV9)")],
                    [P("AUTOTANQUE:", s_lbl), P(aut_txt), P("DESTINO:", s_lbl), P("Combustibles Buenos Aires")],
                    [P("FECHA DESCARGA:", s_lbl), P(fecha_tira), P("HORARIO (INICIO - FIN):", s_lbl), P(f"{hora_inicio} a {hora_termino}")]
                ], colWidths=[95, 181, 105, 171])
                t_info.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,0), (0,-1), c_gris), ('BACKGROUND', (2,0), (2,-1), c_gris), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('PADDING', (0,0), (-1,-1), 4)]))
                elementos.extend([t_info, Spacer(1, 8)])

                reg_vr = f"• Verificación de descarga autorizada.<br/>• <b>Aumento Bruto CT: {vol_descargado:,.2f} L</b>"
                est_vr = f"Facturado: {vol_facturado:,.2f} L<br/>Descargado (Bruto): {vol_descargado:,.2f} L<br/><b>Desviación (Dif): {desviacion:,.2f} L</b>"
                t_ctrl = Table([
                    [P("PARAMETRO/CONTROL", s_thc), P("REGISTRO Y VALIDACIÓN VEEDER-ROOT (T1: MAGNA)", s_thc), P("CUMPLE SASISOPA", s_thc), P("ESTATUS/VALORES", s_thc)],
                    [P("CONTROL VEEDER-ROOT", s_lbl), P(reg_vr), P("[X] SÍ   [ ] NO", s_ctr), P(est_vr)]
                ], colWidths=[105, 212, 90, 145])
                t_ctrl.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), c_rojo), ('BACKGROUND', (0,1), (0,1), c_gris), ('GRID', (0,0), (-1,-1), 0.5, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('PADDING', (0,0), (-1,-1), 5)]))
                elementos.extend([t_ctrl, Spacer(1, 8)])

                obs_txt = f"<b>OBSERVACIONES/ACCIONES:</b><br/>Recepción amparada con Factura {factura_raw}. Aumento Bruto validado mediante registro fotográfico en Anexo 2."
                t_obs = Table([[P(obs_txt)]], colWidths=[552])
                t_obs.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f9f9f9")), ('BOX', (0,0), (-1,-1), 0.5, colors.black), ('PADDING', (0,0), (-1,-1), 6)]))
                elementos.extend([t_obs, Spacer(1, 35)])

                sj, sy = buscar_imagen("firma_javier"), buscar_imagen("firma_yahir")
                cj = RLImage(sj, width=115, height=42) if sj else P("[Firma Javier]", s_ctr)
                cy = RLImage(sy, width=115, height=42) if sy else P("[Firma Yahir]", s_ctr)
                t_fir = Table([
                    [cj, "", cy],
                    [P("Javier Arturo Garcia Venegas", s_fnm), "", P("Yahir Caro Martinez", s_fnm)],
                    [P("Operador/Encargado de Descarga (Realizó)", s_fcg), "", P("Representante Técnico/Administrador (Autorizó)", s_fcg)]
                ], colWidths=[230, 92, 230])
                t_fir.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'BOTTOM'), ('LINEABOVE', (0,1), (0,1), 0.7, colors.black), ('LINEABOVE', (2,1), (2,1), 0.7, colors.black)]))
                elementos.extend([t_fir, PageBreak()])

                t_cab2 = Table([[logo2, P("<b>Auditoría Documental:</b><br/>" + dir_txt, s_der)]], colWidths=[110, 442])
                t_cab2.setStyle(estilo_cab)
                t_anx = Table([[P("ANEXO DE EVIDENCIA: LECTURA VISUAL DE TIRA VEEDER-ROOT", s_bit)]], colWidths=[552])
                t_anx.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), c_rosa), ('BOX', (0,0), (-1,-1), 1, c_rojo), ('PADDING', (0,0), (-1,-1), 4)]))
                elementos.extend([t_cab2, Spacer(1, 8), t_anx, Spacer(1, 10)])

                temp_img_path = "temp_veeder.png"
                img_tira.convert("RGB").save(temp_img_path, format="PNG")
                img_vr = RLImage(temp_img_path, width=250, height=390)
                t_img = Table([[img_vr]], colWidths=[552])
                t_img.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")), ('PADDING', (0,0), (-1,-1), 8)]))

                res_p2 = f"• <b>Factura:</b> {factura_raw} | <b>Litros Facturados:</b> {vol_facturado:,.2f} L<br/>• <b>Litros Descargados (Bruto):</b> {vol_descargado:,.2f} L | <b>Desviación (Dif):</b> {desviacion:,.2f} L"
                t_res = Table([[P(res_p2)]], colWidths=[552])
                t_res.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), c_gris), ('BOX', (0,0), (-1,-1), 0.5, colors.black), ('PADDING', (0,0), (-1,-1), 6)]))
                elementos.extend([t_img, Spacer(1, 10), t_res])

                doc.build(elementos)
                siguiente_folio = int(folio_input) + 1
                guardar_folio(siguiente_folio)
                st.session_state.folio_actual = siguiente_folio
            except Exception as e_pdf:
                st.error(f"❌ Error al construir el PDF: {e_pdf}")
                st.stop()

            try:
                url_script = st.secrets.get("URL_GOOGLE_SCRIPT")
                if url_script:
                    with open(ruta_pdf, "rb") as f:
                        pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
                    res = requests.post(url_script.strip(), data={"archivoB64": pdf_b64, "nombreArchivo": nombre_archivo_pdf}, timeout=45)
                    if any(w in res.text.lower() for w in ["éxito", "exito", "success"]):
                        st.success("✅ ¡Bitácora enviada y guardada en tu Google Drive!")
                        st.info(f"📌 Siguiente folio reservado: {siguiente_folio}")
                    else:
                        st.warning(f"⚠️ Respuesta Drive: {res.text}")
                else:
                    st.warning("⚠️ Falta URL_GOOGLE_SCRIPT en Secrets.")
            except Exception as e_net:
                st.warning(f"⚠️ PDF creado, pero falló envío a Drive: {e_net}")

            with open(ruta_pdf, "rb") as pdf_file:
                st.download_button(label="📥 Descargar Copia", data=pdf_file.read(), file_name=nombre_archivo_pdf, mime="application/pdf", use_container_width=True)
# === FIN DEL ARCHIVO ===
