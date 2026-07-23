# LICIT

Empresa individual (CNPJ 46.552.201/0001-00) que participa de licitações públicas. Duas verticais hoje — ver "Verticais" abaixo. Contexto completo do negócio (riscos, fórmulas, habilitação, Notion): `CLAUDE.md`.

Documento organizado em 3 partes: **espinha dorsal** (ferramentas e arquitetura comuns às 2 verticais), **Anexo — Vertical Pneu** (negócio ativo) e **Anexo — Vertical Oncológico** (exploração de mercado). Nomes de seção não mudam quando referenciados de outro lugar (CLAUDE.md, memória) — só a posição física foi reorganizada.

---

# PARTE 1 — ESPINHA DORSAL

## Verticais

| Vertical | Status | O que já roda |
|---|---|---|
| **Pneu** | Ativo — vende de verdade pro governo | Radar → análise → cotação → habilitação → proposta, ponta a ponta (ver Anexo Pneu) |
| **Oncológico** | Exploração de mercado (iniciado 23/jul/2026) | Só coleta/classifica/mostra tamanho de mercado — vitrine, não vende ainda (ver Anexo Onco) |

Cada vertical tem seu pipeline de mercado próprio (`analise/` pra pneu, `analise_onco/` pra onco) na mesma arquitetura — ver "Estrutura" abaixo. O que muda é o vocabulário/regra do filtro de classificação e se o resto do fluxo comercial (cotação/habilitação/proposta) já existe por trás.

## Estrutura

