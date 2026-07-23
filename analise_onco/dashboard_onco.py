#!/usr/bin/env python3
"""
dashboard_onco.py — Entrypoint do dashboard (Streamlit multi-page nativo),
espelhando analise/dashboard_pncp.py com paridade completa nas 4 páginas de
Mercado (mesmo cálculo, mesmo módulo compartilhado, mesma sidebar de filtro).

Grupo "Radar de Editais" adicionado 22/jul/2026 (decisão revertida — até então
LICIT só monitorava mercado oncológico, sem disputar edital; ver
analise_onco/views/radar_abertos_onco.py). "Cotação Fornecedor" continua sem
existir aqui: LICIT ainda não tem fornecedor/distribuidor de medicamento
cotado (funil "meu preço" do Radar de pneu não tem equivalente ainda).

Uso:
    streamlit run dashboard_onco.py
"""

import streamlit as st

st.set_page_config(page_title="LICIT — Mercado de Medicamentos Oncológicos", layout="wide")

pagina = st.navigation({
    "🗂️ Radar de Editais": [
        st.Page("views/radar_abertos_onco.py", title="Editais Abertos", icon="🗂️"),
    ],
    "🎗️ Mercado Oncológico": [
        st.Page("views/analise_mercado.py", title="Análise de mercado", icon="🎯", default=True),
        st.Page("views/produto.py", title="Fármaco", icon="💊"),
        st.Page("views/sazonalidade.py", title="Sazonalidade", icon="📅"),
        st.Page("views/fornecedores.py", title="Fornecedores e Preço", icon="🏭"),
        st.Page("views/cobertura_termos.py", title="Cobertura de Termos", icon="🔤"),
    ],
})

pagina.run()
