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

from filtro_pecas import classificar_objeto_pecas

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

    # PNCP devolve o campo ora com segundos ("...T23:59:59"), ora sem ("...T09:00") —
    # sem format explícito o pandas infere pelo 1º valor e quebra no outro (achado 05/out/2026).
    # Ano digitado errado pelo órgão (ex: "5026-08-14") estoura o limite do Timestamp — a
    # query já garante data futura e não nula, então NaT aqui é só esse caso: joga pra uma
    # data distante válida, que cai na coluna "Vigência longa" do radar em vez de sumir.
    df["data_fim_vigencia"] = pd.to_datetime(
        df["data_fim_vigencia"], format="ISO8601", errors="coerce"
    ).fillna(pd.Timestamp("2200-01-01"))
    agora_brt = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)
    df["dias_restantes"] = (df["data_fim_vigencia"] - agora_brt).dt.total_seconds() / 86400
    # Tipo pelo OBJETO do edital, não pelo termo de busca (ver filtro_pecas.py) — None
    # quando o objeto não tem sinal de peça automotiva (móvel planejado, hospitalar etc.).
    df["tipo_objeto"] = (df["titulo"].fillna("") + " " + df["descricao"].fillna("")).apply(
        classificar_objeto_pecas
    )
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
