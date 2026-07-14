#!/usr/bin/env python3
"""Página — Cotação Fornecedor: Tendência (preço mínimo por fornecedor ao longo do tempo)."""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import carregar_cotacao_master, fundo_transparente

st.title("📈 Tendência")
st.caption("Histórico de preço mínimo por fornecedor — cresce conforme mais rodadas diárias acontecerem.")

cm = carregar_cotacao_master()
if cm.empty:
    st.info("Nenhuma cotação master gravada ainda.")
    st.stop()

cm = cm.copy()
# string, não datetime.date — px.line trata data ISO como eixo temporal contínuo
# e gera tick fracionário esquisito (23:59:59.999) quando o range é de 1-2 dias só.
cm["data"] = pd.to_datetime(cm["timestamp"]).dt.strftime("%Y-%m-%d")

medidas_disp = sorted(cm["medida"].unique())
medida_sel = st.selectbox("Medida:", medidas_disp, key="medida_tendencia")
cmm = cm[cm["medida"] == medida_sel]

tend = (
    cmm.groupby(["data", "fornecedor"], as_index=False)["preco"]
       .min()
       .sort_values("data")
)
if tend["data"].nunique() < 2:
    st.caption("Só 1 dia de dado até agora — vira linha de tendência real conforme mais rodadas acontecerem.")

figcm = px.line(
    tend, x="data", y="preco", color="fornecedor", markers=True,
    labels={"data": "Data", "preco": "Preço mínimo (R$)", "fornecedor": "Fornecedor"},
    title=f"Preço mínimo — {medida_sel}",
)
figcm.update_layout(legend_title_text="")
# type="category" força eixo discreto — sem isso Plotly reconhece o padrão ISO
# da string e converte pra eixo temporal contínuo de qualquer jeito.
figcm.update_xaxes(type="category")
fundo_transparente(figcm, tickformat_x=False)
st.plotly_chart(figcm, use_container_width=True)
