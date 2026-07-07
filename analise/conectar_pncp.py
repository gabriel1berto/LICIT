#!/usr/bin/env python3
"""
conectar_pncp.py — Base de itens de pneu a partir do Postgres/Supabase (coleta
direta da API do PNCP, ver coletor_pncp.py/coletor_pncp_detalhe.py). Antes era
pncp_raw.db local (SQLite) — migrado jul/2026, ver analise/schema_supabase.sql.

Diferente de conectar.py (ComprasGOV bulk): esta fonte cobre as 27 UFs sem o
gap de ~17x já documentado, mas a coleta por processo (fase 2) é gradual —
`cobertura_pct()` informa quanto já foi baixado.

Uso:
    from conectar_pncp import carregar_base_pncp, cobertura_pct
    df = carregar_base_pncp()
"""

import os
import re

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# pool_pre_ping evita erro de "conexão morta" quando o pooler do Supabase
# derruba conexão idle entre reruns do Streamlit.
ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

# medida tipo "215/75 R17,5" ou "205/60 R16" — captura largura/perfil/aro. Só cobre o
# padrão passeio/caminhão/moto; agrícola ("18.4-30") e câmara de ar têm formato próprio,
# não capturados aqui — ficam como NaN em medida_extraida.
RE_MEDIDA_CAPTURA = re.compile(r"(\d{3})\s*/\s*(\d{2})\s*[Rr]\s*(\d{2}(?:[.,]\d)?)")


def _extrair_medida(descricao: str) -> str | None:
    if not isinstance(descricao, str):
        return None
    m = RE_MEDIDA_CAPTURA.search(descricao)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)} R{m.group(3).replace(',', '.')}"


def carregar_concorrencia() -> pd.DataFrame:
    """1 linha por (processo, item, fornecedor ofertante) — TODOS os ofertantes, não só o
    vencedor. Base pra concorrência em 3 granularidades: edital, item, produto/medida.
    """
    return pd.read_sql_query(
        """
        SELECT r.numero_controle_pncp, r.numero_item, r.ni_fornecedor
        FROM resultados r
        JOIN itens i ON i.numero_controle_pncp = r.numero_controle_pncp AND i.numero_item = r.numero_item
        WHERE i.eh_pneu = TRUE
        """,
        ENGINE,
    )


def cobertura_por_uf() -> pd.DataFrame:
    """Cobertura de coleta (fase 2) por UF — feito/total/pct, pra normalizar leitura de
    volume geográfico (UF com mais % coletado aparece maior sem ser maior de verdade)."""
    cov = pd.read_sql_query(
        """
        SELECT e.uf, COUNT(DISTINCT d.numero_controle_pncp) AS feito, COUNT(DISTINCT e.numero_controle_pncp) AS total
        FROM editais e
        LEFT JOIN detalhes d ON d.numero_controle_pncp = e.numero_controle_pncp
        WHERE e.dentro_periodo_alvo = TRUE
        GROUP BY e.uf
        """,
        ENGINE,
    )
    cov["cobertura_pct"] = (cov["feito"] / cov["total"] * 100).round(1)
    return cov


def cobertura_pct() -> tuple[int, int, float]:
    """(processos com detalhe já baixado, total no período alvo, %)."""
    with ENGINE.connect() as con:
        feito = con.execute(text("SELECT COUNT(*) FROM detalhes")).fetchone()[0]
        total = con.execute(text("SELECT COUNT(*) FROM editais WHERE dentro_periodo_alvo = TRUE")).fetchone()[0]
    pct = (feito / total * 100) if total else 0.0
    return feito, total, pct


def _classificar_tipo(modalidade: str) -> str:
    if not modalidade:
        return "Outro"
    m = modalidade.lower()
    if m.startswith("pregão"):
        return "Pregão"
    if m.startswith("dispensa"):
        return "Dispensa"
    if m.startswith("concorrência") or m.startswith("concorrencia"):
        return "Concorrência"
    return "Outro"


def carregar_base_pncp() -> pd.DataFrame:
    """1 linha por item elegível (eh_pneu=1), mesmo shape de colunas da base ComprasGOV
    (base_pneu.sql) pra reusar a mesma lógica de gráfico se algum dia fizer sentido —
    mas o dashboard_pncp.py usa suas próprias abas, não compartilha código com dashboard.py.
    """
    itens = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, descricao, valor_total AS valor_item,
               valor_unitario_estimado, quantidade, tem_resultado, categoria
        FROM itens
        WHERE eh_pneu = TRUE
        """,
        ENGINE,
    )

    detalhes = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, uf_sigla AS uf, municipio_nome AS municipio,
               codigo_ibge, modalidade_nome, srp, data_abertura_proposta,
               valor_total_estimado
        FROM detalhes
        """,
        ENGINE,
    )

    # 1 resultado por item: menor ordem_classificacao_srp (1º colocado / vencedor)
    resultados = pd.read_sql_query(
        """
        SELECT r.numero_controle_pncp, r.numero_item, r.ni_fornecedor AS cod_fornecedor,
               r.nome_fornecedor, r.valor_unitario_homologado AS valor_unitario_resultado,
               r.valor_total_homologado AS valor_total_resultado
        FROM resultados r
        JOIN (
            SELECT numero_controle_pncp, numero_item, MIN(ordem_classificacao_srp) AS min_ordem
            FROM resultados
            GROUP BY numero_controle_pncp, numero_item
        ) m ON m.numero_controle_pncp = r.numero_controle_pncp
           AND m.numero_item = r.numero_item
           AND (r.ordem_classificacao_srp = m.min_ordem OR m.min_ordem IS NULL)
        """,
        ENGINE,
    )

    df = itens.merge(detalhes, on="numero_controle_pncp", how="left")
    df = df.merge(resultados, on=["numero_controle_pncp", "numero_item"], how="left")

    df["codigo_ibge"] = pd.to_numeric(df["codigo_ibge"], errors="coerce")
    df["data_abertura_proposta"] = pd.to_datetime(df["data_abertura_proposta"], errors="coerce", utc=True)
    df["ano_mes"] = df["data_abertura_proposta"].dt.strftime("%Y-%m")
    df["tipo"] = df["modalidade_nome"].apply(_classificar_tipo)
    df["regime"] = df["srp"].apply(lambda v: "RP" if v else "CD")
    df["cod_compra"] = df["numero_controle_pncp"]
    df["tem_resultado"] = df["tem_resultado"].astype(bool)
    df["medida_extraida"] = df["descricao"].apply(_extrair_medida)

    return df


if __name__ == "__main__":
    feito, total, pct = cobertura_pct()
    print(f"Cobertura: {feito}/{total} processos ({pct:.1f}%)")
    df = carregar_base_pncp()
    print(f"Itens elegíveis (eh_pneu=1): {len(df)}")
    print(df["uf"].value_counts())
