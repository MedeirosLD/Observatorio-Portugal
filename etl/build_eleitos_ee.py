# -*- coding: utf-8 -*-
"""Eleitos das Europeias (1987-2024) a partir dos mapas oficiais DR/CNE.

Formatos por ano (todos texto extraível):
  1987/1989: "SIGLA – Nome do partido (n):"           nomes com ponto final
  1994/1999: "Pela lista do/da Nome (SIGLA):"          nomes com ponto final
  2004:      "Nome do partido (SIGLA)"                 nomes sem ponto
  2009:      "Nome do partido (SIGLA):"                nomes com ponto
  2014:      "Nome do partido (SIGLA)"                 nomes sem ponto
  2019:      "Nome do partido (SIGLA)"                 nomes com ponto
  2024:      "SIGLA — [ALIAS —] NOME (n)"              nomes com ponto

Um cabeçalho só é aceite se a sigla resolver contra METADATA.parties do
ee_{ano}.json — isso torna a deteção robusta a texto circundante do DR.
"""
import re
import sys

from eleitos_common import (DR_DIR, SiglaResolver, clean_name, load_results,
                            nfc, pdf_lines, rebuild_index, write_eleitos_json)

EE_SOURCES = {
    1987: "ce_pe1987.pdf",
    1989: "ce_pe1989.pdf",
    1994: "ce_pe1994.pdf",
    1999: "ce_pe1999.pdf",
    2004: "ce_pe2004.pdf",
    2009: "resultados_pe_2009_.pdf",
    2014: "pe_2014_mapa_resultados_dr_0.pdf",
    2019: "2019_pe_mapa_resultados.pdf",
    2024: "2024_pe_mapa_oficial_resultados_dr.pdf",
}

RE_HEAD_A = re.compile(r"^(?P<sigla>[A-ZÀ-Ü][\w./\- ]*?)\s*[—–]\s*(?P<resto>.+?)"
                       r"(?:\s*\((?P<n>\d+)\))?\s*:?\s*$")
RE_HEAD_B = re.compile(r"^Pela lista d[oa]s?\s+(?P<nome>.+?)\s*\((?P<sigla>[^)]+)\)\s*:?\s*$",
                       re.IGNORECASE)
RE_HEAD_C = re.compile(r"^(?P<nome>[^()]+?)\s*\((?P<sigla>[A-Z][^)]*?)\)\s*:?\s*$")

RE_END = re.compile(r"^(Comissão Nacional de Eleições\s*,|Nota\s*:|Resultados$)")
RE_TABLE = re.compile(r"(\d|\.\s*\.|%)")


def norm_sigla_dr(s):
    s = nfc(s.strip())
    s = re.sub(r"\s*-\s*", "-", s)          # "PCP -PEV" -> "PCP-PEV"
    s = re.sub(r"\.\s+", ".", s)            # "B. E." -> "B.E."
    s = re.sub(r"\s{2,}", " ", s)
    return s


def join_hyphen_wraps(lines):
    out = []
    for ln in lines:
        if out and out[-1].endswith("-") and not out[-1].endswith(" -"):
            out[-1] = out[-1][:-1] + ln
        else:
            out.append(ln)
    return out


# Em 2009 a tabela de resultados contém linhas "Nome (SIGLA)" sem dígitos;
# só os cabeçalhos reais da relação de eleitos terminam em ":".
HEAD_REQUIRE_COLON = {2009}


def try_heading(line, resolver, require_colon=False):
    """Devolve (sigla_site, sigla_dr, nome_dr, n_esperado) ou None."""
    if require_colon and not line.rstrip().endswith(":"):
        return None
    if ". ." in line or ".." in line:  # linha de tabela com pontilhado
        return None
    m = RE_HEAD_A.match(line)
    if m:
        sig = norm_sigla_dr(m.group("sigla"))
        key = resolver.resolve(sig)
        if key:
            resto = m.group("resto").strip().rstrip(":").strip()
            # 2024: "AD — ALIANÇA DEMOCRÁTICA" (alias antes do nome)
            nome_dr = resto.split("—")[-1].split("–")[-1].strip()
            n = int(m.group("n")) if m.group("n") else None
            return key, sig, nome_dr, n
    m = RE_HEAD_B.match(line)
    if m:
        sig = norm_sigla_dr(m.group("sigla"))
        key = resolver.resolve(sig)
        if key:
            return key, sig, clean_name(m.group("nome")), None
    m = RE_HEAD_C.match(line)
    if m:
        sig = norm_sigla_dr(m.group("sigla"))
        key = resolver.resolve(sig)
        if key:
            return key, sig, clean_name(m.group("nome")), None
    return None


def looks_like_name(line):
    s = line.rstrip(".").strip()
    if len(s.split()) < 2:
        return False
    if re.search(r"[\d%()—–]", s):
        return False
    if re.match(r"^(Total|Resultados|Inscritos|Votantes|Abstenção|Brancos|Nulos|Votos)\b", s,
                re.IGNORECASE):
        return False
    return True


def parse_ee(year):
    path = DR_DIR / "europeias" / EE_SOURCES[year]
    results = load_results("ee", year)
    parties = results["METADATA"]["parties"].keys()
    resolver = SiglaResolver(parties, year=year, election="ee")

    lines = join_hyphen_wraps(pdf_lines(path))
    listas, cur = [], None
    started = False
    for ln in lines:
        if not started:
            if re.search(r"deputados eleitos", ln, re.IGNORECASE):
                started = True
            continue
        if RE_END.match(ln):
            if listas:
                break
            continue
        head = try_heading(ln, resolver, require_colon=year in HEAD_REQUIRE_COLON)
        if head:
            key, sig, nome_dr, n = head
            cur = {"sigla": key, "eleitos": []}
            if sig != key:
                cur["sigla_dr"] = sig
            if nome_dr:
                cur["nome_dr"] = nome_dr
            if n is not None:
                cur["n_dr"] = n
            listas.append(cur)
            continue
        if RE_TABLE.search(ln):
            continue
        if cur is not None and looks_like_name(ln):
            cur["eleitos"].append(clean_name(ln))

    # validações locais
    for l in listas:
        n = l.pop("n_dr", None)
        if n is not None and n != len(l["eleitos"]):
            raise SystemExit(f"ee {year} {l['sigla']}: {len(l['eleitos'])} nomes != ({n}) no cabeçalho")
        if not l["eleitos"]:
            raise SystemExit(f"ee {year} {l['sigla']}: lista vazia")
    total = sum(len(l["eleitos"]) for l in listas)
    payload = {"year": year, "election": "ee",
               "national": {"mandatos": total, "listas": listas}}
    write_eleitos_json(f"ee_{year}.json", payload)
    return total, [(l["sigla"], len(l["eleitos"])) for l in listas]


def main():
    years = [int(a) for a in sys.argv[1:]] or sorted(EE_SOURCES)
    for y in years:
        total, resumo = parse_ee(y)
        print(f"ee_{y}: {total} deputados  {resumo}")
    rebuild_index()


if __name__ == "__main__":
    main()
