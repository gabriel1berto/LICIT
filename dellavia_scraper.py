#!/usr/bin/env python3
"""
dellavia_scraper.py  —  Busca preços de pneus na Della Via Pneus
Uso   : python dellavia_scraper.py items.json [results.json]
Output: JSON com produtos aprovados por item, ordenados por preço

Sem login (testado 15/jul/26): a credencial do Notion loga sem erro, mas o preço
não muda autenticado nem logado — não existe tier de atacado self-service no site.
"Atacado" é landing page que só direciona pra telefone/WhatsApp. Preço aqui é
varejo público (com desconto PIX já aplicado), usado como teto de referência até
o desconto real de atacado ser confirmado por contato manual.

Critérios validados por item (via items.json) — mesmo schema dos outros scrapers:
  construcao    — "nylon" | "poliester" | "aco" | "" (ignora) — Della Via não expõe
                  esse dado na ficha técnica, sempre vira nota em obs, nunca reprova
  min_lonas     — mínimo de lonas (0 = ignora) — idem, não exposto
  min_treadwear — UTQG treadwear mínimo (0 = ignora) — exposto (gráfico DURABILIDADE)
  min_ic        — índice de carga mínimo (0 = ignora)
  min_iv        — índice de velocidade mínimo ("" = ignora)
  padrao_piso   — "AT" exige All-Terrain pelo nome ("" = ignora)

INMETRO (combustível/aderência, selo na ficha técnica) é exposto pela Della Via
— não existe critério pra isso no items.json (schema padrão não tem esse campo),
por isso entra só como nota informativa em "obs" quando disponível.
"""

import json, re, sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE = "https://www.dellavia.com.br"
MAX_CHECK = 3
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
    """'Pneu <Marca> <medida>...' — marca é a palavra logo após 'Pneu'.
    Nome vem TUDO MAIÚSCULO no headless (achado real 15/jul/26, diferente do
    Chrome usado pra investigar ao vivo) — regex tem que ser case-insensitive."""
    m = re.match(r"Pneu\s+([A-Za-zÀ-ú]+)\s+\d{2,3}/\d{2,3}", nome, re.I)
    return m.group(1).title() if m else ""


def piso_ok(nome: str, padrao: str) -> bool:
    if not padrao:
        return True
    if padrao.upper() == "AT":
        if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN|OFF[\s\-]?ROAD", nome, re.I):
            return True
        return False  # sem indicação de AT = reprova (modo estrito, igual Bransales)
    return True


# ── URL DE LISTAGEM ────────────────────────────────────────────────────────────

def build_url(item: dict) -> str:
    """Sintaxe confirmada ao vivo 15/jul/26: /{largura}/{perfil}/{aro}/?_q=pneu&...
    Sem variante pra medida sem perfil (tipo '1000 R20') — Della Via só vende
    passeio/SUV/van (Bridgestone/Firestone), catálogo não tem OTR/agrícola."""
    L, P, R = item["largura"], item["altura"], item["aro"]
    return f"{BASE}/{L}/{P}/{R}/?_q=pneu&fuzzy=0&initialMap=ft&map=largura,perfil,aros,ft&operator=and"


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, url: str) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded")
    try:
        # Esperar o 1º link "a[href$='/p']" é uma race — ele aparece antes dos
        # outros produtos hidratarem (achado real 15/jul/26: só 1 de 3 vinha).
        # O contador "X Produtos" só renderiza depois que a listagem inteira
        # está montada, então esperar por ele garante todos os cards prontos.
        page.wait_for_selector("text=/\\d+ Produto/", timeout=8_000)
        # Preço é outra hidratação, ainda mais tardia (achado real: ~2s depois do
        # contador) — sem isso, todo item vinha com price_el=None e o item inteiro
        # era descartado silenciosamente. Se ficar vazio de verdade (item sem
        # nenhum produto em estoque na medida), o timeout aqui é esperado, segue.
        try:
            page.wait_for_selector('[class*="bestPrice"]', timeout=5_000)
        except PwTimeout:
            pass
    except PwTimeout:
        return []

    items = []
    for a in page.query_selector_all('a[href$="/p"]'):
        if a.query_selector("button[disabled]"):
            continue  # "Indisponível" — sem estoque real, confirmado pelo próprio site
        h3 = a.query_selector("h3")
        if not h3:
            continue
        # .title() normaliza o TUDO-MAIÚSCULO do headless pra ficar legível na
        # planilha, igual ao case dos outros 3 fornecedores.
        name = h3.inner_text().strip().title()
        price_el = a.query_selector('[class*="product-price--bestPrice"]')
        if not price_el:
            continue
        pr = parse_price(price_el.inner_text())
        if not pr:
            continue
        # URL absoluta — convenção dos outros fornecedores no Supabase (conferido
        # 15/jul/26: Bransales grava full URL, não path relativo).
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
    """Visita a página do produto e extrai treadwear/INMETRO via classe CSS
    (dellavia-store-theme-5-x-...) — confirmado ao vivo 15/jul/26, não regex em
    texto solto (o dump de innerText embaralha os números do gráfico UTQG com os
    rótulos de escala do eixo). construcao/num_lonas não são expostos pela Della
    Via — ficam sempre None, mesmo tratamento "não disponível" do Bransales."""
    full_url = url if url.startswith("http") else f"{BASE}{url}"
    page.goto(full_url, wait_until="domcontentloaded")
    specs = {"treadwear": None, "construcao": None, "num_lonas": None, "inmetro": None, "marca": None}
    try:
        # Marca real (achado real 15/jul/26): pra linha "Fuzion" a marca oficial na
        # ficha é Bridgestone — a 1ª palavra depois de "Pneu" no nome do produto é
        # o MODELO ("Fuzion"), não a marca. Ficha técnica tem o campo certo.
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
    print(f"[item {item_n}] {len(candidates)} com preço", file=sys.stderr)

    results = []
    checked = 0
    for c in candidates:
        if checked >= MAX_CHECK:
            break

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

        # Sempre visita a página do produto (diferente do Bransales) — INMETRO só
        # sai daqui, não da listagem, e não custa uma chamada extra (site sem WAF).
        specs = get_product_specs(page, c["url"])

        obs_list = []

        tw = specs["treadwear"]
        if tw_min > 0:
            if tw is None:
                obs_list.append(f"Treadwear não disponível na página (exige ≥{tw_min})")
            elif tw < tw_min:
                print(f"  ✗ Treadwear {tw}<{tw_min}  {nome}", file=sys.stderr)
                checked += 1
                continue

        if construcao_req:
            obs_list.append(f"Construção ({construcao_req}) não verificável — Della Via não expõe esse dado")

        if min_lonas:
            obs_list.append(f"Nº de lonas não verificável — Della Via não expõe esse dado (exige ≥{min_lonas})")

        obs_str = " | ".join(obs_list)
        # apto=False aqui é sempre "produto real, critério não confirmado" (Della Via
        # não expõe construção/lonas) — nunca "sem estoque" (isso já foi filtrado
        # antes, via button[disabled] em scrape_listing). Mesma distinção do bug
        # corrigido em preencher_planilha_precificacao.py (linha_para_item()).
        apto = len(obs_list) == 0
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
        checked += 1

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python dellavia_scraper.py items.json [results.json]", file=sys.stderr)
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
        print(f"\n[done] {len(all_results)} produtos aprovados → {sys.argv[2]}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
