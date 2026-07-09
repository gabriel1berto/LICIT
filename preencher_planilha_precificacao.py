#!/usr/bin/env python3
"""
preencher_planilha_precificacao.py — Preenche cópia da planilha modelo de
precificação com os resultados dos 4 scrapers (Bransales/Cantu/GP/Green).

A planilha modelo (sempre duplicada antes, nunca editada direto — ver
https://drive.google.com/drive/folders/1Nf10IsY2Gzpf_1WXWuKBC0B58vAbnuXX)
tem 4 blocos empilhados, um por distribuidor. As colunas L-V (Investimento,
Frete, Imposto, Preço de venda, Expectativa de pagamento) são FÓRMULA — só
escrevemos nas colunas de entrada (A-J). Nunca sobrescrever L-V.

Uso:
  python preencher_planilha_precificacao.py <spreadsheet_id> <analise.json> \
      --bransales results_X_bransales.json --cantu results_X_cantu.json \
      --gp results_X_gp.json --green results_X_green.json

Setup: ver credentials.json/token.json (mesmo OAuth do precificacao_gsheets.py).
"""

import argparse, json, os, sys
import gspread

SHEET_NAME = "Página1"

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token.json")

# Linha inicial do item 1 de cada bloco (12 linhas de item por bloco).
BLOCO_ITEM1_ROW = {
    "Bransales":   5,
    "Cantu":       20,
    "GP":          35,
    "Green Pneus": 50,
}
ITENS_POR_BLOCO = 12


def carregar_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def linha_para_item(resultado_item: dict | None, distribuidor: str) -> dict:
    """Monta os valores de A-J pra 1 item, dado o resultado do scraper (ou None se sem estoque).
    'Produto' = medida pedida no edital (vem de fora). 'Marca' = nome do produto achado
    (segue o padrao da planilha original: essa coluna guarda o nome completo, tipo
    'Bransales B Van', nao so a marca pura)."""
    if resultado_item is None or not resultado_item.get("apto"):
        obs_sem_estoque = (resultado_item or {}).get("obs") or f"Nenhum produto disponível na {distribuidor}"
        return {
            "criterio": "— Sem estoque",
            "marca": "",
            "link": "",
            "obs": obs_sem_estoque,
            "preco_un": "",
        }
    return {
        "criterio": "⚠️ Parcial",
        "marca": resultado_item.get("nome", ""),
        "link": resultado_item.get("url", ""),
        "obs": resultado_item.get("obs", ""),
        "preco_un": resultado_item.get("preco_un", ""),
    }


def preencher_bloco(ws, distribuidor: str, itens_edital: list, resultados: list[dict] | None):
    row1 = BLOCO_ITEM1_ROW[distribuidor]
    por_item = {r["item"]: r for r in (resultados or [])}

    updates = []
    for i in range(ITENS_POR_BLOCO):
        row = row1 + i
        item_num = i + 1
        edital_item = next((it for it in itens_edital if it["numero"] == item_num), None)

        if edital_item is None:
            # item não existe nesse edital (bloco tem 12 linhas fixas, edital pode ter menos) — limpa
            updates.append({"range": f"A{row}:J{row}", "values": [[""] * 10]})
            continue

        resultado_item = por_item.get(item_num)
        dados = linha_para_item(resultado_item, distribuidor)
        preco_leilao = edital_item.get("valor_unit", "")
        if isinstance(preco_leilao, str):
            preco_leilao = preco_leilao.replace("R$", "").strip().replace(".", "").replace(",", ".")
            try:
                preco_leilao = float(preco_leilao)
            except ValueError:
                preco_leilao = ""

        valores = [
            item_num,
            edital_item.get("medida", ""),
            dados["criterio"],
            distribuidor,
            dados["marca"],
            dados["link"],
            dados["obs"],
            dados["preco_un"],
            preco_leilao,
            edital_item.get("qtde", ""),
        ]
        updates.append({"range": f"A{row}:J{row}", "values": [valores]})

    ws.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"  [{distribuidor}] {len(itens_edital)} item(ns) do edital escrito(s)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spreadsheet_id")
    parser.add_argument("analise_json", help="JSON salvo por analisa_edital.py (tem os itens do edital)")
    parser.add_argument("--bransales")
    parser.add_argument("--cantu")
    parser.add_argument("--gp")
    parser.add_argument("--green")
    args = parser.parse_args()

    analise = carregar_json(args.analise_json)
    itens_edital = analise["itens"]

    gc = gspread.oauth(credentials_filename=CREDENTIALS_FILE, authorized_user_filename=TOKEN_FILE)
    sh = gc.open_by_key(args.spreadsheet_id)
    ws = sh.worksheet(SHEET_NAME)

    fontes = {
        "Bransales":   args.bransales,
        "Cantu":       args.cantu,
        "GP":          args.gp,
        "Green Pneus": args.green,
    }
    for distribuidor, path in fontes.items():
        resultados = carregar_json(path) if path else None
        preencher_bloco(ws, distribuidor, itens_edital, resultados)

    print(f"\n✅ Planilha atualizada: https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit", file=sys.stderr)


if __name__ == "__main__":
    main()
