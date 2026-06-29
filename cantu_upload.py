#!/usr/bin/env python3
"""
cantu_upload.py — Popula a tabela "Cotação Cantu" no card do edital.

Uso:
  python cantu_upload.py items.json results.json [--db PAGE_ID]

  items.json   — configuração dos itens do edital (ex: items_cantagalo.json)
  results.json — saída do cantu_scraper.py
  --db         — page ID do database Notion (sobrescreve DEFAULT_DB_ID)

Fluxo por item:
  1. Seleciona o melhor produto (mais barato apto → mais barato com obs → sem estoque)
  2. Arquiva páginas antigas do item
  3. Insere 1 linha nova

Notas Cantu vs Bransales:
  - Coluna "Link Cantu" em vez de "Link Bransales"
  - Construção e lonas NUNCA verificáveis → sempre ⚠ Parcial se o item exigir
"""

import json, os, re, sys, requests

NOTION_VERSION = "2022-06-28"
NOTION_BASE    = "https://api.notion.com/v1"

# ── IDs POR EDITAL ─────────────────────────────────────────────────────────────
# Atualizar ao criar o database "Cotação Cantu" no Notion.
# Page ID: abra o database no Notion → copie o UUID da URL
EDITAIS = {
    "cantagalo_2026": {
        "db_page_id": "5df75a2e-cfe2-4d58-9bef-8feb3a5c93a7",
        "ds_id":      "18b5a92e-9aeb-4daa-96e8-b6f0ada7d4e6",
    },
}
DEFAULT_DB_ID = EDITAIS["cantagalo_2026"]["db_page_id"]

# ── TABELAS DE REFERÊNCIA ──────────────────────────────────────────────────────
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


# ── HELPERS ────────────────────────────────────────────────────────────────────

def load_token() -> str:
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.strip().startswith("NOTION_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip("\"'")
                    break
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization":  f"Bearer {token}",
        "Content-Type":   "application/json",
        "Notion-Version": NOTION_VERSION,
    }


# ── SELEÇÃO DO MELHOR PRODUTO ──────────────────────────────────────────────────

def select_best(candidatos: list[dict]) -> dict | None:
    if not candidatos:
        return None
    aptos = [c for c in candidatos if c.get("apto")]
    return min(aptos or candidatos, key=lambda c: c["preco_un"])


def criterios_label(produto: dict | None) -> str:
    if produto is None:
        return "— Sem estoque"
    return "✅ Verificado" if produto.get("apto") else "⚠️ Parcial"


# ── NOTION REST API ────────────────────────────────────────────────────────────

def query_pages(token: str, db_id: str, item_n: int) -> list[str]:
    url = f"{NOTION_BASE}/databases/{db_id.replace('-','')}/query"
    r = requests.post(
        url,
        headers=_headers(token),
        json={"filter": {"property": "Item", "number": {"equals": item_n}}},
        timeout=30,
    )
    r.raise_for_status()
    return [p["id"] for p in r.json().get("results", [])]


def archive_page(token: str, page_id: str):
    r = requests.patch(
        f"{NOTION_BASE}/pages/{page_id}",
        headers=_headers(token),
        json={"archived": True},
        timeout=30,
    )
    r.raise_for_status()


