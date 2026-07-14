#!/usr/bin/env python3
"""
dashboard_pncp.py — Entrypoint do dashboard (Streamlit multi-page nativo).

2 grupos de página, propósitos diferentes:
  - "Mercado PNCP": dado público de mercado nacional (editais de terceiro),
    sidebar com filtro de UF/período/categoria/regime.
  - "Cotação Fornecedor": preço direto cotado nos nossos 4 distribuidor
    cadastrados (schema cotacao_fornecedor) — sem os filtros PNCP, que não
    fazem sentido aqui.

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
    "💰 Cotação Fornecedor": [
        st.Page("views/cotacao_preco_atual.py", title="Preço Atual", icon="📍"),
        st.Page("views/cotacao_tendencia.py", title="Tendência", icon="📈"),
        st.Page("views/cotacao_aliases.py", title="Aliases Pendentes", icon="⏳"),
    ],
})

pagina.run()
