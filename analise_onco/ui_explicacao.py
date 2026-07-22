#!/usr/bin/env python3
"""
ui_explicacao.py — Padrão de explicabilidade local do dashboard: cabeçalho que
nomeia a pergunta que a página responde + fonte do dado, e blocos "Regra e
cálculo" (expander) perto do gráfico que eles explicam. Mesmo tom já usado na
página Aliases Pendentes: direto, sem jargão, com o achado real por trás da
regra quando existe — não reexplicar o óbvio.
"""

from contextlib import contextmanager
from typing import Optional

import streamlit as st


def cabecalho_pagina(pergunta: str, fonte: str, ultima_atualizacao: Optional[str] = None) -> None:
    linha = f"**Pergunta que essa página responde:** {pergunta}  \n**Fonte:** {fonte}"
    if ultima_atualizacao:
        linha += f"  \n**Última atualização:** {ultima_atualizacao}"
    st.caption(linha)


@contextmanager
def regra(titulo: str = "ℹ️ Regra e cálculo"):
    with st.expander(titulo):
        yield
