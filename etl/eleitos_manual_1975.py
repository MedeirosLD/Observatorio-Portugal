# -*- coding: utf-8 -*-
"""Eleitos da Assembleia Constituinte (25-4-1975).

Transcrição manual verificada visualmente contra o scan do mapa nacional
(Diário do Governo, II Série, n.º 115 — resultados_ac_1975.pdf): o OCR do
scan é demasiado degradado para parsing automático (cabeçalhos de círculo
ilegíveis), pelo que a lista foi lida página a página dos renders a 300 dpi.

Estrutura: [(círculo impresso, [(nome do partido impresso, [nomes]), ...])].
As siglas e códigos de círculo são resolvidos por build_eleitos_ar.py com
os mesmos mapas dos restantes anos (PARTY_NAME_TO_SIGLA, circulo_code).
"""

ELEITOS_1975 = [
    ("Aveiro (14)", [
        ("Partido Popular Democrático (7)", [
            "Sebastião Dias Marques",
            "José Manuel Afonso Gomes de Almeida",
            "José Ângelo Ferreira Correia",
            "Arnaldo Ângelo de Brito Lhamas",
            "António Júlio Correia Teixeira da Silva",
            "Carlos Alberto Branco de Seiça Neves",
            "Antídio das Neves Costa",
        ]),
        ("Partido Socialista (5)", [
            "Carlos Manuel Natividade da Costa Candal",
            "Mário Manuel Cal Brandão",
            "Alcides Strecht Monteiro",
            "Manuel Ferreira dos Santos Pato",
            "José Fernando Silva Lopes",
        ]),
        ("Centro Democrático Social (2)", [
            "Silvério Martins da Silva",
            "Maria José Paulo Sampaio",
        ]),
    ]),
    ("Beja (6)", [
        ("Partido Comunista Português (3)", [
            "Francisco Miguel Duarte",
            "João António Honrado",
            "Fernanda Peleja Patrício",
        ]),
        ("Partido Socialista (3)", [
            "António Pope Lopes Cardoso",
            "Raquel Júdice de Oliveira Howell Franco",
            "Luís Abílio da Conceição Cacito",
        ]),
    ]),
    ("Braga (15)", [
        ("Partido Popular Democrático (7)", [
            "Jorge Manuel Moura Loureiro de Miranda",
            "Fernando Alberto Matos Ribeiro da Silva",
            "Fernando José Sequeira Roriz",
            "Armando António Correia",
            "Nívea Adelaide Pereira e Cruz",
            "Carlos Francisco Cerejeira Pereira Bacelar",
            "João Baptista Machado",
        ]),
        ("Centro Democrático Social (3)", [
            "Adelino Manuel Lopes Amaro da Costa",
            "Francisco Luís de Sá Malheiro",
            "Manuel José Gonçalves Soares",
        ]),
        ("Partido Socialista (5)", [
            "Armando Filipe Cerejeira Pereira Bacelar",
            "Francisco Xavier Sampaio Tinoco de Faria",
            "António Alberto Correia Mota Prego de Faria",
            "Adelino Augusto Miranda de Andrade",
            "Jerónimo da Silva Pereira",
        ]),
    ]),
    ("Bragança (4)", [
        ("Partido Popular Democrático (3)", [
            "Jorge de Carvalho Sá Borges",
            "Manuel da Costa Andrade",
            "António Maria Lopes Ruano",
        ]),
        ("Partido Socialista (1)", [
            "Raul de Assunção Pimenta Rego",
        ]),
    ]),
    ("Castelo Branco (7)", [
        ("Partido Socialista (5)", [
            "Manuel João Vieira",
            "Alfredo Pinto da Silva",
            "Júlio Pereira dos Reis",
            "Mário de Deus Branco",
            "Francisco Carlos Ferreira",
        ]),
        ("Partido Popular Democrático (2)", [
            "Alfredo Joaquim da Silva Morgado",
            "Pedro Manuel Cruz Roseta",
        ]),
    ]),
    ("Coimbra (12)", [
        ("Partido Socialista (7)", [
            "Henrique Teixeira Queirós de Barros",
            "Manuel Alegre de Melo Duarte",
            "António Carlos Ribeiro Campos",
            "António Duarte Arnaut",
            "Vítor Manuel Brás",
            "Manuel Francisco da Costa",
            "Joaquim Antero Romero Magalhães",
        ]),
        ("Partido Popular Democrático (4)", [
            "Carlos Alberto Mota Pinto",
            "António Moreira Barbosa de Melo",
            "Luís Argel de Melo e Silva Biscaia",
            "João António Martelo de Oliveira",
        ]),
        ("Partido Comunista Português (1)", [
            "Fernando Augusto da Silva Blanqui Teixeira",
        ]),
    ]),
    ("Évora (5)", [
        ("Partido Comunista Português (2)", [
            "Dinis Fernandes Miranda",
            "Manuel Mendes Nobre Gusmão",
        ]),
        ("Partido Socialista (3)", [
            "Pedro Amadeu de Albuquerque Santos Coelho",
            "Etelvina Lopes de Almeida",
            "Joaquim Laranjeira Penderlico",
        ]),
    ]),
    ("Faro (9)", [
        ("Partido Socialista (6)", [
            "Luís Filipe Nascimento Madeira",
            "Emídio Pedro Águedo Serrano",
            "António José Sanches Esteves",
            "Eurico Manuel das Neves Henriques Mendes",
            "Eurico Faustino Correia",
            "Manuel Ferreira Ponteiro",
        ]),
        ("Partido Popular Democrático (1)", [
            "Cristóvão Guerreiro Norte",
        ]),
        ("Partido Comunista Português (1)", [
            "Carlos Alfredo de Brito",
        ]),
        ("Movimento Democrático Português (1)", [
            "Luís Manuel Alves de Campos Catarino",
        ]),
    ]),
    ("Guarda (6)", [
        ("Centro Democrático Social (1)", [
            "Emílio Leitão Paulo",
        ]),
        ("Partido Popular Democrático (3)", [
            "José António Valério do Couto",
            "António Júlio Simões de Aguiar",
            "Mário José Pimentel Saraiva Salvado",
        ]),
        ("Partido Socialista (2)", [
            "João Pedro Miller de Lemos Guerra",
            "Maria Helena Carvalho dos Santos Oliveira Lopes",
        ]),
    ]),
    ("Leiria (11)", [
        ("Partido Popular Democrático (5)", [
            "José Ferreira Júnior",
            "Tomás Duarte da Câmara Oliveira Dias",
            "Abílio de Freitas Lourenço",
            "José Gonçalves Sapinho",
            "João Manuel Ferreira",
        ]),
        ("Partido Socialista (5)", [
            "Joaquim Jorge de Pinho Campinos",
            "António Jorge Oliveira Aires Rodrigues",
            "Luís Maria Kalidas Costa Barreto",
            "Vasco da Gama Lopes Fernandes",
            "Amílcar de Pinho",
        ]),
        ("Centro Democrático Social (1)", [
            "Francisco Manuel Lopes Vieira de Oliveira Dias",
        ]),
    ]),
    ("Lisboa (55)", [
        ("Partido Socialista (29)", [
            "Mário Alberto Nobre Lopes Soares",
            "José Maria Barbosa de Magalhães Godinho",
            "Mário Augusto Sottomayor Leal Cardia",
            "Francisco Manuel Marcelo Monteiro Curto",
            "Alfredo Fernando de Carvalho",
            "Florival da Silva Nobre",
            "Mário António da Mota Mesquita",
            "José Manuel de Medeiros Ferreira",
            "Maria Teresa do Vale de Matos Madeira Vidigal",
            "Alberto Arons Braga de Carvalho",
            "Amarino Peralta Sabino",
            "Aquilino Ribeiro Machado",
            "Carlos Alberto Leitão Marques",
            "João Joaquim Gomes",
            "José Alberto Menano Cardoso do Amaral",
            "Teófilo Carvalho dos Santos",
            "José Alfredo Pimenta de Sousa Monteiro",
            "Carlos Alberto Andrade Neves",
            "Vasco Francisco do Rosário Moniz",
            "Luís Giordano dos Santos Covas",
            "Carmelinda Maria dos Santos Pereira",
            "Alberto Manuel Avelino",
            "Jorge Henrique das Dores Ramos",
            "Francisco Igrejas Caeiro",
            "Gualter Viriato Nunes Basílio",
            "Armando Assunção Soares",
            "Nuno Maria Monteiro Godinho de Matos",
            "Mário de Castro Pina Correia",
            "Rui António Ferreira da Cunha",
        ]),
        ("Partido Comunista Português (11)", [
            "Álvaro Barreirinhas Cunhal",
            "Octávio Floriano Rodrigues Pato",
            "Jaime dos Santos Serra",
            "José Alves Tavares Magro",
            "Georgette de Oliveira Ferreira",
            "Maria Alda Barbosa Nogueira",
            "José Pedro Correia Soares",
            "Adriano Lopes da Fonseca",
            "Jerónimo Carvalho de Sousa",
            "Eugénio de Jesus Domingues",
            "José Pinheiro Lopes de Almeida",
        ]),
        ("Partido Popular Democrático (9)", [
            "Joaquim Jorge Magalhães Saraiva da Mota",
            "Francisco José Pereira Pinto Balsemão",
            "Nuno Aires Rodrigues dos Santos",
            "Artur Videira Pinto Cunha Leal",
            "José Manuel Nogueira Ramos",
            "Marcelo Nuno Duarte Rebelo de Sousa",
            "Alfredo António de Sousa",
            "Maria Helena do Rego da Costa Salema Roseta",
            "Mário Fernando de Campos Pinto",
        ]),
        ("Centro Democrático Social (3)", [
            "Diogo Pinto de Freitas do Amaral",
            "Vítor António Augusto Nunes de Sá Machado",
            "Basílio Adolfo de Mendonça Horta da França",
        ]),
        ("Movimento Democrático Português (2)", [
            "Francisco José Cruz Pereira de Moura",
            "José Manuel Marques do Carmo Mendes Tengarrinha",
        ]),
        ("União Democrática Popular (1)", [
            "João Carneiro de Moura Pulido Valente",
        ]),
    ]),
    ("Porto (36)", [
        ("Partido Socialista (18)", [
            "António Cândido Miranda Macedo",
            "Francisco de Almeida Salgado Zenha",
            "Sofia de Melo Breyner Andresen de Sousa Tavares",
            "José Luís do Amaral Nunes",
            "Carlos Cardoso Laje",
            "Rui Manuel Polónio de Sampaio",
            "Alberto Augusto Martins da Silva Andrade",
            "Manuel Joaquim de Paiva Pereira Pires",
            "Maria Emília de Melo Moreira da Silva",
            "António José de Sousa Pereira",
            "Rui Maria Malheiro de Távora de Castro Feijó",
            "Manuel de Brito de Figueiredo Canijo",
            "Laura da Conceição Barraché Cardoso",
            "Manuel de Sousa Ramos",
            "Adelino Teixeira de Carvalho",
            "Bento Elísio de Azevedo",
            "Eurico Telmo de Campos",
            "António Fernandes Areias",
        ]),
        ("Partido Popular Democrático (12)", [
            "Francisco Manuel Lumbrales Sá Carneiro",
            "Emídio Guerreiro",
            "Miguel Luís Kolback Veiga",
            "Artur Morgado Ferreira Santos Silva",
            "Amélia Cavaleiro Monteiro de Andrade de Azevedo",
            "Olívio da Silva França",
            "José Augusto Baptista Lopes Seabra",
            "José Bento Gonçalves",
            "Vasco Navarro da Graça Moura",
            "Joaquim Coelho dos Santos",
            "Eduardo José Vieira",
            "Manuel Coelho Moreira",
        ]),
        ("Centro Democrático Social (3)", [
            "Manuel Januário Soares Ferreira Rosa",
            "António Francisco de Almeida",
            "Manuel Raimundo Ferreira dos Santos Pires de Morais",
        ]),
        ("Partido Comunista Português (2)", [
            "Ângelo Matos Mendes Veloso",
            "José Carlos",
        ]),
        ("Movimento Democrático Português (1)", [
            "Manuel Domingos de Sousa Pereira",
        ]),
    ]),
    ("Portalegre (4)", [
        ("Partido Socialista (3)", [
            "Júlio Francisco Miranda Calha",
            "Domingos do Carmo Pires Pereira",
            "João do Rosário Barrento Henriques",
        ]),
        ("Partido Comunista Português (1)", [
            "António Joaquim Gervásio",
        ]),
    ]),
    ("Santarém (13)", [
        ("Partido Socialista (8)", [
            "António Fernando Marques Ribeiro Reis",
            "José Manuel Nisa Antunes Mendes",
            "Manuel Pereira Dias",
            "Rui Manuel Mendonça Cordeiro",
            "Pedro Manuel Natal da Cruz",
            "Ladislau Teles Botas",
            "Luís Patrício Rosado Gonçalves",
            "Vitorino Vieira Dias",
        ]),
        ("Partido Popular Democrático (3)", [
            "Joaquim da Silva Lourenço",
            "José António Nunes Furtado Fernandes",
            "Leonardo Eugénio Ribeiro de Almeida",
        ]),
        ("Partido Comunista Português (2)", [
            "Pedro dos Santos Soares",
            "António Malaquias Abalada",
        ]),
    ]),
    ("Setúbal (16)", [
        ("Partido Comunista Português (7)", [
            "António Dias Lourenço da Silva",
            "Américo Lázaro Leal",
            "José Manuel Maia Nunes de Almeida",
            "António Branco Marcos dos Santos",
            "Hermenegilda Rosa Camolas Pacheco",
            "José Manuel Marques Figueiredo",
            "Fernando dos Santos Pais",
        ]),
        ("Movimento Democrático Português (1)", [
            "Álvaro Ribeiro Monteiro",
        ]),
        ("Partido Socialista (7)", [
            "António Pereira Rodrigues",
            "Alberto Marques Antunes",
            "Fernando José Capelo Mendes",
            "Afonso do Carmo",
            "Manuel da Mata de Cáceres",
            "Artur Cortês Pereira dos Santos",
            "Maria da Assunção Viegas Vitorino",
        ]),
        ("Partido Popular Democrático (1)", [
            "Eduardo Bastos Albarran",
        ]),
    ]),
    ("Viana do Castelo (6)", [
        ("Partido Popular Democrático (3)", [
            "António Joaquim da Silva Amado Leite de Castro",
            "Abel Augusto Carneiro",
            "António Roleira Marinho",
        ]),
        ("Partido Socialista (2)", [
            "Alberto Marques de Oliveira e Silva",
            "Manuel Alfredo Tito de Morais",
        ]),
        ("Centro Democrático Social (1)", [
            "António Pereira de Castro Norton de Matos",
        ]),
    ]),
    ("Vila Real (6)", [
        ("Partido Popular Democrático (4)", [
            "Carlos Matos Chaves de Macedo",
            "Amândio Anes de Azevedo",
            "Fernando Adriano Pinto",
            "Orlandino de Abreu Teixeira Varejão",
        ]),
        ("Partido Socialista (2)", [
            "Luís da Silva Lopes Roseira",
            "António José Gomes Teles Grilo",
        ]),
    ]),
    ("Viseu (10)", [
        ("Partido Popular Democrático (6)", [
            "Fernando Monteiro do Amaral",
            "José Francisco Lopes",
            "Carlos Alberto Coelho de Sousa",
            "Vítor Manuel Freire Boga",
            "Maria Augusta da Silva Simões",
            "Nuno Guimarães Taveira da Gama",
        ]),
        ("Partido Socialista (2)", [
            "João Alfredo Félix Vieira de Lima",
            "Álvaro Monteiro",
        ]),
        ("Centro Democrático Social (2)", [
            "Carlos Galvão de Melo",
            "António Pais Pereira",
        ]),
    ]),
    ("Angra do Heroísmo (2)", [
        ("Partido Popular Democrático (2)", [
            "José Manuel Costa Bettencourt",
            "Rúben José de Almeida Martins Raposo",
        ]),
    ]),
    ("Horta (1)", [
        ("Partido Popular Democrático (1)", [
            "Germano da Silva Domingos",
        ]),
    ]),
    ("Ponta Delgada (3)", [
        ("Partido Popular Democrático (2)", [
            "João Bosco Soares Mota Amaral",
            "Américo Natalino Pereira de Viveiros",
        ]),
        ("Partido Socialista (1)", [
            "Jaime José Matos da Gama",
        ]),
    ]),
    ("Funchal (6)", [
        ("Partido Popular Democrático (5)", [
            "José António Camacho",
            "Emanuel Nascimento dos Santos Rodrigues",
            "Maria Élia Mendes Brito Câmara",
            "José Carlos Rodrigues",
            "António Cândido Jácome de Castro Varela",
        ]),
        ("Partido Socialista (1)", [
            "António Alberto Monteiro de Aguiar",
        ]),
    ]),
    ("Macau (1)", [
        ("ADIM (1)", [
            "Diamantino de Oliveira Ferreira",
        ]),
    ]),
    ("Moçambique (1)", [
        ("Partido Socialista (1)", [
            "Rosa Maria Antunes Rainho",
        ]),
    ]),
    ("Emigração (1)", [
        ("Partido Popular Democrático (1)", [
            "José Teodoro de Jesus da Silva",
        ]),
    ]),
]

# O mapa inclui ainda uma secção "Substituição de candidatos eleitos"
# (por opção por função incompatível, etc.). Tal como nos restantes anos,
# a lista acima é a dos CANDIDATOS ELEITOS; as substituições posteriores
# não alteram a lista de eleitos publicada.

