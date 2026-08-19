#!/usr/bin/env python3
"""Página — Radar de Peças Automotivas: Kanban por dia de encerramento, mesma
estrutura visual da página "Editais Abertos" do pneu (`radar_abertos.py`) —
achado 19/ago/2026, pedido explícito do usuário pra igualar o formato.

Diferenças deliberadas (fase 1 só, sem detalhe/item, sem cotação de
fornecedor — mesmo estágio do Oncológico hoje):
  - Sem mapa/CAPAG (precisam de codigo_ibge, que só existe na fase 2 —
    decisão de não construir fase 2 ainda, ver conversa 19/ago/2026).
  - Sem funil "meu preço x preço histórico" (sem cotação de distribuidor
    pra peça automotiva, mesma exceção que radar_abertos_onco.py já tem).
  - "Encerra em" usa `data_fim_vigencia` do search API (fase 1), não
    `data_encerramento_proposta` (fase 2) — proxy razoável, não confirmado
    item a item.

Só leitura — nenhum botão aqui dispara coletor/análise/Notion.
"""

import pandas as pd
import streamlit as st

from conectar_pecas import carregar_editais_abertos_pecas
from dashboard_common import COR_STATUS_CRITICAL, COR_STATUS_GOOD, COR_STATUS_WARNING
from ui_explicacao import cabecalho_pagina, regra

WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# Auditoria 19/ago/2026 (amostra real dos 1.726 editais coletados até então):
# % de resultado com sinal explícito de contexto automotivo (veículo/automotivo/carro/
# caminhão/ônibus/frota/moto/van/ambulância/viatura) no título+descrição. Objeto do
# edital raramente qualifica "automotivo" pra óleo/graxa no PNCP — insumo genérico de
# qualquer maquinário (gerador, hidráulico, agrícola, naval), não só veículo. Resolver
# de verdade exigiria fase 2 (item a item, decisão deliberada de não construir ainda).
CONFIANCA_POR_TERMO = {
    "Bateria automotiva":    ("alta", 94.1),
    "Amortecedor":           ("alta", 67.0),
    "Filtro de óleo":        ("média", 56.8),
    "Filtro de combustível": ("média", 52.9),
    "Filtro de ar":          ("média", 52.2),
    "Óleo lubrificante":     ("baixa", 11.4),
    "Graxa":                 ("baixa", 6.2),
}
_ICONE_CONFIANCA = {"alta": "✅", "média": "⚠️", "baixa": "🔴"}

st.title("🔧 Radar de Peças Automotivas")

cabecalho_pagina(
    pergunta="Quais editais com óleo lubrificante, graxa, filtro (ar/óleo/combustível), "
    "bateria automotiva ou amortecedor estão com proposta aberta agora?",
    fonte="Busca direta na API do PNCP (`analise/coletor_pecas.py`), schema `pecas_automotivas` "
    "— isolado do dado de pneu/oncológico.",
)

st.warning(
    "🔴 **Graxa** e **Óleo lubrificante** têm alto risco de falso-positivo — auditoria real "
    "(19/ago/2026) achou só 6-11% dos resultados com sinal explícito de veículo/automotivo/frota "
    "no texto; o restante é majoritariamente insumo genérico (máquina industrial, hidráulico, "
    "agrícola, naval) que usa o mesmo termo. **Filtro de ar/óleo/combustível** ficam em risco "
    "médio (52-57%). Só **Bateria automotiva** e **Amortecedor** têm sinal forte (67-94%). "
    "Coluna **Confiança** na tabela abaixo marca isso por termo — não é confirmação item a item, "
    "só probabilidade baseada no termo de busca."
)
with regra("ℹ️ Por que esse risco existe (e por que não dá pra resolver só ajustando a busca)"):
    st.markdown(
        "O objeto do edital no PNCP raramente qualifica \"automotivo\"/\"veicular\" quando é óleo "
        "ou graxa — é insumo genérico registrado do mesmo jeito pra motor de caminhão, gerador, "
        "equipamento hidráulico, maquinário agrícola ou naval. Adicionar a palavra \"automotivo\" "
        "no termo de busca reduziria o ruído mas também perderia a maioria dos editais reais (a "
        "maior parte não escreve esse qualificador mesmo quando é pra frota). Resolver de verdade "
        "exigiria fase 2 (ler item a item, mesma arquitetura do pneu/onco) — decisão deliberada de "
        "não construir isso ainda, esta página é só radar de edital-nível, não classificação de item."
    )

