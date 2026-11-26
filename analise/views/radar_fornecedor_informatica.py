#!/usr/bin/env python3
"""Página — Radar de Fornecedor: Informática. Quais categorias os editais abertos pedem e
quais distribuidores (GET, TS Shara, Mazer) têm produto pra cada uma (26/nov/2026, pedido
do usuário: "o Radar de fornecedor é de pneus, crie um para Informática").

Diferente do radar de fornecedor de pneu (mapa por UF de 113 fornecedores do Notion):
aqui são só 3 distribuidores nacionais, então distância não decide nada. O que decide é
COBERTURA — categoria com demanda e sem distribuidor é onde falta fornecedor novo.

Demanda = itens dos editais abertos (mesma base do Radar de Informática, ao vivo).
Oferta = resumo dos catálogos em assets/fornecedores_informatica.json (snapshot, gerado
por cotacao_informatica/snapshot_fornecedores.py). Produto no catálogo ≠ produto que
atende o TR — o casamento item a item continua no casar.py.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from conectar_informatica import carregar_itens_informatica
from dashboard_common import fmt_abrev, fundo_transparente
from ui_explicacao import cabecalho_pagina, regra

SNAPSHOT = json.loads(
    (Path(__file__).parent.parent / "assets" / "fornecedores_informatica.json").read_text(encoding="utf-8")
)
FORNECEDORES = [f["fornecedor"] for f in SNAPSHOT["fornecedores"]]


@st.cache_data(ttl=300)
def _itens() -> pd.DataFrame:
    return carregar_itens_informatica()


def _status(n_fornecedores: int) -> str:
    if n_fornecedores >= 2:
        return "🟢 2+ distribuidores"
    if n_fornecedores == 1:
        return "🟡 1 distribuidor"
    return "🔴 sem distribuidor"


st.title("📡 Radar de Fornecedor — Informática")

cabecalho_pagina(
    pergunta="O que os editais abertos de informática pedem, e para quais categorias "
    "falta distribuidor?",
    fonte="Demanda: itens dos editais abertos (schema `informatica`, mesma base do Radar de "
    f"Informática). Oferta: catálogos GET, TS Shara e Mazer (snapshot de {SNAPSHOT['gerado_em']}).",
)

with regra("ℹ️ Como ler"):
    st.markdown(
        "- **Demanda** conta só item classificado em categoria de informática, de edital ainda aberto "
        "(edital de serviço/locação e unitário absurdo ficam de fora, igual ao Radar de Informática).\n"
        "- **Oferta** é quantos produtos cada distribuidor tem no catálogo naquela categoria. Ter produto "
        "não garante que atende a spec do TR — isso o `casar.py` confere item a item.\n"
        "- **Status**: 🟢 2+ distribuidores (dá pra comparar preço) · 🟡 1 só (dependência) · "
        "🔴 nenhum (procurar fornecedor novo).\n"
        "- Catálogo é snapshot: atualizar com `python cotacao_informatica/snapshot_fornecedores.py` "
        "depois de rodar os `catalogo_*.py`."
    )

# ---- Oferta: produtos por categoria x distribuidor ----
oferta = pd.DataFrame(
    [
        {"categoria": cat, "fornecedor": f["fornecedor"], "produtos": d["produtos"]}
        for f in SNAPSHOT["fornecedores"]
        for cat, d in f["categorias"].items()
    ]
)
matriz = oferta.pivot_table(index="categoria", columns="fornecedor", values="produtos", fill_value=0)
matriz = matriz.reindex(columns=FORNECEDORES, fill_value=0)

# ---- Demanda: itens dos editais abertos ----
itens = _itens()
itens = itens[itens["categoria"].notna()] if not itens.empty else itens
if itens.empty:
    demanda = pd.DataFrame(columns=["categoria", "editais", "itens", "valor"])
else:
    demanda = (
        itens.groupby("categoria")
        .agg(editais=("numero_controle_pncp", "nunique"), itens=("numero_item", "size"), valor=("valor_item", "sum"))
        .reset_index()
    )

tabela = (
    demanda.set_index("categoria")
    .join(matriz, how="outer")
    .fillna({"editais": 0, "itens": 0, "valor": 0.0, **{f: 0 for f in FORNECEDORES}})
)
tabela["n_fornecedores"] = (tabela[FORNECEDORES] > 0).sum(axis=1)
tabela["status"] = tabela["n_fornecedores"].apply(_status)
tabela = tabela.sort_values("valor", ascending=False)

com_demanda = tabela[tabela["itens"] > 0]
gap = com_demanda[com_demanda["n_fornecedores"] == 0]
unico = com_demanda[com_demanda["n_fornecedores"] == 1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Distribuidores", len(FORNECEDORES))
c2.metric("Produtos catalogados", f"{sum(f['produtos'] for f in SNAPSHOT['fornecedores']):,}".replace(",", "."))
c3.metric("Valor aberto sem distribuidor", f"R$ {fmt_abrev(gap['valor'].sum())}")
c4.metric("Valor aberto com 1 distribuidor só", f"R$ {fmt_abrev(unico['valor'].sum())}")

# ---- Cobertura por categoria ----
st.subheader("Cobertura por categoria")
st.caption("Ordenado pelo valor em aberto. Linha 🔴 com valor alto = prioridade pra achar fornecedor.")
mostrar = tabela.reset_index().rename(columns={"index": "categoria"})
st.dataframe(
    mostrar[["status", "categoria", "editais", "itens", "valor", *FORNECEDORES]],
    hide_index=True,
    use_container_width=True,
    column_config={
        "status": "Status",
        "categoria": "Categoria",
        "editais": st.column_config.NumberColumn("Editais abertos", format="%d"),
        "itens": st.column_config.NumberColumn("Itens", format="%d"),
        "valor": st.column_config.NumberColumn("Valor em aberto (R$)", format="%.0f"),
        **{f: st.column_config.NumberColumn(f"{f} (produtos)", format="%d") for f in FORNECEDORES},
    },
)

if not com_demanda.empty:
    graf = com_demanda.reset_index().rename(columns={"index": "categoria"})
    fig = px.bar(
        graf.sort_values("valor"),
        x="valor", y="categoria", color="status", orientation="h",
        color_discrete_map={"🟢 2+ distribuidores": "#2e9e5b", "🟡 1 distribuidor": "#e0a526",
                            "🔴 sem distribuidor": "#d64545"},
        labels={"valor": "Valor em aberto (R$)", "categoria": "", "status": ""},
        height=max(280, 34 * len(graf)),
    )
    st.plotly_chart(fundo_transparente(fig), use_container_width=True)

# ---- Distribuidores ----
st.subheader("Distribuidores")
cols = st.columns(len(SNAPSHOT["fornecedores"]))
for col, f in zip(cols, SNAPSHOT["fornecedores"]):
    with col.container(border=True):
        st.markdown(f"**{f['fornecedor']}** · {f['produtos']} produtos")
        st.caption(f"{f['site']} · catálogo de {f['catalogo_em']}")
        for cat, d in f["categorias"].items():
            marcas = ", ".join(d["marcas"])
            st.markdown(f"- {cat}: {d['produtos']} · _{marcas}_")
