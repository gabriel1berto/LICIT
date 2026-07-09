# CLAUDE.md — Projeto LICIT

Context permanente para todas as sessões. Ler integralmente no início de cada conversa.

---

## 1. Negócio

**LICIT** é uma empresa individual (Empresário Individual) que participa de licitações públicas para vender pneus a órgãos governamentais (prefeituras, autarquias, institutos federais, penitenciárias, etc.).

**Uma frase:** Compro pneu de distribuidor, vendo para o governo via pregão ou dispensa eletrônica, entrego via frete.

| Campo | Valor |
|---|---|
| Razão social | G. Humberto Araujo Magalhães |
| CNPJ | 46.552.201/0001-00 |
| Sede | Fortaleza, CE |
| CNAE principal | 4530-7/02 (comércio a varejo de pneumáticos) |
| Regime | Simples Nacional / ME |
| Email operacional | ghumberto.eng@gmail.com |

---

## 2. Modelo de Operação

```
RADAR (pncp_radar.py)
    → Detecta novos editais de pneus no PNCP
    → Filtra por palavras-chave: pneu, pneumático, pneus
    → Envia email com resumo diário

ANÁLISE DO EDITAL (analisa_edital.py)
    → Baixa documentos via API PNCP
    → Extrai: itens, medidas, especificações técnicas, critérios de habilitação
    → Claude gera JSON estruturado
    → Escreve card no Kanban Notion (via REST API ou MCP)

COTAÇÃO DE DISTRIBUIDORES (scrapers por distribuidor)
    → bransales_scraper.py — Bransales Atacadista
    → cantu_scraper.py — Cantu / SpeedMax B2B
    → gp_scraper.py — GP Fácil (cookies necessários, reCAPTCHA bloqueia login)
    → green_scraper.py — PneuGreen
    → Saída: results_X.json → upload para Notion via notion_upload.py / MCP

HABILITAÇÃO
    → Verificar documentação da empresa contra critérios do edital
    → Obter carta de solidariedade do distribuidor

PROPOSTA
    → Carta proposta espelha linguagem exata do edital
    → Preço = custo × 1.24 (20% margem + 4% imposto)

ENTREGA
    → Frete cotado pós-adjudicação (risco: não ajustar após vencer)
```

---

## 3. Status Atual de Tração

**Contratos vencidos: 0**

Perdas anteriores causadas por habilitação incompleta, não por pricing.

Editais analisados (jun/2026):
- IFES Campus Colatina (UASG 158272) — análise feita, não participou
- Embrapa Semiárido (UASG 135012) — análise feita, não participou
- Penitenciária de Mairinque SP (UASG 380263, ACD 101/2026) — dispensa eletrônica, 4 itens, análise competitiva feita
- PE 90051/2026 — Prefeitura de Cantagalo-RJ (UASG 985821) — 12 itens, sessão concluída 06/07/2026, cotações completas de 4 distribuidores no Notion. Não participamos.

Editais analisados (jul/2026 — pipeline novo, testes ponta a ponta):
- **Câmara Municipal de Itararé-SP** (2026/000019) — 2 itens passeio, análise+cotação completas.
- **Doutor Ulysses-PR PE 0017/2026** — 10 itens agrícola/OTR, cobertura baixa nos 4 distribuidores (esperado, fora do catálogo). Planilha gerada.
- **Prefeitura Nova Aurora/PR PE 027/2026** (UASG 987965) — 9 itens, sessão já ocorrida (03/07/2026), usado pra validar o Ciclo de Aprendizado (ver §15.6). Achado: nosso candidato (Pirelli 17.5-25, não confirmado) teria vencido 2 dos 9 itens.

