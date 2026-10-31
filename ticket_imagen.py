import io
import re

from PIL import Image, ImageOps

try:
    import pytesseract
except Exception:
    pytesseract = None

UMBRALES = (110, 130, 150, 170)


def _abrir(img_bytes):
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("L")
    mayor = max(im.size)
    if mayor > 1600 or mayor < 1000:
        k = 1600.0 / mayor
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return ImageOps.autocontrast(im, cutoff=1)


def _girar(im, ang):
    if not ang:
        return im
    return im.rotate(-ang, resample=Image.BICUBIC, expand=True, fillcolor=255)


def _bin(im, th):
    return im.point(lambda p: 255 if p > th else 0)


def _palabras(im):
    d = pytesseract.image_to_data(
        _bin(im, 130), lang="eng", config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT,
    )
    out = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip().upper()
        if t and float(d["conf"][i]) >= 0:
            out.append((t, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
    return out


def _localizar(pal):
    vol = sorted([p for p in pal if "LUME" in p[0] or p[0].startswith("VOLU")], key=lambda p: p[2])
    if len(vol) >= 2 and vol[-1][2] - vol[0][2] > 200:
        vol = [vol[0], vol[-1]]
    else:
        vol = []
    ini = next((p for p in pal if p[0].startswith("INIC")), None)
    fin = next((p for p in pal if p[0] == "FIN"), None)
    score = (2 if vol else 0) + (1 if ini else 0) + (1 if fin else 0)
    return {"vol": vol, "ini": ini, "fin": fin, "score": score, "pal": pal}


def _caja_vol(p, pal):
    _, x, y, w, h = p
    cand = [
        q for q in pal
        if q[1] > x + w and abs((q[2] + q[4] / 2) - (y + h / 2)) < 1.1 * h
        and sum(ch.isdigit() for ch in q[0]) >= 3
    ]
    if cand:
        n = max(cand, key=lambda q: sum(ch.isdigit() for ch in q[0]))
        return (max(0, int(n[1] - 0.4 * h)), max(0, int(n[2] - 0.1 * h)),
                int(n[1] + 4.4 * h), int(n[2] + n[4] + 0.3 * h))
    return (max(0, int(x + 1.5 * w)), max(0, int(y - 0.2 * h)), int(x + 2.5 * w), int(y + 1.9 * h))


def _caja_fecha(p):
    _, x, y, w, h = p
    return (max(0, int(x + 2.5 * h)), max(0, int(y + 0.9 * h)), int(x + 18 * h), int(y + 3.2 * h))


def _ocr_recorte(args):
    im, caja, th, escala, lista, psm, ang = args
    c = im.crop(caja)
    if c.width < 5 or c.height < 5:
        return ""
    if ang:
        c = c.rotate(-ang, resample=Image.BICUBIC, expand=True, fillcolor=255)
    c = c.resize((int(c.width * escala), int(c.height * escala)), Image.LANCZOS)
    c = ImageOps.autocontrast(c, cutoff=1)
    c = ImageOps.expand(_bin(c, th), border=20, fill=255)
    cfg = f"--oem 3 --psm {psm} -c tessedit_char_whitelist=" + lista
    return pytesseract.image_to_string(c, lang="eng", config=cfg).strip()


def _ocr_pagina(args):
    im, th = args
    return pytesseract.image_to_string(_bin(im, th), lang="eng", config="--oem 3 --psm 6")
