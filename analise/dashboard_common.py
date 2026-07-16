#!/usr/bin/env python3
"""
dashboard_common.py — Estilo, cores, loaders e filtro compartilhado entre as
páginas do dashboard (Mercado PNCP + Cotação Fornecedor). Nenhuma página
duplica isso — 1 dono só por helper.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from conectar_pncp import (
    carregar_base_pncp, carregar_editais_abertos as _carregar_editais_abertos,
    carregar_fornecedores_resultado, cobertura_por_uf, cobertura_pct,
)
from conectar_cotacao_master import (
    carregar_cotacoes as _carregar_cotacoes_master,
    carregar_aliases_pendentes_detalhe as _carregar_aliases_pendentes_detalhe,
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
CORES_CATEGORIA = {
    "Passeio":      "#2a78d6",
    "Caminhão":     "#1baf7a",
    "Moto":         "#eda100",
    "Agrícola":     "#008300",
    "Câmara de ar": "#4a3aa7",
}

CATEGORIAS_ABREV = {
    "RP - Pregão": "RP-Preg", "RP - Dispensa": "RP-Disp", "RP - Concorrência": "RP-Conc",
    "CD - Pregão": "CD-Preg", "CD - Dispensa": "CD-Disp", "CD - Concorrência": "CD-Conc",
}

# Paleta categórica validada (skill dataviz — references/palette.md), 8 hues em
# ordem fixa, sem substituição por cinza. Reusar aqui em vez de deixar o Plotly
# gerar cor default (achado 14/jul/2026, auditoria dataviz): qualquer gráfico
# com até 8 séries pega slot 1..N nessa ordem, nunca cor gerada/cíclica.
PALETA_CATEGORICA_8 = [
    "#2a78d6",  # 1 blue
    "#1baf7a",  # 2 aqua
    "#eda100",  # 3 yellow
    "#008300",  # 4 green
    "#4a3aa7",  # 5 violet
    "#e34948",  # 6 red
    "#e87ba4",  # 7 magenta
    "#eb6834",  # 8 orange
]

# Par diverging validado — blue↔red, meio neutro cinza (nunca um hue no meio,
# ver anti-patterns.md). Usado em prêmio/desconto regional (polaridade acima/
# abaixo de referência), não em heatmap de magnitude (isso é sequential).
DIVERGING_POLO_NEG = "#e34948"   # red  — abaixo da referência
DIVERGING_NEUTRO   = "#f0efec"   # meio — "nada" (light mode)
DIVERGING_POLO_POS = "#2a78d6"   # blue — acima da referência

COR_INK_DARK  = "#c3c2b7"
COR_GRID_DARK = "#3a3a37"

# Status palette (skill dataviz — references/palette.md, "fixed — never themed"):
# mesmo hex em claro/escuro, por definição — reservada pra estado (urgência,
# alerta), nunca reusada como cor categórica de série, sempre com ícone/label
# junto (nunca só a cor sozinha carrega o significado).
COR_STATUS_CRITICAL = "#d03b3b"
COR_STATUS_WARNING  = "#fab219"
COR_STATUS_GOOD      = "#0ca30c"


def cor_categorica_ordenada(rotulos_em_ordem: list[str]) -> dict[str, str]:
    """Mapa {rótulo: hex} pela ordem fixa da paleta validada — rótulo mais
    relevante (ranking já decidido por quem chama) pega slot 1, e assim por
    diante. Nunca deixar o Plotly gerar cor default pra série categórica."""
    return dict(zip(rotulos_em_ordem, PALETA_CATEGORICA_8))


def fundo_transparente(fig: go.Figure, tickformat_x: bool = True) -> go.Figure:
    """tickformat_x=False pra eixo X categórico (mês, categoria) — aplicar formato numérico
    (",.0f") num eixo de texto renderiza o literal ",0f" ao lado de cada rótulo (achado
    08/jul/26 no gráfico de tendência mensal por medida)."""
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color=COR_INK_DARK)
    if tickformat_x:
        fig.update_xaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK, tickformat=",.0f")
    else:
        fig.update_xaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK)
    fig.update_yaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK, tickformat=",.0f")
    return fig


def fmt_abrev(v: float) -> str:
    """Abrevia valor grande pra leitura rápida em tabela: 1,2 mi / 850 mil / 234."""
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
    s = s.replace(",", "@").replace(".", ",").replace("@", ".")  # troca separador en-US -> pt-BR sem colisão
    return f"{sinal}{s}{sufixo}"


def para_mil(v: float) -> float:
    """Valor em R$ mil, numérico de verdade (não string) — achado 08/jul/26: colunas
    formatadas como texto ("8 mil") quebravam ordenação/filtro nativo do st.dataframe
    (vira sort alfabético, não numérico). Cabeçalho da coluna deve dizer "(R$ mil)".
    Retorna float("nan") pra vazio, não None — None vira dtype object, reabre o mesmo
    bug (achado numa 2ª rodada: coluna com célula ausente virava "None" literal na tela)."""
    if pd.isna(v):
        return float("nan")
    return round(v / 1000, 1)


# ── Loaders — Mercado PNCP ──────────────────────────────────────────────────

@st.cache_data(ttl=300)
def carregar_base() -> pd.DataFrame:
    df = carregar_base_pncp()
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


@st.cache_data(ttl=300)
def carregar_editais_abertos() -> pd.DataFrame:
    return _carregar_editais_abertos()


@st.cache_data
def carregar_lat_lon() -> pd.DataFrame:
    ll = pd.read_csv(SQL_DIR / "municipios_lat_lon.csv")
    return ll[["codigo_ibge", "latitude", "longitude"]]


# ── Loaders — Cotação Fornecedor ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def carregar_cotacao_master() -> pd.DataFrame:
    return _carregar_cotacoes_master()


@st.cache_data(ttl=300)
def carregar_aliases_pendentes_detalhe() -> pd.DataFrame:
    return _carregar_aliases_pendentes_detalhe()


# ── Filtro compartilhado — Mercado PNCP ──────────────────────────────────────

def preparar_pagina_pncp():
    """Cabeçalho + sidebar de filtro + agregações compartilhadas (com_medida/
    top_medidas), chamado no topo de cada página Mercado PNCP. Streamlit reroda
    o script da página inteira a cada navegação — recalcular aqui é barato
    porque os loaders pesados já estão em @st.cache_data.

    Retorna None (via st.stop()) se não há dado — página que chamou não
    precisa tratar esse caso.
    """
    feito, total, pct = carregar_cobertura()
    st.caption(
        f"⚠️ Coleta em andamento: **{feito}/{total} processos ({pct:.1f}%)**. "
        "Recarregue a página (F5) pra ver dado mais recente — cache expira a cada 5min."
    )
    st.progress(min(pct / 100, 1.0))

    base = carregar_base()
    if base.empty:
        st.warning("Nenhum item elegível coletado ainda.")
        st.stop()

    st.sidebar.header("Filtros")

    ufs_disponiveis = sorted(base["uf"].dropna().unique())
    ufs_sel = st.sidebar.multiselect("UF", ufs_disponiveis, default=ufs_disponiveis)

    meses_disponiveis = sorted(base["ano_mes"].dropna().unique())
    if meses_disponiveis:
        # Padrão fixo jan/2026 até hoje (pedido 14/jul/26) — não o range inteiro
        # disponível, que inclui proposta futura agendada (ano_mes pode passar de
        # hoje) e histórico antigo pouco relevante pro dia a dia. Usuário ainda
        # pode arrastar o slider pra ver mais.
        hoje_str = date.today().strftime("%Y-%m")
        ini_default = next((m for m in meses_disponiveis if m >= "2026-01"), meses_disponiveis[0])
        fim_candidatos = [m for m in meses_disponiveis if m <= hoje_str]
        fim_default = max(fim_candidatos) if fim_candidatos else meses_disponiveis[-1]
        mes_ini, mes_fim = st.sidebar.select_slider(
            "Período (ano-mês)", options=meses_disponiveis,
            value=(ini_default, fim_default),
        )
    else:
        mes_ini, mes_fim = None, None

    categorias_disponiveis = sorted(base["categoria"].dropna().unique())
    categorias_sel = st.sidebar.multiselect("Categoria de produto", categorias_disponiveis, default=categorias_disponiveis)

    tipos_disponiveis = sorted(base["tipo"].dropna().unique())
    tipos_sel = st.sidebar.multiselect("Tipo (procedimento)", tipos_disponiveis, default=tipos_disponiveis)

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
        # achado 08/jul/26: "itens pedidos/vendidos" deve ser UNIDADE real de pneu
        # (quantidade), não contagem de linha de catálogo — 1 linha pode pedir 500 pneus,
        # outra 2. Contar linha mistura giro pequeno com giro grande no mesmo número.
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
