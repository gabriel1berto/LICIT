"""Casos reais de objeto de edital (PNCP, 05/out/2026) usados pra calibrar filtro_pecas.py.
Rodar: python -m pytest test_filtro_pecas.py  (ou python test_filtro_pecas.py)"""

from filtro_pecas import TIPO_PECAS, TIPO_SERVICO, classificar_objeto_pecas

PECAS = [
    "AQUISIÇÃO DE PEÇAS DESTINADAS À MANUTENÇÃO PREVENTIVA E CORRETIVA DA FROTA DE CAMINHÕES PERTENCENTE AO MUNICÍPIO DE SIMÕES – PI",
    "Referente a aquisição de peças para manutenção de micro onibus da linha Volks e Mercedes, para atender a Secretaria Municipal de Saúde e Educação",
    "Registro de Preços para Aquisição de peças para manutenção veículos automotores.",
    "CONSUMÍVEIS VEICULARES INDUSTRIAIS E AUTOMOTIVOS",
    "Edital nº 119/2026 Aquisição de pneus e baterias.",
    "AQUISIÇÃO DE COMBUSTÍVEL ( GASOLINA COMUM) E ÓLEOS LUBRIFICANTE DE MOTOR",
    "Aquisição fracionada, de Óleos Lubrificantes e Filtros de Ar, Combustível e Óleo para atender a demanda junto a municipalidade",
    "CONTRATAÇÃO DE EMPRESA DO RAMO PERTINENTE PARA FORNECIMENTO DE PEÇAS DESTINADAS A REALIZAÇÃO DE MANUTENÇÃO DAS MÁQUINAS: LOTE 01 – PÁ CARREGADEIRA NH W130B",
    "AQUISIÇÃO PEÇAS DE REPOSIÇÃO, OLEOS LUBRIFICANTE, E GRAXAS AUTOMOTIVAS, VISANDO ATENDER AS NECESSIDADES DE MANUTENÇÃO PREVENTIVA E CORRETIVA DA FROTA DE ÔNIBUS",
    "Registro de Preços para seleção de proposta mais vantajosa para futura e eventual aquisição de peças de veículos para manutenção da frota das Secretarias e Fundos Municipais",
]
SERVICO = [
    "ATA DE REGISTRO DE PREÇOS PARA CONTRATAÇÃO DE EMPRESA ESPECIALIZADA EM MANUTENÇÃO CORRETIVA E PREVENTIVA DE VEICULOS INCLUINDO INSUMOS - OFICINA MECANICA",
    "Contratação de empresa especializada no fornecimento de peças e prestação de serviços de manutenção preventiva e corretiva em motocicletas, visando atender às necessidades da frota oficial",
    "CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA FORNECER PEÇAS E MÃO DE OBRA PARA MANUTENÇÃO CORRETIVA DO CAMINHÃO FORD CARGO 2629",
    "Contratação de empresa para realizar a manutenção do veículo placas JAY9F68 da Secretaria de Educação",
]
NAO = [
    # Os casos que motivaram o filtro: "amortecedor" no item, objeto sem nada de automotivo.
    "Contratação de empresa especializada para a fabricação e montagem de móveis planejados, sob medida, com fornecimento de materiais",
    "Contratação de empresa de engenharia para execução das obras de implantação de piso amortecedor e cercamento de áreas destinadas a parquinhos infantis",
    "Aquisição de material esportivo, para atender as demandas das secretaria municipal de Esporte, Lazer e Juventude",
    "Registro de preços para futura e eventual aquisição de peças para manutenção de equipamento médico hospitalar",
    # Contexto de veículo sem peça: compra de veículo, reboque, curso.
    "AQUISIÇÃO DE 01 (UM) VEÍCULO AUTOMOTOR NOVO.",
    "Aquisição de reboque veicular e engate para reboque para van Renault Master ano 2021.",
    "Aquisição de materiais e equipamentos para cursos de Mecânica Automotiva para o Campus Estrutural.",
    "CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA A PRESTAÇÃO DE SERVIÇOS DE TRANSFORMAÇÃO/ADAPTAÇÃO DE MICRO-ÔNIBUS DA MARCA VOLARE, EM UNIDADE MÓVEL DE SAÚDE DA MULHER.",
    # "proposta" contém "porta", "bens móveis" contém "móveis" — não pode confundir.
    "LEILÃO DE BENS MÓVEIS",
    "Formalização de Ata de Registro de Preços para futura e eventual aquisição de aparelhos de ar condicionado de 18.000 BTUs, com filtro de ar",
    None,
    "",
]


def test_pecas():
    for t in PECAS:
        assert classificar_objeto_pecas(t) == TIPO_PECAS, t


def test_servico():
    for t in SERVICO:
        assert classificar_objeto_pecas(t) == TIPO_SERVICO, t


def test_nao_automotivo():
    for t in NAO:
        assert classificar_objeto_pecas(t) is None, t


if __name__ == "__main__":
    test_pecas(); test_servico(); test_nao_automotivo()
    print("ok")
