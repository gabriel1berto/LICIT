"""
test_filtro_onco.py — Regressão do filtro "é medicamento oncológico de verdade?"
(eh_medicamento_onco_de_verdade) e de principio_ativo_provavel().

Cobre os 5 falsos positivos de uso duplo achados no double-check de 23/jul/2026
(Talidomida/Ácido zoledrônico/Denosumabe/Metotrexato/Tretinoína — mesma substância,
indicação NÃO-oncológica confirmada por amostra real). Objetivo: nenhum desses
bugs pode voltar em silêncio.
"""

import pytest

from filtro_onco import eh_medicamento_onco_de_verdade, principio_ativo_provavel


class TestTalidomidaFormularioNaoEhMedicamento:
    def test_bloco_de_receita_e_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade(
            "Bloco de Receita Talidomida receituário branco contendo de 20 folhas"
        ) is False

    def test_notificacao_de_receita_especial_e_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade(
            "BLOCO DE NOTIFICAÇÃO DE RECEITA ESPECIAL DE TALIDOMIDA, IMPRESSÃO EM PAPEL"
        ) is False

    def test_telemedicina_de_renovacao_e_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade(
            "TELEMEDICINA PARA RENOVAÇÃO DE RECEITA... BRANCA DE TALIDOMIDA"
        ) is False

    def test_talidomida_comprimido_de_verdade_continua_true(self):
        assert eh_medicamento_onco_de_verdade("Talidomida 100mg comprimido") is True


class TestAcidoZoledronicoOsteoporoseVsOncologico:
    def test_aclasta_e_osteoporose_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade(
            "ACLASTA ÁCIDO ZOLEDRÔNICO 5 MG / 100 ML - SOLUÇÃO INJETÁVEL"
        ) is False

    def test_5mg_sem_aclasta_tambem_e_osteoporose(self):
        assert eh_medicamento_onco_de_verdade("Ácido Zoledrônico 5mg frasco-ampola") is False

    def test_4mg_e_oncologico_continua_true(self):
        assert eh_medicamento_onco_de_verdade("Ácido Zoledrônico 4mg solução injetável") is True


class TestDenosumabeDoseSeparaIndicacao:
    def test_60mg_e_prolia_osteoporose_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("DENOSUMABE 60mg/ml solução injetável seringa") is False

    def test_120mg_e_xgeva_oncologico_continua_true(self):
        assert eh_medicamento_onco_de_verdade("DENOSUMABE, 120mg, solucao injetavel") is True


class TestMetotrexatoDoseSeparaEspecialidade:
    def test_2_5mg_comprimido_e_reumatologia_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("METOTREXATO, sodico 2,5 mg, comprimido") is False

    def test_injetavel_alta_dose_continua_true(self):
        assert eh_medicamento_onco_de_verdade("METOTREXATO 50MG (25MG/ML) INJETAVEL 2ML") is True


class TestTretinoinaTopicoVsOralOncologico:
    def test_creme_vitacid_e_dermatologia_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("VITACID - TRETINOINA 0,5 MG/ G") is False

    def test_capsula_oral_continua_true(self):
        assert eh_medicamento_onco_de_verdade("Tretinoína 10mg cápsula") is True


class TestPrincipioAtivoRespeitaExclusao:
    def test_bloco_de_receita_nao_retorna_talidomida(self):
        assert principio_ativo_provavel("Bloco de Receita Talidomida receituário branco") is None

    def test_denosumabe_120mg_retorna_denosumabe(self):
        assert principio_ativo_provavel("DENOSUMABE, 120mg, solucao injetavel") == "Denosumabe"


class TestNovosFarmacosAdicionados23Jul:
    @pytest.mark.parametrize("termo,esperado", [
        ("Aquisição de BICALUTAMIDA 50MG.", "Bicalutamida"),
        ("Fulvestranto 250mg/5ml", "Fulvestranto"),
        ("Medicamento Everolimo 0,5mg", "Everolimo"),
        ("Avelumabe 20mg/ml injetável", "Avelumabe"),
        ("AQUISIÇÃO DE CARFILZOMIBE", "Carfilzomibe"),
        ("TRAMETINIBE 2 MG", "Trametinibe"),
        ("Aquisição de medicamento: lapatinibe.", "Lapatinibe"),
        ("Apalutamida 60mg", "Apalutamida"),
        ("Ixazomibe 4mg cápsula", "Ixazomibe"),
    ])
    def test_termo_reconhecido(self, termo, esperado):
        assert eh_medicamento_onco_de_verdade(termo) is True
        assert principio_ativo_provavel(termo) == esperado
