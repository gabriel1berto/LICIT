#!/usr/bin/env python3
"""
filtro_onco.py — Classificação "é medicamento oncológico de verdade?" no nível
do ITEM (descrição real, não título de processo). Espelha filtro_pneu.py mas
pro vocabulário validado em sessão de estudo (double/triple-check):

  - Nome genérico completo: funciona bem, baixo falso-positivo.
  - Nome de marca comercial: necessário — parte de compra judicial cita só a
    marca (Herceptin/Avastin/Glivec/Sutent), sem o genérico no texto.
  - Abreviação clínica (5-FU, MTX, VCR, CTX, VP-16, Ara-C, ADR): TESTADO E
    REJEITADO — colide com código de equipamento/veículo/evento. Não usar.

Match por substring (case/acento-insensível) contra a lista de termos —
suficiente pro volume de vocabulário atual (~109 termos). Se a lista crescer
muito (500+), trocar por regex compilado ou Aho-Corasick.
"""

import unicodedata

from coletor_onco import GENERICOS, MARCAS

TERMOS_GENERICOS = sorted(GENERICOS, key=len, reverse=True)
TERMOS_MARCAS = sorted(MARCAS, key=len, reverse=True)


def _normalizar(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.upper()


_GENERICOS_NORM = [(t, _normalizar(t)) for t in TERMOS_GENERICOS]
_MARCAS_NORM = [(t, _normalizar(t)) for t in TERMOS_MARCAS]


def eh_medicamento_onco_de_verdade(descricao: str) -> bool:
    """True se a descrição do item cita algum fármaco oncológico validado
    (genérico ou marca) — não usa a palavra "oncológico" (ver estudo: aparece
    em obra/hospedagem, não em item de fármaco de verdade)."""
    norm = _normalizar(descricao)
    if not norm:
        return False
    for _, termo_norm in _GENERICOS_NORM:
        if termo_norm in norm:
            return True
    for _, termo_norm in _MARCAS_NORM:
        if termo_norm in norm:
            return True
    return False


# Classe farmacológica — 6 categorias fixas, mesmo padrão de `categoria`
# fixa do pneu (Passeio/Caminhão/Moto/Agrícola/Câmara de ar). Mapeamento por
# nome exato (não regex — o termo já vem casado por principio_ativo_provavel,
# não precisa reclassificar o texto bruto de novo).
CLASSE_FARMACO: dict[str, str] = {}
for _t in ["Ciclofosfamida", "Clorambucila", "Melfalana", "Ifosfamida", "Bussulfano",
           "Temozolomida", "Dacarbazina", "Carmustina", "Lomustina"]:
    CLASSE_FARMACO[_t] = "Alquilante"
for _t in ["Metotrexato", "Pemetrexede", "Mercaptopurina", "Fludarabina", "Cladribina",
           "Citarabina", "Fluorouracila", "Gencitabina", "Capecitabina", "Azacitidina", "Decitabina"]:
    CLASSE_FARMACO[_t] = "Antimetabolito"
for _t in ["Vimblastina", "Vincristina", "Vinorelbina", "Etoposideo", "Paclitaxel",
           "Docetaxel", "Cabazitaxel", "Topotecana", "Irinotecano",
           "Doxorrubicina", "Daunorrubicina", "Epirrubicina", "Idarrubicina",
           "Mitoxantrona", "Bleomicina", "Mitomicina",
           "Cisplatina", "Carboplatina", "Oxaliplatina"]:
    CLASSE_FARMACO[_t] = "Quimioterapico classico"
for _t in ["Imatinibe", "Dasatinibe", "Nilotinibe", "Gefitinibe", "Erlotinibe",
           "Afatinibe", "Osimertinibe", "Vemurafenibe", "Dabrafenibe", "Crizotinibe",
           "Sunitinibe", "Sorafenibe", "Pazopanibe", "Regorafenibe", "Lenvatinibe",
           "Cabozantinibe", "Ibrutinibe", "Acalabrutinibe", "Palbociclibe", "Ribociclibe",
           "Abemaciclibe", "Olaparibe", "Niraparibe", "Enzalutamida", "Glivec", "Sutent",
           "Tagrisso", "Ibrance", "Zelboraf", "Xtandi"]:
    CLASSE_FARMACO[_t] = "Inibidor de quinase/alvo molecular"
for _t in ["Rituximabe", "Trastuzumabe", "Pertuzumabe", "Bevacizumabe", "Cetuximabe",
           "Panitumumabe", "Nivolumabe", "Pembrolizumabe", "Atezolizumabe", "Durvalumabe",
           "Ipilimumabe", "Daratumumabe", "Obinutuzumabe", "Denosumabe",
           "Keytruda", "Opdivo", "Herceptin", "Avastin", "Enhertu"]:
    CLASSE_FARMACO[_t] = "Anticorpo monoclonal"
for _t in ["Abiraterona", "Tamoxifeno", "Letrozol", "Anastrozol", "Exemestano",
           "Leuprorrelina", "Goserrelina", "Zytiga"]:
    CLASSE_FARMACO[_t] = "Hormonal/endocrino"


def classificar_classe_farmaco(principio_ativo: str | None) -> str:
    if not principio_ativo:
        return "Outro"
    return CLASSE_FARMACO.get(principio_ativo, "Outro")


def principio_ativo_provavel(descricao: str) -> str | None:
    """1º termo (genérico tem prioridade sobre marca) que casa na descrição.
    Termos mais longos primeiro evita casar substring de termo mais curto
    dentro de um mais específico (ex: 'Cisplatina' vs termo maior que a contenha)."""
    norm = _normalizar(descricao)
    if not norm:
        return None
    for termo, termo_norm in _GENERICOS_NORM:
        if termo_norm in norm:
            return termo
    for termo, termo_norm in _MARCAS_NORM:
        if termo_norm in norm:
            return termo
    return None
