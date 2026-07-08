#!/usr/bin/env python3
"""
dashboard_pncp.py — Dashboard de mercado de pneu, fonte: coleta direta PNCP
(pncp_raw.db), cobertura nacional (27 UFs) mas parcial — coleta roda em
background via coletor_pncp_detalhe.py. Re-rodar este dashboard a qualquer
momento reflete o que já foi baixado, sem precisar mudar código.

Uso:
    streamlit run dashboard_pncp.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from conectar_pncp import carregar_base_pncp, carregar_fornecedores_resultado, cobertura_por_uf, cobertura_pct

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

COR_INK_DARK  = "#c3c2b7"
COR_GRID_DARK = "#3a3a37"


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


@st.cache_data
def carregar_lat_lon() -> pd.DataFrame:
    ll = pd.read_csv(SQL_DIR / "municipios_lat_lon.csv")
    return ll[["codigo_ibge", "latitude", "longitude"]]


def main() -> None:
    st.set_page_config(page_title="Mercado de Pneu — PNCP (auditado)", layout="wide")
    st.title("Mercado de pneu em licitação pública — PNCP direto")

    feito, total, pct = carregar_cobertura()
    st.caption(
        f"Fonte: API PNCP (coleta direta, todas as 27 UFs — sem o gap ~17x do ComprasGOV bulk). "
        f"⚠️ Coleta em andamento: **{feito}/{total} processos ({pct:.1f}%)**. "
        "Recarregue a página (F5) pra ver dado mais recente — cache expira a cada 5min."
    )
    st.progress(min(pct / 100, 1.0))

    base = carregar_base()
    if base.empty:
        st.warning("Nenhum item elegível coletado ainda.")
        return

    # ── Sidebar: filtros ────────────────────────────────────────────────
    st.sidebar.header("Filtros")

    ufs_disponiveis = sorted(base["uf"].dropna().unique())
    ufs_sel = st.sidebar.multiselect("UF", ufs_disponiveis, default=ufs_disponiveis)

    meses_disponiveis = sorted(base["ano_mes"].dropna().unique())
    if meses_disponiveis:
        mes_ini, mes_fim = st.sidebar.select_slider(
            "Período (ano-mês)", options=meses_disponiveis,
            value=(meses_disponiveis[0], meses_disponiveis[-1]),
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
        return

    # base separada, granularidade fornecedor (aceita fan-out de propósito — cota principal
    # + reservada no mesmo item são 2 fornecedores reais — nunca usar pra somar valor_item).
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

    # calculado 1x, reusado nas abas "Onde Entrar" (preço de referência) e "Produto"
    # (medidas mais pedidas) — evita duplicar a mesma agregação em 2 lugares.
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
        # achado 08/jul/26 auditando lógica do dashboard: usava value_counts() (contagem de
        # LINHA de catálogo) em vez de somar quantidade — divergia do ranking correto de
        # top_medidas em 6 das 8 medidas (ex: omitia "20.5-25", 2ª medida mais vendida em
        # volume real com 80mil unidades, e mostrava "12.5-80" no lugar por ter mais linhas
        # pequenas). Preço de referência/mapa de calor são a ferramenta central de "onde
        # entrar" — usar o mesmo ranking por quantidade da tabela Produto.
        top_medidas_nomes_8 = pd.Index(top_medidas.sort_values("n_itens", ascending=False).head(8)["medida_extraida"])
    else:
        top_medidas = pd.DataFrame(columns=["medida_extraida", "n_itens", "valor_total"])
        top_medidas_nomes_8 = pd.Index([])

    aba_entrar, aba_produto, aba_sazon, aba_forn = st.tabs(
        ["🎯 Análise de mercado", "📦 Produto", "📅 Sazonalidade", "🏭 Fornecedores e Preço"]
    )

    # ── Aba Onde Entrar ──────────────────────────────────────────────────
    # Ordem = funil de decisão: 1) tamanho do mercado, 2) dinâmica de preço por
    # tipo, 3) onde paga bem pelo mesmo produto (prêmio regional), 4) quem já
    # domina, 5) detalhe fino por município. Não é ordem cronológica de quando
    # cada gráfico foi construído — é a ordem em que a pergunta "onde eu entro"
    # precisa ser respondida.
    with aba_entrar:
        agg = (
            df.groupby(["uf", "regime_tipo"], as_index=False)
              .agg(valor_total=("valor_item", "sum"), n_processos=("cod_compra", "nunique"))
        )
        agg["valor_total"] = agg["valor_total"].round().astype("int64")

        metrica_geo = st.radio("Métrica:", ["Valor (R$)", "Nº de processos"], horizontal=True, key="metrica_geo")
        col_geo = "valor_total" if metrica_geo == "Valor (R$)" else "n_processos"
        ordem_uf = agg.groupby("uf")[col_geo].sum().sort_values(ascending=False).index.tolist()

        fig = px.bar(
            agg, x=col_geo, y="uf", color="regime_tipo", orientation="h",
            category_orders={"uf": ordem_uf[::-1], "regime_tipo": list(CORES_REGIME_TIPO)},
            color_discrete_map=CORES_REGIME_TIPO,
            labels={col_geo: metrica_geo, "uf": "UF", "regime_tipo": "Regime - Tipo"},
            title=f"{metrica_geo} de licitação de pneu por UF, RP x CD x tipo (PNCP direto)",
        )
        # achado 08/jul/26: altura default do plotly (~450px) cabe só ~14-15 barras de UF —
        # com as 27 UFs possíveis, as do meio (ex: MG) ficavam cortadas fora da área visível
        # da figura, não só escondidas por scroll. Altura proporcional ao nº de categorias
        # no eixo Y garante que todas as UFs selecionadas apareçam sempre.
        # Sem rótulo de valor aqui de propósito — 27 UF x até 6 segmentos empilhados vira
        # ilegível; a tabela logo abaixo já dá o número exato de cada célula.
        fig.update_layout(barmode="stack", legend_title_text="", height=max(450, 28 * len(ordem_uf)))
        fundo_transparente(fig)
        st.plotly_chart(fig, use_container_width=True)

        seis_cat = agg[agg["regime_tipo"].isin(CATEGORIAS_ABREV)]
        pivot_n = seis_cat.pivot(index="uf", columns="regime_tipo", values="n_processos").fillna(0)
        pivot_v = seis_cat.pivot(index="uf", columns="regime_tipo", values="valor_total").fillna(0)
        for cat in CATEGORIAS_ABREV:
            if cat not in pivot_n.columns:
                pivot_n[cat] = 0
            if cat not in pivot_v.columns:
                pivot_v[cat] = 0.0

        tabelao = pd.DataFrame(index=pivot_n.index)
        tabelao["Total Processos"] = pivot_n[list(CATEGORIAS_ABREV)].sum(axis=1).astype(int)
        tabelao["Valor Licitado (R$ mil)"] = pivot_v[list(CATEGORIAS_ABREV)].sum(axis=1).round().astype("int64")
        for cat, abrev in CATEGORIAS_ABREV.items():
            tabelao[f"{abrev} (n)"] = pivot_n[cat].astype(int)
            tabelao[f"{abrev} (R$ mil)"] = pivot_v[cat].round().astype("int64")
        tabelao = tabelao.sort_values("Valor Licitado (R$ mil)", ascending=False).reset_index().rename(columns={"uf": "Estado"})

        cov_uf = carregar_cobertura_uf().set_index("uf")["cobertura_pct"]
        tabelao["Cobertura %"] = tabelao["Estado"].map(cov_uf)
        cols_ordenadas = ["Estado", "Cobertura %"] + [c for c in tabelao.columns if c not in ("Estado", "Cobertura %")]
        tabelao = tabelao[cols_ordenadas]

        colunas_r_tabelao = ["Valor Licitado (R$ mil)"] + [f"{a} (R$ mil)" for a in CATEGORIAS_ABREV.values()]
        tabelao_fmt = tabelao.copy()
        for c in colunas_r_tabelao:
            tabelao_fmt[c] = tabelao_fmt[c].apply(para_mil)
        st.dataframe(
            tabelao_fmt, use_container_width=True, hide_index=True,
            column_config={"Cobertura %": st.column_config.ProgressColumn("Cobertura %", min_value=0, max_value=100, format="%.0f%%")},
        )
        st.caption(
            "⚠️ Cobertura % = quanto da coleta daquela UF já foi baixado. UF com cobertura baixa "
            "aparece artificialmente pequena no valor/processos acima — não é o tamanho real do mercado ainda."
        )
        st.download_button(
            "Baixar CSV", tabelao.to_csv(index=False).encode("utf-8-sig"),
            "geografia_uf_pncp.csv", "text/csv",
        )

        st.divider()
        col_desc, col_ticket = st.columns([1, 2])

        # achado 08/jul/26: "= None" pra coluna ausente (quando o filtro deixa só 1 tipo,
        # ex: só Dispensa) virava dtype object (Python None), não NaN float — Streamlit
        # quebrava com "TypeError: Expected numeric dtype, got object instead." ao tentar
        # renderizar/ordenar. float("nan") mantém dtype numérico mesmo com célula vazia.
        combos_rt = ["RP - Dispensa", "RP - Pregão", "CD - Dispensa", "CD - Pregão"]

        with col_desc:
            st.subheader("Desconto por regime x tipo")
            preco_regime = df.dropna(subset=["valor_unitario_estimado", "valor_unitario_resultado"])
            # valor_unitario_estimado <= R$1 é placeholder simbólico do órgão (sem preço de
            # referência real publicado) — dividir por isso explode a % de desconto. Excluído.
            preco_regime = preco_regime[preco_regime["valor_unitario_estimado"] > 1]
            if preco_regime.empty:
                st.info("Sem item com valor estimado + resultado nesse filtro.")
            else:
                preco_regime = preco_regime.copy()
                preco_regime["desconto_pct"] = (1 - preco_regime["valor_unitario_resultado"] / preco_regime["valor_unitario_estimado"]) * 100
                desconto_rt = preco_regime.groupby("regime_tipo")["desconto_pct"].median()
                col_a, col_b = st.columns(2)
                for i, combo in enumerate(combos_rt):
                    valor = f"{desconto_rt[combo]:.1f}%" if combo in desconto_rt.index else "sem dado"
                    (col_a if i % 2 == 0 else col_b).metric(f"Desconto — {combo}", valor)
                st.caption(
                    f"Amostra: {len(preco_regime)} itens (mediana — média é sensível a outlier de preço mal "
                    "publicado). Referência: fórmula de leilão assume 20% de margem."
                )

        with col_ticket:
            st.subheader("Ticket mediano por UF — RP x CD, Dispensa x Pregão")
            st.caption(
                "Mediana, não média — dispensa por valor tem teto ~R$50-60k (Lei 14.133/21), mas outras "
                "hipóteses do Art. 75 não têm teto. Poucos processos grandes distorcem a média em UF com "
                "amostra pequena; mediana não sofre isso."
            )
            tm = (
                df.groupby(["uf", "regime_tipo", "cod_compra"], as_index=False)["valor_item"].sum()
                  .groupby(["uf", "regime_tipo"], as_index=False)["valor_item"].median()
                  .rename(columns={"valor_item": "ticket_mediano"})
            )
            tm_pivot = tm[tm["regime_tipo"].isin(combos_rt)].pivot(index="uf", columns="regime_tipo", values="ticket_mediano")
            for col in combos_rt:
                if col not in tm_pivot.columns:
                    tm_pivot[col] = float("nan")
            tm_pivot = tm_pivot.round(0)

            preco_uf = df.dropna(subset=["valor_unitario_estimado", "valor_unitario_resultado"])
            preco_uf = preco_uf[preco_uf["valor_unitario_estimado"] > 1].copy()  # exclui R$0,01 simbólico
            if not preco_uf.empty:
                preco_uf["desconto_pct"] = (1 - preco_uf["valor_unitario_resultado"] / preco_uf["valor_unitario_estimado"]) * 100
                desconto_rt_uf = (
                    preco_uf[preco_uf["regime_tipo"].isin(combos_rt)]
                    .groupby(["uf", "regime_tipo"])["desconto_pct"].median()
                    .unstack("regime_tipo")
                )
                for col in combos_rt:
                    if col not in desconto_rt_uf.columns:
                        desconto_rt_uf[col] = float("nan")
                for combo in combos_rt:
                    tm_pivot[f"Desconto {combo} (%)"] = desconto_rt_uf[combo].round(1)
            else:
                for combo in combos_rt:
                    tm_pivot[f"Desconto {combo} (%)"] = float("nan")

            tm_pivot = tm_pivot.sort_values("RP - Pregão", ascending=False, na_position="last")
            tm_pivot_fmt = tm_pivot.reset_index().rename(columns={"uf": "UF", **{c: f"Ticket {c} (R$ mil)" for c in combos_rt}})
            for c in [f"Ticket {combo} (R$ mil)" for combo in combos_rt]:
                tm_pivot_fmt[c] = tm_pivot_fmt[c].apply(para_mil)
            st.dataframe(tm_pivot_fmt, use_container_width=True, hide_index=True, height=350)
            st.caption("Desconto mediano: exclui preço de referência simbólico (R$0,01).")

        st.divider()
        st.subheader("Fornecedor dominante")
        vencidos_geo = df_forn.dropna(subset=["nome_fornecedor"])
        if vencidos_geo.empty:
            st.info("Sem item com resultado nesse filtro.")
        else:
            por_forn_br = vencidos_geo.groupby("nome_fornecedor", as_index=False).agg(
                valor_total_resultado=("valor_total_resultado", "sum"),
                editais=("numero_controle_pncp", "nunique"),
                itens=("quantidade", "sum"),
            )
            total_br = por_forn_br["valor_total_resultado"].sum()
            top15_br = por_forn_br.sort_values("valor_total_resultado", ascending=False).head(15).copy()
            top15_br["participacao_pct"] = (top15_br["valor_total_resultado"] / total_br * 100).round().astype("int64")
            top15_br["Ranking"] = range(1, len(top15_br) + 1)
            top15_br["valor_total_resultado"] = top15_br["valor_total_resultado"].apply(para_mil)
            top15_br = top15_br.rename(columns={
                "nome_fornecedor": "Fornecedor", "valor_total_resultado": "Valor ganho (R$ mil)", "participacao_pct": "% do total BR",
                "editais": "Editais ganhos", "itens": "Itens vendidos",
            })[["Ranking", "Fornecedor", "Valor ganho (R$ mil)", "% do total BR", "Editais ganhos", "Itens vendidos"]]

            por_uf_forn = vencidos_geo.groupby(["uf", "nome_fornecedor"], as_index=False).agg(
                valor_total_resultado=("valor_total_resultado", "sum"),
                editais=("numero_controle_pncp", "nunique"),
                itens=("quantidade", "sum"),
            )
            total_uf = por_uf_forn.groupby("uf")["valor_total_resultado"].transform("sum")
            por_uf_forn["participacao_pct"] = (por_uf_forn["valor_total_resultado"] / total_uf * 100).round().astype("int64")
            top15_uf = (
                por_uf_forn.sort_values(["uf", "valor_total_resultado"], ascending=[True, False])
                           .groupby("uf").head(15)
            )
            top15_uf["Ranking"] = top15_uf.groupby("uf").cumcount() + 1
            top15_uf["valor_total_resultado"] = top15_uf["valor_total_resultado"].apply(para_mil)
            top15_uf = top15_uf.rename(columns={
                "uf": "UF", "nome_fornecedor": "Fornecedor",
                "valor_total_resultado": "Valor ganho (R$ mil)", "participacao_pct": "% do valor da UF",
                "editais": "Editais ganhos", "itens": "Itens vendidos",
            })[["UF", "Ranking", "Fornecedor", "Valor ganho (R$ mil)", "% do valor da UF", "Editais ganhos", "Itens vendidos"]]

            col_forn_br, col_forn_uf = st.columns(2)
            with col_forn_br:
                st.caption("Top 15 — Brasil:")
                st.dataframe(top15_br, use_container_width=True, hide_index=True, height=400)
            with col_forn_uf:
                st.caption("Top 15 por UF (use os filtros de UF na barra lateral pra focar num estado):")
                st.dataframe(top15_uf, use_container_width=True, hide_index=True, height=400)
            st.caption(
                "Fornecedor com maior valor ganho (itens com resultado), Brasil e por UF, nos filtros atuais. "
                "Amostra parcial — só processos já com detalhe coletado. Marca/modelo do produto não é "
                "campo público do PNCP (fica em proposta anexa, exige login por processo) — não escalável hoje."
            )

        st.divider()
        st.subheader("Preço de referência — medida x UF")
        st.caption(
            "Prêmio regional = preço mediano pago no estado ÷ preço mediano nacional da MESMA medida, "
            "menos 1. Diferente de 'desconto vs estimado' (que mistura qualidade da estimativa do órgão "
            "com concorrência real) — aqui compara produto físico idêntico entre estados, sinal direto de "
            "onde o mercado paga mais/menos pela mesma medida."
        )
        preco_medida_uf = df.dropna(subset=["medida_extraida", "valor_unitario_resultado"])
        if preco_medida_uf.empty:
            st.info("Sem item com medida + preço final nesse filtro.")
        else:
            preco_medida_uf = preco_medida_uf[preco_medida_uf["medida_extraida"].isin(top_medidas_nomes_8)].copy()
            mediana_nacional = preco_medida_uf.groupby("medida_extraida")["valor_unitario_resultado"].median()
            tab_mu = (
                preco_medida_uf.groupby(["medida_extraida", "uf"], as_index=False)
                .agg(preco_mediano=("valor_unitario_resultado", "median"), n=("valor_unitario_resultado", "size"),
                     editais=("numero_controle_pncp", "nunique"))
            )
            tab_mu["preco_mediano_nacional"] = tab_mu["medida_extraida"].map(mediana_nacional)
            tab_mu["premio_pct"] = (tab_mu["preco_mediano"] / tab_mu["preco_mediano_nacional"] - 1) * 100
            # achado 08/jul/26: piso de n>=3 escondia estado com pouca amostra — usuário quer
            # ver todos os estados, mesmo com 1-2 vendas. Mostra tudo, confiança (coluna já
            # existente) comunica o risco em vez do dado sumir da tela.
            tab_mu["confianca"] = pd.cut(tab_mu["n"], bins=[0, 4, 14, float("inf")], labels=["baixa", "média", "alta"])
            tab_mu = tab_mu.sort_values(["medida_extraida", "premio_pct"], ascending=[True, False])

            col_ref, col_heat = st.columns([1, 1])
            with col_ref:
                if tab_mu.empty:
                    st.info("Nenhum item com medida + preço final nesse filtro.")
                else:
                    tab_mu_fmt = tab_mu.copy()
                    tab_mu_fmt["preco_mediano"] = tab_mu_fmt["preco_mediano"].round(2)
                    tab_mu_fmt["preco_mediano_nacional"] = tab_mu_fmt["preco_mediano_nacional"].round(2)
                    tab_mu_fmt["premio_pct"] = tab_mu_fmt["premio_pct"].round(1)
                    st.dataframe(
                        tab_mu_fmt.rename(columns={
                            "medida_extraida": "Medida", "uf": "UF", "preco_mediano": "Preço mediano UF (R$/un)",
                            "preco_mediano_nacional": "Preço mediano BR (R$/un)", "premio_pct": "Prêmio regional (%)",
                            "n": "Itens vendidos", "editais": "Editais ganhos", "confianca": "Confiança",
                        }),
                        use_container_width=True, hide_index=True, height=450,
                    )
                st.caption("Todas as UF com pelo menos 1 venda. Coluna Confiança avisa amostra pequena. Top 8 medidas mais pedidas nacionalmente.")

            with col_heat:
                medida_escolhida = st.selectbox("Medida do mapa de calor:", ["Todas as medidas"] + top_medidas_nomes_8.tolist())
                if medida_escolhida == "Todas as medidas":
                    heat = (
                        tab_mu.groupby("uf", as_index=False)
                              .agg(premio_pct=("premio_pct", "mean"), n=("medida_extraida", "size"))
                              .sort_values("premio_pct", ascending=True)
                    )
                    titulo_heat = "Prêmio regional médio — todas as medidas"
                    legenda_n = "Nº de medidas com amostra"
                else:
                    heat = tab_mu[tab_mu["medida_extraida"] == medida_escolhida].sort_values("premio_pct", ascending=True)
                    titulo_heat = f"Prêmio regional — {medida_escolhida}"
                    legenda_n = "Nº vendas"
                if heat.empty:
                    st.info("Sem venda dessa medida nos filtros atuais.")
                else:
                    heat = heat.copy()
                    heat["premio_label"] = heat["premio_pct"].apply(lambda v: f"{v:+.1f}%")
                    fig_heat = px.bar(
                        heat, x="premio_pct", y="uf", orientation="h", color="premio_pct", text="premio_label",
                        color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                        labels={"premio_pct": "Prêmio regional (%)", "uf": "UF", "n": legenda_n},
                        title=titulo_heat,
                        hover_data={"n": True},
                    )
                    fig_heat.update_traces(textposition="outside")
                    fig_heat.update_layout(coloraxis_showscale=False, height=max(400, 24 * len(heat)))
                    fundo_transparente(fig_heat)
                    st.plotly_chart(fig_heat, use_container_width=True)
                    st.caption("Verde = paga acima da mediana nacional. Vermelho = abaixo. Todas as UF com pelo menos 1 venda — cuidado com UF de amostra pequena (ver tabela ao lado).")

        st.divider()
        st.subheader("Mapa por município")
        lat_lon = carregar_lat_lon()
        muni = (
            df.dropna(subset=["codigo_ibge"])
              .groupby(["codigo_ibge", "municipio", "uf"], as_index=False)
              .agg(valor_total=("valor_item", "sum"), n_processos=("cod_compra", "nunique"))
        )
        muni = muni.merge(lat_lon, on="codigo_ibge", how="left").dropna(subset=["latitude", "longitude"])
        muni["valor_total"] = muni["valor_total"].round().astype("int64")

        if muni.empty:
            st.info("Sem município com coordenada pra mostrar nesse filtro.")
        else:
            col_mapa, col_dados = st.columns([2, 1])
            with col_mapa:
                lat_span = muni["latitude"].max() - muni["latitude"].min()
                lon_span = muni["longitude"].max() - muni["longitude"].min()
                zoom = max(3.0, 8.5 - 1.4 * max(lat_span, lon_span, 0.5))
                fig3 = px.density_mapbox(
                    muni, lat="latitude", lon="longitude", z="valor_total", radius=25,
                    center={"lat": muni["latitude"].mean(), "lon": muni["longitude"].mean()},
                    zoom=zoom, mapbox_style="carto-darkmatter", color_continuous_scale="Blues",
                    labels={"valor_total": "Valor total (R$)"},
                )
                fig3.update_layout(height=600, margin=dict(l=0, r=0, t=0, b=0))
                fundo_transparente(fig3)
                st.plotly_chart(fig3, use_container_width=True)
                st.caption(f"{muni.shape[0]} municípios nos filtros atuais.")
            with col_dados:
                muni_tab = muni[["municipio", "uf", "n_processos", "valor_total"]].sort_values(
                    "valor_total", ascending=False
                ).reset_index(drop=True)
                muni_tab.columns = ["Município", "UF", "Processos", "Valor (R$ mil)"]
                muni_tab["Valor (R$ mil)"] = muni_tab["Valor (R$ mil)"].apply(para_mil)
                st.dataframe(muni_tab, use_container_width=True, hide_index=True, height=600)

    # ── Aba Produto ──────────────────────────────────────────────────────
    with aba_produto:
        if com_medida.empty:
            st.info("Sem medida extraída nesse filtro.")
        else:
            col_medida_graf, col_medida_tab = st.columns([1, 1])
            with col_medida_graf:
                top_medidas_label = top_medidas.sort_values("n_itens").copy()
                top_medidas_label["n_label"] = top_medidas_label["n_itens"].apply(lambda v: f"{v:,}".replace(",", "."))
                figm = px.bar(
                    top_medidas_label, x="n_itens", y="medida_extraida", orientation="h", text="n_label",
                    labels={"n_itens": "Nº de itens pedidos", "medida_extraida": "Medida"},
                    title="Top 15 medidas mais pedidas (por nº de itens)",
                )
                figm.update_traces(marker_color="#2a78d6", textposition="outside")
                fundo_transparente(figm)
                st.plotly_chart(figm, use_container_width=True)
                st.caption(
                    f"Medida extraída da descrição em {cobertura_medida:.0f}% dos itens ({len(com_medida)}/{len(df)}) — "
                    "resto é descrição genérica sem medida, ou câmara/agrícola (formato diferente, não capturado)."
                )
            with col_medida_tab:
                top_medidas_fmt = top_medidas.rename(columns={
                    "medida_extraida": "Medida", "n_itens": "Itens pedidos", "n_vendidos": "Itens vendidos",
                    "valor_total": "Valor total (R$ mil)",
                })
                top_medidas_fmt["Valor total (R$ mil)"] = top_medidas_fmt["Valor total (R$ mil)"].apply(para_mil)
                st.dataframe(top_medidas_fmt, use_container_width=True, hide_index=True, height=480)

            st.divider()
            col_dom_medida, col_tend = st.columns([1, 1])
            with col_dom_medida:
                st.subheader("Fornecedor dominante por medida")
                venc_medida = df_forn.dropna(subset=["nome_fornecedor", "medida_extraida"])
                top_medidas_nomes_geral = top_medidas["medida_extraida"].tolist()
                if venc_medida.empty:
                    st.info("Sem item com resultado + medida nesse filtro.")
                else:
                    por_med_forn = (
                        venc_medida[venc_medida["medida_extraida"].isin(top_medidas_nomes_geral)]
                        .groupby(["medida_extraida", "nome_fornecedor"], as_index=False)
                        .agg(valor_total_resultado=("valor_total_resultado", "sum"),
                             editais=("numero_controle_pncp", "nunique"),
                             itens=("quantidade", "sum"))
                    )
                    total_med = por_med_forn.groupby("medida_extraida")["valor_total_resultado"].transform("sum")
                    por_med_forn["participacao_pct"] = (por_med_forn["valor_total_resultado"] / total_med * 100).round().astype("int64")
                    dom_medida = (
                        por_med_forn.sort_values("valor_total_resultado", ascending=False)
                                    .groupby("medida_extraida").first().reset_index()
                    )
                    dom_medida["valor_total_resultado"] = dom_medida["valor_total_resultado"].apply(para_mil)
                    dom_medida = dom_medida.rename(columns={
                        "medida_extraida": "Medida", "nome_fornecedor": "Fornecedor dominante",
                        "valor_total_resultado": "Valor ganho (R$ mil)", "participacao_pct": "% da medida",
                        "editais": "Editais ganhos", "itens": "Itens vendidos",
                    }).sort_values("% da medida", ascending=False)
                    st.dataframe(dom_medida, use_container_width=True, hide_index=True, height=450)
                    st.caption(
                        "Quem mais vende cada medida. Útil pra identificar medida com fornecedor pouco "
                        "concentrado (mais espaço pra entrar) x medida já dominada."
                    )

            with col_tend:
                st.subheader("Tendência mensal — top 5 medidas")
                top5_medidas = top_medidas.sort_values("n_itens", ascending=False).head(5)["medida_extraida"].tolist()
                tend_medida = (
                    com_medida[com_medida["medida_extraida"].isin(top5_medidas)]
                    .dropna(subset=["ano_mes"])
                    .groupby(["ano_mes", "medida_extraida"], as_index=False)
                    .size().rename(columns={"size": "n_itens"})
                    .sort_values("ano_mes")
                )
                if tend_medida.empty:
                    st.info("Sem dado de data suficiente pra tendência mensal nesse filtro.")
                else:
                    figt = px.line(
                        tend_medida, x="ano_mes", y="n_itens", color="medida_extraida", markers=True,
                        labels={"ano_mes": "Mês", "n_itens": "Nº de itens pedidos", "medida_extraida": "Medida"},
                        title="Evolução mensal de demanda — top 5 medidas",
                    )
                    figt.update_layout(legend_title_text="", height=450)
                    fundo_transparente(figt, tickformat_x=False)
                    st.plotly_chart(figt, use_container_width=True)
                    st.caption("Mês = data de abertura de proposta. Ajuda a ver medida em alta x em queda pra priorizar estoque.")

    # ── Aba Sazonalidade ─────────────────────────────────────────────────
    with aba_sazon:
        st.caption("Mês = data de abertura de proposta (proxy — `detalhes` não tem data de publicação).")
        granularidade = st.radio("Ver por:", ["UF", "Categoria de produto"], horizontal=True)
        grupo_col = "uf" if granularidade == "UF" else "categoria"
        cores = CORES_REGIME_TIPO if granularidade == "UF" else CORES_CATEGORIA

        sazon = (
            df.dropna(subset=["ano_mes"])
              .groupby(["ano_mes", grupo_col], as_index=False)
              .agg(valor_total=("valor_item", "sum"), n_processos=("cod_compra", "nunique"))
              .sort_values("ano_mes")
        )
        sazon["valor_total"] = sazon["valor_total"].round().astype("int64")

        metrica = st.radio("Métrica:", ["Valor total (R$)", "Nº processos"], horizontal=True)
        y_col = "valor_total" if metrica == "Valor total (R$)" else "n_processos"

        fig2 = px.line(
            sazon, x="ano_mes", y=y_col, color=grupo_col, markers=True,
            color_discrete_map=cores if grupo_col == "categoria" else None,
            labels={"ano_mes": "Mês", y_col: metrica, grupo_col: granularidade},
            title=f"Sazonalidade mensal — {metrica} por {granularidade} (PNCP direto)",
        )
        fig2.update_layout(legend_title_text="")
        fundo_transparente(fig2, tickformat_x=False)
        st.plotly_chart(fig2, use_container_width=True)

    # ── Aba Fornecedores e Preço ─────────────────────────────────────────
    with aba_forn:
        vencidos = df_forn

        st.subheader("Concentração de fornecedores")
        if vencidos.empty or vencidos["nome_fornecedor"].dropna().empty:
            st.info("Sem item com resultado (vencedor definido) nesse filtro.")
        else:
            conc = (
                vencidos.dropna(subset=["nome_fornecedor"])
                        .groupby("nome_fornecedor", as_index=False)
                        .agg(valor_ganho=("valor_total_resultado", "sum"),
                             n_processos=("numero_controle_pncp", "nunique"),
                             n_itens=("quantidade", "sum"))
                        .sort_values("valor_ganho", ascending=False)
                        .head(15)
            )
            total_ganho = vencidos["valor_total_resultado"].sum()
            conc["participacao_pct"] = (conc["valor_ganho"] / total_ganho * 100).round().astype("int64")
            conc["valor_ganho"] = conc["valor_ganho"].round().astype("int64")

            conc_label = conc.sort_values("valor_ganho").copy()
            conc_label["valor_label"] = conc_label["valor_ganho"].apply(fmt_abrev)
            col_conc_graf, col_conc_tab = st.columns([1, 1])
            with col_conc_graf:
                figf = px.bar(
                    conc_label, x="valor_ganho", y="nome_fornecedor", orientation="h", text="valor_label",
                    labels={"valor_ganho": "Valor ganho (R$)", "nome_fornecedor": ""},
                    title="Top 15 fornecedores por valor ganho",
                )
                figf.update_traces(marker_color="#2a78d6", textposition="outside")
                figf.update_layout(showlegend=False)
                fundo_transparente(figf)
                st.plotly_chart(figf, use_container_width=True)
                top5_pct = conc.head(5)["participacao_pct"].sum()
                st.caption(f"Top 5 fornecedores concentram {top5_pct:.0f}% do valor ganho nos filtros atuais.")

            with col_conc_tab:
                st.subheader("Recorrência — processos vencidos")
                tabela_forn = conc[["nome_fornecedor", "n_processos", "n_itens", "valor_ganho", "participacao_pct"]].rename(
                    columns={"nome_fornecedor": "Fornecedor", "n_processos": "Editais ganhos", "n_itens": "Itens vendidos",
                             "valor_ganho": "Valor ganho (R$ mil)", "participacao_pct": "% do total"}
                )
                tabela_forn["Valor ganho (R$ mil)"] = tabela_forn["Valor ganho (R$ mil)"].apply(para_mil)
                st.dataframe(tabela_forn, use_container_width=True, hide_index=True, height=480)

        st.divider()
        col_desc_cat, col_ticket_cat = st.columns([1, 1])

        with col_desc_cat:
            st.subheader("Desconto mediano por categoria")
            preco = df.dropna(subset=["valor_unitario_estimado", "valor_unitario_resultado"])
            # > R$1: exclui preço de referência simbólico (R$0,01) que o órgão publica quando
            # não tem estimativa real — dividir por isso gera % de desconto absurda (-8M%).
            preco = preco[preco["valor_unitario_estimado"] > 1]
            if preco.empty:
                st.info("Sem item com valor estimado + resultado nesse filtro.")
            else:
                preco = preco.copy()
                preco["desconto_pct"] = (1 - preco["valor_unitario_resultado"] / preco["valor_unitario_estimado"]) * 100
                desconto_cat = preco.groupby("categoria", as_index=False)["desconto_pct"].median().sort_values("desconto_pct", ascending=False)
                desconto_cat["desconto_pct"] = desconto_cat["desconto_pct"].round().astype("int64")
                desconto_cat["desconto_label"] = desconto_cat["desconto_pct"].apply(lambda v: f"{v:.0f}%")

                fig4 = px.bar(
                    desconto_cat, x="categoria", y="desconto_pct", text="desconto_label",
                    color="categoria", color_discrete_map=CORES_CATEGORIA,
                    labels={"categoria": "Categoria", "desconto_pct": "Desconto mediano (%)"},
                    title="Desconto mediano (estimado → homologado)",
                )
                fig4.update_traces(textposition="outside")
                fig4.update_layout(showlegend=False)
                fundo_transparente(fig4, tickformat_x=False)
                st.plotly_chart(fig4, use_container_width=True)

        with col_ticket_cat:
            st.subheader("Valor médio por item, por categoria")
            ticket_cat = df.groupby("categoria", as_index=False)["valor_item"].mean().rename(columns={"valor_item": "valor_medio"})
            ticket_cat["valor_medio"] = ticket_cat["valor_medio"].round().astype("int64")
            ticket_cat = ticket_cat.sort_values("valor_medio", ascending=False)
            ticket_cat["valor_label"] = ticket_cat["valor_medio"].apply(fmt_abrev)
            fig5 = px.bar(
                ticket_cat, x="categoria", y="valor_medio", text="valor_label",
                color="categoria", color_discrete_map=CORES_CATEGORIA,
                labels={"categoria": "Categoria", "valor_medio": "Valor médio por item (R$)"},
                title="Valor médio por item",
            )
            fig5.update_traces(textposition="outside")
            fig5.update_layout(showlegend=False)
            fundo_transparente(fig5, tickformat_x=False)
            st.plotly_chart(fig5, use_container_width=True)


if __name__ == "__main__":
    main()
