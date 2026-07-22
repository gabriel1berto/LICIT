#!/usr/bin/env python3
"""
conectar_onco.py — Acesso ao schema `oncologia` (Postgres/Supabase), espelhando
analise/conectar_pncp.py mas isolado — nunca lê/escreve public.* nem
cotacao_fornecedor.*.

Uso:
    from conectar_onco import carregar_editais, cobertura_vocabulario
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def carregar_editais() -> pd.DataFrame:
    """1 linha por edital coletado (schema oncologia.editais)."""
    df = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, uf, modalidade_licitacao_nome, municipio_nome,
               orgao_nome, orgao_cnpj, titulo, descricao, ano, numero_sequencial,
               data_publicacao_pncp, situacao_nome, valor_global, tem_resultado,
               termo_busca, coletado_em
        FROM oncologia.editais
        """,
        ENGINE,
    )
    if df.empty:
        return df
    df["data_publicacao_pncp"] = pd.to_datetime(df["data_publicacao_pncp"], errors="coerce", utc=True)
    df["ano_mes"] = df["data_publicacao_pncp"].dt.strftime("%Y-%m")

    def _tipo(m):
        if not isinstance(m, str):
            return "Outro"
        m = m.lower()
        if m.startswith("pregão") or m.startswith("pregao"):
            return "Pregão"
        if m.startswith("dispensa"):
            return "Dispensa"
        if m.startswith("inexigibilidade"):
            return "Inexigibilidade"
        if m.startswith("concorrência") or m.startswith("concorrencia"):
            return "Concorrência"
        return "Outro"

    df["tipo"] = df["modalidade_licitacao_nome"].apply(_tipo)
    return df


def cobertura_vocabulario() -> pd.DataFrame:
    """1 linha por termo buscado — total real na API vs quando foi buscado."""
    return pd.read_sql_query(
        "SELECT termo, tipo, total_ultima_busca, ultima_busca_em FROM oncologia.vocabulario_termos ORDER BY total_ultima_busca DESC",
        ENGINE,
    )


if __name__ == "__main__":
    df = carregar_editais()
    print(f"Editais coletados: {len(df)}")
    if not df.empty:
        print(df["uf"].value_counts().head(10))