Ver página Notion ["Ciclo de aprendizado"](https://app.notion.com/p/392ca98e928180c6a1bbcef7942f583b) pra histórico completo comparando nossa cotação vs resultado real de cada processo.

---

## 4. Distribuidores Cadastrados

Credenciais vivem só no `.env` (gitignorado) — nunca escrever senha aqui de novo (motivo: vazamento real de 8 dias em 2026, ver README.md § Segurança).

| Distribuidor | Portal | Ferramenta | Status |
|---|---|---|---|
| Bransales Atacadista | atacado.bransales.com.br | bransales_scraper.py + notion_upload.py | Funcional |
| Cantu / SpeedMax B2B | empresas.speedmax.com.br | cantu_scraper.py + cantu_upload.py | Funcional |
| GP Fácil | gpfacil.com.br | gp_scraper.py | Funcional — cookies expiram, renovar via MCP browser |
| PneuGreen | pneugreen.com.br | green_scraper.py | Funcional |

**Prioridade de hub de fornecimento:** Fortaleza (RR Pneus, Gerardo Bastos) → SP/ABC → Goiânia/DF

---

## 5. Fórmula de Precificação (fixada jun/2026)

```
Preço de leilão UN  = Custo × 1.24
Margem sem frete    = Custo × 0.20
Imposto             = "4%"
Investimento total  = Custo × Qtde
Frete               = cotação manual pós-análise
```

---

## 6. Riscos Operacionais Críticos

1. **SICAF Inadimplente (risco existencial):** vencer e não entregar = bloqueio de participação futura. Regra absoluta: só participar com fornecedor confirmado.
2. **Ajuste de preço pós-adjudicação:** impossível. Confirmar preço com fornecedor ANTES da sessão de lances.
3. **Habilitação incompleta:** causa real das perdas. Checar CEFR FGTS (bloqueado por migração MEI→ME) e TJCE (aguardando SIRECE) antes de participar.
4. **INMETRO pode estar em nome do distribuidor:** aceito (aprendizado do caso SP Prime, concorrente vencedor analisado).

---

## 7. Stack e Ferramentas

**Lista de scripts e variáveis de ambiente: dono canônico é `README.md`** (seções "Estrutura" e "Setup") — não duplicar tabela aqui de novo. Esta seção guarda só o que é específico do assistente, não do repo em si.

**NOTION_TOKEN (.env):** só acessa páginas explicitamente compartilhadas com a integração "Claude Code" (ID: `326ca98e-9281-81f6-928d-00279a7fa3fa`). `NOTION_DB_ID=f5662b50-f2f3-467e-9051-b6b9f683ff88` é o DB Bransales Cantagalo. Para páginas não compartilhadas, usar MCP Notion em vez da REST API do `.env`.

---

## 8. MCP Servers Disponíveis

| MCP | Uso principal |
|---|---|
| Notion | Ler/escrever cards, bancos inline, kanban |
| Google Drive | Criar planilhas de resultado, anexos |
| Gmail | Enviar cotações, comunicação com órgãos |
| Playwright | Navegação autenticada (scraping B2B, renovação de cookies) |
| Supabase | Conectado — sem tabelas ainda (ver §13 para plano futuro) |

---

## 9. Notion — Estrutura Operacional

### 9.1 URLs e IDs principais

| Recurso | URL / ID |
|---|---|
| Página principal | https://app.notion.com/p/37cca98e92818146a571c6fe00672fa9 |
| Documentação da empresa | https://app.notion.com/p/37cca98e928181e8b3c8d415e6fe55bc |
| Kanban de editais | https://app.notion.com/p/928d078b71a740aeaf438ac091dfc8fc?v=37cca98e928181d398c9000ce2560554 |
| Banco de fornecedores | https://app.notion.com/p/ff81185ce0cd442d8d1386fa4392914d?v=aebae1afd24047dea6dd055f4c239f8a |
| Análise de produto (DB inline schema) | Collection ID: 382ca98e-9281-80b4-8e04-000bb9d221f5 |
| Monitor de concorrentes | https://app.notion.com/p/38cca98e928181ffa9d1df1fe21c1853 |

### 9.2 PE 90051/2026 — Cantagalo-RJ (concluído, sessão 06/07/2026 — não participamos)

| Recurso | ID |
|---|---|
| Card Notion | https://app.notion.com/p/388ca98e92818094bd28fa244ccd899e |
| DB Bransales | data_source_id: afe6de69-5f93-4af0-b82d-ba41bc5dba34 |
| DB Cantu | data_source_id: 18b5a92e-9aeb-4daa-96e8-b6f0ada7d4e6 |
| DB GP | data_source_id: 4cb3168e-1bb7-4fed-816c-05b0d617bcc7 |
| DB Green Pneus | data_source_id: ba22e499-8c23-4153-a0ba-a2e4cd3cfad1 |

### 9.3 Regras Notion MCP

- `insert_content` com `position: "end"` para append sem tocar conteúdo existente
- REST API Notion retorna 404 para databases criados via MCP OAuth → usar `notion-create-pages` com `data_source_id`
- Todas as colunas de tabela declaradas no header, mesmo que vazias
- `notion-fetch` funciona melhor com URL completa

---

## 10. Portais de Busca de Editais

| Portal | URL |
|---|---|
| PNCP nacional | https://pncp.gov.br/app/editais?q=pneus |
| PNCP Fortaleza | https://pncp.gov.br/app/editais?q=pneus&orgaosCnpj=07954605000160 |
| TCE-CE municípios | https://municipios-licitacoes.tce.ce.gov.br |
| SEPOG Fortaleza | compras.sepog.fortaleza.ce.gov.br |

**Limitação conhecida:** PNCP tem WAF que bloqueia requests automatizados sem delay. pncp_radar.py já inclui rate limiting.

**Limitação ComprasNet:** documentos de fornecedores (proposta, marca, habilitação submetida) requerem login autenticado. URLs públicas retornam 404.

---

## 11. Habilitação da Empresa

| Documento | Status |
|---|---|
| CADIN Federal | ✅ |
| CNDT TST | ✅ válido até dez/2026 |
| Certidão Municipal Fortaleza | ✅ |
| Certidão Fazenda Estadual CE | ✅ |
| Simples Nacional | ✅ |
| CNJ Improbidade | ✅ |
| Certidão Conjunta RFB/PGFN | ✅ válida até dez/2026 |
| TJCE Certidão de Falência | ⚠️ DAE pago, aguardando SIRECE |
| CEFR FGTS | ❌ Bloqueado — requer atualização CAIXA pós-MEI→ME |

---

## 12. Inteligência Competitiva — Penitenciária de Mairinque (ACD 101/2026)

4 concorrentes identificados via PNCP (resultados públicos):

| Empresa | CNPJ | Itens ganhos | Posição |
|---|---|---|---|
| SP PRIME SUPRIMENTOS LTDA | 23.461.248/0001-05 | Item 4 (R$ 688,94/UN) | Principal concorrente |
| LICITPNEUS COMERCIO E REPRESENTACAO LTDA | 39.247.048/0001-53 | Item 1 (R$ 532/UN) | Especialista licitação |
| RONALDO MILANI COMERCIAL LTDA | — | Item 2 (R$ 375/UN) | — |
| I. BORDIGNON PNEUS LTDA | — | Item 3 (R$ 589/UN) | — |

Planilha FORNECEDORES — INTELIGÊNCIA COMPETITIVA: Google Drive ID `19ehlc0kVNoKY1NgOiJpbek32SOqjKNW3Hl1zAxfewLs`
(Coluna MARCA preenchida como "A confirmar" — dados de fornecedor requerem login ComprasNet)

---

## 13. Roadmap AI-FIRST (Supabase — ativar com ~3-4 meses de histórico)

**Não confundir com o Supabase do pipeline de mercado nacional (`analise/`, projeto `LICIT` koqsgnvmnzkqzxnskzgq) — esse já está ativo desde 07/jul/2026, schema diferente (editais/detalhes/itens/resultados, ver README.md). O roadmap abaixo é uma segunda base, ainda não construída, pra dado de negócio (histórico de propostas/concorrentes), separada da de mercado.**

**Não evoluir proativamente — só quando usuário solicitar.**

Tabelas planejadas:
```sql
processos  — id_pncp, uasg, objeto, datas, status, valores
itens      — catmat, descricao, medida, qtd, vl_estimado, vl_homologado
fornecedores — cnpj, razao_social, porte, uf, primeira/ultima vez visto
precos     — catmat, uf, data, vl_unit_homologado, cnpj_vencedor, id_processo
```

Skills em backlog: `competitor-profiler`, `price-benchmarker`, `organ-profiler`

---

## 14. Skills Instaladas

### Projeto (C:\Users\ghumb\code\licit\.agents\skills\)

**founder-playbook (15 skills):**
`100m-leads`, `100m-offers`, `blue-ocean-strategy`, `crossing-the-chasm`, `diagnose`, `four-steps`, `influence`, `lean-startup`, `made-to-stick`, `mom-test`, `monetizing-innovation`, `obviously-awesome`, `spin-selling`, `storybrand`, `traction`

**data-analytics-skills (31 skills, github.com/nimrodfisher/data-analytics-skills):**
- *Qualidade/validação:* `programmatic-eda`, `data-quality-audit`, `query-validation`, `schema-mapper`, `metric-reconciliation`
- *Documentação:* `semantic-model-builder`, `analysis-documentation`, `data-catalog-entry`, `sql-to-business-logic`, `analysis-assumptions-log`
- *Análise:* `cohort-analysis`, `segmentation-analysis`, `funnel-analysis`, `time-series-analysis`, `root-cause-investigation`, `ab-test-analysis`, `business-metrics-calculator`
- *Storytelling/viz:* `insight-synthesis`, `visualization-builder`, `executive-summary-generator`, `dashboard-specification`, `data-narrative-builder`
- *Stakeholder:* `technical-to-business-translator`, `stakeholder-requirements-gathering`, `analysis-qa-checklist`, `methodology-explainer`, `impact-quantification`
- *Workflow:* `analysis-planning`, `context-packager`, `peer-review-template`, `analysis-retrospective`

Relevante pra pipeline `analise/` (DuckDB + ComprasGOV): `query-validation` (revisar os SQL de filtro), `time-series-analysis` (sazonalidade), `data-quality-audit` (achar mais bug tipo o de "pneumático"), `visualization-builder` (complementa a skill `dataviz` global).

**A criar (aprovadas para este projeto):**
- `edital-analyzer` — análise estruturada de edital/TR com critérios de risco
- `competitive-intelligence` — profiling de concorrente licitante (adaptada de versão B2B SaaS)

### Globais (C:\Users\ghumb\.claude\skills\)

`icp-identification`, `launch-positioning-builder`, `voice-of-customer-synthesizer`

---

## 15. Como Usar as Skills do founder-playbook

```bash
# Diagnóstico geral (entry point recomendado)
/diagnose

# Skills específicas
/traction          # canais de distribuição (como chegar em mais órgãos)
/obviously-awesome # posicionamento (como se diferenciar de concorrentes)
/blue-ocean-strategy # encontrar mercado menos disputado
/mom-test          # validar hipóteses com compradores públicos
/monetizing-innovation # estrutura de preços e empacotamento
/100m-offers       # construir proposta irresistível
/lean-startup      # iterar rápido com base em resultados de processos
/spin-selling      # abordagem consultiva para órgãos (quando houver contato direto)
```

**Context brief para as skills (colar quando pedir):**
> LICIT vende pneus para licitações públicas (pregão e dispensa eletrônica, Lei 14.133/21). Empresa individual ME, Fortaleza-CE, CNPJ 46.552.201/0001-00. Clientes são órgãos públicos (prefeituras, autarquias, institutos federais). Competição é aberta — qualquer empresa com CNPJ pode participar. Tração: 0 contratos fechados. Perdas anteriores por habilitação documental incompleta. Ferramentas de automação operacionais (radar + scraping + análise). Próximos passos: participar do PE 90051/2026 Cantagalo-RJ (sessão 06/07/2026).

---

## 15.5 Planilha modelo de precificação (Google Sheets)

Formato final de precificação é planilha, não tabela Notion (decisão 09/jul/2026 — tabela Notion achatada foi considerada ruim demais pra decisão).

- **Modelo mestre:** https://drive.google.com/drive/folders/1Nf10IsY2Gzpf_1WXWuKBC0B58vAbnuXX — **nunca editar direto**, sempre duplicar (`copy_file` MCP) antes de preencher. Toda mudança estrutural (coluna nova, fórmula) vai no modelo E na cópia ativa, nunca só numa.
- **Estrutura (12/jul/2026):** 4 blocos empilhados (Bransales linha 5-16, Cantu 20-31, GP 35-46, Green Pneus 50-61), 12 linhas de item cada. Colunas de entrada A-L: Item / **Produto** (tipo: Pneu/Câmara de ar/Roda/etc) / **Modelo** (medida) / **Especificação Técnica** (IC/IV/Treadwear/Construção/INMETRO, N/D se ausente) / Critérios técnicos / Distribuidor / Marca / Link / Observação / Preço UN / **Ref. Edital** (era "Preço Leilão", renomeado) / Qtde. Coluna **U = Vencedor** (fórmula, compara Preço UN do mesmo item nos 4 blocos, marca "🏆 Vencedor" no mais barato — **PT-BR usa `;` não `,` como separador de argumento de função**, `,` só decimal). Colunas N-Q + W/X/Y = fórmula (Investimento/Frete/Imposto/Preço de venda/Margem ruim/boa/líquida) — uniformizadas nos 4 blocos, nunca escrever nelas. Notas de documentação (hover) em cada cabeçalho.
- **Timestamp:** script grava "Última cotação: DD/MM/AAAA HH:MM" na linha do nome do distribuidor toda vez que roda.
- **OAuth Sheets API:** configurado 09/jul/2026 (`credentials.json`/`token.json` no repo, gitignorado). Projeto Google Cloud usado: `mindful-hall-501916-s4` (diferente do suspenso por abuso). App em modo "Teste" — `ghumberto.eng@gmail.com` já cadastrado como test user (limite 100 usuários, não precisa publicar).
- **Script ativo:** `preencher_planilha_precificacao.py <spreadsheet_id> <analise.json> --bransales X --cantu X --gp X --green X` — **`precificacao_gsheets.py` é o script antigo, deprecado, não usar.**
- Testado em 2 editais reais (Doutor Ulysses-PR, Nova Aurora-PR). Bug crítico corrigido 09/jul: `apto=False` no resultado do scraper não é sinônimo de "sem estoque" — pode ser "achou produto real, critério não confirmado" (⚠️ Parcial). Script antigo escondia esse produto real como "Sem estoque"; corrigido em `linha_para_item()`.

## 15.6 Ciclo de Aprendizado — processo padrão (confirmado 09/jul/2026)

Depois que o usuário preenche "📊 Análise do Leilão" de um card com o resultado real da sessão, gerar aprendizado seguindo **sempre** esses passos (ver [[feedback_licit_ciclo_aprendizado_padrao]] na memória):

1. Anunciar o processo antes de rodar
2. Buscar o card com "Análise do Leilão" preenchida + a página ["Ciclo de aprendizado"](https://app.notion.com/p/392ca98e928180c6a1bbcef7942f583b) (formato de referência)
3. Comparar nosso melhor candidato (planilha/scraper) vs preço que realmente venceu, item a item
4. Resumo em 4 pontos fixos, sempre nessa ordem: **Concorrentes | Produto | Edital | Processo** (Processo leva tabela item-a-item quando há comparação numérica)
5. **Mostrar o rascunho e esperar confirmação antes de escrever no Notion — nunca escrever direto**
6. Só depois de confirmado, inserir como novo accordion `<details>`, preservando os anteriores intactos

## 16. Benchmark

**LiciNexus** (https://www.licinexus.com.br) — plataforma brasileira de licitações com funcionalidades de referência para o projeto: radar, análise de edital, cotação.

---

## 17. Regras Operacionais para o Assistente

1. Nunca inventar informações de edital — usar apenas documentos baixados via API
2. Ao propor escrita no Notion, usar MCP (não REST API) para databases criados via MCP OAuth
3. Ao criar planilha no Drive, usar `create_file` (não existe `update_file_content`) — cria novo arquivo se necessário
4. Não evoluir metabase-write ou Supabase proativamente
5. Antes de criar qualquer coisa (script, planilha, página): explicar o plano e perguntar se há custos/requests externos envolvidos
6. Ao detectar novo edital relevante: apresentar tabela de breakdown (itens, valores, risco) antes de propor ação
7. **`analisa_edital.py` nunca pode alucinar (regra travada em código, 09/jul/2026):** todo documento do edital deve ser aberto e lido independente do formato (pdf/docx/txt/html/fallback best-effort — nunca pular arquivo em silêncio). Se a extração ficar abaixo de `LIMIAR_CHARS_CONFIAVEIS` (500 chars confiáveis), o processo levanta `ExtracaoInsuficiente` e **para antes de chamar Claude ou escrever no Notion** — nunca gerar análise sem base documental real. Não relaxar esse limiar nem contornar a trava sem pedido explícito. **Mesma regra vale pro `cabecalho.valor_total`:** nunca confiar em texto livre do documento (já variou entre chamadas pro mesmo edital) — usar `valorTotalEstimado` da API do PNCP via `api/consulta/v1` (não `api/pncp/v1`, que retorna esse campo sempre `None`) quando disponível. Divergência vs soma dos itens vira alerta bloqueante no card, nunca é resolvida escolhendo um número sozinho (ver `validar_valor_total()`).
8. **Testar mudança nesse pipeline só manualmente, 1 ferramenta por vez** — usuário decidiu (09/jul/2026) não automatizar o fluxo completo (buscar edital → card → análise → precificação) ainda. Rodar uma etapa, parar, esperar feedback antes de encadear a próxima.
9. **Formato do card de análise (com coluna Produto + docs anexados) é padrão aprovado (09/jul/2026)** — não redesenhar sem pedido explícito novo. Estrutura fixa: ANÁLISE DE EDITAL → DOCUMENTOS USADOS NA ANÁLISE → HABILITAÇÃO → PRODUTOS (com coluna Produto) → PONTOS-CHAVE → LEILÃO → DOCUMENTOS DA PROPOSTA. Mudanças futuras devem ser aditivas/corretivas (bug), não redesign.
10. **Ciclo de Aprendizado segue processo fixo de 6 passos** (ver §15.6) — sempre mostrar rascunho e esperar confirmação antes de escrever no Notion.
11. **Manter README.md, este arquivo e a descrição das ferramentas no Notion sincronizados com o código** — toda vez que um bug for corrigido ou uma feature mudar comportamento, atualizar a documentação relevante no mesmo momento, não depois. Motivo: usuário já foi pego de surpresa por ferramenta com bug que "voltou" — documentação desatualizada é o mesmo risco.
12. **Arquitetura "1 dono só por fato" (fixada 09/jul/2026):** cada informação vive em exatamente 1 lugar canônico — `README.md` (setup/estrutura/scripts), `CLAUDE.md` (regras operacionais, negócio, processo), memória do assistente (feedback/decisão, só ponteiro pros dois acima quando o fato já existe ali) e Notion (estado vivo de cada processo/edital). Nunca copiar o mesmo fato em 2 lugares — se precisar citar, linkar/referenciar. A trava real que sustenta isso: toda memória LICIT tem uma entrada dizendo pra sempre ler este arquivo primeiro (ver memória `feedback_licit_sempre_ler_claudemd`), já que CLAUDE.md não é carregado automaticamente fora do repo. Política completa documentada no Notion (página "Arquitetura de Documentação — LICIT").
13. **Assistente atua como fiscal ativo dessa hierarquia (12/jul/2026):** antes de escrever qualquer doc (README/CLAUDE.md/memória/Notion) ao evoluir uma ferramenta, checar se o fato já tem dono definido em outro lugar. Se a ação pedida (pelo próprio usuário ou por mim) violar "1 dono só" — duplicar fato em 2 arquivos, escrever regra de negócio no README, criar entrada de memória pra fato que já mora no CLAUDE.md, redesenhar algo já marcado como padrão aprovado (regras 9/10) sem pedido explícito — **parar e avisar antes de executar**, propondo o lugar/formato correto. Só seguir com a duplicação se o usuário confirmar explicitamente depois do aviso. Vale mesmo se o pedido vier direto do usuário — avisar não é opcional.
