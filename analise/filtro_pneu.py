#!/usr/bin/env python3
"""
filtro_pneu.py — Filtro "é pneu de verdade?" único, compartilhado entre
coletor_pncp.py, coletor_pncp_detalhe.py e pncp_radar.py. Zero dependência
pesada de propósito (só `re`) — importável de qualquer script sem puxar
psycopg2/sqlalchemy/etc junto.

Histórico: regex já passou por 8 bugs documentados corrigidos (ver
analise/README.md e página "Dados públicos" no Notion). Antes de 07/jul/2026
essa lógica estava duplicada e divergente em 3 lugares (base_pneu.sql,
coletor_pncp_detalhe.py, pncp_radar.py) — cada um corrigido em momento
diferente, nenhum sincronizado com os outros. Esse módulo é a fonte única.

2 níveis de classificação:
  - Nível PROCESSO (classificar_pneu): texto corrido de título+descrição do
    processo inteiro — mais fraco, usado só pra pré-filtro antes de abrir
    detalhe/itens (economiza chamada de API em processo obviamente não-pneu).
  - Nível ITEM (eh_pneu_de_verdade): descrição estruturada de 1 item de
    catálogo — muito mais confiável, é o filtro que decide de fato.
"""

import re

# ── Nível ITEM — mesmo regex validado, ver README.md ───────────────────────

