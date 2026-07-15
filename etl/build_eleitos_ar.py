# -*- coding: utf-8 -*-
"""Eleitos da Assembleia da República a partir dos mapas oficiais do DR.

Anos com texto extraível: 1999-2025. Dois formatos:
  1999-2019: "N — Círculo de X (m) SIGLA — Nome do partido (n):" (na mesma
             linha) e nomes terminados em ".".
  2022-2025: círculo e partido em linhas separadas, sem ":" nem ".".
Anos digitalizados (1976-1995): mesmo formato de 1999-2019, texto obtido por
OCR (sidecars de ocr_eleitos.py) com tolerância a gralhas nas palavras-chave
e nas siglas; nomes de confiança baixa vão para etl/review/ar_{ano}_lowconf.csv.

A ordem dos partidos e dos nomes é a do DR (ordem da lista = ordem de eleição).
Validação: reconciliação com mandatos_p dos resultados quando existe (é a
autoridade; o "(n)" impresso pode ter gralha de OCR); senão, nº de nomes ==
(n) e soma == mandatos do círculo. QA final em qa_eleitos.py.
"""
import csv
import re
import sys

from eleitos_common import (DR_DIR, ELEITOS_DIR, SiglaResolver, circulo_code,
                            clean_name, load_results, nfc, pdf_lines,
                            rebuild_index, write_eleitos_json)

AR_DIR = DR_DIR / "assembleia da republica"
REVIEW_DIR = ELEITOS_DIR.parent.parent / "etl" / "review"

AR_SOURCES = {
    1999: "MapaOficialEleicoesOutubro1999.pdf",
    2002: "MapaOficialEleicoesMarco2002.pdf",
    2005: "MapaOficialEleicoesMarco2005.pdf",
    2009: "resultados_ar_2009.pdf",
    2011: "MapaOficialEleicoesJunho2011.pdf",
    2015: "MAPAOFICIALELEICOES4OUT2015.pdf",
    2019: "2019ar_mapa_oficial_resultados.pdf",
    2022: "2022ar_mapa_oficial_resultados.pdf",
    2024: "2024_ar_mapa_oficial_dr.pdf",
    2025: "2025_ar_mapa_oficial_dr.pdf",
}

# anos digitalizados -> tag dos sidecars OCR (ocr_eleitos.py)
AR_OCR_YEARS = {
    1975: "ar_1975", 1976: "ar_1976", 1979: "ar_1979", 1980: "ar_1980",
    1983: "ar_1983", 1985: "ar_1985", 1987: "ar_1987", 1991: "ar_1991",
    1995: "ar_1995",
}

LOWCONF_THRESHOLD = 75

# "1 — Círculo de Aveiro (15)" com possível cabeçalho de partido colado no fim
RE_CIRCULO = re.compile(r"^\d{1,2}\s*[—–]\s*Círculo\s+(?:[Ee]leitora\w*[!.]?\s+)?"
                        r"(?:(?:de|da|do|dos|das)\s+)?"
                        r"(?P<nome>.+?)\s*\((?P<n>\d+)\)\s*(?P<rest>[A-ZÀ-Ü].*)?$")
RE_PARTIDO = re.compile(r"^(?P<sigla>[A-ZÀ-Ü][\w./\- ]*?)\s*[—–]\s*(?P<nome>.+?)"
                        r"\s*\((?P<n>\d+)\)\s*[:.]?\s*$")
# variante sem nome por extenso, ex.: "CDS -PP (1):" (Braga, 2019)
RE_PARTIDO2 = re.compile(r"^(?P<sigla>[A-ZÀ-Ü][\w./\- ]*?)\s*\((?P<n>\d+)\)\s*:?\s*$")
# OCR: cabeçalho de partido sem sigla legível — só o nome por extenso
RE_PARTIDO_NOME = re.compile(r"^[—–\-\s]*(?P<nome>[A-Za-zÀ-ü][\w À-ü.\-]*?)"
                             r"\s*\(?(?P<n>\d+)\)?\s*[:.]?\s*$")
