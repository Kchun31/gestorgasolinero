import base64, calendar, io, json, os, re, zipfile
from datetime import datetime, timedelta, timezone
import pandas as pd
from PIL import Image as PILImage
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MESES_MAP = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12
}
ARCHIVO_PLAN_GUARDADO = "plan_mtto_activo.xlsx"
ARCHIVO_ESTADO_MTTO = "estado_folios_mtto.json"

def fecha_hoy_chihuahua():
    return datetime.now(timezone(timedelta(hours=-6))).date()

def cargar_folios_mtto():
    if os.path.exists(ARCHIVO_ESTADO_MTTO):
        try:
            with open(ARCHIVO_ESTADO_MTTO, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"folio_mtto": 1001, "folio_limp": 5001}

def guardar_folios_mtto(f_mtto, f_limp):
    with open(ARCHIVO_ESTADO_MTTO, "w") as f:
        json.dump({"folio_mtto": int(f_mtto), "folio_limp": int(f_limp)}, f)

def buscar_imagen(nombres_base):
    if isinstance(nombres_base, str):
        nombres_base = [nombres_base]
    for base in nombres_base:
        if os.path.exists(base):
            return base
        for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
            ruta = f"{base}.{ext}"
            if os.path.exists(ruta):
                return ruta
    return None

def imagen_proporcional(ruta, max_w, max_h):
    if not ruta or not os.path.exists(ruta):
        return None
    try:
        with PILImage.open(ruta) as im:
            w, h = im.size
        if w > 0 and h > 0:
            escala = min(float(max_w) / w, float(max_h) / h)
            return RLImage(ruta, width=w * escala, height=h * escala)
    except Exception:
        pass
    return RLImage(ruta, width=max_w, height=max_h)

def limpiar_nombre(txt):
    s = re.sub(r'[\\/*?:"<>|\n\r\t]+', "_", str(txt or "").strip())
    return re.sub(r"[\s_]+", "_", s).strip("_")[:45] or "General"

def detectar_mes_anio(df, nombre_archivo="", anio_default=2026):
    texto = f"{nombre_archivo} {' '.join(str(x) for x in df.columns)} {' '.join(str(x) for x in df.iloc[:5, 0])}".upper()
    mes_num, mes_nombre = 10, "OCTUBRE"
    for nombre, num in MESES_MAP.items():
        if nombre in texto:
            mes_num, mes_nombre = num, nombre
            break
    m_anio = re.search(r"\b(202[4-9]|203[0-5])\b", texto)
    anio = int(m_anio.group(1)) if m_anio else int(anio_default)
    return mes_num, mes_nombre, anio

def extraer_actividades_excel(excel_bytes, nombre_archivo="", anio_default=2026):
    xls = pd.ExcelFile(io.BytesIO(excel_bytes))
    actividades = []
    mes_num, mes_nombre, anio = 10, "OCTUBRE", int(anio_default)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        mes_num, mes_nombre, anio = detectar_mes_anio(df, f"{nombre_archivo} {sheet}", anio_default)
        fila_enc = None
        for idx in range(min(15, len(df))):
            fila_str = " ".join(str(x).upper() for x in df.iloc[idx].values if pd.notna(x))
            if "MANTENIMIENTO" in fila_str or "EQUIPO A REVISAR" in fila_str or "PERIODICIDAD" in fila_str:
                fila_enc = idx
                break
        if fila_enc is None:
            continue
        col_dias = {}
        for c_idx in range(4, df.shape[1]):
            val = df.iloc[fila_enc, c_idx]
            if pd.notna(val):
                try:
                    d = int(float(str(val).strip()))
                    if 1 <= d <= 31:
                        col_dias[c_idx] = d
                except Exception:
                    pass
        for r_idx in range(fila_enc + 1, len(df)):
            area = df.iloc[r_idx, 0]
            numeral = df.iloc[r_idx, 1]
            criterio = df.iloc[r_idx, 2]
            periodicidad = df.iloc[r_idx, 3] if df.shape[1] > 3 else "Cada 30 Días"
            if pd.isna(area) or pd.isna(numeral):
                continue
            area_s = str(area).strip()
            if area_s.upper().startswith("FIRMA"):
                continue
            num_s = re.sub(r"^[\-\s]+", "", str(numeral).strip())
            crit_s = str(criterio).strip() if pd.notna(criterio) else "Revisión conforme al fabricante y NOM-005-ASEA-2016."
            per_s = str(periodicidad).strip() if pd.notna(periodicidad) else "Cada 30 Días"
            for c_idx, dia in col_dias.items():
                celda = df.iloc[r_idx, c_idx]
                if pd.notna(celda) and str(celda).strip() not in ("", "nan", "NaN"):
                    actividades.append({
                        "dia": dia,
                        "mes": mes_num,
                        "mes_nombre": mes_nombre,
                        "anio": anio,
                        "fecha": f"{dia:02d}/{mes_num:02d}/{anio}",
                        "area": area_s,
                        "elemento": num_s,
                        "criterio": crit_s,
                        "periodicidad": per_s,
                    })
    actividades.sort(key=lambda x: (x["dia"], x["area"], x["elemento"]))
    return actividades, mes_num, mes_nombre, anio

