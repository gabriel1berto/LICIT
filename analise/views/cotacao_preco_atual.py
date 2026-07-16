#!/usr/bin/env python3
"""Página — Cotação Fornecedor: Preço Atual (comparação da última rodada por medida)."""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import carregar_cotacao_master, fundo_transparente

IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUHVWY")}

st.title("📍 Preço Atual")
st.caption(
    "Cotação diária direta nos distribuidores já cadastrados (Bransales, Cantu, GP Fácil, "
    "PneuGreen, Della Via) — schema `cotacao_fornecedor`, pipeline separado do "
    "mercado PNCP. Cada fornecedor pode ter rodado num dia diferente — a comparação usa a "
    "última cotação de cada um, não só o dia mais recente combinado."
)

cm = carregar_cotacao_master()
if cm.empty:
    st.info("Nenhuma cotação master gravada ainda.")
    st.stop()

cm = cm.copy()
cm["data"] = pd.to_datetime(cm["timestamp"]).dt.strftime("%Y-%m-%d")

medidas_disp = sorted(cm["medida"].unique())
medida_sel = st.selectbox("Medida:", medidas_disp, key="medida_preco_atual")
cmm = cm[cm["medida"] == medida_sel]

# Última RODADA de cada fornecedor — todas as linhas daquele batch, não só 1 (achado
# real 15/jul/26, corrigido de novo agora: pegar direto o idxmax do timestamp deixava
# a escolha de QUAL produto sobra por fornecedor dependendo da ordem de inserção, não
# de um critério explícito). Filtro de especificação entra ANTES de decidir o mais
# barato — senão o "mais barato" pode ser um produto que nem bate o critério pedido.
idx_ultima_rodada = cmm.groupby("fornecedor")["timestamp"].transform("max") == cmm["timestamp"]
ultima_rodada = cmm[idx_ultima_rodada]

st.subheader("Filtros de especificação")
col1, col2, col3 = st.columns(3)
with col1:
    ic_min = st.number_input("Índice de Carga mínimo", min_value=0, value=0, step=1, key="ic_min_preco_atual")
with col2:
    iv_opcoes = [""] + sorted(IV_ORDER, key=IV_ORDER.get)
    iv_min = st.selectbox("Índice de Velocidade mínimo", iv_opcoes, key="iv_min_preco_atual")
with col3:
    construcoes_disp = sorted(ultima_rodada["construcao"].dropna().unique())
    construcao_sel = st.selectbox("Construção", [""] + construcoes_disp, key="construcao_preco_atual")

filtrado = ultima_rodada.copy()
if ic_min > 0:
    filtrado = filtrado[filtrado["ic"] >= ic_min]
if iv_min:
    filtrado = filtrado[filtrado["iv"].map(lambda v: IV_ORDER.get(str(v).upper(), -1) >= IV_ORDER[iv_min] if pd.notna(v) else False)]
if construcao_sel:
    filtrado = filtrado[filtrado["construcao"] == construcao_sel]

if ic_min > 0 or iv_min or construcao_sel:
    st.caption(
        "⚠️ Filtro ativo — produto sem o dado de especificação preenchido é excluído "
        "(não dá pra confirmar se atende o critério)."
    )

if filtrado.empty:
    st.warning("Nenhum produto atende aos filtros de especificação selecionados.")
    st.stop()

idx_barato = filtrado.groupby("fornecedor")["preco"].idxmin()
atual = filtrado.loc[idx_barato].sort_values("preco")
min_forn = atual.groupby("fornecedor", as_index=False)["preco"].min().sort_values("preco")

datas_por_fornecedor = atual["data"].nunique()
titulo_data = atual["data"].iloc[0] if datas_por_fornecedor == 1 else "última rodada de cada fornecedor"
st.subheader(f"Mais barato por fornecedor — {titulo_data}")
figb = px.bar(
    min_forn, x="preco", y="fornecedor", orientation="h", text="preco",
    labels={"preco": "Preço mínimo (R$)", "fornecedor": ""},
    title=f"{medida_sel} — {titulo_data}",
)
figb.update_traces(marker_color="#2a78d6", texttemplate="R$ %{text:.2f}", textposition="outside")
fundo_transparente(figb)
st.plotly_chart(figb, use_container_width=True)

st.divider()
st.subheader("Detalhe completo dessa rodada")
detalhe = atual[[
    "fornecedor", "data", "marca", "preco", "confianca_match", "ic", "iv", "treadwear",
    "construcao", "num_lonas", "tipo_terreno", "inmetro", "url",
]].rename(columns={
    "fornecedor": "Fornecedor", "data": "Data da cotação", "marca": "Marca", "preco": "Preço (R$)",
    "confianca_match": "Confiança", "ic": "IC", "iv": "IV", "treadwear": "Treadwear",
    "construcao": "Construção", "num_lonas": "Nº Lonas", "tipo_terreno": "Terreno",
    "inmetro": "INMETRO", "url": "Link",
}).sort_values("Preço (R$)")
st.dataframe(
    detalhe, use_container_width=True, hide_index=True,
    column_config={"Link": st.column_config.LinkColumn("Link", display_text="abrir")},
)
st.caption(
    "Confiança 'parcial' = notação do produto ainda não aprovada manualmente (1ª vez que aparece "
    "daquele fornecedor) — preço é real, só a confirmação de que bate exatamente a medida ainda não "
    "foi revisada por humano. Ver página 'Aliases Pendentes'."
)
