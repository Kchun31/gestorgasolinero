import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ticket_imagen import (
    pytesseract, UMBRALES, _abrir, _girar, _palabras, _localizar,
    _caja_vol, _caja_fecha, _ocr_recorte, _ocr_pagina,
)

FORMATO_FECHA = "%d/%m/%Y"
ANGULOS = (0, 2, -2)
TOLERANCIA_REF = 0.08
LITROS_MIN, LITROS_MAX = 500.0, 65000.0
RE_FECHAHORA = re.compile(
    r"(\d{2})\s*[-/.]\s*(\d{2})\s*[-/.]\s*(\d{2,4})\s+(\d{1,2})\s*[:.;]\s*(\d{2})"
)
RE_TANQUE = re.compile(r"\bT\s*([1-9])\s*[:.°;]?\s*(MAG|DIE|PRE|REG)", re.IGNORECASE)
PRODUCTOS = {"MAG": "MAGNA", "REG": "MAGNA", "DIE": "DIÉSEL", "PRE": "PREMIUM"}


def _vacio():
    return {
        "litros_descargados": 0.0,
        "fecha": "",
        "hora_inicio": "",
        "hora_termino": "",
        "tanque_vr": "",
        "confianza": "nula",
        "alertas": [],
    }


def _parsear_fechahora(texto):
    salida = []
    for m in RE_FECHAHORA.finditer(texto):
        d, mes, a, h, mi = (int(x) for x in m.groups())
        a = a + 2000 if a < 100 else a
        try:
            datetime(a, mes, d, h, mi)
        except ValueError:
            continue
        salida.append((f"{a:04d}-{mes:02d}-{d:02d}", f"{h:02d}:{mi:02d}"))
    return salida


def _moda(valores, absorber=False):
    if not valores:
        return None, 0, 0
    cuenta = Counter(valores)
    if absorber:
        puntos = dict(cuenta)
        for corto in list(cuenta):
            largos = [l for l in cuenta if len(str(l)) > len(str(corto)) and str(l).startswith(str(corto))]
            if largos:
                puntos[max(largos, key=lambda l: cuenta[l])] += cuenta[corto]
        cuenta = Counter(puntos)
    v, n = cuenta.most_common(1)[0]
    return v, min(n, len(valores)), len(valores)


def extraer_tira_ocr_local(img_bytes, litros_ref=0.0):
    r = _vacio()
    if pytesseract is None:
        r["alertas"].append("pytesseract no está instalado; capture los datos en la Mesa de Control.")
        return r
    try:
        base = _abrir(img_bytes)
        with ThreadPoolExecutor(max_workers=4) as ex:
            giradas = [(a, _girar(base, a)) for a in ANGULOS]
            locs = list(ex.map(lambda t: _localizar(_palabras(t[1])), giradas))
            k = max(range(len(locs)), key=lambda i: locs[i]["score"])
            im, loc = giradas[k][1], locs[k]
            textos = list(ex.map(_ocr_pagina, [(im, th) for th in (120, 140, 160)]))
            jobs = {"vi": [], "vf": [], "fi": [], "ff": []}
            if loc["vol"]:
                jobs["vi"] = _caja_vol(loc["vol"][0], loc["pal"])
                jobs["vf"] = _caja_vol(loc["vol"][1], loc["pal"])
            for clave, p in (("fi", loc["ini"]), ("ff", loc["fin"])):
                jobs[clave] = _caja_fecha(p) if p else None
            lectura = {}
            for clave, caja in jobs.items():
                if not caja:
                    lectura[clave] = []
                    continue
                lista = "0123456789" if clave in ("vi", "vf") else "0123456789-: "
                angs = (0, 1, 2) if clave in ("vi", "vf") else (0,)
                args = [(im, caja, th, esc, lista, psm, a)
                        for th in UMBRALES for esc in (2, 3) for psm in (7, 8) for a in angs]
                lectura[clave] = list(ex.map(_ocr_recorte, args))

        def numeros(clave):
            vals = [re.sub(r"\D", "", t) for t in lectura.get(clave, [])]
            return [int(v) for v in vals if 4 <= len(v) <= 6]

        vi, n_vi, t_vi = _moda(numeros("vi"), True)
        vf, n_vf, t_vf = _moda(numeros("vf"), True)
        if vi is None or vf is None:
            vi2 = re.findall(r"VOLUMEN\D{0,8}(\d{4,6})", " ".join(textos).upper())
            if len(vi2) >= 2 and vi is None and vf is None:
                vi, vf, n_vi, n_vf, t_vi, t_vf = int(vi2[0]), int(vi2[-1]), 1, 1, 3, 3
                r["alertas"].append("Volúmenes leídos de texto completo (baja precisión).")
        bruto = float(vf - vi) if vi is not None and vf is not None and vf > vi else 0.0
        if bruto and not (LITROS_MIN <= bruto <= LITROS_MAX):
            r["alertas"].append(f"Aumento Bruto fuera de rango ({bruto:.0f} L); verifique.")
            bruto = 0.0
        if bruto:
            r["litros_descargados"] = round(bruto, 2)
            if min(n_vi / t_vi, n_vf / t_vf) < 0.5:
                r["alertas"].append("Dígitos de volumen poco concluyentes; verifique el Aumento Bruto.")
            if litros_ref and abs(bruto - litros_ref) / litros_ref > TOLERANCIA_REF:
                r["alertas"].append("El Aumento Bruto difiere más de 8% de los litros facturados.")
        else:
            r["alertas"].append("No se pudo calcular el Aumento Bruto; capturarlo en la Mesa de Control.")

        votos_i, votos_f = [], []
        for t in lectura.get("fi", []):
            votos_i += _parsear_fechahora(t)[:1]
        for t in lectura.get("ff", []):
            votos_f += _parsear_fechahora(t)[:1]
        for tx in textos:
            enc = _parsear_fechahora(tx)
            if len(enc) >= 2:
                votos_i.append(enc[0])
                votos_f.append(enc[-1])
        mi, n_i, t_i = _moda(votos_i)
        mf, n_f, t_f = _moda(votos_f)
        di, hi = mi if mi else ("", "")
        df, hf = mf if mf else ("", "")
        if di and hi:
            r["fecha"] = datetime.strptime(di, "%Y-%m-%d").strftime(FORMATO_FECHA)
            r["hora_inicio"] = hi
        else:
            r["alertas"].append("No se leyeron fecha/hora de inicio.")
        if df and hf:
            r["hora_termino"] = hf
            if di and (df, hf) < (di, hi):
                r["alertas"].append("La hora de término es anterior al inicio; verifique.")
        else:
            r["alertas"].append("No se leyó la hora de término.")

        for tx in textos:
            m = RE_TANQUE.search(tx)
            if m:
                r["tanque_vr"] = f"T{m.group(1)}: {PRODUCTOS[m.group(2).upper()[:3]]}"
                break

        fuertes = (
            t_vi and n_vi / t_vi >= 0.4 and t_vf and n_vf / t_vf >= 0.4
            and n_i >= 2 and n_f >= 2
        ) if (vi and vf and votos_i and votos_f) else False
        if bruto and r["fecha"] and r["hora_inicio"] and r["hora_termino"]:
            r["confianza"] = "alta" if fuertes and not r["alertas"] else "media"
        else:
            r["confianza"] = "baja"
        if r["confianza"] != "alta":
            r["alertas"].append("Confirme los datos del ticket en la Mesa de Control antes de generar el PDF.")
    except Exception as e:
        r["alertas"].append(f"Fallo el OCR local ({type(e).__name__}); use la Mesa de Control.")
        r["confianza"] = "nula"
    return r