```
licit/
├── pncp_radar.py            [Pneu] Radar diário — busca edital novo no PNCP, envia email. Resiliente a queda:
│                            ciclo de 10 tentativas, se falhar avisa por email (1x) e repete a cada
│                            30min até conseguir (job do GH Actions com budget de tempo maior pra isso)
├── analisa_edital.py        [Pneu] Camada 1. Baixa edital via API PNCP (pdf/docx/txt/html), Claude extrai JSON → card Notion.
│                            Trava (ExtracaoInsuficiente) se o documento não puder ser lido com confiança —
│                            nunca analisa sem base documental real. Usa valorTotalEstimado oficial do PNCP
│                            (api/consulta/v1), não o texto livre. Anexa os documentos originais no card.
│                            Card inclui recomendação "evoluir_parecer_juridico" (sim/não + motivo) —
│                            não chama a Camada 2 sozinho, só sinaliza se vale a pena rodar.
├── parecer_juridico.py      [Pneu] Camada 2, script SEPARADO — só roda manualmente, nunca encadeado pela Camada 1.
│                            Lê analise_{cnpj}_{ano}_{seq}.json (saída da Camada 1) + arsenal_juridico.md
│                            inteiro, gera recomendações ARS-XX (cada uma com baseado_em + confiança),
│                            escreve seção própria no card. Nunca presume fato com "fonte": null da Camada 1.
├── bransales_scraper.py     [Pneu] Cotação — Bransales Atacadista
├── cantu_scraper.py         [Pneu] Cotação — Cantu / SpeedMax B2B
├── gp_scraper.py            [Pneu] Cotação — GP Fácil (cookies exportados — reCAPTCHA bloqueia login direto)
├── green_scraper.py         [Pneu] Cotação — PneuGreen (só ele valida se a medida do produto bate com a pedida
│                            antes de aceitar — os outros 3 usam URL estruturada por medida, mais seguro)
├── notion_upload.py         [Pneu] Upload resultado Bransales → Notion (REST API)
├── cantu_upload.py          [Pneu] Upload resultado Cantu → Notion (REST API)
├── preencher_planilha_precificacao.py  [Pneu] Preenche cópia da planilha modelo (Sheets) com resultado dos
│                            4 scrapers + referência do edital — ver Anexo Pneu § Precificação
├── inmetro_lookup.py        [Pneu] Busca certificado INMETRO no ProdCert oficial (Portaria 379/2021,
│                            pneus). Rodar só pros itens marcados "x" na coluna AA da planilha
│                            (Produto Escolhido) — nunca pra todos os candidatos, ver CLAUDE.md §15.5
├── precificacao_gsheets.py  [Pneu] ⚠️ DEPRECADO — hardcoded pro Cantagalo (jun/2026), não usar em edital novo
├── sample_objeto.py         [Pneu] Script de exploração pontual da API PNCP (objetoCompra)
├── items_X.json / results_X_*.json / analise_X.json   [Pneu] Input/output de cotação por edital
│                            (gitignorado — dado local, nome muda por processo)
│
├── analise/                 [Pneu] Pipeline de mercado (dado público PNCP)
│   ├── coletor_pncp.py         Fase 1 — descobre editais (API de busca), grava em Postgres
│   ├── coletor_pncp_detalhe.py Fase 2 — baixa detalhe+itens+resultado de cada edital da fila
│   ├── filtro_pneu.py          Filtro compartilhado "é pneu de verdade?" (regex + regras) — achados
│   │                           por rodada: ver Anexo Pneu § Auto-aperfeiçoamento do filtro
│   ├── test_filtro_pneu.py     Regressão do filtro (39 casos — histórico completo no próprio arquivo)
│   ├── pneu_medida_matcher.py  Matching determinístico de medida (tupla largura/perfil/aro),
│   │                           reusado pelo cotacao_master/ — ver Anexo Pneu § Ciclo de match
│   ├── conectar_pncp.py        Queries do schema `public` (mercado PNCP) usadas pelo dashboard —
│   │                           inclui carregar_editais_abertos() (ver Anexo Pneu § Radar de Editais)
│   ├── conectar_cotacao_master.py  Queries do schema `cotacao_fornecedor` (ver Anexo Pneu § Cotação Master)
│   ├── ui_explicacao.py        Padrão de explicabilidade local (16/jul/2026) — cabecalho_pagina()
│   │                           (pergunta+fonte no topo) e regra() (expander "Regra e cálculo")
│   ├── dashboard_common.py     Estilo/cores/loaders compartilhados entre as páginas do dashboard
│   ├── .streamlit/config.toml  Tema escuro (16/jul/2026) — ver "Tema e paleta" abaixo
│   ├── dashboard_pncp.py       Entrypoint do dashboard (Streamlit multi-page — `st.navigation`)
│   ├── views/                  Conteúdo de cada página do dashboard (Mercado PNCP + Radar de Editais +
│   │                           Cotação Fornecedor)
│   ├── recomputar_filtro.py    Reaplica filtro_pneu.py sem reraspar (quando o filtro muda)
│   ├── migrar_para_supabase.py Migração one-shot SQLite → Postgres (já rodada, mantida por histórico)
│   ├── schema_supabase.sql     Schema das 6 tabelas (schema `public`, mercado PNCP)
│   └── requirements.txt        Deps desse pipeline (psycopg2, streamlit, plotly, curl_cffi...)
│
├── analise_onco/            [Onco] Pipeline de mercado para medicamentos oncológicos (espelha analise/,
│   │                        iniciado 23/jul/2026 — vitrine de capacidade, não vende oncológico
│   │                        ainda: ver `views/mais_no_licit.py`)
│   ├── coletor_onco.py         Fase 1 — busca por LISTA de termos (genérico+marca, ~86 termos),
│   │                           não 1 termo fixo como o de pneu — grava em schema `oncologia`
│   ├── coletor_onco_detalhe.py Fase 2 — detalhe+itens+resultado por edital (mesmo padrão do de pneu)
│   ├── filtro_onco.py          Filtro "é medicamento oncológico de verdade?" — match por substring
│   │                           normalizado (case/acento-insensível) contra genéricos+marcas, com
│   │                           exclusão de uso duplo (mesma substância tem indicação não-oncológica:
│   │                           osteoporose/reumatologia/dermatologia/oftalmologia) — achados por
│   │                           rodada: ver Anexo Onco § Auto-aperfeiçoamento do filtro oncológico
│   ├── test_filtro_onco.py     Regressão do filtro (39 casos — histórico completo no próprio arquivo)
│   ├── recomputar_filtro_onco.py  Reaplica filtro_onco.py sem rebuscar API (espelha recomputar_filtro.py)
│   ├── conectar_onco.py        Queries do schema `oncologia` usadas pelo dashboard
│   ├── dashboard_onco.py + dashboard_common_onco.py  Dashboard Streamlit (multi-página, espelha dashboard_pncp.py)
│   ├── views/                  Conteúdo de cada página — inclui `mais_no_licit.py` (vitrine de
│   │                           possibilidades: capacidade já validada na plataforma, sem citar
│   │                           a vertical de origem, apresentada como próxima prioridade)
│   └── requirements.txt
│
├── cotacao_master/           [Pneu] Coleta diária de preço direto nos 4 distribuidor (ver Anexo Pneu § Cotação Master)
│   ├── *_scraper_master.py     Cópia dos 4 scrapers de edital, adaptada (sem limite de candidato,
│   │                           ficha técnica sempre) — originais na raiz NUNCA são alterados
│   ├── cotacao_master.py       Orquestrador — roda os 4 sequencial, grava no Supabase
│   ├── classificador_alias.py  Regra determinística (zero custo de token) pra sinalizar produto
│   │                           reforçado/comercial (sufixo C, índice de carga duplo, Lonas, Van)
│   └── requirements.txt
│
├── schema_cotacoes_diarias.sql  [Pneu] Schema do schema `cotacao_fornecedor` (medidas/aliases_medida/cotacoes)
├── medidas_prioritarias.json    [Pneu] Config versionada — lista de medida cotada diariamente
│
└── .github/workflows/        Automação (ver abaixo)
```

