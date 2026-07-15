# -*- coding: utf-8 -*-
"""Eleitos das Autárquicas 2001 a partir do mapa oficial do DR (OCR).

O PDF (resultados_al_2001.pdf, 722 pp) tem o texto corrompido (ToUnicode
partido), mas o render digital é perfeito — usa-se OCR (sidecars de
ocr_eleitos.py, tag au_2001). A secção ELEITOS ocupa as pp. 651-721
(bissetada: p. 650 ainda é de resultados), em 2 colunas:

    CONCELHO: X
    ASSEMBLEIA MUNICIPAL / CÂMARA MUNICIPAL
    Assembleia de Freguesia: Y
    Nome do eleito ..................... SIGLA
    Plenário de cidadãos eleitores       (freguesias sem assembleia)
    I - "Denominação do GCE"             (legenda: a sigla das linhas
    PS/CDS-PP - Coligação ...             resolve-se pelos resultados)

Uso: python build_eleitos_au_2001.py
Saídas: au_cm_2001.json, au_am_2001.json, au_af_2001_{dd}.json + index.
"""
import json
import re
import sys

from collections import defaultdict

from common import PROJECT_ROOT, circulo_from_dicofre
from build_eleitos_au_2005 import clean_matching_name
from build_eleitos_au_pdf import _match_freg_by_name
from eleitos_common import (canonicalize_siglas, compute_presidente,
                            load_results, nfc, resolve_leftover_siglas,
                            write_eleitos_json, rebuild_index)
from eleitos_overrides import apply_overrides, apply_sigla_aliases
from ocr_eleitos import OCR_SOURCES, TESSERACT

YEAR = 2001
# o PDF alterna resultados/eleitos POR DISTRITO — varre-se tudo; as zonas
# de resultados são cortadas por linha (INSCRITOS/VOTANTES/...)
PAGES = range(0, 722)
SPLIT_X = 295             # fronteira entre as 2 colunas (pontos PDF)
SIGLA_GAP = 30            # gap mínimo entre o nome e a célula da sigla

RE_SIGLA = re.compile(r"^[A-ZÀ-Ü0-9][A-ZÀ-Ü0-9./\-]{0,17}$")
RE_HEADER_PAG = re.compile(
    r"(DI[ÁA]RIO DA REP[ÚU]BLICA|S[ÉE]RIE|^N\.?[ºo°]|^\d{4}-\(\d+\)$|"
    r"27 de Mar[çc]o)", re.IGNORECASE)
RE_CONCELHO = re.compile(r"^CONCELHO\s*:?\s*(?P<nome>.+)$")
RE_DISTRITO = re.compile(r"^DISTRITO\s*:", re.IGNORECASE)
RE_AF = re.compile(r"^Assembleia\s+de\s+Freguesia\s*:\s*(?P<nome>.+)$",
                   re.IGNORECASE)
RE_LEGENDA = re.compile(r"^\S{1,12}\s*-\s*[«\"“]|Coliga[çc][ãa]o\s")
RE_PLENARIO = re.compile(r"Plen[áa]rio de cidad[ãa]os", re.IGNORECASE)

# headers "CONCELHO: X" cuja fonte forte o OCR destrói (verificados no
# render da página): fragmento estável -> nome real do concelho
CONCELHO_FIXES = {
    "SÃ ÃO DA PE EIRA": "São João da Pesqueira",   # p. 666
}

# headers impressos no mapa mas OMITIDOS pelo Tesseract (verificados nos
# renders das páginas): página (1-based) -> [(âncora, linha a injetar após)]
LINE_INJECTIONS = {
    59: [("Maria Rita Valente Paulino", "CONCELHO: VIDIGUEIRA")],
    279: [("Fernando Manuel Cortes", "CÂMARA MUNICIPAL")],
    459: [("Virgílio Alberto Plácido de Queirós Costa", "CÂMARA MUNICIPAL")],
    569: [("Fernando Costa Araújo", "CÂMARA MUNICIPAL")],
}


OCR_COLS_DIR = PROJECT_ROOT / "scratch" / "ocr" / "au_2001_cols"
PAGE_W, PAGE_H = 595, 842
MIN_CONF = 30


