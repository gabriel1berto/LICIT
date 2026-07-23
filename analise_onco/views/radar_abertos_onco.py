#!/usr/bin/env python3
"""Página — Radar de Editais Oncológico: Kanban de editais com medicamento
oncológico ainda com proposta aberta. Espelha analise/views/radar_abertos.py
do pneu, com 1 diferença estrutural: SEM funil "meu preço x preço histórico"
(LICIT não tem fornecedor/distribuidor de medicamento cotado — decisão
revertida em 22/jul/2026, ver commit; até então este dashboard era só
monitoramento de mercado, sem intenção de disputa ativa).

Só leitura — nenhum botão aqui dispara coletor/análise/Notion.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common_onco import (
    COR_STATUS_CRITICAL, COR_STATUS_GOOD, COR_STATUS_WARNING,
    capag_do_orgao, carregar_base, carregar_capag_estados, carregar_capag_municipios,
    carregar_editais_abertos_onco, carregar_itens_onco_editais_abertos,
    carregar_lat_lon_cached, carregar_ultima_carga_detalhes, cor_capag, fmt_abrev,
    fundo_transparente,
)
from ui_explicacao import cabecalho_pagina, regra

st.title("🗂️ Radar de Editais Oncológico")

_ultima_carga = carregar_ultima_carga_detalhes()
if _ultima_carga is not None:
    st.caption(f"📥 Dado carregado até: {_ultima_carga.strftime('%d/%m/%Y %H:%M')} (BRT)")

cabecalho_pagina(
    pergunta="Quais editais com medicamento oncológico estão com proposta aberta agora, e "
    "quanto tempo falta pra decidir participar?",
    fonte="Mesma base do Mercado Oncológico (`analise_onco/coletor_onco_detalhe.py`), filtrada "
    "por situação 'Divulgada no PNCP' + prazo de proposta no futuro.",
)

with regra("ℹ️ Como esse Kanban decide o que é 'aberto'"):
    st.markdown(
        "Edital entra aqui quando **todas** as condições batem:\n\n"
        "- `situacao_compra_nome = 'Divulgada no PNCP'` (exclui Revogada/Suspensa/Anulada).\n"
        "- `data_encerramento_proposta` no futuro (cache expira a cada 5min).\n"
        "- Pelo menos 1 item bate `eh_medicamento_onco = TRUE`.\n"
        "- Modalidade **não é** Leilão.\n\n"
        "Diferente do Radar de pneu: **sem teto de valor por item** — medicamento "
        "oncológico (biológico/alvo molecular) legitimamente custa dezenas de milhares "
        "por unidade, um teto copiado do pneu descartaria item real. **Sem \"meu preço\"** — "
        "LICIT não tem fornecedor de medicamento cotado ainda, só o preço médio histórico "
        "(mediana do que já venceu processo parecido) aparece em Detalhes, como referência "
        "de mercado, não comparação com custo próprio.\n\n"
        "**CAPAG** (Tesouro Nacional, ano base 2025): 🟢 A+/A · 🟡 B+/B · 🔴 C/D — risco de "
        "atraso/calote no pagamento depois de vencer, não qualidade do edital em si."
    )

editais = carregar_editais_abertos_onco()
if editais.empty:
    st.info("Nenhum edital com medicamento oncológico e proposta aberta no momento.")
    st.stop()

col_uf, col_mod, col_regime = st.columns(3)
with col_uf:
    uf_sel = st.multiselect("UF", sorted(editais["uf"].dropna().unique()), key="uf_radar_onco")
with col_mod:
    mod_sel = st.multiselect(
        "Modalidade", sorted(editais["modalidade_licitacao_nome"].dropna().unique()), key="mod_radar_onco"
    )
with col_regime:
    regime_sel = st.multiselect(
        "Regime", sorted(editais["regime"].dropna().unique()), key="regime_radar_onco",
        help="RP = Registro de Preço (SRP) · CD = Compra Direta (sem SRP)",
    )

if uf_sel:
    editais = editais[editais["uf"].isin(uf_sel)]
if mod_sel:
    editais = editais[editais["modalidade_licitacao_nome"].isin(mod_sel)]
if regime_sel:
    editais = editais[editais["regime"].isin(regime_sel)]

if editais.empty:
    st.warning("Nenhum edital aberto bate esses filtros.")
    st.stop()

st.caption(f"{len(editais)} edital(is) aberto(s) com medicamento oncológico, nesse filtro.")

_capag_mun = carregar_capag_municipios()
_capag_uf = carregar_capag_estados()
MAPA_CAPAG_MUN = dict(zip(_capag_mun["codigo_ibge"], _capag_mun["capag"]))
MAPA_CAPAG_UF = dict(zip(_capag_uf["uf"], _capag_uf["capag"]))

BUCKETS = [
    ("🔴", "Urgente", "até 2 dias", COR_STATUS_CRITICAL, lambda d: d <= 2),
    ("🟡", "Esta semana", "3 a 7 dias", COR_STATUS_WARNING, lambda d: 2 < d <= 7),
    ("🟢", "Depois", "mais de 7 dias", COR_STATUS_GOOD, lambda d: d > 7),
]


def _bucket_de(dias: float) -> str:
    for icone, titulo, _, _, cond in BUCKETS:
        if cond(dias):
            return f"{icone} {titulo}"
    return "❔ Sem prazo"


editais["bucket_label"] = editais["dias_restantes"].apply(_bucket_de)
CORES_BUCKET = {f"{icone} {titulo}": cor for icone, titulo, _, cor, _ in BUCKETS}

contagem_orgao = editais["orgao_nome"].value_counts()

itens_onco = carregar_itens_onco_editais_abertos(tuple(editais["numero_controle_pncp"]))
_base_mercado = carregar_base().dropna(subset=["medida_extraida", "valor_unitario_resultado"])
preco_hist_por_principio = _base_mercado.groupby("medida_extraida")["valor_unitario_resultado"].median()

st.subheader("Onde estão os editais abertos")
mapa_df = editais.dropna(subset=["codigo_ibge"]).merge(carregar_lat_lon_cached(), on="codigo_ibge", how="left")
mapa_df = mapa_df.dropna(subset=["latitude", "longitude"])
if mapa_df.empty:
    st.info("Sem coordenada de município pra mostrar no mapa nesse filtro.")
else:
    zoom = max(3.0, 8.5 - 1.4 * max(
        mapa_df["latitude"].max() - mapa_df["latitude"].min(),
        mapa_df["longitude"].max() - mapa_df["longitude"].min(),
        0.5,
    ))
    fig_mapa = px.scatter_mapbox(
        mapa_df, lat="latitude", lon="longitude", color="bucket_label",
        category_orders={"bucket_label": list(CORES_BUCKET)},
        color_discrete_map=CORES_BUCKET,
        hover_name="orgao_nome",
        hover_data={"municipio": True, "uf": True, "dias_restantes": ":.1f", "latitude": False, "longitude": False},
        center={"lat": mapa_df["latitude"].mean(), "lon": mapa_df["longitude"].mean()},
        zoom=zoom, mapbox_style="carto-darkmatter",
    )
    fig_mapa.update_traces(marker=dict(size=12))
    fig_mapa.update_layout(height=500, margin=dict(l=0, r=0, t=0, b=0), legend_title_text="")
    fundo_transparente(fig_mapa)
    st.plotly_chart(fig_mapa, use_container_width=True)

st.divider()
cols = st.columns(len(BUCKETS))
for col, (icone, titulo, subtitulo, cor, cond) in zip(cols, BUCKETS):
    with col:
        st.markdown(f"#### {icone} {titulo}")
        st.caption(subtitulo)
        bucket = editais[editais["dias_restantes"].apply(cond)].copy().sort_values("dias_restantes")
        if bucket.empty:
            st.caption("Nenhum edital nessa faixa.")
            continue
        for _, row in bucket.iterrows():
            with st.container(border=True):
                st.markdown(
                    f'<div style="height:4px;background:{cor};border-radius:2px;margin-bottom:10px;"></div>',
                    unsafe_allow_html=True,
                )
                dias = row["dias_restantes"]
                st.metric("Encerra em", f"{dias:.1f} dia(s)")
                orgao_label = row["orgao_nome"]
                if contagem_orgao.get(row["orgao_nome"], 0) > 1:
                    orgao_label += " 🔁"
                st.caption(f"**{orgao_label}** — {row['municipio']}/{row['uf']}")

                nota_capag, origem_capag = capag_do_orgao(
                    row["codigo_ibge"], row["uf"], MAPA_CAPAG_MUN, MAPA_CAPAG_UF
                )
                if nota_capag:
                    cor_nota = cor_capag(nota_capag)
                    icone_capag = "🟢" if cor_nota == COR_STATUS_GOOD else "🟡" if cor_nota == COR_STATUS_WARNING else "🔴"
                    st.caption(f"{icone_capag} CAPAG {nota_capag} ({origem_capag})")
                else:
                    st.caption("⚪ CAPAG sem dado")

                valor_onco = row["valor_onco_estimado"]
                if pd.isna(valor_onco) or valor_onco == 0:
                    st.caption("Sem valor estimado (órgão não informou no PNCP)")
                else:
                    st.caption(f"R$ {fmt_abrev(valor_onco)} em itens oncológicos")
                n_onco, n_total = int(row["n_itens_onco"]), int(row["n_itens_total"])
                if n_onco < n_total:
                    st.caption(f"⚠️ {n_onco} de {n_total} itens são oncológico — resto do edital é outra coisa")
                st.link_button("Abrir no PNCP", row["pncp_url"], use_container_width=True)

                with st.expander("Detalhes"):
                    objeto = row["objeto_compra"] or "(sem objeto descrito)"
                    st.caption(objeto[:200] + ("…" if len(objeto) > 200 else ""))
                    data_fmt = row["data_encerramento_proposta"].strftime("%d/%m/%Y %H:%M")
                    st.caption(
                        f"{row['modalidade_licitacao_nome'] or '—'} · "
                        f"{n_onco} de {n_total} item(ns) oncológico(s) · encerra {data_fmt}"
                    )
                    valor_proc = row["valor_total_estimado"]
                    if pd.isna(valor_proc) or valor_proc == 0:
                        st.caption("Valor estimado do processo inteiro: sem dado (órgão não informou no PNCP)")
                    else:
                        st.caption(f"Valor estimado do processo inteiro (todos os itens): R$ {fmt_abrev(valor_proc)}")
                    if contagem_orgao.get(row["orgao_nome"], 0) > 1:
                        st.caption(
                            f"🔁 Esse órgão tem {contagem_orgao[row['orgao_nome']]} editais oncológicos "
                            "abertos agora, nesse filtro."
                        )

                    itens_edital = itens_onco[itens_onco["numero_controle_pncp"] == row["numero_controle_pncp"]]
                    if not itens_edital.empty:
                        tabela = itens_edital.copy()
                        tabela["Princípio ativo (provável)"] = tabela["principio_ativo_provavel"].fillna("—")
                        tabela["Preço médio histórico"] = tabela["principio_ativo_provavel"].map(preco_hist_por_principio)
                        tabela["Valor estimado (edital)"] = tabela["valor_unitario_estimado"]
                        tabela = tabela[
                            ["Princípio ativo (provável)", "Preço médio histórico", "Valor estimado (edital)"]
                        ].drop_duplicates()
                        st.caption("Item x preço médio histórico x valor estimado no edital:")
                        st.dataframe(
                            tabela, use_container_width=True, hide_index=True,
                            column_config={
                                "Preço médio histórico": st.column_config.NumberColumn(format="R$ %.2f"),
                                "Valor estimado (edital)": st.column_config.NumberColumn(format="R$ %.2f"),
                            },
                        )

st.divider()
st.caption(
    "Análise (Camada 1) não roda pra oncológico ainda — este dashboard é monitoramento/"
    "triagem, análise de edital individual continua manual fora daqui."
)