def insert_row(token: str, db_id: str, cfg: dict, produto: dict | None):
    item_n = cfg["item"]
    medida = MEDIDA.get(item_n, cfg.get("descricao", ""))
    ref_un = REF_UN.get(item_n, 0)

    if produto:
        brand  = (produto.get("marca") or "").title() or "Cantu"
        obs    = produto.get("obs", "")
        props = {
            "Produto":            {"title":     [{"text": {"content": medida}}]},
            "Item":               {"number":    item_n},
            "Marca":              {"rich_text": [{"text": {"content": brand}}]},
            "Qtde":               {"number":    cfg.get("qtde", 0)},
            "Preço Un":           {"number":    produto["preco_un"]},
            "Preço ref leilão":   {"number":    ref_un},
            "Distribuidor":       {"rich_text": [{"text": {"content": "Cantu"}}]},
            "Link Cantu":         {"url":       produto.get("url")},
            "Critérios técnicos": {"select":    {"name": criterios_label(produto)}},
            "Observação":         {"rich_text": [{"text": {"content": obs}}]},
        }
    else:
        props = {
            "Produto":            {"title":     [{"text": {"content": medida}}]},
            "Item":               {"number":    item_n},
            "Marca":              {"rich_text": [{"text": {"content": "Sem estoque"}}]},
            "Qtde":               {"number":    cfg.get("qtde", 0)},
            "Preço ref leilão":   {"number":    ref_un},
            "Distribuidor":       {"rich_text": [{"text": {"content": "Cantu"}}]},
            "Critérios técnicos": {"select":    {"name": "— Sem estoque"}},
            "Observação":         {"rich_text": [{"text": {"content": "Nenhum produto disponível na Cantu"}}]},
        }

    r = requests.post(
        f"{NOTION_BASE}/pages",
        headers=_headers(token),
        json={"parent": {"database_id": db_id.replace("-", "")}, "properties": props},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print("uso: python cantu_upload.py items.json results.json [--db PAGE_ID]")
        sys.exit(1)

    items_file   = args[0]
    results_file = args[1]
    db_id = DEFAULT_DB_ID
    if "--db" in args:
        db_id = args[args.index("--db") + 1]

    if not db_id:
        print("ERRO: DEFAULT_DB_ID não configurado. Use --db PAGE_ID.", file=sys.stderr)
        sys.exit(1)

    token = load_token()
    if not token:
        print("ERRO: NOTION_TOKEN não definido em .env.", file=sys.stderr)
        sys.exit(1)

    items_cfg   = json.load(open(items_file,   encoding="utf-8"))
    all_results = json.load(open(results_file, encoding="utf-8"))

    by_item: dict[int, list] = {}
    for r in all_results:
        by_item.setdefault(r["item"], []).append(r)

    erros = 0
    print(f"\n{'─'*62}", file=sys.stderr)
    print(f"  Database: {db_id}", file=sys.stderr)
    print(f"  Itens:    {len(items_cfg)}", file=sys.stderr)
    print(f"{'─'*62}", file=sys.stderr)

    for cfg in items_cfg:
        item_n     = cfg["item"]
        candidatos = by_item.get(item_n, [])
        melhor     = select_best(candidatos)
        label      = criterios_label(melhor)

        try:
            old_ids = query_pages(token, db_id, item_n)
            for pid in old_ids:
                archive_page(token, pid)
        except requests.HTTPError as e:
            print(f"  ! [item {item_n:02}] erro ao arquivar: {e.response.status_code}", file=sys.stderr)
            erros += 1

        try:
            insert_row(token, db_id, cfg, melhor)
            if melhor:
                brand = (melhor.get("marca") or "Cantu").title()
                print(f"  ✓ [item {item_n:02}] {brand:<28} R${melhor['preco_un']:>8.2f}  {label}", file=sys.stderr)
            else:
                print(f"  — [item {item_n:02}] Sem estoque{' '*38}{label}", file=sys.stderr)
        except requests.HTTPError as e:
            print(f"  ! [item {item_n:02}] erro ao inserir: {e.response.status_code} — {e.response.text[:120]}", file=sys.stderr)
            erros += 1

    print(f"{'─'*62}", file=sys.stderr)
    status = "com erros" if erros else "OK"
    print(f"  [done] {len(items_cfg)} itens — {status}\n", file=sys.stderr)
    if erros:
        print("  → Se receber 404: use MCP Notion para upload ou compartilhe", file=sys.stderr)
        print("    a integração 'Claude Code' com a página raiz 'Licitações - Pneus'.", file=sys.stderr)


if __name__ == "__main__":
    main()
