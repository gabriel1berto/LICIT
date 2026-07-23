#!/usr/bin/env python3
"""
coletor_onco.py — Coleta editais de medicamentos oncológicos via API de busca do PNCP.

Espelha analise/coletor_pncp.py (mesma API, mesmo padrão de rate-limit/backoff),
mas busca por LISTA de termos (nome genérico + marca comercial) em vez de 1 termo
fixo, e grava no schema `oncologia` (isolado de `public`/`cotacao_fornecedor` —
nunca toca nas tabelas de pneu).

Vocabulário validado em sessão de estudo (double/triple-check):
  - Nome genérico completo: funciona, baixo falso-positivo.
  - Nome de marca comercial: necessário — parte real de compra judicial cita
    só a marca (Herceptin/Avastin/Glivec/Sutent), sem o genérico no texto.
  - Abreviação clínica (5-FU, MTX, VCR, CTX, VP-16, Ara-C, ADR): TESTADO E
    REJEITADO — 100% ruído (colide com código de equipamento, placa de carro,
    locação de evento, etc). Não usar.

Uso:
    python coletor_onco.py                  # roda todos os termos
    python coletor_onco.py --termo Cisplatina  # só 1 termo (teste)
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
MAX_PAGINAS_POR_TERMO = 6   # teto de segurança — alguns termos tem 800+ resultados
PAUSA_ENTRE_PAGINAS = 2.5
PAUSA_ENTRE_TERMOS = 1.5
MAX_TENTATIVAS = 4

# ── Vocabulário validado (genérico + marca, SEM abreviação) ────────────────

GENERICOS = [
    "Ciclofosfamida", "Clorambucila", "Melfalana", "Ifosfamida", "Bussulfano",
    "Temozolomida", "Dacarbazina", "Carmustina", "Lomustina",
    "Metotrexato", "Pemetrexede", "Mercaptopurina", "Fludarabina", "Cladribina",
    "Citarabina", "Fluorouracila", "Gencitabina", "Capecitabina", "Azacitidina", "Decitabina",
    "Vimblastina", "Vincristina", "Vinorelbina", "Etoposideo", "Paclitaxel",
    "Docetaxel", "Cabazitaxel", "Topotecana", "Irinotecano",
    "Doxorrubicina", "Daunorrubicina", "Epirrubicina", "Idarrubicina",
    "Mitoxantrona", "Bleomicina", "Mitomicina",
    "Cisplatina", "Carboplatina", "Oxaliplatina",
    "Imatinibe", "Dasatinibe", "Nilotinibe", "Gefitinibe", "Erlotinibe",
    "Afatinibe", "Osimertinibe", "Vemurafenibe", "Dabrafenibe", "Crizotinibe",
    "Sunitinibe", "Sorafenibe", "Pazopanibe", "Regorafenibe", "Lenvatinibe",
    "Cabozantinibe", "Ibrutinibe", "Acalabrutinibe", "Palbociclibe", "Ribociclibe",
    "Abemaciclibe",
    "Rituximabe", "Trastuzumabe", "Pertuzumabe", "Bevacizumabe", "Cetuximabe",
    "Panitumumabe", "Nivolumabe", "Pembrolizumabe", "Atezolizumabe", "Durvalumabe",
    "Ipilimumabe", "Daratumumabe", "Obinutuzumabe",
    "Abiraterona", "Bortezomibe", "Talidomida", "Tretinoina",
    "Acido zoledronico", "Trioxido de arsenio", "Hidroxiureia", "Asparaginase",
    "Venetoclaxe", "Olaparibe", "Niraparibe", "Eribulina", "Lenalidomida",
    "Tamoxifeno", "Letrozol", "Anastrozol", "Exemestano", "Leuprorrelina",
    "Goserrelina", "Denosumabe", "Enzalutamida",
    # Adicionados 23/jul/2026 (double-check falso-negativo — fármaco oncológico
    # real com volume confirmado na API do PNCP, ausente do vocabulário até então):
    "Bicalutamida", "Fulvestranto", "Everolimo", "Avelumabe", "Carfilzomibe",
    "Trametinibe", "Lapatinibe", "Apalutamida", "Ixazomibe",
]

MARCAS = [
    "Zelboraf", "Enhertu", "Keytruda", "Opdivo", "Herceptin", "Avastin",
    "Glivec", "Revlimid", "Zytiga", "Xtandi", "Ibrance", "Tagrisso",
    # "Sutent" removido 23/jul/2026 (double-check profundo): substring de
    # "SUTENTACAO"/"SUTENTAVEL" — erro de grafia comum de "sustentação"/
    # "sustentável" em português. 100% dos matches eram colisão real (palco,
    # tenda, aluguel de imóvel, secretaria de desenvolvimento sustentável),
    # zero compra real do fármaco na amostra. Genérico "Sunitinibe" já cobre
    # a droga de verdade sem esse risco.
]


def conectar_db():
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def buscar_pagina(termo: str, pagina: int) -> dict:
    params = {
        "q": termo,
        "pagina": pagina,
        "tam_pagina": TAM_PAGINA,
        "status": "todos",
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
        INSERT INTO oncologia.editais (
            numero_controle_pncp, uf, modalidade_licitacao_id, modalidade_licitacao_nome,
            municipio_nome, orgao_nome, orgao_cnpj, unidade_nome, titulo, descricao,
            ano, numero_sequencial, data_publicacao_pncp, data_atualizacao_pncp,
            situacao_nome, valor_global, tem_resultado, item_url, termo_busca, coletado_em
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (numero_controle_pncp) DO UPDATE SET
            tem_resultado = EXCLUDED.tem_resultado,
            data_atualizacao_pncp = EXCLUDED.data_atualizacao_pncp,
            situacao_nome = EXCLUDED.situacao_nome
    """, (
        item.get("numero_controle_pncp"), item.get("uf"),
        item.get("modalidade_licitacao_id"), item.get("modalidade_licitacao_nome"),
        item.get("municipio_nome"), item.get("orgao_nome"), item.get("orgao_cnpj"),
        item.get("unidade_nome"), item.get("title"), item.get("description"),
        item.get("ano"), item.get("numero_sequencial"),
        item.get("data_publicacao_pncp"), item.get("data_atualizacao_pncp"),
        item.get("situacao_nome"), item.get("valor_global"), item.get("tem_resultado"),
        item.get("item_url"), termo, datetime.now(timezone.utc).isoformat(),
    ))


