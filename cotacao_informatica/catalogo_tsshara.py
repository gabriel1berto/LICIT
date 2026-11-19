#!/usr/bin/env python3
"""catalogo_tsshara.py — Catálogo TS Shara (nobreak e estabilizador) com especificação.

Fonte: WordPress do fabricante — lista via REST `https://tsshara.com.br/wp-json/wp/v2/product`
(457 produtos em 19/nov/2026, sem preço) e ficha em cada página de produto (abas
Características / Especificações, em texto livre: "Potência 1200VA", "Entrada Monovolt 220V",
"Saída Monovolt 220V", "6 tomadas de saída 10A"...). Só nobreak e estabilizador — a TS Shara
não faz periférico; filtro de linha/protetor fica de fora.

Uso: python catalogo_tsshara.py
"""
import html
import json
import re
import time

from comum import PAUSA, baixar, salvar, texto_plano

API = "https://tsshara.com.br/wp-json/wp/v2/product?per_page=100&page={}&_fields=id,title,link"


def categoria(titulo: str) -> str | None:
    t = titulo.upper()
    if "ESTABILIZADOR" in t or "POWEREST" in t:
        return "Estabilizador"
    if "NOBREAK" in t or "NO-BREAK" in t or "UPS" in t:
        return "Nobreak"
    return None


def ficha(url: str) -> tuple[dict, str]:
    s = baixar(url)
    if not s:
        return {}, ""
    t = texto_plano(s)
    # abas (Características|Proteções|Especificações|Aplicações) vêm primeiro como títulos;
    # o conteúdo das 4 abas fica depois do título "Aplicações", até "Downloads"
    a = t.find("|Aplicações|")
    b = t.find("|Downloads|", a)
    corpo = t[a + 12: b if b > a else a + 8000] if a >= 0 else ""
    linhas = [l.strip(" •·-–") for l in corpo.split("|") if l.strip() and not l.startswith("As informações acima")]
    specs = {}
    for k, v in zip(linhas, linhas[1:]):  # bloco "Tensão de entrada:|220V"
        if k.endswith(":") and len(k) < 60 and not v.endswith(":"):
            specs.setdefault(k[:-1].strip(), v)
    for l in linhas:
        m = re.match(r"(Potência|Entrada|Saída|Forma de onda|Tecnologia)\b[: ]*(.*)", l, re.I)
        if m and m.group(1).capitalize() not in specs:
            specs[m.group(1).capitalize()] = m.group(2).strip()
        m = re.search(r"(\d+)\s*tomadas", l, re.I)
        if m and "Tomadas" not in specs:
            specs["Tomadas"] = l
        m = re.search(r"(\d+)\s*bateria", l, re.I)
        if m and "Baterias" not in specs:
            specs["Baterias"] = l
    return specs, " | ".join(linhas)[:6000]


def main():
    itens, pagina = [], 1
    while True:
        s = baixar(API.format(pagina))
        if not s:
            break
        lote = json.loads(s)
        if not lote:
            break
        itens += lote
        pagina += 1
        time.sleep(PAUSA)
    alvo = [(p, categoria(html.unescape(p["title"]["rendered"]))) for p in itens]
    alvo = [(p, c) for p, c in alvo if c]
    print(f"{len(itens)} produtos na API, {len(alvo)} nobreak/estabilizador")
    out = []
    for n, (p, cat) in enumerate(alvo, 1):
        nome = html.unescape(p["title"]["rendered"])
        specs, texto = ficha(p["link"])
        out.append({"fornecedor": "TS Shara", "sku": str(p["id"]), "nome": nome, "marca": "TS Shara",
                    "categoria": cat, "link": p["link"], "specs": specs, "texto": f"{nome} | {texto}"})
        if n % 20 == 0:
            print(f"  {n}/{len(alvo)}", flush=True)
        time.sleep(PAUSA)
    salvar("tsshara", out)


if __name__ == "__main__":
    main()
