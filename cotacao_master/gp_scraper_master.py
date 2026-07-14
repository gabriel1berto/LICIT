#!/usr/bin/env python3
"""
gp_scraper_master.py — Cópia de gp_scraper.py adaptada pro fluxo de COTAÇÃO
MASTER (coleta diária de mercado, não ligada a edital específico).

Diferenças vs. gp_scraper.py (original, NUNCA alterar):
  - Sem limite de candidato por item (MAX_CHECK removido) — visita ficha
    técnica de TODOS os produtos em estoque.
  - Delay entre visita de ficha técnica (rate-limit).
  - COOKIES_F aponta pro gp_cookies.json na RAIZ do repo (arquivo único,
    compartilhado com gp_scraper.py original — não duplicar cookie).

Uso   : python gp_scraper_master.py items.json [results.json]
Output: JSON com TODOS os produtos em estoque por item
"""

import json, os, re, sys, time
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE       = "https://www.gpfacil.com.br"
# Cookie compartilhado com gp_scraper.py — vive na raiz do repo, não em
# cotacao_master/ (script está numa subpasta, __file__ aponta pra cá).
COOKIES_F  = os.path.join(os.path.dirname(__file__), "..", "gp_cookies.json")
DELAY_FICHA = 1.5

IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUHVWY")}


# ── PARSERS ────────────────────────────────────────────────────────────────────

def parse_price(text: str) -> float | None:
    m = re.search(r"R\$\s*([\d.]+,\d{2})", text or "")
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


def piso_ok_nome(nome: str, padrao: str):
    if not padrao or padrao.upper() != "AT":
        return True
    if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN", nome, re.I):
        return True
    if re.search(r"\bH[/\-]?T\b|HIGHWAY|TOURING\b", nome, re.I):
        return False
    return None


def extract_brand(nome: str) -> str:
    parts = nome.strip().split()
    if len(parts) > 1 and parts[0].lower() == "pneu":
        return parts[1].title()
    return parts[0].title() if parts else ""


def build_medida_gp(cfg: dict) -> str:
    L = cfg["largura"]
    A = cfg.get("altura")
    R = str(cfg["aro"]).lower()
    if cfg.get("categoria") == "agricola" or not A:
        return f"{L}-{R}"
    return f"{L}/{A}r{R}"


# ── COOKIES ────────────────────────────────────────────────────────────────────

def load_cookies() -> list[dict]:
    if not os.path.exists(COOKIES_F):
        print(f"ERRO: {COOKIES_F} não encontrado.", file=sys.stderr)
        print("Exporte cookies do MCP browser após login e salve nesse arquivo.", file=sys.stderr)
        sys.exit(1)
    with open(COOKIES_F, encoding="utf-8") as f:
        return json.load(f)


def inject_and_check(ctx, page) -> bool:
    cookies = load_cookies()
    ctx.add_cookies(cookies)
    page.goto(BASE, wait_until="domcontentloaded", timeout=30_000)
    content = page.content().lower()
    return "sair" in content or "minha conta" in content or "logout" in content


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, medida: str) -> list[dict]:
    url = f"{BASE}/busca?busca={quote(medida)}"
    page.goto(url, wait_until="networkidle", timeout=30_000)

    try:
        page.wait_for_selector('a[href*="/pneu-"] h3', timeout=8_000)
    except PwTimeout:
        return []

    raw = page.evaluate(r"""() => {
        const results = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/pneu-"] h3').forEach(h3 => {
            const a = h3.closest('a[href*="/pneu-"]');
            if (!a || seen.has(a.href)) return;
            seen.add(a.href);
            let container = a.parentElement;
            for (let i = 0; i < 6 && container; i++) {
                if (container.querySelectorAll('h3').length === 1) break;
                container = container.parentElement;
            }
            const name = h3.textContent.trim();
            const url  = a.href;
            let priceText = null;
            for (const el of (container ? container.querySelectorAll('*') : [])) {
                const t = el.textContent.trim();
                if (t.startsWith('R$') && el.children.length === 0) {
                    priceText = t;
                    break;
                }
            }
            const cardEl = container ? container.parentElement : null;
            const esgotado = cardEl
                ? Array.from(cardEl.querySelectorAll('p'))
                      .some(p => p.textContent.toLowerCase().includes('esgotado'))
                : false;
            results.push({ name, url, priceText, esgotado });
        });
        return results;
    }""")

    items = []
    for r in raw:
        if r["esgotado"]:
            print(f"  [esgotado] {r['name']}", file=sys.stderr)
            continue
        preco = parse_price(r["priceText"])
        if preco is None:
            print(f"  [sem preço] {r['name']} — texto: {r['priceText']!r}", file=sys.stderr)
            continue
        items.append({
            "nome":     r["name"],
            "marca":    extract_brand(r["name"]),
            "preco_un": preco,
            "url":      r["url"],
        })

    items.sort(key=lambda x: x["preco_un"])
    return items


