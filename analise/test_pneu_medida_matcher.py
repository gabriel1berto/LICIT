import pytest

from pneu_medida_matcher import MedidaTupla, avaliar, comparar_medidas, extrair_medida

REF_225_70_R13 = MedidaTupla(largura=225, perfil=70, construcao="R", aro=13)


class TestExtrairMedida:
    def test_com_barra_e_r(self):
        m = extrair_medida("225/70R13")
        assert m.largura == 225
        assert m.perfil == 70
        assert m.construcao == "R"
        assert m.aro == 13
        assert m.inferido_construcao is False

    def test_com_barras_triplas_sem_r(self):
        m = extrair_medida("225/70/13")
        assert (m.largura, m.perfil, m.aro) == (225, 70, 13)
        assert m.construcao == "R"
        assert m.inferido_construcao is True  # R não estava no texto

    def test_com_espacos(self):
        m = extrair_medida("225 70 13")
        assert (m.largura, m.perfil, m.aro) == (225, 70, 13)
        assert m.inferido_construcao is True

    def test_colado_sem_separador(self):
        m = extrair_medida("22570R13")
        assert (m.largura, m.perfil, m.construcao, m.aro) == (225, 70, "R", 13)
        assert m.inferido_construcao is False

    def test_aro_com_meio_ponto(self):
        m = extrair_medida("275/80R22.5")
        assert m.aro == 22.5

    def test_captura_indice_carga_velocidade(self):
        m = extrair_medida("225/70R13 104S")
        assert m.indice_carga_velocidade == "104S"

    def test_sem_indice_carga_velocidade(self):
        m = extrair_medida("225/70R13")
        assert m.indice_carga_velocidade is None

    def test_erro_digitacao_fuzzy_fallback(self):
        # espaço extra, hífen no lugar errado -- ainda deve extrair via fallback
        m = extrair_medida("225-70 -R- 13")
        assert (m.largura, m.perfil, m.aro) == (225, 70, 13)

    def test_texto_nao_reconhecivel_retorna_none(self):
        assert extrair_medida("sem estoque no momento") is None

    def test_texto_vazio_retorna_none(self):
        assert extrair_medida("") is None

    def test_rejeita_numero_fora_do_range_de_pneu(self):
        # 999/99R99 não é uma medida de pneu real -- não deve casar por acidente
        assert extrair_medida("999/99R99") is None

    def test_medida_caminhao_otr_ainda_extrai(self):
        # medida usada no CLAUDE.md como exemplo de erro de classificação (não é sobre
        # classificação aqui, só confirma que a extração de tupla funciona pra ela também)
        m = extrair_medida("1000X20")
        # "1000X20" não bate no formato largura/perfil/aro-com-R -- comportamento esperado
        # é não achar padrão de pneu de passeio (retorna None ou tupla fora de faixa)
        assert m is None or m.largura > 335 is False


class TestCompararMedidas:
    def test_match_exato(self):
        candidata = MedidaTupla(225, 70, "R", 13, inferido_construcao=False,
                                 indice_carga_velocidade="104S")
        assert comparar_medidas(candidata, REF_225_70_R13) == "match_exato"

    def test_match_parcial_por_construcao_inferida(self):
        candidata = MedidaTupla(225, 70, "R", 13, inferido_construcao=True,
                                 indice_carga_velocidade="104S")
        assert comparar_medidas(candidata, REF_225_70_R13) == "match_parcial"

    def test_match_parcial_por_indice_ausente(self):
        candidata = MedidaTupla(225, 70, "R", 13, inferido_construcao=False,
                                 indice_carga_velocidade=None)
        assert comparar_medidas(candidata, REF_225_70_R13) == "match_parcial"

    def test_sem_match_largura_diferente(self):
        candidata = MedidaTupla(205, 70, "R", 13)
        assert comparar_medidas(candidata, REF_225_70_R13) == "sem_match"

    def test_sem_match_perfil_diferente(self):
        candidata = MedidaTupla(225, 65, "R", 13)
        assert comparar_medidas(candidata, REF_225_70_R13) == "sem_match"

    def test_sem_match_aro_diferente(self):
        candidata = MedidaTupla(225, 70, "R", 14)
        assert comparar_medidas(candidata, REF_225_70_R13) == "sem_match"

    def test_nunca_compara_string_direto(self):
        # 225/70R13 e 225/70/13 têm strings diferentes mas tupla-chave igual
        # (isso é o núcleo do bug que motivou o módulo -- confirma que resolve)
        a = extrair_medida("225/70R13")
        b = extrair_medida("225/70/13")
        assert a.chave()[:2] == b.chave()[:2]  # largura, perfil batem
        assert a.chave()[3] == b.chave()[3]    # aro bate
        # construcao bate no valor final (ambos normalizam pra "R"), mas inferido difere
        assert a.construcao == b.construcao == "R"
        assert a.inferido_construcao != b.inferido_construcao


class TestAvaliar:
    def test_fluxo_completo_match_exato(self):
        confianca, tupla = avaliar("225/70R13 104S", REF_225_70_R13)
        assert confianca == "match_exato"
        assert tupla.largura == 225

    def test_fluxo_completo_sem_match(self):
        confianca, tupla = avaliar("sem estoque", REF_225_70_R13)
        assert confianca == "sem_match"
        assert tupla is None

    def test_fluxo_completo_match_parcial(self):
        confianca, tupla = avaliar("225/70/13", REF_225_70_R13)
        assert confianca == "match_parcial"
        assert tupla is not None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
