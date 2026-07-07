#!/usr/bin/env python3
"""
migrar_para_supabase.py — Migração única (one-shot) do pncp_raw.db local
(SQLite) para o Postgres do Supabase. Rodar uma vez, DEPOIS de aplicar
analise/schema_supabase.sql no projeto novo. Idempotente (ON CONFLICT DO
NOTHING) — seguro rodar de novo se cair no meio.

Uso:
    python analise/migrar_para_supabase.py                  # migra as 6 tabelas
    python analise/migrar_para_supabase.py --tabela itens    # só uma (retomar/depurar)
"""
import argparse
import os
import sqlite3
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DB_SQLITE = Path(__file__).parent / "pncp_raw.db"
TAMANHO_LOTE = 2000

# (tabela, [colunas na ordem do schema], {colunas que são BOOLEAN no Postgres})
TABELAS = [
    ("filas", ["uf", "proxima_pagina", "total_esperado", "concluida", "atualizado_em"],
     {"concluida"}),
    ("editais", [
        "numero_controle_pncp", "uf", "modalidade_licitacao_id", "modalidade_licitacao_nome",
        "municipio_nome", "orgao_nome", "orgao_cnpj", "unidade_nome", "titulo", "descricao",
        "ano", "numero_sequencial", "data_publicacao_pncp", "data_atualizacao_pncp",
        "situacao_nome", "valor_global", "tem_resultado", "item_url", "classificacao",
        "dentro_periodo_alvo", "json_bruto", "coletado_em",
    ], {"tem_resultado", "dentro_periodo_alvo"}),
    ("progresso_detalhe", ["numero_controle_pncp", "status", "tentativas", "atualizado_em"],
     set()),
    ("detalhes", [
        "numero_controle_pncp", "valor_total_estimado", "valor_total_homologado", "srp",
        "objeto_compra", "municipio_nome", "codigo_ibge", "uf_sigla", "modalidade_nome",
        "modo_disputa_nome", "poder_id", "esfera_id", "situacao_compra_nome", "existe_resultado",
        "data_abertura_proposta", "data_encerramento_proposta", "link_sistema_origem",
        "usuario_nome", "coletado_em",
    ], {"srp", "existe_resultado"}),
    ("itens", [
        "numero_controle_pncp", "numero_item", "descricao", "material_ou_servico",
        "valor_unitario_estimado", "valor_total", "quantidade", "unidade_medida",
        "situacao_item_nome", "criterio_julgamento_nome", "tipo_beneficio_nome",
        "ncm_nbs_codigo", "tem_resultado", "eh_pneu", "categoria",
    ], {"tem_resultado", "eh_pneu"}),
    ("resultados", [
        "numero_controle_pncp", "numero_item", "ni_fornecedor", "nome_fornecedor",
        "tipo_pessoa", "porte_fornecedor_nome", "valor_unitario_homologado",
        "valor_total_homologado", "percentual_desconto", "quantidade_homologada",
        "ordem_classificacao_srp", "data_resultado",
    ], set()),
]


def migrar_tabela(sqlite_con, pg_cur, nome, colunas, colunas_bool) -> int:
    idx_bool = {colunas.index(c) for c in colunas_bool}
    sql_select = f"SELECT {', '.join(colunas)} FROM {nome}"
    sql_insert = f"INSERT INTO {nome} ({', '.join(colunas)}) VALUES %s ON CONFLICT DO NOTHING"

    cur_sqlite = sqlite_con.execute(sql_select)
    total = 0
    while True:
        linhas = cur_sqlite.fetchmany(TAMANHO_LOTE)
        if not linhas:
            break
        linhas = [
            tuple(bool(v) if i in idx_bool and v is not None else v for i, v in enumerate(row))
            for row in linhas
        ]
        psycopg2.extras.execute_values(pg_cur, sql_insert, linhas, page_size=TAMANHO_LOTE)
        total += len(linhas)
        print(f"  {nome}: {total} linhas migradas...")
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tabela", type=str, default=None, help="migra só essa tabela")
    args = parser.parse_args()

    alvo = [t for t in TABELAS if args.tabela is None or t[0] == args.tabela]
    if not alvo:
        raise SystemExit(f"Tabela desconhecida: {args.tabela}")

    sqlite_con = sqlite3.connect(f"file:{DB_SQLITE}?mode=ro", uri=True)
    pg_con = psycopg2.connect(os.environ["DATABASE_URL"])
    pg_cur = pg_con.cursor()

    try:
        for nome, colunas, colunas_bool in alvo:
            print(f"Migrando {nome}...")
            total = migrar_tabela(sqlite_con, pg_cur, nome, colunas, colunas_bool)
            pg_con.commit()
            print(f"{nome}: {total} linhas OK (commit).")
    finally:
        pg_cur.close()
        pg_con.close()
        sqlite_con.close()

    print("Migração concluída.")


if __name__ == "__main__":
    main()
