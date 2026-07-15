# -*- coding: utf-8 -*-
"""Resultados oficiais dos círculos da emigração (Europa/Fora da Europa, 1976-1991) e
dos círculos especiais de 1975 (Macau, Moçambique, Emigração), transcritos manualmente
a partir dos mapas oficiais do Diário da República em
`mapas_diario_da_republica/assembleia da republica/` — não existem nos workbooks
Excel brutos usados por `build_results.py` (`resultados puros (sem alteração minha)`),
que só têm os 18 distritos + Açores + Madeira para estes anos.

Cada entrada é {ano: {chave_círculo: {name, inscritos, votantes, brancos, nulos,
mandatos, votes: {sigla: votos}, mandatos_p: {sigla: mandatos}}}}.

Siglas usam a grafia canónica de cada ano (a mesma de METADATA.parties em
dados/resultados/ar_{ano}.json), para que `build_year()` as integre sem precisar
de mapeamento adicional. Partidos sem correspondência nos círculos domésticos desse
ano (ADIM/CDM em 1975, PCR em 1983) são registados por build_results.py em
meta["parties"] se ainda não existirem lá.

Fontes (páginas com "Número de eleitores inscritos ... distribuição dos votos e
mandatos", não confundir com as páginas de "Lista dos candidatos eleitos"):
  1975: resultados_ac_1975.pdf, pp. 6-8 ("Mapa Nacional da Eleição para Assembleia
        Constituinte — Resultados"), linhas Macau/Moçambique/Emigração.
  1976: MapaOficialEleicoesAbril1976.pdf, p. 5 ("Anexo oficial ... Círculo da
        Europa" / "Círculo fora da Europa"). Esta tabela não separa brancos de
        nulos (só "Votos nulos"); por isso brancos=0 nesse ano.
  1979: MapaOficialEleicoesDezembro1979.pdf, p. 5.
  1980: MapaOficialEleicoesOutubro1980.pdf, p. 5.
  1983: MapaOficialEleicoesAbril1983.pdf, p. 5.
  1985: MapaOficialEleicoesOutubro1985.pdf, última página (layout rodado).
  1987: MapaOficialEleicoesJulho1987.pdf, pp. 5-6.
  1991: MapaOficialEleicoesOutubro1991.pdf, pp. 5-6.

Cada círculo foi validado por soma: votes + brancos + nulos == votantes (exacto
ou a menos de uma pequena divergência de arredondamento já presente na fonte
oficial, ex.: 1983).
"""

