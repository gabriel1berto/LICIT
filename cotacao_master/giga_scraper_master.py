#!/usr/bin/env python3
"""
giga_scraper_master.py — Cópia de giga_scraper.py (raiz) adaptada pro fluxo de
COTAÇÃO MASTER (coleta diária de mercado, não ligada a edital específico).

Diferenças vs. giga_scraper.py (original, NUNCA alterar, segue servindo o
fluxo de cotação por edital):
  - Sem limite de candidato por item (MAX_CHECK removido) — visita ficha
    técnica de TODOS os produtos que batem a medida, não só os 3 mais baratos.
  - Delay entre visita de ficha técnica (rate-limit por cortesia).

Sem login (mesmo achado do original, 15/jul/26): preço público, sem tier de
atacado/lojista — testado login + kit de 4 unidades, nenhum dos dois muda o
preço unitário. Busca é FUZZY (mistura medida próxima) — valida via
medida_bate() antes de aceitar.

Uso   : python giga_scraper_master.py items.json [results.json]
Output: JSON com TODOS os produtos que batem a medida, ordenados por preço
"""

import json, re, sys, time
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE = "https://www.gigapneus.com.br"
DELAY_FICHA = 1.0
IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUHVWY")}


# ── PARSERS ────────────────────────────────────────────────────────────────────

def parse_price(text: str):
    m = re.search(r"A partir de\s*\n?\s*R\$\s*([\d.]+,\d{2})", text or "", re.I)
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def iv_ok(iv_produto: str, iv_min: str) -> bool:
    if not iv_min:
        return True
    return IV_ORDER.get(iv_produto.upper(), -1) >= IV_ORDER.get(iv_min.upper(), 0)


def parse_ic_iv(nome: str):
    m = re.search(r"\b(\d{2,3})(?:/\d{2,3})?([A-Z])\b", nome)
    if m:
        return int(m.group(1)), m.group(2).upper()
    return None, None


def extract_brand(nome: str) -> str:
    m = re.search(r"-\s*([A-Za-zÀ-ú]+)", nome)
    return m.group(1).title() if m else ""


def piso_ok(nome: str, padrao: str) -> bool:
    if not padrao:
        return True
    if padrao.upper() == "AT":
        if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN|OFF[\s\-]?ROAD", nome, re.I):
            return True
        return False
    return True


def _num_pattern(valor) -> str:
    return re.escape(str(valor)).replace(r"\.", "[.,]")


def medida_bate(nome: str, cfg: dict) -> bool:
    largura = str(cfg.get("largura") or "").strip()
    aro     = str(cfg.get("aro") or "").strip()
    if not largura or not aro:
        return True
    aro_re = re.escape(aro)
    altura = cfg.get("altura")
    if altura:
        pattern = rf"{_num_pattern(largura)}\s*[/xX]\s*{_num_pattern(altura)}\D{{0,3}}{aro_re}\b"
    else:
        pattern = rf"{_num_pattern(largura)}\s*[-xXrR/]\s*{aro_re}\b"
    return re.search(pattern, nome, re.I) is not None


def build_medida(cfg: dict) -> str:
    return f"{cfg['largura']}/{cfg['altura']} R{cfg['aro']}"


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, medida: str) -> list[dict]:
    url = f"{BASE}/buscar?q={quote(medida)}"
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector('a[href*="/pneu-"]', timeout=8_000)
    except PwTimeout:
        return []

    raw = page.evaluate("""() => {
        const cards = Array.from(document.querySelectorAll('.listagem-item'));
        return cards.map(card => {
            const a = card.querySelector('a[href*="/pneu-"]');
            return { href: a ? a.getAttribute('href') : null, texto: card.innerText };
        });
    }""")

    items = []
    seen = set()
    for r in raw:
        href = r["href"]
        if not href or href in seen:
            continue
        seen.add(href)
        texto = r["texto"] or ""
        if re.search(r"esgotado|indispon[ií]vel|sem estoque", texto, re.I):
            continue
        primeira_linha = texto.split("\n")[0].strip()
        if not primeira_linha:
            continue
        pr = parse_price(texto)
        if not pr:
            continue
        items.append({
            "nome":     primeira_linha,
            "marca":    extract_brand(primeira_linha),
            "preco_un": pr,
            "url":      href if href.startswith("http") else f"{BASE}{href}",
        })

    items.sort(key=lambda x: x["preco_un"])
    return items


# ── PÁGINA DO PRODUTO ──────────────────────────────────────────────────────────

