# -*- coding: utf-8 -*-
"""Reconciliação de siglas partidárias entre os ficheiros `PT {ano} certo.xlsx`
(fonte canónica das siglas por ano) e os workbooks oficiais "Globais".

GLOBAIS_TO_CERTO[ano] mapeia nome de coluna do Globais -> sigla do certo.
Colunas que mapeiam para a mesma sigla são somadas (ex.: as duas variantes da
coligação AD em 2025). Colunas ausentes do mapa passam com o próprio nome.
"""

GLOBAIS_TO_CERTO = {
    2022: {
        # coligações regionais: Madeira Primeiro (PSD+CDS, Madeira) e AD Açores (PSD+CDS+PPM)
        "PPD/PSD.CDS-PP": "Madeira Primeiro",
        "PPD/PSD.CDS-PP.PPM": "AD Açores",
    },
    2015: {
        "PPD/PSD.CDS-PP": "PàF",
        "CDS-PP.PPM": "Aliança Açores",
    }
}


def globais_party_to_certo(year, name, code=None):
    if year == 2025:
        clean_code = str(code).strip() if code is not None else ""
        # Açores: códigos começam com 4
        if clean_code.startswith("4") or clean_code == "000040" or clean_code == "400000":
            if name == "PPD/PSD.CDS-PP.PPM":
                return "AD Açores"
        if name in ("PPD/PSD.CDS-PP", "PPD/PSD.CDS-PP.PPM"):
            return "AD"

    if year == 2024:
        clean_code = str(code).strip() if code is not None else ""
        # Madeira: códigos começam com 3
        if clean_code.startswith("3") or clean_code == "000030" or clean_code == "300000":
            if name == "PPD/PSD.CDS-PP":
                return "Madeira Primeiro"
        if name in ("PPD/PSD.CDS-PP", "PPD/PSD.CDS-PP.PPM"):
            return "AD"
            
    return GLOBAIS_TO_CERTO.get(year, {}).get(name, name)


# Normalização de sigla -> chave de cor (usada também no JS; manter em sincronia
# com PARTY_COLORS_PT em js/globals.js).
COLOR_KEY = {
    "B.E.": "BE",
    "R.I.R.": "RIR",
    "PPD/PSD": "PSD",
    "PPD": "PSD",
    "Madeira Primeiro": "AD",
    "AD Açores": "AD",
    "PCP-PEV": "CDU",
    "APU": "CDU",
    "FEPU": "CDU",
}
