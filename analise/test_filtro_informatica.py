"""Testes do filtro_informatica.py — descrições no formato real do PNCP."""
import pytest

from filtro_informatica import classificar_item, item_valido_valor, objeto_eh_servico, selo_get

CASOS = [
    ("NOBREAK 1500VA BIVOLT COM 6 TOMADAS", "Nobreak", "sim"),
    ("Nobreak 1,2 kVA, entrada bivolt automática", "Nobreak", "sim"),
    ("NOBREAK 10KVA SENOIDAL ONLINE", "Nobreak", "nao"),
    ("No-break 2.200 VA", "Nobreak", "sim"),
    ("Nobreak para computador", "Nobreak", "talvez"),
    ("ESTABILIZADOR 300VA", "Estabilizador", "nao"),
    ('MONITOR LED 23,8" FULL HD', "Monitor", "sim"),
    ("Monitor 21,5 polegadas widescreen", "Monitor", "sim"),
    ("MONITOR 32 POLEGADAS 4K", "Monitor", "nao"),
    ("Monitor de vídeo LED", "Monitor", "talvez"),
    ("MONITOR MULTIPARAMÉTRICO PARA UTI", None, None),
    ("TECLADO USB ABNT2 PRETO", "Teclado/Mouse", "sim"),
    ("KIT TECLADO E MOUSE SEM FIO", "Teclado/Mouse", "sim"),
    ("Mouse óptico USB 1200 dpi", "Teclado/Mouse", "sim"),
    ("Mouse pad com apoio de punho", None, None),
    ("TECLADO MUSICAL 61 TECLAS", None, None),
    ("COMPUTADOR DESKTOP I5, 8GB, SSD 256GB, com teclado, mouse e monitor 21,5", "Computador", "talvez"),
    ("NOTEBOOK 15,6 CORE I5", "Notebook", "nao"),
    ("WEBCAM FULL HD 1080P COM MICROFONE", "Webcam", "nao"),
    ("HEADSET USB COM MICROFONE", "Headset/Fone", "sim"),
    ("PROJETOR MULTIMÍDIA 3500 LUMENS", "Projetor", "sim"),
    ("Tela de projeção retrátil 100 polegadas", None, None),
    ("SSD 480GB SATA III", "Armazenamento", "sim"),
    ("Impressora multifuncional laser", "Impressora", "nao"),
    ("Serviço de manutenção de nobreak", None, None),
    ("Toner para impressora HP", None, None),
    ("Bateria para nobreak 12V 7Ah", None, None),
    ("Arroz tipo 1", None, None),
    # achados reais 19/nov/2026 (primeira coleta, termo Nobreak)
    ("Tomógrafo Computadorizado Odontológico capacidade: até 150", None, None),
    ("Autoclave Para Esterilização tipo: horizontal de solo, funcionamento: pré vácuo, com impressora", None, None),
    ("Aparelho Ultrassonografia frequência emissão: 1 e 3, voltagem: 110 / 220, com teclado", None, None),
    ("Computador Portátil (Notebook): que esteja em linha de produção pelo fabricante", "Notebook", "nao"),
    ("Monitor De Imagem E Cirurgia - Uso Médico tipo tela: tela em lcd colorida", None, None),
    ("Projetor Optótipos tipo: manual", None, None),
    ("Fonte Alimentação Ininterrupta características adicionais: mín 4 tomadas", "Nobreak", "talvez"),
    ("Fone Ouvido tipo: headset, comprimento fio: mínimo 1,5", "Headset/Fone", "sim"),
    ("Monitor Computador tamanho tela: 23 a 30, tipo de tela: led", "Monitor", "sim"),
    ("Monitor Imagem tamanho tela: 25, tipo tela: led", "Monitor", "sim"),
    ("MONITOR LED COM TAMANHO MÍNIMO DE 19,5 POLEGADAS", "Monitor", "sim"),
    ("NOBREAK: POTÊNCIA NOMINAL MÍNIMA DE 1.200 VA; - MÍNIMO DE 6 TOMADAS", "Nobreak", "sim"),
    ("SUPORTE: ARTICULADO DE PAREDE PARA TVS, MONITORES LCD", None, None),
    ("Bateria Recarregável tipo: estacionária e selada, para nobreak", None, None),
    ("CAIXA DE SOM COMPUTADOR. <p><strong>CAIXA DE SOM PARA COMPUTADOR, </strong>sistema de &aacute;udio", "Caixa de som", "sim"),
    ("Caixa Acústica aplicação: entretenimento, karaokê, bluetooth", "Caixa de som", "talvez"),
    ("Câmera Videoconferência características adicionais: webcam", "Webcam", "nao"),
    ("Microcomputador memória ram: superior a 8", "Computador", "talvez"),
    ("Memória Portátil Microcomputador capacidade memória: 128, interface: usb", "Armazenamento", "sim"),
]


@pytest.mark.parametrize("descricao,cat,cob", CASOS)
def test_classificar_item(descricao, cat, cob):
    assert classificar_item(descricao) == (cat, cob)


def test_selo():
    assert selo_get(["sim", "talvez"]) == "100% GET"
    assert selo_get(["sim", "nao"]) == "Parcial GET"
    assert selo_get(["nao"]) == "Fora da GET"
    assert selo_get([None]) == "Sem item de informática"


# Objeto do edital é serviço/locação (achado 19/nov/2026, 1ª coleta Nordeste): item
# "NOTEBOOK" num edital de locação de TI não é compra; "Monitor de Apoio" é cargo.
OBJETOS = [
    ("REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL CONTRATAÇÃO DE EMPRESA(S) ESPECIALIZADA(S) PARA PRESTAÇÃO "
     "CONTINUADA DE SERVIÇOS DE LOCAÇÃO DE EQUIPAMENTOS DE TECNOLOGIA DA INFORMAÇÃO", True),
    ("Contratação, com vigência inicial de 4 (quatro) anos, de serviços de outsourcing de impressão", True),
    ("Credenciamento de pessoas físicas e/ou MEI para a prestação de serviços de Monitor de Apoio ao Transporte", True),
    ("AQUISIÇÃO DE EQUIPAMENTOS DE INFORMÁTICA PARA AS SECRETARIAS MUNICIPAIS", False),
    ("Registro de preços para aquisição de material de informática e prestação de serviço de instalação", False),
    ("SRP PARA CONTRATAÇÃO DE EMPRESA PARA FORNECIMENTO DE NOBREAKS E ESTABILIZADORES", False),
    ("", False),
]


@pytest.mark.parametrize("objeto,esperado", OBJETOS)
def test_objeto_servico(objeto, esperado):
    assert objeto_eh_servico(objeto) is esperado


def test_valor_unitario_absurdo_nao_conta():
    # "NOTEBOOK I5" a R$871 mil/un (Caucaia/CE) — lote ou erro de digitação, mesmo teto do pneu
    assert item_valido_valor(871274.25) is False
    assert item_valido_valor(4500.0) is True
    assert item_valido_valor(None) is True
