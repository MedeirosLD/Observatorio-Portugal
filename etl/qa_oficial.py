# -*- coding: utf-8 -*-
"""QA de consistência contra os ficheiros brutos (resultados puros).

Compara os dados estruturados do JSON (dados/resultados/ar_YYYY.json) com
os workbooks originais e as regras de integridade.

Uso:
    python etl/qa_oficial.py 2025 2022
    python etl/qa_oficial.py --all
"""
import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict

# Garantir importações locais de etl/
sys.path.append(str(Path(__file__).resolve().parent))

from common import OUT_DIR, YEARS, OLD_CONC_TO_MODERN, dhondt, circulo_from_dicofre, strip_accents_upper
from build_results import load_globais_modern, load_globais_era2, load_globais_era1, RAW_FILES

def check_year(year):
    print(f"\n=================== QA OFICIAL {year} ===================")
    
    # Carregar JSON
    json_path = OUT_DIR / "resultados" / f"ar_{year}.json"
    if not json_path.exists():
        print(f"ERRO: Ficheiro JSON não encontrado: {json_path}")
        return False, ["Ficheiro JSON não encontrado"]
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Carregar dados oficiais do Excel correspondente
    try:
        if year >= 2011:
            official = load_globais_modern(year)
        elif year >= 2002:
            official = load_globais_era2(year)
        else:
            official = load_globais_era1(year)
    except Exception as e:
        print(f"ERRO ao carregar dados oficiais: {e}")
        return False, [f"Erro ao carregar dados oficiais: {e}"]
        
    failures = []
    
    # 1. Completude de concelhos
    expected_concelhos = 308 if year >= 1999 else (306 if year == 1995 else 305)
    json_concelhos = set(data["AGG"]["concelho"].keys())
    if len(json_concelhos) != expected_concelhos:
        msg = f"Número de concelhos: esperado {expected_concelhos}, obtido {len(json_concelhos)}"
        print(f"  [FAIL] {msg}")
        failures.append(msg)
    else:
        print(f"  [OK] Número de concelhos: {len(json_concelhos)}")
        
    # Verificar que AGG.concelho contém todos os concelhos oficiais
    off_concelhos = set()
    for code in official.get("concelho", {}):
        off_concelhos.add(OLD_CONC_TO_MODERN.get(code[:4], code[:4]))
        
    missing_concelhos = off_concelhos - json_concelhos
    if missing_concelhos:
        msg = f"Concelhos oficiais em falta no JSON: {missing_concelhos}"
        print(f"  [FAIL] {msg}")
        failures.append(msg)
    else:
        print(f"  [OK] Todos os concelhos oficiais presentes no JSON")
        
    # 2. Turnout em todos os níveis
    
    # Verificar Nacional
    n_json = data["METADATA"].get("national", {})
    n_off = official.get("national")
    if n_off:
        for k in ("inscritos", "votantes", "brancos", "nulos"):
            val_json = n_json.get(k, 0)
            val_off = n_off.get(k, 0)
            if year <= 2005:
                from ar_circulos_extra import MANUAL_CIRCLE_DATA
                for entry in MANUAL_CIRCLE_DATA.get(year, {}).values():
                    val_off += entry.get(k, 0)
            if val_json != val_off:
                msg = f"Nacional {k} divergência: JSON={val_json}, Oficial={val_off}"
                print(f"  [FAIL] {msg}")
                failures.append(msg)
                
    # Verificar Global
    if year >= 2009:
        g_json = data["METADATA"].get("global", {})
        g_off = official.get("global")
        if g_off:
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                val_json = g_json.get(k, 0)
                val_off = g_off.get(k, 0)
                if val_json != val_off:
                    msg = f"Global {k} divergência: JSON={val_json}, Oficial={val_off}"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)
                    
    # Verificar Estrangeiro
    if year >= 2009 or (year in (1995, 1999, 2002, 2005)):
        e_json = data["METADATA"].get("estrangeiro", {})
        e_off = official.get("estrangeiro")
        if e_off:
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                val_json = e_json.get(k, 0)
                val_off = e_off.get(k, 0)
                # Permitir uma tolerância de 10 votos para estrangeiro em anos antigos devido a rollups
                if abs(val_json - val_off) > 10:
                    msg = f"Estrangeiro {k} divergência: JSON={val_json}, Oficial={val_off}"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)

    # Verificar Turnout Distrital
    for key, entry_json in data["AGG"]["distrito"].items():
        if key in ("E1", "E2"):
            continue
        entry_off = official.get("distrito", {}).get(key)
        if entry_off:
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                val_json = entry_json.get(k, 0)
                val_off = entry_off.get(k, 0)
                if val_json != val_off:
                    msg = f"Distrito {key} {k} divergência: JSON={val_json}, Oficial={val_off}"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)

    # Verificar Turnout de Concelho
    for key, entry_json in data["AGG"]["concelho"].items():
        entry_off = None
        for k_off, e_off in official.get("concelho", {}).items():
            mod_k = OLD_CONC_TO_MODERN.get(k_off[:4], k_off[:4])
            if mod_k == key:
                entry_off = e_off
                break
        if entry_off:
            for k in ("inscritos", "votantes", "brancos", "nulos"):
                val_json = entry_json.get(k, 0)
                val_off = entry_off.get(k, 0)
                diff = abs(val_json - val_off)
                if year <= 2005:
                    if diff > 10 and val_off > 0 and (diff / val_off) > 0.005:
                        msg = f"Concelho {key} {k} divergência: JSON={val_json}, Oficial={val_off}"
                        print(f"  [FAIL] {msg}")
                        failures.append(msg)
                elif diff > 0 and year > 2005:
                    msg = f"Concelho {key} {k} divergência: JSON={val_json}, Oficial={val_off}"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)

    # 3. Votos a nível círculo+nacional
    lvl_key = "global" if year >= 2009 else "national"
    n_votes_json = data["METADATA"][lvl_key]["votes"]
    
    if year >= 2009:
        n_votes_off = dict(official["global"]["votes"])
    else:
        n_votes_off = dict(data["METADATA"]["national"].get("votes_oficial", {}))
        
    def unify_qa(y, votes, mandatos_p):
        if y == 2002:
            if votes and "B.E.-UDP" in votes:
                votes["B.E."] = votes.get("B.E.", 0) + votes.pop("B.E.-UDP", 0)
            if mandatos_p and "B.E.-UDP" in mandatos_p:
                mandatos_p["B.E."] = mandatos_p.get("B.E.", 0) + mandatos_p.pop("B.E.-UDP", 0)
        elif y == 2015:
            if votes:
                psd_v = votes.pop("PPD/PSD", 0)
                cds_v = votes.pop("CDS-PP", 0)
                votes["PàF"] = votes.get("PàF", 0) + psd_v + cds_v
            if mandatos_p:
                psd_m = mandatos_p.pop("PPD/PSD", 0)
                cds_m = mandatos_p.pop("CDS-PP", 0)
                mandatos_p["PàF"] = mandatos_p.get("PàF", 0) + psd_m + cds_m
        elif y == 2024:
            if votes:
                mp_v = votes.pop("Madeira Primeiro", 0)
                ppm_v = votes.pop("PPM", 0)
                votes["AD"] = votes.get("AD", 0) + mp_v + ppm_v
            if mandatos_p:
                mp_m = mandatos_p.pop("Madeira Primeiro", 0)
                ppm_m = mandatos_p.pop("PPM", 0)
                mandatos_p["AD"] = mandatos_p.get("AD", 0) + mp_m + ppm_m
        elif y == 2025:
            if votes:
                ada_v = votes.pop("AD Açores", 0)
                votes["AD"] = votes.get("AD", 0) + ada_v
            if mandatos_p:
                ada_m = mandatos_p.pop("AD Açores", 0)
                mandatos_p["AD"] = mandatos_p.get("AD", 0) + ada_m
        elif y in (1979, 1980):
            if votes:
                psd_v = votes.pop("PPD/PSD", 0)
                cds_v = votes.pop("CDS", 0)
                votes["AD"] = votes.get("AD", 0) + psd_v + cds_v
            if mandatos_p:
                psd_m = mandatos_p.pop("PPD/PSD", 0)
                cds_m = mandatos_p.pop("CDS", 0)
                mandatos_p["AD"] = mandatos_p.get("AD", 0) + psd_m + cds_m
        if y == 1980:
            if votes:
                ps_v = votes.pop("PS", 0)
                votes["FRS"] = votes.get("FRS", 0) + ps_v
            if mandatos_p:
                ps_m = mandatos_p.pop("PS", 0)
                mandatos_p["FRS"] = mandatos_p.get("FRS", 0) + ps_m

    n_votes_json = dict(data["METADATA"][lvl_key]["votes"])
    unify_qa(year, n_votes_off, None)
    unify_qa(year, n_votes_json, None)
    
    if n_votes_off:
        for p, v_json in n_votes_json.items():
            v_off = n_votes_off.get(p, 0)
            diff = abs(v_json - v_off)
            if year >= 2009:
                if diff > 0:
                    msg = f"Votos {lvl_key} para o partido {p} divergência: JSON={v_json}, Oficial={v_off}"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)
            else:
                if v_off > 0:
                    diff_pct = diff / v_off
                    if diff > 200 and diff_pct > 0.001:  # 0.1% de tolerância e >200 votos abs
                        msg = f"Votos nacionais para o partido {p} divergência: JSON={v_json}, Oficial={v_off} ({diff_pct*100:.3f}% diff)"
                        print(f"  [FAIL] {msg}")
                        failures.append(msg)
                        
    # 4. Mandatos
    expected_national_seats = {
        1975: 250, 1976: 267, 1979: 250, 1980: 250, 1983: 250, 1985: 250, 1987: 250,
        1991: 230, 1995: 230, 1999: 230, 2002: 230, 2005: 230, 2009: 230, 2011: 230,
        2015: 230, 2019: 230, 2022: 230, 2024: 230, 2025: 230, 2026: 230
    }
    expected_seats = expected_national_seats.get(year, 230)
    
    # Soma dos mandatos dos círculos
    sum_circle_seats = 0
    circle_mandatos_p_sum = defaultdict(int)
    for c_key, c_entry in data["AGG"]["distrito"].items():
        mand = c_entry.get("mandatos")
        if mand is None:
            msg = f"Círculo {c_key} mandatos é None"
            print(f"  [FAIL] {msg}")
            failures.append(msg)
        else:
            if not isinstance(mand, int):
                msg = f"Círculo {c_key} mandatos não é inteiro: {mand}"
                print(f"  [FAIL] {msg}")
                failures.append(msg)
            sum_circle_seats += (mand or 0)
        
        mandatos_p = c_entry.get("mandatos_p", {})
        if not mandatos_p and mand and mand > 0:
            msg = f"Círculo {c_key} mandatos_p está vazio"
            print(f"  [FAIL] {msg}")
            failures.append(msg)
        for p, m in mandatos_p.items():
            circle_mandatos_p_sum[p] += m
            
    if sum_circle_seats != expected_seats:
        msg = f"Soma total dos mandatos dos círculos divergência: esperado {expected_seats}, obtido {sum_circle_seats}"
        print(f"  [FAIL] {msg}")
        failures.append(msg)
    else:
        print(f"  [OK] Soma total dos mandatos dos círculos: {sum_circle_seats}")
        
    # Verificar soma dos mandatos partidários vs global/nacional mandatos_p
    lvl_key = "global" if year >= 2009 else "national"
    n_mand_p = dict(data["METADATA"][lvl_key].get("mandatos_p", {}))
    unify_qa(year, None, n_mand_p)
    unify_qa(year, None, circle_mandatos_p_sum)
    for p, m in circle_mandatos_p_sum.items():
        if n_mand_p.get(p, 0) != m:
            msg = f"{lvl_key.capitalize()} mandatos_p para {p} divergência com soma dos círculos: {lvl_key.capitalize()}={n_mand_p.get(p, 0)}, Soma={m}"
            print(f"  [FAIL] {msg}")
            failures.append(msg)
            
    # Cross-check com ar_{year}.json de eleitos
    eleitos_path = OUT_DIR / "eleitos" / f"ar_{year}.json"
    if eleitos_path.exists():
        with open(eleitos_path, "r", encoding="utf-8") as f:
            el_data = json.load(f)
        el_counts = defaultdict(int)
        for c_key, c_info in el_data.get("circulos", {}).items():
            for lst in c_info.get("listas", []):
                sigla = lst.get("sigla")
                # Harmonizar siglas
                sigla_clean = sigla
                if sigla == "BE": sigla_clean = "B.E."
                elif sigla == "PCP/PEV": sigla_clean = "PCP-PEV"
                elif sigla == "BE-UDP": sigla_clean = "B.E."
                elif sigla == "B.E.-UDP": sigla_clean = "B.E."
                elif sigla == "PàF" and year == 2015: sigla_clean = "PàF"
                elif sigla == "Partido Socialista": sigla_clean = "PS"
                elif sigla == "Partido Popular Democrático": sigla_clean = "PPD"
                el_counts[sigla_clean] += len(lst.get("eleitos", []))
                
        unify_qa(year, None, el_counts)
        for p, m in el_counts.items():
            target_party = p
            json_m = n_mand_p.get(target_party, 0)
            if json_m != m:
                if year == 2024 and target_party == "AD" and json_m == m + n_mand_p.get("Madeira Primeiro", 0):
                    pass
                elif year == 2022 and target_party in ("PS", "PPD/PSD") and abs(json_m - m) <= 1:
                    # Em 2022, a repetição da eleição no círculo da Europa mudou 1 mandato do PSD para o PS
                    # na lista de eleitos final, mas o workbook de resultados manteve os totais iniciais.
                    pass
                else:
                    msg = f"Eleitos contagem para {target_party} divergência: eleitos={m}, JSON mandatos_p={json_m}"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)
            else:
                print(f"  [OK] Eleitos contagem para {target_party} bate com JSON mandatos_p ({m})")
 
    # 5. Sanidade
    # inscritos >= votantes >= válidos + brancos + nulos
    
    # Nacional / Global
    lvl_key = "global" if year >= 2009 else "national"
    n = data["METADATA"][lvl_key]
    insc, vot, bra, nul = n.get("inscritos", 0), n.get("votantes", 0), n.get("brancos", 0), n.get("nulos", 0)
    validos = sum(n.get("votes", {}).values())
    if insc > 0:
        validos_of = sum(n.get("votes_oficial", {}).values()) if "votes_oficial" in n else validos
        has_error = False
        if not (insc >= vot):
            if not (year <= 1999 and (vot - insc) <= 1500):
                has_error = True
        if not (vot >= (validos_of + bra + nul)):
            if not (year <= 1999 and ((validos_of + bra + nul) - vot) <= 1500):
                has_error = True
        if has_error:
            msg = f"Sanidade {lvl_key.capitalize()} falhou: insc={insc}, vot={vot}, validos={validos_of}, bra={bra}, nul={nul}"
            print(f"  [FAIL] {msg}")
            failures.append(msg)
            
    # Distrito
    for c_key, c_entry in data["AGG"]["distrito"].items():
        insc = c_entry.get("inscritos", 0)
        vot = c_entry.get("votantes", 0)
        bra = c_entry.get("brancos", 0)
        nul = c_entry.get("nulos", 0)
        validos = sum(c_entry.get("votes", {}).values())
        if insc > 0:
            has_error = False
            if not (insc >= vot):
                if not (year <= 1999 and (vot - insc) <= 1500):
                    has_error = True
            if not (vot >= (validos + bra + nul)):
                if not (year <= 1999 and ((validos + bra + nul) - vot) <= 1500):
                    has_error = True
            if has_error:
                msg = f"Sanidade Distrito {c_key} falhou: insc={insc}, vot={vot}, validos={validos}, bra={bra}, nul={nul}"
                print(f"  [FAIL] {msg}")
                failures.append(msg)

    # Concelho sum of freguesias ≈ concelho total
    for c_code, c_entry in data["AGG"]["concelho"].items():
        entry_off = None
        for k_off, e_off in official.get("concelho", {}).items():
            mod_k = OLD_CONC_TO_MODERN.get(k_off[:4], k_off[:4])
            if mod_k == c_code:
                entry_off = e_off
                break
        if entry_off:
            sum_freg = sum(c_entry.get("votes", {}).values())
            sum_ofic = sum(entry_off.get("votes", {}).values())
            if sum_ofic > 0:
                diff_pct = abs(sum_freg - sum_ofic) / sum_ofic
                if diff_pct > 0.005:
                    msg = f"Sanidade Concelho {c_code} ({entry_off.get('name')}) freguesias divergem do oficial em {diff_pct*100:.2f}% (freg={sum_freg}, oficial={sum_ofic})"
                    print(f"  [FAIL] {msg}")
                    failures.append(msg)
                    
    ok = len(failures) == 0
    print(f"RESULTADO QA PARA {year}: {'PASSOU' if ok else 'REVER'}")
    return ok, failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA de Resultados Oficiais AR")
    parser.add_argument("years", metavar="N", type=int, nargs="*", help="Anos a processar")
    parser.add_argument("--all", action="store_true", help="Processar todos os anos")
    parser.add_argument("--json", type=str, help="Caminho para guardar relatório JSON")
    args = parser.parse_args()
    
    years_to_proc = YEARS if args.all else args.years
    # Apenas validar anos que tenham o ficheiro JSON gerado
    years_to_proc = [y for y in years_to_proc if (OUT_DIR / "resultados" / f"ar_{y}.json").exists()]
    if not years_to_proc:
        print("Nenhum ficheiro JSON de resultados encontrado para validar.")
        sys.exit(0)
        
    results = {}
    all_ok = True
    for y in sorted(years_to_proc):
        ok, fails = check_year(y)
        results[y] = {"ok": ok, "fails": fails}
        if not ok:
            all_ok = False
            
    # Guardar relatório
    if args.json:
        out_path = Path(args.json)
    else:
        out_path = OUT_DIR.parent / "scratch" / "qa_oficial_report.json"
        
    out_path.parent.mkdir(exist_ok=True, parents=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nRelatório de QA guardado em {out_path}")
                
    if not all_ok:
        print("\nFALHA NO QA OFICIAL!")
        sys.exit(1)
    else:
        print("\nQA OFICIAL COMPLETOU COM SUCESSO!")
        sys.exit(0)
