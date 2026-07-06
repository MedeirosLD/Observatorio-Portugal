# -*- coding: utf-8 -*-
"""Resultados das eleições EUROPEIAS (Parlamento Europeu) -> JSON.

Círculo único nacional, proporcional (d'Hondt). Comporta-se como a AR (partidos +
mandatos), pelo que o frontend reutiliza o sistema de cores de partidos.

Três formatos de origem em resultados/europeias/:
  - Excel "Globais" moderno (2004, 2009, 2014, 2019, 2024): folhas distrito/
    concelho/freguesia (+ país). Coluna de mandatos total e por-partido.
  - TXT largura fixa (1987, 1989, 1994): Pe{yy}{f,c,d}.txt. Blocos de partido de
    19 chars (sigla9 + votos7 + mand3).
  - Binário/linhas 1999 ('  ELPE'): registos de 820 chars (tipo P/D/C/F), tabela
    de 20 partidos (sigla15 + voto7) em [120 + k*35]; contadores em offsets fixos.

Cada ano reutiliza a geometria do ano AR mais próximo (MAP_YEAR).

Uso:  python etl/build_results_ee.py --all   |   python etl/build_results_ee.py 2024 1994
Saída: dados/resultados/ee_{ano}.json + dados/ee_index.json
"""
import json
import re
import sys
from collections import defaultdict

import pandas as pd

from common import (RESULTADOS_DIR, OUT_DIR, norm_dicofre, circulo_from_dicofre,
                    is_freguesia_code)
from build_results import to_int, load_island_crosswalk, OLD_ISLAND_PREFIXES
from build_results_pr import reconcile_with_map, find_sheet, clean_country_name

EE_DIR = RESULTADOS_DIR.parent / "europeias"

# ano -> (formato, ficheiro base)
EE_FILES = {
    "1987": ("txt", "Pe87"), "1989": ("txt", "Pe89"), "1994": ("txt", "Pe94"),
    "1999": ("elpe", "  ELPE"),
    "2004": ("modern", "PE2004_RPais.xls"), "2009": ("modern", "PE2009_Globais.xls"),
    "2014": ("modern", "PE2014_Globais.xls"), "2019": ("modern", "PE2019_Globais.xlsx"),
    "2024": ("modern", "PE2024_Globais.xlsx"),
}

# ano EE -> ano AR do mapa mais próximo (geojson já existente)
MAP_YEAR = {"1987": 1987, "1989": 1987, "1994": 1995, "1999": 1999, "2004": 2005,
            "2009": 2009, "2014": 2015, "2019": 2019, "2024": 2024}

# nº de eurodeputados eleitos por Portugal (para d'Hondt onde a fonte não traz mandatos)
SEATS = {"1987": 24, "1989": 24, "1994": 25, "1999": 25, "2004": 24, "2009": 22,
         "2014": 21, "2019": 21, "2024": 21}

# Concelhos onde NÃO houve votação (não é falta de dados) — o painel/tooltip mostram
# "Votação não realizada" para o concelho e as suas freguesias. ee 2014: Murça (1707).
NO_ELECTION_CONCELHOS = {"2014": ["1707"]}


# ------------------------------------------------------------- helpers -------

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


def level_key(code):
    """Código de agregado -> chave de círculo/nível (tolerante a esquemas curtos)."""
    if code in ("000050", "500000", "230000", "000023"):
        return "national"
    if code in ("000099", "990000"):
        return "global"
    if code in ("000060", "600000"):
        return "estrangeiro"
    if code in ("000030", "300000", "310000", "320000") or code[:2] in ("22", "30", "31", "32"):
        return "30"
    if code in ("000040", "400000") or code[:2] in ("19", "20", "21") or \
       (code[:2].isdigit() and 40 <= int(code[:2]) <= 49):
        return "40"
    if code.endswith("0000") and code[:2].isdigit() and 1 <= int(code[:2]) <= 18:
        return code[:2]
    if code.startswith("0000") and code[4:].isdigit() and 1 <= int(code[4:]) <= 18:
        return f"{int(code[4:]):02d}"
    return None


def conc_key(code):
    """Código de concelho (6-díg antigo 'DDCC00' ou curto '00DDCC') -> 'DDCC'."""
    if code is None:
        return None
    if code.endswith("00") and not code.endswith("0000"):
        return code[:4]
    if code.startswith("00") and not code.endswith("00") and code[2:6].isdigit():
        return f"{int(code):04d}"
    return None


