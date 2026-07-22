#!/usr/bin/env python3
"""Página — Mercado Oncológico: Fármaco (princípios ativos mais pedidos, fornecedor dominante por fármaco, tendência mensal).
Espelha analise/views/mercado_produto.py — mesmo cálculo, trocando medida de pneu por princípio ativo."""

import plotly.express as px
import streamlit as st

from dashboard_common_onco import cor_categorica_ordenada, fundo_transparente, para_mil, preparar_pagina_onco

st.title("💊 Fármaco")

df, df_forn, cobertura_medida, com_medida, top_medidas, top_medidas_nomes_8 = preparar_pagina_onco()

if com_medida.empty:
    st.info("Sem fármaco identificado nesse filtro.")
    st.stop()

col_medida_graf, col_medida_tab = st.columns([1, 1])
with col_medida_graf:
    top_medidas_label = top_medidas.sort_values("n_itens").copy()
    top_medidas_label["n_label"] = top_medidas_label["n_itens"].apply(lambda v: f"{v:,}".replace(",", "."))
    figm = px.bar(
        top_medidas_label, x="n_itens", y="medida_extraida", orientation="h", text="n_label",
        labels={"n_itens": "Nº de itens pedidos", "medida_extraida": "Fármaco"},
        title="Top 15 fármacos mais pedidos (por nº de itens)",
    )
    figm.update_traces(marker_color="#2a78d6", textposition="outside")
    fundo_transparente(figm)
    st.plotly_chart(figm, use_container_width=True)
    st.caption(
        f"Fármaco identificado em {cobertura_medida:.0f}% dos itens ({len(com_medida)}/{len(df)}) — "
        "resto é item ainda sem detalhe processado."
    )
with col_medida_tab:
    top_medidas_fmt = top_medidas.rename(columns={
        "medida_extraida": "Fármaco", "n_itens": "Itens pedidos", "n_vendidos": "Itens vendidos",
        "valor_total": "Valor total (R$ mil)",
    })
    top_medidas_fmt["Valor total (R$ mil)"] = top_medidas_fmt["Valor total (R$ mil)"].apply(para_mil)
    st.dataframe(top_medidas_fmt, use_container_width=True, hide_index=True, height=480)

st.divider()
col_dom_medida, col_tend = st.columns([1, 1])
with col_dom_medida:
    st.subheader("Fornecedor dominante por fármaco")
    venc_medida = df_forn.dropna(subset=["nome_fornecedor", "medida_extraida"])
    top_medidas_nomes_geral = top_medidas["medida_extraida"].tolist()
    if venc_medida.empty:
        st.info("Sem item com resultado + fármaco nesse filtro.")
    else:
        por_med_forn = (
            venc_medida[venc_medida["medida_extraida"].isin(top_medidas_nomes_geral)]
            .groupby(["medida_extraida", "nome_fornecedor"], as_index=False)
            .agg(valor_total_resultado=("valor_total_resultado", "sum"),
                 editais=("numero_controle_pncp", "nunique"),
                 itens=("quantidade", "sum"))
        )
        total_med = por_med_forn.groupby("medida_extraida")["valor_total_resultado"].transform("sum")
        por_med_forn["participacao_pct"] = (por_med_forn["valor_total_resultado"] / total_med * 100).round().astype("int64")
        dom_medida = (
            por_med_forn.sort_values("valor_total_resultado", ascending=False)
                        .groupby("medida_extraida").first().reset_index()
        )
        dom_medida["valor_total_resultado"] = dom_medida["valor_total_resultado"].apply(para_mil)
        dom_medida = dom_medida.rename(columns={
            "medida_extraida": "Fármaco", "nome_fornecedor": "Fornecedor dominante",
            "valor_total_resultado": "Valor ganho (R$ mil)", "participacao_pct": "% do fármaco",
            "editais": "Editais ganhos", "itens": "Itens vendidos",
        }).sort_values("% do fármaco", ascending=False)
        st.dataframe(dom_medida, use_container_width=True, hide_index=True, height=450)
        st.caption(
            "Quem mais vende cada fármaco. Útil pra identificar fármaco com fornecedor pouco "
            "concentrado (mais espaço pra entrar) x fármaco já dominado."
        )

with col_tend:
    st.subheader("Tendência mensal — top 5 fármacos")
    top5_medidas = top_medidas.sort_values("n_itens", ascending=False).head(5)["medida_extraida"].tolist()
    tend_medida = (
        com_medida[com_medida["medida_extraida"].isin(top5_medidas)]
        .dropna(subset=["ano_mes"])
        .groupby(["ano_mes", "medida_extraida"], as_index=False)
        .size().rename(columns={"size": "n_itens"})
        .sort_values("ano_mes")
    )
    if tend_medida.empty:
        st.info("Sem dado de data suficiente pra tendência mensal nesse filtro.")
    else:
        figt = px.line(
            tend_medida, x="ano_mes", y="n_itens", color="medida_extraida", markers=True,
            color_discrete_map=cor_categorica_ordenada(top5_medidas),
            category_orders={"medida_extraida": top5_medidas},
            labels={"ano_mes": "Mês", "n_itens": "Nº de itens pedidos", "medida_extraida": "Fármaco"},
            title="Evolução mensal de demanda — top 5 fármacos",
        )
        figt.update_layout(legend_title_text="", height=450)
        fundo_transparente(figt, tickformat_x=False)
        st.plotly_chart(figt, use_container_width=True)
        st.caption("Mês = data de abertura de proposta. Ajuda a ver fármaco em alta x em queda.")
