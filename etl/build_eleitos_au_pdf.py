# -*- coding: utf-8 -*-
"""Eleitos das Autárquicas 2009-2021 a partir dos mapas oficiais do DR (PDF).

O mapa III (eleitos) é uma tabela em página rodada (90º):
    CÓD | CONC | FREG | ÓRG          (cabeçalho, repetido por página)
    código | concelho | freguesia | CM/AM/AF        (linha de registo)
    sigla @ âncoras x                 (uma coluna por lista; em 2013 pode vir
                                       na mesma linha y do registo)
    nomes por coluna, um por linha, na ordem da lista
Registos continuam entre páginas sem repetir a linha de siglas (as âncoras x
mantêm-se). Extração por get_text("words") com a matriz de rotação aplicada.

O primeiro nome da lista mais votada (resultados do site) é o presidente da
câmara (CM) / junta (AF).

Uso: python build_eleitos_au_pdf.py [ano ...]   (por omissão: 2009 2013 2017 2021)
"""
import re
import sys
from collections import defaultdict

import fitz
import unicodedata

from common import norm_dicofre, circulo_from_dicofre, strip_accents_upper
from eleitos_common import (DR_DIR, canonicalize_siglas, compute_presidente,
                            load_results, nfc, norm_name_if_caps,
                            rebuild_index, resolve_leftover_siglas,
                            write_eleitos_json)
from eleitos_overrides import apply_overrides, apply_sigla_aliases

AU_DIR = DR_DIR / "autarquicas"

AU_PDF_SOURCES = {
    2009: "resultados_al_2009.pdf",
    2013: "al_2013_mapa_resultados.pdf",
    2017: "al2017_mapa_resultados.pdf",
    2021: "al2021_mapa_resultados.pdf",
}

# mapas complementares: a Declaração de Retificação n.º 13-B/2010 publica o
# mapa III de Oeiras e Sintra (CM/AM), omitidos do mapa oficial de 2009
AU_PDF_EXTRA = {
    2009: ["declaracao_rectificacao_13_b_2010.pdf"],
}

# O mapa de 2009 usa os códigos de distrito ANTIGOS nas regiões autónomas
# (19 Angra, 20 Horta, 21 Ponta Delgada, 22 Funchal); os resultados do site
# usam os dicofres modernos (31/32 Madeira, 41-49 Açores). Mapeamento por
# (distrito antigo, nome do concelho sem acentos).
ISLAND_DICO_2009 = {
    # chaves em strip_accents_upper (sem acentos NEM espaços)
    "22": {  # Funchal (Madeira)
        "CALHETA": "3101", "CAMARADELOBOS": "3102", "FUNCHAL": "3103",
        "MACHICO": "3104", "PONTADOSOL": "3105", "PORTOMONIZ": "3106",
        "RIBEIRABRAVA": "3107", "SANTACRUZ": "3108", "SANTANA": "3109",
        "SAOVICENTE": "3110", "PORTOSANTO": "3201",
    },
    "21": {  # Ponta Delgada (S. Miguel + Santa Maria)
        "VILADOPORTO": "4101", "LAGOA": "4201", "NORDESTE": "4202",
        "PONTADELGADA": "4203", "POVOACAO": "4204", "RIBEIRAGRANDE": "4205",
        "VILAFRANCADOCAMPO": "4206",
    },
    "19": {  # Angra do Heroísmo (Terceira + Graciosa + S. Jorge)
        "ANGRADOHEROISMO": "4301", "VILADAPRAIADAVITORIA": "4302",
        "PRAIADAVITORIA": "4302", "SANTACRUZDAGRACIOSA": "4401",
        "CALHETA": "4501", "VELAS": "4502",
    },
    "20": {  # Horta (Pico + Faial + Flores + Corvo)
        "LAJESDOPICO": "4601", "MADALENA": "4602", "SAOROQUEDOPICO": "4603",
        "HORTA": "4701", "LAJESDASFLORES": "4801",
        "SANTACRUZDASFLORES": "4802", "CORVO": "4901",
    },
}


