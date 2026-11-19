#!/usr/bin/env python3
"""casar.py — Para cada item da planilha de cotação, acha nos catálogos (GET, TS Shara,
Mazer) o produto que melhor atende os critérios técnicos e escreve uma aba por fornecedor
("Cotação - GET", "Cotação - TS Shara", "Cotação - Mazer") na planilha do Google Sheets.

Escolha por item, por fornecedor:
  1. só produtos da mesma categoria do item;
  2. melhor = menos critérios FALHA, depois mais OK, depois menos "?" (a confirmar);
  3. status: ✅ atende (0 falha, 0 dúvida) · ⚠️ confirmar (0 falha, alguma dúvida) ·
     ❌ nenhum produto atende (melhor candidato ainda falha) · — fornecedor não tem a linha ·
     ⛔ fora de escopo (item não é produto de informática).
Critério com dúvida NUNCA vira "atende" — o vendedor confirma (CLAUDE.md §6.1).

Uso: python casar.py <spreadsheet_id> [--dry-run]
"""
import argparse
import re
import json
import os
import re
import sys

import gspread

from comum import carregar
from criterios import comparar, fora_de_escopo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORNECEDORES = [("GET", "get"), ("TS Shara", "tsshara"), ("Mazer", "mazer")]
ABA_BASE = "Cotação"


def ler_itens(ws) -> list[dict]:
    linhas = ws.get_all_values()
    cab = linhas[9]  # linha 10 = cabeçalho das colunas
    idx = {n: i for i, n in enumerate(cab)}
    out = []
    for r in linhas[10:]:
        if not r or not r[0]:
            continue
        g = lambda nome: r[idx[nome]] if nome in idx and idx[nome] < len(r) else ""
        out.append({"ref": g("Ref. edital (órgão — nº/ano)"), "encerra": g("Encerramento do edital"),
                    "item": g("Item nº"), "link_pncp": g("Link PNCP"), "categoria": g("Produto"),
                    "desc": g("Especificação técnica (descrição do item no PNCP)"), "qtde": g("Qtde"),
                    "unid": g("Unid."), "ref_preco": g("Preço referência do edital (R$/un)"),
                    "cep": g("CEP de entrega")})
    return out


# Produto da categoria que não serve pro uso de licitação comum (achado 19/nov/2026: "MINI NO
# BREAK UPS P/ROTEADOR 12V" é fonte DC de roteador, não nobreak de computador — ganhava porque
# a ficha não tem VA, o que virava só "?" em vez de falha).
NAO_SERVE = re.compile(r"roteador|modulo de potencia|bateria externa|mini no ?break|s/m s/ssd|barebone", re.I)


def categoria_efetiva(item: dict) -> str:
    """Corrige categoria do radar quando o item é outra coisa (ex: 'Conjunto Atualização
    Microcomputador ... componentes: teclado e mouse sem fio' é kit teclado+mouse, não PC)."""
    d = item["desc"].lower()
    if item["categoria"] == "Computador" and re.search(r"componentes: teclado e mouse", d):
        return "Teclado/Mouse"
    if item["categoria"] == "Estabilizador" and re.search(r"tipo: ?no-?break|autonomia bateria", d):
        return "Nobreak"
    return item["categoria"]


def melhor(item: dict, catalogo: list[dict]):
    cat = categoria_efetiva(item)
    cands = [p for p in catalogo if p["categoria"] == cat and not NAO_SERVE.search(p["nome"])]
    if not cands:
        return None, []
    gamer_ok = "gamer" in item["desc"].lower()
    av = []
    for p in cands:
        c = comparar(cat, item["desc"], p)
        penal = 0 if gamer_ok or "gamer" not in p["nome"].lower() else 1
        # ordem: menos falhas, menos dúvidas (conservador: produto com ficha completa ganha
        # de produto sem dado), mais OK, sem linha gamer, mais perto do mínimo pedido
        av.append((c.n_falha, -c.n_ok, c.n_duv, p, c, (c.n_falha, c.n_duv, -c.n_ok, penal, c.excesso)))
    av.sort(key=lambda x: x[5])
    return av[0][:5], [a[:5] for a in av[1:3]]