## Automação (GitHub Actions)

| Workflow | Vertical | Quando roda | O que faz |
|---|---|---|---|
| `pncp_radar.yml` | Pneu | dias úteis, 5h BRT | Radar diário → email |
| `pncp_coletor_editais.yml` | Pneu | diário, ~meia-noite BRT (+ manual) | Fase 1 — reescaneia as 27 UFs pra achar edital novo (`--reset`, ver docstring de `coletor_pncp.py`) |
| `pncp_coletor_detalhe.yml` | Pneu | a cada ~5h30 | Fase 2 — processa fila pendente (editais novos entram sozinhos) |
| `onco_coletor_editais.yml` | Onco | diário | Fase 1 onco — busca todos os termos do vocabulário (`analise_onco/coletor_onco.py`) |
| `onco_coletor_detalhe.yml` | Onco | periódico | Fase 2 onco — processa fila pendente (`coletor_onco_detalhe.py`) |
| `cotacao_master.yml` | Pneu | diário, 12h UTC / 9h BRT | Ver Anexo Pneu § Cotação Master |

Fase 2 não descobre edital novo sozinha — só fase 1 faz isso (API não permite paginar por data). Rodar `coletor_pncp.py --reset` é a única forma de achar processo novo.

## Auto-aperfeiçoamento dos filtros de classificação (processo comum)

Regra fixada em `CLAUDE.md` §17.15/16, mesma cadência do §17.14 (mensal, último dia útil
— compartilha o lembrete de calendário, ver `feedback_licit_cotacao_master_autoaperfeicoamento`
na memória). Vale igual pras 2 verticais (`filtro_pneu.py` e, desde 23/jul/2026,
`filtro_onco.py`) — **resultado de cada rodada (bugs, impacto medido) mora no anexo da
vertical correspondente, não aqui** (regra "1 dono só", CLAUDE.md §17.12).

2 investigações separadas, cada rodada:

1. **Falso positivo/negativo no filtro item-a-item** — cruza a classificação gravada
   (`itens.eh_pneu` / `itens.eh_medicamento_onco`) contra o campo estruturado
   `material_ou_servico` (sinal barato, nunca usado por padrão) + amostra os buckets de
   risco. Todo bug achado vira teste de regressão **antes** do fix (prova que é bug de
   verdade), depois o fix, depois **medir o impacto na base inteira** (quantos itens
   mudariam de classificação) antes de aplicar via `recomputar_filtro.py`/
   `recomputar_filtro_onco.py` — repetir a medição até estabilizar (achado 14/jul/2026:
   um fix mal calibrado regride caso que já funcionava; só medição contra a base real
   pega isso).
2. **Cobertura da busca (fase 1)** — pra pneu, `TERMO_BUSCA` é 1 palavra só ("Pneu"):
   testar se edital com pneu "escondido" escapa, buscando termo mais amplo/adjacente na
   API ao vivo e **confirmando item a item** se os "novos" achados são reais. Pra onco, a
   fase 1 já busca por LISTA de termos (não é gargalo de termo único) — o risco de
   cobertura é **vocabulário incompleto**: testar fármaco de peso comercial ainda não
   cadastrado contra a base já coletada (coocorrência) e sinalizar risco de uso duplo
   antes de adicionar.

**Subagente que audita nunca aplica sozinho em produção** — regra dura fixada 23/jul/2026
depois de um incidente real (subagente alucinou aprovação e rodou o recompute sozinho),
ver `CLAUDE.md` §17.16.

## Tema e paleta (skill dataviz)

Paleta categórica/diverging validada pela skill `dataviz` (`references/palette.md`) desde
14/jul/2026 (`PALETA_CATEGORICA_8`, `DIVERGING_POLO_NEG/NEUTRO/POS` em `dashboard_common.py`)
— mas os gráficos já assumiam fundo escuro (`COR_GRID_DARK`, `COR_INK_DARK`) sem o dashboard
ter tema escuro configurado, rodando no claro padrão do Streamlit (achado 16/jul/2026: causa
raiz do visual "descombinado"). `analise/.streamlit/config.toml` fixa `base="dark"` com as
mesmas cores de chrome escuro da paleta (`#0d0d0d` fundo de página, `#1a1a19` superfície,
`#2a78d6` cor primária = slot 1 categórico). Testado nas 7 páginas, sem regressão.

