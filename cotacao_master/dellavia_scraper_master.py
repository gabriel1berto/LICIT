#!/usr/bin/env python3
"""
dellavia_scraper_master.py — Cópia de dellavia_scraper.py (raiz) adaptada pro
fluxo de COTAÇÃO MASTER (coleta diária de mercado, não ligada a edital
específico).

Diferenças vs. dellavia_scraper.py (original, NUNCA alterar, segue servindo o
fluxo de cotação por edital):
  - Sem limite de candidato por item (MAX_CHECK removido) — visita ficha
    técnica de TODOS os produtos em estoque, não só os 3 mais baratos.
  - Delay entre visita de ficha técnica (rate-limit por cortesia — Della Via
    não tem WAF confirmado, mas evita martelar o site sem necessidade).
  - Ficha técnica já era sempre visitada no original (por causa do INMETRO),
    diferente do Bransales/Cantu/GP — essa parte não precisou mudar.

Sem login (mesmo achado do original, 15/jul/26): credencial do Notion loga
sem erro, mas não muda preço nem existe tier de atacado self-service. Preço
aqui é varejo público, teto de referência até desconto real ser confirmado
por contato manual (telefone/WhatsApp).

Uso   : python dellavia_scraper_master.py items.json [results.json]
Output: JSON com TODOS os produtos em estoque por item, ordenados por preço
"""

import json, re, sys, time
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE = "https://www.dellavia.com.br"
DELAY_FICHA = 1.0  # segundos entre visita de ficha técnica
IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUHVWY")}


# ── PARSERS ────────────────────────────────────────────────────────────────────

def parse_price(text: str):
    m = re.search(r"R\$\s*([\d.]+,\d{2})", text)
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
    """Fallback se a ficha técnica não trouxer 'Marca' — a 1ª palavra depois de
    'Pneu' às vezes é o MODELO, não a marca (achado real: linha Fuzion vem
    como marca Bridgestone na ficha, mas 'Fuzion' no nome do produto)."""
    m = re.match(r"Pneu\s+([A-Za-zÀ-ú]+)\s+\d{2,3}/\d{2,3}", nome, re.I)
    return m.group(1).title() if m else ""


def piso_ok(nome: str, padrao: str) -> bool:
    if not padrao:
        return True
    if padrao.upper() == "AT":
        if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN|OFF[\s\-]?ROAD", nome, re.I):
            return True
        return False
    return True


# ── URL DE LISTAGEM ────────────────────────────────────────────────────────────

def build_url(item: dict) -> str:
    L, P, R = item["largura"], item["altura"], item["aro"]
    return f"{BASE}/{L}/{P}/{R}/?_q=pneu&fuzzy=0&initialMap=ft&map=largura,perfil,aros,ft&operator=and"


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, url: str) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded")
    try:
        # Esperar o 1º link é race (achado real: só 1 de 3 produtos vinha) — o
        # contador "X Produtos" só renderiza com a listagem inteira montada.
        page.wait_for_selector("text=/\\d+ Produto/", timeout=8_000)
        # Preço hidrata ~2s depois do contador — sem isso todo item vinha com
        # price_el=None e era descartado em silêncio.
        try:
            page.wait_for_selector('[class*="bestPrice"]', timeout=5_000)
        except PwTimeout:
            pass
    except PwTimeout:
        return []

    items = []
    for a in page.query_selector_all('a[href$="/p"]'):
        if a.query_selector("button[disabled]"):
            continue  # "Indisponível" — sem estoque real, confirmado pelo site
        h3 = a.query_selector("h3")
        if not h3:
            continue
        name = h3.inner_text().strip().title()  # headless renderiza TUDO MAIÚSCULO
        price_el = a.query_selector('[class*="product-price--bestPrice"]')
        if not price_el:
            continue
        pr = parse_price(price_el.inner_text())
        if not pr:
            continue
        href = a.get_attribute("href")
        items.append({
            "nome":     name,
            "marca":    extract_brand(name),
            "preco_un": pr,
            "url":      href if href.startswith("http") else f"{BASE}{href}",
        })

    items.sort(key=lambda x: x["preco_un"])
    return items


# ── PÁGINA DO PRODUTO ──────────────────────────────────────────────────────────

