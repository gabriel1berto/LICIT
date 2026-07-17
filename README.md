# LICIT

Venda de pneus para licitações públicas (pregão eletrônico e dispensa eletrônica, Lei 14.133/21). Empresa individual, CNPJ 46.552.201/0001-00.

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

Contexto completo do negócio (riscos, fórmulas, habilitação, Notion): `CLAUDE.md`.

## Estrutura

```
licit/
├── pncp_radar.py            Radar diário — busca edital novo no PNCP, envia email. Resiliente a queda:
│                            ciclo de 10 tentativas, se falhar avisa por email (1x) e repete a cada
│                            30min até conseguir (job do GH Actions com budget de tempo maior pra isso)
├── analisa_edital.py        Camada 1. Baixa edital via API PNCP (pdf/docx/txt/html), Claude extrai JSON → card Notion.
│                            Trava (ExtracaoInsuficiente) se o documento não puder ser lido com confiança —
│                            nunca analisa sem base documental real. Usa valorTotalEstimado oficial do PNCP
│                            (api/consulta/v1), não o texto livre. Anexa os documentos originais no card.
│                            Card inclui recomendação "evoluir_parecer_juridico" (sim/não + motivo) —
│                            não chama a Camada 2 sozinho, só sinaliza se vale a pena rodar.
├── parecer_juridico.py      Camada 2, script SEPARADO — só roda manualmente, nunca encadeado pela Camada 1.
│                            Lê analise_{cnpj}_{ano}_{seq}.json (saída da Camada 1) + arsenal_juridico.md
│                            inteiro, gera recomendações ARS-XX (cada uma com baseado_em + confiança),
│                            escreve seção própria no card. Nunca presume fato com "fonte": null da Camada 1.
├── bransales_scraper.py     Cotação — Bransales Atacadista
├── cantu_scraper.py         Cotação — Cantu / SpeedMax B2B
├── gp_scraper.py            Cotação — GP Fácil (cookies exportados — reCAPTCHA bloqueia login direto)
├── green_scraper.py         Cotação — PneuGreen (só ele valida se a medida do produto bate com a pedida
│                            antes de aceitar — os outros 3 usam URL estruturada por medida, mais seguro)
├── notion_upload.py         Upload resultado Bransales → Notion (REST API)
├── cantu_upload.py          Upload resultado Cantu → Notion (REST API)
├── preencher_planilha_precificacao.py  Preenche cópia da planilha modelo (Sheets) com resultado dos
│                            4 scrapers + referência do edital — ver seção "Precificação" abaixo
├── precificacao_gsheets.py  ⚠️ DEPRECADO — hardcoded pro Cantagalo (jun/2026), não usar em edital novo
├── sample_objeto.py         Script de exploração pontual da API PNCP (objetoCompra)
├── items_X.json / results_X_*.json / analise_X.json   Input/output de cotação por edital
│                            (gitignorado — dado local, nome muda por processo)
│
├── analise/                 Pipeline de análise de mercado (dado público PNCP)
│   ├── coletor_pncp.py         Fase 1 — descobre editais (API de busca), grava em Postgres
│   ├── coletor_pncp_detalhe.py Fase 2 — baixa detalhe+itens+resultado de cada edital da fila
│   ├── filtro_pneu.py          Filtro compartilhado "é pneu de verdade?" (regex + regras)
│   ├── test_filtro_pneu.py     Regressão do filtro (12 achados históricos + 4 de 14/jul/2026 +
│   │                           7 de categoria em 16/jul/2026) — ver "Auto-aperfeiçoamento" abaixo
│   ├── pneu_medida_matcher.py  Matching determinístico de medida (tupla largura/perfil/aro),
│   │                           reusado pelo cotacao_master/ — ver Ciclo de match abaixo
│   ├── conectar_pncp.py        Queries do schema `public` (mercado PNCP) usadas pelo dashboard —
│   │                           inclui carregar_editais_abertos() (ver Radar de Editais abaixo)
│   ├── conectar_cotacao_master.py  Queries do schema `cotacao_fornecedor` (ver Cotação Master abaixo)
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
├── cotacao_master/           Coleta diária de preço direto nos 4 distribuidor (ver seção própria abaixo)
│   ├── *_scraper_master.py     Cópia dos 4 scrapers de edital, adaptada (sem limite de candidato,
│   │                           ficha técnica sempre) — originais na raiz NUNCA são alterados
│   ├── cotacao_master.py       Orquestrador — roda os 4 sequencial, grava no Supabase
│   ├── classificador_alias.py  Regra determinística (zero custo de token) pra sinalizar produto
│   │                           reforçado/comercial (sufixo C, índice de carga duplo, Lonas, Van)
│   └── requirements.txt
│
├── schema_cotacoes_diarias.sql  Schema do schema `cotacao_fornecedor` (medidas/aliases_medida/cotacoes)
├── medidas_prioritarias.json    Config versionada — lista de medida cotada diariamente
│
└── .github/workflows/        Automação (ver abaixo)
```

## Automação (GitHub Actions)

