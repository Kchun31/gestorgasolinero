import io
import os

os.environ.setdefault("OMP_THREAD_LIMIT", "1")

from PIL import Image, ImageChops, ImageFilter, ImageOps

try:
    import pytesseract
except Exception:
    pytesseract = None

ESC_PAGINA = 1.5
ANGULOS_PAGINA = (0, -3, 3, -6, 6, -9, 9)
UMBRALES_RECORTE = (110, 130, 150, 170)
WL_NUM = "0123456789"
WL_FECHA = "0123456789-: "


def abrir(img_bytes):
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("L")
    mayor = max(im.size)
    if mayor > 1800 or mayor < 1200:
        k = 1600.0 / mayor
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return im


def escalar(im, k):
    if k == 1:
        return im
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


def girar(im, ang):
    if not ang:
        return im
    return im.rotate(-ang, resample=Image.BICUBIC, expand=True, fillcolor=255)


def adaptativa(im, radio, c=14):
    fondo = im.filter(ImageFilter.BoxBlur(radio))
    return ImageChops.subtract(fondo, im).point(lambda p: 0 if p > c else 255)


def preparar_pagina(base, ang):
    g = girar(escalar(base, ESC_PAGINA), ang)
    return g, adaptativa(g, int(18 * ESC_PAGINA))


def lineas_pagina(bn):
    d = pytesseract.image_to_data(
        bn, lang="eng", config="--oem 3 --psm 6", output_type=pytesseract.Output.DICT
    )
    grupos = {}
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        if not t or float(d["conf"][i]) < 0:
            continue
        k = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        grupos.setdefault(k, []).append(
            (t.upper(), d["left"][i], d["top"][i], d["width"][i], d["height"][i])
        )
    lineas = [sorted(p, key=lambda w: w[1]) for p in grupos.values()]
    lineas.sort(key=lambda l: sum(w[2] for w in l) / len(l))
    return lineas


def texto_lineas(lineas):
    return "\n".join(" ".join(w[0] for w in l) for l in lineas)


def ocr_recorte(args):
    g, caja, th, esc, lista, psm, ang = args
    x0, y0, x1, y1 = (int(v) for v in caja)
    c = g.crop((max(0, x0), max(0, y0), min(g.width, x1), min(g.height, y1)))
    if c.width < 8 or c.height < 8:
        return ""
    if ang:
        c = girar(c, ang)
    c = escalar(c, esc)
    c = ImageOps.autocontrast(c, cutoff=1)
    c = c.point(lambda p: 255 if p > th else 0)
    c = ImageOps.expand(c, border=20, fill=255)
    cfg = f"--oem 3 --psm {psm} -c tessedit_char_whitelist=" + lista
    try:
        return pytesseract.image_to_string(c, lang="eng", config=cfg).strip()
    except Exception:
        return ""
