"""Testa content.js num Chromium real contra uma página-fixture (layout SIMULADO — não é o DOM do
Compras.gov.br; a calibragem no site real é feita pelo botão Diagnosticar). Uso:
    python -m pytest -p no:dash extensao_compras/test/test_content_fixture.py
"""
import json
import pathlib

import pytest
from playwright.sync_api import sync_playwright

DIR = pathlib.Path(__file__).resolve().parent
EXT = DIR.parent
PACOTE = {
    "versao": 1, "chave": "33287806000161-2026-40", "edital": "CRC (RJ) — 40/2026", "encerramento": "23/12/2099",
    "hash_ficha": "x", "uasg": "791190", "numero_compra": "202", "ano_compra": "2026", "compra_id": "79119006002022026",
    "itens": [{"numero_item": "2", "qtde": 2, "valor_inicial": 3599.0, "valor_minimo": 2387.0, "marca": "GET",
               "fabricante": "GET", "modelo": "PROJ VISION 5 SMART"}],
}

# Stub do chrome.runtime: guarda o listener do content.js pra chamarmos direto.
STUB = "window.chrome = {runtime: {onMessage: {addListener: (f) => { window.__ouvinte = f; }}}};"
CHAMAR = """async (msg) => {
  const L = window.CompraLib;
  msg.pacote && (msg.pacote.checksum = await L.sha256Hex(L.canonico(msg.pacote)));
  return await new Promise((res) => window.__ouvinte(msg, null, res));
}"""


@pytest.fixture(scope="module")
def pagina():
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pg = nav.new_page()
        yield pg
        nav.close()


def abrir(pg, html=None):
    pg.goto((DIR / "fixture_proposta.html").as_uri())
    if html:
        pg.evaluate("h => document.body.innerHTML = h", html)
    pg.add_script_tag(content=STUB)
    pg.add_script_tag(path=str(EXT / "lib.js"))
    pg.add_script_tag(path=str(EXT / "content.js"))


def chamar(pg, acao, pacote=PACOTE, **kw):
    return pg.evaluate(CHAMAR, {"acao": acao, "pacote": json.loads(json.dumps(pacote)), **kw})


def test_diagnostico_acha_campos_por_item(pagina):
    abrir(pagina)
    r = chamar(pagina, "diagnosticar")
    achados = {(c["item"], c["campo"]) for c in r["camposAchados"]}
    assert {("2", "valor_inicial"), ("2", "valor_minimo"), ("2", "marca"), ("2", "fabricante"), ("2", "modelo"),
            ("3", "valor_inicial"), ("3", "marca")} <= achados
    assert r["pagina"]["ok"]
    assert pagina.evaluate("document.getElementById('vu2').value") == ""  # diagnóstico não escreve


def test_simular_nao_escreve(pagina):
    abrir(pagina)
    r = chamar(pagina, "simular")
    assert {(p["campo"], p["valor"]) for p in r["plano"]} >= {("valor_inicial", "3.599,00"), ("valor_minimo", "2.387,00")}
    assert pagina.evaluate("document.getElementById('vu2').value") == ""


def test_preencher_com_mascara_e_nunca_clica(pagina):
    abrir(pagina)
    r = chamar(pagina, "preencher")
    st = {(x["campo"]): x["status"] for x in r["resultado"]}
    assert st == {"valor_inicial": "OK", "valor_minimo": "OK", "marca": "OK", "fabricante": "OK", "modelo": "PULADO"}
    assert pagina.evaluate("document.getElementById('vu2').value") == "3.599,00"
    assert pagina.evaluate("document.getElementById('vu3').value") == ""  # item fora da ficha intocado
    assert pagina.evaluate("window.__cliques") == []  # nunca salva nem envia


def test_sobrescrever_explicito(pagina):
    abrir(pagina)
    r = chamar(pagina, "preencher", sobrescrever=True)
    assert all(x["status"] == "OK" for x in r["resultado"])
    assert pagina.evaluate("document.querySelector('[formcontrolname=modelo]').value") == "PROJ VISION 5 SMART"


def test_pagina_de_outra_compra_recusa(pagina):
    abrir(pagina)
    pagina.evaluate("document.querySelector('h3').textContent = 'Dispensa Eletrônica Nº 00203/2026'")
    r = chamar(pagina, "preencher")
    assert not r["ok"] and "não preencho" in r["erro"]
    assert pagina.evaluate("document.getElementById('vu2').value") == ""


