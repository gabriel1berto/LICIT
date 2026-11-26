#!/usr/bin/env python3
"""gravar_ficha.py — Grava a ficha de um edital (lida do TR/aviso no Claude Code) nas
tabelas fila.fichas / fila.ficha_itens / fila.ficha_documentos e marca o pedido da fila
como lido. Ver sql/fichas_edital.sql.

Uso:
    python analise/gravar_ficha.py ficha.json

ficha.json = {"ficha": {colunas de fila.fichas, com numero_controle_pncp},
              "itens": [{colunas de fila.ficha_itens}],
              "documentos": [{colunas de fila.ficha_documentos}]}
Regrava tudo do edital (itens e documentos antigos saem).
"""

import json
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

JSONB = {"links_documentos", "criterios"}


def _upsert(con, tabela: str, linha: dict, chave: list[str]) -> None:
    cols = list(linha)
    vals = ", ".join(f"CAST(:{c} AS jsonb)" if c in JSONB else f":{c}" for c in cols)
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in chave) or f"{chave[0]} = EXCLUDED.{chave[0]}"
    params = {c: json.dumps(v, ensure_ascii=False) if c in JSONB and v is not None else v for c, v in linha.items()}
    con.execute(
        text(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({vals}) "
             f"ON CONFLICT ({', '.join(chave)}) DO UPDATE SET {sets}"),
        params,
    )


def gravar(dados: dict) -> None:
    ficha = dados["ficha"]
    n = ficha["numero_controle_pncp"]
    with ENGINE.begin() as con:
        _upsert(con, "fila.fichas", ficha, ["numero_controle_pncp"])
        con.execute(text("UPDATE fila.fichas SET lido_em = now() WHERE numero_controle_pncp = :n"), {"n": n})
        con.execute(text("DELETE FROM fila.ficha_itens WHERE numero_controle_pncp = :n"), {"n": n})
        con.execute(text("DELETE FROM fila.ficha_documentos WHERE numero_controle_pncp = :n"), {"n": n})
        for it in dados.get("itens", []):
            _upsert(con, "fila.ficha_itens", {"numero_controle_pncp": n, **it}, ["numero_controle_pncp", "item"])
        for i, doc in enumerate(dados.get("documentos", []), 1):
            _upsert(con, "fila.ficha_documentos", {"numero_controle_pncp": n, "ordem": i, **doc},
                    ["numero_controle_pncp", "ordem"])
        con.execute(
            text("UPDATE fila.editais SET status = 'lido', lido_em = now(), observacao = :o "
                 "WHERE numero_controle_pncp = :n"),
            {"n": n, "o": ficha.get("veredito_motivo")},
        )
    print(f"{n}: ficha + {len(dados.get('itens', []))} itens + {len(dados.get('documentos', []))} documentos gravados")


if __name__ == "__main__":
    gravar(json.load(open(sys.argv[1], encoding="utf-8")))