Status palette (fixa, nunca themed — `COR_STATUS_CRITICAL/WARNING/GOOD` em
`dashboard_common.py`) é reservada pra estado (urgência/alerta), nunca reusada como cor
categórica de série — sempre com ícone/label junto (usada 1ª vez no Kanban de Editais
Abertos, ver Anexo Pneu).

## Setup

Variáveis de ambiente (`.env`, nunca commitado):

```
NOTION_TOKEN, NOTION_DB_ID
ANTHROPIC_API_KEY
BRANSALES_EMAIL, BRANSALES_PASSWORD
CANTU_EMAIL, CANTU_PASSWORD
GREEN_EMAIL, GREEN_PASSWORD
DATABASE_URL              # Postgres/Supabase, pooler transaction mode
```

`credentials.json`/`token.json` (OAuth Google Sheets, gitignorados) — setup de 1x só, ver docstring de `preencher_planilha_precificacao.py`.

Radar (`requirements_radar.txt`) e pipelines de mercado (`analise/requirements.txt`,
`analise_onco/requirements.txt`) têm dependências separadas de propósito — o radar não
precisa puxar `psycopg2`/`streamlit`.

`cotacao_master.yml` (GitHub Actions) roda em nuvem, não lê `.env` — precisa dos mesmos pares
acima (`BRANSALES_EMAIL/PASSWORD`, `CANTU_EMAIL/PASSWORD`, `GREEN_EMAIL/PASSWORD`,
`DATABASE_URL`) cadastrados como **Secrets do repo** (Settings → Secrets and variables →
Actions), mais `GP_COOKIES_JSON` (conteúdo inteiro do `gp_cookies.json`, escrito em arquivo por
um step do workflow). Bransales não entra — roda só local (ver Anexo Pneu § Cotação Master).

## Segurança

- `.env`, `gp_cookies.json`, `credentials.json`/`token.json` (OAuth Google Sheets) — gitignorados, nunca commitados
- Credenciais dos distribuidores viveram hardcoded no código, repo público, entre 29/jun e 07/jul/2026 (commit `2456dcf` corrigiu, moveu pra `.env`) — histórico antigo do git ainda contém as senhas removidas; **trocar as 3 senhas nos portais (Bransales/Cantu/PneuGreen) e avaliar reescrever o histórico do git** enquanto o repo for público
- RLS habilitado nas 6 tabelas do Supabase (sem policy — acesso só via `DATABASE_URL`/service role, que faz bypass)

---

# PARTE 2 — ANEXO: VERTICAL PNEU (negócio ativo)

## Fluxo do negócio

```
RADAR (pncp_radar.py)              → email diário com edital novo publicado no PNCP
ANÁLISE DE EDITAL (analisa_edital.py) → baixa docs do PNCP, Claude extrai critérios → card Notion
                                       → card recomenda (ou não) evoluir pro parecer jurídico
PARECER JURÍDICO (parecer_juridico.py) → Camada 2, manual, só se recomendado — lê arsenal_juridico.md
                                       + fatos da Camada 1, gera recomendações ARS-XX no card
COTAÇÃO (*_scraper.py)             → busca preço em cada distribuidor
PRECIFICAÇÃO (preencher_planilha_precificacao.py) → planilha Sheets (modelo no Drive)
HABILITAÇÃO                        → checklist de documentação da empresa (Notion)
PROPOSTA                           → carta espelha linguagem do edital, preço = custo × 1.24
CICLO DE APRENDIZADO               → após sessão, compara nossa cotação vs resultado real (Notion)
```

## Auto-aperfeiçoamento do filtro (`filtro_pneu.py`)

Processo comum descrito na espinha dorsal (ver acima) — esta seção só guarda os
**resultados de cada rodada**.

