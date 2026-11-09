#!/usr/bin/env python3
"""
dashboard_pncp.py — Entrypoint do dashboard (Streamlit multi-page nativo).

4 grupos de página, propósitos diferentes:
  - "Mercado PNCP": dado público de mercado nacional (editais de terceiro),
    sidebar com filtro de UF/período/categoria/regime.
  - "Radar de Editais": Kanban só-leitura dos editais com pneu ainda com
    proposta aberta — triagem operacional, não análise histórica. Análise
    (Camada 1, analisa_edital.py) continua manual, fora do dashboard.
  - "Radar de Fornecedor" (09/nov/2026, substitui as 3 páginas de "Cotação
    Fornecedor"): mapa dos fornecedores catalogados no Notion por UF + fila de
    prioridade de contato. Snapshot estático (assets/radar_fornecedor.html).
  - "Peças Automotivas" (17-19/ago/2026): exploração de mercado separada de
    pneu (schema `pecas_automotivas`, óleo/graxa/filtro/bateria/amortecedor)
    — só radar de editais abertos, fase 1 (sem detalhe/item), sem cotação de
    fornecedor ainda. Ver analise/coletor_pecas.py.

Conteúdo de cada página vive em views/*.py — este arquivo só declara a
navegação e o page_config global.

Uso:
    streamlit run dashboard_pncp.py
"""

import streamlit as st

st.set_page_config(page_title="LICIT — Mercado & Cotação de Pneu", layout="wide")

pagina = st.navigation({
    "📊 Mercado PNCP": [
        st.Page("views/mercado_analise.py", title="Análise de mercado", icon="🎯", default=True),
        st.Page("views/mercado_produto.py", title="Produto", icon="📦"),
        st.Page("views/mercado_sazonalidade.py", title="Sazonalidade", icon="📅"),
        st.Page("views/mercado_fornecedores.py", title="Fornecedores e Preço", icon="🏭"),
    ],
    "🗂️ Radar de Editais": [
        st.Page("views/radar_abertos.py", title="Editais Abertos", icon="🗂️"),
        st.Page("views/radar_fracassos.py", title="Desertos & Fracassos", icon="📉"),
    ],
    "📡 Radar de Fornecedor": [
        st.Page("views/radar_fornecedor.py", title="Radar de Fornecedor", icon="📡"),
    ],
    "🔧 Peças Automotivas": [
        st.Page("views/radar_pecas.py", title="Editais Abertos", icon="🔧"),
    ],
})

pagina.run()