editais = carregar_editais_abertos_pecas()
if editais.empty:
    st.info("Nenhum edital aberto com esses termos no momento.")
    st.stop()

col_uf, col_mod, col_termo = st.columns(3)
with col_uf:
    uf_sel = st.multiselect("UF", sorted(editais["uf"].dropna().unique()), key="uf_radar_pecas")
with col_mod:
    mod_sel = st.multiselect(
        "Modalidade", sorted(editais["modalidade_licitacao_nome"].dropna().unique()), key="mod_radar_pecas"
    )
with col_termo:
    termos_disp = sorted({t.strip() for ts in editais["termo_busca"].dropna() for t in ts.split(",")})
    termo_sel = st.multiselect("Termo encontrado", termos_disp, key="termo_radar_pecas")

_ORDEM_CONFIANCA = {"alta": 3, "média": 2, "baixa": 1}


def _confianca_edital(termos_str: str) -> str:
    """1 edital pode bater mais de 1 termo — usa a MAIOR confiança entre eles (se bateu
    também por um termo específico tipo 'Bateria automotiva', o contexto automotivo já
    fica mais provável mesmo que 'Graxa' também tenha batido no mesmo texto)."""
    termos = [t.strip() for t in termos_str.split(",")]
    niveis = [CONFIANCA_POR_TERMO.get(t, ("média", 0))[0] for t in termos]
    return max(niveis, key=lambda n: _ORDEM_CONFIANCA[n])


editais["confianca"] = editais["termo_busca"].apply(_confianca_edital)

col_conf = st.columns(1)[0]
with col_conf:
    conf_sel = st.multiselect(
        "Confiança (sinal automotivo no texto)", ["alta", "média", "baixa"], key="conf_radar_pecas",
        help="Baseado no(s) termo(s) que bateram nesse edital — ver auditoria acima. Não é "
        "confirmação item a item.",
    )

if uf_sel:
    editais = editais[editais["uf"].isin(uf_sel)]
if mod_sel:
    editais = editais[editais["modalidade_licitacao_nome"].isin(mod_sel)]
if termo_sel:
    editais = editais[editais["termo_busca"].apply(lambda s: any(t in s for t in termo_sel))]
if conf_sel:
    editais = editais[editais["confianca"].isin(conf_sel)]

if editais.empty:
    st.warning("Nenhum edital aberto bate esses filtros.")
    st.stop()

st.caption(f"{len(editais)} edital(is) aberto(s), nesse filtro.")

# Mesmos 3 buckets de urgência do radar de pneu/onco — cor reservada, sempre com
# ícone+label junto (skill dataviz, "status color nunca sozinha").
BUCKETS = [
    ("🔴", "Urgente", COR_STATUS_CRITICAL, lambda d: d <= 2),
    ("🟡", "Esta semana", COR_STATUS_WARNING, lambda d: 2 < d <= 7),
    ("🟢", "Depois", COR_STATUS_GOOD, lambda d: d > 7),
]


def _icone_cor_dia(dias_faltam: float) -> tuple:
    for icone, _, cor, cond in BUCKETS:
        if cond(dias_faltam):
            return icone, cor
    return "❔", COR_STATUS_GOOD


contagem_orgao = editais["orgao_nome"].value_counts()

# Kanban por dia de encerramento (mesmo padrão de radar_abertos.py do pneu, 1 coluna
# por dia corrido entre hoje e o edital mais distante, mesmo dia sem edital nenhum).
#
# ⚠️ Achado 19/ago/2026 (bug real pego em teste): `data_fim_vigencia` é o único campo
# de prazo que a fase 1 (search API) tem, mas pra Inexigibilidade/Credenciamento/SRP
# ele às vezes é VIGÊNCIA DE ATA (anos), não fim de proposta — 1 edital de Candoi/PR
# tinha data_fim_vigencia em 2029 (1046 dias), o que gerava >1000 colunas e travava o
# navegador. Teto de segurança: só vira coluna de dia se faltar ≤45 dias; o resto cai
# numa coluna "📦 Vigência longa" no final, sem quebrar o layout. Resolver de verdade
# (saber se é prazo de proposta real) exigiria fase 2 — mesma decisão já registrada
# no topo do arquivo.
TETO_DIAS_KANBAN = 45
editais["data_dia"] = editais["data_fim_vigencia"].dt.date
editais_kanban = editais[editais["dias_restantes"] <= TETO_DIAS_KANBAN]
editais_vigencia_longa = editais[editais["dias_restantes"] > TETO_DIAS_KANBAN]

