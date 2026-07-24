#!/usr/bin/env python3
"""Página — Mercado PNCP: Análise de mercado (geografia, desconto, fornecedor dominante, preço regional, mapa)."""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import (
    CATEGORIAS_ABREV, CORES_REGIME_TIPO, DIVERGING_NEUTRO, DIVERGING_POLO_NEG, DIVERGING_POLO_POS,
    carregar_cobertura_uf, carregar_lat_lon,
    fundo_transparente, para_mil, preparar_pagina_pncp,
)
from ui_explicacao import cabecalho_pagina, regra

st.title("🎯 Análise de mercado")
cabecalho_pagina(
    pergunta="Onde tem mercado de pneu no PNCP — qual UF, qual regime/tipo, quem já domina?",
    fonte="Itens de edital coletados via API PNCP (`analise/coletor_pncp_detalhe.py`), já "
    "filtrados pela heurística abaixo.",
)

with regra("ℹ️ Como decidimos que um item de edital é pneu de verdade"):
    st.markdown(
        "Todo item que aparece nesse dashboard passou pelo filtro `eh_pneu_de_verdade()` "
        "(`analise/filtro_pneu.py`), aplicado à descrição estruturada do item (não ao título "
        "do edital, que costuma ser genérico demais). Resumo da regra:\n\n"
        "- **Aceita** quando o item começa com \"pneu\"/\"pneumático\"/\"câmara de ar\" "
        "(ignorando ruído burocrático na frente, tipo código de item ou \"aquisição de\"), "
        "**ou** quando tem uma medida reconhecível de pneu na descrição (ex: `175/70 R14`).\n"
        "- **Recusa** mesmo com medida presente quando o produto real é outra coisa: veículo "
        "inteiro citando a medida do pneu de fábrica (ambulância, van, caminhão), serviço "
        "(montagem, reparo, recapagem de pneu **usado**), ou acessório avulso (roda, bico de ar).\n\n"
        "**Exemplo aceito:** `0006648 - PNEU 205/55 R16, NOVO, CERTIFICADO INMETRO` — código de "
        "item na frente, mas o produto é pneu.\n\n"
        "**Exemplo recusado:** `AMBULÂNCIA TIPO A, PNEUS 185/65 R15 DE FÁBRICA` — tem medida de "
        "pneu na descrição, mas o item vendido é o veículo (R$100k+), não o pneu.\n\n"
        "A regra já passou por várias rodadas de correção documentadas em `README.md` (seção "
        "\"Auto-aperfeiçoamento do filtro\") e tem suíte de teste de regressão "
        "(`test_filtro_pneu.py`) — todo bug achado vira caso de teste antes do fix, pra não "
        "voltar em silêncio."
    )

df, df_forn, cobertura_medida, com_medida, top_medidas, top_medidas_nomes_8 = preparar_pagina_pncp()

# Ordem = funil de decisão: 1) tamanho do mercado, 2) dinâmica de preço por
# tipo, 3) onde paga bem pelo mesmo produto (prêmio regional), 4) quem já
# domina, 5) detalhe fino por município. Não é ordem cronológica de quando
# cada gráfico foi construído — é a ordem em que a pergunta "onde eu entro"
# precisa ser respondida.

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
    with regra("ℹ️ O que esse desconto considera"):
        st.markdown(
            "**O que é \"desconto\":** compara o preço unitário que **realmente venceu** a "
            "licitação (`valor_unitario_resultado`) contra o preço unitário de **referência "
            "publicado pelo próprio órgão** no edital (`valor_unitario_estimado`) — "
            "`desconto% = 1 − resultado/estimado`. Não é desconto de tabela de distribuidor, "
            "é o quanto o mercado pagou a menos (ou a mais) do que o órgão esperava pagar.\n\n"
            "**Regime — RP x CD:** RP = Registro de Preço (ata válida por até 1 ano, outros "
            "órgãos podem \"pegar carona\"). CD = Compra/Contratação Direta (compra pontual, "
            "sem ata).\n\n"
            "**Tipo — Dispensa x Pregão:** Dispensa = contratação direta sem disputa de lance "
            "(valor baixo ou hipótese legal do Art. 75 da Lei 14.133/21). Pregão = disputa de "
            "lance real entre fornecedores.\n\n"
            "**O que fica de fora:** item sem valor estimado OU sem resultado homologado ainda "
            "(a maioria dos processos em aberto) e item com valor estimado ≤ R$1 (placeholder "
            "simbólico do órgão, sem preço de referência real — dividir por isso explodiria a "
            "porcentagem).\n\n"
            "**Por que mediana, não média:** 1 processo com preço mal publicado (erro de "
            "digitação, ordem de grandeza errada) distorce a média inteira — mediana é robusta "
            "a esse tipo de outlier.\n\n"
            "**Cuidado com amostra pequena:** célula com poucos itens (ver contagem no caption "
            "abaixo) pode não representar o regime/tipo de verdade — não compare 2 células com "
            "N muito diferente como se fossem igualmente confiáveis."
        )
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
            # achado 24/jul/2026 (mesmo bug achado no dashboard onco, mesmo ajuste):
            # 1ª tentativa excluiu confiança "baixa" inteira (n≤4) — forte demais,
            # corte final exclui só n=1 (venda isolada, sem robustez nenhuma), mantém
            # n=2+ no agregado (n=2+ já concorda entre pontos, informação real).
            tab_mu_confiavel = tab_mu[tab_mu["n"] > 1]
            heat = (
                tab_mu_confiavel.groupby("uf", as_index=False)
                      .agg(premio_pct=("premio_pct", "mean"), n=("medida_extraida", "size"))
                      .sort_values("premio_pct", ascending=True)
            )
            titulo_heat = "Prêmio regional médio — todas as medidas (exclui venda isolada, n=1)"
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
                # achado 14/jul/26 (auditoria dataviz): RdYlGn tem amarelo no ponto
                # médio — anti-padrão (o meio de um diverging tem que ler como "nada",
                # nunca um hue). Par validado é blue↔red, meio cinza neutro.
                color_continuous_scale=[[0, DIVERGING_POLO_NEG], [0.5, DIVERGING_NEUTRO], [1, DIVERGING_POLO_POS]],
                color_continuous_midpoint=0,
                labels={"premio_pct": "Prêmio regional (%)", "uf": "UF", "n": legenda_n},
                title=titulo_heat,
                hover_data={"n": True},
            )
            fig_heat.update_traces(textposition="outside")
            fig_heat.update_layout(coloraxis_showscale=False, height=max(400, 24 * len(heat)))
            fundo_transparente(fig_heat)
            st.plotly_chart(fig_heat, use_container_width=True)
            if medida_escolhida == "Todas as medidas":
                st.caption(
                    "Azul = paga acima da mediana nacional. Vermelho = abaixo. Medida com "
                    "1 venda isolada fica de fora dessa média resumo (n=1 não tem como "
                    "distinguir preço real de erro de digitação) — Ver tabela ao lado pro "
                    "detalhe completo, incluindo os de confiança baixa/venda única."
                )
            else:
                st.caption("Azul = paga acima da mediana nacional. Vermelho = abaixo. Todas as UF com pelo menos 1 venda — cuidado com UF de amostra pequena (ver tabela ao lado).")

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