def test_pacote_adulterado_recusa(pagina):
    abrir(pagina)
    p = json.loads(json.dumps(PACOTE))
    r = pagina.evaluate("""async (p) => { p.checksum = 'f'.repeat(64);
        return await new Promise((res) => window.__ouvinte({acao: 'preencher', pacote: p}, null, res)); }""", p)
    assert not r["ok"] and "checksum" in r["erro"]
    assert pagina.evaluate("document.getElementById('vu2').value") == ""


def test_valor_minimo_ausente_vira_aviso(pagina):
    abrir(pagina)
    pagina.evaluate("document.querySelector('[formcontrolname=valorMinimo]').parentElement.remove()")
    r = chamar(pagina, "preencher")
    assert any("sem campo de valor mínimo" in a for a in r["avisos"])


def test_sem_vinculo_forte_nao_chuta_campo(pagina):
    # rótulo "Marca" sem input no próprio bloco: antes caía no "próximo input do DOM" (o de outro campo)
    abrir(pagina)
    pagina.evaluate("""() => {
        const bloco = document.querySelector('[formcontrolname=marca]').parentElement;
        bloco.querySelector('input').remove();
    }""")
    r = chamar(pagina, "preencher")
    assert "marca" not in [x["campo"] for x in r["resultado"]]
    assert pagina.evaluate("document.querySelector('[formcontrolname=fabricante]').value") == "GET"
    assert any("campo marca não achado" in a for a in r["avisos"])


def test_bloco_com_dois_campos_e_ambiguo(pagina):
    abrir(pagina)
    pagina.evaluate("""() => {
        const b = document.querySelector('[formcontrolname=marca]').parentElement;
        b.appendChild(document.createElement('input'));
    }""")
    r = chamar(pagina, "preencher")
    assert "marca" not in [x["campo"] for x in r["resultado"]]


@pytest.mark.parametrize("texto,trecho", [("Critério de julgamento: Maior desconto", "DESCONTO"),
                                          ("Forma de envio de lances: valor total", "TOTAL")])
def test_criterio_incompativel_recusa(pagina, texto, trecho):
    abrir(pagina)
    pagina.evaluate("t => document.body.insertAdjacentHTML('afterbegin', '<p>' + t + '</p>')", texto)
    r = chamar(pagina, "preencher")
    assert not r["ok"] and trecho in r["erro"]
    assert pagina.evaluate("document.getElementById('vu2').value") == ""


def test_pagina_com_varias_compras_recusa(pagina):
    abrir(pagina)
    pagina.evaluate("document.body.insertAdjacentHTML('beforeend', '<p>Dispensa Eletrônica Nº 00305/2026</p>')")
    r = chamar(pagina, "preencher")
    assert not r["ok"] and "compras" in r["erro"]


def test_rotulo_total_nao_e_preenchido(pagina):
    abrir(pagina)
    pagina.evaluate("() => document.querySelector('label[for=vu2]').textContent = 'Valor total do item'")
    r = chamar(pagina, "preencher")
    assert "valor_inicial" not in [x["campo"] for x in r["resultado"]]
    assert pagina.evaluate("document.getElementById('vu2').value") == ""


def test_reinjecao_troca_ouvinte(pagina):
    abrir(pagina)
    pagina.add_script_tag(path=str(EXT / "content.js"))  # 2ª injeção não pode quebrar nem duplicar
    r = chamar(pagina, "preencher")
    assert [x["status"] for x in r["resultado"] if x["campo"] == "valor_inicial"] == ["OK"]


def test_campo_antes_do_rotulo_nao_e_ligado(pagina):
    # bloco "Marca" com o input ANTES do rótulo: pode ser o campo de outro rótulo — não liga
    abrir(pagina)
    pagina.evaluate("""() => {
        const inp = document.querySelector('[formcontrolname=marca]');
        inp.parentElement.insertBefore(inp, inp.parentElement.firstChild);
    }""")
    r = chamar(pagina, "preencher")
    assert "marca" not in [x["campo"] for x in r["resultado"]]
    assert pagina.evaluate("document.querySelector('[formcontrolname=marca]').value") == ""


