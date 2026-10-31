import io, re
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps, ImageEnhance

def normalizar_litros(valor):
    if valor is None or str(valor).strip() == "":
        return 0.0
    m = re.findall(r"[-+]?\d*\.?\d+", str(valor).replace(",", ""))
    if not m:
        return 0.0
    num = float(m[0])
    if 5.0 <= num <= 99.999 and "." in m[0] and len(m[0].split(".")[1]) == 3:
        num *= 1000.0
    return round(num, 2)

def extraer_datos_xml_cfdi(xml_bytes, nombre_archivo=""):
    datos = {
        "factura": "",
        "uuid": "",
        "producto": "REGULAR (MAGNA)",
        "tanque_vr": "T1: MAGNA",
        "litros_facturados": 0.0,
        "embarque": "S/D",
        "tanque_at": "S/D"
    }
    try:
        root = ET.fromstring(xml_bytes)
        serie = root.attrib.get("Serie", "") or root.attrib.get("serie", "")
        folio = root.attrib.get("Folio", "") or root.attrib.get("folio", "")
        if serie or folio:
            datos["factura"] = f"{serie}{folio}".strip().upper()

        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "TimbreFiscalDigital":
                uuid = elem.attrib.get("UUID", "") or elem.attrib.get("uuid", "")
                if uuid:
                    datos["uuid"] = uuid.upper()
            elif tag == "Concepto":
                cant_str = elem.attrib.get("Cantidad", "") or elem.attrib.get("cantidad", "0")
                desc = (elem.attrib.get("Descripcion", "") or elem.attrib.get("descripcion", "")).upper()
                clave = elem.attrib.get("ClaveProdServ", "")
                try:
                    cant = float(cant_str)
                    if 10.0 <= cant <= 65.0:
                        cant *= 1000.0
                    if cant > datos["litros_facturados"]:
                        datos["litros_facturados"] = round(cant, 2)
                        if "DIESEL" in desc or "DIÉSEL" in desc or clave == "15101505" or "32011" in desc:
                            datos["producto"] = "DIÉSEL"
                            datos["tanque_vr"] = "T2: DIÉSEL"
                        elif "PREMIUM" in desc or clave == "15101515":
                            datos["producto"] = "PREMIUM"
                            datos["tanque_vr"] = "T3: PREMIUM"
                        else:
                            datos["producto"] = "REGULAR (MAGNA)"
                            datos["tanque_vr"] = "T1: MAGNA"
                except Exception:
                    pass
    except Exception:
        pass
    return datos