# achado 07/jul/26 auditando falso negativo real em massa (jun-jul/2026, ver Notion "PNCP
# Radar"): catálogo real prefixa "pneu" com código de item ("0006648 - PNEU..."), cota de
# licitação ("[COTA AMPLA CONCORRÊNCIA] - PNEU...") ou verbo de aquisição ("AQUISIÇÃO DE
# PNEUS..."). Âncora estrita `^\s*pneus?` perdia todos esses — permite prefixo curto e
# conhecido antes de "pneu"/"câmara", sem abrir mão da âncora (ainda exige que "pneu" seja
# o PRODUTO logo no início, só ignora ruído burocrático na frente dele).
RE_PREFIXO_IGNORAR = (
    r"(?:\[.{0,40}?\]\s*[-–]?\s*)?"                                    # "[COTA ...] - "
    r"(?:(?:lote\s+)?\d{1,10}\s*[-–]\s*)?"                              # "0006648 - " / "Lote 1 - "
    r"(?:(?:aquisi[çc][ãa]o|fornecimento|contrata[çc][ãa]o|compra)\s+"
    r"(?:parcelada\s+)?(?:de\s+)?)?"                                    # "aquisição de "
)
# "pneumático(s)" é o nome formal/técnico do produto em bastante edital ("PNEUMÁTICO PARA
# AUTOMÓVEL LEVE...", "PNEUMÁTICO NOVO DE 1ª LINHA..."), não só adjetivo (bug histórico
# "cadeira pneumática"/"sistema pneumático") — mas como âncora exige ser a 1ª palavra do
# ITEM (não do processo), "pneumático" no início de um item de catálogo é sempre o produto
# em si, nunca "cadeira pneumática" (que começaria com "cadeira", não com "pneumático").
RE_PNEU_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}(?:pneus?|pneum[áa]ticos?)\b", re.IGNORECASE)
RE_CAMARA_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}c[âa]mara\s+(de\s+)?ar\b", re.IGNORECASE)
# "CÂMARA DE FABRICAÇÃO NACIONAL... REFERÊNCIA AR 750/16" — câmara de pneu de verdade, mas
# "de ar" não vem logo depois de "câmara" (RE_CAMARA_INICIO não bate). Fallback: aceita
# "câmara" sozinho no início SE tiver medida ampla em algum lugar da descrição — protege
# contra ruído tipo "Câmara Municipal"/bola esportiva "com câmara butil" (não tem medida de
# pneu, isso nunca bate RE_MEDIDA_AMPLA).
RE_CAMARA_GENERICA = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}c[âa]mara\b", re.IGNORECASE)
# achado 08/jul/26: "CÂMARA REFRIGERADA - Refrigerador modelo científico..." (freezer de
# laboratório) bateu RE_CAMARA_GENERICA + alguma dimensão do equipamento bateu
# RE_MEDIDA_AMPLA por coincidência — "câmara" tem outros sentidos fora de pneu (câmara
# frigorífica, câmara municipal, câmara de vídeo). Exclui explicitamente antes de aceitar.
RE_CAMARA_NAO_PNEU = re.compile(r"c[âa]mara\s+(refrigerad|fria\b|frigor[íi]fic|municipal|de\s+v[íi]deo|escura)", re.IGNORECASE)
RE_MEDIDA_AMPLA = re.compile(r"\d{2,5}[.,]?\d?\s*[-/xX]\s*\d{2,3}([.,]\d)?\b")
# aceita barra opcional antes do R ("215/75/R17.5") e sufixo de letra colado no aro
# ("R14C" — C de comercial/reforçado, sem espaço antes) — os 2 vistos em catálogo real.
RE_MEDIDA_R = re.compile(r"\d{3}\s*/\s*\d{2}\s*/?\s*[Rr]\s*\d{2}(?:[.,]\d)?[A-Za-z]?\b")
# bug achado jul/2026: veículo inteiro (caminhão/ambulância/pick-up/van) que só CITA a
# medida do pneu de fábrica batia em RE_MEDIDA_R e virava "eh_pneu=1" — item de
# R$100k-800k/unidade (o veículo), não o pneu. Mesma lógica de âncora no início já usada
# pra pneu/câmara: se o produto começa com nome de veículo, medida solta não conta.
# achado 08/jul/26: "FURGAO/VAN 10+1 PASSAGEIROS..." e "UNIDADE MOVEL DE BANCO DE
# LEITE - VEÍCULO AUTOMOTOR..." (unidade odontológica móvel, unidade de vacinação) são
# veículo inteiro (R$100k-800k) que escapavam por não ter "furgão"/"unidade móvel" na lista.
RE_VEICULO_INICIO = re.compile(
    rf"^\s*{RE_PREFIXO_IGNORAR}(ve[íi]culo|caminh[ãa]o|ambul[âa]ncia|[ôo]nibus|micro[ -]?[ôo]nibus|van\b|"
    r"furg[ãa]o|unidade\s+m[óo]vel|"
    r"pick[ -]?up|caminhonete|trator\b|motocicleta|motoneta|"
    r"loca[çc][ãa]o\s+(di[áa]ria\s+)?de\s+ve[íi]culo)",
    re.IGNORECASE,
)
# achado 08/jul/26 auditando os 127 itens "eh_pneu=True sem nenhuma palavra pneu/câmara no
# texto" (maior risco — só bateram por RE_MEDIDA_R sozinho): 3 categorias de falso positivo
# real, todas com a mesma assinatura — a MEDIDA citada é do pneu que vai NO produto, mas o
# produto sendo vendido é outra coisa:
# 1. Serviço no início: "MONTAGEM DE PNEU ARO...", "MONTAGEM/DESMONTAGEM...",
#    "DESMONTAGEM/MONTAGEM...", "SERVIÇO MONTAGEM PNEU..." — a exclusão de serviço já
#    existente (RE_EXCLUSAO_SERVICO) só cobria "serviço de montagem"/"montagem e
#    desmontagem" (frases exatas) — todas as variações de ordem/separador acima escapavam.
#    Ancorado no início (como RE_VEICULO_INICIO): se a frase COMEÇA com montagem/
#    desmontagem, é o serviço sendo vendido, não o pneu — diferente de "PNEU X - INCLUSO
#    MONTAGEM E INSTALAÇÃO" (começa com "PNEU", venda do pneu com serviço agregado, mantido).
RE_SERVICO_INICIO = re.compile(
    rf"^\s*{RE_PREFIXO_IGNORAR}(montagem|desmontagem|servi[çc]o|execu[çc][ãa]o)\b",
    re.IGNORECASE,
)
# 2. Roda/aro de liga leve: "ARO 175/70 R13 FABRICADO EM LIGA LEVE", "RODA LIGA LEVE 205/60
#    R16" — produto é a RODA (a medida citada é do pneu que ela recebe), não o pneu.
RE_RODA_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}(aro|roda)\s", re.IGNORECASE)
# 3. Bico/pito avulso: "BICO DE AR INSTALADO PARA RODA ARO...", "AQUISIÇÃO DE PITOS
#    COMPATÍVEIS COM PNEUS..." — produto é a válvula, não o pneu.
RE_ACESSORIO_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}(bicos?|pitos?)\b", re.IGNORECASE)
# achado 07/jul/26: "Pneu para retroescavadeira, construção radial..." é o PRODUTO pneu
# (RE_PNEU_INICIO já bate), retroescavadeira é só o contexto de aplicação — mas caía nessa
# exclusão mesmo assim. Split em 2 grupos: RE_EXCLUSAO_MAQUINA só vale quando o produto foi
# confirmado por medida solta (ambíguo — podia ser a máquina inteira citando a medida do
# pneu de fábrica); se já veio de RE_PNEU_INICIO/RE_CAMARA_INICIO, o produto já é pneu com
# certeza, nome de máquina no meio da frase é só aplicação, não desqualifica.
# RE_EXCLUSAO_SERVICO sempre vale — pneu NOVO nunca é descrito com "recapagem"/"conserto".
# achado 08/jul/26: "PNEU X com alinhamento e balanceamento incluso/instalado" (176 casos
# achados auditando falso negativo em massa) — venda de pneu com serviço agregado, igual o
# padrão já resolvido pra montagem/desmontagem. "alinhamento"/"balanceamento" só desqualifica
# quando o produto NÃO é explícito (mesma semântica de RE_EXCLUSAO_MAQUINA) — se já sabemos
# que é "PNEU X", esses termos depois são sempre serviço agregado, nunca o objeto do item.
RE_EXCLUSAO_MAQUINA = re.compile(
    r"carregadeira|motoniveladora|retroescavadeira|escavadeira|rolo\s+compactador|"
    r"cadeira\s+de\s+rodas|alinhamento|balanceamento",
    re.IGNORECASE,
)
# achado 08/jul/26: "NÃO SE ACEITANDO PNEUS RECONDICIONADOS/REFORMADOS, QUER POR RECAPAGEM,
# RECAUCHUTAGEM OU REMODELAGEM" é uma cláusula de PROIBIÇÃO exigindo pneu NOVO — mas
# RE_EXCLUSAO_SERVICO batia "recapagem"/"recauchutagem" sem entender a negação, excluindo
# pneu novo genuíno (23 casos achados). Removida da string antes de checar exclusão.
RE_PROIBICAO_REFORMA = re.compile(
    r"n[ãa]o\s+(se\s+)?(ser[ãa]o?\s+)?aceit[ao]?s?[^.;]{0,120}?"
    r"(recondicionad|reformad|recapad|recauchutad|remodelad)[^.;]{0,80}",
    re.IGNORECASE,
)
RE_EXCLUSAO_SERVICO = re.compile(
    r"recapagem|vulcaniza[çc][ãa]o|conserto|concerto\s+(de|em)|"  # "concerto" = erro ortográfico comum de "conserto" em edital
    r"presta[çc][aã]o\s+de\s+servi[çc]|servi[çc]os?\s+de\s+(borracharia|recauchutagem|vulcaniza|substitui|troca)|"
    r"loca[çc][aã]o\s+de\s+(trator|m[áa]quina|equipamento)|"
    r"loca[çc][aã]o\s+(di[áa]ria\s+)?de.{0,40}(ve[íi]culo|van|minibus|micro[ -]?[ôo]nibus|[ôo]nibus|caminh[ãa]o|ambul[âa]ncia)|"
    r"manuten[çc][ãa]o\s+(preventiva|corretiva)?\s*(do|de)\s+ve[íi]culo|"
    # achado 08/jul/26: "servi[çc]o de montagem/desmontagem" e "montagem e desmontagem"
    # soltos (qualquer lugar do texto) excluíam venda genuína de pneu com serviço agregado
    # ("FORNECIMENTO...DE PNEU NOVO...INCLUINDO MONTAGEM E DESMONTAGEM") — movido pra
    # RE_SERVICO_INICIO (ancorado no início da descrição), que só pega quando montagem/
    # desmontagem/serviço é o OBJETO do item, não uma cláusula de serviço agregado à venda.
    r"rod[íi]zio\s+de\s+pneus?|remendo\s+de\s+pneus?|"
    # achado 07/jul/26 (auditoria jun-jul/2026): esses termos aparecem SOLTOS no catálogo,
    # sem "serviços de" na frente ("RECAUCHUTAGEM DE PNEU 19.5X24", "SUBSTITUIÇÃO PNEU
    # 2.50-17") — hoje só ficam False por acaso (medida sem R não bate bate_produto), mas
    # se RE_MEDIDA_R/RE_MEDIDA_AMPLA for expandido no futuro pra cobrir esses formatos,
    # precisam estar aqui pra continuar corretamente excluídos como serviço, não venda nova.
    r"recauchutagem\s+(de\s+)?pneus?|recupera[çc][ãa]o\s+de\s+pneus?|substitui[çc][ãa]o\s+(de\s+)?pneus?|"
    r"troca\s+de\s+(pneus?|bicos?)|"
    r"n[úu]cleo.*v[áa]lvula|v[áa]lvula.*n[úu]cleo",
    re.IGNORECASE,
)
RE_CATEGORIA_CAMARA = RE_CAMARA_INICIO
RE_CATEGORIA_MOTO = re.compile(r"motocicleta|motoneta|ciclomotor", re.IGNORECASE)
RE_CATEGORIA_AGRICOLA = re.compile(r"trator|agr[íi]cola", re.IGNORECASE)
RE_CATEGORIA_CAMINHAO = re.compile(r"r2[2-9]\.?[05]?\b|r1[7-9]\.?5\b", re.IGNORECASE)


