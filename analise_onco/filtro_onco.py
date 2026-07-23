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

import re
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


# Achado 23/jul/2026 (double-check falso-positivo/negativo): 5 termos do vocabulário
# são fármacos de uso duplo — mesma substância, indicação NÃO-oncológica é a maior
# fatia real da amostra (confirmado por dose/via/formulação no texto, não suposição).
# Cada entrada = (principio_ativo exato de CLASSE_FARMACO/principio_ativo_provavel,
# regex que sinaliza uso NÃO-oncológico — se casar, excluir mesmo achando o termo).
_RE_TALIDOMIDA_FORMULARIO = re.compile(
    r"\b(BLOCO|RECEITU[AÁ]RIO|NOTIFICA[CÇ][AÃ]O DE RECEITA|TELEMEDICINA|TELERECEITA)\b"
)
_RE_ACLASTA_OU_5MG = re.compile(r"\bACLASTA\b|\b5\s*MG\b")
_RE_ZOLEDRONICO_4MG = re.compile(r"\b4\s*MG\b|\bZOMETA\b")
_RE_DENOSUMABE_60MG = re.compile(r"\b60\s*MG\b")
_RE_DENOSUMABE_120MG = re.compile(r"\b120\s*MG\b")
_RE_METOTREXATO_BAIXA_DOSE = re.compile(r"\b2[,.]5\s*MG\b.*\bCOMPRIMIDO\b|\bCOMPRIMIDO\b.*\b2[,.]5\s*MG\b")
_RE_TRETINOINA_TOPICO = re.compile(r"\bMG\s*/\s*G\b|\bCREME\b|\bGEL\b|\bVITACID\b|\bT[OÓ]PIC[OA]\b|\bDERMATOL")

# Achado 23/jul/2026 (double-check profundo, 2ª rodada): Bevacizumabe (Avastin) e
# Mitomicina têm uso oftalmológico real e comum no Brasil (Avastin intravítreo — anti-
# VEGF fora de bula pra degeneração macular/retinopatia, MUITO comum em tender
# municipal por ser barato; Mitomicina em cirurgia de pterígio/glaucoma) — sinal
# explícito de contexto ocular no texto exclui, mas NÃO exclui menção "pelada" (só
# "Bevacizumabe"/"Avastin" sem contexto) — aí é ambíguo de verdade, não dá pra decidir
# só pelo texto, risco de jogar fora compra oncológica real é maior que o de manter
# alguma ambígua dentro.
_RE_CONTEXTO_OFTALMO = re.compile(
    r"INTRAVITR|INTRA[ -]VITR|\bOCULAR\b|\bOLHO\b|\bOLHOS\b|\bRETINA\b|\bMACULAR\b|"
    r"V[IÍ]TREO|PTER[IÍ]GIO|CONJUNTIV|\bMONOCULAR\b|\bBINOCULAR\b|\bOFTALMO"
)


# Achado 23/jul/2026 (auditoria avançada, MAIOR achado desta rodada): catálogo do PNCP
# às vezes escreve o nome do princípio ativo composto em ordem invertida, estilo
# dicionário/catálogo farmacêutico — "ZOLEDRONICO, ACIDO" em vez de "ACIDO ZOLEDRONICO",
# "ARSENIO TRIOXIDO" em vez de "TRIOXIDO DE ARSENIO". Substring exato contra o termo
# nunca batia esses casos — 17 itens reais medidos contra a base inteira (15
# zoledrônico + 2 trióxido de arsênio, os únicos 2 termos multi-palavra do vocabulário
# atual — escopo listado explicitamente, não regex genérico de permutação de palavras,
# pra não abrir risco de match solto se o vocabulário crescer com termo multi-palavra novo
# sem essa entrada ser adicionada deliberadamente).
_RE_ORDEM_INVERTIDA: dict[str, re.Pattern] = {
    "Acido zoledronico": re.compile(r"ZOLEDRONICO[,\s]+ACIDO"),
    "Trioxido de arsenio": re.compile(r"ARSENIO[,\s]+TRI[OÓ]XIDO"),
}


def _bate_termo(termo: str, termo_norm: str, norm: str) -> bool:
    """True se o termo aparece na descrição — substring direto OU, pra termos
    compostos com ordem invertida conhecida (ver _RE_ORDEM_INVERTIDA acima), a
    variante invertida."""
    if termo_norm in norm:
        return True
    padrao_invertido = _RE_ORDEM_INVERTIDA.get(termo)
    return bool(padrao_invertido and padrao_invertido.search(norm))


def _eh_falso_positivo_uso_duplo(termo: str, norm: str) -> bool:
    """True quando o termo bateu mas o contexto (dose/via/formulação/tipo de item)
    indica a indicação NÃO-oncológica da mesma substância — ver comentário acima."""
    if termo == "Talidomida":
        return bool(_RE_TALIDOMIDA_FORMULARIO.search(norm))
    if termo == "Acido zoledronico":
        if _RE_ZOLEDRONICO_4MG.search(norm):
            return False  # 4mg/Zometa explícito — oncológico, não excluir
        return bool(_RE_ACLASTA_OU_5MG.search(norm))
    if termo == "Denosumabe":
        if _RE_DENOSUMABE_120MG.search(norm):
            return False  # 120mg/Xgeva explícito — oncológico, não excluir
        return bool(_RE_DENOSUMABE_60MG.search(norm))
    if termo == "Metotrexato":
        return bool(_RE_METOTREXATO_BAIXA_DOSE.search(norm))
    if termo == "Tretinoina":
        return bool(_RE_TRETINOINA_TOPICO.search(norm))
    if termo in ("Bevacizumabe", "Avastin", "Mitomicina"):
        return bool(_RE_CONTEXTO_OFTALMO.search(norm))
    return False