def _norm_freg_name(s):
    """Nome de freguesia normalizado para matching (sem acentos, pontuação,
    espaços nem sufixos regionais)."""
    s = strip_accents(nfc(s or "")).upper()
    s = re.sub(r"\(\s*R\.?\s*A\.?[^)]*\)", " ", s)   # "(R.A.Açores)"
    s = re.sub(r"\(\d+\)", " ", s)                    # notas "(1)"
    s = re.sub(r"[().,\-']", " ", s)
    s = re.sub(r"\bN\s+SRA\b", " NOSSA SENHORA ", s)
    s = re.sub(r"\bSTA\b", " SANTA ", s)
    s = re.sub(r"\bSTO\b", " SANTO ", s)
    s = re.sub(r"\bS\b", " SAO ", s)
    return re.sub(r"\s+", "", s)


def _match_freg_by_name(af_names, dico, freg, conc=None):
    """Dicofre moderno de uma freguesia pelo nome, dentro do concelho dado."""
    raw = nfc(freg or "").strip()
    if not raw:
        return None
    # prefixo com as iniciais do concelho ("H ANGÚSTIAS" = Horta (...),
    # "VFC S MIGUEL" = Vila Franca do Campo (São Miguel))
    m_pref = conc and re.match(r"^([A-Za-z]{1,4})\s+(.+)$", raw)
    if m_pref:
        pref = strip_accents(m_pref.group(1)).upper()
        cwords = [w for w in strip_accents(nfc(conc)).upper().split()
                  if w not in ("DE", "DA", "DO", "DOS", "DAS", "E")]
        initials = "".join(w[0] for w in cwords)
        if pref == initials or (len(pref) == 1 and initials.startswith(pref)):
            raw = f"{conc} {m_pref.group(2)}"
    tgt = _norm_freg_name(raw)
    if not tgt:
        return None
    cands = [(k, _norm_freg_name(v)) for k, v in af_names.items()
             if k[:4] == dico]
    exact = [k for k, n in cands if n == tgt]
    if len(exact) == 1:
        return exact[0]
    cont = [k for k, n in cands if tgt in n or n in tgt]
    if len(set(cont)) == 1:
        return cont[0]
    return None


def _remap_island_2009(cod, org, conc, freg, af_names, warn):
    """Converte um código do mapa de 2009 (distritos antigos das ilhas)
    para o dicofre moderno usado nos resultados do site."""
    dmap = ISLAND_DICO_2009.get(cod[:2])
    if not dmap:
        return cod
    nome = strip_accents_upper(conc or "").strip()
    nd = dmap.get(nome)
    if nd is None:
        hits = {v for k, v in dmap.items() if nome and (k in nome or nome in k)}
        nd = hits.pop() if len(hits) == 1 else None
    if nd is None:
        warn.append(f"ilhas 2009: concelho não mapeado {cod!r} {conc!r}")
        return cod
    if org != "AF":
        return nd + "00"
    nf = _match_freg_by_name(af_names, nd, freg, conc)
    if nf is None:
        warn.append(f"ilhas 2009: freguesia não mapeada {cod!r} {conc!r}/{freg!r}")
        return cod
    return nf

X_MARGIN = 745      # à direita disto é o cabeçalho vertical do DR
Y_TOL = 2.6         # tolerância de agrupamento em linhas
RE_COD = re.compile(r"^\d{5,6}$")


def page_lines(page):
    """Linhas de palavras [(x, texto), ...] com rotação aplicada e margem cortada."""
    m = page.rotation_matrix
    words = []
    for w in page.get_text("words"):
        r = fitz.Rect(w[:4]) * m
        if r.x0 >= X_MARGIN or r.y0 < 34:
            continue
        words.append((r.y0, r.x0, nfc(w[4])))
    words.sort()
    lines, cur_y, cur = [], None, []
    for y, x, t in words:
        if cur_y is None or y - cur_y > Y_TOL:
            if cur:
                lines.append(sorted(cur))
            cur, cur_y = [], y
        cur.append((x, t))
        cur_y = y
    if cur:
        lines.append(sorted(cur))
    return lines