| Workflow | Quando roda | O que faz |
|---|---|---|
| `pncp_radar.yml` | dias úteis, 5h BRT | Radar diário → email |
| `pncp_coletor_editais.yml` | diário, ~meia-noite BRT (+ manual) | Fase 1 — reescaneia as 27 UFs pra achar edital novo (`--reset`, ver docstring de `coletor_pncp.py`) |
| `pncp_coletor_detalhe.yml` | a cada ~5h30 | Fase 2 — processa fila pendente (editais novos entram sozinhos) |

Fase 2 não descobre edital novo sozinha — só fase 1 faz isso (API não permite paginar por data). Rodar `coletor_pncp.py --reset` é a única forma de achar processo novo.

### Auto-aperfeiçoamento do filtro (`filtro_pneu.py`)

Regra fixada em `CLAUDE.md` §17.15, mesma cadência do §17.14 (mensal, último dia útil —
compartilha o lembrete de calendário, ver `feedback_licit_cotacao_master_autoaperfeicoamento`
na memória). 2 investigações separadas, cada rodada:

1. **Falso positivo/negativo no filtro item-a-item** — cruza `itens.eh_pneu=TRUE` contra o
   campo estruturado `material_ou_servico` (sinal barato, nunca usado por padrão) + amostra os
   buckets de risco. Todo bug achado vira teste em `test_filtro_pneu.py` **antes** do fix (prova
   que é bug de verdade), depois o fix, depois **medir o impacto na base inteira** (quantos itens
   mudariam de classificação) antes de aplicar via `recomputar_filtro.py` — repetir a medição até
   estabilizar (achado 14/jul/2026: um fix mal calibrado regride caso que já funcionava; só
   medição contra a base real pega isso).
2. **Cobertura da busca (fase 1)** — `TERMO_BUSCA` é 1 palavra só ("Pneu"). Testar se edital com
   pneu "escondido" (título/descrição burocrático genérico) escapa: buscar termo mais amplo/
   adjacente na API ao vivo pra 1 UF amostra, comparar contra o banco, e **confirmar item a item**
   (catálogo real via API de detalhe) se os "novos" achados têm pneu de verdade — a maioria de
   termo genérico é ruído (achado 14/jul/2026: 36 candidatos amostrados via "manutenção de
   frota"/"peça veícular"/"borracharia", 0 tinham pneu real).

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
Abertos abaixo).

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

**Automação:** `.github/workflows/cotacao_master.yml`, só `workflow_dispatch` (manual) até
validar rodagem real — sem cron ainda.

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

- **Modelo mestre:** [pasta no Drive](https://drive.google.com/drive/folders/1Nf10IsY2Gzpf_1WXWuKBC0B58vAbnuXX) — nunca editar direto, sempre duplicar (`copy_file`) antes de preencher
- 4 blocos empilhados (Bransales/Cantu/GP/Green), colunas de entrada A-L (Item/Produto/Modelo/Especificação Técnica/Critérios/Distribuidor/Marca/Link/Observação/Preço UN/Ref. Edital/Qtde) + coluna Vencedor (fórmula, compara os 4 blocos). Colunas de cálculo (Investimento/Frete/Imposto/Preço de venda/Margem) são fórmula — nunca escrever nelas.
- `python preencher_planilha_precificacao.py <spreadsheet_id> <analise.json> --bransales X --cantu X --gp X --green X`
- Detalhe completo: `CLAUDE.md` §15.5

## Ciclo de Aprendizado

Depois de cada sessão de lances, comparar nossa cotação vs resultado real e registrar em [Ciclo de aprendizado](https://app.notion.com/p/392ca98e928180c6a1bbcef7942f583b) (4 pontos fixos: Concorrentes/Produto/Edital/Processo). Processo documentado em `CLAUDE.md` §15.6.

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

Radar (`requirements_radar.txt`) e pipeline de mercado (`analise/requirements.txt`) têm dependências separadas de propósito — o radar não precisa puxar `psycopg2`/`streamlit`.

`cotacao_master.yml` (GitHub Actions) roda em nuvem, não lê `.env` — precisa dos mesmos pares
acima (`BRANSALES_EMAIL/PASSWORD`, `CANTU_EMAIL/PASSWORD`, `GREEN_EMAIL/PASSWORD`,
`DATABASE_URL`) cadastrados como **Secrets do repo** (Settings → Secrets and variables →
Actions), mais `GP_COOKIES_JSON` (conteúdo inteiro do `gp_cookies.json`, escrito em arquivo por
um step do workflow). Bransales não entra — roda só local (ver seção Cotação Master acima).

## Segurança

- `.env`, `gp_cookies.json`, `credentials.json`/`token.json` (OAuth Google Sheets) — gitignorados, nunca commitados
- Credenciais dos distribuidores viveram hardcoded no código, repo público, entre 29/jun e 07/jul/2026 (commit `2456dcf` corrigiu, moveu pra `.env`) — histórico antigo do git ainda contém as senhas removidas; **trocar as 3 senhas nos portais (Bransales/Cantu/PneuGreen) e avaliar reescrever o histórico do git** enquanto o repo for público
- RLS habilitado nas 6 tabelas do Supabase (sem policy — acesso só via `DATABASE_URL`/service role, que faz bypass)
