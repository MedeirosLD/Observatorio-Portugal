# -*- coding: utf-8 -*-
"""Correções cirúrgicas aos eleitos extraídos dos mapas oficiais.

Cada entrada documenta um defeito do próprio mapa do DR (verificado
visualmente na página) e a correção mínima que o reconcilia com a
distribuição oficial de mandatos (mandatos_p dos resultados):

  ("move_tail", DE, PARA, N)  move os últimos N nomes da lista DE para o fim
                              da lista PARA (nomes impressos na coluna errada
                              nas quebras de página do mapa)
  ("trim", SIGLA, N)          corta os últimos N nomes (nomes a mais/duplicados
                              impressos no mapa, ex.: suplentes)

A chave é (ano, subtipo, dico/dicofre).
"""

# Correções manuais de linhas OCR ilegíveis, por tag de fonte
# (ocr_eleitos.py). Chave: trecho EXATO da linha OCR; valor: lista de linhas
# de substituição (vazia = descartar). Verificadas no scan original.
LINE_FIXES = {
    "ar_1995": {
        # Évora: cabeçalho da CDU com ruído e wrap pelo OCR
        "Pra CDU — Coligação Democrática Uni":
            ["PCP/PEV — CDU — Coligação Democrática Unitária (1):"],
        # Portalegre: "Artur Ryder Torres Pereira" desfeito pelo OCR
        # (o fragmento "Pereira" seguinte é descartado por ter 1 palavra)
        "Artur Ryder T P": ["Artur Ryder Torres Pereira."],
        # Aveiro PPD/PSD: o 5.º nome perdeu-se e o 6.º ficou truncado
        # (verificado no render da p. 1)
        "Loureiro Gonçalves ç": [
            "Manuel Alves de Oliveira.",
            "Hermínio José Sobral de Loureiro Gonçalves.",
        ],
        # Leiria PPD/PSD: 2.º nome degradado e 3.º perdido; 4.º ilegível
        # (verificado no render da p. 2)
        "Sa Marques.": [
            "José Augusto da Silva Marques.",
            "João Álvaro Poças Santos.",
        ],
        "José M ue anue unes E": ["José Manuel Nunes Liberato."],
        # Leiria PS: 2.º nome ilegível; 3.º e 4.º fundidos numa linha-lixo
        "Rui do Nasci Rab Vie": ["Rui do Nascimento Rabaça Vieira."],
        "Augusto EDEIO": [
            "Arnaldo Augusto Homem Rebelo.",
            "Osvaldo Alberto Rosário Sarmento e Castro.",
        ],
        # fragmento fantasma da segunda leitura do mesmo nome
        "Rosário Sarmento e Castro,": [],
        # Leiria CDS/PP: "(1):" lido como "(D:"
        "Partido Popular (D:": ["CDS/PP — Partido Popular (1):"],
        # Lisboa PS: sigla da coluna vizinha colada ao fim do nome
        "Ferro Rodrigues. PS": ["Eduardo Luís Barreto Ferro Rodrigues."],
        # Lisboa PCP/PEV: os 2 primeiros nomes fundidos numa linha-lixo
        "Va via mes has": [
            "Carlos Alberto do Vale Gomes Carvalhas.",
            "Luís Manuel da Silva Viana de Sá.",
        ],
        # Braga: fragmento da mancha da margem esquerda ("... eleições
        # legislati-") que o join_wraps colava ao nome seguinte
        "legislati-": [],
        # Castelo Branco PS: gralha de OCR (verificado no render da p. 1)
        "Serrasqueiliro": ["Fernando Pereira Serrasqueiro."],
        # Setúbal PS: mancha da margem fundida com o nome (render da p. 3)
        "RIDEiro": ["Eduardo Ribeiro Pereira."],
        # Madeira PPD/PSD: gralha de OCR (render da p. 4)
        "Comeia": ["Manuel Filipe Correia de Jesus."],
    },
    "ar_1991": {
        # Aveiro PPD/PSD (verificado no render da p. 1): 4.º nome com gralha,
        # 7.º truncado e 9.º lido duas vezes (linha fantasma do skew)
        "Dias Moreifa": ["Maria Manuela Aguiar Dias Moreira."],
        "Gomes Milhomens.": ["Jaime Gomes Milhomens."],
        "Júlio C lho Ribeiro": [],
        # Lisboa PSN: nome lido duas vezes; descarta-se a leitura fantasma
        "Séreio Vieira ha": [],
        # Lisboa PPD/PSD 19.º e 20.º degradados (verificado no render da p. 2)
        "Mari la Dias Ferreira": ["Maria Manuela Dias Ferreira Leite."],
        "Matos exe": ["João José Pedreira de Matos."],
    },
    "ar_1987": {
        # Braga: cabeçalhos do círculo e do PPD/PSD fundidos numa linha
        "Círculo Eleitoral de Braga (17) de": [
            "3 — Círculo Eleitoral de Braga (17)",
            "PPD/PSD — Partido Social-Democrata (10):",
        ],
        # Braga PS: 2.º e 3.º nomes fundidos numa linha-lixo (render p. 1)
        "IViaga": [
            "Alberto Arons Braga de Carvalho.",
            "António Magalhães da Silva.",
        ],
        # Bragança: cabeçalho do círculo duplicado-corrompido pelo OCR
        "reulo Eleitoral de Bragança": ["4 — Círculo Eleitoral de Bragança (4)"],
        # Bragança PS: cabeçalho partido em duas linhas ilegíveis
        "PS — Parti iali": ["PS — Partido Socialista (1):"],
        "Socia 1sta": [],
        # Lisboa PS: 1.º e 2.º nomes fundidos numa linha-lixo (render p. 2)
        "Vanue": [
            "Vítor Manuel Ribeiro Constâncio.",
            "Manuel Alfredo Tito de Morais.",
        ],
        # Porto PPD/PSD: 11.º-14.º nomes fundidos numa linha-lixo (render p. 3)
        "Guia ia Vilela de Araújo": [
            "Guido Orlando Freitas Rodrigues.",
            "José Nuno Borregana Meireles.",
            "Luís Filipe Meneses Lopes.",
            "Joaquim Vilela de Araújo.",
        ],
        # Bragança e Aveiro: gralhas de OCR (verificadas nos renders da p. 1)
        "José AIbi da Silva Peneda": ["José Albino da Silva Peneda."],
        "Arnaldo Angelo Brito Lhamas": ["Arnaldo Ângelo Brito Lhamas."],
    },
    "ar_1985": {
        # Beja: cabeçalho do PS destruído pelo OCR
        "pg partido Socialista": ["PS — Partido Socialista (1):"],
        # Porto: "(4)" lido como "(+)" no cabeçalho do CDS
        "Partido do Centro Social (+":
            ["CDS — Partido do Centro Democrático Social (4):"],
        # Porto PPD/PSD: wrap "de Aze-/vedo." cuja continuação se perdeu
        "Andrade de Aze-":
            ["Amélia Cavaleiro Monteiro de Andrade de Azevedo."],
        # Setúbal: cabeçalho da APU sem parênteses
        "Aliança Povo Unido 7": ["APU — Aliança Povo Unido (7):"],
        # Setúbal APU: 3.º e 4.º nomes degradados (render p. 4)
        "Manuel de Almeida.": [
            "José Manuel Maia Nunes de Almeida.",
            "Maria Odete dos Santos.",
        ],
        # Cabeçalho do círculo 16 (Viana do Castelo) perdido pelo OCR;
        # repõe-se a seguir ao último nome de Setúbal (render p. 4)
        "Fernando Manuel Alves Cardoso Ferreira.": [
            "Fernando Manuel Alves Cardoso Ferreira.",
            "16 — Círculo eleitoral de Viana do Castelo (6)",
        ],
        # Cabeçalho do círculo 22 (fora da Europa) perdido pelo OCR;
        # repõe-se a seguir ao último nome da Europa (render p. 4)
        "Rodolfo Alexandrino Suzano Crespo.": [
            "Rodolfo Alexandrino Suzano Crespo.",
            "22 — Círculo eleitoral de fora da Europa (2)",
        ],
        # Gralhas de OCR verificadas nos renders
        "Almeida Coclho": ["Carlos Miguel Maximiano de Almeida Coelho."],
        "Albu- querque":
            ["Maria Cristina Gomes da Silva Cardoso de Albuquerque."],
        "Angelo Matos Mendes Veloso": ["Ângelo Matos Mendes Veloso."],
        "José Vargas Bulcão": ["José Vargas Bulcão."],
    },
    "ar_1983": {
        # Setúbal PS: 1.º nome perdido pelo OCR (render p. 4);
        # repõe-se antes do 2.º
        "António Manuel Maldonado Gonelha.": [
            "Eduardo Ribeiro Pereira.",
            "António Manuel Maldonado Gonelha.",
        ],
        # Açores PPD/PSD: 2.º nome perdido pelo OCR (render p. 4)
        "Soares Mota Amaral,": [
            "João Bosco Soares Mota Amaral.",
            "Raul Gomes dos Santos.",
        ],
        # Madeira e Europa: prefixo-lixo colado ao nome (renders p. 4)
        "Jorge Nélio Praxedes Ferraz Mendonça":
            ["Jorge Nélio Praxedes Ferraz Mendonça."],
        "José Luís Figueiredo Lopes": ["José Luís Figueiredo Lopes."],
        # Braga PS: "Á" lido a dobrar (render p. 1)
        "d'AÁssunção": ["Raúl d'Assunção Pimenta Rego."],
    },
    "ar_1980": {
        # Aveiro FRS: mancha da margem ("estabe-", "272/80,") colada ao
        # 1.º nome (render p. 1)
        "estabe-": [],
        "72/80,": ["Carlos Manuel Natividade da Costa Candal."],
        # Aveiro AD: cabeçalho da tabela de preços do DR no meio da coluna
        "Anual Semestral": [],
        # Beja: cabeçalhos do círculo e da APU fundidos com a margem
        "Círculo de Beja (5) de": [
            "2 — Círculo de Beja (5)",
            "APU — Aliança Povo Unido (3):",
        ],
        "Dinis Fernandes Miranda": ["Dinis Fernandes Miranda."],
        "Assem- Francisco": ["Francisco Miguel Duarte."],
        # Lisboa AD: wraps cuja continuação se perdeu (renders p. 3)
        "Pestana de celos":
            ["Pedro António José Bracourt Pestana de Vasconcelos."],
        "Natália de Oliveira": ["Natália de Oliveira Correia."],
        "Paulo Sampaio da Costa": ["Maria Teresa Paulo Sampaio da Costa Macedo."],
        "Nascimento gues":
            ["Henrique Alberto Freitas do Nascimento Rodrigues."],
        # Lisboa APU: 2.º nome com wrap perdido (render p. 3)
        "Carmo Mendes rinha":
            ["José Manuel Marques do Carmo Mendes Tengarrinha."],
        # Portalegre: "Círculo" perdido no cabeçalho do círculo 12
        "12— de Portalegre": ["12 — Círculo de Portalegre (4)"],
        # Santarém APU: os 2 nomes perderam-se ('António' órfão descartado);
        # repõem-se a seguir ao cabeçalho (render p. 4)
        "APU — Aliança Povo Unido (2):": [
            "APU — Aliança Povo Unido (2):",
            "António Dias Lourenço.",
            "Raimundo do Céu Cabral.",
        ],
        # Açores: cabeçalho do PPD/PSD com a sigla degradada
        "“Par tido Social-Democrata":
            ["PPD/PSD — Partido Social-Democrata (4):"],
    },
    "ar_1979": {
        # Aveiro AD (render p. 1): "(9)" lido como "OO)"; 2.º nome truncado
        # e 3.º perdido; 4.º-7.º degradados; 5.º do PS sem o apelido final
        "Aliança Democrática OO)": ["AD — Aliança Democrática (9):"],
        "Rodrigues Pena": [
            "Rui Eduardo Ferreira Rodrigues Pena.",
            "Mário Martins Adegas.",
        ],
        "Armando Adão e": ["Armando Adão e Silva."],
        "José Duarte de. Almeida": ["José Duarte de Almeida Ribeiro e Castro."],
        "Nara Portugal": ["Manuel Maria Portugal da Fonseca."],
        "Ferreira Pereira de Melo.": ["António Ferreira Pereira de Melo."],
        "Melo Pires Tavares": ["Manuel Joaquim de Melo Pires Tavares Santos."],
        # Beja: cabeçalho da APU perdido; AD degradado; prefixo no nome
        "2 — Círculo de Beja (5)": [
            "2 — Círculo de Beja (5)",
            "APU — Aliança Povo Unido (3):",
        ],
        "re- — Aliança Democrática (1)": ["AD — Aliança Democrática (1):"],
        "António Duarte e Duarte Chagas": ["António Duarte e Duarte Chagas."],
        # Castelo Branco AD (render p. 2): 1.º e 2.º fundidos em "oseta."
        "^oseta.": [
            "Pedro Manuel Cruz Roseta.",
            "Carlos Martins Robalo.",
        ],
        "Calheiros Veloso pa": ["Luís Carlos Calheiros Veloso de Sampaio."],
        # Coimbra AD (render p. 2): 1.º e 3.º degradados
        "Mário Ferreira Bastos SS": ["Mário Ferreira Bastos Raposo."],
        "Manuel Mend": ["Manuel Pereira."],
        # Porto (render p. 3): 13.º/14.º do PS fundidos; cabeçalho da APU
        # destruído; 6.º da APU sem "Ilda"
        "Bento de Azevedo. alh": [
            "Bento Elísio de Azevedo.",
            "Adelino Teixeira de Carvalho.",
        ],
        "APU — Ali P id": ["APU — Aliança Povo Unido (6):"],
        "Um o (6)": [],
        "Maria da Costa Figueiredo": ["Maria Ilda da Costa Figueiredo."],
        # Santarém AD (render p. 3): gralha e 6.º sem "Henrique"
        "Manuel Bacta Neves": ["Manuel Baeta Neves."],
        "Manuel Soares Cruz": ["Henrique Manuel Soares Cruz."],
        # Gralhas verificadas nos renders
        "Ferreira Pulido de AF":
            ["João José Magalhães Ferreira Pulido de Almeida."],
        "Nascimento Rodri- Bgues":
            ["Henrique Alberto Freitas do Nascimento Rodrigues."],
        "Hélder Simão Pinheiro": ["Hélder Simão Pinheiro."],
        "Manudl Alfredo Tito de Morais": ["Manuel Alfredo Tito de Morais."],
    },
    "ar_1976": {
        # Guarda e Vila Real: "(2)" ilegível nos cabeçalhos do PS
        "Partido Socialista >": ["Partido Socialista (2):"],
        "Socialista OQ": ["Partido Socialista (2):"],
        # Angra do Heroísmo: "(1)" lido como "(DD"
        "Democrático (DD": ["Partido Popular Democrático (1):"],
        # Leiria PPD: gralha
        "Fernando José da Oosta": ["Fernando José da Costa."],
        # Lisboa PS: 16.º e 17.º fundidos numa linha-lixo (render p. 3)
        "Curtos Manuel da Cosa Moreira": [
            "Carlos Manuel da Costa Moreira.",
            "Florival da Silva Nobre.",
        ],
        # Lisboa PCP: 13.º-15.º degradados (render p. 3)
        "Ál A to Vei liveira": ["Álvaro Augusto Veiga de Oliveira."],
        "^Vitor de": ["Vítor Manuel Berrito da Silva."],
        "Vale Gomes Carvalhas los": ["Carlos Alberto do Vale Gomes Carvalhas."],
        # Porto PS: 4.º-6.º fundidos em duas linhas-lixo (render p. 3)
        "Laje, iva": [
            "Carlos Cardoso Laje.",
            "Manuel Joaquim de Paiva Pereira Pires.",
        ],
        "da Veiga Peixoto Vilar es": ["Emílio Rui da Veiga Peixoto Vilar."],
        # Porto PPD: 2.º com lixo e 4.º perdido antes do 5.º (render p. 3)
        "Silva França í": ["Olívio da Silva França."],
        "Bento Goncalves": [
            "Albino Aroso Ramos.",
            "José Bento Gonçalves.",
        ],
        # Viseu CDS: 2.º e 3.º fundidos (render p. 4)
        "de Azevedo e Vas- Mendes": [
            "Manuel António de Almeida de Azevedo e Vasconcelos.",
            "João da Silva Mendes.",
        ],
        # Gralhas verificadas nos renders
        "Al António Machado Rodrigues": ["António Machado Rodrigues."],
        "Andrade de Aze- vedo":
            ["Amélia Cavaleiro Monteiro de Andrade de Azevedo."],
        "Parente Men es": ["José Maria Parente Mendes Godinho."],
        "Rui Eduardo Rodrigues Pena": ["Rui Eduardo Ferreira Rodrigues Pena."],
    },
}