**Achado 16/jul/2026 — contaminação de `categoria` (não é falso positivo/negativo de `eh_pneu`,
é classificação errada dentro dos itens já corretos):**
- `RE_CATEGORIA_CAMINHAO` só cobria aro 17-19,5 (ônibus) e 22-29 (caminhão) via "R" — perdia aro
  solto sem R (16.5/20.5), notação decimal de OTR/agrícola (17.5-25, 12.4-24 — largura decimal
  nunca existe em pneu de passeio) e notação antiga inteira de caminhão (750-16, 1000-20 —
  largura ≥600mm, impossível em passeio). Fix cobre as 3, com `\b` logo após o 1º grupo decimal
  pra não reinterpretar número de decreto formatado "5.123" como largura de pneu (bug de
  backtracking, fechado). **8.565 de 33.804 itens "Passeio" migraram pra "Caminhão"** (25.238 →
  24.958, restante foi pro fix de moto abaixo).
- `RE_CATEGORIA_MOTO_NOTACAO` (novo) — notação de moto sem palavra-chave ("90/90-18",
  "110/90-17") caía em "Passeio". Exige o trio completo largura/perfil/aro (aro obrigatório, não
  opcional) — com aro opcional, par solto de índice de carga/velocidade ("IC 82/88") virava falso
  positivo. **281 itens migraram pra "Moto"** (574 → 855).
- Medição contra a base real antes de aplicar, `recomputar_filtro.py` rodado 16/jul/2026 —
  distribuição final: Passeio 24.958, Caminhão 11.417, Câmara de ar 6.934, Agrícola 1.101,
  Moto 855 (161.491 itens reprocessados, `eh_pneu=TRUE` inalterado em 46.654 — só `categoria`
  mudou, nenhum item entrou/saiu do filtro).

**Rodada 23/jul/2026 (auditoria avançada, 3ª rodada) — 12 bugs corrigidos, 147/163.876
itens mudariam (0,09% da base), `recomputar_filtro.py` rodado — `eh_pneu=TRUE` foi de
47.258 → 47.313 (+55):**

