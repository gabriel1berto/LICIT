#!/usr/bin/env python3
"""
precificacao_gsheets.py — Appenda resultados de scraper na planilha de precificação.

Uso:
  python precificacao_gsheets.py results_X.json [--sheet "Sheet1"] [--spreadsheet-id ID]

Exemplo:
  python precificacao_gsheets.py results_cantagalo_gp.json
  python precificacao_gsheets.py results_cantagalo_cantu.json --sheet "Sheet1"

Setup (uma vez só):
  1. Acesse https://console.cloud.google.com/
  2. Crie/selecione um projeto → "APIs & Services" → "Enable APIs"
  3. Ative "Google Sheets API"
  4. "Credentials" → "Create Credentials" → "OAuth client ID" → "Desktop app"
  5. Baixe o JSON → renomeie para "credentials.json" → coloque em C:\\Users\\ghumb\\code\\licit\\
  6. Execute o script → browser abre para autorizar → salva token.json automaticamente
  7. Próximas execuções usam token.json (sem browser)

Formato da planilha (espelha seções Bransales e Cantu já existentes):
  Item | Produto | Critérios técnicos | Distribuidor | Marca | Link [Dist] | Observação | Preço UN | Preço Leilão | Qtde
"""

import json, os, re, sys
import gspread

# ── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1PUK7W_R4ZpahYcZ7eYl_LfkWXg4bhDIbW-GSbp377DE"
SHEET_NAME     = "Sheet1"

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token.json")

REF_UN = {
    1: 887.67,  2: 505.00,  3: 543.83,  4: 848.23,
    5: 629.67,  6: 616.33,  7: 692.17,  8: 717.33,
    9: 731.39, 10: 523.78, 11: 1183.67, 12: 1221.67,
}
MEDIDA = {
    1: "205/75 R16C", 2: "175/70 R14",  3: "185/65 R15", 4: "235/75 R15",
    5: "185/70 R15",  6: "205/60 R15",  7: "195/70 R15", 8: "205/60 R16",
    9: "215/65 R16", 10: "195/60 R15", 11: "225/75 R16", 12: "225/65 R16",
}
QTDE = {
    1: 88, 2: 132, 3: 144, 4: 8,  5: 12,
    6: 48, 7: 52,  8: 28,  9: 48, 10: 12, 11: 8, 12: 8,
}


# ── HELPERS ────────────────────────────────────────────────────────────────────

def fmt_brl(value: float) -> str:
    """Formata número como decimal brasileiro (ex: 545,90)."""
    return f"{value:.2f}".replace(".", ",")


def select_best(candidatos: list[dict]) -> dict | None:
    if not candidatos:
        return None
    aptos = [c for c in candidatos if c.get("apto")]
    return min(aptos or candidatos, key=lambda c: c["preco_un"])


def criterios_label(produto: dict | None) -> str:
    if produto is None:
        return "— Sem estoque"
    return "✅ Verificado" if produto.get("apto") else "⚠️ Parcial"


def detect_distribuidor(results: list[dict]) -> str:
    for r in results:
        if r.get("fornecedor"):
            return r["fornecedor"]
    # fallback: tenta inferir pelo campo url ou nome
    for r in results:
        url = r.get("url", "")
        if "bransales" in url:
            return "Bransales"
        if "speedmax" in url or "cantu" in url.lower():
            return "Cantu"
        if "gpfacil" in url:
            return "GP"
    return "Desconhecido"


def build_link_header(distribuidor: str) -> str:
    return f"Link {distribuidor}"


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print("uso: python precificacao_gsheets.py results.json [--sheet NOME] [--spreadsheet-id ID]")
        sys.exit(1)

    results_file = args[0]
    sheet_name   = SHEET_NAME
    spreadsheet_id = SPREADSHEET_ID

    if "--sheet" in args:
        sheet_name = args[args.index("--sheet") + 1]
    if "--spreadsheet-id" in args:
        spreadsheet_id = args[args.index("--spreadsheet-id") + 1]

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERRO: {CREDENTIALS_FILE} não encontrado.", file=sys.stderr)
        print("Siga o setup no cabeçalho deste arquivo para criar as credenciais OAuth.", file=sys.stderr)
        sys.exit(1)

    # Autenticação OAuth (abre browser na primeira vez)
    print("[auth] Autenticando com Google...", file=sys.stderr)
    gc = gspread.oauth(
        credentials_filename=CREDENTIALS_FILE,
        authorized_user_filename=TOKEN_FILE,
    )
    print("[auth] OK", file=sys.stderr)

    # Abre planilha e aba
    sh    = gc.open_by_key(spreadsheet_id)
    ws    = sh.worksheet(sheet_name)

    # Carrega resultados
    with open(results_file, encoding="utf-8") as f:
        all_results = json.load(f)

    distribuidor = detect_distribuidor(all_results)
    print(f"[info] Distribuidor detectado: {distribuidor}", file=sys.stderr)

    by_item: dict[int, list] = {}
    for r in all_results:
        by_item.setdefault(r["item"], []).append(r)

    # Monta linhas
    header = [
        "Item", "Produto", "Critérios técnicos", "Distribuidor",
        "Marca", build_link_header(distribuidor),
        "Observação", "Preço UN", "Preço Leilão", "Qtde",
    ]

    rows = [header]
    for i in range(1, 13):
        candidatos = by_item.get(i, [])
        best       = select_best(candidatos)
        label      = criterios_label(best)
        ref_str    = fmt_brl(REF_UN[i])
        medida     = MEDIDA[i]
        qtde       = QTDE[i]

        if best:
            marca   = best.get("marca", "")
            link    = best.get("url", "")
            obs     = best.get("obs", "")
            preco   = fmt_brl(best["preco_un"])
        else:
            marca   = "Sem estoque"
            link    = ""
            obs     = f"Nenhum produto disponível na {distribuidor}"
            preco   = ""

        rows.append([i, medida, label, distribuidor, marca, link, obs, preco, ref_str, qtde])

    # Appenda na planilha (após última linha com conteúdo)
    ws.append_rows(rows, value_input_option="USER_ENTERED")

    print(f"\n[done] {len(rows)-1} itens appendados na aba '{sheet_name}'", file=sys.stderr)
    for r in rows[1:]:
        sem = "SEM ESTOQUE"
        preco_str = r[7] if r[7] else sem
        print(f"  [{r[0]:02}] {r[1]:<14} {r[4]:<15} {preco_str}", file=sys.stderr)


if __name__ == "__main__":
    main()
