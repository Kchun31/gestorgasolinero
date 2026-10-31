import re
import xml.etree.ElementTree as ET

CLAVES_SAT_PRODUCTO = {"15101514", "15101515", "15101505", "15101506", "80161504"}
RE_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
RE_PLACA = r"([A-Z0-9]{5,8})"


def _base():
    return {
        "factura": "",
        "uuid": "",
        "producto": "REGULAR (MAGNA)",
        "tanque_vr": "T1: MAGNA",
        "litros_facturados": 0.0,
        "embarque": "S/D",
        "tanque_at": "S/D",
    }


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


def _producto(clave, desc):
    d = (desc or "").upper()
    if "DIESEL" in d or "DIÉSEL" in d or clave == "15101505" or "32011" in d:
        return "DIÉSEL", "T2: DIÉSEL"
    if "PREMIUM" in d or clave == "15101515":
        return "PREMIUM", "T3: PREMIUM"
    return "REGULAR (MAGNA)", "T1: MAGNA"


def _es_clave_sat(valor):
    solo = re.sub(r"\D", "", valor or "")
    return solo in CLAVES_SAT_PRODUCTO or (len(solo) == 8 and solo.startswith(("1510", "8016")))


def _embarque(texto):
    t = (texto or "").upper()
    patrones = [
        r"EMBARQUE\s*[:#.\-]?\s*((?:[A-Z]{2,4}[\s\-]*)?\d{4,10})\b",
        r"\b(PMX[\s\-]*\d{4,10})\b",
    ]
    for pat in patrones:
        for m in re.finditer(pat, t):
            val = re.sub(r"\s+", " ", m.group(1)).strip(" -")
            if val and not _es_clave_sat(val):
                return val
    return "S/D"


def _tanque_autotanque(texto):
    t = (texto or "").upper()
    patrones = [
        r"PLACAS?\s*(?:DE\s*)?(?:TQ|TANQUE|TK)\b\.?\s*[:\-]?\s*" + RE_PLACA,
        r"\bTQ\b\.?\s*[:\-]?\s*" + RE_PLACA,
        r"\bAUTOTANQUE\b\s*[:\-]?\s*" + RE_PLACA,
    ]
    for pat in patrones:
        for m in re.finditer(pat, t):
            val = m.group(1)
            if any(c.isdigit() for c in val) and not _es_clave_sat(val):
                return val
    return "S/D"


def extraer_datos_xml_cfdi(xml_bytes, nombre_archivo=""):
    datos = _base()
    try:
        root = ET.fromstring(xml_bytes)
        serie = root.attrib.get("Serie", "") or root.attrib.get("serie", "")
        folio = root.attrib.get("Folio", "") or root.attrib.get("folio", "")
        if serie or folio:
            datos["factura"] = f"{serie}{folio}".strip().upper()
        descripciones = []
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "TimbreFiscalDigital":
                uuid = elem.attrib.get("UUID", "") or elem.attrib.get("uuid", "")
                if uuid:
                    datos["uuid"] = uuid.upper()
            elif tag == "Concepto":
                cant_str = elem.attrib.get("Cantidad", "") or elem.attrib.get("cantidad", "0")
                desc = elem.attrib.get("Descripcion", "") or elem.attrib.get("descripcion", "")
                clave = elem.attrib.get("ClaveProdServ", "")
                descripciones.append(desc)
                try:
                    cant = float(cant_str)
                    if 10.0 <= cant <= 65.0:
                        cant *= 1000.0
                    if cant > datos["litros_facturados"]:
                        datos["litros_facturados"] = round(cant, 2)
                        datos["producto"], datos["tanque_vr"] = _producto(clave, desc)
                except Exception:
                    pass
        todo = "\n".join(descripciones)
        datos["embarque"] = _embarque(todo)
        datos["tanque_at"] = _tanque_autotanque(todo)
    except Exception:
        pass
    return datos


def _folio_pdf(txt, nombre_archivo):
    m = re.search(r"REFERENCIA\s*:?\s*([A-Z]{0,3}\d{2,8})\b", txt.upper())
    if m:
        return m.group(1)
    m = re.search(r"\b(?:FACTURA|FOLIO)\s*(?:NO\.?|NUM\.?)?\s*:?\s*([A-Z]{1,3}\d{3,8})\b", txt.upper())
    if m:
        return m.group(1)
    for p in re.split(r"[_.\-\s]+", (nombre_archivo or "").upper()):
        if re.match(r"^[A-Z]{1,3}\d{3,7}$", p) and not p.startswith(("E216", "CBA")):
            return p
    m = re.search(r"\b(B\d{3,6}|F\d{3,6}|A\d{3,6})\b", txt.upper())
    return m.group(1) if m else ""


def _litros_pdf(txt):
    patron_fila = re.compile(
        r"^\s*(\d{1,3}(?:,\d{3})+|\d{3,6})(?:\.(\d{1,4}))?\s+(?:LTR?S?|LITROS?|LT|MTQ|M3)\b",
        re.IGNORECASE | re.MULTILINE,
    )
    candidatos = []
    for m in patron_fila.finditer(txt):
        v = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
        if 500.0 <= v <= 65000.0:
            candidatos.append(v)
    if candidatos:
        return round(max(candidatos), 2)
    amplios = []
    for linea in txt.splitlines():
        up = linea.upper()
        if not any(k in up for k in ("LTR", "LITRO", "MAGNA", "REGULAR", "DIESEL", "DIÉSEL", "PREMIUM")):
            continue
        for m in re.finditer(r"(?<![\d.,$])(\d{1,3}(?:,\d{3})+(?:\.\d{1,4})?|\d{4,6}(?:\.\d{1,4})?)(?![\d,])", linea):
            v = float(m.group(1).replace(",", ""))
            if 2000.0 <= v <= 65000.0:
                amplios.append(v)
    return round(max(amplios), 2) if amplios else 0.0


def extraer_datos_factura_local(texto_pdf="", nombre_archivo=""):
    datos = _base()
    txt = (texto_pdf or "").strip()
    datos["factura"] = _folio_pdf(txt, nombre_archivo)
    m_fiscal = re.search(r"FOLIO\s+FISCAL\s*:?\s*(" + RE_UUID + ")", txt, re.IGNORECASE)
    m_uuid = m_fiscal or re.search(RE_UUID, txt)
    if m_uuid:
        datos["uuid"] = (m_uuid.group(1) if m_fiscal else m_uuid.group(0)).upper()
    datos["litros_facturados"] = _litros_pdf(txt)
    cuerpo = re.search(r"CANTIDAD\s+UNIDAD.*?(?=CANTIDAD\s+CON\s+LETRA|SUBTOTAL)", txt, re.S | re.I)
    zona = cuerpo.group(0) if cuerpo else txt
    clave = re.search(r"\b(15101505|15101514|15101515)\b", zona)
    datos["producto"], datos["tanque_vr"] = _producto(clave.group(1) if clave else "", zona)
    datos["embarque"] = _embarque(zona)
    datos["tanque_at"] = _tanque_autotanque(zona)
    return datos
