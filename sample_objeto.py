#!/usr/bin/env python3
"""
sample_objeto.py — Amostra objetoCompra de processos de pneu no PNCP.

Uso:
  python sample_objeto.py
"""

import time
import requests

PNCP_SEARCH = "https://pncp.gov.br/api/search/"
PNCP_DETAIL = "https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer":         "https://pncp.gov.br/",
}

SAMPLE_SIZE = 30   # quantos processos buscar


def get(url, params=None):
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * attempt)
                continue
            return r
        except Exception as e:
            time.sleep(3 * attempt)
    return None


def main():
    print("Buscando processos...\n")

    items = []
    for mod in [6, 8]:
        r = get(PNCP_SEARCH, params={
            "q": "pneu", "tipos_documento": "edital",
            "status": "recebendo_proposta", "modalidades": mod,
            "pagina": 1, "tam_pagina": 20,
        })
        if r and r.status_code == 200:
            items.extend(r.json().get("items", []))

    print(f"{len(items)} processos encontrados. Buscando detalhes...\n")
    print("-" * 100)

    srp_count   = 0
    no_srp      = 0

    for i, item in enumerate(items[:SAMPLE_SIZE], 1):
        cnpj = item.get("orgao_cnpj", "")
        ano  = item.get("ano", "")
        seq  = item.get("numero_sequencial", "")
        orgao = item.get("orgao_nome", "")[:40]
        uf    = item.get("uf", "")

        r = get(PNCP_DETAIL.format(cnpj=cnpj, ano=ano, seq=seq))
        time.sleep(0.6)

        if not r or r.status_code != 200:
            print(f"[{i:02}] {orgao}/{uf} — FALHA NO DETALHE\n")
            continue

        d      = r.json()
        srp    = d.get("srp", False)
        objeto = (d.get("objetoCompra") or "").strip()

        srp_label = "[SRP]" if srp else "[nao-SRP]"
        if srp:
            srp_count += 1
        else:
            no_srp += 1

        print(f"[{i:02}] {orgao}/{uf}  [{srp_label}]")
        print(f"     {objeto[:200]}")
        print()

    print("-" * 100)
    print(f"SRP: {srp_count}  |  Não-SRP: {no_srp}  |  Total: {srp_count + no_srp}")


if __name__ == "__main__":
    main()
