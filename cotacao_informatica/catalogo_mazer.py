#!/usr/bin/env python3
"""catalogo_mazer.py — Catálogo Mazer Distribuidora com atributos técnicos por produto.

Fonte: https://www.mazer.com.br — listagem por categoria paginada (`?&pagina=N`, 24 por
página) e página de produto com bloco "Atributos" (pares chave: valor, ex. "Potência VA:
1500VA", "Tensão Saída: 120v"). Preço só aparece logado — não é coletado.

Uso: python catalogo_mazer.py
"""
import re
import time

from comum import PAUSA, baixar, salvar, texto_plano

BASE = "https://www.mazer.com.br"
# caminho da categoria no site -> categoria do filtro_informatica.py
CATEGORIAS = {
    "/categoria/departamentos/monitor-e-projetor/monitor": "Monitor",
    "/categoria/departamentos/monitor-e-projetor/projetor": "Projetor",
    "/categoria/departamentos/nobreak-e-estabilizador/nobreak": "Nobreak",
    "/categoria/departamentos/nobreak-e-estabilizador/estabilizador": "Estabilizador",
    "/categoria/departamentos/acessorios/kit-teclado-mouse": "Teclado/Mouse",
    "/categoria/segmentos/integracao-componentes/teclado": "Teclado/Mouse",
    "/categoria/segmentos/integracao-componentes/mouse": "Teclado/Mouse",
    "/categoria/departamentos/armazenamento/ssd": "Armazenamento",
    "/categoria/departamentos/armazenamento/pen-drive": "Armazenamento",
    "/categoria/departamentos/componentes-e-placas/memoria": "Armazenamento",
    "/categoria/departamentos/acessorios/fones-de-ouvidos": "Headset/Fone",
    "/categoria/departamentos/acessorios/caixa-acustica": "Caixa de som",
    "/categoria/departamentos/acessorios/webcam": "Webcam",
    "/categoria/departamentos/microcomputador/microcomputador": "Computador",
    "/categoria/departamentos/notebook/notebook": "Notebook",
    "/categoria/departamentos/tablet-1/tablet": "Tablet",
    "/categoria/segmentos/impressao/impressora-laser-mono": "Impressora",
    "/categoria/segmentos/impressao/impressora-laser-color": "Impressora",
    "/categoria/segmentos/impressao/impressora-tanque-de-tinta": "Impressora",
    "/categoria/segmentos/impressao/multifuncional-laser-mono": "Impressora",
    "/categoria/segmentos/impressao/multifuncional-laser-color": "Impressora",
    "/categoria/segmentos/impressao/multifuncional-tanque-de-tinta": "Impressora",
    "/categoria/segmentos/impressao/multifuncional-jato-de-tinta": "Impressora",
}
MAX_PAGINAS = 40


def listar(caminho: str) -> list[str]:
    links, pagina = [], 1
    while pagina <= MAX_PAGINAS:
        s = baixar(f"{BASE}{caminho}" + (f"?&pagina={pagina}" if pagina > 1 else ""))
        if not s:
            break
        novos = [l for l in dict.fromkeys(re.findall(r'href="(/produto/[^"]+)"', s)) if l not in links]
        if not novos:
            break
        links += novos
        pagina += 1
        time.sleep(PAUSA)
    return links


def ficha(caminho: str) -> dict | None:
    s = baixar(BASE + caminho)
    if not s:
        return None
    t = texto_plano(s)
    # sem <h1>: o nome fica entre "Pn: X|" e "|Código: N" no bloco do produto
    nome = re.search(r"\|Pn: ?[^|]*\|([^|]+)\|Código:", t) or re.search(r"<title>(.*?)</title>", s, re.S)
    nome = texto_plano(nome.group(1), sep=" ").split(" | ")[0].strip() if nome else caminho.split("/")[-1]
    specs = {}
    i = t.find("|Atributos|")
    if i >= 0:
        fim = t.find("|Nossas marcas", i)
        partes = [p.strip() for p in t[i + 11: fim if fim > 0 else i + 4000].split("|") if p.strip()]
        k = None
        for p in partes:
            if p.endswith(":") and len(p) < 60:
                k = p[:-1].strip()
            elif k:
                specs[k] = (specs[k] + " / " + p) if k in specs else p
    a = t.find("|Informações|")
    desc = t[a + 13: i] if 0 <= a < i else ""
    pn = re.search(r"Pn: ?([\w\-./]+)", t)
    cod = re.search(r"Código: ?(\d+)", t)
    return {"nome": nome, "specs": specs, "descricao": desc[:3000],
            "pn": pn.group(1) if pn else None, "codigo": cod.group(1) if cod else None}


def main():
    vistos, out = set(), []
    for caminho, cat in CATEGORIAS.items():
        links = [l for l in listar(caminho) if l not in vistos]
        print(f"{cat:14} {caminho}: {len(links)} produtos novos", flush=True)
        for l in links:
            vistos.add(l)
            f = ficha(l)
            time.sleep(PAUSA)
            if not f:
                continue
            out.append({
                "fornecedor": "Mazer", "sku": f["codigo"] or l.rsplit("-", 1)[-1], "pn": f["pn"],
                "nome": f["nome"], "marca": f["specs"].get("Marca"), "categoria": cat,
                "link": BASE + l, "specs": f["specs"],
                "texto": f"{f['nome']} | {f['descricao']} | " + " | ".join(f"{k}: {v}" for k, v in f["specs"].items()),
            })
        salvar("mazer", out)  # salva a cada categoria — não perde tudo se cair no meio


if __name__ == "__main__":
    main()
