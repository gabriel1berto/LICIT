#!/usr/bin/env python3
"""
cantu_scraper.py — Busca preços de pneus na Cantu/SpeedMax (empresas.speedmax.com.br)
Uso   : python cantu_scraper.py items.json [results.json]
Output: JSON com produtos aprovados por item, ordenados por preço Pix

Critérios validados por item (via items.json):
  construcao    — NUNCA disponível na Cantu (site não publica). Sempre ⚠ obs.
  min_lonas     — NUNCA disponível na Cantu (site não publica). Sempre ⚠ obs.
  min_treadwear — "Código Utqg" na aba "Informações técnicas" (ex: "420AB" → 400)
  min_ic        — "Índice de peso" na aba técnica (ex: "92 - 630 kg, 92" → 92)
  min_iv        — "Índice de velocidade" na aba técnica (ex: "H - 210 km/h, H" → H)
  padrao_piso   — "Tipo de Terreno" na aba técnica (AT/HT/MT) + nome do produto

Preço usado: "à vista no Pix/boleto" — menor preço disponível ao atacado.

ACESSO:
  Site:  https://empresas.speedmax.com.br
  Login: modal disparado ao clicar "Ver preço" na listagem
"""

import json, re, sys, unicodedata
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

EMAIL     = "ghumberto.eng@gmail.com"
PASSWORD  = "N0v@senha"
BASE      = "https://empresas.speedmax.com.br"
MAX_CHECK = 3  # máx de produtos visitados por item

IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUVWHY")}


# ── PARSERS ────────────────────────────────────────────────────────────────────

def parse_price(text: str) -> float | None:
    """Extrai R$ X,XX de uma string."""
    m = re.search(r"R\$\s*([\d.]+,\d{2})", text or "")
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def iv_ok(iv_produto: str, iv_min: str) -> bool:
    if not iv_min:
        return True
    return IV_ORDER.get(iv_produto.upper(), -1) >= IV_ORDER.get(iv_min.upper(), 0)


def parse_ic_iv(nome: str):
    """Extrai IC e IV do nome do produto (ex: '92H' → 92, 'H')."""
    m = re.search(r"\b(\d{2,3})(?:/\d{2,3})?([A-Z])\b", nome)
    if m:
        return int(m.group(1)), m.group(2).upper()
    return None, None


def piso_ok_nome(nome: str, padrao: str):
    """Verifica AT pelo nome. Retorna True/False/None (inconclusivo)."""
    if not padrao or padrao.upper() != "AT":
        return True
    if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN", nome, re.I):
        return True
    if re.search(r"\bH[/\-]?T\b|HIGHWAY|TOURING\b", nome, re.I):
        return False
    return None  # sem indicação clara → precisa verificar ficha


