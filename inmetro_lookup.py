#!/usr/bin/env python3
"""
inmetro_lookup.py — Busca certificado INMETRO (Portaria 379/2021, pneus novos)
no ProdCert (inmetro.gov.br/prodcert), banco oficial de produtos certificados.

Por que existe: site dos 4 distribuidores cadastrados não publica nº de registro
por produto (Bransales/Cantu/GP às vezes têm um número solto no texto, Green
Pneus só tem selo genérico de loja — confirmado manualmente 17/jul/2026, ver
CLAUDE.md §17). ProdCert é a fonte oficial — usada como verificação adicional,
não substitui o scraper de preço.

Uso:
  python inmetro_lookup.py produtos.json [resultado.json]

produtos.json: lista de {"marca": str, "largura": str, "perfil": str, "aro": str}
(mesmos campos usados em items_X.json pros scrapers de cotação — largura/perfil/aro
já existem lá). Saída: mesma lista + campo "inmetro" com
{modelo, certificador, numero_certificado, emissao, validade, status} ou None
se não achou nenhum produto da marca com a medida exata no ProdCert (marca não
cadastrada, medida não certificada, ou nome da marca não bate com o cadastro —
não tenta fuzzy match, evita associar certificado errado a um produto).

ProdCert é um app ASP antigo (funções JS Pagina()/ListaCertificado() fazem
postback da página inteira, sem URL própria por resultado) — não existe link
fixo pra salvar por produto, só o Nº do Certificado, que é reproduzível
manualmente em inmetro.gov.br/prodcert/produtos/busca.asp.
"""

import json, re, sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BUSCA_URL = "http://www.inmetro.gov.br/prodcert/Produtos/busca.asp"
CLASSE_PNEUS_NOVOS = "Pneus Novos - Portaria Inmetro nº 544/2012 / Portaria Inmetro nº 379/2021"
MAX_PAGINAS = 15  # trava de segurança, marca muito genérica pode ter muita página


def carregar_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def buscar_certificado(page, marca: str, largura: str, perfil: str, aro: str) -> dict | None:
    medida_regex = re.compile(rf"{re.escape(largura)}\s*/\s*{re.escape(perfil)}\s*R\s*{re.escape(aro)}\b", re.I)

    page.goto(BUSCA_URL, wait_until="load", timeout=60000)
    page.wait_for_selector("#classe_produto", timeout=60000)
    page.select_option("#classe_produto", CLASSE_PNEUS_NOVOS)
    page.fill("#produto", marca)
    with page.expect_navigation(wait_until="load", timeout=60000):
        page.click('input[value="Buscar"]', no_wait_after=True)

    total_paginas = 1
    onclicks = page.eval_on_selector_all("span[onclick^='Pagina']", "els => els.map(e => e.getAttribute('onclick'))")
    for oc in onclicks:
        m = re.search(r"Pagina\((\d+),1,(\d+)\)", oc or "")
        if m:
            total_paginas = max(total_paginas, int(m.group(2)))

    for pagina in range(1, min(total_paginas, MAX_PAGINAS) + 1):
        if pagina > 1:
            with page.expect_navigation(wait_until="load", timeout=90000):
                page.evaluate(f"Pagina({pagina},1,{total_paginas})")

        linhas = page.eval_on_selector_all(
            "td.listagem",
            """cells => {
                const out = [];
                for (let i = 0; i + 3 < cells.length; i += 4) {
                    out.push({marca: cells[i].innerText.trim(), modelo: cells[i+1].innerText.trim(),
                              importado: cells[i+2].innerText.trim(), desc: cells[i+3].innerText.trim()});
                }
                return out;
            }""",
        )
        achado = next((l for l in linhas if medida_regex.search(l["desc"])), None)
        if not achado:
            continue

        with page.expect_navigation(wait_until="load", timeout=60000):
            page.evaluate(
                "([marca, modelo, importado]) => ListaCertificado(marca, modelo, importado)",
                [achado["marca"], achado["modelo"], achado["importado"]],
            )
        texto = page.locator("strong").first.inner_text()
        cert = {"modelo": achado["modelo"], "descricao_prodcert": achado["desc"]}
        for campo, rotulo in [
            ("certificador", "Certificador"), ("numero_certificado", "Nº Certificado"),
            ("emissao", "Emissão"), ("validade", "Validade"), ("status", "Status do Certificado"),
        ]:
            m = re.search(rf"{rotulo}:\s*([^\n]+?)(?:\s{{2,}}|$)", texto)
            cert[campo] = m.group(1).strip() if m else None
        return cert

    return None


def main():
    if len(sys.argv) < 2:
        print("Uso: python inmetro_lookup.py produtos.json [resultado.json]", file=sys.stderr)
        sys.exit(1)

    produtos = carregar_json(sys.argv[1])
    saida = sys.argv[2] if len(sys.argv) > 2 else "resultado_inmetro.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for produto in produtos:
            cert = buscar_certificado(page, produto["marca"], produto["largura"], produto["perfil"], produto["aro"])
            produto["inmetro"] = cert
            status = cert["numero_certificado"] if cert else "não achado"
            print(f"  [{produto['marca']}] {produto['largura']}/{produto['perfil']}R{produto['aro']} -> {status}", file=sys.stderr)
        browser.close()

    with open(saida, "w", encoding="utf-8") as f:
        json.dump(produtos, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {saida}", file=sys.stderr)


if __name__ == "__main__":
    main()
