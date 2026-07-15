# -*- coding: utf-8 -*-
"""Eleitos das Autárquicas 2005 a partir dos mapas oficiais do DR (PDF)."""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "etl"))

from common import CIRCULOS, circulo_from_dicofre, norm_dicofre
from eleitos_common import (DR_DIR, canonicalize_siglas, compute_presidente,
                            load_results, nfc, norm_name_if_caps,
                            rebuild_index, resolve_leftover_siglas,
                            write_eleitos_json)
from eleitos_overrides import apply_overrides, apply_sigla_aliases

PDF_PATH = DR_DIR / "autarquicas" / "resultados_al_2005.pdf"

# Regex for cleaning up page headers/footers
RE_HEADER_FOOTER = re.compile(
    r"^(diário da república|n\..*de.*de 200|910-\(\d+\)|suplemento|s\s*u\s*m\s*á\s*r\s*i\s*o|comissão nacional|mapa oficial|série-b|i\s*-\s*b\s*s\s*é\s*r\s*i\s*e|segunda-feira|terça-feira|quarta-feira|quinta-feira|sexta-feira|sábado|domingo).*$",
    re.IGNORECASE
)

def clean_matching_name(s):
    if not s:
        return ""
    s = s.strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r'\b(SAO|S\.)(\s|$)', r'S\2', s)
    s = re.sub(r'\b(STA\.?)(\s|$)', r'SANTA\2', s)
    s = re.sub(r'\b(STO\.?)(\s|$)', r'SANTO\2', s)
    s = re.sub(r'\b(DE|DO|DA|DOS|DAS|E)\b', '', s)
    s = re.sub(r'[^A-Z0-9\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def reconstruct_column_lines(words):
    words_sorted = sorted(words, key=lambda w: w[1])
    lines = []
    for w in words_sorted:
        x0, y0, x1, y1, text = w[:5]
        added = False
        for line in lines:
            line_y = sum((word[1] + word[3])/2 for word in line) / len(line)
            word_y = (y0 + y1)/2
            if abs(line_y - word_y) < 3.5:
                line.append(w)
                added = True
                break
        if not added:
            lines.append([w])
            
    line_strings = []
    for line in sorted(lines, key=lambda l: sum((w[1]+w[3])/2 for w in l)/len(l)):
        line_sorted = sorted(line, key=lambda w: w[0])
        line_str = " ".join(w[4] for w in line_sorted).strip()
        if line_str:
            line_strings.append(line_str)
    return line_strings

def parse_year_2005():
    doc = fitz.open(PDF_PATH)
    
    # Load results to map names and validate
    res = {s: load_results(f"au_{s}", 2005) for s in ("cm", "am", "af")}
    
    # Load 2021 concelhos map to map names to codes
    with open(PROJECT_ROOT / "dados/eleitos/au_cm_2021.json", encoding="utf-8") as f:
        eleitos_2021 = json.load(f)
    concelho_map = {}
    concelho_names = {}
    for code, o in eleitos_2021["orgaos"].items():
        name_clean = clean_matching_name(o["nome"])
        concelho_map[name_clean] = code
        concelho_names[code] = o["nome"]
        
        # Disambiguation fallbacks (nomes 2021: "Lagoa (R.A.A)", "Calheta (R.A.M.)")
        up = o["nome"].upper().replace(".", "")
        if "CALHETA" in name_clean:
            if "RAM" in up or "MADEIRA" in up:
                concelho_map["CALHETA MADEIRA"] = code
            else:
                concelho_map["CALHETA ACORES"] = code
        elif "LAGOA" in name_clean:
            if "RAA" in up or "ACORES" in up or "AÇORES" in up:
                concelho_map["LAGOA ACORES"] = code
            else:
                concelho_map["LAGOA FARO"] = code
                
    # Add manual fallbacks
    concelho_map["MARCO CANAVEZES"] = "1307"
    concelho_map["PRAIA VITORIA"] = "4302"
    concelho_map["VILA PORTO"] = "4101"
    concelho_map[clean_matching_name("Ponte de Lima")] = "1607"
    concelho_map[clean_matching_name("Vila do Porto")] = "4101"
    
    # Build freguesia name -> dico code map per concelho
    freg_map_by_concelho = defaultdict(dict)
    
    # Let's parse PDF text sequentially
    concelhos_parsed = {}
    current_concelho = None
    current_organ = None
    current_freguesia = None
    current_distrito = None
    current_name = []
    
    BLACKLIST_SUBSTRINGS = [
        "votantes", "inferior", "soma", "votos", "validamente", "deposito legal",
        "correio electronico", "dre @ incm", "preco deste", "departamento comercial",
        "publicacoes oficiais", "casa da moeda", "telef", "fax", "numero de mandatos",
        "distrito:", "regiao autonoma", "suplemento", "diario da republica", "linha azul",
        # notas da secção de resultados e colofão final
        "ver em eleitos", "sequencia incorrecta", "atrib.de manda", "sem influencia",
        "por ordem superior", "prazos para reclama", "selo branco", "originais destina",
        "ordem de publicacao", "endereco internet", "issn ",
    ]
    # legenda dos GCE na secção ELEITOS, ex.: "XII - Grupo Independente ... - GIEM"
    RE_GCE_LEGEND = re.compile(r"^[IVX]+\s*-\s")
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        words = page.get_text("words")
        
        # Identify blocks to skip
        skipped_rects = []
        for b in page.get_text("blocks"):
            bx0, by0, bx1, by1, btext, bno, btype = b
            if "INSCRITOS" in btext or "VOTANTES" in btext or "NÚMERO DE MANDATOS" in btext:
                skipped_rects.append(fitz.Rect(bx0, by0, bx1, by1))
                
        # Filter words
        valid_words = []
        for w in words:
            wx0, wy0, wx1, wy1, wtext = w[:5]
            w_mid_y = (wy0 + wy1)/2
            if not (65 <= w_mid_y <= 800):
                continue
            w_rect = fitz.Rect(wx0, wy0, wx1, wy1)
            in_skipped = False
            for r in skipped_rects:
                if r.contains(w_rect) or r.intersects(w_rect):
                    in_skipped = True
                    break
            if not in_skipped:
                valid_words.append(w)
        
        # Quando a página muda de secção a meio (eleitos em cima, resultados
        # do distrito seguinte em baixo), a ordem de leitura é por BANDA
        # horizontal: [topo L, topo R], [baixo L, baixo R]. Os "DISTRITO:"
        # marcam o início de cada nova banda.
        cut_ys = sorted((w[1] + w[3]) / 2 - 2 for w in valid_words
                        if w[4].upper().startswith("DISTRITO"))
        bands = []
        prev_y = -1e9
        for cy in cut_ys + [1e9]:
            band = [w for w in valid_words if prev_y <= (w[1]+w[3])/2 < cy]
            if band:
                bands.append(band)
            prev_y = cy

        lines = []
        for band in bands:
            words_left = [w for w in band if (w[0]+w[2])/2 < 295]
            words_right = [w for w in band if (w[0]+w[2])/2 >= 295]
            lines += reconstruct_column_lines(words_left)
            lines += reconstruct_column_lines(words_right)
        
        for line_str in lines:
            # Track district header (os arquipélagos usam "REGIÃO AUTÓNOMA ...")
            _up = line_str.upper()
            if _up.startswith("DISTRITO:") or _up.startswith("REGIÃO AUTÓNOMA") \
                    or _up.startswith("REGIAO AUTONOMA"):
                dist_clean = clean_matching_name(_up.split(":", 1)[-1])
                if "ACORES" in dist_clean:
                    current_distrito = "ACORES"
                elif "MADEIRA" in dist_clean:
                    current_distrito = "MADEIRA"
                elif "FARO" in dist_clean:
                    current_distrito = "FARO"
                else:
                    current_distrito = dist_clean
                continue
                
            # Filter out blacklist
            line_norm = "".join(c for c in unicodedata.normalize("NFD", line_str) if unicodedata.category(c) != "Mn").lower()
            if any(sub in line_norm for sub in BLACKLIST_SUBSTRINGS):
                continue
            # linhas com dígitos são da secção de resultados (nomes nunca têm);
            # legenda dos GCE e linhas longas (colofão) também não são eleitos
            if not line_str.startswith(("CONCELHO:", "Assembleia de Freguesia :")):
                if re.search(r"\d", line_str) or RE_GCE_LEGEND.match(line_str):
                    continue
                if len(line_str) > 70 and " " in line_str and line_str[0].islower():
                    continue
                
            # Detect Concelho header
            if line_str.startswith("CONCELHO:"):
                raw_conc_name = line_str.replace("CONCELHO:", "").strip().upper()
                conc_clean = clean_matching_name(raw_conc_name)
                # Disambiguate Calheta and Lagoa
                if conc_clean in ("CALHETA", "LAGOA") and current_distrito:
                    current_concelho = f"{conc_clean} {current_distrito}"
                else:
                    current_concelho = conc_clean
                    
                if current_concelho not in concelhos_parsed:
                    concelhos_parsed[current_concelho] = {
                        "CM": [],
                        "AM": [],
                        "AF": defaultdict(list)
                    }
                current_organ = None
                current_freguesia = None
                current_name = []
                continue
                
            if current_concelho is None:
                continue
                
            # Detect Organ headers
            if line_str == "CÂMARA MUNICIPAL":
                current_organ = "CM"
                current_freguesia = None
                current_name = []
                continue
            elif line_str == "ASSEMBLEIA MUNICIPAL":
                current_organ = "AM"
                current_freguesia = None
                current_name = []
                continue
            elif line_str.startswith("Assembleia de Freguesia :"):
                freg_name = line_str.replace("Assembleia de Freguesia :", "").strip()
                current_organ = "AF"
                current_freguesia = freg_name
                current_name = []
                continue
            elif line_str == "PLENÁRIO DE CIDADÃOS":
                current_organ = None
                current_freguesia = None
                current_name = []
                continue
                
            if current_organ is not None:
                # Smart name-sigla splitter regex
                m = re.search(r"^(.*?)\s+([A-Z0-9/\\\.\-\+]{1,})$", line_str)
                if m:
                    name_part = m.group(1).rstrip('xX').strip()
                    name_part = re.sub(r"\s*\(IND\.?\)\s*$", "", name_part, flags=re.IGNORECASE).strip()
                    sigla_part = m.group(2).strip()
                    
                    if not any(c.islower() for c in name_part):
                        # Not actually a name (just a sigla)
                        pass
                    else:
                        if current_name:
                            name_part = " ".join(current_name) + " " + name_part
                            current_name = []
                        pair = {"nome": name_part, "sigla": sigla_part}
                        if current_organ == "CM":
                            concelhos_parsed[current_concelho]["CM"].append(pair)
                        elif current_organ == "AM":
                            concelhos_parsed[current_concelho]["AM"].append(pair)
                        elif current_organ == "AF":
                            concelhos_parsed[current_concelho]["AF"][current_freguesia].append(pair)
                        continue
                        
                has_lowercase = any(c.islower() for c in line_str)
                if has_lowercase:
                    # It's a name!
                    name_clean = line_str.rstrip('xX').strip()
                    name_clean = re.sub(r"\s*\(IND\.?\)\s*$", "", name_clean, flags=re.IGNORECASE).strip()
                    current_name.append(name_clean)
                else:
                    # It's a sigla!
                    sigla_clean = line_str.strip()
                    if current_name:
                        pair = {"nome": " ".join(current_name), "sigla": sigla_clean}
                        if current_organ == "CM":
                            concelhos_parsed[current_concelho]["CM"].append(pair)
                        elif current_organ == "AM":
                            concelhos_parsed[current_concelho]["AM"].append(pair)
                        elif current_organ == "AF":
                            concelhos_parsed[current_concelho]["AF"][current_freguesia].append(pair)
                        current_name = []
                    else:
                        # Continuation of previous sigla
                        last_list = None
                        if current_organ == "CM" and concelhos_parsed[current_concelho]["CM"]:
                            last_list = concelhos_parsed[current_concelho]["CM"]
                        elif current_organ == "AM" and concelhos_parsed[current_concelho]["AM"]:
                            last_list = concelhos_parsed[current_concelho]["AM"]
                        elif current_organ == "AF" and concelhos_parsed[current_concelho]["AF"][current_freguesia]:
                            last_list = concelhos_parsed[current_concelho]["AF"][current_freguesia]
                        if last_list:
                            last_list[-1]["sigla"] += sigla_clean
                        
    # Now group and structure them for JSON files
    out_cm = {}
    out_am = {}
    out_af = defaultdict(dict)
    
    # Mapear freguesias com os NAMES dos próprios resultados de 2005
    # (nomes da época, pré-agregações de 2013)
    freg_name_to_code = {}
    freg_by_concelho = defaultdict(list)
    for code, nome in res["af"].get("NAMES", {}).items():
        fc = clean_matching_name(nome)
        freg_name_to_code[(code[:4], fc)] = code
        freg_by_concelho[code[:4]].append((fc, code))

    def match_freguesia(code4, freg_clean):
        """Match exato; senão 'Concelho (Freguesia)' das sedes homónimas,
        ex.: o PDF imprime 'Salvador' e os NAMES têm 'Beja (Salvador)'."""
        hit = freg_name_to_code.get((code4, freg_clean))
        if hit:
            return hit
        cands = [c for fc, c in freg_by_concelho.get(code4, [])
                 if fc.endswith(" " + freg_clean) or fc == freg_clean]
        if len(cands) == 1:
            return cands[0]
        # último recurso: contido (único)
        cands = [c for fc, c in freg_by_concelho.get(code4, []) if freg_clean in fc]
        return cands[0] if len(cands) == 1 else None
        
    warn = []
    
    for conc_name, data in concelhos_parsed.items():
        conc_clean = clean_matching_name(conc_name)
        code = concelho_map.get(conc_clean)
        if not code:
            warn.append(f"Concelho {conc_name} not mapped to code")
            continue
            
        # 1. Câmara Municipal (CM)
        if data["CM"]:
            # Group by sigla
            listas_by_sigla = defaultdict(list)
            for item in data["CM"]:
                listas_by_sigla[item["sigla"]].append(item["nome"])
            listas = [{"sigla": s, "eleitos": names} for s, names in listas_by_sigla.items()]
            listas = apply_sigla_aliases(2005, listas)
            agg = res["cm"].get("AGG", {}).get("concelho", {}).get(code, {})
            local = set(agg.get("votes") or {}) | set(agg.get("mandatos_p") or {})
            listas = canonicalize_siglas(listas, local)
            listas = resolve_leftover_siglas(listas, agg.get("mandatos_p"))
            listas = apply_overrides(2005, "cm", code, listas)
            entry = {"nome": concelho_names[code], "listas": listas}
            p = compute_presidente(listas, agg.get("votes"))
            if p:
                entry["presidente"] = p
            out_cm[code] = entry
            
        # 2. Assembleia Municipal (AM)
        if data["AM"]:
            listas_by_sigla = defaultdict(list)
            for item in data["AM"]:
                listas_by_sigla[item["sigla"]].append(item["nome"])
            listas = [{"sigla": s, "eleitos": names} for s, names in listas_by_sigla.items()]
            listas = apply_sigla_aliases(2005, listas)
            agg = res["am"].get("AGG", {}).get("concelho", {}).get(code, {})
            local = set(agg.get("votes") or {}) | set(agg.get("mandatos_p") or {})
            listas = canonicalize_siglas(listas, local)
            listas = resolve_leftover_siglas(listas, agg.get("mandatos_p"))
            listas = apply_overrides(2005, "am", code, listas)
            entry = {"nome": concelho_names[code], "listas": listas}
            out_am[code] = entry
            
        # 3. Assembleia de Freguesia (AF)
        for freg_name, items in data["AF"].items():
            freg_clean = clean_matching_name(freg_name)
            freg_code = match_freguesia(code, freg_clean)
            if not freg_code:
                # Try prefix search or fuzzy match if possible, or fallback to key search in res["af"]["RESULTS"]
                # Let's find all keys in res["af"]["RESULTS"].keys() starting with this concelho code
                freg_candidates = [k for k in res["af"]["RESULTS"].keys() if k.startswith(code)]
                if len(freg_candidates) == 1:
                    freg_code = freg_candidates[0]
                else:
                    # Try matching by suffix name if we can match clean names in results
                    # (Wait, our results af doesn't have names, but we can log)
                    warn.append(f"Freguesia {conc_name} / {freg_name} not mapped to code")
                    continue
                    
            listas_by_sigla = defaultdict(list)
            for item in items:
                listas_by_sigla[item["sigla"]].append(item["nome"])
            listas = [{"sigla": s, "eleitos": names} for s, names in listas_by_sigla.items()]
            listas = apply_sigla_aliases(2005, listas)
            votes = res["af"]["RESULTS"].get(freg_code, {})
            listas = canonicalize_siglas(listas, set(votes or {}))
            
            # AF: Resolve leftover siglas
            claimed = {l["sigla"] for l in listas}
            leftover_votes = [k for k in (votes or {}) if k not in claimed]
            leftover_listas = [l for l in listas if l["sigla"] not in (votes or {})]
            if len(leftover_votes) == 1 and len(leftover_listas) == 1:
                leftover_listas[0].setdefault("sigla_dr", leftover_listas[0]["sigla"])
                leftover_listas[0]["sigla"] = leftover_votes[0]
                
            listas = apply_overrides(2005, "af", freg_code, listas)
            entry = {"nome": freg_name, "listas": listas}
            p = compute_presidente(listas, votes)
            if p:
                entry["presidente"] = p
                
            dd = circulo_from_dicofre(freg_code) or freg_code[:2]
            out_af[dd][freg_code] = entry
            
    # Save output JSON
    write_eleitos_json("au_cm_2005.json", {
        "year": 2005, "election": "au", "subtype": "cm", "orgaos": out_cm
    })
    print(f"au_cm_2005: {len(out_cm)} concelhos")
    
    write_eleitos_json("au_am_2005.json", {
        "year": 2005, "election": "au", "subtype": "am", "orgaos": out_am
    })
    print(f"au_am_2005: {len(out_am)} concelhos")
    
    total_f = 0
    for dd, orgaos in sorted(out_af.items()):
        write_eleitos_json(f"au_af_2005_{dd}.json", {
            "year": 2005, "election": "au", "subtype": "af", "distrito": dd, "orgaos": orgaos
        })
        total_f += len(orgaos)
    print(f"au_af_2005: {total_f} freguesias em {len(out_af)} distritos")
    
    for w in warn[:30]:
        print(f"  aviso: {w}")
    if len(warn) > 30:
        print(f"  ... +{len(warn) - 30} avisos")

if __name__ == "__main__":
    parse_year_2005()
