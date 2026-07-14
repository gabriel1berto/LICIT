#!/usr/bin/env python3
"""
classificador_alias.py — Regra determinística (sem LLM, zero custo de token)
pra sinalizar notação de produto que bate a tupla de medida mas pode ser
variante reforçada/comercial (van/utilitário), não pneu de passeio padrão.

Achado 14/jul/2026, revisão manual dos 35 primeiros aliases pendentes
(175/70 R14): sufixo "C" logo após o aro, índice de carga duplo (ex:
"95/93S", denota rating pra uso single/dual wheel — típico de pneu LT),
palavra "Lonas" ou "Van" no nome — sinal de reforçado/comercial mesmo
quando a tupla de medida (largura/perfil/aro) bate igual ao pneu de
passeio comum. Exemplo real flagrado: "Speedmax Transfermax Van V11
175/70R14C 93/90Q 8 Lonas" — mesma tupla de "175/70R14 88T" comum, produto
completamente diferente na prática.

Roda dentro do orquestrador (cotacao_master.py) toda rodada — não precisa
de sessão Claude pra classificar alias novo. Só entra aqui de novo (revisão
manual) quando aparecer padrão de ambiguidade que essas 4 regras não cobrem.
"""

import re

_RE_SUFIXO_C     = re.compile(r"\d{2,3}[Rr]\d{2}(?:[.,]\d)?[Cc]\b")
_RE_INDICE_DUPLO = re.compile(r"\b\d{2,3}/\d{2,3}[A-Z]\b")
_RE_LONAS        = re.compile(r"\bLonas?\b", re.I)
_RE_VAN          = re.compile(r"\bVan\b", re.I)


def classificar_alias(texto_bruto: str) -> tuple[bool, str]:
    """Retorna (suspeita_reforcado, motivo). motivo = "" se não suspeito."""
    motivos = []
    if _RE_SUFIXO_C.search(texto_bruto):
        motivos.append("sufixo C (comercial/reforçado)")
    if _RE_INDICE_DUPLO.search(texto_bruto):
        motivos.append("índice de carga duplo (típico LT/reforçado)")
    if _RE_LONAS.search(texto_bruto):
        motivos.append("menciona nº de lonas")
    if _RE_VAN.search(texto_bruto):
        motivos.append("menciona Van")
    return bool(motivos), " | ".join(motivos)
