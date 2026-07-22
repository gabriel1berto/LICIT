#!/usr/bin/env python3
"""
dashboard_onco.py — Entrypoint do dashboard (Streamlit multi-page nativo),
espelhando analise/dashboard_pncp.py com paridade completa nas 4 páginas de
Mercado (mesmo cálculo, mesmo módulo compartilhado, mesma sidebar de filtro).

Só o grupo "Mercado" existe aqui — "Radar de Editais" (disputa ativa) e
"Cotação Fornecedor" (preço dos distribuidores de pneu) não se aplicam:
LICIT não disputa edital de medicamento nem tem fornecedor de remédio cotado.

Uso:
    streamlit run dashboard_onco.py
"""

import streamlit as st

st.set_page_config(page_title="LICIT — Mercado de Medicamentos Oncológicos", layout="wide")

pagina = st.navigation({
    "🎗️ Mercado Oncológico": [
        st.Page("views/analise_mercado.py", title="Análise de mercado", icon="🎯", default=True),
        st.Page("views/produto.py", title="Fármaco", icon="💊"),
        st.Page("views/sazonalidade.py", title="Sazonalidade", icon="📅"),
        st.Page("views/fornecedores.py", title="Fornecedores e Preço", icon="🏭"),
        st.Page("views/cobertura_termos.py", title="Cobertura de Termos", icon="🔤"),
    ],
})

pagina.run()
