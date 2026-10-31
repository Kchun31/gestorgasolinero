import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ticket_imagen import (
    pytesseract, ANGULOS_PAGINA, UMBRALES_RECORTE, WL_NUM, WL_FECHA,
    abrir, preparar_pagina, lineas_pagina, texto_lineas, ocr_recorte,
)
from ticket_parse import (
    LITROS_MIN, LITROS_MAX, RE_VOL, RE_BRUTO,
    numeros, fechahoras, par_de_texto, producto_ticket, puntuar,
    localizar, moda, mejor_triple, _linea_con,
)

FORMATO_FECHA = "%d/%m/%Y"
TOLERANCIA_REF = 0.08
NUCLEOS = max(1, min(4, os.cpu_count() or 2))
SCORE_MIN = 3
VARIANTES_RECORTE = 2
MIN_VOTOS = 2
CLAVES = ("vi", "vf", "br", "di", "hi", "df", "hf", "tq")


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


def _variante(base, ang):
    g, bn = preparar_pagina(base, ang)
    lineas = lineas_pagina(bn)
    return {"ang": ang, "g": g, "lineas": lineas, "score": puntuar(lineas)}


def _voto_fecha(v, dt, quien):
    v["d" + quien].append(dt.strftime("%Y-%m-%d"))
    v["h" + quien].append(dt.strftime("%H:%M"))


def _votos_pagina(variantes):
    v = {k: [] for k in CLAVES}
    for var in variantes:
        if var["score"] < SCORE_MIN:
            continue
        lineas = var["lineas"]
        vol = _linea_con(lineas, RE_VOL)
        if len(vol) >= 2:
            for clave, l in (("vi", vol[0]), ("vf", vol[-1])):
                n = numeros(" ".join(w[0] for w in l))
                if n:
                    v[clave].append(n[0])
        for l in _linea_con(lineas, RE_BRUTO)[-1:]:
            n = numeros(" ".join(w[0] for w in l))
            if n:
                v["br"].append(n[-1])
        par = par_de_texto(texto_lineas(lineas))
        if par:
            _voto_fecha(v, par[0], "i")
            _voto_fecha(v, par[1], "f")
        tq = producto_ticket(lineas)
        if tq:
            v["tq"].append(tq)
    return v


def _trabajos_recorte(variantes):
    trabajos = []
    buenas = [x for x in sorted(variantes, key=lambda x: -x["score"]) if x["score"] >= SCORE_MIN]
    for var in buenas[:VARIANTES_RECORTE]:
        for clave, caja in localizar(var["lineas"]).items():
            es_fecha = clave in ("fi", "ff")
            lista = WL_FECHA if es_fecha else WL_NUM
            angs = (0,) if es_fecha else (0, 1.5, -1.5)
            for th in UMBRALES_RECORTE:
                for esc in (2, 3):
                    for a in angs:
                        trabajos.append((clave, (var["g"], caja, th, esc, lista, 7, a)))
    return trabajos


def _votos_recorte(ex, trabajos, v):
    textos = list(ex.map(lambda t: ocr_recorte(t[1]), trabajos))
    for (clave, _), t in zip(trabajos, textos):
        if clave in ("vi", "vf", "br"):
            grupos = re.findall(r"\d{4,6}", t)
            if grupos:
                v[clave].append(int(grupos[0]))
        else:
            dts = fechahoras(t)
            if dts:
                _voto_fecha(v, dts[0], "i" if clave == "fi" else "f")


def extraer_tira_ocr_local(img_bytes, litros_ref=0.0):
    r = _vacio()
    if pytesseract is None:
        r["alertas"].append("pytesseract no está instalado; capture los datos en la Mesa de Control.")
        return r
    try:
        base = abrir(img_bytes)
        with ThreadPoolExecutor(max_workers=NUCLEOS) as ex:
            variantes = list(ex.map(lambda a: _variante(base, a), ANGULOS_PAGINA))
            v = _votos_pagina(variantes)
            _votos_recorte(ex, _trabajos_recorte(variantes), v)
        _resolver(r, v, litros_ref)
    except Exception as e:
        r["alertas"].append(f"Falló el OCR local ({type(e).__name__}); use la Mesa de Control.")
        r["confianza"] = "nula"
    return r


def _resolver_bruto(r, v):
    tri = mejor_triple(v["vi"], v["vf"], v["br"])
    if tri and tri[0][0] >= MIN_VOTOS:
        r["litros_descargados"] = float(tri[3])
        return True
    a, na, _ = moda(v["vi"])
    b, nb, _ = moda(v["vf"])
    if a and b and min(na, nb) >= MIN_VOTOS and LITROS_MIN <= b - a <= LITROS_MAX:
        r["litros_descargados"] = float(b - a)
        r["alertas"].append(
            "Aumento Bruto calculado como volumen final − inicial (el impreso no se leyó); puede diferir 1 L."
        )
    else:
        r["alertas"].append("No se pudo leer el Aumento Bruto con certeza; capturarlo en la Mesa de Control.")
    return False


def _resolver_fechas(r, v):
    fecha, nf, _ = moda(v["di"] + v["df"])
    hi, n_hi, _ = moda(v["hi"])
    hf, n_hf, _ = moda(v["hf"])
    di, _, _ = moda(v["di"])
    df, _, _ = moda(v["df"])
    if fecha and nf >= MIN_VOTOS:
        r["fecha"] = datetime.strptime(fecha, "%Y-%m-%d").strftime(FORMATO_FECHA)
    if hi and n_hi >= MIN_VOTOS:
        r["hora_inicio"] = hi
    if hf and n_hf >= MIN_VOTOS:
        r["hora_termino"] = hf
    if not (r["fecha"] and r["hora_inicio"] and r["hora_termino"]):
        r["alertas"].append("No se leyeron con certeza fecha y horas; capturarlas en la Mesa de Control.")
    elif di and df and di != df:
        r["alertas"].append("La descarga parece cruzar la medianoche; verifique la fecha.")
    elif r["hora_termino"] < r["hora_inicio"]:
        r["alertas"].append("La hora de término es anterior al inicio; verifique.")


def _resolver(r, v, litros_ref):
    verificado = _resolver_bruto(r, v)
    bruto = r["litros_descargados"]
    if bruto and litros_ref and abs(bruto - litros_ref) / litros_ref > TOLERANCIA_REF:
        r["alertas"].append("El Aumento Bruto difiere más de 8% de los litros facturados.")
    _resolver_fechas(r, v)
    tq, _, _ = moda(v["tq"])
    if tq:
        r["tanque_vr"] = tq
    completo = bool(bruto and r["fecha"] and r["hora_inicio"] and r["hora_termino"])
    if completo:
        r["confianza"] = "alta" if (verificado and tq and not r["alertas"]) else "media"
    else:
        r["confianza"] = "baja"
    if r["confianza"] != "alta":
        r["alertas"].append("Confirme los datos del ticket en la Mesa de Control antes de generar el PDF.")