Falso positivo (46 itens, ~R$4,82 milhões tirados da métrica — todos veículo/serviço
classificado como pneu):
- Boilerplate de especificação técnica antes do nome do veículo ("Esp. Mínimas.",
  "CONTENDO NO MÍNIMO AS SEGUINTES ESPECIFICAÇÕES...", "DESCRIÇÃO COMPLETA SOMENTE NO
  EDITAL -", "Características Gerais do Veículo:Tipo:") quebrava a âncora de início —
  6 veículos inteiros (ambulâncias R$127-427k, hatch R$85,8k, micro-ônibus R$829,9k,
  ônibus R$1,485 milhão) escapavam.
- "Automóvel"/"automotor", "minivan" grudado (sem espaço), "unidade ODONTOLÓGICA/DE
  VACINAÇÃO móvel" (qualificador entre "unidade" e "móvel"), "triciclo", "reboque"/
  "carretinha" nunca estiveram na lista de veículo (`RE_VEICULO_INICIO`).
- Typos não reconhecidos: "concerto" sem preposição, "raparo" (erro de "reparo").
- "Recape" (jargão de recapagem) e "reforma de pneu" nunca excluíam.
- Locação MENSAL de veículo (só "diária" era coberta).

Falso negativo (101 itens — maior achado da rodada):
- **"Câmaras" no plural nunca era reconhecido** (`RE_CAMARA_INICIO`/`RE_CAMARA_GENERICA`
  só aceitavam singular) — catálogo real de câmara de caminhão/OTR/moto é quase sempre
  plural e usa medida fora do formato estrito `.../..R..`. Sozinho responde por 101 dos
  147 itens (R$22,9 mil recuperados).

Ângulos que não acharam nada (robustez confirmada): NCM (campo nunca populado nesta
base), `criterio_julgamento_nome`.

## Radar de Editais (Kanban, 16/jul/2026)

Página "🗂️ Radar de Editais" no dashboard — Kanban só-leitura dos editais com item de pneu
que ainda estão com proposta aberta, agrupado por dias restantes até o encerramento
(urgente ≤2 dias / esta semana 3-7 / depois >7). Fonte: mesma base do Mercado PNCP
(`conectar_pncp.carregar_editais_abertos()`), filtrada por `situacao_compra_nome =
'Divulgada no PNCP'` + `data_encerramento_proposta` no futuro — não precisa de scraper novo,
o dado já é coletado pela Fase 2 (`coletor_pncp_detalhe.py`).

**Decisão explícita (16/jul/2026): nenhum botão dispara escrita.** O card mostra o
identificador `cnpj/ano/seq` pra rodar `analisa_edital.py` manualmente no terminal — dashboard
é público, disparar a Camada 1 (chamada de API + Claude + escrita no Notion) a partir de um
clique ali violaria a regra de nunca automatizar o pipeline buscar→card→análise (CLAUDE.md
§17.8) e exporia custo de token a qualquer visitante. Mesmo raciocínio já usado em "Aliases
Pendentes" (sem botão de aprovar no dashboard público).

Filtros (UF, Modalidade, Categoria de produto, Regime RP/CD) afetam mapa e Kanban juntos.
Mapa "Onde estão os editais abertos" — 1 ponto por edital, cor por urgência (status palette,
não categórica). Ponto de saída dos distribuidores ainda não existe (aguardando cadastro
manual no Notion).

**Achados 16/jul/2026 (EDA real, skill `programmatic-eda`) — 2 bugs de dado + 2 evoluções:**
- Teto de valor por ITEM (`valor_unitario_estimado <= R$50k`, mesmo teto de
  `carregar_base_pncp()`) — sem ele, um edital com câmara de ar cotada a R$521k/unidade
  aparecia como oportunidade de R$195mi (soma real dos itens: ~R$1,64mi). O teto de
  processo (R$300M) não pegava porque o erro estava no item, não no total.
  `valor_pneu_estimado` (soma só dos itens de pneu já filtrados) substitui
  `valor_total_estimado` do processo no card — mais preciso e imune a esse tipo de erro.
- Dedup trocado de `(cnpj+abertura)` pra `(cnpj+valor+encerramento)` — retificação pode
  mudar a data de abertura sem mudar o processo (achado real: Touros/RN duplicado 2x).
- Aviso "N de M itens são pneu" quando o edital não é 100% dedicado (pneu é item
  secundário num edital genérico maior).
- Badge 🔁 de comprador recorrente — mesmo órgão com 2+ editais de pneu abertos ao mesmo
  tempo, sinal de relacionamento a cultivar, não só oportunidade pontual.

## Cotação Master (coleta diária de preço, independente de edital)

Pipeline separado do fluxo de cotação por edital (que segue intocado) — cota diariamente as
medidas de `medidas_prioritarias.json` nos distribuidores já cadastrados (Bransales, Cantu, GP,
Green Pneus, Della Via), grava histórico no schema `cotacao_fornecedor` (mesmo projeto Supabase
do mercado PNCP, schema separado — ver `schema_cotacoes_diarias.sql`). Visível na aba
"💰 Cotação Fornecedor" do dashboard.

**Giga Pneus removido do grupo (15/jul/2026):** nunca ficou em 1º/2º lugar em nenhuma das 12
medidas comparadas, sem tier de atacado (testado login + kit de 4 unidades, preço idêntico nos
2 casos), e perde 100% das vezes pro GP (já ativo). Scraper root (`giga_scraper.py`) continua
existindo pra cotação por edital pontual, só saiu do pipeline de coleta diária.

**Bug corrigido (15/jul/2026):** a página "Preço Atual" filtrava pela data mais recente
combinando TODOS os fornecedores — quando um fornecedor novo rodava num dia diferente dos
outros, a comparação sumia com quem tinha rodado em dia mais antigo (mesmo sendo a cotação
mais recente daquele fornecedor). Corrigido pra usar a última cotação de CADA fornecedor,
não o dia mais recente do conjunto (`analise/views/cotacao_preco_atual.py`).

**Expansão de cobertura (17/jul/2026):** `medidas_prioritarias.json` foi de 30 para 98
medidas — 30 originais (frequência real, itens Passeio 2026) + 28 achadas faltando no
Radar de Editais + 40 novas do mesmo filtro de frequência real (threshold 2+ ocorrências
nos itens Passeio 2026, PNCP). 3 tamanhos descartados do filtro (`110/90 R17`,
`340/80 R18`, `120/80 R18`) por parecerem contaminação de categoria (moto/agrícola
classificado como Passeio — mesmo bug em investigação no §17.15 do CLAUDE.md).

**Automação:** `.github/workflows/cotacao_master.yml` — cron **ativado 17/jul/2026**
(diário, 12h UTC / 9h BRT), depois de validar rodagem manual. `timeout-minutes` subiu de
120 para 350 pra caber o volume novo (3.3x mais medidas). Tarefa agendada local do
Bransales também precisou de `ExecutionTimeLimit` maior (30min → 4h) pelo mesmo motivo.

### Bransales — só roda local (fixado 14/jul/2026)

O WAF da Bransales ("gocache") serve reCAPTCHA pro IP de datacenter do runner do GitHub Actions
— nunca chega no formulário de login (confirmado via screenshot/HTML do artifact
`cotacao-master-debug`, IP `52.x.x.x`, faixa Azure). Não é bug, é bloqueio de rede real — não
contornamos captcha.

`cotacao_master.py` detecta `GITHUB_ACTIONS=true` (setado pelo próprio runner) e pula Bransales
sozinho na nuvem, sem contar como quebra/disparar alerta. Os outros 3 (Cantu/GP/Green Pneus)
rodam normal todo dia via Actions.

Bransales roda **só local** (IP residencial, nunca bloqueado — já provado em todo teste manual):

```
python cotacao_master.py --apenas Bransales
```

Tarefa agendada no Windows (`LICIT - Cotacao Master Bransales`, diária 6h, `WakeToRun` +
`StartWhenAvailable`) cobre isso automaticamente nesta máquina. Limitação real: nenhum software
liga um PC totalmente desligado — `WakeToRun` só acorda de Suspensão/Hibernação;
`StartWhenAvailable` roda a tarefa assim que a máquina ligar de novo se perdeu o horário; ligar
sozinho a partir de desligado de verdade exige BIOS ("Power On By RTC Alarm"), fora do que
Windows/Task Scheduler alcança.

### Resiliência

`cotacao_master.py` retenta cada fornecedor até 3x (30s entre tentativas) antes de marcar
quebra real — a maioria de falha de scraping web é instabilidade passageira do site, não bug
(já visto: Bransales/Cantu falharam na 1ª tentativa e passaram limpo na 2ª, mesmo código, mesmo
dia). Escrita no banco é isolada por fornecedor (rollback + segue pros próximos) — bug na
gravação de 1 fornecedor não impede os outros de rodar. Só sai com `exit(1)` (dispara e-mail do
GitHub Actions) se restar quebra real depois de esgotar tentativas.

### Ciclo de match de medida

Alias novo (nunca visto daquele fornecedor) sempre entra pendente (`aprovado_por_humano=false`)
— cotação correspondente vira confiança `parcial` até revisão manual. Revisão obrigatória por
fornecedor novo + mensal no último dia útil (`CLAUDE.md` §17.14). `classificador_alias.py`
pré-sinaliza suspeita de produto reforçado/comercial antes da revisão (zero custo de token).

## Dados

- **Fonte:** API de busca do PNCP (não o export bulk do ComprasGOV — tem gap de ~17x, ver `analise/coletor_pncp.py` docstring)
- **Armazenamento:** Postgres no Supabase, projeto `LICIT` (`koqsgnvmnzkqzxnskzgq`, sa-east-1)
- **Dashboard público:** https://gsuh5zthgffvohk8xqbuhe.streamlit.app/
- **Documentação do achado/histórico de bugs de filtro:** Notion → [Dados públicos](https://app.notion.com/p/395ca98e9281806684a6c34186a520ca)

## Precificação (planilha)

- **Modelo mestre:** [pasta no Drive](https://drive.google.com/drive/folders/1Nf10IsY2Gzpf_1WXWuKBC0B58vAbnuXX) — nunca editar direto, sempre duplicar (`copy_file`) antes de preencher. Só tem o banner (linhas 1-2) — os 4 blocos (Bransales/Cantu/GP/Green) e as fórmulas são construídos do zero pelo script a cada rodada, altura dinâmica (não mais 12 linhas fixas por bloco). Colunas de entrada A-L (Item/Produto/Modelo/Especificação Técnica/Critérios/Distribuidor/Marca/Link/Observação/Preço UN/Ref. Edital/Qtde) + coluna Vencedor (fórmula, compara os 4 blocos).
- `python preencher_planilha_precificacao.py <spreadsheet_id> <analise.json> --bransales X --cantu X --gp X --green X`
- Detalhe completo: `CLAUDE.md` §15.5

## Ciclo de Aprendizado

Depois de cada sessão de lances, comparar nossa cotação vs resultado real e registrar em [Ciclo de aprendizado](https://app.notion.com/p/392ca98e928180c6a1bbcef7942f583b) (4 pontos fixos: Concorrentes/Produto/Edital/Processo). Processo documentado em `CLAUDE.md` §15.6.

---

# PARTE 3 — ANEXO: VERTICAL ONCOLÓGICO (exploração de mercado)

Pipeline iniciado 23/jul/2026, espelha a arquitetura do pneu (`analise_onco/`) — ainda
**não vende** medicamento oncológico pro governo, é vitrine de capacidade da plataforma
(ver `analise_onco/views/mais_no_licit.py`, página "Possibilidades pro LICIT
Oncológico" — mostra funcionalidade validada em produção como possibilidade a construir
aqui, sem citar a vertical de origem). Se virar negócio real, este anexo ganha as mesmas
seções do Anexo Pneu (fluxo do negócio, cotação, precificação, ciclo de aprendizado).

**Dashboard público:** https://licit-oncologia.streamlit.app/

## Auto-aperfeiçoamento do filtro oncológico (`filtro_onco.py`)

Processo comum descrito na espinha dorsal (ver Parte 1) — esta seção só guarda os
**resultados de cada rodada**.

**Double-check inicial (23/jul/2026, mesmo dia da criação — 2 rodadas antes de
qualquer dado ir pro dashboard):**
- 5 termos de uso duplo (mesma substância, indicação NÃO-oncológica é a fatia real
  maior): Talidomida (bloco de receituário/telemedicina ≠ comprimido oncológico),
  Ácido zoledrônico 5mg/Aclasta (osteoporose) vs 4mg/Zometa (oncológico), Denosumabe
  60mg/Prolia (osteoporose) vs 120mg/Xgeva (oncológico), Metotrexato 2,5mg comprimido
  (reumatologia) vs injetável alta dose (oncológico), Tretinoína tópico/Vitacid
  (dermatologia) vs cápsula oral (oncológico).
- `material_ou_servico="S"` exclui direto — amostra de 57 itens "S" marcados onco eram
  quase todos infusão/aplicação/manipulação/importação (serviço em torno do fármaco,
  não compra do fármaco).
- Contexto oftalmológico exclui Bevacizumabe/Avastin e Mitomicina (uso ocular real e
  comum — anti-VEGF intravítreo, cirurgia de pterígio) — sem contexto ocular explícito,
  mantido `True` (risco de descartar compra oncológica real > risco de manter ambíguo).
- "Sutent" removido da lista de marcas — 100% colisão com "sustentação"/"sustentável",
  zero compra real do fármaco na amostra (genérico "Sunitinibe" já cobre a droga).
- 9 fármacos novos adicionados ao vocabulário (Bicalutamida, Fulvestranto, Everolimo,
  Avelumabe, Carfilzomibe, Trametinibe, Lapatinibe, Apalutamida, Ixazomibe).

**Auditoria avançada (23/jul/2026, mesmo dia, rodada seguinte) — 1 bug de
classificação + achado de cobertura, `recomputar_filtro_onco.py` rodado —
`eh_medicamento_onco=TRUE` foi de 13.355 → 14.038 (+683):**
- **Bug (17 itens):** catálogo do PNCP às vezes escreve princípio ativo composto em
  ordem invertida ("ZOLEDRONICO, ACIDO" em vez de "ACIDO ZOLEDRONICO", "ARSENIO
  TRIOXIDO" em vez de "TRIOXIDO DE ARSENIO") — substring exato nunca batia. Fix
  (`_bate_termo()`) restrito aos 2 únicos termos multi-palavra do vocabulário atual
  (escopo explícito, não regex genérico de permutação — evita abrir risco se o
  vocabulário crescer com termo multi-palavra novo sem entrada deliberada).
- 7 termos sem `CLASSE_FARMACO` (caíam em "Outro" silenciosamente) mapeados pra classe
  correta — não afeta `True`/`False`, só a quebra por classe farmacológica.
- **Achado de cobertura (não virou código — vocabulário vive em `coletor_onco.py`,
  decisão do usuário se/quando expandir):** ~35 fármacos oncológicos de peso comercial
  testados contra a base já coletada, **todos apareceram por coocorrência** mesmo nunca
  tendo sido termo de busca (Octreotida 153x, Ruxolitinibe 117x, Alectinibe 96x,
  Brentuximabe vedotina 93x, Interferona 83x, Megestrol 83x, Lanreotida 89x, Ponatinibe
  51x, Triptorrelina 65x, entre outros) — sinal de que o volume real de mercado onco é
  maior do que o coletado hoje, já que esses termos nunca foram buscados na API.
  **Risco de uso duplo a avaliar antes de adicionar** (mesmo padrão do double-check
  inicial): Interferona (hepatite, risco alto), BCG (vacina infantil universal — só
  "Onco BCG"/"BCG intravesical" seguro), Pamidronato (osteoporose, mesmo padrão do
  zoledrônico), Megestrol/Octreotida/Lanreotida (acromegalia).
- Ângulos que não acharam nada (robustez confirmada): ordenação termo-curto-contido-
  em-termo-maior (0 colisões nos 115 termos), variantes em inglês sem sufixo "-e",
  sinais estruturais (`criterio_julgamento_nome`, `tipo_beneficio_nome`, `unidade_medida`,
  extremos de valor).