MANUAL_CIRCLE_DATA = {
    1976: {
        "E1": {
            "name": "Europa", "inscritos": 57341, "votantes": 51693, "brancos": 0, "nulos": 996,
            "mandatos": 2,
            "votes": {"AOC": 83, "CDS": 3555, "FSP": 183, "LCI": 28, "MES": 165, "MRPP": 69,
                      "PCP": 5212, "PDC": 475, "PPD": 16644, "PPM": 52, "PS": 23824, "UDP": 407},
            "mandatos_p": {"PPD": 1, "PS": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 48368, "votantes": 40047, "brancos": 0, "nulos": 578,
            "mandatos": 2,
            "votes": {"AOC": 21, "CDS": 13483, "MES": 3, "MRPP": 36, "PCP": 562, "PDC": 1277,
                      "PPD": 21317, "PPM": 123, "PS": 2517, "UDP": 130},
            "mandatos_p": {"CDS": 1, "PPD": 1},
        },
    },
    1979: {
        "E1": {
            "name": "Círculo da Europa", "inscritos": 59184, "votantes": 42203, "brancos": 394, "nulos": 712,
            "mandatos": 2,
            "votes": {"AD": 16154, "APU": 5659, "PCTP/MRPP": 932, "PDC": 2416, "PS": 14018,
                      "PSR": 91, "UDP": 2391, "UEDS": 436},
            "mandatos_p": {"AD": 1, "PS": 1},
        },
        "E2": {
            "name": "Círculo fora da Europa", "inscritos": 73089, "votantes": 46176, "brancos": 643, "nulos": 879,
            "mandatos": 2,
            "votes": {"AD": 35689, "APU": 1424, "PCTP/MRPP": 223, "PDC": 4142, "PS": 2639,
                      "PSR": 28, "UDP": 337, "UEDS": 172},
            "mandatos_p": {"AD": 2},
        },
    },
    1980: {
        "E1": {
            "name": "Círculo da Europa", "inscritos": 70426, "votantes": 43913, "brancos": 740, "nulos": 752,
            "mandatos": 2,
            "votes": {"AD": 21757, "APU": 6678, "PCTP/MRPP": 536, "PDC": 1075, "POUS": 230,
                      "PSR": 62, "PT": 227, "PDA": 110, "UDP": 604, "PS": 11142},
            "mandatos_p": {"AD": 1, "PS": 1},
        },
        "E2": {
            "name": "Círculo de fora da Europa", "inscritos": 105151, "votantes": 64183, "brancos": 904, "nulos": 1143,
            "mandatos": 2,
            "votes": {"AD": 54898, "APU": 1694, "PCTP/MRPP": 122, "PDC": 2127, "POUS": 51,
                      "PSR": 40, "PT": 175, "PDA": 170, "UDP": 263, "PS": 2596},
            "mandatos_p": {"AD": 2},
        },
    },
    1983: {
        "E1": {
            "name": "Europa", "inscritos": 74590, "votantes": 35545, "brancos": 404, "nulos": 314,
            "mandatos": 2,
            "votes": {"APU": 6069, "CDS": 3955, "LST": 277, "OCMLP": 23, "PCTP/MRPP": 232,
                      "PDA": 105, "PDC": 815, "POUS": 150, "PPD/PSD": 11101, "PS": 11939,
                      "UDPSR": 23, "PCR": 38},
            "mandatos_p": {"PPD/PSD": 1, "PS": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 110749, "votantes": 48439, "brancos": 878, "nulos": 529,
            "mandatos": 2,
            "votes": {"APU": 1378, "CDS": 16511, "LST": 66, "PCTP/MRPP": 97, "PDA": 352,
                      "PDC": 1766, "POUS": 52, "PPD/PSD": 23365, "PS": 3384,
                      "UDPSR": 23, "PCR": 86},
            "mandatos_p": {"PPD/PSD": 1, "CDS": 1},
        },
    },
    1985: {
        "E1": {
            "name": "Europa", "inscritos": 75606, "votantes": 23540, "brancos": 751, "nulos": 101,
            "mandatos": 2,
            "votes": {"APU": 4417, "CDS": 4074, "PCR": 68, "PCTP/MRPP": 223, "PDC": 486,
                      "POUS": 109, "PRD": 1664, "PPD/PSD": 5712, "PS": 5700, "PSR": 32, "UDP": 203},
            "mandatos_p": {"PPD/PSD": 1, "PS": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 115212, "votantes": 33991, "brancos": 773, "nulos": 191,
            "mandatos": 2,
            "votes": {"APU": 866, "CDS": 12889, "PCR": 33, "PCTP/MRPP": 84, "PDC": 1396,
                      "POUS": 41, "PRD": 1113, "PPD/PSD": 13768, "PS": 2654, "PSR": 35, "UDP": 130},
            "mandatos_p": {"PPD/PSD": 1, "CDS": 1},
        },
    },
    1987: {
        "E1": {
            "name": "Europa", "inscritos": 72978, "votantes": 19261, "brancos": 384, "nulos": 66,
            "mandatos": 2,
            "votes": {"CDS": 1278, "CDU": 3054, "MDP/CDE": 97, "PCR": 70, "PCTP/MRPP": 258,
                      "PDC": 311, "PPM": 38, "PRD": 944, "PPD/PSD": 7125, "PS": 5467, "PSR": 25, "UDP": 144},
            "mandatos_p": {"PPD/PSD": 1, "PS": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 114603, "votantes": 30588, "brancos": 549, "nulos": 183,
            "mandatos": 2,
            "votes": {"CDS": 6089, "CDU": 418, "MDP/CDE": 247, "PCR": 20, "PCTP/MRPP": 82,
                      "PDC": 706, "PPM": 90, "PRD": 513, "PPD/PSD": 19343, "PS": 2221, "PSR": 73, "UDP": 54},
            "mandatos_p": {"PPD/PSD": 2},
        },
    },
    1991: {
        "E1": {
            "name": "Europa", "inscritos": 84495, "votantes": 29484, "brancos": 203, "nulos": 343,
            "mandatos": 2,
            "votes": {"CDS": 894, "FER": 19, "PCP-PEV": 2311, "PCTP/MRPP": 234, "PDA": 32,
                      "PPD/PSD": 15817, "PPM": 62, "PRD": 141, "PS": 9393, "PSR": 35},
            "mandatos_p": {"PPD/PSD": 1, "PS": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 103103, "votantes": 31644, "brancos": 180, "nulos": 177,
            "mandatos": 2,
            "votes": {"CDS": 4613, "PCP-PEV": 308, "PCTP/MRPP": 28, "PDA": 43,
                      "PPD/PSD": 24467, "PPM": 105, "PRD": 143, "PS": 1557, "PSR": 23},
            "mandatos_p": {"PPD/PSD": 2},
        },
    },
    1975: {
        "XM": {
            "name": "Macau", "inscritos": 3437, "votantes": 2876, "brancos": 0, "nulos": 224,
            "mandatos": 1,
            "votes": {"ADIM": 1622, "CDM": 1030},
            "mandatos_p": {"ADIM": 1},
        },
        "XC": {
            "name": "Moçambique", "inscritos": 17739, "votantes": 6080, "brancos": 0, "nulos": 3584,
            "mandatos": 1,
            "votes": {"PS": 2496},
            "mandatos_p": {"PS": 1},
        },
        "XE": {
            "name": "Emigração", "inscritos": 21910, "votantes": 18385, "brancos": 0, "nulos": 273,
            "mandatos": 1,
            "votes": {"PS": 6327, "PPD": 8385, "PCP": 846, "CDS": 2025, "FEC": 485, "PPM": 44},
            "mandatos_p": {"PPD": 1},
        },
    },
    1995: {
        "E1": {
            "name": "Europa", "inscritos": 48357, "votantes": 13077, "brancos": 47, "nulos": 1679,
            "mandatos": 2,
            "votes": {"PSR": 34, "CDS-PP": 635, "PCTP/MRPP": 103, "PCP-PEV": 898, "PS": 4965, "MPT": 131, "PPD/PSD": 4475, "MUT": 63, "UDP": 41, "PDA": 6},
            "mandatos_p": {"PS": 1, "PPD/PSD": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 44586, "votantes": 8320, "brancos": 32, "nulos": 710,
            "mandatos": 2,
            "votes": {"PSR": 22, "CDS-PP": 362, "PCTP/MRPP": 18, "PCP-PEV": 124, "PS": 1185, "MPT": 26, "PPD/PSD": 5800, "UDP": 21, "PDA": 20},
            "mandatos_p": {"PPD/PSD": 2},
        },
    },
    1999: {
        "E1": {
            "name": "Europa", "inscritos": 97023, "votantes": 25711, "brancos": 86, "nulos": 2255,
            "mandatos": 2,
            "votes": {"B.E.": 144, "PCP-PEV": 1340, "MPT": 273, "PCTP/MRPP": 213, "P.H.": 19, "CDS-PP": 822, "PPM": 73, "PPD/PSD": 6276, "PS": 14155, "PSN": 24, "POUS": 31},
            "mandatos_p": {"PS": 2},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 66893, "votantes": 14690, "brancos": 28, "nulos": 993,
            "mandatos": 2,
            "votes": {"B.E.": 25, "PCP-PEV": 256, "MPT": 49, "CDS-PP": 390, "PPM": 29, "PPD/PSD": 6879, "PS": 5967, "PSN": 48, "PCTP/MRPP": 26},
            "mandatos_p": {"PPD/PSD": 1, "PS": 1},
        },
    },
    2002: {
        "E1": {
            "name": "Europa", "inscritos": 85538, "votantes": 23829, "brancos": 112, "nulos": 1717,
            "mandatos": 2,
            "votes": {"PPD/PSD": 8795, "PCP-PEV": 1148, "POUS": 67, "CDS-PP": 1179, "PCTP/MRPP": 168, "B.E.": 250, "PPM": 59, "PS": 10010, "MPT": 302, "PNR": 22},
            "mandatos_p": {"PS": 1, "PPD/PSD": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 71537, "votantes": 14310, "brancos": 64, "nulos": 1080,
            "mandatos": 2,
            "votes": {"PPD/PSD": 9066, "MPT": 87, "B.E.": 57, "PCTP/MRPP": 38, "PPM": 40, "PS": 3288, "PCP-PEV": 144, "CDS-PP": 427, "PNR": 19},
            "mandatos_p": {"PPD/PSD": 2},
        },
    },
    2005: {
        "E1": {
            "name": "Europa", "inscritos": 75803, "votantes": 23437, "brancos": 101, "nulos": 1968,
            "mandatos": 2,
            "votes": {"PPD/PSD": 6268, "PCP-PEV": 962, "PND": 121, "CDS-PP": 786, "PCTP/MRPP": 145, "B.E.": 531, "PS": 12496, "PNR": 59},
            "mandatos_p": {"PS": 1, "PPD/PSD": 1},
        },
        "E2": {
            "name": "Fora da Europa", "inscritos": 68138, "votantes": 12103, "brancos": 32, "nulos": 1075,
            "mandatos": 2,
            "votes": {"PPD/PSD": 6742, "PND": 91, "B.E.": 84, "PS": 3454, "PCP-PEV": 136, "CDS-PP": 400, "PNR": 23, "PCTP/MRPP": 30, "PDA": 36},
            "mandatos_p": {"PPD/PSD": 2},
        },
    },
}
