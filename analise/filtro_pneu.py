#!/usr/bin/env python3
"""
filtro_pneu.py — Filtro "é pneu de verdade?" único, compartilhado entre
coletor_pncp.py, coletor_pncp_detalhe.py e pncp_radar.py. Zero dependência
pesada de propósito (só `re`) — importável de qualquer script sem puxar
psycopg2/sqlalchemy/etc junto.

Histórico: regex já passou por 8 bugs documentados corrigidos (ver
analise/README.md e página "Dados públicos" no Notion). Antes de 07/jul/2026
essa lógica estava duplicada e divergente em 3 lugares (base_pneu.sql,
coletor_pncp_detalhe.py, pncp_radar.py) — cada um corrigido em momento
diferente, nenhum sincronizado com os outros. Esse módulo é a fonte única.

2 níveis de classificação:
  - Nível PROCESSO (classificar_pneu): texto corrido de título+descrição do
    processo inteiro — mais fraco, usado só pra pré-filtro antes de abrir
    detalhe/itens (economiza chamada de API em processo obviamente não-pneu).
  - Nível ITEM (eh_pneu_de_verdade): descrição estruturada de 1 item de
    catálogo — muito mais confiável, é o filtro que decide de fato.
"""

import re

# ── Nível ITEM — mesmo regex validado, ver README.md ───────────────────────

RE_PNEU_INICIO = re.compile(r"^\s*pneus?\b", re.IGNORECASE)
RE_CAMARA_INICIO = re.compile(r"^\s*c[âa]mara\s+(de\s+)?ar\b", re.IGNORECASE)
RE_MEDIDA_R = re.compile(r"\d{3}\s*/\s*\d{2}\s*[Rr]\s*\d{2}\b")
# bug achado jul/2026: veículo inteiro (caminhão/ambulância/pick-up/van) que só CITA a
# medida do pneu de fábrica batia em RE_MEDIDA_R e virava "eh_pneu=1" — item de
# R$100k-800k/unidade (o veículo), não o pneu. Mesma lógica de âncora no início já usada
# pra pneu/câmara: se o produto começa com nome de veículo, medida solta não conta.
RE_VEICULO_INICIO = re.compile(
    r"^\s*(ve[íi]culo|caminh[ãa]o|ambul[âa]ncia|[ôo]nibus|micro[ -]?[ôo]nibus|van\b|"
    r"pick[ -]?up|caminhonete|loca[çc][ãa]o\s+(di[áa]ria\s+)?de\s+ve[íi]culo)",
    re.IGNORECASE,
)
RE_EXCLUSAO = re.compile(
    r"carregadeira|motoniveladora|retroescavadeira|escavadeira|rolo\s+compactador|"
    r"cadeira\s+de\s+rodas|recapagem|vulcaniza[çc][ãa]o|alinhamento|balanceamento|conserto|"
    r"presta[çc][aã]o\s+de\s+servi[çc]|servi[çc]os?\s+de\s+(borracharia|recauchutagem|vulcaniza|substitui)|"
    r"loca[çc][aã]o\s+de\s+(trator|m[áa]quina|equipamento)|"
    r"loca[çc][aã]o\s+(di[áa]ria\s+)?de.{0,40}(ve[íi]culo|van|minibus|micro[ -]?[ôo]nibus|[ôo]nibus|caminh[ãa]o|ambul[âa]ncia)|"
    r"manuten[çc][ãa]o\s+(preventiva|corretiva)?\s*(do|de)\s+ve[íi]culo|"
    r"n[úu]cleo.*v[áa]lvula|v[áa]lvula.*n[úu]cleo",
    re.IGNORECASE,
)
RE_CATEGORIA_CAMARA = RE_CAMARA_INICIO
RE_CATEGORIA_MOTO = re.compile(r"motocicleta|motoneta|ciclomotor", re.IGNORECASE)
RE_CATEGORIA_AGRICOLA = re.compile(r"trator|agr[íi]cola", re.IGNORECASE)
RE_CATEGORIA_CAMINHAO = re.compile(r"r2[2-9]\.?[05]?\b|r1[7-9]\.?5\b", re.IGNORECASE)


def eh_pneu_de_verdade(descricao: str) -> bool:
    """Nível ITEM — filtro forte. Descrição de item de catálogo, não texto livre."""
    if not descricao:
        return False
    if RE_VEICULO_INICIO.search(descricao):
        return False
    bate_produto = bool(RE_PNEU_INICIO.search(descricao) or RE_CAMARA_INICIO.search(descricao) or RE_MEDIDA_R.search(descricao))
    return bate_produto and not RE_EXCLUSAO.search(descricao)


def classificar_categoria(descricao: str) -> str:
    if RE_CATEGORIA_CAMARA.search(descricao):
        return "Câmara de ar"
    if RE_CATEGORIA_MOTO.search(descricao):
        return "Moto"
    if RE_CATEGORIA_AGRICOLA.search(descricao):
        return "Agrícola"
    if RE_CATEGORIA_CAMINHAO.search(descricao):
        return "Caminhão"
    return "Passeio"


# ── Nível PROCESSO — mais fraco, só pré-filtro (título+descrição do edital) ─

RE_MAQUINA_PESADA = re.compile(
    r"carregadeira|motoniveladora|retroescavadeira|escavadeira|rolo\s+compactador|"
    r"cadeira\s+de\s+rodas|trator\b",
    re.IGNORECASE,
)
RE_SERVICO = re.compile(
    r"recapagem|vulcaniza[çc][ãa]o|alinhamento|balanceamento|conserto|"
    r"borracharia|recauchutagem|manuten[çc][ãa]o\s+(preventiva|corretiva)?\s*(do|de)\s+ve[íi]culo",
    re.IGNORECASE,
)
RE_AQUISICAO = re.compile(
    r"aquisi[çc][ãa]o|compra|fornecimento|registro\s+de\s+pre[çc]o",
    re.IGNORECASE,
)
RE_PNEU_SUBSTANTIVO = re.compile(r"\bpneus?\b", re.IGNORECASE)
RE_PNEUMATICO_ADJETIVO = re.compile(r"pneum[áa]tic[ao]", re.IGNORECASE)


def classificar_pneu(titulo: str, descricao: str) -> str:
    """Nível PROCESSO — rótulo de confiança sobre texto corrido (título+descrição
    do processo inteiro, não item de catálogo). Mais fraco que eh_pneu_de_verdade
    — usar só como pré-filtro pra economizar chamada de API, nunca como filtro final.
    """
    texto = f"{titulo or ''} {descricao or ''}"

    tem_pneu_substantivo = bool(RE_PNEU_SUBSTANTIVO.search(texto))
    tem_pneumatico_adjetivo = bool(RE_PNEUMATICO_ADJETIVO.search(texto))

    if not tem_pneu_substantivo and tem_pneumatico_adjetivo:
        return "adjetivo_provavel"

    if RE_MAQUINA_PESADA.search(texto):
        return "maquina_pesada_provavel"

    if RE_SERVICO.search(texto) and not RE_AQUISICAO.search(texto):
        return "servico_provavel"

    if tem_pneu_substantivo:
        return "compra_provavel"

    return "indefinido"
