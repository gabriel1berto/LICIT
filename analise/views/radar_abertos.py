#!/usr/bin/env python3
"""Página — Radar de Editais: Kanban de editais com pneu ainda com proposta aberta.

Só leitura — nenhum botão aqui dispara analisa_edital.py (Camada 1) ou escreve no
Notion. Decisão explícita (16/jul/2026): o pipeline buscar→card→análise continua
manual, 1 ferramenta por vez (CLAUDE.md §17.8) — dashboard é público, não é lugar
pra disparar chamada de API/Claude/Notion sozinho.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import (
    COR_STATUS_CRITICAL, COR_STATUS_GOOD, COR_STATUS_WARNING,
    capag_do_orgao, carregar_base, carregar_capag_estados, carregar_capag_municipios,
    carregar_cotacao_master, carregar_editais_abertos,
    carregar_itens_pneu_editais_abertos, carregar_lat_lon, carregar_ultima_carga_detalhes,
    cor_capag, fmt_abrev, fundo_transparente,
)
from ui_explicacao import cabecalho_pagina, regra

# CLAUDE.md §5 (revisado 17/jul/2026): Investimento + Frete 6% + Imposto 6% + margem
# 20% no final = efetivo Custo x 1.348. Fórmula real vive na planilha (fórmula, não
# script) — aqui é só a mesma constante pra estimar "meu preço" sem abrir a planilha.
MULTIPLICADOR_PRECO_VENDA = 1.348

st.title("🗂️ Radar de Editais")

_ultima_carga = carregar_ultima_carga_detalhes()
if _ultima_carga is not None:
    st.caption(f"📥 Dado carregado até: {_ultima_carga.strftime('%d/%m/%Y %H:%M')} (BRT)")

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
        "itens além de pneu, aparece o aviso '⚠️ N de M itens são pneu'.\n\n"
"O card decompõe cada item de pneu em 4 buckets (achado 17/jul/2026, auditoria com "
        "Fable 5 — um número único 'N bem posicionado' escondia 3 diagnósticos diferentes): "
        "🎯 **bem posicionado** (meu preço ≤ mediana histórica) · 📉 **acima da média** (meu "
        "preço > mediana histórica — problema de custo/distribuidor) · 📵 **sem cotação "
        "nossa** (medida não cotada na Cotação Fornecedor — problema de catálogo/onboarding) "
        "· ⚪ **sem histórico de mercado** (cotamos, mas não há resultado histórico pra "
        "comparar — raro). Só o valor de 🎯 soma meu\\_preço × quantidade; os outros 3 são "
        "só contagem, sem inventar valor pro que não dá pra avaliar.\n\n"
        "Dentro de **Detalhes**, a tabela item x preço compara, por medida: **preço médio "
        "histórico** (mediana do que já venceu processo parecido, Mercado PNCP) x **meu "
        "preço** (menor custo já cotado entre os 5 distribuidores × 1,348, fórmula fixada em "
        "CLAUDE.md §5 — é o menor preço visto em qualquer dia do histórico da Cotação "
        "Fornecedor, não necessariamente o de hoje). Só cobre as medidas já cotadas na "
        "Cotação Fornecedor — fora disso aparece \"sem cotação\". É sinal probabilístico, "
        "não garantia: concorrente pode ter custo que não monitoramos.\n\n"
        "**CAPAG** (adicionado 22/jul/2026): nota de capacidade de pagamento do Tesouro "
        "Nacional (dívida/poupança corrente/liquidez do órgão pagador, ano base 2025) — "
        "🟢 A+/A · 🟡 B+/B · 🔴 C/D. Tenta casar pelo município do órgão primeiro; sem "
        "linha aí, cai pra nota do estado. Sinal de risco de **calote/atraso no pagamento "
        "depois de vencer**, não de qualidade do edital em si — nunca decide sozinho se "
        "vale participar."
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

_capag_mun = carregar_capag_municipios()
_capag_uf = carregar_capag_estados()
MAPA_CAPAG_MUN = dict(zip(_capag_mun["codigo_ibge"], _capag_mun["capag"]))
MAPA_CAPAG_UF = dict(zip(_capag_uf["uf"], _capag_uf["capag"]))

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

# Item x preço médio histórico x meu preço (Detalhes) — 1 lookup por medida pra toda a
# página, não por card, senão vira 1 query por edital aberto.
itens_pneu = carregar_itens_pneu_editais_abertos(tuple(editais["numero_controle_pncp"]))
_base_mercado = carregar_base().dropna(subset=["medida_extraida", "valor_unitario_resultado"])
preco_hist_por_medida = _base_mercado.groupby("medida_extraida")["valor_unitario_resultado"].median()
_cotacao_atual = carregar_cotacao_master()
meu_custo_por_medida = _cotacao_atual.groupby("medida")["preco"].min()
meu_preco_por_medida = meu_custo_por_medida * MULTIPLICADOR_PRECO_VENDA

# Funil por item (achado 17/jul/2026, auditoria com Fable 5): "N bem posicionado" sozinho
# colapsava 3 diagnósticos diferentes num número só — item sem cotação nossa (problema de
# catálogo/onboarding de fornecedor), item cotado acima da mediana histórica (problema de
# custo/distribuidor) e item sem histórico de mercado pra comparar (raro, quase não ocorre)
# viravam todos "não bem posicionado", indistinguíveis. Medido contra a base real: 60,5% dos
# itens do Kanban caem em "sem cotação nossa" — mas quase tudo fora do escopo de categoria
# que a Cotação Master cobre hoje (Passeio + Câmara de ar), não falha de execução.
itens_pneu = itens_pneu.copy()
itens_pneu["preco_hist"] = itens_pneu["medida_extraida"].map(preco_hist_por_medida)
itens_pneu["meu_preco"] = itens_pneu["medida_extraida"].map(meu_preco_por_medida)
itens_pneu["valor_se_ganhar"] = itens_pneu["meu_preco"] * itens_pneu["quantidade"]


def _funil_item(row: pd.Series) -> str:
    if pd.isna(row["meu_preco"]):
        return "sem_cotacao"
    if pd.isna(row["preco_hist"]):
        return "sem_historico"
    if row["meu_preco"] <= row["preco_hist"]:
        return "bem_posicionado"
    return "acima_media"


# item sem medida identificável não entra no funil (nem "sem cotação" nem qualquer outro
# bucket) — é um problema de PARSING da descrição, diferente dos 4 buckets acima, e já tem
# aviso próprio dentro de Detalhes ("⚠️ N itens sem medida identificável").
_itens_com_medida = itens_pneu.dropna(subset=["medida_extraida"]).copy()
_itens_com_medida["funil"] = _itens_com_medida.apply(_funil_item, axis=1)
BUCKETS_FUNIL = [
    ("bem_posicionado", "🎯", "bem posicionado(s)"),
    ("acima_media", "📉", "acima da média"),
    ("sem_cotacao", "📵", "sem cotação nossa"),
    ("sem_historico", "⚪", "sem histórico de mercado"),
]
resumo_funil = (
    _itens_com_medida.groupby(["numero_controle_pncp", "funil"]).size().unstack(fill_value=0)
    .reindex(columns=[b[0] for b in BUCKETS_FUNIL], fill_value=0)
)
valor_bem_posicionado_por_edital = (
    _itens_com_medida[_itens_com_medida["funil"] == "bem_posicionado"]
    .groupby("numero_controle_pncp")["valor_se_ganhar"].sum()
)

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
ordenar_por = st.radio(
    "Ordenar cards por:", ["Prazo (mais urgente primeiro)", "Valor bem posicionado (maior primeiro)"],
    horizontal=True, key="ordenar_radar",
)
cols = st.columns(len(BUCKETS))
for col, (icone, titulo, subtitulo, cor, cond) in zip(cols, BUCKETS):
    with col:
        st.markdown(f"#### {icone} {titulo}")
        st.caption(subtitulo)
        bucket = editais[editais["dias_restantes"].apply(cond)].copy()
        if bucket.empty:
            st.caption("Nenhum edital nessa faixa.")
            continue
        if ordenar_por.startswith("Valor"):
            bucket["_valor_pos"] = bucket["numero_controle_pncp"].map(
                valor_bem_posicionado_por_edital
            ).fillna(-1)
            bucket = bucket.sort_values("_valor_pos", ascending=False)
        else:
            bucket = bucket.sort_values("dias_restantes")
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
                    cor = cor_capag(nota_capag)
                    icone_capag = "🟢" if cor == COR_STATUS_GOOD else "🟡" if cor == COR_STATUS_WARNING else "🔴"
                    st.caption(f"{icone_capag} CAPAG {nota_capag} ({origem_capag})")
                else:
                    st.caption("⚪ CAPAG sem dado")
                valor_pneu = row["valor_pneu_estimado"]
                if pd.isna(valor_pneu) or valor_pneu == 0:
                    # achado 17/jul/26 (auditoria de confiança do card): alguns órgãos
                    # publicam valor_unitario_estimado=0.0 pra todo item (não é bug, é o
                    # órgão não informando valor) — "R$ 0" lia como "não vale nada".
                    st.caption("Sem valor estimado (órgão não informou no PNCP)")
                else:
                    st.caption(f"R$ {fmt_abrev(valor_pneu)} em itens de pneu")
                n_pneu, n_total = int(row["n_itens_pneu"]), int(row["n_itens_total"])
                if n_pneu < n_total:
                    st.caption(f"⚠️ {n_pneu} de {n_total} itens são pneu — resto do edital é outra coisa")
                if row["numero_controle_pncp"] in resumo_funil.index:
                    f = resumo_funil.loc[row["numero_controle_pncp"]]
                    partes = []
                    for chave, icone, label in BUCKETS_FUNIL:
                        n_bucket = int(f[chave])
                        if n_bucket == 0:
                            continue
                        if chave == "bem_posicionado":
                            v = valor_bem_posicionado_por_edital.get(row["numero_controle_pncp"], 0)
                            partes.append(f"{icone} {n_bucket} {label} (R$ {fmt_abrev(v)})")
                        else:
                            partes.append(f"{icone} {n_bucket} {label}")
                    if partes:
                        st.caption(" · ".join(partes))
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
                    valor_proc = row["valor_total_estimado"]
                    if pd.isna(valor_proc) or valor_proc == 0:
                        st.caption("Valor estimado do processo inteiro: sem dado (órgão não informou no PNCP)")
                    else:
                        st.caption(f"Valor estimado do processo inteiro (todos os itens): R$ {fmt_abrev(valor_proc)}")
                    if contagem_orgao.get(row["orgao_nome"], 0) > 1:
                        st.caption(
                            f"🔁 Esse órgão tem {contagem_orgao[row['orgao_nome']]} editais de pneu "
                            "abertos agora, nesse filtro."
                        )

                    itens_edital = itens_pneu[itens_pneu["numero_controle_pncp"] == row["numero_controle_pncp"]]
                    n_sem_medida = int(itens_edital["medida_extraida"].isna().sum())
                    itens_com_medida = itens_edital.dropna(subset=["medida_extraida"])
                    if not itens_com_medida.empty:
                        tabela = itens_com_medida.copy()
                        tabela["Item"] = tabela["medida_extraida"]
                        tabela["Preço médio histórico"] = tabela["medida_extraida"].map(preco_hist_por_medida)
                        tabela["Meu preço"] = tabela["medida_extraida"].map(meu_preco_por_medida)
                        tabela = tabela[["Item", "Preço médio histórico", "Meu preço"]].drop_duplicates("Item")
                        st.caption("Item x preço médio histórico x meu preço:")
                        st.dataframe(
                            tabela, use_container_width=True, hide_index=True,
                            column_config={
                                "Preço médio histórico": st.column_config.NumberColumn(format="R$ %.2f"),
                                "Meu preço": st.column_config.NumberColumn(format="R$ %.2f"),
                            },
                        )
                    if n_sem_medida:
                        st.caption(
                            f"⚠️ {n_sem_medida} item(ns) sem medida identificável na descrição do PNCP "
                            "(ex: \"Pneu veículo automotivo\", sem tamanho) — medida real só no anexo/TR "
                            "do edital, não dá pra comparar preço automaticamente."
                        )
                    st.caption(f"Pra analisar: `python analisa_edital.py {row['cnpj_ano_seq']} <notion_id>`")

st.divider()
st.caption(
    "Análise (Camada 1) continua manual — copie o identificador acima e rode "
    "`analisa_edital.py` no terminal (ver CLAUDE.md §2). Nenhuma escrita acontece a partir "
    "deste dashboard."
)
