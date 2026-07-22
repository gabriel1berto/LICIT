#!/usr/bin/env python3
"""
dashboard_onco.py — Dashboard simples do mercado de medicamentos oncológicos no
PNCP. Espelha analise/dashboard_pncp.py na ideia, mas 1 página só (schema
`oncologia` ainda tem só nível edital — sem item/resultado ainda, ver
coletor_onco.py). Evoluir pra multi-página quando tiver mais dado, igual pneu.

Uso:
    streamlit run dashboard_onco.py
"""

import streamlit as st
import plotly.express as px

from conectar_onco import carregar_editais, cobertura_vocabulario

st.set_page_config(page_title="LICIT — Mercado de Medicamentos Oncológicos", layout="wide")
st.title("🎗️ Mercado de Medicamentos Oncológicos — PNCP")
st.caption(
    "Vocabulário validado: nome genérico completo + marca comercial. "
    "Abreviação clínica testada e rejeitada (falso positivo alto)."
)

df = carregar_editais()

if df.empty:
    st.warning("Ainda sem dado coletado — rode `python coletor_onco.py` primeiro.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Editais coletados", f"{len(df):,}")
col2.metric("Órgãos distintos", f"{df['orgao_cnpj'].nunique():,}")
col3.metric("UFs cobertas", df["uf"].nunique())
col4.metric("Termos já buscados", cobertura_vocabulario().shape[0])

st.divider()

c1, c2 = st.columns(2)
with c1:
    st.subheader("Por modalidade")
    fig = px.pie(df, names="tipo", hole=0.4)
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.subheader("Por UF (top 15)")
    top_uf = df["uf"].value_counts().head(15).reset_index()
    top_uf.columns = ["uf", "n"]
    fig = px.bar(top_uf, x="uf", y="n")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Órgãos mais recorrentes")
top_orgao = df["orgao_nome"].value_counts().head(15).reset_index()
top_orgao.columns = ["orgao_nome", "n"]
st.dataframe(top_orgao, use_container_width=True, hide_index=True)

st.subheader("Evolução mensal (data de publicação)")
por_mes = df.dropna(subset=["ano_mes"]).groupby("ano_mes").size().reset_index(name="n")
fig = px.line(por_mes.sort_values("ano_mes"), x="ano_mes", y="n", markers=True)
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Cobertura por termo de busca (genérico vs marca)")
cov = cobertura_vocabulario()
st.dataframe(cov, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Explorar editais")
uf_filtro = st.multiselect("Filtrar UF", sorted(df["uf"].dropna().unique()))
termo_filtro = st.multiselect("Filtrar termo de busca", sorted(df["termo_busca"].dropna().unique()))
df_filtrado = df.copy()
if uf_filtro:
    df_filtrado = df_filtrado[df_filtrado["uf"].isin(uf_filtro)]
if termo_filtro:
    df_filtrado = df_filtrado[df_filtrado["termo_busca"].isin(termo_filtro)]
st.dataframe(
    df_filtrado[["uf", "orgao_nome", "titulo", "descricao", "modalidade_licitacao_nome", "termo_busca", "data_publicacao_pncp"]],
    use_container_width=True, hide_index=True,
)
