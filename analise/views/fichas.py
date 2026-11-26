#!/usr/bin/env python3
"""Página — Fichas dos editais: tudo que saiu da leitura do TR/aviso de cada edital da fila
(26/nov/2026, pedido do usuário: "tudo oq vou precisar para preparar esses docs e não abrir
mais o pdf"). 3 abas: Decisão (participar ou não), Precificação (itens com o texto literal
do TR) e Documentos (checklist por fase).

Só leitura. A ficha é gravada no Claude Code (/licit-fila → gravar_ficha.py), nunca aqui.
"""

import pandas as pd
import streamlit as st
from sqlalchemy import text

from fila import ENGINE
from ui_explicacao import cabecalho_pagina

VEREDITO = {
    "participar": "🟢 Participar",
    "avaliar": "🟡 Avaliar",
    "nao_participar": "🔴 Não participar",
}
FASES = [
    ("proposta", "📝 Proposta"),
    ("habilitacao", "📂 Habilitação"),
    ("contratacao", "✍️ Contratação"),
    ("pagamento", "💰 Pagamento"),
]


@st.cache_data(ttl=30)
def _fichas() -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT f.*, e.vertical, e.pncp_url FROM fila.fichas f "
        "JOIN fila.editais e USING (numero_controle_pncp) ORDER BY f.encerramento_proposta",
        ENGINE,
    )


@st.cache_data(ttl=30)
def _tabela(nome: str, n: str) -> pd.DataFrame:
    ordem = "item" if nome == "ficha_itens" else "ordem"
    return pd.read_sql_query(
        text(f"SELECT * FROM fila.{nome} WHERE numero_controle_pncp = :n ORDER BY {ordem}"),
        ENGINE, params={"n": n},
    )