def get_product_specs(page, url: str) -> dict:
    full_url = url if url.startswith("http") else f"{BASE}{url}"
    page.goto(full_url, wait_until="domcontentloaded")
    specs = {"treadwear": None, "construcao": None, "num_lonas": None, "inmetro": None, "marca": None}
    try:
        page.wait_for_selector(".dellavia-store-theme-5-x-linha", timeout=5_000)
        for linha in page.query_selector_all(".dellavia-store-theme-5-x-linha"):
            spans = linha.query_selector_all("span")
            if len(spans) == 2 and spans[0].inner_text().strip() == "Marca":
                specs["marca"] = spans[1].inner_text().strip()
                break

        page.wait_for_selector(".dellavia-store-theme-5-x-ClassificadorDurAdTemp--card", timeout=5_000)
        valores = {}
        for c in page.query_selector_all(".dellavia-store-theme-5-x-ClassificadorDurAdTemp--card"):
            titulo_el = c.query_selector(".dellavia-store-theme-5-x-ClassificadorDurAdTempInfo--title strong")
            valor_el  = c.query_selector(".dellavia-store-theme-5-x-ClassificadorDurAdTempInfo--progressBar-counter span")
            if titulo_el and valor_el:
                valores[titulo_el.inner_text().strip().upper()] = valor_el.inner_text().strip()
        if valores.get("DURABILIDADE", "").isdigit():
            specs["treadwear"] = int(valores["DURABILIDADE"])

        graus = []
        for img in page.query_selector_all(".dellavia-store-theme-5-x-ClassificadorInmetro-grid img"):
            src = img.get_attribute("src") or ""
            m = re.search(r"class-(comb|ad)-(\w+)\.png", src)
            if m:
                tipo = "combustível" if m.group(1) == "comb" else "aderência"
                graus.append(f"{tipo} {m.group(2).upper()}")
        if graus:
            specs["inmetro"] = " / ".join(graus)

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

    url = build_url(cfg)
    print(f"[item {item_n}] GET {url}", file=sys.stderr)

    candidates = scrape_listing(page, url)
    print(f"[item {item_n}] {len(candidates)} com preço — visitando ficha de todos (cotação master)", file=sys.stderr)

    results = []
    for c in candidates:
        nome = c["nome"]

        ic, iv = parse_ic_iv(nome)
        if ic is not None and ic_min and ic < ic_min:
            print(f"  ✗ IC {ic}<{ic_min}  {nome}", file=sys.stderr)
            continue
        if iv is not None and not iv_ok(iv, iv_min):
            print(f"  ✗ IV {iv}<{iv_min}  {nome}", file=sys.stderr)
            continue
        if not piso_ok(nome, padrao_piso):
            print(f"  ✗ piso não-AT  {nome}", file=sys.stderr)
            continue

        specs = get_product_specs(page, c["url"])
        time.sleep(DELAY_FICHA)

        obs_list = []

        tw = specs["treadwear"]
        if tw_min > 0:
            if tw is None:
                obs_list.append(f"Treadwear não disponível na página (exige ≥{tw_min})")
            elif tw < tw_min:
                print(f"  ✗ Treadwear {tw}<{tw_min}  {nome}", file=sys.stderr)
                continue

        if construcao_req:
            obs_list.append(f"Construção ({construcao_req}) não verificável — Della Via não expõe esse dado")

        if min_lonas:
            obs_list.append(f"Nº de lonas não verificável — Della Via não expõe esse dado (exige ≥{min_lonas})")

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
            "treadwear":  tw,
            "construcao": specs["construcao"],
            "num_lonas":  specs["num_lonas"],
            "tipo_terreno": None,
            "inmetro":    specs["inmetro"],
            "apto":       apto,
            "obs":        obs_str,
            "qtde":       cfg.get("qtde", 1),
            "url":        c["url"],
            "fornecedor": "Della Via",
        })
        flag = "✓" if apto else "⚠"
        print(f"  {flag} {nome}  R${c['preco_un']:.2f}"
              + (f"  [{obs_str}]" if obs_str else ""), file=sys.stderr)

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python dellavia_scraper_master.py items.json [results.json]", file=sys.stderr)
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
