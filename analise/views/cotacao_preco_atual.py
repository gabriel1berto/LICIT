#!/usr/bin/env python3
"""Página — Cotação Fornecedor: Preço Atual (comparação da última rodada por medida)."""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import carregar_cotacao_master, fundo_transparente

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

# Última cotação de CADA fornecedor, não "só o dia mais recente combinando todos" —
# achado real 15/jul/26: fornecedor novo (Della Via/Giga) rodando hoje fazia a data
# global virar hoje, derrubando os 4 fornecedores originais (rodaram ontem) da view
# inteira pra qualquer medida onde o novo também aparecesse. Cada fornecedor tem seu
# próprio ciclo de coleta — a comparação certa é "o que cada um cotou por último".
idx_recente = cmm.groupby("fornecedor")["timestamp"].idxmax()
atual = cmm.loc[idx_recente].sort_values("preco")
min_forn = atual.groupby("fornecedor", as_index=False)["preco"].min().sort_values("preco")

datas_por_fornecedor = atual["data"].nunique()
titulo_data = atual["data"].iloc[0] if datas_por_fornecedor == 1 else "última rodada de cada fornecedor"
st.subheader(f"Mais barato por fornecedor — {titulo_data}")
figb = px.bar(
    min_forn, x="preco", y="fornecedor", orientation="h", text="preco",
    labels={"preco": "Preço mínimo (R$)", "fornecedor": ""},
    title=f"{medida_sel} — {ultima_data}",
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
