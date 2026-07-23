#!/usr/bin/env python3
"""
dashboard_common_onco.py — Estilo, cores, loaders e filtro compartilhado entre
as páginas do dashboard de oncologia. Espelha analise/dashboard_common.py —
mesmas constantes de paleta (validada, skill dataviz — brand-neutral, não
pneu-específica, reaproveitada verbatim) e mesma função de filtro/sidebar.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from conectar_onco import (
    carregar_base_onco, carregar_capag_estados as _carregar_capag_estados,
    carregar_capag_municipios as _carregar_capag_municipios,
    carregar_editais_abertos_onco as _carregar_editais_abertos_onco,
    carregar_fornecedores_resultado,
    carregar_itens_onco_editais_abertos as _carregar_itens_onco_editais_abertos,
    carregar_lat_lon, cobertura_por_uf, cobertura_pct,
    ultima_carga_detalhes as _ultima_carga_detalhes,
)

SQL_DIR = Path(__file__).parent

CORES_REGIME_TIPO = {
    "RP - Pregão":       "#2a78d6",
    "RP - Dispensa":     "#1baf7a",
    "RP - Concorrência": "#eda100",
    "RP - Outro":        "#898781",
    "CD - Pregão":       "#008300",
    "CD - Dispensa":     "#4a3aa7",
    "CD - Concorrência": "#e34948",
    "CD - Outro":        "#e87ba4",
}

# 6 classes farmacológicas fixas — mesmo padrão de categoria fixa do pneu
# (Passeio/Caminhão/Moto/Agrícola/Câmara de ar), mesma paleta validada.
CORES_CLASSE_FARMACO = {
    "Quimioterapico classico":            "#2a78d6",
    "Inibidor de quinase/alvo molecular":  "#1baf7a",
    "Anticorpo monoclonal":                "#eda100",
    "Antimetabolito":                      "#008300",
    "Alquilante":                          "#4a3aa7",
    "Hormonal/endocrino":                  "#e34948",
    "Outro":                               "#898781",
}

CATEGORIAS_ABREV = {
    "RP - Pregão": "RP-Preg", "RP - Dispensa": "RP-Disp", "RP - Concorrência": "RP-Conc",
    "CD - Pregão": "CD-Preg", "CD - Dispensa": "CD-Disp", "CD - Concorrência": "CD-Conc",
}

PALETA_CATEGORICA_8 = [
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]

DIVERGING_POLO_NEG = "#e34948"
DIVERGING_NEUTRO   = "#f0efec"
DIVERGING_POLO_POS = "#2a78d6"

COR_INK_DARK  = "#c3c2b7"
COR_GRID_DARK = "#3a3a37"

# Status palette (skill dataviz) — mesma constante do analise/dashboard_common.py,
# reservada pra estado/urgência, sempre com ícone+label junto.
COR_STATUS_CRITICAL = "#d03b3b"
COR_STATUS_WARNING  = "#fab219"
COR_STATUS_GOOD      = "#0ca30c"


def cor_categorica_ordenada(rotulos_em_ordem: list[str]) -> dict[str, str]:
    return dict(zip(rotulos_em_ordem, PALETA_CATEGORICA_8))


def fundo_transparente(fig: go.Figure, tickformat_x: bool = True) -> go.Figure:
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color=COR_INK_DARK)
    if tickformat_x:
        fig.update_xaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK, tickformat=",.0f")
    else:
        fig.update_xaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK)
    fig.update_yaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK, tickformat=",.0f")
    return fig


def fmt_abrev(v: float) -> str:
    if pd.isna(v):
        return "—"
    sinal = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        s, sufixo = f"{v / 1_000_000:,.1f}", " mi"
    elif v >= 1_000:
        s, sufixo = f"{v / 1_000:,.0f}", " mil"
    else:
        s, sufixo = f"{v:,.0f}", ""
    s = s.replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{sinal}{s}{sufixo}"


def para_mil(v: float) -> float:
    if pd.isna(v):
        return float("nan")
    return round(v / 1000, 1)


# ── Loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def carregar_base() -> pd.DataFrame:
    df = carregar_base_onco()
    df["regime_tipo"] = df["regime"] + " - " + df["tipo"]
    return df


@st.cache_data(ttl=300)
def carregar_fornecedores() -> pd.DataFrame:
    return carregar_fornecedores_resultado()


@st.cache_data(ttl=300)
def carregar_cobertura():
    return cobertura_pct()


@st.cache_data(ttl=300)
def carregar_cobertura_uf() -> pd.DataFrame:
    return cobertura_por_uf()


@st.cache_data
def carregar_lat_lon_cached() -> pd.DataFrame:
    return carregar_lat_lon()


@st.cache_data(ttl=300)
def carregar_editais_abertos_onco() -> pd.DataFrame:
    return _carregar_editais_abertos_onco()


@st.cache_data(ttl=300)
def carregar_itens_onco_editais_abertos(numeros_controle: tuple[str, ...]) -> pd.DataFrame:
    return _carregar_itens_onco_editais_abertos(list(numeros_controle))


@st.cache_data(ttl=300)
def carregar_ultima_carga_detalhes() -> pd.Timestamp | None:
    return _ultima_carga_detalhes()


@st.cache_data(ttl=3600)
def carregar_capag_municipios() -> pd.DataFrame:
    return _carregar_capag_municipios()


@st.cache_data(ttl=3600)
def carregar_capag_estados() -> pd.DataFrame:
    return _carregar_capag_estados()


_CAPAG_SEM_DADO = {"#N/A", "n.d.", "n.e.", None}
_CAPAG_BOA   = {"A+", "A"}
_CAPAG_MEDIA = {"B+", "B"}
_CAPAG_RUIM  = {"C", "D"}


def cor_capag(nota: str | None) -> str | None:
    if nota in _CAPAG_BOA:
        return COR_STATUS_GOOD
    if nota in _CAPAG_MEDIA:
        return COR_STATUS_WARNING
    if nota in _CAPAG_RUIM:
        return COR_STATUS_CRITICAL
    return None


def capag_do_orgao(codigo_ibge, uf: str | None, mapa_mun: dict, mapa_uf: dict) -> tuple[str | None, str]:
    """Espelha dashboard_common.capag_do_orgao() do pneu."""
    if codigo_ibge is not None and not pd.isna(codigo_ibge):
        nota = mapa_mun.get(int(codigo_ibge))
        if nota is not None and nota not in _CAPAG_SEM_DADO:
            return nota, "município"
    if uf:
        nota = mapa_uf.get(uf)
        if nota is not None and nota not in _CAPAG_SEM_DADO:
            return nota, "estado"
    return None, ""


# ── Filtro compartilhado ──────────────────────────────────────────────────

def preparar_pagina_onco():
    """Cabeçalho + sidebar de filtro + agregações compartilhadas, espelhando
    preparar_pagina_pncp() do pneu — filtro por UF/período/classe farmaco/
    tipo/regime, aplicado em todas as páginas do grupo Mercado Oncológico."""
    feito, total, pct = carregar_cobertura()
    st.caption(
        f"⚠️ Coleta em andamento: **{feito}/{total} processos ({pct:.1f}%)**. "
        "Recarregue a página (F5) pra ver dado mais recente — cache expira a cada 5min."
    )
    st.progress(min(pct / 100, 1.0))

    ultima_carga = carregar_ultima_carga_detalhes()
    if ultima_carga is not None:
        st.caption(f"📥 Dado carregado até: {ultima_carga.strftime('%d/%m/%Y %H:%M')} (BRT)")

    base = carregar_base()
    if base.empty:
        st.warning("Nenhum item elegível coletado ainda.")
        st.stop()

    st.sidebar.header("Filtros")

    ufs_disponiveis = sorted(base["uf"].dropna().unique())
    ufs_sel = st.sidebar.multiselect("UF", ufs_disponiveis, default=ufs_disponiveis)

    meses_disponiveis = sorted(base["ano_mes"].dropna().unique())
    if meses_disponiveis:
        hoje_str = date.today().strftime("%Y-%m")
        fim_candidatos = [m for m in meses_disponiveis if m <= hoje_str]
        fim_default = max(fim_candidatos) if fim_candidatos else meses_disponiveis[-1]
        mes_ini, mes_fim = st.sidebar.select_slider(
            "Período (ano-mês)", options=meses_disponiveis,
            value=(meses_disponiveis[0], fim_default),
        )
    else:
        mes_ini, mes_fim = None, None

    categorias_disponiveis = sorted(base["categoria"].dropna().unique())
    categorias_sel = st.sidebar.multiselect("Classe farmacológica", categorias_disponiveis, default=categorias_disponiveis)

    tipos_disponiveis = sorted(base["tipo"].dropna().unique())
    tipos_sel = st.sidebar.multiselect("Tipo (modalidade)", tipos_disponiveis, default=tipos_disponiveis)

    regimes_disponiveis = sorted(base["regime"].dropna().unique())
    regimes_sel = st.sidebar.multiselect("Regime", regimes_disponiveis, default=regimes_disponiveis)

    df = base[
        base["uf"].isin(ufs_sel)
        & base["categoria"].isin(categorias_sel)
        & base["tipo"].isin(tipos_sel)
        & base["regime"].isin(regimes_sel)
    ]
    if mes_ini and mes_fim:
        df = df[(df["ano_mes"] >= mes_ini) & (df["ano_mes"] <= mes_fim)]

    if df.empty:
        st.warning("Nenhum dado para os filtros selecionados.")
        st.stop()

    base_forn = carregar_fornecedores()
    df_forn = base_forn[
        base_forn["uf"].isin(ufs_sel)
        & base_forn["categoria"].isin(categorias_sel)
        & base_forn["tipo"].isin(tipos_sel)
        & base_forn["regime"].isin(regimes_sel)
    ]
    if mes_ini and mes_fim:
        df_forn = df_forn[(df_forn["ano_mes"] >= mes_ini) & (df_forn["ano_mes"] <= mes_fim)]

    processo = df.groupby("cod_compra")["valor_item"].sum().reset_index(name="valor_processo")
    col1, col2, col3 = st.columns(3)
    col1.metric("Processos", f"{processo.shape[0]:,}")
    col2.metric("Valor total", f"R$ {processo['valor_processo'].sum():,.0f}")
    col3.metric("Ticket médio", f"R$ {processo['valor_processo'].mean():,.0f}")

    com_medida = df.dropna(subset=["medida_extraida"]).copy()
    cobertura_medida = len(com_medida) / len(df) * 100 if len(df) else 0
    if not com_medida.empty:
        com_medida["qtd_vendida"] = com_medida["quantidade"].where(com_medida["tem_resultado"], 0)
        top_medidas = (
            com_medida.groupby("medida_extraida", as_index=False)
                      .agg(n_itens=("quantidade", "sum"), n_vendidos=("qtd_vendida", "sum"),
                           valor_total=("valor_item", "sum"))
                      .sort_values("n_itens", ascending=False)
                      .head(15)
        )
        top_medidas["n_itens"] = top_medidas["n_itens"].round().astype("int64")
        top_medidas["n_vendidos"] = top_medidas["n_vendidos"].round().astype("int64")
        top_medidas["valor_total"] = top_medidas["valor_total"].round().astype("int64")
        top_medidas_nomes_8 = pd.Index(top_medidas.sort_values("n_itens", ascending=False).head(8)["medida_extraida"])
    else:
        top_medidas = pd.DataFrame(columns=["medida_extraida", "n_itens", "valor_total"])
        top_medidas_nomes_8 = pd.Index([])

    return df, df_forn, cobertura_medida, com_medida, top_medidas, top_medidas_nomes_8