def ocr_col_page(pno, force=False):
    """OCR por COLUNA com --psm 6 (o psm 4 da página inteira salta linhas
    isoladas: headers e até nomes). Sidecars próprios por metade."""
    import csv
    outs = [OCR_COLS_DIR / f"page_{pno + 1:04d}_{s}.tsv" for s in ("L", "R")]
    if all(o.exists() for o in outs) and not force:
        return outs
    OCR_COLS_DIR.mkdir(parents=True, exist_ok=True)
    import fitz
    import PIL.Image
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT
    doc = fitz.open(OCR_SOURCES["au_2001"])
    page = doc[pno]
    for out, x0 in zip(outs, (0, PAGE_W / 2)):
        clip = fitz.Rect(x0, 0, x0 + PAGE_W / 2, PAGE_H)
        pix = page.get_pixmap(dpi=300, colorspace=fitz.csGRAY, clip=clip)
        img = PIL.Image.frombytes("L", (pix.width, pix.height), pix.samples)
        data = pytesseract.image_to_data(
            img, lang="por", config="--psm 6",
            output_type=pytesseract.Output.DICT)
        scale = 72.0 / 300
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["x0", "y0", "x1", "y1", "conf", "line", "text"])
            for i, txt in enumerate(data["text"]):
                txt = nfc(txt.strip())
                if not txt:
                    continue
                x = data["left"][i] * scale + x0
                y = data["top"][i] * scale
                ww, hh = data["width"][i] * scale, data["height"][i] * scale
                lid = f"{data['block_num'][i]}.{data['par_num'][i]}.{data['line_num'][i]}"
                w.writerow([f"{x:.1f}", f"{y:.1f}", f"{x + ww:.1f}",
                            f"{y + hh:.1f}", data["conf"][i], lid, txt])
    return outs


def ocr_col_words(pno):
    """Palavras [(x0,y0,x1,y1,texto,conf,line_id)] das 2 metades da página;
    os line_id da metade direita levam prefixo para não colidir."""
    import csv
    words = []
    for out, pref in zip(ocr_col_page(pno), ("L", "R")):
        with open(out, encoding="utf-8") as f:
            rd = csv.reader(f, delimiter="\t")
            next(rd, None)
            for row in rd:
                if len(row) < 7:
                    continue
                conf = float(row[4])
                if 0 <= conf < MIN_CONF:
                    continue
                x0, y0, x1, y1 = (float(v) for v in row[:4])
                words.append((x0, y0, x1, y1, row[6], conf, pref + row[5]))
    return words


def column_line_items(pno):
    """Linhas [[(x, texto), ...], ...] da página, na ordem de leitura.

    A página divide-se em bandas horizontais nos separadores "DISTRITO:"
    (as transições de distrito atravessam a página a meio); dentro de cada
    banda lê-se a coluna esquerda toda e depois a direita."""
    from ocr_eleitos import ocr_lines
    words = ocr_col_words(pno)
    # y das linhas "DISTRITO:" (palavra 'DISTRITO' seguida de ':')
    cuts = sorted({w[1] - 2.0 for w in words if w[4].upper().startswith("DISTRITO")})
    bands = [-1e9] + cuts + [1e9]
    out = []
    for bi in range(len(bands) - 1):
        y0, y1 = bands[bi], bands[bi + 1]
        band = [w for w in words if y0 <= (w[1] + w[3]) / 2 < y1]
        for side in (0, 1):
            col = [w for w in band
                   if (side == 0) == ((w[0] + w[2]) / 2 < SPLIT_X)]
            for _, items in ocr_lines(col):
                cells = [(x, t) for x, t, _ in items]
                if cells:
                    out.append(cells)
    return out


def split_name_sigla(cells):
    """(nome, sigla) de uma linha de eleito; sigla None se não houver.

    A sigla fica à direita do MAIOR gap da linha; pode ocupar várias
    células ("CDS-PP - PPD/PSD"), normalizadas para a forma compacta."""
    if len(cells) < 2:
        return " ".join(t for _, t in cells), None
    gaps = [(cells[i + 1][0] - cells[i][0], i) for i in range(len(cells) - 1)]
    g, i = max(gaps)
    if g >= SIGLA_GAP:
        sig = " ".join(t for _, t in cells[i + 1:])
        sig = re.sub(r"\s*-\s*", "-", sig)
        sig = re.sub(r"\s*\.\s*", ".", sig)
        sig = re.sub(r"\s*/\s*", "/", sig).strip()
        if RE_SIGLA.match(sig):
            nome = " ".join(t for _, t in cells[:i + 1])
            return nome, sig
    return " ".join(t for _, t in cells), None


