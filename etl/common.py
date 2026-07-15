# -*- coding: utf-8 -*-
"""Constantes e helpers partilhados do ETL do Observatório Portugal."""
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAPAS_DIR = PROJECT_ROOT / "mapas"
RESULTADOS_DIR = PROJECT_ROOT / "resultados" / "assembleia da republica"
RAW_DIR = RESULTADOS_DIR / "resultados puros (sem alteração minha)"
OUT_DIR = PROJECT_ROOT / "dados"

YEARS = [1975, 1976, 1979, 1980, 1983, 1985, 1987, 1991, 1993, 1995, 1997, 1999,
         2002, 2005, 2009, 2011, 2015, 2019, 2022, 2024, 2025, 2026]

# Círculos com geometria: 18 distritos + regiões autónomas.
# Madeira = códigos DICOFRE 31/32; Açores = 41..49.
CIRCULOS = {
    "01": "Aveiro", "02": "Beja", "03": "Braga", "04": "Bragança",
    "05": "Castelo Branco", "06": "Coimbra", "07": "Évora", "08": "Faro",
    "09": "Guarda", "10": "Leiria", "11": "Lisboa", "12": "Portalegre",
    "13": "Porto", "14": "Santarém", "15": "Setúbal", "16": "Viana do Castelo",
    "17": "Vila Real", "18": "Viseu", "30": "Madeira", "40": "Açores",
    "E1": "Europa", "E2": "Fora da Europa",
}

# bbox de sanidade (lon/lat WGS84) por região.
# O continente inclui a zona de "inset" onde os mapas família E colocam
# Madeira/Açores deslocadas para exibição junto ao continente (lon até -12).
BBOX_CONTINENTE = (-12.2, 36.5, -6.1, 42.25)
BBOX_MADEIRA = (-17.5, 29.9, -15.2, 33.3)
BBOX_ACORES = (-31.5, 36.8, -24.9, 39.9)


OLD_CONC_TO_MODERN = {
    "1901": "4301", "1902": "4501", "1903": "4401", "1904": "4502", "1905": "4302",
    "2001": "4901", "2002": "4701", "2003": "4801", "2004": "4601", "2005": "4602",
    "2006": "4802", "2007": "4603",
    "2101": "4201", "2102": "4202", "2103": "4203", "2104": "4204", "2105": "4205",
    "2106": "4206", "2107": "4101",
    "2201": "3101", "2202": "3102", "2203": "3103", "2204": "3104", "2205": "3105",
    "2206": "3106", "2207": "3201", "2208": "3107", "2209": "3108", "2210": "3109",
    "2211": "3110",
}


def norm_dicofre(v):
    """Normaliza um código DICOFRE para 6 caracteres (Excel perde zeros à esquerda).

    Nota: alguns códigos são alfanuméricos (ex.: uniões de freguesias de Barcelos
    '0302FA'..'0302FH', usados tanto na CAOP como nos resultados oficiais).
    """
    if v is None:
        return None
    s = str(v).strip().upper()
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"[^0-9A-Z]", "", s)
    if not s or not s[:1].isdigit():
        return None
    if s.isdigit():
        if len(s) <= 2:
            s = s.zfill(2) + "0000"
        elif len(s) <= 4:
            s = s.zfill(4) + "00"
        else:
            s = s.zfill(6)
    if len(s) == 6:
        return s
    return None


def dhondt(votes, seats):
    """Distribuição de `seats` lugares pelos votos (método de Hondt)."""
    quo = []
    for p, v in votes.items():
        for d in range(1, seats + 1):
            quo.append((v / d, p))
    quo.sort(key=lambda x: x[0], reverse=True)
    out = defaultdict(int)
    for _, p in quo[:seats]:
        out[p] += 1
    return dict(out)


def circulo_from_dicofre(dicofre):
    """'01'..'18' continente; 31/32 -> '30' (Madeira); 4x -> '40' (Açores)."""
    dt = dicofre[:2]
    n = int(dt)
    if 1 <= n <= 18:
        return dt
    if n in (31, 32):
        return "30"
    if 40 <= n <= 49:
        return "40"
    return None


def is_freguesia_code(code):
    """True se o código de 6 caracteres é uma freguesia real (não agregado D/C/nacional)."""
    if not code or not re.fullmatch(r"\d{4}[0-9A-Z]{2}", code):
        return False
    if code.endswith("00"):
        return False
    return circulo_from_dicofre(code) is not None


MOJIBAKE_MARKERS = ("\uFFFD",)


def has_mojibake(text):
    if not isinstance(text, str):
        return False
    if any(m in text for m in MOJIBAKE_MARKERS):
        return True
    # Letra + interrogação + letra (ex: S?o, Agad?o, ?gueda)
    if re.search(r"[a-zA-ZÀ-ÿ]\?[a-zA-ZÀ-ÿ]", text) or text.startswith("?"):
        return True
    # Mojibakes de UTF-8 lidos como Latin1/cp1252 (ex: Ã¡, Ã§, Ã£)
    if re.search(r"Ã[¡¢£¤¥§©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ]", text):
        return True
    return False


def strip_accents_upper(s):
    """Slug simples para comparação de nomes (QA)."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s.upper())
