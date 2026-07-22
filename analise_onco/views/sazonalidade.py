#!/usr/bin/env python3
"""Página — Mercado Oncológico: Sazonalidade (demanda mensal por UF ou classe farmacológica).
Espelha analise/views/mercado_sazonalidade.py."""

import plotly.express as px
import streamlit as st

from dashboard_common_onco import CORES_CLASSE_FARMACO, fundo_transparente, preparar_pagina_onco

st.title("📅 Sazonalidade")

df, df_forn, cobertura_medida, com_medida, top_medidas, top_medidas_nomes_8 = preparar_pagina_onco()

st.caption("Mês = data de abertura de proposta (proxy — `detalhes` não tem data de publicação).")
granularidade = st.radio("Ver por:", ["UF", "Classe farmacológica"], horizontal=True)
grupo_col = "uf" if granularidade == "UF" else "categoria"

sazon = (
    df.dropna(subset=["ano_mes"])
      .groupby(["ano_mes", grupo_col], as_index=False)
      .agg(valor_total=("valor_item", "sum"), n_processos=("cod_compra", "nunique"))
      .sort_values("ano_mes")
)
sazon["valor_total"] = sazon["valor_total"].round().astype("int64")

metrica = st.radio("Métrica:", ["Valor total (R$)", "Nº processos"], horizontal=True)
y_col = "valor_total" if metrica == "Valor total (R$)" else "n_processos"

if grupo_col == "categoria":
    fig2 = px.line(
        sazon, x="ano_mes", y=y_col, color=grupo_col, markers=True,
        color_discrete_map=CORES_CLASSE_FARMACO,
        labels={"ano_mes": "Mês", y_col: metrica, grupo_col: granularidade},
        title=f"Sazonalidade mensal — {metrica} por {granularidade} (PNCP direto)",
    )
    fig2.update_layout(legend_title_text="")
    fundo_transparente(fig2, tickformat_x=False)
    st.plotly_chart(fig2, use_container_width=True)
else:
    pivot = sazon.pivot(index="uf", columns="ano_mes", values=y_col).fillna(0)
    ordem_uf = pivot.sum(axis=1).sort_values(ascending=False).index
    pivot = pivot.loc[ordem_uf]

    fig2 = px.imshow(
        pivot, color_continuous_scale="Blues", aspect="auto",
        labels={"x": "Mês", "y": "UF", "color": metrica},
        title=f"Sazonalidade mensal — {metrica} por UF (PNCP direto)",
    )
    fig2.update_layout(height=max(450, 22 * len(pivot)))
    fig2.update_xaxes(side="bottom")
    fundo_transparente(fig2, tickformat_x=False)
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("UF ordenada por volume total, mais escuro = mais. Passe o mouse pra ver o valor exato de cada célula.")