def apply_line_fixes(tag, lines):
    """Aplica LINE_FIXES a [(texto, conf), ...].

    Chaves normais casam por substring; chaves com prefixo "^" casam a
    linha inteira (para fragmentos curtos que existem dentro de nomes
    legítimos, ex. "oseta." em "... Salema Roseta.")."""
    fixes = LINE_FIXES.get(tag)
    if not fixes:
        return lines
    out = []
    for txt, conf in lines:
        hit = next((k for k in fixes
                    if (k[1:] == txt if k.startswith("^") else k in txt)), None)
        if hit is not None:
            out.extend((t, 100.0) for t in fixes[hit])
        else:
            out.append((txt, conf))
    return out


# siglas de GCE cuja grafia no mapa difere da usada nos resultados do site
# (verificadas pelos mandatos e pelo contexto do concelho)
SIGLA_ALIASES = {
    (2017, "vsvhsi"): "VS - VHS",          # Vizela Sempre - Victor Hugo Salgado
    (2017, "nmpm"): "Narciso",             # Narciso Miranda Por Matosinhos
    (2017, "aps"): "SIM",                  # Matosinhos
    (2017, "LCF"): "lcfci",                # Lagos Com Futuro
    (2017, "P+"): "pm",                    # Lajes do Pico
    (2013, "+cmg"): "I",                   # Marinha Grande
    (2013, "mpm"): "II",                   # Marinha Grande
    (2013, "mig"): "XIII",                 # Grândola
    (2013, "gm"): "XVIII",                 # Grândola
    (2013, "nv"): "XII",                   # Nazaré
    (2013, "gcicn"): "XIX",                # Nazaré
    (2013, "ppcb"): "I",                   # Belmonte
    (2013, "i-gois"): "I",                 # Góis
    (2013, "ap"): "I",                     # Amares
    (2013, "ipf"): "XVII",                 # Fafe
}