def group_cells(items, anchors, tol=12):
    """Agrupa palavras (x, texto) nas colunas definidas pelas âncoras."""
    cells = [[] for _ in anchors]
    bounds = list(anchors) + [X_MARGIN]
    for x, t in items:
        for i in range(len(anchors)):
            if bounds[i] - tol <= x < bounds[i + 1] - tol:
                cells[i].append(t)
                break
    return [" ".join(c) if c else None for c in cells]


def group_cells_x(items, anchors, tol=12):
    """Como group_cells, mas devolve também o x da 1.ª palavra da célula
    (para detetar linhas de continuação indentadas)."""
    cells = [[] for _ in anchors]
    first_x = [None] * len(anchors)
    bounds = list(anchors) + [X_MARGIN]
    for x, t in items:
        for i in range(len(anchors)):
            if bounds[i] - tol <= x < bounds[i + 1] - tol:
                if first_x[i] is None:
                    first_x[i] = x
                cells[i].append(t)
                break
    return [(" ".join(c) if c else None, first_x[i])
            for i, c in enumerate(cells)]


class Record:
    def __init__(self, code, conc, freg, org):
        self.code, self.conc, self.freg, self.org = code, conc, freg, org
        self.anchors = []
        self.listas = []      # paralelo a anchors (listas de todos os segmentos)
        self.seg = []         # índices em listas por coluna do segmento atual
        self.awaiting_sigla = True   # a 1.ª linha após o código é sempre de siglas

    def open_segment(self, cells_x):
        self.anchors = [x for x, _ in cells_x]
        self.seg = []
        self.awaiting_sigla = False
        for _, sig in cells_x:
            existing_idx = None
            for idx, l in enumerate(self.listas):
                if l["sigla"] == sig:
                    existing_idx = idx
                    break
            if existing_idx is not None:
                self.seg.append(existing_idx)
            else:
                self.listas.append({"sigla": sig, "eleitos": []})
                self.seg.append(len(self.listas) - 1)

    def add_names(self, items):
        if not self.anchors:
            return
        cells = group_cells_x(items, self.anchors)
        for i, (c, fx) in enumerate(cells):
            if c and i < len(self.seg) and _is_caps_cell(c):
                name = norm_name_if_caps(c)
                eleitos = self.listas[self.seg[i]]["eleitos"]
                # célula indentada face à âncora = continuação (wrap) do
                # nome anterior ("... SANHUDO" + "NOVAIS BARREIRA")
                if eleitos and fx is not None and fx - self.anchors[i] > 8:
                    eleitos[-1] = f"{eleitos[-1]} {name}"
                elif name not in eleitos:
                    eleitos.append(name)

    def merged_listas(self):
        merged, by = [], {}
        for l in self.listas:
            # reparar nomes partidos em duas linhas (fragmento com < 2 palavras
            # junta-se ao nome anterior, ex.: "... VAZ DE" + "ALBUQUERQUE")
            fixed = []
            for nome in l["eleitos"]:
                if fixed and (len(nome.split()) < 2 or nome.split()[0].upper() in ("DE", "DA", "DO", "DOS", "DAS", "E")):
                    fixed[-1] = f"{fixed[-1]} {nome}"
                else:
                    fixed.append(nome)
            l["eleitos"] = fixed
            if not l["eleitos"]:
                continue
            if l["sigla"] in by:
                by[l["sigla"]]["eleitos"].extend(l["eleitos"])
            else:
                by[l["sigla"]] = l
                merged.append(l)
        return merged