def crear_pdf_bitacora_mtto(datos):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=25, bottomMargin=25)
    elementos = []
    c_rojo = colors.HexColor("#a81c1c")
    c_rosa = colors.HexColor("#f9ebea")
    c_gris = colors.HexColor("#f2f2f2")
    c_azul = colors.HexColor("#000080")

    s_der = ParagraphStyle("Der", fontName="Helvetica", fontSize=7.5, leading=10, alignment=2, textColor=colors.HexColor("#222222"))
    s_sas = ParagraphStyle("Sas", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=colors.white)
    s_bit = ParagraphStyle("Bit", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=c_rojo)
    s_lbl = ParagraphStyle("Lbl", fontName="Helvetica-Bold", fontSize=7.2, leading=9.5, textColor=colors.black)
    s_cel = ParagraphStyle("Cel", fontName="Helvetica", fontSize=7.2, leading=9.5, textColor=colors.black)
    s_ctr = ParagraphStyle("Ctr", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, alignment=1, textColor=colors.black)
    s_thc = ParagraphStyle("Thc", fontName="Helvetica-Bold", fontSize=7.2, leading=9.5, alignment=1, textColor=colors.white)
    s_obs = ParagraphStyle("Obs", fontName="Courier-Bold", fontSize=8.5, leading=11.5, textColor=c_azul)
    s_fnm = ParagraphStyle("Fnm", fontName="Helvetica-Bold", fontSize=8.0, leading=10.0, alignment=1, textColor=colors.black)
    s_fcg = ParagraphStyle("Fcg", fontName="Helvetica", fontSize=6.8, leading=8.8, alignment=1, textColor=colors.HexColor("#444444"))

    def P(txt, st_p=s_cel):
        return Paragraph(str(txt).replace("\n", "<br/>"), st_p)

    logo_p = buscar_imagen(["logo_teika", "cabecera"])
    logo = imagen_proporcional(logo_p, 100, 45) if logo_p else P("<b>[Logo TEIKA]</b>")
    dir_txt = (
        "<font size=10><b>COMBUSTIBLES BUENOS AIRES, S.A. DE C.V.</b></font><br/>"
        "AV. BUENOS AIRES NO. 401, AGRÍCOLA BUENOS AIRES, JANOS, CHIHUAHUA. C.P. 31884.<br/>"
        "<b>RFC:</b> CBA140131V12 | <b>PERMISO CRE:</b> PL/3910/EXP/ES/2015"
    )
    t_cab = Table([[logo, P(dir_txt, s_der)]], colWidths=[110, 442])
    t_cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, c_rojo),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.extend([t_cab, Spacer(1, 8)])

    folio_str = str(datos["folio"]).zfill(4)
    t_tit = Table([
        [P("SISTEMA DE ADMINISTRACIÓN (SASISOPA) NOM-005-ASEA-2016", s_sas)],
        [P(f"{datos['titulo']} | FOLIO: {folio_str}", s_bit)],
    ], colWidths=[552])
    t_tit.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), c_rojo),
        ("BACKGROUND", (0, 1), (0, 1), c_rosa),
        ("BOX", (0, 0), (-1, -1), 1, c_rojo),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.extend([t_tit, Spacer(1, 8)])

    t_info = Table([
        [P("FECHA DE EJECUCIÓN:", s_lbl), P(f"<b>{datos['fecha']}</b>"), P("HORARIO:", s_lbl), P(datos["horario"])],
        [P("ÁREA / SISTEMA:", s_lbl), P(f"<b>{datos['area']}</b>"), P("PERIODICIDAD:", s_lbl), P(datos["periodicidad"])],
        [P("ELEMENTO / NUMERAL:", s_lbl), P(f"<b>{datos['elemento']}</b>"), P("TIPO DE ACTIVIDAD:", s_lbl), P(datos["tipo_mtto"])],
    ], colWidths=[105, 195, 95, 157])
    t_info.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), c_gris),
        ("BACKGROUND", (2, 0), (2, -1), c_gris),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.extend([t_info, Spacer(1, 8)])

    t_ctrl = Table([
        [P("ELEMENTO / EQUIPO REVISADO", s_thc), P("CRITERIO NORMATIVO (NOM-005-ASEA-2016)", s_thc), P("CUMPLE", s_thc), P("ESTATUS", s_thc)],
        [P(f"<b>{datos['area']}</b><br/>{datos['elemento']}"), P(datos["criterio"]), P("[X] SÍ   [ ] NO", s_ctr), P("<b>OPERACIÓN SEGURA</b>", s_ctr)],
    ], colWidths=[140, 232, 85, 95])
    t_ctrl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), c_rojo),
        ("BACKGROUND", (0, 1), (0, 1), c_gris),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.extend([t_ctrl, Spacer(1, 10)])

    t_obs = Table([
        [P("OBSERVACIONES Y ACCIONES REALIZADAS (REGISTRO DE CAMPO):", s_lbl)],
        [P(datos["observaciones"], s_obs)],
    ], colWidths=[552])
    t_obs.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), c_gris),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#fcfcfc")),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
        ("LINEBELOW", (0, 0), (0, 0), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.extend([t_obs, Spacer(1, 25)])

    f_salv = buscar_imagen(["firma_salvador.png", "firma_salvador"])
    f_jes = buscar_imagen(["firma_jesus negro.png", "firma_jesus negro", "firma_jesus.png", "firma_jesus"])
    img_salv = imagen_proporcional(f_salv, 125, 55) if f_salv else P("<i>[Firma Salvador Delgado]</i>", s_ctr)
    img_jes = imagen_proporcional(f_jes, 185, 85) if f_jes else P("<b>[Firma Jesús Carbajal]</b>", s_ctr)

    t_fir = Table([
        [img_salv, "", img_jes],
        [P("Salvador Delgado P.", s_fnm), "", P("Jesús Antonio Carbajal Álvarez", s_fnm)],
        [P("Encargado de Mantenimiento y Operación (Realizó)", s_fcg), "", P("Representante Técnico / Administrador (Autorizó)", s_fcg)],
    ], colWidths=[230, 92, 230])
    t_fir.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LINEABOVE", (0, 1), (0, 1), 0.8, colors.black),
        ("LINEABOVE", (2, 1), (2, 1), 0.8, colors.black),
    ]))
    elementos.append(t_fir)
    doc.build(elementos)
    return buf.getvalue()

