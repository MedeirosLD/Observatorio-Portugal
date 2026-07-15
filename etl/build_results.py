# -*- coding: utf-8 -*-
"""Excel -> JSON de resultados para o visualizador.

Fontes por ano:
  A) `PT {ano} certo.xlsx` — votos por freguesia (fonte canónica das siglas)
  B) workbook oficial "Globais" — mandatos, inscritos, brancos/nulos e totais
     oficiais por distrito/concelho/nacional (+ círculos Europa/Fora da Europa)

Uso:
    python etl/build_results.py 2025 2022
    python etl/build_results.py --all

Saída: dados/resultados/ar_{ano}.json
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict

import pandas as pd

from common import (MAPAS_DIR, RESULTADOS_DIR, RAW_DIR, OUT_DIR, YEARS, norm_dicofre,
                    circulo_from_dicofre, is_freguesia_code, OLD_CONC_TO_MODERN,
                    strip_accents_upper)
from party_aliases import globais_party_to_certo
from build_maps import find_year_shapefile
from ar_circulos_extra import MANUAL_CIRCLE_DATA

# Prefixos de distrito ANTIGO usados nos resultados de ilhas até 2005:
# 19 = Angra do Heroísmo, 20 = Horta, 21 = Ponta Delgada (Açores), 22 = Funchal (Madeira).
OLD_ISLAND_PREFIXES = {"19", "20", "21", "22"}

# Anos cujo shapefile de ilhas não traz junção_D (ou não tem ilhas): usar o crosswalk de outro ano.
ISLAND_CROSSWALK_FALLBACK = {2005: 2002}

_ISLAND_CROSSWALK_CACHE = {}


def load_island_crosswalk(year):
    """Devolve {código_antigo(6): DICOFRE_moderno(6)} a partir do shapefile de ilhas
    do ano (colunas junção_D -> DICOFRE). Anos sem junção_D usam o fallback (2005->2002)."""
    if year in _ISLAND_CROSSWALK_CACHE:
        return _ISLAND_CROSSWALK_CACHE[year]

    src_year = ISLAND_CROSSWALK_FALLBACK.get(year, year)
    shp = find_year_shapefile(MAPAS_DIR / "madeira e açores freguesias", src_year)
    cw = {}
    if shp is not None:
        import geopandas as gpd
        try:
            g = gpd.read_file(shp)
            if "junção_D" in g.columns and "DICOFRE" in g.columns:
                for old, new in zip(g["junção_D"], g["DICOFRE"]):
                    if old is None or new is None:
                        continue
                    old_s = str(old).strip()
                    if old_s.endswith(".0"):
                        old_s = old_s[:-2]
                    o = old_s.zfill(6)
                    n = norm_dicofre(new)
                    if o and n:
                        # Corrigir typos e colisões de nomes nos shapefiles de 2002/2005
                        if o == "220305" and n == "460304":
                            cw["220305"] = "310305"
                            cw["200704"] = "460304"
                            continue
                        if o == "200704" and n == "310305":
                            continue
                        if o == "220401" and n == "310401":
                            cw["220901"] = "310401"
                        if o == "190201" and n == "310102":
                            cw["190201"] = "450101"
                            continue
                        if o == "220102" and n == "450101":
                            cw["220102"] = "310102"
                            continue
                        if o == "200603" and n == "311002":
                            cw["200603"] = "480203"
                            continue
                        if o == "221102" and n == "480203":
                            cw["221102"] = "311002"
                            continue
                        if o == "210206" and n == "310903":
                            cw["210206"] = "420207"
                            continue
                        if o == "221003" and n == "420207":
                            cw["221003"] = "310903"
                            continue
                        cw[o] = n
        except Exception as e:
            print(f"  AVISO: falha a ler crosswalk de ilhas {src_year} ({e})")
            
    # Fallback mappings for old island codes that are unresolved in older shapefiles (1975-1995)
    fallback_mappings = {
        "190119": "430110",
        "200406": "460105",
        "210105": "420102",
        "210207": "420206",
        "210321": "420305",
        "210322": "420319",
        "210513": "420504",
        "210514": "420514",
        "210605": "420603",
        "221006": "310906",
        # Novos fallbacks para 2006
        "210208": "420208",
        "210209": "420209",
        "210210": "420210",
        "210323": "420323",
        "210324": "420324",
        "210325": "420325",
        "210606": "420606"
    }
    for o_code, n_code in fallback_mappings.items():
        if o_code not in cw:
            cw[o_code] = n_code
            
    _ISLAND_CROSSWALK_CACHE[year] = cw
    return cw

NON_PARTY_COLS = {"soma", "vencedor", "div admin", "msg", "código", "codigo",
                  "cod_stape", "cod", "denominação", "denominacao",
                  "nome do território", "nome do territorio", "nome da freguesia",
                  "freguesia", "nome", "concelho", "município", "municipio"}

RAW_FILES = {
    2025: "AR_2025_Globais.xlsx", 2024: "AR_2024_Globais.xlsx",
    2022: "AR_2022_Globais.xlsx", 2019: "AR_2019_Globais.xlsx",
    2015: "AR_2015_Globais.xls", 2011: "AR_2011_Globais.xls",
    2009: "AR2009_Globais.xls", 2005: "AR2005_Nacional.xls", 2002: "AR2002.xls",
    1999: "AR1999.xls", 1995: "AR1995.xls", 1991: "AR1991.xls",
    1987: "AR1987.xls", 1985: "AR1985.xls", 1983: "AR1983.xls",
    1980: "AR1980.xls", 1979: "AR1979.xls", 1976: "AR1976.xls",
    1975: "AC1975.xls",
}

DISTRITO_CODE_TO_KEY = {"300000": "30", "310000": "30", "320000": "30", "000030": "30", "220000": "30",
                        "400000": "40", "410000": "40", "000040": "40", "190000": "40",
                        "800000": "E1", "900000": "E2", "000081": "E1", "000082": "E2", "810000": "E1", "820000": "E2"}


def to_int(v):
    if v is None or (isinstance(v, float) and v != v):
        return 0
    if isinstance(v, str):
        v = v.strip().replace(" ", "").replace(".", "").replace(",", "")
        if not v or not re.fullmatch(r"-?\d+", v):
            return 0
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------- fonte A ----

def load_certo(year):
    """Lê `PT {ano} certo.xlsx` -> (results, names, parties, vencedor_qa)."""
    path = RESULTADOS_DIR / f"PT {year} certo.xlsx"
    df = pd.read_excel(path, dtype=str)
    cols = list(df.columns)
    low = [str(c).strip().lower() for c in cols]

    code_col = cols[0]
    try:
        soma_idx = low.index("soma")
    except ValueError:
        raise ValueError(f"{path.name}: sem coluna 'Soma'")
    # nome = primeira coluna que dê match em termos geográficos/nomes
    name_col = None
    for c in cols[1:soma_idx]:
        c_low = str(c).strip().lower()
        if any(k in c_low for k in ("denomina", "territor", "freguesia", "nome")):
            name_col = c
            break
    if not name_col:
        for c in cols[1:soma_idx]:
            if str(c).strip().lower() not in NON_PARTY_COLS:
                name_col = c
                break

    party_cols = [c for c in cols[1:soma_idx]
                  if c != name_col and str(c).strip().lower() not in NON_PARTY_COLS]

    venc_col = next((c for c in cols if str(c).strip().lower() == "vencedor"), None)

    results, names, vencedor_qa = {}, {}, {}

    # Crosswalk de ilhas: códigos antigos (19-22) -> DICOFRE moderno (31/32/41-49).
    island_cw = load_island_crosswalk(year) if year <= 2005 else {}

    def process_df(df_to_proc):
        cols_local = list(df_to_proc.columns)
        venc_col_local = next((c for c in cols_local if str(c).strip().lower() == "vencedor"), None)

        name_col_local = None
        for c in cols_local:
            c_low = str(c).strip().lower()
            if any(k in c_low for k in ("denomina", "territor", "freguesia", "nome")):
                name_col_local = c
                break
        if not name_col_local:
            name_col_local = name_col if name_col in cols_local else cols_local[1]

        for row in df_to_proc.itertuples(index=False):
            raw_code = str(row[0]).strip()
            if raw_code.endswith(".0"):
                raw_code = raw_code[:-2]
            code_raw = raw_code.zfill(6)
            if code_raw[:2] in OLD_ISLAND_PREFIXES:
                if code_raw in island_cw:
                    code = island_cw[code_raw]
                else:
                    if not code_raw.endswith("00"):
                        print(f"  AVISO: código de ilha não resolvido em load_certo ({year}): {code_raw} ({row[cols_local.index(name_col_local)] if name_col_local else ''})")
                    code = norm_dicofre(row[0])
            else:
                code = norm_dicofre(row[0])
            if not is_freguesia_code(code):
                continue
            votes = {}
            for i, c in enumerate(cols_local):
                c_clean = str(c).strip()
                if c_clean in party_cols:
                    v = to_int(row[i])
                    if v:
                        party_key = c_clean
                        if year == 2025 and c_clean == "AD" and code.startswith("4"):
                            party_key = "AD Açores"
                        votes[party_key] = v
            results[code] = votes
            names[code] = str(row[cols_local.index(name_col_local)]).strip() if name_col_local else ""
            if venc_col_local:
                vv = row[cols_local.index(venc_col_local)]
                if isinstance(vv, str) and vv.strip():
                    vencedor_qa[code] = vv.strip()

    process_df(df)

    # NOTA: o ficheiro principal `PT {ano} certo.xlsx` já contém todas as freguesias
    # das ilhas (com código antigo, remapeado acima). O antigo merge de
    # `ilhas {ano} freguesias.xlsx` era redundante e, nalguns anos (ex.: 2002, que só
    # traz a string do vencedor), sobrepunha os votos das ilhas com dicionários vazios.

    parties = [str(c).strip() for c in party_cols]
    if year == 2025 and "AD Açores" not in parties:
        parties.append("AD Açores")
    return results, names, parties, vencedor_qa


# ---------------------------------------------------------------- fonte B ----

def find_header_row(rows, max_scan=8):
    for i, r in enumerate(rows[:max_scan]):
        for cell in r[:3]:
            if isinstance(cell, str) and cell.strip().lower() in ("código", "codigo", "cod_stape"):
                return i
    return None


def parse_globais_sheet(df_raw, year):
    """Parser posicional das sheets modernas (Global/Distrito/Concelho/País).

    Estrutura: código | nome | ano | [totais...] | inscritos | votantes/votos |
    % | brancos | % | nulos | % | [mandatos] | depois grupos
    `PARTIDO [, %][, mandatos]` detetados posicionalmente.
    Devolve {code: {name, inscritos, votantes, brancos, nulos, mandatos,
                    votes:{}, mandatos_p:{}}}
    """
    rows = df_raw.values.tolist()
    h = find_header_row(rows)
    if h is None:
        raise ValueError("cabeçalho não encontrado")
    hdr = [str(c).strip() if c is not None else "" for c in rows[h]]
    low = [c.lower() for c in hdr]

    def idx_of(*names):
        for n in names:
            if n in low:
                return low.index(n)
        return None

    i_insc = idx_of("inscritos")
    i_vot = idx_of("votantes", "votos")
    i_bra = idx_of("brancos", "em_branco")
    i_nul = idx_of("nulos")
    i_pnul = idx_of("% nulos", "perc_nulos", "perc_nulo")
    if i_pnul is None:
        raise ValueError(f"'% nulos' não encontrado em {hdr[:16]}")

    # Localizar a coluna de total de mandatos em toda a folha
    i_mand_total = idx_of("total de mandatos", "total mandatos", "total_mandatos", "tot_mand", "tot_mands")
    if i_mand_total is None:
        for idx_col, name_col in enumerate(low):
            if name_col in ("mandatos", "tot_mand", "tot_mands"):
                if idx_col < i_pnul + 2:
                    i_mand_total = idx_col
                    break

    j = i_pnul + 1
    if i_mand_total is not None and j == i_mand_total:
        j += 1

    groups = []  # (party, i_votes, i_mand|None)
    while j < len(hdr):
        name = hdr[j]
        if not name or low[j] in ("% votos", "% votantes", "perc_vot", "mandatos", "mand", "tot_mand", "total de mandatos", "total mandatos", "mandatos total"):
            j += 1
            continue
        i_votes = j
        i_mand = None
        k = j + 1
        if k < len(hdr) and (low[k] in ("% votos", "% votantes", "perc_vot") or low[k].startswith("perc_") or low[k].startswith("%")):
            k += 1
        if k < len(hdr) and (low[k] in ("mandatos", "mand") or low[k].startswith("mand_") or low[k].startswith("mandatos_")):
            i_mand = k
            k += 1
        groups.append((name, i_votes, i_mand))
        j = k

    # Pré-scan da coluna de códigos
    pad_right = False
    for r in rows[h + 1:]:
        if r and r[0] is not None:
            s_code = str(r[0]).strip()
            if s_code.endswith(".0"):
                s_code = s_code[:-2]
            if len(s_code) == 5 and s_code.startswith("0") and s_code.isdigit():
                pad_right = True
                break

    out = {}
    for r in rows[h + 1:]:
        raw_code = r[0]
        if raw_code is None:
            continue
        if pad_right:
            s_code = str(raw_code).strip()
            if s_code.endswith(".0"):
                s_code = s_code[:-2]
            if len(s_code) == 5 and s_code.isdigit():
                raw_code = s_code + "0"
        code = norm_dicofre(raw_code)
        # aceita numéricos (agregados/concelhos/distritos) e alfanuméricos
        # (freguesias de Barcelos '0302FA'..'0302FH' na sheet Freguesia)
        if code is None or not re.fullmatch(r"\d{4}[0-9A-Z]{2}", code):
            continue  # rodapés "Fonte: ...", linhas vazias, etc.
        votes, mand_p = {}, {}
        for name, iv, im in groups:
            party = globais_party_to_certo(year, name, code)
            v = to_int(r[iv]) if iv < len(r) else 0
            if v:
                votes[party] = votes.get(party, 0) + v
            if im is not None and im < len(r):
                m = to_int(r[im])
                if m:
                    mand_p[party] = mand_p.get(party, 0) + m
        out[code] = {
            "name": str(r[1]).strip() if len(r) > 1 and r[1] is not None else "",
            "inscritos": to_int(r[i_insc]) if i_insc is not None else 0,
            "votantes": to_int(r[i_vot]) if i_vot is not None else 0,
            "brancos": to_int(r[i_bra]) if i_bra is not None else 0,
            "nulos": to_int(r[i_nul]) if i_nul is not None else 0,
            "mandatos": to_int(r[i_mand_total]) if i_mand_total is not None else None,
            "votes": votes, "mandatos_p": mand_p,
        }
    return out


def load_globais_modern(year):
    """Workbook moderno (2011+): devolve dict com national/global/distrito/concelho."""
    path = RAW_DIR / RAW_FILES[year]
    xls = pd.ExcelFile(path)
    sheets = {}
    for sn in xls.sheet_names:
        key = None
        lsn = sn.lower()
        if "global" in lsn:
            key = "global"
        elif "distrito" in lsn:
            key = "distrito"
        elif "concelho" in lsn:
            key = "concelho"
        elif "freguesia" in lsn:
            key = "freguesia"
        elif "país" in lsn or "pais" in lsn:
            key = "pais"
        if key:
            sheets[key] = parse_globais_sheet(pd.read_excel(xls, sn, header=None), year)

    dist = {}
    for code, entry in sheets.get("distrito", {}).items():
        if code == "500000":
            continue
        key = DISTRITO_CODE_TO_KEY.get(code)
        if key is None and code.endswith("0000") and 1 <= int(code[:2]) <= 18:
            key = code[:2]
        if key:
            if key in dist:
                accumulate_official(dist[key], entry)
            else:
                dist[key] = entry

    # Círculos Europa / Fora da Europa
    global_sheet = sheets.get("global", {})
    if year == 2011:
        if "810000" in global_sheet:
            if "E1" in dist:
                accumulate_official(dist["E1"], global_sheet["810000"])
            else:
                dist["E1"] = global_sheet["810000"]
        if "820000" in global_sheet:
            if "E2" in dist:
                accumulate_official(dist["E2"], global_sheet["820000"])
            else:
                dist["E2"] = global_sheet["820000"]
    elif year == 2015:
        for code, entry in global_sheet.items():
            name_norm = strip_accents_upper(entry.get("name", ""))
            if "EUROPA" in name_norm and "FORA" not in name_norm:
                if "E1" in dist:
                    accumulate_official(dist["E1"], entry)
                else:
                    dist["E1"] = entry
            elif "FORA" in name_norm and "EUROPA" in name_norm:
                if "E2" in dist:
                    accumulate_official(dist["E2"], entry)
                else:
                    dist["E2"] = entry

    # Fallback para folha País se ausente em dist
    pais_sheet = sheets.get("pais", {})
    if "E1" not in dist:
        if "800000" in pais_sheet:
            dist["E1"] = pais_sheet["800000"]
    if "E2" not in dist:
        if "900000" in pais_sheet:
            dist["E2"] = pais_sheet["900000"]

    conc = {}
    for code, entry in sheets.get("concelho", {}).items():
        if code.endswith("00") and not code.endswith("0000"):
            conc[code[:4]] = entry

    pais_data = {}
    for code, entry in sheets.get("pais", {}).items():
        if code not in ("600000", "800000", "900000"):
            circ_key = "E1" if code.startswith("8") else "E2"
            if circ_key not in pais_data:
                pais_data[circ_key] = {}
            pais_data[circ_key][entry["name"]] = {
                "votes": entry["votes"],
                "inscritos": entry["inscritos"],
                "votantes": entry["votantes"],
                "brancos": entry["brancos"],
                "nulos": entry["nulos"],
                "mandatos": entry["mandatos"]
            }

    g = sheets.get("global", {})
    return {
        "national": g.get("500000"),   # território nacional (mapeável)
        "global": g.get("990000"),     # inclui estrangeiro
        "estrangeiro": g.get("600000"),
        "distrito": dist,
        "concelho": conc,
        "freguesia": {c: e for c, e in sheets.get("freguesia", {}).items()
                      if is_freguesia_code(c)},
        "countries": pais_data
    }


def load_globais_era2(year):
    """Workbook intermédio (2002-2009): sheets separadas distrito/concelho/freguesia/país."""
    path = RAW_DIR / RAW_FILES[year]
    xls = pd.ExcelFile(path)

    sheet_dist = None
    sheet_conc = None
    sheet_freg = None
    sheet_pais = None

    for sn in xls.sheet_names:
        lsn = sn.lower()
        if "freguesia" in lsn or lsn.endswith("_f"):
            sheet_freg = sn
        elif "distrito" in lsn or lsn.endswith("_d") or "globais" in lsn:
            sheet_dist = sn
        elif "concelho" in lsn or lsn.endswith("_c"):
            sheet_conc = sn
        elif "país" in lsn or "pais" in lsn or lsn.endswith("_p"):
            sheet_pais = sn

    if not sheet_dist:
        raise ValueError(f"Não foi possível encontrar a sheet de distrito para o ano {year}")

    dist_raw = parse_globais_sheet(pd.read_excel(xls, sheet_dist, header=None), year)
    conc_raw = (parse_globais_sheet(pd.read_excel(xls, sheet_conc, header=None), year)
                if sheet_conc else {})
    freg_raw = (parse_globais_sheet(pd.read_excel(xls, sheet_freg, header=None), year)
                if sheet_freg else {})
    pais_raw = (parse_globais_sheet(pd.read_excel(xls, sheet_pais, header=None), year)
                if sheet_pais else {})

    dist = {}
    national = None
    global_entry = None
    estrangeiro = None

    for code, entry in dist_raw.items():
        if code in ("230000", "500000", "000050"):
            national = entry
            continue
        if code in ("990000", "000099"):
            global_entry = entry
            continue
        if year == 2009 and code == "800000":
            continue
        key = DISTRITO_CODE_TO_KEY.get(code)
        if key is None:
            if code.endswith("0000") and 1 <= int(code[:2]) <= 18:
                key = code[:2]
            elif code.startswith("0000") and 1 <= int(code[4:]) <= 18:
                key = f"{int(code[4:]):02d}"
        if key:
            if key in dist:
                accumulate_official(dist[key], entry)
            else:
                dist[key] = entry

    # Estrangeiro
    for code in ("600000", "006000"):
        if code in dist_raw:
            estrangeiro = dist_raw[code]
            break
        if code in pais_raw:
            estrangeiro = pais_raw[code]
            break

    # círculos Europa / Fora da Europa vêm da sheet País
    for code, key in (("800000", "E1"), ("900000", "E2")):
        if code in pais_raw:
            if year == 2009:
                if code == "800000":
                    estrangeiro = pais_raw[code]
            else:
                if key in dist:
                    accumulate_official(dist[key], pais_raw[code])
                else:
                    dist[key] = pais_raw[code]

    conc = {}
    for code, entry in conc_raw.items():
        if code.endswith("00") and not code.endswith("0000"):
            key = OLD_CONC_TO_MODERN.get(code[:4], code[:4])
            conc[key] = entry

    # freguesias: remapear códigos de ilha antigos (19-22) -> DICOFRE moderno
    island_cw = load_island_crosswalk(year) if year <= 2005 else {}
    freg = {}
    for code_raw, entry in freg_raw.items():
        if code_raw[:2] in OLD_ISLAND_PREFIXES:
            if code_raw in island_cw:
                code = island_cw[code_raw]
            else:
                if not code_raw.endswith("00"):
                    print(f"  AVISO: código de ilha não resolvido em load_globais_era2 ({year}): {code_raw} ({entry.get('name')})")
                code = code_raw
        else:
            code = code_raw
        if is_freguesia_code(code):
            freg[code] = entry

    pais_data = {}
    for code, entry in pais_raw.items():
        if code not in ("600000", "800000", "900000"):
            circ_key = "E1" if code.startswith("8") else "E2"
            if circ_key not in pais_data:
                pais_data[circ_key] = {}
            pais_data[circ_key][entry["name"]] = {
                "votes": entry["votes"],
                "inscritos": entry["inscritos"],
                "votantes": entry["votantes"],
                "brancos": entry["brancos"],
                "nulos": entry["nulos"],
                "mandatos": entry["mandatos"]
            }

    return {
        "national": national,
        "global": global_entry,
        "estrangeiro": estrangeiro,
        "distrito": dist,
        "concelho": conc,
        "freguesia": freg,
        "countries": pais_data
    }


def load_globais_era1(year):
    """Excel antigo (1975-1999): sheet única com coluna Div Admin."""
    path = RAW_DIR / RAW_FILES[year]
    xls = pd.ExcelFile(path)
    sheet_name = xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name, header=None)
    
    rows = df.values.tolist()
    hdr = [str(c).strip() if c is not None else "" for c in rows[0]]
    low = [c.lower() for c in hdr]
    
    i_code = low.index("código") if "código" in low else (low.index("codigo") if "codigo" in low else 0)
    i_div = low.index("div admin") if "div admin" in low else 1
    i_name = low.index("denominação") if "denominação" in low else (low.index("denominacao") if "denominacao" in low else 2)
    i_insc = low.index("inscritos") if "inscritos" in low else None
    i_vot = low.index("votantes") if "votantes" in low else None
    i_bra = low.index("brancos") if "brancos" in low else (low.index("em branco") if "em branco" in low else None)
    i_nul = low.index("nulos") if "nulos" in low else None
    i_mand_total = low.index("t mand") if "t mand" in low else (low.index("tot mand") if "tot mand" in low else None)
    
    groups = []
    for idx, col in enumerate(hdr):
        if col and str(col).strip().lower().startswith("sigla"):
            groups.append((idx, idx + 1, idx + 3))
            
    island_cw = load_island_crosswalk(year) if year <= 2005 else {}
    national = None
    distritos = {}
    concelhos = {}
    freguesias = {}
    
    for r in rows[1:]:
        raw_code = r[0]
        if raw_code is None:
            continue
        code = norm_dicofre(raw_code)
        if code is None:
            continue
        div = str(r[i_div]).strip().upper() if r[i_div] is not None else ""
        name = str(r[i_name]).strip() if r[i_name] is not None else ""
        
        votes = {}
        mand_p = {}
        # NOTA: variáveis do loop não podem sombrear os índices de cabeçalho
        # (i_vot/i_mand) — senão entry["votantes"] leria a coluna do último partido.
        for i_sig, i_pv, i_pm in groups:
            sigla = r[i_sig]
            if sigla and isinstance(sigla, str) and sigla.strip():
                party = globais_party_to_certo(year, sigla)
                v = to_int(r[i_pv])
                if v:
                    votes[party] = votes.get(party, 0) + v
                if i_pm < len(r):
                    m = to_int(r[i_pm])
                    if m:
                        mand_p[party] = mand_p.get(party, 0) + m
                        
        entry = {
            "name": name,
            "inscritos": to_int(r[i_insc]) if i_insc is not None else 0,
            "votantes": to_int(r[i_vot]) if i_vot is not None else 0,
            "brancos": to_int(r[i_bra]) if i_bra is not None else 0,
            "nulos": to_int(r[i_nul]) if i_nul is not None else 0,
            "mandatos": to_int(r[i_mand_total]) if i_mand_total is not None else None,
            "votes": votes,
            "mandatos_p": mand_p
        }
        
        if div == 'P':
            national = entry
        elif div in ('D', 'R'):
            # Mapear código de distrito ANTIGO -> círculo moderno. Açores tinha 3
            # distritos (19 Angra, 20 Horta, 21 P.Delgada) que agora formam um único
            # círculo '40' -> somar; Madeira (22/30) -> '30'.
            p2 = code[:2]
            dt = None
            if p2 in ("19", "20", "21", "40"):
                dt = "40"
            elif p2 in ("22", "30", "31", "32"):
                dt = "30"
            elif code == "800000":
                dt = "E1"
            elif code == "900000":
                dt = "E2"
            elif p2.isdigit() and 1 <= int(p2) <= 18:
                dt = p2
            if dt:
                if dt in distritos and dt in ("30", "40"):
                    accumulate_official(distritos[dt], entry)
                else:
                    distritos[dt] = entry
        elif div == 'C':
            key = OLD_CONC_TO_MODERN.get(code[:4], code[:4])
            concelhos[key] = entry
        elif div == 'F':
            code_raw = code
            if code_raw[:2] in OLD_ISLAND_PREFIXES:
                if code_raw in island_cw:
                    code = island_cw[code_raw]
                else:
                    if not code_raw.endswith("00"):
                        print(f"  AVISO: código de ilha não resolvido em load_globais_era1 ({year}): {code_raw} ({entry.get('name')})")
                    code = code_raw
            if is_freguesia_code(code):
                freguesias[code] = entry
            
    return {
        "national": national,
        "distrito": distritos,
        "concelho": concelhos,
        "freguesia": freguesias
    }


# ------------------------------------------------------------------ build ----

def accumulate_official(dst, src):
    """Soma no lugar os totais oficiais de src em dst (para agregar distritos antigos
    das ilhas num único círculo moderno)."""
    for k in ("inscritos", "votantes", "brancos", "nulos"):
        dst[k] = (dst.get(k) or 0) + (src.get(k) or 0)
    dm, sm = dst.get("mandatos"), src.get("mandatos")
    if dm is not None or sm is not None:
        dst["mandatos"] = (dm or 0) + (sm or 0)
    for key in ("votes", "mandatos_p"):
        d = dst.setdefault(key, {})
        for p, v in (src.get(key) or {}).items():
            d[p] = d.get(p, 0) + v
    return dst


def load_estrangeiro_workbook(year):
    """Lê AR{year}_VOT_RESID_ESTRANG.xls da pasta RAW_DIR e devolve {circ_key: {pt_name: {...}}}."""
    path = RAW_DIR / f"AR{year}_VOT_RESID_ESTRANG.xls"
    if not path.exists():
        return {}

    def clean_country_name(name):
        name = str(name).strip()
        name_clean = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn').upper()
        
        # E1
        if "ALEMANHA" in name_clean: return "Alemanha"
        if "BELGICA" in name_clean: return "Bélgica"
        if "ESPANHA" in name_clean: return "Espanha"
        if "FRANCA" in name_clean: return "França"
        if "PAISES BAIXOS" in name_clean: return "Países Baixos"
        if "LUXEMBURGO" in name_clean: return "Luxemburgo"
        if "REINO UNIDO" in name_clean: return "Reino Unido da Grã-bretanha e Irlanda do Norte"
        if "SUICA" in name_clean: return "Suíça"
        if "RESTANTES PAISES DA EUROPA" in name_clean: return "Restantes Países da Europa"
        
        # E2
        if "BRASIL" in name_clean: return "Brasil"
        if "CANADA" in name_clean: return "Canadá"
        if "ESTADOS UNIDOS" in name_clean: return "Estados Unidos da América"
        if "RESTANTES PAISES DA AMERICA" in name_clean: return "Restantes Países da América"
        if "CHINA" in name_clean: return "China"
        if "ASIA E OCEANIA" in name_clean: return "Restantes Países da Ásia e Oceânia"
        if "AFRICA" in name_clean: return "Países de África"
        return None

    xls = pd.ExcelFile(path)
    pais_data = {"E1": {}, "E2": {}}

    if year == 1995:
        # Era 1: Sheet única "Sheet1"
        df = pd.read_excel(xls, "Sheet1", header=None).fillna("")
        row0 = df.iloc[0].values
        party_cols = {}
        for c in range(12, len(row0), 4):
            if c < len(row0) and row0[c]:
                party_cols[c] = str(row0[c]).strip()

        for idx, row in df.iterrows():
            val4 = str(row[4]).strip()
            if not val4:
                continue
            pt_name = clean_country_name(val4)
            if not pt_name:
                continue
            circ_key = "E1" if row[0] == 1 else "E2"
            
            votes = {}
            for c, party_name in party_cols.items():
                party = globais_party_to_certo(year, party_name)
                v = to_int(row[c + 1])
                if v:
                    votes[party] = votes.get(party, 0) + v
                    
            pais_data[circ_key][pt_name] = {
                "votes": votes,
                "inscritos": to_int(row[5]),
                "votantes": to_int(row[6]),
                "brancos": to_int(row[8]),
                "nulos": to_int(row[10]),
                "mandatos": 0
            }
    else:
        # Era 2: 1999, 2002, 2005 (sheets separadas por continente)
        sheets_map = {"E1": [], "E2": []}
        for sn in xls.sheet_names:
            lsn = sn.lower()
            if lsn == "europa":
                sheets_map["E1"].append(sn)
            elif lsn not in ("total", "mesas europa", "mesas fora eur.", "mesas fora da europa", "mesas 1 a 18", "mesas 19 a 36", "cadernos", "candidatos", "obs.", "sheet1", "sheet2", "sheet3"):
                sheets_map["E2"].append(sn)

        for circ_key, sns in sheets_map.items():
            for sn in sns:
                df = pd.read_excel(xls, sn, header=None).fillna("")
                header_row_idx = None
                for idx, row in df.iterrows():
                    row_vals = [str(v).strip().lower() for v in row.values]
                    if "inscritos" in row_vals:
                        header_row_idx = idx
                        break
                if header_row_idx is None:
                    continue

                headers = [str(v).strip() for v in df.iloc[header_row_idx].values]

                for idx in range(header_row_idx + 1, len(df)):
                    row = df.iloc[idx].values
                    val0 = str(row[0]).strip()
                    if not val0 or val0.lower() in ("legislativas", "mesas", "total", "total geral") or "legislativas" in val0.lower():
                        continue
                    if isinstance(row[5], float) and row[5] < 1.0:
                        continue

                    pt_name = clean_country_name(val0)
                    if sn.lower() in ("frica", "frica") and val0.lower() == "total":
                        pt_name = "Países de África"
                    elif sn.lower() in ("sia e oc.", "sia e oc.") and val0.lower() == "total":
                        pt_name = "Restantes Países da Ásia e Oceânia"

                    if not pt_name:
                        continue

                    votes = {}
                    for c in range(8, len(row)):
                        if c < len(headers) and headers[c]:
                            party_name = headers[c]
                            if party_name.lower() in ("total", "nulos", "brancos", "em branco", "mesas", "inscritos", "votantes", ""):
                                continue
                            party = globais_party_to_certo(year, party_name)
                            v = to_int(row[c])
                            if v:
                                votes[party] = votes.get(party, 0) + v

                    pais_data[circ_key][pt_name] = {
                        "votes": votes,
                        "inscritos": to_int(row[4]),
                        "votantes": to_int(row[5]),
                        "brancos": to_int(row[6]),
                        "nulos": to_int(row[7]),
                        "mandatos": 0
                    }
    return pais_data


def sum_votes(entries):
    tot = defaultdict(int)
    for votes in entries:
        for p, v in votes.items():
            tot[p] += v
    return dict(tot)


def build_year(year):
    print(f"=== {year} ===")
    results, names, parties, vencedor_qa = load_certo(year)
    print(f"  certo: {len(results)} freguesias, {len(parties)} partidos: {parties}")

    official = None
    try:
        if year >= 2011:
            official = load_globais_modern(year)
        elif year >= 2002:
            official = load_globais_era2(year)
        else:
            official = load_globais_era1(year)
    except Exception as e:
        print(f"  AVISO: falha no Globais para o ano {year} ({e}) — a prosseguir sem camada oficial")

    if year in (1995, 1999, 2002, 2005):
        try:
            extra_countries = load_estrangeiro_workbook(year)
            if extra_countries:
                if not official:
                    official = {}
                if "countries" not in official or not official["countries"]:
                    official["countries"] = extra_countries
                else:
                    for circ, countries_dict in extra_countries.items():
                        official["countries"].setdefault(circ, {}).update(countries_dict)
                print(f"  -> Estrangeiro complementar carregado para {year}")
        except Exception as e:
            print(f"  AVISO: falha ao carregar estrangeiro complementar para {year} ({e})")

    if year == 2002:
        # Juntar B.E. e B.E.-UDP sob B.E.
        if "B.E.-UDP" in parties:
            parties.remove("B.E.-UDP")
        if "B.E." not in parties:
            parties.append("B.E.")

        def merge_be_2002(entry):
            if not entry: return
            votes = entry.get("votes")
            if votes:
                votes["B.E."] = votes.get("B.E.", 0) + votes.get("B.E.-UDP", 0)
                votes.pop("B.E.-UDP", None)
            m_p = entry.get("mandatos_p")
            if m_p:
                m_p["B.E."] = m_p.get("B.E.", 0) + m_p.get("B.E.-UDP", 0)
                m_p.pop("B.E.-UDP", None)

        for f_code in results:
            results[f_code]["B.E."] = results[f_code].get("B.E.", 0) + results[f_code].get("B.E.-UDP", 0)
            results[f_code].pop("B.E.-UDP", None)

        if official:
            merge_be_2002(official.get("national"))
            merge_be_2002(official.get("global"))
            merge_be_2002(official.get("estrangeiro"))
            if "distrito" in official:
                for d_code, entry in official["distrito"].items():
                    merge_be_2002(entry)
            if "concelho" in official:
                for c_code, entry in official["concelho"].items():
                    merge_be_2002(entry)
            if "freguesia" in official:
                for f_code, entry in official["freguesia"].items():
                    merge_be_2002(entry)
            if "countries" in official:
                for circ_key in official["countries"]:
                    for c_name in official["countries"][circ_key]:
                        merge_be_2002(official["countries"][circ_key][c_name])

    if year == 2015:
        # Renomear no parties
        if "PPD/PSD.CDS-PP" in parties:
            parties.remove("PPD/PSD.CDS-PP")
        if "PàF" not in parties:
            parties.append("PàF")

        # Função auxiliar para renomear chave de dicionário
        def rename_key(d, old_k, new_k):
            if d and old_k in d:
                d[new_k] = d.pop(old_k)

        # Renomear nas freguesias
        for f_code in results:
            rename_key(results[f_code], "PPD/PSD.CDS-PP", "PàF")

        if official:
            # Renomear no oficial nacional/global/estrangeiro
            for level in ("national", "global", "estrangeiro"):
                if level in official and official[level]:
                    rename_key(official[level].get("votes"), "PPD/PSD.CDS-PP", "PàF")
                    rename_key(official[level].get("mandatos_p"), "PPD/PSD.CDS-PP", "PàF")

            # Renomear nos distritos oficiais
            if "distrito" in official:
                for d_code, entry in official["distrito"].items():
                    rename_key(entry.get("votes"), "PPD/PSD.CDS-PP", "PàF")
                    rename_key(entry.get("mandatos_p"), "PPD/PSD.CDS-PP", "PàF")

            # Renomear nos concelhos oficiais
            if "concelho" in official:
                for c_code, entry in official["concelho"].items():
                    rename_key(entry.get("votes"), "PPD/PSD.CDS-PP", "PàF")
                    rename_key(entry.get("mandatos_p"), "PPD/PSD.CDS-PP", "PàF")

            # Renomear nas freguesias oficiais
            if "freguesia" in official:
                for f_code, entry in official["freguesia"].items():
                    rename_key(entry.get("votes"), "PPD/PSD.CDS-PP", "PàF")
                    rename_key(entry.get("mandatos_p"), "PPD/PSD.CDS-PP", "PàF")

            # Renomear nos países oficiais
            if "countries" in official:
                for circ_key in official["countries"]:
                    for c_name in official["countries"][circ_key]:
                        c_entry = official["countries"][circ_key][c_name]
                        rename_key(c_entry.get("votes"), "PPD/PSD.CDS-PP", "PàF")
                        rename_key(c_entry.get("mandatos_p"), "PPD/PSD.CDS-PP", "PàF")

            # Unificar os votos e mandatos partidários a nível nacional e global
            def unify_paf(entry):
                if not entry: return
                votes = entry.get("votes")
                if votes:
                    paf_v = votes.get("PàF", 0)
                    psd_v = votes.get("PPD/PSD", 0)
                    cds_v = votes.get("CDS-PP", 0)
                    votes["PàF"] = paf_v + psd_v + cds_v
                    votes.pop("PPD/PSD", None)
                    votes.pop("CDS-PP", None)
                m_p = entry.get("mandatos_p")
                if m_p:
                    paf_m = m_p.get("PàF", 0)
                    psd_m = m_p.get("PPD/PSD", 0)
                    cds_m = m_p.get("CDS-PP", 0)
                    m_p["PàF"] = paf_m + psd_m + cds_m
                    m_p.pop("PPD/PSD", None)
                    m_p.pop("CDS-PP", None)

            unify_paf(official.get("national"))
            unify_paf(official.get("global"))

    if year == 2024:
        # Unificar os votos e mandatos da coligação Madeira Primeiro e do PPM sob a AD a nível nacional e global
        def unify_ad_2024(entry):
            if not entry: return
            votes = entry.get("votes")
            if votes:
                ad_v = votes.get("AD", 0)
                mp_v = votes.get("Madeira Primeiro", 0)
                ppm_v = votes.get("PPM", 0)
                votes["AD"] = ad_v + mp_v + ppm_v
                votes.pop("Madeira Primeiro", None)
                votes.pop("PPM", None)
            m_p = entry.get("mandatos_p")
            if m_p:
                ad_m = m_p.get("AD", 0)
                mp_m = m_p.get("Madeira Primeiro", 0)
                ppm_m = m_p.get("PPM", 0)
                m_p["AD"] = ad_m + mp_m + ppm_m
                m_p.pop("Madeira Primeiro", None)
                m_p.pop("PPM", None)

        if official:
            unify_ad_2024(official.get("national"))
            unify_ad_2024(official.get("global"))

    if year == 2025:
        # Unificar os votos e mandatos da coligação AD Açores sob a AD a nível nacional e global
        def unify_ad_2025(entry):
            if not entry: return
            votes = entry.get("votes")
            if votes:
                ad_v = votes.get("AD", 0)
                ada_v = votes.get("AD Açores", 0)
                votes["AD"] = ad_v + ada_v
                votes.pop("AD Açores", None)
            m_p = entry.get("mandatos_p")
            if m_p:
                ad_m = m_p.get("AD", 0)
                ada_m = m_p.get("AD Açores", 0)
                m_p["AD"] = ad_m + ada_m
                m_p.pop("AD Açores", None)

        if official:
            unify_ad_2025(official.get("national"))
            unify_ad_2025(official.get("global"))

    if year in (1979, 1980):
        # PPD/PSD e CDS concorreram na AD no Continente mas sozinhos nas ilhas
        # (Açores/Madeira). A nível nacional, fundir esses solos das ilhas na AD
        # (mantendo os distritos/ilhas separados, tal como PàF em 2015).
        def unify_ad_islands(entry):
            if not entry: return
            votes = entry.get("votes")
            if votes:
                votes["AD"] = votes.get("AD", 0) + votes.get("PPD/PSD", 0) + votes.get("CDS", 0)
                votes.pop("PPD/PSD", None)
                votes.pop("CDS", None)
            m_p = entry.get("mandatos_p")
            if m_p:
                m_p["AD"] = m_p.get("AD", 0) + m_p.get("PPD/PSD", 0) + m_p.get("CDS", 0)
                m_p.pop("PPD/PSD", None)
                m_p.pop("CDS", None)

        if official:
            for lvl in ("national", "global"):
                unify_ad_islands(official.get(lvl))

    if year == 1980:
        # A FRS (só existiu em 1980) concorreu no Continente; o PS concorreu
        # sozinho nas ilhas. Fundir o PS das ilhas na FRS a nível nacional.
        def unify_frs_1980(entry):
            if not entry: return
            votes = entry.get("votes")
            if votes:
                votes["FRS"] = votes.get("FRS", 0) + votes.get("PS", 0)
                votes.pop("PS", None)
            m_p = entry.get("mandatos_p")
            if m_p:
                m_p["FRS"] = m_p.get("FRS", 0) + m_p.get("PS", 0)
                m_p.pop("PS", None)

        if official:
            for lvl in ("national", "global"):
                unify_frs_1980(official.get(lvl))

    # agregados a partir das freguesias (consistentes com o mapa)
    agg_conc = defaultdict(list)
    agg_dist = defaultdict(list)
    for code, votes in results.items():
        agg_conc[code[:4]].append(votes)
        circ = circulo_from_dicofre(code)
        if circ:
            agg_dist[circ].append(votes)

    concelho = {k: {"votes": sum_votes(v)} for k, v in agg_conc.items()}
    distrito = {k: {"votes": sum_votes(v)} for k, v in agg_dist.items()}
    national_votes = sum_votes(results.values())

    if year == 2015:
        paf_v = national_votes.get("PàF", 0)
        psd_v = national_votes.get("PPD/PSD", 0)
        cds_v = national_votes.get("CDS-PP", 0)
        national_votes["PàF"] = paf_v + psd_v + cds_v
        national_votes.pop("PPD/PSD", None)
        national_votes.pop("CDS-PP", None)

    if year == 2024:
        ad_v = national_votes.get("AD", 0)
        mp_v = national_votes.get("Madeira Primeiro", 0)
        ppm_v = national_votes.get("PPM", 0)
        national_votes["AD"] = ad_v + mp_v + ppm_v
        national_votes.pop("Madeira Primeiro", None)
        national_votes.pop("PPM", None)

    if year == 2025:
        ad_v = national_votes.get("AD", 0)
        ada_v = national_votes.get("AD Açores", 0)
        national_votes["AD"] = ad_v + ada_v
        national_votes.pop("AD Açores", None)

    if year in (1979, 1980):
        national_votes["AD"] = national_votes.get("AD", 0) + national_votes.get("PPD/PSD", 0) + national_votes.get("CDS", 0)
        national_votes.pop("PPD/PSD", None)
        national_votes.pop("CDS", None)

    if year == 1980:
        national_votes["FRS"] = national_votes.get("FRS", 0) + national_votes.get("PS", 0)
        national_votes.pop("PS", None)

    meta = {"year": year,
            "parties": {p: {"nome": p} for p in parties},
            "national": {"votes": national_votes}}

    if official:
        if official.get("national"):
            n = official["national"]
            meta["national"].update({
                "inscritos": n["inscritos"], "votantes": n["votantes"],
                "brancos": n["brancos"], "nulos": n["nulos"],
                "mandatos": n["mandatos"],
                "mandatos_p": n["mandatos_p"],
                "votes_oficial": n["votes"],
            })
        if official.get("global"):
            g = official["global"]
            meta["global"] = {
                "votes": g["votes"],
                "inscritos": g["inscritos"],
                "votantes": g["votantes"],
                "brancos": g["brancos"],
                "nulos": g["nulos"],
                "mandatos": g["mandatos"],
                "mandatos_p": g["mandatos_p"]
            }
        if official.get("estrangeiro"):
            meta["estrangeiro"] = {k: official["estrangeiro"][k] for k in
                                   ("inscritos", "votantes", "brancos", "nulos",
                                    "mandatos", "votes", "mandatos_p")}
        for key, entry in official.get("distrito", {}).items():
            d = distrito.setdefault(key, {"votes": entry["votes"] if key in ("E1", "E2") else {}})
            d.update({"nome_oficial": entry["name"],
                      "inscritos": entry["inscritos"], "votantes": entry["votantes"],
                      "brancos": entry["brancos"], "nulos": entry["nulos"],
                      "mandatos": entry["mandatos"], "mandatos_p": entry["mandatos_p"]})
            if key in ("E1", "E2"):
                d["votes"] = entry["votes"]
        for key, entry in official.get("concelho", {}).items():
            if key not in concelho:
                concelho[key] = {
                    "votes": dict(entry["votes"]),
                    "inscritos": entry["inscritos"],
                    "votantes": entry["votantes"],
                    "brancos": entry["brancos"],
                    "nulos": entry["nulos"]
                }
                print(f"  FALLBACK Concelho: {key} ({entry.get('name')}) inserido a partir de oficial (em falta na soma de freguesias)")
            else:
                # Verificar divergência nos votos
                sum_freg = sum(concelho[key]["votes"].values())
                sum_ofic = sum(entry["votes"].values())
                if sum_ofic > 0:
                    diff_pct = abs(sum_freg - sum_ofic) / sum_ofic
                    if diff_pct > 0.005:
                        concelho[key]["votes"] = dict(entry["votes"])
                        print(f"  FALLBACK Concelho: {key} ({entry.get('name')}) votos corrigidos via oficial (divergência de {diff_pct*100:.2f}%: freg={sum_freg}, oficial={sum_ofic})")
                
                # Atualizar dados oficiais do concelho
                concelho[key].update({
                    "inscritos": entry["inscritos"],
                    "votantes": entry["votantes"],
                    "brancos": entry["brancos"],
                    "nulos": entry["nulos"]
                })

    # Círculos da emigração (Europa/Fora da Europa 1976-1991) e círculos especiais de
    # 1975 (Macau/Moçambique/Emigração): não constam dos workbooks brutos, só nos
    # mapas oficiais do Diário da República — ver etl/ar_circulos_extra.py.
    for key, entry in MANUAL_CIRCLE_DATA.get(year, {}).items():
        distrito[key] = {
            "nome_oficial": entry["name"],
            "inscritos": entry["inscritos"], "votantes": entry["votantes"],
            "brancos": entry["brancos"], "nulos": entry["nulos"],
            "mandatos": entry["mandatos"], "mandatos_p": dict(entry["mandatos_p"]),
            "votes": dict(entry["votes"]),
        }
        for party in entry["votes"]:
            if party not in parties:
                parties.append(party)
                meta["parties"][party] = {"nome": party}
        for party, v in entry["votes"].items():
            national_votes[party] = national_votes.get(party, 0) + v
            meta["national"]["votes_oficial"][party] = meta["national"]["votes_oficial"].get(party, 0) + v
        for party, m in entry["mandatos_p"].items():
            meta["national"]["mandatos_p"][party] = meta["national"]["mandatos_p"].get(party, 0) + m
        meta["national"]["inscritos"] = meta["national"].get("inscritos", 0) + entry["inscritos"]
        meta["national"]["votantes"] = meta["national"].get("votantes", 0) + entry["votantes"]
        meta["national"]["brancos"] = meta["national"].get("brancos", 0) + entry["brancos"]
        meta["national"]["nulos"] = meta["national"].get("nulos", 0) + entry["nulos"]
    if MANUAL_CIRCLE_DATA.get(year):
        # O total nacional de mandatos (fonte P-row do Excel bruto) por vezes já
        # inclui os mandatos da emigração e por vezes não; nunca deixar o total
        # ficar abaixo da soma por partido depois de somarmos os círculos.
        soma_mandatos_p = sum(meta["national"]["mandatos_p"].values())
        if meta["national"]["mandatos"] < soma_mandatos_p:
            meta["national"]["mandatos"] = soma_mandatos_p

    if year >= 2009:
        # Re-calcular meta["national"] e meta["global"] com a soma dos círculos reais em distrito
        # para evitar as inconsistências das linhas totais dos workbooks Excel
        
        # 1. National (círculos domésticos: todos exceto E1 e E2)
        nat_mandatos = 0
        nat_mandatos_p = defaultdict(int)
        nat_votes_oficial = defaultdict(int)
        for c_key, c_entry in distrito.items():
            if c_key in ("E1", "E2"):
                continue
            nat_mandatos += c_entry.get("mandatos") or 0
            for p, m in c_entry.get("mandatos_p", {}).items():
                nat_mandatos_p[p] += m
            votes_dict = c_entry.get("votes", {})
            if not votes_dict and "votes_oficial" in c_entry:
                votes_dict = c_entry["votes_oficial"]
            for p, v in votes_dict.items():
                nat_votes_oficial[p] += v
                
        meta["national"]["mandatos"] = nat_mandatos
        meta["national"]["mandatos_p"] = dict(nat_mandatos_p)
        meta["national"]["votes_oficial"] = dict(nat_votes_oficial)
        
        # 2. Global (todos os círculos incluindo E1 e E2)
        if "global" in meta and meta["global"]:
            glob_mandatos = 0
            glob_mandatos_p = defaultdict(int)
            glob_votes = defaultdict(int)
            for c_key, c_entry in distrito.items():
                glob_mandatos += c_entry.get("mandatos") or 0
                for p, m in c_entry.get("mandatos_p", {}).items():
                    glob_mandatos_p[p] += m
                votes_dict = c_entry.get("votes", {})
                if not votes_dict and "votes_oficial" in c_entry:
                    votes_dict = c_entry["votes_oficial"]
                for p, v in votes_dict.items():
                    glob_votes[p] += v
                    
            meta["global"]["mandatos"] = glob_mandatos
            meta["global"]["mandatos_p"] = dict(glob_mandatos_p)
            meta["global"]["votes"] = dict(glob_votes)

        # Unificações
        if year == 2015:
            # National
            psd_m = meta["national"]["mandatos_p"].pop("PPD/PSD", 0)
            cds_m = meta["national"]["mandatos_p"].pop("CDS-PP", 0)
            meta["national"]["mandatos_p"]["PàF"] = meta["national"]["mandatos_p"].get("PàF", 0) + psd_m + cds_m
            psd_v = meta["national"]["votes_oficial"].pop("PPD/PSD", 0)
            cds_v = meta["national"]["votes_oficial"].pop("CDS-PP", 0)
            meta["national"]["votes_oficial"]["PàF"] = meta["national"]["votes_oficial"].get("PàF", 0) + psd_v + cds_v
            
            # Global
            if "global" in meta and meta["global"]:
                psd_m = meta["global"]["mandatos_p"].pop("PPD/PSD", 0)
                cds_m = meta["global"]["mandatos_p"].pop("CDS-PP", 0)
                meta["global"]["mandatos_p"]["PàF"] = meta["global"]["mandatos_p"].get("PàF", 0) + psd_m + cds_m
                psd_v = meta["global"]["votes"].pop("PPD/PSD", 0)
                cds_v = meta["global"]["votes"].pop("CDS-PP", 0)
                meta["global"]["votes"]["PàF"] = meta["global"]["votes"].get("PàF", 0) + psd_v + cds_v
                
        elif year == 2024:
            # National
            mp_m = meta["national"]["mandatos_p"].pop("Madeira Primeiro", 0)
            ppm_m = meta["national"]["mandatos_p"].pop("PPM", 0)
            meta["national"]["mandatos_p"]["AD"] = meta["national"]["mandatos_p"].get("AD", 0) + mp_m + ppm_m
            mp_v = meta["national"]["votes_oficial"].pop("Madeira Primeiro", 0)
            ppm_v = meta["national"]["votes_oficial"].pop("PPM", 0)
            meta["national"]["votes_oficial"]["AD"] = meta["national"]["votes_oficial"].get("AD", 0) + mp_v + ppm_v
            
            # Global
            if "global" in meta and meta["global"]:
                mp_m = meta["global"]["mandatos_p"].pop("Madeira Primeiro", 0)
                ppm_m = meta["global"]["mandatos_p"].pop("PPM", 0)
                meta["global"]["mandatos_p"]["AD"] = meta["global"]["mandatos_p"].get("AD", 0) + mp_m + ppm_m
                mp_v = meta["global"]["votes"].pop("Madeira Primeiro", 0)
                ppm_v = meta["global"]["votes"].pop("PPM", 0)
                meta["global"]["votes"]["AD"] = meta["global"]["votes"].get("AD", 0) + mp_v + ppm_v
                
        elif year == 2025:
            # National
            ada_m = meta["national"]["mandatos_p"].pop("AD Açores", 0)
            meta["national"]["mandatos_p"]["AD"] = meta["national"]["mandatos_p"].get("AD", 0) + ada_m
            ada_v = meta["national"]["votes_oficial"].pop("AD Açores", 0)
            meta["national"]["votes_oficial"]["AD"] = meta["national"]["votes_oficial"].get("AD", 0) + ada_v
            
            # Global
            if "global" in meta and meta["global"]:
                ada_m = meta["global"]["mandatos_p"].pop("AD Açores", 0)
                meta["global"]["mandatos_p"]["AD"] = meta["global"]["mandatos_p"].get("AD", 0) + ada_m
                ada_v = meta["global"]["votes"].pop("AD Açores", 0)
                meta["global"]["votes"]["AD"] = meta["global"]["votes"].get("AD", 0) + ada_v

    official_f = {}
    if official and official.get("freguesia"):
        for code, entry in official["freguesia"].items():
            official_f[code] = [
                entry["inscritos"],
                entry["votantes"],
                entry["brancos"],
                entry["nulos"]
            ]

    # QA inline oficial freguesias
    if official and official.get("freguesia"):
        common_f = set(results.keys()) & set(official["freguesia"].keys())
        cov_f_res = 100 * len(common_f) / len(results) if results else 0
        cov_f_of = 100 * len(common_f) / len(official["freguesia"]) if official["freguesia"] else 0
        print(f"  QA Freguesias Oficial: comum={len(common_f)} | cob: results->oficial {cov_f_res:.2f}% | oficial->results {cov_f_of:.2f}%")
        
        divergences = []
        for code in common_f:
            of_votes = official["freguesia"][code].get("votes", {})
            if of_votes:
                certo_votes = results[code]
                sum_of = sum(of_votes.values())
                sum_ce = sum(certo_votes.values())
                if sum_of != sum_ce:
                    divergences.append((code, sum_of, sum_ce, abs(sum_of - sum_ce)))
        if divergences:
            divergences.sort(key=lambda x: x[3], reverse=True)
            print(f"  AVISO: {len(divergences)} freguesias com divergência de votos oficial vs certo. Top-5:")
            for code, s_of, s_ce, diff in divergences[:5]:
                print(f"    - {code}: oficial={s_of}, certo={s_ce} (diff {diff})")

    countries = official.get("countries") if (official and "countries" in official) else {}
    payload = {"METADATA": meta,
               "NAMES": names,
               "RESULTS": results,
               "OFFICIAL_F": official_f,
               "AGG": {"concelho": concelho, "distrito": distrito},
               "COUNTRIES": countries,
               "QA_VENCEDOR": vencedor_qa}

    out = OUT_DIR / "resultados" / f"ar_{year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {out.name}: {out.stat().st_size/1e6:.2f} MB")

    # QA rápido inline
    if official and official.get("national"):
        soma_map = sum(national_votes.values())
        soma_of = sum(official["national"]["votes"].values())
        diff = soma_map - soma_of
        print(f"  QA: soma freguesias={soma_map:,} vs oficial nacional={soma_of:,} (diff {diff:+,})")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    years = YEARS if "--all" in args else [int(a) for a in args if a.isdigit()]
    # Apenas processar anos que tenham o ficheiro de resultados "certo" correspondente
    years = [y for y in years if (RESULTADOS_DIR / f"PT {y} certo.xlsx").exists()]
    if not years:
        print(__doc__)
        sys.exit(1)
    for y in years:
        build_year(y)
