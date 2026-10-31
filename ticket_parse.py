import re
from collections import Counter
from datetime import datetime

LITROS_MIN = 2000
LITROS_MAX = 65000

RE_VOL = re.compile(r"VOL[UVN\w]*|V0L[UVN\w]*", re.I)
RE_BRUTO = re.compile(r"BRUT\w*|AUMENT\w*\s*B\w*", re.I)
RE_FECHA_LIN = re.compile(r"\b\d{1,4}[-/.\s]\d{1,2}[-/.\s]\d{2,4}\b")


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


def _limpiar_texto_fecha(txt):
    t = (txt or "").upper()
    t = re.sub(r"(?<=\d)O(?=\d)", "0", t)
    t = re.sub(r"(?<=\s)O(?=\d)", "0", t)
    t = re.sub(r"(?<=\d)[IL|](?=\d)", "1", t)
    return t


def fechahoras(txt):
    t = _limpiar_texto_fecha(txt)
    dts = []
    patron = r"\b(\d{1,4})[-/.\s]+(\d{1,2})[-/.\s]+(\d{2,4})\s+([0-2]?\d)[:.\s]([0-5]\d)\b"
    for m in re.finditer(patron, t):
        a, b, c, hh, mm = m.groups()
        ih, im = int(hh), int(mm)
        if not (0 <= ih <= 23 and 0 <= im <= 59):
            continue
        ia, ib, ic = int(a), int(b), int(c)
        if ia > 1900:
            year, mes, dia = ia, ib, ic
        else:
            dia, mes, year = ia, ib, (ic + 2000 if ic < 100 else ic)
        if mes > 12 and dia <= 12:
            dia, mes = mes, dia
        try:
            dts.append(datetime(year, mes, dia, ih, im))
        except ValueError:
            pass
    return dts


def _elegir_par_descarga(dts):
    if len(dts) < 2:
        return None
    if len(dts) == 2:
        return dts[0], dts[1]
    mejor = None
    mejor_score = -1e9
    n = len(dts)
    for i in range(n - 1):
        for j in range(i + 1, n):
            dt1, dt2 = dts[i], dts[j]
            diff_min = (dt2 - dt1).total_seconds() / 60.0
            score = 0
            if i == n - 2 and j == n - 1:
                score += 60
            elif i >= 1:
                score += 30
            if 5 <= diff_min <= 180:
                score += 120
            elif 1 <= diff_min < 5 or 180 < diff_min <= 300:
                score += 40
            elif diff_min <= 0:
                score -= 250
            else:
                score -= 90
            if score > mejor_score:
                mejor_score = score
                mejor = (dt1, dt2)
    return mejor


def par_de_texto(txt):
    t = _limpiar_texto_fecha(txt)
    dts = fechahoras(t)
    par = _elegir_par_descarga(dts)
    if par:
        return par
    fechas = []
    for m in re.finditer(r"\b(\d{2})[-/](\d{2})[-/](\d{2,4})\b", t):
        d, mes, y = m.groups()
        year = int(y) + (2000 if int(y) < 100 else 0)
        try:
            fechas.append((year, int(mes), int(d)))
        except ValueError:
            pass
    horas = []
    for m in re.finditer(r"(?<![\d/.\-])([0-2]?\d):([0-5]\d)\b", t):
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23:
            horas.append((hh, mm))
    if fechas and len(horas) >= 2:
        y, mes, d = fechas[-1]
        candidatos = []
        for hh, mm in horas:
            try:
                candidatos.append(datetime(y, mes, d, hh, mm))
            except ValueError:
                pass
        return _elegir_par_descarga(candidatos)
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
    if len(fechas) >= 2:
        cajas["fi"] = _caja_linea(fechas[-2])
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


def _variantes_confusion_termica(h_str):
    hh, mm = h_str.split(":")
    equivalentes = {
        "19": ["08", "09"],
        "18": ["08", "06"],
        "16": ["06", "08"],
        "10": ["00", "08"],
        "09": ["08"],
        "08": ["09", "06"],
    }
    return [f"{alt}:{mm}" for alt in equivalentes.get(hh, [])]


def resolver_par_horas(hi_list, hf_list):
    if not hi_list and not hf_list:
        return "", ""
    if not hi_list:
        hf, _, _ = moda(hf_list)
        return "", hf or ""
    if not hf_list:
        hi, _, _ = moda(hi_list)
        return hi or "", ""

    mi_mod, _, _ = moda([h.split(":")[1] for h in hi_list if ":" in h])
    mf_mod, _, _ = moda([h.split(":")[1] for h in hf_list if ":" in h])

    c_hi = Counter(hi_list)
    c_hf = Counter(hf_list)

    for h_raw, votos in list(c_hi.items()):
        for alt in _variantes_confusion_termica(h_raw):
            c_hi[alt] += max(1, votos // 2)
    for h_raw, votos in list(c_hf.items()):
        for alt in _variantes_confusion_termica(h_raw):
            c_hf[alt] += max(1, votos // 2)

    mejor_par = None
    mejor_score = -1e9

    for hi, n_i in c_hi.most_common(12):
        for hf, n_f in c_hf.most_common(12):
            diff = _a_min(hf) - _a_min(hi)
            bono_min = (2 if hi.endswith(f":{mi_mod}") else 0) + (2 if hf.endswith(f":{mf_mod}") else 0)
            votos_reales = hi_list.count(hi) + hf_list.count(hf)
            score = (n_i + n_f) * 3 + votos_reales * 2 + bono_min

            if 5 <= diff <= 150:
                score += 65
            elif 1 <= diff < 5 or 150 < diff <= 240:
                score += 25
            elif -1430 <= diff <= -1320:
                score += 15
            else:
                score -= 120

            if score > mejor_score:
                mejor_score = score
                mejor_par = (hi, hf)

    return mejor_par if mejor_par else (moda(hi_list)[0] or "", moda(hf_list)[0] or "")


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