def _is_caps_cell(cell):
    """Nos mapas 2009-2021 os nomes vêm SEMPRE em maiúsculas; células em caixa
    mista são continuações do nome da freguesia ou notas — nunca eleitos."""
    letters = [ch for ch in cell if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                    if not unicodedata.combining(c))


def norm_sigla_for_matching(s):
    return re.sub(r"[.\-\s/]", "", strip_accents_upper(s))


def scan_dynamic_siglas(doc):
    dynamic = defaultdict(set)
    for page in doc:
        t = page.get_text()
        if "Sigla" not in t and "Denominação" not in t and "Denominacao" not in t and "[" not in t:
            continue
        lines = page_lines(page)
        for line in lines:
            line_str = " ".join(tok for _, tok in line).strip()
            if not re.match(r"^\d{6}\b", line_str):
                continue
            org_m = re.search(r"\b(CM|AM|AF)\b", line_str)
            if not org_m:
                continue
            org = org_m.group(1)
            code = line_str[:6]
            
            brackets = re.findall(r"\[([^\]\s]+)", line_str)
            if brackets:
                for b in brackets:
                    b = b.strip("«».,;:\"'“”")
                    if b and any(char.isalpha() for char in b) and re.fullmatch(r"[a-zA-Z0-9./+&!«»\-]+", strip_accents(b)):
                        dynamic[(code, org)].add(b.upper())
                        dynamic[(code, org)].add(strip_accents(b).upper())
            else:
                m = re.match(r"^(\d{6})\s+(.*?)\s+(CM|AM|AF)\s+(\S+)", line_str)
                if m:
                    _, _, _, sig = m.groups()
                    sig = sig.strip("«».,;:\"'“”")
                    if sig and any(char.isalpha() for char in sig) and re.fullmatch(r"[a-zA-Z0-9./+&!«»\-]+", strip_accents(sig)):
                        dynamic[(code, org)].add(sig.upper())
                        dynamic[(code, org)].add(strip_accents(sig).upper())
    return dynamic


def is_valid_sigla_token(t, sigla_slugs, record=None, year=None, dynamic_siglas=None):
    t_upper = t.strip().upper()
    t_clean = strip_accents(t_upper)
    
    # 1. Check if it's a known global or dynamic sigla first (lenient on characters)
    sig = t_upper
    if year:
        from eleitos_overrides import SIGLA_ALIASES
        alias = SIGLA_ALIASES.get((int(year), t_upper)) or SIGLA_ALIASES.get((int(year), t_upper.lower()))
        if alias:
            sig = alias
        
    sig_norm = norm_sigla_for_matching(sig)
    if sig_norm in sigla_slugs:
        return True
        
    if record and dynamic_siglas:
        rec_key = (record.code, record.org)
        rec_sigs = dynamic_siglas.get(rec_key, set())
        # Clean both for matching
        rec_sigs_clean = {strip_accents(s.strip("«».,;:\"'“”")).upper() for s in rec_sigs}
        t_clean_sig = strip_accents(t_upper.strip("«».,;:\"'“”")).upper()
        if t_clean_sig in rec_sigs_clean or norm_sigla_for_matching(t_upper) in {norm_sigla_for_matching(s) for s in rec_sigs}:
            return True
            
    # 2. Standard validation rules
    t_clean_no_spaces = t_clean.replace(" ", "")
    # Allow a wider range of characters including !, «, » in general siglas
    if not re.fullmatch(r"[A-Z0-9./+&!«»\-]+", t_clean_no_spaces):
        return False
    if len(t_clean) > 40:
        return False
    if t_clean in ("CM", "AM", "AF", "CÓD", "CONC", "FREG", "DE", "DO", "DA", "E", "O", "A", "AND", "UNIÃO", "UNIAO", "FREGUESIAS"):
        return False
    if record:
        words = []
        if record.conc:
            words.extend(re.findall(r"\w+", strip_accents_upper(record.conc)))
        if record.freg:
            words.extend(re.findall(r"\w+", strip_accents_upper(record.freg)))
        if strip_accents_upper(t_clean) in words:
            return False
            
    # Se não for uma sigla global conhecida ou dinâmica, só permite se tiver tamanho >= 2 e <= 4
    if 2 <= len(t_clean) <= 4:
        return True
    return False


