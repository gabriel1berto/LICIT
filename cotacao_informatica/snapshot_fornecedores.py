#!/usr/bin/env python3
"""snapshot_fornecedores.py — Resumo dos catálogos de informática pro dashboard.

Os catálogos (dados/catalogo_*.json) ficam fora do git, então o Streamlit Cloud não
enxerga eles. Este script grava só o resumo (produtos por categoria e marcas de cada
distribuidor) em analise/assets/fornecedores_informatica.json, que vai pro git e é lido
por analise/views/radar_fornecedor_informatica.py.

Rodar de novo sempre que um catalogo_*.py for atualizado:
    python cotacao_informatica/snapshot_fornecedores.py
"""

import collections
import json
import os
from datetime import date
from urllib.parse import urlparse

from comum import DADOS

SAIDA = os.path.join(os.path.dirname(DADOS), "..", "analise", "assets", "fornecedores_informatica.json")
FORNECEDORES = [("GET", "get"), ("TS Shara", "tsshara"), ("Mazer", "mazer")]
TOP_MARCAS = 5


def resumo(nome: str, chave: str) -> dict:
    caminho = os.path.join(DADOS, f"catalogo_{chave}.json")
    produtos = json.load(open(caminho, encoding="utf-8"))
    por_cat = collections.defaultdict(collections.Counter)
    for p in produtos:
        por_cat[p.get("categoria") or "Outros"][(p.get("marca") or "—").strip().upper()] += 1
    site = next((urlparse(p["link"]).netloc for p in produtos if p.get("link")), "")
    return {
        "fornecedor": nome,
        "site": site,
        "catalogo_em": date.fromtimestamp(os.path.getmtime(caminho)).isoformat(),
        "produtos": len(produtos),
        "categorias": {
            cat: {"produtos": sum(m.values()), "marcas": [k for k, _ in m.most_common(TOP_MARCAS)]}
            for cat, m in sorted(por_cat.items(), key=lambda kv: -sum(kv[1].values()))
        },
    }


if __name__ == "__main__":
    dados = {"gerado_em": date.today().isoformat(), "fornecedores": [resumo(n, c) for n, c in FORNECEDORES]}
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    for fz in dados["fornecedores"]:
        print(f"{fz['fornecedor']}: {fz['produtos']} produtos, {len(fz['categorias'])} categorias")
    print("gravado em", os.path.normpath(SAIDA))