def coletar_termo(cur, termo: str, tipo: str) -> int:
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
        INSERT INTO oncologia.vocabulario_termos (termo, tipo, total_ultima_busca, ultima_busca_em)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (termo) DO UPDATE SET total_ultima_busca = EXCLUDED.total_ultima_busca,
                                           ultima_busca_em = now()
    """, (termo, tipo, total_api))
    print(f"'{termo}' ({tipo}): total_api={total_api}, gravados_nesta_rodada={total_gravado}", flush=True)
    return total_gravado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termo", help="rodar só 1 termo (teste)")
    args = ap.parse_args()

    con, cur = conectar_db()

    if args.termo:
        tipo = "marca" if args.termo in MARCAS else "generico"
        coletar_termo(cur, args.termo, tipo)
        con.commit()
        con.close()
        return

    total_geral = 0
    todos = [(t, "generico") for t in GENERICOS] + [(t, "marca") for t in MARCAS]
    for termo, tipo in todos:
        # reconecta se o Supabase derrubou a conexao (pooler fecha conexao
        # ociosa/antiga) - achado real 22/jul: script morria depois de ~15min
        # com psycopg2.OperationalError, sem isso a coleta inteira parava.
        try:
            total_geral += coletar_termo(cur, termo, tipo)
            con.commit()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"  conexao caiu ({e}); reconectando e tentando '{termo}' de novo...", file=sys.stderr)
            try:
                con.close()
            except Exception:
                pass
            time.sleep(3)
            con, cur = conectar_db()
            total_geral += coletar_termo(cur, termo, tipo)
            con.commit()
        time.sleep(PAUSA_ENTRE_TERMOS)

    print(f"\nTOTAL gravado nesta rodada: {total_geral}")
    con.close()


if __name__ == "__main__":
    main()
