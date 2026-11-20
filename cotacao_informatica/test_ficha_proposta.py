from datetime import date

import pytest

from ficha_proposta import (aprovar, calcular_precos, chave_edital, hash_ficha, montar_fichas, montar_item,
                            parse_brl, parse_data, separar_marca_modelo, verificar_ficha)

HOJE = date(2026, 11, 20)
VALIDADE = date(2026, 11, 30)
CHAVE = "33287806000161-2026-40"
LINHA = {"ref": "CRC (RJ) — 40/2026", "encerra": "23/11/2026", "item": "2",
         "link_pncp": "https://pncp.gov.br/app/editais/33287806000161/2026/40", "produto": "Projetor",
         "desc": "Projetor 3600 lm", "qtde": "2", "unid": "Unidade", "ref_preco": "R$ 3.599,00",
         "mediana_12m": "R$ 3.157,23", "atende": "Sim", "marca_modelo": "GET / PROJ VISION 5 SMART",
         "ncm": "8528.69.10", "preco_un": "R$ 2.000,00", "frete": "R$ 100,00", "link_produto": "x"}


def fichas(linhas=None, **kw):
    kw.setdefault("hoje", HOJE)
    kw.setdefault("validade_cotacao", VALIDADE)
    return montar_fichas(linhas or [LINHA], kw.pop("margem", 0.10), **kw)


# ── parsing ─────────────────────────────────────────────────────────────────

def test_parse_brl():
    assert parse_brl("R$ 3.599,00") == 3599.0
    assert parse_brl("3599") == 3599.0
    assert parse_brl("1.234") == 1234.0
    assert parse_brl("12,5") == 12.5
    assert parse_brl("") is None
    assert parse_brl("sem código CATMAT no PNCP") is None


def test_parse_brl_rejeita_lixo_e_negativo():
    assert parse_brl("-10") is None
    assert parse_brl(-10) is None
    assert parse_brl("1,2,3") is None
    assert parse_brl("R$ 0,00") == 0.0


def test_parse_data():
    assert parse_data("23/11/2026") == date(2026, 11, 23)
    assert parse_data("31/02/2026") is None
    assert parse_data("") is None


def test_chave_edital():
    assert chave_edital(LINHA["link_pncp"]) == CHAVE
    assert chave_edital("") is None


def test_separar_marca_modelo():
    assert separar_marca_modelo("GET / PROJ VISION 5") == ("GET", "PROJ VISION 5", True)
    assert separar_marca_modelo("PROJ VISION 5 GET") == ("PROJ VISION 5 GET", "PROJ VISION 5 GET", False)


# ── preço ───────────────────────────────────────────────────────────────────

def test_calculo_piso_e_inicial():
    # invest 4000 + frete 100 + imposto 240 = 4340 / 2 = 2170 un; piso 10% = 2387; inicial = referência
    p = calcular_precos(2000, 2, 100, 3599, 0.10)
    assert p["cogs_un"] == 2170
    assert p["valor_minimo"] == 2387.0
    assert p["valor_inicial"] == 3599.0
    assert not p["inviavel"]


def test_piso_arredonda_pra_cima_e_nunca_abaixo_do_custo():
    assert calcular_precos(10.0, 3, 0, None, 0.10)["valor_minimo"] == 11.66  # 10,60 × 1,10
    for preco, qtde, frete in [(10.01, 3, 0.01), (0.33, 7, 0.0), (1234.567, 13, 99.99), (0.01, 1, 0)]:
        p = calcular_precos(preco, qtde, frete, None, 0.0)
        assert p["valor_minimo"] >= p["cogs_un"]


def test_sem_referencia_usa_margem_alvo_e_inicial_nunca_abaixo_do_piso():
    assert calcular_precos(100, 1, 0, None, 0.10)["valor_inicial"] == 137.8  # 106 × 1,30
    p = calcular_precos(100, 1, 0, None, 0.45)  # margem mínima > margem alvo
    assert p["valor_inicial"] >= p["valor_minimo"]


@pytest.mark.parametrize("margem", [-0.01, 0.51, 10])
def test_margem_fora_do_limite_da_erro(margem):
    with pytest.raises(ValueError):
        calcular_precos(100, 1, 0, None, margem)
    with pytest.raises(ValueError):
        fichas(margem=margem)


# ── status do item ──────────────────────────────────────────────────────────

def test_inviavel_quando_piso_passa_referencia():
    assert montar_item({**LINHA, "ref_preco": "R$ 2.300,00"}, 0.10)["status"] == "INVIAVEL"


@pytest.mark.parametrize("campo,valor", [("preco_un", ""), ("preco_un", "a combinar"), ("atende", "Parcial"),
                                         ("atende", ""), ("marca_modelo", " "), ("qtde", "0"), ("frete", "")])
def test_pendente_nunca_inventa_valor(campo, valor):
    it = montar_item({**LINHA, campo: valor}, 0.10)
    assert it["status"] == "PENDENTE"
    assert it["valor_minimo"] is None and it["valor_inicial"] is None


