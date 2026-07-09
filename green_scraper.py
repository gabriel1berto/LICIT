#!/usr/bin/env python3
"""
green_scraper.py — Busca preços de pneus no PneuGreen (pneugreen.com.br)
Uso   : python green_scraper.py items_cantagalo.json [results_cantagalo_green.json]
Output: JSON com produtos por item, ordenados por preço

Autenticação: login via UI (e-mail + senha em 2 passos, sem reCAPTCHA).
Credenciais: GREEN_EMAIL / GREEN_PASSWORD no .env

URL de busca: /loja/busca.php?loja=1063462&palavra_busca={MEDIDA}
Formato de medida: "205/75 R16C" (slash, espaço antes do R, uppercase, sufixo C se houver)

Specs disponíveis na ficha de produto:
  IC  → "Índice de Peso"    → primeiro número (ex: "110 - 1060 kg" → 110)
  IV  → "Índice Velocidade" → letra inicial  (ex: "R - 170 Km/h"  → R)
  Construção → "Tipo de construção"  (RADIAL/DIAGONAL)
  Marca      → "Marca" da tabela
  Treadwear  → NÃO publicado → obs automática quando exigido
  INMETRO    → NÃO publicado
  Nº lonas   → NÃO publicado → obs automática quando exigido
"""

import json, os, re, sys
from urllib.parse import quote
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

load_dotenv()
BASE      = "https://www.pneugreen.com.br"
LOJA_ID   = "1063462"
LOGIN_EMAIL = os.environ["GREEN_EMAIL"]
LOGIN_PASS  = os.environ["GREEN_PASSWORD"]
MAX_CHECK   = 3

IV_ORDER = {c: i for i, c in enumerate("LMNPQRSTUHVWY")}


# ── PARSERS ────────────────────────────────────────────────────────────────────

def parse_price(text: str) -> float | None:
    """Extrai primeiro preço 'R$ X.XXX,XX' do texto."""
    m = re.search(r"R\$\s*([\d.]+,\d{2})", text or "")
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def iv_ok(iv_produto: str, iv_min: str) -> bool:
    if not iv_min:
        return True
    return IV_ORDER.get(iv_produto.upper(), -1) >= IV_ORDER.get(iv_min.upper(), 0)


def parse_ic_iv_nome(nome: str):
    """Fallback: extrai IC e IV do nome quando specs não disponíveis."""
    m = re.search(r"\b(\d{2,3})(?:/\d{2,3})?([A-Z])\b", nome)
    if m:
        return int(m.group(1)), m.group(2).upper()
    return None, None


def piso_ok_nome(nome: str, padrao: str) -> bool | None:
    if not padrao or padrao.upper() != "AT":
        return True
    if re.search(r"\bA[/\-]?T\b|ALL[\s\-]?TERRAIN|M[/\-]?T\b|MUD[\s\-]?TERRAIN", nome, re.I):
        return True
    if re.search(r"\bH[/\-]?T\b|HIGHWAY|TOURING\b", nome, re.I):
        return False
    return None


def build_medida_green(cfg: dict) -> str:
    """Formato PneuGreen: '205/75 R16C' (passeio/caminhão) ou '11.2-24' (agrícola, sem espaço/R)."""
    if cfg.get("categoria") == "agricola":
        return f"{cfg['largura']}-{cfg['aro']}"
    return f"{cfg['largura']}/{cfg['altura']} R{cfg['aro'].upper()}"


# ── LOGIN ──────────────────────────────────────────────────────────────────────

def login(page) -> bool:
    """Faz login em 2 passos no PneuGreen. Retorna True se bem-sucedido."""
    page.goto(f"{BASE}/my-account/login", wait_until="networkidle", timeout=45_000)
    # Passo 1: clicar em "Entrar" para revelar o campo de e-mail
    page.click('button:has-text("Entrar"), .btn:has-text("Entrar")')
    page.wait_for_selector('#input-email', state="visible", timeout=5_000)
    page.fill('#input-email', LOGIN_EMAIL)
    page.keyboard.press('Enter')
    # Passo 2: campo de senha
    page.wait_for_selector('#input-password', state="visible", timeout=5_000)
    page.fill('#input-password', LOGIN_PASS)
    page.keyboard.press('Enter')
    page.wait_for_load_state("domcontentloaded", timeout=10_000)
    content = page.content().lower()
    return "minha conta" in content and "sair" in content


# ── SCRAPE DA LISTAGEM ─────────────────────────────────────────────────────────

