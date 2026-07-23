#!/usr/bin/env python3
"""
recomputar_filtro_onco.py — Reaplica eh_medicamento_onco_de_verdade()/
principio_ativo_provavel() (fixes 23/jul/2026: 5 usos duplos, exclusão de serviço,
exclusão oftálmica, 9 fármacos novos, bug de ordem invertida de catálogo) nos itens
já coletados no Postgres/Supabase, sem chamar a API de novo. Espelha
analise/recomputar_filtro.py (pneu), mas contra oncologia.itens. Uso único, rodar
após um fix no filtro_onco.py.
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

from filtro_onco import eh_medicamento_onco_de_verdade, principio_ativo_provavel


def conectar_db():
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def main() -> None:
    con, cur = conectar_db()
    cur.execute("SELECT numero_controle_pncp, numero_item, descricao, material_ou_servico FROM oncologia.itens")
    linhas = cur.fetchall()

    atualizacoes = []
    for pncp, item, descricao, mos in linhas:
        novo_eh_onco = eh_medicamento_onco_de_verdade(descricao, mos)
        novo_principio = principio_ativo_provavel(descricao) if novo_eh_onco else None
        atualizacoes.append((novo_eh_onco, novo_principio, pncp, item))

    psycopg2.extras.execute_batch(
        cur,
        "UPDATE oncologia.itens SET eh_medicamento_onco = %s, principio_ativo_provavel = %s "
        "WHERE numero_controle_pncp = %s AND numero_item = %s",
        atualizacoes,
        page_size=500,
    )
    con.commit()

    total = len(linhas)
    cur.execute("SELECT COUNT(*) FROM oncologia.itens WHERE eh_medicamento_onco = TRUE")
    agora_onco = cur.fetchone()[0]
    print(f"Reprocessados {total} itens.")
    print(f"eh_medicamento_onco=TRUE agora: {agora_onco}")

    cur.close()
    con.close()


if __name__ == "__main__":
    main()
