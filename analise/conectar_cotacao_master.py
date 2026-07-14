#!/usr/bin/env python3
"""
conectar_cotacao_master.py — Base de cotação diária de fornecedor (schema
cotacao_fornecedor, mesmo projeto Supabase do pipeline PNCP mas pipeline
separado — ver cotacao_master/README ou schema_cotacoes_diarias.sql).

Diferente de conectar_pncp.py: aquele lê `public.*` (mercado nacional PNCP,
editais de terceiros); este lê `cotacao_fornecedor.*` (preço direto cotado
nos 4 distribuidores já cadastrados, roda diário via cotacao_master.py).

Uso:
    from conectar_cotacao_master import carregar_cotacoes, contar_aliases_pendentes
    df = carregar_cotacoes()
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def carregar_cotacoes() -> pd.DataFrame:
    """1 linha por cotação (produto individual), com medida canônica e todo
    o detalhamento técnico já resolvido (join com medidas)."""
    return pd.read_sql_query(
        """
        SELECT
            c.id, c.fornecedor, c.preco, c.timestamp, c.confianca_match,
            c.marca, c.url, c.apto, c.ic, c.iv, c.treadwear, c.construcao,
            c.num_lonas, c.tipo_terreno, c.inmetro, c.texto_bruto_origem,
            c.observacao,
            m.texto_canonico AS medida, m.largura, m.perfil, m.aro
        FROM cotacao_fornecedor.cotacoes c
        JOIN cotacao_fornecedor.medidas m ON m.id = c.medida_id
        ORDER BY c.timestamp
        """,
        ENGINE,
    )


def contar_aliases_pendentes() -> int:
    with ENGINE.connect() as con:
        return con.execute(
            text("SELECT COUNT(*) FROM cotacao_fornecedor.aliases_medida WHERE aprovado_por_humano = FALSE")
        ).scalar()


def carregar_aliases_pendentes_detalhe() -> pd.DataFrame:
    """Lista completa (não só contagem) — só leitura. Aprovação de verdade é
    manual via revisar_aliases_pendentes.py (terminal, privado) — dashboard é
    público, não expõe ação de escrita aqui."""
    return pd.read_sql_query(
        """
        SELECT a.id, a.fornecedor, a.texto_bruto, a.inferido, a.created_at,
               m.texto_canonico AS medida
        FROM cotacao_fornecedor.aliases_medida a
        JOIN cotacao_fornecedor.medidas m ON m.id = a.medida_id
        WHERE a.aprovado_por_humano = FALSE
        ORDER BY a.created_at
        """,
        ENGINE,
    )