def test_frete_zero_explicito_vale():
    assert montar_item({**LINHA, "frete": "0"}, 0.10)["status"] == "PRONTO"


def test_atende_sim_case_insensitive():
    assert montar_item({**LINHA, "atende": " sim "}, 0.10)["status"] == "PRONTO"


def test_preco_digitado_errado_bloqueia():
    it = montar_item({**LINHA, "preco_un": "R$ 200,00"}, 0.10)  # 2.000 virou 200
    assert it["status"] == "BLOQUEADO"
    assert "erro de digitação" in it["motivos"][0]


def test_piso_muito_abaixo_da_mediana_bloqueia():
    it = montar_item({**LINHA, "ref_preco": "", "mediana_12m": "R$ 9.000,00"}, 0.10)
    assert it["status"] == "BLOQUEADO"


def test_suspeito_aceito_vira_pronto_com_alerta():
    it = montar_item({**LINHA, "preco_un": "R$ 200,00"}, 0.10, aceitos={"2"})
    assert it["status"] == "PRONTO"
    assert any("ACEITO" in a for a in it["alertas"])


def test_unidade_nao_unitaria_alerta():
    assert any("unidade" in a for a in montar_item({**LINHA, "unid": "Caixa c/ 10"}, 0.10)["alertas"])
    assert not any("unidade" in a for a in montar_item({**LINHA, "unid": "1,00 UNIDADE"}, 0.10)["alertas"])


def test_sem_separador_marca_modelo_alerta():
    it = montar_item({**LINHA, "marca_modelo": "PROJ VISION 5 GET"}, 0.10)
    assert it["status"] == "PRONTO" and any("separador" in a for a in it["alertas"])


# ── ficha ───────────────────────────────────────────────────────────────────

def test_ficha_agrupa_por_edital_e_so_pronta_com_tudo_pronto():
    f = fichas([LINHA, {**LINHA, "item": "3", "preco_un": ""}])[CHAVE]
    assert len(f["itens"]) == 2
    assert f["resumo"] == {"PRONTO": 1, "PENDENTE": 1}
    assert not f["pronta_para_enviar"]


def test_ficha_pronta_caminho_feliz():
    f = fichas()[CHAVE]
    assert f["pronta_para_enviar"] and not f["bloqueios"] and not f["aprovada"]
    assert any("VALOR MÍNIMO R$ 2387.00" in l for l in f["checklist_f0"])


def test_item_duplicado_bloqueia():
    f = fichas([LINHA, LINHA])[CHAVE]
    assert f["resumo"] == {"DUPLICADO": 2} and not f["pronta_para_enviar"]


def test_edital_encerrado_expira():
    f = fichas(hoje=date(2026, 11, 24))[CHAVE]
    assert not f["pronta_para_enviar"] and "EXPIRADA" in f["bloqueios"][0]


@pytest.mark.parametrize("validade,trecho", [(None, "vazia"), (date(2026, 11, 19), "vencida"),
                                             (date(2026, 11, 22), "antes do encerramento")])
def test_validade_da_cotacao(validade, trecho):
    f = fichas(validade_cotacao=validade)[CHAVE]
    assert not f["pronta_para_enviar"] and trecho in " ".join(f["bloqueios"])


# ── aprovação humana + integridade ─────────────────────────────────────────

def regerar(linhas=None):
    return lambda aps: fichas(linhas, aprovacoes=aps)


def test_aprovacao_e_verificacao():
    h = aprovar(regerar(), CHAVE, [])
    f = fichas(aprovacoes={CHAVE: {"hash": h}})[CHAVE]
    assert f["aprovada"]
    assert verificar_ficha(f) == (True, "ok")


def test_mudanca_na_planilha_revoga_aprovacao():
    h = aprovar(regerar(), CHAVE, [])
    f = fichas([{**LINHA, "preco_un": "R$ 2.100,00"}], aprovacoes={CHAVE: {"hash": h}})[CHAVE]
    assert not f["aprovada"]
    assert any("REVOGADA" in b for b in f["bloqueios"])
    assert verificar_ficha(f)[0] is False


def test_mudar_margem_revoga_aprovacao():
    h = aprovar(regerar(), CHAVE, [])
    f = fichas(margem=0.15, aprovacoes={CHAVE: {"hash": h}})[CHAVE]
    assert not f["aprovada"]


def test_nao_aprova_ficha_pendente():
    with pytest.raises(SystemExit):
        aprovar(regerar([{**LINHA, "preco_un": ""}]), CHAVE, [])


def test_nao_aprova_suspeito_sem_aceite_explicito():
    linhas = [{**LINHA, "preco_un": "R$ 200,00"}]
    with pytest.raises(SystemExit, match="aceitar-suspeito 2"):
        aprovar(regerar(linhas), CHAVE, [])
    h = aprovar(regerar(linhas), CHAVE, ["2"])
    f = fichas(linhas, aprovacoes={CHAVE: {"hash": h, "suspeitos_aceitos": ["2"]}})[CHAVE]
    assert f["aprovada"]


