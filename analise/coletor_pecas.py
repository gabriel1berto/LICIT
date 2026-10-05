#!/usr/bin/env python3
"""
coletor_pecas.py — Coleta editais de peças automotivas via API de busca do PNCP.

Espelha analise_onco/coletor_onco.py (mesma API, mesmo padrão de rate-limit/
backoff), busca por LISTA de termos, grava em schema `pecas_automotivas`
(isolado de `public`/`oncologia` — nunca toca nas tabelas de pneu/onco).

Vertical de exploração de mercado (17-19/ago/2026) — mesmo estágio do
Oncológico hoje: só radar de editais abertos, sem cotação de fornecedor.
Fase 1 só (busca de edital, sem detalhe/item) — "aberto" é decidido por
`situacao_nome` + `data_fim_vigencia` (dataFimVigencia do search API, mesma
janela abertura-encerramento de proposta), sem precisar da fase 2
(coletor_detalhe) que pneu/onco usam — suficiente pro radar simples pedido.

Vocabulário (definido pelo usuário, 17/ago/2026): óleo lubrificante, graxa,
filtro de ar, bateria automotiva, filtro de combustível, amortecedor,
filtro de óleo.

Coleta diária agendada em .github/workflows/pecas_coletor_editais.yml (05/out/2026).

Uso:
    python coletor_pecas.py                     # roda todos os termos
    python coletor_pecas.py --termo "Bateria automotiva"  # só 1 termo (teste)
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import psycopg2
from curl_cffi import requests
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = "https://pncp.gov.br/api/search/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/",
}

TAM_PAGINA = 50
# Só edital recebendo proposta agora (05/out/2026): o radar só mostra edital aberto, e
# com "todos" + teto de 300 registros/termo a rodada pegava ~12 abertos de um histórico
# de 6-50 mil por termo. Filtrando na busca, o teto abaixo cobre o termo inteiro (maior
# termo tinha 809 abertos em 05/out/2026; 25 páginas = 1.250). Edital já gravado que
# encerra sai do radar sozinho pelo data_fim_vigencia, sem precisar ser recoletado.
STATUS_BUSCA = "recebendo_proposta"
MAX_PAGINAS_POR_TERMO = 25
PAUSA_ENTRE_PAGINAS = 2.5
PAUSA_ENTRE_TERMOS = 1.5
MAX_TENTATIVAS = 4

TERMOS = [
    "Óleo lubrificante",
    "Graxa",
    "Filtro de ar",
    "Bateria automotiva",
    "Filtro de combustível",
    "Amortecedor",
    "Filtro de óleo",
]


def conectar_db():
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def buscar_pagina(termo: str, pagina: int) -> dict:
    params = {
        "q": termo,
        "pagina": pagina,
        "tam_pagina": TAM_PAGINA,
        "status": STATUS_BUSCA,
        "tipos_documento": "edital",
    }
    espera = 8.0
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(BASE_URL, params=params, headers=HEADERS,
                              timeout=30, impersonate="chrome120", verify=False)
            if r.status_code == 200:
                return r.json()
            print(f"  [{termo}] pág {pagina}: HTTP {r.status_code} (tentativa {tentativa})", file=sys.stderr)
        except Exception as e:
            print(f"  [{termo}] pág {pagina}: erro '{e}' (tentativa {tentativa})", file=sys.stderr)
        time.sleep(espera)
        espera *= 1.6
    return {"total": 0, "items": []}


def upsert_edital(cur, item: dict, termo: str) -> None:
    cur.execute("""
        INSERT INTO pecas_automotivas.editais (
            numero_controle_pncp, uf, modalidade_licitacao_id, modalidade_licitacao_nome,
            municipio_nome, orgao_nome, orgao_cnpj, unidade_nome, titulo, descricao,
            ano, numero_sequencial, data_publicacao_pncp, data_atualizacao_pncp,
            data_fim_vigencia, situacao_nome, cancelado, valor_global, tem_resultado,
            item_url, termo_busca, coletado_em
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (numero_controle_pncp) DO UPDATE SET
            tem_resultado = EXCLUDED.tem_resultado,
            data_atualizacao_pncp = EXCLUDED.data_atualizacao_pncp,
            data_fim_vigencia = EXCLUDED.data_fim_vigencia,
            situacao_nome = EXCLUDED.situacao_nome,
            cancelado = EXCLUDED.cancelado,
            valor_global = EXCLUDED.valor_global
    """, (
        item.get("numero_controle_pncp"), item.get("uf"),
        item.get("modalidade_licitacao_id"), item.get("modalidade_licitacao_nome"),
        item.get("municipio_nome"), item.get("orgao_nome"), item.get("orgao_cnpj"),
        item.get("unidade_nome"), item.get("title"), item.get("description"),
        item.get("ano"), item.get("numero_sequencial"),
        item.get("data_publicacao_pncp"), item.get("data_atualizacao_pncp"),
        item.get("data_fim_vigencia"), item.get("situacao_nome"), item.get("cancelado"),
        # valor_global vem nulo no search API pra edital; o estimado está em
        # valor_total_estimado (achado 05/out/2026 — cards mostravam "sem valor").
        item.get("valor_global") or item.get("valor_total_estimado"), item.get("tem_resultado"),
        item.get("item_url"), termo, datetime.now(timezone.utc).isoformat(),
    ))


def coletar_termo(cur, termo: str) -> int:
    total_gravado = 0
    total_api = None
    for pagina in range(1, MAX_PAGINAS_POR_TERMO + 1):
        data = buscar_pagina(termo, pagina)
        total_api = data.get("total", 0)
        itens = data.get("items", [])
        if not itens:
            break
        for it in itens:
            if it.get("numero_controle_pncp"):
                upsert_edital(cur, it, termo)
                total_gravado += 1
        if pagina * TAM_PAGINA >= (total_api or 0):
            break
        time.sleep(PAUSA_ENTRE_PAGINAS)

    cur.execute("""
        INSERT INTO pecas_automotivas.vocabulario_termos (termo, total_ultima_busca, ultima_busca_em)
        VALUES (%s, %s, now())
        ON CONFLICT (termo) DO UPDATE SET total_ultima_busca = EXCLUDED.total_ultima_busca,
                                           ultima_busca_em = now()
    """, (termo, total_api))
    print(f"'{termo}': total_api={total_api}, gravados_nesta_rodada={total_gravado}", flush=True)
    return total_gravado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termo", help="rodar só 1 termo (teste)")
    args = ap.parse_args()

    con, cur = conectar_db()

    if args.termo:
        coletar_termo(cur, args.termo)
        con.commit()
        con.close()
        return

    total_geral = 0
    for termo in TERMOS:
        try:
            total_geral += coletar_termo(cur, termo)
            con.commit()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"  conexao caiu ({e}); reconectando e tentando '{termo}' de novo...", file=sys.stderr)
            try:
                con.close()
            except Exception:
                pass
            time.sleep(3)
            con, cur = conectar_db()
            total_geral += coletar_termo(cur, termo)
            con.commit()
        time.sleep(PAUSA_ENTRE_TERMOS)

    print(f"\nTOTAL gravado nesta rodada: {total_geral}")
    con.close()


if __name__ == "__main__":
    main()
