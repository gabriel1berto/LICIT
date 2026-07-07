#!/usr/bin/env python3
"""
coletor_pncp.py — Coleta direta da API de busca do PNCP (não do ComprasGOV/SEGES).

Por quê: auditoria em jul/2026 encontrou gap de ~17x entre ComprasGOV (bulk CSV
usado em base_pneu.sql) e a busca ao vivo do PNCP pro mesmo estado/período —
ver README.md, seção "Discrepância ComprasGOV vs PNCP". Esse script busca direto
na fonte que o PNCP expõe, sem depender do export do compras.gov.br.

Decisões tomadas com base em teste real na API (não suposição):
  - Parâmetro `modalidades` OMITIDO de propósito: testamos e sem ele a API já
    retorna TODAS as modalidades (316 resultados p/ ES vs 182 só com
    modalidades=6) — mais simples e mais completo que enumerar IDs.
  - Parâmetros `data_publicacao_inicio`/`data_publicacao_fim` NÃO SÃO
    HONRADOS pela API — testamos pedindo só >=2025-01-01 e voltou registro de
    2024 igual, total idêntico ao sem filtro. O filtro de período (jan/25 até
    ontem) é aplicado no lado do cliente, depois de baixar.
  - Resultado NÃO vem ordenado por data (testamos página 1 vs página final,
    datas espalhadas em ambas) — não dá pra parar a paginação cedo. Precisa
    varrer TODAS as páginas de cada UF pra garantir que nada do período alvo
    fica de fora.
  - Todo registro é gravado (não descarta o que está fora do período) — fica
    marcado em `dentro_periodo_alvo`. Preferível a perder dado numa raspagem
    que roda a noite inteira sem supervisão.

Classificação "é pneu de verdade?" nesse nível (título + descrição do
processo, não item): mais fraca que o filtro item-a-item que construímos pro
ComprasGOV (base_pneu.sql) — aqui não temos o item individual, só o texto do
edital. Aplicamos as mesmas armadilhas já mapeadas hoje:
  - "pneumático" sozinho é ADJETIVO (sistema pneumático, cadeira pneumática) —
    não conta como produto pneu.
  - Máquina pesada descrita "com pneus" (carregadeira, motoniveladora, trator,
    retroescavadeira) — o produto é a máquina, não o pneu.
  - Serviço puro (recapagem, vulcanização, alinhamento, balanceamento,
    conserto, manutenção de veículo) sem menção clara de aquisição/compra —
    não é compra de pneu.
Como aqui é texto corrido (não item de catálogo), a classificação vira um
RÓTULO de confiança (`classificacao`), não um filtro que descarta — a
decisão de cortar fica pra hora de analisar, com a mesma cautela do
README: sempre auditar uma amostra antes de confiar no número agregado.

Uso:
    python coletor_pncp.py                  # roda até esgotar todas as UFs
    python coletor_pncp.py --status         # só mostra progresso, não coleta
    python coletor_pncp.py --uf SP          # roda só uma UF (teste/depuração)
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuração ──────────────────────────────────────────────────────────

LOG_PATH = Path(__file__).parent / "coletor_pncp.log"

TODAS_UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
]

TERMO_BUSCA = "Pneu"

# Período alvo — API não honra filtro de data, aplicado no cliente (ver nota acima).
PERIODO_INICIO = "2025-01-01"
PERIODO_FIM = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")  # "ontem"

TAM_PAGINA = 50
PAUSA_ENTRE_PAGINAS = 2.5     # segundos
PAUSA_APOS_ERRO_BASE = 20.0   # segundos — dobra a cada tentativa (backoff)
MAX_TENTATIVAS_POR_PAGINA = 6
ESPACO_MINIMO_MB = 200        # pausa a coleta se disco livre cair abaixo disso

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/",
}

BASE_URL = "https://pncp.gov.br/api/search/"


# ── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("coletor_pncp")


# ── Classificação "é pneu de verdade?" — módulo único, ver filtro_pneu.py ──

from filtro_pneu import classificar_pneu


# ── Banco (Supabase/Postgres) ────────────────────────────────────────────
# DDL vive em analise/schema_supabase.sql, aplicado uma única vez — não é
# mais recriado a cada run (era assim no SQLite local, sem custo de fazê-lo
# toda vez; contra Postgres remoto isso só seria round-trip desperdiçado).

def conectar_db() -> tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor]:
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def dentro_do_periodo(data_publicacao: str) -> bool:
    if not data_publicacao:
        return False
    data = data_publicacao[:10]  # "YYYY-MM-DD" dos primeiros 10 chars do timestamp ISO
    return PERIODO_INICIO <= data <= PERIODO_FIM


def upsert_edital(cur: psycopg2.extensions.cursor, item: dict, uf: str) -> None:
    titulo = item.get("title")
    descricao = item.get("description")
    cur.execute("""
        INSERT INTO editais (
            numero_controle_pncp, uf, modalidade_licitacao_id, modalidade_licitacao_nome,
            municipio_nome, orgao_nome, orgao_cnpj, unidade_nome, titulo, descricao,
            ano, numero_sequencial, data_publicacao_pncp, data_atualizacao_pncp,
            situacao_nome, valor_global, tem_resultado, item_url, classificacao,
            dentro_periodo_alvo, json_bruto, coletado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(numero_controle_pncp) DO UPDATE SET
            data_atualizacao_pncp = excluded.data_atualizacao_pncp,
            situacao_nome = excluded.situacao_nome,
            valor_global = excluded.valor_global,
            tem_resultado = excluded.tem_resultado,
            json_bruto = excluded.json_bruto,
            coletado_em = excluded.coletado_em
    """, (
        item.get("numero_controle_pncp"), uf,
        item.get("modalidade_licitacao_id"), item.get("modalidade_licitacao_nome"),
        item.get("municipio_nome"), item.get("orgao_nome"), item.get("orgao_cnpj"),
        item.get("unidade_nome"), titulo, descricao,
        item.get("ano"), item.get("numero_sequencial"),
        item.get("data_publicacao_pncp"), item.get("data_atualizacao_pncp"),
        item.get("situacao_nome"), item.get("valor_global"), bool(item.get("tem_resultado")),
        item.get("item_url"), classificar_pneu(titulo, descricao),
        dentro_do_periodo(item.get("data_publicacao_pncp")),
        json.dumps(item, ensure_ascii=False),
        datetime.now(timezone.utc).isoformat(),
    ))


def carregar_fila(con: psycopg2.extensions.connection, cur: psycopg2.extensions.cursor, uf: str) -> tuple[int, bool]:
    cur.execute("SELECT proxima_pagina, concluida FROM filas WHERE uf=%s", (uf,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO filas (uf, proxima_pagina, concluida, atualizado_em) VALUES (%s, 1, FALSE, %s)",
            (uf, datetime.now(timezone.utc).isoformat()),
        )
        con.commit()
        return 1, False
    return row[0], bool(row[1])


def salvar_progresso_fila(con: psycopg2.extensions.connection, cur: psycopg2.extensions.cursor, uf: str,
                           proxima_pagina: int, total_esperado: int | None, concluida: bool) -> None:
    cur.execute("""
        UPDATE filas SET proxima_pagina=%s, total_esperado=COALESCE(%s, total_esperado),
                         concluida=%s, atualizado_em=%s
        WHERE uf=%s
    """, (proxima_pagina, total_esperado, concluida,
          datetime.now(timezone.utc).isoformat(), uf))
    con.commit()


# ── Guarda de disco ───────────────────────────────────────────────────────

def espaco_livre_mb() -> float:
    return shutil.disk_usage(Path(__file__).parent).free / 1_000_000


def aguardar_espaco_em_disco() -> None:
    while espaco_livre_mb() < ESPACO_MINIMO_MB:
        log.warning(
            f"Espaço livre abaixo de {ESPACO_MINIMO_MB}MB ({espaco_livre_mb():.0f}MB). "
            f"Pausando 2min — libere espaço pra coleta continuar."
        )
        time.sleep(120)


# ── Chamada à API ─────────────────────────────────────────────────────────

def buscar_pagina(uf: str, pagina: int) -> dict:
    params = {
        "q": TERMO_BUSCA,
        "pagina": pagina,
        "tam_pagina": TAM_PAGINA,
        "status": "todos",
        "ufs": uf,
        "tipos_documento": "edital",
        # sem "modalidades" de propósito — testado, omitir traz todas (ver nota no topo)
    }
    espera = PAUSA_APOS_ERRO_BASE
    for tentativa in range(1, MAX_TENTATIVAS_POR_PAGINA + 1):
        try:
            r = requests.get(BASE_URL, params=params, headers=HEADERS,
                              timeout=30, impersonate="chrome120", verify=False)
            if r.status_code == 200:
                return r.json()
            log.warning(f"{uf} pág {pagina}: HTTP {r.status_code} (tentativa {tentativa}/{MAX_TENTATIVAS_POR_PAGINA})")
        except Exception as e:
            log.warning(f"{uf} pág {pagina}: erro '{e}' (tentativa {tentativa}/{MAX_TENTATIVAS_POR_PAGINA})")
        time.sleep(espera)
        espera *= 1.6  # backoff exponencial suave
    raise RuntimeError(f"Falhou {MAX_TENTATIVAS_POR_PAGINA}x em {uf} pág {pagina} — abortando essa UF por ora, sigo pras outras.")


# ── Loop principal ────────────────────────────────────────────────────────

def coletar(ufs_alvo: list[str]) -> None:
    con, cur = conectar_db()
    log.info(
        f"Iniciando coleta — {len(ufs_alvo)} UFs, termo='{TERMO_BUSCA}', "
        f"todas modalidades, período alvo {PERIODO_INICIO} a {PERIODO_FIM} "
        f"(aplicado no cliente — API não filtra data)."
    )

    for uf in ufs_alvo:
        aguardar_espaco_em_disco()

        pagina, concluida = carregar_fila(con, cur, uf)
        if concluida:
            log.info(f"{uf}: já concluída, pulando.")
            continue

        log.info(f"{uf}: retomando da página {pagina}")
        while True:
            aguardar_espaco_em_disco()
            try:
                dados = buscar_pagina(uf, pagina)
            except RuntimeError as e:
                log.error(str(e))
                break

            itens = dados.get("items", [])
            total = dados.get("total")

            if not itens:
                log.info(f"{uf}: concluída em {total or 0} registros (página {pagina} vazia).")
                salvar_progresso_fila(con, cur, uf, pagina, total, concluida=True)
                break

            n_no_periodo = 0
            for item in itens:
                upsert_edital(cur, item, uf)
                if dentro_do_periodo(item.get("data_publicacao_pncp")):
                    n_no_periodo += 1
            con.commit()

            log.info(
                f"{uf}: página {pagina} ok ({len(itens)} itens, {n_no_periodo} no período alvo, total_uf={total})"
            )
            salvar_progresso_fila(con, cur, uf, pagina + 1, total, concluida=False)
            pagina += 1
            time.sleep(PAUSA_ENTRE_PAGINAS)

    cur.execute("SELECT COUNT(*) FROM editais")
    n_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM editais WHERE dentro_periodo_alvo=TRUE")
    n_periodo = cur.fetchone()[0]
    log.info(f"Coleta concluída. {n_total} editais únicos ({n_periodo} dentro do período {PERIODO_INICIO} a {PERIODO_FIM}) no Supabase.")
    cur.close()
    con.close()


def mostrar_status() -> None:
    con, cur = conectar_db()
    print(f"Espaço livre em disco: {espaco_livre_mb():.0f}MB\n")

    cur.execute("SELECT COUNT(*) FROM editais")
    n_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM editais WHERE dentro_periodo_alvo=TRUE")
    n_periodo = cur.fetchone()[0]
    print(f"Editais coletados: {n_total} ({n_periodo} dentro do período {PERIODO_INICIO} a {PERIODO_FIM})\n")

    print("Por classificação (dentro do período alvo):")
    cur.execute("""
        SELECT classificacao, COUNT(*) FROM editais WHERE dentro_periodo_alvo=TRUE
        GROUP BY classificacao ORDER BY 2 DESC
    """)
    for classe, n in cur.fetchall():
        print(f"  {classe:26} {n}")
    print()

    print(f"{'UF':4} {'Próx. página':13} {'Total esperado':15} {'Concluída'}")
    cur.execute("SELECT uf, proxima_pagina, total_esperado, concluida FROM filas ORDER BY uf")
    for uf, pag, total, conc in cur.fetchall():
        print(f"{uf:4} {pag:13} {str(total or '?'):15} {'sim' if conc else 'não'}")
    cur.close()
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="só mostra progresso, não coleta")
    parser.add_argument("--uf", type=str, default=None, help="roda só uma UF (teste/depuração)")
    args = parser.parse_args()

    if args.status:
        mostrar_status()
    else:
        alvo = [args.uf.upper()] if args.uf else TODAS_UFS
        coletar(alvo)