def get_product_specs(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded")
    specs = {"marca": None, "ic": None, "iv": None, "treadwear": None,
              "construcao": None, "num_lonas": None, "inmetro": None}
    try:
        page.wait_for_selector("text=/ÍNDICE DE CARGA/", timeout=5_000)
        texto = page.locator("body").inner_text()

        m = re.search(r"MARCA:\s*(.+)", texto)
        if m:
            specs["marca"] = m.group(1).strip().title()
        m = re.search(r"ÍNDICE DE CARGA \((\d+)\)", texto)
        if m:
            specs["ic"] = int(m.group(1))
        m = re.search(r"ÍNDICE DE VELOCIDADE \(([A-Z]+)\)", texto)
        if m:
            specs["iv"] = m.group(1)
    except PwTimeout:
        pass
    return specs


# ── PROCESSAMENTO POR ITEM ─────────────────────────────────────────────────────

def process_item(page, cfg: dict) -> list[dict]:
    ic_min         = cfg.get("min_ic", 0)
    iv_min         = cfg.get("min_iv", "")
    tw_min         = cfg.get("min_treadwear", 0)
    construcao_req = cfg.get("construcao", "")
    min_lonas      = cfg.get("min_lonas", 0)
    padrao_piso    = cfg.get("padrao_piso", "")
    item_n         = cfg["item"]

    medida = build_medida(cfg)
    print(f"[item {item_n}] busca Giga: '{medida}'", file=sys.stderr)

    candidates = scrape_listing(page, medida)
    print(f"[item {item_n}] {len(candidates)} com preço", file=sys.stderr)

    antes = len(candidates)
    candidates = [c for c in candidates if medida_bate(c["nome"], cfg)]
    if len(candidates) < antes:
        print(f"  [filtro medida] {antes - len(candidates)} descartado(s) — medida diferente da pedida", file=sys.stderr)
    print(f"[item {item_n}] {len(candidates)} bate a medida — visitando ficha de todos (cotação master)", file=sys.stderr)

    results = []
    for c in candidates:
        nome = c["nome"]

        ic_nome, iv_nome = parse_ic_iv(nome)
        if ic_nome is not None and ic_min and ic_nome < ic_min:
            print(f"  ✗ IC {ic_nome}<{ic_min}  {nome}", file=sys.stderr)
            continue
        if iv_nome is not None and not iv_ok(iv_nome, iv_min):
            print(f"  ✗ IV {iv_nome}<{iv_min}  {nome}", file=sys.stderr)
            continue
        if not piso_ok(nome, padrao_piso):
            print(f"  ✗ piso não-AT  {nome}", file=sys.stderr)
            continue

        specs = get_product_specs(page, c["url"])
        time.sleep(DELAY_FICHA)

        ic = specs["ic"] if specs["ic"] is not None else ic_nome
        if ic is not None and ic_min and ic < ic_min:
            print(f"  ✗ IC {ic}<{ic_min} (ficha)  {nome}", file=sys.stderr)
            continue
        iv = specs["iv"] if specs["iv"] is not None else iv_nome
        if iv and iv_min and not iv_ok(iv, iv_min):
            print(f"  ✗ IV {iv}<{iv_min} (ficha)  {nome}", file=sys.stderr)
            continue

        obs_list = []
        if tw_min > 0:
            obs_list.append(f"Treadwear não publicado pela Giga Pneus (exige ≥{tw_min})")
        if construcao_req:
            obs_list.append(f"Construção ({construcao_req}) não publicada pela Giga Pneus")
        if min_lonas:
            obs_list.append(f"Nº de lonas não publicado pela Giga Pneus (exige ≥{min_lonas})")

        obs_str = " | ".join(obs_list)
        apto    = len(obs_list) == 0
        results.append({
            "item":       item_n,
            "descricao":  cfg["descricao"],
            "medida":     cfg["descricao"].split(" ", 3)[-1],
            "nome":       nome,
            "marca":      specs["marca"] or c["marca"],
            "preco_un":   c["preco_un"],
            "ic":         ic,
            "iv":         iv,
            "treadwear":  specs["treadwear"],
            "construcao": specs["construcao"],
            "num_lonas":  specs["num_lonas"],
            "inmetro":    specs["inmetro"],
            "apto":       apto,
            "obs":        obs_str,
            "qtde":       cfg.get("qtde", 1),
            "url":        c["url"],
            "fornecedor": "Giga Pneus",
        })
        flag = "✓" if apto else "⚠"
        print(f"  {flag} {nome}  R${c['preco_un']:.2f}"
              + (f"  [{obs_str}]" if obs_str else ""), file=sys.stderr)

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python giga_scraper_master.py items.json [results.json]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        items_cfg = json.load(f)

    all_results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()
        page.set_extra_http_headers({"Accept-Language": "pt-BR,pt;q=0.9"})

        for cfg in items_cfg:
            res = process_item(page, cfg)
            all_results.extend(res)

        browser.close()

    output = json.dumps(all_results, ensure_ascii=False, indent=2)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n[done] {len(all_results)} produtos → {sys.argv[2]}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
