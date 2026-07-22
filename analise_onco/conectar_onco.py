#!/usr/bin/env python3
"""
conectar_onco.py — Base de itens de medicamento oncológico a partir do
Postgres/Supabase (schema `oncologia`, isolado de `public`/`cotacao_fornecedor`
do pneu). Espelha analise/conectar_pncp.py — mesmo shape de coluna, mesma
lógica de agregação — pra reusar exatamente o mesmo código de dashboard.

Mapeamento de conceito (pneu → oncologia):
  medida_extraida  → principio_ativo_provavel (já computado no coletor_detalhe,
                      via filtro_onco.py — não precisa regex aqui)
  categoria        → classe_farmaco (Alquilante/Antimetabolito/Quimioterapico
                      classico/Inibidor de quinase/Anticorpo monoclonal/
                      Hormonal-endocrino/Outro — 6 classes fixas, mesmo padrão
                      de categoria fixa do pneu)

Uso:
    from conectar_onco import carregar_base_onco, cobertura_pct
    df = carregar_base_onco()
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from filtro_onco import classificar_classe_farmaco

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def cobertura_por_uf() -> pd.DataFrame:
    cov = pd.read_sql_query(
        """
        SELECT e.uf, COUNT(DISTINCT d.numero_controle_pncp) AS feito, COUNT(DISTINCT e.numero_controle_pncp) AS total
        FROM oncologia.editais e
        LEFT JOIN oncologia.detalhes d ON d.numero_controle_pncp = e.numero_controle_pncp
        GROUP BY e.uf
        """,
        ENGINE,
    )
    cov["cobertura_pct"] = (cov["feito"] / cov["total"] * 100).round(1)
    return cov


def cobertura_pct() -> tuple[int, int, float]:
    """(processos com detalhe já baixado, total de editais coletados, %)."""
    with ENGINE.connect() as con:
        feito = con.execute(text("SELECT COUNT(*) FROM oncologia.progresso_detalhe WHERE status='feito'")).fetchone()[0]
        total = con.execute(text("SELECT COUNT(*) FROM oncologia.progresso_detalhe")).fetchone()[0]
    pct = (feito / total * 100) if total else 0.0
    return feito, total, pct


def _classificar_tipo(modalidade: str) -> str:
    if not isinstance(modalidade, str) or not modalidade:
        return "Outro"
    m = modalidade.lower()
    if m.startswith("pregão") or m.startswith("pregao"):
        return "Pregão"
    if m.startswith("dispensa"):
        return "Dispensa"
    if m.startswith("concorrência") or m.startswith("concorrencia"):
        return "Concorrência"
    if m.startswith("inexigibilidade"):
        return "Inexigibilidade"
    return "Outro"


def carregar_base_onco() -> pd.DataFrame:
    """1 linha por item elegível (eh_medicamento_onco=TRUE), mesmo shape de
    coluna de carregar_base_pncp() do pneu (uf, municipio, regime, tipo,
    categoria, medida_extraida, valor_item, valor_unitario_estimado,
    valor_unitario_resultado, quantidade, tem_resultado, cod_compra, ano_mes)."""
    itens = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, descricao, valor_total AS valor_item,
               valor_unitario_estimado, quantidade, tem_resultado, principio_ativo_provavel
        FROM oncologia.itens
        WHERE eh_medicamento_onco = TRUE
        """,
        ENGINE,
    )

    detalhes = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, uf_sigla AS uf, municipio_nome AS municipio,
               codigo_ibge, modalidade_nome, srp, data_abertura_proposta,
               valor_total_estimado
        FROM oncologia.detalhes
        """,
        ENGINE,
    )

    resultados = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, ni_fornecedor AS cod_fornecedor,
               nome_fornecedor, valor_unitario_homologado AS valor_unitario_resultado,
               valor_total_homologado AS valor_total_resultado
        FROM oncologia.resultados
        WHERE valor_total_homologado IS NOT NULL AND valor_total_homologado > 0
        """,
        ENGINE,
    )
    resultados_principal = (
        resultados.sort_values("valor_total_resultado", ascending=False)
                  .drop_duplicates(subset=["numero_controle_pncp", "numero_item"], keep="first")
    )

    df = itens.merge(detalhes, on="numero_controle_pncp", how="inner")
    df = df.merge(resultados_principal, on=["numero_controle_pncp", "numero_item"], how="left")

    df["codigo_ibge"] = pd.to_numeric(df["codigo_ibge"], errors="coerce")
    df["data_abertura_proposta"] = pd.to_datetime(df["data_abertura_proposta"], errors="coerce", utc=True)
    df["ano_mes"] = df["data_abertura_proposta"].dt.strftime("%Y-%m")
    df["tipo"] = df["modalidade_nome"].apply(_classificar_tipo)
    df["regime"] = df["srp"].apply(lambda v: "RP" if v else "CD")
    df["cod_compra"] = df["numero_controle_pncp"]
    df["tem_resultado"] = df["tem_resultado"].astype(bool)
    df["medida_extraida"] = df["principio_ativo_provavel"]  # nome de coluna igual ao pneu, valor = fármaco
    df["categoria"] = df["principio_ativo_provavel"].apply(classificar_classe_farmaco)

    return df


