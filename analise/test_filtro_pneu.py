"""
test_filtro_pneu.py — Regressão do filtro "é pneu de verdade?" (eh_pneu_de_verdade) e
da classificação de categoria (classificar_categoria).

Cobre os 8 bugs históricos documentados em filtro_pneu.py (achado 07-08/jul/2026)
+ 3 bugs achados na auditoria de 14/jul/2026 + contaminação de categoria achada
16/jul/2026 (Caminhão/Moto). Objetivo: nenhum bug documentado pode voltar em silêncio.
"""

import pytest

from filtro_pneu import classificar_categoria, eh_pneu_de_verdade


class TestPrefixoIgnoravel:
    def test_codigo_item_na_frente(self):
        assert eh_pneu_de_verdade("0006648 - PNEU 175/70 R14") is True

    def test_cota_ampla_na_frente(self):
        assert eh_pneu_de_verdade("[COTA AMPLA CONCORRÊNCIA] - PNEU 175/70 R14") is True

    def test_aquisicao_de_na_frente(self):
        assert eh_pneu_de_verdade("AQUISIÇÃO DE PNEUS 175/70 R14") is True


class TestPneumaticoAdjetivoVsSubstantivo:
    def test_pneumatico_como_nome_formal_do_produto(self):
        assert eh_pneu_de_verdade("PNEUMÁTICO PARA AUTOMÓVEL LEVE 175/70 R14") is True

    def test_pneumatico_como_adjetivo_sem_medida_e_false(self):
        assert eh_pneu_de_verdade("Cadeira de rodas com sistema pneumático de freio") is False


class TestCamaraGenerica:
    def test_camara_sem_de_ar_mas_com_medida_ampla(self):
        assert eh_pneu_de_verdade("CÂMARA DE FABRICAÇÃO NACIONAL REFERÊNCIA AR 750/16") is True

    def test_camara_refrigerada_nao_e_pneu(self):
        assert eh_pneu_de_verdade("CÂMARA REFRIGERADA MODELO 750/16 CIENTÍFICO LABORATÓRIO") is False

    def test_camara_municipal_nao_e_pneu(self):
        assert eh_pneu_de_verdade("CÂMARA MUNICIPAL DE SÃO PAULO, REFORMA DO PLENÁRIO 750/16") is False


class TestVeiculoInteiro:
    def test_ambulancia_citando_medida_de_fabrica_e_false(self):
        assert eh_pneu_de_verdade("AMBULÂNCIA TIPO A, PNEUS 185/65 R15 DE FÁBRICA") is False

    def test_furgao_van_e_false(self):
        assert eh_pneu_de_verdade("FURGAO/VAN 10+1 PASSAGEIROS 185/65 R15") is False

    def test_aquisicao_de_um_caminhao_e_false(self):
        """Achado 17/jul/26: artigo indefinido (um/uma) entre 'de' e o nome do
        veículo escapava do prefixo ignorável — R$630k classificado como pneu."""
        assert eh_pneu_de_verdade(
            "Aquisição de um caminhão pipa zero quilômetro, ano/modelo 2025/2025, "
            "com tanque de capacidade mínima de 10.000 litros, pneus 275/80 R22.5"
        ) is False

    def test_aquisicao_de_uma_ambulancia_e_false(self):
        assert eh_pneu_de_verdade(
            "Aquisição de uma ambulância tipo A, zero quilômetro, pneus 185/65 R15 de fábrica"
        ) is False


class TestServicoNoInicio:
    def test_montagem_no_inicio_e_false(self):
        assert eh_pneu_de_verdade("MONTAGEM DE PNEU ARO 175/70 R14") is False

    def test_produto_primeiro_com_servico_agregado_e_true(self):
        assert eh_pneu_de_verdade("PNEU 175/70 R14 - INCLUSO MONTAGEM E INSTALAÇÃO") is True


class TestRodaLigaLeve:
    def test_roda_liga_leve_e_false(self):
        assert eh_pneu_de_verdade("RODA LIGA LEVE 205/60 R16") is False

    def test_aro_liga_leve_e_false(self):
        assert eh_pneu_de_verdade("ARO 175/70 R13 FABRICADO EM LIGA LEVE") is False


class TestAcessorioAvulso:
    def test_bico_de_ar_e_false(self):
        assert eh_pneu_de_verdade("BICO DE AR INSTALADO PARA RODA ARO 175/70 R14") is False


