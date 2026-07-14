#!/usr/bin/env python3
"""Página — Mercado PNCP: Sazonalidade (demanda mensal por UF ou categoria)."""

import plotly.express as px
import streamlit as st

from dashboard_common import CORES_CATEGORIA, CORES_REGIME_TIPO, fundo_transparente, preparar_pagina_pncp

st.title("📅 Sazonalidade")

df, df_forn, cobertura_medida, com_medida, top_medidas, top_medidas_nomes_8 = preparar_pagina_pncp()

st.caption("Mês = data de abertura de proposta (proxy — `detalhes` não tem data de publicação).")
granularidade = st.radio("Ver por:", ["UF", "Categoria de produto"], horizontal=True)
grupo_col = "uf" if granularidade == "UF" else "categoria"
cores = CORES_REGIME_TIPO if granularidade == "UF" else CORES_CATEGORIA

sazon = (
    df.dropna(subset=["ano_mes"])
      .groupby(["ano_mes", grupo_col], as_index=False)
      .agg(valor_total=("valor_item", "sum"), n_processos=("cod_compra", "nunique"))
      .sort_values("ano_mes")
)
sazon["valor_total"] = sazon["valor_total"].round().astype("int64")

metrica = st.radio("Métrica:", ["Valor total (R$)", "Nº processos"], horizontal=True)
y_col = "valor_total" if metrica == "Valor total (R$)" else "n_processos"

fig2 = px.line(
    sazon, x="ano_mes", y=y_col, color=grupo_col, markers=True,
    color_discrete_map=cores if grupo_col == "categoria" else None,
    labels={"ano_mes": "Mês", y_col: metrica, grupo_col: granularidade},
    title=f"Sazonalidade mensal — {metrica} por {granularidade} (PNCP direto)",
)
fig2.update_layout(legend_title_text="")
fundo_transparente(fig2, tickformat_x=False)
st.plotly_chart(fig2, use_container_width=True)
