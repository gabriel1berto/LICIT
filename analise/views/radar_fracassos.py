#!/usr/bin/env python3
"""Página — Radar de Editais: Desertos & Fracassos — itens de pneu cujo processo
já foi resolvido sem sucesso (Deserto = ninguém apareceu; Fracassado = apareceu,
foi desclassificado). Diferente de radar_abertos.py (só proposta ainda aberta) —
aqui é o histórico já fechado, base pra achar padrão de recompra e decidir contato
direto com o órgão (Passo 2 do plano "ocupar o gap", ver Notion "Ciclo de
aprendizado" e memória do assistente).

Só leitura — nenhum botão aqui dispara ação. Motivo da desclassificação (qual
documento faltou, qual spec não bateu) NÃO está aqui — não existe campo
estruturado pra isso no PNCP, só leitura manual de ata/documento (mesmo trabalho
do analisa_edital.py). Essa página cobre só TIPO (Deserto/Fracassado) + valor +
geografia + recompra, decisão explícita de escopo (fixada na sessão que criou
esta página) — motivo fica pra depois, só nos casos que valem a pena.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import (
    CORES_CATEGORIA, carregar_itens_fracasso, carregar_ultima_carga_detalhes, dominio_de, fmt_abrev,
    fundo_transparente, portal_de,
)
from ui_explicacao import cabecalho_pagina, regra

st.title("📉 Desertos & Fracassos")

_ultima_carga = carregar_ultima_carga_detalhes()
if _ultima_carga is not None:
    st.caption(f"📥 Dado carregado até: {_ultima_carga.strftime('%d/%m/%Y %H:%M')} (BRT)")

cabecalho_pagina(
    pergunta="Quais itens de pneu já tiveram processo Deserto ou Fracassado, onde "
    "estão (UF/órgão), e quais órgãos repetem o problema?",
    fonte="Mesma base do Radar de Editais Abertos (`itens`/`detalhes`/`editais`, "
    "coleta PNCP), filtrada por `situacao_item_nome IN ('Deserto','Fracassado')`.",
)

with regra("ℹ️ O que entra aqui, e o que fica de fora"):
    st.markdown(
        "- **Deserto** = nenhum fornecedor apareceu. **Fracassado** = apareceu, "
        "foi desclassificado (na base nacional de pneu do LICIT, hoje é "
        "**maioria** — problema de habilitação/spec é mais comum que falta de "
        "interesse).\n\n"
        "- **Anulado/Revogado/Cancelado fica de fora** — é cancelamento "
        "administrativo do órgão, não sinal de mercado (mesmo critério do "
        "pipeline market-scan-2026).\n\n"
        "- **Só item `eh_pneu=TRUE`** (filtro validado — ver auditoria de "
        "cobertura, 87/88 de uma amostra cruzada com extração nacional "
        "independente bateram nesta base).\n\n"
        "- Mesmo teto de sanidade de valor do resto do dashboard: item "
        "acima de R$50 mil/unidade ou processo acima de R$300 milhões é "
        "descartado (erro de digitação do órgão no PNCP, não pneu caro de "
        "verdade).\n\n"
        "- **Medida extraída por regex do texto do item** (`medida_extraida`, "
        "mesma função de `carregar_base_pncp`) — best-effort. Item sem "
        "dimensão no texto (ex: \"Pneu Veículo Automotivo\" genérico, specs "
        "só no anexo/TR) aparece como \"—\".\n\n"
        "- **Motivo da desclassificação não está aqui** — PNCP não estrutura "
        "esse campo; só sai lendo ata/documento do processo (mesmo trabalho "
        "do `analisa_edital.py`). Fica pra próxima rodada, nos casos que "
        "valerem a pena pelo valor."
    )

itens = carregar_itens_fracasso()
if itens.empty:
    st.info("Nenhum item de pneu Deserto/Fracassado na base ainda.")
    st.stop()

# achado 14/ago/2026 (investigação pedida pelo usuário): portal privado
# conhecido e sistema .gov.br próprio do órgão falham ~3x mais (8,9%) que
# domínio não mapeado (3,0%) — "Não informado" (link vazio) só parece
# dominar porque é ~40% do volume total, não porque falha mais. Mesma lógica
# de dominio_de/portal_de do radar_abertos.py (movida pra dashboard_common.py
# 14/ago/2026 quando esta página passou a precisar dela também).
itens["portal_dominio"] = itens["link_sistema_origem"].apply(dominio_de)
itens["portal"] = itens["portal_dominio"].apply(portal_de)

col_uf, col_cat, col_sit, col_tipo, col_portal, col_janela = st.columns(6)
with col_uf:
    uf_sel = st.multiselect("UF", sorted(itens["uf"].dropna().unique()), key="uf_frac")
with col_cat:
    cat_sel = st.multiselect("Categoria", sorted(itens["categoria"].dropna().unique()), key="cat_frac")
with col_sit:
    sit_sel = st.multiselect(
        "Situação", ["Deserto", "Fracassado"], key="sit_frac",
        help="Fracassado = apareceu e foi desclassificado. Deserto = ninguém apareceu.",
    )
with col_tipo:
    tipo_sel = st.multiselect("Tipo (procedimento)", sorted(itens["tipo"].dropna().unique()), key="tipo_frac")
with col_portal:
    portal_sel = st.multiselect(
        "Portal", sorted(itens["portal"].unique()), key="portal_frac",
        help="Onde a sessão do pregão roda (link_sistema_origem do PNCP). 'Não informado' = "
        "órgão não preencheu esse campo (~40% dos casos) — não é sinal de risco por si só.",
    )
with col_janela:
    JANELA_OPCOES = {"Últimos 30 dias": 30, "Últimos 60 dias": 60, "Últimos 90 dias": 90, "2026 inteiro": None}
    janela_sel = st.selectbox("Janela", list(JANELA_OPCOES.keys()), index=1, key="janela_frac")
    janela_dias = JANELA_OPCOES[janela_sel]

df = itens.copy()
if uf_sel:
    df = df[df["uf"].isin(uf_sel)]
if cat_sel:
    df = df[df["categoria"].isin(cat_sel)]
if sit_sel:
    df = df[df["situacao_item_nome"].isin(sit_sel)]
if tipo_sel:
    df = df[df["tipo"].isin(tipo_sel)]
if portal_sel:
    df = df[df["portal"].isin(portal_sel)]
if janela_dias is not None:
    _limite = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).date() - pd.Timedelta(days=janela_dias)
    df = df[df["data_encerramento_proposta"].dt.date >= _limite]

if df.empty:
    st.warning("Nenhum item bate esses filtros.")
    st.stop()

st.caption(f"{len(df)} item(ns), nesse filtro.")

# ── KPIs ──────────────────────────────────────────────────────────────────
n_processos = df["numero_controle_pncp"].nunique()
n_orgaos = df["orgao_cnpj"].nunique()
valor_total = df["valor_item"].sum()
pct_fracassado = (df["situacao_item_nome"] == "Fracassado").mean() * 100

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Valor total", f"R$ {fmt_abrev(valor_total)}")
c2.metric("Itens", f"{len(df):,}")
c3.metric("Processos", f"{n_processos:,}")
c4.metric("Órgãos", f"{n_orgaos:,}")
c5.metric("% Fracassado", f"{pct_fracassado:.0f}%", help="Resto é Deserto — apareceu vs ninguém apareceu")

st.divider()

# ── Valor por UF e por categoria ─────────────────────────────────────────
col_g1, col_g2 = st.columns(2)
with col_g1:
    st.subheader("Valor por UF")
    # empilhado por categoria (pedido usuário 14/ago/2026) — mesma cor de
    # CORES_CATEGORIA do gráfico ao lado, reusa identidade em vez de paleta nova.
    por_uf_cat = df.groupby(["uf", "categoria"], as_index=False)["valor_item"].sum()
    ordem_uf = (
        por_uf_cat.groupby("uf")["valor_item"].sum().sort_values(ascending=True).index.tolist()
    )
    fig_uf = px.bar(por_uf_cat, x="valor_item", y="uf", orientation="h", color="categoria",
                     color_discrete_map=CORES_CATEGORIA, category_orders={"uf": ordem_uf})
    fig_uf.update_layout(xaxis_title="Valor (R$)", yaxis_title="", legend_title_text="")
    fundo_transparente(fig_uf)
    st.plotly_chart(fig_uf, use_container_width=True)

with col_g2:
    st.subheader("Valor por categoria")
    por_cat = df.groupby("categoria", as_index=False)["valor_item"].sum().sort_values("valor_item", ascending=False)
    fig_cat = px.bar(por_cat, x="valor_item", y="categoria", orientation="h", color="categoria",
                      color_discrete_map=CORES_CATEGORIA)
    fig_cat.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Valor (R$)",
                           yaxis_title="", showlegend=False)
    fundo_transparente(fig_cat)
    st.plotly_chart(fig_cat, use_container_width=True)

st.divider()

# ── Órgãos recorrentes ────────────────────────────────────────────────────
st.subheader("Quem compra de novo")
st.caption("Órgão com 2+ processos nesse recorte — demanda recorrente, alvo direto de contato.")
por_orgao = (
    df.groupby(["orgao_cnpj", "orgao_nome", "uf"], as_index=False)
      .agg(processos=("numero_controle_pncp", "nunique"), itens=("numero_item", "size"),
           valor=("valor_item", "sum"))
      .sort_values("valor", ascending=False)
      .head(15)
)
por_orgao["Recompra"] = por_orgao["processos"].apply(lambda n: "🔁" if n >= 2 else "")
st.dataframe(
    por_orgao.rename(columns={
        "orgao_nome": "Órgão", "uf": "UF", "processos": "Processos", "itens": "Itens", "valor": "Valor",
    })[["Órgão", "UF", "Processos", "Itens", "Valor", "Recompra"]],
    use_container_width=True, hide_index=True,
    column_config={"Valor": st.column_config.NumberColumn(format="R$ %.0f")},
)

st.divider()

# ── Kanban dia a dia ──────────────────────────────────────────────────────
# achado 14/ago/2026 (pedido usuário): tabela "linha a linha" virou Kanban por
# dia de encerramento — mesma lógica visual do radar_abertos.py (1 coluna por
# dia), mas retrospectivo (dia que o processo FECHOU sem sucesso) em vez de
# prospectivo (dia que vai encerrar). Diferente do radar_abertos, NÃO mostra
# todo dia corrido do intervalo — a janela aqui é maior (meses, 2026 inteiro)
# e a maioria dos dias não tem processo nenhum; mostrar só dia com dado
# mantém o Kanban navegável em vez de centenas de coluna vazia.
#
# Janela agora é filtro do topo da página (junto de UF/Categoria/Situação/
# Tipo) — afeta KPI/gráficos/órgãos/Kanban juntos, não só esta seção (pedido
# usuário 14/ago/2026, antes só filtrava aqui embaixo).
st.subheader("Dia a dia")
st.caption("1 coluna por dia em que algum processo fechou Deserto/Fracassado — mais recente primeiro.")

WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
df_kanban = df.copy()
df_kanban["data_dia"] = df_kanban["data_encerramento_proposta"].dt.date
dias_lista = sorted(df_kanban["data_dia"].dropna().unique(), reverse=True)

if not dias_lista:
    st.info("Nenhum processo fechado nessa janela.")
else:
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            padding-bottom: 12px;
        }
        div[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) > div[data-testid="column"] {
            min-width: 260px !important;
            flex: 0 0 260px !important;
            width: 260px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(len(dias_lista))
    for col, dia in zip(cols, dias_lista):
        with col:
            st.markdown(f"#### {WEEKDAYS_PT[dia.weekday()]} {dia.strftime('%d/%m')}")
            bucket = df_kanban[df_kanban["data_dia"] == dia].sort_values("valor_item", ascending=False)
            st.caption(f"{len(bucket)} item(ns) · R$ {fmt_abrev(bucket['valor_item'].sum())}")
            for _, row in bucket.iterrows():
                with st.container(border=True):
                    cor_sit = "🔴" if row["situacao_item_nome"] == "Fracassado" else "⚪"
                    st.markdown(f"{cor_sit} **{row['situacao_item_nome']}**")
                    orgao_label = row["orgao_nome"] or "(órgão sem nome no PNCP)"
                    st.caption(f"**{orgao_label}** — {row['uf']}")
                    medida = row["medida_extraida"] or "—"
                    st.caption(f"{row['categoria'] or '—'} · {medida}")
                    valor_txt = f"R$ {row['valor_item']:,.0f}" if pd.notna(row["valor_item"]) else "sem valor"
                    st.caption(valor_txt)
                    st.caption(f"🔗 {row['portal']}")
                    if pd.notna(row["pncp_url"]):
                        st.link_button("Abrir no PNCP", row["pncp_url"], use_container_width=True)
