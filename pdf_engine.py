import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

def buscar_imagen(nombre_base):
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        if os.path.exists(f"{nombre_base}.{ext}"):
            return f"{nombre_base}.{ext}"
    return None

def generar_pdf_recepcion(datos, img_tira, ruta_pdf):
    folio_str = str(datos["folio"]).zfill(4)
    factura_raw = datos["factura"]
    uuid = datos["uuid"]
    producto_txt = datos["producto"]
    tanque_vr = datos["tanque_vr"]
    vol_facturado = float(datos["litros_facturados"])
    vol_descargado = float(datos["litros_descargados"])
    desviacion = abs(vol_facturado - vol_descargado)
    fecha_tira = datos["fecha"]
    hora_inicio = datos["hora_inicio"]
    hora_termino = datos["hora_termino"]
    embarque = datos["embarque"]
    tanque_at = datos["tanque_at"]
    operador = datos.get("operador", "Javier Arturo Garcia")
    observaciones = datos.get("observaciones", "")

    doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=25, bottomMargin=25)
    elementos, styles = [], getSampleStyleSheet()
    c_rojo, c_rosa, c_gris = colors.HexColor("#a81c1c"), colors.HexColor("#f9ebea"), colors.HexColor("#f2f2f2")

    s_der = ParagraphStyle("Der", fontName="Helvetica", fontSize=7.5, leading=10, alignment=2, textColor=colors.HexColor("#222222"))
    s_sas = ParagraphStyle("Sas", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=colors.white)
    s_bit = ParagraphStyle("Bit", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=1, textColor=c_rojo)
    s_lbl = ParagraphStyle("Lbl", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8, textColor=colors.black)
    s_cel = ParagraphStyle("Cel", fontName="Helvetica", fontSize=6.8, leading=8.8, textColor=colors.black)
    s_ctr = ParagraphStyle("Ctr", fontName="Helvetica-Bold", fontSize=7.0, leading=9.0, alignment=1, textColor=colors.black)
    s_thc = ParagraphStyle("Thc", fontName="Helvetica-Bold", fontSize=6.8, leading=8.8, alignment=1, textColor=colors.white)
    s_fnm = ParagraphStyle("Fnm", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, alignment=1, textColor=colors.black)
    s_fcg = ParagraphStyle("Fcg", fontName="Helvetica", fontSize=6.5, leading=8.5, alignment=1, textColor=colors.HexColor("#444444"))

    def P(txt, st_p=s_cel):
        return Paragraph(str(txt), st_p)

    logo_p = buscar_imagen("logo_teika") or buscar_imagen("cabecera")
    logo1 = RLImage(logo_p, width=95, height=42) if logo_p else P("<b>[Logo]</b>")
    logo2 = RLImage(logo_p, width=95, height=42) if logo_p else P("<b>[Logo]</b>")

    dir_txt = "<font size=10><b>COMBUSTIBLES BUENOS AIRES S.A. DE C.V.</b></font><br/>CAMPO 4 SN, COLONIA BUENOS AIRES, JANOS, CHIHUAHUA. C.P. 31844."
    estilo_cab = TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, c_rojo),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
    ])

    t_cab1 = Table([[logo1, P(dir_txt, s_der)]], colWidths=[110, 442])
    t_cab1.setStyle(estilo_cab)
    elementos.extend([t_cab1, Spacer(1, 8)])

    t_tit = Table([
        [P("SISTEMA DE ADMINISTRACIÓN (SASISOPA) NOM-005-ASEA-2016", s_sas)],
        [P(f"BITÁCORA OFICIAL DE RECEPCIÓN, DESCARGA Y CONTROL VEEDER-ROOT | FOLIO: {folio_str}", s_bit)]
    ], colWidths=[552])
    t_tit.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), c_rojo),
        ('BACKGROUND', (0, 1), (0, 1), c_rosa),
        ('BOX', (0, 0), (-1, -1), 1, c_rojo),
        ('LINEABOVE', (0, 1), (-1, 1), 0.8, c_rojo),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
    ]))
    elementos.extend([t_tit, Spacer(1, 6)])

    aut_txt = f"Emb: {embarque} | Tq: {tanque_at} | Op: {operador}"
    t_info = Table([
        [P("FACTURA:", s_lbl), P(f"<b>{factura_raw}</b>"), P("RFC ESTACIÓN:", s_lbl), P("CBA140131V12")],
        [P("PERMISO CRE:", s_lbl), P("PL/3910/EXP/ES/2015"), P("FOLIO FISCAL:", s_lbl), P(uuid)],
        [P("PRODUCTO:", s_lbl), P(f"<b>{producto_txt} ({vol_facturado:,.2f} L)</b>"), P("PROVEEDOR:", s_lbl), P("UNEGAS DISTRIBUCION (UDA171106KV9)")],
        [P("AUTOTANQUE:", s_lbl), P(aut_txt), P("DESTINO:", s_lbl), P("Combustibles Buenos Aires")],
        [P("FECHA DESCARGA:", s_lbl), P(fecha_tira), P("HORARIO (INICIO - FIN):", s_lbl), P(f"{hora_inicio} a {hora_termino}")]
    ], colWidths=[95, 181, 105, 171])
    t_info.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (0, -1), c_gris),
        ('BACKGROUND', (2, 0), (2, -1), c_gris),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 4)
    ]))
    elementos.extend([t_info, Spacer(1, 8)])

    reg_vr = f"• Verificación de descarga autorizada.<br/>• <b>Aumento Bruto CT: {vol_descargado:,.2f} L</b>"
    est_vr = f"Facturado: {vol_facturado:,.2f} L<br/>Descargado (Bruto): {vol_descargado:,.2f} L<br/><b>Desviación (Dif): {desviacion:,.2f} L</b>"
    t_ctrl = Table([
        [P("PARAMETRO/CONTROL", s_thc), P(f"REGISTRO Y VALIDACIÓN VEEDER-ROOT ({tanque_vr})", s_thc), P("CUMPLE SASISOPA", s_thc), P("ESTATUS/VALORES", s_thc)],
        [P("CONTROL VEEDER-ROOT", s_lbl), P(reg_vr), P("[X] SÍ   [ ] NO", s_ctr), P(est_vr)]
    ], colWidths=[105, 212, 90, 145])
    t_ctrl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_rojo),
        ('BACKGROUND', (0, 1), (0, 1), c_gris),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 5)
    ]))
    elementos.extend([t_ctrl, Spacer(1, 8)])

    if not observaciones:
        observaciones = f"Recepción amparada con Factura {factura_raw}. Aumento Bruto validado mediante registro fotográfico en Anexo 2."
    obs_txt = f"<b>OBSERVACIONES/ACCIONES:</b><br/>{observaciones}"
    t_obs = Table([[P(obs_txt)]], colWidths=[552])
    t_obs.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f9f9f9")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elementos.extend([t_obs, Spacer(1, 35)])

    sj, sy = buscar_imagen("firma_javier"), buscar_imagen("firma_yahir")
    cj = RLImage(sj, width=115, height=42) if sj else P("[Firma Javier]", s_ctr)
    cy = RLImage(sy, width=115, height=42) if sy else P("[Firma Yahir]", s_ctr)
    t_fir = Table([
        [cj, "", cy],
        [P("Javier Arturo Garcia Venegas", s_fnm), "", P("Yahir Caro Martinez", s_fnm)],
        [P("Operador/Encargado de Descarga (Realizó)", s_fcg), "", P("Representante Técnico/Administrador (Autorizó)", s_fcg)]
    ], colWidths=[230, 92, 230])
    t_fir.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LINEABOVE', (0, 1), (0, 1), 0.7, colors.black),
        ('LINEABOVE', (2, 1), (2, 1), 0.7, colors.black)
    ]))
    elementos.extend([t_fir, PageBreak()])

    t_cab2 = Table([[logo2, P("<b>Auditoría Documental:</b><br/>" + dir_txt, s_der)]], colWidths=[110, 442])
    t_cab2.setStyle(estilo_cab)
    t_anx = Table([[P("ANEXO DE EVIDENCIA: LECTURA VISUAL DE TIRA VEEDER-ROOT", s_bit)]], colWidths=[552])
    t_anx.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), c_rosa), ('BOX', (0, 0), (-1, -1), 1, c_rojo), ('PADDING', (0, 0), (-1, -1), 4)]))
    elementos.extend([t_cab2, Spacer(1, 8), t_anx, Spacer(1, 10)])

    temp_img_path = "temp_veeder.png"
    img_tira.convert("RGB").save(temp_img_path, format="PNG")
    img_vr = RLImage(temp_img_path, width=250, height=390)
    t_img = Table([[img_vr]], colWidths=[552])
    t_img.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")), ('PADDING', (0, 0), (-1, -1), 8)]))

    res_p2 = f"• <b>Factura:</b> {factura_raw} | <b>Litros Facturados:</b> {vol_facturado:,.2f} L<br/>• <b>Litros Descargados (Bruto):</b> {vol_descargado:,.2f} L | <b>Desviación (Dif):</b> {desviacion:,.2f} L"
    t_res = Table([[P(res_p2)]], colWidths=[552])
    t_res.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), c_gris), ('BOX', (0, 0), (-1, -1), 0.5, colors.black), ('PADDING', (0, 0), (-1, -1), 6)]))
    elementos.extend([t_img, Spacer(1, 10), t_res])

    doc.build(elementos)
    return ruta_pdf
