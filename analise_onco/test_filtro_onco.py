"""
test_filtro_onco.py — Regressão do filtro "é medicamento oncológico de verdade?"
(eh_medicamento_onco_de_verdade) e de principio_ativo_provavel().

Cobre os 5 falsos positivos de uso duplo achados no double-check de 23/jul/2026
(Talidomida/Ácido zoledrônico/Denosumabe/Metotrexato/Tretinoína — mesma substância,
indicação NÃO-oncológica confirmada por amostra real). Objetivo: nenhum desses
bugs pode voltar em silêncio.
"""

import pytest

from filtro_onco import classificar_classe_farmaco, eh_medicamento_onco_de_verdade, principio_ativo_provavel


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


class TestOrdemInvertidaDeCatalogo:
    """Bug MAIOR achado na auditoria avançada de 23/jul/26: catálogo do PNCP às vezes
    escreve o nome do princípio ativo composto em ordem invertida, estilo dicionário/
    catálogo farmacêutico ("ZOLEDRONICO, ACIDO" em vez de "ACIDO ZOLEDRONICO") — a
    checagem por substring exato nunca batia esses casos. 17 itens reais medidos contra
    a base inteira (15 zoledrônico + 2 trióxido de arsênio) — os únicos 2 termos
    multi-palavra do vocabulário, escopo então totalmente delimitado."""

    def test_zoledronico_acido_ordem_invertida_e_true(self):
        assert eh_medicamento_onco_de_verdade(
            "ZOLEDRONICO, acido 4mg injetavel, frasco-ampola."
        ) is True
        assert principio_ativo_provavel(
            "ZOLEDRONICO, acido 4mg injetavel, frasco-ampola."
        ) == "Acido zoledronico"

    def test_zoledronico_acido_ordem_invertida_ainda_respeita_uso_duplo(self):
        """Regressão: ordem invertida não pode furar a exclusão de uso duplo (5mg/
        Aclasta = osteoporose) — só resolve o problema de ORDEM, não desliga a
        checagem de dose/marca já existente."""
        assert eh_medicamento_onco_de_verdade(
            "ZOLEDRONICO, acido 5mg injetavel, frasco-ampola."
        ) is False

    def test_arsenio_trioxido_ordem_invertida_e_true(self):
        assert eh_medicamento_onco_de_verdade(
            "ARSENIO TRIOXIDO, 2MG/ML, SOLUCAO INJETAVEL, AMPOLA 6ML"
        ) is True

    def test_ordem_normal_continua_true(self):
        """Regressão: não pode quebrar a ordem normal (não invertida) já coberta."""
        assert eh_medicamento_onco_de_verdade("Ácido Zoledrônico 4mg solução injetável") is True
        assert eh_medicamento_onco_de_verdade("Trioxido de arsenio 1mg/ml solução") is True


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


class TestServicoNaoEhCompraDeMedicamento:
    def test_infusao_intravenosa_e_servico_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("INFUSAO INTRAVENOSA DE MEDICAMENTO ACIDO ZOLEDRONICO", "S") is False

    def test_manipulacao_e_servico_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("Serviço de Manipulação de Ciclofosfamida", "S") is False

    def test_material_normal_continua_true(self):
        assert eh_medicamento_onco_de_verdade("Ácido Zoledrônico 4mg solução injetável", "M") is True

    def test_sem_material_ou_servico_informado_nao_quebra(self):
        assert eh_medicamento_onco_de_verdade("Ácido Zoledrônico 4mg solução injetável") is True


class TestBevacizumabeMitomicinaOftalmoVsOncologico:
    def test_avastin_intravitrea_e_oftalmo_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("APLICAÇÃO DE INJEÇÃO INTRAVÍTREA DE AVASTIN NO OLHO DIREITO", "M") is False

    def test_avastin_monocular_e_oftalmo_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("APLICAÇÃO DE MEDICAMENTO QUIMIOTERÁPICO AVASTIN - 1ª SESSÃO - MONOCULAR", "M") is False

    def test_mitomicina_pterigio_e_oftalmo_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("CIRURGIA DE PTERÍGIO COM RECOBRIMENTO CONJUNTIVAL + MITOMICINA", "M") is False

    def test_bevacizumabe_sem_contexto_continua_ambiguo_true(self):
        # sem sinal nenhum de oftalmo -- mantém True (risco de jogar fora compra
        # oncológica real > risco de manter ambígua), ver comentário em filtro_onco.py
        assert eh_medicamento_onco_de_verdade("BEVACIZUMABE 25 MG/ML/FRASCO", "M") is True

    def test_mitomicina_oncologica_sem_contexto_continua_true(self):
        assert eh_medicamento_onco_de_verdade("Mitomicina 40mg pó liofilizado para solução injetável", "M") is True


class TestSutentRemovidoDoVocabulario:
    def test_sutentacao_nao_e_mais_falso_positivo(self):
        assert eh_medicamento_onco_de_verdade("ESTRUTURA DE SUTENTACAO EM TUBULAR") is False

    def test_sunitinibe_generico_continua_cobrindo_a_droga(self):
        assert eh_medicamento_onco_de_verdade("Sunitinibe 50mg cápsula") is True


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


class TestClasseFarmacoCoberturaCompleta:
    """Achado 23/jul/26 (auditoria avançada): 19 de 92 genéricos não tinham entrada em
    CLASSE_FARMACO (caíam em 'Outro' silenciosamente), incluindo vários termos
    adicionados nesta mesma sessão (Everolimo/Trametinibe/Lapatinibe/Avelumabe/
    Bicalutamida/Apalutamida/Fulvestranto) — encaixe claro numa das 6 categorias já
    existentes. Os outros 12 (Trioxido de arsenio, Acido zoledronico, Hidroxiureia,
    Asparaginase, Lenalidomida, Carfilzomibe, Bortezomibe, Venetoclaxe, Talidomida,
    Tretinoina, Eribulina, Ixazomibe) NÃO têm encaixe limpo em nenhuma das 6 categorias
    fixas (são IMiD/inibidor de proteassoma/bisfosfonato/enzima/diferenciador — cada um
    mereceria categoria própria) — não forçados aqui, ficam 'Outro' até decisão do
    usuário sobre expandir a taxonomia (ver relatório da auditoria)."""

    @pytest.mark.parametrize("termo,classe_esperada", [
        ("Everolimo", "Inibidor de quinase/alvo molecular"),
        ("Trametinibe", "Inibidor de quinase/alvo molecular"),
        ("Lapatinibe", "Inibidor de quinase/alvo molecular"),
        ("Avelumabe", "Anticorpo monoclonal"),
        ("Bicalutamida", "Hormonal/endocrino"),
        ("Apalutamida", "Hormonal/endocrino"),
        ("Fulvestranto", "Hormonal/endocrino"),
    ])
    def test_classe_farmaco_dos_termos_novos(self, termo, classe_esperada):
        assert classificar_classe_farmaco(termo) == classe_esperada