def eh_pneu_de_verdade(descricao: str) -> bool:
    """Nível ITEM — filtro forte. Descrição de item de catálogo, não texto livre."""
    if not descricao:
        return False
    if RE_VEICULO_INICIO.search(descricao):
        return False
    if RE_SERVICO_INICIO.search(descricao):
        return False
    if RE_ACESSORIO_INICIO.search(descricao):
        return False
    if RE_RODA_INICIO.search(descricao) and re.search(r"liga\s+leve", descricao, re.IGNORECASE):
        return False
    camara_generica = (
        bool(RE_CAMARA_GENERICA.search(descricao))
        and bool(RE_MEDIDA_AMPLA.search(descricao))
        and not RE_CAMARA_NAO_PNEU.search(descricao)
    )
    produto_explicito = bool(RE_PNEU_INICIO.search(descricao) or RE_CAMARA_INICIO.search(descricao) or camara_generica)
    bate_produto = produto_explicito or bool(RE_MEDIDA_R.search(descricao))
    if not bate_produto:
        return False
    descricao_sem_proibicao = RE_PROIBICAO_REFORMA.sub("", descricao)
    if RE_EXCLUSAO_SERVICO.search(descricao_sem_proibicao):
        return False
    if not produto_explicito and RE_EXCLUSAO_MAQUINA.search(descricao):
        return False
    return True


