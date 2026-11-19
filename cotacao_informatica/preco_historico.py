#!/usr/bin/env python3
"""preco_historico.py — Preço que o setor público pagou nos últimos 12 meses por cada item da
aba "Cotação", via código CATMAT.

1. Código CATMAT do item: PNCP `.../compras/{ano}/{seq}/itens` (campo `catalogoCodigoItem`).
2. Preços homologados do mesmo código: API de dados abertos do Compras.gov.br,
   `modulo-pesquisa-preco/1_consultarMaterial` (tipo=codigoItemCatalogo) — a mesma base do
   Painel de Preços que os órgãos usam pra montar o preço de referência. Traz preço unitário,
   marca, fornecedor e data de cada compra.
3. Estatística robusta: mediana e quartis (P25–P75), com corte de outlier por IQR — mesmo
   código CATMAT junta compra de 1 unidade e de lote, e a dispersão é grande (ex: projetor
   469920 de R$1.107 a R$3.465 no mesmo mês). Média simples enganaria.

Escreve 4 colunas na aba "Cotação", logo após "Preço referência do edital (R$/un)".

Uso: python preco_historico.py <spreadsheet_id> [--meses 12]
"""
import argparse
import collections
import os
import statistics
import sys
import time
from datetime import date, timedelta

import gspread
import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://dadosabertos.compras.gov.br/modulo-pesquisa-preco/1_consultarMaterial"
PNCP_ITENS = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
COLS = ["Preço pago no setor público — mediana 12m (R$/un)", "Faixa típica P25–P75 (R$/un)",
        "Nº de compras (12m)", "Marcas que mais venderam (12m)"]


def catmat_por_item(url_pncp: str, cache: dict) -> dict:
    cnpj, ano, seq = url_pncp.rstrip("/").split("/")[-3:]
    chave = (cnpj, ano, seq)
    if chave not in cache:
        out, pag = {}, 1
        while True:
            r = requests.get(PNCP_ITENS.format(cnpj=cnpj, ano=ano, seq=seq),
                             params={"pagina": pag, "tamanhoPagina": 500}, timeout=60)
            lote = r.json() if r.status_code == 200 else []
            for x in lote:
                out[str(x["numeroItem"])] = x.get("catalogoCodigoItem")
            if len(lote) < 500:
                break
            pag += 1
        cache[chave] = out
        time.sleep(0.8)
    return cache[chave]


def precos(codigo: str, inicio: str, fim: str) -> list[dict]:
    regs, pag = [], 1
    while pag <= 10:
        for tentativa in range(3):
            try:
                r = requests.get(API, params={"pagina": pag, "tamanhoPagina": 500, "tipo": "codigoItemCatalogo",
                                              "codigo": codigo, "dataCompraInicio": inicio, "dataCompraFim": fim},
                                 timeout=120)
                break
            except Exception as e:
                print(f"  erro {e}, tentando de novo", file=sys.stderr)
                time.sleep(5)
        else:
            return regs
        if r.status_code != 200:
            return regs
        j = r.json()
        regs += j.get("resultado", [])
        if not j.get("paginasRestantes"):
            break
        pag += 1
        time.sleep(1)
    return regs


def estatistica(regs: list[dict]):
    vals = sorted(float(x["precoUnitario"]) for x in regs if x.get("precoUnitario"))
    if len(vals) < 3:
        return None
    q1, _, q3 = statistics.quantiles(vals, n=4)
    iqr = q3 - q1
    limpos = [v for v in vals if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr] or vals
    p25, med, p75 = statistics.quantiles(limpos, n=4) if len(limpos) >= 3 else (limpos[0], statistics.median(limpos), limpos[-1])
    marcas = collections.Counter((x.get("marca") or "").strip().upper() for x in regs if (x.get("marca") or "").strip())
    top = ", ".join(f"{m} ({n})" for m, n in marcas.most_common(4))
    return round(med, 2), f"R$ {p25:,.0f} – {p75:,.0f}".replace(",", "."), len(vals), top


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spreadsheet_id")
    ap.add_argument("--meses", type=int, default=12)
    a = ap.parse_args()
    fim = date.today()
    inicio = fim - timedelta(days=30 * a.meses)
    gc = gspread.oauth(credentials_filename=os.path.join(REPO, "credentials.json"),
                       authorized_user_filename=os.path.join(REPO, "token.json"))
    sh = gc.open_by_key(a.spreadsheet_id)
    ws = sh.worksheet("Cotação")
    linhas = ws.get_all_values()
    cab = linhas[9]
    i_url, i_item, i_ref = cab.index("Link PNCP"), cab.index("Item nº"), cab.index("Preço referência do edital (R$/un)")

    cache_itens, cache_precos, saida = {}, {}, []
    for n, r in enumerate(linhas[10:], 1):
        if not r or not r[0]:
            continue
        cod = catmat_por_item(r[i_url], cache_itens).get(r[i_item])
        if not cod:
            saida.append(["sem código CATMAT no PNCP", "", "", ""])
            continue
        if cod not in cache_precos:
            cache_precos[cod] = estatistica(precos(str(cod), inicio.isoformat(), fim.isoformat()))
        est = cache_precos[cod]
        saida.append(list(est) if est else [f"menos de 3 compras (CATMAT {cod})", "", "", ""])
        print(f"{n}/{len(linhas) - 10} CATMAT {cod}: {saida[-1][:3]}", flush=True)

    # insere 4 colunas depois de "Preço referência do edital"
    col = i_ref + 1
    if cab[col] != COLS[0]:
        sh.batch_update({"requests": [{"insertDimension": {"range": {"sheetId": ws.id, "dimension": "COLUMNS",
                                                                     "startIndex": col, "endIndex": col + 4},
                                                           "inheritFromBefore": True}}]})
    ws.update(range_name=gspread.utils.rowcol_to_a1(10, col + 1), values=[COLS] + saida, value_input_option="RAW")
    sid = ws.id
    sh.batch_update({"requests": [
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 10 + len(saida), "startColumnIndex": col, "endColumnIndex": col + 1},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "\"R$\" #,##0.00"}, "textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat(numberFormat,textFormat)"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 10 + len(saida), "startColumnIndex": col + 1, "endColumnIndex": col + 4},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": False}, "numberFormat": {"type": "TEXT"}}},
                        "fields": "userEnteredFormat(textFormat,numberFormat)"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": col, "endColumnIndex": col + 4},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": .82, "green": .89, "blue": .98}, "textFormat": {"bold": True}, "wrapStrategy": "WRAP"}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,wrapStrategy)"}},
    ] + [{"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": col + k, "endIndex": col + k + 1},
                                        "properties": {"pixelSize": w}, "fields": "pixelSize"}} for k, w in enumerate([130, 130, 80, 220])]})
    print(f"ok: {len(saida)} linhas, {sum(1 for s in saida if isinstance(s[0], float))} com preço histórico")


if __name__ == "__main__":
    main()