def parse_2001():
    res = {s: load_results(f"au_{s}", YEAR) for s in ("cm", "am", "af")}

    # nome do concelho -> dico (nomes de 2021, com desambiguação das ilhas)
    with open(PROJECT_ROOT / "dados/eleitos/au_cm_2021.json", encoding="utf-8") as f:
        eleitos_2021 = json.load(f)
    concelho_map = {}
    for code, o in eleitos_2021["orgaos"].items():
        cn = clean_matching_name(o["nome"])
        concelho_map[cn] = code
        up = o["nome"].upper().replace(".", "")
        if "CALHETA" in cn:
            concelho_map["CALHETA MADEIRA" if ("RAM" in up or "MADEIRA" in up)
                         else "CALHETA ACORES"] = code
        elif "LAGOA" in cn:
            concelho_map["LAGOA ACORES" if ("RAA" in up or "ACORES" in up)
                         else "LAGOA FARO"] = code

    af_names = res["af"].get("NAMES", {}) or {}

    warn = []
    orgaos = {"cm": {}, "am": {}}
    orgaos_af = {}
    cur_dico = None
    cur_conc_nome = None
    cur = None            # dict do órgão corrente (ou None)
    pending = None        # linha de nome sem sigla (wrap)

    def open_orgao(kind, key, nome):
        nonlocal cur, pending
        pending = None
        store = orgaos_af if kind == "af" else orgaos[kind]
        if key is None:
            cur = None
            return
        if key not in store:
            store[key] = {"nome": nome, "listas": []}
        cur = store[key]

    def add_eleito(nome, sigla):
        for l in cur["listas"]:
            if l["sigla"] == sigla:
                l["eleitos"].append(nome)
                return
        cur["listas"].append({"sigla": sigla, "eleitos": [nome]})

    RE_RESULTS = re.compile(
        r"\b(INSCRITOS|VOTANTES|BRANCOS|NULOS|N[ÚU]MERO DE MANDATOS)\b")
    # header de concelho degradado pelo OCR (fonte forte partida em duas
    # linhas): "NCELHO: SÃ ÃO DA PE EIRA" / "CONC 0:5ÃO0 JOÃO sQU" —
    # só no INÍCIO da linha (as legendas de GCE também contêm "Concelho")
    RE_CONCELHO_FUZZY = re.compile(r"^\W{0,3}([CG][O0]?NC[EL]*[HI]?[O0]?\s*[:;]|NCELHO)")

    def _slug(s):
        import unicodedata
        s = "".join(c for c in unicodedata.normalize("NFKD", s)
                    if not unicodedata.combining(c))
        return re.sub(r"[^A-Z]", "", s.upper())

    def resolve_concelho(nome_raw, extra_raw, pno):
        """Dico a partir do texto (possivelmente degradado) do header."""
        nome = nome_raw.split(":", 1)[-1].strip()
        cn = clean_matching_name(nome)
        # desambiguação Lagoa/Calheta pela zona do PDF (distrito corrente)
        if cn in ("LAGOA", "CALHETA"):
            reg = "ACORES" if (cur_dico or "").startswith("4") else \
                ("MADEIRA" if (cur_dico or "").startswith("3") and cn == "CALHETA"
                 else ("FARO" if cn == "LAGOA" else "MADEIRA"))
            hit = concelho_map.get(f"{cn} {reg}")
            if hit:
                return hit, nome
        hit = concelho_map.get(cn)
        if hit:
            return hit, nome
        hits = {v for k, v in concelho_map.items() if cn and (cn in k or k in cn)}
        if len(hits) == 1:
            return hits.pop(), nome
        # nome truncado ("VILA NOVA DE"): contido único no distrito corrente
        if cur_dico and len(hits) > 1:
            hits_dd = {v for v in hits if v[:2] == cur_dico[:2]}
            if len(hits_dd) == 1:
                return hits_dd.pop(), nome
        # headers destruídos pelo OCR, mapeados à mão (verificados no render)
        for frag, real in CONCELHO_FIXES.items():
            if frag in nome_raw or (extra_raw and frag in extra_raw):
                hit = concelho_map.get(clean_matching_name(real))
                if hit:
                    return hit, real
        # fuzzy: assinatura de letras das linhas degradadas; o distrito
        # corrente só desempata
        import difflib
        sig = _slug(nome_raw + " " + (extra_raw or ""))
        sig = re.sub(r"^(C?ONCELHO|NCELHO)", "", sig)
        best = []
        for k, v in concelho_map.items():
            r = difflib.SequenceMatcher(None, _slug(k), sig).ratio()
            tie = 1 if (cur_dico and v[:2] == cur_dico[:2]) else 0
            best.append((r, tie, v, k))
        best.sort(reverse=True)
        if best and best[0][0] >= 0.62 and (len(best) < 2 or
                                            best[0][0] - best[1][0] > 0.08 or
                                            best[0][2] == best[1][2]):
            return best[0][2], best[0][3].title()
        warn.append(f"concelho não mapeado: {nome_raw!r}+{extra_raw!r} (p{pno + 1})")
        return None, nome

    # lista plana de linhas (para lookahead nos headers degradados)
    flat = []
    for pno in PAGES:
        inj = LINE_INJECTIONS.get(pno + 1, [])
        for cells in column_line_items(pno):
            flat.append((pno, cells))
            line_txt = " ".join(t for _, t in cells)
            for anchor, header in inj:
                if anchor in line_txt:
                    flat.append((pno, [(0.0, header)]))

    skip_next = False
    for idx, (pno, cells) in enumerate(flat):
        if skip_next:
            skip_next = False
            continue
        txt = nfc(" ".join(t for _, t in cells)).strip(" —–-·")
        if not txt or RE_HEADER_PAG.search(txt):
            continue
        up = txt.upper()
        if RE_RESULTS.search(up):
            # zona de resultados (o PDF alterna resultados/eleitos por
            # distrito): fecha o órgão em curso
            cur = None
            pending = None
            continue
        if RE_LEGENDA.search(txt):
            pending = None
            continue
        m = RE_CONCELHO.match(up)
        m_fuzzy = None
        if not m and RE_CONCELHO_FUZZY.search(up) and "FREGUESIA" not in up \
                and len(up) < 55 and not re.search(r"[«»\"“”]", txt):
            m_fuzzy = True
        if (m or m_fuzzy) and "FREGUESIA" not in up:
            pending = None
            extra = None
            nxt = None
            if idx + 1 < len(flat):
                nxt = nfc(" ".join(t for _, t in flat[idx + 1][1])).strip()
            if m_fuzzy and nxt:
                # header partido em duas linhas: junta a seguinte se também
                # for lixo de header (não é AM/CM nem linha de eleito)
                nup = nxt.upper()
                if "MUNICIPAL" not in nup and not RE_AF.match(nxt) and \
                        (RE_CONCELHO_FUZZY.search(nup) or ":" in nxt or
                         re.search(r"\d", nxt)):
                    extra = nxt
                    skip_next = True
            elif m and nxt and re.search(r"\b(DE|DA|DO|DOS|DAS|E)$", up):
                # nome truncado ("CONCELHO: VILA NOVA DE" + "FAMALICÃO")
                if nxt.isupper() and len(nxt) < 30 and ":" not in nxt \
                        and "MUNICIPAL" not in nxt.upper():
                    txt = f"{txt} {nxt}"
                    skip_next = True
            cur_dico, cur_conc_nome = resolve_concelho(txt, extra, pno)
            cur = None
            continue
        if RE_DISTRITO.match(up):
            continue
        if "ASSEMBLEIA MUNICIPAL" in up and len(up) <= 26:
            open_orgao("am", cur_dico, cur_conc_nome)
            continue
        if ("CÂMARA MUNICIPAL" in up or "CAMARA MUNICIPAL" in up) and len(up) <= 22:
            open_orgao("cm", cur_dico, cur_conc_nome)
            continue
        m = RE_AF.match(txt)
        if m and "ASSEMBLEIA" in m.group("nome").upper():
            m = None    # cabeçalho de tabela de resultados (3 colunas, caps)
        if m:
            nome_f = m.group("nome").strip()
            key = None
            if cur_dico:
                key = _match_freg_by_name(af_names, cur_dico, nome_f)
                if key is None:
                    warn.append(f"freguesia não mapeada: {cur_conc_nome}/"
                                f"{nome_f!r} (p{pno + 1})")
            open_orgao("af", key, nome_f)
            continue
        if RE_PLENARIO.search(txt):
            cur = None
            pending = None
            continue
        if RE_LEGENDA.search(txt):
            pending = None
            continue
        if cur is None:
            continue
        nome, sigla = split_name_sigla(cells)
        nome = nfc(nome).strip(" .—–-·")
        if re.search(r"\d", nome):
            continue
        if sigla:
            if pending:
                nome = f"{pending} {nome}".strip()
                pending = None
            if nome:
                add_eleito(nome, sigla)
        else:
            # possível wrap de nome longo: junta-se à linha seguinte
            if len(nome) < 4:
                continue
            pending = f"{pending} {nome}".strip() if pending else nome

    return res, orgaos, orgaos_af, warn


