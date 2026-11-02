import re
from collections import Counter
from datetime import datetime

LITROS_MIN = 2000
LITROS_MAX = 65000

RE_VOL = re.compile(r"VOL[UVN\w]*|V0L[UVN\w]*", re.I)
RE_BRUTO = re.compile(r"BRUT\w*|AUMENT\w*\s*B\w*", re.I)
RE_FECHA_LIN = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{2,4}\b")
RE_HORA_LIN = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")


def _linea_con(lineas, patron):
    res = []
    for l in lineas:
        txt = " ".join(w[0] for w in l)
        if patron.search(txt):
            res.append(l)
    return res


def numeros(txt):
    limpio = re.sub(r"(?<=\d)[.,\s](?=\d{3}\b)", "", txt or "")
    out = []
    for m in re.findall(r"\b\d{4,6}\b", limpio):
        v = int(m)
        if 1000 <= v <= 99999:
            out.append(v)
    return out


def _limpiar(txt):
    t = (txt or "").upper()
    t = re.sub(r"(?<=\d)O(?=\d)", "0", t)
    t = re.sub(r"(?<=\s)O(?=\d)", "0", t)
    t = re.sub(r"(?<=\d)[IL|](?=\d)", "1", t)
    return t


def extraer_fechas_sueltas(txt):
    t = _limpiar(txt)
    fechas = []
    for m in re.finditer(r"\b(\d{2})[-/.](\d{2})[-/.](\d{2,4})\b", t):
        d, mes, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        if mes > 12 and d <= 12:
            d, mes = mes, d
        try:
            fechas.append(datetime(y, mes, d).strftime("%Y-%m-%d"))
        except ValueError:
            pass
    if not fechas:
        for m in re.finditer(r"\b(\d{2})(\d{2})(\d{2,4})\b", t):
            d, mes, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            if 2020 <= y <= 2035 and 1 <= mes <= 12 and 1 <= d <= 31:
                try:
                    fechas.append(datetime(y, mes, d).strftime("%Y-%m-%d"))
                except ValueError:
                    pass
    return fechas


def extraer_horas_sueltas(txt):
    t = _limpiar(txt)
    horas = []
    for m in re.finditer(r"\b([0-2]?\d):([0-5]\d)\b", t):
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            horas.append(f"{hh:02d}:{mm:02d}")
    return horas


def fechahoras(txt):
    t = _limpiar(txt)
    dts = []
    patron = r"\b(\d{2})[-/.](\d{2})[-/.](\d{2,4})\s+([0-2]?\d)[:.]([0-5]\d)\b"
    for m in re.finditer(patron, t):
        d, mes, y, hh, mm = (int(x) for x in m.groups())
        if y < 100:
            y += 2000
        if mes > 12 and d <= 12:
            d, mes = mes, d
        try:
            dts.append(datetime(y, mes, d, hh, mm))
        except ValueError:
            pass
    if not dts:
        fechas = extraer_fechas_sueltas(t)
        horas = extraer_horas_sueltas(t)
        if fechas and horas:
            y, m, d = (int(x) for x in fechas[0].split("-"))
            for h_str in horas:
                hh, mm = (int(x) for x in h_str.split(":"))
                try:
                    dts.append(datetime(y, m, d, hh, mm))
                except ValueError:
                    pass
    return dts


def par_de_texto(txt):
    t = _limpiar(txt)
    dts = fechahoras(t)
    if len(dts) >= 2:
        if len(dts) >= 3:
            diff_ult = (dts[-1] - dts[-2]).total_seconds() / 60.0
            if 1 <= diff_ult <= 240:
                return dts[-2], dts[-1]
        return dts[0], dts[-1]

    fechas = extraer_fechas_sueltas(t)
    horas = extraer_horas_sueltas(t)
    if fechas and len(horas) >= 2:
        y1, m1, d1 = (int(x) for x in fechas[0].split("-"))
        y2, m2, d2 = (int(x) for x in fechas[-1].split("-"))
        h1, min1 = (int(x) for x in horas[0].split(":"))
        h2, min2 = (int(x) for x in horas[-1].split(":"))
        if len(horas) >= 3:
            ht, mint = (int(x) for x in horas[-2].split(":"))
            if 1 <= (h2 * 60 + min2) - (ht * 60 + mint) <= 240:
                h1, min1 = ht, mint
        try:
            return datetime(y1, m1, d1, h1, min1), datetime(y2, m2, d2, h2, min2)
        except ValueError:
            pass
    return None


def producto_ticket(lineas):
    txt = "\n".join(" ".join(w[0] for w in l) for l in lineas).upper()
    if re.search(r"DIESEL|DI[EÉ]SEL|T\s*2\b", txt):
        return "T2: DIÉSEL"
    if re.search(r"PREMIUM|T\s*3\b", txt):
        return "T3: PREMIUM"
    if re.search(r"MAGNA|REGULAR|T\s*1\b", txt):
        return "T1: MAGNA"
    return ""