def _brl(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _linha(rotulo: str, valor) -> None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor == "":
        valor = "— (TR não informa)"
    elif isinstance(valor, bool):
        valor = "Sim" if valor else "Não"
    st.markdown(f"**{rotulo}:** {valor}")


st.title("📋 Fichas dos editais")
cabecalho_pagina(
    pergunta="Vale participar deste edital, e o que preciso pra precificar e montar os documentos?",
    fonte="Leitura do TR e do aviso de cada edital marcado com ▶ Ler TR nos radares. Tudo aqui "
    "vem do texto do documento; o que ele não traz aparece como \"TR não informa\".",
)

fichas = _fichas()
if fichas.empty:
    st.info("Nenhuma ficha ainda. Marque editais com ▶ Ler TR nos radares e peça \"processa a fila\" no Claude Code.")
    st.stop()

fichas["rotulo"] = fichas.apply(
    lambda r: f"{VEREDITO.get(r['veredito'], '⚪')} · {r['orgao']} ({r['uf']}) · {r['certame']}", axis=1
)
escolha = st.selectbox("Edital", fichas["rotulo"], index=0)
f = fichas[fichas["rotulo"] == escolha].iloc[0]
n = f["numero_controle_pncp"]

# ---- Cabeçalho: veredito + números que decidem ----
st.subheader(VEREDITO.get(f["veredito"], "⚪ Sem veredito"))
if f["veredito_motivo"]:
    st.markdown(f["veredito_motivo"])

agora = pd.Timestamp.now(tz="America/Sao_Paulo")
enc = f["encerramento_proposta"]
if pd.notna(enc):
    enc = pd.Timestamp(enc).tz_convert("America/Sao_Paulo")
    horas = (enc - agora).total_seconds() / 3600
    prazo_txt = "encerrado" if horas < 0 else f"faltam {horas:.0f}h" if horas < 48 else f"faltam {horas / 24:.0f} dias"
else:
    prazo_txt = "—"
c1, c2, c3, c4 = st.columns(4)
c1.metric("Encerra", enc.strftime("%d/%m %H:%M") if pd.notna(enc) else "—", prazo_txt, delta_color="off")
c2.metric("Valor de referência", _brl(f["valor_referencia_total"]) if not f["valor_sigiloso"] else "Sigiloso")
c3.metric("Exclusivo ME/EPP", "Sim" if f["exclusivo_me_epp"] else "Não" if f["exclusivo_me_epp"] is not None else "—")
c4.metric("Validade da proposta", f"{int(f['validade_proposta_dias'])} dias" if pd.notna(f["validade_proposta_dias"]) else "—")

if f["alertas"]:
    with st.container(border=True):
        st.markdown("**⚠️ Alertas e pegadinhas**")
        for a in f["alertas"]:
            st.markdown(f"- {a}")

aba_dec, aba_preco, aba_docs = st.tabs(["🧭 Decisão", "💲 Precificação", "📂 Documentos"])

with aba_dec:
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### Certame")
        _linha("Certame", f["certame"])
        _linha("Processo", f["processo"])
        _linha("Órgão", f["orgao"])
        _linha("Endereço do órgão", f["endereco_orgao"])
        _linha("Julgamento", f["criterio_julgamento"])
        _linha("Portal", f["portal"])
        if f["portal_url"]:
            st.markdown(f"[Abrir portal]({f['portal_url']})")
        _linha("Cadastro no portal", f["cadastro_portal"])
        _linha("Lances", f["sessao_lances"])
        _linha("Esclarecimentos", f["contato_esclarecimento"])
    with col_b:
        st.markdown("##### Execução e pagamento")
        _linha("Prazo de entrega", f["prazo_entrega"])
        _linha("Local de entrega", f["local_entrega"])
        _linha("Garantia do produto", f["garantia_produto"])
        _linha("Amostra", f["amostra"])
        _linha("Vistoria", f["vistoria"])
        _linha("Garantia de proposta", f["garantia_proposta"])
        _linha("Garantia de contrato", f["garantia_contrato"])
        _linha("Instrumento", f["instrumento"])
        _linha("Prazo de pagamento", f["prazo_pagamento"])
        _linha("Condições de pagamento", f["condicoes_pagamento"])
    links = f["links_documentos"] or []
    if links:
        st.caption("Documentos originais: " + " · ".join(f"[{l['titulo']}]({l['url']})" for l in links))

with aba_preco:
    itens = _tabela("ficha_itens", n)
    if itens.empty:
        st.info("Ficha sem itens.")
    else:
        st.dataframe(
            itens[["item", "quantidade", "unidade", "valor_ref_unit", "valor_ref_total", "garantia",
                   "exige_no_item", "produto_ofertado", "fornecedor", "custo_unit", "obs"]],
            hide_index=True, use_container_width=True,
            column_config={
                "item": "Item", "quantidade": "Qtde", "unidade": "Un.",
                "valor_ref_unit": st.column_config.NumberColumn("Ref. unit.", format="R$ %.2f"),
                "valor_ref_total": st.column_config.NumberColumn("Ref. total", format="R$ %.2f"),
                "garantia": "Garantia", "exige_no_item": "Exige",
                "produto_ofertado": "Produto ofertado", "fornecedor": "Fornecedor",
                "custo_unit": st.column_config.NumberColumn("Custo unit.", format="R$ %.2f"),
                "obs": "Obs.",
            },
        )
        st.markdown("##### Especificação de cada item (texto do TR)")
        for _, it in itens.iterrows():
            with st.expander(f"Item {it['item']} · {it['quantidade']:g} {it['unidade'] or ''} · ref. {_brl(it['valor_ref_unit'])}/un"):
                st.markdown(it["descricao_tr"] or "—")
                if it["criterios"]:
                    st.caption("Critérios pra cotação")
                    st.json(it["criterios"], expanded=False)

with aba_docs:
    docs = _tabela("ficha_documentos", n)
    if docs.empty:
        st.info("Ficha sem lista de documentos.")
    for fase, titulo in FASES:
        d = docs[docs["fase"] == fase]
        if d.empty:
            continue
        st.markdown(f"##### {titulo}")
        for _, doc in d.iterrows():
            obs = f" — {doc['observacao']}" if doc["observacao"] else ""
            st.markdown(f"- {doc['documento']} _({doc['referencia']})_{obs}")
