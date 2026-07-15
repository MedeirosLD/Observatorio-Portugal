# -*- coding: utf-8 -*-
"""Resultados das eleições AUTÁRQUICAS (CM, AM, AF) -> JSON.

Cada ano tem três eleições:
  - CM: Câmara Municipal (folha Concelho, colore distritos por presidentes, concelhos por vencedor)
  - AM: Assembleia Municipal (folha Concelho, sem presidentes)
  - AF: Assembleia de Freguesia (folha Freguesia + Concelho + Distrito, colore freguesias por vencedor)

Uso:
    python etl/build_results_au.py --all
    python etl/build_results_au.py 2021 2025
Saída:
    dados/resultados/au_{cm|am|af}_{ano}.json
    dados/au_index.json
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
import pandas as pd

from common import (PROJECT_ROOT, OUT_DIR, norm_dicofre, circulo_from_dicofre,
                    is_freguesia_code, strip_accents_upper, OLD_CONC_TO_MODERN, dhondt)
from build_results import to_int, load_island_crosswalk, OLD_ISLAND_PREFIXES

MAPPING_1997_FREGUESIA = {
    # Odivelas (split from Loures 1107 to Odivelas 1116)
    "110704": "111601",  # Caneças
    "110720": "111602",  # Famões
    "110710": "111603",  # Odivelas
    "110725": "111604",  # Olival Basto
    "110718": "111605",  # Pontinha
    "110711": "111606",  # Póvoa de Santo Adrião
    "110721": "111607",  # Ramada
    
    # Vizela (split from Guimarães 0308, Felgueiras 1303, Lousada 1305 to Vizela 0314)
    "130519": "031401",  # Barrosas (Santa Eulália) (Lousada)
    "030852": "031402",  # Caldas de Vizela (São João) (Guimarães)
    "030859": "031403",  # Caldas de Vizela (São Miguel) (Guimarães)
    "030825": "031404",  # Infias (Guimarães)
    "030870": "031405",  # Tagilde (Guimarães)
    "130322": "031406",  # Vizela (Santo Adrião) (Felgueiras)
    "030861": "031407",  # Vizela (São Paio) (Guimarães)
    
    # Trofa (split from Santo Tirso 1314 to Trofa 1318)
    "131403": "131801",  # Alvarelhos
    "131421": "131802",  # Bougado (Santiago)
    "131425": "131803",  # Bougado (São Martinho)
    "131422": "131804",  # Coronado (São Mamede)
    "131428": "131805",  # Coronado (São Romão)
    "131408": "131806",  # Covelas
    "131409": "131807",  # Guidões
    "131414": "131808",  # Muro
}
from build_results_pr import reconcile_with_map, find_sheet

AU_DIR = PROJECT_ROOT / "resultados" / "resultados puros (sem alteração minha)"

# Mapeamento do ano AU para o ano AR do mapa correspondente
MAP_YEAR = {
    "1976": 1976, "1979": 1979, "1982": 1983, "1985": 1985,
    "1989": 1991, "1993": 1993, "1997": 1997, "2001": 2002,
    "2005": 2005, "2009": 2009, "2013": 2015, "2017": 2019,
    "2021": 2022, "2025": 2026
}

AU_YEARS = sorted(list(MAP_YEAR.keys()), key=int, reverse=True)

# Crosswalk de CONCELHO de ilha: código antigo (distrito 19-22 + concelho) -> DICOFRE
# moderno (4 díg.) usado nos mapas. Os códigos antigos de freguesia são sequenciais
# dentro do distrito (não codificam o concelho), por isso o crosswalk de freguesia
# (junção_D) NÃO serve para concelhos — este mapa por concelho é estável em 1976-2005.
# Gerado e validado por correspondência de nomes contra concelhos_2005.geojson (30/30).
ISLAND_CONCELHO_CW = OLD_CONC_TO_MODERN


def get_au_filepath(year, sub):
    sub_upper = sub.upper()
    if year == "2025":
        return AU_DIR / f"resultados_eleicoes_AUT25_{sub_upper}.xlsx"
    elif year == "2013":
        return AU_DIR / f"Resultados_eleicoes_{sub_upper}_2013.xlsx"
    else:
        return AU_DIR / f"resultados_eleicoes_{sub_upper}_{year}.xlsx"


def level_key(code):
    """Código de agregado -> chave de círculo/nível."""
    if code in ("500000", "810000", "005000", "008100", "000000", "230000"):
        return "national"
    if code.endswith("0000") and code[:2].isdigit():
        return code[:2]
    return None


def find_header_row(df, max_scan=15):
    for i in range(min(max_scan, len(df))):
        row = [str(x).strip().lower() for x in df.iloc[i].tolist()]
        if any("inscrito" in c or c == "inscritos" for c in row):
            return i
    return None


def parse_au_sheet(df, level, is_2025=False):
    """
    Parses a sheet from DataFrame df.
    level: distrito|concelho|freguesia|national
    """
    h = find_header_row(df)
    if h is None:
        return []
    hdr = [str(x).strip() for x in df.iloc[h].tolist()]
    low = [x.lower() for x in hdr]

    code_col = next((j for j, c in enumerate(low) if "código" in c or "codigo" in c or c == "cod"), None)
    if code_col is None:
        code_col = 1 if is_2025 else 0

    name_col = next((j for j, c in enumerate(low) if "nome" in c or "territ" in c or c == "concelho" or c == "freguesia"), None)
    if name_col is None:
        name_col = code_col + 1

    i_insc = next((j for j, c in enumerate(low) if c.startswith("inscr")), None)
    i_vot = next((j for j, c in enumerate(low) if c.startswith("votant") or c == "votos"), None)
    i_bra = next((j for j, c in enumerate(low) if "branco" in c), None)
    i_nul = next((j for j, c in enumerate(low) if "nulo" in c), None)
    
    i_mand_total = next((j for j, c in enumerate(low) if c.startswith("mand") and not any(char.isdigit() for char in c) and "atribuir" not in c), None)

    # Encontrar todas as colunas de "opção N"
    option_indices = []
    for j, c in enumerate(low):
        if re.match(r'^op.*\d+$', c):
            option_indices.append(j)

    option_groups = []
    for idx_idx, j in enumerate(option_indices):
        next_j = option_indices[idx_idx + 1] if idx_idx + 1 < len(option_indices) else len(hdr)
        group_cols = {}
        for col_idx in range(j + 1, next_j):
            c_sub = low[col_idx]
            if "voto" in c_sub and not ("%" in c_sub or "pct" in c_sub):
                group_cols["votos"] = col_idx
            elif "mand" in c_sub:
                group_cols["mandatos"] = col_idx
            elif "presid" in c_sub:
                group_cols["presidentes"] = col_idx
            elif "maioria" in c_sub:
                group_cols["maiorias"] = col_idx
            elif "concorre" in c_sub:
                group_cols["concorreu"] = col_idx
        option_groups.append((j, group_cols))

    rows = []
    for r in df.iloc[h + 1:].itertuples(index=False):
        r = list(r)
        if len(r) <= max(code_col, name_col):
            continue
            
        if is_2025:
            row_tipo = str(r[0]).strip().lower()
            target_tipo = {
                "national": "território nacional",
                "distrito": "distrito/ra",
                "concelho": "concelho",
                "freguesia": "freguesia"
            }.get(level)
            
            def clean_tipo(s):
                return s.replace("á", "a").replace("í", "i").replace("ó", "o")
            if clean_tipo(row_tipo) != clean_tipo(target_tipo):
                continue

        code = norm_dicofre(r[code_col])
        if code is None:
            continue

        opts = {}
        for j, group_cols in option_groups:
            if j >= len(r):
                continue
            sigla = str(r[j]).strip()
            if not sigla or sigla.lower() in ("", "nan", "null"):
                continue
            
            v = to_int(r[group_cols["votos"]]) if "votos" in group_cols and group_cols["votos"] < len(r) else 0
            m = to_int(r[group_cols["mandatos"]]) if "mandatos" in group_cols and group_cols["mandatos"] < len(r) else 0
            p = to_int(r[group_cols["presidentes"]]) if "presidentes" in group_cols and group_cols["presidentes"] < len(r) else 0
            ma = to_int(r[group_cols["maiorias"]]) if "maiorias" in group_cols and group_cols["maiorias"] < len(r) else 0
            c = to_int(r[group_cols["concorreu"]]) if "concorreu" in group_cols and group_cols["concorreu"] < len(r) else 0

            if sigla not in opts:
                opts[sigla] = {"votos": 0, "mandatos": 0, "presidentes": 0, "maiorias": 0, "concorreu": 0}
            opts[sigla]["votos"] += v
            opts[sigla]["mandatos"] += m
            opts[sigla]["presidentes"] += p
            opts[sigla]["maiorias"] += ma
            opts[sigla]["concorreu"] += c

        rows.append({
            "code": code,
            "name": str(r[name_col]).strip() if r[name_col] is not None else "",
            "inscritos": to_int(r[i_insc]) if i_insc is not None and i_insc < len(r) else 0,
            "votantes": to_int(r[i_vot]) if i_vot is not None and i_vot < len(r) else 0,
            "brancos": to_int(r[i_bra]) if i_bra is not None and i_bra < len(r) else 0,
            "nulos": to_int(r[i_nul]) if i_nul is not None and i_nul < len(r) else 0,
            "mandatos_total": to_int(r[i_mand_total]) if i_mand_total is not None and i_mand_total < len(r) else 0,
            "opts": opts
        })
    return rows


def build_tag_sub(year, sub):
    path = get_au_filepath(year, sub)
    if not path.exists():
        print(f"Ficheiro não existe: {path}")
        return False
    
    map_year = MAP_YEAR[year]
    print(f"=== AU {year} {sub.upper()} (mapa {map_year}) ===")
    
    if year == "2025":
        df = pd.read_excel(path, sheet_name=0, header=None, dtype=object)
        freg_rows = parse_au_sheet(df, "freguesia", is_2025=True)
        conc_rows = parse_au_sheet(df, "concelho", is_2025=True)
        dist_rows = parse_au_sheet(df, "distrito", is_2025=True)
        nat_rows = parse_au_sheet(df, "national", is_2025=True)
    else:
        xls = pd.ExcelFile(path)
        freg_rows = []
        sn_freg = find_sheet(xls, "freguesia")
        if sn_freg:
            freg_rows = parse_au_sheet(pd.read_excel(xls, sn_freg, header=None, dtype=object), "freguesia")
        sn_conc = find_sheet(xls, "concelho")
        conc_rows = parse_au_sheet(pd.read_excel(xls, sn_conc, header=None, dtype=object), "concelho")
        sn_dist = find_sheet(xls, "distrito")
        dist_rows = parse_au_sheet(pd.read_excel(xls, sn_dist, header=None, dtype=object), "distrito")
        nat_rows = []

    # Encontrar linha nacional
    national_row = None
    for r in nat_rows + dist_rows:
        if level_key(r["code"]) == "national":
            national_row = r
            break

    # Crosswalk de ilhas (códigos antigos -> DICOFRE moderno). Só até 2005.
    # Freguesia: junção_D {antigo6: novo6}; Concelho: mapa estático por concelho
    # (o código antigo de freguesia é sequencial no distrito e não serve para concelho).
    island_cw = load_island_crosswalk(map_year) if map_year <= 2005 else {}
    conc_cw = ISLAND_CONCELHO_CW if map_year <= 2005 else {}

    # Processamento Freguesias (Todos os subtipos descem a freguesias)
    results, names, official_f = {}, {}, {}
    if freg_rows:
        for r in freg_rows:
            code = r["code"]
            if year in ("1993", "1997") and code in MAPPING_1997_FREGUESIA:
                code = MAPPING_1997_FREGUESIA[code]
            if code[:2] in OLD_ISLAND_PREFIXES and code in island_cw:
                code = island_cw[code]
            if not is_freguesia_code(code):
                continue
            results[code] = {sigla: o["votos"] for sigla, o in r["opts"].items()}
            names[code] = r["name"]
            official_f[code] = [r["inscritos"], r["votantes"], r["brancos"], r["nulos"],
                                 r["mandatos_total"], {sigla: o["mandatos"] for sigla, o in r["opts"].items()}]
        
        moved = reconcile_with_map(results, names, official_f, map_year)
        if moved:
            print(f"  reconciliação com mapa {map_year}: {moved} freguesias remapeadas por nome")

    # Agregados Concelho
    concelho = {}
    for r in conc_rows:
        code = r["code"]
        if code.endswith("00") and not code.endswith("0000"):
            c_key = code[:4]
            # Ilhas antigas (19/20/21/22..) -> código moderno do mapa (31/32/4x).
            if c_key[:2] in OLD_ISLAND_PREFIXES and c_key in conc_cw:
                c_key = conc_cw[c_key]
            dst = concelho.get(c_key)
            if dst is None:
                dst = {"votes": defaultdict(int), "mandatos_p": defaultdict(int),
                       "presidents": defaultdict(int), "maiorias": defaultdict(int),
                       "inscritos": 0, "votantes": 0, "brancos": 0, "nulos": 0,
                       "mandatos": 0}
                concelho[c_key] = dst
            for sigla, o in r["opts"].items():
                dst["votes"][sigla] += o["votos"]
                dst["mandatos_p"][sigla] += o["mandatos"]
                dst["presidents"][sigla] += o["presidentes"]
                dst["maiorias"][sigla] += o["maiorias"]
            dst["mandatos"] += r["mandatos_total"]
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                dst[k] += r[k]
    if year in ("1993", "1997"):
        if sub in ("cm", "am"):
            # Odivelas, Vizela, Trofa did not exist as independent concelhos for CM/AM.
            # They copy the results of their mother concelhos (Loures, Guimarães, Santo Tirso).
            import copy
            if "1107" in concelho:
                concelho["1116"] = copy.deepcopy(concelho["1107"])
            if year == "1997":
                if "0308" in concelho:
                    concelho["0314"] = copy.deepcopy(concelho["0308"])
                if "1314" in concelho:
                    concelho["1318"] = copy.deepcopy(concelho["1314"])
        else:
            # Under AF (Assembleia de Freguesia), they had local junta elections,
            # so we aggregate child concelhos and subtract them from mother concelhos.
            child_to_fregs = {
                "1116": ["111601", "111602", "111603", "111604", "111605", "111606", "111607"],
            }
            if year == "1997":
                child_to_fregs["0314"] = ["031401", "031402", "031403", "031404", "031405", "031406", "031407"]
                child_to_fregs["1318"] = ["131801", "131802", "131803", "131804", "131805", "131806", "131807", "131808"]
            
            freg_to_mother = {
                # Odivelas
                "111601": "1107", "111602": "1107", "111603": "1107", "111604": "1107", "111605": "1107", "111606": "1107", "111607": "1107",
            }
            if year == "1997":
                freg_to_mother.update({
                    # Vizela
                    "031401": "1305", "031402": "0308", "031403": "0308", "031404": "0308", "031405": "0308", "031406": "1303", "031407": "0308",
                    # Trofa
                    "131801": "1314", "131802": "1314", "131803": "1314", "131804": "1314", "131805": "1314", "131806": "1314", "131807": "1314", "131808": "1314"
                })
            
            # Build child concelhos by summing their freguesias
            for c_key, f_list in child_to_fregs.items():
                c_votes = defaultdict(int)
                insc = vot = bra = nul = 0
                for f_code in f_list:
                    if f_code in official_f:
                        f_off = official_f[f_code]  # [inscritos, votantes, brancos, nulos, mandatos_total, opts_mandatos]
                        insc += f_off[0]
                        vot += f_off[1]
                        bra += f_off[2]
                        nul += f_off[3]
                    if f_code in results:
                        for p, v in results[f_code].items():
                            c_votes[p] += v
                
                # Calculate mandatos via d'hondt
                num_seats = 11 if c_key == "1116" else 7
                mandatos_p = dhondt(dict(c_votes), num_seats)
                
                # President and maioria
                sorted_parties = sorted(c_votes.items(), key=lambda x: x[1], reverse=True)
                presidents = {}
                maiorias = {}
                if sorted_parties:
                    winner = sorted_parties[0][0]
                    presidents[winner] = 1
                    if mandatos_p.get(winner, 0) > num_seats / 2:
                        maiorias[winner] = 1
                        
                concelho[c_key] = {
                    "votes": dict(c_votes),
                    "mandatos_p": mandatos_p,
                    "presidents": presidents,
                    "maiorias": maiorias,
                    "inscritos": insc,
                    "votantes": vot,
                    "brancos": bra,
                    "nulos": nul,
                    "mandatos": num_seats
                }
                
            # Subtract child freguesias from mother concelhos
            for f_code, m_key in freg_to_mother.items():
                if m_key in concelho and f_code in results:
                    m_dst = concelho[m_key]
                    # Subtract votes
                    for p, v in results[f_code].items():
                        if p in m_dst["votes"]:
                            m_dst["votes"][p] -= v
                            if m_dst["votes"][p] <= 0:
                                del m_dst["votes"][p]
                    # Subtract metadados
                    if f_code in official_f:
                        f_off = official_f[f_code]
                        m_dst["inscritos"] -= f_off[0]
                        m_dst["votantes"] -= f_off[1]
                        m_dst["brancos"] -= f_off[2]
                        m_dst["nulos"] -= f_off[3]

    # defaultdict -> dict
    for c_val in concelho.values():
        for k in ("votes", "mandatos_p", "presidents", "maiorias"):
            c_val[k] = dict(c_val[k])

    # Agregados Distrito
    distrito = {}
    for r in dist_rows:
        # Distritos de ilha antigos (19/20/21/22) são reconstruídos como 30/40 pelo
        # fallback a partir dos concelhos já remapeados — ignorar as linhas antigas.
        if r["code"][:2] in OLD_ISLAND_PREFIXES:
            continue
        d_key = level_key(r["code"])
        if d_key and d_key != "national":
            distrito[d_key] = {
                "votes": {sigla: o["votos"] for sigla, o in r["opts"].items()},
                "mandatos_p": {sigla: o["mandatos"] for sigla, o in r["opts"].items()},
                "presidents": {sigla: o["presidentes"] for sigla, o in r["opts"].items()},
                "maiorias": {sigla: o["maiorias"] for sigla, o in r["opts"].items()},
                "inscritos": r["inscritos"],
                "votantes": r["votantes"],
                "brancos": r["brancos"],
                "nulos": r["nulos"],
                "mandatos": r["mandatos_total"]
            }

    # Fallback agregados Distrito a partir de concelhos se distrito estiver em falta/vazio
    for d_key in ["01","02","03","04","05","06","07","08","09","10","11","12","13","14","15","16","17","18","30","40"]:
        if d_key not in distrito or not distrito[d_key]["votes"]:
            concs = [c_val for c_key, c_val in concelho.items() if circulo_from_dicofre(c_key + "00") == d_key]
            if concs:
                votes_sum = defaultdict(int)
                mandatos_sum = defaultdict(int)
                presidents_sum = defaultdict(int)
                maiorias_sum = defaultdict(int)
                insc = vot = bra = nul = mand_tot = 0
                for c_val in concs:
                    insc += c_val["inscritos"]
                    vot += c_val["votantes"]
                    bra += c_val["brancos"]
                    nul += c_val["nulos"]
                    mand_tot += c_val["mandatos"]
                    for p, v in c_val["votes"].items(): votes_sum[p] += v
                    for p, m in c_val["mandatos_p"].items(): mandatos_sum[p] += m
                    for p, pr in c_val["presidents"].items(): presidents_sum[p] += pr
                    for p, ma in c_val["maiorias"].items(): maiorias_sum[p] += ma
                
                distrito[d_key] = {
                    "votes": dict(votes_sum),
                    "mandatos_p": dict(mandatos_sum),
                    "presidents": dict(presidents_sum),
                    "maiorias": dict(maiorias_sum),
                    "inscritos": insc,
                    "votantes": vot,
                    "brancos": bra,
                    "nulos": nul,
                    "mandatos": mand_tot
                }

    # Totais Nacionais
    if national_row:
        nat_votes = {sigla: o["votos"] for sigla, o in national_row["opts"].items()}
        nat_mandatos = {sigla: o["mandatos"] for sigla, o in national_row["opts"].items()}
        nat_presidents = {sigla: o["presidentes"] for sigla, o in national_row["opts"].items()}
        nat_maiorias = {sigla: o["maiorias"] for sigla, o in national_row["opts"].items()}
        nat_insc = national_row["inscritos"]
        nat_vot = national_row["votantes"]
        nat_bra = national_row["brancos"]
        nat_nul = national_row["nulos"]
        nat_mand_total = national_row["mandatos_total"]
    else:
        # Soma a partir dos distritos
        nat_votes = defaultdict(int)
        nat_mandatos = defaultdict(int)
        nat_presidents = defaultdict(int)
        nat_maiorias = defaultdict(int)
        nat_insc = nat_vot = nat_bra = nat_nul = nat_mand_total = 0
        for d_val in distrito.values():
            nat_insc += d_val["inscritos"]
            nat_vot += d_val["votantes"]
            nat_bra += d_val["brancos"]
            nat_nul += d_val["nulos"]
            nat_mand_total += d_val["mandatos"]
            for p, v in d_val["votes"].items(): nat_votes[p] += v
            for p, m in d_val["mandatos_p"].items(): nat_mandatos[p] += m
            for p, pr in d_val["presidents"].items(): nat_presidents[p] += pr
            for p, ma in d_val["maiorias"].items(): nat_maiorias[p] += ma
        nat_votes = dict(nat_votes)
        nat_mandatos = dict(nat_mandatos)
        nat_presidents = dict(nat_presidents)
        nat_maiorias = dict(nat_maiorias)

    all_siglas = set(nat_votes.keys()) | set(nat_mandatos.keys()) | set(nat_presidents.keys()) | set(nat_maiorias.keys())
    national_parties = {}
    for sigla in all_siglas:
        national_parties[sigla] = {
            "votos": nat_votes.get(sigla, 0),
            "mandatos": nat_mandatos.get(sigla, 0),
            "presidentes": nat_presidents.get(sigla, 0),
            "maiorias": nat_maiorias.get(sigla, 0),
            "concorreu": sum(1 for c_val in concelho.values() if sigla in c_val["votes"])
        }

    parties_meta = {p: {"nome": p} for p in sorted(all_siglas, key=lambda p: nat_votes.get(p, 0), reverse=True)}
    
    meta = {
        "year": year,
        "election": "au",
        "subtype": sub,
        "parties": parties_meta,
        "national": {
            "votes": nat_votes,
            "inscritos": nat_insc,
            "votantes": nat_vot,
            "brancos": nat_bra,
            "nulos": nat_nul,
            "mandatos": nat_mand_total,
            "parties": national_parties
        }
    }
    
    payload = {
        "METADATA": meta,
        "NAMES": names,
        "RESULTS": results,
        "OFFICIAL_F": official_f,
        "AGG": {
            "concelho": concelho,
            "distrito": distrito
        },
        "QA_VENCEDOR": {}
    }

    out = OUT_DIR / "resultados" / f"au_{sub}_{year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    
    print(f"  -> {out.name}: {out.stat().st_size/1e6:.2f} MB")
    
    # Exibir logs de QA rápidos
    if sub == "cm" and nat_presidents:
        sorted_p = sorted(nat_presidents.items(), key=lambda kv: -kv[1])[:5]
        print(f"  QA Presidentes de Câmara: {dict(sorted_p)}")
    elif sub == "af" and nat_presidents:
        sorted_p = sorted(nat_presidents.items(), key=lambda kv: -kv[1])[:5]
        print(f"  QA Presidentes de Junta: {dict(sorted_p)}")
    return True


def write_index(all_years):
    years = [y for y in AU_YEARS if y in all_years]
    idx = {
        "years": years,
        "subtypes": ["cm", "am", "af"],
        "map_year": {t: MAP_YEAR[t] for t in years}
    }
    with open(OUT_DIR / "au_index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> au_index.json: {years}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    years = AU_YEARS if ("--all" in sys.argv or not args) else [a for a in args if a in MAP_YEAR]
    if not years:
        print(__doc__)
        sys.exit(1)
        
    processed_years = set()
    for y in years:
        ok = False
        for sub in ["cm", "am", "af"]:
            if build_tag_sub(y, sub):
                ok = True
        if ok:
            processed_years.add(y)
            
    write_index([y for y in AU_YEARS if y in processed_years or "--all" in sys.argv])