def extraer_datos_factura_local(texto_pdf="", nombre_archivo=""):
    datos = {
        "factura": "",
        "uuid": "",
        "producto": "REGULAR (MAGNA)",
        "tanque_vr": "T1: MAGNA",
        "litros_facturados": 0.0,
        "embarque": "S/D",
        "tanque_at": "S/D"
    }
    txt = (texto_pdf or "").strip()

    if nombre_archivo:
        partes = re.split(r"[_.\-\s]+", nombre_archivo.upper())
        for p in partes:
            if re.match(r"^[A-Z]{1,3}\d{3,7}$", p) and not p.startswith("E216") and not p.startswith("CBA"):
                datos["factura"] = p
                break
    if not datos["factura"] and txt:
        m_fac = re.search(r"\b(B\d{3,6}|F\d{3,6}|A\d{3,6})\b", txt)
        if not m_fac:
            m_fac = re.search(r"(?:FOLIO|FACTURA|SERIE)[:\s\-]*([A-Z]?\d{3,7})\b", txt, re.IGNORECASE)
        if m_fac:
            datos["factura"] = m_fac.group(1).upper()

    m_uuid = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", txt)
    if m_uuid:
        datos["uuid"] = m_uuid.group(0).upper()

    txt_up = txt.upper()
    if "DIESEL" in txt_up or "DIÉSEL" in txt_up or "15101505" in txt_up or "32011" in txt_up:
        if "MAGNA" not in txt_up and "REGULAR" not in txt_up:
            datos["producto"] = "DIÉSEL"
            datos["tanque_vr"] = "T2: DIÉSEL"
    elif "PREMIUM" in txt_up or "15101515" in txt_up:
        if "MAGNA" not in txt_up and "REGULAR" not in txt_up:
            datos["producto"] = "PREMIUM"
            datos["tanque_vr"] = "T3: PREMIUM"

    candidatos = []
    for linea in txt.splitlines():
        l_up = linea.upper()
        if any(w in l_up for w in ["TOTAL", "SUBTOTAL", "IVA", "IMPORTE", "PESOS", "MXN", "CADENA", "SELLO"]):
            if not any(p in l_up for p in ["LITRO", "LTR", "MAGNA", "REGULAR", "DIESEL", "DIÉSEL", "PREMIUM", "151015"]):
                continue
        for match in re.finditer(r"(?<!\$)\b(\d{2},\d{3}(?:\.\d{1,4})?|\d{5}(?:\.\d{1,4})?|\d{2}\.\d{3})\b", linea):
            val_str = match.group(1).replace(",", "")
            try:
                v = float(val_str)
                if 10.0 <= v <= 65.0 and "." in match.group(1) and len(match.group(1).split(".")[1]) == 3:
                    v *= 1000.0
                if 2000.0 <= v <= 65000.0:
                    peso = 2 if any(k in l_up for k in ["LTR", "LITRO", "MAGNA", "REGULAR", "DIESEL", "151015", "M3", "MTQ"]) else 1
                    candidatos.append((peso, v))
            except Exception:
                pass
    if candidatos:
        candidatos.sort(key=lambda x: x[0], reverse=True)
        datos["litros_facturados"] = round(candidatos[0][1], 2)

    m_emb = re.search(r"(?:EMBARQUE|EMB)[:\s#.\-]*([0-9]{4,9})", txt, re.IGNORECASE)
    if m_emb:
        datos["embarque"] = m_emb.group(1)
    m_tq = re.search(r"(?:TANQUE|TONEL|TQ|AUTOTANQUE|PLACA)[:\s#.\-]*([A-Z0-9]{4,8})", txt, re.IGNORECASE)
    if m_tq and m_tq.group(1).upper() not in ("PARA", "COMO", "TIPO", "LITROS"):
        datos["tanque_at"] = m_tq.group(1).upper()

    return datos

def extraer_tira_ocr_local(img_bytes):
    datos = {"litros_descargados": 0.0, "fecha": "", "hora_inicio": "", "hora_termino": "", "tanque_vr": ""}
    try:
        import pytesseract
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("L")
        w, h = img.size
        if w < 1000:
            img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.2)
        img = ImageEnhance.Sharpness(img).enhance(2.0)

        txt = pytesseract.image_to_string(img, config="--oem 3 --psm 6")
        txt_up = txt.upper()

        if "DIESEL" in txt_up or "T 2" in txt_up or "T2" in txt_up:
            datos["tanque_vr"] = "T2: DIÉSEL"
        elif "MAGNA" in txt_up or "REGULAR" in txt_up or "T 1" in txt_up or "T1" in txt_up:
            datos["tanque_vr"] = "T1: MAGNA"

        m_bruto = re.search(r"(?:BRUTO|AUMENTO\s*B|AUM\w*\s*B)[^\d]{0,20}(\d{4,5}(?:\.\d{1,2})?)", txt_up)
        if m_bruto:
            datos["litros_descargados"] = float(m_bruto.group(1))
        else:
            nums = [float(n) for n in re.findall(r"\b([1-5]\d{4})\b", txt_up) if 10000 <= float(n) <= 58000]
            if nums:
                datos["litros_descargados"] = nums[-1]

        m_fec = re.search(r"\b(\d{2}[/\-]\d{2}[/\-]\d{2,4})\b", txt_up)
        if m_fec:
            f_str = m_fec.group(1).replace("-", "/")
            partes_f = f_str.split("/")
            if len(partes_f[2]) == 2:
                f_str = f"{partes_f[0]}/{partes_f[1]}/20{partes_f[2]}"
            datos["fecha"] = f_str

        horas = re.findall(r"\b([0-2]?\d:[0-5]\d)\b", txt_up)
        if len(horas) >= 2:
            datos["hora_inicio"] = horas[0].zfill(5)
            datos["hora_termino"] = horas[-1].zfill(5)
    except Exception:
        pass
    return datos