def sum_votes(list_of_votes):
    tot = defaultdict(int)
    for votes in list_of_votes:
        for p, v in votes.items():
            tot[p] += v
    return dict(tot)


# ------------------------------------------------- parser: Excel moderno -----

def parse_ee_sheet(df, level):
    """Folha moderna -> lista de rows {code,name,inscritos,votantes,brancos,nulos,
    votes,mandatos_p,mandatos_total}. `level`: distrito|concelho|freguesia|pais|global."""
    # cabeçalho: 1.ª linha com 'inscr...' e 'nulos' (tolera 'inscr'/'inscritos')
    h = None
    for i in range(min(12, len(df))):
        row = [str(x).strip().lower() for x in df.iloc[i].tolist()]
        if any(c.startswith("inscr") for c in row) and any(c.startswith("nulo") for c in row):
            h = i
            break
    if h is None:
        return []
    hdr = [str(x).strip() for x in df.iloc[h].tolist()]
    low = [x.lower() for x in hdr]

    codecols = [j for j, c in enumerate(low) if "digo" in c or c == "cod"]
    if not codecols:
        codecols = [0]
    code_col = codecols[-1] if level in ("concelho", "freguesia") else codecols[0]

    nameword = {"freguesia": "freguesia", "concelho": "concelho", "distrito": "distrito",
                "pais": "territ", "global": "territ"}.get(level, "nome")
    name_col = next((j for j, c in enumerate(low) if nameword in c or "denomina" in c), None)
    if name_col is None:
        name_col = next((j for j, c in enumerate(low) if "nome" in c or "territ" in c), None)
    if name_col is None:
        name_col = min(code_col + 1, len(hdr) - 1)

    def find(*preds):
        for j, c in enumerate(low):
            if any(pr(c) for pr in preds):
                return j
        return None
    i_insc = find(lambda c: c.startswith("inscr"))
    i_vot = find(lambda c: c.startswith("votant"))
    i_bra = find(lambda c: c == "brancos" or c.startswith("branco") or "em branco" in c)
    i_nul = find(lambda c: c.startswith("nulo"))
    if i_nul is None:
        return []

    groups = []            # (party, i_votes, i_mand|None)
    i_mand_total = None
    j = i_nul + 1
    while j < len(hdr):
        cl = low[j]
        # saltar %/votos válidos e as colunas do piloto de voto eletrónico de 2019
        # ("votantes voto eletrónico" / "votantes voto tradicional") — não são partidos
        if (cl in ("", "nan") or cl.startswith("%") or "validament" in cl
                or "votant" in cl or cl.startswith("voto ")):
            j += 1
            continue
        if cl.startswith("mand") or cl in ("tot_mand",):
            if i_mand_total is None and not groups:
                i_mand_total = j
            j += 1
            continue
        party = hdr[j]
        iv, im, k = j, None, j + 1
        if k < len(hdr) and low[k].startswith("%"):
            k += 1
        if k < len(hdr) and low[k].startswith("mand"):
            im = k
            k += 1
        groups.append((party, iv, im))
        j = k

    rows = []
    for r in df.iloc[h + 1:].itertuples(index=False):
        r = list(r)
        if code_col >= len(r):
            continue
        code = norm_dicofre(r[code_col])
        if code is None:
            continue
        votes, mand = {}, {}
        for party, iv, im in groups:
            v = to_int(r[iv]) if iv < len(r) else 0
            if v:
                votes[party] = votes.get(party, 0) + v
            if im is not None and im < len(r):
                m = to_int(r[im])
                if m:
                    mand[party] = mand.get(party, 0) + m
        rows.append({
            "code": code,
            "name": str(r[name_col]).strip() if name_col < len(r) and r[name_col] is not None else "",
            "inscritos": to_int(r[i_insc]) if i_insc is not None and i_insc < len(r) else 0,
            "votantes": to_int(r[i_vot]) if i_vot is not None and i_vot < len(r) else 0,
            "brancos": to_int(r[i_bra]) if i_bra is not None and i_bra < len(r) else 0,
            "nulos": to_int(r[i_nul]) if i_nul < len(r) else 0,
            "votes": votes, "mandatos_p": mand,
            "mandatos_total": to_int(r[i_mand_total]) if i_mand_total is not None and i_mand_total < len(r) else 0,
        })
    return rows