# fragmento órfão de cabeçalho partido em duas linhas: "tária (6):"
RE_HEAD_ORPHAN = re.compile(r"^[a-zà-ü][\w-]*\s*\((?P<n>\d+)\)\s*:\s*$")

# nome por extenso -> sigla impressa (resolvida depois pelo SiglaResolver);
# usado quando o OCR perde a sigla e no mapa de 1975 (partidos por extenso)
PARTY_NAME_TO_SIGLA = {
    "PARTIDOSOCIALISTA": "PS",
    "PARTIDOSOCIALDEMOCRATA": "PPD/PSD",
    "PARTIDOPOPULARDEMOCRATICO": "PPD",
    "PARTIDOPOPULARMONARQUICO": "PPM",
    "PARTIDOPOPULAR": "CDS-PP",
    "CENTRODEMOCRATICOSOCIAL": "CDS",
    "PARTIDODOCENTRODEMOCRATICOSOCIAL": "CDS",
    "COLIGACAODEMOCRATICAUNITARIA": "PCP-PEV",
    "PARTIDOCOMUNISTAPORTUGUES": "PCP",
    "PARTIDORENOVADORDEMOCRATICO": "PRD",
    "ALIANCAPOVOUNIDO": "APU",
    "UNIAODEMOCRATICAPOPULAR": "UDP",
    "MOVIMENTODEMOCRATICOPORTUGUES": "MDP",
    "MOVIMENTODEMOCRATICOPORTUGUESCDE": "MDP",
    "ALIANCADEMOCRATICA": "AD",
    "FRENTEREPUBLICANAESOCIALISTA": "FRS",
    "PARTIDODESOLIDARIEDADENACIONAL": "PSN",
    "BLOCODEESQUERDA": "B.E.",
    "ASSOCIACAODEFESAINTERESSESMACAU": "ADIM",
}


def _party_name_to_siglas(nome):
    """Siglas candidatas para um nome de partido por extenso, da chave
    mais longa para a mais curta ("Socialista" -> [FRS, PS])."""
    from eleitos_common import slug
    s = slug(nome)
    hits = []
    for k, v in PARTY_NAME_TO_SIGLA.items():
        if k in s or _edit1(k, s) or (len(s) >= 10 and s in k):
            hits.append((k, v))
    hits.sort(key=lambda kv: -len(kv[0]))
    return [v for _, v in hits]


def _party_name_to_sigla(nome):
    cands = _party_name_to_siglas(nome)
    return cands[0] if cands else None
# linhas que marcam o início do mapa de resultados (fim da relação de eleitos)
RE_TABLE_START = re.compile(r"^(Número|Percentagem|Círculo|Total|Resultados|Inscritos|"
                            r"Eleitores|Votantes|Abstenção|Votos(\s+\S+)?|Círculos Eleitorais)$",
                            re.IGNORECASE)


def norm_sigla_dr(s):
    s = nfc(s.strip())
    s = re.sub(r"\s*-\s*", "-", s)   # "PCP -PEV" -> "PCP-PEV"
    s = re.sub(r"\s*\.\s*", ".", s)  # "PPD/PSD. CDS-PP" -> "PPD/PSD.CDS-PP"
    s = re.sub(r"\s{2,}", " ", s)
    return s


def looks_like_name(line):
    s = line.rstrip(".").strip()
    if len(s.split()) < 2:
        return False
    if re.search(r"[\d%()\[\]—–:;=|]", s):
        return False
    if not re.match(r"[A-ZÀ-Ü]", s):
        return False
    return True