def puntuar(lineas):
    score = 0
    if len(_linea_con(lineas, RE_VOL)) >= 2:
        score += 3
    elif _linea_con(lineas, RE_VOL):
        score += 1
    if _linea_con(lineas, RE_BRUTO):
        score += 2
    txt = "\n".join(" ".join(w[0] for w in l) for l in lineas)
    if par_de_texto(txt):
        score += 3
    if producto_ticket(lineas):
        score += 1
    return score


def _caja_linea(l, pad_x=22, pad_y=12, solo_derecha=False):
    palabras = l
    if solo_derecha:
        con_dig = [w for w in l if sum(c.isdigit() for c in w[0]) >= 3]
        if con_dig:
            palabras = con_dig[-2:]
    x0 = min(w[1] for w in palabras) - pad_x
    y0 = min(w[2] for w in palabras) - pad_y
    x1 = max(w[1] + w[3] for w in palabras) + pad_x
    y1 = max(w[2] + w[4] for w in palabras) + pad_y
    return (x0, y0, x1, y1)


def localizar(lineas):
    cajas = {}
    vols = _linea_con(lineas, RE_VOL)
    if len(vols) >= 2:
        cajas["vi"] = _caja_linea(vols[0], solo_derecha=True)
        cajas["vf"] = _caja_linea(vols[-1], solo_derecha=True)
    brutos = _linea_con(lineas, RE_BRUTO)
    if brutos:
        cajas["br"] = _caja_linea(brutos[-1], solo_derecha=True)
    fechas = _linea_con(lineas, RE_FECHA_LIN)
    if len(fechas) < 2:
        fechas = _linea_con(lineas, RE_HORA_LIN)
    if len(fechas) >= 2:
        cajas["fi"] = _caja_linea(fechas[0])
        cajas["ff"] = _caja_linea(fechas[-1])
    return cajas


def moda(lista):
    vals = [x for x in (lista or []) if x is not None and x != ""]
    if not vals:
        return None, 0, 0
    c = Counter(vals)
    val, n = c.most_common(1)[0]
    return val, n, len(vals)


def _a_min(h_str):
    hh, mm = h_str.split(":")
    return int(hh) * 60 + int(mm)


def corregir_hora_inicio(hi, hf):
    if not hi or not hf:
        return hi, hf
    min_i, min_f = _a_min(hi), _a_min(hf)
    if min_i <= min_f and (min_f - min_i) <= 240:
        return hi, hf
    hh_i, mm_i = hi.split(":")
    hh_f, _ = hf.split(":")
    mapa_termico = {
        "19": ["08", "09"],
        "18": ["08", "06"],
        "16": ["06", "08"],
        "10": ["08", "00"],
        "09": ["08"],
    }
    for cand_hh in mapa_termico.get(hh_i, []):
        cand = f"{cand_hh}:{mm_i}"
        dif = min_f - _a_min(cand)
        if 1 <= dif <= 180:
            return cand, hf
    if min_i > min_f and int(hh_f) <= 11 and int(hh_i) >= 18:
        cand_ mismo_h = f"{hh_f}:{mm_i}"
        if 1 <= min_f - _a_min(cand_mismo_h) <= 60:
            return cand_mismo_h, hf
        prev_h = f"{max(0, int(hh_f) - 1):02d}:{mm_i}"
        if 1 <= min_f - _a_min(prev_h) <= 120:
            return prev_h, hf
    return hi, hf


def resolver_par_horas(hi_list, hf_list):
    hi, _, _ = moda(hi_list)
    hf, _, _ = moda(hf_list)
    hi = hi or ""
    hf = hf or ""
    if hi and hf:
        hi, hf = corregir_hora_inicio(hi, hf)
    return hi, hf


def mejor_triple(vi_list, vf_list, br_list):
    if not vi_list or not vf_list:
        return None
    c_vi = Counter(vi_list)
    c_vf = Counter(vf_list)
    c_br = Counter(br_list)
    mejor = None
    for vi, n_vi in c_vi.most_common(6):
        for vf, n_vf in c_vf.most_common(6):
            dif = vf - vi
            if not (LITROS_MIN <= dif <= LITROS_MAX):
                continue
            for br, n_br in c_br.most_common(6):
                if abs(dif - br) <= 2:
                    apoyo = min(n_vi, n_vf, n_br)
                    total = n_vi + n_vf + n_br
                    cand = ((apoyo, total), vi, vf, br)
                    if mejor is None or cand[0] > mejor[0]:
                        mejor = cand
    return mejor