def load_modern(fname):
    """Devolve dict level -> rows para um workbook moderno."""
    xls = pd.ExcelFile(EE_DIR / fname)
    out = {}
    for level, needles in (("freguesia", ("freguesi",)), ("concelho", ("concelho",)),
                           ("distrito", ("distrito", "globais")), ("pais", ("pa",))):
        sn = None
        for nd in needles:
            sn = find_sheet(xls, nd)
            if sn:
                break
        if sn:
            out[level] = parse_ee_sheet(pd.read_excel(xls, sn, header=None, dtype=object), level)
    return out


# -------------------------------------------------- parser: TXT legado -------

def parse_txt(path):
    """Ficheiro TXT largura fixa -> lista de rows. Blocos de partido de 19 chars."""
    rows = []
    for raw in open(path, encoding="latin1"):
        line = raw.rstrip("\r\n")
        if len(line) < 40:
            continue
        code = norm_dicofre(line[0:6])
        if code is None:
            continue
        name = line[6:36].strip()
        rest = line[36:]
        m = re.search(r"[A-Za-z]", rest)
        if not m:
            continue
        pstart = m.start()
        counters = rest[:pstart].split()
        if len(counters) < 4:
            continue
        insc, vot, bra, nul = (to_int(counters[-4]), to_int(counters[-3]),
                               to_int(counters[-2]), to_int(counters[-1]))
        pr = rest[pstart:]
        votes, mand = {}, {}
        for k in range(0, len(pr), 19):
            blk = pr[k:k + 19]
            if len(blk) < 12:
                break
            sig = blk[0:9].strip()
            if not sig:
                continue
            v = to_int(blk[9:16])
            mm = to_int(blk[16:19])
            if v:
                votes[sig] = votes.get(sig, 0) + v
            if mm:
                mand[sig] = mand.get(sig, 0) + mm
        rows.append({"code": code, "name": name, "inscritos": insc, "votantes": vot,
                     "brancos": bra, "nulos": nul, "votes": votes, "mandatos_p": mand,
                     "mandatos_total": 0})
    return rows


def load_txt(base):
    out = {}
    for level, suf in (("freguesia", "f"), ("concelho", "c"), ("distrito", "d")):
        p = EE_DIR / f"{base}{suf}.txt"
        if p.exists():
            out[level] = parse_txt(p)
    return out


# -------------------------------------------------- parser: 1999 ELPE --------

def load_elpe(fname):
    """Ficheiro de 1999 (linhas de 820 chars, tipo P/D/C/F)."""
    lines = (EE_DIR / fname).read_bytes().decode("latin1").split("\r\n")
    out = {"freguesia": [], "concelho": [], "distrito": [], "national": []}
    tmap = {"F": "freguesia", "C": "concelho", "D": "distrito", "P": "national"}
    for L in lines:
        if len(L) < 200:
            continue
        code = norm_dicofre(L[0:6])
        lvl = tmap.get(L[8:9])
        if code is None or lvl is None:
            continue
        votes = {}
        for k in range(20):
            b = L[120 + k * 35:120 + (k + 1) * 35]
            sig = b[0:15].strip()
            if sig:
                v = to_int(b[15:22])
                if v:
                    votes[sig] = votes.get(sig, 0) + v
        out[lvl].append({
            "code": code, "name": L[19:59].strip(),
            "inscritos": to_int(L[75:82]), "votantes": to_int(L[82:89]),
            "brancos": to_int(L[94:101]), "nulos": to_int(L[106:113]),
            "votes": votes, "mandatos_p": {}, "mandatos_total": 0,
        })
    return out


# ------------------------------------------------------------------ build ----

