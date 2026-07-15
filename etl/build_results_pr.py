# -*- coding: utf-8 -*-
"""Excel -> JSON de resultados das eleições PRESIDENCIAIS (PR).

Ao contrário da AR, a PR não tem ficheiros `certo` limpos à mão: os votos por
freguesia vêm diretamente das folhas oficiais (Distrito/Concelho/Freguesia, +
País nas modernas). Os "partidos" passam a ser CANDIDATOS; não há mandatos nem
d'Hondt (sistema maioritário a duas voltas).

Cada ano PR reutiliza a geometria (geojson) do ano AR mais próximo — ver MAP_YEAR.

Uso:
    python etl/build_results_pr.py --all
    python etl/build_results_pr.py 2021 2016

Saída:
    dados/resultados/pr_{tag}.json   (tag = ano, ou 1986_2 para a 2.ª volta)
    dados/pr_index.json
"""
import json
import sys
import unicodedata
from collections import defaultdict

import pandas as pd

from common import (RESULTADOS_DIR, OUT_DIR, norm_dicofre, circulo_from_dicofre,
                    is_freguesia_code, strip_accents_upper)
from candidate_aliases import resolve_candidate
from build_results import to_int, load_island_crosswalk, OLD_ISLAND_PREFIXES

PR_DIR = RESULTADOS_DIR.parent / "presidente da republica"

# tag -> ficheiro Excel
PR_FILES = {
    "1976": "PR_1976 .xlsx", "1980": "PR_1980.xlsx",
    "1986": "PR_1986_1.xlsx", "1986_2": "PR_1986_2.xlsx",
    "1991": "PR_1991.xlsx", "1996": "PR_1996.xlsx",
    "2001": "PR_2001.xlsx", "2006": "PR_2006.xlsx",
    "2011": "PR_2011_Globais.xls", "2016": "PR_2016_Globais.xls",
    "2021": "PR_2021_Globais.xlsx",
    "2026": "PR_2026_Globais.xlsx", "2026_2": "PR_2026_Globais_2ºSufrágio.xlsx",
}

# tag -> ano AR do mapa mais próximo (geometria já existente em dados/mapas/).
# 2026 usa a sua própria malha (CAOP2025), gerada por build_maps_2026.py.
MAP_YEAR = {
    "1976": 1976, "1980": 1980, "1986": 1985, "1986_2": 1985,
    "1991": 1991, "1996": 1995, "2001": 2002, "2006": 2005,
    "2011": 2011, "2016": 2015, "2021": 2022,
    "2026": 2026, "2026_2": 2026,
}



# rótulo mostrado no seletor de ano do frontend
PR_LABEL = {
    "1976": "1976", "1980": "1980",
    "1986": "1986 (1.ª volta)", "1986_2": "1986 (2.ª volta)",
    "1991": "1991", "1996": "1996", "2001": "2001", "2006": "2006",
    "2011": "2011", "2016": "2016", "2021": "2021",
    "2026": "2026 (1.ª volta)", "2026_2": "2026 (2.ª volta)",
}


def base_year(tag):
    return int(tag[:4])


# --------------------------------------------------------------- parsing -----

def find_sheet(xls, *needles):
    for sn in xls.sheet_names:
        low = sn.lower()
        if any(n in low for n in needles):
            return sn
    return None


def find_header_row(df, max_scan=10):
    for i in range(min(max_scan, len(df))):
        row = [str(x).strip().lower() for x in df.iloc[i].tolist()]
        if "inscritos" in row:
            return i
    return None


def _is_skip_col(cl):
    """Colunas a saltar entre 'nulos' e os candidatos (percentagens, votos válidos)."""
    if cl in ("", "nan"):
        return True
    if cl.startswith("%"):
        return True
    if "validament" in cl or "validos" in cl or "v�lidos" in cl:
        return True
    return False


