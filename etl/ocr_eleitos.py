# -*- coding: utf-8 -*-
"""Infraestrutura OCR para os mapas antigos (scans / fontes corrompidas).

Renderiza páginas a 300 dpi (cinzento) com PyMuPDF e passa-as pelo Tesseract
(`-l por`), guardando sidecars TSV em scratch/ocr/{tag}/page_NNNN.tsv.
O OCR corre uma vez; os parsers releem os sidecars de graça.

Uso:
    python ocr_eleitos.py <tag> [primeira-última]
Tags definidas em OCR_SOURCES (ex.: ar_1995, au_2001).

Helpers para os parsers:
    ocr_words(tag, pno)     -> [(x0, y0, x1, y1, texto, conf), ...]
    ocr_lines(words, ...)   -> linhas [(y, [(x, texto, conf), ...])]
    column_lines(words, split_x) -> texto por colunas na ordem de leitura
"""
import csv
import os
import sys
from pathlib import Path

import fitz

from common import PROJECT_ROOT
from eleitos_common import DR_DIR, nfc

OCR_DIR = PROJECT_ROOT / "scratch" / "ocr"

TESSERACT = os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe")
if not os.path.exists(TESSERACT):
    TESSERACT = "tesseract"  # PATH

AR_DIR = DR_DIR / "assembleia da republica"
AU_DIR = DR_DIR / "autarquicas"

OCR_SOURCES = {
    "ar_1975": AR_DIR / "resultados_ac_1975.pdf",
    "ar_1976": AR_DIR / "MapaOficialEleicoesAbril1976.pdf",
    "ar_1979": AR_DIR / "MapaOficialEleicoesDezembro1979.pdf",
    "ar_1980": AR_DIR / "MapaOficialEleicoesOutubro1980.pdf",
    "ar_1983": AR_DIR / "MapaOficialEleicoesAbril1983.pdf",
    "ar_1985": AR_DIR / "MapaOficialEleicoesOutubro1985.pdf",
    "ar_1987": AR_DIR / "MapaOficialEleicoesJulho1987.pdf",
    "ar_1991": AR_DIR / "MapaOficialEleicoesOutubro1991.pdf",
    "ar_1995": AR_DIR / "MapaOficialEleicoesOutubro1995.pdf",
    "au_2001": AU_DIR / "resultados_al_2001.pdf",
}

DPI = 300

# perfis por tag para scans difíceis: (dpi, limiar de binarização)
OCR_PROFILES = {
    "ar_1975": (400, 160),
}


def _pytesseract():
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT
    return pytesseract


def sidecar_path(tag, pno):
    return OCR_DIR / tag / f"page_{pno + 1:04d}.tsv"


def ocr_page(tag, pno, force=False):
    """OCR de uma página -> sidecar TSV. Devolve o caminho."""
    out = sidecar_path(tag, pno)
    if out.exists() and not force:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    pytesseract = _pytesseract()
    dpi, threshold = OCR_PROFILES.get(tag, (DPI, None))
    doc = fitz.open(OCR_SOURCES[tag])
    pix = doc[pno].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    import PIL.Image
    img = PIL.Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if threshold is not None:
        img = img.point(lambda p: 255 if p > threshold else 0)
    data = pytesseract.image_to_data(
        img, lang="por", config="--psm 4",
        output_type=pytesseract.Output.DICT)
    scale = 72.0 / dpi   # de pixels para pontos PDF
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["x0", "y0", "x1", "y1", "conf", "line", "text"])
        for i, txt in enumerate(data["text"]):
            txt = nfc(txt.strip())
            if not txt:
                continue
            x, y = data["left"][i] * scale, data["top"][i] * scale
            ww, hh = data["width"][i] * scale, data["height"][i] * scale
            # id de linha do próprio tesseract (robusto a scans inclinados)
            line_id = f"{data['block_num'][i]}.{data['par_num'][i]}.{data['line_num'][i]}"
            w.writerow([f"{x:.1f}", f"{y:.1f}", f"{x + ww:.1f}", f"{y + hh:.1f}",
                        data["conf"][i], line_id, txt])
    return out


MIN_WORD_CONF = 34   # palavras-fantasma do ruído do scan têm conf ínfima


def ocr_words(tag, pno):
    """Palavras do sidecar (OCR se preciso):
    [(x0, y0, x1, y1, texto, conf, line_id), ...]."""
    path = ocr_page(tag, pno)
    words = []
    with open(path, encoding="utf-8") as f:
        rd = csv.reader(f, delimiter="\t")
        next(rd, None)
        for row in rd:
            if len(row) < 7:
                continue
            x0, y0, x1, y1 = (float(v) for v in row[:4])
            conf = float(row[4])
            if 0 <= conf < MIN_WORD_CONF:
                continue
            words.append((x0, y0, x1, y1, row[6], conf, row[5]))
    return words


def page_count(tag):
    return len(fitz.open(OCR_SOURCES[tag]))


def ocr_lines(words, y_tol=None):
    """Agrupa palavras em linhas pelo id de linha do tesseract (robusto a
    scans inclinados): [(y, [(x, texto, conf), ...]), ...] por ordem de y."""
    by_line = {}
    for x0, y0, x1, y1, txt, conf, line_id in words:
        by_line.setdefault(line_id, []).append((x0, (y0 + y1) / 2, txt, conf))
    lines = []
    for items in by_line.values():
        items.sort()
        y = sum(i[1] for i in items) / len(items)
        lines.append((y, [(x, t, c) for x, _, t, c in items]))
    lines.sort()
    return lines


def column_lines(words, split_x, y_tol=4.0):
    """Linhas de texto por coluna (esquerda depois direita), com confiança
    mínima da linha: [(texto, min_conf), ...]."""
    out = []
    for side in (lambda w: (w[0] + w[2]) / 2 < split_x,
                 lambda w: (w[0] + w[2]) / 2 >= split_x):
        col = [w for w in words if side(w)]
        for _, items in ocr_lines(col, y_tol):
            txt = " ".join(t for _, t, _ in items).strip()
            confs = [c for _, _, c in items if c >= 0]
            if txt:
                out.append((txt, min(confs) if confs else -1))
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in OCR_SOURCES:
        print("uso: python ocr_eleitos.py <tag> [primeira-última]")
        print("tags:", ", ".join(OCR_SOURCES))
        return 1
    tag = sys.argv[1]
    n = page_count(tag)
    lo, hi = 1, n
    if len(sys.argv) > 2:
        a, _, b = sys.argv[2].partition("-")
        lo, hi = int(a), int(b or a)
    for pno in range(lo - 1, min(hi, n)):
        path = ocr_page(tag, pno)
        print(f"{tag} p{pno + 1}/{n} -> {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
