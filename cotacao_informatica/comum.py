"""Utilidades compartilhadas pelos scrapers de catálogo de informática (GET, TS Shara, Mazer).

Catálogo = lista de produtos com especificação técnica estruturada (dict chave->valor do
próprio site) + texto livre da ficha. Nenhum preço: os 3 sites não mostram preço sem login,
e a cotação de verdade acontece com o vendedor (WhatsApp/e-mail). Ver CLAUDE.md Anexo C.
"""

import html
import json
import os
import re
import sys
import time

import requests

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
PAUSA = 1.0  # segundos entre requisições — site de fornecedor, não sobrecarregar


def baixar(url: str, tentativas: int = 3) -> str | None:
    espera = 3.0
    for t in range(tentativas):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
                return r.text
            if r.status_code == 404:
                return None
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
        except Exception as e:
            print(f"  erro {e} {url}", file=sys.stderr)
        time.sleep(espera)
        espera *= 2
    return None


def texto_plano(trecho_html: str, sep: str = "|") -> str:
    """HTML -> texto com separador nas quebras de tag (preserva a estrutura chave|valor)."""
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", trecho_html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", sep, s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\n]+", " ", s)
    s = re.sub(r"\s*\|\s*(\|\s*)*", sep, s)
    return s.strip(sep + " ")


def salvar(nome: str, produtos: list[dict]) -> str:
    os.makedirs(DADOS, exist_ok=True)
    caminho = os.path.join(DADOS, f"catalogo_{nome}.json")
    json.dump(produtos, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{nome}: {len(produtos)} produtos -> {caminho}")
    return caminho


def carregar(nome: str) -> list[dict]:
    return json.load(open(os.path.join(DADOS, f"catalogo_{nome}.json"), encoding="utf-8"))
