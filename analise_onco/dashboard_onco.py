#!/usr/bin/env python3
"""
dashboard_onco.py — Entrypoint do dashboard (Streamlit multi-page nativo),
espelhando analise/dashboard_pncp.py.

Só o grupo "Mercado" existe aqui — "Radar de Editais" (disputa ativa) e
"Cotação Fornecedor" (preço dos distribuidores de pneu) não se aplicam:
LICIT não disputa edital de medicamento nem tem fornecedor de remédio cotado.
Ver conversa de 21-22/jul/2026 — decisão explícita.

Uso:
    streamlit run dashboard_onco.py
"""

import streamlit as st

st.set_page_config(page_title="LICIT — Mercado de Medicamentos Oncológicos", layout="wide")

pagina = st.navigation({
    "🎗️ Mercado Oncológico": [
        st.Page("views/visao_geral.py", title="Visão Geral", icon="📊", default=True),
        st.Page("views/farmaco.py", title="Fármaco", icon="💊"),
        st.Page("views/cobertura_termos.py", title="Cobertura de Termos", icon="🔤"),
    ],
})

pagina.run()
