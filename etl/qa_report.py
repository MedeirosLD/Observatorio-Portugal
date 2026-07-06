# -*- coding: utf-8 -*-
"""QA cruzado: cobertura de join resultados<->mapa, totais por distrito e vencedores.

Uso:
    python etl/qa_report.py 2025 2022
    python etl/qa_report.py --all
"""
import json
import sys
from collections import defaultdict

from common import OUT_DIR, YEARS, circulo_from_dicofre


def check_official_f(data, geo, year):
    res_codes = set(data["RESULTS"].keys())
    off_f_codes = set(data.get("OFFICIAL_F", {}).keys())
    
    if not off_f_codes:
        print(f"  OFFICIAL_F: Sem dados para {year}")
        return True
        
    inter = len(res_codes & off_f_codes)
    cov_res = 100 * inter / len(res_codes) if res_codes else 0
    cov_of = 100 * inter / len(off_f_codes) if off_f_codes else 0
    print(f"  OFFICIAL_F: comum={inter}, resultados->oficial={cov_res:.2f}%, oficial->resultados={cov_of:.2f}%")
    if cov_of < 98.0:
        print(f"  AVISO: cobertura oficial->resultados é {cov_of:.2f}% < 98%")

    # Sanidade: inscritos >= votantes >= (validos + brancos + nulos)
    sanity_fails = []
    for code, values in data.get("OFFICIAL_F", {}).items():
        if len(values) >= 4:
            insc, vot, bra, nul = values[:4]
            validos = sum(data["RESULTS"].get(code, {}).values())
            if not (insc >= vot >= (validos + bra + nul)):
                sanity_fails.append((code, insc, vot, validos, bra, nul))
    if sanity_fails:
        print(f"  Sanidade OFFICIAL_F: {len(sanity_fails)} freguesias falharam (inscritos >= votantes >= validos+brancos+nulos). Top-10:")
        for code, insc, vot, val, bra, nul in sanity_fails[:10]:
            print(f"    - {code}: insc={insc}, vot={vot}, validos={val}, brancos={bra}, nulos={nul}")

    # Roll-up inscritos por concelho vs AGG.concelho
    concelho_insc_rollup = defaultdict(int)
    for code, values in data.get("OFFICIAL_F", {}).items():
        if len(values) >= 1:
            concelho_insc_rollup[code[:4]] += values[0]
        
    roll_fails = []
    for conc_code, entry in data["AGG"]["concelho"].items():
        if "inscritos" in entry:
            of_insc = entry["inscritos"]
            ru_insc = concelho_insc_rollup.get(conc_code, 0)
            if of_insc > 0:
                diff_pct = abs(of_insc - ru_insc) / of_insc
                if diff_pct > 0.005:
                    roll_fails.append((conc_code, of_insc, ru_insc, diff_pct * 100))
    if roll_fails:
        roll_fails.sort(key=lambda x: x[3], reverse=True)
        print(f"  Roll-up Concelho (oficial vs soma oficial_f): {len(roll_fails)} concelhos > 0.5% diff. Top-10:")
        for cc, of, ru, pct in roll_fails[:10]:
            print(f"    - {cc}: oficial={of}, sum_freg={ru} ({pct:.2f}% diff)")

    # METADATA.global presente >= 2009 e global.inscritos > national.inscritos
    meta = data["METADATA"]
    if year >= 2009:
        if "global" not in meta:
            print("  ERRO: METADATA.global ausente!")
            return False
        g = meta["global"]
        n = meta.get("national", {})
        if g.get("inscritos", 0) <= n.get("inscritos", 0):
            print(f"  ERRO: global.inscritos ({g.get('inscritos')}) <= national.inscritos ({n.get('inscritos')})")
            return False
        print(f"  METADATA.global: OK (inscritos={g['inscritos']:,} > nacional={n.get('inscritos', 0):,})")
    
    return True