OVERRIDES = {
    # 2021 — mapa oficial 1-B/2021: nas mudanças de página as colunas
    # refluem e nomes saem na coluna da lista vizinha
    (2021, "am", "0202"): [
        # Almodôvar: 12.º nome do PS impresso na coluna PPD/PSD (p. 105)
        ("move_tail", "PPD/PSD", "PS", 1),
    ],
    (2021, "am", "0501"): [
        # Belmonte: 2.º nome do PCP-PEV impresso na coluna PS
        ("move_tail", "PS", "PCP-PEV", 1),
    ],
    (2021, "am", "1606"): [
        # Ponte da Barca: 10.º nome do PS impresso na coluna PPD/PSD;
        # o eleito PCP-PEV não consta do mapa (aviso de nomes em falta)
        ("move_tail", "PPD/PSD", "PS", 1),
    ],
    (2021, "am", "1702"): [
        # Boticas: 3.º nome do I impresso na coluna PPD/PSD (pp. 444)
        ("move_tail", "PPD/PSD", "I", 1),
    ],
    # 2005 — gralhas de sigla no próprio mapa oficial (verificadas no PDF:
    # o nome marginal vem impresso com a sigla da lista vizinha; a distribuição
    # oficial de mandatos (d'Hondt/Globais) é a autoridade)
    (2005, "cm", "0313"): [
        # Vila Verde: mapa imprime 2 PS, oficial é PPD/PSD 6 / PS 1
        ("move_tail", "PS", "PPD/PSD", 1),
    ],
    (2005, "am", "0906"): [
        # Gouveia: mapa imprime PPD/PSD 13; oficial 11 / PS 10 / PCP-PEV 2
        ("move_tail", "PPD/PSD", "PCP-PEV", 1),
        ("move_tail", "PPD/PSD", "PS", 1),
    ],
    (2005, "am", "1005"): [
        # Bombarral: mapa imprime PCP-PEV 3 / CDS-PP 1; oficial 2 / 2
        ("move_tail", "PCP-PEV", "CDS-PP", 1),
    ],
    (2005, "am", "1417"): [
        # Sardoal: mapa imprime PS 6; oficial PPD/PSD 10 / PS 5
        ("move_tail", "PS", "PPD/PSD", 1),
    ],
    (2005, "am", "1421"): [
        # Ourém: mapa imprime CDS-PP 2; oficial CDS-PP 1 / PPD/PSD 12
        ("move_tail", "CDS-PP", "PPD/PSD", 1),
    ],
    (2005, "am", "4203"): [
        # Ponta Delgada: mapa imprime "Lúcia ... B.E."; oficial não dá mandato
        # ao B.E. e dá PS 9
        ("move_tail", "B.E.", "PS", 1),
    ],
    # 2017 — mesmos refluxos de coluna nas quebras de página
    (2017, "cm", "0307"): [
        # Fafe: 2.º nome do PPD/PSD.CDS-PP impresso na coluna FS
        ("move_tail", "FS", "PPD/PSD.CDS-PP", 1),
    ],
    (2017, "am", "0603"): [
        # Coimbra: 13.º nome do PS impresso na coluna PCP-PEV
        ("move_tail", "PCP-PEV", "PS", 1),
    ],
    (2017, "am", "0816"): [
        # Vila Real de Santo António: eleito do B.E. impresso na coluna PPD/PSD
        ("move_tail", "PPD/PSD", "B.E.", 1),
    ],
    (2017, "am", "1009"): [
        # Leiria: 11.º nome do PPD/PSD.MPT impresso na coluna PS
        ("move_tail", "PS", "PPD/PSD.MPT", 1),
    ],
    (2017, "am", "1105"): [
        # Cascais: eleito do PDR.JPP impresso na coluna PAN
        ("move_tail", "PAN", "PDR.JPP", 1),
    ],
    (2017, "am", "1812"): [
        # Penedono: 9.º nome do PPD/PSD impresso na coluna PS
        ("move_tail", "PS", "PPD/PSD", 1),
    ],
    (2021, "am", "1414"): [
        # Rio Maior: o mapa imprime 25 nomes para 21 mandatos, incluindo
        # "André Filipe Ferreira Duarte" em duplicado (pp. 392) — mantêm-se
        # os primeiros 13 PPD/PSD.CDS-PP, 7 PS e 1 PCP-PEV
        ("trim", "PPD/PSD.CDS-PP", 3),
        ("trim", "PS", 1),
    ],
    # 2009 — gralha do mapa oficial (verificada no render da p. 107):
    # o 2.º eleito do CDS-PP da AM de Amares vem impresso na coluna PS
    (2009, "am", "0301"): [
        ("move_tail", "PS", "CDS-PP", 1),
    ],
    # 2013 — column shifts in municipal assemblies
    (2013, "am", "0301"): [
        # Amares: 1 name from AP (canonicalized to I) printed under PPD/PSD.CDS-PP column
        ("move_tail", "I", "PPD/PSD.CDS-PP", 1),
    ],
    (2013, "am", "0307"): [
        # Fafe: 1 name from PPD/PSD printed under IPF (canonicalized to XVII)
        ("move_tail", "PPD/PSD", "XVII", 1),
    ],
    (2013, "am", "0401"): [
        # Alfândega da Fé: 1 name from PPD/PSD.CDS-PP printed under PS
        ("move_tail", "PPD/PSD.CDS-PP", "PS", 1),
    ],
    (2013, "am", "1214"): [
        # Portalegre: 1 name from PPD/PSD.CDS-PP printed under PCP-PEV
        ("move_tail", "PPD/PSD.CDS-PP", "PCP - PEV", 1),
    ],
    (2013, "am", "1418"): [
        # Tomar: 1 name from PPD/PSD printed under CDS-PP
        ("move_tail", "PPD/PSD", "CDS-PP", 1),
    ],
    (2013, "am", "1607"): [
        # Ponte de Lima: 1 name from CDS-PP printed under PCP-PEV
        ("move_tail", "CDS-PP", "PCP - PEV", 1),
    ],
    (2013, "am", "3101"): [
        # Calheta: 1 name from CDS-PP printed under PPD/PSD
        ("move_tail", "CDS-PP", "PPD/PSD", 1),
    ],
    (2013, "am", "1505"): [
        # Grândola: the official map printed 5 names for GM (XVIII) which only elected 3
        ("trim", "XVIII", 2),
    ],
    (2009, "af", "031108"): [
        # Guilhofrei: "Manuel Joaquim Carneiro Gonçalves" duplicated in PS and PPD/PSD.CDS-PP
        ("replace_name", "PPD/PSD.CDS-PP", "Manuel Joaquim Carneiro Gonçalves", "Manuel Joaquim Carneiro Gonçalves ")
    ],
    (2009, "af", "071301"): [
        # Alcáçovas: OCR errors in PCP-PEV names (0 instead of o)
        ("replace_name", "PCP-PEV", "Carméni0 Sim Sim M0ncarcha", "Carménio Sim Sim Moncarcha"),
        ("replace_name", "PCP-PEV", "Mári0 Gonçalo Louro Grave", "Mário Gonçalo Louro Grave")
    ],
}