def parse_pr_sheet(df):
    """Devolve (rows, cand_order, cand_meta).

    rows: lista de dicts {code, name, inscritos, votantes, brancos, nulos, votes}
    cand_order: nomes canónicos de candidatos pela ordem das colunas.
    cand_meta: {nome canónico: (cor, partido)} resolvido do cabeçalho bruto.
    """
    h = find_header_row(df)
    if h is None:
        raise ValueError("cabeçalho ('inscritos') não encontrado")
    hdr = [str(x).strip() for x in df.iloc[h].tolist()]
    low = [x.lower() for x in hdr]

    def idx(name):
        return low.index(name) if name in low else None

    i_insc, i_vot = idx("inscritos"), idx("votantes")
    i_bra, i_nul = idx("brancos"), idx("nulos")
    if i_nul is None:
        raise ValueError(f"'nulos' não encontrado em {hdr[:14]}")

    # candidatos: colunas após 'nulos' que não sejam %/votos válidos
    cand_cols = []          # (col_index, canonical_name)
    cand_meta = {}          # nome -> (cor, partido)
    seen = set()
    j = i_nul + 1
    while j < len(hdr):
        cl = low[j]
        if _is_skip_col(cl):
            j += 1
            continue
        nome, cor, part = resolve_candidate(hdr[j])
        if nome not in seen:
            cand_cols.append((j, nome))
            cand_meta[nome] = (cor, part)
            seen.add(nome)
        j += 1

    cand_order = [n for _, n in cand_cols]

    rows = []
    for r in df.iloc[h + 1:].itertuples(index=False):
        r = list(r)
        code = norm_dicofre(r[0]) if len(r) else None
        if code is None:
            continue
        votes = {}
        for ci, nome in cand_cols:
            v = to_int(r[ci]) if ci < len(r) else 0
            if v:
                votes[nome] = votes.get(nome, 0) + v
        rows.append({
            "code": code,
            "name": str(r[1]).strip() if len(r) > 1 and r[1] is not None else "",
            "inscritos": to_int(r[i_insc]) if i_insc is not None and i_insc < len(r) else 0,
            "votantes": to_int(r[i_vot]) if i_vot is not None and i_vot < len(r) else 0,
            "brancos": to_int(r[i_bra]) if i_bra is not None and i_bra < len(r) else 0,
            "nulos": to_int(r[i_nul]) if i_nul < len(r) else 0,
            "votes": votes,
        })
    return rows, cand_order, cand_meta


