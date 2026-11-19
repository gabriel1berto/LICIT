#!/usr/bin/env python3
"""
filtro_informatica.py — Classifica ITEM de edital (descrição do item no PNCP) em
categoria de informática e diz se o catálogo GET cobre.

Vertical Informática (19/nov/2026): radar de editais abertos/futuros com foco em
fornecimento 100% GET (ex-Goldentec, fábrica em Fortaleza). Catálogo GET lido de
https://app.ibyte.com.br/get-catalog/ em 19/nov/2026 (718 SKUs, marcas GET/TCN/OX/GT).

Regra de categoria: ganha o termo que aparece PRIMEIRO na descrição — descrição do
PNCP começa pelo substantivo do produto ("COMPUTADOR ... com teclado e mouse" é
computador; "TECLADO ... para computador" é teclado). Ordem fixa só desempata.

Cobertura GET, 3 valores:
  - "sim": linha existe no catálogo e a especificação extraída cabe nela.
  - "talvez": linha existe, mas a spec varia demais pra confirmar só pela descrição
    (computador, tablet) ou a descrição não traz o número (nobreak sem VA, monitor
    sem polegada).
  - "nao": GET não fabrica (notebook, impressora, webcam, estabilizador) ou spec fora
    da linha (nobreak > 3kVA, monitor > 27").
Heurística por texto — nunca confirma TR/anexo. Casos reais em test_filtro_informatica.py.
"""

import html
import re
import unicodedata

_F = re.IGNORECASE


def _norm(s: str | None) -> str:
    # descrição do PNCP às vezes vem com HTML do sistema de origem (<p><strong>, &aacute;)
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


# Serviço/insumo/acessório ou equipamento de outra área que usa o mesmo nome.
_EXCLUI = re.compile(
    r"\bservico|\bmanutencao|\blocacao|\baluguel|\bconserto|\breparo|\boutsourcing|\binstalacao de"
    r"|\btoner|\bcartucho|\btinta\b|\bcilindro|\bfusor|\bbateria (para|p/|de) (no.?break|nobreak)|\bbaterias? selada"
    r"|multiparam|sinais vitais|cardiac|fetal|oximetr|pressao arterial|hospitalar|paciente|\becg\b|desfibril"
    r"|glicose|glicemi|holter|\bmapa\b|cardiotoc|\buti\b|anestesi|uso medico|cirurgi|mamograf|optotipo"
    r"|teclado (musical|arranjador|eletronico)|\bpiano"
    r"|suporte (para|p/|de) (monitor|projetor|tv)|\btela de projecao|\btela retratil|\bcabo\b|\bcapa\b|\bpelicula"
    r"|\bmouse ?pad|\blampada (para|p/|de) projetor|\bcontrole remoto",
    _F,
)

# Descrição que COMEÇA com acessório/componente nunca é o equipamento em si
# ("SUPORTE: ... PARA TVS, MONITORES", "Bateria estacionária ... para nobreak").
_EXCLUI_INICIO = re.compile(r"^\W*(suporte|bateria|cabo|gabinete|fonte (?!de alimentacao ininterrupta|alimentacao ininterrupta)|"
                            r"adaptador|carregador|capa|pelicula|mochila|bolsa)\b", _F)

# Termo de categoria só vale no COMEÇO da descrição (achado 19/nov/2026, 1ª coleta):
# "Autoclave ... com impressora", "Aparelho Ultrassonografia ... teclado" — o
# substantivo do produto vem primeiro; termo de informática no meio do texto é
# acessório/componente de outra coisa.
JANELA_INICIO = 50

CATEGORIAS = [
    ("Nobreak", r"\bno.?break|\bups\b|\bfonte (de )?alimentacao ininterrupta"),
    ("Estabilizador", r"\bestabilizador"),
    ("Notebook", r"\bcomputador portatil|\bnotebook|\bnetbook|\bchromebook|\blaptop|\bultrabook"),
    ("Tablet", r"\btablet"),
    ("Impressora", r"\bimpressora|\bmultifuncional"),
    ("Projetor", r"\bprojetor|\bdata.?show"),
    ("Webcam", r"\bweb.?cam|\bcamera (de )?videoconferencia|\bcamera (para|p/) (computador|web)"),
    ("Headset/Fone", r"\bheadset|\bheadphone|\bfones? (de )?ouvido|\bfone (com|c/) microfone|\bauricular"),
    ("Caixa de som", r"\bcaixas? de som|\bcaixas? acustica|\bsoundbar"),
    ("Teclado/Mouse", r"\bteclado|\bmouse\b"),
    ("Monitor", r"\bmonitor\b|\bmonitores\b"),
    ("Armazenamento", r"\bssd\b|\bmemoria portatil|\bmemoria ram|\bmemoria (ddr|do tipo ddr)|\bpen.?drive|\bcartao de memoria|\bmicro.?sd"),
    ("Computador", r"\bcomputador(es)?\b|\bmicrocomputador|\bdesktop|\ball.?in.?one|\bestacao de trabalho|\bmini ?pc\b|\bcpu\b"),
]
_CATS = [(nome, re.compile(p, _F)) for nome, p in CATEGORIAS]