def test_nao_aprova_edital_inexistente():
    with pytest.raises(SystemExit):
        aprovar(regerar(), "00000000000000-2026-1", [])


def test_verificar_pega_ficha_adulterada():
    h = aprovar(regerar(), CHAVE, [])
    f = fichas(aprovacoes={CHAVE: {"hash": h}})[CHAVE]
    f["itens"][0]["valor_minimo"] = 1.00  # edição manual no JSON depois de aprovada
    ok, msg = verificar_ficha(f)
    assert not ok and "hash" in msg


def test_verificar_recusa_nao_aprovada():
    assert verificar_ficha(fichas()[CHAVE]) == (False, "ficha não aprovada por humano (--aprovar)")


def test_hash_estavel_e_ignora_gerado_em():
    a, b = fichas()[CHAVE], fichas()[CHAVE]
    b["gerado_em"] = "outro"
    assert hash_ficha(a) == hash_ficha(b) == a["hash"]


def test_aceite_de_suspeito_sem_hash_nao_gera_falsa_revogacao():
    f = fichas([{**LINHA, "preco_un": "R$ 200,00"}], aprovacoes={CHAVE: {"suspeitos_aceitos": ["2"]}})[CHAVE]
    assert f["pronta_para_enviar"] and not any("REVOGADA" in b for b in f["bloqueios"])


# ── pacote pra extensão (F2) ───────────────────────────────────────────────

from ficha_proposta import canonico_pacote, meta_compra, montar_pacote  # noqa: E402

DETALHE = {"usuarioNome": "Compras.gov.br", "numeroCompra": "202", "anoCompra": 2026,
           "modalidadeNome": "Dispensa", "unidadeOrgao": {"codigoUnidade": "791190"},
           "linkSistemaOrigem": "https://cnetmobile.estaleiro.serpro.gov.br/comprasnet-web/public/compras/"
                                "acompanhamento-compra?compra=79119006002022026"}


def ficha_aprovada():
    h = aprovar(regerar(), CHAVE, [])
    return fichas(aprovacoes={CHAVE: {"hash": h}})[CHAVE]


def test_meta_compra():
    m = meta_compra(DETALHE)
    assert (m["uasg"], m["numero_compra"], m["compra_id"]) == ("791190", "202", "79119006002022026")


@pytest.mark.parametrize("mudanca", [{"usuarioNome": "BLL Compras"}, {"linkSistemaOrigem": ""},
                                     {"unidadeOrgao": {}},
                                     {"numeroCompra": "203"},  # id da compra é de outra compra
                                     {"anoCompra": 2025},
                                     {"unidadeOrgao": {"codigoUnidade": "791191"}}])
def test_meta_compra_recusa_fora_do_compras_ou_incompleto(mudanca):
    with pytest.raises(SystemExit):
        meta_compra({**DETALHE, **mudanca})


def test_pacote_so_de_ficha_aprovada():
    with pytest.raises(SystemExit, match="não aprovada"):
        montar_pacote(fichas()[CHAVE], CHAVE, meta_compra(DETALHE))
    p = montar_pacote(ficha_aprovada(), CHAVE, meta_compra(DETALHE))
    assert p["itens"] == [{"numero_item": "2", "qtde": 2.0, "valor_inicial": 3599.0, "valor_minimo": 2387.0,
                           "marca": "GET", "fabricante": "GET", "modelo": "PROJ VISION 5 SMART"}]
    assert "cogs_un" not in p["itens"][0]  # custo não sai pro navegador


def test_canonico_fixo():
    # mesmo texto que extensao_compras/test/lib.test.js recalcula — mudar aqui quebra lá (de propósito)
    p = montar_pacote(ficha_aprovada(), CHAVE, meta_compra(DETALHE))
    assert canonico_pacote(p) == ("33287806000161-2026-40|791190|202|2026|79119006002022026|23/11/2026\n"
                                  "2|2|3599.00|2387.00|GET|GET|PROJ VISION 5 SMART")
    assert p["checksum"] == __import__("hashlib").sha256(canonico_pacote(p).encode()).hexdigest()


def test_fabricante_assumido_vira_alerta():
    assert any("fabricante assumido" in a for a in montar_item(LINHA, 0.10)["alertas"])


def test_checklist_f0_avisa_lance_por_valor_total():
    assert any("VALOR UNITÁRIO" in l for l in fichas()[CHAVE]["checklist_f0"])


def test_qtde_fracionada_no_canonico():
    f = ficha_aprovada()
    f["itens"][0]["qtde"] = 2.5
    assert "|2.5|" in canonico_pacote({**montar_pacote(ficha_aprovada(), CHAVE, meta_compra(DETALHE)),
                                       "itens": f["itens"]})


def test_fmt_qtde_sem_notacao_cientifica():
    from ficha_proposta import fmt_qtde
    assert [fmt_qtde(q) for q in (2.0, 2.5, 1_000_000.0, 100.0, 0.25)] == ["2", "2.5", "1000000", "100", "0.25"]