_hoje = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).date()
if editais_kanban.empty:
    dias_lista = []
else:
    dias_lista = list(pd.date_range(_hoje, editais_kanban["data_dia"].max()).date)

st.markdown(
    """
    <style>
    div[data-testid="stHorizontalBlock"]:has(> div:nth-child(20)) {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        padding-bottom: 12px;
    }
    div[data-testid="stHorizontalBlock"]:has(> div:nth-child(20)) > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"]:has(> div:nth-child(20)) > div[data-testid="column"] {
        min-width: 260px !important;
        flex: 0 0 260px !important;
        width: 260px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def _render_card(row: pd.Series, cor_dia: str) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div style="height:4px;background:{cor_dia};border-radius:2px;margin-bottom:10px;"></div>',
            unsafe_allow_html=True,
        )
        st.metric("Encerra em", f"{row['dias_restantes']:.1f} dia(s)")
        orgao_label = row["orgao_nome"]
        if contagem_orgao.get(row["orgao_nome"], 0) > 1:
            orgao_label += " 🔁"
        st.caption(f"**{orgao_label}** — {row['municipio']}/{row['uf']}")
        icone_conf = _ICONE_CONFIANCA[row["confianca"]]
        st.caption(f"{icone_conf} Confiança {row['confianca']} · termo: {row['termo_busca']}")
        valor = row["valor_global"]
        if pd.isna(valor) or valor == 0:
            st.caption("Sem valor estimado (órgão não informou no PNCP)")
        else:
            st.caption(f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."))
        st.link_button("Abrir no PNCP", row["pncp_url"], use_container_width=True)
        with st.expander("Detalhes"):
            objeto = row["titulo"] or row["descricao"] or "(sem objeto descrito)"
            st.caption(str(objeto)[:200] + ("…" if len(str(objeto)) > 200 else ""))
            st.caption(f"{row['modalidade_licitacao_nome'] or '—'}")
            if contagem_orgao.get(row["orgao_nome"], 0) > 1:
                st.caption(
                    f"🔁 Esse órgão tem {contagem_orgao[row['orgao_nome']]} editais de peça "
                    "automotiva abertos agora, nesse filtro."
                )


n_cols = len(dias_lista) + (1 if not editais_vigencia_longa.empty else 0)
cols = st.columns(max(n_cols, 1))
for col, dia in zip(cols, dias_lista):
    with col:
        dias_faltam = (dia - _hoje).days
        icone_dia, cor_dia = _icone_cor_dia(dias_faltam)
        st.markdown(f"#### {icone_dia} {WEEKDAYS_PT[dia.weekday()]} {dia.strftime('%d/%m')}")
        if dias_faltam == 0:
            st.caption("Encerra hoje")
        elif dias_faltam == 1:
            st.caption("Falta 1 dia")
        else:
            st.caption(f"Faltam {dias_faltam} dias")
        bucket = editais_kanban[editais_kanban["data_dia"] == dia].sort_values("dias_restantes")
        if bucket.empty:
            st.caption("Nenhum edital nesse dia.")
            continue
        for _, row in bucket.iterrows():
            _render_card(row, cor_dia)

if not editais_vigencia_longa.empty:
    with cols[-1]:
        st.markdown(f"#### 📦 Vigência longa (>{TETO_DIAS_KANBAN}d)")
        st.caption(
            "`data_fim_vigencia` aqui é provável vigência de ata/registro de preço, não fim de "
            "proposta real — confirmar no link antes de assumir prazo."
        )
        for _, row in editais_vigencia_longa.sort_values("dias_restantes").iterrows():
            _render_card(row, COR_STATUS_GOOD)

st.divider()
st.caption(
    "Análise de edital individual não roda pra peças automotivas ainda — este radar é só "
    "monitoramento/triagem de mercado. Nenhuma escrita acontece a partir deste dashboard."
)