# Linhas sem nenhum produto GET (catálogo 19/nov/2026).
_SEM_GET = {"Notebook", "Impressora", "Webcam", "Estabilizador"}
# Linhas GET com spec muito variável — só a leitura do TR confirma.
_TALVEZ = {"Computador", "Tablet"}

# GET: nobreak 600-3000VA (8 SKUs), monitor 15-27".
NOBREAK_MAX_VA = 3000
MONITOR_POL_MIN, MONITOR_POL_MAX = 15.0, 27.0

_RE_VA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k?)\s*va\b", _F)
_RE_POL = re.compile(
    r"(\d{2}(?:[.,]\d)?)\s*(?:\"|''|”|pol\b|pol\.|polegadas?|inch)"
    r"|tamanho (?:da )?tela:?\s*(\d{2}(?:[.,]\d)?)",
    _F,
)
# Caixa de som GET é de computador/BT pequena — amplificada/karaokê/MDF não é linha dela.
_RE_CAIXA_PC = re.compile(r"computador|\bpc\b|\busb\b|multimidia|\b2\.0\b", _F)


def categoria_item(descricao: str | None) -> str | None:
    """Categoria de informática do item, ou None (não é informática / é serviço ou acessório)."""
    texto = _norm(descricao)
    if not texto or _EXCLUI.search(texto) or _EXCLUI_INICIO.search(texto):
        return None
    inicio = texto[:JANELA_INICIO]
    achados = [(m.start(), i, nome) for i, (nome, rx) in enumerate(_CATS) if (m := rx.search(inicio))]
    if not achados:
        return None
    return min(achados)[2]


def _num_br(num: str) -> float:
    """'1,2' -> 1.2 · '2.200' -> 2200 · '1.5' -> 1.5"""
    if "," in num:
        return float(num.replace(".", "").replace(",", "."))
    if "." in num and len(num.split(".")[-1]) == 3:
        return float(num.replace(".", ""))
    return float(num)


# Primeiro número citado = mínimo exigido ("tamanho tela: 23 a 30", "mínima 1500 VA").
def _primeiro_va(texto: str) -> float | None:
    for num, k in _RE_VA.findall(texto):
        return _num_br(num) * (1000 if k else 1)
    return None


def _polegadas(texto: str) -> float | None:
    for a, b in _RE_POL.findall(texto):
        v = float((a or b).replace(",", "."))
        if 10 <= v <= 100:
            return v
    return None


def cobertura_get(categoria: str | None, descricao: str | None) -> str | None:
    """'sim' | 'talvez' | 'nao' | None (item não é informática)."""
    if categoria is None:
        return None
    if categoria in _SEM_GET:
        return "nao"
    if categoria in _TALVEZ:
        return "talvez"
    texto = _norm(descricao)
    if categoria == "Nobreak":
        va = _primeiro_va(texto)
        if va is None:
            return "talvez"
        return "sim" if va <= NOBREAK_MAX_VA else "nao"
    if categoria == "Monitor":
        pol = _polegadas(texto)
        if pol is None:
            return "talvez"
        return "sim" if MONITOR_POL_MIN <= pol <= MONITOR_POL_MAX else "nao"
    if categoria == "Caixa de som":
        return "sim" if _RE_CAIXA_PC.search(texto) else "talvez"
    return "sim"


def classificar_item(descricao: str | None) -> tuple[str | None, str | None]:
    cat = categoria_item(descricao)
    return cat, cobertura_get(cat, descricao)


def selo_get(coberturas: list[str]) -> str:
    """Selo do edital a partir da cobertura dos itens de informática dele."""
    cob = [c for c in coberturas if c]
    if not cob:
        return "Sem item de informática"
    if all(c in ("sim", "talvez") for c in cob):
        return "100% GET"
    if any(c in ("sim", "talvez") for c in cob):
        return "Parcial GET"
    return "Fora da GET"