def join_wraps(lines):
    """Junta translineações (linha terminada em '-' continua na seguinte).
    Entrada/saída: [(texto, conf), ...]."""
    out = []
    for ln, conf in lines:
        ln = ln.replace("\xa0", " ")
        if out and out[-1][0].endswith("-") and not out[-1][0].endswith(" -"):
            prev, pconf = out[-1]
            out[-1] = (prev[:-1] + ln, min(pconf, conf))
        else:
            out.append((ln, conf))
    return out


def _edit1(a, b):
    """Distância de edição <= 1 (para gralhas de OCR em palavras-chave)."""
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


def _fix_ocr_keywords(ln):
    """Normaliza gralhas de OCR nas palavras estruturais e nos travessões."""
    words = ln.split(" ")
    fixed = []
    for w in words:
        up = re.sub(r"[^A-Za-zÀ-ü]", "", w).upper()
        if len(up) >= 5 and _edit1(up.replace("Í", "I"), "CIRCULO"):
            fixed.append("Círculo")
        else:
            fixed.append(w)
    ln = " ".join(fixed)
    ln = re.sub(r"\s-{1,2}\s", " — ", ln)          # hífen lido em vez de travessão
    ln = re.sub(r"(?:\s*[*~•¬+«»|;?!=]+)+\s*$", "", ln)  # ruído do scan no fim da linha
    ln = re.sub(r"^[*~•¬+«»|;'\"´`‘’.,]+\s*", "", ln)  # ruído no início da linha
    ln = re.sub(r"(?<=\.)\s+[A-Za-z]{1,2}$", "", ln)   # cauda de 1-2 letras após "."
    ln = re.sub(r"(?<=\.)\s*:+\s*$", "", ln)           # ":" solto após o ponto final
    # mancha da margem colada ao início do nome ("UniAntónio Roleira ...")
    ln = re.sub(r"^[A-Za-z]{1,4}(?=[A-ZÀ-Ü][a-zà-ü])", "", ln)
    return ln.strip()


def ocr_source_lines(tag, split_x=282):
    """Linhas [(texto, conf), ...] dos sidecars OCR, colunas pela ordem de leitura."""
    from ocr_eleitos import column_lines, ocr_words, page_count
    from eleitos_common import is_header_footer
    # cabeçalhos de página do DR partidos entre colunas ("REPÚBLICA — I
    # N.º 246 — 24-10-1995", "6608-(4) DIÁRIO DA", "— I SÉRIE-A ...")
    re_dr_header = re.compile(
        r"(REP[ÚU]BLICA\b|S[ÉE]RIE|DI[ÁA]RIO|\d{1,2}-\d{1,2}-\d{2,4}|"
        r"^\d{3,4}-?\(\d+\)|N\.[ºo°]\s*\d)", re.IGNORECASE)
    # colofão do DR (preços/assinaturas) impresso no rodapé das páginas
    re_colofao = re.compile(
        r"(PREÇO\s+DESTE|assinatur|venda\s+avuls|SUPLEMENTO|Codex|"
        r"Imprensa\s+Nacional|Casa\s+da\s+Moeda|publicaç)", re.IGNORECASE)

    def is_prose(txt):
        # texto corrido do colofão: maioria estrita de palavras em minúscula
        # (cabeçalhos de círculo ficam de fora: "Círculo eleitoral de ...")
        if "Círculo" in txt:
            return False
        words = [w for w in txt.split() if w[0].isalpha()]
        if len(words) < 6:
            return False
        return sum(w[0].islower() for w in words) > len(words) / 2

    lines = []
    for pno in range(page_count(tag)):
        for txt, conf in column_lines(ocr_words(tag, pno), split_x):
            txt = _fix_ocr_keywords(txt)
            if txt and not is_header_footer(txt) and \
                    not re_dr_header.search(txt) and \
                    not re_colofao.search(txt) and not is_prose(txt):
                lines.append((txt, conf))
    # cabeçalho de partido partido em duas linhas em que o OCR perdeu o hífen
    # ("... Coligação Democrática Uni" + "tária (6):") e nomes quebrados cuja
    # continuação começa por minúscula ("... Vale de Matos" + "da Silva.")
    merged = []
    for txt, conf in lines:
        if merged and RE_HEAD_ORPHAN.match(txt):
            prev, pconf = merged[-1]
            merged[-1] = (prev.rstrip("-") + txt, min(pconf, conf))
        elif merged and re.match(r"^[a-zà-ü]", txt) and not merged[-1][0].endswith((".", ":")):
            prev, pconf = merged[-1]
            merged[-1] = (prev + " " + txt, min(pconf, conf))
        elif merged and not merged[-1][0].endswith((".", ":")) and \
                re.fullmatch(r"(?:[A-ZÀ-Ü][a-zà-ü'\-]+\s?){1,2}\.", txt) and \
                looks_like_name(merged[-1][0] + " x"):
            # apelido órfão do wrap ("... Martins Catarino" + "Costa.")
            prev, pconf = merged[-1]
            merged[-1] = (prev + " " + txt, min(pconf, conf))
        else:
            merged.append((txt, conf))
    # ruído em minúsculas colado ao início ("das Manuel Fernandes ...");
    # nomes e cabeçalhos nunca começam por minúscula
    merged = [(re.sub(r"^(?:[a-zà-ü][\w.\-]*\s+)+(?=[A-ZÀ-Ü])", "", t), c)
              for t, c in merged]
    from eleitos_overrides import apply_line_fixes
    return apply_line_fixes(tag, merged)


