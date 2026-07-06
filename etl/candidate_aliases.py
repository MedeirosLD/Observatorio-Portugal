# -*- coding: utf-8 -*-
"""Aliases de candidatos presidenciais (PR).

As planilhas oficiais trazem os nomes dos candidatos com mojibake (acentos
perdidos: `OCT�VIO PATO`, `Jo�o Ferreira`). Mapeamos o *slug* do cabeçalho bruto
(maiúsculas, sem acentos, sem `�`, só A-Z0-9) para o nome canónico, a cor (herdada
do partido de apoio) e a etiqueta de partido mostrada no painel.

O slug é calculado por `slugify_candidate()` — a mesma normalização deve ser
aplicada ao cabeçalho bruto lido do Excel.
"""
import re
import unicodedata


def slugify_candidate(raw):
    """`OCT�VIO PATO` / `Octávio Pato` -> comparação robusta.

    NFKD + remove diacríticos + upper; o U+FFFD (`�`) e restantes não-alfanuméricos
    são removidos. Nota: nomes com mojibake perdem a letra acentuada (é->�->''),
    por isso as chaves abaixo refletem o slug do *bruto com mojibake*."""
    if raw is None:
        return ""
    s = unicodedata.normalize("NFKD", str(raw))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s.upper())


# Cores herdadas do partido de apoio (reutilizam a paleta de globals.js).
_PS = "#e75294"        # PS (rosa)
_PS_ADJ = "#b5478a"    # independentes de área PS (Alegre, Ana Gomes, Sampaio da Nóvoa)
_PSD = "#ff8000"       # PSD (laranja)
_AD80 = "#2950bc"      # AD 1980 (azul)
_CDS = "#0069b4"       # CDS (azul)
_CDU = "#d40000"       # PCP/CDU (vermelho)
_BE = "#b4004e"        # Bloco de Esquerda
_CH = "#202a5e"        # Chega
_IL = "#00b6c7"        # Iniciativa Liberal
_MRPP = "#8b0000"      # PCTP/MRPP
_PSR = "#c81e5a"       # PSR
_PRD = "#216b31"       # PRD (Salgado Zenha 1986)
_UDP = "#7e0f0f"       # UDP / extrema-esquerda (Otelo)
_IND = "#6b8e9e"       # independente (azul-aço)
_IND2 = "#8a6d3b"      # independente (castanho)
_IND3 = "#5a6b7a"      # independente (cinza-azulado)
_GRN = "#0f7d64"       # verde/ambiental-humanista
_FARRIGHT = "#333a8c"  # extrema-direita
_YEL = "#f9b000"       # Vitorino Silva (RIR / independente)
_MAS = "#cc0033"       # MAS
_L = "#3fbf77"         # Livre


