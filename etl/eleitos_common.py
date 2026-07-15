# -*- coding: utf-8 -*-
"""Helpers partilhados dos parsers de eleitos (mapas oficiais do Diário da República).

Fontes em `mapas_diario_da_republica/`; saída em `dados/eleitos/`.
A sigla de cada lista é normalizada para a chave usada nesse ano em
`dados/resultados/{prefix}_{ano}.json` (METADATA.parties), de modo que a
reconciliação com `mandatos_p` e a resolução de cores no site funcionem.
"""
import json
import re
import unicodedata
from pathlib import Path

from common import PROJECT_ROOT, CIRCULOS, strip_accents_upper

DR_DIR = PROJECT_ROOT / "mapas_diario_da_republica"
ELEITOS_DIR = PROJECT_ROOT / "dados" / "eleitos"
RESULTADOS_JSON_DIR = PROJECT_ROOT / "dados" / "resultados"

# ---------------------------------------------------------------------------
# Texto / nomes
# ---------------------------------------------------------------------------

_PT_PARTICLES = {"da", "das", "de", "do", "dos", "e", "d"}


def nfc(s):
    return unicodedata.normalize("NFC", s)


def clean_name(s):
    """Limpa um nome impresso: espaços, pontuação final, anotações, quebras."""
    s = nfc(str(s))
    s = s.replace("­", "")  # soft hyphen
    s = s.replace("0'Neill", "O'Neill").replace("0’Neill", "O’Neill")
    s = s.replace("0'NEILL", "O'NEILL").replace("0’NEILL", "O’NEILL")
    s = s.replace("Sant?ana", "Sant'ana").replace("SANT?ANA", "SANT'ANA").replace("Sant?Ana", "Sant'Ana")
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)   # anotações finais, ex.: "(pps/psd)"
    s = re.sub(r"^\d+\s*\.\s*", "", s)       # numeração de lista, ex.: "1. Nome"
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(".;,").strip()
    return s


def titlecase_pt(s):
    """ALL-CAPS -> Title Case com partículas portuguesas em minúsculas.

    Aplicar apenas quando o input está todo em maiúsculas (AU 2009-2025);
    nomes já em caixa mista passam intactos pelos parsers.
    """
    words = s.split(" ")
    out = []
    for i, w in enumerate(words):
        # preserva iniciais abreviadas ("J.", "M.ª") e apóstrofos (D'OREY)
        parts = re.split(r"(['’])", w)
        parts = [p.capitalize() if p not in ("'", "’") else p for p in parts]
        t = "".join(parts)
        if i > 0 and t.lower() in _PT_PARTICLES:
            t = t.lower()
        out.append(t)
    return " ".join(out)