def armar_datos_limpieza(folio, dia, mes_num, anio):
    return {
        "folio": folio,
        "titulo": "BITÁCORA OFICIAL DE LIMPIEZA E INSPECCIÓN DIARIA DE ELEMENTOS CONSTRUCTIVOS",
        "fecha": f"{dia:02d}/{mes_num:02d}/{anio}",
        "horario": "08:00 a 09:00 hrs",
        "area": "Elementos Constructivos, Islas, Edificios y Áreas Operativas",
        "elemento": "8.18 / 8.19 LIMPIEZA GENERAL DE INSTALACIONES Y ELEMENTOS CONSTRUCTIVOS",
        "criterio": "Mantener las áreas operativas, pisos, edificios, canaletas, islas y registros limpios, libres de derrames, maleza o residuos peligrosos.",
        "periodicidad": "Diaria (Cada 24 Horas)",
        "tipo_mtto": "Limpieza e Inspección Diaria",
        "observaciones": (
            "Limpieza general e inspección física diaria de elementos constructivos, áreas operativas, "
            "islas de despacho, dispensarios, edificios, pisos, drenajes y sanitarios realizada conforme "
            "a la NOM-005-ASEA-2016. Áreas libres de maleza, derrames y obstrucciones. Sin condiciones inseguras reportadas."
        ),
    }