def qa_year(year):
    print(f"=== {year} ===")
    try:
        with open(OUT_DIR / "resultados" / f"ar_{year}.json", encoding="utf-8") as f:
            data = json.load(f)
        with open(OUT_DIR / "mapas" / f"freguesias_{year}.geojson", encoding="utf-8") as f:
            geo = json.load(f)
    except FileNotFoundError as e:
        print(f"  FALTA: {e.filename}")
        return False

    res_codes = set(data["RESULTS"].keys())
    map_codes = {ft["properties"]["dicofre"] for ft in geo["features"]}

    only_res = sorted(res_codes - map_codes)
    only_map = sorted(map_codes - res_codes)
    inter = len(res_codes & map_codes)
    cov_res = 100 * inter / len(res_codes) if res_codes else 0
    cov_map = 100 * inter / len(map_codes) if map_codes else 0
    print(f"  freguesias: resultados={len(res_codes)}, mapa={len(map_codes)}, comum={inter}")
    print(f"  cobertura: resultados->mapa {cov_res:.2f}%  |  mapa->resultados {cov_map:.2f}%")
    if only_res:
        print(f"  só nos resultados ({len(only_res)}): {only_res[:15]}")
    if only_map:
        print(f"  só no mapa ({len(only_map)}): {only_map[:15]}")

    # totais por distrito vs oficial
    dist_sum = defaultdict(int)
    for code, votes in data["RESULTS"].items():
        circ = circulo_from_dicofre(code)
        if circ:
            dist_sum[circ] += sum(votes.values())
    bad_dist = []
    for key, entry in data["AGG"]["distrito"].items():
        if key in ("E1", "E2") or "inscritos" not in entry:
            continue
        official_sum = sum(entry["votes"].values())
        if official_sum != dist_sum.get(key, 0):
            bad_dist.append((key, dist_sum.get(key, 0), official_sum))
    if bad_dist:
        print(f"  DIVERGÊNCIA distrito (freg vs oficial): {bad_dist}")
    else:
        print(f"  totais por distrito: OK ({len(data['AGG']['distrito'])} círculos)")

    # vencedor recomputado vs coluna Vencedor do utilizador
    qa_venc = data.get("QA_VENCEDOR", {})
    mism = []
    for code, venc_str in qa_venc.items():
        votes = data["RESULTS"].get(code)
        if not votes:
            continue
        winner = max(votes, key=votes.get)
        declared = venc_str.rsplit(" ", 1)[0].strip()
        if declared and winner != declared:
            top = sorted(votes.values(), reverse=True)
            if len(top) > 1 and top[0] == top[1]:
                continue  # empate: qualquer um é aceitável
            mism.append((code, winner, declared))
    if mism:
        print(f"  vencedores divergentes ({len(mism)}): {mism[:10]}")
    else:
        print(f"  vencedores: OK ({len(qa_venc)} verificados)")

    # Critério de "sem freguesias cinzentas": TODO o polígono do mapa deve ter
    # resultado -> cov_map (mapa->resultados) ~100%. A cobertura inversa
    # (resultados->mapa) fica <100% nos anos antigos por causa de freguesias
    # continentais extintas/fundidas que têm votos mas não têm polígono nesse ano —
    # é benigno (os votos entram nos agregados; não pintam cinzento). Reportamos mas
    # não reprovamos por isso.
    ok_of = check_official_f(data, geo, year)
    ok = cov_map >= 99.5 and not bad_dist and ok_of
    flag = "" if cov_res >= 99.5 else f" (nota: {100-cov_res:.1f}% dos resultados são freguesias extintas sem polígono)"
    print(f"  => {'PASSOU' if ok else 'REVER'} (mapa->resultados {cov_map:.2f}%){flag}")
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    years = YEARS if "--all" in args else [int(a) for a in args if a.isdigit()]
    if not years:
        print(__doc__)
        sys.exit(1)
    results = {y: qa_year(y) for y in years}
    fails = [y for y, ok in results.items() if not ok]
    if fails:
        print(f"\nANOS A REVER: {fails}")
        sys.exit(1)
    print("\nTODOS OS ANOS PASSARAM")