def norm_name_if_caps(s):
    s = clean_name(s)
    letters = [c for c in s if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return titlecase_pt(s)
    return s


def slug(s):
    return strip_accents_upper(s)


# ---------------------------------------------------------------------------
# Círculos (AR/EE)
# ---------------------------------------------------------------------------

# nome impresso no DR -> código de círculo do site
_CIRCULO_BY_SLUG = {slug(v): k for k, v in CIRCULOS.items()}
_CIRCULO_EXTRA = {
    slug("Europa"): "E1",
    slug("Fora da Europa"): "E2",
    slug("Resto da Europa"): "E1",
    slug("Resto do Mundo"): "E2",
    slug("Emigração Europa"): "E1",
    slug("Emigração Fora da Europa"): "E2",
    slug("Região Autónoma da Madeira"): "30",
    slug("Região Autónoma dos Açores"): "40",
    slug("Funchal"): "30",
    slug("Ponta Delgada"): "40",
    slug("Angra do Heroísmo"): "40",
    slug("Horta"): "40",
}


def circulo_code(nome):
    s = slug(nome)
    return _CIRCULO_BY_SLUG.get(s) or _CIRCULO_EXTRA.get(s)


# ---------------------------------------------------------------------------
# Resultados existentes (para normalização de siglas e reconciliação)
# ---------------------------------------------------------------------------

def load_results(prefix, year):
    """Carrega dados/resultados/{prefix}_{year}.json (ex.: prefix='ar')."""
    p = RESULTADOS_JSON_DIR / f"{prefix}_{year}.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _sigla_variants(sigla):
    """Variantes de escrita de uma sigla DR para matching tolerante."""
    v = {sigla}
    v.add(sigla.replace(" ", ""))
    v.add(sigla.replace(".", ""))
    v.add(sigla.replace("-", ""))
    v.add(re.sub(r"[.\-\s]", "", sigla))
    return {slug(x) for x in v}


# sigla impressa no DR -> siglas alternativas usadas nos resultados de alguns anos
_GENERIC_ALIASES = {
    "PPD/PSD": ("PSD",),
    "PSD": ("PPD/PSD",),
    "CDS-PP": ("CDS",),
    "CDS": ("CDS-PP",),
    "B.E.": ("BE",),
    "PCP-PEV": ("CDU",),
    "PCP/PEV": ("PCP-PEV", "CDU"),
}


class SiglaResolver:
    """Resolve sigla impressa no DR -> chave de partido do JSON de resultados.

    1) match exato; 2) match por slug (sem pontuação/acentos);
    3) transforms específicos por ano/círculo (coligações unificadas no site);
    4) overrides manuais.
    """

    def __init__(self, parties_keys, year=None, election=None, overrides=None):
        self.keys = list(parties_keys)
        self.year = int(year) if year else None
        self.election = election
        self.overrides = overrides or {}
        self._by_slug = {}
        for k in self.keys:
            for s in _sigla_variants(k):
                self._by_slug.setdefault(s, k)

    def resolve(self, sigla_dr, circulo=None):
        sigla_dr = nfc(sigla_dr.strip())
        if sigla_dr in self.overrides:
            return self.overrides[sigla_dr]
        if sigla_dr in self.keys:
            return sigla_dr
        t = self._transform(sigla_dr, circulo)
        if t and t in self.keys:
            return t
        for s in _sigla_variants(sigla_dr):
            if s in self._by_slug:
                return self._by_slug[s]
        # aliases históricos genéricos (aplicados só se nada acima resolveu)
        for alias in _GENERIC_ALIASES.get(sigla_dr, ()):
            if alias in self.keys:
                return alias
        return None

    def _transform(self, sigla, circulo):
        """Espelha as unificações de coligações feitas em build_results*.py."""
        y = self.year
        if self.election == "ar":
            if y == 2025:
                if sigla == "PPD/PSD.CDS-PP.PPM" and circulo == "40":
                    return "AD Açores"
                if sigla in ("PPD/PSD.CDS-PP", "PPD/PSD.CDS-PP.PPM"):
                    return "AD"
            if y == 2024:
                if sigla == "PPD/PSD.CDS-PP" and circulo == "30":
                    return "Madeira Primeiro"
                if sigla in ("PPD/PSD.CDS-PP", "PPD/PSD.CDS-PP.PPM"):
                    return "AD"
            if y == 2022:
                if sigla == "PPD/PSD.CDS-PP":
                    return "Madeira Primeiro"
                if sigla == "PPD/PSD.CDS-PP.PPM":
                    return "AD Açores"
            if y == 2015:
                if sigla == "PPD/PSD.CDS-PP":
                    return "PàF"
                if sigla == "CDS-PP.PPM":
                    return "Aliança Açores"
            if y == 2002 and sigla in ("B.E.-UDP", "BE-UDP"):
                return "B.E."
            if y == 1980 and sigla in ("PS.FRS", "FRS"):
                return "FRS"
        return None


# ---------------------------------------------------------------------------
# Autárquicas: helpers partilhados (xlsx 2025 + PDFs 2005-2021)
# ---------------------------------------------------------------------------

def is_person_name(cell):
    """Nomes próprios nos mapas autárquicos vêm em maiúsculas, >= 2 palavras."""
    letters = [c for c in cell if c.isalpha()]
    return len(cell.split()) >= 2 and bool(letters) and all(c.isupper() for c in letters)


def slug_map(keys):
    return {strip_accents_upper(k): k for k in keys}


def match_votes_key(sigla, votes):
    """Casa a sigla impressa com a chave de votos dos resultados."""
    if sigla in votes:
        return sigla
    return slug_map(votes.keys()).get(strip_accents_upper(sigla))


def canonicalize_siglas(listas, local_keys):
    """Usa a grafia dos resultados como sigla canónica (ex.: mapa imprime
    "PS.PAN", resultados usam "PS - PAN"; GCE "MIPA" vs "I - MIPA")."""
    m = slug_map(local_keys or [])
    for k in (local_keys or []):
        # variantes sem o prefixo de numeração romana dos GCE
        alt = re.sub(r"^[IVX]+\s*-\s*", "", k)
        if alt != k:
            m.setdefault(strip_accents_upper(alt), k)
    for l in listas:
        canon = l["sigla"] if l["sigla"] in (local_keys or []) \
            else m.get(strip_accents_upper(l["sigla"]))
        if canon and canon != l["sigla"]:
            l["sigla_dr"] = l["sigla"]
            l["sigla"] = canon
    return listas


def resolve_leftover_siglas(listas, mandatos_p):
    """Casa listas com sigla não reconhecida às chaves sobrantes dos
    resultados quando o nº de eleitos identifica a chave sem ambiguidade.

    Necessário sobretudo em 2013, em que os resultados do site usam a
    numeração romana dos GCE ("I", "IX") e o mapa imprime a sigla real
    ("JPA", "MIB"). A sigla impressa fica em sigla_dr.
    """
    if not mandatos_p:
        return listas
    claimed = {l["sigla"] for l in listas}
    unclaimed = {k: v for k, v in mandatos_p.items()
                 if v and k not in claimed}
    for l in listas:
        if l["sigla"] in mandatos_p:
            continue
        cands = [k for k, v in unclaimed.items() if v == len(l["eleitos"])]
        if len(cands) == 1:
            l.setdefault("sigla_dr", l["sigla"])
            l["sigla"] = cands[0]
            del unclaimed[cands[0]]
    return listas


def compute_presidente(listas, votes):
    """Primeiro nome da lista mais votada; None se não conseguir casar votos."""
    best, best_v = None, -1
    for l in listas:
        k = match_votes_key(l["sigla"], votes or {})
        v = (votes or {}).get(k, 0)
        if v > best_v and l["eleitos"]:
            best, best_v = l, v
    if best and best_v >= 0:
        return {"nome": best["eleitos"][0], "sigla": best["sigla"]}
    return None


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

def write_eleitos_json(name, payload):
    ELEITOS_DIR.mkdir(parents=True, exist_ok=True)
    p = ELEITOS_DIR / name
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return p


def rebuild_index():
    """Regenera dados/eleitos/index.json a partir dos ficheiros presentes."""
    idx = {"ar": [], "ee": [], "au": {"cm": [], "am": [], "af": []},
           "au_presidente_only": [], "af_split": "distrito"}
    af_years = set()
    for p in sorted(ELEITOS_DIR.glob("*.json")):
        if p.name == "index.json":
            continue
        m = re.fullmatch(r"ar_(\d{4})\.json", p.name)
        if m:
            idx["ar"].append(m.group(1))
            continue
        m = re.fullmatch(r"ee_(\d{4})\.json", p.name)
        if m:
            idx["ee"].append(m.group(1))
            continue
        m = re.fullmatch(r"au_(cm|am)_(\d{4})\.json", p.name)
        if m:
            idx["au"][m.group(1)].append(m.group(2))
            with open(p, encoding="utf-8") as f:
                head = f.read(200)
            if '"presidente_only":true' in head.replace(" ", ""):
                idx["au_presidente_only"].append(m.group(2))
            continue
        m = re.fullmatch(r"au_af_(\d{4})_[0-9E]\w\.json", p.name)
        if m:
            af_years.add(m.group(1))
    idx["au"]["af"] = sorted(af_years, reverse=True)
    for k in ("ar", "ee"):
        idx[k] = sorted(set(idx[k]), reverse=True)
    for k in ("cm", "am"):
        idx["au"][k] = sorted(set(idx["au"][k]), reverse=True)
    idx["au_presidente_only"] = sorted(set(idx["au_presidente_only"]))
    with open(ELEITOS_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, separators=(",", ":"))
    return idx


# ---------------------------------------------------------------------------
# PDF (PyMuPDF)
# ---------------------------------------------------------------------------

_HEADER_FOOTER_RE = re.compile(
    r"(Di[áa]rio da Rep[úu]blica|DI[ÁA]RIO DA REP[ÚU]BLICA|^N\.[ºo°]|^\d+ de \w+ de \d{4}|"
    r"^P[áa]g\.|^\d+/\d+$|^Mapa Oficial|^\d{1,2}-\d{1,2}-\d{4}$|^1\.[ªa] s[ée]rie|"
    r"^I S[ÉE]RIE|^S[ÉE]RIE|^\d{3,4}-?\(\d+\)$|^\d{6,}$)", re.IGNORECASE)


def is_header_footer(line):
    line = line.strip()
    if not line:
        return True
    return bool(_HEADER_FOOTER_RE.search(line))


def pdf_lines(path, page_range=None):
    """Linhas de texto do PDF, filtrando cabeçalhos/rodapés do DR."""
    import fitz
    doc = fitz.open(path)
    pages = range(len(doc)) if page_range is None else page_range
    out = []
    for pno in pages:
        for raw in doc[pno].get_text().splitlines():
            line = nfc(raw).strip()
            if line and not is_header_footer(line):
                out.append(line)
    doc.close()
    return out