def apply_sigla_aliases(year, listas):
    for l in listas:
        alias = SIGLA_ALIASES.get((int(year), l["sigla"])) or SIGLA_ALIASES.get((int(year), l["sigla"].lower()))
        if alias:
            l.setdefault("sigla_dr", l["sigla"])
            l["sigla"] = alias
    return listas


def apply_overrides(year, subtype, code, listas):
    ops = OVERRIDES.get((int(year), subtype, code))
    if not ops:
        return listas
    by = {l["sigla"]: l for l in listas}
    for op in ops:
        if op[0] == "move_tail":
            _, de, para, n = op
            src = by.get(de)
            if not src or len(src["eleitos"]) < n:
                continue
            moved = src["eleitos"][-n:]
            src["eleitos"] = src["eleitos"][:-n]
            if para in by:
                by[para]["eleitos"].extend(moved)
            else:
                nova = {"sigla": para, "eleitos": moved}
                listas.append(nova)
                by[para] = nova
        elif op[0] == "trim":
            _, sigla, n = op
            src = by.get(sigla)
            if src and len(src["eleitos"]) > n:
                src["eleitos"] = src["eleitos"][:-n]
        elif op[0] == "replace_name":
            _, sigla, de, para = op
            src = by.get(sigla)
            if src:
                src["eleitos"] = [para if x == de else x for x in src["eleitos"]]
    return [l for l in listas if l["eleitos"]]
