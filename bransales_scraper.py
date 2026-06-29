#!/usr/bin/env python3
"""
bransales_scraper.py  —  Busca preços de pneus na Bransales
Uso   : python bransales_scraper.py items.json [results.json]
Output: JSON com produtos aprovados por item, ordenados por preço

Critérios validados por item (via items.json):
  construcao    — "nylon" | "poliester" | "aco" | "" (ignora)
  min_lonas     — mínimo de lonas (0 = ignora)
  min_treadwear — UTQG treadwear mínimo (0 = ignora)
  min_ic        — índice de carga mínimo (0 = ignora)
  min_iv        — índice de velocidade mínimo ("" = ignora)
  padrao_piso   — "AT" exige All-Terrain pelo nome ("" = ignora)
"""

import json, re, sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

EMAIL    = "ghumberto.eng@gmail.com"
PASSWORD = "***REMOVIDO***"
BASE     = "https://atacado.bransales.com.br"
MAX_CHECK = 3

IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUVWHY")}


# ── PARSERS DE LISTAGEM ────────────────────────────────────────────────────────

def parse_price(text: str):
    """Retorna preço à vista: maior dos preços cheios (ignora parcelas ~1/10 do maior)."""
    vals = [float(v.replace(".", "").replace(",", "."))
            for v in re.findall(r"\d{1,4}(?:\.\d{3})*,\d{2}", text)]
    if not vals:
        return None
    threshold = max(vals) / 5
    full = [v for v in vals if v >= threshold]
    return min(full) if full else None


def iv_ok(iv_produto: str, iv_min: str) -> bool:
    if not iv_min:
        return True
    return IV_ORDER.get(iv_produto.upper(), -1) >= IV_ORDER.get(iv_min.upper(), 0)


def parse_ic_iv(nome: str):
    m = re.search(r"\b(\d{2,3})(?:/\d{2,3})?([A-Z])\b", nome)
    if m:
        return int(m.group(1)), m.group(2).upper()
    return None, None


def lonas_from_name(nome: str):
    m = re.search(r"(\d+)\s*[Ll]onas?", nome)
    return int(m.group(1)) if m else None


def extract_brand(nome: str) -> str:
    """Extrai marca/fabricante do nome do produto Bransales.

    Padrão 1 – "Pneu Aro NN[C] MARCA spec...": ex. "Pneu Aro 16 Roadking 225/75R16..."
    Padrão 2 – all-caps "PNEU spec MODEL MARCA": ex. "PNEU 215/65R16 98H FM316 FIREMAX"
    """
    # Padrão 1: Pneu Aro NN[C] MARCA ...medida...
    m = re.match(
        r"Pneu Aro \d+[cC]?\s+([A-Za-zÀ-ú][A-Za-zÀ-ú\s]*?)\s+\d{2,3}[/\d]",
        nome, re.I,
    )
    if m:
        brand = m.group(1).strip()
        if re.search(r"sunset", brand, re.I):      return "Sunset Tire"
        if re.search(r"general\s*tire", brand, re.I): return "General Tire"
        return brand.title()
    # Padrão 2: linha all-caps → última palavra é a marca
    if nome.split()[0].isupper():
        return nome.split()[-1].title()
    return ""


def piso_ok(nome: str, padrao: str) -> bool:
    """AT exigido: aceita A/T, AT, All-Terrain, M/T, MT. Rejeita H/T, Highway."""
    if not padrao:
        return True
    if padrao.upper() == "AT":
        if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN|OFF[\s\-]?ROAD", nome, re.I):
            return True
        if re.search(r"\bH[/\-]?T\b|HIGHWAY|TOURING\b", nome, re.I):
            return False
        return False  # sem indicação de AT = reprova (modo estrito)
    return True


# ── PÁGINA DO PRODUTO ──────────────────────────────────────────────────────────

def get_product_specs(page, url: str) -> dict:
    """Visita a página do produto e extrai treadwear, construção e num_lonas."""
    page.goto(url.split("?")[0], wait_until="domcontentloaded")
    specs = {"treadwear": None, "construcao": None, "num_lonas": None}
    try:
        btn = page.get_by_role("button", name=re.compile("Informações Técnicas", re.I))
        btn.click(timeout=4_000)
        txt = page.locator("main").inner_text(timeout=5_000)

        # Treadwear (UTQG)
        m = re.search(r"Treadwear\)[\s:]*(\d+)", txt, re.I)
        if m:
            specs["treadwear"] = int(m.group(1))

        # Construção da carcaça
        if re.search(r"n[áa][iy]lon|nylon", txt, re.I):
            specs["construcao"] = "nylon"
        elif re.search(r"poli[eé]ster", txt, re.I):
            specs["construcao"] = "poliester"
        elif re.search(r"\ba[çc]o\b|steel[\s\-]belt", txt, re.I):
            specs["construcao"] = "aco"

        # Número de lonas
        m = re.search(r"(\d+)\s*[Ll]onas?", txt)
        if m:
            specs["num_lonas"] = int(m.group(1))

    except PwTimeout:
        pass
    return specs


# ── LOGIN ──────────────────────────────────────────────────────────────────────