def name_to_slug(name: str) -> str:
    """Converte nome do produto para slug da URL da Cantu."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s-]", "-", name)
    name = re.sub(r"\s+", "-", name)
    return re.sub(r"-+", "-", name).strip("-")


def extract_brand(nome: str) -> str:
    """Extrai marca: tudo entre 'Pneu ' e ' Aro '."""
    m = re.match(r"Pneu\s+(.+?)\s+Aro\s+\d", nome, re.I)
    return m.group(1).title() if m else ""


def build_title(cfg: dict) -> str:
    """Monta string de busca: ex. '205/60R16' ou '205/75R16C'."""
    L = cfg["largura"]
    A = cfg.get("altura", "")
    R = str(cfg["aro"]).upper()
    return f"{L}/{A}R{R}"


# ── LOGIN ──────────────────────────────────────────────────────────────────────

def _accept_cookies(page):
    """Aceita cookies se o dialóg estiver presente."""
    try:
        btn = page.get_by_role("button", name=re.compile(r"Aceitar", re.I))
        btn.first.click(timeout=3_000)
    except PwTimeout:
        pass


def login(page):
    """Faz login no portal B2B da Cantu via modal de autenticação."""
    page.goto(BASE, wait_until="domcontentloaded")
    _accept_cookies(page)

    # Verifica se sessão já está ativa
    if "Olá," in page.content():
        print("[login] sessão ativa", file=sys.stderr)
        return

    # Navega para listagem para ter "Ver preço" disponível
    page.goto(
        f"{BASE}/pneus?&title=175%2F70R14&page=1&pageSize=20&sortBy=LowestPrice",
        wait_until="domcontentloaded",
    )
    _accept_cookies(page)

    # Clica "Ver preço" para disparar modal de login
    try:
        page.get_by_role("button", name="Ver preço").first.click(timeout=8_000)
    except PwTimeout:
        if "Olá," in page.content():
            print("[login] já logado", file=sys.stderr)
            return
        raise

    # Aguarda modal aparecer
    page.wait_for_selector("input[placeholder*='email'], input[type='email']", timeout=8_000)

    page.get_by_role("textbox", name=re.compile("e-?mail", re.I)).fill(EMAIL)
    page.get_by_role("textbox", name=re.compile(r"\*+|senha", re.I)).fill(PASSWORD)
    page.get_by_role("button", name="Entrar", exact=True).click()

    page.wait_for_function(
        "() => document.body.innerText.includes('Olá,')",
        timeout=15_000,
    )
    print("[login] OK", file=sys.stderr)


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, title: str) -> list[dict]:
    """Retorna produtos em estoque com preço Pix, ordenados do mais barato."""
    url = (
        f"{BASE}/pneus?&title={quote(title)}"
        f"&page=1&pageSize=20&sortBy=LowestPrice"
    )
    # networkidle aguarda as chamadas de API de preços completarem
    page.goto(url, wait_until="networkidle", timeout=30_000)

    try:
        page.wait_for_selector('img[alt^="Imagen do produto "]', timeout=5_000)
    except PwTimeout:
        return []

    raw = page.evaluate("""() => {
        const products = [];
        document.querySelectorAll('img[alt^="Imagen do produto "]').forEach(img => {
            const name = img.alt.replace('Imagen do produto ', '');

            // Sobe até encontrar o card: cursor:pointer que contém h4 de preço
            let card = img.parentElement;
            while (card && !(window.getComputedStyle(card).cursor === 'pointer' && card.querySelector('h4'))) {
                card = card.parentElement;
            }
            if (!card) return;

            const h4 = card.querySelector('h4');
            const hasSemEstoque = Array.from(card.querySelectorAll('p'))
                .some(p => p.textContent.trim().toLowerCase().includes('sem estoque'));

            products.push({
                name,
                pixText: h4 ? h4.textContent.trim() : null,
                outOfStock: hasSemEstoque && !h4
            });
        });
        return products;
    }""")

    items = []
    for d in raw:
        if d["outOfStock"]:
            continue
        preco = parse_price(d["pixText"])
        if preco is None:
            continue
        items.append({
            "nome":     d["name"],
            "marca":    extract_brand(d["name"]),
            "preco_un": preco,
        })

    items.sort(key=lambda x: x["preco_un"])
    return items


# ── PÁGINA DO PRODUTO ──────────────────────────────────────────────────────────

def get_product_specs(page, nome: str) -> dict:
    """Navega para a página do produto e extrai specs da aba 'Informações técnicas'."""
    slug = name_to_slug(nome)
    url  = f"{BASE}/{slug}"
    specs: dict = {
        "treadwear":    None,
        "tipo_terreno": None,
        "ic":           None,
        "iv":           None,
        "url":          url,
    }

    try:
        page.goto(url, wait_until="domcontentloaded")

        # Verifica se chegou na página certa (h1 deve conter parte do nome)
        try:
            h1 = page.locator("h1").first.inner_text(timeout=3_000)
            if not any(w.lower() in h1.lower()
                       for w in nome.split()[:3] if len(w) > 3):
                print(f"  ! slug errado → {url} (h1: {h1[:60]})", file=sys.stderr)
                return specs
        except PwTimeout:
            pass

        # Clica na aba de especificações técnicas
        page.get_by_role("tab", name="Informações técnicas").click(timeout=4_000)

        table_data: dict = page.evaluate("""() => {
            const rows = {};
            document.querySelectorAll('table tr').forEach(row => {
                const th = row.querySelector('th');
                const td = row.querySelector('td');
                if (th && td) rows[th.textContent.trim()] = td.textContent.trim();
            });
            return rows;
        }""")

        # Treadwear: "Código Utqg" → "420AB" → 420
        utqg = table_data.get("Código Utqg", "")
        m = re.search(r"(\d+)", utqg)
        if m:
            specs["treadwear"] = int(m.group(1))

        # Tipo de terreno: "AT", "HT", "MT", etc.
        tt = table_data.get("Tipo de Terreno", "").strip()
        if tt:
            specs["tipo_terreno"] = tt.upper()

        # IC: "Índice de peso" → "92 - 630 kg, 92" → 92
        ip = table_data.get("Índice de peso", "")
        m = re.search(r"^(\d+)", ip)
        if m:
            specs["ic"] = int(m.group(1))

        # IV: "Índice de velocidade" → "H - 210 km/h, H" → "H"
        iv_raw = table_data.get("Índice de velocidade", "")
        m = re.search(r"^([A-Z]+)", iv_raw)
        if m:
            specs["iv"] = m.group(1)

    except PwTimeout:
        pass
    except Exception as e:
        print(f"  ! specs error ({nome[:40]}): {e}", file=sys.stderr)

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

    title = build_title(cfg)
    print(f"\n[item {item_n:02}] busca Cantu: '{title}'", file=sys.stderr)

    candidates = scrape_listing(page, title)
    print(f"[item {item_n:02}] {len(candidates)} produto(s) em estoque", file=sys.stderr)

    results = []
    checked = 0

    for c in candidates:
        if checked >= MAX_CHECK:
            break

        nome = c["nome"]

        # ── Filtros rápidos pelo nome ───────────────────────────────────────

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

        # ── Visita ficha técnica ────────────────────────────────────────────

        specs = get_product_specs(page, nome)
        obs_list: list[str] = []

        # Treadwear
        tw = specs["treadwear"]
        if tw_min > 0:
            if tw is None:
                obs_list.append(f"Treadwear não disponível na ficha (exige ≥{tw_min})")
            elif tw < tw_min:
                print(f"  ✗ Treadwear {tw}<{tw_min}  {nome}", file=sys.stderr)
                checked += 1
                continue  # falha confirmada

        # Tipo de terreno (AT exigido)
        if padrao_piso and padrao_piso.upper() == "AT":
            tt = specs["tipo_terreno"]
            if piso_nome is True:
                pass  # nome já confirma AT
            elif tt is None:
                if piso_nome is None:
                    obs_list.append("Tipo de terreno não disponível na ficha (exige AT)")
                # else piso_nome=True: já confirmado pelo nome
            elif tt not in ("AT", "MT", "AW"):
                print(f"  ✗ Terreno '{tt}' ≠ AT  {nome}", file=sys.stderr)
                checked += 1
                continue  # falha confirmada

        # IC confirmado pela ficha
        ic = specs["ic"] if specs["ic"] is not None else ic_nome
        if ic is not None and ic_min and ic < ic_min:
            print(f"  ✗ IC {ic}<{ic_min} (ficha)  {nome}", file=sys.stderr)
            checked += 1
            continue

        # IV confirmado pela ficha
        iv = specs["iv"] if specs["iv"] is not None else iv_nome
        if iv and iv_min and not iv_ok(iv, iv_min):
            print(f"  ✗ IV {iv}<{iv_min} (ficha)  {nome}", file=sys.stderr)
            checked += 1
            continue

        # Construção: NUNCA disponível na Cantu
        if construcao_req:
            obs_list.append(
                f"Construção ({construcao_req}) não publicada na Cantu — confirmar com fornecedor"
            )

        # Número de lonas: NUNCA disponível na Cantu
        if min_lonas:
            obs_list.append(
                f"Nº de lonas não publicado na Cantu (exige ≥{min_lonas}) — confirmar com fornecedor"
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
            "apto":         apto,
            "obs":          obs_str,
            "qtde":         cfg.get("qtde", 1),
            "url":          specs["url"],
            "fornecedor":   "Cantu",
        })

        flag = "✓" if apto else "⚠"
        print(
            f"  {flag} {nome}  R${c['preco_un']:.2f}"
            + (f"  [{obs_str}]" if obs_str else ""),
            file=sys.stderr,
        )
        checked += 1

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python cantu_scraper.py items.json [results.json]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        items_cfg = json.load(f)

    all_results: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()
        page.set_extra_http_headers({"Accept-Language": "pt-BR,pt;q=0.9"})
        login(page)

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