def carregar_fornecedores_resultado() -> pd.DataFrame:
    """1 linha por (item, fornecedor real vencedor) — mesmo shape de
    carregar_fornecedores_resultado() do pneu."""
    resultados = pd.read_sql_query(
        """
        SELECT r.numero_controle_pncp, r.numero_item, r.ni_fornecedor AS cnpj_fornecedor,
               r.nome_fornecedor,
               r.valor_unitario_homologado AS valor_unitario_resultado,
               r.valor_total_homologado AS valor_total_resultado,
               i.principio_ativo_provavel, i.descricao, i.quantidade,
               d.uf_sigla AS uf, d.modalidade_nome, d.srp, d.data_abertura_proposta,
               d.valor_total_estimado
        FROM oncologia.resultados r
        JOIN oncologia.itens i ON i.numero_controle_pncp = r.numero_controle_pncp AND i.numero_item = r.numero_item
        JOIN oncologia.detalhes d ON d.numero_controle_pncp = r.numero_controle_pncp
        WHERE i.eh_medicamento_onco = TRUE
          AND r.valor_total_homologado IS NOT NULL AND r.valor_total_homologado > 0
        """,
        ENGINE,
    )
    resultados["medida_extraida"] = resultados["principio_ativo_provavel"]
    resultados["categoria"] = resultados["principio_ativo_provavel"].apply(classificar_classe_farmaco)
    resultados["tipo"] = resultados["modalidade_nome"].apply(_classificar_tipo)
    resultados["regime"] = resultados["srp"].apply(lambda v: "RP" if v else "CD")
    resultados["data_abertura_proposta"] = pd.to_datetime(resultados["data_abertura_proposta"], errors="coerce", utc=True)
    resultados["ano_mes"] = resultados["data_abertura_proposta"].dt.strftime("%Y-%m")
    return resultados


def carregar_lat_lon() -> pd.DataFrame:
    import pathlib
    ll = pd.read_csv(pathlib.Path(__file__).parent / "municipios_lat_lon.csv")
    return ll[["codigo_ibge", "latitude", "longitude"]]


def cobertura_vocabulario() -> pd.DataFrame:
    """1 linha por termo buscado — total real na API vs quando foi buscado."""
    return pd.read_sql_query(
        "SELECT termo, tipo, total_ultima_busca, ultima_busca_em FROM oncologia.vocabulario_termos ORDER BY total_ultima_busca DESC",
        ENGINE,
    )


if __name__ == "__main__":
    feito, total, pct = cobertura_pct()
    print(f"Cobertura: {feito}/{total} processos ({pct:.1f}%)")
    df = carregar_base_onco()
    print(f"Itens elegíveis (eh_medicamento_onco=1): {len(df)}")
    if not df.empty:
        print(df["uf"].value_counts())
