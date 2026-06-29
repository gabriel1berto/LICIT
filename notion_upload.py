#!/usr/bin/env python3
"""
notion_upload.py — Popula a tabela "Cotação Bransales" no card do edital.

Uso:
  python notion_upload.py items.json results.json [--db PAGE_ID]

  items.json   — configuração dos itens do edital (ex: items_cantagalo.json)
  results.json — saída do bransales_scraper.py
  --db         — page ID do database Notion (sobrescreve DEFAULT_DB_ID)

Fluxo por item:
  1. Busca resultados em results.json
  2. Seleciona o melhor produto:
       a. Mais barato com apto=True  (todos os critérios confirmados na página)
       b. Se nenhum apto: mais barato com obs  (critérios não verificáveis → pedir ao fornecedor)
       c. Se sem resultados: linha "Sem estoque"
  3. Arquiva páginas antigas do item no database
  4. Insere 1 linha nova

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ATENÇÃO — Acesso REST API Notion
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O token (ntn_...) só acessa páginas explicitamente compartilhadas com a
integração "Claude Code". Se receber 404:
  Notion → Settings → Connections → Claude Code → Share com a página raiz
  "Licitações - Pneus"  (cobre todos os cards filhos automaticamente)

Alternativa sem configurar integração: peça ao Claude para fazer o upload
via MCP Notion (usa OAuth do workspace, sem restrição de acesso).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json, os, re, sys, requests

NOTION_VERSION = "2022-06-28"
NOTION_BASE    = "https://api.notion.com/v1"

# ── IDs POR EDITAL ─────────────────────────────────────────────────────────────
# Atualizar a cada novo edital.
# Page ID: abra o database no Notion → copie o UUID da URL
# Data source ID: notion-fetch no card → <data-source url="collection://UUID">
EDITAIS = {
    "cantagalo_2026": {
        "db_page_id": "e9cb2c07-c323-4629-a404-64298c80beaf",  # "Cotação Bransales — PE 90051/2026"
        "ds_id":      "7403a5e5-241e-48df-90d6-ad278a465d02",  # para referência MCP
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
                    token = line.split("=", 1)[1].strip().strip('"\'')
                    break
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def extract_brand(nome: str, marca: str = "") -> str:
    """Extrai marca do produto. Espelha a função do scraper."""
    if marca:
        return marca.title()
    m = re.match(
        r"Pneu Aro \d+[cC]?\s+([A-Za-zÀ-ú][A-Za-zÀ-ú\s]*?)\s+\d{2,3}[/\d]",
        nome, re.I,
    )
    if m:
        brand = m.group(1).strip()
        if re.search(r"sunset", brand, re.I):         return "Sunset Tire"
        if re.search(r"general\s*tire", brand, re.I): return "General Tire"
        return brand.title()
    if nome.split()[0].isupper():
        return nome.split()[-1].title()
    return nome.split()[0].title()


# ── SELEÇÃO DO MELHOR PRODUTO ──────────────────────────────────────────────────

def select_best(candidatos: list[dict]) -> dict | None:
    """
    Seleciona 1 produto por item seguindo a prioridade:
      1. Mais barato com apto=True  (todos os critérios verificados na página)
      2. Mais barato com apto=False (critérios parcialmente verificáveis — pedir ficha ao fornecedor)
      3. None se lista vazia        (sem estoque / sem produtos na Bransales)
    """
    if not candidatos:
        return None
    aptos = [c for c in candidatos if c.get("apto")]
    return min(aptos or candidatos, key=lambda c: c["preco_un"])


def criterios_label(produto: dict | None) -> str:
    """Retorna o valor da coluna 'Critérios técnicos' para um produto."""
    if produto is None:
        return "— Sem estoque"
    return "✅ Verificado" if produto.get("apto") else "⚠️ Parcial"


# ── NOTION REST API ────────────────────────────────────────────────────────────

def query_pages(token: str, db_id: str, item_n: int) -> list[str]:
    """Retorna IDs de páginas existentes no database para o item."""
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
    """Insere 1 linha no database para o item."""
    item_n = cfg["item"]
    medida = MEDIDA.get(item_n, cfg.get("descricao", ""))
    ref_un = REF_UN.get(item_n, 0)

    if produto:
        brand  = extract_brand(produto["nome"], produto.get("marca", ""))
        obs    = produto.get("obs", "")
        props = {
            "Produto":            {"title":     [{"text": {"content": medida}}]},
            "Item":               {"number":    item_n},
            "Marca":              {"rich_text": [{"text": {"content": brand}}]},
            "Qtde":               {"number":    cfg.get("qtde", 0)},
            "Preço Un":           {"number":    produto["preco_un"]},
            "Preço ref leilão":   {"number":    ref_un},
            "Distribuidor":       {"rich_text": [{"text": {"content": "Bransales"}}]},
            "Link Bransales":     {"url":       produto.get("url")},
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
            "Distribuidor":       {"rich_text": [{"text": {"content": "Bransales"}}]},
            "Critérios técnicos": {"select":    {"name": "— Sem estoque"}},
            "Observação":         {"rich_text": [{"text": {"content": "Nenhum produto disponível na Bransales"}}]},
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
        print("uso: python notion_upload.py items.json results.json [--db PAGE_ID]")
        sys.exit(1)

    items_file   = args[0]
    results_file = args[1]
    db_id = DEFAULT_DB_ID
    if "--db" in args:
        db_id = args[args.index("--db") + 1]

    token = load_token()
    if not token:
        print("ERRO: NOTION_TOKEN não definido em .env ou variável de ambiente.", file=sys.stderr)
        sys.exit(1)

    items_cfg   = json.load(open(items_file,   encoding="utf-8"))
    all_results = json.load(open(results_file, encoding="utf-8"))

    # Agrupa resultados por item
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

        # 1. Arquiva páginas existentes
        try:
            old_ids = query_pages(token, db_id, item_n)
            for pid in old_ids:
                archive_page(token, pid)
        except requests.HTTPError as e:
            print(f"  ! [item {item_n:02}] erro ao arquivar: {e.response.status_code} — {e.response.text[:120]}", file=sys.stderr)
            erros += 1

        # 2. Insere linha definitiva
        try:
            pid = insert_row(token, db_id, cfg, melhor)
            if melhor:
                brand = extract_brand(melhor["nome"], melhor.get("marca", ""))
                print(f"  ✓ [item {item_n:02}] {brand:<28} R${melhor['preco_un']:>8.2f}  {label}", file=sys.stderr)
            else:
                print(f"  — [item {item_n:02}] Sem estoque{' '*38}{label}", file=sys.stderr)
        except requests.HTTPError as e:
            print(f"  ! [item {item_n:02}] erro ao inserir: {e.response.status_code} — {e.response.text[:120]}", file=sys.stderr)
            erros += 1

    print(f"{'─'*62}", file=sys.stderr)
    status = "com erros" if erros else "OK"
    print(f"  [done] {len(items_cfg)} itens processados — {status}\n", file=sys.stderr)
    if erros:
        print("  → Se receber 404: compartilhe a integração 'Claude Code' com a", file=sys.stderr)
        print("    página raiz 'Licitações - Pneus' no Notion (Settings → Connections).", file=sys.stderr)
        print("    Alternativa: peça ao Claude para fazer o upload via MCP Notion.", file=sys.stderr)


if __name__ == "__main__":
    main()
