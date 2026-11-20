#!/usr/bin/env python3
"""prazos_pagamento.py — Prazo de entrega, recebimento definitivo, prazo de pagamento e DATA
ESTIMADA de pagamento de cada edital da aba "Cotação", lidos dos documentos do edital no PNCP.

Documentos: mesma extração do analisa_edital.py (`baixar_documentos`, pdf/docx/zip, trava de
extração insuficiente). Nunca inventa prazo: se o edital não diz, usa premissa e escreve
"(premissa)" na célula.

data estimada = encerramento
              + 5 dias úteis (adjudicação/homologação + nota de empenho — premissa)
              + prazo de entrega do edital (cheio — conservador; entregar antes antecipa)
              + recebimento definitivo do edital (premissa 10 dias úteis)
              + prazo de pagamento do edital (premissa 30 dias corridos, teto usual Lei 14.133)
Dias úteis sem feriado (aproximação).

Uso: python prazos_pagamento.py <spreadsheet_id>
"""
import os
import re
import sys
import time

import gspread
import pandas as pd
from pandas.tseries.offsets import BDay

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import analisa_edital as A  # noqa: E402

F = re.I
N = r"(\d{1,3}) ?(?:\([^)]{2,25}\))? ?dias( [úu]teis| corridos)?"
RX_ENTREGA = [rf"prazo (?:m[áa]ximo )?(?:de |para (?:a )?)?entrega[^.]{{0,120}}?{N}",
              rf"(?:entregues?|entrega)[^.]{{0,80}}?no prazo (?:m[áa]ximo )?de (?:at[ée] )?{N}",
              rf"(?:entregues?|entrega)[^.]{{0,60}}?em at[ée] {N}"]
RX_RECEB = rf"definitiv\w*[^.]{{0,140}}?{N}"
RX_PAG = [rf"pagamento ser[áa] (?:efetuado|realizado|feito)[^.]{{0,80}}?(?:at[ée]|em|no prazo (?:m[áa]ximo )?de(?: at[ée])?) ?{N}",
          rf"prazo (?:m[áa]ximo )?(?:de|para) (?:o )?pagamento[^.]{{0,40}}?{N}",
          r"pagamento[^.]{0,120}?(\d{1,2})[ºo°] dia( [úu]til)",
          rf"pagamento[^.]{{0,120}}?{N}"]
COLS = ["Prazo de entrega exigido (edital)", "Recebimento definitivo (edital)", "Data estimada de pagamento"]


def achar(t, padroes):
    for p in padroes if isinstance(padroes, list) else [padroes]:
        m = re.search(p, t, F)
        if m:
            tipo = (m.group(2) or " corridos").strip()
            return int(m.group(1)), "úteis" if tipo.startswith(("ú", "u", " ú")) or "til" in tipo else "corridos"
    return None


def somar(d, n, tipo):
    return d + BDay(n) if tipo == "úteis" else d + pd.Timedelta(days=n)


def prazos_do_edital(url):
    cnpj, ano, seq = url.rstrip("/").split("/")[-3:]
    _, _, por_arq = A.baixar_documentos(cnpj, int(ano), int(seq))
    t = re.sub(r"\s+", " ", re.sub(r"\(cid:\d+\)", "ti", " ".join(x for _, x in por_arq)))
    return achar(t, RX_ENTREGA), achar(t, RX_RECEB), achar(t, RX_PAG)


def main():
    sheet = sys.argv[1]
    gc = gspread.oauth(credentials_filename=os.path.join(REPO, "credentials.json"),
                       authorized_user_filename=os.path.join(REPO, "token.json"))
    sh = gc.open_by_key(sheet)
    ws = sh.worksheet("Cotação")
    v = ws.get_all_values()
    cab = v[9]
    iU, iE = cab.index("Link PNCP"), cab.index("Encerramento do edital")
    iP = cab.index("Prazo previsto p/ pagamento (após NF/liquidação)")
    cache, saida = {}, []
    for r in v[10:]:
        if not r or not r[0]:
            continue
        if r[iU] not in cache:
            try:
                cache[r[iU]] = prazos_do_edital(r[iU])
            except A.ExtracaoInsuficiente:
                cache[r[iU]] = (None, None, None)
            time.sleep(0.8)
        ent, rec, pag = cache[r[iU]]
        prem = []
        d = pd.to_datetime(r[iE], dayfirst=True) + BDay(5)
        d = somar(d, *(ent or (30, "corridos")))
        prem += [] if ent else ["entrega 30d"]
        d = somar(d, *(rec or (10, "úteis")))
        prem += [] if rec else ["recebimento 10 dias úteis"]
        d = somar(d, *(pag or (30, "corridos")))
        prem += [] if pag else ["pagamento 30d"]
        saida.append([f"{ent[0]} dias {ent[1]}" if ent else "não achado no edital",
                      f"{rec[0]} dias {rec[1]}" if rec else "não achado (premissa 10 dias úteis)",
                      d.strftime("%d/%m/%Y") + (f" — premissa: {', '.join(prem)}" if prem else "")])
    col = iP + 1
    if cab[col] != COLS[0]:
        sh.batch_update({"requests": [{"insertDimension": {"range": {"sheetId": ws.id, "dimension": "COLUMNS",
                                                                     "startIndex": col, "endIndex": col + 3}, "inheritFromBefore": True}}]})
    ws.update(range_name=gspread.utils.rowcol_to_a1(10, col + 1), values=[COLS] + saida, value_input_option="RAW")
    print(f"ok: {len(saida)} linhas, {sum('premissa' in s[2] for s in saida)} com premissa")


if __name__ == "__main__":
    main()
