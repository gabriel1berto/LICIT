#!/usr/bin/env python3
"""Página — Radar de Editais: Desertos & Fracassos — itens de pneu cujo processo
já foi resolvido sem sucesso (Deserto = ninguém apareceu; Fracassado = apareceu,
foi desclassificado). Diferente de radar_abertos.py (só proposta ainda aberta) —
aqui é o histórico já fechado, base pra achar padrão de recompra e decidir contato
direto com o órgão (Passo 2 do plano "ocupar o gap", ver Notion "Ciclo de
aprendizado" e memória do assistente).

Só leitura — nenhum botão aqui dispara ação. Motivo da desclassificação (qual
documento faltou, qual spec não bateu) NÃO está aqui — não existe campo
estruturado pra isso no PNCP, só leitura manual de ata/documento (mesmo trabalho
do analisa_edital.py). Essa página cobre só TIPO (Deserto/Fracassado) + valor +
geografia + recompra, decisão explícita de escopo (fixada na sessão que criou
esta página) — motivo fica pra depois, só nos casos que valem a pena.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import (
    CORES_CATEGORIA, carregar_itens_fracasso, carregar_ultima_carga_detalhes, fmt_abrev, fundo_transparente,
)
from ui_explicacao import cabecalho_pagina, regra

st.title("📉 Desertos & Fracassos")

_ultima_carga = carregar_ultima_carga_detalhes()
if _ultima_carga is not None:
    st.caption(f"📥 Dado carregado até: {_ultima_carga.strftime('%d/%m/%Y %H:%M')} (BRT)")

cabecalho_pagina(
    pergunta="Quais itens de pneu já tiveram processo Deserto ou Fracassado, onde "
    "estão (UF/órgão), e quais órgãos repetem o problema?",
    fonte="Mesma base do Radar de Editais Abertos (`itens`/`detalhes`/`editais`, "
    "coleta PNCP), filtrada por `situacao_item_nome IN ('Deserto','Fracassado')`.",
)

with regra("ℹ️ O que entra aqui, e o que fica de fora"):
    st.markdown(
        "- **Deserto** = nenhum fornecedor apareceu. **Fracassado** = apareceu, "
        "foi desclassificado (na base nacional de pneu do LICIT, hoje é "
        "**maioria** — problema de habilitação/spec é mais comum que falta de "
        "interesse).\n\n"
        "- **Anulado/Revogado/Cancelado fica de fora** — é cancelamento "
        "administrativo do órgão, não sinal de mercado (mesmo critério do "
        "pipeline market-scan-2026).\n\n"
        "- **Só item `eh_pneu=TRUE`** (filtro validado — ver auditoria de "
        "cobertura, 87/88 de uma amostra cruzada com extração nacional "
        "independente bateram nesta base).\n\n"
        "- Mesmo teto de sanidade de valor do resto do dashboard: item "
        "acima de R$50 mil/unidade ou processo acima de R$300 milhões é "
        "descartado (erro de digitação do órgão no PNCP, não pneu caro de "
        "verdade).\n\n"
        "- **Medida extraída por regex do texto do item** (`medida_extraida`, "
        "mesma função de `carregar_base_pncp`) — best-effort. Item sem "
        "dimensão no texto (ex: \"Pneu Veículo Automotivo\" genérico, specs "
        "só no anexo/TR) aparece como \"—\".\n\n"
        "- **Motivo da desclassificação não está aqui** — PNCP não estrutura "
        "esse campo; só sai lendo ata/documento do processo (mesmo trabalho "
        "do `analisa_edital.py`). Fica pra próxima rodada, nos casos que "
        "valerem a pena pelo valor."
    )

itens = carregar_itens_fracasso()
if itens.empty:
    st.info("Nenhum item de pneu Deserto/Fracassado na base ainda.")
    st.stop()

col_uf, col_cat, col_sit, col_tipo = st.columns(4)
with col_uf:
    uf_sel = st.multiselect("UF", sorted(itens["uf"].dropna().unique()), key="uf_frac")
with col_cat:
    cat_sel = st.multiselect("Categoria", sorted(itens["categoria"].dropna().unique()), key="cat_frac")
with col_sit:
    sit_sel = st.multiselect(
        "Situação", ["Deserto", "Fracassado"], key="sit_frac",
        help="Fracassado = apareceu e foi desclassificado. Deserto = ninguém apareceu.",
    )
with col_tipo:
    tipo_sel = st.multiselect("Tipo (procedimento)", sorted(itens["tipo"].dropna().unique()), key="tipo_frac")

df = itens.copy()
if uf_sel:
    df = df[df["uf"].isin(uf_sel)]
if cat_sel:
    df = df[df["categoria"].isin(cat_sel)]
if sit_sel:
    df = df[df["situacao_item_nome"].isin(sit_sel)]
if tipo_sel:
    df = df[df["tipo"].isin(tipo_sel)]

if df.empty:
    st.warning("Nenhum item bate esses filtros.")
    st.stop()

st.caption(f"{len(df)} item(ns), nesse filtro.")

# ── KPIs ──────────────────────────────────────────────────────────────────
n_processos = df["numero_controle_pncp"].nunique()
n_orgaos = df["orgao_cnpj"].nunique()
valor_total = df["valor_item"].sum()
pct_fracassado = (df["situacao_item_nome"] == "Fracassado").mean() * 100

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Valor total", f"R$ {fmt_abrev(valor_total)}")
c2.metric("Itens", f"{len(df):,}")
c3.metric("Processos", f"{n_processos:,}")
c4.metric("Órgãos", f"{n_orgaos:,}")
c5.metric("% Fracassado", f"{pct_fracassado:.0f}%", help="Resto é Deserto — apareceu vs ninguém apareceu")

st.divider()

# ── Valor por UF e por categoria ─────────────────────────────────────────
col_g1, col_g2 = st.columns(2)
with col_g1:
    st.subheader("Valor por UF")
    por_uf = df.groupby("uf", as_index=False)["valor_item"].sum().sort_values("valor_item", ascending=False)
    fig_uf = px.bar(por_uf, x="valor_item", y="uf", orientation="h")
    fig_uf.update_traces(marker_color="#2a78d6")
    fig_uf.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Valor (R$)", yaxis_title="")
    fundo_transparente(fig_uf)
    st.plotly_chart(fig_uf, use_container_width=True)

with col_g2:
    st.subheader("Valor por categoria")
    por_cat = df.groupby("categoria", as_index=False)["valor_item"].sum().sort_values("valor_item", ascending=False)
    fig_cat = px.bar(por_cat, x="valor_item", y="categoria", orientation="h", color="categoria",
                      color_discrete_map=CORES_CATEGORIA)
    fig_cat.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Valor (R$)",
                           yaxis_title="", showlegend=False)
    fundo_transparente(fig_cat)
    st.plotly_chart(fig_cat, use_container_width=True)

st.divider()

# ── Órgãos recorrentes ────────────────────────────────────────────────────
st.subheader("Quem compra de novo")
st.caption("Órgão com 2+ processos nesse recorte — demanda recorrente, alvo direto de contato.")
por_orgao = (
    df.groupby(["orgao_cnpj", "orgao_nome", "uf"], as_index=False)
      .agg(processos=("numero_controle_pncp", "nunique"), itens=("numero_item", "size"),
           valor=("valor_item", "sum"))
      .sort_values("valor", ascending=False)
      .head(15)
)
por_orgao["Recompra"] = por_orgao["processos"].apply(lambda n: "🔁" if n >= 2 else "")
st.dataframe(
    por_orgao.rename(columns={
        "orgao_nome": "Órgão", "uf": "UF", "processos": "Processos", "itens": "Itens", "valor": "Valor",
    })[["Órgão", "UF", "Processos", "Itens", "Valor", "Recompra"]],
    use_container_width=True, hide_index=True,
    column_config={"Valor": st.column_config.NumberColumn(format="R$ %.0f")},
)

st.divider()

# ── Linha a linha ─────────────────────────────────────────────────────────
st.subheader("Linha a linha")
tabela = df[[
    "uf", "orgao_nome", "categoria", "medida_extraida", "situacao_item_nome",
    "valor_item", "data_encerramento_proposta", "pncp_url",
]].copy()
tabela["medida_extraida"] = tabela["medida_extraida"].fillna("—")
tabela = tabela.sort_values("valor_item", ascending=False)
st.dataframe(
    tabela.rename(columns={
        "uf": "UF", "orgao_nome": "Órgão", "categoria": "Categoria", "medida_extraida": "Medida",
        "situacao_item_nome": "Situação", "valor_item": "Valor",
        "data_encerramento_proposta": "Encerrou em", "pncp_url": "PNCP",
    }),
    use_container_width=True, hide_index=True,
    column_config={
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Encerrou em": st.column_config.DatetimeColumn(format="DD/MM/YYYY"),
        "PNCP": st.column_config.LinkColumn(display_text="Abrir"),
    },
)