def distrito_key(code):
    """Código de distrito (antigo ou moderno) -> chave de círculo do frontend."""
    if code in ("230000", "500000", "000050", "000023", "810000"):
        return "national"
    if code in ("990000",):
        return "global"
    if code in ("600000",):
        return "estrangeiro"
    p2 = code[:2]
    if p2 in ("19", "20", "21", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49"):
        return "40"
    if p2 in ("22", "30", "31", "32"):
        return "30"
    if code == "800000":
        return "E1"
    if code == "900000":
        return "E2"
    if p2.isdigit() and 1 <= int(p2) <= 18 and code.endswith("0000"):
        return p2
    return None


# ------------------------------------------------------------- estrangeiro ---

def clean_country_name(name):
    """Nome de país -> forma canónica (agrupada) usada nos insets, tal como na AR."""
    name = str(name).strip()
    n = "".join(c for c in unicodedata.normalize("NFD", name)
                if unicodedata.category(c) != "Mn").upper().replace("�", "")
    table = [
        ("ALEMANHA", "Alemanha"), ("BELGICA", "Bélgica"), ("ESPANHA", "Espanha"),
        ("FRANA", "França"), ("FRANCA", "França"), ("PAISES BAIXOS", "Países Baixos"),
        ("LUXEMBURGO", "Luxemburgo"), ("REINO UNIDO", "Reino Unido da Grã-bretanha e Irlanda do Norte"),
        ("SUIA", "Suíça"), ("SUICA", "Suíça"),
        ("BRASIL", "Brasil"), ("CANAD", "Canadá"),
        ("ESTADOS UNIDOS", "Estados Unidos da América"),
    ]
    for needle, canon in table:
        if needle in n:
            return canon
    return None


def parse_pais(df, year):
    """Folha País -> ({E1,E2: {country: {...}}}, estrangeiro_total_entry)."""
    h = find_header_row(df)
    if h is None:
        return {"E1": {}, "E2": {}}, None
    rows = parse_pr_sheet(df)[0]
    countries = {"E1": {}, "E2": {}}
    estrangeiro = None
    circ_tot = {"E1": None, "E2": None}
    for r in rows:
        code = r["code"]
        if code == "600000":
            estrangeiro = r
            continue
        if not code[:1] == "8" and not code[:1] == "9":
            continue
        circ = "E1" if code.startswith("81") else "E2"
        # acumula agregado do círculo
        if circ_tot[circ] is None:
            circ_tot[circ] = {"votes": defaultdict(int), "inscritos": 0,
                              "votantes": 0, "brancos": 0, "nulos": 0}
        ct = circ_tot[circ]
        for k in ("inscritos", "votantes", "brancos", "nulos"):
            ct[k] += r[k]
        for p, v in r["votes"].items():
            ct["votes"][p] += v
        # país individual (só os reconhecidos, forma canónica agrupada)
        canon = clean_country_name(r["name"])
        if canon:
            dst = countries[circ].setdefault(canon, {"votes": defaultdict(int),
                     "inscritos": 0, "votantes": 0, "brancos": 0, "nulos": 0})
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                dst[k] += r[k]
            for p, v in r["votes"].items():
                dst["votes"][p] += v
    # normaliza defaultdicts -> dict
    out = {"E1": {}, "E2": {}}
    for circ in ("E1", "E2"):
        for cn, d in countries[circ].items():
            out[circ][cn] = {**d, "votes": dict(d["votes"]), "mandatos": 0}
    return out, estrangeiro, circ_tot


# ------------------------------------------------------------------ build ----

def reconcile_with_map(results, names, official_f, map_year):
    """Modelo híbrido: remapeia freguesias cujo RESULTADO existe com um código mas
    cuja GEOMETRIA está no mapa sob outro código (ex.: em 1996 as freguesias que só
    em 1998 formaram o concelho de Odivelas ainda estão codificadas em Loures, mas o
    mapa de 1995 usa já os códigos de Odivelas). Casa por nome normalizado dentro do
    mesmo distrito, apenas quando a correspondência é ÚNICA nos dois lados (sem
    ambiguidade). Move votos + oficiais + nome para o código do mapa."""
    map_path = OUT_DIR / "mapas" / f"freguesias_{map_year}.geojson"
    if not map_path.exists():
        return 0
    with open(map_path, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    map_name = {ft["properties"]["dicofre"]: (ft["properties"].get("nome") or "")
                for ft in feats}
    res_only = set(results) - set(map_name)
    map_only = set(map_name) - set(results)
    idx = defaultdict(list)
    for c in map_only:
        idx[(c[:2], strip_accents_upper(map_name[c]))].append(c)
    moved = 0
    for rc in list(res_only):
        cand = idx.get((rc[:2], strip_accents_upper(names.get(rc, ""))), [])
        if len(cand) != 1:
            continue
        new = cand[0]
        if new in results:
            continue
        results[new] = results.pop(rc)
        if rc in names:
            names[new] = names.pop(rc)
        if rc in official_f:
            official_f[new] = official_f.pop(rc)
        cand.remove(new)  # evita reutilizar o mesmo código do mapa
        moved += 1
    return moved


def sum_votes(list_of_votes):
    tot = defaultdict(int)
    for votes in list_of_votes:
        for p, v in votes.items():
            tot[p] += v
    return dict(tot)


def build_tag(tag):
    year = base_year(tag)
    map_year = MAP_YEAR[tag]
    print(f"=== PR {tag} (mapa {map_year}) ===")
    path = PR_DIR / PR_FILES[tag]
    xls = pd.ExcelFile(path)

    sn_freg = find_sheet(xls, "freguesia")
    sn_conc = find_sheet(xls, "concelho")
    sn_dist = find_sheet(xls, "distrito")
    sn_pais = find_sheet(xls, "pa�s", "país", "pais")

    if not sn_freg:
        raise ValueError(f"{path.name}: sem folha de freguesia")

    freg_rows, cand_order, cand_meta = parse_pr_sheet(
        pd.read_excel(xls, sn_freg, header=None, dtype=object))

    island_cw = load_island_crosswalk(map_year) if map_year <= 2005 else {}

    results, names, official_f = {}, {}, {}
    for r in freg_rows:
        code = r["code"]
        if code[:2] in OLD_ISLAND_PREFIXES and code in island_cw:
            code = island_cw[code]
        if not is_freguesia_code(code):
            continue
        if tag == "1986" and code in ("111001", "170308"):
            continue
        if code in results:
            for cand, v in r["votes"].items():
                results[code][cand] = results[code].get(cand, 0) + v
            official_f[code][0] += r["inscritos"]
            official_f[code][1] += r["votantes"]
            official_f[code][2] += r["brancos"]
            official_f[code][3] += r["nulos"]
            if r["name"] and r["name"].strip().lower() != names[code].strip().lower():
                names[code] = f"{names[code]} / {r['name']}"
        else:
            results[code] = dict(r["votes"])
            names[code] = r["name"]
            official_f[code] = [r["inscritos"], r["votantes"], r["brancos"], r["nulos"]]

    print(f"  freguesias: {len(results)} | candidatos: {cand_order}")

    # modelo híbrido: reconciliar códigos de resultado com a geometria do mapa
    moved = reconcile_with_map(results, names, official_f, map_year)
    if moved:
        print(f"  reconciliação com mapa {map_year}: {moved} freguesias remapeadas por nome")

    # agregados a partir das freguesias (consistentes com o mapa)
    agg_conc, agg_dist = defaultdict(list), defaultdict(list)
    for code, votes in results.items():
        agg_conc[code[:4]].append(votes)
        circ = circulo_from_dicofre(code)
        if circ:
            agg_dist[circ].append(votes)
    concelho = {k: {"votes": sum_votes(v)} for k, v in agg_conc.items()}
    distrito = {k: {"votes": sum_votes(v)} for k, v in agg_dist.items()}
    national_votes = sum_votes(results.values())

    # camada oficial: distrito/concelho (insc/bra/nul + national)
    national_off = None
    if sn_dist:
        for r in parse_pr_sheet(pd.read_excel(xls, sn_dist, header=None, dtype=object))[0]:
            key = distrito_key(r["code"])
            if key == "national":
                national_off = r
            elif key in distrito:
                distrito[key].update({"nome_oficial": r["name"], "inscritos": r["inscritos"],
                                      "votantes": r["votantes"], "brancos": r["brancos"],
                                      "nulos": r["nulos"]})
    if sn_conc:
        for r in parse_pr_sheet(pd.read_excel(xls, sn_conc, header=None, dtype=object))[0]:
            code = r["code"]
            if code.endswith("00") and not code.endswith("0000") and code[:4] in concelho:
                concelho[code[:4]].update({"inscritos": r["inscritos"], "votantes": r["votantes"],
                                           "brancos": r["brancos"], "nulos": r["nulos"]})

    meta = {
        "year": tag,
        "election": "pr",
        "round": 2 if tag.endswith("_2") else 1,
        "parties": {n: {"nome": n, "cor": cand_meta[n][0], "partido": cand_meta[n][1]}
                    for n in cand_order},
        "national": {"votes": national_votes},
    }
    if national_off:
        meta["national"].update({"inscritos": national_off["inscritos"],
                                 "votantes": national_off["votantes"],
                                 "brancos": national_off["brancos"],
                                 "nulos": national_off["nulos"]})

    countries = {}
    if sn_pais:
        try:
            countries, estr, circ_tot = parse_pais(
                pd.read_excel(xls, sn_pais, header=None, dtype=object), year)
            # círculos E1/E2 (agregado) para colorir os insets
            for circ in ("E1", "E2"):
                ct = circ_tot.get(circ)
                if ct:
                    distrito[circ] = {"votes": dict(ct["votes"]),
                                      "inscritos": ct["inscritos"], "votantes": ct["votantes"],
                                      "brancos": ct["brancos"], "nulos": ct["nulos"]}
            # estrangeiro + global (território + estrangeiro)
            if estr:
                meta["estrangeiro"] = {"votes": estr["votes"], "inscritos": estr["inscritos"],
                                       "votantes": estr["votantes"], "brancos": estr["brancos"],
                                       "nulos": estr["nulos"]}
                gv = sum_votes([national_votes, estr["votes"]])
                base_off = national_off or {"inscritos": 0, "votantes": 0, "brancos": 0, "nulos": 0}
                meta["global"] = {
                    "votes": gv,
                    "inscritos": base_off["inscritos"] + estr["inscritos"],
                    "votantes": base_off["votantes"] + estr["votantes"],
                    "brancos": base_off["brancos"] + estr["brancos"],
                    "nulos": base_off["nulos"] + estr["nulos"],
                }
        except Exception as e:
            print(f"  AVISO: falha ao ler folha País ({e})")

    payload = {"METADATA": meta, "NAMES": names, "RESULTS": results,
               "OFFICIAL_F": official_f,
               "AGG": {"concelho": concelho, "distrito": distrito},
               "COUNTRIES": countries, "QA_VENCEDOR": {}}

    out = OUT_DIR / "resultados" / f"pr_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {out.name}: {out.stat().st_size/1e6:.2f} MB")

    # QA
    if national_off:
        soma_map = sum(national_votes.values())
        soma_of = sum(national_off["votes"].values())
        print(f"  QA: soma freguesias={soma_map:,} vs distrito nacional={soma_of:,} "
              f"(diff {soma_map - soma_of:+,})")
    w = max(national_votes.items(), key=lambda kv: kv[1]) if national_votes else None
    if w:
        tot = sum(national_votes.values())
        print(f"  Vencedor nacional (território): {w[0]} {100*w[1]/tot:.2f}%")
    return True


def write_index(tags):
    idx = {
        "years": [t for t in PR_FILES if t in tags or not tags],
        "labels": {t: PR_LABEL[t] for t in PR_FILES},
        "map_year": {t: MAP_YEAR[t] for t in PR_FILES},
    }
    # ordem: mais recente primeiro (2.ª volta logo após a 1.ª)
    order = ["2026_2", "2026", "2021", "2016", "2011", "2006", "2001", "1996", "1991",
             "1986_2", "1986", "1980", "1976"]
    idx["years"] = [t for t in order if t in PR_FILES]
    out = OUT_DIR / "pr_index.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> {out.name}: {idx['years']}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--all" in sys.argv or not args:
        tags = list(PR_FILES.keys())
    else:
        tags = [a for a in args if a in PR_FILES]
    if not tags:
        print(__doc__)
        sys.exit(1)
    for t in tags:
        build_tag(t)
    write_index(tags)
