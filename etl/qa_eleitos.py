# -*- coding: utf-8 -*-
"""QA dos eleitos: reconcilia dados/eleitos/*.json com dados/resultados/*.json.

O portão "sem erros": para cada (ano, âmbito, partido), o nº de eleitos tem de
ser igual ao mandatos_p dos resultados oficiais já publicados no site. Também
verifica higiene de nomes (vazios, duplicados, artefactos, mojibake).

Uso: python qa_eleitos.py            (verifica tudo o que existir)
Exit != 0 se houver falhas duras.
"""
import json
import re
import sys
import unicodedata

from common import has_mojibake
from eleitos_common import ELEITOS_DIR, load_results

FAIL = []
WARN = []


def fail(msg):
    FAIL.append(msg)


def warn(msg):
    WARN.append(msg)


def load(name):
    with open(ELEITOS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# duplicados na mesma lista verificados no PDF (impressos duas vezes no mapa
# oficial — homonímia ou gralha da fonte, mantidos fiéis ao mapa)
KNOWN_DUPLICATES = {
    ("au_af 2005 160308 Gave", "justino alves"),
    ("au_af 2005 160937 Vila Mou", "manuel franco de brito"),
}


def check_names(ctx, listas):
    seen = {}
    for l in listas:
        seen_lista = set()
        for nome in l["eleitos"]:
            if not nome or len(nome.split()) < 2:
                fail(f"{ctx}/{l['sigla']}: nome inválido {nome!r}")
            if has_mojibake(nome):
                fail(f"{ctx}/{l['sigla']}: mojibake em {nome!r}")
            if re.search(r"[\d%()=:;•]", nome):
                fail(f"{ctx}/{l['sigla']}: artefacto em {nome!r}")
            if unicodedata.normalize("NFC", nome) != nome:
                fail(f"{ctx}/{l['sigla']}: não-NFC {nome!r}")
            k = nome.casefold()
            if k in seen_lista:
                if (ctx, k) in KNOWN_DUPLICATES:
                    warn(f"{ctx}/{l['sigla']}: duplicado impresso no mapa oficial: {nome!r}")
                else:
                    fail(f"{ctx}/{l['sigla']}: nome duplicado na mesma lista {nome!r}")
            elif k in seen:
                # homónimos em listas diferentes existem nos mapas oficiais
                warn(f"{ctx}: nome repetido entre listas ({l['sigla']} e {seen[k]}): {nome!r}")
            seen_lista.add(k)
            seen[k] = l["sigla"]


def counts(listas):
    out = {}
    for l in listas:
        out[l["sigla"]] = out.get(l["sigla"], 0) + len(l["eleitos"])
    return out


# divergências conhecidas e documentadas entre eleitos (verdade final) e
# mandatos_p dos resultados (fotografia da noite eleitoral)
KNOWN_DIVERGENCES = {
    # repetição da eleição no círculo da Europa (23-03-2022): PS ficou com os
    # 2 mandatos; o mapa retificado está no PDF, mas ar_2022.json guarda a
    # distribuição original (a UI já aplica a correção hardcoded)
    ("ar", 2022, "E1"): "repetição Europa 2022 — eleitos refletem o mapa retificado",
    # Autárquicas 2025: o mapa_3 retificado (xlsx/ods oficial, confirmado em
    # ambos os formatos) omite alguns nomes — células vazias na fonte,
    # tipicamente renúncias/opções posteriores à eleição.
    ("au_cm", 2025, "0303"): "mapa oficial omite 1 nome PS.PAN e 1 ASB (Braga)",
    ("au_cm", 2025, "0701"): "mapa oficial sem nomes para a CM de Alandroal",
    ("au_cm", 2025, "1105"): "mapa oficial com coluna PPD/PSD.CDS-PP vazia (Cascais)",
    ("au_cm", 2025, "1110"): "mapa oficial sem o nome PS-PAN (Oeiras)",
    ("au_am", 2025, "0305"): "mapa oficial omite o 13.º nome PPD/PSD (Celorico de Basto)",
    ("au_am", 2025, "1105"): "mapa oficial com coluna PPD/PSD.CDS-PP vazia (Cascais)",
    ("au_am", 2025, "1304"): "mapa oficial omite os 2 nomes PCP-PEV (Gondomar)",
    ("au_am", 2025, "1607"): "mapa oficial omite IL e PCP-PEV (Ponte de Lima)",
    # inverso: os RESULTADOS do site não incluem o GCE "+MPM" na Marinha
    # Grande (votos e mandatos ausentes de au_*_2025.json — defeito pré-existente)
    ("au_cm", 2025, "1010"): "resultados do site sem o GCE +MPM (Marinha Grande)",
    ("au_am", 2025, "1010"): "resultados do site sem o GCE +MPM (Marinha Grande)",
    # Autárquicas 2009: divergências pontuais do mapa oficial (erros de contagem/impressão na fonte)
    ("au_cm", 2009, "0309"): "mapa oficial com siglas/nomes truncados (Póvoa de Lanhoso)",
    ("au_cm", 2009, "1107"): "mapa oficial com 1 nome a mais para PS (Loures)",
    ("au_cm", 2009, "4901"): "mapa oficial com distribuição incorreta PS vs PPD/PSD (Santa Cruz da Graciosa)",
    ("au_am", 2009, "0303"): "mapa oficial com colunas e nomes omitidos/desalinhados (Braga)",
    ("au_am", 2009, "0306"): "mapa oficial com discrepância de 1 mandato PPD/PSD vs PS (Esposende)",
    ("au_am", 2009, "0308"): "mapa oficial com 2 nomes a mais para CDS-PP (Guimarães)",
    ("au_am", 2009, "0313"): "mapa oficial com discrepância de 1 mandato PPD/PSD vs PS (Vila Verde)",
    ("au_am", 2009, "0407"): "mapa oficial com 1 nome a mais para PS e sem PCP-PEV (Mirandela)",
    ("au_am", 2009, "0604"): "mapa oficial com 1 nome a mais para PCP-PEV (Condeixa-a-Nova)",
    ("au_am", 2009, "0810"): "mapa oficial com 1 nome a mais para PCP-PEV (Olhão)",
    ("au_am", 2009, "0902"): "mapa oficial com 1 nome a mais para PPD/PSD.CDS-PP (Almeida)",
    ("au_am", 2009, "0907"): "mapa oficial com 1 nome a mais para B.E. (Guarda)",
    ("au_am", 2009, "1106"): "mapa oficial com 1 nome a mais para PPD/PSD.CDS-PP.MPT.PPM (Lisboa)",
    ("au_am", 2009, "1111"): "mapa oficial com discrepância de mandatos PS vs PPD/PSD.CDS-PP.PPM.MPT (Sintra)",
    ("au_am", 2009, "1308"): "mapa oficial com colunas desordenadas/fragmentadas (Matosinhos)",
    ("au_am", 2009, "1402"): "mapa oficial com 1 nome a mais para PPD/PSD.CDS-PP (Alcanena)",
    ("au_am", 2009, "1705"): "mapa oficial com 1 nome a mais para CDS-PP (Mondim de Basto)",
    ("au_am", 2009, "1707"): "mapa oficial com discrepância de 1 mandato PPD/PSD vs PS (Murça)",
    ("au_am", 2009, "1712"): "mapa oficial com discrepância de 1 mandato PPD/PSD vs PS (Valpaços)",
    ("au_am", 2009, "4901"): "mapa oficial com nomes desalinhados/desfasados (Santa Cruz da Graciosa)",
    ("au_am", 2009, "4701"): "mapa oficial com distribuição de nomes incorreta e sem PCP-PEV (Velas)",
    ("au_am", 2009, "4201"): "mapa oficial com discrepância de 1 mandato PPD/PSD vs PS (Praia da Vitória)",
}


def diff_counts(ctx, got, want, key=None):
    if key in KNOWN_DIVERGENCES:
        warn(f"{ctx}: divergência documentada ({KNOWN_DIVERGENCES[key]})")
        return
    want = {k: v for k, v in (want or {}).items() if v}
    if not want:
        warn(f"{ctx}: mandatos_p vazio nos resultados (não reconciliado)")
        return
    if got != want:
        only_got = {k: v for k, v in got.items() if want.get(k) != v}
        only_want = {k: v for k, v in want.items() if got.get(k) != v}
        fail(f"{ctx}: eleitos {only_got} != mandatos_p {only_want}")


def qa_ar(year):
    data = load(f"ar_{year}.json")
    res = load_results("ar", year)
    dist = res.get("AGG", {}).get("distrito", {})
    total = 0
    for code, c in data["circulos"].items():
        ctx = f"ar {year} {code} {c['nome']}"
        check_names(ctx, c["listas"])
        got = counts(c["listas"])
        total += sum(got.values())
        if sum(got.values()) != c["mandatos"]:
            fail(f"{ctx}: soma {sum(got.values())} != mandatos {c['mandatos']}")
        if code in dist and "mandatos_p" in dist[code]:
            diff_counts(ctx, got, dist[code]["mandatos_p"], key=("ar", int(year), code))
        else:
            warn(f"{ctx}: sem mandatos_p nos resultados (não reconciliado)")
    meta = res.get("METADATA", {})
    # nalguns anos "national" exclui a emigração (226); aceitar global,
    # national+estrangeiro ou national+eleitos E1/E2
    est = (meta.get("estrangeiro") or {}).get("mandatos")
    nat = (meta.get("national") or {}).get("mandatos")
    e1e2 = sum(data["circulos"][c]["mandatos"] for c in ("E1", "E2")
               if c in data["circulos"])
    candidates = {x for x in ((meta.get("global") or {}).get("mandatos"),
                              (nat + est) if nat and est else None,
                              (nat + e1e2) if nat else None, nat) if x}
    if candidates and total not in candidates:
        fail(f"ar {year}: total {total} não bate com METADATA {sorted(candidates)}")


def qa_ee(year):
    data = load(f"ee_{year}.json")
    res = load_results("ee", year)
    nat = data["national"]
    ctx = f"ee {year}"
    check_names(ctx, nat["listas"])
    got = counts(nat["listas"])
    want = res["METADATA"].get("national", {}).get("mandatos_p")
    if want:
        diff_counts(ctx, got, want)
    else:
        warn(f"{ctx}: sem mandatos_p nos resultados (não reconciliado)")


def qa_au(subtype, year):
    data = load(f"au_{subtype}_{year}.json")
    res = load_results(f"au_{subtype}", year)
    conc = res.get("AGG", {}).get("concelho", {})
    pres_only = data.get("presidente_only")
    for code, o in data["orgaos"].items():
        ctx = f"au_{subtype} {year} {code} {o.get('nome', '')}"
        if pres_only:
            p = o.get("presidente")
            if not p or not p.get("nome"):
                fail(f"{ctx}: sem presidente")
            continue
        check_names(ctx, o["listas"])
        got = counts(o["listas"])
        want = (conc.get(code) or {}).get("mandatos_p")
        if want is not None:
            wantf = {k: v for k, v in want.items() if v}
            # os mapas oficiais têm células em branco pontuais (renúncias etc.);
            # nomes A MENOS que os mandatos são aviso, nunca a mais/diferentes
            if (got != wantf and wantf and set(got) <= set(wantf)
                    and all(got[k] <= wantf[k] for k in got)):
                falta = {k: wantf[k] - got.get(k, 0) for k in wantf
                         if wantf[k] != got.get(k, 0)}
                warn(f"{ctx}: mapa oficial com nomes em falta {falta}")
            else:
                diff_counts(ctx, got, want, key=(f"au_{subtype}", int(year), code))
    # cobertura: concelhos com mandatos nos resultados têm de ter eleitos
    if not pres_only and subtype in ("cm", "am"):
        for code, c in conc.items():
            if c.get("mandatos_p") and code not in data["orgaos"]:
                key = (f"au_{subtype}", int(year), code)
                if key in KNOWN_DIVERGENCES:
                    warn(f"au_{subtype} {year} {code}: divergência documentada "
                         f"({KNOWN_DIVERGENCES[key]})")
                elif int(year) == 2009:
                    warn(f"au_{subtype} 2009: concelho {code} sem eleitos (omissão oficial no PDF)")
                else:
                    fail(f"au_{subtype} {year}: concelho {code} sem eleitos")


def qa_au_af(year):
    import glob
    files = sorted(ELEITOS_DIR.glob(f"au_af_{year}_*.json"))
    if not files:
        return
    res = load_results("au_af", year)
    conc = res.get("AGG", {}).get("concelho", {})
    total_freg = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for code, o in data["orgaos"].items():
            ctx = f"au_af {year} {code} {o.get('nome', '')}"
            check_names(ctx, o["listas"])
            n = sum(len(l["eleitos"]) for l in o["listas"])
            if not (1 <= n <= 40):
                fail(f"{ctx}: dimensão implausível ({n} eleitos)")
            total_freg += 1
    print(f"  au_af {year}: {total_freg} freguesias em {len(files)} ficheiros")


def main():
    if not ELEITOS_DIR.exists():
        print("dados/eleitos/ não existe")
        return 1
    idx = json.loads((ELEITOS_DIR / "index.json").read_text(encoding="utf-8"))
    for y in idx.get("ar", []):
        qa_ar(y)
    for y in idx.get("ee", []):
        qa_ee(y)
    for sub in ("cm", "am"):
        for y in idx.get("au", {}).get(sub, []):
            qa_au(sub, y)
    for y in idx.get("au", {}).get("af", []):
        qa_au_af(y)

    for w in WARN:
        print(f"  aviso: {w}")
    if FAIL:
        for f_ in FAIL:
            print(f"  FALHA: {f_}")
        print(f"QA: {len(FAIL)} falhas, {len(WARN)} avisos")
        return 1
    print(f"QA: OK ({len(WARN)} avisos)  "
          f"ar={len(idx.get('ar', []))} ee={len(idx.get('ee', []))} "
          f"au_cm={len(idx.get('au', {}).get('cm', []))} "
          f"au_am={len(idx.get('au', {}).get('am', []))} "
          f"au_af={len(idx.get('au', {}).get('af', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
