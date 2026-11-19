#!/usr/bin/env python3
"""
coletor_informatica.py — Coleta editais ABERTOS e FUTUROS de informática (periféricos
foco GET) via API de busca do PNCP, mais os itens de cada edital.

Espelha coletor_pecas.py (mesma API de busca, mesmo rate-limit/backoff, lista de
termos), grava em schema `informatica` (isolado — ver schema_informatica.sql).
Diferença deliberada vs peças: coleta também os ITENS (endpoint pncp/v1 .../itens),
porque a pergunta do radar é "a GET cobre esse edital inteiro?" — só dá pra
responder item a item (filtro_informatica.py). Categoria/cobertura são calculadas na
leitura, não gravadas.

Abertos e futuros: busca com status=recebendo_proposta (inclui edital publicado com
abertura de proposta ainda no futuro — data_inicio_vigencia > agora).

Etapas:
  1. Busca por termo → upsert em informatica.editais (termos acumulam).
  2. Itens só dos editais ainda sem itens, não-Leilão, com prazo no futuro.

Coleta diária: .github/workflows/informatica_coletor.yml.

Uso:
    python coletor_informatica.py                  # busca + itens
    python coletor_informatica.py --termo Nobreak  # só 1 termo (teste)
    python coletor_informatica.py --so-itens        # pula a busca
    python coletor_informatica.py --max-itens 200   # teto de editais na etapa 2
    python coletor_informatica.py --so-itens --ufs CE,PE,BA  # prioriza UFs nos itens
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://pncp.gov.br/api/search/"
ITENS_URL = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/",
}

TAM_PAGINA = 50
STATUS_BUSCA = "recebendo_proposta"
# "Monitor" tinha 1.846 abertos no país em 19/nov/2026 (37 páginas) — teto com folga.
MAX_PAGINAS_POR_TERMO = 60
TAM_PAGINA_ITENS = 500
PAUSA_ENTRE_PAGINAS = 2.5
PAUSA_ENTRE_TERMOS = 1.5
PAUSA_ENTRE_ITENS = 1.2
MAX_TENTATIVAS = 4

# Linhas do catálogo GET (19/nov/2026) + termos amplos que trazem kit de periférico.
TERMOS = [
    "Nobreak",
    "No-break",
    "Estabilizador",
    "Monitor",
    "Teclado",
    "Mouse",
    "Headset",
    "Webcam",
    "Projetor",
    "SSD",
    "Computador",
    "Equipamentos de informática",
    "Material de informática",
    "Periféricos de informática",
]


def conectar_db():
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def _get_json(url: str, params: dict, rotulo: str):
    espera = 8.0
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS,
                             timeout=30, impersonate="chrome120", verify=False)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (204, 404):
                return None
            print(f"  [{rotulo}] HTTP {r.status_code} (tentativa {tentativa})", file=sys.stderr)
        except Exception as e:
            print(f"  [{rotulo}] erro '{e}' (tentativa {tentativa})", file=sys.stderr)
        time.sleep(espera)
        espera *= 1.6
    return None


def buscar_termo(termo: str) -> tuple[list[dict], int]:
    achados, total_api = [], 0
    for pagina in range(1, MAX_PAGINAS_POR_TERMO + 1):
        data = _get_json(BASE_URL, {
            "q": termo, "pagina": pagina, "tam_pagina": TAM_PAGINA,
            "status": STATUS_BUSCA, "tipos_documento": "edital",
        }, f"{termo} pág {pagina}") or {}
        total_api = data.get("total", total_api) or 0
        itens = data.get("items", [])
        if not itens:
            break
        achados.extend(it for it in itens if it.get("numero_controle_pncp"))
        if pagina * TAM_PAGINA >= total_api:
            break
        time.sleep(PAUSA_ENTRE_PAGINAS)
    return achados, total_api


def _int_ou_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def upsert_edital(cur, item: dict, termo: str) -> None:
    cur.execute("""
        INSERT INTO informatica.editais (
            numero_controle_pncp, uf, codigo_ibge, municipio_nome, orgao_nome, orgao_cnpj,
            unidade_nome, modalidade_licitacao_nome, titulo, descricao, ano, numero_sequencial,
            srp, link_sistema_origem, data_publicacao_pncp, data_inicio_vigencia,
            data_fim_vigencia, situacao_nome, cancelado, valor_total_estimado, termos, coletado_em
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,ARRAY[%s],%s)
        ON CONFLICT (numero_controle_pncp) DO UPDATE SET
            data_inicio_vigencia = EXCLUDED.data_inicio_vigencia,
            data_fim_vigencia = EXCLUDED.data_fim_vigencia,
            situacao_nome = EXCLUDED.situacao_nome,
            cancelado = EXCLUDED.cancelado,
            valor_total_estimado = EXCLUDED.valor_total_estimado,
            link_sistema_origem = EXCLUDED.link_sistema_origem,
            termos = ARRAY(SELECT DISTINCT unnest(informatica.editais.termos || EXCLUDED.termos)),
            coletado_em = EXCLUDED.coletado_em
    """, (
        item.get("numero_controle_pncp"), item.get("uf"), _int_ou_none(item.get("codigo_ibge")),
        item.get("municipio_nome"), item.get("orgao_nome"), item.get("orgao_cnpj"),
        item.get("unidade_nome"), item.get("modalidade_licitacao_nome"),
        item.get("title"), item.get("description"),
        str(item.get("ano") or ""), str(item.get("numero_sequencial") or ""),
        item.get("srp"), item.get("link_sistema_origem") or None,
        item.get("data_publicacao_pncp"), item.get("data_inicio_vigencia"),
        item.get("data_fim_vigencia"), item.get("situacao_nome"), item.get("cancelado"),
        # valor_global vem nulo no search API pra edital (achado 05/out/2026, coletor_pecas.py)
        item.get("valor_total_estimado") or item.get("valor_global"),
        termo, datetime.now(timezone.utc).isoformat(),
    ))


def coletar_busca(con, cur, termos: list[str]) -> None:
    for termo in termos:
        achados, total_api = buscar_termo(termo)
        for it in achados:
            upsert_edital(cur, it, termo)
        cur.execute("""
            INSERT INTO informatica.vocabulario_termos (termo, total_ultima_busca, ultima_busca_em)
            VALUES (%s, %s, now())
            ON CONFLICT (termo) DO UPDATE SET total_ultima_busca = EXCLUDED.total_ultima_busca,
                                               ultima_busca_em = now()
        """, (termo, total_api))
        con.commit()
        print(f"'{termo}': total_api={total_api}, gravados={len(achados)}", flush=True)
        time.sleep(PAUSA_ENTRE_TERMOS)


def buscar_itens(cnpj: str, ano: str, seq: str) -> list[dict] | None:
    todos, pagina = [], 1
    while True:
        data = _get_json(ITENS_URL.format(cnpj=cnpj, ano=ano, seq=seq),
                         {"pagina": pagina, "tamanhoPagina": TAM_PAGINA_ITENS},
                         f"itens {cnpj}/{ano}/{seq}")
        if data is None:
            return todos if pagina > 1 else None
        todos.extend(data)
        if len(data) < TAM_PAGINA_ITENS:
            return todos
        pagina += 1
        time.sleep(PAUSA_ENTRE_ITENS)


def coletar_itens(con, cur, max_editais: int | None, ufs: list[str] | None = None) -> None:
    cur.execute("""
        SELECT numero_controle_pncp, orgao_cnpj, ano, numero_sequencial
        FROM informatica.editais
        WHERE itens_coletados_em IS NULL
          AND COALESCE(cancelado, FALSE) = FALSE
          AND COALESCE(modalidade_licitacao_nome, '') NOT ILIKE 'Leil%%'
          AND data_fim_vigencia > to_char(now() AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD"T"HH24:MI')
          AND (%(ufs)s IS NULL OR uf = ANY(%(ufs)s))
        ORDER BY data_fim_vigencia
    """ + (f" LIMIT {int(max_editais)}" if max_editais else ""), {"ufs": ufs})
    pendentes = cur.fetchall()
    print(f"Itens: {len(pendentes)} edital(is) pendente(s)", flush=True)
    for i, (ncp, cnpj, ano, seq) in enumerate(pendentes, 1):
        itens = buscar_itens(cnpj, ano, seq)
        if itens is None:
            print(f"  {i}/{len(pendentes)} {ncp}: sem resposta, tenta na próxima rodada", flush=True)
            time.sleep(PAUSA_ENTRE_ITENS)
            continue
        for x in itens:
            cur.execute("""
                INSERT INTO informatica.itens (
                    numero_controle_pncp, numero_item, descricao, quantidade, unidade_medida,
                    valor_unitario_estimado, valor_total, material_ou_servico, beneficio_nome,
                    orcamento_sigiloso
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (numero_controle_pncp, numero_item) DO NOTHING
            """, (
                ncp, x.get("numeroItem"), x.get("descricao"), x.get("quantidade"),
                x.get("unidadeMedida"), x.get("valorUnitarioEstimado"), x.get("valorTotal"),
                x.get("materialOuServicoNome"), x.get("tipoBeneficioNome"), x.get("orcamentoSigiloso"),
            ))
        cur.execute("UPDATE informatica.editais SET itens_coletados_em = now() WHERE numero_controle_pncp = %s",
                    (ncp,))
        con.commit()
        if i % 25 == 0 or i == len(pendentes):
            print(f"  {i}/{len(pendentes)} editais com itens", flush=True)
        time.sleep(PAUSA_ENTRE_ITENS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termo", help="rodar só 1 termo (teste)")
    ap.add_argument("--so-itens", action="store_true", help="pula a busca, só coleta itens pendentes")
    ap.add_argument("--max-itens", type=int, help="teto de editais na etapa de itens")
    ap.add_argument("--ufs", help="só itens dessas UFs, ex: CE,PE,BA (prioriza uma região na carga)")
    args = ap.parse_args()

    con, cur = conectar_db()
    if not args.so_itens:
        coletar_busca(con, cur, [args.termo] if args.termo else TERMOS)
    try:
        ufs = [u.strip().upper() for u in args.ufs.split(",")] if args.ufs else None
        coletar_itens(con, cur, args.max_itens, ufs)
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        # conexão longa com o Supabase cai às vezes — o que já foi gravado fica (commit
        # por edital), o resto entra na próxima rodada.
        print(f"conexão caiu na etapa de itens ({e}); resto fica pra próxima rodada", file=sys.stderr)
    con.close()


if __name__ == "__main__":
    main()
