#!/usr/bin/env python3
"""fila.py — Botões ⭐ Interesse / ▶ Ler TR dos cards dos radares (26/nov/2026).

O dashboard SÓ grava a marcação em fila.editais (ver sql/fila_editais.sql). Nenhum botão
daqui lê PDF, chama Claude ou escreve no Notion — isso continua fora do dashboard: a
leitura do TR e a ficha do edital rodam no Claude Code (/licit-fila), que lê os pedidos
com status 'na_fila' e grava a ficha (fila.fichas/ficha_itens/ficha_documentos, via
gravar_ficha.py) e status='lido' de volta. A ficha aparece na página 📋 Fichas.

Botões ficam abertos (sem senha), decisão do usuário: o pior caso é alguém marcar ou
desmarcar edital — nada é lido sem o comando no Claude Code.
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

STATUS_LABEL = {
    "marcado": "⭐ Interesse",
    "na_fila": "⏳ Na fila pra ler o TR",
    "lido": "✅ TR lido — ficha pronta",
    "erro": "⚠️ Erro na leitura",
}


@st.cache_data(ttl=30)
def carregar_fila(vertical: str) -> pd.DataFrame:
    return pd.read_sql_query(
        text("SELECT * FROM fila.editais WHERE vertical = :v"), ENGINE, params={"v": vertical}
    ).set_index("numero_controle_pncp")


def _gravar(row: dict, vertical: str, interesse: bool, ler_tr: bool) -> None:
    with ENGINE.begin() as con:
        if not interesse and not ler_tr:
            con.execute(text("DELETE FROM fila.editais WHERE numero_controle_pncp = :n"),
                        {"n": row["numero_controle_pncp"]})
        else:
            con.execute(
                text("""
                INSERT INTO fila.editais (numero_controle_pncp, vertical, orgao_nome, uf, pncp_url,
                                          interesse, ler_tr, status, ler_pedido_em)
                VALUES (:n, :v, :o, :uf, :url, :i, :l, :s, CASE WHEN :l THEN now() END)
                ON CONFLICT (numero_controle_pncp) DO UPDATE SET
                    interesse = EXCLUDED.interesse,
                    ler_tr = EXCLUDED.ler_tr,
                    -- ficha já lida não volta pra fila só porque o botão foi clicado de novo
                    status = CASE WHEN fila.editais.status = 'lido' AND EXCLUDED.ler_tr
                                  THEN 'lido' ELSE EXCLUDED.status END,
                    ler_pedido_em = COALESCE(fila.editais.ler_pedido_em, EXCLUDED.ler_pedido_em)
                """),
                {"n": row["numero_controle_pncp"], "v": vertical, "o": row.get("orgao_nome"),
                 "uf": row.get("uf"), "url": row.get("pncp_url"), "i": interesse, "l": ler_tr,
                 "s": "na_fila" if ler_tr else "marcado"},
            )
    carregar_fila.clear()


def botoes_fila(row: pd.Series, vertical: str, fila: pd.DataFrame) -> None:
    """2 botões no card: ⭐ marca interesse; ▶ Ler TR põe na fila (e marca interesse junto)."""
    n = row["numero_controle_pncp"]
    atual = fila.loc[n] if n in fila.index else None
    interesse = bool(atual is not None and atual["interesse"])
    ler_tr = bool(atual is not None and atual["ler_tr"])
    dados = {k: row.get(k) for k in ("numero_controle_pncp", "orgao_nome", "uf", "pncp_url")}

    if atual is not None:
        st.caption(f"**{STATUS_LABEL.get(atual['status'], atual['status'])}**")
    c1, c2 = st.columns(2)
    c1.button(
        "★ Tirar" if interesse else "⭐ Interesse", key=f"int_{vertical}_{n}", use_container_width=True,
        on_click=_gravar, args=(dados, vertical, not interesse, ler_tr and not interesse),
    )
    c2.button(
        "✖ Tirar da fila" if ler_tr else "▶ Ler TR", key=f"ler_{vertical}_{n}", use_container_width=True,
        on_click=_gravar, args=(dados, vertical, True if not ler_tr else interesse, not ler_tr),
    )


def resumo_fila(fila: pd.DataFrame) -> None:
    """Linha no topo da página: quantos marcados / na fila / lidos, com a lista num expander."""
    if fila.empty:
        st.caption("⭐ Nenhum edital marcado ainda. Use ⭐ Interesse ou ▶ Ler TR nos cards.")
        return
    cont = fila["status"].value_counts()
    partes = [f"{STATUS_LABEL[s]}: {int(cont[s])}" for s in STATUS_LABEL if s in cont]
    with st.expander("📋 Minha fila — " + " · ".join(partes)):
        st.dataframe(
            fila.reset_index()[["status", "orgao_nome", "uf", "marcado_em", "lido_em", "pncp_url"]]
            .assign(status=lambda d: d["status"].map(STATUS_LABEL)),
            hide_index=True, use_container_width=True,
            column_config={
                "status": "Status", "orgao_nome": "Órgão", "uf": "UF",
                "marcado_em": st.column_config.DatetimeColumn("Marcado em", format="DD/MM HH:mm"),
                "lido_em": st.column_config.DatetimeColumn("Lido em", format="DD/MM HH:mm"),
                "pncp_url": st.column_config.LinkColumn("PNCP", display_text="Abrir"),
            },
        )
        st.caption("A leitura do TR roda no Claude Code: diga \"processa a fila\".")
