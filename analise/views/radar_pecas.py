#!/usr/bin/env python3
"""Página — Radar de Peças Automotivas: lista simples de editais abertos com
óleo lubrificante/graxa/filtro de ar/bateria automotiva/filtro de
combustível/amortecedor/filtro de óleo. Vertical de exploração de mercado
(17-19/ago/2026, mesmo estágio do Oncológico) — separado dos dados de pneu,
schema próprio (`pecas_automotivas`), sem cotação de fornecedor ainda.

Fase 1 só (busca de edital, sem detalhe/item) — tabela simples, sem Kanban
por dia/mapa/CAPAG (isso existe no Radar de pneu/onco, decisão deliberada de
manter esta página enxuta, ver conversa 19/ago/2026).

Só leitura — nenhum botão aqui dispara coletor/análise/Notion.
"""

import streamlit as st

from conectar_pecas import carregar_editais_abertos_pecas
from ui_explicacao import cabecalho_pagina, regra

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

editais = editais.sort_values("dias_restantes")
tabela = editais.copy()
tabela["Órgão"] = tabela["orgao_nome"]
tabela["Local"] = tabela["municipio"] + "/" + tabela["uf"]
tabela["Modalidade"] = tabela["modalidade_licitacao_nome"]
tabela["Termo"] = tabela["termo_busca"]
tabela["Confiança"] = tabela["confianca"].map(_ICONE_CONFIANCA) + " " + tabela["confianca"]
tabela["Valor estimado"] = tabela["valor_global"]
tabela["Encerra em (dias)"] = tabela["dias_restantes"].round(1)
tabela["Link"] = tabela["pncp_url"]

st.dataframe(
    tabela[["Órgão", "Local", "Modalidade", "Termo", "Confiança", "Valor estimado", "Encerra em (dias)", "Link"]],
    use_container_width=True, hide_index=True,
    column_config={
        "Valor estimado": st.column_config.NumberColumn(format="R$ %.2f"),
        "Link": st.column_config.LinkColumn(display_text="Abrir no PNCP"),
    },
)

st.caption(
    "Análise de edital individual não roda pra peças automotivas ainda — este radar é só "
    "monitoramento/triagem de mercado."
)
