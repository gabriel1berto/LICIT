#!/usr/bin/env python3
"""Página — Mercado PNCP: Fornecedores e Preço (concentração, desconto e ticket por categoria)."""

import plotly.express as px
import streamlit as st

from dashboard_common import CORES_CATEGORIA, fmt_abrev, fundo_transparente, para_mil, preparar_pagina_pncp

st.title("🏭 Fornecedores e Preço")

df, df_forn, cobertura_medida, com_medida, top_medidas, top_medidas_nomes_8 = preparar_pagina_pncp()

vencidos = df_forn

st.subheader("Concentração de fornecedores")
if vencidos.empty or vencidos["nome_fornecedor"].dropna().empty:
    st.info("Sem item com resultado (vencedor definido) nesse filtro.")
else:
    conc = (
        vencidos.dropna(subset=["nome_fornecedor"])
                .groupby("nome_fornecedor", as_index=False)
                .agg(valor_ganho=("valor_total_resultado", "sum"),
                     n_processos=("numero_controle_pncp", "nunique"),
                     n_itens=("quantidade", "sum"))
                .sort_values("valor_ganho", ascending=False)
                .head(15)
    )
    total_ganho = vencidos["valor_total_resultado"].sum()
    # achado 08/jul/26: "Top 5 concentram X%" somava participacao_pct já
    # arredondado CÉLULA a célula — acumula erro de arredondamento (~0,25pp medido).
    # top5_pct_bruto guarda a fração exata pra somar antes de arredondar 1x só.
    conc["participacao_pct_bruto"] = conc["valor_ganho"] / total_ganho * 100
    conc["participacao_pct"] = conc["participacao_pct_bruto"].round().astype("int64")
    conc["valor_ganho"] = conc["valor_ganho"].round().astype("int64")

    conc_label = conc.sort_values("valor_ganho").copy()
    conc_label["valor_label"] = conc_label["valor_ganho"].apply(fmt_abrev)
    col_conc_graf, col_conc_tab = st.columns([1, 1])
    with col_conc_graf:
        figf = px.bar(
            conc_label, x="valor_ganho", y="nome_fornecedor", orientation="h", text="valor_label",
            labels={"valor_ganho": "Valor ganho (R$)", "nome_fornecedor": ""},
            title="Top 15 fornecedores por valor ganho",
        )
        figf.update_traces(marker_color="#2a78d6", textposition="outside")
        figf.update_layout(showlegend=False)
        fundo_transparente(figf)
        st.plotly_chart(figf, use_container_width=True)
        top5_pct = conc.head(5)["participacao_pct_bruto"].sum()
        st.caption(f"Top 5 fornecedores concentram {top5_pct:.0f}% do valor ganho nos filtros atuais.")

    with col_conc_tab:
        st.subheader("Recorrência — processos vencidos")
        tabela_forn = conc[["nome_fornecedor", "n_processos", "n_itens", "valor_ganho", "participacao_pct"]].rename(
            columns={"nome_fornecedor": "Fornecedor", "n_processos": "Editais ganhos", "n_itens": "Itens vendidos",
                     "valor_ganho": "Valor ganho (R$ mil)", "participacao_pct": "% do total"}
        )
        tabela_forn["Valor ganho (R$ mil)"] = tabela_forn["Valor ganho (R$ mil)"].apply(para_mil)
        st.dataframe(tabela_forn, use_container_width=True, hide_index=True, height=480)

st.divider()
col_desc_cat, col_ticket_cat = st.columns([1, 1])

with col_desc_cat:
    st.subheader("Desconto mediano por categoria")
    preco = df.dropna(subset=["valor_unitario_estimado", "valor_unitario_resultado"])
    # > R$1: exclui preço de referência simbólico (R$0,01) que o órgão publica quando
    # não tem estimativa real — dividir por isso gera % de desconto absurda (-8M%).
    preco = preco[preco["valor_unitario_estimado"] > 1]
    if preco.empty:
        st.info("Sem item com valor estimado + resultado nesse filtro.")
    else:
        preco = preco.copy()
        preco["desconto_pct"] = (1 - preco["valor_unitario_resultado"] / preco["valor_unitario_estimado"]) * 100
        desconto_cat = preco.groupby("categoria", as_index=False)["desconto_pct"].median().sort_values("desconto_pct", ascending=False)
        desconto_cat["desconto_pct"] = desconto_cat["desconto_pct"].round().astype("int64")
        desconto_cat["desconto_label"] = desconto_cat["desconto_pct"].apply(lambda v: f"{v:.0f}%")

        fig4 = px.bar(
            desconto_cat, x="categoria", y="desconto_pct", text="desconto_label",
            color="categoria", color_discrete_map=CORES_CATEGORIA,
            labels={"categoria": "Categoria", "desconto_pct": "Desconto mediano (%)"},
            title="Desconto mediano (estimado → homologado)",
        )
        fig4.update_traces(textposition="outside")
        fig4.update_layout(showlegend=False)
        fundo_transparente(fig4, tickformat_x=False)
        st.plotly_chart(fig4, use_container_width=True)

with col_ticket_cat:
    st.subheader("Valor médio por item, por categoria")
    ticket_cat = df.groupby("categoria", as_index=False)["valor_item"].mean().rename(columns={"valor_item": "valor_medio"})
    ticket_cat["valor_medio"] = ticket_cat["valor_medio"].round().astype("int64")
    ticket_cat = ticket_cat.sort_values("valor_medio", ascending=False)
    ticket_cat["valor_label"] = ticket_cat["valor_medio"].apply(fmt_abrev)
    fig5 = px.bar(
        ticket_cat, x="categoria", y="valor_medio", text="valor_label",
        color="categoria", color_discrete_map=CORES_CATEGORIA,
        labels={"categoria": "Categoria", "valor_medio": "Valor médio por item (R$)"},
        title="Valor médio por item",
    )
    fig5.update_traces(textposition="outside")
    fig5.update_layout(showlegend=False)
    fundo_transparente(fig5, tickformat_x=False)
    st.plotly_chart(fig5, use_container_width=True)