class TestExclusaoMaquinaSoQuandoAmbiguo:
    def test_pneu_explicito_para_maquina_e_true(self):
        assert eh_pneu_de_verdade("Pneu para retroescavadeira, construção radial 17.5-25") is True

    def test_medida_solta_para_maquina_e_false(self):
        assert eh_pneu_de_verdade("17.5-25 PARA RETROESCAVADEIRA") is False

    def test_alinhamento_balanceamento_com_produto_explicito_e_true(self):
        assert eh_pneu_de_verdade("PNEU 175/70 R14 com alinhamento e balanceamento incluso") is True

    def test_alinhamento_balanceamento_sem_produto_explicito_e_false(self):
        assert eh_pneu_de_verdade("175/70 R14 ALINHAMENTO E BALANCEAMENTO") is False


class TestProibicaoDeReforma:
    def test_clausula_de_proibicao_nao_e_exclusao_de_servico(self):
        assert eh_pneu_de_verdade(
            "PNEU 175/70 R14 NÃO SE ACEITANDO PNEUS RECONDICIONADOS OU REFORMADOS"
        ) is True

    def test_clausula_sem_reforma_e_pneu_novo(self):
        """Achado 14/jul/26: mesma exigência de pneu novo, fraseada com 'sem' em vez de
        'não aceitando' — regressão real da 1ª versão do fix de ordem invertida."""
        assert eh_pneu_de_verdade(
            "PNEUS - Pneu 225 - 65 R16 - novo de fabrica, de primeiro uso, "
            "sem reforma ou recauchutagem, com garantia minima de 12 meses"
        ) is True

    def test_clausula_sem_com_lista_de_3_termos_e_pneu_novo(self):
        """Achado 14/jul/26, 2ª rodada: lista com vírgula ('sem reforma, recauchutagem,
        remoldagem ou recuperação') não batia o padrão de exatamente 2 termos com 'ou'."""
        assert eh_pneu_de_verdade(
            "PNEU 175 R70 13 - Pneu novo, de primeira linha, medida 175 R70 13. "
            "O produto deverá ser novo, original de fábrica, sem uso anterior, sem reforma, "
            "recauchutagem, remoldagem ou recuperação de qualquer tipo."
        ) is True

    def test_clausula_sem_uso_recauchutagem_ou_remoldagem_e_pneu_novo(self):
        assert eh_pneu_de_verdade(
            "PNEU 205X60X15 Quantidade: 04 pneus novos 205/60 R15. Condições de "
            "fornecimento: pneus novos, sem uso, recauchutagem ou remoldagem."
        ) is True

    def test_especificacao_de_durabilidade_futura_e_pneu_novo(self):
        """Achado 14/jul/26: 'capaz de suportar recauchutagem futura' é especificação de
        durabilidade do pneu novo, não descrição de serviço de recauchutagem."""
        assert eh_pneu_de_verdade(
            "Pneu 1000-20 novo de primeiro uso, construção diagonal, mínimo 16 lonas. "
            "Estrutura reforçada projetada para suportar, no mínimo, 02 recauchutagens, "
            "garantindo maior vida útil ao casco."
        ) is True

    def test_nao_sendo_resultante_de_e_pneu_novo(self):
        """Achado 14/jul/26, 3ª rodada: 3ª fraseologia de exigência de pneu novo, nem
        'não aceita' nem 'sem'."""
        assert eh_pneu_de_verdade(
            "Pneu 225/65R17 com selo de aprovação do INMETRO, pneu novo, certificado pelo "
            "Inmetro, não sendo resultante de nenhum processo de remoldagem e recauchutagem."
        ) is True

    def test_sem_defeitos_nao_e_negacao_de_recapagem_de_verdade(self):
        """Achado 14/jul/26, 3ª rodada: regressão da 2ª versão do fix — gap coringa
        genérico bateu 'sem DEFEITOS, a RECAPAGEM deverá ser...', que é serviço de
        recapagem de verdade (pneu usado, explícito no texto), não proibição."""
        assert eh_pneu_de_verdade(
            "Recapagem pneu 215/75 R17,5 pneu usado com as seguintes características, "
            "certificado pelo INMETRO, sem defeitos, a recapagem deverá ser com produto "
            "de qualidade."
        ) is False


# ── Achados 14/jul/2026 (auditoria dataviz/filtro) ──────────────────────────

