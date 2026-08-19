#!/usr/bin/env python3
"""
dashboard_pncp.py — Entrypoint do dashboard (Streamlit multi-page nativo).

4 grupos de página, propósitos diferentes:
  - "Mercado PNCP": dado público de mercado nacional (editais de terceiro),
    sidebar com filtro de UF/período/categoria/regime.
  - "Radar de Editais": Kanban só-leitura dos editais com pneu ainda com
    proposta aberta — triagem operacional, não análise histórica. Análise
    (Camada 1, analisa_edital.py) continua manual, fora do dashboard.
  - "Cotação Fornecedor": preço direto cotado nos nossos 4 distribuidor
    cadastrados (schema cotacao_fornecedor) — sem os filtros PNCP, que não
    fazem sentido aqui.
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
    "💰 Cotação Fornecedor": [
        st.Page("views/cotacao_preco_atual.py", title="Preço Atual", icon="📍"),
        st.Page("views/cotacao_tendencia.py", title="Tendência", icon="📈"),
        st.Page("views/cotacao_aliases.py", title="Aliases Pendentes", icon="⏳"),
    ],
    "🔧 Peças Automotivas": [
        st.Page("views/radar_pecas.py", title="Editais Abertos", icon="🔧"),
    ],
})

pagina.run()
