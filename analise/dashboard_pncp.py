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

from conectar_pncp import carregar_base_pncp, cobertura_por_uf, cobertura_pct

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


def fundo_transparente(fig: go.Figure) -> go.Figure:
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color=COR_INK_DARK)
    fig.update_xaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK, tickformat=",.0f")
    fig.update_yaxes(gridcolor=COR_GRID_DARK, zerolinecolor=COR_GRID_DARK, tickformat=",.0f")
    return fig


def fmt0(v: float) -> str:
    return f"{v:,.0f}"


@st.cache_data(ttl=300)
def carregar_base() -> pd.DataFrame:
    df = carregar_base_pncp()
    df["regime_tipo"] = df["regime"] + " - " + df["tipo"]
    return df


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

    processo = df.groupby("cod_compra")["valor_item"].sum().reset_index(name="valor_processo")
    col1, col2, col3 = st.columns(3)
    col1.metric("Processos", f"{processo.shape[0]:,}")
    col2.metric("Valor total", f"R$ {processo['valor_processo'].sum():,.0f}")
    col3.metric("Ticket médio", f"R$ {processo['valor_processo'].mean():,.0f}")

    aba_geo, aba_sazon, aba_forn = st.tabs(["📍 Geografia", "📅 Sazonalidade", "🏭 Fornecedores e Preço"])

    # ── Aba Geografia ────────────────────────────────────────────────────
    with aba_geo:
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
        fig.update_layout(barmode="stack", legend_title_text="")
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
        tabelao["Valor Licitado"]  = pivot_v[list(CATEGORIAS_ABREV)].sum(axis=1).round().astype("int64")
        for cat, abrev in CATEGORIAS_ABREV.items():
            tabelao[f"{abrev} (n)"]  = pivot_n[cat].astype(int)
            tabelao[f"{abrev} (R$)"] = pivot_v[cat].round().astype("int64")
        tabelao = tabelao.sort_values("Valor Licitado", ascending=False).reset_index().rename(columns={"uf": "Estado"})

        cov_uf = carregar_cobertura_uf().set_index("uf")["cobertura_pct"]
        tabelao["Cobertura %"] = tabelao["Estado"].map(cov_uf)
        cols_ordenadas = ["Estado", "Cobertura %"] + [c for c in tabelao.columns if c not in ("Estado", "Cobertura %")]
        tabelao = tabelao[cols_ordenadas]

        st.dataframe(
            tabelao, use_container_width=True, hide_index=True,
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
        st.subheader("Desconto por regime (RP x CD)")
        preco_regime = df.dropna(subset=["valor_unitario_estimado", "valor_unitario_resultado"])
        # valor_unitario_estimado <= R$1 é placeholder simbólico do órgão (sem preço de
        # referência real publicado) — dividir por isso explode a % de desconto. Excluído.
        preco_regime = preco_regime[preco_regime["valor_unitario_estimado"] > 1]
        if preco_regime.empty:
            st.info("Sem item com valor estimado + resultado nesse filtro.")
        else:
            preco_regime = preco_regime.copy()
            preco_regime["desconto_pct"] = (1 - preco_regime["valor_unitario_resultado"] / preco_regime["valor_unitario_estimado"]) * 100
            desconto_regime = preco_regime.groupby("regime")["desconto_pct"].median()
            col_rp, col_cd = st.columns(2)
            for col, regime in zip((col_rp, col_cd), ("RP", "CD")):
                valor = f"{desconto_regime[regime]:.1f}%" if regime in desconto_regime.index else "sem dado"
                col.metric(f"Desconto mediano — {regime}", valor)
            st.caption(
                f"Amostra: {len(preco_regime)} itens com estimado + homologado nesse filtro "
                f"(mediana usada — média é sensível a outlier de preço mal publicado). "
                "Referência: fórmula de leilão assume 20% de margem."
            )

        st.divider()
        st.subheader("Ticket mediano por UF — Dispensa x Pregão")
        st.caption(
            "Mediana, não média — dispensa por valor tem teto ~R$50-60k (Lei 14.133/21), mas outras "
            "hipóteses do Art. 75 (emergência, exclusividade etc.) não têm teto. Poucos processos grandes "
            "distorcem a média em UF com amostra pequena; mediana não sofre isso."
        )
        tm = (
            df.groupby(["uf", "tipo", "cod_compra"], as_index=False)["valor_item"].sum()
              .groupby(["uf", "tipo"], as_index=False)["valor_item"].median()
              .rename(columns={"valor_item": "ticket_mediano"})
        )
        tm_pivot = tm[tm["tipo"].isin(["Dispensa", "Pregão"])].pivot(index="uf", columns="tipo", values="ticket_mediano")
        for col in ["Dispensa", "Pregão"]:
            if col not in tm_pivot.columns:
                tm_pivot[col] = None
        tm_pivot = tm_pivot.round(0)

        preco_uf = df.dropna(subset=["valor_unitario_estimado", "valor_unitario_resultado"])
        preco_uf = preco_uf[preco_uf["valor_unitario_estimado"] > 1].copy()  # exclui R$0,01 simbólico
        if not preco_uf.empty:
            preco_uf["desconto_pct"] = (1 - preco_uf["valor_unitario_resultado"] / preco_uf["valor_unitario_estimado"]) * 100
            desconto_tipo = (
                preco_uf[preco_uf["tipo"].isin(["Dispensa", "Pregão"])]
                .groupby(["uf", "tipo"])["desconto_pct"].median()
                .unstack("tipo")
            )
            for col in ["Dispensa", "Pregão"]:
                if col not in desconto_tipo.columns:
                    desconto_tipo[col] = None
            tm_pivot["Desconto med. Dispensa (%)"] = desconto_tipo["Dispensa"].round(1)
            tm_pivot["Desconto med. Pregão (%)"] = desconto_tipo["Pregão"].round(1)
        else:
            tm_pivot["Desconto med. Dispensa (%)"] = None
            tm_pivot["Desconto med. Pregão (%)"] = None

        tm_pivot = tm_pivot.sort_values("Pregão", ascending=False, na_position="last")
        st.dataframe(
            tm_pivot.reset_index().rename(columns={"uf": "UF", "Dispensa": "Ticket Dispensa (R$)", "Pregão": "Ticket Pregão (R$)"}),
            use_container_width=True, hide_index=True,
        )
        st.caption("Desconto mediano: itens com estimado + homologado, exclui preço de referência simbólico (R$0,01).")

        st.divider()
        st.subheader("Fornecedor dominante por UF")
        vencidos_geo = df[df["tem_resultado"] == True].dropna(subset=["nome_fornecedor"])  # noqa: E712
        if vencidos_geo.empty:
            st.info("Sem item com resultado nesse filtro.")
        else:
            por_uf_forn = vencidos_geo.groupby(["uf", "nome_fornecedor"], as_index=False)["valor_total_resultado"].sum()
            total_uf = por_uf_forn.groupby("uf")["valor_total_resultado"].transform("sum")
            por_uf_forn["participacao_pct"] = (por_uf_forn["valor_total_resultado"] / total_uf * 100).round().astype("int64")
            dominante = (
                por_uf_forn.sort_values("valor_total_resultado", ascending=False)
                           .groupby("uf").first().reset_index()
                           .sort_values("valor_total_resultado", ascending=False)
            )
            dominante["valor_total_resultado"] = dominante["valor_total_resultado"].round().astype("int64")
            dominante = dominante.rename(columns={
                "uf": "UF", "nome_fornecedor": "Fornecedor dominante",
                "valor_total_resultado": "Valor ganho (R$)", "participacao_pct": "% do valor da UF",
            })
            st.dataframe(dominante, use_container_width=True, hide_index=True)
            st.caption(
                "Fornecedor com maior valor ganho (itens com resultado) por UF, nos filtros atuais. "
                "Amostra parcial — só processos já com detalhe coletado. Marca/modelo do produto não é "
                "campo público do PNCP (fica em proposta anexa, exige login por processo) — não escalável hoje."
            )

        st.divider()
        st.subheader("Medidas de pneu mais pedidas")
        com_medida = df.dropna(subset=["medida_extraida"])
        cobertura_medida = len(com_medida) / len(df) * 100 if len(df) else 0
        if com_medida.empty:
            st.info("Sem medida extraída nesse filtro.")
        else:
            top_medidas = (
                com_medida.groupby("medida_extraida", as_index=False)
                          .agg(n_itens=("medida_extraida", "size"), valor_total=("valor_item", "sum"))
                          .sort_values("n_itens", ascending=False)
                          .head(15)
            )
            top_medidas["valor_total"] = top_medidas["valor_total"].round().astype("int64")
            figm = px.bar(
                top_medidas.sort_values("n_itens"), x="n_itens", y="medida_extraida", orientation="h",
                labels={"n_itens": "Nº de itens pedidos", "medida_extraida": "Medida"},
                title="Top 15 medidas mais pedidas (por nº de itens)",
            )
            figm.update_traces(marker_color="#2a78d6")
            fundo_transparente(figm)
            st.plotly_chart(figm, use_container_width=True)
            st.dataframe(
                top_medidas.rename(columns={"medida_extraida": "Medida", "n_itens": "Nº itens", "valor_total": "Valor total (R$)"}),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                f"Medida extraída da descrição em {cobertura_medida:.0f}% dos itens ({len(com_medida)}/{len(df)}) — "
                "resto é descrição genérica sem medida no texto, ou câmara/agrícola (formato de medida diferente, não capturado)."
            )

        st.divider()
        st.subheader("Preço final vendido — medida x UF")
        preco_medida_uf = df.dropna(subset=["medida_extraida", "valor_unitario_estimado", "valor_unitario_resultado"])
        preco_medida_uf = preco_medida_uf[preco_medida_uf["valor_unitario_estimado"] > 1].copy()  # exclui R$0,01 simbólico
        if preco_medida_uf.empty:
            st.info("Sem item com medida + preço final nesse filtro.")
        else:
            preco_medida_uf["desconto_pct"] = (1 - preco_medida_uf["valor_unitario_resultado"] / preco_medida_uf["valor_unitario_estimado"]) * 100
            top_medidas_nomes = com_medida["medida_extraida"].value_counts().head(8).index
            tab_mu = (
                preco_medida_uf[preco_medida_uf["medida_extraida"].isin(top_medidas_nomes)]
                .groupby(["medida_extraida", "uf"], as_index=False)
                .agg(preco_mediano=("valor_unitario_resultado", "median"),
                     desconto_mediano=("desconto_pct", "median"),
                     n=("desconto_pct", "size"))
            )
            tab_mu = tab_mu[tab_mu["n"] >= 3].sort_values(["medida_extraida", "preco_mediano"], ascending=[True, False])
            if tab_mu.empty:
                st.info("Nenhuma combinação medida x UF com 3+ amostras ainda — normal com 20% de cobertura, cresce com a coleta.")
            else:
                tab_mu["preco_mediano"] = tab_mu["preco_mediano"].round(2)
                tab_mu["desconto_mediano"] = tab_mu["desconto_mediano"].round(1)
                st.dataframe(
                    tab_mu.rename(columns={
                        "medida_extraida": "Medida", "uf": "UF", "preco_mediano": "Preço final mediano (R$/un)",
                        "desconto_mediano": "Desconto mediano (%)", "n": "Nº vendas",
                    }),
                    use_container_width=True, hide_index=True,
                )
            st.caption("Só medida x UF com 3+ vendas (evita ruído de amostra única). Top 8 medidas mais pedidas nacionalmente.")

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
                muni_tab.columns = ["Município", "UF", "Processos", "Valor (R$)"]
                muni_tab["Valor (R$)"] = muni_tab["Valor (R$)"].apply(lambda v: f"{v:,.0f}")
                st.dataframe(muni_tab, use_container_width=True, hide_index=True, height=600)

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
        fundo_transparente(fig2)
        st.plotly_chart(fig2, use_container_width=True)

    # ── Aba Fornecedores e Preço ─────────────────────────────────────────
    with aba_forn:
        vencidos = df[df["tem_resultado"] == True]  # noqa: E712

        st.subheader("Concentração de fornecedores")
        if vencidos.empty or vencidos["nome_fornecedor"].dropna().empty:
            st.info("Sem item com resultado (vencedor definido) nesse filtro.")
        else:
            conc = (
                vencidos.dropna(subset=["nome_fornecedor"])
                        .groupby("nome_fornecedor", as_index=False)
                        .agg(valor_ganho=("valor_total_resultado", "sum"), n_processos=("cod_compra", "nunique"))
                        .sort_values("valor_ganho", ascending=False)
                        .head(15)
            )
            total_ganho = vencidos["valor_total_resultado"].sum()
            conc["participacao_pct"] = (conc["valor_ganho"] / total_ganho * 100).round().astype("int64")
            conc["valor_ganho"] = conc["valor_ganho"].round().astype("int64")

            figf = px.bar(
                conc.sort_values("valor_ganho"), x="valor_ganho", y="nome_fornecedor", orientation="h",
                labels={"valor_ganho": "Valor ganho (R$)", "nome_fornecedor": ""},
                title="Top 15 fornecedores por valor ganho (itens com resultado)",
            )
            figf.update_traces(marker_color="#2a78d6")
            figf.update_layout(showlegend=False)
            fundo_transparente(figf)
            st.plotly_chart(figf, use_container_width=True)

            top5_pct = conc.head(5)["participacao_pct"].sum()
            st.caption(f"Top 5 fornecedores concentram {top5_pct:.0f}% do valor ganho nos filtros atuais.")

            st.subheader("Recorrência — nº de processos vencidos por fornecedor")
            tabela_forn = conc[["nome_fornecedor", "n_processos", "valor_ganho", "participacao_pct"]].rename(
                columns={"nome_fornecedor": "Fornecedor", "n_processos": "Processos vencidos",
                         "valor_ganho": "Valor ganho (R$)", "participacao_pct": "% do total"}
            )
            tabela_forn["Valor ganho (R$)"] = tabela_forn["Valor ganho (R$)"].apply(fmt0)
            tabela_forn["% do total"] = tabela_forn["% do total"].apply(lambda v: f"{v:.0f}%")
            st.dataframe(tabela_forn, use_container_width=True, hide_index=True)

        st.divider()
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

            fig4 = px.bar(
                desconto_cat, x="categoria", y="desconto_pct",
                color="categoria", color_discrete_map=CORES_CATEGORIA,
                labels={"categoria": "Categoria", "desconto_pct": "Desconto mediano (%)"},
                title="Desconto mediano (estimado → homologado) por categoria de produto",
            )
            fig4.update_layout(showlegend=False)
            fundo_transparente(fig4)
            st.plotly_chart(fig4, use_container_width=True)

        st.divider()
        st.subheader("Valor médio por item, por categoria")
        ticket_cat = df.groupby("categoria", as_index=False)["valor_item"].mean().rename(columns={"valor_item": "valor_medio"})
        ticket_cat["valor_medio"] = ticket_cat["valor_medio"].round().astype("int64")
        ticket_cat = ticket_cat.sort_values("valor_medio", ascending=False)
        fig5 = px.bar(
            ticket_cat, x="categoria", y="valor_medio",
            color="categoria", color_discrete_map=CORES_CATEGORIA,
            labels={"categoria": "Categoria", "valor_medio": "Valor médio por item (R$)"},
            title="Valor médio por item, por categoria de produto",
        )
        fig5.update_layout(showlegend=False)
        fundo_transparente(fig5)
        st.plotly_chart(fig5, use_container_width=True)


if __name__ == "__main__":
    main()
