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
        "- Item de pneu com `valor_unitário estimado` acima de R$50 mil é descartado — "
        "mesmo teto que a página Análise de mercado usa pra pegar erro de digitação no "
        "PNCP (achado real 16/jul/2026: câmara de ar de R$521 mil/unidade).\n\n"
        "Colunas do Kanban agrupam por dias restantes até o encerramento — quanto mais perto "
        "de 0, mais urgente decidir. Retificação de edital (PNCP gera "
        "`numero_controle_pncp` novo pro mesmo processo) é deduplicada, mantendo a versão "
        "mais recente. **Valor do card é a soma só dos itens de pneu**, não o valor total do "
        "processo (que pode incluir item não-pneu junto) — quando o processo tem outros "
        "itens além de pneu, aparece o aviso '⚠️ N de M itens são pneu'."
    )

editais = carregar_editais_abertos()
if editais.empty:
    st.info("Nenhum edital com pneu e proposta aberta no momento.")
    st.stop()

col_uf, col_mod, col_cat, col_regime = st.columns(4)
with col_uf:
    uf_sel = st.multiselect("UF", sorted(editais["uf"].dropna().unique()), key="uf_radar")
with col_mod:
    mod_sel = st.multiselect(
        "Modalidade", sorted(editais["modalidade_licitacao_nome"].dropna().unique()), key="mod_radar"
    )
with col_cat:
    cats_disp = sorted({c.strip() for cs in editais["categorias"].dropna() for c in cs.split(",")})
    cat_sel = st.multiselect("Categoria de produto", cats_disp, key="cat_radar")
with col_regime:
    regime_sel = st.multiselect(
        "Regime", sorted(editais["regime"].dropna().unique()), key="regime_radar",
        help="RP = Registro de Preço (SRP) · CD = Compra Direta (sem SRP)",
    )

if uf_sel:
    editais = editais[editais["uf"].isin(uf_sel)]
if mod_sel:
    editais = editais[editais["modalidade_licitacao_nome"].isin(mod_sel)]
if regime_sel:
    editais = editais[editais["regime"].isin(regime_sel)]
if cat_sel:
    editais = editais[editais["categorias"].fillna("").apply(lambda s: any(c in s for c in cat_sel))]

if editais.empty:
    st.warning("Nenhum edital aberto bate esses filtros.")
    st.stop()

st.caption(f"{len(editais)} edital(is) aberto(s) com item de pneu, nesse filtro.")

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

# achado 16/jul/2026 (EDA real): mesmo órgão com 2+ editais de pneu abertos ao mesmo
# tempo é sinal de comprador recorrente — vale relacionamento, não só oportunidade pontual.
contagem_orgao = editais["orgao_nome"].value_counts()

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
                orgao_label = row["orgao_nome"]
                if contagem_orgao.get(row["orgao_nome"], 0) > 1:
                    orgao_label += " 🔁"
                st.caption(f"**{orgao_label}** — {row['municipio']}/{row['uf']}")
                valor_txt = fmt_abrev(row["valor_pneu_estimado"])
                st.caption(f"R$ {valor_txt} em itens de pneu" if valor_txt != "—" else "sem valor")
                n_pneu, n_total = int(row["n_itens_pneu"]), int(row["n_itens_total"])
                if n_pneu < n_total:
                    st.caption(f"⚠️ {n_pneu} de {n_total} itens são pneu — resto do edital é outra coisa")
                st.link_button("Abrir no PNCP", row["pncp_url"], use_container_width=True)
                with st.expander("Detalhes"):
                    objeto = row["objeto_compra"] or "(sem objeto descrito)"
                    st.caption(objeto[:200] + ("…" if len(objeto) > 200 else ""))
                    data_fmt = row["data_encerramento_proposta"].strftime("%d/%m/%Y %H:%M")
                    st.caption(
                        f"{row['modalidade_licitacao_nome'] or '—'} · "
                        f"{n_pneu} de {n_total} item(ns) são pneu ({row['categorias'] or '—'}) · "
                        f"encerra {data_fmt}"
                    )
                    valor_proc_txt = fmt_abrev(row["valor_total_estimado"])
                    st.caption(
                        f"Valor estimado do processo inteiro (todos os itens): "
                        f"R$ {valor_proc_txt}" if valor_proc_txt != "—" else "Valor do processo: sem dado"
                    )
                    if contagem_orgao.get(row["orgao_nome"], 0) > 1:
                        st.caption(
                            f"🔁 Esse órgão tem {contagem_orgao[row['orgao_nome']]} editais de pneu "
                            "abertos agora, nesse filtro."
                        )
                    st.caption(f"Pra analisar: `python analisa_edital.py {row['cnpj_ano_seq']} <notion_id>`")

st.divider()
st.caption(
    "Análise (Camada 1) continua manual — copie o identificador acima e rode "
    "`analisa_edital.py` no terminal (ver CLAUDE.md §2). Nenhuma escrita acontece a partir "
    "deste dashboard."
)
