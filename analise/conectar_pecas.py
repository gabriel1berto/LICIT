#!/usr/bin/env python3
"""
conectar_pecas.py — Base de editais de peças automotivas (Supabase, schema
`pecas_automotivas`, ver coletor_pecas.py). Vertical de exploração de mercado,
fase 1 só — sem tabela de detalhe/item, "aberto" decidido por
`situacao_nome` + `data_fim_vigencia` (mesma janela abertura-encerramento
que o search API do PNCP retorna, sem precisar da fase 2).
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def carregar_editais_abertos_pecas() -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, orgao_cnpj, ano, numero_sequencial,
               uf, municipio_nome AS municipio, orgao_nome, modalidade_licitacao_nome,
               titulo, descricao, valor_global, data_fim_vigencia, termo_busca
        FROM pecas_automotivas.editais
        WHERE situacao_nome = 'Divulgada no PNCP'
          AND COALESCE(cancelado, FALSE) = FALSE
          AND data_fim_vigencia IS NOT NULL
          AND data_fim_vigencia::timestamp > (now() AT TIME ZONE 'America/Sao_Paulo')
        """,
        ENGINE,
    )
    if df.empty:
        return df

    df["data_fim_vigencia"] = pd.to_datetime(df["data_fim_vigencia"])
    agora_brt = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)
    df["dias_restantes"] = (df["data_fim_vigencia"] - agora_brt).dt.total_seconds() / 86400
    df["pncp_url"] = (
        "https://pncp.gov.br/app/editais/" + df["orgao_cnpj"] + "/" + df["ano"] + "/" + df["numero_sequencial"]
    )

    # 1 edital pode ter batido mais de 1 termo (ex: "óleo lubrificante" e "filtro
    # de óleo" no mesmo objeto) — junta os termos numa linha só em vez de duplicar
    # o card no radar.
    termos_por_edital = df.groupby("numero_controle_pncp")["termo_busca"].apply(
        lambda s: ", ".join(sorted(set(s)))
    )
    df = df.drop_duplicates(subset="numero_controle_pncp").set_index("numero_controle_pncp")
    df["termo_busca"] = termos_por_edital
    return df.reset_index()


def cobertura_vocabulario_pecas() -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT termo, total_ultima_busca, ultima_busca_em FROM pecas_automotivas.vocabulario_termos "
        "ORDER BY total_ultima_busca DESC",
        ENGINE,
    )


if __name__ == "__main__":
    df = carregar_editais_abertos_pecas()
    print(f"Editais abertos com peça automotiva: {len(df)}")
    if not df.empty:
        print(df["uf"].value_counts())
