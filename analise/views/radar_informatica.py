#!/usr/bin/env python3
"""Página — Radar de Informática: editais ABERTOS e FUTUROS com periférico de
informática (19/nov/2026, pedido do usuário: "tal qual o radar de pneus, mesmos
critérios e mapa"). Selo GET retirado 26/nov/2026 a pedido do usuário — cobertura por
distribuidor agora vive em radar_fornecedor_informatica.py.

Igual ao radar de pneu (`radar_abertos.py`): filtros Região/UF/Modalidade/Categoria/
Regime/Portal/Custo, mapa por urgência, CAPAG, Kanban por dia de encerramento.
Diferenças deliberadas:
  - Prazo vem de `data_fim_vigencia` do search API (mesmo proxy do radar de Peças) —
    teto de 45 dias no Kanban, resto em "Vigência longa" (provável ata/credenciamento).
  - Inclui edital FUTURO (abertura de proposta ainda não chegou), marcado 🔜.

Só leitura — nenhum botão aqui dispara coletor/análise/Notion.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from conectar_informatica import carregar_editais_informatica, carregar_itens_informatica
from dashboard_common import (
    COR_STATUS_CRITICAL, COR_STATUS_GOOD, COR_STATUS_WARNING, ORDEM_REGIOES, REGIAO_POR_UF,
    capag_do_orgao, carregar_capag_estados, carregar_capag_municipios, carregar_lat_lon, cor_capag,
    custo_fornecedor, dominio_de, fmt_abrev, fundo_transparente, portal_de,
)
from fila import botoes_fila, carregar_fila, resumo_fila
from ui_explicacao import cabecalho_pagina, regra

WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
TETO_DIAS_KANBAN = 45
MAX_CARDS_POR_COLUNA = 8



@st.cache_data(ttl=300)
def _carregar() -> tuple[pd.DataFrame, pd.DataFrame]:
    itens = carregar_itens_informatica()
    return carregar_editais_informatica(itens), itens


st.title("💻 Radar de Informática")

cabecalho_pagina(
    pergunta="Quais editais de periférico de informática estão abertos (ou vão abrir)?",
    fonte="Busca direta na API do PNCP + itens de cada edital (`analise/coletor_informatica.py`), "
    "schema `informatica` — isolado do dado de pneu/onco/peças.",
)

with regra("ℹ️ Como o 'aberto' e o item de informática são decididos"):
    st.markdown(
        "**Aberto/futuro:** busca do PNCP com status *recebendo proposta*, situação "
        "'Divulgada no PNCP', não cancelado, não Leilão, prazo no futuro. 🔜 = abertura de "
        "proposta ainda não chegou.\n\n"
        "**Item de informática:** a descrição do item precisa **começar** pelo produto "
        "(nobreak, monitor, teclado, mouse, headset, projetor, SSD, computador...). Serviço, "
        "locação, toner, bateria avulsa, suporte, monitor médico ficam de fora "
        "(`filtro_informatica.py`).\n\n"
        "**Prazo:** `data_fim_vigencia` do search API (fase 1). Em SRP/credenciamento pode ser "
        "vigência de ata — por isso >45 dias vai pra coluna 'Vigência longa'.\n\n"
        "**CAPAG:** mesma regra do radar de pneu (município, senão estado). Risco de "
        "calote/atraso, nunca decide sozinho."
    )

editais, itens = _carregar()
if editais.empty:
    st.info("Nenhum edital de informática aberto na base ainda — coletor não rodou?")
    st.stop()

editais["regiao"] = editais["uf"].map(REGIAO_POR_UF)
editais["portal_dominio"] = editais["link_sistema_origem"].apply(dominio_de)
editais["portal"] = editais["portal_dominio"].apply(portal_de)
editais["custo_fornecedor"] = editais["portal_dominio"].apply(custo_fornecedor)

_capag_mun = carregar_capag_municipios()
_capag_uf = carregar_capag_estados()
MAPA_CAPAG_MUN = dict(zip(_capag_mun["codigo_ibge"], _capag_mun["capag"]))
MAPA_CAPAG_UF = dict(zip(_capag_uf["uf"], _capag_uf["capag"]))
FAIXAS_CAPAG = {COR_STATUS_GOOD: "🟢 A+/A", COR_STATUS_WARNING: "🟡 B+/B", COR_STATUS_CRITICAL: "🔴 C/D"}
_capag = editais.apply(
    lambda r: capag_do_orgao(r["codigo_ibge"], r["uf"], MAPA_CAPAG_MUN, MAPA_CAPAG_UF), axis=1
)
editais["capag"] = _capag.str[0]
editais["capag_origem"] = _capag.str[1]
editais["capag_faixa"] = editais["capag"].apply(lambda n: FAIXAS_CAPAG.get(cor_capag(n), "⚪ Sem dado"))

_total = len(editais)
# Base sem o toggle — denominador do "% interpretados" (precisa incluir os ⏳).
editais_base = editais
so_info = st.toggle(
    "Só editais com item de informática confirmado", value=True, key="so_info_radar_info",
    help="A busca do PNCP acha o termo em qualquer lugar (anexo, item de outra coisa). Ligado, "
    "mostra só edital com pelo menos 1 item classificado como informática — esconde também os "
    "que ainda não tiveram os itens coletados (⏳).",
)
if so_info:
    editais = editais[editais["n_itens_info"] > 0]
st.caption(f"{len(editais)} de {_total} editais abertos/futuros na base" +
           (" têm item de informática." if so_info else "."))

# Filtro padrão ao abrir (26/nov/2026, igual em todos os radares): Dispensa, portal grátis
# ou não identificado, CAPAG A+/A. Substitui o default "Nordeste". Só na
# 1ª carga da sessão — setdefault no session_state, não default= no widget.
_mods = sorted(editais["modalidade_licitacao_nome"].dropna().unique())
st.session_state.setdefault("mod_radar_info", [m for m in _mods if "dispensa" in m.lower()])
st.session_state.setdefault("custo_radar_info", ["Grátis", "Não identificado"])
st.session_state.setdefault("capag_radar_info", ["🟢 A+/A"])

c1, c2, c4 = st.columns(3)
with c1:
    regioes_disp = [r for r in ORDEM_REGIOES if r in set(editais["regiao"].dropna())]
    reg_sel = st.multiselect("Região", regioes_disp, key="regiao_radar_info")
with c2:
    ufs_disp = editais.loc[editais["regiao"].isin(reg_sel), "uf"] if reg_sel else editais["uf"]
    ufs_disp = sorted(ufs_disp.dropna().unique())
    if "uf_radar_info" in st.session_state:
        st.session_state["uf_radar_info"] = [u for u in st.session_state["uf_radar_info"] if u in ufs_disp]
    uf_sel = st.multiselect("UF", ufs_disp, key="uf_radar_info")
with c4:
    cats_disp = sorted({c.strip() for cs in editais["categorias"] for c in cs.split(",") if c.strip()})
    cat_sel = st.multiselect("Categoria de produto", cats_disp, key="cat_radar_info")

c5, c6, c7, c8, c9 = st.columns(5)
with c5:
    mod_sel = st.multiselect("Modalidade", _mods, key="mod_radar_info")
with c6:
    regime_sel = st.multiselect(
        "Regime", sorted(editais["regime"].dropna().unique()), key="regime_radar_info",
        help="RP = Registro de Preço (SRP) · CD = Compra Direta (sem SRP)",
    )
with c7:
    portal_sel = st.multiselect("Portal", sorted(editais["portal"].unique()), key="portal_radar_info")
with c8:
    custo_sel = st.multiselect(
        "Custo p/ fornecedor", ["Grátis", "Pago", "Não identificado"], key="custo_radar_info",
        help="Mesma pesquisa por portal do radar de pneu (06/ago/2026).",
    )
with c9:
    capag_sel = st.multiselect(
        "CAPAG", ["🟢 A+/A", "🟡 B+/B", "🔴 C/D", "⚪ Sem dado"], key="capag_radar_info",
        help="Capacidade de pagamento do Tesouro (município do órgão, senão estado) — risco de "
        "calote/atraso depois de vencer. Mesma regra do radar de pneu.",
    )



def _filtro_contexto(df: pd.DataFrame) -> pd.DataFrame:
    """Filtros que não dependem dos itens (geografia, modalidade, portal, CAPAG)."""
    if reg_sel:
        df = df[df["regiao"].isin(reg_sel)]
    if uf_sel:
        df = df[df["uf"].isin(uf_sel)]
    if mod_sel:
        df = df[df["modalidade_licitacao_nome"].isin(mod_sel)]
    if regime_sel:
        df = df[df["regime"].isin(regime_sel)]
    if portal_sel:
        df = df[df["portal"].isin(portal_sel)]
    if custo_sel:
        df = df[df["custo_fornecedor"].isin(custo_sel)]
    if capag_sel:
        df = df[df["capag_faixa"].isin(capag_sel)]
    return df


editais = _filtro_contexto(editais)
if cat_sel:
    editais = editais[editais["categorias"].apply(lambda s: any(c in s for c in cat_sel))]
_contexto = _filtro_contexto(editais_base)

if editais.empty:
    st.warning("Nenhum edital bate esses filtros.")
    st.stop()

# % interpretados = editais com itens já coletados e classificados, sobre todos os
# abertos/futuros da mesma região/UF/modalidade/portal/CAPAG (sem o toggle, que esconde os ⏳).
_pct_interp = _contexto["itens_coletados_em"].notna().mean() * 100 if len(_contexto) else 0
m1, m2 = st.columns(2)
m1.metric("Editais no filtro", len(editais))
m2.metric(
    "% de editais interpretados", f"{_pct_interp:.0f}%",
    help=f"{int(_contexto['itens_coletados_em'].notna().sum())} de {len(_contexto)} editais abertos/futuros "
    "nesse filtro já tiveram os itens lidos e classificados. O resto (⏳) entra na próxima coleta.",
)
FILA = carregar_fila("informatica")
resumo_fila(FILA)


BUCKETS = [
    ("🔴", "Urgente", COR_STATUS_CRITICAL, lambda d: d <= 2),
    ("🟡", "Esta semana", COR_STATUS_WARNING, lambda d: 2 < d <= 7),
    ("🟢", "Depois", COR_STATUS_GOOD, lambda d: d > 7),
]


def _bucket(d: float) -> tuple[str, str, str]:
    for icone, titulo, cor, cond in BUCKETS:
        if cond(d):
            return icone, titulo, cor
    return "❔", "Sem prazo", COR_STATUS_GOOD


editais["bucket_label"] = editais["dias_restantes"].apply(lambda d: " ".join(_bucket(d)[:2]))
CORES_BUCKET = {f"{i} {t}": c for i, t, c, _ in BUCKETS}

st.subheader("Onde estão os editais")
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
    fig_mapa = px.scatter_map(
        mapa_df, lat="latitude", lon="longitude", color="bucket_label",
        category_orders={"bucket_label": list(CORES_BUCKET)},
        color_discrete_map=CORES_BUCKET,
        hover_name="orgao_nome",
        hover_data={"municipio": True, "uf": True, "dias_restantes": ":.1f",
                    "categorias": True, "latitude": False, "longitude": False},
        center={"lat": mapa_df["latitude"].mean(), "lon": mapa_df["longitude"].mean()},
        zoom=zoom, map_style="carto-darkmatter",
    )
    fig_mapa.update_traces(marker=dict(size=12))
    fig_mapa.update_layout(height=500, margin=dict(l=0, r=0, t=0, b=0), legend_title_text="")
    fundo_transparente(fig_mapa)
    st.plotly_chart(fig_mapa, use_container_width=True)

st.divider()

contagem_orgao = editais["orgao_nome"].value_counts()
editais = editais.sort_values(["dias_restantes", "valor_info"], ascending=[True, False])
editais["data_dia"] = editais["data_fim_vigencia"].dt.date
editais_kanban = editais[editais["dias_restantes"] <= TETO_DIAS_KANBAN]
editais_longa = editais[editais["dias_restantes"] > TETO_DIAS_KANBAN]
itens_por_edital = dict(tuple(itens[itens["categoria"].notna()].groupby("numero_controle_pncp"))) \
    if not itens.empty else {}

_hoje = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).date()
dias_lista = [] if editais_kanban.empty else list(pd.date_range(_hoje, editais_kanban["data_dia"].max()).date)

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


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _render_card(row: pd.Series, cor: str) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div style="height:4px;background:{cor};border-radius:2px;margin-bottom:10px;"></div>',
            unsafe_allow_html=True,
        )
        st.metric("Encerra em", f"{row['dias_restantes']:.1f} dia(s)")
        if row["futuro"]:
            st.caption(f"🔜 Abre proposta em {row['data_inicio_vigencia']:%d/%m %H:%M}")
        orgao = row["orgao_nome"] + (" 🔁" if contagem_orgao.get(row["orgao_nome"], 0) > 1 else "")
        st.caption(f"**{orgao}** — {row['municipio']}/{row['uf']}")
        nota, origem = row["capag"], row["capag_origem"]
        if nota:
            c = cor_capag(nota)
            ic = "🟢" if c == COR_STATUS_GOOD else "🟡" if c == COR_STATUS_WARNING else "🔴"
            st.caption(f"{ic} CAPAG {nota} ({origem})")
        else:
            st.caption("⚪ CAPAG sem dado")
        if row["n_itens_info"]:
            st.caption(row["categorias"])
            if row["valor_info"] > 0:
                st.caption(f"Informática: R$ {fmt_abrev(row['valor_info'])}")
            else:
                st.caption("Sem valor estimado (sigiloso ou não informado)")
            if row["n_itens_info"] < row["n_itens_total"]:
                st.caption(f"⚠️ {row['n_itens_info']} de {row['n_itens_total']} itens são informática")
        st.caption(f"{row['portal']} · {row['custo_fornecedor']}")
        st.link_button("Abrir no PNCP", row["pncp_url"], use_container_width=True)
        botoes_fila(row, "informatica", FILA)
        with st.expander("Detalhes"):
            obj = str(row["objeto"] or "(sem objeto descrito)")
            st.caption(obj[:250] + ("…" if len(obj) > 250 else ""))
            st.caption(f"{row['modalidade_licitacao_nome'] or '—'} · {row['regime'] or '—'} · "
                       f"encerra {row['data_fim_vigencia']:%d/%m/%Y %H:%M}")
            it = itens_por_edital.get(row["numero_controle_pncp"])
            if it is not None:
                tab = it.assign(Descrição=it["descricao"].str[:90])
                st.dataframe(
                    tab[["numero_item", "categoria", "quantidade", "valor_unitario_estimado", "Descrição"]],
                    hide_index=True, use_container_width=True,
                    column_config={
                        "numero_item": "Item", "categoria": "Categoria", "quantidade": "Qtde",
                        "valor_unitario_estimado": st.column_config.NumberColumn("Unit. est.", format="R$ %.2f"),
                    },
                )


n_cols = len(dias_lista) + (1 if not editais_longa.empty else 0)
cols = st.columns(max(n_cols, 1))
for col, dia in zip(cols, dias_lista):
    with col:
        faltam = (dia - _hoje).days
        icone, _, cor = _bucket(faltam)
        st.markdown(f"#### {icone} {WEEKDAYS_PT[dia.weekday()]} {dia.strftime('%d/%m')}")
        st.caption("Encerra hoje" if faltam == 0 else "Falta 1 dia" if faltam == 1 else f"Faltam {faltam} dias")
        bucket = editais_kanban[editais_kanban["data_dia"] == dia]
        if bucket.empty:
            st.caption("Nenhum edital nesse dia.")
            continue
        if len(bucket) > MAX_CARDS_POR_COLUNA:
            st.caption(f"Mostrando {MAX_CARDS_POR_COLUNA} de {len(bucket)} — resto na tabela abaixo.")
        for _, row in bucket.head(MAX_CARDS_POR_COLUNA).iterrows():
            _render_card(row, cor)

if not editais_longa.empty:
    with cols[-1]:
        st.markdown(f"#### 📦 Vigência longa (>{TETO_DIAS_KANBAN}d)")
        st.caption("Provável vigência de ata/credenciamento, não fim de proposta — confirmar no link.")
        if len(editais_longa) > MAX_CARDS_POR_COLUNA:
            st.caption(f"Mostrando {MAX_CARDS_POR_COLUNA} de {len(editais_longa)} — resto na tabela abaixo.")
        for _, row in editais_longa.head(MAX_CARDS_POR_COLUNA).iterrows():
            _render_card(row, COR_STATUS_GOOD)

st.markdown("#### Lista completa")
st.caption(f"Todos os editais do filtro, o que encerra antes primeiro. O Kanban mostra só {MAX_CARDS_POR_COLUNA} por dia.")
tabela = editais
st.dataframe(
    tabela[[
        "data_fim_vigencia", "dias_restantes", "futuro", "uf", "municipio", "orgao_nome",
        "categorias", "n_itens_info", "valor_info", "modalidade_licitacao_nome", "regime",
        "portal", "objeto", "pncp_url",
    ]],
    hide_index=True,
    use_container_width=True,
    column_config={
        "data_fim_vigencia": st.column_config.DatetimeColumn("Encerra em", format="DD/MM/YYYY HH:mm"),
        "dias_restantes": st.column_config.NumberColumn("Dias", format="%.1f"),
        "futuro": st.column_config.CheckboxColumn("🔜"),
        "uf": "UF", "municipio": "Município", "orgao_nome": "Órgão", "categorias": "Categorias",
        "n_itens_info": "Itens info",
        "valor_info": st.column_config.NumberColumn("Valor informática (R$)", format="%.2f"),
        "modalidade_licitacao_nome": "Modalidade", "regime": "Regime", "portal": "Portal",
        "objeto": st.column_config.TextColumn("Objeto", width="large"),
        "pncp_url": st.column_config.LinkColumn("PNCP", display_text="Abrir"),
    },
)

st.divider()
st.caption(
    "Próximo passo de um edital: card no Notion + skill analise-de-edital, depois cotação com o "
    "distribuidor (ver Radar de Fornecedor → Informática). Nenhuma escrita acontece a partir deste dashboard."
)