def test_bloco_de_outro_item_citando_item_da_ficha_nao_preenche(pagina):
    # card do item 3 perde o próprio número e cita "ver Item 2": seus campos viram "item 2" falsos.
    # A regra de campo duplicado tem que barrar — nada do item 2 é escrito em lugar ambíguo.
    abrir(pagina)
    pagina.evaluate("""() => {
        const h = [...document.querySelectorAll('h4')].find((x) => x.textContent.includes('Item 3'));
        h.textContent = 'Projetor - ver Item 2';
    }""")
    r = chamar(pagina, "preencher")
    feitos = [x["campo"] for x in r["resultado"]]
    assert "valor_inicial" not in feitos and "marca" not in feitos
    assert pagina.evaluate("document.getElementById('vu3').value") == ""
    assert any('2 campos "valor_inicial"' in a for a in r["avisos"])


CARDS_ANGULAR = """
<h3>Dispensa Eletrônica N° 202/2026 (Lei 14.133/2021)</h3><p>UASG 791190</p>
<app-cadastro-propostas-itens>
  <div class="row cp-itens-card"><app-identificacao-item><div>1 <span>PROJETOR MULTIMÍDIA</span></div></app-identificacao-item>
    <div><label for="a1">Valor unitário (R$)</label><input id="a1"></div>
    <div><span>Marca</span><input id="m1"></div></div>
  <div class="row cp-itens-card"><app-identificacao-item><div>2 <span>TELA DE PROJEÇÃO</span></div></app-identificacao-item>
    <div><label for="a2">Valor unitário (R$)</label><input id="a2"></div>
    <div><span>Marca</span><input id="m2"></div></div>
</app-cadastro-propostas-itens>
"""


def test_item_pelo_componente_angular_real(pagina):
    # formato visto na tela real (20/nov/2026): número do item sem a palavra "Item"
    abrir(pagina, CARDS_ANGULAR)
    p = json.loads(json.dumps(PACOTE))
    p["itens"][0]["numero_item"] = "2"
    r = chamar(pagina, "simular", pacote=p)
    alvos = {(x["item"], x["campo"]) for x in r["camposAchados"]}
    assert ("1", "valor_inicial") in alvos and ("2", "valor_inicial") in alvos and ("2", "marca") in alvos
    r = chamar(pagina, "preencher", pacote=p)
    assert pagina.evaluate("document.getElementById('a2').value") == "3.599,00"
    assert pagina.evaluate("document.getElementById('m2').value") == "GET"
    assert pagina.evaluate("document.getElementById('a1').value") == ""  # item 1 (fora do pacote) intocado


TELA_REAL = """
<h3>Dispensa Eletrônica N° 202/2026 (Lei 14.133/2021)</h3><p>UASG 791190</p>
<app-cadastro-propostas-itens><div class="row cp-itens-card">
  <app-identificacao-item><div>1 <span>PROJETOR MULTIMÍDIA</span></div></app-identificacao-item>
  <div><label>Valor unitário (R$)</label><div><input data-test="input-valor-proposta" class="moeda"></div></div>
  <div><label>Marca/Fabricante</label><input data-test="input-marca-fabricante" placeholder="digite a marca e o fabricante"></div>
  <div><label>Modelo/Versão</label><input data-test="input-modelo-versao" placeholder="digite o modelo/versão"></div>
  <button type="submit" onclick="window.__cliques.push('salvar')">Salvar</button>
</div></app-cadastro-propostas-itens>
"""


def test_tela_real_por_data_test(pagina):
    # estrutura da tela cadastro-propostas real (20/nov/2026): data-test + Marca/Fabricante num campo só
    abrir(pagina, TELA_REAL)
    pagina.evaluate("window.__cliques = []")
    p = json.loads(json.dumps(PACOTE))
    p["itens"][0]["numero_item"] = "1"
    r = chamar(pagina, "preencher", pacote=p)
    st = {x["campo"]: x["status"] for x in r["resultado"]}
    assert st == {"valor_inicial": "OK", "marca": "OK", "modelo": "OK"}
    assert pagina.evaluate("document.querySelector('[data-test=input-marca-fabricante]').value") == "GET"
    assert any("sem campo de valor mínimo" in a for a in r["avisos"])
    assert pagina.evaluate("window.__cliques") == []
