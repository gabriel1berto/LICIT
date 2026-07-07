#!/usr/bin/env python3
"""
recomputar_filtro.py — Reaplica eh_pneu_de_verdade()/classificar_categoria() (regex
corrigido jul/2026, exclusão de veículo inteiro) nos itens já coletados no
Postgres/Supabase, sem chamar a API de novo. Uso único, rodar após um fix no regex.
"""

import psycopg2.extras

from coletor_pncp_detalhe import classificar_categoria, eh_pneu_de_verdade, conectar_db


def main() -> None:
    con, cur = conectar_db()
    cur.execute("SELECT numero_controle_pncp, numero_item, descricao FROM itens")
    linhas = cur.fetchall()

    atualizacoes = []
    for pncp, item, descricao in linhas:
        novo_eh_pneu = eh_pneu_de_verdade(descricao)
        nova_categoria = classificar_categoria(descricao) if novo_eh_pneu else None
        atualizacoes.append((novo_eh_pneu, nova_categoria, pncp, item))

    psycopg2.extras.execute_batch(
        cur,
        "UPDATE itens SET eh_pneu = %s, categoria = %s WHERE numero_controle_pncp = %s AND numero_item = %s",
        atualizacoes,
    )
    con.commit()

    total = len(linhas)
    cur.execute("SELECT COUNT(*) FROM itens WHERE eh_pneu = TRUE")
    agora_pneu = cur.fetchone()[0]
    print(f"Reprocessados {total} itens.")
    print(f"eh_pneu=TRUE agora: {agora_pneu}")

    cur.close()
    con.close()


if __name__ == "__main__":
    main()