# ── PÁGINA DO PRODUTO ──────────────────────────────────────────────────────────

def get_product_specs(page, url: str) -> dict:
    specs = {
        "treadwear":    None,
        "tipo_terreno": None,
        "ic":           None,
        "iv":           None,
        "construcao":   None,
        "inmetro":      None,
        "url":          url,
    }

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20_000)

        table_data: dict = page.evaluate("""() => {
            const rows = {};
            document.querySelectorAll('table tr').forEach(row => {
                const cells = row.querySelectorAll('th, td');
                if (cells.length >= 2) {
                    rows[cells[0].textContent.trim()] = cells[1].textContent.trim();
                }
            });
            return rows;
        }""")

        ic_raw = table_data.get("Índice de carga", "")
        m = re.search(r"(\d+)", ic_raw)
        if m:
            specs["ic"] = int(m.group(1))

        iv_raw = table_data.get("Índice de velocidade", "")
        m = re.search(r"\b([A-Z]{1,2})\b", iv_raw)
        if m:
            specs["iv"] = m.group(1)

        tw_raw = table_data.get("Tradwear", "") or table_data.get("Treadwear", "")
        m = re.search(r"(\d+)", tw_raw)
        if m and int(m.group(1)) > 0:
            specs["treadwear"] = int(m.group(1))

        const_raw = table_data.get("Tipo de construção", "").strip()
        if const_raw and const_raw not in ("0", ""):
            specs["construcao"] = const_raw.lower()

        tt = table_data.get("Tipo de Terreno", "").strip()
        if tt:
            specs["tipo_terreno"] = tt.upper()

        inm = table_data.get("Número do registro no Inmetro", "").strip()
        if inm and inm not in ("0", ""):
            specs["inmetro"] = inm

    except PwTimeout:
        pass
    except Exception as e:
        print(f"  ! specs error: {e}", file=sys.stderr)

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

    medida = build_medida_gp(cfg)
    print(f"\n[item {item_n:02}] busca GP: '{medida}'", file=sys.stderr)

    candidates = scrape_listing(page, medida)
    print(f"[item {item_n:02}] {len(candidates)} produto(s) em estoque — visitando ficha de todos (cotação master)", file=sys.stderr)

    results = []

    for c in candidates:
        nome = c["nome"]

        ic_nome, iv_nome = parse_ic_iv(nome)

        if ic_nome is not None and ic_min and ic_nome < ic_min:
            print(f"  ✗ IC {ic_nome}<{ic_min}  {nome}", file=sys.stderr)
            continue
        if iv_nome is not None and iv_min and not iv_ok(iv_nome, iv_min):
            print(f"  ✗ IV {iv_nome}<{iv_min}  {nome}", file=sys.stderr)
            continue

        piso_nome = piso_ok_nome(nome, padrao_piso)
        if piso_nome is False:
            print(f"  ✗ piso não-AT (nome)  {nome}", file=sys.stderr)
            continue

        specs = get_product_specs(page, c["url"])
        time.sleep(DELAY_FICHA)
        obs_list: list[str] = []

        tw = specs["treadwear"]
        if tw_min > 0:
            if tw is None:
                obs_list.append(f"Treadwear não disponível na ficha (exige ≥{tw_min})")
            elif tw < tw_min:
                print(f"  ✗ Treadwear {tw}<{tw_min}  {nome}", file=sys.stderr)
                continue

        if padrao_piso and padrao_piso.upper() == "AT":
            tt = specs["tipo_terreno"]
            if piso_nome is True:
                pass
            elif tt is None:
                if piso_nome is None:
                    obs_list.append("Tipo de terreno não disponível na ficha (exige AT)")
            elif tt not in ("AT", "MT", "AW"):
                print(f"  ✗ Terreno '{tt}' ≠ AT  {nome}", file=sys.stderr)
                continue

        ic = specs["ic"] if specs["ic"] is not None else ic_nome
        if ic is not None and ic_min and ic < ic_min:
            print(f"  ✗ IC {ic}<{ic_min} (ficha)  {nome}", file=sys.stderr)
            continue

        iv = specs["iv"] if specs["iv"] is not None else iv_nome
        if iv and iv_min and not iv_ok(iv, iv_min):
            print(f"  ✗ IV {iv}<{iv_min} (ficha)  {nome}", file=sys.stderr)
            continue

        if construcao_req:
            gp_const = specs.get("construcao") or ""
            if not gp_const:
                obs_list.append(
                    f"Construção ({construcao_req}) não publicada na GP — confirmar com fornecedor"
                )

        if min_lonas:
            obs_list.append(
                f"Nº de lonas não publicado na GP (exige ≥{min_lonas}) — confirmar com fornecedor"
            )

        obs_str = " | ".join(obs_list)
        apto    = len(obs_list) == 0

        results.append({
            "item":         item_n,
            "descricao":    cfg["descricao"],
            "nome":         nome,
            "marca":        c["marca"],
            "preco_un":     c["preco_un"],
            "ic":           ic,
            "iv":           iv,
            "treadwear":    tw,
            "tipo_terreno": specs["tipo_terreno"],
            "construcao":   specs.get("construcao"),
            "num_lonas":    None,
            "inmetro":      specs.get("inmetro"),
            "apto":         apto,
            "obs":          obs_str,
            "qtde":         cfg.get("qtde", 1),
            "url":          c["url"],
            "fornecedor":   "GP",
        })

        flag = "✓" if apto else "⚠"
        print(
            f"  {flag} {nome}  R${c['preco_un']:.2f}"
            + (f"  [{obs_str}]" if obs_str else ""),
            file=sys.stderr,
        )

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python gp_scraper_master.py items.json [results.json]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        items_cfg = json.load(f)

    all_results: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()

        print("[auth] Injetando cookies...", file=sys.stderr)
        logged_in = inject_and_check(ctx, page)
        if not logged_in:
            print("ERRO: Cookies expirados ou inválidos.", file=sys.stderr)
            print("Para renovar:", file=sys.stderr)
            print("  1. Acesse https://www.gpfacil.com.br no MCP browser e faça login", file=sys.stderr)
            print("  2. Execute: document.cookie no console", file=sys.stderr)
            print("  3. Atualize gp_cookies.json com os novos valores", file=sys.stderr)
            browser.close()
            sys.exit(1)
        print("[auth] OK — sessão ativa", file=sys.stderr)

        for cfg in items_cfg:
            res = process_item(page, cfg)
            all_results.extend(res)

        browser.close()

    output = json.dumps(all_results, ensure_ascii=False, indent=2)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n[done] {len(all_results)} produto(s) -> {sys.argv[2]}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
