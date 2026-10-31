import io

from extractor_factura import (
    normalizar_litros,
    extraer_datos_xml_cfdi,
    extraer_datos_factura_local,
)
from extractor_ticket import extraer_tira_ocr_local

__all__ = [
    "normalizar_litros",
    "extraer_datos_xml_cfdi",
    "extraer_datos_factura_local",
    "extraer_tira_ocr_local",
    "texto_desde_pdf",
]


def texto_desde_pdf(pdf_bytes):
    lector = None
    try:
        from pypdf import PdfReader as lector
    except Exception:
        try:
            from PyPDF2 import PdfReader as lector
        except Exception:
            return ""
    try:
        reader = lector(io.BytesIO(pdf_bytes))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""
