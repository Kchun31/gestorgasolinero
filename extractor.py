import base64, io, json, re, requests
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps, ImageEnhance
import streamlit as st

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

        txt_completo = ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8", errors="ignore")
        extra_txt = extraer_datos_factura_local(txt_completo, nombre_archivo)
        datos["embarque"] = extra_txt["embarque"]
        datos["tanque_at"] = extra_txt["tanque_at"]

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
        m_fac = re.search(r"\b(B\d{3,6}|F\d{3,6}|A\d{3,6})\b", txt, re.IGNORECASE)
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

    patrones_emb = [
        r"(?:EMBARQUE|REMISION|REMISIÓN|PEDIDO|ORDEN|VIAJE|BOL|DOCUMENTO)[^\d\n]{0,25}(\d{5,10})",
        r"\b(3\d{7}|\d{7,8})\b"
    ]
    for pat in patrones_emb:
        m_emb = re.search(pat, txt, re.IGNORECASE)
        if m_emb:
            datos["embarque"] = m_emb.group(1)
            break

    m_tq = re.search(r"(?:TANQUE|TONEL|TQ|AUTOTANQUE|PLACA|UNIDAD|EQUIPO)[:\s#.\-]*([A-Z0-9\-]{4,10})", txt, re.IGNORECASE)
    if m_tq and m_tq.group(1).upper() not in ("PARA", "COMO", "TIPO", "LITROS", "FISCAL"):
        datos["tanque_at"] = m_tq.group(1).upper()

    return datos

def extraer_tira_ocr_local(img_bytes):
    datos = {"litros_descargados": 0.0, "fecha": "", "hora_inicio": "", "hora_termino": "", "tanque_vr": ""}

    # 1. Lectura de alta precisión para tickets borrosos (usando nombres reales de modelos)
    api_key = ""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
    except Exception:
        pass

    if api_key:
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("RGB")
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

            prompt = (
                "Lee este ticket Veeder-Root de gasolinera. "
                "Extrae: 'litros_descargados' (el valor de AUMENTO BRUTO o AUMENTO B, ej. 43285, nunca uses Neto), "
                "'fecha' (formato DD/MM/AAAA), 'hora_inicio' (HH:MM), 'hora_termino' (HH:MM), "
                "y 'tanque_vr' ('T1: MAGNA' si es T1/Magna/Regular, 'T2: DIÉSEL' si es T2/Diesel). "
                "Devuelve SOLO JSON: "
                '{"litros_descargados": 0.0, "fecha": "", "hora_inicio": "", "hora_termino": "", "tanque_vr": "T1: MAGNA"}'
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
            }
            for mod in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={api_key}"
                r = requests.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    txt_ia = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    m_json = re.search(r"\{.*\}", txt_ia, re.DOTALL)
                    if m_json:
                        js = json.loads(m_json.group(0), strict=False)
                        datos["litros_descargados"] = normalizar_litros(js.get("litros_descargados", 0))
                        datos["fecha"] = str(js.get("fecha", "")).strip()
                        datos["hora_inicio"] = str(js.get("hora_inicio", "")).strip()
                        datos["hora_termino"] = str(js.get("hora_termino", "")).strip()
                        if js.get("tanque_vr") in ["T1: MAGNA", "T2: DIÉSEL", "T3: PREMIUM"]:
                            datos["tanque_vr"] = js.get("tanque_vr")
                        if datos["litros_descargados"] > 0:
                            return datos
        except Exception:
            pass

    # 2. Respaldo OCR local por comando de sistema tesseract (por si no hay internet)
    try:
        import subprocess
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.2)
        img.save("temp_ocr.png")
        res = subprocess.run(["tesseract", "temp_ocr.png", "stdout", "--psm", "6"], capture_output=True, text=True, timeout=8)
        txt_up = res.stdout.upper()

        m_bruto = re.search(r"(?:BRUTO|AUMENTO\s*B|AUM\w*\s*B)[^\d]{0,20}(\d{4,5}(?:\.\d{1,2})?)", txt_up)
        if m_bruto:
            datos["litros_descargados"] = float(m_bruto.group(1))
        else:
            nums = [float(n) for n in re.findall(r"\b([1-5]\d{4})\b", txt_up) if 10000 <= float(n) <= 58000]
            if nums:
                datos["litros_descargados"] = nums[-1]

        m_fec = re.search(r"\b(\d{2}[/\-]\d{2}[/\-]\d{2,4})\b", txt_up)
        if m_fec:
            datos["fecha"] = m_fec.group(1).replace("-", "/")

        horas = re.findall(r"\b([0-2]?\d:[0-5]\d)\b", txt_up)
        if len(horas) >= 2:
            datos["hora_inicio"] = horas[0].zfill(5)
            datos["hora_termino"] = horas[-1].zfill(5)
    except Exception:
        pass

    return datos
# === FIN DE extractor.py ===