class TestServicoOrdemInvertida:
    """Bug: exclusão de recauchutagem/recapagem exige 'termo DE pneu' — não
    pega quando o produto vem primeiro ('PNEU <termo>')."""

    def test_pneu_recauchutagem_ordem_invertida_e_false(self):
        assert eh_pneu_de_verdade("PNEU RECAUCHUTAGEM 17.5-25 L2") is False


class TestReparoNaoReconhecido:
    """Bug: 'reparo' nunca esteve em nenhuma lista de exclusão."""

    def test_reparo_de_pneu_e_false(self):
        assert eh_pneu_de_verdade("REPARO DE PNEU ARO 165/70 R13") is False


class TestPluralDeServico:
    """Bug: regex 'recapagem' não bate 'recapagens' (plural PT-BR troca M por NS, não é só +s)."""

    def test_recapagens_plural_e_false(self):
        assert eh_pneu_de_verdade("RECAPAGENS 205/75 R 16") is False

    def test_recapagem_singular_continua_false(self):
        """Regressão: 1ª tentativa do fix ('recapagens?') quebrou o singular sem querer."""
        assert eh_pneu_de_verdade("RECAPAGEM 205/75 R 16") is False

    def test_recauchutagem_singular_ordem_invertida_e_false(self):
        assert eh_pneu_de_verdade("PNEU RECAUCHUTAGEM 17.5-25 L2") is False

    def test_ressolagem_singular_e_false(self):
        assert eh_pneu_de_verdade("RESSOLAGEM PNEU 295X80X22,5") is False

    def test_sem_qualquer_uso_anterior_e_pneu_novo(self):
        """Achado 14/jul/26, 4ª rodada: 'qualquer' entre 'sem' e 'uso' bloqueava a ponte restrita."""
        assert eh_pneu_de_verdade(
            "PNEU 215/75 R17.5 - Pneu novo, sem qualquer uso anterior, reforma, "
            "recauchutagem, remoldagem ou recuperação."
        ) is True


# ── Achado 16/jul/2026 (auditoria de contaminação de categoria) ─────────────

class TestCategoriaCaminhaoNaoAroR:
    """Bug: regex antigo (r2[2-9]/r1[7-9].5) só cobria aro com 'R' explícito —
    perdia aro solto sem R e notação decimal/inteira de caminhão."""

    def test_aro_solto_sem_r_16_5_e_caminhao(self):
        assert classificar_categoria("PNEU 275/70 16.5 CAMINHÃO BAÚ") == "Caminhão"

    def test_otr_decimal_e_caminhao(self):
        assert classificar_categoria("PNEU 17.5-25 16 LONAS RETROESCAVADEIRA") == "Caminhão"

    def test_notacao_antiga_inteira_e_caminhao(self):
        assert classificar_categoria("PNEU 1000-20 16 LONAS RODOVIÁRIO") == "Caminhão"

    def test_numero_decreto_nao_e_falso_positivo(self):
        """Regressão: backtracking do grupo decimal reinterpretava separador de
        milhar ('5.123') como se fosse largura decimal de pneu de passeio."""
        assert classificar_categoria(
            "PNEU 175/70 R14 CONFORME DECRETO Nº 5.123 DE 2020"
        ) == "Passeio"


class TestCategoriaMotoNotacao:
    """Bug: notação de moto sem palavra-chave ('90/90-18') caía em Passeio."""

    def test_notacao_moto_com_barra_e_traco_e_moto(self):
        assert classificar_categoria("PNEU 90/90-18 TRASEIRO") == "Moto"

    def test_notacao_moto_so_com_barras_e_moto(self):
        assert classificar_categoria("PNEU 110/90/17") == "Moto"

    def test_par_indice_carga_velocidade_sem_aro_nao_e_moto(self):
        """Regressão: exigir o 3º grupo (aro) evita confundir 'IC 82/88' (índice
        de carga/velocidade solto, sem aro depois) com medida de moto."""
        assert classificar_categoria(
            "PNEU 175/65, R 14, ÍNDICE DE VELOCIDADE MÍNIMO T, ÍNDICE DE CARGA 82/88"
        ) != "Moto"

    def test_notacao_passeio_3_numeros_nao_e_moto(self):
        """Regressão: '175/70/13' (passeio escrito sem R) não pode virar Moto
        via substring '70/13' — lookbehind bloqueia trecho no meio do 3º número."""
        assert classificar_categoria("PNEU 175/70/13") != "Moto"