def _edit1(a, b):
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = diff = 0
    while i < la and j < lb:
        if a[i] != b[j]:
            diff += 1
            if diff > 1:
                return False
            j += 1
        else:
            i += 1
            j += 1
    return True


def _norm_sig(s):
    return re.sub(r"[.\-\s/]", "", s.upper())


def fuzzy_siglas(listas, local):
    """Siglas com gralha de OCR ('CP-PEV', 'PPD', 'XVI' por 'XVII'):
    mapeia para a chave local não reclamada a distância <= 1."""
    claimed = {l["sigla"] for l in listas}
    for l in listas:
        if l["sigla"] in local:
            continue
        s = _norm_sig(l["sigla"])
        cands = [k for k in local if k not in claimed
                 and (_edit1(s, _norm_sig(k))
                      or (len(s) >= 2 and (_norm_sig(k).startswith(s)
                                           or s in _norm_sig(k))))]
        if len(cands) == 1:
            l.setdefault("sigla_dr", l["sigla"])
            l["sigla"] = cands[0]
            claimed.add(cands[0])
    return listas


def build_output(res, orgaos, orgaos_af, warn):
    with open(PROJECT_ROOT / "dados/eleitos/au_cm_2021.json", encoding="utf-8") as f:
        conc_names = {c: o["nome"]
                      for c, o in json.load(f)["orgaos"].items()}
    problems = []
    for sub in ("cm", "am"):
        out = {}
        for dico, o in orgaos[sub].items():
            agg = res[sub].get("AGG", {}).get("concelho", {}).get(dico, {})
            local = set(agg.get("votes") or {}) | set(agg.get("mandatos_p") or {})
            listas = apply_sigla_aliases(YEAR, o["listas"])
            listas = canonicalize_siglas(listas, local)
            listas = fuzzy_siglas(listas, local)
            listas = resolve_leftover_siglas(listas, agg.get("mandatos_p"))
            listas = apply_overrides(YEAR, sub, dico, listas)
            entry = {"nome": conc_names.get(dico, o["nome"]), "listas": listas}
            if sub == "cm":
                p = compute_presidente(listas, agg.get("votes"))
                if p:
                    entry["presidente"] = p
            out[dico] = entry
            mp = {k: v for k, v in (agg.get("mandatos_p") or {}).items() if v}
            got = {l["sigla"]: len(l["eleitos"]) for l in listas}
            if mp and got != mp:
                problems.append(f"{sub} {dico} {o['nome']}: {got} != {mp}")
        write_eleitos_json(f"au_{sub}_{YEAR}.json", {
            "year": YEAR, "election": "au", "subtype": sub, "orgaos": out})
        print(f"au_{sub}_{YEAR}: {len(out)} concelhos")

    out_af = defaultdict(dict)
    for code, o in orgaos_af.items():
        votes = res["af"].get("RESULTS", {}).get(code)
        listas = apply_sigla_aliases(YEAR, o["listas"])
        listas = canonicalize_siglas(listas, set(votes or {}))
        claimed = {l["sigla"] for l in listas}
        leftover_votes = [k for k in (votes or {}) if k not in claimed]
        leftover_listas = [l for l in listas if l["sigla"] not in (votes or {})]
        if len(leftover_votes) == 1 and len(leftover_listas) == 1:
            leftover_listas[0].setdefault("sigla_dr", leftover_listas[0]["sigla"])
            leftover_listas[0]["sigla"] = leftover_votes[0]
        listas = apply_overrides(YEAR, "af", code, listas)
        entry = {"nome": o["nome"], "listas": listas}
        p = compute_presidente(listas, votes)
        if p:
            entry["presidente"] = p
        dd = circulo_from_dicofre(code) or code[:2]
        out_af[dd][code] = entry
    total = 0
    for dd, orgs in sorted(out_af.items()):
        write_eleitos_json(f"au_af_{YEAR}_{dd}.json", {
            "year": YEAR, "election": "au", "subtype": "af",
            "distrito": dd, "orgaos": orgs})
        total += len(orgs)
    print(f"au_af_{YEAR}: {total} freguesias em {len(out_af)} distritos")

    for w in warn[:25]:
        print(f"  aviso: {w}")
    if len(warn) > 25:
        print(f"  ... +{len(warn) - 25} avisos")
    for p in problems[:25]:
        print(f"  !! {p}")
    print(f"{len(problems)} reconciliações falhadas (cm+am)")


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    if len(sys.argv) > 2 and sys.argv[1] == "ocr":
        # modo OCR (paralelizável): python build_eleitos_au_2001.py ocr 1-120
        a, _, b = sys.argv[2].partition("-")
        for pno in range(int(a) - 1, int(b or a)):
            ocr_col_page(pno)
            print(f"ocr p{pno + 1}")
        return
    res, orgaos, orgaos_af, warn = parse_2001()
    build_output(res, orgaos, orgaos_af, warn)
    rebuild_index()


if __name__ == "__main__":
    main()