def armar_datos_mtto(folio, act):
    return {
        "folio": folio,
        "titulo": "BITÁCORA OFICIAL DE MANTENIMIENTO PREVENTIVO E INSPECCIÓN",
        "fecha": act["fecha"],
        "horario": "09:00 a 10:00 hrs",
        "area": act["area"],
        "elemento": act["elemento"],
        "criterio": act["criterio"],
        "periodicidad": act["periodicidad"],
        "tipo_mtto": "Preventivo Programado (■)",
        "observaciones": (
            f"Mantenimiento preventivo programado y revisión física de {act['area']} ({act['elemento']}) "
            f"realizada conforme al programa mensual y a la NOM-005-ASEA-2016. "
            f"Equipo e instalaciones operando en condiciones seguras, limpias y sin fugas."
        ),
    }

def generar_zip_mantenimiento(actividades, mes_num, mes_nombre, anio, folio_mtto_ini=1001, folio_limp_ini=5001, incluir_limpieza_diaria=True, dia_inicio=1, dia_corte=31):
    zip_buf = io.BytesIO()
    f_mtto = int(folio_mtto_ini)
    f_limp = int(folio_limp_ini)
    carpeta_raiz = f"Bitacoras_{mes_nombre.capitalize()}_{anio}"
    _, max_dias_mes = calendar.monthrange(int(anio), int(mes_num))
    d_ini = max(1, int(dia_inicio))
    d_fin = min(max_dias_mes, int(dia_corte))
    archivos_creados = []

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for act in actividades:
            if not (d_ini <= act["dia"] <= d_fin):
                continue
            pdf_bytes = crear_pdf_bitacora_mtto(armar_datos_mtto(f_mtto, act))
            sub_area = limpiar_nombre(act["area"])
            elem_clean = limpiar_nombre(act["elemento"])
            nombre_pdf = f"Folio_{f_mtto:04d}_Dia_{act['dia']:02d}_{elem_clean}.pdf"
            subcarpeta = f"{carpeta_raiz}/01_Mantenimiento_Programado/{sub_area}"
            zf.writestr(f"{subcarpeta}/{nombre_pdf}", pdf_bytes)
            archivos_creados.append((nombre_pdf, pdf_bytes, subcarpeta))
            f_mtto += 1

        if incluir_limpieza_diaria:
            for dia in range(d_ini, d_fin + 1):
                pdf_limp = crear_pdf_bitacora_mtto(armar_datos_limpieza(f_limp, dia, mes_num, anio))
                nombre_l = f"Folio_{f_limp:04d}_{anio}-{mes_num:02d}-{dia:02d}_Limpieza_Diaria.pdf"
                subcarpeta_l = f"{carpeta_raiz}/02_Limpieza_Diaria_Elementos_Constructivos"
                zf.writestr(f"{subcarpeta_l}/{nombre_l}", pdf_limp)
                archivos_creados.append((nombre_l, pdf_limp, subcarpeta_l))
                f_limp += 1

    guardar_folios_mtto(f_mtto, f_limp)
    return zip_buf.getvalue(), f_mtto, f_limp, archivos_creados

def enviar_lote_drive(archivos_creados, url_script):
    if not url_script:
        return 0, "Falta URL_GOOGLE_SCRIPT en Secrets."
    enviados = 0
    for item in archivos_creados:
        nombre_pdf, pdf_bytes = item[0], item[1]
        subcarpeta = item[2] if len(item) > 2 else ""
        try:
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            payload = {
                "archivoB64": pdf_b64,
                "nombreArchivo": nombre_pdf,
                "subcarpeta": subcarpeta,
            }
            res = requests.post(url_script.strip(), data=payload, timeout=30)
            if any(w in res.text.lower() for w in ["éxito", "exito", "success"]):
                enviados += 1
        except Exception:
            pass
    return enviados, f"{enviados}/{len(archivos_creados)} enviados y organizados en Google Drive."