def eh_medicamento_onco_de_verdade(descricao: str, material_ou_servico: str | None = None) -> bool:
    """True se a descrição do item cita algum fármaco oncológico validado
    (genérico ou marca) — não usa a palavra "oncológico" (ver estudo: aparece
    em obra/hospedagem, não em item de fármaco de verdade).

    Alguns termos são de uso duplo (mesma substância, indicação não-oncológica
    também existe — osteoporose/reumatologia/dermatologia/oftalmologia/formulário
    de papelaria controlada) — ver _eh_falso_positivo_uso_duplo(), achado 23/jul/2026.

    material_ou_servico="S" (serviço, não material) exclui direto — achado 23/jul/2026,
    2ª rodada: amostra de 57 itens "S" marcados onco eram quase todos infusão/aplicação/
    manipulação/importação (SERVIÇO em torno do fármaco, não a compra do fármaco em si),
    não compra real de medicamento pro propósito de "tamanho de mercado"."""
    if material_ou_servico == "S":
        return False
    norm = _normalizar(descricao)
    if not norm:
        return False
    for termo, termo_norm in _GENERICOS_NORM:
        if _bate_termo(termo, termo_norm, norm):
            if _eh_falso_positivo_uso_duplo(termo, norm):
                continue
            return True
    for termo, termo_norm in _MARCAS_NORM:
        if _bate_termo(termo, termo_norm, norm):
            if _eh_falso_positivo_uso_duplo(termo, norm):
                continue
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
           "Tagrisso", "Ibrance", "Zelboraf", "Xtandi",
           # achado 23/jul/26 (auditoria avançada): faltavam desde que foram adicionados
           # ao vocabulário nesta mesma sessão — inibidores de quinase/alvo molecular
           # de encaixe claro (mTOR/MEK/dual EGFR-HER2), caíam em "Outro" silenciosamente.
           "Everolimo", "Trametinibe", "Lapatinibe"]:
    CLASSE_FARMACO[_t] = "Inibidor de quinase/alvo molecular"
for _t in ["Rituximabe", "Trastuzumabe", "Pertuzumabe", "Bevacizumabe", "Cetuximabe",
           "Panitumumabe", "Nivolumabe", "Pembrolizumabe", "Atezolizumabe", "Durvalumabe",
           "Ipilimumabe", "Daratumumabe", "Obinutuzumabe", "Denosumabe",
           "Keytruda", "Opdivo", "Herceptin", "Avastin", "Enhertu",
           # achado 23/jul/26: anticorpo monoclonal anti-PD-L1, mesmo encaixe claro.
           "Avelumabe"]:
    CLASSE_FARMACO[_t] = "Anticorpo monoclonal"
for _t in ["Abiraterona", "Tamoxifeno", "Letrozol", "Anastrozol", "Exemestano",
           "Leuprorrelina", "Goserrelina", "Zytiga",
           # achado 23/jul/26: antiandrógenos (mesma classe de Enzalutamida acima) e
           # antagonista de receptor de estrogênio (mesma classe de Tamoxifeno/Letrozol/
           # Anastrozol/Exemestano) — encaixe claro, faltavam desde a adição ao vocabulário.
           "Bicalutamida", "Apalutamida", "Fulvestranto"]:
    CLASSE_FARMACO[_t] = "Hormonal/endocrino"
# achado 23/jul/26: outros 12 genéricos sem CLASSE_FARMACO (Trioxido de arsenio,
# Acido zoledronico, Hidroxiureia, Asparaginase, Lenalidomida, Carfilzomibe,
# Bortezomibe, Venetoclaxe, Talidomida, Tretinoina, Eribulina, Ixazomibe) NÃO têm
# encaixe limpo em nenhuma das 6 categorias fixas (são IMiD/inibidor de proteassoma/
# bisfosfonato/enzima/diferenciador — cada família mereceria categoria própria).
# Deliberadamente não forçados numa categoria errada — ficam "Outro" até decisão do
# usuário sobre expandir a taxonomia de 6 pra mais categorias (ver relatório de
# auditoria 23/jul/26). Não afeta eh_medicamento_onco_de_verdade (só a quebra por classe).


def classificar_classe_farmaco(principio_ativo: str | None) -> str:
    if not principio_ativo:
        return "Outro"
    return CLASSE_FARMACO.get(principio_ativo, "Outro")


def principio_ativo_provavel(descricao: str) -> str | None:
    """1º termo (genérico tem prioridade sobre marca) que casa na descrição —
    pulando termo de uso duplo cujo contexto indica indicação não-oncológica
    (mesma exclusão de eh_medicamento_onco_de_verdade(), pra não devolver
    'Talidomida' como princípio ativo de um item que na verdade é bloco de
    receita). Termos mais longos primeiro evita casar substring de termo mais
    curto dentro de um mais específico (ex: 'Cisplatina' vs termo maior que a
    contenha)."""
    norm = _normalizar(descricao)
    if not norm:
        return None
    for termo, termo_norm in _GENERICOS_NORM:
        if _bate_termo(termo, termo_norm, norm) and not _eh_falso_positivo_uso_duplo(termo, norm):
            return termo
    for termo, termo_norm in _MARCAS_NORM:
        if _bate_termo(termo, termo_norm, norm) and not _eh_falso_positivo_uso_duplo(termo, norm):
            return termo
    return None