# slug -> (nome canónico, cor, etiqueta de partido)
CANDIDATES = {
    # 1976
    "RAMALHOEANES":            ("António Ramalho Eanes", _IND, "Independente"),
    "PINHEIRODEAZEVEDO":       ("José Pinheiro de Azevedo", _IND2, "Independente"),
    "OCTAVIOPATO":              ("Octávio Pato", _CDU, "PCP"),
    "OTELOSARAIVADECARVALHO":  ("Otelo Saraiva de Carvalho", _UDP, "Independente"),
    # 1980
    "SOARESCARNEIRO":          ("António Soares Carneiro", _AD80, "AD (PSD/CDS/PPM)"),
    "PIRESVELOSO":             ("António Pires Veloso", _IND2, "Independente"),
    "GALVAOMELO":               ("Carlos Galvão de Melo", _FARRIGHT, "Independente"),
    "ANTONIOAIRESRODRIGUES":    ("António Aires Rodrigues", _IND3, "Independente"),
    # 1986
    "SALGADOZENHA":            ("Francisco Salgado Zenha", _PRD, "Independente"),
    "LURDESPINTASILGO":        ("Maria de Lourdes Pintasilgo", _GRN, "Independente"),
    "FREITASDOAMARAL":         ("Diogo Freitas do Amaral", _CDS, "CDS"),
    "MARIOSOARES":              ("Mário Soares", _PS, "PS"),
    # 1991
    "BASILIOHORTA":             ("Basílio Horta", _CDS, "CDS"),
    "CARLOSCARVALHAS":         ("Carlos Carvalhas", _CDU, "CDU (PCP-PEV)"),
    "CARLOSMARQUES":           ("Carlos Marques", _PSR, "PSR"),
    # 1996
    "CAVACOSILVA":             ("Aníbal Cavaco Silva", _PSD, "PSD"),
    "JORGESAMPAIO":            ("Jorge Sampaio", _PS, "PS"),
    # 2001
    "GARCIAPEREIRA":           ("António Garcia Pereira", _MRPP, "PCTP/MRPP"),
    "FERREIRADOAMARAL":        ("Joaquim Ferreira do Amaral", _PSD, "PSD"),
    "FERNANDOROSAS":           ("Fernando Rosas", _BE, "BE"),
    "ANTONIOABREU":             ("António Abreu", _CDU, "CDU (PCP-PEV)"),
    # 2006
    "FRANCISCOLOUCA":            ("Francisco Louçã", _BE, "BE"),
    "MANUELALEGRE":            ("Manuel Alegre", _PS_ADJ, "Independente"),
    "JERONIMOSOUSA":            ("Jerónimo de Sousa", _CDU, "CDU (PCP-PEV)"),
    # 2011
    "DEFENSORMOURA":           ("Defensor Moura", _PS_ADJ, "Independente"),
    "FRANCISCOLOPES":          ("Francisco Lopes", _CDU, "CDU (PCP-PEV)"),
    "JOSECOELHO":               ("José Manuel Coelho", _YEL, "PTP"),
    "FERNANDONOBRE":           ("Fernando Nobre", _GRN, "Independente"),
    # 2016
    "HENRIQUENETO":            ("Henrique Neto", _IND, "Independente"),
    "SAMPAIODANOVOA":           ("António Sampaio da Nóvoa", _PS_ADJ, "Independente"),
    "CANDIDOFERREIRA":          ("Cândido Ferreira", _IND3, "Independente"),
    "EDGARSILVA":              ("Edgar Silva", _CDU, "CDU (PCP-PEV)"),
    "JORGESEQUEIRA":           ("Jorge Sequeira", "#7a8699", "Independente"),
    "VITORINOSILVA":           ("Vitorino Silva", _YEL, "RIR"),
    "MARISAMATIAS":            ("Marisa Matias", _BE, "BE"),
    "MARIADEBELEM":             ("Maria de Belém Roseira", _PS, "Independente"),
    "MARCELOREBELODESOUSA":    ("Marcelo Rebelo de Sousa", _PSD, "PSD"),
    "PAULODEMORAIS":           ("Paulo de Morais", "#3a7d44", "Independente"),
    # 2021
    "TIAGOMAYANGONCALVES":      ("Tiago Mayan Gonçalves", _IL, "IL"),
    "ANDREVENTURA":             ("André Ventura", _CH, "Chega"),
    "JOAOFERREIRA":             ("João Ferreira", _CDU, "CDU (PCP-PEV)"),
    "ANAGOMES":                ("Ana Gomes", _PS_ADJ, "Independente"),
    # 2026
    "ANDREPESTANADASILVA":     ("André Pestana da Silva", _MAS, "Independente"),
    "ANDREVENTURA":            ("André Ventura", _CH, "Chega"),
    "ANTONIOFILIPE":           ("António Filipe", _CDU, "CDU (PCP-PEV)"),
    "ANTONIOJOSESEGURO":       ("António José Seguro", _PS, "PS"),
    "CATARINAMARTINS":         ("Catarina Martins", _BE, "BE"),
    "HENRIQUEGOUVEIAEMELO":    ("Henrique Gouveia e Melo", _IND, "Independente"),
    "HUMBERTOCORREIA":         ("Humberto Correia", _IND2, "Independente"),
    "JORGEPINTO":              ("Jorge Pinto", _L, "Independente"),
    "JOAOCOTRIMDEFIGUEIREDO":  ("João Cotrim de Figueiredo", _IL, "IL"),
    "LUISMARQUESMENDES":       ("Luís Marques Mendes", _PSD, "PSD"),
    "MANUELJOAOVIEIRA":        ("Manuel João Vieira", _YEL, "Independente"),
}

DEFAULT_CANDIDATE_COLOR = "#7a8699"


def resolve_candidate(raw):
    """Devolve (nome, cor, partido) para um cabeçalho bruto de candidato."""
    slug = slugify_candidate(raw)
    if slug in CANDIDATES:
        return CANDIDATES[slug]
    # fallback: título simples do nome bruto (sem mojibake removido corretamente)
    clean = re.sub(r"\s+", " ", str(raw).replace("\ufffd", "").strip()).title()
    return (clean or slug or "?", DEFAULT_CANDIDATE_COLOR, "")
