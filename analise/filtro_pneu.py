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
    # achado 23/jul/26 (auditoria avançada, ângulo "sem âncora textual"): boilerplate
    # de especificação técnica antes do nome real do produto — "Esp. Mínimas.\nVEÍCULO
    # TIPO AMBULÂNCIA..." e "CONTENDO NO MÍNIMO AS SEGUINTES ESPECIFICAÇÕES TÉCNICAS
    # MÍNIMAS E ITENS:• Veículo..." — quebrava a âncora de início de RE_VEICULO_INICIO,
    # deixando 6 itens reais (ambulância R$127k-144k, hatch R$85k, minivan/micro-ônibus
    # R$829k, ambulância R$427k, ônibus R$1,48M — todos citando medida de pneu de
    # fábrica) virarem eh_pneu=True. Ignora esse cabeçalho também antes de checar produto.
    r"(?:esp\.?\s*m[íi]nimas\.?\s*[\r\n]*\s*)?"
    r"(?:contendo\s+no\s+m[íi]nimo\s+as\s+seguintes\s+"
    r"(?:especifica[çc][õo]es\s+t[ée]cnicas\s+m[íi]nimas\s+e\s+itens|caracter[íi]sticas)"
    r"[:•\s]*)?"
    # achado 23/jul/26, 2ª rodada: mais 2 fraseologias de boilerplate encontradas —
    # "DESCRIÇÃO COMPLETA SOMENTE NO EDITAL - AMBULÂNCIA..." (R$427,8k) e
    # "Características Gerais do Veículo:Tipo: Ônibus..." (R$1,485 milhão), esta última
    # com "veículo" no meio do próprio cabeçalho de bloco (não é o produto, é o rótulo).
    r"(?:descri[çc][ãa]o\s+completa\s+somente\s+no\s+edital\s*[-–]\s*)?"
    r"(?:caracter[íi]sticas\s+gerais\s+do\s+ve[íi]culo\s*:?\s*tipo\s*:?\s*)?"
)
# "pneumático(s)" é o nome formal/técnico do produto em bastante edital ("PNEUMÁTICO PARA
# AUTOMÓVEL LEVE...", "PNEUMÁTICO NOVO DE 1ª LINHA..."), não só adjetivo (bug histórico
# "cadeira pneumática"/"sistema pneumático") — mas como âncora exige ser a 1ª palavra do
# ITEM (não do processo), "pneumático" no início de um item de catálogo é sempre o produto
# em si, nunca "cadeira pneumática" (que começaria com "cadeira", não com "pneumático").
RE_PNEU_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}(?:pneus?|pneum[áa]ticos?)\b", re.IGNORECASE)
# achado 23/jul/26 (auditoria avançada, MAIOR achado de falso negativo desta rodada):
# "câmara" nunca aceitava plural — "CÂMARAS DE AR..." (catálogo real de câmara de
# caminhão/OTR, quase sempre plural) nunca batia produto_explicito, e a maioria não usa
# medida em formato estrito .../..R.. (usa "aro 11.00 R22", "17,5x25", "900x20", etc, que
# só batem RE_MEDIDA_AMPLA, não RE_MEDIDA_R) — 108 de 114 itens reais medidos contra a
# base inteira ficavam eh_pneu=False só por essa lacuna. "s?" cobre singular e plural.
RE_CAMARA_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}c[âa]maras?\s+(de\s+)?ar\b", re.IGNORECASE)
# "CÂMARA DE FABRICAÇÃO NACIONAL... REFERÊNCIA AR 750/16" — câmara de pneu de verdade, mas
# "de ar" não vem logo depois de "câmara" (RE_CAMARA_INICIO não bate). Fallback: aceita
# "câmara" sozinho no início SE tiver medida ampla em algum lugar da descrição — protege
# contra ruído tipo "Câmara Municipal"/bola esportiva "com câmara butil" (não tem medida de
# pneu, isso nunca bate RE_MEDIDA_AMPLA).
RE_CAMARA_GENERICA = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}c[âa]maras?\b", re.IGNORECASE)
# achado 08/jul/26: "CÂMARA REFRIGERADA - Refrigerador modelo científico..." (freezer de
# laboratório) bateu RE_CAMARA_GENERICA + alguma dimensão do equipamento bateu
# RE_MEDIDA_AMPLA por coincidência — "câmara" tem outros sentidos fora de pneu (câmara
# frigorífica, câmara municipal, câmara de vídeo). Exclui explicitamente antes de aceitar.
# achado 23/jul/26: "s?" adicionado — RE_CAMARA_GENERICA passou a aceitar plural
# ("câmaras") na mesma rodada, então essa exclusão precisa cobrir o plural também
# ("câmaras refrigeradas"/"câmaras municipais"), senão reabre o mesmo bug do
# freezer de laboratório/câmara municipal só que na forma plural.
RE_CAMARA_NAO_PNEU = re.compile(r"c[âa]maras?\s+(refrigerad|fria\b|frigor[íi]fic|municipal|de\s+v[íi]deo|escura)", re.IGNORECASE)
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
# achado 17/jul/26 (auditoria de confiança do card Radar de Editais): "AQUISIÇÃO DE UM
# CAMINHÃO PIPA...", "AQUISIÇÃO DE UMA AMBULÂNCIA..." escapavam porque o artigo indefinido
# (um/uma/uns/umas) entre "de" e o nome do veículo não era coberto pelo prefixo ignorável —
# 4 itens reais achados (caminhão pipa R$630k, caminhão basculante R$589k x2, sedan
# R$182k) classificados como pneu.
# achado 23/jul/26: "automóvel"/"automotor" nunca estiveram na lista — "Aquisição de
# Automóvel, tipo Hatch..." e "AUTOMÓVEL BÁSICO DE PASSEIO..." (ambos citando medida de
# pneu de fábrica) escapavam por essa palavra faltar, mesmo com a âncora de início ok.
# achado 23/jul/26, 2ª rodada (auditoria avançada): mais 4 lacunas na lista de veículo —
# "MINIVAN" (uma palavra só, sem espaço — "van\b" não reconhece porque a âncora exige
# bater exatamente na posição, não como substring no meio de outra palavra); "unidade
# ODONTOLÓGICA móvel"/"unidade DE VACINAÇÃO móvel" (qualificador entre "unidade" e
# "móvel" — "unidade\s+m[óo]vel" exigia as 2 palavras adjacentes); "triciclo" (elétrico/
# de carga, R$86,3k); "reboque"/"carretinha" (trailer, R$8,98k-27,2k) — nenhum estava
# na lista. R$260,7k (minivan) + R$749,6k (unidade odontológica móvel) + R$86,3k
# (triciclo) + R$8,98k (carretinha) confirmados na medição contra a base real.
RE_VEICULO_INICIO = re.compile(
    rf"^\s*{RE_PREFIXO_IGNORAR}(?:um[as]?s?\s+)?(ve[íi]culo|caminh[ãa]o|ambul[âa]ncia|[ôo]nibus|micro[ -]?[ôo]nibus|"
    r"mini[ -]?van\b|van\b|"
    r"furg[ãa]o|unidade(?:\s+\w+){0,2}\s+m[óo]vel|autom[óo]vel|automotor\b|"
    r"pick[ -]?up|caminhonete|trator\b|motocicleta|motoneta|tricicl[oa]|"
    r"reboque|carretinha|"
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
# achado 14/jul/26 (auditoria de falso positivo, cruzando com material_ou_servico do
# PNCP): "REPARO DE PNEU ARO..." nunca desqualificava — "reparo" não estava em nenhuma
# lista de exclusão, nem aqui nem em RE_EXCLUSAO_SERVICO.
# achado 23/jul/26: "raparo" (erro ortográfico de "reparo", 2 itens reais achados na
# auditoria avançada) não batia — grafia errada comum o bastante em edital pra valer o fix.
RE_SERVICO_INICIO = re.compile(
    rf"^\s*{RE_PREFIXO_IGNORAR}(montagem|desmontagem|servi[çc]o|execu[çc][ãa]o|reparo|raparo)\b",
    re.IGNORECASE,
)
# 2. Roda/aro de liga leve: "ARO 175/70 R13 FABRICADO EM LIGA LEVE", "RODA LIGA LEVE 205/60
#    R16" — produto é a RODA (a medida citada é do pneu que ela recebe), não o pneu.
RE_RODA_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}(aro|roda)\s", re.IGNORECASE)
# 3. Bico/pito avulso: "BICO DE AR INSTALADO PARA RODA ARO...", "AQUISIÇÃO DE PITOS
#    COMPATÍVEIS COM PNEUS..." — produto é a válvula, não o pneu.
RE_ACESSORIO_INICIO = re.compile(rf"^\s*{RE_PREFIXO_IGNORAR}(bicos?|pitos?|pistos?)\b", re.IGNORECASE)
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
# achado 14/jul/26: ao tornar recauchutagem/recapagem/ressolagem soltos (sem exigir "de
# pneu" depois, pra pegar "PNEU RECAUCHUTAGEM..." com ordem invertida), 2 padrões novos de
# pneu NOVO genuíno passaram a ser excluídos por engano (medido comparando a base toda
# antes de aplicar — 73 casos mudariam, a maioria correta, mas ~15 eram regressão real):
#   1. "sem reforma ou recauchutagem" — mesma exigência de pneu novo, fraseado com "sem"
#      em vez de "não aceitando" ("PNEUS - Pneu 225-65 R16... sem reforma ou recauchutagem").
#   2. "capaz de suportar 2 recauchutagens futuras" — especificação de DURABILIDADE do
#      pneu novo (casco reforçado aguenta recapagem futura), não descrição do item em si.
RE_PROIBICAO_REFORMA = re.compile(
    r"n[ãa]o\s+(se\s+)?(ser[ãa]o?\s+)?aceit[ao]?s?[^.;]{0,120}?"
    r"(recondicionad|reformad|recapad|recauchutad|remodelad|recape)[^.;]{0,80}"
    # achado 14/jul/26, 3ª rodada: gap coringa [^.;]{0,40}? entre "sem" e o termo (2ª
    # versão) é permissivo demais — bateu "sem DEFEITOS, a RECAPAGEM deverá ser..." (isso
    # é serviço de recapagem de verdade, "pneu usado" explícito no texto, não cláusula de
    # proibição). Ponte restrita só às palavras realmente vistas entre "sem" e o termo
    # ("uso [anterior/prévio]", "reforma", vírgula, "ou") — não wildcard genérico.
    # achado 23/jul/26: "recape" adicionado ao grupo — "PNEU X, novo (sem recape ou
    # remanufatura)..." (9 itens reais, R$0-1,3k) regrediu quando "recape" virou termo de
    # exclusão solto (ver RE_EXCLUSAO_SERVICO) sem essa cláusula de negação ser reconhecida.
    r"|sem\s+(qualquer\s+)?(uso(\s+(anterior|pr[ée]vio))?|reforma)?[\s,]*(ou\s+)?"
    r"(recondicionament|recauchutag|recapag|ressolag|remoldag|reform|recape)\w*[^.;]{0,80}"
    r"|suportar[^.;]{0,60}?(recauchutag|recapag|ressolag|remoldag|reform|recape)\w*[^.;]{0,80}"
    # achado 14/jul/26, 3ª rodada: "NÃO SENDO RESULTANTE DE [processo de] remoldagem e
    # recauchutagem" — 3ª fraseologia de exigência de pneu novo (nem "não aceita", nem "sem").
    r"|n[ãa]o\s+sendo\s+resultante\s+de[^.;]{0,60}?"
    r"(recondicionament|recauchutag|recapag|ressolag|remoldag|reform|recape)\w*[^.;]{0,80}",
    re.IGNORECASE,
)
RE_EXCLUSAO_SERVICO = re.compile(
    # achado 14/jul/26 (auditoria de falso positivo): "recapagem"/"recauchutagem"/
    # "ressolagem" são termos técnicos específicos de reforma de pneu — nunca aparecem
    # em contexto não-relacionado, seguro deixar soltos (sem exigir "de pneu" depois).
    # Plural de "-agem" troca M por NS ("recapagem"→"recapagens", não "recapagem"+s) —
    # "recapagens?" sozinho SÓ bate o plural, quebra o singular (bug na 1ª tentativa
    # desse fix, achado rodando a suíte de teste antes de confiar). "-age(m|ns)" cobre
    # os 2 corretamente.
    # achado 23/jul/26 (auditoria avançada): "concerto\s+(de|em)" exigia preposição
    # depois — "CONCERTO PNEU..." (sem "de"/"em") escapava. A exclusão só roda depois
    # que bate_produto já confirmou medida/âncora de pneu no texto (ver eh_pneu_de_verdade),
    # então o risco de colidir com "concerto" no sentido musical é próximo de zero —
    # seguro deixar solto, igual "conserto" (ortografia correta) já era.
    r"recapage(m|ns)|recauchutage(m|ns)|ressolage(m|ns)|vulcaniza[çc][ãa]o|conserto|concerto|"
    # achado 23/jul/26: "recape" é jargão coloquial de "recapagem" (mesmo serviço de
    # reforma) usado em edital real (4 itens, R$253-893 cada) — lookahead evita colidir
    # com "recapeamento" (obra de pavimentação de via, sem relação com pneu).
    r"recape(?!amento)s?\b|"
    # achado 23/jul/26: "reforma de pneu" nunca esteve em nenhuma lista de exclusão —
    # 2 itens reais (R$40 e R$619) de serviço de reforma classificados como pneu novo.
    r"reforma\s+de\s+pneus?|"
    r"presta[çc][aã]o\s+de\s+servi[çc]|servi[çc]os?\s+de\s+(borracharia|recauchutagem|vulcaniza|substitui|troca)|"
    r"loca[çc][aã]o\s+de\s+(trator|m[áa]quina|equipamento)|"
    # achado 23/jul/26: só "diária" era coberta — "LOCAÇÃO MENSAL DE 2 VEÍCULOS TIPO
    # SEDAN..." (aluguel de carro, R$17,1k/mês) escapava por a periodicidade ser outra.
    r"loca[çc][aã]o\s+(di[áa]ria|mensal|semanal|anual)?\s*de.{0,40}(ve[íi]culo|van|minibus|micro[ -]?[ôo]nibus|[ôo]nibus|caminh[ãa]o|ambul[âa]ncia)|"
    r"manuten[çc][ãa]o\s+(preventiva|corretiva)?\s*(do|de)\s+ve[íi]culo|"
    # achado 08/jul/26: "servi[çc]o de montagem/desmontagem" e "montagem e desmontagem"
    # soltos (qualquer lugar do texto) excluíam venda genuína de pneu com serviço agregado
    # ("FORNECIMENTO...DE PNEU NOVO...INCLUINDO MONTAGEM E DESMONTAGEM") — movido pra
    # RE_SERVICO_INICIO (ancorado no início da descrição), que só pega quando montagem/
    # desmontagem/serviço é o OBJETO do item, não uma cláusula de serviço agregado à venda.
    r"rod[íi]zio\s+de\s+pneus?|remendo\s+de\s+pneus?|"
    # achado 07/jul/26 (auditoria jun-jul/2026): "recuperação"/"substituição" sozinhos são
    # genéricos demais fora do domínio de pneu (podem aparecer em outro contexto qualquer),
    # por isso continuam exigindo "de pneu" — diferente de recapagem/recauchutagem/ressolagem
    # acima, que são jargão específico o bastante pra não precisar da âncora.
    r"recupera[çc][ãa]o\s+de\s+pneus?|substitui[çc][ãa]o\s+(de\s+)?pneus?|"
    r"troca\s+de\s+(pneus?|bicos?)|"
    r"n[úu]cleo.*v[áa]lvula|v[áa]lvula.*n[úu]cleo",
    re.IGNORECASE,
)
RE_CATEGORIA_CAMARA = RE_CAMARA_INICIO
RE_CATEGORIA_MOTO = re.compile(r"motocicleta|motoneta|ciclomotor", re.IGNORECASE)
# achado 16/jul/26 (auditoria de contaminação "Passeio"): notação de moto sem palavra-chave
# ("90/90-18", "110/90-17", "90-90-18") caía em Passeio por falta de âncora. Exige o trio
# completo largura/perfil/aro (2º grupo obrigatório, não opcional) — testado contra a base
# real: com o aro opcional, pares soltos de índice de carga/velocidade ("IC 82/88") geravam
# falso positivo (nenhum aro depois); exigindo aro, esses somem e restam só medidas de moto
# genuínas (281/635 candidatos, amostra 100% limpa). Lookbehind bloqueia ser só um trecho no
# meio de notação de passeio 3-números ("175/70/13") ou decimal de OTR ("12.5/80-18").
RE_CATEGORIA_MOTO_NOTACAO = re.compile(r"(?<!\d[-/.,])\b(?:[6-9]\d|1[0-2]\d)[-/]\d{2}[-/]\d{2}\b")
RE_CATEGORIA_AGRICOLA = re.compile(r"trator|agr[íi]cola", re.IGNORECASE)
# achado 16/jul/26 (auditoria de contaminação "Passeio", 8.566/33.804 itens): regex antigo
# só cobria aro 17-19,5 (ônibus) e 22-29 (caminhão) via "R" — perdia aro solto sem R
# ("16.5", "20.5"), notação decimal de OTR/agrícola ("17.5-25", "12.4-24", "18.4-30" — largura
# decimal nunca existe em pneu de passeio) e notação antiga de caminhão em número inteiro
# ("750-16", "1000-20", "900-20" — largura ≥600mm, impossível em passeio). Bug de
# backtracking fechado: \b logo após o 1º grupo decimal impede reinterpretar número de
# decreto formatado "5.123" (separador de milhar) como se fosse largura decimal de pneu —
# confirmado contra amostra de 40 itens que migrariam, 100% limpa.
RE_CATEGORIA_CAMINHAO = re.compile(
    r"r\s*2[2-9][.,]?[05]?\b|r\s*1[6-9][.,]?5\b|"
    r"\b1[6-9][.,]5\b|\b2[0-4][.,]5\b|"
    r"\b\d{1,2}[.,]\d{1,2}\b\s*[-x/r.]?\s*\d{2}\b|"
    r"\b(?:[6-9]\d{2}|1[0-9]\d{2})\b\s*[-x/r.]?\s*\d{2}\b",
    re.IGNORECASE,
)


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
    if RE_CATEGORIA_MOTO.search(descricao) or RE_CATEGORIA_MOTO_NOTACAO.search(descricao):
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