def linha_aba(item, fornecedor, escolha, alternativas):
    base = [item["ref"], item["encerra"], item["item"], item["categoria"], item["qtde"], item["desc"][:400]]
    motivo_fora = fora_de_escopo(item["desc"])
    if motivo_fora:
        return base + ["⛔ Fora de escopo", "", "", "", "", "", motivo_fora, "", item["link_pncp"]]
    if escolha is None:
        return base + [f"— {fornecedor} não tem essa linha", "", "", "", "", "", "", "", item["link_pncp"]]
    nf, _, nd, p, c = escolha
    status = "✅ Atende" if nf == 0 and nd == 0 else ("⚠️ Confirmar com vendedor" if nf == 0 else "❌ Nenhum produto atende")
    if not c.res:
        status = "⚠️ Confirmar com vendedor"
    oks = "; ".join(f"{k}: {d}" for s, k, d in c.res if s == "OK")
    duv = "; ".join(f"{k}: {d}" for s, k, d in c.res if s == "?")
    fal = "; ".join(f"{k}: {d}" for s, k, d in c.res if s == "FALHA")
    alt = " | ".join(f"{a[3]['nome']} ({a[0]} falha) {a[3]['link']}" for a in alternativas if a[0] <= nf)
    return base + [status, p["nome"], p.get("pn") or p["sku"], p["link"], oks, duv, fal, alt, item["link_pncp"]]


CAB = ["Ref. edital", "Encerramento", "Item nº", "Produto", "Qtde", "Especificação do item (edital)",
       "Resultado", "Produto sugerido", "Código / PN", "Link do produto", "Critérios atendidos",
       "A confirmar com vendedor", "Critérios que NÃO atende", "Alternativas", "Link PNCP"]


def escrever_aba(sh, nome, linhas):
    try:
        ws = sh.worksheet(nome)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(nome, rows=len(linhas) + 5, cols=len(CAB))
    ws.resize(rows=len(linhas) + 5, cols=len(CAB))
    ws.update(range_name="A1", values=[CAB] + linhas, value_input_option="RAW")
    sid = ws.id
    larg = [220, 90, 50, 100, 50, 380, 170, 280, 110, 200, 330, 330, 330, 260, 200]
    reqs = [{"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1}},
                                       "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": .85, "green": .94, "blue": .85}, "wrapStrategy": "WRAP"}},
                            "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy)"}},
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": len(linhas) + 1},
                            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                            "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
            {"setBasicFilter": {"filter": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": len(linhas) + 1, "startColumnIndex": 0, "endColumnIndex": len(CAB)}}}}]
    for i, w in enumerate(larg):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                   "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    for txt, cor in (("✅", {"red": .80, "green": .94, "blue": .80}), ("⚠️", {"red": 1, "green": .95, "blue": .75}),
                     ("❌", {"red": .98, "green": .80, "blue": .80})):
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": len(linhas) + 1, "startColumnIndex": 6, "endColumnIndex": 7}],
            "booleanRule": {"condition": {"type": "TEXT_STARTS_WITH", "values": [{"userEnteredValue": txt}]},
                            "format": {"backgroundColor": cor, "textFormat": {"bold": True}}}}}})
    sh.batch_update({"requests": reqs})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spreadsheet_id")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    gc = gspread.oauth(credentials_filename=os.path.join(REPO, "credentials.json"),
                       authorized_user_filename=os.path.join(REPO, "token.json"))
    sh = gc.open_by_key(a.spreadsheet_id)
    itens = ler_itens(sh.worksheet(ABA_BASE))
    print(f"{len(itens)} itens na aba '{ABA_BASE}'")
    resumo = {}
    for nome, arq in FORNECEDORES:
        cat = carregar(arq)
        linhas = []
        for it in itens:
            esc, alts = (None, []) if fora_de_escopo(it["desc"]) else melhor(it, cat)
            linhas.append(linha_aba(it, nome, esc, alts))
        cont = {}
        for l in linhas:
            k = l[6].split(" ")[0]
            cont[k] = cont.get(k, 0) + 1
        resumo[nome] = cont
        print(nome, cont)
        if not a.dry_run:
            escrever_aba(sh, f"Cotação - {nome}", linhas)
        json.dump(linhas, open(os.path.join(os.path.dirname(__file__), "dados", f"casamento_{arq}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