def login(page):
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.get_by_placeholder(re.compile("email|CPF", re.I)).first.fill(EMAIL)
    page.get_by_role("button", name="Continuar").click()
    page.get_by_placeholder(re.compile("senha", re.I)).fill(PASSWORD)
    page.get_by_role("button", name="Continuar").click()
    page.wait_for_url("**/minha-conta**", timeout=15_000)
    print("[login] OK", file=sys.stderr)


# ── URL DE LISTAGEM ────────────────────────────────────────────────────────────

def build_url(item: dict) -> str | None:
    cat = item.get("categoria", "passeio")
    L, A, R = item["largura"], item.get("altura"), item["aro"]
    if cat == "agricola":
        return f"{BASE}/pneus/Secao-{L},Aro-{R}/"
    if cat == "camara":
        return f"{BASE}/camaras/Secao-{L},Aro-{R}/"
    return f"{BASE}/pneus/Largura-{L},Altura-{A},Aro-{R}/"


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, url: str) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("a[href*='/pneu-'], a[href*='/camara-']", timeout=8_000)
    except PwTimeout:
        return []

    items = []
    for a in page.query_selector_all("a[href*='/pneu-'], a[href*='/camara-']"):
        txt = a.inner_text()
        if "indisponível" in txt.lower():
            continue
        if re.search(r"câmara\s*(?:de\s*)?ar|camara\s*(?:de\s*)?ar", txt, re.I):
            continue
        pr = parse_price(txt)
        if not pr:
            continue
        h3 = a.query_selector("h3")
        name = (h3.inner_text() if h3 else txt.split("\n")[0]).strip()
        brand = extract_brand(name)
        items.append({
            "nome":     name,
            "marca":    brand,
            "preco_un": pr,
            "url":      a.get_attribute("href"),
        })

    items.sort(key=lambda x: x["preco_un"])
    return items


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
    print(f"[item {item_n}] {len(candidates)} com preço", file=sys.stderr)

    results = []
    checked = 0
    for c in candidates:
        if checked >= MAX_CHECK:
            break

        nome = c["nome"]

        # ── Filtros pelo nome (sem visitar página) ──────────────────────────

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

        lonas_nome = lonas_from_name(nome)
        if min_lonas and lonas_nome is not None and lonas_nome < min_lonas:
            print(f"  ✗ {lonas_nome}L<{min_lonas}  {nome}", file=sys.stderr)
            continue

        # ── Visita página quando necessário ────────────────────────────────

        need_page = tw_min > 0 or construcao_req or (min_lonas > 0 and lonas_nome is None)
        specs = {"treadwear": None, "construcao": None, "num_lonas": lonas_nome}

        if need_page:
            specs = get_product_specs(page, c["url"])
            if specs["num_lonas"] is None and lonas_nome is not None:
                specs["num_lonas"] = lonas_nome

        obs_list = []

        # Treadwear: None = não disponível na página → anota, não reprova
        tw = specs["treadwear"]
        if tw_min > 0:
            if tw is None:
                obs_list.append(f"Treadwear não disponível na página (exige ≥{tw_min})")
            elif tw < tw_min:
                print(f"  ✗ Treadwear {tw}<{tw_min}  {nome}", file=sys.stderr)
                checked += 1
                continue  # falha confirmada → rejeita

        # Construção: None = não disponível → anota; valor errado → rejeita
        if construcao_req:
            if specs["construcao"] is None:
                obs_list.append(f"Construção ({construcao_req}) não verificável na página")
            elif specs["construcao"] != construcao_req:
                print(f"  ✗ construção '{specs['construcao']}' ≠ '{construcao_req}'  {nome}", file=sys.stderr)
                checked += 1
                continue  # falha confirmada → rejeita

        # Lonas: None = não disponível → anota; abaixo do mínimo → rejeita
        num_lonas = specs["num_lonas"]
        if min_lonas:
            if num_lonas is None:
                obs_list.append(f"Nº de lonas não disponível na página (exige ≥{min_lonas})")
            elif num_lonas < min_lonas:
                print(f"  ✗ {num_lonas}L<{min_lonas}  {nome}", file=sys.stderr)
                checked += 1
                continue  # falha confirmada → rejeita

        obs_str = " | ".join(obs_list)
        apto    = len(obs_list) == 0
        results.append({
            "item":       item_n,
            "descricao":  cfg["descricao"],
            "medida":     cfg["descricao"].split(" ", 3)[-1],
            "nome":       nome,
            "marca":      c["marca"],
            "preco_un":   c["preco_un"],
            "ic":         ic,
            "iv":         iv,
            "treadwear":  tw,
            "construcao": specs["construcao"],
            "num_lonas":  num_lonas,
            "apto":       apto,
            "obs":        obs_str,
            "qtde":       cfg.get("qtde", 1),
            "url":        c["url"],
            "fornecedor": "Bransales",
        })
        flag = "✓" if apto else "⚠"
        print(f"  {flag} {nome}  R${c['preco_un']:.2f}"
              + (f"  [{obs_str}]" if obs_str else ""), file=sys.stderr)
        checked += 1

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python bransales_scraper.py items.json [results.json]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        items_cfg = json.load(f)

    all_results = []

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
        print(f"\n[done] {len(all_results)} produtos aprovados → {sys.argv[2]}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