def looks_like_sigla_row(items, sigla_slugs, record=None, year=None,
                         dynamic_siglas=None, awaiting=False):
    """Linha de siglas: aceite se todas as células parecerem siglas.

    Evita que fragmentos de nomes partidos ou continuações de nomes de
    freguesia abram listas fantasma.

    Com `awaiting=True` (1.ª linha após o registo, que no formato do mapa é
    SEMPRE a linha de siglas) basta UMA célula válida: as restantes podem
    ser cabeçalhos de GCE com denominações por extenso ("MANUEL CERVEIRA
    DIAS", "f100%"), resolvidos depois por canonicalize/resolve_leftover.
    """
    if not items:
        return False
    cells = sigla_cells(items)
    if not cells:
        return False
    valid = [is_valid_sigla_token(t, sigla_slugs, record, year, dynamic_siglas)
             for _, t in cells]
    if awaiting:
        return any(valid)
    return all(valid)


def sigla_cells(items):
    cells, last_x = [], None
    for x, t in items:
        if last_x is None or x - last_x > 60:
            cells.append((x, [t]))
        else:
            cells[-1][1].append(t)
        last_x = x
    return [(x, " ".join(ts)) for x, ts in cells]


def parse_year(year):
    global X_MARGIN
    X_MARGIN = 745
    path = AU_DIR / AU_PDF_SOURCES[year]
    res = {s: load_results(f"au_{s}", year) for s in ("cm", "am", "af")}
    docs = [fitz.open(path)] + [fitz.open(AU_DIR / p)
                                for p in AU_PDF_EXTRA.get(year, [])]
    dynamic_siglas = scan_dynamic_siglas(docs[0])
    for extra in docs[1:]:
        for k, v in scan_dynamic_siglas(extra).items():
            dynamic_siglas[k] |= v

    # slugs de todas as siglas conhecidas nos resultados (para validar linhas
    # de siglas de segmentos extra)
    global_slugs = set()
    for s in ("cm", "am", "af"):
        for k in res[s].get("METADATA", {}).get("parties", {}):
            global_slugs.add(norm_sigla_for_matching(k))
        for agg in res[s].get("AGG", {}).get("concelho", {}).values():
            for k in (agg.get("votes") or {}):
                global_slugs.add(norm_sigla_for_matching(k))
    for votes in res["af"].get("RESULTS", {}).values():
        for k in votes:
            global_slugs.add(norm_sigla_for_matching(k))

    records = {}       # (code, org) -> Record  (fundidos se repetidos)
    order = []
    remap_warn = []
    af_names = res["af"].get("NAMES", {}) or {}
    cur = None
    for page in (p for d in docs for p in d):
        lines = page_lines(page)
        if not lines:
            continue

        for line in lines:
            texts = [t for _, t in line]
            # cercas por linha (os mapas I/II/III alternam a MEIO das páginas):
            # linhas de tabelas de resultados (mapa I: percentagens/contagens)
            # e da legenda de siglas (mapa II) fecham o registo em curso
            ndig = sum(t.replace(",", "").replace(".", "").isdigit() for t in texts)
            if "%" in texts or ndig >= 4:
                cur = None
                continue
            up_line = strip_accents(" ".join(texts)).upper()
            if ("SIGLA" in up_line and "DENOMINAC" in up_line) or "ANEXO" in up_line:
                cur = None
                continue
            if texts[:1] == ["CÓD"] or ("CÓD" in texts and "ÓRG" in texts) or ("Cód." in texts and "Órg." in texts):
                continue
            org_w = [t for _, t in line if t in ("CM", "AM", "AF")]
            cod_w = [(x, t) for x, t in line if RE_COD.match(t)]
            # linha de registo do mapa III: nada à direita do ÓRG além de
            # notas curtas ("(1)", "(P)"); as linhas dos mapas I/II têm
            # números ou denominações depois do ÓRG e marcam fronteira de
            # zona — fecham o registo em curso
            if org_w and cod_w:
                _org_x = max(x for x, t in line if t == org_w[-1])
                right = [t for x, t in line if x > _org_x + 6]
                if any(not re.fullmatch(r"\([A-Za-z0-9]{1,3}\)", t) for t in right):
                    cur = None
                    continue
            if org_w and cod_w:
                cod_x, cod = cod_w[0]
                org = org_w[-1]
                # células CONC/FREG: palavras entre o código e o ÓRG
                org_x = max(x for x, t in line if t == org)
                mid = [(x, t) for x, t in line if cod_x < x < org_x and t != cod]
                # separar conc/freg pelo maior gap horizontal
                conc, freg = _split_conc_freg(mid)
                if year == 2009 and conc and cod.startswith("100") and len(cod) == 6:
                    conc_clean = strip_accents(conc).upper()
                    if conc_clean == "MARINHA GRANDE" and cod.startswith("1000"):
                        cod = "1010" + cod[4:]
                    elif conc_clean == "NAZARE" and cod.startswith("1001"):
                        cod = "1011" + cod[4:]
                    elif conc_clean == "OBIDOS" and cod.startswith("1002"):
                        cod = "1012" + cod[4:]
                    elif conc_clean == "PEDROGAO GRANDE" and cod.startswith("1003"):
                        cod = "1013" + cod[4:]
                    elif conc_clean == "PENICHE" and cod.startswith("1004"):
                        cod = "1014" + cod[4:]
                    elif conc_clean == "POMBAL" and cod.startswith("1005"):
                        cod = "1015" + cod[4:]
                    elif conc_clean == "PORTO DE MOS" and cod.startswith("1006"):
                        cod = "1016" + cod[4:]
                if year == 2009 and cod[:2] in ISLAND_DICO_2009:
                    cod = _remap_island_2009(cod, org, conc, freg,
                                             af_names, remap_warn)
                key = (cod, org)
                if key in records:
                    cur = records[key]
                else:
                    cur = Record(cod, conc, freg, org)
                    records[key] = cur
                    order.append(key)
                # 2013: siglas na mesma linha, à esquerda da coluna CÓD
                left = [(x, t) for x, t in line if x < cod_x - 8]
                if left and looks_like_sigla_row(left, global_slugs, cur, year, dynamic_siglas):
                    cur.open_segment(sigla_cells(left))
                continue
            if cur is None:
                continue
            if cur.awaiting_sigla:
                if looks_like_sigla_row(line, global_slugs, cur, year,
                                        dynamic_siglas, awaiting=True):
                    cells = sigla_cells(line)
                    cur.open_segment(cells)
                    # célula de GCE cujo cabeçalho é o nome do 1.º candidato
                    # ("MANUEL CERVEIRA DIAS"): o nome conta como 1.º eleito
                    seed = [(x, t) for x, t in cells
                            if not is_valid_sigla_token(t, global_slugs, cur,
                                                        year, dynamic_siglas)
                            and _is_caps_cell(t) and len(t.split()) >= 3
                            and not any(ch.isdigit() for ch in t)]
                    if seed:
                        cur.add_names(seed)
                continue
            if looks_like_sigla_row(line, global_slugs, cur, year, dynamic_siglas):
                cur.open_segment(sigla_cells(line))
                continue
            cur.add_names(line)

    for w in remap_warn[:20]:
        print(f"  aviso: {w}")
    return build_output(year, res, records, order)


