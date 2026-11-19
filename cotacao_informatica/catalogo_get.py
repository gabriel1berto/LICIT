#!/usr/bin/env python3
"""catalogo_get.py — Catálogo GET (ex-Goldentec) com especificação técnica por SKU.

Fonte: portal do revendedor https://app.ibyte.com.br/get-catalog/ — a lista de produtos vem
embutida no HTML (`const PRODUCTS = [...]`, 718 SKUs em 19/nov/2026, sem preço). A ficha
técnica de cada SKU é a página `datasheet_url` (tabela "ESPECIFICAÇÕES TÉCNICAS").
Só baixa ficha dos grupos que interessam pra licitação (GRUPOS) — o resto (pulseira, capa,
cadeira gamer...) não entra.

Uso: python catalogo_get.py
"""
import json
import re
import time

from comum import PAUSA, baixar, salvar, texto_plano

URL_CATALOGO = "https://app.ibyte.com.br/get-catalog/"
# código de grupo do catálogo -> categoria do filtro_informatica.py
GRUPOS = {
    "MON": "Monitor", "NBK": "Nobreak", "TEC": "Teclado/Mouse", "MOU": "Teclado/Mouse",
    "SSD": "Armazenamento", "MEM": "Armazenamento", "PEN": "Armazenamento", "CME": "Armazenamento",
    "PRJ": "Projetor", "FON": "Headset/Fone", "SOM": "Caixa de som", "UDA": "Computador",
    "UDI": "Computador", "TBL": "Tablet",
}


_LINHA = re.compile(r"<tr>\s*<td>[^<]*</td>\s*<td>\s*<b>(.*?)</b>\s*</td>\s*<td>(.*?)</td>\s*</tr>", re.S | re.I)


def ficha(url: str) -> tuple[dict, str]:
    """Tabela 'ESPECIFICAÇÕES TÉCNICAS' (linhas <td><b>chave</b></td><td>valor</td>, valor pode
    ter várias linhas com <br>) + bloco descritivo 'INFORMAÇÕES TÉCNICAS'."""
    s = baixar(url)
    if not s:
        return {}, ""
    i = s.find("ESPECIFICA")
    specs = {}
    for k, v in _LINHA.findall(s[i:] if i >= 0 else ""):
        k, v = texto_plano(k), texto_plano(v.replace("<br>", " / "), sep=" ")
        if k and k not in specs:
            specs[k] = v
    t = texto_plano(s)
    a, b = t.find("INFORMAÇÕES TÉCNICAS"), t.find("ESPECIFICAÇÕES TÉCNICAS")
    desc = t[a:b] if 0 <= a < b else ""
    return specs, (desc + " | " + " | ".join(f"{k}: {v}" for k, v in specs.items()))[:6000]


def main():
    s = baixar(URL_CATALOGO)
    m = re.search(r"const PRODUCTS = (\[.*?\]);\s*\n", s, re.S)
    produtos = json.loads(m.group(1))
    alvo = [p for p in produtos if p.get("grupo") in GRUPOS]
    print(f"{len(produtos)} SKUs no catálogo, {len(alvo)} nos grupos de interesse")
    out = []
    for n, p in enumerate(alvo, 1):
        specs, texto = ficha(p["datasheet_url"])
        out.append({
            "fornecedor": "GET", "sku": p["codigo"], "nome": p["descricao"], "marca": p.get("marca"),
            "categoria": GRUPOS[p["grupo"]], "grupo": p["grupo"], "link": p["datasheet_url"],
            "specs": specs, "texto": f"{p['descricao']} | {texto}",
        })
        if n % 20 == 0:
            print(f"  {n}/{len(alvo)}", flush=True)
        time.sleep(PAUSA)
    salvar("get", out)


if __name__ == "__main__":
    main()