def scrape_listing(page, medida: str) -> list[dict]:
    """Retorna pneus individuais em estoque, ordenados do mais barato."""
    url = f"{BASE}/loja/busca.php?loja={LOJA_ID}&palavra_busca={quote(medida)}"
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    try:
        page.wait_for_selector('li.item', timeout=8_000)
    except PwTimeout:
        print(f"  [sem resultados] nenhum li.item encontrado", file=sys.stderr)
        return []

    raw = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('li.item')).map(el => {
            const nameEl = el.querySelector('h2, h3, [class*="name"]');
            const name   = nameEl ? nameEl.innerText.trim() : el.innerText.slice(0, 80);
            const link   = el.querySelector('a[href]')?.href || '';
            const text   = el.innerText;
            // Primeiro preço no texto
            const priceMatch = text.match(/R\\$\\s*([\\d.]+,\\d{2})/);
            const priceText  = priceMatch ? priceMatch[0] : null;
            const outOfStock = /esgotado|indispon|sem estoque/i.test(text);
            const isKit      = /^kit\\b/i.test(name.trim());
            return { name, link, priceText, outOfStock, isKit };
        });
    }""")

    items = []
    for r in raw:
        if r["isKit"]:
            continue
        if r["outOfStock"]:
            print(f"  [esgotado] {r['name']}", file=sys.stderr)
            continue
        preco = parse_price(r["priceText"])
        if preco is None:
            print(f"  [sem preço] {r['name']}", file=sys.stderr)
            continue
        items.append({
            "nome":     r["name"],
            "preco_un": preco,
            "url":      r["link"],
        })

    items.sort(key=lambda x: x["preco_un"])
    return items


# ── PÁGINA DO PRODUTO ──────────────────────────────────────────────────────────

def get_product_specs(page, url: str) -> dict:
    specs = {
        "marca":      None,
        "ic":         None,
        "iv":         None,
        "construcao": None,
        "treadwear":  None,
        "inmetro":    None,
    }

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20_000)

        table_data: dict = page.evaluate("""() => {
            const rows = {};
            document.querySelectorAll('table tr').forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 2) {
                    const key = cells[0].innerText.trim();
                    const val = cells[1].innerText.trim();
                    if (key) rows[key] = val;
                }
            });
            return rows;
        }""")

        # Marca
        specs["marca"] = table_data.get("Marca", "").strip().title() or None

        # IC: "Índice de Peso" → "110 - 1060 kg" → 110
        ic_raw = table_data.get("Índice de Peso", "")
        m = re.search(r"(\d+)", ic_raw)
        if m:
            specs["ic"] = int(m.group(1))

        # IV: "Índice Velocidade" → "R - 170 Km/h" → "R"
        iv_raw = table_data.get("Índice Velocidade", "")
        m = re.match(r"([A-Z]+)", iv_raw.strip())
        if m:
            specs["iv"] = m.group(1)

        # Construção
        const_raw = table_data.get("Tipo de construção", "").strip()
        if const_raw:
            specs["construcao"] = const_raw.lower()

    except PwTimeout:
        pass
    except Exception as e:
        print(f"  ! specs error: {e}", file=sys.stderr)

    return specs


# ── PROCESSAMENTO POR ITEM ─────────────────────────────────────────────────────

def process_item(page, cfg: dict) -> list[dict]:
    item_n         = cfg["item"]
    ic_min         = cfg.get("min_ic", 0)
    iv_min         = cfg.get("min_iv", "")
    tw_min         = cfg.get("min_treadwear", 0)
    construcao_req = cfg.get("construcao", "")
    min_lonas      = cfg.get("min_lonas", 0)
    padrao_piso    = cfg.get("padrao_piso", "")

    medida = build_medida_green(cfg)
    print(f"\n[item {item_n:02}] busca Green: '{medida}'", file=sys.stderr)

    candidates = scrape_listing(page, medida)
    print(f"[item {item_n:02}] {len(candidates)} produto(s) em estoque", file=sys.stderr)

    # Busca por medida mistura tipos de produto (pneu, câmara, roda) — filtra pelo tipo esperado.
    # Bug achado 09/jul/2026: condição estava invertida — só filtrava quando NÃO era câmara,
    # ou seja, buscando câmara de verdade aceitava qualquer coisa (pneu de estrada incluso).
    categoria = cfg.get("categoria", "")
    antes = len(candidates)
    if categoria == "camara":
        candidates = [c for c in candidates if re.search(r"c[âa]mara", c["nome"], re.I)]
        motivo = "não são câmara"
    else:
        candidates = [c for c in candidates if not re.search(r"c[âa]mara|\broda\b", c["nome"], re.I)]
        motivo = "câmara/roda"
    if len(candidates) < antes:
        print(f"  [filtro tipo] {antes - len(candidates)} produto(s) {motivo} descartado(s)", file=sys.stderr)

    if not candidates:
        return [{
            "item":         item_n,
            "descricao":    cfg["descricao"],
            "nome":         "— Sem estoque",
            "marca":        "",
            "preco_un":     None,
            "ic":           None,
            "iv":           None,
            "treadwear":    None,
            "construcao":   None,
            "inmetro":      None,
            "apto":         False,
            "obs":          "Nenhum produto disponível no PneuGreen",
            "qtde":         cfg.get("qtde", 1),
            "url":          "",
            "fornecedor":   "Green Pneus",
        }]

    results = []
    checked = 0

    for c in candidates:
        if checked >= MAX_CHECK:
            break

        nome = c["nome"]

        # Filtro rápido pelo nome
        ic_nome, iv_nome = parse_ic_iv_nome(nome)
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

        # Ficha técnica
        specs = get_product_specs(page, c["url"])
        obs_list: list[str] = []

        # IC
        ic = specs["ic"] if specs["ic"] is not None else ic_nome
        if ic is not None and ic_min and ic < ic_min:
            print(f"  ✗ IC {ic}<{ic_min} (ficha)  {nome}", file=sys.stderr)
            checked += 1
            continue

        # IV
        iv = specs["iv"] if specs["iv"] is not None else iv_nome
        if iv and iv_min and not iv_ok(iv, iv_min):
            print(f"  ✗ IV {iv}<{iv_min} (ficha)  {nome}", file=sys.stderr)
            checked += 1
            continue

        # Treadwear: PneuGreen não publica → obs quando exigido
        if tw_min > 0:
            obs_list.append(
                f"Treadwear não publicado no PneuGreen (exige ≥{tw_min}) — confirmar com fornecedor"
            )

        # Construção: site publica RADIAL/DIAGONAL mas não nylon/poliéster
        if construcao_req:
            gp_const = specs.get("construcao") or ""
            if not gp_const:
                obs_list.append(
                    f"Construção ({construcao_req}) não confirmada — confirmar com fornecedor"
                )

        # Lonas: não publicado
        if min_lonas:
            obs_list.append(
                f"Nº de lonas não publicado no PneuGreen (exige ≥{min_lonas}) — confirmar com fornecedor"
            )

        # Padrão de piso AT
        if padrao_piso and padrao_piso.upper() == "AT" and piso_nome is None:
            obs_list.append(
                "Padrão AT não confirmado pelo nome — verificar ficha do produto"
            )

        # Marca: usar da tabela de specs se disponível
        marca = specs["marca"] or ""
        if not marca:
            # fallback pelo nome: "PNEU ARO 16 FIRESTONE ..." → 4ª palavra
            parts = nome.upper().split()
            for i, p in enumerate(parts):
                if p == "ARO" and i + 2 < len(parts):
                    marca = parts[i + 2].title()
                    break
            if not marca:
                marca = parts[0].title() if parts else ""

        obs_str = " | ".join(obs_list)
        apto    = len(obs_list) == 0

        results.append({
            "item":         item_n,
            "descricao":    cfg["descricao"],
            "nome":         nome,
            "marca":        marca,
            "preco_un":     c["preco_un"],
            "ic":           ic,
            "iv":           iv,
            "treadwear":    None,
            "construcao":   specs.get("construcao"),
            "inmetro":      None,
            "apto":         apto,
            "obs":          obs_str,
            "qtde":         cfg.get("qtde", 1),
            "url":          c["url"],
            "fornecedor":   "Green Pneus",
        })

        flag = "✓" if apto else "⚠"
        print(
            f"  {flag} {nome}  R${c['preco_un']:.2f}"
            + (f"  [{obs_str[:80]}]" if obs_str else ""),
            file=sys.stderr,
        )
        # Retorna apenas o melhor (mais barato que passa os filtros)
        break

    return results


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("uso: python green_scraper.py items.json [results.json]", file=sys.stderr)
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

        print("[auth] Fazendo login no PneuGreen...", file=sys.stderr)
        logged_in = login(page)
        if not logged_in:
            print("ERRO: Login falhou. Verifique credenciais.", file=sys.stderr)
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
