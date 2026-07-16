#!/usr/bin/env python3
"""Página — Radar de Editais: Kanban de editais com pneu ainda com proposta aberta.

Só leitura — nenhum botão aqui dispara analisa_edital.py (Camada 1) ou escreve no
Notion. Decisão explícita (16/jul/2026): o pipeline buscar→card→análise continua
manual, 1 ferramenta por vez (CLAUDE.md §17.8) — dashboard é público, não é lugar
pra disparar chamada de API/Claude/Notion sozinho.
"""

import plotly.express as px
import streamlit as st

from dashboard_common import (
    COR_STATUS_CRITICAL, COR_STATUS_GOOD, COR_STATUS_WARNING,
    carregar_editais_abertos, carregar_lat_lon, fmt_abrev, fundo_transparente,
)
from ui_explicacao import cabecalho_pagina, regra

st.title("🗂️ Radar de Editais")
cabecalho_pagina(
    pergunta="Quais editais com item de pneu estão com proposta aberta agora, e quanto "
    "tempo falta pra decidir participar?",
    fonte="Mesma base do Mercado PNCP (`analise/coletor_pncp_detalhe.py`), filtrada por "
    "situação 'Divulgada no PNCP' + prazo de proposta no futuro.",
)

with regra("ℹ️ Como esse Kanban decide o que é 'aberto'"):
    st.markdown(
        "Edital entra aqui quando **todas** as condições batem:\n\n"
        "- `situacao_compra_nome = 'Divulgada no PNCP'` (exclui Revogada/Suspensa/Anulada).\n"
        "- `data_encerramento_proposta` no futuro (comparado no momento em que a página "
        "carrega — o cache expira a cada 5min).\n"
        "- Pelo menos 1 item da descrição bate a heurística `eh_pneu_de_verdade()` (mesma "
        "regra da página Análise de mercado).\n\n"
        "- Modalidade **não é** Leilão — leilão é o órgão vendendo bem usado, não comprando "
        "(pneu ali é só especificação de um veículo sendo alienado, direção oposta do "
        "negócio).\n\n"
        "Colunas do Kanban agrupam por dias restantes até o encerramento — quanto mais perto "
        "de 0, mais urgente decidir. Retificação de edital (PNCP gera "
        "`numero_controle_pncp` novo pro mesmo processo) é deduplicada, mantendo a versão "
        "mais recente."
    )

editais = carregar_editais_abertos()
if editais.empty:
    st.info("Nenhum edital com pneu e proposta aberta no momento.")
    st.stop()

st.caption(f"{len(editais)} edital(is) aberto(s) com item de pneu.")

# Status (não categórico) — cor reservada de urgência, sempre com ícone+label junto
# (skill dataviz, "status color nunca sozinha"). Bucket mais perto de 0 = mais crítico.
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

st.subheader("Onde estão os editais abertos")
mapa_df = editais.dropna(subset=["codigo_ibge"]).merge(carregar_lat_lon(), on="codigo_ibge", how="left")
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
    st.caption(
        "Ainda só os editais — ponto de saída dos distribuidores entra depois que a "
        "localização de cada um for cadastrada no Notion."
    )

st.divider()
cols = st.columns(len(BUCKETS))
for col, (icone, titulo, subtitulo, cor, cond) in zip(cols, BUCKETS):
    with col:
        st.markdown(f"#### {icone} {titulo}")
        st.caption(subtitulo)
        bucket = editais[editais["dias_restantes"].apply(cond)]
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
                st.caption(f"**{row['orgao_nome']}** — {row['municipio']}/{row['uf']}")
                valor_txt = fmt_abrev(row["valor_total_estimado"])
                st.caption(f"R$ {valor_txt}" if valor_txt != "—" else "sem valor")
                st.link_button("Abrir no PNCP", row["pncp_url"], use_container_width=True)
                with st.expander("Detalhes"):
                    objeto = row["objeto_compra"] or "(sem objeto descrito)"
                    st.caption(objeto[:200] + ("…" if len(objeto) > 200 else ""))
                    data_fmt = row["data_encerramento_proposta"].strftime("%d/%m/%Y %H:%M")
                    st.caption(
                        f"{row['modalidade_licitacao_nome'] or '—'} · "
                        f"{int(row['n_itens_pneu'])} item(ns) pneu ({row['categorias'] or '—'}) · "
                        f"encerra {data_fmt}"
                    )
                    st.caption(f"Pra analisar: `python analisa_edital.py {row['cnpj_ano_seq']} <notion_id>`")

st.divider()
st.caption(
    "Análise (Camada 1) continua manual — copie o identificador acima e rode "
    "`analisa_edital.py` no terminal (ver CLAUDE.md §2). Nenhuma escrita acontece a partir "
    "deste dashboard."
)
