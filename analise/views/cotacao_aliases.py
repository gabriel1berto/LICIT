#!/usr/bin/env python3
"""Página — Cotação Fornecedor: Aliases Pendentes (só leitura — dashboard é público).

Aprovação de verdade é manual, via revisar_aliases_pendentes.py rodado no
terminal (privado). Não expor botão de escrita aqui — qualquer visitante do
dashboard público poderia aprovar alias sem revisão real.
"""

import streamlit as st

from dashboard_common import carregar_aliases_pendentes_detalhe

st.title("⏳ Aliases Pendentes")
st.caption(
    "Notações de produto ainda não aprovadas manualmente — cotação correspondente aparece "
    "como confiança 'parcial' até ser revisada. Aprovação é feita fora daqui, via "
    "`revisar_aliases_pendentes.py` (terminal, privado) — não há ação de escrita neste dashboard "
    "público."
)

pendentes = carregar_aliases_pendentes_detalhe()

if pendentes.empty:
    st.success("Nenhum alias pendente — tudo revisado.")
    st.stop()

n_suspeitos = int(pendentes["suspeita_reforcado"].sum())
st.warning(
    f"⚠️ {len(pendentes)} notação(ões) pendente(s) de aprovação "
    f"— **{n_suspeitos} sinalizada(s)** pelo classificador determinístico (sufixo C, índice "
    "de carga duplo, 'Lonas' ou 'Van' — indício de produto reforçado/comercial)."
)

tabela = pendentes.rename(columns={
    "fornecedor": "Fornecedor", "texto_bruto": "Notação do produto", "medida": "Medida",
    "inferido": "Construção inferida", "created_at": "Visto em",
    "suspeita_reforcado": "Suspeito", "motivo_suspeita": "Motivo",
}).drop(columns=["id"])
st.dataframe(
    tabela, use_container_width=True, hide_index=True,
    column_config={"Suspeito": st.column_config.CheckboxColumn("Suspeito", disabled=True)},
)
st.caption("Ordenado com os suspeitos primeiro. Classificação roda no orquestrador, sem custo de token.")