def build_tag(tag):
    fmt, spec = EE_FILES[tag]
    map_year = MAP_YEAR[tag]
    print(f"=== EE {tag} ({fmt}, mapa {map_year}) ===")

    if fmt == "modern":
        data = load_modern(spec)
    elif fmt == "txt":
        data = load_txt(spec)
    else:
        data = load_elpe(spec)

    freg_rows = data.get("freguesia", [])
    island_cw = load_island_crosswalk(map_year) if map_year <= 2005 else {}

    results, names, official_f = {}, {}, {}
    for r in freg_rows:
        code = r["code"]
        if code[:2] in OLD_ISLAND_PREFIXES and code in island_cw:
            code = island_cw[code]
        if not is_freguesia_code(code):
            continue
        results[code] = r["votes"]
        names[code] = r["name"]
        official_f[code] = [r["inscritos"], r["votantes"], r["brancos"], r["nulos"]]

    moved = reconcile_with_map(results, names, official_f, map_year)
    if moved:
        print(f"  reconciliação com mapa {map_year}: {moved} freguesias remapeadas")

    # agregados a partir das freguesias
    agg_conc, agg_dist = defaultdict(list), defaultdict(list)
    for code, votes in results.items():
        agg_conc[code[:4]].append(votes)
        circ = circulo_from_dicofre(code)
        if circ:
            agg_dist[circ].append(votes)
    concelho = {k: {"votes": sum_votes(v)} for k, v in agg_conc.items()}
    distrito = {k: {"votes": sum_votes(v)} for k, v in agg_dist.items()}
    national_votes = sum_votes(results.values())

    # camada oficial (distrito/concelho/nacional/global) + estrangeiro
    national_off = global_row = None
    countries = {}
    dist_sheet = {}   # key -> row oficial do distrito (votos + insc/bra/nul)
    for r in data.get("distrito", []) + (data.get("national", [])):
        key = level_key(r["code"])
        if key == "national":
            national_off = r
        elif key == "global":
            global_row = r
        elif key in distrito:
            dist_sheet[key] = r
            distrito[key].update({"inscritos": r["inscritos"], "votantes": r["votantes"],
                                  "brancos": r["brancos"], "nulos": r["nulos"]})
    conc_sheet = {}   # ck -> row oficial do concelho
    for r in data.get("concelho", []):
        ck = conc_key(r["code"])
        if ck and ck in concelho:
            conc_sheet[ck] = r
            concelho[ck].update({"inscritos": r["inscritos"], "votantes": r["votantes"],
                                 "brancos": r["brancos"], "nulos": r["nulos"]})
            # Fallback (sem inventar): concelho sem breakdown por freguesia na fonte
            # mas com totais próprios -> usar os votos do nível de concelho.
            if not concelho[ck].get("votes") and r["votes"]:
                concelho[ck]["votes"] = r["votes"]

    # Recuperação (sem inventar): um concelho totalmente suprimido na fonte (freguesia
    # E concelho a NaN, ex.: Murça em 2014) é recuperável por subtração quando é o
    # ÚNICO em falta no seu distrito — o seu total = distrito oficial − Σ(outros
    # concelhos do distrito). Só a nível de concelho (as freguesias ficam sem dados).
    by_circ = defaultdict(list)
    for ck in concelho:
        c = circulo_from_dicofre(ck + "00")
        if c:
            by_circ[c].append(ck)
    for circ, cks in by_circ.items():
        empties = [ck for ck in cks if not concelho[ck].get("votes")]
        ds = dist_sheet.get(circ)
        if len(empties) != 1 or not ds or not ds.get("votes"):
            continue
        miss = empties[0]
        others_v = defaultdict(int)
        others = {"inscritos": 0, "votantes": 0, "brancos": 0, "nulos": 0}
        for ck in cks:
            if ck == miss:
                continue
            src = conc_sheet.get(ck)
            for p, v in (concelho[ck].get("votes") or {}).items():
                others_v[p] += v
            for k in others:
                others[k] += (src[k] if src else concelho[ck].get(k, 0))
        rec = {p: ds["votes"][p] - others_v.get(p, 0) for p in ds["votes"]
               if ds["votes"][p] - others_v.get(p, 0) > 0}
        if rec:
            concelho[miss]["votes"] = rec
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                concelho[miss][k] = max(0, ds[k] - others[k])
            print(f"  concelho {miss} recuperado por subtração do distrito {circ} "
                  f"(vencedor {max(rec, key=rec.get)})")

    # país/estrangeiro (modernos): E1/E2 + countries + estrangeiro total
    circ_tot = {"E1": None, "E2": None}
    estrangeiro = None
    for r in data.get("pais", []):
        code = r["code"]
        raw = code.lstrip("0") or "0"
        if raw in ("60", "600000"):
            estrangeiro = r
            continue
        if not (raw.startswith("8") or raw.startswith("9")):
            continue
        circ = "E1" if raw.startswith("81") else "E2"
        ct = circ_tot[circ] or {"votes": defaultdict(int), "inscritos": 0,
                                "votantes": 0, "brancos": 0, "nulos": 0}
        for k in ("inscritos", "votantes", "brancos", "nulos"):
            ct[k] += r[k]
        for p, v in r["votes"].items():
            ct["votes"][p] += v
        circ_tot[circ] = ct
        canon = clean_country_name(r["name"])
        if canon:
            dst = countries.setdefault(circ, {}).setdefault(canon, {
                "votes": defaultdict(int), "inscritos": 0, "votantes": 0, "brancos": 0, "nulos": 0})
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                dst[k] += r[k]
            for p, v in r["votes"].items():
                dst["votes"][p] += v
    for circ in ("E1", "E2"):
        if circ_tot[circ]:
            distrito[circ] = {"votes": dict(circ_tot[circ]["votes"]),
                              **{k: circ_tot[circ][k] for k in ("inscritos", "votantes", "brancos", "nulos")}}
    countries = {c: {n: {**d, "votes": dict(d["votes"]), "mandatos": 0} for n, d in cs.items()}
                 for c, cs in countries.items()}

    # nacional oficial (insc/bra/nul): linha nacional se existir, senão soma OFFICIAL_F
    if national_off:
        nat_off = {k: national_off[k] for k in ("inscritos", "votantes", "brancos", "nulos")}
    else:
        s = [0, 0, 0, 0]
        for v in official_f.values():
            for i in range(4):
                s[i] += v[i]
        nat_off = {"inscritos": s[0], "votantes": s[1], "brancos": s[2], "nulos": s[3]}

    # mandatos nacionais (eurodeputados): fonte oficial, senão d'Hondt
    seats = SEATS[tag]
    src = global_row or national_off
    if src and src.get("mandatos_p"):
        mand_p = src["mandatos_p"]
    else:
        base_votes = (global_row or {}).get("votes") or (national_off or {}).get("votes") or national_votes
        mand_p = dhondt(base_votes, seats)

    parties = sorted(national_votes, key=lambda p: national_votes[p], reverse=True)
    meta = {
        "year": tag, "election": "ee",
        "parties": {p: {"nome": p} for p in parties},
        "national": {"votes": national_votes, **nat_off,
                     "mandatos": sum(mand_p.values()) or seats, "mandatos_p": mand_p},
    }
    if global_row:
        meta["global"] = {"votes": global_row["votes"],
                          **{k: global_row[k] for k in ("inscritos", "votantes", "brancos", "nulos")},
                          "mandatos": sum(mand_p.values()) or seats, "mandatos_p": mand_p}
    if estrangeiro:
        meta["estrangeiro"] = {"votes": estrangeiro["votes"],
                               **{k: estrangeiro[k] for k in ("inscritos", "votantes", "brancos", "nulos")}}

    # territórios sem votação realizada (concelhos marcados + as suas freguesias)
    no_elec_concs = NO_ELECTION_CONCELHOS.get(tag, [])
    if no_elec_concs:
        no_elec = list(no_elec_concs)
        no_elec += [c for c in results if c[:4] in no_elec_concs]
        meta["no_election"] = sorted(set(no_elec))

    payload = {"METADATA": meta, "NAMES": names, "RESULTS": results,
               "OFFICIAL_F": official_f,
               "AGG": {"concelho": concelho, "distrito": distrito},
               "COUNTRIES": countries, "QA_VENCEDOR": {}}
    out = OUT_DIR / "resultados" / f"ee_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {out.name}: {out.stat().st_size/1e6:.2f} MB | freguesias {len(results)}")

    # QA
    if national_votes:
        tot = sum(national_votes.values())
        w = max(national_votes, key=lambda p: national_votes[p])
        print(f"  Vencedor nacional: {w} {100*national_votes[w]/tot:.2f}% | siglas: {parties[:8]}")
        print(f"  Mandatos ({sum(mand_p.values())}): {dict(sorted(mand_p.items(), key=lambda kv:-kv[1]))}")
    return True


def write_index(all_tags):
    order = ["2024", "2019", "2014", "2009", "2004", "1999", "1994", "1989", "1987"]
    years = [t for t in order if t in all_tags]
    idx = {"years": years, "labels": {t: t for t in years},
           "map_year": {t: MAP_YEAR[t] for t in years}}
    with open(OUT_DIR / "ee_index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> ee_index.json: {years}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    tags = list(EE_FILES) if ("--all" in sys.argv or not args) else [a for a in args if a in EE_FILES]
    if not tags:
        print(__doc__)
        sys.exit(1)
    for t in tags:
        build_tag(t)
    write_index([t for t in EE_FILES if t in tags or "--all" in sys.argv])