def classificar_categoria(descricao: str) -> str:
    if RE_CATEGORIA_CAMARA.search(descricao):
        return "Câmara de ar"
    if RE_CATEGORIA_MOTO.search(descricao):
        return "Moto"
    if RE_CATEGORIA_AGRICOLA.search(descricao):
        return "Agrícola"
    if RE_CATEGORIA_CAMINHAO.search(descricao):
        return "Caminhão"
    return "Passeio"


# ── Nível PROCESSO — mais fraco, só pré-filtro (título+descrição do edital) ─

RE_MAQUINA_PESADA = re.compile(
    r"carregadeira|motoniveladora|retroescavadeira|escavadeira|rolo\s+compactador|"
    r"cadeira\s+de\s+rodas|trator\b",
    re.IGNORECASE,
)
RE_SERVICO = re.compile(
    r"recapagem|vulcaniza[çc][ãa]o|alinhamento|balanceamento|conserto|"
    r"borracharia|recauchutagem|manuten[çc][ãa]o\s+(preventiva|corretiva)?\s*(do|de)\s+ve[íi]culo",
    re.IGNORECASE,
)
RE_AQUISICAO = re.compile(
    r"aquisi[çc][ãa]o|compra|fornecimento|registro\s+de\s+pre[çc]o",
    re.IGNORECASE,
)
RE_PNEU_SUBSTANTIVO = re.compile(r"\bpneus?\b", re.IGNORECASE)
RE_PNEUMATICO_ADJETIVO = re.compile(r"pneum[áa]tic[ao]", re.IGNORECASE)


def classificar_pneu(titulo: str, descricao: str) -> str:
    """Nível PROCESSO — rótulo de confiança sobre texto corrido (título+descrição
    do processo inteiro, não item de catálogo). Mais fraco que eh_pneu_de_verdade
    — usar só como pré-filtro pra economizar chamada de API, nunca como filtro final.
    """
    texto = f"{titulo or ''} {descricao or ''}"

    tem_pneu_substantivo = bool(RE_PNEU_SUBSTANTIVO.search(texto))
    tem_pneumatico_adjetivo = bool(RE_PNEUMATICO_ADJETIVO.search(texto))

    if not tem_pneu_substantivo and tem_pneumatico_adjetivo:
        return "adjetivo_provavel"

    if RE_MAQUINA_PESADA.search(texto):
        return "maquina_pesada_provavel"

    if RE_SERVICO.search(texto) and not RE_AQUISICAO.search(texto):
        return "servico_provavel"

    if tem_pneu_substantivo:
        return "compra_provavel"

    return "indefinido"
