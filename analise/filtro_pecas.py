#!/usr/bin/env python3
"""
filtro_pecas.py — Classifica o OBJETO do edital (título + descrição) como peça
automotiva, serviço de oficina ou nenhum dos dois.

Por que existe (achado 05/out/2026): a busca do PNCP casa o termo dentro dos itens e
anexos, não no objeto. De 140 editais abertos pra "Amortecedor", só 27 eram
automotivos — o resto era amortecedor de gaveta (móvel planejado), piso amortecedor de
playground, cama hospitalar, material esportivo. O termo de busca sozinho não diz nada
sobre o edital; o objeto diz.

Heurística por texto do objeto, não leitura de item (isso seria a fase 2, que essa
vertical não tem). Erra pros dois lados em objeto genérico — ver test_filtro_pecas.py
pros casos reais usados pra calibrar.
"""

import re

TIPO_PECAS = "Peças"
TIPO_SERVICO = "Serviço com peças"

_F = re.IGNORECASE

# Contexto de veículo/máquina rodante. Sem isso, não é automotivo.
_VEICULO = re.compile(
    r"\bve[íi]cul\w*|\bautomo\w*|\bfrotas?\b|\bcaminh[ãõo]\w*|\b[ôo]nibus\b|micro-?[ôo]nibus"
    r"|\bmotocicletas?\b|\bviaturas?\b|\bambul[âa]ncias?\b|m[áa]quinas? pesadas?|\btrator\w*"
    r"|p[áa] carregadeira|motoniveladora|retroescavadeira|linha (leve|pesada)", _F)

# Produto que só existe em veículo/motor: vale como contexto mesmo sem a palavra
# "veículo" no objeto (ex: "Aquisição de Óleos Lubrificantes e Filtros de Ar,
# Combustível e Óleo"). "Filtro de ar" e "óleo lubrificante" sozinhos NÃO entram:
# servem pra ar-condicionado, gerador, hidráulico.
_PRODUTO_VEICULAR = re.compile(
    r"filtros?[^.;]{0,40}combust[íi]vel|(\b[óo]leos?|lubrificantes?) (de|para|p/) motor\w*"
    r"|pastilhas? de freio|\bpneus?\b|\barla\b", _F)

# O que se compra: peça ou insumo de manutenção.
_INSUMO = re.compile(
    r"\bpe[çc]as\b|autope[çc]as|consum[íi]veis|lubrificantes?\b|\bgraxas?\b|\bfiltros?\b"
    r"|\bbaterias?\b|amortecedor\w*|componentes automotivos", _F)

# Compra direta do insumo (e não contratação de quem troca a peça).
_COMPRA = re.compile(r"aquisi[çc]|fornecimento de pe[çc]|registro de pre[çc]", _F)

_SERVICO = re.compile(r"servi[çc]os? mec[âa]nic\w*|m[ãa]o de obra|\boficinas?\b", _F)

# "Prestação de serviços" sozinho é genérico demais (ex: transformação de micro-ônibus em
# unidade de saúde) — só conta como oficina junto de manutenção.
_PRESTACAO = re.compile(r"presta[çc][ãa]o de servi", _F)

_MANUTENCAO = re.compile(r"manuten[çc][ãa]o|revis[ãa]o|alinhamento|balanceamento|troca de", _F)


def classificar_objeto_pecas(texto: str | None) -> str | None:
    """Retorna TIPO_PECAS, TIPO_SERVICO ou None (objeto sem sinal de peça automotiva)."""
    if not texto or not (_VEICULO.search(texto) or _PRODUTO_VEICULAR.search(texto)):
        return None
    tem_insumo = bool(_INSUMO.search(texto))
    tem_manutencao = bool(_MANUTENCAO.search(texto))
    if _SERVICO.search(texto) or (_PRESTACAO.search(texto) and tem_manutencao):
        return TIPO_SERVICO
    if tem_insumo and _COMPRA.search(texto):
        return TIPO_PECAS
    if tem_manutencao:
        return TIPO_SERVICO
    if tem_insumo:
        return TIPO_PECAS
    # Só contexto de veículo, sem peça nem manutenção: compra de veículo, reboque,
    # curso de mecânica etc. — não é edital de peça.
    return None
