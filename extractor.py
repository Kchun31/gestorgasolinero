import base64, io, json, re, time, requests
from PIL import Image, ImageOps

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

def comprimir_imagen_b64(img_bytes):
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("L")
    img = ImageOps.autocontrast(img)
    img.thumbnail((720, 720), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=68, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def extraer_con_ia_ligera(b_tira, api_key, texto_pdf="", b_factura=None, pedir_factura=False):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key.strip()}"
    prompt = (
        "Extrae los datos del ticket Veeder-Root (y factura si se adjunta). "
        "En la tira Veeder-Root toma 'litros_descargados' de la línea 'AUMENTO BRUTO' (ej. 43285 o 43342, nunca uses Aumento Neto), "
        "'tanque_vr' ('T1: MAGNA' si dice T1 o MAGNA, 'T2: DIÉSEL' si dice T2 o DIESEL), "
        "'fecha' en formato DD/MM/AAAA, 'hora_inicio' (HH:MM) y 'hora_termino' (HH:MM). "
        "Responde SOLO JSON: "
        '{"litros_descargados": 0.0, "fecha": "DD/MM/AAAA", "hora_inicio": "HH:MM", "hora_termino": "HH:MM", '
        '"tanque_vr": "T1: MAGNA", "factura": "", "uuid": "", "litros_facturados": 0.0, "embarque": "S/D", "tanque_at": "S/D"}'
    )
    parts = [{"text": prompt}]
    if b_tira:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": comprimir_imagen_b64(b_tira)}})
    if pedir_factura:
        if texto_pdf and len(texto_pdf.strip()) > 20:
            parts.append({"text": f"Texto factura:\n{texto_pdf[:3500]}"})
        elif b_factura:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": comprimir_imagen_b64(b_factura)}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
    }
    for intento in range(2):
        try:
            r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=(10, 45))
            if r.status_code == 200:
                txt_resp = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                match = re.search(r"\{.*\}", txt_resp, re.DOTALL)
                if match:
                    return json.loads(match.group(0), strict=False), None
            elif r.status_code in (429, 500, 502, 503, 504) and intento == 0:
                time.sleep(4)
                continue
            else:
                return None, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            if intento == 0:
                time.sleep(3)
            else:
                return None, str(e)
    return None, "Tiempo de espera agotado en servidor IA."