def _split_conc_freg(mid):
    if not mid:
        return None, None
    gaps = [(mid[i + 1][0] - mid[i][0], i) for i in range(len(mid) - 1)]
    if not gaps or max(g for g, _ in gaps) < 55:
        return " ".join(t for _, t in mid), None
    _, cut = max(gaps)
    conc = " ".join(t for _, t in mid[:cut + 1])
    freg = " ".join(t for _, t in mid[cut + 1:])
    return conc, freg


def _at_anchorish(line, rec):
    """Novo segmento de siglas dentro do registo: 1.ª palavra perto da 1.ª âncora."""
    return abs(line[0][0] - rec.anchors[0]) < 15 if rec.anchors else True


def build_output(year, res, records, order):
    out = {"cm": {}, "am": {}}
    out_af = defaultdict(dict)
    warn = []
    for key in order:
        r = records[key]
        code = norm_dicofre(r.code)
        if not code:
            warn.append(f"código inválido {r.code!r} ({r.conc}/{r.org})")
            continue
        listas = apply_sigla_aliases(year, r.merged_listas())
        if not listas:
            warn.append(f"{r.code} {r.conc} {r.org}: sem nomes")
            continue
        if r.org in ("CM", "AM"):
            dico = code[:4]
            agg = res[r.org.lower()].get("AGG", {}).get("concelho", {}).get(dico, {})
            local = set(agg.get("votes") or {}) | set(agg.get("mandatos_p") or {})
            listas = canonicalize_siglas(listas, local)
            listas = resolve_leftover_siglas(listas, agg.get("mandatos_p"))
            listas = apply_overrides(year, r.org.lower(), dico, listas)
            entry = {"nome": r.conc, "listas": listas}
            if r.org == "CM":
                p = compute_presidente(listas, agg.get("votes"))
                if p:
                    entry["presidente"] = p
                else:
                    warn.append(f"CM {dico} {r.conc}: presidente não determinado")
            out[r.org.lower()][dico] = entry
        else:
            votes = res["af"].get("RESULTS", {}).get(code)
            listas = canonicalize_siglas(listas, set(votes or {}))
            # AF: uma única chave de votos sobrante identifica a lista
            claimed = {l["sigla"] for l in listas}
            leftover_votes = [k for k in (votes or {}) if k not in claimed]
            leftover_listas = [l for l in listas if l["sigla"] not in (votes or {})]
            if len(leftover_votes) == 1 and len(leftover_listas) == 1:
                leftover_listas[0].setdefault("sigla_dr", leftover_listas[0]["sigla"])
                leftover_listas[0]["sigla"] = leftover_votes[0]
            listas = apply_overrides(year, "af", code, listas)
            entry = {"nome": r.freg or r.conc, "listas": listas}
            p = compute_presidente(listas, votes)
            if p:
                entry["presidente"] = p
            dd = circulo_from_dicofre(code) or code[:2]
            out_af[dd][code] = entry

    for sub in ("cm", "am"):
        write_eleitos_json(f"au_{sub}_{year}.json", {
            "year": year, "election": "au", "subtype": sub, "orgaos": out[sub]})
        print(f"au_{sub}_{year}: {len(out[sub])} concelhos")
    total_f = 0
    for dd, orgaos in sorted(out_af.items()):
        write_eleitos_json(f"au_af_{year}_{dd}.json", {
            "year": year, "election": "au", "subtype": "af", "distrito": dd,
            "orgaos": orgaos})
        total_f += len(orgaos)
    print(f"au_af_{year}: {total_f} freguesias em {len(out_af)} distritos")
    for w in warn[:30]:
        print(f"  aviso: {w}")
    if len(warn) > 30:
        print(f"  ... +{len(warn) - 30} avisos")
    return warn


def main():
    years = [int(a) for a in sys.argv[1:]] or sorted(AU_PDF_SOURCES)
    for y in years:
        parse_year(y)
    rebuild_index()


if __name__ == "__main__":
    main()