def parse_ar(year):
    is_ocr = year in AR_OCR_YEARS
    results = load_results("ar", year)
    parties = results["METADATA"]["parties"].keys()
    resolver = SiglaResolver(parties, year=year, election="ar")

    def resolve_sigla(sig):
        from eleitos_common import slug
        key = resolver.resolve(sig, cur_code)
        if key or not is_ocr:
            return key
        # OCR: tolerância a 1 gralha na sigla, comparada sem pontuação
        # ("PPD/P8D" -> "PPD/PSD", "PCP/PEVY" -> "PCP-PEV"); siglas curtas
        # ficam de fora ("CDU" -> "CDS" seria um falso positivo)
        if len(slug(sig)) < 4:
            return None
        cands = [k for k in parties if _edit1(slug(sig), slug(k))]
        return cands[0] if len(cands) == 1 else None

    if year == 1975:
        # scan demasiado degradado para OCR: transcrição manual verificada
        # (eleitos_manual_1975.py), alimentada à mesma máquina de estados
        from eleitos_manual_1975 import ELEITOS_1975
        lines = []
        for circ, partidos in ELEITOS_1975:
            lines.append((circ, 100.0))
            for partido, nomes in partidos:
                lines.append((partido + ":", 100.0))
                lines.extend((n + ".", 100.0) for n in nomes)
    elif is_ocr:
        lines = join_wraps(ocr_source_lines(AR_OCR_YEARS[year]))
    else:
        lines = join_wraps([(l, 100.0) for l in pdf_lines(AR_DIR / AR_SOURCES[year])])
    # até 2019 os nomes terminam em "."; linhas sem ponto final são fragmentos
    # de um nome quebrado em duas linhas (sem hífen) a juntar à seguinte.
    # Em OCR o "." final perde-se com frequência: as continuações já foram
    # juntadas em ocr_source_lines, cada linha é um nome completo.
    dotted = year <= 2019 and not is_ocr
    circulos = {}   # code -> {"nome":..., "mandatos":n, "listas":[...]}
    order = []
    cur_code, cur_circ, cur_lista = None, None, None
    pending, pending_conf = "", 100.0
    problems = []
    lowconf = []    # (circulo, sigla, posicao, nome, conf)

    def add_name(nome, conf):
        cur_lista["eleitos"].append(nome)
        if is_ocr and conf < LOWCONF_THRESHOLD:
            lowconf.append((cur_circ["nome"], cur_lista["sigla"],
                            len(cur_lista["eleitos"]), nome, conf))

    def flush_pending():
        # nome sem ponto final no DR (gralha) seguido de cabeçalho
        nonlocal pending, pending_conf
        if pending and cur_lista is not None and looks_like_name(pending):
            add_name(clean_name(pending), pending_conf)
        pending, pending_conf = "", 100.0

    def open_partido(text):
        nonlocal cur_lista
        sig = None
        m = RE_PARTIDO.match(text)
        nome_dr = None
        if m:
            nome_dr = clean_name(m.group("nome"))
        else:
            m = RE_PARTIDO2.match(text)
            if m and not resolve_sigla(norm_sigla_dr(m.group("sigla"))) and \
                    cur_code not in ("XM", "XC", "XE"):
                m = None
            if not m and is_ocr:
                # ruído antes do cabeçalho ("publinoRe- CDS/PP — Partido ...")
                m2 = re.search(r"(?P<sigla>[A-ZÀ-Ü][\w./\-]{1,14})\s*[—–]\s*"
                               r"(?P<nome>.+?)\s*\((?P<n>\d+)\)\s*:?\s*$", text)
                if m2 and resolve_sigla(norm_sigla_dr(m2.group("sigla"))):
                    m = m2
                    nome_dr = clean_name(m2.group("nome"))
                else:
                    # sigla ilegível: identificar pelo nome por extenso
                    m3 = RE_PARTIDO_NOME.match(text)
                    if m3:
                        sig = next((s for s in
                                    _party_name_to_siglas(m3.group("nome"))
                                    if resolve_sigla(s)), None)
                        if sig:
                            m = m3
                            nome_dr = clean_name(m3.group("nome"))
                if not m:
                    # parêntese perdido: "PPD/PSD — Partido X 2):" / "... (1:"
                    m5 = re.match(r"^(?P<sigla>[A-ZÀ-Ü][\w./\-]{1,14})\s*[—–]\s*"
                                  r"(?P<nome>.+?)\s*\(?(?P<n>\d+)\)?\s*:?\s*$", text)
                    if m5 and resolve_sigla(norm_sigla_dr(m5.group("sigla"))):
                        m = m5
                        nome_dr = clean_name(m5.group("nome"))
                if not m:
                    # "(n)" ilegível: "SIGLA — Nome do partido" sem contagem;
                    # só é cabeçalho se sigla e nome apontarem para o mesmo partido
                    m4 = re.match(r"^(?P<sigla>[A-ZÀ-Ü][\w./\-]{1,14})\s*[—–]\s*"
                                  r"(?P<nome>[A-Za-zÀ-ü][\w À-ü.\-]+?)\s*:?\s*$", text)
                    if m4:
                        s4 = norm_sigla_dr(m4.group("sigla"))
                        by_name = _party_name_to_sigla(m4.group("nome"))
                        if by_name and resolve_sigla(s4) and \
                                resolve_sigla(s4) == resolve_sigla(by_name):
                            m = m4
                            nome_dr = clean_name(m4.group("nome"))
            if not m:
                return False
        flush_pending()
        if sig is None:
            sig = norm_sigla_dr(m.group("sigla"))
        key = resolve_sigla(sig)
        if not key and cur_code in ("XM", "XC", "XE"):
            # ultramar de 1975: partidos sem equivalente nos resultados do
            # site (ex.: ADIM em Macau) mantêm a sigla impressa
            key = sig
        if not key and is_ocr and nome_dr:
            # sigla irreconhecível ou ambígua ("CDU"): resolver pelo nome
            # por extenso do partido/coligação
            for by_name in _party_name_to_siglas(nome_dr):
                key = resolver.resolve(by_name, cur_code) or \
                    (by_name if by_name in parties else None)
                if key:
                    break
        if not key:
            problems.append(f"{cur_circ['nome']}: sigla não resolvida {sig!r} ({text[:80]!r})")
            cur_lista = None
            return True
        n_str = m.groupdict().get("n")
        cur_lista = {"sigla": key, "eleitos": [],
                     "_n": int(n_str) if n_str else None}
        if sig != key:
            cur_lista["sigla_dr"] = sig
        if nome_dr:
            cur_lista["nome_dr"] = nome_dr
        cur_circ["listas"].append(cur_lista)
        return True

    for ln, conf in lines:
        m = RE_CIRCULO.match(ln)
        if not m and is_ocr and "Círculo" in ln:
            # ruído antes do número ("Uni18 — Círculo de Viseu (9)") ou depois
            # do "(n)" ("Círculo da Guarda (4) o")
            m = re.search(r"\d{0,2}\s*[—–]?\s*Círculo\s+(?:[Ee]leitora\w*[!.]?\s+)?"
                          r"(?:(?:de|da|do|dos|das)\s+)?"
                          r"(?P<nome>.+?)\s*\((?P<n>\d+)\)(?P<rest>.*)$", ln)
            if m and not circulo_code(clean_name(m.group("nome"))):
                m = None
        def _circ_code(nome):
            code = circulo_code(nome)
            if not code and year == 1975:
                # círculos do ultramar/emigração da Constituinte, sem
                # equivalente nos resultados do site (códigos próprios)
                from eleitos_common import slug
                code = {"MACAU": "XM", "MOCAMBIQUE": "XC",
                        "EMIGRACAO": "XE"}.get(slug(nome))
            return code

        if not m and is_ocr:
            # perfil 1975/1976: cabeçalho de círculo sem a palavra "Círculo"
            # ("Aveiro (15)"); só aceita nomes de círculo conhecidos
            m2c = re.match(r"^(?P<nome>[A-ZÀ-Ü][^()—–:]*?)\s*\((?P<n>\d+)\)\s*$", ln)
            if m2c and _circ_code(clean_name(m2c.group("nome"))):
                m = m2c
        if m:
            flush_pending()
            nome = clean_name(m.group("nome"))
            code = _circ_code(nome)
            if not code:
                problems.append(f"círculo desconhecido: {nome!r}")
                cur_code, cur_circ, cur_lista = None, None, None
                continue
            # se o mesmo círculo reaparecer (ex.: mapa retificado no fim do
            # PDF), a última ocorrência substitui a anterior; se um círculo
            # DIFERENTE mapear para o mesmo código (Angra/Horta/Ponta
            # Delgada agregados no site como Açores em 1976), fundem-se
            cur_code = code
            if code in circulos and circulos[code]["nome"] != nome:
                cur_circ = circulos[code]
                cur_circ["mandatos"] += int(m.group("n"))
                cur_lista = None
                continue
            cur_circ = {"nome": nome, "mandatos": int(m.group("n")), "listas": []}
            cur_lista = None
            circulos[code] = cur_circ
            if code not in order:
                order.append(code)
            rest = (m.groupdict().get("rest") or "").strip()
            if rest and rest[0].isupper():
                open_partido(rest)
            continue
        if cur_circ is None:
            continue
        if ln.startswith("Comissão Nacional de Eleições,"):
            flush_pending()
            cur_code, cur_circ, cur_lista = None, None, None
            continue
        if RE_TABLE_START.match(ln) or \
                (is_ocr and re.search(r"\b(Vot(os|antes)|Volantes|Percentagem|"
                                      r"Abstenç\w*|[Ii]nscritos)\b", ln)) or \
                (is_ocr and _edit1(re.sub(r"[^A-Za-z]", "", ln).upper(),
                                   "ELEITORESINSCRITOS")):
            # em OCR o título da tabela final pode vir com gralha
            # ("Fleitores inscritos")
            flush_pending()
            cur_code, cur_circ, cur_lista = None, None, None
            continue
        if is_ocr and len(re.findall(r"\d{2,}", ln)) >= 2:
            # linha numérica (colofão de preços/fragmento de tabela no fim
            # da página): ignora-se sem fechar o círculo em curso
            continue
        if open_partido(ln):
            continue
        if cur_lista is not None and looks_like_name(pending + ln):
            if dotted and not ln.rstrip().endswith("."):
                pending += ln + " "
                pending_conf = min(pending_conf, conf)
                continue
            add_name(clean_name(pending + ln), min(pending_conf, conf))
            pending, pending_conf = "", 100.0

    # fundir listas duplicadas da mesma sigla (cabeçalho OCR partido em duas
    # linhas pode abrir a mesma lista duas vezes)
    for c in circulos.values():
        by, dedup = {}, []
        for l in c["listas"]:
            if l["sigla"] in by:
                by[l["sigla"]]["eleitos"].extend(l["eleitos"])
            else:
                by[l["sigla"]] = l
                dedup.append(l)
        c["listas"] = dedup

    # validação: mandatos_p dos resultados é a autoridade quando existe
    # (o "(n)" impresso pode ter gralha de OCR); senão, o "(n)" local
    dist_mp = results.get("AGG", {}).get("distrito", {})
    for code in order:
        c = circulos[code]
        mp = {k: v for k, v in (dist_mp.get(code, {}).get("mandatos_p") or {}).items() if v}
        got = {}
        for l in c["listas"]:
            got[l["sigla"]] = got.get(l["sigla"], 0) + len(l["eleitos"])
        if mp:
            if got == mp:
                c["mandatos"] = sum(got.values())
                for l in c["listas"]:
                    l.pop("_n", None)
                continue
            problems.append(f"{c['nome']}: eleitos {got} != mandatos_p {mp}")
            continue
        soma, sem_n = 0, False
        for l in c["listas"]:
            n = l.pop("_n")
            if n is None:      # "(n)" ilegível no OCR: sem verificação local
                sem_n = True
                soma += len(l["eleitos"])
                continue
            soma += n
            if n != len(l["eleitos"]):
                problems.append(f"{c['nome']}/{l['sigla']}: {len(l['eleitos'])} nomes != ({n})")
        if soma != c["mandatos"] and not sem_n:
            problems.append(f"{c['nome']}: soma partidos {soma} != mandatos {c['mandatos']}")
    for c in circulos.values():
        for l in c["listas"]:
            l.pop("_n", None)
    if lowconf:
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with open(REVIEW_DIR / f"ar_{year}_lowconf.csv", "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["circulo", "sigla", "posicao", "nome_ocr", "conf"])
            w.writerows(lowconf)
        print(f"  ar {year}: {len(lowconf)} nomes de baixa confiança em "
              f"review/ar_{year}_lowconf.csv")
    import os
    dbg = os.environ.get("ELEITOS_DEBUG")
    if dbg:
        for code, c in circulos.items():
            if dbg.lower() in c["nome"].lower():
                for l in c["listas"]:
                    print(f"  DEBUG {c['nome']}/{l['sigla']}:")
                    for nm in l["eleitos"]:
                        print(f"     - {nm}")
    if problems:
        for p in problems:
            print(f"  !! ar {year}: {p}")
        raise SystemExit(f"ar {year}: {len(problems)} problemas")

    payload = {"year": year, "election": "ar", "circulos": circulos}
    write_eleitos_json(f"ar_{year}.json", payload)
    total = sum(c["mandatos"] for c in circulos.values())
    return total, len(circulos)


def main():
    years = [int(a) for a in sys.argv[1:]] or sorted({**AR_SOURCES,
                                                      **AR_OCR_YEARS})
    for y in years:
        total, ncirc = parse_ar(y)
        print(f"ar_{y}: {total} deputados em {ncirc} círculos")
    rebuild_index()


if __name__ == "__main__":
    main()
